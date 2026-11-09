<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# route-finish A/B: plan, pre-registered criteria, noise handling, cost

The A/B of [routing-stages](../../../../docs/topics/routing/routing-stages.md) §6, as built (§7), on the
physics set: the 213 merge3-ab boards with compiled intents (`intent-213/compiled-6329e71`). Registration:
[`../route-finish-ab.sh`](../route-finish-ab.sh). Nothing here is submitted without the user's approval of its size.

## 1. Arms

Every routed arm is merge3-ab's "kae bridge main final" wrapper: `restart.py --parallel 4 --first-s 60
--scale-first --slack 1.15 --resume 0.5 --final '<kae.route.cli lastmile>'`, budget 900 s × sqrt(footprints/40)
(at most 4 h), one attempt per board, Freerouting fork 2e1125a, KiCad 10.0.7, numba cache warmed for the commit
(`warm.sh`). All arms get the board's operating facts (`--set operating=<board>.operating.json`, copied under
`~/.cache/kaebench/rf-ab-operating-<content hash>` because the sandbox hides `/var/tmp`).

| Arm | What | How it is set |
|---|---|---|
| A0 | merge3-ab's stored `kae bridge main final (restarts)` 286c2335844d (e9889fd). Reference only, no routing | cited from merge3-ab (task spec 8, score 7); `fork.sh A0` re-scores its boards at this harness (A0r) |
| A | route-finish code, legacy options | env `KAE_PAD_ENTRY=centre KAE_FR_PIN_ENTRIES=off`; no `--finish`; tighten is a `kae.route.critical` option (`--opt tighten=1`), which the bridge never runs |
| B | A's kept board + finish only | `fork.sh B`: `kae.route.cli finish <task input> <A's board> <out> --time <finish_estimate> --set operating=...`, scored by kaebench in a sandboxed run of its own |
| C | route-finish defaults + finish in the final pass | defaults (`pad_entry=centreline`, rule D born-right grid copper); `restart.py --finish 'kae.route.cli finish @IN@ @BEST@ @OUT@ --time @TIME@ --input-drc @DRC@ --drc-s @DRC_S@ ...'` |
| D | C + rule D tails on each repair-round import | `--set import_tails=true` on the route attempts (`repair.import_tails`) |
| E | C + decap ground vias before routing | env `KAE_ESCAPE_GROUND_VIAS=1` (`lastmile.plane_escapes`; only boards with plane fills) |
| A2 (optional, stage 1) | A/A twin of A | same recipe, `--param replicate=2` separates the id (`TWIN=1`) |
| F (not planned) | critical router ± tighten, + finish | see §8 |

Why B is not a kaeres method: a fork must start from A's exact kept board. A kaeres `--command` method cannot read
another run's output (the sandbox hides the home directory and `/var/tmp`), and re-running A's portfolio with
`--finish` is not a fork: the finish's reserve shortens every attempt budget, so the attempts differ. The step
cache would replay identical attempts only while every budget matches. `fork.sh` reads A's stored
`output.kicad_pcb.gz`, prepares the task with the same harness, and runs finish as a sandboxed kaebench
`--command` arm (the stored board bound read-only), so B is scored by exactly the same scorer and checks.
B runs its own input DRC (C reuses the judge's), one DRC more per board; its `--time` is restart.py's
`finish_estimate` with A's mean judgement as the DRC time.

## 2. What each comparison isolates

| Pair | Isolates | Confounds |
|---|---|---|
| B − A | the finish stage alone (tails, taut, power copper, one journaled gate) on identical routing | B's finish runs outside the wall budget (C's runs inside) |
| C − B | born-right grid copper (rule D in the grid router and last mile) and running finish inside the portfolio | different routing (new attempts); run-to-run noise (see A2) |
| C − A | the redesign as it would ship (the default) | as above |
| D − C | rule D tails on repair-round imports | run-to-run noise |
| E − C | decap ground vias placed before routing instead of by power copper afterwards | only boards with plane fills change; run-to-run noise |
| A − A0r | the code's other changes since e9889fd (decide-2611 merge, NPTH keepouts, zero-length session fixes) plus operating facts in the plan | load differences between the runs |
| A0r − A0 | the scorer change (score 7 → 11) alone | none |
| A2 − A | run-to-run noise of the restart portfolio (wall-clock budgets, load) | none |

Section 6 of the design says C − B also isolates "early tightening". The bridge has no critical stage, so in these
arms nothing is tightened before finish; that question belongs to F.

