# kicad-cli on 10.0 vs master

Scope: `kicad-cli` subcommands, `pcb drc` flags, the referee command. Not here: DRC JSON schema and keys -> [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md); IPC -> [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md); DSN/SES -> [specctra-freerouting-integration.md](specctra-freerouting-integration.md).
Keys: kicad-cli, pcb drc, referee, --refill-zones, --save-board, --schematic-parity, --exit-code-violations, exit code 5, pcb export specctra, api-server, jobset, pcb import, ManualStepRequiredError, escape hatch

## Subcommands by version
| | 10.0 | master adds |
|---|---|---|
| PCB | `pcb drc`; `pcb export` {3d (STEP/GLB/PLY/STL/VRML/XAO/BREP/U3D/3D-PDF), drill, dxf, gencad, gerber, gerbers, hpgl, ipc2581, ipcd356, odb, pdf, pos, ps, stats, svg}; `pcb import`; `pcb render`; `pcb upgrade` | `pcb export specctra`, `pcb export idf/png/stackup`, `pcb diff`, `pcb downgrade` |
| Schematic | `sch erc`; `sch export` {bom, netlist, plot, pythonbom}; `sch upgrade` | `sch diff`, `sch downgrade` |
| Libraries | `fp`/`sym` upgrade and export-svg | `fp diff` |
| Other | `jobset run` (since KiCad 9: "predefined sets of 'jobs'… plotting, exporting, and running DRC"); `version` | `api-server [--socket SOCKET_PATH] [PROJECT_OR_FILE]` (first commit 2026-03-21); `gerber diff/info/convert png`; `project downgrade`; `git_mergedriver`; `mergetool`; top-level `import` |

Sources: [kicad/cli @10.0](https://gitlab.com/kicad/code/kicad/-/tree/10.0/kicad/cli), [@master](https://gitlab.com/kicad/code/kicad/-/tree/master/kicad/cli), [cli.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/cli/cli.adoc) [P].

1. **`pcb import --format` hints (10.0):** `auto, pads, altium, eagle, cadstar, fabmaster, pcad, solidworks`. Allegro and gEDA are not CLI hints although the 10.0 release notes announce those importers [P] ([command_pcb_import.cpp](https://gitlab.com/kicad/code/kicad/-/blob/10.0/kicad/cli/command_pcb_import.cpp)).
2. **`pcb export specctra`:** committed 2026-10-14 as "CLI: Add pcb export specctra_dsn" but registers as `specctra`, not `specctra_dsn` (corrected, VK); undocumented on master. **10.0 has no Specctra export** [P] ([command_pcb_export_specctra.cpp](https://gitlab.com/kicad/code/kicad/-/blob/master/kicad/cli/command_pcb_export_specctra.cpp)). Feature-detect it and switch DSN export from the SWIG helper to the CLI when present [I].

## pcb drc flags (10.0; docs byte-identical on master)
`kicad-cli pcb drc [-o OUT] [-D KEY=VALUE]... [--format report|json] [--all-track-errors] [--schematic-parity] [--units mm|in|mils] [--severity-all|--severity-error|--severity-warning|--severity-exclusions] [--exit-code-violations] [--refill-zones] [--save-board] INPUT` [P]

| Flag / behaviour | Effect |
|---|---|
| `--exit-code-violations` | exit **5** if violations, else 0 |
| zones | not refilled without `--refill-zones`; board saved only with `--refill-zones` **and** `--save-board` |
| `--schematic-parity` | without it, parity is not checked |
| `--severity-all` | without it, excluded items are not reported |
| `.kicad_dru` | read fresh each run; "Any errors in the custom rules will prevent the design rule checker from running" [P] |

## Referee command
`kicad-cli pcb drc --format json --schematic-parity --severity-all --refill-zones --exit-code-violations` on a **saved copy** = single source of truth for violations, unconnected items and parity; add `--all-track-errors` in repair loops [I]. Lint every generated `.kicad_dru` by running DRC on a scratch copy before applying it (syntax errors block DRC) [I, from VK]. Report schema and the 67 keys: [drc-report-and-repair-loop.md](drc-report-and-repair-loop.md).

## Uses seen in MCP servers
| Use | Detail |
|---|---|
| Rendering | KMS `get_board_2d_view`: PNG/JPG/SVG, 1600×1200 default, base64 inline or path; Konnect: top-view 3D render, no layer selection [P] ([KMS view.py](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/python/commands/board/view.py)) |
| Connectivity diff | POA routing harness diffs netlist node sets around every tool call [P] ([testing](mcp-server-testing-practices.md)) |
| Coordinate oracle | drill export + Gerber flashes as transform ground truth (2,970/2,970 pads) → [transform-math-pitfalls.md](transform-math-pitfalls.md) [P] |
| Load check | POA autouse fixture runs `kicad-cli` on every file a test leaves [P] |
| No headless DSN on 10.0 | PRO raises `ManualStepRequiredError` (one-time GUI export) unless `pcb export specctra` is advertised [P] |
| Don't forbid the CLI | POA A/B → [mcp-server-lessons.md](mcp-server-lessons.md#poa-maintenance-mode-ab-2026-10-19) |

Use `kicad-cli` outputs (drill, Gerber, netlist) as test oracles, never a re-implementation [I]. Expose a restricted `kicad_cli` tool (drc, erc, export, render; `upgrade` only on libraries or a copy, since it re-serializes, see [file-format-and-version-hazards.md](file-format-and-version-hazards.md); outputs to a temp dir) instead of forbidding the CLI [I, from MCP].

## Open questions
- Are `th`, `"` and `rad` accepted by some path other than the resolver? Not tested by running the CLI ([drc-rule-language-reference.md](drc-rule-language-reference.md#units)).

## Sources
- [verification_kicad_and_tools.md § 1 (#11–12), § 2.9, § 3.3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [existing_tools_and_apis.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md); [kicad_mcp_codebases.md § 1, § 2E, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
- [cli.adoc @10.0](https://gitlab.com/kicad/services/kicad-doc/-/blob/10.0/src/cli/cli.adoc) ([rendered](https://docs.kicad.org/10.0/en/cli/cli.html)), [KiCad 9.0.0 notes](https://www.kicad.org/blog/2025/02/Version-9.0.0-Released/)
