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

Round 2 checks two models on the same cut-outs: u = one sheet per layer (round 1), c =
the net's pour layers coupled through its plated pads and routed vias (PourMaps
coupled=True). "u_vs_c" ranks the per-layer prediction against the coupled exact change,
i.e. whether the coupling matters.
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

XF_WORK = Path(os.environ.get("XF_WORK", ROOT / "kae-work2"))


def load_world(bid, work):
    from world import World
    inp = XF_WORK / "tasks" / bid / "reference" / "board.kicad_pcb"
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
    work = XF_WORK / "xf_pour"
    work.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    res = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else {}
    for bid in a.boards:
        w = load_world(bid, work)
        for pi in range(len(w.parts)):
            w.place_original(pi)
        r = None
        if a.state == "routed":
            from router import Router, vias_of
            r = Router(w)
            r.pathfinder(iters=8)

        def vias(n):
            if r is None:
                return np.zeros((0, 2), np.int64)
            v = [vias_of(p)[:, 1:] for p in r.routes.get(n, [])]
            return np.concatenate(v) if v else np.zeros((0, 2), np.int64)

        pmu = PourMaps(w, coarse_mm=a.coarse)
        pmc = PourMaps(w, coarse_mm=a.coarse, coupled=True, vias=vias)
        t0 = time.process_time()
        pmu.refresh()
        t_u = time.process_time() - t0
        t0 = time.process_time()
        pmc.refresh()
        t_c = time.process_time() - t0
        print(bid, "pours", [(w.net_names[n], l, pmu.info[(n, l)], pmc.info[(n, l)]) for n, l in pmu.pours],
              f"refresh {t_u:.2f}s / coupled {t_c:.2f}s", flush=True)
        rows = []
        cand = [p.idx for p in w.parts if p.pads]
        cbase = {}
        for (n, l) in pmu.pours:
            if (n, l) not in pmu.E and (n, l) not in pmc.E:
                continue
            if n not in cbase:
                cbase[n] = pmc.solve_net(n)
            rc0, frc, termc = cbase[n]
            ub, fr0, term = pmu.solve(n, l)
            wl = pmu.info[(n, l)]["weight"]
            Eu = pmu.E.get((n, l))
            Ec = pmc.E.get((n, l))
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
                row = dict(net=w.net_names[n], layer=l, part=w.parts[pi].ref, cells=int(hit.sum()))
                row["pred_u"] = float(Eu[hit].sum()) if Eu is not None else None
                row["pred_c"] = float(Ec[hit].sum()) if Ec is not None else None
                if ub["R_eff"] is not None:
                    ex, _, _ = pmu.solve(n, l, extra_cut=cut, term=term)
                    row["exact_u"] = np.inf if ex["R_eff"] is None else wl * (ex["R_eff"] / ub["R_eff"] - 1.0)
                if rc0["R_eff"] is not None:
                    ex, _, _ = pmc.solve_net(n, extra_cut=cut, cut_layer=l, term=termc)
                    row["exact_c"] = np.inf if ex["R_eff"] is None else ex["R_eff"] / rc0["R_eff"] - 1.0
                rows.append(row)
                k += 1
        out = dict(refresh_s=t_u, refresh_coupled_s=t_c,
                   pours={f"{w.net_names[n]}|{l}": dict(u=pmu.info[(n, l)], c=pmc.info[(n, l)])
                          for n, l in pmu.pours}, rows=rows)
        pairs = dict(u=("pred_u", "exact_u"), c=("pred_c", "exact_c"), u_vs_c=("pred_u", "exact_c"))
        per = {}
        for key in sorted({(r["net"], r["layer"]) for r in rows}):
            rr = [r for r in rows if (r["net"], r["layer"]) == key]
            per[f"{key[0]}|{key[1]}"] = {nm: _stat(rr, *pp) for nm, pp in pairs.items()}
        out["per_pour"] = per
        out["pooled"] = {nm: _stat(rows, *pp) for nm, pp in pairs.items()}
        print(bid, json.dumps(dict(per_pour=per, pooled=out["pooled"])), flush=True)
        res[f"{bid}|{a.state}|{a.coarse}"] = out
        Path(a.out).write_text(json.dumps(res, indent=1, default=float))


def _stat(rows, kp, ke):
    rr = [r for r in rows if r.get(kp) is not None and r.get(ke) is not None]
    if len(rr) < 5:
        return None
    p = np.array([r[kp] for r in rr]); e = np.array([r[ke] for r in rr], float)
    e = np.where(np.isfinite(e), e, 1e9)
    return dict(n=len(rr), rho=float(spearmanr(p, e)[0]), ratio=_ratios(p, e))


def _ratios(p, e):
    ok = (p > 1e-9) & (e < 1e8) & (e > 0)
    if not ok.any():
        return None
    q = e[ok] / p[ok]
    return dict(min=float(q.min()), median=float(np.median(q)), max=float(q.max()),
                n_disconnect=int((e >= 1e8).sum()))


if __name__ == "__main__":
    main()
