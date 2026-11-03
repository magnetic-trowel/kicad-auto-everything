# Verification and limits

Scope: which computed claims passed an independent method, the validated domain and scope of each script and quantity, where competent rule-following beats physics-first, falsification tests, and how independent the evidence is. Not here: the measurement plan -> [validation-program](validation-program.md); critic validation -> [physics-critics-validation](physics-critics-validation.md).
Keys: independent method, refinement study, validated domain, model scope, cut law, Q = h/δ, snubber tuning, ℓ50, ℓ_m, wire medium, world-charge identity, T1 first-order delay, MS2, PEECN filaments, graded filaments, thermal length λ, ground fill Z0, VOI prior sweep, steelman of rule-based expert, falsification, one idea several ids, rt_*.py

Tags: [P] primary, [S] secondary, [I] inference, [C] computed (model against model, uncalibrated) by the `rt_*` scripts in [`tools/research/physics/`](../../../tools/research/physics/).

**Results:**
- Three checks per computed number: an independent method, a refinement study, a reference validated where the optimizer selects. Optimizers drift to the edges of validated domains, so that is where the checks bind. Put them in the regression suite ([research-gaps](research-gaps.md) gap 20).
- "Exact" and "certified" mean "inside a discretized or idealized model" (floors, removal prices and rank-1 passports all carry a grid or algebra scope, §1). Every guarantee carries its scope ("raster 0.1 mm", "square grid", "ideal plane, HF"); model error is reported apart from solver error.

## 1. Claims verified by an independent method

