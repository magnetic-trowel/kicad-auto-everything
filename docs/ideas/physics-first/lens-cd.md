# Lens CD ideas: what each conductor is doing (CD1–CD34)

Ideas from the round-2 conductor-centric lens. The principles, derivations and the
prototype are in [lens-cd](../../topics/physics/lens-cd.md). Numbers tagged [C] come from
[cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py), run on a
synthetic 26 × 18 mm, 2-layer, 0.8 mm board with a buck cell, a sensitive trace and a slotted
plane. Ids from round 1 refer to the [physics-first catalog](README.md).

Tags: **new** (not in round 1 or the corpus), **combo** (combines known pieces), **sharp**
(sharpens a round-1 idea with an exact form, a number or a test). Effort: S (days), M (weeks),
L (months). Principles, defined in the topic doc: P1 superposition (shares), P2 Tellegen
attribution, P3 rank-1 counterfactuals, P4 leverage and redundancy, P5 transport vs
circulation, P6 charge to whom, P7 jobs as signs.

**Top five:** CD2 all-budget removal table, CD3 Thevenin addition oracle, CD8 job verbs from
counterfactual signs, CD10 cancellation index, CD18 cycle-rank budgeting per band.

## A. The passport and its oracles

1. **CD1. Piece passport ledger** *(new, M; P1–P7)*.
   - *Mechanism:* for every piece of copper (mesh strip, via, pad cell) and every band, code writes one sparse row to `ledger.json`: the current share of each source, the charge share by destination (fast nodes), the leverage, the exact removal value per budget, the transport/circulation ratio κ, the heat-flux share and the job verbs. Bodies (net × layer) become aggregations of pieces.
   - *Beats:* round 1 indexes physics by structure (loop, node), so nothing answers "what is this copper doing?".
   - *Test:* build passports for 5 open boards. Check that every DRC-clean physics fault planted by the mutation benchmark (PC29) changes at least one verb at the planted site.

2. **CD2. All-budget removal table from one diagonal** *(sharp of XD51 and SIM24, S; P3)*.
   - *Mechanism:* per band, compute the cut-admittance diagonal y_bb = (N K⁻¹ Nᵀ)_bb once. The exact change of every budget when piece b is removed is then ΔZ_qp = s_b^p s_b^q / y_bb, for all pieces and all budgets at once.
   - *Beats:* first-order adjoint prices are off by 1/(1 − ρ). That is exactly 2× for any strip of a uniform sheet, and 11× for a 3 mm notch in our board's plane neck (+22% vs +2% on the ADC's DC error) [C].
   - *Test:* the prototype matches brute-force re-solves to 2×10⁻⁹. Repeat on a real 4-layer board.

3. **CD3. Thevenin addition oracle for non-local copper** *(new, S; P3)*.
   - *Mechanism:* the exact value of adding a via, jumper or bridge of impedance z between nodes m and n is ΔZ_qp = −ΔV_mn^p ΔV_mn^q / (z + Z_th,mn). The open-circuit voltages come from the existing solve; Z_th needs one solve per site, batched.
   - *Beats:* topological derivatives (OP41) are local and first-order; this prices non-local additions too, such as a bridge across a slot or a via 10 mm away. In our board the best of 203 stitching-via sites cuts L_hot by 35.5 pH, the median site by 0.03 pH, and brute force agrees to 0.001 pH [C].
   - *Test:* rank stitching and bridging candidates on 3 boards and compare the top 10 with openEMS.

4. **CD4. Leverage map per band** *(new, S; P4)*.
   - *Mechanism:* ρ_b = 1 − z_b·y_bb is the probability that the piece lies in a random spanning tree. Get it exactly by selected inversion, or for the whole board by a Johnson–Lindenstrauss sketch (24–96 solves). ρ = 1 marks a series path, ρ ≈ ½ a sheet, ρ → 0 a redundant mesh.
   - *Beats:* geometric neck finders (XD95 medial axis, PC20 min-cut) see width, not irreplaceability.
   - *Test:* sketch vs exact; recall of pieces with ρ > 0.9. On our board 96 solves found all 44 such pieces with no false flag [C].

