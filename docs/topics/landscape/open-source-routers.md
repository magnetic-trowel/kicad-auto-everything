# Landscape: open-source routers usable with KiCad

**TL;DR**
- **Freerouting** (GPL-3.0, v2.5.0, 2026-10-05) is the strongest open bulk router. In PCBWorld it scored clean-pass 0.80 / 0.78 (v2.1.0), and its own suite rose from 30.9% to 75.0% clean in v2.5.0. It has REST, MCP and KiCad 10 IPC [P].
- **KiCad's push-and-shove (PNS) router can run headlessly via LG's PCBWorld-Engine** (GPLv3, pybind11 over a socket, KiCad 9.0.8, 58 APIs). That is the engine-grounded interactive primitive LLM agents need. Horizon EDA also embeds PNS [P].
- **KiCadRoutingTools** (MIT; Rust A*, diff pairs, length/time matching, fanout, plane repair; 10 skills) and **kicad-tools** (MIT) are agent-oriented and file-based. Neither does push-and-shove [P].
- **Others:** fastroute (a Rust Freerouting port, ~4× faster), tscircuit's capacity-mesh router (MIT, TypeScript), OrthoRoute (GPU, backplanes only), Topola (topological, work in progress), route-rnd (GPL-2+) [P].
- With GPL-3.0-or-later code, **all of these except GPL-2.0-only ones can be vendored or linked**. See [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md) [I].

