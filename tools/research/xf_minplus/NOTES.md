<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# xf_minplus: status notes (stopped early, moved to a bigger machine)

This is the T1 min-plus best-response maps experiment
([transformations.md](../../../research_notes/transformations/transformations.md) §5.1). It was stopped before any benchmark runs, so it has no results and no verdict.

## Code
- `minplus.py`
  - `MinPlus`: priced costs min-pooled to a coarse grid (default 0.4 mm). The cell price is (1+hist)(1+β·foreign) and the via price is via_cost(1+Σhist)(1+β·foreign over all layers), as in the router. The net's own copper is not counted as foreign.
  - It runs a numba multi-source Dijkstra per (net, moving part) from that net's pins on the other parts. With `mp_tree`, the sources are also the routed tree minus the paths that end on the moving part's pads.
  - The part map is a sum over nets of the min over that net's pads (and over each pad's copper) of the shifted fields, then bilinear upsampling. Unreachable cells cost a board perimeter.
- `MPCollapse` subclasses jc's `Collapse` and blends `minplus_w` with the HPWL + tension term. The plug-ins `xf`, `xf_lv`, `xf_h`, `xf_lv_h` and `xf0` (the control, which should equal jc) wrap the frozen `kae-work/jc-snap/jc_v3.py` by swapping its `Collapse` class.
- `validate.py`: per-move Spearman test. It runs jc's lift and collapse iterations, samples local moves (within 3 mm) and global moves for random parts at the chosen betas, re-routes the part's nets at the current price, and compares the HPWL, jc-term and min-plus predictors against the routed cost and the priced cost.

## Findings so far (one board only, not trustworthy yet)
- Board: `pcbcorpus-tmarhguy-alu-gate-xor-2in`, 6 parts per beta, betas 1/5/20, 142 moves.
- Within-part Spearman on local moves: HPWL 0.88, jc term 0.86, min-plus 0.62–0.69. Pooled: HPWL 0.95, min-plus 0.79.
- Changing the coarse grid (0.2 mm), the pad shape or the tree sources barely changed this.
- **Probable bug, not yet fixed.** A debug script read `field(n, pi)` at the moving part's own terminal cells and got large negative values (about −1e6). Dijkstra distances can never be negative, so something is wrong. Candidates: overflow in the shared numba heap (`router._push/_pop` with this module's `hk/hv` sizes), or the stale-entry check in `dijkstra`.
  - Until a hand-checked 2-pin net matches its routed priced cost, treat the min-plus correlations above as unreliable.
  - The debug script was in the scratchpad and is not kept. It: lifts, runs 8 iterations, then for each net of a part compares `D` at the pad against the priced cost with the part minus without it.
- Bug or not, the jc-term predictor is already strong here (0.86–0.88 within part). Fields measured to the nearest pin also leave out how the rest of the net's tree changes, which the full-net HPWL captures.

## Next steps
1. Fix or confirm the Dijkstra values with a unit test on a hand-made grid, then rerun `validate.py` on dev6.
2. Then dev6 and ab33 runs of `xf` and `xf_lv` (120 CPU-s, -k 3) against `jcollapse-jc-ab33-v3` and `pnr-combo-v5`, scored with `kae-work/score_all.sh`.
