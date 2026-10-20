# Lessons from the four leading KiCad MCP server codebases

> **Method.** Each repo was cloned read-only with `--depth 1` on 2026-10-20, then deepened with `git fetch --depth=1000`. Three histories are complete back to the first commit. kicad-mcp-pro is still shallow, with its oldest fetched commit dated 2026-06-14. The table below gives the HEAD each permalink is pinned to.
>
> | Repo | HEAD SHA | HEAD date | Commits mined |
> |---|---|---|---|
> | mixelpixx/KiCAD-MCP-Server ("KMS") | `cbb59a6203997f5e916be7e0480d63fe5519134a` | 2026-10-01 | 924 (full history from 2025-10-25) |
> | mixelpixx/Konnect | `9488e5f09717cb508cb25779dc16586d1f06f758` | 2026-10-05 | 1,168 (full history from 2026-07-05) |
> | oaslananka/kicad-mcp-pro ("PRO") | `44617f39108c822ab2a02fc557bcffa802e66fea` | 2026-10-20 | 1,130 (shallow, from 2026-06-14) |
> | ProductOfAmerica/mcp-server-kicad ("POA") | `f5f82e02ffe17bbcba806fec35f3302ee332fefc` | 2026-10-20 | 880 (full history from 2026-03-09) |
>
> - **Sources.** Everything comes from the repos' own docs, source, changelogs and commit messages. GitHub issue pages were not read: they and the API return 403. Issue numbers below are quoted from commit messages and docs.
> - **Commit counts.** All counts are keyword matches on non-merge commit subjects that contain "fix", with ci/chore/docs/deps commits excluded. They are approximate. The regexes are in the table note in §2.
> - **Overlap with earlier notes.** These notes add source-level detail to `field_reports_and_ux.md` §1C and to `existing_tools_and_apis.md` §2, which relied on search snippets. Items already there are only referenced, not restated, unless the source changes or corrects them.

## 1. Tool surface: what each server exposes, how fine-grained, through which KiCad interface, with what state model, and how board state is shown to the LLM

### Takeaway
- **Size and interfaces.** The four servers expose 109 to 387 tools. All of them wrap the same four channels: KiCad's IPC API (kipy or a custom NNG client), SWIG `pcbnew`, `kicad-cli`, and direct S-expression editing.
- **Granularity.** Almost every write tool is raw-coordinate CRUD: place, move or rotate at (x, y, θ), a trace segment between two XY points, a via at an XY point. Higher-level operations are few. They include an L-bend pad-to-pad route, a decoupling-cap row, a force-directed suggester, and a Freerouting round trip.
- **Where the projects differ.** The mature projects do not compete on coverage. They compete on:
  - **Source honesty:** stating whether an answer came from the live board or the saved file.
  - **Mutation discipline:** dry-run plans tied to a revision, native commit groups that make one undo step, and refusals that leave the file intact.
  - **Tool-surface gating:** profiles or toolsets that cut the catalogue from about 57k tokens to about 2k.

### Cited findings

**KiCAD-MCP-Server (MIT, TypeScript + Python, v2.8.2)**
- **Size.** 244 tools are registered. 184 are indexed for keyword discovery in 17 categories, and 60 are not indexed; a test freezes the unindexed count so it can only shrink. There is no permission tier: "Every tool listed here is registered … There is no router that hides tools." — [TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md)
- **Per-file counts** — [TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md)
  - Core: project 12, board 19, component 28, routing 17, DRC 7, export 27.
  - Schematic: schematic 46, batch 9, hierarchy 5, layout 5, validation 2.
  - Libraries: footprint libraries 7, symbol libraries 9, footprint creator 7, symbol creator 8.
  - Parts data: datasheet 2, JLCPCB 5, parts registry 3, Digi-Key 3.
  - Other: Freerouting 4, Eagle import 1, PCB import 1, UI 3, discovery 3, GUI driver 11.
- **Granularity, raw primitives** — [TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md)
  - `place_component` (position, rotation), `move_component`, `rotate_component` (absolute angle).
  - `route_trace` ("between XY points (single layer)"), `route_arc_trace`, `add_via`.
- **Granularity, mid-level operations** — [TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md)
  - `batch_move_components` is "transactional": if any reference is invalid, nothing changes.
  - `route_pad_to_pad` adds a via automatically.
  - `route_differential_pair`, `copy_routing_pattern`, `add_gnd_stitching_vias`.
- **Inspection tools** — [TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md)
  - `get_component_geometry` returns separate bounding boxes for body, pads, courtyard, keepout, fab, silk and text.
  - `get_ratsnest` estimates airwires and their lengths.
  - `check_placement_clearance` classifies conflicts as body, courtyard, keepout, silk/text or pad conflicts.
  - Also `get_net_pads`, `check_courtyard_overlaps`, `suggest_placement` and `hierarchical_place`.
