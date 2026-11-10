<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-legal-ab2: anchoring tight parts, KiCad-verified, sized for a decision (pre-registered)

Written 2026-11-10, before any run of this experiment. Ledger J19. It follows `loop-legal-ab`, which failed its rule: legal 21 vs 18 and 21 vs 17
of 60 cells, Fisher p 0.70 and 0.56. In that run 12 of 20 boards were illegal in every arm, and melexinvn regressed from 3 of 3 legal to 0 of 3.

## Change under test (branch `loop-legal-exp2`, `loop-legality` at 887f558 and `exact-arc-tolerance`)
- A big part with no grid spot free of the fixed geometry is fixed before the seed, as before, when a grid-free spot exists once its courtyard may overhang.
- A spot that only the exact check accepts is now fixed only after KiCad's DRC agrees (up to three spots). Otherwise the part keeps only the overhang. This addresses melexinvn: a hole clearance the exact check passed and KiCad flagged.
- Both arms also carry the exact model's arc fix (PR #52): pad and hole arcs within 0.001 mm. It is a correctness fix of the check and is not under test here.

## Boards (`boards.txt`, written when the scans finish, before any run; `select_boards.py`)
The pool is every board with a tight part in three scans. The scans run only the anchoring check and read no score:
- the 213 merit boards (stored task inputs), which gave the 20 boards of `loop-legal-ab`;
- 138 further boards with a stored fixed-task kae output;
- the 2,786 qualified, usable corpus boards, from the corpus board with the benchmark's mechanical rules applied (`kae.place.fixed`, the same rules `prepare` uses).

Draw: one board per repo family, in sha256(`loop-legal-ab2-2026-11-10`, id) order. The 20 boards of `loop-legal-ab` come first, since they were chosen by mechanism, not outcome. The first batch is 60 boards; the rest of the pool is the pre-registered extension. Attempts k = 3 (seeds 0-2).

## Arms (`setup.sh`; J1's restart wrapper; joint-fixed; interleaved)
`staged ctl` / `staged` (J1 arm a, `anchor_tight=0` / default) and `joint ctl` / `joint` (J1 arm d, `anchor_tight=0` / default).

## Primary outcome and decision (`analyze.py`)
- **Primary:** KiCad placement errors (the placement-type errors the score's `legal` uses), summed over the 3 seeds per board. Unit `d = (t − c) / (t + c + 1)`, paired per board.
- **Passes** if, in both chains (staged and joint), mean `d` < 0 with sign-flip p < 0.025, and the guard holds.
- **Guard:** no board is legal in at least 2 of 3 seeds under control and at most 1 of 3 under the change. A single such board fails the experiment, whatever the primary says.
- **Not worse:** total open connections within +3 % of control in each chain (A/A noise 2.8 %), and DRC errors not higher.
- **Secondary, reported:** `legal` and `legal_strict` rates (Fisher exact), clean, completion, placement errors by type, CPU, and the anchoring rows of each run's report (grid-free, KiCad verdicts).

If the primary is undecided after 60 boards, run the extension once. If it is still undecided, report undecided.

## Costs (information only)
About 0.7 CPU-h per board and arm on J1's wrapper, so 60 boards x 4 arms x 3 seeds is about 500 CPU-h. Less in practice: small boards dominate.
