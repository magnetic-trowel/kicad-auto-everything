# High-voltage, manufacturing and mechanical physics

**TL;DR**
- **"Spacing" hides three different insulation physics problems.**
  - Gas discharge through air sets clearance; it is driven by peak and impulse voltage.
  - Surface tracking under contamination and moisture sets creepage; it is driven by RMS voltage and time.
  - Bulk and interface migration (CAF) sets via-to-via spacing; it is driven by DC bias and humidity.
  The tables mix physics with legal margin. IEC's altitude factors equal the air-pressure ratio p(2000 m)/p(h) within ~1% up to 20 km, which is pure Paschen similarity. Creepage-by-pollution-degree and "×2 for reinforced" are empirical and legal [C].
- **Rounded copper is real HV physics, but bounded.**
  - E_max at a 90° pour corner scales as (g/r)^(1/3): 4.9× the uniform field at r = 0.02g, 1.7× at r = g/2.
  - Our streamer-integral estimate of inception rises only ~1.4× from a sharp corner to r = g/2 (1 mm gap), because ionisation needs path length.
  - The 35 µm foil edge already costs 18–48% vs a uniform gap, whatever the plan-view shape.
  - Standards give no credit for rounding: case A assumes a 30 µm point [C].
- **Above ~20 km, PCB gaps sit near the Paschen minimum (~300–330 V).** More clearance barely helps there. Only solid insulation (coating, potting, buried layers) or V_peak below ~300 V works [C].
- **Manufacturing limits decompress into a few processes** [C]: etch (space ≈ 47 µm + 1.65·t), plating (throwing power set by the Wagner number; thieving evens current density), lamination (unbalanced copper or resin gives 0.04–0.3% bow vs the 0.75% limit), drilling (junction breakout Q(ring/σ)), soldering (surface tension is 2–110× gravity from 1206 to 01005; pad asynchrony is set by what the pad is thermally tied to, not by reliefs) and mechanics (a 0.1 mm screw-boss mismatch over 10 mm gives 9,600 µε vs 2,370 µε in the MLCC flex test).
- **Encode by origin.** Legal limits are hard and never relaxed. Fab absolute limits are hard. Fab "recommended" values become yield costs (critical area, σ-margin). Physics budgets are soft costs. Curves and any-angle routing cost nothing at a modern fab; allow them where physics pays (HV, flex, RF, pulsed current).

## Key facts

Scripts: [tm_hv_field.py](../../../tools/research/physics/tm_hv_field.py) (2-D boundary elements plus a streamer criterion), [tm_paschen_altitude.py](../../../tools/research/physics/tm_paschen_altitude.py), [tm_mfg_physics.py](../../../tools/research/physics/tm_mfg_physics.py), [tm_solder_reflow.py](../../../tools/research/physics/tm_solder_reflow.py), [tm_impedance_tolerance.py](../../../tools/research/physics/tm_impedance_tolerance.py).

### Insulation is three physics problems

