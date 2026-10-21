# Data licensing tiers, contamination and bias

**TL;DR**
- **Licensing is a first-order constraint on data.** Licence status of the main pools:
  - PCBench: 62% unlicensed;
  - kicad-happy sample: 41% with no licence file;
  - circuit-skills' licensed corpus: 46% reciprocal [P, measured].
- **CERN-OHL-S §3.2:** "Including Covered Source in a larger work is modifying the Covered Source." Copying a reciprocal fragment's geometry into a user's board plausibly makes that board reciprocal. Whether model *training* is covered is unaddressed [P].
- **Tiers:**

  | Tier | Licences | Uses |
  |---|---|---|
  | A | permissive | training, redistributed data and geometry-copying retrieval |
  | B | reciprocal | evaluation, plus attributed retrieval with a derivative warning |
  | C | unlicensed, NC, ND | private evaluation only |

  Our **data products are CDLA-Permissive-2.0**, so only tier A feeds them [I].
- **Contamination is real.** Hardware benchmarks show about 100% contamination for GPT-3.5 and GPT-4o. Use time- and cluster-split held-out boards [P].
- **Code licence note:** project code is now **GPL-3.0-or-later**, so GPL-3.0 tools (e.g. Freerouting, PCBWorld-Engine) can be integrated in-process. This does not change *data* tiers. Board files under GPL or CERN-OHL-S stay tier B for redistributed data [I].

## Key facts

### Measured licence mixes [P, measured]

| Pool | Unlicensed or unclear | Permissive | Reciprocal |
|---|---|---|---|
| PCBench (1,183) | 62.1% | 18.7% | 18.0% |
| kicad-happy sample (54) | 41% | 37% | 22% |
| circuit-skills licensed (235) | 0% (filtered) | 54% (128) | 46% (107: GPL-3 67, CERN-OHL-S 25, CC-BY-SA 10, CERN-OHL-W 5) |

