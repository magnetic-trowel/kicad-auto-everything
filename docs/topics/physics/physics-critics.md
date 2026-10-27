# Physics critics: measuring "physically right" next to DRC

**TL;DR**
- DRC checks copper against numbers someone typed (clearance, width, connectivity). It cannot see the board's unintended physics: a signal whose return path crosses a void, a decap whose via adds 1.9 nH, a power pour necked to 143 A/mm². Physics critics measure that realization against budgets in physical units, and they form **a separate scorecard that never feeds cp1, cpk or DRC**.
- The suite is about 40 critics ([catalog](physics-critics-catalog.md)) reading one shared board physics model in four fidelity tiers. Each emits continuous values with per-object attribution and KiCad-style markers. Severity comes from budget utilization, not from the critic.
- Ground truth comes from a **DRC-equivalent mutation benchmark**: planted faults that leave `kicad-cli` DRC counts unchanged, each labelled with its physics delta, plus benign twins. The same critics run on router outputs vs the human board show how often routers create these faults on their own.
- Prototype ([pc_refplane.py](../../../tools/research/physics/pc_refplane.py)), pure Python, 1.4–2.7 s per 4-layer board. In this run, on four open boards, it fired at the site of 31/31 planted faults (12 slots, 12 tracks through a plane, 4 deleted return vias, 3 plane-net swaps) and on 0/7 benign twins. Mutants and critic share an author, so this tests the method, not accuracy.
- Without roles and budgets the critics are noisy. On a Pi 5 PCIe adapter, the high-speed pairs were clean (no voids, RPQF 1.01–1.09), but the slow sideband nets crossed 11 voids. A role-blind critic would raise 11 warnings that do not matter.

## Key facts

### 1. What DRC cannot see

Tags: [P] primary, [S] secondary, [V] vendor, [I] inference, [C] computed with [pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py).

| DRC-clean fault | Why DRC passes it | Physical consequence (conditions) | Critic |
|---|---|---|---|
| Signals routed on the GND plane layer. A no-tools Claude baseline did this on a "0 ERC/DRC errors" 4-layer board ([kicad-ai-tools](../landscape/kicad-ai-tools-and-mcp-servers.md)) [P] | Plane layers are ordinary copper to DRC | Slots under every crossing net. Ott: plane voltage 15 → 49 mV for a 1" slot (10 MHz, 3 ns edges) [P] | PLANE-PERF, RET-COV |
| Fast net over a void, split or merged antipads | Clearances are all met | Return detour: a centred 1" slot adds ≈ 3.5 nH by the slot-line proxy, which is within 0–18% of the in-repo PEEC for a slot 2h wide and 1.75–1.9× high for 0.5h. A slot 50h long under the trace raises the end-to-end plane voltage, the common-mode source, 6.4× ([fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py)) [C] | RET-COV, RET-RPQF, CM-V |
| Layer change without a nearby return via, or onto a different-net reference | Vias are legal | Return through the nearest bridging cap: +2.4–3.4 nH estimated on the sample boards, Ott 5–10 nH [C]/[P] | RET-VIA |
| Decap GND via 5 mm from its pad on a 0.25 mm stub | Connected, clean | +1.3–1.9 nH; \|Z(100 MHz)\| of a 100 nF 0402 rises from 0.61 to 1.43 Ω [C] | DECAP-L |
| Hot loop returning through a far plane | No rule on loop shape | 12 × 3 mm path: 0.9 nH at 0.2 mm plane depth vs 3.0 nH at 1.0 mm. At 5 A/ns: 4.4 vs 15 V of overshoot [C] | HOTLOOP-L |
| Power pour necked by a via field or keep-out | Width rules apply to tracks, not pours | 1 mm neck, 1 oz, 5 A: 143 A/mm², 12 mV, 61 mW in 5 mm [C] | J-MAX, IR-DROP |
| GND and power routed as thin traces (OmniRouting LLM outputs) [S] | Connected is connected | Pin-to-plane R and L set by trace length | PWR-TRACE |
| Sparse stitching between GND layers | No rule | First cavity mode 0.7 GHz at 100 mm spacing, 7 GHz at 10 mm (εr 4.5) [C] | CAVITY, SPECTRUM |
| EEVblog "bird's nest" that "would pass unnoticed by the AI, the simulator and the router alike" ([field-failure-modes](../ux/field-failure-modes.md)) [S] | Legal geometry | Loop area, coupling, return detours | RET-RPQF, XTALK, LOOP-RAD |

Some popular concerns rarely earn a finding. 90° corners do not matter below multi-GHz, except on ESD and RF paths ([myths](../rules/myths-and-contested.md)). Via stubs on a 1.6 mm board resonate at 26 GHz or higher, so they matter only around PCIe Gen5 rates [C].

