<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PCB cooling without (and with) heat sinks: numbers for an automated placer and router

Date: 2026-11-02. Scope: board-level conduction, natural/forced convection, radiation, thermal vias,
copper pours, placement, heat sinks, trace heating, and algorithms that fit inside an optimizer loop.

Tags: source number in brackets, then confidence: **[M]** measured, **[S]** simulated or computed,
**[V]** vendor guidance, **[H]** heuristic/forum. "calc" means my own calculation from the stated
physics (reproducible; formulas given), marked [S].

---

Parts: [overview and decision rules](pcb-cooling.md) · [thermal vias, pours, convection](pcb-cooling-vias-pours.md) · [placement, heat sinks, trace heating, algorithms](pcb-cooling-placement-algorithms.md) · [sources](pcb-cooling-sources.md). Numbers in brackets cite the [sources](pcb-cooling-sources.md); [calc] values come from [pcb_cooling_calc.py](../../../tools/research/physics/pcb_cooling_calc.py).

## Summary: what matters for software decisions

1. **The board is the heat sink.** For exposed-pad and power packages, 70-95% of the heat leaves through the
   PCB in JEDEC still-air tests, and θJA is a property of the test board, not the part. Software should model
   θJA ≈ θJB (or θJC,bottom) + θ(board→air) and never use the datasheet θJA for a design. [3][V], [11][V]
2. **Board-to-air is ~10-13 W/m²K per face** in still air at sea level: about 4-7 W/m²K convection, plus 5-7 W/m²K
   radiation at ε≈0.9 (solder mask). A face pointing down convects about half as well as one pointing up
   (3.5 vs 6.8 W/m²K in a worked case). [1][V], [13][S], calc [S]
3. **The "15 cm² per W" rule works only for small, nearly isothermal boards.** TI: about 15.3 cm² of board
   (copper fills on both faces) per W for a 40 °C rise, or area = 500 °C·cm²/W ÷ (θJA,target − θJC). [1][V]
   A copper pour has a characteristic spreading length L = √(k·t / h_total). For 2-layer 1 oz copper cooled on
   both faces, L ≈ 34 mm (48 mm for 2 oz or 4 × 1 oz). Copper beyond a radius of about 1.5-2·L buys less than 10%.
   For a 6 mm source on 2-layer 1 oz, board-to-air bottoms out near 15 K/W however large the pour (≈8.5 K/W
   for 4 × 1 oz). [calc S], consistent with [6][S] and [7][S]
4. **Copper area has strongly diminishing returns, measured and simulated.** LFPAK at 0.5 W on a 40 × 40 mm board,
   one copper layer: growing the top pad from 10 to 25 mm cut Tj from 92 °C to 56 °C, with each step worth less
   (−22%, −14%, −9%). Adding a bottom plane at x = 10 mm gave 63 °C. Inner planes plus 20 vias made Tj almost
   independent of top copper area. [7][S] On a 100 × 100 mm board, Tj plateaus at a level that extra copper
   does not lower. [6][S]
5. **Layers and copper weight beat area.** 2-layer → 4-layer cut θJA by 42% (43.4 → 25 °C/W). [2][M]
   1 oz → 2 oz on a 3 × 3 in 2-layer board cut it by 25% (28.3 → 21.2 °C/W). [1][M/V]
   Inner ground planes can improve even a good 2-layer design by up to 30%. [1][V]
6. **Thermal via:** R = t_board / (k_Cu · π(r² − (r − t_p)²)).
   - 0.3 mm drill, 25 µm plating, 1.6 mm board: ≈190 K/W. TI's figure is 261 K/W (0.5 oz plating).
   - Arrays combine in parallel only directly under the source.
   - A small die needs only 5-9 vias; a 6 × 6 array gives 90% of the benefit of 11 × 11.
   [1][V], [4][V], [12][S], calc [S]
7. **Via drill vs fill.**
   - Unfilled vias have an optimum drill of about 0.25 mm. Going to 0.8 mm raises the array's resistance by 44%.
   - Solder-filled vias have an optimum of about 0.8 mm.
   - A hexagonal (staggered) array has 0.866× the resistance of a square one of the same area.
   - In measurements, solder fill lowered top-case-to-ambient resistance by about 14% vs open vias.
   - For small pads (4 vias or fewer), 0.2 mm vias instead of 0.33 mm add 15-25% to θJA. For 9 or more vias the
     difference is under 10%.
   [8][S/M], [2][S]
