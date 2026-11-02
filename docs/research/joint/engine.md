# pnr engine: halo-grid world, PathFinder router, FFT legal maps, fast router, anytime output

**Status:** worked (substrate); the fast router worked on thin evidence; anytime output is engineering, untested in isolation.
**First published:** 2026-10-24, commit [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a) on branch `claude/keen-wright-mlkjv6`.

Scope: the self-contained place-and-route engine every pnr method runs on (no Freerouting call), and `route_only` on human placements. Not here: eras and suites -> [README](README.md#eras-and-caveats); methods -> sibling pages.
Keys: pnr engine, halo grid, occT, occV, PathFinder, negotiated congestion, legalize, FFT legal map, `legal_map`, `hpwl_map`, `total_cost`, Clock, CPU seconds, `route_only`, fast router, `PNR_FAST`, `PNR_STALL`, connection-level legalize, anytime output, `anytime.py`, `--stop-when-routed`

## Idea and how it works

**Board model.** `kicad_io.py` (runs under KiCad's pcbnew Python) extracts outline, design rules, nets, netclasses and footprints (pads, courtyards, keep-outs, footprint copper, Edge.Cuts cut-outs, rule areas) and writes poses, tracks and vias back. `world.py` rasterizes onto a 0.1 mm grid per copper layer.

**Clearance by halos.** Each copper object stamps its copper dilated by clearance + half-width of the tested object into per-net count maps:
- `occT[net, layer, y, x]`: track centre forbidden; `occV[net, layer, y, x]`: via centre forbidden.
- `DT`, `DV` count distinct nets per cell; foreign nets at a cell for net n = `D − (occ[n] > 0)`.
- 0.75-cell margin covers centreline sampling error.
- `world.court` counts per side: courtyards, pad keep-outs, thermal-spoke corridors, mask-aperture gaps, hole keep-outs.

**Router (`router.py`).**
- numba multi-source / multi-target A*; cell cost `(1 + hist) · (1 + pres · foreign)`, ∞ on static blocks or in hard mode; a via costs `via_cost` × the same factor summed over layers.
- Multi-pin nets grow Prim-style: current tree → nearest unconnected pad.
- `pathfinder()`: VPR-style negotiated congestion (`pres` rises per pass, `hist` accumulates on shared cells), then `legalize`: conflicted nets re-routed in hard mode or dropped. Output copper is DRC-legal by construction.

**Placement kit (`placekit.py`).**
- `legal_map(i, rot)`: FFT correlation of occupancy planes with part i's raster → every legal origin at rotation `rot` at once.
- Separable `hpwl_map`, candidate generation, snapshot/restore of routes.
- `total_cost()` = routed mm + 2 mm per via + one board perimeter per unrouted connection.
- `Clock`: budget in **process CPU seconds**, not wall time.

`methods.py:route_only` keeps the input placement and negotiates routes.

### Fast router (`PNR_FAST`, 2026-10-26)

Profiling (`router.PROF`: A* expansions by phase, search kind, net fanout): whole-tree multi-source searches on big nets = 77% of all A* work. Whole-net drops in `legalize` made `jc` bimodal (a seed routed well or lost whole nets). Switches, comma list in env `PNR_FAST`:

| switch | change |
|---|---|
| D | connect the terminal nearest the tree, sourcing only tree cells near it |
| L | hard-mode (legalize) searches skip the full-grid retry |
| K | a net that cannot reach a terminal continues as a forest (one break counted, not all remaining terminals) |
| B | stop PathFinder after `PNR_STALL` (default 8) passes without progress |
| R | legalize the best pass seen, not the last |
| J | connection-level legalize: drop only the conflicting connections of a conflicted net, group its pins and kept paths into connected pieces, rejoin them in hard mode |
| A, C | reroute only conflicted nets; widen the box before full retry. Did not pay off |

Default `D,L,K,B,R,J`. `PNR_FAST=none` reproduces the original router bit for bit (checked: identical tracks and vias on a 126-part board).

### Anytime output (`anytime.py`, 2026-10-27)

Need: restart wrappers (`tools/kaeres/restart.py`) judge the board left when an attempt exits and kill at a deadline; pnr methods used to write only at the end and ran the final PathFinder outside the CPU clock.
- Hooks every `Router.legalize` (end of each PathFinder call, `Kit.reroute`, final legalize).
- Write condition: pnr's own checks pass (all parts placed, no routed net in conflict, no overlap or part outside the board, no stale copper) and fewer connections open (tie-break: routed length, then vias).
- Write: through KiCad to a temp file, `os.replace` into place, in a background thread.
- A complete legal board raises `Routed` and ends the attempt (`--stop-when-routed`). PathFinder passes and repair stop at budget × (1 + overrun).

## What we tried

Route tasks on human placements of ab33, KiCad 10.0.7, `kicad-cli` DRC as judge. Eras: [README](README.md#eras-and-caveats). Fast router: single boards only.

### Engine versions

Each version fixes a DRC class found in runs; bug log [v7-bugs.md](../../../tools/research/pnr/results/v7-bugs.md). v3 to v5 also added footprint rule areas, anchored Edge.Cuts footprints and footprint copper graphics.

| engine | fix |
|---|---|
| v5 | courtyards per side, pad keep-outs per copper layer, pad-local clearances, hole keep-outs, thermal-spoke room ([world.py](../../../tools/research/pnr/world.py)) |
| v6 | solder-mask apertures between pads; holes under courtyards on both sides |
| v6.1–6.2 | footprint keep-outs; footprint copper drawings become no-net copper |
| v6.3 ([c78c537](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c78c537d0b4928fb4505065a39d07934887c577b)) | pad terminals from KiCad's inner outline (custom ring pads); edge test covers whole pads |
| v6.4 (merged 9db768f, 9 tests pass) | board copper drawings and copper text are pad obstacles; `.kicad_dru` edge clearance; merged with the benchmark-host fix [4c4330a](https://github.com/magnetic-trowel/kicad-auto-everything/commit/4c4330a97b4bd1e1ee735a441674f095be12d458); changes 5 of 33 boards |

Legality calibration against the human boards: the first model counted 22 of 33 human placements illegal (through-hole parts blocked both sides, courtyards could not overhang the board edge, courtyards drawn on the other side went unread); v5: 12, each by ~0.1 mm of raster rounding; legal rate 0.39 → 0.79. Other v3–v5 fixes, each found as DRC errors: pad-local clearances, NPTH hole keep-outs, footprint Edge.Cuts, duplicate UUIDs, courtyards smaller than pads. (Verdict below: 13 of 33 under the later model.)

## Results

| setting | human placement routed by | A clean | B clean | time | source |
|---|---|---|---|---|---|
| v5, route tasks, ab33 (13 A, 20 B boards) | pnr `route_only` | 0.846 | 0.500 | 7.6 / 12.6 s mean wall per board (A / B) | [route-only-v5.md](../../../tools/research/pnr/results/route-only-v5.md), [2a1c9c1](https://github.com/magnetic-trowel/kicad-auto-everything/commit/2a1c9c1f6213e7e289bea7e014c0e9b5c90b6328) |
| v5, same boards | tuned Freerouting (repo default) | 0.62 | 0.35 | ≤ 600 s | [scorecard.md](../../ideas/original/scorecard.md) (row "Own grid router") |
| v7, route task, k = 1 | pnr `route_only` | 0.923 | 0.500 | — | [v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md) (33 boards: clean 0.667, completion 0.927) |

Fast router, **2 boards only**, numbers from commit messages [bf06b18](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bf06b1816fc4707e2fa041286600dc706231b2ca), [eaf1719](https://github.com/magnetic-trowel/kicad-auto-everything/commit/eaf1719b8c33c5070f5b3875c92ab8723a9771f4):

| board, method | unrouted connections, fast | original | CPU saving |
|---|---|---|---|
| 126-part board, `jc`, 4 seeds | 74 / 75 / 74 / 75 of 320 | 179 / 81 / 92 / 80 | 1.7–3.5× |
| same, `jc` with D,L,K,B,R but no J | 166 / 165 / 76 / 166 | — | — |
| 126-part board, `seq` | 76 | 192 | 4.8× |
| 126-part board, `route_only` | 59 | 163 | 6.8× |
| 104-part board, `route_only` | 46 of 224 | 76 | 2× |

No ab33 run of the fast router; no benchmark of anytime output alone.

## Verdict

- **Engine: worked.** Routes thousands of candidate placements per board within 120 CPU-s; every method here depends on it.
- **Known limits.** Legality model stricter than KiCad: rejects the human placement on 13 of 33 boards (four-way spoke corridors, mask apertures). To do: a silkscreen plane, neck-down near fine-pitch pads, a less strict spoke model. DRC classes that cap clean pass for every method (no objective sees them; each traced to placement crowding, not routing; counts from the `seq` and `beam` runs):

| DRC error | cause | status |
|---|---|---|
| `silk_overlap` (error on some boards) | neighbours' silkscreen overlaps; no silkscreen plane | open: silkscreen keep-outs where it is an error |
| `solder_mask_bridge` | mask expansion 0.2 mm on some boards: two pad apertures merge, or a track sits inside an aperture | fixed in the dev engine (pad gap ≥ 2·expansion + web) |
| `starved_thermal` | neighbours' pads crowd a zone pad's relief spokes; deleting every other-net track does not help | thermal-spoke corridors in the placement keep-out: 3 → 1 on olimex |
| `shorting_items` | one board has board-level copper arcs | wires avoid them; parts do not yet |
| unrouted on dense sensor boards | 0.5 mm-pitch pads no track can enter at the board's clearance | open: neck-down near pads |
- **Fast router: worked, thin evidence.** Connection-level legalize (J) removed jc's bimodality on the one board measured.
- **Anytime output:** needed for fair restart wrappers; untested alone.
- Merit arm: `pnr route_only` ([merit list](README.md#merit-list)).

## Open questions

- Suite-level run of the fast router.
- The 5-board engine v6.4 re-runs (`-r4cu`) are unfinished.

## Code

- [`tools/research/pnr/`](../../../tools/research/pnr/): `world.py`, `router.py` (switch docs near the top), `placekit.py`, `raster.py`, `kicad_io.py`, `run.py`, `anytime.py`, `methods.py`; tests `test_world.py`, `test_anytime.py`; suites `suites/*.txt` (board ids only); per-era results `results/*.md`; method-writer brief `AGENT_BRIEF.md`.
- Entry: `python tools/research/pnr/run.py <module.py:fn> IN.kicad_pcb OUT.kicad_pcb --budget 120 --seed N`, or `tools/research/xf_common/xf_run.sh` for harness runs. `run.py` writes `pnr_summary.json` with the A* work counters.
- Deps: numpy, numba, scipy, shapely (tests), KiCad 10 Python via the `KAE_KICAD_PYTHON` wrapper ([`xf_common/kicad-python`](../../../tools/research/xf_common/kicad-python)). Physics methods need the kae package (`KAE_SRC`).
- Tests: `NUMBA_CACHE_DIR=... python -m pytest tools/research/pnr/test_world.py tools/research/pnr/test_anytime.py`.

## Related

[physics-objective.md](physics-objective.md) (physics terms), [jc.md](jc.md) (what the fast router was tuned for), [joint-pnr-experiments.md](../../topics/placement/joint-pnr-experiments.md), [scorecard.md](../../ideas/original/scorecard.md).
