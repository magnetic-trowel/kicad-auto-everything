# PDN and commutation: loop geometry, parallel vias and caps, plane spreading, Kelvin and gate loops, eddy currents

*Tags: [P] primary source read, [S] snippet or secondary, [V] vendor claim, [I] our inference, [C] computed by us.*
*Scripts: [pw_peec.py](../../../tools/research/physics/pw_peec.py) (filament PEEC with an image plane), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py) (2-D Laplace: plane spreading, via clusters, terminal spreading), [pw_eddy.py](../../../tools/research/physics/pw_eddy.py) (Dodd–Deeds coil over a copper sheet), [pw_cells.py](../../../tools/research/physics/pw_cells.py) (current sharing, ringing). Copper shapes, AC resistance and the node/branch classification are in [power-copper](power-copper.md).*

**TL;DR**
- **With a plane within about 0.2 mm, "loop area" stops predicting loop inductance.** In a 4 × 2 mm lateral loop over a plane 0.1 mm down [C]:
  - widening the go/return gap from 0.2 to 4 mm only moves L from 0.89 to 1.35 nH;
  - plane distance moves it 0.93 → 4.1 nH (0.1 → 1.5 mm);
  - conductor width moves it 1.74 → 0.75 nH (0.5 → 4 mm).

  The right metric is Σ μ0·h·dl/w (height × squares; exact for wide copper, microstrip L' for narrow). It is the same Laplace solve as IR drop.
- **Internal-vertical loops beat lateral loops by about 3.5×** (0.27 vs 0.93 nH, same footprint, 0.1 mm dielectric) [C]. That matches EPC's "about 65% lower". A through-board vertical loop is worse (2.2 nH). Its inductance rises 71% from 0.8 to 1.6 mm board thickness (EPC: up to 80%). Widening a loop helps only up to W ≈ terminal width + loop length; past that, widen the terminals (more caps across).
- **Parallel vias and caps are coupled.** In a plane pair, 4 vias at 0.6 mm pitch give 0.71× one via's spreading inductance, not 0.25×; 4 vias at 2 mm give 0.51× [C]. The cluster's outer size matters more than via count. Alternating decap orientation is 16–39% lower than same-orientation, more so with deeper planes. Side vias match via-in-pad. N8 should optimise cluster geometry and orientation, not count.
- **Plane-pair spreading inductance is μ0·d·N□.** 157 pH for 1 inch at d = 75 µm reproduces Archambeault's 154 pH [C]. IR drop, spreading L and decap reach come from one solver.
- **Kelvin, gate and inductor coupling are computable** [C]:
  - a 2512 shunt's sense voltage carries 0.55–0.87 nH of inductive error, depending on the sense route, so the L/R corner of a 1 mΩ shunt is 180–290 kHz;
  - a GaN gate loop must stay under ~0.34 nH, while a 10 mm loop is 2–6 nH;
  - a plane under a shielded inductor costs about 0.2% of L and under 1 mW, and under an open drum core up to ~6% and ~24 mW.

  So the default is to keep the plane, which agrees with MPS.

## Key facts

### 1. Commutation-loop geometry

PEEC filaments with a perfect image plane (inductive limit). The method was validated against closed forms (wire over plane within 1–7%; wide strip over plane within 1–4% of μ0·h·l/(w+2h)). Image-plane PEEC agrees with FastHenry within 1.3% ([open-solvers](open-solvers.md)). Loop: l = 4 mm from cap to switch pair, conductor w = 2 mm [C, `pw_peec.py loops`].

| Configuration | Plane / return distance | L (nH) |
|---|---|---|
| Lateral, gap 0.5 mm (15 mm² at centreline) | no plane / 1.5 / 0.5 / 0.2 / 0.1 mm | 4.78 / 4.11 / 2.68 / 1.53 / 0.93 |
| Lateral, gap 3 mm (30 mm²) | no plane / 1.5 / 0.1 mm | 7.71 / 6.23 / 1.23 |
| Vertical, return directly under, 3 vias per end | 0.1 / 0.2 / 0.5 / 1.5 mm | 0.27 / 0.46 / 0.94 / 2.22 (1 via per end: 0.28 / 0.48 / 1.06 / 2.74) |
| Through-board vertical | 0.79 / 1.58 mm | 1.35 / 2.31 (+71%) |
| w = 6 mm, l = 3 mm: internal vertical vs lateral | 0.1 mm | 0.072 vs 0.645 |

**Anchors** ([hot-loops](../rules/power/hot-loops.md)):

| Anchor | Measured | Our model |
|---|---|---|
| SNVA803: ~20 mm² lateral, plane under | >1 nH | 1.0–1.1 nH (18–24 mm², plane 0.1 mm) |
| SNVA803: vertical "2 mm²" | <0.5 nH | 0.27–0.46 nH (h 0.1–0.2 mm) |
| EPC: internal vertical vs best conventional | ~65% lower | 71% lower |
| EPC: vertical loop, 31 → 62 mil board | up to +80% | +71% |
| AN-139: 100 mm loop vs plane distance, ratio to 0.12 mm (none / 1.5 / 0.5 / 0.27) | 14.4 / 3.2–4.1 / 1.77 / 1.61 | 17.5 / 6.2 / 3.0 / 1.9 (3 mm trace; measured curve flatter, geometry and fixture unknown) |

**Scaling laws** [C, `pw_peec.py scaling`, `pw_sheet.py terminal`]:
- **Overlapped or vertical loops:** L ≈ μ0·h·N□ + via and terminal terms. For a plate of length l between terminal rows of width a, L stops falling once the plate is wider than about a + l:

  | Plate width W | a | 1.5a | 2a | 3a | 6a |
  |---|---|---|---|---|---|
  | L (pH), l = 2 mm, a = 1 mm, h = 0.1 mm | 251 | 178 | 152 | 137 | 133 |

  With 3 mm terminals (for example three caps across) L saturates at 64 pH. Widen the source and sink, not the copper. The fixed-area sweep (l·w = 12 mm², 0.41 → 0.026 nH from 6×2 to 1.5×8 mm) holds only while the terminals span the width.
- **Lateral loops over a close plane:** each conductor images itself. L ≈ Σ μ0·h·l_i/w_i (two microstrips in series), so the gap barely matters:

  | Gap s (mm) | 0.2 | 0.5 | 1 | 2 | 4 |
  |---|---|---|---|---|---|
  | L (nH) | 0.89 | 0.93 | 1.00 | 1.12 | 1.35 |

  Width matters (0.5/1/2/4 mm → 1.74/1.25/0.93/0.75 nH) and h matters most. "Minimise loop area" is the right metric only without a close plane.
- **Symmetric split.** Two CIN sets placed mirror-symmetrically at the switches halve each loop's current and make the loops opposite in orientation. MPS reports −6 dB H-field plus further cancellation ([Hedrich, MPS #0030](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf) [P]). The same article puts the GND layer <100 µm (70 µm) under the converter.

**Ringing and loss** [C, `pw_cells.py ring`]:
- Ring frequency is 1/(2π·√(L·C_oss)). L = 0.3/1/3 nH with C_oss = 1 nF rings at 291/159/92 MHz.
- Overshoot ≈ I·√(L/C_oss): 5.5/10/17 V at 10 A.
- Turn-off energy is ½·L·I²·f, 7.5/25/75 mW at 500 kHz.
- EPC's >4% efficiency loss for 0.4 → 2.9 nH at 1 MHz: ½·ΔL·I²·f at an assumed 20 A gives 0.5 W, about half of 4% of 24 W. Overshoot-driven slower switching is a plausible remainder [I].
- Snubber: R ≈ √(L/C_oss) and C ≈ 3–4 × C_oss, so extracted L sets the BOM.

### 2. Vias: parallel count, pitch and current sharing

Spreading inductance into a plane pair (d = 0.1 mm) from an N-via cluster to a ring 10 mm away [C, `pw_sheet.py cluster`; one via checks against (1/2π)·ln(R/r) within 2%]:

| Vias × pitch | 1 | 2 × 0.6 | 2 × 2 | 4 × 0.6 | 4 × 2 | 9 × 1 | 9 × 2 | 16 × 0.6 | 16 × 1 |
|---|---|---|---|---|---|---|---|---|---|
| L (pH) | 85 | 70 | 59 | 61 | 44 | 41 | 30 | 43 | 34 |
| vs 1 via (ideal 1/N) | 1.00 | 0.82 | 0.69 | 0.71 (0.25) | 0.51 | 0.48 (0.11) | 0.35 | 0.50 (0.06) | 0.40 |

- 4 vias at 2 mm pitch match 16 vias at 0.6 mm. A cluster behaves like one electrode of its outer size: L ≈ (μ0·d/2π)·ln(R/r_eq).
- PEEC via-to-plane groups show the same thing in the vertical section. At h = 0.2 mm, 2 vias at 0.5 mm give 0.69× and 8 give 0.29×. At h = 1.5 mm, 8 vias give 0.43× [C].
- DC is different: barrels share R as 1/N (~1.1 mΩ each), so DC needs count and HF needs spread.
- **Feeding parallel parts.** Four 2 mΩ FETs on 3 mm, 1 oz buses at 5 mm pitch [C, `pw_cells.py sharing`]:
  - same-end feed gives a max/min current ratio of 9.8;
  - opposite-end (reverse-return, Tichelmann) feed gives 1.8.

  MLCCs at 100 MHz (0.5 nH each) show the same 10.1 vs 1.8. With 10 mΩ FETs it is 2.1 vs 1.16. Bus impedance comparable to device impedance is the condition that matters.

### 3. Decoupling capacitors: mounting, orientation, spreading

0402 on the top side, plane at depth h, cap body modelled as a bar [C, `pw_peec.py caps`]. Values in nH:

| Via style | h = 0.1 mm | h = 0.3 mm | h = 1.0 mm |
|---|---|---|---|
| 0.5 mm tracks to vias 0.7 mm past the pads | 0.79 | 1.29 | 2.43 |
| Via at each pad end | 0.57 | 0.88 | 1.72 |
| 2 vias per pad, beside the pads | 0.44 | 0.56 | 0.88 |
| Via-in-pad / 2 per pad | 0.40 / 0.40 | 0.57 / 0.53 | 1.09 / 0.92 |

- **Against Axotron** (h ≈ 0.3 mm: 0.63 tracks, 0.44 via-in-pad, [decoupling-pdn](../rules/decoupling-pdn.md)), the ranking matches. Absolute values run 1.3–2× high, because the body is modelled as a solid bar.
- **Side vias equal via-in-pad** at no plugging cost. They win once the plane is deep.
- **Two caps at 1 mm pitch** (end vias):

  | Plane depth | 0.1 mm | 0.3 mm | 1.0 mm |
  |---|---|---|---|
  | Same orientation, × single | 0.54 | 0.57 | 0.62 |
  | Alternating orientation, × single | 0.46 | 0.43 | 0.38 |

  This quantifies Archambeault's "alternate power/ground pins": it matters most on deep planes and 2-layer boards.
- **Plane-pair spreading** [C, `pw_sheet.py spread`; 100 × 100 mm plane, Peaceman sub-cell vias r = 0.15 mm]: 1.12/1.34/1.67/1.98 squares at 5/10/25.4/50 mm, which is L = 105/126/157/187 pH at d = 75 µm.
  - It tracks the infinite-plane (1/π)·ln(D/r) until the edges intervene.
  - It reproduces Archambeault's 154 pH at 1 inch. It does not reproduce 545 pH at 10 inches (we get 276 pH at 9 inches on a 10 × 10 inch plane): the anchor geometry is unknown.
- **Plane-pair capacitance** is 38 pF/cm² at 0.1 mm (εr 4.3). Target impedance, flat profiles and the 1.57×Z_t peak criterion are in [decoupling-pdn](../rules/decoupling-pdn.md) and not repeated here.

### 4. PDN islands and IR drop

- **One solve per rail.** Feed the regulator pad and sink the loads to get the IR drop (R_s·N□) and the current-density map. The same mask with the IC as sink and d as the plane spacing gives every candidate decap site's spreading L(x) = μ0·d·N□(x). Decap reach is a screened length of 4–24 mm ([cross-domain-lessons](cross-domain-lessons.md)).
- **Shape islands from the field.** In a full pour, 50% of the loss sits in 19% of the area. Trimming 28% of the area costs +9% R ([power-copper §3](power-copper.md#3-trace-vs-pour-vs-plane)). Optimised shapes are in [copper-shape-synthesis](copper-shape-synthesis.md). DC- and HF-optimal shapes coincide over an unbroken plane and differ across slots.
- **Grid economics.** A via of radius r inside a grid cell Δx adds (1/2π)·ln(0.198·Δx/r) squares. This is Peaceman's well model from reservoir simulation, and it lets a 1 mm grid model 0.3 mm vias on a whole board [C].
- **Via fields are necks.** Antipads multiply plane R by 1.8–5× (D/p 0.6–0.9). Check every BGA and connector field on the rail path ([power-copper §3](power-copper.md#3-trace-vs-pour-vs-plane)).

### 5. Kelvin sensing and sense loops

The measured voltage is V = φ(s₁) − φ(s₀) − jω∫A·dl along the sense wires. Here φ is the PEEC node potential and A comes from all currents. 2512 shunt with its resistive element 0.3 mm above top copper, plane 0.2 mm below [C, `pw_peec.py kelvin`]:

| Sense route | L_err (pH) | Error per A/µs | L/R corner with 1 mΩ |
|---|---|---|---|
| Taps leave separately, join 10 mm away | 873 | 0.87 mV | 182 kHz |
| Taps converge 1.8 mm out, then a tight pair | 711 | 0.71 mV | 224 kHz |
| One sense trace returns under the element | 551 | 0.55 mV | 289 kHz |

- **Most of the error is the element's own field.** It sits between the element and the plane. The sense loop's area in the board plane adds almost nothing over a close plane.
- **Fixes:**
  - route a sense trace back under the element;
  - use 4-terminal parts with low internal loop;
  - match the filter, τ_RC = L_err/R_shunt (the classic ESL compensation).

  The RC belongs at the IC ([current-sense-kelvin](../rules/power/current-sense-kelvin.md)).
- **Pickup from a hot loop** (lateral, plane 0.2 mm, 5 A/ns) into a 10 mm long sense loop:

  | Sense loop | at 3 mm | at 10 mm |
  |---|---|---|
  | 30 mm² (3 mm wide) | 17 mV | 0.43 mV |
  | 1 mm² (0.1 mm wide) | 1.5 mV | 0.02 mV |

  The fall-off is roughly 1/d³ with a plane. Over a plane, distance and loop area are worth more than the vendor 1–2 mm keep-outs suggest. The budget for a 20 mV shunt signal decides.

### 6. Gate loops and common-source inductance

- **Gate loop** 10 mm long, 0.5 mm traces [C, `pw_peec.py gate`]:
  - split traces on one layer with a 1 mm / 0.2 mm gap: 5.9 / 4.7 nH;
  - stacked on adjacent layers 0.1 mm apart: 2.2 nH.
- **EPC overshoot-free bound** L_G ≤ ¼·R_G²·C_GS:
  - 0.34 nH for R_G 1.5 Ω and C_GS 0.6 nF (GaN-like), so the driver must sit within about 1–2 mm on a stacked pair;
  - 18.8 nH for 5 Ω and 3 nF (Si), which is generous.
- **Common-source inductance** couples the power loop into the gate loop: 0.2 nH × 5 A/ns = 1 V off the gate drive. A Kelvin source net tie removes the shared segment ([gate-drive-bootstrap](../rules/power/gate-drive-bootstrap.md)).

### 7. Eddy currents under inductors (the contested rule)

The winding is modelled as an air-coil equivalent (radii 1.5–3 mm, 0.5–3.5 mm above the board) over one copper layer, using the Dodd–Deeds spectral solution. The perfect-conductor limit equals −M(image) to 4 digits [C, `pw_eddy.py`].

| Plane position | ΔL/L_air at 100 kHz / 500 kHz / 2 MHz (35 µm) | Perfect conductor |
|---|---|---|
| Top-layer pour directly under | −17.5 / −25.0 / −25.6% | −25.9% |
| L2, 0.1 mm down | −15.9 / −22.4 / −22.9% | −23.2% |
| Bottom, 1.6 mm down | −4.8 / −5.9 / −5.9% | −6.0% |

- **The sheet is already a mirror at switching frequencies.** Its onset is 12–125 kHz ([power-copper §5](power-copper.md#5-ac-effects)). Loss therefore saturates instead of growing with f².
- **Only the ripple matters.** DC current makes no eddies.
- **Scaling to real parts.** Multiply by the share f_ext of the inductor's field energy outside its core [I]. Worked example: 3.3 µH, 500 kHz, 1.5 A p-p, plane at L2:

  | Inductor type | f_ext [I] | Eddy loss | ΔL |
  |---|---|---|---|
  | Open drum | ~0.4 | 24 mW | −6.4% |
  | Semi-shielded | ~0.07 | 4 mW | −1.1% |
  | Shielded / molded | ~0.01 | 0.6 mW | −0.16% |

  Compare the inductor's own DCR loss of ~500 mW at 5 A.
- **Measurements:**
  - MPS: copper "somewhat reduces the effective inductance of the coil (typically less than 5%)", and a plane on the component side keeps the field off the bottom and cables ([Hedrich](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf) [P]).
  - A grounded sheet raised peak current ~8% only with an unshielded inductor ([MPS article via repost](https://www.linkedin.com/pulse/beneficial-lay-copper-under-dc-power-supply-livia-qiu) [S]).
  - A usenet bench test: 22 µH SRU1048 at 500 kHz, −3%, and −1.5% with a 10 mm hole ([thread](https://www.electronics-related.com/showthread/sci.electronics.design/524048-3.php) [S]).
- **Resolution.** Rohm's "no ground under the inductor" protects L and Q for open-flux cores close to a plane. TI's "keep L2, clear top copper" limits SW → VOUT capacitance. MPS's "copper under the coil" buys H-field shielding. They are one trade with different weights. Default to a solid plane. Consider a cut-out only for open drum cores within ~0.5 mm, at high ripple, with no EMI requirement.

## Recommendations for our system

- **N7 objective.** Replace area with PEEC nH (ms per evaluation, image plane). Add a terminal-width term and layer choice (lateral, vertical, internal-vertical), and add symmetric split cells as a template.
- **N8 objective.** Optimise via-cluster spread and decap orientation, with site L from PEEC and spreading L from a one-off Laplace map per rail. Count vias for DC ampacity separately.
- **Victim ledger.** M between each high-di/dt loop and each sensitive loop (FB, sense, gate return, reference), checked against a mV budget, replaces fixed keep-out distances.
- **Kelvin critic.** Compute L_err for the routed sense path and emit τ_RC = L_err/R as a BOM constraint.
- **Copper-under-inductor selector.** Inputs: shield class, ripple, f_sw, plane depth. Output: ΔL and P_eddy. Default: keep the plane.

## Conflicts and open questions

- **[hot-loops](../rules/power/hot-loops.md) tiers in mm².** These are soft scores, and our data show area is a poor proxy over a close plane. Prefer nH.
- **Archambeault's 10-inch spreading anchor** and AN-139's flat curve are not reproduced; both geometries are unknown.
- **f_ext values are assumptions.** Calibrate them with one bench measurement per inductor family (LCR meter, with and without plane) or a magnetostatic FEM.
- **The cap model is crude** (solid-bar body). The Kelvin L_err assumes the taps sit at the element ends.
- **Licences.** FastHenry carries a non-commercial notice and Ki-PIDA is AGPL ([open-solvers](open-solvers.md)). Our own PEEC and Laplace solvers (GPL-3.0-or-later), padne and KiPI (GPL-3.0) are safe.

## Sources

- research notes: [rules_power_rf_analog_dfm.md § 1, § 2, § 17](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [constraints_verification_benchmarks.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md) (padne, KiPI)
- J. Hedrich, MPS Article #0030, "PCB Design for Low-EMI DC/DC Converters" ([PDF](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf)) [P]
- C. V. Dodd, W. E. Deeds, J. Appl. Phys. 39(6):2829 (1968), [doi:10.1063/1.1656680](https://doi.org/10.1063/1.1656680) [S]; A. E. Ruehli, IBM J. R&D 16(5), 1972 [S]; F. W. Grover, *Inductance Calculations*, 1946 [S]; D. W. Peaceman, SPE J. 18(3), 1978 [S]
- Anchors via [hot-loops](../rules/power/hot-loops.md) and [decoupling-pdn](../rules/decoupling-pdn.md): TI SNVA803, EPC WP010, AN-139, Axotron, Archambeault [P per those docs]

See also: [power-copper](power-copper.md), [copper-shape-synthesis](copper-shape-synthesis.md), [open-solvers](open-solvers.md), [fields-si-emi](fields-si-emi.md), [physics-critics](physics-critics.md), [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md), [../rules/power/current-sense-kelvin.md](../rules/power/current-sense-kelvin.md), [power ideas](../../ideas/physics-first/power.md)
