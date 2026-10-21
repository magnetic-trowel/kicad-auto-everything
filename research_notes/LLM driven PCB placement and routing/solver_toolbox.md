# Optimization Solver & Computational Geometry Toolbox for a Python PCB Placement + Routing Engine (LLM-callable, 20–1000 parts, 2–8 layers)

> Research notes, first pass 2026-10-20 (restricted network), deep pass later the same day with full network access and local micro-benchmarks.
>
> **Evidence tags** (after each finding):
> - **[P]** I read it in the primary source: the full paper PDF, official README, source code, or PyPI metadata.
> - **[S]** Only a search-engine snippet or aggregator page was seen.
> - **[M]** My own measurement in this session; scripts and raw results are listed in §1 under "Own micro-benchmarks".
>
> **Versions** are from PyPI JSON metadata (`https://pypi.org/pypi/<pkg>/json`) on 2026-10-20.
>
> **Benchmark machine:** 4 vCPU, 15 GB RAM, Python 3.13, OR-Tools 9.15.6755, Shapely 2.2.0, rtree 1.4.1, pyclipper 1.4.0, SciPy, NumPy 2.5.4. CP-SAT ran with `num_workers=4`.
>
> **Scripts** are in `/tmp/claude-0/-home-user-kicad-auto-everything/009d7404-80d1-57ec-ba01-3ececa478fa8/scratchpad/bench/`:
> - `pcbgen.py`
> - `cpsat_place.py`
> - `hier_place.py`
> - `sa_place.py`
> - `geom_bench.py`
> - `pathfinder_bench.py`
> - raw results: `results*.jsonl`

---

## 1. Exact/declarative solvers (CP-SAT, MILP, SMT, MaxSAT) for placement, floorplanning, escape routing

### Takeaway
Every exact method breaks down at roughly 50–100 freely placed parts with rotation when it is given the whole board as one model. Published PCB results (NS-Place, HiePlace) and SMT floorplanning results agree with my CP-SAT measurements on this. My CP-SAT runs found nothing feasible for 300 or 1000 parts within 300 s.

Exact solvers work well when the problem is decomposed:
- **Per-cluster placement.** HiePlace places 13–404-part industrial boards with Gurobi using DP plus relaxation inside a hierarchy.
- **Legalization with relative order fixed.** NS-Place's GD+MILP is an example.
- **LNS windows.** My hierarchical CP-SAT + LNS beat monolithic CP-SAT by 22–55% HPWL at 100 parts in about the same wall time (one seed; monolithic results vary up to 2× across seeds). It stayed feasible at 300 and 1000 parts (see below).

OR-Tools CP-SAT (Apache-2.0) is the most practical exact engine. It has native `add_no_overlap_2d` over optional intervals, keep-out boxes, hints and packing-LNS workers. MILP (HiGHS/SCIP) suits network-flow sub-problems such as escape routing. SMT (Z3) needs hours for 30–300 blocks with rotation.

### Cited Findings

**CP-SAT core facts**
- `ortools` 9.15.6755 (2026-01-14) is Apache 2.0 — [PyPI ortools](https://pypi.org/pypi/ortools/json) [P]
- `add_no_overlap_2d` takes two lists of (optional) intervals and ensures that for every i,j either the x-intervals or the y-intervals do not overlap. "If either x_intervals[i] or y_intervals[i] are optional, the whole object is optional." — [cpsat-primer advanced_modelling.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md) [P]
- The primer's rotation encoding is a `rotated` Bool, width/height IntVars over `Domain.from_values([w,h])`, and `add_allowed_assignments([w,h,rot],[(w,h,0),(h,w,1)])`. Optional intervals with `is_present=packed_i` give a knapsack variant — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md) [P]
- "CP-SAT is good at finding a feasible packing, but incapable of proving infeasibility in most cases." Benchmarks used a 90 s limit, "Rotations make things slightly more difficult" — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md) [P]
- Resolution sensitivity, CP-SAT 9.3 → 9.8 runtime: 1x 0.02→0.03 s; 100x 7.6→1.1 s; 1000x 75→40.3 s; 10,000x ">15min"→0.4 s ("not stabilized") — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md) [P]
- NoOverlap2D parameters in [sat_parameters.proto (stable)](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto) [P]:
  - `use_timetabling_in_no_overlap_2d`, `use_energetic_reasoning_in_no_overlap_2d` and `use_area_energetic_reasoning_in_no_overlap_2d` all default to false.
  - `max_pairs_pairwise_reasoning_in_no_overlap_2d` defaults to 1250.
  - `no_overlap_2d_boolean_relations_limit` defaults to 10.
  - `maximum_regions_to_split_in_disconnected_no_overlap_2d` "Detects when the space… is disjoint (ie., fixed boxes split the domain)"; default 0 = off.
  - `use_linear3_for_no_overlap_2d_precedences` (default true) is "particularly useful for problems where the distance between two boxes is part of the model."
- **API drift (2026).** The primer's custom-subsolver recipe builds a protobuf `sat_parameters_pb2.SatParameters()` and appends it to `solver.parameters.subsolver_params` — [cpsat-primer parameters.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md) [P]. In OR-Tools 9.15 this raises `TypeError: append(): incompatible function arguments`, because `solver.parameters` is now a pybind11 `cp_model_helper.SatParameters`. What works is `p = cp_model_helper.SatParameters(); …; solver.parameters.subsolver_params.append(p); solver.parameters.extra_subsolvers.append(p.name)`. [M]
- The portfolio includes packing-specific LNS workers `packing_precedences_lns`, `packing_rectangles_lns` and `packing_slice_lns` — [cpsat-primer parameters.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md) [P]
- Warm starts use `add_hint`. "CP-SAT only benefits from complete hints". `fix_variables_to_their_hinted_value` helps debug hints; `hint_conflict_limit` defaults to 10 — [cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/parameters.md); [proto](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto) [P]
- LNS is the primer's recommended route for "bigger problems" — [cpsat-primer lns.md](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/lns.md) [P]

