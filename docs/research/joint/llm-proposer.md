# LLM proposes relational moves, the engine verifies

**Status:** did not work (routing inconclusive, physics no merit).
**First published:** 2026-10-24, commit [6e5c658](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6e5c658f0ea7c268fe8d44682160bf7a820b4d4b) on branch `claude/keen-wright-mlkjv6` (results [13be758](https://github.com/magnetic-trowel/kicad-auto-everything/commit/13be75829834fe3da9aae61f835b35b1becf7b17)).

Language models handle relations much better than coordinates, so the model only proposes relational
moves ("put C3 tight to U1 pin 5", "swap R1 and R2") and the place-and-route engine realizes and verifies
them (idea 30 of the [catalog](../../ideas/original/joint-pnr.md)). It matched blind annealing on
routing and was about 110× worse than physics annealing on physics.

## Idea and how it works

No model API was available, so **the agent itself played the LLM**, seeing only what a model would: a
PNG render and a text summary. `pnr_llm/llmloop.py`:

- **Show.** Copper per layer, missing links, blocking parts (`methods.blockers`), zooms with pad numbers.
  The text summary lists unrouted links, pads no track can enter, illegal parts (pad outside the board or
  in a footprint cut-out), net neighbours, and with `--phys` the per-structure physics breakdown.
- **Move language (JSON).** `near` (part or pad, side, tight / close / loose), `dir`, `between`,
  `to_edge`, `rotate`, `swap`, `push`, rigid groups (`with`), `rot: any`. Each move is resolved to the
  nearest legal pose (`Kit.legal_map` plus a pad-inside map); moves landing > 3 mm from the request are
  refused.
- **Verify.** `Kit.reroute`, then `Router.pathfinder`. Keep the batch if it is better on the tuple
  (illegal parts, unrouted connections, `total_cost`), or (illegal, `total_cost` + 2 · physics) in
  physics mode; if rejected, try each move alone.
- **Controls.** The same verifier and move language with a `random` proposer and a rule-based `blocker`
  proposer (shift a blocker, or pull a disconnected pin's part to its peer).

## What we tried

- **Routing:** 4 hard boards (electron271, siderakb-pmw3610, paw3395, pmw3610), engine v4, harness
  attempt 0; 2–6 rounds per board; controls 6 rounds each, re-run on a frozen v4 copy
  ([3a6b885](https://github.com/magnetic-trowel/kicad-auto-everything/commit/3a6b885874b8777fe76337783c7b4bf40fe69b14)).
  These v4 rounds were a **second pass**: the proposer had seen the verifier's answers in an unscored v3
  pilot on the same boards.
- **Physics:** olimex dcdc and noisecard, engine v5, `--phys`.

## Results

Routing ([pnr_llm/RESULTS.md](../../../tools/research/pnr_llm/RESULTS.md); L = legal, u = DRC
unconnected items):

| board | seq | blocker ctl | random ctl | **LLM** (rounds) | anneal (v3, 120 s) | human, routed |
|---|---|---|---|---|---|---|
| electron271 | L u13 | L u17 | L u16 | L u15 (5) | L u15 | u24 |
| siderakb-pmw3610 | illegal u14 | illegal u14 | illegal u14 | **L u5** (3) | L u5 | u6 |
| paw3395 | illegal u24 | L u8 | L u9 | **L u7** (3) | L u7 | u4 |
| pmw3610 | L u9 | L u7 | L u6 | L u6 (2) | L u6 | u4 |
| completion / legal boards | 0.62 / 2 | 0.71 / 3 | 0.72 / 3 | **0.78 / 4** | | |

Physics (place-terms total, lower is better; human in brackets):

| board | seq | LLM | random ctl | seq_phys | anneal_phys |
|---|---|---|---|---|---|
| olimex dcdc [7.39] | 1407.7 | 696.4 (DRC-clean) | 1291 / 1377 | **6.17** | **5.83** (DRC-clean) |
| noisecard [5.02] | 19.8 | = seq (no move accepted) | = seq | n/a | 18.4 |

Cost: about 3k–5k tokens per round (1.4k–2.6k of image and summary, 60–220 output, plus an estimated
0.5k–2k of reasoning), 10k–35k per board; verifier 1–20 s per round. All gains came in rounds 1–3.

## Verdict

- **Routing: inconclusive, leaning no merit.** The LLM equalled the best optimizer and beat both cheap
  proposers, but it had seen its pilot answers, and its whole edge is two legality fixes that a rule
  ("move every illegal part out") would also make.
- **Physics: no merit.** Opaque terms that `Phys.delta` prices exactly at thousands of poses beat
  engineering priors; `seq_phys` ends ~110× lower than the LLM.
- Caveats: the engine changed v3 → v4 → v5 during the work; resolver bugs (teleporting swaps, `to_edge`
  off-board, empty correlation for single-pad parts) were fixed mid-run; n = 4 + 2 boards; one "LLM"
  (the agent).
- Recommended production use: 1–3 model calls per board where search is blind (a diagnosis call for
  illegal or impossible parts and nets; one restructuring bundle such as connector edge or sensor
  orientation), then `anneal_phys` / `repair` for everything metric. Beat a rule-based "fix illegal
  parts" proposer first.

Not a merit-list arm.

## Code

[`tools/research/pnr_llm/llmloop.py`](../../../tools/research/pnr_llm/llmloop.py) (render, summary,
move resolver, verifier, controls), `emit.py` (hands boards to the harness). The move logs of the runs
were in git-ignored `kae-work/` and are not published; the RESULTS appendix quotes the key moves.

## Related

[anneal-and-repair.md](anneal-and-repair.md), [physics-objective.md](physics-objective.md), and the llm-design area of
`docs/research/` (other LLM-driven work).
