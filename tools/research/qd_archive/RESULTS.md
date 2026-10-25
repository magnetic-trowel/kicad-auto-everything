<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Quality-diversity archive over joint collapse (tag `qd`, idea 16) — PARTIAL

**Partial (closed out early).** All qd arms are complete: 3 × 99 attempts. The jc baselines were not: `v7-jc-r3` had 88/99 attempts and `v7-jc_lv-r3` 94/99. jc physics was not scored.

Does a MAP-Elites archive beat jc's best-of-restarts at equal CPU (120 CPU-s)? Code: [qd.py](qd.py).

## Method

Two plain jc continuations start the archive. Each further candidate restores a uniformly chosen elite, mutates it, then runs a short jc continuation from that placement: no lift, β₀ log-uniform 0.3–6, which sets the mutation strength. It is legalized, routed and inserted; the 15 % `anneal_phys` polish is as in jc.
- **Mutations:** `shift` (k nearest parts move ≤ 3 mm, p 0.3 rotate), `rot`, `swap`; k ∈ {1, 2, 3, 15 %}.
- **Descriptors:** part spread × vias, log-binned against the first board. Dev only: `qd_po` (physics × length) and `qd1` (a single cell).
- **`qdh`:** half the candidates are fresh restarts.
- **Pick:** the lowest routed cost + phys_w · fast physics; `_lv` sets phys_w = 0.

Fixed bugs:
- The hybrid stopped instead of mutating when no restart fit.
- The sandbox allows writes only to the attempt directory, so the archive goes to stdout (`QDARCHIVE` in `adapter.log`).

Counted runs come from a frozen worktree (engine v6.3 c78c537, qd 5987f57; [runj_qd.sh](runj_qd.sh)).

## Results (v7 harness, ab33, 3 seeds, 120 CPU-s; mean [min, max] over seeds)

Physics columns are the 10 physics boards (`kae-v7/phys10.txt`), fast and routed physics × human. 4 of those 10 boards are among the 5 that engine v6.4 changes.

| run (ab33) | legal | clean (cp) | cpk | completion | length | vias | fast phys | routed phys |
|---|---|---|---|---|---|---|---|---|
| `qd` | 0.960 [0.939, 0.970] | 0.717 [0.667, 0.758] | 0.758 | 0.933 | 3356 [3269, 3444] | 62 [42, 84] | 0.96 [0.87, 1.05] | 1.18 [1.15, 1.21] |
| `qdh` | 0.960 [0.939, 0.970] | 0.677 [0.636, 0.727] | 0.758 | 0.931 | 3349 [3254, 3486] | 58 [42, 82] | 0.89 [0.89, 0.90] | 1.13 [1.01, 1.25] |
| `v7-combo-r3` | 0.869 [0.848, 0.879] | 0.657 [0.606, 0.697] | 0.727 | 0.925 | 3433 [3341, 3572] | 52 [42, 72] | 1.26 [1.14, 1.37] | 1.27 [1.23, 1.30] |
| `qd_lv` | 0.960 [0.939, 0.970] | 0.677 [0.667, 0.697] | 0.758 | 0.927 | 3345 [3275, 3436] | 60 [46, 73] | 2.56 [2.05, 2.87] | 1.40 [1.33, 1.51] |
| `v7-combo_lv-r3` | 0.879 [0.848, 0.909] | 0.626 [0.576, 0.667] | 0.727 | 0.924 | 3379 [3324, 3483] | 50 [38, 66] | 2.84 [2.36, 3.35] | 1.26 [1.16, 1.31] |

On the 28 boards that engine v6.4 leaves unchanged:
- `qd`: legal 0.988, clean 0.738 [0.679, 0.786], 2747 mm, 54 vias.
- `qdh`: clean 0.702, 2745 mm, 50 vias.
- `combo`: legal 0.917, clean 0.667, 2764 mm, 43 vias.
- `qd_lv`: clean 0.690, 2738 mm.
- `combo_lv`: legal 0.917, clean 0.643, 2769 mm.

