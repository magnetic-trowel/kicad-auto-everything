<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Post-audit baselines (2026-11)

Scope: the reference methods re-run after the 2026-11 bug audit, against the pre-audit runs; the score v8 rescore of boards that ignore the unconnected check. Not here: the audit itself -> [audit](../audit-2611.md).
Keys: baseline-2611b, post-audit baselines, merge3-ab, load-stable boards, fr-h1-rescore2, unconnected_items ignore, score v8

**Status:** worked as baselines. The reference methods re-run after the whole-codebase bug audit, on
the 213 merit boards. **Correction (2026-11-08):** the before/after comparison below is not evidence
either way: the pre-audit runs are from another week, and on this host the same recipe days apart left
13.9 % more open connections ([host-load drift](../benchmark-drift-2611.md)), more than the −4.6 % here;
the "load-stable boards" filter assumed only large boards drift, but small ones do too.
**First published:** 2026-11-04, branch `place-escape-keepouts`.

## What changed before these runs

Commit 21bc53d gathers the audit's fixes (about 50: router, placer, board loader, physics inputs, harness and
scoring), task spec 9 (place-fixed classifier rules 5: castellated edge pads and 4UCONN connectors are
fixed) and score v9. Every place-fixed / joint-fixed result and every physics number made before is on
another task spec or evaluator, hence these baselines. Recipe: `tools/kaeres/experiments/baseline-2611.sh`;
experiment `baseline-2611b` (`baseline-2611` is superseded: its Freerouting method was pinned to a
spec-8 harness, so its runs landed on the old task and were discarded; kaeres now refuses such a method).

## Results

One attempt per method (restart portfolio, 900 s × sqrt(footprints/40)), against the same methods' runs in
`merge3-ab` (pre-audit). Open connections are pcbnew's count past KiCad's 499 cap.

On all boards Freerouting, a fixed binary, also "improved" by 10.6 %: on 12 large boards it reached
different results within its own time limit (bastardkb dilemma 300 → 94 open, sdi-mipi 920 → 730), so host
load moves results on big boards. The fair comparison is on the 196 boards where Freerouting's result did
not change:

| method | boards | open connections | boards better / worse | clean | errors / board | physics median |
|---|---|---|---|---|---|---|
| kae staged (escape soft, then the default) | 194 | 754 → 719 (−4.6 %) | 26 / 16 | 64 → 66 | 26.6 → 26.5 | 3.00 → 2.60 |
| kae bridge on the human placement | 196 | 299 → 288 (−3.7 %) | 9 / 8 | 57 → 57 | 26.8 → 26.7 | 3.00 → 3.00 |

On all boards (load-confounded on the large ones): kae staged 3,793 → 3,582 open (−5.6 %), kae bridge
4,603 → 4,127 (−10.3 %), Freerouting 8,642 → 7,722 (−10.6 %). kae joint loop final (no pre-audit run on
these boards): 211 boards, 65 clean, 5,392 open.

Physics is kae's module physics (Σu, lower is better), both sides measured by the fixed evaluator
(4d02d001c80b; merge3-ab re-evaluated with `kaeres rephysics`).

## Boards whose project ignores the unconnected check

Score v8 (bae48db) counts unconnected items where a project sets the check to "ignore"; before, every
output on such a board scored as fully routed. Experiment `fr-h1-rescore2`, the three qualified boards:

| board | Freerouting 2.5.0 | kae bridge |
|---|---|---|
| ttankbuster cyberwatch v1b | 29 of 85 open (was "0 of 0", clean) | 14 of 85 |
| gamaphy freedom-rp2040 | 48 of 146 | 14 of 146 |
| feastorg slice prto-smt s2l | 3 of 36 | 2 of 36 |

gamaphy's human layout is not fully connected either (4 unconnected), so it leaves the qualified set when
re-prepared.

## Caveats

- Before and after ran in different weeks: within host-load drift (status line above).

- kaeq froze jobs for memory before it gained its "timed" class (2026-11-03); 29 of 419 jobs here were
  frozen, at most 1.7 min. None timed out.
- One attempt per method: per-board differences on small boards are partly seed noise.
