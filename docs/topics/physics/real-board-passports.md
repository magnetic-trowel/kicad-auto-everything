# Real-board conductor passports: what the copper of a BLDC power board is doing

**TL;DR**
- **The passport method runs on a real board, exactly and in seconds.** On the open BLDCM-Power board (32 mm round, 4 layers, a TMC6300 three-phase bridge with in-line 50 mΩ shunts read by INA240 amplifiers), a rasterized DC model (111k nodes) gives every piece's share of 7 sources and 6 quiet ports in 0.5 s. Its exact removal costs match brute force to 4×10⁻¹¹; the whole script, HF included, runs in about 50 s [C]. Lens CD's sheet law holds: exact removal prices are 2.08× the first-order price (median, 400 loaded pieces).
- **The conductor view finds four things that the netlist and DRC cannot see.**
  - The bridge's return pins reach ground only through 0.2 mm tracks and an exposed pad with no vias: 20% of the supply-path resistance sits inside the chip's footprint.
  - The 10 µF capacitor's ground is an island. Its three vias carry under 1% of the DC current but 86% of the commutation current, which returns 10 mm away, below the 3.3 V plane.
  - The 3.3 V plane, a logic rail by netlist, carries the hot loop's largest HF current (its image). Without it the loop inductance would be 2.8× higher.
  - The daisy-chain ground current at one connector squeezes through two 0.2 mm vias, because the shunt sense traces fence its pad.
- **The quiet nodes are well protected, and the passport says why.** The Kelvin taps leave the shunt pads' inner edges, so copper adds 0.01% to the reading. Outer-edge taps would have added 0.9% and +34 ppm/K. Ground offsets at the amplifiers are ≤0.03% of full scale per amp.
- **Counterfactuals rank fixes exactly:**
  - one via in the exposed pad: −15% of loop inductance (best of 511 legal sites; median site −0.4%);
  - swapping the two inner planes: −19%;
  - the phase pours sit within 24–25% of a certified convex floor at the same copper area.
- **Absolute HF numbers are model-bound** (7.8–9.1 nH across settings; the local model reads narrow tracks high). Shares, rankings and the DC-vs-HF job flips are robust. Calibrate the HF model before budgets use its nanohenries.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py). Method: [lens-cd](lens-cd.md), [lens-vp](lens-vp.md), [lens-ct](lens-ct.md).

## Key facts

### 1. The board, read like a reviewer