Length and vias are summed over the boards complete in every run of that seed.

**vs jc (paired, only the (board, seed) pairs jc finished; DRC only):**

| pairs | run | legal | clean | completion | length | vias |
|---|---|---|---|---|---|---|
| ab33, 88 (65 complete) | `jc` | 0.955 | 0.659 | 0.920 | 10072 | 228 |
| | `qd` | 0.955 | 0.682 | 0.924 | 10241 | 221 |
| | `qdh` | 0.955 | 0.636 | 0.922 | 10213 | 207 |
| | `combo` | 0.886 | 0.648 | 0.921 | 10447 | 193 |
| ab28, 73 (56 complete) | `jc` / `qd` / `qdh` | 0.986 all | 0.699 / 0.699 / 0.658 | 0.933 / 0.935 / 0.932 | 8252 / 8415 / 8401 | 194 / 196 / 183 |
| ab33 lv, 94 (71 complete) | `jc_lv` / `qd_lv` | 0.957 both | 0.702 / 0.660 | 0.925 / 0.923 | 9993 / 10059 | 207 / 201 |
| ab28 lv, 79 (62 complete) | `jc_lv` / `qd_lv` | 0.987 both | 0.747 / 0.671 | 0.934 / 0.932 | 8195 / 8238 | 179 / 179 |

## Archive coverage (ab33 × 3 seeds)

- **Archive size:** `qd` holds 37.6 candidates and 8.4 cells per board; `qdh` 28.9 and 7.5.
- **Mutation outcomes (`qd`):** 18 % open a new cell, 41 % improve a cell, 5 % set a new global best. `shift` does best (6.1 % new global best), `swap` worst (3.0 %).
- **Where the pick comes from:** a mutation on 56 of 99 attempts (`qd`) and 40 of 99 (`qdh`, which has restarts in the archive).
- **Diversity found beyond the pick:**
  - `qd`: the physics-best elite has 0.93× the pick's fast physics at 1.04× its objective.
  - `qd_lv`: a length-optimized archive still holds a physics elite at 0.79× physics for 1.09× objective.
  - The length-best elite is always the pick itself, since length dominates the objective.
  - On v5, jc's restarts held a physics-best run at 0.92×, so the archive's extra diversity is modest.

## Development (engine v5, seed 0)

On dev6, `qd` tied jc. On phys10, `qd`/`qd1`/`qdh` scored fast physics 0.76/0.94/0.98 and clean 0.3/0.5/0.5, against jc's 0.82 and 0.6. Comparing jc's restart logs, the pre-polish objective was 1.02–1.15× jc's (gmean). On olimex, fresh jc restarts found 187; mutations of the elites stayed at 285–311.

## Verdict

**Provisional: no merit over jc** (merit over combo). At equal CPU the archive ties jc's best-of-restarts on legality and completion. Clean is within seed noise (`qd` +0.02, `qdh` −0.02), copper is 1–2 % longer, and vias are about equal. `qd_lv` trails `jc_lv` on clean (−0.04 to −0.08). The archive's elites add only a modest set of physics-leaning alternatives. Against combo all qd arms are more often legal (+0.07–0.09) and have better fast and routed physics, which is jc's advantage inherited.

Mechanism, from the dev logs: on large boards only 2–3 continuations fit in 120 CPU-s, so the archive barely differs from jc. On small boards, fresh restarts reach basins that local mutations of elites do not.

## Next step

To finish:
1. When `v7-jc-r3` and `v7-jc_lv-r3` reach 99/99, rerun the table: `seeds.py` with `--phys`, after scoring jc with `kae-work/qd/phys.sh jc v7-jc-r3 v7-jc_lv-r3`.
2. Rescore on engine v6.4.

If pursued: archive restarts by restart descriptor instead of mutating elites; use full routed physics (`RoutedPhys`) only for the final pick among elites.

Runs: `kae-v7/results/qd-{qd,qd_lv,qdh}-ab33-r3`. Physics: `kae-work/qd/phys/`. Dev: `kae-work/results/qd-*-{dev6,phys10}-v1`.
