# Joint place-and-route experiments (pnr lab)

**TL;DR**
- We built our own engine for placing and routing together, without Freerouting ([tools/research/pnr/](../../../tools/research/pnr/)). It is a 0.1 mm halo grid with a numba negotiated-congestion router, legal-position maps computed by FFT, and KiCad read and write. On the **human** placements of the 33 qualified A/B boards the router alone gets **clean pass 0.85 (A) and 0.50 (B) in 2–8 s per board**. The repo's tuned Freerouting baseline gets 0.62 / 0.35 with up to 600 s [M].
- **Physics belongs in the placement objective.** Every placement driven only by HPWL (half-perimeter wirelength) is electrically worse than the human one: 4.05× the human place-terms total on the 10 boards that have physics structures. The causes are decap loops, coupling and cable common-mode. Adding kae.physics place terms to the objective (`seq_phys`) cuts that to 1.52× at no cost in completion. Beam search with physics reaches **0.98×**, and `combo` reaches capped utilization 0.97× [M].
- **Best pipeline: `combo` = beam search over place-one-route-it → blocker-directed window repair → annealing on routed cost + physics.** Over 3 seeds on all 33 boards it gets legal 0.86, completion 0.90 and clean 0.60, against 0.79 / 0.86 / 0.56 for place-then-route; the clean gain is within seed noise. It also uses 13% less copper. On the physics boards it is at human parity. Beam alone vs greedy on the same score at equal CPU: completion 0.891 vs 0.868, 8% less wire. Annealing with re-routing in every move also helps, and so does window repair aimed at the blocking parts. Soft routing gradients, Physarum flow, exact CP-SAT windows and an LLM move proposer did not beat simple controls [M].
- **Clean pass is capped by DRC types that no method's objective sees.** These are silkscreen overlap (an error on some boards), solder-mask bridges and thermal-spoke starvation. Each was traced to placement crowding, not routing [M].
- Along the way we found three harness bugs: `--command` adapters got relative paths; locked footprints were staged off-board, which made 7 of 33 place tasks unsolvable; and joint methods had no way to be scored. All three were fixed in separate commits.

## Status: re-validation under harness score v7 (in progress)

The numbers below are from engine v5 on the v3 harness. They are being re-measured with joint tasks (score v7) and 3 seeds, at 120 CPU-s per board. Each engine version fixes a DRC error found in those runs. The bug log is [v7-bugs.md](../../../tools/research/pnr/results/v7-bugs.md).

| Engine | Fix |
|---|---|
| v6 | Solder-mask apertures between pads; holes under courtyards on both sides |
| v6.1–6.2 | Footprint keep-outs; footprint copper drawings become no-net copper |
| v6.3 (c78c537) | Pad terminals from KiCad's inner outline (custom ring pads); edge test covers whole pads |
| v6.4 (merged, 9db768f) | Board copper drawings and copper text are pad obstacles; `.kicad_dru` edge clearance. Merged with the Tibia fix 4c4330a. Changes 5 of 33 boards |

**Comparison sets.** Counted runs use v6.3 on [v7-ab33](../../../tools/research/pnr/suites/v7-ab33.txt). The headline compares the 28 boards that v6.4 leaves unchanged. The 5 changed boards are re-run on v6.4.

**Baselines (partial, stopped 2026-10-25):** [v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md). On the 28 boards, legal / clean / completion: seq 0.893 / 0.607 / 0.904, combo 0.917 / 0.667 / 0.935; combo uses 13% less copper and 54% fewer vias on every seed. jc and jc_lv reached 88 and 94 of 99 attempts; on the 24 boards with all seeds: legal 0.986, clean 0.694 (jc) and 0.722 (jc_lv). Clean gains over seq are within seed noise. Routed physics vs human (10 boards): seq 1.22, seq_phys 1.11, combo 1.27; the human placement through the same router scores 1.11. Engine v6.4 is merged (9 tests pass), but the five changed boards have not been re-run. Drivers are in [scripts/](../../../tools/research/pnr/scripts/).

