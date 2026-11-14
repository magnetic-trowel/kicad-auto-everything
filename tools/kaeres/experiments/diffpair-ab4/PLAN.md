<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# diffpair-ab4: pairs routed as pairs, after the rule and budget fixes (pre-registered plan)

Written 2026-11-14, before any run of this experiment's boards. Code: the commit `setup.sh` registers (`a3b6eeb`, branch
`diffpair-ab4`). Ledger E36, E37, R60, R61. Earlier results: `diffpair-ab3` (both arms failed the opens guard; two bugs),
`diffpair-soft` and `bus-post-relay` (other session; read for mechanisms only).

## What changed since diffpair-ab3
- `diffpair-rules`: the pair router lays width and gap per layer from the board's rules (custom track_width and
  diff_pair_gap, net-class diff-pair values), never rounded past a rule's edge; keeps off layers a custom rule disallows;
  checks the pair's coupled pieces against the diff_pair_gap rule as KiCad does (parallel pieces sharing a projection);
  skew bumps are triangles. On ewoudvv ducktop2 right_io the pair stage alone went from 199 track_width / 172
  diff_pair_gap_out_of_range / 6 items_not_allowed to 0 / 0 / 0.
- `diffpair-post-budget`: the post pass no longer takes 240 s from the repair rounds; it gets its own 240 s after them
  and is judged against the fully repaired board.
- `diffpair-fanin-soft`: `pairs_lock=spine` (off by default) leaves the fan-ins unlocked so Freerouting may rip them.
- `bridge-ses-width`, `bridge-disallow-layers` (all arms): Freerouting's session widths are given back where it rounded
  an odd-unit width up (0.1521 -> 0.1522 mm), and net classes keep off layers a custom rule disallows (use_layer).

## Question
Do pairs routed as pairs (first, or re-laid after routing) give coupled, length-matched pairs at no cost in opens or
DRC errors beyond measured noise, with the board's pair rules kept?

## Boards
`boards.txt`: the first 120 of `ordered.txt` (`select_boards.py`, seed `diffpair-ab4-2026-11-14`). Pool: the full tag
suites `diffpair_rules`, `if_usb3`, `if_hdmi.tmds_pairs`, `if_mipi`, `if_pcie`, `if_ethernet`, `if_lvds`, restricted
to the boards the human-layout pair scan covers (545 of 1,980); qualifying as in diffpair-ab3 (a rule- or interface-
tier pair with KiCad's suffix rule, legs >= 4 mm, human coupled share >= 0.5, the pair's pads within 2 mm on one
footprint), `usable_route_test`, 30-500 footprints, one board per `repo_family` (318 families). 103 of the 120 were
also in diffpair-ab3. Extension: the next 60 of `ordered.txt`.

## Arms (kaeq timed class, interleaved per board, same commit, Freerouting fork d137fd1 named in every recipe)
| arm | method | router budget | harness timeout |
|---|---|---|---|
| C  | bridge, no pair routing | 900 s | 900 s |
| Ct | bridge, no pair routing (time-matched control for F, FS) | 1080 s | 1080 s |
| F  | `--pairs first --set pairs_own_budget=true` | 900 s + pair stage (<= 180 s) | 1080 s |
| FS | F `--set pairs_lock=spine --set wire_type=shove_fixed --set wire_scope=pairs` | as F | 1080 s |
| P  | `--pairs post` (own 240 s after the full route and repair) | 900 s + 240 s | 1140 s |

