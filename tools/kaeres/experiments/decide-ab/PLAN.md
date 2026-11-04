# A/B plan for the decide-2611 arms (2026-11-04)

Code: every arm at **decide-2611 680c30e** (harness and kae). Registration script
`tools/kaeres/experiments/decide-ab.sh` on branch **decide-ab** (b524e86, pushed; worktree
`<worktree>`). `decide-ab.sh register N` registers tier N; the older
`legality-ab.sh`, `placement-decide-ab.sh` and `area-cost-ab.sh` now default to 680c30e
(`area-cost-ab.sh` is called by tier 2; the other two are superseded by decide-ab.sh).
Numba cache `numba-kae-decide-680c30e` is warmed once (joint, route, lastmile, critical, place).
Scorer: DRC evaluator 2b1e76886d6f (score v10+: `clean_strict` / `legal_strict` columns).

## Cost model (from past runs of the same recipes)

Budget per run = base × sqrt(max(1, footprints/40)), capped at 4 h. Measured ratios on 213 merit
boards (`~/kae-baselines/experiments/*/results.csv`):

| recipe | source | wall / budget | CPU / budget |
|---|---|---|---|
| staged kae (restarts, P=4) | merge3-ab `kae staged main screen final` | 0.51 | 1.97 |
| joint loop final (restarts) | baseline-2611b `kae joint loop final` | 0.54 | 2.27 |
| critical+bridge (restarts) | merit-500r3k `kae critical+bridge lm-base` | 0.53 | 1.41 |
| kae place (KAE_WORKERS=4) + FR probe | decide-legality smoke jobs (2765 CPU-s for 6 runs at 300 s) | ~1.05 | ~1.8 (incl. probe) |

+15 % for prepare, DRC scoring and in-job physics. Wall time below assumes ~70 effective cores
for these jobs (100-core cap, the host's other users and sessions, kaeq's 10-CPU reserve; at the
time of launch others used 30-50 threads and RAM was the tighter resource: 57-82 GB free).

## Experiments, ranked (value per cost; safety and legality first)

| tier | experiment | decision | boards | arms | k | runs | CPU-h | wall h @70 |
|---|---|---|---|---|---|---|---|---|
| 1 | legality-ab-place-down | P2/P3 | 113 downgraders | old / strict / level-c / escalate | 2 | 904 | 495 | 7.1 |
| 1 | legality-ab-place-relax | P3 | 52 >95 % full, courtyard-less parts | old / level-c / escalate | 2 | 312 | 140 | 2.0 |
| 1 | legality-ab-place-ctrl | P2/P3 control | 40 waive nothing | old / level-c | 2 | 160 | 67 | 1.0 |
| 1 | legality-ab-fixed-down | P2 (place-fixed) | 113 | old / strict / level-c | 2 | 678 | 371 | 5.3 |
| 1 | legality-ab-fixed-relax | P3 (place-fixed) | 52 | old / level-c / escalate | 2 | 312 | 140 | 2.0 |
| 1 | copper-ab | C2 + RC3 (shared control) | 43: crit-v6 A+B (33 qualified) + C6 + 6 power boards | default / rail_over_cap=1 / via_A=1.0 | 2 | 258 | 115 | 1.6 |
| 1 | edge-ab2 | P4 | 135 merit-500 boards with an *unlocked* pinned-kind connector (USB, barrel, RJ, video, SMA/BNC; place tasks keep locked parts where they are) | connector_edge 2 / 1 | 1 | 270 | ~250 | 3.6 |
| 1 | aa-joint | A/A noise floor | 213 merit | joint control / twin | 1 | 426 | 363 | 5.2 |
| | **tier 1 total** | | | | | 3320 | **~1940** | **~27 (35-40 with contention)** |
| 2 | eff-tiebreak-ab | J13 | 213 merit | control (reused from aa-joint) / eff1 | 1 | 213 new | 182 | 2.6 |
| 2 | keepupright-ab | K11 | 213 merit, kae place 300 s | keep-upright 0 / 1 | 2 | 852 | 192 | 2.7 |
| 2 | area-cost-ab | CI7b | 112 qualified (59 can differ; the rest are a determinism check) | 0.05 / 0.2 / 0.5 | 1 | 336 | ~60 (no past runs; pnr --plain + bridge, 900 s cap) | ~1 |
| 3 | placement-decide-staged | P5 + P10 (shared control) | 213 merit | control / cong0 / cong10 / margin0 | 2 | 1704 | 1261 | 18 |
| 3 | placement-decide-joint | J10 | 71 the joint loop leaves open (baseline-2611b) | control (reused att. 0) / bump0 / rmargin0 | 3 | 568 new | 624 | 8.9 |
| 3 | components (PP6, PP3/PP4, C8) | not registered | ~20 intent-213 cell boards / merit crystal boards | env arms | 3 | ~360 | ~300 | ~4 |
| — | pour_r_eff (PP7) | **skipped** | needs `pt_routed_calib.py --routed` phase-1 data (`kae-work-v2/tasks`), not on this host | | | | | |

