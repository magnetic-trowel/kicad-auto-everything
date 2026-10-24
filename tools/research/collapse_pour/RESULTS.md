<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# collapse_pour: minimal-partition pours (status: partial; batch3 running)

## Final results (batch3, corrected metric; added by the lead)

Full output: [summary-final.md](summary-final.md).

- **Verdict: no merit as a pour objective.**
  - Over 21 pour nets on 6 boards, the minimal partition's effective resistance relative to
    the human pours is a geometric mean of 1.045 in fill mode (better on 6, worse on 5),
    1.033 at equal area (better on 4, worse on 8), and 1.011 with the octagon kernel over 11
    nets.
  - Kobold, after the connectivity fixes, is still clearly worse. It leaves 17–18 unconnected
    items against 0 for the human board, and the 105 clearance errors are the same as on
    the refilled human board. RGB_PWR R_eff is 35–49 against 22.
  - Olimex fill mode: /SW −5%, GND tie.
- **Synthetic geometry converges to theory:** junction angle error falls from 3.3° to 0.45°
  as the grid is refined; contact with the rim is 89.6–89.7°; the octagon kernel gives the
  Wulff octagon (81–91% of the boundary within 5° of the facets).
- **Placement study** (80 board × placement × pour-net rows):
  - `pour_score` follows the full Laplace R_eff at Spearman 0.48 in absolute terms, but only
    0.21 as a ratio to human.
  - Full pour R_eff, as a ratio to human, follows kae routed physics at 0.65; `pour_score`
    follows it at 0.11.
  - combo's placements give better pours than the human ones (geometric mean R_eff 0.897
    over 15 boards). seq's give worse (1.088).


Idea: [layer-collapse](../../../docs/ideas/original/layer-collapse.md). When several pour
nets share a layer, the split boundaries should form a minimal partition: constant-curvature
arcs, 120° junctions, 90° at a free edge, octagonal Wulff cells for 0/45/90° copper. Here
that partition is computed with MBO threshold dynamics and compared with the human split
planes on DC conductance.

## Code
- `mbo.py`: multiphase Esedoglu–Otto MBO. Volume targets are met exactly by coordinate
  ascent on the multipliers λ. Pads are pinned cells, islands without a pin are dropped,
  and each phase has its own allowed mask for clearance. Two kernels: a Gaussian (Wulff
  shape = disc), and an "octagon" kernel made of four 1-D Gaussians along 0/45/90/135°
  (σ_K is a zonotope norm, so the Wulff shape is a regular octagon).
- `synth.py`: analytic checks. `geom.py`: measurements.
- `kicad_dump.py` (pcbnew): dumps board geometry and fills, and writes MBO zones as
  copies of the human zones with new outlines, then refills them.
- `board.py`: real boards. Human placement and routing stay as obstacles. Areas are
  calibrated against the KiCad fill, the result is written back, and KiCad DRC checks it.
- `netcond.py`: whole-net Laplace resistance between pads. All layers are included, vias
  conduct 0.5/sq, and the result is in squares.
- `pour_place.py`: `pour_score(world)`, a cheap placement term, plus a placement study.
  `summarize.py` builds the tables.

## Analytic checks (`synth_results.json`, `fig/synth.png`)
| case | measured | theory |
|---|---|---|
| double bubble, radii (cells) | 64.95 / 52.96 / 329 | 64.71 / 52.20 / 270 |
| double bubble, junction angles | 116.7–123.1° | 120° |
| curvature additivity k02−k12+k10 | −3e−4 (k ≈ 0.016) | 0 |
| Laplace law Δλ = σ_K κ, σ_K = s/√(2π) | κ 0.0171/0.0198 vs fit 0.0157/0.0197 | equal |
| triple bubble, junctions | centre 119.0–120.6°, outer 118.0–123.5°; inner edges straight | 120°, straight |
| 3 phases in a disc (0.5/0.3/0.2) | junction 118.8–122.2°, rim contact 88.3–89.6° | 120°, 90° |
| quarter disc in a corner | r = 88.8–91.0 | 90 |
| Wulff, octagon kernel | apothem 77.0 (0/45/90/135°), circumradius 81.9; 81% of boundary within 5° of a facet | 76.9 / 83.2 |
| Wulff, Gaussian kernel | 78.0–78.9 in every direction (disc) | disc |

Caveats:
- MBO pins on the grid. From a poor start it stalls near a state whose energy is only
  0.03% above the optimum, but with junction angles off by up to 9°. Starting from the
  theoretical double bubble it holds 120 ± 0.8°. A wide initial kernel (s0 = 40 cells,
  annealed to 5) removes most of the error.
- With the octagon kernel the square start stays a square (facets are immobile), and the
  disc start gives the octagon.

## Real boards (KiCad-refilled fills; DRC errors: 0 for human and for every MBO board)
"Iso-area" means each net gets the human copper area after calibration. "Fill" means the
largest pour takes every cell it can legally use and the smaller pours keep the human
area. R = mean pad-pair resistance in squares; lower is better.

