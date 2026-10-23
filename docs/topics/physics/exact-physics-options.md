# Exact physics in the optimizer: what it costs and where it changes decisions

**TL;DR**
- **Before routing, "exact" means "route it, then solve it".** A field solver needs copper, so every exact evaluation of a placement first routes the structure's hops; routing is 85–95% of its cost, and the route style alone (any-angle or Manhattan) reorders ⟨R⟩% of candidate pairs, more than PEEC and the closed forms disagree on the same copper (⟨P⟩%) [C].
- **A drop-in exact `delta` is 10³–10⁴× slower:** 12–360 ms per move (median by board, one core) against 10–150 µs, i.e. 0.1–35 CPU-hours per board at today's move count, or ~1,000 moves inside today's budget [C/I].
- **Fast and exact order nearby candidates differently** in ⟨F⟩ of material pairs: ⟨decap⟩ decap, ⟨comm⟩ commutation, ⟨esd⟩ ESD, ⟨xtal⟩ crystal, ⟨coup⟩ coupling, ⟨th⟩ thermal. Loop flips come mostly from route detours; thermal flips from partial pours, which the fin kernel averages away [C].
- **Build first:** exact physics where copper exists (module stage on PEEC, post-route recheck on real-copper passports), and multi-fidelity selection (the place terms propose, routed PEEC chooses among the best three). Thermal gets an exact finite-volume Green's table, priced by lookups [C/I].
- **Skip** a global `--physics exact` switch and per-structure correction factors: the first costs 10³× for decisions inside the route noise; the second cannot change any ranking within a structure.

Tags: [C] computed by the `ex_*` scripts below on one core of the shared 4-core VM (load 9–19; CPU seconds; ±30%) on the human boards of the KiCad 10.0.7 suite; [I] arithmetic on [C] numbers or inference; [S] secondary. Fast terms: [place-terms](place-terms.md); rungs F1–F4: [solver-ladder](solver-ladder.md).

## 1. What was measured

**Evaluators** (`ex_exact.py`), all at the same poses:

