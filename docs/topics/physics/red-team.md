# Red team: what holds, what breaks, and where physics-first loses

**TL;DR**
- **Most of the physics holds under a different method.** The cut law, the wire medium, the ℓ_m length, Q = h/δ for rings, TH's snubber tuning and VP's floors all reproduce [C]. The errors sit at the edges of validated domains, exactly where optimizers go.
- **Five headline numbers are wrong or mis-scoped.**
  - "Cables on one edge buy ~40 dB" is a script input; the board-vs-cable mode leaves 6–30 dB.
  - IN's "MS2 misses the winner by +64%" is the reference's error: PEECN's 7 equal filaments read 11–65% low on wide traces. With a graded reference it is +6.5%.
  - "Copper can never damp" fails for plane pairs below ~30 MHz: Q is 1–6 at 1–10 MHz on 0.1 mm cores.
  - "Off-board unknowns carry 33–84% of VOI" falls to 10–49% under other plausible priors; a pre-scan of the same board is worth zero to its layout.
  - The impedance-matching principle is wrong as stated: with resistive terminations, a short line's first-order effect is a pure delay for any Z0.
- **Joint place-and-route has no equal-compute win yet.** Against an equal-CPU restart portfolio it won 5 of 10 boards (median J ratio 0.96, 95% CI 0.83–1.24). The physics term's effect is 0.99 (0.93–1.05). The supported claim is narrower: routed-objective refinement improves a proxy-optimized start (10/10, −18%).
- **"Exact" and "certified" mean "inside a discretized or idealized model".** VP's floor moved 2–13% between 0.2 and 0.1 mm grids. CD's "×2" belongs to the square grid (×1.5 on a triangular grid, ×3 on a honeycomb), and its 2×10⁻⁹ is algebra, not physics. Every guarantee needs its model scope attached.
- **Physics-first loses wherever a corrected rule suffices or the decisive unknowns are off the board.** At a fixed stackup, "minimize trace length" picks the best hot loop 82–99% of the time against MS2's 97–100%. The thesis is falsifiable only against measured boards, and none exist yet.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by `rt_*` scripts in [`tools/research/physics/`](../../../tools/research/physics/). Corrections with replacement text: [red-team-corrections](red-team-corrections.md).

## Key facts

### 1. Verdicts on the fifteen load-bearing claims

