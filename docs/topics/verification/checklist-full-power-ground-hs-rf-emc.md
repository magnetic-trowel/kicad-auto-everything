# Review checklist (full): power, ground, high-speed, RF, analog, EMC

**TL;DR**
- Physics items need a role/constraint model (currents, frequencies, part roles) before they can be computed.
- GND-02 (no high-speed net over a split/void) is the most agreed item in the whole checklist (8 sources).
- Hot loop, decoupling distance/order and return vias at layer changes are the highest-priority semantic critics.
- This file holds 81 of the 299 checklist items (PDN 15, PWR 9, GND 13, HS 24, RF 6, ANA 4, EMC 10). The Critical items and the most-agreed Major items are summarized in [review-checklist.md](review-checklist.md).

## Key facts

Merged from about 30 checklists by the expert-workflow note. Severity and automation tags are that note's assignments, based on each source's rationale [I]. Numeric thresholds are the cited sources' values; they are fab-specific and conflict between sources, so treat them as profile parameters. Source keys (AZ, GD, KD, AL, ...) are defined in [checklist-sources.md](checklist-sources.md).

- **Sev**: C = critical (dead or unsafe board, unmanufacturable, unassemblable → respin); M = major (SI/PI/EMC/thermal/yield/reliability risk); m = minor (debug, documentation, cosmetics).
- **Auto**: A = geometry/DRC only (KiCad check or custom-rule constraint named where applicable); S = semi-automatic (needs net classes, part roles or datasheet parameters); J = judgment, external info or simulation.

