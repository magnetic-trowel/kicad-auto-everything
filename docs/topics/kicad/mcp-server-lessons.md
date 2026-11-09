# Lessons from the leading KiCad MCP servers

Scope: the four mature servers (KMS, Konnect, PRO, POA): architecture, tool-surface findings, gating, mutation discipline, the POA A/B, bug classes, shipped placement/routing logic. Not here: our tool spec -> [mcp-tool-surface-spec.md](mcp-tool-surface-spec.md); their tests -> [mcp-server-testing-practices.md](mcp-server-testing-practices.md); ecosystem census and stars -> [../landscape/kicad-ai-tools-and-mcp-servers.md](../landscape/kicad-ai-tools-and-mcp-servers.md).
Keys: KMS, KiCAD-MCP-Server, Konnect, PRO, kicad-mcp-pro, POA, mcp-server-kicad, tool count, tool gating, progressive disclosure, list_changed, source tag, mutation discipline, dry run, expected_plan_revision, reliability contract, outcome classes, AmbiguousMutationError, POA A/B, MCP-only doctrine, bug classes, fix commits, Konnect retired placer

Servers compete on **source honesty, mutation discipline and tool gating**, not coverage; almost all write tools are raw (x, y, θ) CRUD over the same four channels (IPC, SWIG, `kicad-cli`, raw S-expressions) [P].

## The four codebases (cloned 2026-10-20)
| Server | License | Size / interface | Notes |
|---|---|---|---|
| mixelpixx/KiCAD-MCP-Server (KMS) v2.8.2 | MIT | 244 tools registered, 184 indexed in 17 categories, 32 "essential" surfaced first; no permission tier ("There is no router that hides tools"); TypeScript MCP + Python subprocess; SWIG + IPC (~22 IPC handlers; `delete_trace` still SWIG) | every response tagged `_backend: ipc` or `swig` and `_realtime`; `suggest_placement`, `route_pad_to_pad`, best-of-N Freerouting; GUI driver (11 tools) [P] |
| mixelpixx/Konnect | AGPL-3.0 + CLA + commercial | 228 tools in 21 toolsets + 7 meta-tools; Rust single binary; KiCad 10 IPC; S-expr schematics; `kicad-cli` | reliability contract; plan → apply; call log (ring of 100 + `calls.jsonl`); 6 skills, 2 agents [P] |
| oaslananka/kicad-mcp-pro (PRO) v4.3.0 | MIT | 387 tools, each annotated Read-Only/Destructive/Open-World/Idempotent/Headless/Requires-KiCad-Running; profiles `default` (24 read-only), `build`, `release`, `expert`, `full`; exactly three channels, **no SWIG** (enforced by script, ADR-0007) | output bounds 200 items, 50,000 characters; ImageContent returns; 7 skills [P] |
| ProductOfAmerica/mcp-server-kicad (POA) v0.21.1 | GPL-3.0-or-later since 2026-10-14 (MIT ≤0.20.1) | 109 tools across five servers; byte-preserving CST + `kicad-cli`; pcbnew subprocess only for `fill_zones` and `autoroute_pcb` | maintenance mode after its A/B; 6 skills [P] |

