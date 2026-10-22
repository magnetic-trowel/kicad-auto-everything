# Autoplacement + autorouting: first experiments (2026-10-22)

**TL;DR**
- On 14 small 2-layer boards, **router-in-the-loop repair** (`sa-loop`: anneal, route with Freerouting, DRC, re-anneal only the parts behind failures) produced placements that route clean on **14/14** boards, the same as the human placements. Plain SA: 9/14. DRC-aware best-of-N SA seeds: 12/14 [M].
- What made the difference was **closing the loop on KiCad DRC, not only on connectivity**. Almost every non-clean result was fully routed but failed DRC (starved thermals, mask bridges). Selecting on unrouted count alone (v3 `sa-best`) did no better than plain SA [M].
- **Seed noise is large:** plain SA scored 8, 11 and 9 of 14 across three seeds. At n = 14, ±2 boards is noise, so the crossing-term and halo-size ablations are inconclusive. The one clear ablation: removing the escape halo adds mask bridges and clearance errors [M].
- **Geometry extraction dominates early debugging.** Copper logos, printed coils and board-level mask text must be obstacles. Each one cost a placer version [M].
- Caveats: one seed, 14 easy boards (selected because Freerouting routes the human placement cleanly), and the loop optimizes against the same router family that scores it. There is no mechanical intent (mounting holes and connectors move freely) and no regularity.

Code: [methods/autoplace](../../../methods/autoplace/README.md). Suite: `bench/suites/place-smoke-14.txt`. Plan this follows: [strategy-candidates](strategy-candidates.md) (P1, P3, P4), [S6 successive halving](../../ideas/original/system-loop.md) and [P1 router-probe pseudo-gradients](../../ideas/original/placement.md).

## Key facts

### Setup

| Item | Value |
|---|---|
| Boards | 14 qualified 2-layer place tasks (6 split A, 8 split B; 4–34 footprints, ≤ 98 pads), one per repo, seeded random draw from boards where Freerouting 2.5.0 routes the human layout clean |
| Task | kaebench place: unlocked footprints start stacked off-board at 0°; sides are kept |
| Score | kaebench score v5, task spec 4, KiCad 10.0.7; `legal` placement, then `--probe freerouting` (2.5.0, 10 passes at attempt 0) + KiCad DRC on the rebuilt board |
| Budget | k = 1, 10 cores (`systemd-run AllowedCPUs=0-9`), `-j 8/9`; 600 s per attempt (1,200 s for v4 `sa-best`/`sa-loop`) |
| Sandbox | All methods ran under the kaebench bwrap sandbox (no network, references hidden) |

### Methods (all in `methods/autoplace/place.py`)

