# Physics-first ideas: optimization and generative geometry (OP)

Workstream 6 of the physics-first effort. Detail and evidence:
[physics-in-the-loop-optimization](../../topics/physics/physics-in-the-loop-optimization.md) and
[copper-shape-synthesis](../../topics/physics/copper-shape-synthesis.md). The joint
placement-and-routing state these ideas plug into is owned by
[joint-place-route](../../topics/physics/joint-place-route.md); entity names follow
[physics-ir](../../topics/physics/physics-ir.md). Numbers tagged [C] come from
[op_topopt_pour.py](../../../tools/research/physics/op_topopt_pour.py) and
[op_placement_kernels.py](../../../tools/research/physics/op_placement_kernels.py).

Tags: *new* (not found in prior PCB work), *combo* (known parts, new combination for PCB),
*sharp* (sharpens an existing rule or idea). Effort: S (days), M (weeks), L (months).

## A. Copper as a field: shape synthesis

**OP1. One sheet operator for three physics.** — *new, S.* DC IR drop, the inductive limit of a pour over a reference plane, and heat spreading are the same 2-D screened-Laplace problem with sheet coefficients 1/R_s, 1/(μ0·h_eff) and k·t (+ convection). Build one sparse solver and one adjoint and feed it three coefficient maps instead of three tools. Test: reproduce padne DC results and a FastHenry plane-pair inductance on 5 boards within 10%.

**OP2. Synthesize a power zone by topology optimization.** — *combo, M.* SIMP with a density filter, Heaviside projection and an OC/MMA update turns "pour for net X with area A between these pads" into a minimum-loss copper shape, legalized to a KiCad zone. At equal area it beat a well-drawn trunk-and-branch layout by 14.5% in loss on our test case (1.79 vs 2.09 mΩ) [C]. Test: 20 high-current nets from open boards, loss and peak J vs the designer's copper at equal area.

**OP3. Copper priced by routing demand.** — *new, M.* Give the pour optimizer a per-cell area price equal to the router's congestion price, so pours yield where signals need to pass and fill where they do not. In the POC a 4× price on a corridor halved the copper placed there for a 26% loss penalty [C]. Test: on 2-layer boards, route completion and IR drop with priced vs unpriced pours.

**OP4. Multi-rail plane partition as multi-phase optimization.** — *combo, L.* One density field per rail on a shared layer, a sum-to-one constraint per cell, and a clearance term on the overlap of the fields dilated by half the gap; solve by phase-field or alternating priced single-rail solves. It replaces hand-drawn splits and the Voronoi default with partitions that equalize marginal loss per mm². Test: 10 boards with 3+ rails on one plane, IR margin and split crossings vs the designer's partition.

**OP5. Return-aware pour.** — *new, M.* Add the high-frequency loop inductance, computed with an h_eff(x,y) map of the distance to the nearest continuous reference, to the DC objective, so switching current avoids slots and split crossings. Above f_c = R_s/(2π·μ0·h) (0.3–0.6 MHz for 1 oz over 0.1–0.2 mm) current spreads by inductance, not resistance [C]. Test: the POC slot case, then three boards with deliberately slotted references checked in FastHenry.

**OP6. Area allocation between nets by marginal value.** — *new, S.* With widths proportional to current, a net's minimum loss at area A is R_s·(Σ I·l)²/A, so the loss-optimal split of shared area gives each net area in proportion to √(weight)·Σ I·l. An equal split of 100 mm² between nets with Σ I·l = 100 and 50 A·mm costs 11% more loss than the proportional split [C]. Test: compare against full multi-net topology optimization on 10 synthetic layers.

**OP7. Etch-robust copper.** — *combo, M.* Optimize the eroded, nominal and dilated designs together (robust formulation), with the erosion set from the fab's ±20% width tolerance. Qian and Sigmund built this for over- and under-etched MEMS. Necks then keep their resistance budget at the worst etch. Test: Monte Carlo on erode/dilate of legalized shapes; worst-case R vs nominal-only optimization.

**OP8. Teardrops and fillets sized by physics.** — *sharp, S.* The shape derivative of loss at a copper edge is proportional to the tangential current density squared, so copper pays most at pad entries, inside corners and junctions. Grow fillets there until the marginal mΩ per mm² falls below the area price, instead of a fixed teardrop percentage. Test: compare loss and peak J against KiCad's default teardrops on 50 pad entries.

