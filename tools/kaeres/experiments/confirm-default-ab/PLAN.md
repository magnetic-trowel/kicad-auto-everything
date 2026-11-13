<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Confirmation A/B of the routing default: plan, pre-registered criteria, cost

The question: does kae's new default, finish in the time left ([routing-stages](../../../../docs/topics/routing/routing-stages.md) §7.1: no finish reserve, taut honours its deadline), keep A's completion, which stage 2's arm C lost on large boards (C/A -0.5 %, [route-finish-ab results](../../../../bench/results/2026-11-11-route-finish-ab.md)), while keeping C's copper and physics gains? Registration: [`../confirm-default-ab.sh`](../confirm-default-ab.sh). Written before any run of these arms exists.

## Arms

All arms use route-finish-ab's restart portfolio (`restart.py --parallel 4 --first-s 60 --scale-first --slack 1.15 --resume 0.5 --final '<kae.route.cli lastmile>'`, 900 s × sqrt(footprints/40), at most 4 h). They pin Freerouting fork 2e1125a, take operating facts from `compiled-9867d0b`, run in the kaeq timed class at priority 5 at most, and use the code of the final SHA, `power-copper-tht` 4392518 (route-finish-default, the deterministic evaluator and the THT neck).

| Arm | Recipe |
|---|---|
| A | Legacy, as stage 2's A: `KAE_PAD_ENTRY=centre KAE_FR_PIN_ENTRIES=off`, no finish pass. Finish is now on by default in `kae.route.cli route`, so A's attempts pass `--no-finish` |
| N | The default kae recipe for this wrapper: nothing set except `--final` and `--finish 'kae.route.cli finish …'`, which routing-stages §7.1 says every kae recipe passes (restart.py is method-agnostic, so finish is explicit there). The attempts get `KAE_FINISH_KEPT=1` and defer to the portfolio's single finish. The difference from stage 2's C is the code, not the flags: no reserve, finish only in the time left |
| A2 | A again (an id-only parameter), on the 17 large open boards and the 16 slow-physics boards |