5. **CD5. Foster self-test on every solve** *(new, S; P4)*.
   - *Mechanism:* Σ_b ρ_b = n − c (nodes minus components) at DC and in thermal networks. The generalized trace equals n − c with mutual inductance too.
   - *Beats:* today an unintended island, a missing via or a port wired to the wrong conductor shows up only as a strange budget. A changed sum flags it before any budget is trusted.
   - *Test:* plant 20 connectivity faults (floating fill, cut via) and count detections.

6. **CD6. Leverage-gated trust for first-order prices** *(sharp of SIM2 and SIM24, S; P3, P4)*.
   - *Mechanism:* use 1/(1 − ρ_b) as the error factor of any first-order removal estimate at DC and in thermal networks, and escalate to the exact rank-k value when it exceeds 1.2. In inductive bands, never use per-piece attribution as a removal estimate.
   - *Beats:* a blanket trust in adjoint prices. At 100 MHz the ratio exact/attribution has median 0.04 in our board [C].
   - *Test:* prediction error of gated vs ungated first-order prices on 1,000 random edits.

## B. Jobs, verbs and explanations

7. **CD7. Share-qualified reference** *(sharp of PC9, S; P1)*.
   - *Mechanism:* a fill counts as the reference of a channel in a band only where it carries that channel's return share (s above a threshold) in that band.
   - *Beats:* connectivity-only qualification. A connected fill that the return never reaches still earns credit there, and here it earns nothing.
   - *Test:* the PC33 red-team edits; count fills that pass PC9 but fail CD7.

8. **CD8. Job verbs from counterfactual signs** *(new, S; P7)*.
   - *Mechanism:* from exact single-piece removals, per band and per (aggressor, victim), assign the verbs:
     - *carries* p (a self budget rises without it);
     - *lowers* p→q (the coupling rises without it);
     - *raises* p→q (the coupling falls without it);
     - *images* p (no transport current, yet removal raises a self budget);
     - *series path* (ρ = 1);
     - *senses* (zero foreign share).
   - *Beats:* role labels assigned top-down by net name or template.
   - *Test:* experts blind-label 200 pieces on 5 boards; measure agreement with the verbs.

9. **CD9. Counterfactual coupling maps instead of spender bars** *(new, S; P2, P3)*.
   - *Mechanism:* show a coupling as the exact per-piece removal change, not as a Tellegen attribution. Spender bars (LA45) stay for self budgets.
   - *Beats:* attribution bars mislead for couplings. In our board the per-region attribution of the hot→victim coupling at 100 MHz ranges from −182% to +161%, because go and return terms cancel (χ = 0.08, CD10) [C].
   - *Test:* ask reviewers "which copper should change to cut this coupling?"; compare accuracy with attribution bars vs counterfactual maps.

10. **CD10. Cancellation index as a coupling-robustness metric** *(new, S; P2)*.
    - *Mechanism:* χ = |Σ_b a_b| / Σ_b |a_b| over the Tellegen terms of a coupling. A small χ means the coupling is a small residual of large, cancelling go and return terms, so a small geometric or etch change can swing it by multiples. Use χ to pick tolerance corners and to prefer structural fixes (remove the sharing) over tuning.
    - *Beats:* a coupling margin quoted without its fragility. Our hot→victim coupling has χ = 0.08–0.10; self budgets have χ = 0.85–1.0 [C].
    - *Test:* Monte-Carlo etch and registration on 50 couplings; does χ predict the spread?

11. **CD11. Loop-basis attribution for explanations** *(new, M; P2, P5)*.
    - *Mechanism:* when an explanation must attribute a coupling, net the go and return contributions first. Express the aggressor's current in its mesh (loop) basis and attribute per loop.
    - *Beats:* per-piece attribution, which is ill-conditioned and mesh-dependent for couplings.
    - *Test:* attribution stability under mesh refinement, per piece vs per loop.

