# Analytical / differentiable placement (Cypress, DREAMPlace, custom JAX/PyTorch losses)

**TL;DR**
- The proven scalable PCB approach is analytical placement; **Cypress** (NVIDIA/Cornell, ISPD'25, Apache-2.0) is DREAMPlace adapted to PCBs and demonstrated from 41 to 6,628 components.
- Its validated terms: orientation-aware LSE wirelength, **two-sided electrostatic density** (sides pre-assigned), **differentiable net crossing** (Bézier parameters through bell functions), **Gumbel-Softmax orientation** optimized bi-level, MOTPE tuning against Freerouting routability.
- Domain terms (decap distance, hot-loop area, keep-out/outline SDF, thermal spreading, RUDY congestion) drop in as penalties; discrete decisions (side, final orientation, legality) still need a discrete legalizer.
- For 20–1000 parts, a lean JAX/PyTorch reimplementation of Cypress's ideas is likely better than DREAMPlace's CUDA build (pinned to Python ≤3.9, PyTorch ≤2.0, GCC 7.5) [I].

## Key facts

**Cypress** (Zhang, Agnesina, Shbat, Leader, Z. Zhang, Ren; ISPD'25; [slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf), [repo](https://github.com/NVlabs/Cypress) [P])
- Scope: surface-mount, non-critical parts on rectilinear boards, top/bottom, **sides pre-assigned**; constraints spacing, non-overlap, fixed critical/mechanical parts.
- Net crossing: each net decomposed into source → sink pin pairs; for two same-layer pairs compute Bézier intersection parameters t, u (intersection iff both in [0, 1]); pass each through a bell function, multiply, sum; side-aware via `pin_side` (default on).
- Orientation {N, E, S, W} via Gumbel-Softmax on `orient_logits` with a separate Adam optimizer; bi-level (fix one of position/orientation while optimizing the other); `enable_rotation` defaults to 0 in code.
- Density: separate top/bottom electric-potential maps and overflow; RUDY-guided area adjustment; RMST wirelength op; legalization per side (Tetris → Abacus; macro, greedy).
- Tuning: MOTPE multi-objective BO in parallel across GPUs (code also has BOHB via hpbandster) over initial position [0.2, 0.8], density weight [1e-6, 1], target density [0.1, 1], net-crossing weight [1e-6, 1], LSE γ [0.1, 0.5], learning rate [1e-4, 1e-2], optimizer {Adam, Nesterov}; configspace also bins 256–1024, WA/LSE, RISA weights, stop_overflow, macro halo ([pcb-configspace.json](https://github.com/NVlabs/Cypress/blob/main/test/tune/pcb-configspace.json)).
- Evaluation: Freerouting v1.9.0, 2 free copper layers, routability = % routed pin pairs. Benchmarks small-1…10 (41–476 parts, 85–5,334 pins) and big-1…5 (5,118–6,628 parts, 1,293–2,152 movable); converters from KiCad and NS-Place.
- Results: routability up to 1.2× SA-PCB, 5.9× NS-Place, 1.6× NS-Place+; up to 492.3× faster than SA-PCB, 329.7× than Quilter; 200–1,765 s on 4 V100s incl. exploration; big-benchmark ablation: + net crossing → HPWL 1.13, crossings 0.31; + orientation → HPWL 1.05, crossings 0.27 (crossing alone worsens WL). Independent OmniLayout RR 0.33.

**DREAMPlace** (BSD-3; [repo](https://github.com/limbo018/DREAMPlace) [P]): >30× vs CPU RePlAce on ISPD05; ABCDPlace ~16× vs NTUPlace3; ops `weighted_average_wirelength`, `logsumexp_wirelength`, `electric_potential` (DCT Poisson per ePlace), `rudy`, `pinrudy`, `abacus_legalize`; defaults γ 4.0, density_weight 8e-5, target_density 0.8, stop_overflow 0.1; RUDY/RISA area adjustment (`adjust_rudy_area_flag`). AutoDMP adds multi-objective BO ([bayesian tuning](bayesian-tuning.md)).

**Other analytical PCB placers**: NS-Place (GD with momentum α=1e-3, λ_NS=λ_D=1, SVM net-separation margin, MILP legalization); PA-ICM (conjugate subgradient + distribution EA); Chen DAC'25 (power/signal wire-area, pad-type two-sided density); Zhao 2025 (joint rotation) — see [PCB placers](../placement/pcb-placers-2022-2026.md). Apollo (photonics) reports routability 94.79% vs DREAMPlace 50.85% and Cypress 51.38% on its domain — wirelength/density placers can score low on routability [S]. torch 2.14.1 and jax 0.12.0 are Apache-2.0.

**Formulation B — differentiable loss with domain terms** (JAX-style pseudo-code from [solver_toolbox.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)):
```python
def loss(params, key, k):                                 # k = continuation step; side is a FIXED input
    xy, logits = params["xy"], params["orient_logits"]
    p = jax.nn.gumbel_softmax(key, logits, tau=tau(k))
    pin = xy[pin2comp] + jnp.einsum("pk,pkd->pd", p[pin2comp], pin_off_rot)   # 4 precomputed rotations
    WL  = sum_nets(w_n * (wa(pin_x, g(k)) + wa(pin_y, g(k))))                   # weighted-average smooth HPWL
    OVL = soft_pair_overlap(xy, p, cand_pairs)            # or two-sided electrostatic density
    NC  = net_crossing(pin, same_layer_pairs)             # Cypress bell(t)*bell(u)
    KO  = (relu(clear - sdf_keepout(corners(xy, p)))**2).sum()
    OUT = (relu(sdf_outline(corners(xy, p)) + margin)**2).sum()
    DEC = sum(relu(norm(pin[c] - pin[i]) - dmax)**2 for c, i, dmax in decaps)
    LOOP= sum(tri_area(pin[vdd], pin[cap], pin[gnd]) for hot_loops)
    TH  = sum(P[i]*P[j] / (sqdist(xy[i], xy[j]) + eps) for hot_pairs)
    CONG= (relu(rudy(pin, nets) - cap_map)**2).sum()
    return WL + lam_d(k)*OVL + lam_nc*NC + lam_k*KO + lam_b*OUT + lam_dec*DEC + lam_l*LOOP + lam_t*TH + lam_c*CONG
# bi-level: alternate Nesterov/Adam on xy and Adam on logits; ramp lam_d (ePlace-style);
# then argmax orientations -> CP-SAT legalization (min displacement, hard decap/keep-out) -> SA/LNS detail
```

**Transplant terms** [I]: VeoPlace weak anchors λ_A·Σ‖x − x̂‖² (λ_A = 0.01) for LLM/VLM regions ([LLM-guided](../placement/llm-guided-placement.md)); NTU power-flow anchors; centroid-direction no-overlap gradient + repel-then-no-repel schedule ([scene transplants](../placement/scene-layout-transplants.md)); TRouter-style differentiable thermal surrogate; Qplacer frequency-aware repulsion for aggressor/victim pairs; CoEvoP&R-style LLM-evolved objective over a restricted observable API ([LLM-evolved heuristics](llm-evolved-heuristics.md)).

## Recommendations for our system
- Global placement for 100–1000 parts: Cypress-style JAX/PyTorch loss with Gumbel orientation, two-sided density, net crossing and domain penalties; or Cypress itself (Apache-2.0, GPU) as reference [I].
- Decide sides upstream (rules, LLM relation `side(part, bottom)`, or a small CP-SAT decision) as Cypress assumes [I].
- Expose loss weights as the LLM's "knob surface"; tune with MOTPE against Freerouting RR on calibration boards ([bayesian tuning](bayesian-tuning.md)) [I].
- Always follow with an exact legalizer and detailed placement; GPU unnecessary at our sizes [I].

## Conflicts and open questions
- Cypress full paper unreachable (TLS chain, ACM 403): exact Gumbel schedule, legalizer details and per-benchmark tables missing; benchmark files not inspected (Bookshelf-like `.aux`).
- No published differentiable formulation of decap-loop or thermal terms for PCBs.
- Cypress award status (nominee vs winner) conflicts.

## Sources
- research notes: [solver_toolbox.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [placement_algorithms.md § Q1, Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [verification_papers.md § 2.5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [placement/pcb-placers-2022-2026](../placement/pcb-placers-2022-2026.md) · [cp-sat-milp-smt](cp-sat-milp-smt.md) · [recommended-stack](recommended-stack.md)
