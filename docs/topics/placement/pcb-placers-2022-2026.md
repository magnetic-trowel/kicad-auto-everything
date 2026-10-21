# PCB-specific placers 2022–2026 (corrected numbers)

**TL;DR**
- Four main groups: UCSD (Cheng/Holtz: SA-PCB, NS-Place, PcbRouter), CUHK/HKUST/Huawei (Bei Yu/Tsung-Yi Ho: HiePlace, PCBAgent, ModuPlace, PCB-Migrator), NTU (Y.-W. Chang: four 2025 DAC/TCAD papers), NVIDIA/Cornell (Cypress); plus WHUT, Zhao/Liu, Hubei, Fuzhou.
- **Cypress (Apache-2.0, reads KiCad) is the only open PCB-aware analytical engine**; on OmniLayout's routability metric, **Chen et al. DAC'25 (RR 0.62) is the best academic placer and Quilter (0.84) the best tool** (VP-corrected).
- Every strong placer since 2024 has a module level ("core IC + satellites" or an LLM functional module); hierarchy is ModuPlace's largest ablation effect.
- **Component sides are an input in every academic placer** — side assignment is unsolved ([sides/thermal/EMC](sides-thermal-emc-reuse.md)).
- Routability is now judged after routing with FreeRouting/PcbRouter, but versions differ, so cross-paper numbers are not comparable ([metrics](benchmarks-and-metrics.md)).

## Key facts

| Placer | Venue / group | Core method | Headline (VP-corrected) | Code |
|---|---|---|---|---|
| **NS-Place** | ASP-DAC'22 **Best Paper**; UCSD | WA wirelength + net-separation (SVM margin between pin convex hulls, alternating hyperplane/position) + APlace density; Laplacian-eigenvector seeds with enumerated orientations; GD α=1e-3, λ_NS=λ_D=1; MILP legalizer ΣHPWL + (max−min HPWL) with relative-position pruning | 14 boards (8–64 parts + one 1,570-part board, 947 locked; 1–4 layers), FreeRouting + KiCad DRC, 4 h cap. **Averages:** routed WL −10% vs manual, −6% vs GDMILP; vias −18%/−39%; DRVs+unrouted ≈ −80/−70/−75% vs manual/MILP/GDMILP ("up to 25%" is a peak). Runtime 5–10 s tiny, 1–1.7 h at 34–64 parts. Fails on PCB2 (~80% utilization) ([arXiv](https://arxiv.org/pdf/2210.14259) [P]) | No public repo |
| **Cypress** | ISPD'25 (slides: Best Paper **Nominee**); Cornell + NVIDIA | DREAMPlace-based; orientation-aware LSE WL; two-sided electrostatic density (sides pre-assigned); differentiable net crossing; Gumbel-Softmax orientation (bi-level); RUDY; RMST; per-side Tetris + Abacus legalization; MOTPE/BOHB tuning — see [analytical](../solvers/analytical-differentiable.md) | Routability up to **1.2× SA-PCB, 5.9× NS-Place, 1.6× NS-Place+**; up to **492.3× faster than SA-PCB, 329.7× than Quilter**; 1–19.7× shorter routed track; benchmarks "synthesized" from commercial designs (41–476 parts small; 5,118–6,628 big). Independent OmniLayout: RR 0.33, overlap 0.24 ([slides](https://ispd.cc/ispd2026/slides/2025/protected/3_1_slides.pdf) [P]) | **Apache-2.0** ([repo](https://github.com/NVlabs/Cypress) [P]) |
| **Chen et al.** Clearance-Constrained GP | DAC'25; NTU | Wire-area model separating **power vs signal** routing demand; pad-to-pad clearance; two-sided **pad-type-aware** density (THT vs SMD); QP legalizer | Beats two SOTA academic placers post-route; **OmniLayout RR 0.62, reference similarity 0.86** — best academic ([DOI](https://doi.org/10.1109/dac63849.2025.11133056) [S]) | No |
| **NTU CG legalization** (Ou, Chen, Chang) | DAC'25 | Constraint graph, parts sliced into rectangles, **MILP not LP**, double-sided any-orientation | [S] ([DOI](https://doi.org/10.1109/DAC63849.2025.11133304)) | No |
| **Tsou et al.** | DAC'24 LBR → TCAD'25; DAC'25 LBR | Power-flow anchors, SA pad alignment, SAT collision, window/scanline legalization | +13.5% routability, −26% runtime vs ePlace-MS; >50% routability vs Cypress [S] | No |
| **Zhao, Hu, Chai, Liu** | Integration 2025 | Rotation jointly optimized with position in GD; Hanan-grid legalization; "insensitive component" fine-tuning | 10 boards, open router [S]; follow-on **MARS-Place** (Wei et al., Integration May 2026), abstract unavailable | No |
| **PA-ICM** | arXiv 2502.14012 / ICICM'25; WHUT | Orientation by distribution EA, coordinates by conjugate subgradient; α·HPWL + β·√overlap + γ·out-of-contour (1, 20, 100); bottom side = DBSCAN clusters of IC pins **inside the IC outline**; legalization push-apart → spacing table → maximal empty rectangles → resample close-to-pin parts from N(pin, σ=2) | Beat Parquet 4.5/IARFP on ami49–n300 at 1–4 s (lost ami33); industrial 80–148 blocks in 3–33 s; **no routing evaluation** [P] | No |
| **HiePlace** | TCAD Jan 2026; CUHK + Huawei | Priority classes, slicing irregular/stacked parts, pattern grouping, DP-knapsack first ring around unrolled chip boundary, SLSQP circle relaxation, cardinal-relation MP, greedy alignment (Gurobi) — see [legalization](legalization.md) | 19 boards (15 phone boards, density ≈0.80, 13–404 parts). Cost **−66% / −18%** vs Floorplet / B*-SA+manual at **13% runtime (7.7×)**; 0.02–120 min; −16% first-priority WL, −46% misaligned vs Floorplet; Floorplet infeasible at 308–404 parts; vs Quilter cost −76.7% to −91.3%, seconds vs 34–75 min. No double-sided, rotation, thermal; proxy routability only [P] | Paper CC BY-NC-ND; no code |
| **PCBAgent** | ASP-DAC'25 | Decision-transformer RL + LLM reweighting — see [LLM-guided](llm-guided-placement.md) | Legal 17/17 industrial boards (18–414 parts); HPWL 1.04×, NSLW 0.94× manual; independent: most vias (94.4) in ModuPlace, RR 0.42 in OmniLayout [P] | No |
| **ModuPlace** | DAC'26 | LLM hierarchy + fine-tuned constraint graphs — see [LLM-guided](llm-guided-placement.md) | WL 1266.5 / vias 48.6 avg vs SA-PCB 1528.5/81.7, NS-Place 1490.2/71.5 (averages only) [P] | No |
| **Li et al.** coarse-to-fine | DAC'26 | LLM grouping agents + group-aware GP + CG/MILP legalization — see [LLM-guided](llm-guided-placement.md) | Survey-reported routed WL/via gains 55%/73% vs commercial placer, 34%/26% vs NS-Place, 15%/13% vs Quilter [S] | No |
| **DRLPlace** | ASP-DAC'26; Hubei | PPO + per-step reward prediction, pre-trained ResNet policy-value, chip-centric clustering init, boundary-aware push-and-reflection legalization | Up to 16% lower HPWL than manual [S] | No |
| **RL_PCB, Lim 2026, Crocker** | DATE'24 / preprint / MEng | Pure RL — see [ML/RL](ml-rl-placement.md) | RL_PCB avg 17%/21% better than SA (VP-corrected) | RL_PCB MIT |
| **SA-PCB** | OpenROAD/UCSD | SA, polygon overlap | Standard baseline [S] | BSD-3 |

