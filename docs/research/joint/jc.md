# Joint layer collapse by continuation (jc), its predecessor negotiate, and jc2

**Status:** jc worked (best family); negotiate partial; jc2 likely worked, unconfirmed (stopped at 61–62 of 99 attempts).
**First published:** 2026-10-24, commit [e55d880](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e55d880d62b400dafeda64c771d763fedf44f1ca) on branch `claude/keen-wright-mlkjv6` (results [0d4b7e9](https://github.com/magnetic-trowel/kicad-auto-everything/commit/0d4b7e94061b3ca99bc19a76658eb0e8d0363677); idea doc [1a36bd0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/1a36bd0caa665eacade6cf757d6e4521db492cb8); negotiate [44831ff](https://github.com/magnetic-trowel/kicad-auto-everything/commit/44831ff3f802b1758b9c1299e0ae0b212d581f9a); jc2 [7c80c05](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7c80c052c3007e04658122c452002e256c0399b0), results [36270e7](https://github.com/magnetic-trowel/kicad-auto-everything/commit/36270e7711003e2565fd4cb3b172f1bacf624d1d)).

Start with every part at its own optimum and every net routed alone, overlaps allowed. Then raise one
price β on shared space so that parts and wires both move out of each other's way, until the board is
legal. Against the same method with parts frozen after the start, the joint version used about half the
copper on 24 of 24 boards: direct evidence that placement and routing cannot be done separately.

## Predecessor: negotiate (idea 1, PathFinder generalized)

**Mechanism** (`methods.py:negotiate`). Parts start at their HPWL optimum, overlapping freely. Each
round: wires re-route under present and history prices (PathFinder); each part best-responds to HPWL +
priced courtyard overlap + priced foreign-wire cells under its pads + courtyard history; prices rise
until parts are legal.

**Results** (v5, ab33, seed 0, [drc-v5-ab33.md](../../../tools/research/pnr/results/drc-v5-ab33.md)):
legal 0.818, clean 0.545, completion **0.897** (best single method of v5) vs `seq` 0.788 / 0.545 /
0.863, but length 3708 vs 3327 mm (+11%); place physics 1.89×, routed 1.40× human.

**Verdict: partial.** If wire prices only grow, parts flee wires and the layout inflates; prices must
decay where there is no conflict. jc keeps the shared-price idea but drives it by a schedule. `negotiate`
is an arm of the merit list.

## jc

**Mechanism** (`collapse_joint/jc.py`). One coupling β, one currency (cells of wire).
- **Lift (β = 0).** Every part at its own HPWL + 2 · physics optimum (overlaps allowed); every net routed
  alone.
- **Collapse iteration.** (a) Every net re-routes with PathFinder, present cost β plus history. (b)
  Every part jumps to its whole-board argmin over XY and 4 rotations of
  HPWL/g + 2 · Δphysics/g + β · (1 + history) · (keep-out overlap + foreign route cells under its pads +
  hole / cut-out conflicts), g the grid pitch. A cached-FFT engine computes a best response in ~11 FFTs
  (15× cheaper than `Kit.overlap_map`). Pin tension (weight 0.3) only from β ≥ 1; earlier it inflated
  HPWL 30%.
- **Schedule.** β starts at 0.05, × 1.35 per iteration, × 1.15 extra while conflict stalls, paced to
  reach β = 60 within the run budget; cap 500.
- **End.** Nearest legal pose (legal map + hole / cut-out checks, eviction), then PathFinder + legalize.
- **Restarts.** A continuation legalizes at median β 2.3 (~10 iterations), so ~85% of the budget repeats
  it with new random orders; the best by routed cost + 2 · physics is kept.
- **Variants.** `jc` adds a 15% `anneal_phys` polish; `jc_lv`: `phys_w` = 0; `jc_full`: restarts also
  judged by 5 · routed physics (`RoutedPhys`); `jc_frozen` (control): parts legalized after the lift,
  then frozen; `jc_nopol`: no polish.
- Failed: additive part history (poisons the best area); a 2 mm trust region (0–10% worse).

**Results.**

v5, ab33, place tasks, **seed 0** ([collapse_joint/RESULTS.md](../../../tools/research/collapse_joint/RESULTS.md);
length over 22 boards; physics × human on phys10):

| run | legal | clean | completion | length mm | vias | fast phys | routed phys |
|---|---|---|---|---|---|---|---|
| seq | 0.788 | 0.545 | 0.863 | 3386 | 60 | 4.05 | 1.39 |
| negotiate | 0.818 | 0.545 | 0.897 | 3749 | 58 | 1.89 | 1.40 |
| combo | 0.848 | 0.636 | 0.897 | 2943 | 25 | 1.03 | 1.13 |
| **jc** | **0.879** | **0.667** | 0.897 | 2977 | 42 | **0.82** | 1.05 |
| jc_nopol | 0.879 | 0.606 | 0.893 | 2928 | 48 | 0.86 | 1.00 |
| jc_lv_nopol | 0.879 | 0.667 | 0.897 | 3045 | 48 | 2.05 | 1.29 |
| jc_frozen (control) | 0.879 | 0.485 | 0.892 | 4684 | 117 | 1.08 | 1.04 |
| jc_full (phys10 only) | 8/10 | 4/10 | 0.943 | — | — | 0.84 | **0.80** |

- **Joint vs frozen:** same lift, schedule, restarts and router; joint is shorter on **24 of 24** boards
  (gmean **0.52×**), 59% fewer vias, clean 0.606 vs 0.485 (no polish in either).
- Restarts carry much of the gain: the first continuation is best on only 6 of 31 boards; the best is 15%
  cheaper (median).
- Wire-history density predicts failure: median 4.3 / mm² on incomplete vs 0.18 on complete boards
  (Mann–Whitney p = 0.046, n = 31).
- `jc_full` beats human routed physics on 8 of 10 boards, but open hops (priced as straight strips)
  flatter it; with no open hop jc's routed physics is 1.27 vs combo 1.22.

v7, joint tasks, engine v6.3, 3 seeds, **partial**: jc reached 88 and jc_lv 94 of 99 attempts; on the 24
boards with all 3 seeds ([v7-baselines.md](../../../tools/research/pnr/results/v7-baselines.md)):

| arm | legal | clean | completion | length mm (16 boards) | vias |
|---|---|---|---|---|---|
| seq | 0.917 | 0.583 ± 0.042 | 0.899 | 2593 | 60.7 |
| combo | 0.944 | 0.653 ± 0.062 | 0.932 | 2283 | 29.0 |
| jc_lv | **0.986** | **0.722 ± 0.021** | 0.928 | 2344 | 41.0 |
| jc | **0.986** | 0.694 ± 0.062 | 0.932 | 2351 | 43.7 |

jc has no v7 physics score. xf3 baseline (fixed engine 4c4330a, all 33 boards, 3 seeds, mean ± sd;
[xf_pour/RESULTS.md](../../../tools/research/xf_pour/RESULTS.md)): jc legal 1.000, clean 0.687 ± 0.017,
completion 0.935, fast physics 0.96 ± 0.08, routed 1.18 ± 0.08.

**Verdict: worked (best family).** Best legality and clean rate in both eras and best fast physics in
v5. Caveats: v5 is one seed; in v7 the clean gains over `combo` are within seed noise and the jc runs are
incomplete; jc uses more vias than combo (+70% in v5, +50% in v7) and is weaker on large B boards;
`RoutedPhys` time (in `jc_full`) is outside the CPU clock. Bugs found later are fixed in jc2.

## jc2: jc hardened

**Diagnosis** (logs on 5 boards; [BUGS.md](../../../tools/research/collapse_joint/BUGS.md)). Vias appear
late, at β > 1 once parts stop moving, when the router hops layers instead of detouring. Open hops come
from the end phase: jc threw away a fully routed but slightly conflicting state and re-negotiated from
scratch, turning 0 open connections into 8–10 on paw3395; a second unguarded PathFinder could drop more.
The schedule burned budget at β = 500 with a flat conflict. Restarts were ranked without regard to
legality. On large boards only 2 continuations fit, so the polish got ~43% of the budget, not 15%.

**Mechanism** (`collapse_joint/jc2.py`, a jc subclass with switches):
- `engine`: drop jc's own hole / cut-out terms, which engine v6 already stamps (fixes double counting);
- `guard`: keep the better of before / after for the end-phase PathFinder retry and the polish;
- `legal_first`: illegal parts add 1e6 to a restart's cost;
- `stall=4`: stop a continuation after 4 flat iterations at β_max;
- `complete`: renegotiate each open net with its bounding-box neighbours, then `repair_phys`;
- `via_beta`: via price × (1 + ln(1 + β));
- `clean`: hard re-route of via nets and their via neighbours at 8 mm per via;
- `minplus_w=0.5` from β ≥ 1 ([min-plus maps](jc-extensions.md#min-plus-best-response-maps-t1)).
- Rejected in screening: perturbed restarts, `fill`, `via_part`, `end_alt`.
- Final arms: `jc2_fix` = guard + legal_first + stall + complete + via_beta + clean (physics objective);
  `jc2_fixmp_lv` = the same + late min-plus, `phys_w` = 0.

**Results** (v7, engine v6.3, 120 CPU-s, paired on attempts every arm finished; **stopped at 61 (physics)
and 62 (lv) of 99 attempts; no physics scoring**;
[RESULTS-jc2.md](../../../tools/research/collapse_joint/RESULTS-jc2.md)):

| run | legal | clean (seeds) | completion | open conn. | length mm | vias |
|---|---|---|---|---|---|---|
| jc | 0.984 | 0.557 (.62/.55/.50) | 0.906 | 154 | 8882 | 245 |
| **jc2_fix** | 0.934 | **0.623** (.71/.55/.60) | **0.917** | **138** | 8872 | **204 (−17%)** |
| jc_lv | 0.984 | 0.613 (.62/.62/.60) | 0.907 | 151 | 8624 | 205 |
| **jc2_fixmp_lv** | **1.000** | 0.613 (.67/.52/.65) | **0.928** | **120** | **8325 (−3.5%)** | **143 (−30%)** |

jc2_fix's lower legality comes from the 5 boards engine v6.4 changes; on the 28-board subset legal is
0.981 for both. A 5-board devB screen (1 seed) hinted the fix stack does not hurt routed physics (1.14
vs jc 1.23) and min-plus does (1.54).

**Verdict: likely worked, unconfirmed.** A cleanup of jc rather than a new method: fewer vias and open
connections, equal length, clean within the seed spread. Most of the gain comes from bug fixes in jc's
end phase. Still open: the remaining 37–38 attempts, physics scores, a base-vs-fix ablation.

`negotiate`, `jc`, `jc_lv`, `jc_full`, `jc2_fix` and `jc2_fixmp_lv` are arms of the merit list; the
500-board comparison (`merit-500r3` / `merit-500r3k`) is running.
Results on the 500-board comparison: pending.

## Code

- [`tools/research/collapse_joint/jc.py`](../../../tools/research/collapse_joint/jc.py) (`jc`, `jc_lv`,
  `jc_full`, `jc_frozen`, `jc_nopol`, `jc_lv_nopol`), [`jc2.py`](../../../tools/research/collapse_joint/jc2.py),
  `agg3.py` (3-seed aggregation), [`score_final.md`](../../../tools/research/collapse_joint/score_final.md).
  Obstruction-map figures are not published (third-party boards).
- `negotiate`: [`tools/research/pnr/methods.py`](../../../tools/research/pnr/methods.py).
- Run: `run.py tools/research/collapse_joint/jc.py:jc IN OUT --budget 120 --seed N`; drivers in
  [`pnr/scripts/`](../../../tools/research/pnr/scripts/) (`jc-seeds.sh`).

## Related

[jc-extensions.md](jc-extensions.md) (harmonic pressure, learned value, quality-diversity, min-plus and
exact physics maps on top of jc), [pour-models.md](pour-models.md) (pour-damage maps in jc),
[layer-collapse-analysis.md](layer-collapse-analysis.md), [combo.md](combo.md),
idea: [layer-collapse.md](../../ideas/original/layer-collapse.md). The kae line's own joint loop:
[kae-joint-loop.md](kae-joint-loop.md).
