# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""jc2: joint collapse by continuation (jc.py, unchanged reference) with its known
weaknesses addressed one switch at a time (tag `jcfix`, write-up RESULTS-jc2.md).

Switches (run.py --opt key=value; defaults reproduce jc on engine v6 except `engine`):
    engine=1        engine v6 prices PTH holes under courtyards and footprint cutouts in its
                    keep-out planes; drop jc's own copies so they are not counted twice
    via_beta=0      router via cost grows with beta: via_mm = 2 * (1 + via_beta * ln(1+beta))
                    (net cost schedule: late layer flips must pay more than detours)
    via_part=0      part best response: the current pose class (same rotation, ~1 mm) pays
                    via_part x the via price per via of the part's own nets within 3 mm
    clean=0         via clean-up at the end: re-route nets with vias one at a time, hard (always
                    legal), at clean_via mm per via with their via neighbours ripped too;
                    keep when vias fall and length grows by less than via_trade mm per via
    complete=0      completion pass: for every open connection, rip the nets whose copper
                    crosses its pins' box, negotiate them together, legalize; keep if fewer
                    open; then methods_combo.repair_phys (blocker parts moved) on what is left
    stall=0         stop a continuation after this many iterations at the top of the beta
                    schedule without a new lowest conflict (jc burns them)
    fill=0          the time after the last whole run goes to one perturbed resume from the
                    best state instead of to the polish
    minplus_w=0     blend the min-plus route-cost map (tools/research/xf_minplus) into the
                    part's wire term, from beta >= mp_from_beta
    guard=1         never accept a final PathFinder retry or a polish that is worse (more
                    open connections or higher cost) than the state before it (BUGS.md 6)
    end_alt=0       end of each continuation: also try keeping the collapsed copper and
                    re-routing only conflicted nets (Router.legalize); keep the cheaper
    legal_first=1   restarts are ranked legal first (jc ranks an illegal run by cost alone)
    restart=scratch scratch (jc) | perturb: every second restart starts from the best state,
                    re-rotates/re-lifts the k parts with the most part+wire history and
                    resumes the continuation from beta_p
