# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""LLM-as-move-proposer loop (joint-pnr catalog idea 30) on the shared pnr grid engine.

The proposer (an LLM/VLM; in this lab, the agent itself) sees only a rendered PNG and a
text summary of the routed board. It emits a batch of relational moves as JSON; this
tool resolves each move to the nearest legal pose, re-routes with the engine and keeps
the batch only if the board got better (unrouted connections first, then Kit.total_cost).

    python llmloop.py init ID                  # seq placement + route -> round 0
    python llmloop.py step ID moves.json       # apply a batch -> next round (render + summary)
    python llmloop.py show ID [--round N]      # re-render a round
    python llmloop.py finalize ID [--round N] [--name final]   # write NAME.kicad_pcb
    python llmloop.py control ID --rounds 8 --moves 4 [--seed 0]  # random proposer, same verifier

Move language (one JSON object per move, optional "why" and "rot" on every move):
    {"move": "C4", "near": "U1", "side": "left|right|above|below|any", "dist": "tight|close|loose"}
    {"move": "C4", "near": "U1.7"}                 # next to pad 7 of U1
    {"move": "R1", "dir": "left|right|up|down", "dist": "tight|close|loose"}
    {"move": "R1", "between": ["U1", "J1"]}
    {"move": "J1", "to_edge": "top|bottom|left|right"}
    {"rotate": "U2", "by": 90}                     # degrees, KiCad sense (CCW)
    {"swap": ["R1", "R3"]}                         # each keeps or takes the other's rotation
A move whose nearest legal pose is > 3 mm from its target is refused ("far_ok": true overrides).
"push": true on a move: smaller movable parts in the way are lifted and re-placed nearest their
old spot ("push": "all" also pushes bigger parts).
"rot": 0/90/180/270 or "any" (resolver picks the orientation with the shortest wiring).
The moves file is {"note": ..., "moves": [...], "plateau": false}; plateau=true keeps the batch
when it adds no illegal part and no unrouted connection even if the cost rises (a sideways step).
Work files go to kae-work/pnr_llm/ID/ (git-ignored).
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path("/home/user/kicad-auto-everything")
PNR = ROOT / "tools/research/pnr"
sys.path.insert(0, str(PNR))

import methods  # noqa: E402
from placekit import Kit, corr  # noqa: E402
from router import Router  # noqa: E402
from world import ROTS, World, rot_pts  # noqa: E402

WORK = ROOT / "kae-work/pnr_llm"
KICAD_PY = os.environ.get("KAE_KICAD_PYTHON", "/usr/bin/python3")
GAP = {"tight": 0.3, "close": 1.0, "loose": 2.5}
STEP = {"tight": 1.0, "close": 2.5, "loose": 5.0}
SIDE = {"left": "left", "right": "right", "above": "above", "top": "above", "up": "above",
        "below": "below", "bottom": "below", "down": "below", "any": "any"}
LAYER_COL = ["#d62728", "#1f5fd6", "#2ca02c", "#9467bd", "#8c564b", "#e377c2"]


