# Congestion forces on parts: pin tension, bloating, soft-route gradients, Physarum

**Status:** did not work (tension, bloat, Physarum); soft-route gradients did not work as a driver but `grad_phys post=phys` is a partial result for physics.
**First published:** 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6` (tension, bloat); [6e5c658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6e5c658f0ea7c268fe8d44682160bf7a820b4d4b) (grad, Physarum; results [aa741a1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/aa741a14eadb45994fbb2b766997b61c5b273871), [4570654](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4570654c232260243ba594c722365b0394181fff)).

Scope: four ways to turn routing information into a continuous push on parts. All numbers v5 era (place tasks, 120 CPU-s, **1 seed**; [eras](README.md#eras-and-caveats)); `seq` / `seq_phys` reference values → [sequential-controls.md](sequential-controls.md#results), [physics-objective.md](physics-objective.md#results). Not here: harmonic fields, the potential-flow cousin of Physarum -> [jc-extensions.md](jc-extensions.md#harmonic-field-routing-and-field-pressure).
Keys: pin tension, envelope theorem, bloat, SimPLR, soft routing, soft-route gradient, grad, grad_hpwl, grad_phys, `post=phys`, direction test, gradcheck, Physarum, slime mould, Tero, copper as charge, ideas 2 3 17 18 20 22 23 26

Shared lesson: on boards that route at about HPWL length, the routing signal adds more noise than information [I].

## Pin tension (ideas 2, 3, 26)

**Mechanism** (`methods.py:tension`, `pin_tensions`). Route the board. Envelope theorem: ∂(routed length)/∂(pin position) = unit vector from the pad toward its track ~1 mm away = the pin's tension. Add the downhill direction of the congestion price (Lagrange multiplier) under the part's courtyard. Move the part along the summed force, pick the rotation whose pins best face their tensions, re-route touched nets, keep the best board.

**Results** ([drc-objectives-v5.md](../../../tools/research/pnr/results/drc-objectives-v5.md), [physics-objectives-v5.md](../../../tools/research/pnr/results/physics-objectives-v5.md)): legal 0.788, clean 0.545, completion 0.871 (`seq` 0.863); place physics 4.23× human, routed 1.41×.

**Verdict: did not work.** Some signal in the direction test (43% of moves improved vs 36% HPWL), but as a driver it equals `seq`.

## Bloat (SimPLR-style inflation)

**Mechanism** (`methods.py:bloat`). Route; parts near failed or detoured nets get an inflated keep-out; re-place by HPWL descent; re-route; keep the best.

**Results:** legal 0.727, clean 0.576, completion **0.748** (vs 0.863); on phys10 placements on only 6 of 10 boards, place physics 12.05×.

**Verdict: did not work.** Inflation pushes parts outward until dense boards no longer fit.

## Soft-route gradients (ideas 22, 23, 17)

**Mechanism** (`pnr_grad/grad.py`).
- Variables: part origin (x, y); rotation as softmax(β · θ) over 4 rotations, β annealed 1 → 30.
- Soft routing on a coarse grid (0.4–0.8 mm): cell cost 1 + wb · (pad halos of other nets) + congestion price; numba Dijkstra from every pin; each net an MST over those distances; connection length D = d_a(b); soft usage of a cell ∝ exp(−(d_a + d_b − D) / T) (soft-min Bellman–Ford marginal).
- Forces: ∇d at the pins (envelope tension along the route) + wb · ∇(other nets' usage) under each part's halos. Overflow priced into the next field pushes pads ("copper as charge", idea 18).
- Placement terms: overflow-only Poisson density, box penetration depth, edge penalties; optional physics by finite differences of `Phys.delta`.
- Schedule: weighted-average HPWL blends into soft routing from 20% to 50% of the run; T 3 → 0.4 mm; wb 0.5 → 4; Adam with noise for 45% of the budget. Finish: nearest legal pose, optional `descent_phys` (`post=phys`), PathFinder. Ablation `grad_hpwl`: HPWL instead of the routing term.
- Fixes along the way: full ePlace charge over-spread sparse boards (2–3× HPWL); overlap area gives no force on contained boxes (replaced by penetration depth); unbounded penalties froze layouts; soft routing from t = 0 was dominated by blockage noise; legalization erased physics gains until a discrete physics descent was added after it.

**Direction test** (`gradcheck.py`, 31 boards): from `seq`'s placement each part moved 0.5–2 mm along a direction, affected nets re-routed. Share of cost-changing moves that improved: HPWL 36%, full soft route 33%, tension only 43%, random 19%. HPWL beat the soft route 315 to 231 in paired moves.

**Results** ([pnr_grad/RESULTS.md](../../../tools/research/pnr_grad/RESULTS.md)):

| run | legal | clean | completion | length mm | place φ × human | capped-u | routed × human |
|---|---|---|---|---|---|---|---|
| seq | 0.788 | 0.545 | 0.863 | 2927 | 4.05 | 1.45 | 1.39 |
| grad | 0.848 | 0.545 | 0.869 | 3357 | 6.56 | 2.01 | 1.83 |
| grad_hpwl | 0.879 | 0.485 | 0.860 | 3132 | 4.38 | 1.64 | 1.86 |
| **grad_phys post=phys** (phys10) | — | — | 0.837 | — | **1.37** | **1.08** | **1.00** |

**Verdict: did not work as a driver; partial for physics.** The routing gradient does not beat HPWL; the analytic placer loses 7–15% routed length to greedy + descent. Continuous placement with the physics term + `descent_phys` gave the best routed physics of the v5 era (1.00× human; `seq_phys` 1.26×), at lower completion; 1 seed, 10 boards. Merit arm: `grad_phys --opt post=phys`.

## Physarum networks (idea 20)

**Mechanism** (`pnr_slime/slime.py`).
- Soft routing: 0.5 mm grid per layer + via edges. Per net, conductivities D on its bounding box + 3 mm; one sparse LU (`splu`), one right-hand side per source pin (≤ 6); update D ← ½ D + ½ f(|Q|) · pen, f = Tero's sigmoid (μ = 2), pen = 1 / (1 + β · other nets' tube occupancy + history). Conductance scales with each cell's free fraction. Plated pads give a free layer change; injection into one layer and 30% noise on initial D break layer symmetry (otherwise every net split 50/50 over both layers).
- Part motion (from `seq`): pads pull along their outgoing tubes, foreign occupancy pushes the body, optionally −`phys_w` · ∇physics; steps legalized and kept only if network cost drops.
- Routing prior: +λ history for net n off its dilated final tubes (λ = 0.2 default).

**Results** ([pnr_slime/RESULTS.md](../../../tools/research/pnr_slime/RESULTS.md)):
- dev6: motion, prior and full equal `seq` (completion 0.904–0.908, length 683–685 mm) or worse (full lost a clean board to `starved_thermal`).
- phys10: seq + slime with physics, place physics 3.77 vs 4.05; on top of `seq_phys` 1.53 vs 1.52, routed 1.30 vs 1.26.
- Unconditional force moves: HPWL +4–8%, routed length +3–7%; λ = 0.6: +2–8% length. Not run on all 33 boards.

**Verdict: did not work.** Credible soft routing, but negotiated A* already finds what the tubes encode, and the tubes ignore real clearance and spoke room. Proposed (not done): tube overflow as a smooth congestion predictor only.

## Open questions

- `grad_hpwl_phys post=phys` over 3 seeds, to separate the physics gradient from the routing term (not done).

## Code

- [`tools/research/pnr/methods.py`](../../../tools/research/pnr/methods.py): `tension`, `pin_tensions`, `bloat`.
- [`tools/research/pnr_grad/`](../../../tools/research/pnr_grad/): `grad.py` (`grad`, `grad_hpwl`, `grad_phys`), `gradcheck.py`.
- [`tools/research/pnr_slime/slime.py`](../../../tools/research/pnr_slime/slime.py) (`slime`, `slime_motion`, `slime_prior`, `slime_phys`, `slime_phys2`).

## Related

[sequential-controls.md](sequential-controls.md), [physics-objective.md](physics-objective.md).
