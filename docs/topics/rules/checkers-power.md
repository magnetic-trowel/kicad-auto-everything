# Power/RF/analog checkers: role detectors, loop-inductance estimator, creepage engine, thermal/PDN screening, criticality map

**TL;DR**
- **Highest-value automation:** recognise circuit roles (CIN_HF, SW, L, COUT, FB divider, BOOT, RSENSE, crystal, RF match, ADC AGND/DGND) from netlist + pin names + datasheet text, then instantiate per-topology templates and typed constraints.
- **Division of labour:** the LLM extracts, classifies and templates. Deterministic code over the KiCad board model does every check. A human confirms safety classes and the criticality map.
- **First-class metrics:**
  - a loop-inductance estimator, which makes "as close as possible" numeric;
  - a safety-spacing engine (lookup + surface-geodesic creepage + 3-D clearance);
  - thermal and PDN screeners cheap enough for the placement loop.
- **Constraints DRC cannot express** emit KiCad-style marker reports, which the LLM reads to repair the board iteratively.
- **Gap and opportunity:** no published system extracts hot loops from netlists, and no open-source KiCad plugin implements these backends.

## Key facts

**Role detectors** (RPA §20) [I]:

| Circuit | Netlist pattern | Roles → constraints |
|---|---|---|
| Switching converter | IC with {SW, LX, PH, SW1/2, LX1..} + {VIN, PVIN, VCC} + {PGND, GND, EP}; or two FETs sharing a node with an inductor. Confirm with datasheet keywords (step-down, buck, boost, inverting, flyback) | Topology from L: SW→regulated output + FB divider = **buck**; input rail→SW with rectifier to output = **boost**; SW→GND with negative output = **inverting**; coupled windings + primary FET = **flyback/forward**; two SW nodes with one L = **4-switch**. Roles: CIN_HF = smallest package between input and PGND (ties: lowest value); CIN_BULK = the rest; COUT; FB_TOP/BOT; C_BOOT (BOOT/BST/CB↔SW); SNUB (series RC SW→GND); RSENSE (≤100 mΩ to CS±/SENSE); AGND/PGND by name → [power/hot-loops.md](power/hot-loops.md) |
| Offline flyback | Transformer, primary on the HV bulk net + drain on the other end; windings classified pri/sec/bias | Clamp; Y-cap (pins on primary and secondary classes); spark-gap footprints; post-filter L → FLY-01…06, ISO-01…07 ([power/flyback-offline.md](power/flyback-offline.md)) |
| H-bridge / 3-phase | N-FET pairs on an SH node to a connector; GHx/SHx/GLx/SLx/SPx/SNx/VDRAIN/VCP | Per-phase bypass, shunt, CSA caps, bulk → MOT-01…07 |
| Charger | PMID/VBUS/SW/BAT/REGN/BTST/ILIM/TS | Ordered `placement_priority` + CHG-02 |
| BMS | VC0…VCn, SRP/SRN, BAT, PACK, CHG/DSG | Cell RCs at the IC; Kelvin pack shunt; FET pours; voltage classes from cell index × V |
| LED driver | CSP/CSN | Sense pair + filter at the IC; SW keep-out under the IC |
| Thermocouple | TC connector or TC± nets + NTC/RTD/temperature IC | CJ co-location + symmetric routing |
| Bridge | Excitation/sense/signal nets of a 4/6-wire connector | Ratiometric REF + matched routing |
| TIA | Op-amp with R_F ≥ ~100 kΩ + photodiode on IN− | Regime classification (SEN-04) |
| Class-D | OUT±/SW/BST/PVDD/VBST/Vsense | AUD-01…03 |
| Crystal | OSC_IN/XTAL1/XIN + OSC_OUT pins + crystal + caps to GND | See [crystals-clocks.md](crystals-clocks.md) |
| LDO | IN/OUT/GND, no SW | [power/ldo.md](power/ldo.md) |

