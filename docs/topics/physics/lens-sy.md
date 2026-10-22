# Lens SY: symmetry, reciprocity and duality

**TL;DR**
- **Reciprocity is why "one solve per victim" works, and it is not the adjoint.** The board's field problem (copper, laminate, linear ferrite) is reciprocal. The circuit is not, but an adjoint (Aᵀλ = c) needs only linearity. What breaks round 1's S1 and S3 is nonlinear victims and periodic switching or sampling (which needs a periodic adjoint). One theorem, the lead field, unifies susceptibility maps, κ_ab maps and Kelvin taps; MREMC's edge law is reciprocity times Maxwell's strip distribution (FD within 1–10% [C]).
- **Copper planes break electric/magnetic duality.** A plane turns a flat loop into a quadrupole, so mutual L ∝ h_a·h_v. It turns a dv/dt node into a vertical dipole fixed by ∫V dA, so mutual C barely depends on h: h^0.19 against h^1.98 for 2 mm strips [C]. Thin prepreg is a lever on loops only, and coplanar guards do almost nothing over thin dielectric (−1% at h = 0.1 mm [C]). Over a plane, capacitive coupling from wide dv/dt copper dominates beyond about 2 mm for a 1 kΩ victim [C].
- **Images and 2-D duality make empirical laws exact.** The slit cost is a mode-III crack with images: ΔR = −(2/π)R_s·ln cos(πΔψ/2I), and an edge notch costs exactly 2×. FD agrees within 1.5%. The dual of a cut is a conducting needle along the flow. For any objective, a cut costs (π/4)R_s·Δψ_u·Δψ_λ: within 3–12%, where the plain adjoint misses by 13–35× [C]. Babinet gives the slot inductance independently, within 6% of round 1.
- **Mode conversion is symmetry breaking at *changes* of imbalance:** V_cm = Δh·V_dm, so Bal and Vcm are one quantity. Near a 100 Ω pair, copper matters only within about 3h (−60 dB at 2h); a 10 µm leg-width mismatch converts −41 dB, a slot under one leg −22 dB [C]. Mirrored halves give a null plane and a quieter far field (−22 dB at 100 mm), not a smaller halo (−2% radius over a plane) [C].
- **Scale and gauge.** f_x is a length, ℓ_d = R_s/(ωμ0), compared with each structure's size. Corner and edge fields follow r^(π/α−1), which explains round 1's −1/3, −0.2, t^(−1/3) and 1/√d. Only loop EMFs are physical, so every voltage budget must name its loop.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [sy_duality_balance.py](../../../tools/research/physics/sy_duality_balance.py) and [sy_images_symmetry.py](../../../tools/research/physics/sy_images_symmetry.py). Ideas SY1–SY32: [lens-sy ideas](../../ideas/physics-first/lens-sy.md).

## Key facts

### 1. Principles

Circuits are the limit where these symmetries hold trivially (one ground node, equipotential wires, invisible fields); layout is where they bend or break.