## 3. Measures (`analyze.py`)

- **Routing** (`--section routing`): cp1; cpk = cp1 (one attempt per board, each the best of its portfolio, as
  in merge3-ab); `clean_strict`; completion; boards not closed; DRC errors per board and by type (sum); invalid
  outputs. Paired tests from `kaebench.stats`: exact McNemar (clean, clean_strict), sign-flip (completion,
  errors), 95 % bootstrap CI resampling repositories, flipped boards.
- **Geometry** (`--section geometry`; `measure.sh` runs `kae.route.taut stats` on each kept board): pad entries
  perpendicular / oblique (10–45°) / acute (> 45°), overhanging entries and their area, copper length by class,
  corners, acute corners, arcs; per-board ratios against A.
- **Physics** (`--section physics`): the fixed evaluator at the experiment's commit (includes 2644a0c,
  `heat.track` currents) via `tools/research/physics/eval_intent.sh`, as ab4 ran it (`KAE_EM_TOL=1e-4`, pitch
  0.25 mm), then `kae.intent status` under the board's intent. Per term against A and against the human layout,
  judged against the noise floor (§5). The human layout and A0 are evaluated again on this evaluator.
- **Hazards** (`--section hazards`): the kept board's hazards by code. The method command prints
  `restarts/report.json` and `restarts/summary.json` into `adapter.log` between `RFAB_<name>` and `RFAB_end`.
- **Seconds per stage** (`--section stages`): route attempts, judge, final pass (last mile), finish and its parts
  (tails, taut, power, gate, replan), wall and CPU.

## 4. Success criteria (pre-registered)

Primary pair per question; a criterion "holds" when its test agrees at α = 0.05 (Holm over the secondary
measures of one question). "Not worse" means the paired difference's 95 % CI lower bound lies above the margin.

**Q1. Does finish alone help without costing routing quality? (B vs A)**
1. DRC never worse: no board where B has more unconnected items than A, and at most 2 boards (magtag-type
   counting noise) with more DRC errors; cp1 and `clean_strict` not worse (McNemar p ≥ 0.05 or B better, B loses
   at most 1 clean board).
2. Geometry: oblique + acute entries fall (per-board sign test, median ratio < 0.9); overhanging entries fall.
3. Physics: `loss.copper` and `drop.rail` median ratio ≤ 1, with more boards "signal better" than "signal worse";
   no observable whose signal-worse boards exceed its signal-better boards by more than 2.
4. Time: finish's median seconds within its estimate; fewer than 5 % of boards with a part skipped for time.

**Q2. Should the redesign be the default? (C vs A) — the stage gate.** C passes when:
1. cp1 not worse (margin −0.02) and McNemar p ≥ 0.05 or C better;
2. completion not worse (margin −0.005); DRC errors per board not higher (sign-flip p ≥ 0.05 or lower);
3. criteria 2 and 3 of Q1 hold for C against A;
4. no new error type with more than 5 occurrences in C that A does not have.
Stage 2 runs only if C passes (or fails only on a criterion the user waives).

**Q3. What does born-right copper add beyond finish? (C vs B)** Descriptive, no gate: report cp1, completion,
entries and physics differences. Supports "born-right" when C's oblique + acute entries are below B's and cp1 /
completion are not worse.

**Q4. Import tails (D vs C).** Adopt `import_tails` as default only if cp1 and completion are not worse (as Q2.1–2)
and either oblique + acute entries fall a further 10 % (median ratio ≤ 0.9) or physics improves by Q1.3; else drop.

**Q5. Ground vias before routing (E vs C).** Judged on boards with plane fills only (E changes nothing elsewhere;
`analyze.py --section hazards` lists the boards whose kept E attempt reports `plane_escapes.ground_vias`). Adopt only if cp1 and completion
are not worse and `supply.peak` or `loss.loop_ac` has at least twice as many signal-better as signal-worse terms.

**Checks, not questions.** A2 − A gives the flip rate expected from noise: a pair whose flips (gained + lost) are
not above the A/A flips is reported as "within run-to-run noise" whatever its p-value. A − A0r larger than
±0.05 cp1 is investigated before any arm is attributed. A0r − A0 shows what the scorer change moved.

## 5. Noise

**DRC.** KiCad counts at its 199 error limit depend on item order, and some types read ±1 on the same board
(magtag mask bridges 24/25). The routing tables report counts; per-board error flips of 1 on boards above 150
errors are not called changes.

