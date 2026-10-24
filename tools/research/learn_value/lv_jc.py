# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Learned value of partial boards (docs/ideas/original/joint-pnr.md, idea 32) on joint
collapse (tools/research/collapse_joint, frozen snapshot kae-work/jc-snap/jc_v3.py).

    jc_log      jc with probes: after the lift and after every beta iteration of every
                restart, cheap features of the partial board are appended to a JSONL file
                (env LV_LOG or --opt log_path=...), and the restart's end state (routed
                cost + phys_w * fast physics, the score jc keeps the best by) is appended
                when it finishes. No steering: the data generator.
    jc_value    jc whose restarts are steered by a value model (model_dir/opt): at probe
                checkpoints the model predicts the restart's final log cost; the restart is
                abandoned when the prediction exceeds the best finished restart by a margin,
                and the freed CPU goes to further restarts. jc_value_lv: phys_w = 0.
    jc_heur     the same rule with the heuristic predictor (current routed cost) instead
                of the model: the control for "learned beats heuristic".

The collapse itself is jc_v3's (Collapse, lift, best response, legalization); only the
iteration loop is re-written here (collapse_once with a hook) and the restart driver.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")  # sklearn/OpenMP: one thread (CPU budget, shared machine)
import importlib.util
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path("/home/user/kicad-auto-everything")
sys.path.insert(0, str(ROOT / "tools/research/pnr"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

_spec = importlib.util.spec_from_file_location("jc_v3", ROOT / "kae-work/jc-snap/jc_v3.py")
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)

import methods_phys as MP  # noqa: E402

RUN_CAP_S = 120 * 0.35  # jc's per-continuation cap at the evaluation budget (x 0.85 inside)


class Probe:
    """Cheap features of the current partial board (a few ms; its CPU is tracked so the
    data generator can subtract it from run times)."""

    def __init__(self, C):
        self.C = C
        w = C.w
        self.area = float(w.inside.sum()) * w.g * w.g
        self.terms = None
        try:
            sys.path.insert(0, str(ROOT / "tools/research/collapse_cplace"))
            from terms import CollapseTerms
            self.terms = CollapseTerms(w, w_fv=1.0, w_x=1.0, w_ovf=1.0)
        except Exception:  # pragma: no cover - terms are optional
            self.terms = None
        self.cpu = 0.0
        self.board = dict(area_mm2=round(self.area, 2), nets=len(w.net_pins),
                          parts=len(C.kit.movable()), unrouted_mm=C.kit.unrouted_mm,
                          layers=w.nl)

    def __call__(self, extra=None):
        t0 = time.process_time()
        C = self.C
        w, r, kit = C.w, C.r, C.kit
        st = r.stats()
        hist = w.hist.sum(0)
        ins = w.inside
        hv = hist[ins]
        f = dict(hpwl=w.hpwl(), phys=C.ph.total(), length=st["length_mm"], vias=st["vias"],
                 unrouted=st["unrouted"], conn=st["connections"], route_cost=kit.total_cost(),
                 hist_sum=float(hv.sum()), hist_nz=float((hv > 0).mean()) if hv.size else 0.0,
                 hist_max=float(hv.max()) if hv.size else 0.0,
                 hist_p99=float(np.percentile(hv, 99)) if hv.size else 0.0,
                 histc_sum=float(C.hist_c.sum()))
        if self.terms is not None:
            try:
                ev = self.terms.evaluate(dict(w.pose))
                f.update(fv=float(ev["fv"]), xings=float(ev["x"]), ovf=float(ev["ovf"]))
            except Exception:
                pass
        if extra:
            f.update(extra)
        self.cpu += time.process_time() - t0
        return f


def collapse_once_hooked(C, run_budget, gamma, beta0, beta_end, beta_max, hook, log):
    """jc_v3.collapse_once (not frozen) with hook(stage, it, info) after the lift and after
    every iteration; a True return abandons the run (returns None: no legalization)."""
    w, r, kit, ph = C.w, C.r, C.kit, C.ph
    clock = C.clock
    t_start = clock.budget - clock.left()
    end_t = t_start + run_budget
    C.lift([q for q in kit.movable() if q not in w.pose])
    mov = [q for q in kit.movable() if q in w.pose]
    ph.sync()
    ovc, wc = C.overlap_cells(), C.wire_conflicts()
    if hook("lift", 0, dict(beta=0.0, overlap=ovc, wire_conf=wc, moved=0, nets_bad=0,
                            t=clock.budget - clock.left() - t_start)):
        return None
    beta = beta0
    g_cur = gamma
    prev = None
    it = zero = 0
    t_it = []
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
        zero = zero + 1 if conf == 0 else 0
        done = (conf == 0 and (moved == 0 or zero >= 2)) or used > end_t
        if not done and hook("it", it, dict(beta=beta, overlap=ovc, wire_conf=wc, moved=moved,
                                            nets_bad=len(bad), t=used - t_start)):
            return None
        if done:
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
    m, nb = C.legalize_parts()
    ph.sync()
    r.pathfinder(iters=20, pres0=max(0.5, min(beta, 4.0)), pres_mul=1.6)
    if any(r.unrouted.values()):
        r.pathfinder(iters=15, log=None)
    return it, beta


class Logger:
    def __init__(self, path, meta):
        self.f = open(path, "a") if path else None
        self.meta = meta

    def write(self, **row):
        if self.f:
            self.f.write(json.dumps({**self.meta, **row}) + "\n")
            self.f.flush()


def _cur_time(clock):
    return clock.budget - clock.left()


def jc_driver(world, seed=0, budget=300, log=print, gamma=1.35, beta0=0.05, beta_end=60.0,
              beta_max=500.0, polish=0.15, first=0.35, run_cap=None, policy=None,
              log_path=None, tag="", max_consec=3, **kw):
    """jc_v3.jc (restarts, keep the best by routed cost + phys_w * fast physics, optional
    anneal_phys polish) with probes at every checkpoint and an optional `policy`:
    policy.start(board info), policy(stage, it, feats, best_cost) -> True to abandon."""
    C = J.Collapse(world, seed, budget, log, **kw)
    w, r, kit, ph = world, C.r, C.kit, C.ph
    clock = C.clock
    probe = Probe(C)
    bid = J._board_id(w)
    L = Logger(log_path or os.environ.get("LV_LOG"),
               dict(board=bid, seed=seed, phys_w=C.phys_w, tag=tag))
    L.write(kind="board", **probe.board)
    if policy is not None:
        policy.start(bid, probe.board, C.phys_w)
    run_end = budget * (1 - polish)
    cap = run_cap if run_cap is not None else budget * first
    best = None
    k = 0
    gammas = [gamma, gamma * 0.9, gamma * 1.2, gamma * 0.8, gamma * 1.4]
    t_full = None
    n_abort = 0
    lift_ref = {}
    consec = [0]  # restarts abandoned in a row; after max_consec the next one runs to the end

    while True:
        t0 = _cur_time(clock)
        if k > 0:
            if t_full is None or run_end - t0 < 1.1 * t_full:
                break
            J._reset(C)
            C.rng = random.Random(seed * 1000 + k)
        C.trace = []
        g = gammas[k % len(gammas)]
        cpu0 = probe.cpu
        best_cost = best[0] if best else None

        def hook(stage, it, info):
            feats = probe(dict(info, gamma=g, k=k, it=it, stage=stage))
            feats["t_run"] = _cur_time(clock) - t0 - (probe.cpu - cpu0)
            if stage == "lift":
                lift_ref.update(feats)
            L.write(kind="ck", **feats)
            if policy is None:
                return False
            stop = policy(stage, it, feats, lift_ref, best_cost) and consec[0] < max_consec
            if stop:
                log(f"lv run {k}: abandoned at {stage} it={it} t={feats['t_run']:.1f}")
            return stop

        res = collapse_once_hooked(C, min(run_end - t0, cap) * 0.85, max(1.02, g), beta0,
                                   beta_end, beta_max, hook, log)
        t_run = _cur_time(clock) - t0
        if res is None:
            n_abort += 1
            consec[0] += 1
            L.write(kind="abort", k=k, t_run=t_run)
            k += 1
            continue
        it, beta = res
        consec[0] = 0
        t_full = t_run
        st = r.stats()
        cost = kit.total_cost() + C.phys_w * ph.total()
        L.write(kind="end", k=k, gamma=g, its=it, beta=beta, cost=cost, t_run=t_run,
                t_probe=probe.cpu - cpu0, hpwl=w.hpwl(), phys=ph.total(),
                overlap=C.overlap_cells(), route_cost=kit.total_cost(), **st)
        log(f"lv run {k}: gamma={g:.2f} its={it} {st} cost={cost:.1f} t_run={t_run:.1f}")
        if policy is not None:
            policy.finished(k, cost)
        if best is None or cost < best[0]:
            best = (cost, dict(w.pose), kit.snapshot(list(w.net_pins)), k, w.hist.copy(), C.hist_c.copy())
        k += 1
    if best[3] != k - 1 or n_abort:
        mov = kit.movable()
        for q in [q for q in mov if q in w.pose]:
            w.unplace(q)
        r.rip_all()
        r.unrouted.clear()
        for q, p in best[1].items():
            if q in mov:
                w.place(q, *p)
        kit.restore(best[2])
        ph.sync()
    w.hist[:] = best[4]
    C.hist_c[:] = best[5]
    r.legalize(list(w.net_pins))
    L.write(kind="done", runs=k, aborted=n_abort, best_k=best[3], best_cost=best[0],
            t=_cur_time(clock), t_probe=probe.cpu)
    log(f"lv collapsed: best run {best[3]} of {k} ({n_abort} abandoned) {r.stats()} "
        f"t={_cur_time(clock):.1f} probe_cpu={probe.cpu:.1f}")
    if polish > 0 and clock.left() > 2:
        r = MP.anneal_phys(w, seed=seed, budget=max(1.0, clock.left()), log=log, phys_w=C.phys_w, router=r)
        log(f"lv polished: {r.stats()} hpwl={w.hpwl():.1f} phys={ph.total():.2f}")
    return r


# ------------------------------------------------------------------ plug-ins
def jc_log(world, **kw):
    """Data generator: no steering, no polish, per-run cap of the 120 s evaluation."""
    kw.setdefault("polish", 0.0)
    kw.setdefault("run_cap", RUN_CAP_S)
    return jc_driver(world, **kw)


def jc_value(world, model_dir=None, margin=None, **kw):
    from lv_policy import ValuePolicy
    pol = ValuePolicy(model_dir or os.environ.get("LV_MODEL", str(ROOT / "kae-work/learnv/model")),
                      margin=margin)
    kw.setdefault("run_cap", RUN_CAP_S * kw.get("budget", 120) / 120)
    return jc_driver(world, policy=pol, **kw)


def jc_value_lv(world, **kw):
    kw["phys_w"] = 0.0
    kw.setdefault("polish", 0.0)
    return jc_value(world, **kw)


def jc_heur(world, margin=None, **kw):
    from lv_policy import HeuristicPolicy
    kw.setdefault("run_cap", RUN_CAP_S * kw.get("budget", 120) / 120)
    return jc_driver(world, policy=HeuristicPolicy(margin=margin), **kw)


def jc_heur_lv(world, **kw):
    kw["phys_w"] = 0.0
    kw.setdefault("polish", 0.0)
    return jc_heur(world, **kw)