### Licence texts and precedents
- **CERN-OHL-S v2** [P] ([SPDX text](https://raw.githubusercontent.com/spdx/license-list-data/main/text/CERN-OHL-S-2.0.txt)):
  - §1.5 "Product": anything "arising from the use, application or processing of Covered Source";
  - §2.4: "not intended to restrict fair use, fair dealing";
  - §3.2: the larger-work clause;
  - §4: conveying Products requires providing the Complete Source.
- **KiCad 9+ corpus split:** CC-BY-SA-4.0 is "one-way compatible *to* GPLv3 only". The copyleft subset was relicensed GPL-3.0-or-later, and its author asserts trained models carry GPL obligations (their interpretation) ([dataset](https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft)) [P].
- **The Stack:** a permissive-only subset matched HumanEval and MBPP performance; "near-deduplicating the data significantly boosts performance"; it offers an opt-out tool ([2211.15533](https://arxiv.org/abs/2211.15533)) [P].
- **open-schematics:** CC-BY-4.0 at dataset level over mixed-licence sources, a licence-laundering risk [P].
- **Practitioner precedent:** circuit-skills and kicad-tools fetch at pinned SHAs into caches, "never into the repo", and record per-board licences. kicad-tools treats unlicensed repos as "ideas only" [P, third-party].
- **PCB layout copyright:**
  - Taiwan treats a layout as a protectable graphical work [S];
  - Singapore litigated PCB artwork (*Real Electronics v Nimrod*) [S];
  - the US SCPA covers chip mask works, not boards [S].

### Contamination
- **VeriContaminated:** "near 100% rates in GPT-3.5 and GPT-4o" on VerilogEval and RTLLM (CDD α = 0.05, Min-K% 0.55), "which explains their superior performance" ([2503.13572](https://arxiv.org/abs/2503.13572)) [P].
- **CodeV-R1** drops training samples with Rouge-L > 0.5 to any evaluation benchmark ([2505.24183](https://arxiv.org/abs/2505.24183)) [P].
- **LiveVerilogEval** (DATE'26) proposes a contamination-free benchmark [S].
- Popular open boards are near-certainly in pretraining crawls [I].

### Hobbyist bias [P, measured]
- 63% of kicad-happy repos and 89% of PCBench boards are 2-layer.
- Decap-distance p90 is 26 mm on 2-layer boards vs 7.7 mm on 4-layer boards (see [measured-priors.md](measured-priors.md)).
- Only 33% of licensed, fully routed boards are DRC-clean under their own rules.

## Recommendations for our system

### Licence tiers [I]

| Tier | Licences | Allowed uses |
|---|---|---|
| A | MIT, Apache, BSD, CC0, CERN-OHL-P, CC-BY | Training; redistributed derived data (attribution); retrieval that copies geometry |
| B | GPL, CERN-OHL-S/W, CC-BY-SA, TAPR | Evaluation; retrieval that shows the fragment with licence and attribution, warning that copying makes the board a derivative; training only with counsel's sign-off, never in redistributed weights by default |
| C | NC (manifest tier `noncommercial`) | Private, non-commercial evaluation only, fetched at a pinned SHA, never redistributed |
| — | none, ND, "personal use", vendor EULAs | Not collected (user decision 2026-10-21) |

### What testing each tier allows [I]

Our use: fetch at a pinned commit, modify locally (strip routing, move parts), run automated and LLM tools, publish only aggregate scores.

| Licence family | Testing allowed? | Limit |
|---|---|---|
| Permissive, copyleft, reciprocal (MIT … GPL, CERN-OHL-S, CC-BY-SA, TAPR) | Yes | Obligations start only on distribution; we distribute pointers, not boards |
| CC NC | Only if the use is non-commercial | CC defines NC as "not primarily intended for or directed towards commercial advantage"; internal R&D in a company can fall on the commercial side. Kept in a separate manifest so it can be switched off |
| CC ND | Excluded | ND 4.0 allows private adaptations, but a routed/placed output is too easy to publish by accident |
| Terms granting use but not modification, "personal use" | Excluded | Our tests modify every board |
| No licence | Excluded | No grant of rights at all |

Applied in [wide-board-corpus.md](wide-board-corpus.md#licence-policy-user-decisions-applied-to-every-row).

- **Facts over expression:** aggregate statistics (percentiles, width ratios) and abstract constraint graphs are far less likely to carry copyright or reciprocal obligations than verbatim geometry. This is an inference, not legal advice.
- Keep an **opt-out list**; record per-board SPDX (LICENSE + README + scancode).
- **Contamination control:**
  - time-split boards committed after the base model's cutoff, plus private boards;
  - cluster-split by footprint set or WL hash;
  - a CodeV-R1-style similarity filter between training fragments and evaluation boards;
  - report popular and obscure splits separately;
  - Min-K%-style probes.
- **Bias control:** condition priors on layer count, package and board class; weight professional and DRC-clean boards.
- **Code reuse** follows the project licence rules (GPL-3.0-or-later; avoid GPL-2.0-only, AGPL, NC). See [../licensing/reuse-matrix.md](../licensing/reuse-matrix.md).

## Conflicts and open questions

- There is no legal analysis of ML training on CERN-OHL, GPL or CC-BY-SA hardware, or of whether model weights are a CERN-OHL "Product". Counsel is needed.
- No contamination study exists for PCB layout benchmarks.
- OmniLayout's data licence is disputed (CC-BY-4.0 per the paper vs none per third-party recon).

## Sources
- research notes:
  - [learning_from_layout_data.md § Q7, § Q8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/learning_from_layout_data.md)
  - [verification_papers.md § 1 row 28](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)

See also: [corpora-and-yield.md](corpora-and-yield.md), [layout-retrieval-and-reuse.md](layout-retrieval-and-reuse.md), [training-recipes.md](training-recipes.md)
