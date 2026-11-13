<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# PCBWorld D3-A/B: kae, pnr and the Freerouting fork, scored by our scorer and by PCBWorld's own chain

**Status:** location measured (R8). No default changes. Report-only tooling: `tools/research/pcbworld/`.
**First published:** 2026-11-11, branch `pcbworld-d3`. Plan: [`tools/kaeres/experiments/pcbworld-d3/PLAN.md`](../../../tools/kaeres/experiments/pcbworld-d3/PLAN.md) (pre-registered), smoke and profile: [`SMOKE.md`](../../../tools/kaeres/experiments/pcbworld-d3/SMOKE.md).
Keys: PCBWorld, PCBWorld-Bench, D3-A, D3-B, clean pass, CP@5, CP@1, potential gain, transplant_v9, KiCad 9.0.8 engine, ProtoFlow, Koppar, DeepPCB, TraceMaker, KRT

**Results**
1. kae bridge is clean on every D3-A and D3-B board, on every one of 5 seeds: cp1 = cpk@5 = CP@5 = CP@1 = 1.00 / 1.00, under our scorer (KiCad 10.0.7) and PCBWorld's own (KiCad 9.0.8 engine). The paper's best is 0.94 / 0.42 (@5).
2. Freerouting fork d137fd1 `-mp 10`, one run: 0.929 / 0.900, against PCBWorld's published Freerouting 2.1.0 `-mp 10` 0.80 / 0.78 (theirs, not rerun).
3. pnr route_only: 0.939 / 0.700; its failures are only open connections.
4. The two scorers gave the same clean verdict on all 1,199 runs; PCBWorld's chain reproduces the paper's Reference row exactly.
5. kae matches the vendors' 1.00 claims (ProtoFlow, Koppar, PUNKFAB) on the same boards, scored by the benchmark's own chain, which none of them used.

## Benchmark and its chain

PCBWorld (Song et al., arXiv 2607.05915, KDD 2026 workshop; code BSD-3, engine GPL-3.0) → [topic doc](../../topics/routing/pcbworld.md).
D3-A = 99 boards with ≤ 31 pads, D3-B = 10 boards of 31-100 pads (one per quantile bin, all 2-layer), from PCBench.

We rebuilt PCBWorld's chain from its published source, outside the repo, as untrusted code in its own directory:

| Step | What | Result |
|---|---|---|
| Engine | PCBWorld 9c125f7, engine eb7d598 (ENGINE_VERSION 1.9), KiCad 9.0.8 b09c980 plus their 24 patched files; `BUILD_CLI=1 BUILD_PCBNEW=1` | built (kaeq, 16 CPUs) |
| Data | `prepare_pcbench.sh` on PCBench dec3be75: KiCad 5 → 9 conversion, `.kicad_pro` edits, DRC filter, guide boards, sort, DSN | 1,182 converted, **679** pass the filter (the paper's count), 668 DSN (11 fail rows, none in D3-A/B/C, as their README says) |
| Splits | `configs/datasets/d3.json` easy/medium `test` | equal to `bench/suites/pcbworld-d3{a,b}-test.txt` and to the paper's Table 28 |
| Scorer | `python -m eval.pipeline --skip-rollout --stages eval,aggregate --reward-config drc_dense_promoted --selection-method final_potential --check-angle 45` (the paper's scoring flags) | `tools/research/pcbworld/score_pcbworld.py` |

Deviations from their setup: their `requirements.txt` without the GPU training stack (torch from the CPU index, 2.8.0, the pinned version; no CUDA, vllm, flash-attn, ray); `kicad-cli` run with `LD_PRELOAD` of the env's libpython (KiCad's libkicommon references Python symbols and the conda Python's `LDLIBRARY` is static, so the build did not link it); micromamba instead of conda. None of these touch scoring code.

**Checks of the chain** (before any of our runs):

| Check | Expected | Got |
|---|---|---|
| Human reference, their scorer, D3-A | paper: CP 1.00, Pot. 23.16, WL 170.2, vias 1.18 | CP 1.000, Pot. 23.163, WL 170.19, vias 1.182 |
| Same, D3-B | paper: CP 1.00, Pot. 63.96, WL 570.3, vias 6.70 | CP 1.000, Pot. 63.955, WL 570.31, vias 6.700 |
| Our KiCad 10 human runs, copper copied onto their KiCad 9 input board (`transplant_v9.py`) | equal to their own routed boards | equal on all 109 boards (WL, vias, CP), no missing nets |
| KRT 561f158 through their runner (deterministic) | paper 0.74 / 0.20 | 0.697 / 0.10 (their README warns KRT's inputs changed since the paper: Default-class rule, via sizes, escaped widths, layer names) |

Pot. needs the paper's Φ: their shipped `drc_dense_promoted` gain minus `0.002·WL + 0.1·vias` (paper eq. 2) reproduces the Reference row to 3 decimals; the config alone gives 23.62 / 65.77.

## Metric definitions side by side

| | PCBWorld (paper §4.3, App. I) | Ours (`bench/README.md` § Scoring) |
|---|---|---|
| Engine | KiCad 9.0.8 + engine patches (uncapped DRC lists) | `kicad-cli` 10.0.7 |
| Board scored | the routed `.kicad_pcb` with the board's `.kicad_pro` | rebuilt: task input + only the run's tracks, arcs, vias; task's `.kicad_pro`; zones refilled |
| Clean | routability = 1 and 0 error-level DRVs | 0 unconnected and 0 errors of any type, each board's own severities |
| Unconnected items | counted as error DRVs ("Missing connection between items") | separate (`unconnected`), not in `errors` |
| Rules | their edited `.kicad_pro` | the same file, re-saved by KiCad 10 |
| Selection, k = 5 | CP@5: the rollout of largest potential gain Φ, then its clean flag | `cpk`: any of k clean (≥ CP@5 by construction) |
| One attempt | @1: mean clean over all rollouts | `cp1`: attempt 0 |
| Deterministic methods | run once, @5 = @1 | run once (Freerouting fork) |

On every run of this experiment the two scorers gave the same clean verdict (table below), so the headline numbers do not depend on which scorer is used.

## Arms

All route-only, from the bare placement, main 3a482ed, KiCad 10.0.7 for our scorer.

- **kae bridge**: `kae.route.cli` under `restart.py` at its defaults, counted-work budgets (`KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1`, nominal 900 s × sqrt(footprints/40), stops when clean), Freerouting fork d137fd1 as the inner engine; k = 5 seeds.
- **pnr**: `tools/research/pnr` `route_only` (grid router, no Freerouting), wall budget 900 s × sqrt(fp/40), stops after its pathfinder passes; k = 5 seeds.
- **Freerouting fork d137fd1**, `-mp 10` (PCBWorld's control setting) through the kaebench adapter, `-mt 1`; once per board (deterministic).
- Not run: stock Freerouting releases (2.1.0 is cited from the paper as theirs); the staged place-and-route pipeline (PCBWorld fixes the placement).

## Results by scorer

D3-A (99 boards) / D3-B (10). Ours: `cp1` (attempt 0), `cpk` (any of k). Theirs: CP@5 (Φ-selected of 5), CP@1 (mean over rollouts); Pot., WL (mm), vias on the selected rollout; Pot. with the paper's WL/via terms.

| Arm | k | ours cp1 | ours cpk | theirs CP@5 | theirs CP@1 | Pot. | WL | vias | CPU per run |
|---|---|---|---|---|---|---|---|---|---|
| kae bridge | 5 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 | 1.000 / 1.000 | 23.34 / 64.64 | 148.2 / 510.3 | 0.96 / 3.90 | 71 s (21 s wall) |
| pnr route_only | 5 | 0.939 / 0.700 | 0.939 / 0.700 | 0.939 / 0.700 | 0.939 / 0.700 | 23.00 / 58.34 | 116.9 / 392.2 | 1.73 / 9.30 | 11 s |
| fork d137fd1 `-mp 10` | 1 | 0.929 / 0.900 | = cp1 | 0.929 / 0.900 | 0.929 / 0.900 | 22.97 / 64.32 | 147.6 / 512.1 | 1.04 / 5.20 | 14 s |
| human layout | - | 1.000 / 1.000 | - | 1.000 / 1.000 | - | 23.16 / 63.96 | 170.2 / 570.3 | 1.18 / 6.70 | - |
| paper: PPO w/o finish | 5 | | | 0.94 / 0.42 | 0.81 / 0.22 | 21.78 / 46.45 | 224.1 / 1000.5 | 2.16 / 10.20 | |
| paper: Freerouting 2.1.0 (theirs) | 4 seeds | | | 0.80 / 0.78 | 0.75 / 0.64 | 22.71 / 61.06 | 156.2 / 535.4 | 0.74 / 3.48 | |
| KRT 561f158, their runner, rerun | 1 | | | 0.697 / 0.10 | = | | 145.6 / 398.8 | 3.86 / 10.0 | |

Errors per type, attempt 0 (ours) and all rollouts (theirs):
- bridge: none (0 opens, 0 errors in 545 runs).
- pnr: open connections only: ours 7 / 27 opens at attempt 0; theirs 170 "missing connection" items over 545 rollouts. pnr's seeds gave the same verdict per board (cp1 = cpk).
- fork: 9 opens, 3 `shorting_items`, 4 `clearance` (ours) = 9 missing connection, 3 shorting, 4 clearance (theirs).

Scorer agreement (clean verdict, per run): bridge 545/545, pnr 545/545, fork 109/109, human 109/109.

Per board against published per-board results: every board Koppar or PUNKFAB (circuit-skills, Freerouting 2.2.4) routes clean, the bridge routes clean too. The fork misses 8 of Koppar's clean boards (0024, 0050, 0052, 0066, 0078, 0086, 0088, 0232); pnr misses 9.

Spot check of the bridge outputs (coordinator, 5 boards): their own copper, 0-5 exact segments shared with the human layout (straight pad-to-pad runs).

## Caveats

- **Budgets.** The bridge gets up to 900 s × sqrt(fp/40) of counted work per attempt and up to 4 parallel restarts; it stops at the first clean board. PCBWorld's methods ran 0.4-10 s (RL, Freerouting) to 230-870 s (LLM agents) per rollout. Vendors' caps: ProtoFlow 30 min, Koppar 1,200 s, DeepPCB 3-5 min of engine time.
- **KiCad version.** Our verdict uses KiCad 10.0.7 on PCBWorld's rules re-saved by KiCad 10; theirs uses their 9.0.8 engine. All 109 human layouts are clean under both. Koppar's KiCad 10 rebuild of the chain left 5 reference boards with clearance errors; ours, built with PCBWorld's own KiCad 9 chain, has none.
- **Rebuilt boards.** PCBWorld's README: a rebuild differs from the paper's files in per-net guide widths on 40 of 679 boards and in diff-pair width/gap defaults on 72 of 677. The Reference row still reproduces exactly on D3-A/B.
- **@k.** Vendors' claims are single attempts (@1) with their own scorers; the paper's headline is @5 with Φ selection. Compare like with like: our `cp1` with @1 claims, CP@5 with the paper's @5.
- **D3-B has 10 boards**: one board is 0.1 of the score.

## Rivals' published claims (all self-reported, D3-A / D3-B)

| Who (date) | Score | Protocol and scorer | Per-board data |
|---|---|---|---|
| PCBWorld paper, PPO w/o finish | 0.94 / 0.42 @5; 0.81 / 0.22 @1 | their chain | no |
| PCBWorld paper, Freerouting 2.1.0 `-mp 10` (theirs) | 0.80 / 0.78 @5; 0.75 / 0.64 @1 | their chain, 4 seeds | no |
| PCBWorld paper, KRT | 0.74 / 0.20 | their chain | no |
| ProtoFlow + LLM (2026-10-13/19) | 1.000 / 1.000 (D3-A one attempt 0.990 before a save-file fix; D3-B 30/30 attempts) | own; KiCad version not stated | no |
| ProtoFlow router alone | 0.919 / 0.900, ~0.1 / 0.7 s median | own | no |
| Koppar (2026-10-18) | 1.000 / 1.000 @1 | own: `kicad-cli` 10.0.4, zones refilled, chain rebuilt under KiCad 10 with 2 patches, `pth_inside_courtyard` ignored | yes (MIT) |
| DeepPCB (2026-09-28) | 0.929 / 0.800 @1 (D3-B as 24/30 attempts); 0.889 / 0.700 without its track-width write-back | own; version not stated; 3 min chosen after seeing the curve | no |
| PUNKFAB TraceMaker / circuit-skills (2026-10-05) | 0.99 / 1.00; best-of-backends 1.00 / 1.00 | stock KiCad 9 DRC, own harness | yes (licence not stated) |

## Sources

- PCBWorld: [paper](https://arxiv.org/abs/2607.05915), [repo](https://github.com/LGAI-Research/PCBWorld) 9c125f7 (`docs/METRICS.md`, `eval/`, `tools/datagen/pcbench_prep/`), [engine](https://github.com/LGAI-Research/PCBWorld-Engine) eb7d598.
- Rivals: [ProtoFlow](https://www.protoflow.ai/benchmarks/pcbworld-bench), [Koppar](https://github.com/Koppar-AI/autorouter-bench) (`results/pcbworld-2026-10/`), [DeepPCB](https://deeppcb.ai/benchmark/pcbworld-bench-deeppcb-results/), [PUNKFAB](https://punkfab.com/blog/tracemaker-router/) ([per-board](https://github.com/punkfab/circuit-skills)).
- Runs: kaeres experiments `pcbworld-d3`, `pcbworld-d3-fr` (`kaeres exp report`, with `KAE_CORPUS` set to the corpus `d3_corpus.py` builds).
