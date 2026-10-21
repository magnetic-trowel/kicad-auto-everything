# Net-role classification (power, diff pairs, clocks, high-speed)

**TL;DR**
- Net roles come from four signals: **power symbols and names**, **suffix and keyword rules**, **pin names and roles on connected IC pins**, and **designer-assigned net classes**. Quilter and Flux key off native net classes first [V].
- **KiCad's diff-pair router is strictly name-based:** `+`/`-` or `P`/`N` suffixes, not mixable. Quilter also accepts A/B, P/M and t/c, so the front end must propose renames [P].
- **IBIS holds authoritative facts no other source has:** `[Diff Pin]` pairing, POWER/GND/NC pins, buffer `Model_type`, and **20–80% edge rates (`[Ramp]`)**. No tool uses IBIS to classify nets for layout, which is an open opportunity [P].
- Use a **layered classifier with evidence**: intent → IBIS/datasheet → topology → names → LLM [I].
- LLMs handle conventional pin names well but fail on **multiplexed and redundant pins**, so resolve MCU pin-mux deterministically [P].

## Key facts

### KiCad rules (official manuals)
- **Diff pairs:** "nets with a common base name and a positive and negative suffix… + and -, or P and N… cannot be mixed: USB+ and USB_N do not form a differential pair". The gap comes from the net class ([KiCad 9 PCB manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html)) [P].
- **Net-class patterns** ([KiCad 9 Schematic manual](https://docs.kicad.org/9.0/en/eeschema/eeschema.html)) [P]:
  - wildcards (`*`, `?`) and regex; dynamic assignment;
  - a net matching several patterns gets all of the classes, with the highest-priority class holding the field winning (Default is the fallback);
  - names include the sheet path.
- **Community hazards** [S] ([forum](https://forum.kicad.info/t/differential-pair-doesnt-work-with-any-of-the-suffixes/26166)):
  - the suffix must be the last character;
  - symbol pin names like `Pin_P` don't create pairable nets;
  - `XTAL_P`/`XTAL_N` names apply diff-pair rules to single-ended traces.
- **Pin electrical types:** Input, Output, Bidirectional, Tri-state, Passive, Unspecified, Power input, Power output, Open collector, Open emitter, Not connected [P, possibly stale mirror].

### Commercial detectors
- **Quilter diff pairs** [V] ([docs](https://docs.quilter.ai/physics-constraints/differential-pairs)):
  - a pair needs a differentialpair (or synonymous, e.g. 75 ohm) net class **and** a suffix: `+`/`–`, A/B, P/M (last or second-to-last character), P/N, t/c;
  - names starting with V are excluded;
  - pairs with series R/C are merged;
  - the user gives Zdiff, single-ended Z and carrier GHz;
  - not supported: multi-drop, fly-by, 2-layer stack-ups, coplanar waveguide (microstrip only).
- **Quilter power nets** [V] ([docs](https://docs.quilter.ai/physics-constraints/power-nets)):
  - detected by name pattern or a "Power" class;
  - default max current **200 mA below 3 V and 500 mA above 3 V**;
  - IPC width calculation per stack-up;
  - "Overheated Length" flags estimated rise **> 20 °C**;
  - single-ended impedance (50/75 Ω) is **manual only**: width within 5%, invalid-width tolerance 10%;
  - uncaptured signals are "generic, low-speed digital".
- **Flux Net Type:** 7 priority buckets (High Speed, Analog, Power, Medium Speed, Low Speed, Uncertain, Ground), inferred and user-editable, routed in that order. Users are told to mark diff pairs and add Max Current or Thermal Rise ([Flux](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter)) [V].
- **kicad-happy keyword classes:** ground, power, clock (SCL/SCK/CLK/XTAL), data, high_speed (USB/CAN/LVDS/ETH), analog (ADC/AIN/VREF), control, chip_select, interrupt, debug, config. Rails come from `#PWR`/`#FLG` symbols plus names; IO domains via VDDIO and VCCA/VCCB ([methodology](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md)) [P].

### Pin semantics
- **HWE-Bench:** with conventional names such as "USBD, USBP, CLK, SDA, TXD, RXD, RST", connection accuracy is "extremely high". Multiplexed or redundant pins (parallel grounds) cause "serious omissions or connection hallucinations" ([2603.18102](https://arxiv.org/abs/2603.18102)) [P].
- **PCBSchemaGen 32-role pin ontology**, in 7 groups [P] ([2602.00510v2](https://arxiv.org/abs/2602.00510)):
  - supply vdd/gnd; signal I/O (sense ±, out ±); logic;
  - MOSFET gate, drain, source, **kelvin source**;
  - **buck vin, gnd, sw, fb, en, boot**;
  - half-bridge hb, hs, ho, lo;
  - transformer and passive.

  Four predicate templates: supply-pair, must-be-connected, driving-pair, diff-pair-distinct.

### IBIS 7.2 (spec read directly) [P] ([PDF](https://ibis.org/ver7.2/ver7_2.pdf))

| Keyword | Layout-relevant content |
|---|---|
| `[Pin]` | signal_name plus model_name per pin; reserved **POWER, GND, NC**; optional R/L/C package parasitics |
| `[Diff Pin]` | non-inverting pin, `inv_pin`, `vdiff`, `tdelay_typ/min/max`. **Authoritative pairing, independent of net names** |
| `Model_type` | Input, Output, I/O, 3-state, Open_drain/sink/source, ECL variants, Terminator, Series; **Input_diff, Output_diff, I/O_diff, 3-state_diff**; Vinl/Vinh thresholds |
| `[Ramp]` | dV/dt **20–80%** into 50 Ω, typ/min/max (example 2.20 V / 1.06 ns) |
| `[Model Selector]` | alternative drive strengths |

- A practitioner guide calls `[Ramp]` "the best place to get rise and fall times" for constraints ([PCEA](https://pcea.net/wp-content/uploads/2022/04/High-Speed-Constraint-Values-v2-Pfeil.pdf)) [S].
- **KiCad already ingests IBIS** for simulation: fields `Sim.Library`, `Sim.Ibis.Pin`, `Sim.Ibis.Model`; helper symbols IBIS_DEVICE and IBIS_DEVICE_DIFF. KiCad ships no IBIS models [P].

## Recommendations for our system

1. **Layered classifier,** recording evidence per layer, with higher layers overriding lower ones [I]:
   1. explicit intent: net classes, directive labels, "Power" or diff-pair classes;
   2. IBIS `[Pin]`/`[Diff Pin]`/`Model_type`/`[Ramp]` when an `.ibs` exists, else datasheet pin roles mapped to a role ontology;
   3. topology: SW pin + L → switch node; FB + divider → feedback; XIN/XOUT + crystal → crystal net;
   4. names: suffix and keyword rules;
   5. LLM adjudication for leftovers, citing pins.
2. **"Is this net fast?" is a computation:** t_r(20–80%) × propagation velocity → critical length, compared with the estimated route length. Protocol data-rate and impedance tables stay deterministic and come from the interface rule packs (rules area, owned by the rules_hs_emi cluster).
3. **Propose renames** to `+`/`-` or `_P`/`_N` whenever a detected pair uses A/B, t/c or P/M; never silently rely on non-KiCad conventions.
4. **Resolve MCU pin-mux** from vendor pin-config exports or an explicit schematic table, not by LLM inference.
5. **Show defaults** (Quilter-style 200/500 mA) as needing confirmation; undetected nets are stated as "generic low-speed".

## Conflicts and open questions

- What fraction of BOM parts have IBIS files? Unquantified.
- No measured accuracy for net-role classification on PCB netlists.
- Vendor constraint managers (Allegro, Xpedition) were not checked for IBIS-driven classification.

## Sources
- research notes: [netlist_datasheet_understanding.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)

See also: [block-recognition.md](block-recognition.md), [design-understanding-pipeline.md](design-understanding-pipeline.md), [part-layout-card.md](part-layout-card.md)
