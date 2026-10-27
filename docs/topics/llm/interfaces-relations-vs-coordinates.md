# LLM write interface: relations, not coordinates

**TL;DR**
- Holding the harness fixed and changing only the write interface moves PCB clean-pass from **23.2% (coordinates) to 90.9% (relation bundle)**. This swing is larger than any model difference [P].
- The LLM should commit **named relations over named objects**, with **ordinal magnitudes** (tight/close/loose). It must never write a coordinate or a metric distance.
- Submit the **whole bundle at once** for joint realization. Sequential relations reach 62.4%; the bundle reaches 90.9% [P].
- Infeasibility feedback should name the conflicting constraints and the **admissible relaxations**, so that the LLM revises commitments instead of geometry.
- Store the bundle as the intent artifact. Re-solving the same bundle after board or footprint changes passed **89.5%**, against **65.6%** for coordinate reuse [P].

## Key facts

### RAC (Relational Agent Contract)

[arXiv 2610.20935](https://arxiv.org/pdf/2610.20935), Univ. of Washington, 14 Oct 2026, preprint [P].

**Setup.**
- 98 PCB tasks: 42 routing, 31 placement, 17 combined and 8 repair.
- Task content: decoupling, board-edge association, keepouts, grouping, symmetry, alignment and routing relations.
- 6 seeds, at most 5 model calls, 9 models (including Claude Opus 4.8 and 5, GPT-5.6 and Gemini 3.8 Flash).

**Mean clean-pass by interface:**

| Interface | Clean-pass |
|---|---|
| Direct coordinates | 23.2% |
| Coordinates plus a Python sandbox | **21.0%** (code does not rescue coordinates) |
| PCBWorld-style candidate selection | 37.4% |
| Sequential single relations | 62.4% |
| Requirements-only delegation | 74.0% |
| **RAC** (bundled relations) | **90.9%** (77.6–95.9% by model) |

**Other results:**
- Eight of nine models reached 89.8–95.9%. Newer models were not reliably better: Opus 4.8 beat Opus 5, and GPT-5.6 Luna beat Sol [P].
- RAC used 22.9–48.5% fewer tokens than candidate selection, and had the lowest latency for 7 of 9 models [P].
- **Harness robustness:** across native function calling, Codex, Claude Code and OpenCode, coordinates scored 22.7–32.7% and RAC 91.8–95.9%. Coding-agent harnesses cost **2.2–5.4×** the tokens of native calls [P].
- **Robustness to geometry change:** the same relations were re-solved after a 20% board shrink, a 20% expansion and a 25% footprint shrink.
  - 89.5% passed (411/459), against 65.6% for the best coordinate-reuse control (frozen, affine, or a fresh solve without relations).
  - Board shrink was hardest: 77.1% vs 47.7% [P].

**Contract details:**
- The agent observes exact authoritative state, including coordinates.
- It may act only through relations: proximity, alignment, symmetry, edge association, keepouts, matched routing, layer preference and via limits.
- Magnitudes are small ordered classes; their metric values are fixed on the solver side.
- An independent DRC plus relation-specific geometric oracles verify the result.
- Example actions: `board_edge(J1, left)`, `place_relative(C1, U1.R1, near, tight)`, `route_matched([N2, N3], 5%)` [P].

**Caveats (verification note):**
- The tasks appear small and synthetic; examples have roughly 5–10 parts.
- The backend placer and router were not identified.
- Preferences that cannot be written as checkable predicates fall outside the contract [P].

### Convergent precedents from scene layout

| System | Mechanism | Result |
|---|---|---|
| **Holodeck** (CVPR 2024) [P] | 10 soft relation types in 5 groups; collisions and bounds are hard; the LLM picks an anchor, then DFS places the rest (MILP alternative with binary auxiliaries for OR) | Human MRR: GPT-4 absolute coordinates **0.364**, about equal to random collision-free placement (0.369); relations plus solver **0.706** ([2312.09067](https://arxiv.org/abs/2312.09067)) |
| **LayoutVLM** (CVPR 2025) [P] | VLM numeric initial poses plus differentiable relations from marked images; projected gradient descent with DIoU collision loss; **self-consistent decoding** keeps only relations its own poses satisfy | CF / in-bounds / semantic alignment: 81.8 / **94.9** / **58.8**, vs LayoutGPT 83.8 / 24.2 / 16.6 and Holodeck 77.8 / 8.1 / 5.6 ([2412.02193](https://arxiv.org/abs/2412.02193)) |
| **Brown PSDL** [P] | Imperative relative programs (`chair.max.x = table.min.x - 0.1`), repaired by LLM-free search minimizing loss + edit distance + volume-weighted optimal transport (large objects move less); about 7.13 edits per scene | Human preference **82.9%** vs DeclBase and **94.3%** vs Holodeck. Repairs 91% of errors (vs 96% for gradient descent), yet wins preference because the relations survive ([2510.16147](https://arxiv.org/abs/2510.16147)) |

**LayoutVLM ablations** (semantic alignment): without self-consistency 46.4; without numeric init 41.0; without spatial constraints 6.7; without the image 48.2 [P].

**(Verification correction):** 2504.05482 and 2510.16147 are one work by the same Brown/UCSD group, not two.

### PCB and EDA precedents for relational output

- **SchGen**: schematic code with relative offsets and pin-name wiring reached 82.0% valid circuits, against 32.5% for raw KiCad files from the same model. See [read-representations.md](read-representations.md) [P].
- **ModuPlace CCG**: the LLM emits a constraint graph with relative offset (x̂, ŷ), rotation θ̂ and weight per edge, and a placer consumes it as soft penalties. See [llm-guided-placement-systems.md](llm-guided-placement-systems.md) [P].
- **PCB-Migrator** (DATE 2026): an offset constraint graph moves expert layouts onto resized or obstructed boards. This is the same use case as RAC's re-solve [S].
- **NS-Place**: MILP legalization with relative-position constraints that preserve global structure [P].
- **Li et al., DAC 2026**: LLM grouping plus constraint-graph/MILP legalization beats a commercial placer and Quilter [S, via survey].
- **Holodeck/LayoutVLM/PSDL plus RAC plus ModuPlace converge on one design point:** the LLM output should be a relation set, never coordinates [I] (verification note).

### Tension: imperative vs bundled

PSDL's sequential imperative programs beat declarative solvers on scenes. On PCB tasks, RAC's sequential-relations baseline (62.4%) lost to one jointly realized bundle (90.9%). Coupled PCB constraints appear to need joint realization [I].

## Recommendations for our system

1. **Typed relation bundle as the only LLM write API** [I]. The verification note's proposed vocabulary:
   - `group`, `region(group, rule_area)`, `side(part, top|bottom)`;
   - `near(part, part.pin, tight|close|loose)`, `align(parts, axis)`, `symmetric(a, b, axis)`;
   - `board_edge(part, side)`, `orient_toward(part, part.pin)`, `keepout(region, layers)`;
   - `route_matched(nets, tol_class)`, `layer_pref(net, layer)`, `via_limit(net, n)`, `net_order(rank)`.

   The EDA note adds `same_side`, `route_priority`, `min_loop(nets)`, `plane(net, layer, region)` and `kelvin(R_sense)`.
2. **Magnitude classes resolve to mm on the solver side**, from net class, stackup, datasheet facts and corpus priors per component class (e.g. the corpus median for a 0402 decap is about 2.5 mm, pad centre to pad centre; see [../data/measured-priors.md](../data/measured-priors.md)). The LLM never chooses mm.
3. **Joint realization** by the analytical placer plus legalizer plus router. Verification uses independent KiCad DRC plus per-relation oracles, never the solver's own satisfaction flag.
4. **Feedback** returns, for each relation, realized or violated, the margin, conflict sets and admissible relaxations.
5. **Self-consistency filter (optional):** drop a proposed relation if the LLM's own coarse sketch violates it (LayoutVLM: −12.4 points without it).
6. **Numeric repair keeps relations:** restrict edits to constants and orientations, and weight movement by footprint area so connectors and ICs move less than passives (PSDL).
7. **Persist the bundle** as the design-intent sidecar, so ECOs and resizes re-solve without new LLM calls. See [../ux/design-rationale-and-intent-record.md](../ux/design-rationale-and-intent-record.md) and [../architecture/constraint-ir.md](../architecture/constraint-ir.md).
8. Coordinates may be *observable* (in the read state) but are never *writable*.
9. Prefer native function calling over coding-agent harnesses, to save 2.2–5.4× tokens.

## Conflicts and open questions

- Does RAC hold on full real boards at PCBWorld D3 scale (dozens of interacting relations, with a KiCad backend)? Its tasks look small and synthetic.
- Calibration of tight/close/loose per component class is unpublished [I].
- **Expressiveness gap:** preferences that are not checkable predicates (aesthetics, house style) need another channel.
- Imperative-sequential (PSDL) vs bundled (RAC): which wins depends on how strongly the constraints are coupled.

## Sources
- research notes:
  - [verification_papers.md § 2.4 RAC, § 2.10 scene precedents, § 3 implications](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_papers.md)
  - [llm_for_eda.md § 1, § 2, § 8](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/llm_for_eda.md)
- primary:
  - [RAC 2610.20935](https://arxiv.org/pdf/2610.20935)
  - [Holodeck 2312.09067](https://arxiv.org/abs/2312.09067)
  - [LayoutVLM 2412.02193](https://arxiv.org/abs/2412.02193)
  - [PSDL 2504.05482](https://arxiv.org/abs/2504.05482) / [2510.16147](https://arxiv.org/abs/2510.16147)
  - [SchGen 2605.30345](https://arxiv.org/abs/2605.30345)
  - [PCB-Migrator DOI](https://doi.org/10.23919/DATE69613.2026.11539307)

See also: [read-representations.md](read-representations.md), [agent-loop-patterns.md](agent-loop-patterns.md), [spatial-reasoning-limits.md](spatial-reasoning-limits.md), [llm-guided-placement-systems.md](llm-guided-placement-systems.md), [../routing/llm-routing-evidence.md](../routing/llm-routing-evidence.md), [../placement/scene-layout-transplants.md](../placement/scene-layout-transplants.md)