### 2. Suite architecture

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

- **Inputs.** The routed board and its stackup; the role model (net roles, edge rates, currents, rails, connector classes, voltage classes); budgets from the IR (`intent.yaml` in [physics-ir](physics-ir.md); [I1/I2](../../ideas/original/intent-and-why.md)). Roles and budgets are frozen and installed by the scorer, like the DRC rules, so a method cannot relabel a clock as slow.
- **Board physics model.** Built once and read by every critic. It removes the most common field failure in checkers, re-implementations that disagree with KiCad ([field-failure-modes](../ux/field-failure-modes.md)).
- **Tiers** follow the evaluation stack ([evaluation-stack](../verification/evaluation-stack.md)). F0/F1 run on every candidate, F2 at stage gates, F3 on sampled findings and for calibration.
- **Critic contract.** `critic(bpm, roles, budgets) -> (rows, markers, coverage)`. Rows are continuous values with attribution; each value is a `Belief` with an exactness class E0–E5 and the model it is exact relative to ([physics-core-v2-api](physics-core-v2-api.md)). Coverage says, per object, whether the critic ran and whether its proxy was inside its calibrated range.

### 3. Reporting

**Markers for the repair loop** use the shape of KiCad's `drc.v1` JSON, so existing parsers and the LLM's DRC habits carry over, plus physics fields:

```json
{"type": "RET-VIA", "severity": "warning", "description": "layer change F.Cu->B.Cu switches reference GND->+3.3V; return via cap C7 at 10.3 mm, est. +2.8 nH",
 "items": [{"uuid": "<via uuid>", "pos": {"x": 162.8, "y": 93.4}}],
 "measured": 2.8, "limit": 1.0, "unit": "nH", "budget_id": "USB.D.loopL", "fidelity": "F1", "trust": "out-of-range",
 "fix": ["add a GND-referenced path: route both segments on layers over GND", "or add a stitching cap within 1.5 mm"]}
```

**Budget rows** are the I1 ledger, stored in the code-only `ledger.json` of [physics-ir](physics-ir.md): `{budget_id, limit, unit, source, spent, utilization, top_spenders: [{object, amount}]}`. Example: a 5 nH hot-loop budget spent as 1.1 nH input-cap vias, 0.9 nH SW copper, 2.6 nH return through In2.

**Physics scorecard.** One per board, next to the DRC-based score. It reports, in this order:
1. **Coverage**: the share of required checks that ran, and the share of nets with roles and budgets. A low-coverage board cannot earn a good score.
2. **Hard budgets**: pass/fail on budgets marked hard (safety creepage, ampacity, declared interface limits).
3. **Margin**: the minimum over soft budgets of (1 − utilization), which is 1 minus the layout invisibility index of [schematic-to-physics](schematic-to-physics.md), and the worst three budgets by name.
4. **Counts** by critic and severity, grouped by root cause (one plane cut causes a dozen crossing markers).
5. **Human-relative**: new findings and utilization deltas against the human reference board.

The scorecard compares lexicographically and has no weighted sum. A single blended number invites trading a creepage failure for twenty good return paths.

### 4. Fitting it into kaebench without touching the score

The CLAUDE.md rule is that scoring and integrity checks define the benchmark, so physics never enters `score.py`, `potential()` or cp1/cpk. Plan:

- **A separate tool first** (later a `kaebench physics` subcommand, in its own commit). It walks `kae-work/results/<run>/<adapter>/<kind>/<id>/attempt-N/` and reads `attempt.json` (skipping invalid attempts) and `output/board.kicad_pcb`. It copies the board with the reference `.kicad_pro`/`.kicad_dru` into `attempt-N/physics/`, refills and saves zones there, runs the critics, and writes `ledger.json` (observed values, spend, markers) and `scorecard.json` with the critic version, BPM hash and coverage.
- **Why it must refill itself.** Route tasks start with zones unfilled, and the scorer refills zones inside `kicad-cli` without saving. Neither `output/` nor `score/` holds the fills the critics need ([harness](../verification/harness.md)).
- **Roles and budgets per task.** Stored as `kae-work/tasks/<id>/physics/intent.yaml`, generated from the reference board, schematic and datasheets, confirmed by a human, and frozen.
- **Human reference.** The `reference` adapter is scored once per task and cached, so every report can show regressions relative to the human copper.
- **Report.** `physics-report <run> <baseline>` prints, per adapter and split: cp1 and cpk (copied unchanged from `results.jsonl`), completion, error counts, and then the physics columns: hard-budget pass@1, median margin, critic coverage, new findings vs human, PLANE-PERF foreign length on declared planes, RET-COV void crossings and RET-VIA findings. An optional "cpk-phys" picks the best clean attempt by physics. It is a separate column and never replaces cpk.
- **Comparisons** follow CLAUDE.md: same KiCad version, manifest and suite; same critic version and role files.

