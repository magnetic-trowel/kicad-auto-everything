# What PCB designers want from AI, and why they distrust it

Scope: surveys of designer AI use, autorouter-configuration overhead, and vendor positions/lessons (Quilter, DeepPCB, Flux, Diode, tscircuit, Cherry Blossom). Not here: forum trust requirements -> [../workflow/trust-requirements.md](../workflow/trust-requirements.md); vendor profiles -> [../landscape/quilter.md](../landscape/quilter.md), [../landscape/deeppcb.md](../landscape/deeppcb.md), [../landscape/commercial-incumbents-and-startups.md](../landscape/commercial-incumbents-and-startups.md).
Keys: designer survey, Weidmuller 91%, 75% acceleration layer, 6% trust, house style, RL opacity, explaining vs doing, configuration overhead, ranked candidates, co-pilot, Flux AI Design Review, Diode Zener, Cherry Blossom 69.3% / 97%, skill atrophy, self-hostable

Conclusion [I]: a one-shot "autoroute everything" button is the wrong primary interface; build a real-time, auditable co-pilot that learns house style and lets experts lock what they care about.

## Surveys and sentiment

- Weidmuller USA / EETech, 2026, 400 North American engineers ([Automation World](https://www.automationworld.com/analytics/news/55393457/weidmuller-pcb-design-survey-reveals-ai-tool-impacts)) [V]: "91% have used AI-based tools in their PCB design workflow" (main value: faster iteration); 75% see AI as "a productivity and acceleration layer within existing workflows"; wishes (unranked): "real-time error detection and fully autonomous text to the PCB"; ~80% value reliability most in component selection.
- General engineers: 86% use AI, 6% trust its output without hesitation, ~90% verify ([Allwork](https://allwork.space/2026/02/86-of-u-s-engineers-use-ai-but-only-6-fully-trust-it-2026-survey-finds/)) [S].
- IPC claim of 30% faster design-to-tapeout: unverified [S].
- Concerns named [V]: trust and auditability (decades of bad autorouters); RL opacity; quality on high-speed, RF, HDI; IP; house style ("what looks right varies by company, by team, sometimes by individual reviewer"); explaining vs doing.
- Where designers draw the line: high-speed, RF, HDI/BGA and novel analog stay with humans [S/V].

## Autorouter distrust and configuration overhead

- Quilter: engineers "learned not to trust them"; Chris Gammell's "Never trust the autorouter" shirt ([Quilter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea)) [V].
- DeepPCB ([DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/)) [V]: "~90% completion with the autorouter, then… several weeks tearing up and rerouting"; fixed priority orderings fail because "the optimal priority ordering changes… from region to region"; engineers spend "nearly as much time configuring the autorouter constraints as… routing manually… debugging the autorouter's interpretation of your rules".
- Flux: "By the time you've configured everything, you might have already routed the board manually" [V].
- Explaining vs doing: faster by hand than by prompt ([trust requirement 10](../workflow/trust-requirements.md#the-11-trust-requirements-practitioners-words)) [P]; Autocuro: data preparation "takes longer than traditional manual review" [V].
- Forum evidence -> [../workflow/autorouter-distrust.md](../workflow/autorouter-distrust.md).

## Vendor positions and lessons

| Vendor | Position / lesson | Tag |
|---|---|---|
| Quilter | "Connecting pins is not the same as producing a board an engineer can trust"; ranked candidates with PRCs during generation vs one per LLM session (architecture -> [../landscape/quilter.md](../landscape/quilter.md#architecture-and-data)). Layout is "artwork"; ignoring it → "rejected on sight". Treats existing copper as "solved"; shows met vs needs-attention constraints; "AI layout should not be a black box". Sweet spot 100–1,000 parts, pin density <20%, ≤10 GHz, through-hole vias; BGA fanout, length matching, RF in development. Speedrun cleanup was "a precision pass" (items -> [../landscape/quilter.md](../landscape/quilter.md#project-speedrun-dec-2025)); 2–5 review cycles [S]. Deployment in customer's own cloud for ITAR/IP | [V] |
| DeepPCB | RL systems "can't explain their reasoning… a genuine limitation" for verification; "interpolation engines", so ask vendors about training distribution; automate routine 80%, humans on critical 20%; "Delegating layout to AI while atrophying your own layout skills is a trap." | [V] |
| Flux ([intro](https://www.flux.ai/p/blog/introducing-ai-auto-layout), [summer](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter), [winter](https://www.flux.ai/p/blog/ai-auto-layout-winter-update), [review](https://www.flux.ai/p/blog/introducing-the-ai-design-review-tab)) | RL auto-layout you can "watch… improve over multiple iterations and accept or cancel at any point"; inferred, editable net-type buckets; "relaxed clearance"; protected polygons <10% of board area; workflows full-board, hybrid (pre-route critical), early "Placement Check"; "not designed to fully autoroute every class of board", prep checklist; stops when improvement unlikely; ~375–1,250 credits per board. AI Design Reviews "always explain why an issue was flagged", ❌/⚠️/✅ statuses, click-to-navigate. Copilot "does not have full context on component positioning or PCB routing" (via StationX) | [V] |
| Diode ([partnership](https://blog.diode.computer/anthropic-partnership), [reviewer](https://blog.diode.computer/hardware-review)) | Zener Starlark DSL; datasheet → LLM draft → programmatic checks → feedback → human review: ~250 reference designs in two weeks. Module Registry with "a validated layout fragment"; SPICE as ground truth; proposals as "a clear, reviewable diff". Read-only reviewer found 22 bugs in comma.ai's challenge ($1000 prize). "it should not invent findings. If there is no evidence, there is no report"; "A bad AI reviewer is worse than no reviewer"; review = "reconstructing the intent of the engineer"; "intent lives outside the file" | [V] |
| tscircuit | "Sequential Optimal Packing": "every individual packing decision is easy to understand"; weak spots (order, local optima) mitigated by hardening constraints, which "LLM loops can easily adapt" ([blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)) | [V] |
| Cherry Blossom | "The same model scores 69.3% designing circuits on its own and produces boards that come back working 97% of the time once real part data and a verification gate are wrapped around it" (69.3% EEBench score disputed -> [../llm/pcb-llm-benchmarks.md](../llm/pcb-llm-benchmarks.md)). Four hurdles: netlist, real parts and footprints, placement and routing ("closest to solved"), manufacturability | [V] |

Vendor convergence [V]: ranked candidates, physics checks, placed copper treated as "solved", explanation of why issues were flagged.

## Design implications [I]

1. Primary interface: real-time co-pilot catching errors as the designer works, auditable step by step, suggestions beside the canvas; board-level autonomy secondary.
2. Learn house style from cleanup edits (bigger pours, straighter routes, label moves); style presets.
3. Experts lock what they care about; locked and placed copper is "solved".
4. Below the "faster than typing" threshold: inline suggestions, not chat round-trips.
5. Explain interpretations up front, to avoid "debugging the autorouter's interpretation".
6. Ranked candidates plus physics checks during generation, not one answer.
7. Self-hostable deployment for IP-sensitive users (GPL-3.0-or-later allows it).
8. "Learn while assisted" mode against skill atrophy (show rationale and the alternative).

## Open questions

- No academic interview study of PCB layout professionals on AI; no Altium, Cadence, Siemens, Zuken or IPC primary survey found.
- Vendor numbers are self-reported.
- Quilter range conflict: ≤10 GHz, pin density <20% (here, vendor positioning) vs <6 GHz, ≤48 V, ≤10 A, density >20% "best handled manually" (Quilter docs per VK, [../workflow/llm-field-reports.md](../workflow/llm-field-reports.md#commercial-tools-as-seen-by-practitioners)); the verified value belongs in [../landscape/quilter.md](../landscape/quilter.md).

## Sources

- [field_reports_and_ux.md § 1D, § 2, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)
- See also: [explanations-and-alternatives.md](explanations-and-alternatives.md), [field-reports.md](field-reports.md)
