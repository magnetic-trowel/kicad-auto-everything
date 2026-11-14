<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# loop-win: windows chosen from evidence, against restarts at the same counted allowance (pre-registered)

Written 2026-11-14, before any run of this experiment.

## Why
`loop-compute-matched` (branch `loop-exp`) found that at the same allowance staged restarts beat the joint loop's windows: 4,485 vs 5,655 opens on 69 boards, 46 boards worse and 13 better, p 0.0001. The window bench and the replays say why:
- 41-53 % of windows repeat a part set already tried;
- about a third end "illegal after repair";
- windows target a connection's two ends, not what blocks it.

Three changes target these, each behind its own flag on branch `loop-win-combo` (merge of `loop-win-evidence`, `loop-win-tabu`, `loop-win-exact` and `loop-win-frcharge`, on `loop-win-base`):
- **evidence** (`window_evidence=1`): each incumbent's open connections are diagnosed by `kae.route.blocked` (nets in window order, within 30 s and 5 % of the budget; the set-up is charged as one DRC). A connection no move frees opens no window (a rule's binding gap against its own footprint, a pad walled in by its own footprint), and neither do J3's DRC types. Congestion adds its free corridor and the movable parts beside it. A rule gap or wall against other parts' pads adds those parts.
- **tabu** (`tabu=1`): a failed part set is not tried again until a window kept after the failure shares a part with it or lies within the loop margin. The next, larger attempt is tried instead.
- **exact** (`legal_exact=1`): a window still grid-illegal after greedy goes to the exact closed loop, and stands if the exact check is clean. Every arm reports `home_grid_illegal`, which says how often the incumbent itself is grid-illegal.

Also in every arm (no flag):
- **Window router budget under counted work** (`loop-win-frcharge`). The window router's budget grows and shrinks on charged work, not wall seconds; before, it moved with host load.
- **Freerouting charging.** Start-up and optimizer charging belong to branch `fr-budget-calibration`, which is not merged and is not used here. Both arms share main's charging, and measured CPU is reported against a guard (below).

## Arms (`setup.sh`, one commit, harness = kae = that commit, Freerouting fork d137fd1, `KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1`)
Allowance A = 3.15 × 900 s × sqrt(fp/40) of nominal work. The harness timeout is the 4 × A wall ceiling (cap 57,600 s).
- **R:** staged (`--max-iters 0 --no-modules`) under `restart.py --parallel 1` for A, with polish-merit's wrapper flags. This is the comparison windows lost.
- **W0 (ctl):** `kae.joint.cli run --time B --no-modules --set window_budget_factor=2`, with B = A / 3.15: iteration 0 on its natural shares of B, then two more budgets for windows. This is `loop-compute-matched`'s W without the module stage. R has no module stage either, and the module stage alone costs opens (chassis-soft: +57 %), so leaving it on would confound windows with modules.
- **We, Wt, Wx:** W0 plus one flag each (evidence, tabu, exact).
- **Wall:** W0 plus all three flags.

All six arms of a board and seed run side by side in one kaeq job (timed class). The step cache (`KAE_STEP_CACHE`, result-neutral) lets the W arms share iteration 0.

## Boards and seeds
- **Batch 1:** `boards.txt`, `loop-compute-matched`'s 69 boards. These are boards where the joint loop leaves connections open, one per repo family. Prior W left 82 opens per board, and the A/A between R runs has a per-board d sd of 0.150.
- **Seeds:** all six arms on seed 0 (`loop-win`). R, W0 and Wall also run on seed 1 (`loop-win-k2`, the same methods, attempt 1).
- **Extension:** `boards-extension.txt`, the 157 route_demand hard/extreme corpus boards from `loop-compute-matched`, one per new repo family, in its sha256 order. Batches of 60 (the last 37), with R, W0 and Wall at seeds 0 and 1, while the primary is undecided.

## Primary: Wall against R (opens)
- Per board and seed, `d = (o_W − o_R) / (o_W + o_R + 1)`. A board's d is the mean over its seeds. Sign-flip test over boards.
- **Wall wins** if mean d < 0, p < α, and total opens are at least 3 % lower. **R wins** on the mirror condition.
- Looks come after batch 1 and after each extension batch: at most 4 looks, α = 0.0125 each (Bonferroni over the 4).
- Anything else is undecided and starts the next batch. When the pool is used up, the verdict is reported as undecided.
- **Guards for a Wall win:**
  - DRC errors and placement errors not above R's by more than 5 %. The A/A spread of DRC errors is 3.4 %.
  - cp1 not lower by more than 2 boards.
  - Measured CPU at most 1.10 × R's. Over that, the result is a win at more real compute. It is not adopted until it is rerun with `fr-budget-calibration`'s charging.

## Per change: We, Wt, Wx and Wall against W0 (batch 1, seed 0; Wall also seed 1)
- **Acts** (descriptive, read from the loop reports):
  - We: a diagnosis on at least half of the boards that have windows, and blamed parts on at least 20 % of its windows.
  - Wt: the share of windows on a part set the board already tried is under 10 % (W0: about 40 %).
  - Wx: the share of windows ending "illegal after repair" is at most half of W0's.
- **Window yield** (decides): opens removed by the window phase. That is iteration-0 opens minus the opens of the last kept window, before the finishing stage. Paired per board, sign-flip test. The change pays if its yield is higher, p < 0.05, with these guards:
  - final opens not more than 5 % worse in total;
  - DRC errors not more than 5 % worse in total;
  - window-phase work (nominal) not more than W0's by more than 10 %.
- **Verdicts:** "pays" (acts, higher yield, guards hold); "acts, no gain" (acts, yield not decided); "does not act".
- Final opens, cp1 and the paired d against W0 are reported too.

## Also reported, per arm
- cp1 and cpk;
- completion, open connections, and DRC errors per type;
- CPU (measured and charged), `ceiling_hit`, time-outs;
- windows, kept, repeats, illegal, `home_grid_illegal`, tabu skips, evidence counts by cause;
- results by tag (route_demand, pad_density);
- physics on boards every compared arm routes fully, judged against the J21 floor only at n ≥ 38.

## Smoke and profile (before batch 1)
- **Smoke (`loop-win-smoke`):** `boards-smoke.txt`, two boards of batch 1 that stay in it: lenaschimmel bestelampe (small) and solderedelectronics dasduino coreplus (medium). All six arms, seed 0. Plumbing only: the arms and rules do not change after it unless it shows a plumbing fault, which is recorded here as an addendum.
- **Profile:** one board per arm (the small board for the W arms and R). py-spy on the python process, `--idle`, summed by `prof_stages.py`.

## Costs (information only)
- From `loop-compute-matched`: about 1.3-1.45 measured CPU-h per board and arm.
- Batch 1 is 69 × (6 + 3) runs, about 900 CPU-h with judging and physics.
- An extension batch is 60 × 6 runs, about 500 CPU-h.
