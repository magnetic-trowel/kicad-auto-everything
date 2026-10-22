# Physics-first ideas: power copper, commutation and PDN (PW)

Workstream 4 of the physics-first effort. Detail and evidence:
[power-copper](../../topics/physics/power-copper.md) and
[pdn-and-commutation](../../topics/physics/pdn-and-commutation.md). These ideas build on the
budget ledger and dimensioned constraints ([I1, I2](../original/intent-and-why.md)), the hot-loop
micro-placer and decap assignment ([N7, N8](../original/priority-agents-and-negotiation.md)), and
entity names in [physics-ir](../../topics/physics/physics-ir.md). Numbers tagged [C] come from
[pw_cells.py](../../../tools/research/physics/pw_cells.py),
[pw_sheet.py](../../../tools/research/physics/pw_sheet.py),
[pw_peec.py](../../../tools/research/physics/pw_peec.py),
[pw_xsec.py](../../../tools/research/physics/pw_xsec.py) and
[pw_eddy.py](../../../tools/research/physics/pw_eddy.py).

Tags: *new* (not found in prior PCB work), *combo* (known parts, new combination for PCB),
*sharp* (sharpens an existing rule or idea). Effort: S (days), M (weeks), L (months).

## A. Objectives from waveforms

**PW1. Waveform-derived copper roles.** — *new, M.*
- **Mechanism:** run the schematic once in SPICE (ngspice, an operating point plus one switching period), or use a topology template. Record dv/dt per node and di/dt, I_rms and I_dc per branch. Map each copper piece to weights: a for L, b for C (split into local, world and victim), g for R, plus victim sensitivity.
- **Why it beats the rule:** this replaces net-name classes (PWR_HOT, SW, SENSITIVE) with numbers. It catches the cases names miss: the inductor branch's di/dt is set by L (0.011 A/ns), not by the edges (5.5 A/ns) [C].
- **Test:** on 30 open converter boards, compare role labels against expert labels. Then check whether the weights rank the copper the way the datasheet layout guide orders it.

**PW2. Width from the a·L + b·C + g·R optimum.** — *sharp, S.*
- **Mechanism:** for each piece over a plane, w* = sqrt((a·μ0·h + g·ρ/t)/(b·ε/h)). For a piece in both a fast node and a fast loop, Z0* = V/I of the cell.
- **Why:** this replaces "make power wide, keep SW small". Low-voltage SW → L copper comes out about 60 mm wide on loss alone; a 400 V PFC drain comes out 0.8–3 mm [C].
- **Test:** compare w* against eval-board widths on 20 TI/ADI/EPC EVMs. Explain each disagreement with an EMI or thermal term.

**PW3. Zero-length SW segment inside the commutation loop.** — *sharp, S.*
- **Mechanism:** a hard constraint that the SW-node copper between the HS source and the LS drain is shorter than ε. Abut the pads, or use the integrated half-bridge pinout.
- **Why:** that segment is the only copper that is both a fast-dv/dt node and a fast-di/dt branch. L·C = (l/v)², so only length helps both.
- **Test:** PEEC L and SW-node C for placements that do and do not abut the FET pads.

**PW4. "Capacitance to whom" ledger for fast nodes.** — *new, M.*
- **Mechanism:** split each fast node's capacitance three ways:
  - to its local return (cheap, often helpful);
  - to the outside world (an EMI budget item, through the [fields-emi-budget](../../topics/physics/fields-emi-budget.md) chain);
  - to victims (a crosstalk budget item).

  Compute them with a 2-D/3-D capacitance extraction.
- **Why:** this replaces "SW area ≤ k × pads". A 100 mm² SW pad 10 mm from a cabled conductor already reaches 35–45 dBµV/m on our upper-bound model, while the same pad over its own plane is harmless [C, I].
- **Test:** rank EMI scan results on 5 converter boards with the ledger vs the area rule.

