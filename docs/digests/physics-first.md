# Digest: physics-first placement and routing

Every statement links to the doc with the numbers and caveats. The philosophy is in [physics/README](../topics/physics/README.md); the ~890 ideas are in the [catalog](../ideas/physics-first/README.md). [C] means computed by our scripts: quasi-static, model against model, not yet measured.

## The idea
- **A circuit is Maxwell at zeroth order, and layout adds a series of corrections.** The series converges only inside the nearest natural mode (gentleness G). Keep each part of the realization invisible, known (budgeted with σ) or designed (a line, a damper, a sense path, an antenna). Match or damp to stay gentle. → [foundations](../topics/physics/foundations.md)
- **Seven principles plus damage:**
  - conservation and topology, with a world node;
  - linear, reciprocal media;
  - extremum;
  - symmetry;
  - locality and scale;
  - dissipation and fluctuation;
  - decisions under belief;
  - extremes and accumulation (damage).
  
  → [foundations](../topics/physics/foundations.md), [derivations](../topics/physics/foundations-derivations.md)
- **132 of 160 rules of thumb derive from them** (51 everywhere, 81 within a regime). Of the rest, 12 are habit and wrong, 9 are convention, 5 are legal and 2 are material data. Only 12 of 67 quoted numbers derive. → [derivation-audit](../topics/physics/derivation-audit.md), [table](../topics/physics/derivation-audit-table.md), [rule-basis-set](../topics/physics/rule-basis-set.md)

## What changes
- **Thirteen design theorems replace slogans:**
  - impedance level (Z0 toward ΔV/ΔI; damp with R = Z0);
  - self vs interaction objectives;
  - exact edit pricing;
  - budgets on closed loops;
  - the world as a node;
  - exact topology;
  - band-limited plane mirrors;
  - designed dissipation;
  - loss vs damage.
  
  → [foundations](../topics/physics/foundations.md) §4
- **What a conductor is doing:** the per-piece, per-band column of exact counterfactuals on every budget. It is computable with one factorization per band. → [lens-cd](../topics/physics/lens-cd.md), [real-board-passports](../topics/physics/real-board-passports.md)
- **Self terms have certified floors:** pour shapes on four open boards sit a median 4% above theirs. Losses come from reliefs and partitioning [C]. → [lens-vp](../topics/physics/lens-vp.md), [validation-program](../topics/physics/validation-program.md)
- **Exact cut law (derived four independent ways):** a slit costs (2/π)·R_s·ln sec(πx/2). The edit spectrum Σ c/(1 − λ) prices any finite edit exactly; first order holds only while λ ≪ 1. → [lens-ct](../topics/physics/lens-ct.md), [lens-sy](../topics/physics/lens-sy.md), [physics-core-v2](../topics/physics/physics-core-v2.md)
- **The R–L crossover is a length band:** ℓ_m = R_s/(π·μ0·f). Converter fundamentals return locally; the open regime is DC to tens of kHz near precision analog. → [lens-ls](../topics/physics/lens-ls.md), [lens-vp](../topics/physics/lens-vp.md)
- **Planes break E/M duality:** height is a lever for loops, not for wide dv/dt copper. Guards do little over thin dielectric. → [lens-sy](../topics/physics/lens-sy.md)
- **Damping:**
  - Copper does not damp hot-loop rings, though it damps plane pairs below ~30 MHz.
  - Tuned snubbers reach the same Q at a third of the loss.
  - Every loss is also a noise source.
  
  → [lens-th](../topics/physics/lens-th.md)
- **Off-board conductors** (cable, enclosure, heatsink) carry much of the value of information (10–84% by prior). → [lens-in](../topics/physics/lens-in.md), [lens-ct](../topics/physics/lens-ct.md)

## Domain physics
- **Power:** classify copper by waveform; height × squares, not area; via clusters by perimeter; keep the plane under shielded inductors. → [power-copper](../topics/physics/power-copper.md), [pdn-and-commutation](../topics/physics/pdn-and-commutation.md)
- **SI/EMI:**
  - The return-path EMF replaces about a dozen plane rules.
  - One worked case: removing a slot gives 24 dB, slower edges 3 dB.
  - Co-located cables give 6–48 dB by orientation.
  
  → [fields-si-emi](../topics/physics/fields-si-emi.md), [fields-emi-budget](../topics/physics/fields-emi-budget.md), [rf-geometry](../topics/physics/rf-geometry.md)
- **Thermal, HV, fab:** spreading lengths, kernel-plus-images placement scoring, HV corner fields, altitude as air density, fab limits as process physics. → [thermal-physics](../topics/physics/thermal-physics.md), [hv-and-manufacturing-physics](../topics/physics/hv-and-manufacturing-physics.md)

## The machine
- **Physics core v2:** Piece/Passport/Job on an extended graph with world conductors. It has 8 kernels sharing one factorization per band; every number is a Belief with an exactness class. → [physics-core-v2](../topics/physics/physics-core-v2.md), [API](../topics/physics/physics-core-v2-api.md)
- **Joint placement and routing on a topology-carrying state,** used as a refiner: on toy boards it improves its start by 18% and ties an equal-CPU restart portfolio. → [joint-place-route](../topics/physics/joint-place-route.md), [experiment](../topics/physics/joint-place-route-experiment.md)
- **A physics scorecard separate from cp1/cpk,** with a DRC-equivalent mutation benchmark. → [physics-critics](../topics/physics/physics-critics.md)

## Truth
- **Verification:** the core maths (cut law, wire medium, floors, duality, thermal lengths) holds under independent methods. Every computed number must pass an independent method, a refinement study and a validated reference. → [verification-and-limits](../topics/physics/verification-and-limits.md)
- **Validation:** a VOI-ranked coupon panel (ℓ_m coupon first) and a pre-registered two-arm first board (rules vs physics), with 11 kill criteria. → [validation-program](../topics/physics/validation-program.md), [coupons](../topics/physics/validation-coupons.md)
