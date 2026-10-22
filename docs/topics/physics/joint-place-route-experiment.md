# Joint vs sequential placement and routing: a proof of concept

**TL;DR**
- At equal CPU (50 s), joint SA (an HPWL start, then moves accepted on routed length, vias, ground-plane cuts and hot-loop area) beat a longer sequential SA on 5/5 30-part boards (median −17% routed objective J) and an equal-CPU restart portfolio on 3/5 (median −10%) (exact sign tests: p = 0.06 and p = 1.0). Over both sizes, joint ties the equal-CPU portfolio 5/10 (median J ratio 0.96, 95% CI 0.83–1.24). The physics term's effect is 0.99 (0.93–1.05). Only "joint improves its own start" is significant (10/10, p = 0.002); run-to-run spread of one board is ×1.18 [C, [rt_jpr_stats](../../../tools/research/physics/rt_jpr_stats.py)]. The gains were fewer vias (median 16 vs 24) and smaller hot loops (3 vs 6–8.5 mm²), not shorter wire.
- At 50 parts it was a coin flip: 2/5 against each control (median +4% and +9%). Routed moves cost ~25× an HPWL move, and when the start sits in a bad basin, restarts escape it and local joint moves do not.
- The joint stage improved its own start in 10/10 runs (median −18% at 30 parts, −24% at 50). After a converged 50 s sequential run, 40 s of joint search beat 40 s more SA on 3 of 4 boards.
- Proxies rank coarse differences (HPWL vs routed J, Spearman 0.87–0.94) but not near-equal placements: 44% of pairs within 3% HPWL differed by more than 10% in J. A straight-line hot-loop proxy ranked the routed loop at only 0.23–0.79.
- Synthetic 2-layer grid boards, a Python router and 5 seeds per size: this bounds mechanisms and costs, not real-board quality. Routing completion was 100% in every arm, so completion did not discriminate.

## Key facts

### Setup [C]

Script: [`tools/research/physics/jpr_joint_vs_sequential.py`](../../../tools/research/physics/jpr_joint_vs_sequential.py) (GPL-3.0-or-later; Python 3.11+, NumPy, Shapely, SciPy).

| Item | Value |
|---|---|
| Instances | `pcbgen.make_instance` from [solver-bench](../../../tools/research/solver-bench/) at N = 30 and 50, seeds 0–4, utilization 0.6: 30–76 nets, boards 29×19 to 43×28 mm; R/C 0402/0603, SOT-23, SOIC-8, QFN-32, TQFP-64, 2×5 headers; 4 mounting-hole keep-outs and an antenna-style edge keep-out; decaps with an L1 ≤ 3 mm rule |
| Added physics | 1–3 **hot loops** per board: an IC VIN pin → C0603 → an adjacent IC GND pin, as two 2-pin nets |
| Boundary conditions | One 2×5 header fixed at the bottom edge; parts may not leave the outline (hard domain constraint) |
| Router | 2-layer grid at 0.5 mm pitch (track + clearance), node capacity 1; SMD pads block the top layer, THT pads both; a via costs 4 steps; bottom-layer steps cost 2×, because the bottom should stay a solid ground plane |
| Referee | PathFinder (first pass free, then present factor 0.5 × 1.3 per pass, history +1 per overuse, ≤ 40 passes) re-routing each **final placement from scratch**, identical for every arm |
| Legalizer | Greedy spiral repair of residual overlaps, same for every arm |
| Routed objective J (mm-equivalent) | wirelength + 2·vias + 1·bottom-layer length + 4·hot-loop area (mm²) + 40·failed nets + 100·(overlaps + keep-out intrusions + decap violations) |
| Hot-loop term | Enclosed plan-view area of the routed VIN and GND paths (lobes add) plus 1.5 mm × loop length on the bottom layer. This is a **2-layer, far-plane simplification**: with a plane within ~0.2 mm, loop inductance follows height × squares or the MS2 proxy, not area ([solver-ladder](solver-ladder.md)) |

