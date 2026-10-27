<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Differentiable joint place-and-route (tag `grad`)

## Idea
Ideas 17, 18, 22 and 23: one energy over continuous poses, with a differentiable routing
term (soft-min DP, perturbed optimizers, DGR, ePlace).

## Mechanism (`grad.py`)
- **Variables:** part origin (x, y) and rotation softmax(β·θ), with β annealed from 1 to 30.
- **Soft routing:** option c (exact gradients, no noisy A* runs).
  - The grid is coarse (0.4–0.8 mm). A cell costs 1 + wb·(pad halos of other nets) + a
    congestion price.
  - Dijkstra (numba) runs from every pin, and each net is an MST over those distances.
  - Connection length is D = d_a(b). Usage ∝ exp(−(d_a+d_b−D)/T), the soft-min
    Bellman–Ford marginal.
  - Forces: ∇d at the pins (envelope tension along the route), plus wb·∇(other nets'
    usage) under each part's halos.
  - Overflow is priced into the next field and also pushes pads ("copper as charge").
- **Placement terms:** overflow-only Poisson density, box penetration, edge penalties.
- **Physics (optional):** phys_w × kae place terms, differentiated by finite differences of
  `Phys.delta`.
- **Schedule:** HPWL (WA) blends into soft routing from 20 % to 50 % of the run. T goes
  from 3 to 0.4 mm and wb from 0.5 to 4. Penalties grow only while needed. Optimizer: Adam
  with noise, for 45 % of the CPU budget.
- **Finish:** nearest legal pose (`Kit.legal_map`), an optional `descent_phys`
  (`post=phys`), then PathFinder.
- **Ablation:** `grad_hpwl` is the same pipeline with HPWL in place of the routing term.

**Fixes made along the way:**
- The full ePlace charge over-spread sparse boards (2–3× HPWL).
- Overlap area gives no force on contained boxes; penetration depth replaced it.
- Unbounded penalty growth froze layouts.
- Soft routing from t = 0 was dominated by blockage noise.
- Gradient refinement of seq's placement made it worse.
- Legalization erased physics gains until a discrete physics descent was added after it.

## Results (engine v5, 120 CPU s, k = 1)
All 33 boards. Length is summed over the 19 boards that every run completed.

| run | legal | clean | completion | length mm | vias | wall s |
|---|---|---|---|---|---|---|
| pnr-seq-v5 | 0.788 | 0.545 | 0.863 | 2927 | 36 | 58 |
| pnr-grow-v5 | 0.788 | 0.545 | 0.861 | 2880 | 28 | 74 |
| **grad** | 0.848 | 0.545 | 0.869 | 3357 | 38 | 127 |
| grad_hpwl | 0.879 | 0.485 | 0.860 | 3132 | 33 | 128 |

Physics on the 10 physics boards (`physics_score.py`, × human, geometric mean):

| run | place total | capped-u (worse/better) | routed | completion |
|---|---|---|---|---|
| pnr-seq-v5 | 4.05 | 1.45 (8/1) | 1.39 | 0.858 |
| pnr-seq_phys-v5 | 1.52 | 1.20 (5/4) | 1.26 | 0.859 |
| grad / grad_hpwl | 6.56 / 4.38 | 2.01 / 1.64 | 1.83 / 1.86 | 0.867 |
| grad_phys | 2.85 | 1.53 (8/1) | 1.69 | 0.852 |
| **grad_phys post=phys** | **1.37** | **1.08 (3/6)** | **1.00** | 0.837 |

`anneal_phys-v5` was still incomplete, so it is not compared.

## Do routing gradients beat HPWL gradients?
- **End to end:** the routing term gives +2 clean boards, +0.009 completion, 7 % *more*
  length and worse physics. In-process dev6 runs (3 seeds, 500 iterations each) put soft
  routing ahead in 7 of 18 pairs, with a cost ratio of 1.017. That is noise.
- **Direction test (`gradcheck.py`, 31 boards):** from seq's placement, each part was moved
  0.5–2 mm along a direction and the affected nets re-routed.

  | direction | share of cost-changing moves that improved |
  |---|---|
  | HPWL | 36 % |
  | full soft route | 33 % |
  | tension only | 43 % |
  | random | 19 % |

  HPWL beat the full soft route 315 to 231 in paired moves. Tension carries some
  information beyond HPWL; the halo forces add noise. (The start is an HPWL optimum.)

## Verdict
- **No merit** for differentiable routing as a placement driver here.
  - The soft-routing gradient does not beat HPWL.
  - The analytic placer loses 7–15 % routed length to greedy plus descent.
  - These boards route at about HPWL, leaving little to fix.
- **Inconclusive but promising** for physics. Continuous placement with the physics term
  plus `descent_phys` gave the best physics seen, against seq_phys:
  - capped-u 1.08 vs 1.20;
  - routed physics 1.00 vs 1.26;
  - completion 0.837 vs 0.859.

  One seed, 10 boards.
- **Next step:** drop the routing term. Run `grad_hpwl_phys post=phys` on phys10 with 3
  seeds against seq_phys and anneal_phys, to separate the effect of the physics gradients
  from that of the smooth start.
