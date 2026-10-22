# Lens IN: information, uncertainty and the epistemology of layout

**TL;DR**
- **Layout is decided under belief, not knowledge.** The state should be a belief about the physics (value, spread, lineage, validity); moves include *learning* (compute, ask, measure) and *robustifying* (make the decision insensitive), chosen by value of information (VOI) per cost. Round 1's escalation rule, criticality field, question ranking and compute market all approximate it.
- **Choosing needs less than knowing, precisely.** A ranking is a differential measurement: common bias cancels, and what decides is the error spread *among contenders* and whether the error follows the truth's dominant direction. That predicts round 1's proxy results within 1–4 points (MS, MS2, PP); area fails because its error *is* the omitted w/h [C]. Compliance verdicts (budgets, LII ≤ 1) need absolute accuracy. Under strong selection MS2's winner error drifts only +3% → +6.5% against a graded PEEC reference; the +64% first reported was the reference's own error (PEECN's 7 equal filaments read 11–42% low where winners sit, w/h ≫ 10) [C, [rt_loop_proxy](../../../tools/research/physics/rt_loop_proxy.py)]. So validate the reference too where the optimizer selects.
- **The most valuable unknowns can be off the board.** In round 1's EMI case, with its stated ranges, the enclosure, cable and test-setup offset carries 33–84% of total VOI: 49% with a 10 dB-wide offset prior, and 10–13% if co-locating the cables buys 6–30 dB rather than the assumed 35–60 dB (the best action then changes too) [C, [rt_voi_sensitivity](../../../tools/research/physics/rt_voi_sensitivity.py)]. The slot and stitching-cap disputes flagged for coupons carry 0–11%. A pre-scan informs the next board of the enclosure class; for the scanned board the layout is fixed (post-build EVSI 0).
- **A rule of thumb is a compressed posterior:** a threshold along its home regime's dominant parameter direction, regime variables dropped. Monotone physics keeps the direction and moves the threshold: "fails by regime, not direction". Plan-view area is free-space loop inductance's dominant direction (cosine 0.95), not over a plane (0.69), where height × squares is (0.95) [C].
- **Robustness and information are substitutes.** A robust action caps what learning is worth: cables on one edge cut total VOI 30× [C] if co-location buys the assumed 35–60 dB. Squeezing margins raises the knowledge an optimizer must buy: margin and measurement are one trade.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [in_decision_quality.py](../../../tools/research/physics/in_decision_quality.py) or [in_emi_voi.py](../../../tools/research/physics/in_emi_voi.py). Ideas: [lens-in ideas](../../ideas/physics-first/lens-in.md).

## Key facts

### 1. Principles

Symbols: θ unknowns, a action, ℓ loss, ŷ estimate of y, b common bias, u candidate-specific error, s true spread among candidates, s_j = ∂y/∂θ_j, σ_j uncertainty of θ_j, m margin.

| # | Principle | Statement |
|---|---|---|
| E1 | Value of information | VOI(X) = min_a E[ℓ(a,θ)] − E_X[min_a E[ℓ(a,θ) \| X]] ≥ 0. Learn X only if VOI > cost; VOI = 0 when the best action is the same for every outcome (Howard 1966 [S]) |
| E2 | Decisions are differential | ŷ_i − ŷ_j = (y_i − y_j) + (u_i − u_j), so b cancels. P(correct pair) = Φ(\|Δ\|/(√2·σ_u)), σ_u measured *among contenders*. Compliance needs \|b + u\| ≪ m |
| E3 | Rules are compressed posteriors | A rule stores a threshold x*(z₀) from home regime z₀; the truth is x*(z). Threshold error ≈ (∂x*/∂z)(z − z₀). The direction survives iff sign(∂y/∂x) holds for all z |
| E4 | Budget the unknown | p = p̂ + δ. A known p̂ is compensated (C_L choice, trim, tuning); only δ spends budget, s·σ_δ. Var(y) ≈ Σ s_j²σ_j²: shrink s_j (robust geometry) or σ_j (information), whichever is cheaper |
| E5 | Locality of knowledge | Footprint F_ε(q) = {x : \|∂q/∂g(x)\| > ε}, from one adjoint solve. Small footprints keep local models valid, verification incremental and verdicts stable under distant edits |
| E6 | Independent evidence | Two estimates with error correlation ρ average to variance σ²(1+ρ)/2. Methods sharing an idealization (ρ → 1) add nothing by agreeing |
| E7 | Predict, then observe | Register ŷ ± σ before every run; the surprise −log p(y_obs \| ŷ, σ) updates model trust; interval coverage sets trust radii and autonomy (Bogatin rule 9; [S4](../../ideas/original/system-loop.md)) |

Circuits are the gentle limit: every parasitic known and zero. Layout makes them nonzero and only *partly* known.

### 2. Derivations

**D1. The escalation threshold is a cost ratio** (derives SIM10/DR33's z = 1 cosmetic, z = 3 safety). For a belief y ~ N(ŷ, σ²) with margin m = B − ŷ > 0 (default: accept), a wrong acceptance costs L and escalating costs c, removing the error. Then VOI = L·Φ(−m/σ): escalate iff m < zσ, z = Φ⁻¹(1 − c/L). z = 1 means c/L = 0.16; z = 3 means c/L = 1.35×10⁻³: a wrong safety verdict is worth ~740 escalations [C]. The [criticality field](../../ideas/original/intent-and-why.md) should store c/L.

**D2. Ranking vs accuracy** (explains SIM7: MS2 picks the best loop 96–98%, area 16–66%). Pick-best uses only differences, so b drops out; with independent Gaussian u, accuracy depends only on σ_u/s. Round 1's 600 mixed loops, best of 10, same candidate sets per proxy [C]:

| Proxy | Median bias | σ_u all | σ_u contenders (best 20%) | corr(error, ln w/h) | Observed | Predicted (σ_u all / contenders) |
|---|---|---|---|---|---|---|
| MS2 | +11.4% | 0.037 | 0.074 | 0.55 | 96.3% | 97.0 / 93.9% |
| MS | +13.4% | 0.051 | 0.073 | 0.21 | 95.0% | 95.7 / 94.0% |
| PP (μ0·h·l/w) | +130% | 0.503 | 0.060 | −0.92 | 91.3% | 66.4 / 95.0% |
| Area (log fit) | — | 0.737 | 0.638 | 0.94 | 15.8% | 55.5 / 59.9% |

- **Bias is free:** MS2 × 1.5 still picks 96.3%; with independent ×1.5 noise, 69%.
- **Only contender errors count:** PP is badly wrong only for narrow traces, which never win.
- **An omitted variable is worse than its size.** Area's error *is* the w/h dependence (correlation 0.94).
- **Against a graded reference** [C, rt_loop_proxy]: MS2 bias +7.7%, contender σ_u 0.020, 96.8%; area 17.3%; PP 88.8%.

**D3. "Fails by regime, not direction"** (explains the genealogy counts in [rule-basis-set](rule-basis-set.md)). For monotone physics y(x, z) (more length → more L; more spacing → less coupling) sign(∂y/∂x) holds for every z, so only the threshold x*(z₀) errs.
- **3W:** K = 1/(1 + (D/h)²) with D = 3w omits w/h. Every 50 Ω microstrip has w/h ≈ 2, so 3W gives ~2.8% on any such stackup: the rule encodes D/h by accident. 0.25 mm on 1.6 mm (w/h = 0.16) gets K ≈ 0.8 ([rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md)).
- **The direction flips only when z enters the sign.** "Smallest cap closest" assumed leads set ESL; with MLCCs package and mounting do, so the ordering changes. Habit rules fail this way.

As priors (Jeffreys Beta, single auditor), P(about right) is 0.88 (95% 0.80–0.93) for physics rules, 0.15 (0.04–0.31) for simplicity proxies and 0.03 (0.00–0.15) for habit rules [C].

**D4. The optimizer's curse and Goodhart** (explains SIM9, SIM14). With independent error the selected candidate looks better by e_k·σ_u²/√(σ_u² + s²) (Smith and Winkler 2006 [S]; e_k = 1.54 for k = 10): only −0.2 to −0.5% for MS2 [C]. The real effect is structured: as selection strengthens (best of 10, 100, 600), area's true regret grows 171% → 767% → 1,407%. MS2's regret stays 0%, and its error on the winner drifts +2.9% → +5.8% → +6.5% against a graded reference (+16/+33/+64% against PEECN, whose error grows with w/h) [C, rt_loop_proxy]. Winners sit at the domain edge (w/h ≫ 10): calibrate the proxy *and the reference* where the optimizer selects, and never use a ranking proxy's *number* for a winner's compliance.

**D5. Robustness caps information.** If a_r's loss does not depend on θ_j, EVPPI(θ_j) ≤ E[ℓ(a_r)] − E[min_a ℓ(a,θ)]: learning never beats what robust action costs above clairvoyance. The information cost of optimality: by D1, thin margins make knowledge the binding resource.

### 3. Resolution: fidelity follows convergence when the evaluator has a nugget

Best of 10 candidates drawn ever closer to a 12 × 6 mm loop (w 0.5 mm, h 0.2 mm) [C]; a nugget is error that does not shrink as candidates converge.

| True spread (sd of ln L) | MS2 | Area | MS2 on a 0.5 mm grid |
|---|---|---|---|
| 28% | 98.8% | 44.0% | 93.6% |
| 8.8% | 98.8% | 46.4% | 88.0% |
| 2.6% | 99.6% | 50.4% | 67.2% |
| 0.9% | 98.4% | 42.4% | 47.6% |

- **Smooth proxies keep resolving** (MS2's gradient is within cosine 0.999 of PEEC's).
- **Evaluators with a nugget** (grids, meshes, routers) lose resolution once spread falls below it.
- Round 1's proxy study (58 of 131 near-equal-HPWL pairs differed > 10% once routed) implies a routed-J nugget of ~13% per pair (11–16% at 95%), ~9% per placement [C]. Near-tie failure is a router nugget, not a trait of physics proxies.

### 4. Sloppiness: why minimal models work

Active subspace of log L (PEEC) over log(a, b, w, h), 300 rectangles (Constantine 2015 [S]) [C]:

| Case | Variance share, leading direction | Direction (a, b, w, h) | Aligns with (cosine) |
|---|---|---|---|
| Over a plane | 0.90 | (0.49, 0.49, −0.52, 0.50) | perimeter × h/w 0.95; area 0.69 |
| Free space | 0.96 | (0.67, 0.67, −0.31, 0) | area 0.95 |

Outputs depend on one or two parameter combinations ("sloppiness", Transtrum et al. 2015 [S]), so dimensionless groups ([RG2](../../ideas/physics-first/rule-replacements.md)) and residual surrogates (SIM34) work. These numbers use the 7-filament reference; re-check with graded filaments.

### 5. The measurement program as experiment design

[in_emi_voi.py](../../../tools/research/physics/in_emi_voi.py) takes [fields-emi-budget](fields-emi-budget.md) case B (a 50 MHz clock crossing a slot, cables on opposite edges).
- **Actions:** leave it, stitching cap, reroute, reroute + slow edge, co-locate the connectors.
- **Units, priors:** % of one respin; round 1's ranges.
- **EVPPI** (partial perfect information) by binning (Strong et al. 2014 [S]).

| Scenario | EVPI | Enclosure/cable/test offset | Slot share × law | Cap path L | Short-slot model | Pre-scan before layout (earlier board), 3 dB |
|---|---|---|---|---|---|---|
| Slot crossing | 15.2 | 12.8 | 0.1 | 0 | — | 9.7 |
| Solid plane | 11.4 | 9.1 | — | — | — | 6.0 |
| 2 mm slot, fix costs 2 | 17.9 | 12.0 | 0 | 0 | 1.7 | 9.8 |
| 2 mm slot, fix costs 15 | 15.3 | 5.1 | 0 | 0 | 1.7 | 3.5 |
| No room to reroute | 1.1 | 0 | 0 | 0 | — | 0 |
| Cables on one edge | 0.5 | 0.2 | 0.4 | 0 | — | 0.2 |

- **The choice flips at offsets of 8 and 16 dB:** that resolution suffices.
- **The bridging-cap dispute** (1.2–3 vs Ott's 5–10 nH) has no decision value.
- **The short-slot dispute matters:** the slot formula fails below l ≈ 25h, and the Ott fit's "2 mm is nearly free" extrapolates below his shortest (6.35 mm) slot.

Round 1's coupon list ([research-gaps](research-gaps.md) gap 1) through VOI:

| Coupon | Verdict |
|---|---|
| Hot loops vs h | Anchored to 1.3–2× (AN-139, SNVA803, EPC); options differ ~3.5×. Measure the *circuit link*: ring Q, overshoot vs L with real FETs |
| Slots | Keep, at 1–5 mm (merged antipads), where models disagree and decisions flip |
| Bridging caps, lattices, decap clusters, via fields | Only when a decision hinges on them |
| *Missing* | **Pre-scan with real cables in the enclosure, stackup TDR, IR image**, fixing common factors once per class |

### 6. Convergences round 1 did not name

| One phenomenon | Scattered as | Consequence |
|---|---|---|
| EVPPI per cost | I5, U3, LA40, SIM10, DR33, OP45, OP49, SIM40, DR16, DR19 | One VOI engine; LA40's ∂margin/∂unknown ranks an unknown at 30 dB margin high, yet its VOI is 0 |
| Selection on misaligned evaluators | SIM9, SIM14, PC33, OP46, V2, JPR near-ties | Select with one evaluator, score winners with another |
| Robust design (Phadke 1989 [S]) | LA15, TM35, OP7, DR15, SIM42, XD110, TM14, DR27, Kelvin, ratiometric case C | A variance term in the objective (none exists) |
| Practice as priors | RG7, RG8, DR50, RG41, [decap median](../data/measured-priors.md) 3.29 mm vs "2 mm" | One prior per budget, weighted by regime distance |
| Measurement as learning | FE19, TM53, TM54, XD111, XD115–118, PC37, SIM12 | Bring-up with registered predictions *is* the F4 rung |
| Adjoints, triple duty | DR3, OP38, S1 | Fisher information (where to probe), footprints and VOI gradients from the same solves |

### 7. Transfers

| Lesson | From | Apply to |
|---|---|---|
| Measure each evaluator's nugget; escalate on spread vs nugget | JPR | Solver ladder, successive halving (JPR45) |
| Ranks right, absolute ±10–20 dB: calibrate the common factor per class | EMI chain | Thermal h_conv (TM54), HV pollution, PDN |
| Absorb the known, budget the unknown | LA15 crystal | Impedance (the fab's width tuning *is* calibration), snubbers tuned at bring-up |
| Mutants measure detectors; seed questions score experts (Cooke 1991 [S]) | PC29–31; risk analysis | Plant couplings to measure LLM hypothesis recall; weight the criticality map by calibration |

### 8. What each conductor is doing, and how the system knows it

Understanding a conductor means a calibrated belief about its role and state per band, provenance and what would change it. Per body (code writes, LLM reads; values illustrative):

```yaml
body: gnd.In1.buck_region
roles:   # hypotheses, not labels
  - {role: return_of(buck1.hot), band: ">3 f_x", p: 0.97, evidence: [band netlist, F2 PEEC]}
  - {role: return_of(buck1.hot), band: f_sw, p: 0.6, note: "f_sw ~ f_x"}
state: {J_max: {value: 3.1 A/mm2, sd: 12%, rung: F2, lineage: [sheet-laplace]}}
budgets: [{id: adc1.offset, spend: 0.31, p_over: 0.02}]
footprint_mm2: 140
unknowns: [{theta: f_x return split, evppi: 0, why: "same choice at both limits"}]
predictions: [{observable: "4-wire TP7-TP9 at 0.3 A", interval: [0.8, 2.4] uV}]
```

Three epistemic classes:
- **Self-evident:** local, validated (a trace over an adjacent solid plane).
- **Computed:** need a board solve (pours, slots, via fields).
- **Conjectured:** outside every model, or with an uncertain role; the biggest are in neither schematic nor board file: cable shields, enclosure, heatsink, chassis. Under round 1's priors they carry most decision value (§5); only asking or measuring reaches them.

The LLM works the card by abduction ([LA39](../../ideas/physics-first/language.md)):
1. Propose a mechanism with a base-rate prior and a discriminating observable.
2. Register a prediction.
3. Choose think, compute, ask, measure or robustify by EVPPI per cost.
4. Read the surprise.
5. Explain decisions by flip thresholds.

Explanations curb over-reliance only if they make verifying cheaper ([Vasconcelos](../ux/explanations-and-alternatives.md) [P]), as flip thresholds do. Representation: [lens-cd](lens-cd.md).

### 9. Critique of round 1

1. **Ranking and compliance are conflated.** [Principle 11](README.md) and "ranking matters more than accuracy" hold for selection, but the ledger and LII are absolute: a proxy, or its reference, can rank perfectly and miss the winner's value (D4). Report P(LII ≤ 1), not a point.
2. **"Proxies fail on near-ties" is mis-stated** (§3): smooth proxies hold 98–99.6% down to 1% spreads. SIM7's metric on random sets also mixes in non-contenders (PP: 66% predicted vs 91% observed).
3. **The coupon program is a coverage design.** It re-measures anchored physics and omits the off-board common factors that dominate VOI under round 1's priors (§5).
4. **Calibration debt is uneven; lineage is missing.** AN-139, EPC, SNVA803, Archambeault and Ott are independent evidence; three PEEC codes sharing the image-plane idealization are not (E6). Genealogy counts are wide single-auditor priors (habit "wrong": 0.42–0.86).
5. **Uncertainty is a side channel, not the state.** σ sits in SIM1 and PC4, but no principle says "budget the unknown" (LA15 is buried), no objective has a variance term and no optimizer can buy knowledge. Round 1 prices constraints, not information.
6. **The thesis should read "invisible or known".**
   - Solid planes, symmetry, Kelvin, differential and ratiometric topology, controlled impedance and guards make parasitics *predictable*: over a solid adjacent plane, local geometry gives the return.
   - [Principle 14](README.md) ("beauty is locality") has an epistemic twin (E5); hence reviewers prize convention.
   - Organic copper must beat convention by more than its extra σ and review cost.
7. **LLM hypotheses need a protocol,** or every hypothesized coupling becomes a budget, moving over-constraint from rules to imagination.

## Recommendations for our system

1. **Keep an epistemic ledger.** Each quantity carries a belief, lineage, validity, a level/shape error split and links to its decisions. Rank actions by EVPPI per cost, *robustify* included.
2. **Separate rankings from compliance.** Rankings may use calibrated proxies; compliance needs level calibration or F2/F3, reported as a probability.
3. **Calibrate proxies (and references) on contenders:** check gradient alignment, measure each nugget, escalate as population spread nears it.
4. **Make the first prototype the experiment:** register predictions before fabrication. Pre-scan with real cables, TDR, an IR image; assimilate; keep priors per fab and enclosure class (the scan informs the next board). Build coupons only where models disagree *and* decisions flip.
5. **Add a variance or chance-constraint term to the joint objective** to trade margin against measurement.

## Conflicts and open questions

- **Round-3 corrections (2026-10-22):** the +64% was the reference's error (graded: +6.5%); VOI shares are prior-driven; a pre-scan informs the next board ([red-team](red-team.md)).
- VOI values depend on round 1's priors and assumed costs (respin 100, connector move 25) in one scenario; the claim is the *ranking* of unknowns, itself prior-driven.
- "Contenders" here are the true best 20%, unknowable in practice: use the optimizer's top-k.
- The active-subspace result covers rectangles over an ideal plane only.

## Sources

- Scripts [C]: [in_decision_quality.py](../../../tools/research/physics/in_decision_quality.py), [in_emi_voi.py](../../../tools/research/physics/in_emi_voi.py), reusing [sl_loop_peec.py](../../../tools/research/physics/sl_loop_peec.py) and [fe_emi_budget.py](../../../tools/research/physics/fe_emi_budget.py).
- [S]:
  - Howard, IEEE Trans. SSC 2(1), 1966.
  - Smith and Winkler, Management Science 52(3), 2006.
  - Strong, Oakley and Brennan, Med. Decis. Making 34(3), 2014.
  - Kennedy and O'Hagan, JRSS B 63(3), 2001.
  - Constantine, *Active Subspaces*, 2015.
  - Transtrum et al., J. Chem. Phys. 143, 010901, 2015.
  - Cooke, *Experts in Uncertainty*, 1991.
  - Phadke, *Quality Engineering Using Robust Design*, 1989.
- [P]: Bogatin's 20 rules, via [what-good-looks-like](../workflow/what-good-looks-like.md).

See also: [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · [lens-vp](lens-vp.md) · [lens-ct](lens-ct.md) · [lens-sy](lens-sy.md) · [lens-ls](lens-ls.md) · [lens-th](lens-th.md) · [lens-cd](lens-cd.md)
