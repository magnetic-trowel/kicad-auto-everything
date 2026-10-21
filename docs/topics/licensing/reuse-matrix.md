# Reuse matrix for third-party code (our code is GPL-3.0-or-later)

**TL;DR**
- **Code is GPL-3.0-or-later** ([LICENSING.md](../../../LICENSING.md)). We may **import, vendor, fork, port and link** GPL-3.0(-only/-or-later), GPL-2.0-or-later, LGPL, MPL-2.0, Apache-2.0, MIT, BSD, ISC, Zlib, BSL-1.0 and PSF code in-process, keeping notices [P/I].
  - That covers Freerouting, fastroute, KiCad's PNS router and DRC (incl. PCBWorld-Engine), SWIG `pcbnew`, kiutils, the POA MCP server (all versions), CGAL and openEMS bindings, Horizon and LibrePCB.
- **Do not combine:** GPL-2.0-only code, non-commercial or unlicensed code, Shewchuk's Triangle, OptiMathSAT, or bundled Gurobi.
- **AGPL-3.0 (Konnect) is reference only by default.** GPLv3 §13 allows combining, but the AGPL network clause then reaches our HTTP MCP server [P].
- **Including GPL-3.0-only code** (e.g. Freerouting) makes that *combined* distribution GPL-3.0. Our own files keep "or later" [I].
- **Earlier notes flagged several items for a permissive or MPL core.** Those flips are **reversed**: vendoring or forking Freerouting, adopting PCBWorld-Engine, using kiutils, and porting KiCad's transform code are all allowed again [I].

## Key facts
Action key:
- **IN**: may vendor, modify, port or link in-process, keeping notices.
- **DEP**: fine as a dependency.
- **PROC**: run as a separate process anyway, for technical reasons such as crash isolation, Java, or a cloud service.
- **REF**: patterns only.
- **AVOID**.

Licenses were verified from LICENSE files by the licensing survey, 2026-10-20 [P].

