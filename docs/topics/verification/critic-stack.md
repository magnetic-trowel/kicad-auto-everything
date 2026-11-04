# Critic stack: turning the review checklist into automated checks

Scope: three-tier critic stack (A deterministic, S semantic geometry, J judgment) encoding the review checklist; Tier-S priority; scoring and thresholds; KiCad plumbing; prior-art LLM review tools. Not here: the checklist -> [review-checklist.md](review-checklist.md); evaluation tiers T0–T3 -> [evaluation-stack.md](evaluation-stack.md); DRC repair loop -> [../kicad/drc-report-and-repair-loop.md](../kicad/drc-report-and-repair-loop.md).
Keys: critic stack, critic, Tier A, Tier S, Tier J, Finding schema, threshold provenance, role model, severity overrides, root-cause grouping, LLM judge, kicad-happy, Adom kicad-board-audit, claude-eda, hold data
Tags: [P] primary; [I] inference.

## Critic-stack rules
1. Tiers: **A** KiCad DRC + generated custom rules, run continuously; **S** semantic-geometry critics driven by a role/constraint model, at stage exits; **J** LLM judge with simulation hooks, at review gates.
2. Priority follows where fabs place holds (one vendor's self-reported data, AtlasPCB [V]) and where checklist authors agree most: documentation/spec completeness → geometry rules → physics.
3. Every finding carries measured value, threshold, threshold source, objects, evidence image, one concrete fix; uncertain judgments go to a human. The Finding schema is the shared format between critics, the LLM and the findings/waivers channel of the constraint IR ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)) [I].
4. Audit DRC severity overrides first ("Anything on 'ignore' makes a clean pass hollow"); group violations by root cause before fixing.
5. Implement Tier A first: cheap, and documentation/parity/footprint errors are the most common and cheapest-to-catch failures ([respin-and-fab-hold-data.md](respin-and-fab-hold-data.md)) [I].
6. The role model (S0 of [../workflow/expert-state-machine.md](../workflow/expert-state-machine.md)) gates Tier S; verify it as Adom insists, a primary source per role [I].
7. The LLM writes narrative only *after* deterministic parsers and checkers produce numbers ("The parsers do the work, the LLM generates the narrative") [I]. Prior art (kicad-happy, Adom) publishes no accuracy.
## Critic tiers

| Tier | When | What | Implementation |
|---|---|---|---|
| A (deterministic) | Continuously, as MacroFab advises for CM DRC | Geometry/DRC items | Generate `.kicad_dru` from the role model and fab profile; run `kicad-cli pcb drc`; map violation types to checklist IDs. Audit severity overrides first (PRC-12); group by root cause (PRC-13) [I] |
| S (semantic geometry) | At state-machine stage exits | Items needing roles/datasheet data | `critic(board, roles, profile) -> [Finding{id, severity, objects, measured, threshold, threshold_source, evidence_png, fix}]` [I] |
| J (judgment) | At review gates | Intent items: MEC-04/06/15, PRC-06/14, GND-04 split justification, ANA-01, option footprints | The LLM gets a structured packet: item text and rationale, datasheet excerpts, role model, cropped renders and Tier A/S numbers. It must answer pass/fail/uncertain with evidence; uncertain goes to a human. HS-08/14, FLX-07 and PWR-01 EMI go to simulators [I] |

## Tier-S priority
Consensus × severity × hold data.

| Rank | Critic | Checklist IDs |
|---|---|---|
| 1 | Stackup/impedance/fab-note completeness; net-class coverage | STK-09/12, CAM-04 |
| 2 | Reference-plane continuity under HS traces, including void distance and plane edge | GND-02/10 |
| 3 | Current capacity of tracks and vias | PDN-06/07/13 |
| 4 | Decap distance, mounting-inductance order and own vias (value order only behind the contested-rule selector, [../rules/decoupling-pdn.md](../rules/decoupling-pdn.md)) | PDN-01/02/11/15 |
| 5 | Hot-loop and switch-node area | PWR-01/02 |
| 6 | Return vias at layer transitions | GND-03 |
| 7 | ESD series placement; filters at exits | EMC-06/07 |
| 8 | Crystal isolation | PLC-07/24 |
| 9 | Via stub, antipad and symmetry on HS pairs | HS-17/18 |
| 10 | Tombstone copper balance | THM-03 |
| 11 | Assembler spacing tables | ASM-09/10 |

