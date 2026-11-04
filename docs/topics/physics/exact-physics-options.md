# Exact physics in the optimizer: what it costs and where it changes decisions

Scope: design study of putting exact physics (routed PEEC, FV thermal, Schur windows) into placement: cost, decision flips vs fast place terms, eight designs (a)–(h), staged recommendation. Not here: the shipped module -> [exact-physics-in-kae](exact-physics-in-kae.md); fast terms -> [place-terms](place-terms.md); rungs -> [solver-ladder](solver-ladder.md).
Keys: exact physics, decision flips, route floor, physics floor, fast vs PEEC, detour, cf, cfm, FV, fvs, Schur window, Green's table, multi-fidelity top-K, bias correction, learned surrogate, async exact, placement-invariant operators, ex_decision_flips.py, ex_polish.py, Stage 1, Stage 2

**Verdict:** exact physics before routing does not pay (reference only as good as the route guess; rugged objective; ms per move); build it where copper exists, then multi-fidelity arbitration (§5). Study summary, provenance and A/B: [kae-exact-physics-before-routing](../../research/placement/kae-exact-physics-before-routing.md).

Tags: [C] from the `ex_*` scripts in Sources, one core of the shared 4-core VM (load 9–21; CPU seconds; ±30%), human boards of the KiCad 10.0.7 suite; [I] arithmetic on [C] or inference.

## 1. What was measured

| Evaluator (`ex_exact.py`, same poses) | Geometry | Physics |
|---|---|---|
| fast | straight pad-to-pad hops | place terms (F1) |
| detour | fast + L′(w, h) × (routed − straight) per board hop | F1 on routed lengths |
| cf | each hop routed on a 0.1 mm grid around other nets' pads and the loop's own copper; any angle (Dijkstra, string-pulled) | module-stage closed forms (`critical_physics.Loop`) |
| cfm | same, Manhattan routes | same |
| PEEC | Manhattan routes | multi-filament PEEC over an image plane, inductive limit (the validation reference) |
| FV | zones as placed | 2.5-D finite volume; heat into the part's outer layer (fv) or every layer under it (fvs: perfectly stitched footprint) |

Crystal: routed XIN/XOUT length × field-solver C′. Coupling: PEEC currents of the routed aggressor, EMF along the routed victim; capacitive part stays fast.

