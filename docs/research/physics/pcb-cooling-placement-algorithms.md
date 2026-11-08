<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PCB cooling: placement, heat sinks, trace heating, algorithms

Parts: [overview and decision rules](pcb-cooling.md) · [thermal vias, pours, convection](pcb-cooling-vias-pours.md) · [placement, heat sinks, trace heating, algorithms](pcb-cooling-placement-algorithms.md) · [sources](pcb-cooling-sources.md). Numbers in brackets cite the [sources](pcb-cooling-sources.md); [calc] values come from [pcb_cooling_calc.py](../../../tools/research/physics/pcb_cooling_calc.py).

## 4. Placement for heat

- **Mutual heating and spacing.**
  - Two 0.5 W LFPAKs on a 1-layer board interact when they are < 20 mm apart. [6][S]
  - The physics scale is L (24-48 mm for typical stacks; table in §2). Parts closer than about L share one fin.
    Their temperature rises add roughly as R_self·P_self + R_mutual·P_other, and R_mutual falls roughly as
    K0(d/L).
  - Spread hot parts by ≥ L when each needs its own copper. Cluster them only on a shared plane sized for the sum
    of their powers. [calc S]
  - Shared-copper evidence: dual FETs on a shared 2 mm-gap pour ran about 3 °C hotter than when alone. [6][S]
- **Edge vs centre.**
  - A source at a straight edge loses half of its spreading disc, so R rises by up to about 2× when the pour is
    larger than L. A corner is worse still (about 4×). This follows from the method of images. [calc S]
  - TI's rule is the converse: run the copper from the exposed pad to the board edges. [1][V]
  - Edges help only when they are cooled, i.e. clamped to a chassis or near a vent.
- **Vertical board.** Put the hottest parts high, so hot air rises past them and not past sensitive parts.
  Put sensitive parts at the bottom or beside them. [H]
- **Heat-sensitive parts.**
  - Aluminium electrolytic life halves per +10 °C. Example: 2,000 h at 105 °C → about 16,000 h at 75 °C.
    Ripple self-heating adds to the local board temperature. [28][V]
  - Precision analog and references suffer thermocouple EMFs at dissimilar-metal joints under gradients. Mitigate
    with symmetric layout, small close-spaced parts and distance from heat sources. [29][V]
  - Crystals/oscillators: Microchip's reference design places the crystal away from everything except the MCU
    clock pins. [29][V]
  - Batteries and Li cells: keep below the cell's charge/storage limit, typically ≤ 45 °C charge. [H]
  - Temperature sensors: either co-locate deliberately or isolate by ≥ 2L.
- **Airflow orientation.** Long axes of tall parts go along the flow. Do not put tall parts upstream of hot,
  low-profile parts. [H]
- **Scaling copper per watt.** Area ∝ P holds only while b < L. Beyond that, ΔT ≈ P·R_floor(stack, a), so more
  watts need lower R_floor: more layers, thicker copper, a larger source footprint, a heat sink, or air.
  - 2 layers × 1 oz, two faces: about 15 K/W with a 6 mm source, i.e. ≈ 2.7 W for a 40 K rise.
  - 4 layers × 1 oz: about 8.5 K/W, ≈ 4.7 W.
  - These are upper limits that ignore the package's θJB and the via array. [calc S]
  - TI copper weight guidance: ≥ 1 oz always, 2 oz above 3 W, 4 oz above 6 W (converters). [1][V]
    For converters dissipating ≥ 2 W: 2 oz, and 12 mil vias with ½ oz plating. [30][V]
  - The FR4 limit is about 120-140 °C board temperature directly under low-θJB packages. [6][V]

## 5. Heat sinks

- **Top-of-package sinks.**
  - A sink on a plastic top is in series with θJT ≈ 50-200 °C/W.
  - A sink on the board's back, under the exposed pad and the via array, sees only θJC plus the via array, and is
    far more effective. [1][V]
  - Measured θJC,top ≈ 22 °C/W vs θJB ≈ 1.3 °C/W for a 6 × 6 QFN. [11][V]
  - So for exposed-pad parts, prefer a "board-bottom sink/chassis through a gap pad" over a top clip.
