# Joint vs sequential placement and routing: a proof of concept

Scope: the synthetic-board experiment comparing joint SA (moves accepted on routed objective) with sequential and equal-CPU restart controls; proxy study; method lessons. Canonical home of all JPR PoC numbers. Not here: architecture and prior art -> [joint-place-route](joint-place-route.md).
Keys: joint SA, sequential SA, seq, seqx, seq_long, seq_port, joint_nophys, long_joint, seq_longer, routed objective J, equal-CPU restart portfolio, proxy study, Spearman HPWL, hot-loop area, PathFinder referee, jpr_joint_vs_sequential.py, rt_jpr_stats, JPR6, JPR14, JPR37, JPR41, JPR45, JPR46

**Results** [C, [rt_jpr_stats](../../../tools/research/physics/rt_jpr_stats.py)]:
- Joint improves its own sequential start 10/10 (p = 0.002; median −18%) but ties an equal-CPU restart portfolio over both sizes, 5/10 (median J ratio 0.96, 95% CI 0.83–1.24): a refiner after diverse starts, not a cold start.
- 30 parts: wins come from fewer vias and smaller hot loops, not shorter wire (sign tests vs `seq_long` p = 0.06, vs `seq_port` p = 1.0).
- 50 parts: coin flip; routed moves cost ~25× an HPWL move, and from a bad basin restarts escape while local joint moves do not.
- Physics-term effect 0.99 (0.93–1.05), below noise; run-to-run spread of one board ×1.18.
- Proxies rank coarse differences (HPWL vs routed J Spearman 0.87–0.94) but not near-equal placements (44% of pairs within 3% HPWL differ > 10% in J); straight-line hot-loop proxy vs routed loop 0.23–0.79.

Bounds: synthetic 2-layer grid boards, Python router, 5 seeds per size; mechanisms and costs, not real-board quality. Completion 100% in every arm, so it did not discriminate.

## Setup [C]

Script: [`tools/research/physics/jpr_joint_vs_sequential.py`](../../../tools/research/physics/jpr_joint_vs_sequential.py) (GPL-3.0-or-later; Python 3.11+, NumPy, Shapely, SciPy).

| Item | Value |
|---|---|
| Instances | `pcbgen.make_instance` from [solver-bench](../../../tools/research/solver-bench/), N = 30 and 50, seeds 0–4, utilization 0.6: 30–76 nets, boards 29×19 to 43×28 mm; R/C 0402/0603, SOT-23, SOIC-8, QFN-32, TQFP-64, 2×5 headers; 4 mounting-hole keep-outs, an antenna-style edge keep-out; decaps with an L1 ≤ 3 mm rule |
| Added physics | 1–3 **hot loops** per board: IC VIN pin → C0603 → adjacent IC GND pin, as two 2-pin nets |
| Boundary conditions | one 2×5 header fixed at the bottom edge; parts may not leave the outline (hard) |
| Router | 2-layer grid, 0.5 mm pitch (track + clearance), node capacity 1; SMD pads block top, THT both; via = 4 steps; bottom-layer steps 2× (bottom should stay a solid ground plane) |
| Referee | PathFinder (first pass free, then present factor 0.5 × 1.3 per pass, history +1 per overuse, ≤ 40 passes) re-routing each **final placement from scratch**, identical for every arm |
| Legalizer | greedy spiral repair of residual overlaps, same for every arm |
| Routed objective J (mm-equivalent) | wirelength + 2·vias + 1·bottom length + 4·hot-loop area (mm²) + 40·failed nets + 100·(overlaps + keep-out intrusions + decap violations) |
| Hot-loop term | enclosed plan-view area of routed VIN and GND paths (lobes add) + 1.5 mm × loop length on bottom. **2-layer far-plane simplification**: with a plane within ~0.2 mm, loop L follows height × squares or MS2, not area ([solver-ladder](solver-ladder.md)) |

**Arms.** Budgets in process CPU seconds (shared machine, wall time unusable): TP = 10 s, TJ = 40 s, B = TP + TJ = 50 s.