| board, net | human R / Cu mm² | MBO iso-area (iso kernel) | MBO iso-area (oct) | MBO fill (iso) |
|---|---|---|---|---|
| olimex dcdc 4L, /SW (F.Cu split with GND) | 1.028 / 114 | 1.125 / 96 | 1.124 / 96 | **0.980** / 113 |
| olimex, GND (whole net, 4 layers) | 1.826 / 3973 | 1.864 / 3950 | 2.136 / 3954 | 1.823 / 3977 |
| olimex F.Cu GND, layer-only R | 7.84 / 918 | 7.66 / 918 | – | 7.66 / 922 |
| olimex B.Cu GND alone (control) | 1.55 / 1449 | 1.67 / 1426 | – | 1.55 / 1449 (identical) |

Figures are in `fig/olimex-dcdc-50-5-12-dcdc-50-5-12-rev-a1_*_{iso3,fill4,iso_area}.png`.
The kobold In1 4-rail split, xerxes In2 5-rail split, oasis, bentwire, pi5-pcie,
caffeinated, libresolar and the fill runs are still in the tmux `pour` batch
(`kae-work/pour/batch1.sh`). After it finishes, `python summarize.py` prints the full table.

What olimex shows so far:
- With a single GND pour, the minimal partition has nothing to decide. Fill mode
  reproduces the human pour exactly. Iso-area mode moves the unpoured area somewhere else
  and loses 3–8% of conductance.
- With a split layer at equal area, conductance changes only within ±10%. The fill
  variant beats the human /SW island by 5% at the same copper. The octagon kernel is
  never better than the isotropic one.
- What counts for conductance is where the copper lies relative to the pads. The length
  of the boundary is secondary. The perimeter objective does not know where the pads are,
  so a "minimal" free region can land between pads.


## Kobold 4-rail split (In1.Cu) — the counter-example
The human In1 is a comb: RGB_PWR fingers run between rows of +3.3V LED pads
(`fig/pcbcorpus-tzarc-keyboards-kobold_In1.Cu_iso_area2.png`). The minimal partition turns
the comb into blobs, and RGB_PWR loses pads. Bridges added by `repair_connectivity` are
thinned away by KiCad's fill. Result at equal copper:
- 18 to 21 unconnected items (the human board has 0);
- whole-net R_eff for RGB_PWR 81 squares against 36;
- +3.3V 20.1 squares against 16.8.

The 105 clearance errors are not caused by the pours: the refilled human board has the
same 105, and they are excluded. The reference `drc.json` (pre-refill) has none.

When the pads of two rails interleave, the boundary has to be long, so minimal perimeter
is the wrong objective.

Fixes made, rerunning in `kae-work/pour/batch3.sh` with tags `iso_area2`/`fill2` and
`place2.json`:
- (a) disconnected pairs count as zero conductance: `R_eff = 1/mean(1/R)`, plus the number
  of cut-off pads;
- (b) bridges keep the terminals the human pour connects on that layer connected;
- (c) PTH pads are dumped on unflashed layers too;
- (d) the kernel is annealed from 4 mm.

`summarize.py` builds the tables, including the placement-term correlations against full
R_eff, the kae fast and routed physics, worst-rail mOhm, length and vias (all read from
`kae-work/phys/*.json`).

## Verdict (provisional)
**No merit as a pour objective on real boards.** Minimal partitions reproduce the soap-film
geometry. On real boards they tie the human pours where there is one GND pour, change
things by ±5–10% on a two-pour layer, and are clearly worse on an interleaved multi-rail
plane. Conductance-aware shapes need a pad-aware term rather than perimeter.

## Placement → pour quality (asked by the lead; running)
`pour_score(world)` predicts each pour net's mean pad-pair resistance as follows:
- Start from the ideal sheet: R_ij = [ln(d/a_i) + ln(d/a_j)]/2π, where d is the pad
  distance and a the pad radius.
- Divide by the free fraction of the band along i–j on the zone layers. A cell is not
  free if it is inside another net's halo (World.DT − own occT), so the routes count too
  once the router has stamped them.
- The total is the sum over pour nets of the mean predicted R. It costs a few ms and is
  meant for use inside the placer.

`pour_place.py` runs the full Laplace metric and the cheap term on the human board and on
the attempt-0 boards of pnr-seq-v5 and pnr-combo-v5, for all 17 A/B boards with zones
(queued as tmux `pour2`, output to `kae-work/pour/place.json`). `summarize.py` then reports
the Spearman correlation and the agreement in pairwise ranking. Pilot result
(pcbcupid, GND):

| | human | seq | combo |
|---|---|---|---|
| full R | 1.68 | 1.21 | 1.78 |
| pour_score | 0.60 | 0.50 | 0.56 |

On the pilot, 2 of the 3 pairwise orders agree.

## Verdict so far
- The solver reproduces the minimal-partition geometry to within a few degrees and
  percent.
- On real boards, the minimal partition does not clearly beat human split planes on
  conductance per copper area. It is about equal, ±10%.
- It helps only where several rails share a layer and the human islands are irregular.
- It changes nothing for a single GND pour.
- Next step: replace the perimeter term with a conductance-aware term (a pad-weighted
  geodesic distance, or a Laplace shape gradient) inside the same MBO loop.
