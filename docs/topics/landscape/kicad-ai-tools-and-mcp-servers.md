# Landscape: KiCad AI tools, MCP servers and plugins (state 2026-10-20)

**TL;DR**
- **The ecosystem is large, young and long-tailed:** 233 GitHub repos for "kicad mcp"; 275 "KiCad AI" repos, of which only 11 have ≥50★. Most wrap file edits, `kicad-cli` and IPC CRUD. **Almost none contain placement or routing intelligence** [P].
- **"I tested seven tools that actually created a routed PCB and they all used Freerouting"** (devbisme, 2026-10-14). A no-tools Claude Code baseline produced a "DRC-clean" 4-layer board for $11.16, while routing signals through the GND plane [P].
- **The official KiCad PCM has zero AI or LLM plugins** (index 2026-10-19). 18 plugins already use the IPC runtime [P].
- **The exceptions with real engines** are KiCadRoutingTools (MIT, Rust A* plus placement optimizer, 10 skills) and rjwalters/kicad-tools (MIT, A* plus FD/GA/CMA-ES placers) [P].
- **Practitioners say placement, not routing, is the hard problem.** LLMs are "really good at the stackup and part config, but [create] some absolutely terrible routes" [P].

## Key facts

### Scale
- **GitHub searches:** "kicad mcp" returns 233 repos; "kicad llm OR claude OR gpt OR agent" returns 194 [P] ([search](https://github.com/search?q=kicad+mcp&type=repositories)).
- **RepoRecon "KiCad AI":** 275 entries, built by embedding-matching 55k KiCad repo descriptions; 11 have ≥50★ and 13 have ≥10★ [P] ([RepoRecon](https://devbisme.github.io/RepoRecon/?topic=kicad_ai&filter=&sort=stars:desc); [data](https://devbisme.github.io/RepoRecon/kicad_ai.json)).
- **PCM index** (updated 2026-10-19 11:02 UTC): 132 packages (97 plugins, 18 themes, 17 libraries).
  - A regex scan for AI/LLM/GPT/Claude/MCP/assistant/copilot/chat found nothing. DeepPCB's plugin is not listed.
  - IPC-runtime plugins include OrthoRoute, Fanout Tool, Layout Clone, Via Stitching, Via Patterns, Silk Reference Tools, a Net Class Clearance Matrix, Z0 Field Solver (writes net classes and rules from a 2D field solve) and Z0 Wavelab [P] ([packages-v1.json](https://gitlab.com/kicad/addons/repository/-/raw/main/packages-v1.json)).
  - Routing plugins: Freerouting 2.4.1 (SWIG, "needs Java JRE 25"), KiCad Routing Tools 0.22.1 (SWIG, MIT), OrthoRoute 1.0.0 (IPC, MIT), Fanout Tool 1.0.0 (IPC, MIT), and a delisted "Length Matching" plugin. Placement plugins: see [open-source-placers.md](open-source-placers.md).

### Leaders and notable projects
| Project | ★ | License | What it is |
|---|---|---|---|
| mixelpixx/KiCAD-MCP-Server | 2,881 (~2.9k) | MIT | v2.8.2, 244 tools; SWIG + experimental IPC; `suggest_placement`, `route_pad_to_pad`, Freerouting (Java/Docker/Podman); JLCPCB catalog; pushed 2026-10-01 (corrected: it does have placement and routing helpers, VK) [P] |
| aklofas/kicad-happy | 1,464 (~1.5k) | MIT | 11 skills (kicad, spice, emc with 44 checks, datasheets, bom, digikey, mouser, lcsc, element14, jlcpcb, pcbway); KiCad 5–10; Claude Code, Codex, opencode; corpus 5,800+ repos, 3,498 PCBs; v2.3.1 (README also says stable v2.1.0). Detector count is inconsistent (40 / "60+" / 21 functions) [P] |
| mixelpixx/Konnect | ~1.3k (184 issues on 2026-10-20) | **AGPL-3.0** + commercial + CLA | Rust single binary for KiCad 10 (IPC; S-expr schematic; `kicad-cli`); 228 + 7 tools (About says 217; KMS README says 171); BETA; Rust DSN exporter + Freerouting MCP; created 2026-07-05 [P] |
| i2cjak/Backplane | 673 | MIT | "Agentic hardware development with lawful, deterministic KiCad/STEP viewers"; ships a **KiCad fork** with extra LLM instrumentation (IPC schematic API); agent-agnostic [P] |
| copperheadhq/copperhead | 614 | Apache-2.0 | "Cursor for circuit boards". Edits S-expressions, runs `kicad-cli` ERC/DRC in a loop, git-snapshots every mutation and rolls back on failure. "**Not an autorouter.**" The loop has "not been observed passing end to end". Show HN 250 points, 115 comments [P] |
| drandyhaas/KiCadRoutingTools | 549 | MIT | Rust A* router + placement optimizer, 10 Claude skills, AI tab; on PCM. See [open-source-routers.md](open-source-routers.md) [P] |
| lamaalrajih/kicad-mcp | 527 | MIT | Mostly read-only (netlist, BOM, DRC via CLI, circuit-pattern recognition such as buck/boost/LDO); stale since 2025-10-17 [P] |
| salitronic/eda-agent | 262 | Apache-2.0 | Altium (DelphiScript) + KiCad IPC; schematic auto-placement only (Sugiyama/force-directed baseline, VF2 "motif composer"); "minimal" mode with only `tool_catalog` + `tool_invoke`; "Experimental" [P] |
| Seeed-Studio/kicad-mcp-server | 163 | README says MIT, **no LICENSE file** | SWIG + text fallback; experimental schematic edits ("KiCad must be closed and reopened") [P] |
| oaslananka/kicad-mcp-pro | 142 | MIT | v4.3.0, 387 tools, read-only default; SI/PI/EMC/thermal "closed-form estimates (typically ~5–10% accuracy)"; "not an automated sign-off authority" [P] |
| paul356/KiCad-AI-Assistant | 119 | MIT | KiCad ≥10 wxPython chat panel with an embedded MCP server (111 tools, 15 categories; PyPI `kcaa`); Freerouting; OpenAI, Anthropic, Ollama, Bedrock. Local Ollama failed to tool-call until the context was raised to 128k [P] |
| ProductOfAmerica/mcp-server-kicad | – | GPL-3.0-or-later (MIT ≤0.20.1) | 109 tools; byte-preserving CST; maintenance mode [P] |
| rjwalters/kicad-tools | 70 | MIT | File-based Python toolkit "for AI agents" (PyPI 0.24.0, 2026-10-20); placers + A* router; ecosystem audit of peers; "studied at the capability level only, never copied from" policy for AGPL and unlicensed neighbours [P] |

**Others:**
- **Small MCP servers:** circuitron (128★, MIT, "Agentic PCB Design Accelerator"); tangency-labs/pcbcraft (66★, GPL-3.0, "MCP-first Rust EDA"); blwfish/kicad-mcp (71 tools); Netlist-Studio/kicad-mcp (IPC, KiCad 9); Finerestaurant/kicad-mcp-python (stale); biosshot/kicad-copilot (18★); BeckhamLabsLLC/kicad-jlcpcb (wired board for EasyEDA routing); circuit-synth/kicad-sch-api (MIT); IntelligentElectron/universal-netlist (Apache-2.0); zxkmm/kicad-harness (33★).
- **Agent pipelines:** **Zane456/PCB-Agent-Teams** (76★; 9-skill multi-agent; "Noncommercial", not reusable); nevenfo/kicad-agentic-mcp (Rust, KiCad 10: "LLM-based planning … with deterministic execution, state tracking, evidence, rollback"); devbisme/boardforge; ChengminLi/AI-PCB-layout (power electronics, "human review gate after every step"); JITx-Inc/jitx-skills (9 skills).
- **Cloud services:** **HeyPCB/heypcb-mcp** (MIT client for a paid cloud `build_board` covering placement, routing and DRC server-side; bound folders are uploaded on change); the DeepPCB plugin (SWIG, cloud); Freerouting's own MCP server.
- **Adom/Hydrogen KiCad Bridge:** a Windows Rust bridge driving the user's GUI, with screenshots fed back to the AI; its "$10M from National Science Foundation" claim is unverified [V].
- **assalas/pcb-designer-ai-agent** (137★): a buzzword list; treat with suspicion [P].
- **Non-AI libraries:** InteractiveHtmlBom 4,610★; kicad-jlcpcb-tools 2,113★; KiKit 2,046★ (1.8.1, 2026-08-05); SKiDL 1,697★ (3.0.0, 2026-10-16); kicad-skip 230★ (last PyPI 2024-02-16); kiutils 130★ (last PyPI 2024-02-02) [P].

### Independent hands-on test (devbisme `ai-circuit-design-tests`)
- **Task:** each tool designs a dual-channel 10 MS/s 12-bit USB 2.0 ADC board from blank. "None of these designs or findings has been validated yet" [P] ([repo](https://github.com/devbisme/ai-circuit-design-tests)).

| Tool | Result | API-equivalent cost |
|---|---|---|
| Konnect | "Routed 4-layer board, DRC clean" | $61.12 |
| kicad-happy | 0 ERC/DRC errors | $29.37 |
| KMS | 4 DRC errors (stock USB-C footprint) | $16.93 |
| kicad-mcp-pro | 0 errors | $19.42 |
| eda-agent | 0 errors | $18.47 |
| KiCad-AI-Assistant | 0 errors | $19.38 |
| kicad-harness | 0 errors | $10.87 |
| boardforge | 0 errors | $23.89 |
| **Null baseline** (Claude Code, no KiCad tools) | "Routed 4-layer board, 0 ERC/DRC errors; signals routed through the In1 GND plane" | $11.16 |

- Forum summary: "I tested seven tools that actually created a routed PCB and they all used Freerouting. The AI might route a few nets using an A* algorithm, but that's about it" [P] ([forum](https://forum.kicad.info/t/testing-kicad-ai-tools/71769)).

### Practitioner reception (HN, KiCad forum, Hackaday)
- **Sceptics:**
  - bsder: "PCB autorouters are a pain in the ass that never work".
  - ChrisGammell: "never trust the autorouter … more likely to use co-creation tools".
  - theamk: "every single track has to abide by the rules".
  - Joel_Mckay: "NP-hard problems are still NP-hard even with magical LLM pixie sprinkles".
  - Heath_Raftery: "AI operating a 60 year old technology is mostly entertainment".
  - davidsrsb: "PCB component placement is the hard problem … A good placement has often autorouted usably well even 30 years ago".
  - paulvdh: cleanup "can take more time than routing the board manually".
  - The KiCad moderator on a built-in autorouter: "not in the foreseeable future" [P].
- **Early adopters:**
  - rutierut (Konnect HN thread): "really good at the stackup and part config, but creates some absolutely terrible routes".
  - ofrzeta: "Konnect was using freerouting".
  - __atx__: "whack-a-mole" getting Opus to use hierarchical sheets.
  - JLC/LCSC part search with stock data is seen as the most valuable feature.
  - A Hackaday commenter has had 3 vibe-coded boards come back working, with "wonky" routing [P].
- **Threads:** tscircuit's "Things I would have told myself before building an autorouter" (396 points); Copperhead Show HN (250); Konnect (147); Quilter's Speedrun ("Designed with AI, not by AI") [P].
- **Gap:** Reddit and EEVblog were blocked, so they are not represented.

## Recommendations for our system
- **Don't compete on tool count** (200–480 tools already exist). Compete on own placement intelligence, routing quality beyond Freerouting defaults, and layout-quality checks beyond DRC [I].
- **Ship as an IPC-runtime PCM plugin plus MCP server.** That niche is empty in the official catalog [I].
- **Keep a human in the loop:** proposals, diffs and renders, per-net accept, undoable commits. Be transparent about quality (DRC plus scores), because marketing claims draw backlash [I].
- **Benchmark head-to-head** on the devbisme dual-ADC task and public benchmarks ([measured-tool-comparisons.md](measured-tool-comparisons.md)) [I].

## Conflicts and open questions
- The devbisme table does not say which router each tool used (beyond the forum summary), and results are unvalidated.
- Konnect's tool count (228/217/171) and kicad-happy's detector counts are internally inconsistent.
- Star counts are rounded page values for some repos.

## Sources
- research notes:
  - [existing_tools_and_apis.md § 2, § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
  - [verification_kicad_and_tools.md § 1 (#29–32, #41–42), § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
  - [kicad_mcp_codebases.md § 1](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/kicad_mcp_codebases.md)
- primary: [HN Konnect thread](https://news.ycombinator.com/item?id=50085553), [HN copperhead](https://news.ycombinator.com/item?id=49610059), [HN tscircuit autorouter](https://news.ycombinator.com/item?id=43499992), [KiCad forum Astra thread](https://forum.kicad.info/t/open-ai-claims-gpt-6-astra-can-make-pcb-boards/71487)

See also: [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md), [open-source-routers.md](open-source-routers.md), [commercial-incumbents-and-startups.md](commercial-incumbents-and-startups.md)
