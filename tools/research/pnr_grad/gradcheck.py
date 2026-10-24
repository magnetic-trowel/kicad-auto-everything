# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Direction test: do soft-routing gradients point somewhere better than HPWL gradients?

    python gradcheck.py EXTRACT.json [--steps 0.5,1,2] [--seed 0]

Start from the control placement (methods.seq: greedy + descent, then PathFinder). At that
placement compute, per movable part, three unit directions: -grad smooth HPWL, -grad soft
routed length (grad.SoftRouter: pin tensions + halo forces, final temperature) and a random
one. Move the part `step` mm along each (nearest legal origin, same rotation), re-route the
affected nets with the real router (Kit.reroute) and record the change of Kit.total_cost
(routed mm + 2 mm/via + a board perimeter per unrouted connection). Restore and repeat.
A direction that carries information should lower the real routed cost more often and by
more than the random one. One JSON line per board.
"""
import argparse
import json
import math
import random
import sys

import numpy as np

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")
sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr_grad")

import methods as M  # noqa: E402
from grad import Model, SoftRouter, bilinear_multi, halo_force, wa_wirelength  # noqa: E402
from placekit import Kit  # noqa: E402
from world import World  # noqa: E402


def directions(world, kit, mov, wb=4.0, T=0.5, gamma=0.3):
    poses = {pi: world.pose[pi] for pi in mov}
    for pi in mov:
        world.unplace(pi)
    model = Model(world, kit, mov)
    X = np.array([world.xy(*poses[pi][:2]) for pi in mov], float).reshape(-1, 2)
    PI = np.zeros((len(mov), 4))
    for m, pi in enumerate(mov):
        PI[m, poses[pi][2]] = 1.0
    P, mv = model.pins_xy(X, PI)
    pp = model.pin_part[mv]
    # smooth HPWL
    _, gP = wa_wirelength(model, P, gamma)
    gH = np.zeros((len(mov), 2))
    np.add.at(gH, pp, gP[mv])
    # soft routed length
    sr = SoftRouter(model)
    sr.update(X, PI, P, wb, T, 0.0)
    gP = np.zeros_like(P)
    uc, vc = model.to_c(P)
    if sr.edges:
        E_ = np.array(sr.edges)
        src = np.concatenate([E_[:, 0], E_[:, 1]])
        dst = np.concatenate([E_[:, 1], E_[:, 0]])
        _, du, dv = bilinear_multi(sr.fields, src, uc[dst], vc[dst])
        np.add.at(gP[:, 0], dst, 0.5 * du / model.G)
        np.add.at(gP[:, 1], dst, 0.5 * dv / model.G)
    gR = np.zeros((len(mov), 2))
    np.add.at(gR, pp, gP[mv])
    hx, _ = halo_force(model, X, PI, wb * model.G * sr.U, {n: wb * model.G * u for n, u in sr.Un.items()})
    gT = gR.copy()  # tension only
    gR += hx
    for pi in mov:
        world.place(pi, *poses[pi])
    return gH, gR, gT


def trial(world, kit, pi, vec, step):
    """Change of total cost when part pi moves step mm along vec (nearest legal origin)."""
    n = np.linalg.norm(vec)
    if n < 1e-9:
        return None
    cur = world.pose[pi]
    world.unplace(pi)
    L = kit.legal_map(pi, cur[2])
    tx = cur[0] - vec[0] / n * step / world.g
    ty = cur[1] - vec[1] / n * step / world.g
    yy, xx = np.nonzero(L)
    if not len(xx):
        world.place(pi, *cur)
        return None
    j = int(np.argmin((xx - tx) ** 2 + (yy - ty) ** 2))
    new = (int(xx[j]), int(yy[j]), cur[2])
    if new == cur:
        world.place(pi, *cur)
        return 0.0
    before = kit.total_cost()
    world.place(pi, *new)
    aff = kit.part_nets([pi]) | set(kit.conflicted_nets())
    snap = kit.snapshot(aff)
    kit.reroute(aff, iters=4)
    after = kit.total_cost()
    kit.restore(snap)
    world.unplace(pi)
    world.place(pi, *cur)
    return after - before


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extract")
    ap.add_argument("--steps", default="0.5,1,2")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    data = json.load(open(a.extract))
    world = World(data, g=0.1)
    r = M.seq(world, seed=a.seed, budget=120, log=lambda s: None)
    kit = Kit(world, r)
    base = kit.total_cost()
    mov = [pi for pi in kit.movable() if pi in world.pose and kit.part_nets([pi])]
    gH, gR, gT = directions(world, kit, mov)
    rng = np.random.default_rng(a.seed)
    out = {k: [] for k in ("hpwl", "route", "tension", "random")}
    for step in [float(s) for s in a.steps.split(",")]:
        for m, pi in enumerate(mov):
            ang = rng.uniform(0, 2 * math.pi)
            for k, v in (("hpwl", gH[m]), ("route", gR[m]), ("tension", gT[m]),
                         ("random", np.array([math.cos(ang), math.sin(ang)]))):
                d = trial(world, kit, pi, v, step)
                if d is not None:
                    out[k].append((step, m, d))
    res = dict(board=a.extract.split("/")[-1][:-5], base=round(base, 1), parts=len(mov))
    for k, v in out.items():
        d = np.array([x[2] for x in v]) if v else np.zeros(0)
        res[k] = dict(n=len(d), mean=round(float(d.mean()), 2) if len(d) else None,
                      improve=int((d < -1e-6).sum()), worse=int((d > 1e-6).sum()))
    # paired route vs hpwl (same part and step)
    hp = {(s, m): d for s, m, d in out["hpwl"]}
    rt = {(s, m): d for s, m, d in out["route"]}
    both = [k for k in hp if k in rt]
    res["route_better"] = sum(rt[k] < hp[k] - 1e-6 for k in both)
    res["hpwl_better"] = sum(hp[k] < rt[k] - 1e-6 for k in both)
    res["cos_route_hpwl"] = round(float(np.mean([np.dot(gH[m], gR[m]) / (np.linalg.norm(gH[m]) * np.linalg.norm(gR[m]) + 1e-12)
                                                 for m in range(len(mov))])), 3)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
