<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# xf B: exact physics maps (T2), round 3

Round 3 = round-2 protocol (joint tasks, sandbox, kae-work2) on the fixed pnr engine
(commit 4c4330a). Baselines: `xf3-base-jc-ab33`, `xf3-base-jc_full-ab33`
(`kae-work2/score/baselines-xf3.md`).

## Built

- **[physmap.py](physmap.py), `ExactPhys(Phys)`** (unchanged from round 1): `exact_map(pi, ri)`
  is `Phys.delta` at every cell. Thermal is a DCT-II Neumann screened-Poisson solve with kae's
  G_s and λ. Loops, coupling and CM run kae's `loop_core` / `eng_eval` over the grid in numba;
  decap, ESD and crystal are numpy closed forms. Nodes every 0.4 mm, bilinear, exact refinement
  where curvature exceeds 1%, with a CPU budget per map.
- **[jc_x.py](jc_x.py)** wraps `collapse_joint/jc.py` without editing it:
  - `jc_x`, `jc_full_x`: exact maps in the lift and polish (0.3 s per map), and in the
    best-response argmin (phys_w·map/g, 0.05 s per map; top candidates still re-scored
    with `Terms.delta`; falls back to plain jc if maps exceed 35% of CPU).
  - **New this round, mitigation `jc_xlp` / `jc_full_xlp`** (`br_maps=False`): exact maps
    only where jc already used `coarse_map` (lift, polish). Best responses are jc's own.
    jc_full has no polish, so `jc_full_xlp` changes only the lift.
- **phys_w = 0 (`jc_lv_nopol`) never consults the maps**, so its code is the baseline. It was
  not re-run.
- [gate.py](gate.py), [gate_summary.py](gate_summary.py) (now skips budgets with no files).
  [phys_seed.py](phys_seed.py) is superseded by `xf_common/physics_score_xf.py`.

## Gate (phys10, re-extracted with the fixed engine's kicad_io; human + random placement, 500 cells per part and rotation)

e = |map − delta| / max(|delta|, 10⁻³). The physics engine (`kae-phys`, ff641dd) has not
changed since round 1, and `pnr/physics.py` is untouched. The gate was re-run on both the
v6.1 engine and the fixed engine. The results are identical to round 1 at full resolution.

| Term | n | Median | p95 | p99 | ≤1% | ≤5% | p95 at 0.3 s budget |
|---|---|---|---|---|---|---|---|
| thermal | 24k | 9.4e-5 | 3.2e-3 | 1.4e-2 | 0.984 | 0.997 | 3.2e-3 |
| coupling | 72k | 5.6e-6 | 2.9e-3 | 1.0e-2 | 0.990 | 0.999 | 5.7e-2 |
| world_cm | 60k | 1.1e-5 | 8.6e-3 | 6.5e-2 | 0.958 | 0.988 | 6.1e-2 |
| decap | 240k | 6.6e-5 | 3.4e-3 | 1.9e-2 | 0.980 | 0.997 | 4.1e-3 |
| commutation | 36k | 3.6e-6 | 5.0e-3 | 3.6e-2 | 0.971 | 0.993 | 4.4e-2 |
| esd | 16k | 2.7e-6 | 4.4e-4 | 2.1e-3 | 0.997 | 0.998 | 8.2e-4 |

**The gate passes:** thermal p95 0.3% (limit 1%), coupling 0.3% (limit 5%). Median map CPU is
0.15 s per part-rotation. In the runs, maps took a median of 14% of CPU on the phys boards
(range 0–50%) for jc_x, and 19% (0–65%) for jc_full_x.

## Results (joint, ab33, budget 120, 3 seeds; scored by kicad-cli and physics_score)

Legal, clean and completion are mean ± sd over seeds. Length and vias are summed over the
25 boards every run in the table completed. Physics is method/human gmean on phys10
(lower is better), mean ± sd, with per-seed values in brackets.

| Run | Legal | Clean | Best-of-3 | Compl. | Length | Vias | Fast phys | Routed phys |
|---|---|---|---|---|---|---|---|---|
| xf3-base-jc-ab33 | 1.000 ± 0.000 | 0.687 ± 0.017 | 0.758 | 0.935 | 3559 | 57 | 0.96 ± 0.08 (1.05/0.92/0.91) | 1.18 ± 0.08 (1.09/1.21/1.23) |
| xf3B-jc-ab33 | 0.990 ± 0.017 | 0.667 ± 0.052 | 0.727 | 0.938 | 3569 | 51 | 0.85 ± 0.05 (0.80/0.89/0.85) | 1.11 ± 0.03 (1.13/1.13/1.08) |
| xf3-base-jc_full-ab33 | 0.990 ± 0.017 | 0.677 ± 0.076 | 0.758 | 0.940 | 3571 | 64 | 0.92 ± 0.08 (0.86/0.88/1.01) | 0.98 ± 0.04 (0.95/1.03/0.98) |
| xf3B-jc_full-ab33 | 0.990 ± 0.017 | 0.667 ± 0.061 | 0.727 | 0.943 | 3601 | 65 | 0.95 ± 0.17 (1.08/0.76/1.02) | 1.08 ± 0.05 (1.12/1.10/1.02) |
| xf3B-jc_full_xlp-ab33 | 1.000 ± 0.000 | 0.707 ± 0.035 | 0.758 | 0.944 | 3561 | 68 | 0.96 ± 0.05 (0.97/1.01/0.92) | 1.05 ± 0.09 (0.96/1.15/1.05) |

