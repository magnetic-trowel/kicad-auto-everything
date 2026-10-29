# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate G1 for kae.em: the raster PEEC solver against FastHenry on identical geometry.

    python em_vs_fasthenry.py run CASE {em PITCH | fh} [-o results.jsonl]
    python em_vs_fasthenry.py table results.jsonl

Cases (mm; 1 oz copper, h = 0.2 mm unless stated; f = 100 MHz):
  microstrip20/30  0.5 mm trace over a 40 x 10 plane, shorted at the far end (L' from the pair)
  slot / noslot    0.3 mm trace, 20 mm long, crossing a 1 x 12 mm slot cut across its return
  pair             two 0.3 mm traces 1 mm apart, both shorted: L11, L22, M12
  viahole          two traces over a plane with a 4 x 4 hole; one returns through a via
  planepair        20 x 20 plane pair, h = 0.1, fed and shorted along opposite edges
For em, each case runs at the pitch given; the table Richardson-extrapolates pairs of pitches
(first order, as the boost-loop refinement study shows) and reports the error estimate.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "kae" / "src"))

T = 0.035
F = 1e8


def _trace_over_plane(L, w, h=0.2, slot=None, py=20.0, px=None):
    zs = T + h
    px = px or L + 10
    yc = py / 2
    x0 = 5.0
    holes = [slot] if slot else []
    return dict(sigma=5.8e7, freqs=[F],
                rects=[dict(x0=x0, y0=yc - w / 2, x1=x0 + L, y1=yc + w / 2, z=zs, t=T, name="tr")],
                planes=[dict(x0=0, y0=0, x1=px, y1=py, z=0, t=T, holes=holes, name="gnd", pitch=(0.1, 0.1))],
                ports=[dict(p=(x0, yc, zs + T / 2), n=(x0, yc, T / 2), name="P")],
                shorts=[dict(a=(x0 + L, yc, zs + T / 2), b=(x0 + L, yc, T / 2))])


def cases():
    out = {}
    for L in (20, 30):
        out[f"microstrip{L}"] = _trace_over_plane(L, 0.5, py=10.0, px=L + 10)
    out["noslot"] = _trace_over_plane(20, 0.3)
    out["slot"] = _trace_over_plane(20, 0.3, slot=(14.5, 4.0, 15.5, 16.0))
    s = _trace_over_plane(20, 0.3)
    yc, zs, x0 = 10.0, T + 0.2, 5.0
    s["rects"].append(dict(x0=x0, y0=yc + 1.3 - 0.15, x1=x0 + 20, y1=yc + 1.3 + 0.15, z=zs, t=T, name="tr2"))
    s["ports"].append(dict(p=(x0, yc + 1.3, zs + T / 2), n=(x0, yc + 1.3, T / 2), name="P2"))
    s["shorts"].append(dict(a=(x0 + 20, yc + 1.3, zs + T / 2), b=(x0 + 20, yc + 1.3, T / 2)))
    out["pair"] = s
    from ref_fasthenry import smoke_spec
    v = smoke_spec(None, hole=True)
    v.pop("workdir", None)
    v["freqs"] = [F]
    v["planes"][0]["pitch"] = (0.1, 0.1)
    v["planes"][0].pop("cells", None)
    out["viahole"] = v
    h = 0.1
    a = 20.0
    out["planepair"] = dict(sigma=5.8e7, freqs=[F],
                            planes=[dict(x0=0, y0=0, x1=a, y1=a, z=T + h, t=T, name="top", pitch=(0.25, 0.25)),
                                    dict(x0=0, y0=0, x1=a, y1=a, z=0, t=T, name="bot", pitch=(0.25, 0.25))],
                            ports=[dict(p=(0.3, a / 2, T + h + T / 2), n=(0.3, a / 2, T / 2), name="P")],
                            shorts=[dict(a=(a - 0.3, y, T + h + T / 2), b=(a - 0.3, y, T / 2)) for y in np.linspace(1, a - 1, 10)])
    return out


def run_em(spec, pitch, nsub=3):
    from kae.em import solve as S
    from kae.em.spec import mesh_of
    m = mesh_of(spec, pitch, nsub=nsub)
    r = S.solve(m, spec["freqs"])
    return dict(Z=[[[z.real, z.imag] for z in row] for row in r["Z"][0]], iters=r["iters"], seconds=r["seconds"],
                stats=r["stats"])


def run_fh(spec):
    import ref_fasthenry as FH
    r = FH.solve(spec)
    return dict(Z=[[[z.real, z.imag] for z in row] for row in r["Z"][0]], seconds=r["seconds"], nfil=r.get("nfil"))


def main(argv):
    if argv[0] == "run":
        name, solver = argv[1], argv[2]
        spec = cases()[name]
        t = time.time()
        if solver == "em":
            res = run_em(spec, float(argv[3]))
            tag = f"em@{argv[3]}"
        else:
            res = run_fh(spec)
            tag = "fh"
        rec = dict(case=name, solver=tag, wall=round(time.time() - t, 1), **res)
        out = argv[argv.index("-o") + 1] if "-o" in argv else None
        line = json.dumps(rec)
        print(line)
        if out:
            with open(out, "a") as fh:
                fh.write(line + "\n")
    elif argv[0] == "table":
        rows = [json.loads(l) for l in open(argv[1]) if l.strip()]
        w = 2 * np.pi * F
        by = {}
        for r in rows:
            Z = np.array([[complex(*z) for z in row] for row in r["Z"]])
            by.setdefault(r["case"], {})[r["solver"]] = Z
        for c, d in sorted(by.items()):
            fh = d.get("fh")
            ems = sorted((float(k[3:]), v) for k, v in d.items() if k.startswith("em@"))
            ext = None
            if len(ems) >= 2:
                (p1, Z1), (p0, Z0) = ems[0], ems[1]           # finest first
                ext = Z1 + (Z1 - Z0) * p1 / (p0 - p1)         # first-order Richardson
            P = (fh if fh is not None else ems[0][1]).shape[0]
            for i in range(P):
                for j in range(i, P):
                    q = lambda Z: Z[i, j].imag / w * 1e9
                    s = f"{c:12s} L[{i}{j}] nH  fh {q(fh) if fh is not None else float('nan'):8.4f}"
                    for p, Z in ems:
                        s += f"  em@{p:g} {q(Z):8.4f}"
                    if ext is not None:
                        s += f"  extrap {q(ext):8.4f} (+-{abs(q(ems[0][1]) - q(ext)):.4f})"
                        if fh is not None:
                            s += f"  err {q(ext) / q(fh) - 1:+.2%}"
                    print(s)


if __name__ == "__main__":
    main(sys.argv[1:])
