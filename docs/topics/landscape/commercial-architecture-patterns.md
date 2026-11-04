# What the commercial disclosures have in common, and the design they imply

Scope: the architecture shared by credible commercial layout tools, and the staged design it implies for us. Not here: per-vendor facts -> [quilter.md](quilter.md), [deeppcb.md](deeppcb.md), [commercial-incumbents-and-startups.md](commercial-incumbents-and-startups.md); our system design -> `architecture/`.
Keys: division of labour, LLM configures engines construct, no vendor lets an LLM lay copper, comprehension and setup, floorplan anchors, placement × router candidate matrix, X.Y, PRC, physics rule checks, lexicographic ranking, correct by construction, staged engines, input contract, setup failure, envelopes, Stage 0–6

## Shared division of labour
1. LLM or heuristics understand and configure; engines construct; checkers judge; humans approve. **No vendor lets an LLM lay copper** (Cooper, Fuse, JITX, the EasyEDA skill, and Astra in practice) [P/I].
2. **Setup is the main failure mode.** DeepPCB: "Autorouters don't fail at routing. Nobody configures them". Quilter's commonest mistake: no floorplan or pre-placement [V].
3. **Placement quality decides routing cost; cheap proxies cannot rank near-equal candidates** → route the top-k [P].
4. **Input contract** (shared): fixed outline, pre-placed connectors, locked critical copper, net classes and named planes, auto-detected physics constraints confirmed by a human. Quilter detects planes by layer name; DeepPCB asks users to retype layers as power; both keep pre-placed parts and pre-routed critical nets [P/I].

