# Extensions of jc: harmonic pressure, learned value, quality-diversity, min-plus maps, exact physics maps

**Status:** harmonic routing did not work, harmonic pressure ties jc (partial); learned value did not work; QD archive did not work vs jc; min-plus maps inconclusive (leans merit on vias); exact physics maps did not work.
**First published:** 2026-10-24, commit [b2bcf8c](https://github.com/magnetic-trowel/kicad-auto-everything/commit/b2bcf8cbfebb19e6a0bd5159eff4b8629ae32131) on branch `claude/keen-wright-mlkjv6` (harmonic, learned value, QD); [093823b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/093823b1b66ff5267f37a19cce72192bdfd1455a) (min-plus); [553ae9f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/553ae9fe88141481bd998d1c9976b4a5952f6538) (exact physics maps). Results: [57eee2c](https://github.com/magnetic-trowel/kicad-auto-everything/commit/57eee2ca29927de258dab0d16f3e24a0ebe92979), [db10e58](https://github.com/magnetic-trowel/kicad-auto-everything/commit/db10e580a68863f09641244e432c401f5a293348), [ecaa86a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ecaa86a78322c0fdcd1021568a3e29185d6aacfd).

Five attempts to improve [jc](jc.md) by changing one of its parts: what the parts feel (harmonic
pressure, min-plus maps, exact physics maps) or how restarts are spent (learned value, quality-diversity
archive). None clearly beat plain jc. Min-plus maps reduced vias on every seed and went into jc2.

**Comparability.** Harmonic, learned value and QD are v7 runs (engine v6.3, 3 seeds) against v7 jc
baselines that were **stopped at 88 / 99 (jc) and 94 / 99 (jc_lv) attempts**, so they compare on the
boards where both have all seeds. Min-plus and exact maps are xf round 3 runs (fixed engine 4c4330a, 3
seeds, all 33 boards) against fresh `xf3-base-*` baselines. The two sets are not comparable with each
other or with v5 numbers.

## Harmonic-field routing and field pressure

**Mechanism** (`harmonic/`, idea 19). Per net, a resistor network on a 0.4 mm grid per layer (via edges
× 0.2): fine-cell conductance 1 / (1 + hist + β · foreign), coarse cells take the block mean, cells
< 0.02 are removed (Neumann walls). The pin nearest the centroid is held at φ = 1, others at 0; sparse
LU on the bounding box + 4 mm (60–80 ms per net). Three uses in jc:
- `stream`: the steepest-ascent streamline tree is the route;
- `bias`: a corridor around the streamline tree biases A*;
- `press`: each part pays for other nets' expected occupancy |J| / I under its pads (a Maxwell-stress
  analogue), price capped at β = 2.

**Results** ([harmonic/RESULTS.md](../../../tools/research/harmonic/RESULTS.md)):
- Streamlines on 33 human placements: 974 of 980 sinks reached, but only 49.5% of connections
  clearance-legal, legal ones 1.45× A* length, 56× A* CPU. Inside jc they never converged.
- Congestion signal: summed |J| / I predicts the router's copper better than RUDY (Spearman 0.26 vs 0.18,
  better on 23 of 33 boards).
- v7, 28 boards, 3 seeds: `hjc_press` legal 0.988, clean 0.714 ± 0.036, completion 0.935 vs `combo`
  0.917 / 0.667 / 0.935; routed physics 1.16 / 1.10 / 1.08 per seed vs combo 1.29 / 1.23 / 1.30.
- vs jc on the 24 boards jc finished: clean 0.667 ± 0.042 vs 0.694 ± 0.062; `hjc_press_lv` 0.694 vs
  `jc_lv` 0.722.

**Verdict.** Router: did not work. Pressure: ties jc within seed spread (partial). Worth keeping only as
an obstacle-aware congestion map. `hjc_press` is a merit-list arm.

## Learned value of partial boards

**Mechanism** (`learn_value/`, idea 32). Probe jc after the lift and after every β iteration of every
restart: 31 boards, 1569 restarts, 28,433 checkpoints, ~20 features at ~5 ms each (HPWL, fast physics,
routed length, vias, unrouted, routed cost, wire-history statistics, part history and overlap,
conflicts, moved parts, forced vias, crossings, overflow, β, time). Pairwise model: (restart a at
checkpoint c, restart b of the same board) → Δ log(1 + final cost), ridge and gradient boosting
(sklearn), 5 leave-boards-out folds. Policy: abandon a restart when its predicted Δ against the
incumbent exceeds a margin chosen on other folds (nested), at most 3 abandons in a row, time spent
charged.

