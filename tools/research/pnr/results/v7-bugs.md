# v7 joint baselines: bugs found and fixed

Log of the fix-and-rerun loop for [v7-baselines.md](v7-baselines.md) (harness score v7,
task spec 6, `--kinds joint`, workdir `kae-v7/`). Every fix is a separate commit; runs made
before a fix are discarded and re-run under a new name.

| # | Where | Symptom | Cause | Fix | Runs affected |
|---|---|---|---|---|---|
| 1 | engine (`kicad_io.py`, `world.py`) | `items_not_allowed` on noisecard: tracks and vias inside the keep-outs of B1 and J1 | Only board-level rule areas were extracted; rule areas drawn inside a footprint were ignored, so wires crossed them | Footprint rule areas are extracted in the footprint frame and move with the part: no-track / no-via areas are no-net obstacles for every net; no-pad / no-footprint areas join the part's keep-out planes (4 of 33 boards have them) | `v7-seq`, `v7-seq_phys` (killed, discarded) |
| 2 | engine (`kicad_io.py`, `world.py`) | Joint output invalid (`locked_moved`) on lt6c; any method | Task spec 5+ keeps footprints that carry Edge.Cuts in place (they are part of the outline); the engine treated them as movable | Footprints with Edge.Cuts graphics count as locked (`anchored`), as the harness defines them (5 of 33 boards) | as 1 |
| 3 | runner (`kae-v7/runj.sh`) | Every physics method (`seq_phys`, `combo`, `combo_lv`, `jc`, `jc_lv`): `no_output`, `ModuleNotFoundError: kae` | The merged harness runs `--command` methods in a bubblewrap sandbox with a private `/tmp`; the kae package (`KAE_SRC`) lives under a scratch directory in `/tmp` | `--sandbox-ro <KAE_SRC>` in the runner (read-only; the sandbox stays on); the lead later fixed it centrally (d6e0f7e: `physics.py` looks in `~/.cache/kaebench/kae-phys/src` first, an identical copy, checked with `diff -r`). Note `combo_lv` and `jc_lv` need kae too: they build the physics object even at `phys_w = 0` | smoke runs only |
| 4 | workdir (`kae-v7/prepare.log`) | 8 boards `FAILED` in prepare (`FileExistsError`, DRC on a half-written board) | Two `prepare` processes (one with `--force`) wrote the same workdir at once | All 33 A/B boards and the 8 failed ones re-prepared with `--force` by a single process before any counted run | none counted |
| 5 | engine (`kicad_io.py`, `world.py`) | `shorting_items` on paw3222: a GND track through D1's copper rectangles | Copper graphics drawn inside a footprint were not extracted (only board-level ones) | Free-standing footprint copper graphics (touching none of the part's pads) are no-net copper that moves with the part; graphics touching a pad (espprog's solder-jumper bridges) are left as before | smoke runs only (fixed before the counted runs) |
| 6 | engine (`kicad_io.py`, `world.py`) | funkeleinhorn: engine 0 unrouted, KiCad `Missing connection` between MK1 pad 1 (a ring-shaped custom pad) and a track ending on it (2 of 3 `seq` seeds) | Terminal cells came from the outward pad approximation (a cell a few microns outside the pad could be an end point), and KiCad's connectivity misses track ends well inside a custom ring pad (measured with pcbnew: ends 0.15-0.25 mm inside the edge are not connected) | Terminals from the inward approximation; on custom-shape pads only the anchor disc is a terminal | `v7-*-r2` (killed, discarded) |
| 7 | engine (`world.py`) | ecc83: `copper_edge_clearance` 0.0 mm (P5/P6 mounting pads touch the edge), a placement error: not legal on any seed | The edge test sampled only cell centres inside the pad; pad copper reaches up to a cell beyond them | Edge test on every cell within half a cell diagonal of the pad | as 6 |
| 8 | engine (`world.py`, `kicad_io.py`, `router.py`) | oasis-ledboard: pads placed on the board's copper arcs. v6.3, 3 seeds each: `seq` solder_mask_bridge 12, shorting_items 10, clearance 2, legal 0/3; `combo` 8 / 6 / 2, legal 0/3. v6.4: `seq` 0 errors, legal 3/3. Also olimex: a board text '4' on B.Cu under 12V_E1's pad (`combo_lv` seed 2: clearance + solder_mask_bridge) | Board copper drawings were wire obstacles only; text on copper was not extracted | v6.4 = bb5b493 (local branch `v64-merge`): the benchmark host's 4c4330a (drawings become pad keep-outs and router terminals, holes kept, .kicad_dru edge clearance) reconciled with v6.2/v6.3, plus text on copper. Footprint copper touching own pads is still skipped. 9/9 tests pass | v6.4 is identical to v6.3 on 28 boards (hash of every static map and part raster; list in `v63-v64-unchanged.txt`) and differs on 5 (olimex, paw3222, badjeff-pmw3610, oasis, jvedder). The `-r4cu` re-runs of those 5 have NOT been run |

Engine versions: v6 = 91fb5f9, v6.1 = 55809b6 (1, 2), v6.2 = 7c1cb3f (5), v6.3 = c78c537 (6, 7), v6.4 = bb5b493 (8, not yet on the branch). The counted runs are `v7-*-r3`, on v6.3.
Engine changes after the shared engine was in use by other agents' runs were made in a dev copy
(`kae-work/pnr-dev`), smoke-tested, and committed once.

## Harness issues written up, not fixed (scoring code is not changed here)

- **`method_usage.cpu_s` is near zero for sandboxed `--command` methods** (0.008 s for a run
  of 48 s). The harness measures the `wait4` rusage of `bwrap`; with `--unshare-pid` the
  method's processes are reaped inside the sandbox's PID namespace and their CPU time never
  reaches that rusage. The `cpu_s` column of `kaebench report` is therefore meaningless for
  these runs; budgets are enforced inside the method (`placekit.Clock`, process time).
- **Interpreter inside the sandbox** (harness-integrity 538170f: `python` could fall back to
  the system interpreter). Checked with a probe method run through the same runner: inside
  bwrap `python` is `bench/.venv/bin/python` (3.13.17, PATH keeps the venv first) and numba
  imports from the venv's site-packages; the system interpreter on this host is also 3.13.17.
  Our runs were not affected. kae is imported as source from `KAE_SRC` / `~/.cache/kaebench`
  (read-only), its dependencies from the venv.

## Engine limitations seen in the outputs (not bugs; left as they are)

- **The legality model rejects the human placement on 13 of 33 boards**, some by hundreds of
  cells (paw3395, noisecard, olimex, pmw3610-siderakb): pad keep-outs grown by the thermal
  spoke corridors of zone-net pads (all four directions kept free, KiCad needs two spokes)
  and by mask apertures. On paw3395 `seq` finds no legal spot for 3 capacitors and leaves
  them staged off the board (`outside` > 0, not legal). This is the engine's model, not a
  bug; changing it would change every method.
- **Mask openings drawn as graphics** (a polygon on F.Mask inside lt6c's U1) are not
  modelled: tracks routed under one, or the GND pour under it, give `solder_mask_bridge`.
- `starved_thermal` (spokes of zone pads blocked by neighbours or wires) remains, as in v5.
