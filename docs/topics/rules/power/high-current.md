# High-current paths: trace and via ampacity, copper weight, busbars

Scope: canonical home for trace width / IR drop, via ampacity, copper weight vs fab minimums, busbars, HC rule IDs. Not here: thermal copper sizing -> [../thermal.md](../thermal.md); fab limits -> [../dfm-fab-limits.md](../dfm-fab-limits.md).
Keys: high current, ampacity, IPC-2221, IPC-2152, trace width, IR drop, via current, via ampacity, plating, copper weight, heavy copper, oz, busbar, press-fit, PowerBusbar, track_width, HC-01, PDN-07

## High-current checks to emit
1. Per-net I_max from regulator ratings and datasheets (LLM extraction); width and via counts computed (code); KiCad `track_width` constraints per net class from I_max and copper weight.
2. Size with IPC-2152 (or conservative IPC-2221) plus an explicit IR-drop check; graph-based narrowest cross-section over tracks and zones.
3. Vias where current enters or leaves pads, not scattered: ≥ceil(I/I_via), default I_via from the conservative TI SLVA959 / IPC-2152 table (~0.8 A per 12 mil via); sources disagree 2.6× (log the conflict).
4. Copper weight is a stackup decision: heavier copper raises fab minimum track/space and can break fine-pitch footprints; surface it early ([../dfm-fab-limits.md](../dfm-fab-limits.md)).
5. Tens to hundreds of amps: press-fit busbars; the 100–200 µΩ transitions and the PCB layout around them are the limits.

## Trace width
- IPC-2221: I = k·ΔT^0.44·A^0.725 (A in mil², k = 0.048 external, 0.024 internal). For 1 A, 10 °C, 1 oz external: A = 16.3 mil² → 11.8 mil = **0.30 mm** (VR arithmetic VERIFIED). 5 A, same conditions: **2.77 mm** [C]. Blogs quoting 20 mil are wrong.
- IPC-2152 is chart-based. It corrects for copper weight, board thickness and plane proximity, usually allows more current, and shows internal traces near planes are not as derated as IPC-2221 implied. A plane within about 0.5–1 mm acts as a heatsink ([semiconductor.tools](https://semiconductor.tools/blogs/07-ipc-2221-vs-ipc-2152)) [S].
- Rohm conservative design values: **>1 mm per A (1 oz), >0.7 mm per A (2 oz)**; 2 A → 0.53 mm for a 20 °C rise ([Rohm](https://fscdn.rohm.com/en/products/databook/applinote/ic/power/switching_regulator/converter_pcb_layout_appli-e.pdf)) [P].
- IR drop: ΔV = I·R, R = ρL/(w·t), ρ_Cu ≈ 1.72e-8 Ω·m, 1 oz ≈ 35 µm.
- [TI SLAA896](https://www.ti.com/lit/pdf/slaa896) (FR-4, 1 oz, 62 mil board) [P], width → DC R / current:

  | Width | DC resistance | Current |
  |---|---|---|
  | 30 mil | 9.68 mΩ/in | 3.18 A |
  | 40 mil | 7.08 mΩ/in | 3.63 A |
  | 50 mil | 5.58 mΩ/in | 4.32 A |
  | 80 mil | 3.41 mΩ/in | 5.55 A |

## Via ampacity

| Source | 8 mil | 10 mil | 12 mil | 16 mil | Other |
|---|---|---|---|---|---|
| TI SLVA959 (IPC-2152, 1 oz, 10 °C) [P] | 0.55 A | 0.81 A | **0.84 A** | 1.1 A | 6 mil 0.2 A |
| TI SLAA896 (epoxy-filled; R / L / I) [P] | — | 1.3 mΩ / 1.32 nH / 2.01 A | 1.1 / 1.26 / **2.21 A** | — | 4 mil 2.9/1.61/1.4; 6 mil 2.1/1.48/1.53; 18 mil 0.7/1.14/2.72 |
| Calculators [S] | — | — | 0.3 mm ≈1.9 A (25 µm plating), 1.6 A (20 µm) | — | others say 0.8–1.0 A; ~1.1 mΩ per via in 1.6 mm board |

- Plating thickness matters more than drill size.
- SLYT614 / SLVA773: ≥1 via per amp [P]. SLVA959: "Minimize the number of layer jumps in the high current path."

## Copper weight
- JLCPCB min track/space by weight (1 oz 0.10 mm … 4.5 oz 0.30 mm; >2 oz 2-layer only; ML outer 1–2 oz) -> [../dfm-fab-limits.md](../dfm-fab-limits.md#jlcpcb-detail).
- TI SNVA419 [P]: ≥1 oz for all DC-DC designs, 2 oz above 3 W, 4 oz above 6 W dissipation.

## Busbars
- Würth ICS PowerBusbar ([overview](https://www.powerelement.com/media_content/pdf1/product-overview-powerbusbar-pcb-en.pdf)) [P]:
  - Busbar, press-fit Powerelements and PCB pressed in one operation, no extra fixing. Order: Powerelement → PCB → busbar.
  - Replaces thick-copper PCBs or inlays.
  - Capacity "must be considered in the context of the overall system". PCB to IPC-A-600 + Würth press-fit spec.
- Würth datasheet [S]: busbar 1.0–1.5 mm; PCB ≤2.0 mm FR-4; press-in force 60–350 N per pin, retention 60–80%; press-fit transition 100–200 µΩ. The limit is usually the PCB layout or the external connection.
- Laminated (overlapping, opposite-current) DC-link conductors cancel fields and cut inductance ([AtlasPCB](https://www.atlaspcb.com/blog/heavy-copper-pcb-design-power-electronics-bus-bar/)) [V].

## High-current rule IDs
RPA §14 [I].

| ID | Rule | Numeric | Check | Sev |
|---|---|---|---|---|
| HC-01 | Each high-current net gets I_max; minimum width per layer + IR drop | ~0.30 mm at 1 A (IPC-2221, scale non-linearly) | Narrowest cross-section along every path (track/zone graph) | S2 |
| HC-02 | ≥ceil(I/I_via) vias at the pad where current enters or leaves | I_via default 0.8 A (12 mil, 1 oz, 10 °C) | Count vias within r of each pad | S2 |
| HC-03 | Heavy-copper layer vs fine-pitch footprints | ≥2 oz → ≥0.15–0.16 mm space | Pad gaps vs fab min-space for the weight | S1 |
| HC-04 | Supply/return overlapped on adjacent layers or side by side | Minimise enclosed area | Loop-area metric for supply+/return pairs | S2 |
| HC-05 | Busbar/press-fit keep-outs; no sensitive nets under busbars; transitions are hot spots | 100–200 µΩ per transition | Rule areas from busbar footprints | S2 |
| HC-06 | Kelvin shunts with pads not shared with the power path | [current-sense-kelvin.md](current-sense-kelvin.md) | Tap inside the pad | S1 |
| PDN-07 | Size power traces and pours with IPC + IR drop | as above | Per-net minimum width vs regulator rating | S2 |

## Open questions
- **SLAA896 vs SLVA959:** 2.21 A vs 0.84 A at 12 mil, probably different ΔT and plating assumptions; neither states them fully.
- **IPC-2152 chart values** were not verified (paywalled), and calculators disagree.
- **Not read:** copper-inlay and coin rules, and the Würth press-fit hole spec.

## Sources
- [rules_power_rf_analog_dfm.md § 2, § 11, § 14](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also: [../thermal.md](../thermal.md), [../decoupling-pdn.md](../decoupling-pdn.md), [../dfm-fab-limits.md](../dfm-fab-limits.md)
