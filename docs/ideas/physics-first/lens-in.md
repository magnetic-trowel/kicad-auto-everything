# Physics-first ideas: information, uncertainty and the epistemology of design (IN)

These ideas treat layout as decision-making under belief. The system holds a belief about the physics, and it can think, compute, ask, measure or robustify, choosing by value of information (VOI) per cost. The argument, derivations and numbers are in [lens-in](../../topics/physics/lens-in.md). The principles cited below (E1 value of information, E2 decisions are differential, E3 rules are compressed posteriors, E4 budget the unknown, E5 locality of knowledge, E6 independent evidence, E7 predict then observe) are defined there.

Scripts: [in_decision_quality.py](../../../tools/research/physics/in_decision_quality.py) and [in_emi_voi.py](../../../tools/research/physics/in_emi_voi.py). The ideas build on, and do not repeat: SIM1/SIM7/SIM9/SIM10/SIM14 ([simulation](simulation.md)), DR15/DR16/DR19/DR33 ([reasoning](reasoning.md)), LA15/LA39/LA40 ([language](language.md)), FE19/FE56 ([si-emi-rf](si-emi-rf.md)), TM53/TM54 ([thermal-hv-mfg](thermal-hv-mfg.md)), XD110/XD111 ([cross-domain](cross-domain.md)), and I5, U3, V4 and S4 ([original](../original/README.md)).

Tags: *new* (not in the corpus), *combo* (new combination of known parts), *sharp* (a known idea made precise or given a number). Effort: S (days), M (weeks), L (months). Everything is untested [I] unless tagged [C].

**Build first:**
- **IN1 + IN2 + IN3:** belief ledger with lineage and a level/shape split.
- **IN27:** pre-registered bring-up as the F4 rung.
- **IN8 + IN9:** decision-invariance test and robustify-or-learn arbitration.
- **IN14 + IN15:** nugget audit and fidelity by population spread.
- **IN17:** two-evaluator protocol.

## A. The epistemic state

**IN1. Belief ledger.** Every number in `ledger.json` becomes a belief:
- a distribution or conformal interval;
- validity (in/edge/out);
- *lineage*, the idealizations it rests on (PEC image plane, quasi-static, 2-D, code base, author);
- links to the decisions that read it;
- its current EVPPI and the cheapest action that would resolve it.

Principle E1/E6. SIM1 attaches σ to an evaluator call, and PC4 marks coverage. Neither says what the number is *for*, nor whether two numbers share a failure mode. Test: on two boards, seed five modelling faults (missed void, wrong port, wrong stackup). Count how many the ledger flags through lineage collisions or decision links versus σ alone. *combo, M*

**IN2. Level/shape error split.** Model every estimator's error as a common factor per product class plus a candidate-specific part. The common factors are fab, stackup, enclosure, cable, test setup and h_conv; the candidate-specific part depends on geometry features. Rankings read only the shape part; compliance verdicts read both. Principle E2. Today one σ serves both uses. That over-escalates ranking decisions (the common bias cancels in them) and under-escalates compliance (the bias does not). On the solver-ladder loop data a common ×1.5 bias left MS2's choices unchanged (96.3%) [C]. Test: on the solver-ladder loop families, check that shape-only σ predicts pick-best accuracy and level+shape σ predicts verdict errors. *new, M*

**IN3. Lineage-aware evidence fusion.** Combine estimates with a correlation set by shared lineage tags: identical idealization gives ρ → 1, different physics or measurement gives ρ → 0. Agreement among same-lineage models must not shrink σ. Principle E6. Under E6, three image-plane PEEC codes agreeing (SIM46), or critics passing mutants by the same author, are close to one piece of evidence. Test: give pairs of existing scripts seeded faults that both share (no plane void modelled); fused σ must not shrink, and the disagreement alarm (SIM11) must fire only for cross-lineage pairs. *new, S*

**IN4. Sensitivity footprint per conductor quantity.** From the adjoint solves the core already runs (OP38, DR3), compute the area where |∂q/∂geometry| > ε for each budgeted quantity, and report it as a locality metric. Principle E5. A small footprint means local models suffice, incremental re-verification is valid, and ECOs elsewhere cannot break the verdict. A large footprint (returns seeking a distant via or cap, slot detours) is fragile and expensive to know. DR42's locality index measures current closure, not knowability. Test: footprint vs the number of verdict changes caused by random distant edits on 10 boards. *new, M*

