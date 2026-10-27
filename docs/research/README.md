# Research: what we tried, what worked, what did not

This section records every placement, routing and PCB-physics method this project built or
planned. That covers what worked, what partly worked, what failed, what is unfinished, and the
ideas nobody has tested yet. Each page gives the mechanism (objective terms, algorithm steps,
parameters), what we ran, the numbers with their sources, and a verdict.

It has two purposes:
- **Spare others dead ends.** The failures are written up as carefully as the successes.
- **Prior art.** Every page is a dated, public, enabling description, published so that nobody
  can patent these methods.

## Status legend

| Status | Meaning |
|---|---|
| **worked** | Beat its control on the benchmark, scored by `kicad-cli` DRC on the re-opened board |
| **partial** | Won on one axis or one split and lost on another, or won by less than seed noise |
| **did not work** | Built and run; no gain over its control, or worse |
| **not finished** | Built; the deciding run is missing or still running |
| **untested idea** | Mechanism written down; nothing built or run |

Page headers also say when and where a method first appeared (date, commit, branch). Most
results are single-seed or small-n, and each page says so. Results from different benchmark eras
(task specs, score versions, engine versions) are not comparable, and the pages do not mix them.
The benchmark itself is described in [verification/harness](../topics/verification/harness.md).
Metrics: `cp1` is the share of boards clean on attempt 1, and `cpk` the share clean on any of k
attempts.

## How the pages are organised

- `docs/research/<area>/README.md` is the area map: one table row per path, giving status, a
  one-line result, the page and the code.
- `docs/research/<area>/<id>.md` is one write-up per path, or per group of small related dead ends.
- `docs/research/ideas.md` lists the untested ideas, grouped by theme, one paragraph each.
- Code lives in `tools/research/<path>/`. The `kae` package is in `kae/`. Code that was not
  ported is cited by branch and commit.
- Surveys of others' work ([docs/ideas/](../ideas/), `docs/topics/`) are linked, not repeated.

## Areas

| Area | Covers |
|---|---|
| [routing](routing/README.md) | Routing a fixed placement: Freerouting bridge, DRC repair, last-mile router, restart portfolios, critical copper |
| [placement](placement/README.md) | The `kae` physics-aware placer, `autoplace` annealers with the router in the loop, routability estimators |
| [joint](joint/README.md) | Placing and routing together: layer collapse (`jc`), beam/repair/anneal, negotiation, exact windows, MCTS, gradients, the `kae` joint loop |
| [physics](physics/README.md) | Physics models and critics: fast placement terms, exact solvers, rule genealogy, domain models, first-principles lenses |
| [llm-design](llm-design/README.md) | LLM-driven circuit design: a typed circuit IR with checks, four designs with independent reviews, the LLM move proposer |
| [data](data/README.md) | The open-board corpus: licence audit, near-duplicate removal, import fixes, DRC statistics |
| [ideas](ideas.md) | Untested ideas with mechanisms: original ideas, cross-domain transplants, joint place-and-route ideas, problem transformations |

## Headline findings

- **Routing.** A constraint-faithful bridge to Freerouting, combined with DRC repair rounds, a
  grid "last mile" router and a restart portfolio, routes split C (79 larger boards) at cp1 0.532
  and cpk 0.633. Stock Freerouting 2.5.0 gets cp1 0.051. On splits A+B (33 boards) the 4-way
  portfolio was clean on every attempt. Ten times the routing budget closed no extra boards.
  [routing](routing/README.md)
- **Placement.** Physics terms in the placement objective cut the physics score from 35,380
  (terms off) to 1,410; the human placements score 4,392. Routability on A+B did not suffer. On
  split C, though, our placements route clean on 30/78 boards against 43/78 for the human ones.
  Low HPWL alone does not make a board routable: annealed placements with 0.7× the human HPWL
  routed clean less often than the human ones. [placement](placement/README.md)
- **Router in the loop.** Re-annealing only the parts the router and DRC blame took a 14-board
  2-layer smoke suite to 14/14 clean. It did not carry over to larger boards (provisional: 19/105
  clean). [placement](placement/README.md)
- **Joint place and route.** Joint layer collapse by continuation (`jc`) was the best family in
  the joint lab: legal 0.879, clean 0.667, physics 0.82× human (one seed). Exact CP-SAT windows
  (0/112 wins), MCTS, Physarum flows, learned value functions and an LLM move proposer did not
  beat simpler heuristics. [joint](joint/README.md)
- **Physics.** Fast closed-form placement terms track exact solvers closely: loop inductance is
  within 5% (median) of PEEC on 324 loops, and the PEEC is within 1.3% of FastHenry on four loops.
  Rules with a physical origin held 80/91 times; rules from habit were wrong 10/15 times. None of
  it has been checked against a measurement. [physics](physics/README.md)
- **LLM design.** A typed circuit IR with deterministic checks gave clean ERC and exact netlist
  parity on four designs. Independent reviews still found 0–2 blockers and 4–7 major issues per
  design, which no check caught. [llm-design](llm-design/README.md)
- **Data.** 14,318 licence-audited open boards were collected, with 1,637 near-duplicates removed
  by content fingerprint. Only about 17% are DRC-clean, as committed, under their own rules.
  [data](data/README.md)

The 500-board comparison of every merit method (experiments `merit-500r3` and `merit-500r3k`)
is still running. Pages for those methods say "pending" until it finishes.
