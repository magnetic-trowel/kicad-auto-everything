# Computational geometry libraries (Shapely, Clipper, R-trees, CDT, NFP, jagua-rs)

**TL;DR**
- **Shapely 2.x** (BSD-3, bundles LGPL-2.1 GEOS) is the default for polygons and vectorized predicates; its STRtree is immutable.
- **pyclipper** (MIT, Clipper1) has manylinux wheels and Minkowski sum/diff (practical no-fit polygons); the Clipper2 binding pyclipr has **no Linux wheels**.
- **jagua-rs** (Rust, MPL-2.0) is the maintained SOTA collision engine for irregular shapes; **sparrow** (MIT) on top is SOTA nesting — no Python bindings yet (PyO3 wrapper needed).
- Measured: a full exact polygon re-check of a 20–1000-part board costs ≤5 ms; per-move checks cost ~12–30 µs in Python with any vectorized method → Python SA caps at ~10⁴–10⁵ moves/s; hot loops belong in Rust.
- Use PythonCDT for triangulation; **avoid `triangle`** (non-commercial upstream).

## Key facts

**Measured** (`geom_bench.py`; courtyard rectangles; 5,000 single-part moves each followed by a 0.2 mm clearance check; µs per move-check, single thread) [M]
| N | NumPy AABB vs all | Python grid hash (2 mm) | rtree delete+insert+query | STRtree query (static) | STRtree rebuilt per move | Exact octagons (STRtree + `dwithin`) | Full all-pairs exact check |
|---|---|---|---|---|---|---|---|
| 100 | 11.4 | 13.3 | 37.7 | 23.6 | 39.4 | 27.3 | 0.49 ms |
| 300 | 11.5 | 14.0 | 153.7 | 23.5 | 69.9 | 27.4 | 1.29 ms |
| 1000 | 14.9 | 14.7 | 62.7 | 24.6 | 280.7 | 31.8 | 4.95 ms |
| 3000 | 23.1 | 16.4 | 239.1 | 26.9 | 889.0 | 29.0 | 15.7 ms |

STRtree build 0.1–0.6 ms. Clearance offset per polygon: pyclipper 12.7–14.6 µs with `arc_tolerance` = 5 µm (~100 µs with too-fine tolerance); Shapely `buffer` 8.4–22.7 µs (vectorized, `quad_segs=4`, so coarser than pyclipper's setting; not like-for-like). Rebuilding the STRtree per move is the slowest dynamic option at N ≥ 1000 (281–889 µs vs rtree's 63–239 µs); rtree's 153.7 µs at N=300 is non-monotonic, likely noise.

**Libraries and licenses** ([P] unless noted; fit for GPL-3.0-or-later)
| Library | License | Notes | Fit |
|---|---|---|---|
| Shapely 2.2.0 | BSD-3 (+ GEOS LGPL-2.1) | STRtree Sort-Tile-Recursive, immutable; `query(predicate='dwithin', distance=…)`, array inputs | OK |
| rtree 1.4.1 | MIT (libspatialindex) | Insert, delete, bulk load | OK |
| pyclipper 1.4.0 | MIT | Manylinux wheels; `MinkowskiSum`, `MinkowskiSum2`, `MinkowskiDiff` | OK |
| Clipper2 | Boost | C++17; README notes a 6-month update pause; pyclipr 0.1.8 only macOS arm64/win wheels | OK (Rust crate inside core) |
| **jagua-rs** | MPL-2.0 | Continuous rotation/translation, reflections, holes, quality zones, minimum separation, WASM; dynamic quadtree; "millions of collision queries per second" ([arXiv 2508.08341](https://arxiv.org/abs/2508.08341)) | OK (MPL is GPL-compatible as a Larger Work) |
| **sparrow** | MIT (Rust ≥1.90) | SOTA 2D irregular strip packing on jagua-rs ([arXiv 2509.13329](https://arxiv.org/abs/2509.13329)) | OK |
| libnest2d / pynest2d | LGPL-3 | PrusaSlicer, SVGnest-inspired, header-only | OK |
| libnfporb | GPL-3 | Author archiving: "way better alternatives … out by now" | License OK, abandoned |
| SVGnest / deepnest-next | MIT | Orbital NFP + GA; deepnest-next moving to Rust | OK |
| PythonCDT 2.0.2 | MPL-2.0 + BSD-3 + Apache-2.0/LLVM | Wheels for Linux/macOS/Windows | OK |
| `triangle` | LGPL-3 wrapper over Shewchuk's Triangle | Commercial distribution "ONLY BY DIRECT ARRANGEMENT WITH THE AUTHOR" | **Avoid** |
| cgal 6.0.1 (Python) | GPLv3+ | "still experimental" | OK under GPL-3.0-or-later |
| scikit-geometry | LGPL-3 | Not on PyPI | OK, unmaintained packaging |
| KiCad IPC `GetPadShapeAsPolygon` | — | Pad copper as polygons ([board_commands.proto](https://gitlab.com/kicad/code/kicad/-/raw/master/api/proto/board/board_commands.proto)) | — |

**Algorithmic notes**: jagua-rs "hazards" abstraction and fail-fast pole-of-inaccessibility surrogates ([packing transplants](../placement/packing-and-graph-drawing-transplants.md)); a robust public NFP generator "remains elusive" (jagua-rs paper); keep-outs and non-rectangular outlines decompose to rectangles (Shapely) as fixed boxes for CP-SAT ([CP-SAT](cp-sat-milp-smt.md)); constrained Delaunay triangulation underlies topological routing and SURF cut checks ([topological](../routing/topological-routing.md)).

## Recommendations for our system
- Inner loop on courtyard rectangles: uniform grid hash or vectorized NumPy AABB; in Rust for SA/LNS [M/I].
- Exact irregular courtyards: Shapely `dwithin` on STRtree candidates in batch; full exact re-check (≤5 ms) after every accepted LNS window or SA temperature step; later jagua-rs via PyO3 [M/I].
- Clearance offsets: pyclipper on Linux with `arc_tolerance` set; Shapely `buffer` for prototyping; Clipper2 crate in the Rust core [I].
- NFPs: `pyclipper.MinkowskiDiff` for courtyard NFPs; prefer jagua-rs over building an NFP library [I].
- Triangulation: PythonCDT; never `triangle` [I].

## Conflicts and open questions
- No existing Python bindings for jagua-rs were checked; FSF compatibility list (Boost, ISC, LGPL with GPLv3) could not be fetched — compatibility relies on ASF and Mozilla statements.

## Sources
- research notes: [solver_toolbox.md § 6, § 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md); [cross_domain_ideas.md § Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md)
- Tags: [M] = measured in the notes' micro-benchmarks.

See also: [performance-and-multifidelity](performance-and-multifidelity.md) · [placement/packing-and-graph-drawing-transplants](../placement/packing-and-graph-drawing-transplants.md) · [recommended-stack](recommended-stack.md)
