<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# LLM as move proposer, joint optimizer as verifier (tag `llm`, catalog idea 30)

## Idea and mechanism
LLMs handle relations far better than coordinates (RAC 90.9 % vs 23.2 %,
`docs/topics/llm/interfaces-relations-vs-coordinates.md`), so the model only proposes
relational moves and the engine realizes and verifies them. No model API was available, so
**the agent played the LLM**, seeing only the PNG render and the text summary.

`llmloop.py`:
- **Show:** copper per layer, missing links, blocking parts (`methods.blockers`), zooms with
  pad numbers. The summary adds unrouted links, pads no track can enter, illegal parts (pad
  outside the board or in a footprint cut-out, as the scorer's `inside`), net neighbours, and
  with `--phys` the per-structure `Phys` breakdown.
- **Moves (JSON):** `near` (part or pad, side, tight/close/loose), `dir`, `between`,
  `to_edge`, `rotate`, `swap`, `push`, rigid group (`with`), `rot: any`. Each part goes to
  the nearest legal pose (`Kit.legal_map` plus a pad-inside map); moves landing > 3 mm off are
  refused.
- **Verify:** `Kit.reroute`, then `Router.pathfinder`. Keep the batch if better on (illegal,
  unrouted, `total_cost`), or (illegal, `total_cost + 2·phys`) as in `methods_phys`; if
  rejected, try each move alone.
- **Controls:** same verifier and language; `random`, or `blocker` (shift a blocker, or pull
  a disconnected pin's part to its peer). `emit.py` hands boards to the harness. Scores are
  harness DRC or `pnr_phys/physics_score.py`.

## Caveats
- The engine changed v3 → v4 → v5 during the work. The v3 pilot is unscored. The routing
  run is v4, with controls re-run on a frozen v4 copy (git `3a6b885`, `KAE_PNR_DIR`).
  Physics is v5. **The v4 rounds are a second pass** after the pilot showed the verifier's
  answers on the same boards.
- Resolver bugs fixed mid-run (teleporting swaps, `to_edge` off-board, `placekit.corr`
  empty for single-pad parts) count as rounds.
- Engine floors no placement fixes: unenterable pads on 0.5 mm connectors (whole net fails
  when one is the start pad), and channel capacity beside sensor cut-outs. The engine does
  not fill footprint cut-outs, so `seq` placed parts in them.

## Routing (v4, harness attempt 0; u = DRC unconnected, L = legal)
| board | seq | blocker ctl (6 rds) | random ctl (6 rds) | **LLM** (rds) | anneal-v3 (v3, 120 s) | human, routed |
|---|---|---|---|---|---|---|
| electron271 | L u13 | L u17 | L u16 | L u15 (5) | L u15 | u24 |
| siderakb-pmw3610 | illegal u14 | illegal u14 | illegal u14 | **L u5** (3) | L u5 | u6 |
| paw3395 | illegal u24 | L u8 | L u9 | **L u7** (3) | L u7 | u4 |
| pmw3610 | L u9 | L u7 | L u6 | L u6 (2) | L u6 | u4 |
| **completion / legal** | 0.62 / 2 | 0.71 / 3 | 0.72 / 3 | **0.78 / 4** | | |

Round 1 fixed both illegal boards (siderakb: JP1/JP2 out of U1's cut-out; paw3395: R1/C6 out
plus J2 to the top edge with `push`); the controls never fixed siderakb. Every LLM result
equals blind annealing and sits at the engine floor, reached in 2 to 5 batches instead of
hundreds of moves. On electron271 the engine gain (21 → 15) is invisible to DRC, because the
GND zone already joins those links. No clean pass.

## Physics (v5, place-terms total, lower is better; human in brackets)
| board | seq | LLM (7 / 6 rds) | random ctl (in-loop, 2 seeds) | `seq_phys` | `anneal_phys` 120 s |
|---|---|---|---|---|---|
| olimex-dcdc [7.39] | 1407.7 | 696.4 (DRC-clean) | 1291 / 1377 | **6.17** | **5.83** (DRC-clean) |
| noisecard [5.02] | 19.8 | = seq (none accepted) | = seq | n/a | 18.4 |

On olimex, 99.6 % of the total is buck-to-feedback coupling. Accepted: divider to the quiet
output corner, catch diode beside U1. Rejected by the model: "divider at the FB pin" and
"rotate U1", because `Phys` counts U1 in the aggressor cell. The optimizer prices every
legal spot with `ph.delta` and beats the human. On noisecard, moving the buck away from the
mic cut physics 19.6 → 11.3 but lost a connection (one board perimeter), so it was rejected.

## Cost
About 3k to 5k tokens per round (1.4k to 2.6k image plus summary, 60 to 220 output, plus an
estimated 0.5k to 2k reasoning), 10k to 35k per board. Verifier 1 to 20 s per round, proposer
15 to 90 s. All gains came in rounds 1 to 3.

## Verdict
- **Routing: inconclusive, leaning no merit.** As good as the best optimizer and better than
  both cheap proposers, but the proposer had seen its pilot answers, and its whole edge is
  two legality fixes a rule ("move every illegal part out") would also make.
- **Physics: no merit as built.** Opaque terms that `ph.delta` prices exactly at thousands
  of poses beat engineering priors; `seq_phys` ends about 110 times lower than the LLM.

## Production version
1 to 3 model calls per board, only where search is blind:
- a diagnosis call (illegal or unfixable parts, cut-outs, through-hole walls, impossible
  nets);
- one restructuring bundle (connector edge, group moves, sensor orientation);
- then `anneal_phys` / `repair` for everything metric.

The verifier should count unconnected items as DRC does (zone-aware) and judge whole
bundles. Beat a rule-based "fix illegal parts" proposer before spending model calls.

Logs (moves, accept/reject, keys, compute and wall time, token estimates):
`kae-work/pnr_llm_v4/<id>/log.jsonl`, `kae-work/pnr_llm/<id>/log.jsonl`.

## Appendix: move logs (rationales are in the logs, `note` and `why`)
Format: moves | batch accepted or rejected | engine unrouted (or phys) before → after.
- **electron271 (v4).**
  - r1 J2 to top, J1 up: rejected (21).
  - r2 rotate J3 180: refused, no room.
  - r3 J3 to top edge rot 180: **accepted, 21 → 15**.
  - r4 J3 down: rejected.
  - r5 J2 right, J1 left: accepted, cost −1.
- **siderakb (v4).**
  - r1 JP1 next to R1, JP2 left of J2 (out of U1's cut-out): **accepted, illegal 2 → 0,
    14 → 10**.
  - r2 resolver bug.
  - r3 TP2 next to JP1 with push (VIN failed from J2.2): **accepted, 10 → 5** (the floor:
    5 unenterable J2 pads).
- **paw3395 (v4).**
  - r1 R1 next to R3, C6 up (both out of the cut-out), J2 to top edge rot 90, all with push:
    **accepted, illegal 2 → 0, 24 → 7**.
  - r2 and r3 shift U2 left for channel room: refused, U1 has no room.
- **pmw3610 (v4).**
  - r1 J2 to top edge, rotate U2 180, R1 right (plateau): **accepted, 9 → 5**.
  - r2 U2 up, C8 below R1: rejected (5 → 7).
- **olimex (v5, phys).**
  - r1 divider left of U1: rejected (1408 → 1577).
  - r2 C5/R7 next to R6: **accepted, 1192**.
  - r3 R5 above 12V_E1: **accepted, 1105**.
  - r4 D2 left of U1: **accepted, 696**.
  - r5 divider above U1's FB pin: rejected (1093).
  - r6 C1/C2 next to D2: one single move accepted, phys unchanged.
  - r7 rotate U1: rejected.
- **noisecard (v5, phys).**
  - r1 C1 on U2.4, C4 under C3: rejected.
  - r2 to r4 and r6 buck group shifted left: rejected (phys 11.3 to 15.6, but routed cost up).
  - r5 C9/C7 under U1: rejected.
- **v3 pilot** (engine unrouted, not scored): electron271 21 → 13, siderakb 7 → 5,
  paw3395 11 → 7 (illegal 2 → 0), pmw3610 8 → 4. Logs are in `kae-work/pnr_llm_v3pilot/`.