def kicad(*args):
    r = subprocess.run([KICAD_PY, str(PNR / "kicad_io.py"), *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def task_board(bid):
    return ROOT / f"kae-work/tasks/{bid}/place/input/board.kicad_pcb"


class Session:
    def __init__(self, bid, grid=0.1):
        self.bid = bid
        self.dir = WORK / bid
        self.dir.mkdir(parents=True, exist_ok=True)
        ext = self.dir / "extract.json"
        if not ext.exists():
            kicad("extract", task_board(bid), ext)
        self.data = json.loads(ext.read_text())
        self.world = World(self.data, g=grid)
        w = self.world
        self.names = {}
        seen = {}
        for p in w.parts:
            nm = p.ref or f"#{p.idx}"
            if nm in seen:
                seen[nm] += 1
                nm = f"{nm}~{seen[nm]}"
            else:
                seen[nm] = 0
            self.names[p.idx] = nm
        self.idx = {v: k for k, v in self.names.items()}
        self.r = None
        self.kit = None
        self.max_miss = 3.0
        self._pad_ok = {}
        self._aper = {}

    # ------------------------------------------------------------ state
    def init_seq(self, budget=120, seed=0, log=None):
        self.r = methods.seq(self.world, seed=seed, budget=budget, log=log or (lambda m: None))
        self.kit = Kit(self.world, self.r)

    def load(self, f):
        st = json.loads(Path(f).read_text())
        w = self.world
        methods._place_fixed(w)
        for pi, (cx, cy, ri) in st["poses"].items():
            w.place(int(pi), cx, cy, ri)
        w.mech = set(st.get("mech", []))
        self.r = Router(w)
        self.kit = Kit(w, self.r)
        for n, paths in st["routes"].items():
            ps = [np.array(p, np.int32).reshape(-1, 3) for p in paths]
            self.r.routes[int(n)] = ps
            for p in ps:
                self.r._stamp(int(n), p, 1)
        self.r.unrouted = {int(n): k for n, k in st["unrouted_nets"].items() if k}
        return st

    def save(self, f, extra=None):
        w = self.world
        st = dict(poses={str(pi): list(map(int, v)) for pi, v in w.pose.items() if pi not in w.fixed},
                  mech=sorted(getattr(w, "mech", set())),
                  routes={str(n): [p.tolist() for p in ps] for n, ps in self.r.routes.items()},
                  unrouted_nets={str(n): int(k) for n, k in self.r.unrouted.items() if k})
        st.update(self.metrics())
        st["illegal"] = self.outside_pads()
        if extra:
            st.update(extra)
        Path(f).write_text(json.dumps(st))

    def metrics(self):
        s = self.r.stats()
        return dict(unrouted=int(s["unrouted"]), length_mm=s["length_mm"], vias=s["vias"],
                    cost=round(self.kit.total_cost(), 2), connections=s["connections"])

    def key(self):
        """Lexicographic: illegal parts (pad outside board / in a cut-out), unrouted, cost."""
        return (len(self.outside_pads()), sum(self.r.unrouted.values()), self.kit.total_cost())

    def movable(self):
        w = self.world
        return [p.idx for p in w.parts if not p.locked and p.idx not in w.fixed and p.idx in w.pose]

    def full_snapshot(self):
        w = self.world
        return (dict((q, w.pose[q]) for q in self.movable()), self.kit.snapshot(list(w.net_pins)), w.hist.copy())

    def full_restore(self, snap):
        poses, routes, hist = snap
        w = self.world
        for q in list(w.pose):
            if q in poses:
                w.unplace(q)
        for q, p in poses.items():
            w.place(q, *p)
        self.kit.restore(routes)
        w.hist[:] = hist

    # ------------------------------------------------------------ geometry helpers
    def bbox_mm(self, pi, pose=None):
        w = self.world
        cx, cy, ri = pose or w.pose[pi]
        b = w.part_raster(w.parts[pi], ri, w.frac.get(pi, (0.0, 0.0)) if pose is None else (0.0, 0.0))["bbox"]
        x, y = w.xy(cx, cy)
        return x + b[0] * w.g, y + b[1] * w.g, x + b[2] * w.g, y + b[3] * w.g

    def center_mm(self, pi):
        x0, y0, x1, y1 = self.bbox_mm(pi)
        return (x0 + x1) / 2, (y0 + y1) / 2

    def half_ext(self, pi, ri):
        b = self.world.part_raster(self.world.parts[pi], ri)["bbox"]
        g = self.world.g
        return (b[2] - b[0]) * g / 2, (b[3] - b[1]) * g / 2, ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

    def aperture_mask(self, exclude=None):
        """Cells enclosed by footprint Edge.Cuts strokes (e.g. a sensor's lens cut-out):
        board holes the engine's stroke raster does not fill."""
        from scipy.ndimage import binary_fill_holes
        from raster import raster_poly
        w = self.world
        keyp = tuple((q, w.pose[q]) for q in sorted(w.pose) if w.parts[q].data.get("edges") and q != exclude)
        if keyp in self._aper:
            return self._aper[keyp]
        m = np.zeros((w.H, w.W), bool)
        for q, (cx, cy, ri) in keyp:
            p = w.parts[q]
            deg = ROTS[ri] if ri < 4 else p.rot0
            fx, fy = w.frac.get(q, (0.0, 0.0))
            strokes = np.zeros((w.H, w.W), bool)
            for e in p.data["edges"]:
                if len(e) < 3:
                    continue
                c = raster_poly(rot_pts(np.array(e, float), deg), 0.0, -fx, -fy, w.g)
                xs, ys = c[:, 0] + cx, c[:, 1] + cy
                ok = (xs >= 0) & (ys >= 0) & (xs < w.W) & (ys < w.H)
                strokes[ys[ok], xs[ok]] = True
            m |= binary_fill_holes(strokes) & ~strokes
        self._aper[keyp] = m
        return m

    def pad_ok_map(self, pi, ri):
        """Origins where every pad centre of part pi lies inside the board (scorer's 'inside'),
        counting footprint cut-outs of other parts as outside."""
        ap = self.aperture_mask(exclude=pi)
        key = (pi, ri, id(ap))
        if key not in self._pad_ok:
            w = self.world
            r = w.part_raster(w.parts[pi], ri)
            offs = np.array([np.round(e["center"] / w.g) for e in r["pads"]], np.int64).reshape(-1, 2)
            if len(offs) == 0:
                self._pad_ok[key] = np.ones((w.H, w.W), bool)
            else:
                offs = np.unique(offs, axis=0)
                self._pad_ok[key] = corr(~w.inside | ap, offs) < 0.5
        return self._pad_ok[key]

    def pad_pos(self, ref_pad):
        ref, num = ref_pad.rsplit(".", 1)
        pi = self.idx[ref]
        for k, pad in enumerate(self.world.parts[pi].pads):
            if str(pad.get("num", pad.get("name", ""))) == num:
                return self.world.pad_world(pi, k)
        raise KeyError(f"pad {ref_pad} not found")

    # ------------------------------------------------------------ move resolution
    def _resolve(self, pi, targets, band=0.5, weights=(1.0, 1.0)):
        """targets: {ri: (tx, ty)} part-centre targets (mm). Part must be unplaced.
        Picks the legal origin nearest its target (weighted dx, dy); among poses within
        `band` mm of the best distance, the one with the lowest HPWL. Returns pose, miss."""
        w, kit = self.world, self.kit
        g = w.g
        cands = []
        for ri, (tx, ty) in targets.items():
            L = kit.legal_map(pi, ri) & self.pad_ok_map(pi, ri)
            if not L.any():
                continue
            _, _, (ox, oy) = self.half_ext(pi, ri)
            yy, xx = np.nonzero(L)
            px = w.x0 + (xx + ox) * g
            py = w.y0 + (yy + oy) * g
            d = np.hypot(weights[0] * (px - tx), weights[1] * (py - ty))
            j = np.argsort(d)[:4000]
            hp = kit.hpwl_map(pi, ri)
            for k in j:
                cands.append((float(d[k]), float(hp[yy[k], xx[k]]), int(xx[k]), int(yy[k]), ri))
        if not cands:
            return None, None
        dmin = min(c[0] for c in cands)
        near = [c for c in cands if c[0] <= dmin + band]
        best = min(near, key=lambda c: c[1])
        return (best[2], best[3], best[4]), best[0]

    def _rots(self, mv, pi):
        r = mv.get("rot")
        if r is None:
            return [self.world.pose[pi][2]]
        if r == "any":
            return [0, 1, 2, 3]
        return [self.world.rot_index(float(r))]

    def apply_move(self, mv):
        """Apply one move to the placement (no routing). Returns a record."""
        w = self.world
        rec = dict(move=mv)
        try:
            if "swap" in mv:
                a, b = (self.idx[x] for x in mv["swap"])
                for q in (a, b):
                    self._check_movable(q)
                pa, pb = w.pose[a], w.pose[b]
                ca, cb = self.center_mm(a), self.center_mm(b)
                w.unplace(a)
                w.unplace(b)
                ra = [pa[2], pb[2]] if mv.get("rot") != "any" else [0, 1, 2, 3]
                rb = [pb[2], pa[2]] if mv.get("rot") != "any" else [0, 1, 2, 3]
                posa, missa = self._resolve(a, {q: cb for q in ra}, band=0.3)
                if posa is None or missa > self.max_miss:
                    w.place(a, *pa), w.place(b, *pb)
                    return dict(rec, ok=False, err="no room for the swap")
                w.place(a, *posa)
                posb, missb = self._resolve(b, {q: ca for q in rb}, band=0.3)
                if posb is None or missb > self.max_miss:
                    w.unplace(a)
                    w.place(a, *pa), w.place(b, *pb)
                    return dict(rec, ok=False, err="no room for the swap")
                w.place(b, *posb)
                return dict(rec, ok=True, parts=[a, b], miss_mm=round(max(missa, missb), 2))
            if "rotate" in mv:
                pi = self.idx[mv["rotate"]]
                self._check_movable(pi)
                old = w.pose[pi]
                c = self.center_mm(pi)
                ri = (old[2] + int(round(float(mv.get("by", 90)) / 90))) % 4
                w.unplace(pi)
                pos, miss = self._resolve(pi, {ri: c}, band=0.3)
                return self._finish(pi, old, pos, miss, rec)
            pi = self.idx[mv["move"]]
            self._check_movable(pi)
            old = w.pose[pi]
            c = self.center_mm(pi)
            rots = self._rots(mv, pi)
            weights = (1.0, 1.0)
            band = 0.5
            if "near" in mv:
                side = SIDE[mv.get("side", "any")]
                gap = GAP[mv.get("dist", "close")]
                anchor = mv["near"]
                if "." in anchor and anchor not in self.idx:
                    # pad anchor: sit beside the owning part's courtyard, level with the pad
                    ax, ay = self.pad_pos(anchor)
                    ob = self.bbox_mm(self.idx[anchor.rsplit(".", 1)[0]])
                    abox = (ob[0], ay, ob[2], ay) if side in ("left", "right") else (ax, ob[1], ax, ob[3])
                    if side == "any":
                        abox = (ax, ay, ax, ay)
                else:
                    q = self.idx[anchor]
                    abox = self.bbox_mm(q)
                w.unplace(pi)
                targets = {}
                for ri in rots:
                    hw, hh, _ = self.half_ext(pi, ri)
                    acx, acy = (abox[0] + abox[2]) / 2, (abox[1] + abox[3]) / 2
                    targets[ri] = {"left": (abox[0] - gap - hw, acy), "right": (abox[2] + gap + hw, acy),
                                   "above": (acx, abox[1] - gap - hh), "below": (acx, abox[3] + gap + hh),
                                   "any": (acx, acy)}[side]
                band = {"tight": 0.3, "close": 0.6, "loose": 1.2}[mv.get("dist", "close")]
            elif "dir" in mv:
                s = STEP[mv.get("dist", "close")]
                dx, dy = {"left": (-s, 0), "right": (s, 0), "up": (0, -s), "down": (0, s)}[mv["dir"]]
                w.unplace(pi)
                targets = {ri: (c[0] + dx, c[1] + dy) for ri in rots}
                band = 0.3
            elif "between" in mv:
                a, b = (self.idx[x] for x in mv["between"])
                ca, cb = self.center_mm(a), self.center_mm(b)
                w.unplace(pi)
                targets = {ri: ((ca[0] + cb[0]) / 2, (ca[1] + cb[1]) / 2) for ri in rots}
                band = 0.8
            elif "to_edge" in mv:
                allp = np.concatenate(w.outline)
                bx0, by0 = allp.min(0)
                bx1, by1 = allp.max(0)
                e = SIDE.get(mv["to_edge"], mv["to_edge"])
                w.unplace(pi)
                targets = {}
                for ri in rots:
                    hw, hh, _ = self.half_ext(pi, ri)
                    m = w.R.ec
                    targets[ri] = {"above": (c[0], by0 + m + hh), "below": (c[0], by1 - m - hh),
                                   "left": (bx0 + m + hw, c[1]), "right": (bx1 - m - hw, c[1])}[e]
                weights = (0.3, 1.0) if e in ("above", "below") else (1.0, 0.3)
                band = 0.3
            else:
                return dict(rec, ok=False, err="unknown move")
            targets = {ri: self._clamp(pi, ri, t) for ri, t in targets.items()}
            if mv.get("push"):
                return self._push(pi, old, targets, band, weights, rec)
            pos, miss = self._resolve(pi, targets, band=band, weights=weights)
            return self._finish(pi, old, pos, miss, rec)
        except (KeyError, ValueError) as ex:
            return dict(rec, ok=False, err=f"bad move: {ex}")

    def _clamp(self, pi, ri, t):
        """Keep a part-centre target where the part's box fits inside the board's box."""
        allp = np.concatenate(self.world.outline)
        (bx0, by0), (bx1, by1) = allp.min(0), allp.max(0)
        hw, hh, _ = self.half_ext(pi, ri)
        m = self.world.R.ec
        x = min(max(t[0], bx0 + m + hw), max(bx0 + m + hw, bx1 - m - hw))
        y = min(max(t[1], by0 + m + hh), max(by0 + m + hh, by1 - m - hh))
        return (x, y)

    def _court_cells(self, pi, pose):
        cx, cy, ri = pose
        c = self.world.part_raster(self.world.parts[pi], ri, self.world.frac.get(pi, (0.0, 0.0)))["court"]
        return {(int(x) + cx, int(y) + cy) for x, y in c}

    def _push(self, pi, old, targets, band, weights, rec):
        """Place pi at its target even if movable parts are in the way: those parts are
        lifted and re-placed at the legal pose nearest their old centre (any rotation)."""
        w = self.world
        g = w.g
        # ideal pose: the first orientation's target, ignoring other parts
        ri, (tx, ty) = next(iter(targets.items()))
        _, _, (ox, oy) = self.half_ext(pi, ri)
        pose = (int(round((tx - w.x0) / g - ox)), int(round((ty - w.y0) / g - oy)), ri)
        mine = self._court_cells(pi, pose)
        sides = set(w.parts[pi].sides)
        hit = []
        for q in self.movable():
            if q == pi or not (sides & set(w.parts[q].sides)):
                continue
            if w.parts[q].area > w.parts[pi].area and rec["move"].get("push") != "all":
                continue  # big parts are not pushed by small ones
            if mine & self._court_cells(q, w.pose[q]):
                hit.append(q)
        olds = {q: w.pose[q] for q in hit}
        centres = {q: self.center_mm(q) for q in hit}
        for q in hit:
            w.unplace(q)
        pos, miss = self._resolve(pi, targets, band=band, weights=weights)
        if pos is None or miss > self.max_miss:
            for q in hit:
                w.place(q, *olds[q])
            w.place(pi, *old)
            return dict(rec, ok=False, err="no room even after pushing")
        w.place(pi, *pos)
        moved = {}
        for q in sorted(hit, key=lambda q: -w.parts[q].area):
            pq, mq = self._resolve(q, {r: centres[q] for r in range(4)}, band=0.3)
            if pq is None:
                for z in moved:
                    w.unplace(z)
                w.unplace(pi)
                w.place(pi, *old)
                for z in hit:
                    w.place(z, *olds[z])
                return dict(rec, ok=False, err=f"pushed part {self.names[q]} has nowhere to go")
            w.place(q, *pq)
            moved[q] = round(mq, 1)
        return dict(rec, ok=True, parts=[pi] + hit, miss_mm=round(miss, 2),
                    pushed={self.names[q]: d for q, d in moved.items()})

    def _check_movable(self, pi):
        p = self.world.parts[pi]
        if p.locked or pi in self.world.fixed:
            raise ValueError(f"{self.names[pi]} is locked")

    def _finish(self, pi, old, pos, miss, rec):
        w = self.world
        if pos is None:
            w.place(pi, *old)
            return dict(rec, ok=False, err="no legal pose")
        if miss > self.max_miss and not rec["move"].get("far_ok"):
            w.place(pi, *old)
            return dict(rec, ok=False, err=f"nearest legal pose is {miss:.1f} mm from the target (no room there)")
        w.place(pi, *pos)
        if tuple(pos) == tuple(old):
            return dict(rec, ok=False, err="resolved to current pose", parts=[pi])
        return dict(rec, ok=True, parts=[pi], miss_mm=round(miss, 2))

    # ------------------------------------------------------------ verification
    def verify(self, moved):
        """Re-route the nets of moved parts (plus any net whose copper became illegal),
        then, if connections are still missing, one negotiated pass over all nets."""
        kit, r = self.kit, self.r
        aff = kit.part_nets(moved) | set(kit.conflicted_nets())
        kit.reroute(aff, iters=8)
        if any(r.unrouted.values()):
            r.pathfinder(iters=15)
        return self.key()

    def try_batch(self, moves, plateau=False):
        """Apply moves, verify, keep if better. Returns (accepted, records, key_before, key_after)."""
        k0 = self.key()
        u0 = {n: c for n, c in self.r.unrouted.items() if c}
        snap = self.full_snapshot()
        recs = [self.apply_move(m) for m in moves]
        moved = sorted({q for rc in recs if rc.get("ok") for q in rc["parts"]})
        if not moved:
            self.full_restore(snap)
            return False, recs, k0, k0
        k1 = self.verify(moved)
        u1 = {n: c for n, c in self.r.unrouted.items() if c}
        nm = self.world.net_names
        diff = dict(fixed=sorted(nm[n] for n in u0 if u1.get(n, 0) < u0[n]),
                    broke=sorted(nm[n] for n in u1 if u1[n] > u0.get(n, 0)))
        if recs:
            recs[0]["net_diff"] = diff
        better = k1[:2] < k0[:2] or (k1[:2] == k0[:2] and k1[2] < k0[2] - 1e-6)
        if plateau and k1[:2] <= k0[:2]:
            better = True  # proposer asked to keep a sideways step (no more illegal/unrouted)
        if not better:
            self.full_restore(snap)
        return better, recs, k0, k1

    def round(self, moves, singles=True, plateau=False):
        out = dict(batch=None, singles=[])
        acc, recs, k0, k1 = self.try_batch(moves, plateau=plateau)
        out["batch"] = dict(accepted=acc, records=[_clean(r, self.names) for r in recs],
                            before=_k(k0), after=_k(k1))
        if not acc and singles and len(moves) > 1:
            for m in moves:
                a, rr, s0, s1 = self.try_batch([m])
                out["singles"].append(dict(accepted=a, record=_clean(rr[0], self.names), before=_k(s0), after=_k(s1)))
        return out

    # ------------------------------------------------------------ connectivity / blockers
    def net_components(self, n):
        """Pin groups of net n that its routed copper connects (list of lists of (pi, k))."""
        w, r = self.world, self.r
        pins = [(pi, k) for pi, k in w.net_pins[n] if pi in w.pose]
        cells = set()
        for p in r.routes.get(n, []):
            cells.update(map(tuple, p.tolist()))
        if not r.unrouted.get(n):
            return [pins]
        conn, alone = [], []
        for pi, k in pins:
            t = w.terminals(pi, k)
            (conn if cells and any(tuple(c) in cells for c in t) else alone).append((pi, k))
        comps = ([conn] if conn else []) + [[a] for a in alone]
        return comps

    def missing_links(self, n):
        """Ratsnest between disconnected components: list of ((x, y), (x, y), pinA, pinB)."""
        w = self.world
        comps = self.net_components(n)
        if len(comps) < 2:
            return []
        pos = [[w.pad_world(pi, k) for pi, k in c] for c in comps]
        joined = {0}
        out = []
        while len(joined) < len(comps):
            best = None
            for a in joined:
                for b in range(len(comps)):
                    if b in joined:
                        continue
                    for ia, pa in enumerate(pos[a]):
                        for ib, pb in enumerate(pos[b]):
                            d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                            if best is None or d < best[0]:
                                best = (d, a, b, ia, ib)
            _, a, b, ia, ib = best
            out.append((pos[a][ia], pos[b][ib], comps[a][ia], comps[b][ib]))
            joined.add(b)
        return out

    def blockers(self):
        """{net: {part: cells}} for unrouted nets, via methods.blockers (routes restored)."""
        out = {}
        for n in [n for n, k in self.r.unrouted.items() if k]:
            snap = self.kit.snapshot([n])
            bl = methods.blockers(self.world, self.kit, n)
            self.kit.restore(snap)
            out[n] = bl
        return out

    def unenterable_pads(self):
        """Pads no track can enter even on an empty board (neighbouring pads' clearance
        covers all their copper): no placement move can connect them."""
        w = self.world
        snap = self.kit.snapshot(list(self.r.routes))
        for n in list(self.r.routes):
            self.r.rip(n)
        out = []
        for pi in w.pose:
            for k, pad in enumerate(w.parts[pi].pads):
                n = w.net_id.get(pad["net"], 0) if pad["net"] else 0
                if n not in w.net_pins:
                    continue
                t = w.terminals(pi, k)
                if t and not any(w.DT[l, y, x] - (1 if w.occT[n, l, y, x] > 0 else 0) == 0 and not w.blockT[l, y, x]
                                 for (l, y, x) in t):
                    out.append(self.pin_name(pi, k))
        self.kit.restore(snap)
        return out

    def pin_name(self, pi, k):
        pad = self.world.parts[pi].pads[k]
        return f"{self.names[pi]}.{pad.get('num', pad.get('name', k))}"

    def outside_pads(self):
        from matplotlib.path import Path as MPath
        w = self.world
        paths = [MPath(o) for o in w.outline]
        bad = []
        for pi in w.pose:
            ap = self.aperture_mask(exclude=pi)
            for k in range(len(w.parts[pi].pads)):
                x, y = w.pad_world(pi, k)
                ix, iy = w.cell(x, y)
                if not any(p.contains_point((x, y)) for p in paths) or ap[iy, ix]:
                    bad.append(self.names[pi])
                    break
        return bad

    # ------------------------------------------------------------ outputs
    def summary(self, blk, title=""):
        w, r, kit = self.world, self.r, self.kit
        allp = np.concatenate(w.outline)
        bw, bh = np.ptp(allp[:, 0]), np.ptp(allp[:, 1])
        m = self.metrics()
        unr = {n: k for n, k in r.unrouted.items() if k}
        L = [f"# {self.bid} {title}",
             f"board {bw:.1f} x {bh:.1f} mm, {w.nl} copper layers; origin top-left, x right, y down (mm)",
             f"parts {len(w.parts)} ({len([p for p in w.parts if p.locked])} locked); nets {len(w.net_pins)}; "
             f"connections {m['connections']}",
             f"STATUS: unrouted connections {m['unrouted']} in {len(unr)} nets; routed length {m['length_mm']:.1f} mm; "
             f"vias {m['vias']}; cost {m['cost']:.1f} (lower is better; unrouted dominates)"]
        out = self.outside_pads()
        if out:
            L.append(f"ILLEGAL: parts with a pad centre outside the board or inside a cut-out (black outline): {', '.join(out)}")
        if unr:
            L.append("UNROUTED (missing links; parts the cheapest blocked route runs under):")
            for n in sorted(unr, key=lambda n: -unr[n]):
                links = self.missing_links(n)
                ls = "; ".join(f"{self.pin_name(*a)}-{self.pin_name(*b)}" for _, _, a, b in links)
                bl = blk.get(n, {})
                bs = ", ".join(f"{self.names[q]}({c})" for q, c in sorted(bl.items(), key=lambda t: -t[1])[:5])
                L.append(f"  {w.net_names[n]} ({len(w.net_pins[n])} pins, {unr[n]} missing): {ls}; blocked by: {bs or '-'}")
        une = self.unenterable_pads()
        if une:
            L.append("PADS NO TRACK CAN ENTER under these rules (pitch too fine; no move fixes them): " + ", ".join(une))
        L.append("PARTS (ref side rot WxH-mm centre(x,y) [locked] -> parts sharing signal nets; nets with >6 pins omitted):")
        big = {n for n, pins in w.net_pins.items() if len(pins) > 6}
        for pi in sorted(w.pose, key=lambda q: self.names[q]):
            p = w.parts[pi]
            x0, y0, x1, y1 = self.bbox_mm(pi)
            cx, cy, ri = w.pose[pi]
            rot = ROTS[ri] if ri < 4 else p.rot0
            nb = {}
            for ent in w.raster(pi)["pads"]:
                n = ent["net"]
                if n in w.net_pins and n not in big:
                    for q, _ in w.net_pins[n]:
                        if q != pi:
                            nb[q] = nb.get(q, 0) + 1
            nbs = " ".join(f"{self.names[q]}" + (f"x{c}" if c > 1 else "") for q, c in sorted(nb.items(), key=lambda t: -t[1])[:6])
            flags = " LOCKED" if (p.locked or pi in w.fixed) else ""
            L.append(f"  {self.names[pi]} {'B' if p.side else 'F'} {rot:.0f} {x1 - x0:.1f}x{y1 - y0:.1f} "
                     f"({(x0 + x1) / 2:.1f},{(y0 + y1) / 2:.1f}){flags} -> {nbs or '-'}")
        if big:
            L.append("big nets: " + ", ".join(f"{w.net_names[n]}({len(w.net_pins[n])})" for n in big))
        return "\n".join(L)

    def render(self, png, blk, title="", focus=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
        from matplotlib.patches import Circle, Polygon
        w, r = self.world, self.r
        g = w.g
        allp = np.concatenate(w.outline)
        bx0, by0 = allp.min(0)
        bx1, by1 = allp.max(0)
        if focus:
            bb = np.array([self.bbox_mm(self.idx[f]) for f in focus])
            bx0, by0 = bb[:, 0].min() - 3, bb[:, 1].min() - 3
            bx1, by1 = bb[:, 2].max() + 3, bb[:, 3].max() + 3
        bw, bh = bx1 - bx0, by1 - by0
        fw = 13.0 if not focus else 9.0
        fh = min(13.0, max(4.0, fw * bh / bw + 0.8))
        if fw * bh / bw + 0.8 > 13.0:
            fw = (13.0 - 0.8) * bw / bh
        fig, ax = plt.subplots(figsize=(fw, fh), dpi=100)
        ax.set_aspect("equal")
        ax.set_xlim(bx0 - 1.5, bx1 + 1.5)
        ax.set_ylim(by1 + 1.5, by0 - 1.5)
        pts_per_mm = fw * 72 / (bw + 3)
        for o in w.outline:
            ax.add_patch(Polygon(o, closed=True, fill=True, fc="#f4f1e8", ec="black", lw=1.5, zorder=0))
        for h in w.holes:
            ax.add_patch(Polygon(h, closed=True, fill=True, fc="white", ec="black", lw=1.0, zorder=0))
        blockers = {}
        for n, bl in blk.items():
            for q, c in bl.items():
                blockers[q] = blockers.get(q, 0) + c
        for pi in w.pose:
            p = w.parts[pi]
            cx, cy, ri = w.pose[pi]
            deg = ROTS[ri] if ri < 4 else p.rot0
            fx, fy = w.frac.get(pi, (0.0, 0.0))
            ox, oy = w.xy(cx, cy)
            ox += fx
            oy += fy
            locked = p.locked or pi in w.fixed
            fc = "#ffb347" if pi in blockers else ("#bbbbbb" if locked else ("#dde8ff" if p.side else "#ffffff"))
            for c in p.court:
                q = rot_pts(c, deg) + (ox, oy)
                ax.add_patch(Polygon(q, closed=True, fc=fc, ec="#555555", lw=0.8, alpha=0.85, zorder=1,
                                     ls="--" if p.side else "-"))
            for e in p.data.get("edges", []):
                if len(e) >= 3:
                    q = rot_pts(np.array(e, float), deg) + (ox, oy)
                    ax.add_patch(Polygon(q, closed=True, fc="black", ec="black", lw=1.2, zorder=5))
            for pad in p.pads:
                col = "#c8a000" if pad["cu"] == "both" else (LAYER_COL[1] if pad["cu"] == "B" else LAYER_COL[0])
                for pl in pad["poly"]:
                    if len(pl) >= 3:
                        q = rot_pts(np.array(pl, float), deg) + (ox, oy)
                        ax.add_patch(Polygon(q, closed=True, fc=col, ec="none", alpha=0.55, zorder=2))
            x0, y0, x1, y1 = self.bbox_mm(pi)
            size = max(5.5, min(11.0, 0.9 * min(x1 - x0, y1 - y0) * pts_per_mm / 2.2))
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, self.names[pi], ha="center", va="center", fontsize=size,
                    fontweight="bold", color="#202020" if not p.side else "#1a3a8a", zorder=6,
                    style="italic" if p.side else "normal",
                    bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.6), clip_on=True)
        lw = max(0.6, w.R.w * pts_per_mm)
        for l in range(w.nl):
            segs = []
            for n, ps in r.routes.items():
                for p in ps:
                    run = []
                    for (ll, y, x) in p.tolist():
                        if ll == l:
                            run.append((w.x0 + x * g, w.y0 + y * g))
                        else:
                            if len(run) > 1:
                                segs.append(run)
                            run = []
                    if len(run) > 1:
                        segs.append(run)
            col = LAYER_COL[0] if l == 0 else (LAYER_COL[1] if l == w.nl - 1 else LAYER_COL[2 + (l - 1) % 4])
            ax.add_collection(LineCollection(segs, colors=col, linewidths=lw, alpha=0.75, zorder=3 + (l == 0) * 0.1))
        for n, ps in r.routes.items():
            for p in ps:
                for i in range(1, len(p)):
                    if p[i, 0] != p[i - 1, 0]:
                        ax.add_patch(Circle((w.x0 + p[i, 2] * g, w.y0 + p[i, 1] * g), w.R.via_d / 2,
                                            fc="#444444", ec="white", lw=0.5, zorder=4))
        for n, k in r.unrouted.items():
            if not k:
                continue
            for a, b, _, _ in self.missing_links(n):
                ax.plot([a[0], b[0]], [a[1], b[1]], color="#ff00ff", lw=2.2, ls="--", zorder=7)
                ax.plot([a[0], b[0]], [a[1], b[1]], "o", color="#ff00ff", ms=4, zorder=7)
                ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, w.net_names[n][-14:], color="#b000b0", fontsize=8,
                        zorder=8, bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="#ff00ff", alpha=0.8), clip_on=True)
        m = self.metrics()
        ax.set_title(f"{self.bid[:60]} {title} | unrouted {m['unrouted']} | len {m['length_mm']:.0f} mm | "
                     f"vias {m['vias']} | cost {m['cost']:.0f}\nred=top Cu, blue=bottom Cu, gold=THT pad, "
                     f"dashed outline=bottom part, grey=locked,\norange=blocks an unrouted net, "
                     f"magenta dashed=missing link", fontsize=8)
        ax.xaxis.set_major_locator(plt.MultipleLocator(5))
        ax.yaxis.set_major_locator(plt.MultipleLocator(5))
        ax.grid(True, lw=0.3, alpha=0.5)
        ax.tick_params(labelsize=7)
        fig.tight_layout()
        fig.savefig(png)
        plt.close(fig)
        return fig.get_size_inches() * 100

    def emit(self, name):
        """Write the board (poses + copper) as NAME.kicad_pcb via kicad_io apply."""
        w = self.world
        tracks, vias = self.r.export()
        poses = {}
        for pi, (cx, cy, ri) in w.pose.items():
            p = w.parts[pi]
            if p.locked or pi in w.fixed:
                continue
            x, y = w.xy(cx, cy)
            poses[str(pi)] = dict(x=x, y=y, rot=ROTS[ri], uuid=p.uuid)
        res = self.dir / f"{name}.result.json"
        res.write_text(json.dumps(dict(poses=poses, tracks=tracks, vias=vias)))
        out = self.dir / f"{name}.kicad_pcb"
        kicad("apply", task_board(self.bid), res, out)
        return out


