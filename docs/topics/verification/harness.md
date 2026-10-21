# Benchmark harness (kaebench)

**TL;DR**
- `bench/` holds `kaebench`, a stdlib-only Python harness. It runs: manifest → fetch at pinned commit → convert to KiCad 10 → qualify → route/place tasks → adapter × k attempts → independent `kicad-cli` scoring → @1/@k report ([bench/README.md](../../../bench/README.md)).
- **No method scores itself.** Every output is re-opened in a fresh process with the reference rules installed. Integrity checks reject routers that move parts or change nets or setup; placers must keep nets and locked parts.
- **Built-in adapters:** `reference` (human), `noop`, and `freerouting` (DSN/SES with the documented pitfalls fixed). Any external tool plugs in through `--command`.
- **First dev numbers [M]** (two KiCad demo boards, Freerouting 2.5.0, k = 2):
  - completion 0.90, 0 clean passes;
  - Freerouting necks tracks to 0.09–0.11 mm below a 0.15 mm board minimum, which KiCad flags;
  - Freerouting's own log claimed "0 unrouted, 1 violation" where KiCad found 2 unconnected and 2 clearance errors.

## Key facts

| Stage | What happens | Code |
|---|---|---|
| Manifest | One JSON line per board: repo, 40-hex commit, path, licence, sha256, stats, tags. Boards are never redistributed | `manifest.py` |
| Fetch | Raw download (GitHub/GitLab) or shallow git fetch of one commit; sha256 verified; sibling `.kicad_pro`/`.kicad_dru` fetched too | `fetch.py` |
| Prepare | `LoadBoard`/`SaveBoard` to KiCad 10. **Qualified** = human layout has 0 unconnected and 0 error DRC. Split by pads: A ≤ 31, B ≤ 100, C larger (PCBWorld) | `prepare.py` |
| Route task | All tracks/vias removed, zones unfilled, placement kept | `pcbnew_ops.py strip-routing` |
| Place task | Unlocked footprints rotated to 0° and stacked off-board, copper removed | `pcbnew_ops.py strip-placement` |
| Run | Private copy per attempt, timeout, resumable, parallel `-j` | `runner.py` |
| Score (route) | `clean`, `completion`, error counts by type, `wl_ratio`, `via_delta`; integrity (placement hash, pad-net hash, `setup` block) | `score.py` |
| Score (place) | `legal` (no courtyard/clearance errors, pads inside outline), `hpwl_ratio`, plus a probe route by a fixed router | `score.py` |
| Report | @1 and best-of-k (clean, completion, errors, length) per adapter × split | `report.py` |

- **KiCad-side operations** run in KiCad's own Python as a separate process, with JSON on a private stdout. Two pcbnew quirks were found while building it:
  - SWIG prints leak warnings on stdout at exit.
  - After `BOARD.Remove()`, zone and bounding-box objects come back untyped. Unfill zones and move footprints before removing tracks.
- **Freerouting adapter:**
  - SWIG `ExportSpecctraDSN`, then the native bundle with `-mt 1 -da --gui.enabled=false`, then strip the SES `(placement …)` block, then `ImportSpecctraSES` ([specctra integration](../kicad/specctra-freerouting-integration.md)).
  - There is no seed flag, so attempts vary `-mp` (10, 20, 30, …).
- **Environment-dependent checks** (`lib_footprint_issues`, `lib_footprint_mismatch`) are excluded, because they depend on the host's libraries, not the board.

## Recommendations for our system

- Use this harness as the agent's verification loop too ([evaluation-stack](evaluation-stack.md)), but keep it outside the agent's write scope ([trust-requirements](../workflow/trust-requirements.md)).
- **Next additions:**
  - PCBWorld D3 import (its boards come from PCBench) and the Cypress placement protocol ([benchmark-plan](benchmark-plan.md)).
  - KiCadRoutingTools and PCBWorld-Engine adapters.
  - Intent-track constraint checks ([constraint-ir](../architecture/constraint-ir.md)).
  - A per-board DSN-loss report that compares Freerouting's drc.v1 output with KiCad DRC.
- Run long benchmarks on a dedicated host (sk-tibia) with `-j` set to the core count. Freerouting runs single-threaded per attempt.

## Conflicts and open questions

- The human layouts of open boards are not always clean after conversion. Qualification drops them by default; `--all` keeps them.
- `inside` checks pad centres against the outline. Courtyard overhang at board edges is legitimate for connectors and is not penalized.
- Freerouting's neck-down near fine-pitch pads may be configurable; it is untested.

## Sources

- Harness code: [bench/src/kaebench/](../../../bench/src/kaebench/), tests in [bench/tests/](../../../bench/tests/)
- Recipe and metrics: [benchmark-plan](benchmark-plan.md), [quality-metrics](quality-metrics.md), [../routing/pcbworld.md](../routing/pcbworld.md)

See also: [benchmarks](benchmarks.md), [../data/open-board-sources.md](../data/open-board-sources.md)