**PW5. Heat through the dielectric, priced in picofarads.** — *new, S.*
- **Mechanism:** a SW pad sheds heat into the plane beneath at G/C = k/ε (7.9×10⁹ (W/K)/F for FR-4, about 280× better for AlN) [C]. Solve for the area and dielectric that meet a ΔT budget and a ½CV²f budget together.
- **Why:** this replaces "never heatsink via SW copper" with a trade. At 12 V the C costs 1.4 mW/cm²; at 400 V it costs 0.3 W/cm² [C].
- **Test:** thermal FV ([thermal-physics](../../topics/physics/thermal-physics.md)) plus switching-loss bench data on a 48 V and a 400 V half-bridge.

**PW6. Length invariants as the first placement metric.** — *sharp, S.*
- **Mechanism:** L·C = (l/v)² and R·A = R_s·l² for a strip. During coarse placement, score power pieces by length weighted by √(a·b) and g. Optimise widths after placement.
- **Why:** widths can trade one parasitic for another but cannot beat length. So placement should minimise length, and width optimisation comes later.
- **Test:** compare the correlation of placement-stage length scores with post-route physics scores against loop-area scores.

**PW7. Edge rate as a layout variable.** — *combo, M.*
- **Mechanism:** when the geometry floor (minimum L) still breaks the overshoot or EMI budget, let the solver choose the gate resistor or bootstrap resistor. It trades efficiency (∝ t_edge) against overshoot (L·di/dt) and spectrum. The LLM proposes, and the ledger checks.
- **Why:** the rule sources treat edge rate as a separate EMI knob ([gate-drive-bootstrap](../../topics/rules/power/gate-drive-bootstrap.md)). Treating it with layout finds cheaper joint optima.
- **Test:** SPICE plus PEEC on 3 cells; compare the Pareto fronts with and without edge rate as a variable.

## B. Trace, pour and plane

**PW8. Squares as the unit of power copper.** — *combo, S.*
- **Mechanism:** store N□ per port pair in the physics IR. One Laplace solve on the copper mask gives R = R_s·N□ and, where the return copy sits at depth d, L = μ0·d·N□.
- **Why:** this unifies IR drop, plane spreading inductance and overlapped-loop inductance in one number per pair. The LLM can reason about "squares" without coordinates.
- **Test:** compare N□-derived R and L against padne and PEEC on 10 boards, within 10%.

**PW9. Feed-first pour design.** — *sharp, S.*
- **Mechanism:**
  - Report the entry-constriction share, the loss within 3 mm of each pad (31% in our test pour [C]).
  - Widen entries first: more pads, via rows along the edge, parallel parts.
  - Widen the body only when that share is low.
- **Why:** pours wider than their feeds pay a logarithmic spreading toll. R·Area is lowest at about feed width [C].
- **Test:** on 20 high-current nets, compare R reduction per added mm² for entry-first vs body-first edits.

**PW10. Field-guided pour trimming for routing space.** — *combo, S.*
- **Mechanism:** compute |J| on the candidate pour and release copper whose removal costs under x% of the IR budget. Then remove islands and legalise to minimum width. Optimised shapes come from OP2 ([optimization](optimization.md)).
- **Why:** in our test pour, the last 28% of the area bought only 9% of R [C], so that area is cheap routing space.
- **Test:** route completion on 2-layer boards, with and without trimmed pours, at equal IR margin.

**PW11. Dead-copper classifier.** — *new, S.*
- **Mechanism:** label every zero-current copper region as one of:
  - heat spreader;
  - multi-tied shield;
  - fab-balance copper;
  - single-tied stub on a fast node (a capacitor or antenna);
  - floating island.

  The label comes from J, the node's dv/dt, tie count and the thermal flux. Keep, stitch or delete by label.
- **Why:** "remove copper islands" and "pour everything" are both wrong half the time.
- **Test:** expert agreement on 200 labelled regions from open boards.

**PW12. Via-field neck detector.** — *sharp, S.*
- **Mechanism:** multiply the sheet resistance in BGA and connector fields by the antipad factor: 1.8× at D/p 0.6, 3.1× at 0.8, 5.2× at 0.9 [C]. Flag D/p > 0.8 on a rail path. Suggest smaller antipads, a power layer elsewhere, or a reroute of the rail around the field.
- **Why:** a plane that looks solid in a screenshot can have a 4× neck.
- **Test:** compare the detector's predicted IR drop with padne on 5 BGA boards.