12. **CD12. Designed/parasitic per (piece, job)** *(new, S)*.
    - *Mechanism:* move the flag of LA3 from structures to piece–job pairs. The SW pour is designed for carrying the inductor current and spreading heat, and parasitic as an antenna.
    - *Beats:* resolves the overlap that [vocabulary](../../topics/physics/vocabulary.md) leaves open: a VIN pour is feed, hot-loop member and spreader at once.
    - *Test:* re-express the 6 worked examples with the flag per job; count the conflicts that disappear.

13. **CD13. Four standard piece queries** *(combo, S; P1–P3)*.
    - *Mechanism:* the system answers four questions, each citing piece ids, budgets and the model:
      - *Why is this copper here?* Jobs ranked by removal value ÷ budget slack.
      - *What breaks if I cut here?* Woodbury, plus the detour map.
      - *What does this piece do at f?* Shares and removal value per band.
      - *Where would one more via help?* The CD3 ranking.
    - *Beats:* geometry dumps and DRC lists that the LLM must interpret itself.
    - *Test:* repair-task success of the LLM with queries vs geometry dumps (SIM44 protocol).

14. **CD14. Functional segmentation of copper** *(new, M; P1, P7)*.
    - *Mechanism:* cluster pieces by passport vectors into named regions, such as "feed trunk", "hot-loop image" or "shared ADC/load return neck". Use them as the IR's bodies and in the LLM's context.
    - *Beats:* net × layer bodies, which lump copper doing different jobs.
    - *Test:* reviewer agreement that the regions are meaningful; token cost vs geometry.

15. **CD15. Passport diff: role-change alarms** *(sharp of PC41, S; P7)*.
    - *Mechanism:* after an edit, list the pieces whose verbs changed: a plane strip that became a series path, a via that started raising a coupling.
    - *Beats:* budget-level diffs, which say that something changed but not which copper changed its role.
    - *Test:* seeded regressions; time to root cause vs budget-level diffs.

16. **CD16. Passport-labelled mutants** *(combo, S; P7)*.
    - *Mechanism:* label PC29/PC30 mutants by which pieces changed jobs and by how much, so detection is scored per job.
    - *Beats:* a single physics delta per mutant, which hides which job the critic missed.
    - *Test:* per-job detection rates of the critic suite.

## C. Bands, circulation and the f_x transition

17. **CD17. Per-piece regime map κ(f)** *(new, M; P5)*.
    - *Mechanism:* compute κ = |I(f)| / |I_R| per piece and source at 5–7 frequencies around f_x, and pick the resistive, RL or inductive model per region from it.
    - *Beats:* one global f_x per board. In our board the hot loop's plane current within 4 mm rises from 0.56 (resistive) to 0.72 (inductive), mostly between f_x and 3 f_x, and the ADC return under its trace goes from 0.18 to 0.35 [C].
    - *Test:* model choice by κ vs by global f_x on 10 converter boards, judged against a full RL solve.

18. **CD18. Cycle-rank budgeting per band** *(new, S; P4, P5)*.
    - *Mechanism:* a reference's cycle rank is the room it gives currents to circulate. Below the crossover, circulation carries foreign transport current through shared pieces and lets external flux drive loops. Above it, circulation is how returns image their signals. Choose single-point, multipoint or hybrid grounding per band by computing both effects, then compile the choice to `split_band` (capacitors add loops at HF only) or to beads (which remove them).
    - *Beats:* the "star vs plane" debate, settled by folklore thresholds that vary from 100 kHz to 10 MHz between sources.
    - *Test:* 10 published grounding schemes; predicted vs reported outcomes.

