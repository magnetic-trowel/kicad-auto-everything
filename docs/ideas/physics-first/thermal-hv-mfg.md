# Physics-first ideas: thermal, high voltage, manufacturing physics (TM)

Workstream 7. These ideas treat heat, insulation, fabrication, assembly and mechanics as physics that bounds and interacts with the electrical design. Evidence and numbers are in [thermal-physics](../../topics/physics/thermal-physics.md) and [hv-and-manufacturing-physics](../../topics/physics/hv-and-manufacturing-physics.md). [C] results come from `tools/research/physics/tm_*.py`.

The ideas build on:
- the ledger and dimensioned constraints ([I1/I2](../original/intent-and-why.md));
- the physics IR entities `heat_path` and `barrier` ([physics-ir](../../topics/physics/physics-ir.md));
- the critics catalog §E ([physics-critics-catalog](../../topics/physics/physics-critics-catalog.md));
- the thermal-kernel and copper-balance ideas OP23 and OP18 ([optimization](optimization.md)).

Tags: *new* (not found in the survey), *combo* (a new combination of known parts), *sharp* (a known idea made precise). Effort: S (days), M (weeks), L (months).

## A. The board as a heat spreader

**TM1. Thermal spacing in units of λ.** Compute the spreading length λ = √(G_s/h_total) per region from the stackup, local copper fraction and cooling. Examples: 38 mm on 2-layer 1 oz in still air, 8 mm on bare FR-4, 22 mm with forced air. Express every thermal distance as r/λ. When the board is smaller than about 2λ, the placer stops spreading hot parts, because there coupling at 10 mm is still 40% of self-heating [C]. It then maximises connected copper, edge and standoff exposure, and moats around victims. Test: on 20 boards, compare FV victim ΔT for "5–10 mm apart" placements vs λ-aware ones. *sharp, S*

**TM2. Image-lattice thermal kernel.** Precompute the FV response to 1 W once per stackup and cooling case. Superpose it at each source, adding a lattice of mirror images for the adiabatic edges. On a 60×40 mm board the kernel alone underestimated by 2–3×; with six rings of images it came within about 2% of a full solve [C]. This makes OP23's term accurate enough to rank placements. Test: rank correlation and absolute error vs FV across random placements and board aspect ratios. *sharp, S*

**TM3. Two-tier thermal evaluation.** Score proposals with the kernel from TM2. Run one FV solve (about 1 s at a 0.5 mm grid on 2 layers) only on accepted moves, and use its residual against the kernel as a learned correction for non-uniform copper. Superposition is exact for a fixed copper map, so only copper edits invalidate the kernel. Test: optimiser wall time and final ΔT error vs FV-every-move. *combo, S*

**TM4. Via return-on-investment critic.** Compute ∂T/∂N_via and ∂T/∂(plating) per via array with the FV solver. Add vias only while each one buys more than a set number of kelvin. The result changes with context: 9 vias cut the rise by 13% when a top pour already spreads the heat, and by 58% when the EP is the only top copper [C]. This replaces "as many vias as fit" with a computed stopping point. Test: via count and ΔT vs the TH-11 rule on EP parts. *sharp, S*

**TM5. Heat-flux-aware cut penalty.** Compute the heat-flux field −k∇T. Penalise every copper cut, slot, plane gap and trace crossing a spreader by ∫|q·n| dl. In our test, a cut across the flow cost 20–30× the same cut along it [C]. This replaces the binary "no perpendicular cuts" rule and tells the router to cross spreaders radially. Test: rerun TI's SNVA419 rule-4 case and compare penalties with FV ΔT on 50 random cuts. *sharp, S*

**TM6. Emissivity-aware copper exposure.** Solder mask emits at ε ≈ 0.9; bare copper and ENIG at 0.03–0.1. Radiation is about half the still-air cooling, so an unmasked spreader loses ~40% of its h [C]. Keep mask on heat spreaders and expose copper only where solder or a thermal interface needs it. Calibrate IR-camera checks with the same emissivity map. Test: FV with per-region ε vs an IR image of a masked and an unmasked spreader. *new, S*

