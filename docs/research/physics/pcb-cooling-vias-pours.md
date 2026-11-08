<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PCB cooling: thermal vias, two-sided pours, convection and radiation

Parts: [overview and decision rules](pcb-cooling.md) · [thermal vias, pours, convection](pcb-cooling-vias-pours.md) · [placement, heat sinks, trace heating, algorithms](pcb-cooling-placement-algorithms.md) · [sources](pcb-cooling-sources.md). Numbers in brackets cite the [sources](pcb-cooling-sources.md); [calc] values come from [pcb_cooling_calc.py](../../../tools/research/physics/pcb_cooling_calc.py).

## 1. Thermal vias

**Single via.** Treat the via as a hollow copper cylinder: R = L/(k_Cu·A_barrel) with
A_barrel = π(r² − (r − t_p)²). This gives TI's 261 K/W for a 12 mil drill, 0.5 oz (17.5 µm) wall and 1.6 mm board.
[1][V] My values with k_Cu = 390 W/mK and L = 1.6 mm [calc S]:

| drill | 18 µm wall | 25 µm | 35 µm | 25 µm + solder fill | 25 µm + Cu fill |
|---|---|---|---|---|---|
| 0.20 mm | 399 K/W | 298 | 226 | 251 | 131 |
| 0.30 mm | 257 | 190 | 141 | 142 | 58 |
| 0.40 mm | 190 | 139 | 102 | 94 | 33 |
| 0.50 mm | 151 | 110 | 80 | 67 | 21 |

- Epoxy (k ≈ 0.3) or "conductive" paste (k ≈ 3-8) filling changes almost nothing (±5%). Plugging is for
  assembly, not for heat. [calc S]
- Copper fill (or VIPPO with plated cap) helps 3-5×. TI: 8 mil plated-closed ≈128 K/W, 12 mil with 1 oz wall
  ≈140 K/W. Plating closed "can double or triple" board cost; heavier plating is a 10-20% adder. [1][V]
- Cree: a 0.6 mm via with 35 µm wall is 441 K/W open vs 96.8 K/W solder-filled, and wicking that does not
  reliably fill the via makes it "not an effective heat management tool". [9][V]
- Resistance scales linearly with board thickness: 0.8 mm board ≈ 95 K/W for 0.3 mm/25 µm. [calc S]

**Arrays.**
- *Parallel model.* Directly under a uniform source, R_array ≈ R_via/N. [1][V] Equivalently, a via field is a
  through-plane conductivity k_z ≈ k_Cu·(A_barrel/p²) + k_FR4. Example: 0.3 mm drill, 25 µm wall, 1 mm pitch gives
  ≈2.2% copper, so k_z ≈ 9 W/mK vs 0.3 for FR4. [calc S] PowerPAD reference patterns have barrel copper of
  ≈1% of the land area. [4][V]
- *Diminishing returns.* FEA of a 10 × 10 mm die: thermal resistance went from 15.9 K/W with no vias down by 90% with
  11 × 11 vias, and 6 × 6 already reached 90% of that reduction. A 1-D parallel model underestimates resistance by up
  to 27% because it ignores spreading in the copper. A circular-fin model with die spreading is within 6%. [12][S]
  TI PowerPAD: 5-9 vias suffice for a small die; more only because space exists. [4][V]
  ROHM: omitting the vias raises θJA by up to 35% (58.4 → 78.8 °C/W for a VQFN 3 × 3 mm). [15][S]
- *Optimum drill and pattern (Shen et al., IEEE TPEL 2019).* Spacing should be as small as manufacturable.
  - Unfilled vias have an optimal drill near 0.25 mm. Using 0.8 mm instead gives +44%.
  - Solder-filled vias have an optimal drill near 0.8 mm. Using 0.2 mm instead gives +23%.
  - A hexagonal pattern has 86.6% of the resistance of a square pattern in the same area.
  - Following the optimal trajectory cut array resistance by 46-90% compared with the vendor reference layouts (GaN Systems, TI).
  - Measured DPAK diodes on 13 × 14 mm pads gave top-case-to-ambient 15.1-17.9 °C/W. Solder-filled vias beat open vias by about 2.5 °C/W (−14%).
  [8][S/M]
- *Small vs large pads (TI AN-1520, FEA on 4L JEDEC).* 0.2 mm instead of 0.33 mm raises θJA by 15-25% when the
  pad holds ≤ 4 vias, and by less than 10% when it holds ≥ 9. Recommended: 0.33 mm vias and 1.2 mm pitch; if the
  pad cannot hold the full count, put the vias near the pad's periphery. [2][S/V]
- *Typical recommendations.* About 1.0 mm pitch with 0.3 mm drill (TI QFN). [5][V] About 1.2 mm pitch with 0.3 mm
  drill (ROHM). [15][V] ADI datasheets use 0.2-0.33 mm at 0.5-1.2 mm pitch. [16][V]