19. **CD19. Transition-band passports and coupling metrics** *(sharp, S; P5, P7)*.
    - *Mechanism:* always evaluate couplings at f_x as well as at the switching and edge bands. Judge them by |Z| (or spectrum-weighted volts), not by their inductive part.
    - *Beats:* edge-band-only checks. Near f_x a coupling is mostly common impedance (Z_ADC←hot = 35 + j18 µΩ in our board), and plane pieces matter several times more than at HF: the strips of the plane under the hot loop are worth +82% of that coupling at f_x and +13% at 100 MHz [C]. Judged by L alone, several verbs flipped sign. Pieces whose role is strong only in the transition band are where band-selective operators (stitching capacitors, beads) beat plain copper.
    - *Test:* verb tables with and without the f_x band on 10 mixed-signal boards; which explains the experts' fixes better?

20. **CD20. Induced-current inventory** *(new, S; P5)*.
    - *Mechanism:* list conductors that carry no transport current from a source, yet whose induced current lowers a self budget or a coupling ("incidental shields"). Protect them in the IR.
    - *Beats:* DC-only trimming and later edits, which remove such copper silently.
    - *Test:* on 10 boards, count how many trims proposed by DC-only pour optimization (OP2) destroy an incidental shield.

21. **CD21. Via passports instead of via rules** *(sharp of PW32 and PW35, S; P1, P3)*.
    - *Mechanism:* each via's share of each loop per band, plus its exact removal and addition values.
    - *Beats:* "N vias per amp" and "return via within X mm". In our board a CIN− via carries 23% of the hot loop at 100 MHz but only 2.6% of the DC feed, and removing it costs 26 pH [C].
    - *Test:* via budgets vs rules on 10 EVM layouts.

## D. Optimization and arbitration

22. **CD22. Job-conflict detector and `separate_jobs` operator** *(new, M; P6, P7)*.
    - *Mechanism:* find pieces whose job vector has large components of opposite sign, such as heat spreading vs charge to the world, or DC carry vs HF coupling path. Propose a geometric split:
      - trim the antenna part and keep the carry part;
      - route heat through a thin dielectric to the node's own return;
      - separate the DC and HF paths.
    - *Beats:* a per-net rule ("minimise SW area"), which cannot keep the useful half. In our board the SW pour's pin-side column is worth 10.8 K of heat spreading. Its far column holds the largest world-charge share (0.19) and is worth only 9 mK [C].
    - *Test:* 10 converter boards; emissions proxy and ΔT before and after.

23. **CD23. Job purity as the beauty metric** *(new, M; P1, P2)*.
    - *Mechanism:* per piece, the overlap of unrelated structures' shares in the same band; board purity = 1 − Σ overlaps. Coupling is a bilinear form over shares, so purity is locality (DR42) made per piece and per band.
    - *Beats:* a locality index per aggressor, which cannot say which copper is impure.
    - *Test:* correlation with expert "looks right" ratings and with the EMI proxy on 30 boards.

24. **CD24. Rayleigh-safe fill and stitch policy** *(sharp of XD122, S; P3)*.
    - *Mechanism:* fill or stitch only where the addition oracle shows no coupling rises.
    - *Beats:* "pour and stitch everything on quiet nets". Rayleigh protects self impedances, not couplings. In our board the worst single via site raises the hot→victim coupling by 1.2 pH (+3%), and another raises the ADC's DC common impedance by 8.9 µΩ (+1.8%) [C].
    - *Test:* fills that pass the policy vs blanket fills; coupling changes on 10 boards.

25. **CD25. Batch-removal guard** *(sharp of PW10 and XD93, S; P3, P4)*.
    - *Mechanism:* price deletions as a batch (Woodbury), never as a sum of single costs. Stop trimming when the batch cost reaches the slack.
    - *Beats:* summed single costs, which undercount badly. Deleting the 20% least-loaded plane strips together cost 7.3× the sum of their single exact costs, and deleting 40% isolated a terminal [C].
    - *Test:* trimming runs priced by batch vs by single costs; final budget errors.

26. **CD26. Passport-guided LNS destroy and repair** *(combo, M; P3)*.
    - *Mechanism:* in JPR19 windows, destroy the pieces with the lowest exact value per area and repair where the addition oracle is highest.
    - *Beats:* random or geometric destroy sets, which waste repairs on copper that was doing a job.
    - *Test:* joint runs with passport-guided vs random destroy, at equal CPU.