| Claim (doc) | Independent method (script) | Agreement [C] | Validated domain and scope |
|---|---|---|---|
| Cut law (2/π)R_s·ln sec(πx/2), 2× edge notch ([lens-ct](lens-ct.md), [lens-sy](lens-sy.md), [lens-cd](lens-cd.md), [lens-vp](lens-vp.md)) | Galerkin crack-row solution ([rt_cut_law](../../../tools/research/physics/rt_cut_law.py)) | 6 digits, x = 0.02–0.9; classical (Johnson; polarization tensors) | DC and sheet inductance. The ×2 interior removal price is a square-grid property (×1.5 triangular, ×3 honeycomb). CD's strip model gives 1.57 / 1.14 / 1.02 / 0.96 of exact at 1 / 4 / 16 / 32 strips: use ≥ 16 |
| Copper Q = h/δ ([lens-th](lens-th.md)) | plate and microstrip eddy model ([rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py) `q`) | microstrip (w/h ≥ 0.5): −7% to +18% of h/δ | rings ≳ 50 MHz with h ≫ δ. A 0.1 mm, 1 oz plane pair: Q = 1.0 / 2.8 / 6.2 / 9.3 at 1 / 3 / 10 / 30 MHz (25 µm core: 4.8 at 100 MHz), so copper loss counts in PDN damping |
| Snubber tuning L_s·C_s ≈ L·C_oss ([lens-th](lens-th.md) D3) | state-space ring model ([rt_damping](../../../tools/research/physics/rt_damping.py)) | Q 0.96 and 1.59 (n = 3) over C_oss 0.5–2×; tuned n = 1: 1.05 and 2.69 | with the edge spectrum, Q 10 → 1 buys 12.5–15 dB, Q 20 → 1 18–21 dB: ring term = 20 log Q₀ minus the edge floor |
| Convex copper floors ([lens-vp](lens-vp.md)) | grid refinement | math holds; at equal area the floor falls 2.2–12.8% from 0.2 to 0.1 mm grid (5.6% near the headline area) | "within 1.6% of the floor" and "14.5–15.8% avoidable" hold on the 0.1 mm raster |
| ℓ50 = R_s/(2πμ0f) and the R–L band ([lens-vp](lens-vp.md), [lens-sy](lens-sy.md), [lens-ls](lens-ls.md)) | separate PEEC | ℓ50/ℓ_m = 0.42–0.53 for h ≤ 0.1ℓ_m; band edges f10, f90 within 1.4–1.6× | ℓ ≥ 6h (at ℓ = 3h, f50·ℓ = 79 Hz·m). Current outside = \|1 − F\|: 18% outside ±5 mm at 100 kHz for h = 0.1 mm, 27% at 1.6 mm; band numbers for a 50 mm plane |
| Loop mirroring by a plane ([lens-sy](lens-sy.md), [lens-ls](lens-ls.md)) | 2-D sheet model ([rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py)) vs LS's 3-D table | agree | half-mirroring needs a/ℓ_m = 2.2–4.8 (~93 kHz for a 5 mm loop on 1 oz; share 0.06 at 12 kHz); 90% needs a/ℓ_m ≈ 10–45. "Fundamentals return under the loop" needs f_sw ≳ 300 kHz on 1 oz |
| Decaps and stitching as one wire medium ([lens-ls](lens-ls.md)) | lumped anti-resonance | ω_p equal by identity (975 MHz both); reach ≈ 23.6 mm reproduces | uniform lattice; a 2–6× via-model spread gives 1.4–2.4× in reach (input uncertain, not the method) |
| World-charge identity I_CM = −jω·ΣC_ext·V ([lens-ct](lens-ct.md) D2) | circuit solve with cable impedance ([rt_world_cm](../../../tools/research/physics/rt_world_cm.py)) | identity holds; CT's D2 table solves the circuit | V must be world-referenced; circuit voltages over-predict by \|1 + jωC_tot·Z_A\|: ≤ 5 dB for a free 5 pF board to 300 MHz, 10–29 dB at 100–300 MHz for 30 pF and 150–500 Ω. Pair C_ext with the CM path impedance |
| T1 first-order delay ([foundations](foundations.md) §3) | terminated-line transfer ([rt_impedance_match](../../../tools/research/physics/rt_impedance_match.py)) | H/H0 = 1/(cos θ + jκ sin θ), κ = (Z0 + Z_S·Z_L/Z0)/(Z_S + Z_L): pure delay κ·T_d to first order for any Z0; matching removes the second-order error −(κ² − 1)θ²/2 | resistive terminations; between unequal ends an intermediate Z0 is a transformer. 30 Ω into 5 pF is delay-only at Z0 = R_S (0% overshoot vs 19–66% at 50–150 Ω). Outside the ~0.3–170 Ω PCB Z0 spans, T1 reduces to min L for low-Z and min C for high-Z pieces. In power cells PW2's R term moves the width 2.3× |
| Loop proxy MS2 ([lens-in](lens-in.md)) | graded-filament PEEC reference ([rt_loop_proxy](../../../tools/research/physics/rt_loop_proxy.py)) | MS2 picks the best loop 96.8%, area 17.3% (stackups mixed); MS2 bias +7.7% | fixed stackup: perimeter 82–99%. Reference shares MS2's idealizations. Full table: [solver-ladder](solver-ladder.md#measured-trust-radii-for-loop-inductance-c) |
| Image PEEC (PEECN) | FastHenry | within 1.3% | 4 rectangles, w/h 0.3–5, 100 MHz. With 7 equal filaments PEECN reads 11% low at w/h 10–20, 21% at 20–60 (p10: 42%), up to 65% at w/h ≥ 30: use ≥ 31 graded (cosine) filaments, or converged 2-D L′ + corner terms, outside w/h 0.3–5 |
| Passport counterfactuals ([lens-cd](lens-cd.md)) | refactoring | rank-1 updates match to 2×10⁻⁹ (solver error only) | model error separate: ε_r = 1 electrostatics overstates world-charge shares up to ~4× (0.5 mm cells on 0.8 mm) |
| Thermal length λ ([thermal-physics](thermal-physics.md)) | recomputed from G_s and h_tot | λ = 37.7 mm reproduces; 21–64 mm across docs agree once both are named | 1–6 copper layers, h_tot 10–60 W/m²K. The ~2% kernel + images figure is method vs the same fin model, not independent |
| Ground fill Z0 shift ([rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md)) | converged 2-D solve ([rt_fill_z0](../../../tools/research/physics/rt_fill_z0.py)) | −5.0% at gap h (thin copper) to −8.4% (t = 0.35h); ≤ 2.2% at g ≥ 2h | fill harmless at ≥ 2h |
| Off-board share of VOI ([lens-in](lens-in.md)) | prior sweep ([rt_voi_sensitivity](../../../tools/research/physics/rt_voi_sensitivity.py)) | 84% reproduces under its prior | 10–49% under other plausible priors (offset ~U(0,10) dB: 49%; same-edge benefit ~U(6,30) dB: 13%, best action becomes "reroute + slow edge"). A post-build pre-scan has EVSI 0 for that board's own layout. Report VOI over a prior sweep; time information honestly (before layout, after build, next board in class) |
| Joint place-and-route ([joint-place-route-experiment](joint-place-route-experiment.md)) | equal-CPU restart portfolio; paired statistics ([rt_jpr_stats](../../../tools/research/physics/rt_jpr_stats.py)) | refinement improves a proxy-optimized start 10/10 (−18%) | vs portfolio: 5/10, p = 1.0 (median J ratio 0.96, 95% CI 0.83–1.24); physics term 0.99 (0.93–1.05); vs longer SA at N = 30: 5/5, p = 0.06; run-to-run sd ×1.18. Architecture claims wait for experiment 6: equal-CPU portfolio control, ≥ 20 boards, pre-registered |