**Arms.** Budgets are process CPU seconds, because the machine was shared and wall time was not usable: TP = 10 s, TJ = 40 s, B = TP + TJ = 50 s.

| Arm | What it does | CPU |
|---|---|---|
| `seq` | SA on HPWL + straight-line hot-loop area + penalties, then referee | TP |
| `seqx` | `seq` plus a crossing proxy (0.5 mm per crossing of star-decomposed nets; best of {0.5, 1.5, 3} on held-out seed 9) | TP |
| `seq_long` | `seq` SA for the whole budget | B |
| `seq_port` | `seq`, then restarts from new random placements (SA + referee each) until B is spent; keep the best J | B |
| `joint` | `seq`'s placement and its referee routes as the start. Every SA move first checks overlaps and keep-outs (hard; illegal moves are rejected before routing), then rips up and A*-reroutes the affected nets (nets on the moved parts plus nets crossing their new pads) and is accepted on the routed objective plus an overflow penalty (2 → 40 mm per overused node) | B |
| `joint_nophys` | `joint` whose acceptance ignores hot-loop area and bottom-layer length | B |
| `long_joint` / `seq_longer` | follow-up on 4 boards: `seq_long` (50 s) then 40 s of joint, vs 90 s of `seq` SA | 90 s |

Commands: `python jpr_joint_vs_sequential.py --n 30 --seed 0 --util 0.6 --tp 10 --tj 40` (six arms); add `--arms long_joint,seq_longer` for the follow-up and `--tp 3 --proxy-study 40` for the proxy study.

### Results [C]

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

**Joint vs equal-CPU controls** (per-board ratio of J):

| N | joint vs seq_long | joint vs seq_port | joint vs its start (seq) |
|---|---|---|---|
| 30 | 5/5 wins, median −17.0% (−56.6 to −3.2%) | 3/5, −10.3% (−24.7 to +23.7%) | 5/5, −17.6% |
| 50 | 2/5, +3.8% (−35.0 to +32.5%) | 2/5, +9.4% (−23.5 to +40.5%) | 5/5, −24.0% |

**Follow-up after a converged start** (J): 30/0: long_joint 362.5 vs seq_longer 364.0; 30/1: 342.5 vs 483.0; 50/0: 788.0 vs 714.0; 50/1: 683.8 vs 726.8. Joint is better on 3 of 4, but its gain over its own start was small at 50 parts (+0.1% and −10.6%).

**Physics term in the acceptance** (`joint` vs `joint_nophys`): lower J on 4/5 boards at N = 30 and 3/5 at N = 50; smaller median hot loops at N = 30 (3.0 vs 4.0 mm²). The effect is smaller than seed-to-seed noise.

**Crossing proxy** (`seqx` vs `seq`, equal CPU): worse at N = 30 (2/5; 2.5–3.5× fewer SA moves) and better at N = 50 (4/5, median −38%). Better proxies cost compute too.

**Proxy study** (`--proxy-study 40 --tp 3`: placements of mixed quality, each routed by the referee; illegal ones dropped; boards 30/0, 50/0, 30/1, 50/1):

| Measure | Value |
|---|---|
| Spearman, HPWL vs routed J | 0.884 / 0.939 / 0.874 / 0.901 |
| Spearman, HPWL vs routed wirelength | 0.897 / 0.961 / 0.984 / 0.978 |
| Spearman, crossings vs routed J | 0.763 / 0.891 / 0.703 / 0.808 |
| Spearman, straight-line loop area vs routed loop area | 0.231 / 0.453 / 0.791 / 0.577 |
| Pairs within 3% HPWL whose routed J differs by > 10% | 41/103, 10/16, 4/7, 3/5 (58/131 = 44%) |

This matches Cadence's 12,000-placement finding at small scale ([joint-place-route](joint-place-route.md)).

