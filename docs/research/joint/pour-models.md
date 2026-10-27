# Pour models: minimal-partition (soap-film) pours, and pour-damage maps in jc

**Status:** minimal-partition pours did not work; layer-coupled pour-damage maps worked on the physics objective (needs confirming).
**First published:** 2026-10-24, commit [014cf29](https://github.com/magnetic-trowel/kicad-auto-everything/commit/014cf29fb3604d6c15b36cc2295509de7ae3bc56) on branch `claude/keen-wright-mlkjv6` (pours; final [e0a8cab](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e0a8cabaef167886085dbf28bd5a47fa415e4835)); pour-damage maps [553ae9f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/553ae9fe88141481bd998d1c9976b4a5952f6538), results [ecaa86a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ecaa86a78322c0fdcd1021568a3e29185d6aacfd).

Copper pours carry power and return current, so their shape and the holes parts punch into them matter.
Drawing pours as minimal partitions (soap films) did not beat KiCad's fill. Pricing how much a part or
track would raise a pour's resistance — a first-order damage map from the pour's potential — and feeding
that into jc lowered pour resistance by 16% and routed physics with completion held.

## Minimal-partition and Wulff pours

**Mechanism** (`collapse_pour/`). When several pour nets share a layer, compute the minimal partition of
the free area: constant-curvature arcs, 120° triple junctions, 90° at the board edge.
- Multiphase Esedoglu–Otto MBO threshold dynamics: convolve each phase's indicator with a kernel,
  threshold to the largest. Volume targets are met exactly by coordinate ascent on per-phase multipliers.
  Pads are pinned to their net's phase; per-phase allowed masks enforce clearance.
- Kernels: Gaussian (isotropic; Wulff shape = disc) or "octagon": four 1-D Gaussians along 0 / 45 / 90 /
  135° (Wulff shape = regular octagon, for 45° copper).
- Written back to KiCad as zone copies with new outlines, refilled, DRC-checked. Scored by whole-net 3-D
  Laplace resistance (`netcond.py`; pads as terminals, vias conducting between layers;
  R_eff = 1 / mean(1 / R_ij) over pad pairs).
- Placement term `pour_place.py:pour_score`: ideal-sheet pad-pair resistance
  [ln(d / a_i) + ln(d / a_j)] / 2π, divided by the free fraction of the band between the pads.

**Results** ([collapse_pour/RESULTS.md](../../../tools/research/collapse_pour/RESULTS.md),
[summary-final.md](../../../tools/research/collapse_pour/summary-final.md)):
- Synthetic geometry matches theory: junction angle error falls from 3.3° to 0.45° with grid
  refinement; the octagon Wulff shape is reproduced ([synth_results.json](../../../tools/research/collapse_pour/synth_results.json)).
- Real boards (21 pour nets on 6 boards): R_eff vs the human pours, gmean 1.045 (fill mode), 1.033
  (equal area), 1.011 (octagon). Interleaved rails (the kobold keyboard's 4-rail inner layer) fail:
  17–18 unconnected items vs 0.
- Placement study: full pour R_eff (ratio to human) tracks kae routed physics at Spearman 0.65; the cheap
  `pour_score` only at 0.11. combo's placements give better pours than the human ones (R_eff 0.897×).

**Verdict: did not work.** Perimeter minimization is the wrong objective for conductance: what matters is
how close the copper comes to the pads that inject current. That lesson led to the damage maps below.
Not a merit arm.

## Pour-damage maps in jc (T4)

**Mechanism** (`xf_pour/pourmap.py`, `pjc.py`).
- For each pour net, solve the pour's potential v once on a 0.4 mm grid: region = zone ∩ board minus
  foreign halos, pads equipotential terminals, R_eff = 1 / mean(1 / R_ij).
- Dirichlet / Thomson principle: removing a set S of copper lowers the conductance by at least
  ∫_S σ |∇v|². The energy density E = σ |∇v|² is therefore a first-order (lower-bound) damage map: the
  relative increase of the net's pour R_eff per removed 0.1 mm cell.
- A part's damage over all its positions is the FFT correlation of its mask (its foreign-pad halos) with
  E, like the engine's legal maps.
- **Layer coupling** (`coupled=True`, `pjc2`): one sparse solve per net over all its pour layers; a
  plated pad is one terminal on all its layers; the net's routed vias link consecutive pour layers with
  netcond's conductance `VIA_G` · (L − 1) / gap. This covers B.Cu pours fed only through vias, which the
  per-layer model (`pjc`) cannot.
- Use in jc: the map enters part best responses (weight `pour_w`) and router cell costs (`route_w`),
  refreshed every jc iteration (0.02–0.3 s per coupled refresh). K = `pour_w` = `route_w` = 100 mm of
  wire per 100% increase in pour R, fixed by a dev6 sweep over K ∈ {30, 100, 300} before any ab33 run.

**What we tried.** Gate: 6 phys10 boards, 40 random cut-outs per pour (640 in all), each a real part's
foreign-pad halo, against exact re-solves. Then xf round 3: fixed engine 4c4330a, ab33 joint tasks, 120
CPU-s, 3 seeds, against fresh `xf3-base` jc baselines. Round 1 (place tasks, older engine) and round 2
(stopped when the engine fix landed) are not comparable.

**Results** ([xf_pour/RESULTS.md](../../../tools/research/xf_pour/RESULTS.md)):
- Gate: coupled maps pooled ρ ≥ 0.963 on every board, 15 of 16 pours ≥ 0.9; per-layer maps misrank
  via-fed layers under the coupled truth (ρ 0.04 on paw3395 B.Cu). Maps are lower bounds: median
  exact / predicted 2.1–3.6×.
- ab33, mean ± sd over 3 seeds; physics phys10 × human; pour R over 23 (board, net) pairs as gmean ratio
  to the baseline:

| run | legal | clean | completion | fast phys | routed phys | pour R / base (better / worse) |
|---|---|---|---|---|---|---|
| base jc | 1.000 | 0.687 ± 0.017 | 0.935 | 0.96 ± 0.08 | 1.18 ± 0.08 | 1 |
| pjc (per-layer) | 1.000 | 0.697 ± 0.030 | 0.937 | 0.90 ± 0.12 | 1.12 ± 0.07 | 0.939 (11/9) |
| **pjc2 (coupled)** | 1.000 | **0.707 ± 0.046** | 0.936 | **0.88 ± 0.05** | **1.05 ± 0.05** | **0.839** (14/6) |
| base jc_lv_nopol | 0.990 | 0.677 ± 0.035 | 0.942 | 1.92 ± 0.50 | 1.26 ± 0.05 | 1 |
| pjc_lv_nopol | 0.990 | 0.707 ± 0.017 | 0.940 | 2.02 ± 0.55 | 1.15 ± 0.06 | 1.123 (10/9) |
| pjc2_lv_nopol | 1.000 | 0.727 ± 0.000 | 0.939 | 2.46 ± 0.30 | 1.15 ± 0.13 | 0.985 (10/10) |

- pjc2 pour R per seed 0.89 / 0.89 / 0.74 (below 0.9 on every seed); against human, pour R is 1.43× for
  base jc and 1.20× for pjc2. All 396 attempts ran; DRC error types match the baselines'.

**Verdict: worked on the physics objective, needs confirming.** pjc2 meets all three pre-set criteria
(pour R ≤ 0.9× baseline, lower routed physics, completion held). Caveats: the routed-physics gap is about
1.6 pooled sd, on 10 boards and 3 seeds; K was not re-tuned on the fixed engine; dev6 had only 3 pour
pairs. `pjc2_lv_nopol` fails the pour criterion (0.985×) although clean and routed physics improve, and
per-layer maps fail (0.939×, 1.123×). Next: a larger pour suite, more seeds, K re-tuned.

`pjc2` and `pjc2_lv_nopol` are arms of the merit list; the 500-board comparison (`merit-500r3` /
`merit-500r3k`) is running. Results on the 500-board comparison: pending.

## Code

- [`tools/research/collapse_pour/`](../../../tools/research/collapse_pour/): `mbo.py`, `synth.py`,
  `geom.py`, `board.py`, `kicad_dump.py`, `netcond.py`, `pour_place.py`, `summarize.py`;
  `synth_*.json` and `fig/synth.png` are synthetic. Figures of real boards are not published (they
  render third-party boards); `summarize.py` regenerates them.
- [`tools/research/xf_pour/`](../../../tools/research/xf_pour/): `pourmap.py` (`PourMaps`,
  `solve_stack`), `pjc.py` (`pjc`, `pjc2`, `*_lv_nopol`), `gate.py`, `pour_score.py`,
  `sweep_table.py`, `runs.sh`, `sweep.sh`. Uses `collapse_pour/netcond.py`.
- Boards named above are from the public corpus listed in the benchmark manifest (olimex dcdc, kobold,
  xerxes, oasis, bentwire usb-c, pi5-pcie, caffeinated-a, paw3395); per-board numbers are summary data,
  not board geometry.

## Related

[jc.md](jc.md), [jc-extensions.md](jc-extensions.md), [layer-collapse-analysis.md](layer-collapse-analysis.md),
[untested-ideas.md](untested-ideas.md) (T11 extremal-length bounds, T12 parametric min-cut splits),
idea: [layer-collapse.md](../../ideas/original/layer-collapse.md).
