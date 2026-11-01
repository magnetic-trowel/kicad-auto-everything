<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Field-solver routing and intent (branch `physics-functional-eval`, 2026-10-27 .. 11-01)

A raster PEEC field solver ([physics-frequency-coverage](../../topics/architecture/physics-frequency-coverage.md)) became an evaluator of whole boards and a router's price, and then the question of what "better" means moved to the commander's intent ([intent-driven-objectives](../../topics/architecture/intent-driven-objectives.md)). Everything here is model against model unless a KiCad DRC result is quoted.

**Read this first.** Until 2026-10-31 every router A/B on this branch started from the human layout: `kae.em.pnr` ripped only the nets it priced and kept every other human trace, and a multi-pass fallback briefly gave unfinished nets their human copper back. Those A/Bs measure re-routing inside a finished board, not routing a new one. Only results from `tools/research/physics/new_board.sh` (routing stripped first, as the benchmark's route task) count as routing a board.

## What worked

| Path | Result | Code |
|---|---|---|
| Reduced-order model over DC .. quasi-static limit | One Galerkin model per board; R2 gate passes on boost (2.7e-4) and chaac 4-layer (2.6e-4, 10 Hz .. 98 MHz) once the reduced solves are equilibrated and the error estimate keeps the model's own residual term (the old estimate was blind at kHz, true error 0.42) | `kae/src/kae/em/reduce.py`, `tools/research/physics/em_reduce_gate.py` |
| True DC limit | Parts given by an impedance function read 1000 rad/s at "DC"; now their limit (capacitors open) | `kae/src/kae/em/mesh.py` |
| Evaluator speed | Factorization cache within a memory budget, snapshot reuses the estimate's factor: boost whole-spectrum evaluation 3553 s → 1279 s, about 4x the RAM (`KAE_EM_FACTOR_GB`) | `reduce.py`, `solve.py` |
| Whole-spectrum evaluator | Losses, waveform peaks, CISPR per harmonic, capacitive coupling, thermal, radiation | `kae/src/kae/excite/wideband.py` and siblings |
| Clock drivers from pin types | DRAM inputs no longer drive their own clock; a clock leaving through a connector loads it there | `kae/src/kae/excite/sources.py` |
| Thin tracks on the raster | Fine-pitch neighbours shared raster cells and broke each other's chains (false opens); skipped cells are bridged with the track's R and L | `kae/src/kae/em/mesh.py` (`bridge_gaps`) |
| Intent and observations | The evaluator keeps physical values per corner; `kae.intent` scores them under an intent (sections, boundaries, tiers, rates, status); legacy profile reproduces the old totals exactly | `kae/src/kae/intent/`, `python -m kae.intent` |
| Intent widths, closed form | Width = sqrt(k_R rho / (t a)) from the intent's loss and drop rates and an explicit area cost; boost from its bare placement, complete and DRC-clean: copper loss 20.5 mW (human 53.6, Freerouting alone 160) | `kae/src/kae/intent/route.py`, `kae.em.pnr --intent` |
| Intent-scoped physics | Only the (observer, aggressor) pairs the intent names are solved and only their nets routed with fields: boost 4 of 9 pairs, 6.5 min (whole-board physics 35 min, chaac 6.4 h) | `kae/src/kae/em/pnr.py` |
| Route viewer | Interactive side-by-side page of several routings of one board | `tools/research/physics/route_view/` |

## What did not work

| Path | Why | Code (kept) |
|---|---|---|
| Objective as a sum of phi(u = size / assumed bound) | Assumed bounds are hidden exchange rates: a 1 m-cable-on-every-connector emission term (u ≈ 20) outweighed 3.5x copper loss, so 0.2 mm power traces "won" | `kae/src/kae/excite/harm.py`; replaced by `kae.intent` |
| Whole-board physics routing | Hours per board (chaac 6.4 h), and it optimized the objective above | `kae/src/kae/em/pnr.py` without `--intent` |
| Hop ports (R4b) | Better two-band score, worse wideband (2899 vs 806): cable common mode near 72–77 MHz | `kae/src/kae/em/hopport.py`, `tools/research/physics/em_r4b_check.py` |
| Router prediction vs evaluator | The router prices one band; the evaluator two. Under a feedback-pin contract the physics route made pickup worse (11.4 mV vs Freerouting 5.6, limit 2) | `pnr.py` `_weights` |
| Power nets first, locked, then Freerouting | Complete on boost; on denser boards the locked copper walls in the rest: unconnected chaac 3 (Freerouting alone 0), ddr5 27 (1), echoplayer 62 (22) | `new_board.sh kae-plain` |
| Falling back to human copper | Meaningless for new boards; hid that the router could not route the DRAM rails | `pnr.route_whole` (now: leave unfinished nets to the completion router) |
| Flux batching, warm-started snapshots, larger preconditioner patches | No speed gain | not adopted |

## Next

Give the intent's widths to the completion router as KiCad net-class rules (one routing pass, power at intent widths, DRC checks the same rules); price with the evaluator's two bands before trusting contracts; per-section field windows. Comparison pages of these runs: published privately as artifacts, regenerated with `route_view.py`.