**TM7. Per-face cooling map.** Assign h per face and region from orientation, enclosure and airflow. In still air a downward-facing side gets about half the convection of an upward one. Shadowed regions behind tall parts get less. Carry these assumptions in the IR `heat_path` so they appear in every report. Test: sensitivity of victim ΔT to the h map; flag decisions that flip within ±30% of h. *sharp, S*

**TM8. Thermal Δ-budget ledger.** Allocate the budget T_J,max − T_ambient across junction→case, pad/TIM, via array, spreading and convection, as an I1 ledger in kelvin. Each object reports its spend: for example "via array 9 K of 40" or "spreading 18 K". The LLM moves budget, not millimetres, and the critic shows which stage to fix. Test: on 10 power boards, does the top spender predict the fix that a human chose? *combo, S*

**TM9. Pulsed-load copper mass.** For pulses shorter than about 1 s, heat diffuses only √(αt) ≈ 3–11 mm in copper and 0.1–0.4 mm into FR-4 [C]. A local copper mass on the source's own layer (thicker copper, a coin, or a dense pour within that radius) beats board area. Use a transient RC ladder (Foster/Cauer) built from the FV mesh for motor starts, transmitter bursts and inrush. Test: peak ΔT from a transient FV solve, local mass vs equal area spread wide. *new, M*

**TM10. Metal standoffs as heat sinks.** A plated screw pad with a brass M3 standoff to a metal chassis is about 22 K/W including spreading. That equals the convection from roughly 23 cm² of two-sided board [C]. Put hot parts near such standoffs and treat each one as a thermal port in the placer, so mechanical fixing points do double duty. Test: FV with a standoff boundary condition; a prototype measured with a thermocouple. *new, S*

**TM11. Copper weight chosen at the margin.** Compute ∂T/∂oz over the board's heat sources (1 → 2 oz cut a pad rise by 22% [C]). Weigh it against the fab spacing penalty, space ≈ 47 µm + 1.65·t [C], which can break fine-pitch escape. Surface the decision before placement, with both sides shown. Test: decision quality on 10 boards vs the 1/2/4 oz by-watts rule. *combo, S*

**TM12. Dual-purpose moats.** Generate a U-slot or copper void around voltage references, crystals and cold-junction sensors. It cuts both the heat flux and the board stress reaching the part; TI recommends a U-slot for stress on references [P]. On boards smaller than 2λ a moat is the only effective thermal lever. Size the moat from the FV flux field and the stress field (TM42), not a template. Test: victim ΔT and gradient with and without the moat; a stress proxy from a plate FE. *combo, S*

## B. Electro-thermal coupling and precision

**TM13. Isotherm-aligned orientation.** For parts in precision DC paths (resistors, shunts, matched-pair inputs, Kovar-leaded packages), choose the rotation that minimises |∇T·d| between the two terminals, and report the result in µV using Seebeck coefficients. Examples: Cu–Kovar 35 µV/K gives 31 µV for an 0603 aligned with the gradient 10 mm from a 1 W source, and about zero when rotated 90° [C]. Test: FV gradient times coefficient vs bench offset on a test board. *new, S*

**TM14. Thermal common-centroid.** Borrow the analog-IC habit: place matched pairs, bridge arms and differential front ends symmetrically about the axis of the computed heat field, not about the geometric centre. Score it by the temperature difference between paired terminals. Test: drift in °C and µV of a bridge or instrumentation-amp front end in FV, before and after. *combo, S*

**TM15. Victim drift budgets in their own units.** Convert each sensitive part's allowed drift into a ΔT budget, then check it with THERM-COUPLE. Examples: a 32 kHz crystal at −0.034 ppm/K² (+20 K → −13.6 ppm); reference TC in ppm/K; electrolytic life ×0.5 per +10 K; CJ-sensor error 1 K per K. Reports read "RTC +1.2 s/day" or "C12 life −45%", not "too close". Test: an LLM-reviewer study comparing actionability of unit reports vs distance flags. *sharp, S*

**TM16. Electro-thermal fixed point for power copper.** Iterate R(T) ↔ T(P) on the FV mesh with α = 0.393%/K. Flag copper where αΔT₀ > 0.3, which means strong feedback. ΔT₀ ≥ 254 K has no steady state, which is fusing [C]. This sizes power copper by its actual hottest point rather than a chart. Test: FV fixed point vs IPC-2152 sizing on 1 oz and 2 oz power stages. (Complements OP11.) *sharp, S*

