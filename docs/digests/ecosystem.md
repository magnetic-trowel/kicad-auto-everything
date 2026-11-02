# Digest: ecosystem (KiCad integration, existing tools, commercial systems, patents, licensing)

Scope: KiCad 10/11 API, CLI and DRC language; open routers, placers, MCP servers; commercial systems; patents; reuse licensing (status 2026-10-20). Not here: algorithms -> [algorithms](algorithms.md); evaluation -> [practice-evaluation](practice-evaluation.md); LLM interfaces -> [llm-data-ux](llm-data-ux.md). Ideas: [inventory](../ideas/inventory-ecosystem.md).
Keys: KiCad IPC API, KiCad 11, api-server, kipy, SWIG, kicad-cli, BoardSession, kicad_dru, DRC rule language, rule-name protocol, SES import, Specctra DSN, Freerouting 2.5.0, PCBWorld-Engine, KiCadRoutingTools, Konnect, MCP servers, tool gating, source tags, Quilter, DeepPCB, Cooper, GPT-6 Astra, patents, reuse matrix

## KiCad integration
- KiCad 10.0.x IPC is GUI-attached item CRUD with undoable commits: no DRC, rules, export or Specctra, no headless server; stackup read-only; zone refill whole-board and async. → [coverage](../topics/kicad/ipc-api-10-vs-11.md#coverage-matrix)
- KiCad 11 (~Q1 2027 [I]) adds headless `kicad-cli api-server`, `CustomRule` over IPC, DSN/SES and export jobs, and plans to drop SWIG. → [versions](../topics/kicad/ipc-api-10-vs-11.md#versions-and-cadence), [SWIG](../topics/kicad/kipy-and-swig-bindings.md#swig-pcbnew)
- 10.x backend: IPC commits, direct `.kicad_dru` writes, `kicad-cli pcb drc` on a saved copy as referee, SWIG helper for DSN/SES, behind a `BoardSession` abstraction. → [recipe](../topics/kicad/ipc-api-10-vs-11.md#10x-backend-recipe), [referee](../topics/kicad/kicad-cli.md#referee-command)
- DRC language (10.0): 35 constraint keywords, 23 functions; units only mm/mil/in/deg/ps/fs. → [grammar](../topics/kicad/drc-rule-language-reference.md#grammar-and-evaluation), [units](../topics/kicad/drc-rule-language-reference.md#units)
- Last matching rule wins, but net ties and pad/footprint overrides beat every custom rule. → [resolution](../topics/kicad/drc-rule-language-reference.md#clearance-resolution)
- `&&` binds looser than `||`: always parenthesise; a second `condition` silently overwrites the first. → [grammar](../topics/kicad/drc-rule-language-reference.md#grammar-and-evaluation)
- DRC JSON has no rule-name field: prefix rule names with IR IDs and map back. → [protocol](../topics/kicad/drc-report-and-repair-loop.md#rule-name-protocol)
- Built-in levers: component classes, multichannel Repeat Layout, Design Blocks, tuning profiles, "Attempt Finish Selected". → [levers](../topics/kicad/built-in-automation-features.md#lever-map)
- Numeric nets in KiCad 10 silently rebind, `SaveBoard` drops data, live and saved state diverge: use a byte-preserving file layer and source-tagged reads. → [dialects](../topics/kicad/file-format-and-version-hazards.md#format-eras-and-dialects), [data loss](../topics/kicad/file-format-and-version-hazards.md#silent-data-loss-on-write)
- Transform math is the most consistent MCP bug class: keep one oracle-pinned module ported from KiCad. → [transforms](../topics/kicad/transform-math-pitfalls.md#one-transform-module-oracle-pinned)

## Routing and placement tools
- Freerouting 2.5.0 is the open bulk baseline (CLI, REST, MCP, KiCad 10 IPC, 0–1000 scores); its release-note suite self-reports clean 30.9% → 75.0% by its own check, not KiCad DRC. → [interfaces](../topics/kicad/specctra-freerouting-integration.md#freerouting-interfaces-gpl-30-v250-2026-10-05), [benchmark](../topics/routing/freerouting.md#release-note-benchmark-v250)
- SES import in 10.0 deletes unlocked copper and applies SES placement; 10.0.7 silently skips unresolvable items. → [DSN/SES](../topics/kicad/specctra-freerouting-integration.md#kicad-side-dsnses)
- A Freerouting wrapper needs locked keep-copper, a pinned binary, `-mt 1`, keepout promotion and growth, and post-import KiCad DRC. → [wrapper](../topics/kicad/specctra-freerouting-integration.md#wrapper-tool-route_with_freerouting)
- Push-and-shove runs headless only via PCBWorld-Engine (GPLv3, 58 APIs, KiCad 9.0.8); KiCadRoutingTools and kicad-tools (MIT) add A*, diff pairs, fanout. → [routers](../topics/landscape/open-source-routers.md#router-table)
- No mature constraint-aware open placer exists; Konnect retired its whole-board placers: build the scorer first, make small moves, route the top-k to rank. → [placers](../topics/landscape/open-source-placers.md#headline-facts)
- LLMs must not emit copper: PCBWorld D3-A, GPT-5.4 interactive 0.65 / plan-then-execute 0.19 / engine-free 0.02 vs Freerouting 2.1.0 0.80; all LLMs 0.00 on D3-B. → [PCBWorld](../topics/routing/pcbworld.md#results-table-21-5)

## MCP servers and agent surface
- All seven tools one tester found that produced routed boards used Freerouting; the PCM has zero AI plugins. → [census](../topics/landscape/kicad-ai-tools-and-mcp-servers.md#scale), [test](../topics/landscape/kicad-ai-tools-and-mcp-servers.md#independent-hands-on-test-devbisme)
- "0 DRC" is weak: a no-tools board passed DRC while routing through the GND plane. → [facts](../topics/landscape/measured-tool-comparisons.md#headline-facts)
- Tool gating shrinks the catalogue ~96%; plain Claude Code got 18/18 edits right vs 3/18 MCP-only. → [gating](../topics/kicad/mcp-server-lessons.md#tool-gating), [A/B](../topics/kicad/mcp-server-lessons.md#poa-maintenance-mode-ab-2026-10-19)
- Adopt source tags, plan → revision-bound apply, one undo per step, outcome envelopes. → [discipline](../topics/kicad/mcp-server-lessons.md#state-honesty-and-mutation-discipline), [spec](../topics/kicad/mcp-tool-surface-spec.md#verification-hooks-on-every-apply)
- Testing: independent judge, negative controls, attempt accounting, tool-selection evals. → [adopt](../topics/kicad/mcp-server-testing-practices.md#what-we-adopt)

## Commercial systems and patents
- Quilter: RL proposals checked by solvers, synthetic data, 8 physics checks, lexicographic ranking, no public API; Speedrun's SOM placement was human. → [ranking](../topics/landscape/quilter.md#ranking-recommended-sort-lexicographic), [Speedrun](../topics/landscape/quilter.md#project-speedrun-dec-2025)
- DeepPCB: NN-guided SMC router plus LLM setup agent Cooper ("Nobody configures them"); not for DDR, length matching or RF. → [product](../topics/landscape/deeppcb.md#product)
- Siemens Fuse (MCP + Agent Skills), Flux (agent placement since Aug 2026), JITX, EasyEDA; GPT-6 Astra ran Freerouting. → [incumbents](../topics/landscape/commercial-incumbents-and-startups.md#incumbent-eda-vendors), [startups](../topics/landscape/commercial-incumbents-and-startups.md#startups-and-code-first-tools), [Astra](../topics/landscape/commercial-incumbents-and-startups.md#openai-gpt-6-astra-in-kicad-sept-2026)
- Shared pattern: LLM configures, engines construct, checkers judge, humans approve; no vendor lets an LLM lay copper. → [pattern](../topics/landscape/commercial-architecture-patterns.md#shared-division-of-labour)
- Patents: Cadence '699, '248; InstaDeep SMC order search '136; pending NVIDIA LLM-ReAct loop US 2025/0315590 (closest to us). → [patents](../topics/landscape/patents-watchlist.md#granted-and-pending-us-patents)

## Licensing
- GPL-3.0-or-later lets us vendor Freerouting, PCBWorld-Engine, kiutils and KiCad code; releases bundling Freerouting are GPL-3.0. → [rules](../topics/licensing/reuse-matrix.md#summary-rules)
- Avoid GPL-2.0-only, AGPL (reference only), non-commercial code, Triangle. → [matrix](../topics/licensing/reuse-matrix.md#file-tooling-solvers-geometry-simulation), [AGPL](../topics/licensing/kicad-and-gpl-ecosystem-notes.md#agpl-network-use-and-separate-programs)
- Boards ship as manifests (PCBench 54.3% unlicensed); rule packs CC0; weights from Apache-2.0-fit bases. → [data](../topics/licensing/data-rulepacks-weights.md#board-datasets), [gates](../topics/licensing/compliance-checklist.md#dependency-gates)

## What to build
- Build: comprehension agent, verified DRC compiler, scored constraint-aware placer, engine-grounded routing orchestration, checks beyond DRC, small MCP surface, open placement benchmark. → [stages](../topics/landscape/commercial-architecture-patterns.md#staged-design-implied-for-our-system), [benchmark](../topics/landscape/measured-tool-comparisons.md#benchmark-plan-for-our-system)
- Reuse: Freerouting, PNS via PCBWorld-Engine, KiCadRoutingTools, Cypress, kipy. → [routers](../topics/landscape/open-source-routers.md#router-choices-for-our-system)
