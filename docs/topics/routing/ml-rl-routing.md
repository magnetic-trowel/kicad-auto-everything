# ML/RL routing (DeepPCB, FanoutNet, MCTS, learned schedules) and transferability

Scope: learned PCB and VLSI routers, their evidence, and which ideas transfer. Not here: benchmark definitions -> [PCBWorld](pcbworld.md), [LLM routing evidence](llm-routing-evidence.md); net-order learning detail -> [net ordering](net-ordering.md#learned-ordering).
Keys: DeepPCB, InstaDeep, Cooper, Sebulba, Jumanji Connector, FanoutNet, MCTS router, polygon partition, DATE'23, He & Bao, DreamerV3, Ranking Cost, Unet-Astar, GPCB, PRG, TRouter, HubRouter, NeuralSteiner, DSBRouter, PRNet, DGR, GAT-Steiner, CQL scheduler, transferability

**Results**
1. ML that works on PCBs either learns a decision a classical router consumes (fanout: FanoutNet; net order: DreamerV3+FR; cost maps: Ranking Cost; search regions: Unet-Astar) or trains a compact policy over engine actions (PCBWorld PPO on KiCad PNS).
2. DeepPCB (commercial RL) reports the top one-attempt PCBWorld-Bench scores (0.929 / 0.800): vendor-run, mostly 2-layer, excludes DDR, length matching, impedance, RF and complex BGA fanout.
3. DATE'23 polygon-partition MCTS router: 10/10 real 2-layer boards (FreeRouting and DeepPCB 8/10); guarantees global ⇒ detailed feasibility by re-partitioning after each net.
4. VLSI generative routers transfer poorly: GPCB 0.69% NRR on OmniRouting's real boards vs PcbRouter 56.2%.
5. Highest transfer: learned control of classical routers (cost schedules 1.56–3× faster; −92% DRVs, VLSI).

## DeepPCB (InstaDeep / BioNTech)

- Commercial RL router (NN-guided SMC over connection orders; Sebulba TPU training); training, product, plugin, PCBWorld-Bench self-evaluation (0.929 / 0.800 @1, vendor-run) and marketing claims → [DeepPCB](../landscape/deeppcb.md#vendor-reported-numbers) [V].
- Jumanji `Connector` (InstaDeep, open): grid toy used by many RL routing baselines (5 actions/agent) [P].

## FanoutNet

Li, Zhang, Xu, Liu; AAAI'23; WHUT/Huawei; [PDF](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802) [P].
- Fanout as MDP: one action per net = per-pin (layer, offset, direction); reward = downstream routability; CNN over layout images + 4-layer attention over net features; PPO (K=20, lr 3e-4/1e-3).
- 11 open boards (bm1–bm11) + 5 Huawei 6-layer HDI (94–368 nets, 277–937 pins): FanoutNet 100% (245 min); Freerouting 1.4.5.1 81% (>24 h on 4/5); ELECTRA 5.91 91% (~1 min); NB-A* 95% (69 min).
- Learned fanout only after exact/pattern escape is in place → [escape](escape-routing.md) [I].

## MCTS routers

- He, Li, Luo, Bao DATE'23 ([PDF](https://past.date-conference.com/proceedings-archive/2023/DATA/603.pdf) [P], 2-page paper):
  1. Extend every pad/obstacle edge to split each layer into routable polygons.
  2. MCTS over sequences of neighbouring polygons (shared border or cross-layer overlap) with DFS-backtracking rollout (reveals global infeasibility after one iteration).
  3. A* with g = w1·WL + w2·C_res, C_res = max_p 1/d(x, p) (pushes traces off pads).
  4. Re-partition each crossed polygon after every routed net (global solution ⇒ detailed realization).
  5. Hierarchical rip-up (DFS top, MCTS per path); random order.
  Result: 10/10 real 2-layer boards vs 8/10 FreeRouting and DeepPCB; better WL, worse vias.
- He & Bao 2020: max-reward UCT + DFS/DNN rollout on single-layer 30×30 grids; solves cases A*/Lee cannot; "not prone to net ordering" ([arXiv 2006.13607](https://arxiv.org/abs/2006.13607) [P]).
- Port the DATE'23 router as a research engine: LLM as PUCT prior over neighbouring polygons (conditioned on net class and homotopy hints) and rip-up chooser; copy the re-partitioning invariant regardless of MCTS [I]. LLM-as-PUCT literature → [cross-domain routing](cross-domain-routing-transplants.md#game-search).

## Other learned PCB routing

| Work | Idea | Evidence |
|---|---|---|
| DreamerV3 + FR (Liao, Pan, Chiang; ESWA'26) | World-model RL optimizes Freerouting net order | 96% completion; −21% training time vs DQN; generalizes to unseen 6-layer; PPO fails under sparse reward; VAE+GAN and LLM agents "falter" ([OpenAlex](https://api.openalex.org/works/doi:10.1016/j.eswa.2026.131424) [P-abs]; [code](https://github.com/yinqimakeitfun/dreamer-Autorouting/tree/main)) |
| Ranking Cost (2021) | ES learns per-net cost maps + ranking for A* | Beats sequential A* and RL baseline ([arXiv 2110.03939](https://arxiv.org/abs/2110.03939) [P-abs]) |
| Unet-Astar (IEEE Access'23) | U-Net "recommended regions" restrict A* (reimplements Lin DAC'21 router) | 200 generated problems: runtime 302 → 78, vias −22%, WL −0.2%, both 100% ([IEEE](https://ieeexplore.ieee.org/document/10274949/) [P]) |
| GPCB (TCAD'25) / PRG (ISEDA'24) | Network-flow pattern tokens, GPT-style, 2-D sliding window, learns from humans | Claims SOTA; 0.69% NRR on OmniRouting (VP) |
| TRouter (TCAD'23) | Thermal-map attention net; backprop gradients steer detours/vias; conflict-graph parallelism over net hulls | Beats PcbRouter on runtime and temperature (HyperLynx) ([PDF](https://www.cse.cuhk.edu.hk/~byu/papers/J94-TCAD2023-TRouter.pdf) [P]) |
| Liao et al. DQN global routing (2020) | Synthetic grids | Beats sequential A* [P-abs] |
| Security-aware routing (ISQED'26) | Sequence-first, multilayer A*, RL test points | 100% on evaluated boards [P-abs] |
| Heatmap Router (Iowa State 2022) | — | Title only |
| Patent US 12019968 | NN-guided sequential Monte Carlo chooses connection order | [S] |

## VLSI learned routers

[P-abs/S]: HubRouter (generative hubs + actor-critic RSMT; reroute still needed); NeuralSteiner (Steiner candidates; up to 99.8% overflow reduction, ≤1.8% WL loss); DSBRouter (diffusion Schrödinger bridge, end-to-end connectivity); PRNet (one-shot generative global routing); DGR (differentiable DAG-forest global router, −0.95–4.08% WL, −1.28–2.54% vias); GAT-Steiner (99.846% ISPD19 nets); offline CQL cost-weight scheduler and history-aware LSTM → [PathFinder](pathfinder-negotiated-congestion.md#learned-negotiation-schedules-vlsi); XRoute RL environment; IJCAI'25 transformer ordering; async RL ordering −26% DRCs.

## Transferability ranking

[I]
1. High: learned control of a classical router (cost-weight schedules, net ordering, cost maps, search-region pruning, flow warm starts); the engine guarantees legality. Learn or LLM-propose + optimizer-refine net order and cost schedules for Freerouting/KRT/PathFinder from logged runs.
2. Medium: congestion/thermal predictors as cost fields (TRouter, RUDY).
3. Low: generative "draw the route" models (gcell outputs, ISPD overflow metrics, need repair).

## Open questions

- DeepPCB numbers vendor-run, not independently reproduced; no peer-reviewed DeepPCB paper; Quilter internals known only from marketing.
- HubRouter, NeuralSteiner, DSBRouter, GPCB, DreamerV3+FR full texts unread.

## Sources

- [routing_algorithms.md § Q2, Q3, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [cross_domain_ideas.md § Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [verification_papers.md § 2.9, 2.12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
