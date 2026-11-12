<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# The physics set's coverage: what the fast evaluator can score, and why some boards have nothing

**TL;DR**
- **The 213-board physics set** (route-finish-ab) is scored by `kae.excite.evaluate` (the fast field evaluator) under intents compiled from model-written board specs (`tools/research/physics/intent_from_spec.py`). An audit before stage 2 of the A/B found that a board's lack of physics was often a bug, not an empty board (§1).
- **Evaluator and intent bugs were fixed** (§2), all from the human layouts and synthetic boards, blind to the A/B arms: the evaluator never saw the schematic's pin facts the intent was compiled from; parts that supply and consume were never loads; a self-powered module had no heat band; split footprints, fuses and net ties broke the DC flow; the field window cut off copper beyond the outermost pad; radio modules had no EMI observer or aggressor.
- **Human-layout coverage (§3):** 158 of 213 boards scored (28 of 41 before on stage 1's boards, now 34), 25 of 32 radio boards with EMI observations (19 with cable emission). J2032, USB armory and PolarFire have no result yet.
- **The raster's pitch bias does not need a correction for the A/B (§4).** The systematic part (first order in pitch, same sign) is common to both arms and to the human layout. The part that does not cancel is sub-cell snapping, measured by shifting the raster: 1–2% on copper loss, rail drop and the board total, 7–16% (median) on single field observations. Local refinement would not remove it; differences inside the shift spread are noise.
- **Boards that still have nothing** are listed with the reason (§5): netless or unrouted files, passive boards, and parts the classifier leaves unknown.

Tags: [M] measured here on the human layouts; [I] inference. Evaluator: [physics-driven-build](../architecture/physics-driven-build.md); intents: [intent-driven-objectives](../architecture/intent-driven-objectives.md); field-solver accuracy: [field-solver-accuracy](../../research/physics/field-solver-accuracy.md).

## Key facts

### 1. What the audit found [M]

Stage 1 of route-finish-ab evaluated 41 human layouts: 13 had no observation at all ("0 sources, 0 observers" or only open copper) and none had an EMI term matched on a radio. Across the 213 boards, a plan-only pass (sources, observers and the DC plan, no field solve) and the ab4 evaluations gave the classes below.

### 2. Fixes, each in its own commit on `physics-set-fix`

| Problem | Boards (examples) | Physics of the fix |
|---|---|---|
| Intents compiled from a brief with the schematic's pin types and names (kaeres `pintypes.json`); the evaluator and `kae.intent` built theirs from the bare board | 45 of 213 saw a different circuit (govish buck: no cell, no +5V source; kocer SDR: four cells missing) | The operating facts carry `pins`; `kae.board.pinfacts.apply` fills only pads the board left blank, in the evaluator and in `kae.intent` |
| A feed was never a load: a module or MCU whose regulator feeds a rail drew nothing | fora888 (Teensy), openremise (Pico) | A consuming feed (module, or an MCU/FPGA/radio IC) is a load on its input |
| A part powered from off the board (its own USB) and alone on its rail: no DC flow, so no heat band | aizuknight keyboard (XIAO, about 0.18 W) | `Plan.self_loads`: its V·I is heat at its pads; the heat band runs without a DC flow |
| Two footprints with one reference: the plan kept the last one | fora888 (Teensy edge and back pins) | Pads merged, as the copper model's REF.NUM tokens already were |
| An export connector without a ground pad of its own was no load | buildacubesat TPSM5D1806 (6 A on J4) | Its return is taken at the other connectors' grounds, when its current is stated |
| Loads missing by kind | LED digits, optocouplers, oscillators | LEDs with a rail and a ground pad, optocouplers and oscillators (10 mA prior) are loads; a load on a rail of unknown voltage heats at the DC band's 3.3 V fallback |
| A fuse and a net tie had no circuit element (open) | krzys backplane (fuse), buildacubesat (GNDA net tie) | A fuse is its cold resistance (0.1 Ω prior); a net tie is a short |
| The field window was the pads' extent + 3 mm, cutting off copper routed beyond the outermost pad | krzys backplane (/5V "open", KiCad: connected) | The window also holds the outline and all copper; with an outline it is the same for every layout of a placement |
| Radio modules are ports: no supply observer, no aggressor; no observer on RF pins; E1/E2 scoped `part` also priced the radio's own noise into other parts | 32 radio boards; devotchi (ESP32-S3-MINI) had no source | `radio_kind` by part number; a module's inside (C_MODULE behind its pins) carries its 50 mA / 5 ns steps and is observed; RF pins are victims (1 mV prior); `where: to_part` (victim side only); 1 m cables (CISPR 32 reference) on a radio board whose spec states none |
| Two boards never finished (65 GB, 6–8 h) | J2032 carrier, kocer SDR | Solved patterns freed after their band (J2032 peaks at 34 GB, down from 65, but still exceeds 6 h at 16 CPUs: 4 of 5 bands). A raster budget of 4M cells × layers doubles the pitch (kocer only: 0.5 mm, where its fine QFN pads fall outside the model) |
| Feed cycles (a regulator read backwards) had no way in | 6 boards | The link the pins deny is dropped |
| RF victim taken from a net's name | phecda `/LoRa_Aux` | A named pin must be named RF/ANT |
| No stackup block: silent even split (0.48 mm on 4 layers) | 130 of 213 boards, 22 of 44 multi-layer | Hazard `stackup_assumed`; 4-layer boards take 0.2 mm prepreg + core ([stackup](../rules/stackup.md) reference stacks); other counts keep the even split |

### 3. Coverage before and after (human layouts) [M]

| | Stage-1 boards, human (41) before → after | 213 boards, ab4 arm B → human after |
|---|---|---|
| Evaluated | 41 → 41 | 211 → 210 |
| Scored (kae.intent tiers present) | 28 → 34 | 148 → 158 |
| Radio boards with EMI observations | 2 of 6 → 5 of 6 | 19 of 32 → 25 of 32 |
| With cable emission (E3) | 2 → 4 | 16 → 19 |

The before column is the old code on the human layouts of stage 1, and routed arm B of ab4 for the 213 (no full human baseline exists).

### 4. Mesh accuracy and A/B comparisons

**Two errors with different behaviour.**
- **Systematic pitch bias.** Hot loops and plane pairs read +5% to +16% high at 0.25 mm, converging from above at first order in pitch; small decap loops −3% to +2% ([field-solver-accuracy](../../research/physics/field-solver-accuracy.md) §3). It has one sign for one kind of structure. In an A/B at one pitch it scales both arms' loop inductances alike, so a difference keeps its sign; only the difference between two geometries' biases (a few percent of L) could reverse a ranking.
- **Sub-cell snapping.** Where a pad, via or track edge falls inside a cell changes R, L and connectivity at the cell scale. Two layouts route different copper, so this part does not cancel.

**Measured on the 41 stage-1 human layouts** (the raster shifted by ¼, ½ and ¾ of a cell; relative spread max − min over the four):

| Observation | Median | 90th percentile |
|---|---|---|
| copper loss | 1.1% | 2.4% |
| rail drop | 1.4% | 8.7% |
| junction temperature | 0.01 K | 0.33 K |
| supply noise (supply.peak) | 7% | 28% |
| victim pickup (pickup.peak) | 16% | 57% |
| cable common mode (cable_cm.v) | 11% | 83% |
| board objective (limit + cost) | 1.1% | 5.6% |

**Decision: no local refinement and no per-board convergence solve.**
- The snapping spread is larger than the systematic bias on every field observation and is what limits an A/B. Refining a hot loop locally (or halving the pitch, 4× the cells) moves the bias, not the spread's cause: copper still snaps at the finer scale.
- The A/B's noise handling (route-finish-ab PLAN.md: the shifted-raster evaluations) is the per-board convergence check that matters. A field difference between arms inside the board's shift spread is noise; the board objective is stable to about 1% (90% of boards within 6%).
- **Against the human layout** the same holds, with one caveat: human copper is wider and poured more often than a router's, and the bias depends on width over height, so a human-vs-router loop comparison carries a few percent of extra bias (reading the router's narrower loops relatively higher). Rankings of large differences stand; differences under about 5% of a loop's L do not.
- One case is not noise: a board whose objective jumps between offsets (sparkfunx smol-esp32, ×4) has copper that opens or closes at the cell scale (fine-pitch pads or thermal spokes narrower than a cell). Such a board needs its connectivity fixed, not averaging.

