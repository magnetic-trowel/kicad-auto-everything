# Specctra DSN/SES and Freerouting integration with KiCad

Scope: DSN/SES paths per KiCad version, SES import semantics, Freerouting CLI/REST/MCP interfaces, integration pitfalls (MCP servers and our benchmark), the wrapper tool. Not here: Freerouting internals and performance -> [../routing/freerouting.md](../routing/freerouting.md); score formulas -> [../verification/quality-metrics.md](../verification/quality-metrics.md); router survey -> [../landscape/open-source-routers.md](../landscape/open-source-routers.md).
Keys: Specctra, DSN, SES, ExportSpecctraDSN, ImportSpecctraSES, SES destructive, partial import, Freerouting 2.5.0, -mt 1, best-of-N, hole keepout, SES resolution, net-name reconciliation, placement block, Java 25, GraalVM, REST /v1/autoroute, autoroute_board, Freerouting-Environment-Host, V2_CONTINUOUS, pipe in net name, unsized netclass, power layers, route_with_freerouting

## KiCad side (DSN/SES)
| | 10.0 | master (KiCad 11) |
|---|---|---|
| DSN export | GUI `pcbnew.EditorControl.exportSpecctraDSN`, `RunAction`, SWIG `ExportSpecctraDSN(board, path)`; 10.0.6 fixed quoting, duplicate-reference, layer-name bugs | `kicad-cli pcb export specctra` (2026-10-14); IPC `RunBoardJobExportSpecctraDsn` |
| SES import | GUI `importSpecctraSession`, `RunAction`, SWIG `ImportSpecctraSES` | IPC `ImportSpecctraSession` ("Since 11.0") |
| SES semantics | **Deletes all unlocked tracks, vias and DRC markers; re-adds locked ones; applies the SES placement (moves and flips footprints)**. The 10.0 doc NOTE ("only adds routing; it does not modify footprints") is wrong (corrected, VK) ([pcbnew_importing.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_importing.adoc)) | proto comment matches the code |
| Partial failure | 10.0.0 aborted on an unknown reference ("Reference '%s' not found."). **10.0.7 skips any place, wire or via with an unknown reference, layer or padstack, logs only a warning, reports success**; wires on an unknown net land on net 0 | – |

Source: [specctra_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/specctra_import_export/specctra_import.cpp) [P]. Verify item counts, connectivity and DRC after every import [I]. Freerouting 2.5.0 also has its own KiCad 10 IPC integration (below).

- **Konnect** writes its own fail-closed Rust DSN exporter from the IPC snapshot with a reverse manifest, plus an optional ActionPlugin bridge to `pcbnew.ExportSpecctraDSN`. It rejects boards with copper zones or rule areas, existing arcs, or unlocked tracks and vias; two layers only (4+ layers on the roadmap) [P] ([specctra.rs](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect-core/src/specctra.rs)).
- **Other DSN/SES speakers:** every commercial router (Allegro PCB Router, Electra, TopoR, PCB Auto Router), fastroute, EasyEDA's fork, LibrePCB ≥1.2.0 → a good DSN doubles as a socket for user-supplied routers [P].

