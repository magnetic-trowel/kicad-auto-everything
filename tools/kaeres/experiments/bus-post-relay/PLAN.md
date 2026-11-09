<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# bus-post-relay: re-lay pairs after routing with priced rip-up (pre-registered plan, E1 / H7 / X7)

Written 2026-11-09, before any run. Branch `bus-post-relay`. Evidence: `bus/mechanisms.md` H7, X7; `diffpair-ab` (`post` re-laid 0.246 of pairs).

## Mechanism
`pair_route.post_pass` re-lays a routed board's pairs as pairs in place and keeps the board only if KiCad finds it no worse (opens and errors), after a last mile. It never crossed other nets' copper. With `rip` (`--set pairs_rip=true`), a pair that does not fit is searched again with other nets' unlocked tracks and vias within `rip_margin` (2 mm) of its pads' box taken out and priced per cell (`rip_cost` 20, `lastmile.RIP_COST`) in the spine search (`PairGrid` with `lastmile._SoftRouter`'s cost) and the fan-ins. Copper the new pair breaks a rule against is ripped (at most `max_rip` items a pair), the rest restored. The last mile then rejoins the ripped nets (nested repair, new copper fixed), and the same KiCad gate keeps the whole result only if not worse.

## Feasibility, measured before building (13 pilot boards, 93 pairs on the control boards at 400 s)
A spine through other nets' copper, priced as above: found for 86 of 93 pairs; it crosses the copper of a median 2 other nets (deciles 0, 1, 1, 1, 2, 2, 3, 4, 5; 92 % at most 5; max 9) and a median 3.5 items. A spine in free space only (no rip) also exists for 84 of 93, with a median detour of 1.00 (8 % longer than 1.2x), so the free-space post pass fails mostly after the spine: legs, via sites and fan-ins near the pads. Pair re-lay alone (no gate) on 6 boards: 16 of 63 pairs without rip, 32 of 63 with, ripping a median 8 items on 4 nets per pair.

## Boards and arms
Boards: `tools/kaeres/experiments/diffpair-ab/boards.txt` (120, real pairs, one per family). Arms interleaved, one commit, kaeq timed class, k = 1, seed 0, bare placement:
- control: no pairs
- post: `--pairs post` (as `diffpair-ab3`)
- post-rip10: `--pairs post --set pairs_rip=true --set pairs_max_rip=10`
- post-rip40: `--pairs post --set pairs_rip=true --set pairs_max_rip=40`

Budgets: 900 s (all, `bus-post-relay`) and 300 s (control, post, post-rip40, `bus-post-relay-300`).

## Outcomes and decision
`pair_report.py` and `diffpair-ab/analyze.py` (pairs: tier rule or interface, both legs routed in both arms, each at least 4 mm in the control), each arm against control and post-rip against post; `bus-wire-types/analyze.py` for opens, errors and passes, split by whether the control finished 2 Freerouting passes.
- Primary: **coupled share**, median paired change against control at least +0.30 (as `diffpair-ab3`); against post, post-rip must re-lay more pairs (share of pairs with coupled share >= 0.5 up by 0.1 or more).
- Guardrails: open connections and DRC errors total within +5 % (95 % bootstrap over boards); by construction the gate keeps a board only when it is no worse, so a violation means the gate is wrong.
- Read: pairs re-laid, items and nets ripped, the gate's kept share, CPU.

Pass: primary and guardrails at 900 s. The 300 s read says whether the reserve for the pass costs routing completion. If post-rip passes, the next step is bundles (ribbons n > 2) on `bus_kind.qspi`.

## Cost (as information)
About 0.3 CPU-h per board-arm at 900 s, 0.13 at 300 s: about 190 CPU-h.