def _k(k):
    return dict(illegal=int(k[0]), unrouted=int(k[1]), cost=round(float(k[2]), 2))


def _clean(rec, names):
    r = {k: v for k, v in rec.items() if k != "parts"}
    if "parts" in rec:
        r["parts"] = [names[q] for q in rec["parts"]]
    return r


# ---------------------------------------------------------------- CLI
def latest_round(d):
    rs = sorted(int(f.stem.split("_r")[1]) for f in d.glob("state_r*.json"))
    return rs[-1] if rs else None


def publish(s, rnd, label="", focus=None):
    t = time.time()
    blk = s.blockers()
    png = s.dir / (f"render_r{rnd}.png" if not focus else f"render_r{rnd}_zoom.png")
    size = s.render(png, blk, f"round {rnd} {label}", focus=focus)
    txt = s.summary(blk, f"round {rnd} {label}")
    (s.dir / f"summary_r{rnd}.txt").write_text(txt)
    img_tok = int(size[0] * size[1] / 750)
    return png, txt, img_tok, time.time() - t


def cmd_init(a):
    s = Session(a.id)
    t0 = time.time()
    s.init_seq(budget=a.budget, seed=a.seed)
    s.save(s.dir / "state_r0.json")
    png, txt, img_tok, _ = publish(s, 0, "(seq)")
    (s.dir / "log.jsonl").write_text(json.dumps(dict(round=0, t=time.time(), compute_s=round(time.time() - t0, 1),
                                                     img_tokens=img_tok, summary_tokens=len(txt) // 4,
                                                     **s.metrics())) + "\n")
    print(txt)
    print(f"render: {png}")


