# Real-board conductor passports: what the copper of a BLDC power board is doing

Scope: exact DC and HF conductor passports on one real open board (BLDCM-Power), with findings no netlist or DRC shows, ranked fixes, and the same HF model on two more boards. Not here: passport theory -> [lens-cd](lens-cd.md); floors -> [lens-vp](lens-vp.md); the core design -> [physics-core-v2](physics-core-v2.md).
Keys: real-board passports, BLDCM-Power, TMC6300, INA240, exposed pad without vias, capacitor ground island, 3.3 V plane image current, plane swap, via site ranking, Kelvin taps, relaxed floor, Beckmann bound, leverage ρ, Tellegen attribution, χ, Woodbury, Thevenin, Foster sum, oasis, AFTONSPARV, rb_board_passports.py

**Results** [C]:
- Exact passports run on a real board in under a minute: BLDCM-Power (32 mm round, 4 layers, TMC6300 three-phase bridge, in-line 50 mΩ shunts, INA240 amplifiers); 111k-node DC model solves 7 sources and 6 quiet ports in 0.5 s; full script 48 s; removal costs exact (§2).
- Four facts no netlist or DRC shows (§3): the bridge return reaches ground only through thin tracks and a via-less exposed pad; the 10 µF cap's ground island's vias carry < 5% of any DC current but 86% of commutation current; the 3.3 V plane carries the hot loop's largest HF current; one 0.2 mm via carries most of a supply connector's ground current.
- Current sensing is sound: copper barely moves the shunt readings or the amplifier ground (§3).
- Exact counterfactuals rank fixes (§3): one exposed-pad via, an inner-plane swap, pour reshaping against a certified floor.
- DC numbers exact for the raster; HF shares and rankings stable across model settings; HF loop L uncalibrated.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py).

## 1. The board and its inferred roles