### KiCad and its interfaces
| Component | License | Action | Notes |
|---|---|---|---|
| KiCad C++ (PNS router, DRC engine, `trigo`, footprint transforms) | GPLv3+ ([LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README)) | IN | Porting or linking is fine; keep KiCad copyright headers |
| IPC `.proto` files | GPL-3.0-or-later headers | IN | We may vendor them and generate bindings in any language. The kipy issue #134 wrinkle doesn't affect us |
| kicad-python (kipy) 0.8.0 | MIT (relicensed 2025-02-02) | DEP | One stray GPL header (issue #134), irrelevant to us |
| SWIG `pcbnew` | GPLv3+ | IN, technically PROC | Licence-compatible; removed in KiCad 11, segfault-prone, so keep it in a helper process ([../kicad/kipy-and-swig-bindings.md](../kicad/kipy-and-swig-bindings.md)) |
| kicad-cli | GPLv3+ | PROC | Outputs (Gerbers, DRC reports, upgraded boards) are not covered by KiCad's GPL ([GPLOutput](https://www.gnu.org/licenses/gpl-faq.html#GPLOutput)) |
| PCBWorld-Engine | GPLv3 | IN | Linkable in-process now; the socket boundary is optional, for crash isolation |
| PCBWorld environment/bench | BSD-3 (+Notice.md) | IN | |
| KiCad libraries (symbols, footprints, 3D) | CC-BY-SA-4.0 WITH KiCad-libraries-exception | data | See [data-rulepacks-weights.md](data-rulepacks-weights.md) |
| KiCad demo projects | CC BY-SA 4.0 | data/fixtures | One-way compatible with GPLv3 ([FSF](https://www.gnu.org/licenses/license-list.html#ccbysa)) |

### Routers, placers, agents, MCP servers
| Component | License | Action | Notes |
|---|---|---|---|
| Freerouting (Java) | GPL-3.0 (no "or later" notice found); npm MCP package GPL-3.0-only | IN / PROC | Vendoring, forking or JVM bridging is allowed; the combination is distributed under GPL-3.0. Pass `-da` (analytics). Provenance is cloudy, so don't upstream Freerouting-derived code into KiCad |
| freerouting-client 2.3.0 | MIT | DEP | |
| fastroute | GPL-3.0-or-later | IN | Rust Freerouting derivative |
| EasyEDA local router | GPL-3.0 | IN | Freerouting fork |
| route-rnd | GPL-2+ (bundled libs PD, LGPL-2.1+, BSD-3) | IN | "or later" makes it GPLv3-compatible |
| Horizon EDA (embeds KiCad router 6.0.4), LibrePCB | GPL-3.0 | IN | |
| tangency-labs/pcbcraft | GPL-3.0 | IN | |
| Place By Sch (PCM) | GPL-3.0 | IN | |
| vygr C-PCB family | GPL-2.0 | AVOID (unless "or later" is confirmed) | Stale anyway |
| ReplicateLayout, Place Footprints (Mitja Nemec) | GPL-2.0, "or later" unverified | AVOID until verified | KiCad now has Repeat Layout natively |
| KiCadRoutingTools, kicad-tools, kicad-happy, OrthoRoute, Fanout Tool, HierarchicalPCB, Layout Clone | MIT | IN | |
| SubLayout | BSD-3 | IN | |
| Parts Placer | LGPL-2.1 | IN | |
| tscircuit / capacity-autorouter | MIT | IN | TypeScript: port or subprocess |
| Topola | MIT (crate MIT OR Apache-2.0) | IN | |
| Cypress | Apache-2.0 | IN | Keep NOTICE; Apache-2.0 is compatible with GPLv3 one-way |
| DREAMPlace, SA-PCB, PcbRouter, ALIGN, MAGICAL, OpenROAD | BSD-3 | IN | |
| RL_PCB, HierPlace v1.1.0, morningfire-pcb-automation | MIT | IN | |
| mixelpixx/KiCAD-MCP-Server | MIT (depends on kicad-skip, LGPL) | IN | Freerouting wrapper, transforms, prompts |
| kicad-mcp-pro | MIT | IN | Placement scorer weights, evals, golden corpus |
| ProductOfAmerica/mcp-server-kicad | GPL-3.0-or-later since 2026-10-14; MIT ≤0.20.1 (bump 511a50d, 2026-08-15) | IN (all versions) | Byte-preserving CST `_cst.py` (round-trips 15,711/15,711 files), orientation helpers, October transform fixes (b588906, cf501c7, 2d4a55f, fff4209), `tests/kicad_ref` ports, `pcbnew_judge`. **Avoid the MIT-era `_transform_local_to_board`** (textbook-rotation bug) |
| mixelpixx/Konnect | AGPL-3.0 + CLA + commercial | REF | Its MIT portions (CPL rotation table, scoring weights, calculator formulas, release-gate lattice from PRO; DSN syntax from Topola) can be taken from the originals |
| lamaalrajih/kicad-mcp, Diode `pcb`, KiKit, InteractiveHtmlBom, SKiDL, atopile, WebCola | MIT | IN | |
| salitronic/eda-agent, copperhead, DeepPCB plugin, IntelligentElectron/universal-netlist | Apache-2.0 | IN | DeepPCB routing is a cloud service under its own terms |
| Backplane | MIT (ships a KiCad fork, so those parts are GPL) | IN | |
| Seeed-Studio/kicad-mcp-server | README says MIT; no LICENSE file | REF until a file exists | |
| Zane456/PCB-Agent-Teams | "Noncommercial" | AVOID | |
| diodeinc/dsn | no license shown | AVOID | |
| MCP SDKs (`mcp`, `@modelcontextprotocol/sdk`, pynng MIT; fastmcp Apache-2.0; protobuf BSD-3) | permissive | DEP | |

### File tooling, solvers, geometry, simulation
| Component | License | Action |
|---|---|---|
| kiutils | GPL-3.0 | IN, but stale for KiCad 9/10 formats (last PyPI 2024-02-02) |
| kicad-skip | LGPL-2.1+ | IN |
| OR-Tools, SCIP, pymoo | Apache-2.0 | IN |
| HiGHS, Z3, pyribs, Optuna, BoTorch, PySCIPOpt | MIT | IN |
| SMAC3, pycma | BSD-3 | IN |
| PyTorch, JAX, NetworkX, rustworkx | permissive | DEP |
| DEAP | LGPL-3.0 | IN |
| Gurobi (`gurobipy` 13.0.3) | Proprietary | Optional user-installed backend only; never bundle |
| OptiMathSAT | Research and evaluation only | AVOID |
| Shapely (BSD-3) + GEOS (LGPL-2.1) | – | DEP (ship LGPL notice and source with binaries) |
| rtree / libspatialindex (MIT since 1.8.0), Clipper2 / pyclipr (BSL-1.0), sparrow (MIT) | permissive | IN |
| PythonCDT / CDT, jagua-rs | MPL-2.0 | IN (MPL §3.3 secondary-license combination) |
| Shewchuk Triangle (Python wrapper LGPL-3.0) | Upstream bars commercial distribution without arrangement | AVOID; use PythonCDT |
| CGAL (GPL/LGPL-3.0+), `cgal` Python | GPLv3+ | IN |
| openEMS (GPL-3.0-or-later Python) / CSXCAD (LGPL-3.0) | – | IN |
| gerber2ems | Apache-2.0 | IN |
| scikit-rf | BSD-3 | IN |
| PySpice | GPLv3 | IN |
| Elmer FEM | GPL-2.0-or-later | IN |
| ngspice | Mixed per file | Check per component |
| Adaptagrams | LGPL-2.1+ | IN |
| ELK / elkjs | EPL-2.0 OR GPL-3.0-or-later | IN (take it under GPL) |
| azonenberg/pcb-checklist | BSD-3 | IN (quote with notice) |

## Recommendations for our system
- **Let technical merit, not licence, decide in-process versus subprocess** for GPL engines. Keep crash-prone or JVM pieces (SWIG, Freerouting, PCBWorld-Engine) in helper processes for isolation [I].
- **Konnect stays reference-only.** Reimplement its patterns (reliability contract, DRC sync, plan revisions) instead [I].
- **Carry notices.** Keep upstream copyright headers when porting KiCad or Freerouting code, mark modified files, and generate `THIRD_PARTY_NOTICES.md` ([compliance-checklist.md](compliance-checklist.md)) [I].
- **Freerouting is GPL-3.0-only:** document that releases bundling it are GPL-3.0 as a whole [I].
- **Re-verify licenses each release.** Examples of drift: kipy GPL→MIT, libspatialindex LGPL→MIT, POA MIT→GPL, Topola's crate versus repo [P].

## Conflicts and open questions
- Freerouting's Java codebase has no "or later" notice; only GPL-3.0 text and an npm `GPL-3.0-only`.
- ReplicateLayout and PlaceFootprints: is it GPL-2.0-only or "or later"? Unverified.
- The ngspice per-component license map was not built.
- Is the Konnect fixture (Antmicro Kria K26) Apache-2.0? Quoted from a commit message only.

## Sources
- research notes:
  - [licensing.md § 1, § 2, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md) (written for an Apache/MPL core; re-assessed here for GPL)
  - [kicad_mcp_codebases.md § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
  - [existing_tools_and_apis.md § 4 Inferences, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- primary: [GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html), [FSF license list](https://www.gnu.org/licenses/license-list.html), [MPL-2.0](https://www.mozilla.org/en-US/MPL/2.0/)

See also: [kicad-and-gpl-ecosystem-notes.md](kicad-and-gpl-ecosystem-notes.md), [data-rulepacks-weights.md](data-rulepacks-weights.md), [compliance-checklist.md](compliance-checklist.md)