### 5. Boards that still have nothing to score

| Class | Boards | Why |
|---|---|---|
| Passive | 12 | no active part or rail (kamilix patch array, keyswitch and adapter boards) |
| No nets or unclassified parts | 4 | Cypress placement benchmark, proto-boards |
| No rail recognised | 14 | e.g. 1kbgz linerack (no nets); 2-layer keyboards with a Pro Micro and no named rail |
| Rails without source or load | 10 | unclassified terminal blocks, transistors as the only loads: real coverage gaps, not fixed |
| Human layout open (no score at all) | 12 | sampled with KiCad: truly unfinished (ajjackson, erichardy, complubot, nhatminh2h: 31–268 unconnected; kocer 499+) |
| Scored, DC band void / some sources open | 22 / 18 | scored on what closes; sampled only |
| Not finished | 3 | J2032 (6 h timeout), USB armory (KiCad's refill hangs), PolarFire |

Capacitive pickup is not in the fast evaluator's `pickup.peak` (only `kae.excite.wideband` adds Cm; the fast one uses capacitance for switch-node loss). On the radio boards with RF nets it is small: above 10 fF only 2 of 11 boards, ≤ 3.3 mV into 50 Ω, against 64–521 mV inductive on the same victims; the second figure was on a false victim later removed.

### 6. Rail drop is never negative [M]

`drop.rail` of a load is its rail's loss from the source's output pins to the load's supply pins plus its ground's rise from the source's ground pins to the load's ground pins (`kae.excite.dc.observe`). Before 2026-11-12 the signed sum was reported, and 23 values in stage 2 were negative (down to −1.6 mV, larger on a few boards), with zero price, so ratios across arms crossed zero.

- **The sign is physics, not a reference choice.** Potentials are differences inside one connected net, so no ground node enters. In the case taken apart (Green Lion's BMS shield, negative at 13–15 of 19 corners in every arm) the rail part was ≥ 0 and the ground part negative: another rail's return current, or the source's own ground-pin current, flows through ground copper shared with the load and leaves the source's ground pin above the load's. There CN7 is both the +5 V source and the +12 V load; the 0.3 A of +12 V returns from CN7's ground pins to J1, putting them 11 mV above IC1's ground; IC1's rail part is +1.2 mV, the sum −10 mV. The load then sees more than the source's voltage.
- **Definition.** A drop is what the load loses of its source's voltage, so `drop.rail` = max(0, signed sum). The signed value stays in the observation's `signed` list for the reader. A cost term with a plain rate on drop.rail had paid a credit for a negative drop; it no longer does. `harm.phi` already priced a negative drop at 0.
- **Not covered:** an over-voltage at a load (signed < 0) is not a requirement any intent states today; a term for it would read `signed`.

## Conflicts and open questions

- **Module aggressor priors** (50 mA in 5 ns behind 1 µF) are stand-ins; a radio module's transmit bursts are larger but slower. A datasheet value should replace them.
- **Unknown-kind parts** (Eagle imports, castellated pins, terminal blocks) still leave rails without a source; the classifier, not the evaluator, is the place to fix them.
- **Human layouts with open copper** (KiCad agrees on some, not on others) still void their DC band; whether a raster artefact (spokes or fine-pitch pads under a cell) or the board is the cause is decided per board.

## Sources

- Code: [`kae.excite`](../../../kae/src/kae/excite/), [`kae.board.pinfacts`](../../../kae/src/kae/board/pinfacts.py), [`intent_from_spec.py`](../../../tools/research/physics/intent_from_spec.py); tests: [`test_excite_physics_set.py`](../../../kae/tests/test_excite_physics_set.py), [`test_intent_from_spec_emi.py`](../../../tools/research/physics/test_intent_from_spec_emi.py).
- CISPR 32 (radiated emission, class B, 10 m; cable reference length); Ott, *Electromagnetic Compatibility Engineering* (2009), eq. 12-7 (cable common-mode emission).