## Scoring and thresholds

- **Scoring**: Critical items gate stage exits. Major items are weighted penalties (weights from consensus and hold data). Minor items and aesthetic metrics ([looks-right-metrics.md](looks-right-metrics.md)) become soft placement objectives, always paired with a coupling penalty (Olney's caveat) [I].
- **Threshold provenance**: datasheet first, then the fab/assembler profile, then house defaults. Tool heuristics are labelled as unsourced: claude-eda's 3 mm decap distance, kicad-happy's 10 mm decap search radius and tombstone ratio of 0.3. Sources conflict (silk height, edge clearance), so profiles are mandatory [I].
- **Coverage**: about 37% of items (110 of 299, A or A/S) can be automated now; about 41% more (123, S or S/J) once the role model exists; about 22% (66, J) stay with LLM/human judgment or simulation [I].

## KiCad plumbing for Tier A/S

- **KiCad 9+ classes and rule functions.** Component classes and net classes, plus custom-rule functions such as `hasComponentClass()`, `inDiffPair()`, `intersectsCourtyard()`, `enclosedByArea()`, `fromTo()` and `getField()`, supply most of the plumbing [P].
- **Version traps (VK):** `microvia_*` constraints master-only → [master-only](../kicad/drc-rule-language-reference.md#master-only-constraints-kicad-11-development); `insideArea`/`insideCourtyard` deprecated → [functions](../kicad/drc-rule-language-reference.md#functions-100); JSON violations carry no rule name → [rule-name protocol](../kicad/drc-report-and-repair-loop.md#rule-name-protocol).
- **What KiCad 10 DRC can express**: courtyard spacing, side and orientation (via `assertion`), area containment, and edge/keepout distances. **What it cannot**: pairwise pad distances between footprints, alignment, symmetry and loop area. Those need Python checkers [P, per VK].

## Prior art LLM review tools

- **aklofas/kicad-happy** (MIT) parses schematic, PCB and Gerbers into structured data. Its PCB analyzer covers connectivity (union-find), decoupling proximity, ground domains, trace proximity, current capacity, thermal-pad vias, via types/annular rings/via-in-pad, layer transitions, courtyard overlap, silkscreen, DFM tiering and tombstoning risk. Its EMC skill has 44 rules, and its harness covers 5,800+ repos and 3,498 PCB files (VERIFIED). Documented limitations include "Zone fill staleness" and "No impedance calculation". Its detector counts are internally inconsistent (40 / 60+ / 21) ([methodology_pcb.md](https://github.com/aklofas/kicad-happy/blob/main/skills/kicad/scripts/methodology_pcb.md)) [P].
- **Adom kicad-board-audit** [P] ([SKILL.md](https://wiki.adom.inc/adom/kicad-board-audit/files/SKILL.md)). Its procedure:
  1. "Run the real checkers first."
  2. Read silenced rule severities.
  3. Group DRC findings by root cause.
  4. Extract a pad-level netlist.
  5. Walk each IC: power pins, mandatory passives, resets, straps, regulator dividers vs the exact variant's VFB, buses, crystals.
  6. Layout audit: net-class coverage, diff skew, via styles, keepout flags, zones.

  "Every suspicious finding gets a primary source." The report is severity-ranked (Critical/High/Medium/Low), with refs, pins, why and one concrete fix per finding. Its slogan is "Never trust a clean ERC".
- **claude-eda** encodes placement priorities and thresholds as prose (unsourced) [P].

## Open questions

- Tier-S thresholds (acceptable hot-loop area, decap distance by package and frequency) are not standardized. They need datasheet extraction or calibration on expert-reviewed boards.
- No evaluated LLM review tool exists; kicad-happy and Adom publish no accuracy.
- The priority order does not match the checklist's automation tags yet: of the rank-1 items only STK-09 is tagged A (STK-12 and CAM-04 are J), and the footprint items FP-01/02/12 are S or J. The documentation-first order also rests on one vendor's hold data; the other vendor dataset ranks geometry first, and holds measure order delays, not respins ([respin-and-fab-hold-data.md](respin-and-fab-hold-data.md)).

## Sources

- [expert_workflow_and_checklists.md § Implications (critic design)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- corrections: [verification_kicad_and_tools.md § 2, § 4 kicad-happy](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)
- See also [../workflow/delegation-and-expert-review.md](../workflow/delegation-and-expert-review.md).
