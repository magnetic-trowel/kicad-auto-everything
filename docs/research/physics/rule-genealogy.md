# Rule genealogy, derivation audit and foundations

**Status:** partial (analysis computed model-vs-model; nothing built into the tools, nothing measured).
**First published:** 2026-10-22, commit [0822bd7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0822bd7f76d20a1683abd9eb2292aab23144744c) on branch `claude/vigilant-mayer-i91rrr`.

Scope: 160 PCB rules of thumb decompressed into protected quantity + binding regime, then derived from seven principles. Not here: full tables -> [rule-basis-set](../../topics/physics/rule-basis-set.md), [derivation-audit](../../topics/physics/derivation-audit.md), [foundations](../../topics/physics/foundations.md).
Keys: rule genealogy, derivation audit, foundations, basis quantities, regime selectors, proxy words, criterion G, (I − G)⁻¹, spectral radius, T1 impedance level, P01–P59, S01–S55, R01–R46, RG1–RG53, F1–F7

Result: 132 of 160 derive (most only with a stated regime); only 12 of 67 quoted numbers do. **Every number is model against model (closed forms, small 2-D field solves); none measured.**

## Idea and how it works

**Genealogy (workstream 1).** One record per rule: `{slogan, origin, basis quantity, governing equation, "binds when" predicate, replacement budget, solver cost}` (idea RG1 in [rule-replacements](../../ideas/physics-first/rule-replacements.md)).

| Field | Codes |
|---|---|
| Rules | P01–P59 power/analog/isolation/thermal, S01–S55 SI/EMI/RF, R01–R46 routing style/DFM |
| Origin | Ph physics, Mf manufacturing, Hb habit, Sp simplicity proxy, Cg cognition, Tl tool, Lg legal |
| Verdict | R about right, C conservative, A anti-conservative, M mixed, X wrong, CT contested |
| Solver cost | CF closed form, 2D, PEEC, FW full-wave, SP SPICE, TN thermal network, LU lookup, GE geometry |

- **Basis of 12 quantities** (rules naming each): L loop/partial inductance 40, Cm node capacitance 29, M mutual/shared path 27, Z propagation 23, Th 22, Vcm radiating common mode 20, R 17, Res distributed resonance 16, Fab 13, Ins 8, Bal 5, Mech 3; non-physical axes Cog, Std. Every electrical quantity except Ins reduces to four PEEC primitives: R, partial-inductance matrix Lp, C/P matrix, retardation τ.
- **Regime selectors** (~14 dimensionless groups): electrical length l·√εe/(c·t_r) (> 1/6 review, > 1/2 terminate); coupling K = 1/(1+(D/h)²); return spread ℓ50 = R_s/(2πμ0f) vs aggressor–victim distance; L·di/dt / V_margin > ~0.1; fin ratio r/√(kt/2h); corner threshold f·h > ~3 GHz·mm.
- **Proxy words:** "short" touches 7 quantities, "keep away" 6, "wide" 6 ("wide" worsens Cm on switch nodes). Rule conflicts are different-quantity trades or same-quantity regime splits.

**Derivation audit.** One attempted one-line derivation per rule, which must give the rule's direction (and number) from principles, geometry and material constants, with its regime.
- Principles: P1 conservation/topology, P2 variational, P3 reciprocity/symmetry, P4 locality/scales, P5 dissipation/fluctuation, P6 information, P7 extremes and accumulation (damage).
- Verdicts: derivable / with-regime / convention / legal / habit-wrong / not derivable. Quoted numbers: derived / instance / data / arbitrary.

