# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Anytime output for run.py: the best legal board so far is on disk while a method runs.

A restart wrapper judges an attempt's board when the attempt exits and kills attempts at
its deadline, so a method that writes only at the end loses everything to a kill and
reports an easy board late. run.py installs this module; every Router.legalize (the end
of every PathFinder call, Kit.reroute and the methods' own final legalize) then offers the
current state, as do methods that call offer() at their own checkpoints. A state is
written (KiCad apply to a temporary file, then os.replace, in a background thread so the
method keeps going) when
  - every part is placed, no routed net is in conflict, no movable part overlaps or leaves
    the board, and every connection pnr counts as routed has copper on its pads, and
  - it leaves fewer connections open than the board written last, or as many at a lower
    routed cost (length + 2 mm per via) and at least `every_s` wall seconds after it.
With stop_when_routed, a written-quality state with no open connection ends the method
(Routed, caught by run.py, which then writes it as the final board): the wrapper stops at
the first DRC-clean board anyway, and only KiCad decides clean.

budget_stop() is the run's CPU deadline (budget x (1 + overrun)); router.STOP uses it to end
PathFinder passes that would run past it.
"""
import os
import shutil
import threading
import time
from pathlib import Path

import numpy as np

_A = None


class Routed(BaseException):
    """Raised through a method when a complete, legal board was reached (not an Exception,
    so a method's own `except Exception` does not swallow it)."""
    def __init__(self, router):
        super().__init__("all connections routed")
        self.router = router


def offer(router, cost=None):
    """Offer the current state (world poses + router copper). No-op unless run.py installed
    the module. `cost` is unused for now (the tie-break is routed length + vias)."""
    if _A is not None:
        _A.offer(router)


def budget_stop():
    return _A is not None and _A.over_budget()


def install(world, write, budget, log, every_s=30.0, stop_when_routed=True, overrun=0.1, enabled=True, t0=None):
    """write(payload, path) writes a board for run.py's export payload. Returns the Anytime."""
    global _A
    _A = Anytime(world, write, budget, log, every_s, stop_when_routed, overrun, enabled)
    if t0 is not None:
        _A.t0 = t0  # times in the summary count from the start of run.py
    import router as R
    if not getattr(R.Router.legalize, "_anytime", False):
        orig = R.Router.legalize

        def legalize(self, *a, **kw):
            out = orig(self, *a, **kw)
            offer(self)
            return out
        legalize._anytime = True
        R.Router.legalize = legalize
    R.STOP = budget_stop
    return _A


def export(world, router):
    """run.py's result payload (poses of movable parts, tracks, vias)."""
    from world import ROTS
    tracks, vias = router.export()
    poses = {}
    for pi, (cx, cy, ri) in world.pose.items():
        p = world.parts[pi]
        if p.locked or pi in world.fixed:
            continue
        x, y = world.xy(cx, cy)
        poses[str(pi)] = dict(x=x, y=y, rot=ROTS[ri], uuid=p.uuid)
    return dict(poses=poses, tracks=tracks, vias=vias)


def routed_cost(router):
    st = router.stats()
    return st["length_mm"] + 2.0 * st["vias"]


def legal(world, router):
    return problem(world, router) is None


def problem(world, router):
    """None when pnr's own checks pass for a board to be written: all parts placed, no routed
    net in conflict, no movable part overlapping or outside, no stale copper (a connection
    counted as routed whose pad has no copper, e.g. after a move without a re-route);
    else what failed."""
    w, r = world, router
    if len(w.pose) < len(w.parts):
        return "unplaced parts"
    for n, ps in r.routes.items():
        if ps and r.net_conflicts(n):
            return "conflicts"
    for p in w.parts:
        if not p.locked and p.idx not in w.fixed and w.part_violation(p.idx) != (0, 0):
            return f"part {p.ref} overlaps or is outside"
    st = getattr(w, "shape_terms", {})
    H, W = w.H, w.W
    for n, pins in w.net_pins.items():
        terms = [w.terminal_array(pi, k) for pi, k in pins] + list(st.get(n, []))
        terms = [t for t in terms if len(t)]
        if len(terms) < 2:
            continue
        unr = r.unrouted.get(n, 0)
        paths = r.routes.get(n, [])
        if not paths:
            if unr < len(terms) - 1:
                return f"net {w.net_names[n]} has no copper"
            continue
        cells = np.unique(np.concatenate([(p[:, 0].astype(np.int64) * H + p[:, 1]) * W + p[:, 2] for p in paths]))
        untouched = sum(1 for t in terms if not np.isin((t[:, 0] * H + t[:, 1]) * W + t[:, 2], cells).any())
        if untouched > unr:
            return f"net {w.net_names[n]}: stale copper"
    return None


class Anytime:
    def __init__(self, world, write, budget, log, every_s, stop_when_routed, overrun, enabled):
        self.w = world
        self.write = write
        self.log = log
        self.every_s = every_s
        self.stop_when_routed = stop_when_routed
        self.enabled = enabled
        self.t0 = time.time()
        self.cpu0 = time.process_time()
        self.limit = None if overrun is None or overrun < 0 else budget * (1.0 + overrun)
        self.best = None  # (open, cost) of the best state accepted for writing
        self.best_payload = None
        self.t_write = -1e9  # wall time of the last accepted state
        self.t_retry = 0.0  # no full check before this wall time (after a failed one)
        self.writes = []  # (wall s since start, open, cost) of every board on disk
        self.first_complete_s = None
        self.stopped = False
        self.lock = threading.Lock()
        self.pending = None
        self.thread = None
        self.closed = False
        self.check_s = 0.0
        self.checks = 0
        self.why = None  # the last check's problem (logged when it changes)

    def over_budget(self):
        return self.limit is not None and time.process_time() - self.cpu0 > self.limit

    def offer(self, router):
        if not (self.enabled or self.stop_when_routed):
            return
        w = self.w
        if len(w.pose) < len(w.parts):
            return
        unr = sum(router.unrouted.values())
        now = time.time()
        if self.best is not None:
            if unr > self.best[0] or (unr == self.best[0] and now - self.t_write < self.every_s):
                return
        if now < self.t_retry:
            return
        t = time.perf_counter()
        cost = routed_cost(router)
        ok = self.best is None or unr < self.best[0] or cost < self.best[1] - 1e-6
        if ok:
            why = problem(w, router)
            if why is not None and why != self.why:
                self.log(f"anytime: not written ({why})")
            self.why = why
            ok = why is None
        dt = time.perf_counter() - t
        self.check_s += dt
        self.checks += 1
        if not ok:
            # a failed check (illegal, or not cheaper) waits 20x its own time before the next
            # one, so checks stay a small share of the run
            self.t_retry = now + 20 * dt
            return
        self.best = (unr, cost)
        self.t_write = now
        if unr == 0 and self.stop_when_routed:
            self.stopped = True
            self.log(f"anytime: complete and legal at {now - self.t0:.1f}s (cost {cost:.1f}); stopping")
            raise Routed(router)
        if not self.enabled:
            return
        payload = export(w, router)
        self.best_payload = payload
        self._submit((now - self.t0, unr, round(cost, 2)), payload)

    # ------------------------------------------------------------ writer thread
    def _submit(self, info, payload):
        with self.lock:
            if self.closed:
                return
            self.pending = (info, payload)
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()

    def _run(self):
        while True:
            with self.lock:
                if self.pending is None or self.closed:
                    self.thread = None
                    return
                info, payload = self.pending
                self.pending = None
            try:
                tmp = self.write(payload, final=False)
            except Exception as e:  # a failed checkpoint must not end the method
                self.log(f"anytime: write failed: {str(e)[-300:]}")
                continue
            with self.lock:
                if self.closed:
                    self.write.discard(tmp)
                    continue
                self.write.commit(tmp)
                t = round(time.time() - self.t0, 1)
                self.writes.append((t,) + info[1:])
                if info[1] == 0 and self.first_complete_s is None:
                    self.first_complete_s = t
            self.log(f"anytime: wrote board from {info[0]:.1f}s at {t:.1f}s open={info[1]} cost={info[2]}")

    def close(self):
        """No more checkpoint writes; one in flight is not committed (the final write follows)."""
        with self.lock:
            self.closed = True
            self.pending = None
            th = self.thread
        return th

    def summary(self):
        return dict(writes=len(self.writes), first_write_s=self.writes[0][0] if self.writes else None,
                    first_complete_s=self.first_complete_s, stopped_routed=self.stopped,
                    checks=self.checks, check_s=round(self.check_s, 2), trail=self.writes[:50])


class Writer:
    """write(payload) -> temporary board; commit(tmp) moves it over the output atomically
    (with the project files KiCad saved next to it)."""
    def __init__(self, kicad, inp, out):
        self.kicad = kicad
        self.inp = inp
        self.out = Path(out)
        self.dir = self.out.parent / ".anytime"
        self.n = 0

    def __call__(self, payload, final=False):
        import json
        self.n += 1
        d = self.dir / ("final" if final else f"w{self.n}")
        d.mkdir(parents=True, exist_ok=True)
        res = d / "result.json"
        res.write_text(json.dumps(payload))
        tmp = d / self.out.name
        self.kicad("apply", self.inp, res, tmp)
        return tmp

    def commit(self, tmp):
        tmp = Path(tmp)
        for f in tmp.parent.iterdir():  # board.kicad_pcb, and board.kicad_pro/prl if KiCad wrote them
            if f.stem == tmp.stem and f.suffix != ".json":
                os.replace(f, self.out.with_suffix(f.suffix))
        self.discard(tmp)

    def discard(self, tmp):
        shutil.rmtree(Path(tmp).parent, ignore_errors=True)
