# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnostic: can harmonic streamlines route without search?

On the human placement of a route task, nets are taken one by one (random order); each
net's field is solved with committed copper of earlier nets and foreign pads as walls
(beta = inf), its streamline tree is rasterized to the 0.1 mm grid, and checked against the
engine's halo clearance (router.conflicts). Legal streamline trees are committed; otherwise
the engine A* routes the net. Also: A* on the same state for the length ratio.

    python diag.py BOARD_ID [BOARD_ID ...] [--coarse 0.4] [--json out.json]
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_world  # noqa: E402
from field import Field  # noqa: E402
from stream import tree_to_fine  # noqa: E402

import methods as M  # noqa: E402
from router import conflicts  # noqa: E402


def path_len(paths, g):
    t = 0.0
    for p in paths:
        d = np.abs(np.diff(p, axis=0))
        same = d[:, 0] == 0
        t += float(np.sum(np.where((d[same, 1] + d[same, 2]) == 2, np.sqrt(2), 1.0))) * g
        t += 2.0 * int((~same).sum())
    return t


def run(board, coarse, seed=0, log=print):
    w = load_world(board, kind="route")
    for pi in range(len(w.parts)):
        w.place_original(pi)
    r = M._router(w, {})
    F = Field(w, coarse_mm=coarse)
    nets = list(w.net_pins)
    random.Random(seed).shuffle(nets)
    st = dict(board=board, nets=len(nets), conns=0, reached=0, legal_conn=0, legal_net=0,
              len_stream=0.0, len_astar=0.0, t_solve=0.0, t_astar=0.0, cells=F.n)
    for n in nets:
        t0 = time.process_time()
        sig = F.sigma(n)
        phi, pins, src = F.solve(n, sig, use_cg=False)
        st["t_solve"] += time.process_time() - t0
        if phi is None:
            continue
        tree = F.streamlines(phi, sig, pins, src)
        fine = tree_to_fine(w, F, n, tree, pins, src)
        st["conns"] += len(pins) - 1
        st["reached"] += sum(t is not None for t in tree)
        conf = [conflicts(p, n, w.DT, w.occT, w.DV, w.occV, w.nl) if p is not None else -1 for p in fine]
        st["legal_conn"] += sum(c == 0 for c in conf)
        # A* reference on the same state
        t1 = time.process_time()
        r.route_net(n, hard=True)
        st["t_astar"] += time.process_time() - t1
        astar_paths = r.routes.get(n, [])
        a_ok = not r.unrouted.get(n)
        if all(c == 0 for c in conf) and fine:
            st["legal_net"] += 1
            if a_ok:
                st["len_stream"] += path_len([p for p in fine if p is not None], w.g)
                st["len_astar"] += path_len(astar_paths, w.g)
            r.rip(n)
            r.routes[n] = [p for p in fine if p is not None]
            for p in r.routes[n]:
                r._stamp(n, p, 1)
        # else keep the A* route committed (hard mode: legal or unrouted)
    stt = r.stats()
    st.update({k: round(v, 3) if isinstance(v, float) else v for k, v in st.items()})
    st["final"] = stt
    log(json.dumps(st))
    return st


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--coarse", type=float, default=0.4)
    ap.add_argument("--json")
    a = ap.parse_args()
    out = [run(b, a.coarse) for b in a.boards]
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1))
