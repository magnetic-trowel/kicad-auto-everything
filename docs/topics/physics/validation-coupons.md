# Validation coupons: a panel chosen by decision value

**TL;DR**
- **Five coupons earn a place, out of about fifteen proposed.** Each separates competing round-1/round-2 predictions by more than its measurement error, and the answer changes a rule or an architecture choice. By value per cost [C]: return-current band (LM) ≫ stitching cut-off (FP) > short voids (SS) ≈ bonding (CM) > node-vs-loop coupling (NL). Via clusters (VC) ride free on the FP panel; the rest are dropped.
- **The predictions differ by 13× to 28 dB.** Round 1's f_x puts the lane-B return transition 13× lower in frequency than lane A; round 2 says within 10%. Symmetric node/loop duality predicts +43 dB of capacitive coupling for the thick dielectric; lens SY predicts +14.5 dB. The λ/20 stitching rule needs 2.9 mm pitch at 2.45 GHz; the wire medium says 10 mm already screens 36 dB.
- **Most predictions are differential:** twins or variants on one panel cancel fab and probe offsets (lens IN, E2).
- **Intervals cover input tolerances; model error is what the panel measures.**
- **One panel costs about $200–500 [I] and 3 engineer-weeks** with NanoVNA-class tools, an audio lock-in and a DMM.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by `val_*.py` in [`tools/research/physics/`](../../../tools/research/physics/): [val_lm_coupon.py](../../../tools/research/physics/val_lm_coupon.py), [val_fp_coupon.py](../../../tools/research/physics/val_fp_coupon.py), [val_coupling_coupon.py](../../../tools/research/physics/val_coupling_coupon.py), [val_slot_coupon.py](../../../tools/research/physics/val_slot_coupon.py), [val_cm_coupon.py](../../../tools/research/physics/val_cm_coupon.py), [val_voi_rank.py](../../../tools/research/physics/val_voi_rank.py). Program and first board: [validation-program](validation-program.md).

## Key facts

### 1. Common setup