**IN5. Conductor epistemic card.** Per body, list:
- its roles as hypotheses with probabilities per band;
- its state per band (J, V, dv/dt) with rung and lineage;
- the budgets it spends, as P(over budget);
- its footprint;
- its top unknowns by EVPPI;
- the predictions registered for bring-up.

Code writes the card; the LLM reads it. Principles E1/E5/E7. It answers "what is this conductor doing, and how sure are we?" Today the system holds only net membership and a role label. Test: reviewers find a seeded wrong role or a missing return faster with cards than with the ledger table. *combo, S*

**IN6. Off-board conductor inventory.** Make cable shields, enclosure panels, heatsinks, chassis bonds and mounting hardware first-class bodies, each with priors and an "ask or measure" action. They are absent from both schematic and board file. Principle E1. In the EMI VOI study the enclosure, cable and test-setup offset carried 33–84% of all decision value under the study's stated ranges and 10–49% under other plausible priors [C, rt_voi_sensitivity]. The vocabulary has the atoms (Antenna, Port) but no workflow that gathers these facts. Test: on five products, count verdict changes after the inventory is filled versus left at defaults. *new, S*

## B. Value of information and actions

**IN7. One VOI engine.** Replace the criticality product (I5), expected-loss ordering (U3), ∂margin/∂unknown (LA40), the |budget − value| < zσ trigger (SIM10, DR33) and the compute market (SIM40) with one estimator: EVPPI per cost, by binning or regression over a Monte Carlo sample of the belief (Strong et al. 2014). Store the cost ratio c/L per consequence class; z then follows as Φ⁻¹(1 − c/L) [C: z = 1 ↔ c/L = 0.16; z = 3 ↔ 1.35×10⁻³]. Principle E1. The heuristics disagree in exactly the cases that matter. A large sensitivity at 30 dB of margin has zero VOI. Test: rank questions and escalations on 10 boards by each rule; count decision changes per action. *sharp, M*

**IN8. Decision-invariance test.** Before any expensive model, evaluate the decision at the corners or quantiles of the current belief. If the best action is the same everywhere, skip the model. Example: the f_x transition regime. If the Kelvin topology and the peninsula are chosen under both the resistive and the inductive limit, no transition solver is needed for that decision. Principle E1. It turns [research-gaps](../../topics/physics/research-gaps.md) gap 2 from "build a solver" into "build it only where the limits disagree". Test: on 30 decisions, the fraction skipped and the fraction later reversed by the full model. *new, S*

**IN9. Robustify-or-learn arbitration.** For each unknown θ_j with high EVPPI, compare two costs:
- shrinking σ_j by a measurement or simulation;
- shrinking s_j with a geometry or topology that makes the decision insensitive (Kelvin, ratiometric, same-edge cables, adjacent return, symmetry).

Take the cheaper. Principle E4. Robust actions cap the value of information [C: cables on one edge cut EVPI from 15.2 to 0.5 when co-location buys 35–60 dB]. SIM10 and DR33 offer only "escalate fidelity". Test: on the EMI and ADC worked cases, total cost (fixes + measurements + expected respins) under learn-only, robustify-only and arbitrated policies. *new, M*

**IN10. Decision-flip thresholds as measurement specs.** For each binding decision, compute the value of each unknown at which the best action changes. Specify measurements only to resolve the unknown relative to those thresholds. Principle E1. In the EMI case the choice flips at offsets of 8 and 16 dB, and a 3 dB pre-scan of a previous board in the same enclosure class recovers 66–81% of the offset's value [C]; for the scanned board itself the layout is fixed, so the scan informs only the next board. A cheap probe suffices. Full characterization to ±1 dB is wasted. Test: compare measurement cost and decision quality with threshold-driven vs full-characterization specs on three products. *new, S*

**IN11. Margin–knowledge frontier.** Let the joint optimizer choose geometry *and* information actions together:
- compliance enters as a chance constraint, P(spend ≤ budget) ≥ 1 − α, under the belief;
- priced actions (F2/F3 runs, coupons, vendor models, bring-up probes) can shrink σ.

Report the frontier "area or layers saved vs knowledge bought". Principle E4, D5. An optimizer that sees only physics prices squeezes margins until knowledge binds. VOI = L·Φ(−m/σ) grows as margins shrink, so thin margins cost information. DR16 discounts budgets by σ but never buys σ down. Test: on two boards, compare cost-to-ship (fab + measurement + expected respin) against the deterministic optimum. *new, L*

