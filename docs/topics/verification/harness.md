# Benchmark harness (kaebench)

Scope: what `bench/` (package `kaebench`) does: pipeline stages, score v2 integrity, adapters, qualification yield, first Freerouting baseline. Not here: metric definitions -> [quality-metrics.md](quality-metrics.md); benchmark recipe and plans -> [benchmark-plan.md](benchmark-plan.md); public benchmarks -> [benchmarks.md](benchmarks.md).
Keys: kaebench, bench/, harness, manifest, fetch, prepare, qualified, split A B C, route task, place task, score v2, transplant-routing, transplant-placement, integrity, valid, clean, completion, wl_ratio, via_delta, legal, hpwl_ratio, probe route, @1, @k, best-of-k, adapter, --command, bubblewrap, bwrap, freerouting, freerouting-stock, reference, noop, ENV_DEPENDENT_CHECKS, test_redteam.py
Tags: [M] measured by our harness.

## Harness invariants
1. `bench/` holds `kaebench`, a stdlib-only Python harness: manifest → fetch at pinned commit → convert to KiCad 10 → qualify → route/place tasks → adapter × k attempts → independent `kicad-cli` scoring → @1/@k report ([bench/README.md](../../../bench/README.md)).
2. **No method scores itself; only allowed changes count.** Score v2 rebuilds each board from the task input plus the method's tracks and vias (route) or footprint poses (place), installs the reference rules, and runs DRC in a fresh process. Any other change (rules, outline, keepouts, pads, layers, nets, locked parts) is detected and makes the result invalid.
3. External methods run in a bubblewrap sandbox with no network and no view of reference layouts. `bench/tests/test_redteam.py` holds the cheats this must catch.
4. Built-in adapters: `reference` (human), `noop`, `freerouting` (DSN/SES with the documented pitfalls fixed); any external tool plugs in through `--command`.
5. A router's own log is not a score: Freerouting claimed "0 unrouted, 1 violation" where KiCad found 2 unconnected and 2 clearance errors.
6. Use this harness as the agent's verification loop too ([evaluation-stack](evaluation-stack.md)), but outside the agent's write scope ([trust-requirements](../workflow/trust-requirements.md)).

## Qualification yield and first baseline
- KiCad 10.0.7 [M]: 112 of 297 manifest boards qualify. By layers: 2-layer 74/138, 4-layer 28/101, 6+ 10/54. Four boards timed out at 900 s DRC. List: `bench/suites/qualified-kicad-10.0.7.txt`.
- First Freerouting 2.5.0 baseline [M] (k = 1, 600 s, 4-core container), clean pass on the qualified boards:

  | Split (boards) | Stock | With adapter fixes |
  |---|---|---|
  | A (13) | 0.31 | 0.62 |
  | B (20) | 0.25 | 0.35 |
  | C (79) | 0.04, with 22 timeouts | not run |

- Stock failures were dominated by DSN translation losses, not routing failures: automatic neck-down below the board's minimum width; missing copper-to-edge clearance; netclass widths below the board minimum.

