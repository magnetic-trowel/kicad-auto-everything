# Rule genealogy, derivation audit and foundations

**Status:** partial (analysis computed model-vs-model; nothing built into the tools, nothing measured).
**First published:** 2026-10-22, commit [0822bd7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0822bd7f76d20a1683abd9eb2292aab23144744c) on branch `claude/vigilant-mayer-i91rrr`.

We took 160 PCB layout rules of thumb, decompressed each into the physical quantity it protects and the regime where it binds, then tried to derive each from seven principles. 132 of 160 derive (most only with a stated regime), but only 12 of the 67 numbers the rules quote do. **Every number on this page is a model-against-model computation (closed forms, small 2-D field solves); none has been checked against a measurement.**

## Idea and how it works

**Genealogy (workstream 1).** Each rule gets one record: `{slogan, origin, basis quantity, governing equation, "binds when" predicate, replacement budget, solver cost}` (idea RG1 in [rule-replacements](../../ideas/physics-first/rule-replacements.md)).
- Rules: P01–P59 power/analog/isolation/thermal, S01–S55 SI/EMI/RF, R01–R46 routing style/DFM.
- Origin codes: Ph physics, Mf manufacturing, Hb habit, Sp simplicity proxy, Cg cognition, Tl tool, Lg legal.
- Verdicts: R about right, C conservative, A anti-conservative, M mixed, X wrong, CT contested.
- Solver cost: CF closed form, 2D, PEEC, FW full-wave, SP SPICE, TN thermal network, LU lookup, GE geometry.
- **Basis of 12 quantities:** L (loop/partial inductance), M (mutual/shared path), Cm (node capacitance), R, Z (propagation), Bal, Vcm (radiating common mode), Res (distributed resonance), Ins, Th, Mech, Fab; plus two non-physical axes Cog and Std. Counts of rules naming each: L 40, Cm 29, M 27, Z 23, Th 22, Vcm 20, R 17, Res 16, Fab 13, Ins 8, Bal 5, Mech 3. Every electrical quantity except Ins reduces to four PEEC primitives: R, the partial-inductance matrix Lp, the C/P matrix and retardation τ.
- **Regime selectors** (about 14 dimensionless groups) decide when a rule binds, e.g. electrical length l·√εe/(c·t_r) (> 1/6 review, > 1/2 terminate); coupling factor K = 1/(1+(D/h)²); return spread ℓ50 = R_s/(2πμ0f) against aggressor–victim distance; L·di/dt / V_margin > ~0.1; fin ratio r/√(kt/2h); corner threshold f·h > ~3 GHz·mm.
- **Proxy words decoded:** "short" touches 7 quantities, "keep away" 6, "wide" 6 (and "wide" makes Cm worse on switch nodes). Rule conflicts are either different-quantity trades or same-quantity regime splits.

**Derivation audit.** Each rule gets one attempted one-line derivation that must give the rule's direction (and number) from principles, geometry and material constants, and state its regime. Principle codes P1 conservation/topology, P2 variational, P3 reciprocity/symmetry, P4 locality/scales, P5 dissipation/fluctuation, P6 information, P7 extremes and accumulation (damage). Verdicts: derivable / with-regime / convention / legal / habit-wrong / not derivable. Quoted numbers: derived / instance / data / arbitrary.

