<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Intent-driven objectives: how the commander tells kae what "better" means

**TL;DR**
- **kae's score sets its own priorities, badly.** Each harm becomes u = size / assumed bound (`observe.TOL`, `dc.LOSS_SHARE`, a 1 m cable on every connector pair), summed through φ(u) = u + 4(u−1)². On the boost board the cable term (u ≈ 18–23, ~2,000 points) swamped 3.5× the copper loss (37 → 128 mW), ~2× the heating and 3× the drop (~30 points together), so 0.2 mm power traces "won" [M]. Normalizing by a guessed bound *is* an exchange rate nobody chose.
- **Recommended interface: kae describes itself; the LLM declares intent against the description.** kae publishes a catalogue of *observables* (quantities, units, board scopes, bands, validity) and *knobs*. The commander writes a declarative intent (sections, environment, *terms* with physical limits and explicit exchange rates); kae reconciles toward it and returns a status in the intent's terms (Kubernetes-style spec → status, MCP-style self-describing schemas, structured results and elicitation).
- **Recommended objective:** lexicographic tiers (hard → limits → costs). Within the cost tier, a sum in one declared currency where every weight is an exchange rate written in the intent (for example "1 dB of margin at GNSS L1 = 20 mW"). Corners are aggregated per term. A limit the intent did not source is reported, never priced.
- **Intent is local.** Terms attach to sections (the brief's structures, which the LLM accepts, renames, merges or adds) and to *boundaries* between them ("buck cell → GNSS LNA input, L1 band"). One board holds a converter, a radio and DDR, each with its own priorities.
- **Biggest gap:** the reduced model stops at 300 MHz or the quasi-static limit (`wideband.F_TOP`, `THETA`), so GNSS, Wi-Fi and cellular bands are not computable; the status must say so, not extrapolate silently.

Tags: [P] primary source read, [S] secondary or search summary, [M] measured here, [I] our inference. Related: [intent-interchange](intent-interchange.md) (operating conditions as a SPICE testbench), [constraint-ir](constraint-ir.md) (geometric constraints, specificity), [physics-driven-design](physics-driven-design.md) (W × Z decomposition), [physics-frequency-coverage](physics-frequency-coverage.md) (the reduced model).

## Key facts

### 1. What goes wrong when the score sets the priorities

| Mechanism in code | Effect |
|---|---|
| `observe.observers` adds a `cm` observer for every connector pair; `harm.cm` compares against CISPR 32 class B for 1 m of cable at 150 Ω | One assumed environment term dominates every board that has two connectors [M] |
| `dc.LOSS_SHARE = 1 %`, `DROP_SHARE = 2 %`, `DT_MAX = 10 K`, `TOL[...]` | Each prior sets that quantity's price, because u = value / prior |
| `harm.phi` quadratic past u = 1; `pnr.PHI_SLOPE_CAP = 5` | the router caps the slope because "one observer whose bound is a crude prior would set every price" (pnr.py); the evaluator does not |
| `harm.robust` takes CVaR over the *sum* | the dominant term picks the corners for all |

Energy shows the scale: DC copper loss was 37 mW, against 5.5 mW for all switching-harmonic copper loss on the same board [M]. The physics is right. Only the priorities are wrong.

### 2. How LLM-facing systems expose themselves

| System | Mechanism worth copying | Source |
|---|---|---|
| MCP tools | self-describing `inputSchema`/`outputSchema`; `structuredContent` that "MUST" conform; errors as results (`isError`) the model can act on; `listChanged` discovery | [P] [MCP tools spec](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) |
| MCP resources and prompts | read-only context by URI; server-supplied prompt templates | [P] [MCP resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources) |
| MCP elicitation | the server asks for missing facts with a flat primitive schema; accept, decline or cancel | [P] [MCP elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation) |
| Anthropic tool guidance | meaningful names, not ids; `response_format` concise/detailed; errors with "specific and actionable improvements" | [P] [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) |
| Kubernetes | declarative `spec`, reconciled `status`, `observedGeneration` against stale reads | [S] [Gateway API status](https://gateway-api.sigs.k8s.io/docs/concepts/troubleshooting/) |
| CEL | side-effect-free expressions that terminate, cost estimable in advance | [S] [InfoQ on cel-expr-python](https://infoq.com/news/2026/03/google-cel-expr-python), [cel-spec](https://github.com/google/cel-spec) |
| EDA constraint managers | Allegro ECSets (one named set per net/bus/XNet); Altium priority; JITX specificity | [S] [Cadence blog](https://community.cadence.com/cadence_blogs_8/b/pcb/posts/using-constraint-sets-to-manage-design-constraints), [constraint-models-compared](constraint-models-compared.md) |

No EDA tool we found lets intent set an optimizer's objective: constraint managers carry limits, analysis setups carry conditions ([intent-interchange](intent-interchange.md) §1).

### 3. Multi-objective practice

| Formulation | Strength | Failure that matters here | Source |
|---|---|---|---|
| Weighted sum of normalized terms (today) | one differentiable number | weights hide in the normalization; misses non-convex Pareto points | [S] [Marler & Arora 2004](https://doi.org/10.1007/s00158-003-0368-6) |
| Lexicographic | "never trade safety for loss" | ignores small lower-tier trade-offs | Marler & Arora; [joint-loop](joint-loop.md) [M] |
| ε-constraint | others bounded in their own units | infeasible ε: no answer | [S] Haimes et al. 1971 |
| Goal programming | penalized deviation from targets | can return Pareto-dominated solutions | [S] Charnes & Cooper 1961 |
| Additive value, elicited trade-offs | weights are exchange rates in the attributes' own units | elicitation effort; rates valid locally | [S] Keeney & Raiffa (1976) |
| Pareto set, choice afterwards | no weights in advance | costly; someone still chooses | Marler & Arora |

## Recommendations for our system

### 4. The interface: catalogue, intent, status

kae runs as a deterministic server (MCP or CLI, same JSON):

| Call or resource | Purpose |
|---|---|
| `kae://board/<rev>/sections` | the brief's structures as named sections with members and evidence |
| `kae://catalog`, `describe(id)` | every observable and knob on this board: meaning, unit, scopes, bands, validity, cost, related knobs, written for a model |
| `evaluate(intent)` | the status (§7), no layout change |
| `route(intent)`, `place(intent)` | reconcile the layout toward the intent; return the status |
| `what_if(intent, knobs)` | first-order predicted term changes from current prices |

A **catalogue entry** names the observable with a template, so the LLM reads `loss.copper[net=+5V]`, not a uuid:

```json
{"id": "coupling.band", "unit": "dBm/Hz", "scope": ["from: section|part|net", "to: port"],
 "args": {"band_Hz": "[lo, hi]"}, "corners": true,
 "validity": "f <= 3.0e8 Hz on this board (quasi-static limit); above: not computable",
 "knobs": ["route.price_scale", "place.distance", "route.return_continuity"],
 "description": "Noise density the copper couples from the aggressors in `from` into port `to` (its reference impedance), over the harmonics in the band; layout share (routed minus ideal copper)."}
```

**Formulas.** Between "the LLM writes the whole objective as a formula" and "fixed families with knobs", recommend **fixed term families plus a small unit-checked expression AST for derived observables**. A free-form objective loses per-term attribution and the router's per-term prices; families alone cannot say "efficiency of the 5 V path". So derived observables are named expressions and the objective is always a sum of terms:

```json
{"derive": {"eff.buck5": {"op": "/", "args": ["power.out[section=buck5]",
            {"op": "+", "args": ["power.out[section=buck5]", "loss.total[section=buck5]"]}]}}}
```

Operators: `+ − × /`, `min`, `max`, `abs`, `db`, `sum_over`, `max_over`; no loops or user functions (CEL-like: terminates, differentiable almost everywhere, units checked at load). A unit error returns `isError` with the fix ("`loss.total` is W; `0.9` needs a unit").

### 5. The intent document

The top-level keys are `schema`, `generation`, `currency`, `defaults`, `environment`, `sections`, `derive`, `terms`, `knobs` and `facts`. `facts` is today's `load_intent` content (part, net and cell parameter overrides), which stays as it is.

```json
{
 "schema": "kae.intent/1", "generation": 7, "currency": "mW_eq", "defaults": "neutral/1",
 "environment": {
   "enclosure": {"kind": "none|plastic|metal_sealed", "why": "handheld, ABS case"},
   "cables": [{"connector": "J1", "length_m": 1.5, "shield": "none"}],
   "receivers": [{"name": "gnss", "port": "U7.RF_IN", "bands_Hz": [[1.559e9, 1.610e9]]}],
   "mounting": [{"kind": "heatsink", "side": "B", "region": "under:U3", "T_C": 60}],
   "ambient_C": [0, 50]},
 "sections": {
   "accept": "all",
   "rename": {"cell:U3": "buck5"},
   "add": [{"id": "gnss_fe", "parts": ["U7", "L4", "C30"], "nets": ["RF_IN"]}]},
 "terms": [
   {"id": "T1", "tier": "hard", "obs": "temp.junction[part=*]", "agg": "worst", "max": "rating",
    "why": "datasheet ratings"},
   {"id": "T2", "tier": "limit", "obs": "drop.rail[load=U5,rail=+1V8]", "agg": "worst", "max": "27 mV",
    "source": "U5 datasheet 1.5 % of 1.8 V", "rate": "2 mW_eq/mV"},
   {"id": "T3", "tier": "cost", "obs": "loss.total[section=buck5]", "agg": "cvar20", "rate": "1 mW_eq/mW",
    "why": "battery life"},
   {"id": "T4", "tier": "limit", "obs": "coupling.band[from=buck5,to=gnss_fe.port,band=gnss]",
    "agg": "worst", "max": "-180 dBm/Hz", "rate": "20 mW_eq/dB", "why": "<= 1 dB noise rise at L1"},
   {"id": "T5", "tier": "ignore", "obs": "emission.cable_cm[*]", "why": "no cable leaves the case"}],
 "knobs": {"route.width.max_mm[net=+5V]": 1.0, "route.via_array[region=under:U3]": "allow"}
}
```

Rules:
- **Every term needs a `why`.** A limit needs a `source`, or it is marked `assumed`. An assumed limit is reported against but not priced unless the intent gives it a `rate`.
- **Specificity:** a part-scoped term beats a section-scoped one, which beats a board-scoped one, as in [constraint-ir](constraint-ir.md). Ties are errors, returned with both term ids.
- **Exchange rates are explicit and local.** "20 mW_eq/dB" means paying 20 mW of loss for 1 dB of GNSS margin is acceptable. kae checks only units and sign. Lacking a rate, the LLM can read each term's marginal cost along the knobs from `evaluate` and answer pairwise ("is 1 dB worth more than 20 mW?"), Keeney–Raiffa style [I].

**Defaults when silent (`neutral/1`), each emitted as a synthetic term with id `D*`, so it shows up in the status like any other term:**

| Quantity | Default | Why |
|---|---|---|
| connectivity, DRC, clearances, creepage | hard | legality, not preference |
| part ratings with a source (V_max of a switch, T_j max) | hard, worst corner | a rating is a fact |
| total copper dissipation | cost, 1 mW_eq/mW, CVaR20 | energy is absolute: it needs no guessed bound |
| drop, heating, supply noise, victim pickup | reported, unpriced, against the old priors labelled `reference` | the user rejected assumed bounds as prices |
| cable common mode | reported as a layout-only *transfer* quantity (nH of shared path per connector pair, V/A), with no CISPR verdict | no cable is assumed; it is priced only when `environment.cables` declares one |
| radiated loop emission | reported in dBµV/m at 10 m next to CISPR 32 B, unpriced | an enclosure is unknown |
| unknown environment items that would flip a verdict | listed in `questions` | elicitation, below |

One default cost gives every board a neutral optimum: no needless loss, no broken ratings; everything else waits for intent.

### 6. Objective formulation

```
minimize lexicographically   ( H_hard,  H_limit,  C )
  H_hard  = Σ hard terms' violation, in each term's own unit (normalized only to sort, never traded)
  H_limit = Σ_t rate_t · max(0, agg_t(x_t) − max_t)      limit tiers: hinge in physical units × rate
  C       = Σ_cost-terms rate_t · agg_t(x_t)  +  Σ_limit-terms-with-target rate_t · max(0, agg_t(x_t) − target_t)
```

- **Why tiers with rates:** a hard term (a switch's rating) must never be bought; within limits and costs, trading is the job. Limits have ε-constraint semantics: once met they cost nothing unless they carry a `target`. The cost tier still minimizes every priced quantity, which avoids goal programming's dominated solutions.
- **Corners per term.** `agg` is `worst` (hard terms, limits from ratings), `cvar20` (costs) or `typ`. Each term picks its own corners, so the worst ripple corner and the worst loss corner may be different operating points. That is pessimistic but traceable. A `joint` option keeps today's CVaR over the sum for terms the intent groups.
- **Traceability.** Every contribution to H or C is a row: (term id, observable instance, corner set, value, unit, rate, contribution) plus the dominant cause, such as an (aggressor, observer) pair, a harmonic, a track or a ledger parameter. The objective is reproduced from the rows exactly.
- **Failure modes.** Rates from nothing reproduce today's bug, so the status shows each term's share of C and flags any term above 80 % whose rate is marked `guess`. Per-dB rates pay steeply near zero coupling, so dB terms clip at the model's noise floor. An infeasible limit tier is reported with its binding terms while the router minimizes H_limit.

### 7. The status: what the LLM reads

```json
{"observedGeneration": 7, "complete": true, "tiers": {"hard": 0, "limit": 41.0, "cost": 212.4},
 "terms": [
  {"id": "T4", "value": "-171.2 dBm/Hz", "limit": "-180 dBm/Hz", "met": false, "margin": "-8.8 dB",
   "contribution": 176.0, "share": 0.46, "dominant": "buck5 SW harmonic 1575.0 MHz via L4-C30 loop",
   "validity": "out_of_model: 1.575e9 Hz > f_max 3.0e8 Hz; value extrapolated from the trapezoid envelope",
   "rests_on": ["prior cell:U3 t_i_s [1e-9, 2e-8]"],
   "buys": [{"knob": "place.distance[buck5,gnss_fe]", "per": "+5 mm", "delta": "-3.1 dB", "how": "first-order"}]}],
 "questions": [{"id": "Q1", "ask": "Is a cable attached to J2 in use?",
   "schema": {"type": "boolean"}, "flips": ["T6"]}]}
```

- **Concise by default** (tiers, unmet terms, top three by share, questions); `detailed` adds every row.
- **`buys`** is d(term)/d(knob) × step from the router's prices, labelled first-order; `evaluate` verifies.
- **`rests_on`** lists the ledger priors (`Ledger.flagged`) and defaults behind a value; a prior whose range flips `met` becomes a **question** with an elicitation-style flat schema, answered by editing `facts`/`environment` and bumping `generation`.

### 8. Locality: sections and boundaries

- **Seeds come from the brief** (`kae/src/kae/circuit/brief.py`: commutation cells, power paths, antennas, crystals, oscillators, decaps, rail groups, victims, chains, heat sources, thermal victims, with members and evidence) and from schematic sheet names.
- **The LLM `accept`s, `rename`s, `merge`s and `add`s** sections by parts, nets or a region; unresolved members come back as errors.
- **A boundary** (`from=A, to=B`) is a first-class scope: the transfer from A's aggressor ports to B's observer ports, the (observer, aggressor) pair kae already computes (`harm.pair_u`, `wideband` `U[(o, s)]`). "Isolate the switcher from the LNA" is one term, not a millimetre rule.
- **One board, many priorities:**

| Section (example) | Terms the LLM would write | kae today |
|---|---|---|
| buck / boost cell | `loss.total` cost; `overshoot[switch]` hard vs V_ds rating; `ripple.rail[band=f_sw..10 f_sw]` limit | loss, overshoot, supply peak: yes |
| GNSS front end | `coupling.band[from=*,to=LNA,band=L1]` limit in dBm/Hz | **no** (>300 MHz) |
| radio PA supply | `ripple.rail[rail=VPA,band=…]` limit from the PA's spur spec | per-harmonic ripple in `spectrum.totals`; band selection missing |
| DDR | impedance, skew, crosstalk limits | **no** SI in `kae.excite`; [constraint-ir](constraint-ir.md) constraints |
| power stage on a heatsink | `temp.junction` hard; `theta[part→mounting]` cost | junction T yes; heatsink boundary no (`heat.py` has face convection only) |
| precision ADC | `pickup[victim=ADC_IN,band=0..f_s/2]` in µV from the LSB | peak pickup yes; band and RMS missing |
| sealed metal box | `emission.*` ignore | — |
| automotive | `emission.cable_cm[connector=J1,band=CISPR25 …]` per harness | CISPR 32 line only; CISPR 25 is licensed text [S] |

Limit sources for those lines:
- **GNSS:** kT = −174 dBm/Hz, so a 1 dB noise rise needs interference near −180 dBm/Hz [I]; L1 arrives near −128 dBm under a −111 dBm in-band noise floor [S] (u-blox integration manuals).
- **Emissions:** FCC Part 15 class B at 3 m, 100 / 150 / 200 / 500 µV/m [P] ([47 CFR 15.109](https://www.govinfo.gov/content/pkg/CFR-2010-title47-vol1/pdf/CFR-2010-title47-vol1-sec15-109.pdf)); CISPR 32 class B 30 / 37 dBµV/m at 10 m (`spectrum.cispr_b`).
- **Copper and heat:** IPC-2221/2152 ([high-current](../rules/power/high-current.md)); via arrays at 1.0–1.2 mm pitch ([thermal](../rules/thermal.md)).
- **Switcher spurs** penetrate planes; distance, filters and ferrites are the remedies [P] ([TI SLVAF16A](https://ti.com/document-viewer/lit/html/SLVAF16A/GUID-A58B5D95-DA4C-4AF1-B04F-78255512C2E2)). **PA ripple:** no vendor number found; spurs sit at the ripple frequency and track its amplitude [S] ([US 7132891](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7132891)), so the limit comes from the PA datasheet via `facts`.

### 9. How the router consumes intent

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
4. **Status report** (§7), with `buys` from pnr prices and questions from `Ledger.flagged` plus environment unknowns.
5. **`pnr.py`:** `_weights` and `_dc_per_ohm` take ∂C/∂x from the objective; band-selective spectral weights; knob clamps; incremental re-route on a generation change.
6. **Server surface:** `describe`, `evaluate`, `route`, `what_if` over [mcp-tool-surface-spec](../kicad/mcp-tool-surface-spec.md).

**Acceptance tests:**
- **Ranking flips with intent:** the boost board's human and 0.2 mm router layouts under intent A (plastic case, no cables, loss cost) and B (1.5 m unshielded cables on J1, J2 with a CISPR 32 B rate). A must prefer the human layout; B may prefer the router's; both name the dominant term.
- **No intent → `neutral/1`;** copper loss decides.
- **Traceability:** rows sum to the objective; each cites a term id. **Incremental:** one rate change re-routes only nets whose price moved.
- **`score.py` and cp1/cpk untouched;** this is kae's internal objective.

## Conflicts and open questions

- **Currency.** Is mW_eq a good universal currency? Alternatives: a dimensionless one, or a different currency per board.
- **Rates.** Should rates always come from the LLM, or should kae propose them from pairwise answers?
- **Corners.** Per-term corners (recommended) are pessimistic for terms that share an operating point. Should `joint` be the default instead?
- **Above 300 MHz.** GNSS, Wi-Fi and cellular need full-wave slices or a calibrated envelope model. Until then they are `out_of_model`. Is an extrapolated, flagged value useful, or misleading?
- **Benchmark fairness.** Methods routing under an intent file must all get the same file ([intent-interchange](intent-interchange.md)).
- **Thin evidence.** CISPR 25 limits (licensed text; [S] third-party table, [emcweb](https://emcweb.pages.dev/limits/cispr25-re)), PA ripple numbers, and a primary u-blox statement on DC/DC desense were not obtained.

## Sources

- In-repo [M]: boost-board evaluation on branch `physics-functional-eval`; `kae/src/kae/excite/`, `kae/src/kae/em/pnr.py`, `kae/src/kae/circuit/brief.py`.
- Primary and secondary URLs are inline above. Books and papers: Marler & Arora 2004; Haimes, Lasdon & Wismer 1971; Charnes & Cooper 1961; Keeney & Raiffa 1976.

See also: [functional-evaluation](../physics/functional-evaluation.md), [fields-emi-budget](../physics/fields-emi-budget.md), [rf](../rules/rf.md), [thermal](../rules/thermal.md), [decoupling-pdn](../rules/decoupling-pdn.md), [design-rationale-and-intent-record](../ux/design-rationale-and-intent-record.md).
