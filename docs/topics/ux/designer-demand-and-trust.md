# What PCB designers want from AI, and why they distrust it

**TL;DR**
- In the one large 2026 survey, **91%** of 400 North American engineers had used AI in PCB design. **75%** want it as an **acceleration layer inside existing workflows**, and the top wish is **real-time error detection** [V].
- **Concerns:**
  - trust and auditability (decades of bad autorouters);
  - **RL opacity** ("can't explain their reasoning");
  - quality on high-speed, RF and HDI work;
  - IP;
  - **house style** ("what looks right varies by company, by team, sometimes by individual reviewer");
  - **explaining vs doing** ("faster than typing that prompt").

  [V]
- **Vendors converge:** ranked candidates, physics checks, treating placed copper as "solved", and explaining why issues were flagged [V].
- A one-shot "autoroute everything" button is the wrong primary interface. Build a real-time, auditable co-pilot that learns house style and lets experts lock what they care about [I].

## Key facts

### Surveys and sentiment
- **Weidmuller USA / EETech, 2026, 400 NA engineers:**
  - "91% have used AI-based tools in their PCB design workflow", with faster iteration as the main value;
  - 75% see AI as "a productivity and acceleration layer within existing workflows";
  - wishes: "real-time error detection and fully autonomous text to the PCB";
  - about 80% value reliability most in component selection.

  Source: [Automation World](https://www.automationworld.com/analytics/news/55393457/weidmuller-pcb-design-survey-reveals-ai-tool-impacts) [V].
- **General engineers:** 86% use AI, only 6% trust its output without hesitation, about 90% verify ([Allwork](https://allwork.space/2026/02/86-of-u-s-engineers-use-ai-but-only-6-fully-trust-it-2026-survey-finds/)) [S].
- **IPC** claim of 30% faster design-to-tapeout: unverified [S].

### Autorouter distrust and configuration overhead
- **Quilter:** engineers "learned not to trust them"; Chris Gammell's "Never trust the autorouter" shirt ([Quilter](https://www.quilter.ai/blog/pcb-autorouter-was-the-right-idea)) [V].
- **DeepPCB** ([DeepPCB](https://deeppcb.ai/the-autorouter-broke-your-trust-heres-whats-actually-different-now/)) [V]:
  - "~90% completion with the autorouter, then… several weeks tearing up and rerouting";
  - fixed priority orderings fail because "the optimal priority ordering changes… from region to region";
  - engineers spend "nearly as much time configuring the autorouter constraints as… routing manually… debugging the autorouter's interpretation of your rules".
- **Flux:** "By the time you've configured everything, you might have already routed the board manually" [V].
- **Explaining vs doing:**
  - "I would have done a better layout for these three components faster than typing that prompt" (KiCad forum) [P].
  - Autocuro: data preparation "takes longer than traditional manual review" [V].

### Vendor positions and lessons
- **Quilter** [V]:
  - **Positioning:** "Connecting pins is not the same as producing a board an engineer can trust"; placement and routing are one coupled problem; RL, solvers and computational geometry, with PRCs during candidate generation; "dozens to hundreds of ranked candidates", whereas an LLM session gives one.
  - **Aesthetics:** layout is "artwork"; output that ignores it is "rejected on sight".
  - **Control:** treats existing copper as "solved"; shows which constraints were met and which need attention; "AI layout should not be a black box".
  - **Range:** sweet spot 100–1,000 parts, pin density <20%, ≤10 GHz, through-hole vias. BGA fanout, length matching and RF are in development.
  - **Speedrun cleanup** was "a precision pass": bigger pours "for comfort", length tuning redone because the engine ignored via delay, power nets made conservative. 2–5 review cycles [S].
  - **On LLM routers:** "Router is very sequential… we can't do some sort of backtracking."
  - Offers deployment in the customer's own cloud for ITAR and IP work.
- **DeepPCB** [V]:
  - RL systems "can't explain their reasoning… a genuine limitation" for verification;
  - they are "interpolation engines", so ask vendors about their training distribution;
  - automate the routine 80% and keep humans on the critical 20%;
  - "Delegating layout to AI while atrophying your own layout skills is a trap."
- **Flux** [V] ([intro](https://www.flux.ai/p/blog/introducing-ai-auto-layout), [summer](https://www.flux.ai/p/blog/ai-auto-layout-just-got-smarter), [winter](https://www.flux.ai/p/blog/ai-auto-layout-winter-update), [review](https://www.flux.ai/p/blog/introducing-the-ai-design-review-tab)):
  - RL auto-layout you can "watch… improve over multiple iterations and accept or cancel at any point";
  - net-type buckets that are inferred and editable; "relaxed clearance"; protected polygons under 10% of board area;
  - workflows: full-board, hybrid (pre-route critical) and early "Placement Check";
  - "not designed to fully autoroute every class of board", with a prep checklist; stops when improvement is unlikely; about 375–1,250 credits per board;
  - AI Design Reviews "always explain why an issue was flagged", with ❌/⚠️/✅ statuses and click-to-navigate;
  - the copilot "does not have full context on component positioning or PCB routing" (via StationX).
- **Diode** [V] ([partnership](https://blog.diode.computer/anthropic-partnership), [reviewer](https://blog.diode.computer/hardware-review)):
  - the Zener Starlark DSL; datasheet → LLM draft → programmatic checks → feedback → human review gave about 250 reference designs in two weeks;
  - a module Registry with "a validated layout fragment"; SPICE as ground truth; proposals as "a clear, reviewable diff";
  - a read-only reviewer found 22 bugs in comma.ai's challenge ($1000 prize);
  - "it should not invent findings. If there is no evidence, there is no report"; "A bad AI reviewer is worse than no reviewer"; review means "reconstructing the intent of the engineer"; "intent lives outside the file".
- **tscircuit** [V]: "Sequential Optimal Packing", in which "every individual packing decision is easy to understand". Weak spots (order, local optima) are mitigated by hardening constraints, which "LLM loops can easily adapt" ([blog](https://blog.autorouting.com/p/sequential-optimal-packing-for-pcb)).
- **Cherry Blossom:** "The same model scores 69.3% designing circuits on its own and produces boards that come back working 97% of the time once real part data and a verification gate are wrapped around it". Four hurdles: netlist, real parts and footprints, placement and routing ("closest to solved"), manufacturability [V].
- **Where designers draw the line:** high-speed, RF, HDI/BGA and novel analog stay with humans [S/V].

## Recommendations for our system

1. **Primary interface:** a real-time co-pilot that catches errors as the designer works, is auditable step by step, and offers suggestions beside the canvas. Board-level autonomy is secondary [I].
2. **Learn house style** from the user's cleanup edits (bigger pours, straighter routes, label moves); offer style presets.
3. **Locking:** experts lock what they care about; locked and placed copper is "solved".
4. **Below the "faster than typing" threshold,** use inline suggestions, not chat round-trips.
5. **Explain interpretations up front,** to avoid "debugging the autorouter's interpretation".
6. Ranked candidates plus physics checks during generation, not one answer.
7. **Self-hostable deployment** for IP-sensitive users. Our GPL-3.0-or-later code allows it.
8. A "learn while assisted" mode to counter skill atrophy (e.g. show the rationale and the alternative).

## Conflicts and open questions

- No academic interview study of PCB layout professionals on AI exists, and no Altium, Cadence, Siemens, Zuken or IPC primary survey was found.
- Vendor numbers are self-reported.

## Sources
- research notes: [field_reports_and_ux.md § 1D, § 2, § 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)

See also: [explanations-and-alternatives.md](explanations-and-alternatives.md), [field-reports.md](field-reports.md), [../workflow/trust-requirements.md](../workflow/trust-requirements.md), [../landscape/commercial-incumbents-and-startups.md](../landscape/commercial-incumbents-and-startups.md), [../landscape/quilter.md](../landscape/quilter.md), [../landscape/deeppcb.md](../landscape/deeppcb.md), [../workflow/autorouter-distrust.md](../workflow/autorouter-distrust.md)