def cmd_step(a):
    s = Session(a.id)
    rnd = latest_round(s.dir)
    s.load(s.dir / f"state_r{rnd}.json")
    spec = json.loads(Path(a.moves).read_text())
    moves = spec["moves"] if isinstance(spec, dict) else spec
    t0 = time.time()
    res = s.round(moves, singles=not a.no_singles, plateau=isinstance(spec, dict) and bool(spec.get("plateau")))
    nxt = rnd + 1
    s.save(s.dir / f"state_r{nxt}.json")
    png, txt, img_tok, _ = publish(s, nxt)
    prev = [json.loads(x) for x in (s.dir / "log.jsonl").read_text().splitlines()]
    entry = dict(round=nxt, t=time.time(), wall_since_prev_s=round(time.time() - prev[-1]["t"], 1),
                 compute_s=round(time.time() - t0, 1), moves=moves, note=spec.get("note") if isinstance(spec, dict) else None,
                 proposer_out_tokens=len(json.dumps(spec)) // 4, img_tokens=img_tok, summary_tokens=len(txt) // 4,
                 result=res, **s.metrics())
    with open(s.dir / "log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
    b = res["batch"]
    print(f"batch accepted={b['accepted']} {b['before']} -> {b['after']} nets {b['records'][0].get('net_diff')}")
    for rc in b["records"]:
        print("  ", json.dumps(rc))
    for sg in res["singles"]:
        rc = {k: v for k, v in sg["record"].items() if k != "move"}
        print(f"  single accepted={sg['accepted']} {sg['before']} -> {sg['after']} {json.dumps(sg['record']['move'])[:70]} {json.dumps(rc)}")
    print(txt)
    print(f"render: {png}")


def cmd_show(a):
    s = Session(a.id)
    rnd = a.round if a.round is not None else latest_round(s.dir)
    s.load(s.dir / f"state_r{rnd}.json")
    png, txt, _, _ = publish(s, rnd, focus=a.focus.split(",") if a.focus else None)
    print(txt)
    print(f"render: {png}")


def cmd_finalize(a):
    s = Session(a.id)
    f = s.dir / (a.state or f"state_r{a.round if a.round is not None else latest_round(s.dir)}.json")
    s.load(f)
    out = s.emit(a.name)
    print(json.dumps(dict(board=str(out), **s.metrics())))


def random_moves(s, rng, k):
    mov = [q for q in s.movable() if q not in getattr(s.world, "mech", set())]
    names = [s.names[q] for q in mov]
    allnames = [s.names[q] for q in s.world.pose]
    out = []
    for _ in range(k):
        t = rng.random()
        a = rng.choice(names)
        if t < 0.35:
            out.append({"move": a, "near": rng.choice([n for n in allnames if n != a]),
                        "side": rng.choice(["left", "right", "above", "below", "any"]),
                        "dist": rng.choice(["tight", "close", "loose"])})
        elif t < 0.55:
            out.append({"rotate": a, "by": rng.choice([90, 180, 270])})
        elif t < 0.7 and len(names) > 1:
            out.append({"swap": rng.sample(names, 2)})
        elif t < 0.9:
            out.append({"move": a, "dir": rng.choice(["left", "right", "up", "down"]),
                        "dist": rng.choice(["tight", "close", "loose"])})
        else:
            out.append({"move": a, "to_edge": rng.choice(["top", "bottom", "left", "right"])})
        if "move" in out[-1] and rng.random() < 0.5:
            out[-1]["push"] = True
        if "move" in out[-1] and rng.random() < 0.3:
            out[-1]["rot"] = "any"
    return out


def blocker_moves(s, rng, k):
    """Non-LLM heuristic proposer from the same summary: move a blocker of an unrouted net
    a step away from the missing link, or move a disconnected pin's part next to its peer."""
    blk = s.blockers()
    unr = [n for n, c in s.r.unrouted.items() if c]
    if not unr:
        return random_moves(s, rng, k)
    out = []
    for _ in range(k):
        n = rng.choice(unr)
        links = s.missing_links(n)
        bl = blk.get(n, {})
        movable = set(s.movable())
        if bl and rng.random() < 0.6:
            q = rng.choice([q for q in bl if q in movable] or list(movable))
            out.append({"move": s.names[q], "dir": rng.choice(["left", "right", "up", "down"]),
                        "dist": rng.choice(["tight", "close", "loose"]), "push": rng.random() < 0.5})
        elif links:
            _, _, pa, pb = rng.choice(links)
            a, b = (pa[0], pb[0]) if rng.random() < 0.5 else (pb[0], pa[0])
            if a in movable and a != b:
                out.append({"move": s.names[a], "near": s.names[b], "side": "any", "dist": "close", "rot": "any",
                            "push": rng.random() < 0.5})
            else:
                out += random_moves(s, rng, 1)
        else:
            out += random_moves(s, rng, 1)
    return out


def cmd_control(a):
    """Same verifier, non-LLM proposer (random or blocker heuristic), from round 0."""
    s = Session(a.id)
    s.load(s.dir / "state_r0.json")
    rng = random.Random(a.seed)
    gen = random_moves if a.kind == "random" else blocker_moves
    logf = s.dir / f"control_{a.kind}_s{a.seed}.jsonl"
    with open(logf, "w") as f:
        for rd in range(1, a.rounds + 1):
            t0 = time.time()
            moves = gen(s, rng, a.moves)
            res = s.round(moves)
            f.write(json.dumps(dict(round=rd, compute_s=round(time.time() - t0, 1), moves=moves,
                                    batch_acc=res["batch"]["accepted"],
                                    singles_acc=sum(x["accepted"] for x in res["singles"]), **s.metrics())) + "\n")
            print(rd, res["batch"]["accepted"], sum(x["accepted"] for x in res["singles"]), s.metrics(), flush=True)
    s.save(s.dir / f"state_control_{a.kind}_s{a.seed}.json")
    out = s.emit(f"control_{a.kind}_s{a.seed}")
    print(json.dumps(dict(board=str(out), **s.metrics())))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("id")
    p.add_argument("--budget", type=float, default=120)
    p.add_argument("--seed", type=int, default=0)
    p = sp.add_parser("step")
    p.add_argument("id")
    p.add_argument("moves")
    p.add_argument("--no-singles", action="store_true")
    p = sp.add_parser("show")
    p.add_argument("id")
    p.add_argument("--round", type=int)
    p.add_argument("--focus", help="comma-separated refs to zoom on")
    p = sp.add_parser("finalize")
    p.add_argument("id")
    p.add_argument("--round", type=int)
    p.add_argument("--state")
    p.add_argument("--name", default="final")
    p = sp.add_parser("control")
    p.add_argument("id")
    p.add_argument("--rounds", type=int, default=8)
    p.add_argument("--moves", type=int, default=4)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--kind", default="random", choices=["random", "blocker"])
    a = ap.parse_args()
    {"init": cmd_init, "step": cmd_step, "show": cmd_show, "finalize": cmd_finalize, "control": cmd_control}[a.cmd](a)


if __name__ == "__main__":
    main()