The board is BLDCM-Power from [brenocq/bldc-motor](https://github.com/brenocq/bldc-motor) (commit b74fb1d, MIT; manifest id `pcbcorpus-brenocq-bldc-motor-bldcm-power`). No board geometry is reproduced here. Roles are inferred from names, values, footprints and adjacency [C].

| Inference | Evidence |
|---|---|
| Nets: GND (1,583 mm²), VIN, and a 3.3 V plane (696 mm² on In1) | net names, copper area |
| Stackup: F.Cu 35 µm / 0.21 mm / In1 3.3 V, 15 µm / 1.065 mm / In2 GND, 15 µm / 0.21 mm / B.Cu 35 µm | file stackup |
| U3 (TMC6300) is the switching cell; pins 16 and 20 are its bridge return | pads on VIN, GND and all three shunt nets; the datasheet's pin table names 16 and 20 as bridge foot points [P] |
| R2, R4, R12: 50 mΩ in-line phase shunts, read by INA240s (U1, U4, U6) on 3.3 V | value "50m"; amplifier pads on both shunt nets |
| J2 is the motor connector. J3 and J4 both carry VIN and GND, so a daisy-chain bus crosses the board. J1 is the host connector (27 nets) | adjacency |
| C9 10 µF (2.8 mm from the supply pin), C10 100 nF (3.2 mm) and C11 1 µF (8.6 mm) decouple VIN | capacitors between VIN and GND |
| The 16 mm × 1 mm bottom-layer VIN bus is tinned | KiCad 9 `layers "B.Cu" "B.Mask"` |
| Fills are current | 13 saved fills; none overlaps other-net copper |

## 2. Definitions, formulas and checks

**Passport quantities** (definitions and derivations: [lens-cd](lens-cd.md)): unit source p (1 A between its terminals) → branch current i_p(b), z_b = 1/g_b. Attribution (Tellegen) Z_qp = Σ_b a_b, a_b = i_p(b)·i_q(b)·z_b; cancellation index χ = |Σ a_b| / Σ |a_b|. Leverage ρ_b = g_b·R_eff(b), Foster Σ ρ_b = n − c (n nodes, c components). Exact removal ΔZ_qp = a_b/(1 − ρ_b) (first order low by 1/(1 − ρ_b) = 2 on an infinite uniform square grid, ρ = ½); sets by Woodbury. Exact addition of z between two nodes: Δ(self-impedance) = −Δφ²/(z + Z_th), Δφ = open-circuit potential difference, Z_th = Thevenin impedance.

**HF loop inductance.**
- Drive: an EMF across the chip's supply lead drives loop current I; W = ½LI² defines L.
- Conductors: every copper island in the window is a sheet conductor, whatever its net; part current paths (chip leads, cap bodies) on a layer 0.3 mm above the parts.
- Energy per unit face area (μ0/2)·Σ_g h_g·H_g², h_g = thickness of gap g, H_g = summed sheet current of layers above g minus half the net stack current; so a plane of any net images currents on both sides.
- Validity: inductive limit, well above f_x = R_s/(2π·μ0·h) ([lens-vp](lens-vp.md) D5); In1 (R_s = 1.13 mΩ/sq, h = 0.21 mm): f_x ≈ 0.7 MHz, so it covers edge harmonics, not the PWM fundamental.

**Floors** ([lens-vp](lens-vp.md)).
- Beckmann bound: pour of sheet resistance R_s, area A, terminals d apart: each unit of current travels ≥ d, so (Cauchy–Schwarz) R ≥ R_s·d²/A.
- Relaxed floor: per-net copper density per cell, per-cell sum ≤ 1, total area fixed; R convex in the densities (Thomson), so the Frank–Wolfe duality gap certifies a lower bound.

**Discretization [C]:** per-net grid, 0.05 mm for VIN and phases, 0.2 mm for planes, supersampled coverage; via barrel (length l, drill d, plating t = 20 µm) R = ρ_Cu·l/(π(d+t)t); terminal pads equipotential; shunt pads bare copper with the resistive element along their facing edges.

| Stage | Size | Time |
|---|---|---|
| DC network | 111k nodes, 215k branches | LU 0.4 s |
| Passports | exact leverage for 889 pieces; a 48-solve sketch for all | 7 s |
| HF window, 21 × 23 mm | 73k cells | 2.9 s |
| Floor | 4.3k cells | 8 s |

**Checks [C]:** exactness: rank-1 removal vs brute force 3.5×10⁻¹¹; Woodbury and Thevenin via edits agree to the printed digit; Foster sum 110,875 vs n − c = 110,879. Fields: strip over a plane vs μ0hl/w 0.7%; via pair in a plate pair vs sheet solve 5×10⁻⁵. Convergence: DC ground grid 0.1 vs 0.2 mm moves R < 1%; HF grid 0.2 vs 0.15 mm moves L 7%; 1 mm vs 10 mm outer field moves L 14%.

## 3. Findings [C unless tagged]

"Per A" means per ampere of that source. DC unless marked.

**Supply and bridge return**

1. **The bridge return is a neck of 0.2 mm tracks.**
   - Each of the two return pins joins the 1.8 mm exposed pad by one 0.2 mm track. The pad has no vias; its copper reaches the ground pour only through a 0.6 mm corridor between two ground pins on the far side, 3 mm from the nearest ground vias.
   - Ground copper inside the footprint holds 1.76 mΩ, 20% of the 8.8 mΩ supply path.
   - The return tracks run at 73 A/mm² per A. Cutting either one adds 6.3–6.8% to R.
   - The datasheet asks for "as many as possible vias" in the pad, and for "solid, thermally conducting vias between the die attach pad and the ground plane" [P].
2. **The pins are the hottest copper.** The supply pin runs at 118 A/mm² per A. The V-phase pin runs at 181 A/mm² per A, and its 1 mm tile holds 20% of that phase's copper loss. At the 2 A peak rating [P] these become 240–360 A/mm².
3. **Four 0.2 mm vias carry the whole motor supply** up from the bottom bus. Each carries 21–29% (ρ 0.55–0.90), and removing one adds 2.0–2.8% to R. At HF they carry 2.5–10%, because the capacitors supply the rest.
4. **The tinned bus carries the pass-through current.** Connector to connector it measures 7.8 mΩ, 84% of it in the bottom-layer bus.
5. **The daisy-chain ground at J3 rests on two vias.**
   - One 0.2 mm via beside J3's ground pad carries 52% of that connector's ground current (ρ 0.87; removal +6.0%). A second carries 36%.
   - The pad sits in a bottom-layer pocket bounded by the CAN pair, the phase-sense traces and the VIN bus.

**Hot loop (inductive limit)**

6. **The capacitor ground is an island, so the commutation loop dives.**
   - C9 and C10 share a 3.6 mm² top-layer ground island. Its three vias carry under 5% of any DC current (0.3–0.6% of the J4 feed), but 39%, 32% and 15% of the commutation current.
   - The return runs 10 mm through the inner ground plane, under the 3.3 V plane, to three vias north of the chip. Each of those carries 24–29% at both DC and HF.
   - L = 9.1 nH, and 25–31% of it lies in the part current paths.
   - The datasheet asks for >10 µF "near pin with shortest possible loop to GND pad" [P].
7. **The 3.3 V plane is the hot loop's image conductor.** It carries 30 A·mm of current-length per A; the ground plane carries 18 and the top ground copper 16. All of its current is induced, since it has no transport role in this loop: it is an incidental shield in the sense of [lens-cd](lens-cd.md) CD20. Removing it from the window raises L from 9.1 to 25.4 nH (+178%; +126% to +182% across settings).
8. **The fixes rank exactly.**
   - One ground via in the exposed pad, at the edge nearest the bridge pins, cuts L by 15%. It is the best of 511 legal sites (median −0.4%), and brute force agrees.
   - Swapping the inner planes cuts L by 19%.
   - Each capacitor-island via is worth 40–210 pH.
9. **Capacitor shares follow loop inductance, not capacitance.** The edge current splits C9 49%, C10 38%, C11 13%. C11's own loop is 16.6 nH, against 10.3–11.0 nH for C9 or C10 alone.
10. **The switch nodes couple mainly to the 3.3 V plane.**
    - The six phase nets in the window have 13.4 pF of parallel-plate capacitance, 78% of it to that plane (50–90% per net).
    - Each phase edge drives 3.0–3.8 mA per V/ns into the amplifiers' supply plane, or about 10 mA per V/ns if all three phases switch together.

**Phase paths, sensing and floors**

11. **The Kelvin taps are placed correctly.** The 0.1 mm taps leave the shunt pads' inner edges, so copper changes the 50 mΩ reading by ±0.01%; outer-edge taps would read +0.9% and drift +34 ppm/K. The per-tile Tellegen terms cancel (χ = 0.02–0.03), so only exact removal can assign the error.
12. **Ground offsets are small.**
    - Supply and bus currents move the amplifiers' ground against the host's by ≤0.29 mΩ per A: 0.03% of the 1 V/A signal (20 V/V on 50 mΩ [S]).
    - The host's own 3.3 V current moves it by 1.3–1.4 mΩ per A, mostly through two ground vias near the host connector (36% of that return each; removal +9%).
13. **Two phases detour around the decoupling capacitor.**
    - Phase copper is 7.5, 6.9 and 4.0 mΩ (V, U, W), beside the 50 mΩ shunt. U and V wrap round C9, and 48–61% of their copper loss lies in the pour body.
    - At equal total area the relaxed floor is ≥10.92 mΩ, against 14.47 mΩ for the actual pours in the same model (duality gap 0.2%; Beckmann bound 4.8 mΩ). At most 24–25% is avoidable, by reshaping V (−1.5 mΩ) and U (−1.9 mΩ) and moving 1.5 mm² to U.
    - The relaxation allows fractional copper, ignores clearances and lets the nets trade area, so this bounds a real redesign from above.
14. **Leverage is near ½ on every net.** The median ρ is 0.49–0.54 (sketch), and 0.7–3.9% of faces exceed 0.9. On the 400 most loaded faces, 1/(1 − ρ) has a median of 2.08 (10–90%: 1.93–2.71).
15. **Some copper is dead or idle.** 11% of the top ground pour and 8% of the bottom pour carry under 0.1% of every modelled current, and four connector mounting pads (27 mm²) float. The top VIN island is 43% idle at DC but is the hot loop's forward path at HF.

## 4. What a netlist-only view misses

| Netlist says | The conductors say |
|---|---|
| C9 decouples the supply to GND | its HF return dives under a foreign plane to vias 10 mm away |
| U3's ground pins and pad are on GND | the motor return crosses 0.2 mm tracks and a pad without vias |
| 3.3 V plane: a logic rail | it carries the hot loop's largest HF current and is the switch nodes' main charge destination |
| U, V and W are equivalent | U and V cost 1.7–1.9× W; the relaxed floor cuts V by 23% and U by 33% |
| A via is a via | a capacitor-island via carries 0.4% of the J4 DC feed but 39% of the HF loop |

## 5. The same HF model on three boards [C]

| Board (licence) | Switching cell | Loop L | Energy in deepest gap | Swap inner planes |
|---|---|---|---|---|
| [oasis](https://github.com/justbuchanan/oasis) (Apache-2.0) | LMR54406 buck on B.Cu; its own +18 V plane 0.1 mm away | 2.4 nH | 8% | −22% |
| BLDCM-Power (MIT) | TMC6300 on F.Cu; 3.3 V plane 0.21 mm away | 9.1 nH | 18% | −19% |
| [AFTONSPARV](https://github.com/caffeinated-labs/Caffeinated-AFTONSPARV) (CERN-OHL-S-2.0) | SY8201 buck on B.Cu; 3.3 V plane 0.21 mm away | 12.7 nH | 56% | −62% |

In both higher-inductance cells, a plane that is not part of the loop lies between the cell and its ground plane.

## Consequences for kae

1. Passport = reviewer-facing output ([lens-cd](lens-cd.md) CD1, CD13, CD21): per via, pin, track and pour tile its DC and HF shares, exact removal or addition value, leverage, job verb (CD8). Protect from trimming pieces whose role differs between DC and HF, and induced-current conductors (CD20).
2. Take return terminals from pin semantics: bridge-return pins as return → supply path 8.78 mΩ; all six driver ground pads tied into one terminal → 7.05 mΩ, because the tie shorts the neck of finding 1 [C].
3. Four critics, each exact or topological: power-IC exposed pad without vias, or reaching ground only through tracks no wider than its pins; decoupling loop whose cap ground and device return reach the plane through different via groups; power-connector pad with > half its current in one via (ρ > 0.8); a plane outside the loop between a switching cell and its ground plane, scored by the plane-swap counterfactual.
4. Fixes from exact counterfactuals: Thevenin via sites (CD3), plane order, tap position, Woodbury batch removals (CD25); one solve per candidate.
5. Calibrate the stack-local HF model against FastHenry or openEMS on the three loops of §5, with a fringing correction; until then use shares, rankings and ratios, not nanohenries.

## Open questions

**Model limits** (they bound the confidence of the numbers above):
- **DC:** bare 20 °C copper; 20 µm via plating assumed; no solder on the tinned bus (its R is overestimated); no package resistance; shunt terminations ignored (the worst case for the Kelvin counterfactual).
- **HF:** no lateral fringing, so narrow features read high (×1.52 for a 1 mm strip 0.2 mm over a plane; about ×3 at w/h ≈ 1); lossless; crude part paths (25–31% of L) and outer field; one window.
- **Not modelled:** temperature, the transition band near f_x (CD19), the PWM fundamental, full-wave effects.
- **Role inference** is heuristic (the driver is a part on the shunt nets, else an IC driving an inductor from a decoupled rail) and was checked by hand on three boards.

**Beliefs, with confidence:**
- **The true loop inductance lies in 6–9 nH (moderate).** The model gives 7.8–9.1 nH across settings. Scaling the 44% of L in the top gap by the strip error gives 7.8 nH; scaling all of L gives 6.0 nH [I].
- **The rankings survive calibration (moderately high).** Across the grid and outer-field settings, L moves 7–14%. The capacitor split moves at most 2 points, the best via site stays in the exposed pad (−15% to −16%), and the plane swap stays at −19% to −21% [C].
- **The exposed-pad neck is also a thermal neck (moderate).** The pad is the package's heat path: about 1 W at 2 A, and 40 K/W only on a "thermally optimized layout" [P]. Its copper leaves through one 0.6 mm corridor. No thermal model was run [I].

**Open questions:**
- Does 3–4 mA per V/ns into the amplifiers' supply plane disturb the sensing? This needs a circuit model.
- Is In1's eddy current a useful damping channel for ringing?
- Would PEEC or full-wave tools rank the via sites the same way?

## Sources

- Trinamic, *TMC6300 Datasheet* rev. 1.01 (2019): pin table, thermal data, layout §8.1–8.3 ([PDF](https://shop.mev-elektronik.com/wp-content/uploads/TMC6300_datasheet.pdf)) [P]. Rev. 1.08 (ADI) was not read.
- Board licences: `bench/manifests/candidates.jsonl`, whose hashes match the files used [P].
- Wheeler microstrip inductance with fringing, in [pc_refplane.py](../../../tools/research/physics/pc_refplane.py); Peaceman's equivalent radius 0.198·Δx (1978), in [pw_sheet.py](../../../tools/research/physics/pw_sheet.py) [S].
- Spielman and Srivastava, [arXiv:0803.0929](https://arxiv.org/abs/0803.0929); Jaggi, "Revisiting Frank–Wolfe", ICML 2013 [S].
- Scripts: [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py), [cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py), [vp_floors.py](../../../tools/research/physics/vp_floors.py).

- Related: [lens-ct](lens-ct.md), [physics-critics](physics-critics.md), [validation-program](validation-program.md), [pdn-and-commutation](pdn-and-commutation.md), [power-copper](power-copper.md).
