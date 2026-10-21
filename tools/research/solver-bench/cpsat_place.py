# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CP-SAT PCB placement micro-benchmark.

Model: integer grid (grid_mm), 4-way rotation (one-hot literals), keep-outs as fixed boxes in
the same NoOverlap2D, hard decap proximity (L1 diamond between decap pin and IC VDD pin, linear),
pin-level HPWL objective via min/max equalities. Optional 2-sided placement.

Rotation encodings:
  var  : one interval per comp with variable size W in {w,h} (allowed assignments with 'swapped')
  opt2 : two optional fixed-size intervals per comp (unrotated / rotated), presence = swapped

Usage: python cpsat_place.py N GRID_MM TIME_S [--mode opt|feas] [--rot var|opt2|none]
                             [--sides 1|2] [--workers 4] [--seed 0] [--nodecap] [--pack-subsolver]
Prints one JSON line with timing/objective trajectory.
"""
import argparse
import json
import math
import time

from ortools.sat.python import cp_model
from ortools.sat.python.cp_model import Domain

from pcbgen import make_instance


def rot_offsets(fp, k, g):
    """Pin offsets (grid units) relative to the bottom-left corner of the courtyard for rotation k*90."""
    w, h = (fp.w, fp.h) if k % 2 == 0 else (fp.h, fp.w)
    W, H = math.ceil(w / g), math.ceil(h / g)
    out = []
    for (dx, dy) in fp.pins:
        if k == 0:
            rx, ry = dx, dy
        elif k == 1:
            rx, ry = -dy, dx
        elif k == 2:
            rx, ry = -dx, -dy
        else:
            rx, ry = dy, -dx
        out.append((round(W / 2 + rx / g), round(H / 2 + ry / g)))
    return W, H, out


def build(inst, g, rot="var", sides=1, decap=True, objective=True):
    m = cp_model.CpModel()
    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    V = {}
    xi = {s: [] for s in range(sides)}
    yi = {s: [] for s in range(sides)}
    pinX, pinY = {}, {}
    for c in inst.comps:
        fp = c.fp
        dims = [rot_offsets(fp, k, g) for k in range(4)]
        W0, H0 = dims[0][0], dims[0][1]
        x = m.new_int_var(0, BW - min(W0, H0), f"x{c.id}")
        y = m.new_int_var(0, BH - min(W0, H0), f"y{c.id}")
        if rot == "none":
            r = [m.new_constant(1), m.new_constant(0), m.new_constant(0), m.new_constant(0)]
            sw = None
        else:
            r = [m.new_bool_var(f"r{c.id}_{k}") for k in range(4)]
            m.add_exactly_one(r)
            sw = m.new_bool_var(f"sw{c.id}")
            m.add(sw == r[1] + r[3])
        if sides == 2:
            top = m.new_bool_var(f"top{c.id}")
            pres = {0: True, 1: True} if fp.tht else {0: top, 1: ~top}
        else:
            top = None
            pres = {0: True}
        V[c.id] = dict(x=x, y=y, r=r, sw=sw, top=top)

        def present(lit_a, lit_b):
            # returns literal list for enforcement (AND of rotation-presence and side-presence)
            lits = [l for l in (lit_a, lit_b) if l is not True and l is not None]
            if not lits:
                return True
            if len(lits) == 1:
                return lits[0]
            b = m.new_bool_var("")
            m.add_bool_and(lits).only_enforce_if(b)
            m.add_bool_or([~l for l in lits]).only_enforce_if(~b)
            return b

        for s in pres:
            if rot == "none" or W0 == H0:
                ex = x + W0
                ey = y + H0
                m.add(ex <= BW); m.add(ey <= BH)
                p = present(pres[s], None)
                if p is True:
                    xi[s].append(m.new_fixed_size_interval_var(x, W0, ""))
                    yi[s].append(m.new_fixed_size_interval_var(y, H0, ""))
                else:
                    xi[s].append(m.new_optional_fixed_size_interval_var(x, W0, p, ""))
                    yi[s].append(m.new_optional_fixed_size_interval_var(y, H0, p, ""))
            elif rot == "var":
                Wv = m.new_int_var_from_domain(Domain.from_values([W0, H0]), "")
                Hv = m.new_int_var_from_domain(Domain.from_values([W0, H0]), "")
                m.add_allowed_assignments([Wv, Hv, sw], [(W0, H0, 0), (H0, W0, 1)])
                ex = m.new_int_var(0, BW, ""); ey = m.new_int_var(0, BH, "")
                p = present(pres[s], None)
                if p is True:
                    xi[s].append(m.new_interval_var(x, Wv, ex, ""))
                    yi[s].append(m.new_interval_var(y, Hv, ey, ""))
                else:
                    xi[s].append(m.new_optional_interval_var(x, Wv, ex, p, ""))
                    yi[s].append(m.new_optional_interval_var(y, Hv, ey, p, ""))
            else:  # opt2
                for (ww, hh, lit) in ((W0, H0, ~sw), (H0, W0, sw)):
                    m.add(x + ww <= BW).only_enforce_if(lit)
                    m.add(y + hh <= BH).only_enforce_if(lit)
                    p = present(pres[s], lit)
                    xi[s].append(m.new_optional_fixed_size_interval_var(x, ww, p, ""))
                    yi[s].append(m.new_optional_fixed_size_interval_var(y, hh, p, ""))
        for pi in range(len(fp.pins)):
            pinX[(c.id, pi)] = x + sum(r[k] * dims[k][2][pi][0] for k in range(4))
            pinY[(c.id, pi)] = y + sum(r[k] * dims[k][2][pi][1] for k in range(4))
    # keep-outs on every side
    for (kx, ky, kw, kh) in inst.keepouts:
        X0, Y0 = math.floor(kx / g), math.floor(ky / g)
        X1, Y1 = math.ceil((kx + kw) / g), math.ceil((ky + kh) / g)
        X1, Y1 = min(X1, BW), min(Y1, BH)
        for s in range(sides):
            xi[s].append(m.new_fixed_size_interval_var(X0, X1 - X0, ""))
            yi[s].append(m.new_fixed_size_interval_var(Y0, Y1 - Y0, ""))
    for s in range(sides):
        m.add_no_overlap_2d(xi[s], yi[s])
    if decap:
        for (cc, cp, ic, ip, dmax) in inst.decaps:
            D = math.floor(dmax / g)
            dx = pinX[(cc, cp)] - pinX[(ic, ip)]
            dy = pinY[(cc, cp)] - pinY[(ic, ip)]
            for sx in (1, -1):
                for sy in (1, -1):
                    m.add(sx * dx + sy * dy <= D)
            if sides == 2:
                m.add(V[cc]["top"] == V[ic]["top"])
    obj_terms = []
    if objective:
        for net in inst.nets:
            xs = [pinX[p] for p in net]; ys = [pinY[p] for p in net]
            if len(net) == 2:
                # |dx| + |dy| for 2-pin nets
                ax = m.new_int_var(0, BW, ""); ay = m.new_int_var(0, BH, "")
                m.add_abs_equality(ax, xs[0] - xs[1]); m.add_abs_equality(ay, ys[0] - ys[1])
                obj_terms += [ax, ay]
            else:
                a = m.new_int_var(0, BW, ""); b = m.new_int_var(0, BW, "")
                c_ = m.new_int_var(0, BH, ""); d = m.new_int_var(0, BH, "")
                m.add_max_equality(a, xs); m.add_min_equality(b, xs)
                m.add_max_equality(c_, ys); m.add_min_equality(d, ys)
                obj_terms += [a - b, c_ - d]
        m.minimize(sum(obj_terms))
    return m, V


class Traj(cp_model.CpSolverSolutionCallback):
    def __init__(self, t0):
        super().__init__()
        self.t0 = t0
        self.pts = []

    def on_solution_callback(self):
        self.pts.append((round(time.time() - self.t0, 3), self.objective_value))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int); ap.add_argument("grid", type=float); ap.add_argument("time", type=float)
    ap.add_argument("--mode", default="opt"); ap.add_argument("--rot", default="var")
    ap.add_argument("--sides", type=int, default=1); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--nodecap", action="store_true")
    ap.add_argument("--util", type=float, default=0.45)
    ap.add_argument("--pack-subsolver", action="store_true")
    a = ap.parse_args()
    inst = make_instance(a.n, seed=a.seed, util=a.util)
    t0 = time.time()
    m, V = build(inst, a.grid, rot=a.rot, sides=a.sides, decap=not a.nodecap, objective=(a.mode == "opt"))
    tb = time.time() - t0
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = a.time
    s.parameters.num_workers = a.workers
    s.parameters.random_seed = a.seed
    if a.pack_subsolver:
        # OR-Tools >= 9.15: solver.parameters is a pybind11 object; the protobuf SatParameters used in
        # older docs (sat_parameters_pb2) is rejected by subsolver_params.append()
        from ortools.sat.python import cp_model_helper
        p = cp_model_helper.SatParameters()
        p.name = "pack"
        p.use_area_energetic_reasoning_in_no_overlap_2d = True
        p.use_energetic_reasoning_in_no_overlap_2d = True
        p.use_timetabling_in_no_overlap_2d = True
        p.max_pairs_pairwise_reasoning_in_no_overlap_2d = 5000
        s.parameters.subsolver_params.append(p)
        s.parameters.extra_subsolvers.append("pack")
    if a.mode == "feas":
        s.parameters.stop_after_first_solution = True
    t1 = time.time()
    cb = Traj(t1)
    st = s.solve(m, cb)
    ts = time.time() - t1
    res = dict(n=a.n, grid_mm=a.grid, mode=a.mode, rot=a.rot, sides=a.sides, decap=not a.nodecap,
               util=a.util, seed=a.seed, workers=a.workers, pack=a.pack_subsolver,
               board_mm=inst.meta["board_mm"], nets=inst.meta["n_nets"], decaps=inst.meta["n_decaps"],
               n_vars=len(m.proto.variables), n_cons=len(m.proto.constraints),
               build_s=round(tb, 2), solve_s=round(ts, 2), status=s.status_name(st),
               first_sol_s=cb.pts[0][0] if cb.pts else None,
               n_sols=len(cb.pts))
    if a.mode == "opt" and cb.pts:
        res["obj_mm"] = round(s.objective_value * a.grid, 1)
        res["bound_mm"] = round(s.best_objective_bound * a.grid, 1)
        res["first_obj_mm"] = round(cb.pts[0][1] * a.grid, 1)
        # objective at checkpoints
        for T in (5, 15, 30, 60, 120, 300):
            if T <= a.time:
                vals = [o for (t, o) in cb.pts if t <= T]
                res[f"obj@{T}s"] = round(min(vals) * a.grid, 1) if vals else None
    print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
