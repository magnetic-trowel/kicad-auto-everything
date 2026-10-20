# Existing Tools, Products, Plugins and APIs for Automated / AI-Assisted PCB Placement and Routing (KiCad + LLM-agent focus), as of Oct 2026

> Research-method note for the report writer. **Pass 1** (restricted network): kicad.org, quilter.ai, deeppcb.ai, flux.ai, arxiv.org, HN, Reddit, EEVblog, forum.kicad.info, hackaday.com and jitx.com were unreachable. KiCad facts in that pass therefore come from primary sources on GitLab: the KiCad source tree, the IPC `.proto` files, the `kicad-dev-docs` source and the `kicad-website` blog source. **Pass 2** (2026-10-20, fuller access) filled the pass-1 gaps: TopoR, Electra, Specctra/Allegro PCB Router, Altium Situs, Siemens, CELUS, Circuit Mind, Diode, SnapMagic, EasyEDA/JLCEDA, route-rnd/toporouter, Horizon, LibrePCB, the KiCad PCM catalog, a broader MCP/LLM-tool sweep, PCBWorld, EEBench, and HN/KiCad-forum sentiment.
>
> **Provenance tags.** Bullets added in pass 2 carry **[P]** (read directly from the cited primary page, repo, source file, paper or API this session) or **[S]** (search-engine summary or secondary coverage only, not opened at the source). Pass-1 bullets have no tag. Their rule: GitHub/GitLab/PyPI/npm sources were read directly (primary); bullets that say "(snippet)" or "(search snippet)" were not.
>
> **Still unreachable in pass 2:** Reddit (the proxy returns 403 "Blocked"), repo.hu (pcb-rnd/route-rnd home; I used Debian's source mirror instead), horizon-eda.org, jlceda.cn. WebSearch was exhausted again near the end of pass 2, so a few items stay [S]. A separate agent is verifying KiCad API/DRC facts, Freerouting, KiCadRoutingTools, kicad-happy, the leading MCP servers, Quilter, DeepPCB, Flux, Allegro X AI and Zuken, so pass 2 adds little on those. Star counts and push dates come from GitHub search on 2026-10-20.

## 1. KiCad programmatic interfaces (IPC API, kicad-python/kipy, SWIG, kicad-cli, file formats, KiCad 9/10 automation features, built-in tools)

### Takeaway
KiCad 10.0.x is the current stable line (10.0.0 shipped 2026-03-20; 10.0.7 on 2026-10-07). Its IPC API (protobuf over NNG) with the official `kicad-python` (`kipy`, MIT, v0.8.0) can read and edit almost everything on a board: footprints, tracks, vias, zones, nets, selection, and undoable commits. On KiCad 9/10 it has three hard limits: it needs a running KiCad GUI, it has no plotting or export, and it has no schematic editing. The API also exposes no routing or placement algorithms. The only way to reach the built-in push-and-shove "Autoroute" or the legacy autoplacer is the unstable `RunAction` escape hatch. KiCad 11, still in development, adds a headless `kicad-cli api-server`, export jobs over IPC (including Specctra DSN export and SES import), schematic API commands, and removes the SWIG `pcbnew` bindings.

### Cited Findings
**IPC API design and status**
- The IPC API "can be used to remotely control a running instance of KiCad"; it uses "Protocol Buffers to define the structure and contents of messages, and NNG to transport messages between processes using UNIX sockets" (named pipes on Windows). API events are handled synchronously on KiCad's single UI thread, so clients "need to anticipate that API messages may sometimes timeout or fail because KiCad is busy" and "should not open multiple connections" — [KiCad dev-docs: IPC API (source)](https://gitlab.com/kicad/services/kicad-dev-docs/-/blob/master/content/apis-and-binding/ipc-api/_index.en.adoc)
- Stability policy: new KiCad versions "may introduce new messages and fields, but will not modify the meaning of existing messages"; deprecated items stay supported "for at least one major version" after the deprecation is announced — [same](https://gitlab.com/kicad/services/kicad-dev-docs/-/blob/master/content/apis-and-binding/ipc-api/_index.en.adoc)
- Limitations, verbatim: "The IPC API in KiCad 9 and 10 only supports communication with a running instance of the KiCad GUI. Support for running in headless mode through `kicad-cli` was added for KiCad 11. There are no plans to support a standalone library for loading and manipulating KiCad files separate from the client-server (IPC) model." Also, "KiCad 9 and 10 [have] no support for plotting or exporting files … added for KiCad 11", and "KiCad 9 and 10 only support IPC API plugins in the PCB Editor. KiCad 11 adds support for plugins in the Schematic Editor." — [dev-docs: For Add-on Developers (source)](https://gitlab.com/kicad/services/kicad-dev-docs/-/blob/master/content/apis-and-binding/ipc-api/for-addon-developers/_index.en.adoc)
- Plugin model: IPC plugins live in `${KICAD_DOCUMENTS_HOME}/<version>/plugins` with a `plugin.json` that follows KiCad's schema. They are either Python plugins, which KiCad runs in a per-plugin venv it creates automatically, or "executable" plugins (any compiled binary). Clients find the socket through the `KICAD_API_SOCKET` and `KICAD_API_TOKEN` environment variables. The default socket is `api.sock` in the temp directory, with the PID appended when several instances run. `EnableAPILogging=1` in `kicad_advanced` logs every protobuf request — [same](https://gitlab.com/kicad/services/kicad-dev-docs/-/blob/master/content/apis-and-binding/ipc-api/for-addon-developers/_index.en.adoc)
- Users must enable the API server under Preferences > Plugins — [kicad-python README](https://gitlab.com/kicad/code/kicad-python)
- Secondhand gotcha from a third-party MCP project: KiCad exposes only one API socket, owned by whichever instance bound it. Board commands reportedly failed while the project manager held the socket and worked when pcbnew held it — [glama.ai listing, lmaag182/kicad_mcp_server_ipc](https://glama.ai/mcp/servers/lmaag182/kicad_mcp_server_ipc) (not verified against the KiCad docs)

**Command coverage (from the `.proto` files)**
- Generic editor commands in KiCad 10.0: `BeginCommit`/`EndCommit` (staged, undoable changes), `CreateItems`, `GetItems`, `GetItemsById`, `UpdateItems`, `DeleteItems`, `GetBoundingBox`, `GetSelection`/`AddToSelection`/`RemoveFromSelection`/`ClearSelection`, `HitTest`, `SaveDocument`, `SaveDocumentToString`, `SaveSelectionToString`, `ParseAndCreateItemsFromString`, `RevertDocument`, `RefreshEditor`, title-block get/set, and `RunAction` — [editor_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto)
- `RunAction` takes a tool-action name string. The proto comment warns: "Command names may change as code is refactored, and commands may disappear. This API method is provided for low-level prototyping purposes only." — [same](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto)
- Board commands in KiCad 10.0: stackup get/update, enabled layers, embedded files, graphics defaults, board origin, layer name lookups, `GetNets`, `GetItemsByNet`, `GetItemsByNetClass`, `GetConnectedItems`, `GetNetClassForNets`, `RefillZones`, `GetPadShapeAsPolygon`, `CheckPadstackPresenceOnLayers`, `InjectDrcError`, visible/active layers, appearance settings, `FlipItems`, `InteractiveMoveItems` — [board_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/board/board_commands.proto)
- Board commands added on `master` (KiCad 11 development): `GetBoardDesignRules`/`SetBoardDesignRules`, `GetCustomDesignRules`/`SetCustomDesignRules`, `ImportNetlist`, **`ImportSpecctraSession`**, `PlaceFootprintFromLibrary`, plot settings, and `GetBoardBoundingBox` — [board_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto)
- New on `master`: `board_jobs.proto` with export jobs for 3D, render, SVG, DXF, PDF, PS, Gerbers, drill, position, GenCAD, **`RunBoardJobExportSpecctraDsn`**, IPC-2581, IPC-D-356, ODB++, stats, PNG and IDF — [board_jobs.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto). Also new is `schematic_commands.proto` with `GetSchematicHierarchy`, `GetSchematicNetlist` and `PlaceSymbolFromLibrary` — [schematic_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/schematic/schematic_commands.proto)
- The board proto has no "route net", "autoroute" or "autoplace" command, either on 10.0 or on master — [10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/board/board_commands.proto), [master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto)

**kicad-python (`kipy`)**
- This is the official binding: "The SWIG bindings still exist in KiCad 9 and 10, but are removed in KiCad 11." It depends on `protobuf` and `pynng`. "In KiCad 11 or newer, `kicad-cli` can be used to start an API server … The `KiCad` class can be used to start up a `kicad-cli api-server` session automatically." — [kicad-python README](https://gitlab.com/kicad/code/kicad-python)
- License is MIT. The `main` branch is `0.9.0.dev0`, and the package is classed "Development Status :: 5 - Production/Stable" — [pyproject.toml](https://gitlab.com/kicad/code/kicad-python/-/blob/main/pyproject.toml)
- PyPI release history: 0.1.0 (2024-12-21), 0.2.0 (2025-02-19), 0.3.0 (2025-03-29), 0.4.0 (2025-07-08), 0.5.0 (2025-10-13), 0.6.0 (2026-03-15), 0.7.0/0.7.1 (2026-04-17/18), 0.8.0 (2026-08-30) — [PyPI kicad-python](https://pypi.org/project/kicad-python/); [GitLab tags](https://gitlab.com/kicad/code/kicad-python/-/tags)
- `Board` methods on `main` include `get_footprints`, `get_tracks`, `get_vias`, `get_zones`, `get_pads`, `get_nets`, `get_items_by_net`, `get_items_by_netclass`, `get_connected_items`, `get_netclass_for_nets`, `refill_zones`, `interactive_move`, `flip_items`, `hit_test`, `get_stackup`, `get_pad_shapes_as_polygons`, `get_design_rules`/`set_design_rules`, `get_custom_design_rules`/`set_custom_design_rules`, `place_footprint_from_library`, `import_netlist`, and a family of `export_*` methods (gerbers, drill, ODB, IPC-2581, PDF, SVG, STEP render and so on). The last group maps to KiCad-11-only protos — [kipy/board.py](https://gitlab.com/kicad/code/kicad-python/-/blob/main/kipy/board.py)
- The most recent `main` commit (2026-09-23) is "Add get_net_class_assignments and set_net_class_assignments" — [kicad-python commits](https://gitlab.com/kicad/code/kicad-python/-/commits/main)
- Examples in the repo: `move_footprints.py`, `create_zone.py`, `round_tracks`, `design_rules.py`, `check_for_testpoints.py`, `headless.py`, `jobs.py`, `layer_indicator` — [examples/](https://gitlab.com/kicad/code/kicad-python/-/tree/main/examples)

**Legacy SWIG `pcbnew` bindings**
- Verbatim: "The SWIG-based Python bindings in KiCad are deprecated as of KiCad 9.0 and will be removed in a future version … The current plan is to remove the SWIG bindings in KiCad 11.0." The docs also call SWIG "a raw binding layer over KiCad rather than a true API" that is "unstable and will generally change between KiCad major versions." SWIG can be used stand-alone, with no GUI running, through load/save of board files — [dev-docs: PCB Python Bindings (source)](https://gitlab.com/kicad/services/kicad-dev-docs/-/blob/master/content/apis-and-binding/pcbnew/_index.en.adoc)

**kicad-cli**
- KiCad 10.0 `kicad-cli` subcommands (from source file names): `pcb drc`, `pcb export` {gerber(s), drill, pos, ipc2581, ipcd356, odb, 3d, pdf, svg, dxf, ps, gencad, hpgl, stats}, `pcb render`, `pcb import`, `pcb upgrade`, `sch erc`, `sch export` {bom, netlist, plot, pythonbom}, `sch upgrade`, `sym`/`fp` upgrade and export-svg, `jobset run`, `version` — [kicad/cli @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/kicad/cli)
- `master` (KiCad 11 development) adds `api_server`, **`pcb_export_specctra`**, `pcb_diff`, `sch_diff`, `fp_diff`, `gerber_diff`/`gerber_info`/`gerber_convert_png`, `pcb_export_idf`, `pcb_export_png`, `pcb_export_stackup`, `pcb/sch/project_downgrade`, `git_mergedriver` and `mergetool` — [kicad/cli @master](https://gitlab.com/kicad/code/kicad/-/tree/master/kicad/cli)
- Jobsets, added in KiCad 9, are "predefined sets of 'jobs'—for example, plotting, exporting, and running DRC" that "can be run from the command line or from the KiCad GUI" — [KiCad 9.0.0 release notes (source)](https://gitlab.com/kicad/services/kicad-website/-/blob/master/content/blog/2025/release-9.0.0.adoc)

**File formats**
- The S-expression formats are documented for PCB, footprint, schematic, symbol library and worksheet — [dev-docs file-formats tree](https://gitlab.com/kicad/services/kicad-dev-docs/-/tree/master/content/file-formats)

**Built-in automation-relevant tools (from source and release notes)**
- The interactive router has an action `pcbnew.InteractiveRouter.Autoroute`, labelled "Attempt Finish Selected (Autoroute)": "Sequentially attempt to automatically route all selected pads." It is present in 10.0 and already existed in the 8.0 and 9.0 sources — [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp)
- A legacy autoplacer still ships: actions `pcbnew.Autoplacer.autoplaceSelected` ("Place Selected Footprints") and `pcbnew.Autoplacer.autoplaceOffboard`. Both are implemented in `pcbnew/autorouter/ar_autoplacer.cpp` (copyright notices from 2011–2012, Charras/Hollenbeck) next to `spread_footprints.cpp`. It needs an Edge.Cuts outline and skips locked footprints — [pcbnew/autorouter @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/autorouter); [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp)
- Specctra round-trip GUI actions: `pcbnew.EditorControl.exportSpecctraDSN` and `importSpecctraSession` — [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp)
- Multichannel tool: `pcbnew.Multichannel.generatePlacementRuleAreas` ("Creates best-fit placement rule areas") and `pcbnew.Multichannel.repeatLayout` ("Clones placement & routing across multiple identical channels") — [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp). Tomasz Wlostowski added multichannel in KiCad 9 to "repeat PCB layout elements from one channel to create identical copies" — [KiCad 9 notes](https://gitlab.com/kicad/services/kicad-website/-/blob/master/content/blog/2025/release-9.0.0.adoc)
- Other KiCad 9 additions: component classes, set from schematic rule-area directive labels, with new DRC expressions `A.ComponentClass`, `A.hasComponentClass('X')` and `A.memberOfFootprint('${Class:X}')`; net class rule areas; schematic design blocks; a zone manager; multi-track drag in the push-and-shove router; and the IPC API itself — [KiCad 9 notes](https://gitlab.com/kicad/services/kicad-website/-/blob/master/content/blog/2025/release-9.0.0.adoc)
- KiCad 10 PCB additions: a time-domain tuning overhaul ("more consistent between the router and DRC", time-domain constraints, per-layer "Tuning Profiles"); PCB Design Blocks (libraries of board layouts); inner-layer objects in footprints; unconstrained pin/gate swap with back-annotation; a graphical DRC rule editor "fully compatible with the existing Custom Rules language"; suggested-fix actions for DRC errors; and Allegro, PADS and gEDA importers — [KiCad 10.0.0 release notes (source)](https://gitlab.com/kicad/services/kicad-website/-/blob/master/content/blog/2026/release-10.0.0.adoc) / [kicad.org](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- KiCad 10.0.0 was released on 2026-03-20 with 7,609 unique commits — [release notes](https://gitlab.com/kicad/services/kicad-website/-/blob/master/content/blog/2026/release-10.0.0.adoc). 10.0.7 was released on 2026-10-07 — [10.0.7 notes](https://gitlab.com/kicad/services/kicad-website/-/blob/master/content/blog/2026/release-10.0.7.adoc). Press summary: [AlternativeTo](https://alternativeto.net/news/2026/3/kicad-10-released-with-track-tuning-revamp-windows-dark-mode-design-variants-and-more)
- KiCad's license: "The majority of KiCad's source code is developed and distributed under the terms of the GPLv3 or later" — [LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README)

### Inferences
- On KiCad 10 the IPC API is a good fit for mutating a live board (placing footprints, creating tracks and vias, refilling zones) with undo-safe commits. It is not a computation engine. Routing and placement intelligence has to live outside KiCad, or be triggered through `RunAction` strings, which can break between versions.
- Headless CI on KiCad 10 has three options: (a) SWIG `pcbnew` (deprecated, gone in 11); (b) direct S-expression editing plus `kicad-cli pcb drc`; (c) the GUI under a virtual display (e.g., Xvfb) with IPC. Option (c) is my inference and I did not find it documented. KiCad 11's `kicad-cli api-server` fixes this properly, so the project should design behind a backend abstraction.
- In KiCad 10, `kicad-cli` has no Specctra DSN export. DSN export there means the GUI action (or `RunAction`) or SWIG. In KiCad 11, DSN export and SES import are both available over IPC and the CLI, so the Freerouting-style loop becomes fully scriptable.
- No KiCad 11 release announcement appears in the 2026 blog source (the latest posts are 10.0.x). Given the annual cadence (9.0 in early 2025, 10.0 in March 2026), KiCad 11 most likely ships around Q1 2027. That timing is my inference.
- Built-in levers an LLM agent can use without new algorithms: component classes and custom DRC rules (constraints), rule areas plus `repeatLayout` (multichannel reuse), PCB Design Blocks (layout reuse), "Attempt Finish Selected", and time-domain tuning profiles.
- The IPC API exposes no router, but KiCad's push-and-shove (PNS) router can still be driven headlessly. LG AI Research's **PCBWorld-Engine** (GPLv3, derived from KiCad 9.0.8) exposes PNS through a pybind11 binding served over a unix socket, with 58 step-level Python APIs (Section 4). Horizon EDA embeds the same router (Section 4). That gives a third option beside `RunAction` and external routers: link PNS directly, which is license-compatible with a GPL-3.0 project. [P] — [PCBWorld-Engine](https://github.com/LGAI-Research/PCBWorld-Engine); [PCBWorld paper](https://arxiv.org/html/2607.05915)

### Gaps
- I could not read the rendered kicad-python API docs (docs.kicad.org blocked), so I could not confirm which kipy version first exposes each method, or exactly which `Board` methods work against 10.0.x versus only against 11 nightlies. The proto diff above is the best proxy. (A separate agent is re-verifying KiCad API facts in pass 2.)
- I could not confirm whether the KiCad 10 interactive router added new automation features beyond tuning (e.g., multi-track routing), because the forum "post-v9 new features" thread was unreachable.
- Exact KiCad 11 release timing and the final IPC feature list are unknown.

## 2. KiCad MCP servers, LLM integrations, and KiCad automation plugins/libraries

### Takeaway
The KiCad-MCP and LLM-tool ecosystem is large, young and long-tailed. GitHub search for "kicad mcp" returns 233 repositories. A curated "KiCad AI" list (RepoRecon) holds 275 repos, of which only 11 have 50 or more stars. Most servers wrap file editing, `kicad-cli` (DRC/ERC/export) and, increasingly, the IPC API. Almost none contain real placement or routing intelligence.

The decisive pass-2 finding comes from an independent tester, the SKiDL author: "I tested seven tools that actually created a routed PCB and they all used Freerouting."

The leaders by stars:
- mixelpixx/KiCAD-MCP-Server (MIT, about 2.5–2.9k)
- kicad-happy (MIT skills, about 1.4k)
- Konnect (AGPL, Rust, KiCad 10 IPC, about 1.3k)
- Backplane (MIT, a KiCad fork with extra LLM instrumentation, about 670)
- copperhead (Apache-2.0, which says it is "Not an autorouter", about 610)

KiCadRoutingTools (MIT) and rjwalters/kicad-tools (MIT) are the exceptions that ship their own routers, and kicad-tools also ships placement optimizers.

The official KiCad Plugin and Content Manager (PCM) has **no AI/LLM plugin at all**. Its routing entries are Freerouting, KiCad Routing Tools, OrthoRoute and a fanout tool. Its placement entries are arrange/replicate/spreadsheet tools, with no autoplacer.

### Cited Findings
**MCP servers (stars / last push as of 2026-10-20)**
- GitHub repository search "kicad mcp": 233 results — [GitHub search](https://github.com/search?q=kicad+mcp&type=repositories)
- **mixelpixx/KiCAD-MCP-Server**: 2,881 stars, pushed 2026-10-01, MIT. KiCad 9.0+. Covers "Project setup, schematic editing, component placement, routing, DRC/ERC, export", JLCPCB parts catalog, and "Freerouting integration — automatic PCB routing via Java/Docker". No placement or routing algorithms are described. The README promotes the successor Konnect — [GitHub](https://github.com/mixelpixx/KiCAD-MCP-Server). A third-party mirror of its docs shows an `IPC_BACKEND_STATUS.md` and an `ipc_backend.py`, meaning it has an IPC backend alongside the older ones — [glama mirror](https://glama.ai/mcp/servers/@mixelpixx/KiCAD-MCP-Server/blob/d2723bc29207c942bc93083131e2ac2a8d1a82d5/docs/IPC_BACKEND_STATUS.md)
- **mixelpixx/Konnect**: 1,339 stars, created 2026-07-05, 241 open issues, **AGPL-3.0** (commercial licenses available). It is "a single Rust binary" native KiCad 10 plugin. PCB edits go through the IPC API ("protobuf over NNG", "real-time and undo-aware"), schematic edits are direct `.kicad_sch` S-expression writes, and exports use `kicad-cli`. It has "228 tools across 21 on-demand toolsets" (the About text says 217). Routing is a Rust Specctra DSN exporter plus local Freerouting (Java child process) plus strict SES import. There is no built-in placer or router. It is labelled BETA; Linux "hasn't had per-platform QA yet" — [GitHub](https://github.com/mixelpixx/Konnect)
- **lamaalrajih/kicad-mcp**: 527 stars, MIT, last push 2025-10-17 (stale for about a year). Mostly read-only: project listing, netlist and BOM extraction, DRC via `kicad-cli`, rendering, and recognition of circuit patterns such as buck/boost/LDO — [GitHub](https://github.com/lamaalrajih/kicad-mcp)
- **salitronic/eda-agent**: 262 stars, Apache-2.0, pushed 2026-10-20. Primarily Altium (a DelphiScript polling loop); KiCad goes through the IPC API ("KiCad 9+ with the IPC API server enabled"). It auto-places schematics only (Sugiyama/force-directed baseline, VF2 subgraph-isomorphism "motif composer", overlap removal). It has no PCB autorouter. A "minimal" mode exposes only `tool_catalog` and `tool_invoke` to clients that cap tool counts. It is labelled "Experimental" — [GitHub](https://github.com/salitronic/eda-agent)
- **Seeed-Studio/kicad-mcp-server**: 163 stars. The README says MIT, but GitHub's search API reports no license. It covers analysis, pin-level net tracing and ERC/DRC. PCB analysis uses SWIG `pcbnew` with a text-parsing fallback; schematic editing is "experimental" raw S-expression manipulation ("KiCad must be closed and reopened to see file changes"). No placement or routing — [GitHub](https://github.com/Seeed-Studio/kicad-mcp-server)
- **oaslananka/kicad-mcp-pro**: 142 stars, MIT, v4.3.0. Read-only by default, with opt-in write and release profiles; ERC/DRC/DFM/BOM; a KiCad 10 IPC companion plugin (read-only); SI/PI/EMC/thermal "closed-form estimates (typically ~5–10% accuracy)"; it says it is "not an automated sign-off authority" — [GitHub](https://github.com/oaslananka/kicad-mcp-pro)
- Others found, all small: Shaurya-Sethi/circuitron (128 stars, MIT, "Agentic PCB Design Accelerator", last push 2026-06) — [GitHub](https://github.com/Shaurya-Sethi/circuitron); tangency-labs/pcbcraft (66 stars, **GPL-3.0**, "MCP-first Rust EDA with … KiCad compatibility") — [GitHub](https://github.com/tangency-labs/pcbcraft); blwfish/kicad-mcp ("71 tools", MIT) — [GitHub](https://github.com/blwfish/kicad-mcp); Netlist-Studio/kicad-mcp ("controlling KiCad 9 over its IPC API", MIT, last push 2026-02) — [GitHub](https://github.com/Netlist-Studio/kicad-mcp); Finerestaurant/kicad-mcp-python (IPC-API based, last push 2025-07, stale) — [GitHub](https://github.com/Finerestaurant/kicad-mcp-python); ProductOfAmerica/mcp-server-kicad ("Maintenance mode", **GPL-3.0**, "100+ … tools") — [GitHub](https://github.com/ProductOfAmerica/mcp-server-kicad); biosshot/kicad-copilot ("schematic generation, PCB placement, local routing", 18 stars) — [GitHub](https://github.com/biosshot/kicad-copilot); BeckhamLabsLLC/kicad-jlcpcb (a Claude Code plugin producing a "wired .kicad_pcb ready for EasyEDA auto-routing") — [GitHub](https://github.com/BeckhamLabsLLC/kicad-jlcpcb); circuit-synth/kicad-sch-api (schematic S-expression API, MIT, last push 2025-12) — [GitHub](https://github.com/circuit-synth/kicad-sch-api); HeyPCB/heypcb-mcp — [GitHub](https://github.com/HeyPCB/heypcb-mcp); IntelligentElectron/universal-netlist (reads Cadence/Altium/KiCad netlists for agents, Apache-2.0) — [GitHub](https://github.com/IntelligentElectron/universal-netlist)
- **Freerouting has its own MCP server**: `npx -y @freerouting/freerouting-mcp-server` uses the public API, and an offline local executable is also available. Clients named are Cursor, Cline and Claude Desktop — [Freerouting README](https://github.com/freerouting/freerouting). npm package v2.5.0, published 2026-10-05, GPL-3.0-only — [npm](https://www.npmjs.com/package/@freerouting/freerouting-mcp-server). v2.5.0 adds an MCP `autoroute_board` tool and `compact=true` DRC summaries "for LLM use" — [Freerouting releases](https://github.com/freerouting/freerouting/releases)
- **drandyhaas/KiCadRoutingTools**: 549 stars, MIT, created 2025-12-13, about 5,856 commits, v0.15.x. A "Rust-accelerated A* autorouter for KiCad PCB files" with diff pairs, length/time matching, BGA/QFN fanout, plane pours and repair, bus routing, "placement optimization for routability", and DRC/connectivity checkers. It ships Claude Code skills (`/plan-pcb-routing`, `/analyze-power-nets`, `/pcb-free-agent`) and an AI tab backed by Claude Code or opencode, "tuned on Claude models". It works on `.kicad_pcb` files, not IPC, and is listed in KiCad's PCM — [GitHub](https://github.com/drandyhaas/KiCadRoutingTools)
- **DeepPCB KiCad plugin** (instadeepai/deeppcb-kicad-plugin): Apache-2.0, routing only, beta. The README says "KiCad 6.0 or later" and it runs from Tools > External Plugins (SWIG-style); it is a cloud service with an API key and credits — [GitHub](https://github.com/instadeepai/deeppcb-kicad-plugin). A vendor blog snippet says it needs KiCad 10.0+, which conflicts with the README, and that placement "from schematics" is coming — [DeepPCB blog (search snippet)](https://deeppcb.ai/deeppcb-kicad-plugin-ai-pcb-routing/). PR #6 (v1.2.0) adds "Cooper", a dockable chat assistant that can act on the open board — [PR #6](https://github.com/instadeepai/deeppcb-kicad-plugin/pull/6)

**Non-AI KiCad libraries and plugins**
- **InteractiveHtmlBom**: 4,610 stars — [GitHub](https://github.com/openscopeproject/InteractiveHtmlBom). **kicad-jlcpcb-tools**: 2,113 stars (BOM/CPL and LCSC assignment) — [GitHub](https://github.com/Bouni/kicad-jlcpcb-tools). **KiKit** ("Automation tools for KiCAD", panelization): 2,046 stars, PyPI 1.8.1 (2026-08-05) — [GitHub](https://github.com/yaqwsx/KiKit), [PyPI](https://pypi.org/project/kikit/)
- **kicad-skip** (S-expression schematic/layout manipulation): 230 stars, repo active, but the last PyPI release is 0.2.5 from 2024-02-16 — [GitHub](https://github.com/psychogenic/kicad-skip), [PyPI](https://pypi.org/project/kicad-skip/). **kiutils** (dataclass parser, "KiCad 6.0 and up"): 130 stars, last PyPI release 1.4.8 on 2024-02-02 (stale for KiCad 9/10 format changes) — [GitHub](https://github.com/mvnmgrx/kiutils), [PyPI](https://pypi.org/project/kiutils/)
- **SKiDL** (Python netlist and schematic description): 1,697 stars, PyPI 3.0.0 on 2026-10-16 — [GitHub](https://github.com/devbisme/skidl), [PyPI](https://pypi.org/project/skidl/)
- **ReplicateLayout** (Mitja Nemec): "The functionality of this plugin is now available in KiCad natively! … this plugin is no longer updated." **GPL-2.0** — [GitHub](https://github.com/MitjaNemec/ReplicateLayout). **SaveRestoreLayout**: 26 stars, default branch v9 — [GitHub](https://github.com/MitjaNemec/SaveRestoreLayout). **PlaceFootprints** (place by sheet, reference or other criteria): 52 stars, default branch v10 — [GitHub](https://github.com/MitjaNemec/PlaceFootprints)
- Placement-related plugins: **kicad-kbplacer** (keyboard key placement and routing, 543 stars) — [GitHub](https://github.com/adamws/kicad-kbplacer); **CadMust-Neo** ("KiCad placement optimizer plugin using simulated annealing", 29 stars, created 2026-03) — [GitHub](https://github.com/remiblokker/CadMust-Neo); **kicad-auto-silkscreen** (refdes placement, 37 stars) — [GitHub](https://github.com/CGrassin/kicad-auto-silkscreen); **VelaTrace** (KiCad 10 lint plus its own router, 3 stars) — [GitHub](https://github.com/F-Blaze/VelaTrace)
- assalas/pcb-designer-ai-agent (137 stars) claims ML placement, routing and SI across KiCad, Altium and Eagle — [GitHub](https://github.com/assalas/pcb-designer-ai-agent). Its description is a buzzword list (GNNs, RL, TensorFlow, PyTorch, thermal…) and I did not verify that it works. Treat with suspicion.

**Official KiCad Plugin and Content Manager (PCM) catalog: index snapshot 2026-10-19 [P]**
- The official repository index (`packages-v1.json`, updated 2026-10-19 11:02 UTC) lists **132 packages: 97 plugins, 18 colour themes, 17 libraries**. The metadata repo is `gitlab.com/kicad/addons/metadata` — [repository.json](https://repository.kicad.org/repository.json); [packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json); [metadata repo](https://gitlab.com/kicad/addons/metadata)
- **Routing plugins:**
  - Freerouting `app.freerouting.kicad-plugin` 2.4.1 (KiCad ≥6.0, SWIG runtime, GPL-3.0, "needs Java JRE 25"). The PCM listing lags upstream v2.5.0.
  - KiCad Routing Tools 0.22.1 (KiCad ≥9.0, SWIG, MIT, "Fast Rust-accelerated A* autorouter"). This is newer than the v0.15.x in its README snapshot.
  - OrthoRoute 1.0.0 (KiCad ≥10.0, **IPC runtime**, MIT).
  - Fanout Tool 1.0.0 (KiCad ≥10.0, IPC, MIT): QFN/QFP/BGA escape routing with "3-segment routing algorithms".
  - A delisted "Length Matching" plugin.
  — [packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json)
- **Placement and layout-reuse plugins:**
  - Place Footprints 5.0.0 (KiCad 10.0–10.1, GPL-2.0; "Arrange footprints on a line, circle or grid")
  - Replicate Layout 5.0.1 (KiCad 10.0–10.1, GPL-2.0). It still has a KiCad-10 build despite its README saying it is no longer updated.
  - Save/Restore Layout 4.0.0 (KiCad 9.x)
  - SubLayout 0.2 (BSD-3; "replicate, load, and save layouts of hierarchical sheets")
  - HierarchicalPCB 1.1.0 (MIT; "Enforce sub-PCB layouts for sub-schematics")
  - Layout Clone 0.3.3 (KiCad 10, IPC, MIT)
  - Parts Placer 0.1.14 (LGPL-2.1; "Declaratively place components using a spreadsheet")
  - Place By Sch 2.2.0 (GPL-3.0; places footprints from schematic positions)
  - KLEPlacement, Keyboard footprints placer (kbplacer), PosOrient, Snap To Grid
  - **None is an optimizing autoplacer.**
  — [packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json)
- **No AI or LLM plugin is listed.** A regex scan of every package name and description for AI/LLM/GPT/Claude/MCP/assistant/copilot/chat found nothing. **The DeepPCB plugin is not in the official index**, which matches its vendor saying the PCM listing was "being finalized" — [packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json)
- 18 plugins already use the new **IPC runtime**. Examples: OrthoRoute, Fanout Tool, Layout Clone, Via Stitching, Via Patterns, Silk Reference Tools, a Net Class Clearance Matrix, Z0 Field Solver (writes net classes and design rules from a 2D field solve) and Z0 Wavelab — [packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json)

**Broader sweep of KiCad AI/LLM tools beyond the top MCP servers (pass 2)**
- **Scale:**
  - GitHub search `kicad llm OR kicad claude OR kicad gpt OR kicad agent` returns 194 repos [P] — [GitHub search](https://github.com/search?q=kicad+llm+OR+kicad+claude+OR+kicad+gpt+OR+kicad+agent&type=repositories)
  - devbisme's RepoRecon "KiCad AI" table (built by embedding-matching 55k KiCad-related repo descriptions) holds **275 entries**. Only 11 have 50 or more stars and 13 have 10 or more [P] — [RepoRecon kicad_ai](https://devbisme.github.io/RepoRecon/?topic=kicad_ai&filter=&sort=stars:desc); [data](https://devbisme.github.io/RepoRecon/kicad_ai.json); [forum post](https://forum.kicad.info/t/kicad-ai-related-projects/71760)
- **aklofas/kicad-happy** (1,464★, MIT, created 2026-03-09). "AI coding agent skills for KiCad … Analyze schematics, review PCB layouts, EMC pre-compliance, SPICE simulation … prep boards for fabrication". It works with Claude Code and Codex. This is the "kicad-happy" named in the brief; it exists and is under separate verification [P] — [GitHub](https://github.com/aklofas/kicad-happy)
- **i2cjak/Backplane** (673★, MIT, created 2026-09-06): "Agentic hardware development with lawful, deterministic KiCad/STEP viewers". It ships a **KiCad fork** that "adds additional instrumentation for LLM control (IPC schematic API, for instance)" and is agent-agnostic (Claude, Codex, Grok, OpenCode). No placement or routing automation is described [P] — [GitHub](https://github.com/i2cjak/Backplane)
- **copperheadhq/copperhead** (614★, Apache-2.0, created 2026-07-18; "Cursor for circuit boards"):
  - It edits `.kicad_sch`/`.kicad_pcb` S-expressions directly and runs `kicad-cli` ERC/DRC in a loop. Each mutation is git-snapshotted and rolled back if verification fails.
  - Verbatim: "**Not an autorouter.** Routing stays human or delegated; copperhead produces the DRC-clean draft that layout tools optimize from."
  - Self-assessed maturity: the agent loop has "not been observed passing end to end". It has an experimental 5-tool MCP server.
  - Show HN got 250 points and 115 comments [P] — [GitHub](https://github.com/copperheadhq/copperhead); [HN](https://news.ycombinator.com/item?id=49610059)
- **paul356/KiCad-AI-Assistant** (119★, MIT, KiCad ≥10, PyPI `kcaa`):
  - A wxPython chat panel inside KiCad that starts an embedded MCP server with **111 tools in 15 categories**, including PCB placement (align, distribute, move, rotate, group), zones and DRC, plus FreeRouting integration (`autorouter.py`) and some IPC calls (e.g., "Update PCB from Schematic").
  - Providers: OpenAI, Anthropic, Ollama, Bedrock.
  - Forum users report it works with GPT-5.4 or DeepSeek but local Ollama models fail to tool-call (one fix was raising the Ollama context window to 128k) [P] — [GitHub](https://github.com/paul356/KiCad-AI-Assistant); [KiCad forum thread](https://forum.kicad.info/t/kicad-ai-assistant-a-llm-powered-kicad-plugin/69770)
- **rjwalters/kicad-tools** (70★, MIT, about 6.9k commits): a file-based Python toolkit "for AI agents".
  - Placement: force-directed and genetic-algorithm optimizers plus a hybrid, and a CMA-ES/Bayesian `kct optimize-placement`.
  - Routing: an "A* PCB autorouter with trace optimization" (optional C++ backend, "10-100x A* speedup") and a multi-strategy `kct route-auto`.
  - It self-reports that KiCadRoutingTools is faster and completes more nets on sparse and medium boards, while kicad-tools does better on some dense boards [P] — [GitHub](https://github.com/rjwalters/kicad-tools)
- **HeyPCB/heypcb-mcp** (MIT client, created 2026-10-12): a front end to a **paid cloud service** (`api.heypcb.ai/mcp`). "Let HeyPCB design the board" tools (`build_board`) cover parts, placement, routing and DRC server-side. Local tools wrap `kicad-cli`. Bound KiCad folders are uploaded on change [P] — [GitHub](https://github.com/HeyPCB/heypcb-mcp)
- **Others with traction:**
  - zxkmm/kicad-harness (33★; "eyes and hands on a KiCad project")
  - Zane456/PCB-Agent-Teams (76★; 9-skill multi-agent pipeline; licence marked "Noncommercial", so **not reusable**)
  - nevenfo/kicad-agentic-mcp (Rust, KiCad 10; "LLM-based planning … with deterministic execution, state tracking, evidence, rollback")
  - JITx-Inc/jitx-skills (Section 3)
  - devbisme/boardforge ("Claude Code plugin distilled from other KiCad-related AI tools")
  - ChengminLi/AI-PCB-layout (power-electronics skill "with a human review gate after every step")
  — [P] [kicad-harness](https://github.com/zxkmm/kicad-harness); [PCB-Agent-Teams](https://github.com/Zane456/PCB-Agent-Teams); [kicad-agentic-mcp](https://github.com/nevenfo/kicad-agentic-mcp); [boardforge](https://github.com/devbisme/boardforge); [AI-PCB-layout](https://github.com/ChengminLi/AI-PCB-layout)
- **Adom/Hydrogen "KiCad Bridge"** (Windows): a native Rust bridge that lets an AI drive the user's own KiCad GUI (open editors, place parts, DRC/ERC, export, screenshot windows back to the AI). In the KiCad forum the vendor claims NSF funding ("$10M from National Science Foundation"). **Unverified vendor claim** [P for the page, claim unverified] — [Adom wiki](https://wiki.adom.inc/adom/kicad-bridge); [forum](https://forum.kicad.info/t/testing-kicad-ai-tools/71769)

**Independent hands-on tests of KiCad AI tools [P]**
- Dave Vandenbout (devbisme, SKiDL author) runs `ai-circuit-design-tests`: each tool designs the same dual-channel 10 MS/s 12-bit USB 2.0 ADC board from a blank slate. His caveat: "None of these designs or findings has been validated yet" — [GitHub](https://github.com/devbisme/ai-circuit-design-tests)
- Reported results (API-equivalent cost of the design run):

  | Tool | Reported result | Cost |
  |---|---|---|
  | Konnect | "Routed 4-layer board, DRC clean" | $61.12 |
  | kicad-happy | 0 ERC/DRC errors | $29.37 |
  | mixelpixx kicad-mcp-server | 4 DRC errors (stock USB-C footprint) | $16.93 |
  | kicad-mcp-pro | 0 errors | $19.42 |
  | eda-agent | 0 errors | $18.47 |
  | KiCad-AI-Assistant | 0 errors | $19.38 |
  | kicad-harness | 0 errors | $10.87 |
  | boardforge | 0 errors | $23.89 |
  | **Null baseline** (Claude Code, no KiCad tools) | "Routed 4-layer board, 0 ERC/DRC errors; signals routed through the In1 GND plane" | $11.16 |

  — [GitHub](https://github.com/devbisme/ai-circuit-design-tests)
- His summary in the forum (2026-10-14): "**I tested seven tools that actually created a routed PCB and they all used Freerouting.** The AI might route a few nets using an A* algorithm, but that's about it." — [KiCad forum](https://forum.kicad.info/t/testing-kicad-ai-tools/71769)

### Inferences
- Most MCP servers repackage the same three primitives: file-level S-expression edits, `kicad-cli` runs, and (lately) IPC CRUD. The differentiator for a new project is not tool coverage, which already reaches 200–480 tools elsewhere. It is placement and routing quality, plus a tight verify loop of DRC, scoring and rendering feedback.
- Tool-count inflation is a known LLM usability problem. eda-agent's two-tool "catalog/invoke" mode and Konnect's "on-demand toolsets" are both workarounds. A smaller set of high-level, verifiable tools is likely better.
- KiCadRoutingTools is the closest existing analogue to "LLM agent + real routing engine for KiCad". Its MIT license makes it reusable in a GPL-3.0 project.
- kiutils and kicad-skip PyPI releases predate KiCad 9 and 10. File-level editing may need its own maintained S-expression layer, or a move to KiCad 11 headless IPC.
- **"AI KiCad tool" today in practice means LLM orchestration plus Freerouting for copper.** The devbisme tests show a no-tools Claude Code baseline producing a "DRC-clean" 4-layer board for $11, cheaper than most tool-augmented runs. Its flaw (signals routed through the GND plane layer) is exactly the kind DRC does not catch. So "0 DRC errors" is a weak quality metric. A differentiated project needs (a) its own placement intelligence, (b) routing quality beyond Freerouting defaults, and (c) layout-quality checks beyond DRC: plane integrity, return paths, decoupling distance.
- The PCM has no AI plugins, and plugins are moving to the IPC runtime (18 already). An IPC-runtime plugin that also exposes MCP would be a first in the official catalog.

### Gaps
- "Circuit-Tracer" and a KiCad plugin literally named "KiCad AI" were not found. Closest matches: KiCad-AI-Assistant (paul356), colaco1123/K-AI (2★) and jasiek/kicad-llm-plugin (9★) — [RepoRecon data](https://devbisme.github.io/RepoRecon/kicad_ai.json). kicad-happy exists (above).
- The devbisme results are unvalidated. Apart from the null baseline, the table does not say which router each tool used. The forum summary says all seven routed tools used Freerouting.
- I could not confirm whether DeepPCB's KiCad plugin uses SWIG or IPC. It is not in the official PCM index.

## 3. Commercial and open products for autorouting and AI placement/routing (Freerouting, Quilter, DeepPCB, Flux, JITX, tscircuit, atopile, incumbents)

### Takeaway
Three kinds of automated layout products exist today.

1. **Cloud AI layout services:**
   - Quilter: placement plus routing, physics-aware, KiCad/Altium/Cadence/Siemens files in and out, project-based pricing.
   - DeepPCB: RL routing plus placement, pay-per-hour, KiCad plugin.
   - Flux AI Auto-Layout: routing only, inside Flux.
   - Newer entrants: HeyPCB (MCP-first cloud service) and Diode Computers (AI-plus-engineer design service with an MIT KiCad-generating toolchain).
2. **Classic DSN/SES autorouters:**
   - Open side: led by Freerouting (GPL-3.0, very active in 2026).
   - Commercial: Cadence's Allegro PCB Router (the original Specctra, shape-based), Konekt Electra (shape-based, actively updated, v10.10 in July 2026, €145/month or €2,495 perpetual, lists KiCad), TopoR (topological; now a module of Eremex's Russian Delta Design suite, with the English product page gone) and a closed GPU/RL "PCB Auto Router" desktop tool.
   - Altium's Situs (topological) is built into Altium Designer. EasyEDA/JLCEDA ships a Freerouting-derived router (Standard) and, since EasyEDA Pro V3.2.148 (2026-06-01), a "brand new auto placement (dual engine)" and auto routing with equal-length diff pairs.
3. **Incumbent "AI" programmes:**
   - Cadence Allegro X AI and Zuken AIPR (2023 announcements).
   - Siemens: AI-assisted features in PADS Pro Essentials/Xpedition Standard (May 2025), and the agentic, MCP-based **Fuse EDA AI Agent** (March 2026), which "aids layout" in Xpedition but makes no autonomous-placement claim.

Front-end AI startups (CELUS, Circuit Mind, SnapMagic, Cadstrom) do schematic, BOM or verification work, **not layout**. Frontier labs entered in Sept 2026, when OpenAI demoed GPT-6 Astra doing KiCad layout. Community testers report the routing went through Freerouting [S]. The atopile-run EEBench deliberately excludes layout from v1.

Code-first tools (atopile, tscircuit, JITX, SKiDL, Diode's Zener) automate design capture. tscircuit (MIT autorouter plus a placement packer) and JITX (proprietary routing solvers in an AI-writes-Python loop) also automate geometry.

### Cited Findings
**Freerouting** (GPL-3.0, 2,123 stars, pushed 2026-10-20)
- "An advanced autorouter for all PCB programs that support the standard Specctra or Electra DSN interface"; it reads `.dsn` and writes `.ses`. Example CLI: `java -jar freerouting.jar -de MyBoard.dsn -do MyBoard.ses -inc GND,VCC`. Docker images are published for amd64, arm64 and arm/v7. REST API root is `https://api.freerouting.app/v1` (beta). Python client `freerouting-client`. Listed integrations: KiCad, Autodesk Fusion, Target3001!, EasyEDA, tscircuit, pcb-rnd — [README](https://github.com/freerouting/freerouting)
- KiCad plugin installs through the Plugin and Content Manager ("KiCad 6.0 or newer"), runs from Tools > External Plugins, and waits "until the Freerouting app exits and the plugin loads your routed design" — [docs/integrations.md](https://github.com/freerouting/freerouting/blob/master/docs/integrations.md)
- Releases (dates inferred from assets; npm corroborates 2.5.0 on 2026-10-05) — [GitHub releases](https://github.com/freerouting/freerouting/releases):
  - **v2.5.0 (≈2026-10-05)**: clean-board completion "rose from about 31% to 75% on the 1,157-board PCBench corpus"; a deterministic post-route optimizer; copper pour and power-plane awareness; GraalVM native CLI binaries for Linux, macOS and Windows; "direct Protocol Buffers IPC integration for KiCad 10+" with fallback to DSN/SES; `POST /v1/autoroute`; MCP `autoroute_board`; DRC `compact=true` for LLMs; router score `V2_CONTINUOUS` and optimizer score `V2_LOWER_BOUND`. Breaking change: `-hr` and the RANDOM/GREEDY/HYBRID optimizer strategies were removed.
  - **v2.4.1 (≈2026-09-03)**: the routing core is "completely decoupled from Swing/AWT"; CLI, REST and GUI share one pipeline; the PCBench suite was added to the repo; "the Specctra DSN/SES path is still the recommended production route" for KiCad.
  - **v2.3.0 (≈2026-08-07)**: `BatchFanout` SMD pre-pass; opt-in `strict_drc`; MCP server over JSON-RPC, SSE and WebSocket; A2A agent card at `/.well-known/agent.json`; `--router.copperToEdgeClearanceUm` works around missing board-edge clearance in KiCad exports.
  - **v2.2.3/2.2.4 (May 2026)**: fixed crashes on boards with more than two layers; auth on by default; stagnation detection; best-board restoration.
- Scoring: `V2_CONTINUOUS` starts at 1000 and subtracts penalties for unfinished connections and clearance violations. `V2_LOWER_BOUND` penalizes excess length (against a Manhattan MST), vias (against a per-net minimum) and bends (against a minimum) relative to placement-derived lower bounds — [docs/scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)

**fastroute** (GPL-3.0-or-later; 107 stars; created 2026-09-29)
- "A Rust port of Freerouting with bug fixes, length matching, controlled impedance and differential pairs". KiCad plugin over DSN that carries `.kicad_dru` rules. Self-reported total time over 20 boards: Freerouting 2102 s, fastroute 510 s, fastroute+PGO 420 s. Memory: Freerouting 1–2 GB versus fastroute 20–300 MB — [GitHub](https://github.com/parisxmas/fastroute)

**Quilter** (cloud; quilter.ai was blocked, so these come from snippets and press)
- Positioning from Quilter's own blog: upload an existing KiCad or Altium project, define the board outline, floorplan and constraints, and get multiple candidate layouts in hours. Results come back "in the same formats you submitted" for DRC and finishing in the user's own tool — [Quilter blog (snippet)](https://www.quilter.ai/blog/the-startups-choice-for-2026-quilter-vs-kicad-vs-altium-on-speed-cost-and-team-efficiency); [Quilter blog (snippet)](https://quilter.ai/blog/a-data-driven-look-at-pcb-layout-efficiency-in-2026-quilter-ai-vs-altium-vs-kicad)
- Series B of $25M (2025-10-07). Quilter says it is "not an autorouter" and that existing automation lacks physics understanding — [BusinessWire](https://www.businesswire.com/news/home/20251007165399/en/Quilter-Secures-%2425M-Series-B-to-Eliminate-Manual-PCB-Design-with-Physics-Driven-AI). A secondary source describes the approach as reinforcement learning, and the founder as ex-SpaceX Sergiy Nesterenko — [hardwarefyi](https://hardwarefyi.substack.com/p/pcb-layout-doesnt-need-to-be-painful). I found no technical paper.
- Project Speedrun (Dec 2025): a two-board NXP i.MX 8M Mini Linux computer with 843 components, 5,141 pins and 8 layers that booted Debian on first power-up. About 38.5 engineer-hours versus 428 hours quoted for manual layout, and "98%" of placement, routing and physics validation done autonomously. All figures are company claims. The raw pre-cleanup layout was published — [BusinessWire](https://www.businesswire.com/news/home/20251210722060/en/Quilter-Unveils-Worlds-First-Computer-Designed-by-AI); [Quilter design files](https://quilter.ai/project-speedrun/download); [TechRadar](https://www.techradar.com/pro/ai-designed-this-linux-computer-with-843-parts-and-dual-pcbs-in-just-a-week-and-it-even-booted-the-first-time); [VentureBeat](https://venturebeat.com/ai/quilters-ai-just-designed-an-843-part-linux-computer-that-booted-on-the); [All About Circuits](https://www.allaboutcircuits.com/news/for-the-first-time-ai-designs-computerin-less-than-a-week/)
- Pricing and limits from a third-party summary: a free tier for personal, academic or small teams (under 10 people and $50K revenue) where designs may be used for training; commercial work is per-project and priced by pins to route, with no public list price; best results at 100–1,000 components, 2,000–5,000 pins, and pin density under 20% — [Protoflow comparison](https://www.protoflow.ai/compare/best-ai-pcb-design-software-2026); [Quilter blog (snippet)](https://www.quilter.ai/blog/analyzing-the-best-free-pcb-tools-in-2026-quilter-vs-kicad-vs-circuitmaker); [Futurepedia](https://www.futurepedia.io/tool/quilter)

**DeepPCB (InstaDeep)**
- Pricing from the homepage snippet: 1 h $0.99, 4 h $3.49, 12 h $9.99, 24 h $18.99; "1 Free Board each day" up to 150 airwires and 12 h of processing — [deeppcb.ai (snippet)](https://deeppcb.ai)
- History: launched 2019 as a "no-human-in-the-loop cloud-native" router for KiCad boards — [Hackaday 2019](https://hackaday.com/2019/12/01/deeppcb-routes-your-kicad-pcbs/). Free beta in 2023 with a commercial version in the works — [eeNews Europe](https://www.eenewseurope.com/en/free-pcb-design-service-uses-ai-in-the-cloud). A placement product exists — [DeepPCB placement page (title)](https://deeppcb.ai/ai-powered-pcb-placement-by-deeppcb/)
- Self-reported: "27,721 Boards, 95.6% Hit 95%+ Completion" (page title) — [DeepPCB](https://deeppcb.ai/kicad-autorouter-alternative/). For the KiCad plugin, see Section 2.

**Flux.ai AI Auto-Layout** (flux.ai was blocked; from snippets)
- A one-click router that runs after the user places parts, fans out fine-pitch parts and routes critical nets. It does no placement. Jobs go through queue, working and converged states, and users can apply intermediate iterations. Updates added seven net-priority buckets and "relaxed clearance". Flux's docs say it is "not designed to fully autoroute every class of board without your input" — [Flux docs (snippet)](https://docs.flux.ai/tutorials/auto-layout); [Flux blog: introducing](https://www.flux.ai/p/blog/introducing-ai-auto-layout); [Winter update](https://www.flux.ai/p/blog/ai-auto-layout-winter-update); [Smarter](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter)
- A competitor's view: it works well for 2- and 4-layer boards of about 40–100 components and does not produce a physics scorecard — [Quilter comparison (snippet)](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)

**Incumbent EDA vendors**
- Cadence Allegro X AI (announced 2023-04-06): generative AI for "small to medium PCBs" that automates placement, metal pouring and critical-net routing, with integrated SI/PI, cloud-based, claiming a ">10X" turnaround reduction — [BusinessWire](https://www.businesswire.com/news/home/20230406005098/en/Cadence-Introduces-Allegro-X-AI-Accelerating-PCB-Design-with-More-Than-10X-Reduction-in-Turnaround-Time); [Electronic Design](https://www.electronicdesign.com/technologies/eda/article/21263574/electronic-design-system-level-pcb-design-tool-embraces-generative-ai)
- Zuken CR-8000 AIPR (Autonomous Intelligent Place and Route), announced 2023: a "Smart Autorouter" with ML "Brain" stages (Basic Brain from Zuken's library; Dynamic Brain learning from the user's past designs; Autonomous Brain). Basic Brain and Smart Autorouter were slated for Q1 2024 — [Zuken AI PCB design page](https://www.zuken.com/fr/product/cr-8000/ai-pcb-design/); [Digital Engineering 24/7](https://www.digitalengineering247.com/article/zuken-launches-ai-powered-pcb-routing-tool-as-first-step-in-long-term-ai-strategy/news); [PCD&F](https://pcdandf.com/pcdesign/index.php/editorial/menu-new-indust-prod/17566-zuken-rolls-out-ai-approach-for-cr-8000); [Silicon Saxony](https://silicon-saxony.de/en/zuken-ai-powered-place-and-route-technology-unveiled-for-cr-8000/)

**Code-first and agentic design tools**
- **atopile**: 4.0k stars, MIT. "A language, compiler, and toolchain for electronics" that updates `.kicad_pcb` on each build. Layout is still "place and route in KiCad" by hand; automation is parametric part picking. The repo carries agent tooling files (CLAUDE.md, AGENTS.md) — [GitHub](https://github.com/atopile/atopile)
- **tscircuit**: 2,857 stars, MIT. TypeScript/React circuits; placement is manual via `pcbX`/`pcbY` for now, with "flex"/"CSS Grid"-style autolayout under development. Uses Algora bounties — [GitHub](https://github.com/tscircuit/tscircuit). Its autorouter, `@tscircuit/capacity-autorouter`, is MIT; npm v0.0.995 was published 2026-10-20 — [npm](https://www.npmjs.com/package/@tscircuit/capacity-autorouter). It is "composed of hundreds of algorithms organized in a Pipeline", uses "successive approximation and hypergraphs instead of sequential routing" with a `CapacityMeshSolver`, and takes and returns SimpleRouteJson — [GitHub](https://github.com/tscircuit/tscircuit-autorouter)
- **JITX**: the 2026 tooling is Python (`py-jitx` 4.2.x, Python 3.12+). `JITx-Inc/jitx-skills` packages nine Claude Code and Codex skills (component modeler, circuit builder, substrate modeler, physical layout with "code-based routes", interconnect constraints, pin assignment and others). It mentions no autorouter and no KiCad export — [GitHub](https://github.com/JITx-Inc/jitx-skills)
- **SKiDL**: see Section 2 — [GitHub](https://github.com/devbisme/skidl)
- **JITX (2026 positioning)**:
  - "Python-based design for high frequency boards. AI writes the code. HFSS validates. Runs on your hardware."
  - JITX "supplies the design primitives, routing solvers, HFSS interface, schematic generation, pin assignment, fencing", while "your approved AI writes and revises Python". It "generates routing, fencing, pin assignments, and schematic output".
  - Example: optimizing a 56 GHz PCIe-gen7 BGA launch in "5 total HFSS simulations". Claimed customers: Honeywell Aerospace, Lockheed Martin, OpenAI.
  - Proprietary, on-prem. No KiCad export is mentioned.
  — [P] [jitx.com](https://www.jitx.com/)

**Classic commercial DSN/SES autorouters (pass 2)**
- **Specctra / Allegro PCB Router (Cadence):**
  - Written by Cooper & Chyan Technology in 1989 and acquired by Cadence in May 1997. Now "Allegro PCB Router"; Wikipedia lists the latest version as 17.4–22.1 (20 Oct 2022).
  - "Shape-based" routing in passes: preview, autoroute, post-processing. It uses rip-up-and-retry plus push-and-shove, takes strategies as Do-files, and returns SES or RTE files.
  - "The DSN/SES file formats are also supported by … KONEKT ELECTRA, Eremex TopoR, Alfons Wirtz's FreeRouting and RL-based DeepPCB". KiCad is in Wikipedia's list of DSN-supporting EDA tools.
  — [P] [Wikipedia: Specctra (wikitext)](https://en.wikipedia.org/w/index.php?title=Specctra&action=raw)
- **Konekt ELECTRA:**
  - "Shape-Based Autorouting software … In contrast with traditional gridded maze autorouters"; "multi-pass cost-based conflict reduction algorithm".
  - Reads SPECCTRA DSN and writes RTE or SES. It plugs into "Altium, Pulsonix, CADInt, TargetPCB, DipTrace, **KiCAD**, Proteus, SeeTrax, Eagle".
  - Features: gridless routing up to 256 layers, diff-pair and length-matching autorouting, blind/buried vias, split planes, SMD fanout control, area rules — [P] [konekt.com/products](https://konekt.com/products/)
  - Version history: v10.10 (July 2026), v10.09 (Jan 2026), v10.0 (Nov 2025), v9.00 (Jan 2025) and so on — [P] [konekt.com](https://konekt.com/)
  - Pricing: PRO-30 €145 for one month, PRO-UL €2,495 perpetual, node-locked, no dongle — [P] [konekt.com/pricing](https://konekt.com/pricing/)
  - Testimonial on its own site: "Best Router for KiCAD to work with" (vendor-selected) — [P] [konekt.com](https://konekt.com/)
  - A 2021 KiCad-forum thread asking for Electra experiences got no user reports — [P] [forum](https://forum.kicad.info/t/has-anyone-used-the-konekt-electra-autorouter/28712)
- **TopoR (Eremex):**
  - Topological router whose "distinctive feature … is the absence of preferred routing directions". It added DSN/SES import/export in version 4.0, and Eremex has maintained it since 4.1 (2008). Wikipedia still lists v6.3.17875 (2017-09-20) as current — [P] [Wikipedia: TopoR (wikitext)](https://en.wikipedia.org/w/index.php?title=TopoR&action=raw)
  - In 2026 Eremex's English site (eremex.com) markets only SimPCB Lite (an SI calculator), and `/products/topor/` returns 404. The Russian site lists TopoR as the "Автоматический трассировщик" (autorouter) module of the Delta Design suite. The topor.ru domain is for sale — [P] [eremex.com](https://www.eremex.com/); [eremex.ru products](https://www.eremex.ru/products/topor/); [topor.ru](https://topor.ru/)
  - A 2020 KiCad-forum user could not buy a single-user licence because of an account bug on Eremex's site — [P] [forum](https://forum.kicad.info/t/topor-still-active-and-what-best-alternative-also-about-footprints-libs/26632)
  - A Hackaday 2019 test reportedly got 100% routing with fewer vias than a manual KiCad route [S] — [hackaday.io](https://hackaday.io/page/6004)
- **Altium Situs** (doc updated 2026-10-07):
  - "uses a topological-analysis technique to map the board space, which, unlike geometric or shape-based mapping, is not dependent on obstacle shape or coordinates". It "first … define[s] the routing path, then calls on a variety of proven routing algorithms".
  - Caveats in Altium's own doc: "**Differential pairs nets must be manually routed and locked before using the autorouter**"; "If the board contains an area that can not be routed by hand, then it will not be autorouted either"; the router "obeys all Electrical and Routing design rules, except the Routing Corners rule".
  — [P] [Altium docs](https://www.altium.com/documentation/altium-designer/pcb/routing/situs-topological-autorouter)
  - Altium Designer 26.5.1 (6 May 2026) is the latest per Wikipedia. Altium does not brand ActiveRoute or Situs as "AI" [S] — [search summary](https://en.wikipedia.org/wiki/Altium_Designer)
- **"PCB Auto Router" (pcbautorouter.top)** (closed desktop tool, Windows/Linux):
  - "A GPU-accelerated, reinforcement-learning (RL) routing engine". It reads DSN and writes SES, with plugins for KiCad and EasyEDA, local-only operation, diff pairs and serpentines. It runs on a free/Pro model.
  - All claims are the vendor's own; there is no public benchmark.
  — [P] [pcbautorouter.top](https://www.pcbautorouter.top/)

**EasyEDA / JLCEDA (pass 2)**
- **EasyEDA Standard:** cloud and local routers. The docs recommend the local router because "when many users using cloud server, the cloud auto router will fail". The docs also say: "**Auto router is not good enough! Suggest routing manually!**" — [P] [EasyEDA docs: Route](https://docs.easyeda.com/en/PCB/Route/index.html)
- **EasyEDA's local router** (`easyeda/easyeda-pcb-router`, v0.8.11): a headless **Freerouting fork** served over WebSocket (`ws://127.0.0.1:3579/router`); DSN in, JSON traces out; **GPL-3.0** — [P] [GitHub](https://github.com/easyeda/easyeda-pcb-router)
- **EasyEDA Pro V3.2.148 (2026-06-01):** "Brand new auto placement (dual engine)" and "Brand new auto routing, dual engine, supports equal-length differential pair auto routing". V3.2.206 (2026-10-12) fixed "the issue where V4 auto-routing rate was low". These are closed engines with undisclosed algorithms — [P] [EasyEDA Pro update record](https://pro.easyeda.com/page/update-record)

**Siemens (pass 2)**
- **PADS Pro Essentials and Xpedition Standard** (2025-05-21): Siemens frames these as "AI-enhanced" tools for small and mid-sized businesses. Essentials adds "an integrated, co-branded front-end powered by CELUS … AI-assisted schematic and BOM generation". Xpedition Standard adds "design reuse, variant management, **advanced routing automation**, native 3D layout". The release names no specific AI placement or routing algorithm — [P] [Siemens press release](https://news.siemens.com/es-es/siemens-pads-pro-xpedition-ai/); [Digital Engineering 24/7](https://www.digitalengineering247.com/article/siemens-democratizes-ai-driven-pcb-design/electronic-cad)
- **Fuse EDA AI Agent** (2026-03-16, launched at GTC):
  - An "autonomous AI agent that plans and orchestrates multi-tool and multi-agent … PCB system workflows". It has "secure agentic orchestration with **Model Context Protocol (MCP) and Agent Skills** support", "dynamic tool discovery and orchestration across MCP-connected EDA tools", a supervisor/worker hierarchy, and NVIDIA Nemotron models.
  - For PCB, the release only says it "aids layout, signal integrity and other analyses in Xpedition™ software and Hyperlynx™ software".
  — [P] [Siemens press release](https://news.siemens.com/en-us/siemens-fuse-eda-ai-agent/)
- More specific claims on fabricator blogs (AI "predicts routing paths", thermal-aware automated placement) are **not** in Siemens' own releases. Treat as unverified [S] — [AtlasPCB](https://www.atlaspcb.com/blog/siemens-fuse-eda-ai-agent-pcb-workflow-orchestration-2026/); [Fly-Wing](https://www.flywing-tech.com/blog/siemens-unwraps-electronic-systems-design-software-with-ai-enhancements/)

**Front-end and adjacent AI startups (not layout) (pass 2)**
- **CELUS:** "Our agents design it … delivered as a schematic and BOM". "A reference schematic and a complete BOM … opened straight in Altium, Cadence, Siemens, Fusion or KiCad". Component makers can expose catalogs "as live tools over MCP". No PCB layout automation — [P] [celus.io](https://www.celus.io/). It is also the AI front end of Siemens PADS Pro Essentials — [P] [Siemens](https://news.siemens.com/es-es/siemens-pads-pro-xpedition-ai/)
- **Circuit Mind** (London): "PCB Schematic & BoM in Seconds"; "a real hardware architecture converted into a complete, verified schematic and BoM in minutes". It cites a "Peer-Reviewed Case Study … by Los Alamos National Labs". No layout product — [P] [circuitmind.io](https://www.circuitmind.io/). Funding per CB Insights: about $8.41M over 7 rounds [S] — [CB Insights](https://www.cbinsights.com/company/circuit-mind/financials)
- **SnapMagic** (formerly SnapEDA) Copilot: "Use AI to auto-complete circuit board designs", "adding bypass capacitors", BOM cost and power optimization, supply-chain alternates, "Works with the tool you already use". It is a schematic/BOM copilot with no placement or routing — [P] [snapmagic.com](https://www.snapmagic.com/)
- **Cadstrom** (Montreal, founded 2023): $6.8M seed led by Bison Ventures. Its "Sigma Engine" does automated design **verification** to avoid respins — [P] [PCD&F](https://www.pcdandf.com/pcdesign/index.php/editorial/menu-news/design-news/18462-ai-based-design-startup-raises-6-8m-in-seed-funding)
- **Flux:** disclosed $37M total in Feb 2026 (a $10M seed plus a Series B led by 8VC) [S] — [SiliconANGLE](https://siliconangle.com/2026/02/27/flux-nabs-37m-automate-printed-circuit-board-development-ai/)

**AI-plus-service and agent-first newcomers (pass 2)**
- **Diode Computers** (YC S24, Brooklyn): "Custom circuit boards, designed and manufactured with AI".
  - Self-serve: "You, with our AI agent", from "a description, block diagram or KiCad project", with fab and assembly in-house. Enterprise: "From $10,000 per design, plus fab" — [P] [diode.computer](https://www.diode.computer/)
  - Series A of $11.4M (a16z), per its YC page news list — [P] [YC profile](https://www.ycombinator.com/companies/diode-computers-inc)
  - Toolchain: the **Zener** language (Starlark-based) plus the `pcb` CLI (Rust, **MIT**, 463★), which "generates KiCad layout files" and "needs KiCad 10.x for layouts". No autorouting or placement automation is described [P] — [diodeinc/pcb](https://github.com/diodeinc/pcb)
  - With Anthropic, Diode built an agentic reference-design-generation task (datasheet to Zener schematic, graded by a requirement testbench). "Diode's electrical engineers preferred Sonnet 4.5's reference designs over those from Opus 4 (60% vs 40%) and Sonnet 4 (82% vs 18%)" — [P] [Claude blog](https://claude.com/blog/making-claude-a-better-electrical-engineer)
- **HeyPCB:** a cloud placement, routing and DRC service behind MCP (Section 2) [P] — [GitHub](https://github.com/HeyPCB/heypcb-mcp)
- **OpenAI GPT-6 Astra KiCad demo** (Sept 2026):
  - OpenAI's launch post included "a 15-second condensed playback of GPT‑6 Astra performing printed circuit board (PCB) layout in KiCad … placing components and routing copper connections" (quoted in the KiCad forum) — [P] [KiCad forum thread](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487)
  - Per a search summary, a community tester found the routing was "KiCad DSN export → Freerouting → SES import", and a GUI-only run produced three short traces in an hour. I could not locate that tester's original post [S] — [Hackaday](https://hackaday.com/2026/09/05/can-ai-now-design-pcbs-that-just-work/)
  - Hackaday: GPT-6 Astra "scores 69.3% (+/- 10%)" on EEBench, "roughly in the same ballpark as Claude Opus 5" — [P] [Hackaday](https://hackaday.com/2026/09/05/can-ai-now-design-pcbs-that-just-work/)

### Inferences
- For a KiCad-native GPL-3.0 project, Freerouting is the obvious routing baseline and dependency: same license, active (five releases from May to Oct 2026), MCP and REST already built, explicitly aimed at LLM consumers (compact DRC), with a KiCad 10 IPC path and a public benchmark corpus.
- Quilter and DeepPCB are the quality bar for "AI layout", but both are closed cloud services. They suit benchmarking comparisons and optional user-facing integrations, not reusable components. Quilter publishes no API (none found).
- Flux, Cadence, Zuken, Altium and Siemens all keep routing of critical nets and placement intent human-led or tool-specific. Altium's own doc requires diff pairs to be pre-routed by hand before Situs runs. "Full autonomy" claims hold mainly for small and medium boards.
- **DSN/SES is the lingua franca.** Every commercial autorouter here (Allegro PCB Router, Electra, TopoR, PCB Auto Router) and all the open ones (Freerouting, fastroute, EasyEDA's fork, LibrePCB export) speak it. A project that emits good DSN gets a plug-in socket for commercial routers as optional user-supplied back ends. Electra at €145/month is the most accessible commercial benchmark to compare against.
- **Placement is where the market is moving.** Of mainstream tools, only EasyEDA Pro (closed, June 2026), DeepPCB, Quilter and the 2023 Cadence/Zuken programmes claim auto-placement. Front-end AI startups stop at the schematic. This supports building open placement as the main differentiator.
- Siemens' Fuse agent and CELUS both standardise on **MCP plus Agent Skills**. That validates an MCP-plus-skills interface for an open KiCad project and suggests interoperability with enterprise agents later.

### Gaps
- No primary detail on algorithms or results for EasyEDA Pro's "dual engine" auto placement and routing, nor on how "AI" any Siemens/Xpedition routing feature is.
- TopoR's current version, pricing and availability outside Russia are unclear. The English product page is gone.
- **Cadstar** (Zuken) was not researched. Search budget was exhausted, and it is a legacy product with no evident 2025–26 AI story.
- The "Silixon" (UK) company mentioned by an HN commenter as an incumbent was not identified.
- No public Quilter API documentation or price list, and no Quilter technical paper confirming RL (under separate verification).

## 4. Open-source autorouting/placement code that could be reused

### Takeaway
Reusable open routing code exists at several quality levels:
- Freerouting (Java, GPL-3.0; mature batch router with fanout, rip-up passes and a post-route optimizer)
- fastroute (Rust port of Freerouting, GPL-3.0)
- KiCadRoutingTools (Rust/Python A* with diff pairs and fanout, MIT)
- tscircuit capacity-autorouter (TypeScript, hypergraph/capacity-mesh, MIT)
- OrthoRoute (GPU PathFinder for huge orthogonal backplanes only, MIT)
- Topola (Rust topological router, MIT, work in progress)
- KiCad's own PNS push-and-shove router (C++, GPLv3+). It is now **available headlessly** through LG AI Research's PCBWorld-Engine (GPLv3 pybind11 binding of KiCad 9.0.8's PNS plus DRC). Horizon EDA (GPL-3.0) also embeds it.
- route-rnd (pcb-rnd's external router; GPL-2+; topological "rubber band sketch" plus horizontal/vertical algorithms over the tEDAx format)
- rjwalters/kicad-tools (MIT; A* router plus force-directed/GA/CMA-ES placement)
- EasyEDA's GPL-3.0 Freerouting fork
- The gEDA Toporouter (2008, Dayan rubber-band thesis), now historical

Open **placement** code is thin but no longer empty:
- KiCad's 2012-era autoplacer
- kicad-tools' force-directed/GA/CMA-ES optimizers (MIT)
- CadMust-Neo (simulated annealing)
- tscircuit's "Sequential Optimal Packing" approach (documented, MIT ecosystem)
- an academic RL codebase (RL_PCB)
- domain-specific placers (keyboards, spreadsheets)

Constraint-aware PCB placement is still the biggest build-it-yourself area.

### Cited Findings
- **Freerouting**: see Section 3. GPL-3.0, Java; v2.4.1 decoupled the core from Swing/AWT — [releases](https://github.com/freerouting/freerouting/releases)
- **fastroute**: GPL-3.0-or-later, Rust, derivative of Freerouting — [GitHub](https://github.com/parisxmas/fastroute)
- **KiCadRoutingTools**: MIT; grid-based octilinear multi-layer A*, Rust core "~10× faster than pure Python", pose-based A* with a Dubins heuristic for diff pairs. Stated limitations: "No push-and-shove (routes around obstacles, doesn't move them)", no blind/buried vias, no global topology planning — [GitHub](https://github.com/drandyhaas/KiCadRoutingTools)
- **tscircuit capacity-autorouter**: MIT, TypeScript, pipeline and hypergraph based; input is SimpleRouteJson (`layerCount`, `minTraceWidth`, `obstacles`, `connections`, `bounds`…); results are tracked on an "Autorouter Benchmark Dashboard" — [GitHub](https://github.com/tscircuit/tscircuit-autorouter). Related tscircuit repos: `tscircuit/autorouting` (dataset plus algorithms, **archived**) — [GitHub](https://github.com/tscircuit/autorouting); `autorouting-dataset-01` ("A set of 200 tscircuit problems to benchmark autorouting") — [GitHub](https://github.com/tscircuit/autorouting-dataset-01); `dataset-zero-obstacle-high-density-z01` — [GitHub](https://github.com/tscircuit/dataset-zero-obstacle-high-density-z01); `dsn-converter` (Specctra DSN to Circuit JSON) — [GitHub](https://github.com/tscircuit/dsn-converter)
- **OrthoRoute**: MIT, v1.0.0, KiCad 10+ IPC plugin. Manhattan lattice plus PathFinder negotiated congestion with a CUDA/CuPy (or Metal) SSSP kernel; "It is not a general-purpose PCB autorouter"; "useful to about five people on the planet" — [GitHub](https://github.com/bbenchoff/OrthoRoute)
- **Topola**: MIT, Rust, "a work-in-progress interactive topological router", funded by NLnet NGI0 Entrust; main repository on Codeberg — [GitHub mirror](https://github.com/mikwielgus/topola)
- **vygr C-PCB / JS-PCB / Python-PCB / Go-PCB**: GPL-2.0, last pushes 2024-02 (C++) and earlier (stale) — [C-PCB](https://github.com/vygr/C-PCB). **Ruby-PCB-Router** (topological rubberband): last push 2016 (stale) — [GitHub](https://github.com/StefanSalewski/Ruby-PCB-Router)
- **Horizon EDA** (1,324★, **GPL-3.0**, last push 2026-10-04):
  - Its `3rd_party/router` contains `kimath` and `clipper_kicad`, and `3rd_party/router/router` holds KiCad's PNS sources (`pns_router`, `pns_shove`, `pns_walkaround`, `pns_diff_pair_placer`, `pns_meander_placer`, `pns_optimizer`, `pns_topology` and others) [P] — [GitHub](https://github.com/horizon-eda/horizon/tree/master/3rd_party/router/router); [licence via GitHub API](https://github.com/horizon-eda/horizon)
  - Horizon's docs confirm "the interactive router originally developed for KiCad … Routing differential pairs is supported as well". They list **Autorouter as a non-goal**: "Writing a good autorouter is a lot of work … an autorouter is rarely useful for small to medium-sized boards" [P] — [Horizon feature overview](https://docs.horizon-eda.org/en/latest/feature-overview.html); [Non-goals](https://docs.horizon-eda.org/en/latest/non-goals.html)
- **PCBWorld-Engine** (LG AI Research; GPLv3; created 2026-08-29; 5★): "KiCad's push-and-shove router exposed through a pybind11 binding and served to the environment over a unix socket. Derived from KiCad 9.0.8" [P] — [GitHub](https://github.com/LGAI-Research/PCBWorld-Engine)
  - The paper describes **58 Python APIs**: "14 reproduce the core routing API of PNS::ROUTER, 28 directly wrap KiCad's DRC and board-state extraction APIs, and 16 provide auxiliary utilities". It is built "against KiCad 9.0.8 with kicad-python 0.6.0".
  - Session primitives include `fix_route`, `cancel_route`, `finish` ("invokes the PNS router to complete the route to the Euclidean-nearest unconnected pad"), `flip_posture`, `toggle_via`/`switch_layer`, `set_routing_mode` (mark_as_obstacles / push_n_shove / walkaround) and `set_corner_mode` (45°/90°).
  - Per-netclass widths and vias are pushed into PNS on net selection. Copper pours are not represented in the PNS routable space.
  — [P] [PCBWorld paper (HTML)](https://arxiv.org/html/2607.05915)
- **PCBWorld** (environment, agents, benchmark; **BSD-3-Clause**; v1.1.0; 31★): a Gymnasium environment with actions `ACT_NET_SELECT`, `ACT_START_ROUTE`, `ACT_MAKE_LINE` and `ACT_NET_END`. Baselines are PPO/GRPO transformer policies, LLM tool-calling agents (OpenAI/Anthropic/Gemini/Together) and rule-based routers (Freerouting, KRT) [P] — [GitHub](https://github.com/LGAI-Research/PCBWorld)
- **route-rnd** (Ringdove/pcb-rnd external autorouter; Debian package 0.9.3-1 in trixie/forky/sid):
  - "a generic 'external autorouter' … It speaks the tEDAx format … Route-rnd is a modular router that offers different routing algorithms".
  - Licence **GPL-2+** (bundled libs are public domain, LGPL-2.1+ or BSD-3), so it can be combined with GPL-3.0.
  - Router plugins: `rt_topo` (topological, with `libgrbs` "generalized rubber band sketch" and CRBS/TRBS variants), `rt_horver` and `rt_hace`.
  - Its state page lists known limitations: the convex-only rt_topo/crbs leaves "unnecessary curves" and some rats "are not routed or go around far away obstacles in long detours", and rt_horver needs pins aligned "on a (preferrably >=100mil) grid". NLnet is named as a major supporter.
  — [P] [Debian sources: README](https://sources.debian.org/src/route-rnd/0.9.3-1/README/); [debian/copyright](https://sources.debian.org/src/route-rnd/0.9.3-1/debian/copyright/); [doc/state.html](https://sources.debian.org/src/route-rnd/0.9.3-1/doc/state.html/); [doc/index.html](https://sources.debian.org/src/route-rnd/0.9.3-1/doc/index.html/)
  - pcb-rnd itself was forked from gEDA PCB in 2013 and grew into the Ringdove suite (sch-rnd, camv-rnd, route-rnd) [P] — [Wikipedia: Pcb-rnd (wikitext)](https://en.wikipedia.org/w/index.php?title=Pcb-rnd&action=raw)
- **gEDA PCB Toporouter:** "developed by Anthony Blake in a Google-funded open source project mentored by DJ Delorie in 2008 … mostly based on … Tal Dayan's 1997 PhD thesis, 'Rubberband based topological router'". Wikipedia adds "This router has meanwhile been adapted for use with the open-source KiCad project as well". I found no evidence of that in KiCad's source (KiCad's router is PNS), so treat the claim as dubious. The original project page is dead (archived 2011). It is historical, not maintained [P] — [Wikipedia: PCB (software) (wikitext)](https://en.wikipedia.org/w/index.php?title=PCB_(software)&action=raw)
- **LibrePCB** (3,026★, **GPL-3.0**; 2.0.0 on 2026-01-28 with a new UI; 2.1.1 on 2026-06-12): no built-in autorouter. Since **1.2.0 (2024-12-01)** it supports "Specctra DSN Export / SES Import (#1457) … luckily you can now use an external autorouter like Freerouting". Its 2026 releases add no routing automation [P] — [LibrePCB 1.2.0 notes](https://librepcb.org/blog/2024-12-01_release_1.2.0/); [blog index](https://librepcb.org/blog/); [2.1.0 notes](https://librepcb.org/blog/2026-05-19_release_2.1.0/)
- **OpenROAD** (3,203★, RTL-to-GDS for chips) — [GitHub](https://github.com/The-OpenROAD-Project/OpenROAD)
- **rjwalters/kicad-tools** (MIT): file-based force-directed, evolutionary and hybrid placement; a CMA-ES/Bayesian `optimize-placement`; an A* autorouter with an optional C++ backend [P] — [GitHub](https://github.com/rjwalters/kicad-tools)
- **tscircuit "Sequential Optimal Packing"** (blog, 2026-04-01):
  - "Sequential Optimal packing sequentially packs chips in the Pack Order. Each time it packs a new chip, it selects the Optimal position based on the Cost Function", searching along the boundary of already-packed parts.
  - The post argues plain space-minimising packing makes boards "nearly impossible to route", and force-directed placement gives odd shapes and local minima that are "wildly unpredictable".
  - It notes "LLM loops can easily adapt the design intent representation" by hardening constraints, such as packing a decoupling capacitor with its chip.
  — [P] [blog.autorouting.com](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)
- **tscircuit Z01 dataset** (2026-02-26): "1 million autorouting input and output sample images for training vision models to autoroute 2-layer printed circuits", produced by running `@tscircuit/high-density-a01` on random zero-obstacle 10×10 mm problems; published on Hugging Face [P] — [blog.autorouting.com](https://blog.autorouting.com/p/were-releasing-z01-1-million-autorouting)
- **EasyEDA's Freerouting fork** (GPL-3.0, WebSocket server) — see Section 3 [P] — [GitHub](https://github.com/easyeda/easyeda-pcb-router)
- **diodeinc/dsn** (Rust, 5★, no README or licence shown; presumably a Specctra DSN crate given the name) [P, purpose unconfirmed] — [GitHub](https://github.com/diodeinc/dsn)
- **KiCad legacy autoplacer** (`ar_autoplacer.cpp`, 2011–2012) and `spread_footprints.cpp`, GPLv3+ — [KiCad source](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/autorouter); [LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README)
- **RL_PCB**: MIT, "an end-to-end Reinforcement Learning PCB placement methodology" where each component acts as an agent. Paper: Vassallo & Bajada, "Learning Circuit Placement Techniques Through Reinforcement Learning with Adaptive Rewards" (DATE 2024). Trained on "a relatively small training dataset of 6 circuits"; Python 3.8, PyTorch 1.13, CUDA 11.7; 71 stars — [GitHub](https://github.com/LukeVassallo/RL_PCB)
- **CadMust-Neo** (simulated annealing, KiCad plugin, 29 stars) — [GitHub](https://github.com/remiblokker/CadMust-Neo); **kicad-kbplacer** (543 stars) — [GitHub](https://github.com/adamws/kicad-kbplacer); **PlaceFootprints** (by sheet or pattern, v10 branch) — [GitHub](https://github.com/MitjaNemec/PlaceFootprints)
- Freerouting lists **pcb-rnd** among its integrations — [README](https://github.com/freerouting/freerouting)

### Inferences
- KiCad's PNS router has been extracted from KiCad **twice**: in Horizon EDA (a long-standing GUI app) and in PCBWorld-Engine (a headless pybind11 server built for agents). Both are GPL-3.0. PCBWorld-Engine is the most direct way for an LLM agent to run KiCad-native, DRC-aware interactive routing (route this net, shove neighbours, finish to the nearest pad) with no GUI. That is a primitive no other open router offers.
- License compatibility for a GPL-3.0 project:
  - Can be absorbed: MIT (KiCadRoutingTools, kicad-tools, tscircuit, OrthoRoute, Topola, RL_PCB, kicad-python, Diode `pcb`), BSD-3 (PCBWorld env), Apache-2.0 (DeepPCB plugin, eda-agent, copperhead), GPL-3.0(+) (Freerouting, fastroute, KiCad, Horizon, PCBWorld-Engine, LibrePCB, EasyEDA router), GPL-2+ "or later" (route-rnd).
  - GPL-2.0-only code (vygr routers; ReplicateLayout, unless "or later") cannot be combined.
  - AGPL-3.0 code (Konnect) can be combined only under GPLv3 §13, and the AGPL network clause then applies to that part. Treat it as reference only.
- The weakest open component is global placement and floorplanning that respects PCB-specific constraints (connectors on edges, decoupling capacitors next to pins, thermal, keepouts, component classes). Analytical placers from the chip world (OpenROAD) address a different problem: millions of uniform cells versus tens to hundreds of heterogeneous parts with mechanical constraints.

### Gaps
- repo.hu (route-rnd home) stayed unreachable. Route-rnd facts come from Debian's source mirror (0.9.3, files dated 2016–2021), so post-0.9.3 development is unknown.
- I did not test PCBWorld-Engine against KiCad 10 (it is pinned to 9.0.8) and did not measure its throughput or stability.
- OpenROAD's license and component modularity were not checked. It targets chips, so it is low priority.

## 5. Public benchmarks and comparisons

### Takeaway
Before 2026 there were no neutral, standard PCB routing benchmarks, and there are still **none for placement**. Routing now has:
- the **PCBench** corpus (He et al., 2024; GitHub `PCBench/PCBench`, MIT), which Freerouting's in-repo "1,157-board PCBench" suite and PCBWorld's 679-board D3 set both derive from;
- **PCBWorld-Bench** (LG AI Research, KDD 2026 workshop; read in full this pass), which scores routers, RL policies and LLM agents with the same 8 KiCad-engine metrics;
- tscircuit's datasets (including the 1M-sample Z01) and its dashboard.

Agent-level benchmarks also appeared: EEBench (atopile; analog and digital design in simulation, **layout explicitly out of scope** in v1), EDA-bench (35 KiCad project-reconstruction tasks, ICML 2026), and devbisme's informal multi-tool KiCad test bed.

PCBWorld's results are the most useful single data point for this project:
- Freerouting is the strongest rule-based router (clean pass 0.80 on 99 small real boards, 0.78 on medium ones).
- LLM agents acting through KiCad's native router with DRC feedback reach 0.65 (GPT-5.4).
- The same model drops to 0.19 in plan-then-execute mode and 0.02 when it emits geometry without the engine.
- Every LLM scores 0.00 on medium boards.

Vendor numbers (Quilter Speedrun, DeepPCB's 27,721 boards, Cadence's 10×) are self-reported and not comparable.

### Cited Findings
- Freerouting PCBench: 1,157 fixtures added to the repo in v2.4.x. v2.5.0 reports clean-board completion rising from about 31% to 75% (self-reported) — [Freerouting releases](https://github.com/freerouting/freerouting/releases). Scoring definitions are in [docs/scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)
- **PCBWorld / PCBWorld-Bench** [P]:
  - Hyungseok Song, Junseok Park, Won-Seok Choi, Seohui Bae, Han-Seul Jeong, Youngjoon Park, Soonyoung Lee, "PCBWorld: A Benchmark Environment for Engine-Grounded PCB Design Automation", arXiv:2607.05915 (v4). "Accepted to the KDD 2026 Workshop on Evaluation and Trustworthiness of Agentic AI (non-archival)" — [arXiv abstract](https://arxiv.org/abs/2607.05915)
  - **Datasets:** D1 is synthetic grid routing (Jumanji Connector-style, grid sizes 10–500). D2 is synthetic gridless 2-layer multi-pin boards. D3 is "a curated set of 679 boards derived from PCBench's open-source PCB corpus (He et al., 2024)", normalized to KiCad 9 and kept only if fully connected and DRV-free, split by pad count into D3-A/B/C. Zero-shot evaluation uses 99 D3-A and 10 D3-B boards; D3-C ("hundreds of nets") is a challenge split — [paper HTML](https://arxiv.org/html/2607.05915)
  - **Metrics:** primary "Clean Pass (CP)", meaning every net connected with zero DRC violations, plus Potential Gain, Routability, Time, DRV count, wirelength and vias; best-of-5 rollouts ("@5") — [paper HTML](https://arxiv.org/html/2607.05915)
  - **Table 3 (CP / Routability, @5):**

    | Method | D2 | D3-A (99 boards) | D3-B (10 boards) |
    |---|---|---|---|
    | Freerouting 2.1.0 | 1.00 / 1.00 | 0.80 / 0.91 | 0.78 / 1.00 |
    | KiCadRoutingTools | 1.00 / 1.00 | 0.74 / 0.94 | 0.20 / 0.86 |
    | OrthoRoute | 0.01 / 0.34 | 0.02 / 0.53 | 0.00 / 0.44 |
    | GPT-5.4 via PCBWorld tools | 0.96 / 1.00 | 0.65 / 0.91 | 0.00 / 0.62 |
    | GPT-5.4-mini | 0.58 | 0.28 | 0.00 |
    | GPT-5.4-nano | 0.55 | 0.30 | 0.00 |
    | Qwen3.5-397B | 0.33 | 0.34 | 0.00 |
    | PPO transformer (trained only on synthetic D2) | 1.00 | 0.86 | 0.45 |

    Mean times on D3-A: Freerouting 7.09 s, KRT 0.65 s, GPT-5.4 231 s, PPO 1.83 s. "All LLM agents nonetheless obtain 0.00 CP on D3-B, leaving large-board routing … an open challenge for current LLMs" — [paper HTML](https://arxiv.org/html/2607.05915)
  - **Engine engagement (Table 4, GPT-5.4 on D3-A):** interactive CP 0.65 (DRV 1.31); plan-and-execute CP 0.19 (DRV 16.28); engine-free CP 0.02. "Leveraging the native API is essential for design-rule-clean routing … generating raw wire segments while keeping every track within the design rules is beyond current models". For GPT-5.4-nano in engine-free mode, on 10% of boards none of the five rollouts even loaded as a valid KiCad file — [paper HTML](https://arxiv.org/html/2607.05915)
  - OrthoRoute's README quotes the OrthoRoute rows slightly differently (30% and 51% routability), probably @1 versus @5 — [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute)
- **PCBench** (`PCBench/PCBench`, MIT per GitHub sidebar, 21★): "a dataset consisting of 164 printed circuit boards", with `raw.kicad_pcb`, `processed.kicad_pcb`, a PCB-RDL `final.json`, an augmentation script and an RL environment [P] — [GitHub](https://github.com/PCBench/PCBench)
  - **Count discrepancy:** the README says 164 boards, PCBWorld derives 679 boards from "PCBench's open-source PCB corpus", and Freerouting's release notes cite a "1,157-board PCBench corpus". These may be different versions or augmentations of the corpus. Unresolved — [PCBench](https://github.com/PCBench/PCBench); [PCBWorld](https://arxiv.org/html/2607.05915); [Freerouting releases](https://github.com/freerouting/freerouting/releases)
- **EEBench** (by atopile):
  - Agents submit atopile design bundles. Grading is deterministic: build checks, SPICE simulations at worst-case tolerance corners, and BOM cost. "The leaderboard score blends engineering and economics: 0.65 × technical + 0.35 × cost-efficiency".
  - "**Layout is deliberately out of scope** — sequenced, not forgotten … V2 and beyond put layout in scope, fabricate the boards". Tasks are private.
  — [P] [EEBench methodology](https://eebench.org/methodology.html); [blog](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)
  - Third-party leaderboard snapshot (Sept 2026): Claude Opus 5.5 (Claude Code) 75.0%, GPT-6 Astra (Codex CLI) 69.3%. An August snapshot had Claude Opus 5 at 61.6% [S] — [BenchLM mirror](https://benchlm.ai/benchmarks/eebench)
- **EDA-bench** ("Execution-based benchmark for open-book KiCad PCB reconstruction agents"): 35 Harbor tasks; the agent must produce a full KiCad project. The verifier checks schematic, PCB, connectivity, physical realization, ERC/DRC and a functional contract, with difficulty-weighted scoring. No model results on the README [P] — [GitHub](https://github.com/EDA-bench/eda-bench). It is associated with an ICML 2026 paper, "EDA Bench: Functional Failure Modes in PCB-Generating Agents" [S] — [ICML](https://icml.cc/virtual/2026/77908)
- **devbisme ai-circuit-design-tests:** the same dual-ADC prompt across about 10 KiCad AI tools plus a no-tools baseline. Results are unvalidated; see Section 2 [P] — [GitHub](https://github.com/devbisme/ai-circuit-design-tests)
- **tscircuit Z01:** 1M zero-obstacle 2-layer routing samples for vision models [P] — [blog](https://blog.autorouting.com/p/were-releasing-z01-1-million-autorouting)
- tscircuit: an "Autorouter Benchmark Dashboard" (autorouter-benchmark-dashboard.vercel.app), plus an SRJ33 DRC-failure dataset of "37 distinct inputs" — [tscircuit-autorouter README](https://github.com/tscircuit/tscircuit-autorouter); a 200-problem dataset — [autorouting-dataset-01](https://github.com/tscircuit/autorouting-dataset-01)
- fastroute versus Freerouting over 20 boards: 510 s versus 2102 s (self-reported) — [fastroute](https://github.com/parisxmas/fastroute)
- KiCadRoutingTools, self-reported: 47/47 FTDI single-ended nets in 8.6 s and 28/28 LVDS pairs in 29.7 s; ongoing A/B tests on a corpus of open-source boards — [GitHub](https://github.com/drandyhaas/KiCadRoutingTools)
- DeepPCB: "27,721 Boards, 95.6% Hit 95%+ Completion" (self-reported, page title) — [DeepPCB](https://deeppcb.ai/kicad-autorouter-alternative/)
- Quilter Speedrun: 843 components, 8 layers, 38.5 h versus 428 h quoted, first-boot success (self-reported; design files public) — [BusinessWire](https://www.businesswire.com/news/home/20251210722060/en/Quilter-Unveils-Worlds-First-Computer-Designed-by-AI); [design files](https://quilter.ai/project-speedrun/download). Quilter also published a March 2026 timed comparison of one MCU board in Altium, KiCad and Quilter; the results were not visible in the snippets — [Quilter blog](https://www.quilter.ai/blog/a-data-driven-look-at-pcb-layout-speed-in-2026-quilter-ai-vs-altium-vs-kicad)
- comma.ai **PCBGolf** ("Are you better than an autorouter?"): a KiCad board loosely based on the panda jungle v2. "Score = PCBA bounding box volume (mm³) + 50 × number of vias + 5,000 × number of copper layers"; JLCPCB-manufacturable; $1,000 prize with an Oct 12, 2026 deadline — [GitHub](https://github.com/commaai/PCBGolf)
- An older anecdote: an EEVblog user found Freerouting produced 11 vias against 18 for their manual routing on a single board (2010 thread) — [EEVblog (search snippet)](https://www.eevblog.com/forum/projects/can-you-route-better-than-an-autorouter/msg25819)

### Inferences
- A GPL-3.0 project can adopt **PCBWorld-Bench** (BSD-3 harness, `.kicad_pcb` boards, engine-checked metrics) as its primary routing benchmark, with PCBench (MIT) and Freerouting's suite and scores as secondary suites. Per-board licences inside the corpus need checking before redistribution. PCBGolf is a good public showcase board, since its scoring combines placement compactness, vias and layer count.
- Completion percentage alone misleads. Freerouting splits "legal and complete" from "efficient", and PCBWorld distinguishes "clean pass" from "routability". The devbisme baseline shows "0 DRC errors" can coexist with signals routed on a plane layer. Use clean-pass plus efficiency plus layout-quality checks.
- **PCBWorld's engine-engagement result supports this project's architecture.** LLMs should not emit copper coordinates. They should drive a DRC-aware engine interactively (or delegate to a router) and reason about intent, constraints and ordering. A small RL policy beating LLMs at the step level suggests a split: the LLM plans and critiques, specialised solvers or policies execute.
- No placement benchmark exists, so a placement-quality suite would be a novel open contribution. Candidate inputs: PCBWorld D3 boards with placement stripped, scored by downstream router clean pass, wirelength and vias, plus design-rule proxies such as decoupling distance.

### Gaps
- Dataset licences for PCBWorld-Bench's 679 real boards and PCBench's per-board provenance were not checked.
- The three different PCBench board counts (164 / 679 / 1,157) are unreconciled.
- No independent third-party benchmark of Quilter, DeepPCB or Flux was found. PCBWorld did not evaluate them.
- tscircuit dashboard contents and any autorouting bounty or contest results could not be fetched. EDA-bench and EEBench per-model layout results do not exist yet, since EEBench v1 excludes layout.

## 6. Practitioner sentiment

### Takeaway
I could gather little direct practitioner sentiment: Reddit, Hacker News, EEVblog and the KiCad forum were blocked and web search ran out. What is available is consistent, though. Autorouters and AI layout are seen as useful for low-to-medium complexity boards and for throughput. Experienced designers stay sceptical and keep critical nets, placement intent and final review human-led. The tools' own docs reinforce this ("Never trust the autorouter"; "not designed to fully autoroute every class of board").

### Cited Findings
- Slashdot commenters on Quilter's Speedrun said the tool builds on auto-routing technology that has existed for years and debated the novelty claim — [Slashdot](https://hardware.slashdot.org/story/25/12/16/229209/dual-pcb-linux-computer-with-843-components-designed-by-ai-boots-on-first-attempt)
- A Gradient podcast with Quilter's CEO covers "dealing with skepticism" (no specifics in the snippet) — [The Gradient](https://thegradientpub.substack.com/p/sergiy-nesterenko-quilter-pcb-design-ai-compiler)
- Flux's own docs say Auto-Layout is "not designed to fully autoroute every class of board without your input" — [Flux docs (snippet)](https://docs.flux.ai/tutorials/auto-layout). A Hacker News thread mentions an Adafruit review of AI PCB tools and a user's Flux experience (content not retrievable) — [HN item 48368721](https://news.ycombinator.com/item?id=48368721)
- tscircuit community: the default autorouter is "hard to steer", and manual `pcbPath` overrides are offered — [tscircuit community thread (snippet)](https://community.tscircuit.com/thread/1535064342741913631/raw)
- OrthoRoute's tagline is "Never trust the autorouter" — [GitHub](https://github.com/bbenchoff/OrthoRoute). PCBGolf frames itself as "Are you better than an autorouter?" — [GitHub](https://github.com/commaai/PCBGolf)
- MCP projects themselves add disclaimers: "AI-generated design suggestions do not replace qualified engineering review" — [mixelpixx](https://github.com/mixelpixx/KiCAD-MCP-Server); "not an automated sign-off authority" — [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro)

### Inferences
- An LLM-driven tool that keeps the human in the loop will likely be received better than a "full autonomy" claim: propose, show diffs and renders, accept per-net, with undoable IPC commits. So will one that is transparent about quality (DRC plus scores).

### Gaps
- No direct Reddit (r/PrintedCircuitBoard, r/KiCad), HN or EEVblog threads on Quilter, DeepPCB, Flux Auto-Layout or Freerouting 2.x could be read. A follow-up with web access to those domains is needed for real sentiment data.
- A search summary said one tscircuit-based project falls back to Freerouting when tscircuit's built-in router leaves nets unrouted or violates clearance. The underlying page could not be identified or opened (possibly [this tessl.io skill listing](https://tessl.io/registry/skills/github/JimmyPang02/open-replicator/replicator-pcb--replicator-pcb)), so treat it as unverified.

## 7. Implications: what to reuse, integrate, or build (for a GPL-3.0, LLM-driven KiCad placement+routing project)

### Takeaway
Reuse KiCad's IPC API (kipy, MIT) for live board mutation. Use Freerouting (GPL-3.0) as the baseline routing engine and benchmark harness. Optionally add fastroute (GPL-3.0) or KiCadRoutingTools (MIT) as faster or specialized routers. Integrate KiCad's built-ins (DRC rules, component classes, multichannel, design blocks, "Attempt Finish Selected") as levers the agent can pull. **Build** the parts nobody has done well in open source: constraint-aware PCB placement and floorplanning guided by an LLM, and a tight agent loop of propose → apply → DRC/score → critique → repair, exposed through a small, high-level MCP tool set.

### Cited Findings
- IPC API: live GUI only on KiCad 9/10; headless and exports in KiCad 11; SWIG removed in 11 — [dev-docs (source)](https://gitlab.com/kicad/services/kicad-dev-docs/-/blob/master/content/apis-and-binding/ipc-api/for-addon-developers/_index.en.adoc); [kicad-python README](https://gitlab.com/kicad/code/kicad-python)
- KiCad 11 IPC adds `RunBoardJobExportSpecctraDsn` and `ImportSpecctraSession` — [board_jobs.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto); [board_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto)
- Freerouting v2.5.0: KiCad 10 IPC integration, REST `/v1/autoroute`, MCP `autoroute_board`, LLM-compact DRC, PCBench, two scores — [releases](https://github.com/freerouting/freerouting/releases)
- KiCad has `RunAction` (unstable) plus built-in actions: Autoroute (Attempt Finish Selected), autoplacer, repeatLayout, generatePlacementRuleAreas, Specctra export/import — [editor_commands.proto](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto); [pcb_actions.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp)
- Licenses: Freerouting GPL-3.0 — [GitHub](https://github.com/freerouting/freerouting); fastroute GPL-3.0-or-later — [GitHub](https://github.com/parisxmas/fastroute); KiCadRoutingTools MIT — [GitHub](https://github.com/drandyhaas/KiCadRoutingTools); tscircuit autorouter MIT — [GitHub](https://github.com/tscircuit/tscircuit-autorouter); kicad-python MIT — [pyproject](https://gitlab.com/kicad/code/kicad-python/-/blob/main/pyproject.toml); Konnect AGPL-3.0 — [GitHub](https://github.com/mixelpixx/Konnect); KiCad GPLv3+ — [LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README); ReplicateLayout GPL-2.0 — [GitHub](https://github.com/MitjaNemec/ReplicateLayout)

### Inferences (concrete recommendations)
1. **KiCad interface layer (reuse plus a thin build).**
   - Target KiCad 10.0.x and pin `kicad-python` 0.8.x.
   - Wrap a `BoardSession` abstraction with three backends:
     - (a) live IPC (default; undoable `BeginCommit`/`EndCommit`; respect single-connection and busy-retry semantics);
     - (b) KiCad 11 headless `kicad-cli api-server` once it ships;
     - (c) a file-level S-expression fallback for CI. Write a small maintained parser, because kiutils and kicad-skip PyPI releases date from Feb 2024.
   - Avoid new SWIG code (removed in 11). If it is used temporarily (e.g., DSN export on KiCad 10), isolate it behind the abstraction.
   - Always use `kicad-cli pcb drc` (JSON report) as the ground-truth checker.
2. **Routing (integrate first, build later).**
   - Ship Freerouting as the default global autorouter. It is license-compatible, so it can be vendored or forked.
   - Drive it through its CLI or native binary, or its local REST/MCP. Feed it DSN from KiCad, via the GUI action or SWIG on 10 and IPC/CLI on 11.
   - Adopt its `V2_CONTINUOUS`/`V2_LOWER_BOUND` scores.
   - Evaluate fastroute as a faster drop-in (Rust, diff pairs, length tuning, `.kicad_dru` carry-over).
   - Evaluate KiCadRoutingTools for BGA/QFN fanout, diff pairs, plane repair and time matching. It is MIT, already agent-oriented, and works on files.
   - Use KiCad's own PNS "Attempt Finish Selected (Autoroute)" through `RunAction` for local completion and cleanup of a few nets, accepting that the action string can break between versions.
   - Treat the tscircuit capacity-mesh/hypergraph pipeline (MIT) as a design reference for a global-routing and congestion-estimation stage, which can also give placement fast routability feedback.
3. **Placement (build; this is the white space).**
   - No mature open-source, KiCad-integrated, constraint-aware PCB placer exists. KiCad's autoplacer dates from 2012, CadMust-Neo is a small SA plugin, RL_PCB is academic, and DeepPCB and Quilter are closed.
   - Build a hybrid. First, an LLM step produces a floorplan and intent: groups by schematic sheet and function, edge-connector and mounting constraints, decoupling-capacitor proximity, thermal and noisy-versus-sensitive zones. Emit this as KiCad-native artifacts (rule areas, component classes, custom DRC rules, keepouts) so the intent is inspectable and DRC-checkable.
   - Then a numeric optimizer (force-directed, SA or analytical) does detailed placement and legalization, using HPWL plus congestion estimates from a fast global router as cost.
   - Use KiCad's `repeatLayout` and PCB Design Blocks for repeated channels and known-good sub-layouts instead of re-solving them.
4. **LLM and agent surface (build, learning from others).**
   - Expose about 15–30 high-level, verifiable MCP tools (board summary, constraint get/set, propose or apply placement for a group, route a net class, run DRC with compact output, score, render a PNG or SVG for vision feedback) rather than 200+ thin CRUD tools.
   - Copy patterns, not code, from Konnect (AGPL: do not vendor), mixelpixx (MIT: reusable), eda-agent's catalog/invoke mode, and Freerouting's `compact=true` DRC.
   - Ship Claude Code skills or playbooks in the way KiCadRoutingTools and JITX do.
5. **Evaluation harness (reuse).** Wire PCBench (1,157 boards, GPL-3.0, in the Freerouting repo), tscircuit datasets (MIT) and, if licensing permits, PCBWorld into CI. Report completion, DRC-clean rate, via count, length relative to lower bounds, and wall time. Use PCBGolf as a public demo target. Optionally run DeepPCB (pay-per-hour API via its plugin) or Quilter (manual upload) as external comparison baselines, not dependencies.
6. **License hygiene.**
   - Can be absorbed: MIT, BSD, Apache-2.0, GPL-3.0(+) code (KiCad, Freerouting, fastroute, kipy, KiCadRoutingTools, tscircuit, OrthoRoute, Topola, RL_PCB).
   - Avoid copying GPL-2.0-only code (vygr routers; check ReplicateLayout's exact "or later" status) and AGPL-3.0 code (Konnect) into the core.
   - Keep cloud services (DeepPCB, Quilter, Freerouting's public API) optional and off by default, for privacy and IP reasons. Quilter's free tier may train on designs, per a third-party summary.
7. **Timing risk.** Plan a migration point at KiCad 11 (likely early 2027; inferred): headless IPC, DSN/SES and design rules over IPC, and SWIG removal all land there. Build the file and IPC abstraction now so the swap costs little.

### Gaps
- No verified data on how well Freerouting 2.5's KiCad 10 IPC integration works in practice, or how much KiCad DRC fidelity is lost on the DSN round trip (Freerouting itself notes missing board-edge clearance in KiCad exports).
- No head-to-head data comparing Freerouting, fastroute, KiCadRoutingTools and the tscircuit router on the same corpus, other than PCBWorld as summarized second-hand in OrthoRoute's README. Running PCBench across all four would close this gap.
