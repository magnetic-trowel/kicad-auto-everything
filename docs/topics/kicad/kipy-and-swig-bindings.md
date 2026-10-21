# KiCad Python bindings: kicad-python (kipy) and legacy SWIG `pcbnew`

**TL;DR**
- **kipy** is the official IPC client: MIT, PyPI **0.8.0 (2026-08-30)**. Every KiCad-11-only method (design rules, custom rules, library placement, netlist import, `export_*`, `set_net_classes`) exists only on unreleased main (0.9.0.dev0). Corrected by VK [P].
- **kipy traps:**
  - The 0.8.0 orientation setter **drops every 3D model**.
  - `Track.length` is a method.
  - Losing the token can silently reconnect a transaction to a new KiCad [P].
- **SWIG `pcbnew`** was deprecated in 9.0 and is to be removed in 11.0. It still offers stand-alone `LoadBoard`/`SaveBoard`, `ExportSpecctraDSN`, `ImportSpecctraSES` and `WriteDRCReport` in 10.0 [P].
- **`SaveBoard` silently drops data.** Never let pcbnew or kipy re-serialize a user's file [P].
- Under GPL-3.0-or-later, linking SWIG is license-compatible. The problem is longevity: **SWIG plugins break in KiCad 11** [I].

## Key facts

