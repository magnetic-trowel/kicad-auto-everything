# Physics critic catalog: 40 metrics computable from a routed board

**TL;DR**
- 40 critics, each computable from a routed `.kicad_pcb` (zones refilled), the net-role model and the stackup. Each has a mnemonic ID that markers, budget rows and the LLM all use.
- Every critic returns a continuous physical quantity (nH, mV, mΩ, A/mm², dB, °C, V/mm, GHz) plus the objects that spend it. Pass/fail happens only in the scorecard, against a budget with a source ([physics-critics.md](physics-critics.md)).
- Fidelity tiers: **F0** geometry only (µs–ms per net), **F1** closed-form physics (ms), **F2** 2-D/2.5-D field solve on the board's own copper (s–min), **F3** full-wave or FEM spot check for calibration (min–h).
- Build first: RET-COV, RET-VIA, PLANE-PERF, PWR-TRACE, DECAP-L and HOTLOOP-L. They are cheap, catch the known "DRC-clean but wrong" failures, and four of them are prototyped in [pc_refplane.py](../../../tools/research/physics/pc_refplane.py).
- Calibration, mutation operators and gaming guards for every row are in [physics-critics-validation.md](physics-critics-validation.md).

## Key facts

Conventions. **Inputs** use B = board geometry (tracks, arcs, vias, pads, filled zones), S = stackup (z, h, εr, copper t), R = role model (net roles, currents, edge rates t_r, rails, voltage classes) and Bu = budgets from the IR ([constraint-ir](../architecture/constraint-ir.md), [I1 ledger](../../ideas/original/intent-and-why.md)). "Edge-critical" nets are those whose role carries a t_r or data rate. h = dielectric distance to the reference. Numbers marked [C] come from [pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py).

### A. Return path and reference structure

| ID | Measures (unit) | Algorithm (inputs) | Tier, cost | Pass criterion source |
|---|---|---|---|---|
| RET-COV | Share of each edge-critical net's length over its nearest reference copper (%); void crossings (count, mm) | Reference = nearest copper layer by z. Erode that layer's GND/power fills by w/2 + k·h. Intersect the track centreline. Gaps not explained by the net's own antipads are VOIDs. Measure each VOID's extent along the perpendicular (B, S, R) | F0; ms per net (shapely) | Zero VOIDs on nets with t_r budgets. k = 1 keeps 50% of return current over copper, k = 3 keeps 80% [C] |
| RET-HOP | Length where the near reference is missing but a far one exists (mm, ΔnH) | VOID pieces covered by the farther adjacent layer; ΔL from L′(w, h_far) − L′(w, h_near) | F0–F1 | Loop-L budget of the net (RET-RPQF) |
| RET-EDGE | Length within w/2 + 3h of a reference edge or the board edge (mm) | Edge parts of the coverage gaps; board-edge distance from Edge.Cuts | F0 | Edge rule as a budget: edge proximity raises L_ret 3.5× at 1 mm vs centred [C] ([emc-placement](../rules/emc-placement.md)) |
| RET-VIA | Per layer change: return-via distance (mm), or bridging-cap excess L (nH) when the reference net changes | Layers used at each via (track ends). Reference set per layer. Same net: nearest via spanning both planes. Different nets: nearest capacitor between the two nets, L ≈ (µ0·t/π)·ln(D/r) + 1 nH [I] | F1; ms | TI ≤200 mil (5 mm), Gen5 ≤50 mil, Altium default 1.5 mm ([si-fundamentals](../rules/si-fundamentals.md)); better: noise budget ÷ (dI/dt) |
| RET-REFNET | Length of edge-critical nets referenced to a power net (mm) | Reference net under each segment midpoint | F0 | TI "does not recommend" power references for HS nets; allowed with stitching caps |
| RET-RPQF | Return-path quality factor lite: L_est / L_ideal per net | Σ L′(w, h)·length (Hammerstad) plus HOP, EDGE, VOID (shorted-slot-line) and via terms; ideal = all over the near plane | F1; ms | Ratio ≤ 1.1 on budgeted nets [I]. Precedent: Cadence RPQF, "ideal 1.0" from a hybrid solve [V] |
| PLANE-PERF | Per plane layer: foreign track length (mm), slots > 2 mm (count, longest mm, half-wave GHz), islands | Plane layer = one GND/power net fills ≥ 30% of the board. Slots = interior rings of the fill, minimum rotated rectangle | F0; ms | Zero foreign tracks on declared planes; slot half-wave > 3 × f_knee |
| SPLIT-X | Crossings of a boundary between two plane nets on the reference layer, with the distance to the nearest stitching cap (mm, nH) | Like RET-COV, but on boundaries between different-net fills | F0–F1 | Ott: 1–10 nF within 0.1" each side; never cross if both planes split |
| CAVITY | Largest empty circle between GND stitching vias over two GND fills (mm); first mode (GHz) | Grid sample of the overlap; KD-tree distance to vias; f ≈ c/(2√εr·d) | F0; ms | Mode > f_knee and away from clock harmonics; λ/20 is the slogan version |
| GND-ISLAND | Copper islands: area, distance to the nearest stitching via, quarter-wave GHz | Connected components of fills per net; via and pad contacts | F0 | No unstitched island with a quarter-wave inside the spectrum |

