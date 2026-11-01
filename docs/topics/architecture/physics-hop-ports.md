<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pricing a hop through the port of the connection it replaces (stage R4b)

**TL;DR**
- **The router's unrouted connections are now ports of the reduced model.** For the net(s) routed
  before the next refresh, each connection is a part of negligible impedance along the router's own
  spanning tree, with a series-EMF port
  ([`kae.em.hopport`](../../../kae/src/kae/em/hopport.py), `kae.em.reduce` `emf=`).
- **Coupling to a hop is the raw flux of the board before it, with the connection opened.** This is
  exact to first order, with no return subtracted and no crossing term. On the R4 check geometry it is
  1.003–1.018 from 1 kHz to 300 MHz, with or without a slot. T1's image subtraction counted the
  short's old return a second time, which is why R4 failed below 0.3 MHz.
- **The hop's own loop** takes the stationary mix of the old return and strip-image returns. The mix
  enters as a rank-one compensation, which covers the R–L transition, the resonance shift, and the
  current a new rail loop picks up.
- **Hop currents are exact.** They are the model's current through the connection, so islands that
  attach downstream are included.

## 1. Why the old prices missed

A hop replaces a field-free short. The pattern currents already crossed between the two islands
through it, and their return already ran in the planes. T1 priced the hop's whole coupling, as if its
return were new. That count matches the board *with* the hop (R4: 1.01–1.07), not the change. The
change is what the per-pair gate measures, and what moves the harm.

The bilinear identity Z'_vs − Z_vs = x'_vᵀ(A' − A) x_s holds with one solution exact and one
unperturbed. It gives dZ_vs = I'_v jω Φ_s(hop), where Φ_s is the raw flux of x_s along the hop. The
return the short had and the return the hop takes form a closed current, and its coupling is a
potential difference, which is zero. Nothing about the return enters the mutual term.

## 2. The model

The model gives, per connection, at every harmonic:
- I_P, the current each pattern drives through the connection;
- Y, the admittance of the loop it closes;
- that loop's currents l_e;
- x_P° = x_P − (I_P/Y) x_e, the patterns with the connection opened.

The hop's loop is h + Σ β_j r_j with Σ β = 1, made stationary. The trial returns r_j are l_e's own
return (right at low frequency) and a strip's image current in the plane at three widths
(1/π · h/(d² + h²) over the strip, h = 0.5, 1, 2 × the gap). The hop is split over the raster's rows
and placed, like its returns, on the faces toward each other.

    dZ_ks = κ [I_k I_s dZ + jω (I_k Φ°_s + I_s Φ°_k)] − Y κ (jω Φ°_k)(jω Φ°_s),
    dZ = Z_loop − Z(l_e),  κ = 1 / (1 + Y dZ)

For A*, the costs are linear in the path about the straight hop:
- κ₀ is taken from the straight hop's loop.
- The second-order term is linearized. It adds Y jω Φ°₀ to each pattern's hop current.
- The weights multiply the basis's raw flux fields.
- The hop's own self cost and its split rule stay as in kae.em.pnr.

## 3. Checks

[`em_r4b_check`](../../../tools/research/physics/em_r4b_check.py), 0.25 mm. The prediction uses
`kae.em.hopport` on the reduced model of the board before the hop. Each entry is the prediction over
the direct change; the ring is at 130 MHz.

| Case | 1 kHz – 0.3 MHz | 1 – 100 MHz | ring | 160 – 300 MHz |
|---|---|---|---|---|
| victim hop, solid plane | 1.00–1.01 | 1.05–1.07 | 1.10 | 1.07 |
| victim hop, slot under both | 1.00–1.01 | 1.01–1.02 | 1.00 | 1.00 |
| aggressor's own hop, ss, solid | 0.87–1.01 | 0.82–0.98 | 1.17 | 0.91–0.93 |
| aggressor's own hop, vs, solid | 1.00–1.01 | 1.05–1.11 | 1.26 | 1.04–1.07 |
| aggressor's own hop, ss, slot under it | 0.82–0.99 | 0.31–0.74, phase off | 29 | 1.0–1.4 |

- Before, the image-return price gave 0.03–7 for the victim hop, with sign flips.
- The self term across a slot is still wrong: the image returns are placed across the void. The
  router keeps its own split rule for that case.

Boost, `--verify`, 0.5 mm debug run, absolute dL at 10 MHz (it was ~0 or wrong-signed before):

| Net | Pair | Actual (nH) | Predicted (nH) |
|---|---|---|---|
| +3V3 | overshoot | +0.866 | +0.864 |
| +5V | overshoot | +4.55 | +3.36 |
| +5V | cm J2–J3 | −0.73 | −0.71 |
| +5V | cm J1–J2 | +0.54 | +0.48 |
| /VBAT | cm J2–J3 | −0.069 | −0.057 |
| /VBAT | supply:IC1 | +0.033 | +0.035 |

The board's resonance lies just under its 95 MHz limit, and the harmonic-weighted harm u is less well
predicted there (ratios 0.3–1.4).

## 4. Cost

Each upcoming connection adds one right-hand side to every snapshot: boost has 9 patterns plus 1–14
connections.

The greedy first build now uses a 12-point error grid and keeps each point's factorization across
steps (opt-in; at the evaluator's 24 points the factorizations ran past a 40 GB address space). With
6 connection ports it took 1304 s, against 1825 s for the old build with none (8 threads).

Recycled refreshes measured on the loaded host were 3–8× slower than before, everything in the job
alike. That is contention, not the method; a controlled measurement is still to do.

## 5. Open

- The self term across a slot. The image returns should be confined to copper, or the stationary
  set should take returns solved around the slot.
- Harm (u) prediction near the in-band resonance.
- Cost per refresh: drop the connection ports of hops already routed, and lower the probes'
  factorization cost.
