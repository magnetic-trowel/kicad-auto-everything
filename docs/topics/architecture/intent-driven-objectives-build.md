<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Intent-driven objectives: router changes, build order and acceptance tests

Scope: how kae builds intent-driven objectives: router changes, build order and acceptance tests. Not here: the catalogue, the intent document, the tiered objective and the status -> [intent-driven-objectives](intent-driven-objectives.md).
Keys: intent router, W × Z prices, incremental re-route, `buys`, band-selective weights, lexicographic hard tier, copper policy, intent build order

**Results**
- Intent changes only the weights W of the router's W × Z prices; field solves are reused, so a new intent generation re-routes only nets whose price moved.
- Built: the intent package, observations with references, the tiered objective and the router's copper policy with its lexicographic hard tier; not built: `buys`, band-selective weights, incremental re-route, the server surface.

Tags: [M] measured here, [I] our inference.

## How the router consumes intent

`pnr.PhysRouter` already separates the field solve (`solve_fields`, cached by `_sig`) from the weights (`_weights`). The prices are W × Z ([physics-driven-design](physics-driven-design.md) §2). Intent changes only W:

| Requirement | With intent (before: `phi_prime(u)` capped at 5, harm/Ω widths) |
|---|---|
| any term | ∂C/∂x_t = `rate_t` (cost) or `rate_t·[x_t > max_t]` (limit); hard terms: [objective](intent-driven-objectives.md#objective-formulation) |
| loss, drop | closed-form widths in mW_eq/Ω (`kae.intent.route`); `knobs.route.width.*` clamp the ladder |
| heating | IPC-2221 floor from the intent's limit, or none if heating is a cost |
| band coupling | spectral weights only from harmonics inside each term's band, times the rate |
| cable CM | declared cables only |
| thermal to heatsink | new knob `route.via_array[region]`, priced by ∂θ/∂via (`kae.em.thermal`) |
| return continuity, decap priority | `_cut_costs` and the placer, weighted by the terms' rates |

Before intent: `phi_prime(u)` per (observer, aggressor) pair capped at `PHI_SLOPE_CAP` = 5; `_dc_per_ohm` (harm/Ω) → `_dc_width` ladder; an IPC-2221 floor at `dcp.dT_max`; one 10 MHz band, or `--spectral` weights from all harmonics; cable CM unpriced (`UNPRICED = ("cm",)`).

**Incremental follow:** a new generation recomputes `_weights` without new solves and re-routes nets whose price moved over 20 %, largest change first; `_route_verified` still guards each candidate.

## Code changes, in order

**Built** (`kae/src/kae/intent/`, `python -m kae.intent catalog|evaluate`, `kae.em.pnr --intent`; measured in [field-solver-routing-and-intent](../../research/physics/field-solver-routing-and-intent.md)): schema, units, specificity, `neutral/1` and `legacy/u`, errors as fixes; observations with references instead of u; tiers, per-term corners and contribution rows; the router's closed-form copper policy, intent-scoped pair prices and lexicographic hard tier. **Not built:** derived-observable AST, `buys`, band-selective spectral weights, knob-driven incremental re-route, the MCP surface ([mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md)).

**Acceptance tests:**
- **Ranking flips with intent:** the boost board's human and 0.2 mm router layouts under intent A (plastic case, no cables, loss cost) and B (1.5 m unshielded cables on J1, J2 with a CISPR 32 B rate). A must prefer the human layout; B may prefer the router's; both name the dominant term.
- **No intent → `neutral/1`;** copper loss decides.
- **Traceability:** rows sum to the objective; each cites a term id. **Incremental:** one rate change re-routes only nets whose price moved.
- **`score.py` and cp1/cpk untouched;** this is kae's internal objective.

## Conflicts and open questions

See [intent-driven-objectives § Conflicts and open questions](intent-driven-objectives.md#open-questions).

## Sources

- In-repo: `kae/src/kae/em/pnr.py` (`PhysRouter`, `solve_fields`, `_weights`, `_dc_per_ohm`, `_dc_width`, `_cut_costs`, `_route_verified`, `PHI_SLOPE_CAP`, `UNPRICED`), `kae/src/kae/intent/route.py`, `kae/src/kae/excite/`.

See also: [intent-driven-objectives](intent-driven-objectives.md), [physics-driven-design](physics-driven-design.md), [mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md).