**IN12. VOI of vendor models and data.** Before requesting a SPICE model, S-parameter file or an NDA, compute the EVPPI of the parameters it would pin against the envelope stand-in (DR5). Request only when VOI exceeds the effort. Principle E1. DR16 notes that accuracy has a price but gives no rule for when to pay it. Test: on 20 parts, how often the obtained model changed a decision vs the VOI forecast. *sharp, S*

**IN13. P(LII ≤ 1) instead of LII.** Report the probability that every output is in budget, from the belief over common factors and model errors, next to the point LII. Rank layouts by expected LII, but gate sign-off on the probability. Principle E2. LII is an absolute instrument. A ranking-grade proxy can be right on the choice and still biased on the winner's value (MS2: +6.5% under strong selection [C, rt_loop_proxy]). Test: on three converter boards, coverage of the predicted probability against F3 or bench outcomes. *sharp, S*

## C. Proxies, fidelity and selection

**IN14. Evaluator nugget audit.** For every evaluator, measure the variance between nearly identical inputs:
- nudges of 0.01–0.05 mm;
- collinear segment splits;
- reseeded routers;
- remeshes.

Report its resolution limit √nugget in the evaluator's metadata. Principle E2. The HPWL-vs-routed study ([joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md)) implies a routed-J nugget of ~13% per pair, ~9% per placement [C]. A grid-snapped MS2 fell from 94% to 48% pick-best as candidates converged, while smooth MS2 held 98–99.6% [C]. PC32 tests continuity but does not quantify resolution. Test: nugget estimates are stable across boards of a class, and predict where proxy decisions fail. *new, S*

**IN15. Fidelity by population spread.** Escalate the evaluator for the current population when its true-value spread, estimated from the next rung on a few members, falls to about twice the current evaluator's nugget. Use this rule instead of fixed generations or fixed successive-halving fractions (JPR45, OP45). Principle E2. A proxy's decision value falls with its spread-to-nugget ratio, not with time. Test: J vs CPU on the [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md) instances, against fixed schedules. *new, S*

**IN16. Contender-restricted calibration.** Calibrate each proxy's dispersion and bias on the top-k candidates the optimizer actually compares, not on random layouts or all visited states. Principle E2. The SIM7 hot-loop data show why. PP's error is 0.50 (log sd) over all loops but 0.06 among contenders, so its choices are good (91%). Area's error is smaller than PP's yet its choices are poor (16% over mixed stackups), because the error is the omitted w/h [C]. SIM14 reweights the whole visited distribution, which still mixes in losers. Test: predicted vs observed pick-best per proxy using contender σ (here within 1–4 points for MS, MS2, PP). *sharp, S*

**IN17. Two-evaluator protocol.** Select candidates with one evaluator and report the winner's physics from an independent one: a different idealization, or at least a different code base. This applies to optimizer outputs, benchmark "best-of-k" columns (PC43) and LLM-proposed repairs. Principle E6, D4. Selection on a proxy biases the winner. Under strong selection MS2's error on the winner drifts to +6.5% beyond its median bias against a graded reference, while its regret stays 0% [C, rt_loop_proxy]. A 7-equal-filament reference reads 11–42% low where winners sit (w/h ≫ 10), so the reporting evaluator must itself be valid where the optimizer selects. Test: reported vs independently re-evaluated winner values on 50 optimizer runs. *new, S*

**IN18. Post-selection shrinkage.** When only the selecting evaluator is available, report the winner's value shrunk by the expected selection bias: e_k·σ_u²/√(σ_u² + s²) for independent error, plus the contender-specific bias from IN16. Flag winners outside the calibration hull. Principle E2 (Smith and Winkler 2006). It converts the Goodhart audit (SIM9) from an alarm into a correction. Test: shrunk vs raw estimates against F2 on optimizer winners. *new, S*

**IN19. Gradient-alignment admission test.** Admit a proxy into an optimizer's inner loop only if the cosine between its gradient and the reference's gradient is high over the region the optimizer visits. Principle E2/E3. Over a plane, MS2's gradient matched PEEC's at cosine 0.999; area's matched at only 0.71 (median) [C]. Rank correlation over random layouts misses this misalignment, and it is exactly what makes an optimizer drift the wrong way. Test: proxies admitted by the test vs by Spearman ρ, scored by true regret after optimization. *new, S*

**IN20. Active-subspace proxy discovery.** For each quantity with a trusted F2 solver (via inductance, decap reach, crosstalk, thermal coupling), sample gradients over the feature space and take the leading eigenvectors. Fit a closed form along them, then a residual surrogate (SIM34). Principle E3 (sloppiness). Loop L over a plane is 90% one direction, perimeter × h/w (cosine 0.95), the height × squares form of PW25 [C]. Automating the search finds the next MS2 for quantities that have none. Test: discovered proxies vs hand-made ones on decision quality at equal cost. *new, M*

