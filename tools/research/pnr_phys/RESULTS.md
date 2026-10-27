<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Physics score of the joint place-and-route runs (tag `phys`)

## How the scorer works
`physics_score.py RUN_DIR...` runs in the `kae` venv (branch `claude/vigilant-mayer-i91rrr`,
`KAE_KICAD_PYTHON=/usr/bin/python3`). Once per board it builds the netlist-only brief, which
is identical from the reference or the input and is the one `pnr/physics.py` optimizes. It
then builds `Terms(board, brief)` and caches both in `kae-work/phys-cache/<id>/`.

The human reference and each run's `attempt-0` output are scored with that same brief:
- **place**: `Terms.total` (confidence × φ(u), barrier above budget) and the robust
  **capped-u** Σ min(u, 5);
- **routed**: `critical_recheck.board_physics` on the real copper, with zones refilled by
  KiCad, summarized as the Scorecard's `physics_total`. Unrouted hops are priced as straight
  strips, which is optimistic, hence the "no open hop" column.

Ratios are geometric means of (method + 0.01) / (human + 0.01). "Worse" means more than
0.1 % above the human. Legal, clean and completion come from `attempt.json`. Results go to
`kae-work/phys/<run>.json` and `table-v5.md`.

## Coverage
- All 33 A+B boards are scored on both place and routed physics, with no per-board errors.
- **Only 10/33 boards have any physics structure.** On the other 23 the brief finds only
  connector chains, victims or antennas, with nothing to price them against, so every term
  is 0. Every statement below is about those 10 boards.
- Every placement run has no output for `azonenberg` and `suzyqboard`. Neither has any
  structures, so this costs no coverage.

## Table (v5, same engine and boards)
| run (v5) | legal / clean / compl. (10 phys boards) | clean / compl. (33) | φ-total × human | capped-u × human (worse/better) | legal only: capped-u × human | routed × human (worse/better) | routed, no open hop (n) |
|---|---|---|---|---|---|---|---|
| route | 10 / 4 / 0.96 | 21 / 0.92 | 1.00 | 1.00 (0/0) | 1.00 (n=10) | 1.09 (3/7) | 0.90 (5) |
| seq | 7 / 3 / 0.86 | 18 / 0.86 | 4.05 | 1.45 (8/1) | 1.31 (n=7) | 1.39 (7/3) | 1.45 (3) |
| seq_phys | 7 / 3 / 0.86 | 18 / 0.86 | 1.52 | 1.20 (5/4) | 1.02 (n=7) | 1.26 (7/3) | 1.32 (3) |
| grow | 8 / 4 / 0.86 | 18 / 0.86 | 7.35 | 1.77 (8/1) | 1.60 (n=8) | 1.37 (8/2) | 1.42 (4) |
| anneal | 9 / 4 / 0.89 | 19 / 0.87 | 4.28 | 1.57 (7/2) | 1.37 (n=9) | 1.54 (6/4) | 2.08 (5) |
| anneal_phys | 8 / 4 / 0.89 | 19 / 0.88 | 1.68 | 1.29 (7/2) | 1.11 (n=8) | 1.33 (7/3) | 1.20 (5) |

The other v5 runs are added to `kae-work/phys/table-v5.md` as they finish.

## What it says
- **HPWL placements are physically worse than the human ones**:
  - capped-u is ×1.45–1.77 the human's, worse on 7–8 of 10 boards;
  - φ-total is ×4–7.
- **Where the excess comes from:**
  - **decap**, 50–70 % of the capped excess. HPWL pulls a capacitor toward its rail and
    ground nets, not toward the pin it serves. Example: paw3222's VDDA loop goes from u 1.05
    to 7.4.
  - **coupling**, about 25 %. Example: olimex's buck feedback node sits next to the switch
    node, at u 40 (405 mV against a 10 mV budget).
  - **world_cm**, the cable common-mode term.
  - ESD paths are *better* than the human's, because compaction shortens the hop from the
    connector to the TVS.
- **Physics in the objective closes most of the place-terms gap at almost no routing cost.**
  - `seq_phys` against `seq`:
    - capped-u drops from ×1.45 to ×1.20 (and ×1.02 on legal placements, which is human level);
    - φ drops from ×4.05 to ×1.52;
    - coupling drops from ×3.5 to ×1.2, decap from ×1.33 to ×1.15, thermal from ×1.39 to ×0.94;
    - legal, clean and completion are identical;
    - routed length is +1.7 % on the physics boards.
  - `anneal_phys` against `anneal`:
    - capped-u drops from ×1.57 to ×1.29 (legal only: ×1.11);
    - routed physics drops from ×1.54 to ×1.33;
    - clean and completion are equal;
    - routed length is +10 % on the physics boards.
  - Four boards did not change under `seq_phys`. On bipolar every physics part is locked.
- **Routed physics stays about ×1.2–1.3 the human's even with physics in placement.**
  - The engine's router is not the main cause: on the human placement it scores ×0.90 on the
    5 boards with no open hop.
  - The rest comes from the decap and commutation terms that remain, and from copper the
    place terms do not see. The routed recheck is worth adding to acceptance.
- **Caveats:**
  - The priors are E5 (not yet measured). Read the numbers as relative.
  - `seq_phys` optimizes the same Terms that score it, so the routed column is the less
    circular check.
  - n = 10 boards.

## Optimizing physics in the loop (as `pnr/physics.py` does)
1. Build `T = Terms(load(input), brief)` once.
2. Keep poses keyed by uuid, as `(*world.xy(cx, cy), ROTS[ri], 'B'|'F')`, for *every* part;
   a missing part is evaluated at its input pose.
3. Price each move with `T.delta(poses, [uuid], {uuid: new})`, which takes 30–60 µs;
   `delta_by_kind` splits it per term.
4. Skip parts outside `T.parts()`.
5. Add `w·d` to the routability cost, because Terms ignore legality.
6. After routing, recheck with `board_physics(path, brief, terms=T)`.
