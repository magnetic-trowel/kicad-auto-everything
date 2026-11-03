# Physics critics: measuring "physically right" next to DRC

Scope: what DRC cannot see, the critic suite architecture, the physics scorecard, how it sits beside kaebench without touching the score, the DRC-clean mutation benchmark and router audit, prototype results on four boards. Not here: the 41 critic definitions -> [physics-critics-catalog](physics-critics-catalog.md); calibration and gaming guards -> [physics-critics-validation](physics-critics-validation.md); functional (circuit) tests -> [functional-evaluation](functional-evaluation.md).
Keys: physics critics, physics scorecard, board physics model BPM, critic contract, markers drc.v1, budget rows, I1 ledger, coverage, mutation benchmark, M-SLOT, M-TRACE-IN-PLANE, M-DEL-RETURN-VIA, M-SWAP-REF, benign twins, router audit, router-induced findings, plane perforation, PC44, cpk-phys, pc_refplane.py, DRC-clean but physically wrong

**Results:**
- DRC checks copper against typed numbers; it cannot see unintended physics (return over a void, a decap via adding nanohenries, a necked pour). Critics measure that realization against budgets in physical units, as **a separate scorecard that never feeds cp1, cpk or DRC**.
- ~40 critics ([catalog](physics-critics-catalog.md)) read one shared board physics model in four fidelity tiers; severity comes from budget utilization, not the critic.
- Prototype [pc_refplane.py](../../../tools/research/physics/pc_refplane.py) (pure Python, 1.4–2.7 s per 4-layer board) fired at all 31 planted faults and no benign twin (§6). Mutants and critic share an author: a method test, not accuracy [C].
- Without roles and budgets critics are noisy (Pi5_PCIe sidebands, §6): make roles and budgets first-class task inputs.

## 1. What DRC cannot see

Tags: [P] primary, [S] secondary, [V] vendor, [I] inference, [C] [pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py).

| DRC-clean fault | Why DRC passes it | Physical consequence (conditions) | Critic |
|---|---|---|---|
| Signals routed on the GND plane layer; a no-tools Claude baseline did this on a "0 ERC/DRC errors" 4-layer board ([kicad-ai-tools](../landscape/kicad-ai-tools-and-mcp-servers.md)) [P] | plane layers are ordinary copper to DRC | slots under every crossing net; Ott: plane voltage 15 → 49 mV for a 1" slot (10 MHz, 3 ns edges) [P] | PLANE-PERF, RET-COV |
| Fast net over a void, split or merged antipads | clearances all met | return detour: a centred 1" slot adds ≈ 3.5 nH by the slot-line proxy (proxy vs PEEC: [validation worked example 2](physics-critics-validation.md#calibration-references-f3-and-measurement)); a slot 50h long under the trace raises end-to-end plane voltage, the CM source, 6.4× ([fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py)) [C] | RET-COV, RET-RPQF, CM-V |
| Layer change without a nearby return via, or onto a different-net reference | vias are legal | return through the nearest bridging cap: +2.4–3.4 nH est. on the sample boards, Ott 5–10 nH [C]/[P] | RET-VIA |
| Decap GND via 5 mm from its pad on a 0.25 mm stub | connected, clean | +1.3–1.9 nH; \|Z(100 MHz)\| of a 100 nF 0402 0.61 → 1.43 Ω [C] | DECAP-L |
| Hot loop returning through a far plane | no rule on loop shape | 12 × 3 mm path: 0.9 nH at 0.2 mm plane depth vs 3.0 nH at 1.0 mm; at 5 A/ns 4.4 vs 15 V overshoot [C] | HOTLOOP-L |
| Power pour necked by a via field or keep-out | width rules apply to tracks, not pours | 1 mm neck, 1 oz, 5 A: 143 A/mm², 12 mV, 61 mW in 5 mm [C] | J-MAX, IR-DROP |
| GND and power as thin traces (OmniRouting LLM outputs) [S] | connected is connected | pin-to-plane R and L set by trace length | PWR-TRACE |
| Sparse stitching between GND layers | no rule | first cavity mode 0.7 GHz at 100 mm spacing, 7 GHz at 10 mm (εr 4.5) [C] | CAVITY, SPECTRUM |
| EEVblog "bird's nest" that "would pass unnoticed by the AI, the simulator and the router alike" ([field-failure-modes](../ux/field-failure-modes.md)) [S] | legal geometry | loop area, coupling, return detours | RET-RPQF, XTALK, LOOP-RAD |

