# PDN and commutation: loop geometry, parallel vias and caps, plane spreading, Kelvin and gate loops, eddy currents

Scope: commutation-loop inductance, via clusters and current sharing, decap mounting and orientation, plane-pair spreading and IR drop, Kelvin sense error, gate loops, eddy currents under inductors. Not here: copper shapes, AC resistance, node/branch classes -> [power-copper](power-copper.md); target impedance -> [decoupling-pdn](../rules/decoupling-pdn.md).
Keys: hot loop, commutation loop, loop inductance, height × squares μ0·h·N□, lateral vs vertical loop, internal-vertical, via cluster spreading inductance, logarithmic in pitch, reverse-return feed, Tichelmann, current sharing, decap mounting inductance, via-in-pad, side vias, alternating orientation, plane-pair spreading, Peaceman, IR drop, decap reach, Kelvin L_err, ESL compensation, gate loop, common-source inductance, eddy current under inductor, Dodd–Deeds, f_ext, inductor cut-out, N7, N8

**Results**
- With a plane within ~0.2 mm, "loop area" stops predicting loop L; the metric is Σ μ0·h·dl/w (height × squares; exact for wide copper, microstrip L′ for narrow), the same Laplace solve as IR drop (§1). Replace area with PEEC nH in N7 (ms per evaluation, image plane), with a terminal-width term, layer choice (lateral, vertical, internal-vertical) and symmetric split cells as a template; [hot-loops](../rules/power/hot-loops.md) mm² tiers are soft scores.
- Parallel vias and caps are coupled: cluster outer size beats via count, decap orientation matters (§2, §3). N8 optimises via-cluster spread and decap orientation (site L from PEEC, spreading L from a one-off Laplace map per rail), not count; count vias for DC ampacity separately.
- Kelvin, gate and inductor coupling are computable (§5–§7): keep the plane under inductors (MPS), never cut a body-sized hole.

[C] scripts: [pw_peec.py](../../../tools/research/physics/pw_peec.py) (filament PEEC with an image plane), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py) (2-D Laplace: plane and terminal spreading, via clusters), [pw_eddy.py](../../../tools/research/physics/pw_eddy.py) (Dodd–Deeds coil over a copper sheet), [pw_cells.py](../../../tools/research/physics/pw_cells.py) (current sharing, ringing).

## 1. Commutation-loop geometry

PEEC filaments with a perfect image plane (inductive limit), validated against closed forms (wire over plane 1–7%; wide strip over plane 1–4% of μ0·h·l/(w+2h)). Image-plane PEEC agrees with FastHenry within 1.3% (4 loops, w/h 0.3–5, 100 MHz; [open-solvers](open-solvers.md)). Loop: l = 4 mm from cap to switch pair, conductor w = 2 mm [C, `pw_peec.py loops`].

| Configuration | Plane / return distance | L (nH) |
|---|---|---|
| Lateral, gap 0.5 mm (15 mm² at centreline) | no plane / 1.5 / 0.5 / 0.2 / 0.1 mm | 4.78 / 4.11 / 2.68 / 1.53 / 0.93 |
| Lateral, gap 3 mm (30 mm²) | no plane / 1.5 / 0.1 mm | 7.71 / 6.23 / 1.23 |
| Vertical, return directly under, 3 vias per end | 0.1 / 0.2 / 0.5 / 1.5 mm | 0.27 / 0.46 / 0.94 / 2.22 (1 via per end: 0.28 / 0.48 / 1.06 / 2.74) |
| Through-board vertical | 0.79 / 1.58 mm | 1.35 / 2.31 (+71%) |
| w = 6 mm, l = 3 mm: internal vertical vs lateral | 0.1 mm | 0.072 vs 0.645 |