## Five recurring components and the evidence
| Component | Evidence |
|---|---|
| 1. Comprehension and setup, human-confirmed | Quilter heuristics plus confirmation ([quilter.md](quilter.md#circuit-comprehension-heuristics-auto-then-confirmed)); Cooper's read → summarize → propose → accept ([deeppcb.md](deeppcb.md#product)); Fuse "specialized parsers for EDA file formats"; Zuken's multimodal "intent" extraction [P/V] |
| 2. Human floorplan anchors | Quilter's four control levels; EMA asks for fixed locations, component associations, power-tree files; Zuken requires placed components before the Smart Autorouter [P/V] |
| 3. Search core → placement × router candidate matrix | RL (Quilter, DeepPCB, Flux, Cadence patents); NN-guided SMC (InstaDeep); GA with learned fitness (Cadence); MCTS reportedly (Allegro X AI [S]); topological constraint-driven routing (JITX). Candidates: Quilter X.Y with lexicographic sort and "parallel seeded runs with varied constraints … returning multiple ranked candidates"; DeepPCB "stream of diverse design solutions … with key metrics"; Allegro X AI parallel runs [P/V] |
| 4. Correct-by-construction physics + physics unit tests (PRCs) for ranking | Quilter diff-pair geometry from Simbeor, IPC-2221 widths, 8 PRCs [V] |
| 5. Staged engines | Quilter fanout, pours, plane-pour planning, IR drop, blind/buried vias (in development); Allegro X AI placement, pours, routing [V] |

| Cross-cutting | Evidence |
|---|---|
| Placement payoff | DeepPCB RPi CM board: 14-h placement routed in 4.5 h / 79 vias vs 7 h / 111 vias for a 6-min placement ([deeppcb.md](deeppcb.md#product)). Cadence: HPWL r = −0.923, routability 0.83–0.94 at equal crossings ([patents-watchlist.md](patents-watchlist.md#granted-and-pending-us-patents)) [V/P] |
| Data strategy | Synthetic only (Quilter); internal design library (Cadence, Zuken); synthetic plus corpus (DeepPCB) [V] |
| Human edits in practice | Polygons, length tuning (via delay not modelled), high-current widening, a few part moves (Speedrun); critical nets hand-routed first in all DeepPCB benchmarks [V] |
| Envelopes ("full autonomy" holds mainly for small/medium boards) | Cadence <5,100 parts, <100 pins/cm²; Quilter <5,000 pins, ≤20% density, <6 GHz, ≤48 V, ≤10 A, "can't … as well as skilled humans"; DeepPCB ≤1,200 airwires, no length matching, crosstalk, DDR or complex BGA fanout [V] |
| Manufacturing reality | Most Speedrun fab friction (48 of 58 findings) was documentation, library, BOM or process-tier communication, not routing; "a clean DRC only covers the checks that are enabled" (Astra review) [P/V] |
| Agent engineering | MCP, Agent Skills playbooks, supervisor/worker agents, recovery loops, human checkpoints, audit trails, self-verification against deterministic engines (Siemens); code as ground truth (JITX); editor API driven by Claude Code or Codex (EasyEDA) [P] |

- **Open space:** DeepPCB (no DDR, no length matching, no advanced impedance or RF) and Quilter (timing "coming soon", <6 GHz) leave high-speed constraints open; KiCad 10 already expresses them with time-domain `length`/`skew` and tuning profiles ([../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)) [I].
- **Conference picture:** talk content thin and vendor-led (PCB West 2023 AI panel; DesignCon 2025 JITX; DesignCon 2026 multi-agent SI by Intel, Simbeor and MathWorks; GTC and DAC 2026 Siemens; DAC 2026 DeepPCB booth). Quotes: "multiple possible solutions … The overall control is still with the designer" (Zuken); "Engineers will be more architects, explorers, optimizers" (Circuit Mind). All AI-vs-human comparisons are vendor case studies; most rigorous third-party-style evidence: Sierra's DFM review and PCBWorld-Bench (2-layer boards) [P].

## Staged design implied for our system
Adapted from PI §8 [I]:
1. **Stage 0, comprehension (LLM + rules).** Parse schematic and netlist; Quilter-style heuristics; LLM recall (datasheet-aware cap-to-pin mapping, USB/Ethernet/DDR recognition, current estimates). Emit KiCad net classes, custom DRC, diff pairs, rooms, proximity constraints. Plain summary; per-item accept or reject; each accepted change = one undoable transaction (Cooper pattern).
2. **Stage 1, floorplan.** Respect parts locked inside the outline; clustering, anchoring, off-board vs on-board region semantics. LLM proposes rooms and edge assignments; human approves.
3. **Stage 2, placement.** Classical optimizers with HPWL, crossings and PRC-based terms (decap pin distance, crystal and converter loop size). Generate N diverse placements; **route the top-k to rank**; spend more placement time where routing payoff is large.
4. **Stage 3, fanout and critical nets.** BGA fanout as its own stage; diff-pair and impedance geometry from a solver; power widths from IPC-2152/2221.
5. **Stage 4, bulk routing.** KiCad push-and-shove (PCBWorld-style candidate actions) and/or Freerouting. LLM chooses net order, strategies, keepouts, retries; several strategies form the X.Y matrix. Keep order search deterministic, or fully route a few proposed orders, rather than NN- or LLM-guided particle look-ahead ([patents-watchlist.md](patents-watchlist.md#risk-tiers-for-our-design)).
6. **Stage 5, pours and planes.** Plane regions covering same-net vias; refill; re-check.
7. **Stage 6, verify and rank.** Re-open the saved board; `kicad-cli` DRC under project rules, no categories silently ignored; run the PRC suite. Rank: clean pass → priority PRCs → conservative fab → layers → other PRCs → length and vias. LLM writes a review report naming every waived check.
8. **Benchmarks.** Clean pass on PCBWorld-Bench plus multilayer boards and PRC pass rates, failures included ([measured-tool-comparisons.md](measured-tool-comparisons.md#benchmark-plan-for-our-system)).
9. **Learned components later.** Prefer synthetic or curated data; review patents first.
- Also check documentation, library and BOM issues: they caused most fab friction [I].

## Open questions
- No vendor discloses placement objective weights (thermal, EMI, SI): tune empirically against PRCs and benchmark outcomes.
- Thermal and EMI handling beyond the PRCs undisclosed by every vendor.

## Sources
- research notes: [patents_and_industry.md § 7, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md); [verification_kicad_and_tools.md § 4 Inferences](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [existing_tools_and_apis.md § 3 Inferences](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- See also: [../kicad/mcp-tool-surface-spec.md](../kicad/mcp-tool-surface-spec.md)
