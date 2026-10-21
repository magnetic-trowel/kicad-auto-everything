# PCIe Gen2–Gen6 layout rules

*Tags: [P] primary source read, [S] snippet only, [I] our inference. VR = verification_rules.md.*

**TL;DR**
- **Budget loss, not length.** TI SNLA426 totals are 23.5 / 28 / 36 dB for Gen3 / Gen4 / Gen5. A 9 in high-loss motherboard trace takes 13 / 14 / 16 dB of that. FR4 loses 0.686 dB/in at 8 GHz and 1.289 dB/in at 16 GHz.
  - Single-board budgets (Qualcomm): Gen2 −6 dB at 2.5 GHz (≤250 mm); Gen3 −10 dB at 4 GHz (≤300 mm).
  - Each via costs about 2 in of length (Gen2, FR4).
- **Impedance and skew:**
  - The spec allows 70–100 Ω. Add-in cards need **85 Ω**. TI SoC tables use 100 Ω ±10% or 95 Ω ±5%.
  - Intra-pair skew ≤5 mil, *additive over segments*. Qualcomm allows 5 ps ≈ 0.7 mm.
  - Lane-to-lane matching is not required.
- **AC caps.** 220 nF satisfies every range quoted (TI 75–220 nF; Qualcomm, Efinix and NXP 176–265 nF for Gen3+). Placement disputes reduce to "near the connector for add-in cards; near either endpoint on one board; never mid-line or staggered".
- **Vias and stubs:**
  - Return vias within 50 mil (TI Gen5) or ≥2 within 100–200 mil (EMA).
  - Stubs <15 mil preferred. The physics limit at Gen5 is ≈51–54 mil.
  - Antipads 40 mil with 10/20 mil drill/pad; non-functional pads removed.
- **Edges and layers:**
  - ≥max(5W, 5H) from the plane edge; ≥4H from voids.
  - Edge-finger keep-outs on add-in cards.
  - Microstrip vs stripline is contested between TI documents.

## Key facts

### Loss budget ([TI SNLA426](https://www.ti.com/lit/pdf/snla426) [P]), dB
| Item | Gen3 | Gen4 | Gen5 |
|---|---|---|---|
| CPU package | 3.5 | 5 | 9.0 |
| 9 in system-board trace (high-loss material) | 13 | 14 | 16 |
| CEM connector | 0.5 | 0.5 | 1.5 |
| 4 in add-in card | 6.5 | 8.5 | 9.5 |
| **Total** | **23.5** | **28** | **36** |
| Crosstalk mitigation | negligible | <2 | 4–5 |
| Temperature/humidity | — | — | 2–3 |

Eye height after EQ is 25 mV for Gen3 and 15±1.5 mV for Gen4/5; eye width is 0.3 UI.

### 1-inch SDD21 by material (TI SNLA426 Table 9-1)
| Material (Dk, Df) | 8 GHz | 16 GHz |
|---|---|---|
| Megtron 6 (3.4, 0.002) | 0.189 dB | 0.336 dB |
| Rogers (3.48, 0.0037) | 0.251 dB | 0.411 dB |
| GETEK (4.1, 0.011) | 0.548 dB | 1.017 dB |
| Nelco 4000-6 (4.0, 0.012) | 0.578 dB | 1.078 dB |
| FR4 (4.4, 0.014) | 0.686 dB | 1.289 dB |
| Tetrafunctional FR4 (4.1, 0.022) | 0.961 dB | 1.844 dB |

