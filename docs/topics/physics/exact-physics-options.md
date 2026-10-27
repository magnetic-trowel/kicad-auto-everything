# Exact physics in the optimizer: what it costs and where it changes decisions

**TL;DR**
- **Before routing, "exact" means "route it, then solve it".** A field solver needs copper, so an exact evaluation of a placement first routes the structure's hops. Routing is 83–94% of its cost, and the route style alone (any-angle or Manhattan) reorders 8–11% of candidate pairs, more than PEEC and the closed forms do on the same copper (0.3–3.3%) [C].
- **A drop-in exact `delta` is 10³–10⁴× slower:** 12–360 ms per move (median by board, one core) against 10–150 µs, i.e. 0.1–35 CPU-hours per board at today's move count [C/I].
- **Fast and exact order nearby candidates differently** in 15% of material decap and commutation pairs, 10% ESD, 19% crystal, 17% coupling and 26–30% thermal. For loops that is only 2–6 points above the route floor: before routing the reference is nearly as uncertain as the estimator. Exact values are missing for 44% of decap loop evaluations, mostly capacitors on the far side of the board [C].
- **Deciding by exact physics before routing gains little, noisily:** a greedy polish that chooses by PEEC ends 1.9% lower in exact cost than one choosing by the place terms (median of 10 boards), from 2.3× better to 1.8× worse per board. Correction factors and a learned residual remove almost no flips [C].
- **Build first:** exact physics where copper exists (module stage, post-route recheck), then multi-fidelity arbitration where budgets bind; thermal arbitration by finite volume with cached source fields. Skip a global `--physics exact` switch and correction factors.

Tags: [C] computed by the `ex_*` scripts in Sources on one core of the shared 4-core VM (load 9–21; CPU seconds; ±30%) on the human boards of the KiCad 10.0.7 suite; [I] arithmetic on [C] numbers, or inference. Fast terms: [place-terms](place-terms.md); rungs: [solver-ladder](solver-ladder.md).

## 1. What was measured

**Evaluators** (`ex_exact.py`), all at the same poses:

| Name | Geometry | Physics |
|---|---|---|
| fast | straight pad-to-pad hops | the place terms (F1) |
| detour | fast plus L′(w, h) × (routed − straight) per board hop | F1 on routed lengths |
| cf | each hop routed on a 0.1 mm grid around other nets' pads and the loop's own copper; any angle (Dijkstra, string-pulled) | the module stage's closed forms (`critical_physics.Loop`) |
| cfm | the same with Manhattan routes | same |
| PEEC | Manhattan routes | multi-filament PEEC over an image plane, inductive limit: the validation's reference |
| FV | the zones as placed | 2.5-D finite volume; heat into the part's outer layer (fv) or into every layer under it (fvs: a perfectly stitched footprint) |

Crystal: routed XIN/XOUT length × field-solver C′. Coupling: PEEC currents of the routed aggressor and the EMF along the routed victim; the capacitive part stays fast.