**OP9. Thermal-relief choice per pad.** — *sharp, S.* Spokes trade solder heat flow against resistance: four 0.3 mm spokes across a 0.4 mm gap add 0.22 mΩ to a 2×2 mm pad, two spokes add 0.52 mΩ [C]. Choose solid, 4-spoke or 2-spoke per pad from the pad's current and the assembly heat budget, not one board-wide setting. Test: reflow simulation and resistance for each choice on power pads.

**OP10. Via-field optimization.** — *new, M.* Treat via density on a layer-pair interface as a design field (vertical conductance per cell) and optimize it with the two sheets, then quantize to via sites with CP-SAT. Vias then land where the current actually transfers, which "≥1 via per amp near the pad" only approximates. Test: IR drop and via count vs the rule on 10 multi-layer power paths.

**OP11. Electro-thermal co-synthesis.** — *combo, M.* Couple Joule heating to the heat equation, with temperature-dependent resistivity (+0.39%/K), and put the hottest copper temperature in the objective as a p-norm. Busbar studies report more than 50% copper saving under temperature limits. Test: 1 oz vs 2 oz power stages; hot-spot temperature from a finite-volume thermal solver vs IPC-2152 sizing.

**OP12. Switch-node copper minimized under a thermal bound.** — *sharp, M.* The SW pour is a dv/dt antenna (C to plane and chassis) and a heat sink for the FETs. Minimize its area times dv/dt, subject to a junction-temperature bound from the thermal sheet solve, instead of "small SW node". Test: radiated proxy and Tj on 5 converter layouts.

**OP13. Two-layer co-design of forward and return copper.** — *new, L.* On 2-layer boards there is no plane; the loop is formed by the top and bottom pours together. Optimize both density fields with a partial-inductance objective (PEEC on a coarse grid) so they overlap where the current flows. Test: FastHenry loop L and DC loss vs the designer's 2-layer power path.

**OP14. Shield copper synthesis.** — *new, L.* Optimize grounded copper (and stitching vias) between an aggressor and a victim to minimize mutual capacitance and inductance, using the adjoint of the coupling. It replaces "add a guard trace" with a computed shape and shows when guard copper does nothing. Test: FasterCap/FastHenry coupling for synthesized vs guard-trace vs nothing.

**OP15. Antenna-aware copper exclusion.** — *new, L.* Replace a fixed antenna keep-out with a detuning-sensitivity map: the adjoint of the antenna's resonant frequency (or S11 at band centre) with respect to copper in each cell. Copper goes where it costs no detuning. Test: openEMS S11 shift vs keep-out area on 3 chip-antenna reference designs.

**OP16. Plane shapes that move cavity resonances.** — *combo, M.* Put the plane-pair eigenvalues (or impedance peaks at the decap set) in the objective, with stitching-via and plane-outline variables, to push resonances out of the noise band. Sigrity-style tools search decap sets; we would also change the plane outline. Test: cavity-model Z(f) before and after on 4-layer boards with known resonance problems.

**OP17. Current-density cap.** — *sharp, S.* Add a p-norm constraint on |J| so the optimizer cannot meet the loss target with a single hot neck; set the cap from IPC-2152 temperature rise or electromigration in fine features. Test: compare peak J and local ΔT of capped vs uncapped designs.

**OP18. Copper balance as a manufacturing field.** — *combo, S.* Add per-region copper-density bands per layer (plating uniformity, warp) as constraints in the same density framework, so thieving and synthesis are one problem instead of an afterthought. Test: density histograms and warp proxy vs post-hoc thieving.

**OP19. Shape catalogue and learned warm starts.** — *new, M.* Precompute optimal shapes for canonical cases (pad-to-pad, star of k loads, bus with taps, around one hole) over current ratios and aspect ratios. Train a small U-Net or neural operator to map boundary conditions to a density field that warm-starts the exact solve. Test: iterations to converge and final loss, warm vs cold start.

**OP20. Level-set polish after SIMP.** — *combo, M.* Convert the thresholded density to a signed distance field and run a few shape-derivative steps with a curvature limit. This gives smooth, arc-friendly outlines with exact boundaries and no grey cells. Test: loss and vertex count vs SIMP + contour only.

## B. Physics terms for placement (evaluated while parts move)

