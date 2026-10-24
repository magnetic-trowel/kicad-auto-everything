<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Harmonic-field routing in the joint loop (tag `harm`, idea 19)

Idea 19 from [joint-pnr](../../../docs/ideas/original/joint-pnr.md), built on [jc](../collapse_joint/RESULTS.md). Code: [field.py](field.py), [stream.py](stream.py), [hjc.py](hjc.py), [diag.py](diag.py), [congestion.py](congestion.py).

## Formulation

- **Field.** Resistor network on a 0.4 mm grid: one node per cell per layer, 4-neighbour edges, via edges scaled by 0.2. Fine cells have conductance 1/(1 + hist + β·foreign); static blocks are 0. Coarse cells take the block mean; edges take the harmonic mean. Cells below 0.02 are removed, which makes walls Neumann.
- **Solve.** Per net: the pin nearest the centroid is held at φ = 1, the other pins at 0. Sparse LU runs on the pin bounding box + 4 mm, about 60–80 ms per net (1–4 % of cells; 0.3 s on board-wide nets). Warm-started red-black SOR did not converge in 600 sweeps, so it was dropped.
- **Route without search.** Steepest ascent by edge current from each sink to the source. Paths merge into a tree, then go to 0.1 mm with line-of-sight pulling.
- **Uses in jc** (continuation, restarts, legalization and polish unchanged):
  - **(a) `stream`:** the streamline tree is the route inside the loop. Conflicts are priced as in jc, and the final copper comes from jc's PathFinder.
  - **(b) `bias`:** A* gets a cost of +0.5 outside a ±1-cell corridor around the tree. This is the topology prior.
  - **(c) `press`:** each part also pays for the summed |J|/I of other nets under its pad halos (Maxwell-stress analog). The price is capped at β = 2.
  - **`hroute` (route task):** PathFinder with (b) on the human placement.

## What worked, what failed

- **No local minima, as promised.** Ascent reached the source for 974 of 980 connections (33 human boards, committed copper as walls).
- **But no route.** Only 49.5 % of streamline connections are clearance-legal at 0.1 mm (34 % of nets). Legal ones are 1.45× A* length. The causes are wall hugging, 4-neighbour staircases and max-current paths that are not shortest. Solve CPU is 56× A*.
- **(a) in the loop** never converges. On the gas sensor at β = 26 there were 430 wire conflicts and 2× the copper. The continuation runs to β = 500 and jc's final A* rescues it.
- **(c) uncapped** pricing (∝ β) made parts accept courtyard overlap rather than sit in other nets' flux (overlap stuck at 72 cells at β = 500). Capping the price fixed this.
- **Congestion signal: modest gain.** Summed |J|/I (pads as walls, before routing) predicts the router's copper better than RUDY. Spearman over cells: 0.26 vs 0.18, better on 23/33 boards. Top-decile overlap: 0.21 vs 0.16. Both are weak.
- **Field CPU** was 15–25 % of the 120 CPU-s budget, so there were fewer jc restarts.

## Results

Place tasks, 33 A/B boards, 120 CPU-s, seed 0. Length and vias are summed over the 24 boards that all runs completed. Physics is the method/human ratio, gmean over the 10 physics boards. φ-total is fast physics; routed physics comes from the full recheck. Full tables: `kae-work/score/harm-{stream,press,lv}.md`.

| Run | Legal | Clean | Completion | Length (mm) | Vias | Fast physics | Routed physics |
|---|---|---|---|---|---|---|---|
| `pnr-combo-v5` | 0.848 | 0.636 | 0.897 | 3311 | 68 | 1.03 | 1.13 |
| `jc` (`jcollapse-jc-ab33-v3`) | 0.879 | 0.667 | 0.897 | 3264 | 74 | **0.82** | **1.05** |
| `hjc_stream` (a)+(c) | **0.909** | **0.697** | 0.902 | 3410 | 73 | 1.02 | 1.19 |
| `hjc_press` (c) | **0.909** | 0.667 | **0.908** | +3 % vs jc (25 boards) | −4 % | 0.85 | 1.09 |
| `jc_lv_nopol` (phys_w 0) | LVJC |
| `hjc_stream_lv_nopol` | LVH |

Notes on the table:
- `hjc_press` routed physics: better than human on 6/10 boards (jc 5/10). On boards with no open hop it scores 1.14 vs 1.27.
- **Seeds 0–2** on the 10 boards where jc also has them (mostly easy A boards): legal and clean are identical on every seed (9/10, 9/10). `hjc_stream` uses **+8 % copper on all three seeds** (585 vs 539 mm mean).
- **dev6** (1 seed): every variant ties jc on legal (1.0). Clean is 0.67–0.83 against 0.83. Copper is 568–634 mm against 612; `bias` is 609 and `bias+press` is 629. The `lv` twin with polish uses +10 % copper vs `jc_lv_nopol`.

Route tasks (human placement, 33 boards) vs the same engine (`pnr-route-v5`):

| Run | cp1 A / B / all | Completion | Error boards | wl_ratio |
|---|---|---|---|---|
| `pnr-route-v5` | 0.846 / 0.50 / 0.636 | 0.924 | 0.394 | 0.746 |
| `hroute` (b) | 0.923 / 0.50 / 0.667 | 0.930 | 0.212 | 0.791 |

Three boards became clean and two stopped being clean, with +6 % copper and more vias. This is perturbation, not a systematic effect.

## Verdict

**No merit as a router; inconclusive (at best a tie) as a joint-loop component.**
- The harmonic guarantee (every streamline reaches its sink) holds, but streamlines are neither clearance-legal nor short. Inside jc they are a costly, noisy stand-in for A*: same DRC, more copper, worse physics.
- The part pressure (c) is the only use that does not hurt. It gave the best single-seed completion (0.908) and legality (0.909), with physics within 4 % of jc. That gap is inside the seed noise reported for `combo` (clean ±0.09).
- The field's real value is as an obstacle-aware congestion map, a small but consistent gain over RUDY.
- Joint vs separate: every variant ran inside the joint loop, so nothing here re-tests separability.

## Next step

Use |J|/I only as a cheap congestion feature, for example in jc's restart ranking or as a learned-value input. Run 3 seeds of `hjc_press` on all 33 before any claim. Drop streamline routing.

Runs: `kae-work/results/harm-{hjc_stream,hjc_press,hjc_stream_lv_nopol}-ab33-v1`, `harm-*-dev6-v{1,2}`, `harm-hroute-v1`. Diagnostics: `kae-work/harm/{diag04,congestion}.json`. Figure: [fig/gas-sensor-field.png](fig/gas-sensor-field.png). `pyamg` was installed into `bench/.venv` for a solver test and is unused.