**TM17. Attract and repel thermal relations.** Typed relations in the IR: `thermal_isolate(victim, aggressor, ΔT_max)` and `thermal_couple(sensor, target, R_th_max)`. Protection NTCs, over-temperature sensors and matched transistors need coupling, while references need isolation. Today's rules only push parts apart, and they misplace protection sensors. Test: NTC-to-FET thermal resistance before and after on motor-driver boards. *new, S*

**TM18. Per-net trace thermal network instead of IPC charts.** Model each high-current trace as a line source with line conductance from its fin and any plane beneath. Add neighbouring parts' heat by superposition, then apply the TCR fixed point. A plane 0.2 mm below roughly halves the rise; the line model and IPC-2221 agree within 2× [C]. Keep IPC-2221 as the conservative fallback and log which one bound. Test: FV trace-temperature map vs IR measurement on a current-loaded test coupon. *sharp, S*

**TM19. Hot-copper IR-drop correction.** Report IR drop at the computed copper temperature, not at 20 °C: a pour 40 K above ambient has 16% more resistance [C]. Low-voltage rails (≤ 1.2 V) under heavy load are where this flips a pass to a fail. Test: number of rail budgets that change verdict on a set of FPGA and SoC boards. *sharp, S*

## C. High-voltage insulation

**TM20. Inception-margin critic.** For each HV net pair, solve the 2-D field (boundary elements, about 1 s per corner) and integrate the streamer criterion ∫(E−E₀)²ds along the worst field lines at the true air density. Report a kV margin against peak working plus transient voltage. The criterion captures what E_max misses: E_max at a sharp corner is >10× the uniform field, yet inception drops only 30–43% [C]. Test: compare predicted inception with partial-discharge (PD) measurements on coupon geometries. *new, M*

**TM21. Altitude as air density, with a Paschen-minimum regime switch.** Compute the clearance multiplier as p_ref/p(h). It matched IEC's factors within ~1% up to 20 km [C]. Above ~15–20 km, or in any low-pressure bay, switch the rule pack: every node pair above ~300 V peak needs solid insulation (coating, potting, buried layers), because extra clearance stops helping near the Paschen minimum. Test: Paschen curve vs gap and altitude; chamber hi-pot of coated vs uncoated coupons. *sharp, S*

**TM22. HV corner fillets as a generated feature.** On HV-class copper, fillet every convex corner to r ≥ g/2. That takes the field factor from singular to 1.74 and recovers about 90% of uniform-gap inception [C]. Emit the fillets as arcs, and report the margin gained without ever reducing the legal clearance, because case A already assumes a 30 µm point. Test: field factor before and after on real HV boards; PD inception on filleted vs sharp coupons. *sharp, S*

**TM23. Three-mechanism insulation model.** Give every net pair three separate checks: clearance (gas, straight line, impulse), creepage (tracking, surface geodesic, RMS, X-width bridging per pollution degree) and CAF/through-laminate (hole-wall gap, inner-layer distance, DC bias, humidity). Each check has its own geometry metric and its own legal or physical source. One "spacing" number currently conflates them. Test: a seeded-defect board where each mechanism fails alone. *combo, S*

**TM24. CAF-aware via placement.** For via pairs at different DC potentials (power–ground pin pairs, HV dividers, battery stacks), keep a hole-wall-gap budget. Avoid lining them up along the glass yarn axes (x/y); stagger them diagonally, and count adjacent bias opportunities, as Isola recommends [P]. This is cheap at placement time and expensive after a field failure. Test: count of in-grid opposite-polarity via pairs under 0.5 mm before and after; THB coupons. *sharp, S*

**TM25. Bury the HV.** Route functional HV nets on inner layers, where there is no air, no contamination film and no triple junction. IPC-2221B allows 0.25 mm internal vs 2.5 mm external at 301–500 V [P]. Pair the buried route with stitched guard planes at the layer transitions. Safety isolation still follows the solid-insulation rules of the relevant standard. Test: area saved on an HV measurement board; PD and hi-pot of buried vs surface coupons. *new, S*

