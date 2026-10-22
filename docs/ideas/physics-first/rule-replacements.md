# Rule replacements: turning rules of thumb into physics checks (RG1–RG53)

Ideas from the rule-genealogy workstream. The evidence is in
[rule-basis-set](../../topics/physics/rule-basis-set.md) and the three genealogy docs
([power-analog-thermal](../../topics/physics/rule-genealogy-power-analog-thermal.md),
[si-emi-rf](../../topics/physics/rule-genealogy-si-emi-rf.md),
[routing-style-dfm](../../topics/physics/rule-genealogy-routing-style-dfm.md)); rule ids
P01–P59, S01–S55 and R01–R46 refer to their rows. Basis codes (L, M, Cm, R, Z, Bal, Vcm,
Res, Ins, Th, Mech, Fab) are defined in the basis-set doc.

Tags: **new** (not found in the corpus), **combo** (combines known pieces), **sharp**
(sharpens an existing idea with a number or a test). Effort: S (days), M (weeks), L (months).
These build on, and do not repeat, the budget ledger and dimensioned constraints
(I1/I2 in [intent-and-why](../original/intent-and-why.md)) and the N7/N8 solvers
([priority-agents](../original/priority-agents-and-negotiation.md)).

## A. Rule records and regime machinery

1. **RG1. Rule decompiler record** *(new, S)*. Store every rule as {slogan, origin class, basis quantities, governing equation, regime predicate, replacement budget, solver cost}, exactly the columns of the genealogy tables. The slogan becomes a retrieval key and an explanation string; only the budget is ever compiled into constraints. Test: port the 160 audited rules and check that every emitted constraint traces to a budget, not a slogan.

2. **RG2. Regime predicates as dimensionless groups** *(new, S)*. Each rule fires only when its group crosses a threshold: l·√εe/(c·t_r), f/f_x, D/h, w/h, size/(λ/2), L·di/dt/V_margin, C·dv/dt·Z/V_allow, I·R/(ε·V), P·R_th/ΔT, r/fin length, V/327 V (table in the basis doc). The groups are computed from stackup, net t_r, currents and outline, so a 4-layer 100 MHz board silently drops most RF and corner rules. Test: count active rules per board in a benchmark set and check that removing the inactive ones changes no physics verdict.

3. **RG3. Origin-aware rule handling** *(new, S)*. Use the origin tag to set behaviour: Hb rules drop to "info" unless their historic regime is detected (RG4); Lg rules are never relaxed by physics; Cg and Tl rules go to the style channel; Mf rules bind against the declared fab profile only. This stops habit rules from blocking physics-correct layouts. Test: re-score 20 boards with and without origin handling and count false violations removed.

4. **RG4. Legacy-regime archaeology** *(new, S)*. For each habit rule, store the regime where it was once right: leaded capacitors (P22, P23), tape-up and photoplotters (R02), immersion etchants (R04), 1956 NBS trace tests (P31), wave soldering (R25). A rule is re-activated only when the design is in that regime (e.g. a through-hole decap, hand assembly). Test: a reviewer panel rates the explanations for clarity versus a plain "myth" label.

5. **RG5. 3W-to-K converter** *(sharp, S)*. Re-express every spacing rule written in trace widths as D/h through the line's actual w/h, then as Johnson's K=1/(1+(D/h)²). For 50 Ω microstrip 3W always means K≈2.8%, but for 0.25 mm traces on a 1.6 mm two-layer board it means 80% [C]. Warn when a W-based rule is applied to a trace whose w/h is far from the controlled-impedance value.

