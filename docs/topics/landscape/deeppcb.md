# Commercial: DeepPCB (InstaDeep / BioNTech)

Scope: DeepPCB's router mechanism (from patents), product (Cooper, KiCad plugin, API, pricing, placement) and vendor-reported numbers. Not here: patent claims and risk -> [patents-watchlist.md](patents-watchlist.md); cross-vendor pattern -> [commercial-architecture-patterns.md](commercial-architecture-patterns.md); PCBWorld paper baselines -> [../routing/pcbworld.md](../routing/pcbworld.md#results-table-21-5).
Keys: DeepPCB, InstaDeep, BioNTech, Cooper, NN-guided Sequential Monte Carlo, SMC, AlphaZero-style router, connection order, isolation region, rays, octagon tangents, Sebulba, TPU, KiCad plugin v1.2.0, ActionPlugin, airwires, pricing, placement payoff, PCBWorld-Bench 0.929

## Mechanism (patents)
AlphaZero-style router whose look-ahead is a **neural-network-guided Sequential Monte Carlo** search over connection *orders* and candidate sub-routes; candidate points generated gridlessly from rays and octagon tangents [P]. Claims and risk → [patents-watchlist.md](patents-watchlist.md#granted-and-pending-us-patents).
- **US 11,842,136 B2** (granted 2023-12-12; priority GB 2019-11-27): define ≥2 routing orders; "SMC process to perform a look ahead search of each defined order … guided using a neural network"; posterior over orders → select, route, update. Rewards: total length, direction changes, connection density, preferred-layer share. Posterior = training target; particles resampled and cloned when weight variance crosses a threshold; entropy-weighted particles. SMC "uses less memory … than … Monte Carlo Tree Search" [P] ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11842136)).
- **US 12,019,968 B2** (2024-06-25): candidate points from linear rays where a direction change avoids "isolation region" polygons whose angles match the allowed bends (e.g. 45° octagons), at tangent intersections, "in a substantially continuous domain … rather than … a grid" [P].
- **US 12,159,094 B2** (2024-12-03): NN-guided SMC over sub-routes, stored targets [P].
- **Training:** custom C++ simulator + Sebulba actor-learner RL on Cloud TPUs (EnvPool, JAX pmap): "15x-235x acceleration"; ~24 h and ~$260 on a GPU → "6 minutes at a mere $20"; PPO for Atari validation; Ray/KubeRay on GKE via AIchor [V] ([InstaDeep, Oct 2023](https://instadeep.com/2023/10/reinforcement-learning-on-google-cloud-tpus-to-improve-deeppcb/)).
- **Data:** "synthetic boards generated programmatically, sometimes real designs from a training corpus" (contrast: Quilter synthetic-only) [V].

## Product
- **Two levels:** "The low level is the routing engine … a reinforcement learning router … On top of that sits Cooper … a natural-language assistant whose job is to get your design intent into a form the router can use … It has skills … Cooper runs on an LLM provider. It could run on a different one next month and the product wouldn't change." Configuring an autorouter takes "about two hours" [V] ([blog 2026-09-17](https://deeppcb.ai/natural-language-pcb-routing/)).
- **Cooper** (2026-06-18): "Cooper orchestrates the routing engine. It doesn't lay copper." "Autorouters don't fail at routing. Nobody configures them" [V]. Reads net classes, diff pairs, planes, clearances, widths, stackup → "a plain summary"; fixes in one approved pass; routes on command; "never touches your connectivity". Example: STM32L4 + nRF24 board had 4 setup errors (inner layers typed as power planes with no net), then routed 98/98 airwires in 2 min 6 s with 68 vias. Claimed "96% mean completion" [V].
- **KiCad plugin:**
  - Uploads board and rules (optionally the schematic) to `api.deeppcb.ai`; result lands as one undo commit; signals, diff pairs, blind/buried vias.
  - First release 2026-05-21: routing only, ≤8 layers and ≤1,200 airwires, net-class and diff-pair aware; "keep[s] your component placement exactly where you put it".
  - v1.2.0 (2026-10-13): SWIG ActionPlugin (corrected, VK), Apache-2.0, cloud-backed. Cooper docked; per-item accept or reject; **one undo entry per routed revision**; highlights and isolates nets; per-board memory; "nothing overwrites without asking". "Not modelled: length matching and skew, crosstalk, DDR, complicated BGA fanout" [P/V].
  - Code: `import pcbnew`, `APP_VERSION = "1.2.0"`, `API_URL = "https://api.deeppcb.ai/api/v1"`; 66★, 9 commits; README says KiCad 6.0+, a vendor page 10.0+ (conflict); not in the official PCM [P] ([repo](https://github.com/instadeepai/deeppcb-kicad-plugin); [Cooper in KiCad](https://deeppcb.ai/cooper-kicad-plugin/)).
- **API** (2025-05-12): "an agent that actively generates, evaluates, and iterates designs … multiple design options, each paired with key metrics", streamed with pause, refine, resume; 0.50 credit/min. Enterprise: "Custom API & MCP", public, private or on-prem cloud [V].
- **Formats:** Altium `.pcbdoc`, KiCad, EasyEDA Pro/Std, Zuken, JSON; OrCAD, Allegro, Eagle via Specctra DSN [V].
- **Scope limits:** "Not for … DDR nets, length matching, advanced impedance control, and RF-specific constraints"; engineers "keep the critical nets"; workflow "critical nets were routed by hand first and the engine finished the rest" [V].
- **Pricing (current; corrected, VK):** 1 h $30, 10 h $280, 30 h $800, plus Enterprise. Free trial: 30 min, 1 board, ≤4 layers, ≤150 airwires, ≤100 components, ≤2,200 pins. Paid: ≤8 layers, ≤1,200 airwires, ≤1,000 components, ≤2,200 pins. ET's $0.99/h and "1 free board/day" are obsolete [P] ([pricing](https://deeppcb.ai/pricing)).
- **Placement** (out of beta 2025-04-15): RL; ≤1,000 components, ≤2,200 pins. **Placement time pays back in routing** [V]:
  - 48 caps around a fixed chip: 2-min placement → 10 h routing; 30-min placement → 59 min routing, fewer vias.
  - RPi CM base board: 6-min placement → fully routed in 7 h (111 vias after 24 h); 14-h placement → fully routed in 4.5 h (79 vias after 6 h).
  - Placement from schematics is "next" for KiCad [V] ([placement post](https://deeppcb.ai/ai-powered-pcb-placement-by-deeppcb/)).

## Vendor-reported numbers
All unaudited vendor claims [V].
- **Platform** (to end of July 2026): 21,000+ engineers, 100,000+ designs, 55,000+ routing jobs. Median router time by airwire count: <100 → 2 min (p90 10); 100–299 → 7 min (p90 31); 300–599 → 9 min (p90 45); 600+ → 16 min (p90 60). Completion: mean 96.1%, median 100%; 87% of boards ≥95%. A 5,208-airwire 8-layer board took ~14 h. "2–3 days by hand → ~3 hours plus 30–60 minutes cleanup" ([routing time](https://deeppcb.ai/pcb-routing-time/)).
- **KiCad page:** "27,721 Boards, 95.6% Hit 95%+ Completion", "Median 96.9%", "11,000+ KiCad users". Disagrees with the platform's 87% ≥95%.
- **PCBWorld-Bench self-evaluation (2026-09-28; 3 min engine time; standard model, one attempt, no tuning):** clean-pass 0.929 on D3-A (92/99 boards, one attempt each) and 0.800 on D3-B (24/30 attempts: 3 per board on the 10 evaluated boards; 95% CI 0.627–0.905), vs paper @1 PPO-w/o-finish 0.81 and Freerouting 0.64 ([PCBWorld @1](../routing/pcbworld.md#results-table-21-5)); median 38–46 s to first clean board; 0.59× and 0.50× the reference vias at 0.94× and 0.95× the track length (pour-free nets only, since PCBench re-routes pours); 98/99 D3-A boards 2-layer; 3-min cut-off chosen after seeing the curve; width-rounding fix needed ([post](https://deeppcb.ai/benchmark/pcbworld-bench-deeppcb-results/)).
- **Marketing vs Freerouting:** "state-of-the-art in 2005", "60–75% on complex boards": conflicts with PCBWorld (Freerouting 2.1.0 0.80/0.78 @5) and ignores Freerouting 2.5/2.6 gains. RL explainer: actions extend/via/complete/rip-up at grid-unit granularity; admits no intent understanding, unreliable confidence, reward loopholes.
- **Product claims (Oct 2026):** "seven years of RL R&D … NeurIPS and ICML" (unverified; no routing paper found); completion falls past ~1,200 airwires; public cap 1,000 components/2,200 pins (Quilter blog).
- **Platform blog:** cloud jobs for placement, routing or both within a time budget; internal board (444 airwires, 2 layers) >50% fewer vias over a year; DRC, clearance matrices, diff pairs, plane area maximization; API ([blog](https://deeppcb.ai/bringing-ai-and-cloud-to-pcb-routing/)) [P].
- **vs Quilter** on STRF (98 airwires), PocketBeagle (290), BeagleConnect Freedom (414): completion 99/96/97% vs 94/82/87%; vias 29/135/191 vs 58/163/235; first result 1–2 min vs 15–20 min. Run by DeepPCB, unreplicated.
- **vs GPT-6 Astra** on "microduck head" (70×60 mm, 4 layers, 27 nets): 132/132 connections at 1,104 mm vs 1,282 mm. DeepPCB 64 vias = 14 layer changes + 50 drops to an inner split power plane; Astra 32, 9 of them in pads. Astra used five track widths but declared one empty net class. Resolves the "14 vs 64 vias" conflict.
- **Benchmarks page:** SAMD51 6-layer (212 connections) 99.5% in 1 h 51 m vs ~56 h estimated by hand; USB-C PD sink 4-layer (342) 100% in 40 m 30 s. **Critical nets hand-routed first** in each case; planes retyped; missing USB pairs defined.
- **Organization:** 25–30 FTE + 15–25 shared InstaDeep staff; 2,000+ designs per week; BioNTech acquired InstaDeep (completed July 2023); embedded by other EDA vendors under NDA [P] ([EEJournal](https://www.eejournal.com/article/2000-ai-routed-pcbs-a-week/)).
- **History:** launched 2019 as a "no-human-in-the-loop" cloud router for KiCad boards (Hackaday); free beta 2023. Appearances: PCB East 2025, DAC 2026 booth 1561, Altium OnTrack podcast ("said out loud which parts we can't handle yet", e.g. arcs) [P].

## Implications for our system
- Make the LLM configuration and review agent our first deliverable with Cooper's UX: read → summarize in plain language → propose → per-item accept → one undo entry per change; DeepPCB's data says setup errors cause most routing failures [I].
- Router pre-checks for the setup errors Cooper catches: inner layers typed as planes with no net, missing diff pairs, empty net classes [I].
- Use DeepPCB only as an optional external comparison baseline or optional bulk router for non-SI nets where cloud upload is acceptable, never a dependency: cloud service, board uploaded; terms/rate limits unreviewed [I].
- Avoid NN- or LLM-guided particle look-ahead over net orders with posterior selection unless counsel clears it [I].
- Own the high-speed space DeepPCB excludes (DDR, length and skew) with KiCad 10 time-domain rules ([../kicad/drc-rule-language-reference.md](../kicad/drc-rule-language-reference.md)) [I].

## Open questions
- Plugin KiCad requirement: 6.0+ (README) vs 10.0+ (vendor).
- Undisclosed: network architecture, SMC particle counts, simulator fidelity, placement algorithm (no placement patent).

## Sources
- research notes: [patents_and_industry.md § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md); [verification_kicad_and_tools.md § 1 (#32–34), § 4 DeepPCB](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md); [existing_tools_and_apis.md § 2–3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/existing_tools_and_apis.md)
- primary: [deeppcb.ai](https://deeppcb.ai/), [benchmarks](https://deeppcb.ai/benchmarks/)
