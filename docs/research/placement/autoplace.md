# autoplace: annealing placer with the router and DRC in the loop

**Status:** partial. Router-in-the-loop repair (`sa-loop`) worked on a 14-board smoke suite; on a larger provisional sample it was much weaker and did not scale to big boards.
**First published:** 2026-10-22, commit [3267001](https://github.com/magnetic-trowel/kicad-auto-everything/commit/32670011f0a3941edfef9629ad6f39fac20f27be) on branch `autoplace-experiments`; results [b3b0896](https://github.com/magnetic-trowel/kicad-auto-everything/commit/b3b08961f8e26555827730f2306c677073d0fca4).

A rectangle placer for kaebench place tasks with five arms: random, greedy, simulated annealing (SA), best-of-N SA picked by routing + DRC, and SA followed by repair rounds that re-anneal only the parts a router and KiCad DRC blame. On 14 small 2-layer boards the repair loop routed clean on 14/14, the same as the human placements, against 9/14 for plain SA. The deciding change was to close the loop on KiCad DRC, not only on connectivity.

## Idea and how it works

**Geometry.** `kicad_helper.py` runs in KiCad's Python (pcbnew) and extracts the board outline, keep-outs, locked footprints, board-level copper and mask items as obstacles, and for each free footprint its rectangle (courtyard bounding box ∪ pads ∪ the footprint's own copper/mask graphics) and pad offsets at 0/90/180/270°, read from pcbnew rather than computed. Footprint sides are kept. The solver (`place.py`, numpy/scipy/shapely) works on these rectangles only.

**Escape halo.** Each part's rectangle grows by `halo = max(0.2 mm, (0.15 + 0.12·√pins) · f)`, where the fill factor `f` is 1 when the rectangles fill ≤ 55 % of the board, 0 at ≥ 75 %, linear between. The halo leaves room for escape routing; at high fill it shrinks to its floor or the legalizer cannot fit the parts.

**Cost.** `C = Σ_nets w_n · HPWL_n + w_x · crossings + overlap/outside penalty`, with
- `w_n` = 0.1 for nets matching a pour/ground pattern, 0.3 for power-net names (regex `POWER_RE`), 1 otherwise;
- `crossings` = number of proper crossings between the segments of per-net ratsnest minimum spanning trees (MST over pad positions), `w_x` = 0.25 × board diagonal per crossing;
- penalty on rectangle(+halo) overlap area and on area outside the allowed region.
Costs are updated incrementally per moved part (`State`).

**Arms (`--algo`):**

