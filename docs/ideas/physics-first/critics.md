# Physics-first ideas: critics and metrics (PC)

Ideas for measuring "physically right" so that DRC-clean but physically wrong boards are caught, scored and fed back to optimizers and the LLM. Design and catalog: [physics-critics](../../topics/physics/physics-critics.md), [catalog](../../topics/physics/physics-critics-catalog.md), [validation](../../topics/physics/physics-critics-validation.md). Prototype: [pc_refplane.py](../../../tools/research/physics/pc_refplane.py). Builds on [V1–V5](../original/verification.md) and the [I1 budget ledger](../original/intent-and-why.md).

Tags: *new* (not found in the survey), *combo* (new combination of known parts), *sharp* (a known idea made precise). Effort: S (days), M (weeks), L (months).

## A. Shared infrastructure

**PC1. Board physics model (BPM).** Compute once per board: copper layer z and h, per-layer reference map (fills by net), current-return graph (pads, tracks, vias, pours as a resistive/inductive graph), plane polygons and slot list, via spans. Every critic reads the BPM instead of re-parsing, and an edit invalidates only the affected tiles. It beats per-checker parsing because consistency bugs ("checks that disagree with KiCad") come from re-implementations. Test: all critics give identical results through the BPM and through standalone parsing on 20 boards. *combo, M*

**PC2. Refill-then-measure contract.** A critic run starts with `kicad-cli pcb drc --refill-zones --save-board` on a private copy and records the fill hash. Stale fills are the commonest silent error: route tasks start unfilled, and the scorer refills without saving. Test: FILL-STALE is never non-zero in recorded runs. *sharp, S*

**PC3. Continuous quantities, thresholds only in the scorecard.** Critics report nH, mV, mm and GHz with attribution, never pass/fail. Budgets turn them into utilization in one place. This gives optimizers gradients and removes cliffs (a via at 1.99 mm vs a 2 mm rule). Test: metamorphic nudges of ±0.05 mm change every score continuously. *sharp, S*

**PC4. Tri-state per check: measured / not checked / out of trust.** Every critic × object pair says whether it ran, and whether the proxy is inside its calibrated region. The scorecard reports coverage first. This applies the field lesson that "a check that didn't run reports zero". Test: inject missing roles and stackups; the scorecard must show reduced coverage, never a cleaner score. *combo, S*

**PC5. Role-model freeze.** Net roles, t_r, currents and connector classes are fixed per task like the DRC rules, and the scorer installs them. Otherwise a method can relabel a cable connector as internal or a clock as slow and pass every EMI critic. Test: red-team edits to roles must change nothing in the score. *sharp, S*

## B. Return path, reference and EMI critics

**PC6. RPQF-lite, a return-path quality factor from closed forms.** L_est/L_ideal per net from microstrip L′ per piece, far-plane hops, edge crowding, void detours (shorted slot-line) and via or cap bridges. Cadence computes the same ratio with a hybrid solver; ours costs milliseconds and can run on every candidate. Test: rank correlation with FastHenry full-net loop L on 100 nets. *sharp, S*

**PC7. Return-current shadow map.** Render the predicted return-current density on each reference (the 1/(1+(x/h)²) profile clipped to copper, detoured around voids by a 2-D Laplace solve) and diff it with the ideal shadow. Voids show as displaced current, which both critics and a VLM judge can read. Test: compare with openEMS surface-current dumps on 10 slices. *new, M*

**PC8. Plane perforation index.** Per declared plane: foreign track length, longest slot and its half-wave frequency, island count. It catches "routing signals through the GND plane" directly; the prototype finds it in 1 ms. Test: M-TRACE-IN-PLANE detection was 100% in the prototype run. *sharp, S*

**PC9. Connectivity-qualified reference.** A fill counts as a reference only if it is connected to the reference net and stitched within d of the trace. Floating or poorly stitched patches stop faking coverage. Test: red-team "cosmetic pour" edits no longer improve RET-COV. *sharp, S*

**PC10. Bridging-cap return estimator.** When a layer change switches the reference net, find the nearest capacitor between the two nets and estimate plane-pair spreading plus mounting L; report nH and the resulting ground-bounce mV at the net's dI/dt. This replaces "stitching cap within X mm" with a number. Test: FastHenry on 20 transitions; the current estimate (1.2–3 nH) is below Ott's 5–10 nH and needs calibration. *sharp, S*

**PC11. Ott-anchored slot severity.** Use ΔV ∝ ℓ·ln(ℓ/ℓ0), fitted to Ott's measurements (ℓ0 ≈ 2.3 mm), as the default slot severity. Slots under about 2 mm are noise; longer slots grow faster than linearly. Make the slot-line Z a function of g/h: the current proxy is within 18% of the in-repo PEEC for wide slots but 1.8× high for narrow ones. Test: openEMS sweep of slot length and width under a 50 Ω line. *sharp, S*

**PC12. Spectral coincidence critic.** List the board's structural resonances (plane cavity, slot half-waves, island quarter-waves, via stubs) and its excitation lines (clock and switching harmonics up to f_knee). Score overlaps in dB. A resonance only matters if something drives it, so this beats blanket λ/20 stitching rules. Test: openEMS resonance list vs the critic's list on 5 boards. *new, M*

