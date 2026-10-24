# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Is the harmonic expected occupancy a better congestion map than RUDY?

On each human-placed route task: fields of every net with only pads as walls (before any
routing) give sum_n |J_n| / I_n per coarse cell; RUDY gives sum_n (w + h) / (w h) over each
net's pin bounding box. Both are compared (Spearman over coarse cells inside the board) with
the copper the engine's PathFinder actually lays (route cells per coarse cell, all layers).

    python congestion.py BOARD_ID ... [--json out.json]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import methods as M  # noqa: E402
from common import load_world  # noqa: E402
from field import Field, block_mean  # noqa: E402


def run(board, coarse=0.4):
    w = load_world(board)
    for pi in range(len(w.parts)):
        w.place_original(pi)
    F = Field(w, coarse_mm=coarse)
    harm = np.zeros((F.Hc, F.Wc))
    rudy = np.zeros((F.Hc, F.Wc))
    for n in w.net_pins:
        sig = F.sigma(n)
        phi, pins, src = F.solve(n, sig)
        if phi is None:
            continue
        harm += F.density(phi, sig).reshape(F.L, F.Hc, F.Wc).sum(0)
        ys = np.concatenate([(p % (F.Hc * F.Wc)) // F.Wc for p in pins])
        xs = np.concatenate([p % F.Wc for p in pins])
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        hh, ww = y1 - y0, x1 - x0
        rudy[y0:y1, x0:x1] += (hh + ww) / (hh * ww)
    r = M._router(w, {})
    r.pathfinder(iters=40)
    act = np.zeros((F.L, w.H, w.W), np.float32)
    for n, ps in r.routes.items():
        for p in ps:
            act[p[:, 0], p[:, 1], p[:, 2]] = 1
    actc = block_mean(act, F.s, F.Hc, F.Wc).sum(0)
    inside = block_mean(w.inside[None].astype(np.float32), F.s, F.Hc, F.Wc)[0] > 0.5
    a, h, ru = actc[inside], harm[inside], rudy[inside]
    out = dict(board=board, cells=int(inside.sum()), rho_harm=float(spearmanr(h, a)[0]),
               rho_rudy=float(spearmanr(ru, a)[0]))
    # top-decile overlap: share of the 10 % most-used cells found in each map's top 10 %
    k = max(1, len(a) // 10)
    top = set(np.argsort(-a)[:k])
    out["top_harm"] = len(top & set(np.argsort(-h)[:k])) / k
    out["top_rudy"] = len(top & set(np.argsort(-ru)[:k])) / k
    print(json.dumps(out), flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = [run(b) for b in a.boards]
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