**Filled / tented / plugged / via-in-pad and voiding.**
- Wicking risk. Drill ≤ 0.33 mm with 1 oz surface plating works (TI/Solectron trials). If vias are not plugged,
  cap them on the component side with mask = drill + 0.1 mm. Tenting only from the far side increased voiding,
  from outgassing and trapped air. [4][V], [5][V]
- Solder joint area. TI asks for a solder joint over ≥ 50% of the pad; standard processes reach > 80%. [4][V]
- Voiding. On a JEDEC high-K board, 25% voiding is where thermal returns start to diminish; TI's limit is 50%
  for high-power parts. [5][V]
- FEA of solder coverage: 50% → +4% θJA, 20% → +13%, 10% → +19%, 5% → +34%. [2][S]
- IPC-7093A covers BTC thermal via types, VIPPO and tenting. A ≤ 50% central-pad voiding limit has been proposed,
  and the text could not be verified here. [17][V/H]
- Open via-in-pad wicks solder whatever its diameter, and voiding was measured from < 25% up to 50%. [17][M]
- No thermal reliefs on thermal vias: connect them solidly to every plane. [4][V]

**How much via arrays lower junction temperature.**
- QFN, 4-layer: −26% θJA with vias. [15][S]
- PowerPAD packages on TI's recommended board run 44% cooler than the same die in a standard package. [4][S]
- A DPAK pad with a heat sink: 120 K/W with no vias → 1.9 K/W with vias. This applies only when there is a sink
  or plane on the other side. [8][S]
- Without a second-side spreader (no bottom pour and no plane), vias do almost nothing. They are a conduit, not a
  sink. [19][H], [7][S]

## 2. Two-sided pours + stitching for natural convection (the no-heat-sink case)

**Physics model to implement.** Treat each connected same-net copper region as a fin. A pour of sheet conductance
k·t (sum over the layers tied together by vias, W/K per square) loses heat at h per face. Temperature decays
from the source with length L = √(k·t / h_tot), where h_tot is the summed per-face h. The resistance from a source
of radius a to a disc of radius b is the standard insulated-tip annular-fin solution (Bessel I0/I1/K0/K1). onsemi
uses the same axisymmetric idea with three annular regions (chip, outer plane, effective board). [11][V], calc [S]

Results with h = 12 W/m²K per face, a = 3 mm [calc S]:

| copper | pour radius b → | 10 mm | 20 | 40 | 80 | ∞ |
|---|---|---|---|---|---|---|
| 1 layer 1 oz, one face cooled | | 299 | 82 | 38 | 31 | 30 K/W |
| 2 layers 1 oz stitched, both faces | | 150 | 41 | 19 | 15 | 15 K/W |
| 4 layers 1 oz stitched, both faces | | 148 | 38 | 14 | 9.0 | 8.5 K/W |

Read-outs:
1. Area matters most up to b ≈ L. With 2-layer 1 oz, going from b = 20 to 40 mm halves the resistance, while
   40 → 80 mm gains only 20%.
2. Stitching the two faces doubles the cooled area and the sheet conductance, so the floor drops about 2× vs a
   single face.
3. Extra layers matter more as the pour gets larger.

For small boards (b < L) the board is nearly isothermal, and TI's area rule (≈15 cm²/W for 40 °C, two faces)
reproduces these numbers. [1][V]

**Evidence from vendors/papers.**
- One vs two faces: LFPAK at 0.5 W on a 40 × 40 mm board: Tj 92.1 °C (top 10 × 10 mm only) → 63.0 °C with a
  full bottom plane. [7][S]
- TI 2-layer: a full bottom pour on 3 × 3 in with minimal top copper gave θJA 28.3 °C/W (1 oz) and 21.2 (2 oz). [1][M]
- Plateaus: Nexperia (100 × 100 mm board, 20 °C ambient, 0.5 W per FET):
  - one layer: Tj stops falling at about 40-50 °C, i.e. about 40-60 K/W;
  - four layers with ≤ 25 vias (0.7 mm, 2.5 mm pitch): Tj stops falling at about 33-36 °C, i.e. about 26-32 K/W.
  [6][S]
- Inner planes: 4-layer vs 2-layer −42% [2][M]. EDN: going from 2-layer ½ oz to 4-layer 1.5 oz improves by up to 3×. [20][H/S]
- Where stitching helps:
  - On a 4-layer board with solid inner GND, vias outside the pad region changed θJA by 0.5% or less. [2][S]
  - On 2-layer boards the outer pours are the only spreaders. There, a ring of vias around the part (the
    "dog-bone"/outer zone) helps until about 2-4 rings. [8][S]
  - Once the pours are connected under and next to the source, more stitching across the pour is cheap insurance,
    not a lever.
    - Bare 1.5 mm FR4 between the faces is 50 K/W per cm². With 1 mm-pitch vias it drops to about 1.7 K/W per cm².
    - Both are ≪ the 830 K/W per cm² convection resistance of one face at h = 12.
    - The face-to-face coupling length through bare FR4 is √(k_Cu·t_Cu · t_FR4/k_FR4) ≈ 8 mm for 1 oz. Even
      without vias, the two pours equalise within about 1 cm wherever the heat flux is low.
    - Vias pay off only where flux is concentrated, i.e. under and within a few mm of the source.
    - So stitching every 5-10 mm across the rest of the pour is sufficient, and is mainly an EMC/electrical choice.
    [calc S]