6. **RG6. Stackup counterfactual test** *(new, S)*. Evaluate each millimetre rule on two stackups: the one its source assumed (e.g. TI's 4-layer for 200 mil return vias) and ours. If the physics verdict flips, the rule is a stackup proxy and gets re-derived from its budget. Test: run on all mm/mil rules in the rule packs and list the ones that flip.

7. **RG7. Vendor-rule back-solver** *(sharp, M)*. Infer the budget hidden in a vendor's number from the vendor's reference stackup (200 mil return via → ~140 pH at d=0.1 mm; CIN <2 mm → nH on their eval board), then re-apply the budget to our stackup. This turns vendor distances into portable physics. Test: compare back-solved budgets across vendors for the same interface; agreement within 2× indicates a shared physics target.

8. **RG8. Eval-board budget extraction** *(combo, M)*. Import the vendor's evaluation-board Gerbers, compute loop nH, SW-node fF and Kelvin shared squares with the same estimators, and store those as precedence-40 targets instead of copying distances. The vendor's working layout becomes a measured budget. Test: on 10 converter eval boards, compare extracted nH with the datasheet's stated anchors (SNVA803, SLAA896 pH tables).

9. **RG9. Physical-units lint for rule packs** *(combo, S)*. Flag every mm or mil number in a rule pack that has no derivation (h, t_r, λ, budget) as "unscoped proxy", and every proxy adjective (short, close, wide, keep away) with no quantity. Extends I2's dimension checking to the rule-pack side. Test: run on the existing packs; target zero unscoped numbers in hard rules.

10. **RG10. Proxy-word disambiguation in the IR** *(new, S)*. The LLM may not emit "short", "close", "wide", "direct", "no vias" or "keep away"; the parser forces a choice of basis quantity and budget from the proxy matrix. "Keep FB away from SW" must become "C(FB, SW) ≤ 10 fF and M(FB loop, hot loop) ≤ 0.1 nH". Test: measure how often the LLM's chosen quantity matches an expert key on 100 datasheet sentences.

## B. Replacement checks (one per family of rules)

11. **RG11. Return-transition budget in pH** *(sharp, S)*. Replace "return via within 200/50 mil" and the layer-change order with L = via partial + (µ0d/π)·ln(s/a) per transition, budgeted from data rate and Z0. The check exposes that plane spacing d matters linearly and via distance only logarithmically [C]. Test: compare against 3-D S-parameters of 10 transitions; rank correlation ≥0.9 would justify retiring the mil rules.

12. **RG12. Corner reflection check scoped by f·h** *(sharp, S)*. Compute a bend's |Γ| from Gupta/Kirschning C and L at the line's w/h and f_max; fire only when f_max·h > ~3 GHz·mm. That keeps the rule for 2.4 GHz on 1.5 mm boards and kills it for 4-layer digital. Test: openEMS on three bends (h = 0.2, 0.8, 1.5 mm) to calibrate the L term, where closed forms disagree 4×.

13. **RG13. Decap placement by mounting + spreading inductance** *(sharp, S)*. Score decap position by L_mount + (µ0d/π)·ln(s/a) to the pin, so "within 2 mm" disappears on 0.1 mm plane pairs and tightens automatically on two-layer boards. Feeds N8. Test: compare predicted rank order with a PDN field solver on 3 stackups.

14. **RG14. Width = max(IR, thermal)** *(sharp, S)*. Size every current path by the larger of an IR-drop budget (% of rail, per segment, current-weighted) and a thermal network, never by IPC-2221 alone. At 1 A on 1 oz, IPC-2221's 0.30 mm drops 3.3% of a 1 V rail in 20 mm [C]. Test: list the nets on benchmark boards whose IPC width violates a 1% IR budget.

15. **RG15. Fin-aware copper-area thermal check** *(sharp, S)*. Discount copper beyond the fin length √(kt/2h) (≈21–29 mm for 1 oz in still air [C]) and suggest heavier copper, inner planes or vias instead of more area. Replaces "15.3 cm²/W". Test: compare with a 2-D thermal FEM on 5 layouts with one 3 W source.

16. **RG16. Kelvin shared-resistance solver** *(new, S)*. Solve the sheet current on the shunt pads and taps and report error % and ppm/K from the squares shared between sense and power paths (1 oz: 0.49 mΩ/□ against a 1 mΩ shunt [C]). Replaces "tap at the inner pad edge" with a number. Test: compare with 4-wire measurements on 3 shunt land patterns.

17. **RG17. SW-node capacitance ledger** *(new, M)*. Compute C from the switch node to every victim net, to the board edge and to declared heatsinks and cables (2-D/3-D electrostatics), and budget i=C·dv/dt against each victim's tolerance. Replaces "minimise SW area" and "keep FB away from SW" while leaving the copper free to grow where it couples to nothing. Test: compare injected-noise predictions with a buck eval board measured with a near-field probe.

18. **RG18. Shared-branch impedance detector** *(combo, M)*. For every pair of current loops, compute the impedance of the copper they share (R + jωL at the aggressor's spectrum) and flag Z_shared·I_aggressor above the victim budget (LSB, FB noise). Replaces single-point ground, AGND/DGND, star ground and "CIN/COUT grounds apart". Test: reproduce the Ott split-plane jumper experiment in simulation.

19. **RG19. Frequency-crossover ground map** *(sharp, S)*. Compute f_x = R′/(2πL′) per return path (0.3–1.1 MHz for 1 oz over 0.2 mm [C]). Below f_x the check enforces DC routing discipline (star, Kelvin, no shared copper); above it, plane continuity. One rule replaces the star-versus-plane argument. Test: 2-D current-distribution solves at 10 kHz and 10 MHz on an audio board.

20. **RG20. Ground-fill admissibility** *(sharp, S)*. Allow same-layer fill only where the gap is ≥2h (Z0 shift <1% [C]) and every island is stitched below λ/10 at f_max; on two-layer boards require a stitched continuous return pour instead. Replaces "never fill" and "fill everything". Test: count fill islands removed or kept on 20 boards and verify Z0 by 2-D solve.

21. **RG21. Stitching from the largest unstitched dimension** *(combo, S)*. Compute, per plane pair, the largest via-free span and compare with λ/2 at f_max and with cavity-mode maxima. Settles perimeter-versus-distributed by computing which modes remain. Test: openEMS cavity on a 100 mm board with both stitching patterns.

22. **RG22. ESD path inductance budget** *(sharp, S)*. L(connector→TVS→ground) ≤ (V_IC,max − V_clamp)/(di/dt), with di/dt ≈ 3.75×10¹⁰ A/s for 8 kV contact (1 nH = 37.5 V [C]). Replaces "TVS near connector", "no via before TVS" and the 5–10 mm blog numbers. Test: IEC 61000-4-2 bench on two layouts with the same parts.

23. **RG23. Crystal ppm ledger** *(sharp, S)*. Sum trace capacitance (0.07–0.10 pF/mm [C]) times pullability (11–20 ppm/pF [C]), plus its tolerance, plus coupling pickup from aggressors, against the ppm budget of the protocol. The placement window comes out instead of 5 or 12 mm. Test: measure frequency offset on 3 trace lengths.

24. **RG24. Leakage-versus-capacitance guard decision** *(sharp, S)*. Compute leakage I = V/(ρ_s·N□) for the input node and the extra capacitance a guard adds; emit a guard only when leakage exceeds its budget and the Cm budget allows it. Resolves the two TIA regimes (P41/P42) by computation. Test: classify 20 TIA circuits and compare with TI reference layouts.

25. **RG25. Via-count rule replaced by via budgets** *(sharp, S)*. Per interface, budget return loss, insertion loss, stub resonance and return-transition pH per via; a via that meets them costs nothing. This removes "≤2 vias" where backdrilled or stitched vias are fine, and keeps "0 vias" only where a budget forbids it. Test: compare with TI/Qualcomm tables on PCIe and USB3 examples.

26. **RG26. Edge distance from fringing and Vcm** *(sharp, S)*. Derive the trace-to-plane-edge distance from h and the MREMC edge term instead of 90 mil, 2h or 3W. Test: openEMS trace-near-edge model at 3 offsets against the closed form.

27. **RG27. Skew budget from mode conversion** *(sharp, S)*. Allowed skew = 2·t_r·(V_cm,allow/V_d), with V_cm,allow from the cable emission budget and the receiver's CM tolerance; take the tighter. Replaces vendor tables that differ 5–25×. Test: compare derived budgets with the vendor tables and flag the outliers.

28. **RG28. Thermal-relief decision per pad** *(new, S)*. For each pad, compute ΔL, ΔR and ΔR_th of reliefs (4 spokes ≈ 37 K/W, 50–90 pH, 0.25 mΩ [C]) against the pad's loop budget, and the soldering heat balance for the declared process (reflow, wave, hand). Set relief or solid per pad. Test: tombstone and joint-quality inspection on a test panel with both choices.

29. **RG29. Tombstone heat-balance check** *(sharp, S)*. Estimate each small passive's two pad heat-up time constants from connected copper and planes and flag ratios above a calibrated threshold. Replaces "symmetric copper" with the quantity that causes the defect. Test: reflow a panel of 0201/0402 parts with controlled asymmetry.

30. **RG30. Power-pour shape objective** *(combo, M)*. Shape pours by minimising R + ωL (at the relevant spectrum) + thermal resistance, subject to Cm caps on switching nodes and to fab rules, using a 2-D sheet solver. Replaces "wide pours" and "round the corners". Hands over to workstream 6 ([optimization](optimization.md)). Test: compare optimised and hand pours on a 20 A buck by IR, loop nH and SW fF.

31. **RG31. Isolation physics side-checks** *(new, M)*. Keep the legal creepage/clearance engine, and add physics flags: Paschen check at altitude or low pressure, electrochemical-migration risk ∝ V/gap × humidity for low-voltage dense boards, and field enhancement at sharp HV copper. These catch cases the tables do not cover. Test: list boards where a physics flag fires but the table passes.

## C. Retirement, audit and calibration tests

32. **RG32. Rule-retirement test** *(new, M)*. For each rule, generate paired micro-layouts that satisfy and violate it while holding every basis quantity it does *not* claim to affect constant, then compute the physics observable. If the verdict never changes inside the target regime, retire the rule to style. Test: run on the 11 "X" rows; all should retire, and no "R" row should.

33. **RG33. Anti-conservative alarm** *(new, M)*. Search for layouts that satisfy every active rule but fail a physics check (thin traces with 3W on two-layer, IPC widths on 1 V rails, decaps "close" over 1 mm dielectric). Each hit becomes a documented rule hole. Test: number of holes found per CPU-hour by random versus adversarial search.

34. **RG34. Myth zoo regression suite** *(new, M)*. One canonical micro-board per myth (90° corner, 20-H, split ground, three values, guard trace, ground fill) with a solver script that prints the magnitude. The LLM must quote that magnitude to argue for or against the rule. Test: CI runs the zoo; a solver change that flips a verdict needs review.

35. **RG35. Rule-to-test-coupon generator** *(new, M)*. For any rule, emit a small KiCad coupon that isolates its mechanism for measurement (TDR for corners, VNA for stubs, thermal camera for copper area, near-field probe for SW area). Calibrates the proxies on real fab output cheaply on one panel. Test: one panel with 10 coupons, compared with solver predictions.

36. **RG36. Cross-rule redundancy pruning** *(new, S)*. Where several rules map to one budget (CIN distance, zero vias, area tier, vertical loop → L_hot), keep only the budget and delete the rest from the active set. Fewer, physically independent constraints should cut LLM and solver errors. Test: compare LLM constraint-authoring error rates with the full and pruned rule sets.

37. **RG37. Sensitivity-ranked rules** *(new, M)*. Compute ∂(observable)/∂(geometry parameter) by finite differences or adjoints on the quasi-static model; the rules whose quantities have the largest sensitivities on this board are the ones shown to the user and solved first. Replaces fixed severity labels and fixed placement order (R43). Test: compare the top-10 sensitivities with an expert's ranking on 5 boards.

38. **RG38. Rule weights from budget overspend** *(combo, S)*. Weight soft rules by the fraction of their budget that the current layout spends, not by S1–S4 labels; a rule at 5% of budget has near-zero weight. Test: placer convergence and final violation count with label weights versus overspend weights.

39. **RG39. Rule-hole catalogue from benchmark failures** *(new, S)*. Whenever the benchmark finds a physics failure on a board that passed the rule pack, record which rule was the nearest proxy and in which regime it failed. Over time this measures each rule's reliability by regime. Test: catalogue size and the fraction of failures explained by known regimes.

40. **RG40. Two-auditor agreement on rule classification** *(new, S)*. Have a second auditor (human or another LLM run) classify origin and verdict for the 160 rules independently, and report agreement (Cohen's κ). Low-agreement rows are where the corpus is ambiguous and need primary sources. Test: κ per column.

## D. Rules as priors for synthesis, not as judges

41. **RG41. Rules as warm starts** *(new, M)*. Use each rule's geometry (CIN next to the IC, return via beside the signal via, decaps at pins) as the initial guess for the physics optimiser, then let the budgets move it. Rules are good priors because they are cached solutions of the typical case. Test: optimiser iterations to feasibility with and without rule warm starts.

42. **RG42. Rules as move generators** *(new, M)*. Turn rules into local moves for search (add return via, move cap to pin, pull fill back to 2h, rotate inductor dot) and let the physics critic accept or reject each move. Test: move acceptance rate per rule; rules with rates near zero on a class of boards are candidates for retirement there.

43. **RG43. Regime-switching generator** *(combo, M)*. When a regime predicate is near its threshold (f/f_x ≈ 1, f·h ≈ 3 GHz·mm), the generator proposes both rule variants (star and plane, mitred and square) and lets the solver choose. Test: frequency of "both variants tried" decisions that the solver reverses.

44. **RG44. Corner and curve geometry only where it pays** *(sharp, S)*. Generate Douville–James miters for microstrip RF bends, arcs for flex and HV edges, inner fillets for pulse-current pours, and 45° elsewhere for editability. Test: reviewer acceptance and RF return loss on mixed boards.

45. **RG45. Vertical-loop proposer** *(sharp, S)*. When the stackup has a thin L1–L2 and the hot loop budget is tight, propose the vertical loop (caps returning through several vias to L2) instead of forbidding vias. Turns P03 from a ban into a geometry choice. Test: N7 placer with and without the vertical template, scored in nH.

## E. Explanation and review

46. **RG46. Three-line decompression on demand** *(new, S)*. For any rule the user asks about, print: the quantity it encodes, its regime predicate evaluated on this board, and the magnitude here ("3W: K=2.8% on these 50 Ω lines; budget 5%; not binding"). Test: user study on whether explanations change review decisions.

47. **RG47. Binding-rule heat map** *(new, S)*. Render which rules are binding where on the board (predicate true and budget spend >50%). Most of the board turns grey, which tells the reviewer where to look. Test: reviewer time to find seeded defects with and without the map.

48. **RG48. Return-current renderer at four frequencies** *(combo, M)*. Solve the quasi-static current distribution on ground copper at DC, 100 kHz, 10 MHz and 1 GHz and show it to the reviewer. Makes split, star and stitching arguments visible. Test: expert agreement that the rendering matches their mental model on 5 boards.

49. **RG49. Slogan detector for LLM output** *(new, S)*. Measure how often the LLM emits myth slogans unprompted (90° corners, three values, split ground, 20-H) and retrain prompts with the decompressed records. Test: slogan rate before and after on 200 design-review prompts.

50. **RG50. Electro-thermal feedback in sensing and IR checks** *(new, S)*. Feed temperature from the thermal network into copper R (TCR 3900 ppm/K) for IR-drop and Kelvin-error checks. A busbar at 60 °C has 16% more resistance than at 20 °C. Test: compare isothermal and coupled predictions on a 20 A path.

51. **RG51. Mechanical strain map for edge and flex rules** *(new, M)*. Compute board strain from depanelling method, mounting holes, heavy parts and flex bends with a plate model, and derive MLCC keep-outs and teardrop requirements from strain limits. Replaces fixed 3–5 mm keep-outs. Test: compare with crack incidence on a depanelled test panel.

52. **RG52. Fab-margin yield model** *(combo, M)*. Replace binary DRC pass/fail at recommended values with a per-feature defect probability from margin/σ (etch, drill registration, mask), summed over the board. The router then trades a little copper geometry for yield where physics allows. Test: correlate predicted defect counts with fab DFM reports on 20 boards.

53. **RG53. Keep-away distances solved from coupling curves** *(sharp, M)*. For each aggressor–victim pair, compute M(d), Cm(d) and ΔT(d) for the actual geometry (trace over plane ~1/(1+(d/h)²), open-flux magnetics ~1/d³, heat by influence coefficients) and solve for the distance at which the victim budget is met. Replaces "1–3 mm from magnetics/SW/clocks" (R46) with a distance that shrinks over a thin plane and grows on two-layer boards. Test: compare solved distances with near-field-probe coupling on a buck plus op-amp test board.
