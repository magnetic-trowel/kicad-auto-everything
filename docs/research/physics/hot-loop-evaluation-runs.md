<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Hot-loop evaluation runs: window cost, validation, AC copper loss (2026-11)

**Status:** measurements behind [hot-loop-evaluation](../../topics/physics/hot-loop-evaluation.md); model against model, no hardware.
**First published:** 2026-11-14 to 2026-11-17 on branches `hotloop-eval`, `hotloop-sw`; moved here from the topic doc on `converter-currents`.
Keys: turn-off current I_pk effect, buck input current eta effect, hot-loop window run time, window cap reverted, scope losses equivalence, hot-loop validation human layouts, loss.loop_ac harmonic sum effect, loss.copper_ac on converter boards, wideband comparison

## 1. Window run time and the reverted window cap

**Run time** (8 threads; 69 evaluations of 23 boards, human and two routed arms): the windows take a median 104 s per board (0–72 min), 49 % of the evaluation's time (up to 92 %); a 1-cell 31 × 31 mm 2-layer board (bq25306, the window is the whole board because module J1 takes 16 % of the loop's current) spends 400 s in the window against 25 s in the board solve. Profile of that run (py-spy): 90 % in the window solves, of it COCG preconditioner 21 %, sparse products 15 %, FFT operator 25 %, factorization 12 %. Windows over 1.2 M cells × layers coarsen; one that would coarsen to the board's own pitch keeps the board's values (`window.refined = false`, no harmonics: 12-layer arvsom). `--cell-pitch 0.125` cuts the window time about 4× at up to 11 % L error; `--no-cells` skips it.

**Window cap tried and reverted.** Windows on the loop's own pads (brief `loop` plus margin, 25 % leak allowed) instead of every part carrying 5 % of the cell's current moved L_loop by up to 16 % (circuitmonkey human −16 %, noggin C −12 %; median 2.4 %) on 16 cells for 18 % less window time: the truncation correction is first order, so parts that carry a share of the current stay inside.

Equivalence and time [C, 8 threads, full against `--scope losses`]: every kept observation and every cell row bit-identical (max relative difference 0) on five boards.

| Board | Kept observations | Full | losses |
|---|---|---|---|
| librewave-ecp5 human (8 layers, 25 sources, 3 cells) | 12 | 6,192 s | 1,140 s (cells 786 s) |
| bq25306 human | 7 | 217 s | 184 s |
| qubik-bmps C | 4 | 74 s | 70 s |
| max98357 A | 9 | 55 s | 66 s |
| powerboost human | 24 | 45 s | 49 s |

On small boards the windows dominate and both modes take the same time; the saving is on boards with many sources and observers, whose 25–100 MHz bands are skipped.

## 2. Validation on human layouts (2026-11-14)

Human layouts of the 24 converter boards of the hot-loop diagnosis, with arms A (rf-legacy) and C (rf-finish) of route-finish-ab; intents compiled-9867d0b; evaluator at this branch [C, run 2026-11-14; boards still running are left out].

| Measure | Value |
|---|---|
| Cells with a value or an explicit open | all; human: 19 valued, 13 open |
| Human opens | openhornet IC2: its VIN pin has no copper in the human file (real); kestrel-esc's 12 half-bridge cells open in every arm, their injection lands on U1's merged 10V/3V3/BATN pins: a cell-recognition artifact upstream of the evaluator, counted, never compared |
| Window vs board, pairwise order of two layouts of a cell (L and R, ties < 3 % skipped) | 81 agree, 1 disagrees (it8951 R, human vs C: 14.4 vs 14.9 mΩ on the board, 14.5 vs 13.8 in the window) |
| Window / board, all valued cells | L 0.64–1.40 (median 0.93), R 0.85–1.64 (median 0.99) |
| Human L_loop, integrated converters (buck, boost, class-D bridges) | 0.24–2.35 nH, median 1.2: TI SNVA803's < 0.5 nH (vertical loop) to > 1 nH (lateral), EPC's 0.4–2.9 nH range [P]; outliers are 2-layer layouts with long loops (it8951 boost 6.1 nH, esp32 flight controller 18.8 nH, moto:bit bridge 7.4 nH) |
| Human R_loop at f_sw | 1.9–102 mΩ, median 4.8 mΩ |

Paired against human (`hotloop.paired`, open cells ranked worst):

| | cells valued in both, board solve | same cells, window | all cells, window, opens counted |
|---|---|---|---|
| A / human, L_loop | 1.25 (16) | 1.30 | 1.34 (20 compared; A open 15, human 13, both 12) |
| A / human, R_loop | 1.76 | 1.56 | 1.71 |
| C / human, L_loop | 1.10 (12) | 1.16 | 1.38 (C open 18) |
| C / human, R_loop | 1.31 | 1.41 | 1.96 |

Counting open cells moves C from 1.10× to 1.38× human: the arm that left more hot loops open had looked better.

