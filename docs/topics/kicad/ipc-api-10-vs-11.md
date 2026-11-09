# KiCad IPC API: 10.0.x vs KiCad 11 (master)

Scope: IPC transport, versions and cadence, capability matrix 10.0 / master / kipy, behaviour observed by MCP servers, the 10.x backend recipe. Not here: kipy and SWIG details -> [kipy-and-swig-bindings.md](kipy-and-swig-bindings.md); `RunAction` names -> [built-in-automation-features.md](built-in-automation-features.md#action-names-100-and-master).
Keys: IPC API, protobuf, NNG, api.sock, KICAD_API_SOCKET, KICAD_API_TOKEN, BeginCommit, EndCommit, commit group, RefillZones async, AS_BUSY, AS_TOKEN_MISMATCH, AS_UNIMPLEMENTED, stackup read-only, api-server headless, CustomRule proto, SetNetClasses, RunAction, KiCad 11, release cadence, BoardSession

## Versions and cadence
| Item | Value |
|---|---|
| KiCad 9.0.0 | 2025-02-20 [P] |
| KiCad 10.0.0 | 2026-03-20, 7,609 unique commits [P] ([notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)) |
| 10.0.x | .1 2026-04-15 · .2 05-09 · .3 05-15 · .4 06-21 · .5 07-22 · .6 08-29 · .7 10-07 (tag 10-06) [P] ([blog src](https://gitlab.com/kicad/services/kicad-website/-/tree/master/content/blog/2026)) |
| Release policy | Feature merge window closes **Oct 31**; major "annually by January 31st"; 9 and 10 both shipped late [P] ([policy](https://dev-docs.kicad.org/en/rules-guidelines/release-policy/)) |
| KiCad 11 | Not announced; ~Q1 2027 [I]; plan a migration point. Master changes daily (a custom-rules commit is dated 2026-10-20) |

## Mechanics
- **Transport:** protobuf over NNG on UNIX sockets (named pipes on Windows), handled on KiCad's single UI thread: clients "need to anticipate that API messages may sometimes timeout or fail because KiCad is busy" and "should not open multiple connections" [P] ([dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)).
- **Stability:** messages and fields may be added; meanings never change; deprecated items supported ≥1 major version [P].
- **KiCad 9/10 limits:** GUI-attached only; no plotting or export; IPC plugins only in the PCB editor; "No plans to support a standalone library for loading and manipulating KiCad files separate from the client-server (IPC) model" [P] ([for-addon-developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)).
- **Plugins:** `${KICAD_DOCUMENTS_HOME}/<version>/plugins`, each with `plugin.json`; Python plugins get an auto-created venv; "executable" plugins may be any binary; env `KICAD_API_SOCKET`, `KICAD_API_TOKEN`; default socket `api.sock` in temp, PID appended when several instances run; `EnableAPILogging=1` logs every request; enable the server under Preferences > Plugins [P].
- **Socket ownership:** one socket, owned by the instance that bound it; board commands reportedly failed while the project manager held it [S] ([glama](https://glama.ai/mcp/servers/lmaag182/kicad_mcp_server_ipc)).
- **PCM:** 18 plugins use the IPC runtime, 0 AI plugins → [../landscape/kicad-ai-tools-and-mcp-servers.md](../landscape/kicad-ai-tools-and-mcp-servers.md#scale).

## Coverage matrix
Sources: [proto @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/api/proto), [api_handler_pcb.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp), [proto @master](https://gitlab.com/kicad/code/kicad/-/tree/master/api/proto), [kipy board.py @0.8.0](https://gitlab.com/kicad/code/kicad-python/-/blob/0.8.0/kipy/board.py). All [P].

| Capability | 10.0.x | master (11-dev) | kipy 0.8.0 | kipy main |
|---|---|---|---|---|
| Headless server | ❌ | ✅ `kicad-cli api-server [--socket] [file]` (first commit 2026-03-21) | ❌ | ✅ auto-launch |
| Open/create/close docs | ❌ (`GetOpenDocuments` only) | ✅ | ❌ | ✅ |
| Commit/undo (`BeginCommit`/`EndCommit`, COMMIT/DROP) | ✅ | ✅ | ✅ | ✅ |
| Item CRUD | ✅ (`GetItems`: tracks, arcs, vias, pads, footprints, shapes, tables, text, barcodes, ref images, dimensions, zones incl. rule areas, groups, ref points; **no generators or tuning patterns, no DRC markers**) | ✅ | ✅ | ✅ |
| Footprint creation | ✅ fully specified `FootprintInstance` or `ParseAndCreateItemsFromString` | ✅ + `PlaceFootprintFromLibrary` | via items/string | ✅ |
| Selection, `HitTest`, `GetBoundingBox` | ✅ | ✅ + `SyncSelection`, `HighlightNets`, `FocusOnItem`, `GetBoardBoundingBox` | ✅ | ✅ |
| `GetNets`, `GetItemsByNet`, `GetItemsByNetClass`, `GetConnectedItems`, `GetNetClassForNets` | ✅ (by-net, by-netclass, connected need **≥10.0.1**) | ✅ | ✅ | ✅ |
| Net-class definitions (incl. `tuning_profile` since 10.0.0; a name only, no call creates profiles) | ✅ `Get/SetNetClasses` | ✅ | get only | ✅ |
| Net-class assignments (patterns) | ❌ | ✅ | ❌ | ✅ (2026-09-23) |
| Text variables; variants (8 commands) | ✅ | ✅ | vars only | – |
| Board stackup | **read-only** (`UpdateBoardStackup` unhandled; corrected, VK) | **read-only** | get | get |
| Layers (`GetBoardLayerByName` since 10.0.6), origin, title block, appearance, embedded files | ✅ | ✅ (+ page settings) | ✅ | ✅ |
| Board design rules | ❌ | ✅ `Get/SetBoardDesignRules` | ❌ | ✅ |
| Custom DRC rules | ❌ (write `.kicad_dru`) | ✅ structured `CustomRule` (condition string, constraint enum, MinOptMax in nm/**attoseconds**, layer, severity, name; options `SKEW_WITHIN_DIFF_PAIRS`/`TIME_DOMAIN`/`SPACE_DOMAIN`); Get/Set round-trip fix 2026-10-20 | ❌ | ✅ |
| Run DRC / read results | ❌ (only `InjectDrcError`) | ❌ | ❌ | ❌ |
| `RefillZones` | whole board only (zone list → `AS_UNIMPLEMENTED`), **async** via `CallAfter` | per zone; rejects rule areas; synchronous when headless | ✅ | ✅ |
| `GetPadShapeAsPolygon`, `CheckPadstackPresenceOnLayers` | ✅ | ✅ | ✅ | ✅ |
| `FlipItems` | ✅ | ✅ | ✅ | ✅ |
| `InteractiveMoveItems` | ✅ hands control to the user, returns immediately, editor busy until done | ✅ | ✅ | ✅ |
| `RunAction(name)` | ✅ `RAS_OK`/`RAS_INVALID` immediately; "specifically *not* an API"; names "may change… disappear" | ✅ | ✅ (fixed 0.7.1) | ✅ |
| Netlist import | ❌ | ✅ `ImportNetlist` | ❌ | ✅ |
| Specctra DSN export / SES import | ❌ | ✅ `RunBoardJobExportSpecctraDsn` / `ImportSpecctraSession` ("Since 11.0") | ❌ | not checked |
| Export/plot jobs | ❌ | ✅ 20 board jobs: 3D, render, SVG, DXF, PDF, PS, PNG, Gerbers, drill, pos, GenCAD, DSN, IPC-2581, IPC-D-356, ODB++, stats, IDF; plot settings | ❌ | ✅ |
| Library tables; schematic (hierarchy, netlist, place symbol, sch jobs) | ❌ (schematic proto exists, empty) | ✅ | ❌ | partial |
| Route / autoroute / autoplace | ❌ (only via `RunAction("pcbnew.InteractiveRouter.Autoroute")` / `"pcbnew.Autoplacer.autoplaceSelected"`) | ❌ | ❌ | ❌ |
| Change notifications | ❌ | ❌ | ❌ | ❌ |

## Behaviour observed by MCP servers (KiCad 10.0.5)
| Behaviour | Detail |
|---|---|
| Commit visibility | "staged creates are not visible through `get_tracks`, generic `get_items` … until the commit is pushed". One real Ctrl+Z reverted a committed track+via group to the exact pre-operation digest; a 20-iteration stage-and-drop soak had zero failures [P] ([PRO cc91138e](https://github.com/oaslananka/kicad-mcp-pro/commit/cc91138e2834204d5eb0e9c285cf4ab07cd209ae)) |
| Chunking | schematic-to-board creates chunked into groups of ≤32 inside one commit; one Undo restored 70 footprints [P] ([Konnect bb45526](https://github.com/mixelpixx/Konnect/commit/bb455261259333a79168a21ad6b74898215e6ca1)) |
| Refill | `RefillZones` answers immediately, then `AS_BUSY` while filling; Konnect retries only that status, 60 s budget, 50 ms polls [P] ([DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md)) |
| Frames | footprint children serialized in **absolute** coordinates despite the proto comment → [transform-math-pitfalls.md](transform-math-pitfalls.md#anchor-only-moves-over-ipc) |
| Socket probe, unknown layers | raw-connect probe wedges NNG until pcbnew restarts (#498); unknown layer names crash 10.0.5 → [file-format-and-version-hazards.md](file-format-and-version-hazards.md#format-eras-and-dialects) |
| Token loss | treat `AS_TOKEN_MISMATCH` as a session break → [kipy-and-swig-bindings.md](kipy-and-swig-bindings.md#kipy-traps-found-by-mcp-servers) |

## 10.x backend recipe
[I, from VK]
1. IPC commit groups for item CRUD. Net classes (project commands) and variants (variant commands) are not board-item edits, so commit groups do not cover them; kipy 0.8.x lacks `set_net_classes` and variant wrappers → send `SetNetClasses` and variant commands as raw protobuf (vendored `.proto`). Tuning profiles: write in `.kicad_pro` [P].
2. Library footprints via `ParseAndCreateItemsFromString` from `.kicad_mod` text, then an `UpdateItems` pass for pad nets: undoable placement a full version before `PlaceFootprintFromLibrary`.
3. `.kicad_dru` written directly.
4. Referee: [kicad-cli.md](kicad-cli.md#referee-command) on a saved copy.
5. SWIG `ExportSpecctraDSN`/`ImportSpecctraSES` for routing round trips ([specctra-freerouting-integration.md](specctra-freerouting-integration.md)).

- **Avoid:** stackup writes, unpolled refills, `RunAction` wherever an alternative exists.
- **`BoardSession` abstraction** with three backends: live IPC, KiCad 11 headless `api-server`, file-level byte-preserving splice. Target 10.0.x, pin kipy 0.8.x [I].
- Verify only after the push; poll refills until not busy; correlate requests by ID; never retry an uncertain write ([mcp-server-lessons.md](mcp-server-lessons.md)).
- KiCad 11: emit `CustomRule` from the same IR as `.kicad_dru`; validate by Get/Set round trip ([drc-rule-language-reference.md](drc-rule-language-reference.md#compiler-rules)).
- Spike early on 10.0.7: does `ParseAndCreateItemsFromString` keep nets? How long do async refills take? When does the GUI reload `.kicad_dru`?

## Open questions
- Can `UpdateItems` modify every field of every item type (padstacks, zone fill settings)? Not tested.
- KiCad 11 date and final IPC surface not announced.
- Socket ownership by project manager vs pcbnew is secondhand [S].

## Sources
- [verification_kicad_and_tools.md § 1 (corrections #2–8, #12–13), § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [existing_tools_and_apis.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md); [kicad_mcp_codebases.md § 1, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
- [IPC dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/), [board_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto), [board_jobs.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto), [board_rules.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_rules.proto), [editor_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto)
