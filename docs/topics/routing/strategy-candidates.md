# Routing strategy candidates for kaebench

**TL;DR**
- Ordered by the split C failure diagnosis in [dev-eval-plan](../verification/dev-eval-plan.md). Cheap wins come first: budgets with partial output, DSN fidelity, seeded diversity.
- New engines next: fastroute, then KRT in a portfolio. A home-grown PathFinder router is gated on measured congestion.
- Every gain below is a hypothesis [I] unless tagged [P]/[M]; every row has a kill criterion.

## Key facts


| ID | Strategy | Reuse (licence) | Effort | Expected [tag] | Kill |
|---|---|---|---|---|---|
| R1 | Per-split budgets (600 s for A/B, 3,600 s for C) with partial output; default 100 passes on attempt 0 | Freerouting (GPL-3.0) | 0.5 d | C completion from 0 on timed-out boards to 0.5–0.9; C clean 0.15–0.30 together with R2 [I]. Freerouting's nightly tier C: 49.6% (2.5.0) → 69.5% (2.6.0-RC3, 360 min budget) [P]; RC3 also changed the router, so not all of that is budget | 3,600 s beats 600 s by < 0.05 and < 25% of failures are timeouts |
| R2 | DSN fidelity pack: zone handling variants, inner-cutout and copper-text keepouts, drop empty rule areas, max of class-pair clearances, `.kicad_dru` class clearances, local and NPTH clearances, 5 µm margin, neck-down floored at board minimum | [fastroute](https://github.com/parisxmas/fastroute) plugin `core.py` (GPL-3.0+); KMS fixes ([specctra-freerouting-integration](../kicad/specctra-freerouting-integration.md)) | 2–4 d | +0.10–0.20 clean on A+B [I]. fastroute demo boards: 83 → 0 unconnected, 118 → 0 errors [P, self-report] | Ablate each fix: keep it only if it cuts its target error type ≥ 50%. Drop the pack if A+B gains < 0.05 |
| R3 | Seeded diversity for best-of-k: permute component and net order in the DSN; vary via and rip-up costs, layer directions, fanout and zone variant; successive halving on C | own | 1–2 d | +0.05–0.10 cpk over the `-mp` schedule [I]; PCBWorld @1 → @5: 0.64 → 0.78 on D3-B [P] | < 0.05 gain on A+B and none on C |
| R4 | fastroute as an engine (Rust port of Freerouting; parallel pass, multi-start, keep-best on SIGTERM, `.kicad_dru` rules) | fastroute (GPL-3.0+) | 1–2 d | 4× faster on 20 boards [P, self-report]; +0.05–0.15 C clean at equal wall time [I]. Repo is 3 weeks old with one author | Below R1+R2 Freerouting on A+B cpk, or not better on C at equal core-seconds |
| R5 | DRC-driven repair: stitch zone islands; lock clean copper, delete nets with errors, re-export, re-route the residue with another config (≤ 3 rounds); clean up thin and dangling segments | KRT `repair_planes.py` (MIT) | 3–5 d | Fix ≥ 50% of near-miss boards (≤ 3 issues) [I] | < 30% of near-misses fixed |
| R6 | Portfolio selector (engine × preset per board, Thompson sampling or racing). **Compute the oracle portfolio from logs first; it is free** | own | 3–5 d | Escape routers are complementary: 7/14 each, 11/14 together [P] | Oracle beats the best single arm by < 0.05 |
| R7 | PNS residual completion via PCBWorld-Engine (beam search over waypoints and modes) | PCBWorld-Engine (GPL-3.0) | 2–3 w | PPO on this engine: 0.86 on D3-A but 0.45 on D3-B [P] | Blocked: the engine is pinned to KiCad 9.0.8. Kill if the port takes > 2 w or residual success < 30% |
| R9 | Own negotiated-congestion router | own | 6–10 w | Mostly negative evidence: a fastroute PathFinder trial got worse, OrthoRoute scored about 0.02 [P] | Build only if congestion causes ≥ 40% of C failures after R1–R5 |

**Order:** R1 → diagnosis → R2 → R3 → R4 → R5 → R6. R7 and R9 are gated.


## Sources

See [dev-eval-plan § Sources](../verification/dev-eval-plan.md#sources).

See also: [dev-eval-plan](../verification/dev-eval-plan.md), [harness](../verification/harness.md)
