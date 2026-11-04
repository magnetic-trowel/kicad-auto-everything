# MIPI CSI-2 / DSI (D-PHY) layout rules

Scope: D-PHY CSI-2/DSI length, impedance, skew, coupling. Not here: shared interface rules -> [common.md](common.md).
Keys: MIPI, CSI-2, DSI, D-PHY, cable_il_db, loosely coupled, LP mode, AM62x, intralane skew, interlane skew
Tags: [P] primary, [S] snippet, [I] inference, [VR] verification_rules.md.

## Qualcomm D-PHY length vs rate and cable loss
Source: [Qualcomm MIPI CSI D-PHY routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html) [P]. Max trace depends on data rate and external flex-cable loss, so the pack needs a `cable_il_db` input, not one length.

| Data rate (Gb/s/lane) | 0.5 | 0.75 | 1.0 | 1.5 | 2.1 | 2.5 |
|---|---|---|---|---|---|---|
| Total channel IL | −2.1 dB | −2.3 dB | −2.3 dB | −2.5 dB | −3.5 dB | −6.5 dB |
| Max trace, better cable (e.g. IL ≥ −0.5 dB) | 260 mm | 210 mm | 200 mm | 145 mm | 170 mm | 210 mm |
| Max trace, worse cable (IL −0.5 to −1.0 dB) | 190 mm | 155 mm | 125 mm | 60 mm | 90 mm | 150 mm |

Not monotonic in rate: each rate is paired with an example flex-cable length (3 in or 6 in). Without cable data fall back to TI's 254 mm.

## D-PHY rules by vendor
| Param | Qualcomm | TI AM62x ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]) |
|---|---|---|
| Impedance | 70–100 Ω diff; 36–52 Ω SE (relaxed from legacy 100/50 Ω) | 85–115 Ω diff; 50 Ω SE |
| Coupling | Intralane spacing 1 × W | "Loosely coupled" (LP mode) |
| Intra-pair skew | 0.7 mm | Set by mode-conversion S-parameter limits; estimate UI/50 = 8 ps at 1.25 GHz [I] [VR VERIFIED+CTX] |
| Inter-lane skew | 1.4 mm | ≤40 ps (0.1 UI) |
| Spacing | 2.5 × W to other signals; 1–1.5 × W between lanes | — |
| Length | Per the table above | ≤10 in (254 mm) |
| Vias | — | ≤2 |

- Skew: UI formula -> [common.md#skew-as-ui-formula](common.md#skew-as-ui-formula).
- Add a pack flag so the router picks a loose diff gap for MIPI (TI), not the tight default.

## Open questions
- Tight (Qualcomm 1W) vs loose (TI) coupling: select by SoC vendor.
- MIPI Alliance primary documents not accessible.

## Sources
- [interface_rule_packs.md § 5](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md); [verification_rules.md § 1A DP-2](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- See also [hdmi-dp.md](hdmi-dp.md), [../rule-pack-format.md](../rule-pack-format.md).
