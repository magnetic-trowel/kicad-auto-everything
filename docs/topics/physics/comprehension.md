# Comprehension: what each part, net and structure is doing

Scope: `kae.circuit`, which reads a `.kicad_pcb` (never positions) and writes the physics brief (roles, structures, confidences); its inference rules and measured accuracy. Not here: schematic simulation -> [schematic-to-physics](schematic-to-physics.md); LLM-side understanding -> [design-understanding-pipeline](../llm/design-understanding-pipeline.md); net-role prior art -> [net-role-classification](../llm/net-role-classification.md).
Keys: kae.circuit, physics brief, kae.brief/1, net role, part kind, commutation_cell, power_path, decap, rail_group, pin_caps, pairing, caps_p, I_belief, R_on_ohm, placement_order, log-odds evidence, pin semantics, capacitor ownership, weak labels, held-out audit, pin-type robustness

Corpus: 112 reference boards, 9,227 parts, KiCad 10.0.7 suite; median runtime 0.1 s/board. Held-out failures come from library typing and unparsed names, not the method: weight every structure by confidence; keep low-confidence ownership soft [I].

Tags: [C] from [`cm_comprehension_eval.py`](../../../tools/research/physics/cm_comprehension_eval.py) and [`cm_pin_type_robustness.py`](../../../tools/research/physics/cm_pin_type_robustness.py); raw evidence, per-board errors, suite table: [comprehension_audit](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/comprehension_audit.md).

## 1. Interface

```python
from kae.board.kicad_file import load
from kae.circuit.brief import build, write
brief = build(load('board.kicad_pcb'))   # JSON-ready dict, schema 'kae.brief/1'
# python -m kae.circuit.brief BOARD.kicad_pcb [-o brief.json] [--no-sheets]
```

| Key | Content |
|---|---|
| `nets` | name → role (ground, rail, switch_node, clock, high_speed, analog, rf, reset, boot, signal, no_connect), subrole, `volts` + `volts_belief`, `source` {kind, `part` uuid, `ref`, `path`}, evidence |
| `parts` | footprint uuid → `ref`, kind, subtype, role, `external`, `P_W`, confidence, evidence |
| `structures` | `id`, `kind`, `confidence`, `evidence`, `priority`; members by footprint uuid, `members_ref` maps back |
| `diff_pairs`, `placement_order`, `summary` | pairs with a Zdiff budget; structure ids by priority; counts, runtime |

| Structure kind | Fields a placer/router reads |
|---|---|
| `commutation_cell` | `class`, `rail`, `sw`, `gnd`, `loop` [[uuid, pad(s)]…] closed on the commutation cap, `caps`, `caps_p`, `excite` {V, I, t_sw_ns, f_sw_Hz}; optional `series_shunt` [uuid], `bootstrap_cap`, `bootstrap_r`, `charge_pump_caps` [uuid], `snubbers` [[r, c]] |
| `power_path` | `class` (load_switch, power_mux, ideal_diode, reverse_polarity, fet_bank, fet_switch), `switches`, `stages` [[uuid]], `controller`, `rail_in`, `rail_out`, `gnd`, `series`, `caps_in`, `caps_out`, `loop`, `group`, `excite` {V, I, I_belief}, `R_on_ohm`, `P_W` |
| `decap` | `ic`, `function`, `rail`, `ground`, `power_pins`, `caps`, `caps_p`, `hf_caps`, `bulk_caps`, `pin_caps` {pin: [uuid]}, `pairing` ('pin', 'nearest_pin', 'nearest_load'), optional `rail_group` |
| `rail_group` | `rail`, `ground`, `loads` [uuid], `caps` [uuid], `pairing` 'nearest_load', `basis` |
| others | `crystal`, `oscillator`, `connector_chain`, `victim` (feedback, sense, divider, analog, crystal), `antenna`, `heat_source` {part, P_W, P_W_belief}, `thermal_victim` |

Position independence is tested: moving every footprint and pad at random returns an identical brief.

## 2. The evidence model

- Confidence = logistic(prior + Σw), clipped to [0.02, 0.98]; w are natural-log-odds weights: STRONG 3.0, MODERATE 1.5, WEAK 0.7, negative for counter-evidence.
- Names outvote pin types: a library that types VIN as `input` or EN as `power_in` no longer changes the brief.
- Facts are kept as checkable text ("power_in pins on 2 parts (U3.VDD)"), from 8 sources: refdes prefix, lib id, value and fields, pin function, pin type, topology, net class, sheet. No source decides alone; each rule names its counter-evidence.
- Part kinds: softmax with an *unknown* score 1.0; 4 of 9,227 suite parts end unknown.
- Budgets are E5 Beliefs with a basis (`f_sw = 1.1 MHz for AP63203`).

