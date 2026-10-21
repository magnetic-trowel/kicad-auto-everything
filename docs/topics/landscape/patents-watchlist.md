# Patents watch-list for LLM-driven PCB placement and routing (identification only, not legal advice)

**TL;DR**
- **High-relevance granted US patents:**
  - **Cadence US 11,599,699** (an RL agent over board images plus scalars choosing place, via or route actions) and **US 12,223,248** (GA placements autorouted to train a CNN + GCN + DNN routability predictor).
  - **InstaDeep US 11,842,136 / 12,019,968 / 12,159,094** (NN-guided Sequential Monte Carlo look-ahead over net orders and sub-routes) [P].
- **Top watch item:** pending **NVIDIA US 2025/0315590 A1**. Its claim 1 recites an LLM in a ReAct loop updating constraints for a "circuit layout tool", which is essentially our architecture. Collect prior art from before 2024-04-03 [P/I].
- **No granted US patent on LLM-driven PCB layout, or on ML or LLM constraint extraction from schematics, was found.** Quilter, Flux, JITX and Altium have none; Siemens' and Zuken's patents are non-ML [P].
- **Lower risk by design:** LLM orchestration of classical engines; deterministic net ordering, or full routing of a few proposed orders; analytic or field-solver physics; rule-based comprehension with human confirmation [I].
- **Our code license** (GPL-3.0-or-later; patent grant §11) covers contributors' patents only, never third parties' [P].

## Key facts
Search scope: USPTO PPUBS full text (US grants and published applications), queried 2026-10-20. **No CN/EP/WO/JP search.** Google Patents blocked automated queries [P].

| Patent | Owner / dates | Mechanism in the independent claims | Relevance |
|---|---|---|---|
| **US 11,599,699 B1** ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11599699)) | Cadence; filed 2020-02-10; granted 2023-03-07; 469 days PTA; DARPA HR0011-18-3-0010; inventors Roberto, Mitra, Hogan, Li, Zumbo, Murphy | An **RL agent** analyses the design on "a feature vector including both images and scalars" and recommends a place, via or route agent action, then repeats. Scalars (claims 8/15): "PCB dimensions, wirelength, number of nets, number of packages, and discrete components". Dependent claims: hierarchical RL; image + scalar + graph; primitive or complex actions; an NN routability reward | **High** for any RL-trained agent choosing place/via/route actions from images plus scalars |
| **US 12,223,248 B1** ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12223248)) | Cadence; filed 2020-08-10; granted 2025-02-11; DARPA | **GA placements**, with a reward adjusted during generation, **autorouted to label routability**; a CNN (images) + GCN (graph) + DNN (scalars) + fusion DNN predicts the routed percentage; a dependent claim adds a crossings reward. Data: 12,000 placements of a 350-part board; HPWL r = −0.923, crossings r = −0.898 | **High** if we train a multimodal routability predictor on autorouted GA placements; low for analytic proxies |
| **US 11,087,060 B1** ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11087060)) | Cadence; filed 2019-07-29; granted 2021-08-10 | Train device-position predictors on a prior schematic plus layout; apply to a new design as **hard constraints** (only satisfying solutions) and **soft constraints** (a cost function). Analog context, but claim 1 says "electronic design" | **Medium** for "learn placement constraints from prior boards" |
| US 11,379,646 B1 | Cadence; 2022-07-05 | Infer missing synthesis parameters (placement, via assignment, routing, pouring); ML predicts compute resources | Low |
| US 11,544,574 B1 / 11,620,548 B1 | Cadence; 2023 | ML recognition of transistor structures; parasitic prediction | Low (IC) |
| **US 11,842,136 B2** ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11842136)) | InstaDeep; priority GB 2019-11-27 (1917292–1917295); PCT/GB2020/053055; granted 2023-12-12; inventors Chouba et al. | Two or more connection **orders** → NN-guided **SMC look-ahead** → posterior over orders → select, route, update. Rewards: length, bends, density, preferred layer; posterior as training target; resample and clone particles; entropy weighting | **High** for (look-ahead over orders or sub-routes) + (NN guidance, which arguably includes an LLM) + (posterior-based selection) |
| **US 12,019,968 B2** ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12019968)) | InstaDeep; 2024-06-25; Fu et al. | Candidate points from **linear rays** where direction changes avoid "isolation region" polygons (angles equal the allowed bends; tangent intersections), plus NN-guided SMC sub-route selection | **High** with the same combination; ray/tangent generation **alone** is not claimed |
| **US 12,159,094 B2** ([USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12159094)) | InstaDeep; 2024-12-03 | NN-guided SMC over candidate sub-routes; stored training targets | High (same combination) |
| **US 2025/0315590 A1** (pending; [USPTO](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20250315590)) | NVIDIA; filed 2025-04-01; provisionals 2024-04-03, 2025-01-30; published 2025-10-09; Ho et al. | "a circuit layout tool configured to generate a layout … based on input cluster constraints; and a feedback loop comprising an agent configured to operate a large language model in a Thought-Action-Observation (ReAct) prompting loop to update the cluster constraints". The description is about standard cells | **Highest watch item.** Monitor prosecution; claims may narrow |
| US 2026/0187328 A1 (pending) | NVIDIA; 2026-07-02 | GPU **stencil-buffer** overlap counting for generative layout | Medium if we use GPU stencil counting |
| US 12,566,911 B2 | **Honeywell**; filed 2022-11-28; granted 2026-03-03 | ML parasitic estimate shown as complex impedance in a GUI | Medium only for ML estimators displayed in a GUI |
| US 11,042,981 B2 / 11,662,479 B2 | **SVXR** (2021) / Bruker Nano (2023) | ML on X-ray inspection data and engineers' corrections adjusts PCB design | Low |
| US 2026/0228404 A1 (pending) | Wistron; 2026-08-06 | Learned netlist-topology similarity against reference PCB modules; offers layout reuse | Medium for "reuse blocks from prior designs" |
| US 2025/0307516 A1 (pending) | Think Circuits; 2025-10-02 | Automated BOM, schematic, layout and DFM review engines plus a modification engine | Low–medium |
| Celus US 12,688,343 B2, US 12,443,611 B2; Circuit Mind US 12,050,847 B2 | 2024–2026 | Requirements and block diagrams → component database or CSP solver → schematic and BOM | Low for layout |
| Google "AlphaChip" family (US 10,699,043; 11,100,266; 11,675,940; 12,086,516; 11,216,609; 11,556,690; 11,853,677; 12,248,745) | 2020–2025 | Claims recite placement on "the surface of an integrated circuit chip" | Low for PCB |

