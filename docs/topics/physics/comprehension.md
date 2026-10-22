# Comprehension: what each part, net and structure is doing

**TL;DR**
- **`kae.circuit` reads only what a `.kicad_pcb` states and writes the physics brief.** It never reads positions. The brief gives every net and part a role, and finds the structures that decide a layout's physics: hot loops, decoupling, crystal loops, protection chains, feedback and sense victims, antennas and heat. Each entry carries a confidence and its evidence. Median cost: 0.06 s per board [C].
- **Evidence is additive log-odds over checkable facts.** A part's kind is a softmax with an explicit *unknown* class, so weak evidence yields "unknown", not a guess. Budgets are E5 Beliefs with a stated basis.
- **Topology-defined structures are reliable.** On 10 audited boards (after fixes), cells, crystals, feedback dividers and Kelvin shunts were all found and right. In the human layouts, 77% of the 64 hot loops sit below the 5th percentile of random placement, and crystals sit a median 4.7 mm from their IC [C].
- **Capacitor ownership on shared rails is the weak spot.** The brief names the right owner for 73% of capacitors, against a 38% baseline. Without sheet names or schematic order it drops to 61%. On boards with many identical loads (keyboards, LED strings) it falls to 0–20%, and the brief's low probabilities flag those cases [C].
- **On 3 held-out boards (before fixes), half the cells and 39% of the sensitive nets came out right.** The failures were library typing and unseen part families, not the method. Placement should take every structure's confidence as a weight and keep low-confidence ownership soft.

Tags: [C] computed by [`cm_comprehension_eval.py`](../../../tools/research/physics/cm_comprehension_eval.py) on the 112 reference boards; [I] our reading. Raw evidence, per-board error lists and the suite table are in [comprehension_audit](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/comprehension_audit.md).

## 1. Interface

```python
from kae.board.kicad_file import load
from kae.circuit.brief import build, write
brief = build(load('board.kicad_pcb'))   # JSON-ready dict, schema 'kae.brief/1'
write(board, 'brief.json')
# python -m kae.circuit.brief BOARD.kicad_pcb [-o brief.json] [--no-sheets]
```

| Key | Content |
|---|---|
| `nets` | name → role (ground, rail, switch_node, clock, high_speed, analog, rf, reset, boot, signal, no_connect), subrole, `volts` plus a full `volts_belief`, `source` (kind, `part` uuid, `path`), evidence |
| `parts` | footprint uuid → `ref`, kind, subtype, role, `external` (cable, antenna, board), `P_W`, confidence, evidence |
| `structures` | list with `id`, `kind`, `confidence`, `evidence`, `priority`; members by uuid, `members_ref` maps them back |
| `diff_pairs` | p, n, interface, a Zdiff budget where the interface defines one |
| `placement_order` | structure ids, physically decisive first |
| `summary` | counts, unknown and low-confidence parts, power pins without capacitors, runtime |

Positions never enter: a test moves every footprint and pad at random and checks that the brief comes back identical, on fixtures and on a real board.

## 2. The evidence model

Every conclusion is a sum of natural-log-odds weights over facts a reviewer can check: STRONG 3.0, MODERATE 1.5, WEAK 0.7, negative where a fact argues against. Confidence = logistic(prior + Σw), clipped to [0.02, 0.98], and the facts are kept as text ("power_in pins on 2 parts (U3.VDD)"). They come from eight sources: refdes prefix, lib id, value and fields, pin function, pin type, topology, net class and sheet. Most errors come from one source lying (a library types VIN as `input`; a GPIO is named after its oscillator function), so no source decides alone and each rule names its counter-evidence.

- **Part kinds** are a softmax over kind scores plus an *unknown* score of 1.0. Over the suite's 9,227 parts, 4 end unknown and 172 below 0.6 [C].
- **Budgets** are E5 Beliefs with a basis, for example `f_sw = 1.1 MHz for AP63203` or `I = 0.6 × the 2.1 A rating in L1's value`. Generic priors live in `kae.physics.priors`; the brief states only board-specific facts.

## 3. Inference rules

### 3.1 Part kinds

| Evidence | Examples | Weight |
|---|---|---|
| Lib id (case-sensitive) | `Capacitor_SMD:`, `R_Shunt_*_Kelvin`, `MountingHole`, `Crystal` | 2.5–4.0 |
| Part-number families | TVS/ESD (`SMBJ`, `USBLC6`), regulators, MCUs, PhotoMOS (`GAQY`), battery monitors (`BQ769xx`) | 2.0–5.5 |
| Value as a quantity | `4u7` (C), `0R05` (R), `600R@100MHz` on an inductor body (bead), `16V` on a diode (zener) | 1.0–4.0 |
| Pins | G/D/S, B/C/E, A/K; supply plus output pins on a crystal-like part means an oscillator (≤ 8 pins) | 0.5–3.0 |
| Pad census | no pads, or only unplated holes, rules out every electrical kind | −3.0 |
| Refdes prefix | `C`, `R`, `U`, `FB`, `TP`; weak alone | 0.5–2.5 |