Reproduced by re-running (same method; reproducibility only) [C]: CT `cm`/`closure`/`nest`, SY duality, LS thin sheet, XD lengths, TM λ, the FE chain, TH `qcu`. Five cited sources checked against the text (three in full): accurate.

## 2. Script and quantity scopes

| Script or quantity | Scope |
|---|---|
| `sl_loop_peec.py` (PEECN) | equal filaments with GMD self terms converge slowly and non-monotonically; 7 filaments read up to 65% low at w/h ≥ 30; valid at w/h 0.3–5 |
| `fe_emi_budget.py`, `in_emi_voi.py` | same-edge benefit is an input (`same_edge_db`), not a result; a lumped board-vs-cable estimate gives 6–30 dB (24–48 dB if the return voltage runs parallel to the cable edge). `in_emi_voi.py` draws it from U(35,60) dB and times the scan before the layout decision. The worked case's order slot > cap > edge is one case, not a law; its 3 dB edge-rate figure is specific to one 50 MHz clock and omits the ring term. Fix: compute the same-edge benefit as a board-vs-cable term from the charge identity and region capacitances; add a ring term with the edge floor (TH6) |
| `pw_cells.py ring` | R from a fixed 2-square loop while L is free: its Q values belong to no single geometry |
| `vp_rl_band.py` | reports 1 − \|F\|, not current outside \|1 − F\|; band numbers for a 50 mm plane |
| `vp_floors.py` | floors grid-dependent; its two grids used different areas (107.8 vs 104.9 mm²) |
| `cd_conductor_passport.py` | ε_r = 1; its sheet sketch flags 44 of 63 high-leverage strips with 35 false flags; board result holds for ρ ≈ 1 |
| `th_damping_ledger.py` | ring model without the edge spectrum |
| `rg_fill_and_decaps.py`, `fe_field2d.py` | under-resolved by 1.3–1.9 points |
| f_x, ℓ50, ℓ_d, ℓ_m, PW24 onset | one length up to factors of 2: ℓ50 = ℓ_d = ℓ_m/2, f_x ↔ ℓ_m = 2h, PW24 ↔ ℓ_m = a. Each "50% point" uses a different observable (L drop, containment, mirroring, share under the trace), so a "transition" moves up to 10× with the observable: name it ([vocabulary](vocabulary.md)) |
| Slot inductance "0.08–0.13 nH/mm" | law is ℓ/ln(4ℓ/g), not linear; per-mm figure holds for 10–40 mm slots; PEEC reads 1.5× lower on short narrow slots; Ott's data grow as ℓ ln ℓ |
| Heatsink capacitance 22–26 pF | parallel-plate estimates differing in area, ε_r, pad thickness (1.4 dB). Deciding number: heatsink C to chassis, which sets where current returns (CT D2) |

## 3. Where competent rule-following beats physics-first

