# kae exact placement legality and the KiCad DRC loop

**Status:** worked (board-label term partial).
**First published:** 2026-10-23, commit [b296354](https://github.com/magnetic-trowel/kicad-auto-everything/commit/b296354bce9e3d560755448ea119ad81912b5349) on branch `claude/vigilant-mayer-i91rrr` (human gate [ea517f9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ea517f91c79166002d7e2a1d88a6849f5dae6fab), KiCad feedback [c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206)).

The [kae placer](kae-placer.md) ends with a legality stage that reproduces what KiCad's DRC checks for a placement on exact polygons, repairs violations by moving parts, then runs kicad-cli DRC on the written board and turns KiCad's remaining complaints into constraints for another round. Passes for protection order, silkscreen and board labels share the same machinery. Split C went from 66/73 legal to 72/72, and the exact model reports no finding type that KiCad does not on any of the 112 human layouts.

## Idea and how it works

**Exact model** (`place/exact.py`, `ExactModel`). Holds each part's real shapes at its pose and checks: courtyard overlap per side (with KiCad's 5 um deflation), pad clearance with net-class and pad-local overrides, `hole_clearance` and `hole_to_hole`, copper to edge, items in rule areas, solder-mask bridges (including mask-only apertures and pad openings over other nets' zone fills, following KiCad 10's `drc_test_provider_solder_mask.cpp`), footprint copper and mask graphics, board copper graphics and board copper text as KiCad glyph outlines (fetched through the [pcbnew bridge](kae-board-model.md)). Candidate pairs come from clearance envelopes. `findings_at(i, X, Y, K)` prices a trial pose without committing it. `repair` moves each culprit to the nearest grid-free and exactly clean spot, evicting smaller parts, with re-seed and lookahead escalation; `diagnose` reports why a part is stuck.

**Human gate** (`tools/research/place/humangate.py`). Read each human reference board into a Problem, run the exact model on every part and compare the finding types with KiCad's DRC on the same board. A type kae reports and KiCad does not is a model false positive. Every new rule (text knockout margins, mask-only apertures, copper text, silk glyphs) had to pass the gate.

**KiCad loop** (`kicad_feedback`, `cli._kicad_loop`). After writing, kicad-cli DRC runs on the board and placement errors become constraints the next repair honours:
- pair separations: current distance + a step, growing while KiCad still objects;
- avoid-geometry: keep a part off a given text or graphic (by uuid);
- edge-clearance growth: +0.05 mm per report, blaming only the part whose copper KiCad names (blaming the neighbour left paw3222 illegal);
- findings that involve only fixed items are not the placer's.

Up to 6 rounds, a retry of a signal-killed kicad-cli (<= 2), and a **safety net** that writes back the best KiCad-judged placement if the loop ends worse. A round that moves parts re-runs the silk pass.

**Protection order.** Brief protection chains (connector -> TVS -> series part -> protected IC pin) become rules "the protection part is nearer the connector than the protected part". The annealer prices violation distance / mean part size (`w_order`). `OrderGuard` forbids any repair or silk move that raises a part's broken-rule count. The final pass `fix_order` moves, per broken rule, the protection part (else the protected part) to the nearest grid-free, exactly clean spot with fewer broken rules; all moves together may cost at most +3% physics, <= 8 priced spots per part. This is a design choice, not learned: only 60% of human layouts put the TVS nearer the connector.

**Silkscreen.** Only where the project makes `silk_overlap` or `silk_over_copper` an error. Other parts' silk and pad mask openings are modelled with KiCad's own glyph outlines, fetched per quarter turn (KiCad keeps text readable, so a part turned 180 degrees does not show its text turned); overlap threshold 1e-5 mm^2. A soft annealer term `w_silk` (default 1; overlap / mean part area on a packed silk grid) and a final pass `fix_silk`: the smaller part of each conflict moves within +3% physics and +10% local HPWL, without breaking order rules, <= 3 rounds. Reference text cannot be moved because the scorer accepts footprint poses only.