| Name | Geometry | Physics |
|---|---|---|
| fast | straight pad-to-pad hops | place terms (F1) |
| detour | fast plus L′(w, h) × (routed − straight) per board hop | F1 on routed lengths |
| cf | each board hop routed on a 0.1 mm grid, any angle (Dijkstra, string-pulled), around other nets' pads and the loop's own copper | closed forms on routed pieces, the module stage's model (`critical_physics.Loop`) |
| cfm | the same, Manhattan routes with a turn penalty | same |
| PEEC | Manhattan routes | multi-filament PEEC over a PEC image plane, inductive limit (the validation's reference) |
| FV | the board's zones as placed | 2.5-D finite volume; heat into the part's outer layer (fv) or into every layer under it (fvs, a perfectly stitched footprint) |

Crystal: routed XIN/XOUT length × field-solver C′. Coupling: PEEC currents of the routed aggressor and the EMF along the routed victim; the capacitive part stays fast.

**Candidates** (`ex_decision_flips.py`): on all 112 boards, up to six parts per structure kind, each with its human pose, three legal 1–5 mm translations and the legal 90/180/270° rotations (the moves of [place-terms §8](place-terms.md#8-human-boards-does-the-physics-prefer-the-human-placement-c)). A **flip** is a pair of one part's candidates that two evaluators order differently, counted when the reference separates them by ≥ 1% of some structure's allocation.

## 2. Cost

| Structure | Fast: per move | Exact at placement, per evaluation | Real-copper model | Setup, memory | Growth |
|---|---|---|---|---|---|
| Hot loop | 0.37 ms (aggressor members), else 13–20 µs | cf 28 ms; PEEC 45 ms (100–300 filaments, ≤ 0.7 MB) | stack HF window: 12.5 s median, 2–107 s per cell | rasterize + factor per call; 0.6–3.3 GB | route ∝ cells^1.1–1.3; PEEC ∝ n^2.0 to n = 800; HF ∝ cells^1.6 |
| Decap loop | 19 µs | cf 7 ms; PEEC 14 ms | plane pairs: closed form within 0.4% of a sheet solve | — | as above |
| ESD path | 36 µs | cf 3.5 ms; PEEC 6 ms | — | — | as above |
| Coupling pair | 80 µs | 91 ms | MoM for the capacitive part | — | as above |
| Crystal | 170 µs | 8 ms of routes + C′ 0.1–1 s per new (w, h), then cached | — | — | per stackup |
| Thermal | 0.33 ms; full 0.05–0.5 ms | FV: one solve per moved source, 2–430 ms | — | factor 0.07–66 s at 6k–268k nodes; LU 4 MB–1.5 GB | factor ∝ nodes^1.4, solve ∝ nodes^1.2 |
| DC rail | none (no placement term) | — | DC passport 1.2 s per rail | factor 0.5 s median (121k nodes), 4.5 s max | ∝ nodes^1.1 |

Sources [C]: `ex_cost_table.py` on 11 boards (7–621 parts), `ex_scaling.py`; real-copper rows from [suite-physics-results](suite-physics-results.md) §3.

- **Routing is the cost.** Of the commutation cf evaluation's 28 ms, 26 ms is routing; PEEC adds 2–6 ms at 100–300 filaments (1.3 ms at 93, 75 ms at 783). Hops cost 0.8 ms (2 mm) to 99 ms (32 mm) any-angle, 1–240 ms Manhattan [C].
- **Per move.** Re-evaluating every structure the moved part belongs to costs 12–363 ms (median by board; p90 0.08–2.3 s) against 10–154 µs fast. At 4,000 moves per physics part that is 0.1 h (split A), 4–7 h (B), 1–35 h (C) of CPU instead of 0.1–290 s; the placer's 245 s budget would allow 700–11,000 exact moves [C/I].
- **Schur windows** (`ex_window_quotes.py`, whole-board DC operator of BLDCM-Power, 76k nodes, refactor 0.23 s): a 1,600-node window (4 × 4 mm, 4 layers) costs 2.6 s and 20 MB to build, a 6,400-node window 22 s and 312 MB. An exact quote of k changed branches costs 0.06 ms (k 8), 1.1–1.2 ms (128), 19–29 ms (512), 100–140 ms (1,024), within 10⁻¹³ of brute force; committing it costs 0.02–7 s [C]. A part move with its two hops changes k ≈ 10²–10³ branches at 0.1–0.2 mm cells [I].

## 3. Decision flips

⟨FLIP TABLE⟩

⟨FLIP TEXT⟩

## 4. Designs

⟨DESIGN TABLE⟩

⟨DESIGN TEXT⟩

## 5. Recommendation

⟨RECOMMENDATION⟩

## Conflicts and open questions

⟨OPEN⟩

## Sources

- Scripts [C]: [ex_exact.py](../../../tools/research/physics/ex_exact.py) (evaluators), [ex_cost_table.py](../../../tools/research/physics/ex_cost_table.py), [ex_scaling.py](../../../tools/research/physics/ex_scaling.py), [ex_window_quotes.py](../../../tools/research/physics/ex_window_quotes.py), [ex_decision_flips.py](../../../tools/research/physics/ex_decision_flips.py), [ex_surrogate.py](../../../tools/research/physics/ex_surrogate.py), [ex_thermal_table.py](../../../tools/research/physics/ex_thermal_table.py), [ex_polish.py](../../../tools/research/physics/ex_polish.py). They reuse [pw_peec](../../../tools/research/physics/pw_peec.py), [fe_field2d](../../../tools/research/physics/fe_field2d.py), [tm_board_thermal_fv](../../../tools/research/physics/tm_board_thermal_fv.py), [pt_human_perturb](../../../tools/research/physics/pt_human_perturb.py), [pt_grid_route](../../../tools/research/physics/pt_grid_route.py), [eng_board_scaling](../../../tools/research/physics/eng_board_scaling.py).
- Outputs (not committed; third-party boards): `kae-work/physics/exact-options/`.

See also: [place-terms](place-terms.md) · [solver-ladder](solver-ladder.md) · [physics-engine-design](../architecture/physics-engine-design.md) · [month-plan § joint loop](../architecture/month-plan.md#the-joint-loop-modules-routed-physics-re-tweak) · [suite-physics-results](suite-physics-results.md) · [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)
