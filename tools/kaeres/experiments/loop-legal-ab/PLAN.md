<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-legal-ab: fixing big parts with no spot, before the seed (pre-registered)

Written 2026-11-09, before any run of this experiment. Ledger J19 (legality root cause). Code: `loop-exp`.

## Mechanism
A big part (over 5 % of the board) with no grid spot free of the outline, locked parts and rule areas can never be placed legally by the annealer or the
legalizer. `_anchor_tight_parts` (kae.place.pipeline) lets its courtyard hang over the edge as the closed loop would and fixes it at the first exactly clean spot, before the seed.
Found on three boards with clean human layouts, legal in 0-2 of 13-19 stored runs (openremise-sniffer, esp32 flight controller, vik-pmw3360).
Before this experiment, `kae place` with the change ended legal under KiCad on those boards (openremise and esp32 one seed each, vik-pmw3360 two seeds).

## Boards
The boards of the merit suite where a part is anchored, from a scan of every merit board's task input that runs only the anchoring check (no placement, routing or score). The list goes in `boards.txt`
when the scan finishes, with no outcome of these arms read. The change is a no-op on every other board, since no part is tight there.
Attempts k = 3 (seeds 0-2): the expected effect is large (0 of 15 legal to most of 15).

## Arms (`setup.sh`; J1's restart wrapper; joint-fixed)
`staged ctl` / `staged` (J1 arm a with `anchor_tight=0` / default) and `joint ctl` / `joint` (J1 arm d with `anchor_tight=0` / default), interleaved.

## Outcomes and decision
`legal`, `legal_strict`, `clean`, placement errors per type, completion, open connections, errors, CPU, physics on boards both arms route (above the J21 floor).
Passes if the legal rate rises on the anchored boards (Fisher exact on board x attempt, p < 0.05) and neither opens nor errors get worse beyond the A/A noise. With so few boards a clean-rate gain is reported, not decided.

## Addendum, before any run of this experiment (2026-11-09)
The board scan does not prepare the task inputs, for queue reasons. It reads a stored kae joint-fixed output of each merit board (which keeps the task's locked flags), strips the routing, stages the movable parts off the board and sets the corpus project files beside it, then runs only the anchoring check. It reads no score. The three known boards are the check that it finds what the task inputs show. Each run's own report (`anchored`) says whether the part was really anchored on the task input.