- **Interface θcs for TO-220 class.**
  - With grease: about 0.4-1.0 °C/W. [31][V/H]
  - Dry: 1.0-2.5 °C/W.
  - Thin silicone pad: about 0.35-0.4 °C/W per datasheet; 1.3 °C/W measured on a bench.
  - Mica with grease: about 1.6 °C/W.
  - Electrical isolation multiplies θcs by 3-6×. [31][V/H]
- **Board-to-chassis gap pads.** R = t / (k·A) + contact.
  - Example: 1 mm pad, k = 3 W/mK, under 2 cm² gives ≈ 1.7 K/W. This beats any natural-convection pour and is in
    series with the via array plus FR4 (≈ 1.5e-3 / (0.3·A) for bare FR4; use the via k_z). [calc S]
  - The vias move heat to the sink; they do not remove it. [19][H]
- **When to choose a sink over copper.**
  - Use a sink when the required θ(board→air) is below the copper floor for the available stack, about 15 K/W
    (2L × 1 oz) or 8 K/W (4L × 1 oz), or when the board area within ~L of the part is not free.
  - TI's formula gives a negative or impossibly large area when θJC ≥ θJA,target, which means change the package. [1][V]
- **Keepouts for a placer.** Use the sink footprint plus its clip/screw/standoff and the vendor's courtyard. Keep
  no tall parts within the sink's fin height downstream in the airflow. For back-side sinks or chassis contact,
  keep the bottom copper free of parts and mask-free only where the TIM sits. [H]

## 6. Current-carrying copper heating

- **IPC-2221** (historical NBS chart): I = k·ΔT^0.44·A^0.725, with k = 0.048 external and 0.024 internal (A in mil²).
  - Its "internal" curve was a doubling guess, and internal traces actually run cooler than external ones in still
    air.
  - That internal curve happens to match a trace in free air, so IPC-2152 keeps it as the "conservative chart",
    valid anywhere except vacuum.
  - The old external chart was safe only on boards > 3 × 3 in with planes, and it was dropped. [10][M/V]
- **IPC-2152** (Jouppi / NSWC Crane data): the baseline is a 3 oz trace on 0.070 in polyimide. Modifiers:
  - Copper weight: 1 oz × 0.84.
  - Plane under the trace: × 0.47 for a 1 oz plane 20 mil away; an extra × 0.96 for 2 oz or for planes > 20 in².
  - Board thickness: × 1.08 for 0.062 in.
  - FR4: × 1.02.
  - Vacuum: 35-55% hotter.
  - Worked example: 10 A at 20 K on 1 oz external copper needs a 180 mil trace, vs 250 mil from the old chart. [10][M/V]
  - Vendors summarise this as about 1.5-2× the current of IPC-2221 for the same rise. [18][V]
  - Parallel traces and "local board temperature" add, so evaluate trace rises on top of the component-induced
    field. [10][V]
- For the router, current-carrying pours and traces are heat sources (I²R) in the same board model. Planes under
  power traces are both electrical and thermal assets.

## 7. Algorithms and tools

**Board thermal model for an optimizer loop (recommended stack):**
1. *Effective-conductivity grid (2.5D).* Per tile and layer, take copper fraction × k_Cu + (1 − f)·k_FR4 in-plane,
   with series layers through-plane. Vias add k_z as in §1.
   - In-plane k: 2 × 1 oz on 1.6 mm ≈ 17 W/mK; 4 × 1 oz ≈ 34 W/mK. [calc S]
   - Count continuous copper; ignore isolated thin traces. [23][M]
   - Per-face h boundary condition plus a radiation h_rad, linearised and iterated 2-3 times.
   - Solve with sparse FDM or FEM; 10⁴-10⁵ unknowns solve in milliseconds to tenths of a second with a
     factorised matrix.
   - Open-source example: KiCad "2.5D Thermal Sim" plugin (sparse FDM over all copper layers). [32][H]
2. *Thermal-resistance matrix / superposition.* For fixed copper, T = T_amb + R·P, where R is the board's Green's
   function, precomputed per footprint position or approximated by K0(d/L) kernels with image sources for edges.
   - This is the classic thermally constrained placement method: precompute per-component profiles with an
     analytical multilayer model, then superpose them inside simulated annealing. [21][S]
   - PCB GA placement has used superposition plus a neural-network correction, with large time savings. [22][S]
   - The math for spreading resistance with multiple and eccentric sources on rectangular, multilayer channels is
     the Yovanovich/Muzychka/Culham Fourier-series family. [33][S]
   - Recalculate R only when the copper changes. A placement move changes only P positions, which makes this ideal
     for SA move evaluation.
