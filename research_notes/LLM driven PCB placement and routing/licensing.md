# Licensing landscape and strategy for an open-source, LLM-driven KiCad placement and routing project

> **Not legal advice.** These are research notes from public primary sources: license files, FSF/GNU, ASF, OSI, Creative Commons, CERN, the US Copyright Office, KiCad docs, and statements by KiCad lead developers. They are meant to inform a decision. Have counsel review before relying on anything here, especially the patent, dataset, and model-weight sections. Licenses were checked on 2026-10-20 by fetching the actual LICENSE/COPYING files (raw.githubusercontent.com, gitlab.com, codeberg.org), PyPI/npm/crates.io/Hugging Face metadata APIs, and the cited web pages.
>
> **Context.** `magnetic-trowel/kicad-auto-everything` currently contains a plain GPL-3.0 `LICENSE` (no "only"/"or later" notice), a two-line README, and research notes. Git history shows one human commit (the owner's "Initial commit") and Claude-authored research-note commits, with no third-party contributors (`git shortlog -sne`, run locally 2026-10-20).
>
> **Method note.** Research notes in this folder were grepped for every tool, library, dataset, and model mentioned. The WebSearch budget ran out partway through, so later facts come from direct fetches of primary URLs only. Some pages could not be retrieved: Google Patents (blocked), OpenAI's terms page (JavaScript-only), and some arXiv pages. These are listed under Gaps.

---

## 1. Inventory: verified licenses of every surveyed component, and what each means if we (a) import/link, (b) call it as a subprocess, socket, or HTTP service, (c) vendor or modify it, (d) redistribute it bundled

### Takeaway
Most of the surveyed stack is permissive: MIT, BSD, Apache-2.0, Boost. That stack fits any license we choose. The strong-copyleft pieces are KiCad itself (C++/SWIG), Freerouting and its port fastroute, PCBWorld-Engine, kiutils, CGAL's Python bindings, openEMS's Python bindings, PySpice, and Elmer. Konnect is AGPL. All of these can be used by a permissive project if they stay behind a process boundary (CLI, socket, HTTP, or KiCad's IPC API) and are never linked in-process. Four things must not be bundled at all: Gurobi, Shewchuk's Triangle, OptiMathSAT, and unlicensed or NC/ND data. Several popular "open" PCB datasets put a single blanket license (MIT or CC-BY-4.0) over boards whose upstream licenses are mixed or missing.

### Legend for columns (a)–(d)
The legend assumes **our code is permissive (e.g., Apache-2.0)**. If our core stayed GPL-3.0-or-later, the GPL-combo rows become free to absorb. See the note after the tables.
- **OK+N**: allowed. Keep the copyright and license notice (Apache-2.0 also requires carrying NOTICE and marking changed files).
- **Sep**: separate program. Communication over exec, pipes, sockets, or command-line arguments "normally" means separate programs. Our license is unaffected. We only take on the component's license terms if we ship the component itself. [GPL FAQ: MereAggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)
- **GPL-combo**: the distributed combination must be GPL-3.0 as a whole. Our own files may keep a GPL-compatible permissive license, but nobody can distribute the combination as proprietary. [GPL FAQ: IfLibraryIsGPL](https://www.gnu.org/licenses/gpl-faq.html#IfLibraryIsGPL)
- **File-CL**: file-level copyleft (MPL-2.0/EPL-2.0). Modified files of the component stay under its license, with source available. Larger works can use any license.
- **LGPL**: unmodified dynamic use is fine. Modifications to the library stay LGPL. If we ship the library binary we must also ship its source. Static linking requires relinkable object files. [GPL FAQ: LGPLStaticVsDynamic](https://www.gnu.org/licenses/gpl-faq.html#LGPLStaticVsDynamic)
- **AGPL**: GPL-combo plus an obligation to offer source to users who interact over a network.
- **✗**: do not redistribute or bundle (non-free or restricted terms).

### Cited Findings

**A. KiCad itself and its interfaces**

| Component | Verified license | Copyleft | Patent grant | (a) import/link | (b) subprocess/socket/HTTP | (c) vendor/modify | (d) redistribute bundled |
|---|---|---|---|---|---|---|---|
| KiCad (C++ core) | "The majority of KiCad's source code is developed and distributed under the terms of the GPLv3 or later". Third-party code inside includes Apache-2.0, Boost, ISC, MIT, BSD, MPL-2.0 (Eigen), LGPL, and CC0. "A combined works as is will be governed under the terms of the GPLv3 (or later)". [LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README); [kicad.org licenses](https://www.kicad.org/about/licenses/) | Strong | Express (GPL-3.0 §11) | GPL-combo | Sep | GPL (porting counts as modification) | Aggregate: ship license and source/offer |
| KiCad demo projects (`demos/*`) | CC BY-SA 4.0 [LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README) | Share-alike | None | n/a | n/a | SA applies to adaptations | CC BY-SA, with attribution |
| KiCad docs | GPL-3.0-or-later **or** CC-BY-3.0-or-later (dual) [kicad.org licenses](https://www.kicad.org/about/licenses/) | Strong (if GPL chosen) | n/a | n/a | n/a | Pick either license | Either |
| KiCad libraries (symbols, footprints, 3D, templates) | CC-BY-SA-4.0 with the KiCad exception: "the copyright holder waives article 3 of the license with respect to these designs and any generated files". Redistributing "the KiCad libraries, or parts thereof… as a collection" is **not** covered by the exception. [kicad.org/libraries/license](https://www.kicad.org/libraries/license/); identical text in [kicad-footprints](https://gitlab.com/kicad/libraries/kicad-footprints/-/blob/master/LICENSE.md), [kicad-symbols](https://gitlab.com/kicad/libraries/kicad-symbols/-/blob/master/LICENSE.md), [kicad-packages3D](https://gitlab.com/kicad/libraries/kicad-packages3D/-/blob/master/LICENSE.md). The SPDX id `KiCad-libraries-exception` exists (SPDX list 3.29.0) [SPDX](https://spdx.org/licenses/KiCad-libraries-exception.html). Article 3 of CC BY-SA 4.0 contains **both** Attribution and ShareAlike [CC BY-SA 4.0 legalcode](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en) | SA, collection-level only | None | Used inside designs: no obligations | n/a | Extracted or modified footprint *libraries* stay CC-BY-SA-4.0 WITH exception | Library collections: CC-BY-SA with attribution and license files |
| IPC API `.proto` definitions (`api/proto/**`) | File headers read "GNU General Public License… either version 3 of the License, or (at your option) any later version" (e.g., [envelope.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/envelope.proto)) | Strong (on the files) | GPL-3.0 §11 | Generated bindings: **ambiguous** (see §2) | Speaking the protocol at runtime: Sep | Vendoring the `.proto` files puts GPL files in our repo | Prefer depending on kipy over shipping our own generated code |
| kicad-python (`kipy`) 0.8.0 | MIT ("Copyright The KiCad Developers") [LICENSE](https://gitlab.com/kicad/code/kicad-python/-/blob/main/LICENSE); PyPI `license_expression: MIT` [PyPI](https://pypi.org/pypi/kicad-python/json). Relicensed from GPLv3 to MIT in commit 7b8a97f7 (2025-02-02) [commit](https://gitlab.com/kicad/code/kicad-python/-/commit/7b8a97f7c073e50ca25787ef53ef0a6ee83c54dd) | Permissive | None express | OK+N | n/a | OK+N | OK+N. One stray GPL header remains in `kipy/proto/common/types/__init__.py` ([issue #134](https://gitlab.com/kicad/code/kicad-python/-/work_items/134), open) |
| kicad-cli | Part of KiCad: GPL-3.0-or-later [LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README) | Strong | §11 | n/a | Sep. Outputs (Gerbers, DRC reports, upgraded boards) are not covered [GPL FAQ: GPLOutput](https://www.gnu.org/licenses/gpl-faq.html#GPLOutput) | n/a | Aggregate |
| Legacy SWIG `pcbnew` Python bindings | Part of KiCad: GPL-3.0-or-later. "Deprecated as of KiCad 9.0… The current plan is to remove the SWIG bindings in KiCad 11.0" [dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/) | Strong | §11 | GPL-combo: the plugin must be "GPL or compatible licensed" ([Seth Hillbrand, KiCad lead dev](https://forum.kicad.info/t/process-to-integrate-a-tool-plugin-in-kicad-distribution/62462/5)) | A helper process that imports pcbnew is itself GPL-combo; our main program talking to it over a socket is Sep ([PCBWorld-Engine](https://github.com/LGAI-Research/PCBWorld-Engine)) | GPL | GPL for the combo |
| KiCad PNS push-and-shove router via PCBWorld-Engine | GPL-3.0, "because it links KiCad". The environment "never" combines with it "into one distributable" [PCBWorld-Engine README](https://github.com/LGAI-Research/PCBWorld-Engine) | Strong | §11 | GPL-combo | Sep (unix socket, primitives only) | GPL | Keep separate |

**B. Routers, placers, agents, MCP servers**

| Component | Verified license | Copyleft | Patent | (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|---|---|
| Freerouting | GPL-3.0 text [LICENSE](https://github.com/freerouting/freerouting/blob/HEAD/LICENSE). The MCP npm package is `GPL-3.0-only` [npm](https://www.npmjs.com/package/@freerouting/freerouting-mcp-server). CLI, REST (`api.freerouting.app/v1`), and MCP are documented [README](https://github.com/freerouting/freerouting). `-da` "Disables the collection of anonymous analytics data" [CLI docs](https://github.com/freerouting/freerouting/blob/master/docs/command_line_arguments.md) | Strong | §11 | GPL-combo (JVM in-process, subclassing: [GPL FAQ: OOPLang](https://www.gnu.org/licenses/gpl-faq.html#OOPLang)) | Sep (CLI/REST/MCP) | GPL, regardless of how much code is replaced ([Seth Hillbrand](https://forum.kicad.info/t/freerouting-modernization/69547/42)) | Aggregate: license plus corresponding source |
| freerouting-client (Python) 2.3.0 | MIT [PyPI](https://pypi.org/pypi/freerouting-client/json) | Permissive | None | OK+N | — | OK+N | OK+N |
| fastroute | GPL-3.0-or-later. "fastroute is a derivative work of Freerouting" [README](https://github.com/parisxmas/fastroute); [LICENSE](https://github.com/parisxmas/fastroute/blob/HEAD/LICENSE) | Strong | §11 | GPL-combo (Rust linking) | Sep | GPL | Aggregate |
| KiCadRoutingTools | MIT [LICENSE](https://github.com/drandyhaas/KiCadRoutingTools/blob/HEAD/LICENSE); "free and MIT-licensed, and it stays that way" [README](https://github.com/drandyhaas/KiCadRoutingTools) | Permissive | None | OK+N | OK | OK+N | OK+N |
| kicad-happy | MIT [LICENSE](https://github.com/aklofas/kicad-happy/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| kicad-tools (rjwalters) | MIT [LICENSE](https://github.com/rjwalters/kicad-tools/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| mixelpixx/KiCAD-MCP-Server | MIT [LICENSE](https://github.com/mixelpixx/KiCAD-MCP-Server/blob/HEAD/LICENSE) (depends on kicad-skip, which is LGPL) | Permissive | None | OK+N | OK | OK+N | OK+N |
| mixelpixx/Konnect | AGPL-3.0, "commercial licenses are available" [LICENSE](https://github.com/mixelpixx/Konnect/blob/HEAD/LICENSE); [README](https://github.com/mixelpixx/Konnect) | Network copyleft | §11 (AGPL) | AGPL | Sep if the user runs it as their own MCP server | AGPL, including §13 network source offer | Aggregate: source required |
| lamaalrajih/kicad-mcp | MIT [LICENSE](https://github.com/lamaalrajih/kicad-mcp/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| Seeed-Studio/kicad-mcp-server | README says "MIT", but no LICENSE/COPYING file was found in 13 candidate filenames [README](https://github.com/Seeed-Studio/kicad-mcp-server) | Unclear | None | Treat as MIT-by-README; ask for a LICENSE file | OK | Caution | Caution |
| salitronic/eda-agent | Apache-2.0 [LICENSE](https://github.com/salitronic/eda-agent/blob/HEAD/LICENSE) | Permissive | Express | OK+N | OK | OK+N | OK+N |
| DeepPCB KiCad plugin | Apache-2.0 [LICENSE](https://github.com/instadeepai/deeppcb-kicad-plugin/blob/HEAD/LICENSE). Routing itself is a closed cloud service | Permissive | Express | OK+N | Cloud ToS apply | OK+N | OK+N |
| tscircuit / capacity-autorouter | MIT [tscircuit LICENSE](https://github.com/tscircuit/tscircuit/blob/HEAD/LICENSE); [autorouter LICENSE](https://github.com/tscircuit/tscircuit-autorouter/blob/HEAD/LICENSE) ("An MIT-licensed PCB autorouter") | Permissive | None | OK+N | OK | OK+N | OK+N |
| Topola | MIT. `REUSE.toml`/`Cargo.toml` on the `develop` branch carry `SPDX-License-Identifier: MIT`, assets are `CC-BY-4.0 OR MIT`, and `LICENSES/` holds Apache-2.0, CC-BY-4.0 and MIT [Codeberg](https://codeberg.org/topola/topola). The crates.io 0.1.0 release says `MIT OR Apache-2.0` [crates.io](https://crates.io/crates/topola) | Permissive | None (MIT) | OK+N | OK | OK+N | OK+N |
| OrthoRoute | MIT [LICENSE](https://github.com/bbenchoff/OrthoRoute/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| PCBWorld (environment and benchmark code) | BSD-3-Clause; "the engine is GPLv3" [LICENSE](https://github.com/LGAI-Research/PCBWorld/blob/HEAD/LICENSE); [README](https://github.com/LGAI-Research/PCBWorld) | Permissive | None | OK+N | OK | OK+N | OK+N, plus its Notice.md |
| RL_PCB | MIT [LICENSE](https://github.com/LukeVassallo/RL_PCB/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| DREAMPlace | BSD-3-Clause [LICENSE](https://github.com/limbo018/DREAMPlace/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| Cypress (NVlabs) | Apache-2.0 [LICENSE](https://github.com/NVlabs/Cypress/blob/HEAD/LICENSE) | Permissive | Express | OK+N | OK | OK+N | OK+N |
| ALIGN | BSD-3-Clause [LICENSE](https://github.com/ALIGN-analoglayout/ALIGN-public/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| MAGICAL | BSD-3-Clause [LICENSE](https://github.com/magical-eda/MAGICAL/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| SA-PCB, PcbRouter (OpenROAD project) | BSD-3-Clause [SA-PCB](https://github.com/The-OpenROAD-Project/SA-PCB/blob/HEAD/LICENSE); [PcbRouter](https://github.com/The-OpenROAD-Project/PcbRouter/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| ReplicateLayout (reference only) | GPL-2.0 text [LICENSE](https://github.com/MitjaNemec/ReplicateLayout/blob/HEAD/LICENSE); whether "or later" applies was not verified | Strong | None express | Incompatible with GPL-3.0/Apache unless "or later" | Sep | Avoid | Avoid |

**C. Solvers and optimizers**

| Component | Verified license | Copyleft | Patent | (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|---|---|
| OR-Tools | Apache-2.0 [LICENSE](https://github.com/google/or-tools/blob/HEAD/LICENSE); PyPI "Apache 2.0" [PyPI](https://pypi.org/pypi/ortools/json) | Permissive | Express | OK+N | OK | OK+N | OK+N |
| HiGHS | MIT [LICENSE.txt](https://github.com/ERGO-Code/HiGHS/blob/HEAD/LICENSE.txt); `highspy` MIT [PyPI](https://pypi.org/pypi/highspy/json) | Permissive | None | OK+N | OK | OK+N | OK+N |
| SCIP / PySCIPOpt | SCIP Apache-2.0 [LICENSE](https://github.com/scipopt/scip/blob/HEAD/LICENSE); PySCIPOpt MIT [PyPI](https://pypi.org/pypi/pyscipopt/json) | Permissive | Express (SCIP) | OK+N | OK | OK+N | OK+N |
| Z3 | MIT [LICENSE.txt](https://github.com/Z3Prover/z3/blob/HEAD/LICENSE.txt) | Permissive | None | OK+N | OK | OK+N | OK+N |
| Gurobi (`gurobipy` 13.0.3) | "Proprietary" [PyPI](https://pypi.org/pypi/gurobipy/json) | Proprietary | — | Optional user-installed backend only | OK if the user installs it | ✗ | ✗ |
| OptiMathSAT | "research and evaluation purposes only" (per existing notes) [solver_toolbox.md](solver_toolbox.md) | Proprietary | — | ✗ | ✗ | ✗ | ✗ |
| pymoo | Apache-2.0 [LICENSE](https://github.com/anyoptimization/pymoo/blob/HEAD/LICENSE) | Permissive | Express | OK+N | OK | OK+N | OK+N |
| pyribs (`ribs`) | MIT [LICENSE](https://github.com/icaros-usc/pyribs/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| Optuna | MIT [LICENSE](https://github.com/optuna/optuna/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| BoTorch | MIT [LICENSE](https://github.com/pytorch/botorch/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| SMAC3 | BSD-3-Clause [LICENSE.txt](https://github.com/automl/SMAC3/blob/HEAD/LICENSE.txt) | Permissive | None | OK+N | OK | OK+N | OK+N |
| DEAP | LGPL-3.0 [LICENSE.txt](https://github.com/DEAP/deap/blob/HEAD/LICENSE.txt); PyPI "LGPL" [PyPI](https://pypi.org/pypi/deap/json) | Weak (library) | Express (via GPLv3) | LGPL (pure Python import is OK) | OK | LGPL | Ship source of DEAP if bundled |
| pycma (`cma`) | BSD-3-Clause [LICENSE](https://github.com/CMA-ES/pycma/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| PyTorch / JAX | PyTorch: `Apache-2.0 AND … BSD-3-Clause AND BSL-1.0 AND MIT` [PyPI](https://pypi.org/pypi/torch/json); JAX: Apache-2.0 [PyPI](https://pypi.org/pypi/jax/json) | Permissive | Express | OK+N | OK | OK+N | OK+N |
| NetworkX / rustworkx | BSD-3-Clause / Apache-2.0 [PyPI networkx](https://pypi.org/pypi/networkx/json); [PyPI rustworkx](https://pypi.org/pypi/rustworkx/json) | Permissive | — / Express | OK+N | OK | OK+N | OK+N |

**D. Geometry**

| Component | Verified license | Copyleft | Patent | (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|---|---|
| Shapely 2.2.0 + GEOS | Shapely BSD-3-Clause [LICENSE.txt](https://github.com/shapely/shapely/blob/HEAD/LICENSE.txt). "GEOS is available under the terms of GNU Lesser General Public License (LGPL) 2.1" [Shapely README](https://github.com/shapely/shapely/blob/HEAD/README.rst); [GEOS COPYING](https://github.com/libgeos/geos/blob/HEAD/COPYING) | Permissive + LGPL-2.1 lib | None express | OK (dynamic) | OK | Changes to GEOS stay LGPL | If we ship wheels (Docker or frozen app): GEOS LGPL notice plus source |
| rtree / libspatialindex | rtree MIT [LICENSE.txt](https://github.com/Toblerity/rtree/blob/HEAD/LICENSE.txt). libspatialindex "changed from a LGPL to a MIT license as of the 1.8.0 release" [COPYING](https://github.com/libspatialindex/libspatialindex/blob/HEAD/COPYING) | Permissive | None | OK+N | OK | OK+N | OK+N |
| Clipper2 / pyclipr | Boost Software License 1.0 [Clipper2](https://github.com/AngusJohnson/Clipper2/blob/HEAD/LICENSE); [pyclipr](https://github.com/drlukeparry/pyclipr/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| PythonCDT / CDT | MPL-2.0 [PythonCDT](https://github.com/artem-ogre/PythonCDT/blob/HEAD/LICENSE); [CDT](https://github.com/artem-ogre/CDT/blob/HEAD/LICENSE). PyPI: `MPL-2.0 AND BSD-3-Clause AND Apache-2.0 WITH LLVM-exception` [PyPI](https://pypi.org/pypi/PythonCDT/json) | Weak (file) | Express (MPL §2.1b) | OK | OK | File-CL | OK+N, with source of MPL files |
| `triangle` (Python) / Shewchuk Triangle | Wrapper LGPL-3.0 [LICENSE](https://github.com/drufat/triangle/blob/HEAD/LICENSE). Upstream: "freely redistributed under the condition that… no compensation is received… Distribution of this code as part of a commercial system is permissible ONLY BY DIRECT ARRANGEMENT WITH THE AUTHOR" [Triangle README](https://github.com/libigl/triangle/blob/HEAD/README) | Non-free upstream | — | ✗ (avoid) | ✗ | ✗ | ✗ |
| CGAL / `cgal` Python | Library files are "either the GNU General Public License or the GNU Lesser General Public License… version 3… or… any later version", and commercial licenses are available [Installation/LICENSE](https://github.com/CGAL/cgal/blob/HEAD/Installation/LICENSE). The Python bindings are GPLv3+ [PyPI](https://pypi.org/pypi/cgal/json) | Strong (for bindings) | §11 | GPL-combo | Sep | GPL | Aggregate |
| jagua-rs / sparrow | jagua-rs MPL-2.0 [LICENSE](https://github.com/JeroenGar/jagua-rs/blob/HEAD/LICENSE); [crates.io](https://crates.io/crates/jagua-rs). sparrow MIT [LICENSE](https://github.com/JeroenGar/sparrow/blob/HEAD/LICENSE) | Weak (file) / Permissive | Express (MPL) / None | OK | OK | File-CL / OK+N | OK+N |

**E. Simulation and RF**

| Component | Verified license | Copyleft | Patent | (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|---|---|
| openEMS | GPL-3.0 [COPYING](https://github.com/thliebig/openEMS/blob/HEAD/COPYING). Python package `LICENSE = "GPL-3.0-or-later"` [python/setup.py](https://github.com/thliebig/openEMS/blob/HEAD/python/setup.py). CSXCAD is LGPL-3.0 [COPYING](https://github.com/thliebig/CSXCAD/blob/HEAD/COPYING) | Strong | §11 | GPL-combo (`import openEMS`) | Sep | GPL | Aggregate |
| gerber2ems | Apache-2.0 [LICENSE](https://github.com/antmicro/gerber2ems/blob/HEAD/LICENSE). Its pyproject does not list openEMS, which is installed separately [pyproject](https://github.com/antmicro/gerber2ems/blob/HEAD/pyproject.toml) | Permissive | Express | OK+N (but it drives openEMS) | Sep (recommended) | OK+N | OK+N |
| scikit-rf | BSD-3-Clause [LICENSE.txt](https://github.com/scikit-rf/scikit-rf/blob/HEAD/LICENSE.txt) | Permissive | None | OK+N | OK | OK+N | OK+N |
| ngspice | Mixed. The original Berkeley code is "modified BSD". "Each piece of code should be kept under its original contributor's license". "GPL is not suitable for code to be directly linked into ngspice, but may be used in shared object libraries only" [COPYING](https://github.com/ngspice/ngspice/blob/HEAD/COPYING) | Mixed | Mixed | Check components | Sep | Per file | Per file |
| PySpice | GPLv3 [PyPI](https://pypi.org/pypi/PySpice/json) | Strong | §11 | GPL-combo | — | GPL | — |
| Elmer FEM | GPL-2.0-or-later (ElmerGUI has an OpenCASCADE exception) [LICENSE.md](https://github.com/ElmerCSC/elmerfem/blob/HEAD/LICENSE.md) | Strong | None express | GPL-combo (via "or later") | Sep | GPL | Aggregate |

**F. KiCad file tooling, code-first EDA, graph layout**

| Component | Verified license | Copyleft | Patent | (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|---|---|
| KiKit | MIT [LICENCE](https://github.com/yaqwsx/KiKit/blob/HEAD/LICENCE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| InteractiveHtmlBom | MIT [LICENSE](https://github.com/openscopeproject/InteractiveHtmlBom/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| **kiutils** | **GPL-3.0** [LICENSE](https://github.com/mvnmgrx/kiutils/blob/HEAD/LICENSE); PyPI classifier "GPLv3" [PyPI](https://pypi.org/pypi/kiutils/json) | Strong | §11 | **GPL-combo** | Sep | GPL | Aggregate |
| kicad-skip | LGPL-2.1 [LICENSE](https://github.com/psychogenic/kicad-skip/blob/HEAD/LICENSE); PyPI "LGPLv2 or later" [PyPI](https://pypi.org/pypi/kicad-skip/json) | Weak (library) | None express | LGPL (Python import OK) | OK | LGPL | Ship source if bundled |
| SKiDL | MIT [LICENSE](https://github.com/devbisme/skidl/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| atopile | MIT [LICENSE](https://github.com/atopile/atopile/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| WebCola | MIT [LICENSE](https://github.com/tgdwyer/WebCola/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| Adaptagrams (libavoid, libcola, libdialect/HOLA) | LGPL-2.1-or-later ("version 2.1 of the License, or (at your option) any later version"), with commercial dual licensing "for a fee" [cola/COPYING](https://github.com/mjwybrow/adaptagrams/blob/HEAD/cola/COPYING); [libavoid.h](https://github.com/mjwybrow/adaptagrams/blob/HEAD/cola/libavoid/libavoid.h) | Weak (library) | None express | LGPL (C++: dynamic linking preferred) | OK | LGPL | Ship source |
| ELK / elkjs | EPL-2.0, with GPL-3.0-or-later designated as a Secondary License: "SPDX-License-Identifier: EPL-2.0 OR GPL-3.0-or-later" [ELK NOTICE.md](https://github.com/eclipse/elk/blob/HEAD/NOTICE.md); elkjs `package.json` "EPL-2.0 OR GPL-3.0-or-later" [elkjs](https://github.com/kieler/elkjs/blob/HEAD/package.json) | Weak (file) | Express (EPL §2b) | OK | OK | File-CL | OK+N |
| Horizon EDA (reference) | GPL-3.0 [LICENSE](https://github.com/horizon-eda/horizon/blob/HEAD/LICENSE). It embeds "KiCad router 6.0.4… GPLv3" in `3rd_party/router` [README](https://github.com/horizon-eda/horizon) | Strong | §11 | GPL-combo | Sep | GPL | Aggregate |
| LibrePCB (reference) | GPL-3.0 [LICENSE.txt](https://github.com/LibrePCB/LibrePCB/blob/HEAD/LICENSE.txt); README "published under the GNU GPLv3" [README](https://github.com/LibrePCB/LibrePCB) | Strong | §11 | GPL-combo | Sep | GPL | Aggregate |
| OpenROAD (reference) | BSD-3-Clause [LICENSE](https://github.com/The-OpenROAD-Project/OpenROAD/blob/HEAD/LICENSE) | Permissive | None | OK+N | OK | OK+N | OK+N |
| azonenberg/pcb-checklist | BSD-3-Clause [LICENSE](https://github.com/azonenberg/pcb-checklist/blob/HEAD/LICENSE) | Permissive | None | OK+N (quote with notice) | — | OK+N | OK+N |
| MCP SDKs | `mcp` (Python) MIT [PyPI](https://pypi.org/pypi/mcp/json); `fastmcp` Apache-2.0 [PyPI](https://pypi.org/pypi/fastmcp/json); `@modelcontextprotocol/sdk` MIT [npm](https://www.npmjs.com/package/@modelcontextprotocol/sdk); `pynng` MIT [PyPI](https://pypi.org/pypi/pynng/json); `protobuf` BSD-3 [PyPI](https://pypi.org/pypi/protobuf/json) | Permissive | — | OK+N | OK | OK+N | OK+N |

**G. Benchmarks and datasets**

| Component | Verified license | Copyleft | Patent | (a)/(c) use or modify | (d) redistribute |
|---|---|---|---|---|---|
| PCBench (PCBench/PCBench) | Repo LICENSE is MIT [LICENSE](https://github.com/PCBench/PCBench/blob/HEAD/LICENSE). The README describes "164 printed circuit boards" [README](https://github.com/PCBench/PCBench), but `master_metadata.json` lists **1,194 designs from 846 repos**, retrieved 2023-08 [metadata](https://github.com/PCBench/PCBench/blob/HEAD/PCBs/master_metadata.json). Per-board upstream licenses (my tally of that file, by board): **none/not found 648 (54.3%)**, MIT 147 (12.3%), GPL-3.0 106 (8.9%), "Other" 96 (8.0%), Apache-2.0 38, GPL unspecified 33, GPL-2.0 20, CC-BY-SA 18, CERN-OHL 18, BSD 16, CC unspecified 15, CC-BY 11, LGPL 6, WTFPL 5, CC0 5, Unlicense 5, AGPL 4, MPL-2.0 2, TAPR 1. By unique repo: 449/846 (53.1%) have no license | Mixed (repo-level MIT cannot relicense the boards) | — | Code: OK+N. Boards: per-board license applies | Per-board filtering only. kicad-tools records it as "MIT repository, **mixed per-board licenses** — boards are cache-only" [kicad-tools](https://github.com/rjwalters/kicad-tools/blob/HEAD/benchmarks/external/README.md) |
| PCBWorld D3 split | Built by "collect[ing] the PCBench boards" at run time via `prepare_pcbench.sh`, rather than shipping them [PCBWorld README](https://github.com/LGAI-Research/PCBWorld) | Inherits PCBench | — | Fetch and prep locally | Do not redistribute boards |
| Freerouting PCBench integration | Expects a local clone of PCBench. Converted DSNs and caches are gitignored [scripts/pcbench/README](https://github.com/freerouting/freerouting/blob/master/scripts/pcbench/README.md) | — | — | Local only | — |
| bshada/open-schematics (HF) | Card says `license: cc-by-4.0`. Data was "collected from publicly available data from the web". Fields include `name` (source repo) but **no per-record upstream license field** [dataset card](https://huggingface.co/datasets/bshada/open-schematics). KiCad lead dev Seth Hillbrand: "Yet another 'open' dataset that merely strips the license and origin of thousands of people's projects… The vast majority require conveying the license and copyright with the data" [forum](https://forum.kicad.info/t/84-000-free-electronic-schematics/67938/2). kicad-tools disagrees and calls it "properly licensed" and "CC-BY-4.0" [recon](https://github.com/rjwalters/kicad-tools/blob/HEAD/docs/research/omnilayout-recon.md) | Contested | — | Use as a pointer to repos; re-check each upstream license | Do not re-host |
| OmniLayout / OmniRouting | "no licence grant of any kind" on data or code. Papers are CC BY-NC-ND 4.0 [kicad-tools recon](https://github.com/rjwalters/kicad-tools/blob/HEAD/docs/research/omnilayout-recon.md) | — | — | ✗ (metrics vocabulary only) | ✗ |
| Hzou9/PCBSchemaGen-Benchmarks | MIT per card [HF API](https://huggingface.co/datasets/Hzou9/PCBSchemaGen-Benchmarks) (provenance not audited) | — | — | Check provenance | Check provenance |
| AbijahKaj/kicad-netlist-sft-dataset | Apache-2.0 per card [HF](https://huggingface.co/datasets/AbijahKaj/kicad-netlist-sft-dataset) (provenance not audited) | — | — | Check provenance | Check provenance |
| commaai/PCBGolf | No LICENSE file found and no license statement in the README [repo](https://github.com/commaai/PCBGolf), so all rights are reserved by default [choosealicense: no permission](https://choosealicense.com/no-permission/) | — | — | Fetch-only demo target | ✗ |

**H. LLM / model weights mentioned in the notes**

| Model family | License (HF card) | FSF/OSI status | Constraints for a derived (fine-tuned) model |
|---|---|---|---|
| Qwen3 (8B/32B/235B-A22B), Qwen3.5 (0.8B–35B-A3B), Qwen3.6 (27B, 35B-A3B), Qwen3-Coder | apache-2.0 [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B); [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B); [Qwen3.5-35B-A3B](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) | OSI-approved license | Apache-2.0 notice and NOTICE only |
| Qwen2.5-7B-Instruct, Qwen2.5-VL-7B, Qwen2.5-Coder-32B | apache-2.0 [Qwen2.5-7B](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct); [Qwen2.5-VL-7B](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) | OSI | Same |
| Qwen2.5-72B, Qwen2.5-VL-72B | "qwen" license. Requires a license above "100 million monthly active users". Models trained with its outputs must "prominently display 'Built with Qwen' or 'Improved using Qwen'" [Qwen LICENSE](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct/blob/main/LICENSE) | Not OSI | Naming/attribution plus MAU cap |
| Llama 3 / 3.1 / 3.3 (e.g., Llama3-8B in notes) | llama3 / llama3.1 / llama3.3, gated [Meta-Llama-3-8B](https://huggingface.co/meta-llama/Meta-Llama-3-8B). Requires "Built with Llama". A trained model "shall also include 'Llama' at the beginning of any such AI model name". AUP incorporated; 700M MAU clause [Llama 3.1 LICENSE](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE) | FSF: "not a free software license" [FSF](https://www.gnu.org/licenses/license-list.html#Llama) | Cannot be released as Apache-2.0-only weights |
| Mistral-7B-Instruct-v0.3 | apache-2.0 [HF](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3) | OSI | Apache-2.0 |
| gpt-oss-20b / 120b | apache-2.0 [HF](https://huggingface.co/openai/gpt-oss-20b) | OSI | Apache-2.0 |
| DeepSeek-R1 | mit [HF](https://huggingface.co/deepseek-ai/DeepSeek-R1). DeepSeek-V3's card lists no license field [HF](https://huggingface.co/deepseek-ai/DeepSeek-V3) | OSI (R1) | MIT notice |
| Phi-4 | mit [HF](https://huggingface.co/microsoft/phi-4) | OSI | MIT notice |
| OLMo-2 | apache-2.0 [HF](https://huggingface.co/allenai/OLMo-2-1124-13B-Instruct) | OSI | Apache-2.0 |
| Gemma 3 | "gemma", gated [HF](https://huggingface.co/google/gemma-3-27b-it). "Model Derivatives" include models trained with "synthetic data Outputs by Gemma". Redistribution "must include the use restrictions" [Gemma Terms](https://ai.google.dev/gemma/terms) | Not OSI | Flow-down restrictions, covering distillation too |
| OpenRAIL family (BLOOM-RAIL, CreativeML OpenRAIL-M) | Derivatives "will always have to include – at minimum – the same use-based restrictions" [CreativeML OpenRAIL-M](https://github.com/CompVis/stable-diffusion/blob/main/LICENSE) | FSF: "nonfree licenses, because they deny freedom 0" [FSF RAIL](https://www.gnu.org/licenses/license-list.html#RAIL) | Flow-down use restrictions |

### Inferences
- Every core building block the earlier notes recommend has a permissive equivalent: kipy, OR-Tools, HiGHS, SCIP, Z3, pymoo, pyribs, Optuna, BoTorch, SMAC3, Shapely (plus the LGPL GEOS library), rtree, Clipper2, PythonCDT (MPL), DREAMPlace, Cypress, KiCadRoutingTools, tscircuit, Topola, OrthoRoute, and scikit-rf. So an Apache-2.0 core is technically feasible without giving up capability.
- The surprise item is **kiutils (GPL-3.0)**. Earlier notes treat it as a general S-expression utility. A permissive core that does `import kiutils` becomes GPL-combo on distribution. Alternatives: kicad-skip (LGPL-2.1+), our own parser, or kipy for live boards.
- The LGPL/MPL/EPL items (GEOS, DEAP, kicad-skip, adaptagrams, PythonCDT, jagua-rs, ELK, CSXCAD) are fine as unmodified dependencies. They need care only if we vendor and modify them, or if we statically link LGPL code into a Rust/C++ binary. A static link means we must provide relinkable objects ([GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html#LGPLStaticVsDynamic)).
- **If our core stayed GPL-3.0-or-later**, the GPL-combo rows (Freerouting, fastroute, kiutils, CGAL bindings, openEMS Python, PySpice, PCBWorld-Engine, KiCad C++/SWIG) could be absorbed freely. AGPL Konnect code could be combined under GPLv3 §13 but would bring the network clause with it. Still excluded either way: GPL-2.0-only code, Triangle, Gurobi, OptiMathSAT, and unlicensed or NC/ND data.

### Gaps
- Freerouting's LICENSE is the GPLv3 text, and the npm package says `GPL-3.0-only`. I found no "or later" notice for the Java codebase.
- ngspice's per-component license map (which parts are LGPL or GPL) was not built.
- The HiGHS "*-apache packages with HiPO" statement comes from the earlier notes ([solver_toolbox.md](solver_toolbox.md)), not re-verified here.
- The license of Qwen3.5-397B (mentioned in [llm_for_eda.md](llm_for_eda.md)) was not checked. Only Qwen3.5 models up to 35B-A3B were listed by the HF search.
- Provenance of the PCBSchemaGen and kicad-netlist-sft datasets was not audited.
- The PCBench per-board tally reflects GitHub's repo-level license detection at retrieval time (2023). It may describe the software license, not the hardware. "Other" usually means GitHub could not classify the text (often CC or CERN variants).

---

## 2. KiCad/GPL interaction: IPC API, SWIG plugins, kicad-cli, file outputs, Freerouting, AGPL

### Takeaway
KiCad's lead developers say on the record that **programs using the IPC API do not need to be GPL**, while distributed plugins that link KiCad's Python (SWIG) library must be "GPL or compatible licensed." The official IPC client, kicad-python, was deliberately relicensed MIT. The one wrinkle is that the IPC `.proto` files themselves carry GPL-3.0-or-later headers. Users' `.kicad_pcb` boards and kicad-cli outputs are not covered by KiCad's GPL, and library footprints embedded in designs are covered by the library exception. Freerouting is safe to call as a CLI/REST/MCP service. Porting or modifying its code, or KiCad's, produces GPL code. Freerouting's 2014 provenance is also murky. AGPL (Konnect) matters only if we copy its code. If we do, the network-source obligation attaches to our MCP server.

### Cited Findings
**IPC API (separate process, protobuf over NNG)**
- Seth Hillbrand ("one of the lead developers on the KiCad project") [profile](https://forum.kicad.info/u/Seth_h): "If you distribute a plug-in that links to the KiCad Python library, your code must be GPL or compatible licensed. If you use the new IPC plugin framework, it does not need to be." [forum, 2025-07-17](https://forum.kicad.info/t/process-to-integrate-a-tool-plugin-in-kicad-distribution/62462/5)
- Design: "Protocol Buffers to define the structure and contents of messages, and NNG to transport messages between processes using UNIX sockets… plugins and other applications act as clients". "Plugins developed for the IPC API are launched in standalone processes". "Third-party software that is not launched as a KiCad plugin can also communicate with any running KiCad instance" [IPC API docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)
- kicad-python was relicensed after a user pointed out that GPL kipy would "taint" plugins built with it. Jon Evans (craftyjon, "Member of the KiCad lead developer team" [profile](https://forum.kicad.info/u/craftyjon)): "we're discussing just relicensing this repo which would prevent the confusion" [issue #9](https://gitlab.com/kicad/code/kicad-python/-/work_items/9). The "Re-license under MIT" commit followed the same day [commit](https://gitlab.com/kicad/code/kicad-python/-/commit/7b8a97f7c073e50ca25787ef53ef0a6ee83c54dd). The README changelog lists "Relicense as MIT" [README](https://gitlab.com/kicad/code/kicad-python/-/blob/main/README.md)
- Open wrinkle: kipy "builds against the API definitions (`.proto` files) in the `kicad` submodule" [README](https://gitlab.com/kicad/code/kicad-python/-/blob/main/README.md). Those `.proto` files are headed GPL-3.0-or-later [envelope.proto](https://gitlab.com/kicad/code/kicad/-/blob/master/api/proto/common/envelope.proto). An issue reports that 11 of 17 generated `*_pb2.pyi` stubs in the 0.7.1 wheel reproduce the GPL header verbatim, and asks "what is the intended license of the generated protobuf artifacts". Jon Evans replied: "The intent is that this library is MIT, but upstream KiCad is GPL. In my opinion the generated sources shouldn't have a license header, but I'm not a lawyer. I'll look into it sometime." The issue is still open [issue #134](https://gitlab.com/kicad/code/kicad-python/-/work_items/134)
- FSF criterion: "pipes, sockets and command-line arguments are communication mechanisms normally used between two separate programs… But if the semantics of the communication are intimate enough, exchanging complex internal data structures, that too could be a basis to consider the two parts as combined" [GPL FAQ: MereAggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation); also [GPLPlugins](https://www.gnu.org/licenses/gpl-faq.html#GPLPlugins)
- The API surface is "stable following the best practices described by the Protocol Buffers team". Deprecated messages are supported "for at least one major version" [IPC API docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/)

**SWIG `pcbnew` in-process plugins**
- SWIG bindings are "deprecated as of KiCad 9.0… plan is to remove the SWIG bindings in KiCad 11.0". They are "a raw binding layer over KiCad rather than a true API" [dev-docs](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)
- FSF: when an interpreter provides "bindings" to GPL facilities, "the interpreted program is effectively linked to the facilities it uses through these bindings… must be released in a GPL-compatible way" [GPL FAQ: IfInterpreterIsGPL](https://www.gnu.org/licenses/gpl-faq.html#IfInterpreterIsGPL). Linked modules "may be under various GPL compatible licenses, but the work as a whole must be licensed under the GPL" [IfLibraryIsGPL](https://www.gnu.org/licenses/gpl-faq.html#IfLibraryIsGPL)
- Precedent: PCBWorld keeps its `pcbnew_prep` scripts on the GPL side "because they import KiCad's `pcbnew` Python module". The BSD environment talks to the engine over a socket, and "no wheel, no container image, no installer contains both" [PCBWorld-Engine README](https://github.com/LGAI-Research/PCBWorld-Engine)

**KiCad's official plugin repository (PCM)**
- "Packages containing code (Python plugins) must be licensed under an open-source license compatible with the GNU GPL". "Packages containing data (color themes, libraries, etc) should be licensed under a Creative Commons or similar license". "Closed-source packages may be used with KiCad under a third-party repository" [KiCad add-on docs](https://dev-docs.kicad.org/en/addons/)

**Users' boards and generated files**
- "copyright law does not give you any say in the use of the output people make from their data using your program… if my program is used to develop hardware designs" [GPL FAQ: GPLOutput](https://www.gnu.org/licenses/gpl-faq.html#GPLOutput); also [CanIUseGPLToolsForNF](https://www.gnu.org/licenses/gpl-faq.html#CanIUseGPLToolsForNF)
- Library data: "Use of the library data in a project does not (by itself) require that the design or any files generated from the design are licensed under the CC-BY-SA 4.0 License" [kicad.org](https://www.kicad.org/libraries/license/)
- Jon Evans on footprints extracted from boards: "If someone extracts the footprint from your design, that extracted footprint is no longer part of your design and the original KiCad license should apply". He confirmed the same reasoning for per-part 3D models [forum](https://forum.kicad.info/t/license-for-exported-footprints-from-pcb-file/32112/3), [#6](https://forum.kicad.info/t/license-for-exported-footprints-from-pcb-file/32112/6). "Symbols/footprints embedded within your design are part of your design. A project-local library that you distribute next to your design is not" [forum](https://forum.kicad.info/t/kicad-library-license-and-design-local-libraries/32114/3)

**Porting KiCad or Freerouting code**
- "translation of a work is considered a kind of modification… If the original program is licensed under certain versions of the GNU GPL, the translated program must be covered by the same versions" [GPL FAQ: TranslateCode](https://www.gnu.org/licenses/gpl-faq.html#TranslateCode)
- Seth Hillbrand (2026-10-19) on a project that ported KiCad's stroke font and text layout code (its author said the license text "was automatically made with AI"): "you don't have the right to re-license the work of others… you must license your code under the GPL" [forum](https://forum.kicad.info/t/kicad-fem-funding/72058/14)
- On a Freerouting rewrite: "your use of Freerouting as the base remains the controlling license regardless of how much code you replaced" [Seth Hillbrand](https://forum.kicad.info/t/freerouting-modernization/69547/42). "If you want to make a modern autorouter, you are welcome to do that and use whatever license you want… But you used other people's existing work" [#60](https://forum.kicad.info/t/freerouting-modernization/69547/60)
- fastroute self-identifies as "a derivative work of Freerouting (GPL-3.0)" and licenses itself GPL-3.0-or-later [README](https://github.com/parisxmas/fastroute)

**Freerouting provenance (unverified, community recollection)**
- A forum member says Freerouting's "legal status is unclear. There was accusations about stealing intellectual property… a derivative or a port of the current existing source code will not be accepted as a part of KiCad" (community member, not an official KiCad statement) [forum #7](https://forum.kicad.info/t/freerouting-modernization/69547/7). Another links 2014 EEVblog threads ("Creator was bullied by Zuken to take it down"; "project opensourced") and an archived post by Alfons Wirtz [#19](https://forum.kicad.info/t/freerouting-modernization/69547/19). The linked sources were not fetched.

**AGPL (Konnect) and network/MCP services**
- AGPL "interacting… remotely through a computer network" covers a program "expressly designed to accept user requests and send responses over a network" [GPL FAQ: AGPLv3InteractingRemotely](https://www.gnu.org/licenses/gpl-faq.html#AGPLv3InteractingRemotely). Modified AGPL software run as a service must offer source [UnreleasedModsAGPL](https://www.gnu.org/licenses/gpl-faq.html#UnreleasedModsAGPL). Under plain GPL, a company running a modified version on a website "does not have to release the modified sources" [UnreleasedMods](https://www.gnu.org/licenses/gpl-faq.html#UnreleasedMods)
- GPLv3 §13 lets GPLv3 code combine with AGPLv3 code, but "the special requirements of the GNU Affero General Public License, section 13, concerning interaction through a network will apply" to the combination [GPL-3.0 text](https://www.gnu.org/licenses/gpl-3.0.txt); [GPL FAQ: AGPLGPL](https://www.gnu.org/licenses/gpl-faq.html#AGPLGPL)
- Konnect's README: "If you're a business: the AGPL requires that anything you build on or around Konnect — including software provided over a network — be open-sourced under the same license" [README](https://github.com/mixelpixx/Konnect). This is the vendor's characterization. "Around" goes beyond the FSF's aggregation analysis for separate programs.
- Private and internal use of GPL code needs no source release: "an organization can make a modified version and use it internally without ever releasing it" [GPL FAQ: GPLRequireSourcePostedPublic](https://www.gnu.org/licenses/gpl-faq.html#GPLRequireSourcePostedPublic); [InternalDistribution](https://www.gnu.org/licenses/gpl-faq.html#InternalDistribution)

**Wrappers do not launder GPL code**
- Putting a permissive "wrapper" between proprietary code and GPL code is "legally irrelevant; what matters is the fact that module C is included in the whole" [GPL FAQ: GPLWrapper](https://www.gnu.org/licenses/gpl-faq.html#GPLWrapper)

### Inferences
- **IPC API path:** a permissive (Apache-2.0/MIT) program that talks to KiCad through kipy or its own NNG client is defensible on three grounds. The FSF treats sockets as separate programs. KiCad's lead developers have said publicly that IPC clients need not be GPL. And the KiCad Developers themselves license the client as MIT. Residual risk sits in the GPL headers on the `.proto` files. For a permissive project:
  - Depend on `kicad-python` from PyPI rather than vendoring `.proto` files.
  - If we need bindings in another language (e.g., Rust, as Konnect has), either generate them at build time from the user's KiCad checkout, or first get written clarification from KiCad. Commenting on [issue #134](https://gitlab.com/kicad/code/kicad-python/-/work_items/134) or asking for an explicit permissive notice on `api/proto` would both serve.
- **Plugin packaging:** IPC plugins we publish to the official PCM must carry a GPL-compatible license. Apache-2.0, MIT, BSD and MPL-2.0 all qualify. EPL-2.0 without a Secondary License designation would not.
- **SWIG:** avoid it in the core. It is deprecated, slated for removal in KiCad 11, and forces GPL-combo. If a headless KiCad 9/10 path needs `pcbnew`, put that adapter in a separately distributed GPL-3.0-or-later helper that talks over a socket (the PCBWorld pattern).
- **Freerouting:** call it only as a subprocess, REST, or MCP service. Pass `-da` to turn off analytics. Never import its classes in a JVM bridge, and never port its code into the core. If we ship a Docker image containing the Freerouting JAR, that is an aggregate: include the GPL text and corresponding source or a written offer. fastroute goes in the same category. Given the provenance cloud, do not plan to contribute Freerouting-derived code to KiCad.
- **"AI-assisted porting" risk:** an LLM-heavy project could easily produce translated KiCad or Freerouting code, for example by asking a model to "reimplement PNS walkaround in Rust." That output is a GPL derivative. Contribution rules should forbid feeding GPL/AGPL source into prompts for core code and require clean-room reimplementation from papers and documentation.
- **Konnect:** treat it as capability-level reference only, as kicad-tools does: "an AGPL or unlicensed neighbour is studied at the capability level only, never copied from" [kicad-tools README](https://github.com/rjwalters/kicad-tools). Our MCP server, if hosted over HTTP, would otherwise inherit AGPL §13 obligations.

### Gaps
- No KiCad statement says explicitly whether bindings generated from the GPL `.proto` files may be distributed under non-GPL terms. Issue #134 is unresolved as of 2026-10-20.
- The KiCad developers mailing list was not searched. The forum Discourse API began rate-limiting after about 10 threads.
- The EEVblog/Internet Archive sources on the 2014 Freerouting dispute were not fetched, so the provenance concern is unverified hearsay.
- I found no court ruling on whether protobuf-over-socket clients of a GPL program are separate works. The FSF FAQ is the main authority, and it says judges ultimately decide.

---

## 3. Data, rule packs, and model weights

### Takeaway
Treat three layers separately. (1) **Third-party boards** keep their upstream licenses. Benchmarks should ship *manifests* (repo, SHA, path, SPDX license, attribution) and fetch at run time; precedents are kicad-tools, PCBWorld, and kicad-happy-testharness. About half of open KiCad repos carry no license at all. (2) **Our own data** (manifests, labels, metrics, synthetic boards) should use a permissive data license. CDLA-Permissive-2.0 is the strongest fit for ML because it puts "no restriction" on Results, including models. (3) **Rule packs** derived from vendor app notes should restate facts and parameters in our own words, with citations. Facts and methods are not copyrightable, but vendor document *expression* is, and TI's notice also restricts reproduction contractually. **Weights** can be Apache-2.0 only if the base model is Apache-2.0 or MIT and no restricted model generated the training data.

### Cited Findings
**Open-hardware licenses found on boards**
- CERN-OHL v2 comes in three variants: "CERN-OHL-S (strongly reciprocal…)", "CERN-OHL-W (weakly reciprocal…)", "CERN-OHL-P (permissive…)" [CERN OHL](https://cern-ohl.web.cern.ch/home). Key S-variant terms ([CERN-OHL-S v2 text](https://ohwr.org/cern_ohl_s_v2.txt)):
  - "Product" means "any device, component, work or physical object… arising from the use, application or processing of Covered Source".
  - "Including Covered Source in a larger work is modifying the Covered Source, and the larger work becomes modified Covered Source".
  - It has an express patent licence (§7.1) with litigation termination (§7.2).
  - W-variant "External Material" is anything that "interfaces with the Covered Source using a documented interface" and is not a derivative [CERN-OHL-W v2](https://ohwr.org/cern_ohl_w_v2.txt).
- FSF on designs: "Circuits are meant for practical use, so circuit designs should carry a free license. We recommend releasing them under the GNU General Public License, version 3 or later" [FSF Designs](https://www.gnu.org/licenses/license-list.html#Designs). Also: "In many situations, copyright does not cover making physical hardware from a drawing" [GPL FAQ: GPLHardware](https://www.gnu.org/licenses/gpl-faq.html#GPLHardware)
- Distribution actually observed on boards: see the PCBench tally in §1G (54% no license; roughly 14% copyleft across GPL, CC-BY-SA, CERN-OHL, LGPL and AGPL).
- No-license repos: "all copyrightable works are copyrighted by default… In some countries, users that download code with no license may infringe copyright merely by compiling it or running it" [FSF NoLicense](https://www.gnu.org/licenses/license-list.html#NoLicense). GitHub's ToS grants only "a nonexclusive, worldwide license to use, display, perform and reproduce (by forking) Your Content through the Service" [GitHub ToS D.5](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#5-license-grant-to-other-users). choosealicense advises users of unlicensed code to "Ask the maintainers nicely to add a license" or "Don't use the software" [choosealicense](https://choosealicense.com/no-permission/)

**Precedents for building benchmarks**
- kicad-tools: "this suite's inputs are third-party repos with their own licenses… `fetch_boards.py` downloads each board's `.kicad_pcb` **at run time** into a gitignored cache directory — never into a tracked path". It uses a `boards.toml` manifest with "pinned repo URL + commit SHA, path…, upstream license" [kicad-tools benchmarks/external](https://github.com/rjwalters/kicad-tools/blob/HEAD/benchmarks/external/README.md)
- kicad-happy-testharness: `repos/` holds "cloned test repos (git-ignored)". "All repos must have a pinned 40-char commit hash" [README](https://github.com/aklofas/kicad-happy-testharness)
- PCBWorld rebuilds D3 from PCBench at run time [README](https://github.com/LGAI-Research/PCBWorld). Its LG Notice.md lists third-party licenses [Notice.md](https://github.com/LGAI-Research/PCBWorld/blob/HEAD/Notice.md)
- Community norm: Seth Hillbrand publicly criticized a dataset for stripping licenses and origins [forum](https://forum.kicad.info/t/84-000-free-electronic-schematics/67938/2). Jon Evans set the bar for official KiCad demo designs: they must be "licensed under a GPLv3-compatible license such as CC BY-SA" (from the forum search snippet) [forum](https://forum.kicad.info/t/seeking-new-official-kicad-demo-designs/26967/1)

**Dataset licenses for our own data**
- CDLA-Permissive-2.0: share Data "so long as the Data Recipient makes available the text of this agreement". "This agreement does not impose any restriction or obligations with respect to the use, modification, or sharing of Results". "Results" means "any outcome obtained by computational analysis of Data, including for example machine learning models" [CDLA-Permissive-2.0](https://cdla.dev/permissive-2-0/)
- ODC-By 1.0: "You must attribute any public use of the database, or works produced from the database" [ODC-By summary](https://opendatacommons.org/licenses/by/summary/)
- CC BY 4.0 has a dedicated "Section 4 – Sui Generis Database Rights" [CC BY 4.0 legalcode](https://creativecommons.org/licenses/by/4.0/legalcode.en). FSF says CC BY 4.0 is "compatible with all versions of the GNU GPL" but "should not be used on software" [FSF ccby](https://www.gnu.org/licenses/license-list.html#ccby)
- CC0: FSF recommends CC0 for non-software public-domain release but warns it "has a term expressly stating it does not grant you any patent licenses" [FSF CC0](https://www.gnu.org/licenses/license-list.html#CC0)
- ODbL is "incompatible with the GNU GPL" [FSF ODbl](https://www.gnu.org/licenses/license-list.html#ODbl)
- CC BY-SA 4.0 is "one-way compatible with the GNU GPL version 3" [FSF ccbysa](https://www.gnu.org/licenses/license-list.html#ccbysa)

**ML training on copyleft or share-alike designs (open question)**
- Creative Commons: "there are many scenarios where compliance with CC license conditions is not required when using CC-licensed works for AI training". Under its explicitly conservative guidance: "When training data is subject to the ShareAlike condition, model outputs and the model itself, if shared publicly, should be made available under the same CC license". NoDerivatives works "should not be used as training data". Following the guidance "will almost certainly lead to overcompliance" [CC, Using CC-licensed Works for AI Training (2025)](https://creativecommons.org/wp-content/uploads/2025/05/Using-CC-licensed-Works-for-AI-Training.pdf)
- BY, SA and ND conditions are "triggered only upon public sharing of the original work or an adaptation… attribution would be required… when the model memorizes and thus stores a copy of expression that is substantially similar" [same](https://creativecommons.org/wp-content/uploads/2025/05/Using-CC-licensed-Works-for-AI-Training.pdf)

**Facts vs expression (rule packs from app notes and datasheets)**
- "In no case does copyright protection… extend to any idea, procedure, process, system, method of operation, concept, principle, or discovery, regardless of the form in which it is described" [17 U.S.C. §102(b)](https://www.law.cornell.edu/uscode/text/17/102); likewise [Copyright Office Circular 33](https://www.copyright.gov/circs/circ33.pdf), which also says "there is no copyrightable authorship in a mere listing of ingredients"
- *Feist v. Rural* (1991): "facts are not copyrightable"; "Originality remains the sine qua non of copyright"; "the copyright in a factual compilation is thin" [Cornell LII](https://www.law.cornell.edu/supremecourt/text/499/340)
- TI's notice, printed in every datasheet: "TI grants you permission to use these resources only for development of an application that uses the TI products described in the resource. Other reproduction and display of these resources is prohibited" [TI datasheet (TPS62130), Important Notice](https://www.ti.com/lit/ds/symlink/tps62130.pdf)

**Model weights and fine-tuning data**
- OSI Open Source AI Definition 1.0 requires that Data Information, Code and Parameters be available under "OSI-approved terms" (code under "OSI-approved licenses"). This includes "the complete description of all data used for training" [OSAID 1.0](https://opensource.org/ai/open-source-ai-definition)
- Base-model flow-down: Llama requires "Llama" at the start of the model name plus "Built with Llama". Qwen-licensed models require "Built with Qwen". Gemma restrictions extend to distillation with synthetic data. RAIL restrictions flow down (sources in §1H)
- API-model outputs as training data: Anthropic's Commercial Terms say "Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models" [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
- AI authorship: "given current generally available technology, prompts alone do not provide sufficient human control to make users of an AI system the authors of the output". "copyright law cannot be the basis of protection for works that do not satisfy" human authorship [USCO, Copyright and AI Part 2 (Jan 2025)](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf)

### Inferences
- **Benchmark design.** Commit only a manifest and our own derived artifacts: metrics, task definitions, rule configs, scores, and stripped-routing *diffs* or *recipes* rather than modified boards. Fetch boards at pinned SHAs into a gitignored cache.
  - Gate by SPDX license with tiers.
    - Tier R (redistributable): permissive or CC-BY/CC0/CERN-OHL-P licenses, with attribution in a generated NOTICE.
    - Tier SA: GPL, CC-BY-SA and CERN-OHL-S/W. These are redistributable only as separate bundles under their own licenses. Never mix them into a CDLA bundle.
    - Tier E (fetch-only): unlicensed or "Other" boards, used only for local evaluation, never re-hosted. Ask upstream authors to add licenses.
    - Exclude NC/ND.
  - **Never re-host PCBench or open-schematics content under their blanket licenses.**
- **KiCad footprints inside boards.** Boards embedding KiCad library footprints are "designs", so the library exception applies and adds no obligations. But a dataset that **extracts** footprints into a stand-alone footprint corpus (e.g., per-footprint training records) is redistributing the libraries "as a collection." It must be CC-BY-SA-4.0 WITH KiCad-libraries-exception, with attribution (Jon Evans's reading). Keep such a corpus separate.
- **Training on copyleft boards** is unresolved. The conservative CC reading would put a model trained on CC-BY-SA boards under CC-BY-SA. CERN-OHL-S's "Product… arising from the use, application or processing of Covered Source" could arguably reach a trained model (my reading; untested). The practical path for an "Apache-2.0 weights" goal is to train only on permissively licensed boards (MIT, BSD, Apache, CC-BY, CC0, CERN-OHL-P), our own synthetic boards, and solver-generated trajectories. Document the mix in a data card (OSAID "Data Information").
- **Rule packs.**
  - Store *facts and parameters* (e.g., "decoupling cap ≤ X mm from pin; via-in-pad per IPC-7093; return-via within λ/20"), with conditions, our own short rationale, and a structured citation: vendor, document number, revision, section/page, URL, access date.
  - Do not copy sentences, tables verbatim, figures, or layout drawings, and do not commit vendor PDFs.
  - TI's notice adds a contractual "use only for development of an application" and "other reproduction… prohibited" term on top of copyright. Linking and paraphrasing facts is the low-risk path. Its enforceability against a non-customer is a question for counsel.
  - License the machine-readable rule records **CC0-1.0**. Facts are not ours to restrict anyway, CC0 is FSF-recommended for non-software, and it lets KiCad, CC-BY-SA library projects, and companies embed packs without attribution stacking. Add a non-binding "please cite" note.
  - Alternative: CC-BY-4.0, which is GPL-compatible and keeps an attribution chain.
  - Executable checks (Python, `.kicad_dru` generators) are code, so license them with the code (Apache-2.0).
- **Weights.** Use Apache-2.0 base models: Qwen3/3.5/3.6, Mistral-7B, OLMo-2, gpt-oss (Apache), or MIT ones like Phi-4 and DeepSeek-R1. Release weights under Apache-2.0 with a model card. Avoid Llama, Gemma, Qwen-license (72B) and RAIL bases, which would force naming, flow-down or use restrictions incompatible with "very open." Synthetic SFT data generated by Claude might count as "train[ing] competing AI models." A narrow layout model probably does not, but get that reviewed. Prefer solver- or DRC-generated supervision or Apache-licensed open-weight generators.
- **AI-authored code.** Large parts of this repo may be AI-generated and therefore have thin or no copyright. A LICENSE file is still useful: it covers the human-authored and selected portions and gives downstream users clear permission. It is not a reason to skip licensing.

### Gaps
- EU sui generis database rights (Directive 96/9/EC) and how they affect compiling a board corpus from EU-hosted repos were not researched in depth.
- No case law was found on whether trained weights are "adaptations" of share-alike or copyleft training data.
- Analog Devices, ST, NXP and Microchip document terms were not retrieved (analog.com had relay failures). Only TI's notice was verified.
- The TAPR OHL text was not read (only reachability of its SPDX page was confirmed).
- OpenAI's services agreement could not be rendered (JavaScript page). Its output-use terms are unverified here.
- I found no official KiCad statement on ML training using KiCad library data.

---

## 4. License options for our project, with pros and cons

### Takeaway
Measured against "very open and a good base for others," the permissive options win, and Apache-2.0 beats MIT because of its express patent grant and the FSF's own recommendation of it among lax licenses. Keeping GPL-3.0 maximizes alignment with KiCad and Freerouting and blocks proprietary forks, but excludes most commercial adopters (ASF Category X) and buys little technically, since we can reach GPL tools through process boundaries anyway. Split licensing by component type is what the comparable projects with mixed stacks actually do (PCBWorld, KiCad's own docs and libraries, Topola). Relicensing is free now and expensive later.

### Cited Findings
- FSF on Apache-2.0: "compatible with version 3 of the GNU GPL… not compatible with GPL version 2… The patent termination provision is a good thing, which is why we recommend the Apache 2.0 license for substantial programs over other lax permissive licenses" [FSF apache2](https://www.gnu.org/licenses/license-list.html#apache2). On Expat/MIT: "For substantial programs it is better to use the Apache 2.0 license since it blocks patent treachery" [FSF Expat](https://www.gnu.org/licenses/license-list.html#Expat)
- ASF: "Apache 2 software can therefore be included in GPLv3 projects… However, GPLv3 software cannot be included in Apache projects. The licenses are incompatible in one direction only" [ASF GPL compatibility](https://www.apache.org/licenses/GPL-compatibility.html). ASF Category X (may NOT be included) lists "GNU GPL 1, 2, 3", "GNU Affero GPL 3", and "GNU LGPL 2, 2.1, 3". MPL and EPL are "weak copyleft" Category B, includable "in binary form" [ASF resolved](https://www.apache.org/legal/resolved.html)
- MPL-2.0 §3.3 lets a "Larger Work" combine with GPL/LGPL/AGPL, so "the Larger Work, as a whole, will be covered under the GNU license(s)" [FSF MPL-2.0](https://www.gnu.org/licenses/license-list.html#MPL-2.0); [MPL-2.0 text](https://www.mozilla.org/en-US/MPL/2.0/). choosealicense: "a larger work using the licensed work may be distributed under different terms and without source" [choosealicense MPL-2.0](https://choosealicense.com/licenses/mpl-2.0/)
- LGPL: FSF calls it "a retreat for free software", decided "case-by-case". "Once we use the LGPL for a particular library, changing back would be difficult" [GPL FAQ: WhySomeGPLAndNotLGPL](https://www.gnu.org/licenses/gpl-faq.html#WhySomeGPLAndNotLGPL). Static linking requires relinkable objects [LGPLStaticVsDynamic](https://www.gnu.org/licenses/gpl-faq.html#LGPLStaticVsDynamic). Rust crates are normally statically linked (inference)
- choosealicense summaries ([Apache-2.0](https://choosealicense.com/licenses/apache-2.0/), [MIT](https://choosealicense.com/licenses/mit/), [GPL-3.0](https://choosealicense.com/licenses/gpl-3.0/), [AGPL-3.0](https://choosealicense.com/licenses/agpl-3.0/)):
  - Apache-2.0: "Contributors provide an express grant of patent rights. Licensed works, modifications, and larger works may be distributed under different terms and without source code".
  - MIT: conditions "only requiring preservation of copyright and license notices"; no patent-use permission listed.
  - GPL-3.0: "strong copyleft… larger works using a licensed work, under the same license".
  - AGPL-3.0 adds "network-use-disclose".
- Rust convention: "The software produced by the Rust project is dual-licensed, under either the MIT or Apache 2.0 licenses. Crates that simply need the maximum compatibility with the Rust ecosystem are recommended to do the same" [Rust API Guidelines C-PERMISSIVE](https://rust-lang.github.io/api-guidelines/necessities.html#crate-and-its-dependencies-have-a-permissive-license-c-permissive)
- Dual licensing with a proprietary option is legally possible for a sole copyright holder: "you can release it under various different non-exclusive licenses at various times" [GPL FAQ: ReleaseUnderGPLAndNF](https://www.gnu.org/licenses/gpl-faq.html#ReleaseUnderGPLAndNF). Konnect uses this model (AGPL plus commercial) [README](https://github.com/mixelpixx/Konnect)
- KiCad upstream already carries Apache-2.0 code (`libs/kimath/include/math/util.h`), plus MPL-2.0 (Eigen), MIT, BSD, Boost, ISC, and others, under a GPLv3+ combined work [LICENSE.README](https://gitlab.com/kicad/code/kicad/-/blob/master/LICENSE.README). KiCad requires source files to carry copyright: "source files must be copyrighted and not be released into the public domain" [KiCad code style §5](https://dev-docs.kicad.org/en/rules-guidelines/code-style/)
- Contributor mechanics:
  - DCO 1.1: contributor certifies "I have the right to submit it under the open source license indicated in the file" [developercertificate.org](https://developercertificate.org/).
  - GitHub ToS: "Whenever you add Content to a repository containing notice of a license, you license that Content under the same terms… commonly referred to by the shorthand 'inbound=outbound'". A CLA supersedes this [GitHub ToS D.6](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#6-contributions-under-repository-license).
  - FSF asks for assignment to simplify GPL enforcement [GPL FAQ: AssignCopyright](https://www.gnu.org/licenses/gpl-faq.html#AssignCopyright).
- Relicensing:
  - GPL-3.0 rights already granted "are irrevocable provided the stated conditions are met" (§2) [repo LICENSE](https://github.com/magnetic-trowel/kicad-auto-everything/blob/main/LICENSE). Anyone who already copied the GPL version keeps those rights to that snapshot.
  - "Once the work has other contributors (each a copyright holder), 'nobody' starts including you" [choosealicense](https://choosealicense.com/no-permission/).
  - "Only the copyright holders for the program can legally authorize" exceptions [GPL FAQ: LinkingOverControlledInterface](https://www.gnu.org/licenses/gpl-faq.html#LinkingOverControlledInterface).
  - Example: OpenSSL applies Apache-2.0 only from 3.0 on, with older releases keeping their old license [OpenSSL license page](https://openssl-library.org/source/license/index.html). kicad-python relicensed about six weeks after its 0.1.0 release (2024-12-21 → 2025-02-02) while the KiCad Developers held the copyright [issue #9](https://gitlab.com/kicad/code/kicad-python/-/work_items/9).
- What comparable projects chose (stated rationale where found):
  - **KiCad**: GPLv3+. It relies on "the copyright enforcement capabilities of copyright law" [code style](https://dev-docs.kicad.org/en/rules-guidelines/code-style/). Its libraries use CC-BY-SA with an exception "to ensure free use of library data for commercial, closed, and non-commercial projects" [kicad.org](https://www.kicad.org/libraries/license/).
  - **kicad-python**: GPLv3 → MIT to stop the confusion that kipy "taints" plugins [issue #9](https://gitlab.com/kicad/code/kicad-python/-/work_items/9).
  - **Freerouting**: GPL-3.0, inherited from its 2014 open-sourcing (per forum) [forum](https://forum.kicad.info/t/freerouting-modernization/69547/56).
  - **tscircuit**: "completely free and MIT-licensed open-source" [README](https://github.com/tscircuit/tscircuit).
  - **atopile**: "MIT. See LICENSE" [README](https://github.com/atopile/atopile).
  - **KiKit**: MIT [LICENCE](https://github.com/yaqwsx/KiKit/blob/HEAD/LICENCE).
  - **KiCadRoutingTools**: "free and MIT-licensed, and it stays that way — there is no paid tier" [README](https://github.com/drandyhaas/KiCadRoutingTools).
  - **Horizon EDA**: GPL-3.0, embedding KiCad's GPLv3 router [README](https://github.com/horizon-eda/horizon).
  - **LibrePCB**: GPLv3 [README](https://github.com/LibrePCB/LibrePCB).
  - **OpenROAD**: BSD-3-Clause [README](https://github.com/The-OpenROAD-Project/OpenROAD).
  - **DREAMPlace**: BSD-3-Clause; Cypress builds on it as Apache-2.0 [Cypress README](https://github.com/NVlabs/Cypress).
  - **PCBWorld**: BSD-3 environment plus GPLv3 engine "because it links KiCad" [README](https://github.com/LGAI-Research/PCBWorld).
  - **Topola**: MIT with REUSE (`REUSE.toml`, `LICENSES/`) [Codeberg](https://codeberg.org/topola/topola).
  - **Konnect**: AGPL-3.0 plus commercial ("free for the little guys") [README](https://github.com/mixelpixx/Konnect).
  - I found no explicit rationale statements from tscircuit, atopile, KiKit, LibrePCB, Horizon, OpenROAD or DREAMPlace beyond the license declarations.

### Inferences
**Options table** (the scoring is my synthesis of the findings above)

| Option | Fit with our deps | Companies/startups can adopt | KiCad upstream can absorb | Blocks proprietary forks | Patent protection (from contributors) | Contributor friction | Net for "very open, good base" |
|---|---|---|---|---|---|---|---|
| (1) Keep GPL-3.0(-or-later) | Absorbs everything incl. Freerouting, fastroute, kiutils, PNS (except GPL-2.0-only, Triangle, proprietary) | Poor: ASF Category X (a proxy for conservative corporate policies; no adoption survey found). Companies can still use it internally and over a network without releasing source (GPL, not AGPL) | Yes (same license) | Yes (distributed forks) | Express (§11) plus §10 retaliation | Low (DCO) | Protective, but narrows the "base for others" audience. Our process-boundary architecture means we don't *need* GPL to use GPL tools |
| (2) Apache-2.0 | All permissive and weak-copyleft deps OK. GPL tools via process boundary only | Best: widely accepted, express patent grant | Yes (KiCad already contains Apache-2.0 code; GPLv3+ accepts it) | No | Express plus termination (§3) | Low (DCO or inbound=outbound) | **Strongest fit** |
| (3) MIT | Same as Apache | Very good; simplest | Yes (also GPL-2.0-only targets) | No | None express | Lowest | Good. Loses the patent grant FSF/ASF value for "substantial programs" |
| (4) MPL-2.0 | Same as Apache. GPL combination via §3.3 | Good. ASF Category B (binary inclusion allowed); obligations are per-file | Yes (via §3.3 secondary licenses) | Partly: our *files* stay open, larger works can be proprietary | Express (§2.1b) plus §5.2 | Low–medium (file headers, marking) | Strong runner-up if the owner wants improvements to our files to come back |
| (5) LGPL-3.0 | OK | Medium–poor: ASF Category X; static-link (Rust) relink obligations | Yes | Library-level | Express (via GPLv3) | Medium | Awkward for Python + Rust; not recommended |
| (6a) Dual "Apache-2.0 OR MIT" | Same as Apache | Best | Yes, plus GPL-2.0-only targets | No | Express only if recipient elects Apache | Low | Good for Rust crates (ecosystem norm) |
| (6b) Dual "GPL/AGPL + commercial" (Konnect model) | As GPL | Paid path only | Yes (GPL side) | Yes | Express | High: needs CLA or assignment so owner can sell licenses | Contradicts "very open" |
| (7) Split by component (recommended form below) | Matches each artifact type to a fit-for-purpose license | Best for code; clear for data, docs and weights | Code yes; docs (CC-BY) and rules (CC0) also GPL-compatible | Only the GPL helper packages | Express for code and weights (Apache) | Low with REUSE plus DCO | **Recommended** |

Notes on the table:
- "Blocks proprietary forks" applies only to *distributed* forks. Neither GPL nor MPL reaches SaaS use. Only AGPL does ([GPL FAQ: UnreleasedMods](https://www.gnu.org/licenses/gpl-faq.html#UnreleasedMods)).
- No license protects against **third-party** patents. Apache, GPL and MPL grants cover only contributors' own patent claims ("licensable by such Contributor": [Apache-2.0 §3](https://www.apache.org/licenses/LICENSE-2.0.txt); "contributor's essential patent claims": [GPL-3.0 §11](https://www.gnu.org/licenses/gpl-3.0.txt); "Patent Claims of such Contributor": [MPL-2.0 §2.1(b)](https://www.mozilla.org/en-US/MPL/2.0/)). So the Cadence family flagged in [patents_and_industry.md](patents_and_industry.md) (US 11,599,699 "System and method for autonomous printed circuit board design using machine learning techniques", US 12,223,248, and also US 12,566,911, US 11,042,981, NVIDIA US 2025/0315590) is unaffected by our license choice. That is identification only; the claims have not been read.
- Express patent grants by license:
  - Present: Apache-2.0 §3; GPL-3.0/AGPL-3.0/LGPL-3.0 §11 (FSF says §10 plus §8 act as patent retaliation, [GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html#v3PatentRetaliation)); MPL-2.0 §2.1(b); EPL-2.0 §2(b) [ELK LICENSE](https://github.com/eclipse/elk/blob/HEAD/LICENSE.md); CERN-OHL v2 §7.
  - Absent: MIT, BSD, Boost, ISC, Zlib, GPL-2.0, LGPL-2.1. CC0 expressly excludes patents [FSF CC0](https://www.gnu.org/licenses/license-list.html#CC0). CC-BY and CC-BY-SA list patent use as a limitation [choosealicense CC-BY-4.0](https://choosealicense.com/licenses/cc-by-4.0/).

### Gaps
- No survey data was found on corporate open-source policy preferences beyond ASF's categories. The "companies prefer Apache/MIT" claim rests on ASF policy and the FSF's own recommendations, not adoption statistics.
- The KiCad project's preferences for receiving third-party Python or Rust code were not found. KiCad core is C++, so direct absorption of our Python is unlikely in any case.
- Whether the current repo LICENSE means GPL-3.0-only or GPL-3.0-or-later is ambiguous. The file contains the bare license text with no notice.

---

## 5. Recommendation and practical checklist

### Takeaway
**Recommended:** split licensing with an **Apache-2.0 core**:
- code (Python, Rust, TypeScript, MCP server, IPC plugins): Apache-2.0
- docs, reports and research notes: CC-BY-4.0
- machine-readable rule packs: CC0-1.0
- our own datasets, manifests and annotations: CDLA-Permissive-2.0
- model weights: Apache-2.0, from Apache/MIT base models only
- an optional, separately distributed GPL-3.0-or-later "bridges" package for anything that must link KiCad, Freerouting, kiutils or other GPL code

**Runner-up:** the same split with an **MPL-2.0** core, if the owner wants modifications to our own files to stay open while still allowing proprietary larger works. Relicense **now**, while the owner is the sole human copyright holder.

### Cited Findings
- Repo state: one human commit plus AI-authored notes; no external contributors (local `git shortlog -sne`, 2026-10-20). AI-only material may lack copyright [USCO Part 2](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf)
- REUSE 3.3: "Each License File MUST be placed in the LICENSES/ directory… named [by] the SPDX License Identifier". "A Project MUST NOT include License Files for licenses under which none of the files in the Project are licensed". "Each Covered File MUST have Licensing Information… Comment headers [or] REUSE.toml" [REUSE spec 3.3](https://reuse.software/spec-3.3/). The `reuse` tool is at 6.2.0 [PyPI](https://pypi.org/project/reuse/). Topola is a working REUSE example in this domain [Codeberg](https://codeberg.org/topola/topola)
- Dependency license tooling:
  - `pip-licenses` 5.5.5 (MIT) supports `--fail-on` and `--allow-only`, and reads metadata or classifiers via `--from=mixed` [PyPI](https://pypi.org/project/pip-licenses/).
  - `licensecheck` checks "if these are compatible with the project license" [PyPI](https://pypi.org/project/licensecheck/).
  - `cargo-deny` 0.20.2 "licenses check is used to verify that every crate you use has license terms you find acceptable" [docs](https://embarkstudios.github.io/cargo-deny/checks/licenses/index.html).
  - ScanCode 32.5.0 [PyPI](https://pypi.org/project/scancode-toolkit/).
- PCBWorld ships a third-party Notice.md, a pattern worth copying [Notice.md](https://github.com/LGAI-Research/PCBWorld/blob/HEAD/Notice.md)
- The KiCad PCM requires GPL-compatible licenses for code packages [KiCad add-ons](https://dev-docs.kicad.org/en/addons/)

### Inferences
**Why this choice:**
- The owner's goal ("very open, good base for others") is about adoption and reuse. Apache-2.0 has the widest reach: commercial users, academia, other open projects, and KiCad itself, since GPLv3+ accepts Apache-2.0 and KiCad already contains Apache-2.0 code. It also carries an express contributor patent grant, which both FSF and ASF value.
- We lose nothing technically by not being GPL. The architecture already isolates GPL tools behind process boundaries (IPC API, kicad-cli, Freerouting CLI/REST, PCBWorld-style sockets), and KiCad's lead devs have said IPC clients need not be GPL.
- Data, docs, rules and weights get licenses designed for them. CC licenses are not recommended for software, and CDLA is explicit that ML Results are unrestricted.

**Runner-up rationale (MPL-2.0 core):** it keeps the same compatibility (GPL combination via §3.3; ASF Category B) and the same patent grant, but requires that improvements to *our files* stay open. It costs a little more compliance effort for adopters (file-level source offers). Choose it if the owner wants some reciprocity without GPL's whole-program reach.

**When to choose GPL-3.0-or-later instead:** if the project decides to embed GPL engines in-process as a core feature, for example linking KiCad PNS, porting Freerouting, or depending on kiutils/CGAL in the core library. At that point the distributed core would be GPL-combo anyway, and declaring GPL-3.0-or-later is more honest.

**Practical checklist**
1. **Relicense now.**
   - Replace `LICENSE` with Apache-2.0 text.
   - Add `NOTICE`, e.g., "kicad-auto-everything, Copyright 2026 The kicad-auto-everything contributors".
   - State in the README that versions before commit X were GPL-3.0, and that the owner relicenses their own contributions.
   - Decide before accepting any outside PR.
2. **REUSE layout.**
   - `LICENSES/Apache-2.0.txt`, `CC-BY-4.0.txt`, `CC0-1.0.txt`, `CDLA-Permissive-2.0.txt`. Add `GPL-3.0-or-later.txt` only if a GPL bridge lives in this repo; better to put it in a separate repo, PCBWorld-style.
   - Put SPDX headers in every source file: `SPDX-FileCopyrightText: 2026 The kicad-auto-everything contributors` and `SPDX-License-Identifier: Apache-2.0`.
   - Add a `REUSE.toml` that annotates `docs/**`, `reports/**`, `research_notes/**` as CC-BY-4.0, `rules/**` as CC0-1.0, and `datasets/manifests/**` as CDLA-Permissive-2.0. Note that quotations inside research notes remain the property of their sources.
   - Run `reuse lint` in CI.
3. **Rust crates.** Use Apache-2.0, or "Apache-2.0 OR MIT" if crates.io and GPL-2.0-only compatibility matter. Run `cargo deny check licenses` with an allow-list: Apache-2.0, MIT, BSD-2/3-Clause, ISC, Zlib, BSL-1.0, Unicode-3.0, MPL-2.0. Deny GPL, AGPL, LGPL and unlicensed crates in core crates.
4. **Python CI gate.**
   - Run `pip-licenses --from=mixed --allow-only="…permissive list…;Mozilla Public License 2.0 (MPL 2.0);GNU Lesser General Public License v2 or later (LGPLv2+)…"` or `licensecheck` against the core's dependency set. Keep GPL-only packages (kiutils, PySpice, `cgal`, openEMS Python, freerouting JVM bridges) out of core dependencies, in optional extras of the GPL bridge package only.
   - Run ScanCode over any vendored directory.
5. **Third-party notices.** Generate `THIRD_PARTY_NOTICES.md` at release (pip-licenses/cargo-about output). For Docker images or bundles that include KiCad, Freerouting or GEOS binaries, include their license texts and corresponding source or a written offer (GPL/LGPL aggregate obligations).
6. **Contributor policy (`CONTRIBUTING.md`).**
   - Require DCO sign-off (`git commit -s`) enforced by a CI or DCO check. Rely on inbound=outbound. Avoid a CLA unless the owner wants the option to relicense later.
   - Add an AI-assisted-contribution rule: no GPL, AGPL or unlicensed source in prompts or diffs for core code. Disclose AI use. Contributors certify provenance under the DCO.
   - Add clean-room rules for KiCad PNS/DRC internals, Freerouting and Konnect: reimplement from papers, docs and observable behavior only.
7. **KiCad integration rules.**
   - Use kicad-python from PyPI and do not vendor `.proto` files.
   - Any other-language bindings are generated at build time. Ask KiCad (issue #134) for an explicit license statement on generated code.
   - kicad-cli runs as a subprocess. No SWIG in the core. IPC plugins on PCM are Apache-2.0, which is GPL-compatible as PCM requires.
8. **Freerouting and other GPL tools.**
   - Run them as subprocess, REST or MCP. Always pass `-da`. Pin versions.
   - Never port or translate their code into the core. fastroute is optional and external.
   - PCBWorld-Engine or other KiCad-linking engines go behind a socket, distributed separately.
9. **Datasets.**
   - Use a manifest schema with `repo_url`, `commit_sha`, `path`, `spdx_license`, `license_evidence_url`, `attribution`, `retrieved_at`, and `tier` (R/SA/E).
   - Fetch at run time into a gitignored cache.
   - Generate NOTICE and attribution files for any redistributed tier-R bundle. Keep separate SA bundles.
   - Provide a takedown and contact process and a datasheet or data card.
   - Do not re-host PCBench, open-schematics, OmniLayout or PCBGolf content. Our own annotations, synthetic boards and metrics are CDLA-Permissive-2.0.
10. **Rule packs.**
    - Each rule record carries vendor, doc ID, revision, section, URL and access date, plus a paraphrased condition/value/rationale.
    - No figures, verbatim tables or PDFs in the repo.
    - Records are CC0-1.0. Executable rule code is Apache-2.0.
11. **Model releases.**
    - Use only Apache-2.0 or MIT base models.
    - Use training data from tier R plus synthetic and solver-generated data.
    - Ship a model card with data information and training code (OSAID checklist).
    - Weights are Apache-2.0.
    - Record which models generated any synthetic data, and check those terms (Anthropic: no training of "competing AI models"; Llama, Qwen-license and Gemma: flow-down).
12. **Patents (identification only).** Keep the FTO watch-list from [patents_and_industry.md](patents_and_industry.md) in the repo. Get counsel review before shipping a trained RL policy that picks place, via or route actions, or a learned routability predictor inside placement (the Cadence family). Note that our own open publication of methods creates dated public disclosures (inference).
13. **Re-verify at each release.** Licenses change. libspatialindex went LGPL→MIT, kipy went GPL→MIT, and Topola's crate shows MIT-or-Apache while its repo shows MIT. Re-run the license audit and update `THIRD_PARTY_NOTICES.md`.

### Gaps
- The KiCad trademark or branding policy for using "KiCad" in the project name (`kicad-auto-everything`) was not researched.
- Whether to use a DCO GitHub App or a CI action was not compared.
- No counsel input. Corporate-adoption claims are inferred from ASF and FSF policy, not surveyed.

---

## 6. Implications: components to avoid or isolate

### Takeaway
For an Apache-2.0 core:
- **Avoid entirely:** Triangle, OptiMathSAT, bundling Gurobi, OmniLayout data, re-hosting PCBench/open-schematics/PCBGolf boards, and Llama/Gemma/Qwen-license/RAIL bases for released weights.
- **Isolate behind a process boundary or a separate GPL package:** KiCad SWIG/C++ (PNS), PCBWorld-Engine, Freerouting, fastroute, kiutils, CGAL Python, openEMS Python, PySpice, Elmer, and Konnect (reference only).
- **Fine as unmodified dependencies with notices:** LGPL, MPL and EPL libraries.

### Cited Findings
- Triangle's upstream bars commercial distribution without arrangement [Triangle README](https://github.com/libigl/triangle/blob/HEAD/README). Gurobi is proprietary [PyPI](https://pypi.org/pypi/gurobipy/json). OptiMathSAT is research-only per earlier notes [solver_toolbox.md](solver_toolbox.md)
- kiutils is GPL-3.0 [LICENSE](https://github.com/mvnmgrx/kiutils/blob/HEAD/LICENSE). kicad-skip is LGPL-2.1+ [LICENSE](https://github.com/psychogenic/kicad-skip/blob/HEAD/LICENSE). kipy is MIT [LICENSE](https://gitlab.com/kicad/code/kicad-python/-/blob/main/LICENSE)
- openEMS Python is "GPL-3.0-or-later" [setup.py](https://github.com/thliebig/openEMS/blob/HEAD/python/setup.py). `cgal` is GPLv3+ [PyPI](https://pypi.org/pypi/cgal/json). PySpice is GPLv3 [PyPI](https://pypi.org/pypi/PySpice/json)
- Konnect is AGPL-3.0 [LICENSE](https://github.com/mixelpixx/Konnect/blob/HEAD/LICENSE). kicad-tools' policy is "studied at the capability level only, never copied from" [README](https://github.com/rjwalters/kicad-tools)
- Dataset issues: PCBench has an MIT overlay on boards that are 54% unlicensed (my tally) [metadata](https://github.com/PCBench/PCBench/blob/HEAD/PCBs/master_metadata.json). open-schematics has a CC-BY-4.0 overlay with no per-record license and is criticized by a KiCad lead dev [card](https://huggingface.co/datasets/bshada/open-schematics); [forum](https://forum.kicad.info/t/84-000-free-electronic-schematics/67938/2). OmniLayout has no grant [recon](https://github.com/rjwalters/kicad-tools/blob/HEAD/docs/research/omnilayout-recon.md). PCBGolf has no license [repo](https://github.com/commaai/PCBGolf)

### Inferences

| Component | Action for an Apache-2.0 core | Why |
|---|---|---|
| KiCad C++ (PNS router, DRC engine) | Isolate: separate GPL engine process (PCBWorld pattern) or don't use | Linking makes the combination GPL |
| SWIG `pcbnew` | Isolate in a GPL helper; prefer IPC API or kicad-cli. It is removed in KiCad 11 anyway | Lead dev: "GPL or compatible"; deprecated |
| IPC `.proto` files | Don't vendor. Use kipy (MIT). Build-time generation for other languages; seek clarification | GPL headers; issue #134 open |
| Freerouting / fastroute | Subprocess, REST or MCP only. `-da`. No porting. Bundled binaries need GPL source/offer | GPL; provenance cloud; analytics default |
| PCBWorld-Engine | Socket only; separate distribution | GPLv3 "because it links KiCad" |
| kiutils | Replace in core with kicad-skip (LGPL), our own S-expression parser, or kipy. Allowed only in the GPL bridge | GPL-3.0 import = GPL-combo |
| CGAL Python, openEMS Python, PySpice, Elmer | Run as subprocesses (e.g., call gerber2ems or openEMS scripts) or confine to the GPL bridge | GPL bindings |
| Konnect (AGPL) | Reference only; never copy code into our (network) MCP server | AGPL §13 network obligation |
| Triangle (Shewchuk) | Avoid; use PythonCDT (MPL-2.0) | Commercial distribution restricted |
| Gurobi, OptiMathSAT | Optional user-installed backends only; never bundle | Proprietary or research-only |
| Shapely/GEOS, DEAP, kicad-skip, adaptagrams, CSXCAD | OK unmodified. If we redistribute binaries, include LGPL notices and source. Avoid static LGPL linking in Rust | LGPL obligations |
| PythonCDT/CDT, jagua-rs, ELK/elkjs | OK. Keep modifications to their files under MPL/EPL | File-level copyleft |
| KiCad library footprints | Fine inside boards. Any extracted footprint corpus is CC-BY-SA-4.0 WITH exception, kept separate | Library license and Jon Evans's reading |
| PCBench, open-schematics, PCBGolf, unlicensed repos | Manifest plus run-time fetch only; per-board license gating; don't re-host | Blanket licenses don't cure upstream rights |
| OmniLayout data | Don't use (metric definitions only) | No grant; papers NC-ND |
| Llama, Gemma, Qwen-license (72B), OpenRAIL bases | Don't fine-tune for release. Use Apache/MIT bases (Qwen3/3.5/3.6, Mistral, OLMo-2, gpt-oss, Phi-4, DeepSeek-R1) | Naming, flow-down and use restrictions conflict with Apache-2.0 weights |
| API-model-generated SFT data (Claude etc.) | Check provider terms before releasing models trained on it; prefer solver or DRC-generated supervision | "train competing AI models" clause |
| Vendor app notes/datasheets | Facts plus citations only; no verbatim text, figures or PDFs | Copyright in expression; TI's reproduction restriction |

- These choices also keep the earlier notes' technical recommendations intact. They already proposed Freerouting via CLI/REST, PCBWorld-style boundaries, kipy, OR-Tools, Shapely, Clipper2, PythonCDT, Optuna and pymoo. Only kiutils, the SWIG paths and "vendor/fork Freerouting" (suggested in [existing_tools_and_apis.md](existing_tools_and_apis.md) under a GPL assumption) need to change for an Apache-2.0 core.

### Gaps
- No enforcement history was found for KiCad's or Freerouting's GPL against IPC or REST clients. The risk assessment rests on the FSF FAQ and lead-developer statements, not case law.
- A per-dependency audit of transitive dependencies (full `pip-licenses`/`cargo-deny` run) was not possible because no code exists yet. It should run once a lockfile exists.