**TM26. Coating as a modelled region.** Draw conformal-coat keep-in and keep-out areas as part of the layout: connectors, test points and adjustable parts stay out. Feed coated regions into the creepage solver as PD1 per IEC 60664-3. Never credit solder mask. The coating then becomes a layout variable the optimiser can trade against distance. Test: creepage savings vs the coating area and process cost. *new, S*

**TM27. Voltage-monotone placement for HV chains.** Place divider strings, bleeder chains, multiplier ladders and cell-balancing resistors so that physical position increases monotonically with voltage. That minimises the peak field between non-adjacent nodes and keeps the surface leakage path long where ΔV is large. Folding a chain back on itself puts its highest ΔV across the shortest gap. Test: peak E and the minimum distance-per-volt across chain nodes, before and after. *new, S*

**TM28. Guard rings for HV leakage.** Around high-impedance HV sense nodes, add driven guard traces at the node's potential. They intercept surface leakage, which at 10⁹–10¹² Ω/□ humid surface resistivity is a real error source, and they shape the field. Generate them from the `barrier` and `coupling(leakage)` entities. Test: leakage error vs humidity on a divider coupon with and without the guard. *combo, S*

**TM29. HV test coupon co-design.** Put a coupon on the panel that copies the board's worst HV geometry: the same smallest corner radius, gap, coating and via spacing. Hi-pot or PD-test the coupon instead of the product. Generate it automatically from the TM20 worst case. Test: correlation between coupon PD inception and product PD inception. *new, S*

## D. Fabrication processes

**TM30. Critical-area yield cost in the router.** With a 1/x³ defect-size distribution, short risk ∝ L/s and open risk ∝ L/w [C]. Add D₀·Σ(L·x₀²/s + L·x₀²/w) to the routing cost, so traces spread and widen wherever room exists. Doubling a 0.1 mm gap halves its short risk. This turns "generously wide when unconstrained" into an optimisable term. Test: total critical area and length vs the baseline router at equal completion. *sharp, S*

**TM31. σ-margin map instead of pass/fail DRC.** For every feature, report its margin to the fab limit in process σ: etch for width and space, drill and registration for rings, plating for vias. The critic lists the least-margin 1% and the board's expected escapes. Fabs see a σ-limited board, not a "DRC clean" one. Test: compare predicted marginal features with fab engineering queries on real orders. *combo, S*

**TM32. Directional teardrops by breakout probability.** Junction breakout probability is Q(ring/σ): 3e-5 per hole at a 0.10 mm ring and σ 25 µm, 6e-3 at σ 40 µm [C]. A 0.15 mm teardrop drives it below 1e-9. Add teardrops where expected breakouts per board exceed a budget. Skip them on RF and fast nets, where their capacitance costs more. Test: teardrop count and capacitance added vs the add-everywhere default. *sharp, S*

**TM33. Plating-uniformity field.** Compute a copper-density map per outer layer at the 5–10 mm plating-cell scale, plus a plating index like Eurocircuits' (<0.40 "leads to problems" [P]). Fix low-density regions inside the copper synthesis (with OP18). Thieving must be grounded and stitched, or kept away from signals, so it does not become a floating resonator. Test: plating index and floating-copper count vs post-hoc thieving. *combo, S*

**TM34. Etch-aware cross-sections everywhere.** Use trapezoidal conductors, with undercut t/EF per side, in resistance, impedance and current-density models. On 1 oz with EF 2–4 the rectangle error is +4–21% in R [C]. Request etch compensation explicitly in fab notes where it matters. Test: model vs measured resistance of 0.1 and 0.2 mm coupons. *sharp, S*

**TM35. Impedance tolerance budget by variance share.** Our Monte Carlo puts dielectric thickness at 46–80% of Z0 variance, width at 13–35% and Dk at 6–8% [C]. To tighten impedance, request thickness control and prefer thicker dielectrics, which make lines wider and width error relatively smaller. Narrower width tolerances help less. Feed this into stackup selection and fab-note generation. Test: coupon Z0 spread across stackup choices. *sharp, S*

