# PathFinder / negotiated congestion and conflict-penalty schedules

Scope: PathFinder cost model, VPR schedule, negotiation in PCB tools, Formulation C, learned schedules. Not here: prototype timings -> [solver benchmarks § G](../solvers/benchmarks.md#g-pathfinder-prototype); MAPF analogues -> [cross-domain routing](cross-domain-routing-transplants.md).
Keys: PathFinder, negotiated congestion, pres_fac, acc_fac, history cost, VPR, VTR, bb_factor, astar_fac, OrthoRoute, FanoutNet MCR, NB-A*, NCER, Formulation C, pathfinder_bench.py, CQL, offline RL schedule, LSTM

**Results**
1. Every production PCB router negotiates conflicts across passes (Specctra, Situs, gEDA, PcbRouter, Freerouting): route first tolerating conflicts, then raise penalties.
2. PathFinder (b_n + h_n)·p_n with the VPR default schedule is a sound start for an in-house router, after normalizing base costs (see below).
3. Pure lattice PathFinder (OrthoRoute) fails on ordinary boards (PCBWorld CP 0.02, run without board rules); negotiation works best inside a detailed router (FanoutNet MCR) or as a coarse global planner.
4. Learned schedules (VLSI): CQL 1.56× faster convergence; LSTM variant −92% DRVs. No PCB-specific schedule study exists; transfer is unproven.
5. kae's one test was a non-standard variant: `lastmile_region.py` (experimental, off) left 8-15 conflicts on fm4dd after 20 rounds, but with present price 2.0 from round 1 ×1.5, per-net history multiplied into the price, every net re-routed each round and a 20-round cap ([kae-closing-open-connections](../../research/routing/kae-closing-open-connections.md)) [C]. The VPR schedule, per-cell history and offender-only reroute are untested on PCBs here.

## PathFinder cost and VPR defaults

- McMurchie & Ebeling, FPGA'95 ([DOI](https://doi.org/10.1145/201310.201328)): node cost C_n = (b_n + h_n)·p_n; b = base cost, h = accumulated congestion history, p = present-sharing penalty ([Lafayette](https://sites.lafayette.edu/cadapps/main-page/pathfinder-fpga-routing-algorithm/) [P]).
- VPR itself computes b·h·p, h starting at 1 and growing by acc_fac × overuse, calibrated for base costs ≈ 1 per wire: normalize b (or use the multiplicative form) before reusing acc_fac 1 ([VTR route_common.h](https://github.com/verilog-to-routing/vtr-verilog-to-routing/blob/master/vpr/src/route/route_common.h) [P]).

VPR defaults ([docs](https://docs.verilogtorouting.org/en/latest/vpr/command_line_usage/) [P]):

| Parameter | Default |
|---|---|
| first_iter_pres_fac | 0.0 |
| initial_pres_fac | 0.5 |
| pres_fac_mult | 1.3 |
| max_pres_fac | 1000 |
| acc_fac | 1 |
| bb_factor | 3 |
| astar_fac | 1.2 |
| max_router_iterations | 50 |

## Negotiation in PCB tools

| Tool | Mechanism | Source |
|---|---|---|
| Specctra | Pass 1 connects everything regardless of conflicts; rip-up + push-and-shove later | [Wikipedia](https://en.wikipedia.org/wiki/Specctra) [S] |
| Altium Situs "Globally Optimised Main" | Ignores violations first, reroutes with increased conflict costs until none remain | [Altium](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc] |
| gEDA autoroute | Routes over traces; previous-pass conflicts cheaper; penalties rise per pass | [autoroute.c](https://raw.githubusercontent.com/bert/pcb/master/src/autoroute.c) [P-code] |
| PcbRouter | Each rip-up iteration adds `gStepTraObsCost`/`gStepViaObsCost` to all nets' obstacle costs; keep best | [GridBasedRouter.cpp](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/src/GridBasedRouter.cpp) [P-code] |
| Freerouting | Linear global rip-up escalation `start_ripup_costs·(pass+1)` | [freerouting](freerouting.md) |
| FanoutNet MCR | 3-D A*, g = c1·WL + c2·layer change + c3·diff pair + c4·reference-layer shielding + c5·spacing; 135° heuristic; raises c5 PathFinder-style | [AAAI'23](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802) [P] |
| OrthoRoute | GPU PathFinder on Manhattan via lattice (H-only/V-only layers, blind/buried); nets still sequential on a shared congestion map; "not a general-purpose PCB autorouter" | [repo](https://github.com/bbenchoff/OrthoRoute) [P] |
| NB-A* (Lin et al.) | Negotiation-based A*; 95% avg routability on FanoutNet's Huawei boards (69 min) | [P] |
| NCER | Negotiated escape router | [escape](escape-routing.md) |
| Negotiation-based layer assignment | Order barely matters | [layer assignment](layer-assignment-and-vias.md) |

OrthoRoute on PCBWorld D3-A: routability 0.53, CP 0.02, 99.7 DRVs at its default 0.4 mm grid with board rules not enforced (VP-corrected; structurally unfavourable) → [PCBWorld](pcbworld.md).

## Formulation C: negotiated multi-layer grid router

Prototype `pathfinder_bench.py` ([solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)); measured: 0 overuse in 14–15 iterations, 2.2–61 s for 50–300 nets → [benchmarks § G](../solvers/benchmarks.md#g-pathfinder-prototype).
```python
# nodes = (ix, iy, layer) at pitch = track+clearance; capacity 1; other nets' pads blocked; via edges cost VIA
hist = zeros(N); pres_fac = 0.0                         # VPR: first_iter_pres_fac = 0
for it in range(50):
    for net in order(nets):                               # critical/diff-pair/bus first, then by bbox
        if it > 0 and not overused(route[net]): continue  # reroute offenders only
        rip_up(net)
        cost = lambda v: (base[v] + hist[v]) * (1 + pres_fac * max(0, occ[v] + 1 - cap[v]))
        tree = {pins(net)[0]}
        for sink in prim_order(pins(net)):
            tree |= astar(tree, sink, cost, h=1.2 * manhattan_lb, window=expand(bbox(net), 3 + it))
        commit(net, tree)
    if not any_overuse(): break
    hist += 1.0 * overuse                                   # acc_fac = 1
    pres_fac = 0.5 if it == 0 else min(pres_fac * 1.3, 1000)
# post: merge collinear, 45° smoothing, neck-down at pads, write via IPC in one commit, kicad-cli drc; repair or fall back to Freerouting
```
Use in kae [I]:
- Base costs normalized to ~1 per grid step; A* windowed to the net bbox, growing per iteration; reroute only offenders.
- Schedule (initial conflict cost, growth per pass, history weight, via-cost ramp, bbox factor) as a typed knob set; LLM picks presets per board class (dense 2-layer, BGA 6-layer, RF); later an offline-RL scheduler on logged runs.
- Conflict-tolerant first pass = seconds-scale feasibility probe (layer count, hotspot map) for placement/stackup revisions → [autorouter skepticism](autorouter-skepticism.md).
- LLM sets per-net-class cost multipliers and priorities, never paths.

## Learned negotiation schedules (VLSI)

- Offline conservative Q-learning picks cost weights per iteration: 1.56× avg (3.01× max) faster convergence on ISPD19 at equal/better DRVs; some cross-technology generalization ([arXiv 2512.03594](https://arxiv.org/abs/2512.03594) [P-abs]).
- History-aware LSTM variant: −92% DRVs, −10% runtime, pluggable into any cost-based router ([arXiv 2609.08232](https://arxiv.org/abs/2609.08232) [P-abs]).

## Sources

- [routing_algorithms.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Q1, Q7, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 1 row 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