**Foundations.** The organising criterion G ("a circuit is Maxwell at zeroth order"): eliminating a hidden coordinate (mode, reflection, eddy, temperature, an edit's own redistribution) multiplies the circuit by (I − G)⁻¹ = Σ Gⁿ. "Circuit + parasitics" methods are the n = 1 truncation, valid iff the spectral radius of G is < 1. Radii:
- resonance: |δL/L| < 1/Q (first-order error (εQ)²);
- line between equal terminations: θ < ln|(m+1)/(m−1)|, m = Z0/Z;
- finite edit: collective leverage λ_max < 1 (a slit across 92% of a strip has λ_max 0.977, 41× its first-order price);
- planes: kℓ_m away from 1, ℓ_m = R_s/(πμ0f) = δ²/t.

Principles F1–F7 (conservation/topology, linear passive reciprocal media, extremum principles, symmetry/images, locality and scale, dissipation/fluctuation, decisions under belief) plus D (damage). Theorems T1–T13, for example:
- T1 impedance level: a uniform piece of delay T stores ½T(Z0ΔI² + ΔV²/Z0) ≥ TΔVΔI, equality iff Z0 = ΔV/ΔI. Between real terminations the first-order effect is a pure phase and the amplitude error is second order, −(θ²/8)(m − 1/m)² (as corrected by the red team, see below).
- T2: copper localises or damps, never both; Q_cu = h/max(δ, δ²/t).
- T4: exact edit price = first order ÷ (1 − leverage) (Woodbury).
- T5: budgets live on closed cycles; Kelvin sensing is a gauge statement.
- T6: the world is a node, I_CM = −jωΣC_ext·V.
- T7: topology is exact (articulation points; neck leakage ∝ w² or w⁴).

## What we tried

Closed forms (Hammerstad–Jensen, Grover, cavity via pair, Johnson via L, fin equation, IPC-2221 fit, Johnson crosstalk) plus two small 2-D finite-difference solves, all on synthetic design points. One auditor classified all 160 rows; the audit re-derived them; `fd_gentleness.py` checked the radii by root tests on Taylor coefficients.

## Results

All [C] = computed, model vs model. Sources: [rule-basis-set](../../topics/physics/rule-basis-set.md), the three genealogy tables ([power/analog/thermal](../../topics/physics/rule-genealogy-power-analog-thermal.md), [SI/EMI/RF](../../topics/physics/rule-genealogy-si-emi-rf.md), [routing style/DFM](../../topics/physics/rule-genealogy-routing-style-dfm.md)), [derivation-audit](../../topics/physics/derivation-audit.md) (commit [19a4d7b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/19a4d7bd8f168de136541f4c068b2739c596ec03)), [foundations](../../topics/physics/foundations.md) (commit [b5c2122](https://github.com/magnetic-trowel/kicad-auto-everything/commit/b5c2122483d5c483b1ad81fc482db6f1e361379b)).

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

Selected computed numbers:
- 3W gives the same 2.8% Johnson NEXT bound for every 50 Ω microstrip, but 80% for 0.25 mm traces on a 1.6 mm 2-layer board.
- Return-via inductance (μ0d/π)·ln(s/a): moving the via from 5 to 1.3 mm saves ~40%; halving d saves 50%.
- A 90° corner reaches −20 dB at ~3–4 GHz·mm/h (1.9–2.6 GHz on 1.5 mm); its DC cost is 0.56 squares. Octilinear routing costs +5.5% length, Manhattan +27%.
- A 16× wider strip off-plane lowers L only ~48%.
- 10µ+100n+1n decaps with equal 1 nH ESL anti-resonate (1.6 Ω peak at 129 MHz in the genealogy, 11 Ω with 10 mΩ ESR in audit D1; the ESR assumption differs).
- Habit-wrong examples: three values per pin, 0.1 µF per pin, split AGND/DGND, 20-H, "no 90° corners".
- Audit D7: thermal reliefs matter for hand/wave soldering (1.8–4.2×) but not in reflow (pad coupling 0.1 mW/K to the oven vs 27–54 mW/K to the plane). This contradicts vendor guidance and needs an assembly experiment.
- Audit P13 (copper under inductors, axisymmetric air-core eddy model): a body-sized cut-out keeps or raises loss (1.05–1.4×); only cut-outs ≥ 2–3× the winding radius help. Default: keep the plane.
- Star grounds pay only below ~6 kHz at 10 mm on 1 oz.

**Red-team corrections that touch this page** ([redteam-corrections](redteam-corrections.md)):
- S18 fill-gap Z0 shift: −3.7% at gap h was replaced by −5.0% at h, −1.2% at 2h, −0.4% at 3h (thin copper), from the converged `rt_fill_z0.py` (correction #32).
- The original "a piece is invisible when Z0 = circuit impedance" was wrong as stated; T1 now carries the pure-phase first order.
- The "×2 notch/removal price" is a property of the square grid.

## Verdict

A useful map: most rules encode a real quantity, and they fail by regime, not by direction. But it is one auditor's classification (an agreement test, RG40, was proposed and not run), and every verdict waits on measured boards. None of RG1–RG53 (rule store, regime predicates, proxy-word lint, myth-zoo regression suite) is implemented; `kae` uses its own closed forms in `kae/src/kae/physics/` instead. P7 needs a damage-norm objective class that does not exist.

## Code

`tools/research/physics/`, print-only, deterministic, synthetic inputs:
- `rg_proxies.py` (closed forms A–W, stdlib), `rg_corners.py` (bend C/L, FD L-bend), `rg_fill_and_decaps.py` (FD microstrip with fill, decap sweep).
- `da_derivations.py`, `da_inductor_cutout.py`, `da_coverage.py` (regenerates every count from [derivation-audit-table](../../topics/physics/derivation-audit-table.md)).
- `fd_gentleness.py`, `fd_impedance_level.py`.

Run `python tools/research/physics/<script>.py [section]`.

## Related

[redteam-corrections](redteam-corrections.md), [first-principles-lenses](first-principles-lenses.md), [physics-ir-and-core](physics-ir-and-core.md), [foundations-derivations](../../topics/physics/foundations-derivations.md).
