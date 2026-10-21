# PCBWorld: step-wise LLM routing in KiCad's engine (deep dive)

**TL;DR**
- PCBWorld wraps KiCad 9.0.8's push-and-shove router as a Gym environment. Interactive GPT-5.4 reaches clean-pass **0.65** on small real boards (D3-A), against 0.80 for Freerouting and 0.86 for PPO. **Every LLM scores 0** on the 10-board D3-B set [P].
- **Corrected:** the LLM prompt carried **no reward and no DRC-violation list**, no zones, a 2-turn history, 256-token replies, no rip-up actions and a 200-step cap. Its LLM numbers are a **lower bound** [P].
- **Engine engagement matters:** interactive 0.65 vs plan-and-execute 0.19 vs engine-free 0.02 (GPT-5.4, D3-A) [P].
- **Cost rules out per-segment LLM routing:** about 425k tokens and 231 s per small board, about 1.92M tokens and 866 s per medium board. That is **35× slower than Freerouting** on D2 (219× slower than PPO) [P].
- Code reuse: the engine is a **GPLv3 KiCad fork**, and our code is GPL-3.0-or-later, so it can be integrated in-process. See [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md) [I].

## Key facts

**Paper:** [arXiv 2607.05915 v4](https://arxiv.org/pdf/2607.05915), LG AI Research; KDD 2026 Workshop on Evaluation and Trustworthiness of Agentic AI (non-archival). Repositories: [PCBWorld](https://github.com/LGAI-Research/PCBWorld), [PCBWorld-Engine](https://github.com/LGAI-Research/PCBWorld-Engine) [P].

### Stack
- L4 is a Gymnasium facade.
- L3 is a Python wrapper with **58 step APIs**. The main text partitions them as 14 PNS / 28 DRC and state / 16 utilities; Table 6 as 25 Action / 25 State / 3 Reward / 5 Utility.
- L2 is pybind11; L1 is KiCad 9.0.8.
- The engine runs as a separate process over a Unix socket.
- **Conflict:** the paper calls L1 "unmodified KiCad", but the repository contains modified KiCad files, a headless RL router, a DRC fork and a `kicad_rl_router` module.

### Agent action space
- `net_select(net_id)`, `start_route(x, y, layer)`, `make_line(x, y, mode)`, `make_via(x, y, mode)`, `finish(mode)` (to the nearest unconnected pad on the layer), `net_end`, plus an `idle` fallback.
- Routing modes: 0 mark obstacles, 1 shove, 2 walk around.
- That is 6 types plus idle, giving 7 parser indices (corrected).
- **Rework and delete APIs exist but were excluded** from the agent action space.
- An FSM mask enforces net_select → start_route → routing.

### Candidates and observation
- **Candidate pool:** net pads (through-hole pads once per layer), track ends, via centres, open ratsnest targets and an **8-way 0.5 mm grid around the head**; deduplicated and capped at 64. The RL policy points into this pool; the LLM may emit free coordinates under a regex.
- **Observation blocks:** board_static, routing_geometry, router_head, drc_violations, action_history, closed_nets.
- **LLM view:**
  - an S-expression with the static block in the system message (prefix caching);
  - zones dropped; rules collapsed to the strictest netclass; pads reduced to xy plus layer; coordinates rounded to 3 decimals;
  - on `net_select`, the environment pushes the per-class width and via sizes into PNS.

### Prompt and output
- **Priority order:** complete connections, then avoid DRC, then minimise wirelength.
- **Rules:**
  - use exact observed coordinates, inventing them only for detours;
  - vias at least 1 mm from any pad, never on a pad;
  - never reach a target pad's xy on the wrong layer;
  - prefer `finish`.
- **Output contract:** exactly one `<think>…</think><action>…</action>` pair, ASCII only, with a strict parser that falls back to idle.
- Replies are capped at 256 tokens (512 for Qwen); episodes at T = 200.

### Reward and metrics
- Φ(s) = −f_drv − λ_w·WL − λ_v·vias, with f_drv = 3·ln(1 + x/2) + Σᵢ ln(1 + xᵢ/2). Here x is the number of dirty nets and xᵢ the violations on net i; λ_w = 0.002 and λ_v = 0.1.
- The DRC basis is 38 checks: 35 stock error-level checks plus DANGLING_VIA, DANGLING_TRACK and NET_CONFLICT.
- **Clean Pass:** full connectivity and 0 error-level DRVs on the best-potential rollout of 5. A board can clean-pass while still carrying the 3 promoted warnings.
- The repository's default potential adds −unconnected, completion bonuses and a step penalty, unlike the paper.

### Datasets
- **D1:** a grid replica of Jumanji Connector.
- **D2:** synthetic, 2 layers, 4–6 nets, 8–21 pads; split 10k/128/128.
- **D3:** **679** real boards from PCBench's pool of 1,182 boards converted to KiCad 9. Only `.kicad_pro` severities were edited; board files are byte-identical.
  - D3-A: 100 boards with ≤31 pads (99 loadable).
  - D3-B: 287 boards with ≤100 pads. **Only 10 two-layer boards were evaluated.**
  - D3-C: 292 boards (6–451 nets, up to 2,103 pads, 2–8 layers), not evaluated.
  - Router and RL rows are means over 4 seeds; LLM rows are a single best-of-5 run.

### Results (Table 21)

Columns: D2 CP / time (s); D3-A CP / routability / DRV / time (s); D3-B CP / routability.

| Method | D2 CP / s | D3-A CP / Rout / DRV / s | D3-B CP / Rout |
|---|---|---|---|
| Freerouting 2.1.0 (`-mp 10`, 4 GiB) | 1.00 / 2.69 | 0.80 / 0.91 / 0.86 / 7.09 | 0.78 / 1.00 |
| KRT | 1.00 / 0.82 | 0.74 / 0.94 / 2.38 / 0.65 | 0.20 / 0.86 |
| OrthoRoute (0.4 mm grid, rules not enforced) | 0.01 / 2.54 | 0.02 / 0.53 / 99.7 / 2.20 | 0.00 / 0.44 |
| GPT-5.4 | 0.96 / 94.04 | 0.65 / 0.91 / 1.31 / 231.15 | 0.00 / 0.62 (865.83 s) |
| GPT-5.4-mini | 0.58 / 33.93 | 0.28 / 0.72 / 3.88 / 56.85 | 0.00 / 0.61 |
| GPT-5.4-nano | 0.55 / 63.39 | 0.30 / 0.73 / 3.84 / 100.76 | 0.00 / 0.59 |
| Qwen3.5-397B (FP4, thinking off) | 0.33 / 47.58 | 0.34 / 0.75 / 3.63 / 81.82 | 0.00 / 0.51 |
| PPO | 1.00 / 0.43 | 0.86 / 0.95 / 0.89 / 1.83 | 0.45 / 0.85 |
| PPO w/o finish | 1.00 / 0.88 | 0.94 / 0.99 / 0.21 / 3.05 | 0.42 / 0.87 |
| GRPO | 1.00 / 1.16 | 0.85 / 0.98 / 0.46 / 3.54 | 0.10 / 0.69 |
| PPO-terminal | 0.92 / 1.37 | 0.82 / 0.95 / 0.67 / 2.58 | 0.38 / 0.81 |

Reference wirelength and vias: D3-A 170.2 mm / 1.18 vias; D3-B 570.3 mm / 6.70 vias. LLMs show *shorter* wirelength only because they leave connections incomplete.

**Engine engagement (Table 4, D3-A, CP):**

| Model | Interactive | Plan-and-execute | Engine-free |
|---|---|---|---|
| GPT-5.4 | 0.65 | 0.19 (DRV 16.28) | 0.02 (DRV 34.58) |
| GPT-5.4-mini | 0.28 | 0.19 | 0.02 |
| GPT-5.4-nano | 0.30 | 0.18 | 0.00 (parse-fail 0.10) |

**Slowdowns (corrected):**
- D2: GPT-5.4 is 219× slower than PPO and 35× slower than Freerouting.
- D3-A: 126× slower than PPO, 33× slower than Freerouting and 356× slower than KRT.

**Tokens per episode (GPT-5.4):** about 107k on D2, about 425k on D3-A, about 1.92M on D3-B.

**Baseline configs:**
- KRT: 0.1 mm grid, 200k A\* iterations, rip-up 3, heuristic weight 1.9, "mps" ordering, via cost 50, turn cost 1000.
- PPO policy: a d = 128, 4-layer, 8-head Transformer with Fourier features (32 frequencies) over 13 token types and a pointer network; γ 0.995, λ 0.95, 32 environments, 300 iterations on one L40.

### Failure modes
- **The first `net_select` often decides success**, and agents "rarely perform corrective recovery".
- Without delete actions, agents loop on reroutes once congestion appears.
- LLM failures map to DRC codes:
  - via on pad → ANNULAR_WIDTH, HOLE_CLEARANCE;
  - wrong-layer endpoint → DANGLING_TRACK;
  - cross-net contact → SHORTING_ITEMS, CLEARANCE;
  - detour over the board edge → EDGE_CLEARANCE;
  - phantom waypoints → parse rejection;
  - repeated identical attempts.

## Recommendations for our system

1. **Do not build per-segment LLM routing.** It is ruled out on cost and quality [I].
2. If a step router agent is built anyway, fix the known gaps:
   - echo DRC violations with codes and positions;
   - include copper zones;
   - expose per-netclass rules;
   - add rip-up and delete actions;
   - keep a longer history;
   - prefix-cache the static block;
   - make the **first net selection an explicit planning decision**.
3. The useful LLM role is net ordering, corridors and rework choice at a coarse level, with a deterministic router underneath (see [agent-loop-patterns.md](agent-loop-patterns.md)).
4. Reuse PCBWorld's 679 KiCad-9 D3 boards (each keeps its source licence) as a routing benchmark and as relation-mining data (see [../data/training-recipes.md](../data/training-recipes.md)).
5. Reuse the reward shape (concave per-net DRV penalty plus promoted dangling and conflict checks) for any RL router.

## Conflicts and open questions

- The paper says "unmodified KiCad"; the repository holds a modified fork.
- The kicad-tools "fair-95" D3-A subset is not a PCBWorld construct; the paper uses 99 boards.
- D3-C has never been evaluated.

## Sources
- research notes:
  - [verification_papers.md § 1 rows 1–11, 45; § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
  - [llm_for_eda.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- primary: [PCBWorld v4](https://arxiv.org/pdf/2607.05915); [ENVIRONMENT.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/ENVIRONMENT.md); [METRICS.md](https://github.com/LGAI-Research/PCBWorld/blob/main/docs/METRICS.md)

See also: [pcb-llm-benchmarks.md](pcb-llm-benchmarks.md), [read-representations.md](read-representations.md), [../routing/freerouting.md](../routing/freerouting.md)