**Constraint schema example** (RPA §20B):
```yaml
- {id: U3.hotloop, type: loop_area, members: [C12.pad1, U3.PVIN, U3.PGND, C12.pad2],
   same_layer: true, severity: S1, source: "SLYT614 step 1"}   # hard part: CIN on the IC layer (integrated converter)
- {id: U3.hotloop_score, type: loop_area, members: same, objective: min_L_est, max_mm2: 15,
   severity: S2, source: "SNVA803; EPC"}   # vias, area, next-layer plane scored via L_est; vertical loops allowed; max_mm2 unsourced
- {id: U3.l_adjacent, type: proximity, a: L2.pad_dot, b: U3.SW, max_gap_mm: 2.0,
   require_net_match: {L2.pad_dot: SW}, severity: S2}
- {id: U3.fb_kelvin, type: connect_at, net: VOUT_SENSE, at_pad: C20.pad1,
   forbid_shared_copper_with: [VOUT_POWER_PATH], severity: S1}
- {id: U3.fb_keepout, type: keepout, victim_netclass: SENSITIVE, aggressors: [net:SW, courtyard:L2],
   clearance_mm: 1.0, layers: all, severity: S2}   # 1 mm is an [I] heuristic (VR PWR-05): warning, not DRC
- {id: U3.L2_plane, type: solid_reference, region: "hull(U3.hotloop.members) + 1mm", layer: In1.Cu, net: GND, severity: S2}
- {id: U3.ep_vias, type: via_array, region: U3.EP, drill_mm: 0.3, pitch_mm: [1.0, 1.2], fill: plugged_or_tented, severity: S2}
```
Full rule-pack contract: [datasheet-to-constraints.md](datasheet-to-constraints.md).

**Loop-inductance estimator** [I]:
- **Area:** shoelace area of ordered pad centroids, plus a routed-path-aware variant (through pads and tracks, area += via count × a board-thickness term).
- **Inductance:** L ≈ µ0·h·length/width over a plane, or rank ordering when uncalibrated.
- **Inputs:** pad gap, trace W/L, via count and length to the reference plane, plane depth (deeper = higher L, per Archambeault). Via L ≈ (h/5)(ln(4h/d)+1) nH (Rohm/Johnson).
- **Calibration anchors:**
  - Axotron 0402: 0.44–0.63 nH top;
  - Archambeault: 0.9 → 3.2 nH at 10 → 100 mil depth;
  - AN-139 table (10 × 10 cm test loop at 27 MHz: plane-distance trend only, not absolute nH);
  - SNVA803: 20 mm² >1 nH, 2 mm² <0.5 nH;
  - EPC: 0.4–2.9 nH.
- **Budgets to judge against:** SLAA896 per-pin pH totals (750–1150 pH; pin-to-pin 250–650 pH) ([power/class-d-audio.md](power/class-d-audio.md)); EPC overshoot/efficiency data.
- **Outputs:** nH; overshoot = L·di/dt (warn >0.2 × V_DS,max); efficiency impact.

**Safety-spacing engine** [I] ([isolation-creepage.md](isolation-creepage.md)):
- Lookup: (V_RMS, V_impulse from OVC, PD, MG/CTI, altitude, grade) → (creepage, clearance).
- Surface creepage: KiCad 10.0's native `creepage` constraint where it suffices ([drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)); otherwise a 2-D surface-geodesic check, routed around slots ≥ the PD minimum width only.
- 3-D straight-line clearance across slots and bodies.
- All-layer barrier keep-out check.
- The LLM classifies nets and grades; a human confirms.

**Thermal screener** ([thermal.md](thermal.md)): power per part → zone-graph flood-fill spreading → network (θ_JC/Ψ_JB + 261 °C/W ÷ N + lateral + convection) → superposition → T_J and sensitive-part ΔT.

**PDN screener** ([decoupling-pdn.md](decoupling-pdn.md)): per rail, Z_t + lumped RLC with derated MLCCs and geometric mounting L → peaks ≤1.57× / 3× Z_t (S2 warnings), Q, rogue-wave warning, cavity modes vs clocks.

