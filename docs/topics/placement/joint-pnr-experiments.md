# Joint place-and-route experiments (pnr lab)

**TL;DR**
- We built our own engine for placing and routing together, without Freerouting ([tools/research/pnr/](../../../tools/research/pnr/)). It is a 0.1 mm halo grid with a numba negotiated-congestion router, legal-position maps computed by FFT, and KiCad read and write. On the **human** placements of the 33 qualified A/B boards the router alone gets **clean pass 0.85 (A) and 0.50 (B) in 2–8 s per board**. The repo's tuned Freerouting baseline gets 0.62 / 0.35 with up to 600 s [M].
- **Physics belongs in the placement objective.** Every placement driven only by HPWL (half-perimeter wirelength) is electrically worse than the human one: 4.05× the human place-terms total on the 10 boards that have physics structures. The causes are decap loops, coupling and cable common-mode. Adding kae.physics place terms to the objective (`seq_phys`) cuts that to 1.52× at no cost in completion. Beam search with physics reaches **0.98×**, and `combo` reaches capped utilization 0.97× [M].
- **Best pipeline: `combo` = beam search over place-one-route-it → blocker-directed window repair → annealing on routed cost + physics.** On all 33 boards it gets legal 0.848, clean 0.636 (equal to the human placement through the same router), completion 0.897, and 13% less copper than place-then-route. On the physics boards it is at human parity. Beam alone vs greedy on the same score at equal CPU: completion 0.891 vs 0.868, 8% less wire. Annealing with re-routing in every move also helps, and so does window repair aimed at the blocking parts. Soft routing gradients, Physarum flow, exact CP-SAT windows and an LLM move proposer did not beat simple controls [M].
- **Clean pass is capped by DRC types that no method's objective sees.** These are silkscreen overlap (an error on some boards), solder-mask bridges and thermal-spoke starvation. Each was traced to placement crowding, not routing [M].
- Along the way we found three harness bugs: `--command` adapters got relative paths; locked footprints were staged off-board, which made 7 of 33 place tasks unsolvable; and joint methods had no way to be scored. All three were fixed in separate commits.

## Setup

| Item | Value |
|---|---|
| Boards | 33 qualified A/B boards (KiCad 10.0.7), place tasks: unlocked parts staged off-board, no copper |
| Score | `kaebench run --kinds place --probe self`: placement legality, then the method's own copper scored by `kicad-cli` DRC with the board's rules (clean, completion against the place input) |
| Physics | [tools/research/pnr_phys/physics_score.py](../../../tools/research/pnr_phys/physics_score.py): kae.physics place terms (decap and hot-loop nH, coupling mV, crystal ppm, thermal K, cable common-mode, ESD) and routed recheck, each as a ratio to the human board (geometric mean over the 10 boards with structures) |
| Budget | 120 CPU-seconds per board (process time, so the results do not depend on machine load), one seed, k = 1 |
| Engine | v5: courtyards per side, pad keep-outs per copper layer, pad-local clearances, hole keep-outs, thermal-spoke room ([world.py](../../../tools/research/pnr/world.py)) |

The model's legality was calibrated against the human boards. Under the first model, 22 of 33 human placements counted as "illegal": through-hole parts blocked both sides, courtyards were not allowed to overhang the board edge, and courtyards drawn on the other side went unread. Under v5 that is down to 12, each by about 0.1 mm of raster rounding.

## Results (all 33 boards, engine v5)

Length is summed over the 22 boards that every run in the table completed. Runs come from `kae-work/results/`.

