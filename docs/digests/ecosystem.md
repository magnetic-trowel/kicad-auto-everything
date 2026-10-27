# Digest: ecosystem (KiCad integration, existing tools, commercial systems, patents, licensing)

Status as of 2026-10-20. Code is GPL-3.0-or-later. Detail and sources are in the linked topic docs; the full idea list is in [inventory-ecosystem.md](../ideas/inventory-ecosystem.md).

## KiCad integration
- **KiCad 10.0.x IPC is GUI-attached CRUD with undoable commits.** It has no DRC run, rules, export, headless mode, Specctra, or routing and placement calls. The stackup is read-only, and zone refill is whole-board and asynchronous. → [ipc-api-10-vs-11](../topics/kicad/ipc-api-10-vs-11.md)
- **KiCad 11 (~Q1 2027) adds** headless `kicad-cli api-server`, rules over IPC, DSN/SES and export jobs, and removes SWIG. Build a backend abstraction now. → [ipc-api-10-vs-11](../topics/kicad/ipc-api-10-vs-11.md), [kipy-and-swig-bindings](../topics/kicad/kipy-and-swig-bindings.md)
- **The 10.x backend has four channels:** IPC commits, direct `.kicad_dru` writes, `kicad-cli pcb drc` JSON as the referee, and a SWIG helper for DSN/SES. → [kicad-cli](../topics/kicad/kicad-cli.md)
- **DRC rule language: 35 constraints, 23 functions.** Units are only mm/mil/in/deg/ps/fs. The last matching rule wins, but net ties and pad/footprint clearance overrides beat every rule. `&&` binds looser than `||`, so always parenthesise. A second `condition` silently overwrites the first. The JSON report has no rule-name field, so map violations back through IR-ID rule names. → [drc-rule-language-reference](../topics/kicad/drc-rule-language-reference.md), [drc-report-and-repair-loop](../topics/kicad/drc-report-and-repair-loop.md)
- **KiCad's built-in levers** are component classes, multichannel Repeat Layout (topology matching), Design Blocks, tuning profiles and "Attempt Finish Selected". → [built-in-automation-features](../topics/kicad/built-in-automation-features.md)
- **KiCad 9→10 dialects silently miswire boards** (numeric nets rebind), `SaveBoard` drops data, and live versus saved state diverges. Use a byte-preserving file layer and source-tagged reads. → [file-format-and-version-hazards](../topics/kicad/file-format-and-version-hazards.md)
- **Transform math is the commonest MCP bug** (textbook rotation; absolute child coordinates over IPC). Keep one oracle-tested module, ported from KiCad. → [transform-math-pitfalls](../topics/kicad/transform-math-pitfalls.md)

## Routing and placement tools
- **Freerouting 2.5.0 is the open bulk-routing baseline:** REST, MCP, KiCad 10 IPC, 0–1000 scores, and a self-reported 30.9%→75.0% clean rate (release-note suite, 1,157 boards; its own check, not KiCad DRC). **SES import in 10.0 is destructive**, and 10.0.7 silently skips items it cannot resolve. A wrapper needs best-of-N, `-mt 1`, keepout growth and more. → [specctra-freerouting-integration](../topics/kicad/specctra-freerouting-integration.md)
- **KiCad's push-and-shove router runs headlessly via PCBWorld-Engine** (GPLv3, 58 APIs; pinned to KiCad 9.0.8). KiCadRoutingTools and kicad-tools (MIT) add A*, diff pairs and fanout. → [open-source-routers](../topics/landscape/open-source-routers.md)
- **No constraint-aware open placer exists.** Cypress (Apache-2.0) and kicad-tools are the building blocks. Konnect retired its whole-board placers, so build the scorer first and prefer small explicit moves. HPWL cannot rank near-equal candidates; route the top-k. → [open-source-placers](../topics/landscape/open-source-placers.md)
- **LLMs must not emit copper.** In PCBWorld, GPT-5.4 scored 0.65 clean-pass interactive, 0.19 plan-then-execute and 0.02 engine-free; Freerouting 2.1.0 scored 0.80 (D3-A, @5, 4-seed mean). All LLMs scored 0.00 on D3-B (10 evaluated boards). → [measured-tool-comparisons](../topics/landscape/measured-tool-comparisons.md)

