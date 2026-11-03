# Generative (diffusion / flow / energy-based) placement and its PCB transplant

Scope: diffusion, flow and energy-based placement and how to transplant it to PCBs. Not here: RL placers -> [ML/RL placement](ml-rl-placement.md).
Keys: diffusion placement, chip diffusion, ICML'25, synthetic netlists, inverted data generation, guidance, legality 0.997, Diffusion-CCSP, energy composition, flow matching, research track

## Methods and results

**Chip Placement with Diffusion Models** (Lee, Nguyen, Elzeiny, Deng, Abbeel, Wawrzynek; ICML'25; [arXiv 2407.12282](https://arxiv.org/abs/2407.12282) [P], VP-verified; [code](https://github.com/vint-1/chipdiffusion))
- Synthetic data, **inverted generation** (legal placement first, then a netlist for which it is near-optimal): sample sizes uniformly, place randomly but legally (retry on overlap); pins per object from a power law (Rent's rule); edge between pins on different objects with p ∝ exp(−l/s) (l = L1 distance, s = scale). **100k circuits of ~200 objects per day on 32 CPUs**, no commercial tools; the scale s strongly affects zero-shot transfer.
- Model: interleaved GNN message passing + attention (fixes oversmoothing, links netlist-far/canvas-near objects); 2-D sinusoidal position encodings; 233k / 1.23M / 6.29M parameters.
- Guidance: backward universal guidance on x̂₀ with φ = w_legality·Σ min(0, d_ij)² + w_hpwl·φ_hpwl (HPWL as a parameter-free PyG layer); **interleaved gradient steps on x and dual ascent on w_legality** (Lagrangian).
- Results: legality 0.88 → **0.997**; HPWL −7.1% (2.976 vs 3.203); **20% below DREAMPlace on clustered IBM**, 4% better on ISPD mixed-size.
- Related: DiffPlace (2025), MacroDiff+ (IJCAI'26) [S].

**Graphic / floorplan generative models** [S]: LayoutDM (discrete diffusion; constraints by masking/logit adjustment at inference), LayoutFlow (flow matching, faster), House-GAN (graph-constrained GAN), HouseDiffusion (graph-masked attention, vector floorplans), HouseTune (LLM CoT draft → diffusion refine; "LLM alone lacks precise geometry"), RLVR floorplanning (≥94% relative compatibility-error cut).

**Compositional / robotics** 
- **Diffusion-CCSP** (CoRL'23, [arXiv 2309.00966](https://arxiv.org/abs/2309.00966) [P]): continuous CSP as a factor graph; one diffusion model per constraint type read as an energy; **sum energies** at sampling; generalizes to novel combinations and more constraints than trained.
- **StructDiffusion** (RSS'23): language-conditioned object diffusion + **collision discriminator**; ~16% higher success [S].

**Protein structure**
- **AlphaFold2 recycling** (Nature 2021, [P]): whole-network iterative refinement "contributes markedly to accuracy with minor extra training time"; 4 recycles × 48 blocks = 192-step inspectable trajectory.
- RFdiffusion motif scaffolding = conditional inpainting around fixed motifs; unified via Doob's h-transform [S].

## Use in kae (research track)
A netlist-conditioned diffusion placer is plausible for PCBs (chip diffusion trains at ~200 objects, PCB scale); long-horizon track, not v1 [I].
- Port the synthetic-data generator to PCBs [I]: real KiCad footprints (courtyards, pad positions) placed legally at random; nets between pads with p ∝ exp(−l/s) plus PCB structure (one power net touching many parts, very short decap pairs, connector-to-IC buses); condition on footprint geometry, side and 4-way rotation (discrete).
- Guidance = our constraint DSL as potentials (courtyard overlap, outline, keep-outs, decap distance, HPWL) with dual ascent on legality ([LLM-guided](llm-guided-placement.md)) [I].
- Train small per-constraint-type energies (decap-near-pin, connector-on-edge, thermal spacing, diff-pair symmetry, keep-out) and compose them from the LLM's constraint graph [I].
- Pair the generator with an exact collision checker (jagua-rs) as reject/rerank stage; add AlphaFold-style recycling with congestion/crossing/DRC-hotspot features; inpaint around mechanically fixed parts for diverse samples feeding QD portfolios ([QD](../solvers/metaheuristics-and-qd.md)) [I].
- PCBWorld's synthetic-trained RL router transfers zero-shot to real boards, supporting the synthetic route → [PCBWorld](../routing/pcbworld.md#results-table-21-5) [S].

## Open questions
- Synthetic netlists lack PCB semantics (EMI, thermal, current loops); those must come from guidance potentials and LLM labels.
- No PCB diffusion placer exists; transfer of the recipe to irregular courtyards and multi-pin footprints is untested.
- Chip-diffusion numbers originally came from a snippet; VP re-verified them from v3.

## Sources
- [cross_domain_ideas.md § Q1, Q2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/cross_domain_ideas.md); [placement_algorithms.md § Q3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/placement_algorithms.md); [verification_papers.md § 1 row 38, § 2.11](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