Full plan ≈ 4,300 CPU-h ≈ 61 h at 70 cores, over the 48 h line: **only tier 1 is submitted.**
Tiers 2 and 3 are registered later (`decide-ab.sh register 2|3`, then `kaeres exp submit`).

## How the plan was shrunk

- **Board sets with power.** Legality arms run only where they can differ: four arms on the 113
  boards that downgrade a strict check, three on the 52 relax boards (strict = level-c there unless
  the project also waives), two on the 40 controls. place-fixed drops escalate on the downgrade set
  and runs no control. J10 runs only on the 71 boards where the loop's windows run. P4 runs only on
  the 135 merit-500 boards with an unlocked pinned-kind connector (scan: `decide-ab/edge_boards.py`, `kae.place.edge_check`); the first design (58 merit-213 boards, k = 2, `edge-ab`) is kept as the smoke.
- **Shared controls.** C2 and RC3 share one default arm. P5 and P10 share one staged control. J10,
  J13 and the A/A share one joint control (its attempt-0 runs are reused across experiments).
- **P4 arms 2 vs 1, not 0.** Mode 1 places exactly as mode 0 (the old placement) and also reports
  `connector_off_edge`, so the control arm carries the hazard count.
- **k.** k = 2 for the legality, copper and edge arms (the specs); k = 1 for the A/A and J13 (each
  run is already a restart portfolio); P5/P10 cut from k = 3 to k = 2 (expected |Δcp1| ≤ 0.02 is
  below what 213 × 3 resolves anyway); CI7b k = 1 (deterministic); K11 k = 2 at a 300 s budget
  (the writer is all that differs).
- **No Freerouting re-runs.** No arm is plain Freerouting (deterministic, one run per board).

## Priorities (kaeq `--prio`, higher first; other sessions' queued work is at 0 / -1 / -2)

legality-* and copper-ab: 3 · edge-ab2: 2 · aa-joint: 1. All jobs are class `timed` (budgets are
wall clock, so they must not be frozen). Submitted in two steps: a smoke of 2 boards per
experiment, then the rest.

## Decision criteria (from the decision reports)

- **P2** primary `legal_strict`, then `legal`, probe completion / cp, hpwl_ratio, errors by type
  (strict). strict replaces level_c as default only if it matches level_c on legality and probe
  completion on the downgrade set. Control set must not move.
- **P3** escalate vs level-c on the relax set: `legal` gained vs `body_overlap` hazards.
- **C2** cp1/cpk/completion/errors; count and max dT of `copper_below_ipc_width`. Expected: no change
  where the cap does not bind. **RC3** completion within ±1 board; hole/via clearance errors,
  `vias_below_current` count.
- **P4** completion, cp1/cpk, errors by type; `connector_off_edge` count (control) vs pinned.
- **A/A** cp1 / cpk / completion differences and p-values between identical arms: the noise floor.
