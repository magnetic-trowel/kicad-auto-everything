# Digest: physics-first placement and routing

Scope: physics-first conclusions; [C] = computed, model against model, never measured. Not here: rule packs -> [rules-hs-emi-interfaces](rules-hs-emi-interfaces.md), [rules-power-rf-analog-dfm](rules-power-rf-analog-dfm.md); evaluation stack -> [practice-evaluation](practice-evaluation.md). Ideas: [catalog](../ideas/physics-first/README.md); runs: [research/physics](../research/physics/README.md).
Keys: physics-first, gentleness G, F1–F7, T1–T13, derivation audit, conductor passport, cut law, edit spectrum, ℓ_m, R–L crossover, copper damping, tuned snubber, return-path EMF, physics scorecard, red team, kill criteria, coupons, reduced-order model, intent objective

## The idea
- Circuit = Maxwell at zeroth order; layout corrections converge only while ρ(G) < 1; keep each part invisible, known (σ-budgeted) or designed; match or damp to stay gentle. → [zeroth order](../topics/physics/foundations.md#the-circuit-is-the-zeroth-order)
- Seven principles F1–F7 (conservation/topology with a world node, linear media, extremum, symmetry, locality, dissipation, belief) plus damage. → [principles](../topics/physics/foundations.md#seven-first-principles)
- 132 of 160 rules of thumb derive (51 everywhere, 81 within a regime); 12 habit-wrong, 9 convention, 5 legal, 2 not derivable; only 12 of 67 quoted numbers derive. → [coverage](../topics/physics/derivation-audit.md#coverage-c-da_coverage)

## What changes
- Theorems T1–T13 replace slogans. → [derivation tree](../topics/physics/foundations.md#design-theorems-the-derivation-tree)
- T1 (restated by the red team): first order a line is a pure delay for any Z0; Z0 = ΔV/ΔI minimizes stored energy; damp with R = Z0. → [T1](../topics/physics/foundations.md#theorem-t1-impedance-level)
- A conductor's passport = its exact counterfactuals on every budget, per band, from one factorization per band. → [passport](../topics/physics/lens-cd.md#7-what-each-conductor-is-doing-the-passport)
- Certified floors: pours on 4 real boards sit a median 4% above theirs; loss comes from reliefs and partitioning [C]. → [lens-vp](../topics/physics/lens-vp.md#use-in-kae)
- Cut law ΔR = (2/π)R_s·ln sec(πx/2) holds to 6 digits under an independent Galerkin check; the four lenses' agreement is not independent evidence. → [verified](../topics/physics/verification-and-limits.md#1-claims-verified-by-an-independent-method)
- Edit spectrum ΔZ = Σ c_i/(1 − λ_i) prices any finite edit exactly; first order holds only while λ ≪ 1. → [edit spectrum](../topics/physics/physics-core-v2.md#4-the-edit-spectrum-when-cheap-physics-holds)
- R–L crossover is a length band, ℓ50 ≈ ℓ_m/2 with ℓ_m = R_s/(π·μ0·f), valid for ℓ ≥ 6h; the open regime is DC to tens of kHz near precision analog. → [lens-vp](../topics/physics/lens-vp.md#lens-vp-variational-principles-and-energy), [mirroring](../topics/physics/lens-sy.md#3-more-derivations-checked-against-computed-numbers-c)
- Planes break E/M duality: height is a lever on loops, not wide dv/dt copper; guards do little over thin dielectric. → [lens-sy](../topics/physics/lens-sy.md#lens-sy-symmetry-reciprocity-and-duality)
- Copper cannot damp hot-loop rings above ~50 MHz but does damp plane pairs below ~30 MHz on thin cores; Q 10–20 → ~1 buys 12–21 dB at the ring band; a tuned snubber matches textbook Q at a third of the loss. → [lens-th](../topics/physics/lens-th.md#2-derivation-map-then-derivations)
- Off-board unknowns carry 33–84% of VOI under the original prior, 10–49% under others. → [lens-in](../topics/physics/lens-in.md#5-the-measurement-program-as-experiment-design)

## Domain physics
- Power: classify copper by waveform; near a plane loop L is height × squares, not area. → [classify](../topics/physics/power-copper.md#1-node-and-branch-classification-the-decision-procedure), [loops](../topics/physics/pdn-and-commutation.md#1-commutation-loop-geometry)
- SI/EMI: one return-path EMF replaces about a dozen plane rules; in one worked case removing a slot buys 24–38 dB, edge rate 2.5–3 dB, cable points on one edge 6–48 dB by orientation. → [metric](../topics/physics/fields-si-emi.md#3-the-one-metric-return-path-emf), [dB ranking](../topics/physics/fields-emi-budget.md#3-what-buys-db-in-order-this-case)
- Thermal: superposition with edge images scores placements within ~2% of a full solve [C]. → [superposition](../topics/physics/thermal-physics.md#placement-scoring-by-superposition)
- HV and fab: spacing is three insulation problems; altitude is Paschen similarity; fab limits are process physics. → [HV/mfg](../topics/physics/hv-and-manufacturing-physics.md#insulation-is-three-physics-problems)

## The machine
- Formal problem J ≈ ⟨W, Z(D)⟩, three solver tiers: feasible [I], no measured ground truth. → [feasibility](../topics/architecture/physics-driven-design.md#7-feasibility)
- Engine (not built): one operator per band factored once per epoch; Schur windows; rank-k commits. → [engine](../topics/architecture/physics-engine-design.md#results)
- One Galerkin reduced model covers DC to the quasi-static limit (R2 gate passed on boost and chaac); hop-port prices scored better on two bands, worse wideband. → [R2](../topics/architecture/physics-frequency-coverage.md#r2-on-boost-passed), [hop ports](../topics/architecture/physics-hop-ports.md#pricing-a-hop-through-the-port-of-the-connection-it-replaces-stage-r4b)
- Intent sets the objective (lexicographic tiers, exchange rates) because assumed bounds were hidden exchange rates; intent widths beat the human on copper loss on boost; locked power routing blocks dense boards. → [objective](../topics/architecture/intent-driven-objectives.md#objective-formulation), [runs](../research/physics/field-solver-routing-and-intent.md#what-did-not-work)
- Fast place terms rank like PEEC at ~10k moves/s; exact physics before routing changed few decisions. → [terms](../research/placement/kae-physics-terms.md#verdict), [exact](../research/placement/kae-exact-physics-before-routing.md#verdict)
- Joint place-and-route is a refiner: −18% vs its own start (10/10), ties an equal-CPU restart portfolio (5/10). → [experiment](../topics/physics/joint-place-route-experiment.md#results-c)
- The physics scorecard sits beside cp1/cpk and never feeds them; a DRC-clean-but-physically-wrong mutation benchmark tests the critics. → [critics](../topics/physics/physics-critics.md#5-the-drc-clean-but-physically-wrong-benchmark)
- On 112 suite boards one via carries a whole rail on 102/335 rails; Freerouting doubles the worst rail drop (median ×1.9) [C]. → [suite](../research/physics/physics-critics-and-passports.md#results)
- `kae.circuit` brief (netlist only) finds hot loops reliably; capacitor ownership 74.7% vs 38.0% baseline. → [accuracy](../research/placement/kae-comprehension-brief.md#weak-labels-from-the-human-placement-c)
- `kae.sim` compares ideal and routed circuits in ngspice at every corner. → [kae.sim](../topics/architecture/functional-evaluator.md#7-results-m)

## Truth
- Red team: ~1/4 of load-bearing claims wrong, overstated or circular (12 kHz mirroring, "copper never damps", Z0-matching invisibility, 40 dB cable benefit). → [red team](../research/physics/redteam-corrections.md#results)
- Each computed number needs an independent method, a refinement study and a reference validated where the optimizer selects. → [verification](../topics/physics/verification-and-limits.md#verification-and-limits)
- Validation plan: VOI-ranked coupons (LM first), pre-registered two-arm board VAL-1, 11 kill criteria; nothing fabricated. → [kill criteria](../topics/physics/validation-program.md#5-kill-criteria), [coupons](../topics/physics/validation-coupons.md#2-the-panel-ranked)
