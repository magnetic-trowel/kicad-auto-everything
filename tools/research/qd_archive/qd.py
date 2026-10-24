# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Quality-diversity archive over joint-collapse boards (catalog idea 16, tag `qd`).

jc (tools/research/collapse_joint/jc.py) spends ~85 % of its budget on restarts of the
whole lift + continuation and keeps the single best end state. Here the same budget
feeds a MAP-Elites archive instead:

    init       n_init plain jc continuations from the lift (jc.collapse_once)
    loop       pick a parent elite (uniform over occupied cells), restore its poses,
               mutate a few parts, then a *short* continuation from that placement
               (no lift: beta starts at beta_m, the mutation strength), legalize, route
    archive    cell = binned behaviour descriptors (relative to the first run), elite =
               lowest objective in the cell; objective = routed cost + phys_w * physics
    end        best elite by the objective, Router.legalize, anneal_phys polish (as jc)

Descriptors (option desc, two names):
    spread   RMS distance of movable part origins from their centroid (placement shape)
    vias     routed via count
    len      routed length (mm)
    phys     fast physics total (kae place terms; vias on boards without structures)
    hpwl     half-perimeter wire length
    none     single cell: the archive degenerates to elitist iterated local search
Mutation operators: `shift` (k nearest parts around a random part moved up to 3 mm,
rotated with p 0.3), `rot` (k random parts rotated), `swap` (two parts exchange origins).