Rarely a finding: 90° corners below multi-GHz, except ESD and RF paths ([myths](../rules/myths-and-contested.md)); via stubs on a 1.6 mm board resonate ≥ 26 GHz, mattering only around PCIe Gen5 rates [C].

## 2. Suite architecture

```
routed .kicad_pcb ─▶ refill zones on a private copy (kicad-cli pcb drc --refill-zones --save-board)
                 ─▶ Board Physics Model (BPM): layer z/h/εr, reference map, current-return graph,
                     plane polygons and slots, via spans, pad shapes
role model + budgets (frozen per task) ─┐
                                         ▼
     F0 geometry (µs–ms) ─ F1 closed forms (ms) ─ F2 2-D/2.5-D solves (s–min) ─ F3 spot checks (min–h)
                                         ▼
     budget rows + markers + coverage ─▶ physics scorecard (beside, never inside, the DRC score)
```

- **Inputs:** routed board and stackup; role model (net roles, edge rates, currents, rails, connector classes, voltage classes); budgets from the IR (`intent.yaml` in [physics-ir](physics-ir.md); [I1/I2](../../ideas/original/intent-and-why.md)). Roles and budgets are frozen and installed by the scorer, like DRC rules, so a method cannot relabel a clock as slow.
- **BPM:** built once, read by every critic; removes the commonest checker field failure, re-implementations disagreeing with KiCad ([field-failure-modes](../ux/field-failure-modes.md)).
- **Tiers** per [solver-ladder](solver-ladder.md) and [evaluation-stack](../verification/evaluation-stack.md): F0/F1 on every candidate, F2 at stage gates, F3 on sampled findings and for calibration.
- **Critic contract:** `critic(bpm, roles, budgets) -> (rows, markers, coverage)`. Rows are continuous values with attribution, each a `Belief` with exactness E0–E5 and its reference model ([physics-core-v2-api](physics-core-v2-api.md)). Coverage says per object whether the critic ran and whether its proxy was inside its calibrated range.

## 3. Reporting

**Markers** for the repair loop use KiCad's `drc.v1` JSON shape (existing parsers and the LLM's DRC habits carry over) plus physics fields:

```json
{"type": "RET-VIA", "severity": "warning", "description": "layer change F.Cu->B.Cu switches reference GND->+3.3V; return via cap C7 at 10.3 mm, est. +2.8 nH",
 "items": [{"uuid": "<via uuid>", "pos": {"x": 162.8, "y": 93.4}}],
 "measured": 2.8, "limit": 1.0, "unit": "nH", "budget_id": "USB.D.loopL", "fidelity": "F1", "trust": "out-of-range",
 "fix": ["add a GND-referenced path: route both segments on layers over GND", "or add a stitching cap within 1.5 mm"]}
```

**Budget rows** = the I1 ledger in the code-only `ledger.json` of [physics-ir](physics-ir.md): `{budget_id, limit, unit, source, spent, utilization, top_spenders: [{object, amount}]}`. Example: 5 nH hot-loop budget spent as 1.1 nH input-cap vias, 0.9 nH SW copper, 2.6 nH return through In2.

**Physics scorecard**, one per board, beside the DRC score, compared lexicographically with no weighted sum (a blended number invites trading a creepage failure for twenty good return paths):
1. **Coverage:** share of required checks that ran; share of nets with roles and budgets. Low coverage cannot earn a good score.
2. **Hard budgets:** pass/fail on hard budgets (safety creepage, ampacity, declared interface limits).
3. **Margin:** min over soft budgets of (1 − utilization) = 1 − layout invisibility index ([schematic-to-physics](schematic-to-physics.md)); worst three budgets by name.
4. **Counts** by critic and severity, grouped by root cause (one plane cut causes a dozen crossing markers).
5. **Human-relative:** new findings and utilization deltas vs the human reference board.

Unbudgeted quantities show "unbudgeted" rather than invented limits (many budgets, e.g. hot-loop area caps and decap distances, have no primary source; [checkers-power](../rules/checkers-power.md)).

## 4. Fitting it into kaebench without touching the score