**Anchors.** Measured values and sources: [hot-loops](../rules/power/hot-loops.md#lateral-vs-vertical-loops) (SNVA803, EPC WP010) and [AN-139 Table 1](../rules/power/hot-loops.md#measured-loop-inductance-vs-plane-distance). Our model on the same cases:

| Anchor | Our model | Agreement |
|---|---|---|
| SNVA803 ~20 mm² lateral, plane under | 1.0–1.1 nH (18–24 mm², plane 0.1 mm) | matches |
| SNVA803 vertical "2 mm²" | 0.27–0.46 nH (h 0.1–0.2 mm) | matches |
| EPC internal vertical vs best conventional | 71% lower | EPC ~65% |
| EPC vertical loop, 31 → 62 mil board | +71% | EPC up to +80% |
| AN-139 100 mm loop vs plane distance, ratio to 0.12 mm (none / 1.5 / 0.5 / 0.27) | 17.5 / 6.2 / 3.0 / 1.9 (3 mm trace) | measured curve flatter; geometry and fixture unknown |

**Scaling laws** [C, `pw_peec.py scaling`, `pw_sheet.py terminal`]:
- **Overlapped or vertical loops:** L ≈ μ0·h·N□ + via and terminal terms. For a plate of length l between terminal rows of width a, L stops falling once the plate is wider than about a + l:

  | Plate width W | a | 1.5a | 2a | 3a | 6a |
  |---|---|---|---|---|---|
  | L (pH), l = 2 mm, a = 1 mm, h = 0.1 mm | 251 | 178 | 152 | 137 | 133 |

  With 3 mm terminals (e.g. three caps across) L saturates at 64 pH. Widen the source and sink, not the copper. The fixed-area sweep (l·w = 12 mm², 0.41 → 0.026 nH from 6×2 to 1.5×8 mm) holds only while the terminals span the width.
- **Lateral loops over a close plane:** each conductor images itself. L ≈ Σ μ0·h·l_i/w_i (two microstrips in series), so the gap barely matters:

  | Gap s (mm) | 0.2 | 0.5 | 1 | 2 | 4 |
  |---|---|---|---|---|---|
  | L (nH) | 0.89 | 0.93 | 1.00 | 1.12 | 1.35 |

  Width matters (0.5/1/2/4 mm → 1.74/1.25/0.93/0.75 nH) and h matters most. Loop area is the right metric only without a close plane.
- **Symmetric split.** Two mirror-symmetric CIN sets halve each loop's current and give the two loops opposite orientation. MPS reports −6 dB H-field plus further cancellation ([Hedrich, MPS #0030](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf) [P]). It puts the GND layer 70 µm (<100 µm) under the converter.

**Ringing and loss** [C, `pw_cells.py ring`]:
- Ring frequency 1/(2π·√(L·C_oss)): L = 0.3/1/3 nH with C_oss = 1 nF rings at 291/159/92 MHz.
- Overshoot ≈ I·√(L/C_oss): 5.5/10/17 V at 10 A.
- Turn-off energy is ½·L·I²·f, 7.5/25/75 mW at 500 kHz.
- EPC's >4% efficiency loss for 0.4 → 2.9 nH at 1 MHz: ½·ΔL·I²·f at an assumed 20 A gives 0.5 W, about half of 4% of 24 W; overshoot-driven slower switching plausibly explains the rest [I].
- Snubber: R ≈ √(L/C_oss) and C ≈ 3–4 × C_oss, so extracted L sets the BOM.

## 2. Vias: parallel count, pitch and current sharing

Spreading inductance into a plane pair (d = 0.1 mm) from an N-via cluster to a ring 10 mm away [C, `pw_sheet.py cluster`; one via checks against (1/2π)·ln(R/r) within 2%]:

| Vias × pitch | 1 | 2 × 0.6 | 2 × 2 | 4 × 0.6 | 4 × 2 | 9 × 1 | 9 × 2 | 16 × 0.6 | 16 × 1 |
|---|---|---|---|---|---|---|---|---|---|
| L (pH) | 85 | 70 | 59 | 61 | 44 | 41 | 30 | 43 | 34 |
| vs 1 via (ideal 1/N) | 1.00 | 0.82 | 0.69 | 0.71 (0.25) | 0.51 | 0.48 (0.11) | 0.35 | 0.50 (0.06) | 0.40 |

- 4 vias at 2 mm pitch match 16 vias at 0.6 mm. A cluster behaves like one electrode of its outer size: L ≈ (μ0·d/2π)·ln(R/r_eq).
- PEEC via groups show the same in the vertical section: at h = 0.2 mm, 2 vias at 0.5 mm give 0.69× and 8 give 0.29×; at 1.5 mm, 8 give 0.43× [C].
- DC is different: barrels share R as 1/N (~1.1 mΩ each), so DC needs count and HF needs spread.
- **Feeding parallel parts.** Four 2 mΩ FETs on 3 mm, 1 oz buses at 5 mm pitch [C, `pw_cells.py sharing`]:
  - same-end feed gives a max/min current ratio of 9.8;
  - opposite-end (reverse-return, Tichelmann) feed gives 1.8.

  MLCCs at 100 MHz (0.5 nH each) show the same 10.1 vs 1.8; 10 mΩ FETs give 2.1 vs 1.16. What matters is bus impedance comparable to device impedance.

## 3. Decoupling capacitors: mounting, orientation, spreading

0402 on the top side, plane at depth h, cap body modelled as a bar [C, `pw_peec.py caps`]. Values in nH:

| Via style | h = 0.1 mm | h = 0.3 mm | h = 1.0 mm |
|---|---|---|---|
| 0.5 mm tracks to vias 0.7 mm past the pads | 0.79 | 1.29 | 2.43 |
| Via at each pad end | 0.57 | 0.88 | 1.72 |
| 2 vias per pad, beside the pads | 0.44 | 0.56 | 0.88 |
| Via-in-pad / 2 per pad | 0.40 / 0.40 | 0.57 / 0.53 | 1.09 / 0.92 |

- **Against Axotron** (h ≈ 0.3 mm, values in [decoupling-pdn](../rules/decoupling-pdn.md#mounting-inductance-data)) the ranking matches; absolute values run 1.3–2× high because the body is a solid bar.
- **Side vias equal via-in-pad** at no plugging cost, and win once the plane is deep.
- **Two caps at 1 mm pitch** (end vias):

  | Plane depth | 0.1 mm | 0.3 mm | 1.0 mm |
  |---|---|---|---|
  | Same orientation, × single | 0.54 | 0.57 | 0.62 |
  | Alternating orientation, × single | 0.46 | 0.43 | 0.38 |

  This quantifies Archambeault's "alternate power/ground pins", which matters most on deep planes and 2-layer boards.
- **Plane-pair spreading** [C, `pw_sheet.py spread`; 100 × 100 mm plane, Peaceman sub-cell vias r = 0.15 mm]: 1.12/1.34/1.67/1.98 squares at 5/10/25.4/50 mm, L = 105/126/157/187 pH at d = 75 µm.
  - It tracks the infinite-plane (1/π)·ln(D/r) until the edges intervene.
  - It reproduces Archambeault's 1-inch value (157 vs 154 pH) but not the 10-inch one (276 pH at 9 inches on a 10 × 10 inch plane vs 545 pH; anchor geometry unknown; values in [decoupling-pdn](../rules/decoupling-pdn.md#mounting-inductance-data)).
- **Plane-pair capacitance** is 38 pF/cm² at 0.1 mm (εr 4.3), from ε·A/d. Target impedance, flat profiles and the peak criterion are rule values: [decoupling-pdn](../rules/decoupling-pdn.md#target-impedance-and-beyond).

## 4. PDN islands and IR drop

- **One solve per rail.** Feed the regulator pad and sink the loads to get the IR drop (R_s·N□) and the current-density map. The same mask with the IC as sink and d as the plane spacing gives every candidate decap site's spreading L(x) = μ0·d·N□(x). Decap reach is a screened length of 4–24 mm ([cross-domain-lessons](cross-domain-lessons.md)).
- **Shape islands from the field:** loss concentrates in a small share of a full pour, so trimming is cheap ([power-copper §3](power-copper.md#3-trace-vs-pour-vs-plane)); optimised shapes: [copper-shape-synthesis](copper-shape-synthesis.md). DC- and HF-optimal shapes coincide over an unbroken plane and differ across slots.
- **Grid economics.** A via of radius r inside a grid cell Δx adds (1/2π)·ln(0.198·Δx/r) squares (Peaceman's well model from reservoir simulation), so a 1 mm grid can model 0.3 mm vias on a whole board [C].
- **Via fields are necks** (antipad multiplier table: [power-copper §3](power-copper.md#3-trace-vs-pour-vs-plane)): check every BGA and connector field on the rail path.

## 5. Kelvin sensing and sense loops

The measured voltage is V = φ(s₁) − φ(s₀) − jω∫A·dl along the sense wires, with φ the PEEC node potential and A from all currents. 2512 shunt with its resistive element 0.3 mm above top copper, plane 0.2 mm below [C, `pw_peec.py kelvin`]:

| Sense route | L_err (pH) | Error per A/µs | L/R corner with 1 mΩ |
|---|---|---|---|
| Taps leave separately, join 10 mm away | 873 | 0.87 mV | 182 kHz |
| Taps converge 1.8 mm out, then a tight pair | 711 | 0.71 mV | 224 kHz |
| One sense trace returns under the element | 551 | 0.55 mV | 289 kHz |

- **Most of the error is the element's own field**, between element and plane; over a close plane the sense loop's plan-view area adds almost nothing.
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

  The fall-off is roughly 1/d³ over a plane, so distance and loop area are worth more than the vendor 1–2 mm keep-outs suggest; the budget for a 20 mV shunt signal decides. Replace fixed keep-outs with a victim ledger: M from each high-di/dt loop to each sensitive loop (FB, sense, gate return, reference) against a mV budget. Kelvin critic: compute the routed sense path's L_err and emit τ_RC = L_err/R as a BOM constraint.

## 6. Gate loops and common-source inductance

- **Gate loop** 10 mm long, 0.5 mm traces [C, `pw_peec.py gate`]:
  - split traces on one layer with a 1 mm / 0.2 mm gap: 5.9 / 4.7 nH;
  - stacked on adjacent layers 0.1 mm apart: 2.2 nH.
- **EPC overshoot-free bound** L_G ≤ ¼·R_G²·C_GS:
  - 0.34 nH for R_G 1.5 Ω and C_GS 0.6 nF (GaN-like), so the driver must sit within about 1–2 mm on a stacked pair;
  - 18.8 nH for 5 Ω and 3 nF (Si): generous.
- **Common-source inductance** couples the power loop into the gate loop: 0.2 nH × 5 A/ns = 1 V off the gate drive. A Kelvin source net tie removes it ([gate-drive-bootstrap](../rules/power/gate-drive-bootstrap.md)).

## 7. Eddy currents under inductors (the contested rule)

The winding is modelled as an air-coil equivalent (radii 1.5–3 mm, 0.5–3.5 mm above the board) over one copper layer, using the Dodd–Deeds spectral solution. The perfect-conductor limit equals −M(image) to 4 digits [C, `pw_eddy.py`].

| Plane position | ΔL/L_air at 100 kHz / 500 kHz / 2 MHz (35 µm) | Perfect conductor |
|---|---|---|
| Top-layer pour directly under | −17.5 / −25.0 / −25.6% | −25.9% |
| L2, 0.1 mm down | −15.9 / −22.4 / −22.9% | −23.2% |
| Bottom, 1.6 mm down | −4.8 / −5.9 / −5.9% | −6.0% |

- **The sheet is already a mirror at switching frequencies** (onset 12–125 kHz, [power-copper §5](power-copper.md#5-ac-effects)), so loss saturates instead of growing with f².
- **Only ripple makes eddies**, not DC.
- **Scaling to real parts.** Multiply by the share f_ext of the inductor's field energy outside its core [I]. Worked example: 3.3 µH, 500 kHz, 1.5 A p-p, plane at L2:

  | Inductor type | f_ext [I] | Eddy loss | ΔL |
  |---|---|---|---|
  | Open drum | ~0.4 | 24 mW | −6.4% |
  | Semi-shielded | ~0.07 | 4 mW | −1.1% |
  | Shielded / molded | ~0.01 | 0.6 mW | −0.16% |

  Its own DCR loss is ~500 mW at 5 A.
- **Measurements:**
  - MPS: copper "somewhat reduces the effective inductance of the coil (typically less than 5%)", and a plane on the component side keeps the field off the bottom and cables ([Hedrich](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf) [P]).
  - A grounded sheet raised peak current ~8% only with an unshielded inductor ([MPS article via repost](https://www.linkedin.com/pulse/beneficial-lay-copper-under-dc-power-supply-livia-qiu) [S]).
  - A usenet bench test: 22 µH SRU1048 at 500 kHz, −3%, and −1.5% with a 10 mm hole ([thread](https://www.electronics-related.com/showthread/sci.electronics.design/524048-3.php) [S]).
- **Resolution.** Rohm's "no ground under the inductor" protects L and Q for open-flux cores close to a plane. TI's "keep L2, clear top copper" limits SW → VOUT capacitance. MPS's "copper under the coil" buys H-field shielding. They are one trade with different weights. Default to a solid plane. Never cut a body-sized hole: its rim still carries eddy current, so loss rises 1.05–1.4× and most shielding is lost. Only a cut-out ≥ 2–3× the winding radius cuts loss and ΔL (to 3–50%, 0.5–2 MHz), and it unshields lower layers; consider it only for open drum cores within ~0.5 mm, at high ripple, with no EMI requirement [C, [da_inductor_cutout.py](../../../tools/research/physics/da_inductor_cutout.py)]. Copper-under-inductor selector: inputs shield class, ripple, f_sw, plane depth, cut-out radius; outputs ΔL and P_eddy; default keep the plane; never offer a body-sized cut-out.

## Open questions

- **f_ext values and the cut-out model are assumptions** (the latter axisymmetric, air-core). Calibrate with one LCR measurement per inductor family, with and without plane and cut-out, or a magnetostatic FEM.
- **The Kelvin L_err assumes the taps sit at the element ends.**
- **Licences.** FastHenry is non-commercial and Ki-PIDA AGPL ([open-solvers](open-solvers.md)); our PEEC and Laplace solvers (GPL-3.0-or-later), padne and KiPI (GPL-3.0) are safe.

## Sources

- research notes: [rules_power_rf_analog_dfm.md § 1, § 2, § 17](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [constraints_verification_benchmarks.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md) (padne, KiPI)
- J. Hedrich, MPS Article #0030, "PCB Design for Low-EMI DC/DC Converters" ([PDF](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf)) [P]
- C. V. Dodd, W. E. Deeds, J. Appl. Phys. 39(6):2829 (1968), [doi:10.1063/1.1656680](https://doi.org/10.1063/1.1656680) [S]; A. E. Ruehli, IBM J. R&D 16(5), 1972 [S]; F. W. Grover, *Inductance Calculations*, 1946 [S]; D. W. Peaceman, SPE J. 18(3), 1978 [S]
- Anchors via [hot-loops](../rules/power/hot-loops.md) and [decoupling-pdn](../rules/decoupling-pdn.md): TI SNVA803, EPC WP010, AN-139, Axotron, Archambeault [P per those docs]

See also: [copper-shape-synthesis](copper-shape-synthesis.md), [open-solvers](open-solvers.md), [fields-si-emi](fields-si-emi.md), [physics-critics](physics-critics.md), [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md), [../rules/power/current-sense-kelvin.md](../rules/power/current-sense-kelvin.md), [power ideas](../../ideas/physics-first/power.md)
