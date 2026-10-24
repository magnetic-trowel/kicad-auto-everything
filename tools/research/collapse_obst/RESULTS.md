<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Layer-collapse obstructions: do analytic bounds predict layer count? (`obst`)

## Method

112 boards, human placement. Pitch p = w + c from the board rules (thinnest routed track if
the rule is 0). Code: `obst.py`, `run_all.py`, `report.py`, `placements.py`, `placecost.py`.

- **Capacity (sound):** nets with pads strictly on both sides of a cut must cross it, so
  N(γ) ≤ Σ_l ⌊(ℓ_free,l + c)/p⌋. Pads block their own layers (inscribed disc), through-hole
  pads all layers. Cuts: 24k straight chords, grid circles, and rings around every part through
  each pad row and outward. Vias and keep-outs are ignored (sound but weaker).
- **BGA escape (formula, not a bound):** t = ⌊(P − D − c)/p⌋ tracks per channel → t+1 rows on
  top, t_in+1 per further layer (dog-bone via diameter).
- **Topology:** with vias any netlist fits on 2 layers, so only planar vs not matters; Euler
  bounds are 1 on 106/112 boards.
- **Area:** 0.824·MST·p plus pad area must fit in L·A.
- Net sets: all, and "nopour" (zone nets removed). Planes: inner layers ≥ 60% covered by one
  net's zones; signal layers = L − planes.

## Predicted vs actual (human placement, all nets)

Predicted = max(side, topology, cut, area, escape).

| actual \ predicted | 1 | 2 | 3 | 4 | 5 | 7 |
|---|---|---|---|---|---|---|
| 2 (74) | 18 | 55 |  |  | 1 |  |
| 4 (28) | 2 | 25 | 1 |  |  |  |
| 6 (7) |  | 6 |  | 1 |  |  |
| 8 (3) |  |  |  | 1 | 1 | 1 |

Against total copper: equal 55, below 56, above 1. Against signal layers: equal 79, below 27, above 6. Without escape, the sound bounds are never above actual and never above 2: equal 56, below 56.

**Which bound binds:**
- The capacity cut forces 2 layers on 2 boards and never 3.
- Local demand (crossing nets × p / free length) has medians of 0.14, 0.28, 0.29 and 0.87 layers for 2-, 4-, 6- and 8-layer boards. The maximum is 1.19, on a ring at a 0.5 mm BGA (ping-dev-kit).
- Every prediction above 2 comes from the escape formula. On the 7 fine-pitch BGAs it lands within ±1 of the signal-layer count, 3 times exactly one above: obsidian 5 vs 4, ping 7 vs 6, kintex 4 vs 3. Humans beat dog-bone fanout, so the formula is not a lower bound.
- Signal layers are 2 on 102/112 boards. A 4-layer board here is 2 signal layers plus a median of 2 inner planes.
- For 4+ vs 2 layers, max demand has AUC 0.77, no better than pad density (0.79).

Heat maps (max demand over local cuts through each cell), all in `heatmaps/`:
- `heatmaps/bluerobotics-ping-dev-kit-pingdevkit.png`
- `heatmaps/berkeleylab-obsidian-obsidian.png`
- `heatmaps/kicad-demos-video-video.png`
- `heatmaps/pcbcorpus-rniwase-tsuraragb-tgb-main.png`

## As functions of placement (33 boards, attempt-0)

| placement | unrouted (probe) | median max demand | boards above human | mean cuts with d ≥ 0.5 |
|---|---|---|---|---|
| human | 0 | 0.12 | – | 0.5 |
| pnr-seq-v5 (31) | 9 | 0.10 | 13 | 0.3 |
| pnr-combo-v5 (31) | 7 | 0.08 | 12 | 0.0 |

No capacity overflow that the human placement avoids: Spearman(our/human demand, unconnected)
= 0.14 (p = 0.44) seq, 0.00 combo. The one overflow is an illegal seq placement (overlapping pads).

Maps: `heatmaps/pcbcorpus-badjeff-paw3395-pcb-paw3395-placements.png`, `heatmaps/pcbcorpus-electron271-tuxkeychain-expansion-placements.png`.

**Bus orientation** (part pairs joined by ≥ 4 two-pin nets; LDS of the pin permutation =
via-free layers, λ1+λ2 = nets that fit via-free on 2 layers; 16 rotation pairs, positions fixed):
- Human, 240 buses on 55 boards: the human rotation pair is LDS-optimal for 60% of buses, against 42% for a random pair. Rotation could cut the forced 2-layer jumpers from 209 to 78.
- Ours, 8 buses: optimal for 50% (human 56%). Seq is worse than human on 2 buses and better on 3; combo is worse on 3 and better on 3.

Placer API (`placecost.py`, pnr `World`): `capacity_overflow(world, circles=False)` (~3 ms on
small boards), `bus_pairs(world)`, `bus_lds(world, a, b, rot_a, rot_b)`.

## Verdict

The bounds are sound but loose, so they cannot predict layer count. On these boards, layers are set by:
1. Planes (power, SI, cost): the extra layers of 4-, 6- and 8-layer boards are mostly planes.
2. Fine-pitch BGA escape: the only analytic quantity that tracks signal layers, to ±1.

Capacity is never binding: even 8-layer boards need ≤ 1.2 layers at their worst cut. As a placement cost, capacity does not explain our routing failures, which must be local (pin access, detours, the router). Bus LDS is a cheap orientation tie-breaker. Humans follow it only weakly.

## Next step

1. Replace single cuts with a multicommodity-flow congestion bound on the pad Delaunay graph, with vias, restricted to the windows around our unconnected nets. Check whether the failures are pin-access obstructions that the human placement does not have.
2. For BGA boards, use the escape row count as a layer and fanout prior for the router.