**PW13. Peaceman sub-cell vias for board-scale solves.** — *new, S.*
- **Mechanism:** model each via as one grid cell plus (1/2π)·ln(0.198·Δx/r) squares, the well index from reservoir simulation. A 1 mm grid then handles 0.3 mm vias.
- **Why:** this cuts cell count about 100× against resolving vias, so whole-board IR and spreading maps run inside the placement loop.
- **Test:** our spread experiment matched the analytic log within 2% [C]. Repeat on irregular boards against a fine-grid reference.

**PW14. Reverse-return feeds for paralleled parts.** — *new, S.*
- **Mechanism:** for paralleled FETs, MLCCs, LED strings or shunts on a bus, feed at one end and exit at the other (the Tichelmann reverse-return principle from hydronic heating). Better still, use a symmetric tree. Check current sharing with a ladder or Laplace solve.
- **Why:** four 2 mΩ FETs on 1 oz buses share 9.8:1 with a same-end feed and 1.8:1 with an opposite-end feed [C].
- **Test:** sharing measurements, or a padne/PEEC check, on 3 multi-FET boards.

**PW15. Trace-to-pour conversion trigger.** — *sharp, S.*
- **Mechanism:** convert a trace to a pour when any of these holds:
  - the width required by the IR, ΔT or L budget exceeds the channel;
  - the piece is a quiet node in a commutation loop;
  - it must spread heat.

  Keep narrow traces for fast low-current nodes, victims and deliberate impedances.
- **Why:** this turns "pours are better" into a per-piece rule with a reason attached.
- **Test:** compare conversions proposed on open boards with expert judgement.

**PW16. Streamline-routed power traces.** — *new, M.*
- **Mechanism:** solve the ideal pour, take its stream function, and route a few traces along chosen streamlines. Each trace's width is set by the flux it carries.
- **Why:** a set of streamline traces approximates the pour's resistance with less copper and leaves gaps for signals. This is the coil-design idea from [cross-domain-lessons](../../topics/physics/cross-domain-lessons.md), applied to pours.
- **Test:** compare R and freed area against the full pour and against OP2 shapes.

**PW17. Regional copper weight and inlays.** — *combo, M.*
- **Mechanism:** choose the copper weight per region from R·A = R_s·l² and the thermal budget. Options include selective heavy copper, embedded coins and press-fit busbars ([high-current](../../topics/rules/power/high-current.md)). Price the cost and the fab spacing penalty.
- **Why:** with a fixed length, the only way to lower R without more area is more thickness.
- **Test:** cost and ΔT trade on 3 motor-drive boards.

## C. Corners, curves and pulses

**PW18. Curves only on pulse paths.** — *sharp, S.*
- **Mechanism:** compute the adiabatic hot-spot factor, ⟨J²⟩ over √(α·t_pulse), for inside corners on nets carrying surge, ESD, inrush, short-circuit or fuse currents. Fillet or arc only those.
- **Why:** steady-state corner hot spots are nil (49.2 vs 49.3 K) [C]. At 10–100 µs pulses a sharp inside corner sees 3.7–7.7× J² [C].
- **Test:** a transient 3-D check, and a fuse-trace bench test of sharp vs filleted necks.

**PW19. Designed PCB fuse necks.** — *new, M.*
- **Mechanism:** size a deliberate neck from I²t (Onderdonk-type adiabatic heating) with filleted transitions, so the neck, not an accidental corner, is the weakest point. Keep it away from other copper so it fails safely.
- **Why:** this gives defined fault behaviour at no BOM cost, where a 3 A trace would otherwise fail at a random corner.
- **Test:** pulse tests on 10 coupons per geometry.

## D. AC behaviour and returns

