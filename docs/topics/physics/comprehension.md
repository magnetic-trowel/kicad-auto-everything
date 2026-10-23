# Comprehension: what each part, net and structure is doing

**TL;DR**
- **`kae.circuit` reads only what a `.kicad_pcb` states and writes the physics brief.** It never reads positions. Every net and part gets a role, and the brief lists the structures that decide a layout's physics: hot loops, non-switching power paths, decoupling, crystal loops, protection chains, victims, antennas and heat. Each entry carries a confidence and its evidence. Median cost: 0.1 s per board [C].
- **Evidence is additive log-odds over checkable facts, and names outvote pin types.** A library that types VIN as `input` or EN as `power_in` no longer changes the brief. With every pin type deleted, 99.4% of net roles and 93% of decap groups survive [C].
- **Topology-defined structures are reliable.** In the human layouts, 81% of the 64 hot loops sit below the 5th percentile of random placement. Crystals sit a median 4.7 mm from their IC. The 26 power paths found are all real [C][I].
- **Capacitor ownership on shared rails is the weak spot.** The brief names the right owner for 74.7% of capacitors, against a 38% baseline, and 76.0% once rail groups of identical loads pair by distance. It now names a pin for a capacitor only where the netlist decides it: 11.6% of those pairs land over 10 mm away in the human layout, down from 33.2% [C].
- **Held-out boards fail on library typing and unparsed names, not on the method.** Placement should weight every structure by its confidence and keep low-confidence ownership soft.

Tags: [C] computed by [`cm_comprehension_eval.py`](../../../tools/research/physics/cm_comprehension_eval.py) and [`cm_pin_type_robustness.py`](../../../tools/research/physics/cm_pin_type_robustness.py) on the 112 reference boards; [I] our reading. The raw evidence, per-board error lists and the suite table are in [comprehension_audit](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/comprehension_audit.md).

## 1. Interface

```python
from kae.board.kicad_file import load
from kae.circuit.brief import build, write
brief = build(load('board.kicad_pcb'))   # JSON-ready dict, schema 'kae.brief/1'
# python -m kae.circuit.brief BOARD.kicad_pcb [-o brief.json] [--no-sheets]
```

| Key | Content |
|---|---|
| `nets` | name → role (ground, rail, switch_node, clock, high_speed, analog, rf, reset, boot, signal, no_connect), subrole, `volts` plus `volts_belief`, `source` {kind, `part` uuid, `ref`, `path`}, evidence |
| `parts` | footprint uuid → `ref`, kind, subtype, role, `external`, `P_W`, confidence, evidence |
| `structures` | `id`, `kind`, `confidence`, `evidence`, `priority`; members by footprint uuid, `members_ref` maps them back |
| `diff_pairs`, `placement_order`, `summary` | pairs with a Zdiff budget; structure ids by priority; counts and runtime |

Structure kinds and the fields a placer or router reads:

| Kind | Fields |
|---|---|
| `commutation_cell` | `class`, `rail`, `sw`, `gnd`, `loop` [[uuid, pad(s)]…] closed on the commutation cap, `caps`, `caps_p`, `excite` {V, I, t_sw_ns, f_sw_Hz}; optional `series_shunt` [uuid], `bootstrap_cap`, `bootstrap_r`, `charge_pump_caps` [uuid], `snubbers` [[r, c]] |
| `power_path` | `class` (load_switch, power_mux, ideal_diode, reverse_polarity, fet_bank, fet_switch), `switches`, `stages` [[uuid]], `controller`, `rail_in`, `rail_out`, `gnd`, `series`, `caps_in`, `caps_out`, `loop`, `group`, `excite` {V, I, I_belief}, `R_on_ohm`, `P_W` |
| `decap` | `ic`, `function`, `rail`, `ground`, `power_pins`, `caps`, `caps_p`, `hf_caps`, `bulk_caps`, `pin_caps` {pin: [uuid]}, `pairing` ('pin', 'nearest_pin', 'nearest_load'), optional `rail_group` |
| `rail_group` | `rail`, `ground`, `loads` [uuid], `caps` [uuid], `pairing` 'nearest_load', `basis` |
| others | `crystal`, `oscillator`, `connector_chain`, `victim` (feedback, sense, divider, analog, crystal), `antenna`, `heat_source` {part, P_W, P_W_belief}, `thermal_victim` |

