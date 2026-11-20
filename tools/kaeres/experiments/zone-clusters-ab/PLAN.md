<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# zone-clusters-ab (pre-registered 2026-11-19)

**Change (PR #117).** `repair.analyse()` judges an open net with fills by its parts (`net_clusters`), not by
which unconnected pairs KiCad's DRC happens to name. The names vary between DRCs of one board. On
ch32v003 the round-0 DRC named GND's cut-off island as a zone pair in 2 of 6 runs, at 2 threads as at 16,
and main split GND's plane in those runs and dropped its planes in the others. With #117 the round-1
decision was the same in 6 of 6 runs at 16 threads, with both namings present (kaeq A/A #112441).

**Decision it changes.** Merge #117 or not.

**Arms.** All arms use `kae.route.cli route --time 900`, KAE_BUDGET=work, PYTHONHASHSEED=0 and
KAE_WORKERS=1, with Freerouting pin 37b1a8b and harness 6d72634.

| Arm | Method | kae |
|---|---|---|
| Control A | cb014b7885a5 | main 6d72634 |
| Control B | af358cb73282 | main 6d72634 (identical twin; differs only by an unread env var) |
| Treatment | ffdf3c65a391 | b0fb800 |

**Boards.** 40 boards (`boards.txt`) from power_pours ∪ inner_planes ∩ route_demand moderate/hard ∩
`usable_route_test`, restricted to boards with an earlier kae-bridge work900 run that left open
connections (so the mechanism can act) and at most 1.6 CPU-h per run (9 runs are under the 16 CPU-h
board cutoff). One board per repo family in turn, by hash. 3 seeds (attempts 0-2).

**Expected effect.** Two effects:
- The twin spread (control A vs control B, same seed) measures main's run-to-run noise from DRC pair
  names. Treatment vs control A should differ no more than the twins do.
- Treatment's own run-to-run spread is not measured here; the A/A covers that.
- Mean opens: no direction expected. The decision rule is the same; only its input is canonical.

**Primary metric.** Per-attempt open connections paired by seed (treatment vs control A), with a CI.
Guards: delivered opens, DRC errors by type, completion, ceiling and wall-stop hits. Also report the
twins' paired difference as the noise floor.

**Verdict.** Merge if the guards hold and the effect's CI does not show harm beyond the twin floor.
A credible gain is a gain. If the result is underpowered, call it unknown and extend.

**Cost.** 40 boards x 3 arms x 3 seeds = 360 runs at up to about 1.6 CPU-h each; most are well under.
