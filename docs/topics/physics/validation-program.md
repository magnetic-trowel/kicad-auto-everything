# Validation program: anchoring physics-first in measurement

**TL;DR**
- **Every number in rounds 1–2 is model against model.** This program anchors them in measurement, in the order that most changes decisions. By value of information (VOI), two claims lead robustly [C]:
  - the thesis itself: physics-first beats competent rule-following;
  - lens VP/SY/LS's return-current band, which decides a solver build and how to protect precision nodes.
  
  Claims whose robust action is cheap (world node, via spreading) should be acted on, not tested.
- **The first board, VAL-1, is the main experiment.** It has a 12 V buck, an ESP32-S3 module with USB 2.0 and a 24-bit ADC, on 4 layers with a fixed USB-C connector and fixed holes. It is laid out twice, rule-following (R) and physics-first (P). Variants by population (snubbers, edge rate, connector edge, bonds, a ground-current injector) turn most budgets into differential predictions. Design-stage examples [C]: overshoot 36% vs 5%; PDN |Z| at 100 MHz 0.68 vs 0.065 Ω; ADC offset 364 µV/A vs < 1% of that with a Kelvin tie.
- **Five coupons settle disputes that flip rules,** with predictions 13× to 28 dB apart ([validation-coupons](validation-coupons.md)).
- **The computational track starts now.** A pilot floor census of 14 nets on four open boards: within the zones as drawn, pour shape wastes a median 4%. Thermal-relief connections cost 7–48% on the one board that uses them. Re-partitioning the planes would remove 107 of 135 mW, almost all of it on one 12 V strip. The copper leverage is front-loaded, as round 1 argued for EMI.
- **Kill criteria are explicit.** Say which result falsifies which part of the philosophy, and report physics apart from cp1/cpk.

Tags: [P] primary, [S] secondary, [I] inference, [C] computed by [val_voi_rank.py](../../../tools/research/physics/val_voi_rank.py), [val_board.py](../../../tools/research/physics/val_board.py), [val_floor_census.py](../../../tools/research/physics/val_floor_census.py) and the coupon scripts. VAL-1 values are design-stage: the registered numbers are recomputed from the frozen copper.

## Key facts

### 1. What is worth testing

For each claim, A acts as if it holds and B does not. EVPI = n·min(p·r_A, (1−p)·r_B) over 50 future boards, in engineer-weeks (EW), from elicited inputs [I] ([lens-in](lens-in.md) E1). The ranking, not the numbers, is the result. "Robust" is P(top 3) when every input varies ×/÷3 [C].

| Rank | Claim (source) | Competing view | Decision it flips | EVPI EW | P(top 3) | Test |
|---|---|---|---|---|---|---|
| 1 | Physics-first beats competent rules on binding budgets ([README](README.md)) | "Corrected rules suffice" ([red-team](red-team.md) §5) | Build the physics core, or rules + critics | 10.5 | 0.78 | VAL-1 |
| 2 | Return spread follows ℓ_m(f), not f_x(h) (VP, SY, LS) | Round 1's f_x; gap 2 | Transition solver; topology vs distance near ADCs | 5.0 | 0.66 | LM coupon, VAL-1 injector |
| 3 | Critics are fit to be rewards ([physics-critics](physics-critics.md)) | Goodhart; circular mutants | Reward on critics, or report only | 3.0 | 0.32 | Mutation benchmark |
| 4 | F1 proxies rank real contenders ([solver-ladder](solver-ladder.md)) | Need F2 in the loop | Inner-loop fidelity | 2.0 | 0.24 | VAL-1 signs, cross-solver |
| 5 | Designed damping, tuned snubbers ([lens-th](lens-th.md)) | Edge rate or device damping suffice | Q ledger; snubber design | 1.7 | 0.23 | VAL-1 variants |
| 6 | Quasi-static models suffice for board budgets | Full-wave needed | Solver class | 1.5 | 0.18 | openEMS; FP, SS |
| 7–9 | Autorouters make physics faults; local CM closure (CT); wire-medium stitching (LS) | Practice | Critic gating; bonding; via pitch | 1.2 each | ≤ 0.12 | Router audit; CM, FP |
| 10–14 | World node; pour floors; short voids; duality break; PDN layer assignment | Various | Per-board rules | 0.8–1.0 | ≤ 0.09 | VAL-1; census; SS, NL |
| 15–17 | Via capacity; edge terminations; hot-loop L vs h | Count rule; anchored data | Small | ≤ 0.1 | 0 | Add-on or none |

