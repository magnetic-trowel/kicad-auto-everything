# kaesynth: from a product brief to a checked KiCad schematic and placement intent

`kaesynth` is the front of the pipeline. A person describes a product, an LLM writes
`designs/<slug>/design.py`, and `kaesynth build` turns it into:

| Output (`designs/<slug>/out/`) | What it is |
|---|---|
| `<slug>.kicad_pro`, `<slug>.kicad_sch`, `<block>.kicad_sch` | KiCad 10 project: a root sheet plus one hierarchical sheet per block, net classes, lib tables |
| `kaesynth.kicad_sym` | Project symbols: generated IC symbols and renumbered transistor symbols |
| `<slug>.kicad_dru` | Custom DRC rules: clearance and creepage between isolation domains |
| `intent.yaml` | `pcb-intent/0.2` placement intent for the placer/router: board, domains, barriers, net classes, relations |
| `netlist.json` | The IR netlist, every pin with its net |
| `bom.csv` | BOM grouped by MPN, with lifecycle and second source |
| `report.md` | Requirements, questions, hazards, calculations, findings, ERC, parity |
| `findings.json`, `erc.json` | Machine-readable check results |

Research behind the design: [schematic-generation-landscape](../docs/topics/synthesis/schematic-generation-landscape.md),
[part-selection-and-verification](../docs/topics/synthesis/part-selection-and-verification.md),
[constraint IR](../docs/topics/architecture/constraint-ir.md),
[relations, not coordinates](../docs/topics/llm/interfaces-relations-vs-coordinates.md).

## Setup and use

```bash
bench/scripts/setup.sh --no-freerouting   # KiCad 10 (+ apt install kicad-symbols kicad-footprints if missing)
cd synth && uv venv .venv && . .venv/bin/activate && uv pip install -e '.[test]'
kaesynth build ../designs/<slug>/design.py -v      # checks + KiCad files + ERC + parity
kaesynth sym 'Relay:.*G5LE'                        # search symbols; `kaesynth sym Lib:Name` prints pins
kaesynth fp 'TerminalBlock_Phoenix:.*5.08'         # search footprints; `kaesynth fp Lib:Name` prints pads
pytest tests                                        # KiCad tests skip without kicad-cli
```

`build` exits non-zero while any unwaived error remains. Iterate until it is clean, then read
`report.md`: warnings are things a reviewer will ask about.

## Pipeline and gates

1. **Brief → requirements.** `require`, `assume`, `question(blocking=...)`, `hazard(...)` records
   live in `design.py`. An unanswered blocking question marks the build "not ready for fabrication".
2. **Architecture.** Blocks (one schematic sheet each), voltage domains, barriers.
3. **Parts.** `PartDef`s with MPN, symbol, footprint, pins, ratings and `source=` provenance.
4. **Circuit.** Nets with domain, voltage range, current, kind. Every pin connected or `nc_pins(..., reason=)`.
5. **Checks** (deterministic, pin-level messages; table below).
6. **Emit + KiCad gates:** `kicad-cli sch erc` and a **netlist round trip** — the schematic KiCad
   reads must be pin-for-pin identical to the IR. Then a static lint of the `.kicad_dru`
   (kicad-cli 10.0.7 ignores bad rules silently) and a DRC smoke run.

ERC-clean is a low bar ([evidence](../docs/topics/synthesis/part-selection-and-verification.md)):
the design-level checks and an independent review are what catch wrong designs.

## Writing `design.py`

```python
from kaesynth import Design, Hole, Isolation, PinDef, Ratings, VLimit
from kaesynth.lib import C, IC, LED, NMOS, R, Conn, Fuse, PINMAP_SOT23_FET

def build():
    d = Design("my-board", title="...", brief="<the user's words>")
    d.require("REQ-1", "Survive 40 V load dump", value="40 V, 400 ms", source="ISO 16750-2", verify="bench")
    d.question("Q-1", "Which battery chemistry?", blocking=True, default="LFP")
    d.hazard("HZ-1", "Short on output harness", mitigation="fuse at battery end", parts=["F1"], single_fault_safe=True)

    # Domains: every net belongs to one. `ref` is the domain's 0 V net.
    d.net("GND", domain="LV", v=0, kind="ground")
    d.domain("LV", ref="GND", kind="selv")
    d.net("+12V", domain="LV", v=(9, 16), kind="power", i_max=2, external=True, threats=("reverse_polarity", "overcurrent"))
    ...
    blk = d.block("input", title="12 V input protection")
    f = blk.add(Fuse(3, 32, "Fuse:Fuse_1206_3216Metric", mpn="...", datasheet="..."), ref="F1")
    sw = blk.net("SW", v=(-0.7, 16), kind="switching", i_max=2)    # local to the block
    d.nets["+12V"].connect(j[1], f[1])
    ...
    d.place.edge(j, "west"); d.place.hot_loop([u["VIN"], cin[1], cin[2], u["PGND"]])
    d.board(width_mm=60, height_mm=40, layers=2, holes=[Hole(3.5, 3.5, 3.2)])
    return d
```

### Domains and voltages (what the rating checks run on)

- `d.domain(name, ref=<net>)`. If `ref` is a net *of this domain* (with `v=0`), the domain is a
  **root**: galvanically separate from other roots. If `ref` is a net of *another* domain, the
  domain floats on it — e.g. battery k of a series stack is `d.domain("B3", ref="B2_POS")`.
- Every net gets `v=(min, max)` in volts relative to its domain's ref (peak for AC: 120 Vrms
  mains is `(-170, 170)`). The checker computes the worst voltage between any two nets by
  summing ranges along the domain chain, so stacked batteries are exact, not interval-blown.
