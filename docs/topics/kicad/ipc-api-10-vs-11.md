# KiCad IPC API: 10.0.x today vs KiCad 11 (master)

**TL;DR**
- On **10.0.x**, the IPC API attaches to a running GUI and offers item CRUD with undoable commits. It has no DRC run, no design-rule access, no export, no headless mode, no Specctra and no route or place commands. Corrected by VK: the stackup is **read-only** [P].
- **KiCad 11 (master)** adds a headless `kicad-cli api-server`, design rules and structured custom rules, netlist import, DSN export and SES import, 20 board export jobs, and library and schematic commands. It still has **no "run DRC", no routing or placement, and no change notifications** [P].
- Agent-loop traps:
  - `RefillZones` is whole-board and **asynchronous** on 10.0.
  - Staged commit items are **invisible until pushed**.
  - Several calls need point releases (≥10.0.1, 10.0.6, 10.0.7).
  - KiCad answers on one UI thread, so expect busy and timeout errors and use a single connection [P].
- On 10.x the backend needs four channels: IPC CRUD in commits, direct `.kicad_dru` writes, `kicad-cli pcb drc` as referee, and SWIG DSN/SES (see [specctra-freerouting-integration.md](specctra-freerouting-integration.md)) [I].
- Plan a migration point for KiCad 11, likely around Q1 2027 [I].

## Key facts

