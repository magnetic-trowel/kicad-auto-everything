# PathFinder / negotiated congestion and conflict-penalty schedules

**TL;DR**
- **Every production PCB router negotiates conflicts across passes** (Specctra, Situs, gEDA, PcbRouter, Freerouting) — route first while tolerating conflicts, then raise penalties.
- PathFinder cost (b_n + h_n)·p_n with **VPR defaults** (pres_fac 0 → 0.5, ×1.3/iteration, acc_fac 1, ≤50 iterations) is a sound starting point for an in-house router.
- Pure lattice PathFinder (OrthoRoute) fails on ordinary boards (PCBWorld CP 0.02, but run without board rules); negotiation works best **inside** a detailed router (FanoutNet MCR) or as a coarse global planner.
- Expose the schedule as typed knobs with LLM presets per board class; learn it offline later (VLSI CQL: 1.56× faster convergence; LSTM variant −92% DRVs).

## Key facts

**PathFinder** (McMurchie & Ebeling, FPGA'95, [DOI](https://doi.org/10.1145/201310.201328)): node cost C_n = (b_n + h_n)·p_n — base cost, accumulated congestion history, present-sharing penalty ([Lafayette](https://sites.lafayette.edu/cadapps/main-page/pathfinder-fpga-routing-algorithm/) [P]).

**VPR defaults** ([docs](https://docs.verilogtorouting.org/en/latest/vpr/command_line_usage/) [P])
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

**Negotiation in PCB tools**
| Tool | Mechanism | Source |
|---|---|---|
| Specctra | Pass 1 connects everything regardless of conflicts; rip-up + push-and-shove later | [Wikipedia](https://en.wikipedia.org/wiki/Specctra) [S] |
| Altium Situs "Globally Optimised Main" | Ignores violations first, reroutes with increased conflict costs until none remain | [Altium](https://www.altium.com/documentation/altium-designer/automated-board-layout-situs-topological-autorouter) [P-doc] |
| gEDA autoroute | Routes over traces; previous-pass conflicts cheaper; penalties rise per pass | [autoroute.c](https://raw.githubusercontent.com/bert/pcb/master/src/autoroute.c) [P-code] |
| PcbRouter | Each rip-up iteration adds `gStepTraObsCost`/`gStepViaObsCost` to all nets' obstacle costs; keep best | [GridBasedRouter.cpp](https://raw.githubusercontent.com/The-OpenROAD-Project-Attic/PcbRouter/master/src/GridBasedRouter.cpp) [P-code] |
| Freerouting | Linear global rip-up escalation `start_ripup_costs·(pass+1)` | [freerouting](freerouting.md) |
| FanoutNet MCR | 3-D A*, g = c1·WL + c2·layer change + c3·diff pair + c4·reference-layer shielding + c5·spacing; 135° heuristic; raises c5 PathFinder-style | [AAAI'23](https://ojs.aaai.org/index.php/AAAI/article/view/26030/25802) [P] |
| OrthoRoute | GPU PathFinder on Manhattan via lattice (H-only/V-only layers, blind/buried); nets still sequential on shared congestion map; "not a general-purpose PCB autorouter" | [repo](https://github.com/bbenchoff/OrthoRoute) [P] |
| NB-A* (Lin et al.) | Negotiation-based A*; 95% avg routability on FanoutNet's Huawei boards (69 min) | [P] |
| NCER | Negotiated escape router | [escape](escape-routing.md) |
| Negotiation-based layer assignment | Order barely matters | [layer assignment](layer-assignment-and-vias.md) |

OrthoRoute on PCBWorld D3-A: routability 0.53, CP 0.02, 99.7 DRVs at its default 0.4 mm grid with **board rules not enforced** (VP-corrected; structurally unfavourable) ([PCBWorld](pcbworld.md)).

**Formulation C — negotiated multi-layer grid router** (prototype `pathfinder_bench.py` in [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)):
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
Measured results of this prototype: see [solver benchmarks](../solvers/benchmarks.md) (pending section in the notes).

**Learning the schedule (VLSI, high transfer)**: offline conservative Q-learning chooses cost weights per iteration — **1.56× avg (3.01× max) faster convergence on ISPD19** at equal/better DRVs, some cross-technology generalization ([arXiv 2512.03594](https://arxiv.org/abs/2512.03594) [P-abs]); history-aware LSTM variant **−92% DRVs**, −10% runtime, pluggable into any cost-based router ([arXiv 2609.08232](https://arxiv.org/abs/2609.08232) [P-abs]).

**MAPF analogs** (CBS, PIBT, LaCAM) as alternative conflict-resolution engines: [cross-domain routing](cross-domain-routing-transplants.md).

## Recommendations for our system
- Implement PathFinder with VPR defaults inside the Rust A* router; window A* to the net bbox, growing per iteration; reroute only offenders [I].
- Expose the schedule (initial conflict cost, growth per pass, history weight, via-cost ramp, bbox factor) as a typed knob set; LLM picks presets per board class (dense 2-layer, BGA 6-layer, RF); later train an offline-RL scheduler on logged runs [I].
- Use a conflict-tolerant first pass as a seconds-scale feasibility probe (layer count, hotspot map) for placement/stackup revisions ([autorouter skepticism](autorouter-skepticism.md)) [I].
- LLM sets per-net-class cost multipliers and priorities, never paths ([cross-domain routing](cross-domain-routing-transplants.md)) [I].

## Conflicts and open questions
- No PCB-specific study of negotiation schedules; transfer of CQL/LSTM results from VLSI is unproven.

## Sources
- research notes: [routing_algorithms.md § Q1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [routing_classics_supplement.md § Q1, Q7, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_classics_supplement.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 1 row 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [algorithm-families](algorithm-families.md) · [ml-rl-routing](ml-rl-routing.md) · [net-ordering](net-ordering.md)
