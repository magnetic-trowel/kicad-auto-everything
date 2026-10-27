# Verification and limits

**TL;DR**
- **Every computed number the architecture relies on must pass three checks:** an independent method, a refinement study, and a reference validated where the optimizer selects. Optimizers drift to the edges of validated domains, so that is where the checks bind.
- **Verified by an independent method [C]:** the cut law (to 6 digits), the wire medium, the ℓ_m length, Q = h/δ for rings, snubber tuning, T1's first-order delay property, the loop-proxy rankings and the thermal length λ, each inside a stated domain (§1).
- **"Exact" and "certified" mean "inside a discretized or idealized model".** Convex floors move 2–13% between 0.2 and 0.1 mm grids. The ×2 removal price of an interior piece belongs to the square grid (×1.5 on a triangular grid, ×3 on a honeycomb). Agreement to 2×10⁻⁹ between rank-1 updates and refactoring is algebra, not physics. Every guarantee carries its model scope.
- **Competent rule-following beats physics-first where a good rule suffices or the decisive unknowns are off the board.** At a fixed stackup, "minimize trace length" picks the best hot loop 82–99% of the time against MS2's 97–100%. Joint place-and-route has no equal-compute win: 5 of 10 boards against an equal-CPU restart portfolio.
- **The thesis is falsifiable only against measured boards** (§4), and none exist yet.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed (model against model, uncalibrated) by the `rt_*` scripts in [`tools/research/physics/`](../../../tools/research/physics/).

## Key facts

### 1. Claims verified by an independent method

