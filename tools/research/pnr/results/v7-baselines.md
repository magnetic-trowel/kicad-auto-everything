<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# v7 joint place-and-route baselines (PARTIAL)

> **Partial.** The run was stopped on request before it finished. Four arms are complete:
> `seq`, `seq_phys`, `combo_lv` and `combo`, each 99 of 99 attempts (33 boards × 3 seeds).
> The two jc arms are incomplete: `jc_lv` 94 of 99, `jc` 88 of 99. They are reported only on
> the 24 boards where both have all 3 seeds. The 5-board v6.4 re-runs (`-r4cu`) were not run,
> and jc has no physics scores yet.

## Setup

| Item | Value |
|---|---|
| Harness | kaebench score v7, task spec 6, `--kinds joint`: place and route in one output, scored by `score_joint_task` with kicad-cli; workdir `kae-v7/` (KiCad 10.0.7) |
| Engine | pnr **v6.3** (c78c537): v6 plus fixes 1, 2, 5, 6 and 7 of [v7-bugs.md](v7-bugs.md) |
| Budget | 120 CPU-s (`placekit.Clock`), seeds 0–2 = attempts 0–2 (`-k 3`), timeout 1080 s wall; there were no timeouts and no failures |
| Runner | `kae-v7/runj.sh SPEC NAME 120 kae-v7/ab33.txt 2 3`, sandboxed |
| Runs | `v7-seq-r3`, `v7-seq_phys-r3`, `v7-combo_lv-r3`, `v7-combo-r3`, `v7-jc_lv-r3` (partial), `v7-jc-r3` (partial), plus `v7-route-r3` (the human placement routed by the same router, route task, k = 1) |
| Methods | `seq`; `methods_phys.py:seq_phys`; `methods_combo.py:combo_lv` / `combo`; `collapse_joint/jc.py:jc_lv` / `jc` (unmodified) |
| Tables | `seeds.py` (DRC) and `phys_seeds.py` (physics); every value is the mean ± half-range over the 3 seeds |

**Board sets.**
- **28 boards (headline):** [v63-v64-unchanged.txt](v63-v64-unchanged.txt). Engine v6.4 is
  identical to v6.3 on these boards (every static map and part raster hashes the same), so the
  numbers will not change once v6.4 lands.
- **33 boards:** the full set, as run on v6.3. On the 5 other boards (olimex, paw3222,
  badjeff-pmw3610, oasis-ledboard, jvedder), v6.3 has a known bug: board copper is not a pad
  keep-out (bug 8).

## DRC: 28 unchanged boards (headline, complete arms)

Length and vias are summed over the 19 boards that every arm completed on every seed.

| Arm | Legal | Clean | Completion | Length (mm) | Vias |
|---|---|---|---|---|---|
| seq | 0.893 ± 0.000 | 0.607 ± 0.036 | 0.904 ± 0.003 | 2715 ± 30 | 62.7 ± 11.0 |
| seq_phys | 0.893 ± 0.000 | 0.595 ± 0.036 | 0.903 ± 0.003 | 2719 ± 33 | 62.0 ± 11.5 |
| combo_lv | 0.917 ± 0.018 | 0.643 ± 0.036 | 0.933 ± 0.002 | 2362 ± 17 | 30.3 ± 1.0 |
| combo | 0.917 ± 0.018 | **0.667 ± 0.054** | **0.935 ± 0.003** | **2350 ± 2** | **29.0 ± 2.5** |

Per seed (legal / clean / completion):
- seq: 0.893/0.571/0.907; 0.893/0.643/0.903; 0.893/0.607/0.902.
- seq_phys: 0.893/0.571/0.907; 0.893/0.571/0.902; 0.893/0.643/0.901.
- combo_lv: 0.929/0.643/0.935; 0.929/0.679/0.930; 0.893/0.607/0.935.
- combo: 0.929/0.714/0.934; 0.929/0.679/0.939; 0.893/0.607/0.933.

## DRC with jc: 24 of the 28 boards with all 3 jc seeds (partial)

Length and vias are summed over the 16 boards every arm completed on every seed.

| Arm | Legal | Clean | Completion | Length (mm) | Vias |
|---|---|---|---|---|---|
| seq | 0.917 ± 0.000 | 0.583 ± 0.042 | 0.899 ± 0.003 | 2593 ± 50 | 60.7 ± 11.0 |
| seq_phys | 0.917 ± 0.000 | 0.569 ± 0.042 | 0.898 ± 0.004 | 2597 ± 53 | 60.0 ± 11.5 |
| combo_lv | 0.944 ± 0.021 | 0.625 ± 0.042 | 0.929 ± 0.000 | 2294 ± 20 | 30.3 ± 1.0 |
| combo | 0.944 ± 0.021 | 0.653 ± 0.062 | 0.932 ± 0.006 | **2283 ± 4** | **29.0 ± 2.5** |
| jc_lv | **0.986 ± 0.021** | **0.722 ± 0.021** | 0.928 ± 0.004 | 2344 ± 25 | 41.0 ± 5.5 |
| jc | **0.986 ± 0.021** | 0.694 ± 0.062 | 0.932 ± 0.005 | 2351 ± 55 | 43.7 ± 2.0 |

## DRC: all 33 boards on v6.3 (as run)