The final transformation experiments are in [scorecard](../../ideas/original/scorecard.md) rows T1, T2 and T4. That was round 3, run on another host with 4c4330a. The pour maps coupled across layers (`pjc2`) improved routed physics to 1.05× human, from jc's 1.18×, a gain still to confirm.

## Objectives and scores (how every method is tested)

- **Objectives**, run as separate variants of each method:
  - **Length + vias:** routed length + 2 mm per via + an unrouted penalty; phys_w = 0. Runs:
    `seq`, `anneal`, `grow`, `combo_lv`.
  - **Fast physics in the loop:** kae place terms (`Terms.delta`, ~50 µs per move), phys_w = 2.
    Runs: `seq_phys`, `anneal_phys`, `grow_phys`, `combo`, beam p2.
  - **Full physics at gates:** kae's routed recheck on the written board
    (`physics.RoutedPhys`, ~1.5 s), used to accept stages and pick checkpoints. Run:
    `combo_full`.
- **Scores**, all three on every run (`kae-work/score_all.sh`):
  - DRC: legal, clean, completion, length, vias;
  - fast physics vs human;
  - full routed physics vs human.
- **Fast physics predicts full physics only moderately:** mean within-board Spearman 0.55
  (0.13 to 0.95 over 9 physics boards). A method tuned on fast physics needs the routed
  check.

### Objective comparison (v5, all 33 boards, one seed)

Physics is the ratio to the human board on the 10 boards with physics structures. Length is summed over the 20 boards every run completed.

| Pipeline | Objective | Legal | Clean | Completion | Length (mm) | Vias | Fast physics (capped u) | Routed physics |
|---|---|---|---|---|---|---|---|---|
| seq | length + vias | 0.788 | 0.545 | 0.863 | 3117 | 40 | 1.45 | 1.39 |
| seq_phys | fast physics | 0.788 | 0.545 | 0.863 | 3152 | 44 | 1.20 | 1.26 |
| anneal | length + vias | 0.848 | 0.576 | 0.874 | 2852 | 22 | 1.57 | 1.54 |
| anneal_phys | fast physics | 0.818 | 0.576 | 0.876 | 2952 | 24 | 1.29 | 1.33 |
| combo_lv | length + vias | 0.818 | 0.545 | 0.900 | 2695 | 16 | 1.34 | 1.26 |
| combo | fast physics | 0.848 | 0.636 | 0.897 | 2687 | 16 | **0.97** | **1.13** |
| combo_full | fast physics + full physics at gates | running | | | | | | |
| **jc**: joint collapse by continuation + polish ([collapse_joint](../../../tools/research/collapse_joint/RESULTS.md)) | fast physics | **0.879** | **0.667** | 0.897 | +1% vs combo (22 boards) | +70% vs combo | **0.82** (φ-total) | 1.05 |
| jc_lv | length + vias | 0.879 | 0.667 | 0.897 | — | — | 2.05 (φ-total) | 1.29 |
| jc_frozen: parts frozen after the lift | fast physics | 0.879 | 0.485 | 0.892 | 1.6× jc | 2.4× jc | 1.08 (φ-total) | 1.04 |
| jc_full (10 physics boards only) | + full physics on restarts | 8/10 | 4/10 | 0.943 | — | — | 0.84 (φ-total) | **0.80** |
| human placement, same router | — | — | 0.636 | — | — | — | 1.00 | 1.09 |

