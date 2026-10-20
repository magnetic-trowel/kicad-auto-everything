# Verification of KiCad API/DRC capabilities and tool/product claims (primary sources, as of 2026-10-20)

> **Method note for the report writer.** This pass had internet access. Every claim below was checked against a primary source:
> - **KiCad.** The KiCad 10.0 and master documentation sources on GitLab, plus the rendered pages on docs.kicad.org and dev-docs.kicad.org. The KiCad source code at the `10.0` branch and at `master`: the DRC rule parser, the DRC expression functions, the unit resolver, the DRC item list, the IPC API `.proto` files and the API handler C++, the CLI commands, the SWIG helpers and the Specctra importer. kicad-python at its `0.8.0` tag and at `main`, with PyPI metadata. The kicad.org release notes.
> - **Third-party projects.** READMEs, docs and source fetched through raw.githubusercontent.com and github.com, plus npm and PyPI metadata.
> - **Vendors.** Vendor sites and docs fetched directly: the Quilter GitBook markdown, DeepPCB pages, and Flux blog posts.
>
> **Blocked during this pass:** cadence.com and zuken.com (HTTP 403), dl.acm.org, csl.cornell.edu and ispd.cc. Claims about those come from distributor pages, the press-release text, or OpenAlex metadata, and are labelled.
>
> **Labels:** **VERIFIED** (matches a primary source), **CORRECTED** (the note was wrong or is outdated; corrected value given), **PRECISION** (the note was right but missed a detail that matters for implementation), **CONFLICT** (primary sources disagree with each other), **NOT FOUND** (no primary evidence either way).
>
> "10.0" means the GitLab `10.0` branch at the time of fetch, which carries 10.0.7 plus fixes. "master" means KiCad 11 development.

---

## 1. Corrections table: which claims in the existing notes are wrong, outdated, or imprecise?

### Takeaway
The earlier notes are broadly right. About 35 items need correction or more precision before implementation. Six of them matter most:
- **Stackup update.** `UpdateBoardStackup` is defined in the proto but has no handler, on 10.0 or on master.
- **Specctra session import.** In 10.0 the code deletes all unlocked tracks and vias and can move footprints. The user doc says the opposite.
- **DRC units.** Rules accept `mm/mil/in/deg/ps/fs`; the documented `th`, `"` and `rad` are not accepted by the source.
- **Microvia rules.** `microvia_*` and `isStackedVia` exist only on master. The master keyword is actually `hole_aspect_ratio`.
- **Freerouting flags.** The `-us greedy/hybrid` and `-is random` values and `-hr` were removed in v2.5.0.
- **DeepPCB pricing.** It changed completely: $30 per hour, and a free trial of 30 minutes.

### Cited Findings

