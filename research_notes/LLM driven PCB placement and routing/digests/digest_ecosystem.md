# Digest: the ecosystem around LLM-driven KiCad placement and routing (state as of 2026-10-20)

> **Scope.** This digest synthesizes five notes files:
> - `existing_tools_and_apis.md` (**ET**)
> - `verification_kicad_and_tools.md` (**VK**)
> - `kicad_mcp_codebases.md` (**MCP**)
> - `patents_and_industry.md` (**PI**)
> - `licensing.md` (**LIC**)
>
> **Precedence.** VK corrects ET and also `constraints_verification_benchmarks.md`, `solver_toolbox.md` and `netlist_datasheet_understanding.md`. Where they conflict, VK wins. The values below are already corrected, and §0 lists the corrections so that other digests can be checked against them.
>
> **Evidence tags.** These are kept from the sources:
> - **[P]** primary page, repo or source read.
> - **[S]** search snippet or secondary coverage only.
> - **[P-pat]** full patent text from USPTO PPUBS.
> - **[V]** verified by VK.
> - **[C]** corrected by VK.
> - **[vendor]** vendor self-report.
>
> Untagged pass-1 ET items count as primary when they come from GitHub, GitLab, PyPI or npm.
>
> **Licensing frame.** The decision is FINAL: code is MPL-2.0; docs are CC-BY-4.0; rule packs are CC0; data is CDLA-Permissive-2.0; GPL code is allowed only behind a process boundary. ET, MCP and PI wrote their reuse advice for a GPL-3.0 project. LIC recommended Apache-2.0, with MPL-2.0 as runner-up. Every reuse verdict below has been re-assessed against **MPL-2.0** (§9). Where an earlier recommendation now flips, it is flagged **[MPL-flip]**.

---

## 0. Corrections register (VK wins; apply across all digests)

Each line gives the corrected value; sources are in the body sections or in VK §1. "Affects" names the other notes files that carry the wrong value.

