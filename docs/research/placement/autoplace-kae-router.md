# autoplace with kae's router in the loop, and the speed-ups

**Status:** not finished. The variant runs in the 500-board comparison; no result yet.
**First published:** 2026-10-26, commit [46e7f89](https://github.com/magnetic-trowel/kicad-auto-everything/commit/46e7f894e8357fad7d6f3f0e9093f5515a097ed6) on branch `autoplace-experiments` (speed-ups [eb39565](https://github.com/magnetic-trowel/kicad-auto-everything/commit/eb395651b95ead5a8575befff9527bc2b91e9f12) and [54be032](https://github.com/magnetic-trowel/kicad-auto-everything/commit/54be03254b821394bc218ecb9a9d71c7914d5e70), 2026-10-27).

The `sa-loop` repair placer ([autoplace.md](autoplace.md)) with the physics-first kae router's bridge as the in-loop router instead of Freerouting, plus two exact speed-ups of the placer's geometry kernels that give bit-identical placements for 15–25 % less CPU.

## Idea and how it works

**Why another router.** Freerouting closes few boards even on human placements, so `sa-loop`'s repair rounds chased the router's failures instead of the placement's (`46e7f89`). With `--router kae`, each candidate placement is routed by `python -m kae.route.cli route <board> <out> --time max(20, T − 15)` in the placer's own interpreter (kae must be importable), with a hard limit of T + 60 s. Everything else is unchanged: the routed candidate is DRC'd by `kicad-cli` under the board's own rules, parts on unrouted nets or named in error-level DRC items are blamed, failed nets get weight × 3 and blamed parts +0.3 mm halo, and a round is kept only if (unrouted, errors, vias, length) improves. The default stays Freerouting, as tested on the 14-board suite.

**Speed-up 1: region test, crossings, masks (`eb39565`).**
- *Cell-grid containment.* Each allowed region is rasterized once into a 256 × 256 grid; shapely classifies every cell as inside, disjoint or boundary. A query box covered only by inside cells is contained; a box touching a disjoint cell or leaving the grid bounds is not; only boxes overlapping boundary cells still go to shapely. Used by the legalizer's candidate masks (now applied last, to the candidates that survive the overlap tests) and by `State._outside`.
- *Crossings.* `_crossings` skips segment pairs with disjoint bounding boxes (they cannot properly cross); `_within` counts all net pairs in one vectorized call instead of one call per pair.
- *Legalizer obstacles* are tested one obstacle at a time instead of materializing a candidates × obstacles array; `np.unique(axis=0)` in `_mst` and `np.clip` in `_overlap` replaced by cheaper equivalents.

**Speed-up 2: separable overlap masks (`54be032`).** The legalizer's candidate centres form a meshgrid (`nx` columns × `ny` rows). A rectangle obstacle overlaps a candidate iff its x-interval overlaps the candidate column's and its y-interval the candidate row's, so the test splits into one column test and one row test, and the blocked set is the band rows × columns. Clearing that band costs O(nx + ny + band) per obstacle instead of O(nx · ny). The column and row bounds use the same floating-point expressions as before, so the masks are bit-identical; non-grid candidates keep the old loop. At the 0.05 mm step this removed ~750k-candidate temporaries per obstacle.

## What we tried

- **kae router:** the method `autoplace sa-loop kae (restarts)` in `tools/kaeres/experiments/merit-restart.sh` (place-fixed task, one attempt with a 1,200 s base budget, wrapped in the restart portfolio of `tools/kaeres/restart.py`, code pinned at `54be032`; the probe is kae's bridge with restarts). It is one of the merit methods; the 500-board comparison (experiments `merit-500r3` / `merit-500r3k`) is running.
- **Speed-ups:** old vs new code on three boards (small, medium, large place-fixed tasks), seeds 0 and 1, same geometry extract; plus end-to-end CLI runs through KiCad extraction and writing.

## Results

- Results on the 500-board comparison: pending.
- Speed-ups (from the commit messages of `eb39565` and `54be032`): poses, rotations, costs, crossings and violations bit-identical to the previous version on 3 boards × 2 seeds; CLI output boards byte-identical; placement CPU 15–25 % lower after `54be032`. Re-checked when importing the code to main: `--algo sa --seed 0` on the 19-part test board writes a byte-identical `.kicad_pcb` from `tools/research/autoplace` and from the `54be032` checkout.

## Verdict

Pending the 500-board comparison. The speed-ups are exact and safe to keep; they do not change the scaling problem of [autoplace.md](autoplace.md) (pure-Python SA at ~1,000 moves/s), which needs a compiled cost kernel. A fair reading of the kae variant also needs the kae bridge's own clean rate on the human placements of the same boards, since the loop can only be as good as its in-loop router.

## Code

`tools/research/autoplace/place.py --router kae` (`_route_kae`, `route_probe`); speed-ups in `_Cells`, `_crossings`, `_within`, `_legal_mask`. `kae` itself is described in the routing area.

## Related

- [autoplace.md](autoplace.md): the placer, arms and 14-board results.
- [Placement area map](README.md); [routing area map](../routing/README.md) for kae.
