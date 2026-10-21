# Differential pairs

*Tags:*
- [P] primary source read
- [S] snippet
- [I] our inference
- VR statuses as in [si-fundamentals.md](si-fundamentals.md)

**TL;DR**
- **Each leg returns under itself.** Pairs are not self-returning, so every return-path rule applies to each leg.
- **Skew turns differential signal into common mode.** 20% skew relative to t_r gives 10% common mode, and common mode dominates both EMI and crosstalk. Budget skew as skew_max = min(vendor spec, ≈0.1·t_r), and correct it with **running-skew** compensation placed near the mismatch.
- **Coupling closer than about 0.5 mm buys no extra EMI benefit**, because driver imbalance dominates. Choose the gap for Zdiff and density. Rounded corners do **not** remove skew.
- **TI's absolute keep-outs:**
  - 30 mil to any signal;
  - 50 mil to clocks;
  - 5W between pairs.
- **Further rules (VR):** uncoupled length ≤45 mil (NXP); bends >135°; equal via counts; family-scoped via limits.
- **Place ICs so each pair leaves the driver heading the same way it enters the receiver.** The left and right turns then cancel.

## Key facts

### Physics ([Johnson] [P])
- **Common mode from skew.** V_cm ≈ Δv·Δt/(2t_r) ([CMA of Skew](https://www.sigcon.com/Pubs/edn/CMAofSkew.htm)). kicad-happy implements the same relation as V_CM = V_diff·skew/(2T_rise).
- **Spacing.** In theory, 0.5 mm spacing gives about 40 dB of cancellation. In practice, drivers rarely balance better than 1:100, so "0.5 mm is close enough" ([Reducing EMI](https://www.sigcon.com/Pubs/edn/ReducingEMI.htm)). LearnEMC: an imbalanced pair radiates like a single-ended line.
- **Corners** ([Skewed Layout](https://www.sigcon.com/Pubs/edn/SkewedLayout.htm)):
  - The outer leg gains 2p (square), 1.65p (chamfered) or 1.57p (rounded) per corner, where p is the pitch. At p = 20 mil and 160 ps/in, that is 5–6.4 ps per corner.
  - Budget layout skew against the driver's own skew; if unspecified, assume ≥10% of t_r. Examples: 100BASE-TX balanced to 1:1000 gives about 0.1"; 2.5 Gb/s with 200 ps edges gives about 20 ps.
- **Serpentines** ([Serpentine](https://www.sigcon.com/Pubs/edn/serpentine.htm)):
  - At 8/8/5 mil geometry, NEXT ≈ 6%.
  - A coupled switchback whose round trip is ≫ ⅓ t_r distorts the signal. One whose round trip is ≪ ⅓ t_r advances it by up to 2× NEXT per switchback (4× for a full serpentine).
  - Maximum useful coupled switchback: about 1" per ns of t_r (about 0.1" at 100 ps). Beyond that, stretch the serpentine to remove the coupling.
  - Delay matching must also match configuration, width, Dk, loading, thresholds and terminations, not just length.
- **Differential vias (XFP).** Use an oval antipad with ground vias pinning the planes at each end. Without them, crosstalk is higher and "falls off less rapidly". Avoid long stubs ([XtkDiffViaGnds](https://www.sigcon.com/Pubs/edn/XtkDiffViaGnds.htm)).

### Numeric rules (VR corrections applied)
| Rule | Value | Source / status |
|---|---|---|
| Pair-to-pair | ≥5W (6 mil traces → 30 mil) | [TI SPRAAR7J](https://www.ti.com/lit/pdf/spraar7) [P; VERIFIED] |
| Pair to other nets | **≥30 mil to any signal; ≥50 mil to clocks or periodic signals; not within 30 mil of another pair after escape** | SPRAAR7J p.9–10 [VR addition] |
| NXP pair to others | ≥max(20 mil, 4h); 30 mil from higher-voltage or faster aggressors | [NXP AN10373](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/powerquicc/2284/2/philips_PCIe_pcb_routing_guide.pdf) [P] |
| Voids | ≥1.5W from voids, waived at intentionally voided SMD pads | SPRAAR7J [VERIFIED+CTX] |
| Intra-pair skew | 5 mil (USB3/PCIe/SATA/HDMI) and 50 mil (USB2), from the AM57xx tables | VERIFIED+CTX (device-family tables). MIPI CSI uses mode-conversion S-parameters instead, ≈ UI/50 |
| Where to compensate | Add length "near the location where the mismatch occurs"; serpentine at the mismatched end | AN10373 [VERIFIED; AN10798 NOT RETR.]; TI |
| Jogs and spread | Jogs ≥15 mil (3W); serpentine spread S1 < 2S | **VR: "amplitude ≥2W" NOT FOUND. The primary rule is a maximum spread** |
| Uncoupled length | **≤45 mil (1.14 mm)** into a pin or ball; breakout **≤0.25 in (6.35 mm)** from the package | **CORRECTED** (the 3.0 mm value was a forum example) |
| Vias | Equal count on P and N, equally spaced, near the SoC. USB3 ≤2; USB2 ≤4; **PCIe/SATA/HDMI 0 on AM57xx/KeyStone II, 2 on AM64x/65x**; CSI 2 | VERIFIED+CTX / CORRECTED |
| Antipads | As large as possible (30 mil gives "significant benefits") on all layers; no non-functional pads | SPRAAR7J p.12 [VR addition] |
| In-line SMDs | ≤0603 (0402 strongly preferred), symmetric. Void the plane 100% under the pads, ≥2 layers deep; 60% under ESD/EMI signal pads; 0402 0 Ω no-stuff option for the CMF | SPRAAR7J p.12–15 [VERIFIED] |
| Bends | >135° (Rev J replaces the older "two 45°"). NXP: ≥135°, ≥20 mil air gap, flanking segments ≥1.5W, equal numbers of left and right bends | [VR VERIFIED, updated] |
| Width / breakout | Constant width after BGA escape; after breakout keep pairs clear of the SoC | SPRAAR7J p.9–10 [VR addition] |
| Return vias | Symmetric, ≤200 mil, scaled by data rate | [si-fundamentals.md](si-fundamentals.md) |

### KiCad semantics ([KiCad 9 docs](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html) [P])
- `skew` is measured against the **longest** matched net, not the average (corrected).
- `within_diff_pairs` checks each pair separately.
- `diff_pair_gap` is not checked on non-parallel fanout.
- `diff_pair_uncoupled` counts length that is non-parallel or outside the gap range.
- The pair-to-pair clearance condition is `A.inDiffPair('*') && !AB.isCoupledDiffPair()`.
- KiCad 10 can express skew in ps (time domain), with per-layer and via delay.
- kicad-happy carries per-protocol skew limits that we have not verified: USB HS 25 ps, PCIe 5 ps, Ethernet 50 ps, HDMI 20 ps ([MIT](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P]).

## Recommendations for our system
- **Skew budget.** skew_max = min(spec or vendor value, k·t_r), with k ≈ 0.1, or tighter for balanced links such as Ethernet. Convert ps to mm with the per-layer delay: use KiCad 10 profiles, with Ott's 150/180 ps/in as a fallback.
- **Running-skew compensation.** Walk both legs and insert a tune wherever |running skew| exceeds about 0.2 × the budget [I]. Checking only the end-of-route totals is not enough.
- **Placer.** Add a cost for pair direction alignment, i.e. same exit and entry direction.
- **Router.**
  - Use symmetric breakouts.
  - Keep serpentine switchbacks short or uncoupled.
  - Put GND vias beside every differential via pair.
  - Keep via counts equal on both legs.
  - Route into connector pads from the non-stub end.
- **Constraints to emit:** `diff_pair_gap`, `diff_pair_uncoupled (max 1.14mm)`, `skew within_diff_pairs`, `via_count`, and pair-to-other clearances of 0.762 mm (30 mil) and 1.27 mm (50 mil to clocks). Interface packs override these defaults (e.g. [interfaces/usb3-usb4-typec.md](interfaces/usb3-usb4-typec.md), [interfaces/pcie.md](interfaces/pcie.md), [interfaces/ddr.md](interfaces/ddr.md)).

## Conflicts and open questions
- **Vendor intra-pair skew differs by up to 14× for USB3.** See [interfaces/usb3-usb4-typec.md](interfaces/usb3-usb4-typec.md).
- **No general primary rule for the number or distance of return GND vias per differential via**, beyond TI's 200 mil and the XFP figure, whose dimensions are illegible.
- **The SPRAAR7J bend-figure annotations** (">1.5 x Trace Width", ">5 x Trace Width") are unexplained.

## Sources
- Research notes:
  - [rules_highspeed_emi.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
  - [verification_rules.md § 1A, 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- Primary documents:
  - TI SPRAAR7J: https://www.ti.com/lit/pdf/spraar7
  - Johnson articles: https://www.sigcon.com/Pubs/edn/

See also:
- [si-fundamentals.md](si-fundamentals.md)
- [checkers-si-emi.md](checkers-si-emi.md)
- [interfaces/usb2.md](interfaces/usb2.md)
- [interfaces/pcie.md](interfaces/pcie.md)