The jc_full_xlp row comes from a separate score (`xf3B-mit.md`), so its length and vias
are over that table's common boards. The base jc_full row reads the same in both.

**Replicate (phys10 only, same code, 3 more attempts each).** On ab33, jc_x looked like it
met the criterion, so jc_x and baseline jc were re-run on phys10 (`xf3B-rep-*-p10`):

| Run | Clean (phys10) | Fast phys | Routed phys |
|---|---|---|---|
| xf3B-rep-jc-p10 (baseline code) | 0.600 ± 0.000 | 0.88 ± 0.06 (0.91/0.81/0.93) | 1.12 ± 0.09 (1.15/1.01/1.19) |
| xf3B-rep-jc_x-p10 | 0.600 ± 0.000 | 0.98 ± 0.03 (0.96/1.01/0.96) | 1.13 ± 0.02 (1.13/1.14/1.11) |
| **pooled 6 attempts, jc** | | **0.92** | **1.15** |
| **pooled 6 attempts, jc_x** | | **0.91 (−1%)** | **1.12 (−2%)** |

- **jc_x:** on ab33, fast physics −11% (lower on all three seeds) and routed −6% (better on
  2 of 3 seeds). The replicate reverses it: jc_x is +11% on fast physics. Baseline code alone
  moved 0.96 → 0.88 between two runs. Pooled over 6 attempts, the gain is −1% fast and −2%
  routed, well inside the noise. One effect does look stable: routed sd for jc_x is 0.02–0.03,
  against 0.08–0.09 for jc. DRC is unchanged within noise, with vias −6 on ab33.
- **jc_full_x:** fast +3% and routed +10%, worse on all seeds (1.12/1.10/1.02 against
  0.95/1.03/0.98).
- **Mitigation jc_full_xlp** (exact maps in the lift only): routed +7% and fast +4%, so it is
  no better than jc_full_x. Clean 0.707 against 0.677 is within seed noise.
- **Old-engine phys10 scratch**, same code: `xf2B-p10-*`, scored as `kae-work2/score/xf2B-p10.md`.
  jc_x was −1% fast against jc, and jc_xlp +7% fast and +4% routed. That agrees with the pooled
  numbers above.

## Verdict: no merit

The criterion fails. Pooled over 6 attempts, jc_x's fast physics is about 1% lower, not
≥5%. The −11% on ab33 did not replicate, and the run-to-run spread of identical code (±0.08)
is as large as any effect. With jc_full, exact maps make routed physics worse (+10%), and the
lift-only mitigation does not recover it (+7%). Round 1 found the same pattern. Exact maps
pass the gate, and they sharpen the place terms the optimizer sees. That does not show up as
better routed physics, because the router does not realise the place terms' straight-hop model.
The −6 vias and the lower routed variance with jc_x are the only hints of a benefit, and both
would need more seeds.

**kae finding (round 1, still true):** on olimex (λ 53 mm, larger than the 51 × 36 mm box),
kae's thermal rings = 1 plus continuum tail gives G 35–40% below the full Neumann lattice.

## Runs and files

- **Round 3 (fixed engine):** `xf3B-jc-ab33`, `xf3B-jc_full-ab33`, `xf3B-jc_full_xlp-ab33`,
  `xf3B-rep-jc-p10`, `xf3B-rep-jc_x-p10`.
  - Scores: `kae-work2/score/xf3B.md`, `xf3B-mit.md` and `xf3B-rep.md`.
  - Gate: `kae-work2/xfB/gate2-{none,0.3}-*.json`.
- **Old engine (v6.1, scratch only):**
  - `xf2B-jc-ab33` and `xf2B-jc_full-ab33` were killed partway on request.
  - `xf2B-p10-{jc_x,jc_xlp,jc_full_x}` and `xf2B-p10sub-base-*`, which are symlinks to
    phys10 boards of the xf2 baselines.
  - Old gate: `kae-work2/xfB/old/`.

Scorecard row:

| T2 | Exact physics maps (DCT thermal, kae kernels compiled over the grid) replacing `coarse_map` in jc's lift, best response and polish | Green's functions, spectral Poisson | `jc_x`, `jc_full_x`, `jc_full_xlp` (xf_physmap) vs xf3-base-jc / jc_full, joint ab33, 3 seeds + phys10 replicate | No merit | gate passed (p95 thermal 0.3%, coupling 0.3%); jc fast 0.96→0.85× on ab33 but replicate reversed it (pooled 6 attempts −1% fast, −2% routed, noise ±0.08); jc_full routed 0.98→1.08× (worse all seeds), lift-only mitigation 1.05×; maps used a median of 14–19% of CPU |