**Effect of the harmonic sum on `loss.loop_ac`** (typical corner, 76 valued cells of 23 boards, against the old fundamental formula on the board solve's R): median ×1.06, ×0.54 to ×2.71 [C]. Up: gecko5 U13/U14 ×2.0–2.7, noggin ×1.3–1.8, qubik ×1.4–1.5, bq25306 ×1.3–1.6. Down: arvsom and audio-latency ×0.7–0.9, where the layout's R share falls with frequency as the current moves to the nearest capacitor.

## 3. AC copper loss on the converter boards

**On the converter boards** (human layouts, `--scope losses`; 11 of 24 boards finished when written) [C]:
- `loss.copper_ac / loss.copper` (typical corner, boards with both): median 0.00056, 0.00022–0.0019 (3 boards: powerboost, govish, it8951). Most of these boards have no DC flow modelled (`DC: no rail with a source and a load`), so the ratio rests on few boards.
- `loss.copper_ac / loss.loop_ac` per cell: median 0.019, 0.003–2.25 (7 cells); above 1 only on chip-lcd's boost, whose loop losses are 0.1–0.2 µW.
- Class-D and filterless bridges (max98357, circuitmonkey, noggin) have no inductor in their structure: no ripple term, noted.
- Physics agrees: ripple RMS is ΔI/√12, ~10 % of a CCM load current, through mΩ of output copper, against the full pulsed current RMS I·√(D(1−D)) in the hot loop.

**Against `kae.excite.wideband`** (its `ac_loss.copper_W`: every AC source's harmonics through the reduced model at 0.25 mm, skin on; no ripple source either):
| Board | wideband | `loss.loop_ac` + `loss.copper_ac` | Why they differ |
|---|---|---|---|
| bq25306 human | 0.235 mW | 0.230 + 0.018 = 0.248 mW | the cell's term agrees within 2 %; wideband adds the cores' currents, has no ripple |
| qubik-bmps human | 0.210 mW | 0.141 + 0.003 = 0.144 mW | wideband builds its circuit without the operating facts' pin facts (a different brief), solves every harmonic to 172 MHz where `loss.loop_ac` extrapolates √f above 5 f_sw, and stays at 0.25 mm (the window reads R 8 % lower here) |
| powerboost human | — | 0.086 + 0.011 mW | wideband fails with no sources (no pin facts: no cell found) |

## 4. Converter-current changes on human layouts (2026-11-17)

Branch `converter-currents`, `--scope losses`, typical corner (loss sums, overshoot and drop maxima), status tiers summed [C]. A = base 37c5307 with `compiled-9867d0b`; B = 51eaed9 with `compiled-51eaed9` (boost input current, η in the boost duty, buck input current D·I_out/η); C = 248e030 (loss.loop and the overshoot edge at the turn-off current I_pk = I + ΔI/2). B/A on 14 of the 22 buck-only converter boards (the 8 with evaluations over ~1 h not re-run: arvsom, sdi-mipi, kocer, sinara, pumpbot, polarfire, J2032, USB armory); C/B on those and three boost boards ("0→x": no A run). "-": no such observation.

| board | B/A loss.copper | B/A drop.rail | B/A loss.part | B/A total | C/B loss.loop | C/B overshoot | C/B total |
|---|---|---|---|---|---|---|---|
| adafruit-adafruit-powerboost-500-c | 0→0.0101 | 0→0.00549 | 0→0.0609 | 0→166 | 1.175 | 1.082 | 1.001 |
| aifryz-sensor-hub-sensor-hub | 1.000 | 1.000 | 1.000 | 1.000 | 1.784 | 1.331 | 1.002 |
| antmicro-audio-latency-tester-boar | - | - | - | 1.000 | 1.166 | 1.066 | 1.017 |
| buildacubesat-project-bac-hardware | - | - | 1.000 | 1.000 | 1.606 | 1.262 | 1.004 |
| computergeek1507-kicad-designs-pi- | 1.000 | 1.000 | 1.000 | 1.000 | - | - | 1.000 |
| dimoustroufis-librewave-ecp5-libre | - | - | - | 1.000 | 1.437 | 1.169 | 1.094 |
| govish-fusion-pack-buck-converter- | 1.035 | 1.000 | 1.000 | 1.000 | 1.199 | 1.093 | 1.000 |
| heypcb-kestrel-esc-kestrel-esc | 0.821 | 0.900 | 1.000 | 0.996 | 1.017 | 1.000 | 1.000 |
| jrsteensen-openhornet-controller-a | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| librespacefoundation-qubik-qubik-b | - | - | - | 1.000 | 1.150 | 1.071 | 1.058 |
| logisim-evolution-gecko5education- | 1.006 | 1.000 | 1.000 | 0.975 | 1.096 | 1.050 | 1.000 |
| martinberlin-h-cinread-it8951-mini | 0→0.0174 | 0→0.00922 | 0→0.515 | 0→1.16e+03 | 1.052 | 1.025 | 1.000 |
| robertpheller-rpi-rrcircuits-stm32 | - | - | - | 1.000 | 1.000 | 1.000 | 1.000 |
| seniordesignmay1607-pcb-hdmi2rgb-h | 1.061 | 1.015 | 1.000 | 1.025 | 1.000 | 1.000 | 1.000 |
| shazmeenshz-esp32-flight-controlle | 1.003 | 1.000 | 1.006 | 0.975 | 1.073 | 1.035 | 1.001 |
| sparkfun-micro-bit-moto-bit-sparkf | 1.014 | 0.999 | 1.000 | 1.031 | 1.536 | 1.000 | 1.002 |
| zephray-nekoink-pcb-2 | - | - | - | 0→7.3 | 1.369 | 1.144 | 1.062 |

- Buck input current (B/A): DC copper loss 0.82–1.06×, board totals within ±3 %. Kestrel's 0.82: the cell's loss current now returns through its controller's ground pins, against the synchronous rectifier's ground current, shortening the net return.
- Turn-off current (C/B): loss.loop median 1.16× (1.00–1.78), overshoot 1.00–1.33×, board totals ≤ +9.4 % (librewave). Cells with no inductor in their circuit (jrsteensen, robertpheller, hdmi2rgb) do not move.
