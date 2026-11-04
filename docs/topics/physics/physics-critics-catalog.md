# Physics critic catalog: 41 metrics computable from a routed board

Scope: definitions of 39 physics critics + 2 run-integrity checks (ID, measured quantity and unit, algorithm, inputs, tier, pass-criterion source). Not here: suite architecture and scorecard -> [physics-critics](physics-critics.md); calibration, mutation operators, gaming guards per row -> [physics-critics-validation](physics-critics-validation.md); tiers -> [solver-ladder](solver-ladder.md).
Keys: RET-COV, RET-HOP, RET-EDGE, RET-VIA, RET-REFNET, RET-RPQF, PLANE-PERF, SPLIT-X, CAVITY, GND-ISLAND, XTALK, VIA-STUB, IMP-DISC, DIFF-BAL, TOPO, HOTLOOP-L, DECAP-L, PDN-Z, IR-DROP, J-MAX, VIA-AMP, PWR-TRACE, SW-AREA, SENSE-M, KELVIN, CM-V, IO-COUPLE, FILTER-POS, LOOP-RAD, ANT-KEEP, SPECTRUM, THERM-DT, THERM-COUPLE, THERM-VIA, HV-FIELD, CREEPAGE, COPPER-BAL, TOMBSTONE, VIA-AR, FILL-STALE, ROLE-COVER

Rules:
- Each critic is computable from a routed `.kicad_pcb` (zones refilled), the net-role model and the stackup; the mnemonic ID is shared by markers, budget rows and the LLM. Keep IDs stable: they are the repair loop's vocabulary.
- Each returns a continuous physical quantity (nH, mV, mΩ, A/mm², dB, °C, V/mm, GHz) plus the objects that spend it. Pass/fail only in the scorecard against a sourced budget, so a router cannot sit at 1.99 mm of a 2 mm rule.
- Tiers: F0 geometry (µs–ms per net), F1 closed form (ms), F2 2-D/2.5-D field solve on the board's copper (s–min), F3 full-wave/FEM spot check (min–h). Compute A, PWR-TRACE and DECAP-L on every candidate (F0/F1); IR-DROP, J-MAX, PDN-Z, THERM-DT at stage gates (F2); F3 for calibration and finalists ([evaluation-stack](../verification/evaluation-stack.md)).
- Build first: RET-COV, RET-VIA, PLANE-PERF, PWR-TRACE, DECAP-L, HOTLOOP-L (cheap; catch the known DRC-clean failures; four prototyped in [pc_refplane.py](../../../tools/research/physics/pc_refplane.py)).

Inputs column: B = board geometry (tracks, arcs, vias, pads, filled zones); S = stackup (z, h, εr, copper t); R = role model (net roles, currents, edge rates t_r, rails, voltage classes); Bu = budgets from the IR ([constraint-ir](../architecture/constraint-ir.md), [I1 ledger](../../ideas/original/intent-and-why.md)). Edge-critical nets: role carries a t_r or data rate. h = dielectric distance to the reference. [C] from [pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py).

## A. Return path and reference structure

