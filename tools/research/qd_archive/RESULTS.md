<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Quality-diversity archive over joint collapse (tag `qd`, idea 16)

Does a MAP-Elites archive beat jc's best-of-restarts at equal CPU (120 CPU-s)? Code: [qd.py](qd.py).

## Method

- **Start.** Two plain jc continuations from the lift (`jc.collapse_once`).
- **Loop.** Pick a parent uniformly from the occupied cells and restore its poses. Mutate a few parts, then run a short jc continuation from that placement: no lift; β starts at β_m, log-uniform 0.3–6, which sets the mutation strength. Then legalize, route, and insert the result into the archive. Polish with `anneal_phys` at 15 %, as in jc.
- **Descriptors** (log bins relative to the first board): `qd`: part spread (RMS distance of origins from their centroid) × via count. Tried on dev: `qd_po` (fast physics × length) and `qd1` (one cell: elitist iterated local search).
- **Mutations:** `shift`: the k nearest parts around a random part move up to 3 mm, rotated with p 0.3. `rot`: k parts rotated. `swap`: two parts exchange origins. k ∈ {1, 2, 3, 15 % of parts}.
- **`qdh`:** half of the candidates are fresh jc restarts, and all enter the archive.
- **Pick:** the lowest objective (routed cost + phys_w · fast physics). `_lv`: phys_w = 0.

Bugs fixed during the work: the hybrid stopped instead of trying a shorter mutation when no restart fit; the v7 sandbox allows writes only to the attempt directory, so the archive goes to stdout (`QDARCHIVE` line in `adapter.log`). Counted runs used a frozen worktree (engine v6.3, c78c537, plus qd at 5987f57) via [runj_qd.sh](runj_qd.sh).

## Results (v7 harness, ab33, 3 seeds, 120 CPU-s; mean [min, max] over seeds)

TABLE_PLACEHOLDER

## Archive coverage (ab33 × 3 seeds)

COVERAGE_PLACEHOLDER

## Development (engine v5, seed 0, vs `jcollapse-jc-ab33-v3`)

- **dev6:** `qd` tied jc (clean 0.833, 612 mm, 8 vias). `qd1` was shorter (591 mm) but used more vias (11). `qd_po` was worse (629 mm).
- **phys10 (fast / routed physics × human):**
  - `qd`: 0.76 / 0.96, clean 0.3.
  - `qd1`: 0.94 / 1.02, clean 0.5.
  - `qdh`: 0.98 / 1.03, clean 0.5.
  - jc: 0.82 / 1.05, clean 0.6.
  - combo: 1.03 / 1.13, clean 0.5.
- **Pre-polish objective** vs jc's own restart logs: `qd1` 1.15× (gmean), `qdh` 1.02×, `qd` 1.12×. On big boards a restart takes about 40 CPU-s, so only 2–3 candidates fit, and per-run noise is huge: two jc restarts on noisecard cost 3569 and 352. On olimex, jc's third and fourth fresh restarts reached 187 and 196, while mutations of the elites stayed at 285–311. Restarts reach basins that local mutations do not.

## Verdict

VERDICT_PLACEHOLDER

## Next step

NEXT_PLACEHOLDER

Runs: `kae-v7/results/qd-{qd,qd_lv,qdh}-ab33-r3`. Physics: `kae-work/qd/phys/`. Dev: `kae-work/results/qd-*-{dev6,phys10}-v1`.