Positions never enter: a test moves every footprint and pad at random and checks that the brief comes back identical.

## 2. The evidence model

Every conclusion is a sum of natural-log-odds weights over facts a reviewer can check: STRONG 3.0, MODERATE 1.5, WEAK 0.7, negative where a fact argues against. Confidence = logistic(prior + Σw), clipped to [0.02, 0.98]. The facts are kept as text ("power_in pins on 2 parts (U3.VDD)"). They come from eight sources: refdes prefix, lib id, value and fields, pin function, pin type, topology, net class and sheet. No source decides alone, and each rule names its counter-evidence. Part kinds are a softmax with an *unknown* score of 1.0: 4 of the suite's 9,227 parts end unknown. Budgets are E5 Beliefs with a basis (`f_sw = 1.1 MHz for AP63203`).

**Pin semantics put the name first.** Each pin is read as ground, supply, supply output, analog, signal or nothing, in this order:
1. Ground names, except V−/VSS on a negative rail.
2. Differential-input names (VIN+, IN−, SENSE+) on non-power ICs are analog.
3. A `power_out` pin on a regulator, PMIC or charger is an output unless named VIN or IN.
4. Supply names (VIN, VDD, AVCC, MVDD, VBAT, `3V3`) are supplies.
5. Internal regulator outputs (VCAP, REG18, VBUS_OUT) and regulator OUT pins are supply outputs.
6. Logic names (GPIO, EN, TXD, SCL, PA3) are signals.
7. Only then the pin type, then weak names.

KiCad markup is stripped first: `V_{DD}` reads as VDD.

## 3. Inference rules

### 3.1 Part kinds and net roles

Part kinds come from lib ids (`R_Shunt_*_Kelvin`, `Crystal`), part-number families (USBLC6, BQ769xx, GAQY), values read as quantities (`4u7`, `0R05`, `16V` on a diode), pin sets (G/D/S, A/K) and refdes prefixes. A pad census rules out electrical kinds for logos and holes. Package codes are stripped from values first, so `10k/0402` does not read as 0.04 Ω.

| Role | For | Against |
|---|---|---|
| Ground | names, ground pins, many 2-pin caps; a battery's negative pole net-tied to ground | splits stay distinct (analog, power, isolated, chassis); Kelvin lines tied to ground keep their role |
| Rail | supply pins, regulator and inductor outputs, caps to ground, pours, rail names; a module supply pin wired straight to a connector pin | a control suffix (`12V0_OUT_EN`); a sense input with no supply pin; logic-only IC pins |
| Switch node | an inductor between an IC switch pin or FET pair and a decoupled rail | a FET pair without power-stage evidence is a logic gate |
| Clock | crystal or oscillator terminals | a pin name alone (PC14, XTAL_32K on an ESP32-C3 GPIO) |
| Diff pair | complementary names on a common IC or connector; MIPI on a camera FPC | an LED across the pair; a crystal's XTALP/XTALN |
| Analog, reset, boot | ADC, sense and reference names; amplifier and AFE inputs; RST and BOOT pins | logic and bridge-driver pins; a converter's BST net |

**Rail sources**, first match wins: battery, a dev module's 3V3 pin, an input jack's supply pin, an IC's internal output, a bridge rectifier, a regulator or load-switch output, an inductor, a series path (fuse, bead, ≤ 1 Ω, closed jumper, diode, four-terminal shunt) through middle nets, any connector, unknown. A diode from a low-side switch's drain is a flyback clamp, not a source. When two rails joined by a fuse name each other, the connector side wins. **Voltages** come from the name, a regulator part number, USB or battery defaults, a core-regulator table, inheritance through series parts (−0.4 V per diode), and last the lowest capacitor rating ÷ 1.6.

