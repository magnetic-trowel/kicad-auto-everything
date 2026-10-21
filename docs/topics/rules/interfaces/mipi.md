# MIPI CSI-2 / DSI (D-PHY) layout rules

*Tags: [P] primary source read, [S] snippet only, [I] our inference.*

**TL;DR**
- **Maximum trace length trades off against data rate and the external flex-cable loss.** Qualcomm's table runs from 260 mm (0.5 Gb/s, good cable) down to 60 mm (1.5 Gb/s, worse cable). The pack therefore needs a `cable_il_db` input, not a single length.
- **Impedance and skew (Qualcomm):** 70–100 Ω differential and 36–52 Ω single-ended, relaxed from the legacy 100/50 Ω. Intralane skew 0.7 mm, interlane skew 1.4 mm.
- **TI AM62x CSI:** ≤10 in, 85–115 Ω, **loosely coupled pairs** (because of LP mode), lane skew ≤40 ps (0.1 UI), ≤2 vias. Intra-pair skew is set by mode-conversion S-parameter limits, estimated as UI/50.
- **Spacing (Qualcomm):** 2.5W to other signals, 1W within a pair, 1–1.5W between lanes.

## Key facts

### Qualcomm D-PHY limits

Source: [Qualcomm MIPI CSI D-PHY routing](https://docs.qualcomm.com/doc/80-PV086-5P/topic/mipi-csi-d-phy-routing-constraints-up-to-2dot5-Gbps.html) [P].

| Data rate (Gb/s/lane) | 0.5 | 0.75 | 1.0 | 1.5 | 2.1 | 2.5 |
|---|---|---|---|---|---|---|
| Total channel IL | −2.1 dB | −2.3 dB | −2.3 dB | −2.5 dB | −3.5 dB | −6.5 dB |
| Max trace, better cable (e.g. IL ≥ −0.5 dB) | 260 mm | 210 mm | 200 mm | 145 mm | 170 mm | 210 mm |
| Max trace, worse cable (IL −0.5 to −1.0 dB) | 190 mm | 155 mm | 125 mm | 60 mm | 90 mm | 150 mm |

The limits are not monotonic in data rate. Each rate is paired with an example flex-cable length (3 in or 6 in).

### Rules by parameter

| Param | Qualcomm | TI AM62x ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P]) |
|---|---|---|
| Impedance | 70–100 Ω diff; 36–52 Ω SE | 85–115 Ω diff; 50 Ω SE |
| Coupling | Intralane spacing 1 × W | "Loosely coupled" (LP mode) |
| Intra-pair skew | 0.7 mm | Must satisfy mode-conversion S-parameters; estimate UI/50 = 8 ps at 1.25 GHz [I] [VR VERIFIED+CTX] |
| Inter-lane skew | 1.4 mm | ≤40 ps (0.1 UI) |
| Spacing | 2.5 × W to other signals; 1–1.5 × W between lanes | — |
| Length | Per the table above | ≤10 in (254 mm) |
| Vias | — | ≤2 |

## Recommendations for our system
- **Length:** compute the maximum from the data rate and `cable_il_db` using the Qualcomm table, or fall back to TI's 254 mm.
- **Skew:** store as UI formulas resolved at the configured rate, and emit them as ps `skew`.
- **Coupling:** add a pack flag that makes the router choose a loose diff gap for MIPI, not the tight default.

## Conflicts and open questions
- **Tight vs loose coupling:** Qualcomm gives a gap of 1W; TI says "loosely coupled". Select by SoC vendor.
- **MIPI Alliance primary documents** were not accessible.

## Sources
- Research notes:
  - [interface_rule_packs.md § 5](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
  - [verification_rules.md § 1A DP-2](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also:
- [hdmi-dp.md](hdmi-dp.md)
- [../diff-pairs.md](../diff-pairs.md)
- [../rule-pack-format.md](../rule-pack-format.md)
