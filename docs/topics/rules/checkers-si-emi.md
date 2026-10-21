# SI/EMI checkers: KiCad-native vs custom (A–I) vs simulation, and existing open-source checkers

*Tags: [P] primary/code read, [S] snippet, [V] unverified project claim, [I] inference.*

**TL;DR**
- **Use native KiCad first.**
  - KiCad 9/10 check width, gap, clearance, uncoupled length, skew, length, via count, edge clearance and angle.
  - KiCad 10 adds ps-domain delay (per-layer and via delay), `fromTo()` pad-to-pad paths, and backdrill modelling.
  - KiCad master (unreleased) adds `return_path`, `stub_length`, net chains and a via-stitch generator.
- **Nine custom checkers cover what is not native.** Build them in this order:
  1. B: return-path continuity.
  2. C: reference changes.
  3. H: via stubs.
  4. F: connector between-ness.
  5. E: crosstalk.
  6. G: stitching.
  7. I: protection topology, islands, edge rate.
  8. D: loop ranking.
  
  All of them depend on A, the reference-layer map built from the stackup plus zone fills.
- **Code licence is GPL-3.0-or-later.** Code from MIT (kicad-happy, EMI Guardian, kipy), 0BSD-style (emcvisual) and GPL-3.0 (RF-tools-KiCAD, KiCad itself) projects can be reused directly. The unlicensed `return_path` checker and the non-commercial EMC Auditor are **references for their algorithms only**.
- **KiCad 10 IPC cannot create persistent custom DRC markers.** Report findings through an HTML/JSON overlay, and use IPC selection and zoom to point at them.
- **Rank findings by consequence** (estimated V_cm, far-field share, risk score), not by count. Johnson: good EMI tools are "more like expert systems than simulators".

## Key facts

