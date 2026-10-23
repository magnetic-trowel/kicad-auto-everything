# Exact solvers for placement and escape: CP-SAT, MILP, SMT, MaxSAT

**TL;DR**
- **Monolithic exact models with free rotation scale poorly**: our monolithic CP-SAT stays feasible to ~200 parts but has competitive HPWL only to ~100 (single instance, 4 workers) and found no solution at 300/1000 parts in 300 s (UNKNOWN); NS-Place's vanilla MILP found no feasible placement in 4 h for 9–10 of its 14 boards (the note's count and per-board list disagree); HiePlace's ILP baseline gave no result at 308–404 parts; Z3 SMT needed up to 45,474 s.
- Exact solvers work when **decomposed**: per-cluster placement, legalization with relative order fixed, windowed LNS. Our hierarchical CP-SAT + LNS beat monolithic CP-SAT by 22–55% HPWL at 100 parts and stayed feasible at 300 and 1000 ([benchmarks](benchmarks.md)).
- **Free 4-way rotation is the main driver of difficulty**: fixing orientations upstream made N=300 feasible in 82.6 s; decap constraints were not the bottleneck.
- **OR-Tools CP-SAT (Apache-2.0)** is the most practical exact engine (NoOverlap2D over optional intervals, hints, packing-LNS workers) — a feasibility/legalization engine, **not** an HPWL optimizer (SA beats it on HPWL at small N; lower bounds are 2.5–25% of incumbents with rotation, 51% with fixed orientation).
- MILP (HiGHS MIT, SCIP Apache-2.0) suits network-flow subproblems such as escape; Gurobi, OptiMathSAT and Triangle are excluded.

## Key facts