**Deterministic checks** (pcbnew Python / IPC API) [I]:
- **Adjacency and proximity:** pad-edge distances; same-side test; via count on the shortest copper path (graph search over tracks and vias).
- **Reference-plane integrity:** rasterise zones on the adjacent layer under a region or along each critical track; flag voids, slots, foreign nets, split crossings (Ott), except voids the part's datasheet mandates (U.FL pad, RF matching network).
- **Coupling:** parallel-run length and minimum distance, victim vs aggressor, same layer and ±1 layer.
- **Keep-out compliance:** copper on all layers vs antenna/module/inductor/barrier polygons.
- **Via fence and stitching:** maximum GND-via gap along the RF centreline within an offset; pour maximum gap ≤ λ/20.
- **Thermal:** EP via count/pitch; P vs connected copper; hot↔sensitive distances; airflow cone; cut angle vs radial.
- **DFM:** courtyards (built in); tombstone asymmetry (copper within 1 mm of each pad); polarized-rotation histogram; fiducial count/position/asymmetry; test-point coverage; part-class distance to Edge.Cuts / V-score; HV clearance by net class.
- **PDN:** nearest cap and via distance per power pin; derated C vs Z_t; bead + cap attenuation at f_sw and its harmonics.
- **Specials:**
  - FB angular sector (PWR-17); loop non-containment (FLY-02); parallel SW copper on >1 layer (CHG-02; a WCSP series layer change passes); SW area cap (PWR-03);
  - narrowest cross-section on the current graph (HC-01); quiet/power-ground single join (FLY-05);
  - shared copper between high-current paths and monitor/audio references (BMS-03, AUD-05);
  - mirror symmetry (AMS-07); TC± symmetry (SEN-01); IN− copper (SEN-04/05); Kelvin tap inside the pad (PWR-14);
  - comparative distances (filter nearer the IC than the shunt).

**KiCad encoding** (verify syntax on the installed KiCad) [I]:
- **Net classes per role:** `PWR_HOT`, `SW`, `SENSITIVE` (FB/COMP/RT/SS/REF/crystal), `RF50`, `HV`, `ANALOG`, `DIGITAL`; widths and clearances generated from IPC and fab limits.
- **`.kicad_dru` rules** on `A.NetClass` / `B.NetClass`, `A.intersectsArea('…')` (`insideArea` is deprecated in 10.0) and layer, e.g. SENSITIVE↔SW ≥1 mm with `(severity warning)`, since that distance is a heuristic.
- **Rule areas** from module, antenna and barrier keep-outs (disallow tracks, vias and zones on all layers); courtyard and edge rules by part class (MLCC near V-score).
- **Net ties** to enforce Kelvin and single-point ties, proposed as schematic changes (symbol + `net_tie_pad_groups` footprint). A board-only footprint is an `extra_footprint` parity error.
- **Everything else** (loop area, Kelvin tap point, solid-reference coverage, via-fence pitch, tombstone symmetry, creepage beyond the native `creepage` constraint) is a custom Python check emitting KiCad-style markers.

**Criticality map** (Pease) [I]. Before placement, the LLM emits a reviewable list, each item with severity and provenance:
- hot loops;
- high-Z and summing nodes;
- matched pairs (symmetry constraints);
- thermal aggressors and victims;
- noisy buses and their sensitive neighbours;
- isolation barriers.

A human corrects it before any geometry is generated, and the deterministic checks consume it.

## Recommendations for our system
- **Build the converter detector + hot-loop polygon + loop-inductance estimator first.** They cover the rules sources rank highest.
- **Treat low-authority numbers as soft objectives** and keep provenance (URL, tag) on every emitted constraint, so humans can audit and override.
- **Context-dependence flags** stop over-application:
  - corner rules on RF, ESD, differential-pair and ≥10 Gb/s nets (90° corners are a myth for single-ended nets below about 2 Gb/s);
  - split ground only on datasheet mandate (single bridge);
  - "smallest closest" means lowest mounting L;
  - copper under inductors follows the datasheet;
  - ferrite beads only on requirement, always with a resonance check.
- **Validate detectors on a corpus** of open-source KiCad boards with known regulators. Calibrate thresholds on TI, ADI and Espressif eval-board layouts.

## Conflicts and open questions
- **Default thresholds** (pad gaps, loop-area caps, keep-out distances) are uncalibrated heuristics.
- **KiCad custom-rule syntax**, including the native `creepage` constraint, is documented for 10.0 in [drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md). How `creepage` treats slots and the PD minimum slot width is still to be tested.

## Sources
- research notes: [rules_power_rf_analog_dfm.md § 8, § 9, § 17, § 18, § 19, § 20](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 8, § 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)

See also: [datasheet-to-constraints.md](datasheet-to-constraints.md), [power/hot-loops.md](power/hot-loops.md), [isolation-creepage.md](isolation-creepage.md), [thermal.md](thermal.md), [decoupling-pdn.md](decoupling-pdn.md)
