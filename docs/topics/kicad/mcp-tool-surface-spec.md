# Recommended MCP tool surface for our KiCad placer/router (spec derived from the MCP server lessons)

**TL;DR**
- **About 20–25 tools in three groups, kept apart:**
  - **read and score:** bounded, source-tagged reads plus an independent referee;
  - **propose:** deterministic engines return candidates, never writes;
  - **apply:** revision-bound, one undo entry, verified after the push [I].
- **Every response carries `{source, board_rev, kicad_version, outcome}`.** Once a board has been seen live, file writes are refused for the session [I].
- **Explicit escape hatches** (a restricted `kicad_cli` tool and a verified raw CST splice), because "MCP-only" doctrine lost 3/18 vs 18/18 in POA's A/B [P/I].
- **Automatic verification hooks after every apply:** readback against intent, footprint content counts, score or DRC, connectivity, format stamp [I].
- **Untested.** It needs head-to-head trials against coding-agent-only and tools plus escape hatches [I].

## Key facts
This spec comes from [kicad_mcp_codebases.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md) [I], plus ET §7 and PI §8 recommendations. Evidence behind each rule is in [mcp-server-lessons.md](mcp-server-lessons.md). Conventions: lengths in mm; angles in degrees CCW as KiCad displays them; coordinates in KiCad's Y-down board frame.

### State model
- **Board identity:** a session is bound to exactly one board identity (project path, board path, KiCad instance token).
  - `backend = ipc_live` when KiCad holds the board open, `file` otherwise.
  - Once seen live, file writes are refused (Konnect `unsafe_file_fallback`).
- **`board_rev`** is the SHA-256 of a normalized live snapshot (`SaveDocumentToString`) or of the file bytes.
- **Mutation flow:**
  1. `propose_*` returns a candidate `{candidate_id, base_rev, diff, predicted_score}`.
  2. `apply_candidate(candidate_id, expected_rev)` refuses on drift.
  3. It applies through one IPC commit group (chunked ≤32 creates, one undo entry), or through an atomic byte-preserving splice in file mode.
  4. It reads back and runs the hooks.
- **Transport:** correlate requests by ID; never socket-probe; bound timeouts; an uncertain write is reported `uncertain`, never retried.
- **Outcome envelope:** `complete` | `partial` (applied, failed and unattempted items) | `refused` (with proof nothing changed) | `uncertain` (stop and reconcile) | `check_unavailable`. Unchecked categories are `null`, never `0`.

