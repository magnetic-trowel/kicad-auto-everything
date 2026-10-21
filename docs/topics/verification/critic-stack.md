# Critic stack: turning the review checklist into automated checks

**TL;DR**
- The checklist is encoded as a three-tier critic stack:
  - **A**: KiCad DRC plus generated custom rules, run continuously.
  - **S**: semantic-geometry critics driven by a role/constraint model, run at stage exits.
  - **J**: an LLM judge with simulation hooks, run at review gates.
- Critic priority follows where fabs place holds and where checklist authors agree most: documentation/spec completeness → geometry rules → physics.
- Every finding carries the measured value, threshold, threshold source, objects, evidence image and one concrete fix. Uncertain judgments go to a human.
- Audit DRC severity overrides first ("Anything on 'ignore' makes a clean pass hollow"). Group violations by root cause before fixing.
- Prior art: aklofas/kicad-happy (MIT; parsers plus LLM narration) and the Adom kicad-board-audit skill ("run the real checkers first"; "Every suspicious finding gets a primary source"). Neither has published accuracy.

## Key facts

Tags: [P] primary; [I] inference.

### Tiers

| Tier | When | What | Implementation |
|---|---|---|---|
| A (deterministic) | Continuously, as MacroFab advises for CM DRC | Geometry/DRC items | Generate `.kicad_dru` from the role model and fab profile; run `kicad-cli pcb drc`; map violation types to checklist IDs. Audit severity overrides first (PRC-12); group by root cause (PRC-13) [I] |
| S (semantic geometry) | At state-machine stage exits | Items needing roles/datasheet data | `critic(board, roles, profile) -> [Finding{id, severity, objects, measured, threshold, threshold_source, evidence_png, fix}]` [I] |
| J (judgment) | At review gates | Intent items: MEC-04/06/15, PRC-06/14, GND-04 split justification, ANA-01, option footprints | The LLM gets a structured packet: item text and rationale, datasheet excerpts, role model, cropped renders and Tier A/S numbers. It must answer pass/fail/uncertain with evidence; uncertain goes to a human. HS-08/14, FLX-07 and PWR-01 EMI go to simulators [I] |

### Tier-S priority (consensus × severity × hold data)

| Rank | Critic | Checklist IDs |
|---|---|---|
| 1 | Stackup/impedance/fab-note completeness; net-class coverage | STK-09/12, CAM-04 |
| 2 | Reference-plane continuity under HS traces, including void distance and plane edge | GND-02/10 |
| 3 | Current capacity of tracks and vias | PDN-06/07/13 |
| 4 | Decap distance, value order and own vias | PDN-01/02/11/15 |
| 5 | Hot-loop and switch-node area | PWR-01/02 |
| 6 | Return vias at layer transitions | GND-03 |
| 7 | ESD series placement; filters at exits | EMC-06/07 |
| 8 | Crystal isolation | PLC-07/24 |
| 9 | Via stub, antipad and symmetry on HS pairs | HS-17/18 |
| 10 | Tombstone copper balance | THM-03 |
| 11 | Assembler spacing tables | ASM-09/10 |

### Scoring and thresholds

- **Scoring**: Critical items gate stage exits. Major items are weighted penalties (weights from consensus and hold data). Minor items and aesthetic metrics ([looks-right-metrics.md](looks-right-metrics.md)) become soft placement objectives, always paired with a coupling penalty (Olney's caveat) [I].
- **Threshold provenance**: datasheet first, then the fab/assembler profile, then house defaults. Tool heuristics are labelled as unsourced: claude-eda's 3 mm decap distance, kicad-happy's 10 mm decap search radius and tombstone ratio of 0.3. Sources conflict (silk height, edge clearance), so profiles are mandatory [I].
- **Coverage**: about 37% of items (110 of 299, A or A/S) can be automated now; about 41% more (123, S or S/J) once the role model exists; about 22% (66, J) stay with LLM/human judgment or simulation [I].

### KiCad plumbing for Tier A/S

- **KiCad 9+ classes and rule functions.** Component classes and net classes, plus custom-rule functions such as `hasComponentClass()`, `inDiffPair()`, `intersectsCourtyard()`, `enclosedByArea()`, `fromTo()` and `getField()`, supply most of the plumbing [P].
- **Version traps (VK)**:
  - `microvia_*` constraints are master-only;
  - `insideArea`/`insideCourtyard` are deprecated;
  - JSON violations carry no rule name, so prefix generated rule names with an IR ID and parse `description`.

  The full verified reference is in [../kicad/drc-rule-language.md](../kicad/drc-rule-language.md).
- **What KiCad 10 DRC can express**: courtyard spacing, side and orientation (via `assertion`), area containment, and edge/keepout distances. **What it cannot**: pairwise pad distances between footprints, alignment, symmetry and loop area. Those need Python checkers [P, per VK].

### Prior art (LLM review tools)

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

## Recommendations for our system

- Implement Tier A first. It is cheap, and documentation/parity/footprint errors are the most common and cheapest-to-catch failures ([respin-and-fab-hold-data.md](respin-and-fab-hold-data.md)) [I].
- Make the role model (S0 of [../workflow/expert-state-machine.md](../workflow/expert-state-machine.md)) the gate for Tier S. Verify it as Adom insists, with a primary source per role [I].
- Use the Finding schema as the shared format between critics, the LLM and the findings/waivers channel of the constraint IR ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)) [I].
- Have the LLM write narrative only *after* deterministic parsers and checkers produce numbers ("The parsers do the work, the LLM generates the narrative") [I].

## Conflicts and open questions

- Tier-S thresholds (acceptable hot-loop area, decap distance by package and frequency) are not standardized. They need datasheet extraction or calibration on expert-reviewed boards.
- No evaluated LLM review tool exists; kicad-happy and Adom publish no accuracy.

## Sources

- research notes: [expert_workflow_and_checklists.md § Implications (critic design)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md)
- corrections: [verification_kicad_and_tools.md § 2, § 4 kicad-happy](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)

See also: [review-checklist.md](review-checklist.md), [evaluation-stack.md](evaluation-stack.md), [../workflow/delegation-and-expert-review.md](../workflow/delegation-and-expert-review.md)