## Pipeline stages
| Stage | What happens | Code |
|---|---|---|
| Manifest | One JSON line per board: repo, 40-hex commit, path, licence, sha256, stats, tags. Boards are never redistributed | `manifest.py` |
| Fetch | Raw download (GitHub/GitLab) or shallow git fetch of one commit; sha256 verified; sibling `.kicad_pro`/`.kicad_dru` fetched too | `fetch.py` |
| Prepare | `LoadBoard`/`SaveBoard` to KiCad 10. **Qualified** = human layout has 0 unconnected and 0 error DRC. Split by pads: A ≤ 31, B ≤ 100, C larger (PCBWorld) | `prepare.py` |
| Route task | All tracks/vias removed, zones unfilled, placement kept | `pcbnew_ops.py strip-routing` |
| Place task | Unlocked footprints rotated to 0° and stacked off-board; locked footprints stay (task spec 2); copper removed | `pcbnew_ops.py strip-placement` |
| Run | Private copy per attempt, timeout, resumable, parallel `-j` | `runner.py` |
| Score (route) | Rebuild from input + routing (`transplant-routing`); `clean`, `completion`, error counts by type, `wl_ratio`, `via_delta`; integrity (placement, pad nets, layers, nets, no foreign changes); copy check against the human copper | `score.py`, `pcbnew_ops.py` |
| Score (place) | Rebuild from input + poses (`transplant-placement`); `legal` (no courtyard, clearance, edge, hole or keepout errors; pads inside outline), `hpwl_ratio`, plus a probe route of the rebuilt board by a fixed router | `score.py`, `pcbnew_ops.py` |
| Severities | `clean`/`legal` use each board's own `.kicad_pro` severities. Since score v11, `clean_strict`/`legal_strict` also need no shorts, clearance, hole-clearance, copper-to-edge, courtyard-overlap or rule-area errors, whatever the project says (`STRICT_CHECKS`; a second DRC runs only on boards that downgrade one of them). 184 of 2,454 qualified boards downgrade courtyards, 96 copper-to-edge, 49 clearance, 7 shorts. Results scored before v11 have no strict columns, so baselines must be re-run to compare them | `score.py` |
| Report | @1 and best-of-k (clean, completion, errors, length) per adapter × split, with `cp1_strict`/`cpk_strict`/`legal_strict` when every result has them, and CPU-seconds per attempt; with two adapters, a paired A/B (McNemar, sign-flip, repo bootstrap, Holm, flipped boards, guardrails on boards both arms routed clean, scorer failures set aside) | `report.py`, `stats.py` |

## KiCad-side operations and adapters
- **KiCad-side operations** run in KiCad's own Python as a separate process, with JSON on a private stdout. Two pcbnew quirks:
  - SWIG prints leak warnings on stdout at exit.
  - After `BOARD.Remove()`, zone and bounding-box objects come back untyped. Unfill zones and move footprints before removing tracks.
- **Freerouting adapter:**
  - SWIG `ExportSpecctraDSN`, then the native bundle with `-mt 1 -da --gui.enabled=false`, then strip the SES `(placement …)` block, then `ImportSpecctraSES` ([specctra integration](../kicad/specctra-freerouting-integration.md)).
  - There is no seed flag, so attempts vary `-mp` (10, 20, 30, …).
  - Board-rule fixes, on by default:
    - `--router.automatic_neckdown=false`;
    - the board's copper-to-edge and hole clearances passed as `--router.*_um`;
    - DSN `(width …)` rules clamped to the board's minimum track width.
  - With edge clearance set, Freerouting still shrinks a few tracks to 75% near the edge, and `router.neck_width_um` does not stop it.
  - `freerouting-stock` runs it as shipped.
- **Environment-dependent checks** (`lib_footprint_issues`, `lib_footprint_mismatch`) are excluded, because they depend on the host's libraries, not the board.

## Next additions
- PCBWorld D3 import (its boards come from PCBench) and the Cypress placement protocol ([benchmark-plan](benchmark-plan.md)).
- KiCadRoutingTools and PCBWorld-Engine adapters.
- Intent-track constraint checks ([constraint-ir](../architecture/constraint-ir.md)).
- Per-board DSN-loss report comparing Freerouting's drc.v1 output with KiCad DRC.
- Run long benchmarks on a dedicated host with `-j` = core count; Freerouting runs single-threaded per attempt.

## Open questions

- The human layouts of open boards are not always clean after conversion. Qualification drops them by default; `--all` keeps them.
- `inside` checks pad centres against the outline. Courtyard overhang at board edges is legitimate for connectors and is not penalized.
- Freerouting's neck-down near fine-pitch pads may be configurable; it is untested.
- The code also scores a joint place+route task (`score_joint_task` in `score.py`), undocumented here.

## Sources

- Harness code: [bench/src/kaebench/](../../../bench/src/kaebench/), tests in [bench/tests/](../../../bench/tests/)
- Recipe and metrics: [benchmark-plan](benchmark-plan.md), [quality-metrics](quality-metrics.md), [../routing/pcbworld.md](../routing/pcbworld.md)
- See also [../data/open-board-sources.md](../data/open-board-sources.md).
