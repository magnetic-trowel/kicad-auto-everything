# KiCad file-format, version and live-vs-saved hazards

Scope: 9↔10 dialect differences, silent data loss on write, live vs saved divergence, parsing libraries. Not here: transform bugs -> [transform-math-pitfalls.md](transform-math-pitfalls.md); fix-commit counts per bug class -> [mcp-server-lessons.md](mcp-server-lessons.md#recurring-bug-classes).
Keys: format stamp, 20241229, 20260206, _NUMERIC_NET_VERSION_MAX, numeric net rebinding, named nets, net table, BL_UNDEFINED, unknown layer crash, 0xc0000005, socket probe, SaveBoard data loss, re-serialization, torn writes, O_TRUNC, atomic write, CST, byte-preserving, live vs saved, SaveDocumentToString, unsafe_file_fallback, session pinning, kiutils, kicad-skip

Rules [I]: a subprocess may compute, never write ("A subprocess may compute, never write" [P]); measure version differences, don't infer them; every MCP server with an IPC path hit live-vs-saved divergence independently [P].

## Format eras and dialects
| Hazard | Detail |
|---|---|
| Format stamps | Highest KiCad 9 board stamp **20241229** (`_NUMERIC_NET_VERSION_MAX`); pcbnew 10 upgrades a KiCad 9 board to **20260206** through a bare `LoadBoard` + `SaveBoard` [P] ([POA CLAUDE.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/CLAUDE.md)) |
| Net references | Numeric `(net N)` in a KiCad 10 board "is accepted and silently rebound by load order (a real miswire, measured: `(net 2)` landed on GND with no error)"; named `(net "NAME")` in a KiCad 9 board is a hard reject [P] ([adr-cst-substrate.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)) |
| Net table | KiCad 10 boards have no top-level net table. Konnect read the name "at index 2 unconditionally", got `""` for every pad, reported 0 nets; wrote zones as `(net 0)`, "an electrically orphaned pour reported as success" (#192) [P] ([1a11f69](https://github.com/mixelpixx/Konnect/commit/1a11f69771c5566f6b621ae4ae4eeffdf9a05cd2), [f2372ca](https://github.com/mixelpixx/Konnect/commit/f2372ca429688ce955c68d2790ca379869adc637)) |
| Unknown layers | `Dwgs.User`, `User.1–45`, inner copper beyond In2 mapped to `BL_UNDEFINED`; KiCad 10.0.5 indexes its layer bitset with the unvalidated value; placing a stock USB-C footprint "faulted KiCAD at `0xc0000005` … discarding the session's unsaved board"; client saw only an NNG timeout [P] ([ff518c8](https://github.com/mixelpixx/Konnect/commit/ff518c80235c6d546d0b93266fdaad4a57ee0cc4)) |
| Socket probe | a raw connect "never completes NNG's handshake, and afterwards KiCad answers no client at all … until pcbnew restarts" (#498); discover the socket through filesystem metadata only [P] ([7e2d787](https://github.com/mixelpixx/Konnect/commit/7e2d787603406e6def19fed28f432d77696a55b3)) |
| Units over IPC | KMS IPC handlers ignored `unit`: parts "at 1/25.4th of the intended position" when inches were given [P] ([319a65b](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/319a65bd0b49e47fb4fcf2dd37be46f88fa29caa)) |
| Mixed versions | POA `autoroute_pcb` refuses a KiCad 10 board when only pcbnew 9 is available [P] |
| DRC JSON | KiCad 10 courtyard classification changed; deleting a missing ID needs a 10-specific postcondition (PRO) [P] |

Emit version-gated: numeric nets up to stamp 20241229, named nets above; canonical layer names only; refuse unknown layers before any IPC send [I].

## Silent data loss on write
**`pcbnew.SaveBoard` "is not a reformat: it drops data"** [P] ([adr-cst-substrate.md](https://github.com/ProductOfAmerica/mcp-server-kicad/blob/f5f82e02ffe17bbcba806fec35f3302ee332fefc/docs/adr-cst-substrate.md)):
| Loss | Measurement |
|---|---|
| Coincident `PCB_SHAPE`s de-duplicated (writer's `std::set` ignores UUIDs) | vme-wren 554 → 552 |
| Hidden `fp_text` destroyed at load (KiCad 9) | 32 → 0 |
| `fill_zones` on KiCad's `multichannel_mixer-unrouted` | format upgraded in place, 114 footprint property UUIDs dropped, user layers renamed, returned `status="ok"` |
| No-op round trip on Windows | 760 LF → CRLF |
| `.kicad_pro` | overwritten with a possibly stale model (KMS `preserve_project_settings()` guard) |
| kipy 0.8.0 orientation setter | drops 3D models → [kipy-and-swig-bindings.md](kipy-and-swig-bindings.md#kipy-traps-found-by-mcp-servers) |

Other write failures [P]:
- **Torn writes:** plain `write_bytes` opens with `O_TRUNC`; with a concurrent reader on NTFS, "345 torn reads out of 800 … against 0 out of 25,529 through the [atomic] helper".
- **Unloadable but well-formed:** `add_trace(layer="banana")` wrote a file that would not load; angle spellings `+90`, `9_0`, `1e-400` read as numbers in Python but break KiCad's parser.
- **Concurrent writes:** concurrent file-backed PCB mutations lost edits in PRO, which now serializes them ([cda8afca](https://github.com/oaslananka/kicad-mcp-pro/commit/cda8afca6a313029914570cf598a9f114e5cacaa)).
- **POA's fix:** stdlib-only, byte-preserving S-expression CST, round-trips **15,711/15,711 files**. KiCad writes in only two places: library upgrades and the routed copy made by `autoroute_pcb`; pcbnew computes zone fills read-only and the polygons are spliced into the user's file.

Use a byte-preserving CST file layer (POA's `_cst.py` is reusable under our GPL-3.0-or-later); atomic writes; validate values before writing; serialize mutations; never write through `SaveBoard` or whole-object setters; in file mode confirm the format stamp is unchanged after each write [I].

## Live versus saved divergence
| Case | Detail [P] |
|---|---|
| Konnect scorer read the saved file while KiCad held unsaved moves | negative control: "verdict 'pass', score 70, zero hard_failures despite a real live collision"; fix prefers the live `SaveDocumentToString` snapshot and tags `"source": "ipc" \| "saved_file"` (#595) ([bc3b6c6](https://github.com/mixelpixx/Konnect/commit/bc3b6c6346dad3f2e95f9b97ed3a9aea3bfd319a)) |
| Konnect after a lost IPC link | once seen live, file fallback is blocked (`unsafe_file_fallback`): the saved file "may be older than lost editor state" |
| KMS session pinning (#223) | pin to IPC only when the GUI provably has the same `.kicad_pcb` open; never upgrade silently from SWIG, "the exact lost-edits bug in #223" ([IPC_BACKEND_STATUS.md](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/cbb59a6203997f5e916be7e0480d63fe5519134a/docs/IPC_BACKEND_STATUS.md)) |
| KMS save clobbering | `save_project` called `SaveBoard` unconditionally, "destroying any direct edit"; now checks content-hash divergence, not mtime ([9e12628](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/9e1262888b5e9026318bb8a4f5884b53bb87873b), [c2c77f5](https://github.com/mixelpixx/KiCAD-MCP-Server/commit/c2c77f5995665729bbaa35790dd2e8ca2e58fba1)) |
| KMS empty reads | an empty IPC read returned `success:true` with zeroed counts "AND an embedded error string" |
| Konnect board-write gates | `ensure_board_is_active`; `attempt_ipc_write` (file fallback only when IPC is unreachable; any KiCad response, including a rejection, "fails closed"); `refuse_if_board_open_in_kicad` ([KICAD_INTEGRATION.md](https://github.com/mixelpixx/Konnect/blob/9488e5f09717cb508cb25779dc16586d1f06f758/docs/KICAD_INTEGRATION.md)) |

Every read carries `source: live|saved|mixed`, `board_rev`, `kicad_version`; after a board has been seen live, refuse file writes for the session [I] ([tool surface](mcp-tool-surface-spec.md#state-model)).

## Parsing libraries
- **kiutils** (GPL-3.0, "KiCad 6.0 and up"; last PyPI 1.4.8, 2024-02-02) and **kicad-skip** (LGPL-2.1+; last PyPI 0.2.5, 2024-02-16) predate the KiCad 9/10 format changes [P] ([kiutils](https://pypi.org/project/kiutils/), [kicad-skip](https://pypi.org/project/kicad-skip/)).
- S-expression formats documented for PCB, footprint, schematic, symbol library, worksheet [P] ([dev-docs](https://gitlab.com/kicad/services/kicad-dev-docs/-/tree/master/content/file-formats)).

## CI matrix
KiCad 9.0.x and 10.0.x on Linux, macOS, Windows, with a `kicad-cli` load check on every file a test produces [I] ([testing](mcp-server-testing-practices.md)).

## Open questions
- Further 9/10 dialect differences (padstacks, tenting, DRC JSON)? Found only by measurement so far; none documented in advance.

## Sources
- [kicad_mcp_codebases.md § 2B–E, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md); [existing_tools_and_apis.md § 2 (kiutils, kicad-skip)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md); [licensing.md § 1F](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md); commit links above
