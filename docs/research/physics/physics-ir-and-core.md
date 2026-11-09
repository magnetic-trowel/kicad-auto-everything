# Physics vocabulary, IR, solver ladder and physics core v2

**Status:** not finished (schemas, a validator, a partial core skeleton and solver prototypes; never wired into the tools; model vs model).
**First published:** 2026-10-22, commits [ba45def](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ba45defde956f7d73cf07929345b86e4793cd1aa) (prototypes), [d685262](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d685262a655b24408249c51ff9efcd8051118b4f) (vocabulary), [c23ca3a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c23ca3a7e45ad33f0a1a00821a9ef8fd289b5ffa) (solvers), [0dfe51a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0dfe51aadd1968b83f8425a2197befc98c3d32ea) (core v2), [d21f9a1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/d21f9a1da4a366200a8311f0d319a54142def51b) (synthesis) on branch `claude/vigilant-mayer-i91rrr`.

Scope: representation for a physics-first layout tool: vocabulary of the parasitic structures a schematic omits, intent file format with a dimensional validator, multi-fidelity solver ladder with an evaluator contract, "physics core" of copper pieces with exact edit prices. Mostly specification; all results synthetic, against closed forms or other models, nothing measured. Not here: specs -> [vocabulary](../../topics/physics/vocabulary.md), [physics-ir](../../topics/physics/physics-ir.md), [solver-ladder](../../topics/physics/solver-ladder.md), [open-solvers](../../topics/physics/open-solvers.md), [physics-core-v2](../../topics/physics/physics-core-v2.md), [physics-core-v2-api](../../topics/physics/physics-core-v2-api.md).
Keys: `pcb-intent/0.3`, `pcb-intent/0.4`, `intent.yaml`, `ledger.json`, atoms, half a port, validator, solver ladder F0–F4, C0–C3, SIM1 evaluator contract, SIM7, SIM8, SIM10, MS2, PEECN, Piece, Passport, Jobs, Belief E0–E5, kernels K1–K8, edit spectrum, Woodbury, `PhysicsCore`

## Idea and how it works

### Vocabulary and `pcb-intent/0.3`
- Layout = parasitic realisation of a schematic: 12 atoms (Port, Node, Loop, Body, Reference, Channel, Cavity, Discontinuity, Antenna, Heat path, Barrier, Coupling), 5 value types (Spectrum, Sensitivity, Budget, Band, Regime). Each structure is *designed* (has a spec) or *parasitic* (has a budget).
- Driving facts: (1) a schematic net is "half a port": ports are terminal pairs, signal + reference (FastHenry `.External n1 n2`); (2) inductance belongs to closed loops, Ruehli partial inductance as accounting unit; (3) where return current flows is a regime, boundary f_x ≈ R_□/(2πμ0h) (0.31 MHz at h = 0.2 mm, 39 kHz at 1.6 mm, 1 oz).
- Relations twice: *required* (detectors, LLM, humans) and *observed* (computed on a PEEC-like graph of partial R, L, M, C, G and thermal edges). Critics diff the two.
- Operators with signed effects and sensitivity cards: `widen_to_pour`, `shrink_node`, `fold_loop_vertical`, `overlap_return`, `stitch`, `kelvin_tap`, `guard`, `void`, `slow_edge`, ...
- IR `pcb-intent/0.3` adds `bands`, `symbols`, `physics`, `ops`. `intent.yaml`: requirements with provenance. `ledger.json` (written by code only): observed values, regimes, budget spend with attribution and trust radius. Values are dimensioned quantities or expressions (`0.85*V_abs(U3.VIN)`). The LLM writes requirements, allocations, mechanism hypotheses and operator choices, never geometry or spend. Each entity compiles to ≤ 6 targets: KiCad objects, `.kicad_dru`, placer terms, router costs, checkers, solver decks.
- Validator rules: closed kinds, required fields, no unknown keys; SI dimension algebra over quantities and expressions; non-empty `port.ref`; closed loops name a return; coupling mechanism compatible with aggressor/victim kinds; `alloc` ≤ 100%; couplings and antennas name a band.

### Solver ladder
- Rungs: F0 geometry; F1 closed forms (µs); S learned residual on F1; F2 quasi-static on real copper (image PEEC, 2-D FD cross-sections, 2.5-D FV, meshed-plane PEEC; ms–min); F3 full-wave/FEM on slices (openEMS, Palace, Elmer; min–h); F4 measurement/vendor data. Circuit axis C0–C3 (budget arithmetic, lumped, SPICE, channel statistics).
- Evaluator contract (SIM1): every call returns `{value, σ, unit, rung, validity in/edge/out, provenance, cost, cache key}`; validity coded in dimensionless features (w/h, s/h, l/λ, f·t_r); σ from split-conformal residual quantiles per region (SIM8).
- Escalate by value of information, not schedule (SIM10): only if |budget − v_k| < z·σ_k, if candidate intervals overlap the leader's, or if |∂objective/∂v|·σ_k exceeds tolerance.
- Score proxies by decision quality (pick-the-best-of-10 rate, regret), not R² (SIM7).
- Loop-inductance proxy **MS2** = Σ l·L′(w,h) − 2·overlap·(μ0/4π)·ln(1 + (2h/s)²); L′ = Hammerstad–Jensen air-microstrip Z0/c0; subtracted term = mutual of antiparallel overlapping sides. Over a plane the image current confines the field, so L scales with length × L′(w,h), not plan-view area. Reference **PEECN**: N filaments per width over a PEC image, Grover parallel-filament mutuals, GMD 0.2235(w+t) self terms.

