<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Routability in the placer: pre-registered plan

Written 2026-11-09, before any run of these experiments. Ledger J70 (untangle), J6 (routing failures to the global
placer and across restarts), J46 (routing channels), and the crossing term in the annealer (new). Mechanism and
results: `docs/research/placement/placement-routability-2611.md`.

## Questions
1. Does the untangle pass lower open connections? (J70)
2. Does a crossing term in the annealer lower open connections, and does it matter beyond the pass? (new)
3. Does the routing-channel term do so on more than one board? (J46)
4. Does feeding an attempt's failed corridors to later attempts' global placement lower open connections, separately
   from the RUDY term it needs? (J6)

## Boards (`boards.txt`, from `select_boards.py`, deterministic)
Boards where the placement is what fails to route; the rule is in the script. 47 boards, 40 primary (merge3-ab: staged
arm left connections open, human layout none, bridge on the human placement fewer than staged; less davang and beems, which
E107 attributes to rule-area barriers; plus mystorm and ubertooth, E107 placement-caused), 7 secondary (tagged
`route_demand.hard/extreme` or `pad_density.very_dense/extreme` with opens at staged, human layout at most 3 open, at most
2000 pads). All `usable_route_test`, one per `repo_family`. Tags only add boards that already had real opens, so the
unverified `route_demand` heuristic selects nothing by itself. `results` are read on all 47 and on the primary 40.

## Arms and chassis
All arms at one commit, knobs set with `--set` (a change per arm), interleaved in each board's job, timed class.

**`placement-routability`** (questions 1-3): one placement, one route (`kae.joint.cli run --max-iters 0 --no-modules`,
staged, no restarts), so the placement's effect is not hidden by a restart portfolio choosing among seeds. Budget
900 s x sqrt(fp/40), seeds 0-2 (k=3).

| Arm | Flags |
|---|---|
| control | none (knobs off) |
| untangle | `--set place_untangle=1` |
| xing | `--set place_w_xing=2` |
| chan1 | `--set place_w_chan=1` |
| chan3 | `--set place_w_chan=3` |

**`place-history`** (question 4): the restart chassis, because history only exists across attempts: as the J1 staged arm
(restart wrapper `--parallel 4 --first-s 300 --scale-first --slack 1.15 --resume 0.5 --final lastmile --check-placement`,
inner `kae.joint.cli run --max-iters 0 --no-modules`), k=1.

| Arm | Flags |
|---|---|
| control | none |
| cong30 | `--set place_w_cong=30` (needed: history only pays through the RUDY term) |
| cong30 history | `--set place_w_cong=30 --set place_history=../phist` (attempts of the same run share `restarts/phist`) |

The first wave of 4 attempts has no history, so the effect has to show in later waves.

## Metrics
From `kaeres exp report` and per-attempt run folders. `cp1`, `cpk`, completion, open connections (total and paired), DRC errors
total and per type, legal placements, CPU, wirelength, vias. Ratsnest crossings of the placement (`stages.place.crossings`
in the joint report) to verify the knob moved what it aims at. Physics on `physics_inputs_ok` boards, only above the floor (J21). Reported
by stratum (primary / all, 2-layer / 4+ layers) and, for untangle, with servo-hat excluded too.

## Size, from measured noise
Paired per-board noise in log1p(opens), the same code under two names and seeds (placement-decide-staged control vs cong0,
40 of these boards, 80 pairs): SD 0.54 (per seed). The mean of 3 seeds has SD about 0.31 per board (seeds differ more than
arms), so 47 boards detect about a 13% reduction in opens at 80% power (two-sided 5%), and 40 boards about 14%. Noise of
total opens in A/A twins: 2.8%.

## Decision rule (each arm against control, paired by board over the 3 seeds, mean of log1p(opens))
Adopt the knob on by default only if: opens down at least 10% in total, and a two-sided sign-flip test on the per-board mean
differences gives p < 0.05 on the 47 boards, and DRC errors (total, and each error type) not up beyond 5%, and legal placements not
down, and cp1 not down. HPWL is free to rise. One pre-registered extension: if p is 0.05 to 0.2 with an effect of 10% or more,
seeds 3-5 are added once and the test is run once more on 6 seeds; else the verdict stands. J6: opens or completion better in
history than in cong30 with the same test on k=1 and the 47 boards, and cong30 reported against control separately.

## Cost
`placement-routability`: about 19 h wall per arm-seed on the 47 boards (single process), 5 arms x 3 seeds, about 370 CPU-h.
`place-history`: 3 arms at 4 parallel, about 225 CPU-h. Information, not a cap.

## Addendum, before the full submission (2026-11-09; no result of the 47 boards seen)
Smokes outside the 47: placement-only on metro-m7 and vspeed (2 seeds; the term cuts crossings about 3x on metro-m7, 5 mm no better than 2 mm, so
one weight, 2 mm); the kaeres job path on terjeio dummy (all arms, runs scored); two sequential joint runs on vspeed for the history. That last
smoke found the loop never wrote the history (kae.joint.cli passes the loop only its own keys); fixed before any run of the 47, so the history
arm is the code as fixed.
