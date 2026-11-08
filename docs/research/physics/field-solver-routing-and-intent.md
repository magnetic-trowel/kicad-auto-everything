<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Field-solver routing and intent (branch `physics-functional-eval`, 2026-10-27 .. 11-01)

Scope: a raster PEEC field solver ([physics-frequency-coverage](../../topics/architecture/physics-frequency-coverage.md)) as whole-board evaluator and router price, then "better" defined by the commander's intent ([intent-driven-objectives](../../topics/architecture/intent-driven-objectives.md)). Model against model unless a KiCad DRC result is quoted.
Keys: `kae.em`, `kae.excite`, `kae.intent`, reduced-order model, R2 gate, wideband evaluator, intent widths, intent-scoped physics, hop ports R4b, `new_board.sh`, route viewer, boost, chaac

**Validity caveat:** until 2026-10-31 every router A/B on this branch started from the human layout: `kae.em.pnr` ripped only the nets it priced and kept every other human trace, and a multi-pass fallback briefly gave unfinished nets their human copper back. Those A/Bs measure re-routing inside a finished board. Only results from `tools/research/physics/new_board.sh` (routing stripped first, as the benchmark's route task) count as routing a board.

## What worked

| Path | Result | Code |
|---|---|---|
| Reduced-order model over DC .. quasi-static limit | One Galerkin model per board; R2 gate passes on boost (2.7e-4) and chaac 4-layer (2.6e-4, 10 Hz .. 98 MHz) once the reduced solves are equilibrated and the error estimate keeps the model's own residual term (old estimate blind at kHz, true error 0.42) | `kae/src/kae/em/reduce.py`, `tools/research/physics/em_reduce_gate.py` |
| True DC limit | Parts given by an impedance function read 1000 rad/s at "DC"; now their limit (capacitors open) | `kae/src/kae/em/mesh.py` |
| Evaluator speed | Factorization cache within a memory budget, snapshot reuses the estimate's factor: boost whole-spectrum evaluation 3553 s → 1279 s, ~4x the RAM (`KAE_EM_FACTOR_GB`) | `reduce.py`, `solve.py` |
| Whole-spectrum evaluator | Losses, waveform peaks, CISPR per harmonic, capacitive coupling, thermal, radiation | `kae/src/kae/excite/wideband.py` and siblings |
| Clock drivers from pin types | DRAM inputs no longer drive their own clock; a clock leaving through a connector loads it there | `kae/src/kae/excite/sources.py` |
| Thin tracks on the raster | Fine-pitch neighbours shared raster cells and broke each other's chains (false opens); skipped cells bridged with the track's R and L | `kae/src/kae/em/mesh.py` (`bridge_gaps`) |
| Intent and observations | Evaluator keeps physical values per corner; `kae.intent` scores them under an intent (sections, boundaries, tiers, rates, status); legacy profile reproduces the old totals exactly | `kae/src/kae/intent/`, `python -m kae.intent` |
| Intent widths, closed form | Width = sqrt(k_R rho / (t a)) from the intent's loss and drop rates and an explicit area cost; boost from its bare placement, complete and DRC-clean: copper loss 20.5 mW (human 53.6, Freerouting alone 160) | `kae/src/kae/intent/route.py`, `kae.em.pnr --intent` |
| Intent-scoped physics | Only the (observer, aggressor) pairs the intent names are solved and only their nets routed with fields: boost 4 of 9 pairs, 6.5 min (whole-board physics 35 min, chaac 6.4 h) | `kae/src/kae/em/pnr.py` |
| Route viewer | Interactive side-by-side page of several routings of one board | `tools/research/physics/route_view/` |

## What did not work

| Path | Why | Code (kept) |
|---|---|---|
| Objective as a sum of phi(u = size / assumed bound) | Assumed bounds are hidden exchange rates. Boost: a 1 m-cable-on-every-connector emission term (u ≈ 18–23, ~2,000 points) swamped 3.5x the copper loss (37 → 128 mW), ~2x the heating and 3x the drop (~30 points together), so 0.2 mm power traces "won". The physics was right (DC copper loss 37 mW vs 5.5 mW for all switching-harmonic copper loss), the priorities wrong | `kae/src/kae/excite/harm.py`; replaced by `kae.intent` |
| Whole-board physics routing | Hours per board (chaac 6.4 h), and it optimized the objective above | `kae/src/kae/em/pnr.py` without `--intent` |
| Hop ports (R4b) | Better two-band score, worse wideband (2899 vs 806): cable common mode near 72–77 MHz | `kae/src/kae/em/hopport.py`, `tools/research/physics/em_r4b_check.py` |
| Router prediction vs evaluator | Router prices one band, evaluator two. Under a feedback-pin contract the physics route made pickup worse (11.4 mV vs Freerouting 5.6, limit 2) | `pnr.py` `_weights` |
| Power nets first, locked, then Freerouting | Complete on boost; on denser boards the locked copper walls in the rest: unconnected chaac 3 (Freerouting alone 0), ddr5 27 (1), echoplayer 62 (22) | `new_board.sh kae-plain` |
| Falling back to human copper | Meaningless for new boards; hid that the router could not route the DRAM rails | `pnr.route_whole` (now: leave unfinished nets to the completion router) |
| Flux batching, warm-started snapshots, larger preconditioner patches | No speed gain | not adopted |

## Open: the neutral area price

`AREA_COST` = 0.05 mW_eq/mm² (`kae/src/kae/intent/route.py`, since 5199c80 without a stated basis) sets every power width when an intent is silent, w* = 3.1 mm/A on 35 µm copper.
- **Economic basis [S][I]:** a 2-layer board at volume costs $0.0003–0.0008/mm² ([PCBCart](https://www.pcbcart.com/article/content/how-much-does-a-pcb-cost)); 1 mW for 5 years at $0.15/kWh is $0.0066; so 0.05–0.12 for an always-on board, about 4× more at 25 % duty.
- **Human layouts [M]:** 147 rail nets carrying ≥ 0.1 A in kae's DC plan on 59 of the 112 suite boards (`tools/research/physics/area_cost_widths.py`). The human p90 width implies a median 0.64 (IQR 0.18–3.4). At 0.3–3 A the median human width is 0.4–0.5 mm, where w*(0.05) is 0.9–3.5 mm; 3 % of human nets are that wide. The plan's currents are priors (0.15–1× ratings), which biases the implied price up.
- **Router widths at 0.05 [M]:** battery and VBUS rails 1.5–3 mm (aura, chaac, echoplayer, boost), 1V8_SYS 2 mm (ddr5); the locked power copper is where completion suffered above.
- **Decided by A/B (area-cost-ab2, kae-plain, 112 qualified boards, k = 1, 2026-11-05) [M]:**

  | area_cost | cp1 | completion | timeouts | no output | physics Σu (94 common boards) |
  |---|---|---|---|---|---|
  | 0.05 | 0.550 | 0.854 | 26 | 12 | 19.18 |
  | 0.2 | 0.555 | 0.903 | 21 | 6 | 19.23 |
  | 0.5 | 0.532 | 0.875 | 20 | 9 | 19.24 |

  No difference is significant: cp1 is within the A/A noise of ±2 pp, and the completion gain of 0.2 over 0.05 has p = 0.08, or 0.23 after Holm. 0.2 is the default because it completed most and timed out least, with the same physics, and sits nearer human practice. Too-hot copper is caught by the `heating_width_capped` hazard.

## Next

1. Give the intent's widths to the completion router as KiCad net-class rules (one routing pass, power at intent widths, DRC checks the same rules).
2. Price with the evaluator's two bands before trusting contracts.
3. Per-section field windows.

Comparison pages of these runs: published privately as artifacts, regenerated with `route_view.py`.
