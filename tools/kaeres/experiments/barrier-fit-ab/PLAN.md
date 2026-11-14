<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# barrier-fit-ab: region splits that probe their fit first (pre-registered plan)

Written 2026-11-14, before any run of these arms on these boards. Follow-up to `barrier-split-ab2`
([its plan](../barrier-ab/PLAN.md), [research page](../../../../docs/research/placement/barriers-voids-2611.md)).
Code: the commit `setup.sh` records (branch `place-barrier-moves`).

## Why
`barrier-split-ab2` (100 boards, `barrier_split=1`) cut open connections 10.4 % (54 boards lower, 16 higher,
p < 0.0001) but `legal` fell 42 -> 36 boards, past its 3 pp limit. Found after the fact: on the 59 boards where
the split moved no part between regions opens fell 37 %; the 14 boards where the capacity rule moved parts lost legality.

Diagnosis on those boards (placement only, prepared task inputs, the ab2 code; scripts in the research page):
- The 7 boards whose split arm kept an illegal placement (`--check-placement` rank) are all among the 14 moved boards;
  no board without moves had an illegal placement in the split arm.
- In every moved board with an illegal region, the illegal region is the one parts were moved *out of*, and the
  parts left illegal are not the moved ones. The capacity rule counts courtyard area: a region whose area is
  mostly taken by fixed parts (a eurorack panel's jacks and pots; len42 audiout: 10 fixed parts, 81 % of the
  front used) passes the area test after the moves, but the placer's legalizer finds no spot for a DIP there.
  The parts moved were those the human layout has in the destination (len42 audiout: 41 of 41).
- So the fault is the fit test, not the moving: area is not room.

## Mechanism (`barrier_split=2`; `1` unchanged, `0` off and the default)
`kae.place.barriers.fit_split`: before the regions are placed, each region gets the placer's own seed and
legalizer (no annealing). A movable part a region cannot legalize moves to the region it is most tied to by
nets among those it has not failed in; the changed regions are probed again, up to 3 rounds, within 40 % of
the placement budget. A split that still does not fit is not applied: the board is placed whole, as the
control (`barrier_split.skipped = "unfit"`). The regions then get the time the probes left (at least half).
On len42 audiout: 4 parts moved to fit in 2 rounds, signal nets across regions 33 -> 22, placement legal.

## Boards
`select_boards.py` on the barrier scan (`kae.place.barriers.regions` over 3,310 usable boards): true splits
(outline less all-copper track keepouts in 2 or more regions of at least 2 % of the board), `usable_route_test`,
at most 1,000 pads, courtyards at most 90 % of the outline on a side; **no board of barrier-split-ab2 and no
board of their repo families**; one board per `repo_family`, in sha256 order. 211 boards (35 cut by an
all-copper keepout, the rest by separate outlines: panels, eurorack PCB pairs). 127 of the 138 that E104's
outline scan covers are multi-component there too; the others are split by keepouts, which E104 does not read.
Stage 1 is the first 120 (`stage1.boards.txt`); the rest form the extension. Boards a task cannot be prepared
for drop out of both arms.

## Arms (interleaved per board; one commit; only `--set barrier_split=2` differs)
Staged joint-fixed chassis as ab2 (`kae.joint.cli --max-iters 0 --no-modules` under `restart.py --parallel 4
--first-s 300 --scale-first --slack 1.15 --resume 0.5 --final lastmile --check-placement`), counted-work
budgets (`KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1`, nominal 900 s x sqrt(fp/40), wall ceiling 4x),
Freerouting fork d137fd1 named explicitly (`KAE_BRIDGE_FREEROUTING` and `KAE_FREEROUTING`) in the wrapper and
every inner command. C: control. F: `barrier_split=2`. k = 1 (attempt 0).

## Metrics (paired, attempt 0)
Primary: total open connections (`unconnected`). Guards: `legal` boards, DRC errors (total and per type,
`errors_by_type`). Also: `cp1` (= `cpk`, k = 1), completion, per-board CPU, and the mechanism (offline, from the
task input and the kept seed: split applied / skipped over capacity / skipped unfit, parts moved to fit,
signal nets across regions; and in F's output no movable part outside every region). Physics not reported:
the mechanism does not change module structure. Results also by cut type (keepout wall vs separate outlines).

## Noise and size
- A/A (`aa-joint` twins, 213 boards, same seed): total opens 2.8 %, total DRC errors 5.7 %, `legal` discordant
  on 3 boards (1.4 pp) with totals 103 vs 106. The `legal` guard of 3 pp is above that, so it stays 3 pp; the
  DRC guard is set above the A/A spread at 6 %.
- Expected effect: ab2's -10.4 % overall, -37 % where no part moved. F should keep the no-move gain and turn the
  moved boards from a loss to neutral or a gain. A 10 % effect decided ab2 at 100 boards (ratio CI 0.78-0.99).
- The binding guard is `legal`, a board count, so boards buy more than seeds: k = 1 (the restart wrapper already
  runs about 10 seeds per board inside the budget; ab2's per-board paired signs decided at k = 1). 3 pp is 4
  boards at 120 and 6 at 211.
- Cost, from ab2 (wall-clock budgets then): about 2.5 CPU-h per board for both arms, so about 300 CPU-h for stage 1
  and 230 more for the extension.

## Decision rule (pre-registered; two looks)
Pass needs all of:
1. **Opens:** F's total opens at least 5 % below C's, paired sign test over boards p < alpha, and the bootstrap
   95 % CI of the ratio of totals below 1.
2. **Legal:** F's `legal` count not below C's by more than 3 pp of the boards.
3. **DRC:** F's total DRC errors at most 1.06x C's.
4. **cp1:** not lower by more than 3 pp.

Look 1 (stage 1, 120 boards): adopt if 1-4 pass with alpha = 0.01; reject if `legal` falls more than 3 pp with
McNemar p < 0.05, or the ratio CI's lower end is above 0.95 (no 5 % gain is possible); otherwise run the extension
(`barrier-fit2-ab-ext`, the other 91 boards) and decide on all 211 with alpha = 0.04. At look 2 a failed guard
rejects.
If adopted, `barrier_split=2` becomes the default in `kae.route.constraints.DEFAULTS` in its own PR; if not, it
stays off with its numbers in the research page.

## Smoke (before any full run)
`barrier-fit2-smoke`: len42-synth-audiout (moved parts, fit repair), niektb-sluisbrinkie andes-10hp (three regions,
no moves), gregification-beems-mini-orion-tem (HV keepout wall). All three are ab2 boards, not in this test.
One board per arm profiled (py-spy on the python process, JFR on Freerouting), results in SMOKE.md; job
`--cpus`/`--mem` from the smoke's peaks.

## Amendment before any run (2026-11-14)
Placement-only checks of the first `fit_split` (e810834) on the ab2 boards (not this test's boards) found two faults,
fixed before anything was submitted: a region that cannot hold its parts is slow to probe, so on a 100 s placement the
first round alone used the probes' share and no repair ran (the split was skipped on all four len42/fihdi boards it was
meant to fix); and probes of a few seconds flagged parts that only lacked time, so fit moved parts that needed no move
(niektb: 8 parts moved, 0 -> 13 nets across regions). Now one repair round always runs, a round's regions share half
of what is left, and a probe names the parts its greedy legalizer found no spot for when there are any (all illegal
parts otherwise). The methods and experiments registered at e810834 (`barrier-fit-smoke`, `barrier-fit-ab`) were never
submitted; the test runs as `barrier-fit2-smoke`, `barrier-fit2-ab` (and `barrier-fit2-ab-ext`) at the commit
`setup.sh` was run with.
