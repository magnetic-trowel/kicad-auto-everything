<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# polish-ab: pair swaps and margin (pre-registered plan)

Written 2026-11-09, before any run. Ledger E116, J58, E7. Code: the commit `setup.sh` records.

## Question
**Pair swaps (E116).** Stage 1 found pair swaps of equal two-pad parts cut the placer's own physics term by over 10% on 27 of 138
boards (over 50% on 11), measured on the term only on stored placements. Does the gain reach routed boards: opens and routed physics, and
what does it do to assembly (nothing to the footprint set; it can lengthen some paths: HPWL reported).
**Margin (J58).** kae's neighbour gaps are 0.19 mm below the human's at the median while clean results were the same (65-66 of 210 across arms), so routing may
have room to spare. Does a placement margin keep clean rate and give gaps closer to what rework and inspection need (ledger: `place_margin`), at the cost of routing?
Assembly: part-to-part gaps set rework nozzle access and AOI shadowing; a board that routes the same either way should take the larger gap.

## E7 (shared-rail decaps have no value)
The placer's term prices a shared-rail cap against its nearest IC pin; the routed evaluator drops it (ownership below 0.5), so swaps of those caps can show up in the
placer term and not in the routed physics. We do not fix E7 here (physics session, its own commit). Decision: report the placer's term (`pair_swap.before/after`)
and the routed physics on valued modules only, and judge by routed opens and valued physics; a term gain with no routed effect is reported as such.

## Arms (joint-fixed, staged: `kae.joint.cli --max-iters 0 --no-modules`, restart `--resume 0.5 --final`, 900 s x sqrt(fp/40); interleaved per board)
| Experiment | Boards | Arms |
|---|---|---|
| `pair-swap-ab` | `swap.boards.txt`: the 27 merit boards with a stage-1 placer-term gain over 10% (arvsom, nekoink, usbarmory among them) | C control, SW `pair_swap=1` |
| `margin-ab` | `margin.boards.txt`: 60 merit boards (usable_route_test, sha256 order, disjoint from the pair-swap boards) | C control (`place_margin=0`), M2 `place_margin=0.2`, MA `place_margin=-1` (the auto margin: `Problem.auto_margin`, about 1 mm on an empty board, 0 above 70% fill) |

## Metrics (paired, attempt 0)
Usual: `cp1`, `cpk`, completion, open connections, `legal`, DRC per type, CPU. Own: pair swap report (`pair_swap`: tries, swaps, placer term before/after, HPWL before/after);
for margin: neighbour-gap p10/p50 and share of gaps under 0.3 mm/0.5 mm in the output (stage-1 `extract.features` on the output board) against the human board's.
Physics: decap/critical Σu on valued modules only, above the noise floor (J21, median ratio at n boards; pair-swap boards ≥ ~30 needed for a 1.08 floor).

Noise: A/A staged twins move total opens by about 3% (`aa-joint`, 213 boards), cp1 by about 0.5 pp. With n of 27 / 60 boards, open differences under about 15% and cp1 differences under 12 / 8 pp are not visible.
Pair swaps: extended to all 138 boards with term gain if routed physics or opens at 27 boards are positive but not significant; to a cost of about 100 CPU-h.

## Decision rule (pre-registered)
- Pair swaps ship (default `pair_swap=1`) if SW lowers the placer term as measured (median ratio at or below 0.9, boards with gain over 10%) with routed opens not worse by more than 5% and valued routed physics not worse beyond its noise floor. Otherwise off.
- Margin: `place_margin` default stays 0 unless M2 or MA raise the p50 gap toward the human by at least 0.1 mm with clean rate and opens not worse by the A/A noise (3 pp / 3%); on a tie on routing, gaps closer to human win (tie-break, J58). If routing is hurt, it stays 0 and we report what margin costs.