**Results** ([learn_value/RESULTS.md](../../../tools/research/learn_value/RESULTS.md)):
- Within-board Spearman with the final restart cost: at the lift ≤ 0.12 for every predictor; at
  iteration 5 the current routed cost alone gives 0.45, ridge 0.32, GBM 0.36.
- Simulated at equal CPU (60 bootstrap orders): an oracle at the lift buys only 3.3–3.8% (0.967 /
  0.962); learned ridge 0.996 / 1.002 (physics / lv objective).
- Harness (v7, 29 boards, 3 seeds): `jc_value` clean 0.667 ± 0.017 vs jc 0.655 ± 0.034, vias 53.7 vs
  57.7, legal 0.943 vs 0.954.

**Verdict: did not work.** jc's restarts are nearly exchangeable early on, so even perfect pruning is
worth little. The data predates engine v6. The trained models are not published (pickles execute code
on load); `lv_model.py` re-trains them from `lv_gen.py` data.

## Quality-diversity archive (MAP-Elites)

**Mechanism** (`qd_archive/qd.py`, idea 16). Two plain jc continuations seed the archive. Each further
candidate restores a uniformly chosen elite, mutates it (`shift`: k nearest parts move ≤ 3 mm, rotate
with p = 0.3; `rot`; `swap`; k ∈ {1, 2, 3, 15% of parts}), runs a short jc continuation with no lift and
β₀ log-uniform in 0.3–6 (sets the mutation strength), legalizes, routes, inserts. Descriptors: part
spread × vias, log-binned. `qdh`: half the candidates are fresh restarts. Pick: lowest routed cost +
`phys_w` · physics; 15% polish as in jc.

**Results** ([qd_archive/RESULTS.md](../../../tools/research/qd_archive/RESULTS.md); v7, 3 seeds):
- Paired with jc (88 attempts): legal 0.955 both, clean 0.682 vs 0.659 (noise), +1–2% copper, vias 221
  vs 228. `qd_lv` vs `jc_lv` (94 pairs): clean 0.660 vs 0.702.
- vs `combo` on ab33: legal 0.960 vs 0.869, clean 0.717 vs 0.657, routed physics 1.18 vs 1.27.
- Archive ~8 cells per board; on large boards only 2–3 continuations fit in 120 CPU-s, so the archive
  barely differs from jc's restarts; on small boards fresh restarts reach basins that mutations do not.

**Verdict: did not work vs jc** (beats combo, inherited from jc). `qd` is a merit-list arm.

## Min-plus best-response maps (T1)

**Mechanism** (`xf_minplus/minplus.py`). On jc's β-priced grid (cell cost (1 + hist)(1 + β · foreign),
vias priced as the router does), for each (net, moving part): a numba multi-source Dijkstra from that
net's pins on *other* parts, min-pooled to 0.4 mm. The part's map = Σ over its nets of the min over its
pads of the field shifted by the pad offset (a tropical / min-plus convolution), bilinearly upsampled;
unreachable = board perimeter. `MPCollapse` blends it with jc's HPWL + tension term by `minplus_w`
(1 or 0.5). Gate (`validate.py`): within-part Spearman of predictors vs re-routed cost on sampled moves.

**Results** ([xf_minplus/RESULTS.md](../../../tools/research/xf_minplus/RESULTS.md)):
- Gate, dev6, 2268 moves: ρ 0.82 vs HPWL 0.79 vs jc term 0.78 (paired +0.030, CI +0.002…+0.059);
  argmin regret 0.74 vs 0.88 mm.
- xf3, ab33, 3 seeds, 396 attempts:

| run | legal | clean | completion | length mm | vias | routed phys |
|---|---|---|---|---|---|---|
| base jc | 1.000 | 0.687 ± 0.017 | 0.935 | 3945 | 90 | 1.18 ± 0.08 |
| mp w = 1 | 0.980 | 0.687 ± 0.035 | 0.939 | 3779 (−4.2%) | 75 (−17%) | 1.19 ± 0.11 |
| mp w = 0.5 (`xf_h`) | 1.000 | 0.687 ± 0.046 | 0.938 | 3711 (−5.9%) | 72 (−20%) | 1.18 ± 0.11 |
| base jc_lv_nopol | 0.990 | 0.677 ± 0.035 | 0.942 | 3465 | 61 | 1.26 ± 0.05 |
| mp lv w = 1 | 0.980 | 0.707 ± 0.017 | 0.942 | 3457 | 51 (−16%) | 1.43 ± 0.14 |
| mp lv w = 0.5 | 0.990 | 0.667 ± 0.030 | 0.940 | 3402 | 54 (−11%) | 1.20 ± 0.06 |

Vias fall 9–28% on every seed in all 4 arms (baseline via noise about ±9%), spread over ~10 boards.
Length gains ≥ 5% come from one board (noisecard); without it 0–3%.

**Verdict: inconclusive, leaning merit on vias.** Kept in jc2 (`minplus_w = 0.5` from β ≥ 1). An earlier
negative-distance bug (recorded in `NOTES.md`) was fixed and unit-tested against Bellman–Ford.
`xf_h` is a merit-list arm.

## Exact physics maps (T2)

**Mechanism** (`xf_physmap/physmap.py`). `ExactPhys(Phys).exact_map(part, rot)` evaluates `Phys.delta`
at every cell instead of sampling (`coarse_map`): thermal by a DCT-II Neumann screened-Poisson solve with
kae's G_s and λ; loop, coupling and common-mode terms by kae's `loop_core` / `eng_eval` compiled over the
grid in numba; decap, ESD and crystal in closed form. Nodes every 0.4 mm, bilinear interpolation, exact
refinement where curvature > 1%, a CPU budget per map. Used in jc's lift, polish and best-response
argmin (`jc_x`, `jc_full_x`) or lift / polish only (`*_xlp`); falls back to plain jc if maps exceed 35%
of CPU.

**Results** ([xf_physmap/RESULTS.md](../../../tools/research/xf_physmap/RESULTS.md); xf3, 3 seeds):
- Gate passed: p95 relative error thermal 0.3%, coupling 0.3%.
- ab33: `jc_x` fast physics 0.85 vs 0.96 (−11%), routed 1.11 vs 1.18; a phys10 replicate reversed it
  (pooled 6 attempts: −1% fast, −2% routed; identical-code noise ±0.08).
- `jc_full_x` routed physics 1.08 vs 0.98 for `jc_full`, worse on every seed; lift / polish only 1.05.
- Maps used 14–19% of CPU.

**Verdict: did not work.** Exact maps do not beat sampled maps once noise is accounted for. Side finding
for kae: the thermal approximation "rings = 1 + continuum tail" gives G 35–40% below the full lattice on
olimex. Not a merit arm.

`hjc_press`, `qd` and `xf_h` are arms of the merit list; the 500-board comparison (`merit-500r3` /
`merit-500r3k`) is running. Results on the 500-board comparison: pending.

## Code

- [`tools/research/harmonic/`](../../../tools/research/harmonic/): `field.py`, `stream.py`, `hjc.py`,
  `common.py`, `congestion.py`, `diag.py`, `fig_field.py`, `test_field.py`, `runj_harm.sh`.
- [`tools/research/learn_value/`](../../../tools/research/learn_value/): `lv_jc.py`, `lv_gen.py`,
  `lv_model.py`, `lv_policy.py`, `runj_wt.sh`.
- [`tools/research/qd_archive/`](../../../tools/research/qd_archive/): `qd.py`, `archive_stats.py`,
  `search_cost.py`, `seeds.py`, `runj_qd.sh`.
- [`tools/research/xf_minplus/`](../../../tools/research/xf_minplus/): `minplus.py`, `validate.py`,
  `gate_report.py`, `summarize.py`, `test_minplus.py`.
- [`tools/research/xf_physmap/`](../../../tools/research/xf_physmap/): `physmap.py`, `jc_x.py`, `gate.py`,
  `gate_summary.py`, `phys_seed.py`.
- Shared xf setup: [`xf_common/SETUP.md`](../../../tools/research/xf_common/SETUP.md), `xf_run.sh`.

## Related

[jc.md](jc.md), [pour-models.md](pour-models.md) (T4, the transformation that worked),
[untested-ideas.md](untested-ideas.md) (T3, T5–T12), plans:
[transformations.md](../../../research_notes/transformations/transformations.md).
