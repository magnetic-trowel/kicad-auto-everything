# Power copper: node and branch physics, trace vs pour vs plane, current density, corners, AC effects

*Tags: [P] primary, [S] secondary, [V] vendor claim, [I] inference, [C] computed by us.*
*Scripts: [pw_cells.py](../../../tools/research/physics/pw_cells.py) (closed forms), [pw_sheet.py](../../../tools/research/physics/pw_sheet.py) (2-D Laplace on copper masks, electro-thermal), [pw_xsec.py](../../../tools/research/physics/pw_xsec.py) (2-D skin and proximity solver). Each runs in seconds to about a minute, numpy/scipy only. Loops, vias, decoupling and Kelvin sensing are in [pdn-and-commutation](pdn-and-commutation.md).*

**TL;DR**
- **Classify copper by waveform, not by net name.** Each node gets a dv/dt and a swing. Each branch gets a di/dt, an I_rms and an I_dc. Those set the objective for each piece of copper:
  - a high-dv/dt node minimises capacitance to the world and to victims;
  - a high-di/dt branch minimises loop inductance;
  - a heavy-current branch minimises R and ΔT;
  - a quiet sensitive node minimises M and C to aggressors.
  Only the switch node is both fast-dv/dt and inside the hot loop. The SW copper inside that loop should have near-zero length.
- **Every piece of copper over a plane trades L, C and R through its width.** Minimise a·L + b·C + g·R with L ∝ h·l/w, C ∝ w·l/h and R ∝ l/w. Two length invariants hold: L·C = l²/v² and R·Area = R_s·l². Width trades one parasitic for another; only length lowers all of them.
  - In a low-voltage buck, loss alone would make SW copper about 60 mm wide [C]. What really limits SW area is coupling to the world and victims: an EMI budget.
  - In a 400 V converter, capacitive switching loss itself limits SW copper to about 1–3 mm wide [C].
- **Pour vs trace.** A two-terminal connection gains little once the copper is wider than its feeds. In a large pour, 31% of the loss sits within 3 mm of the pads [C]. So widen the entries (pads, via rows, parallel parts) before the body. Via fields multiply sheet resistance by 1.8× at antipad/pitch 0.6, 3.1× at 0.8 and 5.2× at 0.9 [C].
- **Corners do not matter for steady current.** A sharp corner's steady peak temperature equals the straight trace's within 0.5% [C]. They matter for pulses shorter than about 1 ms: a sharp inside corner sees 2–8× the local J² [C]. Round inside corners only on surge, fault, fuse and ESD paths.
- **AC effects are small in power copper below about 1 MHz** (R_ac/R_dc ≤ 1.6) [C]. The big AC effect is where the return flows. A stacked go/return pair has 0.07 nH/mm vs 0.55–0.66 nH/mm side by side. Even a floating plane 0.1 mm below cuts side-by-side L by 5× through eddy currents [C].

## Key facts

### 1. Node and branch classification (the decision procedure)

Inputs: a SPICE run of the schematic, or the [hot-loops](../rules/power/hot-loops.md) topology template with datasheet values. Worked case [C, `pw_cells.py classify`]: an idealised sync buck, 12 V → 1.2 V, 10 A, 500 kHz, 1 µH, 2 ns edges.

| Copper piece | dv/dt (node) | di/dt (branch) | I_rms / I_dc | Objective | What the rule of thumb says |
|---|---|---|---|---|---|
| CIN_HF ↔ HS ↔ LS (hot loop) | VIN, PGND quiet; SW 6 V/ns | 5.5 A/ns | 3.0 A / 0 | min L: short, wide, return directly beneath | "smallest loop area" |
| LS FET → PGND | quiet | 5.5 A/ns | 9.5 / 9.0 A | min L, then R and ΔT | "wide" |
| SW → inductor | 6 V/ns | 0.011 A/ns (set by L) | 10 / 10 A | min R vs min C to world and victims | "keep SW small" |
| L → COUT → load | quiet | 0.011 A/ns | 10 / 10 A | min R, ΔT; pour freely | "wide trace" |
| BOOT, gate | 6 V/ns, 0.2 A/ns | — | small | min L of the gate loop; min C to victims | "short" |
| FB, COMP, sense | victims | — | µA | min M·di/dt and C·dv/dt pickup; Kelvin tap | "away from SW" |

