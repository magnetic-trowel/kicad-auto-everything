# Real-board conductor passports: what the copper of a BLDC power board is doing

**TL;DR**
- **Passports run on a real board, exactly and fast.** The test board is the open BLDCM-Power: 32 mm round, 4 layers, a TMC6300 three-phase bridge with in-line 50 mΩ shunts read by INA240 amplifiers. Its rasterized DC model (111k nodes) solves 7 sources and 6 quiet ports in 0.5 s, and exact removal costs match brute force to 3.5×10⁻¹¹. The whole script, HF included, takes 48 s [C]. Lens CD's sheet law holds here: exact removal prices are 2.08× the first-order prices (median over 400 loaded faces).
- **The conductor view finds four problems that the netlist and DRC cannot see:**
  - The bridge's return pins reach ground only through 0.2 mm tracks and an exposed pad with no vias. Ground copper inside the chip's footprint holds 20% of the supply-path resistance.
  - The 10 µF capacitor's ground is an island. Its three vias carry under 5% of any DC current but 86% of the commutation current, which returns 10 mm away, under the 3.3 V plane.
  - The 3.3 V plane, a logic rail by netlist, carries the hot loop's largest HF current (its image). Without the plane, the loop inductance would be 2.8× higher.
  - Half the daisy-chain ground current at one connector squeezes through one 0.2 mm via.
- **The quiet nodes are well protected, and the passport says why.**
  - Inner-edge Kelvin taps add 0.01% to the shunt reading. Outer-edge taps would add 0.9% and drift +34 ppm/K.
  - Supply current moves the amplifiers' ground by at most 0.29 mV per A, 0.03% of the 1 V/A signal.
- **Counterfactuals rank fixes exactly:**
  - one via in the exposed pad: −15% loop inductance (best of 511 sites; the median site gives −0.4%);
  - swapping the inner planes: −19%;
  - a certified convex floor shows 24–25% of the phase pours' resistance is avoidable at equal area.
- **Absolute HF numbers depend on the model:** 7.8–9.1 nH across settings, and the local model reads narrow tracks high. Shares, rankings and DC-versus-HF job flips are robust. Calibrate before budgets use the nanohenries.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py). Method: [lens-cd](lens-cd.md), [lens-vp](lens-vp.md), [lens-ct](lens-ct.md).

## Key facts

### 1. The board, read like a reviewer

