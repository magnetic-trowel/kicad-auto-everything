<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Intent-driven objectives: router changes, build order and acceptance tests

**TL;DR**
- Split from [intent-driven-objectives](intent-driven-objectives.md), which defines the catalogue, the intent document, the tiered objective and the status. This doc is how kae would build it.
- Intent changes only the weights W of the router's W × Z prices; field solves are reused, so a new intent generation re-routes only nets whose price moved.
- Build order: `kae/src/kae/intent/`, observations instead of u, `excite/objective.py`, the status, `pnr.py`, the server surface; a `legacy/u` profile is the regression gate.

Tags: [M] measured here, [I] our inference.

## How the router consumes intent

`pnr.PhysRouter` already separates the field solve (`solve_fields`, cached by `_sig`) from the weights (`_weights`). The prices are W × Z ([physics-driven-design](physics-driven-design.md) §2). Intent changes only W:

| Requirement | Today | With intent |
|---|---|---|
| any term | `phi_prime(u)` per (observer, aggressor) pair, capped at 5 | ∂C/∂x_t = `rate_t` (cost) or `rate_t·[x_t > max_t]` plus a hinge-smoothing barrier (limit); `PHI_SLOPE_CAP` deleted |
| loss, drop | `_dc_per_ohm` (harm/Ω) → `_dc_width` ladder | same code in mW_eq/Ω; `knobs.route.width.*` clamp the ladder |
| heating | IPC-2221 floor at `dcp.dT_max` | floor from the intent's limit, or none if heating is a cost |
| band coupling | one 10 MHz band, or `--spectral` weights from all harmonics | spectral weights only from harmonics inside each term's band, times the rate |
| cable CM | `UNPRICED = ("cm",)` | declared cables only, after the pending coupling check |
| thermal to heatsink | none | new knob `route.via_array[region]`, priced by ∂θ/∂via (`kae.em.thermal`) |
| return continuity, decap priority | `_cut_costs`; placer | same code, weighted by the terms' rates |

**Incremental follow.** A new generation recomputes `_weights` without new field solves; nets whose weighted price moved by more than a threshold (start at 20 %) are re-routed, largest change first, and `_route_verified` still guards each candidate.

## Code changes, in order

1. **`kae/src/kae/intent/` (new):** schema, units, AST, specificity, `neutral/1`, errors as fixes. Tests: unit mismatch and tied specificity rejected with messages; deterministic compile.
2. **Observations instead of u:** `observe.py`, `dc.py`, `heat.py`, `wideband.py`, `capacitive.py` emit `Observation(id, scope, unit, per-corner values, band, basis, rests_on)`. `TOL`, `LOSS_SHARE`, `DROP_SHARE`, `DT_MAX` become `reference` values; cable `cm` only for declared cables.
3. **`kae/src/kae/excite/objective.py`:** tiers, per-term aggregation, contribution rows, replacing the sums in `evaluate.py`, `wideband.py`, `heat.py`. A `legacy/u` profile reproduces today's totals as a regression gate.
4. **Status report** ([intent-driven-objectives](intent-driven-objectives.md) §7), with `buys` from pnr prices and questions from `Ledger.flagged` plus environment unknowns.
5. **`pnr.py`:** `_weights` and `_dc_per_ohm` take ∂C/∂x from the objective; band-selective spectral weights; knob clamps; incremental re-route on a generation change.
6. **Server surface:** `describe`, `evaluate`, `route`, `what_if` over [mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md).

**Acceptance tests:**
- **Ranking flips with intent:** the boost board's human and 0.2 mm router layouts under intent A (plastic case, no cables, loss cost) and B (1.5 m unshielded cables on J1, J2 with a CISPR 32 B rate). A must prefer the human layout; B may prefer the router's; both name the dominant term.
- **No intent → `neutral/1`;** copper loss decides.
- **Traceability:** rows sum to the objective; each cites a term id. **Incremental:** one rate change re-routes only nets whose price moved.
- **`score.py` and cp1/cpk untouched;** this is kae's internal objective.

## Conflicts and open questions

See [intent-driven-objectives § Conflicts and open questions](intent-driven-objectives.md#conflicts-and-open-questions).

## Sources

- In-repo: `kae/src/kae/em/pnr.py` (`PhysRouter`, `solve_fields`, `_weights`, `_dc_per_ohm`, `_dc_width`, `_cut_costs`, `_route_verified`, `PHI_SLOPE_CAP`, `UNPRICED`), `kae/src/kae/excite/`.

See also: [intent-driven-objectives](intent-driven-objectives.md), [physics-driven-design](physics-driven-design.md), [mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md).
