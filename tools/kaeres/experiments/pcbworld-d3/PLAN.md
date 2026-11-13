<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# pcbworld-d3: where kae and the Freerouting fork sit on PCBWorld's D3-A/B (pre-registered 2026-11-11)

Ledger R8. A location, not an A/B: no default changes on this result.

## Question

PCBWorld-Bench (Song et al., arXiv 2607.05915; [topic doc](../../../../docs/topics/routing/pcbworld.md)) is the
one public routing scoreboard. Its paper reports clean pass (CP) on D3-A (99 boards, ≤ 31 pads) and D3-B
(10 boards, 31-100 pads): Freerouting 2.1.0 `-mp 10` 0.80 / 0.78 and the best method (PPO without finish)
0.94 / 0.42 at @5; 0.75 / 0.64 and 0.81 / 0.22 at @1. Vendors now claim 0.92 to 1.00 at one attempt, each
with its own KiCad DRC scorer, not PCBWorld's (ProtoFlow, Koppar, DeepPCB, PUNKFAB TraceMaker). Where do the
kae bridge, pnr and our production Freerouting fork sit on the same boards, scored by our scorer and by
PCBWorld's own?

## Boards

PCBWorld's D3 boards are not PCBench's files: PCBWorld's chain converts them to KiCad 9.0.8, edits the
`.kicad_pro` (some severities to ignore, some rule floors to 0) and narrows per-net widths (guide boards).
We build them with that chain from its published source (PCBWorld 9c125f7, engine eb7d598 = ENGINE_VERSION
1.9, KiCad 9.0.8 b09c980; PCBench dec3be75), and copy the 109 boards of `bench/suites/pcbworld-d3{a,b}-test.txt`
(= `configs/datasets/d3.json` easy.test and medium.test at 9c125f7, and the paper's Table 28) into a kaeres
corpus with `tools/research/pcbworld/d3_corpus.py`: `processed_v9_guide_v3.kicad_pcb` and its `.kicad_pro`,
ids `pcbw-d3a-*`, `pcbw-d3b-*`. Boards stay out of git (third-party licences).

Smoke: two D3-C boards (`boards-smoke.txt`), outside the measured splits and larger, so the profile shows
where time goes on more than a trivial board.

## Arms

All route-only, from the bare placement (kaebench's route task: copper stripped, zones kept), harness and kae
at main 3a482ed (Stage 2's harness), KiCad 10.0.7, `setup.sh` in this folder.

| Arm | Method | k | Budget |
|---|---|---|---|
| kae bridge | `d3 bridge 3a482ed (restarts)`: Stage 2's bridge recipe without operating facts (none exist for these boards). `KAE_BUDGET=work PYTHONHASHSEED=0 KAE_WORKERS=1`; Freerouting fork d137fd1 named in `KAE_BRIDGE_FREEROUTING` and `KAE_FREEROUTING` in the wrapper and every inner command | 5 (seeds 0-4) | counted work, nominal 900 s × sqrt(fp/40), wall ceiling 4× |
| pnr | `d3 pnr route_only 3a482ed (restarts)`: `tools/research/pnr` route_only at 3a482ed, one attempt | 5 (seeds 0-4) | wall clock 900 s × sqrt(fp/40) (pnr has no counted budget) |
| Freerouting fork | `s2 fr-fork d137fd1 mp10` (Stage 2's method b07f426d7c2f): kaebench adapter, `-mp 10` as PCBWorld's control, `-mt 1` | 1 (deterministic) | wall ceiling 3600 s × sqrt(fp/40) |
| human | the reference layout, scored by both chains | - | - |

Not run: stock Freerouting 2.5.0 (obsolete, user 2026-11-11); the staged place-and-route pipeline, because
PCBWorld's task fixes the placement (only tracks and vias may be added), so a placing method is outside its
task. k = 5 matches PCBWorld's five rollouts; the fork is deterministic, so it runs once (PCBWorld runs its
deterministic baselines once too).

Reproduction arms, PCBWorld's own runner and scorer, unchanged (`tools/research/pcbworld/README.md`):
the human reference, and KRT 561f158 once (deterministic; a rival router). Amended 2026-11-11, before any
result: stock Freerouting 2.1.0 is not run (stock releases are not measured, and Freerouting is deterministic,
so repeated runs measure nothing); its 0.80 / 0.78 is cited as PCBWorld's published row, labelled as theirs.

## Scoring, side by side

1. **Ours** (benchmark scorer, unchanged): `kicad-cli` 10.0.7 DRC of the rebuilt board with the task's
   `.kicad_pro` (PCBWorld's rules, re-saved by KiCad 10), zones refilled, each board's own severities.
   `cp1` (attempt 0 clean), `cpk` (any of k clean), `xc` (no error type above the input's), completion,
   open connections, per-type DRC errors, CPU.
2. **PCBWorld's** (their code, their KiCad 9.0.8 engine): each run's tracks, arcs and vias are copied onto
   their unrouted input board with KiCad 9's pcbnew (`transplant_v9.py`), then `python -m eval.pipeline
   --skip-rollout --stages eval,aggregate --reward-config drc_dense_promoted --selection-method
   final_potential --check-angle 45` (the paper's scoring flags). Reported: CP@5 (rollout of largest
   potential gain, then clean), CP@1 (mean over rollouts), Pot., Rout., DRV, WL, vias, and DRV per code.

## Checks before reading results

- Their chain reproduces 679 boards and the 109 eval boards exist; their scorer gives the human reference
  CP 1.00 and Pot. / WL / vias at the paper's Reference row (D3-A 23.16 / 170.2 / 1.18; D3-B 63.96 / 570.3 /
  6.70). Their own README says rebuilt guide widths differ from the paper's on 40 of 679 boards, so small
  differences are expected and listed.
- KRT through their runner near 0.74 / 0.20 (their README: KRT inputs changed since the paper).
- Transplant check: the human layout's copper transplanted onto their unrouted board scores the same as
  their own routed guide board under their scorer, and every run's transplant reports no missing nets.
- Our scorer on the human reference: count boards not clean under KiCad 10.0.7 (cp of `human`), with types.

## Reporting

Per arm and split: our cp1, cpk, xc, completion, open connections, DRC errors per type, CPU; their CP@5,
CP@1, Pot., Rout., DRV per code, WL, vias. Boards where the two scorers disagree, listed with the cause.
Located against the published numbers (paper @5/@1, vendors' @1 claims with their scorer and KiCad version).
Per-board comparisons only where a source publishes per-board results (Koppar, PUNKFAB). Write-up:
`docs/research/routing/pcbworld-d3-2611.md`.

Noise: on 99 boards a CP of 0.90 has a binomial standard error of 0.03; D3-B's 10 boards resolve 0.1 steps
only. We state no winner on differences inside that.

## Cost (information)

Under 30 CPU-h for our arms (w2's estimate; ≤ 100-pad boards). PCBWorld's chain: engine build ~1 CPU-h on 32
cores, the 1,182-board conversion a few CPU-h, KRT well under 1 CPU-h.