### Tools
| # | Tool | Contract |
|---|---|---|
| 1 | `board_summary()` | outline `{shape: rect/polygon/unproven, polygon_mm, area}`, layers, stackup, netclasses, counts, design rules, source, board_rev |
| 2 | `list_footprints(filter?, fields?)` | filter by refs, side, locked, group, bbox; bounded with `limit`/`offset` and `_total`/`_truncated` |
| 3 | `get_pads(refs or net)` | board coordinates from the single oracle-pinned transform ([transform-math-pitfalls.md](transform-math-pitfalls.md)) |
| 4 | `get_netlist(scope?)` | `{net: {class, pads, is_power, fanout}}` |
| 5 | `get_ratsnest(nets?)` | airwires plus total HPWL |
| 6 | `render(view, bbox?, highlight?, px=1024)` | `kicad-cli` SVG→PNG; returned only when asked |
| 7 | `score_placement(candidate? or current)` | verdict `pass`/`hard_fail`/`outline_unproven`/`outline_missing`. Hard: polygon courtyard overlap, outside outline. Soft: HPWL, connector-to-edge, decap distance (non-ground associations only), thermal and keepout rules from rule packs |
| 8 | `run_drc(sync_live=true, refill_zones=true)` | violations, unconnected, parity (null if not run), by_rule, source evidence; never drops categories ([drc-report-and-repair-loop.md](drc-report-and-repair-loop.md)) |
| 9 | `check_connectivity(expected?)` | shorts, opens, pad-net mismatches via `kicad-cli` netlist node sets |
| 10 | `propose_placement(refs or group, constraints, objective?, seed?)` | constraints: fixed, keepouts, regions, rotate_set, side. Refuses an unproven outline without an explicit polygon; a candidate that does not beat the current score is `blocked` |
| 11 | `propose_moves([{ref, x?, y?, rot?, side?, dx?, dy?}])` | the small-explicit-move path the LLM uses most; scored like any other candidate |
| 12 | `propose_route(nets or netclass, engine: freerouting/pad_to_pad/fanout/pns, attempts=3, pass_schedule?, keep_existing=locked_only)` | Freerouting with every fix in [specctra-freerouting-integration.md](specctra-freerouting-integration.md). Best-of-N score `nets_routed·1000 + segments (+50,000 if all route)` plus the post-import DRC delta |
| 13 | `propose_fanout(ref, style: dogbone/inline, via_rule?)` | BGA/QFN escape plan |
| 14 | `apply_candidate(candidate_id, expected_rev, description)` | outcome, applied items, `board_rev_after`, verification `{score, drc_summary, connectivity}` |
| 15 | `undo_last(n=1)` / `revert_to(rev)` | native KiCad undo / snapshot journal (file mode only) |
| 16 | `snapshot(label)` / `diff(rev_a, rev_b)` | moved, added, removed, nets changed |
| 17 | `kicad_cli(args[])` | escape hatch limited to drc, erc, export, render, and upgrade of libraries or a copy (never the user's board in place: `upgrade` re-serializes, see [file-format-and-version-hazards.md](file-format-and-version-hazards.md)); outputs to a temp dir |
| 18 | `raw_edit(path, splice{anchor_uuid, old_sexpr, new_sexpr}, expected_rev)` | byte-preserving CST splice, then a `kicad-cli` load check and connectivity check; refused while the board is open live |

### Verification hooks on every apply
1. Read back each touched object and compare with the intent, never with an echo of the request.
2. Check 3D-model, field and pad counts on every touched footprint (catches whole-object re-serialization loss).
3. Run `score_placement` for placement applies; run `run_drc` with unconnected items for routing applies.
4. Check connectivity against the expected netlist.
5. In file mode, confirm the format stamp is unchanged.

A failure in 1–4 makes the outcome `partial` or `uncertain`, naming the first mismatch.

### Additions from the broader survey
- **Human-in-the-loop UX** (DeepPCB Cooper pattern): read → summarize → propose → per-item accept or reject → each accepted change as one undo entry [P] ([Cooper](https://deeppcb.ai/cooper-kicad-plugin/)). See [../landscape/deeppcb.md](../landscape/deeppcb.md).
- **Freerouting as a single tool** that returns scores and a compact DRC summary, never geometry [I, from VK].
- **An interactive engine-grounded router** (KiCad push-and-shove via PCBWorld-Engine) offered as small candidate actions. In PCBWorld, interactive engine use scored 0.65 clean-pass versus 0.19 plan-then-execute and 0.02 engine-free [P]. See [../landscape/measured-tool-comparisons.md](../landscape/measured-tool-comparisons.md).
- **Distribution:** an IPC-runtime KiCad plugin plus MCP server, published through the PCM, where there are zero AI plugins today [P/I]. Pair it with Agent Skills playbooks, following Siemens Fuse and CELUS's MCP-plus-Skills pattern [I].

## Recommendations for our system
- **Keep about 12 tools always visible** (1–9, 11, 14, 17), named in the server instructions. Load propose and route tools as a toolset only when the client honours `list_changed`; otherwise expose them all [I].
- **Build the referee (7–9) before any placer**, and never let a placer apply without beating the referee's score [I].
- **Run tool-selection evals** with expected and forbidden tools and call budgets on this surface before release ([mcp-server-testing-practices.md](mcp-server-testing-practices.md)) [I].

## Conflicts and open questions
- The spec is untested. Plan head-to-head trials on a shared board corpus: tool only, tool plus escape hatches, coding agent only.
- Until KiCad 11's headless `api-server` ships, live commit groups need a running GUI or a file-mode snapshot journal. PRO tracks headless IPC as preview-only.

## Sources
- research notes:
  - [kicad_mcp_codebases.md § 6, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [existing_tools_and_apis.md § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [verification_kicad_and_tools.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [patents_and_industry.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)

See also: [mcp-server-lessons.md](mcp-server-lessons.md), [ipc-api-10-vs-11.md](ipc-api-10-vs-11.md), [../landscape/commercial-architecture-patterns.md](../landscape/commercial-architecture-patterns.md)
