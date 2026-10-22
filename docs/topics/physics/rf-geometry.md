# RF structures and trace geometry: when shape matters

*Tags: [P] primary source read, [S] snippet or secondary, [V] vendor claim, [I] our inference, [C] computed by us.*
*Scripts: [fe_geometry.py](../../../tools/research/physics/fe_geometry.py) (closed forms), [fe_field2d.py](../../../tools/research/physics/fe_field2d.py) (2-D field solver), [fe_cavity.py](../../../tools/research/physics/fe_cavity.py) (fences). Corner closed forms are cross-checked with [rg_corners.py](../../../tools/research/physics/rg_corners.py) ([rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md)).*

**TL;DR**
- **Geometry matters when a feature's excess charge or flux is a visible fraction of the edge:** |Γ| ≈ Z0·ΔC/(2·t_r). On a 50 Ω line with h = 0.1 mm:
  - a 90° corner (20 fF) gives 0.5% at 100 ps and 1.4% at 35 ps;
  - a teardrop is the same size;
  - an unvoided 0402 pad (64 fF) gives 4.6% at 35 ps.
  
  So corners, arcs, teardrops and any-angle routing are cosmetic for SI at edges slower than ~30 ps. Pads, stubs and vias are not.
- **Via stubs:** an open stub reflects |S11| ≈ (Z0/2Z_s)·tan(βL). A −20 dB budget at Nyquist gives L ≤ c / (4√εr · 7.9·f_N), which is Telian's "0.3/Gbps inch" within 20%. The rule is a reflection budget.
- **Fibre weave is a real physics reason for non-orthogonal routing:**
  - Aligned with a glass bundle, skew grows with length: 4–18 ps/in for a Dk contrast of 0.2–0.8.
  - Rotating by θ bounds it to a length-independent ≤ 0.6 ps at 10° (bundle pitch 0.45 mm).
  - Pick θ from segment length and from the Bragg period P/sinθ, which must keep the periodic-loading resonance above the band: θ ≳ 6° for 20 GHz.
- **Pad voids are an impedance-matching problem with a stackup-specific answer.** In our stackup, Z_pad is 25 Ω unvoided, 32 Ω with a 60% void, 39 Ω with a 100% void, and 46 Ω with the void extended 0.1 mm past the pad. So the TI 60%-vs-100% conflict is settled by solving, not choosing.
- **RF structures decompress to physics:**
  - Fence rows must sit closer than the TE10 cut-off width c/(2f√εr). One row's isolation is ≈ 20·log(2s·ln(s/2πr)/λ_d), but finite boards scatter it widely.
  - The antenna keep-out is the Chu sphere: radius ≥ 7.5 mm for VSWR 2 over the 2.4 GHz band.
  - "Match at the pin" scales with the pin's Q: 2 mm of line costs 0.03 dB at Q = 0.3 and 3 dB at Q = 4.
  - "Only GND under RF on every layer" is a proxy: one solid plane absorbs 46 dB at 100 MHz and 146 dB at 1 GHz.

## Key facts

### 1. "Geometry matters above X" (50 Ω microstrip, h = 0.1 mm, w = 0.19 mm, εr 4.3) [C fe_geometry A]

| t_r (≈ data rate) | f_knee = 0.35/t_r | \|Γ\| 90° corner (20 fF) | \|Γ\| 57% mitre (13 fF) | \|Γ\| teardrop (~20 fF) | \|Γ\| 0402 pad, no void (64 fF) | 90° turns of a 0.3 mm-pitch pair to reach 0.1·t_r skew | Longest via stub for \|S11\| ≤ 0.1 at f_knee |
|---|---|---|---|---|---|---|---|
| 5 ns (slow CMOS) | 70 MHz | 0.01% | 0.01% | 0.01% | 0.03% | 181 | 66 mm |
| 1 ns (fast CMOS) | 350 MHz | 0.05% | 0.03% | 0.05% | 0.16% | 36 | 13 mm |
| 300 ps (≈1–2 Gb/s) | 1.2 GHz | 0.17% | 0.11% | 0.16% | 0.5% | 11 | 3.9 mm |
| 100 ps (≈5 Gb/s) | 3.5 GHz | 0.5% | 0.3% | 0.5% | 1.6% | 4 | 1.3 mm |
| 35 ps (≈10–16 Gb/s) | 10 GHz | 1.4% | 1.0% | 1.4% | 4.6% | 1 | 0.46 mm |
| 15 ps (≈28–56 Gb/s) | 23 GHz | 3.4% | 2.2% | 3.3% | 10.7% | 1 | 0.20 mm |

