# Myths, context-dependent and contested rules

*Tags: [P] primary, [S] snippet, [I] inference. VR statuses as in [si-fundamentals.md](si-fundamentals.md).*

**TL;DR**
- **Many famous rules of thumb are wrong in general, or valid only in narrow contexts.**
  - Store each one as a **negative rule**: it stops the LLM emitting the slogan as a constraint, and it carries the physics-based check that replaces it.
  - Hubing: "a board that complies with 90% of the guidelines may be much worse than a board that complies with only one or two."
- **Some rules are genuinely CONTESTED between primary experts:**
  - 20-H;
  - perimeter stitching;
  - microstrip vs stripline for HS pairs;
  - termination threshold;
  - guard traces;
  - copper under inductors;
  - CIN/COUT grounds;
  - "smallest cap closest";
  - thermal-via tenting;
  - PMIC ground cuts.
  
  Never emit any of these by default. Store both variants plus a selector, ask the user, and log the choice.
- **90° corners are a myth for single-ended nets below about 2 Gb/s, but they matter on ESD paths (≤45°), RF lines (arcs or 135°), differential pairs (each corner adds skew) and nets at ≥10 Gb/s.** So the corner rule applies to the `ESD_UNPROTECTED` and `RF50` net classes, every differential pair, and nets at ≥10 Gb/s ([diff-pairs.md](diff-pairs.md) bends >135°).

## Key facts

### Myths and context-dependent rules
Split grounds (VERIFIED+CTX), 20-H and guard traces (both in the selector table below) are not myths: each holds in a stated context.