- Pour shape and cuts:
  - Slots perpendicular to radial flow cost 5.5 °C vs 1.5 °C parallel. [1][M]
  - Route other nets' traces radially away from hot parts, never as rings around them. [1][V]
  - Keep the copper continuous next to the package: extending the traces as far as possible lowered θJA by up to
    10% (2 °C/W). [2][S]
  - Measured in-plane conductivity depends on continuous copper thickness, hardly at all on surface circuitry, so
    thin traces count for almost nothing. [23][M]
- Thermal reliefs on pads:
  - For exposed pads and thermal vias, connect solid. [4][V]
  - For through-hole parts and small SMD pads that need hand or wave soldering, reliefs remain. Four
    0.25 mm-wide, 0.25 mm-long spokes in 1 oz copper are ≈ 73 K/W each, ≈ 18 K/W per pad. That is larger than
    a whole 2-layer board's spreading floor. [calc S]
  - Vendor blogs suggest going solid above about 3 A and using preheat instead. [24][H]
  - Software rule: solid connections for the hot part's heat-carrying pins (exposed pad, drain tab, the GND pins
    of an LDO); reliefs elsewhere.

## 3. Convection and radiation

**Natural convection correlations (laminar; air at about 300 K):**

| Surface | Correlation | Characteristic length |
|---|---|---|
| Vertical plate | Nu = 0.59 Ra^¼ for Ra 10⁴-10⁹, or Churchill-Chu | height |
| Hot face up | Nu = 0.54 Ra^¼ for Ra 10⁴-10⁷; 0.15 Ra^⅓ above | A/P |
| Hot face down | Nu = 0.27 Ra^¼ | A/P |

[13][S], [25][S]

The flow stays laminar for ΔT < 100 K and length < 0.5 m, which covers almost all PCBs. A compact form is
h ≈ 1.42·(ΔT/L)^0.25 W/m²K. [8][S]

Worked case: a 15 × 20 cm board, 8 W from one face, ε = 0.8, 20 °C ambient. [13][S]

| Orientation | h_conv | Surface temperature |
|---|---|---|
| Vertical | 5.1 W/m²K | 46 °C |
| Horizontal, face up | 6.8 W/m²K | 42 °C |
| Horizontal, face down | 3.5 W/m²K | 50 °C |

- Vertical mounting gave 15-30% more dissipation than horizontal in measurements. [26][M]
- Stacked horizontal boards are far worse: 97.9 → 127.4 °C going from 5 to 7 boards, vs 64.9 → 65.9 °C vertical. [26][M]

**Radiation.** h_rad = εσ(Ts² + Ta²)(Ts + Ta). [calc S]

| Surface | ε | h_rad at Ts 40-85 °C (Ta 25 °C) |
|---|---|---|
| Solder mask | 0.9 | 5.8-7.3 W/m²K |
| (example) | 0.5 | 3.2-4.0 W/m²K |
| Bare or plated copper | ≈0.05 | ≈0.3 W/m²K |

- Radiation is 35-40% of the "h" below 1 m/s airflow. [11][V]
- Board ε 0.5 → 0.9 lowers θJA by 13%. Solder mask lowers θJA by about 5% vs bare copper. [2][S/M]
- So pours should be mask-covered. Exposed copper or ENIG "heat-spreader windows" radiate worse. Mask colour
  matters little in the IR. [H]
- Radiation to nearby enclosure walls or boards at similar temperature is lost.

**Forced air.** Effective h (convection plus radiation) is about 15, 30 and 45 W/m²K at 0, 1 and 2.5 m/s. [11][V]
TI: airflow can cut the needed board area by up to half. [1][V]
Software: L shrinks as 1/√h, so under forced air copper far from the source matters even less.

**Altitude.** Multiply the sea-level rise by: [14][V]

| Altitude | Natural convection | Fan-cooled |
|---|---|---|
| 1.5 km | 1.10 | 1.20 |
| 3 km | 1.21 | 1.45 |
| 4.5 km | 1.33 | 1.77 |
| 6 km | 1.48 | 2.18 |

- IBM data: 20% hotter at 8,000 ft. [3][V]
- Physics: laminar natural-convection h ∝ ρ^½, so at the stratosphere's ~5 kPa convection is ≈ 20% of sea level,
  while radiation is unchanged. [calc S]
- In vacuum, traces run 35-55% hotter. [10][M]
- Radiation becomes the dominant air-side path at altitude. [27][S]

**Enclosure.** All the area rules assume both faces are free to convect. [1][V] A sealed small box adds an
internal air-to-wall step, so model the inside air as a node.

**Conformal coating.** No measured temperature data found. Coatings are 25-75 µm thick with k ≈ 0.1-0.2 W/mK,
which adds well under 1 K/W per cm² and keeps emissivity high, so the effect is expected to be small. [calc S] [H]
