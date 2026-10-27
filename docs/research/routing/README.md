# Research: routing

Routing paths we tried, with how they work, the numbers and the verdict. The pages here cover the physics-first `kae` line (package `kae.route`): Freerouting is used as an inner engine behind a constraint-complete translation, KiCad's DRC on the re-opened board is the only judge, and our own exact grid router does the local work. Benchmark terms: cp1 = share of boards clean on attempt 1, cpk = clean on any of k attempts; "A+B" = the 33 boards of splits A and B, "C6" = six hard split-C boards with switching cells. Results from different benchmark eras (task specs, engine versions) are not comparable.

| Path | Status | One-line result | Page | Code |
|---|---|---|---|---|
| Constraint-complete KiCad → Freerouting bridge (rule port, DSN translation, no narrowing, hardened runner) | worked | Split C cp1 0.051 → 0.532, cpk 0.633, 0 errors besides 69 starved_thermal; merit method "kae bridge", 500-board results pending | [kae-freerouting-bridge](kae-freerouting-bridge.md) | `kae/src/kae/route/{bridge,cli,rules,constraints,translate,freerouting}.py` |
| DRC-driven repair rounds | worked (enabler) | Every bridge result relies on it; no isolated ablation | [kae-repair-loop](kae-repair-loop.md) | `kae/src/kae/route/repair.py` |
| Last mile: exact grid joins with negotiated rip-up | worked | A+B cp1 0.727 → 0.909, cpk 0.818 → 0.970, no physics cost | [kae-last-mile](kae-last-mile.md) | `kae/src/kae/route/lastmile.py` |
| Soft critical tier in the last mile | partial (thin) | Only arm to route libresolar-bms-c1 clean; C6 6/12 vs 8/12; merit method "kae critical soft", results pending | [kae-last-mile](kae-last-mile.md#soft-critical-tier---last-mile-soft) | `lastmile._SoftRouter`, `critical.soft_critical` |
| Physics-first critical copper (cells, decaps, rails, chains, guards, joint modules) | partial | Decap 0.74× the bridge, rail drop 0.74× human vs 2.21×; A+B cp1 0.667 vs 0.727; merit method "kae critical+bridge", results pending | [kae-critical-copper](kae-critical-copper.md) | `kae/src/kae/route/critical*.py` |
| Restart portfolio (seeded item orders, doubling waves) | worked | A+B 99/99 clean vs 91/99, worst 224 s vs 1,626 s; C6 12/12 | [kae-restart-portfolio](kae-restart-portfolio.md) | `kae/src/kae/route/portfolio.py` |
| Longer budgets (10×) | did not work | Same 70/99 clean attempts as at 1×; stops are COMPLETED/STAGNATION | [kae-routing-dead-ends](kae-routing-dead-ends.md#1-longer-budgets-did-not-work) | `tools/research/routing/run_crit_v4.sh` |
| Freerouting fork patch: last-mile rip-up on COMPLETED | did not work | Never triggered on the target boards | [kae-routing-dead-ends](kae-routing-dead-ends.md#2-freerouting-fork-patch-fixlast-mile-on-completed-did-not-work) | not in this repo (fork branch) |
| Escape corridors out of dense ICs | did not work | canhw unconnected 19-33 vs 13-29 (one board) | [kae-routing-dead-ends](kae-routing-dead-ends.md#3-escape-corridors-out-of-dense-ics-did-not-work) | `critical.Session.escape_corridors` |
| Routed-physics recheck and re-tweak rip-up loop | did not work (recheck kept) | A+B 5 flagged, 0 kept; C6 2 of 4 kept | [kae-routing-dead-ends](kae-routing-dead-ends.md#4-routed-physics-recheck-and-re-tweak-loop-re-tweak-did-not-work-recheck-kept-as-a-measurement) | `kae/src/kae/route/critical_recheck.py` |
| Mixed-router portfolio (critical first, bridge second) | not finished | C6 12/12 but the bridge won all; corrected full run has no result | [kae-routing-dead-ends](kae-routing-dead-ends.md#5-mixed-router-portfolio-critical-router-first-bridge-second-not-finished) | `portfolio.py --router` |
| Not built from the 2026-10-21 plan: fastroute engine, PNS via PCBWorld, own negotiated-congestion router, learned selector | untested idea | — | [kae-freerouting-bridge](kae-freerouting-bridge.md#verdict) | — |

Evidence: the dated write-ups in [bench/results/](../../../bench/results/) and the topic docs [freerouting-constraint-bridge](../../topics/routing/freerouting-constraint-bridge.md), [last-mile-and-restarts](../../topics/routing/last-mile-and-restarts.md) and [critical-net-routing](../../topics/routing/critical-net-routing.md).

Related areas: [placement](../placement/README.md), [joint place and route](../joint/README.md), [physics](../physics/README.md).
