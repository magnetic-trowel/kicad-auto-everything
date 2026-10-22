# First-principles EMI budget: from edge rate to dBµV/m

*Tags: [P] primary source read, [S] snippet or secondary, [V] vendor claim, [I] our inference, [C] computed by us.*
*Calculator: [fe_emi_budget.py](../../../tools/research/physics/fe_emi_budget.py) (under 1 s, numpy only). Slot and edge coupling are calibrated with [fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py).*

**TL;DR**
- **Radiated emission from a board with cables is a product of five factors:** source spectrum × drive current × coupling impedance between the cable attachment points × cable antenna × limit. Each factor is a closed form, so the whole chain runs in microseconds per net and connector pair. Only the coupling factor depends on layout, and it is an inductance: about 30 pH for a centred 30 mm trace over a solid plane, 160 pH at 3h from the edge, and 0.45–2.5 nH when the trace crosses a 20 mm slot.
- **Worked case [C]:** a 50 MHz, 1 ns, 3.3 V clock drives 10 pF over 30 mm, with cables on opposite board edges.
  - Over a solid plane it sits near the Class B line: −6 dB by the worst-case MREMC model, but 1.9 µA of cable current against Ott's 5 µA.
  - A 20 mm slot under it costs 24 dB. A split plane costs 38 dB.
  - Putting both cables on the same edge removes the voltage between them (PEEC: 43–63 dB). It leaves the board-vs-cable mode, so it buys 6–30 dB when the return voltage runs away from the cable edge and 24–48 dB when it runs parallel to it (lumped estimate, [C, [rt_world_cm](../../../tools/research/physics/rt_world_cm.py)]). A stitching cap buys about 10 dB. Slowing edges from 1 to 3 ns buys 3 dB, and raising the series R from 33 to 100 Ω buys 2.5 dB.
  - **In this case, removing a slot or split beats edge-rate and series-R tweaks by 20–35 dB; ring damping, not modelled here, is worth 12–21 dB at the ring band** ([lens-th](lens-th.md)).
- **The 1 mV and 5 µA rules are one rule:** 1 mV across a typical 150 Ω common-mode impedance is 6.7 µA. MREMC's worst-case resonant cable (about 36 Ω) is ~13 dB harsher: 1 mV gives 61 dBµV/m, 21 dB over the Class B limit.
- **Use the chain for ranking and placement cost, not pass/fail.** It brackets reality within ±10–20 dB, but it ranks layouts and fixes correctly, and it names the dominant (net, harmonic, connector pair).
- **The skew → common-mode path on unshielded differential cables is the same chain** with V_cm = V_d·|sin(πfΔt)|/2: 50 ps of skew on a 2 Vpp, 31 MHz link leaves ~30 dB for the magnetics and common-mode choke to cover.

## Key facts

### 1. The chain