| # | Principle | Statement | On a board |
|---|---|---|---|
| P1 | Reciprocity (Lorentz; Tellegen) | ∫(E_a·J_b − H_a·M_b)dV = ∫(E_b·J_a − H_b·M_a)dV for symmetric ε, μ, σ; Z = Zᵀ. Lead field: a port reads a source as V = (1/I_L)∫J_src·E_L dV, where E_L is the field of current I_L fed into the port ([Malmivuo & Plonsey ch. 11](https://www.bem.fi/book/11/11.htm) [P]) | Coupling a→b = b→a; a victim's susceptibility map is its own field when driven; for linear victims immunity mirrors emission |
| P1′ | Adjoint ≠ reciprocity | dJ/dp = −λᵀ(∂A/∂p)u with Aᵀλ = c for any linear(ized) A. Reciprocity only lets the forward solver supply λ | `.noise` handles active parts. Switching and sampling need the periodic adjoint, which maps f → f ± k·f_s (PXF, Telichevesky–Kundert–White 1996 [S]) |
| P2 | Duality | (a) EM: E→η0H, H→−E/η0, PEC↔PMC; Babinet–Booker Z_slot·Z_strip = η0²/4 [S]. (b) Sheets: K = −∇φ/R_s = ∇ψ×ẑ, so φ/R_s↔ψ and cut↔needle (Keller [S]). (c) Planar networks: node↔mesh, C↔L, V↔I | Every loop rule has a node twin; every cut a bridge twin; every slot a floating-strip twin |
| P3 | Images | PEC: q→−q, horizontal I→−I, vertical I→+I, vertical m→−m, horizontal m→+m. Neumann edges (sheet edge, adiabatic edge, open cavity edge = PMC): same sign | Valid for field patterns larger than ℓ_d = R_s/(ωμ0), a few h from edges, below cavity modes |
| P4 | Mirror decomposition | If PXPᵀ = X (X = R, Lp, C), even (CM) and odd (DM) modes do not mix; conversion is first order in the antisymmetric part. At a change of current-division factor h = C1g/(C1g+C2g), V_cm = Δh·V_dm (imbalance-difference model [S]). Odd sources are null on their mirror plane. Curie: responses keep the symmetry of cause plus structure | Balance, cancellation, current sharing |
| P5 | Gauge | φ and A are not physical; ∮E·dl = −dΦ/dt and port quantities are. Partial inductance fixes a gauge (A → 0 at infinity) | "Ground" means earth, reference or return ([André 2025](https://digital.incompliancemag.com/issue/april-2025/grounds-and-returns/) [P]); only the return is a conductor role, a reference is a measurement loop |
| P6 | Scale | Near a wedge of angle α, fields go as r^(π/α−1) (Jackson §3.4 [S]). The intrinsic lengths are h, ℓ_d(ω), screening λ, δ and λ_g. Similarity: L, C ∝ s and E ∝ 1/s; for gas breakdown, p·d | Regimes per structure, not per board |
| P7 | Noether-style pairs | Gauge ↔ KCL; time translation ↔ frequency conservation (switching breaks it to f mod f_s); passive time reversal ↔ Z = Zᵀ; mirror ↔ mode parity; permutation ↔ equal sharing; matched moments ↔ gradient cancellation to order k | Each symmetry gives a checkable invariant |

### 2. Three derivations

**D1. Planes break node/loop duality.** Consider lateral distance D ≫ h, w (2-D, per unit length).
- **Loop.** Current I at height h_a plus its image is a line dipole 2I·h_a. Its flux through the victim's strip-to-plane loop gives L_m′ = μ0·h_a·h_v/(πD²), independent of width.
- **Node.** A wide strip at V on thin dielectric is, seen from above, a potential patch. Its field is a line dipole 2ε0·w_a·V, and a grounded victim intercepts ε0·E_z·w_v. So C_m′ = ε0·w_a·w_v/(πD²), independent of h.
- **3-D.** p = 2ε0∫V dA gives C_m = ε0·A_a·A_v/(2πr³), while M ≈ (μ0/4π)·18h²·A_a·A_v/r⁵.

FD check (microstrip, εr 4.3, D = 5 mm, h = 0.05–0.4 mm) [C]:

| Strip widths | L_m′ slope | C_m′ slope |
|---|---|---|
| 2 mm / 2 mm | h^1.98 | h^0.19 |
| 2 / 0.15 mm | h^1.92 | h^0.47 |
| 0.15 / 0.15 mm | h^1.85 | h^0.74 |

Also [C]:
- A grounded 0.5 mm coplanar guard cuts both couplings by only 1–3% at h = 0.1 mm, and by 48% at 1.6 mm.
- For a 20 mm² switch node (6 V/ns) and an 8 mm² hot loop (5.5 A/ns) over a plane 0.1 mm down, capacitive pickup exceeds magnetic beyond 9.7, 2.2 and 0.7 mm for 50 Ω, 1 kΩ and 10 kΩ victims.

**D2. The MREMC edge law is reciprocity.** By P1, the voltage a trace's DM current induces between cable points a and b equals its overlap with the antenna-mode current that would flow on the plane if a–b were driven: V_ab/I = jω·μ0·h·K_ext(x)/(2I_ext) per unit length. For a strip plane of width W, K_ext is Maxwell's distribution I_ext/(π√((W/2)²−x²)). Hence L_ret(x) = μ0·h/(2π√((W/2)²−x²)).
At the centre this is MREMC's (μ0/π)·h/W ([fields-emi-budget](fields-emi-budget.md)); toward the edge it is MREMC's 1/√(1−(2x/W)²), the −1/2 exponent of a thin sheet's edge. FD/prediction is 0.90–0.99 for x/(W/2) = 0–0.975 [C]. The voltage-driven twin is h_C(x) = w_e/(2π√((W/2)²−x²)) with capture width w_e ≈ w + 2–4h [C]. Current-driven common mode scales with height, voltage-driven with width: D1 again.

**D3. The slit law is a crack with images.**
- **Small cut.** In 2-D, a thin cut across sheet current K0 has polarizability π(ℓ/2)², so ΔP = (π/4)R_s·Δψ², round 1's XD2.
- **Centred cut.** A strip's edges are mirrors, so a centred cut and its images form a periodic collinear array of period W. Its exact mode-III energy gives ΔR = −(2/π)R_s·ln cos(πq/2) with q = Δψ/I.
- **Edge notch.** A notch plus its image is a centred cut in a period-2W array, so ΔR = −(4/π)R_s·ln cos(πq/2). That is twice an interior cut at every q.
- **Check.** Zero-width-cut FD agrees within 0.7–1.5% (0.05 mm cells); the quadratic law reads 28% low at q = 0.75 [C].
- **Dual (Keller).** A conducting needle along the flow saves (π/4)·R_s·(Δφ/(R_s·I))² (FD within 0.2% at q = 0.25 [C]). Long needles saturate where long cuts diverge.
- **Any objective.** By reciprocity plus the crack's polarization tensor, ΔJ = (π/4)R_s·Δψ_u·Δψ_λ, using the stream-function steps of the forward and adjoint solutions across the cut. For a Kelvin-pair objective it is within 3–12% of FD, where the first-order adjoint over the removed links was 13–35× low [C].

So the "adjoints miss cuts" finding ([solver-ladder](solver-ladder.md): 0.27 vs 8.1 mW) was a missing tensor, not an adjoint failure.

### 3. More derivations, checked against round-1 numbers [C]

| Round-1 result | SY explanation | Check |
|---|---|---|
| Bend peak J 2.6/3.3/4.1 per mesh doubling; pulse J² 7.7/3.7/1.75 at 10 µs/100 µs/1 ms; 135° bend r^(−0.2); HV (g/r)^(1/3) ([power-copper](power-copper.md), [hv](hv-and-manufacturing-physics.md)) | Wedge exponent π/α−1 = −1/3 (270°), −0.2 (225°). ⟨J²⟩ over a diffusion disk ∝ ρ^(−2/3) ∝ t^(−1/3) | Ratios 1.27/1.24 vs 2^(1/3) = 1.26; 2.08/2.11 vs 10^(1/3) = 2.15 |
| Corners (new duality) | Concave copper corners crowd current and are E-free; convex corners crowd E (270° gap) and carry no current (+1) | Round convex HV corners, fillet concave pulse corners; chamfer convex pour corners freely |
| Slot ΔL ≈ μ0·l/(2 ln(4l/g)) ([fields-si-emi](fields-si-emi.md)) | Babinet: L = (η0²/4)·C_strip = π·μ0·l/(8(ln(4l/g)−1)) | Within 0.3–6%. Both exceed PEEC by up to 1.5× for short narrow slots |
| Reverse return 13.6 → 2.4 ([cross-domain-lessons](cross-domain-lessons.md)) | Z2 symmetry (180° turn plus rail swap) forces I_k = I_(N+1−k): pairs only. A binary tree's group is transitive | Pairs equal to 1e-15. Tree 1.000; 1.067 with one branch +20% |
| Perimeter stitching raises f₁ "only ~1.5×" | Edges go PMC → PEC (TM10 → TM11): √(1+(a/b)²) | 1.67 for 40×30 mm; cavity model 1.56 |
| f_x found four times ([research-gaps](research-gaps.md)) | One length ℓ_d vs each scale. 1 oz mirrors a 5 mm loop above 12 kHz, a 20 mm region above 3 kHz, a trace return at h = 0.1 mm above 0.6 MHz | ℓ_d = 0.12 mm at 500 kHz |
| Weave rotation up to 45° (FE42) | Cloth is a 2-D lattice: skew grows along directions normal to strong reciprocal vectors (axes; the diagonal if crossings add Dk) | Toy square weave: 45° 1.5 ps per 2 in, others ≤0.5, aligned 31 |

### 4. Human rules and their principles

| Rule | Principle | Physics |
|---|---|---|
| Return under the trace; no slots under fast nets | P3, P2a | Keep the image intact. A slot is a magnetic dipole |
| Many small holes, not one slot (cans, vents, antipads) | P2a | Aperture polarizability ∝ size³ (Bethe [S]) |
| Connectors on one edge; nothing fast between them; 2h/3h/90 mil from edges | P1, P6 | κ_ab is the antenna-mode current density, with the −1/2 edge law |
| Symmetric pairs, matched lengths, twisting | P4 | Only the antisymmetric part converts, and only where it changes |
| Symmetric feeds; alternating decaps; opposite-current vias; common centroid | P4, P7 | Transitive groups share equally; odd arrangements make mutuals negative; matched moments cancel gradients |
| Split or star ground | P5, P6 | Ground potential exists only below the region's mirroring frequency |
| Guard traces | P2, P3 | They help only where the image is weak (thick boards, edges) |

### 5. Convergences and synergies round 1 missed

- **One lead-field theorem (P1, P1′).** XD35, FE3, DR3, S3, S11, XD53, XD72, LA7, LA8, DR26 and the Kelvin L_err analysis ([pdn-and-commutation](pdn-and-commutation.md)) are one theorem. So exclusion zones are sufficient, not necessary: a measurement needs orthogonality, R_s∫K_aggr·K_lead dA = 0 and ∫J·A_lead dV = 0, and foreign current may cross its region along lead equipotentials.
- **One Babinet object.** Slot ΔL (FE2), slot antennas, merged antipads (FE4), stitching pitch from slot modes (XD83), can seams (FE32), hatched planes (XD80) and floating copper (PW11) are all apertures or islands with a polarizability and a half-wave resonance c/(2ℓ√ε_eff).
- **One wedge exponent** spans power, HV, routing style, EMI edges and slit tips (§3).
- **One image machinery.** Thermal edge lattices (TM2), slit images (D3), the Maxwell strip (D2) and open cavity edges are one construction, with the sign set by the boundary type.
- **One Z2 mechanism behind 16 ideas from six workstreams:** XD11, LA35, PW27, PW33, PW36, PW51, PW14, XD47, XD58, TM14, XD76, FE16, DR44, PC16, FE35, FE36. Each reduces to: declare a symmetry, compute its antisymmetric residual.
- **Synergy: one map, both CM mechanisms.** FE3's map (one solve per connector pair) gives current-driven coupling ∝ h·K_ext and voltage-driven ∝ A·σ_ext; round 1 used the latter only for heatsinks.
- **Synergy: cuts as measurement tools.** Pricing a cut by Δψ_aggr·Δψ_lead finds slots that reduce foreign coupling into a measurement: the physics of a split ground that works.

### 6. Transfers

| From | To |
|---|---|
| Thermal image lattice (TM2) | IR drop, decap reach (XD113), slit prices, κ maps near edges |
| Fracture mechanics (mode III, polarization tensors) | Cut prices in XD2, SIM25, OP41, PW10, S2 |
| Bioelectromagnetic lead fields | Kelvin and measurement design (S11, XD72, DR26) |
| RF-IC periodic analysis (PXF, PNoise) | DR3, S1 for switching and sampled victims; S8 modulo f_s |
| Imbalance-difference model (EMC) | FE35 (sum Δh steps with phase), PC16, XD24 pin maps |
| Group theory (Curie, transitive actions) | PW14, XD58, multiphase converters, 3-phase drives |
| Gradiometers and array null steering | S5 and LA35: put victims on null planes |
| Commensurability (crystallography) | FE42 weave angles |

### 7. What each conductor is doing, in symmetry terms

Per band, each body gets a symmetry passport ([lens-cd](lens-cd.md)):
1. **Mode content:** imbalance h(z); where h changes, it sources common mode.
2. **Image:** which reference mirrors it, and whether that holds (ℓ ≫ ℓ_d, away from edges, below cavity modes). Where the image breaks, it radiates.
3. **Multipole with image:** I·A·h for a flat loop, ∫V dA for a node.
4. **Lead field:** what it hears, which equals what it radiates.
5. **Group:** its pair, bridge or paralleled set, and the antisymmetric residual.
6. **Gauge:** its voltage means something only with the loop that measures it.

### 8. Critique of round 1's synthesis

1. **"Adjoint/reciprocity" is filed as one object** ([cross-workstream-synthesis](cross-workstream-synthesis.md) §1). S1 needs adjoints, periodic ones for converters and ADCs. S3 needs field reciprocity, which is safe on boards. Both fail for rectifying and threshold victims.
2. **Node/loop duality is presented as symmetric** (README principle 2, LA4). Principle 3 ("height is the strongest knob") and "distance is the weak lever once a solid plane is close" hold for loops only. Over a plane, magnetic coupling falls 30 dB per doubling of distance; what remains is electric coupling, which prepreg thickness does not touch.
3. **S5 ("cancel, then pack tighter") overstates cancellation** [C]. With 3 mm halves and a 10 mm halo, the radius shrinks only 2% over a plane and 16% in free space. Cancellation is a far-field and null-plane operator, capped near 20·log ε by the imbalance ε.
4. **Bal and Vcm are one quantity**, which settles the question in [rule-basis-set](rule-basis-set.md). Conversion happens at changes of h, so FE35's "accumulate imbalance along the route" is wrong.
5. **"One regime boundary f_x" is one length, and gap 2 is narrower than stated.** At f_sw the plane already mirrors the hot loop at board scale; what stays open is the return width at the scale of h, which sets L (L′ 0.39 → 0.068 nH/mm from 1 kHz to 1 MHz, [power-copper](power-copper.md)). Ripple does not wander under a distant ADC; DC and low frequencies do.
6. **LA21's partial-element accounting fixes a gauge.** Ledger "spenders" should come from sensitivities of loop or port quantities, or be labelled conventions.
7. **The nine objects omit symmetry groups and the duality map.** Add both: the first as a tenth object, the second as a rule generator.
8. **Updates.** "Adjoints miss cuts", "the edge factor of about 2 is empirical" and "slits 12–19% off" are now exact (D3). The openEMS slot check should target short narrow slots, where Babinet and the slotline formula agree and PEEC differs. The immunity gap is half closed: reciprocity already gives the linear coupling.

## Recommendations for our system

1. Add **symmetry declarations**, permutations on the physics graph, with residual critics. Merge Bal into Vcm as "mode conversion" with a level index (SY13–SY15).
2. Split the solver API into `adjoint(J)` (circuit, LTI or periodic) and `lead_field(port)` (field). Flag rectifying and threshold victims (SY1–SY4).
3. Replace Δψ² with the image-exact law and the cross-objective crack price, and add the needle price (SY6–SY9).
4. Budget dv/dt nodes in ∫V dA with h-independent coupling. Treat prepreg as a loop lever only. Bury victims rather than guard them (SY10–SY12).
5. Build one image-lattice kernel library, and choose solvers per structure by ℓ_d (SY24, SY25).
6. Every voltage budget names its loop, and spend is attributed by sensitivity (SY22, SY23).

## Conflicts and open questions

- D1 and D2 are 2-D quasi-static; the 3-D formulas assume r ≫ sizes and an unbroken plane.
- In microstrip h_C ≠ h_L: neighbour asymmetries give h_L 3–15× larger [C]. The termination decides which applies; Scd21 needs full-wave checks.
- The weave result is a toy, and the Dk added where bundles cross is unknown.
- No open SPICE offers a periodic adjoint [I]; build it on Xyce's harmonic balance.
- Whether one-sided copper skews leg widths through etch loading is untested; at 10 µm it would dominate.

## Sources

- Round-1 docs and the two scripts above [C]; notes: [rules_highspeed_emi.md § 7, 9](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md).
- Malmivuo & Plonsey, *Bioelectromagnetism*, ch. 11: https://www.bem.fi/book/11/11.htm [P]. André, "Grounds and Returns", In Compliance, April 2025 [P].
- Su & Hubing, IEEE T-EMC 53(1):150, 2011; Watanabe et al., IEICE Trans. Commun. E87-B(8):2327 [S].
- Booker, J. IEE 93(IIIA), 1946; Bethe, Phys. Rev. 66:163, 1944; Keller, J. Math. Phys. 5:548, 1964; Jackson, *Classical Electrodynamics* §3.4; Telichevesky, Kundert, White, DAC 1996; Curie, J. Phys. 3, 1894 [S].

See also: [README](README.md) · [cross-workstream-synthesis](cross-workstream-synthesis.md) · [research-gaps](research-gaps.md) · [lens-vp](lens-vp.md) · [lens-ct](lens-ct.md) · [lens-ls](lens-ls.md) · [lens-th](lens-th.md) · [lens-in](lens-in.md) · [lens-cd](lens-cd.md)