Physics never enters `score.py`, `potential()` or cp1/cpk (CLAUDE.md).
- **Separate tool first** (later `kaebench physics`, own commit): walks `kae-work/results/<run>/<adapter>/<kind>/<id>/attempt-N/`, reads `attempt.json` (skipping invalid attempts) and `output/board.kicad_pcb`; copies the board with the reference `.kicad_pro`/`.kicad_dru` into `attempt-N/physics/`, refills and saves zones there, runs critics, writes `ledger.json` (observed values, spend, markers) and `scorecard.json` (critic version, BPM hash, coverage).
- **Must refill itself:** route tasks start with zones unfilled and the scorer refills inside `kicad-cli` without saving; neither `output/` nor `score/` holds the fills ([harness](../verification/harness.md)).
- **Roles and budgets per task:** `kae-work/tasks/<id>/physics/intent.yaml`, generated from reference board, schematic, datasheets; human-confirmed; frozen.
- **Human reference:** the `reference` adapter scored once per task and cached, so reports show regressions vs human copper.
- **Report:** `physics-report <run> <baseline>` prints per adapter and split: cp1 and cpk (copied unchanged from `results.jsonl`), completion, error counts, then hard-budget pass@1, median margin, critic coverage, new findings vs human, PLANE-PERF foreign length on declared planes, RET-COV void crossings, RET-VIA findings. Optional "cpk-phys" (best clean attempt by physics) is a separate column, never replacing cpk.
- **Comparisons:** same KiCad version, manifest, suite; same critic version and role files.

## 5. The "DRC-clean but physically wrong" benchmark

Build it before any optimizer uses a critic; report detection, false alarms and magnitude agreement per critic version. Each operator is DRC-neutral by construction or kept only if DRC is unchanged. Full per-critic list, scoring and gaming guards: [physics-critics-validation](physics-critics-validation.md).

| Operator | Edit | How DRC stays clean | Physics delta (oracle) |
|---|---|---|---|
| M-SLOT | pour keep-out rule area as a 0.6 × 12 mm strip on the reference under a fast net | keep-outs only remove pour | slot detour L; Ott-fitted ΔV |
| M-TRACE-IN-PLANE | move a segment onto the plane layer with two vias | DRC filter | slot in the plane under every net above it |
| M-DEL-STITCH / M-DEL-RETURN-VIA | delete GND vias carrying no tracks | stitching vias carry no connectivity | return-via distance, cavity mode |
| M-SWAP-REF | swap the nets of two plane zones | vias connect to whichever plane has their net | reference-net change per layer, signed per net |
| M-DECAP-FAR | move a decap's GND via d mm along a stub | DRC filter | ΔL by trace L′ |
| M-NECK, M-VIAFIELD | keep-out or other-net via field across a power pour | keep-out; DRC filter | ΔR, J_max |
| M-THERMAL-RELIEF | power pad solid → thermal relief | zone setting | ΔR, ΔT |
| M-EDGE-SHIFT, M-SENSE-PARALLEL, M-LAYER-SWAP | re-route a run toward an edge, next to SW, or onto another reference | DRC filter | L_ret, mutual L, reference change |

**Protocol:**
1. Start from qualified reference boards (human copper, DRC-clean).
2. Apply each operator at sampled sites with a fixed seed.
3. Run DRC with refill; keep mutants whose per-type and unconnected counts equal the original's.
4. Label each with an oracle delta (F1 for all, F2/F3 on a sample); drop equivalent mutants.
5. Pair each operator with benign twins.
6. Score per critic: detection at the site (recall), false alarms on twins and originals, rank agreement of estimate vs oracle delta.

**Router audit:** run the critics on every routed attempt and the reference; count *router-induced* findings (absent from the human board on the same task); publish next to the cp1/cpk table (qualified suite, Freerouting vs reference). Predictions to test [I]:
- Plane perforation on 4+-layer boards: KiCad's Freerouting guide says only `power`-typed layers are withheld from routing ([KiCad guide](https://git.fossee.in/KiCad-eSim/.git/plain/pcbnew/dialogs/dialog_freeroute_exchange_help.html) [S]); all four sampled 4-layer boards type their planes `signal`. Source is an old guide and forum reports; untested on the harness. A layer-type-hygiene adapter variant (PC44) measures it, as a method change with a new run name.
- More RET-VIA findings than the human board (router adds layer changes without return vias).

## 6. Prototype results