| Step | Formula | Source | Uncertainty |
|---|---|---|---|
| 1. Spectrum | Trapezoid: V_n = 2·A·d·\|sinc(nd)\|·\|sinc(n·t_r/T)\|; −20 dB/dec above 1/(πτ), −40 dB/dec above 1/(π·t_r) | Fourier series (Ott; Paul) [I] | Real edges are not trapezoids; overshoot adds energy near the ringing frequency |
| 2. Drive current | Short line: I_n = V_n·ωC/√(1+(ωR_sC)²). Matched line: V_n/(2Z0) | lumped RC [I]; MREMC uses V/R_L or V·ωC_L [P-code] | ±3 dB; IBIS models do better |
| 3a. Coupling, solid plane | L_ret = (μ0/π)·h·l_t/w_e / √(1 − 4(1−2h/w_e)·off²/w_e²), with w_e = d1 + d2 (edge distances) and off = \|d1−d2\|/2 | LearnEMC MREMC, [CMode_algr.js](https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js) [P-code]; Hockanson et al., IEEE T-EMC 38(4), 1996 [S] | For a centred trace PEEC is 5–40% above MREMC, depending on the attachment point; near an edge MREMC lies between the best and worst attachment points (±2×) [C] |
| 3b. Coupling, slot | κ_ab·ΔL_slot, with ΔL_slot ≈ μ0·l/(2·ln(4l/g)) and κ_ab the share seen between the cable points: 0.18 for a slot inside a 60 × 50 mm board, about 1 for a split [C PEEC] | [fields-si-emi](fields-si-emi.md) | ±2× |
| 3c. Stitching cap | Z_slot ∥ (jωL_path + 1/(jωC) + ESR) | circuit [I] | L_path 0.5–1.6 nH assumed |
| 4. CM voltage | V_cm = ω·L_cm·I_n (current-driven); V_cm = imbalance·V_dm (voltage-driven) | MREMC [P-code] | — |
| 5. Antenna and field | E_max = F_max·0.55·V_cm·cablefactor at 3 m. F_max = 2/sin(√2) below the 1 m cable's half-wave resonance, 2/sin(√(λ/1 m)) above it. cablefactor = sin(2π·1 m/λ) for λ ≥ 4 m | MREMC [P-code] | A worst-case maximum (resonant cable, best orientation); typical measurements fall 6–20 dB lower [I] |
| 5'. Cross-check | I_cm = V_cm/Z_cm, with Z_cm = 36 Ω (resonant monopole) or 150 Ω (typical). E = 1.257×10⁻⁶·f·L·I/r, capped at 2·60·I/r | Ott, via [kicad-happy](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) [P]; dipole theory [I] | The 5 µA rule assumes the typical case |
| 6. Limit | CISPR 32 Class B at 3 m: 40 dBµV/m (30–230 MHz), 47 dBµV/m (230–1000 MHz); above 1 GHz 50 average / 70 peak. FCC 15.109 B: 40 / 43.5 / 46 / 54 dBµV/m | vendor summaries of CISPR 32 [S]; [eCFR](https://www.law.cornell.edu/cfr/text/47/15.109) [P] | Check the edition in force |

Two physical points sit behind step 3a:
- **The plane is not equipotential at radio frequencies.** A return current I flowing along a finite plane produces a voltage between its ends of jω·L_ret·I, because part of the return flux wraps around the plane edges. For a trace at h = 0.2 mm, L_ret is tiny (tens of pH). It is still enough: 30 pH × 3 mA at 450 MHz is 0.29 mV, and a resonant cable turns 0.29 mV into 53 dBµV/m.
- **Orientation matters.** The voltage appears along the direction of the return current. A fast trace that runs parallel to the line joining two cable points drives them; the same trace running perpendicular drives much less. MREMC handles this through its "horizontal/vertical" cable placement and L_eff.

### 2. Worked cases (fe_emi_budget.py) [C]
Common setup: 50 MHz, 50% duty, 3.3 V, t_r = 1 ns; R_s = 33 Ω; load 10 pF; 30 mm trace at h = 0.2 mm (L1 over L2 GND); board 80 mm wide; 1 m cables; harmonics to 1 GHz. "Margin" is the worst margin to CISPR 32 Class B (3 m) under MREMC's worst case; "I_cm" is the largest harmonic at Z_cm = 150 Ω.

| Case | Coupling L between cable points | Worst margin | I_cm (vs 5 µA) | Change vs base |
|---|---|---|---|---|
| A. Solid plane, centred trace, cables on opposite edges | 30 pH | −5.7 dB @ 450 MHz | 1.9 µA (+8 dB) | base |
| A2. Same, trace 3h from the board edge | 161 pH | −20.3 dB | 10 µA | −15 dB |
| G. Same on a 2-layer board, h = 1.5 mm | 225 pH | −23.2 dB | 14 µA | −17 dB |
| B. Crosses a 20 × 0.5 mm slot inside the plane | 30 pH + 0.18·2.48 nH | −29.7 dB | 30 µA | −24 dB |
| B2. Slot splits the plane (bridge far away) | 30 pH + 2.48 nH | −44.1 dB | 159 µA | −38 dB |
| C. B + one 10 nF cap at the crossing (1 nH path) | shunted | −20.0 dB | 9.9 µA | +10 dB vs B |
| C2 / C3 / C4. B2 + one cap / two caps / one cap 5 mm along the slot | shunted | −33.5 / −29.1 / −36.1 dB | 47 / 28 / 63 µA | +11 / +15 / +8 dB vs B2 |
| D. B with both cables on the same edge | 43–63 dB less voltage between the cables (PEEC); the board-vs-cable mode remains | — | — | +6–48 dB vs B by orientation (lumped model, [rt_world_cm](../../../tools/research/physics/rt_world_cm.py)) |
| E. B with t_r = 3 ns | — | −26.8 dB @ 150 MHz | 13 µA | +3 dB vs B |
| F. B with R_s = 100 Ω | — | −27.2 dB | 16 µA | +2.5 dB vs B |

**Unshielded differential cable** (2 Vpp square wave at 31.25 MHz with t_r 3 ns, an upper bound for 100BASE-TX, before magnetics and CMC): skew 5 / 50 / 200 ps gives a worst margin of −10 / −30 / −42 dB and I_cm of 2 / 21 / 82 µA. Ethernet magnetics and chokes provide the ~30–40 dB that closes this. So **skew is a budget shared with the magnetics, not a free number.**

### 3. What buys dB, in order (this case)
1. **Cable attachment points on one edge** (κ → ~0 removes the inter-cable term; the board-vs-cable mode remains): 6–48 dB by orientation (lumped model). This is the physics behind LearnEMC's "connectors on one edge; nothing fast between connectors" ([emc-placement](../rules/emc-placement.md)).
2. **No slot or split under the net:** 24–38 dB.
3. **Distance from the board edge, and a thin dielectric:** 15–17 dB. A 2-layer board loses most of this ([Ott](https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-1.html): 4-layer radiates ~15 dB less [P]).
4. **Stitching capacitors:** 8–15 dB above their self-resonance. They help at the frequency they resonate at, and a cap placed 5 mm down the slot loses 2–3 dB of that.
5. **Edge rate and series R:** 2.5–3 dB here (one 50 MHz clock). Slowing t_r from 1 to 3 ns moves the spectral corner 1/(π·t_r) from 318 to 106 MHz, but the worst harmonic then becomes the 3rd (150 MHz), which barely moves. Edge control matters more when the cable resonances sit well above the corner.

The ranking changes with the case, so the system should compute it: every candidate fix is a parameter of the chain, and ∂margin/∂parameter tells the agent which fix to try first.

### 4. Consistency checks
- **1 mV rule** (LearnEMC: about 1 mV between antenna parts can fail Class B [P]). MREMC gives 60.9 dBµV/m for 1 mV at 100 MHz, 21 dB over the limit. At a typical 150 Ω, 1 mV is 6.7 µA, close to Ott's 5 µA. The two rules agree at typical common-mode impedance; MREMC is the resonant worst case.
- **5 µA rule** (Ott: Class B for cables ≥ 1 m [P]). Ott's short-antenna formula with 1 m at 3 m and 100 MHz gives 46 dBµV/m for 5 µA: 3 dB over the FCC 88–216 MHz limit and 6 dB over CISPR 32's 40 dBµV/m. So 5 µA is a typical-case rule with no margin.
- **Base case** A: MREMC says fail by 6 dB, the 5 µA check says pass by 8 dB. The 14 dB spread is the difference between a resonant and a typical cable impedance. Treat MREMC as the upper bound and the 5 µA check as the median.

### 5. Other source mechanisms

| Mechanism | Physics | Typical size | When it dominates |
|---|---|---|---|
| Voltage-driven common mode | A trace, heatsink or tall part at V relative to the plane couples capacitively to the cable/board antenna; V_cm ≈ V·C_part→outside / C_board→outside (Shim & Hubing [S]) | Small for traces close to a plane; large for heatsinks over fast dies, long edge traces, unshielded tall magnetics | Heatsinks above ~300 MHz (a 50 mm sink is λ/4 near 1.5 GHz); switch-node copper; 2-layer boards [I] |
| I/O coupling | Crosstalk from a fast net onto an I/O net leaves the board on the cable as common mode | Crosstalk coefficient × aggressor V, with no on-board filter | Unfiltered I/O lines routed near clocks (LearnEMC; HyperLynx rule) |
| Differential-mode loop | E = 2.632×10⁻¹⁴·f²·A·I/r (Ott) | 30 mm × 0.2 mm loop, 3.4 mA, 450 MHz: 31 dBµV/m at 3 m, 16 dB under the limit and ~20 dB below the same net's common-mode estimate [C, hand calc] | Rarely, on boards with planes; it matters for large loops without planes (2-layer, power stages) |
| Cavity / edge radiation | Plane-pair modes radiate from the edges | Excited by vias that change reference ([fields-si-emi](fields-si-emi.md)) | Above ~1 GHz; high-Q GND–PWR pairs |
| Slot antenna | Slot at λ/2 resonance | 20 mm slot ≈ 4.6 GHz in FR-4 | Above 1 GHz (CISPR 32 above-1 GHz limits) |

### 6. From calculator to placement and routing cost
- **Per connector pair (a, b):** precompute κ_ab(x, y, direction) with PEEC over the outline. It gives the cable-pair voltage per unit of return EMF at each position and orientation.
- **Per fast net:** I_n(f) from the role model (IBIS or part family), and its sketch or route.
- **Cost:** Σ_f softplus(E(f) − limit(f) + guard) over the top harmonics. It is smooth in component positions, so it drops into the [P8](../../ideas/original/placement.md) placer loss.
- **Router:** each slot crossing, edge approach or reference change has a ΔL price in nH. The router compares prices instead of obeying a forbid list ([R2](../../ideas/original/routing.md)).
- **Ledger:** I1 rows such as "USB connector ↔ DC jack: V_cm ≤ 100 µV at 150–450 MHz; top spenders: CLK50 (62%), SDIO_CLK (21%)".

## Recommendations for our system
1. **Ship fe_emi_budget as the reference spend model** for EMI budgets. Inputs are net spectra, the outline, connector positions and κ maps. Outputs are a margin per (net, harmonic, connector pair) and the sensitivities.
2. **Calibrate the absolute level once** against a measured board or openEMS run per enclosure class. Until then use the worst-case MREMC level and label results "ranking only".
3. **Make cable-point topology a first-class placement variable.** It is worth 6–48 dB here, depending on orientation; model the board-vs-cable mode, not only κ.
4. **Price stitching caps honestly:** about 10 dB each, near their SRF. Offer "remove the split" first.
5. **Treat skew on cables that leave the board as a common-mode budget** shared with the CMC and magnetics, not as a timing number only.
6. **Model the same-edge case in fe_emi_budget.py and in_emi_voi.py with a board-vs-cable term,** I_same ≈ ω·c_far·ΔV/|1 + jω·C_tot·Z_cm|, where c_far is the capacitance to the world of the board region beyond the return's voltage drop ([rt_world_cm](../../../tools/research/physics/rt_world_cm.py)). Add a ring term with the edge floor ([lens-th](lens-th.md)).

## Conflicts and open questions
- MREMC is a worst case; how far real boards in plastic enclosures sit below it (6 dB? 20 dB?) is not known for our corpus. Measurement or full-wave calibration is needed.
- The 6–48 dB same-edge benefit is a lumped, quasi-static estimate with plate capacitances ([rt_world_cm](../../../tools/research/physics/rt_world_cm.py)); a full-wave board-plus-cable run should settle it ([verification-and-limits](verification-and-limits.md)).
- κ for slots was computed on one outline (60 × 50 mm, h = 0.2 mm). The PEEC needs to be run per board.
- CISPR 32 3 m Class B values (40/47 dBµV/m) come from vendor summaries; verify them against the standard text.
- The Clemson MREMC reports (CVEL-13-051/052) were unreachable (HTTP 503), so the antenna constants (0.55, F_max) come from the calculator code, not the paper.

## Sources
- Research notes: [rules_highspeed_emi.md § 7, 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
- LearnEMC MREMC calculator code: https://learnemc.com/ext/calculators/mremc/calculator/CMode_algr.js [P-code]
- Hockanson, Drewniak, Hubing et al., "Investigation of fundamental EMI source mechanisms driving common-mode radiation from PCBs with attached cables", IEEE T-EMC 38(4), 1996 [S] (https://scholarsmine.mst.edu/ele_comeng_facwork/1140)
- Shim and Hubing, voltage-driven model [S] (https://scholarsmine.mst.edu/faculty_work/1319)
- Ott, common-mode current and red flags: https://hott.shielddigitaldesign.com/techtips/tips-cm.html [P]
- CISPR 32 summaries: https://ti.com/lit/slyy202, https://expo.meanwell.com/upload/data/SafetyNews/EN/EMC-CISPR32.pdf [S]

See also: [fields-si-emi](fields-si-emi.md), [rf-geometry](rf-geometry.md), [emc-placement](../rules/emc-placement.md), [checkers-si-emi](../rules/checkers-si-emi.md), [ideas: si-emi-rf](../../ideas/physics-first/si-emi-rf.md)