| Mechanism | Failure | Driver | Geometry metric | What the tables encode | Origin |
|---|---|---|---|---|---|
| Gas discharge (clearance) | Spark or partial discharge (PD) through air | Peak and impulse V, air density, field shape | 3-D straight line | Breakdown for a worst-case point-plane gap ("case A": 30 µm point electrode, [IEV 442-09-03](https://electropedia.org/iev/iev.nsf/17127c61f2426ed8c1257cb5003c9bec/c6d461f12306edf3c1257d630053c246) [S]) plus margin; altitude factor | Physics + margin |
| Surface tracking (creepage) | Carbonised track | RMS V over years, moisture, contamination, material CTI | Surface geodesic; gaps narrower than X (0.25/1.0/1.5 mm at PD1/2/3) count as bridged | Empirical tracking experience by pollution degree and material group; ×2 reinforced | Empirical + legal |
| Bulk/interface migration (CAF) | Copper filament along glass fibre | DC bias, humidity, temperature, hole-wall gap, drilling damage | Hole-wall-to-hole-wall distance; alignment with the weave | Laminate qualification at 85 °C/85% RH, 10–100 V bias, 500–1000 h ([Isola/Trobough](https://www.isola-group.com/wp-content/uploads/Material-Process-Influences-on-Conductive-Anodic-Filamentation.pdf) [P]) | Physics + process |

**CAF design levers** (Isola, citing an NPL/Isola DOE [P]): gap (300–800 µm), voltage (5 vs 500 V), curing system and glass weave were the large factors; orientation "X-Y in grid – follows glass yarn directions" vs "rotated or staggered"; "Minimize adjacent bias locations (power-ground pins)"; and "Selecting a CAF-resistant material does not guarantee a CAF-resistant PCB."

**Mask, coating and inner layers.** Solder mask is not a B4 coating ([isolation-creepage](../rules/isolation-creepage.md) [P]); conformal coating can move a board to PD1 (IEC 60664-3). IPC-2221B functional spacing at 301–500 V is 0.25 mm internal (B1) vs 2.5 mm external uncoated (B2), a 10× ratio: inside cured resin there is no air, no contamination film and no copper/FR-4/air triple junction where PD starts. Burying HV nets is the densest physics option (TM25); safety standards then apply solid-insulation rules [I].

### Field enhancement at copper corners and edges

Results are from a 2-D boundary-element solve in a homogeneous medium [C, [tm_hv_field.py](../../../tools/research/physics/tm_hv_field.py)]:
- **Plan view, case 1:** a pad corner of radius r inside a pour at constant clearance g, which is what KiCad zone fill produces.
- **Plan view, case 2:** the end of a parallel run.
- The sharp-corner values are grid-limited (singular).

| r/g | 0 | 0.02 | 0.05 | 0.1 | 0.2 | 0.5 | 1 | 2 |
|---|---|---|---|---|---|---|---|---|
| E_max/(V/g), corner in pour | ∞ (13.7 at l = g/1000) | 4.94 | 3.65 | 2.90 | 2.31 | 1.74 | 1.43 | 1.23 |
| E_max/(V/g), end of run | ∞ (10.7) | — | 2.84 | — | 1.83 | 1.42 | 1.23 | — |

The 0.02 → 0.05 → 0.1 steps follow the wedge law r^(−1/3) (ratios 1.35 and 1.26).

**Cross-section, coplanar foils.** For infinitely thin coplanar foils on a dielectric interface the field equals the homogeneous field. A fully rounded 35 µm foil edge gives E_max/(V/g) of:

| Gap g | Enhancement |
|---|---|
| 0.25 mm | 2.6 |
| 0.5 mm | 3.5 |
| 1 mm | 4.9 |
| 2.5 mm | 7.5 |

Square edges are higher still and singular.

**Peak field is not the right metric.** Inception needs ∫α_eff ds ≥ K over the ionising region, not just E_max > 3 kV/mm. We use the quadratic effective-ionisation fit that reproduces the uniform-field law V = 24.22·δd + 6.08·√(δd) kV (d in cm; Kuffel, Zaengl and Kuffel [S]), applied along the worst field line [C]:

| Gap | Uniform field | Sharp pour corner | r = 0.05g | r = 0.2g | r = 0.5g | r = g | Coplanar 35 µm foils, rounded edge |
|---|---|---|---|---|---|---|---|
| 0.5 mm | 2.57 kV | 1.82 | 2.04 | 2.23 | 2.38 | 2.48 | 2.11 |
| 1 mm | 4.34 kV | 2.87 | 3.29 | 3.66 | 3.96 | 4.16 | 3.10 |
| 3 mm | 10.6 kV | 6.02 | 7.27 | 8.34 | 9.28 | 9.96 | 5.46 |

Sharpness costs 30–43% of breakdown voltage, and rounding to r ≥ g/2 recovers most of it. The foil edge is a second factor that plan-view rounding cannot fix; coating, burying or thicker copper can. IEC case A is conservative against these 2-D numbers, as a 3-D 30 µm point should be (1.5 kV at 0.5 mm vs our coplanar 2.1 kV). The case-A table sits 1.7–3.0× below uniform-field breakdown [C, [tm_paschen_altitude.py](../../../tools/research/physics/tm_paschen_altitude.py) §4]. Rounding buys real margin (PD inception, erosion, ESD and surge headroom), not a smaller legal clearance.

### Altitude and Paschen

[C, [tm_paschen_altitude.py](../../../tools/research/physics/tm_paschen_altitude.py)]. The ratio uses ISA pressure. IEC values are as commonly reproduced; 5000 m = 1.48 is confirmed in [TI SLUP419](https://www.ti.com/lit/pdf/slup419) [P].

| Altitude | p (kPa) | p(2000)/p | IEC factor | Uniform-field V_b at 1 mm, Townsend form |
|---|---|---|---|---|
| 0 | 101.3 | 0.78 | — | 5.0 kV |
| 5 km | 54.0 | 1.47 | 1.48 | 3.0 kV |
| 10 km | 26.4 | 3.01 | 3.02 | 1.7 kV |
| 15 km | 12.0 | 6.60 | 6.67 | 0.98 kV |
| 20 km | 5.5 | 14.5 | 14.50 | 0.58 kV |
| 30 km | 1.2 | — | — | 0.31 kV (0.5 mm: 0.45; 2 mm: 0.37) |

The air Paschen minimum is ≈ 327 V near 0.75 Torr·cm (305 V with our constants); below it no gas discharge happens at any gap or pressure. At 25–35 km, 0.5–2 mm gaps break down at 300–550 V and 5 mm gaps near 0.4–1 kV, so distance barely helps. Plan very-high-altitude HV around solid insulation, with ~300 V peak as the "needs encapsulation" threshold (TM21).

### Manufacturing processes as physics

| Process | Physics | What it bounds in layout | Our number | Rule verdict |
|---|---|---|---|---|
| Etch | Isotropic-ish dissolution; undercut t/EF per side; etchant exchange in narrow gaps | Min space and width vs copper thickness | JLCPCB min space ≈ 47 µm + 1.65·t (1–4.5 oz fit); EF 2–4 on 1 oz → 9–17 µm/side undercut, R +4–21% vs a rectangle [C §A] | Physics + process capability |
| Acid traps | Etchant pooling in acute pockets (older immersion etching) | Acute copper-free pockets | Forum/vendor evidence only: the rule "may have made sense over ten years ago" ([Cadence](https://resources.pcb.cadence.com/blog/are-acid-traps-still-a-problem-for-pcbs) [S]); residual concern for <4 mil on ≥1 oz and flex ([EEVblog](https://www.eevblog.com/forum/eda/acid-traps-310805/msg3983057) [S]) | Mostly legacy. Test enclosed pockets narrower than min space, not angles (TM38) |
| Electroplating | Current density follows the electrolyte field; isolated features over-plate | Copper balance on outer layers; thieving | Eurocircuits: "If the copper density is low … too much copper will be deposited"; plating index <0.40 "leads to problems" ([Eurocircuits](https://www.eurocircuits.com/?p=9575) [P]) | Physics |
| Hole plating | 1-D transmission line: TP = 1/cosh(L/2Λ), Λ = √(R_p·d/4ρ_e) | Via aspect ratio, board thickness | R_p 5 Ω·cm²: AR 8 → 79%, AR 12 → 61%; R_p 20 (strong additives): AR 12 → 87% [C §B]. Vendor: >80% at 12:1, 51% at 24:1 ([Uyemura](https://www.uyemura.com/new-developments-in-DC-acid-copper-for-vertical-plating-tanks.htm) [V]) | Physics (Wagner number) |
| Lamination | Bimetal bending from unequal CTE × modulus × distance from the neutral axis | Copper symmetry, dielectric symmetry | 1 oz outer imbalance 20/50/80%: 0.04–0.08 / 0.10–0.19 / 0.14–0.28% bow per 100 mm (Δα 3–6 ppm/K, ΔT 150 K); 0.1 mm resin-rich layer 0.31%; IPC SMT limit 0.75% [C §C] | Physics, at up to a third of the limit; outer layers matter most |
| Drilling | Position error σ (wander plus registration) | Annular ring; teardrops | Ring 0.10 mm: junction breakout 3e-5 per hole at σ 25 µm, 6e-3 at σ 40 µm; a 0.15 mm teardrop drops it below 1e-9 [C §I] | Physics + process σ |
| Dielectric and etch tolerance → impedance | Z0 sensitivity: −0.55% per 1% w, +0.59% per 1% h, −0.4% per 1% Dk | Fab impedance tolerance | 3σ w ±15 µm, h ±10%, Dk ±0.2: σ_Z = 2.2–2.9%, and h is 46–80% of the variance [C, [tm_impedance_tolerance.py](../../../tools/research/physics/tm_impedance_tolerance.py)] | Physics. Ask the fab for thickness control, not width |

**Critical-area yield** [C §J]. With a 1/x³ defect-size distribution, parallel conductors have short critical area L·x0²/s and open critical area L·x0²/w; yield is exp(−D0·ΣA). Widening a 0.1 mm gap to 0.2 mm halves its short risk, which puts a number on "unconstrained traces generously wide" (RTE-07).

### Solder-joint physics

**Tombstoning torque** [C, [tm_solder_reflow.py](../../../tools/research/physics/tm_solder_reflow.py)]. Compare the surface-tension torque γ·W·H (γ ≈ 0.5 N/m) with the gravity torque m·g·L/2:

| Package | Ratio |
|---|---|
| 1206 | 2 |
| 0805 | 4 |
| 0603 | 7 |
| 0402 | 18 |
| 0201 | 49 |
| 01005 | 110 |

The ratio scales as 1/L², and a fillet acts within 0.1–0.6 ms (capillary time). Only the other end wetting at nearly the same moment holds a small part down, so timing asymmetry is the variable to control.

**Lumped reflow model.** An 0402 has pad A on a 20×20 mm plane and pad B on local copper only, at h = 80 W/m²K [C]. ΔT is pad B minus pad A at liquidus; lag is the time between the two pads reaching liquidus.

| Link from pad A to the plane | No heavy part, ramp 1 K/s | Heavy 10×10×5 mm part on the plane, 1 K/s | Heavy part, 2.5 K/s |
|---|---|---|---|
| Solid | 0.87 K, 0.9 s | 10.4 K, 12.0 s | 14.0 K, 14.4 s |
| 4 spokes 0.25×0.25 mm | 0.87 K | 10.3 K | 13.9 K |
| 2 spokes 0.15×0.5 mm | 0.84 K | 10.0 K | 13.4 K |
| Neck, 0.15×2 mm trace | 0.67 K | 8.0 K | 10.7 K |
| Symmetric (both pads alike) | 0 | 0 | 0 |

- **Reliefs barely matter for small pads.** Spokes (6–54 mW/K) are still 60–500× stronger than a pad's own coupling (~0.1 mW/K), so the pad follows the plane either way.
- **What matters is what the plane is tied to:** heavy parts, shields and rails with a different time constant. The lag is about Δτ and barely changes with ramp rate. Fix it with symmetric environments, no heavy mass on a small part's plane region, or a long neck.
- **Reliefs remain physics for hand and wave soldering** of THT pins on multilayer planes, where an iron must beat the plane's drain.

**Electrical cost of reliefs is small** [C §G]. Four 0.25 × 0.25–0.5 mm spokes on 1 oz add 0.12–0.25 mΩ and 16–47 pH (no mutual inductance). That matters only in sub-nH hot loops and for pads carrying more than a few amps. [rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md) R25 quotes 50–90 pH with mutual inductance.

**Via-in-pad solder theft** [C §F]. Ratio of open via volume to printed solder volume:

| Case | Ratio |
|---|---|
| 0402 with one 0.2 mm via | 1.9 |
| 3×3 mm EP with nine 0.3 mm vias | 2.2 |
| Same EP with nine 0.2 mm vias | 0.8 |
| 0.1 mm microvia in a 0.5 mm-pitch BGA pad | 0.24 |

Open vias can swallow all the solder, which is the physics behind tent, plug or fill rules ([thermal](../rules/thermal.md) TH-02 conflict).

### Mechanics

**Surface strain** is ε = 6tδ/L² [C §H]:

| Load case | Strain |
|---|---|
| AEC-Q200 flex test, 2 mm over 90 mm | 2,370 µε |
| Same test, 5 mm (soft termination) | 5,900 µε |
| Screw boss pulling 0.1 mm over 10 mm | 9,600 µε (4,800 on a 0.8 mm board) |
| ICT fixture, 0.5 mm over 60 mm | 1,330 µε |

**MLCCs.** Orienting parts "parallel to the break line" is "the most effective means"; a slit helps when orientation cannot change ([Murata](https://article.murata.com/en-eu/article/layout-helps-prevent-chip-mlcc-from-cracking) [P]). Cracks start at the mounted-side termination edge at ~45° ([TDK](https://product.tdk.com/en/producttechnotes/16331.html) [S]). BGA pad cratering follows the strain-gauge limits of [IPC/JEDEC-9704A](https://webstore.ansi.org/preview-pages/IPC/preview_IPC+JEDEC+9704A-2012.pdf) [S] (numbers not read).

**Vibration.** The first mode of a simply supported 100×80×1.6 mm board is 640 Hz bare and 452 Hz with parts doubling its mass; 246 Hz at 160×100 mm; 226 Hz at 0.8 mm thick [C]. Steinberg's allowed displacement Z = 0.00022·B/(c·t·r·√L) penalises parts at mid-span (r = 1) [S], so put heavy and large parts near supports.

**Connectors.** Mating forces of 10–100 N belong in THT anchors and bosses, not SMT pad peel strength ([MEC-11](../verification/checklist-full-mechanical-placement-footprints.md)).

### Curves and angles at the fab

**Curves are native in the modern flow.** Gerber has circular arcs (G02/G03, multi-quadrant) and KiCad has had arc tracks since v6. Laser direct imaging rasterises at micrometre scale, so a curve costs nothing to image [I], and we found no fab that prices arcs. The real costs are tool-side: Freerouting emits no arcs, DRC on arcs is slower, and hand editing is harder ([practitioner_discussions § 4a](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)).

**45° routing is habit and tooling.** Its roots are tape-on-mylar drafting and early CAD grids ([SparkFun forum](https://community.sparkfun.com/t/should-i-be-able-to-see-via-holes-in-batchpcb-preview-image/4754) [S]) plus readability, not fab physics. It costs about 5.5% path length ([rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md)).

Curves pay where physics does: HV convex corners (r ≥ g/2), flex bends (strain), RF bends ([rf-geometry](rf-geometry.md)) and inner corners of pulsed-current pours (current crowding). Acute angles matter only as sub-resolution pockets.

### Encoding manufacturing physics

| Constraint class | Examples | Encoding |
|---|---|---|
| Legal | Creepage/clearance tables, reinforced ×2, altitude | Hard; physics may tighten, never relax; human sign-off |
| Fab absolute | Min trace/space per copper weight, drill, ring | Hard DRC `min` |
| Fab recommended | Comfortable widths, rings, spacing | Yield cost: σ-margin and critical area (TM30–31) |
| Physics budget | ΔT, inception margin, warp %, strain µε, tombstone Δτ | Soft cost in the ledger ([physics-ir](physics-ir.md) `barrier`, `heat_path`) |
| Habit | 45°, "no acute angles", fixed 5 mm spacings | Style channel or delete |

**Manufacturing caps the electrical optimum.** Min width and space plus dielectric thickness set the smallest loop inductance. Copper balance limits pour asymmetry. Reliefs add tens of pH. Heavy copper forces wider spacing and breaks fine-pitch escape. The optimiser should know these floors (TM52).

## Recommendations for our system

1. **Check insulation three ways:** straight-line clearance, surface geodesic with X-width bridging, and hole-wall/inner-layer distance with weave alignment. Add an inception-margin critic (HV-FIELD) at the true air density (TM20).
2. **Generate arc fillets** (r ≥ g/2) on convex HV copper corners. Report the margin gained, never a reduced legal clearance.
3. **Load fab capability as a process model** (etch, drill and registration σ; plating class). Run yield critics from it: critical area, junction breakout, plating index, warp proxy, via-in-pad theft.
4. **Replace "symmetric thermal relief" for tombstoning with a pad thermal-environment check:** Δτ between the pads of 2-terminal parts.
5. **Run mechanical load cases with a cheap plate solver:** depanel, screw bosses, ICT, vibration. Orient and keep out MLCCs and BGAs by computed µε.

## Conflicts and open questions

- **Thermal reliefs vs tombstoning:** our lumped model says reliefs change pad asynchrony by under 5%; vendor guidance and WS1 R25 say they balance small pads. No controlled study was found. Needs an assembly DOE or a transient FV check.
- **The streamer estimate is 2-D,** ignores surface flashover (lower) and fails near the Paschen minimum. Use it to rank geometries, not to certify.
- **IEC 60664-1 altitude factors other than 5000 m are from memory and secondary reproductions.** The 2020 edition moved them to Table F.10 [S].
- **Warp numbers are bilayer estimates.** Warp at reflow (above Tg) needs FEA or shadow moiré.
- **Not read:** IPC-9704A strain limits, IPC-6012 ring and breakout classes, IEC 60112 CTI details.

## Sources

- research notes: [rules_power_rf_analog_dfm.md § 6, § 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [expert_workflow_and_checklists.md § Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- Other URLs are linked inline where used. Tombstoning practice: https://www.circuitsassembly.com/ca/editorial/menu-news/20006-suntron-recommends-solutions-to-0402-tombstoning.html [S].

See also: [thermal-physics](thermal-physics.md), [thermal-hv-mfg ideas](../../ideas/physics-first/thermal-hv-mfg.md), [../rules/isolation-creepage.md](../rules/isolation-creepage.md), [../rules/dfm-fab-limits.md](../rules/dfm-fab-limits.md), [rule-genealogy-routing-style-dfm](rule-genealogy-routing-style-dfm.md), [physics-critics-catalog](physics-critics-catalog.md)