| Slogan | Verdict | Status / source |
|---|---|---|
| 90° corners are bad | Negligible up to about 2 Gb/s. For an 8 mil 50 Ω microstrip corner: ≈1 ps, 0.012 pF, ≈0.3% reflection at 100 ps. Rounding removes 21% of the corner copper, but 70–90% would be needed to cancel the excess capacitance. Corners start to matter around 10 Gb/s and for pair skew. The myth traces to the MECL handbook (1971). Other figures: 3 Ω at about 80 GHz; a 5 mil corner is 8.5 fF, with no impact below about 70 GHz | VERIFIED+CTX ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm); [Altium](https://resources.altium.com/p/slaying-900-right-angle-bend-dragon); LearnEMC "urban legend"). **Exceptions:** ESD paths ≤45° (arcs below 2.6 mm radius; [SLVA680A](https://www.ti.com/lit/pdf/slva680)); RF uses arcs or 135° (Espressif, u-blox) |
| 20-H rule | Shim & Hubing measured slightly *higher* far-field radiation (the "3.6 dB at TM10" figure is NOT RETR.). LearnEMC: it helps only when the power plane is sandwiched between grounds, and 2–3H is enough. **Montrose, Liu & Li 2005 (FDTD): "fact, not fiction"; 10-H may suffice; recommended only for high-density multilayer boards with multiple power/return planes; adding components "generally negates" the result** | **CONTESTED** ([Scholars' Mine](https://scholarsmine.mst.edu/ele_comeng_facwork/1333/); [Montrose](https://courseware.zcu.cz/CoursewarePortlets2/DownloadDokumentu?id=186283)) |
| Split analog/digital ground | "Probably a close second" worst guideline. Valid only for isolation below 100 kHz at about 1000:1 sensitivity, and even then better done as a separate return on another layer | VERIFIED+CTX. Ott's ≥14-bit exception: isolated regions joined under each ADC |
| I/O ground island with a single-point tie | "One of the worst possible ways." Use an overlapping chassis layer with capacitors instead | LearnEMC; Ott red flag |
| Group by type, HS farthest from the connector | "Responsible for more crazy board layouts than any other." Place each connector's talkers next to it | LearnEMC |
| 3W rule | A proxy for D/H. Use K = 1/(1+(D/H)²) | Johnson; Ott |
| Guard traces (crosstalk guards between signal traces; not crystal guard rings or driven analog guards) | **CORRECTED** (Bogatin & Simonovich, not "Simonovich, −60 dB"): "−50 dB … perfectly adequate … never a need for a guard trace". Never use one in microstrip. In stripline, short both ends with the lowest-L via and match the coupled length, which gives −70 dB vs −50 dB. λ/10 stitching was *tested* and showed no benefit in some cases. Only 3-D simulation quantifies it | [DesignCon 2013](https://www.signalintegrityjournal.com/ext/resources/article-images-2019/Guard-Traces---Love-Them-or-Leave-Them/4567Guard_Trace_DesignCon-2013-rev14_Final.pdf) [P]; Johnson: guards help only on 2-layer analog boards, grounded at both ends |
| Ground fill on multilayer boards | No function; it perturbs Z0. Floating fill is an Ott red flag | Johnson; Ott |
| Perimeter vias every 2 cm as a Faraday cage | Usually unnecessary, and a perimeter-only ring can form a cavity, so distribute the vias | CONTESTED (Ott stitches the periphery of G/S/S/G) |
| Two ground planes above 25 MHz | Outdated; many GHz boards use one | VERIFIED |
| Terminate beyond λ/4; series R above 1 V/ns; Z ≥ Z0/4 | Not decision criteria. Relate delay to t_r and slow edges first | LearnEMC |
| Single-point for LF, multipoint for HF | Misused. At LF, limit the options; at HF, provide one good path | LearnEMC |
| Minimise all HS trace lengths | Not an EMC fix ("control your loop areas"). People following long guideline lists produce worse boards than people with no guidance | VERIFIED |
| Rely on slow logic | Parts get faster over a product's life. Use slew-controlled logic | VERIFIED |
| Ferrite in ground or a return | Never | LearnEMC |
| 0.1 µF up to 15 MHz, 0.01 µF above; 1 ground per 8 lines | Too narrow; depends on plane spacing | VERIFIED (LearnEMC not-so-good list) |
| Decaps on both sides of a plane gap | "Don't gap the ground plane!" | LearnEMC |
| Ground daughterboards to chassis | "Don't confuse current return paths with grounds": returns belong on connector pins | LearnEMC |
| Rounded or chamfered pair corners remove skew | No: 1.57p–2p per corner regardless | Johnson |
| Tighter pair coupling always reduces EMI | Not below about 0.5 mm | Johnson |
| Follow as many guidelines as possible | 90% compliance can be worse than following only one or two rules | LearnEMC |
| Other anti-rules | "Power traces ≥3× signal width"; ground islands under ICs ("bad idea"); "daisy chain, no stubs" ("sometimes yes, sometimes no"); "ground E-field shields in ≥2 places" ("terrible advice") | [VR] LearnEMC not-so-good |

### Contested rules requiring an explicit selector ([VR] §3)
| Rule | Side A | Side B | Selector |
|---|---|---|---|
| 20-H | Shim & Hubing, LearnEMC: no | Montrose: yes, on high-density multi-plane boards | Board density and plane count |
| Perimeter stitching | Ott: periphery cage (G/S/S/G) | Hubing: distribute to avoid a cavity | Use the largest-unstitched-region metric ([checkers-si-emi.md](checkers-si-emi.md) G) |
| HS pairs: microstrip vs stripline | TI SPRAAR7J: no stripline | Ott (bury HS); TI SNLA426 and Efinix (coupled stripline at Gen4–5) | Via-stub strategy, data rate, fab |
| Termination threshold | LearnEMC, ADI: t_r/2 | Johnson: simulate above t_r/6 | Use both: "review" vs "must" |
| Guard traces | Never in microstrip | Stripline, end-shorted, length-matched | Only for a specific known problem plus 3-D simulation |
| Copper under inductors | TI: top-layer keep-out only, L2 GND kept | Rohm: no ground directly under (eddy-current loss) | Datasheet ([power/buck.md](power/buck.md)) |
| CIN/COUT ground spacing | Rohm: 1–2 cm apart | MPS and TI: short common return | Vendor profile ([power/buck.md](power/buck.md)) |
| "Smallest cap closest" | ADI MT-101 | Bogatin, Archambeault | [decoupling-pdn.md](decoupling-pdn.md) |
| Thermal-via tenting | TI SLOA122: don't | TI SLUA271, Renesas TB389: tent from the top | Fab process |
| PMIC ground cuts | One-ground doctrine | Renesas DA9080 mandates cuts | Datasheet mandate wins |
| Ethernet PHY↔magnetics; ESD side | Pulse ≥25 mm; ESD at the connector | Microchip <1 in; TI ESD on the PHY side | Vendor ([interfaces/ethernet.md](interfaces/ethernet.md)) |
| Crystal can grounding; copper under the crystal | ST: can not tied to osc GND; most: solid ground | TI/AVR: can to ground; CDCE925: cut planes | Vendor ([crystals-clocks.md](crystals-clocks.md)) |

## Recommendations for our system
- Store each myth as a knowledge-base record with `source_type = myth`, the slogan's text patterns (to block it), and a `replacement_check` (for example, 3W → the K-budget clearance).
  - Each record also carries its `source_scope`, so a blocked slogan never strips a rule another doc requires: crystal guard rings ([crystals-clocks.md](crystals-clocks.md)), driven analog guards ([analog-mixed-signal.md](analog-mixed-signal.md)) or isolation barriers ([isolation-creepage.md](isolation-creepage.md)).
- Contested rules carry `contested_by[]` and a `selector`. The system asks the user, or follows the datasheet, and logs the decision with its rationale (see [rule-pack-format.md](rule-pack-format.md)).
- Scope corner-angle rules to the `ESD_UNPROTECTED` and `RF50` net classes, every differential pair, and nets at ≥10 Gb/s.
- When explaining "why not", the LLM should quote the primary verdict (Johnson, LearnEMC). This addresses the user's need to understand why each choice was made.

## Conflicts and open questions
- **20-H:** Archambeault's own 20-H papers were not retrieved, and Shim & Hubing's 3.6 dB figure is NOT RETR.
- **TI "no stripline":** TI does not say what drives this advice, so the selector cannot yet be parameterised from the source alone.

## Sources
- Research notes:
  - [rules_highspeed_emi.md § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
  - [verification_rules.md § 1A, 2, 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- LearnEMC worst guidelines: https://learnemc.com/some-of-the-worst-emc-design-guidelines
- LearnEMC not-so-good guidelines: https://learnemc.com/not-so-good-emc-design-guidelines

See also:
- [si-fundamentals.md](si-fundamentals.md)
- [emc-placement.md](emc-placement.md)
- [rule-pack-format.md](rule-pack-format.md)