3. *Compact package models.* Two-resistor (θJC + θJB) or DELPHI-style models connect the junction to the board node;
   use ΨJB to back out Tj from the board temperature: Tj = T_board + ΨJB·P. [3][V], [15][V]
4. *Annular-fin closed form* (§2) gives a cheap per-part initial copper-area estimate and a "floor" check. Shen
   et al. give an iterative algorithm for the minimum pad radius that meets Tj,max, e.g. a DPAK at 0.5 W needs
   r ≥ 2.8 mm and at 1 W r ≥ 5.9 mm (Tj ≤ 125 °C). [8][S/M]
- **Placement cost terms in the literature.** Peak or average Tj above a limit (penalty), Σ over components of
  reliability (Arrhenius) terms, hot-part spacing, and closeness to cooled regions. SA, GA, tabu search and PSO
  have all been used. [21][S], [22][S], [34][S]
- **Thermal-via planning (3D-IC literature, transferable).**
  - Goplen & Sapatnekar place thermal vias into regions by iteratively adjusting each region's effective
    conductivity until temperature targets are met. [35][S]
  - Cong & Zhang use multilevel planning driven by temperature profiling; later work used 68% fewer vias for the
    same temperature. [36][S]
  - Both reduce to: add k_z where ∂T_max/∂k_z per via is largest, subject to routing blockage.
  - For PCBs the gradient is concentrated under the source, and away from it only when no inner plane exists
    (§2).
- **Commercial tools.**
  - Cadence Celsius: 2.5D/3D FEA, electrothermal co-simulation with PI.
  - Siemens Simcenter Flotherm (and Flotherm PCB/XT): CFD from package to system.
  - Ansys Icepak (CFD) with Sherlock: ECAD import into a trace-mapped board model, then solder-fatigue analysis.
  - Altium relies on IPC calculators and partner tools.
  - Most of these import ECAD copper as per-tile conductivity maps. [37][V]
  - KiCad has no built-in thermal solver. [32][H]

## 8. Rules of thumb that are wrong or contested

| Claim | Status and evidence |
|---|---|
| "Use datasheet θJA to compute Tj." | Wrong. θJA is a JEDEC test-board number. PCB design is the strongest factor; 1s vs 2s2p boards differ by up to 50%, and high-K vs low-K boards by 30-45%. [3][V], [34b][V] |
| "More copper area always helps." | Saturates beyond about 1.5-2·L. Shown in simulation (plateaus) [6][S], [7][S] and by fin physics [calc S]. TI notes the same saturation at about 1 in² of 1 oz copper. [38][V] |
| "15 cm² per W." | Valid only for small, nearly isothermal two-sided boards with copper reaching the edges and both faces free. Fails for large pours or one hot spot (spreading floor) and for horizontal face-down boards. [1][V], [13][S] |
| "Pack in as many vias as fit." | Strongly diminishing. 5-9 vias suffice for a small die, and 6×6 gives 90% of 11×11. Many open vias raise wicking and voiding risk. [4][V], [12][S], [17][M] |
| "Bigger vias are better." | Only if filled. Unfilled vias have an optimum near 0.25 mm. [8][S] |
| "Filled vias are needed." | Epoxy or conductive-paste fill gives essentially no thermal gain. Only copper fill helps, at 2-3× board cost. Plugging is an assembly measure. [1][V], [calc S] |
| "Stitch the whole pour densely." | On 4-layer boards with GND planes, adding 0→24 extra vias gave about 0.5%. It matters on 2-layer boards near the source. [2][S] |
| "Solder mask insulates; leave copper bare for cooling." | Mask raises emissivity and lowered θJA by about 5%. [2][M] |
| "IPC-2221 internal traces need 2× the width." | The internal curve is a worst case; internal traces run cooler than external ones. IPC-2152 allows 1.5-2× more current, more with planes. [10][M] |
| "Radiation is negligible." | About 26% of the heat in a validated JEDEC model at ε = 0.5, and 35-40% of h below 1 m/s. [2][S], [11][V] |
| "Thermal relief on everything." | Wrong for exposed pads and thermal vias. [4][V] |
| "Copper hatching kills spreading." | Small effect on outer layers when inner planes exist (+3%). Larger when the hatch is the only spreader. [2][M] |

---
