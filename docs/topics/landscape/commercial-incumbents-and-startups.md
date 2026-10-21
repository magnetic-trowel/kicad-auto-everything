# Commercial: incumbents, startups, commercial routers and the GPT-6 Astra demo

**TL;DR**
- **Incumbents disclose little.**
  - Cadence Allegro X AI (2023: placement, pours, critical-net routing; ">10X") has no primary update since 2023.
  - Zuken AIPR's later "Brains" are not shown to have shipped.
  - Siemens' Fuse agent (MCP + Agent Skills, 2026-03) only "aids layout".
  - Altium does not brand Situs or ActiveRoute as AI [P/V].
- **Flux added agent placement and a public MCP server in Aug 2026.** "Flux does no placement" is outdated (corrected, VK) [V].
- **Front-end startups** (CELUS, Circuit Mind, SnapMagic, Cadstrom, Diode) stop at schematic, BOM or verification, **not layout**. JITX makes Python code the ground truth with a topological constraint-driven router [V].
- **OpenAI's GPT-6 Astra KiCad demo actually orchestrated Freerouting.** In GUI-only mode it drew 3 trace segments in an hour [P].
- **Commercial DSN/SES routers** (Allegro PCB Router, Electra €145/month, TopoR, PCB Auto Router) can plug into a DSN socket [P].

## Key facts

