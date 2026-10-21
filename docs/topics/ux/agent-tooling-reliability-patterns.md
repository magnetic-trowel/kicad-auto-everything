# Tool and agent-loop designs that made LLM PCB work reliable

**TL;DR**
- The highest-value features are **trustworthy state and verdicts**, not more operations:
  - judge the live board;
  - read back after every write;
  - name muted checks;
  - refuse when unverifiable;
  - make each agent step one undoable commit.

  [I]
- **Explicit AI/deterministic boundary:** "AI may interpret constraints and propose net ordering, corridors, cost weights, and repairs. Deterministic code owns geometry, connectivity, DRC, provenance, and file mutation" (CopperMCP) [P].
- **Propose → gate → accept with monotone acceptance:** keep a change only if violations and unconnected counts don't worsen. Per-net acceptance took 256 → 226 unrouted in 10 unattended rounds where whole-board acceptance would have failed [P].
- **A library of deterministic, measurable moves,** each with a diagnostic that says when it applies, closed the last routing dead ends: "Learning isn't the bottleneck… Formalise the moves… as deterministic tools" [P].
- **Order matters:** placement gate → critical routes → lock → autoroute the rest → refill plus locked-copper check → full gate [P, anecdote].

## Key facts

### Reliability ingredients seen in the field

