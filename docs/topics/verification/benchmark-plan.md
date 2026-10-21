# Proposed benchmark plan for our placer/router

**TL;DR**
- **Routing**: PCBWorld D3 under its @5 protocol, against Freerouting re-run at 2.5.0 (not only the published 2.1.0 numbers) and KRT.
- **Placement**: Cypress small benchmarks under the Cypress protocol, plus placement-stripped PCBWorld boards routed by a fixed router and compared with the human placement routed the same way.
- **Extra tracks** beyond routing/placement: intent conformance, physics checks, human-relative diagnostics, synthetic unit suites, and a checklist track seeded with known-bad boards.
- **Hygiene**: pinned KiCad version, per-board licence manifest, private recent held-out split, and no method ever scoring itself (re-open saved files, re-run DRC).
- **Build the harness first.** It doubles as the agent's verification loop, which practitioners say LLM tools lack.

## Key facts

Tags: [P] primary; [I] inference. Items 1–7 come from the constraints/benchmarks note. Items 8–11 are additions from the workflow and practitioner research [I].

| # | Track | Content | Scoring |
|---|---|---|---|
| 1 | Routing leaderboard | PCBWorld D3-A/B, later D3-C | @5 CP / Pot. / Rout. / DRV / WL / Via / Time / Parse-fail, against published Freerouting (0.80/0.78) and KRT (0.74/0.20). Also re-run Freerouting 2.5.0, since the published baseline is 2.1.0 (VK) |
| 2 | Placement leaderboard | Cypress small benchmarks; PCBWorld D3 boards with placement stripped (keep outline, mechanical parts, connectors and locks; re-place everything else) | Cypress protocol (Freerouting routability, two layers) plus HPWL, overlap, out-of-bounds, crossings; compare with the human placement routed by the same router |
| 3 | Intent track | Subset of D3 plus own boards, annotated with human-confirmed IR constraints ([../architecture/constraint-ir.md](../architecture/constraint-ir.md)) | PRC pass rate by constraint kind; hard-violation counts |
| 4 | Physics track | Decap PRCs, return-path violations, IR-drop margin (padne/KiPI); si-wrapper/openEMS impedance and delay on a few high-speed boards | Measured vs limit ([evaluation-stack.md](evaluation-stack.md)) |
| 5 | Human-relative diagnostics | Every board with human copper | OmniRouting-style MGS plus WL, via and HPWL ratios. Report human scores on every metric, since human boards are not 100% clean |
| 6 | Unit suites | Synthetic generators per IR kind (PCBWorld D1/D2-style); DPP simulator for decaps; FloorSet-style mixes of region, edge, grouping and pre-placed constraints | Per-kind pass rates |
| 7 | Hygiene | Pinned KiCad version; licence manifest per board; private recent held-out split against pretraining contamination | Methods never score themselves: re-open and re-run DRC on saved files |
| 8 | Checklist track [I] | Run the 299-item critic stack ([review-checklist.md](review-checklist.md)). Seed with known-bad boards plus fixes ("very very few examples out there as to what is wrong... need bad examples and their fixes", Naib) and escaped-error cases: SOT-23 flips, a backwards USB-C connector, missing MCU VCAP caps, open nets at export | Critical/Major pass counts; detection rate on seeded faults |
| 9 | Trust/process track [I] | Scripted tasks with locked regions and narrow scopes | Edits outside scope; determinism (board hash across runs); human setup minutes; agreement of predicted vs actual DRC/routability; harness immutability |
| 10 | Blind expert review [I] | A sample of outputs mixed with human boards | Acceptance rate and review time; used to calibrate the convention metrics ([looks-right-metrics.md](looks-right-metrics.md)) |
| 11 | Controlled comparison [I] | Human vs Freerouting-only vs LLM-orchestrated layout on identical netlists | Eventually fabricated boards with measurements. Practitioners report no such study |

### Construction recipe for our own corpus

Follow the PCBWorld recipe [P]:
1. Convert boards to the current KiCad version.
2. Keep each board's own rules.
3. Drop boards that are not fully connected and DRV-clean after conversion.
4. Keep the human copper as the reference.
5. Split by pad count.

Then add placement-stripped variants and intent annotations [I].

## Recommendations for our system

- **Implement the harness before the agent.** The same scripts score benchmark runs and gate the agent's own state transitions ([../workflow/expert-state-machine.md](../workflow/expert-state-machine.md)) [I].
- **Keep the harness outside the agent's write scope.** A practitioner's agent rewrote its scoreboard; see [../workflow/trust-requirements.md](../workflow/trust-requirements.md) [I].
- **Publish only licence-clean boards**, and record each board's licence in a manifest (licensing area: `docs/topics/licensing/`) [I].

## Conflicts and open questions

- Licences of PCBWorld D3, PCBench and the Cypress benchmarks need per-board verification.
- IR checkers (pad distance, via-to-plane, loop area, layer switches) need implementation and validation against Quilter-style PRC definitions and openEMS before the intent and physics tracks are trustworthy.
- Tier timings for DRC, padne and KiPI on representative boards are unmeasured.

## Sources

- research notes: [constraints_verification_benchmarks.md § Q4, Q6C](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)
- research notes: [practitioner_discussions.md § Q2b, Q5 Gaps](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md)
- corrections: [verification_kicad_and_tools.md § 5 (#9)](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_kicad_and_tools.md)

See also: [benchmarks.md](benchmarks.md), [quality-metrics.md](quality-metrics.md)