BLDCM-Power from [brenocq/bldc-motor](https://github.com/brenocq/bldc-motor) (commit b74fb1d, MIT; bench manifest id `pcbcorpus-brenocq-bldc-motor-bldcm-power`). No geometry from it is reproduced here. The script printed this reading of the board [C]:

| Inference | Evidence |
|---|---|
| GND (1,583 mm²), VIN, and a 3.3 V plane (696 mm² on In1) | net names, copper area |
| Stackup: F.Cu 35 µm, 0.21 mm, In1 (3.3 V, 15 µm), 1.065 mm, In2 (GND, 15 µm), 0.21 mm, B.Cu 35 µm | file stackup |
| U3 (TMC6300) is the switching cell | pads on VIN, GND and all three shunt nets |
| U3 pins 16 and 20 are the bridge return | ground pins next to the VS pin; the datasheet calls them "foot point of bridges", tied to GND here [P] |
| R2, R4, R12: 50 mΩ in-line phase shunts, each read by an INA240 (U1, U4, U6) | value "50m"; amplifier pads on both shunt nets |
| J2 is the motor connector. J3 and J4 both carry VIN and GND, so a daisy-chain bus passes through the board | adjacency |
| J1 is the host connector (27 nets, including the sense outputs) | most distinct nets |
| C9 (10 µF, 2.8 mm from VS), C10 (100 nF), C11 (1 µF, 8.6 mm) decouple VIN | capacitors between VIN and GND |
| The bottom-layer VIN bus (16 mm × 1 mm) is tinned | KiCad 9 `layers "B.Cu" "B.Mask"` |
| Fills are current | all 13 zone layers carry saved fills; none overlap other-net copper |

### 2. Model and checks [C]

| Part | Method | Size, time |
|---|---|---|
| DC network | Each net is rasterized on its own grid: 0.05 mm for VIN and the phases, 0.2 mm for the planes. Cell and face coverage come from supersampling. Via barrels are ρl/(π(d+t)t) with t = 20 µm plating. Terminal pads are equipotential. Shunt pads stay bare copper, with the resistive element along their facing edges. | 111k nodes, 215k branches; LU 0.4 s |
| Passports | Shares, Tellegen attribution, exact rank-1 and Woodbury removal, leverage (exact for 889 pieces, a 48-solve sketch for all), dead copper, common impedance | 4 s |
| HF hot loop | Stack-local model of a 21 × 23 mm window (below) | 73k cells, 1.5 s per solve |
| Floor | Beckmann R ≥ R_s·d²/A per pour; Frank–Wolfe on the relaxed density of the three phase pours (per-cell sum ≤ 1, same total area) | 4.3k cells, 8 s |

**The HF model generalizes "μ0·h·squares over the nearest plane" to a whole stack.** Every copper island in the window is a sheet conductor, whatever its net. The energy per face is (μ0/2)·Σ_g h_g·H_g². Here h_g is the thickness of gap g, and H_g is the sheet current above that gap minus half the net stack current. A plane of any net therefore images what lies above and below it, and a pure plate-pair current leaves no field outside the stack. The parts' current paths lie on a layer 0.3 mm above the parts: the chip's supply lead and return leads, and each capacitor body. An EMF across the chip's supply lead drives the loop, so every loop current is a sheet current. This is the inductive limit, valid above the 15 µm plane's imaging frequency (about 0.1–1 MHz at millimetre scale, [lens-vp](lens-vp.md) D5): edge harmonics, not the PWM fundamental.

**Checks:**
- Rank-1 removal matches a brute-force re-solve to 4×10⁻¹¹.
- Woodbury via removal and Thevenin via addition match brute force to the printed digit.
- The sketch's leverage sum is 110,875 against n − c = 110,879 (Foster).
- A strip over a plane gives μ0hl/w to 1%.
- A via pair in a plate pair matches a plain sheet solve to 10⁻⁴.
- Refining the DC ground grid from 0.2 to 0.1 mm changes R by under 1%.
- The HF grid (0.15 vs 0.2 mm) and the outer-field thickness (10 vs 1 mm) move L by 7% and 14%.

### 3. Fifteen findings [C unless tagged]

"Per A" means per ampere of that source. DC unless marked.

**Supply and bridge return**

1. **The bridge return is a neck of 0.2 mm tracks.** The low-side current leaves the TMC6300 at its two return pins. Each pin reaches the 1.8 mm exposed pad by one 0.2 mm track. The pad has no vias and does not touch the ground pour; two more 0.2 mm tracks at its far edge lead to the pour and to vias 3 mm away.
   - Copper inside the chip's footprint holds 1.76 mΩ, 20% of the 8.8 mΩ supply path.
   - A return track runs at 73 A/mm² per A, and cutting either one adds 6.3–6.8% to the supply-path R.
   - The datasheet asks for "solid, thermally conducting vias between the die attach pad and the ground plane" [P].
   - The same pad is the package's heat path: 1 W typical at 2 A, and R_θJA = 40 K/W only on a "thermally optimized layout" [P]. The electrical neck is therefore a thermal neck too [I].
2. **The pins are the hottest copper.**
   - The single 0.2 mm supply pin runs at 118 A/mm² per A.
   - The V-phase pin runs at 181 A/mm² per A, and the 1 mm² below it holds 20% of that phase's copper loss.
   - At the 2 A peak rating [P] these become 240–360 A/mm², over sub-millimetre lengths.
3. **Four 0.2 mm vias carry the whole motor supply** from the bottom bus to the top layer. Each takes 21–29%, with leverage 0.55–0.90; removing one adds 2.0–2.8% to R. At HF the same four vias carry only 1–10% of the commutation current, because the local capacitors supply it.
4. **The tinned bus is the pass-through conductor.** For current entering at one supply connector and leaving at the other, R = 7.8 mΩ, 84% of it in the bottom-layer bus (as bare 35 µm copper). The designer's mask opening for extra solder reads this conductor's job correctly.
5. **The daisy-chain ground at J3 hangs on two vias.** One 0.2 mm via beside J3's ground pad carries 52% of that connector's ground current (leverage 0.87; removing it adds 6.0%), and a second carries 35%. The pad sits in a bottom-layer pocket fenced by the U-phase sense traces. At 2 A of bus current that via carries about 1 A [I].

**Hot loop (inductive limit)**

6. **The capacitor ground is an island, so the commutation loop dives.**
   - C9 and C10 share a 3.6 mm² top-layer ground island with three vias.
   - Those vias carry 0.3–0.6% of the DC current, but 39%, 32% and 15% of the commutation current.
   - The return runs 10 mm through the inner ground plane, under the 3.3 V plane, to the three vias north of the chip. Those vias carry 24–29% at both DC and HF.
   - The loop inductance is 9.1 nH in the model (7.8–9.1 across settings), 31% of it in the parts' current paths.
   - The datasheet asks for >10 µF "near pin with shortest possible loop to GND pad" [P]. The netlist cannot tell this loop from a good one.
7. **The 3.3 V plane is the hot loop's image conductor.** It carries 30 A·mm per A of current-length, more than the ground plane (18) or the top ground copper (16). This is induced current only: it has no transport job in this loop. Removing the plane from the window raises L from 9.1 to 25.4 nH (+178%; +126% to +182% across settings).
8. **Fixes are ranked exactly.**
   - One added ground via in the exposed pad, on the capacitor side, cuts L by 15% (best of 511 legal sites; median site −0.4%; brute force agrees).
   - Swapping the inner planes so that ground sits under the power stage cuts L by 19%.
   - Each via of the capacitor island is worth 40–210 pH.
9. **Capacitor shares follow loop inductance, not capacitance:** C9 49%, C10 38%, C11 13% of the edge current. C11's own loop, through the bottom bus, is 16.6 nH, against 10–11 nH for C9 or C10 alone.
10. **The phase copper talks mainly to the 3.3 V plane.** The six phase nets in the window have 13.4 pF of parallel-plate capacitance, and 78% of it faces the 3.3 V plane (50–90% per net). Each PWM edge injects about 10 mA per V/ns into the rail that powers the sense amplifiers. The datasheet warns of dV/dt coupling only into "high resistive" nets [P].

**Phase paths, sensing and floors**

11. **The Kelvin taps work, and the counterfactual says by how much.** The 0.1 mm taps leave the shunt pads' inner edges, and copper adds −0.01% to +0.01% to the 50 mΩ reading. Taps at the outer edges would read +0.9% and drift +34 ppm/K (copper's temperature coefficient). The per-tile Tellegen terms of this error cancel to χ = 0.02, so blame must be counterfactual, as [lens-cd](lens-cd.md) predicts.
12. **Ground offsets are small because the planes work.** Amplifier ground against host ground moves 0.09–0.29 mΩ per A of supply or bus current: at most 0.03% of the 1 V/A full scale. The host's own 3.3 V current moves it 1.3 mΩ per A, mostly in the six vias of the host connector's ground island.
13. **Two phases detour around the decoupling capacitor.**
   - Phase copper is 7.5, 6.9 and 4.0 mΩ (V, U, W), against the 50 mΩ shunt. U and V wrap round C9, and 48–61% of their copper loss is in the pour body.
   - The joint convex floor at the same total area is ≥10.92 mΩ, against 14.47 mΩ for the actual pours in the same relaxed model (gap 0.2%). So 24–25% of the phase-copper loss is avoidable, mainly by giving U 1.5 mm² more.
   - The closed-form Beckmann floor (4.8 mΩ) is far looser.
