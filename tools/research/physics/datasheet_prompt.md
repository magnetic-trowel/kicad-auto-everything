<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Part facts from datasheets (kae.part-facts/1)

kae's evaluator reads numbers, never prose. For each part number it needs (regulators, converter
switches and controllers, the larger loads), a model finds the manufacturer's datasheet, keeps the PDF
in the local datasheet library, and records the values kae uses, each with the page it came from. kae
then reads these through its part table (kae.excite.parts.json); boards only state what is specific to
them (their own load currents, their wiring).

## Library (on the benchmark host, never committed: datasheets are the manufacturers' copyright)

    $KAE_DATASHEETS (default ~/kae-datasheets)
      pdf/<slug>.pdf        the datasheet as downloaded (one per part family)
      facts/<slug>.json     this format; one per part number asked for
      text/<slug>.txt       pdftotext -layout output (for searching later)

`<slug>`: the part number in lower case with every character other than a-z, 0-9 and - replaced by -.

## Steps per part

1. From the value and lib_id, identify the part number and manufacturer. A module (ESP32-WROOM, Pro
   Micro, Raspberry Pi) uses its module datasheet; a generic value ("3.3V", "LDO") with no part number is
   `"identified": false` with a reason, and nothing else.
2. Find the manufacturer's datasheet (the manufacturer's site first; a distributor's copy if it is the
   manufacturer's document). Download it: `curl -L -A "Mozilla/5.0" --max-time 90 -o pdf/<slug>.pdf URL`;
   check it is a PDF (`pdfinfo`); then `pdftotext -layout pdf/<slug>.pdf text/<slug>.txt`. Never fetch
   from gitlab.fabcloud.org. If no PDF can be downloaded, record the URL and `"pdf": null`.
3. Read the values from the text (search it with grep for the table names) and write facts/<slug>.json.

## facts/<slug>.json

```json
{"schema": "kae.part-facts/1", "query": "<the value asked for>", "identified": true,
 "part": "LM7805", "manufacturer": "Texas Instruments", "family": "LM78xx",
 "match": "<a regex matching this part's values in board files, e.g. (?i)^(LM|L|MC)?7805>",
 "kind": "linear_regulator|switching_regulator|charger|load_switch|mosfet|diode|mcu|module|driver|amplifier|other",
 "datasheet": {"url": "...", "pdf": "pdf/lm7805.pdf", "title": "...", "revision": "...", "sha256": "<of the pdf>"},
 "values": {
   "<name>": {"typ": 1.0, "min": null, "max": null, "unit": "A", "conditions": "...", "page": 5, "table": "Electrical Characteristics"}
 },
 "notes": "anything a reader needs (e.g. 'efficiency read from Figure 12 at 0.5 A, 12 V in')"}
```

Value names (use these exact names and units; record only what the datasheet states):

- every part: `T_j_max_C` (absolute max junction or max operating temperature, C), `theta_ja_C_W`,
  `theta_jc_C_W` and `theta_jb_C_W` (junction to ambient, case and board, for the package used, C/W;
  `theta_jb_C_W` is RthetaJB, or psiJB when that is all the sheet gives: say which in conditions), `package`.
- regulators and chargers: `V_in_max_V`, `V_out_V`, `I_out_max_A`, `I_q_A` (quiescent), `V_dropout_V`
  (at its rated current), and for switching ones `f_sw_Hz`, `eta` (as {"typ": 0.9, "conditions": "load,
  V_in, V_out"}), `R_on_high_ohm`, `R_on_low_ohm` (integrated switches), `V_sw_max_V` (switch node
  absolute max).
- MOSFETs: `R_ds_on_ohm` (at the stated V_gs), `V_ds_max_V`, `I_d_max_A`, `Q_g_C`, `C_oss_F`.
- diodes: `V_f_V` (at the stated current), `V_rrm_V`, `I_f_max_A`.
- heat sinks (kind `other`): `theta_sa_C_W` (sink to ambient in natural convection, C/W; at a stated
  airflow say so in conditions).
- MCUs, modules, drivers, amplifiers and other loads: `I_supply_typ_A`, `I_supply_max_A` (the active
  current at the typical and the worst stated condition, e.g. radio transmitting), `V_supply_V`; modules
  also `body_w_mm` and `body_l_mm` (their own board's outline, shorter and longer side).

Rules: a number is copied with its unit converted to the one named; `page` is the PDF page number;
`conditions` quotes the test conditions; a value read from a graph says so in `conditions`. Never fill
a value from memory: if it is not in the datasheet, leave it out.
