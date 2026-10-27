# LLM circuit design through a typed IR with deterministic checks (kaesynth)

**Status:** partial. The tool worked: four non-trivial LLM-written designs build with 0 unwaived check errors, a clean KiCad ERC and an exact netlist round trip. The designs did not: an independent review found 0–2 blockers and 4–7 major issues in each, mostly of a kind the automatic checks cannot see.
**First published:** 2026-10-23, commit [9f953d0](https://github.com/magnetic-trowel/kicad-auto-everything/commit/9f953d01d7d4fa6cbbfa7851c791c59a5e6d0d79) on branch `claude/focused-hamilton-a7ocm0`.

An LLM turns a plain-language product brief into Python against a typed circuit IR (requirements, hazards, voltage domains, rated parts with datasheet provenance, nets with voltage/current envelopes, placement relations). `kaesynth build` checks the IR deterministically, emits a KiCad 10 schematic, custom DRC rules and a placement-intent file, and proves through KiCad that the schematic's netlist equals the IR. A separate LLM agent then reviews each design against datasheets.

## Idea and how it works

**Pipeline.** Brief → LLM engineering pass (`DESIGN.md`: requirements, hazards, trade study, calculations, part choice) → encoded in `parts.py` + `design.py` → `kaesynth build` until clean → independent LLM review (`REVIEW.md`) → designer response and fixes → (relay only) re-review.

**Typed IR** (`synth/src/kaesynth/ir.py`):
- *Records:* `require` (value, source standard, verification method), `assume`, `question(blocking=…)`, `hazard(mitigation, parts, single_fault_safe)`, `calc(name, value, unit, expr, limit)` (fails the build if the limit is violated).
- *Voltage domains.* `d.domain(name, ref=net)`. A domain whose `ref` is its own 0 V net is a **root** (galvanically separate from other roots); a domain whose `ref` is a net of another domain **floats** on it (battery k of a stack: `ref="B2_POS"`; a bootstrap supply: `ref="SW1"`). Every net has `v=(min, max)` relative to its domain's ref (AC as peak). The worst-case voltage between any two nets is the sum of ranges along the domain chain, so stacked batteries get exact bounds instead of interval blow-up.
- *Parts:* MPN, KiCad symbol (library or generated from a datasheet pin table), footprint, explicit pin maps for transistors and unnamed library pins, `source={"pins", "pinmap", "ratings"}` provenance, ratings (`v_max`, directional `VLimit` with recommended maximum `v_rec`, `i_max`, `p_max`, polarity, `Isolation(grade, v_iso, v_work, creepage_mm, material_group)`), lifecycle and second source.
- *Nets:* kind (signal, power, ground, hv, mains, switching, …), current, `external=True` with `threats` (esd, surge, overcurrent, reverse_polarity, load_dump, overvoltage) that require a matching protector.
- *Barriers* between domains with grade, working voltage, creepage/clearance and the standard's table as `source`; the framework never invents spacing numbers.
- *Placement relations* (`d.place.*`), ordinal and never coordinates: group, region, near(tight/close/loose), far, edge, hot_loop(pins), pins_toward, separate(domains), keepout, thermal, array, align, symmetric, side. The build adds inferred ones (block groups, decoupling cap next to its IC pin, external connectors on an edge).
- *Waivers:* `d.waive(check, regex, reason, by)`; unused waivers are reported so stale ones get removed.

**Checks** (`checks.py`, pin-level messages): unconnected pins and single-pin nets; push-pull output conflicts; voltage, polarity, current, power and MLCC DC-bias ratings against worst-case envelopes; parts across two roots must be rated isolators backed by a barrier (grade, withstand, working voltage, package creepage); external-net threats need protectors; BOM lifecycle and provenance; calculation limits; hazard mitigations; open blocking questions mark the build "not ready for fabrication".

**Emit and KiCad gates.** A label-only hierarchical KiCad 10 schematic (one sheet per block; exact by construction, not pretty), project symbols, net classes, `.kicad_dru` with IPC-2221B functional spacing per domain pair from the exact worst voltage plus barrier creepage/clearance rules, `intent.yaml` (`pcb-intent/0.2`), BOM, `report.md`. Then `kicad-cli sch erc`; a **netlist round trip** (the netlist KiCad reads from the schematic must equal the IR pin for pin); a static lint of the `.kicad_dru` (kicad-cli 10.0.7 ignores bad rules silently); and a DRC smoke run of the rules on a stub board (kicad-cli 10.0.7 segfaults on creepage rules without an Edge.Cuts outline, so the stub has one). Multi-board systems get one project and parity check per board, and a net may cross boards only through a connector on each.

## What we tried

Four briefs, each designed end to end by an LLM agent and reviewed by a separate one (datasheets downloaded and read; two reviewers wrote small time-domain models of a watchdog and a switched-capacitor cell):

| Design | What it is | Parts (distinct) | Build (from `out/report.md`) |
|---|---|---|---|
| `rpi-mains-relay` | Pi Zero 2 W switching six 120 V receptacles, one enclosure, listed 5 V supply, hardware heartbeat watchdog | 103 (37) | 0 errors, 31 waived; ERC 0/0; parity identical; 4 blocking questions |
| `liion-balancer` | 13–16S home-pack active balancer: per-cell isolated flyback (LT8584) + ADBMS1818 monitor, hardware trips | 448 (69) | 0 errors, 24 waived; ERC 0 errors, 6 warnings; identical; 6 blocking |
| `leadacid-balancer` | 2–4 × 12 V lead-acid switched-capacitor balancer, MCU-free, fail-safe alarm | 503 (62) | 0 errors, 31 waived; ERC 0/0; identical; 4 blocking |
| `prius-solar-mppt` | 2017 Prius Prime roof solar into the HV pack: MPPT, isolated step-up, two boards | 644 (137) | 0 errors, 17 waived; ERC 0 errors, 4 warnings; system and both boards identical; 6 blocking |

## Results

Review counts from each `REVIEW.md` (commits [c460023](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c4600230407ebb51519e53b05d17aea2a64abc76), [6ccb2e3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6ccb2e34b508dab514027443287c09aeeda52398), [98643b6](https://github.com/magnetic-trowel/kicad-auto-everything/commit/98643b691361213944d2a021b101eb15d260f672), [c6e7fbd](https://github.com/magnetic-trowel/kicad-auto-everything/commit/c6e7fbd0f535f2fb3da5cffad02286189d834a0e)); every reviewer's verdict was "not ready".

| Design | Blocker | Major | Minor | Examples of what the review found |
|---|---|---|---|---|
| rpi-mains-relay, review 1 | 0 | 6 | 10 | outputs take 1–1.6 s to disarm with the heartbeat stuck high, not 0.15 s (a capacitor change during fixes caused it); single watchdog faults go undetected; field wires can rest on exposed mains copper; `intent.yaml` lets a placer put parts in unsafe places |
| rpi-mains-relay, re-review of rev. 3 | 0 | 3 | 8 | watchdog window so short that heartbeat jitter drops every outlet; live mains parts in the compartment opened to service the Pi; unsafe cover-mounted receptacle details |
| liion-balancer | 0 | 5 | 8 | an open end tap while balancing is not detected; a clamp diode defeats the LT8584's own open-output detection; monitor pins drive the flyback enables with no series resistance (a > 0.5 A path between taps); board fuses carry faults beyond their interrupting rating; one MCU holds both enables |
| leadacid-balancer | 1 | 4 | 10 | **blocker:** board fuse rated 500 A DC breaking capacity where 1.5 kA is needed; ratio-window tolerance ±5 %, not ±1.5 %; lockout depends on LED forward voltage; "open tap → FAULT" false for some taps |
| prius-solar-mppt | 2 | 7 | 9 | **blockers:** HV-to-chassis insulation not designed (intent puts HV copper on a chassis-bonded pad); safety thresholds rest on an inferred cell window. Majors: CCM-only LM5176 can run power backwards; CAN clocked from a ±1.5–2 % RC oscillator; open pack-temperature sensor fails unsafe; "latched" trip clears on brownout |

Pin maps were the strong part: every reviewer reported that the pinouts they checked against datasheets were correct.

## Verdict

- **What the typed IR + checks catch:** wiring and pin bookkeeping, worst-case voltage/current/power ratings, isolation-domain crossings and barrier spacing, missing protectors, unsourced part facts, and schematic/netlist drift (proved by KiCad's own reading of the files). All four designs reached that bar.
- **What only the review caught:** time-domain behaviour (watchdog discharge paths, oscillation of dawn/dusk relays), controller operating modes (CCM-only reverse power flow), clock tolerance against a protocol's budget, fail-unsafe sensor opens, single-fault claims, wrong breaking capacity of a correctly rated fuse, mechanical/installation safety, and whether the design fits the brief. None of these is a property of the netlist and ratings alone. "ERC-clean and checks pass" therefore says little about readiness, in line with the survey evidence that ERC accepts many designs full verifiers reject ([part-selection-and-verification](../../topics/synthesis/part-selection-and-verification.md)).
- **Next steps the results point to:** SPICE testbenches for every calculation that has a time domain (stuck-high and stuck-low scenarios), typed interfaces (I²C pull-ups and addresses, CAN timing), distributor lookup for MPNs and lifecycle, and the independent review as a required gate.
- **Caveats:** n = 4, one designer and one reviewer per design, both LLMs; no design was simulated in SPICE, built, or checked by a licensed engineer; none was placed or routed (only placement intent was produced). Parts counts in the earlier design index (`designs/README.md`) are rounder than the build reports; the table above uses the reports.

## Code

`tools/research/llm-design/synth/` (package `kaesynth`, ~4,100 lines; README with the full IR guide and check table), designs in `tools/research/llm-design/designs/<slug>/` (`DESIGN.md`, `CONNECTIONS.md`, `parts.py`, `design.py`, `REVIEW.md`, own footprints, and the committed `out/report.md` and `out/erc.json`). Rebuild:

```bash
cd tools/research/llm-design/synth && uv venv .venv && . .venv/bin/activate && uv pip install -e '.[test]'
kaesynth build ../designs/rpi-mains-relay/design.py -v   # needs kicad-cli and the KiCad symbol/footprint libraries
pytest tests
```

Re-checked when importing to main: tests 25 passed, 4 skipped; `rpi-mains-relay` and `leadacid-balancer` rebuild with the same check, ERC and parity results.

## Related

- [LLM-design area map](README.md); [research index](../README.md).
- Surveys of others' work: [schematic-generation-landscape](../../topics/synthesis/schematic-generation-landscape.md), [part-selection-and-verification](../../topics/synthesis/part-selection-and-verification.md).
- [Constraint IR](../../topics/architecture/constraint-ir.md); [relations, not coordinates](../../topics/llm/interfaces-relations-vs-coordinates.md) (why intent is ordinal).