14. **Leverage is a sheet's ½ almost everywhere.** The median ρ is 0.49–0.54 on every net, and exact/first-order prices have a median of 2.08 (10–90%: 1.93–2.71). Only vias, pins and the J3 pocket approach 1.
15. **There is dead and idle copper.**
   - 11% of the top ground pour and 8% of the bottom pour carry under 0.1% of every modelled current.
   - Four connector mounting pads (27 mm²) float.
   - The top VIN island is 43% idle at DC, yet it is the hot loop's forward path at HF. This is a job flip, like the capacitor vias.

### 4. Passports of selected pieces [C]

| Piece | DC | HF (commutation) | Verbs |
|---|---|---|---|
| Capacitor-island via (best of 3) | 0.4% of supply | 39%; removal +210 pH | idle at DC; carries the HF return: protect |
| Via north of the chip (1 of 3) | 29% of supply, ρ 0.61, removal +2.8% R | 29%, +137 pH | carries both |
| VIN via (1 of 4) | 28% of supply, ρ 0.90, removal +2.8% R | 10%, +12 pH | carries the DC feed |
| Via at J3's ground pad | 52% of J3 current, ρ 0.87, removal +6.0% R | not in loop | near-series path |
| Return track (0.2 mm) | ~50% of the bridge return, 73 A/mm² per A, removal +6.3% R | in the loop | neck |
| 3.3 V plane (In1) | 3.3 V rail only (32% of its loss) | 30 A·mm per A; removal +178% L | images the hot loop |
| U-phase pour | 5.3 mΩ; 61% of the phase's copper loss in the pour body | (not analysed) | carries U; detours round C9 |
| Connector mounting pads | floating | (not analysed) | dead at DC |