**IN21. Common random numbers for robust comparisons.** When candidates are compared under tolerance ensembles (XD110, SIM42), evaluate every candidate on the *same* sampled fab, part and model-error draws. Principle E2: paired differences cancel the common noise, so ranking needs far fewer samples. XD110 and SIM42 specify ensembles per design. Test: samples needed for a stable robust ranking with and without common draws on impedance and hot-loop cases. *new, S*

## D. Rules as priors

**IN22. Rule reliability posteriors by origin and regime.** Give each rule record (RG1) a Beta posterior on "about right", seeded by origin:
- physics 0.88 (0.80–0.93);
- simplicity proxy 0.15;
- habit 0.03 (0.00–0.15) [C].

Update it per regime from benchmark failures (RG39) and solver audits (RG32). Use the posterior as the rule's prior weight in warm starts (RG41) and move generation (RG42). Principle E3. RG3's origin tags change behaviour but carry no uncertainty and never learn. Test: the posteriors predict which rules the physics critic overrides on held-out boards. *new, S*

**IN23. Regime-distance kernel.** Weight a rule's prior by exp(−d/ℓ), where d is the distance between the current dimensionless-group vector (RG2) and the rule's home regime z₀ (RG4, RG7). Far outside, the rule contributes nothing; inside, it acts as a strong prior. Principle E3. Today a regime predicate is a hard on/off switch, which throws away the rule's information near the boundary and over-trusts it just inside. Test: calibration of rule-predicted verdicts against physics verdicts vs regime distance. *new, S*

**IN24. Direction-vs-threshold rule classifier.** Sweep each rule's regime variables in the solver and test whether sign(∂quantity/∂rule variable) ever flips.
- Rules whose direction never flips (more spacing → less coupling) become move generators everywhere, safe as search directions.
- Rules whose threshold drifts keep only their budget.
- Rules whose direction flips ("smallest cap closest") are retired outside their home regime.

Principle E3. RG42 uses rules as moves without knowing where their direction holds. Test: acceptance rate of rule-generated moves by class over a benchmark run. *new, M*

**IN25. Revealed vs stated priors.** Fit geometry priors from the open-board corpus and compare them with the stated rules: human decap distance has median 3.29 mm and only 17% within 2 mm, against "≤2 mm". Where practice is systematically looser than the rule without failures, the rule is conservative there. Where practice is looser and failures cluster, practice is sloppy. Principle E3. Corpus priors and rule packs are kept separately today and never confronted. Survivorship is a known bias: published boards worked well enough to publish. Test: agreement of the inferred "conservative" list with the genealogy verdicts. *combo, S*

**IN26. Rule alignment score.** For each rule, compute the cosine between the direction its variable moves the design (area: (1, 1, 0, 0) in log(a, b, w, h)) and the active-subspace direction of its quantity in the current regime. Low alignment means the rule optimizes the wrong combination here. Principle E3. "Minimize loop area" aligns at cosine 0.95 in free space and 0.69 over a plane [C]. That is the computable form of "rules fail by regime". Test: alignment predicts the rules the genealogy marks M or X. *new, S*

## E. The measurement program

**IN27. Pre-registered bring-up as the F4 rung.** Before fabrication, the system writes predictions with intervals for its first article:
- near-field at probe points (FE19);
- ring frequency and amplitude;
- 4-wire µV between test points;
- TDR impedance;
- IR checkpoints (TM53);
- a pre-compliance scan with real cables in the enclosure.

After bring-up it assimilates the results, using common factors first and a model-discrepancy term, and stores the posteriors per fab and enclosure class. Principles E7/E2. The product shares every common factor, so it is the highest-VOI coupon, and registration turns every board into a calibration point. SIM12 and FE19 treat coupons and bring-up separately. Test: prediction error on the second board of a class after assimilating the first. *combo, M*

**IN28. VOI-designed coupon panel.** Choose coupons by summed EVPPI over the decision portfolio expected across future boards, not one per basis quantity.
- Favour model-form disputes that flip decisions, such as 1–5 mm slots and merged antipads, where the slot-line formula and the Ott fit disagree.
- Favour the circuit link (overshoot vs L with real FETs) over re-measuring anchored L vs h.

Principle E1. In the EMI case the bridging-cap dispute had zero decision value and the short-slot dispute had 1.7 of 15.3 [C]. Test: VOI-ranked vs the SIM12 panel; decision changes per coupon. *sharp, M*