| Claim (doc) | Independent method (script) | Agreement [C] | Validated domain and scope |
|---|---|---|---|
| Cut law (2/π)R_s·ln sec(πx/2), 2× edge notch ([lens-ct](lens-ct.md), [lens-sy](lens-sy.md), [lens-cd](lens-cd.md), [lens-vp](lens-vp.md)) | Galerkin crack-row solution ([rt_cut_law](../../../tools/research/physics/rt_cut_law.py)) | 6 digits, x = 0.02–0.9. Classical (Johnson; polarization tensors) | DC and sheet inductance. CD's strip model gives 1.57 / 1.14 / 1.02 / 0.96 of exact at 1 / 4 / 16 / 32 strips: use ≥ 16 |
| Copper Q = h/δ ([lens-th](lens-th.md)) | Plate and microstrip eddy model ([rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py) `q`) | Microstrip (w/h ≥ 0.5): −7% to +18% of h/δ | Rings ≳ 50 MHz with h ≫ δ. A 0.1 mm, 1 oz plane pair has Q = 1.0 / 2.8 / 6.2 / 9.3 at 1 / 3 / 10 / 30 MHz (a 25 µm core: 4.8 at 100 MHz), so copper loss counts in PDN damping |
| Snubber tuning L_s·C_s ≈ L·C_oss ([lens-th](lens-th.md) D3) | State-space ring model ([rt_damping](../../../tools/research/physics/rt_damping.py)) | Q 0.96 and 1.59 (n = 3) over C_oss 0.5–2×; tuned n = 1: 1.05 and 2.69 | With the edge spectrum included, Q 10 → 1 buys 12.5–15 dB and Q 20 → 1 18–21 dB: the ring term is 20 log Q₀ minus the edge floor |
| Convex copper floors ([lens-vp](lens-vp.md)) | Grid refinement | The math holds; at equal area the floor falls 2.2–12.8% from the 0.2 to the 0.1 mm grid (5.6% near the headline area) | "Within 1.6% of the floor" and "14.5–15.8% avoidable" hold on the 0.1 mm raster |
| ℓ50 = R_s/(2πμ0f) and the R–L band ([lens-vp](lens-vp.md), [lens-sy](lens-sy.md), [lens-ls](lens-ls.md)) | Separate PEEC | ℓ50/ℓ_m = 0.42–0.53 for h ≤ 0.1ℓ_m; band edges f10 and f90 within 1.4–1.6× | ℓ ≥ 6h (at ℓ = 3h, f50·ℓ = 79 Hz·m). The current outside is \|1 − F\|: 18% outside ±5 mm at 100 kHz for h = 0.1 mm, 27% at 1.6 mm. Band numbers are for a 50 mm plane |
| Loop mirroring by a plane ([lens-sy](lens-sy.md), [lens-ls](lens-ls.md)) | 2-D sheet model ([rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py)) vs LS's 3-D table | Agree | Half-mirroring needs a/ℓ_m = 2.2–4.8 (~93 kHz for a 5 mm loop on 1 oz; a share of 0.06 at 12 kHz); 90% needs a/ℓ_m ≈ 10–45. "Fundamentals return under the loop" needs f_sw ≳ 300 kHz on 1 oz |
| Decaps and stitching as one wire medium ([lens-ls](lens-ls.md)) | Lumped anti-resonance | ω_p equals it by identity (975 MHz both); reach ≈ 23.6 mm reproduces | Uniform lattice. A 2–6× via-model spread gives 1.4–2.4× in reach: the input is uncertain, not the method |
| World-charge identity I_CM = −jω·ΣC_ext·V ([lens-ct](lens-ct.md) D2) | Circuit solve with the cable impedance ([rt_world_cm](../../../tools/research/physics/rt_world_cm.py)) | The identity holds; CT's D2 table solves the circuit | V must be world-referenced. Circuit voltages over-predict by \|1 + jωC_tot·Z_A\|: ≤ 5 dB for a free 5 pF board to 300 MHz, 10–29 dB at 100–300 MHz for 30 pF and 150–500 Ω. Pair C_ext with the CM path impedance |
| T1's first-order delay ([foundations](foundations.md) §3) | Terminated-line transfer ([rt_impedance_match](../../../tools/research/physics/rt_impedance_match.py)) | H/H0 = 1/(cos θ + jκ sin θ), κ = (Z0 + Z_S·Z_L/Z0)/(Z_S + Z_L): a pure delay κ·T_d to first order for any Z0; matching removes the second-order error −(κ² − 1)θ²/2 | Resistive terminations; between unequal ends an intermediate Z0 is a transformer. 30 Ω into 5 pF is delay-only at Z0 = R_S (0% overshoot, against 19–66% at 50–150 Ω). Outside the ~0.3–170 Ω that PCB Z0 spans, T1 reduces to min L for low-Z and min C for high-Z pieces. In power cells PW2's R term moves the width 2.3× |
| Loop proxy MS2 ([lens-in](lens-in.md)) | Graded-filament PEEC reference ([rt_loop_proxy](../../../tools/research/physics/rt_loop_proxy.py)) | MS2 picks the best loop 96.8% of the time, area 17.3% (stackups mixed); MS2 bias +7.7% | At a fixed stackup perimeter scores 82–99%. The reference shares MS2's idealizations |
| Image PEEC (PEECN) | FastHenry | Within 1.3% | 4 rectangles, w/h 0.3–5, 100 MHz. With 7 equal filaments PEECN reads 11% low at w/h 10–20 and 21% low at 20–60 (p10: 42%); use ≥ 31 graded (cosine) filaments |
| Passport counterfactuals ([lens-cd](lens-cd.md)) | Refactoring | Rank-1 updates match to 2×10⁻⁹ (solver error only) | Model error is separate: ε_r = 1 electrostatics overstates world-charge shares up to ~4× (0.5 mm cells on 0.8 mm) |
| Thermal length λ ([thermal-physics](thermal-physics.md)) | Recomputed from G_s and h_tot | λ = 37.7 mm reproduces; 21–64 mm across docs agree once both are named | One to six copper layers, h_tot 10–60 W/m²K. The ~2% kernel + images figure is method against the same fin model, not independent |
| Ground fill Z0 shift ([rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md)) | Converged 2-D solve ([rt_fill_z0](../../../tools/research/physics/rt_fill_z0.py)) | −5.0% at gap h (thin copper) to −8.4% (t = 0.35h); ≤ 2.2% at g ≥ 2h | Fill is harmless at ≥ 2h |
| Off-board share of VOI ([lens-in](lens-in.md)) | Prior sweep ([rt_voi_sensitivity](../../../tools/research/physics/rt_voi_sensitivity.py)) | 84% reproduces under its prior | 10–49% under other plausible priors (offset ~U(0,10) dB: 49%; same-edge benefit ~U(6,30) dB: 13%, where the best action becomes "reroute + slow edge"). A post-build pre-scan has EVSI 0 for that board's own layout |
| Joint place-and-route ([joint-place-route-experiment](joint-place-route-experiment.md)) | Equal-CPU restart portfolio; paired statistics ([rt_jpr_stats](../../../tools/research/physics/rt_jpr_stats.py)) | Routed-objective refinement improves a proxy-optimized start on 10/10 boards (−18%) | Against the portfolio: 5/10, p = 1.0 (median J ratio 0.96, 95% CI 0.83–1.24); the physics term's effect is 0.99 (0.93–1.05). Against a longer SA run at N = 30: 5/5, p = 0.06. Run-to-run sd of one board: ×1.18 |

