# Lens CD: what each conductor is doing

**TL;DR**
- **A netlist is the support of the DC share matrix; layout physics is its values, band by band.** Every piece of copper (strip, via, pad cell, plane region) gets a *passport*: its share of each source's current, where its charge's field lines end, its share of each budget, and the exact change of every budget if removed or extended. Superposition, Tellegen's theorem and rank-1 updates make this exact: one factorization per band, one back-substitution per source, one diagonal for all removals.
- **Removal cost = attribution ÷ (1 − leverage).** Leverage ρ, the probability that a piece lies in a random spanning tree, maps irreplaceability without any source. On a square grid every interior strip has ρ = ½ (Foster: ρ = 2/z), so deleting one costs exactly twice its first-order price (1.5× on a triangular grid, 3× on a honeycomb) [C, [rt_cut_law](../../../tools/research/physics/rt_cut_law.py)]. Mesh-independently, the cost is the removed region's polarization tensor (2 × area for a disc), which is why round 1's hand-set factor 2 worked for compact holes; a slit costs the crack polarizability (π/4)·R_s·(Δψ)² however thin it is. This explains round 1's 30× slot miss [C].
- **Jobs are signs of exact counterfactuals:** carries, lowers or raises a coupling, images (induced current only), series path (ρ = 1), senses (zero foreign share). On a synthetic buck + ADC board, passports for 4,415 pieces × 4 bands × 10 budgets took ~25 s and matched brute force to 2×10⁻⁹ [C] (an algebraic check of the rank-1 updates; the model's physical error is untested, see Conflicts). They put 62% of the ADC's 1.5 mV DC error in two plane regions and showed one 0.5 mm slot bridge removing 78% of the HF coupling.
- **Three surprises.** A coupling's per-piece attribution is a residual of cancelling go and return terms (hot loop→ADC: 8% of their sum), so blame must be counterfactual. Adding copper can raise a coupling: Rayleigh protects only self terms. Deleting "useless" copper in one batch cost 7.3× its summed single costs.
- **Round 1 is net-centric at the bottom** (Body = net × layer, top-down roles, designed/parasitic on structures), and "one adjoint prices every edit" fails for finite edits. Add Piece, Passport and Job; derive loops, references, cells and exclusions as queries on the share matrix.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py). Ideas CD1–CD34: [lens-cd ideas](../../ideas/physics-first/lens-cd.md).

## Key facts

### 1. Principles

The circuit is the gentle limit: each conductor is one node. Layout bends it: a conductor is a field boundary with internal structure. The principles hold in any linear, reciprocal, quasi-static band (resistive, RL with mutuals, thermal); P6 is the electrostatic dual.

| # | Principle | Equation | Meaning for a conductor |
|---|---|---|---|
| P1 | Superposition | i_b(f) = Σ_p S_bp(f)·I_p(f); q_c = Σ_n Q_cn·V_n | its state is its row of S (current by source) and Q (charge by driven node) |
| P2 | Tellegen attribution | Z_qp = Σ_b v_b^p·i_b^q (v^p = Z·i^p obeys KVL, i^q KCL); a_b = ½(v_b^p i_b^q + v_b^q i_b^p) | every impedance, coupling, loss and stored energy is an exact sum over pieces; the split, not the sum, depends on piece size and test current |
| P3 | Rank-1 counterfactuals | remove b: ΔZ_qp = s_b^p·s_b^q / y_bb, y_bb = (N K⁻¹ Nᵀ)_bb = 1/Z_cut,b; set B: s_Bᵀ Y_BB⁻¹ s_B; add z across m,n: −ΔV_mn^p ΔV_mn^q / (z + Z_th,mn) | exact; Z_cut is what a current meets going round the piece |
| P4 | Leverage | ρ_b = 1 − z_b·y_bb; Σρ_b = n − c; Σ(1 − ρ_b) = cycle rank; removal = a_b/(1 − ρ_b) without mutuals | 1: series path; ½: square-grid sheet; → 0: redundant mesh |
| P5 | Transport vs circulation | J^p(f) = J_R^p + J_c^p(f), ∇·J_c = 0, no port flux; κ = \|J(f)\|/\|J_R\| | J_R carries; J_c images and shields; a tree cannot circulate |
| P6 | Charge to whom | δq_O = −P_OO⁻¹ P_Oe·q_e; Δq(remove e) = −C_:e q_e / C_ee | field lines end on the local return, quiet nets, victims or the world |
| P7 | Jobs are signs; arbitration is prices | verb = sign of ΔB_k(b); value = Σ_k λ_k·ΔB_k(b)/slack_k | conflicts are pieces with large opposite-signed components |