**Source:** BLDCM-Power from [brenocq/bldc-motor](https://github.com/brenocq/bldc-motor), commit b74fb1d, MIT licence; bench manifest id `pcbcorpus-brenocq-bldc-motor-bldcm-power`. No geometry from the board is reproduced here.

The script's reading of the board [C]:

| Inference | Evidence |
|---|---|
| GND (1,583 mm²), VIN, and a 3.3 V plane (696 mm² on In1) | net names, copper area |
| Stackup: F.Cu 35 µm / 0.21 mm / In1 3.3 V, 15 µm / 1.065 mm / In2 GND, 15 µm / 0.21 mm / B.Cu 35 µm | the file's stackup |
| U3 (TMC6300) is the switching cell. Its pins 16 and 20 are the bridge return | U3 has pads on VIN, GND and all three shunt nets. Pins 16 and 20 are GND pins beside the supply pin, which the datasheet calls bridge "foot points" [P] |
| R2, R4 and R12 are 50 mΩ in-line phase shunts, read by INA240s (U1, U4, U6) powered from 3.3 V | value "50m"; amplifier pads on both shunt nets and on 3.3V |
| J2 is the motor connector. J3 and J4 both carry VIN and GND, so a daisy-chain bus crosses the board. J1 is the host connector (27 nets, including the sense outputs) | adjacency |
| C9 10 µF (2.8 mm from the supply pin), C10 100 nF (3.2 mm) and C11 1 µF (8.6 mm) decouple VIN | capacitors between VIN and GND |
| The 16 mm × 1 mm bottom-layer VIN bus is tinned | KiCad 9 `layers "B.Cu" "B.Mask"` |
| The zone fills are current | 13 saved fills, none overlapping other-net copper |

### 2. Model and checks [C]

| Part | Method | Size, time |
|---|---|---|
| DC network | Per-net grids: 0.05 mm for VIN and the phases, 0.2 mm for the planes. Cell and face coverage are supersampled. Via barrels are ρl/(π(d+t)t), with t = 20 µm plating. Terminal pads are equipotential. Shunt pads stay bare copper, with the resistive element along their facing edges | 111k nodes, 215k branches; LU 0.4 s |
| Passports | Shares, Tellegen attribution, exact rank-1 and Woodbury removal, leverage (exact for 889 pieces, a 48-solve sketch for all), dead copper, common impedance | 7 s |
| HF hot loop | Stack-local model of a 21 × 23 mm window (described below) | 73k cells, 2.9 s |
| Floor | Beckmann R ≥ R_s·d²/A. Frank–Wolfe on the relaxed density of the three phase pours (per-cell sum ≤ 1, same total area) | 4.3k cells, 8 s |

**The HF model.** It generalizes "μ0·h·squares over the nearest plane" to a whole stack.
- Every copper island in the window is a sheet conductor, whatever its net.
- The energy per face is (μ0/2)·Σ_g h_g·H_g². Here h_g is the thickness of gap g, and H_g is the sheet current above gap g minus half the net stack current.
- A plane of any net therefore images the currents on both sides of it. A pure plate-pair current leaves no field outside the stack.
- The parts' current paths lie on a layer 0.3 mm above the parts: the chip's supply and return leads, and each capacitor body.
- An EMF across the chip's supply lead drives the loop.

This is the inductive limit. It holds well above f_x = R_s/(2π·μ0·h), which is about 0.7 MHz for the 15 µm In1 at 0.21 mm ([lens-vp](lens-vp.md) D5). It therefore describes the edge harmonics, not the PWM fundamental.

**Checks:**
- Rank-1 removal against a brute-force re-solve: 3.5×10⁻¹¹.
- Woodbury via removal and Thevenin via addition against brute force: equal to the printed digit.
- Sketch leverage sum: 110,875 against n − c = 110,879 (Foster).
- Strip over a plane against μ0hl/w: 0.7%.
- Via pair in a plate pair against a plain sheet solve: 5×10⁻⁵.
- DC ground grid refined from 0.2 to 0.1 mm: R moves under 1%.
- HF grid 0.15 → 0.2 mm: L moves 7%. Outer-field thickness 10 → 1 mm: L moves 14%.

### 3. Fifteen findings [C unless tagged]

"Per A" means per ampere of that source. Findings are at DC unless marked.

**Supply and bridge return**

1. **The bridge return is a neck of 0.2 mm tracks.** The low-side current leaves the TMC6300 at two return pins. Each pin joins the 1.8 mm exposed pad by one 0.2 mm track. The pad has no vias. Its copper joins the ground pour only through a 0.6 mm corridor between two ground pins on its far side, and the nearest ground vias are 3 mm beyond that.
   - Ground copper inside the footprint holds 1.76 mΩ, 20% of the 8.8 mΩ supply path.
   - The return tracks run at 73 A/mm² per A. Cutting either one adds 6.3–6.8% to the supply-path R.
   - The datasheet asks for "as many as possible vias" in the exposed pad and for "solid, thermally conducting vias between the die attach pad and the ground plane" [P].
   - The pad is also the heat path: about 1 W at 2 A, and R_θJA = 40 K/W only on a "thermally optimized layout" [P]. The electrical neck is probably a thermal neck too [I].
2. **The pins are the hottest copper.**
   - The supply pin runs at 118 A/mm² per A.
   - The V-phase pin runs at 181 A/mm² per A, and the 1 mm tile around it holds 20% of that phase's copper loss.
   - At the 2 A peak rating [P] these become 240–360 A/mm², over sub-millimetre lengths.
3. **Four 0.2 mm vias carry the whole motor supply** from the bottom bus to the top layer: 21–29% each, leverage 0.55–0.90. Removing one adds 2.0–2.8% to R. At HF they carry only 2.5–10% of the commutation current, because the capacitors supply it.
4. **The tinned bus is the pass-through conductor.** Current that enters at one supply connector and leaves at the other sees 7.8 mΩ, 84% of it in the bottom-layer bus (modelled as bare copper). The designer's mask opening matches this conductor's job.
5. **The daisy-chain ground at J3 hangs on two vias.**
   - One 0.2 mm via beside J3's ground pad carries 52% of that connector's ground current (ρ 0.87; removing it adds 6.0%). A second carries 36%.
   - The pad sits in a bottom-layer pocket fenced by the CAN pair, the phase-sense traces and the VIN bus.
   - At 2 A of bus current, the first via carries 1 A.

**Hot loop (inductive limit)**

6. **The capacitor ground is an island, so the commutation loop dives.**
   - C9 and C10 share a 3.6 mm² top-layer ground island with three vias. The vias carry 0.3–4.4% of the DC currents, but 39%, 32% and 15% of the commutation current.
   - The return runs 10 mm through the inner ground plane, under the 3.3 V plane, to three vias north of the chip. Those vias carry 24–29% each at both DC and HF.
   - The loop inductance is 9.1 nH (7.8–9.1 across settings), 25–31% of it in the parts' current paths.
   - The datasheet asks for >10 µF "near pin with shortest possible loop to GND pad" [P]. The netlist cannot tell this loop from a good one.
7. **The 3.3 V plane is the hot loop's image conductor.** It carries 30 A·mm of current-length per A, more than the ground plane (18) or the top ground copper (16). All of it is induced: the plane has no transport job in this loop. Removing it from the window raises L from 9.1 to 25.4 nH (+178%; +126% to +182% across settings). This is lens CD's incidental shield (CD20) on a real board.
8. **Fixes are ranked exactly.**
   - One added ground via in the exposed pad, at the edge nearest the bridge pins, cuts L by 15%. It is the best of 511 legal sites, the median site gives −0.4%, and brute force agrees.
   - Swapping the inner planes, so that ground sits under the power stage, cuts L by 19%.
   - Each capacitor-island via is worth 40–210 pH.
9. **Capacitor shares follow loop inductance, not capacitance.** C9 takes 49% of the edge current, C10 38% and C11 13%. C11's own loop is 16.6 nH, against 10.3–11.0 nH for C9 or C10 alone.
10. **The switch nodes talk mainly to the 3.3 V plane.**
    - The six phase nets in the window have 13.4 pF of parallel-plate capacitance, 78% of it to the 3.3 V plane (50–90% per net).
    - Each phase edge pushes 3.0–3.8 mA per V/ns into the plane that powers the sense amplifiers: about 10 mA per V/ns if all three phases switch together.
    - The datasheet warns about dV/dt coupling into "high resistive signals" [P]. A low-impedance rail is a different victim; only a circuit model can say whether this current matters [I].

**Phase paths, sensing and floors**

11. **The Kelvin taps work, and the counterfactual says by how much.**
    - The 0.1 mm taps leave the shunt pads' inner edges. Copper changes the 50 mΩ reading by −0.01% to +0.01%.
    - Taps at the outer edges would read +0.9% and drift +34 ppm/K.
    - The per-tile Tellegen terms cancel (χ = 0.02–0.03), so blame must be assigned by counterfactual, as lens CD predicts.
12. **Ground offsets are small because the planes work.**
    - Supply and bus currents move the amplifiers' ground against the host's by at most 0.29 mΩ per A. That is 0.03% of the 1 V/A signal (20 V/V on 50 mΩ [S]).
    - The host's own 3.3 V current moves it by 1.3–1.4 mΩ per A. Most of this is in two ground vias near the host connector, which carry 36% each of that return (ρ 0.63–0.92; removing one adds 9%).
13. **Two phases detour around the decoupling capacitor.**
    - Phase copper is 7.5, 6.9 and 4.0 mΩ (V, U, W), beside the 50 mΩ shunt.
    - U and V wrap round C9, and 48–61% of their copper loss is in the pour body.
    - At the same total area, the joint convex floor is ≥10.92 mΩ, against 14.47 mΩ for the actual pours in the same relaxed model (gap 0.2%). So 24–25% is avoidable, by reshaping V and U (−1.5 and −1.9 mΩ) and moving 1.5 mm² to U.
    - The closed-form Beckmann floor (4.8 mΩ) is far looser.
14. **Leverage is a sheet's ½ almost everywhere.** The median ρ is 0.49–0.54 on every net, and only 0.7–3.9% of faces exceed 0.9. Exact/first-order prices have a median of 2.08 (10–90%: 1.93–2.71).
15. **There is dead and idle copper.**
    - 11% of the top ground pour and 8% of the bottom pour carry under 0.1% of every modelled current.
    - Four connector mounting pads (27 mm²) float.
    - The top VIN island is 43% idle at DC, yet it is the hot loop's forward path. This is a job flip, like the capacitor vias.

### 4. Passports of selected pieces [C]

| Piece | DC | HF (commutation) | Job |
|---|---|---|---|
| Capacitor-island via (best of 3) | 0.4% of the J4 feed, 3% of the J3 feed | 39%; removing it adds 210 pH | carries the HF return only: protect it |
| Via north of the chip (1 of 3) | 29% of the supply, ρ 0.61, removal +2.8% R | 29%, +137 pH | carries both |
| VIN via (1 of 4) | 28% of the supply, ρ 0.90, removal +2.8% R | 10%, +12 pH | carries the DC feed |
| Via at J3's ground pad | 52% of J3's current, ρ 0.87, removal +6.0% R | not in the loop | near-series path |
| Return tracks (0.2 mm, 2) | together the whole bridge return; 73 A/mm² per A; removing one adds 6.3–6.8% R | in the loop | neck |
| 3.3 V plane (In1) | the 3.3 V rail only (32% of its loss) | 30 A·mm per A; removing it adds 178% to L | images the hot loop |

### 5. What a netlist-only view misses

| Netlist says | The conductors say |
|---|---|
| C9 decouples the supply to GND | its HF return dives under a foreign plane, to vias 10 mm away |
| U3's ground pins and pad are on GND | the motor return crosses 0.2 mm tracks and a pad with no vias |
| 3.3 V plane: a logic rail | the largest HF current in the hot loop, and the switch nodes' main charge destination |
| J3 GND is connected | half its current goes through one via behind a fence of CAN and sense traces |
| U, V and W are equivalent | U and V cost 1.7–1.9× W in copper; the joint floor would cut V by 23% and U by 33% |
| INA240 across the shunt | inner-edge taps give 0.01%, outer-edge taps would give 0.9% |
| In1 and In2 are "planes" | their order is worth 19% of the loop inductance |

### 6. Calibration: the same HF model on three boards [C]

| Board (licence) | Switching cell | Loop L | Energy in the deepest gap | Swap inner planes |
|---|---|---|---|---|
| [oasis](https://github.com/justbuchanan/oasis) (Apache-2.0) | LMR54406 buck on B.Cu; its own +18 V plane 0.1 mm away | 2.4 nH | 8% | −22% |
| BLDCM-Power (MIT) | TMC6300 bridge on F.Cu; 3.3 V plane 0.21 mm away | 9.1 nH | 18% | −19% |
| [AFTONSPARV](https://github.com/caffeinated-labs/Caffeinated-AFTONSPARV) (CERN-OHL-S-2.0) | SY8201 buck on B.Cu; 3.3 V plane 0.21 mm away | 12.7 nH | 56% | −62% |

The model separates the tight cell from the two loose ones. In both loose ones, a plane that is not in the loop lies between the cell and its ground plane.

## Recommendations for our system

1. **Make the passport the reviewer-facing output** ([lens-cd](lens-cd.md) CD1, CD13, CD21).
   - For each via, pin, track and pour tile, report its DC and HF shares, its exact removal or addition value, its leverage and its job verb (CD8).
   - Flag job flips (idle at DC, load-bearing at HF) and induced-current conductors (CD20). Protect both from trimming.
2. **Treat pin functions as physics inputs.** Using the bridge-return pins rather than "all GND pins" as the DC return raised the supply-path R by 25%. The role model needs the datasheet's pin semantics (foot points, exposed pad), not only net names.
3. **Add four critics, each an exact or topological check:**
   - a power IC's exposed pad with no vias, or one that reaches ground only through tracks no wider than its pins;
   - a decoupling loop whose capacitor ground and device return reach the ground plane through different via groups;
   - a power-connector pad with more than half its current in one via (ρ > 0.8);
   - a plane that is not in the loop lying between a switching cell and its ground plane, scored by the plane-swap counterfactual.
4. **Propose fixes from exact counterfactuals:** Thevenin via sites (CD3), plane order, tap position, and Woodbury batch removals (CD25). Each costs one solve per candidate.
5. **Calibrate the stack-local HF model** against FastHenry or openEMS on the three loops in §6, and add a fringing correction, before budgets use its nanohenries. Until then, use shares, rankings and relative changes.

## Conflicts and open questions

**DC model limits:**
- bare copper at 20 °C;
- 20 µm via plating assumed;
- no solder on the tinned bus, so its R is overestimated;
- no package or lead-frame resistance;
- shunt terminations ignored, which is the worst case for the Kelvin counterfactual.

**HF model limits:**
- **Local.** There is no lateral fringing, so narrow features read high: ×1.5 at w/h = 5 and about ×3 at w/h ≈ 1. The worst case is the 0.2 mm tracks over 0.21 mm.
- **Lossless.** There is no plane damping.
- **Crude parts and outer field.** The part current paths (25–31% of L) and the field outside the stack are rough.
- **One window.**
- **Size of the error.** Applying the strip error to the top-gap energy alone gives about 7.8 nH; applying it to everything gives about 6 nH [I].

**Not modelled:**
- temperature;
- the transition band near f_x (CD19);
- the PWM fundamental;
- full-wave effects.

Role inference is heuristic: it needed one fix to find the converter on oasis.

**Robust versus model-bound.** Every DC number, every share and ranking, and the job flips are robust. Absolute nanohenries are not.

**Corrections for other documents:**
- **[physics-critics](physics-critics.md):** its BLDCM-Power row lists signal reference changes and thin VBUS traces. It misses this board's power-stage necks, which are larger issues.
- **[lens-cd](lens-cd.md):** add that the sheet ×2 law (2.08) and the χ warning (0.02) hold on a real board. CD21's DC-versus-HF contrast for vias is stronger here: 0.4% against 39%.
- **Round-3 point 3 ("the world matters"):** include pass-through currents. The daisy-chain bus is off-board current in on-board copper, and it adds up to 0.13 mΩ per A to the amplifier ground offsets.

**Open questions:**
- Is In1's eddy current a useful damping channel for ringing? Its R_s is 1.1 mΩ/sq.
- Would PEEC or full-wave tools agree on the ranking of via sites?

## Sources

- Trinamic, *TMC6300 Datasheet* rev. 1.01 (2019): pin table, thermal characteristics, layout §8.1–8.3 ([PDF](https://shop.mev-elektronik.com/wp-content/uploads/TMC6300_datasheet.pdf)) [P]. The current ADI revision (1.08) could not be reached.
- Board sources and licences: `bench/manifests/candidates.jsonl`; the hashes match the files used [P].
- Microstrip inductance with fringing (Wheeler), as in [pc_refplane.py](../../../tools/research/physics/pc_refplane.py) [S].
- Peaceman's equivalent well radius 0.198·Δx (1978), as in [pw_sheet.py](../../../tools/research/physics/pw_sheet.py) [S].
- Spielman and Srivastava, leverage sketch, [arXiv:0803.0929](https://arxiv.org/abs/0803.0929) [S].
- Jaggi, "Revisiting Frank–Wolfe", ICML 2013 (duality-gap certificate) [S].
- Scripts: [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py) (this doc), [cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py), [vp_floors.py](../../../tools/research/physics/vp_floors.py).

See also: [lens-cd](lens-cd.md) · [lens-vp](lens-vp.md) · [lens-ct](lens-ct.md) · [physics-critics](physics-critics.md) · [pdn-and-commutation](pdn-and-commutation.md) · [power-copper](power-copper.md) · [research-gaps](research-gaps.md)