**PW20. Stacked power pairs as a router primitive.** — *new, M.*
- **Mechanism:** route the go and return of each high-di/dt branch as a broadside pair on adjacent layers, analogous to a diff pair.
- **Why:** 0.07 nH/mm stacked against 0.55–0.66 nH/mm side by side [C]. The proximity effect moves the current to the facing surfaces, so the field stays in the gap.
- **Test:** PEEC loop L and near-field scans on a buck routed both ways.

**PW21. Frequency-split return design.** — *sharp, S.*
- **Mechanism:** below f_c = R_s/(2π·μ0·h), about 0.1–0.5 MHz, return current spreads by resistance; above it, it follows inductance. Design the DC path for R and the HF path for L separately. They can differ, and the HF one must be continuous.
- **Why:** in our solve, L' under a trace dropped from 0.39 to 0.068 nH/mm between 1 kHz and 1 MHz [C].
- **Test:** IR drop and PEEC loop L on boards with a slotted DC path but a continuous HF path.

**PW22. Local eddy shields on 2-layer boards.** — *new, S.*
- **Mechanism:** pour an isolated or single-tied copper patch under a lateral hot loop when a full ground plane is impossible.
- **Why:** a floating plane 0.1 mm below a side-by-side pair cut L' from 0.66 to 0.13 nH/mm at ≥1 MHz, through mirror currents alone, at +12% R [C]. MPS uses a related "noisy local PGND" island.
- **Test:** an H-field probe and PEEC on a 2-layer buck with and without the patch.

**PW23. AC-resistance budgeting only where it matters.** — *sharp, S.*
- **Mechanism:** compute R_ac only for planar-magnetics windings and for paths carrying more than ~5 A at >5 MHz content. Skip it elsewhere and say so in the report.
- **Why:** PCB power copper is ≤1.6× DC below 1 MHz [C]. Modelling it everywhere spends compute and attention on nothing.
- **Test:** the share of boards whose loss estimate changes by more than 1% when AC resistance is included.

**PW24. Plane as magnetic shield credit.** — *new, S.*
- **Mechanism:** above f_c = 1/(π·μ0·σ·t·a), 12–125 kHz for 35 µm [C], a solid plane mirrors a loop of size a. Credit that reduction to the near-field term of the EMI ledger.
- **Why:** this corrects the myth that a plane thinner than a skin depth does not shield.
- **Test:** near-field scans over a loop with 18, 35 and 70 µm planes, 50 kHz–5 MHz.

## E. Commutation cells

**PW25. Height × squares instead of loop area.** — *sharp, S.*
- **Mechanism:** score hot loops by Σ μ0·h_i·dl/w_i (the field volume) whenever a plane lies within about half the go/return gap. Use loop area only without a close plane.
- **Why:** over a plane 0.1 mm away, a 20× change in gap moved L 1.5× while plane height moved it 4.4× [C]. Area tiers mis-rank layouts.
- **Test:** rank correlation of each metric with PEEC on 200 random hot-loop placements.

**PW26. Commutation-cell geometry search inside N7.** — *combo, M.*
- **Mechanism:** N7 enumerates lateral, vertical and internal-vertical variants, layer pairs, via rows and terminal widths. It scores each with image-plane PEEC (milliseconds per evaluation).
- **Why:** internal-vertical beat lateral 3.5× on the same footprint, matching EPC's ~65% [C]. The choice depends on the stackup, so it should be searched, not templated.
- **Test:** compare N7-chosen cells on 30 EVM converters against EVM nH and overshoot.

**PW27. Terminal-row widening and symmetric split cells.** — *combo, S.*
- **Mechanism:** use a template that puts several CIN_HF across the loop (width ≈ terminal span + loop length) and mirrors the cell into two opposite-orientation half-loops.
- **Why:**
  - Plate widening saturates at W ≈ a + l [C], so the terminals must widen instead.
  - Split loops halve the current per loop and cancel the far field (MPS: −6 dB) [P].
- **Test:** PEEC and near-field on single vs split cells.

**PW28. Stackup co-design from ∂L/∂h.** — *sharp, S.*
- **Mechanism:** report ∂L_loop/∂h for the L1–L2 dielectric. Bid it in the stackup negotiation against SI's impedance needs.
- **Why:** h is the strongest knob: L ∝ h for vertical loops, and 0.93 → 4.1 nH from 0.1 to 1.5 mm for lateral loops [C]. Yet the stackup is usually fixed before power is considered.
- **Test:** nH saved per µm against cost on 10 four-layer boards.

