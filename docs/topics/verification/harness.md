# Benchmark harness (kaebench)

**TL;DR**
- `bench/` holds `kaebench`, a stdlib-only Python harness. It runs: manifest → fetch at pinned commit → convert to KiCad 10 → qualify → route/place tasks → adapter × k attempts → independent `kicad-cli` scoring → @1/@k report ([bench/README.md](../../../bench/README.md)).
- **No method scores itself, and only allowed changes count.** Since score v2 the scorer rebuilds each board from the task input plus the method's tracks and vias (route) or footprint poses (place), installs the reference rules, and runs DRC in a fresh process. Any other change the method made (rules, outline, keepouts, pads, layers, nets, locked parts) is detected and makes the result invalid. External methods run in a bubblewrap sandbox with no network and no view of reference layouts. `bench/tests/test_redteam.py` holds the cheats this must catch.
- **Built-in adapters:** `reference` (human), `noop`, and `freerouting` (DSN/SES with the documented pitfalls fixed). Any external tool plugs in through `--command`.
- **Qualification yield on KiCad 10.0.7 [M]:** 112 of 297 manifest boards qualify. By layers: 2-layer 74/138, 4-layer 28/101, 6+ 10/54. Four boards timed out at 900 s DRC. The list is `bench/suites/qualified-kicad-10.0.7.txt`. These counts come from task spec 1; spec 4 adds a round-trip requirement and spec 6 fixes a zone-uuid deadlock, so re-run `prepare` before relying on them.
- **First Freerouting 2.5.0 baseline [M]** (k = 1, 600 s, 4-core container, score v1): clean pass on the qualified boards. It predates rebuild-then-score and partial output on timeout, so re-run it under the current scorer before comparing ([dev-eval-plan](dev-eval-plan.md) Phase 1).

  | Split (boards) | Stock | With adapter fixes |
  |---|---|---|
  | A (13) | 0.31 | 0.62 |
  | B (20) | 0.25 | 0.35 |
  | C (79) | 0.04, with 22 timeouts | not run |

  Stock failures were dominated by DSN translation losses, not routing failures:
  - automatic neck-down below the board's minimum width;
  - missing copper-to-edge clearance;
  - netclass widths below the board minimum.
- **Freerouting's own log is not a reliable score:** it claimed "0 unrouted, 1 violation" where KiCad found 2 unconnected and 2 clearance errors.

## Key facts

| Stage | What happens | Code |
|---|---|---|
| Manifest | One JSON line per board: repo, 40-hex commit, path, licence, sha256, stats, tags. Boards are never redistributed | `manifest.py` |
| Fetch | Raw download (GitHub/GitLab) or shallow git fetch of one commit; sha256 verified; sibling `.kicad_pro`/`.kicad_dru` fetched too | `fetch.py` |
| Prepare | `LoadBoard`/`SaveBoard` to KiCad 10. **Qualified** = human layout has 0 unconnected and 0 error DRC. Split by pads: A ≤ 31, B ≤ 100, C larger (PCBWorld) | `prepare.py` |
| Route task | All tracks/vias removed, zones unfilled, placement kept | `pcbnew_ops.py strip-routing` |
| Place task | Unlocked footprints rotated to 0° and stacked off-board; locked footprints (spec 2) and footprints carrying Edge.Cuts (spec 5) stay; copper removed | `pcbnew_ops.py strip-placement` |
| Run | Private copy per attempt, timeout, resumable, parallel `-j` | `runner.py` |
| Score (route) | Rebuild from input + routing (`transplant-routing`); `clean`, `completion`, error counts by type, `wl_ratio`, `via_delta`; integrity (placement, pad nets, layers, nets, no foreign changes); copy check against the human copper | `score.py`, `pcbnew_ops.py` |
| Score (place) | Rebuild from input + poses (`transplant-placement`); `legal` (no courtyard, clearance, edge, hole or keepout errors; pads inside outline), `hpwl_ratio`, plus a probe route of the rebuilt board by a fixed router | `score.py`, `pcbnew_ops.py` |
| Report | @1 (attempt 0) and any-clean best-of-k (ranked clean, completion, errors, length) per adapter × split; runs that share an adapter name are labelled `adapter@run` | `report.py` |

- **KiCad-side operations** run in KiCad's own Python as a separate process, with JSON on a private stdout. Two pcbnew quirks were found while building it:
  - SWIG prints leak warnings on stdout at exit.
  - After `BOARD.Remove()`, zone and bounding-box objects come back untyped. Unfill zones and move footprints before removing tracks.
- **Freerouting adapter:**
  - SWIG `ExportSpecctraDSN`, then the native bundle with `-mt 1 -da --gui.enabled=false`, then strip the SES `(placement …)` block, then `ImportSpecctraSES` ([specctra integration](../kicad/specctra-freerouting-integration.md)).
  - There is no seed flag, so attempts vary `-mp` (10, 20, 30, …). They are nested runs of one seeded search, not independent samples ([dev-eval-plan](dev-eval-plan.md) H4), and `cpk` is any-clean@k, not PCBWorld's best-potential @k.
  - Board-rule fixes, on by default:
    - `--router.automatic_neckdown=false`;
    - the board's copper-to-edge and hole clearances passed as `--router.*_um`;
    - DSN `(width …)` rules clamped to the board's minimum track width.
  - With edge clearance set, Freerouting still shrinks a few tracks to 75% near the edge, and `router.neck_width_um` does not stop it.
  - `freerouting-stock` runs it as shipped.
- **Environment-dependent checks** (`lib_footprint_issues`, `lib_footprint_mismatch`) are excluded, because they depend on the host's libraries, not the board.

## Recommendations for our system

- Use this harness as the agent's verification loop too ([evaluation-stack](evaluation-stack.md)), but keep it outside the agent's write scope ([trust-requirements](../workflow/trust-requirements.md)).
- **Next additions:**
  - The Cypress placement protocol ([benchmark-plan](benchmark-plan.md)). PCBWorld D3 boards can already be imported with `prepare-dir` ([bench/README.md](../../../bench/README.md)).
  - KiCadRoutingTools and PCBWorld-Engine adapters.
  - Intent-track constraint checks ([constraint-ir](../architecture/constraint-ir.md)).
  - A per-board DSN-loss report that compares Freerouting's drc.v1 output with KiCad DRC.
- Run long benchmarks on a dedicated host with `-j` set to the cores you may use (host details go in `CLAUDE.local.md`). Freerouting runs single-threaded per attempt.

## Conflicts and open questions

- The human layouts of open boards are not always clean after conversion. Qualification drops them by default; `--all` keeps them.
- `inside` checks pad centres against the outline. Courtyard overhang at board edges is legitimate for connectors and is not penalized.
- Neck-down is disabled with `--router.automatic_neckdown=false`; the edge-driven shrink to 75% remains and no setting found so far stops it.

## Sources

- Harness code: [bench/src/kaebench/](../../../bench/src/kaebench/), tests in [bench/tests/](../../../bench/tests/)
- Recipe and metrics: [benchmark-plan](benchmark-plan.md), [quality-metrics](quality-metrics.md), [../routing/pcbworld.md](../routing/pcbworld.md)

See also: [benchmarks](benchmarks.md), [../data/open-board-sources.md](../data/open-board-sources.md)