**Cost** (median per CPU second): HPWL SA 13.9k moves (N = 30) and 12.2k (N = 50); joint 1.6k proposals, of which 510–550 were legal and routed (2.5 and 1.6 nets re-routed per move). The gap is ~25× per routed move. Five restarts fit in the portfolio budget.

### Development lessons [C]
- **Keep hard constraints hard.** A first version of `joint` priced overlaps with a ramped penalty. It ended with 2–7 overlaps, and the end-of-run legalizer moved parts without regard to their routes: on one board the joint's own routed J of 602.5 became 1163.5 after legalization and re-routing. Rejecting illegal moves before routing fixed this and raised the routed-move rate 3–7× (from 70–170 to 510–550 per second). A joint optimizer must stay legal throughout, or legalize with its routes in view (JPR14, JPR37).
- **Incremental route state drifts.** At N = 50 the joint's maintained routes ended with 2–10 failed nets in 4/5 runs, while a from-scratch PathFinder re-route of the same placement was clean. Periodic global renegotiation, or LPA* repair with history costs, is needed (JPR6). Scoring the joint's own routes instead of the referee gives the same picture at N = 30 (wins 5/5 and 4/5 against the two controls) and a worse one at N = 50 (2/5 and 1/5).
- **Variance is large.** Three runs of one board and seed gave `seq` J of 241, 290 and 337 (CPU budgets change move counts). Five seeds show direction, not significance.

## Recommendations for our system
- Use routed-objective search as a **refinement stage** after a fast, converged sequential placement, never as the cold start. The per-move cost makes cheap global moves essential, and the joint stage won on 3/4 boards in that role [C/I].
- Spend extra compute on **restarts and joint refinement together**: at 50 parts the portfolio and the joint stage each won where the other lost. Successive halving over restarts, with joint refinement of the survivors, follows directly (JPR45) [I].
- Reject illegal moves before routing them; make admissible-pose masks and the channel-width legalizer part of the joint loop (JPR37, JPR14) [C].
- Make delayed acceptance the next step: 53–62% of routed moves were rejected after paying for the reroute (JPR41) [C].
- Adopt the equal-CPU sequential portfolio as the required control in the bench harness (JPR46); `kicad-cli` DRC on re-opened boards then replaces our referee [I].
- Score hot loops with MS2 or height × squares on boards with a near plane; the area term here fits only the 2-layer far-plane case [I].

## Conflicts and open questions
- **Round-3 corrections (2026-10-22):** sign tests and confidence intervals added; joint ties the equal-CPU portfolio 5/10, so the supported claim is refinement of a sequential start ([red-team](red-team.md)).
- **Not a real-board result.** No clearance geometry, diff pairs, pours, 4+ layers, or DRC; nets have 2–4 pins; the router always completed. Whether the via and loop gains survive Freerouting realization and `kicad-cli` DRC on PCBWorld D3 is the open test.
- **Language bias.** Both arms are pure Python; Rust may shift the 50-part outcome [I].
- **Post-hoc fix.** The legality fix to `joint` was made after a first matrix in which `joint` lost badly. It is a correctness fix, applied before the final runs, but it was not pre-registered.
- **Weights.** J's weights are choices; the I1 ledger should set them.

## Sources
- Script: [`tools/research/physics/jpr_joint_vs_sequential.py`](../../../tools/research/physics/jpr_joint_vs_sequential.py); instance generator and earlier SA and PathFinder measurements: [solver benchmarks](../solvers/benchmarks.md)
- Prior art for the method (PROXI, Starfish) and Cadence's proxy study: [joint-place-route](joint-place-route.md)

See also: [joint-place-route](joint-place-route.md) · [ideas: joint placement and routing](../../ideas/physics-first/joint-place-route.md) · [pathfinder-negotiated-congestion](../routing/pathfinder-negotiated-congestion.md) · [metaheuristics-and-qd](../solvers/metaheuristics-and-qd.md) · [solver-ladder](solver-ladder.md)
