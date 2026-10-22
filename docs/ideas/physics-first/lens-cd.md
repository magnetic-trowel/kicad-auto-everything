# Lens CD ideas: what each conductor is doing (CD1–CD34)

Ideas from the round-2 conductor-centric lens. The principles, derivations and the
prototype are in [lens-cd](../../topics/physics/lens-cd.md); numbers tagged [C] come from
[cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py)
(a synthetic 26 × 18 mm, 2-layer, 0.8 mm board with a buck cell, a sensitive trace and a
slotted plane). Ids from round 1 refer to the [physics-first catalog](README.md).

Tags: **new** (not in round 1 or the corpus), **combo** (combines known pieces),
**sharp** (sharpens a round-1 idea with an exact form, a number or a test). Effort: S (days),
M (weeks), L (months). Principles CD-P1 … CD-P7 are defined in the topic doc:
P1 superposition (shares), P2 Tellegen attribution, P3 rank-1 counterfactuals,
P4 leverage and redundancy, P5 transport vs circulation, P6 charge to whom, P7 jobs as signs.

**Top five:** CD2 all-budget removal table, CD3 Thevenin addition oracle, CD8 job verbs from
counterfactual signs, CD10 cancellation index, CD18 cycle-rank budgeting per band.

## A. The passport and its oracles

1. **CD1. Piece passport ledger** *(new, M; P1–P7)*. For every piece of copper (mesh strip,
   via, pad cell) and every band, code writes one sparse row to `ledger.json`: current share
   of each source, charge share by destination (fast nodes), leverage, exact removal value
   per budget, transport/circulation ratio κ, heat-flux share and the job verbs. Bodies
   (net × layer) become aggregations of pieces. *Beats:* round 1 indexes physics by
   structure (loop, node); nothing answers "what is this copper doing". *Test:* build
   passports for 5 open boards; check that every DRC-clean physics fault planted by the
   mutation benchmark (PC29) changes at least one verb at the planted site.

2. **CD2. All-budget removal table from one diagonal** *(sharp of XD51/SIM24, S; P3)*. Per
   band, compute the cut-admittance diagonal y_bb = (N K⁻¹ Nᵀ)_bb once. Then the exact
   change of every budget when piece b is removed is ΔZ_qp = s_b^p s_b^q / y_bb, for all
   pieces and all budgets at once. *Beats:* first-order adjoint prices are off by
   1/(1 − ρ): exactly 2× for any strip of a uniform sheet, 11× for a 3 mm notch in our
   board's plane neck (+22% vs +2% on the ADC's DC error) [C]. *Test:* our prototype
   matches brute-force re-solves to 2×10⁻⁹; repeat on a real 4-layer board.

3. **CD3. Thevenin addition oracle for non-local copper** *(new, S; P3)*. The exact value
   of adding a via, jumper or bridge of impedance z between nodes m and n is
   ΔZ_qp = −ΔV_mn^p ΔV_mn^q / (z + Z_th,mn): open-circuit voltages from the existing solve,
   Z_th from one solve per site (batched). It prices non-local additions (a bridge across a
   slot, a via 10 mm away) that topological derivatives (OP41) cannot. *Beats:* in our board
   the best of 203 stitching-via sites cuts L_hot by 35.5 pH; the median site by 0.03 pH;
   brute force agrees to 0.001 pH [C]. *Test:* rank stitching and bridging candidates on
   3 boards; compare with openEMS for the top 10.

4. **CD4. Leverage map per band** *(new, S; P4)*. ρ_b = 1 − z_b·y_bb, the probability that
   the piece lies in a random spanning tree. Exact from selected inversion, or by a
   Johnson–Lindenstrauss sketch (24–96 solves) for the whole board. ρ = 1: series path;
   ρ ≈ ½: sheet; ρ → 0: redundant mesh. *Beats:* neck finders based on geometry (XD95
   medial axis, PC20 min-cut) see width, not irreplaceability. *Test:* sketch vs exact on
   the board; recall of pieces with ρ > 0.9 (see the topic doc for our numbers).