## Key facts
| Router | License | Status | Mechanism and features | Limits |
|---|---|---|---|---|
| **Freerouting** | GPL-3.0 (npm MCP: GPL-3.0-only) | ~2.1k★; v2.1.0 2025-04-12 (sole maintainer stepped back); v2.2.x Apr–May 2026; v2.3.0 08-07; v2.4.1 09-03; **v2.5.0 10-05** | Specctra DSN→SES; fanout pre-pass (`BatchFanout`), rip-up passes, deterministic post-route optimizer, pour and plane awareness (2.5); REST, MCP, A2A; KiCad 10 IPC; GraalVM native binaries; `V2_CONTINUOUS`/`V2_LOWER_BOUND` scores | Multi-threaded optimization "broken"; misses KiCad board-edge clearance on export; leaves 1–7 nets on dense boards per run. Integration and pitfalls: [../kicad/specctra-freerouting-integration.md](../kicad/specctra-freerouting-integration.md) [P] |
| **fastroute** | GPL-3.0-or-later ("a derivative work of Freerouting") | 107★, created 2026-09-29 | Rust port with bug fixes, length matching, controlled impedance, diff pairs; KiCad plugin carrying `.kicad_dru` rules; `--parity` gives byte-identical SES to Freerouting's deterministic mode on all 20 boards; `--live` view; fixes the optimizer never running after a self-stop and traces ignoring the outline for edge pads | Self-reported, 20 boards: 2,102 s (Freerouting) → 510 s → 420 s with PGO; memory 1–2 GB → 20–300 MB [P] ([README](https://github.com/parisxmas/fastroute)) |
| **PCBWorld-Engine** (LG AI Research) | GPLv3 ("because it links KiCad") | 5★, created 2026-08-29; built on KiCad 9.0.8 + kipy 0.6.0 | KiCad PNS via pybind11 over a unix socket. **58 APIs**: 14 reproduce `PNS::ROUTER`, 28 wrap KiCad DRC and board-state extraction, 16 utilities. `fix_route`, `cancel_route`, `finish` (to the nearest unconnected pad), `flip_posture`, `toggle_via`/`switch_layer`, `set_routing_mode` (mark_as_obstacles/push_n_shove/walkaround), `set_corner_mode` (45°/90°); per-netclass widths and vias pushed on net selection | **Copper pours not in PNS space**; pinned to 9.0.8; research codebase [P] ([repo](https://github.com/LGAI-Research/PCBWorld-Engine); [paper](https://arxiv.org/html/2607.05915)) |
| **Horizon EDA** | GPL-3.0 | 1,324★, pushed 2026-10-04 | Embeds KiCad's PNS sources (`pns_router`, `pns_shove`, `pns_walkaround`, `pns_diff_pair_placer`, `pns_meander_placer`, `pns_optimizer`, `pns_topology`…; README: "KiCad router 6.0.4") | Autorouter is a **non-goal** ("rarely useful for small to medium-sized boards") [P] |
| **KiCadRoutingTools** (drandyhaas) | MIT ("stays that way — there is no paid tier") | 549★, ~5,856 commits, created 2025-12-13; README v0.15.x; PCM 0.22.1 (SWIG, KiCad ≥9) | Grid-based octilinear multi-layer A* with a Rust core (~10× faster than Python); rip-up and reroute; diff pairs by pose-based A* with a Dubins heuristic; length and **time** matching; plane pours and repair; BGA/QFN fanout; bus routing; placement optimization; "design brief", graded floorplan intent, KiCad-oracle reconnect; DRC and connectivity checkers; plugin GUI for 9/10; 10 skills (corrected, VK) | "No push-and-shove", no blind or buried vias, no coarse grid assignment, no region-based rules. Self-reported: 47/47 FTDI nets in 8.6 s; 28/28 LVDS pairs in 29.7 s [P] ([repo](https://github.com/drandyhaas/KiCadRoutingTools)) |
| **kicad-tools** (rjwalters) | MIT | 70★, ~6.9k commits, PyPI 0.24.0 (2026-10-20) | File-based A* "with trace optimization" (optional C++ backend, "10-100x A* speedup"); `kct route-auto` multi-strategy; extras `[cuda]`, `[metal]`, `[native]`, `[placement]`, `[mcp]` | Self-report: KRT is faster and completes more on sparse and medium boards. TraceMaker ≈0.99/1.00/0.90 vs Freerouting 2.2.4 ≈0.7/0.7/0.2 (single 60 s runs; corrected, VK) [P] |
| **tscircuit capacity-autorouter** | MIT | npm 0.0.995 (2026-10-20) | "Hundreds of algorithms organized in a Pipeline"; "successive approximation and hypergraphs instead of sequential routing" (`CapacityMeshSolver`); `AutoroutingPipelineSolver(simpleRouteJson)` with a `step()` loop; SimpleRouteJson has `buses[].maxLengthSkew` and diff pairs with `lengthTolerance` | TypeScript; "hard to steer" [S]; benchmarks on SRJ33 (37 DRC-failure inputs) and a dashboard [P] ([repo](https://github.com/tscircuit/tscircuit-autorouter)) |
| **OrthoRoute** | MIT | v1.0.0, KiCad ≥10 IPC; PCM | Manhattan lattice + PathFinder negotiated congestion with a CUDA 12/CuPy or Apple Metal SSSP kernel; nets sequential, parallelism inside SSSP | "Not a general-purpose PCB autorouter"; "useful to about five people on the planet"; PCBWorld CP ≈0.02 [P] |
| **Fanout Tool** | MIT | 1.0.0, KiCad ≥10 IPC; PCM | QFN/QFP/BGA escape with "3-segment routing algorithms" | – [P] |
| **Topola** | MIT (crate MIT OR Apache-2.0) | v0.1.0, 33★, updated 2026-08-09; **codeberg.org/topola/topola** (corrected, VK); NLnet NGI0 Entrust | "Work-in-progress interactive topological router"; crates `specctra-core`, `topola-cli`, `topola-egui`, `planar-incr-embed` | WIP [P] |
| **route-rnd** (Ringdove/pcb-rnd) | GPL-2+ (bundled libs PD, LGPL-2.1+, BSD-3) | Debian 0.9.3 (files 2016–2021); NLnet support | External router over tEDAx; `rt_topo` (libgrbs "generalized rubber band sketch", CRBS/TRBS), `rt_horver`, `rt_hace` | Convex-only crbs leaves "unnecessary curves", some rats go "around far away obstacles in long detours"; horver needs pins on a grid (preferably ≥100 mil) [P] |
| **EasyEDA local router** | GPL-3.0 | v0.8.11 | Headless Freerouting fork over WebSocket (`ws://127.0.0.1:3579/router`), DSN in, JSON out | – [P] |
| **vygr C-PCB / JS / Python / Go-PCB** | GPL-2.0 | stale (last push 2024-02) | grid routers | GPL-2.0 [P] |
| **Ruby-PCB-Router**; **gEDA Toporouter** | – | 2016; 2008 (Anthony Blake, after Tal Dayan's 1997 rubber-band thesis) | topological rubber band | Historical. Wikipedia's claim that it was adapted for KiCad is dubious [P] |
| **SA-PCB, PcbRouter** (OpenROAD project) | BSD-3 | – | academic | – [P] (licensing.md) |

**KiCad itself** ships no autorouter. Its PNS "Attempt Finish Selected" is reachable via `RunAction` ([../kicad/built-in-automation-features.md](../kicad/built-in-automation-features.md)). **LibrePCB** (GPL-3.0; 2.0.0 2026-01-28, 2.1.1 2026-06-12) has no router, but has DSN export and SES import since 1.2.0 (2024-12-01) [P].

**Freerouting KiCad plugin:** PCM version 2.4.1 ("KiCad 6.0 or newer", Tools → External Plugins, waits for the app to exit, then loads the routed design), which lags upstream. Its SWIG support "will be removed in the next release" [P].

**Commercial DSN/SES back ends** (Allegro PCB Router, Konekt Electra, TopoR, Altium Situs, PCB Auto Router) are covered in [commercial-incumbents-and-startups.md](commercial-incumbents-and-startups.md).

## Recommendations for our system
- **Bulk routing:** Freerouting 2.5, supervised as in [../kicad/specctra-freerouting-integration.md](../kicad/specctra-freerouting-integration.md). Evaluate fastroute as a faster drop-in [I].
- **Critical nets and repair:** PCBWorld-Engine, linkable in-process under our GPL license, or kept behind its socket for crash isolation. Budget a port to KiCad 10/11 and upstreaming. Pours need separate handling [I].
- **Specialized jobs:** KRT for fanout, diff pairs, plane repair and time matching. Use tscircuit's capacity mesh as a design reference for fast congestion estimates that can feed placement [I].
- **Keep DSN/SES first-class** for user-supplied commercial routers [I].
- **Re-run PCBWorld-Bench with current versions** (Freerouting 2.5, fastroute, kicad-tools, tscircuit), not the paper's 2.1.0 [I]. See [measured-tool-comparisons.md](measured-tool-comparisons.md).
- Routing *algorithms* (A*, PathFinder, topological, push-and-shove internals) belong to the `routing/` area.

## Conflicts and open questions
- PCBWorld-Engine has not been tested on KiCad 10/11, and its throughput and stability at scale are unknown.
- route-rnd development after 0.9.3 is unknown (repo.hu was unreachable).
- Freerouting Docker arm/v7: the README lists it, but the v2.2.2 notes say it was dropped.

## Sources
- research notes:
  - [existing_tools_and_apis.md § 3, § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [verification_kicad_and_tools.md § 1 (#20, #23–27, #31, #45–46), § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [licensing.md § 1B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: [Freerouting releases](https://github.com/freerouting/freerouting/releases), [Horizon router](https://github.com/horizon-eda/horizon/tree/master/3rd_party/router/router), [route-rnd README (Debian)](https://sources.debian.org/src/route-rnd/0.9.3-1/README/), [Topola Codeberg](https://codeberg.org/topola/topola), [OrthoRoute](https://github.com/bbenchoff/OrthoRoute)

See also: [open-source-placers.md](open-source-placers.md), [measured-tool-comparisons.md](measured-tool-comparisons.md), [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md)
