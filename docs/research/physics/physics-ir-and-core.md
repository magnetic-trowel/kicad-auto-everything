# Physics vocabulary, IR, solver ladder and physics core v2

**Status:** not finished (schemas, a validator, a partial core skeleton and solver prototypes; never wired into the tools; model vs model).
**First published:** 2026-10-22, commits [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa) (prototypes), [d685262](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d685262a655b24408249c51ff9efcd8051118b4f) (vocabulary), [c23ca3a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c23ca3a7e45ad33f0a1a00821a9ef8fd289b5ffa) (solvers), [0dfe51a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0dfe51aadd1968b83f8425a2197befc98c3d32ea) (core v2), [d21f9a1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d21f9a1da4a366200a8311f0d319a54142def51b) (synthesis) on branch `claude/vigilant-mayer-i91rrr`.

The design for the representation a physics-first layout tool would need: a vocabulary for the parasitic structures a schematic omits, an intent file format with a dimensional validator, a multi-fidelity solver ladder with a contract every evaluator obeys, and a "physics core" that models copper pieces with exact edit prices. Most of it is specification. **Every result here is computed on synthetic cases against closed forms or other models; nothing is measured.**

## Idea and how it works

### Vocabulary and `pcb-intent/0.3`
- A layout is the parasitic realisation of a schematic, described with 12 atoms (Port, Node, Loop, Body, Reference, Channel, Cavity, Discontinuity, Antenna, Heat path, Barrier, Coupling) and 5 value types (Spectrum, Sensitivity, Budget, Band, Regime). Each structure is *designed* (has a spec) or *parasitic* (has a budget).
- Three facts drive it: a schematic net is "half a port" (ports are terminal pairs, signal plus reference, as FastHenry's `.External n1 n2`); inductance belongs to closed loops, with Ruehli partial inductance as the accounting unit; where return current flows is a regime with boundary f_x ≈ R_□/(2πμ0h) (0.31 MHz at h = 0.2 mm, 39 kHz at 1.6 mm, 1 oz).
- Relations exist twice: *required* (from detectors, the LLM, humans) and *observed* (computed on a PEEC-like graph of partial R, L, M, C, G and thermal edges). Critics diff the two.
- Operators carry signed effects and sensitivity cards: `widen_to_pour`, `shrink_node`, `fold_loop_vertical`, `overlap_return`, `stitch`, `kelvin_tap`, `guard`, `void`, `slow_edge`, ...
- The IR `pcb-intent/0.3` adds `bands`, `symbols`, `physics`, `ops`. `intent.yaml` holds requirements with provenance; `ledger.json` (written by code only) holds observed values, regimes and budget spend with attribution and a trust radius. Values are dimensioned quantities or expressions such as `0.85*V_abs(U3.VIN)`. The LLM writes requirements, allocations, mechanism hypotheses and operator choices, never geometry or spend. Each entity compiles to up to six targets: KiCad objects, `.kicad_dru`, placer terms, router costs, checkers, solver decks.
- Validator rules: closed kinds, required fields, no unknown keys; SI dimension algebra over quantities and expressions; non-empty `port.ref`; closed loops that name a return; coupling mechanism compatible with aggressor/victim kinds; `alloc` ≤ 100%; couplings and antennas name a band.

### Solver ladder
- Rungs: F0 geometry; F1 closed forms (µs); S learned residual on F1; F2 quasi-static on the real copper (image PEEC, 2-D FD cross-sections, 2.5-D FV, meshed-plane PEEC; ms–min); F3 full-wave/FEM on slices (openEMS, Palace, Elmer; min–h); F4 measurement/vendor data. A circuit axis C0–C3 (budget arithmetic, lumped, SPICE, channel statistics).
- Evaluator contract (SIM1): every call returns `{value, σ, unit, rung, validity in/edge/out, provenance, cost, cache key}`; validity is coded in dimensionless features (w/h, s/h, l/λ, f·t_r); σ from split-conformal residual quantiles per region (SIM8).
- Escalate by value of information, not schedule (SIM10): only if |budget − v_k| < z·σ_k, if candidate intervals overlap the leader's, or if |∂objective/∂v|·σ_k exceeds tolerance.
- Score proxies by decision quality (pick-the-best-of-10 rate and regret), not R² (SIM7).
- The loop-inductance proxy **MS2** = Σ l·L′(w,h) − 2·overlap·(μ0/4π)·ln(1 + (2h/s)²), with L′ the Hammerstad–Jensen air-microstrip Z0/c0 and the subtracted term the mutual of antiparallel overlapping sides. Over a plane the image current confines the field, so L scales with length × L′(w,h), not plan-view area. Reference **PEECN**: N filaments per width over a PEC image, Grover parallel-filament mutuals, GMD 0.2235(w+t) self terms.

### Physics core v2
- Unit is the **Piece** (track segment, pad, via, pour/plane tile 2h–2 mm, part body, or *world conductor*: chassis, cable with Z_cm(f), heatsink, LISN). Each piece has a per-band **Passport**: topological role, current share per source, charge destination, energies, the exact change of every budget if removed (with its Woodbury spectrum), damping share per mode, and **Jobs** (verbs: carries, returns, images, lowers/raises p→q, senses, damps, shields, ...) valued Σλ_k|ΔB_k|/slack_k.
- Budgets are closed-loop budgets naming the victim's observation loop. Every number is a **Belief** with an exactness class: E0 topological, E1 algebraic (exact on the discretised model), E2 certified bound, E3 asymptotic, E4 calibrated, E5 conjectured.
- Eight kernels: K1 topology, K2 complex sheet operator ∇·(Z_s⁻¹∇φ) − Y_p·φ = −s, K3 complex-image PEEC, K4 response (adjoints, Tellegen attribution, Woodbury removal, Thevenin addition), K5 floors, K6 modal Q ledger, K7 morphology, K8 belief/VOI (escalate when margin < z·σ, z = Φ⁻¹(1 − c/L)). One factorisation per (operator, band, topology epoch).
- **Edit spectrum:** for removal of branches B, P_B = diag(y_B)·A_Bᵀ·Y⁻¹·A_B; exact ΔZ_qp = Σ c_i/(1 − λ_i), where Σc_i is the first-order adjoint price; trust radius r = max|λ|. At DC 0 ≤ λ ≤ 1 (λ = 1 exactly at a disconnect); brackets 1 ≤ exact/first-order ≤ 1/(1 − λ_max). The inner loop rejects first-order prices with r ≥ 0.5.
- API (`physics-core-v2-api`): frozen dataclasses, `PhysicsCore` facade with `passport`, `why_here`, `what_if`, `where_add`, `explain`, `menu`, `binding`, `unknowns`, `evaluate`, `commit`; proposes `pcb-intent/0.4`.

### Synthesis
Eleven workstreams kept arriving at nine objects (screened Laplace sheet operator φ, stream function ψ, PEEC partials, adjoints/reciprocity, Lagrange prices, eigenmodes, multipoles, homotopy classes, morphology), which became the eight kernels. About 890 ideas are catalogued in [docs/ideas/physics-first](../../ideas/physics-first/README.md); the build order is in [cross-workstream-synthesis](../../topics/physics/cross-workstream-synthesis.md) and gaps in [research-gaps](../../topics/physics/research-gaps.md).

## What we tried

Validator on the six worked examples of [physics-ir-examples](../../topics/physics/physics-ir-examples.md); 600 random rectangle/hairpin/L loops over an ideal plane for proxies; tier-cost timings; a core skeleton on a synthetic 30 × 20 mm PWR/GND plane pair (2,384 cells, a slot, two loads, Kelvin taps, six decaps).

## Results

All [C], synthetic. Sources: [vocabulary](../../topics/physics/vocabulary.md), [physics-ir](../../topics/physics/physics-ir.md), [solver-ladder](../../topics/physics/solver-ladder.md), [open-solvers](../../topics/physics/open-solvers.md), [physics-core-v2](../../topics/physics/physics-core-v2.md), [physics-core-v2-api](../../topics/physics/physics-core-v2-api.md).

| Check | Result |
|---|---|
| IR validator on six examples | 0 errors, 46 entities, 40 budgets. "12 of 12 seeded errors caught" refers to a test file that is not committed (not reproducible) |
| Plan-view area as loop proxy | Spearman 0.36 mixed stackups; picks best of 10 in 66% (fixed stackup) / 16% (mixed), median regret 169% |
| MS2 | Spearman 0.999, picks best 96–98%; bias +7.7% vs graded-filament reference |
| μ0·h·l/w | +50…+1000% bias |
| PEECN vs FastHenry | within 1.3% on 4 loops (w/h 0.3–5, 100 MHz) |
| Residual surrogate on MS2 (300 labels) | median 3.5%, p95 9.8%, max 114% (black box 28%) |
| Tier costs | H-J Z0 within 0.2–0.7% of extrapolated FD; IPC-2141 −12% at w/h 3, −65% at 6; plain area-weighted adjoint prices a 6 mm slot 30× low |
| Core identities (Woodbury, Thevenin, Tellegen, Foster) | match brute-force refactoring to ≤ 4×10⁻¹¹ |
| Core cost | factor/solve 6 ms / 0.2 ms at 2.4k cells; 0.8–1.2 s / 20–41 ms at 153k cells (~n^1.2) |
| Edit spectrum | cut grown to a 0.5 mm neck: λ = 0.990, first order +2.2% vs exact +197%; decap removed at anti-resonance: abs(λ) = 1.36, first order has the wrong sign |

**Red-team corrections** ([redteam-corrections](redteam-corrections.md)): the 7-filament PEECN reference reads 11–21% low at w/h 10–60 (to 65% at ≥ 30), so the reference needs ≥ 31 graded filaments; at a fixed stackup plain trace length picks the best 82–99% vs MS2's 97–100%, so a competent rule nearly matches; the core's agreement is "algebra, not physics"; the ×2 removal price is a square-grid artefact. Return-spread scoping: ℓ50/ℓ_m 0.42–0.53 holds for ℓ ≥ 6h, band numbers are for a 50 mm plane.

Exact physics inside the placer before routing (exact-options, 112 human boards) changed few decisions; see [exact-physics-options](../../topics/physics/exact-physics-options.md) and [kae-exact-physics-before-routing](../placement/kae-exact-physics-before-routing.md).

## Verdict

The vocabulary and the core's exact edit algebra are sound and cheap; the proxy study shows MS2 is a good loop-L ranker but only modestly better than plain length at a fixed stackup. Nothing here was wired into the tools: `kae` borrows labels and shapes only (`kae/src/kae/physics/priors.py` marks priors as E5 Beliefs; `kae/src/kae/circuit/roles.py:belief()` emits Belief-shaped JSON) and uses its own `kae.brief/1` schema instead of `pcb-intent`. The H-J L′ with Grover image partials (the MS family) is what `kae/src/kae/physics/kernels.py` uses. Missing: the IR compiler, ledger, physics graph, the SIM1 contract with conformal σ, merged PEEC cores (SIM46), K3/K5–K8 in the core, any run on a real board.

**Not built (plans):** a "copper doctor" review tool, an LLM "physicist" that adjudicates and explains but never writes coordinates, a per-board session server holding warm factorisations, and a 12-month build plan with kill criteria ([system-design](../../topics/architecture/system-design.md), [system-design-build-plan](../../topics/architecture/system-design-build-plan.md)); the month plan replaced it with the `kae` pipeline. Schematic-to-physics (simulate the schematic, adjoint susceptibility, layout invisibility index) is described in [domain-models](domain-models.md) and [schematic-to-physics](../../topics/physics/schematic-to-physics.md); no kae code.

## Code

`tools/research/physics/`: `vo_ir_check.py` (validator; `python vo_ir_check.py FILE.yaml|FILE.md`, needs PyYAML), `vo_numbers.py`, `vo_return_spread.py`, `sl_loop_peec.py` (`--fasthenry DIR` writes synthetic decks; FastHenry is not bundled), `sl_tier_costs.py`, `pc2_core_skeleton.py` (`[exact|events|dispatch|passport|floors|bench|all]`). All print-only, synthetic inputs.

## Related

[rule-genealogy](rule-genealogy.md), [first-principles-lenses](first-principles-lenses.md), [domain-models](domain-models.md), [physics-critics-and-passports](physics-critics-and-passports.md), [digest](../../digests/physics-first.md), [executive report](../../../reports/Physics-first%20PCB%20layout.md).