27. **CD27. Incremental passports with topological-event refactoring** *(sharp of LA27, M; P3)*.
    - *Mechanism:* each move changes k pieces, so update all shares with a rank-k Woodbury step (k solves). Refactor when the cumulative rank passes a threshold or when the Woodbury core becomes ill-conditioned. Ill-conditioning means a near-bridge is forming: the copper analogue of a JPR2 kinetic-certificate failure.
    - *Beats:* full re-extraction per move, or stale passports.
    - *Test:* drift and speed over 10,000 joint moves.

28. **CD28. Spectral sparsifier of the copper graph** *(new, M; P4)*.
    - *Mechanism:* sample pieces with probability ∝ leverage (Spielman–Srivastava) to build a sparse surrogate network. Its quadratic forms (loss, loop impedance, ΔT) stay within 1 ± ε of the full network's.
    - *Beats:* unvalidated proxies in the optimizer's inner loop; this one has a guarantee.
    - *Test:* budget errors and speed-up vs the full network on 5 boards.

29. **CD29. Piece value in output units** *(combo, M; P3)*.
    - *Mechanism:* multiply each piece's exact ΔZ_qp by the circuit adjoint ∂output/∂Z_qp (DR3), giving statements like "this strip is worth 3 µV at the ADC".
    - *Beats:* S1, which gives only gradients; this covers exact finite edits.
    - *Test:* predicted vs re-simulated output change for 100 edits on a buck + ADC board.

## E. Manufacturing, thermal and the rest of the passport

30. **CD30. Physics-weighted critical area** *(combo, M; P3)*.
    - *Mechanism:* expected physics damage from fab defects = Σ P_open(b)·removal value(b) + Σ P_short(m,n)·addition value(m,n). This merges TM30's yield model with the budgets.
    - *Beats:* geometric critical area, which treats every opened strip as equal. Here widening and redundant stitching go where defects would hurt the physics.
    - *Test:* rank defect sites on 5 boards; compare with brute-force defect injection.

31. **CD31. Removal-cost-aware DFM fixes** *(combo, S; P3)*.
    - *Mechanism:* when DFM requires removing copper (slivers, acid traps, thieving balance), choose the removal with the smallest exact physics cost.
    - *Beats:* purely geometric cleanup.
    - *Test:* physics budgets after DFM cleanup, cost-aware vs geometric.

32. **CD32. Thermal passports on the same pieces** *(combo, S; P2, P3)*.
    - *Mechanism:* per piece, heat-flux shares and exact thermal removal values (rank-1 on the thermal Laplacian), joined to the electrical passport.
    - *Beats:* separate thermal and electrical reports, which hide electro-thermal job conflicts piece by piece.
    - *Test:* thermal removal values vs finite-volume re-solves on 5 power boards.

33. **CD33. Charge-destination passport for fast nodes** *(combo of PW4, M; P6)*.
    - *Mechanism:* per piece of a dv/dt node, the exact split of its charge among the local return, quiet nets, victims and the world (δq = −P_OO⁻¹ P_Oe q_e), plus its exact removal value (Δq = −C_:e q_e / C_ee).
    - *Beats:* PW4's per-net split. This finds the antenna end of a pour.
    - *Test:* compare the world share with a near-field scan on 3 converter boards.

34. **CD34. Tellegen Kelvin proof across bands** *(sharp of LA8 and XD72, S; P2)*.
    - *Mechanism:* compute V_err = Σ_b s_b^sense v_b^load at DC and in every switching band, attributed to pieces. A sense path is proven when its pieces carry no load share at DC and pick up no inductive EMF at HF.
    - *Beats:* DC-only current-free checks, which miss HF pickup.
    - *Test:* tap-error predictions vs measurements on 5 shunt layouts.

See also: [lens-cd](../../topics/physics/lens-cd.md) · [language ideas](language.md) ·
[optimization ideas](optimization.md) · [critics ideas](critics.md) ·
[cross-domain ideas](cross-domain.md)