Attempts: `--seed {attempt}` (the bridge permutes net order by seed, so attempts sample Freerouting's input order and
the host's wall-clock variation). The experiment sets `KAE_STEP_CACHE` (result-neutral): P replays C's identical
Freerouting runs and DRCs, so P's routed board before the post pass is C's.

## Noise, and how many attempts
Three earlier runs of the same control logic on the same boards (diffpair-ab3, diffpair-soft and bus-post-relay
controls, fork 2e1125a, 900 s, 108-120 boards) are an A/A: total opens differ by -0.9 %, +2.6 % and +4.3 %
(bootstrap intervals about -3 % to +15 %, heavy-tailed: a few boards carry most opens); the per-board difference of
log(opens + 1) between two single runs has SD 0.34-0.42; 48-52 boards were identical. DRC errors: -1.4 % to +1.8 %
here, 3.4 % between replicates elsewhere (loop-polish). With per-run noise sigma ~ 0.28 per board and k attempts per arm,
the board mean difference has SD ~ 0.4 / sqrt(k); with an assumed spread of true effects of 0.1, 120 boards give a
standard error of the geometric-mean ratio of about 0.026 at k = 2 and 0.023 at k = 3. A +5 % margin (log 0.049) is
then decided for a true change near 0 only with k >= 3 and often 180 boards. Round 1 runs k = 2; the extension below
adds attempts and boards.

## Outcomes
Pairs: the bus scorecard's pair rows (`kae.bus.scorecard`: coupled_3w, pad-to-pad skew_mm, vias_lane), tier rule or
interface from the human board with its project rules, measured in both arms, len_mean >= 4 mm in C, values averaged
over the attempts both arms have. Statistics by board (a board's pairs are not independent), bootstrap over boards.

**Primary** (F, FS, P each against C; as diffpair-ab3): coupled_3w median paired change >= +0.30, and skew median
paired ratio arm/C <= 0.5, both with the interval excluding the failing side.

**Guards** (F and FS against Ct, P against C):
- Opens: per board, mean over attempts of log(opens + 1), arm minus comparator. The geometric-mean ratio's upper
  bound <= 1.05 **and** the total-opens change <= +5 % (above the largest A/A total difference, 4.3 %). Fails when the
  lower bound > 1.05.
- DRC errors: the same, +5 %.
- Pair rules kept: the arm's track_width + diff_pair_gap_out_of_range + items_not_allowed per attempt not above its
  comparator's by more than 5 % + 5 errors; read by type and board.
- cp1 reported with flips (not deciding at this n).

Secondary, reported: vias per pair; survival of FS's pair copper (`pairs.survival`); CPU per arm; timeouts; physics
where both are complete (noise floor J21); results by tag (`pad_density`, `route_demand`, interface).

## Decision (each of F, FS, P)
- **Pass**: primaries reached, guards hold: a candidate default option (the user decides).
- **Partial**: primaries reached, a guard fails or stays undecided after the extension: report where it costs.
- **Fail**: a primary not reached.
Between F and FS, if both pass, the one with lower opens (geometric mean, paired) is preferred; FS's survival is read.

## Looks and extension
Look 1 after round 1 (120 boards, attempts 0-1, every arm): 97.5 % intervals (two looks, Bonferroni). If a guard is
undecided (upper bound > 1.05, lower bound <= 1.05) for an arm whose primaries are reached, round 2 adds attempt 2 for
every arm on the 120 boards and the next 60 boards of `ordered.txt` at attempts 0-2; look 2 decides with 97.5 %
intervals over everything. No look in between; no change to arms, boards or rules after look 1 except as written here.

## Run
`SHA=a3b6eeb4e6a010d0d39522955f556e1d031ce2e9 setup.sh`; numba cache `numba-kae-dp4-a3b6eeb` warmed;
`kaeres exp create diffpair-ab4 --boards @boards.txt --attempts 2 --env KAE_STEP_CACHE=/var/tmp/$USER/step-cache ...`;
`kaeres exp submit diffpair-ab4`. Pair scorecards: `kaeres bus submit diffpair-ab4 --boards @boards.txt --method ...
(all five) --kae a3b6eeb`. Analysis: `analyze.py diffpair-ab4 --level 0.975` in a kae venv.

## Cost (information)
About 0.3 CPU-h per run at 900-1140 s: 120 boards x 5 arms x 2 attempts, about 330 CPU-h (P cheaper with the step
cache); the extension about 270 CPU-h more.
