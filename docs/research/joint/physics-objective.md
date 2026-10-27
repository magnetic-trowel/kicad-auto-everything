# Physics place terms in the placement objective, and the physics scorer

**Status:** worked (objective); the scorer is a working measurement tool.
**First published:** 2026-10-24, commit [2a1c9c1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2a1c9c1f6213e7e289bea7e014c0e9b5c90b6328) on branch `claude/keen-wright-mlkjv6` (engine v5; scorer [6e5c658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6e5c658f0ea7c268fe8d44682160bf7a820b4d4b)).

Placements that minimize wire length (HPWL) are electrically worse than human ones: decaps far from
the pin they serve, feedback nodes next to switch nodes. Adding kae's fast physics terms to every
placement objective (idea 43 of the [catalog](../../ideas/original/joint-pnr.md)) closed most of that
gap at no cost to routing completion.

## Idea and how it works

### Physics in the objective (`pnr/physics.py`, `pnr/methods_phys.py`)

- `Phys` builds a netlist-only "brief" (which parts form a decap loop, hot loop, crystal, cable
  entry, ESD path, coupled victim) and kae's `Terms` object once per board. It keeps poses by
  footprint uuid.
- A move is priced with `Terms.delta(...)` in 30–60 µs. Terms are φ(u) per structure, where u is the
  structure's metric over its budget: decap loop inductance (nH), hot-loop inductance (nH), coupling
  (mV), crystal (ppm), thermal rise (K), cable common-mode, ESD path.
- Objective = routability cost + `phys_w` · Δphysics, with `phys_w` = 2 mm of copper per unit of φ.
- `descent_phys`: best-response descent. Physics parts use a coarse physics map over their legal
  origins (`coarse_map`); others use the HPWL map.
- `seq_phys` = HPWL placement (as `seq`), then `descent_phys`, then route.
- `anneal_phys` = annealing on routed cost + `phys_w` · physics. Half the moves pick a physics part; a
  third of those jump to the part's best HPWL + physics spot.
- `RoutedPhys`: a full routed recheck (~1.5 s, a KiCad subprocess) for stage gates in `combo_full`
  and `jc_full`.
- kae is found through `KAE_SRC` (default `~/.cache/kaebench/kae-phys/src`, else `kae/src` in the
  repo).

### Physics scorer (`pnr_phys/physics_score.py`)

`physics_score.py RUN_DIR...` (kae venv). Per board, once (cached): build the brief (identical from
the reference board or the task input) and `Terms(board, brief)`. Score the human reference and each
attempt:
- **place:** `Terms.total` (confidence × φ(u), barrier above budget), and the robust **capped-u**
  Σ min(u, 5);
- **routed:** kae's `critical_recheck.board_physics` on the real copper, with zones refilled by KiCad.
  Unrouted hops are priced as straight strips (optimistic), so a "no open hop" column is reported too.

Ratios are geometric means over boards of (method + 0.01) / (human + 0.01).
`xf_common/physics_score_xf.py` supersedes it for the xf rounds.

## What we tried

- **v5 era** (place tasks, engine v5, 1 seed): `seq` vs `seq_phys`, `anneal` vs `anneal_phys`, `grow`,
  on ab33; physics on the 10 boards with any physics structure ("phys10").
- **v7 era** (joint tasks, engine v6.3, 3 seeds): `seq`, `seq_phys`, `combo_lv` (phys_w = 0), `combo`.

