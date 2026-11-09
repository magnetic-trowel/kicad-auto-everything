# Mixed-initiative UX: alternatives, contrastive "why", calibrated trust

Scope: HCI evidence for mixed-initiative design, alternatives, contrastive explanation of solver output and trust calibration, applied to a PCB co-pilot. Not here: intent record and rationale storage -> [design-rationale-and-intent-record.md](design-rationale-and-intent-record.md); designer demand -> [designer-demand-and-trust.md](designer-demand-and-trust.md).
Keys: mixed-initiative, Horvitz 12 principles, Amershi 18 guidelines, G11, Sketchplore, Dream Lens, parallel prototyping, contrastive explanation, plan negotiation, Krarup 89.8%, counterfactual, OptiChat, overreliance, Bansal, Vasconcelos N = 731, cognitive forcing, Buçinca, Zhang/Cagan, autonomy dial, ProCAD 4.8% → 0.9%, Gmeiner

## Mixed-initiative principles

Horvitz, CHI '99, 12 principles ([PDF](https://www.erichorvitz.com/chi99horvitz.pdf)) [P]:
1. significant value-added automation;
2. uncertainty about goals;
3. attention-aware timing;
4. expected-value action choice (automate only where expected value beats inaction);
5. dialog for key uncertainties, "considering the costs of potentially bothering a user needlessly";
6. efficient invocation and termination;
7. minimize the cost of poor guesses;
8. **scope precision to uncertainty: "doing less" but correctly**;
9. efficient refinement;
10. social appropriateness;
11. memory of recent interactions;
12. continued learning.

Example: LookOut "degrades its goal to identifying a span of time" and shows a scoped view the user can manipulate directly.

