# Docs conventions

Goal: an agent or person doing a narrow task loads one short doc, not a giant
survey. Detail lives in small topic docs; summaries only point to them.

## Layout

```
docs/
  INDEX.md                 map of everything (short)
  CONVENTIONS.md           this file
  digests/<cluster>.md     executive digests, <= 800 words each
  topics/<area>/<topic>.md focused topic docs
  ideas/                   idea inventories and the original-ideas catalog
reports/                   executive summary report (short, links into docs/)
research_notes/LLM driven PCB placement and routing/
                           raw research notes = evidence; topic docs cite them
```

## Areas and owners

Each area has one owning cluster so files don't collide. Link freely across
areas; if a target doesn't exist yet, link the expected path anyway (links are
checked at the end).

| Area (`docs/topics/...`) | Contents | Owner cluster |
|---|---|---|
| `placement/` | placement algorithms, PCB placers, analog constraint placement, ML placement | algorithms |
| `routing/` | routing algorithms, escape/length/diff-pair routing, ML routing, Freerouting and KiCad PNS internals | algorithms |
| `solvers/` | CP-SAT/MILP/SMT, analytical, metaheuristics, geometry libs, benchmarks | algorithms |
| `llm/` | interfaces/representations, agent loops, spatial reasoning, design understanding, datasheet extraction | llm_data_ux |
| `data/` | corpora, priors, training/fine-tuning recipes | llm_data_ux |
| `ux/` | human-AI interaction, explanations, field-report lessons | llm_data_ux |
| `kicad/` | IPC API, kicad-cli, DRC rule language reference, file formats, Specctra/Freerouting integration pitfalls, MCP server lessons | ecosystem |
| `landscape/` | existing open tools, commercial systems, patents | ecosystem |
| `licensing/` | license inventory and reuse matrix (code is GPL-3.0-or-later) | ecosystem |
| `rules/` (si, emc, stackup, diff pairs, `interfaces/`, crystals/clocks, myths, SI/EMI checkers) | high-speed and EMC rules | rules_hs_emi |
| `rules/` (`power/`, decoupling-pdn, rf, analog, isolation, thermal, dfm-fab, datasheet-to-constraints, power checkers) | power, RF, analog, DFM rules | rules_power |
| `workflow/` | expert workflow state machine, practitioner views, trust requirements | practice |
| `verification/` | review checklist, evaluation stack, metrics, benchmarks | practice |
| `architecture/` | constraint/intent IR | practice |
| `synthesis/` | brief-to-schematic generation, part selection, schematic-level verification, intent handoff | synthesis |

## Size limits

- Digest: <= 800 words. Executive statements (one or two lines each), every
  statement links to the topic doc(s) holding the detail.
- Topic doc: aim for 600-2,000 words; hard cap 3,000. Split rather than exceed.
- Idea inventories (`docs/ideas/`) may be longer; one line per idea.

## Topic doc template

```
# <Topic>

**TL;DR**
- <= 5 bullets with the conclusions that matter for building the system.

## Key facts
(tables preferred; numbers with inline source links and evidence tags)

## Recommendations for our system

## Conflicts and open questions

## Sources
- research notes: [file.md § Section](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/file.md)
- primary URLs

See also: related topic docs (relative links)
```

## Content rules

- Corrections from `verification_*.md` notes override the original notes.
- Keep evidence tags: `[P]` read in primary source, `[S]` snippet/secondary,
  `[V]` vendor claim, `[I]` our inference.
- Use relative links. Encode spaces in paths as `%20`.
- Licensing: code is GPL-3.0-or-later; GPL engines can be integrated in-process.
  Avoid GPL-2.0-only, AGPL (reference only), non-commercial, and
  non-redistributable components.
- No new research in synthesis passes; cite the notes.
