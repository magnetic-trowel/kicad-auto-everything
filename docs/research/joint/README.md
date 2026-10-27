# Joint placement and routing

Methods that place parts and route copper together instead of one after the other. Most of this area
is the **pnr line**: an own place-and-route engine (2026-10-24 to 2026-10-27) on which 30 methods were
built and benchmarked against KiCad DRC and kae physics. The kae line's joint loop also belongs here.

Main findings:
- Placement and routing are not separable: the same continuation with parts frozen after the start used
  about twice the copper on 24 of 24 boards ([jc.md](jc.md)).
- Physics terms in the placement objective cost nothing in routability ([physics-objective.md](physics-objective.md)).
- What worked keeps several alternatives alive and judges them by real routing (beam search, annealing,
  restarts, continuation). Continuous forces, exact solvers and an LLM proposer did not beat simple
  controls.

## Read this first: eras and caveats

- **Two evaluation eras, not comparable.**
  - **v5 era:** engine v5, harness v3, `--kinds place --probe self`, mostly **1 seed**.
  - **v7 / xf3 era:** harness score v7, `--kinds joint`, engine v6.3 or the fixed engine 4c4330a, **3
    seeds**. The headline set is the 28 boards that engine v6.4 leaves unchanged.
  - Numbers from different eras never share a table on these pages.
- **Partial baselines.** The v7 jc baselines stopped at 88 (jc) and 94 (jc_lv) of 99 attempts and have
  no physics scores. v7 comparisons against jc use only the boards with all seeds.
- **jc2 is unconfirmed:** it ran 61 and 62 of 99 attempts, with no physics scoring.
- **Fast router evidence covers 2 boards** (commit messages); there is no suite-level run.
- **Small samples.** All runs use ab33, the 33 qualified A/B boards (≤ 200 pads), with 120 CPU-s per
  board. Physics is measured on the 10 of them that have physics structures (phys10). kae's physics
  priors are unmeasured, so physics ratios are relative.
- The kicad-cli DRC on the re-opened board is the judge. A router's own log is not a score.

## Area map