### kicad-python (kipy)
| Item | Value |
|---|---|
| License | MIT. Relicensed from GPLv3 on 2025-02-02 (commit 7b8a97f7) so plugins would not be "tainted" [P] ([issue #9](https://gitlab.com/kicad/code/kicad-python/-/work_items/9)) |
| Releases | 0.1.0 2024-12-21 · 0.2.0 2025-02-19 · 0.3.0 03-29 · 0.4.0 07-08 · 0.5.0 10-13 · 0.6.0 2026-03-15 · 0.7.0/0.7.1 04-17/18 · 0.8.0 08-30 [P] ([PyPI](https://pypi.org/project/kicad-python/)) |
| Requirements | `protobuf<6,>=5.29`, `pynng<0.10,>=0.9`, `jsonschema`, Python ≥3.9; `KiCad.check_version` checks compatibility [P] ([PyPI JSON](https://pypi.org/pypi/kicad-python/json)) |
| main | 0.9.0.dev0, "Production/Stable" classifier. Latest commit 2026-09-23 adds net-class assignments. Can auto-launch `kicad-cli api-server` (KiCad 11) [P] |
| `Board` methods in 0.8.0 | footprints, tracks, vias, zones, pads, nets; by-net, by-netclass and connected items (KiCad ≥10.0.1); `refill_zones`, `interactive_move`, `flip_items`, `hit_test`, `get_stackup`, pad polygons, commits, `run_action`, save/revert/`get_as_string` [P] |
| main-only, needs KiCad 11 | `get/set_design_rules`, `get/set_custom_design_rules`, `place_footprint_from_library`, `import_netlist`, `export_*`, `open/create/close_document`, `set_net_classes`, net-class assignments [P] (corrected, VK) |
| Examples | `move_footprints.py`, `create_zone.py`, `round_tracks`, `design_rules.py`, `check_for_testpoints.py`, `headless.py`, `jobs.py`, `layer_indicator` [P] |
| Docs | [docs.kicad.org/kicad-python-main](https://docs.kicad.org/kicad-python-main/) |
| License wrinkle | A stray GPL header in `kipy/proto/common/types/__init__.py`. 11 of 17 generated `*_pb2.pyi` stubs in 0.7.1 carry GPL headers ([issue #134](https://gitlab.com/kicad/code/kicad-python/-/work_items/134), open). Irrelevant for our GPL code [I]. |

**Traps found by MCP servers** [P]:
- The 0.8.0 `FootprintInstance.orientation` setter "rotates the footprint's fields, pads, text, zones and shapes, then rebuilds `definition.items` from only those types — every `Footprint3DModel` is dropped, even when the angle is unchanged". KMS snapshots the models, re-attaches them, and pins the behaviour with a tripwire test ([KMS ebc2ed1](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/ebc2ed15691d183e25e7eb815f37b5b6a9ec3909)). PRO hit the same bug four weeks later (#1325, [3659ceb5](https://github.com/oaslananka/kicad-mcp-pro/commit/3659ceb5e7ee9c7ef73e53cc0cad2ca70bbd5dde)).
- `Track.length` is a method. Mocks modelled it as an int, so "the mock could only fail in the way its author expected" ([PRO 30d02c76](https://github.com/oaslananka/kicad-mcp-pro/commit/30d02c76b74b95ab83d588d43cbbf33630014e7f)).
- A TTL expiry discarded the authenticated client and its per-instance token. The old transaction could then stage a mutation in a *newly started* KiCad. Treat `AS_TOKEN_MISMATCH` as a break in session continuity.

### SWIG `pcbnew`
- "Deprecated as of KiCad 9.0… The current plan is to remove the SWIG bindings in KiCad 11.0". It is "a raw binding layer over KiCad rather than a true API" and "unstable" between majors [P] ([dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)).
- **10.0 stand-alone helpers:** `LoadBoard`/`SaveBoard`, `ExportSpecctraDSN(BOARD*, path)`, `ImportSpecctraSES(BOARD*, path)`, `WriteDRCReport(board, file, units, …)` [P] ([pcbnew_scripting_helpers.h](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/python/scripting/pcbnew_scripting_helpers.h)). 10.0.6 fixed quoting, duplicate-reference and layer-name bugs in DSN export.
- **Hazards** [P]:
  - `SaveBoard` "is not a reformat: it drops data". Details in [file-format-and-version-hazards.md](file-format-and-version-hazards.md).
  - pcbnew writes a possibly stale project model over `.kicad_pro` on every save. KMS restores `net_settings` with `preserve_project_settings()`.
  - "Calling `ZONE_FILLER` via SWIG causes segfault" ([KMS KNOWN_ISSUES](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/KNOWN_ISSUES.md)).
  - A SWIG `BOARD` proxy can lose its methods after some sequences (`delete_trace` + auto-save), and `open_project` kept reporting success ([KMS f65eaf2](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f65eaf2798c642eb174af2ace6a9c7e8d2753ec8)).
  - `ImportSpecctraSES`/`ExportSpecctraDSN` return `False` on failure, and a `!= 0` check accepted it because `False == 0` ([KMS f476a97](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/f476a9794daaa323e9020010b5d09376c680bbd4)).
  - Calling `Flip()` before `board.Add()` caused "a 30s hang in KiCAD 9" (KMS).
  - SWIG has no undo and needs a manual reload; IPC has transactions. KMS's `place_component` is hybrid: SWIG loads the library footprint, IPC places it.
- **Plugins that break in 11:**
  - DeepPCB's KiCad plugin (a SWIG `ActionPlugin`).
  - Freerouting's SWIG path ("legacy KiCad SWIG support will be removed in the next release").
  - KRT's External Plugin.
  - The Freerouting PCM plugin (SWIG runtime) [P].
- **PRO's policy:** "There is no SWIG fallback", enforced by `scripts/check_no_pcbnew.py` (ADR-0007) [P].

## Recommendations for our system
- **Depend on kipy from PyPI.** Gate features on the released version and KiCad point release, not on main [I].
- **Never call kipy whole-object setters or pcbnew `SaveBoard` on a user's file.** Use native IPC operations (e.g. `FlipItems`) or a byte-preserving splice. Snapshot and re-attach 3D models if an orientation write is unavoidable [I, from MCP].
- **Keep SWIG strictly in a short-lived helper process** for DSN/SES on 10.x. Under GPL-3.0-or-later this is a technical choice, not a licensing one: it isolates crashes and segfaults, and the helper disappears in KiCad 11 [I].
- **Never rely on mocks of kipy or pcbnew.** Test against real KiCad. See [mcp-server-testing-practices.md](mcp-server-testing-practices.md).

## Conflicts and open questions
- Which kipy version first exposes each method against 10.0.x versus 11 nightlies is known only from the proto diff.
- Do the kipy 0.9 KiCad-11 methods also degrade gracefully on 10.0.x? Not checked.

## Sources
- research notes:
  - [verification_kicad_and_tools.md § 1 (#6–7, #10), § 3.2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [existing_tools_and_apis.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [kicad_mcp_codebases.md § 1, § 2B–D](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [licensing.md § 1A, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: [kicad-python repo](https://gitlab.com/kicad/code/kicad-python), [kipy board.py @0.8.0](https://gitlab.com/kicad/code/kicad-python/-/blob/0.8.0/kipy/board.py), [@main](https://gitlab.com/kicad/code/kicad-python/-/blob/main/kipy/board.py)

See also: [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md), [file-format-and-version-hazards.md](file-format-and-version-hazards.md), [specctra-freerouting-integration.md](specctra-freerouting-integration.md)