"""
import os
import math
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pnr"))

import jc as J  # noqa: E402
import methods as M  # noqa: E402
import methods_combo as MC  # noqa: E402
import methods_phys as MP  # noqa: E402
from placekit import Clock  # noqa: E402
from router import vias_of  # noqa: E402

EMPTY = np.zeros((0, 2), np.int32)


def _vias(r, n):
    return sum(len(vias_of(p)) for p in r.routes.get(n, []))


def _length(r, w, n):
    L = 0.0
    for p in r.routes.get(n, []):
        d = np.abs(np.diff(p, axis=0))
        same = d[:, 0] == 0
        L += float(np.sum(np.where((d[same, 1] + d[same, 2]) == 2, math.sqrt(2), 1.0))) * w.g
    return L


class Collapse2(J.Collapse):
    def __init__(self, world, seed, budget, log, engine=1, via_beta=0.0, via_part=0.0, minplus_w=0.0,
                 mp_from_beta=0.0, coarse_mm=0.4, guard=1, end_alt=0, legal_first=1, **kw):
        super().__init__(world, seed, budget, log, **kw)
        self.guard = bool(guard)
        self.legal_first = bool(legal_first)
        self.end_alt = bool(end_alt)
        self.mp = None
        self.minplus_w = float(minplus_w)
        self.mp_from_beta = mp_from_beta
        if self.minplus_w > 0:
            # min-plus wire term (tools/research/xf_minplus, transformation T1): routed-cost
            # distance fields on the priced grid instead of HPWL in the part best response
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xf_minplus"))
            import minplus as MPL
            self._MPC = MPL.MPCollapse
            self.mp = MPL.MinPlus(world, self.r, self.kit, coarse_mm, True, False)
            self.mp_t, self.mp_calls = 0.0, 0
        self.engine = bool(engine)
        if self.engine:
            self.cut_parts = []
        self.via_beta = via_beta
        self.via_part = via_part
        self.via0 = self.r.via_cost

    def holes(self, pi, ri):
        if self.engine:
            return EMPTY, EMPTY
        return super().holes(pi, ri)

    def hole_map(self, skip=None):
        if self.engine:
            return np.zeros((self.w.H, self.w.W), np.float32)
        return super().hole_map(skip)

    def set_via(self, beta):
        self.r.via_cost = self.via0 * (1.0 + self.via_beta * math.log1p(max(beta, 0.0)))

    def route_all(self, beta):
        self.set_via(beta)
        return super().route_all(beta)

    def best_response(self, pi, beta, CT, CV, per):
        """jc's best response; with via_part, the part's current pose class (same rotation,
        within ~1 mm) also pays via_part x the via price for every via of its own nets
        within 3 mm of it: a pose that forces vias must beat its alternatives by that much."""
        self._vp = None
        if self.via_part and beta > 0:
            w = self.w
            cx, cy, ri = w.pose[pi]
            c = w.raster(pi)["court"]
            rad = int(3.0 / w.g)
            x0, x1 = c[:, 0].min() + cx - rad, c[:, 0].max() + cx + rad
            y0, y1 = c[:, 1].min() + cy - rad, c[:, 1].max() + cy + rad
            nv = 0
            for n in self.kit.part_nets([pi]):
                if n in per and len(per[n][1]):
                    v = per[n][1]
                    nv += int(((v[:, 0] >= y0) & (v[:, 0] <= y1) & (v[:, 1] >= x0) & (v[:, 1] <= x1)).sum())
            if nv:
                self._vp = (cx, cy, ri, self.via_part * self.via0 * nv)
        return super().best_response(pi, beta, CT, CV, per)

    def wire_term(self, pi, ri, beta, anchors, prepared):
        return self._MPC.wire_term(self, pi, ri, beta, anchors, prepared)

    def part_cost_maps(self, pi, beta, CT, CV, anchors):
        vp = getattr(self, "_vp", None)
        base = (self._MPC.part_cost_maps(self, pi, beta, CT, CV, anchors) if self.mp is not None
                else super().part_cost_maps(pi, beta, CT, CV, anchors))
        for ri, c, inside in base:
            if vp is not None and ri == vp[2]:
                r = max(2, int(1.0 / self.w.g))
                c = np.array(c, dtype=np.float64, copy=True)
                c[max(0, vp[1] - r):vp[1] + r + 1, max(0, vp[0] - r):vp[0] + r + 1] += vp[3]
            yield ri, c, inside

    # ------------------------------------------------------------ end passes
    def via_cleanup(self, clock, via_mm=8.0, via_trade=3.0, rounds=2):
        """Re-route nets with vias at a higher via price, hard (legal by construction)."""
        w, r, kit = self.w, self.r, self.kit
        hist = w.hist.copy()
        w.hist[:] = 0
        old = r.via_cost
        r.via_cost = via_mm / w.g
        r.pres = 0.0
        v0 = r.stats()["vias"]
        acc = tried = 0
        for _ in range(rounds):
            nets = sorted([n for n in w.net_pins if _vias(r, n)], key=lambda n: -_vias(r, n))
            gain = 0
            for n in nets:
                if clock.left() <= 0:
                    break
                group = [n] + self.via_neighbours(n)
                snap = kit.snapshot(group)
                vb = sum(_vias(r, m) for m in group)
                lb = sum(_length(r, w, m) for m in group)
                ub = sum(r.unrouted.get(m, 0) for m in group)
                for m in group:
                    r.rip(m)
                for m in group:
                    r.route_net(m, hard=True)
                va = sum(_vias(r, m) for m in group)
                la = sum(_length(r, w, m) for m in group)
                ua = sum(r.unrouted.get(m, 0) for m in group)
                bad = any(r.net_conflicts(m) for m in group)
                tried += 1
                if not bad and ua <= ub and va < vb and la - lb < via_trade * (vb - va):
                    acc += 1
                    gain += vb - va
                else:
                    kit.restore(snap)
            if not gain:
                break
        r.via_cost = old
        w.hist[:] = hist
        self.log(f"jc2 via clean-up: vias {v0} -> {r.stats()['vias']} (tried {tried}, kept {acc}) {r.stats()}")

    def via_neighbours(self, n, rad_mm=1.5, k=4):
        """Nets with copper near the vias of net n (the nets the vias hop over)."""
        w, r = self.w, self.r
        vs = np.concatenate([vias_of(p) for p in r.routes.get(n, [])] or [np.zeros((0, 3), np.int32)])
        if not len(vs):
            return []
        rad = int(rad_mm / w.g)
        cnt = {}
        for _, y, x in vs:
            y0, y1, x0, x1 = max(0, y - rad), y + rad + 1, max(0, x - rad), x + rad + 1
            for m, ps in r.routes.items():
                if m == n or not ps:
                    continue
                for p in ps:
                    sel = (p[:, 1] >= y0) & (p[:, 1] < y1) & (p[:, 2] >= x0) & (p[:, 2] < x1)
                    if sel.any():
                        cnt[m] = cnt.get(m, 0) + 1
                        break
        return sorted(cnt, key=lambda m: -cnt[m])[:k]

    def open_nets(self):
        return [n for n in self.w.net_pins if self.r.unrouted.get(n)]

    def box_neighbours(self, n, margin_mm=2.0):
        w, r = self.w, self.r
        pins = np.array([w.pad_world(q, k) for q, k in w.net_pins[n] if q in w.pose])
        if not len(pins):
            return []
        x0, y0 = pins.min(0) - margin_mm
        x1, y1 = pins.max(0) + margin_mm
        cx0, cy0 = int((x0 - w.x0) / w.g), int((y0 - w.y0) / w.g)
        cx1, cy1 = int((x1 - w.x0) / w.g), int((y1 - w.y0) / w.g)
        out = []
        for m, ps in r.routes.items():
            if m == n or not ps:
                continue
            for p in ps:
                if ((p[:, 1] >= cy0) & (p[:, 1] <= cy1) & (p[:, 2] >= cx0) & (p[:, 2] <= cx1)).any():
                    out.append(m)
                    break
        return out

    def complete(self, clock, repair_frac=0.6):
        """Open connections: negotiate each with the nets crossing its box, then move
        blocking parts (methods_combo.repair_phys) with what is left of the clock."""
        w, r, kit = self.w, self.r, self.kit
        u0 = sum(r.unrouted.values())
        if not u0:
            return
        for n in self.open_nets():
            if clock.left() <= clock.budget * repair_frac:
                break
            if not r.unrouted.get(n):
                continue
            group = [n] + self.box_neighbours(n)
            allsnap = kit.snapshot(list(w.net_pins))
            cb = kit.total_cost()
            ub = sum(r.unrouted.values())
            r.pathfinder(nets=group, iters=12, pres0=0.5, pres_mul=1.6, order=lambda ns: ns)
            if any(r.unrouted.values()):
                r.legalize(list(w.net_pins))
            ua = sum(r.unrouted.values())
            if ua < ub or (ua == ub and kit.total_cost() < cb - 1e-6):
                self.log(f"jc2 complete: net {n} open {ub} -> {ua} ({len(group)} nets)")
            else:
                kit.restore(allsnap)
        if any(r.unrouted.values()) and clock.left() > 1:
            self.ph.sync()
            MC.repair_phys(w, kit, self.ph, self.phys_w, Clock(max(1.0, clock.left())), self.log,
                           self.rng)
        self.log(f"jc2 complete: open {u0} -> {sum(r.unrouted.values())} {r.stats()}")

    def illegal_parts(self):
        return [q for q in self.kit.movable() if q in self.w.pose and self.violation(q) != (0, 0)]

    def hot_parts(self, k):
        """Movable parts ranked by part history under their keep-out + wire history at
        their pads (where the collapse fought hardest)."""
        w = self.w
        wire = w.hist.sum(0)
        part = self.hist_c.sum(0)
        sc = {}
        for q in self.kit.movable():
            if q not in w.pose:
                continue
            cx, cy, _ = w.pose[q]
            c = w.raster(q)["court"]
            xs = np.clip(c[:, 0] + cx, 0, w.W - 1)
            ys = np.clip(c[:, 1] + cy, 0, w.H - 1)
            sc[q] = float(part[ys, xs].sum() + wire[ys, xs].sum()) / max(1, len(c)) ** 0.5
        return sorted(sc, key=lambda q: -sc[q] * self.rng.uniform(0.6, 1.4))[:k]


def _state(C):
    w, kit = C.w, C.kit
    return (dict(w.pose), kit.snapshot(list(w.net_pins)), w.hist.copy(), C.hist_c.copy())


def _restore(C, st):
    w, r, kit = C.w, C.r, C.kit
    mov = kit.movable()
    for q in [q for q in mov if q in w.pose]:
        w.unplace(q)
    r.rip_all()
    r.unrouted.clear()
    for q, p in st[0].items():
        if q in mov:
            w.place(q, *p)
    kit.restore(st[1])
    w.hist[:] = st[2]
    C.hist_c[:] = st[3]
    C.ph.sync()


def perturb(C, k, hist_keep=0.5):
    """From the current (best) state: the k hottest parts get a random new rotation and jump
    to their HPWL(+physics) optimum ignoring overlaps (a partial re-lift); histories decay."""
    w, kit, ph = C.w, C.kit, C.ph
    hot = C.hot_parts(k)
    for q in hot:
        cur = w.pose[q]
        w.unplace(q)
        rots = [ri for ri in range(4) if ri != cur[2]] if C.rng.random() < 0.7 else [cur[2]]
        best = None
        for ri in rots:
            inside = C.inside_map(q, ri)
            if not inside.any():
                continue
            c = kit.hpwl_map(q, ri) + C.bias(q, ri)
            c = np.where(inside, c, np.inf)
            j = int(np.argmin(c))
            if np.isfinite(c.flat[j]) and (best is None or c.flat[j] < best[0]):
                best = (c.flat[j], j % w.W, j // w.W, ri)
        w.place(q, *(best[1:] if best else cur))
        ph.commit(q)
    w.hist *= hist_keep
    C.hist_c *= hist_keep
    ph.sync()
    return hot


def collapse_run(C, run_budget, gamma, beta0, beta_end, beta_max, log, start=None, stall=0):
    """jc.collapse_once, optionally resuming from the current placement (start='resume':
    no lift, nets kept) at beta0."""
    w, r, kit, ph = C.w, C.r, C.kit, C.ph
    clock = C.clock
    t_start = clock.budget - clock.left()
    end_t = t_start + run_budget
    if start is None:
        mov = [q for q in kit.movable() if q not in w.pose]
        C.lift(mov)
    mov = [q for q in kit.movable() if q in w.pose]
    ph.sync()
    log(f"jc2 start({start or 'lift'}): overlap={C.overlap_cells()} wire_conflicts={C.wire_conflicts()} "
        f"{r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f} parts={len(mov)}")
    beta = beta0
    g_cur = gamma
    prev = None
    it = zero = 0
    t_it = []
    best_conf, flat = None, 0
    while True:
        it += 1
        t0 = clock.budget - clock.left()
        bad = C.route_all(beta)
        moved = 0
        CT, CV, per = C.route_maps()
        order = list(mov)
        C.rng.shuffle(order)
        for pi in order:
            moved += C.best_response(pi, beta, CT, CV, per)
        C.hist_c += C.hist_inc * (w.court > 1)
        ovc = C.overlap_cells()
        wc = C.wire_conflicts()
        conf = ovc + wc
        used = clock.budget - clock.left()
        t_it.append(used - t0)
        C.trace.append((beta, ovc, wc, w.hpwl()))
        log(f"  jc it={it} beta={beta:.3g} gamma={g_cur:.2f} via={C.r.via_cost * w.g:.1f} moved={moved} "
            f"overlap={ovc} wire_conf={wc} nets_bad={len(bad)} {r.stats()} hpwl={w.hpwl():.1f} "
            f"phys={ph.total():.2f} t={used:.1f}")
        zero = zero + 1 if conf == 0 else 0
        if conf == 0 and (moved == 0 or zero >= 2):
            break
        if used > end_t:
            break
        # stall: at the top of the schedule nothing moves and the same conflict stays; the
        # remaining iterations only burn budget (the end phase decides those nets anyway)
        if best_conf is None or conf < best_conf:
            best_conf, flat = conf, 0
        elif beta >= min(beta_end, beta_max):
            flat += 1
        if stall and flat >= stall:
            log(f"jc2 stall: beta={beta:.3g} conflict {conf} flat for {flat} its")
            break
        if prev is not None and prev > 0:
            ratio = conf / prev
            if ratio > 0.85:
                g_cur = min(2.5, g_cur * 1.15)
            elif ratio < 0.5:
                g_cur = max(gamma, g_cur / 1.15)
        prev = conf
        per_it = float(np.mean(t_it[-3:]))
        left_its = max(1.0, (end_t - used) / max(per_it, 1e-3))
        need = (beta_end / beta) ** (1.0 / left_its) if beta < beta_end else 1.0
        beta = min(beta_max, beta * max(g_cur, need))
    st0 = r.stats()
    pose0 = dict(w.pose)
    m, nb = C.legalize_parts()
    ph.sync()
    C.set_via(beta)
    alt = None
    if C.end_alt:
        # candidate A: keep the collapsed copper, re-route only the conflicted nets hard
        # (Router.legalize); jc always throws it away and negotiates again from scratch,
        # which on paw3395 turns 0 open (18 conflicting cells) into 8-10 open connections
        snap0 = kit.snapshot(list(w.net_pins))
        moved_p = [q for q in w.pose if pose0.get(q) != w.pose[q]]
        for n in kit.part_nets(moved_p):  # copper of moved parts no longer meets its pads
            r.rip(n)
            r.route_net(n)
        r.legalize(list(w.net_pins))
        alt = (kit.total_cost(), kit.snapshot(list(w.net_pins)), r.stats())
        kit.restore(snap0)
    r.pathfinder(iters=20, pres0=max(0.5, min(beta, 4.0)), pres_mul=1.6)
    if any(r.unrouted.values()):
        # jc re-runs PathFinder from scratch here and keeps the result even when it leaves
        # more connections open (BUGS.md 6); guard: keep the better of the two
        snap = kit.snapshot(list(w.net_pins)) if C.guard else None
        c0 = kit.total_cost()
        r.pathfinder(iters=15, log=None)
        if snap is not None and kit.total_cost() > c0 + 1e-6:
            kit.restore(snap)
    if alt is not None:
        if alt[0] < kit.total_cost() - 1e-6:
            log(f"jc2 end_alt: kept collapsed copper + legalize {alt[2]} over pathfinder {r.stats()}")
            kit.restore(alt[1])
        else:
            log(f"jc2 end_alt: pathfinder {r.stats()} over collapsed copper + legalize {alt[2]}")
    log(f"jc2 end: beta={beta:.3g} its={it} collapsed {st0} -> legalized {m}/{nb} parts, "
        f"pathfinder {r.stats()}")
    return it, beta, st0


def jc2(world, seed=0, budget=300, log=print, gamma=1.35, beta0=0.05, beta_end=60.0, beta_max=500.0,
        polish=0.15, first=0.35, restart="scratch", perturb_k=0.25, beta_p=0.3, clean=0,
        clean_frac=0.03, clean_via=8.0, via_trade=3.0, complete=0, complete_frac=0.1, stall=0, fill=0,
        **kw):
    log0 = log

    def log(msg):  # phase lines also to stderr: the harness keeps them in adapter.log
        log0(msg)
        if msg.startswith(("jc2 ", "anneal_phys ", "  no legal", "  repair_phys done")):
            print(msg, file=sys.stderr, flush=True)

    C = Collapse2(world, seed, budget, log, **kw)
    w, r, kit, ph = world, C.r, C.kit, C.ph
    clock = C.clock
    # the end passes take their time out of the polish share, not out of the restarts:
    # reserving it up front cost a restart on large boards, and on olimex the restart is
    # what finds the low-physics placement (BUGS.md 10)
    run_end = budget * (1 - polish)
    best = None
    k = 0
    gammas = [gamma, gamma * 0.9, gamma * 1.2, gamma * 0.8, gamma * 1.4]
    t_run = None
    runs = []
    nmov = len(kit.movable())
    filled = False
    while True:
        t0 = budget - clock.left()
        start = None
        if k > 0:
            short = t_run is not None and run_end - t0 < 1.1 * t_run
            # fill: the time left after the last whole run goes to one perturbed resume
            # from the best state instead of to the polish (jc gives it to the polish)
            if t_run is None or (short and not (fill and run_end - t0 > 0.3 * t_run and not filled)):
                break
            C.rng = random.Random(seed * 1000 + k)
            if short:
                filled = True
            if best is not None and ((restart == "perturb" and k % 2 == 0) or short):
                _restore(C, best[1])
                kk = max(1, int(round(perturb_k * nmov))) if perturb_k < 1 else int(perturb_k)
                hot = perturb(C, kk)
                log(f"jc2 perturb from run {best[2]}: {[w.parts[q].ref for q in hot]}")
                start = "resume"
            else:
                J._reset(C)
        C.trace = []
        g = gammas[k % len(gammas)]
        it, beta, st0 = collapse_run(C, min(run_end - t0, budget * first) * 0.85, max(1.02, g),
                                     beta_p if start else beta0, beta_end, beta_max, log, start=start,
                                     stall=stall)
        t_run = budget - clock.left() - t0
        st = r.stats()
        cost = kit.total_cost() + C.phys_w * ph.total()
        bad = C.illegal_parts() if C.legal_first else []
        if bad:
            # jc ranks restarts by routed cost + physics only, so a run whose legalization
            # failed (parts left overlapping) can win (BUGS.md 9); an illegal part costs
            # more than any routing difference
            cost += 1.0e6 * len(bad)
            log(f"jc2 run {k}: {len(bad)} parts still illegal: {[w.parts[q].ref for q in bad]}")
        log(f"jc2 run {k} ({start or 'lift'}): gamma={g:.2f} its={it} {st} hpwl={w.hpwl():.1f} "
            f"phys={ph.total():.2f} cost={cost:.1f} t_run={t_run:.1f}")
        runs.append(dict(k=k, start=start or "lift", its=it, beta=round(beta, 3), cost=round(cost, 2),
                         collapsed_vias=st0["vias"], **st))
        if best is None or cost < best[0]:
            best = (cost, _state(C), k)
        k += 1
    if best[2] != k - 1:
        _restore(C, best[1])
    else:
        w.hist[:] = best[1][2]
        C.hist_c[:] = best[1][3]
    r.via_cost = C.via0
    r.legalize(list(w.net_pins))
    log(f"jc2 collapsed: best run {best[2]} of {k} {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f} "
        f"t={budget - clock.left():.1f} runs={runs}")
    if complete and any(r.unrouted.values()):
        C.complete(Clock(max(1.0, min(clock.left(), budget * complete_frac))))
    if polish > 0 and clock.left() > 2:
        pol = clock.left() - (budget * clean_frac if clean else 0)
        st_pre = _state(C) if C.guard else None
        c_pre = kit.total_cost() + C.phys_w * ph.total()
        r = MP.anneal_phys(w, seed=seed, budget=max(1.0, pol), log=log, phys_w=C.phys_w, router=r)
        c_post = kit.total_cost() + C.phys_w * ph.total()
        # anneal_phys ends with an unguarded PathFinder that can drop nets (BUGS.md 6)
        if st_pre is not None and c_post > c_pre + 1e-6:
            log(f"jc2 polish rejected: cost {c_pre:.1f} -> {c_post:.1f} {r.stats()}")
            _restore(C, st_pre)
        log(f"jc2 polished: {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f}")
    if complete and any(r.unrouted.values()) and clock.left() > 1:
        C.complete(Clock(max(1.0, clock.left() * 0.5)), repair_frac=0.0)
    if clean:
        C.via_cleanup(Clock(max(1.0, clock.left())), via_mm=clean_via, via_trade=via_trade)
    log(f"jc2 done: {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f} t={budget - clock.left():.1f}")
    return r


def _v(name, **fixed):
    def f(world, **kw):
        for a, b in fixed.items():
            kw.setdefault(a, b)
        return jc2(world, **kw)
    f.__name__ = name
    f.__doc__ = f"jc2 with {fixed}"
    f.fixed = fixed
    return f


# ablation arms (phys_w=2 physics objective; append `_lv` for length + vias, phys_w=0)
jc2_base = _v("jc2_base")                                   # engine reconcile only
jc2_via = _v("jc2_via", via_beta=1.0)
jc2_viap = _v("jc2_viap", via_part=1.0)
jc2_clean = _v("jc2_clean", clean=1)
jc2_comp = _v("jc2_comp", complete=1)
jc2_pert = _v("jc2_pert", restart="perturb")
jc2_stall = _v("jc2_stall", stall=4)
jc2_endalt = _v("jc2_endalt", end_alt=1)
jc2_fill = _v("jc2_fill", fill=1)
jc2_mp = _v("jc2_mp", minplus_w=0.5, mp_from_beta=1.0)      # min-plus only late (vias appear at beta > 1)
jc2_mp1 = _v("jc2_mp1", minplus_w=1.0)
# combinations (chosen from the dev6 screen): guard + stall + completion + via schedule + clean-up
FIX = dict(stall=4, complete=1, via_beta=1.0, clean=1)
jc2_fix = _v("jc2_fix", **FIX)
jc2_fixp = _v("jc2_fixp", restart="perturb", **FIX)
jc2_fixmp = _v("jc2_fixmp", minplus_w=0.5, mp_from_beta=1.0, **FIX)
jc2_all = _v("jc2_all", via_beta=1.0, clean=1, complete=1, restart="perturb")
for _n in list(globals()):
    if _n.startswith("jc2_") and callable(globals()[_n]):
        globals()[_n + "_lv"] = _v(_n + "_lv", phys_w=0.0, **globals()[_n].fixed)