| path | status | one-line result | page | code |
|---|---|---|---|---|
| pnr engine (halo grid, PathFinder, FFT legal maps, `route_only`) | worked (substrate) | Human placements routed clean 0.85 (A) / 0.50 (B) in seconds vs tuned Freerouting 0.62 / 0.35 (v5) | [engine.md](engine.md) | `tools/research/pnr` |
| fast router (`PNR_FAST`) | worked, thin evidence | 1.7–6.8× less CPU and far fewer unrouted connections on 2 boards; jc no longer bimodal | [engine.md](engine.md#fast-router-pnr_fast-2026-10-26) | `pnr/router.py` |
| anytime output | engineering, untested alone | Writes every improving legal board; stops when fully routed | [engine.md](engine.md#anytime-output-anytimepy-2026-10-27) | `pnr/anytime.py` |
| physics place terms in the objective | worked | Place physics 4.05× → 1.52× human (v5); completion unchanged | [physics-objective.md](physics-objective.md) | `pnr/physics.py`, `methods_phys.py` |
| physics scorer | tool, worked | Only 10/33 boards have physics; fast vs routed Spearman 0.55 | [physics-objective.md](physics-objective.md#physics-scorer-pnr_physphysics_scorepy) | `pnr_phys` |
| seq (control) | control | v7: legal 0.893, clean 0.607, completion 0.904 | [sequential-controls.md](sequential-controls.md) | `pnr/methods.py` |
| seq_margin | did not work | Legal 0.727, +19% copper (v5) | [sequential-controls.md](sequential-controls.md) | `pnr/methods.py` |
| grow (place one part, route it) | did not work alone | Same as seq; useful inside beam | [sequential-controls.md](sequential-controls.md) | `pnr/methods.py` |
| anneal on routed cost | worked | Legal 0.848, clean 0.576, −8% copper (v5, 1 seed) | [anneal-and-repair.md](anneal-and-repair.md) | `pnr/methods.py` |
| blocker-directed repair | worked (as a stage) | dev6 completion 0.921 vs 0.904 | [anneal-and-repair.md](anneal-and-repair.md) | `pnr/methods.py` |
| CP-SAT windows | did not work | 0 of 112 wins vs heuristic repair; no window optimal | [anneal-and-repair.md](anneal-and-repair.md#cpsat-idea-36-spr-numberlink-sat-as-the-repair-window-solver) | `pnr_cpsat` |
| beam search | worked (moderate) | Completion 0.891 vs 0.868 greedy, −8% wire (v5, 1 seed) | [tree-search.md](tree-search.md) | `pnr_mcts` |
| MCTS | did not work at this budget | 8–10 rollouts per part; trails beam | [tree-search.md](tree-search.md) | `pnr_mcts` |
| combo (beam → repair → anneal_phys) | worked | v7: clean 0.667 vs 0.607, −13% copper, −54% vias vs seq | [combo.md](combo.md) | `pnr/methods_combo.py` |
| pin tension | did not work | Completion 0.871, physics 4.2× | [forces-and-fields.md](forces-and-fields.md#pin-tension-ideas-2-3-26) | `pnr/methods.py` |
| bloat | did not work | Completion 0.748 | [forces-and-fields.md](forces-and-fields.md#bloat-simplr-style-inflation) | `pnr/methods.py` |
| soft-route gradients (grad, grad_phys) | did not work as driver; partial for physics | Direction test 33% vs HPWL 36%; grad_phys routed physics 1.00× | [forces-and-fields.md](forces-and-fields.md#soft-route-gradients-ideas-22-23-17) | `pnr_grad` |
| Physarum | did not work | Prior neutral, motion near no-op | [forces-and-fields.md](forces-and-fields.md#physarum-networks-idea-20) | `pnr_slime` |
| LLM move proposer | did not work | Matched annealing on 4 boards; ~110× worse than anneal_phys on physics | [llm-proposer.md](llm-proposer.md) | `pnr_llm` |
| layer-count bounds | did not work (escape formula narrow merit) | Sound bounds never exceed 2 layers; BGA escape within ±1 | [layer-collapse-analysis.md](layer-collapse-analysis.md#layer-count-bounds-collapse_obst) | `collapse_obst` |
| exact layer assignment; lifted cost | router did not work; measure partial | Optimal assignment ≤ random control; lifted cost ρ 0.85 vs HPWL 0.51 | [layer-collapse-analysis.md](layer-collapse-analysis.md) | `collapse_assign` |
| collapse terms in placement | did not work | Proxies drop, routed vias do not (118 vs 117) | [layer-collapse-analysis.md](layer-collapse-analysis.md#collapse-quantities-as-placement-terms-collapse_cplace) | `collapse_cplace` |
| negotiate | partial | Best v5 single-method completion 0.897, +11% copper | [jc.md](jc.md#predecessor-negotiate-idea-1-pathfinder-generalized) | `pnr/methods.py` |
| jc (joint layer collapse) | worked (best family) | v5 legal 0.879, clean 0.667; joint vs frozen 0.52× copper on 24/24 | [jc.md](jc.md) | `collapse_joint/jc.py` |
| jc2 (jc hardened) | likely worked, unconfirmed | Vias −17% / −30%, open connections −10% / −20% (61–62 of 99 attempts) | [jc.md](jc.md#jc2-jc-hardened) | `collapse_joint/jc2.py` |
| harmonic field routing / pressure | router did not work; pressure ties jc | Streamlines 49.5% clearance-legal | [jc-extensions.md](jc-extensions.md#harmonic-field-routing-and-field-pressure) | `harmonic` |
| learned value of partial boards | did not work | Oracle pruning ceiling 3–4%; learned ≈ 0 | [jc-extensions.md](jc-extensions.md#learned-value-of-partial-boards) | `learn_value` |
| QD archive (MAP-Elites) | did not work vs jc | Clean 0.682 vs 0.659 (noise), +1–2% copper | [jc-extensions.md](jc-extensions.md#quality-diversity-archive-map-elites) | `qd_archive` |
| min-plus best-response maps (T1) | inconclusive, leans merit (vias) | Vias −9 to −28% on every seed, equal clean | [jc-extensions.md](jc-extensions.md#min-plus-best-response-maps-t1) | `xf_minplus` |
| exact physics maps (T2) | did not work | −11% fast physics reversed by a replicate | [jc-extensions.md](jc-extensions.md#exact-physics-maps-t2) | `xf_physmap` |
| minimal-partition (soap-film) pours | did not work | Pours 1.01–1.05× human resistance; interleaved rails fail | [pour-models.md](pour-models.md) | `collapse_pour` |
| pour-damage maps (T4) | worked (physics objective; needs confirming) | Pour R 0.84× jc, routed physics 1.05 vs 1.18 | [pour-models.md](pour-models.md#pour-damage-maps-in-jc-t4) | `xf_pour` |
| transformations T3, T5–T12; untested catalog ideas | untested ideas | Mechanisms and test plans only | [untested-ideas.md](untested-ideas.md) | — |
| kae joint loop: KiCad-judged feedback windows, local re-place and rip-up, incremental re-route, lexicographic accept | worked on A+B; clock-bound on split C | A+B cp1 0.909 vs staged 0.879 vs human + Freerouting 0.455; module physics 0.78x human | [kae-joint-loop.md](kae-joint-loop.md) | `kae/src/kae/joint/`, `tools/research/joint/` |
| kae staged: kae place, then the Freerouting bridge with last mile | worked on A+B; partial on split C | A+B cp1 0.909, as the human placement with the same router; split C 30/78 clean vs 43/78 human | [kae-staged.md](kae-staged.md) | `kae/src/kae/joint/cli.py` (`--max-iters 0 --no-modules`) |

Two older micro-benchmarks from the same research, already on main, are listed in the placement area:
synthetic CP-SAT / annealing placement benchmarks (`tools/research/solver-bench`, see
[solver benchmarks](../../topics/solvers/benchmarks.md)) and decap distance statistics
(`tools/research/layout-data`).

**Merit list.** 22 pnr arms are in the 500-board comparison (`tools/kaeres/experiments/merit-restart.sh`;
experiments `merit-500r3` / `merit-500r3k`, running): route_only, seq, seq_phys, anneal, anneal_phys,
repair, negotiate, beam, combo, combo_full, seq_collapse, grad_phys, jc, jc_lv, jc_full, xf_h, pjc2,
pjc2_lv_nopol, hjc_press, qd, jc2_fix, jc2_fixmp_lv. The list is "merit or partial merit": some arms
(seq_collapse, qd, hjc_press, xf_h, pjc2_lv_nopol, combo_full, jc2) carry weaker verdicts on their pages.

## Open items

These are unfinished on the branch:
- the v7 jc baselines (88 and 94 of 99) and their physics scores;
- the 5-board engine v6.4 re-runs (`-r4cu`);
- `combo_full`;
- the remaining jc2 attempts and a base-vs-fix ablation;
- `grad_hpwl_phys` over 3 seeds;
- harmonic pressure and QD re-compared against a complete jc;
- a suite-level run of the fast router.

## Harness and engine lessons

Harness bugs found along the way:
- relative paths for `--command`;
- locked footprints staged off-board;
- a legality model stricter than KiCad;
- the sandbox hiding `/tmp` (kae import);
- concurrent `prepare` runs writing one workdir;
- tasks re-prepared, and the engine edited, under running jobs;
- `cpu_s` near zero for sandboxed methods.

Details: [v7-bugs.md](../../../tools/research/pnr/results/v7-bugs.md),
[BUGS.md](../../../tools/research/collapse_joint/BUGS.md),
[scorecard.md](../../ideas/original/scorecard.md) (engine and harness findings).

## Boards and licences

The ab33 boards come from public repositories listed in `bench/manifests/candidates.jsonl`. Licences of
the boards named on these pages:
- olimex dcdc-50-5-12: CERN-OHL-S-2.0
- badjeff paw3222, paw3395, pmw3610; siderakb pmw3360, pmw3610; jvedder bipolar supply: CERN-OHL-P-2.0
- 0rax esphome xiao, lambdakb lt6c, tzarc kobold, caffeinated aftonsparv: CERN-OHL-S-2.0
- electron271 tuxkeychain, kicad-demos ecc83 and video: CC-BY-SA-4.0
- tcsullivan noisecard: GPL-3.0-only
- jangtrinh desktop companion, d3a kitspace gas sensor, bentwire usb-c fusb302, m1geo pi5-pcie: MIT
- justbuchanan oasis (pcb, ledboard), rapidanalysis xerxes: Apache-2.0
- 0xjmux esp-prog adapter, bluerobotics ping dev kit: CERN-OHL-P-2.0
- berkeleylab obsidian: CERN-OHL-W-2.0
- c-biscuit crowbar: GPL-2.0-only

Only summary numbers are published, no board geometry or renders.

## Sources and related

- Experiment log: [joint-pnr-experiments.md](../../topics/placement/joint-pnr-experiments.md).
- Verdict per idea: [scorecard.md](../../ideas/original/scorecard.md).
- Catalog: [joint-pnr.md](../../ideas/original/joint-pnr.md), [layer-collapse.md](../../ideas/original/layer-collapse.md).
- Notes: [literature survey](../../../research_notes/joint-pnr/literature-survey.md),
  [transformations](../../../research_notes/transformations/transformations.md),
  [layer-collapse analogs](../../../research_notes/layer-collapse/analogs.md).
- Other areas: placement, routing and physics under `docs/research/`.