| # | Claim (source) | Verdict | Evidence [C] | Fix |
|---|---|---|---|---|
| 1 | Exact cut law, ln sec and 2× notch (CT, SY, CD, VP) | **Holds** | A Galerkin crack-row solution, a method no lens used, matches (2/π)R_s ln sec(πx/2) to 6 digits, x = 0.02–0.9 ([rt_cut_law](../../../tools/research/physics/rt_cut_law.py)) | Cite as classical (Johnson; polarization tensors). DC and sheet inductance only |
| 2 | Copper Q = h/δ, "copper can never damp" (TH) | **Holds for rings, wrong for planes below ~30 MHz** | 0.1 mm, 1 oz plates: Q = 1.0/2.8/6.2/9.3 at 1/3/10/30 MHz; a 25 µm core: 4.8 at 100 MHz. Microstrip Q (w/h ≥ 0.5) is −7% to +18% of h/δ. "Reproduces round 1 exactly" is an identity ([rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py) `q`) | Scope to rings ≳ 50 MHz with h ≫ δ; count copper loss in PDN damping |
| 3 | Ring damping is a 20–27 dB lever (TH) | **Overstated by 6–8 dB** | Snubber Q values reproduce in an independent state-space model (n = 3: 0.96, 1.59 over C_oss 0.5–2×; n = 1 tuned: 1.05, 2.69). With the edge spectrum included, Q 10→1 buys 12.5–15 dB and Q 20→1 18–21 dB ([rt_damping](../../../tools/research/physics/rt_damping.py)) | Ring term = 20 log Q₀ minus the edge floor |
| 4 | Convex floors; SIMP "certified within 1.6%", human "15.8% avoidable" (VP) | **Holds on the raster only** | The math is right, but at equal area the floor fell 2.2–12.8% from the 0.2 to the 0.1 mm grid (5.6% near the headline area; VP's own logs) | Add a refinement study; "14.5–15.8% on the 0.1 mm raster" |
| 5 | ℓ50 = R_s/(2πμ0f) "whatever h"; the R–L band (VP, SY, LS) | **Holds, with three slips** | ℓ50/ℓ_m = 0.42–0.53 for h ≤ 0.1ℓ_m, but f50·ℓ = 79 Hz·m at ℓ = 3h. VP's "1.3% outside ±5 mm at ≥ 100 kHz" uses 1 − \|F\|; the current outside, \|1 − F\|, is 18% (h 0.1 mm) and 27% (1.6 mm). The band edges are for a 50 mm plane (text: 100 mm); my PEEC moves f10 and f90 by 1.4–1.6× | Quote ℓ ≥ 6h, \|1 − F\| and plane width |
| 6 | "1 oz mirrors a 5 mm loop above 12 kHz" (SY) | **Wrong** | At 12 kHz the mirrored share is 0.06. Half-mirroring needs a/ℓ_m = 2.2–4.8, i.e. ~93 kHz. LS's own 3-D table agrees with this, not with SY | 90% mirrored needs a/ℓ_m ≈ 10–45 |
| 7 | Decaps and stitching are one wire medium (LS) | **Holds** | ω_p equals the lumped anti-resonance by identity (975 MHz both). Reach ≈ 23.6 mm reproduces | The uncertainty is the input: a 2–6× via-model spread gives 1.4–2.4× in reach. Uniform lattice only |
| 8 | I_CM = −jω·ΣC_ext·V from "one electrostatic solve" (CT) | **Identity holds; not a one-solve predictor** | V must be world-referenced, which needs the cable or LISN impedance. With circuit voltages it over-predicts by \|1 + jωC_tot·Z_A\|: ≤ 5 dB for a free 5 pF board to 300 MHz, 10–29 dB at 100–300 MHz for 30 pF and 150–500 Ω ([rt_world_cm](../../../tools/research/physics/rt_world_cm.py)). CT's D2 table solved the circuit, so it is right | Pair C_ext with the CM path impedance |
| 9 | MS2 picks the PEEC-best loop 96–98%, area 16–66% (round-1 SIM) | **Holds numerically, oversold** | Graded reference: MS2 96.8%, area 17.3%. The 16% comes from candidates mixing stackups (h 0.08–1.6 mm), which no real decision does; at a fixed stackup perimeter scores 82–99% ([rt_loop_proxy](../../../tools/research/physics/rt_loop_proxy.py)) | Quote fixed-stackup numbers; the truth shares MS2's idealizations |
| 10 | Image PEEC within 1.3% of FastHenry (round 1) | **Holds in a narrow window** | 4 rectangles, w/h 0.3–5, 100 MHz. Against a graded reference, PEECN reads 11% low at w/h 10–20 and 21% low at w/h 20–60 (p10: 42% low); a 20 × 10 mm loop at w/h 50 reads 0.44 vs 1.25 nH | Make PEECN graded (≥ 31 cosine filaments); state its validity domain |
| 11 | Passports exact to 2×10⁻⁹ (CD) | **Algebra, not physics** | Rank-1 vs refactoring is an identity. ε_r = 1 electrostatics overstates world-charge shares up to ~4×; 0.5 mm cells on 0.8 mm | Report model error apart from solver error |
| 12 | EMI worked case; "topology beats tweaks by 20–40 dB" (round-1 FE) | **Partly wrong** | Case D's 40 dB is `same_edge_db=40.0`, from the PEEC voltage between the cables. The board-vs-cable mode leaves 6–30 dB (24–48 dB if the return voltage runs parallel to the cable edge). The 3 dB edge-rate figure is specific to one 50 MHz clock; the ring term is missing | Slot > cap > edge survives as one case, not a law |
| 13 | Thermal λ; kernel + images within ~2% (round-1 TM) | **Holds** | λ = 37.7 mm reproduces; all λ values (21–64 mm) agree once G_s and h_tot are named. The 2% is method vs the same fin model | Name the stackup in every λ |
| 14 | Joint beats sequential (round-1 JPR) | **Unsupported at equal CPU** | vs portfolio: 5/10, p = 1.0. vs a longer SA run at N = 30: 5/5, p = 0.06. Run-to-run sd of one board: ×1.18 ([rt_jpr_stats](../../../tools/research/physics/rt_jpr_stats.py)) | Restate as "refinement after a sequential start". Pre-register experiment 6 |
| 15 | Off-board unknowns carry 33–84% of VOI (IN) | **Prior-driven** | 84% reproduces. Offset ~U(0,10) dB: 49%. Same-edge benefit ~U(6,30) dB: 13%, and the best action becomes "reroute + slow edge". Post-build pre-scan: EVSI 0 ([rt_voi_sensitivity](../../../tools/research/physics/rt_voi_sensitivity.py)) | Sweep priors; time information correctly |

**The candidate unifying principle** (round-3 context, point 5): "a conductor is invisible to first order when Z0 equals the circuit impedance; then its only effect is delay" ([rt_impedance_match](../../../tools/research/physics/rt_impedance_match.py)) [C].
- **Resistive terminations.** H/H0 = 1/(cos θ + jκ sin θ), κ = (Z0 + Z_S·Z_L/Z0)/(Z_S + Z_L). To first order this is a pure delay κ·T_d for any Z0. Matching (Z0 = Z_S or Z_L) only removes the second-order error −(κ² − 1)θ²/2; between unequal ends an intermediate Z0 gives gain (a transformer).
- **Reactive loads.** With 30 Ω into 5 pF, the delay-only line is Z0 = R_S (0% overshoot, against 19–66% at 50–150 Ω). There is no single "circuit Z".
- **Reach.** PCB Z0 spans ~0.3–170 Ω, circuits mΩ to TΩ. Elsewhere the principle reduces to round 1's principle 2 (min L for low Z, min C for high Z).
- **Power cells.** Z0 = V/I minimizes stored energy per cycle (a loss argument); PW2's own R term moves the width 2.3×.
- **What survives** [I]: ε_L = θZ0/Z and ε_C = θZ/Z0 as regime variables, and "terminate in Z0 to absorb", which is TH's damping principle (R = √(L/C), Q ≈ 1): context points 5 and 6 are one idea.

### 2. Numbers that disagree between docs

| Conflict | Resolution |
|---|---|
| Fill at gap h: −3.7% ([genealogy](rule-genealogy-si-emi-rf.md)) vs −6.5% ([fields-si-emi](fields-si-emi.md)) | Conductor thickness (t/h 0.08 vs 0.35), and both grids are coarse. A converged solve gives −5.0% (thin) to −8.4% (t = 0.35h); ≤ 2.2% at g ≥ 2h ([rt_fill_z0](../../../tools/research/physics/rt_fill_z0.py)). "Harmless at ≥ 2h" stands |
| Heatsink 22 vs 26 pF | Both are parallel-plate estimates with different area, ε_r and pad thickness; the difference is 1.4 dB. The missing number is the heatsink's C to chassis, which decides where the current returns (CT D2) |
| λ: 21–29, 26–37, 38, 46, 52, 64 mm | All right: one to six copper layers, h_tot 10–60 W/m²K |
| Slot "0.08–0.13 nH/mm" | The law is ℓ/ln(4ℓ/g), not linear. It holds for 10–40 mm slots; PEEC reads 1.5× lower on short narrow slots and Ott's data grow as ℓ ln ℓ |
| f_x, ℓ50, ℓ_d, ℓ_m, the PW24 onset | One length up to factors of 2: ℓ50 = ℓ_d = ℓ_m/2, f_x ↔ ℓ_m = 2h, PW24 ↔ ℓ_m = a. Each "50% point" uses a different observable (L drop, containment, mirroring, share under the trace), so the "transition" moves by 10× between docs |
| CD: crack law "0.96–1.02 of exact" | The script prints 1.57 / 1.14 / 1.02 / 0.96 for 1 / 4 / 16 / 32 strips. The range holds only for 16–32 |
| MS2 bias "+9…+14%" | +7.7% against a graded reference; the rest was PEECN's own error |
| Tier names | F0–F4 + S, T0–T3, C0–C3, critic F-levels, and now an "exactness ladder". Make guarantee a field (exact / bound / estimate / calibrated) on each evaluator result, not another ladder |

### 3. Script audit

- **`sl_loop_peec.py` has a convergence bug in its reference.** Equal filaments with GMD self terms converge slowly and non-monotonically, and 7 filaments read up to 65% low at w/h ≥ 30. This propagates to IN's D4 and to MS2's quoted bias.
- **`fe_emi_budget.py`** takes case D's 40 dB as an input. **`in_emi_voi.py`** inherits it (U(35,60) dB) and lets the scan arrive before the layout decision.
- **`pw_cells.py ring`** takes R from a fixed 2-square loop while L is free, so its Q values belong to no single geometry.
- **`vp_rl_band.py`** uses 1 − |F|, and its band numbers are for a 50 mm plane.
- **`vp_floors.py`** floors depend on the grid, and the two grids used different areas (107.8 vs 104.9 mm²).
- **`cd_conductor_passport.py`** uses ε_r = 1. Its sheet sketch flags 44 of 63 high-leverage strips with 35 false flags; the board result (all found) holds only for ρ ≈ 1.
- **`th_damping_ledger.py`** models the ring without the edge spectrum.
- **`rg_fill_and_decaps.py` and `fe_field2d.py`** are both under-resolved, by 1.3–1.9 points.

Re-run and confirmed [C]: CT `cm`/`closure`/`nest`, SY duality, LS thin sheet, XD lengths, TM λ, the FE chain, TH `qcu`. Five citations checked (three in full text) are accurate.

### 4. The coordinator's thirteen points

- **Hold:** 3 (the same-edge benefit is itself a world effect), 4, 7 (self vs interaction, the strongest idea of round 2), 9, 10 (images tuned on two cases), 11 [I], 12 and 13.
- **Hold with caveats:**
  - 1: one adjoint plus the edit's polarization tensor prices small edits, Woodbury finite ones; round 1 had the topological derivative (OP41).
  - 2: at 100 kHz, 18% of the return lies outside ±5 mm, so "fundamentals return under the loop" needs f_sw ≳ 300 kHz on 1 oz.
  - 8: "exact" holds only within each model.
- **Wrong as stated:** 5 (see above) and 6 (planes). The Q ledger as LS's representation trigger is plausible [I].

### 5. Where physics-first loses: the rule-based expert, steelmanned

1. **Rules are robust policies; optimizers spend margin where the model is confident.** "Connectors on one edge" and "solid reference under fast nets" work across unknown enclosures, cables, part substitutions and fab spread; IN's D5 shows a robust action caps the value of information. An optimizer drifts to where its model is least validated, as PEECN's spurious reward for width at w/h > 30 shows.
2. **Rules are calibrated by failures; our numbers by other models.** No [C] number here has met a measurement.
3. **Rules cover unmodeled physics.** One keep-out guards against C, M, heat, ESD and stress at once; we model no ESD, immunity, nonlinear victims or mechanics. Optimizing modeled terms can spend unmodeled margin (trimmed copper: plating imbalance, warpage; organic shapes: review time).
4. **Rules need no inputs we lack.** Physics needs the stackup with tolerances, C_oss(V), edge rates, cables and the enclosure. With default inputs, a physics engine is a rule engine with more failure modes.
5. **The big computed wins are rules.** No slot under the net (24–38 dB), thin dielectric (15–17 dB) and connectors together are textbook rules. What geometry optimization adds (−14.5% pour loss, MS2's 98% vs perimeter's 95%) is the size of fab and part tolerance.
6. **A corrected rule often suffices.** At a fixed stackup the decisive step was replacing "minimize area" (66–97%) with "minimize length × h/w" (82–99%), not solving fields.

**Physics wins** [I] where rules conflict, at regime boundaries, on out-of-distribution designs, where trades must be priced (SW copper at 400 V), and as a generator of corrected rules.

**What would falsify the thesis.** Any one of these, pre-registered:
- On ≥ 10 measured boards (ripple, overshoot, pre-scan, IR), physics-critic scores rank outcomes no better than a rule-violation count (ΔSpearman < 0.1).
- Physics-optimized layouts beat rule-following ones by no more than measurement and fab scatter (≈ 2–3 dB, 10% ripple, 2 K) at equal cost.
- Joint P&R fails to beat an equal-CPU sequential portfolio on ≥ 20 real boards.
- Physics critics cannot tell autorouted boards from human ones above their false-alarm rate.

### 6. Overreach

- **Tags.** Some [C] tags sit on inputs or identities (the 40 dB; TH's "reproduces exactly"; CD's "exact"). "80 of 91" is one auditor's judgement [I]. "Topology beats tweaks" and "off-board unknowns are the most valuable" are single-case or prior-driven [I] stated as laws. No [P] tag checked was false.
- **Architecture presented as result.** "One adjoint solve prices every copper edit" (README). S1's two-solve gradient "for every pad pose", which ignores topological events and periodic adjoints. LS's "closes most of gap 2", which holds for intact thin planes only. VP's "certified", which holds on the raster only.
- **One idea, several names; merge them.**
  - cut pricing: CT1, CT2, SY6–SY9, VP D4, CD2, CD6;
  - regime selector: LS5, LS12, VP17, SY25, CT26, CD17;
  - antiphase pairing: SY16 = CT10;
  - loop-honest ledger: CT22, SY22/23, CD9, CD11;
  - topological events: CT28 = CD27;
  - damping: TH1/2/4/6, VP15, VP18, LS15;
  - world node: CT9, CT15, CT16, IN6, SY27, CD33, TH11.
- **Independence.** The lenses ran in sequence and cite each other. "Found four ways" means four routes to textbook results: good for correctness, not novelty. The passport sections converge because the brief asked for them.

## Recommendations for our system

1. **A three-part check for every [C] number the architecture uses:** an independent method, a refinement study, and a reference whose validated domain covers where the optimizer selects. Put it in the regression suite ([research-gaps](research-gaps.md) gap 20); it would have caught every error above.
2. **Replace PEECN's 7 equal filaments with graded filaments (≥ 31)** or converged 2-D L′ plus corner terms. Then re-run IN D2, D4 and §4.
3. **EMI chain.** Replace `same_edge_db` with a board-vs-cable term from the charge identity and region capacitances. Add a ring term with the edge floor (TH6).
4. **Every guarantee carries its scope** ("raster 0.1 mm", "square grid", "ideal plane, HF"). Report model error separately from solver error.
5. **Restate the impedance principle** as the (ε_L, ε_C) regime pair plus "terminate to absorb". Re-scope "copper cannot damp" to rings.
6. **Joint P&R.** Freeze architecture claims until experiment 6 runs with the equal-CPU portfolio control on ≥ 20 boards, pre-registered.
7. **VOI.** Report results over a sweep of priors, and time information honestly: before layout, after build, or for the next board in the class.

## Conflicts and open questions

- My same-edge and CM estimates are lumped and quasi-static with plate capacitances: they show a constant 40 dB is wrong, not what replaces it. A full-wave board-plus-cable run should settle it.
- The graded reference is still unconverged at w/h ≥ 30 (+4–7% from 31 to 61 filaments); Hammerstad–Jensen plus corner terms may be cheaper.
- The plate Q assumes wide plates; narrow traces and vias add loss.
- Physics vs rules has no data either way; the steelman is an argument.

## Sources

- Scripts [C]: the nine `rt_*.py` linked above (they reuse `sl_loop_peec`, `in_decision_quality` and `in_emi_voi` unchanged), plus re-runs of the scripts named in §3.
- [P], checked in full text: Kotiuga & Lahtinen, [arXiv:1809.01002](https://arxiv.org/abs/1809.01002); Benz et al., [arXiv:1101.0312](https://arxiv.org/abs/1101.0312); Liu & Belcher, [arXiv:0712.0182](https://arxiv.org/abs/0712.0182) eq. (1).
- [S]: Wheeler's incremental-inductance rule (Proc. IRE 1942); Foster's theorem; Hockanson et al., IEEE T-EMC 38(4), 1996 (single-cable current-driven CM).

See also: [red-team-corrections](red-team-corrections.md) · [README](README.md) · [research-gaps](research-gaps.md) · lenses [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md)
