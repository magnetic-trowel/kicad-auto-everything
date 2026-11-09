# kae restart portfolio: item order, not time, closes boards

Scope: defensive publication of the seeded restart portfolio with doubling wave budgets. Not here: operating rules and mixed-router caveat -> [last mile and restarts](../../topics/routing/last-mile-and-restarts.md#soft-tier-and-mixed-portfolio).
Keys: restart portfolio, portfolio.run, _rank, waves, parallel, first_s, growth, GRACE_S, MARGIN_S, item_order_seed, translate.permute, StopReason, _autorouter_stop, _optimizer_stop, heavy-tailed routing time, --router, restart.py

**Status:** worked.
**First published:** 2026-10-24, commit [17f2185](https://github.com/magnetic-trowel/kicad-auto-everything/commit/17f218519310a0cb5330365065241d0b7a70c8bf) on branch `claude/vigilant-mayer-i91rrr` (stop-reason parsing [0865c48](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0865c488a3e90241fb1f2268c56edcf953bda657)).
**Merit method:** none of its own: the merit script notes "kae portfolio is left out: it is kae bridge in this same wrapper", because main's restart wrapper (`tools/kaeres/restart.py`) plays the portfolio's role for every merit method. 500-board comparison (kae methods under that wrapper, merit-500r3 / merit-500r3k): pending.

Freerouting is deterministic in DSN item order, and its failures on our boards are not clock-bound (at 10× budgets the same attempts fail; every stop is COMPLETED or STAGNATION). So `kae.route.portfolio` runs waves of differently seeded attempts in parallel with a doubling wave budget and keeps the first clean board. A+B: clean on 99/99 attempts (single attempt 91/99), worst wall time 224 s instead of 1,626 s; C6: 12/12.

## Idea and how it works

- Finding first: `freerouting._autorouter_stop` and `_optimizer_stop` parse the fork's log for its StopReason (COMPLETED, STAGNATION/NO_IMPROVEMENT, TIMED_OUT, MAX_PASSES); the repair loop records why it stopped. Clock-bound failures would close at 10× budgets; they did not. Routing time per board is heavy-tailed: median ~10 s, a few attempts at ~1,500 s stuck on connections a different item order would not meet.
- Portfolio (`portfolio.run`):
  1. Waves of `parallel` separate `python -m <router> route` processes, each with its own seed = DSN item-order permutation (`translate.permute` in the [bridge](kae-freerouting-bridge.md)) plus the fork's `item_order_seed`.
  2. Wave budget starts at `first_s`, multiplied by `growth` (default 2) each wave: 60, 120, 240 s, …, so a board needing a long attempt still gets one.
  3. First clean attempt (0 errors, 0 unconnected, read from the attempt's JSON report `repair.final`, else `drc`) stops the rest; otherwise the best (errors, unconnected) is kept when time runs out. Since the 2026-11 bug audit, attempts rank by (unconnected, errors beyond the input's own), stop on the first board routed fully, and the kept board gets a final last mile with reserved time ([last mile and restarts](../../topics/routing/last-mile-and-restarts.md)); the results below predate that.
  4. Attempts get `GRACE_S` = 30 s to write their board and a `MARGIN_S` = 15 s safety margin; the run stops early if all attempts of a wave fail at once.
  5. `--router M[:ARGS]` may be repeated; attempts cycle through the listed routers ([mixed portfolio](kae-routing-dead-ends.md#5-mixed-router-portfolio-critical-router-first-bridge-second-not-finished), not finished).

## What we tried

A+B (33 boards), k = 3, 1800 s per attempt, fork heap 2 GB: single `kae.route.cli` attempt (last mile on) vs `--parallel 4 --first-s 60`. C6 (six split-C boards with switching cells), k = 2, 3600 s, heap 6 GB, `--first-s 300`. Full benchmark's A+B portion at [03096d9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/03096d9fa4203cb6983f39592438c88410c674b7). Budget experiment: crit-v6, `tools/research/routing/run_crit_v4.sh` with T_AB = 6000 s, T_C = 9000 s, k = 3, vs the 600/900 s runs.

## Results

| Run | Arm | cp1 | cpk | Clean attempts | Wall s per attempt (median / p90 / max) | Source |
|---|---|---|---|---|---|---|
| A+B, 0465818 | single | 0.909 | 1.000 | 91/99 | 10 / 154 / 1,626 | [portfolio-ab-0465818](../../../bench/results/2026-10-24-portfolio-ab-0465818.md), [0465818](https://github.com/magnetic-trowel/kicad-auto-everything/commit/04658186e01f08a079acf025a41b7fb844f1f150) |
| A+B, 0465818 | portfolio P=4 | **1.000** | **1.000** | **99/99** | 12 / 65 / 224 | same |
| C6, 0465818 | single | — | — | 10/12 | 157 / — / 3,558 | same |
| C6, 0465818 | portfolio P=4 | — | — | **12/12** | 125 / — / 228 | same |
| A+B, 03096d9 | stock FR 2.5.0 / single / portfolio | 0.455 / 0.879 / 1.000 | 0.455 / 1.000 / 1.000 | — | — | [full-benchmark-03096d9](../../../bench/results/2026-10-24-full-benchmark-03096d9.md) |
| A+B, 10× budget (crit-v6) | bridge | 0.727 | 0.818 | 70/99 (same as at 1×) | no attempt > 90% of 6,000 s | [crit-v6-10x-1ef5bf1](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md), [1ef5bf1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1ef5bf10ffb86704afc8c1dd40836b2ac33ad28c) |

- A+B portfolio: attempts launched per board median 4, max 10; winning wave 60 s on 66 attempts, 120 s on 23, 240 s on 10; paw3395 won with its 9th and 10th seeds.
- C6: every board won in the first wave; canhw-processor, whose single first route timed out, routed clean in 190 s and 128 s with other seeds.
- 10× run: bridge stops COMPLETED 91 / STAGNATION 8 (critical arms 63 / 36); on split C only canhw's first route ran long (7,000–8,500 s, still 2–9 open). The k = 10 stock baseline also has cp1 = cpk on every split ([qualified-k10-baseline](../../../bench/results/2026-10-22-qualified-k10-baseline.md)).
- Caveats: the 10× run is a single run predating the last mile; CPU cost (up to `parallel` cores and JVMs per board) not measured (harness sandbox hides child processes); the full split-C portfolio arm was still running at the branch's handoff and has no results file.

## Verdict

Worked. Item-order diversity closes the last connections on these boards, so a restart portfolio with a doubling budget beats one long attempt in completion and tail latency. Refuted R1 "per-split budgets" of [strategy candidates](../../topics/routing/strategy-candidates.md) → [dead ends](kae-routing-dead-ends.md#1-longer-budgets-did-not-work). Not built: a learned portfolio selector (Thompson sampling or racing).

## Code

`kae/src/kae/route/portfolio.py` (`run`, `_rank`). Entry point: `python -m kae.route.portfolio route IN OUT --parallel P --first-s F [--growth G] [--router M[:ARGS]]…`. Stop parsing in `kae/src/kae/route/freerouting.py`. Tests: `kae/tests/test_route_portfolio.py`.

## Related

[Bridge](kae-freerouting-bridge.md), [last mile](kae-last-mile.md), [dead ends](kae-routing-dead-ends.md), [joint loop](../joint/kae-joint-loop.md) (portfolio finish with `--route-parallel`).
