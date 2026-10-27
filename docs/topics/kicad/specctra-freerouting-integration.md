# Specctra DSN/SES and Freerouting integration with KiCad (how to drive it, pitfalls)

**TL;DR**
- **DSN/SES paths by version:**
  - 10.0: GUI action, `RunAction`, or SWIG `ExportSpecctraDSN`/`ImportSpecctraSES`.
  - KiCad 11 adds `kicad-cli pcb export specctra` and the IPC calls `RunBoardJobExportSpecctraDsn`/`ImportSpecctraSession`.
  - Freerouting 2.5.0 adds its own KiCad 10 IPC integration [P].
- **SES import in 10.0 is destructive.** It deletes all unlocked tracks and vias and all DRC markers, and **applies the SES placement**, moving and flipping footprints. The user doc says otherwise (corrected, VK) [P].
  - **On 10.0.7 it can partially fail and still report success.** 10.0.0 aborted on an unknown reference; 10.0.7 skips any place, wire or via with an unknown reference, layer or padstack and only logs a warning. Wires on an unknown net land on net 0. Verify item counts, connectivity and DRC after every import [P] ([specctra_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/specctra_import_export/specctra_import.cpp)).
- **Freerouting v2.5.0 (2026-10-05):**
  - REST `POST /v1/autoroute` and MCP `autoroute_board`.
  - Compact DRC in KiCad drc.v1 format; scores on a 0–1000 scale; GraalVM native binaries.
  - Clean-board rate on its release-note suite (1,157 boards) rose from 30.9% (2.4.1) to 75.0% (self-reported; "clean" is Freerouting's own check, not KiCad DRC). The nightly suite (1,142 fixtures) differs; see [../landscape/measured-tool-comparisons.md](../landscape/measured-tool-comparisons.md).
  - `-hr` and the RANDOM/GREEDY/HYBRID strategies were removed (corrected, VK) [P].
- **A Freerouting wrapper silently fails on real boards unless it handles:** best-of-N, `-mt 1`, hole-keepout growth, SES placement stripping, netclass export, net-name reconciliation, SES units, Java detection and lock-before-import [P].
- **Expose one tool to the LLM** that returns scores and a compact DRC summary, never geometry [I].

## Key facts

### KiCad side
| | 10.0 | master (KiCad 11) |
|---|---|---|
| DSN export | GUI `pcbnew.EditorControl.exportSpecctraDSN`, `RunAction`, or SWIG `ExportSpecctraDSN(board, path)`; 10.0.6 fixed quoting, duplicate-reference and layer-name bugs | `kicad-cli pcb export specctra` (2026-10-14); IPC `RunBoardJobExportSpecctraDsn` |
| SES import | GUI `importSpecctraSession`, `RunAction`, or SWIG `ImportSpecctraSES` | IPC `ImportSpecctraSession` ("Since 11.0") |
| SES semantics | **Deletes unlocked tracks, vias and markers; re-adds locked ones; applies placement** ([specctra_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/specctra_import_export/specctra_import.cpp)). The 10.0 doc NOTE ("only adds routing; it does not modify footprints") is wrong ([pcbnew_importing.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_importing.adoc)) | The proto comment matches the code |

Other implementations:
- **Konnect** writes its own fail-closed Rust DSN exporter from the IPC snapshot, with a reverse manifest, and an optional ActionPlugin bridge to `pcbnew.ExportSpecctraDSN`. The exporter rejects boards with copper zones or rule areas, existing arcs, or unlocked tracks and vias, and supports two layers only (roadmap) [P] ([specctra.rs](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect-core/src/specctra.rs)).
- **Others speaking DSN/SES:** every commercial router (Allegro PCB Router, Electra, TopoR, PCB Auto Router), plus fastroute, EasyEDA's fork and LibrePCB ≥1.2.0. A good DSN therefore doubles as a socket for user-supplied routers [P]. See [../landscape/open-source-routers.md](../landscape/open-source-routers.md).

### Freerouting interfaces (GPL-3.0; latest v2.5.0)
- **CLI** ([doc](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md), stale on removed options):
  - Example: `java -jar freerouting.jar -de b.dsn -do b.ses -inc GND,VCC`.
  - `-de` (DSN, optionally `+ses+rules`), `-do` (`.dsn`/`.ses`/`.scr`), `-dr`, `-drc` (KiCad JSON), `-mp` (passes), `-mt` (threads; 0 disables optimization).
  - `--router.optimizer.improvement_threshold` (default 2.5%), `-inc`, `-im`, `--gui.enabled=false`, `-da` (disable anonymous analytics).
  - Strategy: `-us GLOBAL_OPTIMAL` with `-is SEQUENTIAL|PRIORITIZED`.
  - API server default `http://127.0.0.1:37864`, with auth on by default [P].
- **Runtime:** the JAR needs Java 25 (since v2.4.1). v2.5.0 adds GraalVM native binaries for Linux x64, macOS arm64/x64 and Windows x64 [P]. Docker images exist; arm/v7 is a conflict (the README lists it, v2.2.2 notes say dropped).
- **REST** ([API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md)):
  - Required headers: `Freerouting-Profile-ID` (UUID) and `Freerouting-Environment-Host` (e.g. `KiCad/10.0`; 400 if missing). Bearer auth unless disabled.
  - Sessions and jobs: enqueue, settings, start, cancel, logs and stream, input and rules upload, output (202 with partial output while running).
  - `GET /jobs/{id}/drc[?compact=true]` and `/drc/summary`.
  - `POST /v1/autoroute` takes `file_content`, `rules_content`, `session_content`, `output_formats`, `timeout_seconds` and `router_settings`.
  - MCP at `POST /v1/mcp`; A2A card at `/.well-known/agent.json` [P].
- **MCP** ([MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md)): `autoroute_board(filePath|fileContent, rulesPath, sessionPath, outputFormats ["SES","DRC_SUMMARY"], timeoutSeconds)`, plus a multi-turn session workflow. The npm package `@freerouting/freerouting-mcp-server` 2.5.0 is GPL-3.0-only [P].
- **KiCad 10 IPC (v2.5.0):** "direct Protocol Buffers IPC integration for KiCad 10+", with a progress dialog (Fanout, Autoroute, Optimize), routing in a separate process, and "fallback to the battle-tested Specctra DSN/SES pipeline" [P]. In v2.4.1, "the Specctra DSN/SES path is still the recommended production route".
- **Scores** ([scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)):
  - `V2_CONTINUOUS` = max(0, 1000 − W1·o1 − W2·o2 − W_C·N_viol/D − W_D·ΣL_um/(U·D)). The open fraction is split at F = 0.5, W1 ≈ 333.3, W2 ≈ 666.7, D = max(1, pins × signal layers).
  - `V2_LOWER_BOUND` compares length against a Manhattan MST, vias against a per-net minimum, and bends against a minimum. Incomplete nets and DRC hits are vetoes [P].

### Pitfalls documented by the four MCP codebases
| Pitfall | Fix | Source |
|---|---|---|
| PRO: SES `(resolution um 10)` declares a grid, not a multiplier; coordinates came out 10× too small | PRO uses 1 mm = 1000 units, Y negated, no offset. **This conflicts with KiCad's own importer**, which computes nm = value × unit ÷ resolution, i.e. 1 mm = 10,000 units at `(resolution um 10)` ([specctra_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/specctra_import_export/specctra_import.cpp) `scale()`). Use KiCad's rule and test it on a real Freerouting SES | [PRO 565a0203](https://github.com/oaslananka/kicad-mcp-pro/commit/565a02030d68cdb2b0bcddd325f5f5a1014ef66f) [P] |
| Internal Edge.Cuts holes become keepouts cleared at track clearance (0.2 mm), not edge clearance (0.5 mm); `router.copper_to_edge_clearance_um` "does not change this (byte-identical SES)" | Grow circular keepouts by the difference, sized by apothem; test board went from 8 violations to 0 | [KMS da8ff18](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/da8ff187816d5b7adabfe3680c93d125edd0c1fe) [P] |
| Net names lose their leading `/` through SES (#246) | Reconcile on import | [KMS 8c84fe9](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/8c84fe9862c38c9ba24614d8f78606e6d9947a4f) [P] |
| `.kicad_pro` netclasses missing from the DSN (#302) | Export them | [KMS 711b0fe](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/711b0fe31ded406eb72e21654626b8fd6f2c0eeb) [P] |
| The SES `(placement …)` block aborts the import when duplicate `REF**` references were renamed (10.0.0: "Reference '%s' not found."; 10.0.7 skips the unknown reference instead, with only a log warning) | Strip the placement block | [KMS f476a97](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f476a9794daaa323e9020010b5d09376c680bbd4) [P] |
| `False == 0` let failed import or export report success | Check strictly. On 10.0.7 a partial import returns success too, so also verify item counts, connectivity and DRC after import and capture wx log warnings | same [P]; [specctra_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/specctra_import_export/specctra_import.cpp) [P] |
| Wrong Java runtime | Read the required version from the JAR's class-file major version (2.4.x needs Java 25); Docker (`eclipse-temurin:<N>-jre`) or Podman fallback | [KMS 356be10](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/356be10abf0acf209d961ca9505a9fa8c4ebe9c1) [P] |
| Stale SES files | Guard them; stage artifacts in a temp dir | [KMS a7b4901](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/a7b49012d11673785cafa4dba7f03b6dc4618aea) [P] |
| Freerouting prints "Multi-threaded route optimization is broken and it is known to generate clearance violations" on every run | `num_threads = 1`; KMS forces `-mt 1` in best-of-N | [POA pcb.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/mcp_server_kicad/pcb.py) [P] |
| "On dense boards a single Freerouting run routinely leaves 1–7 nets unrouted" | Best-of-N varying `--max-passes`; score = `nets_routed·1000 + segments`, +50,000 if all target nets route. "3 attempts is usually enough for 4-layer designs; 5–8 for stubborn cases" (ported from morningfire-pcb-automation, MIT) | [KMS CHANGELOG](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/CHANGELOG.md) [P] |
| Footprint-level keepouts ignored | Promote them to board level before export (POA) | [POA pcb.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/mcp_server_kicad/pcb.py) [P] |
| Footprint text displaced after import | Fix it after import (POA) | same [P] |
| Board-edge clearance missing in KiCad exports | `--router.copperToEdgeClearanceUm` (v2.3.0 workaround) | [releases](https://github.com/freerouting/freerouting/releases) [P] |

### Seen in our benchmark (KiCad 10.0.7, Freerouting 2.5.0)
Reproduced on corpus boards; `bench/src/kaebench/adapters.py` (`Freerouting`) handles each [P].

| Pitfall | Fix |
|---|---|
| A bare net name with `\|` (e.g. `ADD\|SUB`) passes through DSN and Freerouting, but KiCad's SES import then fails the whole session with no message | Quote every bare `(net …)` name in the SES |
| A `.kicad_pro` netclass without track width, via diameter or drill exports `(width -0.001)` and padstack `Via[0-1]_-0.001:-0.001_um`; 2.5.0 draws zero-width tracks and vias | Raise widths to the board minimum; resize and rename unsized via padstacks (KiCad reads the drill from the name) |
| A board whose copper layers are all KiCad "power" layers exports as `(type power)` only; Freerouting refuses it ("all layers are disabled") and 2.5.0 then hangs instead of exiting | Export those layers as `signal` (KiCad routes tracks on power layers) |

### How the four servers run it
- **Shared core:** all four run `java -jar <jar> -de <dsn> -do <ses> -mp <passes>`.
- **POA:**
  1. Pin Freerouting 2.5.0 by SHA-256.
  2. Promote footprint keepouts to board level.
  3. Export with `pcbnew.ExportSpecctraDSN` in a subprocess.
  4. Route.
  5. Import into a **new** `<stem>_routed.kicad_pcb`.
  6. Fix displaced text.
  7. Run `kicad-cli pcb drc --format json` and report `traces_added`, `vias_added`, `drc_violations` and `drc_unconnected`.
- **Konnect:** `export_specctra_dsn` (revision-bound DSN plus reverse manifest) → `route_specctra_dsn` (drives Freerouting's native headless MCP server as a loopback-only child that is always reaped) → `plan_specctra_ses_import` → `apply_specctra_ses`. The apply keeps locked copper, applies "through KiCad IPC as one undo transaction", verifies by post-commit readback, builds a separate candidate board and reports DRC.
- **PRO:** a headless SES apply through a transactional board writer (`router_core.apply_ses_to_pcb`).
- **KMS:** Java or Docker, best-of-N with `attempts`, `targetNets` and `passSchedule`.

## Recommendations for our system
- **Expose one tool**, `route_with_freerouting(board, nets_subset?, timeout)` [I, from VK]:
  1. Export DSN: SWIG helper on 10.x; `kicad-cli pcb export specctra` or IPC on 11.
  2. Call `POST /v1/autoroute` on a **local** server (auth disabled, `Freerouting-Environment-Host: KiCad/10.0`), or the CLI with `-da`.
  3. Import SES into a candidate board, then check item counts and connectivity (10.0.7 skips unresolved items silently).
  4. Return only `normalized_score`, `optimizer_score`, the unrouted count and the compact DRC summary.
- **Lock before import:** lock every track and via to keep (critical nets, earlier routes) before export. Strip or match the SES placement block. Refill zones afterwards (async on 10.0, so poll), then run `kicad-cli pcb drc` [I].
- **Compare KiCad's DRC JSON with Freerouting's drc.v1** to expose DSN translation losses, such as the edge-clearance gap [I].
- **Bake in every pitfall above:** hash-pinned binary, `-mt 1`, best-of-N, and a post-import DRC delta in the score [I].
- **Licensing:** our code is GPL-3.0-or-later, so Freerouting may be vendored, forked or bridged in-process. Freerouting's GPL-3.0-only terms make the combined distribution GPL-3.0. Its 2014 provenance is unclear by community hearsay; avoid upstreaming Freerouting-derived code into KiCad [I]. See [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md).
- **Pin and benchmark against Freerouting 2.5.0** (the latest release; 2.6.x exists only as RCs), not PCBWorld's 2.1.0 baseline [I]. See [../landscape/measured-tool-comparisons.md](../landscape/measured-tool-comparisons.md).

## Conflicts and open questions
- Freerouting 2.5's KiCad 10 IPC path (which plugin mechanism? DRC fidelity?) has not been independently evaluated.
- How much KiCad DRC fidelity is lost on the DSN round trip is unmeasured.
- Freerouting has announced removing SWIG plugin support in the next release.
- Konnect's round trip is unsupported on boards with 4+ layers.

## Sources
- research notes:
  - [verification_kicad_and_tools.md § 1 (#9–11, #23–26), § 4 Freerouting, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [kicad_mcp_codebases.md § 2F, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [existing_tools_and_apis.md § 1, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [licensing.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: [Freerouting README](https://github.com/freerouting/freerouting), [v2.5.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0), [integrations.md](https://github.com/freerouting/freerouting/blob/master/docs/integrations.md)

See also: [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md), [kipy-and-swig-bindings.md](kipy-and-swig-bindings.md), [../landscape/open-source-routers.md](../landscape/open-source-routers.md)
