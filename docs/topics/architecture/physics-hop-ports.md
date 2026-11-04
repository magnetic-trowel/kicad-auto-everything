<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pricing a hop through the port of the connection it replaces (stage R4b)

Scope: stage R4b of [physics-frequency-coverage](physics-frequency-coverage.md#6-build-stages-and-their-gates): the router's unrouted connections as series-EMF ports of the reduced model, the first-order coupling formula, checks and cost. Not here: R4 spectral prices -> [physics-frequency-coverage](physics-frequency-coverage.md#r4-spectral-router-prices).
Keys: hop ports, R4b, `kae.em.hopport`, `kae.em.reduce` `emf=`, series-EMF port, connection opened x_P°, raw flux Φ°, bilinear identity, rank-one compensation κ, stationary return mix β, strip image returns, `em_r4b_check`

Model: for the net(s) routed before the next refresh, each unrouted connection is a part of negligible impedance along the router's own spanning tree, with a series-EMF port ([`kae.em.hopport`](../../../kae/src/kae/em/hopport.py), `kae.em.reduce` `emf=`). Hop currents are exact: the model's current through the connection, including islands that attach downstream.

Verdict on routing: better two-band score, worse wideband (2899 vs 806), cable common mode near 72–77 MHz -> [field-solver-routing-and-intent](../../research/physics/field-solver-routing-and-intent.md).

## 1. Why the old prices missed

A hop replaces a field-free short through which pattern currents already crossed, returning in the planes. T1 priced the whole coupling as if the return were new: right for the board *with* the hop (R4: 1.01–1.07), wrong for the change the per-pair gate measures and the harm responds to. T1's image subtraction counted the short's old return twice: why R4 failed below 0.3 MHz.

Bilinear identity (one solution exact, one unperturbed): Z'_vs − Z_vs = x'_vᵀ(A' − A) x_s, giving

  dZ_vs = I'_v jω Φ_s(hop),  Φ_s = raw flux of x_s along the hop.

Old and new returns form a closed current whose coupling is a potential difference, zero; so **coupling to a hop = raw flux of the board before it, connection opened**: exact to first order, no return subtracted, no crossing term.

## 2. The model

Per connection, at every harmonic:
- I_P: current each pattern drives through the connection;
- Y: admittance of the loop it closes; l_e: that loop's currents;
- x_P° = x_P − (I_P/Y) x_e: patterns with the connection opened.

Hop's own loop = h + Σ β_j r_j, Σ β = 1, stationary. Trial returns r_j: l_e's return (right at low frequency); strip image current in the plane at three widths (1/π · h/(d² + h²), h = 0.5, 1, 2 × the gap). Hop split over raster rows, placed with its returns on the facing faces. The mix enters as a rank-one compensation (covers R–L transition, resonance shift, current a new rail loop picks up):

    dZ_ks = κ [I_k I_s dZ + jω (I_k Φ°_s + I_s Φ°_k)] − Y κ (jω Φ°_k)(jω Φ°_s),
    dZ = Z_loop − Z(l_e),  κ = 1 / (1 + Y dZ)

For A*, costs are linear in the path about the straight hop:
- κ₀ from the straight hop's loop;
- second-order term linearized: adds Y jω Φ°₀ to each pattern's hop current;
- weights multiply the basis's raw flux fields;
- the hop's self cost and split rule stay as in kae.em.pnr.

## 3. Checks

[`em_r4b_check`](../../../tools/research/physics/em_r4b_check.py), 0.25 mm; prediction by `kae.em.hopport` on the reduced model of the board before the hop, over the direct change; ring at 130 MHz. On the R4 check geometry ([em_r4_check](../../../tools/research/physics/em_r4_check.py)) the hop-port coupling price is 1.003–1.018 from 1 kHz to 300 MHz, with or without a slot.

| Case | 1 kHz – 0.3 MHz | 1 – 100 MHz | Ring | 160 – 300 MHz |
|---|---|---|---|---|
| victim hop, solid plane | 1.00–1.01 | 1.05–1.07 | 1.10 | 1.07 |
| victim hop, slot under both | 1.00–1.01 | 1.01–1.02 | 1.00 | 1.00 |
| aggressor's own hop, ss, solid | 0.87–1.01 | 0.82–0.98 | 1.17 | 0.91–0.93 |
| aggressor's own hop, vs, solid | 1.00–1.01 | 1.05–1.11 | 1.26 | 1.04–1.07 |
| aggressor's own hop, ss, slot under it | 0.82–0.99 | 0.31–0.74, phase off | 29 | 1.0–1.4 |

- Before: image-return price gave 0.03–7 for the victim hop, with sign flips.
- Self term across a slot still wrong (image returns placed across the void); the router keeps its own split rule there.

Boost, `--verify`, 0.5 mm debug run, absolute dL at 10 MHz (before: ~0 or wrong-signed):

| Net | Pair | Actual (nH) | Predicted (nH) |
|---|---|---|---|
| +3V3 | overshoot | +0.866 | +0.864 |
| +5V | overshoot | +4.55 | +3.36 |
| +5V | cm J2–J3 | −0.73 | −0.71 |
| +5V | cm J1–J2 | +0.54 | +0.48 |
| /VBAT | cm J2–J3 | −0.069 | −0.057 |
| /VBAT | supply:IC1 | +0.033 | +0.035 |

Board resonance lies just under its 95 MHz limit; harmonic-weighted harm u is less well predicted there (ratios 0.3–1.4).

## 4. Cost

- Each upcoming connection adds one right-hand side to every snapshot: boost = 9 patterns + 1–14 connections.
- Greedy first build: 12-point error grid, each point's factorization kept across steps (opt-in; at the evaluator's 24 points factorizations ran past a 40 GB address space). With 6 connection ports 1304 s vs 1825 s for the old build with none (8 threads).
- Recycled refreshes on the loaded host were 3–8× slower than before, everything in the job alike: contention, not the method; controlled measurement still to do.

## 5. Open

- Self term across a slot: confine image returns to copper, or let the stationary set take returns solved around the slot.
- Harm (u) prediction near the in-band resonance.
- Cost per refresh: drop connection ports of hops already routed; lower the probes' factorization cost.