| ID | Category | What to check | Why | Sev | Auto | Sources |
|---|---|---|---|---|---|---|
| PDN-01 | Power integrity | Decoupling caps as close as possible to power pins, one per pin (Altium: under 15 mm; CE default <3 mm) | Loop inductance | M (C for fast ICs) | S (cap-to-pin association) | AZ, JN, KG, CE, AL, UW, SCR |
| PDN-02 | Power integrity | Lowest-mounting-inductance cap closest to the pin (package, via count, via-to-pad distance). The sources' "smallest-value cap closest" is CONTESTED (MT-101 vs Bogatin/Archambeault, VR): use value order only behind the contested-rule selector ([../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)) | HF effectiveness | M | S | PK, TI, UW, FD |
| PDN-03 | Power integrity | Low-inductance mounting (via-in-pad if available, else short side vias to plane) | Mounting inductance dominates | M | S | AZ, HH |
| PDN-04 | Power integrity | Bulk capacitance at power entry and regulator outputs | LF stability | M | S | HH, CE |
| PDN-05 | Power integrity | Every IC power/ground pin connected (pour/thermal connections on all layers; ground pins have vias to the plane) | Floating supply pins | C | A (parity + connectivity) | GD, HH, AL |
| PDN-06 | Power integrity | Trace/plane widths sized for current and temperature rise | Burn-out, IR drop | C | S (per-net current) | AZ, HH, JN, GD, SC |
| PDN-07 | Power integrity | Vias sized and multiplied on high-current paths | Fusing, IR drop | M | S | GD, HH, AL |
| PDN-08 | Power integrity | Plane slots from via antipads minimized | Slotted planes break returns | M | S | AZ |
| PDN-09 | Power integrity | Power filtered at board entry | Conducted noise | M | S | GD |
| PDN-10 | Power integrity | DNP footprints for extra regulator input/output caps | Bring-up tuning | m | J | PK |
| PDN-11 | Power integrity | Every GND/VCC pin and every decap has its own via(s); vias not shared | Shared vias add inductance | M | S | AL, BO, SCR |
| PDN-12 | Power integrity | Enough GND current-carrying vias near connectors and current sinks/sources | Return current capacity | M | S | AL |
| PDN-13 | Power integrity | Width calculated for every track carrying >100 mA from IPC-2221/2152; internal-layer width used if airflow is poor (Flux: ~10 mil/A on 1 oz external at 10 °C rise as a rough start; internal ~2×). Flux's rule holds only near 1 A: IPC-2221 is non-linear (≈12 / 31 / 54 / 109 mil at 1 / 2 / 3 / 5 A on 1 oz external, 10 °C), and inner layers need ≈2.6× the width [I, arithmetic on the VR formula] | Overheating | C | S | AL, FL |
| PDN-14 | Power integrity | Through-hole pin rows in planes keep copper webs between pins (no merged-antipad slots) | Plane slots | M | A | TI-EMI, AZ |
| PDN-15 | Power integrity | BGA decap staging: nF at pins, µF nearby/around BGA, 100s of µF around BGA or on the path from the source (value order: same CONTESTED caveat as PDN-02) | Frequency-staged decoupling | M | S | FD |
| PWR-01 | Power conversion | Switching hot loop (input cap–switch–rectifier; boost: switch–rectifier–output cap) has minimal area | High di/dt loop radiates | C | S + J/sim | TI, GD, TI-BUCK |
| PWR-02 | Power conversion | SW-node copper area minimal; ground plane under the regulator | dV/dt antenna | M | S | TI |
| PWR-03 | Power conversion | FB network at the FB pin; FB trace away from SW/inductor | Regulation noise | M | S | TI |
| PWR-04 | Power conversion | Current-sense lines Kelvin-routed apart from power planes (net ties); gate-drive return routed with its gate | Accuracy, ringing | M | S | TI-FJ3 |
| PWR-05 | Power conversion | AGND/PGND separated and joined at a single point per datasheet | Ground noise into the controller | M | S/J | TI-FJ3, TI-BUCK |
| PWR-06 | Power conversion | Tracks between switch, inductor and caps (including GND) short and wide | Loss, EMI | M | S | GD |
| PWR-07 | Power conversion | Connectors and regulators current-rated in the chosen package | Overheating | C | J | AZ |
| PWR-08 | Power conversion | Shorten before widening: reduce power-loop length first; "beefing up" traces is a last resort | Inductance tracks length | M | S | TI-1229 |
| PWR-09 | Power conversion | Thermal vias under power ICs / exposed pads | Junction temperature | M | S | TI-FJ3 |
| GND-01 | Ground/return | At least one continuous, unbroken ground plane | Return path, EMI | M | S | AL, FL, SCR |
| GND-02 | Ground/return | High-speed nets don't cross splits/slots/voids; if unavoidable, stitching caps (TI: ≤1 µF, at the crossing) or vias | Detoured return acts as an antenna | C (HS) | S | AZ, HH, HT, BOH, TI-HS, FL, VSE, SC |
| GND-03 | Ground/return | Return/stitching vias next to signal vias at reference-layer changes; GND vias around high-speed vias | Return continuity | M | S | PK, BOH, BG, UW, FL |
| GND-04 | Ground/return | Ground not split without justification (audio/precision <~100 kHz exception) | Splits usually worsen EMI | M | J | GD, HT, FXG, FL |
| GND-05 | Ground/return | If grounds are separated, they join at exactly one point | Ground loops | M | S | HH, JN, CD, AL |
| GND-06 | Ground/return | No plane bottlenecks or isolated/floating copper | Starved returns; antennas | M | A (Isolated copper fill) | GD, JN, KD, UW, SCR |
| GND-07 | Ground/return | Vias spread evenly across planes (no via walls) | Avoid slots | m | S | JN |
| GND-08 | Ground/return | No signals, especially noisy ones, along board edges; edge ground ring/stitching (perimeter stitching is CONTESTED, Ott vs Hubing: context switch, not a default, VR) | Edge radiation ("Never run noisy traces on the outside edge") | m | A | HH, GD, TI-EMI, FL |
| GND-09 | Ground/return | Return path checked for every critical net | Root of many SI/EMI problems | M | S/J | GD, HT |
| GND-10 | Ground/return | High-speed differential traces ≥1.5×W from reference voids, except at intentionally voided SMD pads (VR RP-2; see HS-08, EMC-08), and ≥90 mil from plane edges (TI, HS diff pairs) | Fringing/return disruption | M | A/S | TI-HS |
| GND-11 | Ground/return | Two-layer boards: no ground loops; ground track sized for each device's return; unbroken pour under every high-speed trace; power and ground run over each other; length:width ≤3:1 | 2-layer return control | M | S | AL, TI-EMI |
| GND-12 | Ground/return | No buried signal traces in the ground plane (use the +V plane if unavoidable) | Plane integrity | M | A | TI-EMI |
| GND-13 | Ground/return | No loops in power and ground nets | Loop antennas | M | S | SCR, AL |
| HS-01 | High-speed | Differential pairs coupled at impedance gap, as close as possible; uncoupled length limited | Mode conversion | C | A (diff_pair_gap, diff_pair_uncoupled) | AZ, HH, KD, AL, VSE |
| HS-02 | High-speed | Intra-pair skew matched (serpentines at the mismatched end) | Mode conversion | M | A (skew) | AZ, JN, KD, TI-HS |
| HS-03 | High-speed | Inter-signal length matching per interface (DDR, PCIe, Ethernet, LVDS, HDMI, USB3+, MIPI) | Timing | M | A (length/skew rules) | AZ, JR, AL |
| HS-04 | High-speed | Clearance to aggressors; pair-to-pair spacing maximized; clocks isolated | Crosstalk | M | S | AZ, GD, TI-HS, VSE, SC |
| HS-05 | High-speed | Stubs and layer changes minimized; via count limited | Reflections | M | A/S (via_count) | HH, AZ, KD, SC, SCR, FL |
| HS-06 | High-speed | Terminations present and at the correct end | Reflections | M | S | HH, JN, AL |
| HS-07 | High-speed | Mitered/curved bends on impedance-sensitive traces (Flux: a 90° corner on a 20.5 mil trace is transparent below ~25 GHz, so this is mostly DFM/aesthetic for single-ended nets below about 2 Gb/s; keep bend rules for differential pairs and ≥10 Gb/s, [../rules/myths-and-contested.md](../rules/myths-and-contested.md)) | Minor discontinuity | m | A (track_angle) | HH, JN, FL, SF |
| HS-08 | High-speed | Wide connector/SMD pads compensated (plane cutouts/voids under pads) | Impedance dip | M | J/sim | AZ, TI-HS |
| HS-09 | High-speed | Footprint option for a common-mode filter on off-board high-speed pairs | EMC fallback | m | J | HH, TI-HS |
| HS-10 | High-speed | Series-R / 0 Ω placeholders on fast single-ended lines | Edge control later | m | J | HH, PK |
| HS-11 | High-speed | Critical nets routed first, by hand, and locked (power/ground and susceptible nets → clocked data → rest; autorouter only for <50 kHz nets) | Everything else routes around them | M | J (process) | JR, EN, PC, BO, TI-EMI |
| HS-12 | High-speed | "Low-frequency" buses judged by edge rate | Fast edges radiate | m | J | GD |
| HS-13 | High-speed | Impedance constant along each trace, including across layer changes and after BGA escape | Reflections | M | S | AL, TI-HS |
| HS-14 | High-speed | Electrically long nets (Altium: longer than 1/6 of rise time) simulated and terminated; long parallel runs simulated for crosstalk | SI | M | J/sim | AL |
| HS-15 | High-speed | No test points or stubs on high-speed differential nets; no stubs to test points or unused connector pins | Stubs, discontinuities | M | A/S | TI-HS, AL, SCR |
| HS-16 | High-speed | High-speed traces not under/near crystals, oscillators, SMPS, mounting holes, magnetics or clock-duplicating ICs | Coupling | M | S | TI-HS |
| HS-17 | High-speed | Via stubs <15 mil or back-drilled; antipads enlarged (~30 mil) on high-speed vias; no non-functional pads | Resonance, capacitance | M | A/S | TI-HS, SC |
| HS-18 | High-speed | Equal via count on both members of a pair, symmetric and close to the SoC | Mode conversion | M | A | TI-HS |
| HS-19 | High-speed | Pair routed symmetrically; deviations (escape, connector) short; breakout within 0.25" of the package; constant width after escape | Skew, Z | M | S | TI-HS |
| HS-20 | High-speed | Series SMDs on high-speed lines ≤0603 (prefer 0402), placed symmetrically | Pad discontinuity | M | S | TI-HS |
| HS-21 | High-speed | Routing topology per interface checked (point-to-point, fly-by, T, daisy chain); signal groups use the same topology | Timing/SI | M | S | SC, FD |
| HS-22 | High-speed | Net-length vs Manhattan/MST ratio outliers flagged ("no scenic routes") | Delay, EMI | m | A | AL, BO |
| HS-23 | High-speed | Trace length vs wavelength: >λ/10 (FCC) or >λ/50 (automotive/consumer 2-layer) considered for termination | Antenna factor | m | S | TI-EMI |
| HS-24 | High-speed | Adjacent signal layers routed orthogonally (H/V) | Broadside coupling | m | A/S | VSE, SC |
| RF-01 | RF | RF line (e.g., GCPW) impedance verified with the real stackup; mask effect | Mismatch | M | S | AZ, PK |
| RF-02 | RF | Via-fence pitch ≤ λ/8 | Leakage | M | S (needs frequency) | PK, HH |
| RF-03 | RF | Stitching vias in large top-layer ground pads (e.g., SMA) | Resonances | M | S | AZ |
| RF-04 | RF | Antenna/module keep-outs per datasheet | Detuning | C | A once drawn; S to derive | GD, JN, CE |
| RF-05 | RF | Shield-can footprint where needed | EMC fallback | m | J | HH, AL |
| RF-06 | RF | Edge launch: fab confirmed for copper to edge | Launch performance | M | J | AZ |
| ANA-01 | Analog | Guard rings/cages where needed | Leakage, pickup | M | J | AZ |
| ANA-02 | Analog | Sensitive analog separated from SMPS/noisy digital; filters between groups | Noise | M | S | AZ, GD, KG, SCR, SC |
| ANA-03 | Analog | Noisy traces not adjacent to critical traces on any layer | Crosstalk | M | S | GD |
| ANA-04 | Analog | MLCC microphonics considered | Noise | m | J | AZ |
| EMC-01 | EMC/ESD | ESD/TVS at the connector entry with a short ground path | Shunt the surge early | M | S | HH, CE, TI-HS, SC |
| EMC-02 | EMC/ESD | No small or sharp floating copper | Radiation | m | A (Isolated copper fill) | JN, KD |
| EMC-03 | EMC/ESD | Ferrite-bead DC-current margin; filter targets defined | Bead impedance collapses under bias | m | J | HH |
| EMC-04 | EMC/ESD | SMPS snubber footprint option | Ringing | m | J | HH, TI-1229 |
| EMC-05 | EMC/ESD | Plane keepouts and chassis bonding for shielded connectors and magnetics | Isolation | M | S | AZ, HH |
| EMC-06 | EMC/ESD | EMI/RFI filtering at the exit point (board edge, connector, shield) | Filter before leaving | M | S | AL |
| EMC-07 | EMC/ESD | ESD pads in series with the track (the surge reaches the protection pad before the protected device); unprotected traces kept away from protected ones | Protection effectiveness | M | S | AL, TI-HS |
| EMC-08 | EMC/ESD | High-speed ESD layout: AC caps on the protected side of the CMF, all close to the connector; ~60% voids under ESD pads; 0402 0 Ω CMF no-stuff | Loss and protection | m | S | TI-HS |
| EMC-09 | EMC/ESD | Decoupling at connectors where needed; separate ESD earth paths considered | EMC | m | J | AL |
| EMC-10 | EMC/ESD | Board-to-board cables: ≥1 ground return per 9 signals (1 per 4 if >1 ft) | Return path in cables | m | S | TI-EMI |

## Recommendations for our system

- Store these rows as machine-readable data (ID, severity, automation class, threshold, threshold source, KiCad key) and drive the critic stack from it; see [critic-stack.md](critic-stack.md).
- Load every numeric threshold from a fab/assembler profile with provenance (datasheet > fab profile > house default) [I].

## Conflicts and open questions

- Severity/automation tags are one author's assignments and need validation against escaped-error data [I].
- Thresholds conflict between sources (e.g. silk height 25 mil vs 1.0 mm vs 50 mil; edge clearance 8 vs 10 mil; part-to-edge 125 mil vs 5 mm).
- KiCad DRC key names in the Auto column follow the source note; the verified KiCad 10 key list is in [../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md).

## Sources

- research notes: [expert_workflow_and_checklists.md § Q4 Master checklist table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- corrections: [verification_kicad_and_tools.md § 1 Corrections table](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- corrections (VR): [verification_rules.md § 1 (RP-2, PDN-07, EMI-4, "smallest closest"), § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- source checklists and their URLs: [checklist-sources.md](checklist-sources.md)

See also: [review-checklist.md](review-checklist.md), [critic-stack.md](critic-stack.md), [respin-and-fab-hold-data.md](respin-and-fab-hold-data.md)