5. **CD5. Foster self-test on every solve** *(new, S; P4)*. Σ_b ρ_b = n − c (nodes minus
   components) at DC and in thermal networks; the generalized trace equals n − c with mutual
   inductance too. A changed sum flags an unintended island, a missing via or a port wired
   to the wrong conductor before any budget is trusted. *Test:* plant 20 connectivity
   faults (floating fill, cut via) and count detections.

6. **CD6. Leverage-gated trust for first-order prices** *(sharp of SIM2/SIM24, S; P3, P4)*.
   Use 1/(1 − ρ_b) as the error factor of any first-order removal estimate at DC and in
   thermal networks; escalate to the exact rank-k value when it exceeds 1.2. In inductive
   bands never use per-piece attribution as a removal estimate: in our board the ratio
   exact/attribution has median 0.04 at 100 MHz [C]. *Test:* prediction error of gated vs
   ungated first-order prices on 1,000 random edits.

## B. Jobs, verbs and explanations

7. **CD7. Share-qualified reference** *(sharp of PC9, S; P1)*. A fill counts as the
   reference of a channel in a band only where it carries that channel's return share
   (s > threshold) in that band. A connected but unused fill, or a stitched island that the
   return never reaches, earns nothing. *Beats:* connectivity-only qualification can still
   be gamed by cosmetic copper that is connected but carries nothing. *Test:* the PC33
   red-team edits; count fills that pass PC9 but fail CD7.

8. **CD8. Job verbs from counterfactual signs** *(new, S; P7)*. From exact single-piece
   removals, per band and per (aggressor, victim): *carries* p (self budget rises),
   *lowers* p→q (coupling rises without it), *raises* p→q (coupling falls without it),
   *images* p (no transport current, yet removal raises a self budget), *series path*
   (ρ = 1), *senses* (zero foreign share). *Beats:* role labels assigned top-down by net
   name or template. *Test:* blind-label 200 pieces on 5 boards by experts; agreement with
   the verbs.

9. **CD9. Counterfactual coupling maps instead of spender bars** *(new, S; P2, P3)*. Show
   couplings as the exact per-piece removal change, not as Tellegen attribution. In our
   board the per-region attribution of the inductive hot→victim coupling ranges from −289%
   to +196% because go and return terms cancel [C]. Spender bars (LA45) stay for self
   budgets. *Test:* reviewers asked "which copper should change to cut this coupling";
   accuracy with attribution bars vs counterfactual maps.

10. **CD10. Cancellation index as a coupling-robustness metric** *(new, S; P2)*.
    χ = |Σ_b a_b| / Σ_b |a_b| over the Tellegen terms of a coupling. Small χ means the
    coupling is a small residual of large cancelling go and return terms, so a small
    geometric or etch change can swing it by multiples. Use χ to pick tolerance corners
    and to prefer structural fixes (remove the sharing) over tuning. *Test:* Monte-Carlo
    etch and registration on 50 couplings; does χ predict the spread?

11. **CD11. Loop-basis attribution for explanations** *(new, M; P2, P5)*. When an
    explanation must attribute a coupling, net go and return contributions first: express
    the aggressor's current in its mesh (loop) basis and attribute per loop, where terms are
    well conditioned. *Test:* attribution stability under mesh refinement, per piece vs per
    loop.

12. **CD12. Designed/parasitic per (piece, job)** *(new, S)*. Move the flag of LA3 from
    structures to piece–job pairs: the SW pour is designed for carrying the inductor
    current and spreading heat, parasitic as an antenna. *Beats:* resolves the overlap
    that [vocabulary](../../topics/physics/vocabulary.md) leaves open (a VIN pour is feed,
    hot-loop member and spreader at once). *Test:* express the 6 worked examples with the
    flag per job; count conflicts that disappear.

13. **CD13. Four standard piece queries** *(combo, S; P1–P3)*. *Why here?* (jobs ranked by
    removal value ÷ budget slack), *what breaks if cut here?* (Woodbury plus the detour
    map), *what does this piece do at f?* (shares and removal per band), *where would one
    more via help?* (CD3 ranking). Answers cite piece ids, budgets and the model.
    *Test:* repair-task success of the LLM with queries vs geometry dumps (SIM44 protocol).