**TM36. Laminate-theory warp proxy.** Compute per-layer copper fraction, effective CTE and modulus, and the curvature from each layer pair's moment about the midplane. Outer-layer imbalance counts most because of its lever arm. Bilayer estimates give 0.04–0.3% bow against the 0.75% limit [C]. Flag predicted bow above ~0.3% and balance outer layers first. Test: shadow-moiré or feeler-gauge bow vs prediction on a test panel. *sharp, S*

**TM37. Throwing-power-aware via sizing.** Pick the via drill from board thickness and the fab's bath class using TP = 1/cosh(L/2Λ). A 3.2 mm board needs larger drills than a 1.6 mm board at the same reliability [C]. This replaces a fixed aspect-ratio limit and catches thick-board designs that copy 0.2 mm vias. Test: predicted vs measured barrel thickness in coupon cross-sections. *sharp, S*

**TM38. Acid-trap test as morphology.** Flag only copper-free pockets that close under a morphological opening of radius about half the fab's minimum space, weighted by copper thickness, and only on flex or ≥1 oz fine features. Do not flag every acute angle. Evidence that acute angles fail with modern spray etching is forum-level [S], so the rule shrinks to its plausible regime. Test: false-flag rate vs `track_angle`-style checks on 50 boards. *sharp, S*

## E. Assembly and soldering

**TM39. Pad thermal-environment check for tombstoning.** For each 2-terminal part of 0402 or smaller, compute each pad's effective reflow time constant: the plane it is tied to, heavy parts on that plane, shadowed areas. Flag Δτ between the pads above a threshold. In our lumped model a heavy part on the plane caused a 10–14 K, 12–14 s asynchrony; thermal reliefs changed it by under 5% [C]. Fix by re-placement, a symmetric environment or a long neck, not by reliefs. Test: assembler tombstone rates vs the Δτ metric across many boards. *new, M*

**TM40. Reflow shadow and mass map.** Map each heavy part's (shields, inductors, connectors, large BGAs) influence on the surrounding plane temperature during the ramp, from its time constant and copper diffusion length. Keep small passives off plane regions tied to such masses, or give them symmetric ties. This is the reflow analogue of TM2. Test: oven-profile thermocouples placed at predicted cold spots. *new, M*

**TM41. Via-in-pad theft ratio.** For each via inside or touching a pad, compute open-barrel volume ÷ printed solder volume: 1.9 for an 0402 with a 0.2 mm via, 2.2 for a 3×3 mm EP with nine 0.3 mm vias, 0.24 for a BGA microvia [C]. Above ~0.3 require tenting, plugging or filling, and choose the drill to bring the ratio down. This resolves the TH-02 tenting conflict per pad rather than per board. Test: voiding and starved-joint rates vs the ratio, from assembly X-ray. *sharp, S*

**TM42. Relief policy by process, not habit.** Use thermal reliefs where an iron or a wave must beat the plane's drain: THT pins on multilayer planes. Use direct connect for reflow-only SMD power pads and hot-loop pads. Reliefs cost 0.12–0.25 mΩ and 16–47 pH [C]; they barely change reflow balance on small pads. Store the assembly process in the IR so the choice is automatic. Test: hand-solderability and resistance per policy (complements OP9). *sharp, S*

## F. Mechanics

**TM43. Strain-field placement for brittle parts.** Run plate-bending load cases: V-score snap, screw-boss mismatch, ICT fixture, connector insertion. Place and orient MLCCs (long axis parallel to bend lines, per Murata [P]), BGAs and crystals by the computed principal strain against part budgets (about 2,000 µε for standard MLCCs, 5,000 for soft termination). A screw pulling 0.1 mm over 10 mm reaches 9,600 µε [C]. Test: plate FE strain vs strain gauges on a test board. *new, M*

**TM44. Mount points designed against flatness.** Treat standoff height mismatch as a load case. Put brittle parts outside the radius where ε = 6tδ/L² exceeds their budget. Alternatively specify compliant mounts or a thicker board: 0.8 mm boards see half the strain but have a lower f₁. Test: the MLCC failure rate near bosses in field-return data, where available. *sharp, S*

**TM45. Mode-aware placement for vibration.** Compute the first plate modes with part masses: 640 Hz for a bare 100×80×1.6 mm board, 452 Hz with parts doubling its mass [C]. Put heavy and large parts near supports or nodal lines, and add mounting points to push f₁ above the excitation band. Check Steinberg's displacement limit per part. Test: shaker-table resonance vs prediction. *combo, M*