**PW29. Snubber and C_oss-aware BOM from extracted L.** — *new, S.*
- **Mechanism:** after the loop is placed, compute f_ring, the overshoot I·√(L/C_oss) and an RC snubber (R ≈ √(L/C_oss), C ≈ 3–4·C_oss). Write them back to the schematic as constraints, with the snubber placed inside the same cell.
- **Why:** this closes the layout-to-circuit loop the rule sources leave open (SLYT614 gives no values).
- **Test:** SPICE plus bench ringing on 3 boards.

**PW30. Loop nH in watts.** — *combo, S.*
- **Mechanism:** express loop L as loss, ½·L·I²·f per edge, and as derating (overshoot / V_DS,max). The ledger then trades nH against mΩ and °C in one currency.
- **Why:** EPC's >4% efficiency step is about twice ½·ΔL·I²·f, so the first-order model is right in order of magnitude [C, I].
- **Test:** predicted vs measured efficiency deltas on EPC- and TI-published layout comparisons.

**PW31. Ring-frequency steering.** — *new, M.*
- **Mechanism:** when L cannot drop further, choose L and the snubber so that f_ring = 1/(2π·√(L·C_oss)) avoids protected bands (FM, GNSS sub-harmonics, the cable's first resonance) and lands where the board's antennas are inefficient.
- **Why:** f_ring of 90–290 MHz sits in the radiated-emission band [C]. Its position is a design variable.
- **Test:** an EMI scan of two geometries with equal overshoot and different f_ring.

## F. Vias and decoupling

**PW32. Via clusters by perimeter, not count.** — *sharp, S.*
- **Mechanism:** for HF paths (decaps, hot-loop transitions, plane stitching at power entries), place vias around a perimeter. Count vias separately for DC ampacity, since barrels share DC as 1/N.
- **Why:** in a plane pair, 4 vias at 2 mm pitch match 16 at 0.6 mm (0.51× vs 0.50× of one via; ideal would be 0.25× and 0.06×) [C].
- **Test:** compare PEEC and Laplace with N8 site choices on 20 MCU boards.

**PW33. Alternating decap orientation as an N8 constraint.** — *combo, S.*
- **Mechanism:** in rows of decaps, alternate power/ground pin order. Weight the rule by plane depth.
- **Why:** alternating was 16% lower than same-orientation at 0.1 mm and 39% lower at 1.0 mm [C], which quantifies Archambeault's rule.
- **Test:** a PDN screener sweep plus VNA on a 2-layer and a 6-layer coupon.

**PW34. Side-via decap footprints.** — *new, S.*
- **Mechanism:** generate 0402/0603 footprint variants with two vias beside each pad. Rank variants by PEEC.
- **Why:** side vias matched via-in-pad (0.56 vs 0.57 nH at h = 0.3 mm) and beat it on deep planes (0.88 vs 1.09 nH), with no plugging cost [C].
- **Test:** VNA on coupons with three via styles.

**PW35. PEEC-computed site inductance for N8.** — *combo, S.*
- **Mechanism:** replace N8's lookup-table mounting L with a millisecond PEEC evaluation per candidate site (pads, traces, vias, plane depth, neighbours). Add the Laplace spreading L to the IC.
- **Why:** the table cannot see neighbours or orientation, and those changed L by 16–39% [C].
- **Test:** rank agreement with Axotron-style measurements.

**PW36. Opposite-current via pairing in hot loops.** — *sharp, S.*
- **Mechanism:** when the hot loop must change layer, place each supply via next to a return via carrying opposite current. That gives negative mutual inductance.
- **Why:** this is the via form of PW20. Coupled opposite currents cancel, while same-direction vias add mutual L (0.69× instead of 0.5× for two).
- **Test:** PEEC and a bench L measurement on paired vs grouped via layouts.

## G. PDN and power islands

**PW37. Spreading-L heat map for decap placement.** — *combo, S.*
- **Mechanism:** run one Laplace solve per rail with the IC pins as sink. Each candidate site then gets L_spread(x) = μ0·d·N□(x), a map the placer and N8 can read.
- **Why:** this matched Archambeault's 1-inch anchor (157 vs 154 pH) [C], and it shows where location matters (thin, narrow or perforated planes) and where it does not.
- **Test:** PDN screener Z(f) with map-guided vs distance-guided placement.

**PW38. Islands shaped by both J and spreading L.** — *new, M.*
- **Mechanism:** optimise a power island's outline for IR drop at DC and for spreading L at the decap band at the same time. The two fields differ: DC follows the loads, HF follows the IC-to-decap paths.
- **Why:** a by-eye island, or a DC-only optimised one, can leave a narrow neck between the decaps and the IC.
- **Test:** a two-objective OP2 run on 5 FPGA rails.

**PW39. Adjoint IR-drop sensitivities per neck.** — *combo, S.*
- **Mechanism:** compute ∂V_load/∂(width) along the rail tree with one adjoint solve. Rank necks by millivolts per mm² so the LLM widens the right one first.
- **Why:** this replaces "widen the power trace" with a ranked list; the adjoint machinery is in OP ([optimization](optimization.md)).
- **Test:** IR drop reduction per mm² vs uniform widening.

**PW40. Plane-pair capacitance and cavity as budget items.** — *sharp, S.*
- **Mechanism:** count 38 pF/cm² at 0.1 mm into the PDN screener and compute the cavity modes per island. Prefer thin power/ground cores under power-dense regions.
- **Why:** the rule ("tight plane pair") then becomes an impedance number at the relevant frequency.
- **Test:** PDN screener vs a VNA on one coupon per core thickness.

## H. Sensing, gates and magnetics

**PW41. Kelvin L_err extraction and filter matching.** — *new, S.*
- **Mechanism:** compute the inductive error of each shunt with its actual sense route: V = φ(s₁) − φ(s₀) − jω∫A·dl. Emit τ_RC = L_err/R_shunt as a BOM constraint, and flag routes where L_err·di/dt exceeds the signal budget.
- **Why:** a 2512 over a plane carried 0.55–0.87 nH, which puts the corner at 180–290 kHz with 1 mΩ [C]. The usual "Kelvin taps" rule says nothing about this.
- **Test:** compare scope traces of the sense voltage at a switching edge with and without the matched RC.

**PW42. Sense return under the element.** — *sharp, S.*
- **Mechanism:** route one sense trace back beneath the resistive element, or choose a 4-terminal part. Offer footprint variants.
- **Why:** this cut L_err by 37% against separate taps [C].
- **Test:** the same bench as PW41.

**PW43. Aggressor–victim M ledger.** — *combo, S.*
- **Mechanism:** compute M between every high-di/dt loop and every sensitive loop (FB, sense, gate return, ADC reference) with PEEC. Charge V = M·di/dt to the victim's mV budget. Do the same for C·dv/dt.
- **Why:** this replaces fixed 1–2 mm keep-outs. Over a plane, a 30 mm² sense loop picked up 17 mV at 3 mm but 0.43 mV at 10 mm, and a 1 mm² loop 1.5 mV at 3 mm [C].
- **Test:** ledger predictions against measured FB/sense noise on 5 boards.

**PW44. Per-FET gate-loop budget.** — *sharp, S.*
- **Mechanism:** compute L_G,max = ¼·R_G²·C_GS from datasheet values, then the maximum driver distance for a stacked or split gate pair.
- **Why:** GaN-like parts allow 0.34 nH, so a stacked pair can be only ~1–2 mm long. Si parts allow 18.8 nH [C]. One "short and wide" rule fits neither.
- **Test:** SPICE plus bench gate ringing at 3 distances.

**PW45. Common-source-inductance detector.** — *sharp, S.*
- **Mechanism:** find copper shared between the gate return and the power source path. Compute V = L_cs·di/dt and force a Kelvin source net tie.
- **Why:** 0.2 nH at 5 A/ns steals 1 V of gate drive [C]. It is invisible in DRC.
- **Test:** inject the fault on 10 boards and check the detector catches it.

**PW46. Inductor shield-class selector for copper under the coil.** — *sharp, S.*
- **Mechanism:** inputs are shield class, ripple, f_sw and plane depth. Dodd–Deeds gives ΔL and P_eddy. The default keeps the plane. Consider a cut-out (or slot pattern) only for open drum cores within ~0.5 mm and without EMI limits.
- **Why:** this resolves the Rohm vs TI vs MPS conflict quantitatively:
  - shielded parts: about −0.2% L and under 1 mW;
  - open drum cores: up to −6% and ~24 mW [C, I].
- **Test:** LCR measurement with and without the plane for 3 inductor families, which also calibrates f_ext.

**PW47. Inductor orientation from dipole coupling.** — *combo, M.*
- **Mechanism:** model each inductor's stray field as a dipole (or the Dodd–Deeds loop) and choose its rotation and its start-of-winding pin. Minimise coupling to victims and to cable entry points, alongside the dot-on-SW E-field rule.
- **Why:** today orientation is a single measured 8 dB anecdote ([buck](../../topics/rules/power/buck.md)).
- **Test:** near-field scans while rotating the part.

## I. Thermal coupling and calibration

**PW48. IPC-2152 replaced by a two-term trace model.** — *sharp, S.*
- **Mechanism:** trace ΔT = q'/(k·w/h) (local, through the dielectric) + the plane temperature from the board model. Flag only traces whose local term exceeds x K.
- **Why:** a 1 mm trace 0.1 mm from a plane couples 3 W/(m·K) into it against 0.02 W/(m·K) by convection [C]. The board, not the trace, sets the temperature ([thermal-physics](../../topics/physics/thermal-physics.md)).
- **Test:** FV and IR camera on IPC-2152-style coupons.

**PW49. Electro-thermal pour solve.** — *combo, S.*
- **Mechanism:** iterate the Laplace current solve and the thermal solve with ρ(T) = ρ₀·(1 + 0.0039·ΔT). Necks heat, raise their resistance and heat more.
- **Why:** at >20 K rise the cold-copper IR estimate is optimistic by about 8% or more, and the hot spot moves [I].
- **Test:** compare with a padne-plus-thermal reference on 3 high-current boards.

**PW50. Power-copper calibration set.** — *new, M.*
- **Mechanism:** a public set of 20 converter cells and decap fields, with published nH, mΩ or overshoot (EPC, TI, ADI EVMs, plus our own coupons), each turned into a test that the PEEC, Laplace and Dodd–Deeds models must reproduce within a stated tolerance before their numbers feed budgets.
- **Why:** the [C] numbers here agree with the anchors to within 1.3–2× (EPC 65% vs 71%, Axotron, Archambeault 1 inch), and two anchors are not reproduced (AN-139's flat curve, Archambeault 10 inch). This set gives each model a trust radius ([V4](../original/verification.md)).
- **Test:** the set itself, run in CI.

**PW51. Interdigitated go/return fingers for very low-L buses.** — *new, M.*
- **Mechanism:** split a wide bus into N interleaved go and return fingers on one layer, or alternating on two. The loop L drops roughly as 1/N for the same area, like laminated busbars and interdigitated capacitors.
- **Why:** this is useful where no adjacent-layer return exists (2-layer boards, flex) and the stacked pair of PW20 is impossible.
- **Test:** PEEC sweep of N; VNA on a coupon.

**PW52. "Physics diff" for power edits.** — *new, S.*
- **Mechanism:** every proposed edit to power copper (move, widen, add via, trim) returns a delta in nH, mΩ, mV pickup and K. The numbers come from the incremental Laplace and PEEC solvers, and the LLM sees them before accepting the edit.
- **Why:** this gives the LLM physics feedback in its own words ("this via saves 14 pH and costs 0.3 mm of channel"), not a DRC pass or fail.
- **Test:** compare LLM edit acceptance quality with and without the diff on 10 repair tasks.
