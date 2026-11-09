<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# BGA window repair: negotiated re-routes of small windows in a ball field

Scope: defensive publication of the monotone BGA window repair (`kae.route.region`) and its four measurements, ending in a negative verdict. Not here: the other closing methods -> [closing open connections](kae-closing-open-connections.md); the ball-grid placer and escape changes it shipped with -> [escape bands § bga-next-ab](../placement/escape-keepouts.md#the-ball-grid-router-changes-bga-next-ab).
Keys: BGA window repair, kae.route.region, close-bga-region, route-bga-next, region_reserve, region_reserve_frac, region_windows, bga-next-ab, region-reserve-ab, region-complete-ab, dense_refs, negotiated congestion, ball field

**Status:** did not work. One early run looked like −20 % open connections; three later A/Bs with both
arms side by side found no gain, and given every chance (6× the budget, no caps on windows or rounds)
it left 26 % more open connections than the same router without it. Not merged; the code stays on
branch `route-bga-next`.
**First published:** 2026-11-08. Code: `close-bga-region` (30eef20), merged into `route-bga-next` with a
time reserve and settings ([edabfb6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/edabfb6dc09814214397d13b0fc8eb6ec491c500));
recipe `region-complete-ab.sh` ([a6e0897](https://github.com/magnetic-trowel/kicad-auto-everything/commit/a6e0897208dc6a47638640c4a30c83367c1f5e7c)).

## Mechanism

After the bridge's DRC repair rounds, per open connection inside a dense part's ball field
(`escape.dense_refs`: ball grids and fine-pitch rings): take a window around it, rip at most 12 blocking
nets, re-route them and the open connection together with negotiated congestion (flexibility-weighted
prices; planes and signals both movable), and keep the batch only if KiCad's DRC after a zone refill
improves on the board's count ("monotone"). Windows are visited per package, worst first, until the
budget or the windows run out.

`region_reserve` (auto) sets time aside for it after round 0, in proportion to the share of unconnected
items in dense parts (≥ 10 % or nothing; capped at `region_reserve_frac` of what is left, default 0.5);
`region_windows` caps the windows tried (default 3).

## Results

| experiment | setup | open connections | verdict |
|---|---|---|---|
| close-bga-region (2026-10) | 6 boards × 3 seeds, restart wrapper | 916 → 729 (−20 %); gecko5 216 → 84, kata0510 8 → 11 | one run; whether its arms ran side by side was not recorded |
| bga-next-ab | kae staged, 10 ball-grid boards × 3 seeds, side by side | 5,270 → 5,526 (+4.9 %), boards 2 better / 4 worse | no gain; on big boards the repair rarely ran: the repair rounds used the time up to the last mile's reserve |
| region-reserve smoke | nekoink, one seed per arm, its own time reserve | reserve 0: 102; auto: 120; max: 173; single attempt 0 / max: 96 / 113 | the reserve took time from stages that pay more |
| region-complete-ab | bridge on the human placement, 10 ball-grid boards × 2 seeds, one attempt with 6× the usual budget, `rounds=auto`, `region_windows=50`, reserve up to 80 % | 2,422 → 3,054 (+26 %); runs 2 fewer / 9 more (p = 0.07); boards 1 better / 6 worse / 3 same | did not work |

In region-complete-ab the repair did run: sdi-mipi tried 98–131 windows and kept 52–83, kocer 39–56
(kept 32–48), polarfire 31–57 (kept 5), with about 4,400 s reserved per run. The boards still ended worse
(sdi-mipi 86–89 open without, 118–133 with). Two reasons from the logs:

- **Windows are judged one at a time.** A batch is kept when the board's count improves right then, but
  the nets it moved crowd connections routed later; single steps went 32 → 49 open and had to be undone
  (nekoink U100).
- **Its time comes from stronger stages.** The reserve is taken from the DRC repair rounds: arvsom got 3
  rounds instead of 9.

Even at 6× the budget, 7 of the 10 big-board runs with the repair hit the job timeout mid-repair (against
3 without), so "every stage runs to convergence" was not reached in practical time.

The restart wrapper's runs on these boards also showed the router is the limit on deep ball-grid rings
([board studies, finding 3](../joint/board-studies-2611.md#findings)): what is left points at the router
itself (outer-layer cost, smallest via for escapes) rather than at repairing its output.

## Not done

- Judging a batch of windows together, or by a global measure (total flexibility left) rather than the
  open count at that moment.
- MAPF-LNS2-style window repair with floating terminals, from the
  [ranked BGA ideas](../../topics/routing/bga-routing-ranked-ideas.md).
