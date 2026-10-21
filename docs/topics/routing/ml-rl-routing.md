# ML/RL routing (DeepPCB, FanoutNet, MCTS, learned schedules) and transferability

**TL;DR**
- ML that works on PCBs either **learns a decision a classical router consumes** (fanout locations: FanoutNet; net order: DreamerV3+FR; cost maps: Ranking Cost; search regions: Unet-Astar) or trains a **compact policy over engine actions** (PCBWorld PPO on KiCad PNS).
- **DeepPCB** (commercial RL) reports the top one-attempt PCBWorld-Bench scores (0.929 / 0.800) — vendor-run, mostly 2-layer, and it excludes DDR, length matching, impedance, RF and complex BGA fanout.
- The **DATE'23 polygon-partition MCTS router** routed 10/10 real 2-layer boards (FreeRouting and DeepPCB 8/10) and guarantees global ⇒ detailed feasibility by re-partitioning after each net.
- VLSI generative routers (HubRouter, NeuralSteiner, DSBRouter, GPCB) transfer poorly; **GPCB scored 0.69% NRR on OmniRouting's real boards** vs PcbRouter 56.2%.
- Highest transfer: learned control of classical routers (cost schedules: 1.56–3× faster; −92% DRVs in VLSI).

## Key facts

**DeepPCB (InstaDeep / BioNTech)**
- Training: custom C++ simulator; Sebulba actor/learner on Cloud TPUs, **15–235×** throughput; full run ~24 h/$260 on GPU → 6 min/$20; PPO for Atari validation; Ray/KubeRay on GKE via AIchor ([InstaDeep](https://instadeep.com/2023/10/reinforcement-learning-on-google-cloud-tpus-to-improve-deeppcb/) [P]).
- Platform: cloud jobs for placement, routing or both within a time budget; internal board (444 airwires, 2 layers) >50% fewer vias over a year; DRC, clearance matrices, diff pairs, plane area maximization; API ([blog](https://deeppcb.ai/bringing-ai-and-cloud-to-pcb-routing/) [P]).
- Product (Oct 2026) [V]: "seven years of RL R&D … NeurIPS and ICML" (unverified; no routing paper found); **Cooper** setup agent reports stackup, classes, pairs, planes, clearances and takes plain-language setup; workflow "critical nets were routed by hand first and the engine finished the rest"; **not for DDR, length matching, advanced impedance, RF**. KiCad plugin (Apache-2.0, [repo](https://github.com/instadeepai/deeppcb-kicad-plugin)) uploads board/rules (optionally schematic) to `api.deeppcb.ai`, result as one undo commit; signals, diff pairs, blind/buried, 8 layers; completion falls past ~1,200 airwires; free tier 30 min/4 layers/150 airwires; public cap 1,000 components/2,200 pins (Quilter blog).
- **PCBWorld-Bench self-evaluation** (2026-09-28) [V]: standard model, one attempt, no tuning: **D3-A 0.929 (92/99), D3-B 0.800 (24/30; 95% CI 0.627–0.905)** vs paper @1 PPO-w/o-finish 0.81 and Freerouting 0.64; median 38–46 s to first clean board; vias 0.59×/0.50×, track 0.94–0.95× reference (pour-free nets only, since PCBench re-routes pours); 98/99 D3-A boards 2-layer; 3-min cut-off chosen after seeing the curve; width-rounding fix needed ([results](https://deeppcb.ai/benchmark/pcbworld-bench-deeppcb-results/)).
- Marketing vs Freerouting ("state-of-the-art in 2005", "60–75% on complex boards") conflicts with PCBWorld (0.80/0.78) and ignores Freerouting 2.5/2.6 gains. RL explainer: actions extend/via/complete/rip-up at grid-unit granularity; admits no intent understanding, unreliable confidence, reward loopholes [V].
- Jumanji `Connector` (InstaDeep, open) is the grid toy many RL routing baselines use (5 actions/agent) [P].

**FanoutNet** (Li, Zhang, Xu, Liu; AAAI'23; WHUT/Huawei; [PDF](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802) [P]): fanout as MDP, one action per net = per-pin (layer, offset, direction); reward = downstream routability; CNN over layout images + 4-layer attention over net features; PPO (K=20, lr 3e-4/1e-3). 11 open boards (bm1–bm11) + 5 Huawei 6-layer HDI (94–368 nets, 277–937 pins): **FanoutNet 100% (245 min); Freerouting 1.4.5.1 81% (>24 h on 4/5); ELECTRA 5.91 91% (~1 min); NB-A* 95% (69 min)**.

**MCTS routers**
- **He, Li, Luo, Bao DATE'23** ([PDF](https://past.date-conference.com/proceedings-archive/2023/DATA/603.pdf) [P]): extend every pad/obstacle edge to split each layer into routable polygons; MCTS over sequences of neighbouring polygons (shared border or cross-layer overlap) with DFS-backtracking rollout (reveals global infeasibility after one iteration); A* with g = w1·WL + w2·C_res, C_res = max_p 1/d(x, p) pushes traces off pads; **re-partition each crossed polygon after every routed net** (global solution ⇒ detailed realization); hierarchical rip-up (DFS top, MCTS per path); random order. 10/10 real 2-layer boards vs 8/10 FreeRouting and DeepPCB; better WL, worse vias; 2-page paper.
- He & Bao 2020: max-reward UCT + DFS/DNN rollout on single-layer 30×30 grids; solves cases A*/Lee cannot; "not prone to net ordering" ([arXiv 2006.13607](https://arxiv.org/abs/2006.13607) [P]).
- LLM-as-PUCT-prior literature (LLM-MCTS, LLM-First Search, Scattered Forest Search) ([cross-domain routing](cross-domain-routing-transplants.md)).

**Other learned PCB routing**
| Work | Idea | Evidence |
|---|---|---|
| DreamerV3 + FR (Liao, Pan, Chiang; ESWA'26) | World-model RL optimizes Freerouting net order | 96% completion; −21% training time vs DQN; generalizes to unseen 6-layer; PPO fails under sparse reward; VAE+GAN and LLM agents "falter" ([OpenAlex](https://api.openalex.org/works/doi:10.1016/j.eswa.2026.131424) [P-abs]; [code](https://github.com/yinqimakeitfun/dreamer-Autorouting/tree/main)) |
| Ranking Cost (2021) | ES learns per-net cost maps + ranking for A* | Beats sequential A* and RL baseline ([arXiv 2110.03939](https://arxiv.org/abs/2110.03939) [P-abs]) |
| Unet-Astar (IEEE Access'23) | U-Net "recommended regions" restrict A* (reimplements Lin DAC'21 router) | 200 generated problems: runtime 302 → 78, vias −22%, WL −0.2%, both 100% ([IEEE](https://ieeexplore.ieee.org/document/10274949/) [P]) |
| GPCB (TCAD'25) / PRG (ISEDA'24) | Network-flow pattern tokens, GPT-style, 2-D sliding window, learns from humans | Claims SOTA; **0.69% NRR on OmniRouting** (VP) |
| TRouter (TCAD'23) | Thermal-map attention net; backprop gradients steer detours/vias; conflict-graph parallelism over net hulls | Beats PcbRouter on runtime and temperature (HyperLynx) ([PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J94-TCAD2023-TRouter.pdf) [P]) |
| Liao et al. DQN global routing (2020) | Synthetic grids | Beats sequential A* [P-abs] |
| Security-aware routing (ISQED'26) | Sequence-first, multilayer A*, RL test points | 100% on evaluated boards [P-abs] |
| Heatmap Router (Iowa State 2022) | — | Title only |
| Patent US 12019968 | NN-guided sequential Monte Carlo chooses connection order | [S] |

**VLSI learned routers** [P-abs/S]: HubRouter (generative hubs + actor-critic RSMT; reroute still needed); NeuralSteiner (Steiner candidates; up to 99.8% overflow reduction, ≤1.8% WL loss); DSBRouter (diffusion Schrödinger bridge, end-to-end connectivity); PRNet (one-shot generative global routing); DGR (differentiable DAG-forest global router, −0.95–4.08% WL, −1.28–2.54% vias); GAT-Steiner (99.846% ISPD19 nets); **offline CQL cost-weight scheduler: 1.56× avg (3.01× max) faster convergence on ISPD19**; **history-aware LSTM: −92% DRVs, −10% runtime**; XRoute RL environment; IJCAI'25 transformer ordering; async RL ordering −26% DRCs.

## Transferability ranking [I]
1. **High** — learned control of a classical router: cost-weight schedules, net ordering, cost maps, search-region pruning, flow warm starts; legality guaranteed by the engine.
2. **Medium** — congestion/thermal predictors as cost fields (TRouter, RUDY).
3. **Low** — generative "draw the route" models (gcell outputs, ISPD overflow metrics, need repair).

## Recommendations for our system
- Learn (or LLM-propose + optimizer-refine) **net order and cost schedules** for Freerouting/KRT/in-house PathFinder from logged runs [I].
- Port the DATE'23 polygon router as a research engine: LLM as PUCT prior over neighbouring polygons (conditioned on net class and homotopy hints) and as rip-up chooser; copy the re-partitioning invariant regardless of MCTS [I].
- FanoutNet-style learned fanout only after exact/pattern escape is in place ([escape](escape-routing.md)) [I].
- DeepPCB API only as optional bulk router for non-SI nets where cloud upload is acceptable; terms/rate limits unreviewed [I].

## Conflicts and open questions
- DeepPCB numbers are vendor-run, not independently reproduced; no peer-reviewed DeepPCB paper found; Quilter internals known only from marketing.
- HubRouter, NeuralSteiner, DSBRouter, GPCB, DreamerV3+FR full texts unread.

## Sources
- research notes: [routing_algorithms.md § Q2, Q3, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [cross_domain_ideas.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [verification_papers.md § 2.9, 2.12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [pcbworld](pcbworld.md) · [llm-routing-evidence](llm-routing-evidence.md) · [pathfinder-negotiated-congestion](pathfinder-negotiated-congestion.md) · [net-ordering](net-ordering.md)
