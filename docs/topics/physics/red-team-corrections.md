# Red-team corrections: exact text changes for existing physics docs

**TL;DR**
- This is the edit list behind [red-team](red-team.md). Each item gives the file, the current text (quoted verbatim, checked with grep), what is wrong, and replacement text.
- **The ten corrections that matter most** are ranked first. The rest are grouped by file.
- **No owning doc has been edited.** Owners should apply these, re-run the named scripts, and keep the [C] tags pointing at them.
- Evidence scripts: `rt_*.py` in [`tools/research/physics/`](../../../tools/research/physics/) [C].

## Key facts

### Top ten, ranked by how much the architecture leans on them

| Rank | File · location | Problem | Fix (short) |
|---|---|---|---|
| 1 | [fields-emi-budget](fields-emi-budget.md) TL;DR, case D, §3, rec. 3; [README](README.md) principle 7; [report](../../../reports/Physics-first%20PCB%20layout.md) §2 | "Both cables on one edge buy ~40 dB" is an input (`same_edge_db=40.0`). It ignores the board-vs-cable mode, which leaves 6–30 dB in the worst orientation. It drives "topology beats tweaks", the VOI study and principle 7 | Give 6–48 dB by orientation and model the board-vs-cable term |
| 2 | [lens-in](lens-in.md) TL;DR, D2, D4 | "MS2 misses the winner by +64%" is the reference's error: PEECN's 7 equal filaments read 11–65% low for w/h ≥ 10 | Graded reference: drift +2.9% → +6.5%. Re-run D2–D4 |
| 3 | [solver-ladder](solver-ladder.md), [README](README.md) TL;DR, [open-solvers](open-solvers.md), [digest](../../digests/physics-first.md), [report](../../../reports/Physics-first%20PCB%20layout.md) | "PEEC agrees with FastHenry within 1.3%" holds only for 4 loops, w/h 0.3–5, at 100 MHz | State the domain; switch PEECN to graded filaments |
| 4 | [lens-th](lens-th.md) TL;DR, D1, critique 3; [power-copper](power-copper.md) §5 | "Copper can never be [the damper]" fails for plane pairs below ~30 MHz and for thin cores (TH's own D4). The ring lever is overstated by 6–8 dB | Scope to rings; 12–21 dB lever |
| 5 | [README](README.md) TL;DR, [solver-ladder](solver-ladder.md), [digest](../../digests/physics-first.md), [report](../../../reports/Physics-first%20PCB%20layout.md) | "One adjoint solve prices every copper edit" is wrong for cuts and for finite edits | Adjoint plus polarization tensor for small edits; rank-k updates for finite ones |
| 6 | [joint-place-route-experiment](joint-place-route-experiment.md), [README](README.md) principle 10, [report](../../../reports/Physics-first%20PCB%20layout.md) §3 | Joint vs the equal-CPU portfolio is 5/10 (median ratio 0.96, CI 0.83–1.24); the 5/5 has p = 0.06 | Report the tests; call it a refiner |
| 7 | [lens-in](lens-in.md) TL;DR, §5 | The 33–84% VOI share depends on priors (10–49% under alternatives), and the pre-scan's value is mistimed | Prior sweep; pre-layout vs post-build |
| 8 | [lens-ct](lens-ct.md) TL;DR, D2 | "I_CM exactly … one electrostatic solve gives every C_ext" needs world-referenced V. With circuit V it over-predicts by \|1 + jωC_tot·Z_A\| (up to 29 dB) | Add the CM path impedance |
| 9 | [lens-vp](lens-vp.md) TL;DR, critique 2; [research-gaps](research-gaps.md) §4 | "Certified within 1.6% of the best possible" is certified on the 0.1 mm raster only; the floor moved 2–13% with the grid | Scope to the raster; add a refinement study |
| 10 | [lens-sy](lens-sy.md) §3 and P3; [lens-ls](lens-ls.md) TL;DR; round-3 context point 5 | "Mirrors a 5 mm loop above 12 kHz" is wrong (6% mirrored). The impedance-matching principle is wrong as stated | Half-mirroring at a/ℓ_m ≈ 2–5. Restate the principle as a regime pair plus termination |

### Corrections by file

#### reports/Physics-first PCB layout.md

1. **§1 bullets.**
   - Current: "A numpy PEEC hot-loop solve takes ~1 ms and agrees with FastHenry within 1.3% [C]." and "One adjoint solve prices every copper edit [C]."
   - Problem: the agreement is for 4 loops (w/h 0.3–5) at 100 MHz. The adjoint statement fails for cuts and for finite edits (lenses CT, SY, CD, VP).
   - Replacement: "A numpy PEEC hot-loop solve takes ~1 ms and agrees with FastHenry within 1.3% on four loops (w/h 0.3–5, 100 MHz); with seven equal filaments per trace it reads 11–65% low on wide traces (w/h ≥ 10), so the reference now uses graded filaments [C, rt_loop_proxy]. One forward and one adjoint solve price every small copper edit when combined with the edit's polarization tensor; finite edits need an exact rank-k update [C, lenses CT, CD]."
2. **§1 bullet.**
   - Current: "A µs proxy (MS2) picks the best of 10 candidate loops 96–98% of the time, against 16–66% for "loop area" [C]".
   - Replacement: "At a fixed stackup, a µs proxy (MS2) picks the best of 10 candidate loops 97–100% of the time, plain trace length (height × squares) 82–99% and plan-view area 66–97% [C, rt_loop_proxy]. The often-quoted 16% for area comes from candidate sets that mix stackups."
3. **§2 table, the "Return via…" row.**
   - Current: "Slot ≈ 0.08–0.13 nH/mm; same-edge cables ~40 dB, slower edges ~3 dB [C]".
   - Replacement: "Slot ΔL ≈ μ0·l/(2 ln(4l/g)), e.g. 2.5 nH for 20 × 0.5 mm; same-edge cables 6–48 dB depending on orientation (40 dB was an assumed input); slower edges ~3 dB in one case [C, rt_world_cm]".
4. **§3, the joint P&R bullets.**
   - Current: "joint search beat a longer sequential run on 5/5 boards (median −17% routed objective) and a restart portfolio on 3/5".
   - Append: "(sign tests p = 0.06 and 1.0; over both sizes joint ties the equal-CPU portfolio 5/10, median J ratio 0.96, 95% CI 0.83–1.24; run-to-run spread of one board ×1.18) [C, rt_jpr_stats]".

#### docs/digests/physics-first.md

5. **Line 30.**
   - Current: "In the EMI chain topology beats tweaks by 20–40 dB."
   - Replacement: "In one worked EMI case, removing a slot or a split under the net beats edge-rate tweaks by 20–35 dB; the often-quoted 40 dB for co-located cables was an input, and the real benefit is 6–48 dB by orientation [C, rt_world_cm]."
6. **Line 48.**
   - Current: "One adjoint solve prices every copper edit."
   - Replacement: "One adjoint solve plus the edit's polarization tensor prices every small copper edit; finite edits use exact rank-k updates."
7. **Line 50.**
   - Current: "Numpy PEEC agrees with FastHenry within 1.3% at ~1 ms [C]."
   - Append: "(4 loops, w/h ≤ 5, 100 MHz; graded filaments needed for wide traces)".

#### docs/topics/physics/README.md

8. **TL;DR bullet 4.**
   - Current: "A numpy PEEC loop solve takes about 1 ms and agrees with FastHenry within 1.3%, and one adjoint solve prices every copper edit".
   - Replacement: as in item 1.
9. **TL;DR bullet 3.**
   - Current: "Physics-origin rules were right in 80 of 91 cases, but habit rules were wrong in 10 of 15."
   - Append: "(one auditor's judgement [I]; 95% intervals 0.80–0.93 and 0.42–0.86, [lens-in](lens-in.md))".
10. **Principle 3, "What it replaces / Evidence".**
    - Current: "Height to the reference is the strongest knob."
    - Replacement: "Height to the reference is the strongest knob for loops (mutual L ∝ h_a·h_v). It barely moves capacitive coupling from wide dv/dt copper (C_m ∝ h^0.19–0.74, [lens-sy](lens-sy.md))."
11. **Principle 4, evidence.**
    - Current: "decap reach 4–24 mm".
    - Replacement: "decap reach 4–24 mm between the decaps' SRF and the plasma frequency f_p ([lens-ls](lens-ls.md)), uncertain by 1.4–2.4× through the mounting inductance".
12. **Principle 7, evidence.**
    - Current: "EMI: both cables on one edge buys ~40 dB, removing a slot 24 dB, slower edges 3 dB [C]".
    - Replacement: "One EMI case: removing a slot 24 dB (a split 38 dB), a stitching cap ~10 dB, slower edges 3 dB; co-locating the cables 6–48 dB depending on orientation (the 40 dB was an input); damping the ring band 12–21 dB [C, rt_world_cm, rt_damping]".
13. **Principle 10, evidence column.**
    - Add: "[I]; on toy boards, routed-objective refinement improves a sequential start 10/10 (−18%) but ties an equal-CPU restart portfolio 5/10 [C, rt_jpr_stats]".
14. **Principle 11, evidence.**
    - Current: "The µs proxy MS2 picks the PEEC-best hot loop 96–98% of the time; loop area does so 16–66% [C]".
    - Replacement: the fixed-stackup numbers of item 2.
15. **Conflicts.**
    - Mark the heatsink 22 vs 26 pF and the thermal λ conflicts as resolved (assumptions; [red-team](red-team.md) §2).
    - Add the fill resolution (items 30 and 32).

#### docs/topics/physics/solver-ladder.md

16. **TL;DR.**
    - Current: "One adjoint solve prices every copper edit, but it misses cuts: a 6 mm slot was estimated at 0.27 mW against 8.1 mW exact [C]."
    - Replacement: "One adjoint solve gives the first-order price of every small edit once the edit's polarization tensor is applied: a slit across the flow costs (π/4)R_s·Δψ_u·Δψ_λ (lenses CT, SY). The plain area-weighted adjoint missed a 6 mm slot 30× (0.27 vs 8.1 mW). Finite edits use exact Woodbury updates (lens CD)."
17. **TL;DR.**
    - Current: "plan-view loop area picks it 66% (fixed stackup) or 16% (mixed widths and layers)".
    - Append: "; at a fixed stackup plain trace length picks it 82–99% [C, rt_loop_proxy]".
18. **F2 row.**
    - Current: "Image PEEC within 1.3% of FastHenry at 100 MHz [C]".
    - Replacement: "Image PEEC within 1.3% of FastHenry at 100 MHz on 4 loops with w/h 0.3–5. With 7 equal filaments it reads 11% (w/h 10–20) to 21% (w/h 20–60, p10 42%) low; use ≥ 31 cosine-graded filaments [C, rt_loop_proxy]".
19. **Trust radii.**
    - Current: "itself within 1.3% of FastHenry on 4 cases".
    - Append: "(w/h 0.3–5 only)". Add a validity column to the table.
20. **MS2 row.**
    - Current: "Spearman 0.999; median +9…+14%; p90 ≤ +31%".
    - Replacement: "Spearman 0.999; median +7.7% against a graded reference (+9…+14% against PEECN, part of which is PEECN's own error)".

#### docs/topics/physics/open-solvers.md, pdn-and-commutation.md, physics-in-the-loop-optimization.md, docs/ideas/physics-first/simulation.md

21. Every "agrees with FastHenry (on a meshed plane) within 1.3%" and "matches FastHenry within 1.3%": append "(4 loops, w/h 0.3–5, 100 MHz)". In [physics-in-the-loop-optimization](physics-in-the-loop-optimization.md), add that PEECN needs graded filaments for w/h > 10 before it serves as the reference.

#### docs/topics/physics/joint-place-route.md

22. **Line 115.**
    - Current: "which picks the PEEC-best loop 96–98% of the time where plan-view area picks it 16–66%".
    - Replacement: "which picks the PEEC-best loop 97–100% of the time at a fixed stackup, where plain trace length picks it 82–99% and plan-view area 66–97% [C, rt_loop_proxy]".

#### docs/topics/physics/joint-place-route-experiment.md

23. **TL;DR bullet 1.**
    - Current: "beat a longer sequential SA on 5/5 30-part boards (median −17% routed objective J) and an equal-CPU restart portfolio on 3/5 (median −10%)".
    - Append: "(exact sign tests: p = 0.06 and p = 1.0). Over both sizes, joint ties the equal-CPU portfolio 5/10 (median J ratio 0.96, 95% CI 0.83–1.24). The physics term's effect is 0.99 (0.93–1.05). Only 'joint improves its own start' is significant (10/10, p = 0.002) [C, rt_jpr_stats]".

#### docs/topics/physics/fields-emi-budget.md

24. **TL;DR.**
    - Current: "Putting both cables on the same edge buys about 40 dB."
    - Replacement: "Putting both cables on the same edge removes the voltage between them (PEEC: 43–63 dB). It leaves the board-vs-cable mode, so it buys 6–30 dB when the return voltage runs away from the cable edge and 24–48 dB when it runs parallel to it (lumped estimate, [C, rt_world_cm])."
25. **TL;DR.**
    - Current: "**Topology beats tweaks by 20–40 dB.**"
    - Replacement: "**In this case, removing a slot or split beats edge-rate and series-R tweaks by 20–35 dB; ring damping, not modelled here, is worth 12–21 dB at the ring band.**"
26. **Table, case D.**
    - Current: "B − 40 dB (PEEC: 43–63 dB less)".
    - Replacement: "B − 40 dB assumed (PEEC: 43–63 dB less voltage between the cables); the board-vs-cable mode limits the real benefit to 6–30 dB in the worst orientation".
27. **§3 item 1.**
    - Current: "1. **Cable attachment points on one edge** (κ → ~0): 40 dB."
    - Replacement: "1. **Cable attachment points on one edge** (κ → ~0 removes the inter-cable term): 6–48 dB by orientation."
28. **Recommendation 3.**
    - Current: "It is worth 40 dB here, more than any routing rule."
    - Replacement: "It is worth 6–48 dB here, depending on orientation; model the board-vs-cable mode, not only κ."
29. **Script.** In `fe_emi_budget.py` (and `in_emi_voi.py`), replace the `same_edge_db` constant with a board-vs-cable term: I_same ≈ ω·c_far·ΔV/|1 + jω·C_tot·Z_cm|, with c_far the capacitance to the world of the board region beyond the return's voltage drop (rt_world_cm).

#### docs/topics/physics/fields-si-emi.md and rf-geometry.md

30. **fields-si-emi line 76.**
    - Current: "at 1h by −6.5%".
    - Replacement: "at 1h by −5% (thin copper) to −8.4% (t = 0.35h); at 0.5h by −13% to −21%; under 2.2% at ≥ 2h [C, rt_fill_z0, converged to 0.1 point]".
    - Make the same change in rf-geometry ("at g = h by −6.5%").
31. **fields-si-emi TL;DR.**
    - Current: "about 0.08–0.13 nH per mm of slot".
    - Replacement: "ΔL ≈ μ0·l/(2 ln(4l/g)): 2.5 nH for 20 × 0.5 mm. It is not linear in l. It reads up to 1.5× above PEEC for short narrow slots and below Ott's l·ln l data for long ones".

#### docs/topics/physics/rule-genealogy-si-emi-rf.md

32. **S18.**
    - Current: "Z0 −3.7% at gap h".
    - Replacement: "Z0 −5.0% at gap h, −1.2% at 2h, −0.4% at 3h for thin copper (−8.4%/−2.2%/−0.8% at t = 0.35h) [C, rt_fill_z0]; the earlier −3.7% came from a thin strip on a coarse grid (12 cells per h, box 12h tall)".

#### docs/topics/physics/power-copper.md

33. **§5.**
    - Current: "The copper's 10–18 mΩ gives Q 31–173".
    - Replacement: "The copper's 10–18 mΩ gives Q 31–173, using R from a fixed 2-square loop while L is a free input. For wide copper the Q is h/δ ([lens-th](lens-th.md)). Plane pairs below ~30 MHz are different: there copper alone gives Q 1–10 on 0.1 mm cores [C, rt_sheet_return]."
    - In the same paragraph, "Copper never damps ringing." becomes "Copper barely damps hot-loop ringing."

#### docs/topics/physics/cross-workstream-synthesis.md

34. **S1.**
    - Current: "for two extra solves".
    - Append: "within one topology and one linearization. Vias, cuts and new connections are topological events priced by exact rank-k updates (lenses CT, CD); switching or sampled circuits need a periodic adjoint (lens SY)."

#### docs/topics/physics/research-gaps.md

35. **TL;DR bullet 3 and gap 2.**
    - Current: "The hardest physics regime is where most converters switch." and "Most DC-DC converters switch near f_x".
    - Replacement: "Most converters switch near or above f_x. For intact planes the transition now has closed forms (lens LS), and fundamentals above ~300 kHz on 1 oz return within a few mm. At 100 kHz, about 18% of the return current still flows beyond ±5 mm (h = 0.1 mm) [C, rt_sheet_return]. The open regime is slotted, perforated and finite planes, and DC to tens of kHz near precision analog."
36. **§4.**
    - Current: "\"Near-optimal\" is unprovable today".
    - Replacement: "Near-optimality is provable for self-energy terms on a fixed raster (lens VP's floors). For continuous layouts it needs a refinement study, and for couplings and joint placement it remains unprovable."
37. **§1 table, "Decisions made early matter most".**
    - Append: "(one EMI case; the 40 dB was an assumed input)".

#### docs/topics/physics/thermal-physics.md

38. **TL;DR.**
    - Current: "On such a board "keep hot parts 5–10 mm apart" buys little".
    - Replacement: "On such a board, spacing hot parts lowers the mean rise little. It still moves a neighbour's peak by 10–20% (E5) and matters for fatigue, current hogging and plumes ([lens-th](lens-th.md))".

#### docs/topics/physics/lens-th.md

39. **TL;DR bullet 1.**
    - Current: "Every unwanted joule needs a designed destination, and copper can never be it."
    - Replacement: "Every unwanted joule needs a destination. For rings above ~50 MHz over gaps of 0.1 mm or more, copper cannot be it: for wide copper with δ ≪ t, the copper-loss Q is h/δ (15–170 for hot loops). Below ~30 MHz on thin cores copper is a real damper (0.1 mm, 1 oz: Q = 1.0/2.8/6.2 at 1/3/10 MHz; 25 µm cores: Q ≈ 5 at 100 MHz) [C, rt_sheet_return]."
    - Delete "That is a theorem, and it reproduces round 1's "Q 31–173" exactly [C]." Round 1 used the same formula, so this is an identity, not a check.
40. **TL;DR bullet 1.**
    - Current: "Ring-band emission scales with Q (19.9 dB per decade [C]), so damping is a 20–27 dB lever that round 1's EMI chain leaves out."
    - Replacement: "The ring-band peak scales with Q (19.9 dB per decade) until the edge spectrum takes over. Damping from Q 10–20 to ~1 buys 12–21 dB at the ring band (2–5 ns edges, ring amplitude ≈ supply) [C, rt_damping], a lever round 1's EMI chain leaves out."
41. **D1.**
    - Current: "Edge crowding in narrow strips lowers Q up to ~2×."
    - Replacement: "By Wheeler's incremental-inductance rule, microstrip Q is within −7% to +18% of h/δ for w/h ≥ 0.5 and 0.67·h/δ at w/h = 0.25 [C, rt_sheet_return]."
42. **D1.**
    - Current: "That gives h/δ = 30.8/76.0/173.4 and 102.8, against round 1's 31/76/173/103 [C]."
    - Append: "(the same formula as round 1, so the agreement is an identity)".
43. **Critique 3.**
    - Current: "while damping Q from 10–20 to ~1 buys 20–26 dB at the ring band."
    - Replacement: "while damping Q from 10–20 to ~1 buys 12–21 dB at the ring band once the edge spectrum is included [C, rt_damping]."
44. **D4.** Add one line: "The thin-core damping here is mostly copper loss: δ/d is 0.10 at d = 25 µm and 0.72 GHz, against tanδ 0.02, which qualifies the TL;DR's 'copper can never be it'."

#### docs/topics/physics/lens-in.md

45. **TL;DR bullet 2.**
    - Current: "under strong selection MS2 misses the winner by +64% beyond its usual bias [C]."
    - Replacement: "Under strong selection, MS2's winner error drifts only +3% → +6.5% against a graded PEEC reference. The +64% first reported was the reference's own error: PEECN's 7 equal filaments read 11–42% low where the winners sit (w/h ≫ 10) [C, rt_loop_proxy]. So validate the reference, not only the proxy, where the optimizer selects."
46. **D4.**
    - Current: "its error on the winner drifts +16% → +33% → +64% beyond its median bias [C]."
    - Replacement: "its error on the winner drifts +2.9% → +5.8% → +6.5% against a graded reference (+16/+33/+64% against PEECN, whose error grows with w/h)."
    - Keep the advice "calibrate where the optimizer selects", and apply it to the reference too.
47. **D2 table.** Add a note: "Against a graded reference: MS2 bias +7.7%, σ_u for contenders 0.020, picks 96.8%; area 17.3%; PP 88.8% [C, rt_loop_proxy]."
48. **TL;DR bullet 3.**
    - Current: "33–84% of total VOI" and "A first-prototype pre-scan with 3 dB error recovers 66–81% of the offset's value [C]."
    - Replacement: "In round 1's EMI case, with its stated ranges, the enclosure, cable and test-setup offset carries 33–84% of total VOI. The share falls to 49% with a 10 dB-wide offset prior, and to 10–13% if co-locating the cables buys 6–30 dB rather than the assumed 35–60 dB (in which case the best action also changes) [C, rt_voi_sensitivity]. A pre-scan informs the next board in the same enclosure class. For the board being scanned the layout is already fixed: its post-build EVSI is 0 under the same loss."
    - Change the §5 column header "Pre-scan, 3 dB" to "Pre-scan before layout (earlier board of the class), 3 dB".
49. **TL;DR bullet 5.**
    - Current: "cables on one edge cut total VOI 30× [C]".
    - Append: "if co-location buys the assumed 35–60 dB".
50. **§4.** Add: "The active-subspace numbers use the 7-filament reference; re-check with graded filaments."

#### docs/topics/physics/lens-cd.md

51. **TL;DR bullet 2.**
    - Current: "In a uniform sheet ρ = ½, so deleting a strip costs exactly twice its first-order price".
    - Replacement: "On a square grid every interior strip has ρ = ½ (Foster: ρ = 2/z), so deleting one costs exactly twice its first-order price. On a triangular grid the factor is 1.5×, on a honeycomb 3× [C, rt_cut_law]. The mesh-independent statement is the removed region's polarization tensor: 2 × area for a disc, which is why round 1's hand-set factor 2 worked for compact holes."
52. **D1.**
    - Current: "the crack law with length (k+1) cells gives 0.96–1.02 of exact [C]".
    - Replacement: "the crack law with length (k+1) cells gives 1.57, 1.14, 1.02 and 0.96 of exact for 1, 4, 16 and 32 strips [C]: it holds once the slit spans about 16 cells".
53. **TL;DR bullet 3.**
    - Current: "passports for 4,415 pieces × 4 bands × 10 budgets took ~25 s and matched brute force to 2×10⁻⁹".
    - Append: "(an algebraic check of the rank-1 updates; the model's physical error is untested: 0.5 mm cells on 0.8 mm, ε_r = 1, no skin effect)".
54. **§4 table, "One pour, three jobs".**
    - Current: "Far column past the inductor pad: 9 mK, 25 µΩ, world share 0.19, the highest".
    - Append: "(ε_r = 1 electrostatics; FR-4 under the copper lowers world shares by up to ~ε_r, the ranking probably less)".
55. **§4 table, "Leverage".**
    - Current: "A 96-solve sketch (27 ms) finds all 44, no false flag".
    - Append: "(these are ρ = 1 bridges; on a slotted uniform sheet the same sketch flags 44 of 63 strips with ρ > 0.6, with 35 false flags)".
56. **Critique 2.**
    - Current: "Removals are off by 1/(1 − ρ): ×2 even for a compact hole".
    - Replacement: "Removals are off by the edit's polarization factor: about ×2 for compact holes (exactly ×2 for one strip on a square grid), unbounded for slits and necks".

#### docs/topics/physics/lens-vp.md

57. **TL;DR bullet 2.**
    - Current: "and the human tree (2.092 mΩ) carries 15.8% avoidable loss".
    - Replacement: "and, on round 1's 0.1 mm raster, the human tree (2.092 mΩ) carries 14.5–15.8% avoidable loss. The raster floor is not grid-converged: at equal area it fell 2.2–12.8% from the 0.2 mm to the 0.1 mm grid (VP's logs). A certificate for real layouts needs a refinement study or a discretization whose error has a known sign."
58. **Critique 2.**
    - Current: "Round 1's own SIMP is certified within 1.6%".
    - Replacement: "Round 1's own SIMP is certified within 1.6% of every layout on its 0.1 mm raster".
59. **TL;DR bullet 4 and D5.**
    - Current: "Half the return lies within ℓ50 ≈ R_s/(2π·μ0·f) of the trace, whatever h".
    - Replacement: "Half the return lies within ℓ50 ≈ R_s/(2π·μ0·f) of the trace for ℓ ≳ 6h (exact: 0.42–0.53·ℓ_m for h ≤ 0.1·ℓ_m; 79 Hz·m instead of 62 at ℓ = 3h) [C, rt_sheet_return]".
60. **D5, containment.**
    - Current: "f50·ℓ = 56–70 Hz·m for ℓ = 1–10 mm and h = 0.1–1.6 mm".
    - Replacement: "f50·ℓ = 56–70 Hz·m for ℓ ≥ 6h, and 80–84 Hz·m at ℓ = 3h (the rows h 0.5/ℓ 1.5 and h 1.6/ℓ 4.8 of vp_rl_band's own log, which lie inside the quoted range)".
61. **D5, away from the trace.**
    - Current: "At ≥ 100 kHz the return outside ±5 mm is only the image's own tail".
    - Replacement: "Measured as the current outside ±5 mm, |1 − F|: 18% (h 0.1 mm) and 27% (h 1.6 mm) at 100 kHz, 3.4% and 20% at 500 kHz, and 61–62% at 20 kHz. Most of it at 100 kHz is in quadrature, which the in-band magnitude 1 − |F| (1.6% and 21%) hides. A common-impedance victim sees its magnitude [C, rt_sheet_return]."
62. **D5, spectrum.**
    - Current: "puts 10/50/90% of the DC-to-HF inductance drop at 17/65/360 kHz".
    - Replacement: "puts 10/50/90% of the DC-to-HF inductance drop at 17/65/360 kHz for h = 0.1 mm on a 50 mm-wide plane, and 8.6/41/315 kHz on 100 mm. An independent PEEC gives 10.7/60/490 kHz (50 mm), so the band edges are uncertain by ±50% and depend on plane width [C, rt_sheet_return]".
    - Fix the setup note "[C; 0.3 mm trace, 100 mm plane]" to match.
63. **Critique 3.**
    - Current: "Gap 2 concerns DC-to-kHz returns near precision analog, not converter fundamentals".
    - Append: "above ~300 kHz on 1 oz; at 100 kHz about 18% of the return current still flows beyond ±5 mm".

#### docs/topics/physics/lens-sy.md

64. **§3, "f_x found four times".**
    - Current: "1 oz mirrors a 5 mm loop above 12 kHz".
    - Replacement: "ℓ_d = a marks only the onset: at that frequency a loop is about 5% mirrored. Half-mirroring needs a/ℓ_m ≈ 2–5 (ℓ_m = 2ℓ_d), e.g. ~93 kHz for a 5 mm loop at h = 0.1 mm on 1 oz; 90% needs a/ℓ_m ≈ 10–45 [C, rt_sheet_return; lens LS's 3-D table agrees]".
    - Correct "a 20 mm region above 3 kHz" the same way.
65. **P3.**
    - Current: "Valid for field patterns larger than ℓ_d".
    - Replacement: "Half-valid for patterns of size a ≈ 4–10·ℓ_d, and within 10% for a ≳ 20–90·ℓ_d".
66. **Critique 5.**
    - Current: "At f_sw the plane already mirrors the hot loop at board scale".
    - Replacement: "At f_sw ≥ ~300 kHz on 1 oz the plane mirrors a 5–10 mm hot loop by 78–89% (2-D, h = 0.1 mm); at 100 kHz by 52–62% [C, rt_sheet_return]".
67. **D1.**
    - Current: "C_m′ = ε0·w_a·w_v/(πD²), independent of h".
    - Replacement: "C_m′ ≈ ε0·w_a·w_v/(πD²), nearly independent of h for wide copper. FD gives h^0.19 for 2 mm strips and h^0.74 for 0.15 mm strips, and the patch formula reads 26–50% below FD for 2 mm strips."

#### docs/topics/physics/lens-ct.md

68. **TL;DR bullet 4 and D2.**
    - Current: "Charge conservation on the board's boundary gives one-cable CM current exactly".
    - Replacement: "Charge conservation on the board's boundary gives one-cable CM current exactly, I_CM = −jω·Σ C_i,ext·V_i, with V_i measured from the outside world. One electrostatic solve gives every C_ext. The board's own potential needs the CM path impedance Z_A: with circuit voltages, I_CM = −jω·Σ C_i,ext·V_i/(1 + jω·C_tot·Z_A). The error of dropping the denominator is ≤ 5 dB for a free 5 pF board up to 300 MHz, and 10–29 dB at 100–300 MHz for 30 pF and 150–500 Ω [C, rt_world_cm]. Shim and Hubing's ratio is the Z_A → ∞ limit."
69. **Critique 6.**
    - Current: "(cables on one edge, 40 dB)".
    - Replacement: "(cables on one edge, an assumed 40 dB; 6–48 dB by orientation, rt_world_cm)".

#### docs/topics/physics/lens-ls.md

70. **TL;DR bullet 1.**
    - Current: "at Z0 = Z they reduce to a pure delay".
    - Replacement: "with resistive terminations each first-order term is already a pure delay. Z0 = Z removes the second-order amplitude error −(θ²/8)(m − 1/m)² and the excess delay [C, rt_impedance_match]".
    - Soften "and settles t_r/6-vs-t_r/2 [C]" to "and explains t_r/6 vs t_r/2 for capacitive loads [C]".
71. **TL;DR bullet 2.**
    - Current: "That closes most of round 1's Tier-1 gap 2".
    - Replacement: "That closes gap 2 for intact, thin, infinite planes (images tuned on two cases); slotted, perforated and finite planes stay open".

#### Round-3 context (coordinator's reading; not a doc file)

72. **Point 1.** "One adjoint prices every copper edit is wrong for finite edits" should read: wrong as implemented (area-weighted) even for small cuts. Right for small edits when the edit's polarization tensor multiplies the forward and adjoint fields. Exact for finite edits via rank-k updates. CD's ρ = ½ is the square grid.
73. **Point 2.** Add the |1 − F| metric. At 100 kHz, 18% of the return lies outside ±5 mm (h = 0.1 mm), so "fundamentals already return under the loop" holds above ~300 kHz on 1 oz.
74. **Point 5.** Restate: the pair ε_L = θ·Z0/Z and ε_C = θ·Z/Z0 selects which parasitic matters. With resistive terminations, a short line is a pure delay to first order for any Z0, and matching only removes the second-order error. With reactive loads the delay-only line is Z0 = R_S. Outside ~1–170 Ω no PCB conductor can be matched. The surviving content is "terminate in Z0 to absorb", which is point 6 (damping), not invisibility.
75. **Point 6.** Copper cannot damp rings above ~50 MHz over gaps of 0.1 mm or more. It is a significant damper of plane-pair resonances below ~30 MHz, and of thin (≤ 50 µm) cores up to ~1 GHz.
76. **Point 8.** "Exact" rungs are exact only within their models (square grid, raster, ideal plane). Each guarantee needs its model scope, and model error must be reported separately from solver error.

## Recommendations for our system

- Apply items 1–3, 16–20, 24–29 and 45–48 before any optimizer uses PEECN, the EMI chain or the VOI engine. They change what those components report.
- Add each corrected number to the physics regression suite as a test against its `rt_*` script, so a future edit cannot silently reintroduce it.

## Conflicts and open questions

- Item 24's 6–48 dB comes from a lumped estimate; a full-wave board-plus-cable run should replace it.
- Item 62's band edges differ between two independent PEECs by 1.4–1.6×; a meshed-plane FastHenry-class run could settle them.

## Sources

- Scripts [C]: [rt_cut_law](../../../tools/research/physics/rt_cut_law.py), [rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py), [rt_damping](../../../tools/research/physics/rt_damping.py), [rt_impedance_match](../../../tools/research/physics/rt_impedance_match.py), [rt_world_cm](../../../tools/research/physics/rt_world_cm.py), [rt_loop_proxy](../../../tools/research/physics/rt_loop_proxy.py), [rt_voi_sensitivity](../../../tools/research/physics/rt_voi_sensitivity.py), [rt_jpr_stats](../../../tools/research/physics/rt_jpr_stats.py), [rt_fill_z0](../../../tools/research/physics/rt_fill_z0.py).
- Evidence and verdicts: [red-team](red-team.md).

See also: [red-team](red-team.md) · [README](README.md) · [research-gaps](research-gaps.md)