**Routing.** The portfolio is wall-clock driven, so two runs of one recipe differ. The A/A twin (optional, 13
CPU-h on stage 1) measures that; all comparisons are paired by board.

**Physics raster.** The evaluator's floor at 0.25 mm (one side, measured by shifting the raster window):
`loss.copper` ±0.5 %, `drop.rail` ±1–2 % (2 % used), `supply.peak` ±4 %, `emission.cable_E` ±5 %. Other
observables have no measured floor; they are reported raw and never called a signal alone. Per term:
- |ratio − 1| ≤ floor: noise; floor < |ratio − 1| ≤ 2 × floor: ambiguous; > 2 × floor: signal.
- **Offset-averaging.** For every light board (physics ≤ 10 min at 4 cpus: 191 of 213, 12 CPU-h per arm), the
  arms of the stage's primary pairs are also evaluated at three window offsets, (1/4, 1/4), (1/2, 1/2) and
  (3/4, 3/4) of the pitch (`measure.sh BOARD ARM DX DY`, `offset_eval.py`). With all four samples, a term's
  difference is a signal only when the means differ by more than 2 × the pooled offset SD; else "noise (offsets)".
- **Heavy boards** (20 boards, 94 % of the physics cost) are reported against the floor only. Their ambiguous terms
  are listed (`analyze.py --offset-list`) and get offsets only if one decides a criterion.

## 6. Cost (from stored timings; `cost.py`)

Sources: merge3-ab's A0 runs (`run.json`: runtime, prepare, scoring, judgements), the finish estimate that
restart.py reserves (15 s + 0.17 s per pad + two DRCs; the 12-board finish study measured 1,328 s against
1,300 s for the chained passes), and the queue's history of physics evaluations of the same boards (ab4 and the
phys-* owners; 4 cpus). Physics on heavy boards runs at 16 cpus and is assumed 2× faster than at 4.

Per arm, all 213 boards:

| item | job-hours | CPU-hours | longest job (h) |
|---|---|---|---|
| routing arm A | 29.9 | 120 | 1.1 |
| routing arm C, D or E (finish added where the portfolio stopped early) | 32.4 | 130 | 1.1 |
| fork B | 7.5 | 15 | 0.2 |
| re-score A0 | 2.2 | 4 | 0.2 |
| physics, 191 light boards | 2.9 | 12 | 0.2 |
| physics, 20 heavy boards | 13.0 | 207 | 2.9 |
| physics offsets (3 shifts, light boards) | 8.8 | 35 | 0.2 |

Two boards (kocer direct-sampling SDR, Seeed J2032) never finished an evaluation in any earlier run (6–8 h
timeouts, up to 65 GB); they are left out of physics. Step cache: about 3.4 GB per routing arm (50 GB cap).

Everything at once (A, C, D, E routed; B; A0r; physics for 7 arms incl. human and A0; offsets for A–E) is
about 2,200 CPU-hours, of which heavy-board physics is 1,450.

**Staged plan.**

| stage | contents | CPU-hours | wall at 50 / 25 cores |
|---|---|---|---|
| 1 | 40 boards (`route-finish-ab-s1.boards.txt`: 8 per pad-count quintile, physics ≤ 30 min, hash order); route A, C; fork B; physics human, A, B, C + offsets; (optional A2 twin: +13) | 70 | 1.8 h / 3.2 h |
| 2 (if C passes) | the other 173 boards for A, C, B; D, E on all 213; A0r; physics light boards for all 7 arms, heavy boards for human, A, C; offsets light for A–E | 1,340 | 30 h / 57 h |
| 2 option | heavy-board physics for B, D, E, A0 as well | +830 | +20 h / +36 h |

Wall times assume the share of the queue named; the queue ran 2,400–2,800 CPU-h/day over the last three days and,
when this was written, was memory-bound (MemAvailable less the running jobs' set-aside left no room for an
8 GB job; a prio-3 owner had 204 jobs queued). Heavy physics jobs need up to 60 GB each, so only one or two run at
once there: stage 2's heavy tail is closer to 2–3 days than to its CPU-hours over 50 cores. Stage 1 runs at
priority ≤ 5 in about 3 h once memory frees.

## 7. Running order