**Reproduced by re-running** (same method, so reproducibility only) [C]: CT `cm`/`closure`/`nest`, SY duality, LS thin sheet, XD lengths, TM λ, the FE chain, TH `qcu`. Five cited sources were checked against the text (three in full) and are accurate.

### 2. Script and quantity scopes

| Script or quantity | Scope |
|---|---|
| `sl_loop_peec.py` (PEECN) | Equal filaments with GMD self terms converge slowly and non-monotonically; 7 filaments read up to 65% low at w/h ≥ 30. Valid at w/h 0.3–5 |
| `fe_emi_budget.py`, `in_emi_voi.py` | The same-edge benefit is an input (`same_edge_db`), not a result; a lumped board-vs-cable estimate gives 6–30 dB (24–48 dB if the return voltage runs parallel to the cable edge). `in_emi_voi.py` draws it from U(35,60) dB and times the scan before the layout decision. The worked case's order slot > cap > edge is one case, not a law; its 3 dB edge-rate figure is specific to one 50 MHz clock and omits the ring term |
| `pw_cells.py ring` | R comes from a fixed 2-square loop while L is free, so its Q values belong to no single geometry |
| `vp_rl_band.py` | Reports 1 − \|F\|, not the current outside \|1 − F\|; band numbers are for a 50 mm plane |
| `vp_floors.py` | Floors depend on the grid; its two grids used different areas (107.8 vs 104.9 mm²) |
| `cd_conductor_passport.py` | ε_r = 1. Its sheet sketch flags 44 of 63 high-leverage strips with 35 false flags; the board result holds for ρ ≈ 1 |
| `th_damping_ledger.py` | Ring model without the edge spectrum |
| `rg_fill_and_decaps.py`, `fe_field2d.py` | Under-resolved by 1.3–1.9 points |
| f_x, ℓ50, ℓ_d, ℓ_m, PW24 onset | One length up to factors of 2: ℓ50 = ℓ_d = ℓ_m/2, f_x ↔ ℓ_m = 2h, PW24 ↔ ℓ_m = a. Each "50% point" uses a different observable (L drop, containment, mirroring, share under the trace), so a "transition" moves by up to 10× with the observable: name it |
| Slot inductance "0.08–0.13 nH/mm" | The law is ℓ/ln(4ℓ/g), not linear. The per-mm figure holds for 10–40 mm slots; PEEC reads 1.5× lower on short narrow slots and Ott's data grow as ℓ ln ℓ |
| Heatsink capacitance 22–26 pF | Parallel-plate estimates differing in area, ε_r and pad thickness (1.4 dB). The deciding number is the heatsink's C to chassis, which sets where the current returns (CT D2) |

### 3. Where competent rule-following beats physics-first

The rule-based expert, steelmanned:
1. **Rules are robust policies; optimizers spend margin where the model is confident.** "Connectors on one edge" and "solid reference under fast nets" work across unknown enclosures, cables, part substitutions and fab spread; [lens-in](lens-in.md) D5 shows a robust action caps the value of information. An optimizer drifts to where its model is least validated: PEECN with 7 equal filaments rewards width spuriously at w/h > 30.
2. **Rules are calibrated by failures; our numbers by other models.** No [C] number here has met a measurement.
3. **Rules cover unmodeled physics.** One keep-out guards against C, M, heat, ESD and stress at once; we model no ESD, immunity, nonlinear victims or mechanics. Optimizing modeled terms can spend unmodeled margin (trimmed copper: plating imbalance, warpage; organic shapes: review time).
4. **Rules need no inputs we lack.** Physics needs the stackup with tolerances, C_oss(V), edge rates, cables and the enclosure. With default inputs, a physics engine is a rule engine with more failure modes.
5. **The big computed wins are rules.** No slot under the net (24–38 dB), thin dielectric (15–17 dB) and connectors together are textbook rules. What geometry optimization adds (−14.5% pour loss, MS2's 98% vs perimeter's 95%) is the size of fab and part tolerance.
6. **A better rule often suffices.** At a fixed stackup, "minimize length × h/w" picks the best loop 82–99% of the time, against 66–97% for the common "minimize area"; solving fields adds little.