### B. Signal integrity

| ID | Measures (unit) | Algorithm (inputs) | Tier, cost | Pass criterion source |
|---|---|---|---|---|
| XTALK | Per victim: summed near/far-end noise (mV) | Spatial hash of segments; pairs ≤5° from parallel, same or adjacent layer; K = 1/(1+(D/H)²) × min(1, 2T/t_r) per aggressor; sum the worst 2 + 2 ([checkers-si-emi](../rules/checkers-si-emi.md) E) | F1; ms | Victim noise budget (mV). K = 0.1 at D = 3H, 0.5 at D = H [C] |
| VIA-STUB | Stub length (mm), resonance (GHz) | Drill span minus used span minus backdrill; f = c/(4ℓ√εr) | F1 | f_res > 3 × Nyquist. A 1.4 mm stub resonates at 26 GHz: irrelevant below PCIe Gen5 [C] |
| IMP-DISC | Worst reflection Γ along a net and its electrical length vs t_r | Z0 per piece from width, h, εr and reference state (Hammerstad or a 2-D solve); neck-downs, reference changes, stubs | F1–F2 | Γ budget per interface; ignore pieces shorter than t_r·v/6 |
| DIFF-BAL | Pair skew (ps) and asymmetric features (vias, bends, references); V_cm from mode conversion | Per-leg delay; feature-by-feature diff; V_cm ≈ ΔT/t_r × V_swing [I] | F1 | Interface skew (ps); V_cm per the CM-V budget |
| TOPO | Branch stubs (ps) and series-termination distance from the driver (ps) | Net tree from tracks and pads; branch delay vs t_r/6 | F0–F1 | t_r/6 rule restated in ps |

### C. Power, PDN and commutation