**Foundations.** Criterion G ("a circuit is Maxwell at zeroth order"): eliminating a hidden coordinate (mode, reflection, eddy, temperature, an edit's own redistribution) multiplies the circuit by (I − G)⁻¹ = Σ Gⁿ. "Circuit + parasitics" = the n = 1 truncation, valid iff spectral radius of G < 1. Radii:
- resonance: |δL/L| < 1/Q (first-order error (εQ)²);
- line between equal terminations: θ < ln|(m+1)/(m−1)|, m = Z0/Z;
- finite edit: collective leverage λ_max < 1 (slit across 92% of a strip: λ_max 0.977, 41× its first-order price);
- planes: kℓ_m away from 1, ℓ_m = R_s/(πμ0f) = δ²/t.

Principles F1–F7 (conservation/topology, linear passive reciprocal media, extremum principles, symmetry/images, locality and scale, dissipation/fluctuation, decisions under belief) + D (damage). Theorems T1–T13, e.g.:
- T1 impedance level: a uniform piece of delay T stores ½T(Z0ΔI² + ΔV²/Z0) ≥ TΔVΔI, equality iff Z0 = ΔV/ΔI. Between real terminations first order is a pure phase; amplitude error is second order, −(θ²/8)(m − 1/m)² (red-team corrected).
- T2: copper localises or damps, never both; Q_cu = h/max(δ, δ²/t).
- T4: exact edit price = first order ÷ (1 − leverage) (Woodbury).
- T5: budgets live on closed cycles; Kelvin sensing is a gauge statement.
- T6: the world is a node, I_CM = −jωΣC_ext·V.
- T7: topology is exact (articulation points; neck leakage ∝ w² or w⁴).

Method: closed forms (Hammerstad–Jensen, Grover, cavity via pair, Johnson via L, fin equation, IPC-2221 fit, Johnson crosstalk) + two small 2-D finite-difference solves on synthetic design points. One auditor classified all 160 rows; the audit re-derived them; `fd_gentleness.py` checked the radii by root tests on Taylor coefficients.

## Results

All [C], model vs model. Sources: [rule-basis-set](../../topics/physics/rule-basis-set.md); genealogy tables [power/analog/thermal](../../topics/physics/rule-genealogy-power-analog-thermal.md), [SI/EMI/RF](../../topics/physics/rule-genealogy-si-emi-rf.md), [routing style/DFM](../../topics/physics/rule-genealogy-routing-style-dfm.md); [derivation-audit](../../topics/physics/derivation-audit.md) (commit [19a4d7b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/19a4d7bd8f168de136541f4c068b2739c596ec03)); [foundations](../../topics/physics/foundations.md) (commit [b5c2122](https://github.com/magnetic-trowel/kicad-auto-everything/commit/b5c2122483d5c483b1ad81fc482db6f1e361379b)).

| Result | Value |
|---|---|
| Physics-origin rules about right | 80 of 91 |
| Simplicity proxies mixed | 16 of 23 |
| Habit rules wrong | 10 of 15 |
| Rules replaceable by cheap solvers | 143 of 160 (8 strictly need full-wave/FEM) |
| Rules that derive from principles | 132 of 160 (51 cleanly, 81 only with a regime); 9 conventions, 5 legal, 12 habit-wrong, 2 not derivable |
| Quoted numbers | 67: 12 derive, 23 are a budget at one regime, 14 data, 18 arbitrary |
| T1 derives | 18 rules, all self terms, no coupling rule |
| Resonance radius check | equals 1/Q to 5 digits (Q = 5/30/170) |

Selected results (numbers in the rows named; [SI/EMI/RF](../../topics/physics/rule-genealogy-si-emi-rf.md), [routing/DFM](../../topics/physics/rule-genealogy-routing-style-dfm.md), [power](../../topics/physics/rule-genealogy-power-analog-thermal.md), [audit](../../topics/physics/derivation-audit.md#nine-short-derivations)):
- 3W (S15): the same Johnson NEXT bound for every 50 Ω microstrip; far looser for thin traces on a thick two-layer board.
- Return-via inductance (S03) is logarithmic in via distance, linear in plane spacing.
- 90° corner (R01, S46): matters only above ~3–4 GHz·mm/h; DC cost about half a square. Octilinear +5.5% length, Manhattan +27% (R02).
- Wide strip off-plane (R09): 16× wider lowers L only ~48%.
- 10µ+100n+1n decaps at equal 1 nH ESL anti-resonate (P22): 1.6 Ω at 129 MHz (genealogy) vs 11 Ω with 10 mΩ ESR (audit D1); the ESR assumption differs.
- Habit-wrong: three values per pin, 0.1 µF per pin, split AGND/DGND, 20-H, "no 90° corners".
- Thermal reliefs (R25, audit D7): matter for hand/wave soldering, not reflow. Contradicts vendor guidance; needs an assembly experiment.
- Copper under inductors (P13): a body-sized cut-out keeps or raises loss; only cut-outs ≥ 2–3× winding radius help. Default: keep the plane.
- Star grounds (P45) pay only below ~6 kHz at 10 mm on 1 oz.

Red-team corrections ([redteam-corrections](redteam-corrections.md)): S18 fill-gap Z0 shift −3.7% at gap h → −5.0% at h, −1.2% at 2h, −0.4% at 3h (thin copper; converged `rt_fill_z0.py`, correction #32); "a piece is invisible when Z0 = circuit impedance" wrong as stated, T1 now carries the pure-phase first order; the "×2 notch/removal price" is a square-grid property.

## Verdict

Useful map: most rules encode a real quantity and fail by regime, not direction. Limits: one auditor's classification (agreement test RG40 proposed, not run); every verdict waits on measured boards. None of RG1–RG53 (rule store, regime predicates, proxy-word lint, myth-zoo regression suite) is implemented; `kae` uses its own closed forms in `kae/src/kae/physics/`. P7 needs a damage-norm objective class that does not exist.

## Code

`tools/research/physics/`, print-only, deterministic, synthetic inputs; run `python tools/research/physics/<script>.py [section]`:
- `rg_proxies.py` (closed forms A–W, stdlib), `rg_corners.py` (bend C/L, FD L-bend), `rg_fill_and_decaps.py` (FD microstrip with fill, decap sweep);
- `da_derivations.py`, `da_inductor_cutout.py`, `da_coverage.py` (regenerates every count from [derivation-audit-table](../../topics/physics/derivation-audit-table.md));
- `fd_gentleness.py`, `fd_impedance_level.py`.

Related: [redteam-corrections](redteam-corrections.md), [first-principles-lenses](first-principles-lenses.md), [physics-ir-and-core](physics-ir-and-core.md), [foundations-derivations](../../topics/physics/foundations-derivations.md).