**OP21. Filament-PEEC loop term with an image plane.** — *sharp, S.* A Manhattan filament model with Grover's closed-form parallel-filament mutuals and a mirror image for the reference plane gives loop L within 1.5% of Grover's rectangle and within 1% of microstrip L′ [C]. It costs about 0.35 ms per loop in numpy on one core, about 1 µs on a GPU batch [I]. It is differentiable in pad positions and replaces "loop area" in the placer. Test: rank correlation with FastHenry on 30 hot loops vs the area proxy.

**OP22. Use path length × plane depth, not loop area, when a plane is close.** — *sharp, S.* With a solid plane 0.1 mm below, equal-area loops differ 1.7× in L, and L tracks perimeter to within 3% (0.052–0.055 nH/mm for 1.5 mm strips) [C]. Without a plane, area is a ±20% proxy. The objective must switch with h_eff/w, which the regime classifier knows. Test: same as OP21, split by stackup.

**OP23. Thermal Green's-function placement term.** — *sharp, S.* A convectively cooled board is a fin with spreading length λ = √(k·t/2h): about 5 mm for bare 1.6 mm FR-4 and 37–64 mm with copper planes [C]. Superpose K0(r/λ) kernels, with images for board edges, as a smooth ΔT term. Spacing then follows λ instead of "keep hot parts apart". Test: rank correlation with a finite-volume thermal solver on 20 boards.

**OP24. Noise potential instead of electrostatic density.** — *new, M.* ePlace spreads cells with an electrostatic potential. Add a second, physical potential: the aggressor near-field (dipole moment of each hot loop and dv/dt node convolved with a coupling kernel), which sensitive victims descend. It is one FFT per step, like ePlace's density. Test: victim coupling (FasterCap/FastHenry) vs keep-out rules on mixed-signal boards.

**OP25. Price of a millimetre.** — *combo, S.* For each part, report ∂(weighted budget spend)/∂(x, y, θ) from the kernels, in units like nH/mm, K/mm or mV/mm. The legalizer uses it to choose which part yields, and the LLM sees which part is physically pinned. Test: legalization displacement cost in physics units vs plain displacement.

**OP26. Orientation by current direction.** — *combo, S.* Gumbel-softmax orientation (as in Cypress) with the loop-L term, so a part rotates to put its current-carrying pins on the loop's closing side. Test: hot-loop nH after orientation search vs netlist-only orientation.

**OP27. Pad forces from pour solves.** — *new, M.* The derivative of a pour's loss with respect to a pad position is a boundary integral of energy density around the pad. Run a coarse (0.5 mm) pour solve every k placement steps and apply the result as a force, so loads drift toward their source along cheap copper. Test: IR drop after routing, with and without pour forces, on power-heavy boards.

**OP28. Batched physics screening of placement candidates.** — *combo, M.* Closed-form kernels (loop L, ΔT, coupling) evaluated for 10⁵–10⁶ candidate poses per second on a GPU reject physically bad placements before any router runs. Test: fraction of finalists that fail full-solver budgets, with vs without screening.

## C. Routing as current flow

**OP29. Gilbert-tree power routing.** — *new, S.* At fixed copper area, loss is minimized by widths proportional to current, and the minimum is R_s·(Σ I·l)²/A [C]. So a power net's topology should be the Steiner tree minimizing Σ I·l (a Gilbert network), and widths follow current. A competent trunk-and-branch layout already sits on this law (0.67 mm/A on every branch, 1-D loss within 0.2% of the optimum for its topology) [C]. The remaining 14.5% gain from topology optimization comes from topology and 2-D spreading. Test: Gilbert-tree + width rule vs IPC per-segment sizing vs full synthesis.

**OP30. Constant current density, not constant width.** — *sharp, S.* Taper power traces so width tracks the current each segment carries. It is the loss optimum at fixed area. IPC-2221's thermal width (w ∝ I^1.38 at fixed ΔT) answers a different question, so use the larger of the two widths. Test: loss and ΔT of tapered vs uniform-width trees at equal area.

**OP31. Physics-priced PathFinder.** — *sharp, M.* Edge costs in the negotiated router come from physics fields: reference continuity (h_eff and slot crossings), impedance deviation of the local width on that layer, and coupling potential to declared victims. PathFinder's history cost then becomes a measured shadow price. Test: return-path violations and crosstalk mV at equal completion vs plain PathFinder.