- **Architecture.** A TypeScript MCP server talks MCP over stdio and spawns a Python subprocess. The subprocess receives JSON commands and calls `pcbnew` SWIG or the IPC API. — [ARCHITECTURE.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/ARCHITECTURE.md)
- **SWIG versus IPC.** SWIG has no undo and needs a manual reload; IPC has transactions. About 22 commands have IPC handlers; `delete_trace` still falls back to SWIG. `place_component` is hybrid: SWIG loads the library footprint and IPC places it. — [IPC_BACKEND_STATUS.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/IPC_BACKEND_STATUS.md)
- **Session pinning (#223).** `open_project` pins the session to IPC only when the live GUI provably has the same `.kicad_pcb` open; otherwise it pins to SWIG. A SWIG-pinned session never upgrades silently: the GUI's in-memory board would be stale, and saving through IPC would clobber the MCP's edits — "the exact lost-edits bug in #223". — [IPC_BACKEND_STATUS.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/IPC_BACKEND_STATUS.md)
- **State tools.** `is_dirty`, `discard_or_reload`, `reload_board`, `snapshot_project` (renders a PDF checkpoint) and `get_backend_state`. Every response is tagged with `_backend: "ipc"|"swig"` and `_realtime`. — [TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md); [VISUAL_FEEDBACK.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/VISUAL_FEEDBACK.md)
- **IPC commits.** The IPC backend wraps single edits in `begin_commit`/`push_commit`, e.g. "Moved component {reference}". — [ipc_backend.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/kicad_api/ipc_backend.py)
- **Board images.** `get_board_2d_view` renders PNG, JPG or SVG through `kicad-cli`, default 1600×1200, returned inline as base64 or as a file path. — [board/view.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/board/view.py)
- **GUI driver.** 11 tools. `kicad_run_drc` opens the DRC dialog, clicks "Run DRC" and scrapes the violations grid. There is also a Linux AT-SPI backend. — [TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md)
- **Known issues** — [KNOWN_ISSUES.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/KNOWN_ISSUES.md)
  - "Calling `ZONE_FILLER` via SWIG causes segfault."
  - pcbnew writes a possibly stale project model over `.kicad_pro` on every `SaveBoard`. The `preserve_project_settings()` guard restores `net_settings` after each save.

**Konnect (AGPL-3.0, Rust, KiCad 10)**
- **Size and discovery.** 21 toolsets hold 228 tools, plus 7 always-visible meta-tools (235 in total). Only a "starter kit" (`project`, `config`) is preloaded, "so baseline `tools/list` costs ~2K tokens instead of ~23K". The model loads more with `list_toolboxes` → `load_toolset(name)`. Every call is logged (a ring buffer of 100, plus `logs/calls.jsonl`) and is readable through `get_recent_calls` and `server_stats`. — [tool-directory.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/tool-directory.md)
- **The KMS README undercounts Konnect.** It says Konnect has "171 tools"; Konnect's generated directory says 228 + 7 (above). — [KMS README](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/README.md)
- **Dynamic toolsets broke over stdio.** The `tools/list_changed` notification reached HTTP/SSE clients only. In Claude Code, "172 of 185 tools … were unreachable" after `load_toolset` until the fix. — [commit dca61c0](https://github.com/mixelpixx/Konnect/commit/dca61c07be5498f0bd82b258e028908403eacf55)
- **Channels.** Schematics: direct `.kicad_sch` S-expression edits with atomic writes. PCB: the KiCad 10 IPC API (NNG + protobuf, "real-time and undo-aware"). Specctra: "Revision-bound Rust DSN export, local Freerouting MCP routing, and strict one-transaction SES import". Exports and checks: `kicad-cli`. — [README](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/README.md)
- **Three board-write gates** — [KICAD_INTEGRATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/KICAD_INTEGRATION.md)
  - `ensure_board_is_active`: a request naming one board cannot change another open board.
  - `attempt_ipc_write`: file fallback happens only when IPC is unreachable. A response from KiCad, including a rejection, "fails closed".
  - `refuse_if_board_open_in_kicad`: protects file-only tools "from edits KiCad would discard on its next save".
- **Plan → apply.** `update_pcb_from_schematic` and `update_footprints_from_library` default to dry run. Apply needs the exact `expected_plan_revision` the dry run returned. "A successful apply is one KiCad undo entry." — [kicad-pcb SKILL.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect/assets/skills/kicad-pcb/SKILL.md)
- **Notable PCB tools** — [tool-directory.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/tool-directory.md)
  - `set_component_placements`: XY and absolute rotation for many footprints "atomically, using one live KiCAD update and one undo step".
  - `flip_component`: uses KiCad 10.0.6's native `FlipItems` IPC command.
  - `get_component_pads`: live board-space pad positions with nets. A present but unreadable net reports null.
  - `check_clearance`: explicit anchor and courtyard modes.
  - `get_board_2d_view`: a `kicad-cli` 3D render seen from the top, returned as base64 PNG, with no layer selection.
  - `set_active_layer`: returns `unsupported_capability`, because IPC has no such mutation.
- **Reliability contract.**
  - Outcome classes: Complete, Partial, Refused/failed before mutation, Uncertain after possible mutation, Check unavailable.
  - "Echoing the request is not evidence that the operation applied it."
  - "Required unavailable evidence makes a design verdict incomplete."
  - Source: [RELIABILITY_CONTRACT.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/RELIABILITY_CONTRACT.md)
- **DRC synchronization.** `sync_live_board` runs: exact target → save → native-snapshot comparison → CLI DRC → check that the saved source did not change.
  - KiCad answers `RefillZones` immediately, then returns `AS_BUSY` while filling. Only that status is retried, with a 60 s readiness budget and 50 ms polling.
  - A failed save gives `mutation_outcome_uncertain`, and DRC stops.
  - Source: [DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md)

**kicad-mcp-pro (MIT, Python/FastMCP, v4.3.0)**
- **Size and annotations.** "Total public tools: 387". Every tool is annotated Read-Only, Destructive, Open-World, Idempotent, Headless and Requires-KiCad-Running, and lists the profiles it belongs to. — [tools-reference.generated.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/tools-reference.generated.md)
- **Profiles.** The `default` profile is 24 read-only review tools. `build` (write mode) and `release` (manufacturing mode) have 24 tools each; `expert` and `full` expose everything.
  - The build allowlist covers only commit control and deletes (`pcb_begin_commit`, `pcb_delete_items`, `pcb_push_commit`, `pcb_drop_commit`, `pcb_revert`). It has no move or route tools, so layout needs `pcb_layout` or `expert`.
  - Sources: [README](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/README.md); [router.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/tools/router.py)
- **Measured catalogue cost.** The expert profile is 387 tools, 227,578 characters, about 56,895 tokens. The default profile is 24 tools, 9,345 characters, about 2,337 tokens: 95.9% smaller. — [progressive-disclosure-profile-snapshot.json](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/evidence/progressive-disclosure-profile-snapshot.json)
- **Adapter rules.**
  - Exactly three channels: `kicad-cli`, IPC/kipy and S-expression files. All KiCad fragility sits behind one adapter seam. Four operating modes (readonly, write, manufacturing, experimental) sit on top of profiles. — [ARCHITECTURE.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/ARCHITECTURE.md)
  - "There is no SWIG fallback", enforced by `scripts/check_no_pcbnew.py`.
  - KiCad 11 headless IPC (`kicad-cli api-server`) is used only when headless mode is explicitly asserted.
  - "A hidden or opportunistic fallback is unsafe … An IPC mutation must not silently become an unguarded text rewrite."
  - Source: [ADR-0007](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/adr/0007-kicad-adapter-selection-and-swig-retirement.md)
- **Native-live transaction evidence (KiCad 10.0.5)** — [native-live transaction evidence](https://github.com/oaslananka/kicad-mcp-pro/commit/cc91138e2834204d5eb0e9c285cf4ab07cd209ae)
  - Tools: `pcb_begin_commit`, `pcb_push_commit`, `pcb_drop_commit`, `pcb_revert`, `pcb_get_live_edit_state`.
  - "staged creates are not visible through `get_tracks`, generic `get_items` … until the commit is pushed", so postconditions are checked after the push.
  - One real Ctrl+Z reverted a committed track + via group to the exact pre-operation digest.
  - A 20-iteration stage-and-drop soak had zero failures.
  - A TTL expiry bug discarded the authenticated kipy client, and with it KiCad's per-instance token, so "the old transaction could then silently reconnect to a newly started KiCad process and stage a mutation there". The fix treats `AS_TOKEN_MISMATCH` as a break in session continuity.
- **Output bounds.** Defaults are `max_items_per_response` 200 and `max_text_response_chars` 50,000. — [config.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/config.py)
- **Board-state presentation.**
  - `pcb_get_board_as_string` returns live or file-backed S-expression text, truncated at that limit. — [session_inspection.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/pcb/session_inspection.py)
  - Images go back as MCP `ImageContent`. — [mcp_media.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/mcp_media.py)
- **Focused DRC slices and gates.**
  - DRC slices: `get_courtyard_violations`, `get_unconnected_nets`, `get_silk_to_pad_violations`.
  - Gates: `pcb_placement_quality_gate` (overlap-free and inside the frame), `pcb_transfer_quality_gate` (pad nets transferred) and `project_full_validation_loop` (bounded fix-and-rerun).
  - Source: [tools-reference.generated.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/tools-reference.generated.md)

**mcp-server-kicad (GPL-3.0-or-later since 2026-10-14, Python, v0.21.1, maintenance mode)**
- **Size and layout.** 109 tools across five servers: schematic 42, pcb 34, project 24, symbol 5, footprint 4. They run as one unified server or split.
  - PCB reads: `list_pcb_footprints`, `list_pcb_traces`, `list_pcb_nets`, `list_pcb_zones`, `list_pcb_layers`, `list_pcb_graphic_items`; `get_board_info`, `get_footprint_pads`, `get_footprint_bounds`.
  - PCB writes: `place_footprint`, `move_footprint`, `remove_footprint`, `add_trace`, `remove_traces`, `set_trace_width`, `remove_dangling_tracks`, `add_via`, `add_thermal_vias`, `add_copper_zone`, `add_keepout_zone`, `fill_zones`, `set_net_class`, `update_pcb_from_schematic`.
  - Checks: `run_drc`, `check_placement`, `validate_board`, `autoroute_pcb`.
  - Source: [README](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/README.md)
- **Interface.** Every read and write runs on a stdlib-only, byte-preserving S-expression CST.
  - `kicad-cli` handles ERC, DRC, exports and netlists. A `pcbnew` subprocess is used only for `fill_zones` and `autoroute_pcb`.
  - "KiCad itself writes a design file in just two places: the library upgrades, and `autoroute_pcb`'s routed copy, a new board that leaves yours untouched."
  - Sources: [README](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/README.md); [CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md)
- **`check_placement` is only a point test.** It tests the footprint origin against keepouts and the board edge. Its `rotation` parameter was removed because "rotating about the origin cannot move the origin". — [commit 456839d](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/456839d98da94b0d6e6ea2df6509d3c4c2bc0240); [ADR status log](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)
- **Server instructions name the start tools.** They do this because in hosts that defer tool schemas, "'place a 10k resistor' cost three tool_search calls before place_component surfaced". A test checks that every name in the instructions exists in the live registry. — [server.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/mcp_server_kicad/server.py)
- **No direct file access.** The plugin's `hooks.json` blocks Read/Write/Edit on KiCad file extensions at the harness level. — [CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md)

### Inferences
- **Granularity mismatch.** None of the four exposes a placement or routing operation at the level of design intent, such as "place this group respecting these constraints and return a scored candidate", that is also safe to apply. Where one existed (Konnect's planners), it was retired (§3). For an LLM, granularity is therefore stuck at raw (x, y, θ), which is where the field reports find LLMs weakest.
- **Gating has measurable value.** Konnect's ~23k → ~2k tokens and PRO's ~57k → ~2.3k tokens are measured. POA's finding that deferred-schema hosts cost extra search turns shows the opposite failure, where gating hides tools. A small, always-visible core of well-named tools is the stable middle ground.
- **Tools must state their data source.** All three projects with an IPC path (KMS, Konnect, PRO) independently converged on tagging each answer with its source: `_backend`, `source: ipc|saved_file`, `board_source`. Every tool in our layer should do the same.

### Gaps
- No server publishes measured token cost per board-read tool (for example, bytes returned by a 400-footprint `list_footprints`). Only catalogue sizes are measured.
- Issue threads (for example Konnect #595 and #754, KMS #223 and #406) could not be read; their content is known only through commit messages and docs.

## 2. Recurring bugs and fixes from commit history

### Takeaway
- **The same failures recur.** The same six failure classes show up independently in all four codebases, often in the same month:
  1. Transform math: the textbook rotation matrix versus KiCad's Y-down transpose, mirror applied before rotation, moves that shift only the anchor.
  2. Silent data loss on write: 3D models dropped by a kicad-python setter; pcbnew `SaveBoard` dropping shapes and hidden text; KiCad 10 net references silently rebinding.
  3. Saved-file versus live-board divergence.
  4. KiCad 9 to 10 format and API breaks.
  5. "Success" that wasn't.
  6. Gaps in the Freerouting DSN/SES round trip.
- **Most were found the same way.** Most fixes were found only when someone compared against KiCad's own output: drill files, Gerbers, `kicad-cli` netlists, live readback. The projects' own unit tests had not caught them.

### Cited findings

**Approximate counts.** Non-merge fix commits whose subject matches each class, out of all fix commits:

| Bug class (regex keywords) | KMS | Konnect | PRO | POA |
|---|---:|---:|---:|---:|
| rotation/flip/mirror/transpose/rigid body | 19 | 12 | 5 | 12 |
| KiCad 10 compatibility ("kicad 10", "10.0.x") | 13 | 7 | 7 | 3 |
| stale/live/saved/reload/clobber/dirty | 11 | 11 | 3 | 3 |
| net/netclass/net name/net ref | 15 | 14 | 7 | 20 |
| DRC report/parsing | 3 | 8 | 1 | 1 |
| Freerouting/DSN/SES/Specctra | 7 | 6 | 1 | 9 |
| library tables/resolution | 28 | 43 | 6 | 11 |
| zone/pour/refill | 3 | 5 | 0 | 8 |
| IPC transport/socket/endpoint | 15 | 27 | 4 | 0 |
| units/inch/mil/scale | 3 | 1 | 3 | 0 |
| **all fix commits** (of all commits) | 292 (924) | 358 (1,168) | 275 (1,130) | 227 (880) |

- **Source.** Computed from `git log` subjects of the four clones at the HEADs listed at the top; the patterns are in the column headings. Many POA fixes are labelled "test:" or "docs:" with numbered "bug N" tags, so POA is undercounted.

**A. Transform and rotation math (the most consistent cross-repo class)**
- **Konnect: textbook rotation matrix.** `get_component_pads`, `get_pad_position` and `route_pad_to_pad` used the textbook matrix; KiCad's Y-down axis needs `board_x = fp_x + lx·cosθ + ly·sinθ` and `board_y = fp_y − lx·sinθ + ly·cosθ`.
  - The two forms agree at 0° and 180° and disagree at ±90°, "e.g. reporting a connector's pin 1 at the far end of the connector".
  - The regression test uses routed copper from Antmicro's Kria K26 board (Apache-2.0) as ground truth, because "a purely geometric check cannot catch this on a symmetric pad grid".
  - Source: [commit 2581b40](https://github.com/mixelpixx/Konnect/commit/2581b40d76d57a1ccaf77f24862df81478f54f4d)
- **POA: the same bug (#59), ten weeks later.** `_transform_local_to_board` used the textbook matrix, so "every footprint at a non-180 degree angle came back mirrored". It corrupted footprint bounds, the keepout scan, thermal-via pad centres, dangling-track detection and autoroute's keepout promotion.
  - The back-side special case was also wrong. KiCad already stores a B.Cu footprint's children in the flipped frame, so negating `local_x` moved them by twice their offset.
  - The bug stayed hidden because "every rotated fixture used a square courtyard".
  - Ground truth was `kicad-cli pcb export drill`. Across every KiCad 9 demo board, the new transform matches 2,970 of 2,970 drilled through-hole pads (the old one matched 2,292) and all 1,231 back-side SMD pads against B.Cu Gerber flashes.
  - Source: [commit b588906](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/b58890613d8c7abb061db916dc814f7438042f78)
- **POA: mirror applied before rotation in schematic pin reads.**
  - `get_pin_positions` misreported 28 of 84 pin positions across a 12-orientation sweep.
  - `connect_pins(R1:1, R9:1)` joined R1 pad 2.
  - Angles that do not truncate to 0, 90, 180 or 270 now raise an error.
  - Source: [commit fff4209](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/fff42098b5a291c85e753acdebdb1d8e4903c405)
- **KMS: same mirror/rotation-order class.** It fixed the same order in `pin_world_xy` and aligned rotation direction and mirror axis with eeschema. — [commit 29b213e](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/29b213ec6e2be3d685bdc89d1e3d0822d157d1c2); [commit 7e67cb9](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/7e67cb91c465c77e7c5a01ebadefa8b6b5603a08)
- **Konnect: anchor-only moves over IPC.** "KiCAD 10 serializes a FootprintInstance's children … in ABSOLUTE board coordinates — despite the proto comment on Pad.position claiming footprint-relative." `FOOTPRINT::Deserialize` recreates the children at those coordinates.
  - Updating only position or orientation therefore moved the anchor while copper, silkscreen and text stayed behind, "permanently corrupting the .kicad_pcb on save".
  - The fix applies KiCad's own `SetPosition`/`SetOrientation` rigid-body transform to every child. "Off-axis rectangles become polygons", and unknown item types are rejected.
  - Source: [commit 37adcaa](https://github.com/mixelpixx/Konnect/commit/37adcaaf148f6ae68bbc424fab8637700b15a7b1)
- **POA: rotation left pads and texts behind.** `place_footprint`/`move_footprint` rewrote only the footprint's `(at)`, leaving pad and text angles stale (bugs 2, 53, 63, 87, 89 of #110). The fix:
  - Applies KiCad's `FOOTPRINT::Rotate` with the KeepUpright text rule.
  - Writes angles the way KiCad formats them (270, not −90; omitted at 0).
  - Computes the transform in integer nanometres like `RotatePoint`, choosing KiROUND by the board's format version ("KiCad 10's for a board stamped above 20241229").
  - Source: [commit cf501c7](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/cf501c7faf7069757cd479211b221334b5b74290)
- **POA: flip.** Flipping is KiCad's `FOOTPRINT::Flip`:
  - pad and text angles are rewritten, Y is negated, and layers go through the board's flip map;
  - tenting is swapped on KiCad 10 boards only;
  - zones, KiCad 10 padstacks and partial inner stacks are refused before any edit.
  - Source: [commit 2d4a55f](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/2d4a55fdb0de987fcd67c63d88eaa5ae150d9e91)
  - The earlier `move_footprint(layer=…)` "rewrote the footprint's own layer atom and nothing else, leaving pads on F.Cu … and kicad-cli loaded it without complaint". The measured flip rule: angle → (180 − angle) % 360, local Y negated.
  - Two of the author's own probes measured the wrong thing. At 90° the angle rule is invisible, and pairing items by index failed because KiCad re-sorts them.
  - Source: [commit 45ba30b](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/45ba30b462b28d95f35d9585dd0e3b5740d486ff)
- **Smaller KMS rotation bugs.**
  - IPC `rotate_component` treated the angle as relative while the schema said absolute (#159). — [commit 457e4e3](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/457e4e30ad37a69408497192d2e7c87ce0c7788a)
  - Calling `Flip()` before `board.Add()` caused "a 30s hang in KiCAD 9". — [commit f4d516f](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f4d516f5c33e8af0ec25ba880a986d1064ab68b5)
- **POA: angle spellings.** Angles that KiCad's parser refuses (`+90`, `9_0`, `1e-400`) are read by Python's `float()` as 90, 90 and 0, so a "no change" comparison left an unloadable sheet in place. — [commit 6135102](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/613510237327b2b99d969fc440af55340be7cb5e)
- **JLCPCB pick-and-place rotation corrections** were a separate fix in Konnect. — [commit 103e698](https://github.com/mixelpixx/Konnect/commit/103e69876e611328a48c852d5d1e66fd6efcd52f)

**B. Silent data loss on write**
- **3D models dropped by kicad-python.** "kipy's `FootprintInstance.orientation` setter (kicad-python 0.8.0) rotates the footprint's fields, pads, text, zones and shapes, then rebuilds `definition.items` from only those types — every `Footprint3DModel` is dropped, even when the angle is unchanged." KMS now snapshots the models and re-attaches them, with a tripwire test that pins the upstream behaviour. — [KMS commit ebc2ed1](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/ebc2ed15691d183e25e7eb815f37b5b6a9ec3909)
  - PRO fixed the same loss four weeks later (#1325). — [PRO commit 3659ceb5](https://github.com/oaslananka/kicad-mcp-pro/commit/3659ceb5e7ee9c7ef73e53cc0cad2ca70bbd5dde)
- **`pcbnew.SaveBoard` is "not a reformat: it drops data"** — [adr-cst-substrate.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)
  - Coincident `PCB_SHAPE`s are de-duplicated: the writer uses a `std::set` ordered by `Compare()`, which ignores UUIDs (vme-wren board: 554 → 552).
  - On KiCad 9, every `fp_text` with `(hide yes)` is destroyed at load (32 → 0).
  - `fill_zones` on KiCad's own `multichannel_mixer-unrouted` upgraded the format in place (20241030 → 20241229), dropped 114 footprint property UUIDs, renamed user layers, and returned `status="ok"`.
  - On Windows a no-op round trip converted 760 line endings from LF to CRLF.
  - The fix rule: "a subprocess may compute, never write". pcbnew computes the zone fill read-only, and the polygons are spliced into the user's file.
- **Board net references depend on KiCad version.** Numeric `(net N)` in a KiCad 10 board "is accepted and silently rebound by load order (a real miswire, measured: `(net 2)` landed on GND with no error)". Named `(net "NAME")` in a KiCad 9 board is a hard reject. — [adr-cst-substrate.md ADR-2 guardrail 5](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)
- **Konnect hit the same net-format change from both sides.**
  - Zones on KiCad 10 boards were written as `(net 0)`, "an electrically orphaned pour reported as success" (#192). — [commit f2372ca](https://github.com/mixelpixx/Konnect/commit/f2372ca429688ce955c68d2790ca379869adc637)
  - KiCad 10 boards have no top-level net table. Reading the net name "at index 2 unconditionally" returned `""` for every pad, and `get_board_info` reported 0 nets. — [commit 1a11f69](https://github.com/mixelpixx/Konnect/commit/1a11f69771c5566f6b621ae4ae4eeffdf9a05cd2)
- **Konnect: unknown layer crashed KiCad.** Unknown layer names (`Dwgs.User`, `User.1–45`, inner copper beyond In2) mapped to `BL_UNDEFINED`. KiCad 10.0.5 does not validate the scalar layer field and indexes its layer bitset with it. Placing a stock USB-C footprint "faulted KiCAD at `0xc0000005` … discarding the session's unsaved board"; Konnect saw only an NNG timeout. — [commit ff518c8](https://github.com/mixelpixx/Konnect/commit/ff518c80235c6d546d0b93266fdaad4a57ee0cc4)
- **POA: truncated writes and unloadable values.** Plain `write_bytes` opens with `O_TRUNC`. With a concurrent reader on NTFS, it gave "345 torn reads out of 800 … against 0 out of 25,529 through the [atomic] helper". Separately, `add_trace(layer="banana")` wrote a well-formed file that would not load, so values are now validated before writing. — [CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md); [adr-cst-substrate.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)
- **PRO: concurrent file writes lost edits.** Concurrent file-backed PCB mutations lost edits, and are now serialized. — [commit cda8afca](https://github.com/oaslananka/kicad-mcp-pro/commit/cda8afca6a313029914570cf598a9f114e5cacaa)

**C. Saved-file versus live-board divergence**
- **Konnect: scorer read the saved file.** `score_placement` read the saved `.kicad_pcb` while KiCad held unsaved live moves, so a real courtyard overlap vanished (#595).
  - A negative control reproduced the false-clean result exactly: "verdict 'pass', score 70, zero hard_failures despite a real live collision".
  - The fix prefers the live IPC snapshot (`SaveDocumentToString`) and adds `"source": "ipc" | "saved_file"`.
  - Source: [commit bc3b6c6](https://github.com/mixelpixx/Konnect/commit/bc3b6c6346dad3f2e95f9b97ed3a9aea3bfd319a)
- **Konnect: no file edits after a lost IPC link.** Once a board has been seen live in a session and IPC then drops, file fallback is blocked, because the saved file "may be older than lost editor state". The result is the `unsafe_file_fallback` stop condition. — [commit e3366b9](https://github.com/mixelpixx/Konnect/commit/e3366b98a49bfa51263079d9659e2e8f5b043679); [kicad-pcb SKILL.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect/assets/skills/kicad-pcb/SKILL.md)
- **KMS: save clobbered external edits.** `save_project` called `SaveBoard` unconditionally, "destroying any direct edit made to the .kicad_pcb since the MCP loaded it". It now checks content-hash divergence. — [commit 9e12628](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/9e1262888b5e9026318bb8a4f5884b53bb87873b)
  - The auto-save guard now refuses only on content divergence, not on mtime. — [commit c2c77f5](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/c2c77f5995665729bbaa35790dd2e8ca2e58fba1)
- **KMS: empty IPC read reported as success.** With no document open, an IPC read returned `success:true` with zeroed counts "AND an embedded error string". It now falls back to the file and is tagged. — [commit 96a61bd](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/96a61bd298cc3f21f6aed82ed1923ac21e957890)
- **KMS: dead SWIG board object.** A SWIG `BOARD` proxy can lose its methods after certain sequences (`delete_trace` + auto-save). `open_project` kept reporting success while every later operation failed. — [commit f65eaf2](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f65eaf2798c642eb174af2ace6a9c7e8d2753ec8)
- **KMS: replies shifted by one.** After a tool-call timeout, the late reply resolved the next request, and "every response after that was off by one". Requests now carry an ID. — [commit 42bfa4b](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/42bfa4b41b8e5f2567e7161cc7933c08fc7ee697); [KNOWN_ISSUES.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/KNOWN_ISSUES.md)

**D. "Success" that wasn't, and missing evidence**
- **Konnect: DRC parser discarded two thirds of the result.** It dropped `unconnected_items` and `schematic_parity` from `kicad-cli pcb drc --format json`, "so an unrouted net … was invisible".
  - On the ecc83-pp demo with its 59 segments stripped, KiCad reports 17 violations and 14 unconnected items; Konnect's error count had been 0.
  - Positions were read from a top-level field that "the schema has never had".
  - The rule key, "the only part of a violation a caller can act on", was dropped.
  - Source: [commit e7eeeac](https://github.com/mixelpixx/Konnect/commit/e7eeeac3dc013f4fdeb18598d77fed9e591f2930)
- **KMS: `False == 0`.** `ImportSpecctraSES`/`ExportSpecctraDSN` return `False` on failure. "The check 'result is not True and result != 0' accepted it because False == 0, so autoroute and import_ses answered success with an unchanged board." — [commit f476a97](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f476a9794daaa323e9020010b5d09376c680bbd4)
- **Konnect: mislabeled `check_clearance`.** It returned anchor-to-anchor distance under a description saying "physical clearance". A `21.125` answer "stood in for a courtyard gap of about 3 mm" (#410). — [API_MIGRATIONS.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/API_MIGRATIONS.md); [commit cb74c04](https://github.com/mixelpixx/Konnect/commit/cb74c04a1c1a203fdaaf08af9ad214f7860aaa89)
- **PRO: mocks hid an API shape.** `kipy` `Track.length` is a method, not a property, so net statistics failed on any routed live board. Mocks modelled it as an int, "the mock could only fail in the way its author expected". — [commit 30d02c76](https://github.com/oaslananka/kicad-mcp-pro/commit/30d02c76b74b95ab83d588d43cbbf33630014e7f)
- **PRO: empty versus unavailable.** "empty data remains distinct from unavailable or unreadable board state." — [commit 46f4fafb](https://github.com/oaslananka/kicad-mcp-pro/commit/46f4fafb52676a2dbc4f02d9385a6890d6590357)

**E. KiCad version and IPC-transport incompatibilities**
- **Board format eras.** The highest KiCad 9 board format stamp is 20241229 (`_NUMERIC_NET_VERSION_MAX`). — [CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md)
  - pcbnew 10 upgrades a KiCad 9 board's stamp in place through a bare `LoadBoard` + `SaveBoard`, from 20241229 to 20260206. — [adr-cst-substrate.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)
  - `autoroute_pcb` refuses a KiCad 10 board when only pcbnew 9 is available. — [pcb.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/mcp_server_kicad/pcb.py)
- **Konnect: probing the socket wedged KiCad (#498).** Socket discovery that dialled the socket with a raw connect "never completes NNG's handshake, and afterwards KiCad answers no client at all — its own kipy included — until pcbnew restarts". Discovery now uses filesystem metadata only. — [commit 7e2d787](https://github.com/mixelpixx/Konnect/commit/7e2d787603406e6def19fed28f432d77696a55b3)
- **KMS: units ignored on IPC.** IPC move/place handlers ignored the `unit` field, placing parts "at 1/25.4th of the intended position" when inches were given. — [commit 319a65b](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/319a65bd0b49e47fb4fcf2dd37be46f88fa29caa)
- **PRO: KiCad 10 schema changes.**
  - The KiCad 10 DRC JSON changed how courtyard violations are classified. — [commit 03238cae](https://github.com/oaslananka/kicad-mcp-pro/commit/03238cae9a22b1cfb72df1c5fe4d552a54aaa90a)
  - Deleting a missing ID needs a KiCad 10-specific postcondition. — [commit 47056e46](https://github.com/oaslananka/kicad-mcp-pro/commit/47056e46eab4c9cea9afa5de5d4b8d1fd87f5afe)
- **No headless DSN export on KiCad 10.**
  - Konnect writes its own fail-closed Rust exporter from the IPC snapshot, with an optional ActionPlugin bridge to `pcbnew.ExportSpecctraDSN`. — [KICAD_INTEGRATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/KICAD_INTEGRATION.md)
  - PRO raises `ManualStepRequiredError` (a one-time GUI export) unless `kicad-cli` advertises `pcb export specctra`. — [freerouting.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/utils/freerouting.py)

**F. Freerouting round-trip bugs**
- **PRO: SES coordinates 10× too small.** `(resolution um 10)` declares a grid, not a multiplier: "1 mm = 1000 units, Y negated, no offset". — [commit 565a0203](https://github.com/oaslananka/kicad-mcp-pro/commit/565a02030d68cdb2b0bcddd325f5f5a1014ef66f)
- **KMS: hole clearance.** DSN export turns internal Edge.Cuts holes into plain keepouts, which Freerouting clears at track clearance (0.2 mm) rather than edge clearance (0.5 mm).
  - `router.copper_to_edge_clearance_um` "does not change this (byte-identical SES)".
  - The fix grows circular keepouts by the difference, sized by apothem. Test board: 8 edge violations → 0.
  - Source: [commit da8ff18](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/da8ff187816d5b7adabfe3680c93d125edd0c1fe)
- **KMS: other round-trip fixes.**
  - Net names lost their leading slash through SES and are now reconciled on import (#246). — [commit 8c84fe9](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/8c84fe9862c38c9ba24614d8f78606e6d9947a4f)
  - `.kicad_pro` netclasses were missing from the DSN (#302). — [commit 711b0fe](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/711b0fe31ded406eb72e21654626b8fd6f2c0eeb)
  - The SES `(placement …)` block aborts the whole import when duplicate `REF**` references were renamed `REF**_1` and so on, so the block is now stripped. — [commit f476a97](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f476a9794daaa323e9020010b5d09376c680bbd4)
  - The required Java version is read from the JAR's class-file major version, because Freerouting 2.4.x needs Java 25. — [commit 356be10](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/356be10abf0acf209d961ca9505a9fa8c4ebe9c1)
  - Stale SES files are guarded and artifacts are staged in a temp dir. — [commit a7b4901](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/a7b49012d11673785cafa4dba7f03b6dc4618aea)
- **POA: single-threaded by default.** `num_threads` defaults to 1 "because freerouting prints 'Multi-threaded route optimization is broken and it is known to generate clearance violations' on every run". KMS likewise forces `-mt 1` during scored best-of-N attempts. — [POA pcb.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/mcp_server_kicad/pcb.py); [KMS CHANGELOG.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/CHANGELOG.md)

### Inferences
- **Transform bugs need one oracle-pinned helper.** These bugs appear in every codebase. They are invisible on symmetric parts and at 0° and 180°, so they survive any test suite whose fixtures are symmetric. Our layer should have exactly one transform helper (local↔board, rotate, flip, mirror), pinned to KiCad output such as drill and Gerber coordinates or pcbnew/IPC readback, on asymmetric fixtures at all four orientations, both sides.
- **No server should write through `pcbnew.SaveBoard`.** Every write path that lets pcbnew or kipy re-serialize a whole object lost data somewhere: 3D models, hidden text, coincident shapes, UUIDs, format stamps. The safe options are:
  - a byte-preserving splice, as in POA;
  - a native IPC operation that KiCad itself performs (Konnect's `FlipItems`);
  - a "compute in a subprocess, splice the result" pattern.
- **Version differences must be tested, not inferred.** KiCad 9/10 dialect differences in nets, layers, net tables, DRC JSON and padstacks are not documentable in advance. Each project discovered them by measurement, so a KiCad 9 + 10 CI matrix is mandatory.

### Gaps
- Bug-class counts come from commit subjects and miss fixes labelled `test:`/`docs:`, which are common in POA. Precise counts would need issue labels, and issues were not accessible.
- No codebase reports zone-fill crash statistics beyond KMS's "SWIG segfault" note and the Gato513 report already in `field_reports_and_ux.md`.

## 3. Placement and routing logic: algorithms, Freerouting invocation, verification, and shipped prompts/skills

### Takeaway
- **Placement.** Three projects shipped force-directed (spring-embedder) placement and one shipped HierPlace clustering. Konnect, which put the most engineering into it, retired autonomous whole-board placement within five weeks. It found that force-directed plans pulled parts toward board-wide rails, did not converge, and were applied without proof of improvement. Konnect now recommends small explicit moves, each followed by score_placement and DRC.
- **Routing.** In all four, routing means Freerouting through DSN/SES, plus L-bend pad-to-pad helpers. The best practice is:
  - export from a pinned snapshot;
  - route in a subprocess;
  - validate the SES against a manifest;
  - apply it as one undo transaction;
  - read back and run DRC.

### Cited findings
- **KMS `suggest_placement`.** A "Fruchterman-Reingold flavoured" relaxation (still marked DRAFT in its module docstring):
  - Nets pull parts together, overlapping courtyards push apart, and the board outline contains everything. Power nets (a list of name fragments such as VBAT, VCC, +3V3) and IC↔decoupling links are weighted.
  - A pin-facing rotation pass tries 0/90/180/270 to minimise pad-level wire length, then everything snaps to grid.
  - It is dry-run unless `apply=true` and reports pad-level HPWL. Collisions use the same courtyard axis-aligned bounding box (AABB) as `check_courtyard_overlaps`.
  - Intended loop: "suggest_placement(dryRun) -> check_courtyard_overlaps -> apply -> autoroute(best-of-N) -> run_drc".
  - Source: [placement_optimizer.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/placement_optimizer.py)
- **KMS `hierarchical_place`.** Wraps HierPlace v1.1.0 by Dave Vandenbout (MIT), vendored in. — [_hierplace.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/_hierplace.py)
- **KMS best-of-N autoroute.** Parameters `attempts`, `targetNets` and `passSchedule`. Each attempt varies `--max-passes`.
  - Score = `nets_routed·1000 + segments`, plus 50,000 when every target net routes.
  - "On dense boards a single Freerouting run routinely leaves 1–7 nets unrouted … 3 attempts is usually enough for 4-layer designs; 5–8 for stubborn cases."
  - Ported from morningfire-pcb-automation (MIT).
  - Source: [CHANGELOG.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/CHANGELOG.md); [freerouting.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/freerouting.py)
- **Konnect `score_placement`.** Built as "the objective judge … The metric lands before any placer exists on purpose".
  - Hard failures decide the verdict whatever the score: same-side courtyard-bbox overlaps and parts outside the outline.
  - Soft weights: overlaps ×20 (capped at 40), outside ×20 (cap 40), connector more than 10 mm from the edge ×15 (cap 30), decoupling ×15 (cap 30).
  - The weights are ported from kicad-mcp-pro (MIT, attributed in THIRD_PARTY.md).
  - Source: [placement.rs](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect-core/src/tools/placement.rs); [THIRD_PARTY.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/THIRD_PARTY.md)
- **Konnect outline handling (#594).** The outline is classified as `rectangular`, `unproven` or `missing`. On an unproven outline, containment checks are skipped "as unproven rather than silently passed", and the planners refuse to plan. — [commit 6d43408](https://github.com/mixelpixx/Konnect/commit/6d4340847919dadf9f647a56039c2a3bc55f9979); [API_MIGRATIONS.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/API_MIGRATIONS.md)
- **Konnect placement timeline**
  - **Introduced, 2026-08-26:** `score_placement`, `place_decoupling_caps`, `plan_bga_fanout`, `auto_place_from_schematic` (union-find net clustering) and `refine_placement_force_directed`. — [commit 668af70](https://github.com/mixelpixx/Konnect/commit/668af70808a754acf4c24c60bfd5dae6d1209a53); [commit 54b7f84](https://github.com/mixelpixx/Konnect/commit/54b7f84bc7c000f0eadfe4e4d2b37fa8e40961a6)
  - **Locked footprints, 2026-08-28:** both planners had been moving footprints that KiCad marks locked, because the parser never read `(locked yes)`. A loose text search reports "all 15 as locked" on ecc83, because every footprint carries a nested `(unlocked yes)`. — [commit 32c3bbc](https://github.com/mixelpixx/Konnect/commit/32c3bbc93675c022fb01418f35fe96e1c8698ced)
  - **Force-directed blocked, 2026-09-18:**
    - "Its global-net spring model can pull one footprint toward every other footprint sharing a board-wide rail, and a non-converged plan previously applied without proving that it improved placement."
    - Plans are now blocked unless they converge, improve the score (ties count as no improvement), have no hard failure or off-board target, and respect a required `max_displacement_mm`.
    - Sources: [commit fd4b8fe](https://github.com/mixelpixx/Konnect/commit/fd4b8fee7296fac012ba0d2608ea49ef4551eadd); [API_MIGRATIONS.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/API_MIGRATIONS.md)
  - **Retired, 2026-10-01 (#754):** "autonomous whole-board mutation is retired"; `dry_run:false` returns `plan_blocked`. "Callers should make small, explicit `move_component` operations, read the requested board back after each batch, and run placement scoring and DRC before continuing."
    - Decoupling association now requires the capacitor and IC to share a non-ground net with at most 8 distinct references ("a shared ground rail [is not] proof").
    - Sources: [commit 4ae4048](https://github.com/mixelpixx/Konnect/commit/4ae4048d6496361a5cfef22579ab8e7f599c764f); [API_MIGRATIONS.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/API_MIGRATIONS.md)
  - **Force-directed constants:** `K_SPRING 0.4`, `K_REPEL 80`, `K_WALL 5`, damping 0.85, grid 0.5 mm, patience 4; power nets weighted 3×, differential pairs 5×. — [placement.rs](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect-core/src/tools/placement.rs)
- **PRO placement.** `force_directed_placement` is a spring embedder with springs, Coulomb repulsion, boundary walls, spiral search for a free spot and keepout checks; a BGA fanout planner sits in the same module. Tools built on it: `pcb_auto_place_by_schematic`, `pcb_auto_place_force_directed`, `pcb_group_by_function`, `pcb_place_decoupling_caps`, `pcb_critique_placement`, `pcb_score_placement`. — [utils/placement.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/utils/placement.py); [tools-reference.generated.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/tools-reference.generated.md)
- **Pad-to-pad routing helpers** — [Konnect SKILL.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect/assets/skills/kicad-pcb/SKILL.md); [KMS TOOL_INVENTORY.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/TOOL_INVENTORY.md)
  - Konnect's `route_pad_to_pad` lays one or two segments in an L on a single layer and adds no via.
  - KMS's version inserts a via automatically when the pads are on different layers.
  - Konnect's skill tells the model to read `get_component_pads` geometry before choosing approach points: "A null geometry field is unavailable evidence, not a zero-size pad".
- **How Freerouting is invoked**
  - **Common command line:** all four run `java -jar <jar> -de <dsn> -do <ses> -mp <passes>`.
  - **KMS** can also run it in Docker (`eclipse-temurin:<N>-jre`). — [KMS freerouting.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/freerouting.py)
  - **POA**, in order:
    1. Pins Freerouting 2.5.0 by SHA-256.
    2. Promotes footprint-level keepouts to board level.
    3. Exports DSN with `pcbnew.ExportSpecctraDSN` in a subprocess.
    4. Runs Freerouting.
    5. Imports the SES into a new `<stem>_routed.kicad_pcb`.
    6. Fixes displaced footprint text.
    7. Runs `kicad-cli pcb drc --format json` and reports `traces_added`, `vias_added`, `drc_violations` and `drc_unconnected`.
    - Source: [pcb.py autoroute_pcb](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/mcp_server_kicad/pcb.py)
  - **Konnect** runs `export_specctra_dsn` (revision-bound DSN + reverse manifest from the IPC snapshot) → `route_specctra_dsn` (drives Freerouting's native headless MCP server, a loopback-only child that is always reaped) → `plan_specctra_ses_import` → `apply_specctra_ses`.
    - The apply keeps locked tracks and vias, applies "through KiCad IPC as one undo transaction", verifies "post-commit IPC read-back", creates a separate candidate board, and reports DRC.
    - The DSN exporter is deliberately narrow and fails closed: it rejects boards with copper zones or rule areas, existing arcs, or unlocked tracks and vias.
    - The roadmap lists expanding the round trip "beyond its current two-layer boundary".
    - Sources: [README](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/README.md); [specctra.rs](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect-core/src/specctra.rs); [ROADMAP.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/ROADMAP.md)
  - **PRO** has a headless SES apply service that writes the routed SES through a transactional board writer (`router_core.apply_ses_to_pcb`). — [ses_apply.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/routing/ses_apply.py)
- **Shipped skills and prompts**
  - **POA: six skills.**
    - The skills are `using-kicad`, `circuit-design`, `schematic-plan`, `schematic-design`, `pcb-layout` and `verification`. Reviewer subagents (BOM, code, schematic plan) check artifacts.
    - The `pcb-layout` skill begins with a CRITICAL-RULE: "NEVER use the Read, Write, or Edit tools on KiCad files … NEVER run kicad-cli commands via Bash … If you find yourself thinking 'there's no MCP tool for this,' you are wrong."
    - Its layout process: import the netlist → board setup → place by function → route critical nets → route the rest or autoroute → refine (net classes, wider power traces, thermal vias, `remove_dangling_tracks`) → zones → DRC until clean.
    - Source: [skills/pcb-layout/SKILL.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/skills/pcb-layout/SKILL.md)
  - **Konnect: six skills** (`kicad-pcb`, `kicad-schematic`, `kicad-review`, `kicad-manufacture`, `kicad-library`, `konnect`), with reference files for layers, trace widths and design rules. — [kicad-pcb SKILL.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/crates/konnect/assets/skills/kicad-pcb/SKILL.md)
  - **PRO: seven skills**, including `pcb-design`, `drc-check` and `visual-excellence`. — [skills/](https://github.com/oaslananka/kicad-mcp-pro/tree/44617f39108c822ab2a02fc557bcffa802e66fea/skills)
  - **KMS: MCP prompts**, such as `component_placement_strategy`. — [src/prompts/component.ts](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/src/prompts/component.ts)
- **The maintenance-mode experiment (POA, 2026-10-19)** — [README "Why maintenance mode"](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/README.md); [commit ad0230c](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/ad0230c95b1bfe8d50a35199cec2f179034ee576)
  - **Setup:** the same model (Claude Opus 5.5), with and without the plugin, judged by KiCad 10 itself (netlist, board, ERC, DRC).
  - **Single edits:** "Six single edits … three runs each. Plain Claude Code got all 18 right. With the plugin, 3 of 18 were right."
  - **Long session:** in a 20-edit session both got every edit right, but the plugin used "about 1.8 times as much context".
  - **Causes:**
    - missing tools (a pad's net, the DNP flag, swapping one footprint);
    - its "never edit KiCad files directly" instruction made the model stop and ask;
    - "Its board-sync tool rewrote almost every footprint on the board, so the model undid its own work."
  - **Conclusion:** "Plain Claude Code changed a 2 MB board without reading it whole: it searched for the part and edited only the lines it needed."
  - **Caveat in the README:** "small tests on one design"; the test material is not published.

### Inferences
- **What retirement means for placement.** Konnect is the best-engineered placement attempt among the four, and it retired, rather than improved, its global heuristic placers. That is strong practitioner evidence that a generic spring embedder applied to a whole board without constraints is not an acceptable autonomous placer. Two conditions are needed:
  - real constraints (locks, outline polygon, function groups, decoupling associations that are not ground-based);
  - a scorer that blocks non-improving moves.
  Our placer must earn its applies against a referee it does not control. Konnect's "metric before placer" ordering is the right sequence.
- **The POA result.** The result carries the "small tests on one design" caveat, but it directly challenges the "MCP tools only, never touch files" doctrine that POA and PRO both enforced through hooks and skills (PRO commit "keep Claude PCB edits on MCP tools" — [commit 26681ed7](https://github.com/oaslananka/kicad-mcp-pro/commit/26681ed7e487cad4907128490f32f53b8cffd7e3)). The lesson is not "no tools". Three things follow:
  - Tools must cover every edit class, or they must permit a verified direct edit.
  - Tool instructions must not forbid the agent's general abilities.
  - Bulk tools such as board sync must not rewrite unrelated objects.
- **Freerouting needs supervision.** The best-of-N pass schedule, single-threaded optimization, hole-keepout growth, SES placement stripping, netclass export and net-name reconciliation are each a documented Freerouting pitfall. A KiCad Freerouting wrapper that lacks any one of them will fail silently on real boards.

### Gaps
- None of the repos publishes quantitative placement-quality results for its placers: no HPWL or DRC-pass rates on a corpus. Konnect's retirement rationale is qualitative; the commit messages contain no numbers.
- Konnect's `route_specctra_dsn` depends on Freerouting's native MCP server. Its behaviour on 4+ layer boards is explicitly unsupported (the two-layer boundary in the roadmap).

## 4. Tests: what is tested, against real KiCad or not, and fixtures reusable for our benchmark

### Takeaway
- **Judges, not mocks.** The strongest test strategy is POA's: every test is judged by something that is not the code under test, such as KiCad's own Python, `kicad-cli` output, Python ports of KiCad routines, or exact integer geometry. KMS mostly tests against `MagicMock` stubs of pcbnew.
- **Reusable assets.**
  - PRO's 14 pass/fail benchmark projects with defect classes, and its attempt-accounting contract;
  - POA's KiCad-reference ports and pcbnew judge;
  - Konnect's live-DRC regression recipe.

### Cited findings
- **POA test ladder.** About 1,950 test functions in `tests/` (counted by grep).
  - Rung files `test_ladder_r<N>`: 1 bytes and tokens, 2 numbers and geometry, 3 single-element edits, 4 whole-file reads, 5 one tool call, 6 composite tools, 7 end to end.
  - "Every test has a judge that is not the code under test."
  - An autouse fixture runs `kicad-cli` on every KiCad file a test leaves behind.
  - The only allowed xfail is a strict xfail naming a numbered bug and the step that fixes it.
  - Hypothesis runs 200 examples in CI and 5,000 nightly.
  - CI runs the full suite on Linux with KiCad 9 and KiCad 10, and on macOS and Windows with KiCad 10.
  - Source: [CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md)
- **POA judges and harness**
  - `tests/pcbnew_judge.py` runs scripts under KiCad's own Python: "pcbnew is KiCad's board model, so what it computes … is KiCad's answer by definition". It asks pcbnew for its own version rather than trusting the package's probe. — [pcbnew_judge.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/pcbnew_judge.py)
  - `tests/kicad_ref/` ports KiCad's `trigo`, `transform`, footprint `SetPosition`/`SetOrientation`/`Rotate`/`Flip`, pad and board-layer pairs, the DSN lexer and unit parsing. — [tests/kicad_ref](https://github.com/ProductOfAmerica/mcp-server-kicad/tree/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/kicad_ref)
  - `tests/kicad_corpus.py` sweeps the demos and libraries a KiCad install ships. — [kicad_corpus.py](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/tests/kicad_corpus.py)
  - `tools/routing_harness/` compares `kicad-cli` netlist node sets before and after each tool call. — [adr-routing-safety.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-routing-safety.md)
- **POA measured wiring failures.** "16 of 36 generated layouts built the way the repo's skills prescribe came out shorted", and the wrong pin was wired in 4 of 12 orientations. — [adr-routing-safety.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-routing-safety.md)
- **Konnect tests.**
  - About 2,445 `#[test]`/`#[tokio::test]` functions (counted by grep), an NNG mock server, and `--ignored` live tests that need a disposable board open in KiCad (`KONNECT_LIVE_KICAD_BOARD`).
  - A weekly Windows E2E job installs KiCad 10.0.5 with choco.
  - Governance requires a "negative control": neutralize the guard and show its regression test fails.
  - Fixtures include 20 `.kicad_pcb` files: KiCad demos such as `pic_programmer` and `ecc83`, plus Antmicro's Kria K26 board for transform ground truth.
  - Sources: [DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md); [RELIABILITY_CONTRACT.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/RELIABILITY_CONTRACT.md); [e2e-kicad.yml](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/.github/workflows/e2e-kicad.yml); [commit 2581b40](https://github.com/mixelpixx/Konnect/commit/2581b40d76d57a1ccaf77f24862df81478f54f4d)
- **Konnect live DRC regression recipe:**
  1. Create and save a via.
  2. Delete it without saving.
  3. Prove that file-only DRC still reports the via's UUID.
  4. Prove that synchronized DRC drops it after refill and save.
  - Source: [DRC_SYNCHRONIZATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/DRC_SYNCHRONIZATION.md)
- **PRO tests and evals.**
  - About 5,250 `def test_` functions.
  - A golden corpus of 14 small KiCad projects under `tests/fixtures/benchmark_projects/`, with per-gate expected outcomes:
    - pass cases: `pass_minimal_mcu_board`, `pass_sensor_node`;
    - fail cases: `fail_bad_decoupling_placement`, `fail_footprint_overlap_board`, `fail_dfm_edge_clearance`, `fail_dirty_transfer_wrong_pad_nets`, `fail_sensor_cluster_spread`, `fail_label_only_schematic`;
    - KiCad 10 feature cases: custom DRC, design blocks, time-domain, variants.
  - Source: [golden_corpus.yaml](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/evals/golden_corpus.yaml)
- **PRO tool-selection evals.** Each case declares `expected_tools`, `forbidden_tools`, a safety tier (read_only, write, export, publish, human_only, no_tool) and `max_calls`. A scorer measures recall, safety violations, unnecessary calls and nondeterminism across repeated runs. — [evals/README.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/evals/README.md)
- **PRO reference-board publication contract (#730).** Each attempt directory holds `specification.md`, `original-prompt.md`, `benchmark.json` (`pcb-task-outcome.v1`) and an `attempt-manifest.json` with SHA-256 digests over every attempt.
  - Failed attempts stay in the denominator. An "infrastructure_invalid" exclusion is refused if the agent log shows any tool call.
  - A `manual_repair=true` success is "not publishable as autonomous success".
  - The README says its own native-live evidence "intentionally reports `insufficient_evidence`".
  - Sources: [reference-board-corpus.md](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/development/reference-board-corpus.md); [commit 2cd28fc8](https://github.com/oaslananka/kicad-mcp-pro/commit/2cd28fc8e24e070f2142b596afa20ce0c62ccb56); [README](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/README.md)
- **KMS tests.** About 2,309 test functions. `tests/conftest.py` installs `MagicMock` stubs for `pcbnew` (`GetBuildVersion` returns "9.0.0-stub") and for `skip`. Real-pcbnew smoke tests run only with `KICAD_USE_REAL_PCBNEW=1`. CI installs KiCad from the PPA. — [conftest.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/tests/conftest.py); [test_real_pcbnew_matrix.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/tests/test_real_pcbnew_matrix.py)

### Inferences
- **What to adopt for our benchmark:**
  - PRO's attempt-accounting contract (full denominator, no silent exclusion, manual repair is not autonomous success);
  - Konnect's and POA's "independent judge plus negative control" testing rules;
  - POA's drill/Gerber-coordinate oracle for every transform.
- **Fixtures.**
  - PRO's 14 fixture projects are tiny but MIT-licensed, with labelled defect classes. They make good smoke and regression fixtures for "detect bad placement" gates.
  - KiCad's shipped demos (ecc83, pic_programmer, multichannel_mixer, vme-wren) are the shared real-board corpus that POA and Konnect both test against.
  - Antmicro's Apache-2.0 open hardware gives routed ground truth.

### Gaps
- Test-function counts are grep counts and include parametrized bases. They were not run.
- None of the four publishes a placement or routing quality benchmark result on a board corpus. PRO's reference-board corpus is infrastructure only: "does **not** by itself satisfy the requirement to publish at least three serious reference boards".

## 5. Licenses (verified from LICENSE files) and reuse potential

### Takeaway
- **Compatibility.** Three of the four are reusable in a GPL-3.0 project. Two are reusable in a permissive project:
  - KMS: MIT.
  - kicad-mcp-pro: MIT.
  - mcp-server-kicad: GPL-3.0-or-later, but MIT up to v0.20.1.
- **Konnect** is AGPL-3.0 with a CLA and commercial dual licensing; treat it as reference only.

### Cited findings
- **KMS:** "MIT License, Copyright (c) 2024 mixelpixx". — [LICENSE](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/LICENSE)
  - It vendors HierPlace v1.1.0 (MIT, Dave Vandenbout). — [_hierplace.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/_hierplace.py)
  - Its best-of-N scoring is ported from morningfire-pcb-automation, whose LICENSE reads "MIT License, Copyright (c) 2026 Morning Fire LLC". — [morningfire LICENSE](https://raw.githubusercontent.com/NiNjA-CodE/morningfire-pcb-automation/main/LICENSE)
- **Konnect:** GNU AGPL-3.0, "free for individuals and open source; commercial licenses available". — [LICENSE](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/LICENSE); [COMMERCIAL.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/COMMERCIAL.md)
  - Contributions fall under a Contributor License Agreement. — [CONTRIBUTING.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/CONTRIBUTING.md)
  - It includes MIT-licensed portions ported from kicad-mcp-pro (CPL rotation table, placement scoring weights, calculator formulas, release-gate lattice) and from Topola (DSN syntax). — [THIRD_PARTY.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/THIRD_PARTY.md)
- **kicad-mcp-pro:** "MIT License, Copyright (c) 2026 Osman Aslan". — [LICENSE](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/LICENSE)
- **mcp-server-kicad:** relicensed "under GPL-3.0-or-later" on 2026-10-14, because "Its test judges in tests/kicad_ref are deliberate ports of KiCad's GPL source". NOTICE says "Releases up to and including 0.20.1 were published under the MIT License". The v0.20.1 version bump was 2026-08-15. — [commit 71fa70d](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/71fa70d15826a6d376df7a17d9fa4c09777c3e65); [NOTICE](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/NOTICE); [commit 511a50d](https://github.com/ProductOfAmerica/mcp-server-kicad/commit/511a50d6bf6f1a0df1b2c965443efa674d2fe618)

### Inferences
- **For a GPL-3.0 project:**
  - The candidates for direct reuse, with notices kept:
    - POA's `_cst.py`: byte-preserving, stdlib-only, round-trips 15,711/15,711 files.
    - POA's orientation helpers (`_fp_translate`, `_fp_turn`, `_fp_rotate_to`, `_fp_flip`).
    - POA's `tests/kicad_ref` ports and `pcbnew_judge`.
    - KMS's Freerouting wrapper (best-of-N, hole-keepout growth, SES placement pruning, Java detection).
    - PRO's placement scorer, golden corpus and eval scorer.
  - Konnect code can legally be combined only under GPLv3 §13 + AGPL. That would put AGPL network obligations on the combined work, so copy patterns, not code.
- **For a permissive project:** limit reuse to KMS, PRO and POA at v0.20.1 or earlier, which is MIT, and notably predates the CST board slices of 2026-08-10. POA's later transform fixes (October 2026) are GPL-only. Konnect is off-limits.

### Gaps
- The exact `git` tag for POA v0.20.1 was not fetched (only `v0.21.1` exists in the shallow clone). The bump commit above identifies it.
- The license of Konnect's Antmicro fixture (Apache-2.0) is quoted from a commit message, not from a LICENSE file in the fixture directory.

## 6. Concrete design lessons for our own tool layer: abstractions to adopt, pitfalls to avoid, code to reuse

### Takeaway
- **Adopt** the safety and evidence machinery the four projects converged on:
  - an explicit live-versus-saved data source on every answer;
  - plan → revision-bound apply;
  - native commit groups, one undo per agent step;
  - fail-closed refusals that leave the file intact;
  - outcome envelopes that separate "check did not run" from "zero findings";
  - a scorer built before any placer.
- **Avoid** these mistakes:
  - re-serializing whole objects through pcbnew or kipy;
  - hand-written transforms;
  - silent fallbacks;
  - echoing requested values as proof;
  - tool doctrines that forbid the agent from reading files or running `kicad-cli`.

### Cited findings
- **Live versus saved state is the number-one correctness hazard.** Each project hit it independently. — [Konnect commit bc3b6c6](https://github.com/mixelpixx/Konnect/commit/bc3b6c6346dad3f2e95f9b97ed3a9aea3bfd319a); [KMS IPC_BACKEND_STATUS.md (#223)](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/IPC_BACKEND_STATUS.md); [KMS commit 9e12628](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/9e1262888b5e9026318bb8a4f5884b53bb87873b); [Konnect commit f2372ca](https://github.com/mixelpixx/Konnect/commit/f2372ca429688ce955c68d2790ca379869adc637)
- **Native KiCad operations beat re-implementations wherever they exist.** Examples: `FlipItems` on 10.0.6 including the 3D-model transform, `RefillZones`, and commit groups. Konnect's roadmap filter is "native capability first, transparent AI-directed workflow second, Konnect-owned replacement only by deliberate exception". — [KICAD_INTEGRATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/KICAD_INTEGRATION.md); [ROADMAP.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/ROADMAP.md)
- **Commit groups are invisible until pushed.** Read-back inside a commit group is impossible on KiCad 10.0.5, so verification must run after the push. Schematic-to-board creates are chunked into groups of at most 32 inside one commit, and live testing showed one Undo restoring 70 footprints. — [PRO evidence (commit cc91138e)](https://github.com/oaslananka/kicad-mcp-pro/commit/cc91138e2834204d5eb0e9c285cf4ab07cd209ae); [Konnect commit bb45526](https://github.com/mixelpixx/Konnect/commit/bb455261259333a79168a21ad6b74898215e6ca1); [API_MIGRATIONS.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/API_MIGRATIONS.md)
- **Retrying after an uncertain IPC write is dangerous.** Konnect reports "uncertain outcomes without blind rollback". PRO raises an `AmbiguousMutationError` that puts the session into recovery-required state. — [Konnect commit f553696](https://github.com/mixelpixx/Konnect/commit/f553696ad1a4aefdbb5441847bdedf72a2a1be43); [PRO transaction_lifecycle.py](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/src/kicad_mcp/pcb/transaction_lifecycle.py)
- **Never connect to KiCad's socket just to probe it.** It wedges the NNG server. — [Konnect commit 7e2d787](https://github.com/mixelpixx/Konnect/commit/7e2d787603406e6def19fed28f432d77696a55b3)
- **Validate every layer name** before sending an item over IPC. — [Konnect commit ff518c8](https://github.com/mixelpixx/Konnect/commit/ff518c80235c6d546d0b93266fdaad4a57ee0cc4)
- **Board-sync tools are a collateral-damage risk.** POA's sync "rewrote almost every footprint on the board, so the model undid its own work". — [POA README](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/README.md)

### Inferences
**Adopt:**
1. **Source disclosure.** Every read returns `source: live|saved|mixed`, `board_rev` (a hash of the live snapshot from `SaveDocumentToString`, or of the file bytes) and `kicad_version`.
2. **Plan/apply with revision binding.** Write tools take `dry_run` (default true for batch operations) and return `plan_id` + `base_rev`. Apply requires the matching `base_rev` and refuses on drift. This is Konnect's `expected_plan_revision`.
3. **One undo per agent step.** All writes in a step go into one IPC commit group, with verification after the push.
4. **Outcome envelope.** One of `complete`, `partial` (with applied, failed and unattempted items), `refused` (with proof nothing changed), `uncertain` (stop and reconcile) or `check_unavailable`. A result carries `null`, never `0`, for a category that was not checked.
5. **Independent referee.** The placement score and the DRC/unconnected/parity gates are implemented separately from the placer, and the placer cannot apply without improving the score.

**Avoid:**
- hand-coding a rotation (or any transform) more than once;
- trusting proto comments about coordinate frames;
- using pcbnew `SaveBoard` or kipy whole-object setters on a user's file;
- bounding-box-only containment for non-rectangular outlines;
- inferring decoupling from shared GND;
- treating "transport OK" as "applied";
- file fallback after a board has been seen live;
- dynamic tool loading that depends on the client honouring `list_changed`;
- skill text that forbids `kicad-cli` and file reads.

**Reuse, if GPL-compatible:**
- POA `_cst.py` and its orientation helpers;
- the KMS Freerouting wrapper;
- the PRO placement scorer and evals;
- POA `pcbnew_judge` and `kicad_ref` for tests.

### Gaps
- No project measured LLM task success as a function of tool granularity, apart from POA's small A/B. That is the main open question for our design.

## Implications for an LLM-driven KiCad placer/router

### Takeaway
- **Separate measurement from mutation.** Build a small surface (about 20 to 25 tools) that keeps the two apart:
  - **Read and score:** rich, bounded, source-tagged reads plus independent scorers and DRC gates.
  - **Propose:** deterministic placement and routing engines that return candidates, never writes.
  - **Apply:** revision-bound, one-undo commits through native KiCad operations.
- **Do not forbid raw file access.** Allow kicad-cli and raw-file escape hatches with mandatory verification.
- **Freerouting as a supervised subprocess.** Use Freerouting with best-of-N, the documented pitfall fixes, and post-route DRC.

### Cited findings
- **Placement:** autonomous whole-board heuristic mutation was retired in favour of small, explicit, scored moves. — [Konnect API_MIGRATIONS.md #754](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/API_MIGRATIONS.md)
- **Tool restrictions:** "MCP-only" tool restrictions underperformed plain Claude Code + `kicad-cli` on single edits (3/18 versus 18/18, small test). — [POA README](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/README.md)
- **Catalogue size:** the full catalogue costs about 57k tokens versus about 2.3k for 24 tools. — [PRO profile snapshot](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/evidence/progressive-disclosure-profile-snapshot.json)
- **Commit visibility:** commit groups give one undo step but are invisible until pushed. — [PRO commit cc91138e](https://github.com/oaslananka/kicad-mcp-pro/commit/cc91138e2834204d5eb0e9c285cf4ab07cd209ae)
- **Freerouting pitfalls** are listed in §2F, with sources there.

### Inferences
**Recommended tool-surface spec.** The signature notation below is pseudo-Python. All lengths are mm, angles are degrees counter-clockwise as KiCad displays them, and coordinates are board coordinates in KiCad's Y-down frame.

**State model**
- A session is bound to exactly one board identity: project path, board path and KiCad instance token.
  - `backend` is `ipc_live` when KiCad holds the board open, or `file` when no KiCad instance holds it.
  - Once a board has been seen live, file writes are refused for the rest of the session (Konnect `unsafe_file_fallback`).
- Every response carries `{source, board_rev, kicad_version, outcome}`. `board_rev` is the SHA-256 of a normalized live snapshot or of the file bytes.
- Mutation flow is `propose_* → candidate {candidate_id, base_rev, diff, predicted_score}` then `apply_candidate(candidate_id, expected_rev)`.
  - Apply refuses if the board revision drifted.
  - It applies through one IPC commit group (chunked, one undo entry), or through an atomic byte-preserving splice in file mode.
  - It then reads back and runs verification hooks.
- Transport rules: correlate requests by ID; never socket-probe; bound timeouts; treat an uncertain write as `uncertain`, and do not retry it.

**Read and inspect tools.** All are bounded, with `limit`/`offset` and `_total`/`_truncated` fields.
1. `board_summary() -> {outline:{shape: rect|polygon|unproven, polygon_mm, area}, layers, stackup, netclasses, counts, design_rules, source, board_rev}`
2. `list_footprints(filter?: {refs?, side?, locked?, group?, bbox?}, fields?=[ref,value,fp_lib_id,x,y,rot,side,locked,courtyard_poly?]) -> rows`
3. `get_pads(refs | net) -> [{ref, pad, x, y, layer_set, shape, size, drill, net, local_xy}]`, with board coordinates computed by the single oracle-pinned transform.
4. `get_netlist(scope?: nets | ref) -> {net: {class, pads:[ref:pad], is_power, fanout}}`
5. `get_ratsnest(nets?) -> [{net, from, to, length}] + total_hpwl`
6. `render(view: top|bottom|layer_set, bbox?, highlight?: {refs, nets, markers}, px?: 1024) -> image`, using a `kicad-cli` SVG→PNG render. A PNG is returned only when asked, never by default.

**Score and verify tools** (the independent referee)
7. `score_placement(candidate_id? | current) -> {verdict: pass|hard_fail|outline_unproven|outline_missing, score, deductions[], hard_failures[], decoupling_associations[], source}`
   - Hard failures: polygon courtyard overlap and outside-outline containment.
   - Soft metrics: HPWL, connector-to-edge, decoupling distance using non-ground associations only, and thermal/keepout rules from our rule packs.
8. `run_drc(sync_live?: true, refill_zones?: true, categories?: all) -> {violations[], unconnected[], parity[] (null if not run), by_rule, source_evidence}`. It never drops `unconnected_items` or `schematic_parity`, and keeps each rule key and each item's position.
9. `check_connectivity(expected_netlist?) -> {shorts[], opens[], pad_net_mismatches[]}`, comparing `kicad-cli` netlist node sets before and after.

**Propose tools** (deterministic, never write)
10. `propose_placement(refs | group, constraints: {fixed[], keepouts[], regions{group: polygon}, rotate_set?: [0, 90, 180, 270], side?}, objective?: weights, seed?) -> candidate`
    - It refuses on an unproven outline unless the constraints carry an explicit containment polygon.
    - A candidate whose `predicted_score` does not beat the current score is marked `blocked`.
11. `propose_moves(moves: [{ref, x?, y?, rot?, side?, dx?, dy?}]) -> candidate`. This is the small-explicit-move path the LLM uses most, scored like any other candidate.
12. `propose_route(nets | netclass, engine: freerouting|pad_to_pad|fanout, layers?, attempts?: 3, pass_schedule?, keep_existing?: locked_only) -> candidate`
    - Freerouting setup: hash-pinned jar; `-mt 1`; netclasses exported; hole keepouts grown by the edge-clearance delta; footprint keepouts promoted; SES `(placement)` stripped; net-name reconciliation.
    - Best-of-N scoring: `nets_routed·1000 + segments + 50,000` when every target net routes, plus a post-import DRC delta.
    - Coordinates: 1 mm = 1000 SES units, Y negated.
13. `propose_fanout(ref, style: dogbone|inline, via_rule?) -> candidate`, the BGA/QFN escape plan.

**Apply and transaction tools**
14. `apply_candidate(candidate_id, expected_rev, description) -> {outcome, applied[], board_rev_after, verification:{score, drc_summary, connectivity}}`
15. `undo_last(n?: 1)` (a native undo through KiCad) and `revert_to(rev)` (from a snapshot journal; file mode only).
16. `snapshot(label) -> rev` and `diff(rev_a, rev_b) -> {moved[], added[], removed[], nets_changed[]}`

**Escape hatches** (explicitly allowed, given the POA result)
17. `kicad_cli(args[]) -> {rc, stdout, artifacts}`, restricted to the documented subcommands (drc, erc, export, render, upgrade), with outputs written to a temp directory.
18. `raw_edit(path, splice: {anchor_uuid, old_sexpr, new_sexpr}, expected_rev) -> outcome`. This is a byte-preserving CST splice, followed by a `kicad-cli` load check and connectivity verification. It is refused while the board is open live.

**Verification hooks on every apply.** These run automatically and their results are returned inline:
- (a) Read back each touched object and compare it with the intent, never with an echo of the request.
- (b) Check the 3D-model, field and pad counts on every touched footprint, to catch whole-object re-serialization loss.
- (c) Run `score_placement` for placement applies, and `run_drc` with unconnected items for routing applies.
- (d) Check connectivity against the expected netlist.
- (e) Confirm the format stamp is unchanged in file mode.

A failure in any of (a) to (d) makes the outcome `partial` or `uncertain`, with the first mismatch named.

**Engineering rules for our implementation**
- **One transform module.** Port KiCad's `RotatePoint`/`Flip` in integer nanometres, with KiROUND chosen by format era. Test it against `kicad-cli` drill and Gerber coordinates on asymmetric footprints at 0/90/180/270°, on both sides.
- **Version-gated emitters** for nets (numeric up to 20241229, named after it) and layers (canonical names only). Run a CI matrix on KiCad 9.0.x and 10.0.x.
- **Evaluation contract.** Adopt PRO-style attempt accounting for our benchmark, and run tool-selection evals with forbidden tools and call budgets.
- **Keep the always-visible core small.** About 12 tools, named in the server instructions. Load the propose/route tools as a toolset only when the client supports `list_changed`; otherwise expose them all.

### Gaps
- This spec has not been tested. It needs head-to-head trials of tool-only, tool plus escape hatches, and coding-agent-only, on a shared board corpus, which none of the four repos has published. The POA trial is the only direct evidence, and it is small.
- KiCad 11's headless `kicad-cli api-server` would let the IPC path run without a GUI. PRO tracks it as preview-only and blocked on upstream ([ADR-0007](https://github.com/oaslananka/kicad-mcp-pro/blob/44617f39108c822ab2a02fc557bcffa802e66fea/docs/adr/0007-kicad-adapter-selection-and-swig-retirement.md)). Until then, live commit groups need a running GUI instance, or a file-mode equivalent built from a snapshot journal.