**Board labels** (`place/labels.py`). Infer which part each board-level silk text names: `ref` (token = a reference), `pin` (token = pin function or net of a connector-like part's pad), `keyword` (>= 3 chars in an LED's or switch's net names; ON/OFF for <= 2 switches), `row` (>= 3 numbered labels aligned within 0.3 mm, matched in numeric order to exactly one family of LEDs, switches or connectors with consecutive numbers). `LabelTerm` pulls a part's labelled pads to its label with a dead zone (one third of the row pitch along a row, preserving order).

**Severities** (`place/problem.py`: `FIXED_ERROR_CHECKS`, `Problem._severities`; option `place_severity`, `kae place --severity`, project text variable `KAE_PLACE_SEVERITY`). Until 2026-11 legality followed each board's `.kicad_pro`: a check the project set to warning or ignore was dropped, so on those boards parts were placed on courtyard-free pads, copper-to-edge became 0 and rule areas were ignored. That matched the scorer's `legal`, not physics. Now:

- `level_c` (default): courtyard overlap, copper-to-edge, rule areas, clearance, shorts and hole clearance are errors whatever the project says. On a project that waives `courtyards_overlap`, each courtyard is taken in by 0.15 mm (IPC-7351 Level B 0.25 mm excess minus Level C 0.10 mm, [dfm-fab-limits](../../topics/rules/dfm-fab-limits.md)), so neighbours' margins may overlap but no part sits on another; elsewhere it is `strict`. The KiCad loop runs DRC on a staged copy whose project has the checks at error (`route/drc.promote_severities`), except waived courtyards, which KiCad cannot check partially (it skips a negative `courtyard_clearance`), so the exact model alone checks them and the scorer's `legal_strict` still counts the margin overlaps.
- `strict`: drawn courtyards everywhere.
- `board`: the old behaviour.
- Kept as waivers in every mode: custom `.kicad_dru` rules with their own severity; KiCad's own exemptions from copper-to-edge (castellated pads, `Pad.fab`, and edge-connector `connect` pads, as in `drc_test_provider_edge_clearance.cpp`); a violation whose items all belong to one footprint (its own cut-out against its own pads, a resistor array's pads), which no move fixes (`exact._intrinsic`).
- Every downgraded check gives a hazard in the place report: `project_check_kept_strict` (info; warn under `level_c`) or, under `board`, `project_check_ignored` (warn).

Why: the human layouts of boards that waive a check do break it. With the check at error, KiCad's DRC flags 25 of 30 sampled boards that ignore courtyards, 20/25 for copper-to-edge, 14/20 for clearance and 7/11 for shorts. Of 490 courtyard pairs on those boards, 233 overlap by less than 10% of the smaller courtyard (margins), 153 by 10-50% and 104 by more than half (parts under modules, encoders and other parts). Copper-to-edge waivers come mostly from footprints' own cut-outs (1,298 of 2,464 findings; exempt above) and connector pads at the edge (810, 25 boards). Clearance and short waivers are mostly footprint-internal (hot-swap MX/Choc sockets, net ties, resistor arrays) or routing. On the 64 merit-500 or sampled boards that waive courtyards, utilization rises from 0.05-0.75 to above 1 on 8 boards under `strict` and on 5 under `level_c` (dense drone ESCs, a compute-module carrier): those cannot be placed legally in full, and the report says which parts are stuck. Why `level_c` is the default (smoke, kae place 300 s, seed 0, courtyard-waiving git4dcc decoders): d12 is legal in all three modes with HPWL 186 mm (`board`), 228 (`level_c`) and 362 (`strict`); d24 is legal with `board` (184) and `level_c` (297) but not with `strict` (57 courtyard and 31 short errors left by KiCad: the board does not fit). The A/B of `strict`, `level_c`, `board` and the body modes is [legality-ab.sh](../../../tools/kaeres/experiments/legality-ab.sh).

**Bodies** (`Problem.relax_bodies`, option `relax_bodies`). A footprint without a courtyard occupies its body (the box of its fab drawing and pads). `relax_bodies` frees through-hole ones to their pads, on the grounds that "KiCad does not check bodies". It used to run up front on any board over 95% utilization and as the last escalation step. On merit-500 the 95% trigger fires on 64 of 499 boards, 52 of them with parts to relax; the escalation fired on 6 of 145 joint-loop boards, and in 3 of them kae's output then had a USB receptacle over 0402 parts, overlapping axial resistors, and a USB-C receptacle over diodes and a button, none of which the human layout has. A body on the board cannot share space; only a part standing off on headers can, and kae cannot tell which. So `relax_bodies` is now `off` by default; `escalate` relaxes only when legalization fails and `auto` is the old behaviour. Every relaxed part gets a hazard: `body_overlap` (block) when its body ends over another part at the final poses, else `body_relaxed` (info).

## What we tried

Split-C placement sweeps across versions (`csweep.py`, 600 s, seed 0), the human gate on all 112 boards, silk A/B on the 5 projects that make silk an error, label precision on the 91 tasks that carry board silk text.

## Results

