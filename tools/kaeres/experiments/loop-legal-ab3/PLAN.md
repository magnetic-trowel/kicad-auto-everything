<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-legal-ab3: anchoring tight parts, third run (pre-registered)

Written 2026-11-10, before any run of this experiment. Ledger J19. Follows `loop-legal-ab2`. Its primary passed in both chains: placement errors per board, p 0.010 staged and 0.005 joint. It failed its guard:
- Three module carriers lost legality.
- Cause: the anchored module was the board's only free part, `place()` then wrote no poses, and the module stayed at its staged pose off the board.
- Staged opens also rose 3.6 %.

## Change under test (branch `loop-legal-exp3`: `loop-legality` at 68908f2 with PR #52's arc fix in both arms)
- The `place()` return when no free part is left now carries the pinned and anchored poses. A regression test covers it.
- An anchored spot must keep every pad centre inside the outline.
- Otherwise as in `loop-legal-ab2`: grid-free spots are fixed directly, and spots only the exact check accepts are fixed only when KiCad's DRC agrees (up to 3), else the part keeps the overhang.
- Before this plan, `kae place` (seeds 0 and 1) made all three carriers legal under KiCad's transplant scoring.

## Boards and arms
- Boards: the same 60 boards as `loop-legal-ab2` (`boards.txt`, copied unchanged), seeds 0-2. `boards-extension.txt` (103) is the extension, under the rule below.
- Arms: `setup.sh`, as in ab2. `staged ctl` / `staged` (J1 arm a, `anchor_tight=0` / default) and `joint ctl` / `joint` (J1 arm d), J1's restart wrapper, joint-fixed, interleaved.

## Decision (`analyze.py`); all four conditions are required, in each chain (staged, joint)
1. **Primary:** KiCad placement errors per board, summed over the 3 seeds. Paired unit `d = (t − c) / (t + c + 1)`; mean `d` < 0 with sign-flip p < 0.025.
2. **Guard:** no board is legal in at least 2 of 3 seeds under control and at most 1 of 3 under the change. One such board fails the experiment.
3. **Opens bound:** total open connections under the change at most 3 % above control (A/A noise on total opens 2.8 %). Above that, the experiment fails, whatever the primary says.
4. **Errors:** total DRC errors not above control.

If 1 is undecided but 2-4 hold, run `boards-extension.txt` once and decide on all boards pooled.
Secondary, reported: `legal` and `legal_strict` (Fisher exact), clean, completion, placement errors by type, CPU, and the known boards (openremise, esp32 flight, vik-pmw3360, melexinvn, the three carriers).

## Costs (information only)
As ab2: about 500 CPU-h.
