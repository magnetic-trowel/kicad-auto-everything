# Imitation from human layouts and learned placement scores

**TL;DR**
- **Human placements carry real, learnable signal.** Designer placements route clean **0.56** of the time, against **0.12–0.16** for two automatic placers on the same netlists. Swapping interchangeable parts alone drops this to 0.31–0.39, so **assignment within groups matters** [P, third-party].
- **Imitation works only in narrow, data-efficient forms:**
  - GeniusRoute: tiny labelled sets;
  - DevFormer: **100 GA samples beat baselines trained on 2,000**, thanks to symmetry biases;
  - ChiPFormer's "expert" data is optimizer output.

  Nothing is end-to-end on PCBs [P].
- **Learned scores rarely beat simple signals on small corpora.** A learned ranker scored 0.743 vs 0.749 for plain HPWL (0.603 once perturbation size is controlled). With 64 diverse boards, a combination reached 0.79 vs ≤0.72 [P, third-party].
- **Use the router as the label oracle and a bounded real route as the acceptance gate** [I].

## Key facts

### Imitation-learning precedents

| Work | Data and method | Result | Source |
|---|---|---|---|
| **GeniusRoute** (ICCAD'19) | Imitates where clock, diff and power nets run in manual analog layouts. VAE on 64×64 images, blurred 17×17 (routing) and 5×5 (placement). 168 / 128 / 256 labelled + 6,360 unlabelled samples | "Competitive" with manual on COMP1, COMP2 and OTA. Motivating case: an expert clock route detours around the boundary, against minimum-wirelength intuition | [PDF](https://par.nsf.gov/servlets/purl/10192510) [P] |
| PARoute/AnalogFold critique (DAC'24) | — | ML routing suffers "scarcity of manual data… biased routing guidance" | [PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C223-DAC2024-PARoute.pdf) [P] |
| **ChiPFormer** (ICML'23) | "Expert" = **500 MaskPlace placements × 12 circuits**; return-weighted regression; few-shot online fine-tuning (e.g. 300 rollouts) | 32 circuits including 6 industrial; 10× runtime reduction | [2306.14744](https://arxiv.org/abs/2306.14744) [P] |
| **DevFormer** (ICML'23) | Decap placement on a 10×10 PDN, 201 frequency points from 200 MHz to 20 GHz; N = 2,000 GA solutions; teacher forcing plus symmetric augmentation | **N = 100 beats baselines at N = 2,000**; zero-shot to 15×15; 94.2% noise reduction with **26 decaps vs GA's 93.5% with 40** | [2205.13225](https://arxiv.org/abs/2205.13225) [P] |
| **Lim et al. 2026** | PCB subcircuits (main IC + 8–24 passives, 4–14 nets); human placement as ground truth | ML beats human TEWL except on U20/U26, but "TEWL does not take into account… overlapping and routing conflicts". A2C best; net-aware DQN better. DTs "require large, diverse datasets" | [2602.23540](https://arxiv.org/abs/2602.23540) [P] |
| DeepPCB (vendor) | RL on "synthetic boards… real designs", "millions of routing attempts" | Warns that simulator-legal but EDA-illegal patterns get learned and "novel" strategies may be reward loopholes. "If you haven't explicitly specified a constraint, the model won't respect it" | [blog](https://deeppcb.ai/reinforcement-learning-pcb-routing-explained/) [V] |
| Net ordering | Transformer RL learns detailed-routing net order (IJCAI'25) [S]. A hand-designed crossing-aware order on KiCad boards "leaves completion unchanged and makes vias worse" (37→38, 46→52), helping only a small board (5→3) | Human routing order is not stored in board files, so no imitation-learned net order exists | [kicad-tools doc](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/kct-route-net-order-experiment.md) [P, third-party] |
| RL_PCB (DATE'24) | TD3/SAC trained on 6 circuits | Average −17% / −21% post-route WL vs SA on unseen circuits | [UM OAR](https://www.um.edu.mt/library/oar/handle/123456789/131782) [P] |

### Which placement measures predict a clean route? [P, third-party, unreviewed]

circuit-skills score study: 64 boards, 320 placements, routed by TraceMaker, judged by KiCad DRC ([score_study.md](https://github.com/punkfab/circuit-skills/blob/main/evals/corpus/score_study.md)).

| Placement | Clean | Routed | Pre-route DRC errors |
|---|---|---|---|
| Designer | **0.56** | 0.96 | 0.0 |
| swap25 (¼ of interchangeable parts swapped) | 0.39 | 0.94 | 0.9 |
| swap100 | 0.31 | 0.90 | 3.5 |
| Their annealer | 0.12 | 0.92 | 36.9 |
| tracemaker-place | 0.16 | 0.78 | 200.3 |

**Single measures** (pairwise accuracy; 440 informative pairs):
- congestion_max 0.72; placement_drv 0.70; over_capacity_pct 0.70;
- decap_mm 0.60 (0.75 legal-only); crossings 0.60 (0.85 legal-only); MST length 0.51 (0.84 legal-only).

**Combined logistic:** 0.79 held-out over 5 board-split folds. Weights per log(1 + x): over_capacity +2.41, crossings_per_net +1.29, **decap_mm +1.24**, congestion_max +0.73, off_board_pads +0.23.

**Conflict:** kicad-tools quotes an earlier self-reported 0.89; the committed file says 0.79.

### kicad-tools calibration studies [P, third-party, unreviewed]
- **Pre-route score calibration** ([doc](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/placement_score_calibration.md)):
  - Corpus A (2 boards, 915 pairs): best single signal 0.672; fitted 0.586.
  - Corpus B (6 boards, 370 pairs): HPWL **0.749** (0.795 on completion-decided pairs, 0.698 on same-σ pairs); fitted RankNet-style logistic over 10 signals **0.743**, falling to **0.603** on same-σ pairs; RUDY at chance (0.46–0.57).
  - "The perturbation sigma alone ranks 0.739 of all pairs"; "a fitted combination never beats the best fixed signal of its own corpus, out of sample".
  - **Decision:** use "a bounded real route instead".
- **Soft-FOM weight calibration:** the committed placement is preferred over 40 jittered alternatives (σ 2.5 mm); holdout rank consistency **0.875** (diff pair 0.975, match group 0.775); beats uniform weights on 7/7 boards. Low-variance terms (crossings) transfer; high-variance terms are board-specific ([doc](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/fom_calibration.md)).
- **Perturbation corpus:** see [training-recipes.md](training-recipes.md).

## Recommendations for our system

1. **Features plus oracle:** hand-coded signals (HPWL, crossings, decap distance, congestion, over-capacity) are features; **the router is the label oracle** [I].
2. **Fit learned rankers only** with ≥ tens of boards *and* diverse styles (designer, swaps, several placers), board-grouped CV, and perturbation-size controls; otherwise they learn shake size. Use rankers as tie-breakers or β-terms, never as the acceptance gate.
3. **First learned model:** a DevFormer-style relative-pose and **assignment** model for satellites around anchors (which cap goes to which pin), trained on corpus fragments with symmetry augmentation.
4. **Metrics must include legality** (overlaps, DRC), or "learned beats human" is an artifact (Lim).
5. **A/B on the same solver,** scored by clean-route rate and HPWL vs designer on held-out boards: (a) rules-only, (b) corpus priors, (c) learned pose model, (d) LLM constraint graphs. The circuit-skills harness is a template.

## Conflicts and open questions

- Learned rankers fail (kicad-tools, 2–7 boards) or help (circuit-skills, 64 boards); corpus size and diversity appear decisive.
- Designer clean-route rates of 0.56 vs 0.63 come from different board subsets.
- No peer-reviewed PCB study of learned vs rule priors exists, and there is no imitation learning of PCB routing topology.

## Sources
- research notes: [learning_from_layout_data.md § Q3, § Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)

See also: [measured-priors.md](measured-priors.md), [training-recipes.md](training-recipes.md), [layout-retrieval-and-reuse.md](layout-retrieval-and-reuse.md), [../verification/benchmarks.md](../verification/benchmarks.md)