Three lessons:
- **Robustness caps information** (IN D5). Modelling the world node and spreading vias are cheap enough to do unconditionally, so testing them buys little. Their magnitudes are calibrated per product class at bring-up.
- **Architecture claims outrank layout claims.** Rows 1–6 decide what gets built; the rest decide rules.
- **Experiments by value per cost** [C]: LM coupon 6.6/EW ≫ FP 2.5 > SS, CM 1.7 > VAL-1 1.4 (largest absolute value, 11.5 EW) ≈ NL, census 1.4 > router audit 1.3 ≈ mutation benchmark 1.2 > cross-solver 0.7 ≫ VC 0.4, ET 0.15.

### 2. The first board, VAL-1 (IN27)

**Design.** Both arms share everything except layout and layer assignment.

| Item | Specification |
|---|---|
| Board | 80 × 60 mm, 4 layers, JLC04161H-3313 (0.0994 mm prepreg) |
| Fixed parts | USB-C on one short edge; four M3 plated holes with 0 Ω/DNP links to GND; the module's antenna at a fixed edge position |
| Power | 12 V locking connector, with footprints on the USB edge and the opposite edge (populate one); TVS, reverse-polarity FET, π filter |
| Buck | Synchronous flip-chip buck with a SYNC pin, 12 → 3.3 V, 2 A, f_sw 1 MHz, spread spectrum off; snubber footprints S1/S2/S3; boot-resistor footprint (E1) |
| MCU, radio, USB | ESP32-S3-MINI-1 (2.4 GHz PCB antenna); USB 2.0 full speed to the fixed USB-C |
| ADC | ADS1220 with a 4-wire bridge connector, ratiometric reference, on-board bridge emulator, inputs-shorted jumper |
| Injector | Two pads that drive up to 2 A DC–100 kHz through the ground plane along a defined path |
| Common-factor and probe structures | R_s strips, a TDR line, a 1 kΩ SMA tap at the switch node, U.FL shunt pairs at ADC AVDD and module 3V3, emissivity dots, a heater resistor |
| Firmware | Logs ADC data and the Wi-Fi noise floor over USB; drives buck SYNC |

**Arms.**
- **R.** An experienced engineer, blind to the predictions, works from vendor layout guides and common rules (TI buck guide, ADS1220 datasheet, Espressif guidelines).
- **P.** Laid out by the physics-first method, by the system or a different person.
- Both arms get the same time and must pass DRC.
- **Optional F:** Freerouting on R's placement. It tests the founding complaint, "DRC-correct but physically wrong".
- **Optional factor:** both arms ordered again on JLC04161H-7628 (0.21 mm). This is SY's duality break on a real board: loops should move, nodes should not.

**Registered predictions.** Recomputed from the frozen copper by the system's evaluators and hashed before fabrication. Design-stage values with 5–95% ranges are [C, val_board] unless tagged [I]:

| Budget | Observable and method | Design-stage prediction |
|---|---|---|
| Ring frequency | Comb envelope at the switch-node tap (tinySA Ultra), or a ≥ 1 GHz scope | R 411 MHz [298, 563], P 531 [379, 712]; P/R 1.29 |
| Overshoot, S0 | Scope, or comb-line amplitude A ≈ π·f_r·V_line/(Q·f_sw) | R 36% [23, 48], P 5% [1, 25] |
| Ring Q and band level | Variants against S0 | S1 −16 dB [−20, −12], Q 0.64, 65 mW. S2 (tuned) −14.5 [−19, −11], Q 1.1, 22 mW. S3 (far) Q 2.4. E1 (4 ns edge) −8.5 dB (trapezoid) to −60 dB (erf edge), +30 mW |
| ADC offset | Injected ground current, DC, emulator input | R 364 µV/A [204, 602]; P < 1% of R (Kelvin reference, one plane tie); 1 A gives ~3,600 noise σ in R |
| ADC noise and aliasing | Shorted-input noise at 20 SPS, PGA 128, buck off and on; spectrum while SYNC sweeps through 4·f_MOD = 1.024 MHz | About 0.1 µV rms in both arms, under 10% rise with the buck on [I]; tones only within the sinc passband of k·f_MOD, amplitude = coupled ripple × sinc response |
| Decap impedance at pins | 2-port shunt, 1–300 MHz | \|Z\|(100 MHz) R 0.68 Ω (rail on L3 across the core), P 0.065 Ω (pour over L2 at 0.1 mm); ratio 0.09 |
| Conducted emissions | LISN + tinySA, 150 kHz–30 MHz, 12 V cable | DM about 30 dBµV at 1 MHz (±10 dB) behind the π filter [I]; arms differ by filter-bypass coupling and SW-node C_ext |
| Cable CM and radiated pre-scan | Clamp probe on both cables in an aluminium box; antenna at 1 m | Ratios between variants [I]: connector edge 6–30 dB ([red-team](red-team.md) claim 12; the 40 dB was an input), board-to-box bonds as in the CM coupon. Absolute E ±15 dB, used to calibrate the enclosure class |
| IR temperatures | Thermal camera at 2 A, after calibrating h_conv on the heater | Buck IC rise 20–50 K; P minus R ≤ −5 K [I]; ±25% after calibration |
| Radio desense | ESP32 noise floor with the buck on and off | < 1 dB (a registered null) [I] |

**Equipment.** About $1.5–2.5k [I]:
- NanoVNA or LiteVNA, tinySA Ultra, near-field probes;
- a DIY LISN and a clamp probe calibrated on the VNA;
- a thermal camera (P2 Pro class), a 6½-digit DMM, an audio-interface lock-in, a 100 MHz scope;
- an aluminium box, a USB isolator, 1 m cables;
- a borrowed ≥ 1 GHz scope if available.

Fabrication and assembly: under $1k.

**Pass/fail for the predictions themselves** (per class; registered before data):
- **Coverage.** At least 80% of values inside their 90% intervals (n ≥ 10; fail below the binomial 5% quantile).
- **Sharpness.** Median interval narrower than the decision's flip margin, so a covered prediction still decides something.
- **Differentials.** Sign right in ≥ 90% where |Δ_pred| > 2× repeatability, and magnitude within 2× (±6 dB).
- **Skill.** Interval score (Gneiting and Raftery 2007 [S]) better than a rule-of-thumb baseline: app-note values and "no difference between arms".

A class that ranks well but misses levels is fit for ranking, not compliance (IN E2).

**Assimilation.**
1. **Common factors first:** R_s (strips), ε_r and h (TDR), probe transfer impedances, h_conv (heater), enclosure and cable offset (pre-scan vs model).
2. **Then one discrepancy term per model lineage:** image PEEC, cavity, MREMC chain, thermal FV, lumped CM graph (IN30). An identifiability check (IN29) must pass first.
3. **Store posteriors** per fab, stackup and enclosure class in a versioned registry.
4. **Re-register for the next board of the class.** Success means the error shrinks while coverage holds. Post-build data cannot improve this board's layout, only the next one's ([red-team](red-team.md) claim 15).

### 3. Coupons

LM, FP (with VC), SS, CM and NL, with geometries, predictions and pass rules in [validation-coupons](validation-coupons.md). They share the VAL-1 order, and VAL-1 carries the same R_s strips to test coupon-to-board transfer.