[pc_refplane.py](../../../tools/research/physics/pc_refplane.py) implements RET-COV/HOP/EDGE, RET-VIA (with bridging-cap estimate), RET-REFNET, RET-RPQF, PLANE-PERF, PWR-TRACE, CAVITY, plus an in-memory mutation self-test. Run on four boards from `bench/manifests/candidates.jsonl` (pinned commits, hash-verified, not committed); roles by net-name regex (flags USB, CAN, SWD, PCIe names only). Planes inferred from fill share (≥ 30%), which also catches outer-layer pours; declared IR-stackup planes are the right source, inference a fallback.

| Board (4-layer) | Findings | Matters? |
|---|---|---|
| justbuchanan/oasis (GND / +18 V inner planes) | USB D± change reference GND → power at both F→B vias; nearest bridging cap 5.9–16 mm, est. +2.9–3.4 nH. In1 GND plane: 0.33 mm foreign track, longest slot 7.6 mm | probably not if USB is full-speed: ~9 mA/ns × 3 nH ≈ 26 mV bounce [I] |
| brenocq/BLDCM-Power (3.3 V / GND inner) | every USB, CAN, SWD layer change switches reference 3.3 V → GND (+2.4–2.9 nH est.). VBUS: 6/6 pads off-pour with 43 mm of < 0.4 mm track. Power stage: exposed pad without vias, island ground under input caps, one connector via carrying 52% of that connector's ground current ([real-board-passports](real-board-passports.md)) | needs rail current: VBUS on thin traces matters only if it carries amps |
| caffeinated-labs/AFTONSPARV (ESP32) | USB D+ and D− only 46% and 30% over the near reference; 4 small voids near the connector (0.07–0.36 nH each) | low at USB FS edge rates |
| m1geo/Pi5_PCIe | PCIe TX/RX/CLK: zero voids, RPQF 1.01–1.09. Sidebands (WAKE#, SMCLK, SMDAT, CLKREQ#, PRSNT2#): 11 void crossings; In2 GND plane 48 mm foreign track, 45 mm slot (half-wave ≈ 2.0 GHz) | no: fast pairs kept clean, slow nets over the voids |

Self-test with fast-net roles: M-SLOT 12/12, M-TRACE-IN-PLANE 12/12, M-DEL-RETURN-VIA 4/4, M-SWAP-REF 3/3 (any change in reference findings counts). Benign twins: 0/3 far slots, 0/4 extra GND vias fired. Blind spots a red team would exploit:
- an own-antipad exclusion hides slots under a same-net pad unless limited to antipad-sized voids (≤ 2 mm);
- via reference tests fail inside the via's own antipad.

Next: productionize pc_refplane.py into a small package under `tools/` with tests on synthetic unit boards; build the BPM, refill contract and the six cheap critics (RET-COV, RET-VIA, PLANE-PERF, PWR-TRACE, DECAP-L, HOTLOOP-L); calibrate F1 proxies (FastHenry, openEMS slices, `sl_loop_peec.py`, `pw_peec.py`, `fe_peec_plane.py`, `fe_cavity.py`, [validation coupons](validation-coupons.md)) and record a trust range before any reward use.

## Open questions

- Bridging-cap estimate and slot proxy calibration -> [physics-critics-validation](physics-critics-validation.md#open-questions).
- Circularity: critic and mutants share an author; real routers may fail in ways no operator models (Just et al.: 27% of real software faults uncoupled to any mutant). Seed operators from real escapes (V5).

## Sources

- Research notes: [constraints_verification_benchmarks.md § Q2–Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md); [field_reports_and_ux.md § 1A](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md); [rules_highspeed_emi.md § 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md).
- Altium Return Path rule: https://altium.com/documentation/altium-designer/pcb-high-speed-rule-return-path [P]
- Cadence/EMA return-path quality factor (loop L / ideal; "no best value or threshold"): https://www.ema-eda.com/ema-resources/blog/investigating-return-path-discontinuities-understanding-impacts-and-effective-mitigation-strategies/ [V]
- Clemson CVEL, EMC expert systems (sources, coupling paths, antennas; ranking): https://cecas.clemson.edu/cvel/emc/expert_systems/PCB/pcb_es_overview.html [S]
- KiCad Freerouter guide (power-typed layers removed from routing): https://git.fossee.in/KiCad-eSim/.git/plain/pcbnew/dialogs/dialog_freeroute_exchange_help.html [S]
- Just et al., FSE 2014: https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf [S]
- Related: [vocabulary](vocabulary.md), [critic-stack](../verification/critic-stack.md), [ideas: critics](../../ideas/physics-first/critics.md).