### Physics core v2
- Unit **Piece**: track segment, pad, via, pour/plane tile 2h–2 mm, part body, or *world conductor* (chassis, cable with Z_cm(f), heatsink, LISN). Per-band **Passport**: topological role, current share per source, charge destination, energies, exact change of every budget if removed (with its Woodbury spectrum), damping share per mode, **Jobs** (verbs: carries, returns, images, lowers/raises p→q, senses, damps, shields, ...) valued Σλ_k|ΔB_k|/slack_k.
- Budgets are closed-loop budgets naming the victim's observation loop. Every number is a **Belief** with exactness class: E0 topological, E1 algebraic (exact on the discretised model), E2 certified bound, E3 asymptotic, E4 calibrated, E5 conjectured.
- Eight kernels: K1 topology; K2 complex sheet operator ∇·(Z_s⁻¹∇φ) − Y_p·φ = −s; K3 complex-image PEEC; K4 response (adjoints, Tellegen attribution, Woodbury removal, Thevenin addition); K5 floors; K6 modal Q ledger; K7 morphology; K8 belief/VOI (escalate when margin < z·σ, z = Φ⁻¹(1 − c/L)). One factorisation per (operator, band, topology epoch).
- **Edit spectrum** (removal of branches B): P_B = diag(y_B)·A_Bᵀ·Y⁻¹·A_B; exact ΔZ_qp = Σ c_i/(1 − λ_i), Σc_i = first-order adjoint price; trust radius r = max|λ|. At DC 0 ≤ λ ≤ 1 (λ = 1 exactly at a disconnect); 1 ≤ exact/first-order ≤ 1/(1 − λ_max). Inner loop rejects first-order prices with r ≥ 0.5.
- API (`physics-core-v2-api`): frozen dataclasses; `PhysicsCore` facade with `passport`, `why_here`, `what_if`, `where_add`, `explain`, `menu`, `binding`, `unknowns`, `evaluate`, `commit`; proposes `pcb-intent/0.4`.

### Synthesis
Eleven workstreams converged on nine objects (screened Laplace sheet operator φ, stream function ψ, PEEC partials, adjoints/reciprocity, Lagrange prices, eigenmodes, multipoles, homotopy classes, morphology) → the eight kernels. ~890 ideas in [docs/ideas/physics-first](../../ideas/physics-first/README.md); build order in [cross-workstream-synthesis](../../topics/physics/cross-workstream-synthesis.md); gaps in [research-gaps](../../topics/physics/research-gaps.md).

Test cases: validator on the six worked examples of [physics-ir-examples](../../topics/physics/physics-ir-examples.md); 600 random rectangle/hairpin/L loops over an ideal plane for proxies; tier-cost timings; core skeleton on a synthetic 30 × 20 mm PWR/GND plane pair (2,384 cells, a slot, two loads, Kelvin taps, six decaps).

## Results

All [C], synthetic.

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

Red team -> [redteam-corrections](redteam-corrections.md) rows `rt_loop_proxy` (PEECN reference needs ≥ 31 graded filaments; plain length nearly matches MS2 at fixed stackup), `rt_cut_law` (×2 is square-grid), `rt_sheet_return` (ℓ50 scope, 50 mm plane); core agreement is "algebra, not physics".

Exact physics inside the placer before routing (exact-options, 112 human boards) changed few decisions -> [exact-physics-options](../../topics/physics/exact-physics-options.md), [kae-exact-physics-before-routing](../placement/kae-exact-physics-before-routing.md).

## Verdict

- Vocabulary and the core's exact edit algebra: sound and cheap. MS2: good loop-L ranker, only modestly better than plain length at fixed stackup.
- Not wired into the tools. `kae` borrows labels and shapes only: `kae/src/kae/physics/priors.py` marks priors as E5 Beliefs; `kae/src/kae/circuit/roles.py:belief()` emits Belief-shaped JSON; own `kae.brief/1` schema instead of `pcb-intent`. H-J L′ with Grover image partials (the MS family) is what `kae/src/kae/physics/kernels.py` uses.
- Missing: IR compiler, ledger, physics graph, SIM1 contract with conformal σ, merged PEEC cores (SIM46), K3/K5–K8 in the core, any run on a real board.
- **Not built (plans):** "copper doctor" review tool; LLM "physicist" that adjudicates and explains but never writes coordinates; per-board session server holding warm factorisations; 12-month build plan with kill criteria ([system-design](../../topics/architecture/system-design.md), [system-design-build-plan](../../topics/architecture/system-design-build-plan.md)), replaced by the month plan's `kae` pipeline. Schematic-to-physics (simulate the schematic, adjoint susceptibility, layout invisibility index) -> [domain-models](domain-models.md), [schematic-to-physics](../../topics/physics/schematic-to-physics.md); no kae code.

## Code

`tools/research/physics/`, print-only, synthetic inputs: `vo_ir_check.py` (validator; `python vo_ir_check.py FILE.yaml|FILE.md`, needs PyYAML), `vo_numbers.py`, `vo_return_spread.py`, `sl_loop_peec.py` (`--fasthenry DIR` writes synthetic decks; FastHenry not bundled), `sl_tier_costs.py`, `pc2_core_skeleton.py` (`[exact|events|dispatch|passport|floors|bench|all]`).

Related: [rule-genealogy](rule-genealogy.md), [first-principles-lenses](first-principles-lenses.md), [domain-models](domain-models.md), [physics-critics-and-passports](physics-critics-and-passports.md), [digest](../../digests/physics-first.md), [executive report](../../../reports/Physics-first%20PCB%20layout.md).
