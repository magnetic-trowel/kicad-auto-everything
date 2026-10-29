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
    # the reference plane in three abutting bands: 0.1 mm cells under the traces (h/2), 0.4 mm elsewhere,
    # 3 filaments through the copper (FastHenry's automatic choice runs out of memory at 0.85M filaments)
    bands = [(0, yc - 2.5, 0.4), (yc - 2.5, yc + 3.5, 0.1), (yc + 3.5, py, 0.4)]
    planes = []
    for k, (b0, b1, pp) in enumerate(bands):
        hb = [(hx0, max(hy0, b0), hx1, min(hy1, b1)) for hx0, hy0, hx1, hy1 in holes if hy0 < b1 and hy1 > b0]
        for q, ((a0, c0, a1, c1), hh) in enumerate(_band_pieces(0, b0, px, b1, hb)):
            planes.append(dict(x0=a0, y0=c0, x1=a1, y1=c1, z=0, t=T, holes=hh, name=f"gnd{k}{q}", pitch=(pp, pp)))
    return dict(sigma=5.8e7, freqs=[F], plane_nhinc=3,
                rects=[dict(x0=x0, y0=yc - w / 2, x1=x0 + L, y1=yc + w / 2, z=zs, t=T, name="tr")],
                planes=planes,
                ports=[dict(p=(x0, yc, zs + T / 2), n=(x0, yc, T / 2), name="P")],
                shorts=[dict(a=(x0 + L, yc, zs + T / 2), b=(x0 + L, yc, T / 2))])


def _band_pieces(x0, y0, x1, y1, holes):
    """A band minus its holes as FastHenry planes: a hole that spans the band's full height would cut
    one plane in two (FastHenry needs each plane connected), so the band is split at it."""
    full = [h for h in holes if h[1] <= y0 + 1e-9 and h[3] >= y1 - 1e-9]
    if not full:
        return [((x0, y0, x1, y1), list(holes))]
    hx0, _, hx1, _ = full[0]
    rest = [h for h in holes if h is not full[0]]
    out = []
    for a, b in ((x0, hx0), (hx1, x1)):
        if b - a > 1e-9:
            out += _band_pieces(a, y0, b, y1, [h for h in rest if h[0] < b and h[2] > a])
    return out


def _banded(name, z, px, py, yc, holes=(), fine=0.1, coarse=0.4, half=2.5):
    """A plane in three abutting bands (fine under the traces at yc)."""
    out = []
    for k, (b0, b1, pp) in enumerate([(0, yc - half, coarse), (yc - half, yc + half, fine), (yc + half, py, coarse)]):
        hb = [(hx0, max(hy0, b0), hx1, min(hy1, b1)) for hx0, hy0, hx1, hy1 in holes if hy0 < b1 and hy1 > b0]
        for q, ((a0, c0, a1, c1), hh) in enumerate(_band_pieces(0, b0, px, b1, hb)):
            out.append(dict(x0=a0, y0=c0, x1=a1, y1=c1, z=z, t=T, holes=hh, name=f"{name}{k}{q}", pitch=(pp, pp)))
    return out


def _stripline(h_dn, h_up, w=0.3, L=14.0, slot_up=None, slot_dn=None, px=24.0, py=14.0):
    """A trace between two planes h_dn below and h_up above it, both planes tied together by rows of
    shorts at the feed and at the far end; the trace is shorted to the lower plane at its far end."""
    yc, x0 = py / 2, 5.0
    zt = T + h_dn
    zu = zt + T + h_up
    planes = _banded("dn", 0.0, px, py, yc, [slot_dn] if slot_dn else []) + \
        _banded("up", zu, px, py, yc, [slot_up] if slot_up else [])
    ties = [dict(a=(x, y, T / 2), b=(x, y, zu + T / 2)) for x in (x0 - 2.0, x0 + L + 2.0)
            for y in np.linspace(2.0, py - 2.0, 7)]
    return dict(sigma=5.8e7, freqs=[F], plane_nhinc=3,
                rects=[dict(x0=x0, y0=yc - w / 2, x1=x0 + L, y1=yc + w / 2, z=zt, t=T, name="tr")],
                planes=planes,
                ports=[dict(p=(x0, yc, zt + T / 2), n=(x0, yc, T / 2), name="P")],
                shorts=[dict(a=(x0 + L, yc, zt + T / 2), b=(x0 + L, yc, T / 2))] + ties)


def _layer_change(D, w=0.3, px=24.0, py=None):
    """4 layers: a trace on L1 over plane A (L2) runs to a via at x = 12 and continues on L4 under
    plane B (L3); A and B are joined only by one capacitor (an ideal short) D mm from the via. The
    return has to change planes there."""
    py = py or max(20.0, 2 * D + 6.0)             # the capacitor at yc + D stays on the board
    yc, x0, xv, x1 = py / 2, 4.0, 12.0, 20.0
    h = 0.2
    z4, z3 = 0.0, T + h            # L4 trace, L3 plane B
    z2 = z3 + T + 0.6              # L2 plane A (core 0.6 between the planes)
    z1 = z2 + T + h                # L1 trace
    hole = (xv - 0.5, yc - 0.5, xv + 0.5, yc + 0.5)
    half = min(max(2.5, D + 1.0), 6.0)            # the fine band reaches the capacitor (FastHenry memory bound)
    planes = _banded("A", z2, px, py, yc, [hole], half=half) + _banded("B", z3, px, py, yc, [hole], half=half)
    return dict(sigma=5.8e7, freqs=[F], plane_nhinc=3,
                rects=[dict(x0=x0, y0=yc - w / 2, x1=xv + 0.2, y1=yc + w / 2, z=z1, t=T, name="t1"),
                       dict(x0=xv - 0.2, y0=yc - w / 2, x1=x1, y1=yc + w / 2, z=z4, t=T, name="t4")],
                planes=planes,
                vias=[dict(x=xv, y=yc, z0=z1 + T / 2, z1=z4 + T / 2, d=0.3)],
                ports=[dict(p=(x0, yc, z1 + T / 2), n=(x0, yc, z2 + T / 2), name="P")],
                shorts=[dict(a=(x1, yc, z4 + T / 2), b=(x1, yc, z3 + T / 2)),          # far end to plane B
                        dict(a=(xv, yc + D, z2 + T / 2), b=(xv, yc + D, z3 + T / 2))])  # the capacitor A-B


def cases():
    out = {}
    out["strip_sym"] = _stripline(0.2, 0.2)
    out["strip_asym"] = _stripline(0.1, 0.3)
    out["strip_slot_up"] = _stripline(0.2, 0.2, slot_up=(11.5, 3.0, 12.5, 11.0))
    out["strip_slot_dn"] = _stripline(0.2, 0.2, slot_dn=(11.5, 3.0, 12.5, 11.0))
    for D in (1, 5, 15):
        out[f"layerchange_{D}"] = _layer_change(float(D))
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
    v["planes"][0]["pitch"] = (0.2, 0.2)
    v["plane_nhinc"] = 3
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
