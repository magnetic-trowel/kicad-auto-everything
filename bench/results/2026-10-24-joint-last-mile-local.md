# Joint loop with last mile (6 split-B boards) and `--route-parallel 2` (split C), local

Local, 2026-10-24, shared 4-core host, KiCad 10.0.7, kaebench `joint` kind, score v7, `-j 1`,
Freerouting heap 3 GB (no attempt was OOM-killed). Physics from
`tools/research/joint/joint_physics.py`, stops from `joint_stops.py`. Values are seed 0 / 1.
Follows [joint-loop-b6](2026-10-24-joint-loop-b6.md).

## Last mile in the loop: 6 split-B boards, 900 s (snapshot v15)

Joint: windows run `lastmile.close` on their nets after `route_open`; the finishing bridge runs
with `rounds=auto, last_mile=True`; the first route has no last mile (bridge default then off).
"staged, last mile" is the staged arm with the bridge's default since c9c49d6.

| arm | clean | unconnected | DRC errors | module value vs human | worst rail mΩ | Σu | time s |
|---|---|---|---|---|---|---|---|
| staged, no last mile (v12) | 3 / 4 | 3 / 3 | 0 / 0 | 1.18 / 1.39 | 108 / 87 | 4.23 / 4.46 | 160 / 112 |
| staged, last mile | 5 / 5 | 4 / 5 | 0 / 0 | 1.24 / 1.33 | 104 / 103 | 5.45 / 4.59 | 199 / 178 |
| joint, no last mile (v14) | 3 / 3 | 11 / 8 | 0 / 0 | 0.81 / 0.96 | 43 / 58 | 2.56 / 3.38 | 394 / 331 |
| joint, last mile (v15) | 4 / 5 | 9 / 6 | 0 / 0 | 0.75 / 0.88 | 47 / 68 | 2.10 / 3.61 | 342 / 349 |

kaebench cp1 / cpk: joint v15 0.667 / 0.833, staged with last mile 0.833 / 0.833, staged v12
0.500 / 0.667.

- The gap is pmw3610: joint 7 / 6 unconnected, staged with last mile 4 / 5 (at Σu 22.3 / 17.0
  against the loop's 5.5 / 14.5). Noisecard seed 0 keeps 2; every other joint attempt is clean.
- On pmw3610 the finishing last mile joined 5–7 nets but ripped 19–22 items (8–9 unconnected, not
  kept); window last miles joined 9–12 and failed 5–6, ending 1–2 worse than the incumbent.
- Stops (joint v15): loop clean 8, time 4; window Freerouting COMPLETED 25 of 29; finishing
  bridge STAGNATION 4, TIMED_OUT 2; 38 % of the budget used on average (up to 91 %).

## `--route-parallel 2` on the six split-C boards, 2,400 s, seed 0 (snapshot v17)

Finishing stage = `kae.route.portfolio` (critical_cli `--last-mile-soft`, then the bridge) on the
current placement; windows left with ≤ 8 open get 2 more seeded `route_open` runs; window router
budget doubling after a timeout. Run before the portfolio rank fix (5b590c0), with an equivalent
in-loop ranking.

| board | result | iteration 0 (s) | loop stop |
|---|---|---|---|
| doorman | clean | 378 | clean |
| oasis-pcb | clean | 1,312 | time (flagged modules) |
| aftonsparv | clean | 412 | time (flagged modules) |
| bldcm-power | 3 unconnected | 1,214 | time |
| canhw-processor | 18 unconnected | 1,434 | time |
| libresolar-bms-c1 | 44 unconnected, 2 clearance errors (placement) | 1,471 | time |

- At this budget the large boards are bound by iteration 0, so the check cannot show whether the
  loop still stops on time at 9,000 s.
- Window routers timed out 4 of 53 times; restarts improved 7 of 21 windows.
- The portfolio finish (P = 2, 400–500 s, from scratch) never beat the loop's board: libresolar 98
  against 44, canhw 49 against 18, bldcm equal completion with worse physics.
