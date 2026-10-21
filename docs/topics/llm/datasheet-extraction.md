# Datasheet and app-note extraction

**TL;DR**
- Extracting **electrical facts** is reliable when **staged and grounded**:
  - chunked, provenance-preserving extraction reaches **98.8%** property faithfulness, against 76.1% one-shot;
  - compatibility checks with deterministic scripts reach **97.5%** [P].
- **Naive "upload the PDF and ask" is unreliable:**
  - the best model passes **30.7%** of GDP.pdf professional-PDF questions;
  - PDF input scores 0.43 on PCB-QA;
  - one model **faked extractions without opening the datasheet** [P].
- **No system or benchmark extracts PCB *layout* guidelines** from datasheets or app notes, or parses EVM reference layouts into relations. This is a gap we must fill [P].
- **Two schemas:**
  - electrical tables: staged extraction with provenance;
  - layout guidance: typed predicates that keep qualitative strength. Never invent millimetres [I].
- For MCUs and SoCs, read the **hardware design guide** first; that is where numeric layout rules live [P].

## Key facts

### Pipelines and reliability

| Work | Method | Result | Source |
|---|---|---|---|
| Hierarchical hardware KG (Oct 2026) | Chunked property extraction, hierarchical routing, iterative refinement, "validated instructions and deterministic local execution", provenance | **98.8% vs 76.1%** one-shot (20 datasheets). Covers 83.6% of the baseline's faithful properties; the baseline covers 10.5% of its. One-shot "omits relevant specifications even when the document fits within the model's context window" | [2610.12762](https://arxiv.org/abs/2610.12762) [P] |
| "Fidelity Is Not Enough" (EMNLP 2026 Industry) | Dispatch-level logging of every tool call | One model "passed our fidelity check without ever opening the datasheet": a structured-output constraint had disabled tool use. Logging caught **50/50 planted faults** with 0 false flags on 207 clean runs. Physical measurement verified only 2 of 37 claims | [2608.28439](https://arxiv.org/abs/2608.28439) [P] |
| Datasheet-aware compatibility verification | Design graph; retrieve only the properties the criteria need; **generate deterministic scripts** for the numbers | **97.5%** on 7 designs / 34 datasheets; **8.6× less context** | [2608.25217](https://arxiv.org/abs/2608.25217) [P] |
| D2S-FLOW (datasheet → SPICE) | Document focusing, hierarchy-aware retrieval, entity normalization | EM 0.86, F1 0.92, exact correctness 0.96; 38% fewer tokens | [2502.16540](https://arxiv.org/abs/2502.16540) [P] |
| GDP.pdf (CVPR 2026 workshop) | Hard professional-PDF questions | Best of 17 models: **30.7%**. Errors: "misaligned tables, misread charts, skipped footnotes and exclusions… amendments that supersede earlier text" | [2607.11192](https://arxiv.org/abs/2607.11192) [P] |
| ElecSafety | Datasheet and manual rules for safety judgments | Better, but "unreliable on near-boundary and missing-information scenarios" | [2610.06905](https://arxiv.org/abs/2610.06905) [P] |
| SpecMap | Hierarchical narrowing (repo → file → symbol) | 73.3% file mapping; **−84% tokens**, about −80% runtime | [2601.11688](https://arxiv.org/abs/2601.11688) [P] |
| DocEDA | Datasheet layout-analysis model plus CoT parameter extraction plus YOLO circuit parsing | — | [2412.05301](https://arxiv.org/abs/2412.05301) [P] |
| HWE-Bench preprocessing | PDF → Markdown (MinerU) → LLM → pin JSON | "Greatly mitigat[es] misunderstandings caused by document formatting" | [2603.18102](https://arxiv.org/abs/2603.18102) [P] |
| DRC-Coder | Rule text plus illustrations → interpretation LLM → coding LLM → checker | F1 1.000 vs 0.631: maps to "datasheet rule → executable board check" | [2412.05311](https://arxiv.org/abs/2412.05311) [P] |
| Weak verifiers | LLM-written verifier programs, aggregated | Up to 7× F1 over LLM-as-judge | [2606.05268](https://arxiv.org/abs/2606.05268) [P] |
| JITX test (2024) | nRF5340 95-row pin table from an 820-page datasheet | "Exactly correct" | [JITX](https://blog.jitx.com/jitx-corporate-blog/testing-generative-ai-for-circuit-board-design) [V] |
| RF workflow | Agent read a datasheet mid-design | Noticed the ESD variant's V_CEO = 2.25 V limit and redesigned the bias unprompted | [2608.31006](https://arxiv.org/abs/2608.31006) [P] |

**DRCY** (AllSpice, production; no accuracy numbers) [P] ([2603.15672](https://arxiv.org/abs/2603.15672)):
1. netlist augmentation;
2. component selection and grouping;
3. **agentic datasheet retrieval** (DigiKey or client APIs):
   - a Critic scores each extraction out of 10: feature completeness 25%, **pin-function coverage 40%**, application info 20%, typical circuits 15%;
   - up to 5 alternative sources;
   - a 7-day cache keyed by part number and URL;
4. per-group pin-by-pin review;
5. k-run consensus plus error grouping.

A strong model reviews; a weak model extracts. Findings are posted as inline review comments.

**kicad-happy datasheet skill** [P] ([datasheet-extraction.md](https://github.com/aklofas/kicad-happy/blob/main/datasheet-extraction.md)):
- page selection: TOC → keyword density → fallback (8–15 pages);
- category prompts;
- `SpecValue{min, typ, max, unit, condition, evidence{page, confidence}}`;
- quality-score trust gates; PDF-hash staleness; **"null, never guess"**;
- it **skips app-note and "recommended for X" prose**.

### Footprint and figure geometry
- **LLM4-IC8K / ICGeo8K:** LMMs "severely suffer from inaccurate geometric perception" on IC drawings. The fix splits the task into pin count, centres and dimensions, pretrains on synthetic drawings and fine-tunes on real ones (8,608 samples) ([2508.03725](https://arxiv.org/html/2508.03725v1)) [S].
- **ICLabagent:** multi-agent LMM footprint labelling ([OpenReview](https://openreview.net/forum?id=d6tTnuWmTb)) [S].
- **JITX pattern:** "trust a hand-coded BGA footprint generator for the details, and have the LLM tell me which pads to omit", then reconcile the lists in code [V].

### PDF parsers (OmniDocBench v1.6 table TEDS; general documents, not datasheet-specific) [P] ([leaderboard](https://github.com/opendatalab/OmniDocBench))

| Parser | TEDS |
|---|---|
| MinerU2.5-Pro (1.2B) | **93.42** (overall 95.75) |
| Gemini 3 Flash | 89.29 |
| Gemini 3 Pro | 89.15 |
| MinerU-2.5 | 87.88 |
| dots.ocr | 87.18 |
| olmOCR | 83.00 |
| GPT-5.2 | 82.95 |
| MinerU pipeline | 81.88 |
| Mistral OCR | 76.78 |
| Marker | **65.77** |

Overall leaders: TeleOCR 96.91, OvisOCR2 96.47, PaddleOCR-VL-1.6 96.34. Docling is not in the current table.

### Vendor layout content
Regulator datasheets are qualitative; MCU guides are numeric. See [function-to-recipe-mapping.md](function-to-recipe-mapping.md) for the numbers.

## Recommendations for our system

1. **Pipeline** [I]:
   1. retrieve and score (DRCY critic weights);
   2. parse (MinerU2.5-Pro or a VLM for tables; `pdftotext -layout` fallback for prose);
   3. extract by chunks into a KG with provenance and **applicability conditions**;
   4. map layout statements to the **closed predicate vocabulary** shared with the relation API;
   5. generate or attach a checker per predicate (DRC-Coder / weak-verifier pattern);
   6. multi-run consensus for safety-critical rules.
2. **Reliability controls,** each backed by a cited failure:
   - page and sentence evidence on every value;
   - a **tool-call audit** that rejects runs which never read the source;
   - chunked multi-pass extraction;
   - deterministic computation of derived numbers;
   - consensus for critical checks;
   - PDF-hash plus revision pinning.
3. **Layout guidance:** keep the strength level ("as close as possible" → `weight=high, bound=null`); never invent mm.
4. **Figures** (EVM layouts, recommended layouts) are **low-confidence topology hints** only.
5. **Footprints** come from generators plus real part data; the LLM supplies only pin lists to reconcile.
6. **Build a datasheet layout-guideline extraction benchmark** (a gap and a contribution opportunity; CDLA-Permissive-2.0 data).

## Conflicts and open questions

- No layout-guideline extraction benchmark or EVM-figure parser exists.
- There is no datasheet-specific PDF parser benchmark.
- Vendor machine-readable layout constraints were not found; ADI, ST and NXP were unreachable.

## Sources
- research notes:
  - [netlist_datasheet_understanding.md § 3](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/netlist_datasheet_understanding.md)
  - [llm_for_eda.md § 4](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
  - [field_reports_and_ux.md § 2 (JITX)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)

See also: [part-layout-card.md](part-layout-card.md), [function-to-recipe-mapping.md](function-to-recipe-mapping.md), [design-understanding-pipeline.md](design-understanding-pipeline.md), [../rules/datasheet-to-constraints.md](../rules/datasheet-to-constraints.md)
