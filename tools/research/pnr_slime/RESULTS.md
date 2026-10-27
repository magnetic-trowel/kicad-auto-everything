<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Physarum network dynamics coupled to part motion (tag `slime`)

## Idea and source
Catalog idea 20 (survey §4): slime-mould networks (Tero et al. 2007/2010; Bonifaci et al.
multi-commodity Physarum). Tubes carrying flux thicken and idle ones decay, so flow networks
thin to near-minimal trees. Every net is a commodity; parts move in response to the flow.

## Mechanism as built (`slime.py`, engine v5)
- **Soft routing**: 0.5 mm grid per layer plus via edges. Per net: conductivities on its
  bounding box + 3 mm, one sparse solve (`splu`) with one RHS per source pin (≤ 6), then
  D ← ½D + ½·f(|Q|)·pen, f = Tero's sigmoid (μ = 2), pen = 1/(1 + β·other nets' tube
  occupancy on that node/layer + history). Conductance scales with each cell's free
  fraction (foreign pad halos, edge, keep-outs → ~0). Plated pads get a free layer change,
  injection goes into one layer and initial D has 30 % noise; without that every net split
  50/50 over both layers. After the fix nets thin to trees on different layers.
- **Part motion** (from `seq`'s placement): each pad pulls along its outgoing tube
  (envelope-theorem force), foreign tube occupancy pushes the body, and optionally
  −phys_w·∇`Phys.delta` (finite differences, 2 mm/unit). Steps are legalized to the nearest
  `Kit.legal_map` origin and kept only if network cost (+ phys_w·physics) drops.
- **Routing**: `Router.pathfinder`, optionally via `PriorRouter`: while net n routes, its
  history cost gets +λ off its dilated final tubes (topology + layer prior).

## What failed
- Unconditional force moves: HPWL +4–8 %, routed length +3–7 %.
- "Best placement by network cost" mostly picked the start, because congestion history
  makes the cost drift up. With history frozen and an accept rule, motion is near a no-op.
- Corridor prior λ = 0.6: +2–8 % length and more vias; λ = 0.2 (default) is about neutral.

## Results (KiCad DRC via harness, 120 CPU-s, -j 1, seed 0; t = mean wall s under load)

**dev6** (length summed over the 4 boards every run completes):

| run | legal | clean | completion | length mm | vias | t (s) |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.667 | 0.667 | 0.904 | 682 | 8 | 45 |
| slime-dev6-motion-v5b (motion only) | 0.667 | 0.667 | 0.904 | 684 | 6 | 84 |
| slime-dev6-prior-v5 (prior only, seq placement) | 0.667 | 0.667 | 0.904 | 685 | 8 | 41 |
| slime-dev6-full-v5b (motion + prior) | 0.667 | 0.500 | 0.908 | 683 | 8 | 92 |

The full method lost xor-2in to `starved_thermal` (the prior routed copper into spoke
room). paw3395, the only congested dev board, stays at 0.68–0.70 completion in every run.

**10 physics boards** (`kae-work/slime-phys11.txt`; place and routed physics × human,
geometric mean, from `pnr_phys/physics_score.py`; length over 5 complete boards):

| run | legal | clean | completion | length | vias | t (s) | place phys | routed phys |
|---|---|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.70 | 0.30 | 0.858 | 1224 | 43 | 78 | 4.05 | 1.39 |
| pnr-seq_phys-v5 | 0.70 | 0.30 | 0.859 | 1260 | 47 | 144 | **1.52** | **1.26** |
| slime-phys11-phys-v5b (seq + slime with physics) | 0.70 | 0.30 | 0.856 | 1214 | 46 | 107 | 3.77 | 1.34 |
| slime-phys11-phys2-v5b (seq_phys + slime with physics) | 0.70 | 0.30 | 0.862 | 1253 | 49 | 111 | 1.53 | 1.30 |

`pnr-anneal_phys-v5` was unfinished. The physics force barely helps (4.05 → 3.77): physics
needs global jumps (a decap to its IC), which `descent_phys`'s coarse map makes and local
force steps do not. On top of `seq_phys`, slime motion adds nothing (1.52 → 1.53 place,
1.26 → 1.30 routed). In dev-driver runs, motion cut unrouted connections on pmw3360 (3 → 0)
and paw3222 (2 → 1). Neither shows in harness completion. I did not run all 33 boards,
because dev6 was not promising; the physics runs cover 10 of the 33.

## Verdict: no merit (as built)
The Physarum solve gives a credible soft routing, but neither transfer channel beats the
controls. The **corridor prior** is neutral at best: negotiated A* already finds what the
tubes encode, and the tubes ignore real clearance and spoke room. **Part motion** worsens
wirelength as a force and is nearly a no-op as an accepted descent; with physics it trails
`seq_phys`.

**Next step**: use the tube overflow only as a congestion predictor (a smooth density
penalty in `seq_margin`/`negotiate`), tested on the 8 boards where `seq` leaves
connections unrouted.

Code: `slime.py` (plug-ins `slime`, `slime_motion`, `slime_prior`, `slime_phys`,
`slime_phys2`). The v5b runs used `kae-work/slime-code/slime_v5b.py`, whose code body is
identical.