### Other loss figures
- **[Efinix AN063](https://www.efinixinc.com/docs/an063-high-speed-transceiver-design-guidelines-v1.2.pdf) [P]:**
  - At 6.25 GHz, about 0.5 dB/in for Megtron 6 and about 1 dB/in for FR4.
  - Maximum RX channel loss: 25 dB.
- **[EMA](https://www.ema-eda.com/wp-content/uploads/2025/10/PCIe-Design-Guide-Part-1.pdf) [P]** (an EDA reseller, so lower authority):
  - End-to-end budgets: Gen3 <20 dB at 4 GHz; Gen4 <28 dB at 8 GHz; Gen5 <36 dB at 16 GHz; Gen6 <32 dB at 32 GHz (PAM4).
  - Material Df: <0.010 for Gen3, <0.005 for Gen4, <0.002 for Gen5. Standard FR4 (Df ~0.020) is only for Gen1/2 or very short Gen3.
  - "Even 12 inches of standard FR4 can exceed the Gen5 loss budget."
- **NXP AN10373 (2005)** [P]:
  - 0.35–0.50 dB/in and 1–5 ps of jitter per inch.
  - Add-in cards ≤4 in; system boards <12 in.
- **NXP AN12864** [S]: Gen4 adds 1.0–1.2 dB/in and 1–5 ps of jitter per inch.

### Rules
| Param | Default | Variants / **conflicts** | Check |
|---|---|---|---|
| Zdiff | 85 Ω for CEM add-in; the spec allows 70–100 Ω (excluding vias, cap pads, connectors and cables) | TI SoC tables: **100 Ω ±10% (AM57xx/KeyStone), 95 Ω ±5% (AM64x/AM65x)** [VR]; Qualcomm 70–100 Ω; SLLU149E 100 Ω / 50–55 Ω SE; REFCLK 100 Ω with ≤200 fs RMS RJ | K + S |
| Intra-pair skew | ≤5 mil; "differences over all segments are additive and must be less than 5 mils" ([SLLU149E](https://www.ti.com/lit/pdf/sllu149), SNLA426, Efinix) | [Qualcomm](https://docs.qualcomm.com/doc/80-PV086-5P/topic/PCIe%20layout%20guidelines.html) 5 ps (0.7 mm); EMA ±2 mil for Gen4–6 | K `skew within_diff_pairs`, per `fromTo` segment when caps split the pair |
| Lane-to-lane | Not required (SNLA426: "typically up to 1 inch"; §13 also says "<6 in", an internal inconsistency). Qualcomm: no matching between REFCLK, TX and RX; no serpentines required | SoC tables: RX and TX groups ≤550 mil each (AM57xx/KeyStone), or 6 ns RX / 1.5 ns TX (AM65xx); Efinix: no inter-pair requirement | Emit only on device demand |
| Board budget | Single board: Gen2 −6 dB at 2.5 GHz / 250 mm; Gen3 −10 dB at 4 GHz / 300 mm (Qualcomm). Motherboard-to-CEM: 13/14/16 dB (TI) | SLLU149E: Gen2 drivers designed for a 20 in pair on FR4. Efinix: add-in card ≤101.6 mm. TI SoC limits: ≤4700 mil (AM57xx), ≤5500 mil (KeyStone II/K2G), ≤4000 mil (AM65xx) | S |
| Via penalty | "Each signal trace via reduces the maximum trace length by approximately 2 inches", e.g. 6 vias → 8 in (SLLU149E) | Heck ≈1 in per via at 5 Gb/s | S/G loss score |
| Via count | Qualcomm: layer transitions only at breakout and connectors | TI SoC tables: **0 vias (AM57xx/KeyStone) vs 2 (AM65xx)** [VR] | K `via_count` |
| Via geometry | 10/20/40 mil drill/pad/antipad; as many GND stitches around the antipad as possible; via-in-pad preferred; non-functional pads removed (SNLA426) | EMA: 8–10 mil drill, 18–22 mil pad, 30–35 mil antipad | G |
| Return vias | Within 50 mil (1.27 mm) at Gen5 (SNLA426) | EMA: ≥2 within 100–200 mil, on both sides of a pair; SPRAAR7J 200 mil; SLLU149E: bypass caps next to the vias if the reference changes | G |
| Via stubs | <15 mil, otherwise backdrill. Gen5 quarter-wave maximum ≈54 mil (Megtron 6) / 51 mil (FR4) | EMA: a 20 mil stub resonates near 8–16 GHz | G (stub from stackup) |
| AC-cap value | **Conflict:** TI SNLA426 75–220 nF (220 nF typical); Qualcomm Gen3 176–265 nF, Gen2 75–265 nF; Efinix 176–265 nF (220 nF conventional); NXP QorIQ Gen2 75–200, Gen3 176–265 nF [S]; SLLU149E 0.1 µF 0402 | **220 nF fits all**; BOM window 176–220 nF [I] | M |
| AC-cap position | **Conflict:** chip-to-chip near RX (SNLA426); same board near TXP/TXN (SLLU149E); TX side (Efinix); "anywhere … better close to source or receiver" (Qualcomm). Agreed: add-in/edge-finger → near the connector. Qualcomm: do not stagger caps | Treat "within N mm of TX pins *or* RX pins" as satisfied; pair caps side by side | G |
| AC-cap package and void | Smallest package (0201 pad 12 mil vs a 5–7 mil 85 Ω trace); Efinix recommends 0201. Pad void 100%, two layers, larger than the pad | — | G / M |
| Edge, voids, spacing | ≥max(5W, 5H) from the reference-plane edge; ≥4H from voids; pairs ≥4–5H apart; avoid the board edge (SNLA426) | Qualcomm 4W to others, Rx-Tx 4W (Gen3) / 3W (Gen2); EMA ≥3W (15–20 mil), ≥4W for Gen6; Efinix ×5 to other signals | K `clearance` / G |
| Serpentine | Segments ≥max(3W, 3H); at the mismatched (source) end (SNLA426); Qualcomm: any serpentine at the source breakout | — | G |
| Bends | Round preferred, 45° acceptable, no right angles (Efinix); 45° preferred (SLLU149E) | — | K `track_angle` |
| Layering | Efinix: TX and RX on different layers | **Conflict:** SPRAAR7J "does not recommend stripline"; SNLA426 and Efinix favour closely coupled stripline at Gen4–5 | selector |
| Edge fingers (PCIe 4.0 CEM) | No inner conductor within 0.381 mm below the edge-card connector; inner planes must not extend >2 mm into the edge-finger footprint (Efinix) | — | G: inner-layer keep-out zones |
| Clock buffer / REFCLK | Renesas: no parts or vias between the lines; 0402/0201; same layer and via count; "1 mm ⇒ 6 ps"; GND via at each change; ≥3W (5W optimal); one GND via per decap. See [../crystals-clocks.md](../crystals-clocks.md) | — | G |

## Recommendations for our system
- **Length from budget [I].** L_max ≈ (budget − Σ via/cap/connector allowances) / dB-per-inch at Nyquist.
  - Qualcomm's anchor points imply about 0.85 dB/in at 4 GHz and 0.6 dB/in at 2.5 GHz.
  - TI's FR4 figure with Gen4's 14 dB gives about 20 in before vias; realistically 9–12 in on FR-4, and much less at Gen5.
  - Store budgets and material tables; compute the limit per stackup.
- **Checks to emit:**
  - BOM: 176–220 nF window.
  - Placement: "cap within N mm of either endpoint", or of the connector on add-in cards.
  - Stub check (via checker H).
  - Return-via check, rate-scaled.
  - Inner-layer keep-outs under the edge fingers.

## Conflicts and open questions
- **AC-cap value and position.** Resolved above.
- **Microstrip vs stripline.** Unresolved; TI's motive is unexplained.
- **Lane-skew inconsistency** within SNLA426.
- **Missing sources:**
  - The PCI-SIG Base and CEM specs (C_TX table, M.2 budgets) were not accessible.
  - No primary per-via dB figure exists at 8/16 GHz.

## Sources
- Research notes:
  - [interface_rule_packs.md § 2](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
  - [verification_rules.md § 1A DP-6, § 2](../../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)

See also:
- [../diff-pairs.md](../diff-pairs.md)
- [../si-fundamentals.md](../si-fundamentals.md)
- [../stackup.md](../stackup.md)
- [usb3-usb4-typec.md](usb3-usb4-typec.md)
