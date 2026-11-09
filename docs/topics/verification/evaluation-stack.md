# Evaluation stack: fast-to-slow checks, open-source tools and runtimes

Scope: tiered evaluation T0–T3, `kicad-cli` DRC as referee, KiCad 10 evaluation-loop backend, open SI/PI/thermal tools, speed evidence, ML surrogates. Not here: harness -> [harness.md](harness.md); metric definitions -> [quality-metrics.md](quality-metrics.md); critics -> [critic-stack.md](critic-stack.md); kicad-cli details -> [../kicad/kicad-cli.md](../kicad/kicad-cli.md).
Keys: evaluation stack, T0, T1, T2, T3, kicad-cli pcb drc, drc.v1.json, --schematic-parity, --severity-all, --refill-zones, --exit-code-violations, IPC API, RefillZones, SES import, route_with_freerouting, Transcalc, gerber2ems, si-wrapper, openEMS, Palace, padne, KiPI, Ki-PIDA, PCB_SI_Toolkit, emcvisual, CalculiX, Elmer, PDN DNN, DevFormer, surrogate
Tags: [P] primary; [S] snippet/secondary; [V] vendor; [I] inference; [M] measured in this repo.

## Evaluation rules
1. Four tiers (table below): wire T0 and T1 into the placement loop, T2 at state gates, T3 for finalists; record every verdict in the findings channel ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)) [I].
2. Rule routers fit inside a placement loop as evaluators only on small boards (KRT ≈0.65 s, Freerouting 2.1.0 ≈7 s per D3-A board ≤31 pads); on large boards the harness measured 600 s timeouts and 900 s DRC timeouts ([harness.md](harness.md#qualification-yield-and-first-baseline)) [M].
3. Calibrate T0/T1 proxies against T3 on reference boards before using them as rewards (precedents: Antmicro's VNA slices, emcvisual's 1 dB agreement) [I].
4. Most production-ready open SI verifier: Antmicro si-wrapper + gerber2ems (CI-able, VNA-validated, KiCad 9.0.x only); reuse its slicing (pick constrained classes, slice, short passives, terminate neighbours, auto-place ports) [I]. Thermal: analytic proxies in the loop, FEM only at sign-off [I].
5. ML surrogates exist for PDN impedance, decap selection, eye metrics, crosstalk; none is layout-generic, open and KiCad-integrated; no layout-level EMI or thermal surrogate exists. Surrogate training data: label synthetic KiCad boards with fast physics tools (padne, KiPI, return_path, si-wrapper slices), following the PDN-DNN recipe [I].
6. Return compact summaries to the LLM (scores, unrouted counts, grouped violations, congestion hotspots), never geometry dumps [I].
## Tiers

| Tier | When | Checks | Tools and runtime evidence |
|---|---|---|---|
| T0 (µs–ms) | Every move | Overlap/out-of-bounds; intent and PRC geometry (proximity, region, edge, symmetry, layer-switch count once routed); HPWL; net crossings; Transcalc Z0/delay; IPC-2221/2152 widths; overheated-length proxy; convention metrics ([looks-right-metrics.md](looks-right-metrics.md)) | In-process geometry; KRT-style intent grader; optional trained PDN-impedance DNN (0.1 s) |
| T1 (s on small boards; minutes or more on large ones) | Per accepted placement or route batch | `kicad-cli pcb drc --format json --schematic-parity --severity-all --refill-zones --exit-code-violations` (add `--all-track-errors` for repair loops); return-path VOID/SPLIT/VIA flags; NRR/PRR/PShort; quick reference router as routability probe | kicad-cli; `return_path`; KRT ≈0.65 s and Freerouting 2.1.0 ≈7 s per small PCBWorld D3-A board ([PCBWorld Table 3](https://arxiv.org/html/2607.05915v2)) [P]; see Speed evidence for large boards |
| T2 (s–min) | Checkpoints | DC IR drop and current density; PDN impedance vs target; switcher coupled noise; near-field estimate | padne, KiPI, Ki-PIDA, emcvisual |
| T3 (min–h) | Finalists | openEMS S-parameters, TDR and delay per critical net/pair via si-wrapper slices; FEM thermal | gerber2ems + si-wrapper + scikit-rf; FreeCAD/gmsh/CalculiX (Antmicro scripts) or Salome/Elmer; Palace for C/L extraction |

## Legality: kicad-cli pcb drc
Referee: `kicad-cli pcb drc` on a saved copy (KiCad 10 IPC cannot run DRC) → flags and exit code 5 in [../kicad/kicad-cli.md](../kicad/kicad-cli.md#referee-command); `drc.v1.json` schema, no rule-name field, trailing comma, 67 `type` keys, Freerouting `-drc` in the same format → [../kicad/drc-report-and-repair-loop.md](../kicad/drc-report-and-repair-loop.md#schema-drcv1json-identical-on-100-and-master) [P, VK].

## KiCad 10 backend for the evaluation loop
Four channels on 10.x (IPC CRUD in commits, direct `.kicad_dru` writes, `kicad-cli` referee, SWIG DSN/SES helper process) → [../kicad/ipc-api-10-vs-11.md](../kicad/ipc-api-10-vs-11.md#10x-backend-recipe) [P/I, VK §3, §5]. The verification note gave only `--format json --refill-zones` for the referee; without `--schematic-parity` parity is not checked, and without `--severity-all` excluded items are not reported. Evaluation-loop pitfalls, each at its home:
- Async whole-board `RefillZones`: poll until not busy → [IPC](../kicad/ipc-api-10-vs-11.md#behaviour-observed-by-mcp-servers-kicad-1005).
- Destructive SES import, wrapper tool `route_with_freerouting` → [integration](../kicad/specctra-freerouting-integration.md#wrapper-tool-route_with_freerouting).
- KiCad DRC vs Freerouting drc.v1 diff reveals DSN translation losses → [DRC report](../kicad/drc-report-and-repair-loop.md#parser-and-loop-requirements).
- Diff-pair name matcher pairs `XTAL_P`/`XTAL_N` falsely: flag such pairs → [rule language](../kicad/drc-rule-language-reference.md#diff-pair-naming-rule-router-and-drc-share-it).
- KiCad 11 adds headless `kicad-cli api-server`, design rules over IPC, `ImportSpecctraSession`, `kicad-cli pcb export specctra`, export jobs → [IPC](../kicad/ipc-api-10-vs-11.md#coverage-matrix).

## Tools beyond DRC

| Tool | What it does | Notes | Tag |
|---|---|---|---|
| KiCad PCB Calculator (Transcalc) | Microstrip, CPW, GCPW, coax, coupled microstrip, stripline, twisted pair; IPC-2221 track width | KiCad 10 tuning profiles compute geometry and unit delay from target impedance | [P] |
| gerber2ems (Apache-2.0) | Gerbers + `stackup.json` + drill + `-pos.csv` ports + `simulation.json` → openEMS → S-params/impedance CSV | Pixel 5 µm default (raise for large boards, libcairo limit); grid optimal 50 µm, perpendicular 200 µm, max 500 µm, pitch ≤ λmin/10; ports ≥8 cells; capacitors shorted; field dumps "can easily take hundreds GB" ([README](https://github.com/antmicro/gerber2ems)) | [P] |
| kicad-si-simulation-wrapper | Selects nets (e.g. a controlled-impedance class); slices net/pair + neighbours + vias + planes; shorts 0 Ω and large caps; terminates neighbours; auto-places ports; writes netinfo | Needs KiCad 9.0.x. 2025: adaptive grid, diff pairs, trace delay; "operate[s] mostly without manual tweaking", CI-capable; VNA-validated on the RDIMM DDR5 tester clock pair ("match pretty well") ([Antmicro 2025](https://antmicro.com/blog/2025/07/recent-improvements-to-antmicros-signal-integrity-simulation-flow)) | [P] |
| openEMS | EC-FDTD; Python/Octave | Engine GPLv3+, CSXCAD LGPLv3+ | [P] |
| Palace (AWS) | 3D FEM: eigenmode, driven, time-domain; lumped C/L matrix extraction; AMR | Apache-2.0 | [P] |
| FastHenry/FastCap; scikit-rf | Inductance/capacitance extraction; Touchstone/network analysis | scikit-rf is BSD | [P] |
| padne | KiCad-native 2.5D FEM DC solver; sources declared in schematic text (`!padne VOLTAGE v=3.3V p=U1.1 n=U1.4`) | FEM core ~40 lines: "the vast majority of work … is ferrying data around"; via model uncertain except "large and short" vias | [P] |
| KiPI | DC drop, AC PDN impedance sweep vs a target-impedance calculator, switcher coupled noise; YAML setup, HTML/PDF reports | GPL-3.0, 0.9.1 alpha | [P] |
| Ki-PIDA | Hybrid 2.5D resistive mesh with electro-thermal coupling | KiCad 9+, IPC API | [P] |
| PCB_SI_Toolkit | Measured-vs-limit checks: decap distance, plane edge 3×h, reference changes without ground vias, DC network, 2D Z0 solver, NEXT, openEMS tab | KiCad 10 | [P] |
| `return_path` (kicad-tools) | VOID, ISLAND, SPLIT, TERMINAL, VIA and EDGE flags on a 0.05 mm A* raster; loop-area estimate | — | [P] |
| emcvisual | Biot–Savart with image currents; ~30 rule checks | Far field "within 1 dB between 30 and 350 MHz" of openEMS on a validation board | [P] |
| kicad-happy EMC | 44 rules | kicad-emi-guardian is "not an EMC compliance instrument" | [P] |
| Antmicro thermal scripts | FreeCAD 1.0 geometry and meshing → CalculiX 2.20 → ParaView | Validated on an RPi5 enclosure at 2.5/8 W (film coefficients 5.14/6.61 W/m²K) and in vacuum tests; CLI, CI-suitable | [P] |
| KiCad + Salome + Elmer | XAO copper export → mesh (0.02–0.08 mm) → static current conduction | "a bit tedious" with "four different software packages" | [P] |
| Quilter Overheated Length PRC | Analytic: % of a high-current net with temperature rise >20 °C | Cheap thermal proxy | [V] |

The KiCad core has no SI/PI plans: a July 2026 forum request got no developer reply, and FEM issue #8398 "has not seen much progress in the last 6 years" [P/S].

## Speed evidence

| Item | Figure | Tag |
|---|---|---|
| PCBWorld per-rollout time | Freerouting 2.1.0, KRT, PPO, GPT-5.4 agent times -> [PCBWorld](../routing/pcbworld.md#results-table-21-5) | [P] |
| kaebench on KiCad 10.0.7 | 22 of 79 split-C boards time out at 600 s; 4 of 297 DRC timeouts at 900 s; CLAUDE.md sets `KAE_DRC_TIMEOUT=3600` for big boards ([harness.md](harness.md)) | [M] |
| gerber2ems sample | 3.37 ms/timestep × 10,000 steps ≈ 34 s per excited port; scales with cells, steps and ports | [P, derived] |
| Analytic radiated power | 30 s vs ~5 h full-wave | [S] |

## ML surrogates

| Surrogate | Facts | Tag |
|---|---|---|
| PDN impedance DNN (Missouri S&T, 2021) | Trained on >1M random BEM-labelled boards; 0.1 s; >100× faster than BEM and 5000× faster than full-wave ([arXiv 2106.10693](https://arxiv.org/abs/2106.10693)). A journal snippet says 10,000× | [P]/[S] |
| DevFormer / DPP (ICML 2023) | Decap placement; >30% fewer components; `decap_sim(probe, solution, keep_out)`; RL4CO envs; used by ReEvo for LLM-discovered heuristics | [P] |
| SI eye-metric surrogates | NNs win with lots of data, anisotropic GPR with little; amortized neural optimization: ~10% optimality loss for 10³–10⁴× speedups | [P] |
| Crosstalk | MLP time-domain; LS-SVM worst-case under tolerances | [S] |
| EMI / thermal | Only a 2003 near-to-far-field paper; no maintained layout-level surrogate. A vendor claims 100–1000× speedups without support | [S]/[V] |

## Open questions

- No published wall-clock data exists for kicad-cli DRC vs board size, padne/KiPI solves, or a full DDR-net gerber2ems slice. Measure them in-project. The harness has started: DRC exceeded 900 s on 4 of 297 boards ([harness.md](harness.md)), so a per-move T1 router probe is plausible only on small boards [I].
- Validation of KiPI, Ki-PIDA, padne and SPIKE beyond the authors' caveats is undocumented.
- Thermal-ML and EMI-ML surrogate searches were incomplete (search budget exhausted).

## Sources

- [constraints_verification_benchmarks.md § Q2, Q6B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- corrections: [verification_kicad_and_tools.md § 2.9, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- See also [../kicad/specctra-freerouting-integration.md](../kicad/specctra-freerouting-integration.md).
