# kicad-cli: what it can do on 10.0 vs master, and how an agent should use it

**TL;DR**
- `kicad-cli` is the **headless referee on 10.x**. It runs DRC (JSON report, exit code 5 on violations) and ERC, exports netlists for connectivity diffs, and renders images for vision feedback [P].
- **10.0 has no Specctra export.** Master adds `kicad-cli pcb export specctra` (named `specctra`, not `specctra_dsn`; corrected by VK), `api-server`, diff tools and more [P].
- **DRC refills zones only with `--refill-zones`**, and saves only with `--save-board` as well [P].
- **A bad `.kicad_dru` is dropped silently on 10.0.7.** One parse error and `kicad-cli pcb drc` runs with no custom rules and exits 0, so a DRC run is no lint. Check rules files with `kae dru-check` [M].

## Key facts

### Subcommands
| | 10.0 | master adds |
|---|---|---|
| PCB | `pcb drc`; `pcb export` {3d (STEP/GLB/PLY/STL/VRML/XAO/BREP/U3D/3D-PDF), drill, dxf, gencad, gerber, gerbers, hpgl, ipc2581, ipcd356, odb, pdf, pos, ps, stats, svg}; `pcb import`; `pcb render`; `pcb upgrade` | `pcb export specctra`, `pcb export idf/png/stackup`, `pcb diff`, `pcb downgrade` |
| Schematic | `sch erc`; `sch export` {bom, netlist, plot, pythonbom}; `sch upgrade` | `sch diff`, `sch downgrade` |
| Libraries | `fp`/`sym` upgrade and export-svg | `fp diff` |
| Other | `jobset run` (jobsets since KiCad 9: "predefined sets of 'jobs'… plotting, exporting, and running DRC"); `version` | `api-server [--socket SOCKET_PATH] [PROJECT_OR_FILE]` (first commit 2026-03-21); `gerber diff/info/convert png`; `project downgrade`; `git_mergedriver`; `mergetool`; top-level `import` |