- Corner capacitance uses the Kirschning-Jansen fits ([Qucs notes](https://qucs.sourceforge.net/tech/node76.html) [S], valid w/h 0.2–6, εr 2.4–10.4, to 14 GHz); the Gupta fit gives 21–22 fF. In the frequency domain a single corner reaches −30 dB return loss at ~9 GHz and −20 dB at ~29 GHz for h = 0.1 mm. These frequencies scale as 1/h, so thick 2-layer boards (h = 1.5 mm) reach −20 dB near 2 GHz ([rg_corners.py](../../../tools/research/physics/rg_corners.py)).
- **The optimal mitre** is M = 0.52 + 0.65·exp(−1.35·w/h), 57% at w/h = 1.9 (Douville and James, via [RF Essentials](https://rfessentials.com/resources/rf-glossary/bend-discontinuity/) [S]). Rounding removes only 21% of the corner copper, while compensation needs 70–90% ([Johnson](https://www.sigcon.com/Pubs/edn/bigbadbend.htm) [P]).
- **A reflection of 1% is invisible on an eye.** Several in phase (periodic bends, serpentines) add, so use the budget per net, not per feature.
- **Skew per bend** is p·θ for an arc and 2p·tan(θ/2) for a sharp corner: 2.8 ps (arc) and 3.5 ps (square) per 90° turn at 0.3 mm pitch. Rounding does not remove skew ([diff-pairs](../rules/diff-pairs.md)); alternating left and right turns does.
- **Serpentine self-coupling.** A coupled switchback short-circuits part of its own delay: up to 2× NEXT per switchback (Johnson, [diff-pairs](../rules/diff-pairs.md)). Use the per-layer kernel ([fields-si-emi](fields-si-emi.md) §4): at D = 6h, NEXT is 1.3% in microstrip and 0.02% in stripline, so stripline serpentines can be packed much tighter.

### 2. Origins of the geometry rules

| Rule | Origin | Regime where it is real | Replacement |
|---|---|---|---|
| No 90° corners | Legacy (1971 MECL handbook), habit | Thick substrates above a few GHz; mm-wave; ESD strike paths, where field enhancement at a sharp corner arcs over (TI: ≥7 kV at a 90° corner, keep radii ≥ 2.6 mm [P]) | \|Γ\| budget per net; HV/ESD corner-radius rule from field strength |
| Arcs or 135° on RF | Physics at multi-GHz, habit below | Above ~5–10 GHz on thin substrates, lower on thick ones | Same \|Γ\| budget plus radiation (curvature radiation grows as w/R and h/λ [I]) |
| Teardrops | Manufacturing: drill wander, annular-ring breakout, stress cracks | Small annular rings and flex | DFM rule; the SI cost is about one corner's worth |
| 45° only | Tool limitation (octilinear routers), habit | None for physics; octilinear costs ≤ 8.2% length vs straight [C] | Any-angle allowed; useful for fibre weave and density |
| No acute angles | Manufacturing legacy (acid traps) | Weak with modern etch [S] | DFM check only |
| Rotate 10–35° to the weave | Physics (glass/resin Dk contrast) | Long pairs at ≥ ~10 Gb/s | Angle from segment length and Bragg period (§3) |
| Void under SMD pads | Physics | t_r ≲ 50 ps | Field-solved void extent (§4) |
| Stub < 15 mil, < 0.3/Gbps | Physics | ≥ 5 Gb/s | \|S11\| budget (§5) |
| Fence pitch λ/20 | Physics proxy | RF, compartments | Isolation target plus cavity check (§6) |
| RF ≥ 20 mm from SMPS | Vendor heuristic [V] | Near-field coupling | Coupling budget (magnetic: inductor dipole; electric: switch-node area) |

### 3. Fibre weave [C fe_geometry B]
- **Dk contrast:** E-glass Dk ≈ 6, resin ≈ 3. Loyer et al. (DesignCon 2007) measured mean differential skew 3.85 ps/in (σ 4.15). Intel adopted a 15 ps/in cut-off, equivalent to ΔDk ≈ 0.8 ([fiber-weave summary](https://smtnet.com/library/files/upload/Practical_Fiber_Weave_Modeling.pdf) [S]). Our closed form gives 2.2 / 4.4 / 17.6 ps/in for ΔDk 0.1 / 0.2 / 0.8. At ΔDk 0.8, 100 mm aligned is 70 ps, nearly two 25 Gb/s UIs.
- **Rotation.** With the trace at θ to bundles of pitch P, the trace samples glass and resin periodically, so skew stops growing with length and is bounded by ≈ 2·δ·P/(2π·sinθ), where δ is the aligned skew per unit length. Worst case (ΔDk 0.8):

  | θ | Residual (P = 0.45 mm) | Bragg period P/sinθ | Bragg frequency |
  |---|---|---|---|
  | 2° | 2.9 ps | 12.9 mm | 6.6 GHz |
  | 5° | 1.1 ps | 5.2 mm | 16.5 GHz |
  | 10° | 0.57 ps | 2.6 mm | 33 GHz |
  | 15° | 0.38 ps | 1.7 mm | 49 GHz |

- **Two constraints set θ:**
  1. The segment must cross several bundles: θ ≥ asin(3P/L), which is 7.8° for a 10 mm segment but only 1.5° for 50 mm.
  2. The periodic Dk loading forms a Bragg grating, so keep c/(2√ε_eff·P/sinθ) above the highest frequency of interest: θ ≳ 6° for 20 GHz at P = 0.45 mm [I].
  
  TI's 10–35° ([stackup](../rules/stackup.md)) satisfies both. Very small angles (1–3°) fix skew on long runs but can put a weak stopband in band. Coarse weaves (7628, P ≈ 0.8 mm) need roughly twice the angle.
- **Alternatives:** spread glass (still ~3–8 ps/in measured on 1035/1078 [S]), rotating the image on the panel (costs panel yield), and zig-zag routing. Each is a cost trade the system can price.

### 4. Pads, voids and reference cut-outs [C fe_field2d]
A 0.5 mm wide pad on a 50 Ω line, with L2 at h = 0.1 mm and L3 0.235 mm below L2:

| Reference under the pad | Z_pad | C′ (pF/mm) |
|---|---|---|
| L2 solid | 25.1 Ω | 0.248 |
| L2 voided over 60% of the pad width | 31.9 Ω | 0.191 |
| L2 voided over the full pad width | 39.1 Ω | 0.151 |
| L2 voided to 0.1 mm beyond the pad | 46.5 Ω | 0.125 |
| L2 removed, reference L3 | 55.5 Ω | 0.105 |

- The line itself has C′ = 0.120 pF/mm. The void that matches the line here is the pad width plus about 0.1 mm. A 60% void leaves the pad at 32 Ω. TI's 60% ([SPRAAR7J](https://www.ti.com/lit/pdf/spraar7)) and Heck's 100% ([usb3-usb4-typec](../rules/interfaces/usb3-usb4-typec.md)) are each right for some stackup. The system should solve for the void per stackup and pad.
- The same method sizes antipads under connector pins, BGA balls and AC caps: choose the cut-out so the local Z equals the line Z, then check that the hole does not form a slot for neighbouring nets ([fields-si-emi](fields-si-emi.md) §2).

### 5. Via transitions and stubs [C fe_geometry C]
- **Quarter-wave frequency** f_qw = c/(4L√εr): stubs of 0.25 / 0.5 / 1.0 / 1.4 / 2.4 mm resonate at 145 / 72 / 36 / 26 / 15 GHz (εr 4.3; pads and non-functional pads lower it).
- **Reflection budget:**

  | Data rate (NRZ) | Longest stub, \|S11\| ≤ 0.1 at Nyquist | Telian 0.3/Gbps in |
  |---|---|---|
  | 5 Gb/s | 1.84 mm | 1.52 mm |
  | 10 Gb/s | 0.92 mm | 0.76 mm |
  | 16 Gb/s | 0.58 mm | 0.48 mm |
  | 28 Gb/s | 0.33 mm | 0.27 mm |
  | 56 Gb/s | 0.16 mm | 0.14 mm |

  Telian's rule is therefore "a −20 dB stub reflection at Nyquist" with Z_s ≈ Z0 ([SIJ](https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs) [P]). A lower-impedance stub (big pads, NFPs) reflects more. The budget form handles that; the length rule cannot.
- **Backdrill residue** of 0.2–0.25 mm resonates above 140 GHz, so it is negligible below 56 Gb/s.
- **Choosing layers to avoid stubs** (L1→L(n−1), blind vias) is an assignment problem with a stub-length price. Give it to the router, not a fixed rule.
- **Return vias** at a transition are sized by cavity excitation, s ≈ λ_d/10 at Nyquist ([fields-si-emi](fields-si-emi.md) §2).

### 6. RF transmission lines, bends, fences, shields
- **Microstrip vs CPWG.** A coplanar ground at gap g ≥ 2h changes Z0 by < 2.2%; at g = h by −5% (thin copper) to −8.4% (t = 0.35h); at g = 0.5h by −13% to −21% [C, [rt_fill_z0](../../../tools/research/physics/rt_fill_z0.py), converged to 0.1 point]. CPWG with g ≥ 2h is microstrip with a fence. u-blox's "use the CPW model if gap ≤ 5× track width" is conservative but safe ([rf](../rules/rf.md)).
- **Bends on RF:** 57% mitre or an arc. A radius of a few w makes the bend's excess C negligible [I]. At 2.4 GHz on h = 0.1–0.2 mm even a square corner is below −30 dB return loss (it reaches −30 dB at ~4.6 GHz for h = 0.2 mm, per rg_corners.py). The rule is real for 5 GHz and up, and for thick boards.
- **Fence rows.** Two rows of vias form a dielectric-filled channel. It must stay below the TE10 cut-off, W < c/(2f√εr): 30 mm at 2.44 GHz (FR-4), 12 mm at 6 GHz, 3.3 mm at 24 GHz (RO4350B), 1.1 mm at 77 GHz (RO3003) [C].
- **Fence pitch.** For an infinite parallel plate, one row passes |T| = 2/√(4 + B²), with B = λ_d/(s·ln(s/2πr)): −19 dB at λ_d/20 and −9 dB at λ_d/10 [I]. In finite boards the cavity model scattered the realised isolation from +3 to −33 dB around this [C fe_cavity], because the fence creates new resonant rooms. Use the closed form to choose pitch and the cavity model to verify. SIW walls that must guide a mode need pitch ≤ 2d and d ≤ λ_g/5 (Deslandes and Wu; Xu and Wu, via [Wikipedia](https://en.wikipedia.org/wiki/Substrate-integrated_waveguide) [S]).
- **Shield cans are cavities:** TE110 = (c/2)·√(1/a² + 1/b²) is 12.5 GHz for a 20 × 15 mm can and 6.25 GHz for 40 × 30 mm [C]. A large can over a Wi-Fi 6 GHz radio can resonate in band, so check it or add absorber.

### 7. Matching at the pin [C fe_geometry D]
At 2.44 GHz (ε_eff 3.1), 50 Ω microstrip rotates 5.2°/mm. Suppose the match is designed to present Z_pin* at the pin but is placed l mm away. The mismatch loss then depends on the pin's Q:

| Pin impedance (Q) | 1 mm | 2 mm | 5 mm |
|---|---|---|---|
| 35 − 10j (0.3) | 0.01 dB | 0.03 dB | 0.16 dB |
| 15 − 30j (2) | 0.17 dB | 0.63 dB | 2.8 dB |
| 5 + 20j (4) | 1.0 dB | 3.2 dB | 8.6 dB |

So "first match element ≤ ~1 mm" ([rf](../rules/rf.md) RF-03) is right for high-Q PA/LNA ports and irrelevant for near-50 Ω module outputs. The budget is l_max(Q, mismatch allowance). The fix for a long line is to re-design the match for the line, not to move parts.

### 8. Antenna keep-outs and ground under RF
- **The Chu limit** Q ≥ 1/(ka)³ + 1/(ka) (McLean 1996 [S]) sets the smallest sphere, including the ground currents, that can radiate a bandwidth B. VSWR-2 bandwidth is B = 1/(√2·Q) [C]:

  | Band | Bandwidth | Minimum sphere radius | λ/2π |
  |---|---|---|---|
  | 2.44 GHz | 83.5 MHz | 7.5 mm | 20 mm |
  | 915 MHz | 26 MHz | 18.6 mm | 52 mm |
  | 868 MHz | 7 MHz | 12.6 mm | 55 mm |
  | 5.5 GHz | 600 MHz | 5.1 mm | 9 mm |

  Metal (parts, pours, batteries) inside this sphere stores reactive energy and detunes the antenna. That is what the vendor keep-out polygon encodes. The reactive near field extends to λ/2π. Keep the vendor polygon as the hard rule ([rf](../rules/rf.md)), and use the sphere to judge things the polygon does not cover: enclosure walls, the battery, a nearby connector. In-situ tuning is still mandatory.
- **The ground plane is half the antenna** for monopole-type and chip antennas. Its length near λ/4–λ/2 sets the bandwidth (handset chassis-mode analysis, Vainikainen et al. 2002 [S]). This is the physics behind u-blox's "≥24 × 30 mm, not above 50 × 50 mm" [P].
- **Ground under RF.** Absorption through a copper plane is 8.686·t/δ. For 35 µm: 4.6 dB at 1 MHz, 14.5 dB at 10 MHz, 46 dB at 100 MHz, 146 dB at 1 GHz [C]. One intact plane therefore isolates GHz RF from everything below it. "Only GND under the RF trace on every layer" really protects against holes, antipads and slots in that plane, and against 2-layer boards. On a board with an intact L2, check reference integrity within ±3h of the RF line; ban foreign nets on L3 and below only for low-frequency magnetic aggressors, where the plane does not shield.

## Recommendations for our system
1. **Gate geometry rules by physics.** Compute each net's |Γ| budget and t_r. Apply corner, arc, mitre and teardrop constraints only where the table says the effect exceeds the budget. Otherwise let the router choose geometry for length, density or manufacturing.
2. **Solve pad voids and antipads per stackup** with the 2-D solver (seconds), and emit them as KiCad zones or rule areas.
3. **Replace stub-length limits with an |S11| budget,** using Z_s from the pad stack. Let the router trade layers against backdrill and microvias by price.
4. **Fibre-weave mode for long SerDes pairs:** an any-angle segment constraint θ ∈ [θ_min(L, P), 45°], avoiding Bragg frequencies in band. Panel rotation is offered as a fab-cost alternative.
5. **RF:** a fence generator driven by isolation targets and channel cut-off, with a cavity-model check. Chu-sphere keep-out volumes in the 3-D mechanical check. A pin-Q-based l_max for the first match element.

## Conflicts and open questions
- The arc-radius guidance ("a few w") is [I]. A Kirschning-style closed form for curved bends was not found.
- The Bragg-in-band risk at small weave angles is inferred, not measured; spread-glass data disagree on how much it helps.
- Pin impedances in §7 are illustrative, not from a datasheet. Real optimum loads come from vendor reference designs.
- Fence isolation in resonant boards needs full-wave verification; the closed form is optimistic or pessimistic depending on the modes.

## Sources
- Research notes: [rules_power_rf_analog_dfm.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [rules_highspeed_emi.md § 5, 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [verification_rules.md § 1B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md)
- Johnson, "Big bad bend": https://www.sigcon.com/Pubs/edn/bigbadbend.htm [P]
- Telian, stubs: https://www.signalintegrityjournal.com/articles/2962-fixing-the-problem-of-stubs [P]
- Qucs technical notes, microstrip corner: https://qucs.sourceforge.net/tech/node76.html [S]
- Fibre weave: Loyer, Kunze, Ye, DesignCon 2007, summarised at https://smtnet.com/library/files/upload/Practical_Fiber_Weave_Modeling.pdf [S]; https://iconnect007.com/article/61693/berts-practical-design-notes-fiber-weaveinduced-timing-skew/61696/design [S]
- TI SPRAAR7J (voids, weave): https://www.ti.com/lit/pdf/spraar7 [P via notes]
- SIW design rules: https://en.wikipedia.org/wiki/Substrate-integrated_waveguide [S]

See also: [fields-si-emi](fields-si-emi.md), [fields-emi-budget](fields-emi-budget.md), [rf](../rules/rf.md), [myths-and-contested](../rules/myths-and-contested.md), [diff-pairs](../rules/diff-pairs.md), [ideas: si-emi-rf](../../ideas/physics-first/si-emi-rf.md)
