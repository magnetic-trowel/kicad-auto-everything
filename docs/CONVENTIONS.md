# Docs conventions

Goal: an agent finds a fact with one `grep` or one index lookup and loads one short
section to get it. Write like a dense reference textbook: definitions, formulas, tables,
figures, numbered facts. Each fact lives in one place; everything else links to it.

## Layout

```
docs/
  INDEX.md                 map: areas, task -> doc table (short)
  SUBJECTS.md              subject index: one line per term -> doc#section (generated)
  IDS.md                   idea id -> defining line (generated)
  CONVENTIONS.md           this file
  digests/<cluster>.md     <= 800 words; one line per statement, each links to its topic doc
  topics/<area>/<topic>.md reference docs (surveys, physics, rules, architecture)
  ideas/                   idea inventories, original ideas, physics-first idea catalog
  research/<area>/         our own methods: mechanism, runs, numbers, verdict (prior art)
reports/                   executive reports (short, link into docs/)
research_notes/            raw evidence; topic docs cite it; not rewritten
```

Find things: `grep -i '<term>' docs/SUBJECTS.md`, then open the linked section.
Idea ids: `grep -w XD113 docs/IDS.md`. Both files are generated from `Keys:` lines and
`- **ID** ...` definition lines by `python3 tools/docs/subjects.py`; re-run it after editing
docs (`--check` fails when they are stale).

## Doc template

```
# <Topic>

Scope: <one line>. Not here: <neighbouring subject> -> <doc link>.
Keys: <comma-separated terms, symbols, aliases, idea ids a reader might grep for>

## <Descriptive noun-phrase heading>
<definitions / formulas / table / numbered facts>

## Open questions            (only if any)
## Sources                   (research-note links, primary URLs)
```

- No TL;DR that repeats the body. A doc may open with up to 5 **Results** bullets
  only if the body is long and the bullets are the doc's conclusions, not a preview.
- No "Recommendations" section restating the facts; write a recommendation once, as an
  imperative line where the fact is ("Use X: Y because Z [C]").
- `docs/research/` pages keep their provenance header (date, commit, branch, status) and
  enough mechanism to reproduce the method: they are defensive publications.

## Style

Do:
- State facts as `term: value [tag]`, table rows, formulas, numbered lists.
- Define a symbol once, where first used: `λ = √(R_s/G)` (sheet screening length).
- Formulas in Unicode or inline code so they grep: `ΔR ≈ (π/4)·R_s·(Δψ/I)²`. Use
  `$...$` LaTeX only when Unicode would be unreadable.
- Figures: ASCII diagrams or Mermaid when geometry or flow is easier to see than read.
- Headings name the content (`## L1. Coil design by stream functions → pours, slots, planar coils`), are unique in
  the file, and stay stable: other docs link to them by anchor.
- Make each section stand alone: name the thing instead of "as above", "this", "the former".
- Quantify: a number with its unit, condition and tag beats an adjective.

Don't:
- Narrate (`we found that`, `it turns out`, `interestingly`, `importantly`, `note that`,
  `in other words`, `this doc covers`, `let's`, `the key insight is`).
- Restate a fact in a second wording, in a summary, a TL;DR, a closing paragraph or another doc.
- Hedge twice (`may potentially`), stack adjectives, or write transitions between sections.
- Write prose paragraphs longer than three sentences. Prefer a table.

Example (before, 61 words):

> The biggest synergy is two adjoints chained. A circuit adjoint (SPICE `.noise`: which
> parasitic moves which output) times a field adjoint (which copper edit moves which
> parasitic) gives the gradient from the circuit specification to the copper geometry in
> two extra solves. No single workstream proposed the whole chain.

After (32 words):

> **Chained adjoints.** ∂output/∂geometry = (∂output/∂parasitic: circuit adjoint, SPICE
> `.noise`, DR3) · (∂parasitic/∂geometry: field adjoint, OP38/OP40/PW39). Cost: 2 extra
> solves. Proposed by no single workstream [I].

## Say it once

- Each fact has one canonical home: the most specific doc on the subject. Other docs link
  to it (`→ [cut pricing](topics/physics/cross-domain-lessons.md#l1-coil-design-by-stream-functions--pours-slots-planar-coils)`)
  and add only what is new in their context.
- Digests, READMEs, inventories and the index only point; they hold no facts of their own
  beyond one-line statements.
- Where two docs disagree, keep the later or verified value and record the conflict in
  `Open questions` of the canonical doc. Corrections from `verification_*.md` research notes
  override the original notes.

## Size

- Digest <= 800 words. Topic doc: aim for <= 1,500 words, hard cap 3,000; split by subject
  rather than exceed. Inventories: one line per idea.

## Evidence tags and links

- Keep evidence tags: `[P]` read in primary source, `[S]` snippet/secondary, `[V]` vendor
  claim, `[I]` our inference, `[C]` computed by our scripts.
- Relative links; encode spaces as `%20`. Link to a section anchor when one exists.
- Never drop a number, unit, source link, commit hash, date, idea id or evidence tag when
  condensing: move it to its canonical home instead.

## Licensing

Code is GPL-3.0-or-later; docs CC-BY-4.0. GPL engines can be integrated in-process.
Avoid GPL-2.0-only, AGPL (reference only), non-commercial and non-redistributable components.
