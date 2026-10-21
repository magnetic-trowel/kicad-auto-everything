# Freerouting: internals, interfaces and current performance

**TL;DR**
- GPL-3.0 Java router, Specctra DSN → SES; pipeline **fanout → batch A* over convex expansion rooms with escalating rip-up → keep-or-undo optimizer**.
- De facto **routability oracle** of the placement literature (NS-Place, Cypress v1.9.0, ModuPlace, OmniLayout) and the strongest open rule-based router on PCBWorld D3-B (0.78 clean-pass with v2.1.0).
- It **improved sharply in Sept–Oct 2026**: own nightly "clean" rate 31–36% (v1.9/2.4.1) → 75.2% (2.5.0) → **92.4% (2.6.0-RC4)** — partly a DRC-measurement fix; "clean" is its own check, not KiCad DRC.
- Diff pairs and meanders are **parsed but not routed**; fanout has no congestion analysis; rip-up escalation is linear and "sub-optimal" per maintainers.
- Headless CLI, REST server, MCP server, Docker and a Python client exist; under GPL-3.0-or-later it can be integrated in-process or out-of-process.

## Key facts

**Lineage and releases**: Alfons Wirtz (2004; GitHub 2014); v1.9.0 developers Andras Fuchs, Michael Hoffer, Andrey Belomutskiy, Alfons Wirtz; Eagle ULP credits an earlier design by Thomas Kaeubler; master ports 260 commits from Erik Gavriluk's C# "freerouting.net"; v2.4.1 (2026-09-03), **v2.5.0 (2026-10-05)**, 2.6.0-RC4 nightly ([repo](https://github.com/freerouting/freerouting) [P]).

**Internals** [P]
- Search space: `FreeSpaceExpansionRoom`, `ObstacleExpansionRoom`, `ExpansionDoor`, `TargetItemExpansionDoor`, `Sorted45DegreeRoomNeighbours`, `SortedOrthogonalRoomNeighbours`; A* over convex rooms through doors, 45° or orthogonal ([expansion](https://github.com/freerouting/freerouting/tree/master/src/main/java/app/freerouting/autoroute/expansion); [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)).
- Heuristic `DestinationDistance`: admissible multi-layer lower bound from per-layer min trace costs (component side, solder side, inner) + min via costs; open list `SortedSet<MazeListElement>`.
- `MazeRipupResolver`: rip-up cost = `ripupCosts × costFactor` (obstacle half-width, contacts) / detour; randomized on passes ≥4 not multiples of 3; global linear escalation `startRipupCosts·(passNo+1)` — "sub-optimal" ([escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)).
- `MazeTraceShover`; optimizer rips up and reroutes locally, keeping a change only if better.
- Ordering: `ItemSelectionStrategy` SEQUENTIAL/PRIORITIZED; fanout most-SMD-pins component first, outermost pins first ("breaks down for adjacent dense components"); fanout: "No congestion analysis of any kind", vias "at first feasible location".
- Rules: `DifferentialPair` (coupled spacing, max skew) parsed but unused by `autoroute`; `NetMeanderConstraint` (0.2–1.0 mm amplitude) model only.

**Defaults and scoring** ([settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md); [scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md) [P]): via_costs 50, plane_via_costs 5, start_ripup_costs 100, preferred/undesired trace cost 1.0/2.5, max_passes 100, fanout max_passes 20. V2 router score 0–1000 minus penalties for incompletes and clearance violations scaled by D = max(1, pins × signal layers); optimizer score = excess length, vias, bends vs placement-derived lower bounds, gated by completeness and DRC.

**Interfaces** [P]: CLI `--gui.enabled=false -de in.dsn -do out.ses`, `-mp` (passes), `-mt` (optimizer threads; 0 = off), `--router.optimizer.improvement_threshold` (default 2.5%), `-drc` (KiCad-format JSON report), `-inc` (ignore net classes); REST API via `--api_server.enabled=true`; MCP server `npx @freerouting/freerouting-mcp-server`; Docker `ghcr.io/freerouting/freerouting`; Python `freerouting-client` (MIT); KiCad JSON writer; KiCad IPC research doc; Java 25 JRE recommended. "Preserved traces … must retain their exact geometry" → critical nets can be pre-routed and frozen. KiCad 11 adds DSN export/SES import RPCs ([PNS/IPC](kicad-pns-router.md)).

**Nightly benchmark** (2026-10-20, Ryzen 5 3600; [benchmarks.md](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md) [P])
| Version | Fixtures | Clean (0 DRC) | Fully routed |
|---|---|---|---|
| 1.9.0 | 1,142 | 36.2% | 49.3% |
| 2.4.1 | 1,142 | 31.3% | 52.3% |
| 2.5.0 | 1,142 | 75.2% | 75.5% |
| 2.6.0-RC3 | 1,142 | 87.7% | 87.8% |
| 2.6.0-RC4 | 979 | 92.4% | 92.5% |

Tiers: A (452 two-layer canaries) 100% clean from RC1; B (527, 2–4 layers) 86.0% at RC4; C (141 dense/6+ layers) 69.5% at RC3; **D (22 stress boards) 13.6–18.2%**. Fixtures: ~1,143 PCBench-derived DSNs, DAC2020 bm01–bm11, KiCad 10 demos. Caveats: "clean" = Freerouting's own clearance check; #925 removed false positives on composite pads and rounding noise (part of the jump is measurement); KiCad DSN export omits copper-to-edge clearance (Issue 558) — PCBench treats KiCad DRC as arbiter ([pcbench README](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md)).

**Runtime profiles** (2.5.0-RC9, [doc](https://github.com/freerouting/freerouting/blob/master/docs/research/large-board-autorouter-performance.md) [P]): Aleste-520EX (2210 pins, 2 layers) one 1748 s pass cut incompletes 1620 → 882; logicbone (8 layers) fanout 899 s; si31-3 router 640 s + optimizer 807 s; "pin count does not separate the slow boards from the fast ones". Full runs "a few minutes to several hours".

**External measurements**: PCBWorld (v2.1.0, `-mp 10`): D3-A CP 0.80 (routability only 0.91), D3-B 0.78, 7–10 s/board; WL 156 mm and 0.74 vias beat the human reference (170 mm, 1.18) ([PCBWorld](pcbworld.md)). FanoutNet (v1.4.5.1): 81%, >24 h on 4/5 HDI boards. Cypress used v1.9.0 two layers. DeepPCB marketing claims ("60–75%") conflict with these [V].

## Recommendations for our system
- Ship Freerouting latest 2.6.x, **pinned**, as bulk router, fallback and routability judge; re-score outputs with KiCad DRC; record version/flags in every benchmark [I].
- Use fidelity knobs in loops (`-mp`, `-mt 0`, improvement threshold); budget minutes–hours on large boards; run as a JVM process (simplest) even though GPL-3.0-or-later now allows tighter integration [I].
- Pre-route and lock SI-critical classes (pairs, matched groups, escape) before bulk; compensate known weaknesses with LLM-set order hints, via costs, layer directions [I].
- Contribute or wrap improvements (congestion-aware fanout, negotiated rip-up schedule) — the code is GPL-3 and actively developed [I].

## Conflicts and open questions
- No independent KiCad-DRC re-scoring of 2.5/2.6 on PCBWorld-Bench; the C# improvements' algorithmic content was not reviewed.

## Sources
- research notes: [routing_algorithms.md § Q1, Q2, Q4, Q6, Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [kicad-pns-router](kicad-pns-router.md) · [pcbworld](pcbworld.md) · [benchmarks-and-datasets](benchmarks-and-datasets.md) · [algorithm-families](algorithm-families.md)