| Arm | What it does | CPU |
|---|---|---|
| `seq` | SA on HPWL + straight-line hot-loop area + penalties, then referee | TP |
| `seqx` | `seq` + crossing proxy (0.5 mm per crossing of star-decomposed nets; best of {0.5, 1.5, 3} on held-out seed 9) | TP |
| `seq_long` | `seq` SA for the whole budget | B |
| `seq_port` | `seq`, then restarts from new random placements (SA + referee each) until B is spent; best J | B |
| `joint` | start = `seq` placement + its referee routes. Each SA move checks overlaps and keep-outs first (hard; illegal moves rejected before routing), rips up and A*-reroutes affected nets (nets on moved parts + nets crossing their new pads), accepts on routed objective + overflow penalty (2 → 40 mm per overused node) | B |
| `joint_nophys` | `joint` with acceptance ignoring hot-loop area and bottom length | B |
| `long_joint` / `seq_longer` | follow-up, 4 boards: `seq_long` (50 s) then 40 s joint, vs 90 s `seq` SA | 90 s |

Commands: `python jpr_joint_vs_sequential.py --n 30 --seed 0 --util 0.6 --tp 10 --tj 40` (six arms); `--arms long_joint,seq_longer` for the follow-up; `--tp 3 --proxy-study 40` for the proxy study.

## Results [C]

**Routed objective J per board** (lower is better; all arms 100% routed):

| N, seed | seq | seqx | seq_long | seq_port | joint | joint_nophys |
|---|---|---|---|---|---|---|
| 30, 0 | 381.5 | 1173.5 | 379.0 | 375.5 | **314.5** | 335.5 |
| 30, 1 | 406.5 | 819.5 | 404.5 | 443.5 | **334.0** | 347.5 |
| 30, 2 | 369.5 | 504.5 | 342.5 | 369.5 | **331.5** | 337.0 |
| 30, 3 | 950.0 | 764.3 | 1244.5 | 528.5 | 539.5 | **498.9** |
| 30, 4 | 403.0 | 392.5 | 398.0 | **304.0** | 376.0 | 420.0 |
| 50, 0 | 2954.5 | **745.0** | 1945.5 | 900.0 | 1264.5 | 1478.0 |
| 50, 1 | 809.2 | 947.5 | **692.5** | 805.0 | 719.0 | 722.0 |
| 50, 2 | 904.9 | 801.9 | 891.0 | 899.1 | 687.5 | **649.2** |
| 50, 3 | 1113.3 | 443.9 | 445.5 | 460.7 | 590.2 | 594.5 |
| 50, 4 | 669.0 | **415.0** | 536.5 | 535.5 | 586.0 | 558.0 |

**Medians per arm:**

| N | Arm | J | Wire (mm) | Vias | Bottom (mm) | Hot loop (mm²) |
|---|---|---|---|---|---|---|
| 30 | seq_long | 398.0 | 262.5 | 24 | 49.5 | 8.5 |
| 30 | seq_port | 375.5 | 271.5 | 24 | 46.0 | 6.0 |
| 30 | joint | **334.0** | 247.0 | **16** | 31.5 | **3.0** |
| 30 | joint_nophys | 347.5 | 257.5 | 17 | 24.0 | 4.0 |
| 50 | seq_long | 692.5 | 385.5 | 30 | 64.0 | 34.8 |
| 50 | seq_port | 805.0 | 426.5 | 32 | 63.5 | 14.5 |
| 50 | joint | 687.5 | 407.0 | **22** | 60.0 | 16.6 |
| 50 | joint_nophys | **649.2** | 407.5 | 25 | 48.5 | 19.4 |

**Joint vs equal-CPU controls** (per-board J ratio):

| N | joint vs seq_long | joint vs seq_port | joint vs its start (seq) |
|---|---|---|---|
| 30 | 5/5 wins, median −17.0% (−56.6 to −3.2%) | 3/5, −10.3% (−24.7 to +23.7%) | 5/5, −17.6% |
| 50 | 2/5, +3.8% (−35.0 to +32.5%) | 2/5, +9.4% (−23.5 to +40.5%) | 5/5, −24.0% |

- **Follow-up after a converged start** (long_joint vs seq_longer J): 30/0 362.5 vs 364.0; 30/1 342.5 vs 483.0; 50/0 788.0 vs 714.0; 50/1 683.8 vs 726.8. Joint better 3/4; its gain over its own start was small at 50 parts (+0.1%, −10.6%).
- **Physics term in acceptance** (`joint` vs `joint_nophys`): lower J on 4/5 at N = 30, 3/5 at N = 50; median hot loop 3.0 vs 4.0 mm² at N = 30. Smaller than seed-to-seed noise.
- **Crossing proxy** (`seqx` vs `seq`, equal CPU): worse at N = 30 (2/5; 2.5–3.5× fewer SA moves), better at N = 50 (4/5, median −38%). Better proxies cost compute too.