14. **CD14. Functional segmentation of copper** *(new, M; P1, P7)*. Cluster pieces by
    passport vectors into named regions ("feed trunk", "hot-loop image", "shared
    ADC/load return neck") and use them as the IR's bodies and the LLM's context.
    *Test:* reviewers' agreement that the regions are meaningful; token cost vs geometry.

15. **CD15. Passport diff: role-change alarms** *(sharp of PC41, S; P7)*. After an edit,
    list pieces whose verbs changed (a plane strip became a series path; a via started
    raising a coupling). *Test:* seeded regressions; time to root cause vs budget-level
    diffs.

16. **CD16. Passport-labelled mutants** *(combo, S)*. Label PC29/PC30 mutants by which
    pieces changed jobs and by how much, so detection is scored per job. *Test:* per-job
    detection rates of the critic suite.

## C. Bands, circulation and the f_x transition

17. **CD17. Per-piece regime map κ(f)** *(new, M; P5)*. Compute κ = |I(f)| / |I_R| per
    piece and source at 5–7 frequencies around f_x; pick the resistive, RL or inductive
    model per region from it. In our board the hot loop's plane current within 4 mm rises
    from the resistive 0.56 to 0.72 at HF, most of it by 6 f_x [C]. *Test:* model choice by
    κ vs global f_x on 10 converter boards against a full RL solve.

18. **CD18. Cycle-rank budgeting per band** *(new, S; P4, P5)*. A reference's cycle rank
    is the room it gives currents to circulate. Below the crossover, circulation carries
    foreign transport current through shared pieces and lets external flux drive loops;
    above it, circulation is how returns image their signals. Choose single-point,
    multipoint or hybrid grounding per band by computing both effects, then compile to
    `split_band` (capacitors add loops at HF only) or beads (remove them). *Test:* 10
    published grounding schemes; predicted vs reported outcomes.

19. **CD19. Sign-flip alarm across bands** *(new, S; P7)*. Flag pieces that lower a
    coupling in one band and raise it in another. In our board the top GND pour under the
    hot loop and the plane under it raise the hot→victim coupling at f_x and lower it at
    500 kHz and 100 MHz [C]. Such pieces are where band-selective operators (stitching
    capacitors, beads) beat plain copper. *Test:* count sign flips on 10 mixed-signal
    boards and check the fixes experts chose there.

20. **CD20. Induced-current inventory** *(new, S; P5)*. List conductors that carry no
    transport current of a source but whose induced current lowers a self budget or a
    coupling ("incidental shields"), and protect them in the IR, so a trim, a void or a
    later edit cannot silently remove them. *Test:* on 10 boards, how many trims proposed
    by DC-only pour optimization (OP2) destroy an incidental shield?

21. **CD21. Via passports instead of via rules** *(sharp of PW32/PW35, S; P1, P3)*. Each
    via's share of each loop per band and its exact removal and addition values replace
    "N vias per amp" and "return via within X mm". In our board each CIN− via carries 23%
    of the hot loop at 100 MHz but 2.6% of the DC feed; removing one costs 26 pH [C].
    *Test:* via budgets vs rules on 10 EVM layouts.

## D. Optimization and arbitration

22. **CD22. Job-conflict detector and `separate_jobs` operator** *(new, M; P6, P7)*. Find
    pieces whose job vector has large components of opposite sign (heat spreading vs
    charge to the world; DC carry vs HF coupling path) and propose a geometric split:
    trim the antenna part and keep the carry part, route heat through a thin dielectric
    to the node's own return, separate the DC and HF paths. In our board the SW pour's
    pin-side column is worth 10.8 K of heat spreading while its far column holds the
    largest world-charge share (0.19) for 9 mK [C]. *Test:* 10 converter boards; emissions
    proxy and ΔT before and after.

23. **CD23. Job purity as the beauty metric** *(new, M; P1, P2)*. Per piece, the overlap
    of unrelated structures' shares in the same band; board purity = 1 − Σ overlaps.
    Coupling is a bilinear form over shares, so purity is locality (DR42) made per piece
    and per band. *Test:* correlation with expert "looks right" ratings and with the EMI
    proxy on 30 boards.

24. **CD24. Rayleigh-safe fill and stitch policy** *(sharp of XD122, S; P3)*. Fill or
    stitch only where the addition oracle shows no coupling rises: Rayleigh protects self
    impedances, not couplings. In our board the worst single via site raises the
    hot→victim coupling by 1.2 pH (+3%) and another raises the ADC's DC common impedance by
    8.9 µΩ (+1.8%) [C]. *Test:* fills that pass the policy vs blanket fills; coupling
    changes on 10 boards.

25. **CD25. Batch-removal guard** *(sharp of PW10/XD93, S; P3, P4)*. Price deletions as a
    batch (Woodbury), never as a sum of singles. Deleting the 20% least-loaded plane strips
    together cost 7.3× the sum of their single exact costs; deleting 40% isolated a
    terminal [C]. *Test:* trimming runs with batch vs single pricing; final budget errors.

26. **CD26. Passport-guided LNS destroy and repair** *(combo, M; P3)*. In JPR19 windows,
    destroy the pieces with the lowest exact value per area and repair where the addition
    oracle is highest. *Test:* joint runs with passport vs random destroy at equal CPU.

27. **CD27. Incremental passports with topological-event refactoring** *(sharp of LA27,
    M; P3)*. Each move changes k pieces: update all shares by a rank-k Woodbury step
    (k solves). Refactor when the cumulative rank passes a threshold or when the Woodbury
    core becomes ill-conditioned, which is a near-bridge forming: the copper analogue of a
    JPR2 kinetic-certificate failure. *Test:* drift and speed over 10,000 joint moves.

28. **CD28. Spectral sparsifier of the copper graph** *(new, M; P4)*. Sample pieces with
    probability ∝ leverage (Spielman–Srivastava) to build a sparse surrogate network whose
    quadratic forms (loss, loop impedance, ΔT) are within 1 ± ε of the full one. Use it in
    the optimizer's inner loop with a guarantee instead of an unvalidated proxy.
    *Test:* budget errors and speed-up vs the full network on 5 boards.

29. **CD29. Piece value in output units** *(combo, M; P3)*. Multiply each piece's exact
    ΔZ_qp by the circuit adjoint ∂output/∂Z_qp (DR3): "this strip is worth 3 µV at the
    ADC". Extends S1 from gradients to exact finite edits. *Test:* predicted vs re-simulated
    output change for 100 edits on a buck + ADC board.

## E. Manufacturing, thermal and the rest of the passport

30. **CD30. Physics-weighted critical area** *(combo, M; P3)*. Expected physics damage of
    fab defects = Σ P_open(b)·removal value(b) + Σ P_short(m,n)·addition value(m,n); merges
    TM30's yield model with budgets, so widening and redundant stitching go where defects
    would hurt the physics. *Test:* rank defect sites on 5 boards; compare with
    brute-force defect injection.

31. **CD31. Removal-cost-aware DFM fixes** *(combo, S; P3)*. When DFM requires removing
    copper (slivers, acid traps, thieving balance), choose the removal with the smallest
    exact physics cost. *Test:* physics budgets after DFM cleanup, cost-aware vs
    geometric.

32. **CD32. Thermal passports on the same pieces** *(combo, S; P2, P3)*. Heat-flux shares
    and exact thermal removal values (rank-1 on the thermal Laplacian) per piece, joined
    to the electrical passport, so electro-thermal job conflicts are visible piece by piece.
    *Test:* thermal removal values vs FV re-solves on 5 power boards.

33. **CD33. Charge-destination passport for fast nodes** *(combo of PW4, M; P6)*. Per piece
    of a dv/dt node, the exact split of its charge among local return, quiet nets, victims
    and the world (δq = −P_OO⁻¹ P_Oe q_e) and its exact removal value
    (Δq = −C_:e q_e / C_ee). Finds the antenna end of a pour. *Test:* compare the world
    share with a near-field scan on 3 converter boards.

34. **CD34. Tellegen Kelvin proof across bands** *(sharp of LA8/XD72, S; P2)*. Compute
    V_err = Σ_b s_b^sense v_b^load at DC and in every switching band, attributed to pieces;
    a sense path is proven when its pieces carry no load share at DC and pick up no
    inductive EMF at HF. *Test:* tap-error predictions vs measurements on 5 shunt layouts.

See also: [lens-cd](../../topics/physics/lens-cd.md) · [language ideas](language.md) ·
[optimization ideas](optimization.md) · [critics ideas](critics.md) ·
[cross-domain ideas](cross-domain.md)