IC subtypes come from a family table (specific families first). Package codes in values are stripped first, so `10k/0402` does not read as 0.04 Ω.

### 3.2 Net roles

| Role | For | Against |
|---|---|---|
| Ground | name, pins named GND/VSS/EP, many 2-pin caps to it | splits stay distinct: analog, power, isolated, chassis |
| Rail | `power_in` pins; supply-named pins even when typed input or bidirectional; `power_out` on an IC or module only; regulator/inductor outputs; caps to ground; pours; rail-like names | a control suffix (`12V0_OUT_EN`); a differential sense input (VIN+/IN−) with no supply pin; sense or monitor names; only logic-typed IC pins |
| Switch node | an inductor between an IC switch pin (or a FET pair) and a decoupled rail; integrated bridge outputs | a FET pair without power-stage evidence (inductor, shunt, driver, power package) is a logic gate |
| Clock | crystal or oscillator terminal (STRONG); clock names | a pin name alone is WEAK: STM32 PC14 and ESP32-C3 XTAL_32K pins double as GPIOs |
| High-speed, diff pair | interface names, net class, complementary names (P/N, +/−, H/L) on a common IC or connector | an LED or opto across the pair; I2C names win over SPI's SCLK |
| Analog | ADC/sense/reference names; op-amp, ADC and current-sense inputs; any IC with `+`/`−` pins; battery-monitor cell inputs | logic, memory and bridge-driver pins (`AIN1` on a DRV8411 is a logic input) |
| Reset, boot | names; RST/MCLR pins; EN only on MCUs and modules; BOOT/GPIO0 only on ESP parts | a converter's BST net is a bootstrap, not a boot strap |

**Rail sources**, first match wins:
1. a battery;
2. a development-board module's 3V3 pin;
3. an input jack's supply pin;
4. an IC's internal output;
5. a bridge rectifier;
6. a regulator, charger or load switch output;
7. a converter's inductor;
8. a series path up to a rail or jack (fuse, bead, inductor, a resistor ≤ 1 Ω, a closed jumper, a diode, a four-terminal shunt), through middle nets that carry only shunt parts;
9. any connector;
10. unknown.

Normally-open solder jumpers carry nothing. On a negative rail the diode direction reverses. An auto-named net seen only by one IC and its capacitors is that IC's own node (`internal`).

**Rail voltages**, in order:
- the name (`3V3`, `12P0V`, `-12V`);
- a regulator part number (`AMS1117-3.3`);
- USB (5 V; 4.4–20 V with a PD controller) or battery defaults;
- connector names;
- a core-regulator table (RP2040 VREG_VOUT 1.1 V, STM32 VCAP 1.2 V);
- inheritance through series parts (−0.4 V per diode; a load switch passes its input);
- last, the lowest capacitor rating ÷ 1.6, with interval [rating/3, rating].

### 3.3 Structures

**Commutation cells** follow [hot-loops](../rules/power/hot-loops.md):

| Topology | Loop (closed on the commutation capacitor) |
|---|---|
| Buck (integrated, synchronous, asynchronous) | C+ → VIN/high side → SW → low side or catch diode → PGND → C− |
| Boost | C_out+ → rectifier or high side → SW → low side → PGND → C_out− |
| 4-switch buck-boost | input half-bridge and output half-bridge as two cells |
| Integrated bridge, discrete half-bridge | C_bus → VM → bridge → PGND |
| Regulator module | C_in → VIN → GND (inductor inside) |

Buck versus boost is a vote: an input pin away from the inductor, a high-side FET or a catch diode count for buck; a rectifier into another rail, a supply pin on the inductor's far end or an output pin elsewhere count for boost. Part-number tables break ties. Without a named input pin, the controller's `power_in` pins on decoupled rails stand in. That excludes rails it feeds through its own inductor: the nPM1300's +1V8 came back through a 0 Ω link. Loop terminals leave out EN, MODE and PG pins tied to the rail. Excitation (V, I, t_sw, f_sw) comes from the rail, the part tables and the inductor's current rating.

**Capacitor allocation** runs jointly per rail, over every capacitor from the rail to ground:

