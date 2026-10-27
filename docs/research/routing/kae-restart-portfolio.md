# kae restart portfolio: item order, not time, closes boards

**Status:** worked.
**First published:** 2026-10-24, commit [17f2185](https://github.com/magnetic-trowel/kicad-auto-everything/commit/17f218519310a0cb5330365065241d0b7a70c8bf) on branch `claude/vigilant-mayer-i91rrr` (stop-reason parsing [0865c48](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0865c488a3e90241fb1f2268c56edcf953bda657)).

Freerouting is deterministic in DSN item order, and its failures on our boards are not clock-bound: at 10× budgets the same attempts fail and every stop is COMPLETED or STAGNATION. So instead of one long attempt, `kae.route.portfolio` runs waves of differently seeded attempts in parallel with a doubling wave budget and keeps the first clean board. On splits A+B it is clean on 99 of 99 attempts (single attempt 91/99) with a worst wall time of 224 s instead of 1,626 s; on the six hard split-C boards 12/12.

There is no merit method of its own: the merit script notes "kae portfolio is left out: it is kae bridge in this same wrapper", because main's restart wrapper (`tools/kaeres/restart.py`) plays the portfolio's role for every merit method. Results on the 500-board comparison (kae methods under that wrapper, merit-500r3 / merit-500r3k): pending.

## Idea and how it works

**Finding first (the experiment behind it).** `freerouting._autorouter_stop` and `_optimizer_stop` parse the fork's log for its StopReason (COMPLETED, STAGNATION/NO_IMPROVEMENT, TIMED_OUT, MAX_PASSES), and the repair loop records why it stopped. If failures were clock-bound, 10× budgets would close them; they did not (see results). Routing time per board is instead heavy-tailed: median ~10 s, a few attempts at ~1,500 s stuck on connections that a different item order would not meet.

**Portfolio** (`portfolio.run`):

- Waves of `parallel` separate `python -m <router> route` processes, each with its own seed. The seed is the DSN item-order permutation (`translate.permute` in the [bridge](kae-freerouting-bridge.md)) plus the fork's `item_order_seed`.
- The wave budget starts at `first_s` and multiplies by `growth` (default 2) each wave, so a board that genuinely needs a long attempt still gets one: 60, 120, 240 s, ...
- The first clean attempt (0 errors, 0 unconnected, read from the attempt's JSON report `repair.final`, else `drc`) stops the rest. Otherwise the best (errors, unconnected) is kept when time runs out.
- Attempts get `GRACE_S` = 30 s to write their board and a `MARGIN_S` = 15 s safety margin; the run stops early if all attempts of a wave fail at once.
- `--router M[:ARGS]` may be repeated; attempts cycle through the listed routers (the [mixed portfolio](kae-routing-dead-ends.md), not finished).

## What we tried

A+B (33 boards), k = 3, 1800 s per attempt, fork heap 2 GB: single `kae.route.cli` attempt (last mile on) vs `--parallel 4 --first-s 60`. Six split-C boards with switching cells (C6), k = 2, 3600 s, heap 6 GB, `--first-s 300`. The full benchmark's A+B portion at [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7). The budget experiment: crit-v6, `tools/research/routing/run_crit_v4.sh` with T_AB = 6000 s, T_C = 9000 s, k = 3, against the 600/900 s runs.

## Results

| Run | Arm | cp1 | cpk | Clean attempts | Wall s per attempt (median / p90 / max) | Source |
|---|---|---|---|---|---|---|
| A+B, 0465818 | single | 0.909 | 1.000 | 91/99 | 10 / 154 / 1,626 | [portfolio-ab-0465818](../../../bench/results/2026-10-24-portfolio-ab-0465818.md), [0465818](https://github.com/magnetic-trowel/kicad-auto-everything/commit/04658186e01f08a079acf025a41b7fb844f1f150) |
| A+B, 0465818 | portfolio P=4 | **1.000** | **1.000** | **99/99** | 12 / 65 / 224 | same |
| C6, 0465818 | single | — | — | 10/12 | 157 / — / 3,558 | same |
| C6, 0465818 | portfolio P=4 | — | — | **12/12** | 125 / — / 228 | same |
| A+B, 03096d9 | stock FR 2.5.0 / single / portfolio | 0.455 / 0.879 / 1.000 | 0.455 / 1.000 / 1.000 | — | — | [full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md) |
| A+B, 10× budget (crit-v6) | bridge | 0.727 | 0.818 | 70/99 (same as at 1×) | no attempt > 90 % of 6,000 s | [crit-v6-10x-1ef5bf1](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md), [1ef5bf1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1ef5bf10ffb86704afc8c1dd40836b2ac33ad28c) |

Portfolio details (A+B): attempts launched per board median 4, max 10; the winning wave was 60 s on 66 attempts, 120 s on 23 and 240 s on 10; paw3395 won with its 9th and 10th seeds. On C6 every board won in the first wave; canhw-processor, whose single first route timed out, routed clean in 190 s and 128 s with other seeds. In the 10× run the bridge's stops were COMPLETED 91 / STAGNATION 8 (critical arms 63 / 36); on split C only canhw's first route ran long (7,000-8,500 s, still 2-9 open). The k = 10 stock baseline also has cp1 = cpk on every split ([qualified-k10-baseline](../../../bench/results/2026-10-22-qualified-k10-baseline.md)). Caveats: the 10× run is a single run and predates the last mile; CPU cost (up to `parallel` cores and JVMs per board) was not measured because the harness sandbox hides child processes; the full split-C portfolio arm was still running at the branch's handoff and has no results file.

## Verdict

Worked. Diversity of item order is what closes the last connections on these boards, so a restart portfolio with a doubling budget beats one long attempt both in completion and in tail latency. It refuted the "per-split budgets" idea (R1 of [strategy-candidates.md](../../topics/routing/strategy-candidates.md)); see [dead ends](kae-routing-dead-ends.md). Not built: a learned portfolio selector (Thompson sampling or racing).

## Code

`kae/src/kae/route/portfolio.py` (`run`, `_rank`). Entry point: `python -m kae.route.portfolio route IN OUT --parallel P --first-s F [--growth G] [--router M[:ARGS]]…`. Stop parsing in `kae/src/kae/route/freerouting.py`. Tests: `kae/tests/test_route_portfolio.py`. Topic doc: [last-mile-and-restarts.md](../../topics/routing/last-mile-and-restarts.md).

## Related

[Bridge](kae-freerouting-bridge.md), [last mile](kae-last-mile.md), [dead ends](kae-routing-dead-ends.md) (longer budgets, mixed portfolio), [joint loop](../joint/kae-joint-loop.md) (portfolio finish with `--route-parallel`).