**PCB-scale evidence from the literature**
- **NS-Place** (Cheng, Ho, Holtz; ASP-DAC 2022; [arXiv 2210.14259](https://arxiv.org/abs/2210.14259)) [P]
  - Its MILP legalizer is the classic big-M formulation: `x_i + r_i h_i + (1−r_i) w_i ≤ x_j + W(p_ij+q_ij)` etc., with binaries for orientation r_i and relative position p_ij, q_ij.
  - On 14 PCBs (8–1570 components, 1–4 routing layers), **vanilla MILP found no feasible placement within 4 h for 10 of 14 designs**.
    - Solved within limits: PCB1 (8 comps) in 2.7 s and PCB2 (18 comps) in 6.3 s.
    - Hit the 4 h limit with a feasible solution: PCB3 (34), PCB8 (36), PCB12 (58).
    - No feasible solution: PCB4 (28 comps, 6 locked) and everything larger.
  - With relative-position constraints taken from a gradient-descent global placement (GDMILP / NS-Place), feasible results came in 4.9 s–6,008 s for ≤64-component boards. PCB14 (1,570 comps, 947 locked) hit the 14,400 s limit.
  - Evaluation used Freerouting plus KiCad DRC. Reported results: routed WL up to −25%, vias up to −50%, and DRVs −79% vs manual.
  - The MILP solver is not named in the paper.
- **HiePlace** (Li, Zhuang, Liu, Sheng, Yu, Ho; IEEE TCAD 45(1), Jan 2026, CUHK + Huawei; [PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf)) [P]
  - A "mathematical-programming (MP)-based placement framework designed explicitly for PCBs", solved by **Gurobi**. Hierarchy: component grouping → DP for first-priority parts around the core chip → a relaxation that "minimize[s] the number of boolean variables" → alignment refinement.
  - Table I: 15 industrial boards (mostly mobile phones, density ≈0.58–0.81, **13–404 components**, 35–2,455 pins) plus 4 academic boards (13–57 components).
  - Table II runtimes: **0.02 min (13 parts) to 120 min (399–404 parts)**.
  - The ILP baseline Floorplet [25] took 30–240 min and produced **no feasible result for PCB11–PCB15 (308–404 components)**.
  - HiePlace reports −66% cost with 13% of the runtime. Against Quilter on bm1–bm4, Quilter took 34–75 min vs. seconds for HiePlace.
  - The paper itself is CC BY-NC-ND. No code release was found.
- **SMT floorplanning with Z3** ([arXiv 1709.07241](https://arxiv.org/abs/1709.07241)) [P]
  - GSRC CPU time without → with rotation: n30 64 s → 1,220 s; n50b 569 s → **45,474 s**; n100 315 s → 8,745 s; n300 932 s → **26,777 s**.
  - MCNC with rotation: 2,013–29,282 s.
  - The authors state that "it was necessary to break up the circuits into spatial clusters" for the larger cases.
- **CDCL vs CP-SAT vs MILP** on discrete facility layout ([arXiv 2512.18034](https://arxiv.org/abs/2512.18034)) [P]
  - Only 2×2–6×6 slot grids, with MILP = PuLP–CBC.
  - CDCL dominates feasibility, CP-SAT proves optimality on 5×5/6×6 within 60 s, and MILP "suffers exponential slowdown".
  - A CDCL→CP-SAT warm-start hybrid reached the global optimum faster than cold-start CP-SAT.
  - The instances are tiny, so this is weak evidence for PCB scale.

**MILP / SMT / MaxSAT tooling**
- `highspy` 1.15.1 is MIT; the HiPO builds are Apache — [PyPI](https://pypi.org/pypi/highspy/json) [P]; [HiGHS README](https://github.com/ERGO-Code/HiGHS) [S]
- SCIP has been Apache-2.0 since 8.0.3 (SCIP 10) — [SCIP Opt Suite 10 report](https://arxiv.org/html/2511.18580v1) [S]. `pyscipopt` 6.3.0 is MIT — [PyPI](https://pypi.org/pypi/pyscipopt/json) [P]
- `gurobipy` 13.0.3 is proprietary — [PyPI](https://pypi.org/pypi/gurobipy/json) [P]
- `z3-solver` 5.3.1.0 is MIT — [PyPI](https://pypi.org/pypi/z3-solver/json) [P]
- OptiMathSAT is "available for research and evaluation purposes only… can not be used in a commercial environment… without written permission" — [download page](https://optimathsat.disi.unitn.it/pages/download-js.html) [S]
- `python-sat` (PySAT) is MIT: a "simple interface to a number of state-of-art SAT solvers… easy… to implement a MaxSAT solver" — [PyPI](https://pypi.org/pypi/python-sat/json) [P]
- SMT analog placement (DATE 2016): "As the number of physical constraints increases, the SMT solver processing time decreases" — [PDF](https://past.date-conference.com/proceedings-archive/2016/pdf/0804.pdf) [S]

**BGA escape routing**
- "Unordered escape can be solved optimally with network flow". Ordered escape is handled exactly with SAT — [ASP-DAC 2008](https://www.cecs.uci.edu/~papers/aspdac08/pdf/p244_3A-4.pdf) [S]
- A two-stage network-flow ILP covers escape plus area routing — [PeerJ CS 499](https://peerj.com/articles/cs-499.pdf) [S]
- Network-flow models solve net ordering and escape together — [Sattar & Ignjatovic](https://jml.um.edu.my/index.php/MJCS/article/view/7006) [S]

**Own micro-benchmarks [M]: CP-SAT on synthetic PCB-like instances**

The instances come from `pcbgen.py`. The size mix is realistic: R/C 0402/0603, SOT-23, SOIC-8, QFN-32 and TQFP-64 ICs, and 2×5 headers, using courtyard sizes. Settings:
- board aspect 1.5 at 45% area utilization
- 4 mounting-hole keep-outs (6×6 mm) plus one edge keep-out (antenna-style)
- 2–4 decaps per IC, with a **hard decap-pin ↔ IC-VDD-pin L1 distance ≤ 3 mm**
- 2–4-pin nets with cluster locality
- 4-way rotation
- pin-level HPWL objective (exact min/max)
- model = formulation A below

Instance sizes:

| N | board (mm) | nets | decap constraints | CP-SAT vars |
|---|---|---|---|---|
| 30 | 32.7×20.7 | 43 | 5 | 322 |
| 100 | 51.9×32.9 | 109 | 25 | 1,080 |
| 300 | 98.1×62.3 | 323 | 65 | 3,248 |
| 1000 | 180×114 | 1,127 | 200 | 10,812 |

*A. Monolithic model, time to first feasible solution (no objective), 4 workers:*

| N | 0.5 mm grid | 0.1 mm grid |
|---|---|---|
| 30 | 0.24 s | 2.0 s |
| 100 | 5.9 s | 72 s |
| 300 | **none in 300 s** | **none in 300 s** |
| 1000 | **none in 300 s** | **none in 323 s** |

Area utilization was not what made it hard at N=100: first-feasible times were 6.2 s at 55%, 5.0 s at 65% and 5.8 s at 75% utilization (0.5 mm grid).

*B. Monolithic model, HPWL optimization, 60 s, 4 workers.* Values are HPWL in mm, best@15s/@30s/@60s, with the final lower bound in brackets. "var" is the variable-size interval rotation encoding; "opt2" is two optional fixed-size intervals per part.

| N, grid | rotation "var" | rotation "opt2" | no rotation |
|---|---|---|---|
| 30, 0.5 mm | 249 / 245 / **243.5** [55] | 233.5 / 225 / **218.5** [55] | – |
| 30, 0.1 mm | 255 / 226 / **222.8** [42] | 282 / 281 / **241.8** [11.8] | – |
| 100, 0.5 mm | 1300 / 784 / **643.5** [62.5] | 1172 / 771 / **616.5** [63] | **585.5** [299] |
| 100, 0.1 mm | –/–/ **1009** (1st sol @45 s) [25] | –/–/ **860** (1st sol @40 s) [22] | – |
| 300, 0.5/0.1 mm | no solution | no solution | no solution |
| 1000, 0.5 mm (300 s) | no solution | – | – |

Two-sided (N=100, 0.5 mm, side literal per part, two NoOverlap2D): first solution at 11.2 s, 396 mm after 60 s [bound 92]. N=300 two-sided: no solution in 60 s.

The lower bounds stay at 5–25% of the incumbent. CP-SAT's HPWL relaxation is weak, so it cannot certify placement quality even at N=30.

*C. Hierarchical CP-SAT + LNS (`hier_place.py`).* The steps:
1. Per IC cluster, a CP-SAT run (1 s) for each of 2 aspect-ratio variants (1:1, 2:1) produces "soft macros". Connectors stay single top-level items.
2. A top-level CP-SAT floorplan with a one-hot over (variant × 4 rotations), keep-outs, and inter-cluster pin-level HPWL.
3. Flatten.
4. Windowed CP-SAT LNS on the full model: free the 40 nearest parts, fix the rest, hint the current solution, 2 s per iteration.

The first version with rigid square macros was INFEASIBLE at N=30. One 15.5 mm cluster square plus one 10.4 mm square could not fit between the corner keep-outs of a 32.7×20.7 mm board. Aspect-ratio variants plus excluding connectors from clusters fixed it, which makes soft macros a necessity. Results (HPWL in mm; check = overlaps/decap violations/out-of-board/keep-out intrusions, all 0):

| N, grid | hierarchy only | + LNS | total wall time | monolithic CP-SAT (60 s) |
|---|---|---|---|---|
| 100, 0.5 mm | 599.0 (31 s) | **480.5** | 71 s | 616.5–643.5 |
| 100, 0.1 mm | 584.1 (34 s) | **454.4** | 75 s | 860–1009 |
| 300, 0.5 mm | 2,826 (63 s; 26 clusters) | **2,461.5** | 124 s | **no solution** |
| 300, 0.1 mm | 2,793.8 (70 s) | **2,473.2** | 131 s | **no solution** |
| 1000, 0.5 mm | 22,963 (172 s; 87 clusters) | 22,595.5 (1 of 14 LNS moves accepted) | 294 s | **no solution in 300 s** |
| 1000, 0.1 mm | top-level floorplan of 87 soft macros: **no solution in 60 s** | – | 193 s | no solution |

Observations:
- At N=1000, each LNS iteration cost about 8.6 s for a 3 s solve. Cloning, presolving and hinting the full 10.8k-variable model dominates. A production LNS should build a *window sub-model*: free parts as variables, neighbours as fixed boxes, external pins as constants.
- Cluster solves (112 s for 87 clusters × 2 variants) are independent and trivially parallel.
- The top-level floorplan at 0.1 mm with 87 macros needs either a coarser grid (0.5 mm worked) or its own hierarchy level.

*D. Ablation: what makes monolithic N≥300 hard?* Time to first feasible, 0.5 mm grid, 300 s limit, 4 workers:

| variant | result |
|---|---|
| N=150, full model | 15.0 s |
| N=200, full model | 72.7 s |
| N=300, full model | none in 300 s |
| N=300 without decap constraints | **none in 300 s** (decap distance is *not* the bottleneck) |
| N=300 with **fixed orientation** | **82.6 s** |
| N=300 "opt2" rotation encoding | none in 300 s |
| N=300 at 35% utilization | 173.7 s |
| N=300 + dedicated packing subsolver (area-energetic + energetic + timetabling NoOverlap2D reasoning, 5,000 pairwise pairs; the primer's recipe with the 9.15 API fix) | **271 s** (vs none without) |
| N=100 seed variance (seeds 0–3) | first feasible 4.0–5.9 s; 60 s HPWL 616–1,177 mm (≈2× spread) |

Takeaways:
- Free 4-way rotation is the main driver of difficulty at scale. Choosing orientations upstream (rules, LLM, or a continuous placer's argmax) and fixing them in CP-SAT removes most of it.
- The packing subsolver helps. Keep it as one extra worker, as the primer suggests.
- Time to first feasible grows super-linearly: 0.24 s (30) → 5.9 s (100) → 15 s (150) → 73 s (200) → >300 s (300).

### Inferences
- **Scale guidance, now backed by the measurements above.**
  - One monolithic CP-SAT model with 4-way rotation, keep-outs and decap distance constraints is viable up to about 100 parts on a coarse grid (0.5 mm). It is not viable at 300+ parts.
  - Go hierarchical: cluster (IC + its passives) → soft-macro floorplan → windowed LNS. This matches how HiePlace (Gurobi) and Cypress's benchmark design describe engineers' practice: "local placement on a subset of components, then position the group" — [Cypress ISPD'25 slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P].
- **Use a 0.5 mm grid for global search and refine only in windows.** At N=100, 0.1 mm made first-feasible 12× slower (72 s vs 5.9 s).
- **Prefer the two-optional-interval rotation encoding ("opt2")** for N ≥ 100. It produced the better 60 s HPWL in 3 of 4 cells, with fewer variables but more constraints.
- **CP-SAT is a feasibility/legalization engine, not an HPWL optimizer.** On HPWL alone, simulated annealing beats it at small N (§3 [M]). Use CP-SAT where hard constraints dominate: legal non-overlap with keep-outs, decap distance, alignment/symmetry, edge connectors, and fixed parts. Feed it hints from an analytical or SA placement.
- **Keep-outs and non-rectangular outlines** become fixed boxes in the same NoOverlap2D (rectangle decomposition via Shapely). Turn on `maximum_regions_to_split_in_disconnected_no_overlap_2d` when keep-outs split the board.
- **Symmetry-break interchangeable parts** (identical decaps in one group) with lexicographic order constraints.
- **GPL-3.0.** Apache-2.0 is GPLv3-compatible per the ASF: "Apache 2 software can therefore be included in GPLv3 projects" — [ASF GPL-compatibility](https://www.apache.org/licenses/GPL-compatibility.html) [P]. MIT/BSD (HiGHS, Z3, PySCIPOpt, PySAT) are also fine; I could not re-fetch the FSF list (gnu.org blocked) to confirm this. Gurobi and OptiMathSAT can only be optional, user-supplied backends.

#### Example formulation A — CP-SAT placement with rotation, sides, keep-outs, decap proximity (as benchmarked; `cpsat_place.py`)
```python
from ortools.sat.python import cp_model
from ortools.sat.python.cp_model import Domain
m = cp_model.CpModel(); g = 0.5                      # mm per grid unit (coarse for global; refine in windows)
for c in comps:                                      # c.w,c.h = courtyard (mm) -> ceil(/g)
    r = [m.new_bool_var(f"r{c}_{k}") for k in range(4)]; m.add_exactly_one(r)   # 0/90/180/270
    sw = m.new_bool_var(""); m.add(sw == r[1] + r[3])                           # swapped dims
    x = m.new_int_var(0, BW - min(W0, H0), ""); y = m.new_int_var(0, BH - min(W0, H0), "")
    top = m.new_bool_var("")                                                    # side (2-sided only)
    # ENCODING "opt2" (two optional fixed-size boxes; better at N>=100 in my runs):
    for (w, h, lit) in ((W0, H0, ~sw), (H0, W0, sw)):
        m.add(x + w <= BW).only_enforce_if(lit); m.add(y + h <= BH).only_enforce_if(lit)
        pres = and_(lit, top) if two_sided and not c.tht else lit                 # THT: both sides
        X_TOP.append(m.new_optional_fixed_size_interval_var(x, w, pres, ""))
        Y_TOP.append(m.new_optional_fixed_size_interval_var(y, h, pres, ""))
        # ... and the same with and_(lit, ~top) into X_BOT/Y_BOT
    # pin positions are LINEAR in the one-hot rotation literals (offsets precomputed per k):
    for p in c.pins: PX[p] = x + sum(r[k] * dx[p][k] for k in range(4)); PY[p] = y + sum(r[k]*dy[p][k] for k in range(4))
for (kx, ky, kw, kh) in keepout_rects:              # board outline complement + keep-outs as fixed boxes
    X_TOP.append(m.new_fixed_size_interval_var(kx, kw, "")); Y_TOP.append(m.new_fixed_size_interval_var(ky, kh, ""))
m.add_no_overlap_2d(X_TOP, Y_TOP); m.add_no_overlap_2d(X_BOT, Y_BOT)
for (cap_pin, ic_pin, dmax) in decaps:               # hard L1 ball = 4 linear constraints (no aux vars)
    dx = PX[cap_pin] - PX[ic_pin]; dy = PY[cap_pin] - PY[ic_pin]
    for sx in (1, -1):
        for sy in (1, -1): m.add(sx * dx + sy * dy <= int(dmax / g))
    m.add(top[cap] == top[ic])                       # or allow opposite side under a BGA
obj = []
for net in nets:                                     # exact HPWL; 2-pin nets via abs equality
    xs = [PX[p] for p in net]; ys = [PY[p] for p in net]
    a, b, c_, d = (m.new_int_var(0, BW, "") for _ in range(2)), ...
    m.add_max_equality(a, xs); m.add_min_equality(b, xs); m.add_max_equality(c_, ys); m.add_min_equality(d, ys)
    obj += [w_net * (a - b + c_ - d)]
for grp in interchangeable_groups:                   # symmetry breaking
    for u, v in zip(grp, grp[1:]): m.add(x[u] <= x[v])
m.minimize(sum(obj))
for c in comps: m.add_hint(x[c], x0[c]); m.add_hint(y[c], y0[c])   # from SA / analytical placement
s = cp_model.CpSolver(); s.parameters.num_workers = 8; s.parameters.max_time_in_seconds = 30
# LNS (hier_place.py::lns_polish): clone model, fix (x,y,r) of all parts outside a k-NN window, hint window, solve 2 s, accept if better
```

### Gaps
- No open-source CP-SAT-based PCB placer was found. The search budget ran out again before targeted GitHub searches. HiePlace's code was not found.
- My instances are synthetic. Real boards have irregular outlines, many more fixed parts, height/edge rules, and thermal and EMI constraints. The measurements bound scale, not quality.
- The custom packing subsolver run at N=300 is pending or reported in the ablation above.
- The MILP solver used by NS-Place is not stated in the paper.
- The FSF GPL-compatibility list (gnu.org) could not be fetched; compatibility comes from the ASF and Mozilla statements only.

---

## 2. Continuous / differentiable placement (ePlace/DREAMPlace-style, custom PyTorch/JAX losses, RUDY)

### Takeaway
The proven scalable PCB approach is analytical placement. Cypress (NVIDIA/Cornell, ISPD 2025 Best Paper, Apache-2.0) is DREAMPlace adapted to PCBs:
- orientation-aware LogSumExp wirelength
- **two-sided** electrostatic density (sides are *pre-assigned* inputs, not optimized)
- a differentiable **net-crossing** term
- **Gumbel-Softmax** over 4 orientations, optimized bi-level with positions
- Tetris + Abacus legalization
- MOTPE (multi-objective TPE) tuning of 8 hyperparameters

It has been demonstrated from 41 to 6,628 components. NS-Place (gradient descent + MILP legalization) is the older open baseline. Domain terms (decap, keep-out SDF, thermal, loop area) can be added as penalties in a custom PyTorch/JAX loss. Discrete decisions (side, final orientation, legality) still need a discrete legalizer.

### Cited Findings
**Cypress** (Zhang, Agnesina, Shbat, Leader, Zhang, Ren; ISPD 2025) — [ISPD slides PDF](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]; [NVlabs/Cypress](https://github.com/NVlabs/Cypress) [P]
- **Problem:** "Surfaced-mounted, noncritical components on rectilinear PCB top/bottom". Input is a netlist "with pre-assigned side". Constraints: "spacing, non-overlap, fixed critical, mechanical components".
- **Objective:**
  - wirelength is an "orientation-aware" extension of LogSumExp
  - density is a "two-sided electro-static density map"
  - net crossing is "the sum of smoothed first-degree Bézier parameters of all source-sink pin pairs": crossing parameters t,u pass through a bell function and are multiplied, summed over pin pairs on the same layer
- **Orientation:** "Components have four legal orientations… We use Gumbel-Softmax reparameterization… a bi-level placement optimization process for position and orientation… fix one while optimizing the other."
  - In code, `orient_logits` get a separate Adam optimizer, and `enable_rotation` defaults to 0 — [Cypress PlaceObj.py](https://raw.githubusercontent.com/NVlabs/Cypress/main/dreamplace/PlaceObj.py), [NonLinearPlace.py](https://raw.githubusercontent.com/NVlabs/Cypress/main/dreamplace/NonLinearPlace.py), [params.json](https://raw.githubusercontent.com/NVlabs/Cypress/main/dreamplace/params.json) [P]
  - The ops include `net_crossing` and a `two_side_density_op` — [ops tree](https://github.com/NVlabs/Cypress/tree/main/dreamplace/ops) [P]
- **Tuning:** "multi-objective Bayesian optimization (MOTPE)", run in parallel across GPUs, over:
  - horizontal and vertical initial position [0.2, 0.8]
  - initial density weight [1e-6, 1]
  - target density [0.1, 1]
  - initial net-crossing weight [1e-6, 1]
  - LogSumExp initial γ [0.1, 0.5]
  - initial learning rate [1e-4, 1e-2]
  - optimizer {Adam, Nesterov}
- **Evaluation:** "Freerouting… V1.9.0, two free copper layers, default settings, routability defined as the percentage of routed pin pairs."
- **Baselines:**
  - SA-PCB (OpenROAD community annealer)
  - NS-Place (gradient + MILP legalization)
  - NS-Place+ (NS-Place with Cypress's legalizer: "Tetris legalization, followed by Abacus row-based legalization")
  - Quilter, which the slides call commercial/closed-source and RL-based. HiePlace instead calls Quilter "an open-source RL-based tool"; the two sources conflict.
- **Benchmarks** (open suite):
  - small-1…10: **41–476 components** (all movable), 85–5,334 pins, 26–1,513 nets
  - big-1…5 (commercial): **5,118–6,628 components** (1,293–2,152 movable), 11.6k–21.9k pins, 2.9k–7.2k nets
- **Results:**
  - Routability up to 1.2× vs SA-PCB, 5.9× vs NS-Place, 1.6× vs NS-Place+ (normalized to the human baseline).
  - "Up to 492.3X faster than SA-PCB… Up to 329.7X faster than Quilter."
  - With 4 V100s, most small benchmarks complete in 200.5–350.7 s including exploration; S2 takes 1,764.7 s.
  - Big-benchmark ablation (normalized avg): adding net crossing → HPWL 1.13, net crossings 0.31; adding orientation as well → HPWL 1.05, NC 0.27.
- Headline claims "1–5.9× higher routability… 1–19.7× shorter routed track lengths" — [Cornell news](https://zhang.ece.cornell.edu/news/cypress_ispd_bpa.html) [S]

**NS-Place** ([arXiv 2210.14259](https://arxiv.org/abs/2210.14259)) [P]
- Pipeline: seed layouts → gradient descent with momentum (α=1e−3, λ_NS=λ_D=1) on wirelength + density + an SVM-style net-separation margin → congestion-aware MILP legalization with relative-position pruning (see §1).

**Double-layer module placement** ([arXiv 2502.14012](https://arxiv.org/abs/2502.14012)) [P]
- Separates top-layer "centralized" placement around the IC from bottom-layer "pin-oriented" placement.
- Uses a mixed-variable model: positions via a conjugate-subgradient analytical method, orientations via a distribution evolutionary algorithm.
- Industrial cases, sizes not extracted.

**DREAMPlace** (BSD-3) — [README](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/README.md) [P]
- Over 30× speedup vs RePlAce (GPU, ISPD 2005); ABCDPlace about 16× vs NTUPlace3.
- Ops include `weighted_average_wirelength`, `logsumexp_wirelength`, `electric_potential` (DCT Poisson "according to e-place"), `rudy`, `pinrudy`, `abacus_legalize` and others — [ops tree](https://github.com/limbo018/DREAMPlace/tree/master/dreamplace/ops); [electric_potential.py](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/ops/electric_potential/electric_potential.py); [ePlace paper](http://cseweb.ucsd.edu/~jlu/papers/eplace-todaes14/paper.pdf) [P]
- Defaults: `gamma` 4.0, `density_weight` 8e-5, `target_density` 0.8, `stop_overflow` 0.1; optimizer ∈ {nesterov, adam, sgd…}; RUDY area adjustment — [params.json](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/params.json) [P]
- Tested with Python 3.5–3.9 and PyTorch 1.6–2.0; GCC 7.5 — [GitHub](https://github.com/limbo018/DREAMPlace) [P]

**Other**
- Apollo (photonic ICs): geometric-mean routability 94.79% vs DREAMPlace 50.85% and Cypress 51.38% — [arXiv 2504.18813](https://arxiv.org/pdf/2504.18813) [S]
- RL_PCB (MIT, DATE 2024): per-component RL policies; Python 3.8; parses `.kicad_pcb` — [README](https://raw.githubusercontent.com/LukeVassallo/RL_PCB/main/README.md) [P]
- `torch` 2.14.1 and `jax` 0.12.0 are Apache-2.0 — [PyPI torch](https://pypi.org/pypi/torch/json), [PyPI jax](https://pypi.org/pypi/jax/json) [P]

### Inferences
- **Cypress's modelling choices are a validated template** for our differentiable stage: Gumbel-Softmax orientation, two-sided density with sides fixed upstream, a net-crossing term for 2-layer routability, and MOTPE tuning.
- **Side assignment is better made upstream.** Use rules (passives under BGAs, tall parts top) or a small CP-SAT/LLM decision, then run the continuous placer. This mirrors Cypress, which takes the side as an input.
- **For 20–1000 parts, a lean JAX/PyTorch reimplementation of Cypress's ideas is likely better than adopting DREAMPlace's CUDA build.** DREAMPlace pins Python ≤3.9, PyTorch ≤2.0 and GCC 7.5, and is Bookshelf-centric. Cypress's small benchmarks still took 200–350 s on 4 V100s with exploration, so GPU is not needed at our size. (Inference; not benchmarked here.)
- **Domain terms to add** (differentiable penalties):
  - decap: relu(‖pin_cap−pin_IC‖−dmax)²
  - hot-loop area: triangle (VDD pin, cap, GND pin)
  - keep-out and outline: SDF sampled bilinearly
  - thermal spreading: Σ PᵢPⱼ/(d²+ε)
  - congestion: RUDY
  - same-layer net crossings: Cypress-style Bézier/bell term

#### Example formulation B — differentiable placement loss with domain terms (JAX-style pseudo-code)
```python
def wa(v, mask, gamma):                                   # weighted-average smooth max - smooth min
    ep = jnp.exp((v - v.max()) / gamma) * mask; en = jnp.exp((v.min() - v) / gamma) * mask
    return (v * ep).sum() / ep.sum() - (v * en).sum() / en.sum()

def loss(params, key, k):                                 # k = continuation step
    xy, logits = params["xy"], params["orient_logits"]    # side is FIXED input (as in Cypress)
    p = jax.nn.gumbel_softmax(key, logits, tau=tau(k))    # or softmax(logits/tau); Cypress: Gumbel-Softmax
    off = jnp.einsum("pk,pkd->pd", p[pin2comp], pin_off_rot)            # 4 precomputed rotated offsets
    pin = xy[pin2comp] + off
    WL  = vmap_nets(lambda idx, m: w_n * (wa(pin[idx,0], m, g(k)) + wa(pin[idx,1], m, g(k))))
    OVL = soft_pair_overlap(xy, p, cand_pairs)            # or two-sided electrostatic density (FFT/DCT)
    NC  = net_crossing(pin, same_layer_pairs)             # Cypress: bell(t)*bell(u) of segment-pair params
    KO  = (relu(clear - sdf_keepout(corners(xy, p)))**2).sum()
    OUT = (relu(sdf_outline(corners(xy, p)) + margin)**2).sum()
    DEC = sum(relu(norm(pin[c] - pin[i]) - dmax)**2 for c, i, dmax in decaps)
    LOOP= sum(tri_area(pin[vdd], pin[cap], pin[gnd]) for ...)
    TH  = sum(P[i] * P[j] / (sqdist(xy[i], xy[j]) + eps) for hot pairs)
    CONG= (relu(rudy(pin, nets) - cap_map)**2).sum()
    return WL + lam_d(k)*OVL + lam_nc*NC + lam_k*KO + lam_b*OUT + lam_dec*DEC + lam_l*LOOP + lam_t*TH + lam_c*CONG
# bi-level (Cypress): alternate Nesterov/Adam steps on xy and Adam on orient_logits; ramp lam_d (ePlace-style);
# then argmax orientations -> CP-SAT legalization (min displacement, hard decap/keep-out) -> SA/LNS detailed placement.
```

### Gaps
- The Cypress full paper PDF (csl.cornell.edu) is still unreachable from this environment. The details above come from the ISPD slides and source code: the exact Gumbel temperature schedule, legalizer details, and per-benchmark routability tables are missing.
- The Cypress benchmark files were not downloaded and inspected (format is Bookshelf-like `.aux` according to the README).
- No published differentiable formulation of decap-loop or thermal terms for PCBs was found.

---

## 3. Metaheuristics (SA, GA, CMA-ES, NSGA-II/III, MAP-Elites, tabu, LNS) and LLM-driven heuristic search

### Takeaway
Simulated annealing with incremental cost is still the strongest simple HPWL optimizer at small to medium N. In my runs, pure-Python SA beat 60 s of 4-worker CP-SAT on HPWL at N=30 in a few seconds. SA does not guarantee legality, though, and needs a legalizer, which is CP-SAT's strength.

For multi-objective trade-offs and diversity:
- pymoo (Apache-2.0): NSGA-II/III, MOEA/D, …
- pyribs (MIT): MAP-Elites family
- pycma (BSD-3)
- Nevergrad (MIT)

A newer option is LLM-driven heuristic/algorithm evolution (FunSearch-style ReEvo, EoH, AlphaEvolve, LLM4AD). It could let the LLM agent evolve move operators or cost terms against our evaluator.

### Cited Findings
- pymoo 0.6.2 (Apache-2.0) `moo` algorithms: nsga2, nsga3, unsga3, rnsga2/3, moead, age/age2, ctaea, rvea, sms, spea2, mocmaes, como_cmaes, gde3, nsde, mopso_cd, cmopso, dnsga2, pinsga2, kgb — [PyPI](https://pypi.org/pypi/pymoo/json); [dir listing](https://github.com/anyoptimization/pymoo/tree/main/pymoo/algorithms/moo) [P]
- `ribs` 0.12.0 (MIT): MAP-Elites, CMA-ME, CMA-MEGA, CMA-MAE plus scalable variants; ask/tell with archive, emitters and scheduler — [PyPI](https://pypi.org/pypi/ribs/json) [P]
- DEAP 1.4.4 (LGPL): CMA-ES, NSGA-II/III, SPEA2, MO-CMA-ES — [PyPI](https://pypi.org/pypi/deap/json) [P]
- Nevergrad 1.0.12 (MIT, `NGOpt`; last release 2025-04) — [PyPI](https://pypi.org/pypi/nevergrad/json) [P]
- `cma` 4.5.0 is BSD-3 — [PyPI](https://pypi.org/pypi/cma/json) [P]
- SA-PCB (the Cypress baseline) is an annealing-based PCB placer, BSD-3, upstream `choltz95/c-pcb-annealer` — [Gitee mirror](https://gitee.com/hitero/SA-PCB) [S]
- Its host app, OpenROAD PCB-PR-App, is BSD-3 and supports "kicad_pcb format derived from KiCad v5.1.2" — [README](https://raw.githubusercontent.com/The-OpenROAD-Project/PCB-PR-App/master/README.md) [P]
- Cypress reports SA-PCB's "strategy works for small designs but hurts larger ones" — [slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]
- **LLM-driven heuristic design:**
  - ReEvo, "Language Hyper-Heuristics": evolutionary search plus LLM "reflections… verbal gradients", state of the art on six COPs — [arXiv 2402.01145](https://arxiv.org/abs/2402.01145) [P]
  - EoH evolves "thoughts" and code — [arXiv 2401.02051](https://arxiv.org/abs/2401.02051) [P]
  - AlphaEvolve: "evolutionary coding agent… improve an algorithm by making direct changes to the code… continuously receiving feedback from one or more evaluators" — [arXiv 2506.13131](https://arxiv.org/abs/2506.13131) [P]
  - LLM4AD is a unified Python platform with search methods, task suite and sandbox — [arXiv 2412.17287](https://arxiv.org/abs/2412.17287) [P]
  - OPRO: the LLM proposes solutions given prior solutions and scores — [arXiv 2309.03409](https://arxiv.org/abs/2309.03409) [P]
- Own measurement [M], `sa_place.py`: pure Python + NumPy SA with penalty λ ramp, moves = shift/rotate/swap.
  - About 10–11k moves/s at N=30.
  - Within 4–5 s at N=30 (0.5 mm grid) it reached legal placements of **202–223 mm HPWL**, versus CP-SAT's best 218.5–243.5 mm after 60 s on 4 workers.
  - One 5 s run ended with 2 residual overlaps; penalty SA alone does not guarantee legality.
  - CP-SAT LNS polishing of a 202 mm SA result found no improvement in 3×2 s windows.

{{SA}}

### Inferences
- **Recommended division of labour:**
  - analytical (Cypress-style) or SA for wirelength-driven global placement
  - CP-SAT for legalization under hard constraints (min-displacement model `hier_place.py::legalize`) and for constraint-heavy local windows
  - SA/tabu with incremental cost (Rust) for detailed placement
  - pymoo/Optuna for Pareto fronts; pyribs for diverse alternatives to show the LLM
- **LLM-evolved heuristics** (ReEvo/EoH/AlphaEvolve pattern) map naturally onto an LLM-driven engine. Let the agent propose new move operators or cost terms as code, scored on a fixed benchmark set with a sandboxed evaluator. That is cheaper and safer than having the LLM place parts directly.

### Gaps
- No PCB-specific study of LLM-evolved placement heuristics was found (search budget exhausted).
- FunSearch's bin-packing result (Nature 2023) was not re-fetched.
- My SA has no clustering or legalization-aware moves, so its numbers are a lower bar for what SA can do.

---

## 4. Bayesian optimization / hyperparameter tuning; LLM-guided tuning

### Takeaway
Tuning placer and router knobs by multi-objective BO is proven for PCBs:
- Cypress uses MOTPE over 8 placer parameters, scored by routed results.
- AutoDMP does multi-objective BO for DREAMPlace in VLSI.

Optuna (MIT) provides TPE/MOTPE, NSGA-II, CMA-ES, GP and AutoSampler. **OptunaHub now has an LLAMBO sampler**, which makes "LLM-guided BO" a drop-in: the LLM proposes warm-starts and candidates from a natural-language task description, at roughly $0.05–0.10 per 30-trial run with GPT-4o-mini. LLAMBO's benefit is in the sparse early phase; it is costlier and studied mainly on low-dimensional problems.

### Cited Findings
- **Cypress** tunes 8 parameters with MOTPE, parallel on multiple GPUs; objectives are wirelength, density and net crossing, with the routed result evaluated afterwards — [slides p.11](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]
- **AutoDMP**: DREAMPlace + ABCDPlace with "automatic parameter tuning based on multi-objective hyperparameter Bayesian optimization (MOBO)"; the example runs 20 iterations × 2 workers — [README](https://raw.githubusercontent.com/NVlabs/AutoDMP/main/README.md) [P]
- **Optuna** 5.0.0 (MIT). AutoSampler gives "Full Support for Multi-Objective & Constrained Optimization". Rustuna (experimental) offers TPE/MOTPE/NSGA-II/CMA-ES and is "several times to several hundred times faster for cheap objective functions" — [PyPI optuna](https://pypi.org/pypi/optuna/json) [P]
- **LLAMBO** (Liu, Astorga, Seedat, van der Schaar; ICLR 2024; [arXiv 2402.03921](https://arxiv.org/abs/2402.03921)) [P]
  - Frames BO in natural language. The LLM does zero-shot warm-starting, acts as a surrogate (discriminative or generative), and samples candidates.
  - Tested on 74 Bayesmark/HPOBench tasks with GPT-3.5.
  - The authors' limitations: "inference through LLMs incurs a much larger computational footprint than traditional BO algorithms… Our study has primarily focused on HPT tasks, which are relatively low-dimensional." They suggest using it "in earlier stages of the search, or only leveraging an individual component".
- **OptunaHub LLAMBO sampler** — [hub.optuna.org/samplers/llambo](https://hub.optuna.org/samplers/llambo/) [P]
  - Adapted "beyond tabular ML" via `custom_task_description`; categorical parameters go to random search.
  - Its prompts forbid re-proposing observed points.
  - Cost: "using GPT-4o-mini… the estimated cost per run with n_trials = 30 ranges between $0.05 and $0.10".
- **Reproducibility study** ([arXiv 2511.18891](https://arxiv.org/abs/2511.18891)) [P]
  - With Llama 3.1 70B it "broadly confirm[s] the main claims": warm-starting improves early regret, and the LLAMBO sampler beats TPE and random.
  - "Smaller backbones (Gemma 27B, Llama 3.1 8B) yield unstable or invalid predictions."
- **Other tools:**
  - BoTorch 0.18.1 (MIT) — [PyPI](https://pypi.org/pypi/botorch/json) [P]
  - SMAC 2.4.1 (BSD-3), "All facades/intensifiers support multi-objective, multi-fidelity" — [PyPI](https://pypi.org/pypi/smac/json) [P]
  - ChatEDA: LLM agent orchestrating RTL→GDSII tool flows — [arXiv 2308.10204](https://arxiv.org/abs/2308.10204) [P]

### Inferences
- **Concrete recipe:**
  1. The LLM writes the Optuna search space and constraints from design intent.
  2. Use LLAMBO (OptunaHub) or the LLM's own zero-shot proposals for the first ~10 trials.
  3. Switch to MOTPE/NSGA-II (cheap, Rustuna if needed) for the bulk.
  4. Use multi-fidelity pruning: HPWL → RUDY → quick route → Freerouting.
  5. The LLM picks from the Pareto front.

  This mirrors Cypress (MOTPE + router evaluation) and the LLAMBO authors' own advice to use the LLM early.
- **Keep the search space small** (about 5–15 continuous knobs). LLAMBO evidence is for low-dimensional spaces, and small open models are unreliable as surrogates.

### Gaps
- No published study applies LLAMBO or other LLM-BO to EDA or PCB placement parameters (search budget exhausted before a targeted search).
- The original LLAMBO repo URL was not verified (an aggregator lists `tennisonliu/LLAMBO`, MIT [S]).

---

## 5. Routing engines (maze/A*, PathFinder, Freerouting, KiCadRoutingTools, PCBWorld/KiCad PNS, tscircuit, Topola, MAPF)

### Takeaway
**Freerouting** (GPL-3.0) is still the strongest open rule-based router.
- In PCBWorld (679 real KiCad boards) it led on clean-pass rate on larger boards: CP 0.78 on D3-B vs 0.20 for KiCadRoutingTools and 0.00 for OrthoRoute and all LLM agents.
- **KiCadRoutingTools** (MIT; Python + Rust A*, octilinear, rip-up/reroute, diff pairs) is fast and strong on small boards. It is the closest open reference for our in-house router.

**KiCad's push-and-shove router can be scripted**, but only by building KiCad with custom bindings. PCBWorld (BSD-3 env, GPLv3 engine) does exactly this against KiCad 9.0.8, exposing 14 `PNS::ROUTER` core APIs plus DRC to Python. The stock IPC API still has no router.

For an in-house router, use PathFinder negotiated congestion. The VPR defaults (pres_fac 0→0.5, ×1.3 per iteration, acc_fac 1, ≤50 iterations) are a sound starting point.

### Cited Findings
**PCBWorld** (LG AI Research; KDD Agentic AI workshop '26; [arXiv 2607.05915v4](https://arxiv.org/abs/2607.05915)) [P]; [repo README](https://github.com/LGAI-Research/PCBWorld) [P]
- Gym environment over KiCad's engine. "58 Python APIs built on bindings to the KiCad engine: 14 reproduce the core routing API of PNS::ROUTER, 28 directly wrap KiCad's DRC and board-state extraction APIs".
- "Built against KiCad 9.0.8 with kicad-python 0.6.0". The engine is a submodule; the repo license is "BSD-3-Clause; the engine is GPLv3".
- Routing modes are mark_as_obstacles, push_n_shove and walkaround.
- Datasets: D1 grid; D2 gridless (4–6 nets); D3 real boards from PCBench, split A (100 boards, 2–13 nets), B (287, 5–42 nets), C (292, 6–451 nets, 101–2,103 pads, 2–8 layers).
- Main metric is Clean Pass = routability 1 AND zero DRC errors.

Table 3, @5 protocol, CP / routability / time:

| Router | D2 | D3-A (99 boards) | D3-B (10 boards) |
|---|---|---|---|
| Freerouting | 1.00 / 1.00 / 2.7 s | 0.80 / 0.91 / 7.1 s | **0.78** / 1.00 / 9.9 s |
| KiCadRoutingTools | 1.00 / 1.00 / 0.8 s | 0.74 / 0.94 / 0.65 s | 0.20 / 0.86 / 3.3 s |
| OrthoRoute | 0.01 | 0.02 | 0.00 |
| GPT-5.4 tool-calling agent | 0.96 | 0.65 | 0.00 (866 s) |
| PPO transformer | 1.00 | 0.86 | 0.45 |

**KiCadRoutingTools** (Andy Haas; MIT) — [README](https://raw.githubusercontent.com/drandyhaas/KiCadRoutingTools/main/README.md) [P]
- "A fast Rust-accelerated A* autorouter for KiCad PCB files", compatible with KiCad 9 and 10, as plugin and CLI.
- Octilinear multi-layer routing, automatic vias, rip-up/reroute, net ordering, BGA exclusion zones, differential pairs.
- "Rust acceleration provides ~10x speedup vs pure Python".
- Test runs: FTDI 47/47 nets in 8.6 s; DDR 51/51 single-ended in 6.2 s; LVDS diff pairs 28/28 in about 30 s.
- Limitations: "No push-and-shove… No blind or buried vias… No coarse grid assignment".

**Freerouting** (GPL-3.0; Java 25 JRE recommended) — [README](https://github.com/freerouting/freerouting), [CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md) [P]
- Headless: `--gui.enabled=false -de in.dsn -do out.ses`, plus `-mp` (passes), `-mt` (optimizer threads; 0 = off), `--router.optimizer.improvement_threshold` (default 2.5%), `-drc` (KiCad-format JSON report).
- Local REST server via `--api_server.enabled=true`. Docker image `ghcr.io/freerouting/freerouting`; Python client `freerouting-client` (MIT) — [PyPI](https://pypi.org/pypi/freerouting-client/json)

**KiCad IPC API**
- No routing command exists. `RunAction` "WARNING: The TOOL_ACTIONs are specifically *not* an API" — [editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/common/commands/editor_commands.proto) [P]
- `ImportSpecctraSession` is marked "Since: 11.0" — [board_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/board/board_commands.proto) [P]
- On 2026-10-14 master gained "CLI: Add pcb export specctra_dsn" and "API: Support specctra import/export"; the latest stable is 10.0.7 — [GitLab commits API](https://gitlab.com/api/v4/projects/kicad%2Fcode%2Fkicad/repository/commits?path=kicad/cli/command_pcb_export_specctra.cpp&per_page=100) [P]
- kicad-python (main) has `get_pad_shapes_as_polygons`, `refill_zones`, `hit_test`, `interactive_move` and `place_footprint_from_library` — [kipy/board.py](https://gitlab.com/kicad/code/kicad-python/-/raw/main/kipy/board.py) [P]

**PathFinder**
- Cost Cn = (bn + hn) · pn, where bn is base cost, hn the congestion history, and pn depends on how many signals currently use n — [Lafayette CADApps](https://sites.lafayette.edu/cadapps/main-page/pathfinder-fpga-routing-algorithm/) [P]
- VPR defaults — [VPR command-line docs](https://docs.verilogtorouting.org/en/latest/vpr/command_line_usage/) [P]:
  - `--first_iter_pres_fac` 0.0
  - `--initial_pres_fac` 0.5
  - `--pres_fac_mult` 1.3
  - `--max_pres_fac` 1000
  - `--acc_fac` 1
  - `--bb_factor` 3
  - `--astar_fac` 1.2
  - `--max_router_iterations` 50

**Other routers and libraries**
- OrthoRoute (MIT): GPU PathFinder; nets routed sequentially; "not a general-purpose PCB autorouter" — [README](https://github.com/bbenchoff/OrthoRoute) [P]
- tscircuit capacity-autorouter (MIT, TypeScript): hypergraph pipeline; SimpleRouteJson with buses and diff pairs — [README](https://raw.githubusercontent.com/tscircuit/tscircuit-autorouter/main/README.md) [P]
- Topola (Rust, MIT, WIP, NLnet-funded topological router) — [NLnet](https://nlnet.nl/project/Topola/) [S]
- libMultiRobotPlanning (MIT, header-only C++14): A*, focal A*, SIPP, CBS, ECBS; no Python bindings — [README](https://raw.githubusercontent.com/whoenig/libMultiRobotPlanning/main/README.md) [P]
- `pathfinding` 1.0.22 (MIT): A*, Dijkstra, … no Theta* — [PyPI](https://pypi.org/pypi/pathfinding/json) [P]
- `rustworkx` 0.18.1 (Apache-2.0) and `networkx` 3.7 (BSD-3) — [PyPI](https://pypi.org/pypi/rustworkx/json) [P]

{{PF}}

### Inferences
- **Router strategy:**
  1. Ship Freerouting (headless, DSN/SES) as the baseline and fallback router and as the "judge".
  2. Build an in-house Rust A*/PathFinder router modelled on KiCadRoutingTools (MIT, so code reuse is GPL-compatible) for fast, controllable, LLM-steerable routing.
  3. Optionally reuse PCBWorld's KiCad-PNS bindings for push-and-shove cleanup. This requires building KiCad 9.0.8 from source with their binding layer (GPLv3 engine), which is heavy but proven.
- **LLM tool-calling agents are not yet competitive routers.** In PCBWorld, CP was 0 on medium boards and runs were 100–1000× slower. The LLM should orchestrate and constrain routers, not draw tracks.

#### Example formulation C — negotiated-congestion (PathFinder) multi-layer grid router (pseudo-code; prototype in `pathfinder_bench.py`)
```python
# nodes = (ix, iy, layer) at pitch = track+clearance; capacity 1; pads of other nets blocked; via edges cost VIA
hist = zeros(N); pres_fac = 0.0                         # VPR: first_iter_pres_fac = 0
for it in range(MAX_IT := 50):
    for net in order(nets):                               # critical/diff-pair/bus first, then by bbox
        if it > 0 and not overused(route[net]): continue  # reroute offenders only
        rip_up(net)
        cost = lambda v: (base[v] + hist[v]) * (1 + pres_fac * max(0, occ[v] + 1 - cap[v]))   # (b+h)*p
        tree = {pins(net)[0]}
        for sink in prim_order(pins(net)):
            tree |= astar(tree, sink, cost, h=1.2 * manhattan_lb, window=expand(bbox(net), 3 + it))
        commit(net, tree)
    if not any_overuse(): break
    hist += 1.0 * overuse                                   # acc_fac = 1
    pres_fac = 0.5 if it == 0 else min(pres_fac * 1.3, 1000)
# post: merge collinear segments, 45° smoothing, neck-down at pads, write tracks/vias via IPC CreateItems in one commit,
# run kicad-cli pcb drc; repair or fall back to Freerouting
```

### Gaps
- PCBWorld's KiCad binding layer was not inspected; its build size and maintenance cost across KiCad 10/11 are unknown.
- No published comparison of KiCadRoutingTools vs Freerouting on 4–8-layer boards with many BGAs was found beyond PCBWorld D3.
- No maintained Python-bound Theta*/any-angle router was verified.

---

## 6. Computational geometry (Shapely/GEOS, Clipper, R-trees, triangulation, SDF, Minkowski / no-fit polygons, nesting engines)

### Takeaway
- **Shapely 2.x** (BSD-3; bundles LGPL-2.1 GEOS) is the default for polygons and vectorized predicates. Its STRtree is immutable.
- **pyclipper** (MIT, Clipper1) has manylinux wheels and **MinkowskiSum/MinkowskiDiff**, which gives practical no-fit polygons. The Clipper2 binding `pyclipr` (Boost) ships **no Linux wheels**.
- For irregular-shape collision checking at scale, **jagua-rs** (Rust, MPL-2.0) is a maintained, state-of-the-art "collision detection engine" for nesting, with continuous rotation and minimum-separation support. **sparrow** (Rust, MIT) on top of it is a state-of-the-art nesting heuristic.
- The old NFP libraries are LGPL/GPL or abandoned.
- For triangulation use PythonCDT. Avoid `triangle` (non-free upstream).

**Own micro-benchmark [M] (`geom_bench.py`).** Courtyard rectangles at random positions; 5,000 single-part moves, each followed by "violates 0.2 mm clearance with anyone?". Cost per move-check in µs, single thread:

| N | NumPy AABB vs all | Python grid hash (2 mm cells) | rtree delete+insert+query | Shapely STRtree query (static tree) | STRtree rebuilt every move | Shapely exact octagons (STRtree + `dwithin`) | full all-pairs exact check (one shot) |
|---|---|---|---|---|---|---|---|
| 100 | 11.4 | 13.3 | 37.7 | 23.6 | 39.4 | 27.3 | 0.49 ms |
| 300 | 11.5 | 14.0 | 153.7 | 23.5 | 69.9 | 27.4 | 1.29 ms |
| 1000 | 14.9 | 14.7 | 62.7 | 24.6 | 280.7 | 31.8 | 4.95 ms |
| 3000 | 23.1 | 16.4 | 239.1 | 26.9 | 889.0 | 29.0 | 15.7 ms |

- STRtree build takes 0.1–0.6 ms.
- Clearance offset per polygon: pyclipper 12.7–14.6 µs with `arc_tolerance` = 5 µm (about 100 µs per polygon with a too-fine tolerance); Shapely `buffer` 8.4–22.7 µs.

Conclusions:
- At 20–1000 parts, a full exact polygon re-check of the whole board (≤5 ms) is cheap enough to run after every accepted LNS window or SA temperature step.
- Per-move checks cost about 12–30 µs in Python with any vectorized method. That caps Python SA at roughly 10⁴–10⁵ moves/s, which is why the hot loop belongs in Rust.
- rtree's per-move delete+insert is the slowest dynamic option here.

### Cited Findings
- Shapely 2.2.0 (BSD-3). STRtree is Sort-Tile-Recursive and "constructed directly at initialization and nodes cannot be added or removed". `query(geom, predicate=…, distance=…)` supports 'dwithin' and array inputs — [strtree.py](https://raw.githubusercontent.com/shapely/shapely/main/src/shapely/strtree.py) [P]. GEOS is LGPL-2.1 — [COPYING](https://raw.githubusercontent.com/libgeos/geos/main/COPYING) [P]
- `rtree` 1.4.1 (MIT, libspatialindex) supports deletion, insertion and bulk loading — [PyPI](https://pypi.org/pypi/rtree/json) [P]
- Clipper2 is Boost-licensed C++17; its README links "Why there haven't been any updates in the last 6 months" — [README](https://raw.githubusercontent.com/AngusJohnson/Clipper2/main/README.md) [P]
- `pyclipr` 0.1.8 files on PyPI are only `macosx_*_arm64` and `win_amd64` wheels plus an sdist. `pip download pyclipr --only-binary=:all:` fails on Linux/py3.13 — [PyPI JSON](https://pypi.org/pypi/pyclipr/json) [P][M]
- `pyclipper` 1.4.0 (MIT) has manylinux wheels and exposes `MinkowskiSum`, `MinkowskiSum2` and `MinkowskiDiff` — [PyPI](https://pypi.org/pypi/pyclipper/json) [P]; module inspection [M]
- **jagua-rs** (Gardeyn; MPL-2.0; INFORMS J. Computing) — [README](https://raw.githubusercontent.com/JeroenGar/jagua-rs/main/README.md) [P]; [arXiv 2508.08341](https://arxiv.org/abs/2508.08341) [P]
  - "designed to be used as a backend by optimization algorithms solving 2D nesting problems… Resolves millions of collision queries per second".
  - Supports "Continuous rotation & translation", reflections, "Holes and inferior quality zones", "Minimum separation distance between an item and any hazard", and a WASM target.
  - The broad phase is a dynamically updated quadtree. The paper reviews raster/NFP/trigonometric approaches and notes NFP robustness problems.
- **sparrow** (MIT, Rust ≥1.90): "state-of-the-art nesting heuristic for 2D irregular strip packing", built on jagua-rs — [README](https://raw.githubusercontent.com/JeroenGar/sparrow/main/README.md); [arXiv 2509.13329](https://arxiv.org/abs/2509.13329) [P]
- libnest2d is LGPL-3, from PrusaSlicer, SVGnest-inspired, C++11 header-only — [README](https://raw.githubusercontent.com/tamasmeszaros/libnest2d/master/README.md) [P]. pynest2d (Ultimaker CPython bindings) is LGPL-3 — [README](https://raw.githubusercontent.com/Ultimaker/pynest2d/main/README.md) [P]
- libnfporb is GPL-3. Its author: "There are way better alternatives to libnfporb out by now that is why I'm going to archive this repository" — [README](https://raw.githubusercontent.com/kallaballa/libnfporb/master/README.md) [P]
- deepnest-next is MIT, "originally based on SVGNest", moving core code to Rust — [README](https://raw.githubusercontent.com/deepnest-next/deepnest/main/README.md) [P]. SVGnest is MIT — [LICENSE.txt](https://raw.githubusercontent.com/Jack000/SVGnest/master/LICENSE.txt) [P]
- `PythonCDT` 2.0.2 (MPL-2.0 AND BSD-3 AND Apache-2.0+LLVM-exception) has wheels for Linux, macOS and Windows — [PyPI](https://pypi.org/pypi/PythonCDT/json) [P]
- The `triangle` wrapper is LGPL-3.0 over Shewchuk's Triangle: "Distribution of this code as part of a commercial system is permissible ONLY BY DIRECT ARRANGEMENT WITH THE AUTHOR" — [Triangle README (libigl mirror)](https://raw.githubusercontent.com/libigl/triangle/master/README) [P]
- `cgal` 6.0.1 (2024) is GPLv3+ and "still experimental"; scikit-geometry is LGPL-3.0 and not on PyPI — [PyPI cgal](https://pypi.org/pypi/cgal/json); [LICENSE](https://raw.githubusercontent.com/scikit-geometry/scikit-geometry/master/LICENSE) [P]
- MPL-2.0 can be combined with (L)GPL code as a "Larger Work" unless it is marked "Incompatible With Secondary Licenses" — [MPL 2.0 FAQ Q14](https://www.mozilla.org/en-US/MPL/2.0/FAQ/) [P]
- KiCad's IPC `GetPadShapeAsPolygon` returns pad copper as polygons — [board_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/board/board_commands.proto) [P]

### Inferences
- **Inner-loop collision checks:**
  - For SA/LNS on courtyard rectangles, a uniform grid hash or vectorized NumPy AABB check is fastest at our N.
  - For exact irregular courtyards, use Shapely `dwithin` on STRtree candidates in batch mode. When the Rust core matures, jagua-rs gives exact polygon checks with clearance at millions of queries per second.
- **Clearance offsetting:** use pyclipper on Linux (wheels; set `arc_tolerance`, or round joins explode in vertex count). Use Shapely `buffer` for prototyping, and a Rust Clipper2 crate inside the Rust core.
- **NFPs:** `pyclipper.MinkowskiDiff` is enough for courtyard NFPs. Prefer the jagua-rs approach over building an NFP library, given libnfporb's own deprecation.
- **License fit for a GPL-3.0 project:** MPL-2.0 (jagua-rs, PythonCDT) can be combined into a GPL "Larger Work" per Mozilla's FAQ. MIT (sparrow, pyclipper, rtree) and Apache-2.0 are fine. LGPL-3 (libnest2d/pynest2d) is GPLv3-compatible (inference; FSF list not fetched). Avoid `triangle`.

### Gaps
- jagua-rs has no Python bindings; using it means a PyO3 wrapper (not checked for existing community bindings).
- The FSF compatibility list (Boost, ISC, LGPL with GPLv3) could not be fetched.

---

## 7. Performance engineering (Rust/C++ cores via PyO3, incremental evaluation, GPU, parallel restarts)

### Takeaway
Keep orchestration and LLM tools in Python and put hot loops in Rust via PyO3/maturin. KiCadRoutingTools reports about 10× from moving A* to Rust. My pure-Python SA managed only about 10k moves/s at N=30, which is too slow for 1000-part detailed placement.

Use parallelism in three places:
- CP-SAT's multi-worker portfolio
- parallel cluster solves, which are embarrassingly parallel in the hierarchical scheme
- parallel Optuna trials

GPU only pays off at Cypress-scale boards with thousands of parts, or for very large routing lattices.

### Cited Findings
- `maturin` 1.15.0 ("MIT OR Apache-2.0") builds PyO3, cffi and uniffi crates — [PyPI](https://pypi.org/pypi/maturin/json) [P]
- KiCadRoutingTools: "Rust acceleration provides ~10x speedup vs pure Python" — [README](https://raw.githubusercontent.com/drandyhaas/KiCadRoutingTools/main/README.md) [P]
- Rustuna is "several times to several hundred times faster" than Optuna for cheap objectives — [PyPI optuna](https://pypi.org/pypi/optuna/json) [P]
- DREAMPlace GPU gives over 30× on million-cell VLSI — [README](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/README.md) [P]. Cypress small benchmarks took 200–1,765 s on 4 V100s including MOTPE exploration — [slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]
- OrthoRoute parallelizes inside the single-net SSSP; nets stay sequential — [README](https://github.com/bbenchoff/OrthoRoute) [P]
- jagua-rs: "millions of collision queries per second" — [arXiv 2508.08341](https://arxiv.org/abs/2508.08341) [P]
- [M] SA: about 10.7–11.2k moves/s at N=30 (Python + NumPy); CP-SAT model build time 0.01 s (N=30) to 0.2 s (N=1000). {{PERF}}

### Inferences
- **The Rust core should contain:**
  - incremental HPWL (per-net min/max with counts)
  - a grid-hash overlap check
  - RUDY bins
  - SA moves
  - A*/PathFinder
  - optionally a jagua-rs-based exact collision check
- **Python keeps:** CP-SAT models, Optuna, KiCad IPC I/O and the LLM tool layer.

### Gaps
- No direct Rust-vs-Python measurement for placement kernels beyond KiCadRoutingTools' routing claim.

---

## 8. Multi-fidelity evaluation (fast proxies during search, accurate checks at the end)

### Takeaway
The published PCB placers converge on a ladder that ends at a real router:
- Cypress, NS-Place and HiePlace all evaluate with Freerouting (Cypress: v1.9.0, 2 layers) and/or KiCad DRC.
- PCBWorld defines an engine-checked "Clean Pass" metric (fully routed AND zero DRC errors) and 7 other metrics on KiCad boards.

Our ladder:

| Level | Check | Cost |
|---|---|---|
| L0 | HPWL + hard-constraint check | µs |
| L1 | RUDY + net-crossing proxy (Cypress) | ms |
| L2 | coarse PathFinder (capped iterations) | seconds |
| L3 | Freerouting headless / KiCadRoutingTools / in-house router | seconds–minutes |
| L4 | `kicad-cli pcb drc` + PCBWorld-style CP metric | final |

### Cited Findings
- Cypress uses Freerouting v1.9.0 with two free copper layers; routability is the percentage of routed pin pairs. MOTPE trades wirelength, density and net crossing, then routes — [slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]
- NS-Place uses FreeRouting routed WL and vias plus KiCad DRVs — [arXiv 2210.14259](https://arxiv.org/abs/2210.14259) [P]
- PCBWorld defines CP = 1{routability = 1}·1{drc_errors = 0} and enumerates KiCad's 62 `DRCE_*` codes. Freerouting took 2.7–9.9 s per board on D2/D3 — [arXiv 2607.05915](https://arxiv.org/abs/2607.05915) [P]
- DREAMPlace has RUDY/RISA area adjustment (`adjust_rudy_area_flag`) — [params.json](https://raw.githubusercontent.com/limbo018/DREAMPlace/master/dreamplace/params.json) [P]
- Freerouting fidelity knobs are `-mp`, `-mt 0` and `--router.optimizer.improvement_threshold`; a full run takes "a few minutes to several hours" — [CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md); [README](https://github.com/freerouting/freerouting) [P]
- SMAC supports multi-fidelity — [PyPI](https://pypi.org/pypi/smac/json) [P]
- Apollo suggests wirelength/density placers can score low on routability (about 51%) — [arXiv 2504.18813](https://arxiv.org/pdf/2504.18813) [S]
- In Cypress's ablation, the net-crossing term cut crossings to 0.31× at a 1.13× HPWL cost — [slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]

### Inferences
- **Make Freerouting-on-2-layers (L3) the calibration target** for L1/L2 proxies on a held-out board set: PCBWorld D3 plus the Cypress small suite. Check proxy-to-routed rank correlation before trusting proxies inside Optuna.
- **Expose `evaluate(candidate, level)` to the LLM** so it spends L3/L4 only on Pareto finalists.

### Gaps
- No published correlation between RUDY or net-crossing proxies and PCB router completion was found.

---

## 9. Recommended solver stack for an LLM-driven KiCad placer/router

### Takeaway
A hybrid pipeline, validated piecewise by the literature and by my measurements:
- KiCad IPC I/O
- LLM decides clusters, sides and constraints
- per-cluster CP-SAT (soft macros, 2+ aspect variants) for constraint-heavy local placement
- either Cypress-style differentiable global placement (JAX/PyTorch: Gumbel orientation, two-sided density, net crossing, domain penalties) or a CP-SAT soft-macro floorplan
- CP-SAT min-displacement legalization
- SA (Rust) + windowed CP-SAT LNS detailed placement
- Optuna MOTPE (+ OptunaHub LLAMBO warm-start) tuning
- in-house Rust PathFinder/A* router modelled on KiCadRoutingTools
- Freerouting headless as baseline and fallback
- KiCad DRC / PCBWorld CP metric as the final judge

### Cited Findings
- Decomposition is needed. Monolithic exact models fail beyond about 50–100 parts: NS-Place MILP failed on 10/14 boards in 4 h; HiePlace's ILP baseline failed at 308–404 parts; my CP-SAT found nothing at 300/1000 parts. Hierarchical MP (HiePlace) handles 404 parts in ≤2 h, and my hierarchical CP-SAT+LNS stays feasible at 100–1000 parts (§1) [P][M]
- Cypress's differentiable recipe scales to 6.6k parts, with MOTPE tuning and Freerouting evaluation [P]
- Freerouting has the best clean-pass on medium real boards; KiCadRoutingTools is fastest; LLM agents are not routers (PCBWorld) [P]
- pyclipr lacks Linux wheels, while pyclipper and jagua-rs are viable (§6) [P][M]

### Inferences

**Subproblem → tool mapping**

| Subproblem | Primary tool | Alternatives / notes | License |
|---|---|---|---|
| Board I/O, writing placements and tracks | `kicad-python` IPC (`create_items`/commit, `get_pad_shapes_as_polygons`) | pcbnew SWIG (KiCad 10); `.kicad_pcb` parsing | MIT (KiCad GPL-3+) |
| Clustering, sides, constraints | LLM + netlist graph (rustworkx/NetworkX) + rules | Cypress assumes pre-assigned sides | Apache/BSD |
| Cluster placement (≤50 parts, hard decap/keep-out/alignment) | CP-SAT formulation A, 0.5 mm grid, "opt2" rotation, ≥2 aspect-ratio variants | Gurobi MP (HiePlace) as optional backend | Apache-2.0 |
| Global placement 100–1000 parts | (a) Cypress-style JAX/PyTorch loss (Gumbel orientation, two-sided density, net crossing, decap/keep-out/thermal penalties) or (b) CP-SAT soft-macro floorplan (as benchmarked) | Cypress itself (Apache-2.0, GPU, Bookshelf) | Apache-2.0 |
| Legalization | CP-SAT min-displacement model with hard constraints (`hier_place.py::legalize`) | Tetris + Abacus (Cypress), greedy (Rust) | Apache-2.0 |
| Detailed placement | SA (Rust, incremental HPWL/RUDY) + windowed CP-SAT LNS | tabu | own |
| Weight tuning / Pareto | Optuna MOTPE / NSGA-II (+ OptunaHub LLAMBO for first ~10 trials) | SMAC (multi-fidelity), BoTorch, pymoo | MIT/BSD |
| Diverse alternatives for the LLM | pyribs CMA-MAE over weights | pymoo fronts | MIT |
| Algorithm self-improvement | ReEvo/EoH/AlphaEvolve-style LLM code evolution against a sandboxed benchmark set | LLM4AD platform | own |
| Escape / fan-out | network-flow MILP (HiGHS/SCIP) or CP-SAT | SAT (ASP-DAC'08), CBS/ECBS | MIT/Apache |
| Routing | in-house Rust A*/PathFinder (VPR defaults) | KiCadRoutingTools (MIT, reuse), Freerouting headless (GPL-3), tscircuit (MIT, Node), PCBWorld PNS bindings (GPLv3 engine) | own/MIT/GPL |
| Geometry | Shapely 2 (batch), pyclipper (offset, Minkowski), grid hash / NumPy (inner loop), jagua-rs (Rust exact collision) | rtree for dynamic sets; PythonCDT for channels; avoid `triangle` | BSD/MIT/MPL |
| Verification | `kicad-cli pcb drc` + PCBWorld CP metric | Freerouting `-drc` JSON | GPL |

**GPL-3.0 notes:** see §1 and §6. Apache-2.0 compatibility is confirmed by the ASF, and MPL-2.0 combination by the Mozilla FAQ. Exclude OptiMathSAT and Triangle. Gurobi is optional and user-supplied.

### Gaps
- No end-to-end open implementation of this exact stack exists. The pieces are validated separately.
- Real-board validation (PCBWorld D3, Cypress small suite) of the placement half is the obvious next experiment.