| Arm | Mechanism |
|---|---|
| `rand` | Random positions and rotations, then the legalizer. Control: measures the legalizer alone. |
| `greedy` | Place parts one at a time, most connections to already-placed parts first, at the legal grid cell × rotation with least added weighted HPWL (`_incremental_wl`, vectorized over candidate centres from `_legal_mask`). Also the SA seed. |
| `sa` | Greedy seed, then SA with displace, rotate, swap and long-jump moves; budget 1,500 × parts moves, clipped to 20,000–120,000 (a move count, not wall time, so results don't depend on host load); then the legalizer. |
| `sa-best` | Up to 6 SA seeds. Each candidate is routed in the loop (Freerouting, 4 passes) and DRC'd by `kicad-cli` under the board's own `.kicad_pro`/`.kicad_dru`; candidates rank by (unrouted, DRC errors, vias, track length); stop at the first clean one. A lite form of successive halving (idea S6). |
| `sa-loop` | One SA seed, then up to 6 repair rounds: route + DRC as above; blamed parts = owners of pads on unrouted nets (pad clusters from pcbnew connectivity) ∪ footprints named in error-level DRC items; failed nets get weight × 3, blamed parts +0.3 mm halo; re-anneal only the blamed parts. Keep the round if the rank tuple improves, else revert and widen the move radius × 1.5. After KiCadRoutingTools' `place_route_loop` (ideas P1/P4). |

**Legalizer.** Candidate centres are a meshgrid over the board, tried coarse to fine (step = diagonal/150 clipped to 0.1–0.5 mm, then 0.1 mm, then 0.05 mm); the greedy arm uses diagonal/90 clipped to 0.25–1 mm. The overlap penalty weight ramps up ×30 during annealing. For each overlapping or out-of-region part, pick the legal candidate (any of the four rotations) with the least added weighted HPWL; `make_legal` drops halos and shakes out remaining overlaps if needed.

## What we tried

- **Suite:** 14 qualified 2-layer place tasks (`tools/research/autoplace/place-smoke-14.txt`; 6 split A, 8 split B; 4–34 footprints, ≤ 98 pads), one per repo, a seeded draw from boards where Freerouting 2.5.0 routes the human placement clean. The task stacks unlocked footprints off-board at 0°.
- **Score:** kaebench score v5 (task spec 4, KiCad 10.0.7): placement `legal`, then `--probe freerouting` (2.5.0, 10 passes) and KiCad DRC on the rebuilt board. k = 1, 600 s per attempt (1,200 s for v4 `sa-best`/`sa-loop`), 10 cores, bwrap sandbox.
- **Versions:** v3 (code `4b4fba0`) and v4 (`e63bd23`, copper graphics inside footprints counted, DRC in the loop). Ablations on v3 SA: crossing term off (`--cross-w 0`), halo off.

## Results

Attempt 0, 14 boards, single seed unless noted. Source: `docs/topics/placement/autoplace-experiments-2026-10.md` at [b3b0896](https://github.com/magnetic-trowel/kicad-auto-everything/commit/b3b08961f8e26555827730f2306c677073d0fca4) (branch `autoplace-experiments`; run outputs were local, boards are third-party).

| Arm | legal | probe clean | probe completion | HPWL / human | probe DRC errors | method s |
|---|---|---|---|---|---|---|
| reference (human placement) | 14 | **14** | 1.000 | 1.00 | 0 | — |
| v3 `rand` | 12 | 7 | 0.832 | 1.36 | 73 | 32 |
| v3 `greedy` | 11 | 8 | 0.745 | 0.71 | 70 | 24 |
| v3 `sa`, seeds 0/1/2 | 13/13/13 | 8/11/9 | 0.89–0.93 | 0.67–0.71 | 42–74 | 31–53 |
| v3 `sa`, no crossing term | 13 | 10 | 0.886 | 0.69 | 66 | 32 |
| v3 `sa`, no halo | 12 | 8 | 0.853 | 0.71 | 84 (mask bridge 9, clearance 7) | 34 |
| v3 `sa-best` (rank by unrouted only) | 13 | 9 | 0.893 | 0.66 | 69 | 164 |
| v4 `sa` | **14** | 9 | 0.961 | 0.73 | 5 | 31 |
| v4 `sa-best` (rank includes DRC) | 14 | 12 | 0.964 | 0.73 | 1 | 128 |
| v4 `sa-loop` | 14 | **14** | 1.000 | 0.74 | 0 | 109 |

v3 counts include a printed-coil bug (below) that caused 64 copper-edge errors and one illegal result per v3 arm; compare v3 arms only with each other. Seed noise for plain SA is ±2 boards, so the crossing-term ablation (10/14) is inconclusive; removing the halo adds mask-bridge and clearance errors.

How the loop spent its effort (in-loop unrouted/errors per probe, `*` = kept): a 34-part LED-matrix board 2/1 → 0/0\*; a 75 %-fill board with eight 13 mm jacks 0/1 → 0/3 → 0/3 → 0/0\* in 825 s, where `sa-best`'s six seeds never got clean; 9 of 14 boards were clean on the first probe.

**Provisional, larger sample** (not from a written-up experiment; from the kaeres results index, experiment `merit-500` plus `merit-smoke`, method `autoplace sa-loop` at `b3b0896`, evaluator `98dc632c1679`, queried 2026-10-27): 145 runs, 36 produced no output (the Python SA did not finish within budget on larger boards), 109 scored, 105 legal, **19/105 probe-clean**, mean probe completion 0.867 over the legal ones. Freerouting 2.5.0 on the human placements of the same 109 boards (experiment `fr-baseline`): 15 clean. Different routing budgets, so not a matched comparison. This method was superseded by the `--router kae` variant ([autoplace-kae-router.md](autoplace-kae-router.md)).

## Verdict

- **Close the loop on DRC.** Almost every non-clean result was fully routed and failed DRC: `starved_thermal` (Freerouting's tracks cut the GND pour into islands, so thermal spokes land on an isolated island), `solder_mask_bridge` (tracks across mask openings in logos and board text), `clearance` with the halo off. Selecting seeds on unrouted count alone (v3 `sa-best`, 9/14) did no better than plain SA; adding DRC to the rank gave 12/14, and DRC-blamed repair 14/14.
- **HPWL is not the target.** Every SA arm beat the human HPWL by ~30 % and still routed clean less often.
- **Geometry bugs dominated early debugging**; each found from a failed DRC and cost a placer version:
  - footprints with no courtyard and no pads (logos) collided with nothing; now parked out of the way (`213f484`);
  - pure silkscreen artwork is free, but copper or mask artwork is an obstacle; board-level text on mask layers is an obstacle (`4b4fba0`);
  - copper graphics inside a footprint (a 560 µH printed coil on an RFID board) belong to its rectangle (`e63bd23`);
  - packing courtyard-to-courtyard starves thermal spokes: keep a 0.2 mm halo floor (`4b4fba0`);
  - at ≥ 75 % fill the halo must shrink to the floor or the legalizer can't fit the parts.
- **Caveats:** one seed; 14 easy boards chosen because Freerouting routes their human placement; the loop optimizes against the same router family that scores it (4 vs 10 passes); no mechanical intent (mounting holes and edge connectors move; overhanging connectors are pulled on-board); no regularity (LED/switch grids scatter). On the provisional larger sample the method lost most of its advantage and timed out on big boards (~1,000 SA moves/s in Python).
- **Left to do:** k ≥ 3 seeds; a second probe to test transfer (kill if Spearman < 0.5 between inner and outer probe); a compute-matched best-of-N control (the v3 seeds-0–2 oracle is 11/14); harder suites (4-layer, 50–150 parts, boards Freerouting cannot route as designed); mechanical anchors; report `starved_thermal` separately; a compiled cost kernel.

## Code

`tools/research/autoplace/` (moved from `methods/autoplace` on the branch, tip `cd26ccb`): `place.py` (solver and driver), `kicad_helper.py` (pcbnew side), `summarize.py`, `place-smoke-14.txt`, README with setup. Run as a kaebench `--command`:

```bash
kaebench run --adapter sa-loop --kinds place --probe freerouting --timeout 1200 \
  --command "$PY $PWD/tools/research/autoplace/place.py --algo sa-loop --input {input} --output {output} --workdir {workdir} --attempt {attempt} --timeout {timeout}" \
  --only @tools/research/autoplace/place-smoke-14.txt --name sa-loop
```

`$PY` needs numpy, scipy and shapely; `kaebench` is taken from `PYTHONPATH` or this checkout's `bench/src`. The runs above used score v5; main's harness scores with a later version, so re-run the reference before comparing.

## Related

- [autoplace-kae-router.md](autoplace-kae-router.md): the same loop with kae's router, and the speed-ups.
- [Placement area map](README.md); [research index](../README.md).
- Plans this followed: [strategy-candidates](../../topics/placement/strategy-candidates.md) (P1, P3, P4); original ideas [P1 router-probe forces](../../ideas/original/placement.md) and [S6 successive halving](../../ideas/original/system-loop.md); [legalization survey](../../topics/placement/legalization.md).
- Prior art used: [KiCadRoutingTools placement notes](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md) (MIT; crossing term, √pins halo, `place_route_loop`); [autolayout ROADMAP](https://github.com/bwattendorf/autolayout/blob/main/ROADMAP.md) (escape halo).
