# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics place terms in the loop: kae.physics (branch claude/vigilant-mayer-i91rrr).

    ph = Phys(world, input_board)        # brief built from the input netlist (no positions)
    ph.sync()                            # poses of all placed parts -> kae poses
    ph.delta(pi, (cx, cy, ri))           # change of the place-terms total if pi moves there
    ph.commit(pi)                        # after world.place(...) of an accepted move
    ph.total(), ph.coarse_map(pi, ri, kit)

kae is found through KAE_SRC (path to kae/src of that branch). Terms are φ(u) per
structure (decap loop nH, hot-loop nH, aggressor-victim mV, crystal ppm, thermal K, cable
common-mode / ESD); the same brief and terms are used by tools/research/pnr_phys to score.
"""
import json
import os
import sys

import numpy as np

from world import ROTS

KAE_SRC = os.environ.get(
    "KAE_SRC", "/tmp/claude-0/-home-user-kicad-auto-everything/1f01ab67-8a71-51cc-ad90-95d7df3bea54/"
               "scratchpad/kae-phys/kae/src")


class Phys:
    def __init__(self, world, board_path):
        if KAE_SRC not in sys.path:
            sys.path.insert(0, KAE_SRC)
        from kae.board.kicad_file import load
        from kae.circuit.brief import build
        from kae.physics.place_terms import Terms
        self.w = world
        board = load(board_path)
        brief = json.loads(json.dumps(build(board), default=str))
        self.T = Terms(board, brief)
        self.uuids = {fp.uuid for fp in board.footprints}
        self.poses = {fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in board.footprints}
        # world part -> kae uuid (uuid, else a unique reference designator)
        by_ref = {}
        for fp in board.footprints:
            by_ref.setdefault(fp.ref, []).append(fp.uuid)
        self.key = {}
        for p in world.parts:
            if p.uuid in self.uuids and list(by_ref.get(p.ref, [])).count(p.uuid) <= 1:
                self.key[p.idx] = p.uuid
            elif len(by_ref.get(p.ref, [])) == 1:
                self.key[p.idx] = by_ref[p.ref][0]
        tp = set(self.T.parts())
        self.active = {pi for pi, u in self.key.items() if u in tp}  # parts any term touches

    def pose(self, pi, pose):
        cx, cy, ri = pose
        p = self.w.parts[pi]
        x, y = self.w.xy(cx, cy)
        fx, fy = self.w.frac.get(pi, (0.0, 0.0)) if self.w.pose.get(pi) == pose else (0.0, 0.0)
        rot = ROTS[ri] if ri < 4 else p.rot0
        return (x + fx, y + fy, rot, "B" if p.side else "F")

    def sync(self):
        for pi, pose in self.w.pose.items():
            if pi in self.key:
                self.poses[self.key[pi]] = self.pose(pi, pose)

    def commit(self, pi):
        if pi in self.key and pi in self.w.pose:
            self.poses[self.key[pi]] = self.pose(pi, self.w.pose[pi])

    def total(self):
        return float(self.T.total(self.poses))

    def delta(self, pi, pose):
        if pi not in self.active:
            return 0.0
        u = self.key[pi]
        return float(self.T.delta(self.poses, [u], {u: self.pose(pi, pose)}))

    def delta_many(self, moves):
        """moves: {pi: pose} applied together."""
        moves = {pi: p for pi, p in moves.items() if pi in self.active}
        if not moves:
            return 0.0
        new = {self.key[pi]: self.pose(pi, p) for pi, p in moves.items()}
        return float(self.T.delta(self.poses, list(new), new))

    def coarse_map(self, pi, ri, step_mm=0.8, legal=None):
        """Physics delta of moving pi to every origin cell at orientation ri, sampled every
        step_mm (legal cells only when `legal` is given) and spread to the full grid by
        nearest sample. Zero map for parts no term touches."""
        w = self.w
        out = np.zeros((w.H, w.W))
        if pi not in self.active:
            return out
        s = max(1, int(round(step_mm / w.g)))
        ys = np.arange(s // 2, w.H, s)
        xs = np.arange(s // 2, w.W, s)
        vals = np.full((len(ys), len(xs)), np.nan)
        for a, y in enumerate(ys):
            for b, x in enumerate(xs):
                if legal is not None and not legal[max(0, y - s // 2):y + s // 2 + 1,
                                                   max(0, x - s // 2):x + s // 2 + 1].any():
                    continue
                vals[a, b] = self.delta(pi, (int(x), int(y), ri))
        if np.all(np.isnan(vals)):
            return out
        vals = np.where(np.isnan(vals), np.nanmax(vals), vals)
        iy = np.minimum(np.arange(w.H) // s, len(ys) - 1)
        ix = np.minimum(np.arange(w.W) // s, len(xs) - 1)
        return vals[iy][:, ix]