Sources: [kicad/cli @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/kicad/cli), [@master](https://gitlab.com/kicad/code/kicad/-/tree/master/kicad/cli), [cli.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/cli/cli.adoc) [P].

- **`pcb import --format` hints in 10.0:** `auto, pads, altium, eagle, cadstar, fabmaster, pcad, solidworks`. Allegro and gEDA are not CLI hints, even though the 10.0 release notes announce those importers [P] ([command_pcb_import.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/kicad/cli/command_pcb_import.cpp)).
- **`pcb export specctra`** was committed 2026-10-14 as "CLI: Add pcb export specctra_dsn", but the subcommand registers as `specctra`. The master docs do not document it yet [P] ([command_pcb_export_specctra.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/kicad/cli/command_pcb_export_specctra.cpp)).

### `pcb drc` (10.0; byte-identical docs on master)
- **Usage:** `kicad-cli pcb drc [-o OUT] [-D KEY=VALUE]... [--format report|json] [--all-track-errors] [--schematic-parity] [--units mm|in|mils] [--severity-all|--severity-error|--severity-warning|--severity-exclusions] [--exit-code-violations] [--refill-zones] [--save-board] INPUT` [P].
- `--exit-code-violations` returns exit code **5** when violations exist, 0 otherwise.
- Zones are not refilled unless `--refill-zones` is given. The board is saved only with both `--refill-zones` and `--save-board`.
- The CLI reads `.kicad_dru` fresh on each run. The 10.0 manual says custom rules "will only be applied if there are no errors in the custom rules definitions" (Board Setup) [P]; an older quote, "Any errors in the custom rules will prevent the design rule checker from running" ([verification_kicad_and_tools.md](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)), does not hold for the CLI.
- **Silent drop, measured on 10.0.7** [M]: one bad token (a `;` comment, a misspelled constraint, function, property, layer or severity, a time unit on a clearance, a repeated constraint, a missing paren or `(version 1)`) and the CLI ignores the whole file, prints nothing and exits 0. `kae dru-check` agreed with KiCad on 50 crafted cases and on all 530 corpus `.kicad_dru` files; KiCad rejects 10 of them on their own boards ([44cebf9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44cebf9dfeb55cb103bdf015ec6fee0965e9119a), [32ad4c4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/32ad4c403bf7b54ecfbdad76185075c58b177189)).
- Master returns exit code 3 (`ERR_INVALID_INPUT_FILE`), "DRC incomplete: could not compile custom design rules.", and writes no report ([91358c2230](https://gitlab.com/kicad/code/kicad/-/commit/91358c2230), "Report custom rule compilation failures in CLI DRC"); not in 10.0.7 [P].
- The report schema, all 67 violation keys and how to map them back to rules are in [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md).

### Other uses seen in MCP servers
- **Rendering.** KMS `get_board_2d_view` renders PNG, JPG or SVG through `kicad-cli`, 1600×1200 by default, returned inline as base64 or as a path. Konnect returns a top-view 3D render with no layer selection [P] ([KMS view.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/board/view.py)).
- **Connectivity diffs.** POA's routing harness compares `kicad-cli` netlist node sets before and after every tool call [P].
- **Coordinate oracle.** `kicad-cli pcb export drill` and Gerber flashes served as ground truth for POA's transform fix: 2,970/2,970 pads matched [P]. See [transform-math-pitfalls.md](transform-math-pitfalls.md).
- **Load check.** POA runs `kicad-cli` on every KiCad file a test leaves behind (autouse fixture) [P].
- **No headless DSN on 10.0.** PRO raises `ManualStepRequiredError`, asking for a one-time GUI export, unless the CLI advertises `pcb export specctra` [P].
- **The POA A/B result** argues against skill text that forbids running `kicad-cli`. See [mcp-server-lessons.md](mcp-server-lessons.md).

## Recommendations for our system
- **Make `kicad-cli pcb drc --format json --schematic-parity --severity-all --refill-zones --exit-code-violations` on a saved copy the single source of truth** for violations, unconnected items and schematic parity. Without `--schematic-parity` parity is not checked, and without `--severity-all` excluded items are not reported. Add `--all-track-errors` in repair loops [I].
- **Check every `.kicad_dru` with `kae dru-check FILE`** (`kae/src/kae/board/dru_check.py`) before relying on it. Exit 0 clean, 1 errors, 2 could not run [M].
  - Static pass: pure Python, names line, column and fix; vocabulary per KiCad version in `kae/src/kae/board/dru_vocab/`.
  - KiCad pass: DRC on a probe board with a sentinel rule appended; no sentinel violation means KiCad dropped the file, and each rule is then tried alone to name the culprits. `--board` runs it on the real board (board-specific layer names).
  - kae's rule readers (`kae.route.rules.build`, `kicad_file.read_rules`) run the static pass and, on an error, use no custom rules, as KiCad does ([c1eadb4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c1eadb4)). kaesynth's `lint_dru` calls `dru_check` too.
  - A plain DRC run on a scratch copy (the earlier advice, from VK) cannot detect a dropped file.
- **Expose a restricted `kicad_cli` escape-hatch tool** (drc, erc, export, render, and upgrade of libraries or of a copy only, never the user's board in place, since `upgrade` re-serializes through KiCad ([file-format-and-version-hazards.md](file-format-and-version-hazards.md)); outputs to a temp dir) instead of forbidding the CLI [I, from MCP].
- **Feature-detect `pcb export specctra`** and switch DSN export from the SWIG helper to the CLI when available [I].
- **Use `kicad-cli` outputs (drill, Gerber, netlist) as test oracles**, never our own re-implementation [I].

## Conflicts and open questions
- Are `th`, `"` and `rad` units accepted by some path other than the resolver? Not tested by running the CLI. See [drc-rule-language-reference.md](drc-rule-language-reference.md).

## Sources
- research notes:
  - [verification_kicad_and_tools.md § 1 (#11–12), § 2.9, § 3.3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [existing_tools_and_apis.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [kicad_mcp_codebases.md § 1, § 2E, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
- primary: [cli.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/cli/cli.adoc) ([rendered](https://docs.kicad.org/10.0/en/cli/cli.html)), [KiCad 9.0.0 notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)

See also: [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md), [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md), [specctra-freerouting-integration.md](specctra-freerouting-integration.md)