**OP32. One copper market for signals and pours.** — *new, L.* Signal routing and pour synthesis compete for the same cells per layer. Put them on one price field updated by a resource-sharing (Lagrangian) scheme, as in BonnRoute's min-max resource sharing. Router congestion prices and topology-optimization area multipliers are then the same dual variables. Test: completion + IR margin on 2-layer boards vs route-then-pour and pour-then-route.

**OP33. Route the loop, not the net.** — *combo, M.* Make the return path a routed object: reference-layer choice, stitching-via positions at each layer change, and the decap that closes the loop. Cost each by its loop-inductance increment from the filament kernel. Test: via-transition loop L and common-mode proxy vs "add a ground via nearby".

**OP34. Elastic bands with physics forces.** — *combo, M.* After topology is fixed, relax each critical path as an elastic band (Quinlan–Khatib), contracted by tension, repelled by victims' coupling potential and attracted to continuous reference. It improves spacing where it matters while keeping homotopy and DRC. Test: crosstalk and length vs PNS optimize on 20 buses.

**OP35. Curves only where they pay.** — *sharp, S.* An unmitred corner reflects |Γ| ≈ 0.002–0.003 at 1 GHz and 0.05–0.09 at 30 GHz [C], and octilinear wiring is only ~5% longer than any-angle. Use arcs or clothoids for > 20 GHz lines, flex bend zones and clearance-limited dense escapes (where arcs widen minimum gaps), and octilinear elsewhere. Test: TDR/S11 in openEMS for corner styles at 5, 20 and 40 GHz.

**OP36. Coupling-budgeted corridor capacity.** — *combo, M.* In the multicommodity-flow or SURF cut test, reduce each corridor's capacity by the parallel length the crosstalk budget allows (mV per mm of parallel run at that spacing), not just by width + space. Test: crosstalk violations after routing with and without budgeted capacity.

**OP37. Diff pairs and length matching as ribbon objects.** — *combo, M.* A pair is one ribbon with fixed internal geometry. Length matching is an equality constraint whose Lagrange multiplier prices meander area, so continuous or topological routing can reserve the right area. Test: meander area reserved vs needed on DDR/USB3 sets.

## D. Adjoints and sensitivities

**OP38. Adjoint copper advisor for any layout.** — *new, S.* One extra solve gives dJ/d(every cell) for J = loss, IR drop at a load, loop L or ΔT. Show the top cells where added copper buys the most mΩ per mm², and the copper that does nothing. Adjoint and finite-difference gradients agree to 10⁻⁶ in the POC [C]. Test: designers' acceptance of suggestions and the realized mΩ per mm².

**OP39. Neck finder by sensitivity.** — *sharp, S.* Rank copper by ∂R/∂(local width): the top cells are the bottlenecks that the "narrowest cross-section" graph check approximates. This also covers 2-D necks between vias and pads that a graph misses. Test: agreement with designer-identified bottlenecks; false positives vs the graph check.

**OP40. Budget shadow prices from adjoints.** — *combo, S.* Every budget's multiplier (nH, mV, K) comes from adjoint sensitivities at convergence. The design-reasoning layer can then say "relaxing the hot-loop budget by 0.1 nH frees 2 mm²" from computed numbers ([design-reasoning-architecture](../../topics/physics/design-reasoning-architecture.md)). Test: predicted vs realized trade when a budget is relaxed.

**OP41. Topological derivative for vias and voids.** — *combo, M.* The topological derivative gives the change from inserting a small hole (via antipad, slot) or a small conductor (stitching via) anywhere. It ranks antipad and stitching positions in one solve. Test: predicted vs re-solved change for 50 via insertions.

**OP42. Adjoint FDTD for small RF structures.** — *combo, L.* For matching stubs, transitions and pixelated filters, use MIT-licensed JAX/autograd FDTD or FDFD (FDTDX, ceviche) with fab-rule filters. Princeton's pixelated mm-wave inverse design shows the payoff. Test: one via transition and one matching network vs hand-tuned versions in openEMS.

## E. Search at scale

**OP43. Physics continuation.** — *new, S.* Optimize first with smooth, nearly convex terms (DC loss, thermal superposition, wirelength), then switch on HF loop, coupling and field terms as parts settle. This is homotopy in physics, like ePlace's density ramp. Test: final budget spend and runtime vs all terms from the start.

**OP44. Quality-diversity over physics descriptors.** — *combo, M.* MAP-Elites archives indexed by hot-loop nH, peak ΔT and worst victim coupling (mV) give the designer a portfolio along real trade-offs, not along geometric ones. Test: coverage and best-in-niche quality vs NSGA-II with the same evaluations.