### 5. What a netlist-only view misses

| Netlist says | The conductors say |
|---|---|
| C9 decouples VS to GND | its HF return dives under a foreign plane, to vias 10 mm away |
| U3's ground pins and pad are on GND | the motor return crosses 0.2 mm tracks and a pad with no vias |
| 3.3 V plane: a logic rail | the largest HF current in the hot loop; it is part of the power stage's magnetic circuit |
| J3 GND is connected | through two vias behind a fence of sense traces |
| U, V, W are equivalent | U and V cost 1.7× W in copper and are 25% from their floor |
| INA240 across the shunt | taps at the inner edges: 0.01%, against 0.9% at the outer edges |
| In1 and In2 are "planes" | their order is worth 19% of the loop inductance |

### 6. Calibration: the same HF model on three boards [C]

| Board (licence) | Switching cell | Loop L | Energy in the deepest gap | Swap inner planes |
|---|---|---|---|---|
| [oasis](https://github.com/justbuchanan/oasis) (Apache-2.0) | LMR54406 buck on B.Cu; +18 V plane 0.1 mm under it | 2.4 nH | 8% | −22% |
| BLDCM-Power (MIT) | TMC6300 bridge on F.Cu; 3.3 V plane under it | 9.1 nH | 18% | −19% |
| [AFTONSPARV](https://github.com/caffeinated-labs/Caffeinated-AFTONSPARV) (CERN-OHL-S-2.0) | SY8201 buck on B.Cu; 3.3 V plane under it | 12.7 nH | 56% | −62% |

The model separates a tight cell from two loose ones. In both loose ones a foreign-net plane separates the cell from its ground plane.

## Recommendations for our system

1. **Make the passport the reviewer-facing output** ([lens-cd](lens-cd.md) CD1, CD13). For each via, pin, track and pour tile, report its DC and HF shares, its exact removal or addition value, its leverage and its job verb. Flag job flips (idle at DC, load-bearing at HF) and protect them from trimming (CD20).
2. **Treat pin functions as physics inputs.** Taking the bridge-return pins rather than "all GND pins" as the DC return raised the supply-path R by 25%. The role model must read the datasheet's pin semantics (foot points, exposed pad), not only net names.
3. **Add four critics, each an exact or topological check:**
   - a power IC's exposed pad with no vias, or reaching ground only through tracks narrower than its pins;
   - a decoupling loop that crosses a foreign-net plane (the capacitor's ground and the device's return reach ground through different via groups);
   - a power-connector pad with more than half its current in one via (leverage above 0.8);
   - a foreign-net plane between a switching cell and its ground plane, scored by the plane-swap counterfactual.
4. **Propose fixes from exact counterfactuals:** Thevenin via sites, plane order, tap position, and Woodbury batch removals. They cost one solve per candidate.
5. **Calibrate the stack-local HF model** against FastHenry or openEMS on the three loops above, and add a fringing correction, before budgets use its absolute inductance. Until then, use it for shares, rankings and relative changes.

## Conflicts and open questions

**Model limits:**
- **DC:**
  - bare 20 °C copper;
  - 20 µm via plating assumed;
  - no solder, so the tinned bus is overestimated;
  - no lead-frame or package resistance;
  - shunt terminations ignored, which is the worst case for the Kelvin counterfactual.
- **HF:**
  - Local: there is no lateral fringing, so narrow features read high (×1.5 at w/h = 5, about ×3 at w/h ≈ 1). The 0.2 mm tracks over 0.21 mm are the worst case.
  - Lossless: no plane damping.
  - The part current paths (31% of L) and the outer field are crude.
  - Only one window is modelled.
- **Not modelled:** thermal, the floating pads' HF role, the PWM-fundamental band, and the full-wave band.

**Robust versus model-bound:**
- Robust: every DC number, every share and ranking, and the job flips.
- Model-bound: absolute nanohenries. A rough fringing correction suggests 5–7 nH for this loop [I].

**Corrections for other documents:**
- [physics-critics](physics-critics.md): its row for this board lists only reference changes on signal nets. The power-stage necks found here are larger issues that the existing critics miss.
- [lens-cd](lens-cd.md): add that its sheet ×2 law and its χ warning both hold on a real board (2.08 and χ = 0.02).
- Coordinator point 3 ("the world matters"): the daisy-chain current is off-board current that flows in on-board copper and shapes ground offsets (finding 12). Model it as a source.

**Open questions:**
- Is In1's eddy current a useful damping channel for ringing (it has R_s = 1.1 mΩ/sq)?
- Would full-wave or PEEC tools agree on the ranking of via sites?

## Sources

- Trinamic, *TMC6300 Datasheet* rev. 1.01: pin table, §7.3 thermal characteristics, §8.1–8.3 layout ([ADI](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC6300_datasheet_rev1.08.pdf)) [P].
- Board sources and licences: `bench/manifests/candidates.jsonl` (hashes match the files used) [P].
- Wheeler and Hammerstad microstrip inductance, as in [pc_refplane.py](../../../tools/research/physics/pc_refplane.py) [S]. Peaceman well index (1978), via [pw_sheet.py](../../../tools/research/physics/pw_sheet.py) [S]. Spielman and Srivastava leverage sketch, [arXiv:0803.0929](https://arxiv.org/abs/0803.0929) [S]. Frank–Wolfe duality gap: Jaggi, ICML 2013 [S].
- Scripts: [rb_board_passports.py](../../../tools/research/physics/rb_board_passports.py) (this doc), [cd_conductor_passport.py](../../../tools/research/physics/cd_conductor_passport.py), [vp_floors.py](../../../tools/research/physics/vp_floors.py), [pc_refplane.py](../../../tools/research/physics/pc_refplane.py).

See also: [lens-cd](lens-cd.md) · [lens-vp](lens-vp.md) · [lens-ct](lens-ct.md) · [physics-critics](physics-critics.md) · [pdn-and-commutation](pdn-and-commutation.md) · [power-copper](power-copper.md) · [research-gaps](research-gaps.md)
