# What the commercial disclosures have in common, and the design they imply

**TL;DR**
- **Every credible system splits the work the same way:** the LLM (or heuristics) understands and configures, engines construct, checkers judge, humans approve. **No vendor lets an LLM lay copper** (Cooper, Fuse, JITX, the EasyEDA skill, and Astra in practice) [P/I].
- **Five recurring components:**
  1. comprehension and setup, human-confirmed;
  2. human floorplan anchors;
  3. a search core producing a **placement × router candidate matrix**;
  4. correct-by-construction physics plus physics unit tests (PRCs) for ranking;
  5. staged engines (fanout, pours, planes, tuning) [P].
- **Setup is the main failure mode.** DeepPCB: "Autorouters don't fail at routing. Nobody configures them". Quilter's commonest mistake is a missing floorplan or pre-placement [V].
- **Shared input contract:** fixed outline, pre-placed connectors, locked critical copper, net classes and named planes, auto-detected physics constraints confirmed by a human [P/I].
- **Placement quality decides routing cost, and cheap proxies cannot rank near-equal candidates.** Route the top-k [P].

## Key facts
| Component | Evidence |
|---|---|
| Comprehension and setup | Quilter heuristics plus confirmation ([quilter.md](quilter.md)); Cooper's read → summarize → propose → accept ([deeppcb.md](deeppcb.md)); Fuse "specialized parsers for EDA file formats"; Zuken's multimodal "intent" extraction [P/V] |
| Floorplan anchors | Quilter's four control levels; EMA asks for fixed locations, component associations and power-tree files; Zuken requires components placed before the Smart Autorouter [P/V] |
| Search cores | RL (Quilter, DeepPCB, Flux, Cadence patents); NN-guided SMC (InstaDeep); GA with learned fitness (Cadence); MCTS reportedly (Allegro X AI [S]); topological constraint-driven routing (JITX) [P/V] |
| Candidate matrix and ranking | Quilter X.Y candidates with lexicographic sort; DeepPCB's "stream of diverse design solutions … with key metrics"; Allegro X AI parallel runs; Quilter "parallel seeded runs with varied constraints … returning multiple ranked candidates" [V] |
| Correct by construction | Quilter diff-pair geometry from Simbeor, IPC-2221 widths [V] |
| Staged engines | Quilter fanout, pours, plane-pour planning, IR drop, blind/buried vias (in development); Allegro X AI placement, pours, routing [V] |
| Placement payoff | DeepPCB: a 14-h placement routed in 4.5 h with 79 vias, versus 7 h and 111 vias for a 6-min placement. Cadence: HPWL r = −0.923, but routability spans 0.83–0.94 at equal crossings [V/P] |
| Data strategy | Synthetic only (Quilter); internal design library (Cadence, Zuken); synthetic plus corpus (DeepPCB) [V] |
| Human edits in practice | Polygons, length tuning (via delay not modelled), high-current widening, a few part moves (Speedrun); critical nets hand-routed first in all DeepPCB benchmarks [V] |
| Honest limits | Quilter <5,000 pins, ≤20% density, <6 GHz, ≤48 V, ≤10 A, "can't … as well as skilled humans"; DeepPCB does not model length matching, crosstalk, DDR or complex BGA fanout [V] |
| Manufacturing reality | Most Speedrun fab friction (48 of 58 findings) was documentation, library, BOM or process-tier communication, not routing; "a clean DRC only covers the checks that are enabled" (Astra review) [P/V] |
| Agent engineering | MCP, Agent Skills playbooks, supervisor/worker agents, recovery loops, human checkpoints, audit trails, self-verification against deterministic engines (Siemens); code as ground truth (JITX); editor API driven by Claude Code or Codex (EasyEDA) [P] |

- **Commercial input contract:** Quilter detects planes by layer name; DeepPCB asks users to retype layers as power; both keep pre-placed parts and pre-routed critical nets [P].
- **Open space:** DeepPCB's scope limits (no DDR, no length matching, no advanced impedance or RF) and Quilter's (timing "coming soon", <6 GHz) leave the high-speed constraint space open. KiCad 10 already expresses it with time-domain `length`/`skew` and tuning profiles [I] ([../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)).
- **Conference picture:** public talk content is thin and vendor-led (PCB West 2023 AI panel; DesignCon 2025 JITX; DesignCon 2026 multi-agent SI by Intel, Simbeor and MathWorks; GTC and DAC 2026 Siemens; DAC 2026 DeepPCB booth). PCB West quotes: "multiple possible solutions … The overall control is still with the designer" (Zuken); "Engineers will be more architects, explorers, optimizers" (Circuit Mind). All AI-versus-human comparisons are vendor case studies; the most rigorous third-party-style evidence is Sierra's DFM review and PCBWorld-Bench (2-layer boards) [P].

## Recommendations for our system
A staged design for the open project, adapted from PI §8 [I]:
1. **Stage 0, comprehension (LLM + rules).** Parse schematic and netlist; run Quilter-style heuristics; add LLM recall (datasheet-aware cap-to-pin mapping, USB/Ethernet/DDR recognition, current estimates). Emit KiCad net classes, custom DRC, diff pairs, rooms and proximity constraints. Show a plain summary; per-item accept or reject; each accepted change is one undoable transaction (Cooper pattern).
2. **Stage 1, floorplan.** Respect parts locked inside the outline. Use clustering, anchoring, and off-board versus on-board region semantics. The LLM proposes rooms and edge assignments; the human approves.
3. **Stage 2, placement.** Classical optimizers with HPWL, crossings and PRC-based terms (decap pin distance, crystal and converter loop size). Generate N diverse placements; **route the top-k to rank**. Spend more placement time where routing payoff is large.
4. **Stage 3, fanout and critical nets.** BGA fanout as its own stage. Diff-pair and impedance geometry from a solver; power widths from IPC-2152/2221.
5. **Stage 4, bulk routing.** KiCad push-and-shove (PCBWorld-style candidate actions) and/or Freerouting. The LLM chooses net order, strategies, keepouts and retries; several strategies form the X.Y matrix. Keep order search deterministic, or fully route a few proposed orders, rather than NN- or LLM-guided particle look-ahead ([patents-watchlist.md](patents-watchlist.md)).
6. **Stage 5, pours and planes.** Plane regions covering same-net vias; refill; re-check.
7. **Stage 6, verify and rank.** Re-open the saved board; run `kicad-cli` DRC under project rules with no categories silently ignored; run the PRC suite. Rank: clean pass → priority PRCs → conservative fab → layers → other PRCs → length and vias. The LLM writes a review report naming every waived check.
8. **Benchmarks.** Publish clean pass on PCBWorld-Bench plus multilayer boards and PRC pass rates, including failures ([measured-tool-comparisons.md](measured-tool-comparisons.md)).
9. **Learned components later.** Prefer synthetic or curated data; review the patents first.

Also: check documentation, library and BOM issues, since these caused most fab friction [I].

## Conflicts and open questions
- No vendor discloses placement objective weights (thermal, EMI, SI). We must tune them empirically against PRCs and benchmark outcomes.
- Thermal and EMI handling beyond the PRCs is undisclosed by every vendor.

## Sources
- research notes:
  - [patents_and_industry.md § 7, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
  - [verification_kicad_and_tools.md § 4 Inferences](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [existing_tools_and_apis.md § 3 Inferences](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)

See also: [quilter.md](quilter.md), [deeppcb.md](deeppcb.md), [commercial-incumbents-and-startups.md](commercial-incumbents-and-startups.md), [../kicad/mcp-tool-surface-spec.md](../kicad/mcp-tool-surface-spec.md)