| Owner | Quota | Prefers |
|---|---|---|
| Commutation cell | 2 | ceramics ≤ 1 µF, unless the loads' pins need every one; then the largest bulk ones |
| Load (IC, module, LED) | one per power pin | ceramics ≤ 1 µF (+0.3) |
| Regulator input or output pin | 1 | larger capacitors |
| Split supply (V+ to V−, op-amps) | one per V+ pin | capacitors straight across the two rails |
| Entry of a connector-fed rail | the number of polarized caps ≥ 10 µF | those caps only |
| Converter output (buck) / input (boost) | the number of caps ≥ 10 µF | those caps only, owned by the inductor's far pad |

The score adds schematic affinity (same sheet +2, other −1; same 100-block of references +1.5) and a class preference. Assignment is greedy by score with quotas. Ties fill owners in reference order with capacitors in reference order, because designers number blocks together. Leftover caps go to the best-scoring owner. Each capacitor's ownership probability is a softmax of the same scores plus log(quota). Each decap structure also suggests a pin-to-capacitor pairing.

**Other structures:**
- **Crystal circuits:** IC oscillator pins, load caps, series and feedback resistors, f.
- **Oscillators:** output net and load.
- **Feedback dividers:** top, bottom and feed-forward cap. A Vref table gives the implied Vout. When an IC's pins are unnamed, a `V?FB` net name stands in.
- **Measurement dividers:** a resistor from a rail, switch node, analog net or connector, and one to ground, read by an IC. A strap on a logic pin from a regulated rail of 5.5 V or less does not count.
- **Shunts** (≤ 0.2 Ω, or a shunt footprint): the amplifier that reads both sides, directly or through filter resistors of 1 kΩ or less; the Kelvin type, two- or four-terminal.
- **Protection chains:** connector pin → TVS or ESD array, or a zener clamping to a ground or rail → series parts → first IC pin. A converter's inductor and diodes are never chain parts.
- **Antennas:** feed and match network.
- **Heat sources:** conversion loss at 88%, LDO drop × current, bridge and FPGA class estimates.
- **Thermal victims:** crystals, electrolytics, sensors.

### 3.4 Placement order

Structures are ranked by priority:
- **Hot loops: 100 + 10·log10(1 + V·I).**
- **85:** antennas.
- **75–77:** crystals.
- **40–70:** victims (sense 70, feedback 65, crystal 60).
- **50–55 + 5·log10(1 + pins):** decaps.
- **45:** protected chains.
- **30–60:** heat sources.

The placer seeds structures in this order.

## 4. Measured accuracy

### 4.1 Weak labels from the human placement [C]

These are 112 reference boards (9,227 parts) from the KiCad 10.0.7 suite. The brief is built without positions. The human layout then scores it.

| Measure | Result | Without sheet names | Random tie order | Baseline |
|---|---|---|---|---|
| Capacitor ownership: all owners on rails with ≥ 2 candidates (1,381 caps, 74 boards) | **73.1%** (per-board mean 68.0%) | 60.9% | 60.8% | 37.8% |
| Decap ownership: decap groups only (1,160 caps) | 74.7% | 61.9% | 59.6% | 38.2% |
| Cap among the 3 nearest caps to one of its IC's power pins | 74.9% | 66.7% | 66.6% | |
| Suggested pin pairing: the nearest same-rail cap | 33.3% | 31.0% | 23.5% | 16.8% |
| Hot loops below the 5th percentile of random placement (64 cells) | **76.6%** (below the 1st: 40.6%; median 13.5 mm) | 70.3% | 71.9% | 5% |
| Crystal to IC (31) | median 4.7 mm, 87% within 12 mm; load caps 2.8 mm away | | | |
| TVS nearer the connector than the protected IC (266 chains) | 60.2% | | | 50% |

The truth for ownership is the nearest candidate owner's pin. Candidates include decap groups, cells, a connector-fed rail's entry and a buck's inductor, even in runs that do not name them. Boosts sit tighter than bucks: all 6 boosts and 70% of the 47 bucks fall below the 5th percentile. Feedback dividers (95% below the 5th percentile of member spread) and crystal circuits (97%) are the most compact structures.

**Ownership probabilities are monotone but underconfident below 0.7.** Caps reported below 0.5 (mean 0.24) are right 52% of the time, 0.5–0.7 (mean 0.59) 79%, 0.7–0.9 90%, ≥ 0.9 91%.

**What did not help (ablations):**
- a rank-order term (best at weight 0);
- a penalty on a cell's second capacitor;
- quotas scaled under shortage (−2.4 pp);
- "ICs before LEDs" on ties (neutral).

Each kept rule moved the pooled number by 0.2–0.5 pp or fixed an audited case.

### 4.2 Manual audit [I]

The counts below are structure-level. Member-level slips, such as a loop closed on the second-nearest capacitor, are listed in the note but not counted.