| measure | result | source |
|---|---|---|
| split C legal | e171267 66/73 (exact model only) -> 34fa56b 67/72 (with KiCad DRC) -> fe68468 **72/72**, no legal-to-illegal flips; A 12/12, B 16/16 | [place-split-c-e171267](../../../bench/results/2026-10-23-place-split-c-e171267.md), [place-split-c-34fa56b](../../../bench/results/2026-10-23-place-split-c-34fa56b.md) |
| human gate | A 13/13, B 20/20, C 79/79 since [ea517f9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ea517f91c79166002d7e2a1d88a6849f5dae6fab); caught four exact-checker false positives (net-less fiducials and mounting holes over GND pour) | [place-split-c-34fa56b](../../../bench/results/2026-10-23-place-split-c-34fa56b.md) |
| copper text check | same 4 pads KiCad flags on pic-programmer; 0 on the 21 human boards with copper text | [place-split-c-34fa56b](../../../bench/results/2026-10-23-place-split-c-34fa56b.md) |
| protection order, split C | 0 of 252 rules broken (human layouts break 110), at e171267, 34fa56b and 1ef5bf1; stickhub regression (4 broken via the mask-bridge repair) fixed by the guard, 0 on seeds 0-2 | [place-split-c-e171267](../../../bench/results/2026-10-23-place-split-c-e171267.md), [place-split-c-34fa56b](../../../bench/results/2026-10-23-place-split-c-34fa56b.md), [kae-place](../../topics/placement/kae-place.md) |
| KiCad silk errors, 5 silk-error projects | 224 -> 71 (pass only) -> 13 (term + pass), all legal; HPWL +7-13% on three (seed 0, single runs) | [kae-place](../../topics/placement/kae-place.md) |
| silk in the pipeline, A+B at c9c49d6 | no silk error | [pipeline-ab-c9c49d6](../../../bench/results/2026-10-24-pipeline-ab-c9c49d6.md) |
| label precision (human part within 3 mm) | row 100% (14 labels, 2 boards), pin 68%, keyword 49%, ref 17%; only `row` on by default | [kae-place](../../topics/placement/kae-place.md) |
| noisecard with labels | 7/12 LEDs at their labels (vs 0), physics +1.7%, HPWL +52%, routing unaffected | same |

Residuals: one paw3222 copper_edge_clearance on one attempt (fixed in [644b268](https://github.com/magnetic-trowel/kicad-auto-everything/commit/644b26865698f2be6d2e252cfc5d896dcb6fc7f3)); a pcbnew zone-fill assert on pingdevkit is pcbnew's.

## Verdict

Worked. Two things made it work: the human gate (a model of KiCad's DRC is only trustworthy when it never flags what KiCad accepts on real boards) and the closed loop with KiCad, which catches what the model misses and a safety net that never returns a worse placement. Labels are partial: only numbered rows are precise enough to turn on. The checks were built against KiCad 10.0.7; new KiCad DRC providers need new rules and a new gate run.

## Code

- `kae/src/kae/place/exact.py` (exact model, `repair`, `kicad_feedback`, `fix_order`, `OrderGuard`, silk functions), `kae/src/kae/place/labels.py`, `kae/src/kae/cli.py` (`_kicad_loop`, `--drc`, `--drc-rounds`).
- Study tools: `tools/research/place/humangate.py`, `tools/research/place/labels.py`. Tests: `kae/tests/test_place_labels.py`, `test_place_pipeline.py`.
- First appearances: exact model [b296354](https://github.com/magnetic-trowel/kicad-auto-everything/commit/b296354bce9e3d560755448ea119ad81912b5349); human gate [ea517f9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ea517f91c79166002d7e2a1d88a6849f5dae6fab); KiCad feedback [c6ae9be](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6ae9be0d935bea6e481386ee2863f35a3c62206); `w_order` [bde4bc4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bde4bc4ac8f15c6dfe21aee47d4b14a868c0d9da); `fix_order` [1988ef7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1988ef7370bde434794d6495938603bbc2d4ce1c); silk [cce2277](https://github.com/magnetic-trowel/kicad-auto-everything/commit/cce22775749e0dc6f3842e3fe17b6975d3ac43e5); labels [58f39cd](https://github.com/magnetic-trowel/kicad-auto-everything/commit/58f39cd3f6f712afa229ead7c9213805ec02d955), `w_label` [006e170](https://github.com/magnetic-trowel/kicad-auto-everything/commit/006e17052e0f6024b59858b85b071a8cd852ce8d).
- The joint loop uses the same legality for its windows ([kae-joint-loop](../joint/kae-joint-loop.md)).

## Related

[kae-placer](kae-placer.md), [kae-board-model](kae-board-model.md), [kae-fixed-interface](kae-fixed-interface.md).