| Ingredient | Evidence | Source |
|---|---|---|
| Code or API, not GUI | NextPCB 3 segments/h GUI vs about 12 min orchestrated; EEBench and Diode views | see [../llm/read-representations.md](../llm/read-representations.md) |
| Deterministic engines | KiCadRoutingTools routed what Freerouting left in 1.25 s; DSN → Freerouting → SES flows | [A6M-Zero](https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/) [P] |
| **Verdict owned by KiCad or the fab** | "I did not want the AI itself deciding that a PCB was correct. KiCad does the verification"; errors if checks can't run (kicad-agentic-mcp). "Trusted because the tools stopped objecting"; "zero discretion in verification" (StationX). Fab DFM as truth (tinycomputers) | [forum](https://forum.kicad.info/t/kicad-agentic-mcp-an-ai-assistant-that-edits-your-board-through-kicads-own-api-and-lets-kicad-decide-whether-the-result-is-good/71403) [P] |
| **Read-back after write** | 138/138 pins, 6 missing GNDs; 120 pin-pad independent comparison ("two files can match and still share the same mistake"); the scorer judges the live board and reports its source (Konnect #648) | [JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design) [P] |
| **Surface muted checks** | The Adom audit skill "reads the project's silenced-rule config so a 'clean' pass can't hide muted checks", verifies each suspicion against a primary source, and keeps a "verified-correct section" | [Adom](https://wiki.adom.inc/api/pages/adom/kicad-board-audit/files/README.md) [P] |
| **Staged gates** | tscircuit: placement → `tsci check placement` → PNG → fix → route, with one focused correction at a time ("try to pack it more tightly"); Flux "Placement Check: run Auto-Layout early"; DRC on pre-routes before Freerouting (pcbkit #2 [S]) | [tscircuit](https://docs.tscircuit.com/guides/circuit-generation/generating-circuit-boards-with-ai) [V] |
| **Lock and verify critical copper** | "Lock that geometry before any autorouter runs… then refill the zones and confirm the locked copper survived"; Flux and Quilter treat existing copper as fixed or "solved" | [JLCPCB Astra](https://jlcpcb.com/blog/gpt-6-astra-pcb-design-in-kicad) [V] |
| **Permission tiers and sandboxing** | kicad-mcp-pro: 24 read-only tools by default (of 377), `build` write mode, `release` manufacturing mode; stdio only; one Git folder; token plus Origin check on bridges; Diode's reviewer "does not edit your files" | [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro) [P] |
| **Transactions** | Native IPC commit groups make one agent edit one Ctrl+Z (kicad-mcp-pro #728/#808, Konnect #752 [S]); file before-images for rollback | [S] |
| **Revision-bound candidates** | CopperMCP: typed exact-integer geometry; "every generated result is an immutable candidate bound to an exact board revision" (SHA-256); two write ops, off by default behind an operator flag plus a "single-use token that no model can mint" | [CopperMCP](https://github.com/seunghyukchoe/copper-mcp) [P] |
| **Propose → gate → accept** | CopperLoop: one commit per change; "kicad-cli is the only truth"; keep a change only if counts don't worsen; "the agent must look" (region renders per layer); route specs as JSON in the project; plan-only unless `--apply` | [CopperLoop](https://github.com/PaoloJN/copperloop) [P] |
| **Compile and refuse; server-side state** | kicad-agentic-mcp: "LLM planning → Deterministic compile + refusal (a plan that cannot finish never starts) → Transactional execution (revisions, idempotency, rollback) → Independent validation + evidence"; coordinates grid-snapped by the operation library; "validator findings carry stable ids, so a fix is an id that disappeared"; "objective, constraints, verified facts, failed attempts and evidence live server-side and survive a context compaction or a model swap" | [README](https://github.com/nevenfo/kicad-agentic-mcp) [P] |
| **Refusal and honest tool semantics** [S] | Planners refuse unverifiable outlines (Konnect #684); "applicable" only if every target is inside the outline and the score improves (#638); exact references required; tool names say what they measure (#528) | [S] |
| **Spec first** | copperhead: nothing touches a file until a validated change proposal exists | [S] |
| **Grounding** | The EasyEDA API reference lets the model "look up real method signatures instead of guessing them"; Cherry Blossom pulls "every footprint from real part data"; Diode's Registry of validated layout fragments; StationX skills file | [JLCPCB](https://jlcpcb.com/blog/claude-code-pcb-design) [V] |
| **Plans as editable checklists** | KiCadRoutingTools: the Claude plan becomes GUI parameters plus a checkable step list run sequentially with status marks, saved as JSON and replayed with no Claude call; per-field "Ask Claude" with transcript and cancel | [README](https://github.com/atomic14/KiCadRoutingTools) [P] |
| **Human checkpoints and decision files** | haohao: style preset (Tidy / Compact / Robust plus 17 axes); a yes/no `PCB_DECISIONS.md` where "a blank row means 'not approved'"; 1:1 printout before routing; route one function group at a time with DRC after each. nexatech asks for the GUI-only F8 check at milestones | [haohao](https://github.com/haohao-0725/PCB_Layout_with_AGENT_in_KiCAD) [P] |
| **Proof that checks ran** | "`gate.sh` prints `skipped` for checks it could not run; do not report those as passed"; verdicts carry an input SHA | [AGENTS.md](https://raw.githubusercontent.com/nexatech-ltd/kicad-agent-toolkit/main/AGENTS.md) [P] |
| **Stop rules** | Flux "stops when further search is unlikely to improve"; stop after the 2nd–3rd failed fix (tinycomputers); hard spend caps (StationX) | [Flux](https://www.flux.ai/p/blog/ai-auto-layout-winter-update) [V] |

### nexatech kicad-agent-toolkit methodology [P] ([lessons](https://raw.githubusercontent.com/nexatech-ltd/kicad-agent-toolkit/main/docs/lessons-learned.md); [methodology](https://raw.githubusercontent.com/nexatech-ltd/kicad-agent-toolkit/main/docs/methodology.md))

**Acceptance and helpers:**
- **Per-net monotone acceptance:** "ten unattended rounds went 256 → 226 at zero violations, and none of them would have passed whole."
- **Judge helpers by the acceptance verdict:** hiding vias made Freerouting 6× faster but "every round unusable (149 shorts)".
- **Prune-to-DRC:** snapshot, write copper, run DRC, delete *this run's* flagged objects, so "only copper that DRC accepted stays".

**Routing moves:**
- "For the last breaks the maze router beats Freerouting" (0.1 s and 5.5 s vs zero-progress campaigns).
- **Read "no path" by the cell count:** small means a locked pad, so fix placement; millions means a blocked corridor, so rip the named wall nets.
- "A pin boxed in by neighbours: move the signal to a pin with via room": 4 signals routed after 12 failed rip-up rounds.
- "Via size is a routing-capacity knob."

**Placement moves:**
- "Search placements with the real rules": exact search found 6,254 positions where a simplified search found none.
- "QFN pins are locked by local support parts, not board size."
- "In a buck converter the fast loop is the input loop."

**Ordering and agent rules:**
- Fan out first; stitch ground last ("stitching vias placed during routing become walls"); widen to class and current only after zero breaks.
- AGENTS.md: "KiCad is the judge… Your own model of the board is a hypothesis; DRC is the fact"; "Plan first, then `--apply`"; "Work on a copy, accept monotonically"; "Quote the gate only with its fingerprint"; "When the agent's shell gets blocked, stop and write a resume point"; "Search the project documents before asking."

## Recommendations for our system

### Tool API [I]
1. No coordinate math in the model. Offer intent-level operations (`place_near`, `keep_together`, `align/distribute`, `orient_pin_toward`, `place_in_region`, `fix`, board-coordinate label placement), all through KiCad code in **one shared orientation helper** that preserves 3D models, zones and text.
2. The LLM edits the **constraint set** between deterministic solver runs, "hardening" intent (tscircuit's Seve), rather than moving parts.
3. **Ground truth** comes from kicad-cli or IPC plus the fab profile:
   - judge the live board and name the source;
   - fab rules are a precondition;
   - list disabled categories.
4. **Every mutating call returns an observed diff;** a mismatch with the intent is an error. Netlist parity and pin-by-pin pad↔net comparison are first-class tools.
5. **Typed refusals;** a plan is "applicable" only if it is legal and the scorecard improves.
6. **Transactions:**
   - one native commit per step;
   - immutable, revision-bound candidates with a human-only apply token;
   - Git auto-snapshots;
   - `compare(a, b)`;
   - an idempotency ledger;
   - server-side task state.
7. **Coarse calls** ("place block under constraints", "route nets protecting locked copper", "verify locked copper plus refill").
8. **Perception:** compact JSON with truncation metadata; labelled renders as a secondary channel.
9. **Failure attribution:** e.g. "49 unrouted, 80% ending in region R near U6–U10; capacity X vs demand Y". Plus no-path cell counts, wall nets, escape capacity per fine-pitch package, and via-spot scans.
10. **Move library:** rip named wall nets; move a signal to a pin with via room (alternate-function table); change via size; nudge support parts; re-fanout; `fit_near` exact search; temporary keepouts.
11. **Prune-to-DRC writes,** with each pruned item pointing to a missing rule.
12. **Checks report checked / defect / not checked** plus input counts and a board hash; never quote a stale log.

### Agent loop
1. Interpret → confirm → constrain → place (solver) → placement gate (check, render, readability, escape capacity, 1:1 fit) → route critical → lock → autoroute → refill plus locked check → DRC/parity/semantic/DFM gate → triage.
2. Monotone acceptance with a regression ledger.
3. Retry cap of 2–3 per issue plus iteration and spend caps; escalate with evidence.
4. Recognize every failure category, including unconnected, silkscreen and parity.
5. A separate read-only, evidence-only reviewer, severity-ranked, with a verified-correct list.
6. Reference designs and validated fragments first.
7. Clarify only when necessary, before long runs.
8. Record seeds, versions, constraint sets and prompts; the solver step is deterministic given constraints.
9. A skills/lessons file with sources.

## Conflicts and open questions

- No A/B study (same model, same board) compares high- and low-level APIs.
- CopperLoop and kicad-agent-toolkit internals were seen partly through snippets.
- None of these patterns has been A/B tested.

## Sources
- research notes: [field_reports_and_ux.md § 1A2, § 1C, § 3, § 6A–B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/field_reports_and_ux.md)

See also: [field-failure-modes.md](field-failure-modes.md), [../llm/agent-loop-patterns.md](../llm/agent-loop-patterns.md), [explanations-and-alternatives.md](explanations-and-alternatives.md), [../kicad/mcp-server-lessons.md](../kicad/mcp-server-lessons.md)