**Candidates** (`ex_decision_flips.py`): on all 112 boards, up to six parts per structure kind, each at its human pose, three legal 1–5 mm translations and its legal rotations (the moves of [place-terms §8](place-terms.md#8-human-boards-does-the-physics-prefer-the-human-placement-c)). A **flip** is a pair of one part's candidates that two evaluators order differently; a pair counts when the reference separates the two by ≥ 1% of some structure's allocation.

## 2. Cost

| Structure | Fast, per move | Exact at placement, per evaluation | Real-copper model | Setup and memory | Growth |
|---|---|---|---|---|---|
| Hot loop | 0.37 ms (its parts also drive coupling terms) | cf 28 ms; PEEC 45 ms (100–300 filaments, ≤ 0.7 MB) | stack HF window 12.5 s median, 2–107 s per cell | rasterize and factor per call; 0.6–3.3 GB | route ∝ cells^1.1–1.3; PEEC ∝ n² to n = 800; HF ∝ cells^1.6 |
| Decap loop | 19 µs | cf 7 ms; PEEC 14 ms | plane pair: closed form within 0.4% of a sheet solve | — | as above |
| ESD path | 36 µs | cf 3.5 ms; PEEC 6 ms | — | — | as above |
| Coupling pair | 80 µs | 91 ms | — | — | as above |
| Crystal | 170 µs | 8 ms of routes; C′ 0.2–1.4 s per new (w, h), then cached | — | — | per stackup |
| Thermal | 0.33 ms; full 0.05–0.5 ms | FV: a victim move reads cached fields; a source move costs one solve, 2–430 ms | — | factor 0.07–66 s (6k–268k nodes), LU 4 MB–1.5 GB | factor ∝ nodes^1.4, solve ∝ nodes^1.2 |
| DC rail | no placement term | — | DC passport 1.2 s per rail | factor 0.5 s median (121k nodes), 4.5 s max | ∝ nodes^1.1 |

From `ex_cost_table.py` (11 boards, 7–621 parts) and `ex_scaling.py`; real-copper rows from [suite-physics-results](suite-physics-results.md) §3 [C].

- **Routing is the cost.** Of a commutation loop's 28 ms, 26 ms is routing; PEEC adds 2–6 ms (1.3 ms at 93 filaments, 75 ms at 783). A hop routes in 0.8 ms (2 mm) to 99 ms (32 mm) at any angle, 1–240 ms Manhattan [C].
- **Per move.** Re-evaluating every structure of the moved part costs 12–363 ms (median by board; p90 0.08–2.3 s) against 10–154 µs. At 4,000 moves per physics part that is 0.1 CPU-hour on split A, 2–7 h on B and 0.4–35 h on C, against 0.1–290 s fast; the placer's 245 s budget would buy 700–11,000 exact moves [C/I].
- **Schur windows** (`ex_window_quotes.py`; the whole-board DC operator of BLDCM-Power, 76k nodes, refactored in 0.23 s): a 1,600-node window (4 × 4 mm, four layers) takes 2.6 s and 20 MB to build, a 6,400-node one 22 s and 312 MB. An exact quote of k changed branches costs 0.06 ms (k = 8), 1.1–1.2 ms (128), 19–29 ms (512) and 100–140 ms (1,024), within 10⁻¹³ of brute force; committing it costs 0.02–7 s [C]. A part move with its two hops changes 10²–10³ branches at 0.1–0.2 mm cells [I].
- **Green's tables.** The thermal operator does not change when parts move. Tabulating it on a 1 mm lattice of both outer layers takes 2k–6k solves (5–21 s) and 16–137 MB; lookups then err by 0.1–0.6 K (median) against direct FV and still flip 14% of material pairs (`ex_thermal_table.py`, 6 boards) [C].

## 3. Decision flips

Pairs pooled over the human pose and the perturbations, 112 boards (24–78 per kind) [C]. The **route floor** (cf vs cfm) and **physics floor** (cfm vs PEEC) show how much the reference itself depends on choices a placement does not fix; for thermal the floor is the via assumption (fv vs fvs).

| Kind | Pairs | fast vs PEEC | detour vs PEEC | Route floor | Physics floor | PEEC's best = fast's best (in fast's top 3) |
|---|---|---|---|---|---|---|
| Commutation | 716 | 15% | 13% | 9% | 1.5% | 69% (95%) |
| Decap | 2,544 | 15% | 14% | 11% | 3.3% | 73% (96%) |
| ESD | 661 | 10% | 9% | 8% | 0.3% | 85% (100%) |
| Crystal | 594 | 19% | 0% | 0% | 0% | 70% (97%) |
| Coupling | 839 | 17% | 17% | — | — | 72% (91%) |
| Thermal (vs fv; fvs) | 1,083 | 30%; 26% | — | 13% | — | 81% (93%) |

- **Loops.** Fast and PEEC disagree a few points above the route floor: the place terms route straight through other nets' pads, use terminal centroids instead of the pads the current uses, and let go and return paths cross. Routed lengths alone (detour) remove a tenth of these flips. On fixed copper PEEC and the closed forms rarely disagree. A third of real hops detour by > 5% when routed (median 1.01, p90 1.20) [C].
- **Crystal** flips come from length alone: routed XIN/XOUT paths, not the field solver's C′.
- **Coupling** flips come from routed loop shapes; detour has no hop to correct. Counted over all terms a coupling move flips 18%.
- **Thermal.** The fin kernel assumes a uniform board; partial pours make a part's own rise depend on the copper it sits on. The flip rate stays 30% for pairs separated by ≥ 20% of a budget, while the via floor drops to 7%: the kernel misses pours, not resolution.
- **Corrections anchored at the human pose** (a per-structure factor or offset, per-hop detour ratios) cannot reorder two values of one structure: decap flips stay 15%, and over all terms they move the flip rate by less than a point. A leave-one-board-out residual on routing-free features (blocked straight length, pad count, w, h) did not help either: flips 15–16% (commutation), 15% (decap), 10–11% (ESD) against fast's 15%, 15% and 10% [C].
- **Misses are amplified over budget.** In one polish run a decap at u ≈ 2 shortened its straight hops while its routed loop grew from 4.9 to 6.6 nH, and the barrier above u = 1 doubled the board's exact cost [C].
- **Coverage.** Exact values exist for 88% of commutation, 56% of decap, 76% of ESD, 72% of crystal and 61% of coupling evaluations. The rest span both board sides or have no single-layer route (BGA escapes); they need vias and the multi-plane stack model, which exists only for real copper.

## 4. Designs

Added CPU per board on split A (7–18 parts) / B (5–46) / C (25–621), from §2 [C/I]; gains measured by the scripts named.

| Design | Plugs in at | Added runtime A / B / C | Accuracy gain | Effort | Main risks |
|---|---|---|---|---|---|
| (a) `--physics exact` | placer inner loop (`Terms.delta`) | 0.1 h / 2–7 h / 0.4–35 h, or 10³× fewer moves | removes the 10–19% flips, keeps the 8–11% route floor; polish median 1.9% better (2.3× better to 1.8× worse) | M | runtime; rugged objective; optimizes router artefacts |
| (b) multi-fidelity top-K | macro layouts (`clusters` keeps K), end-of-anneal polish, every N-th accepted move | ~1 s / 2–10 s / 5–60 s | PEEC's best in fast's top 3 in 91–100%; polish (top 3 + incumbent) as (a) at 0.5–0.8× its PEEC calls | S | gain bounded by top-K recall |
| (c) bias correction | per-structure factor, offset or per-hop detour ratio, refreshed every N moves | seconds per refresh | none within a structure; < 1 point over all terms | S | false confidence, stale anchors |
| (d) Schur windows | module stage and post-route edits (vias, patches) | 2.6–22 s per window; ≤ 1.2 ms per edit to k = 128; 20–140 ms per part move | exact on the window's copper model | L (engine E2–E5) | part moves are high-rank; needs copper |
| (e) exact where copper exists | module stage (PEEC on routed module copper), post-route recheck (passports) | < 1 s / 1–5 s / 5–60 s, plus a 9 s median recheck | 0.3–3.3% of module decisions change; recheck finds DRC-invisible faults | S | uncalibrated models |
| (f) learned surrogate | `Terms`, a residual on fast | µs per call; labels 20–45 ms | leave-one-board-out: no gain (±1 point) | M | out of domain; labels carry route noise |
| (g) async exact, 50 cores | beside the annealer: shadow accepted states, exact-scored elite archive, seed portfolio | wall-clock neutral, 50× CPU | as (b), at scale | M | stale feedback, nondeterminism |
| (h) placement-invariant operators | thermal: FV with cached source fields, or a Green's table | factor once (0.07–66 s); one solve per source move, or 5–21 s of table | thermal flips 26–30% → 0 (cached FV) or 14% (1 mm table) | S | via assumption; table memory |

**(a)** turns the placer into an optimizer of our router: the routed objective jumps when a hop finds or loses a gap, and greedy search on it stalls (one board ended 1.8× worse than fast-only). Keep it as an evaluation mode for small boards and tests.
**(b)** keeps the smooth place terms for proposals and lets routed physics arbitrate among few candidates where it matters. Macros already keep K CP-SAT layouts ranked by `Terms.breakdown`, and the annealer's end state can be polished. Escalate only structures within z·σ of their budget ([solver-ladder §4](solver-ladder.md#4-value-of-information-escalation)), because misses cost most there.
**(c)** is a control variate for a structure's level, not its slope: useful in utilisation reports and allocation calibration, useless for ranking.
**(d)** pays for low-rank copper edits (return vias, pour patches, width steps) inside a module window, where the [engine](../architecture/physics-engine-design.md) already plans it; a part move with its hops costs as much as re-routing plus PEEC.
**(e)** is cheap because the module stage has already routed: PEEC adds 2–6 ms per quote, about 0.1–0.3 s per commutation module (≈ 50 via-site quotes). Any-angle module copper needs oblique filaments (Neumann quadrature, as `kernels.m_seg`) or the stack model on the module window. The recheck is [month-plan](../architecture/month-plan.md#the-joint-loop-modules-routed-physics-re-tweak) step 3: passports and critics in 8.8 s median per board. Its stack model, run today on hot loops only, is also what loops spanning both board sides (most far-side decaps) need.
**(f)** needs features that see the route, which the place terms do not compute; revisit once (b) and (e) log labels on our own placements, with an out-of-domain check.
**(g)**: 50 cores at 20–50 ms per structure give 1,000–2,500 exact evaluations per second against ~1,800 accepted moves per second, but each answer arrives hundreds of moves late. Use the host for a seed portfolio with exact selection of finalists, and for label factories.
**(h)** applies to any operator placement does not change (thermal, plane-pair spreading): victims read cached fields for free, a source move costs one solve. A 1 mm Green's table is not yet accurate enough to replace direct FV.

## 5. Recommendation

Build **(e)** first, then **(b)** with thermal by **(h)**.

1. **Stage 1, exact where copper exists.** After general routing, run passports and critics on every board and PEEC on every routed commutation and decap module; then quote commutation via sites and hop widths with PEEC instead of closed forms. *Accept when*, on all qualified boards: the recheck takes ≤ 60 s CPU median and ≤ 4 GB and reproduces [suite-physics-results](suite-physics-results.md) within 1%; module PEEC agrees with `pw_peec` on the same copper to 10⁻⁶; the module stage takes ≤ 1.1× its current time; cp1, cpk, completion and per-type DRC errors are unchanged against a baseline run with the same KiCad, manifest and suite.
2. **Stage 2, multi-fidelity arbitration.** Routed exact physics re-ranks each macro's K layouts and arbitrates an end-of-anneal polish (fast top 3 plus the incumbent) for structures with u ≥ 0.7; thermal arbitration uses FV with cached source fields. *Accept when* the summed exact cost of the final placements (PEEC, FV) is ≥ 2% lower in median than fast-only on boards with physics structures, no board is > 5% worse and no structure crosses a budget that fast-only kept, at ≤ 1.2× placer CPU, with the same DRC and cp guards. The polish experiment (median 1.9%) says this bar is not a given; failing it means keeping fast-only placement.
3. **Later:** (f) once stages 1–2 have logged ≥ 10⁵ labels; (g) as portfolio selection on the 50-core host; a multi-plane exact model for far-side decaps. Not (a), (c), or (d) for part moves.

## Conflicts and open questions

- **The reference is not unique before routing.** Every flip is relative to our router's route; real copper, layer changes and the critical router's own choices move it. Module-stage numbers, on fixed copper, are the trustworthy ones.
- **PEEC is not ground truth.** It images an ideal plane, ignores foreign copper and is uncalibrated, as is the real-copper HF model, which reads narrow strips 1.5–3× high. Flips against it are flips against a better model, not against measurement ([validation-program](validation-program.md)).
- **Thermal** sits between the surface and stack bounds until part data (exposed pads, via arrays) narrows it.
- **The polish experiment is small** (10 boards, up to 10 parts each, two greedy sweeps): it shows sign and spread, not the gain of a full placer run.

## Sources

- Scripts [C]: [ex_exact.py](../../../tools/research/physics/ex_exact.py) (evaluators), [ex_cost_table.py](../../../tools/research/physics/ex_cost_table.py), [ex_scaling.py](../../../tools/research/physics/ex_scaling.py), [ex_window_quotes.py](../../../tools/research/physics/ex_window_quotes.py), [ex_decision_flips.py](../../../tools/research/physics/ex_decision_flips.py), [ex_surrogate.py](../../../tools/research/physics/ex_surrogate.py), [ex_thermal_table.py](../../../tools/research/physics/ex_thermal_table.py), [ex_polish.py](../../../tools/research/physics/ex_polish.py); they reuse [pw_peec](../../../tools/research/physics/pw_peec.py), [fe_field2d](../../../tools/research/physics/fe_field2d.py), [tm_board_thermal_fv](../../../tools/research/physics/tm_board_thermal_fv.py), [pt_human_perturb](../../../tools/research/physics/pt_human_perturb.py), [pt_grid_route](../../../tools/research/physics/pt_grid_route.py) and [eng_board_scaling](../../../tools/research/physics/eng_board_scaling.py). Flips, costs and polish ran on the kae code of commit c5c53c4.
- Outputs (not committed; third-party boards): `kae-work/physics/exact-options/`.

See also: [place-terms](place-terms.md) · [solver-ladder](solver-ladder.md) · [physics-engine-design](../architecture/physics-engine-design.md) · [month-plan](../architecture/month-plan.md) · [suite-physics-results](suite-physics-results.md) · [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)