**Corrections made during the deep pass:**
- US 12,566,911 is Honeywell.
- US 11,042,981 is SVXR.
- US 12,223,248 is confirmed Cadence.
- US 11,599,699's inventors are Roberto et al. (not Quayle/Poplack) [P].

**Negative searches:**
- PCB + LLM/natural language + layout/placement/routing in claims: no PCB layout patent.
- Schematic constraint extraction by ML/NL/LLM: only IC-level Cadence filings.
- RL + PCB: only Cadence '699.
- No Quilter, Flux, JITX or Synopsys/Ansys hits.
- Altium: only US 10,089,429 (2018, verification).
- Siemens/Mentor: 23 documents, none ML (e.g. US 7,305,648 distributed autorouting).
- Zuken: 25 documents, none ML layout (newest US 12,572,710, EMI-scan overlay).
- Huawei: 7 PCB documents, all hardware structures [P].

**Eligibility context:** *Recentive v. Fox* (Fed. Cir., Apr 2025) held generic ML applied to a new data environment ineligible under §101 [S].

**Expiry estimates** (from filing dates; unverified; subject to fees and PTA): Cadence '699 ~2041 (2040-02-10 + 469 days); InstaDeep family ~2040-11 plus any PTA; Cadence '248 ~2040-08 plus any PTA [I].

## Recommendations for our system
- **(a) Avoid, or seek counsel before shipping:**
  - an RL-trained policy over board images plus scalars choosing place/via/route actions ('699);
  - a GA placer whose fitness is a CNN + GCN + DNN routability model trained on autorouter labels ('248);
  - NN- or **LLM-guided** particle (SMC) look-ahead over net orders or sub-routes with posterior selection (InstaDeep) [I].
- **(b) Monitor** NVIDIA 2025/0315590. Gather LLM-agent EDA prior art from before 2024-04-03, and watch whether "circuit" stays generic or narrows to standard cells [I].
- **(c) Lower risk:**
  - LLM orchestration of push-and-shove, Freerouting, analytic, SA or force-directed placement;
  - deterministic net-order heuristics, or full re-route evaluation of a few LLM-proposed orders;
  - analytic and field-solver physics;
  - rule-based comprehension with human confirmation [I].
- **Keep this watch-list in the repo** and get counsel before training RL policies or learned routability predictors. Our open publications create dated prior art [I].

## Conflicts and open questions
- Not checked: CN/EP/WO/JP filings, legal or maintenance status, claim construction, validity.
- Applications filed after about April 2025 are unpublished.

## Sources
- research notes:
  - [patents_and_industry.md § 5, § 3, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/patents_and_industry.md)
  - [licensing.md § 4 notes (no license protects against third-party patents)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/licensing.md)
- primary: [USPTO Patent Public Search](https://ppubs.uspto.gov/pubwebapp/), [Fish & Richardson on Recentive](https://www.fr.com/insights/thought-leadership/blogs/federal-circuit-clarifies-limits-of-patent-eligibility-for-machine-learning-claims/)

See also: [deeppcb.md](deeppcb.md), [commercial-incumbents-and-startups.md](commercial-incumbents-and-startups.md), [commercial-architecture-patterns.md](commercial-architecture-patterns.md)