| ID | Measures (unit) | Algorithm (inputs) | Tier, cost | Pass criterion source |
|---|---|---|---|---|
| HOTLOOP-L | Commutation-loop inductance (nH); overshoot L·di/dt (V) | Loop members from the role model ([hot-loops](../rules/power/hot-loops.md)). Extract the realized copper path (pads, pours, vias) as a polygon chain; F1 current sheet over a plane, L ≈ µ0·h·ℓ/(w + 2h); F2 PEEC/FastHenry on that copper | F1 ms; F2 s | Overshoot ≤ 0.2 × V_DS,max ([checkers-power](../rules/checkers-power.md)); 12 × 3 mm path: 0.9 nH with the plane at 0.2 mm, 3.0 nH at 1.0 mm [C] |
| DECAP-L | Per power pin: mounting + spreading L to its decaps (nH); \|Z\| in the band (mΩ) | Graph from pin to via, plane pair, cap vias and cap; trace L′, via L, plane spreading (µ0·t/π)·ln(D/r) | F1 | From Z_t. Moving a 0402's GND via 5 mm away adds 1.3–1.9 nH and lifts \|Z(100 MHz)\| from 0.61 to 1.43 Ω [C] |
| PDN-Z | Rail impedance vs frequency; peaks / Z_t | Lumped RLC from DECAP-L, derated C, plane C, cavity modes; F2: plane-pair solver | F1–F2; s | Peak ≤ 1.57 × Z_t (robust), ≤ 3 × (tolerated) ([decoupling-pdn](../rules/decoupling-pdn.md)) |
| IR-DROP | DC drop per load (mV) | 2-D Laplace on each rail's copper per layer, vias as resistors, sources and sinks from R; scipy sparse | F2; s | Rail tolerance share (mV) |
| J-MAX | Peak current density (A/mm²) and its location; neck width | Same solve; gradient of potential; minimum cut on the copper graph as an F0 screen | F2 | Ampacity / ΔT budget. A 1 mm neck in 1 oz at 5 A is 143 A/mm², 12 mV, 61 mW [C] |
| VIA-AMP | Current per via in an array (A) and sharing ratio | Via currents from the IR-DROP solution | F2 | Via ampacity and thermal budget |
| PWR-TRACE | GND/power nets connected by thin traces instead of pours: pads off-pour, thin-track length (mm), summed R (mΩ) | Pad shapes vs same-net fills; tracks narrower than w_thin | F0 | Each power pin's R and L to its plane within budget. OmniRouting failure mode |
| SW-AREA | Switch-node copper area (mm²), capacitance (pF) and displacement current C·dV/dt (mA) | Fill + track area of the SW net per layer; C from area/h to each plane | F1 | EMI budget; minimum = pads + FET-to-inductor path ([buck](../rules/power/buck.md)) |
| SENSE-M | Mutual inductance from hot loops and SW to FB, sense and Kelvin loops (nH); induced mV | Neumann double integral over polyline loops (with plane images) | F1; ms | Sense noise budget (mV); FB keep-out restated |
| KELVIN | Shared resistance between the sense tap and the main current path (mΩ) and the error (mV) | Path search on the copper graph; IR-DROP potentials at the tap pads | F2 | Shunt error budget ([current-sense-kelvin](../rules/power/current-sense-kelvin.md)) |

### D. EMI

| ID | Measures (unit) | Algorithm (inputs) | Tier, cost | Pass criterion source |
|---|---|---|---|---|
| CM-V | Common-mode voltage between cable connectors (µV) per fast net | MREMC: L_ret from trace position and board width; V_cm = h·V_dm or 2πf·L_ret·I_dm; E_max ([emc-placement](../rules/emc-placement.md)) | F1; ms | 1 mV fails Class B; 100 µV for strict limits |
| IO-COUPLE | Coupling from fast nets into unfiltered I/O nets near connectors (mV) | XTALK restricted to I/O victims between the connector and its filter | F1 | I/O budget (mV), stricter than internal |
| FILTER-POS | Position of ESD/filter/CMC along the path; shunt loop L to the return (nH) | Path order on the net graph; loop L of the shunt branch | F0–F1 | Protection topology ([checkers-si-emi](../rules/checkers-si-emi.md) I) |
| LOOP-RAD | Differential-mode field at 3 m per loop (dBµV/m) | Ott: E = 2.632×10⁻¹⁴·f²·A·I/r at harmonics up to f_knee; A from RET-RPQF geometry | F1 | Ranking only: cables dominate |
| ANT-KEEP | Copper inside antenna keep-outs, any layer (mm²) | Polygon intersection | F0 | Module datasheet |
| SPECTRUM | Coincidence of clock and switching harmonics with structure resonances (cavity, slot, island, stub) (dB) | Line spectra from R; resonance list from CAVITY, PLANE-PERF, GND-ISLAND, VIA-STUB; overlap score | F1 | No strong harmonic within a resonance's bandwidth |

### E. Thermal, high voltage, manufacturing physics