## Tool granularity
- Raw primitives dominate: `place_component(x,y,rot)`, `route_trace` "between XY points (single layer)", `add_via` [P].
- Mid-level ops are few: KMS `batch_move_components` ("transactional"), `route_pad_to_pad` (auto via), `route_differential_pair`, `copy_routing_pattern`, `add_gnd_stitching_vias`; Konnect `set_component_placements` ("one live KiCAD update and one undo step"). Inspection: `get_component_geometry` (separate bboxes for body, pads, courtyard, keepout, fab, silk, text), `get_ratsnest`, `check_placement_clearance` (body, courtyard, keepout, silk/text or pad conflicts) [P].
- **No server exposes a safe intent-level operation** ("place this group under these constraints and return a scored candidate"); where one existed (Konnect's planners) it was retired [I]. Konnect retired autonomous whole-board placement after five weeks; lesson: small explicit moves, each followed by scoring and DRC, scorer built before the placer [P] → [timeline](../landscape/open-source-placers.md#konnect-placement-timeline).

## Tool gating
[P]
- PRO expert profile: 387 tools, 227,578 characters, ≈56,895 tokens; default: 24 tools, 9,345 characters, ≈2,337 tokens (95.9% smaller; ~57k → 2.3k) ([snapshot](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/evidence/progressive-disclosure-profile-snapshot.json)).
- Konnect starter kit ~2K tokens vs ~23K for all tools. Its `list_toolboxes` → `load_toolset(name)` failed over stdio: "172 of 185 tools … were unreachable" until fixed, because `tools/list_changed` reached only HTTP/SSE clients ([dca61c0](https://github.com/mixelpixx/Konnect/commit/dca61c07be5498f0bd82b258e028908403eacf55)).
- Hosts that defer schemas: POA found "'place a 10k resistor' cost three tool_search calls"; its server instructions name the start tools and a test checks they exist.
- eda-agent "minimal" mode exposes only `tool_catalog` and `tool_invoke` for clients that cap tool counts.

Keep a small always-visible core named in the server instructions; use dynamic toolsets only when the client honours `list_changed` [I].

## State honesty and mutation discipline
[P]
- **Source tags:** KMS (`_backend`), Konnect (`source: ipc|saved_file`), PRO (`board_source`) converged independently on tagging every answer with its data source.
- **Plan → apply:** Konnect `update_pcb_from_schematic` and `update_footprints_from_library` default to dry run; apply needs the exact `expected_plan_revision`; "A successful apply is one KiCad undo entry". KMS `suggest_placement` is dry-run unless `apply=true`.
- **Konnect reliability contract** ([RELIABILITY_CONTRACT.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/RELIABILITY_CONTRACT.md)): outcome classes Complete, Partial, Refused/failed before mutation, Uncertain after possible mutation, Check unavailable. "Echoing the request is not evidence that the operation applied it." "Required unavailable evidence makes a design verdict incomplete." Reports "uncertain outcomes without blind rollback". PRO raises `AmbiguousMutationError` and enters a recovery-required state.
- **Empty ≠ unavailable:** PRO "empty data remains distinct from unavailable or unreadable board state"; Konnect "A null geometry field is unavailable evidence, not a zero-size pad".
- **Mislabelled outputs:** Konnect `check_clearance` returned anchor-to-anchor distance under a "physical clearance" description; a `21.125` answer "stood in for a courtyard gap of about 3 mm" (#410).
- **Collateral damage:** POA's board-sync tool "rewrote almost every footprint on the board, so the model undid its own work".
- **Off-by-one replies:** KMS replies shifted after a timeout ("every response after that was off by one"); requests now carry IDs.
- **Harness hooks:** POA plugin `hooks.json` blocks Read/Write/Edit on KiCad file extensions; its `pcb-layout` skill opens "NEVER use the Read, Write, or Edit tools on KiCad files … NEVER run kicad-cli commands via Bash". PRO had a similar "keep Claude PCB edits on MCP tools" commit.

Adopt [I]: source tags on every answer, plan → revision-bound apply, one undo per step, fail-closed refusals, outcome envelopes separating "check did not run" from "zero findings". Native KiCad operations first (`FlipItems`, `RefillZones`, commit groups); Konnect's filter: "native capability first, transparent AI-directed workflow second, Konnect-owned replacement only by deliberate exception" [P].

## POA maintenance-mode A/B (2026-10-19)
[P] ([README](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/README.md); [ad0230c](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/ad0230c95b1bfe8d50a35199cec2f179034ee576))
| Item | Value |
|---|---|
| Setup | same model (Claude Opus 5.5) with and without the plugin; judged by KiCad 10 (netlist, board, ERC, DRC) |
| Single edits | "Six single edits … three runs each. Plain Claude Code got all 18 right. With the plugin, 3 of 18 were right." |
| 20-edit session | both all right; plugin used "about 1.8 times as much context" |
| Causes | missing tools (a pad's net, the DNP flag, swapping one footprint); "never edit files" made the model stop and ask; board sync rewrote nearly every footprint |
| Conclusion | "Plain Claude Code changed a 2 MB board without reading it whole: it searched for the part and edited only the lines it needed." |
| Caveat | "small tests on one design"; materials unpublished |

→ Don't forbid raw file reads or `kicad-cli`; cover every edit class or allow a verified direct edit; bulk tools must not rewrite unrelated objects; skill text must not forbid the agent's general abilities [I].

## Recurring bug classes
Non-merge fix commits by subject keyword, KMS / Konnect / PRO / POA; total fixes 292 / 358 / 275 / 227 [P] ([kicad_mcp_codebases.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)).
| Class | Counts | Details |
|---|---|---|
| Rotation, flip, mirror, transform | 19 / 12 / 5 / 12 | [transform-math-pitfalls.md](transform-math-pitfalls.md) |
| Silent data loss on write | – | [file-format-and-version-hazards.md](file-format-and-version-hazards.md#silent-data-loss-on-write) |
| Stale or live divergence | 11 / 11 / 3 / 3 | [file-format…](file-format-and-version-hazards.md#live-versus-saved-divergence) |
| KiCad 10 compatibility | 13 / 7 / 7 / 3 | [file-format…](file-format-and-version-hazards.md#format-eras-and-dialects) |
| Nets | 15 / 14 / 7 / 20 | same |
| Units | 3 / 1 / 3 / 0 | same |
| DRC report parsing | 3 / 8 / 1 / 1 | [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md) |
| Freerouting round trip | 7 / 6 / 1 / 9 | [specctra-freerouting-integration.md](specctra-freerouting-integration.md) |
| Library tables | 28 / 43 / 6 / 11 | – |
| IPC transport | 15 / 27 / 4 / 0 | [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md) |
| Zone, pour, refill | 3 / 5 / 0 / 8 | – |

- Counts come from commit subjects and undercount POA's `test:`/`docs:` labelled fixes.
- Most of these bugs were found only by comparing against KiCad's own output (drill, Gerber, `kicad-cli` netlists, live readback), not by the projects' unit tests [P].

## Placement and routing logic shipped
- **Placement:** three force-directed spring embedders (KMS, Konnect, PRO), one HierPlace wrapper (KMS) → [../landscape/open-source-placers.md](../landscape/open-source-placers.md).
- **Routing:** in all four = Freerouting via DSN/SES + L-bend pad-to-pad helpers; Konnect's helper lays 1–2 segments on one layer, no via; KMS inserts a via automatically [P].
- **Skills and prompts:** POA six skills incl. `pcb-layout` (import netlist → board setup → place by function → route critical nets → autoroute the rest → refine (net classes, wider power traces, thermal vias, `remove_dangling_tracks`) → zones → DRC until clean; reviewer subagents check BOM and schematic plan); Konnect six skills with reference files for layers, trace widths, rules; PRO seven (`pcb-design`, `drc-check`, `visual-excellence`, …); KMS MCP prompts such as `component_placement_strategy` [P].

Differentiate on placement and routing quality and a tight verify loop (DRC, scores, renders), not tool count; split the surface into read/score, propose (never writes), apply (revision-bound, one undo) → [mcp-tool-surface-spec.md](mcp-tool-surface-spec.md) [I].

## Open questions
- Task success vs tool granularity is measured only by POA's small A/B; head-to-head trials (tools only, tools + escape hatches, coding agent only) on a shared corpus are needed.
- Token cost per board-read tool (e.g. a 400-footprint list): unmeasured by anyone.
- Issue threads (Konnect #595, #754; KMS #223, #406) known only through commits; GitHub issues returned 403.

## Sources
- [kicad_mcp_codebases.md § 1–3, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md); [verification_kicad_and_tools.md § 1 (#29–30), § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [existing_tools_and_apis.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- [KMS TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md), [Konnect tool-directory.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/tool-directory.md), [PRO ADR-0007](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/adr/0007-kicad-adapter-selection-and-swig-retirement.md)