| ID | Measures (unit) | Algorithm | Inputs; tier, cost | Pass criterion source |
|---|---|---|---|---|
| RET-COV | share of each edge-critical net's length over its nearest reference copper (%); void crossings (count, mm) | reference = nearest copper layer by z; erode its GND/power fills by w/2 + k·h; intersect the track centreline; gaps not explained by own antipads are VOIDs; measure each VOID's perpendicular extent | B S R; F0; ms per net (shapely) | zero VOIDs on nets with t_r budgets; k = 1 keeps 50% of return current over copper, k = 3 keeps 80% (PEEC within 0.02) [C] |
| RET-HOP | length where the near reference is missing but a far one exists (mm, ΔnH) | VOID pieces covered by the farther adjacent layer; ΔL = L′(w, h_far) − L′(w, h_near) | B S R; F0–F1 | net's loop-L budget (RET-RPQF) |
| RET-EDGE | length within w/2 + 3h of a reference edge or board edge (mm) | edge parts of coverage gaps; board-edge distance from Edge.Cuts | B S R; F0 | edge rule as budget: edge proximity raises L_ret 3.5× at 1 mm vs centred [C] ([emc-placement](../rules/emc-placement.md)) |
| RET-VIA | per layer change: return-via distance (mm), or bridging-cap excess L (nH) when the reference net changes | layers used at each via (track ends); reference set per layer; same net: nearest via spanning both planes; different nets: nearest cap between the two nets, L ≈ (µ0·t/π)·ln(D/r) + 1 nH [I] | B S R; F1; ms | TI ≤ 200 mil (5 mm), Gen5 ≤ 50 mil, Altium default 1.5 mm ([si-fundamentals](../rules/si-fundamentals.md)); better: noise budget ÷ (dI/dt) |
| RET-REFNET | length of edge-critical nets referenced to a power net (mm) | reference net under each segment midpoint | B S R; F0 | TI "does not recommend" power references for HS nets; allowed with stitching caps |
| RET-RPQF | return-path quality factor lite: L_est / L_ideal per net | Σ L′(w, h)·length (Hammerstad) + HOP, EDGE, VOID (shorted-slot-line) and via terms; ideal = all over the near plane | B S R Bu; F1; ms | ratio ≤ 1.1 on budgeted nets [I]; precedent Cadence RPQF, "ideal 1.0" from a hybrid solve [V] |
| PLANE-PERF | per plane layer: foreign track length (mm), slots > 2 mm (count, longest mm, half-wave GHz), islands | plane layer = one GND/power net fills ≥ 30% of the board; slots = interior rings of the fill, minimum rotated rectangle | B S Bu; F0; ms | zero foreign tracks on declared planes; slot half-wave > 3 × f_knee |
| SPLIT-X | crossings of a boundary between two plane nets on the reference layer, with distance to the nearest stitching cap (mm, nH) | like RET-COV on boundaries between different-net fills | B S R; F0–F1 | Ott: 1–10 nF within 0.1" each side; never cross if both planes split |
| CAVITY | largest empty circle between GND stitching vias over two GND fills (mm); first mode (GHz) | grid sample of the overlap; KD-tree distance to vias; f ≈ c/(2√εr·d) | B S R; F0; ms | mode > f_knee and away from clock harmonics; λ/20 is the slogan version |
| GND-ISLAND | copper islands: area, distance to nearest stitching via, quarter-wave GHz | connected components of fills per net; via and pad contacts | B S R; F0 | no unstitched island with a quarter-wave inside the spectrum |

## B. Signal integrity

| ID | Measures (unit) | Algorithm | Inputs; tier, cost | Pass criterion source |
|---|---|---|---|---|
| XTALK | per victim: summed near/far-end noise (mV) | spatial hash of segments; pairs ≤ 5° from parallel, same or adjacent layer; K = 1/(1+(D/H)²) × min(1, 2T/t_r) per aggressor; sum worst 2 + 2 ([checkers-si-emi](../rules/checkers-si-emi.md) E) | B S R Bu; F1; ms | victim noise budget (mV); K = 0.1 at D = 3H, 0.5 at D = H [C] |
| VIA-STUB | stub length (mm), resonance (GHz) | drill span − used span − backdrill; f = c/(4ℓ√εr) | B S R; F1 | f_res > 3 × Nyquist; a 1.4 mm stub resonates at 26 GHz: irrelevant below PCIe Gen5 [C] |
| IMP-DISC | worst Γ along a net and its electrical length vs t_r | Z0 per piece from width, h, εr, reference state (Hammerstad or 2-D solve); neck-downs, reference changes, stubs | B S R Bu; F1–F2 | Γ budget per interface; ignore pieces shorter than t_r·v/6 |
| DIFF-BAL | pair skew (ps), asymmetric features (vias, bends, references); V_cm from mode conversion | per-leg delay; feature-by-feature diff; V_cm ≈ ΔT/t_r × V_swing [I] | B S R Bu; F1 | interface skew (ps); V_cm per CM-V budget |
| TOPO | branch stubs (ps), series-termination distance from driver (ps) | net tree from tracks and pads; branch delay vs t_r/6 | B R; F0–F1 | t_r/6 rule in ps |

## C. Power, PDN and commutation

