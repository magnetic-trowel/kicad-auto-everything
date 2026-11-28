<!-- SPDX-FileCopyrightText: 2026 HaslamPCB contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# DC plan, cell windows and default DC terms after obd-solar (2026-11)

**Status:** scorer changes on branches, each its own commit with a test, re-scored (not re-run) against main;
not merged. Branches: `physics/dc-plan-cells` (DC plan, heat, from main), `physics/cell-window-memory` (window memory,
from main), `synth/dc-defaults` (synth width gate and default terms, from `obd-solar-e2e` with the DC-plan commits
ported), `physics/neutral-heat-rating` (a `neutral/1` proposal, from main).
Scope: the three evaluator gaps obd-solar met (FRICTION.md #52, #56, #57, #62, #65, #66 on branch `obd-solar-e2e`):
a DC plan with no load where only a converter is stated, per-cell window solves that ran out of memory, and no DC terms
unless a design writes them. Not here: the router's widths -> [power-net-track-width](../routing/power-net-track-width.md)
(branch `obd-solar-e2e`); the 1 % export prior's own A/B -> [export-current-one-percent](export-current-one-percent.md).
Keys: EXPORT_FROM_FEED, band, stated, CHARGE_SINKS, CHARGE_PATH, charge sink, feed_output, element_terminals, per_net,
planned_injections facts, _switch_parts, external switch FET heat, HASLAM_CELL_WINDOW_GB, window memory budget,
D-HEAT, dc_terms, D-laminate, LAMINATE_MOT_C, width_injections, obd-solar

## 1. DC plan (`physics/dc-plan-cells`)

| # | Commit | Change | Why |
|---|---|---|---|
| 1 | 255193be | unstated exports alone on a converter's rail take what it delivers; a charger with no load charges the external source one series part away (`CHARGE_SINKS`) | obd-solar: J301 export at 30 mA (0.127 mm on 3.5 A read 0 K); CN3767 -> Q203 -> VBAT -> J101 carried nothing |
| 2 | cf09e4c0 | `planned_injections` builds the brief from the facts (and reads a `haslam.intent/1` document) | it used `B.build(board)`: rails fed through a connector by facts had no feed; power copper and the width gate solved another plan than the one scored |
| 3 | 746fe400 | `planned_injections(per_net=True)`: each DC element's current on its pads (`element_terminals`, lumped nodal solve per piece) | a net fed through a fuse, inductor or sense resistor did not balance on its own; the width gate fell back to `i_max` |
| 4 | 4fa0b717 | a charge path runs through a FET or diode (`CHARGE_PATH`), any series part only for a charger IC | 213-board re-score: antmicro sdi-mipi's buck -> R40 -> +3V3 (brief: fed by J7) read as charging J7 at 1.64 A |
| 5 | 7db04632 | `heat.part_heat`: a cell's switch losses heat its external switch FETs (`_switch_parts`, by duty), not the controller | with its charge current modelled, obd-solar's CN3767 read 1.36 W, 225 C for its external PFET's loss |
| 6 | 6c906d70, f93eb860 | `EXPORT_FROM_FEED = "band"` (default): the export keeps its 1 % typical, its band's top is the feed's current | "stated" heated regulators by a guess: the cell I_A it took on qubik and robertpheller is "intent" in source, "class values" in provenance |

Rules in force (`haslam/src/haslam/excite/dc.py`):

1. A rail whose only loads are unstated connector exports, that feeds no regulator: the exports' band top is the feed's
   current split by rating (a cell's `cells.<id>.I_out_A`, else its ledger `I_A` through its topology; a charger IC's
   `parts.<ref>.I_A`; through a series link from a rail that feeds nothing else). Typical stays `EXPORT_SHARE`. The
   export question names the reason (priority high).
2. A converter rail with no load and no regulator fed from it, joined by exactly one FET or diode (any series part for
   a charger IC) to a rail an external connector feeds: a load on the rail at the series part, passed on into the
   connector at the feed's current (stated or ledger, typical as stated). Several candidates: none, with a note.
3. The superposition of charge and discharge through one battery is the battery's net current; the corners' all-low
   vertex and hypercube still take the charge at its low end.

### 1.1 Re-scored: 213-board intent set (DC plan and typical part power, no field solve)

Inputs `intent-213/compiled-51eaed9`; script `bin/plan_mode.py` (plancmp with `$DCMODE`); old = main 8a0f51e1.

| Arm | Identical to main | Changed | KCL failures | Error mismatches |
|---|---|---|---|---|
| rules off (`off,0`) | 213 | 0 | 0 | 0 |
| `stated` | 211 | qubik (PQ1 0.03 -> 0.55 A), robertpheller (CN7 0.05 -> 1.10 A) | 0 | 0 |
| `all` | 211 | the same two | 0 | 0 |
| `band` (default) | 211 | qubik (PQ1 top 0.3 -> 1.0 A), robertpheller (CN7 top 0.5 -> 2.0 A); typicals and part power unchanged | 0 | 0 |
| final code, `stated` (heat fix included) | 211 | the same two; typical part power U1 12.9 -> 221.5 mW, U401 32.6 -> 656.6 mW | 0 | 0 |

1. No corpus board triggers the charge rule after commit 4, and the heat fix changes no corpus board's part power.
2. `all` = `stated`: no board has an export-only rail on a converter whose current is only a prior.
3. Two jobs failed on a missing module (`haslam.board.dru_check`, `haslam.route`) in their queue snapshot; re-run
   directly, both identical to main.

### 1.2 Re-scored: 12-board set (14 inputs, full evaluator, `--no-cells`)

Inputs and intents of [evaluator-audit-2611](evaluator-audit-2611.md) (`runs12`). Tiers hard / limit / cost (mW_eq).

| Board | main | `stated` | `band` |
|---|---|---|---|
| qubik bmps | 0 / 0 / 55.5 | 0 / 0 / 349.3 (U1 17 -> 304 mW) | 0 / 0 / 66.4 (track 0.7 -> 1.4 K, PQ1 drop 3.5 -> 11.7 mV) |
| robertpheller pnet-router | 0 / 6570.5 / 484.2 | 0.20 / 6728.9 / 1604.1 (U401 Tj 47.5 -> 191.9 C) | 0 / 6607.0 / 684.4 (track 0.9 -> 20.7 K, CN7 drop 39 -> 158 mV) |
| the other 12 inputs | | identical | identical |

### 1.3 obd-solar routed-s1 (cells at 0.125 mm, PVOUT roles patch applied for the run only)

| Run | Tiers | Hottest track | VBUS drop | Cu loss | Tj |
|---|---|---|---|---|---|
| main, J301 fact (the hand-fixed design) | 2.07 / 2500 / 2086 | 199.6 K VBAT | 266 mV | 3.01 W | U301 254 C |
| main, no J301 fact | 1.04 / 1486 / 52 | 3.5 K | 39 mV | 0.08 W | U201 88 C |
| `stated`, no fact | 2.04 / 2501 / 1675 | 199.6 K | 267 mV | 2.49 W | Q202 377, U301 250 C |
| `band` (default), no fact | 1.04 / 2485 / 1350 | 199.6 K | 252 mV | 2.28 W | Q202 361, U301 89 C |

1. Without any hand fact the default flags the copper as the hand-fixed design does; U301's temperature needs the
   load stated (the question asks for it).
2. Q202 (SOT-23) carries the charger's loss at its stated eta's low end, 0.85 at 0.75 A (about 1.8 W): the design's eta
   range, not the evaluator, sets that; its `temp.junction` term covers `U*` only.
3. Width gate (`synth/dc-defaults`, `width_check.py` reading the intent beside the board, per-net plan): every power
   net judged by branch currents with no `width_injections.json`; the same 7 nets fail as with the hand file
   (BB_SW1 6.8, BB_SW2 25.8, CHG_OUT 41.7, OBD_RAW 8.6, VBUS 20.9 mm; VBAT 71.9 against 69.7, its charge path now in).
   The hand file is deleted there.

## 2. Cell-window memory (`physics/cell-window-memory`)

Done by a sub-agent; numbers and method in `docs/research/physics/cell-window-memory.md` on that branch.

1. A memory estimate before factoring, `420 B x (1 + layers/2) x n log2 n` (upper envelope of 30 measured windows,
   1.02-2.3x actual), against a fixed budget of 6 GB per window (`HASLAM_CELL_WINDOW_GB`); over it the pitch doubles,
   at the board's pitch the board values stand; recorded in the row (`window.coarsened`, `window.why`).
2. `MemoryError`, and SuperLU's out-of-memory `SystemError`, fall back the same way (a backstop: the heap stays high).
3. Freed after use: each cell's kernel tables, the DC network and operator after the heat band.
4. obd-solar at the default pitch: 15.9 GB, 95 min -> 6.1 GB, 44 min (its three cells refuse 0.0625 and run at 0.125:
   observations identical to the old `--cell-pitch 0.125` run). 0.125 vs 0.0625 mm on 11 cells: L_loop -5.6 .. +3.8 %,
   R_loop -9.1 .. +8.2 %. 8 corpus boards: observations identical before and after.
5. Not adopted: a subprocess per window (fork after OpenMP threads), a free-memory budget (a board's pitch would
   depend on the host's load).

## 3. Default DC terms

| Where | What | Re-scored |
|---|---|---|
| haslamsynth (`synth/dc-defaults`, c850b56d) | `D-HEAT`: limit, `heat.track`, max = `BoardSpec.trace_rise_c` K, 5 mW_eq/K, written when a net has `i_max` and the design states no `heat.track` term; `drop.rail` only on request (`dc_terms(drop_share=...)`) | obd-solar stored evaluation: limit 585 -> 1533 |
| haslam `neutral/1` (`physics/neutral-heat-rating`, proposal) | `D-laminate`: hard, `heat.track` <= 130 C (FR-4 MOT) less the hottest ambient (`T_amb_C`, else 50 C) | 14 stored 12-board evaluations: every tier unchanged (hottest human track 16.4 K); obd-solar without T-HEAT: hard 0.48 -> 2.81 |

1. A `drop.rail` default has no source in a design (a rail's tolerance is not stated): kept opt-in.
2. The critical router reads board-wide `heat.track` limits (`haslam.intent.uses`): designs with `i_max` route under
   their own rise with D-HEAT. Not measured (a layout experiment).
3. `heat.track` is one observation (the board's hottest track): a per-net bound only binds when that net is hottest.
4. On the 14 stored evaluations a 10 K bound would fire on 1 (shazmeenshz, GND 0.2 mm, 16.4 K) and 2 % drop on 2.
5. `neutral/1` priced only copper loss by the user's decision ("assumed bounds are no prices"); D-laminate is a material
   rating, priced as part ratings are. It is a proposal for that decision.

## Open questions

1. Charge sinks take the charger's typical as stated, not the band rule: the corpus has no case; a prior-only charger
   current would heat by a guess.
2. `+3V3` on obd-solar: U402's input is behind R403 from VBAT, so the LDO is read as the board's input (50 mA missing
   from VBAT). An input net one series part from the facts' `from` rail is not followed.
3. `layout.sh`/`pipeline.py` on `obd-solar-e2e` still pass `--cell-pitch 0.125`; with the window budget it can go.

## Sources

Runs under `/var/tmp/$USER/dcplan/`: `p213/{old,stated,all,off,final,band}`, `runs12/<board>/{old,stated,all,band}`,
`obd/ev/*`, `wc*/` (width gate), `neutral/`, `terms/`; scripts in `bin/`. haslamq owners `dcplan-*`, `cellmem-*`.