**Pin semantics, name first.** Each pin reads as ground, supply, supply output, analog, signal or nothing; first match wins:
1. Ground names, except V−/VSS on a negative rail.
2. Differential-input names (VIN+, IN−, SENSE+) on non-power ICs → analog.
3. `power_out` on a regulator, PMIC or charger → output, unless named VIN or IN.
4. Supply names (VIN, VDD, AVCC, MVDD, VBAT, `3V3`) → supply.
5. Internal regulator outputs (VCAP, REG18, VBUS_OUT) and regulator OUT pins → supply output.
6. Logic names (GPIO, EN, TXD, SCL, PA3) → signal.
7. Then pin type, then weak names.

KiCad markup is stripped first (`V_{DD}` → VDD).

## 3. Inference rules

### 3.1 Part kinds and net roles

Part kinds from lib ids (`R_Shunt_*_Kelvin`, `Crystal`), part-number families (USBLC6, BQ769xx, GAQY), values as quantities (`4u7`, `0R05`, `16V` on a diode), pin sets (G/D/S, A/K), refdes prefixes. A pad census rules out electrical kinds for logos and holes. Package codes are stripped from values first (`10k/0402` ≠ 0.04 Ω).

| Role | For | Against |
|---|---|---|
| Ground | names, ground pins, many 2-pin caps; battery negative net-tied to ground | splits stay distinct (analog, power, isolated, chassis); Kelvin lines tied to ground keep their role |
| Rail | supply pins, regulator/inductor outputs, caps to ground, pours, rail names; module supply pin wired to a connector pin | control suffix (`12V0_OUT_EN`); sense input with no supply pin; logic-only IC pins |
| Switch node | inductor between an IC switch pin or FET pair and a decoupled rail | FET pair without power-stage evidence = logic gate |
| Clock | crystal or oscillator terminals | pin name alone (PC14, XTAL_32K on an ESP32-C3 GPIO) |
| Diff pair | complementary names on a common IC or connector; MIPI on a camera FPC | LED across the pair; crystal XTALP/XTALN |
| Analog, reset, boot | ADC, sense, reference names; amplifier/AFE inputs; RST, BOOT pins | logic and bridge-driver pins; a converter's BST net |

- **Rail source**, first match: battery, dev module 3V3 pin, input-jack supply pin, IC internal output, bridge rectifier, regulator or load-switch output, inductor, series path (fuse, bead, ≤ 1 Ω, closed jumper, diode, four-terminal shunt) through middle nets, any connector, unknown. A diode from a low-side switch drain is a flyback clamp, not a source. Two rails joined by a fuse that name each other: connector side wins.
- **Voltage**, in order: name, regulator part number, USB/battery defaults, core-regulator table, inheritance through series parts (−0.4 V per diode), lowest capacitor rating ÷ 1.6.

### 3.2 Commutation cells

Topologies from [hot-loops](../rules/power/hot-loops.md): buck (C+ → high side → SW → low side or catch diode → PGND → C−), boost (closed on C_out), 4-switch buck-boost as two half-bridges, integrated and discrete bridges, regulator modules.
- Buck vs boost: vote over input-pin side, high-side FET, catch diode, rectifier direction; part tables break ties.
- Loop terminals exclude EN, MODE, PG pins tied to the rail and a PMIC's VSYS output on the input net.
- Two-step members: `series_shunt` (shunt between input cap and switch), `bootstrap_r` (resistor between BST pin and its cap), `charge_pump_caps` (bridge-driver flying and storage caps), `snubbers` (RC from SW to ground or rail).

### 3.3 Capacitor allocation and pin pairing

Allocation is joint per rail over every rail-to-ground capacitor:

| Owner | Quota | Prefers |
|---|---|---|
| Commutation cell | 2 | ceramics ≤ 1 µF unless loads need every one |
| Load (IC, module, LED) | 1 per power pin | ceramics ≤ 1 µF |
| Regulator pin | 1 | larger caps |
| Split supply (V+ to V−) | 1 per V+ pin | caps straight across the rails |
| Connector entry; buck output / boost input | their bulk caps (polarized ≥ 10 µF; ≥ 10 µF) | those only (exclusive) |

- Score = schematic affinity (same sheet +2, other −1, same 100-block of references +1.5) + class preference. Greedy with quotas; ties fill owners in reference order. Leftovers → near-best owner with fewest caps per pin. A converter with no cap takes another converter's second. `caps_p` = softmax of the same scores.
- **Pairing only where the netlist decides it.** `pin_caps` names a pin only for a single-pin group, small ceramics within quota, p ≥ 0.5 (`pairing: 'pin'`). Several pins on one net → `nearest_pin` (placer pairs each cap with the nearest). Entry bulk → `nearest_load`.
- Three rule errors fixed (round-robin pin assignment; module `3V3` pin read as regulator output; leftovers piling on the first consumer): pairings with human distance > 10 mm 33.2% → 11.6% [C].

### 3.4 Power paths without switching