`kae.route.portfolio` (kae's own portfolio: first wave 120 s, no resume or slack) is the default for a user who calls kae directly. It is not an arm: comparing it with A would change the wrapper too.

## Boards (`*.boards.txt`; chosen from stage-2 data, never from these arms)

- `open.boards.txt`: the 50 boards with open connections in stage 2's A or C.
- `physics.boards.txt`: 20 complete boards, all with copper-loss and rail-drop terms in the human, A and C evaluations.
  - 7 of them have radio terms (`emission.cable_E` or `pickup.peak`).
  - 13 are the largest by the human's copper-loss plus rail-drop contribution.
  - The 7 boards with unused declared layers are left out of everything.
- `slow-physics.boards.txt`: 16 further complete boards with copper and rail terms whose stage-2 evaluation took over an hour (up to 10 h). They are routed in every arm but left out of physics. All 16 were complete in stage 2's A and C, and most are small (12 to 194 footprints).
- `large-open.boards.txt`: the 17 open boards with at least 130 footprints (budget at least 1,620 s).
- `twin.boards.txt`: the large open boards plus the slow-physics boards (33). A2 runs here.
- `all.boards.txt`: the 86 boards A and N run on (open, physics and slow-physics).

## Context: the THT neck (not a gate)

The final code (`power-copper-tht` 4392518) necks power copper into THT lands, driven by the DC plan's currents, the loss budget and heat-path exceptions. Its own 12-board check: THT overhang -45 %, physics within the floor except zx2-backplane's rail drop (+1.1 %). These figures come from that branch's work and are given for context; the gates below judge this run alone.

## Pre-registered criteria (`analyze.py --section gates`)

**Primary: completion.** N against A on all 86 boards. Passes when the paired 95 % CI lower bound of N - A, resampled by repository, is above -0.005 (Q2's margin).

**Noise check.** On the boards A2 ran (large open and slow-physics), report N - A next to A2 - A: their means, the twin's 95 % CI, and how many boards are worse or better. If the primary fails and N - A's mean lies inside the twin's CI, the result is reported as "not distinguishable from run-to-run noise". It is not reported as a pass.

**Secondary: physics.** On the 20 complete boards, base evaluations only, with the deterministic evaluator from the same code (`KAE_EVAL_MAX_CELLS` default, 4,000,000).
- `loss.copper` and `drop.rail` each pass when the median N/A ratio is at most 1 and signal-better terms outnumber signal-worse.
- Noise floors are the re-measured median spreads ([physics-set-coverage](../../../../docs/topics/physics/physics-set-coverage.md) §4): `loss.copper` 0.6 %, `drop.rail` 0.4 %, `supply.peak` 0.5 % (`--floor`); `emission.cable_E` keeps 5 %.
- As a sensitivity check, the verdicts are repeated at the 90th-percentile spreads: 1.6 %, 2.2 %, 10 %.
- No offsets: the evaluator is a function of the copper, and the floors cover the grid.

**Overhang.** THT lands and SMD lands each: neither the per-board entry count nor the area of N rises above A beyond noise (the repository-resampled CI of the mean per-board difference must not lie wholly above 0). The THT gate is judged after the cap.

**Reported, not gated:**
- exposed acute notches per metre (gap < 80°, ≥ 50 µm) for A, N and human;
- cp1, `clean_strict` and DRC errors;
- validity;
- the boards where N's finish was skipped, failed or time-limited: `finish_part_skipped`, `finish_failed` and `taut_time_limited` hazards in the kept board's report, a skipped part in the summary, or no finish record.

## Process

1. **Smoke**, one board per arm (transistorfet z280, open in stage 2, budget 1,064 s):
   - the kaeres methods end to end (experiment `confirm-default-ab-smoke-<sha7>`);
   - a profiled run per arm (`smoke_prof.sh`: py-spy over every Python process, JFR on Freerouting), with time per stage from `stage_prof.py`;
   - base physics of human, A and N on that board.
2. **Right-size** `--cpus` and `--mem` from the smoke peaks.
3. **Full run** after the final SHA is registered and the cost is approved: routing first, then physics on `physics.boards.txt` for human, A and N, then the analysis with `--floor loss.copper=0.006 --floor drop.rail=0.004 --floor supply.peak=0.005`.

## Running order

```bash
SHA=<final sha> tools/kaeres/experiments/confirm-default-ab.sh          # confirm-default-ab, confirm-default-ab-twin
(cd tools/kaeres/experiments/route-finish-ab && SHA=<sha12> bash warm.sh) # through kaeq
python3 tools/kaeres/kaeres.py exp submit <exp> --dry-run               # then kaeq submit --jobs with prio 5, class timed
S=tools/kaeres/experiments/route-finish-ab
for arm in human <A id> <N id>; do $S/submit.py measure --arm $arm --sha <sha12> --out <OUT> \
  --boards tools/kaeres/experiments/confirm-default-ab/physics.boards.txt --submit; done
$S/analyze.py --exp confirm-default-ab --twin confirm-default-ab-twin --out <OUT> --floor loss.copper=0.006 \
  --floor drop.rail=0.004 --floor supply.peak=0.005
```

## Smoke (code 321762d, physics-determinism; transistorfet z280, budget 1,064 s, seed 0)

| arm | completion | unconnected | DRC errors | wall s | attempts' s | final s | finish | job peak / CPU |
|---|---|---|---|---|---|---|---|---|
| A | 0.956 | 14 | 16 | 1,016 | 3,355 | 133 | - | 4.8 GB, 3.4 cores (A and A2 in one job) |
| A2 | 0.962 | 12 | 21 | 990 | 3,400 | 105 | - | |
| N | 0.994 | 2 | 10 | 1,016 | 3,358 | 154 | skipped: 22 s left, 30 needed (`finish_part_skipped` in report.json) | 4.7 GB, 4.2 cores |

All three methods ran end to end in kaeres, with valid outputs. The operating facts were found, and the `RFAB_summary`/`RFAB_report` blocks were stored. The A/A pair on this one board differs by 2 unconnected and 5 errors. N's 2 open connections are a single seed, not evidence.

**Profile** (`smoke_prof.sh` outside the sandbox, same recipe; py-spy samples, all processes): restart.py waiting 58 %; route attempts 40 %, of which Freerouting is 25 % of all samples, the repair loop 7 to 8 %, the attempts' last mile 4 to 5 % and blocked 0.6 %; the final last mile 1.4 to 1.7 %; finish 0 (skipped in N). JFR recordings of Freerouting are in the profile folders (17 and 18). The finish deferral works: no attempt of N ran finish.

**Right-sizing** (stage 2's 426 routing jobs): peak / kaeres's `--mem` estimate median 0.51, 95th percentile 0.62, max 1.28. Jobs used 3.6 cores on average. Full-run jobs keep `--cpus 4` and request 0.75 × the kaeres estimate; the one in 20 that needs more is requeued once with its measured peak.

## Cost (stage-2 timings of the same boards)

| item | job-hours | CPU-hours | longest job |
|---|---|---|---|
| A, 86 boards | 25 | 90 | 2.4 h (J2032) |
| N, 86 boards | 25 | 90 | 2.4 h |
| A2, 33 boards | 13.5 | 49 | 2.4 h |
| physics, human + A + N, 20 boards | 6 | 30 to 60 | about 1 h |
| total | about 70 | about 260 | |

At 40 cores from the queue that is about 6 h of routing, then about 2 h of physics, plus the tails. Step cache: under 2 GB.
