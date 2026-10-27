# Layer collapse as analysis: layer-count bounds, exact layer assignment, collapse terms in placement

**Status:** did not work, with narrow partial results (BGA escape formula; bus pin-order LDS; lifted cost as a placement measure).
**First published:** 2026-10-24, commit [014cf29](https://github.com/magnetic-trowel/kicad-auto-everything/commit/014cf29fb3604d6c15b36cc2295509de7ae3bc56) on branch `claude/keen-wright-mlkjv6` (assign results [d1ea2c9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d1ea2c93150c3dc4df27bf0b511b6856ca9521ce); placement terms [e55d880](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e55d880d62b400dafeda64c771d763fedf44f1ca), results [62d3e6e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/62d3e6e06593d9e5da8de3f05c48e8ebe58e8eed)).

The [layer-collapse idea](../../ideas/original/layer-collapse.md): give every net its own layer, then
collapse the stack into the board's L layers, mapping each piece to a problem with exact answers
(graph thickness, cut capacity, planar max-cut via minimization, Robinson–Schensted–Knuth (RSK) shapes).
Three studies tested the static pieces: as layer-count predictors, as a router, and as placement terms.
None worked as built; the *dynamic* version, where parts and nets collapse together, is [jc](jc.md).

## Layer-count bounds (`collapse_obst`)

**Mechanism.** On 112 human boards, with track pitch p = w + c (width + clearance):
- **Capacity cuts.** Nets with pads on both sides of a cut γ must cross it:
  N(γ) ≤ Σ_l ⌊(ℓ_free,l + c) / p⌋, the sum over layers of tracks that fit in the free length of γ.
  Cuts: 24k straight chords, grid circles, rings around every part.
- **Topology.** Euler / graph thickness; with vias any netlist fits on 2 layers.
- **Area.** 0.824 · MST · p + pad area ≤ L · A.
- **BGA escape.** t = ⌊(P − D − c) / p⌋ tracks per channel between balls (pitch P, pad D) gives
  rows escaped per layer.
- **Bus orientation.** Part pairs joined by ≥ 4 two-pin nets: the longest decreasing subsequence of the
  pin permutation (more generally the RSK shape) gives how many nets can share a via-free layer.
- API `placecost.py`: `capacity_overflow`, `bus_pairs`, `bus_lds`.

**Results** ([collapse_obst/RESULTS.md](../../../tools/research/collapse_obst/RESULTS.md)):
- Sound bounds never exceed 2 layers (capacity forces 2 on 2 boards, never 3); real layer counts are
  planes plus BGA escape.
- Escape formula: within ±1 of the signal-layer count on all 7 fine-pitch BGAs (3 times one above).
- For 4+ vs 2 layers, max cut demand has AUC 0.77, no better than plain pad density (0.79).
- Buses (240 on 55 boards): the human rotation pair is LDS-optimal for 60% of buses vs 42% for random;
  LDS-optimal rotations would cut forced 2-layer jumpers from 209 to 78.

**Verdict.** No merit as a layer-count predictor; narrow merit for the BGA escape formula; bus LDS
partial (see placement terms below).

## Exact layer assignment as a router; lifted cost as a placement measure (`collapse_assign`)

**Mechanism.**
1. **Lift.** Each net is A*-routed alone on one virtual layer against static blocks and pads; cells
   blocked on all layers are hard, cells blocked on some layers cost +1 and are recorded as forbidden.
   "spread" adds 2 rounds of single-layer negotiation.
2. **Conflicts.** Lifted centrelines closer than the halo. Paths are cut into runs of constant
   signature (conflicting nets + forbidden layers); runs are the variables.
3. **Assign.** Hadlock/Pinter via-minimization energy: 10 per layer change, 1000 per unresolved conflict
   or forbidden layer, 5 per plane-net run off its plane. Solved exactly by CP-SAT per connected
   component (Boolean at L = 2, one-hot at L = 4), or by Potts annealing.
4. **Realize.** +β history on the non-assigned layers within 1 mm of the lifted path, then
   PathFinder (40 passes) + legalize.

`lifted.py:LiftedConflicts` exposes the lifted cost with incremental `update` for placement use.

**Results** ([collapse_assign/RESULTS.md](../../../tools/research/collapse_assign/RESULTS.md); v5 route
tasks on ab33 human placements):

| run | A clean | B clean | all clean | completion | vias | length mm |
|---|---|---|---|---|---|---|
| engine `route_only` | 0.846 | 0.50 | 0.636 | 0.924 | 173 | 8116 |
| collapse, exact assignment | 0.769 | 0.50 | 0.606 | 0.937 | 186 | 8413 |
| collapse, spread | 0.769 | 0.50 | 0.606 | 0.922 | 168 | 8214 |
| **collapse, random assignment (control)** | **0.923** | 0.50 | **0.667** | 0.917 | 193 | 8352 |

- CP-SAT proved the assignment optimal on 33/33 boards (≤ 24 s); Potts annealing on 9/33.
- Lifted geometry predicts 2.8× the realized vias; conflicts are mostly corridor sharing, which the
  router resolves by detours, not layer changes.
- Placement study (219 placements): within-board Spearman ρ of predictors vs routed cost
  (length + 2 · vias + 20 · unrouted): HPWL 0.51, lift forced vias 0.42, **spread cost 0.85**. Nothing
  predicts unrouted connections (ρ ≈ 0).

**Verdict.** The router did not work: an *optimal* assignment did no better than a random one. The
lifted spread cost is a promising placement measure (ρ 0.85 vs 0.51); using it as an annealing move
cost was proposed and not done.

## Collapse quantities as placement terms (`collapse_cplace`)

**Mechanism** (`terms.py:CollapseTerms`).
- **fv**: forced vias of buses (part pairs with ≥ 3 two-pin nets): pins projected across the gap,
  fv = n − (λ1 + … + λL) of the RSK shape; 0.1 ms per bus.
- **x**: crossings of ratsnest MST segments (idea 25).
- **ovf**: cut-capacity overflow on Delaunay edges ≤ 4 mm between pads (~5 ms).
- Used in the beam child score, beam candidate order and repair / anneal acceptance (`combo_collapse`),
  or as a descent on HPWL + physics + terms over the top-4 candidates (`seq_collapse`). Weights w_fv =
  4 mm, w_x = 1 mm, w_ovf = 0.

**Results** ([collapse_cplace/RESULTS.md](../../../tools/research/collapse_cplace/RESULTS.md); v5,
ab33, 3 seeds):

| method | legal | clean (per seed) | completion | length | vias | fast phys | routed phys |
|---|---|---|---|---|---|---|---|
| combo | 0.859 | 0.596 (.64/.61/.55) | 0.897 | 8923 | 85 | **1.03** | **1.13** |
| combo_collapse | 0.838 | 0.606 (.61/.61/.61) | 0.893 | 9028 | 94 | 1.23 | 1.36 |
| seq | 0.788 | 0.556 | 0.855 | 10223 | 187 | 4.05 | 1.39 |
| seq_collapse | 0.788 | 0.505 | 0.858 | 10180 | 194 | 1.45 | 1.22 |

- `combo_collapse` vs `combo`: crossings 372 vs 421, fv 4 vs 6, overflow 8 vs 62 — but output-board vias
  118 vs 117.
- `seq_collapse`'s clean losses are all `starved_thermal`. Bus vias drop 22 → 12 in `seq` (outside the
  joint loop).