- Envelopes are conservative. When a part can never see the full envelope difference (a shunt,
  an LED that cannot be reverse biased), declare `blk.add(part, v_across=0.1)` and say why in a comment.
- Anything connecting two **roots** must declare `Ratings(isolation=[Isolation(a_pins, b_pins,
  v_iso_rms, grade, v_work_rms, creepage_mm)])`, and a `d.barrier(a, b, grade, v_work,
  creepage_mm, clearance_mm, standard, v_test_rms, source)` must exist. Spacing numbers come from
  the standard's tables (cite them in `source`); the framework does not invent them.
- `d.barrier` also works between non-root domains (functional spacing, e.g. relay contacts vs
  line); `d.place.separate(a, b)` turns it into a placement relation; the `.kicad_dru` carries it.

### Parts

- **Library symbol** (`symbol="Lib:Name"`): pins come from KiCad. Prefer this for passives,
  connectors, relays and anything KiCad has. Check pins with `kaesynth sym Lib:Name`.
- **Generated symbol** (`IC(mpn, pins=[PinDef(number, name, type, side=None), ...], footprint=...)`):
  for ICs; pin numbers and names from the datasheet pin table. Types: `input output bidirectional
  tri_state passive power_in power_out open_collector open_emitter no_connect free`.
- **Transistors** from `lib.NMOS/PMOS/NPN` need `pinmap=` from the datasheet (KiCad's generic
  symbols use letter pins); there is no default.
- `source={"pins": "...", "pinmap": "...", "ratings": "..."}` and `datasheet=` on every non-generic
  part: datasheet revision, page, table. Missing provenance is a warning a reviewer will chase.
- Ratings: `v_max` (2-terminal), `limits=[VLimit(("D",), ("S",), 100)]`, `i_max` / `pin_i_max`,
  `p_max`, `polarity=("1", "2")`, `isolation=[...]`. Set `p_diss=` on parts from your calculations.
- Generic passives (`R`, `C` without MPN) are allowed; resistors default to thick-film package
  ratings, capacitors need a voltage rating. Pass an MPN and real ratings for anything stressed.
- Multi-unit library symbols (op-amps, relays with separate coil units) are placed unit by unit.
- `lifecycle="active" | "nrnd" | "obsolete"`, `second_source="..."` feed the BOM checks.

### Nets

`kind`: `signal power ground hv mains switching sense analog high_current pe clock diff`.
`external=True` for nets leaving the board; `threats=("esd", "surge", "overcurrent",
"reverse_polarity", "load_dump", "overvoltage")` require a protector of the matching category on
that net. `i_max` drives current checks and net-class track widths.

### Placement relations (`d.place.*`; ordinal magnitudes, never coordinates)

`group(block)`, `region(block, "north")`, `near(a, b, "tight|close|loose")`, `far(a, b)`,
`hot_loop([pins...])`, `edge(part, "north|south|east|west|any")`, `orient(part, facing)`,
`separate(domA, domB)`, `keepout(obj, what, layers)`, `thermal(part, watts, sink)`,
`array(parts, axis)`, `align(parts, axis)`, `symmetric(pairs, axis)`, `side(part, "top|bottom")`,
`custom(kind, ...)` for anything else. Objects are parts, pins (`u["VIN"]`), blocks or domains.
The build adds inferred relations (block groups, decoupling caps next to their IC pin, external
connectors on an edge) marked `source: auto`. `d.board(...)` records outline, layers, holes,
height limits, enclosure and coating.

### Calculations and waivers

`d.calc(name, value, unit, expr=, note=, limit=, op="<=")` records a calculation in the report
and fails the build if the limit is violated. `d.waive(check, regex, reason, by)` accepts a
finding on the record; never waive an error you have not understood.

## Checks

| Check | Severity | Catches |
|---|---|---|
| `conn.unconnected_pin`, `conn.single_pin_net`, `conn.nc_without_reason` | error/warn | unaccounted pins, dangling nets |
| `erc.output_conflict` | error | two push-pull outputs on one net |
| `net.no_domain`, `domain.ref`, `net.no_voltage` | error/warn | nets the voltage model cannot place |
| `rating.voltage`, `rating.polarity` | error/warn | worst-case voltage vs `v_max`/`limits`, reverse-biased electrolytics |
| `rating.current`, `rating.power`, `rating.dc_bias` | error/warn | net current through series parts, dissipation, MLCC DC bias |
| `domain.crossing`, `barrier.*` | error | non-isolating parts across roots; isolation grade, withstand, working voltage, package creepage |
| `lib.*` | error/warn | missing symbols/footprints, symbol pins without pads, hidden power pins |
| `part.no_datasheet`, `part.no_provenance`, `bom.*` | warn/error | unsourced facts, missing MPN, NRND/obsolete |
| `protect.threat`, `protect.entry_fuse` | error/warn | external wires without the protector their threat needs |
| `calc.limit`, `hazard.*`, `intent.blocking_question`, `place.*` | error/warn/info | design calculations, hazard mitigations, open questions, relation sanity |
| `kicad.erc.*`, `kicad.netlist_roundtrip`, `kicad.dru_parse` | error/warn | the emitted files, as KiCad reads them |

## Known limits

- Schematic layout is label-based (exact by construction, readable, not pretty): parts cluster
  around the multi-pin part they connect to. No wire routing between symbols.
- No distributor lookup yet: MPNs and lifecycle are what the design says, so `source=` and an
  independent review carry the weight. Part cards should move to a resolved catalog.
- No SPICE yet. Typed interfaces (I²C pull-ups, address uniqueness) are not modelled.
- `kicad-cli` 10.0.7 segfaults running DRC with `creepage` rules on a board without an
  Edge.Cuts outline; the DRC smoke run adds one.
- Output targets KiCad 10 (`20260306`); KiCad 9 cannot open it.
