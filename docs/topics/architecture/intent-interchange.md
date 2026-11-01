# Intent interchange: how operating intent reaches the evaluator

**TL;DR**
- **Industry has no standard file for operating intent.**
  - Load currents, tolerances, regulator setup and bus speeds are typed into each analysis tool's setup (Altium PDN Analyzer, Cadence PowerTree feeding PowerDC, HyperLynx DRC object lists).
  - Constraint rules live in vendor constraint managers.
  - Exchange formats carry stackup, impedance and pairs only.
  - Chips have SDC and IEEE 1801 (UPF); PCBs have no counterpart.
- **Our corpus states almost none of it** [M]. Over 300 random boards:
  - declared stackup 32%;
  - custom netclasses 23%;
  - part numbers on footprints 14%;
  - SPICE fields 7%;
  - `.kicad_dru` 3%;
  - currents, frequencies and bus modes: essentially none.
- **We use a SPICE testbench beside the KiCad project.** Plain ngspice SPICE plus a few `*@` annotations, naming pins and nets as KiCad does (`<U5.12>`, `<+3V3>`). It holds:
  - sources and loads;
  - parameter intervals with citations;
  - `.meas` requirements with their sources.
  
  The KiCad project stays the source of truth for parts and nets.
- **Twenty candidate formats were checked; none replaces it** (§3). The only format whose requirements both run and re-run with layout parasitics is SPICE. Borrowed features:
  - atopile's requirement fields;
  - PolymorphicBlocks' interval checks;
  - Verilog-A (through ngspice OSDI) for behavioural part models.
- **KiCad 10 integrates today; KiCad 11 needs a port.**
  - `kicad-cli` exports SPICE and netlists from modern schematics and upgrades old boards.
  - KiCad 5 schematics cannot be read from the CLI.
  - KiCad 11 removes the SWIG Python bindings that about 15 of our modules use.

Tags: [P] primary, [S] secondary (search summaries of vendor documentation), [V] vendor, [I] inference, [M] measured in this repo, [C] checked hands-on here. Evaluation semantics: [functional-evaluation](../physics/functional-evaluation.md). Code: [functional-evaluator](functional-evaluator.md).

## Key facts

### 1. Where intent lives in industry