### Incumbent EDA vendors
- **Cadence Allegro X AI** (announced 2023-04-06):
  - Generative AI for "small to medium PCBs" automating placement, metal pouring and critical-net routing, with SI/PI; cloud-based; ">10X" turnaround [P] ([BusinessWire](https://www.businesswire.com/news/home/20230406005098/en/Cadence-Introduces-Allegro-X-AI-Accelerating-PCB-Design-with-More-Than-10X-Reduction-in-Turnaround-Time)).
  - Distributors (2025–26) describe "Placement AI" (fixed parts, height limits, assembly rules, rooms), copper-pour AI and "Route AI … Full Board Routing Closure" in Allegro X and OrCAD X [V] ([EMA](https://www.ema-eda.com/allegro-x-ai/); [FlowCAD](https://www.flowcad.com/en/x-ai-overview.htm)).
  - EMA: "isn't trained on customer designs", RL on internal designs plus "30 years of PCB design experience". AWS, with on-prem "rolling out in 2026". Imports Altium, KiCad, Eagle and PADS. Inputs: power/ground values, mechanical locations, outline, stackup, key IC locations. Uses: a feasibility study cut from a week to 29 min (showing another layer pair was needed), and Rev-to-Rev ECO (lock the design, re-place and re-route only the changes). "50–70%" time savings claimed [V] ([EMA blog](https://www.ema-eda.com/ema-resources/blog/everything-you-need-to-know-about-allegro-x-ai/)).
  - EMA case study, low-density 4-layer board (10.886 pins/cm²): 10 min common setup + 5 min X AI setup + **2 min placement** + 8 min review = 25 min, vs 70 min manual. Issues: passives on the bottom side, over-tight rooms. Envelope <5,100 components and <100 pins/cm² [V] ([case](https://www.ema-eda.com/ema-resources/case-study/case-study-accelerating-component-placement-with-allegro-x-ai/)).
  - Other claims [S]: MCTS for placement, limited to smaller designs (per the Cypress paper); a 3 days → 75 min benchmark with 12% shorter wirelength (Quilter blog); DARPA IDEA/MAGESTIC goals "no human in the loop", "<24h".
  - Patents: [patents-watchlist.md](patents-watchlist.md).
- **Zuken CR-8000 AIPR** (PCB West, Sept 2023):
  - Smart Autorouter + **Basic Brain** trained on Zuken's CR-8000 design database ("mimics human routing, with channels organized in logical ways").
  - **Dynamic Brain** would ingest IPC-2581 to learn from the user's other designs. **Autonomous Brain** is "multi-modal … extracts the designer's intent" via text inference.
  - "The brain can be untaught if it is sent a dirty design." Tested on ~100 mostly high-speed digital designs; ~5 days to learn the tool; 30 min setup + 15 min autorouting reduced to 30 s.
  - Components must already be placed; "Smart Placement is under development". Training runs on a local "AIPR server" [P/V] ([PCD&F](https://www.pcdandf.com/pcdesign/index.php/editorial/the-digital-route-ipc-designer-s-council-news/17588-new-ai-tools-offer-look-and-questions-for-future); [Zuken](https://www.zuken.com/en/product/cr-8000/ai-pcb-design/)).
  - Basic Brain and Smart Autorouter were slated for Q1 2024. **No evidence that the later Brains shipped** (VK; zuken.com returned 403).
- **Siemens:**
  - PADS Pro Essentials and Xpedition Standard (2025-05-21): an "AI-enhanced" CELUS front end, "advanced routing automation", design reuse; **no AI placement or routing algorithm named** [P] ([press](https://news.siemens.com/es-es/siemens-pads-pro-xpedition-ai/)).
  - **Fuse EDA AI Agent** (GTC, 2026-03-16):
    - an "autonomous AI agent that plans and orchestrates multi-tool and multi-agent … PCB system workflows";
    - "Model Context Protocol (MCP) and Agent Skills" ("executable playbooks"), dynamic tool discovery;
    - supervisor and worker agents, "autonomous recovery loops", EDA file parsers, guardrails;
    - RBAC, audit trails, human checkpoints; NVIDIA Nemotron; air-gapped on-prem.
    - For PCB it only "aids layout, signal integrity and other analyses in Xpedition™ … and Hyperlynx™" [P] ([press](https://news.siemens.com/en-us/siemens-fuse-eda-ai-agent/)).
  - DAC 2026: "self-verifying" agents that "continuously validate decisions against deterministic, physics-based EDA engines", using NeMo Gym [P].
  - Blog (2026-05-18): "Not every problem requires AI … Some of the most valuable improvements come from algorithmic automation" [P].
  - Fabricator-blog claims that its AI "predicts routing paths" are not in Siemens' releases [S].
- **Altium:**
  - Situs is topological ("not dependent on obstacle shape or coordinates"). Altium's doc: "Differential pairs nets must be manually routed and locked before using the autorouter"; "If the board contains an area that can not be routed by hand, then it will not be autorouted either"; it obeys all rules except Routing Corners [P] ([docs](https://www.altium.com/documentation/altium-designer/pcb/routing/situs-topological-autorouter)).
  - Not branded AI; users export to Quilter or DeepPCB. Altium Designer 26.5.1 (2026-05-06) [S]. Uses Simbeor SFS for impedance.
- **Synopsys and Ansys:** AgentEngineer (chip-focused); SIwave PI Advisor; SimAI needs "30 to 100 simulation results". No AI PCB placement or routing [P].
- **Survey:** Weidmuller/EETech 2026 (400 engineers, Apr–May 2026): 91% have used AI tools in PCB workflows; 75% see AI as a productivity layer, not an autonomous step (second-hand via DeepPCB) [S].

### Startups and code-first tools
| Company | What it does | Facts |
|---|---|---|
| **Flux** | AI Auto-Layout (Dec 2024) via RL: "place your components and hit the Auto-Layout button"; visible iterations ("10-15 minutes or even several hours" for complex boards); built-in "Sensitive Power Trace Prioritization" and crystal "shortest path to the clock input". Spring 2026: "converges faster … fewer vias". **Aug 2026: agent placement edits ("moving a connector to one side of the board") and a public MCP server** for Claude, Cursor and Codex. Copilot Knowledge (user and project memory of approved rules) plus System Knowledge (curated by senior engineers). Earlier docs: "not designed to fully autoroute every class of board without your input" [S, not re-verifiable] | $37M total (Feb 2026; $10M seed + Series B led by 8VC) [S]; no US patents [P] ([Aug 2026](https://www.flux.ai/p/blog/summer-2026-updates-flux-mcp-server-and-chat-mode)) |
| **JITX** | "Requirements become Python. The AI edits the code. JITX generates a candidate design. HFSS … evaluates". The router is "constraint-driven … directly make a layout that meets the rules" and "topological (operates on continuous geometry …)", fitting 8 traces where a legacy tool fit 6, with pin swapping in the router; automated router setup ("a single line of code … six DDR7 memory chips"); "zero cleanup"; ODB++ | 5–20× fewer hours on 30+ layer designs (unpublished); "up to 25x"; PCIe-gen7 BGA launch optimized in 5 HFSS runs; customers Honeywell, Lockheed, OpenAI; `py-jitx` 4.2.x; jitx-skills (9); proprietary, on-prem, no KiCad export; no patents [V] ([jitx.com](https://www.jitx.com/)) |
| **CELUS** | "Our agents design it … delivered as a schematic and BOM"; component catalogs exposed "as live tools over MCP"; the Siemens PADS front end | US 12,688,343 B2; US 12,443,611 B2; no layout [P] |
| **Circuit Mind** | Requirements → parts → constraints → solver → schematic and BoM; LANL case study | US 12,050,847 B2; ~$8.41M raised [S]; no layout [P] |
| **SnapMagic Copilot** | Schematic auto-complete, bypass caps, BOM cost, alternates | No layout [P] |
| **Cadstrom** | "Sigma Engine" automated design verification | $6.8M seed (Bison) [P] |
| **Diode Computers** | AI plus engineers; Zener (Starlark) + `pcb` CLI (Rust, MIT, 463★, "needs KiCad 10.x for layouts"); no autorouting or placement automation described | YC S24; $11.4M Series A (a16z); enterprise "from $10,000 per design". With Anthropic: engineers preferred Sonnet 4.5's reference designs over Opus 4 (60 vs 40) and Sonnet 4 (82 vs 18) [P] ([Claude blog](https://claude.com/blog/making-claude-a-better-electrical-engineer)) |
| **HeyPCB** | Paid cloud placement, routing and DRC behind MCP (`build_board`) | MIT client, created 2026-10-12 [P] |
| **atopile / tscircuit / SKiDL** | Code-first capture. atopile (4.0k★, MIT) updates `.kicad_pcb` on build but layout is by hand. tscircuit (2,857★, MIT) has a manual `pcbX`/`pcbY` + MIT autorouter. SKiDL (MIT) is netlists | [P] |
| **EasyEDA / JLCEDA** | 6.58M engineers, 52M designs (2025-12-31). Standard: "Auto router is not good enough! Suggest routing manually!" (cloud router fails under load; local router is a GPL Freerouting fork). **Pro V3.2.148 (2026-06-01): "Brand new auto placement (dual engine)"** and equal-length diff-pair routing; V3.2.206 (2026-10-12) fixed a low V4 routing rate; closed algorithms. Official "EasyEDA API Skill" + local bridge: Claude Code or Codex "emits JavaScript that calls EasyEDA's extension API — … autoRouting, run ERC" | [P] ([update record](https://pro.easyeda.com/page/update-record); [JLCPCB blog](https://jlcpcb.com/blog/ai-pcb-design-easyeda)) |

### Commercial DSN/SES routers (potential user-supplied back ends)
| Router | Facts |
|---|---|
| **Allegro PCB Router** (Cadence; ex-Specctra) | Cooper & Chyan 1989; Cadence since May 1997; latest version per Wikipedia 17.4–22.1 (2022). "Shape-based" passes (preview, autoroute, post-processing) with rip-up-and-retry plus push-and-shove; Do-file strategies; returns SES or RTE [P] ([Wikipedia](https://en.wikipedia.org/w/index.php?title=Specctra&action=raw)) |
| **Konekt Electra** | "Shape-Based Autorouting … multi-pass cost-based conflict reduction"; gridless up to 256 layers, diff pairs, length matching, blind and buried vias, split planes, fanout, area rules; DSN in, RTE or SES out; lists KiCad. v10.10 (Jul 2026), v10.09 (Jan 2026), v10.0 (Nov 2025). PRO-30 €145/month, PRO-UL €2,495 perpetual (node-locked). Vendor testimonial "Best Router for KiCAD"; no user reports in a 2021 forum thread [P] ([konekt.com](https://konekt.com/products/)) |
| **TopoR** (Eremex) | Topological, "absence of preferred routing directions"; DSN/SES since 4.0. Wikipedia still lists v6.3.17875 (2017). Now the autorouter module of Russia's Delta Design; the English product page is 404 and topor.ru is for sale. Hackaday 2019: 100% routed with fewer vias than a manual route [S] [P] |
| **PCB Auto Router** (pcbautorouter.top) | Closed desktop "GPU-accelerated, reinforcement-learning (RL) routing engine"; DSN/SES; KiCad and EasyEDA plugins; free and Pro tiers; no public benchmark [V] |

### OpenAI GPT-6 Astra in KiCad (Sept 2026)
- **The launch clip** is a "15-second condensed playback" of a 2 min 54 s run; OpenAI published no PCB benchmark [P] ([Quilter analysis](https://www.quilter.ai/blog/llm-pcb-layout-gpt-6-astra); [forum](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487)).
- **NextPCB test 1:** Astra exported DSN, ran **Freerouting** and imported SES: "Freerouting performed the core routing computation. Astra orchestrated the workflow". **Test 2, GUI only:** "After one hour … only three short trace segments" [P] ([NextPCB](https://www.nextpcb.com/blog/gpt-6-astra-kicad-pcb-routing-test)).
- **JLCPCB review:** Astra "defined and protected the critical power, bootstrap, and switching connections, then ran local Freerouting". 46 parity issues were found and then cleared. The final 0 ERC / 0 DRC came **with 5 DRC and 4 ERC categories ignored**. The project was re-verified in a fresh directory [P] ([JLCPCB](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad)).
- **EEBench:** Astra 69.3% (±10%) [P via Hackaday]. Leaderboard snapshot (Sept 2026): Claude Opus 5.5 75.0%, GPT-6 Astra 69.3%; August had Opus 5 at 61.6% [S].
- **Forum consensus:** give LLMs "deterministic tools to orchestrate" [P].

## Recommendations for our system
- **Adopt MCP plus Agent Skills** so enterprise agents (Siemens Fuse, CELUS catalogs, Flux MCP) can interoperate with us [I].
- **Use incumbent envelopes as comparison points.** Cadence <5,100 parts and <100 pins/cm²; Quilter <5,000 pins; DeepPCB ≤1,200 airwires. "Full autonomy" claims hold mainly for small and medium boards [I].
- **Feasibility studies and Rev-to-Rev ECO** (re-place and re-route only the changes) are concrete workflows worth supporting [I].
- **Never count "0 DRC" as success without reporting ignored categories.** The Astra review is the cautionary case ([../kicad/drc-report-and-repair-loop.md](../kicad/drc-report-and-repair-loop.md)) [I].
- **Treat vendor facts as perishable** (DeepPCB price ~30× per hour; Flux placement plus MCP within 2026). Re-check before citing [I].

## Conflicts and open questions
- Cadence and Zuken 2026 status is unknown (their sites returned 403).
- EasyEDA Pro's "dual engine" placement algorithms are undisclosed; it would be a useful comparison target.
- "Silixon" (UK, named in an HN comment) was not identified; Zuken Cadstar was not researched.

## Sources
- research notes:
  - [patents_and_industry.md § 3, § 4, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
  - [existing_tools_and_apis.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [verification_kicad_and_tools.md § 1 (#38, #43–44), § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)

See also: [quilter.md](quilter.md), [deeppcb.md](deeppcb.md), [commercial-architecture-patterns.md](commercial-architecture-patterns.md), [patents-watchlist.md](patents-watchlist.md)
