<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# pcbworld-d3 smoke and profile (2026-11-11, before the full run)

Smoke experiment `pcbworld-d3-smoke`: 2 D3-C boards (0473 data-manager, 38 footprints, 75 nets; 0571 brushless
ESC, 77 footprints), every arm once, through kaeq as the full run's jobs.

| Arm | 0473 | 0571 | Our scorer | PCBWorld's scorer |
|---|---|---|---|---|
| kae bridge | clean, 72 s wall, 290 CPU-s (4 parallel attempts) | clean, 111 s, 560 CPU-s | 2/2 clean | 2/2 CP, DRV 0 |
| pnr route_only | 25 open, 35 s | 1 open, 32 s | 0/2 (opens only, no other errors) | 0/2; DRV 25 and 1, all "missing connection" |
| fork d137fd1 `-mp 10` | clean, 46 s | clean, 82 s | 2/2 clean | 2/2 CP |
| human | clean | clean | 2/2 | 2/2 |

Both scorers agree on every smoke run. PCBWorld counts unconnected items as error-level DRVs; ours keeps them
as `unconnected`. Our KiCad 10 human runs, transplanted onto PCBWorld's KiCad 9 input board, score exactly as
PCBWorld's own routed boards (WL and vias equal), so the transplant carries the copper faithfully.

## Profile (0571, one run per arm, py-spy on the python process, JFR on Freerouting)

- **kae bridge** (`kae.route.cli route`, counted budget 1,248 s nominal; stops when clean): 76 s wall, 122 CPU-s.
  Waiting on Freerouting 84 %, imports 9 % (first use of the frozen venv writing bytecode), pcbnew calls 3 %,
  KiCad DRC 3 %. Freerouting's own time (JFR): `MinAreaTree.overlapsUnsortedUnlocked` and the search tree's
  shape queries dominate; no cheap fix outside the router.
- **pnr route_only**: 31 s of sampled time: A* and selector waits 39 %, imports 33 %, numba compiles 27 %. The
  recipe copies `~/.cache/kaebench/numba-anytfast`, which had no entries for this code, so every run compiled
  cold. Warmed that cache once (compiled code only): pnr went from 24 to 9 CPU-s on this board, and the output's
  copper is item-for-item identical to two cold runs (925 segments, 78 vias, same sets). No code changed.
- **fork** (kaebench adapter): 87 s wall, 126 CPU-s, peak RSS 1.3 GB; same Freerouting hot spots.
- Prepare 21 s, physics 7 s per board.

## Job sizing for the full run

Measured kaeq peaks: bridge+pnr jobs 3.7 GB and 8 threads (4 parallel attempts, each with Freerouting), fork
jobs 0.95 GB and 2 threads. Full-run jobs: bridge/pnr 4 CPUs, 4 GB (kaeres estimated 7.2 GB); fork 2 CPUs,
1.2 GB (estimated 1.8 GB). Submitted 2026-11-11 at priority 0, class timed, 218 + 109 jobs, both experiments
in the same window (owners `exp-pcbworld-d3`, `exp-pcbworld-d3-fr`), `KAE_CORPUS` set on the jobs.