Decision procedure for each copper piece k [I]:
1. Simulate the node's dv/dt spectrum and the branch's di/dt, I_rms and I_dc.
2. Set the weights:
   - a_k (W per H) = ½·I_sw²·f for pieces in a commutation loop;
   - b_k (W per F) = ½·V²·f for capacitance to the local return, plus an EMI weight for capacitance to the world and a crosstalk weight for capacitance to victims;
   - g_k (W per Ω) = I_rms²;
   - victim sensitivities in V per H and V per F.
3. Choose the shape (trace, pour, stacked pair, plane) and width from the weights (§2). Check each budget in the [physics ledger](../../ideas/original/intent-and-why.md#i1-physics-budget-ledger--novel-combination).
4. Re-run with the realised geometry, because SW-node C changes the edges and loop L changes the overshoot.

**Central tensions, made explicit:**

| Tension | Physics | Resolution |
|---|---|---|
| SW area: heat spreading and low R vs E-field antenna | C to the local plane is cheap. C to the world drives common-mode current: a 100 mm² SW pad 10 mm from a cabled conductor gives about 4 µA, 35–45 dBµV/m [C, I] (chain in [fields-emi-budget](fields-emi-budget.md)) | Grow SW area only over a solid local plane, away from edges and cables. Take heat through a thin dielectric (below) |
| Hot-loop compactness vs thermal spreading | Heat crosses a dielectric and charge does not. G/C = k/ε does not depend on geometry: 7.9×10⁹ (W/K)/F for FR-4 [C] | The heat-spreading copper can be a different net (the L2 plane), 0.1 mm away |
| Pour size vs coupling | A pour on a quiet node is a shield. A pour on a fast node is an antenna. Rayleigh monotonicity: more copper never raises DC R ([cross-domain-lessons](cross-domain-lessons.md)) | Pour freely on quiet nodes. Size fast-node copper by the width trade |

**Thermal via a dielectric.** A 1 cm² SW pad over 0.1 mm FR-4 to a plane has 3.3 K/W and 38 pF [C].
- At 12 V and 500 kHz, ½CV²f = 1.4 mW: free.
- At 400 V and 100 kHz it is 0.3 W: not free.
- Thermal prepreg (1–3 W/m·K) improves the trade 3–9×, and AlN about 280×.

### 2. The width trade and two invariants

Over a plane at height h (wide-strip limit): L = μ0·h·l/w, C = ε·w·l/h, R = ρ·l/(w·t). Minimising a·L + b·C + g·R gives:

w* = sqrt((a·μ0·h + g·ρ/t) / (b·ε/h)), and with no R term Z0* = sqrt(b/a) = V/I of the switching cell.

| Piece [C, `pw_cells.py width`] | w* | Comment |
|---|---|---|
| LV buck SW → L (12 V, 10 A, 500 kHz, h 0.1 mm) | 60 mm | Loss never limits width. EMI does |
| SW copper inside that hot loop | 36 mm | Irrelevant: make it short |
| 48 V GaN SW (20 A, 1 MHz) | 17 mm | |
| 400 V PFC drain (2 A rms, 100 kHz), h 0.1 / 1.5 mm | 0.8 / 3.1 mm | HV nodes: capacitance costs real loss |

- **Invariants.** L·C = (l/v)² and R·A = R_s·l² for a strip: w/h only moves parasitics between L, C and R.
- **Rule origin.** "Make power traces wide" is physics for quiet high-current pieces. "Keep SW small" is EMI physics, and loss physics only at high V. Rohm's ">1 mm/A" ([buck](../rules/power/buck.md)) is a thermal proxy (§6).

### 3. Trace vs pour vs plane

One 2-D Laplace solve on the copper mask gives the number of squares N□ between ports. Then:
- R = R_s·N□ (R_s = 0.49 mΩ/□ for 1 oz);
- for a plane pair, or a pour with its return copy at depth d, L = μ0·d·N□ below the cavity resonance;
- C = ε·A/d is computed separately.

The same operator underlies [copper-shape-synthesis](copper-shape-synthesis.md).

Experiment [C, `pw_sheet.py pour`]: a 2×2 mm source pad and a 2×2 mm load pad, centres 30 mm apart, 1 oz:

| Copper | Area mm² | N□ | R mΩ | R·Area |
|---|---|---|---|---|
| Trace 0.5 mm | 25 | 46.8 | 23.0 | 1161 |
| Trace 1 mm | 36 | 28.1 | 13.8 | 1012 |
| Trace 2 mm (= pad width) | 64 | 14.1 | 6.9 | 899 |
| Trace 4 mm | 128 | 7.1 | 3.5 | 911 |
| Pour 8 mm | 272 | 3.7 | 1.8 | 1016 |
| Pour 16 mm | 608 | 2.1 | 1.0 | 1295 |
| Full 44×30 mm region | 1320 | 1.47 | 0.72 | 1942 |

- **Area efficiency peaks at feed width;** wider pours pay a logarithmic spreading toll at the pads.
- **In the full region:**
  - 50% of the loss sits in 19% of the area;
  - 31% sits within 3 mm of the two pads, 43% within 5 mm.
- **Greedy trimming of low-|J| copper:**
  - −28% area costs +9% R; −48% costs +27%; −62% costs +53%.
  - At equal area, trimmed shapes do no better than a plain strip (263 mm² trimmed: 3.69 □ vs a 272 mm² strip: 3.74 □).

  Optimised shapes gain about 15% at equal area ([copper-shape-synthesis](copper-shape-synthesis.md)).
- **Spreading at a via:** ΔR = (R_s/2π)·ln(r₂/r₁) = 0.27 mΩ from a 0.15 mm via out to 5 mm at 1 oz, a quarter of the barrel's ~1.1 mΩ ([SLAA896](https://www.ti.com/lit/pdf/slaa896)) [C].
- **Via fields perforate planes** [C, `pw_sheet.py viafield`, square array, unit-cell solve]:

  | Antipad D / pitch p | 0.3 | 0.5 | 0.6 | 0.7 | 0.8 | 0.85 | 0.9 | 0.95 |
  |---|---|---|---|---|---|---|---|---|
  | Sheet-R multiplier | 1.16 | 1.50 | 1.80 | 2.28 | 3.14 | 3.89 | 5.18 | 8.23 |

  Rayleigh's (1+f)/(1−f) (f = hole fraction) holds within 4% up to D/p = 0.8, then under-predicts. Example: a 0.8 mm-pitch field with 0.7 mm antipads is a 4× neck.
- **Copper that carries no current** can be a heat spreader, a shield if tied at many points, or fab balance (keep all three). On a fast node, a floating or single-tied stub is capacitance or an antenna, so remove or stitch it. A deliberately isolated noisy local PGND is also kept ([Hedrich, MPS](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf) [P]).

**A narrow trace is right** for fast nodes with little current (BOOT, snubber legs), victim nets, low-current rails, and deliberate impedance (net ties, fuse necks, thermal isolation for sensors).

**Convert a trace to a pour when** any of these holds [I]:
- the width needed by the IR-drop, ΔT or L budget exceeds the channel width;
- the piece is a quiet node inside a commutation loop;
- it needs to spread heat.

### 4. Corners and curves

Unit-width L-bends, arms of 8 widths [C, `pw_sheet.py corner`]. Our 0.55 □ for the sharp corner agrees with [rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md) (0.56).

| Bend | Corner counts as | Peak J / J₀ at the inside corner |
|---|---|---|
| Sharp 90° | 0.55 □ | 2.6 → 3.3 → 4.1 at 20/40/80 cells per width. Singular, ∝ r^(−1/3) |
| Outer miter only | 0.57 □ | Same singularity as sharp |
| Two 135° corners (45° segment) | 0.39 □ | 1.9–2.5, weak r^(−0.2) singularity |
| Inner fillet r = 0.5w / 1.0w | 0.35 / 0.04 □ | 1.8 / 1.45 (adds copper) |
| Constant-width arc, inner r = 0.5w / 2w | saves 0.09 □ vs sharp | 1.82 / 1.23 (annulus: (w/r)/ln(1+w/r)) |

- **Steady state.** A 1 mm, 1 oz trace at 5 A [C, `pw_sheet.py thermal`]:
  - over a bare 1.6 mm board: a sharp corner's peak rise is 49.2 K against 49.3 K for a straight trace of the same length;
  - over an isothermal plane 0.1 mm down: 3.39 K vs 3.44 K.

  Copper conducts heat sideways over millimetres, so crowding never shows; the corner even shortens the path.
- **Pulses.** Heat diffuses only √(α·t) in copper (α = 1.1×10⁻⁴ m²/s). J² averaged over that radius at a sharp inside corner:

  | Pulse | 10 µs | 100 µs | 1 ms | 10 ms |
  |---|---|---|---|---|
  | J² vs the trace's | 7.7× | 3.7× | 1.75× | <1× |

  So curves matter for surge, ESD, inrush, short-circuit and intended fuse traces, not for steady DC [C]. The kV ESD-corner case is field enhancement, not current ([hv-and-manufacturing-physics](hv-and-manufacturing-physics.md)).
- **Electromigration is irrelevant:** 10 A in 1 mm of 1 oz is 3×10⁸ A/m², 1–2 orders below interconnect limits [I].

### 5. AC effects

Skin depth in copper is 66 µm at 1 MHz, 21 µm at 10 MHz and 6.6 µm at 100 MHz. Cross-section solves (2 mm wide 1 oz traces, near-pair mutuals by sub-square averaging, converged to <5%) [C, `pw_xsec.py`]:

| Configuration | L' at 1 kHz → 1 MHz → 10 MHz (nH/mm) | R_ac/R_dc at 100 kHz / 1 MHz / 10 MHz / 100 MHz |
|---|---|---|
| Trace over plane, h = 0.1 mm | 0.39 → 0.068 → 0.063 | 1.31 / 1.59 / 2.27 / ~7 |
| Trace over plane, h = 1.5 mm | 0.47 → 0.38 → 0.37 | 1.08 / 1.27 / 1.67 / ~4 |
| Go/return side by side, 0.5 mm gap | 0.66 → 0.58 → 0.55 | 1.03 / 1.52 / 2.21 / ~5 |
| Same, floating plane 0.1 mm below | 0.66 → 0.13 → 0.12 | 1.29 / 1.71 / 2.40 / ~8 |
| Stacked go/return, 0.1 mm | 0.070 (flat) | 1.00 / 1.01 / 1.42 / 4.5 |

- **The return current changes path with frequency.** Under a trace with a plane at 0.1 mm:
  - at 1 kHz the return spreads across the plane by resistance (0.39 nH/mm);
  - by 1 MHz it gathers under the trace (0.068 nH/mm).

  The crossover f_c = R_s/(2π·μ0·h) is the same one [copper-shape-synthesis](copper-shape-synthesis.md) derives. Design DC paths for R, fast paths for L.
- **Proximity effect is why overlap lowers L.** Current moves to the facing surfaces (99% in the facing halves at 100 MHz), confining the field to the gap.
- **R_ac matters little below ~1 MHz** (≤1.6× DC), except in planar-magnetics windings (Dowell).
- **Copper barely damps hot-loop ringing.** A commutation loop (0.3–3 nH) with C_oss 1 nF rings at 90–290 MHz with Z0 0.55–1.7 Ω. The copper's 10–18 mΩ gives Q 31–173 [C, `pw_cells.py ring`], using R from a fixed 2-square loop while L is a free input. For wide copper the Q is h/δ ([lens-th](lens-th.md)). Plane pairs below ~30 MHz are different: there copper alone gives Q 1–10 on 0.1 mm cores [C, [rt_sheet_return](../../../tools/research/physics/rt_sheet_return.py)]. Damping comes from snubbers and ESR.
- **A conducting sheet starts to mirror a loop of size a** above f_c = 1/(π·μ0·σ·t·a): 124 kHz at a = 1 mm, 41 kHz at 3 mm and 12 kHz at 10 mm, for 35 µm copper [C]; that is the onset, and half-mirroring needs 2–5× higher f ([lens-sy](lens-sy.md)). So "skin depth (66 µm at 1 MHz) exceeds the copper thickness, so the plane does not shield" is wrong. A thin plane mirrors mm-scale loops at the switching frequency.

### 6. Coupling to the thermal model (owner: [thermal-physics](thermal-physics.md))

- IPC-2152 is a thermal model of one test board. The physics replacement is a network: trace I²R → dielectric → plane → board → ambient.
- A 1 mm trace 0.1 mm above a plane couples 3 W/(m·K) of conductance into it, while its top surface convects only 0.02 W/(m·K): a trace near a plane is cooled by the plane and board, which is why IPC-2152 lets inner traces near planes carry more than IPC-2221 implied ([high-current](../rules/power/high-current.md)) [C].
- A copper plane spreads heat over a healing length √(k·t/h_total): 26–37 mm for 1 oz and 37–52 mm for 2 oz, at 10–20 W/m²·K [C].
- Resistivity rises 0.39%/K: iterate electro-thermally above ~20 K rise [I].

## Recommendations for our system

- **Role extraction emits waveforms, not just labels.** The LLM proposes topology and operating points; code runs a SPICE operating sweep or topology template and writes per-node dv/dt and per-branch di/dt, I_rms and I_dc into the physics IR ([physics-ir](physics-ir.md)).
- **Generate per-piece objectives (a, b, g, victim weights) from those numbers.** Compile them to router costs, width constraints and keep-outs, replacing the PWR_HOT/SW/SENSITIVE net-class heuristics in [checkers-power](../rules/checkers-power.md).
- **Add the N□ solver as a T1 critic,** with grid plus Peaceman sub-cell vias ([pdn-and-commutation](pdn-and-commutation.md)). It reports R, IR drop, entry-constriction share, via-field necks and, where a return copy exists, μ0·d·N□.
- **Treat corner style as a pulse-path property only** (net classes `SURGE`, `FUSE`, `ESD_UNPROTECTED`).
- **Make SW-node area an EMI-budget item,** and a loss item at ≥100 V. Drop the fixed "≤ k × pad area" rule (PWR-03).

## Conflicts and open questions

- **SW area.** "Never heatsink through SW copper" (Rohm, TH-08 in [thermal](../rules/thermal.md)) is too strong for low-voltage converters over a solid plane, right at high voltage and near cables; a computed trade replaces it [I].
- **The EMI numbers in §1 are an upper-bound coupling model** (all displacement current onto a 1 m cable). Calibrate them against the [fields-emi-budget](fields-emi-budget.md) chain and measurements.
- **2-D sheet models ignore copper thickness at corners and etch rounding.** The pulse hot-spot factors are 2-D, grid-limited at 10 µs, and need a 3-D transient check before becoming limits.
- **Not verified:** IPC-2152 charts (paywalled), and the claim that electromigration limits are irrelevant at PCB scale (no primary source read).

## Sources

- research notes: [rules_power_rf_analog_dfm.md § 1, § 2, § 14](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- J. Hedrich, "PCB Design for Low-EMI DC/DC Converters", MPS Article #0030 ([PDF](https://media.monolithicpower.com/mps_cms_document/2/0/2019-aip-pcb-design-for-low-emi-dc-dc-converters_r1.0.pdf)) [P]
- TI SLAA896 (via R, L, I) [P via [high-current](../rules/power/high-current.md)]; TI SNVA419 (thermal rules) [P via [thermal](../rules/thermal.md)]
- Lord Rayleigh, "On the influence of obstacles arranged in rectangular order…", Phil. Mag. 34 (1892) [S]; re-entrant-corner singularity r^(π/α−1), standard potential theory [S]
- H. W. Ott, *Electromagnetic Compatibility Engineering*, Wiley 2009 (common-mode radiation) [S]
- All [C] numbers: the three scripts named at the top.

See also: [pdn-and-commutation](pdn-and-commutation.md), [copper-shape-synthesis](copper-shape-synthesis.md), [thermal-physics](thermal-physics.md), [fields-emi-budget](fields-emi-budget.md), [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md), [../rules/power/hot-loops.md](../rules/power/hot-loops.md), [../rules/power/high-current.md](../rules/power/high-current.md), [power ideas](../../ideas/physics-first/power.md)