| Method | Idea | Legal | Clean | Completion | Length (mm) | Vias |
|---|---|---|---|---|---|---|
| `seq`: HPWL place, then route (control) | — | 0.788 | 0.545 | 0.863 | 3386 | 60 |
| `seq_phys`: + physics descent | 43 | 0.788 | 0.545 | 0.863 | 3422 | 64 |
| `grow`: place one, route it | 6 | 0.788 | 0.545 | 0.861 | — | — |
| `anneal_phys`: annealing on routed cost + physics | 11, 43 | 0.818 | 0.576 | 0.876 | 3189 | 38 |
| `beam`: beam over grow, + physics ([pnr_mcts](../../../tools/research/pnr_mcts/RESULTS.md)) | 7, 43 | 0.818 | 0.545 | 0.891 | 3095 | 39 |
| **`combo`: beam → blocker repair → physics annealing** ([methods_combo.py](../../../tools/research/pnr/methods_combo.py)) | 7, 12, 11, 43 | **0.848** | **0.636** | **0.897** | **2943** | **25** |
| `grad`: soft-min routing gradients ([pnr_grad](../../../tools/research/pnr_grad/RESULTS.md)) | 22 | 0.848 | 0.545 | 0.869 | — | — |
| human placement, same router (route task) | — | — | 0.636 | — | — | — |

On all 33 boards, `combo` matches the clean pass of the **human placement routed by the same router** (0.636). It uses 13% less copper and 58% fewer vias than `seq`.

Physics on the 10 boards with structures (ratio to human; lower is better; [physics_score.py](../../../tools/research/pnr_phys/physics_score.py)):

| Method | Legal / clean (of 10) | Completion | Place terms | Capped u | Routed physics |
|---|---|---|---|---|---|
| human placement, same router | 10 / 4 | 0.96 | 1.00 | 1.00 | 1.09 |
| `seq` | 7 / 3 | 0.86 | 4.05 | 1.45 | 1.39 |
| `seq_phys` | 7 / 3 | 0.86 | 1.52 | 1.20 | 1.26 |
| `anneal_phys` | 8 / 4 | 0.89 | 1.68 | 1.29 | 1.33 |
| `beam` (phys_w = 2) | 8 / 4 | 0.94 | 0.98 | 1.01 | 1.14 |
| **`combo`** | **9 / 5** | **0.96** | 1.03 | **0.97** | **1.13** |
| `grad_phys` + physics descent | — | 0.84 | 1.37 | 1.08 | **1.00** |
| Physarum motion + physics, from `seq_phys` | 7 / 3 | 0.86 | 1.53 | — | 1.30 |

Single boards:
- On the olimex buck converter, the HPWL placement scores 51–1400 depending on the version, the human scores 7.39, and `anneal_phys` scores 5.83 and is DRC clean.
- The LLM proposer got that board from 1408 to 696.

## What each approach showed

- **Annealing with real re-routing** ([methods.py](../../../tools/research/pnr/methods.py) `anneal`; Nag–Rutenbar 1998). With physics (`anneal_phys`, v5) it gives clean 0.576 vs 0.545, completion 0.876 vs 0.863, and 6% less copper than `seq`. It works best as the finishing stage of `combo`.
- **Beam search over growth.** Keeping alternatives across steps helps; adding candidates per step does not (24 candidates per step scored the same as 6). MCTS gets only about 8–10 rollouts per part at 120 s and trails beam. Switching nodes by diffing poses and routes is 2–3 orders of magnitude cheaper than replaying them ([pnr_mcts](../../../tools/research/pnr_mcts/RESULTS.md)).
- **Differentiable routing.** We tested whether soft-min shortest-path gradients point somewhere better than HPWL. Moving parts along the soft-route gradient improved the routed cost 33% of the time; HPWL did 36%, pin tension alone 43%, random 19%. **No merit** as a placement driver. A global gradient start followed by discrete physics descent gave the best routed physics (1.00×) ([pnr_grad](../../../tools/research/pnr_grad/RESULTS.md)).
- **Physarum (slime-mould) networks.** The tubes thin to believable trees. As a router prior the effect is neutral or worse, and as forces on parts with an accept test it barely moves anything. **No merit** as built ([pnr_slime](../../../tools/research/pnr_slime/RESULTS.md)).
- **LLM as move proposer.** The agent played the LLM, seeing only renders and summaries. It matched blind annealing on routing on 4 hard boards, with completion 0.78 vs 0.62 for `seq`. Most of the gain came from legality fixes that a rule would also make. On physics it was about 110× behind `anneal_phys`. Production use: 1–3 diagnostic calls, then hand over to search ([pnr_llm](../../../tools/research/pnr_llm/RESULTS.md)).
- **A-priori spacing (`seq_margin`)** is the control for "is it just room?". On v3 it raised clean (0.49 vs 0.39) at +29% copper and failed to place parts on dense boards. Routing in the loop gets completion without that cost.
- **Unified negotiation (`negotiate`).** Parts and wires bid in one price field. It reaches a legal, fully routed state within 3 rounds. When wire prices only grow, parts flee wires and the layout inflates, so wire prices must decay when there are no conflicts.
- **Exact CP-SAT windows** (SP&R-style LNS; window up to 9 mm, 2–3 parts, routing as Numberlink paths, [pnr_cpsat](../../../tools/research/pnr_cpsat/RESULTS.md)). **No merit.** None of about 750 window solves was proven optimal. With poses fixed, about 40% of windows left a connection unrouted that the engine routes. On identical windows CP-SAT beat the heuristic `repair` 0 times in 112. The same loop without CP-SAT scores the same. The heuristic repair is better (dev6: legal 0.833, completion 0.921 vs 0.667 / 0.904 for `seq`). Worth trying next: exact joint choice among a few candidate poses, with pair costs measured by the real router.