**OP45. Multi-fidelity physics ladder with expected-value-of-information.** — *combo, M.* Kernel → 2-D sheet solve → PEEC/FastHenry → openEMS. Spend the next fidelity only on candidates whose budget margin is within the cheaper model's error band ([V4 trust radius](../original/verification.md#v4-proxy-trust-radius--sharpened)). Test: full-solver calls per accepted design vs fixed-rung successive halving.

**OP46. Adversarial excitation red team.** — *new, M.* Search the switching phases, edge rates and load steps that maximize victim noise or IR drop on a candidate, then optimize the layout against the worst case found (min-max). It extends V2 from reward hacking to physics. Test: noise under found worst cases vs nominal-only optimization.

**OP47. Greedy shape screening, exact finish.** — *sharp, S.* Energy-ranked removal from a full pour (ESO style) reached 1.88 mΩ in 14 solves, against 1.79 mΩ for full SIMP [C]. Use it to screen pour variants for many placements and run SIMP only on finalists. Test: rank agreement between greedy and SIMP over 100 placements.

**OP48. Surrogate-accelerated topology optimization.** — *combo, M.* Train a neural operator on synthetic pour problems (random pads, holes, currents) labelled by the exact solver. Use it for warm starts and inner-loop screening; every accepted design gets an exact solve. Test: speed-up and loss gap on held-out real boards.

**OP49. Criticality-proportional solver compute.** — *combo, S.* Allocate high-fidelity solves by |∂objective/∂geometry| × model uncertainty, so compute goes to binding budgets (extends I5). Test: budget violations found per CPU-hour vs uniform allocation.

## F. Legalization and manufacturability

**OP50. Contour-and-Minkowski legalizer with a physics re-check.** — *sharp, S.* Steps: marching-squares contour at ρ = 0.5, keep pad-connected islands, close by the minimum gap, open by the minimum width (round joins), clip keep-outs, simplify, re-solve. In the POC this cost 0.0–2.8% loss. An opening wider than a neck disconnected the net, which the re-check catches [C]. Test: run on every synthesized zone; report ΔR, ΔL and DRC.

**OP51. Minimum width inside the optimizer, not only after.** — *sharp, S.* Set the filter radius (or robust erode/dilate thresholds) from the fab's minimum width so the optimizer never draws a neck the legalizer must cut. Test: legalization ΔR and disconnect rate vs filter radius.

**OP52. Differentiable design rules.** — *combo, M.* Port foundry-rule topology optimization (Hammond et al.: minimum width, spacing, area and enclosed area via differentiable morphology) and OptiClear-style minimum-distortion legalization to PCB rules. Test: DRC violations at convergence and objective loss vs post-hoc legalization.

**OP53. Arc fitting at export.** — *new, S.* Fit biarcs to contours with the fab's minimum curvature radius, then write zone outlines or graphic polygons with arcs where KiCad accepts them, and short segments where it does not. Fewer vertices, smoother clearance and no acid traps. Test: vertex count and clearance margin vs segment export.

**OP54. CP-SAT for the discrete residue.** — *combo, S.* Keep continuous methods for shapes and positions. Give CP-SAT the discrete leftovers: via counts and sites, relief styles, pad connection modes, layer choices. Objective costs come from adjoint sensitivities. Test: solve time and budget spend vs greedy rounding.

**OP55. Zone recipes stored as intent.** — *new, M.* Save each synthesized zone's recipe (net, terminals, currents, area or price, objective weights, filter radius) in the board, so it re-synthesizes after a part move the way KiCad refills a zone. Test: ECO turnaround on moved parts; loss drift vs a frozen polygon.

## G. Plugging into the joint placement-and-routing state

**OP56. Copper fields as first-class state.** — *new, M.* The joint state ([joint-place-route](../../topics/physics/joint-place-route.md)) carries, per layer, a coarse copper-density field and a price field next to part poses and route topologies. Physics terms read the fields, and shape synthesis writes them while parts still move. Test: convergence of joint runs with and without copper fields.

**OP57. Physics stop rule.** — *sharp, S.* Stop refining a term when its marginal improvement per iteration, times its shadow price, falls below the cost of compute or below its budget slack. Compute then shifts to terms that still bind. Test: wall-clock to a budget-feasible design vs fixed iteration counts.