Steelman of the rule-based expert (the baseline [validation-program](validation-program.md) must beat):
1. **Rules are robust policies; optimizers spend margin where the model is confident.** "Connectors on one edge" and "solid reference under fast nets" work across unknown enclosures, cables, substitutions, fab spread; [lens-in](lens-in.md) D5: a robust action caps VOI. Optimizers drift to where models are least validated (PEECN with 7 equal filaments rewards width spuriously at w/h > 30).
2. **Rules are calibrated by failures; our numbers by other models.** No [C] number here has met a measurement.
3. **Rules cover unmodeled physics.** One keep-out guards C, M, heat, ESD and stress; we model no ESD, immunity, nonlinear victims or mechanics. Optimizing modeled terms can spend unmodeled margin (trimmed copper: plating imbalance, warpage; organic shapes: review time).
4. **Rules need no inputs we lack.** Physics needs stackup with tolerances, C_oss(V), edge rates, cables, enclosure; with default inputs a physics engine is a rule engine with more failure modes.
5. **The big computed wins are rules:** no slot under the net (24–38 dB), thin dielectric (15–17 dB), connectors together. Geometry optimization adds (−14.5% pour loss, MS2's 98% vs perimeter's 95%) about the size of fab and part tolerance.
6. **A better rule often suffices:** at fixed stackup "minimize length × h/w" picks the best loop 82–99%, vs 66–97% for "minimize area".

Physics wins [I] where rules conflict, at regime boundaries, on out-of-distribution designs, where trades must be priced (SW copper at 400 V), and as a generator of better rules. Physics vs rules has no data either way; the steelman is an argument.

## 4. Falsification tests

Any one, pre-registered, falsifies the thesis:
- On ≥ 10 measured boards (ripple, overshoot, pre-scan, IR), physics-critic scores rank outcomes no better than a rule-violation count (ΔSpearman < 0.1).
- Physics-optimized layouts beat rule-following ones by no more than measurement and fab scatter (≈ 2–3 dB, 10% ripple, 2 K) at equal cost.
- Joint P&R fails to beat an equal-CPU sequential portfolio on ≥ 20 real boards.
- Physics critics cannot tell autorouted from human boards above their false-alarm rate.

## 5. Independence of the evidence

- The lenses ran in sequence and cite each other: "found four ways" is four routes to textbook results, evidence of correctness, not novelty or independence. Passport sections converge because the brief asked for them.
- A [C] tag certifies a computation, not the physics; an identity or a script input is not evidence. "Topology beats tweaks" and "off-board unknowns are the most valuable" are single-case or prior-driven [I]. The 160-rule audit is one auditor's judgement ([derivation-audit](derivation-audit.md)).
- One idea, several ids: cut pricing CT1, CT2, SY6–SY9, VP D4, CD2, CD6; regime selector LS5, LS12, VP17, SY25, CT26, CD17; antiphase pairing SY16 = CT10; loop-honest ledger CT22, SY22/23, CD9, CD11; topological events CT28 = CD27; damping TH1/2/4/6, VP15, VP18, LS15; world node CT9, CT15, CT16, IN6, SY27, CD33, TH11.
- Make guarantee a field on each evaluator result (exact / bound / estimate / calibrated) rather than another tier ladder beside F0–F4 + S, T0–T3, C0–C3 and critic levels ([solver-ladder](solver-ladder.md#name-mapping)).

## Open questions

- Board-vs-cable and CM estimates are lumped, quasi-static, plate capacitances: they bound the same-edge benefit, do not fix it; a full-wave board-plus-cable run should settle it.
- The graded reference is unconverged at w/h ≥ 30 (+4–7% from 31 to 61 filaments); Hammerstad–Jensen plus corner terms may be cheaper.
- Plate Q assumes wide plates; narrow traces and vias add loss.
- Q ledger as LS's representation trigger: plausible [I], untested.

## Sources

- Scripts [C]: the nine `rt_*.py` linked above (reusing `sl_loop_peec`, `in_decision_quality`, `in_emi_voi` unchanged), plus re-runs of §2 scripts.
- [P], full text: Kotiuga & Lahtinen, [arXiv:1809.01002](https://arxiv.org/abs/1809.01002); Benz et al., [arXiv:1101.0312](https://arxiv.org/abs/1101.0312); Liu & Belcher, [arXiv:0712.0182](https://arxiv.org/abs/0712.0182) eq. (1).
- [S]: Wheeler's incremental-inductance rule (Proc. IRE 1942); Foster's theorem; Hockanson et al., IEEE T-EMC 38(4), 1996 (single-cable current-driven CM).
- Related: lenses [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md).