Amershi et al., CHI 2019: 18 guidelines from 150+ recommendations, tested with 49 practitioners ([PDF](https://www.microsoft.com/en-us/research/uploads/prod/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf)) [P]. Most relevant: G2 "Make clear how well the system can do what it can do"; G8/G9 efficient dismissal and correction; G10 "Scope services when in doubt"; **G11 "Make clear why the system did what it did"**; G15 granular feedback; G16 convey consequences; G17 global controls.

## Alternatives and co-creativity

| Work | Finding | Source |
|---|---|---|
| Sketchplore (DIS 2016) | Optimizers' "insistence on precise objectives and a point optimum is a poor fit with sketching"; a real-time optimizer offers local improvements and radical alternatives "without overriding the designer" | [Aalto](https://research.aalto.fi/en/publications/sketchplore-sketch-and-explore-with-a-layout-optimiser/) [P] |
| Dream Lens (Autodesk, CHI 2018) | "Engineer" vs "artist" users need both metrics and visuals; outliers "some of the most interesting"; cluster similar designs; early exploration to "guide the generation engine"; "make more like this one"; 16,800 → 1,242 designs | [PDF](https://research.autodesk.com/app/uploads/2023/03/dream-lens-exploration-and.pdf_recFfqgLe5eOFLays.pdf) [P] |
| Parallel prototyping (TOCHI 2010) | Parallel alternatives beat serial iteration; more diverse; higher self-efficacy | [PDF](https://hci.stanford.edu/publications/2010/parallel-prototyping/ParallelPrototyping2010-submitted.pdf) [S] |
| Juxtapose (UIST 2008) | Side-by-side authoring let 18 participants survey more options faster | [Stanford](https://hci.stanford.edu/research/juxtapose) [S] |
| Sentient Sketchbook / MI-CC | Human and computer both contribute proactively; suggestions target diversity; "foster human creativity" | [PDF](https://www.antoniosliapis.com/papers/mixed_initiative_co-creativity.pdf) [P] |
| Meignan et al. (TiiS 2015) | Interactive-optimization taxonomy: trial-and-error, interactive reoptimization, interactive multiobjective, interactive EA, human-guided search | [DOI](https://doi.org/10.1145/2808234) [S] |

## Contrastive and counterfactual explanation of solver output

| Work | Finding | Source |
|---|---|---|
| Krarup et al. (JAIR) | 168 user questions, ~90% contrastive (FQ1 "why not A" 17; FQ2 "why A" 75; FQ3 "A rather than B" 35). Each question → constraint added to the model; re-solve; compare plans ("plan negotiation"); covers 89.8% | [2103.15575](https://arxiv.org/pdf/2103.15575) [P] |
| RADAR-X | Contrastive explanations plus revised plans; user's preferred plan as the foil | [2011.09644](https://arxiv.org/pdf/2011.09644) [S] |
| Korikov & Beck (CP 2021) | Counterfactual = "the minimal change to the world required for a user's desired decisions", via inverse CP | [PDF](https://tidel.mie.utoronto.ca/pubs/Counterfactual_CP2021.pdf) [P] |
| OptiChat (INFORMS JDS 2025) | LLM dialogue interprets formulations, diagnoses infeasibility, analyzes sensitivity, gives counterfactuals, using function calls and code against the solver to "minimize the risk of hallucinations" | [2501.08406](https://arxiv.org/pdf/2501.08406) [P] |
| XAI-for-OR references | De Bock (EJOR 2024), Erwig & Kumar, Aigner (AAAI 2024), Goerigk & Hartisch, Forel (ICML 2023) | [2412.01264](https://arxiv.org/pdf/2412.01264) [S] |

## Trust calibration

| Work | Finding | Source |
|---|---|---|
| Bansal et al. (CHI 2021) | "Explanations increased the chance that humans will accept the AI's recommendation, regardless of its correctness". Adaptive design: explain the top-two alternatives only when confidence is low | [2006.14779](https://arxiv.org/pdf/2006.14779) [P] |
| Vasconcelos et al. (CSCW 2023, 5 studies, N = 731) | People weigh cost of verifying vs cost of relying; overreliance falls only when explanations make verification easier | [2212.06823](https://arxiv.org/pdf/2212.06823) [P] |
| Buçinca et al. (CSCW 2021, N = 199) | Cognitive forcing (on demand / update / wait) reduced overreliance but got "the least favorable subjective ratings"; larger benefit for people high in Need for Cognition | [PDF](https://kgajos.seas.harvard.edu/papers/bucinca21trust.pdf) [P] |
| Zhang, Raina, Cagan, McComb (Design Studies 2021) | AI "boosts the initial performance of low-performing teams… but always hurts the performance of high-performing teams" | [PSU](https://pure.psu.edu/en/publications/a-cautionary-tale-about-the-impact-of-ai-on-human-design-teams/) [P] |

## Generative design and CAD co-creation

| Work | Finding | Source |
|---|---|---|
| Gmeiner et al. (CHI 2023, 14 designers, Fusion 360 GD) | Couldn't tell intended features from "algorithmic glitches"; "felt unable to communicate their design goals"; hard to "specify all required parameters upfront". Wanted conversational interaction and project examples ("a skilled teammate who is not listening to you"). Successful designers tested boundaries early; good guides suggested "alternative design goals that align with the AI's capabilities" | [2303.00192](https://arxiv.org/pdf/2303.00192) [P] |
| ProCAD (ICML 2026) | Models "hallucinate dimensions when the text is ambiguous"; "targeted clarification questions only when necessary" cut invalid outputs 4.8% → 0.9% and Chamfer distance 79.9% vs frontier models | [2602.03045](https://arxiv.org/abs/2602.03045) [P] |
| Text-to-CAD agents | Visual feedback best of 4 workflows; spatial and topological requirements hardest (CADTests); CADialogue 95.71% with human-in-the-loop | [S] |
| Saadi & Yang (ASME JMD 2023) | Generative design role study, 6 designers | [S] |

## Design implications for a PCB co-pilot [I]

1. Show the interpretation before acting: inferred net classes and priorities, critical loops, keepouts, fab rules, all editable (as Flux and Quilter do).
2. Suggestions beside the canvas; direct manipulation stays primary. One-click accept/reject/tweak; lock controls; global autonomy dial (suggest-only → do region → do board).
3. 2–4 distinct alternatives (e.g. compact, connector-left, thermal-spread), each with scorecard + render, an outlier option, "more like this", clustering of near-duplicates.
4. Contrastive "why here, not there?": clicking an object or dragging a ghost compiles a constraint; re-run the deterministic solver; show the measured delta (loop area, WL, vias, DRC, congestion). The LLM narrates; it never fabricates numbers.
5. Explanations lower verification cost: each claim links to a one-click check (loop polygon, DRC marker, datasheet page). Tag measured / rule / datasheet / estimate / inference. At low confidence, show the runner-up and why.
6. Calibrated sign-off: light cognitive-forcing step at release only (reviewer marks top risks before seeing the AI verdict). No single green "looks good" for novices; show residual risks and what was not checked.
7. Diff-first review; every step revertible; cleanup edits become house-style preferences.
8. Plans as editable checklists that replay without the LLM; a decision file in which a blank row means not approved.
9. Clarify only high-impact, low-confidence fields: connector edges, mechanical keepouts, sensitive nets, fab and stackup.
10. Help novices set goals matching system capabilities (Gmeiner); guardrails against automation bias; suggest-only mode for experts.

## Open questions

- No peer-reviewed HCI study of PCB designers with an AI placement or routing co-pilot; no XAI work on PCB or IC placement decisions.
- None of these principles A/B tested on PCB tasks; candidate evaluation: EEBench-style deterministic grading extended to layout plus a small designer study.

## Sources

- [field_reports_and_ux.md § 4, § 6C](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
- See also: [agent-tooling-reliability-patterns.md](agent-tooling-reliability-patterns.md)