| Arm | Mechanism | Doc idea |
|---|---|---|
| `rand` | random poses → grid legalizer | B2 (legalizer alone) |
| `greedy` | connectivity-ordered constructive placement on a grid, 4 rotations, least added HPWL | P1-lite |
| `sa` | greedy seed → SA. Cost: HPWL (pour nets × 0.1, power × 0.3) + 0.25·diag per ratsnest-MST crossing + overlap/outside penalty. Halo = floor 0.2 mm + (0.15 + 0.12·√pins) × fill factor (1 at ≤ 55 % fill, 0 at ≥ 75 %). Move/rotate/swap/jump moves; budget 1,500 × parts moves; then legalizer | P3; crossings and √pins halo from [KRT's placement notes](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md) |
| `sa-best` | up to 6 SA seeds; each routed in the loop (Freerouting, 4 passes) and DRC'd under the board's own rules; best by (unrouted, errors, vias, length); stop at the first clean | S6-lite |
| `sa-loop` | one SA seed, then up to 6 rounds: re-anneal only parts on unrouted nets or named in DRC errors (failed nets × 3, blamed parts +0.3 mm halo); keep only if better, else revert and widen moves ×1.5 | P4 / KRT `place_route_loop` with Freerouting |

### Results (attempt 0, 14 boards; reference = human placement)

| Arm (code) | legal | probe clean | probe completion | HPWL / human | probe DRC errors | method s |
|---|---|---|---|---|---|---|
| reference | 14 | **14** | 1.000 | 1.00 | 0 | — |
| v3 `rand` | 12 | 7 | 0.832 | 1.36 | 73 | 32 |
| v3 `greedy` | 11 | 8 | 0.745 | 0.71 | 70 | 24 |
| v3 `sa`, seeds 0/1/2 | 13/13/13 | 8/11/9 | 0.89–0.93 | 0.67–0.71 | 42–74 | 31–53 |
| v3 `sa`, no crossing term | 13 | 10 | 0.886 | 0.69 | 66 | 32 |
| v3 `sa`, no halo | 12 | 8 | 0.853 | 0.71 | 84 (mask bridge 9, clearance 7) | 34 |
| v3 `sa-best` (rank by unrouted only) | 13 | 9 | 0.893 | 0.66 | 69 | 164 |
| v4 `sa` | **14** | 9 | 0.961 | 0.73 | 5 | 31 |
| v4 `sa-best` (rank includes DRC) | 14 | 12 | 0.964 | 0.73 | 1 | 128 |
| v4 `sa-loop` | 14 | **14** | 1.000 | 0.74 | 0 | 109 |

v3 counts include one board (an RFID reader) where a printed coil's copper was not in the footprint rectangle. That bug accounts for 64 of the copper-edge errors and one illegal result per v3 arm; v4 fixes it. Compare v3 arms only with each other.

How the loop spent its effort (in-loop `unrouted/errors` per probe, `*` = kept):

| Board | v4 `sa-loop` | v4 `sa-best` |
|---|---|---|
| andreas (34 parts, LED matrix) | 2/1 → 0/0* | 2/1, 5/7, 0/0 |
| arts-laboratory | 0/2 → 1/0 → 0/0* | 0/2, 0/1, 0/1, 0/0 |
| freetronics | 0/1 → 0/0* | 0/1, 0/0 |
| iley (75 % fill) | 0/1 → 0/3 → 0/3 → 0/0* (825 s) | six seeds, best 0/1 → final not clean |
| openflexure | 1/0 → 0/0* | six seeds, none clean |
| the other 9 | clean on the first probe | same |

### What failed, and why

- **DRC, not connectivity.** Most non-clean probe results had 0 unrouted. The errors were:
  - `starved_thermal`: Freerouting's tracks cut the GND pour into islands, so pad spokes land on an isolated island;
  - `solder_mask_bridge`: tracks crossing mask openings in logos and board text;
  - `clearance` once the halo is off.

  The loop fixes these by moving the blamed parts. A connectivity-only probe can't see them.
- **Geometry the placer must treat as obstacles** (each found from a failed DRC, fixed in v2–v4):
  - artwork footprints without courtyard or pads; pure silk is free, copper or mask is not;
  - board-level text on mask layers;
  - copper graphics inside footprints (a 560 µH printed coil);
  - logos with copper.
- **Dense boards.** At ≥ 75 % rectangle fill the halo must shrink to its floor. Otherwise the legalizer can't fit the parts (iley, eight 13 mm jacks).
- **HPWL is not the target.** Every SA arm beat the human HPWL by about 30 % and still routed clean less often. The human layouts optimize things HPWL ignores.

## Recommendations for our system

1. Keep **`sa-loop` as the placement baseline to beat** and make the loop DRC-aware by default. Next measurements:
   - k ≥ 3 seeds;
   - a second probe (KRT or the Freerouting fork) to test transfer. The [strategy-candidates](strategy-candidates.md) P4 kill criterion: Spearman < 0.5 between inner and outer probe;
   - a compute-matched control: best-of-N plain SA picked by the final probe. From v3 seeds 0–2 that oracle is 11/14.
2. **Scale the suite before tuning weights.** These 14 boards saturate (9 are clean under nearly every SA run). Next suites:
   - B boards where Freerouting does *not* route the human placement cleanly;
   - 4-layer boards;
   - 50–150 parts.
3. **Add mechanical anchors.** A `--keep-anchors`-style task variant, or a placer option to pin mounting holes and edge connectors to their designer edge, before anyone compares placements on looks. Today the placer pulls overhanging connectors fully on-board and moves mounting holes. See the [strategy-candidates](strategy-candidates.md) prerequisites.
4. **Harness:** count `starved_thermal` separately in reports. It measures the router's interaction with pours as much as placement.
5. **Speed:** the Python SA does about 1,000 moves/s, so `iley` needed 825 s in the loop. Port the cost kernel to Rust or numba before the 100+ part boards.

## Conflicts and open questions

- **Is the loop over-fitting the probe?** It optimizes against Freerouting (4 passes) and KiCad DRC, and is scored by Freerouting (10 passes) and KiCad DRC. That's legitimate for a router-in-the-loop placer, but transfer to another router is untested.
- **Crossing term:** KRT reports crossings as the dominant routability term. Here, removing it didn't hurt (10/14 vs 8–11/14). Small boards with low crossing counts may not exercise it.
- **Halo size:** only on/off was tested. KRT warns that strong halos collapse completion on dense boards.

## Sources

- Runs: `kae-place/results/{ref,v3-*,v4-*}` in the local-NVMe work dir on sk-tibia (local only; boards are third-party). Code commits: v3 `4b4fba0`, v4 `e63bd23`; harness `7abe5fc`.
- [KiCadRoutingTools placement-optimization notes](https://github.com/drandyhaas/KiCadRoutingTools/blob/main/docs/placement-optimization.md) (MIT): crossing weights, halo, `place_route_loop` [P].
- [autolayout ROADMAP](https://github.com/bwattendorf/autolayout/blob/main/ROADMAP.md): escape halo 0.65 mm × escapes/4 [P].

See also: [strategy-candidates](strategy-candidates.md), [legalization](legalization.md), [dev-eval-plan](../verification/dev-eval-plan.md), [freerouting](../routing/freerouting.md).
