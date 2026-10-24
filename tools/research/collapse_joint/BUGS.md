<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Bugs found while fixing jc (tag `jcfix`)

Each entry: what, where, effect, fix, which runs it affects. Scoring code was never changed.

1. **Physics methods cannot import `kae` inside the harness sandbox** (environment, kae-v7).
   `tools/research/pnr/physics.py` defaults `KAE_SRC` to a `/tmp` scratchpad; kaebench's
   bwrap sandbox mounts a tmpfs over `/tmp`, so every `phys_w`-using method (jc, seq_phys,
   combo, ...) died with `No module named 'kae'` (all attempts `no_output`). Fix: copy of
   kae src in `kae-work/kae-src`, `export KAE_SRC=...` before `kae-v7/runj.sh` (the env
   passes through bwrap); `trust` then added `--sandbox-ro` for the kae src to
   `kae-v7/runj.sh`, which all later jcfix runs use. Failed runs deleted and re-run.
2. **jc double counts two legality terms on engine v6** (jc.py, by design at the time).
   Engine v6 stamps drilled holes into both courtyard planes and footprint cutouts into
   every plane; jc still adds its own hole-under-courtyard and cutout maps to the part
   cost and legal map. Fix in jc2 (`engine=1`, default): jc's copies are empty.
3. **jc's polish share is not 15 % on large boards** (jc.py restart loop). A new
   continuation starts only if 1.1 x the last run's time is left before `run_end`; on
   boards where one run takes ~35 CPU-s (of 120) only 2 runs fit and the polish gets
   ~43 % of the budget (diagnostic logs: olimex, jangtrinh, siderakb-pmw3610). jc2 `fill=1`
   spends that remainder on a perturbed resume from the best state.
4. **jc burns its run budget at the top of the schedule** (jc.py `collapse_once`). On
   siderakb-pmw3610 beta sits at 500 for 15 iterations with the same 5 conflicting nets
   and no part moving; legalization then drops them (6 open connections). jc2 `stall=4`
   stops a continuation after 4 flat iterations at the top of the schedule.
5. **Tasks re-prepared under running jobs** (workdir, not code). kae-v7 tasks were
   re-prepared to task spec 6 at 19:47-19:49 UTC while the first dev6 arms ran; attempts
   whose input came from the old task and whose score used the new one were invalid
   (`place_foreign`: dimensions, targets, graphics with new uuids). All jcfix runs started
   before the re-prepare finished were deleted and re-run from scratch.
6. **Unguarded final PathFinder opens connections** (jc.py `collapse_once` end and
   `methods_phys.anneal_phys` end, used as jc's polish). When a connection is open, both
   rip every net and negotiate again from a low present cost, then legalize, and keep the
   result even if more nets are dropped. paw3395 (jc2 v1, seed 0): 4 open connections
   before the polish, 8 after, although annealing kept its best state. This is one source
   of jc's open hops. Fix in jc2 (`guard=1`, from v2 on): keep the better of before/after
   for the PathFinder retry and for the polish. `anneal_phys` itself is shared with combo
   and left unchanged.