| ID | Measures (unit) | Algorithm (inputs) | Tier, cost | Pass criterion source |
|---|---|---|---|---|
| THERM-DT | ΔT per dissipating part (°C) | 2.5-D resistive network from the actual copper: pads, pours, vias (261 °C/W per 12 mil via), convection ([thermal](../rules/thermal.md)) | F1–F2; s | Part T_J limit; Quilter-style overheated length |
| THERM-COUPLE | ΔT at sensitive parts (crystal, reference, sensor, electrolytic) from neighbours (°C) | Superposition on the same network | F1 | Drift budget of the victim |
| THERM-VIA | Thermal-via count, pitch and plating under exposed pads → θ (°C/W) | Via array under the EP polygon | F0 | Datasheet θ assumptions |
| HV-FIELD | Peak field between conductors at different potentials (V/mm), incl. inner layers and corners | Edge-to-edge distance per voltage pair; corner enhancement for acute copper | F1; F2 for corners | Material strength with margin; standard clearance |
| CREEPAGE | Surface geodesic creepage and 3-D clearance (mm) | Geodesic around slots ≥ the pollution-degree minimum ([isolation-creepage](../rules/isolation-creepage.md)) | F1 | IEC 60664-1 / 62368-1 tables |
| COPPER-BAL | Copper density per layer and between mirrored layers (%) | Fill + track area per layer | F0 | Fab warp guidance |
| TOMBSTONE | Thermal-mass asymmetry between the two pads of small passives (ratio) | Copper connected within r of each pad | F0 | Assembler guidance; kicad-happy uses 0.3 (unsourced) |
| VIA-AR | Aspect ratio and current/heat duty of vias (ratio, A) | Drill vs thickness; current from VIA-AMP | F0 | Fab class |

### F. Integrity of the critic run

| ID | Measures | Algorithm | Tier |
|---|---|---|---|
| FILL-STALE | Whether fills match a fresh refill (area delta %) | Compare saved fills with a `kicad-cli --refill-zones --save-board` copy | F0 |
| ROLE-COVER | Share of nets with roles, budgets and t_r; which critics ran per net | Join critic logs with the role model | F0 |

## Recommendations for our system

- Compute A, PWR-TRACE and DECAP-L on every candidate (F0/F1). Run IR-DROP, J-MAX, PDN-Z and THERM-DT at stage gates (F2). Keep F3 for calibration and finalists ([evaluation-stack](../verification/evaluation-stack.md)).
- Report continuous values. Thresholds belong to the scorecard and come from budgets, so a router cannot sit at 1.99 mm of a 2 mm rule.
- Keep ID names stable: they are the vocabulary the LLM repair loop reads.

## Conflicts and open questions

- Several F1 formulas are uncalibrated in this setting: the slot-line VOID term, the bridging-cap estimate (1.2–3 nH [C] vs Ott's 5–10 nH), and the hot-loop sheet model. See [physics-critics-validation.md](physics-critics-validation.md).
- Edge-critical role assignment is the weak input. Regex roles in the prototype flag USB, CAN, SWD and PCIe names only.

## Sources

- research notes: [rules_highspeed_emi.md § 11, 12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [rules_power_rf_analog_dfm.md § 17–20](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
- Altium Return Path rule (reference layer, minimum gap, max stitch-via distance 1.5 mm default): https://altium.com/documentation/altium-designer/pcb-high-speed-rule-return-path [P]
- Cadence return-path quality factor = loop L / ideal loop L, ideal 1.0: https://www.ema-eda.com/ema-resources/blog/investigating-return-path-discontinuities-understanding-impacts-and-effective-mitigation-strategies/ [V]
- Ott slot measurements: https://hott.shielddigitaldesign.com/techtips/tips-slots.html [P]

See also: [physics-critics.md](physics-critics.md), [physics-critics-validation.md](physics-critics-validation.md), [../rules/checkers-si-emi.md](../rules/checkers-si-emi.md), [../rules/checkers-power.md](../rules/checkers-power.md)