| Channel | Carries | Does not carry | Tag |
|---|---|---|---|
| KiCad netclasses and directive labels; component classes (KiCad 9); `.kicad_dru` (length, skew, diff-pair gap; time domain in KiCad 10); stackup; `Sim.*` fields | widths, clearances, pairs, lengths, skews, dielectrics, SPICE model bindings | currents, frequencies, interface types, tolerances | [P] [constraint-models-compared](constraint-models-compared.md) |
| Altium PDN Analyzer setup | sources (DC, SMPS or linear VRM) and loads (current sinks) with ±% voltage limits | anything outside the analysis | [S] [Altium guide](https://altium.com/documentation/altium-nexus/pdn-analyzer-example-guide-v2) |
| Cadence Sigrity PowerTree → PowerDC | sources, sinks, models, decoupling, target impedance, captured at the schematic stage | signal intent | [S] [PowerDC datasheet](https://ema-eda.com/wp-content/uploads/2024/01/sigrity-powerdc.pdf) |
| Cadence Constraint Manager | impedance, pin-pair delay, match groups, max crosstalk, return-path DRC | currents | [S] [constraint-models-compared](constraint-models-compared.md) |
| Siemens HyperLynx DRC | parametric rules (nets crossing gaps, reference changes) on object lists from the layout tool's classes | operating conditions | [S] [Siemens blog](https://blogs.sw.siemens.com/electronic-systems-design/?p=6176) |
| IPC-2581C | stackup, impedance, diff pairs, net class, intended shorts; KiCad exports fields only as unitless text | clearance, length, placement, conditions | [P] [constraint-ir](constraint-ir.md) |
| ODB++ 8.1 | `.net_test_current`, `.net_test_voltage`, `.eclass_rise_time`, `.eclass_voltage_swing`, `.eclass_impedance` (single nominal values) | intervals, requirements | [P] [ODB++ spec](https://odbplusplus.com/wp-content/uploads/sites/2/2024/08/odb_spec_user.pdf) |
| IBIS, IBIS EMD (IBIS 7.1), SPICE, Touchstone | buffer edges and drive; interconnect models | system intent | [S] [ibis.org EMD](https://www.ibis.org/interconnect_wip/emd_intro.docx) |

### 2. What our corpus carries [M]

From 300 random boards of the 14,597:

| Channel | Boards |
|---|---|
| KiCad 5-era files | 33% (footprints carry no symbol fields) |
| custom netclass | 23% |
| declared stackup | 32% |
| part-number field on footprints | 14% |
| `Sim.*` fields | 7% |
| `.kicad_dru` | 3% |

Other facts:
- **Schematics:** fetched for 8,100 boards; pin types extracted for 6,748 ([pintypes.py](../../../tools/kaeres/pintypes.py)).
- **Empty values:** some boards carry no component values in the footprints at all (for example exports from other tools). Their values come from the schematic.

### 3. Formats evaluated

Twenty formats were checked by three research passes against the same criteria:
- connectivity and part binding;
- conditions as intervals with sources;
- requirements with units;
- execution;
- re-execution with layout parasitics;
- effort to generate from our corpus;
- LLM authoring;
- licence;
- reach beyond circuits.

| Format | Best at | Why it is not the carrier | Kept |
|---|---|---|---|
| Annotated SPICE (ngspice) | runs requirements; takes R, L, K and C parasitics; KiCad exports it | names need care (§5) | **the carrier** |
| Zener / `pcb` (Diode Computers, MIT) | Starlark parts with range literals; emits SPICE | never compares results to bounds; no parasitics; refuses KiCad 5 | range syntax |
| atopile | interval parameters, `assert`; an unmerged branch adds ngspice-checked requirements | no KiCad importer; solver only in releases | requirement fields (min/typ/max, analysis, measurement, justification) |
| PolymorphicBlocks (edg) | ports with voltage and current ranges, checked per link | no simulation | interval semantics |
| SKiDL | Python netlists, SPICE through InSpice | no units or intent | — |
| tscircuit / Circuit JSON | `pcb-spice-pipeline`: FastHenry and FasterCap on routed copper, then ngspice | signal channels only, unpublished, JSON for tools | extraction method to compare against |
| JITX | SI constraints | proprietary; no rail model | — |
| Modelica (+ Modelica_Requirements) | units, `assert`, thermal and mechanical domains | no KiCad path; weak at fast switching; requirements library unfinished | later electro-thermal option |
| SysML v2 | requirement definitions with ISQ units | evaluates nothing itself | possible export |
| Verilog-A / AMS | behavioural models | not a netlist format | inside SPICE via OSDI |
| KiCad netlist / schematic | binding, `Sim.*` models, text directives exported verbatim | conditions only as free text; a schematic is hard to write from scratch | importer; designer-facing store |
| ODB++, IPC-2581C, EDIF, ReqIF, FMI, VHDL-AMS | various | no intervals or executable requirements | — |

### 4. The workflow

**A board designed in KiCad:**

```
KiCad project (schematic + board)                       source of truth for parts and nets
  ├─ design: board netlist + passives' values (schematic when the board has none) + Sim.* models
  └─ testbench file <project>.tb.cir                      written by code, a human or an LLM
        sources, loads, .param + *@range, .meas + *@require, with citations, in KiCad's names
            │
our program: deterministic fixes (value suffixes, stand-ins for unmodelled ICs, interval priors)
  → simulator decks with safe names → ngspice, ideal and routed (extracted copper), every corner
  → verdicts, capability, the layout's effect, and questions (inputs whose range flips a verdict)
            └→ questions go back to the LLM or the human, who edit the testbench
```

- **The LLM never sees escaped names.** The program maps KiCad names to safe nodes and translates results back.
- **Facts about one part go into KiCad symbol fields,** so they stay with the part.
- **Facts about operation go into the testbench.** It is a separate file, because the exported design changes with every schematic edit.

**A design the LLM starts from scratch:** the LLM writes one deck with both the circuit and the testbench. The program turns the circuit into the KiCad project and keeps the rest as the testbench. From there the flow is the same.

**Our corpus:** code writes a default testbench for every board (no LLM). An LLM researches only the questions, on a small subset; see [functional-evaluation](../physics/functional-evaluation.md) §6.

### 5. Facts that shape the format [C]

**ngspice 44.2** (in the KiCad 10.0.7 container):
- folds names to lower case: `CLK` and `clk` merged;
- a top-level node `x1.n` shorts silently to subcircuit X1's internal node `n` (5.0 V where 0 V was due);
- `10uF 35V` reads as 35 F;
- a failed `.meas` or a malformed line still exits 0;
- there is no `.step`; corner sweeps run as separate decks.

So pins and nets are written `<…>` (illegal in node names, so never passed through unresolved). The program generates every simulator name, and a missing measurement is a failure.

**`kicad-cli` 10.0.7:**
- exports `--format spice` and `kicadsexpr` from KiCad 6+ schematics, with elements named by reference and nodes by net;
- upgrades a 2015 board (`pcb upgrade`);
- returns an empty netlist for a KiCad 5 `.sch`, and fails to upgrade one.

The board's own netlist and our KiCad 5 parser cover those boards.

**KiCad 11:**
- The SWIG `pcbnew` bindings are planned for removal in 11.0 ([KiCad dev docs](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)) and are already gone from nightlies ([devlist](https://mid.mail-archive.com/devlist@kicad.org/msg00846.html)).
- The IPC API (`kicad-python`) gains headless mode, design rules and export.
- A schematic API appears in 11 per third-party projects; not confirmed officially.

## Recommendations for our system

1. Keep the testbench format small: the annotations in [testbench.py](../../../kae/src/kae/sim/testbench.py). Add atopile's requirement fields only when a test needs them.
2. Read values and fields from the schematic through `kicad-cli` (KiCad 6+). For KiCad 5 boards, ask for an upgrade in KiCad, or use the board netlist plus our parser.
3. Port the SWIG `pcbnew` users to the IPC API before KiCad 11. This is separate work, on our path whatever the format.
4. Cache LLM-researched facts per part number, so the cost per board falls as the cache fills.

## Conflicts and open questions

- **Part facts in KiCad fields** (`kae.I_max` on a symbol) versus everything in the testbench. Fields travel with the part; the testbench is easier to review in one place.
- **Whether methods may read the testbench:** servoing needs it; fairness requires that every method gets the same file.
- **The vendor-tool rows are search summaries of vendor documentation;** none of those formats appears in our corpus.

## Sources

- In-repo: 300-board corpus sample (seed 3), 2026-10-27; three research passes and ngspice/kicad-cli checks, 2026-10-28.
- [Altium PDN Analyzer guide](https://altium.com/documentation/altium-nexus/pdn-analyzer-example-guide-v2); [Sigrity PowerDC](https://ema-eda.com/wp-content/uploads/2024/01/sigrity-powerdc.pdf); [Siemens HyperLynx DRC](https://blogs.sw.siemens.com/electronic-systems-design/?p=6176); [ODB++ 8.1u4](https://odbplusplus.com/wp-content/uploads/sites/2/2024/08/odb_spec_user.pdf); [IBIS EMD](https://www.ibis.org/interconnect_wip/emd_intro.docx).
- [ngspice 44 manual](https://ngspice.sourceforge.io/docs/ngspice-44-manual.pdf); [ngspice OSDI](https://ngspice.sourceforge.io/osdi.html); [Xyce reference 7.9](https://xyce.sandia.gov/files/xyce/Xyce_Reference_Guide_7.9.pdf); [KiCad SPICE exporter @10.0](https://gitlab.com/kicad/code/kicad/-/raw/10.0/eeschema/netlist_exporters/netlist_exporter_spice.cpp).
- Hardware-as-code: [Zener](https://docs.pcb.new/pages/spec), [atopile](https://github.com/atopile/atopile), [PolymorphicBlocks](https://github.com/BerkeleyHCI/PolymorphicBlocks), [SKiDL](https://github.com/devbisme/skidl), [tscircuit pcb-spice-pipeline](https://github.com/tscircuit/pcb-spice-pipeline); [Modelica_Requirements](https://github.com/modelica/Modelica_Requirements); [SysML v2 release](https://github.com/Systems-Modeling/SysML-v2-Release).

See also: [constraint-ir](constraint-ir.md), [constraint-models-compared](constraint-models-compared.md), [physics-ir](../physics/physics-ir.md), [part-layout-card](../llm/part-layout-card.md), [schematic-to-physics](../physics/schematic-to-physics.md).