**Joint collapse vs frozen parts** (same start, schedule, restarts and router): moving parts together with nets gives 0.52× the copper on 24 of 24 boards, 59% fewer vias and clean 0.606 vs 0.485. This is direct evidence that placement and routing cannot be separated. jc rows use the φ-total for fast physics (combo's φ-total is 1.03). jc leaves more open hops (1.3 vs 0.5 for combo), and that flatters its routed physics: on boards with no open hop it is 1.27 vs 1.22, roughly a tie. One seed so far; more seeds are running.

In every pipeline, switching from length + vias to fast physics improves both fast and routed physics. Completion, length and vias stay the same within noise. The physics objective costs essentially nothing in routability, so it should be on by default.

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
| `grow_phys`: grow + physics descent | 6, 43 | 0.758 | 0.515 | 0.850 | — | — |
| `anneal`: annealing on routed cost | 11 | 0.848 | 0.576 | 0.874 | — | — |
| `anneal_phys`: annealing on routed cost + physics | 11, 43 | 0.818 | 0.576 | 0.876 | 3189 | 38 |
| `repair`: blocker-directed window repair | 12, 13 | 0.818 | 0.545 | 0.873 | — | — |
| `negotiate`: parts and wires in one price field | 1 | 0.818 | 0.545 | 0.897 | +11% vs `seq` | — |
| `beam`: beam over grow, + physics ([pnr_mcts](../../../tools/research/pnr_mcts/RESULTS.md)) | 7, 43 | 0.818 | 0.545 | 0.891 | 3095 | 39 |
| **`combo`: beam → blocker repair → physics annealing** ([methods_combo.py](../../../tools/research/pnr/methods_combo.py)) | 7, 12, 11, 43 | **0.848** | **0.636** | **0.897** | **2943** | **25** |
| `grad`: soft-min routing gradients ([pnr_grad](../../../tools/research/pnr_grad/RESULTS.md)) | 22 | 0.848 | 0.545 | 0.869 | — | — |
| human placement, same router (route task) | — | — | 0.636 | — | — | — |

Seed check (3 seeds, all 33 boards):

| | `seq` per seed | `seq` mean | `combo` per seed | `combo` mean |
|---|---|---|---|---|
| Legal | 0.788 / 0.788 / 0.788 | 0.788 | 0.848 / 0.848 / 0.879 | **0.859** |
| Clean | 0.545 / 0.545 / 0.576 | 0.556 | 0.636 / 0.606 / 0.545 | 0.596 |
| Completion | 0.863 / 0.850 / 0.854 | 0.856 | 0.897 / 0.893 / 0.899 | **0.896** |

The gains in legality (+0.07) and completion (+0.04) hold on every seed. The clean gain (+0.04 on average) is within seed noise: seed 0 matched the human placement through the same router (0.636), but that seed was lucky. `combo` uses 13% less copper and about 60% fewer vias than `seq` (seed 0).

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
- **Unified negotiation (`negotiate`).** Parts and wires bid in one price field, starting from overlapping parts. It reaches the highest completion of the single methods (0.897), but with 11% more copper: parts spread out to give wires room. When wire prices only grow, parts flee wires and the layout inflates, so wire prices must decay when there are no conflicts.
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

- All results are one seed except the `seq`/`combo` check above. The physics evidence rests on 10 boards whose priors are unmeasured (kae E5), so read them as relative. The `*_phys` methods optimize the same terms that score them, so routed physics is the less circular check.
- Two boards (azonenberg, suzyqboard) draw their outline inside an unlocked footprint, which the place task stages off-board. Every method fails them.
- The engine changed during the work (v3 → v5); compare only runs of the same version.
- Joint methods compact boards more than humans do. Place-task scoring does not reward connectors at edges or mechanical intent.

## Sources

- Code: [tools/research/pnr/](../../../tools/research/pnr/) and `pnr_<tag>/` for each experiment; agent brief [AGENT_BRIEF.md](../../../tools/research/pnr/AGENT_BRIEF.md).
- Ideas: [joint-pnr ideas](../../ideas/original/joint-pnr.md); survey: [literature-survey](../../../research_notes/joint-pnr/literature-survey.md).
- Harness: [harness.md](../verification/harness.md).

See also: [pcb-placers-2022-2026](pcb-placers-2022-2026.md), [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md)