### KiCad native capability
- **KiCad 9/10 constraints:** `track_width`, `clearance`, `diff_pair_gap`, `diff_pair_uncoupled`, `skew`, `length`, `via_count`, `edge_clearance`, `track_angle`, `track_segment_length`, `assertion`, `hole_size`, `annular_width`, `hole_to_hole`, `silk_clearance`, `courtyard_clearance`, `text_height`/`text_thickness`, `physical_clearance`, `via_diameter`, `disallow`.
  - `skew` is measured against the longest net; add `within_diff_pairs` to check each pair separately.
  - `length` also sets the tuner's target length.
  - Conditions: `hasNetclass`, `inDiffPair`, `isCoupledDiffPair`, `intersectsArea`, `intersectsCourtyard`, `memberOfSheet(OrChildren)` (from 9.0.2).
  - KiCad 10 adds `fromTo('U1-A*','U2-B*')`.
  - Sources: [KiCad 9](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html); [KiCad 10](https://docs.kicad.org/10.0/en/pcbnew/pcbnew_advanced.html) [P].
- **KiCad 10 time domain.**
  - Delay = Σ(length × per-layer unit delay) + via delay (stackup height × via unit delay, with per-layer-pair overrides) + pad-to-die delay.
  - Tuning profiles hold targets in ps. KiCad recommends them for DDR, PCIe and USB, even on a single layer.
  - ps and mm cannot be mixed within one constraint.
  - Backdrill can be set on vias and pads, from one or both sides, with a "must-cut" layer.
  - Source: [docs](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html) [P].
- **KiCad master keywords:** `return_path`, `stub_length`, `net_chain_length`, `hole_aspect_ratio`, `microvia_stack_depth`, `net` ([keywords](https://gitlab.com/kicad/code/kicad/-/raw/master/common/drc_rules.keywords) [P]).
  - **`(constraint return_path (layer "B.Cu") (net "GND"))`** works like this:
    1. Union the zone fills on the reference layer.
    2. Subtract that union from each track or arc polygon of the net chain.
    3. Report what remains as "no copper return path".
    4. Merge the flagged pieces with union-find.
    
    It checks one explicit layer only. It does not consider vias, detours, edge proximity or reference changes.
  - **Net chains** bridge across series components (`BoardChainBridging`). Their topology gives the trunk and each stub (branch point, length, delay), and `stub_length` works in the time domain.
  - **`PCB_VIA_STITCH`** offers STITCH and GUARD modes with PLAIN, STAGGERED and POISSON layouts. The default pitch is max(2 mm, 2× via diameter). It is exposed over IPC as `ViaStitchGuardSettings`, and a DRC check catches overlapping stitch zones.
  - Final syntax may change before KiCad 11. Whether rule conditions will see `A.NetChain` is unknown.
- **IPC Python API (kipy, MIT).**
  - Useful calls: `Board.get_stackup()`, `get_zones()`, `refill_zones()`, `get_pad_shapes_as_polygons()`, `hit_test()`, `Zone.filled_polygons`.
  - The SWIG bindings do not expose the stackup, so it has to be parsed from `.kicad_pcb`.

### Custom checker specifications ([HS] §11 synthesis [I]; each step cites its physics in [si-fundamentals.md](si-fundamentals.md) / [emc-placement.md](emc-placement.md))
| ID | Checker | Algorithm |
|---|---|---|
| A | Reference-layer map | 1. Read the stackup (IPC or `.kicad_pcb`). 2. For each signal layer, record both neighbours, h_up/h_down, and whether each is filled with GND or a declared reference net. 3. Take the nearer filled layer as the reference; for stripline keep both (about 75% returns on the nearer). 4. Refill zones first. Lints Ott's objective 1 |
| B | Return continuity | Fast path: master `return_path`. Full path: 1. Sample each segment against a net-labelled raster or polygon map. 2. Compute the geodesic detour from entry to exit (A* on the raster, or a visibility graph). 3. Classify as VOID, ISLAND or SPLIT. **Merge antipads and clearances into voids first** (Ott's slot data). Buffer by 1.5W or w/2 + 3h; severity scales with t_r and detour/h |
| C | Reference change | 1. At each via or PTH pad, find the layers actually used (track ends within the pad radius, SMD pads hit). 2. Map them to reference sets; an unchanged set is OK (Ott case 2). 3. Same net on different planes: report the nearest via spanning both; extra loop ≈ d × plane separation; threshold ≤200 mil, preferably 1–2 mm, scaled by data rate. 4. Different nets: find the capacitor that minimises the pos→padA→padB loop, warn of 5–10 nH, and recommend re-layering |
| D | Loop area | A = Σ length·h + plan-view detour area (shoelace) + Σ d_via·Δz. Screen with Ott's E = 2.632×10⁻¹⁴f²AI/r at harmonics up to the knee, I = V/Z0. **For ranking only**, since the cable common-mode path dominates |
| E | Crosstalk | 1. Spatially hash the segments. 2. Pair segments within ≤5° of parallel, with D = s + (w1+w2)/2; include broadside pairs on adjacent layers. 3. K = 1/(1+(D/H)²) × min(1, 2T/t_r); add microstrip FEXT ∝ L/t_r. 4. Per victim, sum the two nearest aggressors plus the next two. Use stricter budgets for I/O and analog victims. EMI Guardian's (h/s)² × overlap/critical-length is a cruder proxy |
| F | Connector clustering and "between" | 1. Each cabled connector's reference point is the centroid of its GND/shield pins. 2. Score whether they fit one edge band or corner quadrant (maximum pairwise distance, angular spread). 3. For each fast net and connector pair, classify the sides, then run MREMC: L_ret → V_cm → E_max. 4. Flag E_max within 6 dB of the limit (emcvisual), or V_cm >1 mV (100 µV for strict limits). Use as both a placement cost and a post-route check |
| G | Stitching and fences | 1. Clip the GND vias spanning a plane pair to the overlap of both fills. 2. Find the **largest empty circle** (farthest Voronoi vertex), with diameter d_max. 3. Require cavity resonance c/(2√εr·d_max) > f_knee; for apertures or fences, require d_max ≤ λ/20. 4. Prefer distributed vias. For GUARD fences, check the maximum gap along the offset polyline (the KiCad master generator can create the fence) |
| H | Via stubs | 1. Take z-depths from the stackup. 2. Use the drilled span minus any backdrill, and the used span from attached tracks. 3. Stub = plated barrel beyond the used span + pad rings + unremoved NFPs. 4. f_res = c/(4·stub·√εr); flag if > min(15 mil, 0.3/Gbps), or if f_res < 3× Nyquist. Shares the stackup model with KiCad 10's via delay |
| I | Other checks | I/O corridor ("no unrelated trace between connector and device"); TVS/filter/CMC nearer the connector than the IC, with a short GND via; floating copper and metal islands; clock edge/period <10%; series R near the driver; running skew |
| IF | Interface-pack geometry | Path order with zero vias; offset-polygon GND coverage; no T-junctions or test points; distance windows and annuli; plane-edge offset (or a shrunken keep-in rule area); loop polygon → L estimate → overshoot L·dI/dt (warn above 0.2·Vds_max); trace capacitance (crystal, I2C C_b); AC cap near either endpoint; edge-finger keep-outs |

**Simulation backend (S):** loss budgets (Σ length × dB/in + allowances), DDR IBIS PVT, termination current (Archambeault), guard traces (3-D), and width/gap field solves. The MREMC estimate serves as a pre-screen.

### Encodability matrix
| Rule family | KiCad 9/10 | KiCad master | External |
|---|---|---|---|
| Width/gap per layer for Z0 | native `(layer …)` | same | S: field solve |
| Pair/bus skew; DDR segments | native (ps, `fromTo`) | same | — |
| Length/delay across series parts | partial | `net_chain_length` | — |
| Uncoupled length, vias, edge, angles | native | native | — |
| Return path on one layer | — | `return_path` | G: automatic layer choice, buffers, detours |
| Reference change → via or cap | — | — | G (C) |
| Loop area | — | — | G (D) |
| Trace stubs | — | `stub_length` | G for plain nets |
| Via stubs | backdrill model only | — | G (H) |
| Crosstalk coupled length | clearance only | — | G (E) |
| Connector clustering / between | — | — | G (F) |
| Stitching / fence pitch | — | generator only | G (G) |
| Protection topology; plane-edge offsets | rule areas, partly | — | G (I) |

### Existing open-source checkers (read from code)
| Project | Licence → reuse under GPL-3.0+ | What it checks |
|---|---|---|
| [aklofas/kicad-happy](https://github.com/aklofas/kicad-happy/blob/main/emc-precompliance.md) | MIT → **reusable** | An agent skill (Claude Code/Codex) running on analyser JSON, with 44 rule IDs in 18 categories: ground-plane voids; transitions without a GND via; trace near edge (< h); stitching (√(area/count) vs λ/20 at 3× the highest crystal frequency); outer-layer "3H" crosstalk (≥5 mm coupled); skew→CM; ESD path; connector filtering and ground-pin ratio; cavity; switching harmonics; PDN. Outputs a 0–100 risk score (≤3 findings per rule), band prioritisation, interface risk ranking, and XY near-field probe points |
| [hap231/kicad-emi-guardian](https://github.com/hap231/kicad-emi-guardian) | MIT → **reusable** | KiCad ≥10.0.5 IPC plugin. Checks: plane gaps and detours; return vias within 2 mm; parallel coupling (≤5°, ≥5 mm overlap, ≤0.5 mm gap, uniform-grid hash); edge 1 mm; pair mismatch 1 mm; acute corners <75°; dangling stubs ≥0.8 mm; long nets by route diameter (1/6); GND-pour appendage antennas (≤1500 MHz); stitching planner. Dry-run only, no persistent markers |
| [tombueng/emcvisual](https://github.com/tombueng/emcvisual) | 0BSD-style → **reusable** | Browser TypeScript; reads KiCad 6–10, IPC-2581, ODB++ and Eagle. Quasi-static Biot–Savart near field with image currents. About 30 rules, each with threshold, origin and test board: return-gap (≥0.2 mm gap, detour ≥2 mm); ref-change; no-stitching (3 mm); edge-trace (<3h, ≥1 mm, over ≥3 mm); cable-cm; io-coupling; long-line (no ≥10 Ω series R within 15 mm); filters >10 mm; ESD diode placement; crystal; hot loop 30–40 mm². Orders findings by far-field share. Its full-wave comparison claim is unreviewed [V] |
| [easyw/RF-tools-KiCAD](https://github.com/easyw/RF-tools-KiCAD) | GPL-3.0 → **reusable directly** | Via-fence generator (pyclipper offsets), with links to via-stitching and teardrop scripts |
| KiCad / kipy | GPL-3.0+ / MIT → reusable | `return_path`, `stub_length` and via-stitch generator code (master) |
| [jasonarnoldarnie/kicad-tools `return_path`](https://github.com/jasonarnoldarnie/kicad-tools) | **No licence → algorithm reference only** | KiCad 10 SWIG + numpy. Reference = nearest filled layer by dielectric thickness. Samples every 0.1 mm against a 0.05 mm raster. Flags: VOID (A* detour; FAIL >1.0 mm), ISLAND, SPLIT, TERMINAL, VIA (same-net stitching via FAIL >2.0 mm; different-net capacitor FAIL >5.0 mm), EDGE (w/2 + 3h). Loop area = length·h + detour area + via distance × plane spacing. HTML glow 1/(1+(x/h)²) out to ±3h. `return_path_classes.json` overrides net-name classes. Plane copper only, no spreading model |
| [RolandWa/KiCAD_Custom_DRC](https://github.com/RolandWa/KiCAD_Custom_DRC) "EMC Auditor" | **Non-commercial proprietary → reference only** | TOML rules: GND via within 2 mm of critical vias; decap within 3 mm; plane continuity sampled every 0.5 mm in a 1 mm band; plane and board edge distance; 3W; connector filter topology; IEC 60664-1 creepage |
| rjwalters/kicad-tools | not checked | Protocol-aware pair rules emitting native `diff_pair_gap`, uncoupled, `skew` and `via_count` [S] |

### Commercial references
- **HyperLynx DRC EMI rules** (parameterised): edge rate/period, edge shield, exposed length, filter placement, ICs over a split, I/O coupling, metal island, net crossing a gap, net near a plane edge, reference-plane change, via stub ([whitepaper](https://schematicsforfree.com/files/Manufacturing%20and%20Design/PC%20Board%20Design%20and%20Fabrication/PCB%20Design,%20Layout%20&%20Routing/USING%20HYPERLYNX%20DRC%20TO%20FIND%20EMI%20ISSUES.pdf) [P]).
- **Other tools:** NEC EMISTREAM; IBM EMSAT (Archambeault; "hundreds of man-years" [S]); Zuken CR-8000 EMC Adviser EX.
- **How these tools classify nets:** manual entry, net-name substrings, a component database, or IBIS/simulation data. Names alone "can not provide detailed information" ([LearnEMC](https://learnemc.com/commercial-emc-rule-checkers) [P]).
- **Clemson:** source/path/antenna combinations are computer-identifiable from layout plus component data [S].

## Recommendations for our system
- **Constraint emission.** Generate native constraints wherever possible:
  - KiCad 10: ps profiles, `fromTo`, `diff_pair_uncoupled`, `via_count`, per-layer `edge_clearance` ≥2–3h;
  - KiCad master: `return_path (layer <ref>) (net GND*)` per net chain and layer, plus `stub_length`.
  
  Tag each emitted rule with `rule_id`, `source_url` and provenance.
- **Python checker suite.** Implement A–I against IPC data (stackup and fills), in the priority order above. kicad-happy, EMI Guardian, emcvisual and RF-tools can be forked or vendored. The `return_path` checker and EMC Auditor are reimplemented from their algorithm descriptions only.
- **Reporting.** Show findings in an HTML/JSON overlay with IPC selection and zoom.
- **Net classification.** Combine regex seeds, LLM confirmation from pin function and datasheet, and user overrides (in the style of `return_path_classes.json`).
- **Closing the loop.** Add these checkers to the agent's generate → route → check loop. No public tool does this.

## Conflicts and open questions
- **Unreleased features.** KiCad master's `return_path` and net chains are unreleased, and their syntax may change.
- **Accuracy.** None of the open-source checkers has been benchmarked against measurement or full-wave results.
- **API stability.** IPC stability across 10.x and 11 was not verified.

## Sources
- Research notes:
  - [rules_highspeed_emi.md § 11, 12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md)
  - [interface_rule_packs.md § 11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)
- KiCad source (GitLab master): drc_rule_parser.cpp, drc_test_provider_matched_length.cpp, pcb_via_stitch.cpp.

See also:
- [si-fundamentals.md](si-fundamentals.md)
- [emc-placement.md](emc-placement.md)
- [rule-pack-format.md](rule-pack-format.md)
- [../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)
- [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md)
