# KiCad file-format, version and live-vs-saved hazards

**TL;DR**
- **KiCad 9→10 dialect differences can silently miswire boards.** KiCad 10 accepts a numeric `(net N)` and **rebinds it by load order**; in one measurement `(net 2)` landed on GND. KiCad 9 rejects named nets. KiCad 10 boards have no top-level net table [P].
- **Re-serializing through pcbnew `SaveBoard` or kipy setters loses data:** shapes, hidden text, UUIDs, 3D models, format stamps, line endings. "A subprocess may compute, never write" [P].
- **Live versus saved divergence is the most common correctness hazard.** Every MCP server with an IPC path hit it independently [P].
- **Unknown layer names crash KiCad 10.0.5**, and probing the IPC socket wedges it [P].
- **Version differences must be measured, not inferred.** Run CI on KiCad 9 and 10 [I].

## Key facts

### Format eras and dialects
| Hazard | Detail |
|---|---|
| Format stamps | The highest KiCad 9 board stamp is **20241229** (`_NUMERIC_NET_VERSION_MAX`). pcbnew 10 upgrades a KiCad 9 board to **20260206** through a bare `LoadBoard` + `SaveBoard` [P] ([POA CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md)) |
| Net references | Numeric `(net N)` in a KiCad 10 board "is accepted and silently rebound by load order (a real miswire, measured: `(net 2)` landed on GND with no error)". Named `(net "NAME")` in a KiCad 9 board is a hard reject [P] ([adr-cst-substrate.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)) |
| Net table | KiCad 10 boards have no top-level net table. Konnect read the name "at index 2 unconditionally", got `""` for every pad and reported 0 nets; it also wrote zones as `(net 0)`, "an electrically orphaned pour reported as success" (#192) [P] ([1a11f69](https://github.com/mixelpixx/Konnect/commit/1a11f69771c5566f6b621ae4ae4eeffdf9a05cd2), [f2372ca](https://github.com/mixelpixx/Konnect/commit/f2372ca429688ce955c68d2790ca379869adc637)) |
| Unknown layers | `Dwgs.User`, `User.1–45` and inner copper beyond In2 mapped to `BL_UNDEFINED`. KiCad 10.0.5 indexes its layer bitset with the unvalidated value, and placing a stock USB-C footprint "faulted KiCAD at `0xc0000005` … discarding the session's unsaved board". The client saw only an NNG timeout [P] ([ff518c8](https://github.com/mixelpixx/Konnect/commit/ff518c80235c6d546d0b93266fdaad4a57ee0cc4)) |
| Socket probe | A raw connect "never completes NNG's handshake, and afterwards KiCad answers no client at all … until pcbnew restarts" (#498). Discover the socket through filesystem metadata only [P] ([7e2d787](https://github.com/mixelpixx/Konnect/commit/7e2d787603406e6def19fed28f432d77696a55b3)) |
| Units over IPC | KMS IPC handlers ignored `unit`, placing parts "at 1/25.4th of the intended position" when inches were given [P] ([319a65b](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/319a65bd0b49e47fb4fcf2dd37be46f88fa29caa)) |
| Mixed versions | POA's `autoroute_pcb` refuses a KiCad 10 board when only pcbnew 9 is available [P] |
| DRC JSON | The KiCad 10 courtyard classification changed; deleting a missing ID needs a 10-specific postcondition (PRO) [P] |

### Silent data loss on write
- **`pcbnew.SaveBoard` "is not a reformat: it drops data"** [P] ([adr-cst-substrate.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)):
  - Coincident `PCB_SHAPE`s are de-duplicated, because the writer's `std::set` ignores UUIDs (vme-wren: 554 → 552).
  - On KiCad 9 every hidden `fp_text` is destroyed at load (32 → 0).
  - `fill_zones` on KiCad's own `multichannel_mixer-unrouted` upgraded the format in place, dropped 114 footprint property UUIDs, renamed user layers and returned `status="ok"`.
  - A no-op round trip on Windows turned 760 LF line endings into CRLF.
  - pcbnew also overwrites `.kicad_pro` with a possibly stale model (the KMS `preserve_project_settings()` guard).
- **kipy 0.8.0's orientation setter drops 3D models.** See [kipy-and-swig-bindings.md](kipy-and-swig-bindings.md).
- **Torn writes.** Plain `write_bytes` opens with `O_TRUNC`. With a concurrent reader on NTFS this gave "345 torn reads out of 800 … against 0 out of 25,529 through the [atomic] helper" [P].
- **Unloadable but well-formed output.** `add_trace(layer="banana")` wrote a well-formed file that would not load. Angle spellings `+90`, `9_0` and `1e-400` read as numbers in Python but break KiCad's parser [P].
- **Concurrent writes.** Concurrent file-backed PCB mutations lost edits in PRO, which now serializes them [P] ([cda8afca](https://github.com/oaslananka/kicad-mcp-pro/commit/cda8afca6a313029914570cf598a9f114e5cacaa)).
- **POA's fix** is a stdlib-only, byte-preserving S-expression CST that round-trips **15,711/15,711 files**. KiCad itself writes in only two places: library upgrades, and the routed copy made by `autoroute_pcb`. pcbnew computes zone fills read-only, and the polygons are spliced into the user's file [P].

### Live versus saved divergence
- **Konnect's scorer read the saved file** while KiCad held unsaved moves. A negative control reproduced "verdict 'pass', score 70, zero hard_failures despite a real live collision". The fix prefers the live `SaveDocumentToString` snapshot and tags `"source": "ipc" | "saved_file"` (#595) [P] ([bc3b6c6](https://github.com/mixelpixx/Konnect/commit/bc3b6c6346dad3f2e95f9b97ed3a9aea3bfd319a)).
- **Konnect after a lost IPC link:** once a board has been seen live and IPC drops, file fallback is blocked (`unsafe_file_fallback`), because the saved file "may be older than lost editor state" [P].
- **KMS session pinning (#223).** Pin to IPC only when the GUI provably has the same `.kicad_pcb` open; never upgrade silently from SWIG, "the exact lost-edits bug in #223" [P] ([IPC_BACKEND_STATUS.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/IPC_BACKEND_STATUS.md)).
- **KMS save clobbering.** `save_project` called `SaveBoard` unconditionally, "destroying any direct edit". It now checks content-hash divergence, not mtime [P] ([9e12628](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/9e1262888b5e9026318bb8a4f5884b53bb87873b), [c2c77f5](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/c2c77f5995665729bbaa35790dd2e8ca2e58fba1)).
- **KMS empty reads.** An empty IPC read returned `success:true` with zeroed counts "AND an embedded error string" [P].
- **Konnect board-write gates:**
  - `ensure_board_is_active`;
  - `attempt_ipc_write`: file fallback only when IPC is unreachable; any KiCad response, including a rejection, "fails closed";
  - `refuse_if_board_open_in_kicad` [P] ([KICAD_INTEGRATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/KICAD_INTEGRATION.md)).

### Fix-commit counts by bug class
Non-merge fix commits by subject keyword, KMS / Konnect / PRO / POA:
- stale or live state: 11 / 11 / 3 / 3
- KiCad 10 compatibility: 13 / 7 / 7 / 3
- nets: 15 / 14 / 7 / 20
- library tables: 28 / 43 / 6 / 11
- IPC transport: 15 / 27 / 4 / 0
- units: 3 / 1 / 3 / 0

Source: [kicad_mcp_codebases.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md) [P].

### Parsing libraries
- **kiutils** (GPL-3.0, "KiCad 6.0 and up"; last PyPI 1.4.8 on 2024-02-02) and **kicad-skip** (LGPL-2.1+; last PyPI 0.2.5 on 2024-02-16) both predate the KiCad 9/10 format changes [P] ([kiutils](https://pypi.org/project/kiutils/), [kicad-skip](https://pypi.org/project/kicad-skip/)).
- The S-expression formats are documented for PCB, footprint, schematic, symbol library and worksheet [P] ([dev-docs](https://gitlab.com/kicad/services/kicad-dev-docs/-/tree/master/content/file-formats)).

## Recommendations for our system
- **Use a byte-preserving CST file layer.** POA's `_cst.py` is reusable, since our code is GPL-3.0-or-later. Use atomic writes, validate values before writing, and serialize mutations. Never write through `SaveBoard` or whole-object setters [I].
- **Version-gated emitters:** numeric nets up to stamp 20241229, named nets above it; canonical layer names only; refuse unknown layers before any IPC send [I].
- **Every read carries a source tag** (`source: live|saved|mixed`, `board_rev`, `kicad_version`). After a board has been seen live, refuse file writes for the rest of the session [I]. See [mcp-tool-surface-spec.md](mcp-tool-surface-spec.md).
- **Run a CI matrix** on KiCad 9.0.x and 10.0.x (Linux, macOS, Windows), with a `kicad-cli` load check on every file a test produces [I].
- **In file mode, confirm the format stamp is unchanged** after each write [I].

## Conflicts and open questions
- Which further 9/10 dialect differences exist (padstacks, tenting, DRC JSON)? Discovered only by measurement so far; none is documented in advance.
- Bug counts come from commit subjects and undercount POA's `test:`/`docs:` labelled fixes.

## Sources
- research notes:
  - [kicad_mcp_codebases.md § 2B–E, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [existing_tools_and_apis.md § 2 (kiutils, kicad-skip)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [licensing.md § 1F](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: commit links above

See also: [transform-math-pitfalls.md](transform-math-pitfalls.md), [kipy-and-swig-bindings.md](kipy-and-swig-bindings.md), [mcp-server-lessons.md](mcp-server-lessons.md), [mcp-server-testing-practices.md](mcp-server-testing-practices.md)
