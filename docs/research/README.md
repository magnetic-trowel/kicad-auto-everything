# Research: what we tried, what worked, what did not

Scope: map of every placement, routing and PCB-physics method this project built or planned. Each page gives mechanism (objective terms, algorithm steps, parameters), runs, numbers with sources, verdict. Not here: surveys of others' work -> [docs/ideas/](../ideas/), `docs/topics/` (linked, not repeated).
Keys: research map, status legend, worked, partial, did not work, not finished, untested idea, prior art, defensive publication, dead ends, cp1, cpk, headline findings

Purposes: (1) spare others dead ends: failures are written up as carefully as successes; (2) prior art: every page is a dated, public, enabling description, published so that nobody can patent these methods.

## Status legend

| Status | Meaning |
|---|---|
| **worked** | Beat its control on the benchmark, scored by `kicad-cli` DRC on the re-opened board |
| **partial** | Won on one axis or one split and lost on another, or won by less than seed noise |
| **did not work** | Built and run; no gain over its control, or worse |
| **not finished** | Built; the deciding run is missing or still running |
| **untested idea** | Mechanism written down; nothing built or run |

- Page headers give when and where a method first appeared (date, commit, branch).
- Most results are single-seed or small-n; each page says so.
- Results from different benchmark eras (task specs, score versions, engine versions) are not comparable; pages do not mix them. Benchmark: [verification/harness](../topics/verification/harness.md).
- `cp1` = share of boards clean on attempt 1; `cpk` = share clean on any of k attempts.

## How the pages are organised

- `docs/research/<area>/README.md`: area map, one table row per path (status, one-line result, page, code).
- `docs/research/<area>/<id>.md`: one write-up per path, or per group of small related dead ends.
- `docs/research/ideas.md`: untested ideas by theme.
- Code: `tools/research/<path>/`; the `kae` package in `kae/`; code not ported is cited by branch and commit.

## Areas

| Area | Covers | Headline result |
|---|---|---|
| [routing](routing/README.md) | Routing a fixed placement: Freerouting bridge, DRC repair, last-mile router, restart portfolios, critical copper | Bridge + repair + last mile + restart portfolio: split C cp1 0.532 / cpk 0.633 vs stock Freerouting 0.051; A+B clean on every attempt; more budget closes nothing → [routing](routing/README.md) |
| [placement](placement/README.md) | The `kae` physics-aware placer, `autoplace` annealers with the router in the loop, routability estimators | Physics terms 35,380 → 1,410 (human 4,392) at no A+B routability cost; split C clean 30/78 vs human 43/78; low HPWL alone does not make a board routable; router-in-the-loop annealing 14/14 on a smoke suite, not on larger boards → [placement](placement/README.md) |
| [joint](joint/README.md) | Placing and routing together: layer collapse (`jc`), beam/repair/anneal, negotiation, exact windows, MCTS, gradients, the `kae` joint loop | `jc` best family (v5 legal 0.879, clean 0.667, one seed); placement and routing not separable; exact windows, MCTS, Physarum, learned value and an LLM proposer did not beat simple controls → [joint](joint/README.md) |
| [physics](physics/README.md) | Physics models and critics: fast placement terms, exact solvers, rule genealogy, domain models, first-principles lenses | Closed-form loop inductance within 5% (median) of PEEC on 324 loops; PEEC within 1.3% of FastHenry on four loops. Rules with a physical origin held 80/91 times; rules from habit were wrong 10/15 times. None checked against a measurement. |
| [llm-design](llm-design/README.md) | LLM-driven circuit design: typed circuit IR with checks, four designs with independent reviews, the LLM move proposer | Typed IR + deterministic checks: clean ERC and exact netlist parity on four designs; independent reviews still found 0–2 blockers and 4–7 major issues per design that no check caught. |
| [data](data/README.md) | The open-board corpus: licence audit, near-duplicate removal, import fixes, DRC statistics | 14,318 licence-audited open boards; 1,637 near-duplicates removed by content fingerprint; about 17% DRC-clean, as committed, under their own rules. |
| [ideas](ideas.md) | Untested ideas with mechanisms: original ideas, cross-domain transplants, joint place-and-route ideas, problem transformations | — |

Cross-cutting: [whole-codebase bug audit (2026-11)](audit-2611.md): about 50 bugs fixed across routers, placer, loader, physics inputs and scoring (score v8, v9; task spec 9). [Host-load drift (2026-11)](benchmark-drift-2611.md): the same run, days apart, left 13.9 % more open connections; compare only arms run side by side.

Pending: the 500-board comparison of every merit method (experiments `merit-500r3`, `merit-500r3k`) is still running; those method pages say "pending" until it finishes.
