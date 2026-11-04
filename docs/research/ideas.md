# Untested ideas, with mechanisms

Scope: our ideas that were written down but not built (or only partly tried), with the status of every partial test; mechanisms live in the linked catalog entries. Not here: tested methods -> [research map](README.md); surveys of others' work (about 1,700 one-line items, prior art by others) -> inventories [algorithms](../ideas/inventory-algorithms.md), [ecosystem](../ideas/inventory-ecosystem.md), [LLM, data and UX](../ideas/inventory-llm-data-ux.md), [practice and evaluation](../ideas/inventory-practice-evaluation.md), [rules: high-speed and EMI](../ideas/inventory-rules-hs-emi.md), [rules: power](../ideas/inventory-rules-power.md).
Keys: untested ideas, defensive publication, prior art, original ideas, transplants, joint place-and-route catalog, problem transformations, T1-T12, free part angles, edge-mate, physics-first catalog

**Status:** untested idea, unless an entry says otherwise.
**First published:**
- original ideas: 2026-10-21, commit [7ac84d6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7ac84d621fa687fb17ce63f0cb1f350594fa7ee9) on `main`;
- cross-domain transplants: 2026-10-21, commit [0ea98bf](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0ea98bff673d70b65a5459dcdf547046dd3fac34) on `main`;
- joint place-and-route catalog: 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6`;
- problem transformations: 2026-10-24, commit [7ae90d8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7ae90d849fd4697b32ecd76ac579b9f7d2558059) on the same branch.

## Contents

- [Original ideas (58)](#original-ideas-58)
- [Cross-domain transplants (33)](#cross-domain-transplants-33)
- [Joint place and route: untested catalog ideas](#joint-place-and-route-untested-catalog-ideas)
- [Problem transformations](#problem-transformations)
- [Untested pieces of the kae line](#untested-pieces-of-the-kae-line)
- [The physics-first catalog (about 890 ideas)](#the-physics-first-catalog-about-890-ideas)

## Original ideas (58)

Catalog and one-line index: [docs/ideas/original/](../ideas/original/README.md); full mechanism per idea in its theme file (I intent, N negotiation, P placement, R routing, S system loop, V verification, L learning/data, U workflow/UX). Placement ids P1–P10 are not the P0–P7 ids of [strategy-candidates](../topics/placement/strategy-candidates.md). Of the "top 10 to try first" (P6, N8, N7, V2, V1, I4, I1+I2, R2, P1, R1) only two were tried, both in part: V2 as a fixed suite, P1 in a discrete form.

Partial tests and related results (every other original idea: untested):

| Id | Status | Result / related page |
|---|---|---|
| I1 Physics budget ledger, R2 Shadow return nets | untested | refined / generalized by the [physics-first catalog](#the-physics-first-catalog-about-890-ideas) |
| N1 Resource market | closest test partial | unified negotiated congestion of parts and wires partly worked ([negotiate](joint/jc.md)) |
| N7 Hot-loop nH micro-placer | untested | later physics work: estimate loop L from height × squares, not area ([physics](physics/README.md)) |
| N8 Decap-to-pin assignment | untested | padne is DC-only, so it cannot validate this |
| P1 Router-probe pseudo-gradients | **partial** | discrete form tried twice: blame-driven re-annealing ([ap-sa-loop](placement/autoplace.md)), blocker-directed window repair ([blocker-repair](joint/anneal-and-repair.md)); continuous-force version untested |
| P2 Contracted floorplan + cut check | untested | cut-capacity bounds as layer predictors did not work ([collapse-obst](joint/layer-collapse-analysis.md)), a different use |
| P5 Verified motif distributions | untested | data step exists as measured decap priors ([measured-priors](../topics/data/measured-priors.md)) |
| P7 Live topological sketch objective | closest test | lifted layer-collapse cost as a placement measure ranked placements at ρ 0.85 vs 0.51 for HPWL ([collapse-assign](joint/layer-collapse-analysis.md)) |
| R5 Router-portfolio bandit | untested | a fixed restart portfolio (not a bandit) worked ([restart-portfolio-and-budgets](routing/kae-restart-portfolio.md)) |
| S6 Successive halving | **partial** | best-of-N ranked by in-loop DRC reached 12/14 ([ap-sa-best](placement/autoplace.md)); a QD archive did not beat `jc` ([qd-archive](joint/jc-extensions.md)) |
| V2 Red-team reward-hacker gate | **partial** | fixed hand-written red-team suite guards the benchmark ([redteam_cheats.py](../../bench/tests/redteam_cheats.py)); no adversarial agent |
| L5 Git-history repair pairs | untested | the [board corpus](data/board-corpus.md) pins single commits only |

## Cross-domain transplants (33)

Ranked table with mechanisms: [cross-domain-transplants](../ideas/cross-domain-transplants.md) (other fields' methods; the PCB mapping and the ranking are ours). Related results (all other rows untested):

| # | Transplant | Result / related page |
|---|---|---|
| 7 | Polygon-partition MCTS global router | related form: MCTS did not work at our budget ([mcts](joint/tree-search.md)) |
| 9 | QD portfolio with legalizer repair | tried: no gain over `jc` ([qd-archive](joint/jc-extensions.md)) |
| 11 | Silkscreen refdes by map labelling | the `kae` placer has a related silk pass ([placement](placement/README.md)) |
| 15 | LLM as MAPF meta-controller | our grid router uses PathFinder without an LLM ([pnr-engine](joint/engine.md)) |
| 17 | SAT/ZDD local windows | tried as exact CP-SAT windows: no merit ([cpsat-windows](joint/anneal-and-repair.md)) |
| 26 | MCTS over coarse placement decisions | related result: [mcts](joint/tree-search.md) |

## Joint place and route: untested catalog ideas

Source: the 42-idea catalog [docs/ideas/original/joint-pnr.md](../ideas/original/joint-pnr.md) (first on branch `claude/keen-wright-mlkjv6`; mechanisms there) and its [literature survey](../../research_notes/joint-pnr/literature-survey.md). Tested (pages in the [joint area](joint/README.md)): 1–3, 6–8, 11–13, 16, 17, 19, 20, 22, 23, 26, 30, 32, 36, 43; 17 and 23 were folded into the differentiable-routing test ([soft-route-grad](joint/forces-and-fields.md)).

Untested: 4 congestion game (tests whether global prices matter), 5 auction for board area, 9 space-colonization growth, 10 dungeon-generator layout, 14 tabu over part swaps with route reuse, 15 CMA-ES over poses, 18 copper as charge (only the overflow-pushes-pads part exists, inside [soft-route-grad](joint/forces-and-fields.md)), 21 homotopy continuation of clearance, 24 Tutte embedding seed, 25 crossing-number objective (tried only as a term inside other objectives: [collapse-cplace](joint/layer-collapse-analysis.md), [ap-crossing-halo-ablation](placement/autoplace.md)), 27 planar sub-netlist layering, 28 multigrid V-cycle, 29 channel reservation (= corridor contract S1), 31 LLM-evolved coupling policy, 33 diffusion on the joint state, 34 imitation of human routing order, 35 factory-game solvers, 37 chemical plant piping, 38 ship cable harness, 39 urban co-generation, 40 microfluidic biochip co-design, 41 protein side-chain packing, 42 origami and knot routing (literature review found no merit).

## Problem transformations

Source: [research_notes/transformations/transformations.md](../../research_notes/transformations/transformations.md) (first on `claude/keen-wright-mlkjv6`); each entry there gives mapping, known results, what breaks, payoff, test plan, novelty note.

Built and run: T1 min-plus best-response maps ([minplus-maps](joint/jc-extensions.md)); T2 exact Green's-function physics maps ([exact-physics-maps](joint/jc-extensions.md)); T4 pour-damage maps ([pour-damage-maps](joint/pour-models.md)).

Untested:
- **T3 Coupling as an additive A\* edge cost.** Aggressors' vector potential over a plane A = G ⊛ J, kernel (μ0/4π)·ln(1 + (2h/s)²). |A·dl| along a candidate path bounds the mutual inductance, so coupling becomes an edge cost. Ranked 4th of the transformations.
- **T5 Satellite assignment.** Decaps and pull-ups to tiled slots around each IC by exact Hungarian matching on a separable Σ1/L_i cost; Frank–Wolfe steps across groups.
- **T6 Homotopy class in the A\* state.** Carry the H-signature (a free-group word) in the A\* state to get per-class route alternatives.
- **T7 Legalization as optimal transport**, minimizing total displacement.
- **T8 LPA\*/D\* Lite incremental re-routing** after annealing moves.
- **T9 Frustrated plaquettes → via-forcing map.** Places where vias are forced, by min-weight matching in the dual graph.
- **T10 Lindström–Gessel–Viennot / Fomin determinant** as a one-layer routability score.
- **T12 Parametric min-cut** for splitting a region between two pours.

Tested in notes only, dropped: T11 extremal-length bounds on pour resistance (exact on rectangles, 2–200× loose on perforated pours); DCT-preconditioned CG on masked pours (did not converge). Checked and dropped without tests: braids, knots, Noether, Koopman, a tropical reading of `jc`, Minkowski sums, steerable filters, eikonal, Radon, Morse, spectral/SOS/QUBO, sheaves.

## Untested pieces of the kae line

Built on branch `claude/vigilant-mayer-i91rrr`, never measured; off by default. Tested parts of this line: [routing](routing/README.md), [placement](placement/README.md), [joint](joint/README.md), [physics](physics/README.md).

- **Free part angles.** `kae place --angles STEP`: parts take any multiple of STEP degrees in the annealer; heatsink-mount packages keep right angles; CP-SAT stays on right angles. Paired test `tools/research/place/anglepolish.py`: both arms start from the same finished legal placement and get the same number of low-temperature moves (geometric schedule T0·hot → T0·1e-4, final legality weight, same seed), scored on HPWL and the physics scorecard. No recorded paired result. First appeared in [6a32272](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6a322723ca7e85f6136de3655071a9c132c2b163) and [e171267](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e171267e73ad11b230df15ac32a9ef9e2e832be0), 2026-10-23.
- **Edge-mate.** Footprints that carry Edge.Cuts (edge connectors, cut-outs) are placed by mating their outline segments to the board outline (`kae/src/kae/place/edges.py`, `--edge-mate`). The six outline-incomplete tasks stayed held out, so no result. First appeared in [1120fc0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1120fc039a1dbb970fe7f05bfe731f6513094e5d), 2026-10-22.

## The physics-first catalog (about 890 ideas)

[docs/ideas/physics-first/](../ideas/physics-first/) (first on branch `claude/vigilant-mayer-i91rrr`): about 660 ideas in eleven theme files (rule replacements, a design language, reasoning and joint place-route; optimization and simulation; power, SI/EMI/RF, thermal, high-voltage and manufacturing; critics and cross-domain transplants) + 232 in seven first-principles lens files. Builds on original ideas I1, N7, N8, R2, V1, V2 without repeating them. Untested unless a number is tagged [C] (computed by us); computed parts: [physics area](physics/README.md).