### 3.2 Commutation cells

Cells follow [hot-loops](../rules/power/hot-loops.md): buck (C+ → high side → SW → low side or catch diode → PGND → C−), boost (closed on C_out), 4-switch buck-boost as two half-bridges, integrated and discrete bridges, regulator modules. Buck versus boost is a vote over input-pin side, high-side FET, catch diode and rectifier direction; part tables break ties. Loop terminals leave out EN, MODE and PG pins tied to the rail, and a PMIC's VSYS output on the input net. Two-step members join the cell:
- `series_shunt`: a shunt between the input cap and the switch;
- `bootstrap_r`: a resistor between the BST pin and its capacitor;
- `charge_pump_caps`: a bridge driver's flying and storage caps;
- `snubbers`: an RC from the switch node to ground or the rail.

### 3.3 Capacitor allocation and pin pairing

Allocation runs jointly per rail over every capacitor from the rail to ground:

| Owner | Quota | Prefers |
|---|---|---|
| Commutation cell | 2 | ceramics ≤ 1 µF unless the loads need every one |
| Load (IC, module, LED) | one per power pin | ceramics ≤ 1 µF |
| Regulator pin | 1 | larger capacitors |
| Split supply (V+ to V−) | one per V+ pin | caps straight across the rails |
| Connector entry; buck output / boost input | their bulk caps (polarized ≥ 10 µF; ≥ 10 µF) | those only (exclusive owners) |

The score adds schematic affinity (same sheet +2, other −1, same 100-block of references +1.5) and the class preference. Assignment is greedy with quotas; ties fill owners in reference order. Leftovers go to the near-best owner with the fewest caps per pin. A converter left without a capacitor takes another converter's second one. Ownership probability `caps_p` is a softmax of the same scores.

**Pairing is stated only where the netlist decides it.** `pin_caps` names a pin only for a single-pin group and only for small ceramics within quota at p ≥ 0.5 (`pairing: 'pin'`). A group with several pins on one net says `nearest_pin`: the placer pairs each cap with the nearest of those pins. Entry bulk says `nearest_load`. Three critical-router cases traced to rule errors: round-robin pin assignment, a module's `3V3` pin read as a regulator output, and leftovers piling on the first consumer. Fixing them cut pairings with a human distance over 10 mm from 33.2% to 11.6% [C].

### 3.4 Power paths without switching

A `power_path` covers integrated load switches, eFuses and muxes, and discrete MOSFETs: banks of equal D/S chained through back-to-back middle nets, reverse-polarity and ideal-diode PMOS, and low-side switches. Gate drive sets direction. A gate at ground, or a PNP mirror or ideal-diode IC, puts the body diode forward (D in). A switch drive puts a PMOS's source in. Totem poles (logic gates, half-bridges) and FETs straight across a regulated rail (crowbars) are excluded. Multi-input classes get one path per input, sharing `caps_out`; `group` is the mux IC's uuid or `or:<rail_out>`.

- **Loop:** C_in+ → pass element(s) → C_out+ → C_out− → C_in−. A low-side path closes through the load's terminals (a connector's two pins, or twin pads) and the supply cap.
- **Capacitors:** the path IC's own and unclaimed or entry caps first. A load's cap is borrowed only to close the loop.
- **Current** (`I_belief`, E5, interval [I/3, I]): fuse rating > load-switch table > shunt at 50 mV full scale > connector or package class. It is capped by what the package can dissipate.
- **Heat:** `R_on_ohm` (an E5 Belief) comes from a part table or package class. Each pass element is a `heat_source` with P = (I/n)²·R_on.

### 3.5 Rail groups and other structures

A **rail group** marks ≥ 6 identical loads on one rail, or ≥ 4 when the rail has fewer caps than loads. Identical means the same kind and value; rotated footprint variants count. Ownership there is a reference-order guess, so the group tells the placer to pair each cap with its nearest group load. Those loads' decaps carry `rail_group` and `pin_caps: {}`.