The two eras are not comparable (different task kind, engine and seed count; see
[engine.md](engine.md#what-we-tried)).

## Results

v5, phys10, 1 seed, ratio to human
([pnr_phys/RESULTS.md](../../../tools/research/pnr_phys/RESULTS.md), [15e1899](https://github.com/magnetic-trowel/kicad-auto-everything/commit/15e189903b958c1a77e5ca1aaae21ac526b38a25)):

| run | clean / compl. (33 boards) | φ-total | capped-u (worse/better boards) | routed (worse/better) |
|---|---|---|---|---|
| human placement, pnr router | 21 / 0.92 | 1.00 | 1.00 | 1.09 (3/7) |
| seq | 18 / 0.86 | 4.05 | 1.45 (8/1) | 1.39 (7/3) |
| **seq_phys** | 18 / 0.86 | **1.52** | **1.20** (5/4) | **1.26** (7/3) |
| grow | 18 / 0.86 | 7.35 | 1.77 (8/1) | 1.37 (8/2) |
| anneal | 19 / 0.87 | 4.28 | 1.57 (7/2) | 1.54 (6/4) |
| **anneal_phys** | 19 / 0.88 | **1.68** | **1.29** (7/2) | **1.33** (7/3) |

- Where the HPWL excess comes from: decap 50–70% of the capped excess (HPWL pulls a capacitor toward
  its rail and ground nets, not toward the pin it serves), coupling ~25% (olimex buck: feedback node
  next to the switch node, 405 mV against a 10 mV budget), cable common-mode. ESD is *better* than
  human, because compaction shortens the connector-to-TVS hop.
- `seq_phys` vs `seq`: coupling 3.5× → 1.2×, decap 1.33× → 1.15×, thermal 1.39× → 0.94×; legal, clean
  and completion identical; routed length +1.7% on the physics boards.

v7, phys10, 3 seeds, mean ± half-range
([v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md)):

| arm | place terms | fast (capped-u) | routed |
|---|---|---|---|
| human placement, same router (1 run) | 1.00 | 1.00 | 1.11 |
| seq | 2.52 ± 0.37 | 1.22 ± 0.10 | 1.22 ± 0.07 |
| **seq_phys** | 1.12 ± 0.07 | **1.01 ± 0.05** | **1.11 ± 0.09** |
| combo_lv | 2.84 ± 0.50 | 1.31 ± 0.04 | 1.26 ± 0.07 |
| combo | 1.26 ± 0.11 | 1.06 ± 0.06 | 1.27 ± 0.03 |

Scorer findings:
- Only **10 of 33** boards have any physics structure; on the other 23 every term is 0.
- Fast physics predicts routed physics only weakly: within-board Spearman 0.55 (range 0.13–0.95 over
  boards) ([scorecard.md](../../ideas/original/scorecard.md)).

## Verdict

**Worked.** Physics place terms cut the place-physics gap to human from ~4× to ~1.5× (v5) and capped-u
to human level in v7, with no loss in legality, clean rate or completion. Routed physics improves less
(1.39 → 1.26 v5; 1.22 → 1.11 v7) and stays above human: copper the place terms do not see, and the
remaining decap and commutation terms.

Caveats:
- n = 10 boards; kae's priors are unmeasured ("E5"), so ratios are relative, not absolute.
- `*_phys` optimizes the same terms that score it; the routed column is the less circular check.
- `RoutedPhys` runs in a subprocess outside the CPU clock (affects `combo_full`, `jc_full`).

`seq_phys` and `anneal_phys` are arms of the merit list (`tools/kaeres/experiments/merit-restart.sh`);
the 500-board comparison (`merit-500r3` / `merit-500r3k`) is running.
Results on the 500-board comparison: pending.

## Code

- [`tools/research/pnr/physics.py`](../../../tools/research/pnr/physics.py) (`Phys`, `RoutedPhys`),
  [`methods_phys.py`](../../../tools/research/pnr/methods_phys.py) (`seq_phys`, `anneal_phys`,
  `grow_phys`, `descent_phys`).
- Scorer: [`tools/research/pnr_phys/physics_score.py`](../../../tools/research/pnr_phys/physics_score.py),
  xf version [`xf_common/physics_score_xf.py`](../../../tools/research/xf_common/physics_score_xf.py).
  Needs the kae package (`KAE_SRC`).

## Related

- [sequential-controls.md](sequential-controls.md) (`seq`, `grow`),
  [anneal-and-repair.md](anneal-and-repair.md) (`anneal_phys`), [combo.md](combo.md), [jc.md](jc.md).
- Exact physics maps instead of `Terms.delta` sampling: [jc-extensions.md](jc-extensions.md#exact-physics-maps-t2).