### Versions and cadence
| Item | Value |
|---|---|
| KiCad 10.0.0 | 2026-03-20, 7,609 unique commits [P] ([notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)) |
| 10.0.x point releases | .1 2026-04-15 · .2 05-09 · .3 05-15 · .4 06-21 · .5 07-22 · .6 08-29 · .7 10-07 (tag 10-06) [P] ([blog src](https://gitlab.com/kicad/services/kicad-website/-/tree/master/content/blog/2026)) |
| KiCad 9.0.0 | 2025-02-20 [P] |
| Release policy | Feature merge window closes **Oct 31**; major release "annually by January 31st"; 9 and 10 both shipped late [P] ([policy](https://dev-docs.kicad.org/en/rules-guidelines/release-policy/)) |
| KiCad 11 | Not announced; ~Q1 2027 [I]. Master changes daily (a custom-rules commit is dated 2026-10-20). |

### Mechanics
- **Transport:** protobuf over NNG on UNIX sockets (named pipes on Windows). Requests are handled on KiCad's single UI thread, so clients "need to anticipate that API messages may sometimes timeout or fail because KiCad is busy" and "should not open multiple connections" [P] ([dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)).
- **Stability:** new messages and fields may be added, but existing meanings never change. Deprecated items stay supported for at least one major version [P].
- **KiCad 9/10 limits:**
  - GUI-attached only.
  - No plotting or export.
  - IPC plugins only in the PCB editor.
  - "No plans to support a standalone library for loading and manipulating KiCad files separate from the client-server (IPC) model" [P] ([for-addon-developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)).
- **Plugins:**
  - Live in `${KICAD_DOCUMENTS_HOME}/<version>/plugins`, each with a `plugin.json`.
  - Python plugins get an auto-created venv; "executable" plugins can be any binary.
  - Environment: `KICAD_API_SOCKET` and `KICAD_API_TOKEN`; default socket `api.sock` in temp, with the PID appended when several instances run.
  - `EnableAPILogging=1` logs every request.
  - The server must be enabled under Preferences > Plugins [P].
- **Socket ownership:** only one socket exists, owned by the instance that bound it. Board commands reportedly failed while the project manager held it [S] ([glama](https://glama.ai/mcp/servers/lmaag182/kicad_mcp_server_ipc)).
- **PCM:** 18 PCM plugins already use the IPC runtime, and no AI plugin exists (index 2026-10-19) [P]. See [../landscape/kicad-ai-tools-and-mcp-servers.md](../landscape/kicad-ai-tools-and-mcp-servers.md).

### Coverage matrix
Sources: [proto @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/api/proto), [api_handler_pcb.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp), [proto @master](https://gitlab.com/kicad/code/kicad/-/tree/master/api/proto), [kipy board.py @0.8.0](https://gitlab.com/kicad/code/kicad-python/-/blob/0.8.0/kipy/board.py). All [P].

| Capability | 10.0.x | master (11-dev) | kipy 0.8.0 | kipy main |
|---|---|---|---|---|
| Headless server | ❌ | ✅ `kicad-cli api-server [--socket] [file]` (first commit 2026-03-21) | ❌ | ✅ auto-launch |
| Open/create/close docs | ❌ (`GetOpenDocuments` only) | ✅ | ❌ | ✅ |
| Commit/undo (`BeginCommit`/`EndCommit`, COMMIT/DROP) | ✅ | ✅ | ✅ | ✅ |
| Item CRUD | ✅ (`GetItems`: tracks, arcs, vias, pads, footprints, shapes, tables, text, barcodes, ref images, dimensions, zones incl. rule areas, groups, ref points; **no generators or tuning patterns, no DRC markers**) | ✅ | ✅ | ✅ |
| Footprint creation | ✅ fully specified `FootprintInstance` or `ParseAndCreateItemsFromString` | ✅ + `PlaceFootprintFromLibrary` | via items/string | ✅ |
| Selection, `HitTest`, `GetBoundingBox` | ✅ | ✅ + `SyncSelection`, `HighlightNets`, `FocusOnItem`, `GetBoardBoundingBox` | ✅ | ✅ |
| `GetNets`, `GetItemsByNet`, `GetItemsByNetClass`, `GetConnectedItems`, `GetNetClassForNets` | ✅ (by-net, by-netclass and connected need **≥10.0.1**) | ✅ | ✅ | ✅ |
| Net-class definitions (incl. `tuning_profile`, since 10.0.0) | ✅ `Get/SetNetClasses` | ✅ | get only | ✅ |
| Net-class assignments (patterns) | ❌ | ✅ | ❌ | ✅ (2026-09-23) |
| Text variables; variants (8 commands) | ✅ | ✅ | vars only | – |
| Board stackup | **read-only** (`UpdateBoardStackup` unhandled; corrected, VK) | **read-only** | get | get |
| Layers (`GetBoardLayerByName` since 10.0.6), origin, title block, appearance, embedded files | ✅ | ✅ (+ page settings) | ✅ | ✅ |
| Board design rules | ❌ | ✅ `Get/SetBoardDesignRules` | ❌ | ✅ |
| Custom DRC rules | ❌ (write `.kicad_dru`) | ✅ structured `CustomRule` (condition string, constraint enum, MinOptMax in nm/**attoseconds**, layer, severity, name; options `SKEW_WITHIN_DIFF_PAIRS`/`TIME_DOMAIN`/`SPACE_DOMAIN`); Get/Set round-trip fix 2026-10-20 | ❌ | ✅ |
| Run DRC / read results | ❌ (only `InjectDrcError`) | ❌ | ❌ | ❌ |
| `RefillZones` | whole board only (a zone list returns `AS_UNIMPLEMENTED`), **async** via `CallAfter` | per zone; rejects rule areas; synchronous when headless | ✅ | ✅ |
| `GetPadShapeAsPolygon`, `CheckPadstackPresenceOnLayers` | ✅ | ✅ | ✅ | ✅ |
| `FlipItems` | ✅ | ✅ | ✅ | ✅ |
| `InteractiveMoveItems` | ✅ hands control to the user, returns immediately, editor busy until done | ✅ | ✅ | ✅ |
| `RunAction(name)` | ✅ returns `RAS_OK`/`RAS_INVALID` immediately; "specifically *not* an API"; names "may change… disappear" | ✅ | ✅ (fixed 0.7.1) | ✅ |
| Netlist import | ❌ | ✅ `ImportNetlist` | ❌ | ✅ |
| Specctra DSN export / SES import | ❌ | ✅ `RunBoardJobExportSpecctraDsn` / `ImportSpecctraSession` ("Since 11.0") | ❌ | not checked |
| Export/plot jobs | ❌ | ✅ 3D, render, SVG, DXF, PDF, PS, PNG, Gerbers, drill, pos, GenCAD, DSN, IPC-2581, IPC-D-356, ODB++, stats, IDF; plot settings | ❌ | ✅ |
| Library tables; schematic (hierarchy, netlist, place symbol, sch jobs) | ❌ (schematic proto exists but is empty) | ✅ | ❌ | partial |
| Route / autoroute / autoplace | ❌ | ❌ | ❌ | ❌ |
| Change notifications | ❌ | ❌ | ❌ | ❌ |

- **Built-in routing and placement** are reachable only through `RunAction("pcbnew.InteractiveRouter.Autoroute")` or `"pcbnew.Autoplacer.autoplaceSelected"`. See [built-in-automation-features.md](built-in-automation-features.md).

### Behaviour observed by MCP servers (KiCad 10.0.5)
- **Commit visibility:** "staged creates are not visible through `get_tracks`, generic `get_items` … until the commit is pushed". One real Ctrl+Z reverted a committed track and via group to the exact pre-operation digest. A 20-iteration stage-and-drop soak had zero failures [P] ([PRO evidence](https://github.com/oaslananka/kicad-mcp-pro/commit/cc91138e2834204d5eb0e9c285cf4ab07cd209ae)).
- **Chunking:** schematic-to-board creates are chunked into groups of ≤32 inside one commit, and one Undo restored 70 footprints [P] ([Konnect bb45526](https://github.com/mixelpixx/Konnect/commit/bb455261259333a79168a21ad6b74898215e6ca1)).
- **Refill:** `RefillZones` answers immediately, then returns `AS_BUSY` while filling. Konnect retries only that status, with a 60 s budget and 50 ms polls [P] ([DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md)).
- **Coordinate frames:** IPC serializes footprint children in **absolute** coordinates, despite the proto comment. See [transform-math-pitfalls.md](transform-math-pitfalls.md).
- **Socket probing:** a raw-connect probe of the socket wedges NNG until pcbnew restarts (#498). Unknown layer names crash 10.0.5. See [file-format-and-version-hazards.md](file-format-and-version-hazards.md).
- **Token loss:** a TTL bug discarded the kipy client and its token, so a transaction "could … silently reconnect to a newly started KiCad process". Treat `AS_TOKEN_MISMATCH` as a session break [P].

## Recommendations for our system
- **10.x backend** [I, from VK]:
  1. IPC inside commit groups for CRUD, net classes and variants.
  2. Library footprints via `ParseAndCreateItemsFromString` from `.kicad_mod` text, then an `UpdateItems` pass for pad nets. This gives undoable placement a full version before `PlaceFootprintFromLibrary`.
  3. `.kicad_dru` written directly.
  4. `kicad-cli pcb drc --format json --refill-zones` on a saved copy as the referee.
  5. SWIG `ExportSpecctraDSN`/`ImportSpecctraSES` for routing round trips.
- **Avoid:** stackup writes, unpolled refills, and `RunAction` wherever an alternative exists.
- **Put a `BoardSession` abstraction in front** with three backends: live IPC, KiCad 11 headless `api-server`, and a file-level byte-preserving splice. Target 10.0.x and pin kipy 0.8.x [I].
- **Verify only after the push.** Poll refills until not busy. Correlate requests by ID. Never retry an uncertain write. See [mcp-server-lessons.md](mcp-server-lessons.md).
- **For KiCad 11,** emit the structured `CustomRule` proto from the same IR as `.kicad_dru` and validate it by Get/Set round trip. See [drc-rule-language-reference.md](drc-rule-language-reference.md).
- **Spike early on 10.0.7:**
  - Does `ParseAndCreateItemsFromString` keep nets?
  - How long do async refills take?
  - When does the GUI reload `.kicad_dru`?

## Conflicts and open questions
- Can `UpdateItems` modify every field of every item type, e.g. padstacks and zone fill settings? Not tested.
- The KiCad 11 date and final IPC surface are not announced.
- Socket ownership by project manager vs pcbnew is a secondhand claim [S].

## Sources
- research notes:
  - [verification_kicad_and_tools.md § 1 (corrections #2–8, #12–13), § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [existing_tools_and_apis.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [kicad_mcp_codebases.md § 1, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
- primary: [IPC dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/), [board_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto), [board_jobs.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto), [board_rules.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_rules.proto), [editor_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto)

See also: [kipy-and-swig-bindings.md](kipy-and-swig-bindings.md), [kicad-cli.md](kicad-cli.md), [built-in-automation-features.md](built-in-automation-features.md), [mcp-tool-surface-spec.md](mcp-tool-surface-spec.md)
