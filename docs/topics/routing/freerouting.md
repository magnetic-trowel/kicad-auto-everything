# Freerouting: internals, interfaces and current performance

Scope: Freerouting lineage, search internals, defaults, interfaces, self-reported and external benchmarks. Not here: how kae translates KiCad rules into DSN and relies on 2.5.0 behaviour -> [constraint bridge](freerouting-constraint-bridge.md); integration pitfalls -> [specctra-freerouting-integration](../kicad/specctra-freerouting-integration.md).
Keys: Freerouting, Specctra DSN, SES, expansion room, ExpansionDoor, DestinationDistance, MazeRipupResolver, MazeTraceShover, ItemSelectionStrategy, fanout, via_costs, start_ripup_costs, max_passes, -mp, -mt, improvement_threshold, -drc, -inc, REST API, MCP server, freerouting-client, nightly benchmark, tiers A–D, v2.5.0, 2.6.0-RC3, 2.6.0-RC4, #925, Issue 558

**Results**
1. GPL-3.0 Java router, Specctra DSN → SES; pipeline fanout → batch A* over convex expansion rooms with escalating rip-up → keep-or-undo optimizer.
2. De facto routability oracle of the placement literature (NS-Place, Cypress v1.9.0, ModuPlace, OmniLayout); strongest open rule-based router on PCBWorld D3-B, even at v2.1.0.
3. Self-reported clean rates more than doubled Sept–Oct 2026 (2.4.1 → 2.6.0-RC3), but part of the jump is a DRC-measurement fix, time budgets differ per version, suites differ, and "clean" is its own check, not KiCad DRC (→ [Nightly benchmark](#nightly-benchmark)).
4. Diff pairs and meanders parsed but not routed; fanout has no congestion analysis; rip-up escalation linear and "sub-optimal" per maintainers.
5. Headless CLI, REST server, MCP server, Docker, Python client; under GPL-3.0-or-later integrable in- or out-of-process.

## Lineage and releases

Alfons Wirtz (2004; GitHub 2014); v1.9.0 developers Andras Fuchs, Michael Hoffer, Andrey Belomutskiy, Alfons Wirtz; Eagle ULP credits an earlier design by Thomas Kaeubler; master ports 260 commits from Erik Gavriluk's C# "freerouting.net"; v2.4.1 (2026-09-03), v2.5.0 (2026-10-05), 2.6.0-RC4 nightly ([repo](https://github.com/freerouting/freerouting) [P]).

## Internals

[P]
- Search space: `FreeSpaceExpansionRoom`, `ObstacleExpansionRoom`, `ExpansionDoor`, `TargetItemExpansionDoor`, `Sorted45DegreeRoomNeighbours`, `SortedOrthogonalRoomNeighbours`; A* over convex rooms through doors, 45° or orthogonal ([expansion](https://github.com/freerouting/freerouting/tree/master/src/main/java/app/freerouting/autoroute/expansion); [architecture.md](https://github.com/freerouting/freerouting/blob/master/docs/architecture.md)).
- Heuristic `DestinationDistance`: admissible multi-layer lower bound from per-layer min trace costs (component side, solder side, inner) + min via costs; open list `SortedSet<MazeListElement>`.
- `MazeRipupResolver`: rip-up cost = `ripupCosts × costFactor` (obstacle half-width, contacts) / detour; randomized on passes ≥4 not multiples of 3; global linear escalation `startRipupCosts·(passNo+1)`: "sub-optimal" ([escape_congestion_research.md](https://github.com/freerouting/freerouting/blob/master/docs/research/escape_congestion_research.md)).
- `MazeTraceShover`; optimizer rips up and reroutes locally, keeping a change only if better.
- Ordering: `ItemSelectionStrategy` SEQUENTIAL/PRIORITIZED; fanout most-SMD-pins component first, outermost pins first ("breaks down for adjacent dense components"); fanout: "No congestion analysis of any kind", vias "at first feasible location".
- Rules: `DifferentialPair` (coupled spacing, max skew) parsed but unused by `autoroute`; `NetMeanderConstraint` (0.2–1.0 mm amplitude) model only.
- Defaults and scoring ([settings.md](https://github.com/freerouting/freerouting/blob/master/docs/settings.md); [scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)): via_costs 50, plane_via_costs 5, start_ripup_costs 100, preferred/undesired trace cost 1.0/2.5, max_passes 100, fanout max_passes 20. V2 router score 0–1000 minus penalties for incompletes and clearance violations scaled by D = max(1, pins × signal layers); optimizer score = excess length, vias, bends vs placement-derived lower bounds, gated by completeness and DRC.

## Interfaces

[P]
- **CLI** ([command_line_arguments.md](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md), stale on removed options): `java -jar freerouting.jar -de b.dsn -do b.ses -inc GND,VCC`. Flags: `-de` (DSN, optionally `+ses+rules`), `-do` (`.dsn`/`.ses`/`.scr`), `-dr`, `-drc` (KiCad-format JSON report, drc.v1), `-mp` (passes), `-mt` (optimizer threads; 0 = optimization off), `--router.optimizer.improvement_threshold` (default 2.5%), `-inc` (ignore net classes), `-im`, `--gui.enabled=false`, `-da` (disable anonymous analytics); strategy `-us GLOBAL_OPTIMAL` with `-is SEQUENTIAL|PRIORITIZED`. **Removed in 2.5.0:** `-hr` and the RANDOM/GREEDY/HYBRID strategies (corrected, VK).
- **Runtime:** JAR needs Java 25 (since v2.4.1; Java 25 JRE recommended); v2.5.0 adds GraalVM native binaries (Linux x64, macOS arm64/x64, Windows x64); Docker `ghcr.io/freerouting/freerouting`; arm/v7 conflict (README lists it, v2.2.2 notes say dropped).
- **Servers and clients:** REST API via `--api_server.enabled=true` (default `http://127.0.0.1:37864`, auth on by default); MCP server `npx @freerouting/freerouting-mcp-server`; Python `freerouting-client` (MIT); KiCad JSON writer; KiCad IPC research doc. Endpoints, headers, MCP tool and KiCad 10 IPC integration → [integration](../kicad/specctra-freerouting-integration.md#freerouting-interfaces-gpl-30-v250-2026-10-05).
- "Preserved traces … must retain their exact geometry": critical nets can be pre-routed and frozen. KiCad 11 adds DSN export/SES import RPCs → [PNS/IPC](kicad-pns-router.md#ipc-api-and-cli).

## Release-note benchmark (v2.5.0)

PCBench suite, 1,157 boards, v2.4.1 → v2.5.0 ([release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0); [verification_kicad_and_tools.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)) [P, self-reported, VK]: clean 358 (30.9%) → 868 (75.0%); fully routed 600 → 872 (75.4%); timeouts 78 → 78; total time 3,251 s → 2,997 s; Tier C (6+ layers) 49.2% clean; Tier D 50%. "Clean" = Freerouting's own check, not KiCad DRC. Differs from the nightly suite (1,142 fixtures; 2.5.0 Tier D 2/22 = 9.1%): tier definitions may differ, so name the suite wherever a rate is quoted.

## Nightly benchmark

2026-10-20, Ryzen 5 3600; [benchmarks.md](https://github.com/freerouting/freerouting/blob/master/scripts/benchmark/results/benchmarks.md) [P].

| Version | Fixtures | Clean (0 DRC) | Fully routed |
|---|---|---|---|
| 1.9.0 | 1,142 | 36.2% | 49.3% |
| 2.4.1 | 1,142 | 31.3% | 52.3% |
| 2.5.0 | 1,142 | 75.2% | 75.5% |
| 2.6.0-RC3 | 1,142 | 87.7% | 87.8% |
| 2.6.0-RC4 | 979 (tiers A+B only) | 92.4% | 92.5% |

- RC4 has no Tier C/D rows (979 = 452 + 527); tiers A+B alone: 2.5.0 80.4%, RC3 92.0%.
- Job time budgets: 360 min (1.9.0), 1–30 min (2.4.1), 5–45 min (2.5.0, RC1), 360–480 min (RC2–RC4).
- Tiers: A (452 two-layer canaries) 100% clean from RC1; B (527, 2–4 layers) 86.0% at RC4; C (141 dense/6+ layers) 69.5% at RC3 (49.6% → 69.5% when the budget grew to 360 min); D (22 stress boards) 13.6–18.2% (RC2/RC3; 2.5.0: 9.1%).
- Fixtures: PCBench-derived DSNs (the 2026-10-20 report lists all 1,142 under its PCBench group); notes also name DAC2020 bm01–bm11 and KiCad 10 demos.
- Caveats: "clean" = Freerouting's own clearance check; #925 removed false positives on composite pads and rounding noise (part of the jump is measurement); KiCad DSN export omits copper-to-edge clearance (Issue 558); PCBench treats KiCad DRC as arbiter ([pcbench README](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md)).
- Runtime profiles (2.5.0-RC9, [doc](https://github.com/freerouting/freerouting/blob/master/docs/research/large-board-autorouter-performance.md) [P]): Aleste-520EX (2210 pins, 2 layers) one 1748 s pass cut incompletes 1620 → 882; logicbone (8 layers) fanout 899 s; si31-3 router 640 s + optimizer 807 s; "pin count does not separate the slow boards from the fast ones"; full runs "a few minutes to several hours".

## External measurements

- PCBWorld (v2.1.0, `-mp 10`): best D3-B clean pass of all methods, 7–10 s/board; fewer vias and shorter WL than the human boards (D3-A at routability 0.91) → [PCBWorld](pcbworld.md#results-table-21-5), [skepticism](autorouter-skepticism.md#benchmark-evidence).
- FanoutNet (v1.4.5.1): 81%, >24 h on 4/5 HDI boards. Cypress used v1.9.0 two layers. DeepPCB marketing claims ("60–75%") conflict with these [V].
- kae measurements of 2.5.0 on our benchmark → [constraint bridge](freerouting-constraint-bridge.md#measured-effect).

## Use in kae

- Pin v2.5.0 (latest release, 2026-10-05; 2.6.x only RCs) until 2.6.0 is released, as bulk router, fallback and routability judge; re-score outputs with KiCad DRC; record version/flags in every benchmark [I].
- Final runs `-mt 1`: every run prints "Multi-threaded route optimization is broken and it is known to generate clearance violations" (POA sets `num_threads = 1`; KMS forces `-mt 1` in best-of-N → [integration pitfalls](../kicad/specctra-freerouting-integration.md#pitfalls-documented-by-the-four-mcp-codebases)) [P]. Fidelity knobs (`-mp`, `-mt 0` = optimizer off, improvement threshold) for fast probes only; budget minutes–hours on large boards; run as a JVM process [I].
- Freerouting is deterministic in DSN item order: the same DSN gives the same result; diversity comes from permuting item order (`--seed`) → [restart portfolio](../../research/routing/kae-restart-portfolio.md).
- Pre-route and lock SI-critical classes (pairs, matched groups, escape) before bulk; compensate weaknesses with LLM-set order hints, via costs, layer directions [I].
- Contribute or wrap improvements (congestion-aware fanout, negotiated rip-up schedule): code is GPL-3 and actively developed [I].

## Open questions

- No independent KiCad-DRC re-scoring of 2.5/2.6 on PCBWorld-Bench; the C# improvements' algorithmic content not reviewed.
- Release-note suite (1,157 boards) and nightly suite (1,142 fixtures) disagree on Tier D (50% vs 9.1% for 2.5.0) → [release-note benchmark](#release-note-benchmark-v250).
- Nightly fixtures and PCBWorld D3 both derive from PCBench, so newer versions may have been tuned on boards overlapping D3 [I].

## Sources

- [routing_algorithms.md § Q1, Q2, Q4, Q6, Q7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/routing_algorithms.md); [solver_toolbox.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [verification_papers.md § 2.1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