**Proxy study** (`--proxy-study 40 --tp 3`: placements of mixed quality, each routed by the referee, illegal ones dropped; boards 30/0, 50/0, 30/1, 50/1). Matches Cadence's 12,000-placement finding at small scale ([joint-place-route](joint-place-route.md#1-why-staged-place-then-route-gets-stuck)).

| Measure | Value |
|---|---|
| Spearman, HPWL vs routed J | 0.884 / 0.939 / 0.874 / 0.901 |
| Spearman, HPWL vs routed wirelength | 0.897 / 0.961 / 0.984 / 0.978 |
| Spearman, crossings vs routed J | 0.763 / 0.891 / 0.703 / 0.808 |
| Spearman, straight-line vs routed loop area | 0.231 / 0.453 / 0.791 / 0.577 |
| Pairs within 3% HPWL whose routed J differs > 10% | 41/103, 10/16, 4/7, 3/5 (58/131 = 44%) |

**Cost** (median per CPU second): HPWL SA 13.9k moves (N = 30), 12.2k (N = 50); joint 1.6k proposals, 510–550 legal and routed (2.5 and 1.6 nets re-routed per move): ~25× per routed move. Five restarts fit the portfolio budget.

## Method lessons [C]

- **Keep hard constraints hard.** A ramped overlap penalty left 2–7 overlaps at run end; the end-of-run legalizer then moved parts blind to their routes (one board: joint's routed J 602.5 → 1163.5 after legalization and re-route). Rejecting illegal moves before routing avoids this and raises routed moves 3–7× (70–170 → 510–550 per second). Stay legal throughout, or legalize with routes in view (JPR14, JPR37).
- **Incremental route state drifts.** At N = 50 the joint's maintained routes ended with 2–10 failed nets in 4/5 runs, while a from-scratch PathFinder re-route of the same placement was clean: needs periodic global renegotiation or LPA* repair with history costs (JPR6). Scoring the joint's own routes instead of the referee: same at N = 30 (5/5, 4/5 vs the two controls), worse at N = 50 (2/5, 1/5).
- **Variance is large.** Three runs of one board and seed gave `seq` J 241, 290, 337 (CPU budgets change move counts). Five seeds show direction, not significance.
- **Delayed acceptance next:** 53–62% of routed moves were rejected after paying for the reroute (JPR41).

## Consequences for the system [C/I]

- Use routed-objective search as refinement after a fast, converged sequential placement, never as cold start (won 3/4 in that role).
- Spend extra compute on restarts and joint refinement together (at 50 parts each won where the other lost): successive halving over restarts, joint refinement of survivors (JPR45) [I].
- Require the equal-CPU sequential portfolio as control in the bench harness (JPR46); `kicad-cli` DRC on re-opened boards replaces our referee [I].
- Score hot loops by MS2 or height × squares near a plane; this area term fits only the 2-layer far-plane case [I].

## Open questions

- **Not a real-board result:** no clearance geometry, diff pairs, pours, 4+ layers or DRC; nets have 2–4 pins; router always completed. Open test: do via and loop gains survive Freerouting realization and `kicad-cli` DRC on PCBWorld D3?
- **Language bias:** both arms pure Python; Rust may shift the 50-part outcome [I].
- **Post-hoc fix:** rejecting illegal moves before routing was adopted after a first matrix in which the penalty variant lost badly; a correctness fix applied before the final runs, not pre-registered.
- **Weights** of J are choices; the I1 ledger should set them.
- **Cost gap wording:** earlier idea rows said ~30× per move; the measured median is ~25× per legal routed move (cost line above); the ~30× figure is superseded.

## Sources

- Script above; instance generator, SA and PathFinder measurements: [solver benchmarks](../solvers/benchmarks.md).
- Prior art (PROXI, Starfish) and Cadence's proxy study: [joint-place-route](joint-place-route.md).
- Related: [ideas: joint placement and routing](../../ideas/physics-first/joint-place-route.md), [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md), [metaheuristics-and-qd](../solvers/metaheuristics-and-qd.md).