**Verdict.** No merit. The proxies drop and the routed vias do not: the router already avoids the vias
these terms predict, and the terms pull against physics.

`seq_collapse --opt w_fv=4 w_x=1 w_ovf=0` is nevertheless an arm of the merit list; the 500-board
comparison (`merit-500r3` / `merit-500r3k`) is running. Results on the 500-board comparison: pending.

## Code

- [`tools/research/collapse_obst/`](../../../tools/research/collapse_obst/): `obst.py`, `placecost.py`,
  `placements.py`, `report.py`, `run_all.py`. The heat-map figures are not published (they render
  third-party boards); `report.py` regenerates them.
- [`tools/research/collapse_assign/`](../../../tools/research/collapse_assign/): `collapse.py` (router
  plug-in), `lifted.py`, `analyze.py`, `placement_study.py`. Needs `ortools`.
- [`tools/research/collapse_cplace/`](../../../tools/research/collapse_cplace/): `terms.py`,
  `methods_cplace.py`, `methods_cplace_lv.py`, `diag.py`, `diag_report.py`, `summarize.py`,
  `run_cplace.sh`.

## Related

[jc.md](jc.md) (the dynamic collapse that worked), [pour-models.md](pour-models.md) (the pour piece of
layer collapse), [learn_value features](jc-extensions.md#learned-value-of-partial-boards),
literature: [analogs.md](../../../research_notes/layer-collapse/analogs.md).