1. **Stackup is read-only over IPC.** `UpdateBoardStackup` has no handler on 10.0 or master.
2. **SES import in 10.0 is destructive.** It deletes unlocked tracks, vias and markers, and applies the SES placement, moving and flipping footprints. The 10.0 user doc says the opposite. Affects ET, solver_toolbox.
3. **DRC units:** only `mm/mil/in/deg/ps/fs`, not `th`, `"` or `rad`. Time units only in `length`/`skew`. Affects constraints_verification_benchmarks.
4. **`microvia_*` and `isStackedVia` are master-only.** The master keyword is `hole_aspect_ratio` (2026-10-12). `track_angle` and `track_segment_length` are in 10.0. Affects constraints_verification_benchmarks.
5. **`RefillZones` in 10.0 is whole-board only and async.** A zone list returns `AS_UNIMPLEMENTED`.
6. **kipy KiCad-11 methods are main-only (0.9.0.dev0).** Released 0.8.0 (2026-08-30) has get-only net classes.
7. **Point-release requirements:** by-net, by-netclass and connected-items queries need ≥10.0.1; `GetBoardLayerByName` 10.0.6; `BeginCommit` header 10.0.7; `tuning_profile` since 10.0.0.
8. **10.0 also serves** `Get/SetNetClasses`, text variables and 8 variant commands. `schematic_commands.proto` exists in 10.0 but is empty.
9. **The master CLI subcommand is `kicad-cli pcb export specctra`.**
10. **Freerouting v2.5.0 removed `-hr` and `RANDOM`/`GREEDY`/`HYBRID`.** Use `-us GLOBAL_OPTIMAL` with `-is SEQUENTIAL|PRIORITIZED`. The CLI doc is stale. Affects solver_toolbox.
11. **DeepPCB price:** $30/1 h, $280/10 h, $800/30 h, Enterprise. Free trial 30 min (1 board, ≤4 layers, ≤150 airwires, ≤100 components, ≤2,200 pins). Paid tiers: ≤8 layers, ≤1,200 airwires, ≤1,000 components ([pricing](https://deeppcb.ai/pricing)).
12. **Flux now places parts** (Aug 2026) and runs a **public MCP server**. "No placement" is outdated.
13. **KMS ships `suggest_placement`, `route_pad_to_pad` and Freerouting `autoroute`.** v2.8.2: 244 tools registered, 184 indexed.
14. **Konnect:** 1.3k★ and 184 issues (not 241). 228 + 7 tools; its About says 217 and the KMS README says 171.
15. **KRT has 10 skills.**
16. **The DeepPCB plugin is a SWIG ActionPlugin, v1.2.0.** The 6.0+ versus 10.0+ conflict remains.
17. **Diff-pair matcher:** skips trailing `[0-9_]`, then needs uppercase `+ - P N`. `LANE_P_0`↔`LANE_N_0` pair; lowercase is not recognized; `XTAL_P/N` pairs (false positive). Affects netlist_datasheet_understanding.
18. **`ComponentClass` and `Component_Class` both resolve.**
19. **Cypress is confirmed:** Apache-2.0, ISPD '25, DOI 10.1145/3698364.3705346. Affects constraints_verification_benchmarks.
20. **Topola lives at codeberg.org/topola/topola.** Affects solver_toolbox.
21. **Quilter:** exactly 8 PRCs; envelope "<5,000 pins" with no component range.
22. **PCBWorld used Freerouting 2.1.0;** D3-B is 10 boards.
23. **TraceMaker's baseline was Freerouting 2.2.4**, single 60 s runs.
24. **kicad-happy detector counts are inconsistent** (40 / 60+ / 21).
25. **OrthoRoute routability @5 is 0.34 (D2) and 0.53 (D3-A).**
26. **Freerouting Docker arm/v7: conflict.**
27. **NOT FOUND:** "122 actions added / 47 removed" (solver_toolbox).
28. **Zuken later Brains not shown to have shipped;** no Cadence primary update since 2023.
29. **Speedrun hours:** baseboard 12 h, SOM 26.5 h (PI corrected a first-pass reversal).

---

## 1. KiCad integration surface: 10.x today vs KiCad 11

### 1.1 Versions and cadence
- **KiCad 10.0.0** shipped 2026-03-20 with 7,609 unique commits [V] ([notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)).
  - Point releases: 10.0.1 on 04-15, 10.0.2 on 05-09, 10.0.3 on 05-15, 10.0.4 on 06-21, 10.0.5 on 07-22, 10.0.6 on 08-29, 10.0.7 on 10-07 ([blog src](https://gitlab.com/kicad/services/kicad-website/-/tree/master/content/blog/2026)).
  - 9.0.0 shipped 2025-02-20.
- **Release policy:** the feature merge window closes **Oct 31** and a major release is due "annually by January 31st". Both 9 and 10 shipped late ([policy](https://dev-docs.kicad.org/en/rules-guidelines/release-policy/)). So **KiCad 11 is likely around Q1 2027** (inference). Master changes daily.
- KiCad core is "GPLv3 or later" ([LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README)).

### 1.2 IPC API mechanics
- **Transport:** protobuf over NNG (UNIX sockets; named pipes on Windows). Calls run on KiCad's **single UI thread**, so clients "need to anticipate that API messages may sometimes timeout or fail because KiCad is busy" and "should not open multiple connections" ([dev-docs IPC](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)).
- **Stability:** new messages and fields may be added, but existing meanings never change. Deprecated items stay supported for at least one major version.
- **KiCad 9/10 limits** ([for-addon-developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)):
  - GUI-attached only.
  - No plotting or export.
  - IPC plugins work only in the PCB editor.
  - "No plans to support a standalone library for loading and manipulating KiCad files separate from the client-server (IPC) model."
- **Plugins:**
  - Location `${KICAD_DOCUMENTS_HOME}/<version>/plugins`, with a `plugin.json` per plugin.
  - Python plugins get an auto-created per-plugin venv; "executable" plugins can be any binary.
  - Environment: `KICAD_API_SOCKET` and `KICAD_API_TOKEN`; the default socket is `api.sock` in temp, with the PID appended when several instances run.
  - `EnableAPILogging=1` logs every request.
  - The user must enable the server under Preferences > Plugins.
- **Socket ownership [S, unverified]:** only one socket exists, owned by whichever instance bound it. Board commands failed while the project manager held it ([glama](https://glama.ai/mcp/servers/lmaag182/kicad_mcp_server_ipc)).

### 1.3 Coverage matrix (VK §3.1; sources: [proto @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/api/proto), [handler @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/api/api_handler_pcb.cpp), [proto @master](https://gitlab.com/kicad/code/kicad/-/tree/master/api/proto), [kipy 0.8.0](https://gitlab.com/kicad/code/kicad-python/-/blob/0.8.0/kipy/board.py))

| Capability | 10.0.x | master (11-dev) | kipy 0.8.0 | kipy main |
|---|---|---|---|---|
| Headless server | ❌ GUI only | ✅ `kicad-cli api-server [--socket] [file]` (first commit 2026-03-21) | ❌ | ✅ auto-launch |
| Open/create/close docs | ❌ (`GetOpenDocuments` only) | ✅ | ❌ | ✅ |
| Commit/undo (`BeginCommit`/`EndCommit`, COMMIT/DROP) | ✅ | ✅ | ✅ begin/push/drop | ✅ |
| Item CRUD (Create/Get/GetById/Update/Delete) | ✅ (no generators or tuning patterns, no DRC markers in `GetItems`) | ✅ | ✅ | ✅ |
| Footprint creation | ✅ fully specified `FootprintInstance` or `ParseAndCreateItemsFromString` | ✅ + `PlaceFootprintFromLibrary` | via items/string | ✅ |
| Selection, hit test, bbox | ✅ | ✅ + cross-probe `SyncSelection`/`HighlightNets`/`FocusOnItem`, `GetBoardBoundingBox` | ✅ | ✅ |
| Nets, by-net, by-netclass, connected | ✅ (≥10.0.1) | ✅ | ✅ | ✅ |
| Net-class definitions (incl. `tuning_profile`) | ✅ get/set | ✅ | get only | ✅ |
| Net-class assignments (patterns) | ❌ | ✅ | ❌ | ✅ (2026-09-23) |
| Text variables; variants (8 cmds) | ✅ | ✅ | vars ✅ / variants not wrapped | – |
| Stackup | **read-only** | **read-only** | ✅ get | ✅ |
| Layers, origin, title block, appearance | ✅ | ✅ (+page settings) | ✅ | ✅ |
| Board design rules | ❌ | ✅ `Get/SetBoardDesignRules` | ❌ | ✅ |
| Custom DRC rules | ❌ (write `.kicad_dru`) | ✅ structured `CustomRule` (condition string, constraint enum, MinOptMax in nm/**attoseconds**, layer, severity, name; options `SKEW_WITHIN_DIFF_PAIRS`/`TIME_DOMAIN`/`SPACE_DOMAIN`); round-trip fix 2026-10-20 | ❌ | ✅ |
| Run DRC / read results | ❌ (only `InjectDrcError`) | ❌ | ❌ | ❌ |
| Zone refill | whole-board, **async** | per-zone; sync when headless | ✅ | ✅ |
| Pad polygons, padstack presence | ✅ | ✅ | ✅ | ✅ |
| `FlipItems` | ✅ | ✅ | ✅ | ✅ |
| `InteractiveMoveItems` | ✅ (hands control to the user; editor busy until done) | ✅ | ✅ | ✅ |
| `RunAction(name)` | ✅ returns `RAS_OK`/`RAS_INVALID` immediately; "specifically *not* an API"; names "may change… disappear" | ✅ | ✅ (fixed 0.7.1) | ✅ |
| Netlist import | ❌ | ✅ | ❌ | ✅ |
| Specctra DSN export / SES import | ❌ (GUI, `RunAction` or SWIG) | ✅ `RunBoardJobExportSpecctraDsn` / `ImportSpecctraSession` | ❌ | not checked |
| Export/plot jobs | ❌ | ✅ 3D, render, SVG, DXF, PDF, PS, PNG, Gerbers, drill, pos, GenCAD, DSN, IPC-2581, IPC-D-356, ODB++, stats, IDF | ❌ | ✅ |
| Library tables; schematic | ❌ | ✅ (hierarchy, netlist, place symbol, sch jobs) | ❌ | partial |
| Route/autoroute/autoplace | ❌ | ❌ | ❌ | ❌ |
| Change notifications | ❌ | ❌ | ❌ | ❌ |

### 1.4 kicad-python (kipy) details
- **Release:** PyPI 0.8.0 (2026-08-30), **MIT**. It was relicensed from GPLv3 on 2025-02-02 (commit 7b8a97f7).
  - Requirements: `protobuf<6,>=5.29`, `pynng<0.10,>=0.9`, `jsonschema`; Python ≥3.9. `KiCad.check_version` checks compatibility.
  - History: 0.1.0 (2024-12-21), 0.2.0 (2025-02-19), 0.3.0 (03-29), 0.4.0 (07-08), 0.5.0 (10-13), 0.6.0 (2026-03-15), 0.7.0/0.7.1 (04-17/18), 0.8.0 (08-30) [V].
  - Rendered docs: [docs.kicad.org/kicad-python-main](https://docs.kicad.org/kicad-python-main/).
  - Repo examples: `move_footprints.py`, `create_zone.py`, `round_tracks`, `design_rules.py`, `check_for_testpoints.py`, `headless.py`, `jobs.py`, `layer_indicator`.
- **Known API traps (MCP):**
  - The 0.8.0 `FootprintInstance.orientation` setter **drops every `Footprint3DModel`**, even when the angle is unchanged. KMS ([ebc2ed1](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/ebc2ed15691d183e25e7eb815f37b5b6a9ec3909)) and PRO (#1325) both hit it.
  - `Track.length` is a method, not a property; mocks hid this.
  - Staged creates are invisible to `get_items` until the commit is pushed (PRO evidence on 10.0.5).
  - A TTL bug let a transaction reconnect to a *new* KiCad process. Treat `AS_TOKEN_MISMATCH` as a session break.
- **License wrinkle:** one stray GPL header remains in `kipy/proto/common/types/__init__.py`, and 11 of 17 generated `*_pb2.pyi` stubs in 0.7.1 carry GPL headers ([issue #134](https://gitlab.com/kicad/code/kicad-python/-/work_items/134), open).

### 1.5 SWIG `pcbnew` (deprecated in 9.0, removal planned for 11.0)
- It is "a raw binding layer… not a true API" and works stand-alone ([dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)).
- In 10.0 it exposes `LoadBoard`/`SaveBoard`, `ExportSpecctraDSN(board, path)`, `ImportSpecctraSES(board, path)` and `WriteDRCReport` ([helpers.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/python/scripting/pcbnew_scripting_helpers.h)).
- 10.0.6 fixed DSN-export quoting, duplicate-reference and layer-name bugs.
- **Hazards (MCP):**
  - `SaveBoard` "is not a reformat: it drops data". It de-duplicates coincident shapes (554→552 on vme-wren), destroys hidden `fp_text` on KiCad 9 (32→0), and upgraded the format in place while dropping 114 property UUIDs and returning `status="ok"`. On Windows it rewrote 760 line endings as CRLF ([adr-cst-substrate](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)).
  - `SaveBoard` writes a possibly stale project model over `.kicad_pro`.
  - "Calling `ZONE_FILLER` via SWIG causes segfault" (KMS).
  - A SWIG `BOARD` proxy can go dead after some sequences.
- **SWIG plugins break in KiCad 11.** That includes DeepPCB's plugin, Freerouting's SWIG path ("will be removed in the next release") and KRT's External Plugin.

### 1.6 kicad-cli
- **10.0:**
  - `pcb drc`
  - `pcb export` {3d (STEP/GLB/PLY/STL/VRML/XAO/BREP/U3D/3D-PDF), drill, dxf, gencad, gerber(s), hpgl, ipc2581, ipcd356, odb, pdf, pos, ps, stats, svg}
  - `pcb import`, `pcb render`, `pcb upgrade`
  - `sch erc`, `sch export` {bom, netlist, plot, pythonbom}, `sch upgrade`
  - `fp`/`sym` upgrade and export-svg
  - `jobset run` (jobsets arrived in KiCad 9), `version`
- `pcb import --format` hints are `auto, pads, altium, eagle, cadstar, fabmaster, pcad, solidworks`. Allegro and gEDA are not CLI hints, despite the 10.0 importer announcement.
- **Master adds:**
  - `api-server`, `pcb export specctra`, `pcb export idf/png/stackup`
  - `pcb/sch/fp/gerber diff`, `gerber info`/`convert png`
  - `pcb/sch/project downgrade`, `git_mergedriver`, `mergetool`, top-level `import`
- **No headless DSN on 10.0.** Konnect wrote its own fail-closed Rust DSN exporter from the IPC snapshot, with an optional ActionPlugin bridge. PRO raises `ManualStepRequiredError` unless the CLI advertises `pcb export specctra` (MCP).

### 1.7 Built-in automation levers (all reachable only through GUI or `RunAction`)
- **Autoroute.** `pcbnew.InteractiveRouter.Autoroute`, "Attempt Finish Selected (Autoroute)", sequentially routes selected pads. It has existed since 8.0 and is still in master.
- **Legacy autoplacer.** `pcbnew.Autoplacer.autoplaceSelected` and `…autoplaceOffboard` (`ar_autoplacer.cpp`, 2011–12, Charras/Hollenbeck; plus `spread_footprints.cpp`). It needs Edge.Cuts and skips locked parts.
- **Specctra GUI actions:** `pcbnew.EditorControl.exportSpecctraDSN` and `importSpecctraSession`.
- **Multichannel** (KiCad 9, Wlostowski) ([pcbnew_multichannel.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_multichannel.adoc)):
  - Channels come from hierarchical sheets ("most common and convenient"), component classes or groups.
  - `generatePlacementRuleAreas` creates `auto-placement-area-<source>` areas.
  - `repeatLayout` options: anchor footprint, copy placement, copy routing (fully enclosed only; existing target routing is removed), restrict to connected routing, other items, grouping, include locked.
  - Channels are matched by **topology isomorphism**: refdes prefix plus pin connectivity, with ties broken by sheet instance, then proximity.
- **PCB Design Blocks** (10.0) ([design_blocks.adoc](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_design_blocks.adoc)):
  - Stored as `.kicad_blocks` libraries.
  - "Apply Design Block Layout" works on footprints grouped from a schematic block; it needs "Place as group" and a group library link.
  - Actions include `placeDesignBlock`, `applyDesignBlockLayout` and `saveSelectionAsDesignBlock`.
- **KiCad 9:**
  - component classes (set from rule-area directive labels) with `A.ComponentClass`, `hasComponentClass`, `memberOfFootprint('${Class:X}')`;
  - multiple net classes per net with `hasNetclass`;
  - net-class rule areas, schematic design blocks, zone manager;
  - multi-track drag in the push-and-shove (PNS) router.
- **KiCad 10:**
  - time-domain tuning and tuning profiles;
  - inner-layer objects in footprints;
  - unconstrained pin/gate swap with back-annotation;
  - graphical DRC rule editor, suggested DRC fixes;
  - variants, jumpers, schematic grouping, barcodes, 3D PDF;
  - Allegro, PADS and gEDA importers ([10.0.0 notes](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)).
- **Variants in PCB:** defined in the schematic, carried by Update PCB, with a toolbar selector, per-variant DNP and `${VARIANT}`/`${VARIANT_DESC}` variables.
- **10.0.4** made the interactive router enforce `physical_clearance` and `physical_hole_clearance`.

### 1.8 File-format and dialect hazards (MCP, measured)
- **Format stamps.** KiCad 9's maximum board stamp is **20241229**. pcbnew 10 silently upgrades a board to **20260206** on a bare load and save.
- **Net references:**
  - KiCad 10 accepts a numeric `(net N)` and **silently rebinds it by load order**. In one measurement `(net 2)` landed on GND.
  - KiCad 9 hard-rejects a named `(net "NAME")`.
  - KiCad 10 boards have no top-level net table. Konnect reported 0 nets and wrote zones as `(net 0)`, "an electrically orphaned pour reported as success".
- **Unknown layer names** (`Dwgs.User`, `User.1–45`, inner layers beyond In2) crash KiCad 10.0.5 through the unvalidated scalar layer field (`0xc0000005`, unsaved board lost). The client sees only an NNG timeout.
- **DRC JSON.** KiCad 10 changed the courtyard classification in DRC JSON, so PRO needed a schema-aware classifier.
- S-expression formats are documented for PCB, footprint, schematic, symbol and worksheet ([dev-docs](https://gitlab.com/kicad/services/kicad-dev-docs/-/tree/master/content/file-formats)).

### Implications for our system
- **Use four channels on 10.0.x** (VK):
  1. IPC inside commit groups for CRUD, net classes, variants and footprint creation via `ParseAndCreateItemsFromString`, followed by an `UpdateItems` pass for pad nets. This gives undoable library placement a full version before `PlaceFootprintFromLibrary`.
  2. Direct `.kicad_dru` writes for rules.
  3. `kicad-cli pcb drc --format json --refill-zones` on a saved copy as the referee.
  4. SWIG `ExportSpecctraDSN`/`ImportSpecctraSES` in a **separately distributed GPL helper process** for DSN/SES.
- **Avoid:** stackup writes, unpolled refills, and `RunAction` where an alternative exists.
- **Put a `BoardSession` abstraction in front** with three backends: live IPC, KiCad 11 headless `api-server`, and file-level CST splice. Migrate at KiCad 11.
- **Version-gate everything.** Use named nets only above 20241229 and canonical layer names. Run CI on KiCad 9.0.x and 10.0.x.
- **Spike early on 10.0.7.** Check whether net assignment survives `ParseAndCreateItemsFromString`, how long async refills take, and when `.kicad_dru` reloads in the GUI.

---

## 2. DRC rules reference for a constraint compiler (KiCad 10.0; VK §2)

**Grammar** ([pcbnew_advanced.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/pcbnew/pcbnew_advanced.adoc); [drc_rule_parser.cpp @10.0](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_rule_parser.cpp))
- The file is `<project>.kicad_dru` and starts with `(version 1)`. `#` starts a comment.
- `${var}` is substituted before parsing. Object-dependent variables (`${LAYER}`) cause syntax errors.
- Rules are evaluated in reverse order and the first match wins, so **specific rules go later**.
- Form: `(rule name [(severity error|warning|ignore|exclusion)] [(layer L|outer|inner)] [(condition "expr")] (constraint …)…)`.
- **Parser behaviour:**
  - A second `condition` silently **overwrites** the first.
  - A second `layer` is an error.
  - Each constraint type may appear once per rule.
  - Only `version` and `rule` are valid at top level.
  - `ParseComponentClassAssignmentRules` separately handles `(assign_component_class name (condition …))`.
- **Severity:** `ignore` rules are still evaluated and can override earlier ones, but the interactive router does not observe them.
- **Conditions:**
  - They are tested on A/B pairs, in both orders, with `AB.` for pair functions.
  - `== != > >= < <= && || !` all have **equal precedence and evaluate left to right**.
  - Booleans are bare (no `true`/`false` literals), and `null` is comparable.
  - A value without a unit is in nm, or degrees for angles.
  - Units must be mm/mil/in/deg/ps/fs. Time units on any other constraint raise "Time based units not allowed"; mixing time and length raises "Mixed units".
- **Constraints parsed in 10.0: 35** (34 documented plus the undocumented `solder_mask_sliver`), plus deprecated aliases `mechanical_clearance`, `mechanical_hole_clearance` and `hole`.
  - **Clearance family:**
    - `clearance` (min; negative = overlap allowed; router honours it; different nets only; keys `clearance`/`hole_clearance`/`shorting_items`/`tracks_crossing`/`zones_intersect`).
    - `physical_clearance` (net-agnostic; same layer only, except Edge.Cuts counts on all; "much slower"; reports as `clearance`/`hole_clearance`).
    - `physical_hole_clearance` (round holes only).
    - `hole_clearance`.
    - `edge_clearance` (Edge.Cuts plus oval pad holes; keys `copper_edge_clearance`/`silk_edge_clearance`).
    - `courtyard_clearance` (footprints without a courtyard produce no error; keys `courtyards_overlap`/`missing_courtyard`/`malformed_courtyard`/`pth_`/`npth_inside_courtyard`).
    - `creepage`, `connection_width` (includes zone necks), `silk_clearance`.
  - **Holes and vias:**
    - `hole_size` (min/opt/max; opt = router default drill; oval holes: minor axis against min, major against max).
    - `hole_to_hole` (mechanical drills only).
    - `annular_width`.
    - `via_diameter` (opt = router default).
    - `via_count` (unitless, per net or path → `too_many_vias`; also emitted by the diff-pair and matched-length providers).
    - `via_dangling`.
    - `disallow` (tokens `track via through_via blind_via buried_via micro_via pad zone text graphic hole footprint`; `via` means all via types).
  - **Tracks:** `track_width` (opt = router default), `track_angle`, `track_segment_length`.
  - **High-speed:**
    - `diff_pair_gap` (opt = router gap; not tested on non-parallel fan-out).
    - `diff_pair_uncoupled` (tuning patterns excluded since 10.0.4).
    - `length` (len **or time**; opt = tuner target; time units force time-domain tuning).
    - `skew` (target opt, else min, else 0; `(within_diff_pairs)` switches from bus skew to intra-pair skew). The internal `DIFF_PAIR_INTRA_SKEW_CONSTRAINT` has no keyword.
  - **Mask, paste, text:** `solder_mask_expansion`, `solder_mask_sliver` (shown in the editor as "Minimum soldermask silver"; no DRC key found), `solder_paste_abs_margin` + `_rel_margin` (final value = absolute + relative), `bridged_mask`, `text_height`, `text_thickness`.
  - **Zones:** `zone_connection` (solid|thermal_reliefs|none), `thermal_relief_gap`, `thermal_spoke_width`, `min_resolved_spokes` (bare integer 0–4 → `starved_thermal`).
  - **`assertion "bool expr"`** → `assertion_failure`. The graphical editor's "Permitted layers" and "Allowed orientation" compile to this.
- **Master-only constraints:** `microvia_stack_depth`, `hole_aspect_ratio` (proto stores thousandths), `net_chain_length` and `stub_length` (both accept time units), and `return_path` (`(constraint return_path (layer "B.Cu") (net "GND"))` → `net_chain_return_path`). These are KiCad's first native reference-plane check.
- **Functions in 10.0: 23 current.**
  - `enclosedByArea` (slower), `intersectsArea` (uses the fill for filled zones), `existsOnLayer`.
  - `fromTo('U1-C5','U2-D3')` (wildcards, case-insensitive; the path must be unique).
  - `getField` (footprints only).
  - `hasComponentClass` (the item or its parent footprint), `hasNetclass`, `hasExactNetclass`.
  - `inDiffPair` (false if the complement net is missing).
  - `intersectsCourtyard` with Front/Back variants (refdes, `lib:fp` or `${Class:Name}`).
  - The undocumented `intersectsKeepout`.
  - `isBlindVia`, `isBuriedVia`, `isBlindBuriedVia`, `isMicroVia`, `isCoupledDiffPair` (AB), `isPlated`.
  - `memberOfGroup`, `memberOfFootprint`, `memberOfSheet` (exact path), `memberOfSheetOrChildren`.
  - **5 deprecated:** `insideArea`, `insideCourtyard`, `insideFrontCourtyard`, `insideBackCourtyard`, `memberOf`.
  - **Master adds:** `customProperty`, `hasCustomProperty`, `hasNetChain`, `inNetChain`, `inNetChainClass`, `isStackedVia`.
- **Properties:**
  - Any registered `PROPERTY` can be read, with `_` standing for a space. `NetClass` (a priority-ordered list), `ComponentClass`, `NetName` and `Type` have fast paths.
  - Undocumented in 10.0: pad `Pad_To_Die_Delay`, backdrill and post-machining properties, `Hole_Shape`; via tenting, plugging, filling and capping; zone `Keep_Out_*`, `Source_Type`/`Source_Name` (the multichannel source), `Remove_Islands`; tuning-pattern `Target_Skew_Delay`.
- **Graphical editor (10.0):**
  - Five categories: Electrical, Manufacturability, Highspeed, Footprints, Custom.
  - Condition rows offer Any, Net, Netclass, Within Area and Custom Query, combined with AND, OR, AND NOT or OR NOT.
  - 10.0.7 fixed the editor breaking time-domain rules.
- **Tuning profiles:**
  - A profile is Single or Differential. Per layer it holds width, unit delay and diff gap; vias have a global delay plus per-layer-pair overrides.
  - Profiles are assigned per net class.
  - DRC keys: `missing_tuning_profile`, `tuning_profile_track_geometries`.
  - 10.0.5 stopped profiles from always implying time domain. 10.0.7 allows a length tolerance as large as the optimum.
  - Any `length` or `skew` rule written in `ps` forces time-domain mode regardless of the profile setting.
- **Verified syntax**, from the doc examples plus the parser:
  - `(rule "USB delay" (condition "A.inDiffPair('/USB')") (constraint length (max 500ps)))`
  - `(constraint skew (max 5ps) (within_diff_pairs))`
  - `(rule "DP clearance" (condition "A.inDiffPair('*') && !AB.isCoupledDiffPair()") (constraint clearance (min 1.5mm)))`
  - `(rule front_courtyard_to_edge (layer "F.Courtyard") (condition "B.Layer == 'Edge.Cuts'") (constraint physical_clearance (min 3mm)))`
  - `(rule "TP spacing" (condition "A.Reference == 'TP*' && B.Reference == 'TP*'") (constraint courtyard_clearance (min 1.5mm)))`
  - `via_count (max 2)` with `hasNetclass('HS')`.
- **`kicad-cli pcb drc`** ([cli.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/cli/cli.adoc); identical on master):
  - Flags: `[-o] [-D KEY=VALUE] [--format report|json] [--all-track-errors] [--schematic-parity] [--units mm|in|mils] [--severity-*] [--exit-code-violations] [--refill-zones] [--save-board]`.
  - `--exit-code-violations` returns exit code **5** when violations exist.
  - Zones are refilled only with `--refill-zones`, and the board is saved only with that plus `--save-board`.
  - "Any errors in the custom rules will prevent the design rule checker from running."
- **JSON `drc.v1.json`:**
  - Top level: `$schema`, `source`, `date`, `kicad_version`, `violations[]`, `unconnected_items[]`, `schematic_parity[]`, `coordinate_units`, `included_severities[]`, `ignored_checks[]`.
  - Each violation: `type`, `description`, `severity`, `items[{uuid, description, pos{x,y}}]`, `excluded`, `comment`.
  - The schema has a trailing comma in `required` (invalid strict JSON).
  - **There is no rule-name field.** `description` reads like "Clearance violation (<source> clearance 0.2000 mm; actual 0.1500 mm)". Only the text `.rpt` adds the violating rule.
  - Freerouting writes the same drc.v1 plus a `freerouting_version` key, which `additionalProperties:false` would reject.
- **All 67 DRC type keys in 10.0:** unconnected_items, shorting_items, items_not_allowed, text_on_edge_cuts, clearance, creepage, tracks_crossing, copper_edge_clearance, zones_intersect, isolated_copper, starved_thermal, via_dangling, track_dangling, hole_clearance, hole_to_hole, holes_co_located, connection_width, track_width, track_angle, track_segment_length, annular_width, drill_out_of_range, via_diameter, padstack, padstack_invalid, microvia_drill_out_of_range, courtyards_overlap, missing_courtyard, malformed_courtyard, pth_inside_courtyard, npth_inside_courtyard, item_on_disabled_layer, invalid_outline, duplicate_footprints, missing_footprint, extra_footprint, net_conflict, footprint_symbol_mismatch, footprint_filters_mismatch, footprint_symbol_field_mismatch, lib_footprint_issues, lib_footprint_mismatch, unresolved_variable, assertion_failure, generic_warning, generic_error, copper_sliver, solder_mask_bridge, silk_over_copper, silk_edge_clearance, silk_overlap, text_height, text_thickness, length_out_of_range, skew_out_of_range, too_many_vias, diff_pair_gap_out_of_range, diff_pair_uncoupled_length_too_long, footprint, footprint_type_mismatch, through_hole_pad_without_hole, mirrored_text_on_front_layer, nonmirrored_text_on_back_layer, missing_tuning_profile, tuning_profile_track_geometries, track_on_post_machined_layer, track_not_centered_on_via ([drc_item.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_item.cpp)).
  - Master adds footprint_scaled_with_pads, hole_aspect_ratio, malformed_microvia_stack_span, microvia_crosses_core, microvia_stack_depth, microvia_stack_not_filled, net_chain_return_path, net_chain_stub_length, net_chain_tuning_profiles and via_stitch_overlap, and **drops zones_intersect**.
- **What DRC can express for placement intent:**
  - Can: courtyard spacing, side (`assertion` on `Layer`), orientation (`assertion` on `Orientation`), containment in a rule area, edge and keepout distances.
  - Cannot: pairwise distance between two footprints' pads, alignment, symmetry, loop area.
- **Open questions.**
  - Is `th`/`"`/`rad` accepted by some other path? This was concluded from source reading only.
  - How does `solder_mask_sliver` report?
  - Net-chain semantics are undocumented.
  - How does the GUI reload an externally edited `.kicad_dru`? The docs say "should not be edited with an external text editor".

### Implications for our system
- **Compiler rules:**
  1. Combine all predicates into one condition with explicit parentheses.
  2. Use one constraint type per rule.
  3. Order rules general to specific.
  4. Emit canonical `mm`, `deg` and `ps` only.
  5. Give each rule a stable `IR:<id>:<slug>` name and keep a sidecar map from rule name to IR constraint.
  6. Map violations back by regex on `description`, e.g. `\((rule '|)?([^ ]+)'? .*?; actual .*?\)`, or from the `.rpt`. Treat `type` as coarse only.
- **Lint every emitted file** by running `kicad-cli pcb drc` on a scratch copy.
- **High-speed classes, time-domain first:** a tuning profile per class via `SetNetClasses`, plus `length`/`skew` rules in ps with `(within_diff_pairs)`.
- **Write the custom checker only for what DRC cannot express:** pairwise pad distance, alignment, symmetry, loop area, return path on 10.x. Re-target return-path checks to native `return_path` if it ships in 11.
- **Build a second emitter** for the KiCad 11 `CustomRule` proto, which validates by Get/Set round trip.
- **Use one parser** for KiCad and Freerouting drc.v1. Tolerate the trailing comma and extra keys.

---

## 3. Routers available and how to drive them (with pitfalls)

### 3.1 Freerouting (GPL-3.0; ~2.1k★; pushed 2026-10-20)
- **What it is:** a Specctra DSN→SES router. CLI example: `java -jar freerouting.jar -de b.dsn -do b.ses -inc GND,VCC`.
  - Interfaces: Docker image; REST at `api.freerouting.app/v1` (beta); Python `freerouting-client` (MIT, 2.3.0).
  - Integrations: KiCad, Fusion, Target3001!, EasyEDA, tscircuit, pcb-rnd ([README](https://github.com/freerouting/freerouting)).
  - The PCM lists plugin 2.4.1 ("needs Java JRE 25", KiCad ≥6.0, SWIG), which lags upstream.
- **Releases [V]:**
  - v2.1.0 on 2025-04-12; the sole maintainer stepped back.
  - v2.2.0–2.2.4 in Apr–May 2026: fixed crashes on boards with more than two layers; auth on by default; stagnation detection; best-board restoration.
  - v2.3.0 on 2026-08-07: `BatchFanout` SMD pre-pass, opt-in `strict_drc`, MCP over JSON-RPC/SSE/WebSocket, A2A card at `/.well-known/agent.json`, and `--router.copperToEdgeClearanceUm`.
  - v2.4.1 on 2026-09-03: core decoupled from Swing/AWT; CLI, REST and GUI share one pipeline; PCBench suite added; "DSN/SES path is still the recommended production route".
  - v2.5.0 on 2026-10-05 ([release](https://github.com/freerouting/freerouting/releases/tag/v2.5.0)):
    - "direct Protocol Buffers IPC integration for KiCad 10+", routing in a separate process, with fallback to DSN/SES;
    - GraalVM native binaries (Linux x64, macOS arm64/x64, Windows x64; no JRE);
    - `POST /v1/autoroute` and MCP `autoroute_board`;
    - `compact=true` DRC ("drops raw coordinate bloat by >70%");
    - `normalized_score` on a 0–1000 scale; a deterministic post-route optimizer; pour and plane awareness;
    - PCBench table: clean boards **358 (30.9%) → 868 (75.0%)**; fully routed 600 → 872 (75.4%); timeouts unchanged at 78; total time 3,251 s → 2,997 s; Tier C (6+ layers) 49.2% clean, Tier D 50%;
    - "legacy KiCad SWIG support will be removed in the next release".
- **CLI flags** ([doc](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md)):
  - `-de` (DSN, optionally `+ses+rules`), `-do` (.dsn/.ses/.scr), `-dr`, `-drc` (KiCad JSON), `-mp`, `-mt` (0 disables optimization).
  - `--router.optimizer.improvement_threshold` (default 2.5%), `-inc`, `-im`, `--gui.enabled=false`, and **`-da` to disable anonymous analytics**.
  - API server default `http://127.0.0.1:37864`, with authentication enabled.
- **REST API** ([API_v1.md](https://github.com/freerouting/freerouting/blob/master/docs/API/API_v1.md)):
  - Required headers: `Freerouting-Profile-ID` (UUID) and `Freerouting-Environment-Host` (e.g. `KiCad/10.0`; 400 if missing). Bearer auth unless disabled.
  - Sessions and jobs: enqueue, settings, start, cancel, logs and stream, uploads, partial output (202 while running).
  - `GET /jobs/{id}/drc[?compact=true]` and `/drc/summary`, which gives "spatial congestion hotspots and… auto-correction hints".
  - `POST /v1/autoroute` takes `file_content`/`rules_content`/`session_content`, `output_formats`, `timeout_seconds` and `router_settings`.
  - MCP is at `POST /v1/mcp`.
- **MCP:** `autoroute_board(filePath|fileContent, rulesPath, sessionPath, outputFormats ["SES","DRC_SUMMARY"], timeoutSeconds)`, plus a multi-turn workflow ([MCP.md](https://github.com/freerouting/freerouting/blob/master/docs/API/MCP.md)). The npm `@freerouting/freerouting-mcp-server` v2.5.0 is GPL-3.0-only.
- **Scores** ([scoring.md](https://github.com/freerouting/freerouting/blob/master/docs/scoring.md)):
  - `V2_CONTINUOUS` = max(0, 1000 − W1·o1 − W2·o2 − W_C·N_viol/D − W_D·ΣL_um/(U·D)). The open fraction is split at F = 0.5, W1 ≈ 333.3, W2 ≈ 666.7, D = max(1, pins × signal layers).
  - `V2_LOWER_BOUND` compares length against a Manhattan MST, vias against a per-net minimum, and bends against a minimum. Incomplete nets and DRC hits are vetoes.
- **Pitfalls documented by the four MCP codebases (MCP §2F, §3):**
  - SES `(resolution um 10)` declares a grid, not a multiplier: 1 mm = 1000 units, Y negated (PRO had coordinates 10× too small).
  - DSN turns internal Edge.Cuts holes into keepouts cleared at track clearance (0.2 mm), not edge clearance (0.5 mm). The copper-to-edge flag does not fix it ("byte-identical SES"). Fix by growing circular keepouts by the difference, sized by apothem; on the test board this took 8 violations to 0.
  - Leading `/` lost on net names. `.kicad_pro` netclasses missing from the DSN.
  - The SES `(placement)` block aborts the import on renamed duplicate `REF**` references; strip it.
  - Read the required Java version from the JAR's class-file major version (2.4.x needs Java 25).
  - Guard against stale SES files and stage artifacts in a temp dir.
  - Freerouting prints "Multi-threaded route optimization is broken… generate clearance violations" on every run, so use **`-mt 1`**.
  - A single run routinely leaves 1–7 nets unrouted on dense boards. **Best-of-N**: 3 attempts is usually enough for 4-layer designs, 5–8 for stubborn ones. Score = `nets_routed·1000 + segments + 50,000` if all target nets route (from morningfire-pcb-automation, MIT).
  - `ImportSpecctraSES` returns `False`, and "False == 0" made failures report success.
  - Footprint keepouts must be promoted to board level, and displaced text fixed after import (POA).
  - Konnect's DSN exporter fails closed on zones, rule areas, arcs or unlocked tracks, and supports two layers only (roadmap).
  - Always lock copper to keep before import (§0 item 2).

### 3.2 fastroute (GPL-3.0-or-later; 107★; created 2026-09-29)
- A Rust "derivative work of Freerouting" adding bug fixes, length matching, controlled impedance and diff pairs. Its KiCad plugin carries `.kicad_dru` rules over DSN.
- Self-reported over 20 boards: 2,102 s (Freerouting), 510 s, and 420 s with PGO. Memory 1–2 GB versus 20–300 MB.
- `--parity` gives SES byte-identical to Freerouting's deterministic mode on all 20 boards. It fixes the optimizer never running after a self-stop and traces ignoring the outline for edge pads. It has a `--live` view ([README](https://github.com/parisxmas/fastroute)).

### 3.3 KiCad PNS router, headless: PCBWorld-Engine (GPLv3; 5★; created 2026-08-29)
- "KiCad's push-and-shove router exposed through a pybind11 binding and served… over a unix socket", derived from **KiCad 9.0.8** and built with kipy 0.6.0 ([repo](https://github.com/LGAI-Research/PCBWorld-Engine)).
- **58 Python APIs:** 14 reproduce `PNS::ROUTER`, 28 wrap KiCad DRC and board-state extraction, 16 are utilities.
- **Primitives:** `fix_route`, `cancel_route`, `finish` (complete to the Euclidean-nearest unconnected pad), `flip_posture`, `toggle_via`/`switch_layer`, `set_routing_mode` (mark_as_obstacles/push_n_shove/walkaround), `set_corner_mode` (45°/90°).
- Per-netclass widths and vias are pushed into PNS on net selection. **Copper pours are not in PNS space** ([paper](https://arxiv.org/html/2607.05915)).
- Horizon EDA (GPL-3.0, 1,324★) also embeds the PNS sources and lists an autorouter as a **non-goal** ("rarely useful for small to medium-sized boards").

### 3.4 KiCadRoutingTools (KRT; MIT; 549★; ~5,856 commits; created 2025-12-13)
- **Engine:** a grid-based octilinear multi-layer A* with a Rust core ("~10× faster than pure Python").
- **Features:**
  - rip-up and reroute;
  - diff pairs via pose-based A* with a Dubins heuristic;
  - length and **time** matching;
  - plane pours and repair;
  - BGA/QFN fanout, bus routing;
  - placement optimization for routability;
  - DRC and connectivity checkers;
  - a "design brief", graded floorplan intent, a KiCad-oracle reconnect, and a plugin GUI for KiCad 9 and 10.
- **Limits:** no push-and-shove, no blind or buried vias, no coarse or global grid assignment, no region-based rules.
- **10 skills:** `/pcb-free-agent` (ends with "one independent verifier"), `/plan-pcb-routing`, `/analyze-power-nets`, `/find-high-speed-nets`, `/identify-diff-pairs`, `/recommend-stackup`, `/recommend-plane-mappings`, `/diagnose-routing-failures`, `/review-routed-board`, `/stress-test-router`. There is an AI tab backed by Claude Code or opencode.
- **Distribution:** works on `.kicad_pcb` files, not IPC. PCM 0.22.1 (KiCad ≥9, SWIG).
- **Self-reported results:** 47/47 FTDI nets in 8.6 s; 28/28 LVDS pairs in 29.7 s ([repo](https://github.com/drandyhaas/KiCadRoutingTools)).

### 3.5 Other open routers
- **rjwalters/kicad-tools** (MIT; PyPI 0.24.0, 2026-10-20; ~6.9k commits): file-based. A* with an optional C++ backend ("10–100× A* speedup"), `kct route-auto`, and extras `[cuda]`, `[metal]`, `[native]`, `[placement]`, `[mcp]`. It self-reports that KRT is faster on sparse and medium boards while it does better on some dense ones. TraceMaker scores ≈0.99/1.00/0.90 against Freerouting 2.2.4 at ≈0.7/0.7/0.2.
- **tscircuit `@tscircuit/capacity-autorouter`** (MIT; npm 0.0.995, 2026-10-20 17:26 UTC):
  - "hundreds of algorithms organized in a Pipeline", using successive approximation and hypergraphs, with a `CapacityMeshSolver`.
  - `AutoroutingPipelineSolver(simpleRouteJson)` with a `step()` loop. SimpleRouteJson supports `buses[].maxLengthSkew` and diff pairs with `lengthTolerance`.
  - Benchmarks: SRJ33 DRC-failure set (37 inputs) and an online dashboard.
  - Community: the default router is "hard to steer"; `pcbPath` overrides exist [S].
- **OrthoRoute** (MIT; v1.0.0; KiCad ≥10 IPC): a Manhattan lattice plus PathFinder with a CUDA 12/CuPy or Metal SSSP kernel; nets are routed sequentially. It is "not a general-purpose PCB autorouter" and "useful to about five people on the planet".
- **Fanout Tool** 1.0.0 (MIT, IPC): QFN/QFP/BGA escape with "3-segment routing algorithms".
- **Topola** (MIT; Codeberg; NLnet NGI0 Entrust): an interactive topological router, still a work in progress. Crates: `specctra-core`, `topola-cli`, `topola-egui`, `planar-incr-embed`. Version 0.1.0, 33★.
- **route-rnd** (GPL-2+; Debian 0.9.3): speaks tEDAx. Algorithms are `rt_topo` (libgrbs rubber-band), `rt_horver` (needs pins on a grid, preferably ≥100 mil) and `rt_hace`. Known issues: detours and unnecessary curves.
- **Historical or stale:** gEDA Toporouter (2008, after Dayan's thesis; the claim that it was adapted for KiCad is dubious); vygr C-PCB family (GPL-2.0, stale); Ruby-PCB-Router (2016).
- **EasyEDA local router** (GPL-3.0): a headless Freerouting fork on `ws://127.0.0.1:3579/router`, DSN in and JSON out.
- **LibrePCB** (GPL-3.0): no router, but DSN/SES export and import since 1.2.0.
- **OpenROAD** project **SA-PCB** and **PcbRouter** are BSD-3 (LIC).
- **Commercial DSN back ends:**
  - **Allegro PCB Router.** Specctra by Cooper & Chyan, 1989; Cadence since May 1997. Shape-based, with rip-up and push-and-shove and Do-file strategies. Wikipedia lists the latest version as 17.4–22.1 (2022).
  - **Konekt Electra.** Shape-based multi-pass cost-based conflict reduction; up to 256 layers; diff pairs and length; DSN in, SES/RTE out; lists KiCad. v10.10 July 2026. PRO-30 €145/month, PRO-UL €2,495 perpetual.
  - **TopoR.** Topological with no preferred directions; now a module of Russian Delta Design; English page 404.
  - **Altium Situs.** Topological. Its own doc: "Differential pairs nets must be manually routed and locked before using the autorouter"; it obeys all rules except Routing Corners.
  - **"PCB Auto Router" (pcbautorouter.top).** Claims GPU RL; closed.
  - **EasyEDA Pro V3.2.148 (2026-06-01).** "Dual engine" auto placement and routing with equal-length diff pairs. V3.2.206 fixed a low V4 routing rate.
- **DSN/SES is the lingua franca**: every router above, open or commercial, speaks it (ET).

### 3.6 Measured head-to-head: PCBWorld-Bench
LG AI Research, arXiv 2607.05915, KDD 2026 workshop (non-archival) [P].

**@5 results (best of 5), v2 Table 3** [V]:

| Method | D2 CP | D3-A CP / Rout. (99 boards) | D3-B CP / Rout. (10 boards) |
|---|---|---|---|
| Freerouting 2.1.0 | 1.00 | 0.80 / 0.91 | 0.78 / 1.00 |
| KRT | 1.00 | 0.74 / 0.94 | 0.20 / 0.86 |
| OrthoRoute | 0.01 (rout. 0.34) | 0.02 / 0.53 | 0.00 / 0.44 |
| GPT-5.4 via PCBWorld tools | 0.96 | 0.65 / 0.91 | 0.00 / 0.62 |
| GPT-5.4-mini / -nano / Qwen3.5-397B | 0.58 / 0.55 / 0.33 | 0.28 / 0.30 / 0.34 | 0.00 |
| PPO transformer (trained on synthetic D2 only) | 1.00 | 0.86 | 0.45 |

- **Times on D3-A:** Freerouting 7.09 s, KRT 0.65 s, GPT-5.4 231 s (231–866 s per board per VK), PPO 1.83 s.
- **Engine engagement (GPT-5.4, D3-A):**
  - interactive CP 0.65 (DRV 1.31);
  - plan-and-execute 0.19 (DRV 16.28);
  - engine-free 0.02;
  - in engine-free mode, nano produced no loadable file in any rollout on 10% of boards.
- **One-attempt results (v4 Tables 21–22 as reproduced by DeepPCB [vendor]):** GPT-5.4 0.42/0.00; Freerouting 0.75/0.64; PPO 0.81/0.22; KRT 0.74/0.20; Qwen 0.19/0.00; OrthoRoute 0.02/0.00. DeepPCB claims 0.929 (D3-A) and 0.800 (D3-B, 3 attempts), with 0.59×/0.50× the vias and 0.94×/0.95× the length, in 3 min of engine time. Almost all boards are 2-layer.

### Implications for our system
- **Freerouting** is the default bulk router, run as a supervised subprocess, local REST service or MCP service **only** **[MPL-flip: ET's "vendor or fork Freerouting" is out]**.
  - Pin the binary by hash, pass `-da`, and use `-mt 1` with best-of-N.
  - Apply every pitfall fix above.
  - Expose one tool, `route_with_freerouting(board, nets?, timeout)`. It returns `normalized_score`, `optimizer_score`, the unrouted count and the compact DRC summary, never geometry.
- **PCBWorld-Engine** is the interactive, DRC-aware primitive for critical nets and repair. It runs as a **separately distributed GPL process over a socket**. Porting it to KiCad 10/11 is GPL-side work, and it cannot reach pours.
- **KRT and kicad-tools** (MIT) can be used in-process for fanout, diff pairs, plane repair and time matching.
- **tscircuit's capacity mesh** (MIT) is a design reference for fast congestion estimates.
- **Keep DSN/SES first-class** so users can plug in Electra, TopoR or Allegro.
- **Benchmark against Freerouting 2.5.0**, not the paper's 2.1.0.

---

## 4. Placement engines available

- **KiCad itself:** no API, only the 2012-era autoplacer through `RunAction`.
- **PCM placement plugins** (index 2026-10-19):
  - Place Footprints 5.0.0 (GPL-2.0) and Replicate Layout 5.0.1 (GPL-2.0; still a KiCad 10 build even though its README says the feature went native).
  - Save/Restore Layout 4.0.0, SubLayout 0.2 (BSD-3), HierarchicalPCB 1.1.0 (MIT), Layout Clone 0.3.3 (MIT, IPC).
  - Parts Placer 0.1.14 (LGPL-2.1, spreadsheet), Place By Sch 2.2.0 (GPL-3.0), KLEPlacement, kbplacer, PosOrient, Snap To Grid.
  - **None is an optimizing autoplacer** ([packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json)).
- **Cypress** (NVlabs; Apache-2.0; 55★; 746 commits):
  - A GPU, DREAMPlace-style placer. Abstract claims: 1–5.9× routability, 1–19.7× shorter routed length, up to 492.3× speedup, and a benchmark suite "synthesized from real commercial designs". The paper is closed-access.
  - Repo: `benchmarks/small-1…small-20`, `pcb-util/kicad_converter.py` plus a Bookshelf converter, `tuner/`, `dreamplace/`. Run with `python dreamplace/Placer.py config.json`.
  - `enable_rotation` defaults to **0**. Parts keep their TOP/BOTTOM side (bottom written as `FN`) and can be marked `/FIXED`. No side (flip) optimization was found ([params.json](https://github.com/NVlabs/Cypress/blob/main/dreamplace/params.json)).
  - Context from solver_toolbox.md: ISPD 2025 Best Paper. DREAMPlace (BSD-3) pins old toolchains.
- **kicad-tools** (MIT): force-directed, GA and hybrid placers, plus CMA-ES/Bayesian `kct optimize-placement`.
- **KMS `suggest_placement`** (MIT; still DRAFT):
  - Fruchterman-Reingold-flavoured relaxation. Nets attract, overlapping courtyards repel, and the outline contains. Power-net name fragments (VBAT, VCC, +3V3) and IC↔decap links are weighted.
  - A pin-facing rotation pass tries 0/90/180/270 to minimise pad-level wirelength, then snaps to grid. It reports pad-level HPWL and is dry-run unless `apply=true`.
  - Intended loop: suggest(dry) → courtyard check → apply → autoroute best-of-N → DRC.
  - KMS also vendors **HierPlace v1.1.0** (MIT, Dave Vandenbout).
- **Konnect placers** (AGPL; reference only):
  - Introduced 2026-08-26: `score_placement`, `place_decoupling_caps`, `plan_bga_fanout`, union-find `auto_place_from_schematic`, `refine_placement_force_directed`.
  - Bug: they moved locked parts because `(locked yes)` was never parsed, and a loose text search counted all 15 ecc83 parts as locked via the nested `(unlocked yes)`.
  - Force-directed blocked 2026-09-18: the "global-net spring model can pull one footprint toward every other footprint sharing a board-wide rail", and non-converged plans had been applied. Plans now need convergence, a strict score improvement, no hard failure and a `max_displacement_mm`.
  - **Retired 2026-10-01 (#754):** "autonomous whole-board mutation is retired". Use small explicit moves, then read back, score and run DRC. Decap association now requires a shared non-ground net with ≤8 references.
  - Constants: `K_SPRING 0.4`, `K_REPEL 80`, `K_WALL 5`, damping 0.85, grid 0.5 mm, patience 4; power nets 3×, diff pairs 5×.
  - `score_placement`: hard failures are same-side courtyard overlap and parts outside the outline. Soft weights: overlap ×20 (cap 40), outside ×20 (cap 40), connector >10 mm from edge ×15 (cap 30), decoupling ×15 (cap 30). **The weights are ported from kicad-mcp-pro (MIT)**, so take them from there.
  - The outline is classified rectangular, unproven or missing. On unproven, checks are skipped "as unproven rather than silently passed".
- **kicad-mcp-pro** (MIT): a spring embedder with Coulomb repulsion, walls, spiral free-spot search and keepouts, plus a BGA fanout planner. Tools include `pcb_auto_place_by_schematic`, `…_force_directed`, `pcb_group_by_function`, `pcb_place_decoupling_caps`, `pcb_critique_placement` and `pcb_score_placement`.
- **KRT placement doc:** "The killer isn't the algorithm — it's **constraint capture**." It argues for refining from a seed rather than placing from scratch, with experiments in June–Aug 2026 including router-in-the-loop repair (`place_route_loop.py`) ([doc](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md)).
- **tscircuit "Sequential Optimal Packing"** (blog, 2026-04-01):
  - Packs chips in a Pack Order, choosing each position by a Cost Function along the boundary of the parts already packed.
  - Pure space-minimising packing makes boards "nearly impossible to route", and force-directed placement is "wildly unpredictable".
  - "LLM loops can easily adapt the design intent representation", e.g. by hardening "pack decap with its chip". tscircuit's own placement is manual (`pcbX`/`pcbY`) with flex/grid autolayout in development.
- **Others:**
  - CadMust-Neo (simulated annealing plugin, 29★).
  - RL_PCB (MIT; DATE 2024; trained on 6 circuits; Python 3.8, PyTorch 1.13).
  - kicad-kbplacer (keyboards, 543★), kicad-auto-silkscreen (refdes), VelaTrace.
  - BSD-3 analog placers ALIGN and MAGICAL, and SA-PCB (LIC).
  - Packing libraries jagua-rs (MPL-2.0) and sparrow (MIT) (LIC).
  - OpenROAD (BSD-3) targets a different problem: millions of uniform cells versus tens to hundreds of heterogeneous parts.
- **Commercial placement:**
  - DeepPCB RL placement, out of beta since 2025-04-15: up to 1,000 components and 2,200 pins. Examples: 48 caps around a fixed chip, where a 2-min placement led to 10 h of routing and a 30-min placement to 59 min with fewer vias. RPi CM base board: a 6-min placement routed fully in 7 h (111 vias after 24 h); a 14-h placement routed fully in 4.5 h (79 vias after 6 h).
  - Quilter "[BETA]" placement engines (2026-07-31) "can neglect some of your constraints".
  - Cadence Placement AI.
  - Zuken "Smart Placement is under development".
  - EasyEDA Pro dual engine.
- **Evidence on proxies (Cadence US 12,223,248 [P-pat]):**
  - 12,000 GA placements of one 350-component board, each autorouted.
  - HPWL correlates with routability at r = −0.923, normalized crossings at r = −0.898.
  - At crossings ≈0.075, routability still ranged 0.83–0.94, while rerouting the same placement varied by only σ ≈ 0.005. So proxies cannot rank close candidates.
- **No placement quality numbers** are published by any MCP codebase.

### Implications for our system
- **Placement is the main build item.** Practitioners call it the hard problem; every open AI tool punts; Konnect retired its global placers.
- **Architecture:**
  1. The LLM produces a floorplan and intent: groups by sheet and function, edge connectors, mounting holes, decap proximity, thermal and noisy-versus-sensitive zones. Emit these as KiCad artifacts: rule areas, component classes, custom DRC, keepouts.
  2. Seed with Sequential Optimal Packing or human-like priors.
  3. Refine numerically with force-directed, SA or analytical methods (Cypress via Bookshelf is an option).
  4. Legalize.
  5. Generate N diverse candidates and **route the top-k to rank**.
- **Build the independent scorer first**, using PRO's MIT weights, polygon courtyards and non-ground decap associations. No apply unless the score strictly improves.
- **Give the LLM a small-explicit-move path** for most edits.
- **Use multichannel `repeatLayout` and Design Blocks** for repeated channels.

---

## 5. MCP server landscape and lessons

### 5.1 Landscape (stars and dates as of 2026-10-20)
- **Scale.** GitHub "kicad mcp" returns 233 repos, and the llm/claude/gpt/agent query returns 194. RepoRecon's "KiCad AI" list has 275 entries, of which 11 have ≥50★ and 13 have ≥10★ ([RepoRecon](https://devbisme.github.io/RepoRecon/?topic=kicad_ai&filter=&sort=stars:desc)).
- **PCM.** The official index (2026-10-19) has 132 packages: 97 plugins, 18 themes, 17 libraries. A regex scan for AI/LLM/GPT/Claude/MCP/assistant/copilot/chat found **zero AI or LLM plugins**. 18 plugins already use the IPC runtime, e.g. OrthoRoute, Fanout, Layout Clone, Via Stitching, Z0 Field Solver (which writes net classes and rules). DeepPCB is not listed.
- **Leaders:**

| Project | ★ | License | Interface | Notes |
|---|---|---|---|---|
| mixelpixx/KiCAD-MCP-Server (KMS) | 2,881 | MIT | TS MCP + Python subprocess; SWIG + IPC (~22 IPC handlers, "experimental") | v2.8.2; 244 tools (184 indexed, 32 "essential"); Freerouting via Java/Docker/Podman; JLCPCB catalog |
| mixelpixx/Konnect | ~1.3k | AGPL-3.0 + commercial + CLA | single Rust binary; KiCad 10 IPC; S-expr schematic; kicad-cli | BETA; 228+7 tools; ~23K tokens for all vs ~2K starter; 6 skills, 2 agents; stdio or Streamable HTTP |
| aklofas/kicad-happy | 1,464 (~1.5k) | MIT | skills (Claude Code, Codex, opencode) | 11 skills (kicad, spice, emc with 44 checks, datasheets, bom, distributors, jlcpcb, pcbway); KiCad 5–10; corpus 5,800+ repos, 3,498 PCBs; v2.3.1 (README also says stable v2.1.0) |
| i2cjak/Backplane | 673 | MIT | ships a **KiCad fork** with extra LLM instrumentation (IPC schematic API) | no placement or routing |
| copperheadhq/copperhead | 614 | Apache-2.0 | S-expr + kicad-cli loop; git snapshot per mutation, rollback on failure | "**Not an autorouter**"; loop "not been observed passing end to end"; Show HN 250 pts |
| drandyhaas/KiCadRoutingTools | 549 | MIT | files | real router + placement optimizer; 10 skills |
| lamaalrajih/kicad-mcp | 527 | MIT | read-only; stale since 2025-10-17 | pattern recognition (buck/boost/LDO) |
| salitronic/eda-agent | 262 | Apache-2.0 | Altium (DelphiScript) + KiCad IPC | schematic autoplace only (Sugiyama/FD, VF2 motif composer); "minimal" mode exposes only `tool_catalog` + `tool_invoke` |
| Seeed-Studio/kicad-mcp-server | 163 | README MIT, **no LICENSE file** | SWIG + text fallback | edits need KiCad restarted |
| oaslananka/kicad-mcp-pro (PRO) | 142 | MIT | FastMCP; kicad-cli + IPC + S-expr; no SWIG | v4.3.0; 387 tools; SI/PI/EMC/thermal "closed-form estimates (~5–10% accuracy)"; "not an automated sign-off authority" |
| paul356/KiCad-AI-Assistant | 119 | MIT | KiCad ≥10 wxPython panel with embedded MCP (111 tools, 15 categories; PyPI `kcaa`) | Freerouting; Ollama tool calls failed until the context was raised to 128k |
| ProductOfAmerica/mcp-server-kicad (POA) | – | **GPL-3.0+ since 2026-10-14** (MIT ≤0.20.1) | byte-preserving CST + kicad-cli | v0.21.1, maintenance mode; 109 tools |
| rjwalters/kicad-tools | 70 | MIT | files | placers + router; ecosystem audit |

- **Others:**
  - circuitron (128★, MIT); pcbcraft (66★, GPL-3.0, Rust); blwfish (71 tools); Netlist-Studio; Finerestaurant (stale); biosshot/kicad-copilot.
  - BeckhamLabs kicad-jlcpcb (hands off to EasyEDA routing); circuit-synth/kicad-sch-api (MIT); IntelligentElectron/universal-netlist (Apache-2.0).
  - zxkmm/kicad-harness (33★); **Zane456/PCB-Agent-Teams (76★, "Noncommercial", not reusable)**; nevenfo/kicad-agentic-mcp ("LLM-based planning… deterministic execution, state tracking, evidence, rollback"); devbisme/boardforge; ChengminLi/AI-PCB-layout (human review gate after every step); JITx-Inc/jitx-skills (9 skills).
  - **HeyPCB** (MIT client in front of a paid cloud `build_board`; bound folders are uploaded on change).
  - **Adom/Hydrogen KiCad Bridge** (Windows Rust bridge driving the user's GUI; "$10M from NSF" claim unverified).
  - assalas/pcb-designer-ai-agent (137★; a buzzword list; treat with suspicion).
- **Non-AI libraries:**
  - InteractiveHtmlBom (4,610★), kicad-jlcpcb-tools (2,113★), KiKit (2,046★, 1.8.1, 2026-08-05), SKiDL (1,697★, 3.0.0, 2026-10-16).
  - kicad-skip (LGPL; last PyPI 0.2.5, 2024-02-16) and **kiutils (GPL-3.0; last 1.4.8, 2024-02-02)** are both stale for 9/10 formats.

### 5.2 Measured results
- **devbisme ai-circuit-design-tests:** a dual-channel 10 MS/s 12-bit USB 2.0 ADC board from blank. Results are unvalidated ([repo](https://github.com/devbisme/ai-circuit-design-tests)):
  - Konnect: "routed 4-layer, DRC clean", $61.12.
  - kicad-happy: 0 errors, $29.37.
  - KMS: 4 DRC errors (stock USB-C footprint), $16.93.
  - PRO: 0 errors, $19.42. eda-agent: 0, $18.47. KiCad-AI-Assistant: 0, $19.38. kicad-harness: 0, $10.87. boardforge: 0, $23.89.
  - **Null baseline (Claude Code with no KiCad tools):** routed 4-layer with 0 ERC/DRC errors, $11.16, but "signals routed through the In1 GND plane".
  - Forum summary, 2026-10-14: "**I tested seven tools that actually created a routed PCB and they all used Freerouting.**"
- **POA maintenance-mode A/B** (Claude Opus 5.5 with and without the plugin, judged by KiCad 10; "small tests on one design"; materials unpublished):
  - Single edits: plain Claude Code got **18/18**, the plugin 3/18.
  - In a 20-edit session both got everything right, but the plugin used **~1.8× the context**.
  - Causes: missing tools (pad net, DNP, footprint swap); "never edit files" made the model stop and ask; board sync rewrote almost every footprint, "so the model undid its own work".
  - Conclusion: "Plain Claude Code changed a 2 MB board without reading it whole."
- **Catalogue cost:** PRO's expert profile is 387 tools, 227,578 characters, ≈56,895 tokens; its default profile is 24 tools, ≈2,337 tokens (−95.9%). Konnect: ~23K tokens for all tools versus ~2K for the starter kit.
- **Deferred tool schemas:** POA found that "'place a 10k resistor' cost three tool_search calls" in hosts that defer schemas.
- **Generated layouts:** POA found "16 of 36 generated layouts built the way the repo's skills prescribe came out shorted", and the wrong pin was wired in 4 of 12 orientations.
- **Dynamic toolsets failed over stdio:** "172 of 185 tools… were unreachable" after `load_toolset` in Claude Code, because `list_changed` reached only HTTP/SSE clients.

### 5.3 Recurring bug classes (MCP §2; all four codebases, often in the same month)
**Fix-commit counts (KMS / Konnect / PRO / POA):**
- rotation, flip, transform: 19/12/5/12
- KiCad 10 compatibility: 13/7/7/3
- stale or live state: 11/11/3/3
- nets: 15/14/7/20
- library tables: 28/43/6/11
- IPC transport: 15/27/4/0
- Freerouting: 7/6/1/9
- all fixes: 292/358/275/227

**The six classes:**
1. **Transforms.**
   - The textbook rotation matrix is wrong for KiCad's Y-down frame: `board_x = fp_x + lx·cosθ + ly·sinθ`, `board_y = fp_y − lx·sinθ + ly·cosθ`. The two forms agree at 0° and 180° but not at ±90°.
   - POA's fix matched 2,970/2,970 drilled pads (versus 2,292 before) and all 1,231 B.Cu SMD pads against Gerber flashes. The bug had hidden behind square courtyards.
   - Mirror applied before rotation misplaced 28/84 pins. Back-side children are already stored flipped.
   - IPC serializes footprint children in absolute coordinates, contrary to the proto comment. Updating only position therefore corrupted boards; Konnect now applies `SetPosition`/`SetOrientation` rigid transforms.
   - Flip rule: angle → (180 − angle) % 360 with local Y negated, plus a layer flip map and tenting swap (10 only).
   - Angle spellings `+90`, `9_0` and `1e-400` break KiCad's parser while Python reads them as numbers.
   - Write 270, not −90, and compute in integer nm with KiROUND chosen by format era.
2. **Silent data loss on write:** see the kipy 3D-model, `SaveBoard`, net-rebinding and torn-write items above. NTFS `O_TRUNC` gave 345/800 torn reads, versus 0/25,529 with atomic writes. `layer="banana"` wrote an unloadable file. Concurrent writes lost edits.
3. **Live versus saved divergence:**
   - Konnect's scorer read the saved file and returned "pass, score 70" despite a real live collision.
   - KMS: `SaveBoard` clobbered external edits; the guard is now content-hash, not mtime.
   - KMS: an empty IPC read reported success; KMS #223 lost edits.
   - KMS: replies shifted by one after a timeout, so requests now carry IDs.
4. **KiCad 9→10 breaks:** formats, nets, layers, DRC JSON, padstacks. A raw-connect socket probe wedged KiCad's NNG server until restart (#498). IPC handlers ignored `unit`, so parts landed at 1/25.4 of the intended position.
5. **"Success" that wasn't:** Konnect's DRC parser dropped `unconnected_items` and `schematic_parity` (ecc83 test: 17 violations plus 14 unconnected reported as 0). `check_clearance` returned the anchor-to-anchor distance as "physical clearance". The `False == 0` bug.
6. **Freerouting round trip:** see §3.1.

**Most of these bugs were found only by comparing against KiCad's own output**, not by unit tests.

### 5.4 Test practices worth copying
- **POA:**
  - ~1,950 tests in rungs 1–7 (bytes/tokens → geometry → single edits → whole-file reads → one tool call → composite tools → end to end). "Every test has a judge that is not the code under test."
  - An autouse `kicad-cli` load check on every file a test leaves behind. The only allowed xfail is a strict one naming a numbered bug.
  - Hypothesis runs 200 examples in CI and 5,000 nightly.
  - CI: Linux with KiCad 9 and 10; macOS and Windows with KiCad 10.
  - `pcbnew_judge` runs scripts under KiCad's own Python; `kicad_ref` ports KiCad routines; `kicad_corpus` sweeps the installed demos.
  - The routing harness compares `kicad-cli` netlist node sets before and after each call.
- **Konnect:**
  - ~2,445 tests, an NNG mock, and live tests on a disposable board. Weekly Windows E2E with choco-installed 10.0.5.
  - Governance requires a **negative control**: neutralize the guard and show its test fails.
  - Fixtures: 20 boards, including the Antmicro Kria K26 (Apache-2.0) for transform ground truth.
  - Live DRC recipe: create and save a via, delete it unsaved, show file-only DRC still reports its UUID, then show synced DRC drops it.
- **PRO:**
  - ~5,250 tests and a 14-project golden corpus with per-gate outcomes: `pass_minimal_mcu_board`, `pass_sensor_node`, `fail_bad_decoupling_placement`, `fail_footprint_overlap_board`, `fail_dfm_edge_clearance`, `fail_dirty_transfer_wrong_pad_nets`, `fail_sensor_cluster_spread`, `fail_label_only_schematic`, plus KiCad 10 feature cases.
  - Tool-selection evals declare `expected_tools`, `forbidden_tools`, a safety tier and `max_calls`, and score recall, safety, unnecessary calls and nondeterminism.
  - Attempt accounting (#730): failures stay in the denominator; an "infrastructure_invalid" exclusion is refused if any tool call happened; `manual_repair=true` is not autonomous success; manifests carry SHA-256 digests.
- **KMS:** mostly `MagicMock` pcbnew stubs (the weak pattern). Real pcbnew runs only with `KICAD_USE_REAL_PCBNEW=1`.

### 5.5 Recommended tool-surface spec (MCP §6, untested)
- **State model:**
  - A session is bound to one board identity: project, board and KiCad instance token.
  - `backend` is `ipc_live` or `file`. Once a board has been seen live, file writes are refused.
  - Every response carries `{source, board_rev (SHA-256 of normalized snapshot or file bytes), kicad_version, outcome}`.
  - Transport: correlate requests by ID, never probe the socket, bound timeouts, never retry an uncertain write.
- **Tools** (lengths in mm; angles CCW as KiCad displays them; Y-down board frame):
  - **Read**, all bounded: `board_summary` (outline rect/polygon/unproven), `list_footprints`, `get_pads` (through the single transform module), `get_netlist`, `get_ratsnest` (+ total HPWL), and `render` (PNG only when asked).
  - **Referee:** `score_placement` (pass/hard_fail/outline_unproven/outline_missing), `run_drc` (sync, refill; never drops unconnected or parity results; parity null if not run), `check_connectivity` (netlist node sets).
  - **Propose** (deterministic, never write): `propose_placement` (refuses unproven outline; non-improving candidates are `blocked`), `propose_moves`, `propose_route` (Freerouting with every §3.1 fix, `pad_to_pad` or fanout; `keep_existing=locked_only`), `propose_fanout` (dogbone or inline).
  - **Apply:** `apply_candidate(id, expected_rev)` (one chunked commit or an atomic splice), `undo_last`, `revert_to`, `snapshot`, `diff`.
  - **Escape hatches:** `kicad_cli` (drc, erc, export, render, upgrade only; outputs to temp) and `raw_edit` (anchor-UUID CST splice + load check + connectivity; refused while the board is open live).
- **Hooks on every apply:** read back against intent; check 3D-model, field and pad counts; run score or DRC; check connectivity; confirm the format stamp is unchanged. Any mismatch makes the outcome `partial` or `uncertain`, naming the first mismatch.
- **Core size:** about 12 always-visible tools named in the server instructions; load toolsets only if the client honours `list_changed`.

### Implications for our system
- **Differentiate on placement and routing quality and the verify loop**, not on tool count.
- **Separate read/score, propose and apply.**
- **Never forbid file reads or `kicad-cli`.** Give tools for every edit class, or a verified raw edit.
- **Build one clean-room transform module, oracle-pinned** to `kicad-cli` drill and Gerber output on asymmetric fixtures, at four orientations, on both sides.
- **Never re-serialize whole objects** through pcbnew or kipy.
- **Adopt PRO-style attempt accounting** and tool-selection evals.

---

## 6. Commercial systems and what they disclose

**Quilter** ([docs](https://docs.quilter.ai/llms.txt); [changelog](https://www.quilter.ai/changelog); [technology](https://www.quilter.ai/product/technology))
- **Approach:**
  - "Reinforcement learning + classical solvers + computational geometry". Placement and routing are treated as one coupled problem, producing "dozens to hundreds of ranked candidates".
  - Candidates are numbered **X.Y** (placement X, router Y).
  - "Some decisions should be correct by construction… diff-pair spacing… derived from the stackup and impedance target, not guessed by a neural network."
  - "Never trained on human-designed boards". Free-tier designs "generate synthetic training puzzles". Paid designs are never used.
  - Engineer Fayaz Rahman: "Router is very sequential… can't do… backtracking… The order and the constraints is probably the most difficult thing."
  - It is "a design agent, not a 'copilot'". "Can't typically design or optimize boards as well as skilled humans." No silkscreen placement.
- **Speed history (2024):** routing 27× faster (local router Python→C++ 6.7×, global router 4×), jobs 9.4× faster. A job "explores 50+ unique designs and produces 20 DRC-free… candidates… in less than an hour".
- **Stackups:** before 2026-03-26 a job tried many stackups; now it uses one. Diff pairs came from a 2D quasi-static solver; since 2026-06-30 any target is solved with Simbeor.
- **"Recommended" sort (lexicographic):**
  1. min DRC, then max completion;
  2. priority PRCs (power, diff pairs, single-ended impedance);
  3. most conservative fab rules (min trace width, then clearance, drill, via);
  4. fewest layers;
  5. other PRCs;
  6. shortest traces.
- **Circuit Comprehension** (auto-detected, then human-confirmed):
  - Bypass caps are "connected between a component and ground". Parent-pin priority: explicit wire, then voltage-named pins, then equal split. Smaller capacitance goes closer.
  - Crystals: refdes X* or Y* with both pins on one parent; load-limiting resistors are not supported.
  - Converters: U* whose output goes to an L* inductor.
  - Power nets: voltage-like names or a "Power" class, with defaults of 200 mA (<3 V) and 500 mA (>3 V), and IPC-2221 widths per layer.
  - Diff pairs: from `_P/_N` names; they need a differential impedance, single-ended impedance and carrier frequency. Pairs with multiple receivers are not routed. Always microstrip.
  - Timing-sensitive signals are in internal testing. Anything unspecified is "a generic signal". No datasheet review.
  - Custom Component Proximity (2026-05-01): a child part within N mm of a parent pin.
- **8 PRCs:**
  - Ground Plane Overlap: the plane under both traces everywhere except 2×clearance at each end.
  - Overheated Length: segments with analytic rise above 20 °C; example pass range 0–10% of length.
  - Pin Distance (0–1 cm), Layer Switch Count (0–1), Length Mismatch (0–1 cm).
  - Uncoupled Spacing (spacing more than 10% off nominal; 0–1 cm), Trace Path Length (0–1 cm).
  - Invalid Width Span (outside ±10%).
  - Planned: top-plane pour, neck-downs, trace proximity.
  - PRCs launched 2024-11-18 as per-constraint "unit tests" meant to drive learning.
- **Floorplan controls** (most freedom to least): schematic clustering; anchoring; off-board regions, optionally plus an anchor ("our current favorite"); on-board rooms (multipolygon allowed); manual placement, where anything inside the outline is locked. Leftover vias block placement.
- **Timeline:**
  - Bypass auto-placement 2024-12-10; power pours 2025-07-15.
  - 2026-03-26: ground-net comprehension; 4-page setup.
  - 2026-04-07: Projects allowing iterations within 10% BOM change.
  - 2026-05-01: clearance rules read from Altium only; BGA fanout for square patterns (beta per press release 2026-07-08).
  - 2026-05-31: "routes through-vias only".
  - 2026-06-30: Floorplan page, because the commonest mistake is not floorplanning or pre-placing; Cadence schematic parsing.
  - 2026-08-31: plane pours sized to cover same-net vias; DC IR-drop beta.
  - 2026-09-30: New Router Strategy alpha (<400 pins); native Xpedition.
- **Inputs:**
  - One closed outline (KiCad Edge.Cuts or Altium Mechanical 1), footprints, and a netlist matching the schematic.
  - Ground and power layers must be named ground/gnd and power/pwr.
  - Pre-placed parts and traces are kept; connectors should be pre-placed.
  - CAD support: Altium, KiCad, Allegro/OrCAD, Xpedition; Zuken and EasyEDA as "other".
- **Envelope:** <5,000 pins; above 20% pin density do it manually; <6 GHz; ≤48 V; ≤10 A.
- **Pricing:** per project by unrouted pins, unlimited iterations within 10% BOM change. AWS (SOC 2 Type 2), or self-hosted Helm on Kubernetes with NVIDIA GPUs (≥16 GB VRAM), air-gapped possible. No public price and **no public API**. Free tier: <10 people and <$50K revenue.
- **Project Speedrun** (i.MX 8M Mini; 843 parts; 5,141 pins; 8-layer HDI; Sierra Circuits):
  - Baseboard: ~27 h of compute, ~500 parts placed, ~2,000 pins routed, 98.4% complete at 3.5 mil. A 99% candidate at 3 mil was rejected.
  - **SOM: placement fixed from the original design, plus a partial human BGA fanout.** It reached 98.7% at 2 mil in a 15 h job.
  - Cleanup: polygons, length tuning (via delay not modelled), widening high-current nets, moving L102.
  - Bring-up: LPDDR4 at 3 GT/s; 10+10 boards all ran.
  - Sierra raised 58 DFM/DFA findings: 48 were documentation, library or BOM items; 10 were physical. Impedance came back 62 Ω versus a 50 Ω target and 92 Ω versus 100 Ω, accepted.
  - HN top comment: "Designed with AI, not by AI."
- **Company:** founded 2019 by Sergiy Nesterenko (ex-SpaceX). $10M Series A (Feb 2024) [S]; $25M Series B led by Index (2025-10-07). **No patents** (USPTO query 2026-10-20).

**DeepPCB (InstaDeep, owned by BioNTech since July 2023)**
- **Mechanism** (patents, §8): an AlphaZero-style router with **NN-guided Sequential Monte Carlo** look-ahead over connection orders and sub-routes, and gridless ray/octagon-tangent candidate points.
- **Training:** a custom simulator plus Sebulba on TPUs, "15x-235x acceleration"; ~24 h and $260 dropped to 6 min and $20. Data is synthetic plus "sometimes real designs", in contrast to Quilter.
- **Cooper** (2026-06-18) is an LLM setup agent: "Cooper orchestrates the routing engine. It doesn't lay copper"; it is LLM-provider-agnostic.
  - "Autorouters don't fail at routing. Nobody configures them."
  - It reads net classes, pairs, planes and stackup, summarizes, and fixes in one approved pass. It "never touches your connectivity".
  - Example: an STM32 + nRF24 board had 4 setup errors (inner layers typed as power with no net); it then routed 98/98 airwires in 2 min 6 s with 68 vias.
- **KiCad plugin:**
  - First release 2026-05-21: routing only, ≤8 layers, ≤1,200 airwires; "keep[s] your component placement exactly where you put it".
  - v1.2.0 on 2026-10-13: Cooper in a docked panel with per-item accept, net isolation, per-board memory, and **each routed revision as a single undo entry**.
  - "Not modelled: length matching and skew, crosstalk, DDR, complicated BGA fanout."
  - Apache-2.0, SWIG, sends the board to api.deeppcb.ai.
- **Other offerings:** API (2025-05-12) at 0.50 credit/min returning "a stream of diverse design solutions"; Enterprise "Custom API & MCP".
- **Formats:** Altium, KiCad, EasyEDA, Zuken; OrCAD, Allegro and Eagle via DSN.
- **Stats [vendor]:**
  - 21,000+ engineers, 100,000+ designs, 55,000+ routing jobs.
  - Median time: <100 airwires 2 min; 100–299 7 min; 300–599 9 min; 600+ 16 min.
  - Mean completion 96.1%, median 100%; 87% of boards ≥95%.
  - "27,721 Boards, 95.6% Hit 95%+", "11,000+ KiCad users".
- **Comparisons it ran:** versus Quilter on three open boards, 99/96/97% against 94/82/87% completion. Versus GPT-6 Astra on microduck: 132/132 routed at 1,104 mm versus 1,282 mm; 64 vias = 14 layer changes + 50 plane drops, versus Astra's 32 (9 in pads).
- **Benchmarks page:** critical nets were always hand-routed first.
- **Organization:** 25–30 FTE; 2,000+ designs per week; embedded by other EDA vendors under NDA.

**Flux:** RL Auto-Layout (Dec 2024; the user placed parts first). Spring 2026: "converges faster… fewer vias". Aug 2026: agent placement edits and a public MCP server. Copilot Knowledge (user and project memory) plus System Knowledge (curated by senior engineers). $37M total raised (Feb 2026) [S]. No patents.

**Cadence Allegro X AI** (announced 2023-04-06)
- Placement, pours and critical-net routing with SI/PI, cloud-based, ">10X" [V 2023].
- Distributors (EMA, FlowCAD) describe Placement AI (fixed parts, height, rooms), copper-pour AI and "Route AI… Full Board Routing Closure".
- EMA:
  - "isn't trained on customer designs"; RL on internal designs;
  - AWS, with on-prem "rolling out in 2026"; imports Altium, KiCad, Eagle and PADS;
  - feasibility study cut from a week to 29 min; Rev-to-Rev ECO;
  - "50–70%" time savings.
- EMA case study: 4-layer board at 10.886 pins/cm². 25 min (2 min placement) versus 70 min manual. Issues: bottom-side passives, tight rooms. Envelope <5,100 parts and <100 pins/cm².
- [S] Uses MCTS (per the Cypress paper). DARPA IDEA/MAGESTIC goals: "no human in the loop", "<24h".

**Zuken CR-8000 AIPR** (PCB West, Sept 2023)
- A Smart Autorouter plus Basic Brain trained on Zuken's design database.
- Dynamic Brain would ingest IPC-2581 and learn from the user's designs. Autonomous Brain would be multimodal, extracting intent through text inference.
- "The brain can be untaught if it is sent a dirty design."
- About 100 test designs; 45 min cut to 30 s.
- Components must be placed first; "Smart Placement is under development".
- Status of the later Brains is unknown.

**Siemens**
- PADS Pro Essentials and Xpedition Standard (2025-05-21): CELUS front end, "advanced routing automation", with no AI algorithm named.
- **Fuse EDA AI Agent** (GTC 2026-03-16):
  - MCP plus "Agent Skills" ("executable playbooks"), dynamic tool discovery;
  - supervisor and worker agents, autonomous recovery loops, EDA file parsers, guardrails;
  - RBAC, audit trails, human checkpoints; Nemotron; air-gapped.
  - For PCB it only "aids layout".
- DAC 2026: "self-verifying" agents validated against deterministic physics engines, using NeMo Gym.
- Blog 2026-05-18: "Not every problem requires AI."
- 23 US patents found, none ML. Fabricator-blog claims about AI routing are unverified [S].

**Others**
- **Altium:** Situs and ActiveRoute are not branded AI; users export to Quilter or DeepPCB. Only a 2018 patent. Altium Designer 26.5.1 (2026-05-06) [S].
- **Synopsys and Ansys:** chip agents, SIwave PI Advisor, SimAI needs 30–100 runs; no PCB AI layout.
- **JITX:**
  - "AI writes the code. HFSS validates"; a constraint-driven **topological** router ("directly make a layout that meets the rules"), 8 traces where a legacy tool fit 6, pin swapping inside the router.
  - 5–20× fewer hours on 30+ layer designs (unpublished); "up to 25x"; PCIe-gen7 BGA launch optimized in 5 HFSS runs.
  - Customers named: Honeywell, Lockheed, OpenAI. `py-jitx` 4.2.x. No KiCad export; no patents.
- **CELUS:** block diagram → schematic and BOM; catalogs exposed over MCP; patents US 12,688,343 and 12,443,611.
- **Circuit Mind:** schematic and BOM via a solver; US 12,050,847; ~$8.41M raised [S].
- **SnapMagic Copilot** (schematic and BOM). **Cadstrom** ($6.8M seed; Sigma verification).
- **Diode Computers:**
  - YC S24; $11.4M Series A (a16z); enterprise designs "from $10,000"; Zener/Starlark plus the `pcb` CLI (MIT, 463★), which needs KiCad 10.
  - With Anthropic: engineers preferred Sonnet 4.5's reference designs over Opus 4 (60/40) and Sonnet 4 (82/18).
- **JLCEDA/EasyEDA:**
  - 6.58M engineers and 52M designs.
  - The official "EasyEDA API Skill" plus a local bridge, through which Claude Code or Codex "emits JavaScript that calls EasyEDA's extension API… autoRouting".
  - Its docs: "Auto router is not good enough! Suggest routing manually!"
- **OpenAI GPT-6 Astra** (Sept 2026):
  - The launch clip is a 15-second condensation of a 2 min 54 s run.
  - NextPCB test 1: DSN → **Freerouting** → SES; "Astra orchestrated". Test 2, GUI only: "three short trace segments" in an hour.
  - JLCPCB review: Astra protected critical nets and then ran Freerouting. It reached 0 ERC/DRC after 46 parity fixes, **with 5 DRC and 4 ERC categories ignored**.
  - EEBench 69.3% ±10% [P via Hackaday]. A leaderboard snapshot shows Claude Opus 5.5 at 75.0% and Opus 5 at 61.6% in August [S].
- **Survey:** Weidmuller/EETech 2026 (400 engineers): 91% have used AI in PCB work; 75% see it as a productivity layer, not an autonomous step (second-hand via DeepPCB).

**Common architecture across the disclosures (PI §7)**
1. A comprehension and setup layer, always human-confirmed.
2. Human floorplan anchors.
3. A search core (RL, NN-SMC, GA with learned fitness, MCTS, or topological constraint-driven routing) producing a **placement × router candidate matrix**.
4. Correct-by-construction physics plus PRC unit tests for ranking.
5. Staged engines: fanout, pours, plane planning, tuning.

LLMs appear only as orchestrators (Cooper, Fuse, JITX code editing, the EasyEDA skill, Astra in practice). Data strategies split three ways: synthetic only (Quilter), internal library (Cadence, Zuken), synthetic plus corpus (DeepPCB).

### Implications for our system
- **Copy the shared input contract:** a fixed outline, pre-placed connectors, locked critical copper, net classes and named planes, and auto-detected constraints that a human confirms. Express it as KiCad-native artifacts.
- **Copy Cooper's UX:** read → summarize → propose → per-item accept → one undo entry. Make the configuration and review agent the **first deliverable**.
- **Re-express Quilter's heuristics, PRCs and ranking in our own words** as CC0 rule records (facts are free; see §9).
- **Own the high-speed space vendors leave open:** DDR, length and skew, time domain. KiCad 10 already expresses these constraints.
- **Treat vendor facts as perishable:** DeepPCB's price changed about 30-fold per hour, and Flux added placement plus MCP, all within 2026.

---

## 7. Benchmarks, datasets and evaluation
- **PCBench** (MIT repo, 21★): the README says 164 boards, but `master_metadata.json` lists **1,194 designs from 846 repos** (2023-08). PCBWorld derives 679 curated boards (KiCad 9, fully connected, DRV-free, split D3-A/B/C), and Freerouting cites 1,157.
  - The counts are partly reconciled by LIC's metadata read. The remaining gap (1,194 versus 1,157) is unexplained; my guess is loadable or convertible boards (inference).
  - Per-board licences: see §9.
- **PCBWorld:**
  - BSD-3 Gymnasium environment with actions `ACT_NET_SELECT`, `ACT_START_ROUTE`, `ACT_MAKE_LINE` and `ACT_NET_END`.
  - Datasets: D1 is a Jumanji-style grid (10–500); D2 is gridless 2-layer; D3 is the real boards. Agents choose from **masked candidate point sets**. State is exact mm, with an S-expression text wrapper for LLMs.
  - Reward is potential-based with a log-shaped DRC penalty.
  - Metrics: Clean Pass, Potential Gain, Routability, Time, DRV, wirelength, vias; reported @5.
  - Baselines: PPO/GRPO, LLM tool agents (OpenAI, Anthropic, Gemini, Together), Freerouting, KRT.
  - D3 is rebuilt at run time with `prepare_pcbench.sh` and is not redistributed.
- **EEBench** (atopile):
  - Deterministic build, SPICE at worst-case corners, and BOM checks; score = 0.65 × technical + 0.35 × cost efficiency.
  - "**Layout is deliberately out of scope**" in v1; V2 will add layout and fabricate boards. Tasks are private.
- **EDA-bench:** 35 Harbor tasks for KiCad project reconstruction (schematic, PCB, connectivity, ERC/DRC, functional contract). Tied to an ICML 2026 paper [S]; no model results yet.
- **tscircuit datasets:** `autorouting-dataset-01` (200 problems), the archived `autorouting` repo, `dataset-zero-obstacle-high-density-z01`, **Z01** (1M 2-layer sample images for vision models, Hugging Face, 2026-02-26), and `dsn-converter`. seveibar: routing is "basically an image transformer problem without a good dataset".
- **comma.ai PCBGolf:** score = bounding-box volume (mm³) + 50 × vias + 5,000 × copper layers. $1,000 prize, deadline 2026-10-12 (now past). **No licence file.**
- **Anecdotes:** EEVblog (2010): Freerouting 11 vias versus 18 manual [S]. Hackaday (2019): TopoR routed 100% with fewer vias than a manual KiCad route [S].
- **No placement benchmark exists.** No independent benchmark of Quilter, DeepPCB or Flux exists.

### Implications for our system
- **Primary routing benchmark:** PCBWorld-Bench (fetch at run time). Secondary: Freerouting's PCBench suite and tscircuit datasets.
- **Re-run current versions:** Freerouting 2.5, fastroute, kicad-tools, the tscircuit router.
- **Report:** clean pass, routability, DRV, vias, length versus lower bounds, time, and layout-quality checks. "0 DRC" alone is weak; the null baseline routed signals through a GND plane.
- **Publish a placement benchmark:** strip placement from D3 boards and score downstream clean pass, wirelength, vias and rule proxies. Also cover multilayer boards. Publish failures.
- **PCBGolf and the devbisme dual-ADC test** work as fetch-only showcases.

---

## 8. Practitioner sentiment (short)
- **Experienced engineers are sceptical:**
  - bsder: autorouters "are a pain in the ass that never work".
  - Heath_Raftery: "AI operating a 60 year old technology is mostly entertainment".
  - davidsrsb: "PCB component placement is the hard problem… A good placement has often autorouted usably well even 30 years ago".
  - joojala: "the critical thing is where on the board things are located".
  - paulvdh: cleanup can cost more than routing by hand.
  - K0balt: fixing autorouted work "takes as long… as… doing it yourself".
  - ChrisGammell prefers "co-creation tools, rather than full auto tools".
  - theamk: "every single track has to abide by the rules".
  - Joel_Mckay: "NP-hard problems are still NP-hard"; monocasa answered that it is closer to bin packing.
  - The KiCad forum moderator on a built-in autorouter: "not in the foreseeable future".
- **Early adopters are more positive:**
  - rutierut: LLMs are "_really_ good at the stackup and part config, but [create] some absolutely terrible routes".
  - A Hackaday commenter has had 3 vibe-coded boards come back working first time; the routing was "wonky".
  - __atx__: it is "whack-a-mole" getting Opus to use hierarchical sheets.
  - JLC/LCSC part search with stock data is seen as the most valuable feature.
  - The GPT-6 Astra forum thread's original poster: LLMs are "very bad with high frequency signals… HDIs… BGAs".
- **MCP projects add disclaimers:** "do not replace qualified engineering review"; "not an automated sign-off authority".
- **Implications for our system:** keep a human in the loop with diffs, renders, per-net accept and undoable commits. Lead with explainable placement. Earn credibility with reproducible benchmarks, not demos.

---

## 9. Licensing and the reuse matrix under MPL-2.0

### 9.1 MPL-2.0 mechanics that matter (LIC §4)
- **Scope:** file-level copyleft. Modified MPL files stay MPL with source available; larger works may use any license.
- **Patent grant:** express, §2.1(b), with §5.2 termination.
- **GPL combination:** §3.3 lets a "Larger Work" combine with GPL/LGPL/AGPL, so KiCad could absorb our code. **Never add the "Incompatible With Secondary Licenses" notice.**
- **ASF:** Category B (binary inclusion allowed).
- **KiCad PCM:** requires GPL-compatible code licenses, and MPL-2.0 qualifies ([add-ons](https://dev-docs.kicad.org/en/addons/)).
- **What it does not do:** it does not reach SaaS use (only AGPL does), and no license protects against **third-party** patents.
- **Absorbing other code:**
  - Permissive code (MIT, BSD, Apache-2.0 with NOTICE and change marking, BSL-1.0, ISC) can be vendored, keeping its notices.
  - LGPL, EPL and MPL libraries are fine unmodified. Avoid static LGPL links in Rust (relinkable objects would be required).
  - GPL or AGPL code must **not** enter our distributed files. The decision limits GPL to a process boundary.

### 9.2 KiCad/GPL interaction facts (LIC §2)
- **IPC clients need not be GPL.** Seth Hillbrand (KiCad lead dev, 2025-07-17): "If you distribute a plug-in that links to the KiCad Python library, your code must be GPL or compatible licensed. If you use the new IPC plugin framework, it does not need to be."
- **kipy went MIT** after a user worried that a GPL kipy would "taint" plugins (Jon Evans; [issue #9](https://gitlab.com/kicad/code/kicad-python/-/work_items/9)).
- **Residual risk:** the `.proto` files carry GPL-3.0-or-later headers, and issue #134 is unresolved. The FSF test is whether "the semantics of the communication are intimate enough, exchanging complex internal data structures".
- **Outputs and libraries are not covered.** kicad-cli outputs and users' boards fall outside the GPL ([GPLOutput](https://www.gnu.org/licenses/gpl-faq.html#GPLOutput)).
  - KiCad libraries are CC-BY-SA-4.0 with an exception that waives Article 3 for designs and generated files (SPDX `KiCad-libraries-exception`). **A redistributed collection is not covered** by the exception.
  - Extracted footprints revert to the library license (Jon Evans).
  - KiCad demos are CC BY-SA 4.0. KiCad docs are GPL-3.0+ or CC-BY-3.0+.
- **Porting KiCad or Freerouting code produces GPL code.**
  - Seth Hillbrand (2026-10-19), to a project that AI-ported KiCad's stroke font: "you don't have the right to re-license the work of others".
  - On a Freerouting rewrite: "your use of Freerouting as the base remains the controlling license regardless of how much code you replaced".
  - **AI-assisted porting is the main contamination risk** for an LLM-heavy project.
- **Freerouting provenance:** community hearsay (unverified) mentions 2014 IP accusations involving Zuken. Do not plan to contribute Freerouting-derived code to KiCad.
- **AGPL §13** would attach network-source obligations to our HTTP MCP server if Konnect code were copied.
- **Wrappers do not launder GPL code** ([GPLWrapper](https://www.gnu.org/licenses/gpl-faq.html#GPLWrapper)).

### 9.3 Reuse matrix
**Action key:**
- **IN** = may vendor into our MPL tree, keeping its notice.
- **DEP** = unmodified dependency.
- **PROC** = GPL, process boundary only, distributed separately. Bundling it in an image is an aggregate that needs the license text plus source or a written offer.
- **REF** = patterns only, no code.
- **AVOID**.
- **FETCH** = manifest plus run-time fetch, never re-hosted.

| Component | License | Action under MPL-2.0 |
|---|---|---|
| KiCad C++ (PNS, DRC), kicad-cli, IPC server | GPLv3+ | PROC (IPC/CLI); **never port** |
| IPC `.proto` | GPL-3.0+ headers | do not vendor; depend on kipy; generate other-language bindings at build time; ask about #134 |
| kipy 0.8.0 | MIT | DEP |
| SWIG `pcbnew` helpers | GPLv3+ | PROC only (separate GPL "bridges" repo, PCBWorld pattern); gone in 11 |
| PCBWorld-Engine | GPLv3 | PROC (socket); a port to 10/11 is GPL work |
| PCBWorld env/bench | BSD-3 | IN (+Notice.md) |
| Freerouting (Java; GPL-3.0, no "or later" found); MCP npm | GPL-3.0 / GPL-3.0-only | PROC (CLI/REST/MCP), `-da`; **[MPL-flip]** no vendoring, fork or JVM import |
| freerouting-client 2.3.0 | MIT | DEP/IN |
| fastroute; EasyEDA router; route-rnd | GPL-3.0+; GPL-3.0; GPL-2+ | PROC (optional) |
| Horizon, LibrePCB, pcbcraft, Place By Sch | GPL-3.0 | REF |
| vygr routers, ReplicateLayout, Place Footprints | GPL-2.0 | REF/AVOID |
| KiCadRoutingTools, kicad-tools, kicad-happy, OrthoRoute, Fanout Tool, HierarchicalPCB, Layout Clone | MIT | IN |
| SubLayout | BSD-3 | IN |
| Parts Placer | LGPL-2.1 | DEP |
| tscircuit / capacity-autorouter | MIT (TypeScript) | IN (port or subprocess) |
| Topola | MIT (crate MIT OR Apache-2.0) | IN |
| Cypress | Apache-2.0 | IN (+NOTICE) |
| DREAMPlace, SA-PCB, PcbRouter, ALIGN, MAGICAL, OpenROAD | BSD-3 | IN |
| RL_PCB, HierPlace v1.1.0, morningfire-pcb-automation | MIT | IN |
| KMS | MIT (depends on kicad-skip, LGPL) | IN |
| kicad-mcp-pro (scorer weights, evals, golden corpus) | MIT | IN |
| POA ≤0.20.1 (bump 511a50d, 2026-08-15) | MIT | IN *only* the CST substrate (`_cst.py`, round-trips 15,711/15,711 files), atomic writes, board CST slices, measured flip (45ba30b, 456839d). **Exclude `tests/kicad_ref`** (deliberate ports of KiCad's GPL source, the very reason POA relicensed, so GPL whatever the label; my inference). **Exclude** the MIT-era `_transform_local_to_board` (textbook-rotation bug). |
| POA ≥0.21 (October transform fixes b588906, cf501c7, 2d4a55f, fff4209) | GPL-3.0+ | REF (re-derive behaviour clean-room) |
| Konnect | AGPL-3.0 + CLA | REF only. Its MIT portions (CPL rotation table, scoring weights, calculators, release-gate lattice from PRO; DSN syntax from Topola) should be taken from the originals |
| eda-agent, copperhead, DeepPCB plugin | Apache-2.0 | IN |
| lamaalrajih/kicad-mcp, Diode `pcb`, KiKit, IHB, SKiDL, atopile, WebCola | MIT | IN |
| Seeed kicad-mcp-server | README "MIT", no LICENSE file | caution: ask for a file |
| Backplane | MIT, but ships a KiCad fork | caution: the fork parts are GPL (inference) |
| PCB-Agent-Teams | Noncommercial | AVOID |
| diodeinc/dsn | no license shown | AVOID |
| kiutils | GPL-3.0 | not in core; PROC bridge only **[MPL-flip]** |
| kicad-skip | LGPL-2.1+ | DEP |
| Solvers: OR-Tools, SCIP, pymoo (Apache); HiGHS, Z3, pyribs, Optuna, BoTorch, PySCIPOpt (MIT); SMAC3, pycma (BSD-3); PyTorch, JAX, NetworkX, rustworkx | permissive | IN/DEP |
| DEAP | LGPL-3.0 | DEP |
| Gurobi | proprietary | user-installed optional backend only |
| OptiMathSAT | research only | AVOID |
| Geometry: Shapely (BSD) + GEOS (LGPL-2.1) | – | DEP (ship LGPL notice and source if bundled) |
| rtree/libspatialindex (MIT), Clipper2/pyclipr (BSL-1.0), sparrow (MIT) | permissive | IN |
| PythonCDT/CDT, jagua-rs | MPL-2.0 | IN (native fit) |
| Shewchuk Triangle | non-free for commercial use | AVOID (use PythonCDT) |
| CGAL Python | GPLv3+ | PROC |
| openEMS Python, PySpice, Elmer | GPL | PROC |
| CSXCAD | LGPL-3.0 | DEP |
| gerber2ems | Apache-2.0 (drives openEMS) | IN, with openEMS as a subprocess |
| scikit-rf | BSD | IN |
| ngspice | mixed | per file |
| adaptagrams | LGPL-2.1+ | DEP |
| ELK/elkjs | EPL-2.0 OR GPL-3.0+ | DEP |
| MCP SDKs: `mcp`, `@modelcontextprotocol/sdk`, pynng (MIT); fastmcp (Apache); protobuf (BSD) | permissive | DEP |
| azonenberg/pcb-checklist | BSD-3 | IN (quote with notice) |

### 9.4 Data, rule packs, weights
- **PCBench per-board licences** (by board, 1,194 total):
  - none 648 (54.3%), MIT 147 (12.3%), GPL-3.0 106 (8.9%), "Other" 96 (8.0%), Apache 38, GPL unspecified 33, GPL-2.0 20, CC-BY-SA 18, CERN-OHL 18, BSD 16, CC unspecified 15, CC-BY 11, LGPL 6, WTFPL 5, CC0 5, Unlicense 5, AGPL 4, MPL-2.0 2, TAPR 1.
  - By repo, 449/846 (53.1%) have no license.
  - **A repo-level MIT license cannot relicense the boards.**
- **Other datasets:**
  - open-schematics (HF) puts a CC-BY-4.0 overlay over records with no per-record license. Seth Hillbrand: it "merely strips the license and origin".
  - OmniLayout/OmniRouting: "no licence grant of any kind"; the papers are CC BY-NC-ND.
  - PCBSchemaGen (MIT card) and kicad-netlist-sft (Apache card): provenance not audited.
  - PCBGolf: no license.
- **Precedents for run-time fetch:** kicad-tools (`boards.toml` with pinned SHA and upstream license; gitignored cache), kicad-happy-testharness (pinned 40-character hashes), PCBWorld, Freerouting.
- **Our data (CDLA-Permissive-2.0):** it puts "no restriction… with respect to… Results", including ML models.
  - Use manifests with `repo_url`, `commit_sha`, `path`, `spdx_license`, `license_evidence_url`, `attribution`, `retrieved_at` and `tier`.
  - Tiers: **R** (permissive/CC-BY/CC0/CERN-OHL-P; may be redistributed with a NOTICE); **SA** (GPL/CC-BY-SA/CERN-OHL-S/W; separate bundles only, never inside a CDLA bundle); **E** (unlicensed or "Other"; fetch-only). Exclude NC and ND.
  - Provide takedown contacts and a data card.
  - An extracted footprint corpus must stay CC-BY-SA-4.0 WITH the exception, kept separate.
  - KiCad demos used as fixtures should be read from the user's KiCad install (POA's `kicad_corpus`), not re-hosted (my inference from CC BY-SA).
- **Rule packs (CC0):**
  - Facts and methods are not copyrightable (17 U.S.C. §102(b); *Feist*).
  - Store parameter, condition, our own rationale, and a structured citation: vendor, document ID, revision, section, URL, access date.
  - No verbatim text, tables, figures or PDFs.
  - TI's notice adds a contractual restriction: "use these resources only for development of an application… Other reproduction… prohibited".
  - Executable checks and `.kicad_dru` generators are code, so they are MPL-2.0.
- **Weights (not covered by the decision; open):**
  - LIC advises Apache-2.0 weights from Apache or MIT bases only: Qwen3/3.5/3.6, Qwen2.5 ≤32B, Mistral-7B, OLMo-2, gpt-oss, Phi-4, DeepSeek-R1.
  - Avoid Llama ("Llama" name prefix plus "Built with Llama"; FSF calls it non-free), Gemma (flow-down even through distillation), Qwen-license 72B ("Built with Qwen"; 100M MAU) and RAIL.
  - Anthropic terms forbid using the service "to train competing AI models". Prefer solver- or DRC-generated supervision, and record which models generated any synthetic data.
  - Model cards should meet OSAID 1.0.
  - Training on copyleft boards is unresolved. CC's conservative guidance would pass SA through to the model, and CERN-OHL-S's "Product" might reach a model.
- **AI-authored code may carry thin copyright** (USCO Part 2, Jan 2025). A license file is still needed.

### 9.5 Process checklist (adapted to MPL-2.0)
1. **Relicense now**, while the owner is the sole human copyright holder. The repo currently has a bare GPL-3.0 `LICENSE`. Earlier snapshots stay GPL forever (§2).
2. **REUSE 3.3 layout:**
   - `LICENSES/MPL-2.0.txt`, `CC-BY-4.0.txt`, `CC0-1.0.txt`, `CDLA-Permissive-2.0.txt`.
   - SPDX headers in every file.
   - `REUSE.toml` annotating docs, notes and reports as CC-BY-4.0, `rules/**` as CC0 and dataset manifests as CDLA. Quotations inside notes remain their sources'.
   - Run `reuse lint` (6.2.0) in CI.
3. **Rust gate:** `cargo deny check licenses` (0.20.2) allowing Apache-2.0, MIT, BSD-2/3, ISC, Zlib, BSL-1.0, Unicode-3.0 and MPL-2.0. Deny GPL, AGPL, LGPL and unlicensed crates in core.
4. **Python gate:** `pip-licenses` 5.5.5 with `--allow-only`, or `licensecheck`; ScanCode 32.5.0 on any vendored directory. GPL packages live only in the separate bridge.
5. **`THIRD_PARTY_NOTICES.md`** at each release.
6. **Contributions:** DCO sign-off with inbound=outbound and no CLA.
   - AI rule: no GPL, AGPL or unlicensed source in prompts or diffs for core code; disclose AI use.
   - Clean-room only for KiCad PNS/DRC, Freerouting and Konnect.
7. **Re-verify licenses each release.** Examples of drift: libspatialindex LGPL→MIT, kipy GPL→MIT, Topola's crate versus repo, POA MIT→GPL.

### Implications for our system
- **Five flips from the earlier GPL-era advice:**
  1. Freerouting and fastroute: process boundary only, with no forking or vendoring.
  2. PCBWorld-Engine: separate GPL distribution behind a socket.
  3. kiutils: not usable in core, so write our own parser.
  4. POA: only the narrow MIT-era subset (above). Its transform fixes and `kicad_ref` are reference only.
  5. **MCP's "port KiCad's `RotatePoint`/`Flip`" must become a clean-room reimplementation**, validated against `kicad-cli` drill and Gerber output. A port would be GPL.

---

## 10. Patents to watch (identification only, not legal advice; PI §5)

USPTO PPUBS only (US grants and published applications), queried 2026-10-20. No CN, EP, WO or JP searches.

- **High relevance:**
  - **Cadence US 11,599,699 B1.** Filed 2020-02-10, granted 2023-03-07, 469 days PTA, DARPA HR0011-18-3-0010. Inventors Roberto, Mitra, Hogan, Li, Zumbo, Murphy.
    - Claim 1: an **RL agent** over a feature vector of images plus scalars recommends a place, via or route action, then repeats.
    - Dependent claims: hierarchical RL, a GCN, an NN routability reward.
    - Est. expiry ~2041.
  - **Cadence US 12,223,248 B1.** Filed 2020-08-10, granted 2025-02-11.
    - Claim 1: GA placements are autorouted to label routability; a CNN + GCN + DNN + fusion DNN then predicts it.
    - Est. expiry ~2040-08.
  - **InstaDeep US 11,842,136 B2** (granted 2023-12-12; priority GB 2019-11-27), **US 12,019,968 B2** (2024-06-25) and **US 12,159,094 B2** (2024-12-03).
    - Claims: NN-guided **Sequential Monte Carlo look-ahead** over connection orders or sub-routes, with a posterior used for selection and as the training target; particle resampling and entropy weighting.
    - '968 adds ray/octagon-tangent candidate points. Those **alone** are not claimed without the SMC + NN element.
    - Est. expiry ~2040-11.
- **Watch-list:**
  - **NVIDIA US 2025/0315590 A1** (pending; filed 2025-04-01; provisionals 2024-04-03 and 2025-01-30; published 2025-10-09). Claim 1: a "circuit layout tool… based on input cluster constraints" plus an agent running an "LLM in a Thought-Action-Observation (ReAct) prompting loop to update the cluster constraints". The description is about standard cells. **This is the architecture of our project.** Collect prior art from before 2024-04-03 and monitor prosecution.
- **Medium relevance:**
  - Cadence US 11,087,060 B1 (2021): learn device-position predictors from a prior design, then create hard and soft constraints.
  - NVIDIA US 2026/0187328 A1: GPU stencil-buffer overlap counting.
  - Honeywell US 12,566,911 B2 (2026-03-03): an ML parasitic estimate shown as complex impedance in a GUI.
  - Wistron US 2026/0228404 A1: learned netlist-topology similarity to reuse layout modules.
  - Think Circuits US 2025/0307516 A1: automated review engines (low to medium).
- **Low relevance:**
  - Cadence US 11,379,646 (synthesis-parameter inference and compute prediction), US 11,544,574 and US 11,620,548 (IC level).
  - SVXR US 11,042,981 / Bruker US 11,662,479.
  - Celus and Circuit Mind (schematic generation).
  - Google AlphaChip family (claims recite an "integrated circuit chip").
- **Nothing found for:** LLM-driven PCB layout; schematic constraint extraction by ML/NL/LLM; RL plus PCB beyond Cadence '699. Nothing from Quilter, Flux, JITX, Altium, Synopsys/Ansys, Zuken (none ML) or Siemens (none ML).
- **Eligibility context:** *Recentive v. Fox* (Fed. Cir., Apr 2025) found generic ML in a new data environment ineligible [S].

### Implications for our system
- **Lower risk by design:**
  - LLM orchestration of classical engines: PNS, Freerouting, analytic placement, SA, force-directed.
  - Deterministic net-order heuristics, or full re-route evaluation of a few LLM-proposed orders, **instead of NN- or LLM-guided particle look-ahead with posterior selection**.
  - Analytic and field-solver physics.
  - Rule-based comprehension with human confirmation.
- **Get counsel before:** an RL place/via/route policy over images plus scalars, or a learned multimodal routability predictor trained on autorouted GA placements.
- **Keep the FTO watch-list in the repo.** Our open publications create dated prior art.

---

## 11. What to reuse vs build (synthesis)

- **Reuse or integrate:**
  - kipy (MIT) and `kicad-cli` (process boundary); KiCad built-ins (DRC rules, component classes, multichannel, Design Blocks, tuning profiles, Attempt Finish Selected).
  - Freerouting 2.5 (process boundary; REST or MCP; scores; drc.v1).
  - PCBWorld-Engine (separate GPL process) and PCBWorld-Bench (BSD-3).
  - KRT and kicad-tools (MIT) for fanout, diff pairs and placers; Cypress (Apache-2.0) as an optional global placer.
  - tscircuit capacity mesh as a reference; PythonCDT and jagua-rs (MPL); OR-Tools, Optuna and friends.
  - From KMS (MIT): the Freerouting wrapper (best-of-N, hole growth, SES pruning, Java detection).
  - From PRO (MIT): the scorer, evals and golden corpus.
  - From POA ≤0.20.1 (MIT): the CST splice.
  - HierPlace (MIT).
- **Build:**
  1. An LLM comprehension and configuration agent with Cooper-style UX, emitting KiCad-native constraints.
  2. A source-verified `.kicad_dru` compiler (and later a `CustomRule` compiler) with IR rule names.
  3. A constraint-aware floorplan → packing → refinement placer, with an independent scorer and top-k route ranking.
  4. Engine-grounded routing orchestration (critical nets in PNS, bulk in Freerouting, repair loops).
  5. A PRC-style layout-quality suite beyond DRC.
  6. A small MCP surface with source tags, plan/apply, one undo per step, outcome envelopes and escape hatches; an IPC-runtime PCM plugin (an empty niche).
  7. Evaluation: placement benchmark, attempt accounting, published failures.
  8. A clean-room transform module and a byte-preserving file layer.
- **Timing:** KiCad 11 (~Q1 2027) brings headless IPC, rules over IPC, DSN/SES jobs and SWIG removal. Keep the backend abstraction thin, so the swap is cheap.

---

## 12. Conflicts and open questions

**Unresolved conflicts**
- DeepPCB plugin: KiCad 6.0+ (README) versus 10.0+ (vendor page).
- Konnect: 228 versus 217 versus 171 tools.
- Freerouting Docker arm/v7.
- kicad-happy detector and Vref counts; v2.3.1 versus "stable v2.1.0".
- PCBench: 164 / 679 / 1,157 / 1,194.
- OrthoRoute: 30%/51% versus 0.34/0.53.
- PCBWorld @5 numbers versus one-attempt numbers. Use labelled values, never mixed.
- Wikipedia's claim that the gEDA toporouter was adapted for KiCad (dubious).

**Behaviour still to test**
- Does `ParseAndCreateItemsFromString` keep nets?
- How long do async refills take?
- When does `.kicad_dru` reload in the GUI?
- Can `UpdateItems` modify every field, e.g. padstacks and zone settings?
- Freerouting 2.5's KiCad 10 IPC path (IPC or SWIG? DRC fidelity?).
- PCBWorld-Engine portability, throughput and stability on KiCad 10/11.
- Konnect's round trip on boards with 4+ layers.

**Unknown or undisclosed**
- KiCad 11's date and final IPC surface. Net-chain semantics. How `th`/`rad` units and `solder_mask_sliver` behave at run time.
- Cypress paper details (cost terms, evaluation router). EasyEDA Pro's dual-engine algorithms.
- Quilter's RL algorithm and weights. DeepPCB's architecture, SMC particle counts and placement method.
- Zuken and Cadence 2026 status. Every vendor's placement objective weights.

**Licensing**
- Generated-binding license (#134).
- Freerouting provenance.
- Training on copyleft boards.
- Enforceability of TI's terms against non-customers.
- Weights license (outside the user's decision).
- KiCad trademark policy for the project name.
- EU database rights.

**Evidence gaps**
- No measured LLM success as a function of tool granularity beyond POA's small A/B.
- No per-read token-cost data.
- No independent SI measurement of AI-routed boards.
- No Reddit or EEVblog sentiment (blocked).

---

## 13. Idea inventory (every distinct approach, technique or recommendation; source tags ET/VK/MCP/PI/LIC)

**KiCad interface and backend**
1. Target KiCad 10.0.x; pin kipy 0.8.x; gate features on point releases (≥10.0.1, 10.0.6, 10.0.7). [ET][VK]
2. A `BoardSession` abstraction with backends: live IPC, KiCad 11 `kicad-cli api-server`, file-level fallback. [ET]
3. A four-channel 10.0 backend: IPC CRUD in commits, `.kicad_dru` writes, kicad-cli DRC referee, SWIG DSN/SES helper process. [VK]
4. Headless CI options on 10.x: SWIG, S-expr plus kicad-cli, or GUI under Xvfb with IPC (undocumented). [ET]
5. A self-maintained S-expression parser (kiutils/kicad-skip are stale; kiutils is GPL). [ET][LIC]
6. Keep SWIG out of core; quarantine it in a short-lived, separately distributed GPL helper. [ET][VK][LIC]
7. Use `kicad-cli pcb drc --format json` on a saved copy as ground truth. [ET][VK]
8. Place library footprints on 10.0 via `ParseAndCreateItemsFromString` from `.kicad_mod` text, plus `UpdateItems` for pad nets. [VK]
9. Poll after async `RefillZones` (Konnect: retry `AS_BUSY` only, 60 s budget, 50 ms polls). [VK][MCP]
10. Lock all copper to keep before SES import; strip or match the SES placement section. [VK][MCP]
11. Plan the KiCad 11 migration (headless, rules over IPC, DSN/SES jobs, SWIG removal). [ET][VK]
12. Build a `CustomRule` protobuf emitter sharing code with the `.kicad_dru` emitter; validate by round trip. [VK]
13. Respect single-connection and busy-retry semantics; bound timeouts. [ET][VK][MCP]
14. Use `RunAction` "Attempt Finish Selected" for local completion and cleanup, accepting the fragility. [ET]
15. Treat component classes, custom DRC, rule areas, Design Blocks and tuning profiles as agent levers. [ET]
16. Use multichannel Repeat Layout as a placement multiplier; prefer hierarchical-sheet channels. [VK]
17. Reuse known-good sub-layouts through PCB Design Blocks. [ET]
18. Ship an IPC-runtime PCM plugin plus MCP server (zero AI plugins in the PCM). [ET]
19. Depend on kipy from PyPI; never vendor `.proto`; generate other-language bindings at build time. [LIC]
20. Version-gated emitters: numeric nets ≤20241229, named nets after; canonical layer names only. [MCP]
21. Run a CI matrix on KiCad 9.0.x and 10.0.x across OSes. [MCP]
22. Validate every layer name before an IPC send (unknown layers crash KiCad). [MCP]
23. Never socket-probe NNG; discover through filesystem metadata. [MCP]
24. Treat `AS_TOKEN_MISMATCH` as a break in session continuity. [MCP]
25. Correlate requests by ID to avoid off-by-one replies after timeouts. [MCP]
26. Native operations first, AI-directed workflow second, own replacement by exception (Konnect filter). [MCP]
27. Never write through pcbnew `SaveBoard` or kipy whole-object setters. [MCP]
28. "A subprocess may compute, never write": splice computed results (e.g. zone fills) into the file. [MCP]
29. Use a byte-preserving CST for file edits. [MCP]
30. Atomic writes; validate values before writing; serialize concurrent file mutations. [MCP]
31. Guard saves by content-hash divergence, not mtime; `preserve_project_settings` after saves. [MCP]
32. Pin a session to IPC only when the GUI provably has the same board; never silently switch. [MCP]
33. Once a board is seen live, refuse file fallback (`unsafe_file_fallback`). [MCP]
34. Board-write gates: active-board check, fail-closed IPC write, refuse file edits while open. [MCP]
35. One clean-room transform module (rotate/flip/mirror, integer nm, KiROUND by era), oracle-tested on drill and Gerber output. [MCP][LIC]
36. Never trust proto comments about coordinate frames; verify by readback. [MCP]
37. Reject non-orthogonal or unparseable angle spellings; write angles KiCad's way (270, omit 0). [MCP]
38. Snapshot and re-attach 3D models around kipy orientation writes; add a tripwire test. [MCP]
39. Chunk bulk creates into groups of ≤32 within one commit (one Undo restored 70 footprints). [MCP]
40. Verify only after the commit push (staged items are invisible). [MCP]
41. Never blind-retry uncertain writes; enter a recovery-required state. [MCP]
42. Use `EnableAPILogging=1` when debugging the IPC traffic. [ET]
43. Raise `ManualStepRequiredError` for GUI-only steps rather than faking them. [MCP]
44. Generate DSN from the IPC snapshot with a revision-bound exporter plus reverse manifest (Konnect). [MCP]

**Constraint compiler and DRC**
45. Emit only canonical units (mm, deg, ps). [VK]
46. Put one condition per rule with explicit parentheses (equal precedence, left to right). [VK]
47. Use one constraint of each type per rule. [VK]
48. Order rules general to specific (last match wins). [VK]
49. Name rules with an IR-ID prefix, keep a sidecar map, and regex the `description` to attribute violations. [VK]
50. Treat the DRC `type` key as coarse only (`physical_clearance` reports as `clearance`). [VK]
51. Lint emitted rules by running kicad-cli DRC on a scratch copy. [VK]
52. Time-domain first: tuning profiles via `SetNetClasses`, plus ps `length`/`skew` with `within_diff_pairs`. [VK]
53. Compile placement intent into courtyard, side/orientation assertions, rule areas and edge/keepout rules. [VK][ET]
54. Write a custom checker for pairwise pad distance, alignment, symmetry and loop area. [VK]
55. Re-target return-path checks to master's `return_path` net-chain constraint if 11 ships it. [VK]
56. Detect diff pairs with KiCad's suffix rule; guard against XTAL_P/N false positives. [VK]
57. Emit intent as KiCad-native artifacts so it is inspectable and checkable by DRC. [ET]
58. Use one parser for KiCad and Freerouting drc.v1 JSON. [VK]
59. Never drop `unconnected_items` or `schematic_parity`; keep rule keys and positions. [MCP]
60. Report every waived or ignored DRC category; re-open the saved board under project rules. [PI]
61. Compare KiCad DRC with Freerouting DRC to expose DSN translation losses. [VK]

**Routing**
62. Use Freerouting as default bulk router via subprocess, REST or MCP only. [ET][LIC]
63. One `route_with_freerouting` tool returning scores, unrouted count and compact DRC, not geometry. [VK]
64. Run a local Freerouting server with auth disabled and the required headers. [VK]
65. Adopt Freerouting's `V2_CONTINUOUS` and `V2_LOWER_BOUND` scores. [ET]
66. Pin the Freerouting binary by hash; pass `-da`. [MCP][LIC]
67. Best-of-N runs with a varied pass schedule and route-completion scoring. [MCP]
68. Force `-mt 1` (multi-threaded optimization creates clearance violations). [MCP]
69. Grow hole keepouts by the edge-clearance delta; promote footprint keepouts to board level. [MCP]
70. Strip the SES placement block; reconcile net-name slashes; export netclasses into the DSN. [MCP]
71. Detect the Java version from the JAR; Docker/Podman or GraalVM native fallback. [MCP][VK]
72. Guard against stale SES; stage artifacts in a temp dir; handle SES units correctly. [MCP]
73. Import SES into a new candidate board; fix displaced text; DRC and read back. [MCP]
74. Revision-bound export → subprocess route → manifest-validated SES → one undo transaction. [MCP]
75. Evaluate fastroute as a faster drop-in, as a process. [ET]
76. Use KRT (MIT) for fanout, diff pairs, plane repair and time matching. [ET][VK]
77. PCBWorld-Engine as a headless, engine-grounded interactive router for critical nets and repair. [ET]
78. Port PCBWorld-Engine to KiCad 10/11 and upstream it (GPL-side work). [ET]
79. Use the tscircuit capacity mesh/hypergraph as a reference for global routing and congestion estimates. [ET]
80. Keep DSN/SES first-class for user-supplied commercial routers. [ET]
81. LLMs orchestrate, constrain and repair; never emit copper coordinates. [ET][VK][PI]
82. LLM plans and critiques while specialized solvers or small policies execute. [ET]
83. Interactive engine-grounded tool use over plan-then-execute or engine-free generation. [ET]
84. Offer the LLM a small masked candidate-action set (PCBWorld style). [PI]
85. Deterministic net ordering, or full-route evaluation of a few LLM-proposed orders (FTO-safe). [PI]
86. Multiple router strategies, forming an X.Y candidate matrix. [PI]
87. BGA and QFN fanout as a dedicated stage. [PI]
88. Correct-by-construction diff-pair/impedance geometry from a solver; power widths from IPC-2152/2221. [PI]
89. Pour and plane planning that covers same-net vias, then refill and recheck. [PI]
90. Route critical nets first, then bulk, then refine (widths, thermal vias, dangling tracks). [PI][MCP]
91. Target the DDR/length/skew space vendors exclude. [VK]
92. Benchmark against Freerouting 2.5, not 2.1. [VK]
93. Pad-to-pad L-bend helper that reads pad geometry first; null geometry is unavailable, not zero. [MCP]
94. Account for via delay in length tuning (Speedrun lesson). [PI]
95. Use Freerouting's DRC summary hotspots and correction hints for repair. [VK]

**Placement**
96. Make constraint-aware placement the main differentiator. [ET]
97. LLM floorplan and intent first; then a numeric optimizer (packing, then FD/SA/analytical). [ET]
98. Cost = HPWL + congestion from a fast global router; score candidates with fast routing. [ET]
99. Refine perturbatively from a human-like seed rather than from scratch (constraint capture is the bottleneck). [VK]
100. A user-confirmed floorplan (regions, pre-placed connectors, anchors, pin-distance limits) before optimization. [VK]
101. Build the metric before the placer; apply only on strict score improvement. [MCP]
102. Block non-converged plans; require `max_displacement`. [MCP]
103. Default to small explicit moves plus readback plus score plus DRC. [MCP]
104. Associate decaps only through a shared non-ground net with ≤8 references. [MCP]
105. Parse `(locked yes)` properly; never move locked parts. [MCP]
106. Classify the outline (rect/unproven/missing); refuse to plan on unproven outlines. [MCP]
107. Use polygon courtyards and polygon containment, not AABB only. [MCP]
108. A pin-facing rotation pass (0/90/180/270) plus grid snap. [MCP]
109. Weighted springs: power 3×, diff pairs 5×, IC↔decap links. [MCP]
110. Generate N diverse placements; route the top-k to rank (proxies cannot separate them). [PI]
111. Spend more placement time where the routing payoff is large. [PI]
112. PRC-based placement terms: decap pin distance, crystal and converter loop size. [PI]
113. Quilter floorplan levels: clustering, anchoring, off-board regions (+anchor), on-board rooms, manual locks. [PI]
114. A component-proximity constraint (child within N mm of a parent pin). [PI]
115. Cypress via a KiCad→Bookshelf converter (rotation off, sides fixed, `/FIXED` parts). [VK]
116. kicad-tools FD, GA and CMA-ES placers; HierPlace clustering. [ET][MCP]
117. Sequential Optimal Packing (pack order, cost function, boundary search, hardened constraints). [ET]
118. Router-in-the-loop placement repair (KRT `place_route_loop`). [VK]
119. Union-find net clustering from the schematic (Konnect, later retired). [MCP]
120. Group by sheet and function; edge connectors; mounting; decap proximity; thermal and noisy/sensitive zones. [ET]
121. A placement benchmark: strip D3 placements and score downstream results. [ET]
122. Learned routability predictor or RL placement policy only after patent review. [PI]
123. Single-sided versus two-sided region semantics. [PI]
124. Use the feasibility-study mode (do we need another layer pair?) and Rev-to-Rev ECO re-place of changes only. [PI]

**Agent and tool surface**
125. About 15–30 high-level, verifiable tools rather than 200+ CRUD tools; about 12 always visible. [ET][MCP]
126. A two-tool catalog/invoke mode for clients that cap tool counts. [ET]
127. On-demand toolsets only when the client honours `list_changed`; otherwise expose all. [MCP]
128. Server instructions name the start tools; test that those names exist. [MCP]
129. A source tag on every read: `source`, `board_rev`, `kicad_version`. [MCP]
130. `propose_*` returns a candidate (diff, predicted score); `apply_candidate(expected_rev)` refuses on drift. [MCP]
131. Dry run by default for batch operations, with plan-revision binding. [MCP]
132. One undo entry per agent step. [MCP][PI]
133. An outcome envelope (complete/partial/refused/uncertain/check_unavailable); null, never 0, for unchecked items. [MCP]
134. An echo is not evidence; read back and compare with intent. [MCP]
135. Automatic verification hooks on every apply (readback, counts, score/DRC, connectivity, format stamp). [MCP]
136. Escape hatches: a restricted `kicad_cli` tool and a verified `raw_edit` splice. [MCP]
137. Never forbid file reads or kicad-cli in skills (the POA A/B result). [MCP]
138. Cover every edit class, or permit a verified direct edit. [MCP]
139. Bulk sync tools must not rewrite unrelated objects. [MCP]
140. Bounded outputs (limit/offset, `_total`/`_truncated`). [MCP]
141. Render images only on request; highlight refs, nets and markers. [MCP]
142. Tool annotations (read-only, destructive, idempotent, headless, needs-KiCad) and profiles. [MCP]
143. Focused DRC slices and quality gates (placement, transfer, bounded fix loop). [MCP]
144. Call logging (ring buffer plus jsonl, `get_recent_calls`, `server_stats`). [MCP]
145. A read-only default profile; opt-in write and release profiles. [ET][MCP]
146. Copy patterns, not code, from Konnect; reuse MIT code from KMS and PRO. [ET][LIC]
147. Ship Claude Code skills and playbooks. [ET]
148. MCP plus Agent Skills, for interoperability with Siemens Fuse and CELUS. [ET][PI]
149. Cooper UX: read → summarize → propose → per-item accept → one undo entry. [PI]
150. Ship the LLM configuration and review agent first (setup errors are the main failure). [PI]
151. Stage-0 comprehension: Quilter heuristics plus LLM recall (datasheets, interfaces, current estimates). [PI]
152. Comprehension heuristics: _P/_N; cap-to-ground with parent-pin priority; X/Y crystals; U+L converters; power nets at 200/500 mA. [PI]
153. A router setup pre-check (planes typed with no net, missing pairs). [PI]
154. Human in the loop: proposals, diffs and renders, per-net accept, undoable commits. [ET]
155. Layout-quality checks beyond DRC: signals on plane layers, return-path splits, decap distance, skew, via counts. [ET]
156. A PRC suite with Quilter-style definitions and thresholds. [PI]
157. Lexicographic ranking: validity → priority PRCs → conservative fab → layers → other PRCs → length and vias. [PI]
158. An LLM-written review report that names every waived check. [PI]
159. Supervisor/worker agents, recovery loops, checkpoints, audit trails, self-verification (Fuse). [PI]
160. Code as the ground truth that AI edits (JITX). [PI]
161. A coding agent emits editor-API scripts (EasyEDA API Skill). [PI]
162. Persistent project memory of approved rules plus curated system knowledge (Flux). [PI]
163. A chat panel inside KiCad with an embedded MCP server (KiCad-AI-Assistant, Cooper). [ET][PI]
164. Git-snapshot each mutation; roll back when verification fails (copperhead). [ET]
165. LLM planning with deterministic execution, evidence and rollback (kicad-agentic-mcp). [ET]
166. Human review gates after each step (AI-PCB-layout); multi-agent skill pipelines. [ET]
167. Part search with live stock data (JLC/LCSC). [ET]
168. Computer use mixed with tools and skills for GUI-only gaps. [ET]
169. Separate bounding boxes per layer class; categorized placement-clearance conflicts. [MCP]
170. Circuit-pattern and signal-path detectors (buck/LDO, kicad-happy's 21 detectors). [ET][VK]
171. Closed-form SI/PI/EMC/thermal estimates, explicitly not sign-off. [ET]
172. Local models need large context (128k) for reliable tool calling. [ET]
173. Keep cloud services optional and off by default (privacy, training clauses). [ET]

**Evaluation and testing**
174. PCBWorld-Bench as primary benchmark, plus the PCBench/Freerouting suite and tscircuit sets. [ET]
175. Report clean pass, routability, DRV, vias, length versus lower bound, time and layout checks. [ET]
176. Re-run PCBWorld with current routers. [ET]
177. PCBGolf and the devbisme dual-ADC test as showcases (fetch-only). [ET][LIC]
178. Commercial tools as external baselines, not dependencies. [ET]
179. PRO attempt accounting (full denominator; manual repair is not autonomous). [MCP]
180. Tool-selection evals: expected and forbidden tools, safety tiers, call budgets, nondeterminism. [MCP]
181. An independent judge plus a negative control for every guard. [MCP]
182. A test ladder (bytes → end to end), autouse kicad-cli load checks, strict xfails, Hypothesis. [MCP]
183. Netlist node-set diffing before and after each tool call. [MCP]
184. A live-versus-file DRC regression recipe. [MCP]
185. Fixtures: PRO's 14 golden projects, KiCad demos from the install, Antmicro routed ground truth. [MCP][LIC]
186. Head-to-head trials: tools only versus tools plus escape hatches versus coding agent only. [MCP]
187. Transparent evaluation: publish failures; include multilayer boards. [PI]
188. Prove layout on a fixed schematic (the Speedrun method); parallel seeded runs with varied constraints. [ET]
189. Copy the project to a fresh directory to re-verify portability. [PI]
190. Measure the token cost of board-read tools. [MCP]

**Licensing, data, patents**
191. MPL-2.0 core; GPL tools only across process boundaries; GPL bridges in a separate repo. [LIC]
192. REUSE layout, SPDX headers, `reuse lint`. [LIC]
193. cargo-deny, pip-licenses/licensecheck and ScanCode gates; `THIRD_PARTY_NOTICES`. [LIC]
194. DCO with inbound=outbound; no CLA. [LIC]
195. An AI-contribution rule: no GPL, AGPL or unlicensed source in prompts; clean-room reimplementation. [LIC]
196. Dataset manifests with pinned SHA and SPDX, fetched at run time; tiers R/SA/E; exclude NC/ND. [LIC]
197. Keep any extracted footprint corpus separate under CC-BY-SA with the exception. [LIC]
198. Rule packs as paraphrased facts plus structured citations, CC0; no verbatim content or PDFs. [LIC]
199. Weights only from Apache/MIT bases, with OSAID model cards; record synthetic-data generators. [LIC]
200. Prefer solver- or DRC-generated supervision over API-model SFT data. [LIC]
201. Relicense now, while there is a sole copyright holder. [LIC]
202. A takedown and contact process plus a data card. [LIC]
203. Re-verify licenses at every release. [LIC]
204. Keep an FTO watch-list; counsel before RL policies or learned routability predictors. [PI][LIC]
205. Collect prior art predating 2024-04-03 against NVIDIA US 2025/0315590. [PI]
206. Treat vendor facts as perishable; re-check before citing. [VK]
207. Synthetic, physics-scored training data (Quilter) as a route to clean-licensed learned components. [PI]
208. Learn constraints or reusable modules from prior boards (Cadence '060, Wistron): flagged. [PI]
209. Patented or flagged techniques, noted only: hierarchical RL agents with a dispatcher; imitation bootstrapping; SMC net-order look-ahead; ray/octagon candidate points; GPU stencil overlap counting; ML parasitic display. [PI]
210. Training-infrastructure idea: a fast simulator plus actor-learner RL (Sebulba/EnvPool). [PI]
211. Zuken idea: a brain learned from a user's past designs that can be "untaught" by a dirty design. [PI]
212. The documented commercial input contract (outline, pre-placed connectors, locked copper, named planes) as our setup checklist. [VK][PI]
213. Expect most fab friction from documentation, library, BOM and process tier; check them too. [PI]

**Additional approaches named in the sources**

214. Generate net classes and design rules from a field solve (Z0 Field Solver PCM plugin). [ET]
215. Vision-model routing trained on large synthetic image sets (tscircuit Z01; "routing as image transformer"). [ET]
216. Publish an A2A agent card alongside MCP (Freerouting `/.well-known/agent.json`). [ET][VK]
217. As a last-resort fallback, drive GUI dialogs through accessibility APIs and scrape the DRC grid (KMS AT-SPI driver). [MCP]
218. A native bridge that drives the user's own KiCad GUI and screenshots windows back to the AI (Adom). [ET]
219. A KiCad fork with extra LLM instrumentation instead of waiting for upstream API (Backplane). [ET]
220. Cloud design-as-a-service behind MCP (HeyPCB), which raises privacy and upload concerns. [ET]
221. Schematic auto-placement: Sugiyama/force-directed baseline plus a VF2 subgraph "motif composer" (eda-agent). [ET]
222. Topological routing: Topola, route-rnd rubber-band sketch, TopoR (no preferred directions), Situs, JITX continuous geometry. [ET][PI]
223. Shape-based gridless routing with multi-pass cost-based conflict reduction, rip-up and push-and-shove (Electra, Specctra). [ET]
224. Octilinear grid A* with rip-up and reroute, and pose-based A* with a Dubins heuristic for diff pairs (KRT). [ET][VK]
225. PathFinder negotiated congestion with a GPU SSSP kernel for huge regular backplanes (OrthoRoute). [ET]
226. Capacity-mesh and hypergraph successive approximation instead of sequential net routing (tscircuit). [ET]
227. Pin and gate swapping inside the router (JITX); KiCad 10 pin/gate swap with back-annotation as a lever. [PI][ET]
228. Rewrite hot router paths in C++ or Rust (Quilter 6.7× local and 4× global; fastroute; KRT's Rust core). [PI][ET]
229. MCP prompts carrying strategy guidance (KMS `component_placement_strategy`). [MCP]
230. Reviewer subagents that check intermediate artifacts (BOM, schematic plan) in skill pipelines (POA). [MCP]
231. Route in a separate process with progress phases (Fanout, Autoroute, Optimize) and DSN fallback (Freerouting 2.5 IPC). [VK]
232. Power-net-aware placement that orients same-net pins toward planned pours; region ground pours for isolation (Quilter 2026). [PI]
233. Treat comprehension as replacing the layout-kickoff meeting: the engineer verifies the interpreted constraints (Quilter). [PI]