| Structure | Dev, 10 boards after fixes: P / R | Held-out, 3 boards before fixes: P / R |
|---|---|---|
| Commutation cells | 10/10, 10/10 | 2/4, 2/4 (an nPM1300's own output taken as its input) |
| Crystals, feedback dividers, antennas | 11/11, 11/11 | 3/3, 3/3 |
| Kelvin shunts | 8/8, 8/8 | 0/0, 0/1 (a '300µ' four-terminal shunt) |
| Measurement dividers | 9/9 | 0/1 (a logic strap) |
| Protected chains | 12/14 (two through an ESD array's VBUS pin) | 18/18 |
| Decap groups (IC, rail) | 47/48, 47/50 | 25/25 |
| Rails | 50/50; 3 voltages, 3 sources wrong | 27/27; 3 voltages, 3 sources wrong |
| Sensitive nets | (not counted) | 13/15, 13/33: THAT1512 inputs and 17 BMS cell taps missed |
| Part kinds | 943/945 | 430/431 |

The dev boards are training data: the errors found there were fixed, each with a test. The held-out errors came from library typing and families the dev boards lacked (amplifiers known only by `+`/`−` pins, battery-monitor AFEs, `300µ` values, a PMIC symbol without an input pin); they were then fixed and tested too.

## 5. Failure modes that matter for placement

1. **Many identical loads on one rail.** With 29 WS2812 LEDs on 5 capacitors, or a keyboard's per-key LEDs, ownership is guesswork (0–20% on those boards). Reference order is the only cue. The brief reports probabilities of 0.2–0.3 there; place these caps by pin density, not by the named owner.
2. **Unnamed rails have no voltage.** Excitation V is null on 13 of 64 cells (20%), where the input rail has no name, part number or rating, and on OR-ed inputs only the known input counts (4.6 V where a 24 V bus can feed the node). Treat a null V as "unknown, possibly high", not as zero.
3. **Power paths without switching are invisible.** Load switches, ideal-diode PMOS muxes and FET banks (a BMS's 8 pack FETs) get no heat or loop structure, because currents are unknown. PMOS power paths are not followed, so those rails show a header as their source.
4. **Two-hop topologies.** An input shunt inside a buck's switch path, a bootstrap through a series resistor, and charge-pump caps all get generic roles. The hot loop is then right in order but incomplete.
5. **Library typing lies.** Pins typed against their function (VIN as input, VIN+ as power_in, GPIOs named XTAL) were the largest error class on both dev and held-out boards. The rules now cross-check type, name and topology, but new libraries will find new cases. The dev-board recall of 94–100% is optimistic; expect something nearer the held-out figures on new designs.
6. **Protection order is a weak label.** In only 60% of human layouts does the TVS sit nearer the connector than the IC. Placement should still enforce connector → TVS → IC, but cannot learn it from human boards.

## 6. Recommendations for our system

- **Seed the placer from `placement_order` and weight terms by confidence.** Hot loops and crystals can act as hard groups. Keep decap ownership below p = 0.7 soft: let such a capacitor go to the nearest same-rail power pin.
- **Use `caps_p`, not only `caps`.** The probabilities rank well (§4.1); recalibrate before using a hard threshold.
- **Report "unknown" upward.** A null rail voltage, an unknown source or an unknown part goes to the LLM layer as a question, with the evidence gathered ([design-understanding-pipeline](../llm/design-understanding-pipeline.md)).
- **Re-run the weak-label evaluation after every rule change** (40 s for 112 boards). A new rule must not lower pooled ownership, cell compactness or crystal distance.

## Conflicts and open questions

- **Schematic order carries about 12 points of ownership accuracy** (§4.1 ablations). The netlist alone cannot separate a 10-pin MCU's caps from a flash chip's on one rail. A schematic, or a datasheet's per-pin recommendation, would.
- **Hot-loop membership is set by topology tables.** Simulating the schematic ([schematic-to-physics](schematic-to-physics.md)) would measure it, including for topologies no table covers.
- **Held-out recall rests on 3 boards.** A larger blind audit, of 10 boards from the newer `kae-work-v2` suite, would tighten the 39% sensitive-net and 50% cell figures.

## Sources

- Research note: [comprehension_audit.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/comprehension_audit.md) (weak labels, variant study, per-board audit lists, suite table).
- Code: `kae/src/kae/circuit/` (roles, structures, brief); tests `kae/tests/test_circuit_*.py`; evaluation [`cm_comprehension_eval.py`](../../../tools/research/physics/cm_comprehension_eval.py).
- Topology tables: [hot-loops](../rules/power/hot-loops.md); interface impedances: `docs/topics/rules/interfaces/`.

See also: [net-role-classification](../llm/net-role-classification.md), [suite-physics-results](suite-physics-results.md) (the suite run whose failure modes this stage fixes), [physics-core-v2-api](physics-core-v2-api.md) (Belief), [pdn-and-commutation](pdn-and-commutation.md).