**TM46. Connector load paths.** Route mating and cable forces (10–100 N) into THT anchors, bosses and nearby mounting holes, not SMT pad peel. Place frequently mated connectors within a short lever arm of a mounting point. Score the moment arm and the pad stress. Test: pull and lever tests on SMT-only vs anchored footprints. *sharp, S*

## G. Curves and geometry at the fab

**TM47. Curves where physics pays.** Enable arcs and any-angle copper per net class: HV corners (TM22), flex bends (strain), RF bends, and inner corners of pulsed-current pours (current crowding). Keep 45° elsewhere for editability. Curves have no fab cost [I]; the real costs are router support and hand editing. Test: per-class physics gain vs edit time in a user study. *combo, S*

**TM48. Arc-native output with exact radii.** Emit HV fillets, flex bends and synthesised pours as true arcs (Gerber G02/G03, KiCad PCB_ARC) rather than polylines. Field and strain critics then see the exact radius, and files stay small. Check each fab's CAM import once and record arc support in the fab profile. Test: arc round-trip through KiCad and two fab CAM viewers. (Related to OP53.) *sharp, S*

**TM49. Flex bend geometry from strain.** In bend zones, route traces perpendicular to the bend with arcs and stagger them across layers to avoid I-beaming. Compute conductor strain as ε = t/(2R) from bend radius and position relative to the neutral axis. Keep it under the copper fatigue budget, which is tighter for dynamic flex. Test: predicted strain vs the vendor's bend-radius tables. *sharp, S*

## H. Encoding manufacturing physics

**TM50. Origin-typed constraints.** Tag every constraint with its origin (physics, fab capability, standard or legal, habit) and its enforcement: hard-legal (never relaxed, human sign-off), hard-fab-absolute, soft-yield (σ-margin or critical area), soft-physics-budget, or style. Physics can tighten a legal limit, never relax it. Habit rules move to a style channel. Test: an audit of 300 checklist rows tagged by origin; count the rules that become soft or disappear. *combo, S*

**TM51. Fab process model, not a fab table.** Represent each fab by distributions: etch σ by copper weight, drill and registration σ, plating class (Wagner number), lamination warp tendency, and impedance coupon spread. Fit them from capability pages and coupon data. All yield critics (TM30–TM37) read the same model. Test: predicted vs reported hold and query rates per fab. *new, M*

**TM52. Manufacturing floors on electrical budgets.** Compute the best physically achievable value of each budget under the fab profile, and show it beside the budget, so the optimiser stops pushing past it. Examples: minimum hot-loop inductance from minimum width, space and dielectric; minimum relief inductance under the assembly policy; maximum pour asymmetry under the warp budget. An infeasible budget becomes a requirement conflict to negotiate. Test: how often the LLM negotiates budgets that are infeasible under the fab profile. *new, S*

**TM53. Layout-derived test plan.** Generate hi-pot and PD test levels from `barrier` entities, IR-camera checkpoints and emissivity notes from `heat_path` entities, strain-gauge locations for ICT and depanel, and coupon lists for impedance, CAF and HV. Verification becomes part of the layout output. Test: coverage of a human test plan on 5 products. *new, S*

**TM54. Calibrate with the IR camera.** Fit h, contact resistances and emissivity in the FV model to one emissivity-corrected IR image of the first prototype. Store the fitted priors per enclosure and product family, so the next board starts calibrated. Test: prediction error on a second board after calibration on the first. *new, M*

## Top five to try first

1. **TM2 + TM3:** image-lattice kernel with FV correction. Exact thermal placement scoring is cheap and validated within 2% [C].
2. **TM20 + TM22:** inception-margin critic and HV corner fillets. They turn "round HV copper" into a margin in kV.
3. **TM39:** pad thermal-environment check for tombstoning. It challenges the relief habit with a measurable metric.
4. **TM30 + TM31:** critical-area and σ-margin yield costs. They make "don't push the fab" optimisable.
5. **TM21:** altitude as air density with the Paschen-minimum regime switch. Simple, exact and safety-relevant.