**PCB vs IC differences stated by these papers** [P]: density up to 76%, irregular boundaries, spacing tables, surface-layer wires, rotation, order sensitivity (PCBAgent); **core chip goes in the centre** (VLSI puts macros at the boundary), pairwise spacing tables, symmetric stacked overlaps (HiePlace); arbitrary shapes and routing constraints (NS-Place); modular expert practice and two sides (ModuPlace).

**Commercial** [V]: Trace (Claude + SA, KiCad-integrated), Quilter (RL + physics checks; HiePlace wrongly calls it open source), DeepPCB placement, Cadence Allegro X AI (>10× turnaround claim). NVIDIA's ISPD'24 talk calls PCB layout "typically semi-automated or fully manual" [S].

## Recommendations for our system
- Fork Cypress or reimplement its terms in JAX/PyTorch; add Chen DAC'25 power/signal wire-area, pad-to-pad clearance and pad-type two-sided density, plus NTU power-flow anchors and pad alignment ([analytical](../solvers/analytical-differentiable.md)) [I].
- Let the LLM own hierarchy, sides, regions and priorities ([LLM-guided](llm-guided-placement.md)); legalize exactly ([legalization](legalization.md)) [I].
- Beat **Chen DAC'25 (RR 0.62) and Quilter (0.84)**, not just academic placers; LMM zero-shot RR (GPT-5.5 0.90) is a non-trivial baseline ([metrics](benchmarks-and-metrics.md)) [I].
- Reimplement HiePlace ideas from the paper (no code; CC BY-NC-ND text) with CP-SAT/HiGHS instead of Gurobi [I].

## Conflicts and open questions
- Cypress Best Paper: Cornell news says won, ISPD slides say nominee.
- Cypress benchmarks: repo has 20 Bookshelf `small-*` + 10 KiCad boards (code read); slides describe 10 small + 5 big.
- NTU TCAD'25 >50% routability over Cypress is abstract-only; full texts of NTU, DRLPlace, MARS-Place, Li DAC'26 unread.
- NS-Place code not public; HiePlace's "PCBBenchmarks" repo returned 404.

## Sources
- research notes: [placement_algorithms.md § Q1, Q3, Q4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [verification_papers.md § 1 rows 12–14, 35–37, 42, 44; § 2.12](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md); [solver_toolbox.md § 1–2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/solver_toolbox.md)

See also: [algorithm-families](algorithm-families.md) · [sides-thermal-emc-reuse](sides-thermal-emc-reuse.md) · [benchmarks-and-metrics](benchmarks-and-metrics.md) · [llm-guided-placement](llm-guided-placement.md)
