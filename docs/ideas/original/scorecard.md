# Scorecard: every idea from the joint place-and-route and layer-collapse work

Scope: verdict and headline per tested idea, one row each; mechanisms in [joint-pnr ideas](joint-pnr.md) and [layer-collapse](layer-collapse.md); numbers, conditions and provenance on the linked [research/joint](../../research/joint/README.md) pages. Not here: experiment log -> [joint-pnr-experiments](../../topics/placement/joint-pnr-experiments.md).
Keys: scorecard, verdict, merit, partial, no merit, jc, combo, beam, anneal, repair, negotiate, grad, slime, cpsat, llm, xf_minplus, xf_physmap, xf_pour, harmonic, learn_value, qd, jc2, obst, cplace, assign, pour

Conditions: 33 qualified A/B boards; KiCad DRC, kae.physics fast (place terms) and routed physics; 120 CPU-s per board; "vs seq" = place by HPWL, then route. Eras (v5 mostly 1 seed, v7, xf3) → [eras](../../research/joint/README.md#eras-and-caveats).
Verdicts: **Merit** beat its control on DRC or physics; **Partial** helps in some setting or as a component; **No merit** did not beat a simple control; **Not tested** idea only.

## Methods (place + route)

| # | Idea | Source domain | Tested as | Verdict | Headline | Page |
|---|---|---|---|---|---|---|
| — | Own grid router (halo clearance, negotiated congestion) | FPGA PathFinder | `route_only` | **Merit** (substrate) | human placements clean 0.85 (A) / 0.50 (B) vs tuned Freerouting 0.62 / 0.35 | [engine](../../research/joint/engine.md#results) |
| 43 | Physics place terms in the objective | kae.physics | `seq_phys`, `anneal_phys`, `combo` vs length+vias twins | **Merit** | fast physics 4.05× → 1.52× human (seq); routability unchanged | [physics-objective](../../research/joint/physics-objective.md#results) |
| — | Full routed physics at stage gates | kae routed recheck | `combo_full`, `jc_full` | **Partial** (promising) | jc_full routed 0.80× human (open hops flatter it); combo_full unfinished | [jc](../../research/joint/jc.md#jc), [combo](../../research/joint/combo.md#verdict) |
| L | **Joint layer collapse by continuation**: everything lifted, one coupling β | homotopy, deterministic annealing | `jc` | **Merit (best)** | best legal and clean in v5 and v7; +70% vias vs combo (v5) | [jc](../../research/joint/jc.md#jc) |
| L | Same, parts frozen after the lift | ablation | `jc_frozen` | Control | joint 0.52× copper on 24/24 boards: placement and routing not separable | [jc](../../research/joint/jc.md#jc) |
| 7 | Beam search over place-one-route-it | search | `beam` | **Merit** | completion 0.891 vs 0.868 greedy at equal CPU | [tree-search](../../research/joint/tree-search.md#results) |
| — | combo = beam → blocker repair → physics annealing | combination | `combo` (3 seeds) | **Merit** | more legal and complete on every seed; clean within noise | [combo](../../research/joint/combo.md#results) |
| 11 | Annealing whose cost is re-routed copper | VPR, Nag–Rutenbar | `anneal`, `anneal_phys` | **Merit** | −8% copper vs seq (1 seed) | [anneal-and-repair](../../research/joint/anneal-and-repair.md#results) |
| 12, 13 | Blocker-directed window repair (LNS + guided local search) | vehicle-routing LNS, GLS | `repair` | **Merit** (as a stage) | dev6 completion 0.921 vs 0.904 | [anneal-and-repair](../../research/joint/anneal-and-repair.md#results) |
| 1 | Unified negotiated congestion (parts and wires in one market) | PathFinder generalized | `negotiate` | **Partial** | best v5 single-method completion, +11% copper; wire prices must decay | [jc](../../research/joint/jc.md#predecessor-negotiate-idea-1-pathfinder-generalized) |
| 6 | Place one part, route it, next | hand layout | `grow` | No merit alone | same as seq; useful inside beam | [sequential-controls](../../research/joint/sequential-controls.md#verdict) |
| 2, 3, 26 | Envelope-theorem pin tension + Lagrange price gradient + pin-facing rotation | envelope theorem, Lagrangian relaxation | `tension` | No merit | equals seq as a driver | [forces-and-fields](../../research/joint/forces-and-fields.md#pin-tension-ideas-2-3-26) |
| — | SimPLR-style bloating of congested parts | VLSI routability placement | `bloat` | No merit | completion 0.748 | [forces-and-fields](../../research/joint/forces-and-fields.md#bloat-simplr-style-inflation) |
| — | A-priori spacing margins (control) | — | `seq_margin` | No merit | costs copper and legality on dense boards | [sequential-controls](../../research/joint/sequential-controls.md#results) |
| 8 | MCTS with routing rollouts | AlphaGo | `mcts` | No merit at this budget | 8–10 rollouts per part; trails beam | [tree-search](../../research/joint/tree-search.md#verdict) |
| 22, 23, 17 | Differentiable routing: soft-min shortest paths, gradient descent | Mensch–Blondel, Berthet | `grad` | No merit as a driver | soft-route direction improves 33% of moves vs HPWL 36% | [forces-and-fields](../../research/joint/forces-and-fields.md#soft-route-gradients-ideas-22-23-17) |
| 22 + 43 | Gradient global start + physics descent | combination | `grad_phys post=phys` | **Partial** | routed physics 1.00× human, lower completion | [forces-and-fields](../../research/joint/forces-and-fields.md#soft-route-gradients-ideas-22-23-17) |
| 20 | Physarum multi-commodity flow networks | slime-mould biology | `slime` | No merit | neutral as a router prior | [forces-and-fields](../../research/joint/forces-and-fields.md#physarum-networks-idea-20) |
| 36 | Exact CP-SAT window place-and-route | SP&R, Numberlink SAT | `cpsat` | No merit | 0/112 wins over heuristic repair | [anneal-and-repair](../../research/joint/anneal-and-repair.md#results) |
| 30 | LLM/VLM proposes moves, optimizer verifies | LLM agents | `llm` (agent as the LLM) | No merit (routing inconclusive) | use only for diagnosis | [llm-proposer](../../research/joint/llm-proposer.md#verdict) |
| T1 | Min-plus best-response maps in jc's part move | distance transforms, min-plus convolution | `xf_minplus` | **Inconclusive** (leans merit on vias) | vias down on every seed, equal clean | [jc-extensions](../../research/joint/jc-extensions.md#min-plus-best-response-maps-t1) |
| T2 | Exact physics maps replacing `coarse_map` in jc | Green's functions, spectral Poisson | `xf_physmap` | **No merit** | gain reversed by a replicate | [jc-extensions](../../research/joint/jc-extensions.md#exact-physics-maps-t2) |
| T4 | Pour-damage maps (layer-coupled sensitivity of pour R_eff) | variational principles, topological derivative | `xf_pour` (`pjc2`, `pjc`) | **Merit** (physics objective, coupled maps; needs confirming) | pjc2 routed physics 1.05 vs 1.18 | [pour-models](../../research/joint/pour-models.md#pour-damage-maps-in-jc-t4) |
| 19 | Harmonic-field routing; field pressure on parts | electrostatics, potential flow | `harmonic` (`hjc_press`) | No merit as a router; **partial** as pressure (ties jc) | 49.5% of streamline connections clearance-legal | [jc-extensions](../../research/joint/jc-extensions.md#harmonic-field-routing-and-field-pressure) |
| 32 | Learned value of partial boards to prune jc restarts | AlphaZero value nets | `learn_value` | No merit (provisional) | oracle pruning buys only 3–4% | [jc-extensions](../../research/joint/jc-extensions.md#learned-value-of-partial-boards) |
| 16 | Quality-diversity (MAP-Elites) archive over short jc continuations | evolutionary computation | `qd`, `qd_lv`, `qdh` | No merit vs jc (provisional); beats combo | ~8 archive cells per board | [jc-extensions](../../research/joint/jc-extensions.md#quality-diversity-archive-map-elites) |
| L′ | jc hardened (`jc2`) | ablations of jc | `jc2_fix`, `jc2_fixmp_lv` | **Merit likely** (unconfirmed) | fewer vias and open connections; 61–62 of 99 attempts | [jc](../../research/joint/jc.md#jc2-jc-hardened) |

## Layer collapse pieces

| Piece | Analog | Tested as | Verdict | Headline | Page |
|---|---|---|---|---|---|
| Topological layer bounds (graph thickness) | Euler, thickness | literature + `obst` | No merit | with vias, topology never forces > 2 layers; bound = 1 on real netlists | [bounds](../../research/joint/layer-collapse-analysis.md#layer-count-bounds-collapse_obst) |
| Cut-capacity bound | Cole–Siegel, Okamura–Seymour | `obst`, 112 boards | No merit as a predictor | layer counts = planes + BGA escape | [bounds](../../research/joint/layer-collapse-analysis.md#layer-count-bounds-collapse_obst) |
| BGA escape formula | escape routing | `obst` | **Merit** (narrow) | within ±1 of signal layers on 7 fine-pitch BGAs | [bounds](../../research/joint/layer-collapse-analysis.md#layer-count-bounds-collapse_obst) |
| Bus via-free layers by pin order (LDS, RSK) | Greene / RSK | `obst`, `cplace` | **Partial** | helps place-then-route, not the joint loop | [cplace](../../research/joint/layer-collapse-analysis.md#collapse-quantities-as-placement-terms-collapse_cplace) |
| Ratsnest crossings / cut overflow as placement terms | via proxies | `cplace` | No merit in the joint loop | proxies drop, routed vias do not | [cplace](../../research/joint/layer-collapse-analysis.md#collapse-quantities-as-placement-terms-collapse_cplace) |
| Collapse as a router: lift, exact layer assignment, realize | via minimization, planar max-cut | `assign` | No merit | optimal assignment no better than random | [assign](../../research/joint/layer-collapse-analysis.md#exact-layer-assignment-as-a-router-lifted-cost-as-a-placement-measure-collapse_assign) |
| Lifted cost as a placement measure | lifted relaxation | `assign` placement study | **Partial** (promising) | ρ 0.85 vs HPWL 0.51 | [assign](../../research/joint/layer-collapse-analysis.md#exact-layer-assignment-as-a-router-lifted-cost-as-a-placement-measure-collapse_assign) |
| Minimal-partition (soap-film) pours | Plateau, double bubble, MBO | `pour` | No merit | interleaved rails fail | [pours](../../research/joint/pour-models.md#minimal-partition-and-wulff-pours) |
| Octilinear Wulff pours | crystalline variational problems | `pour` | No merit | never better than isotropic | [pours](../../research/joint/pour-models.md#minimal-partition-and-wulff-pours) |
| Pour score as a placement term | Laplace conductance | `pour` placement study | **Partial** | full pour R tracks routed physics; cheap score does not | [pours](../../research/joint/pour-models.md#minimal-partition-and-wulff-pours) |
| Over/under at crossings as knot diagrams; origami layer ordering | knot theory, flat folding | literature | No merit | nothing transfers | [layer-collapse](layer-collapse.md) |

## Engine and harness findings

Harness bugs (relative `--command` paths, locked footprints off-board, joint scoring) → [harness lessons](../../research/joint/README.md#harness-and-engine-lessons); legality calibration and DRC fixes → [engine versions](../../research/joint/engine.md#engine-versions); thermal starvation from placement crowding → [engine verdict](../../research/joint/engine.md#verdict); fast vs routed physics Spearman 0.55 → [physics-objective](../../research/joint/physics-objective.md#results).

## Not tested (idea only)

Joint-pnr ideas 4, 5, 9, 10, 14, 15, 18, 21, 24, 25 (tested only as a proxy in `cplace`), 27, 28, 29, 31, 33, 34, 35, 37–42: list with status in [research/ideas](../../research/ideas.md#joint-place-and-route-untested-catalog-ideas).