**PC13. Connector-pair common-mode ledger.** For every pair of cable connectors, sum the MREMC V_cm contributions of all fast nets whose return crosses between them, and charge them against 1 mV (Class B) or 100 µV (strict). Physics: the cable pair is the antenna below about 100 MHz. Test: pre-scan of coupons with planted connector splits. *combo, M*

**PC14. Edge-proximity as inductance.** Report the return-plane inductance increase from the MREMC offset formula instead of a "3h from the edge" rule: L_ret grows 3.5× when a 50 mm trace moves from the centre to 1 mm from the edge [C]. Test: openEMS fringing on 5 edge distances. *sharp, S*

**PC15. Aggressor–victim noise matrix.** For each victim role (sense, FB, analog, I/O, clock), sum coupled noise in mV from every aggressor role (SW node, hot loop, clocks, high-current lines) using K, run length, broadside overlap and loop mutual L. "Keep high-current lines away from differential pairs" becomes a budget. Test: 2-D solves of 30 coupled sections. *combo, M*

**PC16. Diff-pair imbalance localizer.** Diff the two legs feature by feature (vias, bends, reference changes, neck-downs) and report where mode conversion happens, not just total skew. Local imbalance radiates even when total skew is zero. Test: openEMS Scd21 on pairs with planted asymmetric vias. *sharp, M*

## C. Power and PDN critics

**PC17. Hot-loop L from realized copper.** Extract the commutation path the current actually takes (pads, pours, vias, the plane under it) and compute partial L with a coarse PEEC/FastHenry. Report overshoot = L·di/dt against 0.2·V_DS,max. Pad-centroid shoelace areas miss returns routed through far planes or via detours. Test: AN-139, SNVA803 and EPC anchors as regression points. *combo, M*

**PC18. Decap effectiveness as impedance at the pin.** Per power pin: the loop from pin to via, plane pair, cap vias and cap, giving |Z| in the band the pin needs. This replaces "decap within 3 mm". Moving a 0402's GND via 5 mm away lifts |Z(100 MHz)| from 0.61 to 1.43 Ω [C]. Test: M-DECAP-FAR detection, and FastHenry spot checks. *sharp, S*

**PC19. Current-density hotspot map.** A sparse 2-D Laplace solve on each rail's copper per layer, with vias as resistors, gives drop, peak J and via current sharing. It finds via-field "Swiss cheese" necks and starved thermal reliefs that a width rule cannot see. Test: padne/KiPI agreement; M-NECK and M-THERMAL-RELIEF detection. *combo, M*

**PC20. Via-field min-cut screen.** Before the Laplace solve, compute the minimum conductive cross-section along each source-to-sink path (a max-flow min cut on a copper raster). It runs in milliseconds and flags merged antipads that neck a pour. Test: rank agreement with J-MAX. *new, S*

**PC21. Sense-loop mutual inductance.** Neumann integral between the hot loop (or SW copper) and each FB, current-sense or Kelvin loop, with plane images; induced mV = M·di/dt against the sense budget. The FB keep-out distance becomes a computed quantity. Test: FastHenry mutual L; M-SENSE-PARALLEL detection. *new, M*

**PC22. SW-node displacement current.** C of the switch-node copper to every plane and neighbour, times dV/dt, gives injected current in mA. Each extra mm² has a price. Test: 2-D C extraction on 10 converters. *sharp, S*

**PC23. Kelvin tap error.** Shared resistance between the sense tap and the main current path, from the Laplace potentials, gives the error in mV and % of the shunt signal. Test: M-KELVIN-MOVE. *sharp, M*

**PC24. Ground-as-traces detector.** GND and power pins that reach their plane only through thin traces, scored by R and L to the plane against the rail's current budget, not by a width cut. This is the OmniRouting failure mode. It must know the rail's current: on a real board a filtered +3.3VA rail ran 79 mm of thin trace on purpose. Test: M-GND-TRACE; false alarms on filtered analog rails. *sharp, S*

## D. Thermal, high voltage and manufacturing physics

**PC25. Copper-graph thermal screener.** A 2.5-D resistive network from the actual copper and vias (261 °C/W per 12 mil via), with power per part from the role model, run on every candidate. It replaces "big pad, many vias" with ΔT. Test: Elmer on 10 boards; thermal camera on coupons. *combo, M*

**PC26. Thermal-victim critic.** ΔT at crystals, references, sensors and electrolytic caps from nearby dissipators, against each victim's drift or life budget (electrolytic life halves per +10 °C). Test: M-HOT-NEIGHBOUR. *sharp, S*

**PC27. HV field map with corner enhancement.** Peak V/mm between different-potential copper, including inner layers and acute corners, from a 2-D electrostatic solve on candidate regions. Creepage tables cover the surface; this covers the field in the laminate and at points. Test: FEniCS/Elmer reference on 10 geometries. *combo, M*

