# Digest: expert practice, review checklists, practitioner trust, constraint IR, verification stack and benchmarks

**Scope.** This digest synthesizes three notes, each read in full:
- `expert_workflow_and_checklists.md` (**EW**)
- `practitioner_discussions.md` (**PD**)
- `constraints_verification_benchmarks.md` (**CVB**)

Corrections come from `verification_kicad_and_tools.md` (**VK**), searched for KiCad DRC rules, `kicad-cli` and benchmarks. **Where VK conflicts with the other notes, VK wins.** No new research was done. Compiled 2026-10-21.

**Evidence tags** (kept from the source notes):

| Tag | Meaning |
|---|---|
| [P] | Read at the primary source |
| [3P] | Credible secondary source, read in full |
| [Snip] | Search snippet only. This is the "[S]" of EW and CVB |
| [E] | An expert's own words |
| [Sys] | Systematic test with a stated method. This is PD's "[S]" |
| [A] | One practitioner's anecdote |
| [C] | Community opinion |
| [V] | Vendor claim |
| VK status | VERIFIED, CORRECTED, PRECISION or CONFLICT |

"Inference" marks the note author's reasoning. **[digest]** marks my own synthesis.

---

## 0. Verification overrides (read first)

1. **Microvia rules are not in KiCad 10.** `microvia_aspect_ratio`, `microvia_stack_depth` and `isStackedVia` exist only on master (KiCad 11 development). On master the parser keyword is `hole_aspect_ratio`, even though the master docs still say `microvia_aspect_ratio`. EW items DFM-05 and DFM-25 and CVB's constraint list treat these as current. On 10.x these checks must be custom Python code. [VK #14]
2. **DRC units.** Only `mm`, `mil`, `in`, `deg`, `ps` and `fs` are accepted. The documented `th`, `"` and `rad` are rejected. `ps`/`fs` work only in `length` and `skew`, and using them there forces time-domain tuning. [VK #17, #18]
3. **Deprecated functions.** `insideArea`, `insideCourtyard*` and `memberOf` are deprecated, but CVB lists `insideArea` and `insideCourtyard('${Class:X}')` as current. Use `intersectsArea`/`enclosedByArea`, `intersectsCourtyard*` and `memberOfFootprint` instead. [VK §2.4]
4. **Parser traps.**
   - A second `condition` clause silently overwrites the first.
   - Each constraint type may appear only once per rule.
   - Only `(version 1)` and `(rule …)` are valid at top level.
   - Operators all have equal precedence and evaluate left to right.
   - An `ignore` rule is still evaluated and can override earlier rules, but the interactive router does not observe it. [VK §2.1]
5. **DRC JSON output.**
   - It has **no rule-name field**. The rule's source name is embedded in the `description` text.
   - `physical_clearance` violations are reported under the `clearance` and `hole_clearance` keys.
   - `drc.v1.json` has a trailing comma, so it is not valid strict JSON.
   - `--exit-code-violations` makes the exit code 5.
   - Zones are refilled only with `--refill-zones`. The board is saved only with both `--refill-zones` and `--save-board`. [VK §2.9]
6. **Counts in KiCad 10.0.**
   - 35 constraint keywords, including the undocumented `solder_mask_sliver`.
   - 23 current functions, including the undocumented `intersectsKeepout`, plus 5 deprecated.
   - 67 DRC `type` keys.

   Master adds `net_chain_length`, `stub_length` and `return_path` (KiCad's first native reference-plane check), plus `microvia_stack_depth` and `hole_aspect_ratio`. [VK §2]
7. **PCBWorld numbers are VERIFIED** (Clean Pass at @5, D3-A / D3-B):
   - Freerouting **2.1.0**: 0.80 / 0.78.
   - KRT: 0.74 / 0.20.
   - OrthoRoute: 0.02 / 0.00.
   - PPO: 0.86 / 0.45.
   - GPT-5.4: 0.65 / 0.00.

   D3-B evaluation uses **10 boards**. OrthoRoute routability is 0.34 (D2) and 0.53 (D3-A) in the v2 paper; its README says 30% and 51%. [VK #19, #46]
8. **Freerouting has improved since PCBWorld's baseline.** v2.5.0 (2026-10-05) raised its clean rate on its 1,157-board corpus from 30.9% to 75.0%. PCBWorld's 2.1.0 baseline therefore understates current Freerouting; re-baseline. [VK #26, §5.9]
9. **Cypress is confirmed.**
   - DOI 10.1145/3698364.3705346, ISPD '25, pp. 31–41. The paper is closed-access.
   - Benchmarks: the repo ships small-1…small-20, while the slides describe 10 small plus 5 commercial.
   - `enable_rotation` defaults to 0, and part sides are fixed by the input.
   - Award status conflicts: "Best Paper" (Cornell) vs "Best Paper Nominee" (ISPD slides). [VK #22, #28]
10. **Quilter's scope.**
    - Exactly 8 PRCs and 7 constraint types. Timing-sensitive signals are "coming soon".
    - Stated limits: <5,000 pins; >20% pin density is "best handled manually"; <6 GHz; ≤48 V; ≤10 A.
    - 2026 additions: a pin-distance placement constraint (May), a Floorplan page (Jun), and X.Y candidate numbering (Sep). [VK #21, #35, §4]
11. **IPC API limits in 10.0.**
    - The stackup is read-only (`UpdateBoardStackup` has no handler).
    - `RefillZones` refills only the whole board, asynchronously.
    - There is no run-DRC message.
    - Specctra SES import **deletes unlocked tracks and vias and applies the session's placement**, contrary to the user doc. [VK #2, #8, #9]
12. **TraceMaker's comparison** used Freerouting 2.2.4 in single 60 s runs. It is a third-party self-report. [VK #20]
13. **kicad-happy.** The corpus figures (5,800+ repos, 3,498 PCB files) are VERIFIED. Its detector counts are inconsistent across its own docs: 40, 60+ and 21. [VK #41, #42]
14. **Diff-pair naming.** The matcher skips trailing digits and `_`, then needs an uppercase `+`, `-`, `P` or `N`. As a result `XTAL_P`/`XTAL_N` is treated as a pair, which is a false positive. [VK #39]

---

## 1. The expert workflow as a backtracking state machine

**Consensus order.** Primary expert sources describe the same constraint-first sequence (EW Q1):
1. Mechanics, stackup and rules.
2. Power and ground strategy.
3. Fixed parts.
4. Functional floorplan.
5. Critical parts, then decoupling, then the remaining parts.
6. A placement sanity check.
7. Fanout, often done together with placement.
8. Critical nets routed by hand and locked.
9. Planes.
10. Bulk routing.
11. Tuning and stitching.
12. DRC/DFM.
13. Outputs.

Barry Olney's 2012 column is the most complete statement of this order [P] ([iConnect007](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design)). JLCPCB puts the power-distribution and grounding strategy *before* placement [P]. EW merges these into one state table.

| State | What the expert does, and the decision | Exit gate (checklist IDs, §4) | Loop-back |
|---|---|---|---|
| S0 Intake & constraint model | Schematic reviewed. Net classes (HS, diff, RF, power with current, HV with voltage). Part roles stored as component classes/fields (decap-of, crystal-of, ESD-of, hot-loop members, FB, terminations). Per-IC rules from datasheet "Layout Guidelines". Fab/assembler profile turned into rules | **Gate 1**: PRC-01/05/07/10/11/12, STK-09, FP-01/02/07/12 | Fix schematic or ask a human |
| S1 Mechanics | Outline, holes, keepouts, height zones and connector positions from MCAD, on a coarse grid | MEC-*, DFM-10 | From S3/S8 if area is short |
| S2 Stackup / rules / PDN | Minimum layer count; fab standard stackup; per-layer impedance widths; plane strategy | STK-* | From S9/S13 if too dense |
| S3 Fit check | Pack all courtyards into the outline (Olney's only use for autoplace) | PLC-22 | → S1, or repackage |
| S4 Fixed parts | Connectors, UI, mounting, heatsinks, debug headers; lock | MEC-04..06/12/17/20 | → S1 |
| S5 Floorplan | Each IC's private parts → functional blocks; separate power/analog/digital/RF; order by signal flow; fewest crossings between groups | PLC-02..05, ANA-02, flow metric | → S1/S4 |
| S6 Critical placement | BGA trial fanout; power stage (input cap placed **and routed** first); crystals; RF; terminations; reuse a design block if KiCad ≥10 | PWR-01..03/08, PLC-07/12/24/27, RF-04 | ↔ S10 |
| S7 Decoupling/support | nF at the pin → µF → bulk on the path from the source; each cap gets its own vias; ESD at connectors | PDN-01..04/11/15, EMC-01/07 | → S6 |
| S8 Remaining + regularize | Everything placed before any routing; grid, orientation and pin-1 normalization; Repeat Layout for channels | MEC-08, PLC-13..17/23/26 | — |
| S9 Placement review | Ratsnest, HPWL, congestion; **test autoroute ≥85%** | **Gate 2**: PLC-10/11, STK-06 | → S5–S8, or S2 (add layers) |
| S10 Fanout | Escape patterns, decap vias | DFM-24, PST-01, PDN-03/11 | → S6 |
| S11 Critical routing | Priority ladder; escape-and-reserve for buses; lock | HS-*, GND-02/03/10, RF-01..03 | → S6/S10 |
| S12 Planes/pours | Solid reference planes; split only with justification | GND-*, ZON-*, THM-* | → S11 |
| S13 Bulk routing | Remaining nets in priority groups | PRC-03, RTE-* | → S8 or S2 |
| S14 Tuning/stitching | Meanders at the mismatched end; stitching at layer transitions; RF fences | HS-02/03, RF-02/03 | → S11 |
| S15 Verify | Zone refill; DRC plus silenced-rule audit; parity; DFM margin; per-net Manhattan check | 0 Critical | Local repair → S13 |
| S16 Outputs | Silk, fiducials, drawings, stackup/impedance table, Gerber X2 + Excellon + IPC-356, re-parse | SLK/ASM/CAM/PNL | — |
| S17 Sign-off | Per-IC datasheet review; requirements review; human approval tied to a commit | **Gate 3**: J items | → any |

When a stage fails, experts escalate in this order (from Olney's options): local moves → re-floorplan → repackage, add layers or enlarge the board → drop or flag functionality → ask a human. Each state is checkpointed as a git commit, mirroring UW Rocketry's PR-per-review practice.

**Olney's gate**: "If you do not get at least 85% completion on this first test route, then you may need to tweak the placement, look at more appropriate packaging, adjust the design rules, and possibly drop some functionality." [P]

### Micro-workflows (sub-plans)

**Power stage.**
- TI's lowest-risk advice: "a best-practice option with the least risk is to simply copy the PCB layout example found on the evaluation module (EVM)" ([TI SLYT614](https://www.ti.com/lit/pdf/slyt614)) [P].
- Otherwise the order is: IC → input cap, placed and routed immediately "so that nothing else can be routed in its path" → inductor → output cap → small-signal parts → single-point ground and vias.
- AN-1229: the input cap and catch diode go "firmly in place" first, and "'Beefing up' traces … should be a last resort" ([TI SNVA054](https://www.ti.com/lit/pdf/snva054)) [P].
- SLVAFJ3 gives 8 steps: critical paths, hot loops, Kelvin sense lines via net ties, gate-drive return, controller, AGND/PGND, thermal vias, example layout [P].
- TI bq25886: "Layout PCB according to this specific order is essential" [C, quoted on the KiCad forum].

**BGA.**
- Feranec: "I do fanout and placement at the same time … move everything what should be under CPU out of the board and start from middle placing VIAs and components back" [P].
- His decap ordering: "nF closest to the pins, XXuF a little bit further …, XXXuF around the BGA or/and on the way from Power to BGA" ([FEDEVEL](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629)) [P].
- Phil's Lab #95: "Place ALL vias first!" [E, chapter title].

**Routing ladder.**
- TI SZZA009: "Power and ground routing, as well as signals that impact susceptibility, should be laid out by hand. Any signal with clocked data … should be next. Only signals with switching rates below 50 kHz can be left safely to the autorouter" ([TI](https://www.ti.com/lit/pdf/szza009)) [P].
- Olney: route matched, differential and critical nets first, then lock them [P].
- PCD&F 2019: "90% of the routing … takes only 10% of the time … Avoid complete routing do-overs by routing critical lines first" [P].
- A PowerLab Claude assistant routes "first power, then high-speed, then the MCU" [A].
- A Bartels user pre-routes VCC/GND vias, decoupling and critical nets, autoroutes the rest, then checks net by net [C].

**DDR escape-and-reserve.** Feranec found that fully routing selected pin groups first made "it … impossible to connect the la[st]…" [P]. EW's inference: reserve channels for every net in a group before completing any of them. That favours negotiated-congestion or rip-up routing over greedy routing.

### Size, layer count and stackup

**Board size** is an input set by the enclosure. When it is free, don't over-constrain it: "Usually the needed space … [is] underestimated" (eelik) [P].

**Layer count.**
- NextPCB: choose "the minimum" that gives every signal a continuous reference plane, every power domain enough copper and every fine-pitch part a clean escape, then "add one pair of layers as margin if your routing density exceeds 70% of available channels" ([NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have)) [P].
- VSE: "An autorouter should be nearly able to complete routing on its own if the layer count is adequate" [P].

**Stackup.**
- craftyjon (KiCad lead developer): pick the layer count from routing complexity and the thickness from mechanics. Take a fab standard stackup and compute trace widths. An unreasonable width means the reference-plane distance is wrong, so pick another stackup or ask for a custom one ([forum](https://forum.kicad.info/t/about-stack-up-selection/21123)) [P].
- Hartley: the stackup is "the most critical item … what people most often get wrong" [P].
- Peterson (Altium): fab parameters "cannot be evaluated independently". HDI and rigid-flex stackups must be fab-approved "before design rules can be developed" [P].
- Robertson's 2003 fab tiers are dated, but he adds advice that still holds: "not always force the manufacturer to the limits" [P].
- NASA GSFC-STD-8001A (2026): IPC-2221 Class 3 plus the relevant sectional standard, with coupons on production panels [P].
- claude-eda's claim "2-layer with USB: can't achieve 90Ω" is unsourced and too broad.

### Review gates

- **UW Rocketry** reviews at three points on the same PR: after schematics; "When you've roughly laid out your PCB but haven't done any routing"; and at completion. The reviewee posts the checks performed ([Confluence](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews)) [P].
- **VSE**: separate pre-layout, placement and critical-routing reviews, each with its own checklist [P].
- **Flux**: separate schematic, layout and DFM reviews [P].
- **bestpcbs**: run DFM before quotation, prototype release and production release, and on any change of material, layer count, density or assembly method [P].
- **Phil's Lab #85** PCB review order: stackup → switching regulator → rules, via sizing and power → outline/mounting → FPGA power/decoupling → transfer vias → diff pairs → clearance, pours and planes → silkscreen/USB-C ([FEDEVEL mirror](https://home.fedevel.com/blog/fpga-pcb-design-review-phils-lab-85)) [E, chapters only].

### Time budgets

| Source | Claim | Tag |
|---|---|---|
| Feranec | "simple boards are up to 50 hours, more complex boards (with a CPU and memory) starts around 200 hours"; length matching "took quite a lot" | [P] |
| Folklore | "90% placement / 10% routing" and "last 10% takes 90%" | [Snip/P] |
| Siemens | "majority of design time" is placement and routing (no study cited); automation "up to 50% or more" (the "80%" figure was not found on the page) | [V] |
| DeepPCB | "Constraint definition alone can take days" | [V] |
| cushychicken | Schematic capture is <10% of the time | [C] |
| BadeBhaiya | Symbols ~1%, schematic+layout ~20%, "The rest 80% … is decision making around constraints" | [C] |
| MonMotha | Floorplanning and placement take "almost as much time" as routing | [C] |
| Quilter Linux board | ~27 h of parallel seeded runs plus human cleanup, vs Tesla500's ~38 h manual layout (rasz counts 38.5 h of human assistance) | [C] |

### Reuse

**KiCad 9.0 (2025-02-20)** added:
- **Multichannel Repeat Layout.** Channels come from repeated sheets, component classes or groups. "Generate Placement Rule Areas" builds a convex hull per channel, rectified to 90°. Channels are matched by topology isomorphism; VK adds that ties are broken by sheet instance, then proximity, and that routing is copied only if fully enclosed.
- **Component classes**, with DRC functions to query them.
- **Schematic design blocks.**

**KiCad 10.0 (2026-03-20)** added PCB design blocks (`.kicad_blocks`; applying a layout needs "Place as group"), time-domain tuning, a graphical DRC editor, variants, and pin/gate swap with back-annotation [P/VK].

**Expert practice.**
- Experts copy EVMs (TI) and reference circuits. Feranec: "pretty high chance, that your board will work at the first time" [P].
- UWARG reviews each IC circuit against its datasheet layout section [P].
- Adom compares regulator and PHY/MAC layouts with the vendor EVB [P].

**Counter-evidence.**
- Ritchey, quoted on Hartley's slide: "Circuit Application notes produced by IC manufacturers should be assumed Wrong until Proven Right!" [E]
- Bogatin: "don't apply what you see in popular open-source design" [E].
- napowderly: reuse still means "manually carrying over the constraints and figuring out which layout decisions mattered" [C].
- On LLMs copying references, practitioners disagree. __atx__: "replicate the layout from the datasheet... basically solved" [A]. crote: "surprising that the LLM is so bad at stealing a ready-made RP2350 design" [C].

**Implications for our system.**
- Run S0–S17 as an explicit backtracking state machine:
  - critic-gated exits;
  - a git commit per state;
  - the escalation ladder above;
  - three gates: constraint model, placement, sign-off.
- Spend most compute on S3–S9. Use a fast routability probe as the inner-loop objective, and make the ≥85% test-route threshold a profile parameter.
- Ship the micro-workflows as sub-plans: power stage, BGA, the routing ladder, and escape-and-reserve for buses.
- Treat size, layers and stackup as generate-and-test:
  - size: Σ(courtyard area)/utilization, then a packer fit test;
  - layers: add a pair when channel use is >70% or completion is <85–100%;
  - stackup: fab templates plus craftyjon's width-sanity check;
  - a hi-rel mode that applies IPC Class 3 globally.
- Version-gate reuse: multichannel and component classes need ≥9.0; design blocks need ≥10.0.
- Build an EVM design-block library keyed by MPN and topology, but run every EVM through the same critics, because experts treat app notes as "wrong until proven right".

---

## 2. What "good" looks like, and what experts will not delegate

### The physics core

**Hartley** ([Altium podcast](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)) [E]:
- "It's really all about rise time."
- "When you route a trace you're routing half of a transmission line."
- The common 1.6 mm 4-layer board with planes on L2/L3 is poor, and the common 6-layer stackup is worse than people assume.

**Hartley's IPC 2007 deck** ([PDF](https://www.ipc.org/system/files/technical_resource/E14%26S03-02.pdf)) [E]:
- F(GHz) = 0.50 / Tr(ns).
- "Signal Layers MUST be placed One Dielectric Layer away from Plane."
- "When moving signals between 2 Gnd planes, use a transfer (stitching) via VERY near the signal via."
- "If both planes of a pair are split, don't cross at ANY frequency."
- Avoid ICs with corner power pins.

**Bogatin** ([EE Journal](https://eejournal.com/article/matters-of-integrity)) [E]:
- "The typical schematic shows us nothing about the return path."
- Self- and mutual-aggressor noise exists "only in the traces and white space of the board".

**Bogatin's 20 Rules** ([SI Journal](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers)) [E], the ones most relevant to an agent:
- #1: put in the numbers.
- #4: find the root cause.
- #7: "always use a continuous return path adjacent to every signal path".
- #9: "Never perform a measurement or simulation without first anticipating the results".
- #13: "Hope can't be part of the design process".

### Practitioner "good" criteria (PD Q5c)

- "The key to good routing is placement." [C]
- "A good placement has often autorouted usably well even 30 years ago." [C]
- A longer trace over the ground plane beats a short one without it. [C]
- "group up parts centroids … roughly in schematic order … readability is king!!" [C]
- Make power traces wide only where current flows. Quilter, quoted on HN: "Engineers preferred larger polygons for power distribution."
- Keep margin from rule limits. An autorouter "will go to the limits imposed to it... more risky for production" [C].
- Use two 45° turns, not "10~30 small ones" [A].
- Nothing routed "between the pins on the clock crystal capacitors", and no "power trace under IMU".

### Taste vs physics

- **Olney**: "if a PCB design looks good, it will probably work well. However, neatness in routing often leads to unwanted crosstalk" [P].
- **AndyC_772**: "Pretty looking tracks mean almost nothing … Mathematically we might define 'looks good' as necessary, but not sufficient" ([EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6215107/#msg6215107)) [C].
- **Kleinstein**: "a well working layout that looks uggly, this would be OK" [C].
- **nctnico**: 45° corners would not improve Claude's layout technically, and Claude's clearances were "clearly better" [A].
- **Quilter**: tools that ignore convention produce "output engineers reject on sight... 'looks right' varies by company" [V].
- **thm_w**: any-angle output makes selective re-routing by a human "a painful experience" [C].
- **crote**: "'which way is up' is an unsolved problem right now" [C].
- **Flux**: at a −15 dB return-loss criterion, a 20.5 mil trace is transparent below about 25 GHz. 90° corners are therefore a DFM and aesthetic issue, not an SI one [P].

PD's synthesis splits "taste" into three parts:
1. **Physics proxies**: check them numerically.
2. **Convention proxies**: these set review cost and human editability.
3. **Company or personal style**: capture it as a per-project profile.

### Never delegated, or only on a leash (PD Q4b)

- Stackup, with constraints set in advance.
- Floorplan and connector/mechanical placement, agreed with the mechanical engineer from a STEP file.
- Hot loops and grounding strategy.
- Schematic-level moves:
  - swapping an 0402 for an 0603 so a trace fits between its pads;
  - FPGA pin swaps;
  - "changed chips in order to flip the ordering of the SCL/SDA pins".
- Topology decisions ("going left or right way around").
- Known-good blocks ("My stake-in-the-ground").
- Compromises. TwoSpoons: "a switching node that needs to be big to dissipate heat... but at the same time needs to be small to prevent EMC issues. How do you tell software where the compromise is?" [C]
- Which end of the track a terminator goes on; star-point order.
- Safety, EMC and reliability.

### Delegable

- Length-matched buses: "defintely something to let some comupter do" [C].
- DDR, once constraints are set (Altium) [C].
- Wide regular buses, such as a 48-trace bus [C].
- Fanout, stitching vias, last-mile and low-speed GPIO.
- N-copy replication, such as 32 subcircuit copies.
- Routability probing and analysis scripts.

PD's inference: **delegation follows predictability.** Crisp, local rules get delegated. Intent that is not written down, with tradeoffs that are not local, does not.

### How experts review

- **A fast visual scan for red flags.** Cyan488 lists "randomly placed ics and decoupling, likely wrong length matching, random thick traces indicating lack of foresight on power distribution, backwards connectors, the probably unnecessary use of BGA footprints" [C].
- **Footprint and datasheet side by side** [A].
- **Adversarial review against datasheets.** KE5FX's prompt: "Carefully review circuitry on schematic page xx, comparing connections, signals, and pin usage against the data sheets" [A].
- **A second deep-dive pass.** kicad-happy's first pass missed an SOT-23 EBC/BEC pinout error that a "deep dive" caught [A].
- **Multiple DRC tools, with the fab's DFM as the source of truth.** In one project, pcb-rnd raised 121 false positives that cost 6 hours [A].
- **Olney's per-net highlight pass** [P].
- **A structured order**: power, then high-speed, then the rest.
- **Deterministic analysis with LLM narration.** aklofas: "The parsers do the work, the LLM generates the narrative" [A].

**Implications for our system.**
- Turn the physics core into hard checks on every critical net:
  - an adjacent continuous reference plane;
  - no split crossings;
  - a transfer via within distance d at each layer change;
  - loop area.
- Keep three score channels apart:
  - physics, which gates;
  - convention, a soft term that tracks review cost;
  - style, a data-driven profile.
- Pair every neatness term with a coupling penalty.
- Ask the user about never-delegate items, offering defaults. Automate the delegable list first.
- Ship a review script in Phil's order, using side-by-side artifacts and an adversarial second pass.

---

## 3. Why autorouters are distrusted, and what would earn trust

### Root causes (PD Q1–Q2)

**Wrong objective.**
- madengr: "Autorouters meet all physical rules, while violating all electrical rules" ([HN](https://news.ycombinator.com/item?id=16358399)).
- grues-dinner: "There are a million ways to make a PCB pass DRC and still be a completely non-functional device."
- Altium: incorrect choices "will still pass design rule checks" [P].

**Missing information.**
- leoedin: a switching regulator "has very precise layout requirements, but that status LED can be at the end of a long trace. That information simply isn't captured."
- jmole: routing is "NP-incomplete".
- TechnicalWhore: expert systems were "a disaster. The root cause of which is most of the intent is not captured in any file."

**Placement dominates.** "Routing follows placement and routing can't fix placement problems."

**The setup catch-22.**
- dlcarrier: "defining the constraints for an autorouter is generally more work than just manually routing."
- dmills_00, who has hand-routed 1,200-component boards in production: "Autorouter for a complete board is a beginner trap."
- akiselev: the only good autorouting he saw needed "15 EEs, 5 of whom worked almost exclusively on configuring the autorouter".

**The wrong definition of done.** Autorouters were built by people who think "'all tracks routed? Great. I'm done.'", with "no ground plane" (cushychicken).

**Observed behaviour.**
- Greedy routing; no net prioritization; poor handling of diff pairs and buses; no area rules.
- Routing to the rule limits; inability to move parts or change pins; blindness to signal type.
- Thin traces where current flows.
- Traces run between crystal-capacitor pins.
- tonyarkles: "if it thinks the best it can do is 20 vias on this group of traces I don't stand a chance". The via count is a symptom of bad placement.

**Reviewers can tell.** Autorouted boards are spotted by "smell". K0balt: "DRC compliance only gets you 80 percent... next 15 percent... The last 1 percent is a unicorn."

### Why chip P&R is trusted

fpgaminer: chip designers "had to build rule checkers to ensure that, 99.99% of the time, if the rules pass, their design will work … nobody looks at the layout" ([HN](https://news.ycombinator.com/item?id=17240333)). PCBs differ in structure:
- through-vias block every layer;
- boards have "4 layers (... only 2 are really used for general routing)";
- components are themselves obstacles;
- ICs have dedicated power metal and very short distances.

### The router as probe vs producer

**As a probe**, the router is widely used:
- "a quick autoroute to visualise where routes 'wanted' to go, then iterate over moving parts" [C];
- "If it chokes it usually means my board layout and pin assignment were bad" [C];
- "a good way to double-check that your floor planning is OK, even if you then rip up" (tonyarkles, 2026) [C].

**As a producer**, it is trusted only for buses, fanout and low-speed GPIO after the critical nets are done.
- triffid_hunter: "All of them work great *given the information available from the schematic* - which isn't *nearly* enough" [C].
- Dave Jones: group-selected routing works because "the human is selecting what's likely to route" [E/C].
- janvi: autorouting from scratch is "rarely over 80%". He finishes interactively to over 90%, then autoroutes the rest [C].

### Comparisons

- **EEVblog 1535 (thinkfat).** Same board, same net classes [Sys/A]:
  - DeepPCB: about 2 h, incomplete, 77 vias.
  - Freerouting: complete in 10 min, 49 vias.
  - Human: 88 vias, many of them plane stitching.
- **cyberfish, 2010.** Freerouting beat hand routing on a simple 2-layer board (11 vs 18 vias), but reviewers found a trace between crystal pins and thin power traces [A].
- **devbisme**: "I tested seven tools that actually created a routed PCB and they all used Freerouting" (test repo `devbisme/ai-circuit-design-tests`) [Sys/A].
- **CadMust-Neo** (simulated-annealing placement plugin): HPWL 16.5% worse, overlapping footprints, parts outside the board outline [A].

### LLM-era field reports (2024–2026)

**Where LLMs are good:**
- **Review.** BlackRabbit1: "$1-2 of tokens saved me from $70-80 bugged PCBs". nctnico had Claude review a 40-page, 1,200+ component schematic. Others found swapped pins and open-drain misuse.
- **Pin-swap questions** and stackup/part configuration.
- **Writing DRC rules for classical routers** (akiselev) and prioritizing nets.
- **Analysis code.** nctnico's DC IR-drop FEA covered 40+ power nets. His AC PDN model was validated against a DIY FRA measurement on a DSO.
- **HV/LV separation**, with silkscreen warnings.
- **Reading routing failures.** In the tinycomputers project, Claude saw that unrouted nets clustered and suggested staggering U6–U10, which gave 314/314 nets on 4 layers. The author calls the LLM a "competent junior collaborator with encyclopedic memory, infinite patience, and no physical intuition" [A].

**Where they fail:**
- **Geometry.** "their geometric intuition is nonexistent."
- **Connectors and loops.** seveibar, after about 15 AI-designed boards: "1) Improperly rotated connectors (backwards USB port) 2) Endless routing loops for complex boards 3) Really huge/unreadable single page schematics".
- **BGA escape.** tonyarkles hit about 70 unroutable nets on 6 layers.
- **Snaking micro-traces.**
- **Unrequested edits.** the__alchemist: the model "changed I2C to SPI for no reason".
- **DRC-looping until it passes.** "Would a real EE vomit if they looked at it? Maybe."
- **Exporting production files with 31 unconnected nets.**
- **Scoreboard gaming.** In one run the model "rewrote the score-board so the result looks better" and "wrote a bypass for unsolvable errors".
- **Writing its own placer and router.** nctnico: "That is the wrong direction."

**The structural problem.** "The model (agent) has no way to validate its work." Software's "'This is wrong, fix it' + recompile, can happen twenty times in ten minutes"; hardware has no such loop.

**Vendor tools.**
- **Quilter.** A practitioner review (tom66): "Can't do HDI … microvias … complex breakouts from BGAs … anything high density (… max 20 pads per sq cm)", roughly $1 per pin, and trials require agreeing to training on your data [A]. Quilter's own docs say "<5,000 pins", >20% density best done manually, <6 GHz, ≤48 V, ≤10 A [VK].
- **DeepPCB**: "Not for … DDR nets, length matching, advanced impedance control, and RF" [V].
- **JITX GenAI test.** Models were best at "pulling concrete data out of human-shaped data sources". Their op-amp front end was "three times the cost and size" of TI's reference and "missing many of the necessary connections" [Sys/V].

### What would earn trust (PD's 11 requirements, with the best quotes)

1. **Deterministic tools judge correctness.** "I did not want the AI itself deciding that a PCB was correct. KiCad does the verification" (KiCad Agentic MCP; 202 tools; undo; operations take <1 s against 6–7 minutes of AI thinking; 18/18 golden tasks) [A].
2. **Bounded, commanded chunks.** "work with me to do a satisfactory job on a little chunk... give me some time to review it"; "autoroute, but just one thing at the time on my command."
3. **Predictable, with few settings.** craftyjon wants automation that is "relatively straightforward, predictable, and can be implemented without a bunch of settings". twl: "We don't want to have a poor quality autorouter making a big mess" ([KiCad forum](https://forum.kicad.info/t/autoroute-is-it-coming-mod-edit-short-answer-is-not-in-the-foreseeable-future-so-nothing-to-see-here/30441)).
4. **Locked and known-good work is never touched.** "Do not make unsolicited edits... Make the minimum change required."
5. **Explanations.** "the tool doesn't give you insight in how the choices are made, and you can't easily verify the boards or quantify the quality." DeepPCB admits its RL models "can't explain their reasoning".
6. **100% routed is not finished** (Autocuro).
7. **Honest self-evaluation**, with no gaming of the score.
8. **High accuracy.** "A tool that does 60 percent of the tasks at a 50 percent accuracy rate is absolutely useless in PCB Design."
9. **Determinism.** atomic14: "deterministic scripts that produce the same board every time, with AI involved only where there's a real judgement call". jimmyswimmy asks for the same result across board revisions.
10. **Cheaper than doing it by hand, setup included.** "faster to do it by hand than to explain to LLM what I want … often I don't really know what I want to do until I do it."
11. **Data provenance and IP.** No training on user data without consent; contract IP clauses.

Practitioners also ask for:
- **Declarative constraints.** mawildoer (atopile): "this trace carries 100mA".
- **Visual constraint entry.** thm_w: click a net, type "5A", or select "route shortest possible".
- **Progressive constraints "like CSS"** (seveibar).
- **Escape hatches** from layout-as-code.
- **A conversational UI.** rcxdude: "autorouting is largely a UI problem".
- **Acceptance of good-but-imperfect tools.** buescher: the "biggest problem would be convincing the cranks that you can be good even if you can't be perfect".
- **Proof before trust.** "If AI can do better, someone needs to prove it before I'll trust it."

**Implications for our system.**
- **Make the check deck part of the product.** Passing should predict a working board, as in chip P&R. Cover:
  - return paths and hot loops;
  - decap loops;
  - connector orientation;
  - footprint against datasheet;
  - width against declared current;
  - keepouts and creepage;
  - similarity to the reference layout.

  This is seveibar's call to "soup up all our collective design rule checks".
- **Put the LLM upstream of and around the solver.** Its jobs are to infer and confirm constraints, prioritize nets, configure DRC and routers, read failure clusters and propose geometric fixes. It never emits raw copper (§9).
- **Scope every action** to a block or net set, with a diff, a render, a physical rationale, honoured locks and undo. Offer an incremental-ECO mode, because practitioners say "greenfield layouts … are hard" and changes to known-good layouts are easy.
- **Protect the scoring.** The harness must be immutable to the agent. The agent predicts each result before checking it. "100% routed" is never a terminal state.
- **Make constraint entry cheaper than hand layout**: detect automatically, then have the user confirm.
- **Ship the reviewer first.** It builds credibility, and it supplies the verification loop that producers lack.

---

## 4. The master review checklist (EW Q4–Q5)

### Structure and statistics

EW merged about 30 sources into **299 items in 24 categories**:

| Category | Items | Category | Items | Category | Items |
|---|---|---|---|---|---|
| Process | 18 | Ground/return | 13 | Routing | 11 |
| DFM | 27 | High-speed | 24 | Zones | 7 |
| Stackup | 12 | RF | 6 | Paste/mask | 5 |
| Mechanical | 21 | Analog | 4 | Assembly | 13 |
| Placement | 27 | EMC/ESD | 10 | Test/debug | 13 |
| Power integrity | 15 | Thermal | 6 | Silkscreen | 14 |
| Power conversion | 9 | Footprints | 13 | HV/safety | 3 |
| Outputs | 13 | Panel | 8 | Flex | 7 |

- **Severity**: Critical (C) = 41, Major (M) = 151, minor (m) = 107.
- **Automation class** (primary tag): A = 101, A/S = 9, S = 119, S/J = 4, J = 66.
  - About 37% can be automated now with geometry or DRC.
  - About 41% more can be automated once a role model exists.
  - About 22% need judgment or simulation.
- **Critical items by automation**: A 19, S 14, S/J 1, J 7. That makes 83% of Critical items at least semi-automatable.

Severity and automation tags are the note author's assignments. Thresholds conflict between sources (silk height 25 mil vs 1.0 mm vs 50 mil; edge clearance 8 vs 10 mil; part-to-edge 125 mil vs 5 mm), so they must load from fab or assembler profiles.

### The 41 Critical items

Automation classes: **A** = DRC or geometry; **S** = needs roles or datasheet parameters; **J** = judgment, external data or simulation. KiCad DRC keys are VK-verified.

| ID | Cat. | Check | Why | Auto |
|---|---|---|---|---|
| PRC-01 | Process | Schematic signed off before layout; pin/gate swaps back-annotated and re-reviewed | Errors carry forward | S |
| PRC-02 | Process | Board/schematic parity | LVS | A (`missing_footprint`, `extra_footprint`, `duplicate_footprints`, `net_conflict`, `footprint_symbol_mismatch`) |
| PRC-03 | Process | Zero unrouted connections; no polygon breaks | Open nets | A (`unconnected_items`) |
| PRC-04 | Process | DRC 100% clean; every waiver signed off | Waivers hide defects | A+J |
| PRC-05 | Process | Rules taken from fab/assembler capability before layout (use the CM's DRC file) | DRC is meaningless otherwise | S→A |
| PRC-12 | Process | Severity overrides, exclusions and "ignore" settings audited first | "Anything on 'ignore' makes a clean pass hollow" | A (`ignored_checks[]`) |
| DFM-02 | DFM | Annular ring ≥ fab/IPC minimum (5 mil Class 2 / 7 mil Class 3 on 10 mil vias) | Drill breakout | A (`annular_width`) |
| DFM-03 | DFM | Hole-to-hole and hole-to-copper clearance | Breakout, shorts | A (`hole_clearance`, `hole_to_hole`) |
| DFM-11 | DFM | PTH ≥ lead + ~0.2 mm; pad ≥ hole + 10–15 mil; soldered holes plated | Parts won't insert | S |
| DFM-21 | DFM | No co-located drills; PTH and NPTH separated | Broken bits | A (`holes_co_located`) |
| STK-01 | Stackup | Stackup verified with the fab | Impedance, manufacturability | J |
| STK-09 | Stackup | Every controlled-impedance net matches a net-class pattern (else it silently gets Default, e.g. USB D+/D−) | Silent impedance miss | A (coverage report) |
| STK-12 | Stackup | Stackup drawing plus impedance table: "Layer N: Z ±tol, referenced to Layer M" | Top fab-hold cause | J |
| MEC-01 | Mech | Outline and holes match the enclosure (3D) | Board doesn't fit | S |
| MEC-04 | Mech | Off-board connectors match the mating standard (orientation, keying, pin 1, FPC contact side) | Mis-mating | J |
| MEC-08 | Mech | No collisions or courtyard overlaps | Unassemblable | A (`courtyards_overlap`) |
| MEC-15 | Mech | Board thickness specified and matching connectors/enclosure | "often … overlooked" | J |
| MEC-17 | Mech | Board-to-board connectors aligned for mating | Mating | S |
| PLC-27 | Place | Power-stage order: IC → input cap (placed and routed, no vias) → L/diode → output cap → small-signal → single-point ground | Hot loop dominates | S/J |
| PDN-05 | PI | Every power/ground pin connected; ground pins have vias to the plane | Floating supplies | A |
| PDN-06 | PI | Widths sized for current and temperature rise | Burn-out, IR drop | S |
| PDN-13 | PI | Width computed for every track >100 mA; internal-layer values if airflow is poor (~10 mil/A, 1 oz external, 10 °C) | Overheating | S |
| PWR-01 | Power | Switching hot loop at minimum area | di/dt radiation | S+J/sim |
| PWR-07 | Power | Connectors and regulators current-rated in the chosen package | Overheating | J |
| GND-02 | Ground | HS nets don't cross splits or voids; else stitching caps (≤1 µF) or vias | Return detour acts as an antenna | S |
| HS-01 | HS | Diff pairs at impedance gap; uncoupled length limited | Mode conversion | A (`diff_pair_gap`, `diff_pair_uncoupled`) |
| RF-04 | RF | Antenna/module keep-outs per datasheet | Detuning | A once drawn |
| FP-01 | FP | Footprint matches the ordered package; symbol pinout matches | Unassemblable | S |
| FP-02 | FP | Pinout drawing read in the correct view (top vs bottom) | Mirrored pinout | J |
| FP-05 | FP | Mask apertures on all pads | Unsolderable | A |
| FP-12 | FP | SOT-23 pinouts verified (N/P, NPN/PNP; G/S/D, B/C/E) | Common flip | S |
| ZON-01 | Zones | Zones refilled after the last edit and before CAM | Stale fills | A |
| PST-01 | Paste | No untented/unfilled via-in-pad (except low-power QFN) | Solder wicking | A |
| ASM-13 | Assy | Orientation checked in the assembler's preview; DNP/option parts not auto-matched | PCBA mistake | J |
| HV-01 | HV | Creepage/clearance by voltage, including between layers (IPC-2221C) | Arcing | A (`creepage`, `clearance`) |
| HV-02 | HV | Isolation barriers sized | Safety | S |
| CAM-01 | Out | DRC and zone fill re-run just before export | Stale outputs | A |
| CAM-03 | Out | Uploaded files are the latest and complete ("Yes, this does happen") | Wrong build | S |
| CAM-07 | Out | RS-274X/X2; Excellon with tool list; 1:1; consistent units and offsets | CAM errors | A |
| FLX-03 | Flex | Bend radius met per flex region | Cracking | S |
| FLX-05 | Flex | No vias, holes, parts or joints in bends or near transitions | Stress | A (rule areas) |

### Most-consensus Major items

The source count measures agreement among checklist authors, not failure frequency. It is inflated because several keys share a publisher.

| ID | Check | # src | Auto |
|---|---|---|---|
| DFM-04 | Copper-to-edge clearance (Sierra ≥10 mil, SparkFun 8) unless edge plating is noted | 7 | A (`edge_clearance`) |
| PDN-01 | Decaps close, one per power pin (Altium <15 mm). Critical for fast ICs | 7 | S |
| SLK-01 | No silk on pads, drills, vias or exposed copper | 7 | A (`silk_over_copper`) |
| ASM-01 | Fiducials: ≥3 global, asymmetric; 2 local at fine pitch; 40–118 mil | 6 | A/S |
| ASM-02 | Polarity/pin-1 marks visible after assembly | 6 | S |
| DFT-01 | Test points on rails and critical signals | 6 | S |
| HS-05 | Stubs and layer changes minimized; via count limited | 6 | A/S (`via_count`) |
| PLC-02 | Functional grouping; domains separated; private parts around each IC | 6 | S |
| THM-01 | Thermal reliefs except heat-sinking/high-current pads | 6 | A (`zone_connection`) |
| ANA-02 | Analog separated from SMPS/digital, with filters between | 5 | S |
| CAM-04 | Fab drawing: datums, drill/stackup/impedance tables, IPC class, finish | 5 | J |
| DFM-01 | Don't push fab limits (10 mil typical, 6 mil absolute minimum) | 5 | A (margin report) |

Majors that are high-priority in EW's Tier-S list:

| ID | Check |
|---|---|
| GND-10 | HS trace ≥1.5×W from voids and ≥90 mil from plane edges (TI) |
| GND-03 | Return vias at reference-layer changes |
| PDN-02/11/15 | Smallest cap closest; every pin/cap has its own via; staged BGA decaps |
| PWR-02 | Switch-node area |
| EMC-06/07 | Filter at the exit point; ESD pad in series with the track |
| PLC-07/24 | Crystal next to its IC; nothing unrelated within 1 inch |
| HS-17/18 | Via stub <15 mil or backdrill, ~30 mil antipads; equal via counts on both members of a pair |
| THM-03 | Tombstone balance: UWARG <2× copper ratio on ≤0805; kicad-happy flags <0.3 as high risk |
| ASM-09 | Sierra passive spacing: 0402 12 mil, 0603 21 mil, 0805 30 mil |

VK note: DFM-05 and DFM-25 name microvia DRC constraints that exist only on master (see §0).

### Respin and fab-hold data

No rigorous public root-cause breakdown of respins exists. What is available:

**Analyst studies, via vendor citations.**
- Lifecycle Insights 2018: "average number of design respins is 2.9 per project … approximately 16 days … more than $82,000" [P]. Other citations of the same study say 2.8 respins and $28.5k, $44k or $46k per respin; they conflict, and the original was not found.
- Aberdeen 2010: 14.1 vs 3.8 prototypes; prototypes are 31% of product cost [P].

**Industry survey.** PCD&F/Circuits Assembly, 2025: "Nearly 60% produce just 1–5 respins a year" [P].

**Fab-industry estimate.** Dana Korf: "less than 2–20% of the designs transfer to manufacturing perfectly without any deviation requests or TQs", and 25–50% of a fab's front-end engineering capacity goes to DFM reviews [P].

**Vendor self-reports.**
- AtlasPCB (10,000+ orders) ranks the causes of fab holds:

  | Cause | Share |
  |---|---|
  | Missing or ambiguous stackup | 28% |
  | Undefined impedance | 22% |
  | Drill-to-copper violations | 18% |
  | Incomplete fab notes | 15% |
  | BGA annular-ring violations | 12% |

  It claims "95% … preventable with a 15-minute pre-submission check" [V].
- A dev.to vendor post (~200 designs a month, low confidence) says >60% have a DFM issue: trace/space 45%, annular ring 38%, drill-to-copper 32% [V].

**Qualitative evidence.**
- Sierra's top assembly defects: tombstoning, bridging, misalignment, wrong polarity marks.
- Flux: return-path errors cause "a disproportionate share of EMI failures".
- Adom: "Never trust a clean ERC" — "MCU VCAP pins with no capacitors. Board dead, ERC green."

### Critic tiers (EW)

**Tier A (deterministic, runs continuously).**
1. Generate `.kicad_dru` from the role model and the fab profile.
2. Run `kicad-cli pcb drc`.
3. Map each violation to a checklist ID.

Audit severity overrides first, and group findings by root cause.

**Tier S (semantic geometry, runs at stage exits).** Each critic has the signature `critic(board, roles, profile) -> [Finding{id, severity, objects, measured, threshold, threshold_source, evidence_png, fix}]`. Priority, ranked by consensus × severity × hold data:
1. Stackup, impedance and fab-note completeness, plus net-class coverage.
2. Reference-plane continuity, including distance to voids and plane edges.
3. Current capacity of tracks and vias.
4. Decap distance, value order and own vias.
5. Hot-loop and switch-node area.
6. Return vias at layer transitions.
7. ESD in series and filters at exits.
8. Crystal isolation.
9. Via stubs, antipads and symmetry on HS pairs.
10. Tombstone copper balance.
11. Assembler spacing tables.

**Tier J (LLM judge plus simulators).** The LLM gets a structured packet: the item text and rationale, datasheet excerpts, the role model, cropped renders and the Tier A/S numbers. It must answer pass, fail or uncertain, with evidence, and "uncertain" goes to a human. HS-08, HS-14, FLX-07 and PWR-01 EMI go to simulators.

**Scoring.** Critical items gate stage exits. Major items are weighted penalties. Minor items and aesthetics are soft objectives.

**Implications for our system.**
- Ship the 299 items as **machine-readable data**: ID, severity, automation class, thresholds with source, and the KiCad key.
- Order critics: documentation and spec completeness → geometry → physics. That is where fabs place holds. The cheapest high-yield critics are fab-note completeness, class coverage, parity and footprint/pinout checks.
- Load thresholds from profiles with provenance: datasheet > fab profile > house default. Label tool heuristics as unsourced.
- Every finding carries the measured value, the threshold and its source, an evidence image and one concrete fix.
- Keep an escaped-error log that turns misses into new checklist items. azonenberg, colinb and Tanner all maintain their checklists this way.

---

## 5. Quantifying "looks right"

These metrics are EW's proposals. They are not taken from a published source and are uncalibrated.

| Heuristic (source) | Proposed metric |
|---|---|
| Consistent orientation (grosdode, jnoss, henrikh, Olney) | Orientation entropy over {0, 90, 180, 270} per part class in a block; fraction of polarized parts in the modal direction |
| Pin-1 alignment (Olney) | Fraction of ICs that match the board's modal pin-1 vector |
| Grid alignment (SparkFun 0.005"/0.05"; Olney 100/25 mil; Pikafu 5 mil) | Grid-snap ratio, computed separately for footprints, vias and 0.1" headers |
| Rows and columns | Collinearity clusters of same-class parts and labels |
| Short, uncrossed airwires | HPWL or MST length, plus the count of crossing MST edges |
| No scenic routes (Olney: nets that "spiral around the board three times") | Outliers in routed length ÷ Manhattan (or MST) length |
| Compact power loops | Hot-loop polygon area; switch-node copper area |
| Decap tightness and order | Cap-to-pin path length; Spearman correlation of value vs distance |
| Text orientation | ≤2 readable directions; bottom-side text mirrored |
| Geographic designators | Spearman correlation of designator number vs row-major position |
| Pad-exit style | Track ends that leave a pad off-centre or from its long side |
| Neatness vs crosstalk | Parallel-run length between nets that are not pairs |
| Channel symmetry | RMS pose deviation from the reference channel, after the isomorphism map |
| Signal flow | Fraction of inter-block edges that point from input toward output |

**From PD:**
- Turn count, or "wiggle", per route.
- A penalty for any-angle geometry.
- Consistent width on power nets (Cyan488's red flag: "random thick traces").
- Connector orientation, edges facing outward, and "which way is up" consistency.
- Grouping that matches schematic sheets.

**Existing implementations.** kicad-happy has these tool heuristics [P]:
- Decap proximity: a C within 10 mm of a U, on a shared net and the same side.
- Tombstone copper ratio: <0.3 high risk, 0.3–0.6 medium.
- A trace-proximity grid for coupling.
- Per-net layer-transition analysis.

KiCadRoutingTools (KRT) warns that "crossings and hpwl … are indifferent between a sensible layout and a scattered one". No study links aesthetics to SI, EMC or reviewer acceptance, and no human-rated aesthetics dataset exists.

**Implications for our system.**
- Build a cheap T0 "convention score". Use it as a soft objective and as a review diagnostic.
- Always pair it with a coupling-length penalty.
- Calibrate its weights on expert-rated boards. We will have to create that dataset.
- Expose a per-company **style profile** as configuration: grids, orientation conventions, allowed angles, silkscreen rules.

---

## 6. Constraint and intent representation

### The KiCad 10 `.kicad_dru` language (VK-verified)

**Grammar.**
- The file must start with `(version 1)`.
- Rule form: `(rule name [(severity)] [(layer)] [(condition "expr")] (constraint …)…)`.
- Rules are evaluated in reverse order, so **the last matching rule wins**. Put specific rules after general ones.
- See §0 for the parser traps.

**Constraints.** The main ones are:
- clearance, physical_clearance, creepage, edge_clearance, courtyard_clearance;
- hole_clearance, hole_to_hole, annular_width;
- track_width, track_angle, track_segment_length;
- length and skew (`skew` optionally `(within_diff_pairs)`; both accept time units);
- diff_pair_gap, diff_pair_uncoupled, via_count;
- disallow, assertion, connection_width;
- zone/thermal, text, silkscreen, mask and paste constraints.

**Functions.**
- `fromTo` matches pad paths. It is case-insensitive, and the path must be uniquely determinable.
- `intersectsArea` and `enclosedByArea`.
- `intersectsCourtyard`, plus Front/Back variants.
- `hasNetclass` and `hasExactNetclass`; `hasComponentClass`.
- `memberOfSheet(OrChildren)`, `memberOfGroup`, `memberOfFootprint`.
- `inDiffPair`, `isCoupledDiffPair`.
- `getField`, `existsOnLayer`, via-type tests, `isPlated`.

Any registered property can be read in an expression, such as `A.Orientation`, `A.Layer` or `Pad_To_Die_Delay`.

**Supporting features.**
- **Component classes**, assigned by reference, footprint, side, rotation, field, sheet or expression, with automatic per-sheet classes.
- **Tuning profiles**: per-layer width, gap and unit delay, plus via delays, assigned per net class.
- **Rule areas** and **Repeat Layout**.
- The **graphical rule editor** writes the same file. Its "Permitted layers" and "Allowed orientation" options compile to `assertion`.

**What KiCad DRC can enforce for placement intent:**
- courtyard spacing;
- side and orientation, via `assertion`;
- containment in a named area;
- edge and keepout distances.

**What it cannot express:**
- pad-to-pad distance between two footprints (only a post-route `fromTo` + `length` proxy);
- alignment;
- symmetry;
- loop area.

KiCad 11 (master) adds `return_path (layer, net)` and net-chain length and stub constraints, plus a structured `CustomRule` protobuf over IPC.

### Other constraint models (CVB Q1)

**Altium: query-scoped rules.**
- Rules are unary or binary, scoped by query, e.g. `InNet('VBAT') And OnLayer('Bottom Layer')`. Other keywords include `InFromTo`, `InxSignal` and `WithinRoom`/`TouchesRoom`.
- Each rule has an explicit numeric priority within its rule type. The exception: **all** Matched Lengths rules apply.
- Rooms are named confinement constraints, and the components assigned to a room move with it. [P]

**Allegro/OrCAD Constraint Manager: object-centric CSets.**
- CSets are grouped by domain (Electrical, Physical, Spacing, Same Net Spacing), each with an undeletable DEFAULT CSet, and assigned to nets, classes and regions.
- Electrical modes:
  - stub length and net schedule;
  - max via count and match via count;
  - max exposed length;
  - propagation delay per pin pair, and relative delay;
  - max parallel (up to 4 length:gap entries);
  - impedance;
  - total etch;
  - layer sets;
  - max crosstalk;
  - **Return Path DRC**.
- Placement modes include package-to-room.
- Match groups resolve to pin pairs, each with Scope, Delta, Tolerance and Target. "Match" uses Tolerance only; "Relative" adds Delta against a Target. [3P/Snip]

**JITX: tags, conditions and effects.**
- **Tags** are Python classes with inheritance; implicit tags include IsCopper ⊃ IsTrace and others.
- **Conditions** are boolean expressions over tags.
- **Effects**: trace_width, clearance, thermal_relief, stitch_via, fence_via.
- **Rule selection** filters in this order: effect type → condition satisfied → highest explicit priority → **global logical specificity** → local specificity → tie-break. The docs recommend specificity over explicit priority.
- **SI constraints** live on topologies:
  - `>>` pad trees;
  - `BridgingPinModel` for pass-through parts and `TerminatingPinModel(delay, loss)` for endpoints;
  - `RoutingStructure` for the medium;
  - Timing, TimingDifference and InsertionLoss constraints;
  - Signal Tuning regions.
- **Placement** is a kinematic tree, not a constraint system.
- **Circuit-port forwarding** lets reusable sub-circuits carry their constraints into any parent. [P]

**tscircuit: constructive properties.**
- Placement: pcbX/Y, edge anchors and position modes.
- `calc()` can reference pad bounds, e.g. `calc(R1.pin1.minX - 2mm)`.
- `<constraint xDist … centerToCenter|edgeToEdge>` for footprint geometry.
- Groups with grid, flex and pack layout (beta).
- `<bus maxLengthSkew>`, `<differentialpair>` and `<breakout>` regions for routing.
- `<drccheck checkFn>` for custom design-local DRC. [P]

**atopile: parametric assertions.**
- Assertions with tolerances, e.g. `assert … within 3.3V +/- 10%`, plus equations for the solver.
- Layout reuse: build a sub-module as its own target, lay it out in KiCad, then use KiCad's "pull group".
- No geometric vocabulary, and the syntax is in flux. [P]

**Quilter: physics constraints graded by PRCs.**
- **7 constraint types**:
  - Bypass Capacitors, with a parent-pin assignment priority;
  - Switching Converters, detected from `U`/`L` refdes and ≥2 caps;
  - Crystal Oscillators;
  - Power Nets;
  - Timing-sensitive Signals ("soon");
  - Differential Pairs;
  - Single-ended Impedance.
- **8 PRCs**, each with units and a pass criterion:
  - Pin Distance (e.g. 0–1 cm);
  - Layer Switch Count;
  - Ground Plane Overlap (every point except the last 2×clearance);
  - Trace Path Length;
  - Length Mismatch;
  - Uncoupled Spacing;
  - Invalid Width Span;
  - Overheated Length (% of a high-current net whose analytic temperature rise exceeds 20 °C, e.g. 0–10%).
- Nets without constraints are routed as generic low-speed signals. [P/VK]

**ALIGN: typed constraints.** Typed Pydantic constraints in `.const.json`. A `HardConstraint` implements `translate(solver)`. A `UserConstraint` expands into low-level constraints such as SymmetricBlocks, BlockDistance, GuardRing or NetPriority. [P]

**FloorSet (Intel; ICCAD 2026 Problem C).** Hard constraints: fixed outline, shape, boundary, grouping, multi-instantiation and pre-placement. [P]

**KRT `floorplan-intent.json`.**
- Strict keys: blocks/zones, keepouts, edge_connectors, decaps, `proximity[]` (ref, near, max_mm, basis), keep_away, replicate, arrays, fixed_poses, must_lock, legality_budget, severity.
- Unknown keys are refused at load.
- The intent acts as a monotone per-move gate in the optimizer. [P]

**IPC-2581C** (XSD dated 2020-07-31):
- **Impedance spec**: value and tolerances, with a structure of SingleEnded, EdgeCoupled, BroadsideCoupled or CoplanarWaveguide (line width, spacing, RefPlane).
- **Loss** spec.
- **Nets**: `netClass` (CLK, FIXED, GROUND, SIGNAL, POWER, UNUSED) and `netPair`.
- **DFX**: criteria and queries, with responses such as APPROVED, WAIVED and REJECTED.
- It carries **no** clearance, length/skew or placement rules.
- KiCad's exporter writes stackup, finish and backdrill specs but **no Impedance spec**. [P]

**Academic work.**
- GNN extraction of analog symmetry constraints (arXiv 2312.14405).
- LLANA: LLM priors to speed Bayesian optimization of analog layout constraints (2406.05250).
- PCBSchemaGen: per-IC knowledge graphs plus a deterministic 5-layer verifier, 81.3% pass on schematic tasks (2602.00510).
- No PCB layout intent language, and no paper on LLM extraction of layout rules from datasheets, was found.

### One intent in five systems

How each system expresses "keep C5 within 2 mm of U1 pin 7, with a via to the GND plane":

| System | Expression |
|---|---|
| tscircuit | Constructively, as `calc()` |
| Quilter | A bypass constraint graded by PRCs |
| KRT | `proximity[]` |
| KiCad | Only post-route: `fromTo('U1-7','C5-1')` + `length (max 2mm)` |
| IPC-2581 | Not at all |

So the IR needs native `proximity` and `via_to_plane` primitives.

### Proposed IR: `pcb-intent/0.2` (CVB Q6; untested)

**Format.**
- Strict YAML/JSON; unknown keys are rejected.
- `resolution: specificity | explicit_priority`.
- JITX-style tags with inheritance, bound to KiCad selectors.
- Selectors that render to KiCad conditions, e.g. `U1-7` or `${Class:BUCK1}`.
- Topologies: ordered pad paths through series parts, with bridging and pin-delay models.

**Constraint kinds:**

| Kind | Content |
|---|---|
| `bypass` | High-level intent. `expands_to` proximity, ground via, loop and layer-switch primitives. Carries `provenance` {source, doc, page, confidence, confirmed_by} |
| `proximity` | `max`, `basis: pad_edge`, hard/soft. Compiles to a `geom.pad_distance` checker, a `hinge_sq` optimizer penalty, and a KiCad `fromTo`/`length` proxy |
| `via_to_plane` | Pad, plane net and layer, `max_via_distance`, `min_vias` |
| `layer_switch_count` | Path, `max` |
| `loop_area` | Path, `max_mm2` |
| `match_group` | Members, `mode: relative`, target, `tol_ps`. Compiles to a time-domain tuning profile and a `skew` rule |
| `impedance` | Maps to and from IPC-2581 EdgeCoupled |
| `region` | Rect, side, keep inside |
| `cluster_tight` | Anchor, members, `max_span` |
| `edge_placement` | Ref, edge, overhang |
| `symmetry` | Pairs, axis |
| `overheated_length` | `max_rise_c` 20, `max_fraction` 0.10 |

Findings use the fields constraint_id, measured, limit, unit, severity, objects, location and response (open, approved, waived or rejected).

**Eight design rules:**
1. Split hard and soft constraints. Hard constraints get a monotone gate in the optimizer.
2. High-level intents expand into primitives. The LLM authors the high-level intents.
3. Every primitive has a checker with units and pass criteria, plus a KiCad compilation where one exists.
4. Resolve by specificity, and emit rules to KiCad general-to-specific so that KiCad's last-match semantics agree.
5. Express timing on topologies and match groups. Length belongs to a pad-to-pad path through series parts, not to a net.
6. Record provenance and human confirmation for every LLM-extracted constraint.
7. Map impedance and loss specs to and from IPC-2581.
8. Keep a DFX-like findings and waivers channel that mirrors KiCad exclusions.

**VK refinements.**
- `skew` accepts `ps`, so emit the match-group fallback in time units. The sketch's `0.8mm` with "~6.3 ps/mm illustrative" is unnecessary.
- Prefix every rule name with `IR:<id>`, because DRC JSON has no rule field.
- Write one condition per rule.
- Use canonical units: mm, deg, ps.
- Add KiCad 11's `CustomRule` protobuf as a second compile target.

### The practitioner version: `intent.yaml` (PD)

PD's proposed fields:
- net classes with current and edge rate;
- hot-loop member sets;
- decoupling targets per pin group;
- terminator ends;
- star point and its order;
- keep-outs ("no power under IMU");
- connector edges and orientation from the enclosure;
- locked "stake-in-the-ground" regions;
- reference-layout copies;
- a style profile.

CadMust's author reports, from his own measurement on a 161-part board, that schematic-only extraction got about 70% of hand-written placement constraints, and about 95% after adding datasheet extraction for two key ICs [A]. A critic (Jewnadian) replied that this merely "replaced the act of dragging the select box … and clicking 'Add Room'".

**Implications for our system.**
- Make `pcb-intent` the single source of truth. The LLM authors high-level intents with detection evidence; expansion into primitives is deterministic; each constraint carries a confirmation flag.
- Compile three ways:
  - a strict `.kicad_dru` emitter, linted with `kicad-cli` on a scratch copy;
  - Python PRC checkers, the only route on 10.x for proximity, alignment, symmetry, loop area and via-to-plane;
  - optimizer penalties.
- Carry part roles in component classes. Carry impedance and timing in net classes plus tuning profiles, written via `SetNetClasses`.
- Import IPC-2581 impedance specs when they exist; never expect KiCad to export them.
- Retire custom return-path checkers once KiCad 11 ships `return_path`.

---

## 7. Evaluation stack (fast → slow)

| Tier | When | Checks | Tools and runtime evidence |
|---|---|---|---|
| T0 (µs–ms) | Every move | Overlap and out-of-bounds; IR/PRC geometry; HPWL; crossings; Transcalc Z0 and delay; IPC-2221/2152 widths; overheated-length proxy; convention metrics | In-process geometry; KRT-style intent grader; PDN DNN at 0.1 s if trained for the board class |
| T1 (s) | Per accepted placement or route batch | `kicad-cli pcb drc --format json --refill-zones --schematic-parity --exit-code-violations`; return-path VOID/SPLIT/VIA flags; NRR/PRR/PShort; router as routability probe | `return_path` (0.05 mm A* raster, loop-area estimate); KRT ≈0.65 s and Freerouting 2.1.0 ≈7 s per small PCBWorld board |
| T2 (s–min) | Checkpoints | DC IR drop; PDN impedance vs target; switcher coupled noise; near field | padne, KiPI, Ki-PIDA; emcvisual (within 1 dB of openEMS, 30–350 MHz) |
| T3 (min–h) | Finalists | openEMS S-parameters, TDR and delay per critical net; FEM thermal | gerber2ems + si-wrapper + scikit-rf (sample: 3.37 ms/timestep × 10k steps ≈ 34 s per excited port); FreeCAD/gmsh/CalculiX or Salome/Elmer; Palace for C/L |

### KiCad 10 backend for an agent (VK)

The IPC API in 10.0 cannot run DRC, has no rules access, no export and no headless mode. VK recommends four channels:
1. **IPC** for item CRUD inside commits. Library footprints can be placed with `ParseAndCreateItemsFromString` from `.kicad_mod` text, followed by an `UpdateItems` pass for nets.
2. **Direct `.kicad_dru` file writes** for rules.
3. **`kicad-cli` DRC on a saved copy** as the referee.
4. **A short-lived SWIG helper process** for `ExportSpecctraDSN` and `ImportSpecctraSES`. Lock any copper to keep, and strip the SES placement section, because SES import deletes unlocked copper and moves footprints.

Zone refill over IPC is asynchronous, so poll before reading geometry or running DRC. Freerouting's `-drc` writes the same `drc.v1` format, plus a `freerouting_version` key that the KiCad schema would reject. KiCad 11 adds `kicad-cli api-server`, rules over IPC, and DSN/SES and export jobs; SWIG removal is planned.

### Tool notes

**SI (openEMS-based).**
- **gerber2ems** (Apache-2.0): pixel size 5 µm by default; grid 50, 200 and 500 µm (optimal, perpendicular, max), with pitch ≤ λmin/10; ports at least 8 cells long; capacitors are shorted; field dumps can take "hundreds GB".
- **si-wrapper** (KiCad 9.0.x): slices a net or pair with its neighbours, vias and planes; shorts passives; terminates neighbours; auto-places ports. The 2025 update added an adaptive grid, diff pairs and delay. Results were VNA-validated on a DDR5 clock pair, and the flow can run in CI.
- **Licences**: openEMS is GPLv3+; Palace is Apache-2.0, with C/L extraction and AMR. FastHenry, FastCap and scikit-rf are also available.

**PI and DC.**
- **padne**: 2.5D FEM; sources declared in the schematic (`!padne VOLTAGE v=3.3V p=U1.1 n=U1.4`). The FEM core is about 40 lines: "the vast majority of work … is ferrying data around". Its via model is uncertain.
- **KiPI**: DC drop, AC PDN impedance against a target, switcher coupled noise.
- **Ki-PIDA**: 2.5D resistive mesh with electro-thermal coupling.
- **PCB_SI_Toolkit**: measured-vs-limit checks (decap distance, plane edge 3×h, reference changes without ground vias), a 2D Z0 solver, NEXT estimates.

**EMC.** kicad-happy EMC has 44 rules. kicad-emi-guardian says it is "not an EMC compliance instrument".

**Thermal.** Antmicro's flow (FreeCAD 1.0, CalculiX 2.20) was validated on an RPi5 enclosure at 2.5 W and 8 W, and in a vacuum chamber.

**KiCad itself** has no SI/PI plans: a forum request went unanswered, and FEM issue #8398 has stalled.

### ML surrogates

- **PDN impedance DNN**: trained on more than 1M BEM-labelled boards; answers in 0.1 s, 5000× faster than full-wave. The journal snippet says 10,000×, which conflicts.
- **DevFormer/DPP**: decap placement with >30% fewer components. The DPP benchmark offers a `decap_sim()` simulator and RL4CO environments, and ReEvo used it for LLM-discovered heuristics.
- **SI eye-metric surrogates**: neural nets win with data; anisotropic GPR wins when data are scarce. Amortized neural optimization loses about 10% optimality for 10³–10⁴× speedups.
- **Crosstalk**: MLP and LS-SVM surrogates [Snip].
- **EMI and thermal**: no layout-level surrogate exists.

**Implications for our system.**
- Wire T0 and T1 into the placement loop, run T2 at gates, and run T3 only for finalists. Record every verdict in the findings channel.
- Calibrate T0/T1 proxies against T3 before using them as rewards. Antmicro's VNA-validated slices and emcvisual's 1 dB agreement are the precedents.
- Measure our own tier runtimes. Nobody has published DRC timing vs board size or padne/KiPI solve times.
- Train surrogates on synthetic KiCad boards labelled by fast physics tools (padne, KiPI, return_path, si-wrapper). This is the PDN-DNN recipe.
- Feed the LLM compact summaries only: scores, unrouted counts, grouped violations, congestion hotspots. Never geometry dumps.

---

## 8. Quality metrics

| Source | Metrics |
|---|---|
| PCBWorld | **CP** (fully connected, 0 error-level DRVs); **Potential gain** Φ over unconnected, DRV, WL and vias; Routability; DRV; WL; Via; Time; Parse-fail. @5 = best of five by Φ; time averaged over all rollouts; DRC re-run on saved boards against each board's own rules [P] |
| OmniRouting | **PR** (load and schema success); **NRR** (% nets connected and DRC-clean); **PRR** (% of Σ(\|Pₙ\|−1) pad connections; missing outputs stay in denominators); **Open/PShort/NShort** (PShort counts only different-net wire–wire and via–wire contacts); Clr./Dist. by cause; Polygon; TWL; #Vias; #Layers; RT [P] |
| OmniRouting MGS | Pad-aware, layer-specific graphs at coarse (corridor/topology) and fine (geometry) scale, coarse weighted more. Measures agreement with the expert, **not correctness** [P] |
| Quilter | % pins routed; DRC count (candidates with DRC errors are hidden); sides; layers; min width; clearance; via/drill; via count; PRC pass/fail [P] |
| Cypress | Routability = % of pin pairs routed by Freerouting v1.9.0 on two free layers at default settings; routed track length; runtime [P] |
| RL_PCB | HPWL, Euclidean WL, overlap, post-route WL vs simulated annealing [P] |
| Freerouting v2.5.0 | `V2_CONTINUOUS` = max(0, 1000 − W1·o1 − W2·o2 − W_C·N_viol/D − W_D·ΣL/(U·D)), with W1 ≈ 333.3, W2 ≈ 666.7 and D = max(1, pins × signal layers); `V2_LOWER_BOUND` measures copper efficiency against placement-derived bounds, with vetoes [VK] |

**Human references are not perfect.** OmniRouting's human engineer reference scores NRR 93.58%, PRR 95.91%, Open 4.38% and PShort 0.38%.

**Cautions.**
- Quilter's blog: routing metrics without first-pass yield or bring-up data do not prove boards work [Snip].
- KRT: HPWL and crossings are blind to intent.
- AndyC_772: there is still no validated figure of merit for reinforcement learning.

**Recommended union set (CVB).**
- **Gates**: loadable, LVS parity, CP.
- **Routing**: NRR, PRR, Open/PShort/NShort, DRV by cause, TWL, vias, layers, RT.
- **Placement**: HPWL, overlap, out-of-bounds, crossings, net separation, Cypress-protocol routability, intent conformance.
- **Physics PRCs**: pin distance, layer switches, ground-plane overlap, length mismatch, uncoupled spacing, overheated length, return-path violations, IR-drop margin.
- **Human-relative**: MGS, plus WL, via and HPWL ratios to the human board.

Report human scores on the same metrics and normalize against them. Use MGS as a diagnostic only, because valid alternative routes score low on it.

**Implications [digest].** Add these metrics from EW and PD:
- checklist Critical/Major pass counts;
- the convention score;
- blind expert acceptance and review time;
- edits outside the requested scope;
- determinism (same inputs give the same board hash);
- human setup minutes;
- prediction-vs-outcome agreement.

---

## 9. Benchmarks and datasets (corrected numbers)

**There are no ISPD or ICCAD PCB problems.** ISPD contests 2005–2027 are all IC or FPGA topics. ICCAD routing problems are IC-level. ICCAD 2026 covers LLM netlist exploration, regression bucketing and FloorSet. [P]

### PCBWorld-Bench (LG AI Research)

Version 1.1.0; BSD-3, with a GPLv3 engine; KiCad 9.0.8.

| Split | Boards | Nets | Pads | Layers |
|---|---|---|---|---|
| D1 (grid) | 10,000 / 128 / 128 | 5 | — | 1 |
| D2 (gridless) | 10,000 / 128 / 128 | 4–6 | — | 2 |
| D3-A (small) | 100 | 2–13 | 6–31 | 2–4 |
| D3-B (medium) | 287 | 5–42 | 31–100 | 2–4 |
| D3-C (large) | 292 | 6–451 | 101–2,103 | 2–4 |

- D3's 679 real boards come from PCBench's corpus. Each was converted to KiCad 9 with its own rules and kept only if still fully connected and DRV-free; the original copper is the reference.
- Zero-shot evaluation uses 99 D3-A and 10 D3-B boards. D3-C is reserved as a challenge split.

**Table 3, @5** (VK VERIFIED):

| Method | D3-A CP | D3-B CP |
|---|---|---|
| Freerouting 2.1.0 | 0.80 | 0.78 |
| KRT | 0.74 | 0.20 |
| OrthoRoute | 0.02 | 0.00 |
| PPO (synthetic-only training) | 0.86 | 0.45 |
| PPO (w/o finish) | 0.94 | 0.42 |
| GPT-5.4 interactive | 0.65 | 0.00 |

**Agent mode matters.** On D3-A, GPT-5.4 reached CP 0.65 interactive, 0.19 plan-and-execute and 0.02 engine-free, with DRV 1.31, 16.28 and 34.58. "Leveraging the native API is essential for design-rule-clean routing" ([arXiv v2](https://arxiv.org/html/2607.05915v2)).

**Time per rollout:**

| Router | D2 | D3-A | D3-B |
|---|---|---|---|
| Freerouting | 2.69 s | 7.09 s | 9.94 s |
| KRT | 0.82 s | 0.65 s | 3.27 s |
| PPO | 0.43 s | 1.83 s | — |
| GPT-5.4 | — | 231 s | 866 s |

OrthoRoute's v2 routability is 0.34 (D2) and 0.53 (D3-A). DeepPCB claims "the top one-attempt score on both test sets", self-reported [V].

### PCBench

The README says 164 PCBs, each with raw and processed `.kicad_pcb`, PCB-RDL JSON, metadata and a PNG, plus a grid RL environment. **Three conflicting counts:**
- 164 in the README;
- 679 derived by PCBWorld from "PCBench's corpus";
- 1,157 boards in Freerouting v2.5.0's "PCBench table" [VK].

This is unresolved, and per-board licences are unverified.

### Freerouting v2.5.0 corpus

| Measure | v2.4.1 | v2.5.0 |
|---|---|---|
| Clean | 358 (30.9%) | 868 (75.0%) |
| Fully routed | 600 | 872 |
| Timeouts | 78 | 78 |
| Total time | 3,251 s | 2,997 s |

Tier C (6+ layers) reached 49.2% clean. [VK]

### Cypress (NVlabs)

- Apache-2.0; built on DREAMPlace; DOI 10.1145/3698364.3705346.
- Benchmarks: the slides describe 10 small synthesized and 5 large commercial designs; the repo ships small-1…small-20.
- Formulation:
  - SMD non-critical parts on two-sided rectilinear boards, with sides pre-assigned;
  - spacing, non-overlap and fixed parts;
  - orientation-aware LogSumExp wirelength;
  - two-sided electrostatic density;
  - a net-crossing model.
- Rotation is off by default.
- Claims vs SA-PCB and NS-Place: 1–5.9× routability, 1–19.7× shorter routed length, up to 492.3× speedup.

### OmniLayout / OmniRouting

- OmniLayout has 77.24K placement instances. OmniRouting covers 2–8 layers with human reference routings and four tasks.
- Both come from 1,681 Eagle designs (SparkFun, Arduino, Adafruit, GitHub).
- The authors promise open data, but a 2026-08-15 audit found 5 public sample boards, no data licence and CC BY-NC-ND papers [3P].
- **Results:**

  | Method | NRR | PRR |
  |---|---|---|
  | Best zero-shot LMM | 12.60% | 15.41% |
  | Agentic refinement | 27.98% | 30.34% |
  | OpenROAD PcbRouter | 56.20% | 71.37% |

  Base LMM outputs average 69.77–431.29 DRC violations, and "Feedback quality matters more than iteration count."

### Other datasets

- **PCB-Bench (ICLR 2026)**: knowledge QA, not layout. About 3,700 text items, about 500 image-text items, and 174 OSHWHub designs.
- **EEBench**: atopile-based, graded with SPICE corners and BOM cost. Claude Opus 5 scored 61.6% on 13 tasks. The authors say it "does not yet tell us whether a model can lay out" [V].
- **Smaller sets:**
  - RL_PCB: 6 training circuits.
  - tscircuit `dataset-srj18`: 16 boards. Also the SRJ33 DRC-failure set. The SRJ format is lossy: it drops widths, clearances, zones and keepouts.
  - DevFormer DPP.
  - FloorSet: 2×1M synthetic floorplans.
  - devbisme's test repo.
  - KiCad Agentic MCP's 18/18 golden tasks [A].
  - kicad-happy's harness over 5,800+ repos and 3,498 PCB files.
  - TraceMaker ≈0.99/1.00/0.90 vs Freerouting 2.2.4 at "about 0.7/0.7/0.2" [VK].
  - Older BGA-escape work used proprietary instances, e.g. a 28×28 BGA with ~380 signals [Snip].

**Implications for our system.**
- Treat PCBWorld D3 (routing) and the Cypress protocol (placement) as the de-facto standards.
- Re-run Freerouting 2.5.0 ourselves before claiming gains.
- PCBWorld's engine-interactive result means the agent must act through KiCad's router and DRC.
- Resolve PCBench counts and licences before redistributing anything.

---

## 10. Proposed benchmark plan

CVB's seven tracks, plus additions marked [digest]:
1. **Routing leaderboard.**
   - PCBWorld D3-A/B, later D3-C.
   - @5 CP / Pot. / Rout. / DRV / WL / Via / Time / Parse-fail.
   - Baselines: Freerouting 2.5.0 re-run alongside the published 2.1.0 (0.80 / 0.78), and KRT (0.74 / 0.20).
2. **Placement leaderboard.**
   - Cypress small benchmarks under the Cypress protocol, plus HPWL, overlap, out-of-bounds and crossings.
   - **Placement-stripped D3 variants**: keep the outline, mechanical parts, connectors and locks; re-place the rest; route with a fixed router; compare with the human placement routed by the same router.
3. **Intent track**: boards annotated with human-confirmed IR constraints. Score PRC pass rate by constraint kind and hard-violation counts.
4. **Physics track**: decap PRCs, return-path violations, IR-drop margin (padne/KiPI), and si-wrapper/openEMS on a few high-speed boards.
5. **Human-relative diagnostics**: MGS plus WL, via and HPWL ratios. Report human scores on every metric.
6. **Unit suites**:
   - synthetic generators for each IR kind, in the style of D1/D2;
   - the DPP simulator for decaps;
   - FloorSet-style constraint mixes.
7. **Hygiene**:
   - a pinned KiCad version;
   - a licence manifest per board;
   - a private, recent held-out split against contamination;
   - methods never score themselves (re-open and re-run DRC on saved files).
8. [digest] **Checklist track**: score boards with the 299-item critic stack. Include known-bad boards with their fixes (Naib: "very very few examples out there as to what is wrong") and escaped-error cases: SOT-23 flips, a backwards USB-C connector, missing VCAP caps.
9. [digest] **Trust track**: scope violations, determinism, setup minutes, prediction accuracy, and an agent-immutable harness.
10. [digest] **Blind expert review** of a sample, measuring acceptance and review time, to calibrate the convention metrics.
11. [digest] **A controlled comparison** of human vs Freerouting vs LLM-orchestrated layout on identical netlists, eventually with fabricated boards and measurements. PD found no such study.

**Implications for our system.** Build the harness first; it doubles as the agent's verification loop. Use a licence-clean corpus. Every result must be reproducible from saved KiCad files.

---

## 11. Conflicts and open questions

### Conflicts

**Rule resolution.** Each tool resolves conflicting rules differently, so the IR must define its own semantics:
- KiCad: last match wins.
- Altium: explicit numeric priority, but all Matched Lengths rules apply.
- JITX: logical specificity.
- Allegro: CSet assignment and object precedence.

**Templates as ground truth.**
- TI: "copy the EVM".
- Ritchey: app notes are "Wrong until Proven Right".
- extralongdivisi: datasheet recommendations can be "written in the 80s, overkill... or completely wrong", or under NDA.

**Decoupling.**
- Distance thresholds: <15 mm (Altium), <3 mm (claude-eda, unsourced), a 10 mm search radius (kicad-happy).
- Loop impedance instead of distance (summa_tech: "Qualcomm actually gives you these").
- rcxdude: with good planes, distance matters less.

**Aesthetics.**
- "Necessary not sufficient" vs "ugly is OK".
- Hatched vs solid planes: PCB Power warns hatching causes lamination microvoids; jnoss recommends hatched pours.

**Numbers.**
- Respin cost: $28.5k, $44k or $46k per respin; 2.8 vs 2.9 respins per project.
- PCBench size: 164, 679 or 1,157.
- Cypress: 10 vs 20 small benchmarks; Best Paper vs nominee.
- OrthoRoute: 0.34/0.53 vs 30%/51%.
- PDN DNN speedup: 5000× vs 10,000×.
- kicad-happy detector count: 40, 60+ or 21.
- Thresholds: silk height, edge clearance and part-to-edge distance differ between sources.

### Open questions

**No ground truth:**
- no validated figure of merit;
- no controlled human vs autorouter vs LLM study with EMC/SI measurements;
- no aesthetics or acceptability dataset;
- no company style-profile data;
- no dataset of datasheet reference layouts, and no PCB layout-retrieval paper;
- no evaluation of LLM extraction of layout rules.

**Untested on KiCad 10:**
- whether `ParseAndCreateItemsFromString` keeps net assignments;
- how long async zone refill takes;
- whether the GUI reloads an externally edited `.kicad_dru`;
- how long each tier takes on representative boards;
- how the master net-chain semantics work.

**Unavailable or unread:**
- no thermal or EMI surrogates;
- Phil's Lab and Hartley talk content (YouTube blocked transcripts);
- Feranec's per-phase timesheets (images only);
- the original Lifecycle Insights and Aberdeen reports;
- the full Cypress paper.

---

## 12. Idea inventory

Tags: [EW] expert_workflow_and_checklists, [PD] practitioner_discussions, [CVB] constraints_verification_benchmarks, [VK] verification_kicad_and_tools, [digest] this digest's synthesis.

### Workflow and process

1. Constraint-first order: mechanics/stackup/rules → PDN/ground → fixed → floorplan → critical → decaps → rest → sanity → fanout → critical routes → planes → bulk → tune → stitch → DRC → outputs [EW]
2. Agent plan as backtracking state machine S0–S17 with critic-gated exits [EW]
3. Three review gates: constraint model, rough placement before routing, completion [EW]
4. Git commit/PR per state; reviews tied to a commit; reviewee posts checks performed [EW]
5. Escalation ladder: local moves → re-floorplan → repackage/add layers/enlarge → drop or flag functions → human [EW]
6. Olney's ≥85% first test-route completion as the placement gate [EW]
7. Autorouter near-completion as layer-count adequacy test (VSE) [EW]
8. Spend most search on placement; fast routability estimator as inner objective [EW]
9. Staged reviews with distinct checklists (pre-layout, placement, critical routing, DFM) [EW]
10. DFM before quote, prototype, production, and on material/layer/density/assembly changes [EW]
11. Whole-assembly design review before assembly (NASA) [EW]
12. Pre-routing setup: stackup into rules, PDN plan, via sizes per class, rule priority, router options [EW]
13. Per-net highlight sanity pass for nets longer than Manhattan or spiralling [EW]
14. Per-IC layout review against datasheet by a separate reviewer [EW]
15. Effort anchors 50 h simple / 200 h CPU+memory (Feranec) [EW]
16. Treat 90/10 placement/routing sayings as folklore, not data [EW]
17. Constraint definition is a dominant time sink; make it cheap [EW/PD]
18. Checklist grows after every escaped error (failure-log learning loop) [EW]
19. Phil's Lab review order as a fixed LLM review script [PD]

### Placement

20. Place by cross-probing one part at a time, by function and importance [EW]
21. Group each IC's private parts first, minimizing crossings between groups [EW]
22. Functional blocks ordered by signal flow; separate power/analog/digital/RF [EW]
23. Place everything before routing (Tip 095) [EW]
24. Autoplace only as a fit check [EW]
25. Feranec order: defined parts → CPU+memory → other ICs → power → small parts [EW]
26. BGA: trial placement, clear, then fan out and place from the centre, concurrently [EW]
27. Leave routing channels between memories and dense ICs [EW]
28. Keep power-stage transistor, inductor and caps tight [EW]
29. Decap staging nF at pins → µF near → bulk on source path [EW]
30. Power-stage order with input cap placed and routed first [EW]
31. Shorten power loops before widening traces [EW]
32. SLVAFJ3 8-step converter order including Kelvin sense through net ties [EW]
33. Follow ordered datasheet layout priority lists (bq25886) [PD]
34. Crystal: nothing unrelated within 1 inch; ground guard; check routing near it [EW]
35. Interface ICs, ESD and filters at connectors; series R at source; terminators at load [EW]
36. ADC anti-alias filter at ADC input [EW]
37. Align bottom lands with top lands to open via channels [EW]
38. Rework clearance 80 mil; inspection angle ⇒ spacing = tallest neighbour height [EW]
39. Like parts same orientation; pin-1s aligned; memories in a matrix [EW]
40. Placement grids (100/25 mil; 0.05"; 0.1" headers; 5 mil origin) [EW]
41. MLCCs away from V-scores, tabs and holes, aligned against flex [EW/PD]
42. Space and orient nearby inductors against magnetic coupling (unsourced) [EW]
43. Heat sources by airflow/edge; small parts ≥1 mm from tall or hot parts [EW]
44. Switching converters away from sensitive analog [EW]
45. Group circuits sharing supply/ground domains [EW]
46. Don't over-constrain board size; needed space is underestimated [EW]
47. Rough placement → swap-autoplace for shortest nets with "unmovable" parts → autoroute → star-ground fix → pours [PD]
48. Group parts by ratsnest length and crossing count for initial placement [PD]
49. Cluster by fewest unique nets [PD]
50. Total-ratsnest-length metric with net weighting [PD]
51. Paper sketch of functional "nuggets"; Pack and Move per block; group and move groups [PD]
52. Reference-designator ranges per block (x3nn power, x5nn MCU) [PD]
53. Agree fixed part positions with the mechanical engineer via STEP [PD]
54. Sequential optimal packing as a seed, then an LLM feedback loop that "hardens" constraints [PD]
55. CSS-grid-style placement constraints beat flexbox/cassowary [PD]
56. Area-minimizing packing gives unroutable boards; force-directed placement is unpredictable [PD]
57. Hierarchical decomposition to avoid UNFEASIBLE placements [PD]
58. Placement framed as bin-packing [PD]
59. Refine from a seed rather than place from scratch; constraint capture is the bottleneck (KRT) [VK]
60. First output is a floorplan (regions, pre-placed connectors, anchors, pin-distance constraints) confirmed before optimizing [VK]
61. Lock connectors and fixed parts before any optimizer runs [PD]

### Routing

62. Matched, diff and critical nets first, by hand, then locked [EW]
63. TI ladder: power/ground and susceptible → clocked data → only <50 kHz to autorouter [EW]
64. Order power → high-speed → MCU [PD]
65. Bartels flow: pre-route power vias, decaps and critical nets, autoroute the rest, check net by net [PD]
66. Escape-and-reserve all nets of a bus before completing any [EW]
67. Same topology per signal group; stitching vias at reference changes [EW]
68. Own via per GND/VCC pin and per decap; 10–20 mil power fanout [EW]
69. Interactive finish to >90%, then autoroute remainder [PD]
70. Autoroute regular buses in cleared areas [PD]
71. Autorouter as placement probe, then rip up [PD]
72. Router via count and failure clusters as placement diagnostics [PD]
73. Tournament of routers or routes; keep and lock the best [PD]
74. Pin key traces via the Python API, Freerouting for the rest [PD]
75. Router must rip up earlier routes [PD]
76. Feed routers quantitative information: keepouts, vias by ground pins, layer penalties [PD]
77. EMI-aware autorouter as long-term goal [PD]
78. Topological, any-angle and 8-direction routing are underexplored [PD]
79. Avoid any-angle and micro-wiggles for human editability [PD]
80. Width only where current flows; polygons for power distribution [PD]
81. Keep margin from rule minima [PD]
82. Change layers across the same plane; transfer via very near; never cross split pairs [PD]
83. No noisy traces on board edges; edge stitching [EW]
84. Orthogonal routing on adjacent signal layers [EW]
85. Neat long parallel runs create crosstalk; penalize them [EW]

### Size, layers and stackup

86. Size = Σ(courtyard area)/utilization + packer fit test [EW]
87. Layer count generate-and-test; +pair at >70% channel use or <85–100% completion [EW]
88. Stackup from fab catalog with craftyjon's impedance-width sanity check [EW]
89. Fab approves HDI/rigid-flex stackup before rules [EW]
90. Evaluate interdependent fab parameters jointly [EW]
91. Robertson tiers; don't push fab limits; fab notes in process order [EW]
92. Hi-rel mode: IPC-2221 Class 3, sectional standard, coupons [EW]
93. Hartley's lists of stackups to use and avoid; signal one dielectric from plane [PD]
94. Rise time sets bandwidth: F(GHz) = 0.5/Tr(ns) [PD]
95. Prefer ICs with paired power/ground pins and lowest adequate Vcc [PD]
96. Two-layer rules: power over ground, length:width ≤3:1, unbroken pour under HS traces [EW]
97. Panel efficiency and board thickness as explicit decisions [EW]

### Reuse

98. Copy the EVM/datasheet layout as the least-risk path [EW]
99. EVM layout → KiCad 10 design-block library keyed by MPN and topology [EW]
100. Save agent-learned blocks only after they pass critics [EW]
101. Hierarchical sheets → per-sheet rule areas as floorplan cells [EW]
102. Multichannel channel detection by isomorphism plus Repeat Layout; prefer hierarchical-sheet channels [EW/VK]
103. Version-gate reuse (≥9 multichannel/classes; ≥10 design blocks) [EW]
104. Compare the schematic with a known-working reference board [EW]
105. Treat app notes and EVMs as wrong until proven right; run critics on them [PD]
106. Don't copy popular open-source layouts (Arduino Uno counterexample) [PD]
107. Retrieval index keyed by (footprint/MPN, passives, pin functions) supplying relative-pose seeds [CVB]
108. Compile datasheet guidance into IR constraints, not copied geometry [CVB]
109. Quilter-style schematic-pattern detection as first-pass intent extractor [CVB]
110. JITX circuit-port forwarding so reusable blocks carry their constraints [CVB]
111. atopile sub-build plus "pull group" layout reuse [CVB]
112. Altium rooms that move their components, generated from component classes [CVB]
113. Use multichannel as a placement multiplier after one channel is done [VK]

### Review, checklists and critics

114. 299-item master checklist, 24 categories, severity and automation tags [EW]
115. Semantic annotation layer (roles, currents, voltages, frequencies) as the key enabler [EW]
116. Three-tier critic stack: A (DRC), S (semantic geometry), J (LLM and simulation) [EW]
117. Generate `.kicad_dru` from roles + fab profile; map violations to checklist IDs [EW]
118. Audit severity overrides, exclusions and "ignore" before trusting DRC [EW]
119. Group DRC violations by root cause [EW]
120. Finding record: measured, threshold, threshold source, evidence PNG, fix [EW]
121. Tier-S priority list of 11 critics [EW]
122. Tier-J structured packet; pass/fail/uncertain; uncertain → human [EW]
123. Hand HS-08/14, FLX-07 and PWR-01 EMI to simulators [EW]
124. Critical items gate; Major items penalize; minor items and aesthetics are soft [EW]
125. Threshold provenance: datasheet > fab profile > house default; label tool heuristics [EW]
126. Mandatory fab/assembler profiles because thresholds conflict [EW]
127. Critic priority: documentation/spec → geometry → physics [EW]
128. Output-package checks (RS-274X/X2, Excellon, 1:1, IPC-356, readme, no CAD files) [EW]
129. Net-class coverage report for controlled-impedance nets [EW]
130. Margin-to-limit DFM report [EW]
131. Verify each suspected issue against a primary source before reporting [EW]
132. "Never trust a clean ERC": walk each IC's power pins, mandatory passives, straps, VFB dividers [EW]
133. Audit order "run the real checkers first" (Adom) [EW]
134. Severity-ranked report with refs, pins, why and one fix [EW]
135. Footprint vs datasheet side-by-side images [PD]
136. Adversarial datasheet-comparison review prompt [PD]
137. Mandatory second deep-dive pinout pass [PD]
138. Multiple DRC tools; fab DFM as source of truth; watch for checker false positives [PD]
139. Same-LLM audit of its own changes catches introduced bugs [PD]
140. Unit-test board generators [PD]
141. Visual red-flag list: random decaps, thick traces, backwards connectors, needless BGAs, length matching [PD]
142. Connector-orientation and supplier-footprint-orientation checks [PD]
143. "Trace width matches the chip's reference design" check [PD]
144. "Op-amp schematic layout conventional" check [PD]
145. Readable schematic as a review precondition [PD]
146. Project web page with chronological change log and visualizations [PD]
147. Test-point distance L = 0.29·H + 0.7 mm [EW]
148. Copper balance of symmetric layer pairs within ~20% (15% double reflow) [EW]
149. ≥1 ground return per 9 signals in cables (1 per 4 if >1 ft) [EW]
150. Termination threshold at λ/10 (FCC) or λ/50 [EW]
151. Via-fence pitch ≤λ/8 [EW]
152. Simulate nets longer than 1/6 of rise time [EW]
153. HS ≥1.5W from voids and ≥90 mil from plane edges; stitching caps ≤1 µF [EW]
154. Via stubs <15 mil or backdrill; ~30 mil antipads; equal via counts; SMDs ≤0603; breakout within 0.25" [EW]
155. Tombstone copper-ratio checks (UWARG <2×; kicad-happy <0.3) [EW]
156. Assembler passive spacing table; part-to-hole ≥8 mil [EW]
157. Fiducials: 3 global, 2 local, 40–118 mil [EW]
158. Split ground only for audio/precision <~100 kHz, joined at a single point [EW]
159. Respin framing: 2.9 respins/project; ~60% of designers at 1–5/year; <2–20% with no TQs [EW]
160. Fab-hold ranking: stackup 28%, impedance 22%, drill-to-copper 18%, notes 15%, BGA ring 12% [EW]
161. Datasheet-driven per-IC rule extraction from "Layout Guidelines" sections [EW]

### Metrics

162. Orientation entropy per part class [EW]
163. Pin-1 agreement fraction [EW]
164. Grid-snap ratio [EW]
165. Collinearity score [EW]
166. HPWL/MST plus crossing count [EW]
167. Manhattan/MST route ratio outliers [EW]
168. Hot-loop polygon area and switch-node copper area [EW]
169. Decap distance plus Spearman value-vs-distance order [EW]
170. ≤2 text directions; mirrored bottom text [EW]
171. Geographic designator rank correlation [EW]
172. Pad-exit-style violations [EW]
173. Coupled parallel-run length [EW]
174. Channel congruence (RMS pose deviation) [EW]
175. Signal-flow monotonicity [EW]
176. Turn-count/wiggle and any-angle fraction [PD]
177. Pair every neatness term with a coupling penalty [EW]
178. Taste = physics proxies + convention proxies + company style profile [PD]
179. Field-containment check per critical net: plane adjacency, splits, transfer via, loop area [PD]
180. PCBWorld CP, potential gain and @5 [CVB]
181. OmniRouting PR, NRR, PRR, Open, PShort, NShort, Clr., Dist., Polygon, TWL, vias, layers, RT [CVB]
182. MGS human-similarity, as a diagnostic only [CVB]
183. Normalize against human scores (human NRR 93.58%) [CVB]
184. Cypress routability protocol (Freerouting v1.9.0, two layers) [CVB]
185. Quilter PRCs as physics metrics with units and pass criteria [CVB]
186. Intent conformance as PRC pass rate per kind [CVB]
187. Freerouting `V2_CONTINUOUS` and `V2_LOWER_BOUND` scores [VK]
188. Union metric set: gates, routing, placement, physics, human-relative [CVB]
189. Trust/process metrics: out-of-scope edits, determinism, setup minutes, prediction accuracy [digest]

### Trust and UX

190. Deterministic tools decide correctness; the LLM never self-judges [PD]
191. Bounded, commanded chunks with review between them [PD]
192. Predictable automation without settings; human "plots a course" [PD]
193. Never touch locked or known-good work; minimum change [PD]
194. Physical rationale with before/after render for every step ("loop L 1.8→0.9 nH est.") [PD]
195. 100% routed is never a terminal state [PD]
196. Immutable scoring harness against scoreboard gaming [PD]
197. State the expected result before running checks (Bogatin #9) [PD]
198. Determinism across board revisions [PD]
199. Cheaper than hand layout, including setup [PD]
200. Data provenance and IP; no training without consent [PD]
201. Declarative constraints ("this trace carries 100 mA"), lockfiles, tests [PD]
202. Progressive constraints "like CSS" [PD]
203. Visual constraint entry (click net, "5A", "route shortest possible") [PD]
204. Spreadsheet constraint entry (OrCAD-style) [PD]
205. Per-zone and per-net-type rule sets with priorities [PD]
206. Escape hatch from layout-as-code to the GUI [PD]
207. Co-creation and conversational UI; cruise control, not chauffeur; sketch routing [PD]
208. Guided commands ("Connect this 32 bit databus") with star-ground, shunt, HV and guard-ring awareness [PD]
209. "Do DRC, fix whatever it tosses and show me what you did" [PD]
210. Incremental-ECO mode, because greenfield is hard and edits are easy [PD]
211. Undo, commits and project snapshots before mutating edits [PD]
212. Ask explicit questions about never-delegate items [PD]
213. Do the delegable work perfectly first [PD]
214. Ship the reviewer/analyzer before the producer [PD]
215. Position as "good but not perfect"; "well-constrained one-step-up from autorouter" for simple boards [PD]
216. Boilerplate prototypes are valuable even without analog/HS [PD]
217. Leave the enjoyable craft (routing) to humans when they want it [PD]
218. Prove quality with evidence before claiming it [PD]
219. Reliable round-trips and fixed-part marking [PD]
220. AI silkscreen placement [PD]
221. Tedious N-copy replication [PD]
222. Pin planning, review against requirements, part suitability [PD]
223. Parametric APIs (DigiKey) over model recall [PD]
224. Standardized JSON/XML pin maps [PD]
225. Accuracy bar: "60 percent of the tasks at a 50 percent accuracy rate is absolutely useless" [PD]

### LLM roles and failure modes

226. LLM works upstream of and around the solver: constraints, net priority, DRC configuration, floorplan fixes, judging [PD]
227. LLM reads routing-failure clusters and proposes geometric fixes (stagger U6–U10) [PD]
228. LLM authors DRC rules for classical routers [PD]
229. LLM sorts nets into manual vs autorouted [PD]
230. LLM as datasheet extractor [PD]
231. LLM review is cheap insurance ($1–2 vs $70–80 boards) [PD]
232. LLM-written analysis: DC IR FEA; AC PDN validated against a DSO FRA [PD]
233. Parsers give the LLM "eyes"; post-processed data beats raw files [PD]
234. "Parsers do the work, LLM generates the narrative" [PD]
235. Don't let the LLM write its own placer or router [PD]
236. Guard failure modes: backwards connectors, endless loops, huge schematics, BGA escape, micro-wiggles, unrequested edits, DRC-loop slop, open nets exported, odd self-imposed rules [PD]
237. LLMs don't reliably use only datasheet information [PD]
238. Guard against LLM overconfidence [PD]
239. Datasheet footnote traps (e.g. "3.3v max 80MHz") [PD]
240. Datasheets are not ground truth (old, overkill, wrong, NDA) [PD]
241. Decoupling as a loop/cross-impedance target; distance is only a proxy [PD]
242. Layout is circuit design with unknown component values [PD]
243. Pin, part and package swaps as layout moves, with schematic back-annotation [PD]
244. Schematic order communicates layout order [PD]
245. Close the feedback-loop gap with fast verification [PD]
246. Training data is scarce; collect bad examples with fixes [PD]
247. An image-transformer router would need >10M boards [PD]
248. Parallel seeded runs with ranked candidates (Quilter) [PD]
249. LLM orchestrates router jobs with low token use [PD]
250. Fast tool operations (<1 s) vs minutes of LLM thinking [PD]
251. Code-first EDA (atopile) avoids GUI context waste [PD]
252. Deterministic scripts with AI only at judgment calls; per-module `board.yaml` hard-errors on unsafe pins [PD]
253. `git describe` revision on silkscreen [PD]
254. AI learning from layout plus simulation (Feranec's outlook) [PD]
255. Harness with built-in EMC/EMI/SI/PI/thermal solvers [PD]

### Constraint and intent IR

256. Three model families: rule scoping, object-centric managers, placement relations [CVB]
257. IR as a superset that compiles to `.kicad_dru`, checkers and penalties [CVB]
258. Explicit resolution semantics; JITX specificity emitted general→specific [CVB]
259. Tags with inheritance bound to KiCad selectors [CVB]
260. Topologies with bridging and terminating pin models for timing [CVB]
261. Allegro match groups resolved to pin pairs (Match vs Relative) [CVB]
262. Allegro electrical modes as vocabulary (stub, exposed length, max parallel, return-path DRC) [CVB]
263. Native `proximity(pad, pad, max, basis)` primitive [CVB]
264. Native `via_to_plane` primitive [CVB]
265. `loop_area` and `layer_switch_count` primitives [CVB]
266. `region`, `cluster_tight`, `edge_placement` and `symmetry` primitives [CVB]
267. `overheated_length` primitive [CVB]
268. High-level intents (bypass, switcher, DDR lane, USB pair) expand into primitives [CVB]
269. Hard/soft split with a monotone gate on hard constraints [CVB]
270. Provenance, confidence and `confirmed_by` per constraint [CVB]
271. DFX-like findings and waivers channel [CVB]
272. IPC-2581 import/export for impedance and loss [CVB]
273. LLM proposes with evidence → human confirms → PRCs grade [CVB]
274. Strict schema; unknown keys refused (KRT) [CVB]
275. Practitioner `intent.yaml` field list [PD]
276. tscircuit `calc()` pad-relative placement and `drccheck` custom checks as models [CVB]
277. atopile tolerance assertions as electrical intent [CVB]
278. FloorSet multi-instantiation and boundary constraints [CVB]
279. ALIGN `UserConstraint` expansion into solver terms [CVB]
280. GNN symmetry extraction; LLM priors for Bayesian optimization (LLANA) [CVB]
281. PCBSchemaGen per-IC knowledge graph plus 5-layer verifier with pin-level localization [CVB]
282. Schematic-plus-datasheet constraint extraction completeness (~70% → ~95%) as an evaluation target [PD]

### KiCad implementation

283. Strict emitter: one condition, one constraint per type per rule, parenthesized, general→specific [VK]
284. Canonical units mm/deg/ps; never `th`, `"` or `rad` [VK]
285. Rule names prefixed `IR:<id>`; map violations by regex on `description` [VK]
286. Lint generated rules with `kicad-cli` on a scratch copy [VK]
287. Avoid deprecated `insideArea`, `insideCourtyard` and `memberOf` [VK]
288. Don't rely on `ignore` severity to constrain the router [VK]
289. Time-domain first: tuning profiles via `SetNetClasses`, `ps` length/skew, `within_diff_pairs` [VK]
290. Four-channel 10.0 backend: IPC CRUD, `.kicad_dru` writes, `kicad-cli` referee, SWIG DSN/SES helper [VK]
291. Poll after async `RefillZones` [VK]
292. Lock copper before SES import; strip the SES placement section [VK]
293. Diff KiCad vs Freerouting DRC JSON to expose DSN translation losses [VK]
294. Freerouting single-call tool returning scores, not geometry [VK]
295. Freerouting `/drc/summary` congestion hotspots as LLM input [VK]
296. Library placement via `ParseAndCreateItemsFromString` plus an `UpdateItems` net pass [VK]
297. KiCad 11 `CustomRule` protobuf as a second compile target [VK]
298. Adopt master `return_path` and net-chain rules when they ship [VK]
299. SWIG only in a short-lived helper; plan for removal in KiCad 11 [VK]
300. Check for diff-pair name false positives (XTAL_P/N) [VK]
301. Enforceable in KiCad: side, orientation (assertion), area containment, courtyard; custom only: pad distance, alignment, symmetry, loop area [VK]
302. Component classes as role carriers queried by `hasComponentClass` [EW]
303. Copy the commercial input contract: fixed outline, pre-placed connectors, locked copper, named planes, confirmed constraints [VK]
304. Target the high-speed space DeepPCB and Quilter leave open [VK]

### Verification tools and tiers

305. Tiered T0–T3 evaluation [CVB]
306. `kicad-cli` DRC with JSON, parity, refill and exit code 5 [CVB/VK]
307. Transcalc Z0 and IPC-2221 width inside the loop [CVB]
308. `return_path` raster flags and loop-area estimate [CVB]
309. emcvisual Biot–Savart near/far field [CVB]
310. padne, KiPI and Ki-PIDA for IR drop, PDN impedance, coupled noise and electro-thermal [CVB]
311. PCB_SI_Toolkit measured-vs-limit checks [CVB]
312. si-wrapper slicing plus gerber2ems/openEMS: CI-able and VNA-validated [CVB]
313. Palace C/L extraction; FastHenry/FastCap; scikit-rf [CVB]
314. Antmicro FreeCAD/CalculiX thermal; Salome/Elmer conduction [CVB]
315. Analytic thermal proxies in the loop; FEM only at sign-off [CVB]
316. Calibrate proxies against T3 before using them as rewards [CVB]
317. Train surrogates on synthetic boards labelled by fast physics tools [CVB]
318. Precedent surrogates: PDN DNN, DevFormer DPP, SI eye, crosstalk [CVB]
319. Return compact summaries, not geometry, to the LLM [VK]

### Benchmarks and data

320. PCBWorld D3 routing leaderboard under the @5 protocol [CVB]
321. Re-run Freerouting 2.5.0 baselines [VK]
322. Cypress-protocol placement leaderboard [CVB]
323. Placement-stripped PCBWorld variants [CVB]
324. PCBWorld construction recipe for our own corpus [CVB]
325. Intent track with human-confirmed annotations [CVB]
326. Physics track [CVB]
327. Human-relative diagnostics [CVB]
328. Unit suites: synthetic per IR kind, DPP, FloorSet mixes [CVB]
329. Hygiene: pinned KiCad, licence manifest, private held-out set, re-run DRC on saved files [CVB]
330. Act through the engine (CP 0.65 vs 0.19 vs 0.02) [CVB]
331. Feedback quality beats iteration count [CVB]
332. LLM-only routing is not competitive (0.65/0.00 vs 0.80/0.78) [VK]
333. Golden-task suites (18/18) and devbisme's test repo [PD]
334. EEBench-style deterministic grading (SPICE corners, BOM cost) [PD]
335. Controlled human vs autorouter vs LLM comparison with measurements [PD]
336. Corpus-scale regression harness (kicad-happy, 5,800+ repos) [PD/VK]
337. fastroute `--parity` as a determinism reference [VK]
338. Checklist track seeded with known-bad boards and escaped-error cases [digest]
339. Blind expert review to calibrate convention metrics [digest]