### 4. Computational track (no hardware; start now)

**Pilot floor census** [C, val_floor_census]. Fourteen nets on four open boards (oasis, aftonsparv, BLDCM-Power, Pi5 PCIe), with current patterns assumed by inspection. Floors at equal area, each compared with the same copper on its own grid, under three freedoms: shape (own zones), routing (other tracks movable), partition (other zones' fills negotiable). Beckmann is the shape-free bound ([lens-vp](lens-vp.md) D1).

| Board | Nets | DC loss, mW | Avoidable: shape / routing / partition (medians) | Note |
|---|---|---|---|---|
| oasis | 7 | 2.7 | 24 / 33 / 43% | Pads on thermal reliefs: 92–100% of the extra domain lies within 0.8 mm of the net's pads |
| aftonsparv | 3 | 4.3 | 0 / 3 / 64% | Solid pad connections |
| Pi5 PCIe | 2 | 121.9 | 0 / 0 / 66% | 12 V in a ~3 mm × 80 mm strip on a 0.5 oz inner layer: 28.5 mΩ, 114 mW, 57 mV at 2 A; 85% avoidable by partition |
| BLDCM-Power | 2 | 6.5 | 0 / 4 / 67% | VIN on tracks |

Readings:
- **Inside the drawn zones, KiCad fills sit on the floor** where pads connect solidly. This confirms VP: the domain, not the shape, sets the loss.
- **Relief connections are a priced trade.** They cost 7–48% of a pour's resistance. Solderability is the other side of it.
- **What remains is front-loaded.** Plane partition alone holds 79% of the loss across all 14 nets (107 of 135 mW); layer reassignment was not even allowed. So VP's "report avoidable loss for every pour" should report the partition-level floor.
- **The absolute loss is negligible on three of four boards.** A pour synthesizer earns its keep on high-current designs only.
- **Caveats.** Assumed currents; single-net floors that ignore other nets' needs; raster scope (0.15/0.25 mm; [red-team](red-team.md) claim 4).
- **Next.** Run the 112 qualified boards, with DC currents from the schematic operating point.

**Mutation benchmark** (PC29–31, IN36, V5):
- At least 8 operators × 50 qualified boards, each with benign twins.
- Oracle labels: F1 everywhere, F2 on a sample. Equivalent mutants are dropped.
- Operators come from real escapes, written by someone other than the critic's author ([physics-critics](physics-critics.md), circularity).
- Metrics: recall at the site, false alarms on twins, Spearman between the critic's value and the oracle's Δ.

**Router audit.** Run the critics on Freerouting and reference attempts over the qualified suite. Registered:
- Freerouting perforates `signal`-typed planes;
- it produces more RET-VIA findings than the human board;
- a `power`-typed DSN variant (PC44, new run name) removes most of the perforation.

**Cross-solver checks.** Each is pre-registered and from an independent lineage (IN E6):
- **openEMS:** SS geometries, FP tiles (radiation and launches) and ET terminations;
- **FastHenry** (internal use only): the LM lanes as meshed finite planes;
- **Palace:** eigenmodes of the FP tiles.

Agreement lowers a coupon's VOI; disagreement makes it decisive.

**Harness integration** ([CLAUDE.md](../../../CLAUDE.md), [physics-critics](physics-critics.md) §4):
- A separate `physics-report <run> <baseline>` reads attempt directories and writes `physics/ledger.json` and `scorecard.json`.
- It prints cp1, cpk, completion and error counts unchanged, beside the physics columns, the floor census included.
- It never touches score.py, potential() or cp1/cpk.
- Comparisons use the same KiCad version, manifest, suite, critic version and role files.
- Registered predictions become golden values in the regression suite (gap 20), versioned so that no script changes them silently.

### 5. Kill criteria

| Result | Falsifies | Then |
|---|---|---|
| P beats R by less than fab and measurement scatter (≈ 2–3 dB EMI, 10% overshoot or ripple, 2 K, 3σ ADC noise) on every binding budget, where ≥ 6 dB or 2× was predicted | The thesis for this board class (cf. [red-team](red-team.md) §5) | Rules + critics; physics for calibration and diagnosis |
| More than 20% of differentials wrong-signed | Ranking-grade proxies | F2 in the inner loop |
| Coverage < 50% after common-factor calibration | That model class for compliance | Ranking use only |
| LM: features scale as 1/h, no near-trace rise | The ℓ_m band | Round 1's f_x; build the transition solver |
| FP: first peak > 25% from f_p | Wire-medium unification | Empirical stitching rules |
| NL: wide-strip C_m ratio ≥ 50× | Duality break | Thin prepreg helps nodes; guards return |
| CM: V3 not ≥ 15 dB below V2 at 10–30 MHz | The lumped board–world cut | Bonding by practice; full-wave world model |
| SS: 2 × 0.3 mm void under 0.1 nH | EM slot models for short voids | Relax RET-COV below a few mm |
| S2 not within 3 dB of S1's ring band at < ½ the loss | The tuned absorber with real C_oss | Textbook snubbers; Q ledger as a report |
| Critic recall < 70%, false alarms > 10%, or critic scores rank measured outcomes no better than rule-violation counts (ΔSpearman < 0.1) | Critics as rewards | Reports only |
| Partition-level avoidable < 10% on nets above 0.5 A at suite scale | Front-loaded copper leverage | Floors as a report only |

**What does not falsify.** Absolute EMI misses up to ~15 dB with correct rankings, which lens IN expects. One-board results, which bind only their class.

## Recommendations for our system

1. **Weeks 0–2:**
   - run the census on the qualified suite;
   - run the router audit;
   - build the mutation benchmark;
   - finalize the coupon geometries in KiCad and register their predictions.
2. **Weeks 2–4:** order the coupon panel and the CM board; run openEMS on SS and FP while they ship; lay out VAL-1 R and P in parallel.
3. **Weeks 4–8:**
   - freeze VAL-1;
   - recompute and hash every prediction;
   - fabricate, measure (blinded, randomized order) and score;
   - assimilate common factors before reading any model-form residual.
4. **Throughout:** treat each later prototype as a registered experiment (IN27). Keep an evidence ledger that cites the measurement registry, not scripts.

## Conflicts and open questions

- **The VOI inputs are elicited.** Lens IN's own priors moved its headline 33–84% to 10–49% ([red-team](red-team.md) claim 15). Only rankings that survive ×/÷3 are claimed.
- **VAL-1 is one board class with one designer per arm.** Designer skill confounds the arms; a second R designer, or the F arm, bounds it.
- **The design-stage predictions** assume a generic part (C_oss 100–220 pF, Q0 5–20) and a generic plane. The frozen-copper values supersede them.
- **The census uses assumed currents and single-net floors.** A multi-net partition floor needs a joint formulation.

## Sources

- [S]: Gneiting and Raftery, JASA 102(477), 2007 (interval scores); Kennedy and O'Hagan, JRSS B 63(3), 2001 (model discrepancy).
- [P]: JLCPCB stackups ([impedance page](https://jlcpcb.com/impedance)).
- Boards: kaebench candidates manifest, fetched at pinned commits (not redistributed).
- Round-2 inputs: [lens-in](lens-in.md), [lens-vp](lens-vp.md), [lens-ct](lens-ct.md), [lens-sy](lens-sy.md), [lens-ls](lens-ls.md), [lens-th](lens-th.md), [lens-cd](lens-cd.md).
- Round-3 red team: [red-team](red-team.md).

See also: [validation-coupons](validation-coupons.md) · [research-gaps](research-gaps.md) · [physics-critics-validation](physics-critics-validation.md) · [solver-ladder](solver-ladder.md) · [benchmark-plan](../verification/benchmark-plan.md)