Plug-ins for run.py: qd (desc spread,vias), qd_po (desc phys,len), qd1 (desc none),
qd_lv / qd1_lv (phys_w = 0). Options via --opt key=value; qd_dir=PATH writes the
archive of every board as JSON.
"""
import json
import math
import os
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")
sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/collapse_joint")

import methods_phys as MP  # noqa: E402
from jc import Collapse, _reset, collapse_once  # noqa: E402

ROOT = Path("/home/user/kicad-auto-everything")


def _board_id(world):
    """Task id from the input path (kae-v7 or kae-work task trees)."""
    parts = Path(world.data.get("path", "board")).parts
    for s in reversed(parts):
        if any((ROOT / d / "tasks" / s).is_dir() for d in ("kae-v7", "kae-work")):
            return s
    return Path(world.data.get("path", "board")).parent.name


# ------------------------------------------------------------------ continuation
def continue_once(C, run_budget, beta0, gamma, beta_end, beta_max, log):
    """jc.collapse_once without the lift: the continuation starts from the current
    placement at beta0 (wire and part history cleared). Returns (iterations, beta)."""
    w, r, kit, ph = C.w, C.r, C.kit, C.ph
    clock = C.clock
    end_t = clock.budget - clock.left() + run_budget
    mov = [q for q in kit.movable() if q in w.pose]
    w.hist[:] = 0
    C.hist_c[:] = 0
    C.stuck.clear()
    r.rip_all()
    r.unrouted.clear()
    ph.sync()
    beta, g_cur, prev, it, zero, t_it = beta0, gamma, None, 0, 0, []
    while True:
        it += 1
        t0 = clock.budget - clock.left()
        C.route_all(beta)
        moved = 0
        CT, CV, per = C.route_maps()
        order = list(mov)
        C.rng.shuffle(order)
        for pi in order:
            moved += C.best_response(pi, beta, CT, CV, per)
        C.hist_c += C.hist_inc * (w.court > 1)
        conf = C.overlap_cells() + C.wire_conflicts()
        used = clock.budget - clock.left()
        t_it.append(used - t0)
        zero = zero + 1 if conf == 0 else 0
        if conf == 0 and (moved == 0 or zero >= 2):
            break
        if used > end_t:
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
    C.legalize_parts()
    ph.sync()
    r.pathfinder(iters=20, pres0=max(0.5, min(beta, 4.0)), pres_mul=1.6)
    if any(r.unrouted.values()):
        r.pathfinder(iters=15, log=None)
    return it, beta


# ------------------------------------------------------------------ mutation
def mutate(C, rng, k_frac=0.15, shift_mm=3.0):
    """Perturb a few movable parts in place (overlaps allowed; the continuation repairs).
    Returns a short description of the operator."""
    w, kit, ph = C.w, C.kit, C.ph
    mov = [q for q in kit.movable() if q in w.pose]
    if not mov:
        return "none"
    kmax = max(2, int(round(k_frac * len(mov))))
    k = min(len(mov), rng.choice([1, 2, 3, kmax]))
    u = rng.random()
    if u < 0.45:
        act = [q for q in mov if q in ph.active] if C.phys_w > 0 else []
        seed = rng.choice(act) if act and rng.random() < 0.3 else rng.choice(mov)
        sx, sy, _ = w.pose[seed]
        near = sorted(mov, key=lambda q: abs(w.pose[q][0] - sx) + abs(w.pose[q][1] - sy))[:k]
        R = max(2, int(shift_mm / w.g))
        for q in near:
            cx, cy, ri = w.pose[q]
            if rng.random() < 0.3:
                ri = rng.choice([x for x in range(4) if x != ri])
            nx = min(max(cx + rng.randint(-R, R), 0), w.W - 1)
            ny = min(max(cy + rng.randint(-R, R), 0), w.H - 1)
            if not C.inside_map(q, ri)[ny, nx]:
                ins = np.argwhere(C.inside_map(q, ri))
                if not len(ins):
                    continue
                j = int(np.argmin(np.abs(ins[:, 0] - ny) + np.abs(ins[:, 1] - nx)))
                ny, nx = int(ins[j, 0]), int(ins[j, 1])
            w.unplace(q)
            w.place(q, nx, ny, ri)
        op = f"shift{k}"
    elif u < 0.75:
        for q in rng.sample(mov, k):
            cx, cy, ri = w.pose[q]
            ri2 = rng.choice([x for x in range(4) if x != ri])
            if C.inside_map(q, ri2)[cy, cx]:
                w.unplace(q)
                w.place(q, cx, cy, ri2)
        op = f"rot{k}"
    else:
        if len(mov) < 2:
            return "none"
        n = 0
        for _ in range(max(1, k // 2)):
            a, b = rng.sample(mov, 2)
            pa, pb = w.pose[a], w.pose[b]
            if C.inside_map(a, pa[2])[pb[1], pb[0]] and C.inside_map(b, pb[2])[pa[1], pa[0]]:
                w.unplace(a)
                w.unplace(b)
                w.place(a, pb[0], pb[1], pa[2])
                w.place(b, pa[0], pa[1], pb[2])
                n += 1
        op = f"swap{n}"
    ph.sync()
    return op


# ------------------------------------------------------------------ archive
def descriptors(C):
    w, r, kit, ph = C.w, C.r, C.kit, C.ph
    st = r.stats()
    mov = [q for q in kit.movable() if q in w.pose]
    if mov:
        xy = np.array([w.xy(*w.pose[q][:2]) for q in mov], float)
        spread = float(np.sqrt(((xy - xy.mean(0)) ** 2).sum(1).mean()))
    else:
        spread = 0.0
    phys = ph.total()
    return dict(spread=spread, vias=float(st["vias"]), len=float(st["length_mm"]),
                phys=phys if ph.active else float(st["vias"]), hpwl=float(w.hpwl()),
                unrouted=int(st["unrouted"]), overlap=int(C.overlap_cells()))


WIDTH = dict(spread=0.06, vias=0.15, len=0.05, phys=0.12, hpwl=0.05)


def cell_of(d, ref, names, K=10):
    if names == ["none"]:
        return (0,)
    out = []
    for nm in names:
        x, x0 = d[nm], ref[nm]
        eps = 1.0 if nm in ("vias", "phys") else 1e-3
        b = math.log((x + eps) / (x0 + eps)) / WIDTH[nm]
        out.append(int(max(-K, min(K, round(b)))))
    return tuple(out)


class Archive:
    def __init__(self, names):
        self.names = names
        self.ref = None
        self.cells = {}
        self.log = []

    def add(self, cost, d, state, meta):
        if self.ref is None:
            self.ref = dict(d)
        key = cell_of(d, self.ref, self.names)
        old = self.cells.get(key)
        new_cell = old is None
        better = new_cell or cost < old["cost"] - 1e-9
        if better:
            self.cells[key] = dict(cost=cost, d=d, state=state, meta=meta, key=key)
        return key, new_cell, better

    def best(self, f=None):
        f = f or (lambda e: e["cost"])
        return min(self.cells.values(), key=f)


def _save(C, cost):
    w, kit = C.w, C.kit
    return (dict(w.pose), kit.snapshot(list(w.net_pins)))


def _load(C, state):
    w, r, kit, ph = C.w, C.r, C.kit, C.ph
    mov = kit.movable()
    for q in [q for q in mov if q in w.pose]:
        w.unplace(q)
    r.rip_all()
    r.unrouted.clear()
    for q, p in state[0].items():
        if q in mov:
            w.place(q, *p)
    kit.restore(state[1])
    ph.sync()


def qd(world, seed=0, budget=300, log=print, desc="spread,vias", n_init=2, polish=0.15,
       gamma=1.35, beta0=0.05, beta_end=60.0, beta_max=500.0, first=0.35, mut_cap=0.15,
       beta_m=(0.3, 6.0), illegal_pen=0.0, select="uniform", p_fresh=0.0, qd_dir=None, **kw):
    """MAP-Elites over joint-collapse end states; see the module docstring."""
    C = Collapse(world, seed, budget, log, **kw)
    w, r, kit, ph = world, C.r, C.kit, C.ph
    clock = C.clock
    rng = random.Random(seed * 7919 + 17)
    names = [s.strip() for s in str(desc).split(",") if s.strip()]
    A = Archive(names)
    run_end = budget * (1 - polish)
    gammas = [gamma, gamma * 0.9, gamma * 1.2, gamma * 0.8, gamma * 1.4]
    hist = []
    t_init = t_mut = None
    k = 0

    def evaluate(op, parent, t_c, it, beta):
        d = descriptors(C)
        cost = kit.total_cost() + C.phys_w * ph.total() + illegal_pen * d["overlap"]
        gbest = min((e["cost"] for e in A.cells.values()), default=math.inf)
        key, new_cell, better = A.add(cost, d, _save(C, cost), dict(op=op, parent=parent, k=k))
        hist.append(dict(k=k, op=op, parent=parent, t=round(t_c, 2), its=it, beta=round(beta, 3),
                         cost=round(cost, 2), key=list(key), new_cell=new_cell, improved=better,
                         gbest=cost < gbest - 1e-9, **{a: round(b, 3) for a, b in d.items()}))
        log(f"qd cand {k} op={op} parent={parent} cost={cost:.1f} cell={key} new={new_cell} "
            f"better={better} gbest={cost < gbest - 1e-9} cells={len(A.cells)} {r.stats()} "
            f"phys={ph.total():.2f} t_c={t_c:.1f} its={it}")

    while True:
        t0 = budget - clock.left()
        fresh = k < n_init or (p_fresh > 0 and rng.random() < p_fresh)
        if fresh and k > 0 and (t_init is None or run_end - t0 < 1.1 * t_init):
            if k < n_init:
                break
            fresh = False  # no room for a restart: a (shorter) mutation may still fit
        if fresh:
            if k > 0:
                _reset(C)
            C.rng = random.Random(seed * 1000 + k)
            it, beta = collapse_once(C, min(run_end - t0, budget * first) * 0.85,
                                     max(1.02, gammas[k % len(gammas)]), beta0, beta_end, beta_max, False,
                                     lambda *a: None)
            t_c = budget - clock.left() - t0
            t_init = t_c if t_init is None else max(t_init, t_c)
            evaluate("init" if k < n_init else "fresh", None, t_c, it, beta)
        else:
            est = t_mut if t_mut is not None else 0.5 * t_init
            if run_end - t0 < 1.1 * est:
                break
            cells = list(A.cells.values())
            if select == "tournament" and len(cells) > 1:
                par = min(rng.sample(cells, 2), key=lambda e: e["cost"])
            else:
                par = rng.choice(cells)
            _load(C, par["state"])
            C.rng = random.Random(seed * 1000 + k)
            op = mutate(C, rng)
            bm = math.exp(rng.uniform(math.log(beta_m[0]), math.log(beta_m[1])))
            it, beta = continue_once(C, min(run_end - t0, budget * mut_cap), bm,
                                     max(1.02, gamma * rng.uniform(0.85, 1.3)), beta_end, beta_max, log)
            t_c = budget - clock.left() - t0
            t_mut = t_c if t_mut is None else 0.7 * t_mut + 0.3 * t_c
            evaluate(f"{op}@b{bm:.2g}", list(par["key"]), t_c, it, beta)
        k += 1

    best = A.best()
    _load(C, best["state"])
    r.legalize(list(w.net_pins))
    # diversity: what the archive holds beyond the objective's pick
    by_len = A.best(lambda e: e["d"]["len"] + 2.0 * e["d"]["vias"] + 1e3 * e["d"]["unrouted"])
    by_phys = A.best(lambda e: (e["d"]["unrouted"], e["d"]["phys"])) if ph.active else None
    log(f"qd done: {k} candidates, {len(A.cells)} cells, best cell {best['key']} cost={best['cost']:.1f} "
        f"{r.stats()} phys={ph.total():.2f} t={budget - clock.left():.1f}")
    qd_dir = qd_dir or os.environ.get("QD_DIR")
    out = dict(board=_board_id(w), seed=seed, desc=names, phys_w=C.phys_w, ref=A.ref, n=k,
               cells=[dict(key=list(e["key"]), cost=round(e["cost"], 3), meta=e["meta"],
                           **{a: round(b, 3) for a, b in e["d"].items()}) for e in A.cells.values()],
               best=list(best["key"]), by_len=list(by_len["key"]),
               by_phys=list(by_phys["key"]) if by_phys else None, hist=hist)
    # the kaebench sandbox keeps only stdout (adapter.log): one line, read by archive_stats.py
    print("QDARCHIVE " + json.dumps(out), flush=True)
    if qd_dir:
        Path(qd_dir).mkdir(parents=True, exist_ok=True)
        (Path(qd_dir) / f"{_board_id(w)}.s{seed}.json").write_text(json.dumps(out))
    if polish > 0 and clock.left() > 2:
        r = MP.anneal_phys(w, seed=seed, budget=max(1.0, clock.left()), log=log, phys_w=C.phys_w, router=r)
        log(f"qd polished: {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f}")
    return r


def qd_po(world, **kw):
    """Archive binned by the two objective terms (fast physics, routed length)."""
    kw.setdefault("desc", "phys,len")
    return qd(world, **kw)


def qd1(world, **kw):
    """Single-cell archive: elitist mutation + short continuation (iterated local search)."""
    kw.setdefault("desc", "none")
    return qd(world, **kw)


def qdh(world, **kw):
    """Hybrid: half the candidates are fresh jc continuations from the lift (as jc's
    restarts), half mutate an elite; all enter the archive."""
    kw.setdefault("p_fresh", 0.5)
    return qd(world, **kw)


def qdh_lv(world, **kw):
    kw["phys_w"] = 0.0
    return qdh(world, **kw)


def qd_lv(world, **kw):
    kw["phys_w"] = 0.0
    return qd(world, **kw)


def qd1_lv(world, **kw):
    kw["phys_w"] = 0.0
    return qd1(world, **kw)


def qd_po_lv(world, **kw):
    kw["phys_w"] = 0.0
    return qd_po(world, **kw)
