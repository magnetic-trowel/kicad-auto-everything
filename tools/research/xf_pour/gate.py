# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validation gate for the pour-damage maps (venv Python, env from xf_common/env.sh).

    python gate.py OUT.json [--cuts 40] [--state human|routed] BOARD_ID [...]

For each board: the human placement (reference board), optionally routed by the pnr
router (so foreign tracks cut the pours), PourMaps.refresh(), then for every pour
(net, layer) `--cuts` random cut-outs, each a real part's foreign-pad halo (the mask the
placement term uses) at a random free spot of the pour. Predicted relative R_eff increase
= sum of the map under the cut; exact = re-solve of the same coarse sheet with the cut
removed. Reports Spearman per pour and pooled per board, and the exact/predicted ratios.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PNR = ROOT / "tools" / "research" / "pnr"
sys.path.insert(0, str(PNR))
sys.path.insert(0, str(HERE))

from pourmap import PourMaps  # noqa: E402


def load_world(bid, work):
    from world import World
    inp = ROOT / "kae-work" / "tasks" / bid / "reference" / "board.kicad_pcb"
    ext = Path(work) / f"{bid}.extract.json"
    if not ext.exists():
        kpy = os.environ.get("KAE_KICAD_PYTHON", "/usr/bin/python3")
        r = subprocess.run([kpy, str(PNR / "kicad_io.py"), "extract", str(inp), str(ext)],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-2000:])
    return World(json.loads(ext.read_text()), g=0.1)


def part_cut(w, pi, ri, n, l):
    rr = w.part_raster(w.parts[pi], ri)
    cs = [e["hT"] for e in rr["pads"] if e["net"] != n and l in e["layers_halo"] and len(e["hT"])]
    return np.unique(np.concatenate(cs), axis=0) if cs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--cuts", type=int, default=40)
    ap.add_argument("--state", default="routed", choices=["human", "routed"])
    ap.add_argument("--coarse", type=float, default=0.4)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    work = ROOT / "kae-work" / "xf_pour"
    work.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    res = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else {}
    for bid in a.boards:
        w = load_world(bid, work)
        for pi in range(len(w.parts)):
            w.place_original(pi)
        if a.state == "routed":
            from router import Router
            r = Router(w)
            r.pathfinder(iters=8)
        pm = PourMaps(w, coarse_mm=a.coarse)
        t0 = time.process_time()
        pm.refresh()
        t_ref = time.process_time() - t0
        print(bid, "pours", [(w.net_names[n], l, pm.info[(n, l)]) for n, l in pm.pours], f"refresh {t_ref:.2f}s",
              flush=True)
        rows = []
        cand = [p.idx for p in w.parts if any(pd["net"] for pd in p.pads) or p.pads]
        for (n, l) in pm.pours:
            if (n, l) not in pm.E:
                continue
            base, fr0, term = pm.solve(n, l)
            wl = pm.info[(n, l)]["weight"]
            E = pm.E[(n, l)]
            ys, xs = np.nonzero(fr0)
            if len(ys) == 0:
                continue
            k = tries = 0
            while k < a.cuts and tries < a.cuts * 20:
                tries += 1
                pi = int(rng.choice(cand))
                ri = int(rng.integers(4))
                cells = part_cut(w, pi, ri, n, l)
                if cells is None:
                    continue
                j = int(rng.integers(len(ys)))
                cx = xs[j] - int(round(cells[:, 0].mean()))
                cy = ys[j] - int(round(cells[:, 1].mean()))
                X, Y = cells[:, 0] + cx, cells[:, 1] + cy
                ok = (X >= 0) & (Y >= 0) & (X < w.W) & (Y < w.H)
                cut = np.zeros((w.H, w.W), bool)
                cut[Y[ok], X[ok]] = True
                hit = cut & fr0
                if hit.sum() < 3:
                    continue
                pred = float(E[hit].sum())
                ex, _, _ = pm.solve(n, l, extra_cut=cut, term=term)
                if ex["R_eff"] is None:
                    exact = np.inf
                else:
                    exact = wl * (ex["R_eff"] / base["R_eff"] - 1.0)
                rows.append(dict(net=w.net_names[n], layer=l, part=w.parts[pi].ref, cells=int(hit.sum()),
                                 pred=pred, exact=exact,
                                 disc=int((np.isfinite(ex["R"]) == False).sum() - (np.isfinite(base["R"]) == False).sum())))  # noqa: E712
                k += 1
        out = dict(refresh_s=t_ref, pours={f"{w.net_names[n]}|{l}": pm.info[(n, l)] for n, l in pm.pours},
                   rows=rows)
        per = {}
        for key in {(r["net"], r["layer"]) for r in rows}:
            rr = [r for r in rows if (r["net"], r["layer"]) == key]
            p = np.array([r["pred"] for r in rr]); e = np.array([r["exact"] for r in rr])
            e = np.where(np.isfinite(e), e, 1e9)
            if len(rr) >= 5:
                per[f"{key[0]}|{key[1]}"] = dict(n=len(rr), rho=float(spearmanr(p, e)[0]),
                                                 ratio=_ratios(p, e))
        p = np.array([r["pred"] for r in rows]); e = np.array([r["exact"] for r in rows])
        e = np.where(np.isfinite(e), e, 1e9)
        out["per_pour"] = per
        out["pooled"] = dict(n=len(rows), rho=float(spearmanr(p, e)[0]) if len(rows) >= 5 else None,
                             ratio=_ratios(p, e))
        print(bid, json.dumps(dict(per_pour=per, pooled=out["pooled"])), flush=True)
        res[f"{bid}|{a.state}|{a.coarse}"] = out
        Path(a.out).write_text(json.dumps(res, indent=1, default=float))


def _ratios(p, e):
    ok = (p > 1e-9) & (e < 1e8) & (e > 0)
    if not ok.any():
        return None
    q = e[ok] / p[ok]
    return dict(min=float(q.min()), median=float(np.median(q)), max=float(q.max()),
                n_disconnect=int((e >= 1e8).sum()))


if __name__ == "__main__":
    main()
