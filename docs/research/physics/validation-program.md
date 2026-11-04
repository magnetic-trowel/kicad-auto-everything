# Validation program: VOI-ranked claims, a two-arm test board, coupons and a floor census

**Status:** untested idea (predictions registered and computed; nothing fabricated or measured).
**First published:** 2026-10-22, commit [2171ac1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2171ac1a79c027d5836c01b94da193cdba562690) on branch `claude/vigilant-mayer-i91rrr` (scripts from [0dfe51a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0dfe51aadd1968b83f8425a2197befc98c3d32ea) and [ca92bc5](https://github.com/magnetic-trowel/kicad-auto-everything/commit/ca92bc5b4b716e2ee0a1d42c25b94e99e307a37e)).

Scope: plan to anchor the model-only physics numbers in measurement: rank claims by value of information, one two-arm test board, six coupons, pre-registered predictions with kill criteria, blind measurement. Computed so far: design-stage predictions and a pilot floor census on four open boards. **No board or coupon ordered; nothing measured.** Not here: full plan -> [validation-program](../../topics/physics/validation-program.md), [validation-coupons](../../topics/physics/validation-coupons.md).
Keys: VOI, EVPI, engineer-weeks EW, VAL-1, arm R, arm P, arm F, kill criteria, coupons LM FP VC NL SS CM, floor census, Beckmann floor, SIMP p = 1, LS30, IN27, IN28

## Idea and how it works

- **VOI ranking.** Claim k: action A assumes it holds, B that it does not; EVPI_k = n_k·min(p·r_A, (1 − p)·r_B) over n = 50 future boards, in engineer-weeks (EW). Inputs elicited [I]. Robustness = P(top 3) under Monte Carlo multiplying every input by a log-uniform factor in [1/3, 3]; only rankings that survive ×/÷3 are claimed.
- **VAL-1 two-arm board.** 80 × 60 mm, 4 layers (JLC04161H-3313 stackup): 12 → 3.3 V 1 MHz synchronous buck, ESP32-S3-MINI-1 with USB 2.0, ADS1220 24-bit ADC, 2 A ground-current injector, common-factor probe structures. Arm R: experienced rule-following engineer blind to the predictions; arm P: physics-first method; optional arm F: Freerouting. Population variants (snubbers S0–S3, slowed edge E1, connector edge, bonds) turn budgets into differential predictions. Models: series-RLC ring ODE with an erf edge, sheet Laplace for ADC offset, continuum plane pair with decaps for PDN.
- **Pass rules:** coverage ≥ 80% inside 90% intervals; differential sign right ≥ 90% and magnitude within 2×; interval score better than app-note baselines. Assimilation fits common factors first, then one discrepancy term per model lineage.
- **Eleven kill criteria**, e.g.: P beats R by less than scatter (thesis falsified for this class); > 20% of differentials wrong-signed; coverage < 50%; LM features scale as 1/h; FP peak > 25% from f_p; tuned snubber S2 not within 3 dB of S1 at under half the loss; critic recall < 70% or false alarms > 10% or ΔSpearman < 0.1; partition-level avoidable loss < 10% at suite scale.
- **Pilot floor census** (`val_floor_census.py`), 14 nets on four open boards: actual resistance R_act (finite volumes, 0.1 mm cells, vias as barrels); Beckmann floor R ≥ W1²/(I²·ΣA_l/R_s,l); convex SIMP p = 1 floors at equal area (Q4 elements on 0.15/0.25 mm cells, optimality-criteria updates, fractional-knapsack dual certificate). Three domains: shape (own zones), routing (others' tracks movable), partition (others' fills negotiable).

**Coupons** (registered predictions):

| Coupon | Dispute | Registered prediction | Competing prediction |
|---|---|---|---|
| LM | return-current band | f_peak·x = 336 Hz·m (1.17·R_s/(πμ0)); f_half 82/65 kHz at 12/18 mm | f_x(h) model: 0.077 |
| FP | stitching cut-off | first S21 peak at Belov f_p (3.28/2.05/1.47/0.93 GHz at 10/15/20/30 mm pitch); 10 mm screens 2.45 GHz by −36 dB | λ/20 rule needs 2.9 mm |
| VC | via clusters | L ratio 0.96 | count rule 0.44 |
| NL | coupling vs height | C_m ×5.3 (+14.5 dB), L_m ×142 (+43 dB) | symmetric duality |
| SS | short slots | 2 × 0.3 mm void ΔL 0.32 nH; four EM models agree within 1.5× | Ott fit: 0 |
| CM | heatsink bonding | strap to GND −31 dB at 30 MHz vs chassis bond | none |

Inputs: VOI ranking `val_voi_rank.py`, VAL-1 design values `val_board.py`, coupons `val_*_coupon.py`; census boards from `bench/manifests/candidates.jsonl`: oasis ([justbuchanan/oasis](https://github.com/justbuchanan/oasis), Apache-2.0), Caffeinated-AFTONSPARV (CERN-OHL-S-2.0), Pi5_PCIe ([m1geo/Pi5_PCIe](https://github.com/m1geo/Pi5_PCIe), MIT), BLDCM-Power ([brenocq/bldc-motor](https://github.com/brenocq/bldc-motor), MIT). Currents assumed by inspection (the `PILOT` dict in the script).

## Results

All predictions [C] or elicited [I].

| Item | Result |
|---|---|
| Rank 1 claim | "physics-first beats competent rules": EVPI 10.5 EW, P(top 3) 0.78 |
| Rank 2 claim | "return spread follows ℓ_m(f) = R_s/(πμ0f), not f_x(h)": 5.0 EW, 0.66 |
| Value per cost | LM coupon 6.6/EW, FP 2.5, SS and CM 1.7, VAL-1 1.4 (largest absolute value, 11.5 EW) |
| VAL-1 R vs P (design stage) | ring 411 vs 531 MHz; overshoot 36% [23, 48] vs 5% [1, 25]; PDN abs(Z) at 100 MHz 0.68 vs 0.065 Ω; ADC offset 364 µV/A [204, 602] vs under 1% with a Kelvin REFN |
| Floor census | median 4% avoidable by shape; thermal reliefs cost 7–48% (oasis); partition holds 107 of 135 mW (79%); Pi5_PCIe's 12 V strip 28.5 mΩ, 114 mW, 85% avoidable by partition |

- Robustness caps information: cheap robust actions (world node, via spreading) should just be done, not tested [I].
- Caveats: VAL-1 values use generic parts (C_oss 100–220 pF, Q0 5–20); coupon intervals cover input tolerances, not model-form error.
- Red team -> [redteam-corrections](redteam-corrections.md) (`rt_voi_sensitivity`: off-board VOI share prior-dependent; convex floors grid-dependent, so census floors are raster-scoped).

## Verdict

Not executed. Next steps (none done): census on the 112 qualified boards with schematic DC operating points; finalise coupon geometries; openEMS on SS and FP; order the panel and CM board; lay out and freeze VAL-1 arms R and P; hash the predictions; fabricate and measure blind. Known confounds: one designer per arm; single-net floors. Until run, the physics pages here describe a consistent model, not established physics; [research gaps](../../topics/physics/research-gaps.md) ranks "ground truth" the largest open problem.

## Code

`tools/research/physics/`, print-only: `val_voi_rank.py`, `val_board.py` (`[ring|adc|pdn]`), `val_floor_census.py` (`python -I val_floor_census.py DIR` reads `DIR/<board>/board.kicad_pcb` with saved zone fills; boards are third-party, never copied into the repo), `val_lm_coupon.py`, `val_slot_coupon.py`, `val_cm_coupon.py`, `val_coupling_coupon.py`, `val_fp_coupon.py` (`[fp|vc|et]`).

Related: [first-principles-lenses](first-principles-lenses.md) (LS30, IN27/IN28, VP floors), [physics-critics-and-passports](physics-critics-and-passports.md) (same four boards, mutation benchmark), [redteam-corrections](redteam-corrections.md), [domain-models](domain-models.md).
