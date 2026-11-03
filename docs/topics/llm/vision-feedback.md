# Rendered images as LLM feedback

Scope: value of renders/images vs structured text as LLM feedback. Not here: text encodings -> [read-representations](read-representations.md); geometric limits -> [spatial-reasoning-limits](spatial-reasoning-limits.md).
Keys: vision feedback, renders, VLM, image vs text, Score tool, Geo. Check, structured conflict list, MAGE vision ablation, VeoPlace image ablation, SCALE DRC-VLM, CoDeLayout, Blink, OmniSch, gestalt review, CopperLoop, tsci build --pcb-png

## Rule

- Primary feedback channel is structured and numeric: per-relation verdicts, DRC lists with object ids, unrouted counts, conflict lists naming components [I].
- Renders are a secondary gestalt channel (signal flow, clustering, symmetry, aesthetics), with refdes, net highlights and violation markers whose ids match the text. Images verify, text constrains [I].
- Build the text channel first; add renders later for structure-level critique (MAGE showed value there) [I].
- Do not rely on a general VLM to spot small geometric defects; if vision is needed for defects, plan a fine-tuned small VLM (SCALE, CoDeLayout) [I].
- VLM reading of datasheet figures gives low-confidence hints only -> [datasheet-extraction](datasheet-extraction.md#footprint-and-figure-geometry) [I].

## Evidence

| Evidence | Result | Source |
|---|---|---|
| OmniRouting agentic tools | Visual feedback lowers total DRC for every model, but the **Score** tool cuts the cross-model mean 141.18 -> 32.31 (−77.1%). Visualization alone: GPT-5.5 NRR 21.71% -> 20.96% while clearance violations fell 42.87 -> 32.90. Pre-routing tool raised reference similarity ≈10 points for all 8 models. "Tools improve local legality and routing-corridor selection more than global connectivity." Our notes give no NRR effect for Score, so neither is shown to raise routability much [I] | [2608.04434](https://arxiv.org/abs/2608.04434) [P] |
| OmniLayout overlap repair | **Structured text list naming conflicting components and locations** (Geo. Check) gave the lowest overlap, better than inferring conflicts from images; combining all tools not uniformly best | [2607.03261](https://arxiv.org/pdf/2607.03261) [P] |
| VeoPlace (IC macro placement) | Removing image or text, or shuffling images: < 0.8% change; random regions "sharply degrade" | [2603.28733](https://arxiv.org/pdf/2603.28733) [P] |
| MAGE (verification correction: an ablation exists) | Without visual feedback: WNS 40.5% worse, TNS 133.0% worse, human-likeness −4.2%; rWL +2.3%, power +0.4% (Ariane and BP on NG45): vision matters for timing/structure, not wirelength | [2607.18536](https://arxiv.org/pdf/2607.18536) [P] |
| TopoBench | Image + ASCII "does not reliably help and can reduce accuracy"; ASCII render tool 42% vs 50% structured-state suite | [2603.12133](https://arxiv.org/abs/2603.12133) [P] |
| FloorplanQA | Rendered images "do not consistently outperform symbolic input" | [2507.07644](https://arxiv.org/abs/2507.07644) [P] |
| SpatialEval | VLMs often underperform their LLM backbones; text-only often wins | [2406.14852](https://arxiv.org/abs/2406.14852) [P] |
| Blink | GPT-4V 51.26%, Gemini 45.72%, humans 95.7% on "blink" perception | [2404.12390](https://arxiv.org/abs/2404.12390) [P] |
| OmniSch (1,854 schematics) | Unreliable fine-grained grounding, brittle layout-to-graph parsing; tool-augmented active visual search helps | [2604.00270](https://arxiv.org/abs/2604.00270) [P] |
| CoDeLayout | GPT-o3 79.68% vs post-trained Qwen2.5-VL-7B 91.66% on compositional layout understanding | [2608.26716](https://arxiv.org/abs/2608.26716) [P] |
| SCALE | Fine-tuned DRC-VLM: +12–25% local DRV-fix rate -> [agent-loop-patterns](agent-loop-patterns.md#bounded-action-space-deterministic-realization-independent-check) | [2607.21850](https://arxiv.org/abs/2607.21850) [P] |
| DRC-Coder | VLM reads foundry rule illustrations; F1 1.000 vs 0.631 | [2412.05311](https://arxiv.org/abs/2412.05311) [P] |
| LLM4-IC8K / ICGeo8K | LMMs "severely suffer from inaccurate geometric perception" on IC drawings | [2508.03725](https://arxiv.org/abs/2508.03725) [S] |
| PCBA visual QA | Task-aware GRPO fine-tune scores 83.24 (assembly inspection, not layout) | [2609.21276](https://arxiv.org/abs/2609.21276) [P] |

## Practitioner use of renders

Counter-evidence: practitioners require renders as a sanity check.
- CopperLoop: "The agent must look. Region renders per layer before claiming anything is routed" ([CopperLoop](https://github.com/PaoloJN/copperloop)) [P].
- tscircuit: agent runs `tsci build --pcb-png` and inspects the PCB image before routing ([tscircuit](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai)) [V].
- Autocuro: "moderate success" on placement review with heavily labelled diagrams; routing interpretation and distances failed ([Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs)) [V].
- Text-to-CAD study: visual feedback was best of four agent workflows ([Design Society](https://www.cambridge.org/core/journals/proceedings-of-the-design-society/article/from-text-to-design-a-framework-to-leverage-llm-agents-for-automated-cad-generation/5BD8D63CFCED28BDD7A01313162FFBE7)) [S].
- JLCPCB EasyEDA: "Claude Code did not directly see the PCB layout", so visual review stayed with the human ([JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design)) [P, anecdote].

## Open questions

- No PCB study isolates the value of renders when strong structured feedback already exists.

## Sources
- [llm_for_eda.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- [verification_papers.md § 1 rows 22, 26; § 2.6, § 2.8, § 2.9; § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- [field_reports_and_ux.md § 1, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