8. **Assembly limits on vias.**
   - Use a drill of 0.33 mm or less, or plugged/capped vias, to stop solder wicking.
   - Tent from the component side. Back-side tenting increases voiding.
   - No thermal-relief spokes on thermal vias.
   - Keep at least 50% solder coverage. Above 50%, θJA changes by less than 5%; at 10% coverage it is +19%.
   [4][V], [5][V], [2][S]
9. **Stitching vias away from the pad matter only when no inner plane exists.** On a 4-layer JEDEC-like board,
   adding 0 → 24 "dog-bone" vias changed θJA by 0.5%. A larger dog-bone area with more vias gave −5%. The effect
   grows with fewer layers. [2][S/M] Outer rings of vias around an array stop helping after 2-4 rings. [8][S]
   Bare 1.6 mm FR4 already couples two 1 oz faces over about 8 mm wherever flux is low. Stitching far from the
   source is therefore an electrical choice, not a thermal one. [calc S]
10. **Cuts in the pour matter by direction.** A slot cut across the radial heat flow added +5.5 °C; the same slot
    along the flow added +1.5 °C. [1][M] Changing outer layers to 50% hatch (with inner planes present) added only +3%. [2][M]
11. **Radiation is not negligible.** Turning radiation off in a validated model raised Tj from 68.7 to 84.6 °C
    (θJA 23.8 → 32.4 °C/W, about 26% of the heat). Board emissivity 0.5 → 0.9 cut θJA by 13%. Solder mask
    lowered θJA by about 5% vs bare copper. Keep the mask on pours. [2][S/M]
12. **Mutual heating:** 0.5 W parts on a 1-layer board start heating each other when closer than about 20 mm. [6][S]
    In a linear model, the board temperature field is the superposition of per-source fields, which is the basis
    for fast placement cost terms. [21][S], [22][S]
13. **Altitude and vacuum.** Natural-convection temperature rise grows ×1.10 at 1.5 km, ×1.21 at 3 km and ×1.48 at
    6 km; fan-cooled rise grows faster (×1.45 at 3 km). [14][V] Traces run 35-55% hotter in vacuum. [10][M]
    Near-vacuum boards cool only by radiation and by conduction to the mount.
14. **Trace heating:** IPC-2152 allows about 1.5-2× the current of IPC-2221 for the same rise. A plane close under
    the trace is the biggest modifier: an example multiplier of 0.47 on the required cross-section for a 1 oz plane
    0.5 mm away. The old IPC-2221 "internal" chart is really the free-air worst case. [10][M], [18][V]

---

## Decision rules for an automated placer/router