| # | Note file | Claim in notes (abridged) | Status | Verified / corrected value | Source |
|---|---|---|---|---|---|
| 1 | existing_tools | KiCad 10.0.0 released 2026-03-20, 7,609 commits; 10.0.7 on 2026-10-07 | VERIFIED | 10.0.0 post dated 2026-03-20 and "7,609 unique commits". 10.0.7 post dated 2026-10-07 (git tag commit 2026-10-06). | [10.0.0 notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/); [10.0.7 notes](https://www.kicad.org/blog/2026/10/KiCad-10.0.7-Release/); [tags](https://gitlab.com/kicad/code/kicad/-/tags) |
| 2 | existing_tools | "Board commands in KiCad 10.0: stackup get/update" | **CORRECTED** | `UpdateBoardStackup` exists in `board_commands.proto`, but no handler is registered in `api_handler_pcb.cpp` on 10.0 **or** master. Only `GetBoardStackup` is served. Treat the stackup as **read-only** over IPC. | [board_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/board/board_commands.proto); [api_handler_pcb.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp); [@master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/api/api_handler_pcb.cpp) |
| 3 | existing_tools | The 10.0 command list covers only editor and board commands | **PRECISION** | 10.0 also serves the project commands `GetNetClasses`/`SetNetClasses`, `Get/SetTextVariables` and `ExpandTextVariables` (in `API_HANDLER_COMMON`). It also serves 8 variant commands: `GetVariants`, `AddVariant`, `DeleteVariant`, `RenameVariant`, `CopyVariant`, `SetVariantDescription`, `SetCurrentVariant` and `GetCurrentVariant`. | [project_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/project_commands.proto); [variant_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/variant_commands.proto); [api_handler_common.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/api/api_handler_common.cpp) |
| 4 | existing_tools | `GetItemsByNet`, `GetItemsByNetClass` and `GetConnectedItems` are "in 10.0" | PRECISION | They need **10.0.1 or later**, per the kipy changelog. Some other items carry point-release tags: `GetBoardLayerByName` is "Since: 10.0.6", and the document header on `BeginCommit` is "Since: 10.0.7". The net-class `tuning_profile` field is "Since 10.0.0". | [kicad-python README changelog](https://gitlab.com/kicad/code/kicad-python/-/blob/main/README.md); [board_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto); [editor_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto); [project_settings.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/types/project_settings.proto) |
| 5 | existing_tools | `schematic_commands.proto` is "new on master" | PRECISION | The file already exists in 10.0 but defines **no messages**. Master adds `GetSchematicHierarchy`, `GetSchematicNetlist` and `PlaceSymbolFromLibrary`, plus `schematic_jobs.proto`. | [tree @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/api/proto); [schematic_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/schematic/schematic_commands.proto) |
| 6 | existing_tools | kipy `main` has `get/set_design_rules`, `get/set_custom_design_rules`, `place_footprint_from_library`, `import_netlist` and `export_*` | **CORRECTED (scope)** | All of these are **unreleased** (main only, version 0.9.0.dev0) and need KiCad 11 (master) protos. The released **kipy 0.8.0 (2026-08-30) has none of them**. Its `Project` has `get_net_classes` but not `set_net_classes`, which is main only. | [kipy/board.py @0.8.0](https://gitlab.com/kicad/code/kicad-python/-/blob/0.8.0/kipy/board.py); [@main](https://gitlab.com/kicad/code/kicad-python/-/blob/main/kipy/board.py); [kipy/project.py @0.8.0](https://gitlab.com/kicad/code/kicad-python/-/blob/0.8.0/kipy/project.py); [pyproject @main](https://gitlab.com/kicad/code/kicad-python/-/blob/main/pyproject.toml) |
| 7 | existing_tools | kipy release history (0.1.0 2024-12-21 … 0.8.0 2026-08-30); MIT; latest main commit 2026-09-23 | VERIFIED | Matches PyPI upload times and the GitLab commit list exactly. 0.7.1 uploaded 2026-04-18 02:51 UTC; the changelog says April 17. | [PyPI](https://pypi.org/project/kicad-python/); [commits](https://gitlab.com/kicad/code/kicad-python/-/commits/main) |
| 8 | existing_tools / solver_toolbox | `RefillZones` is available in 10.0 | **PRECISION** | In 10.0 only a whole-board refill works; passing a zone list returns `AS_UNIMPLEMENTED`. The fill is **asynchronous** (`CallAfter`), so the call returns before the fill finishes. Master adds per-zone fills, rejects rule areas, and fills synchronously in headless mode. | [api_handler_pcb.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp) (handleRefillZones); [@master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/api/api_handler_pcb.cpp) |
| 9 | existing_tools / solver_toolbox | Specctra SES import "adds the routed tracks" | **CORRECTED** | The 10.0 code **deletes all unlocked tracks and vias** and all DRC markers, re-adds locked ones, and **applies the session's placement section**, which repositions and flips footprints. The 10.0 user doc NOTE ("only adds routing; it does not modify footprints") contradicts the code. The master proto comment matches the code. | [specctra_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/specctra_import_export/specctra_import.cpp); [pcbnew_importing.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_importing.adoc); [ImportSpecctraSession comment @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto) |
| 10 | existing_tools | DSN export on KiCad 10 needs the GUI action or SWIG | VERIFIED + PRECISION | The SWIG module `pcbnew` in 10.0 exposes stand-alone `ExportSpecctraDSN(BOARD*, path)`, `ImportSpecctraSES(BOARD*, path)` and `WriteDRCReport(...)`. 10.0.6 fixed quoting, duplicate-reference and layer-name bugs in DSN export. | [pcbnew_scripting_helpers.h @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/python/scripting/pcbnew_scripting_helpers.h); [10.0.6 notes](https://www.kicad.org/blog/2026/08/KiCad-10.0.6-Release/) |
| 11 | existing_tools / solver_toolbox | Master adds `pcb_export_specctra`; commit "CLI: Add pcb export specctra_dsn" (2026-10-14) | VERIFIED + PRECISION | The CLI subcommand name is **`kicad-cli pcb export specctra`** (`PCB_EXPORT_BASE_COMMAND("specctra", …)`). The commit title says "specctra_dsn". The master CLI docs do not document it yet. | [command_pcb_export_specctra.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/kicad/cli/command_pcb_export_specctra.cpp); [commits](https://gitlab.com/kicad/code/kicad/-/commits/master/kicad/cli/command_pcb_export_specctra.cpp) |
| 12 | existing_tools | Headless `kicad-cli api-server` exists in KiCad 11 | VERIFIED + PRECISION | First commit: "ADDED: Headless API server mode for kicad-cli" (2026-03-21, master). Usage is `kicad-cli api-server [--socket SOCKET_PATH] [PROJECT_OR_FILE]`. Not in 10.0. | [command_api_server.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/kicad/cli/command_api_server.cpp); [cli.adoc @master](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/cli/cli.adoc) |
| 13 | existing_tools | KiCad 11 "most likely ships around Q1 2027" (inference) | VERIFIED (inference basis) | Policy: the feature merge window closes **Oct 31**; the major release is due "annually by January 31st". In practice 9.0 shipped 2025-02-20 and 10.0 on 2026-03-20, both late. | [Release policy](https://dev-docs.kicad.org/en/rules-guidelines/release-policy/); [9.0.0 notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/) |
| 14 | constraints_verif | DRC constraint list includes `microvia_aspect_ratio`, `microvia_stack_depth` and `isStackedVia` (flagged "may be dev-only") | **CORRECTED** | These are **master-only**. They are absent from the 10.0 docs, the rendered 10.0 HTML, the 10.0 keyword file and the 10.0 parser. On master the parser keyword is **`hole_aspect_ratio`** (renamed 2026-10-12, "Check the aspect ratio of every plated hole"). The master docs still say `microvia_aspect_ratio`, which the master parser does not accept. | [drc_rules.keywords @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/drc_rules.keywords); [@master](https://gitlab.com/kicad/code/kicad/-/blob/master/common/drc_rules.keywords); [drc_rule_parser.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_rule_parser.cpp); [pcbnew_advanced.adoc @master](https://gitlab.com/kicad/services/kicad-doc/-/blob/master/src/pcbnew/pcbnew_advanced.adoc) |
| 15 | constraints_verif | `track_angle` and `track_segment_length` "may be KiCad 10 or development-only" | VERIFIED (10.0) | Both are parsed and documented in 10.0. | [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp); [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc) |
| 16 | constraints_verif | Constraint list is complete | **PRECISION** | The 10.0 parser also accepts `solder_mask_sliver` (undocumented in the 10.0 constraint table) and the deprecated aliases `mechanical_clearance`, `mechanical_hole_clearance` and `hole`. The 10.0 code also registers an undocumented function `intersectsKeepout('x')`, plus the front/back courtyard variants. | [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp); [pcbexpr_functions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_functions.cpp) |
| 17 | constraints_verif | Units are `mm`, `mil`/`th`, `in`, `deg`, `rad` | **CORRECTED / CONFLICT** | The source unit resolver accepts only **`mil`, `mm`, `in`, `deg`, `fs`, `ps`**. Its error text reads "must be mm, in, mil, deg, fs, or ps". The docs list `th`, `"` and `rad`, but the 10.0 and master resolvers do not include them. The time units `ps`/`fs` are allowed **only** in `length` and `skew` (master also allows them in `net_chain_length` and `stub_length`). | [pcbexpr_evaluator.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_evaluator.cpp); [libeval_compiler.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/libeval_compiler/libeval_compiler.cpp); [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp) |
| 18 | constraints_verif | Time-domain tuning in KiCad 10 lives in tuning profiles | VERIFIED + PRECISION | Beyond profiles, a `length` or `skew` rule written in time units (e.g. `500ps`) "will force the length tuner into time-domain mode for matching nets, regardless of the tuning profile setting". Pads carry an undocumented property `Pad_To_Die_Delay`. | [pcbnew_create_board.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_create_board.adoc); [pad.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pad.cpp) |
| 19 | constraints_verif | PCBWorld Clean Pass: Freerouting 0.80/0.78, KRT 0.74/0.20 (quoted by a third party) | VERIFIED | arXiv v2 Table 3 (@5): Freerouting CP 0.80 (D3-A, 99 boards) and 0.78 (D3-B, **10 boards**); KRT 0.74 and 0.20; OrthoRoute 0.02 and 0.00. The paper ran **Freerouting 2.1.0**. A GPT-5.4 agent reached 0.65 on D3-A, and PPO 0.86/0.45. | [PCBWorld arXiv v2](https://arxiv.org/html/2607.05915v2) |
| 20 | constraints_verif | TraceMaker ≈0.99/1.00/0.90 vs "about 0.7/0.7/0.2" | PRECISION | The comparison baseline was **Freerouting 2.2.4**, in single 60 s runs, self-reported by a third party. | [kicad-tools README](https://github.com/rjwalters/kicad-tools) |
| 21 | constraints_verif | Quilter PRCs cover "impedance targets, return-path continuity, bypass-cap placement, switching-converter layout, diff-pair integrity and trace width for current" | PRECISION | The docs name exactly **8 PRCs**: Ground Plane Overlap, Invalid Width Span, Layer Switch Count, Length Mismatch, Overheated Length, Pin Distance, Trace Path Length and Uncoupled Spacing. Timing-sensitive (DDR length-match) signals are "coming soon". | [PRC overview](https://docs.quilter.ai/physics-rule-checks-prcs/overview.md); [docs index](https://docs.quilter.ai/llms.txt) |
| 22 | constraints_verif | "Cypress (ISPD 2025) could not be confirmed" | **CORRECTED** | Confirmed: [NVlabs/Cypress](https://github.com/NVlabs/Cypress), Apache-2.0; DOI 10.1145/3698364.3705346, ISPD '25, pp. 31–41. The abstract claims 1–5.9× routability, 1–19.7× shorter routed length and up to 492.3× GPU speedup. The repo ships benchmarks `small-1` … `small-20`. | [Crossref/DOI](https://doi.org/10.1145/3698364.3705346); [OpenAlex abstract](https://api.openalex.org/works/doi:10.1145/3698364.3705346); [benchmarks dir](https://github.com/NVlabs/Cypress/tree/main/benchmarks) |
| 23 | solver_toolbox | Freerouting CLI `-us greedy\|global\|hybrid`, `-is sequential\|random\|prioritized`, `-hr` | **CORRECTED** | v2.5.0 **removed** `-hr` and the values `RANDOM`, `GREEDY` and `HYBRID`. Use `-us GLOBAL_OPTIMAL` with `-is SEQUENTIAL` or `-is PRIORITIZED`. The repo's `command_line_arguments.md` still documents the removed options, so that doc is stale. | [v2.5.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0); [command_line_arguments.md](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md) |
| 24 | solver_toolbox | Freerouting "Java JRE 25 recommended" | PRECISION | Still true for the JAR (v2.4.1 moved to Java 25). v2.5.0 also ships GraalVM native binaries (Linux x64, macOS arm64/x64, Windows x64) that need no JRE. The v2.5.0 notes say "legacy KiCad SWIG support will be removed in the next release". | [v2.5.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0); [releases](https://github.com/freerouting/freerouting/releases) |
| 25 | existing_tools | Freerouting Docker images for amd64, arm64 and arm/v7 | **CONFLICT** | The README still lists `linux/arm/v7`. The v2.2.2 release notes say the arm/v7 image was dropped. | [README](https://github.com/freerouting/freerouting); [releases (v2.2.2)](https://github.com/freerouting/freerouting/releases) |
| 26 | existing_tools | Freerouting v2.5.0 details (31%→75% clean on 1,157 boards, IPC, REST, MCP, compact DRC, V2 scores) | VERIFIED | Table: v2.4.1 had 358 clean (30.9%) and v2.5.0 has 868 (75.0%). Fully routed went from 600 to 872 (75.4%). Timeouts stayed at 78. Total time fell from 3,251 s to 2,997 s. `normalized_score` is now a 0–1000 scale. | [v2.5.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0) |
| 27 | solver_toolbox | Topola main repository at `codeberg.org/mikolaj/topola` | **CORRECTED** | The official repo is **codeberg.org/topola/topola**, with a GitHub mirror at mikwielgus/topola. Crates: `specctra-core`, `topola-cli`, `topola-egui` and `planar-incr-embed`. Version 0.1.0, MIT. 33 stars; last updated 2026-08-09. | [Codeberg](https://codeberg.org/topola/topola); [README (mirror)](https://github.com/mikwielgus/topola); [Codeberg API](https://codeberg.org/api/v1/repos/topola/topola) |
| 28 | solver_toolbox | "Cypress README does not describe rotation or double-sided handling" | PRECISION | `dreamplace/params.json` has `enable_rotation` (**default 0**). The PCB converter keeps each part's TOP/BOTTOM side, writing Bookshelf orientation `N` for top and `FN` for bottom, and can mark parts `/FIXED`. No side-assignment (flip-optimization) parameter was found. | [params.json](https://github.com/NVlabs/Cypress/blob/main/dreamplace/params.json); [bookshelf_converter.py](https://github.com/NVlabs/Cypress/blob/main/pcb-util/bookshelf_converter.py) |
| 29 | existing_tools | mixelpixx KiCAD-MCP-Server: "No placement or routing algorithms are described" | **CORRECTED** | The README lists `suggest_placement` ("connectivity-driven PCB placement optimizer (dry-run by default, deterministic)"), `route_pad_to_pad` (with via insertion) and Freerouting `autoroute`/`import_ses`. Version v2.8.2: "244 tools registered", "184 tools … 17 categories". MIT. 2.9k stars. | [README](https://github.com/mixelpixx/KiCAD-MCP-Server); [repo page](https://github.com/mixelpixx/KiCAD-MCP-Server) |
| 30 | existing_tools | Konnect: 1,339 stars, 241 open issues, 228 tools / 21 toolsets (About says 217) | VERIFIED / CHANGED | AGPL-3.0 with commercial licences; "228 tools across 21 on-demand toolsets"; About says 217. On 2026-10-20 the page showed **1.3k stars and 184 issues** (not 241). The KiCAD-MCP-Server README says Konnect has "171 tools", so the three counts disagree. | [Konnect README](https://github.com/mixelpixx/Konnect); [KiCAD-MCP-Server README](https://github.com/mixelpixx/KiCAD-MCP-Server) |
| 31 | existing_tools | KiCadRoutingTools: 549 stars, MIT, 5,856 commits, v0.15.x; 3 Claude skills | VERIFIED + PRECISION | Stars, licence and commits match. The README cites `v0.15.13` as an example version. There are **10 skills**, not 3: `/pcb-free-agent`, `/plan-pcb-routing`, `/analyze-power-nets`, `/find-high-speed-nets`, `/identify-diff-pairs`, `/recommend-stackup`, `/recommend-plane-mappings`, `/diagnose-routing-failures`, `/review-routed-board` and `/stress-test-router`. | [repo](https://github.com/drandyhaas/KiCadRoutingTools); [docs/claude-skills.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/claude-skills.md) |
| 32 | existing_tools | DeepPCB plugin: SWIG vs IPC unknown; README says KiCad 6.0+, a vendor page says 10.0+ | **RESOLVED** | The plugin is a **SWIG `pcbnew.ActionPlugin`** (`import pcbnew` in `deeppcb_plugin.py`). `APP_VERSION = "1.2.0"`, `API_URL = "https://api.deeppcb.ai/api/v1"`, and a chat panel (Cooper) is in the code. The 6.0+ vs 10.0+ conflict remains (README vs vendor page). SWIG plugins will stop working in KiCad 11. | [deeppcb_plugin.py](https://github.com/instadeepai/deeppcb-kicad-plugin/blob/main/deeppcb_plugin.py); [config.py](https://github.com/instadeepai/deeppcb-kicad-plugin/blob/main/config.py); [README](https://github.com/instadeepai/deeppcb-kicad-plugin); [DeepPCB KiCad page](https://deeppcb.ai/kicad-autorouter-alternative/) |
| 33 | existing_tools | DeepPCB pricing: 1 h $0.99, 4 h $3.49, 12 h $9.99, 24 h $18.99; "1 Free Board each day" | **CORRECTED** | Current packages: **1 h $30**, **10 h $280** and **30 h $800**, plus an Enterprise tier. The free trial is **30 minutes**: 1 board, ≤4 layers, ≤150 airwires, ≤100 components, ≤2,200 pins. Paid tiers allow ≤8 layers, ≤1,200 airwires, ≤1,000 components and ≤2,200 pins. | [deeppcb.ai/pricing](https://deeppcb.ai/pricing) |
| 34 | existing_tools | DeepPCB "27,721 Boards, 95.6% Hit 95%+ Completion" | VERIFIED | The page adds "11,000+ KiCad users" and a "Median 96.9%". All figures are self-reported. | [DeepPCB page](https://deeppcb.ai/kicad-autorouter-alternative/) |
| 35 | existing_tools | Quilter "best results at 100–1,000 components, 2,000–5,000 pins, pin density <20%" (from third-party summary) | PRECISION | The docs recommend **"<5,000 pins"**, low-to-medium density (">20% pin density" is "best handled manually"), signals **<6 GHz**, **≤48 V** and **≤10 A**. No component-count range appears in the docs. | [What Quilter does well](https://docs.quilter.ai/about-quilter/what-quilter-does-well.md) |
| 36 | existing_tools | Quilter free tier for <10 people and <$50K revenue; may train on designs | VERIFIED | The free-tier page says "Eligible if less than 10 people, less than $50K revenue" and that it uses board metadata or inputs to "generate training puzzles". Paid tiers: "never used for direct or indirect training". | [Quilter free tier](https://www.quilter.ai/free-ai-pcb-design); [FAQ](https://docs.quilter.ai/about-quilter/faq.md) |
| 37 | existing_tools | "Quilter publishes no API (none found)" | NOT FOUND (still) | The docs index, FAQ and pricing pages describe web upload and review, cloud or self-hosted on Kubernetes/Helm, and "custom integrations" for enterprise, but **no public API**. | [docs index](https://docs.quilter.ai/llms.txt); [pricing](https://www.quilter.ai/pricing) |
| 38 | existing_tools | Flux Auto-Layout "does no placement" | **OUTDATED** | Auto-Layout launched in Dec 2024 as routing-only: "simply place your components and hit the Auto-Layout button". In Aug 2026 Flux said its agent handles placement requests ("moving a connector to one side of the board") and "iterates toward a fully placed, manufacturable design". It also launched a **public Flux MCP server**. | [Flux intro (Dec 2024)](https://www.flux.ai/p/blog/introducing-ai-auto-layout); [Flux Aug 2026 update](https://www.flux.ai/p/blog/summer-2026-updates-flux-mcp-server-and-chat-mode) |
| 39 | netlist_datasheet | KiCad diff-pair suffix "must be the last character" | **CORRECTED** | `MatchDpSuffix` scans from the end and **skips trailing digits and `_`**, then needs `+`, `-`, `P` or `N` (uppercase only). So `LANE_P_0` pairs with `LANE_N_0`, and `USB_DP` pairs with `USB_DN`. Lowercase `p`/`n` is not recognized. `XTAL_P`/`XTAL_N` *is* paired, which confirms the false-positive hazard. The router and DRC share this logic. | [drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp); [board.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/board.cpp) |
| 40 | netlist_datasheet | KiCad 9 expression `A.ComponentClass == '…'` | VERIFIED (both forms) | `ComponentClass` is special-cased in the evaluator. `Component_Class` also resolves, because generic properties map `_`→space, case-insensitively. | [pcbexpr_evaluator.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_evaluator.cpp) |
| 41 | netlist_datasheet / constraints | kicad-happy "60+ detectors" vs "40" | CONFLICT (verified as inconsistent) | Four counts appear: README "40 detectors total" (domain row); how-it-works "60+ signal, domain, validation, and audit detectors"; a methodology link labelled "40 signal and domain detectors"; and the methodology body, where `analyze_signal_paths()` "orchestrates 21 detector functions". Vref data also differs: "~65 Vref families" (README) vs "~60 part families" (how-it-works). | [README](https://github.com/aklofas/kicad-happy); [how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md); [methodology_schematic.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md) |
| 42 | constraints_verif | kicad-happy corpus 5,800+ repos, 3,498 PCB files | VERIFIED | Corpus: "Repos in corpus 5,800+", "PCB files analyzed 3,498 (99.9%)". Current release v2.3.1, though the README also says stable is "currently v2.1.0". | [README](https://github.com/aklofas/kicad-happy) |
| 43 | existing_tools | Cadence Allegro X AI (2023): placement, metal pour, critical-net routing, cloud, >10× | VERIFIED (2023 claims) | No 2026 Cadence update was found. Cadence distributors now present it as Placement AI, copper-pour AI and Route AI ("Full Board Routing Closure") inside Allegro X / OrCAD X. cadence.com returned 403. | [BusinessWire 2023](https://www.businesswire.com/news/home/20230406005098/en/Cadence-Introduces-Allegro-X-AI-Accelerating-PCB-Design-with-More-Than-10X-Reduction-in-Turnaround-Time); [EMA](https://www.ema-eda.com/allegro-x-ai/); [FlowCAD](https://www.flowcad.com/en/x-ai-overview.htm) |
| 44 | existing_tools | Zuken AIPR: Basic Brain and Smart Autorouter Q1 2024; Dynamic/Autonomous Brain later | NOT FOUND (status) | Only the 2023 announcement could be found; zuken.com returned 403. There is no evidence that Dynamic or Autonomous Brain has shipped. | [Zuken press release (iConnect007 reprint)](https://www.iconnect007.com/article/137836/zuken-introduces-aipr-for-cr8000-empowering-pcb-designers-with-innovative-aipowered-place-and-route-technology/137833/pcb) |
| 45 | existing_tools | tscircuit capacity-autorouter MIT, npm 0.0.995 (2026-10-20) | VERIFIED | The LICENSE file is MIT; the npm registry metadata has no licence field. Latest version 0.0.995, published 2026-10-20 17:26 UTC. | [LICENSE/README](https://github.com/tscircuit/tscircuit-autorouter); [npm](https://www.npmjs.com/package/@tscircuit/capacity-autorouter) |
| 46 | existing_tools | OrthoRoute MIT, v1.0.0, KiCad 10+ IPC; PCBWorld 1%/30% (D2), 2%/51% (D3-A) | VERIFIED (+ minor conflict) | The README says this. Paper v2 Table 3 gives routability **0.34 (D2) and 0.53 (D3-A)** at @5; the README's 30% and 51% probably come from an earlier version or from @1. | [OrthoRoute README](https://github.com/bbenchoff/OrthoRoute); [PCBWorld v2](https://arxiv.org/html/2607.05915v2) |
| 47 | solver_toolbox | "122 actions added, 47 removed between 9.0 and 10.0 (third-party)" | NOT FOUND | Not verifiable from a primary source in this pass. | — |

### Inferences
- The notes' main architectural conclusion still holds. KiCad 10 IPC is good for live CRUD with undo but is not a rules-or-routing engine; KiCad 11 adds headless mode, design rules over IPC, DSN/SES and export jobs. Several implementation-level details were wrong, though: stackup writes, zone refill semantics, SES import semantics and DRC units. Any code written from the old notes would have hit these bugs.
- Vendor facts go stale fast. DeepPCB pricing changed roughly 30-fold per hour, and Flux added placement and MCP within 2026. Treat commercial facts as perishable; re-check them before citing.

### Gaps
- Exact star counts for several repos come from rounded page values ("2.9k"). The GitHub API was blocked in this session, and the counts were not re-verified for repos not listed above.
- The Flux docs page `docs.flux.ai/tutorials/auto-layout` now renders client-side, and its `.md` variant returns "Not Found". The earlier notes' Flux doc quotes (seven priority buckets, "not designed to fully autoroute every class of board") could not be re-verified.

---

## 2. KiCad 10.x custom DRC rules: complete reference for a constraint compiler

### Takeaway
KiCad 10's `.kicad_dru` language has the following parts:
- **Constraints.** 35 constraint keywords are parsed in 10.0 (34 documented, plus the undocumented `solder_mask_sliver`), plus 3 deprecated aliases.
- **Functions.** 28 registered functions: 23 current (22 documented, plus the undocumented `intersectsKeepout`) and 5 deprecated.
- **Properties.** Any registered `PROPERTY` of a board item can be read, with spaces written as underscores.
- **Severities.** Four severities, plus a `layer` clause.

`length` and `skew` accept time units (`ps`/`fs`). Master (KiCad 11) adds net-chain constraints (`net_chain_length`, `stub_length`, `return_path`), `microvia_stack_depth`, `hole_aspect_ratio`, six functions, and a structured `CustomRule` protobuf. A compiler should:
1. emit only `mm/mil/in/deg/ps/fs` units;
2. put one condition per rule, because a second `condition` silently replaces the first;
3. use at most one constraint of each type per rule;
4. order rules general-to-specific, because the last match wins;
5. map violations back to rules through `type` keys plus parsing of the `description` string. The JSON report has no rule-name field.

### Cited Findings

#### 2.1 File format and grammar (10.0)
- The file is `<project>.kicad_dru` and must begin with `(version 1)`: "As of KiCad 10.0, the version is `1`." Rules are "evaluated in reverse order", and the first match wins, so more specific rules go **later** in the file. Comments start with `#`. Text variables (`${var}`) are substituted before parsing; object-dependent variables such as `${LAYER}` cannot be resolved and cause syntax errors. — [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc) (rendered: [docs.kicad.org 10.0 custom rules](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom-design-rules))
- Rule form: `(rule <name> [(severity <s>)] [(layer <layer>|outer|inner)] [(condition "<expr>")] (constraint <type> …)…)`. Parser behaviour:
  - A **second `condition` clause overwrites the first**; `rule->m_Condition` is reassigned.
  - A second `layer` clause is an error.
  - Each constraint type may appear **once per rule** ("Rule already has a '%s' constraint").
  - In `.kicad_dru`, only `(version …)` and `(rule …)` are valid top-level statements ("expected rule or version"). A separate parser entry point, `ParseComponentClassAssignmentRules`, handles `(assign_component_class <name> (condition …))` statements for Board Setup component-class assignment rules.

  — [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp)
- Severity is one of `error|warning|ignore|exclusion`. An `ignore` rule is still evaluated and "can still override previous rules". `ignore` rules are not observed by the interactive router; errors, warnings and exclusions are. — [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc)
- Conditions are evaluated against object pairs `A` and `B`; both orderings are tested. `AB.` is used for pair functions. The operators `== != > >= < <= && || !` all have equal precedence and evaluate **left to right**. Booleans are tested bare (`A.Do_not_populate`), and there are no `true`/`false` literals. `null` can be compared for nullable properties. Without a unit suffix a value is in internal units (nm, or degrees for angles). — [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc)
- **Units accepted by the source:** `mil, mm, in, deg, fs, ps` ("must be mm, in, mil, deg, fs, or ps"). Time units on any constraint other than `length`/`skew` raise "Time based units not allowed for constraint type"; mixing time and length within one constraint raises "Mixed units". The docs also list `th`, `"` and `rad`, which the resolver does not contain (see Corrections #17). — [pcbexpr_evaluator.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_evaluator.cpp); [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp)

#### 2.2 Constraint types parsed by KiCad 10.0
Column key:
- **Args:** argument shape.
- **Units:** "len" means length units; "time" means `ps`/`fs`.
- **Router/tuner:** whether the interactive router or length tuner uses the `opt` value.
- **DRC `type` key:** the value written into the JSON report.

Sources: [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp) (types, args and time-domain flag); [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc) (semantics); [drc_item.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp) and the [drc_test_provider_*.cpp](https://gitlab.com/kicad/code/kicad/-/tree/10.0/pcbnew/drc) files (keys emitted).

| Constraint | Args | Units | Router/tuner uses `opt` | DRC `type` key(s) emitted | Semantics / gotchas |
|---|---|---|---|---|---|
| `annular_width` | min/max | len | – | `annular_width` | Annular ring of vias and pads |
| `assertion` | `"bool expr"` | – | – | `assertion_failure` | Single-object predicate. The graphical editor's "Permitted layers" and "Allowed orientation" compile to this. |
| `bridged_mask` | (none) | – | – | `solder_mask_bridge` | Use with `severity` to allow or disallow mask bridging |
| `clearance` | min | len (negative min ⇒ overlap allowed) | honoured by router | `clearance`, `hole_clearance`, `shorting_items`, `tracks_crossing`, `zones_intersect` | Electrical clearance between **different nets** |
| `connection_width` | min | len | – | `connection_width` | Narrowest copper connection, including zone necks |
| `courtyard_clearance` | min | len (negative ⇒ overlap allowed) | – | `courtyards_overlap` (+ `missing_courtyard`, `malformed_courtyard`, `pth_inside_courtyard`, `npth_inside_courtyard`) | Footprints without a courtyard produce no error |
| `creepage` | min | len | – | `creepage` | Surface path between nets |
| `diff_pair_gap` | min/opt/max | len | `opt` = router gap for new pairs | `diff_pair_gap_out_of_range` | Not tested on non-parallel parts (fan-out) |
| `diff_pair_uncoupled` | max | len | – | `diff_pair_uncoupled_length_too_long` | Uncoupled = not parallel, or outside the `diff_pair_gap` range. Since 10.0.4, tuning patterns are excluded from the total. |
| `disallow` | tokens `track via through_via blind_via buried_via micro_via pad zone text graphic hole footprint` | – | – | `items_not_allowed` (`text_on_edge_cuts`) | `via` means **all** via types; it is a finer-grained keepout |
| `edge_clearance` | min | len (negative ⇒ allowed) | – | `copper_edge_clearance`, `silk_edge_clearance` | Edge = Edge.Cuts graphics **and oval pad holes** (the "milling tolerance") |
| `hole_clearance` | min | len | – | `hole_clearance` | Drilled hole to copper of another net |
| `hole_size` | min/opt/max | len | `opt` = router default via drill | `drill_out_of_range`, `microvia_drill_out_of_range` | Oval holes: minor axis against min, major axis against max |
| `hole_to_hole` | min | len | – | `hole_to_hole`, `holes_co_located` | Mechanical drills only; laser and milled holes are not checked |
| `length` | min/opt/max | len **or time** | `opt` = length-tuner target | `length_out_of_range` | Per net, or per `fromTo` path. Time units force time-domain tuning. |
| `min_resolved_spokes` | bare integer 0–4 (no min/max wrapper) | – | – | `starved_thermal` | Spoke count to a zone |
| `physical_clearance` | min | len | enforced by router since 10.0.4 | reported as **`clearance`** / **`hole_clearance`** | Net-agnostic, same layer only, except Edge.Cuts, which counts as on all layers. "Much slower". |
| `physical_hole_clearance` | min | len | enforced by router since 10.0.4 | `hole_clearance` | Round holes only (the "drilling tolerance") |
| `silk_clearance` | min | len (negative ⇒ allowed) | – | `silk_overlap`, `silk_over_copper` | Silk to other objects |
| `skew` | min/opt/max + optional `(within_diff_pairs)` | len **or time** | target = `opt`, else `min`, else 0 | `skew_out_of_range` | Without the option, skew is across all matching nets (bus). With it, skew is tested within each diff pair. |
| `solder_mask_expansion` | opt | len | – | – | Sets expansion on pads, shapes and tracks |
| `solder_mask_sliver` | generic min/opt/max parser path (the editor shows a minimum) | len | – | (no dedicated key found) | **Undocumented** in the 10.0 table. It appears in the graphical editor as "Minimum soldermask silver" [sic]. |
| `solder_paste_abs_margin` | opt | len | – | – | Absolute paste margin; final value = absolute + relative |
| `solder_paste_rel_margin` | opt | ratio | – | – | Relative paste margin |
| `text_height` | min/max | len | – | `text_height` | Includes text boxes |
| `text_thickness` | min/max | len | – | `text_thickness` | |
| `thermal_relief_gap` | min | len | – | – (sets fill geometry; the zone-connections provider reads it while testing `starved_thermal`) | |
| `thermal_spoke_width` | opt | len | – | – | |
| `track_angle` | min/max | deg (unitless resolver) | – | `track_angle` | Angle between connected segments |
| `track_segment_length` | min/max | len | – | `track_segment_length` | Per segment or arc |
| `track_width` | min/opt/max | len | `opt` = router default width | `track_width` | |
| `via_count` | min/max | integer (unitless) | – | `too_many_vias` | Per net (or per path) |
| `via_dangling` | (none) | – | – | `via_dangling` | Use with `severity` |
| `via_diameter` | min/opt/max | len | `opt` = router default via diameter | `via_diameter` | |
| `zone_connection` | `solid` \| `thermal_reliefs` \| `none` | – | – | – | Sets the pad-to-zone connection |
| deprecated aliases | `mechanical_clearance` → `physical_clearance`; `mechanical_hole_clearance` → `physical_hole_clearance`; `hole` → `hole_size` | | | | The parser accepts them with a deprecation warning |

Notes:
- The internal `DIFF_PAIR_INTRA_SKEW_CONSTRAINT` exists in the enum, but no keyword creates it; `skew … (within_diff_pairs)` sets an option instead. — [drc_rule.h @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule.h)
- The `diff_pair_coupling` and `matched_length` providers can both emit `too_many_vias`. — [drc_test_provider_matched_length.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_test_provider_matched_length.cpp)
- The router changes for `physical_clearance` and `physical_hole_clearance` arrived in 10.0.4 ("Enforce physical_clearance rules in the interactive router"; "Fix physical_hole_clearance not being enforced in the interactive router"). — [10.0.4 notes](https://www.kicad.org/blog/2026/06/KiCad-10.0.4-Release/)

#### 2.3 Constraints added on master only (KiCad 11 development; not in 10.x)
| Constraint | Args / syntax | Time units | Notes | Source |
|---|---|---|---|---|
| `microvia_stack_depth` | max (unitless) | no | Microvia stacking depth. DRC keys `microvia_stack_depth`, `malformed_microvia_stack_span`, `microvia_crosses_core`, `microvia_stack_not_filled`. | [drc_rule_parser.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_rule_parser.cpp); [drc_item.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_item.cpp) |
| `hole_aspect_ratio` | max (ratio; the proto stores thousandths) | no | Documented on master as `microvia_aspect_ratio`, which is not a parser keyword. Now applies to every plated hole (commit 2026-10-12). | [keywords @master](https://gitlab.com/kicad/code/kicad/-/blob/master/common/drc_rules.keywords); [board_rules.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_rules.proto) |
| `net_chain_length` | min/opt/max | **yes** | Net chains, undocumented | [drc_rule_parser.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_rule_parser.cpp) |
| `stub_length` | min/opt/max | **yes** | Net-chain stub length | same |
| `return_path` | `(constraint return_path (layer "B.Cu") (net "GND"))` | – | Reference-plane check for net chains; DRC key `net_chain_return_path` | same; [board_rules.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_rules.proto) |

#### 2.4 Expression functions
**10.0, from the registration list in [pcbexpr_functions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_functions.cpp), with semantics from [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc):**

| Function | Object | Semantics |
|---|---|---|
| `enclosedByArea('x')` | A/B | Entire object inside the named rule area or zone. Slower than `intersectsArea`. |
| `existsOnLayer('L')` | A/B | Object exists on the layer |
| `fromTo('x','y')` | A/B | Object lies on the copper path between pads `RefDes-PadNumber` (or `RefDes` for all pads). `*`/`?` wildcards; matching is **case-insensitive**. The path must be uniquely determinable, otherwise it is not created. Typically used with `length`, `skew`, `track_width`, `clearance` and `diff_pair_gap`. |
| `getField('x')` | A/B | Field value; only footprints have fields |
| `hasComponentClass('x')` | A/B | The component-class set of the object **or its parent footprint** contains x |
| `hasExactNetclass('x')` | A/B | The net-class set equals x |
| `hasNetclass('x')` | A/B | The net-class set contains x |
| `inDiffPair('base')` | A/B | Object is in a *valid* pair whose base name matches; wildcards allowed. False if the complement net does not exist. |
| `intersectsArea('x')` | A/B | Any part inside the named rule area or zone. For a filled copper zone the test uses the fill, not the outline. |
| `intersectsCourtyard('x')`, `intersectsFrontCourtyard('x')`, `intersectsBackCourtyard('x')` | A/B | x is a refdes wildcard, a `lib:footprint` wildcard, or `${Class:Name}` |
| `intersectsKeepout('x')` | A/B | **Undocumented.** Shares its implementation with `intersectsArea`, with a keepout flag set. |
| `isBlindVia()`, `isBuriedVia()`, `isBlindBuriedVia()`, `isMicroVia()` | A/B | Via type tests |
| `isCoupledDiffPair()` | **AB** | A and B are opposite polarities of the same pair |
| `isPlated()` | A/B | Plated hole |
| `memberOfGroup('x')` | A/B | Member of the named group |
| `memberOfFootprint('x')` | A/B | Refdes wildcard, `lib:fp` wildcard, or `${Class:Name}` |
| `memberOfSheet('x')` | A/B | Exact sheet path (wildcards allowed); child sheets excluded |
| `memberOfSheetOrChildren('x')` | A/B | Sheet path including children |
| Deprecated | | `insideArea`, `insideCourtyard`, `insideFrontCourtyard`, `insideBackCourtyard`, `memberOf` (still registered, marked DEPRECATED) |

**Master-only:** `customProperty('x')`, `hasCustomProperty('x')`, `hasNetChain()`, `inNetChain('x')`, `inNetChainClass('x')`, `isStackedVia()`. — [pcbexpr_functions.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/pcbexpr_functions.cpp)

#### 2.5 Object properties
- **Documented in 10.0.**
  - Common: `Layer`, `Locked`, `Parent`, `Position_X`, `Position_Y`, `Type`.
  - Connected items: `Net`, `NetClass` (priority-ordered comma list; equality matches any member or the full list), `NetName`, plus teardrop properties.
  - Footprint (inherited by children): `Clearance_Override`, `Component_Class`, `Do_not_Populate`, `Exclude_From_Position_Files`, `Exclude_From_Bill_of_Materials`, `Exempt_From_Courtyard_Requirement`, `Keywords`, `Library_Description`, `Library_Link`, `Not_in_Schematic`, `Orientation`, `Reference`, solder-paste overrides, thermal settings, `Value`, `Zone_Connection_Style`.
  - Pad: `Fabrication_Property`, `Hole_Size_X/Y`, `Pad_Number`, `Pad_Shape`, `Pad_To_Die_Length`, `Pad_Type`, `Pin_Name`, `Pin_Type` (with a `+no_connect` suffix), `Size_X/Y`, plus others.
  - Track: `Origin_X/Y` (aliased to `Start_X/Y`), `End_X/Y`, `Width`.
  - Via: `Diameter`, `Hole`, `Layer_Top`, `Layer_Bottom`, `Via_Type`.
  - Tuning pattern: `Tuning_Mode`, `Target_Length`, `Target_Skew`, and others.
  - Zone and rule area: `Name`, `Priority`, `Pad_Connections`, hatch properties, and others.
  - Graphic shapes and text.

  — [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc)
- **Resolution rule.** Any `PROPERTY` registered on a `BOARD_ITEM` subclass can be read. The field name has `_` replaced by a space and is looked up in the property manager. `NetClass`, `ComponentClass`, `NetName` and `Type` have fast paths. — [pcbexpr_evaluator.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcbexpr_evaluator.cpp)
- **Undocumented properties found in 10.0 source (partial scan).**
  - Pad: `Pad_To_Die_Delay` (time domain), backdrill and post-machining properties (`Backdrill_Mode`, `Top_Post-machining`, …), `Hole_Shape`.
  - Via: tenting, plugging, covering, filling and capping properties.
  - Zone and rule area: `Keep_Out_Tracks`, `Keep_Out_Vias`, `Keep_Out_Pads`, `Keep_Out_Zone_Fills`, `Keep_Out_Footprints`, `Source_Type` and `Source_Name` (the multichannel placement source), `Remove_Islands`, `Minimum_Island_Area`.
  - Tuning pattern: `Target_Skew_Delay`.

  — [pad.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pad.cpp), [pcb_track.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/pcb_track.cpp), [zone.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/zone.cpp), [pcb_tuning_pattern.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/generators/pcb_tuning_pattern.cpp) (all @10.0)

#### 2.6 Graphical rule editor (KiCad 10)
- Opened from Tools → Design Rule Editor. It writes the same `.kicad_dru` and is interchangeable with the text editor.
- Five categories:
  - Electrical: min clearance, copper-to-edge, courtyard, physical, creepage, connection width, copper-to-hole, thermal spoke count.
  - Manufacturability: annular, drill, hole-to-hole, via style with a via-type filter, text, silk-to-silk, silk-to-mask, mask sliver, mask expansion, paste expansion.
  - Highspeed: routing width, max via count, diff-pair skew, matched-length diff pair with gap, absolute length.
  - Footprints: permitted layers, allowed orientation (0/90/180/270), vias under SMD.
  - Custom: raw syntax.
- Condition rows offer Any, Net, Netclass, Within Area and Custom Query, combined left-to-right with AND, OR, AND NOT or OR NOT.
- "Permitted layers" and "Allowed orientation" are implemented as `assertion` and report as "Assertion violation".

— [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc). 10.0.7 fixed "the DRC rule editor breaking time domain rules" and allowed it to edit picosecond length rules. — [10.0.7 notes](https://www.kicad.org/blog/2026/10/KiCad-10.0.7-Release/)

#### 2.7 Tuning profiles and time-domain constraints (KiCad 10)
- A tuning profile is Single or Differential. Per signal layer it holds Track Width, Unit Delay (e.g. ps/mm) and, for differential profiles, Diff Pair Gap. Via propagation has a global unit delay plus per-layer-pair absolute overrides.
- Profiles are assigned per net class. The router then uses the profile's width and gap per layer, and the tuner uses its delays when "Enable time domain tuning" is checked. DRC can flag tracks that don't match their profile; the keys are `missing_tuning_profile` and `tuning_profile_track_geometries`.

— [pcbnew_create_board.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_create_board.adoc); [drc_item.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp)

- Related fixes: 10.0.5 "Keep tuning profile from always implying time domain tuning"; 10.0.7 "Allow a DRC length tolerance as large as the optimum length". — [10.0.5 notes](https://www.kicad.org/blog/2026/07/KiCad-10.0.5-Release/); [10.0.7 notes](https://www.kicad.org/blog/2026/10/KiCad-10.0.7-Release/)

#### 2.8 Verified syntax snippets for the items the brief asked about (10.0)
```lisp
(version 1)
# length / time-domain length (time units force time-domain tuning)
(rule "DDR_CLK len"   (condition "A.fromTo('U1-C5','U2-D3')") (constraint length (min 20mm) (max 25mm)))
(rule "USB delay"     (condition "A.inDiffPair('/USB')")      (constraint length (max 500ps)))
# skew across a bus vs within each diff pair
(rule "DQ skew"       (condition "A.fromTo('U1-A*','U2-B*')") (constraint skew (max 0.2mm)))
(rule "USB intra"     (condition "A.inDiffPair('/USB*')")     (constraint skew (max 5ps) (within_diff_pairs)))
# diff pair geometry
(rule "Clock gap"     (condition "A.inDiffPair('/CLK')")      (constraint diff_pair_gap (min 0.12mm) (opt 0.15mm) (max 0.2mm))
                                                               (constraint diff_pair_uncoupled (max 3mm)))
(rule "DP clearance"  (condition "A.inDiffPair('*') && !AB.isCoupledDiffPair()") (constraint clearance (min 1.5mm)))
# via count, edge, physical, courtyard
(rule "HS vias"       (condition "A.hasNetclass('HS')")       (constraint via_count (max 2)))
(rule "edge"          (constraint edge_clearance (min 0.5mm)))
(rule front_courtyard_to_edge (layer "F.Courtyard") (condition "B.Layer == 'Edge.Cuts'") (constraint physical_clearance (min 3mm)))
(rule "TP spacing"    (condition "A.Reference == 'TP*' && B.Reference == 'TP*'") (constraint courtyard_clearance (min 1.5mm)))
```
- The `length`, `skew`, `fromTo`, clock-gap, DP-clearance, courtyard-to-edge and TP-spacing forms are copied from the 10.0 docs' examples. The `(within_diff_pairs)` parenthesized form follows from the parser, which reads a `(` token and then `within_diff_pairs` followed by `)`. The `500ps` form is from the tuning-profile NOTE. — [pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc); [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp); [pcbnew_create_board.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_create_board.adoc)

#### 2.9 `kicad-cli pcb drc` flags and JSON schema (10.0, unchanged on master)
- Usage: `kicad-cli pcb drc [-o OUT] [-D KEY=VALUE]... [--format report|json] [--all-track-errors] [--schematic-parity] [--units mm|in|mils] [--severity-all|--severity-error|--severity-warning|--severity-exclusions] [--exit-code-violations] [--refill-zones] [--save-board] INPUT`.
- `--exit-code-violations` makes the exit code **5** when violations exist (0 otherwise).
- Zones are not refilled unless `--refill-zones` is given, and the board is saved only with both `--refill-zones` and `--save-board`.

— [cli.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/cli/cli.adoc) ([rendered](https://docs.kicad.org/10.0/en/cli/cli.html)). The 10.0 and master DRC sections are byte-identical.

- **JSON schema `drc.v1.json`.** Top level:
  - `$schema`, `source`, `date`, `kicad_version`
  - `violations[]`, `unconnected_items[]`, `schematic_parity[]`
  - `coordinate_units` (`mm|mils|in`)
  - `included_severities[]` (`error|warning|exclusion`)
  - `ignored_checks[]` (`{key, description}`)

  Each violation has `type` (the settings key), `description`, `severity` (`error|warning`), `items[]` (`{uuid, description, pos{x,y}}`), `excluded` and `comment`. The 10.0 schema file has a trailing comma in `required` (invalid strict JSON), and master's file is identical. — [drc.v1.json @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/resources/schemas/drc.v1.json)
- **There is no rule-name field in JSON.** `description` = `GetErrorMessage()` = error title + detail, e.g. `"Clearance violation (<source> clearance 0.2000 mm; actual 0.1500 mm)"`, where `<source>` is the constraint's name (rule or net class). Only the text `.rpt` adds `GetViolatingRuleDesc()`. — [rc_item.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/rc_item.cpp); [rc_item.h @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/include/rc_item.h); [drc_test_provider_copper_clearance.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_test_provider_copper_clearance.cpp)
- **All 67 DRC `type` keys in 10.0:** `unconnected_items, shorting_items, items_not_allowed, text_on_edge_cuts, clearance, creepage, tracks_crossing, copper_edge_clearance, zones_intersect, isolated_copper, starved_thermal, via_dangling, track_dangling, hole_clearance, hole_to_hole, holes_co_located, connection_width, track_width, track_angle, track_segment_length, annular_width, drill_out_of_range, via_diameter, padstack, padstack_invalid, microvia_drill_out_of_range, courtyards_overlap, missing_courtyard, malformed_courtyard, pth_inside_courtyard, npth_inside_courtyard, item_on_disabled_layer, invalid_outline, duplicate_footprints, missing_footprint, extra_footprint, net_conflict, footprint_symbol_mismatch, footprint_filters_mismatch, footprint_symbol_field_mismatch, lib_footprint_issues, lib_footprint_mismatch, unresolved_variable, assertion_failure, generic_warning, generic_error, copper_sliver, solder_mask_bridge, silk_over_copper, silk_edge_clearance, silk_overlap, text_height, text_thickness, length_out_of_range, skew_out_of_range, too_many_vias, diff_pair_gap_out_of_range, diff_pair_uncoupled_length_too_long, footprint, footprint_type_mismatch, through_hole_pad_without_hole, mirrored_text_on_front_layer, nonmirrored_text_on_back_layer, missing_tuning_profile, tuning_profile_track_geometries, track_on_post_machined_layer, track_not_centered_on_via`.
  - Master adds `footprint_scaled_with_pads, hole_aspect_ratio, malformed_microvia_stack_span, microvia_crosses_core, microvia_stack_depth, microvia_stack_not_filled, net_chain_return_path, net_chain_stub_length, net_chain_tuning_profiles, via_stitch_overlap` and drops `zones_intersect`.

  — [drc_item.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp); [@master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/drc/drc_item.cpp)
- Freerouting writes DRC reports in this same KiCad drc.v1 format, via `-drc` and `GET /jobs/{id}/drc`. It adds a `freerouting_version` key, which the KiCad schema's `additionalProperties:false` would reject. — [Freerouting API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md)

#### 2.10 Diff-pair naming rule
- The matcher runs from the end of the net name. It skips `[0-9_]`, then needs `+`, `-`, `P` or `N` (uppercase). The complement swaps that character and keeps the skipped suffix. The DRC engine and the router share the logic. — [drc_engine.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_engine.cpp); [board.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/board.cpp)

### Inferences
- **Compiler rules, derived from parser behaviour:**
  1. Combine all predicates into one `condition` string with explicit parentheses; operators otherwise evaluate left to right with equal precedence.
  2. Emit one rule per constraint group, never two constraints of the same type in one rule.
  3. Emit general rules first and specific rules last.
  4. Use only `mm`, `deg` and `ps` (pick canonical units).
  5. Keep a sidecar map from rule name to IR constraint ID, because JSON violations carry the rule only inside the free-text `description`.
- **Violation-type ambiguity.** `physical_clearance` violations reuse the `clearance` and `hole_clearance` keys. A feedback loop that maps DRC failures to repair actions must parse `description` for the `<source>` name. Unique rule names, such as an `IR:<id>` prefix, make this reliable.
- **What KiCad DRC can enforce in 10.0 for placement intent.** Courtyard spacing, side (`assertion` on `Layer`), orientation (`assertion` on `Orientation`), `intersectsArea`/`enclosedByArea` against named rule areas, and edge or keepout distances. What it can't express: pairwise distances between two footprints' pads, alignment, symmetry and loop area. The earlier notes' conclusion stands.
- The master net-chain constraints (`net_chain_length`, `stub_length`, `return_path` with a reference layer and net) are KiCad's first native return-path or reference-plane check. If they ship in 11.0, part of the custom "via-to-plane / return path" checker could compile to native DRC.

### Gaps
- The undocumented `solder_mask_sliver` emits no dedicated DRC key that I could find in the 10.0 test providers; how it reports was not determined.
- Whether `th`, `"` and `rad` are accepted through some other path, given that the docs claim them, was not tested by running KiCad. The finding comes from source reading only.
- Net-chain semantics on master (how a "net chain" is defined) are undocumented. Only the parser and proto were read.
- How and when the GUI reloads an externally modified `.kicad_dru` was not verified. `kicad-cli pcb drc` reads the file fresh on each run. The docs say the file "should not be edited with an external text editor".

---

## 3. KiCad IPC API coverage matrix (10.0.x vs master/KiCad 11) and related automation facts

### Takeaway
On **10.0.x** the IPC API is a GUI-attached CRUD-plus-commit interface:
- items, selection, nets and net classes (read and write), variants, text variables;
- a read-only stackup, whole-board async zone refill, pad polygons, hit-test, flip, and interactive move;
- an unstable `RunAction`.

It has no design rules, no DRC run, no export, no headless mode, no Specctra and no footprint-from-library placement.

**Master (KiCad 11)** adds:
- headless `kicad-cli api-server`;
- board design rules and structured custom rules get/set;
- netlist import and Specctra session import;
- `PlaceFootprintFromLibrary` and library commands;
- 20 board export jobs (including Specctra DSN) and schematic commands and jobs;
- cross-probing, page settings, per-zone refill.

Neither branch has a "run DRC" message, a routing or placement command, or change notifications.

### Cited Findings

#### 3.1 Coverage matrix
Sources:
- 10.0: the [api/proto tree @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/api/proto) and the handler registrations in [api_handler_pcb.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp), [api_handler_editor.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/api/api_handler_editor.cpp) and [api_handler_common.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/api/api_handler_common.cpp).
- Master: the [api/proto tree @master](https://gitlab.com/kicad/code/kicad/-/tree/master/api/proto) and [api_handler_pcb.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/api/api_handler_pcb.cpp).
- kipy: [board.py @0.8.0](https://gitlab.com/kicad/code/kicad-python/-/blob/0.8.0/kipy/board.py) and [@main](https://gitlab.com/kicad/code/kicad-python/-/blob/main/kipy/board.py).

| Capability | 10.0.x | master (11-dev) | kipy 0.8.0 (released) | kipy main (unreleased) | Notes |
|---|---|---|---|---|---|
| Connect, version, ping, binary path, plugin settings path | ✅ | ✅ (+`GetPaths`) | ✅ | ✅ | Busy or timeout errors are expected; use a single connection ([dev-docs IPC](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)) |
| Headless server | ❌ (GUI only) | ✅ `kicad-cli api-server [--socket] [file]` | ❌ | ✅ auto-launch ("Add support for launching `kicad-cli api-server`") | [for-addon-developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/); [kipy README](https://gitlab.com/kicad/code/kicad-python/-/blob/main/README.md) |
| Open, create, close documents | ❌ (`GetOpenDocuments` only) | ✅ `OpenDocument`, `CreateDocument`, `CloseDocument`, `CloseAllDocuments`, `SaveDocumentAs`, `GetDocumentModifiedState` | ❌ | ✅ (`open_document`, `create_document`, `close_document`) | [project_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/commands/project_commands.proto) |
| Save, save copy, revert, save to string | ✅ | ✅ (SaveDocument moved to project_commands) | ✅ (`save`, `save_as`, `revert`, `get_as_string`) | ✅ | |
| Commit / undo (`BeginCommit`/`EndCommit` with COMMIT/DROP) | ✅ (document header since 10.0.7) | ✅ | ✅ `begin_commit`/`push_commit`/`drop_commit` | ✅ | [editor_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto) |
| Item CRUD: `CreateItems`/`GetItems`/`GetItemsById`/`UpdateItems`/`DeleteItems` | ✅ | ✅ | ✅ | ✅ | `GetItems` types in 10.0: tracks, arcs, vias, pads, footprints, shapes, tables, text, text boxes, barcodes, reference images, dimensions, zones (incl. rule areas), groups, reference points. **No generators/tuning patterns, no DRC markers.** |
| Footprint creation | ✅ (a `FootprintInstance` must be fully specified, or created via `ParseAndCreateItemsFromString` from S-expression text) | ✅ + `PlaceFootprintFromLibrary` (Since 11.0) | create via items / string | ✅ `place_footprint_from_library` | `createItemForType` accepts `PCB_FOOTPRINT_T` in a board container ([handler @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp)) |
| Selection: get, add, remove, clear | ✅ | ✅ (+ cross-probe `SyncSelection`, `HighlightNets`, `FocusOnItem`) | ✅ | ✅ | [cross_probe_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/commands/cross_probe_commands.proto) |
| Hit test, bounding boxes | ✅ `HitTest`, `GetBoundingBox` | ✅ + `GetBoardBoundingBox` (modes all / physical / edges) | ✅ | ✅ | |
| Nets: `GetNets`, `GetItemsByNet`, `GetItemsByNetClass`, `GetConnectedItems`, `GetNetClassForNets` | ✅ (by-net, by-netclass and connected items need ≥10.0.1) | ✅ | ✅ | ✅ | [kipy changelog](https://gitlab.com/kicad/code/kicad-python/-/blob/main/README.md) |
| Net-class definitions get/set (incl. `tuning_profile` per class) | ✅ `GetNetClasses`/`SetNetClasses` | ✅ | get only (`Project.get_net_classes`) | ✅ get/set | [project_settings.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/types/project_settings.proto) |
| Net-class *assignments* (patterns) | ❌ | ✅ `Get/SetNetClassAssignments` | ❌ | ✅ (commit 2026-09-23) | [kipy commits](https://gitlab.com/kicad/code/kicad-python/-/commits/main) |
| Text variables get/set/expand | ✅ | ✅ | ✅ | ✅ | |
| Variants (8 commands) | ✅ | ✅ | not wrapped | not checked | [variant_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/variant_commands.proto) |
| Board stackup | **read only** (`UpdateBoardStackup` unhandled) | **read only** (still unhandled) | ✅ `get_stackup` | ✅ | Corrections #2 |
| Enabled layers get/set, layer names, active and visible layers, appearance | ✅ (`GetBoardLayerByName` since 10.0.6) | ✅ | ✅ | ✅ | |
| Board origin get/set, title block get/set, graphics defaults, embedded files | ✅ | ✅ (+ page settings) | ✅ (title block needs 10.0.1) | ✅ | |
| Design rules (Board Setup constraints, predefined sizes, mask/paste, teardrops, severities, exclusions) | ❌ | ✅ `Get/SetBoardDesignRules` | ❌ | ✅ | [board_rules.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_rules.proto) |
| Custom DRC rules | ❌ (write `.kicad_dru` yourself) | ✅ `Get/SetCustomDesignRules`, structured `CustomRule` (condition string, constraint enum incl. net-chain/microvia, `MinOptMax` in nm/**attoseconds**, layer, severity, name; options `SKEW_WITHIN_DIFF_PAIRS`/`TIME_DOMAIN`/`SPACE_DOMAIN`). "API: make custom rules survive a Get/Set round trip" (2026-10-20). | ❌ | ✅ | [board_rules.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_rules.proto); [commits](https://gitlab.com/kicad/code/kicad/-/commits/master/api/proto/board/board_rules.proto) |
| Run DRC / read DRC results | ❌ (only `InjectDrcError` to add markers) | ❌ (no DRC job; DRC exclusions only inside BoardDesignRules) | ❌ | ❌ | Use `kicad-cli pcb drc` |
| Zone refill | ✅ **whole board only, async** | ✅ per-zone; synchronous when headless | ✅ `refill_zones` | ✅ | Corrections #8 |
| Pad geometry: `GetPadShapeAsPolygon`, `CheckPadstackPresenceOnLayers` | ✅ | ✅ | ✅ | ✅ | |
| Flip items | ✅ `FlipItems` | ✅ | ✅ (0.8.0) | ✅ | |
| Interactive move | ✅ `InteractiveMoveItems` (hands control to the user; returns immediately; editor busy until done) | ✅ | ✅ `interactive_move` | ✅ | [board_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_commands.proto) |
| `RunAction(name)` | ✅ (returns `RAS_OK`/`RAS_INVALID` immediately; "specifically *not* an API") | ✅ | ✅ `run_action` (fixed 0.7.1) | ✅ | [editor_commands.proto @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/api/proto/common/commands/editor_commands.proto) |
| Netlist import (schematic→PCB update) | ❌ | ✅ `ImportNetlist` | ❌ | ✅ `import_netlist` | |
| Specctra DSN export | ❌ (GUI / `RunAction` / SWIG) | ✅ `RunBoardJobExportSpecctraDsn` | ❌ | not checked | [board_jobs.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto) |
| Specctra SES import | ❌ (GUI / `RunAction` / SWIG) | ✅ `ImportSpecctraSession` (Since 11.0) | ❌ | not checked | |
| Export/plot jobs | ❌ | ✅ 3D, render, SVG, DXF, PDF, PS, PNG, Gerbers, drill, position, GenCAD, Specctra DSN, IPC-2581, IPC-D-356, ODB++, stats, IDF; plot settings get/set | ❌ | ✅ `export_*` | [board_jobs.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/board/board_jobs.proto) |
| Library tables and items | ❌ | ✅ (get/add/update/delete table entries, statuses, reload, search, items) | ❌ | ✅ | [library_commands.proto @master](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/commands/library_commands.proto) |
| Schematic | ❌ (empty proto) | ✅ hierarchy, netlist, place symbol, export jobs (SVG/DXF/PDF/PS/PNG/netlist/BOM) | ❌ | ✅ initial (`get_schematic`) | |
| Routing / autoroute / autoplace commands | ❌ | ❌ | ❌ | ❌ | Only via `RunAction("pcbnew.InteractiveRouter.Autoroute")` or `"pcbnew.Autoplacer.autoplaceSelected"` ([pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp)) |
| Change notifications / event subscription | ❌ | ❌ | ❌ | ❌ | No subscribe or notify messages in the board or editor protos (grep of both trees) |

#### 3.2 Behaviour details that matter for an agent loop
- KiCad handles API calls on its single UI thread, so clients "need to anticipate that API messages may sometimes timeout or fail because KiCad is busy" and "should not open multiple connections". — [dev-docs IPC API](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)
- Limitations, verbatim from the live dev-docs: "The IPC API in KiCad 9 and 10 only supports communication with a running instance of the KiCad GUI. Support for running in headless mode through kicad-cli was added for KiCad 11." Also: "no support for plotting or exporting files … added for KiCad 11 and up". KiCad 9 and 10 support IPC plugins only in the PCB editor. — [for-addon-developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- Plugins and environment: the `KICAD_API_SOCKET` and `KICAD_API_TOKEN` environment variables; a `plugin.json` per plugin; `api.sock` in the temp directory; `EnableAPILogging=1` for request logging. — [for-addon-developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- SWIG: "The current plan is to remove the SWIG bindings in KiCad 11.0." In 10.0 it still provides stand-alone `LoadBoard`/`SaveBoard`, `ExportSpecctraDSN(board, path)`, `ImportSpecctraSES(board, path)` and `WriteDRCReport(board, file, units, ...)`. — [dev-docs pcbnew bindings](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/); [pcbnew_scripting_helpers.h @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/python/scripting/pcbnew_scripting_helpers.h)
- kicad-python: on PyPI as 0.8.0 (2026-08-30); requires `protobuf<6,>=5.29`, `pynng<0.10,>=0.9` and `jsonschema`; Python ≥3.9. `KiCad.check_version` verifies compatibility. Rendered docs are at [docs.kicad.org/kicad-python-main](https://docs.kicad.org/kicad-python-main/). — [PyPI JSON](https://pypi.org/pypi/kicad-python/json); [README](https://gitlab.com/kicad/code/kicad-python/-/blob/main/README.md)

#### 3.3 kicad-cli inventory (from the source file lists)
- **10.0:** `pcb drc`; `pcb export` {3d (STEP/GLB/PLY/STL/VRML/XAO/BREP/U3D/3D-PDF), drill, dxf, gencad, gerber, gerbers, hpgl, ipc2581, ipcd356, odb, pdf, pos, ps, stats, svg}; `pcb import`; `pcb render`; `pcb upgrade`; `sch erc`; `sch export` {bom, netlist, plot, pythonbom}; `sch upgrade`; `fp`/`sym` export-svg and upgrade; `jobset run`; `version`. — [kicad/cli @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/kicad/cli); [cli.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/cli/cli.adoc)
- **Master adds:** `api-server`, `pcb export specctra`, `pcb export idf/png/stackup`, `pcb/sch/fp/gerber diff`, `gerber info/convert png`, `pcb/sch/project downgrade`, `git_mergedriver`, `mergetool`, and a top-level `import`. — [kicad/cli @master](https://gitlab.com/kicad/code/kicad/-/tree/master/kicad/cli)
- `pcb import --format` hints in 10.0: `auto, pads, altium, eagle, cadstar, fabmaster, pcad, solidworks`. Allegro and gEDA are not named as CLI hints, even though the 10.0 release notes announce Allegro, PADS and gEDA/Lepton importers. — [command_pcb_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/kicad/cli/command_pcb_import.cpp); [10.0.0 notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)

#### 3.4 Built-in automation features and dates
- **KiCad 9.0.0 (2025-02-20)** introduced:
  - jobsets;
  - multi-channel design (Tomasz Wlostowski: "repeat PCB layout elements from one channel to create identical copies");
  - component classes, with three DRC expressions;
  - multiple net classes per net and `hasNetclass`;
  - net-class rule areas, schematic design blocks, and the IPC API.

  — [9.0.0 notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)
- **KiCad 10.0.0 (2026-03-20)** added:
  - time-domain tuning (James Jackson: "support for defining time-domain constraints instead of just length constraints, and support for Tuning Profiles");
  - **PCB Design Blocks** ("libraries of board layouts");
  - inner-layer objects in footprints;
  - unconstrained pin and gate swap with back-annotation;
  - the **graphical DRC rule editor** ("fully compatible with the existing Custom Rules language");
  - **variants**, jumpers, schematic grouping;
  - Allegro, PADS and gEDA importers, barcodes, suggested DRC fixes, 3D PDF.

  — [10.0.0 notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- **Multichannel (10.0 docs).**
  - Channels come from hierarchical sheets, component classes or named groups.
  - "Generate placement rule areas" creates `auto-placement-area-<source>` rule areas.
  - Repeat Layout options: anchor footprint, copy placement, copy routing (fully enclosed only; existing target routing removed), restrict to connected routing, copy other items, group items, include locked.
  - Channels are matched by **topology isomorphism**: refdes prefix plus pin-connectivity preservation, with ties broken by sheet instance and then proximity.

  — [pcbnew_multichannel.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_multichannel.adoc). The action names `pcbnew.Multichannel.generatePlacementRuleAreas` and `pcbnew.Multichannel.repeatLayout` were confirmed on 10.0 and master. — [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp)
- **PCB Design Blocks (10.0 docs).**
  - Libraries are `.kicad_blocks` folders listed in global or project tables.
  - A block can be saved from the whole board or a selection.
  - "Apply Design Block Layout" applies a saved layout to footprints grouped from a schematic design block; this needs "Place as group" and a group library link.
  - Actions: `pcbnew.InteractiveDrawing.placeDesignBlock`, `…applyDesignBlockLayout`, `pcbnew.PcbDesignBlockControl.saveSelectionAsDesignBlock`, and others.

  — [pcbnew_design_blocks.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_design_blocks.adoc); [pcb_actions.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/tools/pcb_actions.cpp)
- **Variants in PCB.** Variants are defined in the schematic and transferred by Update PCB. The PCB toolbar has a variant selector; DNP is per variant; `${VARIANT}` and `${VARIANT_DESC}` text variables are available. — [pcbnew_variants.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_variants.adoc)
- **Legacy tools still in master.** The legacy autoplacer (`ar_autoplacer.cpp`, `spread_footprints.cpp`) and "Attempt Finish Selected (Autoroute)" (`pcbnew.InteractiveRouter.Autoroute`). — [pcbnew/autorouter @master](https://gitlab.com/kicad/code/kicad/-/tree/master/pcbnew/autorouter); [pcb_actions.cpp @master](https://gitlab.com/kicad/code/kicad/-/blob/master/pcbnew/tools/pcb_actions.cpp)
- **10.0.x point releases**, from the blog post dates:
  - 10.0.1: 2026-04-15
  - 10.0.2: 2026-05-09
  - 10.0.3: 2026-05-15
  - 10.0.4: 2026-06-21
  - 10.0.5: 2026-07-22
  - 10.0.6: 2026-08-29
  - 10.0.7: 2026-10-07

  — [kicad-website 2026 blog sources](https://gitlab.com/kicad/services/kicad-website/-/tree/master/content/blog/2026)

### Inferences
- **The 10.0 backend for an agent should combine four channels:**
  1. IPC for item CRUD inside commits, footprint creation via `ParseAndCreateItemsFromString` from library `.kicad_mod` text, net-class definitions and variants;
  2. direct `.kicad_dru` file writes for rules;
  3. `kicad-cli pcb drc --format json --refill-zones` on a saved copy as the referee;
  4. SWIG `ExportSpecctraDSN`/`ImportSpecctraSES` in a separate Python process on the saved file, for Freerouting round trips.

  This avoids every unimplemented or unstable path: stackup writes, async refill and `RunAction`.
- **`RefillZones` in 10.0 is fire-and-forget.** After calling it, poll until KiCad stops returning busy (or until zone fill state changes, via `GetItems`) before reading geometry or running DRC on a saved file. Otherwise you read stale fills.
- **SES import is destructive in 10.0.** Lock any copper the agent wants to keep (manually routed critical nets, or copper from a previous router) before import. Footprint positions in the SES will overwrite placement; strip the placement section, or make sure it matches.
- **Plan for KiCad 11 now.** A `CustomRule` protobuf compiler target (condition string plus constraint enum plus MinOptMax) can share code with the `.kicad_dru` emitter. The structured proto can then validate rules in a round trip instead of relying on file parsing.

### Gaps
- Whether `UpdateItems` can modify every field of every 10.0 item type (e.g. pad stacks, zone fill settings) was not exhaustively tested.
- The KiCad 11 release date and final IPC surface are not announced. The master branch changes daily; one custom-rules commit is dated 2026-10-20.

---

## 4. Tool and product verified facts

### Takeaway
The open tools are better documented than the earlier notes said:
- **Freerouting** v2.5.0: GPL-3.0, KiCad 10 IPC path, REST and MCP with a one-call `autoroute_board`, two 0–1000 scores, 75% clean on its 1,157-board corpus, and a documented DRC JSON in KiCad format.
- **KiCadRoutingTools** (MIT): 10 Claude skills and a strong essay on why from-scratch autoplacement fails.
- **Cypress** (Apache-2.0): GPU DREAMPlace-style placer with 20 small benchmarks, rotation off by default, sides fixed by the input.

Commercial tools are moving fast:
- **Quilter:** physics-constraint vocabulary of 7 constraint types and 8 PRCs, per-project pin pricing, self-hosting on Kubernetes, no API.
- **DeepPCB:** RL routing plus placement, $30/h, SWIG plugin, explicitly "not for" DDR and length matching.
- **Flux:** agent-driven placement and routing, plus a public MCP server.
- **Cadence:** no new primary information since 2023.
- **Zuken:** no new primary information since 2023.

### Cited Findings

#### Freerouting (GPL-3.0; about 2.1k stars; latest v2.5.0, 2026-10-05)
- Releases:
  - v2.1.0: 2025-04-12 (freerouting-client 2.1.0 on PyPI the same day; the sole maintainer stepped back).
  - v2.2.0–2.2.4: Apr–May 2026.
  - v2.3.0: 2026-08-07.
  - v2.4.1: 2026-09-03.
  - v2.5.0: 2026-10-05 (npm MCP package dates corroborate).

  — [releases](https://github.com/freerouting/freerouting/releases); [npm](https://www.npmjs.com/package/@freerouting/freerouting-mcp-server); [PyPI client](https://pypi.org/project/freerouting-client/)
- **v2.5.0** — [release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0):
  - "direct Protocol Buffers IPC integration for KiCad 10+", with a progress dialog (Fanout, Autoroute, Optimize), routing in a separate process, and "fallback to the battle-tested Specctra DSN/SES pipeline";
  - "legacy KiCad SWIG support will be removed in the next release";
  - GraalVM native binaries;
  - `POST /v1/autoroute` and MCP `autoroute_board`;
  - `compact=true` DRC ("drops raw coordinate bloat by >70%");
  - `normalized_score` is now 0–1000;
  - the PCBench table: clean 30.9% → 75.0%, Tier C (6+ layers) 49.2% clean, Tier D 50%.
- **CLI flags:** `-de` (DSN, optionally `+ses+rules`), `-do` (`.dsn`/`.ses`/`.scr`), `-dr`, `-drc` (KiCad JSON), `-mp`, `-mt` (0 disables optimization), `--router.optimizer.improvement_threshold` (default 2.5%), `-inc`, `-im`, `--gui.enabled=false`, and API server settings (`api_server.endpoints` default `http://127.0.0.1:37864`, authentication enabled by default). The doc page still lists the `-us`/`-is`/`-hr` values that v2.5.0 removed. — [command_line_arguments.md](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md)
- **REST API** — [API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md):
  - Required headers: `Freerouting-Profile-ID` (UUID) and `Freerouting-Environment-Host` (e.g. `KiCad/10.0`; 400 if missing). Use `Authorization: Bearer` unless authentication is disabled.
  - Sessions and jobs: enqueue, settings, start, cancel, logs and stream, input and rules upload, output (202 with partial output while running).
  - `GET /jobs/{id}/drc[?compact=true]` and `/drc/summary`, which provides "spatial congestion hotspots and … auto-correction hints".
  - `POST /v1/autoroute` takes `file_content`/`rules_content`/`session_content`, `output_formats`, `timeout_seconds` and `router_settings`.
  - MCP over `POST /v1/mcp`, with an A2A card at `/.well-known/agent.json`.
- **MCP tool `autoroute_board`** takes `filePath`/`fileContent`, `rulesPath`, `sessionPath`, `outputFormats` (`["SES","DRC_SUMMARY"]`) and `timeoutSeconds`. There is also a multi-turn workflow (`create_session`, `enqueue_job`, …). — [MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md)
- **Scoring.**
  - Router score `V2_CONTINUOUS` = max(0, 1000 − W1·o1 − W2·o2 − W_C·N_viol/D − W_D·ΣL_um/(U·D)). The open fraction is split at F = 0.5, with W1 ≈ 333.3 and W2 ≈ 666.7, and D = max(1, pins × signal layers).
  - Optimizer score `V2_LOWER_BOUND` measures copper efficiency against placement-derived bounds; incomplete nets and DRC hits are vetoes.

  — [scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)
- KiCad integration through the PCM plugin ("KiCad 6.0 or newer", Tools → External Plugins). — [integrations.md](https://github.com/freerouting/freerouting/blob/master/docs/integrations.md)

#### KiCadRoutingTools (drandyhaas; MIT; 549 stars; 5,856 commits)
- Grid-based octilinear multi-layer A* with a Rust core ("~10× faster than pure Python"). Features:
  - rip-up and reroute;
  - diff pairs (pose-based A* with a Dubins heuristic);
  - length and **time** matching;
  - plane pours and repair;
  - BGA/QFN fanout;
  - placement optimization;
  - a "design brief", graded floorplan intent, a KiCad-oracle reconnect, and a plugin GUI for KiCad 9 and 10.

  Stated limitations: "No push-and-shove", "No blind or buried vias", "No coarse grid assignment", "No design rules by region/area support". — [README](https://github.com/drandyhaas/KiCadRoutingTools)
- The skills list (10) is in Corrections #31. `/pcb-free-agent` places and/or routes end to end and ends with "one independent verifier". — [docs/claude-skills.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/claude-skills.md)
- Placement doc: "The killer isn't the algorithm — it's **constraint capture**". It argues for perturbative refinement from a seed over from-scratch placement and reports experiments (June–Aug 2026), including router-in-the-loop repair (`place_route_loop.py`). — [docs/placement-optimization.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md)
- Distributed through the official KiCad PCM repository. — [README](https://github.com/drandyhaas/KiCadRoutingTools)

#### kicad-happy (aklofas; MIT; about 1.5k stars; v2.3.1)
- 11 skills: kicad, spice, emc (44 rule checks), datasheets, bom, digikey, mouser, lcsc, element14, jlcpcb, pcbway. Works with Claude Code, Codex and opencode. Supports KiCad 5–10. — [README](https://github.com/aklofas/kicad-happy)
- Signal-path detectors in execution order:
  1. voltage_dividers
  2. rc_filters
  3. lc_filters
  4. crystal_circuits
  5. decoupling
  6. current_sense
  7. power_regulators
  8. protection_devices
  9. opamp_circuits
  10. bridge_circuits
  11. transistor_circuits
  12. postfilter_vd_and_dedup
  13. led_drivers
  14. buzzer_speakers
  15. key_matrices
  16. isolation_barriers
  17. ethernet_interfaces
  18. memory_interfaces
  19. rf_chains
  20. bms_systems
  21. design_observations

  Further domain, validation and audit detectors are listed in how-it-works (I2C address conflicts, level shifters, ADC, RTC, clock distribution, and others). — [methodology_schematic.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_schematic.md); [how-it-works](https://github.com/aklofas/kicad-happy/blob/main/how-it-works.md)

#### mixelpixx KiCAD-MCP-Server (MIT; about 2.9k stars) and Konnect (AGPL-3.0 + commercial; about 1.3k stars)
- **KiCAD-MCP-Server** — [README](https://github.com/mixelpixx/KiCAD-MCP-Server):
  - v2.8.2; 244 tools registered, 184 indexed in 17 categories, 32 "essential" tools surfaced first by search;
  - Freerouting through Java, Docker or Podman; IPC "(experimental)" alongside SWIG;
  - `suggest_placement` and `route_pad_to_pad`.
- **Konnect** — [README](https://github.com/mixelpixx/Konnect):
  - a single Rust binary for KiCad 10, labelled BETA;
  - PCB editing over IPC; direct S-expression schematic writes;
  - Rust DSN exporter, then local Freerouting MCP, then a strict one-transaction SES import; an "authenticated KiCad 10 native-export bridge" is opt-in;
  - MCP over stdio or Streamable HTTP;
  - "Exposing all 228 tools … costs roughly 23K tokens"; the starter kit is about 2K tokens;
  - 6 skills and 2 agents.

#### rjwalters/kicad-tools (MIT; PyPI 0.24.0, 2026-10-20)
- "Standalone Python tools … parse, analyze, and manipulate KiCad schematic and PCB files … require no running KiCad instance". Extras: `[cuda]`, `[metal]`, `[native]` (C++ router), `[placement]` (CMA-ES `kct optimize-placement`), `[mcp]`. The README includes an ecosystem audit of peers with licences and benchmark notes. — [README](https://github.com/rjwalters/kicad-tools); [PyPI](https://pypi.org/project/kicad-tools/)

#### Cypress (NVlabs; Apache-2.0; 55 stars; 746 commits)
- Abstract (OpenAlex): "a scalable, GPU-accelerated PCB placement method inspired by VLSI … tailored cost functions, constraint handling … a PCB benchmark suite synthesized from real commercial designs … 1-5.9X higher routability … 1-19.7X shorter routed track lengths … up to 492.3X speedup". The paper is closed-access, per OpenAlex `oa_status: closed`. — [OpenAlex](https://api.openalex.org/works/doi:10.1145/3698364.3705346); [DOI](https://doi.org/10.1145/3698364.3705346)
- Repo:
  - top-level `benchmarks/` (small-1…small-20), `pcb-util/` (with `kicad_converter.py` and a Bookshelf converter), `tuner/`, `dreamplace/`;
  - run with `python dreamplace/Placer.py config.json`;
  - `enable_rotation` defaults to 0;
  - bottom-side parts are written with Bookshelf orientation `FN`.

  — [repo](https://github.com/NVlabs/Cypress); [params.json](https://github.com/NVlabs/Cypress/blob/main/dreamplace/params.json); [bookshelf_converter.py](https://github.com/NVlabs/Cypress/blob/main/pcb-util/bookshelf_converter.py)

#### OrthoRoute, Topola, tscircuit, fastroute, PCBWorld
- **OrthoRoute** (MIT, v1.0.0): "designed specifically for a narrow class of extremely large, dense, highly regular multilayer backplanes and BGA escape patterns". Needs KiCad 10.0+ with the API server enabled, and an NVIDIA CUDA 12 GPU or Apple Silicon. Nets are routed sequentially; the parallelism is inside the SSSP search. — [README](https://github.com/bbenchoff/OrthoRoute)
- **Topola** (MIT): "work-in-progress interactive topological router"; reads Specctra (`specctra-core` crate); NLnet NGI0 Entrust funded. — [Codeberg](https://codeberg.org/topola/topola); [Cargo.toml (mirror)](https://github.com/mikwielgus/topola/blob/master/Cargo.toml)
- **tscircuit capacity-autorouter** (MIT; npm 0.0.995).
  - `AutoroutingPipelineSolver(simpleRouteJson)` with a `step()` loop, plus a simplification-only pipeline.
  - SRJ supports `buses[].maxLengthSkew` and differential pairs with `lengthTolerance`.
  - Benchmarks run on the SRJ33 DRC-failure dataset and an online dashboard.

  — [README](https://github.com/tscircuit/tscircuit-autorouter)
- **fastroute** (GPL-3.0): a Rust port of Freerouting. `--parity` gives SES output byte-identical to Freerouting's deterministic mode on all 20 benchmark boards. It fixes listed Freerouting bugs, e.g. the optimizer never running after a self-stop and traces ignoring the outline for edge pads. It adds a KiCad plugin and `--live` view. — [README](https://github.com/parisxmas/fastroute)
- **PCBWorld** (LG AI Research; BSD-3; engine GPLv3; v1.1.0): main results are in Corrections #19. The paper's Freerouting baseline was version 2.1.0. — [arXiv v2](https://arxiv.org/html/2607.05915v2); [repo](https://github.com/LGAI-Research/PCBWorld)

#### Quilter (all from Quilter's own docs and pages)
- **Inputs.** A board file (one closed outline on KiCad `Edge.Cuts` or Altium Mechanical 1), footprints pre-loaded, and a netlist matching the schematic. Schematics drive physics-constraint detection; project files are optional. Results come back "in the same file format". Ground and power layers must be named "ground"/"gnd" and "power"/"pwr" to be detected. Pre-placed parts and pre-routed traces are kept, and connectors should be pre-placed. — [Prepare input board](https://docs.quilter.ai/using-quilter/prepare-your-input-board-file.md); [Upload files](https://docs.quilter.ai/using-quilter/upload-your-design-files.md)
- **Constraints workflow.** "Circuit Comprehension" auto-detects constraints from net classes, names, pins, connections and positions.
  - Routing constraints: Power Nets (auto), Differential Pairs (auto), Single-ended Impedance (manual), Timing-sensitive Signals (manual, coming soon).
  - Placement constraints: Crystal Oscillators, Switching Converters, Bypass Capacitors (all auto).
  - Unconstrained nets are "routed as generic signals".

  — [Physics constraints overview](https://docs.quilter.ai/physics-constraints/overview.md)
- **PRC scorecard.**
  - Power Nets → Overheated Length.
  - Single-ended impedance → Invalid Width Span, Ground Plane Overlap.
  - Diff pairs → Ground Plane Overlap, Uncoupled Spacing, Length Mismatch.
  - Bypass caps, crystals and switchers → Pin Distance, Trace Path Length, Layer Switch Count, Ground Plane Overlap.
  - Future: Top Plane Ground Pour, Neck Downs, Trace Proximity.

  — [PRC overview](https://docs.quilter.ai/physics-rule-checks-prcs/overview.md); [docs index](https://docs.quilter.ai/llms.txt)
- **Design parameters.** Pre-placed components, placement regions (Altium "Rooms", single- or two-sided), single-sided placement, pre-routed traces, preserved pours, keepouts, net widths by layer, stackups (from the input file or fab presets), and fabricator constraints. — [docs index](https://docs.quilter.ai/llms.txt)
- **2026 changelog:**
  - Apr 2026: Simbeor-based impedance profiles.
  - May 2026: reads net-class, layer and pair clearance rules from input files; a new placement constraint "restricted component … parent component … target pin … maximum allowed distance".
  - Jun 2026: Floorplan page.
  - Jul 2026: "[BETA]" experimental placement engines.
  - Sep 2026: "X.Y" candidate numbering, meaning placement X and router Y.
  - Aug 2026: large power pours with power-net-aware placement.

  — [Quilter changelog](https://www.quilter.ai/changelog)
- **Approach and scope.**
  - "Quilter uses … reinforcement learning … similar to how AlphaGo learned".
  - "Right now, Quilter can't typically design or optimize boards as well as skilled humans."
  - It does not handle silkscreen placement.
  - It is "a design agent, not a 'copilot'".

  — [FAQ](https://docs.quilter.ai/about-quilter/faq.md); [What Quilter does well](https://docs.quilter.ai/about-quilter/what-quilter-does-well.md); [What Quilter isn't](https://docs.quilter.ai/about-quilter/what-quilter-isnt.md)
- **Pricing and deployment.**
  - "Pay per Project. Not per Seat"; the cost is set by unrouted pins at upload.
  - Unlimited iterations, as long as the BOM stays within 10% of the original.
  - Parallel jobs.
  - AWS cloud (SOC 2 Type 2) or self-hosted Helm chart on Kubernetes with NVIDIA GPUs (FAQ: ≥16 GB VRAM); air-gapped operation is possible.
  - No public list price.

  — [Pricing](https://www.quilter.ai/pricing); [FAQ](https://docs.quilter.ai/about-quilter/faq.md)

#### DeepPCB (InstaDeep)
- Positioning:
  - "a learned routing engine: over seven years of reinforcement learning R&D".
  - Engineers "keep the critical nets".
  - "Not for … The densest, highest-speed boards: DDR nets, length matching, advanced impedance control, and RF-specific constraints".
  - Inputs: Altium `.pcbdoc`, KiCad (plus plugin), EasyEDA Pro/Std, Zuken; OrCAD, Allegro and Eagle via Specctra DSN.
  - "Cooper" checks setup in natural language.
  - Enterprise: "Custom API & MCP", public, private or on-prem cloud.
  - Claims "the top one-attempt score on both test sets" of PCBWorld-Bench (self-reported).

  — [deeppcb.ai](https://deeppcb.ai/); [benchmarks](https://deeppcb.ai/benchmarks/)
- **Placement** has been out of beta since April 2025: "up to 1,000 components and 2,200 pins", RL-based, credit-metered. — [DeepPCB placement post](https://deeppcb.ai/ai-powered-pcb-placement-by-deeppcb/)
- **KiCad plugin** released 2026-05-21 (beta, routing only). "PCB placement from schematics files and our agentic design assistant" were announced as next. The routing task "keep[s] your component placement exactly where you put it". — [plugin release post](https://deeppcb.ai/deeppcb-kicad-plugin-ai-pcb-routing/); [KiCad page](https://deeppcb.ai/kicad-autorouter-alternative/)
- Pricing is in Corrections #33. The plugin is a SWIG ActionPlugin v1.2.0, Apache-2.0, 66 stars, 9 commits. — [repo page](https://github.com/instadeepai/deeppcb-kicad-plugin)

#### Flux
- AI Auto-Layout was previewed in Dec 2024 ("place your components and hit the Auto-Layout button"; RL-based; uses Copilot credits). Spring 2026 update: routing "converges faster, with shorter traces, fewer vias". August 2026 update: a "public MCP server" for Claude, Cursor, Codex and others, and "sharper at placement and routing", including surgical placement edits. — [Flux Dec 2024](https://www.flux.ai/p/blog/introducing-ai-auto-layout); [Spring 2026](https://www.flux.ai/p/blog/spring-2026-updates-faster-ai-better-layouts-smarter-sourcing); [Aug 2026](https://www.flux.ai/p/blog/summer-2026-updates-flux-mcp-server-and-chat-mode)

#### Cadence Allegro X AI and Zuken AIPR
- **Cadence**, 2023 press release: automates "placement, metal pouring and critical net routing", with integrated SI/PI, running in the cloud, ">10X" faster. Distributor pages (2025–26) describe "Placement AI" (fixed parts, height limits, assembly rules, rooms), copper-pour generation, and "Route AI … Full Board Routing Closure" in Allegro X and OrCAD X. — [BusinessWire](https://www.businesswire.com/news/home/20230406005098/en/Cadence-Introduces-Allegro-X-AI-Accelerating-PCB-Design-with-More-Than-10X-Reduction-in-Turnaround-Time); [EMA](https://www.ema-eda.com/allegro-x-ai/); [FlowCAD](https://www.flowcad.com/en/x-ai-overview.htm)
- **Zuken**, Sept 2023: Smart Autorouter plus Basic Brain first, then Dynamic Brain (learns from the user's past designs) and Autonomous Brain. No later primary information was obtainable. — [iConnect007 reprint](https://www.iconnect007.com/article/137836/zuken-introduces-aipr-for-cr8000-empowering-pcb-designers-with-innovative-aipowered-place-and-route-technology/137833/pcb)

### Inferences
- **License fit for a GPL-3.0 core:**
  - Can be vendored: Freerouting (GPL-3.0), fastroute (GPL-3.0), KiCadRoutingTools (MIT), Cypress (Apache-2.0), tscircuit (MIT), Topola (MIT), kicad-tools (MIT), kicad-happy (MIT).
  - Konnect (AGPL) stays reference-only.
- **The commercial tools converge on one input contract:**
  - fixed outline, pre-placed connectors, locked critical copper;
  - net classes and named planes (Quilter detects planes by layer name, DeepPCB asks users to retype layers as power);
  - auto-detected "physics constraints" that a human confirms.

  An open LLM tool can copy this contract directly with KiCad-native artifacts.
- **DeepPCB's own scope limits** (no DDR, no length matching, no advanced impedance or RF) and **Quilter's** (timing-sensitive signals "coming soon", <6 GHz) leave the high-speed constraint space open. KiCad 10's time-domain `length`/`skew` plus tuning profiles already express this space, so an open tool that routes to those constraints would be differentiated.

### Gaps
- Cypress paper details (cost terms, the exact rotation model, benchmark sizes and licence, the evaluation router) could not be read: ACM and Cornell PDFs were blocked, and the paper is closed-access.
- No primary source on whether the PCBWorld authors evaluated DeepPCB. DeepPCB's leaderboard claim is self-reported.
- Freerouting's KiCad 10 IPC integration mechanism (which plugin it uses, IPC or SWIG) is not documented beyond the release notes.
- Zuken and Cadence 2026 status could not be checked on their own sites (403).

---

## 5. Implications for an LLM-driven KiCad placer/router (new points only)

### Takeaway
The verified facts change several implementation choices:
- Use `kicad-cli` plus SWIG, not IPC, for DSN/SES and DRC on 10.x.
- Treat SES import as destructive.
- Compile constraints with strict, source-verified syntax.
- Make the DRC feedback loop rule-name-aware by parsing `description`.
- Exploit capabilities the notes missed: footprint creation from S-expression strings, net-class writes, variants, time-domain `length`/`skew`, multichannel topology matching, and Freerouting's one-call REST/MCP with KiCad-format DRC.

### Cited Findings
- `ParseAndCreateItemsFromString`, `SetNetClasses` and the variant commands are served in 10.0. — [api_handler_pcb.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp); [api_handler_common.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/api/api_handler_common.cpp)
- SES import deletes unlocked copper and applies placement. — [specctra_import.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/specctra_import_export/specctra_import.cpp)
- JSON DRC has no rule field; the rule name is embedded in `description`. — [rc_item.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/common/rc_item.cpp)
- `length`/`skew` accept `ps`/`fs`. — [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp)
- Repeat Layout matches channels by topology isomorphism. — [pcbnew_multichannel.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_multichannel.adoc)
- Freerouting `POST /v1/autoroute`, MCP `autoroute_board` and the KiCad-format `-drc`. — [API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md); [MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md)
- PCBWorld results: Freerouting 2.1.0 CP 0.80/0.78 vs a GPT-5.4 tool-calling agent at 0.65/0.00. — [PCBWorld v2](https://arxiv.org/html/2607.05915v2)
- KRT's constraint-capture argument and refine-from-seed results. — [placement-optimization.md](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md)

### Inferences
1. **Library footprint placement on 10.0 without SWIG.** Read the `.kicad_mod` S-expression from the library, rewrite position, rotation, side and reference, then call `ParseAndCreateItemsFromString` inside a commit. That gives undoable placement from libraries a full KiCad version before `PlaceFootprintFromLibrary` (11.0). Test it early, because pad-net assignment after paste needs an `UpdateItems` pass.
2. **Rule-name protocol for the repair loop.** Prefix every generated rule name with a stable IR ID, e.g. `(rule "IR:c42:decap_len" …)`. Parse the JSON `description` with a regex for `\((rule '|)?([^ ]+)'? .*?; actual .*?\)`, or from the text `.rpt`, to map each violation to its IR constraint. Treat `type` only as a coarse class, because `physical_clearance` reports as `clearance`.
3. **Canonical units and a lint pass.** The rule emitter outputs only `mm`, `deg` and `ps`. After writing `.kicad_dru`, run a validation pass: `kicad-cli pcb drc` on a scratch copy will fail fast on syntax errors, because "Any errors in the custom rules will prevent the design rule checker from running". Never emit two `condition` clauses.
4. **Time-domain first for high-speed classes.** For an interface with an impedance target, emit:
   - a tuning profile per net class (width, gap, unit delay per layer, via delays), written through `SetNetClasses`, whose `tuning_profile` field is available since 10.0.0;
   - `length`/`skew` rules in `ps`, with `(within_diff_pairs)` for intra-pair skew.

   This matches how KiCad's tuner and DRC already behave in 10.x, and it targets the high-speed space that DeepPCB and Quilter explicitly leave out.
5. **Lock-before-import discipline for Freerouting.** Before DSN export, lock all copper the agent or user wants to keep. After SES import, re-run zone fill (async on 10.0, so poll) and `kicad-cli pcb drc`. Compare the KiCad DRC JSON with Freerouting's own drc.v1 output; the schemas match, so a single parser handles both. Differences reveal translation losses at the DSN boundary, such as the board-edge clearance gap that v2.4.1 told users to work around.
6. **Use Freerouting's single-turn API as a tool primitive.** Expose one MCP tool, `route_with_freerouting(board, nets_subset?, timeout)`. Internally it exports DSN (SWIG on 10.x; `kicad-cli pcb export specctra` or IPC on 11), calls `POST /v1/autoroute` on a local server (authentication disabled, `Freerouting-Environment-Host: KiCad/10.0`), and imports the SES. Return only `normalized_score`, `optimizer_score`, unrouted count and the compact DRC summary to the LLM, not geometry.
7. **Multichannel as a placement multiplier.** Once the agent has placed and routed one channel, "Generate placement rule areas" plus Repeat Layout (via `RunAction`, or by replicating its logic with IPC CRUD) copies it to N channels. KiCad's topology-isomorphism matcher resolves component correspondence, ties broken by sheet instance. Prefer hierarchical-sheet channels, which the docs call "most common and convenient", over component classes or groups.
8. **Seed placement from human-like priors, then refine.** KRT's measured lesson ("constraint capture" is the bottleneck; refine from a seed rather than place from scratch) and Quilter's 2026 additions (floorplan page, pin-distance placement constraint, region-based clustering with anchoring) point the same way. The agent's first output should be a floorplan of regions, pre-placed connectors, anchors and pin-distance constraints, confirmed by the user, before any numeric optimizer runs.
9. **Benchmark against Freerouting 2.5, not 2.1.** PCBWorld's published baselines use Freerouting 2.1.0. Freerouting reports its own clean rate rising from 30.9% (2.4.1) to 75.0% (2.5.0) on its corpus. A comparison with the paper's numbers alone would overstate gains; re-run Freerouting 2.5.0 locally on PCBWorld D3-A and D3-B.
10. **LLM-only routing is not competitive.** On PCBWorld, the strongest LLM agent (GPT-5.4) reached 0.65 CP on D3-A and 0.00 on D3-B (10 larger boards), with 231–866 s per board. Freerouting reached 0.80 and 0.78 at 7–10 s. The LLM should orchestrate, constrain and repair, and leave geometric search to engines.
11. **Plugin longevity.** SWIG-based plugins break in KiCad 11. That includes the DeepPCB plugin, the Freerouting KiCad plugin's SWIG path (to be removed in the next Freerouting release), and KRT's External Plugins. Keep SWIG strictly in a short-lived helper process for DSN/SES on 10.x and switch to the IPC jobs on 11.

### Gaps
- No end-to-end test was run: whether `ParseAndCreateItemsFromString` keeps net assignments, how long async refills take, and whether `.kicad_dru` reloads in the GUI. These need an in-project spike on KiCad 10.0.7.
- Freerouting 2.5.0's KiCad 10 IPC path has not been evaluated independently, and its DRC fidelity relative to KiCad's own DRC is unknown.
