<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# THT neck after confirm-default-ab: short-neck heating, land caps, and a fork on the 20 physics boards

**Question.** confirm-default-ab ([report](2026-11-13-confirm-default-ab.md), branch `route-finish-ab`) failed its THT overhang gate: 1.4 mm² in A against 559 in N, higher on 13 of 20 boards. Does sizing necks by their real heating as short conductors, rather than by IPC-2221's long-trace chart, bring N's THT overhang to A's level with N's physics?

**Fork.**
- **Why A's boards.** N's kept boards are finished already, and power copper never narrows copper, so finish on them cannot undo an overhang. The fork therefore finishes the 20 complete physics boards from A's kept board (method `591ae9f64339`), once with N's code (f0, `4392518`) and once with this branch (f1). A and N are the stored outputs.
- **Measures.** `overhang_diag.py` and the deterministic evaluator (intents `compiled-9867d0b`) on all four arms. DRC by type compares the finish reports of f0 and f1.
- **Summary.** `tools/research/routing/pc_tht_confirm.py`.

## Result (f1 = this branch's head)

| | A | N | f0 | f1 |
|---|---|---|---|---|
| THT overhang, mm² | 1.4 | 559.4 | 520.5 | 520.5 |
| SMD overhang, mm² | 14.7 | 4.9 | 8.5 | 8.5 |

- **f1 against f0.** loss.copper median 1.000, worse on servo bonnet +3.2 %, magtag +2.0 % and aquarium sensor +0.4 %; drop.rail worse on magtag +5.8 %, servo bonnet +5.1 % and aquarium +0.2 %; Tj and heat.track unchanged.
- **DRC.** No error type differs except cm4-carrier, where solder_mask_bridge falls from 30 to 24.
- **f1 against A.** loss median 0.71, drop median 0.78.
- **f1 against N.** Medians 1.000. The boards that differ (ostr, cm4, pi-wedge) differ in routing, not finish: f0 shows the same.

## What was tried, in order

| commit | change | THT f1 | f1/f0 physics worse |
|---|---|---|---|
| 9d3721cb | necks sized by short-conductor heating (`short_neck_width`): ΔT = I²ρL²/(8k w² t²), 10 K at 3× I (2.1 A: 0.27 mm, IPC 3.8 mm) | 520.5 (no copper changed) | magtag loss +4.9 % |
| d97ff7ab | the loss budget caps loaded pads at their land width before keeping them wide | 349.4 | cm4 loss +4.9 %, drop +10.6 %; secsense, aquarium +1 % |
| 68ffae4e | the budget is a share of the *grown* loss (routed currents at max_width), not the routed copper's | 520.5 | magtag +2 %, servo +3.2 % |
| 12dbbec2, reverted | one DC solve over all rails with the DC branches (fuses, ferrites, diodes) | 520.5 | cm4 +13 %, magtag +4.5 % |

## Reading

- **The heat-sunk hazard was not the cause on these boards.** The coordinator's diagnosis (zx J4–J7.31 kept wide by IPC-2221 widths) holds for N's run. In the fork, the short-neck model gave every pad a feasible neck, and f1's THT overhang still equals f0's. What keeps the copper wide is the loss budget (`tht_pad_kept_wide`, 69 entries). These pads carry the rail's current: zx's 2.5 mm /5V bus runs through J2–J7.31 at 0.3–2 A, and secsense's and fortitude60's feeds likewise. The overhang there *is* the conductor.
- **Capping those pads at their land width removes the overhang (-33 %).** The evaluator then shows several % more loss and drop on cm4 and aquarium, against 0.2 % in power copper's model.
- **The DC solve on routed copper underestimates what necks cost the finished board.** Grown copper merges pads and makes paths the routed graph does not have, and the cost stacks over each neck's taper and min-run merges. Every version that removes loaded overhang loses more than the evaluator's floor on some board.
- **Remaining THT overhang against A, per board.** zx2-backplane 238, fortitude60 130, secsense 42, aquarium 36, servo 25, kitten 14, pi-wedge 11, btmessbox 10, can-bus 5, rheoboard 3, stlinkv3 3, lichen 1 mm². All of it is power copper on rails into connector or resistor lands that carry the rail's current under the DC plan. A has none because A has no power copper and 1.4× its loss (f1/A loss median 0.71).
- **Open: price necks with the evaluator itself.** One DC solve of the grown board with and without each set of necks; revert those over the floor. Or accept the overhang where current flows, as the human zx layout does with 1.7 mm tracks (no overhang, narrower rail).
