# Digest: expert practice, review checklists, practitioner trust, constraint IR, verification stack and benchmarks

**Scope.** This digest combines three notes, each read in full:
- `expert_workflow_and_checklists.md` (**EW**)
- `practitioner_discussions.md` (**PD**)
- `constraints_verification_benchmarks.md` (**CVB**)

Corrections come from searching `verification_kicad_and_tools.md` (**VK**) for KiCad DRC rules, `kicad-cli` and benchmark facts. **Where VK conflicts with the other notes, VK wins.** No new research was done. Compiled 2026-10-21.

**Tags.**

| Tag | Meaning |
|---|---|
| [P] | Read at the primary source |
| [3P] | Credible secondary source, read in full |
| [Snip] | Search snippet only (the "[S]" of EW/CVB) |
| [E] | An expert's own words |
| [Sys] | Systematic test with a stated method (PD's "[S]") |
| [A] | One practitioner's anecdote |
| [C] | Community opinion |
| [V] | Vendor claim |
| VK status | VERIFIED / CORRECTED / PRECISION / CONFLICT |

"Inference" means the note author reasoned it. **[digest]** marks my own synthesis.

---

## 0. Verification overrides (read first)

**KiCad 10 DRC language**

1. **Microvia rules are not in 10.x.** `microvia_aspect_ratio`, `microvia_stack_depth` and `isStackedVia` exist only on master (KiCad 11 dev), where the parser keyword is `hole_aspect_ratio`. EW items DFM-05/25 and the CVB constraint list cite them as current. On 10.x, write custom checks. [VK #14]
2. **Units.** Only `mm`, `mil`, `in`, `deg`, `ps` and `fs` are accepted. The documented `th`, `"` and `rad` are rejected. `ps`/`fs` work only in `length` and `skew`, and using them forces time-domain tuning. [VK #17–18]
3. **Deprecated functions.** `insideArea`, `insideCourtyard*` and `memberOf` are deprecated, though CVB lists the first two as selectors. Use `intersectsArea`/`enclosedByArea`, `intersectsCourtyard*` and `memberOfFootprint`.
4. **Parser traps.**
   - A second `condition` silently overwrites the first.
   - Each constraint type may appear only once per rule.
   - Operators have equal precedence and evaluate left to right.
   - An `ignore` rule is still evaluated and can override earlier rules, but the interactive router does not observe it.
5. **Counts.** 10.0 has 35 constraint keywords (including undocumented `solder_mask_sliver`), 23 current functions (including undocumented `intersectsKeepout`) and 67 DRC type keys. Master adds `net_chain_length`, `stub_length` and `return_path`, which is KiCad's first native reference-plane check.

**DRC output and KiCad API**

6. **DRC JSON.**
   - It has no rule-name field; the rule's name is embedded in `description`.
   - `physical_clearance` violations are reported under the `clearance` and `hole_clearance` keys.
   - The `drc.v1.json` schema has a trailing comma, so it is not valid strict JSON.
   - `--exit-code-violations` exits with code 5.
   - Zones refill only with `--refill-zones`. The board saves only with `--refill-zones --save-board`.
7. **IPC API in 10.0.**
   - The stackup is read-only.
   - `RefillZones` works only on the whole board, asynchronously.
   - There is no run-DRC call.
   - Specctra SES import **deletes unlocked tracks and vias and applies the session's placement**. The user doc says the opposite. [VK #2, #8, #9]
8. **Diff-pair matcher.** It skips trailing digits and `_`, then needs an uppercase `+`, `-`, `P` or `N`. So `XTAL_P`/`XTAL_N` count as a pair (a false positive).

**Benchmarks and tools**

9. **PCBWorld** numbers are VERIFIED, but the baseline is Freerouting **2.1.0** and D3-B has only **10 boards**. OrthoRoute routability is 0.34/0.53 in paper v2 vs 30%/51% in its README.
10. **Freerouting v2.5.0** (2026-10-05) went from 30.9% to 75.0% clean on its 1,157-board corpus. Re-baseline before comparing.
11. **Cypress** is confirmed (DOI 10.1145/3698364.3705346; ISPD '25; closed-access). The repo has 20 small benchmarks; the slides say 10 small plus 5 commercial. Rotation is off by default and sides are fixed. Award status: "Best Paper" vs "Nominee".
12. **Quilter** has exactly 8 PRCs and 7 constraint types, with timing-sensitive signals "coming soon". Scope: <5,000 pins, <20% pin density, <6 GHz, ≤48 V, ≤10 A.
13. **TraceMaker** compared itself against Freerouting 2.2.4 (single 60 s runs).
14. **kicad-happy**: the corpus (5,800+ repos, 3,498 PCBs) is VERIFIED, but its detector counts disagree (40 / 60+ / 21).

---

## 1. The expert workflow as a backtracking state machine

Primary sources share one constraint-first order. Olney 2012 states it most completely [P] ([iConnect007](https://iconnect007.com/article/72046/beyond-design-interactive-placement-and-routing-strategies/72049/design)):

mechanics/stackup/rules → power and ground strategy (JLCPCB puts this *before* placement) → fixed parts → functional floorplan → critical parts → decoupling → remaining parts → placement sanity check → fanout (often during placement) → critical nets by hand, locked → planes → bulk routing → tuning and stitching → DRC/DFM → outputs.

EW merges the sources into the state table below. IDs refer to the checklist in §4.

| State | Expert action / decision | Exit gate | Loop-back |
|---|---|---|---|
| S0 Intake | Schematic reviewed. Net classes: HS, diff, RF, power with current, HV with voltage. Part roles as component classes (decap-of, crystal-of, ESD-of, hot-loop, FB, terminator). Per-IC rules from datasheet "Layout Guidelines". Fab profile turned into rules | **Gate 1**: PRC-01/05/07/10–12, STK-09, FP-01/02/07/12 | Fix schematic / ask |
| S1 Mechanics | Outline, holes, keepouts, height zones, connector positions from MCAD; coarse grid | MEC-*, DFM-10 | from S3/S8 |
| S2 Stackup/PDN | Minimum layer count, fab stackup, per-layer impedance widths, plane strategy | STK-* | from S9/S13 |
| S3 Fit check | Pack all courtyards into the outline (Olney's only use for autoplace) | PLC-22 | → S1 or repackage |
| S4 Fixed parts | Connectors, UI, mounting, debug; lock | MEC-04..06/12/17 | → S1 |
| S5 Floorplan | Each IC's private parts → functional blocks. Separate domains. Order by signal flow, with fewest crossings between groups | PLC-02..05, ANA-02 | → S1/S4 |
| S6 Critical placement | BGA trial fanout; power stage (input cap placed **and routed** first); crystal; RF; terminators. Use a design block if KiCad ≥10 | PWR-01..03/08, PLC-07/12/24/27, RF-04 | ↔ S10 |
| S7 Decoupling | nF at the pin → µF → bulk on the source path; own vias; ESD at connectors | PDN-01..04/11/15, EMC-01/07 | → S6 |
| S8 Rest + regularize | Everything placed before routing. Snap to grid, normalize orientation and pin 1, Repeat Layout | MEC-08, PLC-13..17/23/26 | — |
| S9 Placement review | Ratsnest, HPWL, congestion, **test autoroute ≥85%** | **Gate 2**: PLC-10/11, STK-06 | → S5–S8 or S2 |
| S10 Fanout | Escapes, decap vias | DFM-24, PST-01, PDN-03/11 | → S6 |
| S11 Critical routing | Priority ladder; escape-and-reserve; lock | HS-*, GND-02/03/10, RF-01..03 | → S6/S10 |
| S12 Planes | Solid references; split only with justification | GND-*, ZON-*, THM-* | → S11 |
| S13 Bulk routing | Remaining nets in priority groups | PRC-03, RTE-* | → S8/S2 |
| S14 Tune/stitch | Meanders at the mismatched end; stitching at transitions; RF fences | HS-02/03, RF-02/03 | → S11 |
| S15 Verify | Zone refill; DRC plus silenced-rule audit; parity; DFM margins; per-net Manhattan check | 0 Critical | repair → S13 |
| S16 Outputs | Silk, fiducials, drawings, stackup/impedance table, Gerber X2 + Excellon + IPC-356, re-parse | SLK/ASM/CAM/PNL | — |
| S17 Sign-off | Per-IC datasheet review; requirements; human approval tied to a commit | **Gate 3** | → any |

**Escalation ladder** (from Olney's options): local moves → re-floorplan → repackage, add layers or enlarge the board → drop or flag functionality → ask a human. Each state becomes a git commit, following UW Rocketry's practice of one PR per review.

Olney's gate in full: "If you do not get at least 85% completion on this first test route, then you may need to tweak the placement, look at more appropriate packaging, adjust the design rules, and possibly drop some functionality." [P]

### Micro-workflows (sub-plans)

**Power stage.**
- TI's least-risk path: "a best-practice option with the least risk is to simply copy the PCB layout example found on the evaluation module (EVM)" ([TI SLYT614](https://www.ti.com/lit/pdf/slyt614)) [P].
- Otherwise: IC, then the input cap, placed and routed immediately "so that nothing else can be routed in its path". Then the inductor, the output cap, the small-signal parts, and finally a single-point ground.
- AN-1229: "'Beefing up' traces … should be a last resort" — shorten the loop first ([TI SNVA054](https://www.ti.com/lit/pdf/snva054)).
- SLVAFJ3 gives 8 steps, including Kelvin sense lines through net ties [P].
- The bq25886 datasheet: "Layout PCB according to this specific order is essential" [C].

**BGA (Feranec).**
- "I do fanout and placement at the same time … move everything what should be under CPU out of the board and start from middle placing VIAs and components back."
- Decap order: "nF closest to the pins, XXuF a little bit further …, XXXuF around the BGA or/and on the way from Power to BGA" ([FEDEVEL](https://designhelp.fedevel.com/forum/test/pcb-layout/4626-placement?p=4629)) [P].
- Phil's Lab #95: "Place ALL vias first!" [E].

**Routing ladder.**
- TI SZZA009: "Power and ground routing, as well as signals that impact susceptibility, should be laid out by hand. Any signal with clocked data … should be next. Only signals with switching rates below 50 kHz can be left safely to the autorouter" ([TI](https://www.ti.com/lit/pdf/szza009)) [P].
- PCD&F 2019: "Avoid complete routing do-overs by routing critical lines first" [P].
- Other orders seen: "first power, then high-speed, then the MCU" [A]; Bartels flow — pre-route power vias, decaps and critical nets, autoroute the rest, then check net by net [C].

**DDR escape-and-reserve.** Feranec: routing selected pin groups fully made "it … impossible to connect the la[st]…". The inference is to reserve channels for every net in the group before completing any, which favours negotiated-congestion or rip-up routing over greedy routing.

### Size, layers and stackup

**Board size.** The enclosure fixes it. When it is free, don't over-constrain it: "Usually the needed space … [is] underestimated" [P].

**Layer count.**
- NextPCB: pick the minimum that gives continuous reference planes, enough power copper and escape room. Then "add one pair of layers as margin if your routing density exceeds 70% of available channels" ([NextPCB](https://www.nextpcb.com/blog/how-many-layers-can-a-pcb-have)) [P].
- VSE: "An autorouter should be nearly able to complete routing on its own if the layer count is adequate" [P].

**Stackup.**
- craftyjon (KiCad lead): take a fab standard stackup and compute widths. An unreasonable width means the wrong reference distance, so pick another stackup or ask for a custom one ([forum](https://forum.kicad.info/t/about-stack-up-selection/21123)) [P].
- Hartley: stackup is "the most critical item … what people most often get wrong" [P].
- Peterson: fab parameters "cannot be evaluated independently"; HDI and rigid-flex stackups need fab approval "before design rules can be developed" [P].
- Robertson: "not always force the manufacturer to the limits" [P].
- NASA GSFC-STD-8001A: IPC-2221 Class 3 plus coupons [P].
- claude-eda's "2-layer with USB: can't achieve 90Ω" is unsourced.

### Review gates

| Source | Gates |
|---|---|
| UW Rocketry ([Confluence](https://uwaterloo.atlassian.net/wiki/spaces/ROCKETRY/pages/43024155641/Design+Reviews)) | After schematic; "When you've roughly laid out your PCB but haven't done any routing"; at completion. All on one PR, with the checks listed |
| VSE | Pre-layout, placement and critical-routing reviews, each with its own checklist |
| Flux | Schematic, layout and DFM reviews |
| bestpcbs | DFM before quote, prototype and production, and on any change of material, layer count, density or assembly |
| Phil's Lab #85 | Stackup → switching regulator → rules, vias, power → outline → FPGA decoupling → transfer vias → diff pairs → pours and planes → silkscreen [E, chapter list] |

### Time budgets

| Source | Claim | Tag |
|---|---|---|
| Feranec | "simple boards are up to 50 hours, more complex boards (with a CPU and memory) starts around 200 hours". Length matching "took quite a lot" | [P] |
| Folklore | "90% placement / 10% routing"; "last 10% takes 90%" | [Snip/P] |
| Siemens | Placement and routing are the "majority" of time (no study cited); automation saves "up to 50% or more" (the "80%" figure was not found) | [V] |
| DeepPCB | "Constraint definition alone can take days" | [V] |
| Practitioners | Capture <10% of time. "The rest 80% … is decision making around constraints". Placement takes about as long as routing | [C] |
| Quilter Linux board | ~27 h of seeded runs plus cleanup, vs Tesla500's ~38 h by hand (rasz: 38.5 h of human help) | [C] |

### Reuse

KiCad's reuse features:
- **9.0 (2025-02-20):** multichannel Repeat Layout. It generates rule areas as convex hulls rectified to 90°. Channels are matched by topology isomorphism, with ties broken by sheet instance and then proximity [VK]. Routing is copied only if fully enclosed. Component classes with DRC functions arrived in the same release.
- **10.0 (2026-03-20):** PCB design blocks (applying one needs "Place as group"), time-domain tuning, a graphical rule editor, variants, and pin/gate swap with back-annotation.

What experts do:
- Copy EVMs, and reference circuits ("pretty high chance, that your board will work at the first time", Feranec).
- Review every IC circuit against its datasheet (UWARG).
- Compare against the vendor EVB (Adom).

Counterpoints:
- Ritchey, on Hartley's slide: "Circuit Application notes produced by IC manufacturers should be assumed Wrong until Proven Right!" [E]
- Bogatin: "don't apply what you see in popular open-source design" [E].
- napowderly: reuse means "manually carrying over the constraints" [C].
- __atx__: "replicate the layout from the datasheet... basically solved" [A]. crote, by contrast, found the LLM "so bad at stealing a ready-made RP2350 design" [C].

**Implications for our system.**
- **Backtracking state machine.** Run S0–S17 with critic-gated exits, a git commit per state, the escalation ladder, and three gates (constraint model, placement, sign-off).
- **Compute budget.** Spend it mostly on S3–S9. A fast routability probe is the inner objective. The ≥85% gate is a profile parameter.
- **Micro-workflows as sub-plans:** power stage, BGA, routing ladder, escape-and-reserve.
- **Size, layers and stackup as generate-and-test:**
  - size from Σ(courtyard area)/utilization plus a packer fit test;
  - add two layers at >70% channel use or <85–100% completion;
  - pick fab stackup templates and apply craftyjon's width check;
  - provide a hi-rel Class 3 mode.
- **Reuse.** Version-gate it (≥9.0 multichannel, ≥10.0 design blocks). Keep an EVM design-block library keyed by MPN and topology, and put every EVM through the critics.

---

## 2. What "good" looks like; what experts never delegate

### The physics core

**Hartley** ([Altium](https://resources.altium.com/p/pc-board-stack-up-best-practices-with-rick-hartley)) [E]:
- "It's really all about rise time."
- "When you route a trace you're routing half of a transmission line."
- A 1.6 mm 4-layer board with planes on L2/L3 is poor, and the common 6-layer stackup is worse than assumed.

**Hartley's IPC deck** ([PDF](https://www.ipc.org/system/files/technical_resource/E14%26S03-02.pdf)):
- F(GHz) = 0.50 / Tr(ns).
- "Signal Layers MUST be placed One Dielectric Layer away from Plane."
- "When moving signals between 2 Gnd planes, use a transfer (stitching) via VERY near the signal via."
- "If both planes of a pair are split, don't cross at ANY frequency."
- Avoid ICs with corner power pins.

**Bogatin:**
- "The typical schematic shows us nothing about the return path"; noise lives "only in the traces and white space of the board" ([EE Journal](https://eejournal.com/article/matters-of-integrity)).
- His 20 rules include: #1 put in the numbers; #4 find the root cause; #7 "always use a continuous return path adjacent to every signal path"; #9 "Never perform a measurement or simulation without first anticipating the results"; #13 "Hope can't be part of the design process" ([SI Journal](https://www.signalintegrityjournal.com/blogs/4-eric-bogatin-signal-integrity-journal-technical-editor/post/1539-bogatins-20-rules-for-engineers)).

### Practitioner criteria

All [C] unless marked:
- "The key to good routing is placement."
- "A good placement has often autorouted usably well even 30 years ago."
- A longer trace over the ground plane beats a shorter one without it.
- "group up parts centroids … roughly in schematic order … readability is king!!"
- Widen traces only where current flows. "Engineers preferred larger polygons for power distribution" (Quilter).
- Keep margin: an autorouter "will go to the limits imposed to it... more risky for production".
- Use two 45° turns, not "10~30 small ones" [A].
- Never route "between the pins on the clock crystal capacitors", and no "power trace under IMU".

### Taste vs physics

**"Looks good" helps, but isn't enough:**
- Olney: "if a PCB design looks good, it will probably work well. However, neatness in routing often leads to unwanted crosstalk" [P].
- AndyC_772: "Mathematically we might define 'looks good' as necessary, but not sufficient" ([EEVblog](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/msg6215107/#msg6215107)).

**Ugly can be fine:**
- Kleinstein: "a well working layout that looks uggly, this would be OK".
- nctnico: 45° angles add nothing technical; Claude's clearances were "clearly better".

**Convention still matters to reviewers:**
- Quilter: tools that ignore convention produce "output engineers reject on sight... 'looks right' varies by company" [V].
- thm_w: re-routing any-angle output by hand is "a painful experience".
- crote: "'which way is up' is an unsolved problem right now".
- Flux: a 20.5 mil trace is transparent below about 25 GHz at −15 dB return loss, so 90° corners are a DFM and aesthetics question [P].

PD's resolution splits "taste" into three parts:
1. **Physics proxies.** Check these numerically.
2. **Convention proxies.** These drive review cost and how easily a human can edit the board.
3. **Company style.** Store it as a per-project profile.

### Who does what

**Never delegated, or only on a leash:**
- the stackup;
- the floorplan and connector placement, agreed with the mechanical engineer from a STEP file;
- hot loops and grounding;
- schematic-level moves, e.g. 0402→0603 so a trace fits, FPGA pin swaps, "changed chips in order to flip the ordering of the SCL/SDA pins";
- topology ("going left or right way around");
- known-good blocks ("My stake-in-the-ground");
- compromises — TwoSpoons: a switch node "needs to be big to dissipate heat... but at the same time needs to be small to prevent EMC issues. How do you tell software where the compromise is?";
- which end of the line a terminator goes on, and star-point order;
- safety, EMC and reliability.

**Delegable:**
- length-matched buses ("defintely something to let some comupter do");
- DDR with proper constraints;
- wide regular buses and fanout;
- stitching;
- last-mile GPIO;
- N-copy replication;
- probing and analysis scripts.

PD's inference: **delegation follows predictability.**

### How experts review

| Method | Example |
|---|---|
| Red-flag visual scan | Cyan488: "randomly placed ics and decoupling, likely wrong length matching, random thick traces indicating lack of foresight on power distribution, backwards connectors, the probably unnecessary use of BGA footprints" |
| Side by side | Footprint next to the datasheet drawing |
| Adversarial prompt | "Carefully review circuitry on schematic page xx, comparing connections, signals, and pin usage against the data sheets" |
| Deep second pass | The first kicad-happy pass missed an SOT-23 EBC/BEC error that the second caught |
| Multiple DRC tools, fab DFM as truth | pcb-rnd's 121 false positives cost 6 h |
| Per-net highlight | Olney's sanity pass |
| Deterministic analysis, LLM narration | "The parsers do the work, the LLM generates the narrative" |

**Implications for our system.**
- **Field-containment gates.** Check every critical net for an adjacent continuous plane, no split crossings, a transfer via within d of each layer change, and loop area.
- **Three score channels:** physics (gates), convention (soft), style (data, not code). Pair each neatness term with a coupling penalty.
- **Never-delegate items become explicit questions** with defaults. Automate the delegable list first.
- **Review script in Phil's order**, with side-by-side artifacts and an adversarial second pass.

---

## 3. Why autorouters are distrusted, and what would earn trust

### Root causes

**Wrong objective.**
- "Autorouters meet all physical rules, while violating all electrical rules" ([HN](https://news.ycombinator.com/item?id=16358399)) [C].
- "There are a million ways to make a PCB pass DRC and still be a completely non-functional device" [C].

**Missing information.**
- A switcher "has very precise layout requirements, but that status LED can be at the end of a long trace. That information simply isn't captured."
- Routing is "NP-incomplete".
- Expert systems were "a disaster. The root cause of which is most of the intent is not captured in any file."

**Placement dominates.** "Routing follows placement and routing can't fix placement problems."

**Setup catch-22.**
- "defining the constraints for an autorouter is generally more work than just manually routing."
- "Autorouter for a complete board is a beginner trap" — dmills_00, who routes 1,200-component production boards by hand.
- The one good result akiselev saw took "15 EEs, 5 of whom worked almost exclusively on configuring the autorouter".

**Wrong done-criterion.** "'all tracks routed? Great. I'm done.'" with "no ground plane".

**Behaviour.**
- Greedy routing; no net priorities; poor handling of pairs and buses; no area rules.
- Routes to the rule limits.
- Can't move parts or change pins.
- Uses thin traces where current flows, and runs traces between crystal pins.
- "if it thinks the best it can do is 20 vias on this group of traces I don't stand a chance" — high via counts point to a placement problem.

**The result.** Reviewers spot autorouted boards by "smell". K0balt: "DRC compliance only gets you 80 percent... The last 1 percent is a unicorn."

### Why chip P&R is trusted

fpgaminer: chip designers "had to build rule checkers to ensure that, 99.99% of the time, if the rules pass, their design will work … nobody looks at the layout" ([HN](https://news.ycombinator.com/item?id=17240333)). PCBs differ:
- through-vias block every layer;
- "4 layers (... only 2 are really used for general routing)";
- components are obstacles;
- ICs have dedicated power metal.

### Probe vs producer

**As a probe:**
- "a quick autoroute to visualise where routes 'wanted' to go";
- "If it chokes it usually means my board layout and pin assignment were bad";
- "a good way to double-check that your floor planning is OK, even if you then rip up".

**As a producer,** trusted only for buses, fanout and low-speed GPIO:
- "All of them work great *given the information available from the schematic* - which isn't *nearly* enough" (triffid_hunter).
- Group-selected routing works because "the human is selecting what's likely to route" (Dave Jones).
- From scratch it rarely gets "over 80%". Finish interactively to >90%, then autoroute the rest (janvi).

**Comparisons.**
- **EEVblog 1535:** same board, same net classes. DeepPCB took about 2 h and stayed incomplete with 77 vias. Freerouting finished in 10 min with 49 vias. The human used 88 vias, many for stitching [Sys/A].
- **cyberfish 2010:** Freerouting beat hand routing on a 2-layer board (11 vs 18 vias), but put a trace between crystal pins and used thin power traces.
- **devbisme:** "I tested seven tools that actually created a routed PCB and they all used Freerouting" [Sys/A].
- **CadMust-Neo annealing:** HPWL got 16.5% worse, with overlaps and parts outside the outline [A].

### LLM-era reports (2024–2026)

**Good at:**
- **Review.** "$1-2 of tokens saved me from $70-80 bugged PCBs". It handled a 40-page, 1,200+-component schematic and found swapped pins and open-drain misuse.
- Pin-swap questions, stackup and part configuration.
- Writing DRC rules for classical routers, and prioritizing nets.
- **Analysis code.** A DC IR-drop FEA over 40+ power nets. An AC PDN model validated against a DSO FRA measurement.
- HV/LV separation, with silkscreen warnings.
- **Reading failure clusters.** Staggering U6–U10 took one board to 314/314 nets on 4 layers. The LLM there was "a competent junior collaborator with encyclopedic memory, infinite patience, and no physical intuition" [A].

**Bad at:**
- **Geometry**: "their geometric intuition is nonexistent".
- **seveibar, after ~15 AI-designed boards**: "1) Improperly rotated connectors (backwards USB port) 2) Endless routing loops for complex boards 3) Really huge/unreadable single page schematics".
- **Other failures**:
  - BGA escape (~70 unroutable nets on 6 layers) and snaking micro-traces;
  - unrequested edits ("changed I2C to SPI for no reason");
  - looping on DRC ("Would a real EE vomit if they looked at it? Maybe.") and exporting with 31 nets unconnected;
  - scoreboard gaming: it "rewrote the score-board so the result looks better" and "wrote a bypass for unsolvable errors";
  - writing its own placer ("That is the wrong direction").

**The structural gap:** "The model (agent) has no way to validate its work." Software has a loop where "'This is wrong, fix it' + recompile, can happen twenty times in ten minutes"; hardware has nothing like it.

**Vendor limits.**
- **Quilter (practitioner review):** "Can't do HDI … microvias … complex breakouts from BGAs … anything high density (… max 20 pads per sq cm)"; about $1 per pin; trials require consenting to training on your data.
- **Quilter's own scope** is in §0.
- **DeepPCB** is "Not for … DDR nets, length matching, advanced impedance control, and RF".
- **JITX GenAI test:** models are best at "pulling concrete data out of human-shaped data sources". The generated op-amp front end was "three times the cost and size" of TI's, and "missing many of the necessary connections" [Sys/V].

### What would earn trust (PD's 11 requirements)

1. **Deterministic tools judge.** "I did not want the AI itself deciding that a PCB was correct. KiCad does the verification" (KiCad Agentic MCP: 202 tools, undo, <1 s operations vs 6–7 min of LLM thinking, 18/18 golden tasks).
2. **Bounded, commanded chunks.** "work with me to do a satisfactory job on a little chunk... give me some time to review it"; "autoroute, but just one thing at the time on my command".
3. **Predictable, few settings.** craftyjon: automation "relatively straightforward, predictable, and can be implemented without a bunch of settings". twl: "We don't want to have a poor quality autorouter making a big mess" ([forum](https://forum.kicad.info/t/autoroute-is-it-coming-mod-edit-short-answer-is-not-in-the-foreseeable-future-so-nothing-to-see-here/30441)).
4. **Never touch known-good work.** "Do not make unsolicited edits... Make the minimum change required."
5. **Explanations.** Without them "you can't easily verify the boards or quantify the quality". DeepPCB admits RL "can't explain their reasoning".
6. **100% routed ≠ finished.**
7. **Honest self-evaluation.**
8. **Accuracy.** "60 percent of the tasks at a 50 percent accuracy rate is absolutely useless."
9. **Determinism.** "deterministic scripts that produce the same board every time, with AI involved only where there's a real judgement call."
10. **Cheaper than doing it by hand, setup included.** "faster to do it by hand than to explain to LLM what I want."
11. **Data provenance and IP.**

Practitioners also want declarative constraints ("this trace carries 100mA"), visual entry ("minimum current: 5A … 'route shortest possible'"), progressive constraints "like CSS", escape hatches, and a conversational UI ("autorouting is largely a UI problem"). They will accept a tool that can "be good even if you can't be perfect", but want proof before trust.

**Implications for our system.**
- **Make the check deck part of the product**, so that passing predicts function, as chip P&R deck results do. Cover return paths, hot loops, decap loops, connector orientation, footprint vs datasheet, width vs declared current, keepouts, creepage and similarity to the reference. This is seveibar's call to "soup up all our collective design rule checks".
- **Keep the LLM upstream of the solver.** It infers constraints, ranks nets, configures DRC and the router, and reads failure clusters. It never emits raw copper (§9).
- **Scope every action** to a block or net set, with a diff, render, physical rationale, locks and undo. Offer an incremental-ECO mode ("greenfield layouts … are hard", edits are easy).
- **Harden the harness.** The agent cannot change it, must predict results before checking, and never treats "100% routed" as terminal.
- **Make constraint entry cheaper than hand layout:** auto-detect, then confirm.
- **Ship the reviewer first.**

---

## 4. The master review checklist (EW Q4–Q5)

### Structure

About 30 checklists merge into **299 items across 24 categories**:

| Category | Items | Category | Items | Category | Items | Category | Items |
|---|---|---|---|---|---|---|---|
| Process | 18 | Power conv. | 9 | EMC | 10 | Assembly | 13 |
| DFM | 27 | Ground | 13 | Thermal | 6 | Test | 13 |
| Stackup | 12 | High-speed | 24 | Footprints | 13 | Silk | 14 |
| Mechanical | 21 | RF | 6 | Routing | 11 | HV | 3 |
| Placement | 27 | Analog | 4 | Zones | 7 | Outputs | 13 |
| PI | 15 | Flex | 7 | Paste | 5 | Panel | 8 |

**Severity:** C = 41, M = 151, m = 107.

**Automation:** A = 101, A/S = 9, S = 119, S/J = 4, J = 66. That is about 37% automatable now, about 41% more once a role model exists, and about 22% left to judgment or simulation. Of the 41 Critical items, 19 are A, 14 S, 1 S/J and 7 J, so 83% are at least semi-automatable.

The author assigned these tags. Sources disagree on thresholds, so thresholds come from a fab profile. Examples: silk height 25 mil, 1.0 mm or 50 mil; edge clearance 8 or 10 mil; part-to-edge 125 mil or 5 mm.

### All 41 Critical items

Auto classes: A = DRC or geometry; S = needs roles or datasheet data; J = judgment or simulation. KiCad keys are verified by VK.

| ID | Check | Why | Auto |
|---|---|---|---|
| PRC-01 | Schematic signed off before layout; swaps back-annotated and re-reviewed | Errors carry forward | S |
| PRC-02 | Board/schematic parity | LVS | A (`missing_footprint`, `extra_footprint`, `duplicate_footprints`, `net_conflict`, `footprint_symbol_mismatch`) |
| PRC-03 | Zero unrouted; no polygon breaks | Opens | A (`unconnected_items`) |
| PRC-04 | DRC clean; every waiver signed | Waivers hide defects | A+J |
| PRC-05 | Rules from fab/CM capability before layout | DRC otherwise meaningless | S→A |
| PRC-12 | Severity overrides and "ignore" settings audited | "Anything on 'ignore' makes a clean pass hollow" | A (`ignored_checks[]`) |
| DFM-02 | Annular ring ≥ fab/IPC minimum (5 mil Cl.2 / 7 mil Cl.3 on 10 mil vias) | Breakout | A (`annular_width`) |
| DFM-03 | Hole-to-hole and hole-to-copper clearance | Breakout, shorts | A (`hole_clearance`, `hole_to_hole`) |
| DFM-11 | PTH ≥ lead + ~0.2 mm; pad ≥ hole + 10–15 mil; soldered holes plated | Won't insert | S |
| DFM-21 | No co-located drills; PTH and NPTH separated | Broken bits | A (`holes_co_located`) |
| STK-01 | Stackup verified with the fab | Impedance | J |
| STK-09 | Every impedance net matches a class pattern (else it silently gets Default, e.g. USB D±) | Silent miss | A (coverage report) |
| STK-12 | Stackup drawing plus "Layer N: Z ±tol, referenced to Layer M" | Top fab-hold cause | J |
| MEC-01 | Outline and holes fit the enclosure (3D) | Fit | S |
| MEC-04 | Connectors match the mating standard (orientation, key, pin 1, FPC contact side) | Mis-mating | J |
| MEC-08 | No collisions or courtyard overlaps | Unassemblable | A (`courtyards_overlap`) |
| MEC-15 | Board thickness specified and matching | "often … overlooked" | J |
| MEC-17 | Board-to-board connectors aligned | Mating | S |
| PLC-27 | Power-stage order: IC → input cap (placed and routed, no vias) → L/diode → output cap → small-signal → single-point ground | Hot loop | S/J |
| PDN-05 | Every power and ground pin connected; vias to plane | Floating supply | A |
| PDN-06 | Widths sized for current and temperature rise | Burn-out | S |
| PDN-13 | Width computed for every track >100 mA (~10 mil/A on 1 oz external at 10 °C rise) | Overheating | S |
| PWR-01 | Switching hot loop of minimal area | di/dt radiation | S+J/sim |
| PWR-07 | Connectors and regulators current-rated in the chosen package | Overheating | J |
| GND-02 | HS nets don't cross splits or voids; else stitching caps (≤1 µF) or vias | Antenna | S |
| HS-01 | Diff pairs held at the impedance gap; uncoupled length limited | Mode conversion | A (`diff_pair_gap`, `diff_pair_uncoupled`) |
| RF-04 | Antenna/module keep-outs per datasheet | Detuning | A once drawn |
| FP-01 | Footprint matches the ordered package; pinout matches | Unassemblable | S |
| FP-02 | Pinout drawing read in the right view (top vs bottom) | Mirrored | J |
| FP-05 | Mask apertures on all pads | Unsolderable | A |
| FP-12 | SOT-23 pinouts verified (N/P, NPN/PNP; GSD/BCE) | Common flip | S |
| ZON-01 | Zones refilled after the last edit and before CAM | Stale fills | A |
| PST-01 | No untented via-in-pad (except low-power QFN) | Wicking | A |
| ASM-13 | Orientation checked in the assembler's preview; DNP parts not auto-matched | PCBA error | J |
| HV-01 | Creepage and clearance by voltage, including between layers | Arcing | A (`creepage`, `clearance`) |
| HV-02 | Isolation barriers sized | Safety | S |
| CAM-01 | DRC and zone fill re-run just before export | Stale outputs | A |
| CAM-03 | Uploaded files are the latest and complete ("Yes, this does happen") | Wrong build | S |
| CAM-07 | RS-274X/X2; Excellon with tool list; 1:1; consistent units and offsets | CAM errors | A |
| FLX-03 | Bend radius met per flex region | Cracks | S |
| FLX-05 | No vias, parts or joints in bends or near transitions | Stress | A (rule areas) |

### Most-consensus Major items

The source count measures how many checklist authors agree, not how often the failure occurs. Same-publisher sources inflate it.

| ID | Check | # src | Auto |
|---|---|---|---|
| DFM-04 | Copper-to-edge ≥10 mil (Sierra) / 8 mil (SparkFun) unless edge plating noted | 7 | A (`edge_clearance`) |
| PDN-01 | Decaps close, one per pin (Altium <15 mm); Critical for fast ICs | 7 | S |
| SLK-01 | No silk on pads, vias or exposed copper | 7 | A (`silk_over_copper`) |
| ASM-01 | ≥3 asymmetric global fiducials; 2 local at fine pitch; 40–118 mil | 6 | A/S |
| ASM-02 | Polarity/pin-1 marks visible after assembly | 6 | S |
| DFT-01 | Test points on rails and critical signals | 6 | S |
| HS-05 | Stubs and layer changes minimized | 6 | A/S (`via_count`) |
| PLC-02 | Functional grouping; domains separated | 6 | S |
| THM-01 | Thermal reliefs except heat-sinking or high-current pads | 6 | A (`zone_connection`) |
| ANA-02 | Analog separated from SMPS and digital | 5 | S |
| CAM-04 | Fab drawing: datums, drill/stackup/impedance tables, class, finish | 5 | J |
| DFM-01 | Don't push fab limits (10 mil typical, 6 mil absolute minimum) | 5 | A (margin report) |

EW's Tier-S priority list adds these Majors:
- **GND-10:** ≥1.5W from voids and ≥90 mil from plane edges (TI).
- **GND-03:** return vias at layer changes.
- **PDN-02/11/15:** smallest cap closest; own vias; staged BGA decaps.
- **PWR-02:** switch-node area.
- **EMC-06/07:** filter at the exit; ESD pad in series with the trace.
- **PLC-07/24:** crystal next to its IC; nothing unrelated within 1 inch.
- **HS-17/18:** stubs <15 mil or backdrill, ~30 mil antipads; equal via counts on both sides of a pair.
- **THM-03:** tombstoning. UWARG requires the copper ratio between pads to stay <2× on ≤0805; kicad-happy flags <0.3 as high risk.
- **ASM-09:** Sierra spacing, 0402 12 mil / 0603 21 mil / 0805 30 mil.

(DFM-05 and DFM-25 name microvia DRC keys that exist only on master; see §0.)

### Respin and fab-hold data

There is no rigorous public breakdown of respin root causes.

**Analyst and survey figures:**
- **Lifecycle Insights 2018** (via vendors): "average number of design respins is 2.9 per project … approximately 16 days … more than $82,000". Other citations give 2.8 respins and $28.5k, $44k or $46k per respin; the original report was not found.
- **Aberdeen 2010:** 14.1 vs 3.8 prototypes; prototypes are 31% of product cost.
- **PCD&F 2025 survey:** "Nearly 60% produce just 1–5 respins a year."
- **Dana Korf:** "less than 2–20% of the designs transfer to manufacturing perfectly without any deviation requests or TQs", and 25–50% of a fab's front-end engineering goes to DFM review.

**Vendor-reported:**
- **AtlasPCB** [V], over 10,000+ orders, ranks hold causes as below, and claims "95% … preventable with a 15-minute pre-submission check".

  | Hold cause | Share |
  |---|---|
  | Missing or ambiguous stackup | 28% |
  | Undefined impedance | 22% |
  | Drill-to-copper | 18% |
  | Incomplete fab notes | 15% |
  | BGA annular ring | 12% |

- **dev.to vendor post** (low confidence): >60% of designs have a DFM issue; trace/space 45%, annular ring 38%, drill-to-copper 32%.

**Qualitative:** Sierra names tombstoning, bridging, misalignment and polarity as the top assembly defects. Flux says return-path errors cause "a disproportionate share of EMI failures". Adom: "Never trust a clean ERC" ("MCU VCAP pins with no capacitors. Board dead, ERC green").

### Critic tiers

**Tier A** (deterministic, continuous):
1. Generate `.kicad_dru` from the role model and fab profile.
2. Run `kicad-cli pcb drc`.
3. Map each violation to a checklist ID.
4. Audit overrides first, then group findings by root cause.

**Tier S** (semantic geometry):

```
critic(board, roles, profile) -> [Finding{id, severity, objects, measured,
                                          threshold, threshold_source, evidence_png, fix}]
```

Priority: (1) stackup/impedance/fab-note completeness and class coverage; (2) plane continuity, including void and edge distance; (3) current capacity; (4) decap distance, order and vias; (5) hot-loop and switch-node area; (6) return vias; (7) ESD and exit filters; (8) crystal isolation; (9) HS via stubs and symmetry; (10) tombstoning; (11) assembler spacing.

**Tier J:** the LLM receives a structured packet (item text and rationale, datasheet excerpts, roles, cropped renders, A/S numbers). It answers pass, fail or uncertain, with evidence. Uncertain goes to a human. HS-08/14, FLX-07 and PWR-01 EMI go to simulators.

**Scoring:** Criticals gate, Majors are weighted penalties, minors and aesthetics are soft.

**Implications for our system.**
- **Ship the checklist as data:** ID, severity, automation class, threshold with source, KiCad key.
- **Order critics** documentation/spec → geometry → physics, matching where fabs place holds. The cheapest high-yield critics are fab notes, class coverage, parity and footprint/pinout.
- **Threshold provenance:** datasheet > fab profile > house default. Label tool heuristics.
- **Every finding** carries measured value, threshold, source, image and one fix.
- **Escaped-error log** that adds new items, as azonenberg, colinb and Tanner do.

---

## 5. Quantifying "looks right"

These are EW's proposed, uncalibrated metrics:

| Heuristic | Metric |
|---|---|
| Consistent orientation | Orientation entropy over {0, 90, 180, 270} per part class; polarized parts' modal-direction fraction |
| Pin-1 alignment | Fraction of ICs matching the modal pin-1 vector |
| Grids (100/25 mil, 0.05", 5 mil) | Grid-snap ratio for footprints, vias and 0.1" headers |
| Rows/columns | Collinearity clusters |
| Short, uncrossed airwires | HPWL/MST plus MST-edge crossings |
| No scenic routes ("spiral around the board three times") | Routed/Manhattan ratio outliers |
| Compact power loops | Hot-loop polygon area; switch-node copper area |
| Decap tightness and order | Cap-to-pin path length; Spearman(value, distance) |
| Text | ≤2 directions; bottom text mirrored |
| Geographic designators | Spearman(number, row-major position) |
| Pad exits | Off-centre or long-side exits |
| Neatness vs crosstalk | Parallel-run length between nets that aren't pairs |
| Channel symmetry | RMS pose deviation after isomorphism mapping |
| Signal flow | Fraction of inter-block edges pointing input→output |

PD adds:
- turn count, or "wiggle";
- a penalty for any-angle routing;
- consistent power-trace width ("random thick traces");
- connector orientation and "which way is up";
- grouping that matches the schematic sheets.

kicad-happy already implements some [P, tool heuristics]:
- decap within 10 mm of the IC, on the same net and side;
- tombstone copper ratio (<0.3 high risk, 0.3–0.6 medium);
- a trace-proximity grid;
- per-net layer-transition counts.

KiCadRoutingTools (KRT): "crossings and hpwl … are indifferent between a sensible layout and a scattered one". No study links aesthetics to SI, EMC or reviewer acceptance, and no human-rated aesthetics dataset exists.

**Implications for our system.**
- Use a cheap T0 convention score as a soft objective and review diagnostic, always paired with a coupling penalty.
- Calibrate it on expert-rated boards. That dataset still has to be built.
- Make a per-company style profile (grids, orientations, angles, silk rules) part of the configuration.

---

## 6. Constraint and intent representation

### KiCad 10 `.kicad_dru` (VK-verified)

**Grammar.** `(version 1)`, then `(rule name [(severity)] [(layer)] [(condition "expr")] (constraint …)…)`. **The last matching rule wins**, so write specific rules later. The traps are in §0.

**Constraints:**
- clearance, physical_clearance, creepage, edge/courtyard/hole clearance, hole_to_hole;
- annular_width;
- track_width, track_angle and segment length;
- length and skew (`within_diff_pairs`; both accept time units);
- diff_pair_gap and uncoupled length;
- via_count, disallow, assertion, connection_width;
- zone, thermal, text, silk, mask and paste.

**Functions:**
- `fromTo`: pad paths, case-insensitive, and the path must be unique;
- `intersectsArea` and `enclosedByArea`;
- `intersectsCourtyard` (plus Front/Back);
- `hasNetclass`, `hasExactNetclass`, `hasComponentClass`;
- `memberOfSheet(OrChildren)`, `memberOfGroup`, `memberOfFootprint`;
- `inDiffPair`, `isCoupledDiffPair`;
- `getField`, `existsOnLayer`, via-type tests, `isPlated`.

Any registered property is readable (`A.Orientation`, `Pad_To_Die_Delay`).

**Supporting features:**
- component classes, assigned by reference, footprint, side, rotation, field, sheet or expression;
- tuning profiles: per-layer width, gap and delay plus via delays, set per net class;
- rule areas and Repeat Layout;
- a graphical editor that writes the same file. Its "Permitted layers" and "Allowed orientation" become `assertion`.

**KiCad can enforce** courtyard spacing, side and orientation (via `assertion`), area containment, and edge or keepout distance. **It cannot express** footprint-to-footprint pad distance (only a post-route `fromTo`+`length` proxy), alignment, symmetry or loop area. KiCad 11 adds `return_path(layer, net)`, net-chain rules and a `CustomRule` protobuf.

### Other models

| System | Model | Notable features |
|---|---|---|
| Altium [P] | Query-scoped unary/binary rules, e.g. `InNet('VBAT') And OnLayer('Bottom Layer')`, `InFromTo`, `InxSignal`, `WithinRoom` | Explicit numeric priority per rule type, except that **all Matched Lengths rules apply**. Rooms are confinement constraints that move their parts |
| Allegro CM [3P/Snip] | CSets per domain (Electrical, Physical, Spacing, Same-Net), each with a DEFAULT, assigned to nets, classes and regions | Electrical modes: stub length / net schedule, max/match via count, max exposed length, pin-pair delay, relative delay, max parallel (≤4 length:gap), impedance, total etch, layer sets, xtalk, **Return Path DRC**. Package-to-room placement. Match groups resolve to pin pairs with Scope, Delta, Tolerance and Target ("Match" vs "Relative") |
| JITX [P] | Tags (Python classes with inheritance) + boolean conditions + effects (width, clearance, thermal relief, stitch and fence vias) | Resolution order: effect type → satisfied → explicit priority → **global logical specificity** → local specificity → tie-break. SI on `>>` pad topologies with Bridging/Terminating pin models, RoutingStructure, Timing/TimingDifference/InsertionLoss, Signal Tuning regions. Placement is a kinematic tree. Port forwarding lets reusable blocks carry constraints |
| tscircuit [P] | Placement props, edge anchors, pad-relative `calc(R1.pin1.minX - 2mm)`, `<constraint xDist>` | Grid/flex/pack groups (beta); `<bus maxLengthSkew>`, `<differentialpair>`, `<breakout>`; `<drccheck checkFn>` for custom DRC |
| atopile [P] | `assert … within 3.3V +/- 10%`, solver equations | Layout reuse by sub-build plus "pull group". No geometric vocabulary; syntax in flux |
| Quilter [P/VK] | 7 constraint types: Bypass Caps (parent-pin priority), Switching Converters (`U`/`L` refdes, ≥2 caps), Crystals, Power Nets, Timing (soon), Diff Pairs, SE Impedance | 8 PRCs with units and pass criteria: Pin Distance (e.g. 0–1 cm), Layer Switch Count, Ground Plane Overlap (all but the last 2×clearance), Trace Path Length, Length Mismatch, Uncoupled Spacing, Invalid Width Span, Overheated Length (% of net with rise >20 °C, e.g. 0–10%). Unconstrained nets are treated as generic |
| ALIGN [P] | Typed Pydantic `.const.json`; HardConstraint `translate(solver)` | UserConstraints expand into primitives (SymmetricBlocks, GuardRing, NetPriority…) |
| FloorSet [P] | Hard constraints: fixed outline, shape, boundary, grouping, multi-instantiation, pre-placement | ICCAD 2026 Problem C |
| KRT `floorplan-intent.json` [P] | Strict keys: zones, keepouts, edge connectors, decaps, `proximity[]` {ref, near, max_mm, basis}, keep_away, replicate, fixed_poses, must_lock, legality_budget | Unknown keys refused; acts as a monotone per-move gate |
| IPC-2581C [P] | Impedance spec (value and tolerance; SingleEnded / EdgeCoupled / Broadside / CPW with width, spacing, RefPlane), Loss, `netClass` enum, `netPair`, DFX criteria and responses (APPROVED / WAIVED / REJECTED) | **No** clearance, length or placement rules. KiCad's exporter writes **no Impedance spec** |

**Academic work:**
- GNN symmetry-constraint extraction (arXiv 2312.14405).
- LLANA: LLM priors for Bayesian optimization (2406.05250).
- PCBSchemaGen: per-IC knowledge graph plus a 5-layer verifier, 81.3% on schematic tasks (2602.00510).
- The notes found no PCB layout-intent language and no paper on LLM extraction of layout rules from datasheets.

### "Keep C5 within 2 mm of U1-7, with a via to GND"

| System | How it expresses this |
|---|---|
| tscircuit | Constructively, with `calc()` |
| Quilter | A bypass constraint, graded by PRCs |
| KRT | `proximity[]` |
| KiCad | Post-route only: `fromTo('U1-7','C5-1')` + `length (max 2mm)` |
| IPC-2581 | Cannot express it |

So the IR needs native `proximity` and `via_to_plane` primitives.

### Proposed IR `pcb-intent/0.2` (CVB; untested)

**Format.** Strict YAML/JSON that rejects unknown keys. `resolution: specificity | explicit_priority`. JITX-style tags bound to KiCad selectors (`U1-7`, `${Class:BUCK1}`). Topologies are pad paths through series parts with bridging and delay models.

**Constraint kinds:**

| Kind | Content |
|---|---|
| `bypass` | High-level. `expands_to` [prox, gndvia, loop, layersw]. `provenance` {source, doc, page, confidence, confirmed_by} |
| `proximity` | `max`, `basis: pad_edge`, hard. Compiles to checker `geom.pad_distance`, optimizer hinge_sq, KiCad fromTo/length proxy |
| `via_to_plane` | plane net/layer, `max_via_distance`, `min_vias` |
| `layer_switch_count` / `loop_area` | Path with `max` / `max_mm2` |
| `match_group` | relative to target, `tol_ps`. Compiles to a time-domain tuning profile and a skew rule |
| `impedance` | ↔ IPC-2581 EdgeCoupled |
| `region` / `cluster_tight` / `edge_placement` / `symmetry` | Rect+side / anchor+`max_span` / edge+overhang / pairs+axis |
| `overheated_length` | `max_rise_c` 20, `max_fraction` 0.10 |

Findings records: constraint_id, measured, limit, unit, severity, objects, location, response (open / approved / waived / rejected).

**Design rules:**
1. Hard/soft split, with a monotone gate on hard constraints.
2. High-level intents expand into primitives; the LLM writes the intents.
3. Every primitive has a checker with units and pass criteria, plus a KiCad compilation where possible.
4. Specificity resolution, emitted general→specific so KiCad's last-match rule agrees.
5. Timing lives on topologies and match groups: length belongs to pad paths, not nets.
6. Provenance and human confirmation for every extracted constraint.
7. IPC-2581 mapping for impedance and loss.
8. A DFX-like channel for findings and waivers.

**VK refinements:**
- Emit skew directly in `ps`. The sketch's "0.8mm, ~6.3 ps/mm illustrative" is unnecessary.
- Prefix rule names `IR:<id>`.
- One condition per rule.
- Units mm/deg/ps only.
- Target KiCad 11's `CustomRule` protobuf as a second backend.

**PD's practitioner `intent.yaml` fields:**
- net classes with current and edge rate;
- hot-loop member sets;
- decap targets per pin group;
- which end each terminator goes on;
- star point and order;
- keep-outs ("no power under IMU");
- connector edges and orientation from the enclosure;
- locked "stake-in-the-ground" regions;
- reference copies;
- a style profile.

CadMust (self-measured, 161 parts): LLM placement constraints from the schematic alone matched about 70% of a hand-written baseline; adding datasheets for two ICs raised that to about 95% [A]. One critic: this "replaced the act of dragging the select box … and clicking 'Add Room'".

**Implications for our system.**
- **`pcb-intent` is the single source of truth.** The LLM writes intents with detection evidence. Deterministic code expands them. Each constraint carries a confirmation flag.
- **Compile three ways:**
  - a strict `.kicad_dru`, linted by running `kicad-cli` on a scratch copy;
  - Python PRC checkers, which on 10.x are the only way to check proximity, alignment, symmetry, loop area and via-to-plane;
  - optimizer penalties.
- **Carry intent in KiCad's own objects.** Roles go in component classes. Impedance and timing go in net classes plus tuning profiles, written with `SetNetClasses`.
- **IPC-2581:** import impedance specs from it, but never expect KiCad to export them.
- **KiCad 11:** retire the custom return-path checker once `return_path` ships.

---

## 7. Evaluation stack (fast → slow)

| Tier | When | Checks | Tools and evidence |
|---|---|---|---|
| T0 µs–ms | Every move | Overlap and out-of-bounds; IR/PRC geometry; HPWL; crossings; Transcalc Z0 and delay; IPC-2221/2152 widths; overheat proxy; convention score | In-process code; KRT-style intent grader; PDN DNN (0.1 s) |
| T1 s | Accepted moves and route batches | `kicad-cli pcb drc --format json --refill-zones --schematic-parity --exit-code-violations`; return-path VOID/SPLIT/VIA flags; NRR/PRR; routability probe | `return_path` (0.05 mm A* raster with loop-area estimate); KRT ≈0.65 s and Freerouting 2.1.0 ≈7 s per small PCBWorld board |
| T2 s–min | Gates | DC IR drop, PDN impedance vs target, coupled noise, near field | padne, KiPI, Ki-PIDA, emcvisual (within 1 dB of openEMS, 30–350 MHz) |
| T3 min–h | Finalists | openEMS S-params, TDR and delay per critical net; FEM thermal | gerber2ems + si-wrapper + scikit-rf (≈34 s per excited port in the sample: 3.37 ms × 10k steps); FreeCAD/gmsh/CalculiX or Salome/Elmer; Palace for C/L |

### KiCad 10 backend (VK)

10.0's IPC has no DRC, rules, export or headless mode. The recommended split:
1. **IPC** for CRUD in commits, placing library footprints via `ParseAndCreateItemsFromString` from `.kicad_mod` text, followed by an `UpdateItems` pass for nets.
2. **Direct `.kicad_dru` writes.**
3. **`kicad-cli` DRC** on a saved copy as the referee.
4. **A short-lived SWIG helper** for DSN/SES. Lock copper and strip the SES placement first.

Refill is asynchronous: poll before reading the board. Freerouting `-drc` writes the same `drc.v1` format plus a `freerouting_version` key. KiCad 11 adds `kicad-cli api-server`, rules over IPC and export jobs, and plans to drop SWIG.

### Tool notes

| Tool | Notes |
|---|---|
| gerber2ems (Apache-2.0) | 5 µm pixels; grid 50/200/500 µm with pitch ≤ λmin/10; ports ≥8 cells; caps shorted; field dumps can reach "hundreds GB" |
| si-wrapper (KiCad 9.0.x) | Slices a net with neighbours, vias and planes; shorts passives; terminates neighbours; auto-places ports. Adaptive grid, diff pairs, delay. VNA-validated on a DDR5 clock pair; runs in CI |
| Solvers | openEMS GPLv3+; Palace (Apache-2.0) C/L extraction with AMR; FastHenry, FastCap, scikit-rf |
| padne | 2.5D FEM from schematic directives (`!padne VOLTAGE v=3.3V p=U1.1 n=U1.4`). The core is ~40 lines; "the vast majority of work … is ferrying data around". Via model uncertain |
| KiPI | DC drop, AC PDN impedance vs target, coupled noise |
| Ki-PIDA | Electro-thermal mesh |
| PCB_SI_Toolkit | Decap distance, plane edge 3×h, reference changes without ground vias, 2D Z0, NEXT |
| kicad-happy EMC | 44 rules (kicad-emi-guardian, by contrast, disclaims compliance use) |
| Antmicro thermal | FreeCAD 1.0 + CalculiX 2.20; validated on an RPi5 enclosure at 2.5/8 W |

The KiCad core has no SI/PI plans: a forum request went unanswered, and issue #8398 has stalled.

### Surrogates

- **PDN DNN:** trained on >1M BEM-labelled boards; 0.1 s per answer, 5000× faster than full-wave (a snippet says 10,000×).
- **DevFormer/DPP:** >30% fewer decaps; `decap_sim()` and RL4CO; used by ReEvo for heuristics an LLM discovers.
- **SI eye-metric surrogates:** neural nets win with ample data, anisotropic GPR when data are scarce. Amortized optimization loses ~10% optimality for 10³–10⁴× speed.
- **Crosstalk:** MLP and LS-SVM [Snip].
- **No layout-level EMI or thermal surrogate exists.**

**Implications for our system.**
- **Tier placement.** T0/T1 run inside the placement loop, T2 at gates, T3 for finalists. Every verdict goes to the findings channel.
- **Calibrate proxies against T3** before using them as rewards. Antmicro's VNA slices and emcvisual's 1 dB agreement are precedents.
- **Measure our own tier runtimes.** No published DRC or padne/KiPI timings exist.
- **Train surrogates** on synthetic KiCad boards labelled by padne, KiPI, return_path and si-wrapper (the PDN-DNN recipe).
- **Give the LLM summaries only:** scores, unrouted counts, grouped violations and hotspots.

---

## 8. Quality metrics

| Source | Metrics |
|---|---|
| PCBWorld [P] | **CP** (connected, 0 error-level DRVs); **Potential gain Φ** over unconnected, DRV, WL and vias; Routability, DRV, WL, Via, Time, Parse-fail. @5 = best of five by Φ. Time averaged over all rollouts. DRC re-run on saved boards against each board's own rules |
| OmniRouting [P] | **PR** (loads); **NRR** (% nets connected and clean); **PRR** (% of Σ(\|Pₙ\|−1) pad connections, missing outputs kept in the denominator); **Open, PShort** (only different-net wire–wire or via–wire contacts), **NShort**; violations by cause; Polygon; TWL; vias; layers; RT |
| OmniRouting MGS | Pad-aware layer graphs at coarse corridor and fine geometry scales, coarse weighted more. Measures agreement with the expert, **not correctness** |
| Quilter [P] | % pins routed; DRC count (DRC-failing candidates hidden); sides; layers; min width; clearance; via/drill; via count; PRCs |
| Cypress [P] | Routability = % pin pairs routed by Freerouting v1.9.0 on two free layers at defaults; track length; runtime |
| RL_PCB | HPWL, Euclidean WL, overlap, post-route WL vs SA |
| Freerouting v2.5.0 [VK] | `V2_CONTINUOUS` = max(0, 1000 − W1·o1 − W2·o2 − W_C·N_viol/D − W_D·ΣL/(U·D)), with W1≈333.3, W2≈666.7, D = max(1, pins × signal layers). `V2_LOWER_BOUND` copper efficiency, with vetoes |

**Cautions:**
- **Human boards are imperfect.** The human reference scores NRR 93.58%, PRR 95.91%, Open 4.38% and PShort 0.38%.
- **Routing metrics don't prove boards work.** Quilter: not without first-pass yield data [Snip].
- **HPWL and crossings are blind to intent** (KRT).
- **No validated figure of merit exists for RL** (AndyC_772).

**Union set (CVB):**
- **Gates:** loadable, LVS, CP.
- **Routing:** NRR, PRR, opens/shorts, DRV by cause, TWL, vias, layers, RT.
- **Placement:** HPWL, overlap, out-of-bounds, crossings, separation, Cypress routability, intent conformance.
- **Physics:** pin distance, layer switches, plane overlap, mismatch, uncoupled spacing, overheating, return path, IR-drop margin.
- **Human-relative:** MGS plus WL/via/HPWL ratios.

Normalize against human scores. Use MGS as a diagnostic only.

**Implications for our system [digest].** Add:
- checklist Critical/Major pass counts;
- the convention score;
- blind expert acceptance and review time;
- out-of-scope edits;
- determinism (board hash);
- setup minutes;
- prediction accuracy.

---

## 9. Benchmarks and datasets (corrected numbers)

**There are no PCB problems in ISPD or ICCAD contests.** ISPD 2005–2027 is all IC or FPGA. ICCAD routing problems are IC-level. ICCAD 2026's problems are LLM netlist work, failure bucketing and FloorSet.

### PCBWorld-Bench (v1.1.0)

BSD-3 licence, GPLv3 engine, KiCad 9.0.8.

| Split | Boards | Nets | Pads | Layers |
|---|---|---|---|---|
| D1 (grid) | 10,000 / 128 / 128 | 5 | — | 1 |
| D2 (gridless) | 10,000 / 128 / 128 | 4–6 | — | 2 |
| D3-A | 100 | 2–13 | 6–31 | 2–4 |
| D3-B | 287 | 5–42 | 31–100 | 2–4 |
| D3-C | 292 | 6–451 | 101–2,103 | 2–4 |

D3 is 679 boards from PCBench's corpus. Each was converted with its own rules and kept only if still connected and DRV-free, with the human copper as reference. Zero-shot evaluation uses 99 D3-A and 10 D3-B boards; D3-C is the challenge split.

**CP @5, VK VERIFIED** ([arXiv v2](https://arxiv.org/html/2607.05915v2)):

| Method | D3-A | D3-B |
|---|---|---|
| Freerouting 2.1.0 | 0.80 | 0.78 |
| KRT | 0.74 | 0.20 |
| OrthoRoute | 0.02 | 0.00 |
| PPO (synthetic) | 0.86 | 0.45 |
| PPO (no finish) | 0.94 | 0.42 |
| GPT-5.4 interactive | 0.65 | 0.00 |

On D3-A, GPT-5.4 scores CP 0.65 when interactive, 0.19 when it plans then executes, and 0.02 without the engine (DRV 1.31 / 16.28 / 34.58). The paper's conclusion: "Leveraging the native API is essential for design-rule-clean routing."

**Seconds per rollout:**

| Router | D2 | D3-A | D3-B |
|---|---|---|---|
| Freerouting | 2.69 | 7.09 | 9.94 |
| KRT | 0.82 | 0.65 | 3.27 |
| PPO | 0.43 | 1.83 | — |
| GPT-5.4 | — | 231 | 866 |

DeepPCB claims "the top one-attempt score on both test sets" [V].

### PCBench

The README says 164 PCBs (KiCad files, PCB-RDL JSON, PNG, grid RL environment). **Conflict:** PCBWorld derives 679 boards from it, and Freerouting's "PCBench table" covers 1,157 [VK]. Licences are unverified.

### Freerouting v2.5.0 corpus

| Measure | v2.4.1 | v2.5.0 |
|---|---|---|
| Clean | 358 (30.9%) | 868 (75.0%) |
| Fully routed | 600 | 872 |
| Timeouts | 78 | 78 |
| Total time | 3,251 s | 2,997 s |

Boards with 6+ layers reach 49.2% clean.

### Cypress (Apache-2.0, built on DREAMPlace)

- **Benchmarks:** the slides list 10 small plus 5 commercial; the repo ships 20 small.
- **Model:** two-sided SMD placement with fixed sides, spacing and non-overlap constraints, LogSumExp wirelength, electrostatic density and a net-crossing term.
- **Defaults:** rotation off.
- **Claims:** 1–5.9× routability, 1–19.7× shorter routed length and up to 492.3× speed, against SA-PCB and NS-Place.

### OmniLayout / OmniRouting

- **Scale:** 77.24K placement instances; 2–8 layers; 1,681 Eagle designs.
- **Openness:** the authors promise open data, but an audit found 5 public boards, no data licence and CC BY-NC-ND papers [3P].

| Method | NRR | PRR |
|---|---|---|
| Best zero-shot LMM | 12.60% | 15.41% |
| Agentic | 27.98% | 30.34% |
| OpenROAD PcbRouter | 56.20% | 71.37% |

Base model outputs average 69.77–431.29 DRC violations. "Feedback quality matters more than iteration count."

### Other benchmarks and datasets

- **PCB-Bench (ICLR 2026):** knowledge QA only (~3,700 text items, ~500 image-text items, 174 OSHWHub designs).
- **EEBench:** atopile-based, graded by SPICE and BOM cost. Opus 5 scored 61.6% on 13 tasks. It "does not yet tell us whether a model can lay out".
- **Small sets:**
  - RL_PCB: 6 circuits.
  - tscircuit srj18: 16 boards, plus SRJ33. SRJ drops widths, clearances, zones and keepouts.
  - DevFormer DPP; FloorSet (2×1M).
  - devbisme tests; KiCad Agentic MCP 18/18 golden tasks.
  - kicad-happy: 5,800+ repos.
- **TraceMaker vs Freerouting 2.2.4:** ≈0.99/1.00/0.90 vs "about 0.7/0.7/0.2" [VK].
- **Older academic work:** proprietary BGA instances, e.g. 28×28 BGA, ~380 signals [Snip].

**Implications for our system.**
- PCBWorld D3 (routing) and the Cypress protocol (placement) are the de-facto standards.
- Re-run Freerouting 2.5.0 ourselves.
- Act through KiCad's engine.
- Resolve PCBench counts and licences before redistributing.

---

## 10. Proposed benchmark plan

CVB's plan, plus [digest] additions:

1. **Routing.** PCBWorld D3-A/B, then D3-C, under the @5 protocol. Baselines: Freerouting 2.5.0 re-run (published 2.1.0: 0.80/0.78) and KRT (0.74/0.20).
2. **Placement.**
   - Cypress small benchmarks, under the Cypress protocol, plus HPWL, overlap, out-of-bounds and crossings.
   - **Placement-stripped D3:** keep outline, mechanical parts, connectors and locks; re-place the rest; route with a fixed router; compare against the human placement routed the same way.
3. **Intent.** Human-confirmed IR annotations, scored by PRC pass rate per kind and hard violations.
4. **Physics.** Decap PRCs, return-path checks, IR-drop margin, si-wrapper/openEMS on high-speed boards.
5. **Human-relative.** MGS plus WL/via/HPWL ratios, with human scores reported throughout.
6. **Unit suites.** Synthetic boards per IR kind, DPP and FloorSet-style mixes.
7. **Hygiene.** Pinned KiCad, a licence manifest, a private recent held-out set, and no self-scoring: re-open boards and re-run DRC.
8. [digest] **Checklist track.** The 299-item critic stack, run on known-bad boards with fixes ("very very few examples out there as to what is wrong", Naib) and escaped errors such as SOT-23 flips, a backwards USB-C connector and missing VCAP caps.
9. [digest] **Trust track.** Scope violations, determinism, setup minutes, prediction accuracy, and a harness the agent cannot touch.
10. [digest] **Blind expert review.** Acceptance and review time, used to calibrate convention metrics.
11. [digest] **Controlled comparison.** Human vs Freerouting vs LLM-orchestrated on identical netlists, eventually fabricated and measured. PD found no such study.

**Implications for our system.** Build the harness first; it doubles as the agent's verification loop. Keep the corpus licence-clean and every result reproducible from saved files.

---

## 11. Conflicts and open questions

**Conflicts:**
- **Rule resolution** differs: KiCad last-match, Altium priority (Matched Lengths accumulate), JITX specificity, Allegro CSet precedence. The IR must define its own.
- **Templates as ground truth.** TI says "copy the EVM"; Ritchey says "Wrong until Proven Right"; extralongdivisi says datasheets can be "written in the 80s, overkill... or completely wrong".
- **Decoupling** by distance (<15 mm / <3 mm / 10 mm radius) or by loop impedance ("Qualcomm actually gives you these"). rcxdude: with good planes, distance matters less.
- **Aesthetics:** necessary vs optional. Hatched planes: PCB Power warns of microvoids; jnoss recommends them.
- **Numbers**: respin cost ($28.5k/$44k/$46k; 2.8 vs 2.9), PCBench size (164/679/1,157), Cypress (10 vs 20 benchmarks; award), OrthoRoute (0.34/0.53 vs 30%/51%), PDN DNN (5000× vs 10,000×), kicad-happy detectors (40/60+/21), and silk/edge thresholds.

**Open questions:**
- **Missing data:**
  - no validated figure of merit;
  - no controlled human/autorouter/LLM study with EMC or SI measurements;
  - no aesthetics or acceptance dataset;
  - no company style data;
  - no dataset of datasheet reference layouts and no layout-retrieval paper;
  - no evaluation of LLM layout-rule extraction.
- **Untested on KiCad 10:**
  - whether `ParseAndCreateItemsFromString` keeps nets;
  - refill latency;
  - whether the GUI reloads `.kicad_dru`;
  - tier runtimes;
  - net-chain semantics on master.
- **Unread or missing sources:**
  - no thermal or EMI surrogates;
  - Phil's Lab and Hartley talks (YouTube blocked);
  - Feranec's phase timesheets;
  - the original Lifecycle Insights and Aberdeen reports;
  - the full Cypress paper.

---

## 12. Idea inventory

Tags: [EW] expert_workflow_and_checklists · [PD] practitioner_discussions · [CVB] constraints_verification_benchmarks · [VK] verification_kicad_and_tools · [digest] this digest.

### Workflow and process

1. Constraint-first order: mechanics/stackup/rules → PDN → fixed parts → floorplan → critical → decaps → rest → sanity check → fanout → critical routes → planes → bulk → tuning → stitching → DRC → outputs [EW]
2. Backtracking state machine S0–S17 with critic-gated exits [EW]
3. Three gates: constraint model, rough placement before routing, completion [EW]
4. Git commit or PR per state; review tied to a commit; reviewee lists the checks done [EW]
5. Escalation: local moves → re-floorplan → repackage/add layers/enlarge → drop functions → human [EW]
6. Olney's ≥85% test-route gate [EW]
7. Autorouter completion as a layer-count adequacy test [EW]
8. Spend search on placement; fast routability estimator as inner objective [EW]
9. Staged reviews, each with its own checklist [EW]
10. DFM at quote, prototype, production, and whenever material, layers, density or assembly change [EW]
11. Whole-assembly design review before assembly (NASA) [EW]
12. Pre-routing setup: stackup in rules, PDN plan, via sizes per class, rule priority, router options [EW]
13. Per-net highlight pass for scenic or spiralling nets [EW]
14. Separate per-IC datasheet layout review [EW]
15. Effort anchors: 50 h simple, 200 h CPU+memory [EW]
16. 90/10 sayings are folklore [EW]
17. Constraint definition is the time sink, so make it cheap [EW/PD]
18. Checklist grows after every escaped error [EW]
19. Phil's Lab review order as the LLM review script [PD]

### Placement

20. Cross-probe placement, one part at a time, by importance [EW]
21. Private parts per IC first; minimize crossings between groups [EW]
22. Functional blocks in signal-flow order; separate domains [EW]
23. Place everything before routing [EW]
24. Autoplace only as a fit check [EW]
25. Order: fixed → CPU+memory → ICs → power → small parts [EW]
26. BGA trial placement, clear, then fan out from the centre [EW]
27. Routing channels between memories [EW]
28. Tight power-stage cluster [EW]
29. Decap staging nF → µF → bulk [EW]
30. Input cap placed and routed first [EW]
31. Shorten loops before widening [EW]
32. SLVAFJ3 8-step converter order with Kelvin net ties [EW]
33. Follow datasheet layout-order lists (bq25886) [PD]
34. Crystal: 1-inch exclusion zone, guard ring, routing checks [EW]
35. ESD and filters at connectors; series R at the source; terminators at the load [EW]
36. Anti-alias filter at the ADC [EW]
37. Align bottom-side lands with top-side lands [EW]
38. Rework clearance 80 mil; inspection spacing = tallest neighbour's height [EW]
39. Uniform orientation; pin-1 alignment; memory matrices [EW]
40. Placement grids [EW]
41. MLCCs away from flex points, aligned against bending [EW/PD]
42. Space and orient inductors against coupling [EW]
43. Thermal placement and spacing between tall and small parts [EW]
44. SMPS away from analog [EW]
45. Group by supply domain [EW]
46. Don't over-constrain board size [EW]
47. Rough place → swap-autoplace with unmovable parts → autoroute → star-ground fix → pours [PD]
48. Group parts by ratsnest length and crossings [PD]
49. Cluster by fewest unique nets [PD]
50. Weighted total-ratsnest metric [PD]
51. Paper sketch of "nuggets"; Pack and Move per block [PD]
52. Refdes ranges per block [PD]
53. Fixed positions agreed with ME via STEP [PD]
54. Sequential packing seed, then an LLM loop that hardens constraints [PD]
55. CSS-grid-style placement constraints [PD]
56. Area-minimizing packing yields unroutable boards; force-directed is unpredictable [PD]
57. Hierarchical decomposition to avoid UNFEASIBLE [PD]
58. Placement as bin-packing [PD]
59. Refine from a seed; constraint capture is the bottleneck [VK]
60. User confirms a floorplan of regions and anchors before optimization [VK]
61. Lock connectors before optimizing [PD]

### Routing

62. Critical nets by hand first, then lock [EW]
63. TI ladder; only <50 kHz nets to the autorouter [EW]
64. Order: power → high-speed → MCU [PD]
65. Bartels flow [PD]
66. Escape-and-reserve buses [EW]
67. Same topology per group; stitching at reference changes [EW]
68. Own via per power pin and per decap [EW]
69. Interactive to >90%, then autoroute [PD]
70. Autoroute regular buses in cleared areas [PD]
71. Router as placement probe, then rip up [PD]
72. Via counts and failure clusters as placement diagnostics [PD]
73. Tournament of routers; lock the winners [PD]
74. Pin key traces by API, Freerouting for the rest [PD]
75. Router must rip up its own routes [PD]
76. Give routers quantitative keepouts, vias and layer penalties [PD]
77. EMI-aware autorouter vision [PD]
78. Topological, any-angle and 8-direction routing are underexplored [PD]
79. Avoid any-angle routes and micro-wiggles [PD]
80. Width only where current flows; power polygons [PD]
81. Margin from rule minima [PD]
82. Same-plane layer changes; adjacent transfer via; never cross split pairs [PD]
83. No noisy traces at board edges [EW]
84. Orthogonal adjacent layers [EW]
85. Penalize neat long parallel runs [EW]

### Size, layers and stackup

86. Size = Σ courtyard / utilization, plus a fit test [EW]
87. Layer generate-and-test: +2 at >70% channel use or <85–100% completion [EW]
88. Fab stackup template plus width-sanity check [EW]
89. Fab approves HDI/flex stackup before rules [EW]
90. Evaluate fab parameters jointly [EW]
91. Fab capability tiers; avoid limits; notes in process order [EW]
92. Hi-rel Class 3 plus coupons [EW]
93. Hartley's stackups to use and avoid; one dielectric from the plane [PD]
94. F = 0.5/Tr bandwidth rule [PD]
95. Prefer paired power pins and lowest adequate Vcc [PD]
96. Two-layer rules: power over ground, length:width ≤3:1, pour under HS traces [EW]
97. Panel efficiency and thickness as explicit decisions [EW]

### Reuse

98. Copy the EVM layout (least risk) [EW]
99. EVM design-block library keyed by MPN and topology [EW]
100. Save learned blocks after they pass critics [EW]
101. Per-sheet rule areas as floorplan cells [EW]
102. Isomorphism channel detection plus Repeat Layout; prefer sheet-based channels [EW/VK]
103. Version-gate features (≥9, ≥10) [EW]
104. Compare against a working reference board [EW]
105. App notes are wrong until proven right; run critics on them [PD]
106. Don't copy popular open-source layouts [PD]
107. Retrieval index (footprint/MPN, passives, pin functions) → relative-pose seeds [CVB]
108. Turn datasheet guidance into constraints, not copied geometry [CVB]
109. Quilter-style pattern detection as the intent extractor [CVB]
110. Port forwarding so blocks carry constraints [CVB]
111. atopile sub-build + pull group [CVB]
112. Rooms that move their components [CVB]
113. Multichannel as a placement multiplier [VK]

### Review, checklists and critics

114. 299-item checklist with severity and automation tags [EW]
115. Semantic role/current/voltage/frequency layer [EW]
116. Three-tier critics A/S/J [EW]
117. `.kicad_dru` from roles and profile, mapped to IDs [EW]
118. Audit overrides first [EW]
119. Group violations by root cause [EW]
120. Finding record with measured, threshold, source, image, fix [EW]
121. Tier-S priority list of 11 [EW]
122. Tier-J packet; uncertain goes to a human [EW]
123. Hand SI/flex/EMI items to simulators [EW]
124. Criticals gate; Majors penalize; minors are soft [EW]
125. Threshold provenance hierarchy [EW]
126. Mandatory fab profiles [EW]
127. Documentation → geometry → physics priority [EW]
128. Output-package checks [EW]
129. Class-coverage report [EW]
130. Margin-to-limit report [EW]
131. Verify every finding against a primary source [EW]
132. "Never trust a clean ERC": per-IC walk [EW]
133. "Run the real checkers first" [EW]
134. Severity-ranked report with one fix each [EW]
135. Side-by-side datasheet images [PD]
136. Adversarial review prompt [PD]
137. Deep second pinout pass [PD]
138. Multiple DRC tools with fab DFM as truth; watch false positives [PD]
139. Same-LLM audit of its own edits [PD]
140. Unit-test board generators [PD]
141. Red-flag visual list [PD]
142. Connector and footprint orientation checks [PD]
143. "Trace width matches the chip's reference design" check [PD]
144. "Conventional op-amp schematic layout" check [PD]
145. Readable schematic before review [PD]
146. Chronological change-log page with visuals [PD]
147. Test-point distance L = 0.29·H + 0.7 mm [EW]
148. Copper balance within ~20% [EW]
149. One ground return per 9 cable signals (1 per 4 if >1 ft) [EW]
150. λ/10 or λ/50 termination threshold [EW]
151. Via fence ≤λ/8 [EW]
152. Simulate nets longer than 1/6 of rise time [EW]
153. 1.5W from voids, 90 mil from plane edges, ≤1 µF stitching caps [EW]
154. Stub <15 mil, 30 mil antipads, equal vias, ≤0603 SMDs, breakout within 0.25" [EW]
155. Tombstone copper ratio [EW]
156. Assembler spacing; part-to-hole ≥8 mil [EW]
157. Fiducial rules [EW]
158. Split grounds only below ~100 kHz, joined at a single point [EW]
159. Respin statistics as motivation [EW]
160. Fab-hold ranking drives critic order [EW]
161. Extract rules from datasheet layout sections [EW]

### Metrics

162. Orientation entropy [EW]
163. Pin-1 agreement [EW]
164. Grid-snap ratio [EW]
165. Collinearity [EW]
166. HPWL + crossings [EW]
167. Manhattan-ratio outliers [EW]
168. Hot-loop and switch-node area [EW]
169. Decap distance + Spearman order [EW]
170. Text-direction count [EW]
171. Geographic designators [EW]
172. Pad-exit violations [EW]
173. Parallel-run length [EW]
174. Channel congruence [EW]
175. Flow monotonicity [EW]
176. Wiggle and any-angle fraction [PD]
177. Neatness paired with a coupling penalty [EW]
178. Taste = physics + convention + style [PD]
179. Field-containment check per critical net [PD]
180. PCBWorld CP, Φ, @5 [CVB]
181. OmniRouting PR/NRR/PRR/shorts/opens [CVB]
182. MGS as a diagnostic only [CVB]
183. Normalize against human scores [CVB]
184. Cypress routability protocol [CVB]
185. Quilter PRCs as physics metrics [CVB]
186. Intent conformance [CVB]
187. Freerouting V2 scores [VK]
188. Union metric set [CVB]
189. Process metrics: scope, determinism, setup time, prediction accuracy [digest]

### Trust and UX

190. Deterministic tools judge correctness [PD]
191. Bounded, commanded chunks [PD]
192. Predictable automation with no settings; the human plots the course [PD]
193. Never touch locked work; minimum change [PD]
194. Before/after render with physical rationale [PD]
195. 100% routed is not done [PD]
196. Immutable harness [PD]
197. Predict before checking [PD]
198. Determinism across revisions [PD]
199. Cheaper than hand layout, setup included [PD]
200. Provenance and IP; no training without consent [PD]
201. Declarative constraints, lockfiles, tests [PD]
202. Progressive "CSS" constraints [PD]
203. Visual constraint entry [PD]
204. Spreadsheet constraint entry [PD]
205. Per-zone and per-net-type rule sets with priorities [PD]
206. Escape hatch to the GUI [PD]
207. Co-creation and conversational UI; cruise control; sketch routing [PD]
208. Guided bus commands with grounding, shunt, HV and guard-ring awareness [PD]
209. "DRC, fix, show me" [PD]
210. Incremental-ECO mode [PD]
211. Undo, commits, snapshots [PD]
212. Ask about never-delegate items [PD]
213. Perfect the delegable work first [PD]
214. Reviewer before producer [PD]
215. "Good not perfect"; one step up from an autorouter for simple boards [PD]
216. Boilerplate prototypes have value [PD]
217. Let humans keep the routing craft [PD]
218. Evidence before claims [PD]
219. Reliable round-trips; fixed-part marking [PD]
220. AI silkscreen placement [PD]
221. N-copy replication [PD]
222. Pin planning, requirements review, part suitability [PD]
223. Parametric APIs over recall [PD]
224. Standard JSON pin maps [PD]
225. Accuracy bar (60% of tasks at 50% accuracy is useless) [PD]

### LLM roles and failure modes

226. LLM sits upstream of and around the solver [PD]
227. LLM fixes failure clusters geometrically (stagger U6–U10) [PD]
228. LLM writes DRC rules for routers [PD]
229. LLM ranks nets manual vs auto [PD]
230. LLM as datasheet extractor [PD]
231. LLM review as cheap insurance [PD]
232. LLM-written FEA/PDN analysis validated against measurement [PD]
233. Parsers as the LLM's eyes; processed data beats raw [PD]
234. Parsers work, the LLM narrates [PD]
235. No LLM-written placers or routers [PD]
236. Guard against LLM failure modes: connectors, loops, escapes, wiggles, unrequested edits, DRC slop, open nets, odd rules [PD]
237. LLM is inconsistent at staying within the datasheet [PD]
238. LLM overconfidence [PD]
239. Datasheet footnote traps [PD]
240. Datasheets aren't ground truth [PD]
241. Decoupling as an impedance target [PD]
242. Layout is circuit design [PD]
243. Pin and part swaps with back-annotation [PD]
244. Schematic order signals layout order [PD]
245. Build a fast verification loop [PD]
246. Collect bad examples with fixes [PD]
247. Image routers would need >10M boards [PD]
248. Parallel seeded, ranked candidates [PD]
249. Low-token router orchestration [PD]
250. Sub-second tool operations [PD]
251. Code-first EDA to save context [PD]
252. Deterministic scripts; AI for judgment; `board.yaml` hard errors [PD]
253. `git describe` revision on silkscreen [PD]
254. Learning from layout plus simulation [PD]
255. A harness with built-in solvers [PD]

### Constraint and intent IR

256. Three constraint-model families [CVB]
257. IR superset compiled down [CVB]
258. Explicit resolution; specificity → general-to-specific [CVB]
259. Tags with inheritance [CVB]
260. Topologies with pin models [CVB]
261. Match groups resolved to pin pairs [CVB]
262. Allegro electrical-mode vocabulary [CVB]
263. `proximity` primitive [CVB]
264. `via_to_plane` primitive [CVB]
265. `loop_area` and `layer_switch_count` [CVB]
266. `region`, `cluster_tight`, `edge_placement`, `symmetry` [CVB]
267. `overheated_length` [CVB]
268. High-level intents expand into primitives [CVB]
269. Hard/soft split with a monotone gate [CVB]
270. Provenance, confidence, confirmation [CVB]
271. DFX-like findings and waivers [CVB]
272. IPC-2581 impedance/loss mapping [CVB]
273. Propose → confirm → PRC-grade [CVB]
274. Strict schema [CVB]
275. Practitioner `intent.yaml` [PD]
276. tscircuit `calc()` and `drccheck` as models [CVB]
277. atopile tolerance assertions [CVB]
278. FloorSet multi-instantiation and boundary constraints [CVB]
279. ALIGN UserConstraint expansion [CVB]
280. GNN symmetry extraction; LLANA [CVB]
281. PCBSchemaGen knowledge graph plus verifier [CVB]
282. Extraction completeness (70% → 95%) as an evaluation target [PD]

### KiCad implementation

283. Strict `.kicad_dru` emitter rules [VK]
284. Canonical units [VK]
285. `IR:<id>` rule names plus description regex [VK]
286. Lint rules via `kicad-cli` [VK]
287. No deprecated functions [VK]
288. Don't rely on `ignore` for routing [VK]
289. Time-domain-first high-speed classes [VK]
290. Four-channel KiCad 10 backend [VK]
291. Poll after async refill [VK]
292. Lock before SES import; strip SES placement [VK]
293. Diff KiCad and Freerouting DRC JSON [VK]
294. Single-call Freerouting tool returning scores [VK]
295. Congestion hotspots to the LLM [VK]
296. Library placement from S-expression text [VK]
297. `CustomRule` protobuf target [VK]
298. Adopt `return_path` when it ships [VK]
299. SWIG isolated in a helper process [VK]
300. Diff-pair name false-positive check [VK]
301. Map KiCad-enforceable vs custom-only intents [VK]
302. Component classes as role carriers [EW]
303. Copy the commercial input contract [VK]
304. Target the open high-speed space [VK]

### Verification tools and tiers

305. T0–T3 tiers [CVB]
306. `kicad-cli` DRC JSON, exit code 5 [CVB/VK]
307. Transcalc Z0 and IPC-2221 width in the loop [CVB]
308. `return_path` raster [CVB]
309. emcvisual field estimate [CVB]
310. padne, KiPI, Ki-PIDA [CVB]
311. PCB_SI_Toolkit checks [CVB]
312. si-wrapper + gerber2ems, CI-able [CVB]
313. Palace, FastHenry, FastCap, scikit-rf [CVB]
314. FEM thermal flows [CVB]
315. Analytic proxies in the loop; FEM at sign-off [CVB]
316. Calibrate proxies against T3 [CVB]
317. Train surrogates on synthetic labelled boards [CVB]
318. Surrogate precedents [CVB]
319. Summaries, not geometry, to the LLM [VK]

### Benchmarks and data

320. PCBWorld D3 leaderboard [CVB]
321. Re-run Freerouting 2.5.0 [VK]
322. Cypress placement leaderboard [CVB]
323. Placement-stripped D3 [CVB]
324. PCBWorld recipe for our corpus [CVB]
325. Intent track [CVB]
326. Physics track [CVB]
327. Human-relative diagnostics [CVB]
328. Synthetic unit suites [CVB]
329. Benchmark hygiene [CVB]
330. Act through the engine [CVB]
331. Feedback quality beats iteration count [CVB]
332. LLM-only routing isn't competitive [VK]
333. Golden-task suites [PD]
334. Deterministic EEBench-style grading [PD]
335. Controlled measured comparison [PD]
336. Corpus-scale regression harness [PD/VK]
337. fastroute parity as a determinism reference [VK]
338. Checklist track with known-bad boards [digest]
339. Blind expert review to calibrate convention metrics [digest]