| ID | Measures (unit) | Algorithm | Inputs; tier, cost | Pass criterion source |
|---|---|---|---|---|
| HOTLOOP-L | commutation-loop L (nH); overshoot L·di/dt (V) | members from the role model ([hot-loops](../rules/power/hot-loops.md)); realized copper path (pads, pours, vias) as a polygon chain; F1 current sheet over a plane L ≈ µ0·h·ℓ/(w + 2h); F2 PEEC/FastHenry on that copper | B S R Bu; F1 ms; F2 s | overshoot ≤ 0.2 × V_DS,max ([checkers-power](../rules/checkers-power.md)); 12 × 3 mm path 0.9 nH at 0.2 mm plane, 3.0 nH at 1.0 mm [C] |
| DECAP-L | per power pin: mounting + spreading L to its decaps (nH); \|Z\| in band (mΩ) | graph pin → via → plane pair → cap vias → cap; trace L′, via L, plane spreading (µ0·t/π)·ln(D/r) | B S R Bu; F1 | from Z_t; moving a 0402's GND via 5 mm away adds 1.3–1.9 nH, \|Z(100 MHz)\| 0.61 → 1.43 Ω [C] |
| PDN-Z | rail impedance vs frequency; peaks / Z_t | lumped RLC from DECAP-L, derated C, plane C, cavity modes; F2 plane-pair solver | B S R Bu; F1–F2; s | peak ≤ 1.57 × Z_t (robust), ≤ 3 × (tolerated) ([decoupling-pdn](../rules/decoupling-pdn.md)) |
| IR-DROP | DC drop per load (mV) | 2-D Laplace on each rail's copper per layer, vias as resistors, sources and sinks from R; scipy sparse | B S R Bu; F2; s | rail tolerance share (mV) |
| J-MAX | peak current density (A/mm²), location; neck width | same solve; potential gradient; min cut on the copper graph as F0 screen | B S R Bu; F2 | ampacity / ΔT budget; 1 mm neck, 1 oz, 5 A: 143 A/mm², 12 mV, 61 mW [C] |
| VIA-AMP | current per via in an array (A), sharing ratio | via currents from IR-DROP | B S R; F2 | via ampacity and thermal budget |
| PWR-TRACE | GND/power nets on thin traces instead of pours: pads off-pour, thin-track length (mm), summed R (mΩ) | pad shapes vs same-net fills; tracks narrower than w_thin | B S R Bu; F0 | each power pin's R and L to its plane within budget; OmniRouting failure mode |
| SW-AREA | switch-node copper area (mm²), capacitance (pF), displacement current C·dV/dt (mA) | fill + track area of the SW net per layer; C = area/h to each plane | B S R; F1 | EMI budget; minimum = pads + FET-to-inductor path ([buck](../rules/power/buck.md)) |
| SENSE-M | mutual L from hot loops and SW to FB, sense, Kelvin loops (nH); induced mV | Neumann double integral over polyline loops (with plane images) | B S R Bu; F1; ms | sense noise budget (mV); FB keep-out restated |
| KELVIN | shared R between sense tap and main current path (mΩ), error (mV) | path search on the copper graph; IR-DROP potentials at the tap pads | B S R Bu; F2 | shunt error budget ([current-sense-kelvin](../rules/power/current-sense-kelvin.md)) |

## D. EMI

| ID | Measures (unit) | Algorithm | Inputs; tier, cost | Pass criterion source |
|---|---|---|---|---|
| CM-V | CM voltage between cable connectors (µV) per fast net | MREMC: L_ret from trace position and board width; V_cm = h·V_dm or 2πf·L_ret·I_dm; E_max ([emc-placement](../rules/emc-placement.md)) | B S R Bu; F1; ms | 1 mV fails Class B; 100 µV for strict limits |
| IO-COUPLE | coupling from fast nets into unfiltered I/O nets near connectors (mV) | XTALK restricted to I/O victims between connector and filter | B S R Bu; F1 | I/O budget (mV), stricter than internal |
| FILTER-POS | position of ESD/filter/CMC along the path; shunt loop L to return (nH) | path order on the net graph; loop L of the shunt branch | B R; F0–F1 | protection topology ([checkers-si-emi](../rules/checkers-si-emi.md) I) |
| LOOP-RAD | DM field at 3 m per loop (dBµV/m) | Ott: E = 2.632×10⁻¹⁴·f²·A·I/r at harmonics up to f_knee; A from RET-RPQF geometry | B S R; F1 | ranking only: cables dominate |
| ANT-KEEP | copper inside antenna keep-outs, any layer (mm²) | polygon intersection | B R; F0 | module datasheet |
| SPECTRUM | coincidence of clock/switching harmonics with structure resonances (cavity, slot, island, stub) (dB) | line spectra from R; resonances from CAVITY, PLANE-PERF, GND-ISLAND, VIA-STUB; overlap score | B S R; F1 | no strong harmonic within a resonance's bandwidth |