## What limits clean pass

The error counts across the `seq` and `beam` runs, mostly from placement:

| Error | Cause | Status |
|---|---|---|
| `silk_overlap` (an error on some boards) | silkscreen of neighbours overlaps; the engine has no silkscreen plane | open: add silkscreen keep-outs for boards where it is an error |
| `solder_mask_bridge` | mask expansion 0.2 mm on some boards: two pad apertures merge, or a track sits inside an aperture | fixed in the dev engine (pad gap ≥ 2·expansion + web) |
| `starved_thermal` | neighbours' pads crowd a zone pad's relief spokes; deleting every other-net track does not help | thermal-spoke corridors in the placement keep-out: 3 → 1 on olimex |
| `shorting_items` | one board has board-level copper arcs | wires avoid them; parts do not yet |
| unrouted on dense sensor boards | 0.5 mm-pitch pads that no track can enter at the board's clearance | open: neck-down near pads |

## Recommendations for our system

- Make physics a first-class term in every placement objective (`Terms.delta` costs about 50 µs per move). Score routed physics on the final copper. HPWL alone produces electrically wrong boards that route well.
- Use `combo` as the baseline to beat: beam search over interleaved place-and-route with the physics term ([mcts.py](../../../tools/research/pnr_mcts/mcts.py)), then blocker-directed repair, then annealing on routed cost plus physics ([methods_combo.py](../../../tools/research/pnr/methods_combo.py)).
- Put every DRC error type that blocks clean into the search score: silkscreen, mask apertures, spoke room. Clean depends on these, not on wirelength.
- Use LLMs for diagnosis and structure (which parts are blocked, which connector goes to which edge), not for move-by-move proposals.

## Conflicts and open questions

- All results are one seed. The physics evidence rests on 10 boards whose priors are unmeasured (kae E5), so read them as relative.
- The engine changed during the work (v3 → v5); compare only runs of the same version.
- Joint methods compact boards more than humans do. Place-task scoring does not reward connectors at edges or mechanical intent.

## Sources

- Code: [tools/research/pnr/](../../../tools/research/pnr/) and `pnr_<tag>/` for each experiment; agent brief [AGENT_BRIEF.md](../../../tools/research/pnr/AGENT_BRIEF.md).
- Ideas: [joint-pnr ideas](../../ideas/original/joint-pnr.md); survey: [literature-survey](../../../research_notes/joint-pnr/literature-survey.md).
- Harness: [harness.md](../verification/harness.md).

See also: [pcb-placers-2022-2026](pcb-placers-2022-2026.md), [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md)