| # | Condition | Action | Expected effect | Source / confidence |
|---|---|---|---|---|
| 1 | Any part with P ≥ ~0.1 W, or a datasheet θJA·P > 20 K | Model it as a heat source; estimate Tj = T_board + ΨJB·P (or θJC,bot path) | Correct Tj; avoids θJA misuse | [3][V] |
| 2 | Part has an exposed pad or tab | Solid (no-relief) pad-to-pour connection; via array under the pad, 0.25-0.33 mm drill, 1.0-1.2 mm pitch, hexagonal if it fits, vias as many as fit up to ~9-16; tent/cap on the component side or plug | θJA −26…−35% vs no vias; past 9 vias < 10% further | [2][4][5][8][15] V/S |
| 3 | Pad fits ≤ 4 vias | Prefer 0.3-0.33 mm drill over 0.2 mm; add a ring of vias just outside the pad (≤ 2-4 rings) | −15…−25% θJA vs 0.2 mm | [2][S], [8][S] |
| 4 | No heat sink, P·R_target needs θ(board→air) < ~40 K/W | Pour the source's thermal net (usually GND) on both outer faces under and around the part; stitch faces with the array under the pad plus a ring within a few mm; elsewhere 5-10 mm stitching suffices (FR4 alone couples the faces over ~8 mm at low flux) | ≈2× lower floor than one face (e.g. 92 → 63 °C for LFPAK at 0.5 W) | [7][S], calc [S] |
| 5 | Sizing the pour | Compute the annular-fin R for the actual stack. Extend copper to radius ≈ L·1.5 (2L×1 oz: ~50 mm; 4L×1 oz: ~70 mm), then stop growing area | Within ~10% of the infinite-pour floor | calc [S], [6][S] |
| 6 | Required R below the floor for the stack (2L×1 oz ≈ 15 K/W, 4L×1 oz ≈ 8.5 K/W, 6 mm source) | Escalate in this order: add inner GND planes → 2 oz copper → larger package/pad → board-bottom sink or chassis gap pad under the via array → airflow → top sink | 4L vs 2L −42%; 2 oz −25%; gap pad ≈ 1-2 K/W | [1][2][M], calc [S] |
| 7 | Other-net traces must cross the hot pour | Route them radially (parallel to heat flow), short, on one layer only; never as a ring; keep the opposite face's pour intact under them | +1.5 °C vs +5.5 °C for a perpendicular cut | [1][M] |
| 8 | Two hot parts each relying on their own copper | Separate them by ≥ L (~20-50 mm), or share one plane sized for P1+P2 | Avoids mutual rise (< 20 mm interacts at 0.5 W) | [6][S], calc [S] |
| 9 | Heat-sensitive part (electrolytic, reference, crystal, sensor, battery) | Cost term on its predicted local board temperature; target ≥ 2L from hot parts, upstream/below on vertical boards, not on the hot net's pour | Electrolytic life ×2 per −10 °C | [28][V], [29][V] |
| 10 | Hot part near a board edge or corner, edge not cooled | Penalise the edge (≈2× R at an edge, ≈4× in a corner for large pours); prefer the centre or run copper to a cooled edge | Lower R | calc [S], [1][V] |
| 11 | Pours | Keep solder mask on them; avoid bare-copper "radiator" windows | −5…−13% θJA | [2][S/M] |
| 12 | Board vertical / horizontal known | Use orientation-specific h; for a face-down hot face use about half the upward h; hot parts high on vertical boards | Avoids up to ~2× h error on one face | [13][S], [26][M] |
| 13 | Altitude/vacuum product (e.g. balloon payloads) | Scale convection h by (ρ/ρ0)^½; at high altitude rely on radiation (ε ≈ 0.9 mask) plus conduction to the frame; IPC-2152 vacuum charts for traces | Natural rise ×1.21 at 3 km; vacuum traces +35-55% | [14][V], [10][M], calc [S] |
| 14 | Current-carrying trace/pour | Size with IPC-2152 incl. plane modifier; add its I²R to the thermal model; widen or add a plane under it before using thicker copper | 1.5-2× current vs IPC-2221 | [10][M], [18][V] |
| 15 | Through-hole or hand-soldered pads on big pours | Thermal relief (4 spokes) except heat-carrying pins; above ~3 A use solid | Solderability; ≈18 K/W per relief pad | [24][H], calc [S] |
| 16 | Heat sink present | Keepout = sink outline + clip/screws + fin height zone downstream; pick the bottom-side sink for exposed-pad parts | θJT 50-200 vs θJC 1-10 °C/W | [1][V], [11][V] |

## Open questions

1. No primary measured dataset was found that varies stitching-via pitch over a two-sided pour, away from the pad,
   on a 2-layer board. The 5-10 mm figure is a calculation. A small FDM study, or a test board, would settle it.
2. Measured effect of conformal coating on board temperature was not found.
3. IPC-7093A's exact void and thermal-via clauses were not accessible; only secondary statements were found.
4. Thermal-relief thermal resistance is a calculation only. Measured spoke data was not found.
5. Accuracy of the 2.5D grid vs CFD for components with large top-surface convection (tall inductors, electrolytics).
   onsemi's and Shen's analytical models report agreement within a few percent for their cases, but these were
   single-source validations. [8][11]
6. Fab-specific plating thickness. IPC-6012 class 2 vs 3 nominal values (≈20 vs 25 µm average) were not verified
   here. Query the fab's capability and default to 18-20 µm.