P2 also underlies the adjoint method of Director and Rohrer ([schematic-to-physics](schematic-to-physics.md)); P3 is the power-grid LODF, PTDF/(1 − PTDF); P4 is Kirchhoff and Foster; P5 is computational EM's loop–tree basis [S].

### 2. Derivation map

| Result or rule | From | How |
|---|---|---|
| First-order removal prices ×2 for holes, 30× low for slots ([solver-ladder](solver-ladder.md)); slit cost (π/4)R_s(Δψ/I)² (XD2, SIM25) | P3, P4 | D1 |
| "Pour everything on quiet nets" (XD122); Kelvin and sense ports (LA8, XD72, S11); single-point vs multipoint grounding | P2–P5 | D2, D4, D3 |
| "Last 28% of pour area buys 9% of R" (PW10); the 20% least-loaded copper +21% | P4 | removing copper spends redundancy (Σ(1 − ρ) = cycle rank): remaining leverage rises |
| "Return flows under the trace" above f_x | P5 | κ > 1 under the trace (§4 sweep) |
| Coupling types "common impedance" vs "inductive" (IR `mech`) | P2 | diagonal and off-diagonal of one basis-dependent bilinear form |
| "Stitch close to the loop's terminals" | P3 add | gain ∝ ΔV²/(z + Z_th); best site 1,000× the median (§4) |
| "Capacitance to whom" (PW4, S4) | P6 | per piece, exact, with removal values |

### 3. Four derivations

**D1. First-order prices are off by 1/(1 − ρ).** For an uncoupled piece with impedance z_b and share s_b the adjoint price is the attribution a_b = z_b·s_b²; exactly, ΔZ = s_b²/y_bb = s_b²(z_b + Z_rest) = a_b/(1 − ρ_b), where Z_rest is the path round b. On an infinite square lattice the resistance between neighbours is R/2, so ρ = ½ and every strip costs 2a_b: round 1's hand-set "2 ×" ([sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py)), within 15% for compact holes. A slit removes no area (a_b → 0) while its strips have ρ → 1; the limit is the crack polarizability ΔR = (π/4)R_s(Jℓ/I)² = (π/4)R_s(Δψ/I)², the constant of a flat plate's added mass in potential flow [S]. Exact/first-order is 2.0, 4.3, 13.9 and 27.8 for slits of 1, 4, 16 and 32 strips; the crack law with length (k+1) cells gives 1.57, 1.14, 1.02 and 0.96 of exact [C], so it holds from about 16 cells. Round 1's 30× was a 60-cell slot. Lenses [CT](lens-ct.md) and [SY](lens-sy.md) reached the same crack law independently; leverage explains the 2× for holes and extends the rule to every piece and budget.

**D2. Rayleigh protects self impedances, not couplings.** ΔZ_pp = s²/y ≥ 0 at DC and ΔL ≥ 0 in the inductive limit: no strip of 4,369 lowers L_hot at 100 MHz beyond round-off [C]. But ΔZ_qp = s^p·s^q/y, and −ΔV^p·ΔV^q/(z + Z_th) for additions, carry the sign of a product. Of 203 via sites, the worst raised hot→ADC coupling 1.2 pH (+3%) and another the ADC's DC common impedance 8.9 µΩ (+1.8%). Where two currents cross a piece in the same direction, cutting it raises their coupling: a 3 mm notch in the shared plane neck raised the ADC error 22% [C].

