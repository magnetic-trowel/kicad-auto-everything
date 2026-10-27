# Rendered images as LLM feedback

**TL;DR**
- **Structured scoring feedback beats visual feedback for routing on DRC.** OmniRouting's Score tool cut the cross-model mean DRC count by **77.1%**; visual feedback also lowered DRC for every model, with smaller, inconsistent gains. Visualization alone barely moved routability [P]. Our notes give no NRR effect for the Score tool, so neither is shown to raise routability much [I].
- Adding images to good text gives little or negative benefit in general spatial benchmarks (TopoBench, FloorplanQA, SpatialEval). VeoPlace's text-only and image-only variants differ by **under 0.8%** [P].
- **Exception:** MAGE's vision gate mattered for timing and structure (WNS **40.5%** worse without it) but not for wirelength [P].
- Vision helps when it is **specialized or fine-tuned** (SCALE's DRC-VLM: +12–25% fix rate) or used for **reading figures in documents** (DRC-Coder) [P].
- Practitioners still use renders as a sanity check ("the agent must look"). Treat images as a gestalt channel with ids shared with the text, never as the constraint carrier [I].

## Key facts

| Evidence | Result | Source |
|---|---|---|
| OmniRouting agentic tools | Visual feedback lowers total DRC for every model, but the **Score** tool cuts the cross-model mean from 141.18 to 32.31 (−77.1%). Visualization alone: GPT-5.5 NRR 21.71% → 20.96% while clearance violations fell 42.87 → 32.90. A pre-routing tool raised reference similarity by about 10 points for all 8 models. "Tools improve local legality and routing-corridor selection more than global connectivity." | [2608.04434](https://arxiv.org/abs/2608.04434) [P] |
| OmniLayout overlap repair | A **structured text list naming conflicting components and locations** (Geo. Check) gave the lowest overlap, better than inferring conflicts from images; combining all tools was not uniformly best | [2607.03261](https://arxiv.org/pdf/2607.03261) [P] |
| VeoPlace (IC macro placement) | Removing the image or the text, or shuffling images, changes results by <0.8%; random regions "sharply degrade" | [2603.28733](https://arxiv.org/pdf/2603.28733) [P] |
| MAGE (verification correction: an ablation exists) | Without visual feedback: WNS 40.5% worse, TNS 133.0% worse, human-likeness −4.2%; rWL +2.3% and power +0.4% barely change (Ariane and BP on NG45) | [2607.18536](https://arxiv.org/pdf/2607.18536) [P] |
| TopoBench | Image plus ASCII "does not reliably help and can reduce accuracy"; an ASCII render tool scored 42%, against 50% for a structured-state suite | [2603.12133](https://arxiv.org/abs/2603.12133) [P] |
| FloorplanQA | Rendered images "do not consistently outperform symbolic input" | [2507.07644](https://arxiv.org/abs/2507.07644) [P] |
| SpatialEval | VLMs often underperform their LLM backbones; text-only inputs often win | [2406.14852](https://arxiv.org/abs/2406.14852) [P] |
| Blink | GPT-4V 51.26%, Gemini 45.72%, humans 95.7% on "blink" perception | [2404.12390](https://arxiv.org/abs/2404.12390) [P] |
| OmniSch (1,854 schematics) | Unreliable fine-grained grounding, brittle layout-to-graph parsing; tool-augmented active visual search helps | [2604.00270](https://arxiv.org/abs/2604.00270) [P] |
| CoDeLayout | GPT-o3 79.68% vs a post-trained Qwen2.5-VL-7B at 91.66% on compositional layout understanding | [2608.26716](https://arxiv.org/abs/2608.26716) [P] |
| SCALE | A fine-tuned DRC-VLM raises SOTA agents' local DRV-fix solve rates by +12–25%, up to 97%, on 100 real sub-2 nm cases | [2607.21850](https://arxiv.org/abs/2607.21850) [P] |
| DRC-Coder | A VLM reads foundry rule illustrations; F1 1.000 vs 0.631 | [2412.05311](https://arxiv.org/abs/2412.05311) [P] |
| LLM4-IC8K / ICGeo8K | LMMs "severely suffer from inaccurate geometric perception" on IC drawings | [2508.03725](https://arxiv.org/abs/2508.03725) [S] |
| PCBA visual QA | Task-aware GRPO fine-tune scores 83.24 (assembly inspection, not layout) | [2609.21276](https://arxiv.org/abs/2609.21276) [P] |

### Practitioner use of renders (counter-evidence)
- **CopperLoop:** "The agent must look. Region renders per layer before claiming anything is routed" ([CopperLoop](https://github.com/PaoloJN/copperloop)) [P].
- **tscircuit** asks the agent to run `tsci build --pcb-png` and inspect the PCB image before routing ([tscircuit](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai)) [V].
- **Autocuro:** "moderate success" on placement review with heavily labelled diagrams; routing interpretation and distances failed ([Autocuro](https://autocuro.com/blog/can-llms-verify-pcb-designs)) [V].
- **Text-to-CAD study:** visual feedback was the best of four agent workflows ([Design Society](https://www.cambridge.org/core/journals/proceedings-of-the-design-society/article/from-text-to-design-a-framework-to-leverage-llm-agents-for-automated-cad-generation/5BD8D63CFCED28BDD7A01313162FFBE7)) [S].
- **JLCPCB EasyEDA:** "Claude Code did not directly see the PCB layout", so visual review stayed with the human ([JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design)) [P, anecdote].

## Recommendations for our system

1. The primary feedback channel is **structured and numeric**: per-relation verdicts, DRC lists with object ids, unrouted counts, and conflict lists naming components [I].
2. **Renders are a secondary channel** for gestalt review (signal flow, clustering, symmetry, aesthetics). Overlay refdes, net highlights and violation markers whose ids match the text.
3. Do not rely on a general VLM to spot small geometric defects. If vision is needed for defects, plan a **fine-tuned small VLM** (SCALE, CoDeLayout evidence).
4. Build the text channel first and add renders later, for structure-level critique (MAGE showed value there).
5. Use VLMs to read **datasheet figures** only as low-confidence hints (see [datasheet-extraction.md](datasheet-extraction.md)).

## Conflicts and open questions

- Research says images add little; practitioners require renders as a sanity check. These are reconcilable: images verify, text constrains.
- No PCB study isolates the value of renders when strong structured feedback already exists.

## Sources
- research notes:
  - [llm_for_eda.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
  - [verification_papers.md § 1 rows 22, 26; § 2.6, § 2.8, § 2.9; § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
  - [field_reports_and_ux.md § 1, § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)

See also: [read-representations.md](read-representations.md), [spatial-reasoning-limits.md](spatial-reasoning-limits.md), [llm-guided-placement-systems.md](llm-guided-placement-systems.md)
