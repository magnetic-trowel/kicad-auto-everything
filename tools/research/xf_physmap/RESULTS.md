<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# xf B: exact physics maps (T2)

## Built

- **[physmap.py](physmap.py), `ExactPhys(Phys)`:** `exact_map(pi, ri)` = `Phys.delta` at every cell, and `coarse_map` returns it. Spend is mapped per component; φ(u) and the reduction are applied pointwise.
  - **Thermal:** a spectral Neumann (DCT-II) screened-Poisson solve with kae's G_s and λ. Sources are smoothed (σ 0.4 mm), with exact floored K0 near every image and a smooth correction to kae's truncated lattice.
  - **Loops, coupling and CM:** kae's `loop_core` and `eng_eval` run over the grid in numba loops.
  - **Decap pour and nearest load, ESD, crystal:** numpy closed forms.
  - **Grid:** nodes every 0.4 mm, bilinear, exact refinement where the curvature estimate exceeds 1%, with a CPU budget per map.
- **Departures from the plan:** decap is the hop-mode `LoopComp` on 9/10 phys boards, not analytic, so kae's kernel is compiled over the grid. Coupling uses the exact engine, not FFT, because it passed the gate.
- **[jc_x.py](jc_x.py)** wraps `collapse_joint/jc.py` without editing it.
  - **Lift and polish:** use the exact map (0.3 s per map).
  - **Best response:** the whole-board argmin includes phys_w·map/g (0.05 s per map), and the top candidates are still re-scored with `Terms.delta`.
  - **Cap:** best responses fall back to plain jc when their maps take more than 35% of CPU.
- **Tools:** [gate.py](gate.py), [gate_summary.py](gate_summary.py), and [phys_seed.py](phys_seed.py) (scores attempt-N).

## Gate (phys10, human plus random placement, 500 cells per part and rotation)

e = |map − delta| / max(|delta|, 10⁻³)

| Term | n | Median | p95 | p99 | ≤1% | ≤5% |
|---|---|---|---|---|---|---|
| thermal | 24k | 9e-5 | 3.2e-3 | 1.4e-2 | 0.984 | 0.997 |
| coupling | 72k | 6e-6 | 2.9e-3 | 1.0e-2 | 0.990 | 0.999 |
| world_cm | 60k | 1e-5 | 8.6e-3 | 6.5e-2 | 0.958 | 0.988 |
| decap | 240k | 6e-5 | 3.5e-3 | 2.0e-2 | 0.980 | 0.997 |
| commutation | 36k | 4e-6 | 5.0e-3 | 3.6e-2 | 0.971 | 0.993 |
| esd | 16k | 3e-6 | 4.4e-4 | 2.1e-3 | 0.997 | 0.998 |

- **Passes at p95:** thermal 0.3% (limit 1%), coupling 0.3% (limit 5%).
- **Exact at full resolution:** with the stride at the grid, every term matches to 1e-14.
- **Maxima:** thermal 0.74 and coupling 4.6, at single-cell jumps in kae's plane-height raster lookups.
- **Budgeted maps used in the runs (0.3 s):** thermal unchanged; coupling 94% of cells ≤5%.
- **kae finding:** on olimex (λ 53 mm, larger than the 51 × 36 mm box), kae's rings = 1 plus tail gives G 35–40% below the full Neumann lattice (25.3 against 39.1 K/W). The note's "rings = 1 converged" does not hold there.

## Results (ab33, budget 120, 3 seeds)

- **Columns:**
  - Physics is method/human gmean on phys10, mean of seeds 0/1/2.
  - Length and vias are seed 0.
- **lv pair:** phys_w = 0 never consults the maps, so its code equals the baseline. It is a noise replicate, with physics from seed 0 only.

| Run | Legal | Clean | Best-of-3 | Compl. | Length | Vias | Fast phys | Routed phys |
|---|---|---|---|---|---|---|---|---|
| xf-base-jc-ab33 | 0.899 | 0.657 ± 0.035 | 0.727 | 0.897 | 3111 | 76 | 0.97 (1.08/0.91/0.91) | 0.96 (0.88/1.06/0.94) |
| xfB-jc-ab33 | 0.899 | 0.606 ± 0.080 | 0.697 | 0.898 | 3296 | 76 | **0.80** (0.86/0.82/0.72) | 1.17 (1.18/1.29/1.04) |
| xfB-base-jc_full-ab33 | 0.879 | 0.606 ± 0.052 | 0.667 | 0.900 | 3026 | 57 | 0.82 (0.82/0.75/0.90) | 0.93 (0.84/1.00/0.94) |
| xfB-jc_full-ab33 | 0.889 | 0.606 ± 0.030 | 0.667 | 0.901 | 3015 | 49 | 0.88 (0.92/0.88/0.83) | 0.99 (0.95/1.00/1.01) |
| xf-base-jc_lv_nopol-ab33 | 0.879 | 0.616 ± 0.046 | 0.697 | 0.900 | 3298 | 79 | 2.31 | 1.16 |
| xfB-jc_lv_nopol-ab33 | 0.879 | 0.606 ± 0.030 | 0.667 | 0.900 | 3371 | 83 | 2.69 | 1.25 |

- **jc:**
  - **Fast physics −17%, lower on every seed.** Coupling, commutation and thermal all fall.
  - **Routed physics +22%, worse on every seed.** It is also no better on boards with no open hop.
- **jc_full:** worse on both physics numbers (+7% fast, +6% routed); DRC unchanged.
- **Noise is large.** With identical code, the lv replicate differs by 16% (fast) and 8% (routed).
- **Map CPU share** on phys boards is 5–67%, median about 13%. The maps cost CPU rather than freeing it.

## Verdict: no merit

- **The criterion fails.** Fast physics is lower by ≥5% only in jc, and routed physics gets worse there on all seeds. jc_full improves neither.
- **Likely cause:** a sharper argmin of the place terms over-fits their straight-hop model, and the router does not realise it.

Scorecard row:

| T2 | Exact physics maps (DCT thermal, kae kernels compiled over the grid) replacing `coarse_map` in jc's lift, best response and polish | Green's functions, spectral Poisson | `jc_x`, `jc_full_x` (xf_physmap) vs xf-base-jc / jc_full, 3 seeds | No merit | jc fast physics 0.97→0.80× human (−17%, all seeds) but routed 0.96→1.17× (worse, all seeds); jc_full worse on both (+7% / +6%); gate passed (p95 thermal 0.3%, coupling 0.3%); maps used 5–67% of CPU |