**IN29. Identifiability check for measurement plans.** Before measuring, compute the Fisher information of the planned observables with respect to the parameters, by the adjoint chain (S1). Reject plans in which decision-relevant combinations are unidentifiable, and add the experiment that breaks the degeneracy. Examples: a second cable length to separate source from antenna; two airflow states to separate h_conv from emissivity. Principle E1/E6. Without it, data assimilation silently trades one parameter against another (Kennedy and O'Hagan 2001). Test: on simulated bring-ups with known truth, posterior error with and without the check. *new, M*

**IN30. Discrepancy-aware assimilation.** When fitting stackup Dk, h_conv, via constants or the EMI offset to measurements (XD111, TM54), include an explicit model-discrepancy term per lineage. Model-form error is then not absorbed into physical parameters that carry over to the next board. Principle E6. A fitted Dk that compensates a missing roughness model will be wrong on the next stackup. Test: transfer error of fitted parameters to a second stackup, with and without the discrepancy term. *sharp, M*

## F. Reasoning and people

**IN31. Hypothesis protocol for the LLM.** Every mechanism hypothesis (LA39) must carry three things:
- a prior from failure base rates (IN32);
- an observable that differs under the hypothesis and its negation;
- the cheapest test that measures that observable.

It becomes a budget only if posterior × consequence clears the VOI bar. Principles E1/E7. Without the protocol each hypothesized coupling adds a constraint, and over-constraint moves from rules to imagination. Test: precision and recall of hypotheses on planted couplings in the DR51 benchmark boards, and the count of budgets added. *sharp, S*

**IN32. Failure-mechanism base rates and an unknown-unknowns reserve.** Build a base-rate table of root causes from post-mortems, respin data and EMC lab reports. Use it as the prior over mechanism hypotheses. Reserve budget margin in proportion to the historical rate of mechanisms the screen does not model. Principle E1. No rigorous public respin breakdown exists ([respin data](../../topics/verification/respin-and-fab-hold-data.md)), so the system currently assumes its screen is complete. Test: retrospective coverage of the screen on published failure write-ups. *new, M*

**IN33. Calibrated expert elicitation (Cooke's classical model).** Ask experts for probability statements about where a board will fail, not rankings. Score each expert on seed questions with known answers, and weight their criticality maps by calibration and informativeness. Principle E7. The criticality map (I5) is tacit knowledge, and I5 treats any expert's map as truth. Test: weighted vs unweighted maps predicting critic findings on 10 boards. *new, M*

**IN34. Explanations by flip thresholds.** Every decision explanation lists the top two or three unknowns by EVPPI and the values at which the decision would change. Example: "if the cable common-mode offset is under 8 dB, move the connector; we assumed 10 ± 6". Principles E1/E7. Explanations reduce over-reliance only when they lower the cost of verifying ([explanations-and-alternatives](../../topics/ux/explanations-and-alternatives.md)). A flip threshold tells the reviewer exactly what to check. DR39 explains *why* with multipliers, not what would change the answer. Test: reviewer error-detection rate on seeded wrong decisions, with and without flip thresholds. *new, S*

**IN35. Board epistemic scorecard.** Report next to the physics scorecard:
- the share of budget spend verified at each rung;
- the share of decisions made outside validated domains;
- P(all budgets met);
- the remaining EVPI, i.e. what further knowledge could still buy.

Principle E1. PC4's coverage counts checks run; this measures how much of the board is *known*. Test: correlation of remaining EVPI with later ECO count on real projects. *combo, S*

**IN36. Information-gain mutants.** Weight or select mutants (PC29, PC30) by how much they discriminate between good and bad critics, i.e. those whose physics delta sits near the critic's decision boundary, rather than by count. Gross faults that every critic catches carry little information about critic quality. Principle E1 (adaptive testing). Test: critic rankings stabilize with fewer mutants than under uniform sampling. *new, S*

**IN37. Predictability premium for exotic geometry.** Add λ·σ(spend/budget) to the objective, so geometry outside validated model domains has to beat conventional geometry by more than its extra uncertainty and review cost. Exotic geometry here means organic pours near slots, unusual via topologies and any-angle copper near discontinuities. Principle E4/E5. This is the epistemic reason reviewers prize convention. It replaces a vague "regularity regularizer" ([research-gaps](../../topics/physics/research-gaps.md) gap 15) with a priced risk. Test: user acceptance and verified physics of optimized boards with λ = 0 vs λ calibrated. *new, M*