| Arm | Legal | Clean | Completion | Length (mm, 22 boards) | Vias |
|---|---|---|---|---|---|
| seq | 0.879 ± 0.000 | 0.566 ± 0.030 | 0.894 ± 0.007 | 3389 ± 44 | 74.0 ± 12.0 |
| seq_phys | 0.879 ± 0.000 | 0.566 ± 0.030 | 0.893 ± 0.007 | 3376 ± 46 | 67.0 ± 11.5 |
| combo_lv | 0.879 ± 0.030 | 0.626 ± 0.045 | 0.924 ± 0.002 | 2947 ± 18 | 33.7 ± 0.5 |
| combo | 0.869 ± 0.015 | 0.657 ± 0.045 | 0.925 ± 0.003 | 2994 ± 18 | 36.3 ± 3.0 |

The table that swaps in the 5-board v6.4 re-runs is pending: `-r4cu` has not run. When it
has, run `seeds.py --override v7-X-r3=kae-v7/results/v7-X-r4cu --override-ids kae-v7/cu5.txt`.

Reference: the human placement routed by the same router (`v7-route-r3`, route task, one
deterministic run) is clean on 0.667 of the 33 boards (A 0.923, B 0.500), with completion 0.927.

DRC errors left in the outputs on the 28 boards:
- `silk_overlap` / `silk_over_copper`: ecc83 only. Silkscreen is not modelled.
- `starved_thermal`: 12–20 per arm over 84 attempts.
- Rare `solder_mask_bridge`: lt6c's U1 mask polygon.

Not legal on the 28 boards, all of them method or engine-model failures, not crashes:
- `seq` / `seq_phys` leave parts staged off the board when they find no legal spot
  (xiao-base SW2/SW3, paw3395, kabukiflux R3).
- `combo` / `combo_lv` also fail on biscuit-crowbar seed 2.

## Physics vs human (10 physics boards; complete arms only)

Each value is the method / human geometric mean; below 1 is better than human. "Fast" is the
kae place-terms capped utilisation; "routed" is kae's routed recheck on the real copper.

| Arm | Legal (of 10) | Clean | Place terms | Fast (capped u) | Routed | Routed, no open hop (n per seed) |
|---|---|---|---|---|---|---|
| human placement, same router (`v7-route-r3`, seed 0 only) | 10 | 6 | 1.00 | 1.00 | 1.11 | 1.15 (6) |
| seq | 9.0 ± 0.0 | 4.3 ± 1.5 | 2.52 ± 0.37 | 1.22 ± 0.10 | 1.22 ± 0.07 | 1.60 ± 0.23 (5/5/4) |
| seq_phys | 9.0 ± 0.0 | 4.3 ± 0.5 | 1.12 ± 0.07 | **1.01 ± 0.05** | **1.11 ± 0.09** | 1.38 ± 0.23 (5/5/4) |
| combo_lv | 8.3 ± 0.5 | 5.3 ± 1.0 | 2.84 ± 0.50 | 1.31 ± 0.04 | 1.26 ± 0.07 | 1.27 ± 0.09 (7/7/6) |
| combo | 8.0 ± 0.0 | 5.7 ± 0.5 | 1.26 ± 0.11 | 1.06 ± 0.06 | 1.27 ± 0.03 | **1.24 ± 0.07** (7/7/6) |

Per seed (fast / routed):
- seq: 1.31/1.26; 1.26/1.26; 1.10/1.13.
- seq_phys: 1.02/1.12; 1.05/1.20; 0.95/1.01.

On the 6 physics boards unchanged by v6.4, the ordering is the same. seq_phys is best on fast
physics (1.15 ± 0.04) and combo second (1.28 ± 0.09). combo is best on routed with no open hop
(1.31 ± 0.05). The jc arms are not physics-scored yet.

## What is trustworthy and what isn't

**Trustworthy:**
- **Harness integrity.** All 396 attempts of the complete arms are status ok and valid; none
  moved an anchored part, and none timed out.
- **Engine and KiCad agree on connectivity.** The engine's own unrouted count matches KiCad's
  unconnected count, except where explained: unplaced parts, zone-connected pads, and copper
  arcs on the excluded boards.
- **The 28-board DRC table.** It does not depend on the v6.4 fix.
- **The physics objective costs nothing in routability.** seq vs seq_phys and combo_lv vs
  combo are equal on legal, clean and completion, and better on fast physics.
- **combo beats seq on every seed** in completion (+0.03), copper (−13%) and vias (−54%).

**Within seed noise:**
- combo vs seq on clean (+0.06 ± 0.05).
- combo vs combo_lv on clean.

**Partial:**
- jc. On 24 boards it is the most often legal (0.986) and the cleanest (jc_lv 0.722), but with
  more vias than combo.

**Not trustworthy, or biased:**
- **The 33-board numbers.** The 5 boards with copper drawings are judged by a v6.3 engine that
  ignores those drawings.
- **Physics.** It rests on 10 boards, or 6 unchanged by v6.4, with 4–7 boards per routed
  comparison. Open hops flatter routed physics.
- **Some failures come from an over-strict legality model.** The engine's model rejects the
  human placement on 13 of 33 boards (thermal-spoke corridors, mask apertures). Several
  "no legal spot" failures are this model's fault.
- **CPU accounting.** `cpu_s` in kaebench reports is not usable for sandboxed methods. Budgets
  are process CPU inside the method; wall time per attempt was 2–5× the budget under a
  machine load of about 15.
