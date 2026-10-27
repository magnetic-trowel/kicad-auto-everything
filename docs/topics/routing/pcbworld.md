# PCBWorld: Gym environment over KiCad PNS, results and lessons (VP-verified)

**TL;DR**
- PCBWorld (LG AI Research; arXiv 2607.05915 v4; KDD'26 workshop, non-archival) wraps **KiCad 9.0.8's PNS router + DRC** as 58 Python APIs in a separate GPLv3 process; BSD-3 environment.
- Real boards (99 small D3-A boards; 10 of D3-B's 287 medium boards, all 2-layer): **Freerouting 2.1.0 0.80 / 0.78** clean-pass @5, **PPO on engine actions 0.86 / 0.45** (0.94 on D3-A without `finish`), **GPT-5.4 interactive 0.65 / 0.00**.
- LLM agents were handicapped: **no reward and no DRC list in the prompt**, no copper zones, 2-turn history, 256-token replies, no delete/rework actions, T = 200 — their numbers are a lower bound.
- Engine engagement is decisive (GPT-5.4 interactive 0.65 vs plan-and-execute 0.19 vs engine-free 0.02), but per-step LLM routing is ruled out on cost: **~425k tokens per small board, ~1.92M per medium board; 126× slower than PPO, 33× slower than Freerouting**.
- The first `net_select` often decides success; agents rarely recover.

## Key facts

**Stack** ([arXiv](https://arxiv.org/pdf/2607.05915) [P]): L4 Gymnasium facade (dispatcher, observation builder, reward composer, action mask) → L3 58 step-level APIs (14 PNS::ROUTER, 28 DRC/board-state, 16 utilities) → L2 pybind11 → L1 KiCad 9.0.8 engine in a separate GPLv3 process (paper calls L1 "unmodified", the engine repo contains modified KiCad files — conflict) ([PCBWorld-Engine](kicad-pns-router.md)).
- API groups: configuration (routing/corner mode, track width, via diameter/drill), routing (`start_route`, `move`, `fix_route`, `cancel_route`, `finish`, `undo_last_segment`, `flip_posture`, `toggle_via`, `switch_layer`), dragging, rework (`delete_track_*`, `delete_via_*`), state (tracks, vias, pads, ratsnest, outline, design rules, netclass), reward (`get_drc_violation_count`, `get_drc_violations`, `get_reward_snapshot`).

**Agent interface**
- Actions: `net_select(net)`, `start_route(x,y,layer)`, `make_line(x,y,mode)`, `make_via(x,y,mode)`, `finish(mode)` (to nearest unconnected pad on current layer), `net_end`, `idle` fallback — 6 types + idle (VP-corrected). Mode 0 mark obstacles, 1 shove, 2 walkaround. FSM mask enforces net_select → start_route → routing. **Rework APIs excluded from agents.**
- Candidate pool per step: active net's pads (per layer for THT), track ends, via centres, open ratsnest targets, **8-way 0.5 mm offsets around the router head**; dedup by (x, y, layer), cap 64. RL points into it; LLM may emit free coordinates under a guided-decoding regex.
- Observation: board_static, routing_geometry, router_head, drc_violations near head, action_history, closed_nets; LLM sees S-expressions (static block in system message for prefix caching); LLM view **drops copper zones, collapses netclass rules to the strictest envelope**, rounds to 3 decimals; on `net_select` per-class sizes are pushed into PNS.
- Prompt: one `<think>…</think><action>…</action>`; priorities complete > avoid DRC > minimize WL; vias ≥1 mm from pads, never on a pad; never reach a pad on the wrong layer; prefer `finish`. Replies capped 256 tokens (512 Qwen); T = 200 steps.

**Reward / metrics**: Φ = −f_drv − 0.002·WL − 0.1·vias; f_drv = 3·ln(1+x/2) + Σᵢ ln(1+xᵢ/2) (x = dirty nets, xᵢ = violations on net i); 38 checks = 35 stock error checks + DANGLING_VIA, DANGLING_TRACK, NET_CONFLICT; terminal reward Φ(s_T) − Φ(s_0); shipped repo uses a newer potential (−unconnected, completion bonus, step penalty). **Clean Pass** = full connectivity and 0 error DRVs on the best-potential of 5 rollouts (@5); boards can pass with the 3 promoted warnings.

**Datasets**: D1 Jumanji-Connector grid replica (10–500); D2 synthetic gridless (2 layers, 4–6 nets, 8–21 pads; 10k/128/128); D3 = 679 real boards from PCBench's 1,182-board `PCBs_version_9` pool converted to KiCad 9 (only `.kicad_pro` edited: some checks set to ignore, some rule floors zeroed; board files byte-identical) — D3-A 100 (≤31 pads), D3-B 287 (≤100 pads), D3-C 292 (6–451 nets, ≤2,103 pads, 2–8 layers; unevaluated). Evaluations use 99 D3-A boards and 10 D3-B boards (2-layer, one per pad-count quantile); Freerouting/RL rows are 4-seed means; LLM rows single best-of-5.

**Results (Table 21, @5)** — CP / routability / DRV / WL mm / vias / s
| Method | D2 | D3-A | D3-B |
|---|---|---|---|
| Human reference | — | 1.00 / 1.00 / 0 / 170.2 / 1.18 | 1.00 / 1.00 / 0 / 570.3 / 6.70 |
| Freerouting 2.1.0 | 1.00, 2.69 s | **0.80** / 0.91 / 0.86 / 156.2 / 0.74 / 7.09 | **0.78** / 1.00 / 10.6 / 535.4 / 3.48 / 9.94 |
| KRT | 1.00, 0.82 s | 0.74 / 0.94 / 2.38 / 142.8 / 3.69 / 0.65 | 0.20 / 0.86 / 44.7 / 472.3 / 11.8 / 3.27 |
| OrthoRoute (rules not enforced) | 0.01 | 0.02 / 0.53 / 99.7 / 129.8 / 26.97 | 0.00 |
| GPT-5.4 | 0.96, 94.04 s | 0.65 / 0.91 / 1.31 / 150.8 / 2.09 / 231.15 | 0.00 / 0.62 / 17.3, 865.83 s |
| GPT-5.4-mini / nano / Qwen3.5-397B | 0.58 / 0.55 / 0.33 | 0.28 / 0.30 / 0.34 | 0.00 |
| **PPO** | 1.00, 0.43 s | **0.86** / 0.95 / 0.89 / 165.4 / 0.92 / 1.83 | 0.45 / 0.85 / 8.28 / 668.6 / 6.17 / 10.77 |
| GRPO | 1.00 | 0.85 (279 mm, 9.39 vias) | 0.10 |
| PPO-terminal | 0.92 | 0.82 | 0.38 |
| **PPO w/o finish** | 1.00 | **0.94** / 0.99 / 0.21 / 224.1 / 2.16 | 0.42 |

- @1 (Table 22): D3-A Freerouting 0.75, PPO-w/o-finish 0.81; D3-B Freerouting 0.64; GPT-5.4-mini D2 0.58 → 0.20; PPO-terminal 0.92 → 0.61.
- Engine engagement (D3-A): GPT-5.4 interactive 0.65 / plan-and-execute 0.19 / engine-free 0.02; mini 0.28/0.19/0.02; nano 0.30/0.18/0.00 (parse-fail 0.10).
- Speed (VP-corrected): D3-A GPT-5.4 = 126× PPO, 33× Freerouting, 356× KRT; D2 0.43 s is PPO only.
- Tokens/episode (GPT-5.4): ~107k D2, ~425k D3-A, ~1.92M D3-B. Grid-action RL collapses (A2C ≥100, Sable ≥200).
- Baseline configs: Freerouting 2.1.0 `-mp 10`, 4 GiB heap; KRT 0.1 mm grid, 200k iterations, rip-up 3, heuristic weight 1.9, MPS, via 50, turn 1000; OrthoRoute 0.4 mm grid, rules off.
- RL policy: decoder-only transformer (d 128, 4 layers, 8 heads), Fourier features (32 freqs), 13 entity token types, pointer network over candidates; PPO γ 0.995, λ 0.95, 32 envs, 256-step episodes, 300 iterations on one L40. Synthetic-trained policy transfers zero-shot to real boards.
- Failure modes: first `net_select` decides; loops without delete actions; LLM errors map to DRC codes — via on pad (ANNULAR_WIDTH, HOLE_CLEARANCE), wrong-layer endpoint (DANGLING_TRACK), shorts/clearance, edge detours (EDGE_CLEARANCE), phantom waypoints, repeated attempts.

## Recommendations for our system
- Use PCBWorld D3-A/B as a routing benchmark with matched @1/@5, seed means, stated router settings and potential function (kaebench's `cpk` is any-clean@k, so it can only be ≥ PCBWorld's Φ-selected CP@5); add D3-C and Freerouting Tier C/D as stress sets ([benchmarks](benchmarks-and-datasets.md)) [I].
- Do not build per-segment LLM routing; if a step agent is built, fix: echo DRC codes/positions, include zones, per-netclass rules, delete/rip-up actions, longer history, explicit first-`net_select` planning, prefix-cached static block [I].
- Reuse the engine (GPLv3 — in-process allowed under our GPL-3.0-or-later) for scripted PNS: checkpoint/restore enables beam search/MCTS over waypoints and modes ([PNS](kicad-pns-router.md)) [I].
- Mine D3's human-routed boards for relation/offset priors and ordinal-magnitude calibration, excluding the 99 D3-A + 10 D3-B evaluation boards: never mine, fit or calibrate on them (per-board licenses apply) [I].

## Conflicts and open questions
- Paper says L1 engine "unmodified"; repo contains modified KiCad files.
- Freerouting 2.1.0 is far older than 2.5/2.6 ([freerouting](freerouting.md)); no independent KiCad-DRC re-score of new versions on PCBWorld-Bench.

## Sources
- research notes: [verification_papers.md § 1 rows 1–11, 45; § 2.1; § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [routing_algorithms.md § Q3, Q4, Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)
- primary: [arXiv 2607.05915](https://arxiv.org/abs/2607.05915); [PCBWorld repo](https://github.com/LGAI-Research/PCBWorld); [PCBWorld-Engine](https://github.com/LGAI-Research/PCBWorld-Engine)

See also: [llm-routing-evidence](llm-routing-evidence.md) · [kicad-pns-router](kicad-pns-router.md) · [ml-rl-routing](ml-rl-routing.md)