## Freerouting interfaces (GPL-3.0; v2.5.0, 2026-10-05)
- **CLI flags, runtime (Java 25 since v2.4.1, GraalVM binaries), options removed in 2.5.0** → [../routing/freerouting.md](../routing/freerouting.md#interfaces). Integration-level flags: `-de`/`-do` for DSN in, SES out; `-drc` writes drc.v1; `-mt 1` in final runs; `-da` disables analytics; `--gui.enabled=false` for headless. [P].
- **REST** ([API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md)) [P]:
  - required headers `Freerouting-Profile-ID` (UUID), `Freerouting-Environment-Host` (e.g. `KiCad/10.0`; 400 if missing); Bearer auth unless disabled;
  - sessions and jobs: enqueue, settings, start, cancel, logs and stream, input and rules upload, output (202 with partial output while running);
  - `GET /jobs/{id}/drc[?compact=true]`, `/drc/summary` (drc.v1 format, [report](drc-report-and-repair-loop.md#schema-drcv1json-identical-on-100-and-master));
  - `POST /v1/autoroute` takes `file_content`, `rules_content`, `session_content`, `output_formats`, `timeout_seconds`, `router_settings`;
  - MCP at `POST /v1/mcp`; A2A card `/.well-known/agent.json`.
- **MCP** ([MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md)): `autoroute_board(filePath|fileContent, rulesPath, sessionPath, outputFormats ["SES","DRC_SUMMARY"], timeoutSeconds)` + multi-turn session workflow; npm `@freerouting/freerouting-mcp-server` 2.5.0 is GPL-3.0-only [P].
- **KiCad 10 IPC (v2.5.0):** "direct Protocol Buffers IPC integration for KiCad 10+", progress dialog (Fanout, Autoroute, Optimize), routing in a separate process, "fallback to the battle-tested Specctra DSN/SES pipeline". v2.4.1: "the Specctra DSN/SES path is still the recommended production route" [P]. Freerouting announced removing SWIG plugin support in the next release.
- **Scores:** `V2_CONTINUOUS` (0–1000) and `V2_LOWER_BOUND` (length vs a Manhattan MST, vias vs a per-net minimum, bends vs a minimum); incomplete nets and DRC hits are vetoes → formula in [../verification/quality-metrics.md](../verification/quality-metrics.md) [P] ([scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)).
- **Clean-board rate** (self-reported, two suites) → [../routing/freerouting.md](../routing/freerouting.md#release-note-benchmark-v250).

## Pitfalls documented by the four MCP codebases
| Pitfall | Fix | Source |
|---|---|---|
| SES `(resolution um 10)` declares a grid, not a multiplier; PRO's coordinates came out 10× too small | PRO uses 1 mm = 1000 units, Y negated, no offset. **Conflicts with KiCad's importer**: nm = value × unit ÷ resolution, i.e. 1 mm = 10,000 units at `(resolution um 10)` (`scale()` in specctra_import.cpp). Use KiCad's rule; test on a real Freerouting SES | [PRO 565a0203](https://github.com/oaslananka/kicad-mcp-pro/commit/565a02030d68cdb2b0bcddd325f5f5a1014ef66f) [P] |
| Internal Edge.Cuts holes become keepouts cleared at track clearance (0.2 mm), not edge clearance (0.5 mm); `router.copper_to_edge_clearance_um` "does not change this (byte-identical SES)" | grow circular keepouts by the difference, sized by apothem; test board 8 violations → 0 | [KMS da8ff18](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/da8ff187816d5b7adabfe3680c93d125edd0c1fe) [P] |
| Net names lose their leading `/` through SES (#246) | reconcile on import | [KMS 8c84fe9](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/8c84fe9862c38c9ba24614d8f78606e6d9947a4f) [P] |
| `.kicad_pro` netclasses missing from the DSN (#302) | export them | [KMS 711b0fe](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/711b0fe31ded406eb72e21654626b8fd6f2c0eeb) [P] |
| SES `(placement …)` block aborts import when duplicate `REF**` references were renamed (10.0.0; 10.0.7 skips the unknown reference with a log warning) | strip the placement block | [KMS f476a97](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f476a9794daaa323e9020010b5d09376c680bbd4) [P] |
| `False == 0` let failed import/export report success | check strictly; on 10.0.7 also verify counts, connectivity, DRC after import and capture wx log warnings | same [P] |
| Wrong Java runtime | read the required version from the JAR's class-file major version (2.4.x needs Java 25); Docker (`eclipse-temurin:<N>-jre`) or Podman fallback | [KMS 356be10](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/356be10abf0acf209d961ca9505a9fa8c4ebe9c1) [P] |
| Stale SES files | guard; stage artifacts in a temp dir | [KMS a7b4901](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/a7b49012d11673785cafa4dba7f03b6dc4618aea) [P] |
| Multi-threaded optimizer warns of clearance violations ([quote](../routing/freerouting.md#use-in-kae)) | `num_threads = 1`; KMS forces `-mt 1` in best-of-N | [POA pcb.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/mcp_server_kicad/pcb.py) [P] |
| "On dense boards a single Freerouting run routinely leaves 1–7 nets unrouted" | best-of-N varying `--max-passes`; score = `nets_routed·1000 + segments`, +50,000 if all target nets route; "3 attempts is usually enough for 4-layer designs; 5–8 for stubborn cases" (ported from morningfire-pcb-automation, MIT) | [KMS CHANGELOG](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/CHANGELOG.md) [P] |
| Footprint-level keepouts ignored | promote to board level before export (POA) | POA pcb.py [P] |
| Footprint text displaced after import | fix after import (POA) | same [P] |
| Board-edge clearance missing in KiCad exports | `--router.copperToEdgeClearanceUm` (v2.3.0 workaround) | [releases](https://github.com/freerouting/freerouting/releases) [P] |

## Pitfalls seen in our benchmark (KiCad 10.0.7, Freerouting 2.5.0)
Reproduced on corpus boards; `bench/src/kaebench/adapters.py` (`Freerouting`) handles each [P].
| Pitfall | Fix |
|---|---|
| Bare net name with `\|` (e.g. `ADD\|SUB`) passes through DSN and Freerouting, then KiCad's SES import fails the whole session with no message | quote every bare `(net …)` name in the SES |
| `.kicad_pro` netclass without track width, via diameter or drill exports `(width -0.001)` and padstack `Via[0-1]_-0.001:-0.001_um`; 2.5.0 draws zero-width tracks and vias | raise widths to the board minimum; resize and rename unsized via padstacks (KiCad reads the drill from the name) |
| All copper layers are KiCad "power" layers → `(type power)` only; Freerouting refuses ("all layers are disabled") and 2.5.0 then hangs instead of exiting | export those layers as `signal` (KiCad routes tracks on power layers) |

## How the four servers run it
Shared core: `java -jar <jar> -de <dsn> -do <ses> -mp <passes>`.
- **POA:** pin Freerouting 2.5.0 by SHA-256 → promote footprint keepouts → `pcbnew.ExportSpecctraDSN` in a subprocess → route → import into a **new** `<stem>_routed.kicad_pcb` → fix displaced text → `kicad-cli pcb drc --format json`; reports `traces_added`, `vias_added`, `drc_violations`, `drc_unconnected`.
- **Konnect:** `export_specctra_dsn` (revision-bound DSN + reverse manifest) → `route_specctra_dsn` (Freerouting's native headless MCP server as a loopback-only child, always reaped) → `plan_specctra_ses_import` → `apply_specctra_ses` (keeps locked copper, applies "through KiCad IPC as one undo transaction", verifies by post-commit readback, builds a separate candidate board, reports DRC).
- **PRO:** headless SES apply through a transactional board writer (`router_core.apply_ses_to_pcb`).
- **KMS:** Java or Docker; best-of-N with `attempts`, `targetNets`, `passSchedule`.

## Wrapper tool: route_with_freerouting
Expose one tool, `route_with_freerouting(board, nets_subset?, timeout)`, returning scores and a compact DRC summary, never geometry [I, from VK]:
1. Lock every track and via to keep (critical nets, earlier routes) before export.
2. Export DSN: SWIG helper on 10.x; `kicad-cli pcb export specctra` or IPC on 11.
3. `POST /v1/autoroute` on a **local** server (auth disabled, `Freerouting-Environment-Host: KiCad/10.0`), or the CLI with `-da`. Hash-pinned binary, `-mt 1`, best-of-N.
4. Strip or match the SES placement block; import SES into a candidate board; check item counts and connectivity. `ImportSpecctraSession` ends with `BOARD::BuildConnectivity`, which moves copper that touches a single pad onto that pad's net, kept pre-routes included; kae restores those nets and compares the session's wires and vias per net with what landed (`kae.route.bridge.import_session`; [kae-board-model](../../research/placement/kae-board-model.md#writing-boards)) [C].
5. Refill zones (async on 10.0, poll), run `kicad-cli pcb drc`; put the post-import DRC delta in the score; diff KiCad DRC vs Freerouting drc.v1 to expose DSN translation losses (e.g. the edge-clearance gap).
6. Return `normalized_score`, `optimizer_score`, unrouted count, compact DRC summary.

Pin and benchmark against Freerouting 2.5.0 (latest release; 2.6.x only RCs), not PCBWorld's 2.1.0 baseline [I]. Licensing (GPL-3.0-only Freerouting may be vendored, forked or bridged in-process; combined distribution GPL-3.0; 2014 provenance unclear by community hearsay; don't upstream Freerouting-derived code into KiCad) → [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md) [I].

## Open questions
- Freerouting 2.5's KiCad 10 IPC path (which plugin mechanism? DRC fidelity?) not independently evaluated.
- KiCad DRC fidelity lost on the DSN round trip: unmeasured.

## Sources
- [verification_kicad_and_tools.md § 1 (#9–11, #23–26), § 4 Freerouting, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [kicad_mcp_codebases.md § 2F, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md); [existing_tools_and_apis.md § 1, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md); [licensing.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- [Freerouting README](https://github.com/freerouting/freerouting), [v2.5.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0), [integrations.md](https://github.com/freerouting/freerouting/blob/master/docs/integrations.md)