**Candidates** (`ex_decision_flips.py`): all 112 boards, ≤ 6 parts per structure kind, each at its human pose + 3 legal 1–5 mm translations + legal rotations (moves of [place-terms §8](place-terms.md#8-human-boards-does-the-physics-prefer-the-human-placement-c)). **Flip** = a pair of one part's candidates two evaluators order differently; counted when the reference separates them by ≥ 1% of some structure's allocation.

## 2. Cost

| Structure | Fast, per move | Exact at placement, per evaluation | Real-copper model | Setup, memory | Growth |
|---|---|---|---|---|---|
| Hot loop | 0.37 ms (its parts also drive coupling terms) | cf 28 ms; PEEC 45 ms (100–300 filaments, ≤ 0.7 MB) | stack HF window 12.5 s median, 2–107 s per cell | rasterize and factor per call; 0.6–3.3 GB | route ∝ cells^1.1–1.3; PEEC ∝ n² to n = 800; HF ∝ cells^1.6 |
| Decap loop | 19 µs | cf 7 ms; PEEC 14 ms | plane pair: closed form within 0.4% of a sheet solve | — | as above |
| ESD path | 36 µs | cf 3.5 ms; PEEC 6 ms | — | — | as above |
| Coupling pair | 80 µs | 91 ms | — | — | as above |
| Crystal | 170 µs | 8 ms of routes; C′ 0.2–1.4 s per new (w, h), then cached | — | — | per stackup |
| Thermal | 0.33 ms; full 0.05–0.5 ms | FV: victim move reads cached fields; source move one solve, 2–430 ms | — | factor 0.07–66 s (6k–268k nodes), LU 4 MB–1.5 GB | factor ∝ nodes^1.4, solve ∝ nodes^1.2 |
| DC rail | no placement term | — | DC passport 1.2 s per rail | factor 0.5 s median (121k nodes), 4.5 s max | ∝ nodes^1.1 |

From `ex_cost_table.py` (11 boards, 7–621 parts) and `ex_scaling.py`; real-copper rows from [suite-physics-results](suite-physics-results.md) §3 [C].

- **Routing is the cost:** 83–94% of the exact cost before routing; of a commutation loop's 28 ms, 26 ms is routing; PEEC adds 2–6 ms (1.3 ms at 93 filaments, 75 ms at 783). A hop routes in 0.8 ms (2 mm) to 99 ms (32 mm) any-angle, 1–240 ms Manhattan [C].
- **Per move:** re-evaluating every structure of the moved part 12–363 ms (median by board; p90 0.08–2.3 s) vs 10–154 µs. At 4,000 moves per physics part: 0.1 CPU-h on split A, 2–7 h on B, 0.4–35 h on C, vs 0.1–290 s fast; the placer's 245 s budget buys 700–11,000 exact moves [C/I].
- **Schur windows** (`ex_window_quotes.py`; whole-board DC operator of BLDCM-Power, 76k nodes, refactored in 0.23 s): 1,600-node window (4 × 4 mm, 4 layers) 2.6 s, 20 MB to build; 6,400-node 22 s, 312 MB. Exact quote of k changed branches: 0.06 ms (k = 8), 1.1–1.2 ms (128), 19–29 ms (512), 100–140 ms (1,024), within 10⁻¹³ of brute force; commit 0.02–7 s [C]. A part move with its two hops changes 10²–10³ branches at 0.1–0.2 mm cells [I].
- **Green's tables:** the thermal operator does not change when parts move. A 1 mm lattice on both outer layers takes 2k–6k solves (5–21 s), 16–137 MB; lookups err 0.1–0.6 K (median) vs direct FV and still flip 14% of material pairs (`ex_thermal_table.py`, 6 boards) [C].

## 3. Decision flips

Pairs pooled over human pose and perturbations, 112 boards (24–78 per kind) [C]. **Route floor** = cf vs cfm; **physics floor** = cfm vs PEEC: how much the reference depends on choices a placement does not fix. Thermal floor = via assumption (fv vs fvs).

| Kind | Pairs | fast vs PEEC | detour vs PEEC | Route floor | Physics floor | PEEC's best = fast's best (in fast's top 3) |
|---|---|---|---|---|---|---|
| Commutation | 716 | 15% | 13% | 9% | 1.5% | 69% (95%) |
| Decap | 2,544 | 15% | 14% | 11% | 3.3% | 73% (96%) |
| ESD | 661 | 10% | 9% | 8% | 0.3% | 85% (100%) |
| Crystal | 594 | 19% | 0% | 0% | 0% | 70% (97%) |
| Coupling | 839 | 17% | 17% | — | — | 72% (91%) |
| Thermal (vs fv; fvs) | 1,083 | 30%; 26% | — | 13% | — | 81% (93%) |

- **Loops:** place terms route straight through other nets' pads, use terminal centroids instead of the pads the current uses, and let go and return paths cross. Routed lengths (detour) remove a tenth of flips; fast vs PEEC sits only 2–6 points above the route floor. On fixed copper PEEC and closed forms rarely disagree. A third of real hops detour > 5% when routed (median 1.01, p90 1.20).
- **Crystal** flips come from length alone (routed XIN/XOUT), not C′.
- **Coupling** flips come from routed loop shapes; detour has no hop to correct; over all terms a coupling move flips 18%.
- **Thermal:** the fin kernel assumes a uniform board; partial pours make a part's own rise depend on its copper. Flip rate stays 30% for pairs separated by ≥ 20% of a budget while the via floor drops to 7%: the kernel misses pours, not resolution.
- **Corrections anchored at the human pose** (per-structure factor or offset, per-hop detour ratios) cannot reorder two values of one structure: decap flips stay 15%; over all terms < 1 point. Leave-one-board-out residual on routing-free features (blocked straight length, pad count, w, h): flips 15–16% (commutation), 15% (decap), 10–11% (ESD) vs fast's 15%, 15%, 10%.
- **Misses amplified over budget:** in one polish run a decap at u ≈ 2 shortened its straight hops while its routed loop grew 4.9 → 6.6 nH, and the barrier above u = 1 doubled the board's exact cost.
- **Coverage:** exact values exist for 88% commutation, 56% decap, 76% ESD, 72% crystal, 61% coupling evaluations; the rest span both sides or have no single-layer route (BGA escapes) and need vias and the multi-plane stack model, which exists only for real copper.

## 4. Designs

Added CPU per board on split A (7–18 parts) / B (5–46) / C (25–621), from §2 [C/I]; gains from the named scripts.

| Design | Plugs in at | Added runtime A / B / C | Accuracy gain | Effort | Main risks |
|---|---|---|---|---|---|
| (a) `--physics exact` | placer inner loop (`Terms.delta`) | 0.1 h / 2–7 h / 0.4–35 h, or 10³× fewer moves | removes the 10–19% flips, keeps the 8–11% route floor; polish median 1.9% better (2.3× better to 1.8× worse) | M | runtime; rugged objective; optimizes router artefacts |
| (b) multi-fidelity top-K | macro layouts (`clusters` keeps K), end-of-anneal polish, every N-th accepted move | ~1 s / 2–10 s / 5–60 s | PEEC's best in fast's top 3 in 91–100%; polish (top 3 + incumbent) as (a) at 0.5–0.8× its PEEC calls | S | gain bounded by top-K recall |
| (c) bias correction | per-structure factor, offset or per-hop detour ratio, refreshed every N moves | seconds per refresh | none within a structure; < 1 point over all terms | S | false confidence, stale anchors |
| (d) Schur windows | module stage, post-route edits (vias, patches) | 2.6–22 s per window; ≤ 1.2 ms per edit to k = 128; 20–140 ms per part move | exact on the window's copper model | L (engine E2–E5) | part moves are high-rank; needs copper |
| (e) exact where copper exists | module stage (PEEC on routed module copper), post-route recheck (passports) | < 1 s / 1–5 s / 5–60 s, plus a 9 s median recheck | 0.3–3.3% of module decisions change; recheck finds DRC-invisible faults | S | uncalibrated models |
| (f) learned surrogate | `Terms`, residual on fast | µs per call; labels 20–45 ms | leave-one-board-out: no gain (±1 point) | M | out of domain; labels carry route noise |
| (g) async exact, 50 cores | beside the annealer: shadow accepted states, exact-scored elite archive, seed portfolio | wall-clock neutral, 50× CPU | as (b), at scale | M | stale feedback, nondeterminism |
| (h) placement-invariant operators | thermal: FV with cached source fields, or a Green's table | factor once (0.07–66 s); one solve per source move, or 5–21 s of table | thermal flips 26–30% → 0 (cached FV) or 14% (1 mm table) | S | via assumption; table memory |

- **(a)** makes the placer an optimizer of our router: the routed objective jumps when a hop finds or loses a gap; greedy search stalls (one board 1.8× worse than fast-only). Keep as an evaluation mode for small boards and tests.
- **(b)** keeps smooth place terms for proposals; routed physics arbitrates few candidates where it matters. Macros already keep K CP-SAT layouts ranked by `Terms.breakdown`; the annealer's end state can be polished. Escalate only structures within z·σ of budget ([solver-ladder §4](solver-ladder.md#4-value-of-information-escalation)), where misses cost most.
- **(c)** is a control variate for a structure's level, not its slope: useful in utilisation reports and allocation calibration, useless for ranking.
- **(d)** pays for low-rank copper edits (return vias, pour patches, width steps) in a module window, where the [engine](../architecture/physics-engine-design.md) already plans it; a part move with its hops costs as much as re-routing plus PEEC.
- **(e)** is cheap because the module stage already routed: PEEC adds 2–6 ms per quote, ~0.1–0.3 s per commutation module (≈ 50 via-site quotes). Any-angle module copper needs oblique filaments (Neumann quadrature, as `kernels.m_seg`) or the stack model on the module window. The recheck is [month-plan](../architecture/month-plan.md#the-joint-loop-modules-routed-physics-re-tweak) step 3: passports and critics in 8.8 s median per board; its stack model (today hot loops only) is also what loops spanning both sides (most far-side decaps) need. Shipped as [exact-physics-in-kae](exact-physics-in-kae.md).
- **(f)** needs features that see the route, which place terms do not compute; revisit when (b) and (e) log labels on our placements, with an out-of-domain check.
- **(g)** 50 cores at 20–50 ms per structure → 1,000–2,500 exact evaluations/s vs ~1,800 accepted moves/s, but each answer arrives hundreds of moves late. Use the host for a seed portfolio with exact finalist selection, and label factories.
- **(h)** applies to any operator placement does not change (thermal, plane-pair spreading): victims read cached fields free; a source move costs one solve. A 1 mm Green's table is not yet accurate enough to replace direct FV.

## 5. Recommendation

Build **(e)** first, then **(b)** with thermal by **(h)**.

1. **Stage 1, exact where copper exists.** After general routing: passports and critics on every board, PEEC on every routed commutation and decap module; then quote commutation via sites and hop widths by PEEC. *Accept when*, on all qualified boards: recheck ≤ 60 s CPU median and ≤ 4 GB, reproduces [suite-physics-results](suite-physics-results.md) within 1%; module PEEC agrees with `pw_peec` on the same copper to 10⁻⁶; module stage ≤ 1.1× current time; cp1, cpk, completion and per-type DRC unchanged vs a baseline with the same KiCad, manifest and suite.
2. **Stage 2, multi-fidelity arbitration.** Routed exact physics re-ranks each macro's K layouts and arbitrates an end-of-anneal polish (fast top 3 + incumbent) for structures with u ≥ 0.7; thermal by FV with cached source fields. *Accept when* summed exact cost of final placements (PEEC, FV) is ≥ 2% lower in median than fast-only on boards with physics structures, no board > 5% worse, no structure crosses a budget fast-only kept, at ≤ 1.2× placer CPU, same DRC and cp guards. The polish experiment (median 1.9%) says this bar is not a given; failing it means keeping fast-only placement.
3. **Later:** (f) after ≥ 10⁵ logged labels; (g) as portfolio selection on the 50-core host; a multi-plane exact model for far-side decaps. Not (a), (c), or (d) for part moves.

## Open questions

- The reference is not unique before routing: every flip is relative to our router's route; real copper, layer changes and the critical router's choices move it. Module-stage numbers on fixed copper are the trustworthy ones.
- PEEC is not ground truth: ideal image plane, no foreign copper, uncalibrated; the real-copper HF model reads narrow strips 1.5–3× high. Flips are against a better model, not measurement ([validation-program](validation-program.md)).
- Thermal sits between surface and stack bounds until part data (exposed pads, via arrays) narrows it.
- The polish experiment is small (10 boards, ≤ 10 parts each, two greedy sweeps): sign and spread, not a full placer run's gain.

## Sources

- Scripts [C]: [ex_exact.py](../../../tools/research/physics/ex_exact.py), [ex_cost_table.py](../../../tools/research/physics/ex_cost_table.py), [ex_scaling.py](../../../tools/research/physics/ex_scaling.py), [ex_window_quotes.py](../../../tools/research/physics/ex_window_quotes.py), [ex_decision_flips.py](../../../tools/research/physics/ex_decision_flips.py), [ex_surrogate.py](../../../tools/research/physics/ex_surrogate.py), [ex_thermal_table.py](../../../tools/research/physics/ex_thermal_table.py), [ex_polish.py](../../../tools/research/physics/ex_polish.py); reusing [pw_peec](../../../tools/research/physics/pw_peec.py), [fe_field2d](../../../tools/research/physics/fe_field2d.py), [tm_board_thermal_fv](../../../tools/research/physics/tm_board_thermal_fv.py), [pt_human_perturb](../../../tools/research/physics/pt_human_perturb.py), [pt_grid_route](../../../tools/research/physics/pt_grid_route.py), [eng_board_scaling](../../../tools/research/physics/eng_board_scaling.py). Flips, costs and polish ran on kae commit c5c53c4.
- Outputs (not committed; third-party boards): `kae-work/physics/exact-options/`.
- Related: [physics-engine-design](../architecture/physics-engine-design.md), [month-plan](../architecture/month-plan.md), [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md).