**CP-SAT core facts** ([cpsat-primer](https://raw.githubusercontent.com/d-krupke/cpsat-primer/main/chapters/advanced_modelling.md) [P]; ortools 9.15.6755, Apache-2.0)
- `add_no_overlap_2d(x_intervals, y_intervals)`: for each pair, x- or y-intervals disjoint; if either interval is optional, the whole box is optional.
- Rotation encoding: `rotated` Bool + width/height over `Domain.from_values([w, h])` + `add_allowed_assignments`; optional intervals with `is_present` give a knapsack variant.
- "CP-SAT is good at finding a feasible packing, but incapable of proving infeasibility in most cases"; rotations make it harder.
- Resolution sensitivity (9.3 → 9.8): 1× 0.02 → 0.03 s; 100× 7.6 → 1.1 s; 1000× 75 → 40.3 s; 10,000× ">15 min" → 0.4 s ("not stabilized").
- NoOverlap2D parameters ([sat_parameters.proto](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto)): timetabling/energetic/area-energetic reasoning default **off**; `max_pairs_pairwise_reasoning_in_no_overlap_2d` 1250; `no_overlap_2d_boolean_relations_limit` 10; `maximum_regions_to_split_in_disconnected_no_overlap_2d` (0 = off) detects domains split by fixed boxes; `use_linear3_for_no_overlap_2d_precedences` (default true) helps when inter-box distance is in the model.
- Packing LNS workers: `packing_precedences_lns`, `packing_rectangles_lns`, `packing_slice_lns`. Warm start via `add_hint` ("only benefits from complete hints"; `fix_variables_to_their_hinted_value` for debugging; `hint_conflict_limit` 10). LNS is the primer's route for bigger problems.
- **API drift [M]**: the primer's protobuf custom-subsolver recipe raises `TypeError` in 9.15; working form: `p = cp_model_helper.SatParameters(); …; solver.parameters.subsolver_params.append(p); solver.parameters.extra_subsolvers.append(p.name)`.

**PCB-scale literature**
| Source | Finding |
|---|---|
| NS-Place ([arXiv 2210.14259](https://arxiv.org/abs/2210.14259) [P]) | Big-M MILP (`x_i + r_i h_i + (1−r_i) w_i ≤ x_j + W(p_ij+q_ij)`); vanilla: no feasible placement in 4 h for "10/14" designs per the note, but its own per-board list gives feasible results on 5 (PCB1 8 parts 2.7 s; PCB2 18 parts 6.3 s; PCB3/8/12, 34/36/58 parts, hit 4 h with a feasible solution), which leaves 9; none for PCB4 (28 parts, 6 locked); recheck the paper; with GD relative positions 4.9–6,008 s for ≤64 parts; 1,570-part board hit 14,400 s; solver unnamed |
| HiePlace ([PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J156-TCAD2026-HiePlace.pdf) [P]) | Gurobi MP inside a hierarchy; 15 industrial boards (density 0.58–0.81, 13–404 parts, 35–2,455 pins) + 4 academic; 0.02–120 min; Floorplet ILP 30–240 min, none at 308–404 parts |
| Z3 SMT floorplanning ([arXiv 1709.07241](https://arxiv.org/abs/1709.07241) [P]) | Without → with rotation: n30 64 → 1,220 s; n50b 569 → 45,474 s; n100 315 → 8,745 s; n300 932 → 26,777 s; MCNC 2,013–29,282 s; needed spatial clustering |
| CDCL vs CP-SAT vs MILP ([arXiv 2512.18034](https://arxiv.org/abs/2512.18034) [P]) | 2×2–6×6 facility grids: CDCL dominates feasibility, CP-SAT proves optimality on 5×5/6×6 in 60 s, CBC MILP exponential; CDCL → CP-SAT warm start reaches optimum faster (tiny instances) |
| SMT analog placement (DATE'16) | Solver time *decreases* as physical constraints increase [S] |
| Holodeck MILP | Gurobi disjunctions with binaries for scene layout ([scene transplants](../placement/scene-layout-transplants.md)) |

**MILP / SMT / MaxSAT tooling** (PyPI metadata 2026-10-20 [P] unless noted; fit for GPL-3.0-or-later)
| Package | License | Fit |
|---|---|---|
| highspy 1.15.1 (HiGHS) | MIT (HiPO builds Apache) | OK |
| SCIP 10 / pyscipopt 6.3.0 | Apache-2.0 since 8.0.3 [S] / MIT | OK |
| z3-solver 5.3.1.0 | MIT | OK |
| python-sat (PySAT) | MIT; "easy … to implement a MaxSAT solver" | OK |
| gurobipy 13.0.3 | Proprietary | Exclude |
| OptiMathSAT | Research/evaluation only, no commercial use [S] | Exclude |

**Escape routing as MILP/SAT**: unordered escape optimal by network flow; ordered exactly by SAT (ASP-DAC'08); two-stage flow ILP for escape + area routing (PeerJ CS 499); MonoSAT SAT + flow for multi-layer ([escape](../routing/escape-routing.md)) [S/P].

**LLMs writing constraint models**: Text2Zinc ≤25.39% (GPT-4, MiniZinc); CP-Bench ~70% with documentation-rich prompts, repeated sampling and self-verification, Python (CPMpy, OR-Tools CP-SAT) easier than MiniZinc; per-global-constraint agent ensembles beat CoT ([arXiv 2503.10642](https://arxiv.org/abs/2503.10642), [2506.06052](https://arxiv.org/abs/2506.06052), [2509.08970](https://arxiv.org/abs/2509.08970) [S]).

**Formulation A — CP-SAT placement with rotation, sides, keep-outs, decap proximity** (benchmarked as `cpsat_place.py`, [solver_toolbox.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)):
```python
m = cp_model.CpModel(); g = 0.5                      # mm per grid unit; refine only in windows
for c in comps:
    r = [m.new_bool_var(f"r{c}_{k}") for k in range(4)]; m.add_exactly_one(r)   # 0/90/180/270
    sw = m.new_bool_var(""); m.add(sw == r[1] + r[3])                           # swapped dims
    x = m.new_int_var(0, BW - min(W0, H0), ""); y = m.new_int_var(0, BH - min(W0, H0), "")
    top = m.new_bool_var("")                                                    # side (2-sided only)
    for (w, h, lit) in ((W0, H0, ~sw), (H0, W0, sw)):                           # "opt2" encoding
        m.add(x + w <= BW).only_enforce_if(lit); m.add(y + h <= BH).only_enforce_if(lit)
        pres = and_(lit, top) if two_sided and not c.tht else lit                 # THT occupies both sides
        X_TOP.append(m.new_optional_fixed_size_interval_var(x, w, pres, ""))
        Y_TOP.append(m.new_optional_fixed_size_interval_var(y, h, pres, ""))      # + same for bottom
    for p in c.pins: PX[p] = x + sum(r[k]*dx[p][k] for k in range(4)); PY[p] = y + sum(r[k]*dy[p][k] for k in range(4))
for (kx, ky, kw, kh) in keepout_rects:              # outline complement + keep-outs as fixed boxes
    X_TOP.append(m.new_fixed_size_interval_var(kx, kw, "")); Y_TOP.append(m.new_fixed_size_interval_var(ky, kh, ""))
m.add_no_overlap_2d(X_TOP, Y_TOP); m.add_no_overlap_2d(X_BOT, Y_BOT)
for (cap_pin, ic_pin, dmax) in decaps:               # hard L1 ball = 4 linear constraints
    for sx in (1, -1):
        for sy in (1, -1): m.add(sx*(PX[cap_pin]-PX[ic_pin]) + sy*(PY[cap_pin]-PY[ic_pin]) <= int(dmax/g))
    m.add(top[cap] == top[ic])                       # or allow opposite side under a BGA
# exact pin-level HPWL via add_max_equality/add_min_equality per net; lexicographic symmetry breaking for
# interchangeable parts; add_hint from SA/analytical placement; num_workers 8; 30 s
# LNS: fix (x, y, r) outside a k-NN window, hint the window, solve 2 s, accept if better
```

## Recommendations for our system
- Use CP-SAT for: cluster placement (≤~50 parts with hard decap/keep-out/alignment), min-displacement legalization, constraint-heavy windows; feed hints from analytical/SA placement ([legalization](../placement/legalization.md)) [M/I].
- Monolithic CP-SAT only ≤~100 parts at 0.5 mm; otherwise cluster (IC + passives) → soft macros with ≥2 aspect-ratio variants → top-level floorplan → windowed LNS on a **window sub-model** (free parts as variables, neighbours fixed, external pins constant) [M].
- **Fix orientations upstream** (rules, LLM, continuous placer argmax) at scale; keep one dedicated packing subsolver worker (area-energetic + energetic + timetabling, 5,000 pairs) [M].
- Use 0.5 mm global grid (0.1 mm made first-feasible 12× slower at N=100); "opt2" rotation encoding for N ≥ 100 (one instance; all measured hierarchical/LNS/legalization runs used "var"); turn on disconnected-region splitting when keep-outs split the board; lexicographic symmetry breaking for identical decaps [M].
- Do not let the LLM write CP models from scratch: provide a tested template and let it add typed constraints from a vocabulary [I].
- MILP (HiGHS/SCIP) or CP-SAT for escape flow models; MonoSAT (`-DGPL=OFF` to avoid GPLv2 code) for multi-layer escape [I].

## Conflicts and open questions
- No open-source CP-SAT PCB placer found; HiePlace code not found; our instances are synthetic (irregular outlines, many fixed parts, height/thermal/EMI rules absent).
- CP-SAT's weak HPWL relaxation means it cannot certify placement quality even at N=30.

## Sources
- research notes: [solver_toolbox.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [placement_algorithms.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [cross_domain_ideas.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)
- Tags: [M] = measured in the notes' micro-benchmarks (4 vCPU, OR-Tools 9.15).

See also: [benchmarks](benchmarks.md) · [placement/legalization](../placement/legalization.md) · [recommended-stack](recommended-stack.md)