**Physics wins** [I] where rules conflict, at regime boundaries, on out-of-distribution designs, where trades must be priced (SW copper at 400 V), and as a generator of better rules.

### 4. Falsification tests

Any one of these, pre-registered, would falsify the thesis:
- On ≥ 10 measured boards (ripple, overshoot, pre-scan, IR), physics-critic scores rank outcomes no better than a rule-violation count (ΔSpearman < 0.1).
- Physics-optimized layouts beat rule-following ones by no more than measurement and fab scatter (≈ 2–3 dB, 10% ripple, 2 K) at equal cost.
- Joint P&R fails to beat an equal-CPU sequential portfolio on ≥ 20 real boards.
- Physics critics cannot tell autorouted boards from human ones above their false-alarm rate.

### 5. Independence of the evidence

- **The lenses ran in sequence and cite each other.** Agreement among them ("found four ways") is four routes to textbook results: evidence of correctness, not of novelty or independence. The passport sections converge because the brief asked for them.
- **A [C] tag certifies a computation, not the physics.** An identity or a script input is not evidence; "topology beats tweaks" and "off-board unknowns are the most valuable" are single-case or prior-driven [I]. The 160-rule audit is one auditor's judgement ([derivation-audit](derivation-audit.md)).
- **One idea, several ids:**
  - cut pricing: CT1, CT2, SY6–SY9, VP D4, CD2, CD6;
  - regime selector: LS5, LS12, VP17, SY25, CT26, CD17;
  - antiphase pairing: SY16 = CT10;
  - loop-honest ledger: CT22, SY22/23, CD9, CD11;
  - topological events: CT28 = CD27;
  - damping: TH1/2/4/6, VP15, VP18, LS15;
  - world node: CT9, CT15, CT16, IN6, SY27, CD33, TH11.

## Recommendations for our system

1. **Run the three-part check on every [C] number the architecture uses:** an independent method, a refinement study, and a reference whose validated domain covers where the optimizer selects. Put it in the regression suite ([research-gaps](research-gaps.md) gap 20).
2. **Use graded filaments (≥ 31) in PEECN,** or converged 2-D L′ plus corner terms, outside w/h 0.3–5.
3. **EMI chain.** Compute the same-edge benefit as a board-vs-cable term from the charge identity and region capacitances, and add a ring term with the edge floor (TH6).
4. **Every guarantee carries its scope** ("raster 0.1 mm", "square grid", "ideal plane, HF"), and model error is reported apart from solver error. Make guarantee a field on each evaluator result (exact / bound / estimate / calibrated) rather than another tier ladder beside F0–F4 + S, T0–T3, C0–C3 and the critic levels.
5. **Joint P&R.** Architecture claims wait for experiment 6, run with the equal-CPU portfolio control on ≥ 20 boards, pre-registered.
6. **VOI.** Report results over a sweep of priors, and time information honestly: before layout, after build, or for the next board in the class.

## Conflicts and open questions

- The board-vs-cable and CM estimates are lumped and quasi-static with plate capacitances: they bound the same-edge benefit but do not fix it. A full-wave board-plus-cable run should settle it.
- The graded reference is still unconverged at w/h ≥ 30 (+4–7% from 31 to 61 filaments); Hammerstad–Jensen plus corner terms may be cheaper.
- The plate Q assumes wide plates; narrow traces and vias add loss.
- The Q ledger as LS's representation trigger is plausible [I] and untested.
- Physics vs rules has no data either way; the steelman is an argument.

## Sources

- Scripts [C]: the nine `rt_*.py` linked above (they reuse `sl_loop_peec`, `in_decision_quality` and `in_emi_voi` unchanged), plus re-runs of the scripts named in §2.
- [P], checked in full text: Kotiuga & Lahtinen, [arXiv:1809.01002](https://arxiv.org/abs/1809.01002); Benz et al., [arXiv:1101.0312](https://arxiv.org/abs/1101.0312); Liu & Belcher, [arXiv:0712.0182](https://arxiv.org/abs/0712.0182) eq. (1).
- [S]: Wheeler's incremental-inductance rule (Proc. IRE 1942); Foster's theorem; Hockanson et al., IEEE T-EMC 38(4), 1996 (single-cable current-driven CM).

See also: [README](README.md) · [validation-program](validation-program.md) · [physics-critics-validation](physics-critics-validation.md) · [research-gaps](research-gaps.md) · lenses [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md), [CD](lens-cd.md)
