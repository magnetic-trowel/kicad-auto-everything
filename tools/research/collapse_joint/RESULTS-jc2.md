<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# jc2: fixing joint collapse's weaknesses (tag `jcfix`) — PARTIAL

**Status: partial, stopped on request.** The final 33-board × 3-seed runs were stopped at
61/99 (physics) and 62/99 (length + vias) attempts; physics scoring was not run on them.
Every number below is provisional. Code: [jc2.py](jc2.py) (subclasses the unchanged
[jc.py](jc.py)); bugs: [BUGS.md](BUGS.md); multi-seed summary: [agg3.py](agg3.py).

## Diagnosis (logs of jc on olimex, jangtrinh, espprog, siderakb-pmw3610, paw3395)

- **Vias appear late.** The lift and early β have no vias. Vias appear at β > 1, once
  parts have stopped moving (`moved=0`) but wire–wire conflicts remain. The router then
  hops layers instead of detouring. The polish removes a few. Restarts are not a via source;
  they only pick among runs whose via counts vary a lot (0–7 on espprog).
- **Open hops come from the end phase.** The collapse often ends with every connection
  routed but some cells conflicting. jc then throws that copper away and re-negotiates from
  scratch. On paw3395 that turns 0 open connections into 8–10. A second, unguarded
  PathFinder (in jc's end phase and at the end of `anneal_phys`) can drop more (4 → 8).
  The continuation also burns budget at β = 500 with a flat conflict (15 iterations on
  siderakb).
- **Restarts and budget.** On large boards only 2 continuations fit, so the polish gets
  about 43 % of the budget, not 15 %. Restarts are ranked without regard to legality, so an
  illegal run can win.

## Fixes (each a switch in jc2; screened on dev6 and devB, 1 seed)

| fix | effect in screen |
|---|---|
| `engine`: drop jc's hole/cutout terms (engine v6 has them) | bug fix (no double count) |
| `guard`: keep the better side of the end-phase PathFinder and of the polish | bug fix; polish rejected when it opened nets |
| `legal_first`: illegal parts add 1e6 to a restart's cost | bug fix (biscuit, paw3395) |
| `stall=4`: stop at β_max after 4 flat iterations | dev6 open 8 → 4 |
| `complete`: renegotiate each open net with its box neighbours, then `repair_phys` | dev6 open 8 → 6 |
| `via_beta=1`: via price × (1 + ln(1+β)) | dev6 vias 3 → 2; devB fewer vias, longer |
| `clean`: hard re-route of via nets and their via neighbours at 8 mm/via | removes 1–2 vias/board, legal by construction |
| `minplus_w=0.5` from β ≥ 1 (xf_minplus T1) | devB vias 48 → 25 with fix; routed physics worse (1.54 vs 1.17, 5 boards) |
| rejected: `restart=perturb`, `fill`, `via_part`, `end_alt` | no gain, or more vias/length |

Final arms: `jc2_fix` = guard + legal_first + stall + complete + via_beta + clean (physics
objective). `jc2_fixmp_lv` = the same + late min-plus (phys_w = 0). End passes take their
time from the polish, not from the restarts (BUGS 10).

## Provisional results (kae-v7, score v7, engine v6.3, 120 CPU-s; runs `-r5` vs `v7-*-r3`)

Paired on the attempts every arm finished (board × seed). Length and vias are summed over
the attempts every arm fully routed. Clean is also shown per seed, as the spread.

Physics objective (61 attempts, 21 boards; 44 all-complete):

| run | legal | clean (seeds 0/1/2) | completion | open conn. | errors | length mm | vias |
|---|---|---|---|---|---|---|---|
| jc | 0.984 | 0.557 (.62/.55/.50) | 0.906 | 154 | 50 | 8882 | 245 |
| **jc2_fix** | 0.934 | **0.623** (.71/.55/.60) | **0.917** | **138** | 50 | 8872 | **204 (−17 %)** |
| combo | 0.902 | 0.557 (.62/.55/.50) | 0.909 | 160 | 84 | 9100 | 225 |
| *28-board subset:* jc / jc2_fix / combo | 0.981 / 0.981 / 0.942 | 0.577 / 0.615 / 0.538 | 0.906 / 0.912 / 0.907 | 125 / 121 / 135 | 48 / 47 / 81 | 7138 / 7097 / 7167 | 225 / 187 / 203 |

Length + vias objective (62 attempts, 21 boards; 44 all-complete):

| run | legal | clean (seeds 0/1/2) | completion | open conn. | errors | length mm | vias |
|---|---|---|---|---|---|---|---|
| jc_lv | 0.984 | 0.613 (.62/.62/.60) | 0.907 | 151 | 38 | 8624 | 205 |
| **jc2_fixmp_lv** | **1.000** | 0.613 (.67/.52/.65) | **0.928** | **120** | 47 | **8325 (−3.5 %)** | **143 (−30 %)** |
| combo_lv | 0.919 | 0.516 (.52/.57/.45) | 0.909 | 161 | 93 | 8683 | 179 |
| *28-board subset:* jc_lv / jc2_fixmp_lv / combo_lv | 0.981 / 1.000 / 0.943 | 0.642 / 0.604 / 0.509 | 0.902 / 0.923 / 0.906 | 132 / 106 / 139 | 36 / 47 / 90 | 6901 / 6609 / 6928 | 189 / 134 / 169 |

The 28-board subset leaves out the 5 boards that engine v6.4 changes
(`pnr/results/v63-v64-unchanged.txt`). jc2_fix's lower 33-board legal comes from those
boards.

Not done: physics (fast and routed, phys10 and the unchanged phys6, with open hops and
"no open hop" routed physics reported separately), the remaining 37–38 attempts, and
per-type DRC reading for the finals. A devB screen on 5 physics boards (1 seed) hinted
that the fix stack does not hurt routed physics (1.14 vs jc 1.23) and that min-plus does
(1.54). Fast physics there was dominated by restart luck (BUGS 10).

## Provisional verdict

**Likely merit as a cleanup of jc, not a new method.** On the finished attempts, jc2 cuts
vias by 17 % (physics objective) and 30 % (length + vias). It leaves fewer open
connections (−10 % / −20 %) and gains completion. Clean is equal or slightly better
(within seed spread), at equal length. Most of the gain comes from bug fixes in jc's end
phase (unguarded PathFinder, illegal restarts, stalled schedule) plus the via-aware
schedule and clean-up. It is not trustworthy yet: the runs are 62 % complete, have no
physics score, and the clean differences are inside the seed spread.

## Next steps to finish

1. Re-run the missing attempts. Same names and code snapshot `kae-v7/jcfix-snap/r5`;
   re-using a run name resumes it:
   `VER=r5 TAG=ab33 queue2.sh kae-v7/ab33.txt 1 3 120 jc2_fix`, and the same for
   `jc2_fixmp_lv`.
2. Run `agg3.py` (33 and `kae-v7/jcfix-ab28.txt`), `compare.py`, and `physics_score.py
   --suite kae-v7/phys10.txt` (and `jcfix-phys6.txt`) against `v7-jc-r3`, `v7-jc_lv-r3`,
   `v7-combo*-r3`. Read the per-type errors (solder_mask_bridge on lt6c is an engine
   limitation).
3. Ablate on the full set: jc2_base (bug fixes only) vs jc2_fix, to split bug fixes from
   heuristics. Also jc2_fix_lv, to split min-plus from the rest.
4. Then update the scorecard row (not yet changed).