### 5. The "DRC-clean but physically wrong" benchmark

**Operators.** Each one is DRC-neutral by construction or kept only if DRC is unchanged.

| Operator | Edit | How DRC stays clean | Physics delta (oracle) |
|---|---|---|---|
| M-SLOT | Pour keep-out rule area (copper pour not allowed) as a 0.6 × 12 mm strip on the reference under a fast net | Keep-outs only remove pour | Slot detour L; Ott-fitted ΔV |
| M-TRACE-IN-PLANE | Move a segment onto the plane layer with two vias | DRC filter | Slot in the plane under every net above it |
| M-DEL-STITCH / M-DEL-RETURN-VIA | Delete GND vias that carry no tracks | Stitching vias carry no connectivity | Return-via distance, cavity mode |
| M-SWAP-REF | Swap the nets of two plane zones | Vias connect to whichever plane has their net | Reference-net change per layer, signed per net |
| M-DECAP-FAR | Move a decap's GND via d mm along a stub track | DRC filter | ΔL by trace L′ |
| M-NECK, M-VIAFIELD | Keep-out or other-net via field across a power pour | Keep-out; DRC filter | ΔR, J_max |
| M-THERMAL-RELIEF | Power pad connection solid → thermal relief | A zone setting | ΔR, ΔT |
| M-EDGE-SHIFT, M-SENSE-PARALLEL, M-LAYER-SWAP | Re-route a run toward an edge, next to SW, or onto another reference | DRC filter | L_ret, mutual L, reference change |

The full list, with calibration and gaming guards per critic, is in [physics-critics-validation.md](physics-critics-validation.md).

**Protocol.**
1. Start from qualified reference boards (human copper, DRC-clean).
2. Apply each operator at sampled sites with a fixed seed.
3. Run DRC with refill and keep mutants whose per-type counts and unconnected count equal the original's.
4. Label each with an oracle delta (F1 for all, F2/F3 on a sample) and drop equivalent mutants.
5. Pair each operator with benign twins.
6. Score each critic: detection at the site (recall), false alarms on twins and originals, and rank agreement between its estimate and the oracle delta.

**Router audit.** Run the same critics on every routed attempt and on the reference, and count *router-induced* findings: those absent from the human board on the same task. Two predictions to test [I]:
- **Plane perforation on 4+-layer boards.** KiCad's Freerouting guide says only layers typed `power` are withheld from routing ([KiCad guide](https://git.fossee.in/KiCad-eSim/.git/plain/pcbnew/dialogs/dialog_freeroute_exchange_help.html) [S]). All four 4-layer boards sampled here type their planes as `signal`.
- **More RET-VIA findings** than the human board, because the router adds layer changes without return vias.

A layer-type-hygiene adapter variant (idea PC44) would measure the first effect. It counts as a method change, with a new run name.

### 6. Prototype results

[pc_refplane.py](../../../tools/research/physics/pc_refplane.py) implements RET-COV/HOP/EDGE, RET-VIA (with the bridging-cap estimate), RET-REFNET, RET-RPQF, PLANE-PERF, PWR-TRACE and CAVITY, plus an in-memory mutation self-test. It was run on four boards from `bench/manifests/candidates.jsonl` (fetched at their pinned commits and hash-verified; not committed). Roles were assigned by net-name regex. Findings on the human boards:

| Board (4-layer) | Findings | Matters? |
|---|---|---|
| justbuchanan/oasis (GND / +18 V inner planes) | USB D± change reference GND → power at both F→B vias; nearest bridging cap 5.9–16 mm, est. +2.9–3.4 nH. In1 GND plane: 0.33 mm of foreign track, longest slot 7.6 mm | Probably not, if USB is full-speed: about 9 mA/ns × 3 nH ≈ 26 mV of bounce [I] |
| brenocq/BLDCM-Power (3.3 V / GND inner) | Every USB, CAN and SWD layer change switches reference 3.3 V → GND (+2.4–2.9 nH est.). VBUS: 6/6 pads off-pour with 43 mm of < 0.4 mm track. Power stage: exposed pad without vias, an island ground under the input caps, one connector via carrying 52% of that connector's ground current ([real-board-passports](real-board-passports.md)) | Needs the rail current: VBUS on thin traces matters only if it carries amps |
| caffeinated-labs/AFTONSPARV (ESP32) | USB D+ and D− only 46% and 30% over the near reference; 4 small voids near the connector (0.07–0.36 nH each) | Low at USB FS edge rates |
| m1geo/Pi5_PCIe | PCIe TX/RX/CLK: zero voids, RPQF 1.01–1.09. Sidebands (WAKE#, SMCLK, SMDAT, CLKREQ#, PRSNT2#): 11 void crossings; In2 GND plane has 48 mm of foreign track and a 45 mm slot (half-wave ≈ 2.0 GHz) | No: the designer kept the fast pairs clean and put slow nets over the voids |

Self-test with fast-net roles: M-SLOT 12/12, M-TRACE-IN-PLANE 12/12, M-DEL-RETURN-VIA 4/4, and M-SWAP-REF 3/3 (any change in reference findings counts as detection). Benign twins: 0/3 far slots and 0/4 extra GND vias fired. The self-test exposes two blind spots a critic must guard against:
- An own-antipad exclusion hides slots under a same-net pad unless it is limited to antipad-sized voids (≤ 2 mm).
- Via reference tests fail inside the via's own antipad.

Both are the kind of escape a red team would exploit.

## Recommendations for our system

1. Build the BPM, the refill contract and the six cheap critics (RET-COV, RET-VIA, PLANE-PERF, PWR-TRACE, DECAP-L, HOTLOOP-L). Productionize pc_refplane.py into a small package under `tools/` with tests on synthetic unit boards.
2. Build the mutation benchmark before any optimizer uses a critic. Report detection, false alarms and magnitude agreement per critic version.
3. Run the router audit on the qualified suite, Freerouting vs reference, and publish router-induced physics findings next to the existing cp1/cpk table.
4. Calibrate F1 proxies against FastHenry, openEMS slices, the in-repo PEEC scripts (`sl_loop_peec.py`, `pw_peec.py`, `fe_peec_plane.py`, `fe_cavity.py`) and the [validation coupons](validation-coupons.md) before using them as rewards. Record a trust range per proxy.
5. Make roles and budgets first-class task inputs. Without them a critic cannot tell a PCIe pair from a WAKE# line.

## Conflicts and open questions

- **Threshold sources.** Many budgets have no primary source (hot-loop area caps, decap distances). The scorecard should show "unbudgeted" rather than invent limits ([checkers-power](../rules/checkers-power.md)).
- **Plane inference vs declaration.** The prototype infers planes from fill share (≥ 30%), which also catches outer-layer pours. Declared planes in the IR stackup are the right source; inference is a fallback.
- **Bridging-cap estimate.** Ours (1.2–3 nH) disagrees with Ott's 5–10 nH. It probably misses the cap's own via loop and ESL.
- **Slot proxy.** It ignores slot width. Against the PEEC it is right for wide slots and about 1.8× pessimistic for narrow ones; Z_slot should become a function of g/h.
- **Freerouting prediction.** The claim that Freerouting perforates `signal`-typed planes comes from an old KiCad guide and forum reports [S]. It is untested on the harness.
- **Circularity.** The prototype's critic and mutants share an author, and real routers may fail in ways no operator models (Just et al. found 27% of real software faults uncoupled to any mutant). Seed operators from real escapes (V5).

## Sources

- research notes: [constraints_verification_benchmarks.md § Q2–Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md); [field_reports_and_ux.md § 1A](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md); [rules_highspeed_emi.md § 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
- Altium Return Path rule: https://altium.com/documentation/altium-designer/pcb-high-speed-rule-return-path [P]
- Cadence/EMA return-path quality factor (loop L / ideal; "no best value or threshold"): https://www.ema-eda.com/ema-resources/blog/investigating-return-path-discontinuities-understanding-impacts-and-effective-mitigation-strategies/ [V]
- Clemson CVEL, EMC expert systems (sources, coupling paths, antennas; ranking): https://cecas.clemson.edu/cvel/emc/expert_systems/PCB/pcb_es_overview.html [S]
- KiCad Freerouter guide (power-typed layers removed from routing): https://git.fossee.in/KiCad-eSim/.git/plain/pcbnew/dialogs/dialog_freeroute_exchange_help.html [S]
- Just et al., FSE 2014, mutants vs real faults: https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf [S]

See also: [physics-critics-catalog.md](physics-critics-catalog.md), [physics-critics-validation.md](physics-critics-validation.md), [physics-ir.md](physics-ir.md), [vocabulary.md](vocabulary.md), [solver-ladder.md](solver-ladder.md), [../verification/critic-stack.md](../verification/critic-stack.md), [../verification/harness.md](../verification/harness.md), [../../ideas/physics-first/critics.md](../../ideas/physics-first/critics.md)