`power_path` covers integrated load switches, eFuses, muxes, and discrete MOSFETs: equal-D/S banks chained through back-to-back middle nets, reverse-polarity and ideal-diode PMOS, low-side switches.
- Direction from gate drive: gate at ground, PNP mirror or ideal-diode IC → body diode forward (D in); switch drive → PMOS source in.
- Excluded: totem poles (logic gates, half-bridges), FETs straight across a regulated rail (crowbars).
- Multi-input classes: one path per input, shared `caps_out`; `group` = mux IC uuid or `or:<rail_out>`.
- Loop: C_in+ → pass element(s) → C_out+ → C_out− → C_in−. Low-side paths close through the load terminals (connector's two pins, or twin pads) and the supply cap.
- Caps: the path IC's own, unclaimed and entry caps first; a load's cap only to close the loop.
- Current `I_belief` (E5, interval [I/3, I]): fuse rating > load-switch table > shunt at 50 mV full scale > connector or package class; capped by package dissipation.
- Heat: `R_on_ohm` (E5) from part table or package class; each pass element is a `heat_source` with P = (I/n)²·R_on.

### 3.5 Rail groups and other structures

- **Rail group:** ≥ 6 identical loads on one rail, or ≥ 4 if the rail has fewer caps than loads; identical = same kind and value (rotated footprint variants count). Members' decaps carry `rail_group` and `pin_caps: {}`; placer pairs each cap with its nearest group load.
- Others: crystal circuits (oscillator pins, load caps, series and feedback R); feedback dividers (Vref table → implied Vout); measurement dividers (not logic straps); shunts (with amplifier, Kelvin type); protection chains (connector → TVS → series parts → first IC pin); antennas (with match networks); heat (conversion loss, LDO drop, class estimates); thermal victims (crystals, electrolytics, sensors).

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

Weak labels from the human placement on 112 boards, manual audit (10 dev + 3 held-out boards), pin-type robustness -> [kae-comprehension-brief](../../research/placement/kae-comprehension-brief.md#measured-accuracy). Summary: hot loops and crystals sit where the brief says; ownership among unlike loads on one rail is the weak part (§5).

## 5. Failure modes that matter for placement

| # | Failure | Placer action |
|---|---|---|
| 1 | Ownership among unlike loads on one rail is a guess: 63% without sheet names; 5 bucks sharing 6 caps are indistinguishable from the netlist | keep p < 0.7 soft; treat `caps_p` < 0.5 as unowned |
| 2 | Unnamed rails have no voltage: excitation V null without name, part number or rating | treat null as "unknown, possibly high", not 0; send upward to the LLM layer as a question ([design-understanding-pipeline](../llm/design-understanding-pipeline.md)) |
| 3 | Power-path currents are upper bounds: a load-switch rating (24 A for NCP45560) or package class beats a 50 mV shunt estimate | use `I_belief.interval`, not the point, for thermal margins |
| 4 | Discrete paths need recognisable parts: small-signal FET families skipped unless both ends are rails; FET across a regulated rail = crowbar | — |
| 5 | Unparsed names (`VBUS-In`) and pins whose direction only the type gives (charger VBAT) still depend on library types | — |
| 6 | Protection order is a weak label: only 60% of human layouts put the TVS nearer the connector than the IC | enforce connector → TVS → IC anyway |

Placer use:
- Seed from `placement_order`; weight terms by confidence; hot loops and crystals may be hard groups.
- Read pairing literally: named pin only for `pairing: 'pin'`; nearest group power pin for `nearest_pin`; nearest load on the rail for `nearest_load` and inside a `rail_group`.
- Power paths are cells one level down: keep `caps_in`, pass elements, `caps_out` tight; size copper for `I_belief`; spread `heat_source` heat.
- Re-run both evaluations after every rule change (minutes for 112 boards); a rule must not lower ownership, cell compactness or crystal distance.

## Open questions

- Schematic order carries ~12 points of ownership accuracy; only a schematic or a datasheet's per-pin recommendation can split one rail's caps between unlike ICs.
- Hot-loop and path membership come from topology tables; schematic simulation ([schematic-to-physics](schematic-to-physics.md)) would measure them.
- Held-out recall rests on 6 boards; a blind audit of the `kae-work-v2` suite would tighten cell and sensitive-net figures.

## Sources

- [comprehension_audit.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/comprehension_audit.md) (weak labels, variants, audits, pin types, power paths, rail groups, suite table).
- Code: `kae/src/kae/circuit/`; tests `kae/tests/test_circuit_*.py`; evaluations above.
- Topology tables: [hot-loops](../rules/power/hot-loops.md); interface impedances: `docs/topics/rules/interfaces/`.
- Related: [suite-physics-results](suite-physics-results.md), [physics-core-v2-api](physics-core-v2-api.md), [pdn-and-commutation](pdn-and-commutation.md).