| Item | Choice |
|---|---|
| Stackup | JLC04161H-3313: L1–L2 and L3–L4 prepreg 0.0994 mm (ε_r 4.1), core 1.265 mm (ε_r 4.6), outer copper 35 µm, inner 15.2 µm ([JLCPCB](https://jlcpcb.com/impedance) [P]) |
| On every panel | 4-wire R_s strips on each layer (copper weight, the main common factor), a 50 Ω TDR line (ε_r and h), fiducial twins |
| Instruments | NanoVNA-H4 (to 1.5 GHz) or LiteVNA (to 6 GHz); tinySA Ultra; a 24-bit/192 kHz audio interface used as a lock-in with a ~1 A current buffer; a 6½-digit DMM; a clamp-on CM current probe calibrated on the VNA |
| Protocol | Predictions recomputed from the final KiCad geometry and hashed into git before ordering; variant labels hidden from the person measuring; randomized order; repeatability measured first |

Intervals are corner or Monte Carlo ranges over stated tolerances, read as about 90% [I]. Model-form error is the unknown under test, not part of the interval.

### 2. The panel, ranked

| Coupon | Dispute it settles | Decision it informs | Value per cost [C] |
|---|---|---|---|
| LM return band | f_x(h) (round 1) vs ℓ_m(f) = R_s/(πμ0f) (VP, SY, LS) | Distance or topology to protect precision nodes; whether a transition-band solver is needed | 6.6 per EW |
| FP stitching cut-off | Wire medium (LS) vs empty circle (VP) vs κ fit (round 1) vs λ/20 | Stitching pitch and via count; decap reach | 2.5 |
| SS short voids | Slot-line, Babinet, PEEC vs Ott-fit extrapolation | Critic severity and DFM rule for merged antipads | 1.7 |
| CM board–world cut | Chassis bond (practice) vs local closure (CT, DR28) | Heatsink, Y-capacitor and standoff bonding | 1.7 |
| NL node vs loop | Symmetric duality (round 1) vs duality break (SY) | Guards, prepreg as a lever, SW-to-high-Z keep-outs | 1.4 |
| VC via clusters (add-on) | Logarithmic capacity (VP) vs count rule L/N | Via arrangement at decaps and power entries | 0.4: only as free copper on the FP panel |
| ET edge terminations | Cavity model (TH) vs radiating edges | PDN damping by edge RC | 0.15: openEMS check first |

Value is Σ s × EVPI over the claims each coupon settles, in engineer-weeks (EW). The inputs are elicited and the ranking survives ×/÷3 changes ([validation-program](validation-program.md) §1).

**In situ on VAL-1, not as coupons:** tuned vs textbook snubbers and edge rate (real, nonlinear C_oss), and |Z| at real pins. **Dropped:** hot-loop L vs h (anchored by AN-139, SNVA803, EPC; [lens-in](lens-in.md) §5); bridging caps (zero decision value); thermal spreaders (h_conv is a common factor); the DC cut law (exact; one notch on the R_s strip checks the fab).

### 3. Coupon LM: where a return current flows at kHz

**Geometry.**
- **Lanes.** Two 40 mm-wide plane lanes, 140 mm long and 20 mm apart, with no copper between them.
  - Lane A: a 1.0 mm trace on L1 over the L2 plane, h = 0.0994 mm, 0.5 oz.
  - Lane B: the same trace with L2 cleared from the lane, so the plane is L3 at h = 1.38 mm.
- **Drive.** At the near end, between trace and plane; four vias short the trace to the plane at the far end.
- **Kelvin pairs** at lateral offsets x = 1.5, 3, 6, 12 and 18 mm, 50 mm apart along the trace, at least 45 mm from either end.
- **Sense traces** run 0.12 mm from the plane (L1 in lane A, L4 in lane B) and leave as a tight pair at right angles. An optional 1 oz-inner order tests R_s scaling.

**Method.**
- Drive 0.5–1 A; a lock-in reads 100 Hz–80 kHz, a USB network analyser plus buffer 50–300 kHz.
- The observable, |V(x, f)|/|V(x, DC)|, includes the sense loop's own pickup (2–5% at 100 kHz here [C]): a budget names its loop ([lens-ct](lens-ct.md), [lens-sy](lens-sy.md)).

**Predictions** [C, val_lm_coupon]:
- **DC.** 1.414 mV per A at every offset, which is R_s·Δz/W.
- **Lane A, near the trace.** The ratio *rises* before it falls, peaking at f_peak = 223 kHz (×5.0), 112 kHz (×2.5) and 56 kHz (×1.24) at x = 1.5, 3 and 6 mm. Hence f_peak·x = 336 Hz·m, i.e. 1.17·R_s/(πμ0).
- **Far from the trace.** f_half = 82 kHz [70, 95] at 12 mm and 65 kHz [55, 74] at 18 mm.
- **Lane B / lane A** feature frequencies at x ≥ 6 mm: 1.05–1.09.
- **Round 1's f_x reading** predicts no rise. It puts the transition near 1.34 MHz in lane A and 103 kHz in lane B, a ratio of 0.077.
- **Optional 1 oz order:** every frequency drops by the R_s ratio, 2.30.

**Decision.** Below f_half(x), distance does not protect a precision node from a nearby return current; only topology does (a cut, Kelvin taps, a neck at a stagnation point, [lens-ct](lens-ct.md) D3), and prepreg thickness does not move that frequency. If the curves hold, closed forms suffice and no transition-band solver is needed ([research-gaps](research-gaps.md) gap 2). "The transition" moved 10× between docs because each used a different observable ([red-team](red-team.md) claim 5); this coupon fixes one.

### 4. Coupon FP: stitching cut-off, plus via clusters

**Geometry.**
- L2 and L3 solid planes across the core (d = 1.265 mm).
- Tiles of 60, 60, 80 and 90 mm, each with 0.3 mm vias on a square lattice of pitch 10, 15, 20 and 30 mm, and each with a twin tile without vias.
- Two vertical SMAs per tile (centre pin to L3, body to L2), each midway between four posts, 30 mm apart (40 mm at 20 mm pitch).

**Method.** |S21| from 0.3 to 4 GHz (LiteVNA or NanoVNA V2). The registered features are the first transmission peak and the isolation relative to the twin. Both are insensitive to the SMA launch.

**Predictions** [C, val_fp_coupon]:

| Pitch | Belov f_p | First S21 peak | \|S21\| vs twin, 1.0 GHz | 2.45 GHz |
|---|---|---|---|---|
| 10 mm | 3.28 GHz | 3.28 [3.22, 3.40] | −48 dB [−49, −47] | −36 dB [−37, −35] |
| 15 mm | 2.05 | 2.06 [2.02, 2.12] | −30 [−30, −29] | −8 [−12, −2] |
| 20 mm | 1.47 | 1.48 [1.44, 1.52] | −18 [−22, −16] | above f_p: +19 [+10, +28] |
| 30 mm | 0.93 | 0.92 [0.92, 0.96] | above f_p: +13 [+10, +18] | ~0 |

**Competing predictions.** VP's empty-circle bound (7.6/5.1/3.8/2.5 GHz) holds but is loose; round 1's κ = 0.32–0.64 spans 2× at every pitch; λ/20 needs p ≤ 2.9 mm at 2.45 GHz, about 15× the vias of the 10 mm that the wire medium says suffices (LS: ≤ 12 mm, [lens-ls](lens-ls.md)).

**VC add-on.**
- **Geometry.** On the same core: clusters of 1, 2 (2 mm apart), 4 (2 mm square), 9 (3 × 3 at 1 mm) and 4 (0.6 mm square) vias. Each feeds L1 to L3 through L2 antipads inside a ring of 24 vias at R = 10 mm.
- **Method.** 2-port shunt-through from L1 at 20–200 MHz.
- **Predictions** [C]:
  - L = 1.11, 0.78, 0.60, 0.57 and 0.81 nH, each ±12%.
  - Discriminator L(9 at 1 mm)/L(4 at 2 mm) = 0.96 (capacity, [lens-vp](lens-vp.md) D3); the count rule L₁/N gives 0.44.

### 5. Coupon NL: does height cut capacitive coupling?

**Geometry.**
- **Strips.** 60 mm strip pairs, centres 4 mm apart. Aggressor 2.0 mm; victim 2.0 mm (wide) or 0.2 mm (narrow).
- **Heights.** On L1 over L2 (h = 0.0994 mm), or over L3 with L2 cleared (h = 1.38 mm).
- **Guard.** Each pair with and without a 0.5 mm grounded guard, stitched every 2.5 mm.
- **Ports.** An SMA at each near end; a 0 Ω link makes the far ends open (node mode) or shorted to the plane (loop mode).

**Method.** S21 at 5–100 MHz, keeping |S21| above about −75 dB.

**Predictions** [C, val_coupling_coupon]:
- **Per-length coupling, wide/wide:**
  - h = 0.10 mm: C_m′ 1.09 fF/mm [1.04, 1.14], L_m′ 0.32 pH/mm [0.26, 0.38];
  - h = 1.38 mm: C_m′ 5.8 [5.3, 6.6], L_m′ 45 [38, 52].
- **Ratios, thick over thin:**
  - wide: C_m ×5.3 [4.7, 6.3] (+14.5 dB), L_m ×142 [99, 204] (+43 dB);
  - narrow victim: C_m ×10.9 [8.9, 14.9], L_m ×136.
  - Symmetric duality would predict about +43 dB for both.
- **S21 at 30 MHz:**
  - node mode: −60 → −44 dB;
  - loop mode: −77 → −34 dB.
- **Guard:**
  - h = 0.10 mm: C_m ×0.98 and L_m ×0.94, under 1 dB (unmeasurable);
  - h = 1.38 mm: ×0.47 and ×0.45, −6.6 and −6.9 dB.

**Decision.**
- Thin prepreg is a lever on loops, not nodes.
- Guards cost routing space for nothing over thin dielectric.
- Keep-outs for dv/dt copper are set by area and distance, not by h ([lens-sy](lens-sy.md) D1).

### 6. Coupon SS: what a short void costs

**Geometry.**
- Nine 20 mm traces, 50 Ω (0.19 mm on L1 over L2), each crossing one void at mid-length at right angles, plus three twins without a void.
- An SMA at the near end; two vias short each trace to L2 at the far end.
- Voids:
  - slots 1, 2, 3, 5 and 10 × 0.3 mm;
  - slots 2 and 5 × 0.8 mm;
  - five 0.9 mm antipads at 0.8 mm pitch (merged) and at 1.0 mm (separate holes).
- Ott's observable: on the five 0.3 mm slots, a Kelvin pair on L1, 1 mm beside the trace, straddles the void over 25.4 mm.

**Method.** S11 at 20–100 MHz, each trace against its twin.

**Predictions** [C, val_slot_coupon]. ΔL in nH, PEEC with interval, and the alternatives:

| Void | PEEC | Slot-line | Babinet | Critic proxy | Ott fit (ℓ0 = 2.3 mm) | Plane-V ratio |
|---|---|---|---|---|---|---|
| 1 × 0.3 | 0.17 [0.14, 0.20] | 0.24 | 0.31 | 0.15 | 0 | 1.04 |
| 2 × 0.3 | 0.32 [0.26, 0.38] | 0.38 | 0.43 | 0.29 | 0 | 1.18 |
| 3 × 0.3 | 0.45 [0.38, 0.54] | 0.51 | 0.55 | 0.44 | 0.07 | 1.32 |
| 5 × 0.3 | 0.70 [0.60, 0.84] | 0.75 | 0.77 | 0.73 | 0.34 | 1.62 |
| 10 × 0.3 | 1.29 [1.07, 1.51] | 1.28 | 1.27 | 1.47 | 1.29 (anchor) | 2.73 |
| 2 × 0.8 / 5 × 0.8 | 0.56 / 1.11 | 0.55 / 0.98 | 0.76 / 1.11 | 0.29 / 0.73 | 0 / 0.34 | — |
| Antipads merged / separate | 1.03 [0.86, 1.22] / 0.37 [0.29, 0.44] | | | | | — |

- **The four EM models agree within about 1.5×.** The outlier is the Ott fit's knee, an extrapolation below his shortest (6 mm) slot. If ℓ0 scales with h (ℓ0 ≈ 1.4h, taking his board as 1.6 mm [I]), the fit matches PEEC: 0.12 vs 0.10 for the 2-to-10 mm voltage ratio.
- **Decision.** A void matters for an edge-critical net when ΔL > 0.1 nH (3 mV at 30 mA/ns). That holds for every void here except separate antipads at low edge rates. Merging antipads triples the cost.

### 7. Coupon CM: where the displacement current closes

**Geometry.**
- **Board.** 80 × 60 mm, 4 layers, GND on L2, with a 10 × 10 mm switch-node pad on L1 fed by an SMA.
- **Heatsink.** A 40 × 40 mm aluminium plate on 0.25 mm Kapton over the pad, about 12 pF.
- **Chassis.** 6 mm standoffs (nylon or metal) over a 300 × 200 mm aluminium plate.
- **Cable.** 1 m two-wire cable to a LISN bonded to the plate, with a clamp probe 50 mm from the board.
- **Variants:**
  - V1: heatsink floating;
  - V2: heatsink strapped to the chassis;
  - V3: heatsink strapped to board GND (10 mm wire);
  - V4: V3 plus a 4.7 nF Y-capacitor from GND to the chassis at a mounting hole;
  - V5: V1 with metal standoffs.

**Method.** VNA S21 from the pad drive to the probe, 3–200 MHz, registered as ratios to V2. The probe transfer impedance cancels.

**Predictions** [C, val_cm_coupon; lumped extended graph of [lens-ct](lens-ct.md) D2 with the cable as a line, as [red-team](red-team.md) claim 8 requires]:

| vs V2 | 10 MHz | 30 MHz | 100 MHz | 200 MHz |
|---|---|---|---|---|
| V1 floating | −11 [−15, −8] | −16 [−22, −10] | −8 [−11, −5] | −7 [−10, −4] |
| V3 strap to GND | −26 [−33, −20] | −31 [−38, −22] | −27 [−45, −18] | −26 [−45, −14] |
| V4 + Y-cap | −51 [−58, −44] | ≤ −76 (Y-cap series resonance ~41 MHz) | −60 [−79, −50] | −49 [−69, −34] |
| V5 metal standoffs | −56 [−63, −49] | −65 [−75, −56] | −35 [−41, −28] | −25 [−32, −17] |

**Decision.** Bonding a heatsink only to the chassis gives the *most* cable CM current here; closing the displacement current locally (V3–V5) wins by 20–60 dB, less above ~100 MHz as the strap's ωL nears the cable's CM impedance. Values below about −60 dB register as "at floor".

### 8. Pre-registration summary

| ID | Observable | Registered value [interval] | Competing value | Script |
|---|---|---|---|---|
| LM1 | f_peak·x, lane A, x = 1.5–6 mm | 336 Hz·m [285, 385] | no rise below ~1.3 MHz (round 1) | val_lm_coupon |
| LM2 | Feature frequency ratio B/A, x ≥ 6 mm | 1.05–1.09 (±15%) | 0.077 | val_lm_coupon |
| LM3 | f_half at 12 / 18 mm, lane A | 82 [70, 95] / 65 [55, 74] kHz | ~1.3 MHz | val_lm_coupon |
| FP1 | First S21 peak vs Belov f_p, 4 pitches | ratio 1.00 ±0.03 | κ fit: 0.96–1.93× f_p at 10 mm | val_fp_coupon |
| FP2 | Isolation at 2.45 GHz, 10 vs 15 mm | −36 vs −8 dB | λ/20: both inadequate | val_fp_coupon |
| VC1 | L(9 at 1 mm)/L(4 at 2 mm) | 0.96 [0.90, 1.02] (±6% model) | 0.44 (count rule) | val_fp_coupon |
| NL1 | C_m ratio thick/thin, wide | ×5.3 [4.7, 6.3] | ×~140 | val_coupling_coupon |
| NL2 | L_m ratio thick/thin, wide | ×142 [99, 204] | same | val_coupling_coupon |
| NL3 | Guard effect at h = 0.10 mm | < 1 dB (node and loop) | "guards help" | val_coupling_coupon |
| SS1 | ΔL of a 2 × 0.3 mm void | 0.32 [0.26, 0.38] nH | 0 (Ott fit) | val_slot_coupon |
| SS2 | Merged / separate antipads | ×2.8 [2.0, 4.2] | — | val_slot_coupon |
| CM1 | V3/V2 at 30 MHz | −31 [−38, −22] dB | ≥ 0 dB (chassis bond best) | val_cm_coupon |
| CM2 | V5/V2 at 30 MHz | −65 [−75, −56] dB, or at floor | — | val_cm_coupon |

**Pass rule.** At least 80% of registered values inside their intervals per coupon, with every discriminator on the registered side. A coupon whose measurement lands on the competing value refutes its claim. The kill criteria are in [validation-program](validation-program.md) §5.

## Recommendations for our system

1. **Order one panel now:** LM, FP with VC, SS, NL, plus the CM board and the common-factor strips. The geometries are fixed above; the scripts recompute the predictions from the final KiCad files.
2. **Hash the predictions, the analysis script and the measurement order into git before ordering.** Fit nothing until the registered comparison has been read.
3. **Assimilate common factors first** (R_s from the strips, ε_r and h from TDR), re-score, then attribute the residual to model lineage ([lens-in](lens-in.md) IN30).
4. **Fold the outcomes into rules and critics:** LM into precision-node topology rules and the solver plan, FP into stitching pitch, SS into RET-COV severity and a merged-antipad DFM rule, CM into bonding advice, NL into guard and keep-out rules.

## Conflicts and open questions

- **All predictions are quasi-static** (2-D cross-sections, cavity modal sums, plane PEEC, lumped graphs). Radiation from coupon edges and SMA launches is not modelled. FP's S21 levels above f_p are resonant and wide.
- **Chassis-plate and cable resonances** dominate absolute CM levels, so only ratios are registered.
- **Coupon-to-board transfer is unproven;** VAL-1 carries the same strips to test it.
- **The VOI inputs are elicited [I].** The ranking, not the numbers, is the claim.

## Sources

- JLCPCB stackup table ([impedance page](https://jlcpcb.com/impedance)) [P]. Ott's slot data via [physics-critics-validation](physics-critics-validation.md) [P].
- Round-2 lenses: [lens-ls](lens-ls.md) (wire medium, ℓ_m), [lens-vp](lens-vp.md) (capacity, floors), [lens-sy](lens-sy.md) (duality), [lens-ct](lens-ct.md) (board–world cut), [lens-th](lens-th.md) (damping), [lens-in](lens-in.md) (VOI).
- Reused scripts: vp_rl_band, fe_cavity, vp_floors, sy_duality_balance, fe_peec_plane, ct_cut_topology.

See also: [validation-program](validation-program.md) · [red-team](red-team.md) · [research-gaps](research-gaps.md) · [physics-critics-validation](physics-critics-validation.md) · [solver-ladder](solver-ladder.md)