## MCP servers and agent surface
- **Hundreds of KiCad AI repos exist, but all seven tools one tester found that produced routed boards used Freerouting.** There are zero AI plugins in the PCM. A no-tools baseline passed DRC while routing through the GND plane. → [kicad-ai-tools-and-mcp-servers](../topics/landscape/kicad-ai-tools-and-mcp-servers.md)
- **MCP lessons:** tool gating saves about 95% of catalogue tokens. "MCP-only, never touch files" lost 3/18 vs 18/18 in a small test. Adopt source tags, plan → revision-bound apply, one undo per step, and outcome envelopes. → [mcp-server-lessons](../topics/kicad/mcp-server-lessons.md), [mcp-tool-surface-spec](../topics/kicad/mcp-tool-surface-spec.md)
- **Testing:** use an independent judge, negative controls, attempt accounting and tool-selection evals. → [mcp-server-testing-practices](../topics/kicad/mcp-server-testing-practices.md)

## Commercial systems and patents
- **Quilter:** RL plus solvers; Comprehension heuristics; 8 physics checks; lexicographic ranking. Speedrun's SOM placement was human. It has no API. → [quilter](../topics/landscape/quilter.md)
- **DeepPCB:** an SMC-guided RL router with an LLM setup agent, Cooper. "Autorouters don't fail at routing. Nobody configures them." It excludes DDR and length matching. → [deeppcb](../topics/landscape/deeppcb.md)
- **Incumbents and startups:** Cadence, Zuken, Siemens (Fuse, MCP + Skills), Flux (placement and MCP since Aug 2026), JITX, EasyEDA. The GPT-6 Astra demo actually ran Freerouting. → [commercial-incumbents-and-startups](../topics/landscape/commercial-incumbents-and-startups.md)
- **Shared pattern:** the LLM configures, engines construct, checkers rank, humans approve. That implies a staged pipeline for us. → [commercial-architecture-patterns](../topics/landscape/commercial-architecture-patterns.md)
- **Patent watch:** Cadence RL and learned routability ('699, '248); InstaDeep SMC net-order search; pending NVIDIA LLM-ReAct constraint loop (US 2025/0315590). Prefer orchestrating classical engines. → [patents-watchlist](../topics/landscape/patents-watchlist.md)

## Licensing
- **GPL-3.0-or-later code** can vendor or link Freerouting, PNS, SWIG, kiutils and the POA server. Avoid GPL-2.0-only, AGPL (reference only), non-commercial code and Triangle. → [reuse-matrix](../topics/licensing/reuse-matrix.md), [kicad-and-gpl-ecosystem-notes](../topics/licensing/kicad-and-gpl-ecosystem-notes.md)
- **Data and non-code:** boards ship as manifests (PCBench is 54% unlicensed); rule packs are CC0 restated facts; weights come only from Apache/MIT bases. → [data-rulepacks-weights](../topics/licensing/data-rulepacks-weights.md), [compliance-checklist](../topics/licensing/compliance-checklist.md)

## What to build
- **Build:**
  - an LLM comprehension and configuration agent;
  - a verified DRC compiler;
  - a constraint-aware placer with an independent scorer;
  - engine-grounded routing orchestration;
  - layout-quality checks beyond DRC;
  - a small verified MCP surface;
  - an open placement benchmark.
- **Reuse:** Freerouting, PNS (via PCBWorld-Engine, KiCad 9.0.8 only), KRT, Cypress and kipy.
- → [commercial-architecture-patterns](../topics/landscape/commercial-architecture-patterns.md), [mcp-tool-surface-spec](../topics/kicad/mcp-tool-surface-spec.md)