Other structures:
- **Crystal circuits:** oscillator pins, load caps, series and feedback resistors.
- **Feedback dividers:** with a Vref table for the implied Vout.
- **Measurement dividers:** but not logic straps.
- **Shunts:** with their amplifier and Kelvin type.
- **Protection chains:** connector → TVS → series parts → first IC pin.
- **Antennas:** with match networks.
- **Heat:** conversion loss, LDO drop, class estimates.
- **Thermal victims:** crystals, electrolytics, sensors.

### 3.6 Placement order

| Priority | Structures |
|---|---|
| 100 + 10·log10(1 + V·I) | hot loops |
| 85 | antennas |
| 75–77 | crystals |
| 60 + 10·log10(1 + P) | power paths |
| 40–70 | victims |
| 50–55 + 5·log10(1 + pins) | decaps |
| 48 + 2·log10(1 + loads) | rail groups |
| 45 | protected chains |
| 30–60 | heat sources |

## 4. Measured accuracy

### 4.1 Weak labels from the human placement [C]

The brief is built without positions on 112 reference boards (9,227 parts, KiCad 10.0.7 suite); the human layout scores it. The ownership truth is the nearest candidate owner's pin.

| Measure | First report | Final | No sheet names | Random tie order | Baseline |
|---|---|---|---|---|---|
| Ownership, all owners (1,373 caps on 74 boards) | 73.1% | **74.7%** (per board 70.5%) | 62.9% | 61.3% | 38.0% |
| … rail-group caps paired by nearest load | | **76.0%** | 64.3% | 64.0% | |
| Pin pairings over 10 mm | 33.2% of 1,457 | **11.6%** of 284 | 14.5% | 12.1% | |
| Hot loops below the 5th percentile of random (64) | 76.6% | **81.3%** (below 1st: 40.6%) | 73.4% | 71.9% | 5% |
| Power-path loops below the 5th percentile (21) | | 52% | | | 5% |
| Crystal to IC (31) | 4.7 mm | 4.7 mm; 87% within 12 mm | | | |
| TVS nearer the connector (269 chains) | 60.2% | 59.5% | | | 50% |

- **Rail groups:** 8 on 5 boards cover 62 caps. Reference-order allocation got 61% of them right; nearest-load pairing gets 90%.
- **Power paths by class:** loops of load switches, muxes, reverse-polarity FETs and the BMS bank sit at percentile ≤ 0.02. Low-side and ideal-diode paths sit at 0.14–0.15. Their caps sit at the rail's source, or the loop runs through a cable.
- **Calibration:** ownership probabilities are monotone but underconfident below 0.7. Caps reported below 0.5 are right 55% of the time; 0.5–0.7, 77%; ≥ 0.9, 92%.
- **Variants that did not help:** a rank-order term, a penalty on a cell's second capacitor, quotas scaled under shortage, "ICs before LEDs" on ties, and a first-capacitor round for converters (beaten by donation).

### 4.2 Manual audit [I]

These counts are structure-level. Dev boards are training data; held-out boards were audited with the code frozen.

| Structure | Dev, 10 boards (after fixes): P / R | Held-out, 3 boards (before fixes): P / R |
|---|---|---|
| Commutation cells | 10/10, 10/10 | 2/4, 2/4 |
| Crystals, feedback dividers, antennas | 11/11, 11/11 | 3/3, 3/3 |
| Kelvin shunts | 8/8, 8/8 | 0/0, 0/1 |
| Protected chains | 12/14 | 18/18 |
| Decap groups (IC, rail) | 47/48, 47/50 | 25/25 |
| Rails | 50/50 (3 voltages, 3 sources wrong) | 27/27 (same) |
| Sensitive nets | not counted | 13/15, 13/33 |

### 4.3 Pin types that contradict names [C][I]