**PC28. Warp and tombstone physics.** Copper balance between mirrored layers (CTE mismatch) and thermal-mass asymmetry between the two pads of small passives. These are assembly physics checks, cheap, and the only manufacturing physics most boards need. Test: correlation with assembler defect reports where available. *sharp, S*

## E. Trust: mutation, calibration and gaming

**PC29. DRC-equivalent mutation benchmark.** Generate faults that keep `kicad-cli` DRC counts identical (pour keep-out slots, deleted stitching vias, swapped plane nets, moved decap vias, traces moved onto plane layers), then measure each critic's detection and false alarms. This is the ground truth that DRC-based scores cannot provide. Test: the benchmark itself, with ≥ 8 operators × 50 boards. *new, M*

**PC30. Physics-labelled mutants.** Label every mutant's delta with an oracle (F1 everywhere, F2/F3 on a sample). Treat sub-resolution deltas as equivalent mutants, and score improvements and regressions per net. "Mutated" is not the same as "worse": swapping plane nets improved some nets on a real board. Test: label agreement between F1 and F3 on the sample. *sharp, S*

**PC31. Benign twins.** Each operator has a control edit with no physics delta (a far slot, an extra GND via, a collinear split, a whole-board rotation). False alarms are measured on twins, not only on clean originals. Test: the prototype's controls raised no new findings. *sharp, S*

**PC32. Metamorphic tests for critics.** Results must be invariant under translation, rotation, mirroring, segment splitting and net renaming, and continuous under ±0.05 mm nudges. These catch parser and transform bugs, the most common class in the field reports. Test: run on all qualified boards in CI. *new, S*

**PC33. Per-critic red team.** Before a critic enters any reward, an adversarial agent gets its API and tries to raise the score without a physics gain (cosmetic pours, vias landing on one plane, 6° jogs, role edits). Each hack becomes a regression test ([V2](../original/verification.md)). Test: hacks found per critic version. *combo, S*

**PC34. Disagreement-driven calibration.** When F1 and F2 disagree beyond tolerance on a candidate, escalate and keep the pair as a calibration point. Proxies improve where the optimizer actually goes ([V4](../original/verification.md)). Test: proxy error on optimizer-visited states before and after. *combo, M*

**PC35. Windowed field-solver spot checks.** Simulate only a 10 × 10 mm window (openEMS or FastHenry) around the top-k findings of each board. A full-board solve is unaffordable; a window costs minutes. Test: window vs full-slice agreement on 10 cases. *combo, M*

**PC36. Physics unit boards.** Tiny generated boards, each isolating one mechanism (slot crossing, layer change, decap loop, edge run, cavity) with an analytic answer. They serve as unit tests for every critic and as a teaching set for the LLM. Test: critic error vs closed form and openEMS. *combo, S*

**PC37. Coupon campaign for EMI and thermal ground truth.** Fabricate 5–10 coupons with planted faults and their twins; measure near-field scans, VNA S-parameters and thermal images. This is the only way to calibrate CM-V and LOOP-RAD, which no open dataset covers. Test: the campaign itself. *new, L*

## F. Reporting and the repair loop

**PC38. Physics markers in drc.v1 shape.** Emit findings with DRC's JSON shape (type, severity, description, items with uuid and pos) plus measured, limit, unit, budget_id and top spenders. The LLM repair loop and existing DRC tooling read them unchanged. Test: an LLM repair loop fixes planted faults from markers alone. *combo, S*

**PC39. Root-cause grouping.** One plane cut causes a dozen crossing markers; group them by the copper feature that caused them (the slot polygon, the missing via) before showing the LLM. Test: repair success with grouped vs ungrouped markers. *combo, S*

**PC40. Parametric repair hints.** Each marker carries IR-level fixes ("add a GND via within 1.5 mm of (x, y) on both planes"; "move segment uuid to the layer referenced to GND"), so the LLM edits intent, not copper. Test: share of findings fixed in one step. *combo, M*

**PC41. Physics diff between two boards.** Per-budget deltas with attribution ("+1.2 nH: GND via of C12 moved 4 mm"). Reviewers and the LLM see what an edit cost. Test: reviewer time on 20 diffs. *new, M*

**PC42. Human-relative physics.** Score the human reference with the same critics and report regressions relative to it, separating board-inherent issues from router-induced ones. Human boards are not physically perfect either: the prototype found USB lines on three of four boards changing reference between GND and a power plane at vias. Test: the router audit in [physics-critics](../../topics/physics/physics-critics.md). *sharp, S*

**PC43. Physics best-of-k as a separate column.** Among clean attempts, pick the best by the physics scorecard and report "cpk-phys" next to cpk. It never changes cpk, but shows whether k attempts buy physics. Test: cpk-phys vs cpk on the Freerouting baseline. *new, S*

**PC44. Layer-type hygiene probe.** All four sampled 4-layer boards type their plane layers as `signal`, and KiCad's Freerouting guide says only `power` layers are withheld from routing. A separate adapter variant that marks declared planes as `power` in the DSN would measure how much plane perforation this alone removes. Run it as a new adapter and run name; it changes the method, never the score. Test: PLANE-PERF on Freerouting outputs with and without. *sharp, S*
