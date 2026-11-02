<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Board spec (kae.board-spec/1): what a model states about a board for kae's evaluator

kae is not an LLM: it reads numbers. A model (or a designer) reads a board's summary
(`board_summary.py`) and writes one spec; `intent_from_spec.py` turns it into the evaluator's operating
facts and the board's `kae.intent`, checking every id against the board and every number against
physical bounds. This file is the instruction given to the model.

## Input

`SUMMARY.json`: `source` (repo, path, tags), `parts` (ref, kind, role, value, lib_id), `rails`
(net -> volts as kae inferred it), `sections` (ids such as `cell:buck:U2`, `victim:feedback:U2.4`,
`ant:U3`, `decap:...`, `chain:J1:...`), `summary`.

## Output: exactly this JSON

```json
{"schema": "kae.board-spec/1",
 "purpose": "one line: what the board is and does",
 "rails": [{"net": "<a net from rails or sections>", "V_nom": 3.3, "tolerance_pct": 5,
            "ripple_max_mV": 50, "I_max_A": 0.5, "source_ref": "<ref of the regulator/connector feeding it>",
            "regulator": "linear|switching|none", "from_net": "<the regulator's input rail, or null>",
            "eta": [0.85, 0.92],
            "critical": false, "basis": "datasheet|typical|guess", "why": "..."}],
 "loads": [{"ref": "<IC/module ref>", "rail": "<net>", "I_typ_A": 0.02, "I_max_A": 0.15,
            "T_max_C": 125, "basis": "...", "why": "..."}],
 "converters": [{"cell": "<a cell:... section id, exactly>", "V_in_V": 12, "V_out_V": 5,
                 "f_sw_Hz": 500000, "I_out_A": 1.0, "t_edge_s": 5e-9, "switch_V_max_V": 30,
                 "basis": "...", "why": "..."}],
 "sensitive": [{"victim": "<a victim:... section id>" , "ref": "<or a part ref>",
                "what": "feedback|ADC input|reference|reset|RF input|audio input|crystal",
                "max_noise_mV": 5, "basis": "...", "why": "..."}],
 "radio": [{"ref": "<radio/GNSS part>", "kind": "Wi-Fi|BLE|GNSS|LoRa|sub-GHz|cellular|Zigbee|NFC|other",
            "band_MHz": [2400, 2483.5], "supply_ripple_max_mV": 10, "basis": "...", "why": "..."}],
 "connectors": [{"ref": "<connector ref>", "function": "short", "direction": "input|output|bidirectional|unknown",
                 "rail": "<net it carries, or null>", "V_V": 5, "I_A": 0.5, "cable_length_m": 1.0,
                 "basis": "...", "why": "..."}],
 "thermal": {"T_amb_C": [0, 40], "enclosure": "none|plastic|metal|unknown", "track_rise_max_K": 20,
             "airflow_h_W_m2K": null,
             "heatsinks": [{"part": "<ref>", "sink_part": "<heat sink part number or null>", "theta_sa_C_W": 12,
                            "theta_cs_C_W": 0.5, "basis": "...", "why": "..."},
                           {"side": "top|bottom", "region": "board", "theta_C_W": 0.5, "T_C": 45,
                            "basis": "...", "why": "..."}],
             "basis": "...", "why": "..."}}
```

## Rules

- Every number is a plain number in the unit its key names (V, A, Hz, s, mV, K, m, C). Use null when the
  summary gives no basis at all; do not invent a field.
- `basis`: `datasheet` when you know the part number's datasheet value (e.g. TPS62130 f_sw 2.5 MHz,
  ESP32 peak 0.5 A at 3.3 V), `typical` for a class value (USB 2.0 port 0.5 A, LDO dropout), `guess`
  otherwise. `why` names the evidence: part value, lib_id, net name, repo.
- Ids must be copied exactly: rails' `net` from `rails` or a section's nets; `cell` from a section id
  starting `cell:`; `victim` from a section id starting `victim:`; refs from `parts` or a section.
- `rails`: every supply rail the summary lists. `tolerance_pct` is the load's allowed deviation (digital
  3.3 V: 5-10 %; MCU core: 3-5 %; analog reference: 0.5-1 %). `ripple_max_mV` is what the rail's most
  sensitive load tolerates (digital logic ~50-100 mV, ADC/analog ~5-20 mV, RF/PLL ~5-10 mV).
  `critical`: true for rails feeding a radio, an ADC/reference, a precision analog part or a CPU core.
  `regulator`: how `source_ref` makes this rail: `linear` (LDO, 78xx, load switch, series diode),
  `switching` (buck, boost, buck-boost, charge pump), or `none` (a connector, battery or module output).
  `from_net`: the rail it regulates from (an LDO's input, a buck's VIN), copied exactly; null when none.
  `eta`: a switching regulator's efficiency range at this load from its datasheet class (e.g. [0.85, 0.92]);
  null otherwise. Without these, kae takes the regulator as the board's power input and sees no loss in it.
- `loads`: every IC and module, with typical and maximum current from its datasheet class, and
  `T_max_C` its maximum junction (or operating) temperature when the part number's datasheet gives it
  (null otherwise: kae then uses the part class's rating).
- `converters`: one per `cell:` section; switching regulators and motor/LED drivers.
- `sensitive`: feedback pins (`victim:feedback:*`), ADC inputs, references, resets, crystal pins, RF inputs.
- `radio`: only parts that are a radio transmitter/receiver or a GNSS receiver on this board.
- `connectors`: every connector. `direction` is power/signal flow seen from the board; `I_A` is what flows
  through it; `cable_length_m` only when a cable leaves the board from it (USB, jack, terminal block,
  wire-to-board), null for headers that mate with another board.
- `thermal.heatsinks`: only cooling the board shows or its documentation states: a heat sink footprint
  or a TO-220/TO-247 tab with a mounting hole next to a part (`part`, with `sink_part` when the board names
  the sink, and `theta_sa_C_W` from that sink's datasheet or its class: clip-on SOT-223/DPAK 20-40,
  TO-220 bolt-on 5-25); a board meant to sit on a metal plate or enclosure through a gap pad (`side`,
  `region` "board" or [x0, y0, x1, y1] in mm, `theta_C_W` of the whole interface, `T_C` the plate's
  temperature if stated). `airflow_h_W_m2K` only for a stated fan (25-100); null in still air. No heat sink
  is an empty list, never a guess.
- Keep it factual; when unsure, give the class value with basis `typical` or `guess`, not silence.