```bash
SHA=<pushed route-finish commit, with the scoring fix>; S=tools/kaeres/experiments/route-finish-ab
SHA=$SHA STAGE=s1 [TWIN=1] tools/kaeres/experiments/route-finish-ab.sh       # methods + experiment; installs the code
(cd $S && kaeq submit --owner rf-ab --prio 5 --cpus 2 --mem 8G --timeout 2h -- env SHA=$SHA bash warm.sh)
python3 tools/kaeres/kaeres.py exp submit route-finish-ab-s1                  # after warm.sh finished
A=<A's method id>; C=<C's>
$S/submit.py fork --arm B --a-id $A --sha $SHA --boards tools/kaeres/experiments/route-finish-ab-s1.boards.txt --submit
for arm in human $A $C B; do $S/submit.py measure --arm $arm --sha $SHA --boards ...-s1.boards.txt --submit; done
for arm in $A $C B; do $S/submit.py measure --arm $arm --offsets --sha $SHA --boards <light boards> --submit; done
$S/analyze.py --exp route-finish-ab-s1 > REPORT-s1.md
# stage 2: STAGE=full route-finish-ab.sh, exp submit route-finish-ab, fork B and A0 on all boards, measures as §6
```

After a scoring fix, stored boards are re-scored without re-routing: `submit.py fork --arm rescore:<method id>`
(or `rescore:B`, `rescore:A0`) copies each stored output into a kaebench run at the new SHA
(`OUT/rescore-<id>/`); `analyze.py` prefers those scores and says which source each arm's scores came from.

`exp submit` queues as owner `exp-<name>` at the default priority; use `kaeq prio` to raise it (≤ 5).

## 8. Known limits

- **Arms of a board do not share one job.** `exp submit` splits a board's methods into at least two jobs
  (`CHUNKS_MIN = 2`), so C and D may run at the same time and D replays C's Freerouting runs from the step cache
  only when C got there first. Results are unaffected (hits are charged their recorded time); savings are smaller
  than the kaeres README suggests.
- **A0 stays out of the experiments.** Route task spec 9 (here) against 8 (merge3-ab) would make kaeres re-run A0's
  old code; route inputs are identical between the two (spec 9 changed place-fixed only), so A0r is comparable.
- **F (critical router ± tighten).** No critical method at route-finish code is stored (the newest is 680c30e),
  so F would be two new routed arms (about 2 × 130 CPU-h routing plus physics), for a stage the 4-board study
  measured at 0–8 s with equal DRC on all boards and one board with small crystal and rail gains. Not worth it in
  this round; a 12-board subset is the cheap form if wanted.
