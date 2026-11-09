<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Intent-driven objectives: how the commander tells kae what "better" means

Scope: design of kae's internal objective, set by the commander's declared intent. Not here: router changes, build status and acceptance tests -> [intent-driven-objectives-build](intent-driven-objectives-build.md); operating conditions as a SPICE testbench -> [intent-interchange](intent-interchange.md); geometric constraints and specificity -> [constraint-ir](constraint-ir.md); W × Z decomposition -> [physics-driven-design](physics-driven-design.md); reduced-model frequency range -> [physics-frequency-coverage](physics-frequency-coverage.md).
Keys: intent, objective, exchange rate, mW_eq, lexicographic tiers, ε-constraint, CVaR20, catalogue, observable, knob, what_if, status, elicitation, neutral/1, sections, boundaries, kae.intent/1, phi(u), PHI_SLOPE_CAP, MCP, CEL, out_of_model

Tags: [P] primary source read, [S] secondary or search summary, [M] measured here, [I] our inference.

## Failure of score-set priorities

Today each harm is u = size / assumed bound (`observe.TOL`, `dc.LOSS_SHARE`, a 1 m cable on every connector pair), summed through φ(u) = u + 4(u−1)². Normalizing by a guessed bound *is* an exchange rate nobody chose.

Boost board [M]: an assumed cable term swamped 3.5× the copper loss, so 0.2 mm power traces "won"; numbers in [field-solver-routing-and-intent](../../research/physics/field-solver-routing-and-intent.md#what-did-not-work). The physics is right, only the priorities are wrong.

| Mechanism in code | Effect |
|---|---|
| `observe.observers` adds a `cm` observer for every connector pair; `harm.cm` compares against CISPR 32 class B for 1 m of cable at 150 Ω | one assumed environment term dominates every board with two connectors [M] |
| `dc.LOSS_SHARE = 1 %`, `DROP_SHARE = 2 %`, `DT_MAX = 10 K`, `TOL[...]` | each prior sets that quantity's price, because u = value / prior |
| `harm.phi` quadratic past u = 1; `pnr.PHI_SLOPE_CAP = 5` | the router caps the slope because "one observer whose bound is a crude prior would set every price" (pnr.py); the evaluator does not |
| `harm.robust` takes CVaR over the *sum* | the dominant term picks the corners for all |

## Prior art: self-describing LLM-facing systems

| System | Mechanism worth copying | Source |
|---|---|---|
| MCP tools | self-describing `inputSchema`/`outputSchema`; `structuredContent` that "MUST" conform; errors as results (`isError`) the model can act on; `listChanged` discovery | [P] [MCP tools spec](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) |
| MCP resources and prompts | read-only context by URI; server-supplied prompt templates | [P] [MCP resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources) |
| MCP elicitation | server asks for missing facts with a flat primitive schema; accept, decline or cancel | [P] [MCP elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation) |
| Anthropic tool guidance | meaningful names, not ids; `response_format` concise/detailed; errors with "specific and actionable improvements" | [P] [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) |
| Kubernetes | declarative `spec`, reconciled `status`, `observedGeneration` against stale reads | [S] [Gateway API status](https://gateway-api.sigs.k8s.io/docs/concepts/troubleshooting/) |
| CEL | side-effect-free expressions that terminate, cost estimable in advance | [S] [InfoQ on cel-expr-python](https://infoq.com/news/2026/03/google-cel-expr-python), [cel-spec](https://github.com/google/cel-spec) |
| EDA constraint managers | Allegro ECSets (one named set per net/bus/XNet); Altium priority; JITX specificity | [S] [Cadence blog](https://community.cadence.com/cadence_blogs_8/b/pcb/posts/using-constraint-sets-to-manage-design-constraints), [constraint-models-compared](constraint-models-compared.md) |

No EDA tool found lets intent set an optimizer's objective: constraint managers carry limits, analysis setups carry conditions ([intent-interchange](intent-interchange.md#where-intent-lives-in-industry)).

## Multi-objective formulations

| Formulation | Strength | Failure that matters here | Source |
|---|---|---|---|
| Weighted sum of normalized terms (today) | one differentiable number | weights hide in the normalization; misses non-convex Pareto points | [S] [Marler & Arora 2004](https://doi.org/10.1007/s00158-003-0368-6) |
| Lexicographic | "never trade safety for loss" | ignores small lower-tier trade-offs | Marler & Arora; [joint-loop](joint-loop.md) [M] |
| ε-constraint | others bounded in their own units | infeasible ε: no answer | [S] Haimes et al. 1971 |
| Goal programming | penalized deviation from targets | can return Pareto-dominated solutions | [S] Charnes & Cooper 1961 |
| Additive value, elicited trade-offs | weights are exchange rates in the attributes' own units | elicitation effort; rates valid locally | [S] Keeney & Raiffa (1976) |
| Pareto set, choice afterwards | no weights in advance | costly; someone still chooses | Marler & Arora |

## Interface: catalogue, intent, status

Design [I]: kae describes itself; the LLM declares intent against the description; kae reconciles toward it and returns a status in the intent's terms. kae runs as a deterministic server (MCP or CLI, same JSON):

| Call or resource | Purpose |
|---|---|
| `kae://board/<rev>/sections` | the brief's structures as named sections with members and evidence |
| `kae://catalog`, `describe(id)` | every observable and knob on this board: meaning, unit, scopes, bands, validity, cost, related knobs, written for a model |
| `evaluate(intent)` | the [status](#status-what-the-llm-reads), no layout change |
| `route(intent)`, `place(intent)` | reconcile the layout toward the intent; return the status |
| `what_if(intent, knobs)` | first-order predicted term changes from current prices |

A catalogue entry names the observable with a template, so the LLM reads `loss.copper[net=+5V]`, not a uuid:

```json
{"id": "coupling.band", "unit": "dBm/Hz", "scope": ["from: section|part|net", "to: port"],
 "args": {"band_Hz": "[lo, hi]"}, "corners": true,
 "validity": "f <= 3.0e8 Hz on this board (quasi-static limit); above: not computable",
 "knobs": ["route.price_scale", "place.distance", "route.return_continuity"],
 "description": "Noise density the copper couples from the aggressors in `from` into port `to` (its reference impedance), over the harmonics in the band; layout share (routed minus ideal copper)."}
```

Formulas: fixed term families + a small unit-checked expression AST for derived observables [I]. A free-form objective loses per-term attribution and the router's per-term prices; families alone cannot say "efficiency of the 5 V path". The objective stays a sum of terms:

```json
{"derive": {"eff.buck5": {"op": "/", "args": ["power.out[section=buck5]",
            {"op": "+", "args": ["power.out[section=buck5]", "loss.total[section=buck5]"]}]}}}
```

Operators: `+ − × /`, `min`, `max`, `abs`, `db`, `sum_over`, `max_over`; no loops or user functions (CEL-like: terminates, differentiable almost everywhere, units checked at load). A unit error returns `isError` with the fix ("`loss.total` is W; `0.9` needs a unit").

## Intent document

Top-level keys: `schema`, `generation`, `currency`, `defaults`, `environment`, `sections`, `derive`, `terms`, `knobs`, `facts`. `facts` = today's `load_intent` content (part, net and cell parameter overrides), unchanged.

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
- Every term says why (`why` or `source`). A bound without a `source` is priced as written but marked `assumed` in its row and in `assumed_limits`. A `limit` needs a `rate`; an unpriced bound is a `report` term (`load` rejects a rate-less limit rather than downgrade it). A `hard` term takes no rate.
- Temperatures: °C is absolute for `temp.junction`, a rise for `heat.track` (IPC-2221's wording); K is a rise only, rejected against an absolute temperature.
- Specificity: part-scoped term > section-scoped > board-scoped, as in [constraint-ir](constraint-ir.md#eight-design-rules). Ties are errors, returned with both term ids. Terms compete only within one tier and bound side, so a `min` and a `max` term make a window (`objective.resolve` lists which `where` keys are part or section scope).
- Exchange rates are explicit and local: "20 mW_eq/dB" = paying 20 mW of loss for 1 dB of GNSS margin is acceptable. kae checks only units and sign. Lacking a rate, the LLM reads each term's marginal cost along the knobs from `evaluate` and answers pairwise ("is 1 dB worth more than 20 mW?"), Keeney–Raiffa style [I].

Defaults when silent (`neutral/1`), each emitted as a synthetic term with id `D*` so it shows in the status like any other term:

| Quantity | Default | Why |
|---|---|---|
| connectivity, DRC, clearances, creepage | hard | legality, not preference |
| part ratings with a source (V_max of a switch, T_j max) | hard, worst corner | a rating is a fact |
| total copper dissipation | cost, 1 mW_eq/mW, CVaR20 | energy is absolute: no guessed bound; this one cost gives every board a neutral optimum (no needless loss, no broken ratings) |
| copper area (router widths only) | `knobs.route.area_cost` 0.2 mW_eq/mm², reported as defaulted | bounds w* = √(k_R ρ / (t a)); between the always-on economic value (0.05–0.12) and human layouts (≈ 0.6); chosen by A/B (0.2 completed most, same physics): basis and A/B in [field-solver-routing-and-intent](../../research/physics/field-solver-routing-and-intent.md) |
| drop, heating, supply noise, victim pickup | reported, unpriced, against the old priors labelled `reference` | the user rejected assumed bounds as prices |
| cable common mode | reported as a layout-only *transfer* quantity (nH of shared path per connector pair, V/A), no CISPR verdict | no cable is assumed; priced only when `environment.cables` declares one |
| radiated loop emission | reported in dBµV/m at 10 m next to CISPR 32 B, unpriced | enclosure unknown |
| unknown environment items that would flip a verdict | listed in `questions` | elicitation |

## Objective formulation

```
minimize lexicographically   ( H_hard,  H_limit,  C )
  H_hard  = Σ hard terms' violation, in each term's own unit (normalized only to sort, never traded)
  H_limit = Σ_t rate_t · max(0, agg_t(x_t) − max_t)      limit tiers: hinge in physical units × rate
  C       = Σ_cost-terms rate_t · agg_t(x_t)  +  Σ_limit-terms-with-target rate_t · max(0, agg_t(x_t) − target_t)
```

- Tiers with rates: a hard term (a switch's rating) is never bought; within limits and costs, trading is the job. Limits have ε-constraint semantics: once met they cost nothing unless they carry a `target`. The cost tier still minimizes every priced quantity, avoiding goal programming's dominated solutions. The router keeps the tier: it picks candidate routes by (hard violation, cost), as `objective.key` ranks layouts; a violated hard term only steers the path search (`route.Policy.HARD_SLOPE`, an exact-penalty slope [Nocedal & Wright, *Numerical Optimization*, §17.2]). In the output, a violated hard term is a `block` hazard, one the router cannot compute (e.g. `temp.junction`) a `warn`.
- Corners per term: `agg` ∈ {`worst` (hard terms, limits from ratings), `cvar20` (costs), `typ`}. Each term picks its own corners, so the worst ripple corner and the worst loss corner may be different operating points: pessimistic but traceable. A `joint` option keeps today's CVaR over the sum for terms the intent groups.
- Traceability: every contribution to H or C is a row (term id, observable instance, corner set, value, unit, rate, contribution) plus the dominant cause (an (aggressor, observer) pair, a harmonic, a track or a ledger parameter); the objective is reproduced from the rows exactly.
- Failure modes: rates from nothing reproduce today's bug, so the status shows each term's share of C and flags any term above 80 % whose rate is marked `guess`. Per-dB rates pay steeply near zero coupling, so dB terms clip at the model's noise floor. An infeasible limit tier is reported with its binding terms while the router minimizes H_limit.

## Status: what the LLM reads

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

- Concise by default (tiers, unmet terms, top three by share, questions); `detailed` adds every row.
- `buys` = d(term)/d(knob) × step from the router's prices, labelled first-order; `evaluate` verifies.
- `rests_on` lists the ledger priors (`Ledger.flagged`) and defaults behind a value; a prior whose range flips `met` becomes a question with an elicitation-style flat schema, answered by editing `facts`/`environment` and bumping `generation`.
- Validity: the reduced model stops at 300 MHz or the quasi-static limit (`wideband.F_TOP`, `THETA`), so GNSS, Wi-Fi and cellular bands are not computable; the status says so (`out_of_model`) instead of extrapolating silently.

## Locality: sections and boundaries

Intent is local: one board holds a converter, a radio and DDR, each with its own priorities.
- Section seeds: the brief (`kae/src/kae/circuit/brief.py`: commutation cells, power paths, antennas, crystals, oscillators, decaps, rail groups, victims, chains, heat sources, thermal victims, with members and evidence) and schematic sheet names.
- The LLM `accept`s, `rename`s, `merge`s and `add`s sections by parts, nets or a region; unresolved members come back as errors.
- A boundary (`from=A, to=B`, e.g. "buck cell → GNSS LNA input, L1 band") is a first-class scope: the transfer from A's aggressor ports to B's observer ports, the (observer, aggressor) pair kae already computes (`harm.pair_u`, `wideband` `U[(o, s)]`). "Isolate the switcher from the LNA" is one term, not a millimetre rule.

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

Limit sources:
- GNSS: kT = −174 dBm/Hz, so a 1 dB noise rise needs interference near −180 dBm/Hz [I]; L1 arrives near −128 dBm under a −111 dBm in-band noise floor [S] (u-blox integration manuals).
- Emissions: FCC Part 15 class B at 3 m, 100 / 150 / 200 / 500 µV/m [P] ([47 CFR 15.109](https://www.govinfo.gov/content/pkg/CFR-2010-title47-vol1/pdf/CFR-2010-title47-vol1-sec15-109.pdf)); CISPR 32 class B 30 / 37 dBµV/m at 10 m (`spectrum.cispr_b`).
- Copper and heat: IPC-2221/2152 ([high-current](../rules/power/high-current.md)); via arrays at 1.0–1.2 mm pitch ([thermal](../rules/thermal.md)).
- Switcher spurs penetrate planes; distance, filters and ferrites are the remedies [P] ([TI SLVAF16A](https://ti.com/document-viewer/lit/html/SLVAF16A/GUID-A58B5D95-DA4C-4AF1-B04F-78255512C2E2)).
- PA ripple: no vendor number found; spurs sit at the ripple frequency and track its amplitude [S] ([US 7132891](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7132891)), so the limit comes from the PA datasheet via `facts`.

## How the router consumes intent, build order, acceptance tests

Intent changes only W in the router's W × Z prices, and hard terms stay a lexicographic tier ([objective](#objective-formulation)); a new generation re-routes only nets whose price moved. The router table, what is built and what is not, and the acceptance tests (ranking flips on the boost board under two intents, `neutral/1`, traceable rows, `score.py` untouched) are in [intent-driven-objectives-build](intent-driven-objectives-build.md).

## Open questions

- Currency: is mW_eq a good universal currency? Alternatives: dimensionless, or a different currency per board.
- Rates: always from the LLM, or proposed by kae from pairwise answers?
- Corners: per-term corners (recommended) are pessimistic for terms that share an operating point. Should `joint` be the default?
- Above 300 MHz: GNSS, Wi-Fi and cellular need full-wave slices or a calibrated envelope model; until then `out_of_model`. Is an extrapolated, flagged value useful or misleading?
- Benchmark fairness: methods routing under an intent file must all get the same file ([intent-interchange](intent-interchange.md#open-questions)).
- Thin evidence: CISPR 25 limits (licensed text; [S] third-party table, [emcweb](https://emcweb.pages.dev/limits/cispr25-re)), PA ripple numbers, and a primary u-blox statement on DC/DC desense not obtained.

## Sources

- In-repo [M]: boost-board evaluation on branch `physics-functional-eval`; `kae/src/kae/excite/`, `kae/src/kae/em/pnr.py`, `kae/src/kae/circuit/brief.py`.
- Primary and secondary URLs inline. Books and papers: Marler & Arora 2004; Haimes, Lasdon & Wismer 1971; Charnes & Cooper 1961; Keeney & Raiffa 1976.
- See also: [functional-evaluation](../physics/functional-evaluation.md), [fields-emi-budget](../physics/fields-emi-budget.md), [rf](../rules/rf.md), [thermal](../rules/thermal.md), [decoupling-pdn](../rules/decoupling-pdn.md), [design-rationale-and-intent-record](../ux/design-rationale-and-intent-record.md).
