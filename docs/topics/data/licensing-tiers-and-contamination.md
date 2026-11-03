# Data licensing tiers, contamination and bias

Scope: which board licences permit which data uses (training, redistribution, retrieval, testing), contamination control and hobby bias. Not here: licences of our own data/rules/weights and base models -> [../licensing/data-rulepacks-weights.md](../licensing/data-rulepacks-weights.md); per-row licence decisions -> [wide-board-corpus](wide-board-corpus.md#licence-policy-user-decisions-applied-to-every-row); code reuse -> [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md).
Keys: tier A/B/C, noncommercial, ND, CERN-OHL-S §3.2, larger work, derivative, contamination, VeriContaminated, Min-K%, time-split, cluster-split, hobbyist bias, opt-out list

## Measured licence mixes [P, measured]

- PCBench 62.1% unlicensed; kicad-happy sample (54) 41% no licence file -> [corpora-and-yield](corpora-and-yield.md#pcbench-source-pool-of-pcbworld-d3).
- circuit-skills licensed (235): permissive 54% (128), reciprocal **46%** (107: GPL-3 67, CERN-OHL-S 25, CC-BY-SA 10, CERN-OHL-W 5). The split uses GitHub-detected labels (same 235 boards as pcb-corpus); our audit of 89 found `minuet` recorded MIT with CERN-OHL-W hardware, so the split is unaudited ([open-board-sources](open-board-sources.md#open-questions)).

## Licence tiers [I]

| Tier | Licences | Allowed uses |
|---|---|---|
| A | MIT, Apache, BSD, CC0, CERN-OHL-P, CC-BY | Training; redistributed derived data (attribution); retrieval that copies geometry |
| B | GPL, CERN-OHL-S/W, CC-BY-SA, TAPR | Evaluation; retrieval showing the fragment with licence and attribution, warning that copying makes the board a derivative; training only with counsel's sign-off, never in redistributed weights by default |
| C | NC (manifest tier `noncommercial`) | Private, non-commercial evaluation only, fetched at a pinned SHA, never redistributed |
| — | none, ND, "personal use", vendor EULAs | Not collected (user decision 2026-10-21) |

- Our data products are **CDLA-Permissive-2.0**: only tier A feeds them ([CDLA terms](../licensing/data-rulepacks-weights.md#licenses-for-our-own-data-docs-and-rules)).
- GPL-3.0-or-later project code ([LICENSING.md](../../../LICENSING.md#why-gpl-for-code)) does not change data tiers: GPL or CERN-OHL-S board files stay tier B for redistributed data [I].
- Facts over expression: aggregate statistics (percentiles, width ratios) and abstract constraint graphs are far less likely to carry copyright or reciprocal obligations than verbatim geometry. Inference, not legal advice.
- Keep an opt-out list; record per-board SPDX (LICENSE + README + scancode).

## What testing each tier allows

Our use: fetch at a pinned commit, modify locally (strip routing, move parts), run automated and LLM tools, publish only aggregate scores [I].

| Licence family | Testing allowed? | Limit |
|---|---|---|
| Permissive, copyleft, reciprocal (MIT … GPL, CERN-OHL-S, CC-BY-SA, TAPR) | Yes | Obligations start only on distribution; we distribute pointers, not boards |
| CC NC | Only if the use is non-commercial | CC defines NC as "not primarily intended for or directed towards commercial advantage"; internal R&D in a company can fall on the commercial side. Separate manifest so it can be switched off |
| CC ND | Excluded | ND 4.0 allows private adaptations, but a routed/placed output is too easy to publish by accident |
| Terms granting use but not modification, "personal use" | Excluded | Our tests modify every board |
| No licence | Excluded | No grant of rights at all |

Applied in [wide-board-corpus](wide-board-corpus.md#licence-policy-user-decisions-applied-to-every-row).

## Licence texts and precedents

- **CERN-OHL-S v2** [P] ([SPDX text](https://raw.githubusercontent.com/spdx/license-list-data/main/text/CERN-OHL-S-2.0.txt)):
  - §1.5 "Product": anything "arising from the use, application or processing of Covered Source";
  - §2.4: "not intended to restrict fair use, fair dealing";
  - §3.2: "Including Covered Source in a larger work is modifying the Covered Source." Copying a reciprocal fragment's geometry into a user's board plausibly makes that board reciprocal; whether model *training* is covered is unaddressed;
  - §4: conveying Products requires providing the Complete Source.
- **KiCad 9+ corpus split:** CC-BY-SA-4.0 is "one-way compatible *to* GPLv3 only"; the copyleft subset was relicensed GPL-3.0-or-later; its author asserts trained models carry GPL obligations (their interpretation) ([dataset](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft)) [P].
- **The Stack:** permissive-only subset matched HumanEval and MBPP; "near-deduplicating the data significantly boosts performance"; offers an opt-out tool ([2211.15533](https://arxiv.org/abs/2211.15533)) [P].
- **open-schematics:** CC-BY-4.0 at dataset level over mixed-licence sources: licence-laundering risk [P].
- **Practitioner precedent:** circuit-skills and kicad-tools fetch at pinned SHAs into caches, "never into the repo", and record per-board licences; kicad-tools treats unlicensed repos as "ideas only" [P, third-party].
- **PCB layout copyright:** Taiwan treats a layout as a protectable graphical work [S]; Singapore litigated PCB artwork (*Real Electronics v Nimrod*) [S]; the US SCPA covers chip mask works, not boards [S].

## Contamination

Evidence:
- **VeriContaminated:** "near 100% rates in GPT-3.5 and GPT-4o" on VerilogEval and RTLLM (CDD α = 0.05, Min-K% 0.55), "which explains their superior performance" ([2503.13572](https://arxiv.org/abs/2503.13572)) [P].
- **CodeV-R1** drops training samples with Rouge-L > 0.5 to any evaluation benchmark ([2505.24183](https://arxiv.org/abs/2505.24183)) [P].
- **LiveVerilogEval** (DATE'26) proposes a contamination-free benchmark [S].
- Popular open boards (HackRF, Glasgow, Corne, Antmicro carriers) are near-certainly in pretraining crawls [I].

Controls [I]:
1. Time-split: boards whose *first* public commit (blob lineage, forks and re-uploads deduplicated) is after the base model's cutoff, plus private boards. Pinning a post-cutoff commit of an older board does not decontaminate it.
2. Cluster-split by footprint set or WL hash.
3. CodeV-R1-style similarity filter between training fragments and evaluation boards.
4. Report popular and obscure splits separately.
5. Min-K%-style probes need per-token log-probabilities (open-weight models only); weak evidence.

## Hobbyist bias [P, measured]

- 63% of kicad-happy repos and 89% of PCBench boards are 2-layer ([corpora-and-yield](corpora-and-yield.md)).
- Decap-distance p90 26 mm on 2-layer vs 7.7 mm on 4-layer boards ([measured-priors](measured-priors.md#decoupling-distance-priors)).
- Only 33% of licensed, fully routed boards are DRC-clean under their own rules.
- Control [I]: condition priors on layer count, package and board class; weight professional and DRC-clean boards.

## Open questions

- No legal analysis of ML training on CERN-OHL, GPL or CC-BY-SA hardware, or of whether model weights are a CERN-OHL "Product". Counsel needed.
- No contamination study exists for PCB layout benchmarks.
- OmniLayout's data licence disputed (CC-BY-4.0 per the paper vs none per third-party recon).
- Tier conflict: an earlier summary here put unlicensed, NC and ND boards together in tier C (private evaluation); the later user decision (2026-10-21) excludes unlicensed and ND entirely (table above). [../licensing/data-rulepacks-weights.md](../licensing/data-rulepacks-weights.md#tiers-for-board-bundles) uses a different scheme (R/SA/E, E = unlicensed fetch-only evaluation); A ≈ R, B ≈ SA; E conflicts with the 2026-10-21 decision.

## Sources

- research notes: [learning_from_layout_data.md § Q7, § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md); [verification_papers.md § 1 row 28](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
- related: [layout-retrieval-and-reuse](layout-retrieval-and-reuse.md), [training-recipes](training-recipes.md)