**D3. Star vs plane is a choice of cycle rank per band.** A star (tree) has cycle rank 0 (CT's articulation points): every piece is a series path and J_c ≡ 0: external flux drives no loop current (no ground loops), but no return can re-route under its signal. A plane has cycle rank ≈ n and ρ ≈ ½: returns image their signals above f_x, and below it foreign transport currents share its pieces. Hybrid grounds (capacitors that close loops only at HF, beads that open them) set the cycle rank per band. The "single-point below 1 MHz, multipoint above 10 MHz" folklore is this crossover [S]; its spread between sources (100 kHz to 10 MHz) is plausibly the geometry-dependence of the ωL = R crossover [I].

**D4. Kelvin from Tellegen.** A load p puts V_err = Σ_b s_b^q·v_b^p on a sense port q (P2), zero when the sense loop's pieces carry none of the load's drop: no shared pieces, or taps on a load equipotential. That is LA8, XD72 and S11 in one line, at every band, inductive pickup included; SY's lead field says the same.

### 4. Prototype: a buck cell, a sensitive trace and a slotted plane

26 × 18 mm, 2 layers, 0.8 mm (f_x = 78 kHz), 1 oz, 0.5 mm cells; quasi-static RL-PEEC with dense partial inductances in mesh form K = NᵀZN. Sources: DC feed, 3 A load, hot-loop commutation, output ripple, a unit probe around the ADC loop; bands DC, f_x, 500 kHz, 100 MHz; electrostatics and a thermal network share the cells [C].

| Question | Result [C] |
|---|---|
| Exactness | rank-1 vs brute force 2×10⁻⁹; Woodbury notch and via addition agree to all printed digits; Σρ = 2,330 = n − c |
| Cost (2 threads) | per AC band: factor 1.5–3 s plus cut diagonal 2 s; whole script with all checks ~100 s |
| Leverage | interior plane 0.501; sheet edge 0.64; slot tip ≤ 0.63; 44 series pieces (the trace and its vias). A 96-solve sketch (27 ms) finds all 44, no false flag, median error 8% (ρ = 1 bridges; on a slotted uniform sheet it flags 44 of 63 strips with ρ > 0.6, 35 falsely) |
| ADC's DC error | 1.47 mV at 3 A (0.49 mΩ): 43.7% in the plane neck under the inductor, 18.6% at the slot end, 16.7% under VOUT |
| The slot | ×2.25 DC common impedance, ×5–8 hot→ADC, ×5 ripple→ADC; one 0.5 mm bridge: −26% at DC, −78% at 100 MHz |
| First-order vs exact | DC: exact = 2.01× attribution (median). 3 mm notch: exact +22.3%, its strips' sum +4.3%, first-order +2.0%. 100 MHz: exact/attribution median 0.04 (10–90%: −0.10 to 0.66) |
| f_x transition (0.1, 1, 3, 10 f_x) | hot-loop plane current within 4 mm 0.56, 0.62, 0.69, 0.72; its return diving into the plane at CIN− 0.26, 0.28, 0.33, 0.39; ADC return under its trace 0.18, 0.27, 0.33, 0.35; L_ADC 20.0, 17.5, 15.8, 15.1 nH |
| Vias | a CIN− via: 2.6% of the DC feed, 23% of the hot loop at 100 MHz, +26 pH if removed. Best new via of 203 sites −35.5 pH; median −0.03 pH |
| Cancellation χ = \|Σa\|/Σ\|a\| | self budgets 0.85–1.0; DC common impedance 0.35–0.61; hot→ADC 0.08–0.10; ripple→ADC 0.21–0.28 |
| Batch removal | 20% least-loaded plane strips (0.04% of loss): 7.3× their summed single costs; 40% isolates a terminal |
| One pour, three jobs | SW pour pin column: +10.8 K if its strips go, world-charge share 0.15. Far column past the inductor pad: 9 mK, 25 µΩ, world share 0.19, the highest (ε_r = 1; FR-4 lowers world shares up to ~ε_r, the ranking probably less). Trim the antenna end, keep the spreader |

**What surprised me.** Coupling attributions swing −182% to +161% by region, and the HF attribution does not even predict a removal's sign. The plane under the hot loop *lowers* the ADC coupling at every band; the top GND pour away from the loop *raises* it at f_x. Near f_x, Z_ADC←hot = 35 + j18 µΩ is mostly common impedance, so my first run, judging couplings by their inductive part, flipped several verbs; judge by |Z|.

### 5. Convergences and synergies round 1 missed

| One object | Round-1 ideas that approximate it |
|---|---|
| Exact removal value s²/y | XD51, SIM24, SIM25, XD2, OP39, OP41, XD95, PC20, PW10, PW11, PW12, PW39, XD93, TM4, TM5 |
| Tellegen attribution | LA21, LA45, LA47, FE1, TM8, PW43, PW52, PC41, DR14 |
| Queries on the share matrix | DR22 (cells), DR42 (locality), XD121, LA7, LA20, LA8, XD72, PC9, PC7/FE9/RG48, DR25 |
| Node–loop duality per piece | PW1, PW4, LA4, XD122, S4, DR28 |
| The leverage diagonal outside PCB | LODF (only XD51 saw it), structural redundancy matrix, statistical leverage, spanning trees, loop–tree bases |

Six workstreams approximated the first row.

**Synergies.** Passport × S1: exact ΔZ per piece times the circuit adjoint gives each piece's value in µV or ppm, for finite edits (CD29). × JPR19: destroy low-value pieces, repair where addition gain is high (CD26). × TM30: defect probability × removal value is physics-weighted yield (CD30). × SIM44/DR14: the LLM reads verbs and numbers, not fields (CD13). × [lens-in](lens-in.md): decide by counterfactuals, explain by attributions.

### 6. Transfers

| From | Lesson | Apply to |
|---|---|---|
| Power grids (N-1, LODF) | no single outage may break a limit | returns, ESD, surge: no budget hangs on a piece with ρ > 0.9 (CD4) |
| Structural redundancy matrix ([Tkachuk et al.](https://arxiv.org/abs/2303.03945)) | its diagonal distributes indeterminacy, predicting robustness | fab opens and etch sensitivity (CD30) |
| Spectral graph theory | leverage sampling keeps quadratic forms within 1 ± ε | sparse copper surrogates in the inner loop (CD28) |
| Thermal (TM5: cuts across flow cost 20–30×) | same Δψ² law | exact thermal removal values (CD32) |

### 7. What each conductor is doing: the passport

```yaml
piece: plane.slot_end     # 61 strips aggregated; per-strip rows exist
DC:  {jobs: [lowers load->ADC (+43% if its strips go), lowers feed->ADC (+30%)]}
f_x: {hold: {Z_ADC: 6%}, jobs: [lowers hot->ADC (+73%), lowers ripple->ADC (+60%)], kappa: {ADC: 1.62}}
HF:  {hold: {Z_ADC: 5%}, jobs: [lowers hot->ADC (+44%; whole region +125%)], kappa: {ADC: 1.87}}
flag: parasitic, protect  # no spec, yet load-bearing for two couplings
```

- **Jobs:** the P7 verbs, plus spreads heat, holds charge (world, victims, own return), anchor and balance.
- **Queries:** *why is this copper here?* (jobs by value ÷ slack); *what breaks if I cut here?* (Woodbury plus detour); *what does this via do at 100 MHz?* (shares, removal per band); *where would one more via help?* (Thevenin ranking).
- **Arbitration:** net value = Σ λ_k·ΔB_k/slack_k with the optimizer's shadow prices; opposite-signed jobs mark a decision point for `separate_jobs` (CD22).
- **Incremental upkeep:** a move changes k pieces; a rank-k Woodbury step updates all shares with k solves. Refactor when the core turns ill-conditioned: a near-bridge forming (λ_max → 1) is a topological event, the copper analogue of JPR2. At DC, 1 ≤ exact/first-order ≤ 1/(1 − λ_max) for self terms ([physics-core-v2](physics-core-v2.md) §4).
- **Whole-board cost:** DC and thermal are sparse (one factorization, ~100 source solves, 24–96 sketch solves). HF needs per-cell windows (SIM26, DR22) or compressed PEEC: dense L grows as N².

### 8. Critique of round 1's synthesis

1. **The vocabulary is net-centric at the bottom.** Body = net × layer; `carries` and `returns_through` are booleans; nothing indexes physics by piece (LA47 is only a UI). The [vocabulary](vocabulary.md)'s open questions (body granularity, overlapping designed/parasitic roles) are symptoms. Keep the 12 atoms for intent; add Piece, Passport and Job for observation, with designed/parasitic per (piece, job).
2. **"One adjoint solve prices every copper edit" ([README](README.md) TL;DR) is false for finite edits.** Removals are off by the edit's polarization factor: about ×2 for compact holes (exactly ×2 for one strip on a square grid), unbounded for slits and necks; at HF the attribution misses even the sign. Restate: one adjoint plus the edit's polarization tensor prices small edits; one extra solve per piece prices finite ones exactly.
3. **The IR's `mech` enum is basis-dependent.** Common impedance and mutual inductance trade places as the mesh changes, so per-mechanism `alloc` can double-count. Use the label to explain, not to budget.
4. **Spender bars (LA45) and the I1 ledger mislead for couplings** (χ = 0.08 for hot→ADC). Attribute self budgets; use counterfactuals for couplings.
5. **Principle 2 ("classify copper by waveform") is still per net,** yet one SW pour is a heat spreader at one end and an antenna at the other. Restate it per piece and band.
6. **The [nine objects](cross-workstream-synthesis.md) omit Tellegen, the rank-1 counterfactual and the transport/circulation split;** "adjoint" and "partial elements" are listed apart, yet both are Tellegen.
7. **XD122's Rayleigh argument and S2's "cuts along streamlines are nearly free" are DC, self-term statements;** both can fail for couplings and at HF (D2).
8. **[Research-gaps](research-gaps.md) gap 2 is also a representation gap:** jobs change with band, piece by piece; in our toy the transition spans about 0.3–10 f_x, half done near 1–2 f_x.
9. **"Return-path continuity is a cause, not a quantity" ([rule-basis-set](rule-basis-set.md)) can now be a quantity:** the HF return share on high-leverage pieces, and the exact removal values of reference pieces.

## Recommendations for our system

1. **Add Piece, Passport and Job to `ledger.json`** (code-written, per band, sparse).
2. **Put the removal/addition oracle in the physics core (SIM46):** factor once per band; y_bb by selected inversion or sketch; Woodbury for sets, Thevenin for additions, the Foster sum as self-test.
3. **Replace first-order removal prices (SIM24) with exact ones;** keep adjoints for shape gradients.
4. **Critics:** share-qualified reference (CD7), series-path returns, counterfactual coupling maps (CD9), incidental shields (CD20), batch-removal guard (CD25).
5. **Give each budget a per-band metric:** |Z| or spectrum-weighted volts for couplings, L for loops, R for feeds.
6. **LLM:** queries and verbs with numbers; no per-piece coupling attributions without χ.

## Conflicts and open questions

- **Round-3 corrections (2026-10-22):** ρ = ½ is square-grid only; crack law from ~16 cells; 2×10⁻⁹ is algebra; sketch false flags on uniform sheets ([red-team](red-team.md)).
- **Model limits:** no skin effect or retardation, no via–via mutuals, ε_r = 1 electrostatics, one synthetic board; 0.5 mm cells resolve h = 0.8 mm, not 0.1 mm prepregs; uncalibrated ([research-gaps](research-gaps.md)).
- **Attribution is a convention; counterfactuals are physical but not additive** (the notch cost 5× its strips' sum); Shapley splits are possible but costly.
- **HF passports need compression:** dense PEEC cannot cover a board.
- **Passports are linear per band;** switching nonlinearity enters only through source spectra; ESD and surge need transient passports.

## Sources

- B. D. H. Tellegen, "A general network theorem, with applications", Philips Res. Rep. 7:259–269, 1952; P. Penfield, R. Spence, S. Duinker, *Tellegen's Theorem and Electrical Networks*, MIT Press 1970 ([ETHW](https://ethw.org/Bernard_Tellegen)) [S].
- S. W. Director, R. A. Rohrer, "The generalized adjoint network and network sensitivities", IEEE Trans. Circuit Theory 16(3):318–323, 1969 [S].
- Foster's theorem, spanning-tree probabilities: [arXiv:2201.06385](https://arxiv.org/pdf/2201.06385) [S]; Spielman and Srivastava, [arXiv:0803.0929](https://arxiv.org/abs/0803.0929) [S].
- LODF = PTDF/(1 − PTDF): Güler, Gross, Liu, IEEE TPWRS 2007 ([PSERC](https://documents.pserc.wisc.edu/documents/publications/papers/2006_general_publications/guler_generalized_lodf.pdf)) [S]. Loop–tree bases: [arXiv:2211.07704](https://arxiv.org/pdf/2211.07704) [S].
- Hybrid grounding thresholds, which vary by source: [EEPower](https://eepower.com/technical-articles/single-point-and-multi-point-signal-grounding/) [S].
- Flat-plate added mass ρπℓ²/4: classical potential flow (Lamb, *Hydrodynamics*) [S].
- Scripts: [cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py), [fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py), [sl_tier_costs.py](../../../tools/research/physics/sl_tier_costs.py), [xd_sheet.py](../../../tools/research/physics/xd_sheet.py).

See also: [README](README.md) · [vocabulary](vocabulary.md) · [physics-ir](physics-ir.md) · [solver-ladder](solver-ladder.md) · lenses [VP](lens-vp.md), [CT](lens-ct.md), [SY](lens-sy.md), [LS](lens-ls.md), [TH](lens-th.md), [IN](lens-in.md)
