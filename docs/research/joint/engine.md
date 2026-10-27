# pnr engine: halo-grid world, PathFinder router, FFT legal maps, fast router, anytime output

**Status:** worked (substrate); the fast router worked on thin evidence; anytime output is engineering, untested in isolation.
**First published:** 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6`.

A self-contained place-and-route engine, so that placement and routing can be searched together
without calling Freerouting. Every joint method in this area runs on it. Routing human placements,
it reached clean boards more often than the repo's tuned Freerouting, in seconds instead of up to 600 s.

## Idea and how it works

**Board model (`kicad_io.py`, `world.py`).** `kicad_io.py` runs under KiCad's Python (pcbnew). It
extracts the outline, design rules, nets and netclasses, and footprints: pads, courtyards, keep-outs,
footprint copper, Edge.Cuts cut-outs and rule areas. It writes poses, tracks and vias back.
`world.py` rasterizes everything onto a 0.1 mm grid per copper layer.

**Clearance by halos.** Every copper object stamps its copper, dilated by clearance plus the
half-width of the object tested against it, into per-net count maps:
- `occT[net, layer, y, x]`: a track centre is forbidden here;
- `occV[net, layer, y, x]`: a via centre is forbidden here.

`DT` and `DV` count distinct nets per cell, so the number of foreign nets at a cell for net n is
`D − (occ[n] > 0)`. A 0.75-cell margin covers centreline sampling error. Courtyards, plus pad
keep-outs, thermal-spoke corridors, mask-aperture gaps and hole keep-outs, are counted per side in
`world.court`.

**Router (`router.py`).**
- numba multi-source / multi-target A*. Cell cost `(1 + hist) · (1 + pres · foreign)`, infinite on
  static blocks or in hard mode. A via costs `via_cost` times the same factor summed over layers.
- Multi-pin nets grow Prim-style: from the current tree to the nearest unconnected pad.
- `pathfinder()`: VPR-style negotiated congestion (present cost `pres` rises per pass, history
  `hist` accumulates on shared cells), then `legalize`: conflicted nets are re-routed in hard mode
  or dropped. Output copper is DRC-legal by construction.

**Placement kit (`placekit.py`).**
- `legal_map(i, rot)`: FFT correlation of the occupancy planes with the part's raster gives every
  legal origin of part i at rotation `rot` at once.
- Separable `hpwl_map`, candidate generation, snapshot/restore of routes.
- `total_cost()` = routed mm + 2 mm per via + one board perimeter per unrouted connection.
- `Clock`: budget in **process CPU seconds**, not wall time.

`methods.py:route_only` keeps the input placement and negotiates routes.

### Fast router (`PNR_FAST`, 2026-10-26)

Profiling with `router.PROF` (A* expansions counted by phase, search kind and net fanout) showed that
whole-tree multi-source searches on big nets were 77% of all A* work. Whole-net drops in `legalize`
also made `jc` bimodal: a seed either routed well or lost whole nets. Switches, set as a comma list
in env `PNR_FAST`:

| switch | change |
|---|---|
| D | connect the terminal nearest the tree, sourcing only tree cells near it |
| L | hard-mode (legalize) searches skip the full-grid retry |
| K | a net that cannot reach a terminal continues as a forest (one break counted, not all remaining terminals) |
| B | stop PathFinder after `PNR_STALL` (default 8) passes without progress |
| R | legalize the best pass seen, not the last |
| J | connection-level legalize: drop only the conflicting connections of a conflicted net, group its pins and kept paths into connected pieces, rejoin them in hard mode |
| A, C | reroute only conflicted nets; widen the box before full retry. Did not pay off |

The default is `D,L,K,B,R,J`. `PNR_FAST=none` reproduces the original router bit for bit (checked:
identical tracks and vias on a 126-part board).

### Anytime output (`anytime.py`, 2026-10-27)

Restart wrappers (`tools/kaeres/restart.py`) judge the board left when an attempt exits and kill at a
deadline. pnr methods used to write only at the end and ran the final PathFinder outside the CPU
clock. `anytime.py` hooks every `Router.legalize` (end of each PathFinder call, `Kit.reroute`, the
final legalize). If pnr's own checks pass (all parts placed, no routed net in conflict, no overlap or
part outside the board, no stale copper) and the state leaves fewer connections open (tie-break:
routed length, then vias), the board is written through KiCad to a temp file and moved into place
with `os.replace` in a background thread. A complete legal board raises `Routed` and ends the attempt
(`--stop-when-routed`). PathFinder passes and repair stop at budget × (1 + overrun).

## What we tried

Route tasks on human placements of the 33 qualified A/B boards ("ab33", ≤ 31 and 32–200 pads),
KiCad 10.0.7, DRC by `kicad-cli` as the judge. The fast router was measured on single boards only.

**Two evaluation eras, not comparable.** The joint pages quote numbers from two eras:
- **v5 era:** engine v5, harness v3, `--kinds place --probe self` (the method places; the probe routes),
  mostly **1 seed**.
- **v7 / xf3 era:** harness score v7, `--kinds joint` (the method places and routes in one output),
  engine v6.3 ([c78c537](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c78c537d0b4928fb4505065a39d07934887c577b))
  or the fixed engine ([4c4330a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4c4330a97b4bd1e1ee735a441674f095be12d458), "xf3"),
  **3 seeds**. The headline set is 28 boards that engine v6.4 leaves unchanged
  ([v63-v64-unchanged.txt](../../../tools/research/pnr/results/v63-v64-unchanged.txt)).

Engine versions v3 to v6.4 each fixed one DRC class: footprint rule areas, anchored Edge.Cuts
footprints, footprint copper graphics, custom ring-pad terminals, a whole-pad edge test, board copper
drawings and copper text as pad obstacles
([v7-bugs.md](../../../tools/research/pnr/results/v7-bugs.md)). Runs compare only within one engine
version.

## Results

| setting | human placement routed by | A clean | B clean | time | source |
|---|---|---|---|---|---|
| v5, route tasks, ab33 (13 A, 20 B boards) | pnr `route_only` | 0.846 | 0.500 | 7.6 / 12.6 s mean wall per board (A / B) | [route-only-v5.md](../../../tools/research/pnr/results/route-only-v5.md), [2a1c9c1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2a1c9c1f6213e7e289bea7e014c0e9b5c90b6328) |
| v5, same boards | tuned Freerouting (repo default) | 0.62 | 0.35 | ≤ 600 s | [scorecard.md](../../ideas/original/scorecard.md) (row "Own grid router") |
| v7, route task, k = 1 | pnr `route_only` | 0.923 | 0.500 | — | [v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md) (33 boards: clean 0.667, completion 0.927) |

Fast router (commits [bf06b18](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bf06b1816fc4707e2fa041286600dc706231b2ca),
[eaf1719](https://github.com/magnetic-trowel/kicad-auto-everything/commit/eaf1719b8c33c5070f5b3875c92ab8723a9771f4);
**evidence on 2 boards only**, numbers from the commit messages):

| board, method | unrouted connections, fast | original | CPU saving |
|---|---|---|---|
| 126-part board, `jc`, 4 seeds | 74 / 75 / 74 / 75 of 320 | 179 / 81 / 92 / 80 | 1.7–3.5× |
| same, `jc` with D,L,K,B,R but no J | 166 / 165 / 76 / 166 | — | — |
| 126-part board, `seq` | 76 | 192 | 4.8× |
| 126-part board, `route_only` | 59 | 163 | 6.8× |
| 104-part board, `route_only` | 46 of 224 | 76 | 2× |

No ab33 run of the fast router exists. Anytime output has no benchmark of its own.

## Verdict

- **Engine: worked.** It is fast enough to route thousands of candidate placements per board within
  120 CPU-s, which every method here depends on.
- **Known limits.** Its legality model is stricter than KiCad: it rejects the human placement on 13 of
  33 boards (four-way spoke corridors, mask apertures). Silkscreen and graphic mask openings are not
  modelled (silk errors stay in outputs). 0.5 mm-pitch pads are sometimes unenterable. Left: a
  silkscreen plane, neck-down near fine-pitch pads, a less strict spoke model.
- **Fast router: worked, thin evidence.** Connection-level legalize (J) removed jc's bimodality on the
  one board where it was measured. It needs a suite-level run.
- **Anytime output:** needed for fair restart wrappers. Untested on its own.

All 22 pnr arms of the merit list (`tools/kaeres/experiments/merit-restart.sh`) run on this engine at
[957a37f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/957a37fd0d58483e0b8194d24ab47cfd69c56d9d)
(fast router + anytime output). `pnr route_only` is itself a merit arm. The 500-board comparison
(experiments `merit-500r3` / `merit-500r3k`) is running.
Results on the 500-board comparison: pending.

## Code

- [`tools/research/pnr/`](../../../tools/research/pnr/): `world.py`, `router.py` (switch docs near the
  top), `placekit.py`, `raster.py`, `kicad_io.py`, `run.py`, `anytime.py`, `methods.py`; tests
  `test_world.py`, `test_anytime.py`; suites `suites/*.txt` (board ids only); per-era results
  `results/*.md`; method-writer brief `AGENT_BRIEF.md`.
- Entry: `python tools/research/pnr/run.py <module.py:fn> IN.kicad_pcb OUT.kicad_pcb --budget 120 --seed N`,
  or `tools/research/xf_common/xf_run.sh` for harness runs. `run.py` writes `pnr_summary.json` with the
  A* work counters.
- Deps: numpy, numba, scipy, shapely (tests), KiCad 10 Python via the `KAE_KICAD_PYTHON` wrapper
  ([`xf_common/kicad-python`](../../../tools/research/xf_common/kicad-python)). Physics methods need
  the kae package (`KAE_SRC`).
- Tests: `NUMBA_CACHE_DIR=... python -m pytest tools/research/pnr/test_world.py tools/research/pnr/test_anytime.py`.

## Related

- [physics-objective.md](physics-objective.md): physics terms used by most methods.
- [jc.md](jc.md): the method the fast router was tuned for.
- Experiment log: [joint-pnr-experiments.md](../../topics/placement/joint-pnr-experiments.md);
  scorecard: [scorecard.md](../../ideas/original/scorecard.md).