- **Queue freezes move the budget.** kaeq freezes jobs under memory pressure (SIGSTOP); restart.py's budget is wall
  time, so a frozen routing job loses attempts. In the smoke, the A and C jobs were frozen 3 min each (A 270 s and
  C 292 s against A0's 36 s on the same board). Arms of one board then differ by load, not code: check
  `kaeq result` freeze counts per job, re-run boards whose job was frozen in one arm and not the other, or run the
  routing stage when the queue is not memory-bound.
- The warmed numba cache is small (204 KB against 9.7 MB for merge3-ab's, which also warmed kae.joint); kernels a
  board needs beyond the two warm boards compile inside the first attempt of every arm alike.
- B's finish is not charged to a wall budget; C's is. A B > C result on time-skipped parts is that, not a code effect.

## 9. Stage 1 rerun (`route-finish-ab-s1r`): pre-registered before any of its results exist

Arms A and C only, the same 40 boards (`route-finish-ab-s1.boards.txt`), code at c8188eb (score v12, task spec 10 with deterministic uuids, the corrected physics set, the finish notch fixes). Intents and operating facts: `intent-213/compiled-9867d0b`. Routing runs in the kaeq `timed` class at priority 5 at most, results in `OUT=/var/tmp/$USER/rf-ab-s1r`. Stage 2 is not part of this and waits for its own approval.

**Physics settings.** `KAE_EVAL_MAX_CELLS` stays at its default, **4,000,000** cells (`eval_intent.sh`; `offset_eval.py` passes the same value): a larger window has its pitch doubled until it fits, and the evaluator says so. kocer and J2032 are dropped from physics; neither is in these 40 boards. Human, A and C each get base physics and geometry on every board. Offsets (three shifted rasters) follow on boards whose slowest base evaluation among the three arms took at most 900 s (`submit.py --offset-max-s`); heavier boards (poledancer's offsets timed out at 4 h in stage 1) are judged against the floor alone.

**Routing tables** cover all 40 boards: with spec 10 the 10 boards left out of stage 1 for uuid churn are comparable. The check: their non-routing object uuids are the same in A's and C's outputs, which come from separately prepared tasks.

**Gates, C against A** (`analyze.py --section gates` computes each verdict):

| Criterion | Passes when |
|---|---|
| cp1 and `clean_strict` | paired 95 % CI lower bound above -0.02, and McNemar p ≥ 0.05 or C better |
| completion | CI lower bound above -0.005 |
| DRC errors per board | sign-flip p ≥ 0.05, or C lower |
| new error types | none in C with more than 5 occurrences and absent from A |
| validity (check) | no invalid output in either arm |
| oblique + acute entries | per-board median C/A below 0.9 and sign-flip p < 0.05 |
| `loss.copper`, `drop.rail` | median C/A at most 1, and more signal-better than signal-worse terms |
| every observable | signal-worse terms exceed signal-better by at most 2 |
| **overhang on SMD lands** | neither the per-board entry count nor the area (mm²) of C rises above A beyond noise: the repository-resampled 95 % CI of the mean per-board difference (C - A) must not lie wholly above 0 |
| **exposed acute notches** | notches with gap < 80° and depth ≥ 50 µm, pooled per metre of track: C not above human beyond noise, i.e. the repository-resampled 95 % CI of the pooled-rate difference (C - human) must not lie wholly above 0 |

The overhang gate replaces §4 Q1.2's "overhanging entries fall". SMD lands are two-terminal SMD plus other SMD (`tools/research/routing/overhang_diag.py`). Overhang totals and THT lands are reported, not gated: wide rails into THT pads are normal practice. Notches come from `tools/research/routing/notch_stats.py` ([why](../../../../bench/results/2026-11-08-finish-notches.md)) and are reported for A, C and human. "Not above beyond noise" is a one-sided claim about 40 boards: a pass means no clear rise, not proof of equality; the point estimates are reported alongside.

Physics terms are judged as in §5, on raw values in base units (dB converted to linear) when both arms have one, else on contributions.

## 10. The full experiment (`route-finish-ab`): pre-registered before any of its results exist

The user approved stage 2, so section 9's rerun became a part of this. One set of method ids at c8188eb: A, C, D and E routed on all 213 boards (timed class, priority 5 at most), and the A/A twin of A (`route-finish-ab-twin`) on the 40 stage-1 boards, in the same run. B is the fork of A. A0r re-scores merge3-ab's boards; only boards without uuid churn count (A0's outputs carry the random uuids of their own prepare). Results of `route-finish-ab-s1r` are the same runs; its 40 boards are a section of the full report. `OUT=/var/tmp/$USER/rf-ab-s2`.

Physics (`compiled-9867d0b`, section 9's settings) for human, A, B, C, D and E, base measures on 211 boards (kocer and J2032 are out), offsets on boards whose slowest base evaluation took at most 900 s.

**Questions and verdicts** (`analyze.py --section gates`, repeated for the 40-board subset):

- **Check.** A2 against A gives the flips expected from noise. A pair whose flips are no more than A2's is "within run-to-run noise" whatever its p-value.
- **Q1, B against A:** no board with more unconnected; at most 2 boards with more DRC errors; at most 1 clean board lost; cp1, `clean_strict`, completion not worse; oblique + acute entries fall; SMD overhang gate (section 9); `loss.copper` and `drop.rail`; no observable mostly worse; median finish seconds within its estimate and under 5 % of boards with a part skipped for time.
- **Q2, C against A (the stage's headline):** section 9's table.
- **Q3, C against B:** descriptive.
- **Q4, D against C:** adopt `import_tails` only if cp1, `clean_strict` and completion are not worse, and either entries fall a further 10 % or the physics rows of Q1 pass.
- **Q5, E against C:** on boards where E laid ground vias; cp1, `clean_strict` and completion not worse on all boards, and `supply.peak` or `loss.loop_ac` with signal-better at least twice signal-worse.

**Not in this run:** the task change "route only on layers the board uses" (task spec 11, branch `route-used-layers`) had not reached main at registration. These boards declare inner layers no copper uses, so a router here may use layers their design does not have (an estimate from the board files): adafruit mini-analog-thumbstick, adafruit pcf8523-rtc, asanza keithley-199, kocer direct-sampling-sdr, protocentral max30205, sparkfun edison micro-sd-block, sparkfun redbot-buzzer. Their results are not comparable with spec 11 runs.
