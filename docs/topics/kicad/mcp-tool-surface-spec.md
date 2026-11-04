# MCP tool surface for our KiCad placer/router (spec)

Scope: proposed state model, 18-tool surface, verification hooks and visibility for our MCP server. Untested [I]. Not here: evidence behind each rule -> [mcp-server-lessons.md](mcp-server-lessons.md); agent-loop patterns from the field -> [../ux/agent-tooling-reliability-patterns.md](../ux/agent-tooling-reliability-patterns.md).
Keys: tool surface, read/score, propose, apply, apply_candidate, board_rev, expected_rev, outcome envelope, complete, partial, refused, uncertain, check_unavailable, escape hatch, kicad_cli tool, raw_edit, CST splice, verification hooks, score_placement, run_drc, propose_route, always-visible core

Derived from [kicad_mcp_codebases.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md) plus ET §7 and PI §8 [I]. Conventions: lengths mm; angles degrees CCW as KiCad displays them; coordinates in KiCad's Y-down board frame. About 20–25 tools in three groups kept apart: **read and score** (bounded, source-tagged reads + an independent referee), **propose** (deterministic engines return candidates, never writes), **apply** (revision-bound, one undo entry, verified after the push). Explicit escape hatches (17, 18) because "MCP-only" doctrine lost 3/18 vs 18/18 in POA's A/B ([lessons](mcp-server-lessons.md#poa-maintenance-mode-ab-2026-10-19)) [P/I].

## State model
- **Session ↔ one board identity** (project path, board path, KiCad instance token); `backend = ipc_live` when KiCad holds the board open, else `file`. Once seen live, file writes are refused for the session (Konnect `unsafe_file_fallback`).
- **`board_rev`** = SHA-256 of a normalized live snapshot (`SaveDocumentToString`) or of the file bytes. Every response carries `{source, board_rev, kicad_version, outcome}`.
- **Mutation flow:**
  1. `propose_*` → `{candidate_id, base_rev, diff, predicted_score}`.
  2. `apply_candidate(candidate_id, expected_rev)` refuses on drift.
  3. Applies through one IPC commit group (creates chunked ≤32, one undo entry) or an atomic byte-preserving splice in file mode.
  4. Reads back and runs the hooks.
- **Transport:** correlate requests by ID; never socket-probe; bounded timeouts; an uncertain write is reported `uncertain`, never retried.
- **Outcome envelope:** `complete` | `partial` (applied, failed, unattempted items) | `refused` (with proof nothing changed) | `uncertain` (stop and reconcile) | `check_unavailable`. Unchecked categories are `null`, never `0`.

## Tools
| # | Tool | Contract |
|---|---|---|
| 1 | `board_summary()` | outline `{shape: rect/polygon/unproven, polygon_mm, area}`, layers, stackup, netclasses, counts, design rules, source, board_rev |
| 2 | `list_footprints(filter?, fields?)` | filter by refs, side, locked, group, bbox; bounded `limit`/`offset` with `_total`/`_truncated` |
| 3 | `get_pads(refs or net)` | board coordinates from the single oracle-pinned transform ([transform-math-pitfalls.md](transform-math-pitfalls.md#one-transform-module-oracle-pinned)) |
| 4 | `get_netlist(scope?)` | `{net: {class, pads, is_power, fanout}}` |
| 5 | `get_ratsnest(nets?)` | airwires + total HPWL |
| 6 | `render(view, bbox?, highlight?, px=1024)` | `kicad-cli` SVG→PNG; returned only when asked |
| 7 | `score_placement(candidate? or current)` | verdict `pass`/`hard_fail`/`outline_unproven`/`outline_missing`. Hard: polygon courtyard overlap, outside outline. Soft: HPWL, connector-to-edge, decap distance (non-ground associations only), thermal and keepout rules from rule packs |
| 8 | `run_drc(sync_live=true, refill_zones=true)` | violations, unconnected, parity (null if not run), by_rule, source evidence; never drops categories ([drc-report-and-repair-loop.md](drc-report-and-repair-loop.md#parser-and-loop-requirements)) |
| 9 | `check_connectivity(expected?)` | shorts, opens, pad-net mismatches via `kicad-cli` netlist node sets |
| 10 | `propose_placement(refs or group, constraints, objective?, seed?)` | constraints: fixed, keepouts, regions, rotate_set, side; refuses an unproven outline without an explicit polygon; a candidate not beating the current score is `blocked` |
| 11 | `propose_moves([{ref, x?, y?, rot?, side?, dx?, dy?}])` | the small-explicit-move path the LLM uses most; scored like any candidate |
| 12 | `propose_route(nets or netclass, engine: freerouting/pad_to_pad/fanout/pns, attempts=3, pass_schedule?, keep_existing=locked_only)` | Freerouting with every fix in [specctra-freerouting-integration.md](specctra-freerouting-integration.md#wrapper-tool-route_with_freerouting); best-of-N score `nets_routed·1000 + segments (+50,000 if all route)` + post-import DRC delta; returns scores and compact DRC summary, never geometry [I, from VK] |
| 13 | `propose_fanout(ref, style: dogbone/inline, via_rule?)` | BGA/QFN escape plan |
| 14 | `apply_candidate(candidate_id, expected_rev, description)` | outcome, applied items, `board_rev_after`, verification `{score, drc_summary, connectivity}` |
| 15 | `undo_last(n=1)` / `revert_to(rev)` | native KiCad undo / snapshot journal (file mode only) |
| 16 | `snapshot(label)` / `diff(rev_a, rev_b)` | moved, added, removed, nets changed |
| 17 | `kicad_cli(args[])` | escape hatch: drc, erc, export, render, `upgrade` of libraries or a copy only (never the user's board in place: it re-serializes, [file-format-and-version-hazards.md](file-format-and-version-hazards.md)); outputs to a temp dir |
| 18 | `raw_edit(path, splice{anchor_uuid, old_sexpr, new_sexpr}, expected_rev)` | byte-preserving CST splice → `kicad-cli` load check + connectivity check; refused while the board is open live |

## Verification hooks on every apply
1. Read back each touched object; compare with the intent, never with an echo of the request.
2. Check 3D-model, field and pad counts on every touched footprint (catches whole-object re-serialization loss).
3. `score_placement` for placement applies; `run_drc` with unconnected items for routing applies.
4. Connectivity against the expected netlist.
5. File mode: format stamp unchanged.

A failure in 1–4 makes the outcome `partial` or `uncertain`, naming the first mismatch.

## Visibility, ordering, release gates
[I]
- Keep about 12 tools always visible (1–9, 11, 14, 17), named in the server instructions. Load propose and route tools as a toolset only when the client honours `list_changed`; otherwise expose all.
- Build the referee (7–9) before any placer; a placer never applies without beating the referee's score.
- Run tool-selection evals (expected and forbidden tools, call budgets) on this surface before release ([testing](mcp-server-testing-practices.md#practices-by-server)).

## Additions from the broader survey
- **Human-in-the-loop UX** (DeepPCB Cooper): read → summarize → propose → per-item accept/reject → each accepted change one undo entry [P] ([Cooper](https://deeppcb.ai/cooper-kicad-plugin/); [../landscape/deeppcb.md](../landscape/deeppcb.md)).
- **Interactive engine-grounded router** (KiCad push-and-shove via PCBWorld-Engine) as small candidate actions: engine engagement decides LLM clean-pass on PCBWorld [P] → [PCBWorld](../routing/pcbworld.md#llm-agents).
- **Distribution:** IPC-runtime KiCad plugin + MCP server through the PCM (zero AI plugins today) [P/I]; pair with Agent Skills playbooks, following Siemens Fuse and CELUS's MCP-plus-Skills pattern [I].

## Open questions
- Untested: plan head-to-head trials on a shared board corpus (tool only, tool + escape hatches, coding agent only).
- Until KiCad 11's headless `api-server` ships, live commit groups need a running GUI or a file-mode snapshot journal; PRO tracks headless IPC as preview-only.

## Sources
- [kicad_mcp_codebases.md § 6, Implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md); [existing_tools_and_apis.md § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md); [verification_kicad_and_tools.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [patents_and_industry.md § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
- Cross-vendor patterns: [../landscape/commercial-architecture-patterns.md](../landscape/commercial-architecture-patterns.md)