Deleting every pin type keeps 99.45% of net roles, a rail-set Jaccard of 0.93 and a decap-group Jaccard of 0.93. Before the name-first rules these were 0.993, 0.92 and 0.90. Flipping types against names (supply names typed input, EN and VIN+ typed power_in) now changes nothing measurable (0.998–1.0, was 0.95 on rails). That test is partly circular.

Six held-out boards were checked: the three above and three never opened before, chosen for contradicting types. They hold only 4 IC pins typed against their name, and all 4 are handled now; 3 were handled before. The commoner failures were missing types and unparsed names: an ADV7280 with every pin `passive` and an `MVDD` supply, `V_{DD}` markup, module supply pins wired straight to a header. Each was fixed with a test.

## 5. Failure modes that matter for placement

1. **Ownership among unlike loads on one rail stays a guess.** Without sheet names it drops to 63%. Five bucks sharing six caps cannot be told apart by the netlist. Keep p < 0.7 soft.
2. **Unnamed rails have no voltage.** Excitation V is null where the input rail has no name, part number or rating. Treat null as "unknown, possibly high", not zero.
3. **Power-path currents are upper bounds.** A load-switch rating (24 A for an NCP45560) or a package class beats a 50 mV shunt estimate under the agreed order. Use `I_belief.interval`, not the point value, for thermal margins.
4. **Discrete power paths need recognisable parts.** Small-signal FET families are skipped unless both ends are rails. A FET straight across a regulated rail reads as a crowbar.
5. **Names the rules do not parse** (`VBUS-In`) and pins whose direction only the type gives (a charger's VBAT) still depend on library types.
6. **Protection order is a weak label.** Only 60% of human layouts put the TVS nearer the connector than the IC. Enforce connector → TVS → IC anyway.

## 6. Recommendations for our system

- **Seed the placer from `placement_order` and weight terms by confidence.** Hot loops and crystals can act as hard groups.
- **Read pairing literally.** Pull a cap to a named pin only for `pairing: 'pin'`. For `nearest_pin`, use the nearest of the group's power pins. For `nearest_load` and inside a `rail_group`, use the nearest load on the rail. Treat caps with `caps_p` < 0.5 as unowned.
- **Treat power paths like cells, one level down.** Keep `caps_in`, the pass elements and `caps_out` tight, size copper for `I_belief`, and spread the heat of `heat_source` entries.
- **Report "unknown" upward.** A null voltage or an unknown source goes to the LLM layer as a question ([design-understanding-pipeline](../llm/design-understanding-pipeline.md)).
- **Re-run both evaluations after every rule change** (a few minutes for 112 boards). A rule must not lower ownership, cell compactness or crystal distance.

## Conflicts and open questions

- **Schematic order carries about 12 points of ownership accuracy.** Only a schematic or a datasheet's per-pin recommendation can split one rail's caps between unlike ICs.
- **Hot-loop and path membership come from topology tables.** Simulating the schematic ([schematic-to-physics](schematic-to-physics.md)) would measure them.
- **Held-out recall rests on 6 boards.** A blind audit of the newer `kae-work-v2` suite would tighten the cell and sensitive-net figures.

## Sources

- Research note: [comprehension_audit.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/comprehension_audit.md) (weak labels, variants, audits, pin types, power paths, rail groups, suite table).
- Code: `kae/src/kae/circuit/`; tests `kae/tests/test_circuit_*.py`; evaluations [`cm_comprehension_eval.py`](../../../tools/research/physics/cm_comprehension_eval.py), [`cm_pin_type_robustness.py`](../../../tools/research/physics/cm_pin_type_robustness.py).
- Topology tables: [hot-loops](../rules/power/hot-loops.md); interface impedances: `docs/topics/rules/interfaces/`.

See also: [net-role-classification](../llm/net-role-classification.md), [suite-physics-results](suite-physics-results.md), [physics-core-v2-api](physics-core-v2-api.md), [pdn-and-commutation](pdn-and-commutation.md).