## E. Thermal, high voltage, manufacturing physics

| ID | Measures (unit) | Algorithm | Inputs; tier, cost | Pass criterion source |
|---|---|---|---|---|
| THERM-DT | ΔT per dissipating part (°C) | 2.5-D resistive network from actual copper: pads, pours, vias (261 °C/W per 12 mil via), convection ([thermal](../rules/thermal.md)) | B S R Bu; F1–F2; s | part T_J limit; Quilter-style overheated length |
| THERM-COUPLE | ΔT at sensitive parts (crystal, reference, sensor, electrolytic) from neighbours (°C) | superposition on the same network | B S R Bu; F1 | victim drift budget |
| THERM-VIA | thermal-via count, pitch, plating under exposed pads → θ (°C/W) | via array under the EP polygon | B S R; F0 | datasheet θ assumptions |
| HV-FIELD | peak field between conductors at different potentials (V/mm), incl. inner layers and corners | edge-to-edge distance per voltage pair; corner enhancement for acute copper | B S R Bu; F1; F2 for corners | material strength with margin; standard clearance |
| CREEPAGE | surface geodesic creepage, 3-D clearance (mm) | geodesic around slots ≥ pollution-degree minimum ([isolation-creepage](../rules/isolation-creepage.md)) | B S R Bu; F1 | IEC 60664-1 / 62368-1 tables |
| COPPER-BAL | copper density per layer and between mirrored layers (%) | fill + track area per layer | B S; F0 | fab warp guidance |
| TOMBSTONE | thermal-mass asymmetry between the two pads of small passives (ratio) | copper connected within r of each pad | B; F0 | assembler guidance; kicad-happy uses 0.3 (unsourced) |
| VIA-AR | via aspect ratio, current/heat duty (ratio, A) | drill vs thickness; current from VIA-AMP | B S R; F0 | fab class |

## F. Integrity of the critic run

| ID | Measures | Algorithm | Tier |
|---|---|---|---|
| FILL-STALE | whether fills match a fresh refill (area delta %) | compare saved fills with a `kicad-cli --refill-zones --save-board` copy | F0 |
| ROLE-COVER | share of nets with roles, budgets, t_r; which critics ran per net | join critic logs with the role model | F0 |

## Open questions

- Uncalibrated F1 formulas here: slot-line VOID term, bridging-cap estimate, hot-loop sheet model -> [physics-critics-validation](physics-critics-validation.md#open-questions).
- Edge-critical role assignment is the weak input; prototype regex roles flag USB, CAN, SWD, PCIe names only.

## Sources

- Research notes: [rules_highspeed_emi.md § 11, 12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [rules_power_rf_analog_dfm.md § 17–20](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md).
- Altium Return Path rule (reference layer, minimum gap, max stitch-via distance 1.5 mm default): https://altium.com/documentation/altium-designer/pcb-high-speed-rule-return-path [P]
- Cadence return-path quality factor = loop L / ideal loop L, ideal 1.0: https://www.ema-eda.com/ema-resources/blog/investigating-return-path-discontinuities-understanding-impacts-and-effective-mitigation-strategies/ [V]
- Ott slot measurements: https://hott.shielddigitaldesign.com/techtips/tips-slots.html [P]
- Related: [checkers-si-emi](../rules/checkers-si-emi.md), [checkers-power](../rules/checkers-power.md).
