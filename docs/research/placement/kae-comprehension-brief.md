# Circuit comprehension: the kae physics brief

**Status:** worked; capacitor ownership on shared rails partial.
**First published:** 2026-10-22, commit [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc) on branch `claude/vigilant-mayer-i91rrr` (evidence model in [39f8d17](https://github.com/magnetic-trowel/kicad-auto-everything/commit/39f8d1707be0300dfce0d6b81d33dd09b494c4f0); unannotated pins [dfe6260](https://github.com/magnetic-trowel/kicad-auto-everything/commit/dfe626056d1087259702fe786b4a098f85c0cbee) on branch `physics-unannotated-pins`).

`kae.circuit.brief` reads a board's netlist and part data, never positions, and states what the circuit is physically: net roles and voltages, switching cells, power paths, decap ownership, crystals, protection chains, heat sources, each with a confidence. This "physics brief" (`kae.brief/1`) is what the placer's physics terms, the critical router and the joint loop price. It runs in 0.1 s per board and finds 81% of human hot loops tighter than the 5th percentile of random placement.

## Idea and how it works

**Inputs, position-free.** Refdes, library id, value and fields, pin function and pin type, netlist topology, net class, schematic sheet. A test randomizes every footprint and pad position and checks the brief is identical.

**Evidence model.** Every claim is a sum of natural-log-odds weights over checkable facts (STRONG 3.0, MODERATE 1.5, WEAK 0.7, negative weights for counter-evidence); confidence = logistic(prior + sum w), clipped to [0.02, 0.98]; the facts are kept as text, so each claim explains itself. Part kinds are a softmax over per-kind scores with an explicit *unknown* class (score 1.0).

**Net roles.** ground, rail, switch_node, clock, high_speed, analog, rf, reset, boot, signal, no_connect. Each rail gets a voltage (from the name, regulator part numbers, USB and battery defaults, inheritance through series parts with -0.4 V per diode, and last the lowest capacitor rating / 1.6) and a source (first match: battery, module 3V3 pin, jack, IC internal output, rectifier, regulator or load-switch output, inductor, series path, connector).

**Pin semantics, names first.** Library pin types are often wrong (VIN typed input, EN typed power_in). `roles.pin_sem` reads each pin as ground, supply, supply output, analog, signal or nothing by an ordered rule list in which names outvote types: ground names (except V-/VSS on a negative rail); differential-input names on non-power ICs -> analog; `power_out` on a regulator, PMIC or charger unless named VIN/IN; supply names; internal regulator outputs (VCAP, REG18); logic names; only then the pin type; then weak names. KiCad markup (`V_{DD}`) is stripped first.

**Unannotated pins** ([dfe6260](https://github.com/magnetic-trowel/kicad-auto-everything/commit/dfe626056d1087259702fe786b4a098f85c0cbee)). About 57% of the open-hardware corpus was never updated from a schematic (KiCad 5 or Eagle imports): pads carry no pin function or type, so no IC pin read as supply and no decap module was found. Now a pin with neither function nor type on an IC, module or oscillator takes its **net name's** meaning: ground on a ground-named net (chassis excluded), supply on a rail-named net unless the name carries a control word or suffix. It uses net names only, not rail detection, because rail detection itself asks pin semantics (a cycle).

**Structures.**
- Commutation cells (buck, boost, bridge): the loop in current order, closed on the commutation capacitor, with series shunt, bootstrap resistor, charge-pump caps and snubbers; buck vs boost by a vote over pin side, high-side FET, catch diode and rectifier direction.
- Non-switching power paths (load switch, mux, ideal diode, reverse-polarity FET, FET banks): loop C_in -> pass element -> C_out, current belief interval [I/3, I], R_on and P = (I/n)^2 R_on.
- Decaps: a joint per-rail allocation of capacitors with quotas (cell 2, load 1 per power pin, regulator pin 1, split supply, exclusive bulk owners). Scores add sheet affinity (+2 same sheet, -1 other) and same-hundred-block refdes (+1.5); greedy assignment, then a softmax gives `caps_p`. The pairing is `pin` only where the netlist decides; otherwise `nearest_pin` or `nearest_load` (decided at placement time by the physics terms).
- Rail groups (>= 6 identical loads, or >= 4 with fewer caps than loads -> pair each cap with its nearest load), crystals, feedback and measurement dividers, Kelvin shunts, protection chains (connector -> TVS -> series part -> first IC pin), antennas with matching network, heat sources, thermal victims, diff pairs.
- `placement_order` priorities: hot loops 100 + 10 log10(1 + VI), antennas 85, crystals 75-77, and so on.
- Budgets are E5 "Beliefs" with a stated basis (priors, not measurements); see [kae-physics-terms](kae-physics-terms.md).

## What we tried

- `tools/research/physics/cm_comprehension_eval.py` on the 112 suite boards (9,227 parts), scoring the brief against the human layouts (does the owned cap sit next to its IC, are cells tight).
- Manual audit: 10 development boards and 3 held-out boards ([comprehension_audit](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/comprehension_audit.md)).
- `tools/research/physics/cm_pin_type_robustness.py`: delete or flip every pin type and measure what survives.
- Unannotated pins: 40 random annotated and 40 unannotated corpus boards, brief before and after.
- Variants that did not help and were dropped: a rank-order term, a second-cap penalty, quotas scaled under shortage, ICs-before-LEDs ties, a first-cap round for converters.

## Results

| measure | result | source |
|---|---|---|
| capacitor ownership agreeing with the human layout (1,373 caps on 74 of the 112 suite boards) | 74.7% (per board 70.5%) vs 38.0% for the simplest baseline; 76.0% with rail groups | [comprehension](../../topics/physics/comprehension.md) |
| pin pairings > 10 mm from the human pose | 33.2% -> 11.6% | same |
| 64 hot loops vs random placement | 81.3% below the 5th percentile (40.6% below the 1st) | same |
| power-path loops below the 5th percentile | 52% | same |
| crystal to IC, human layouts | median 4.7 mm | same |
| TVS nearer the connector than the protected IC in human layouts | 59.5% (weak label) | same |
| manual audit | dev 10 boards: cells 10/10; held-out 3 boards: cells 2/4 (before fixes); sensitive-net recall 13/33 | same |
| all pin types deleted | 99.45% of net roles kept, rail-set Jaccard 0.93, decap-group Jaccard 0.93 (before name-first: 0.993 / 0.92 / 0.90) | same |
| pin types flipped against names | 0.998-1.0 (was 0.95 on rails); partly circular test | same |
| unannotated pins, 40 unannotated boards | boards with physics modules 12 -> 27, decaps 26 -> 133; 40 annotated boards unchanged | commit [dfe6260](https://github.com/magnetic-trowel/kicad-auto-everything/commit/dfe626056d1087259702fe786b4a098f85c0cbee) |
| run time | median 0.1 s per board | same doc |

Small n: the held-out audit rests on 3 boards (6 for the pin-type test), the unannotated-pins check on 40+40 boards with no placement or routing result on top.

## Verdict

Worked: the brief is cheap, position-free and good enough to drive the placer's physics. The weak part is ownership among unlike loads on one rail, which is a guess (63% without sheet names; schematic order carries about 12 points). Unnamed rails get no voltage. Sensitive-net recall is low (13/33). The untested next step is to simulate the schematic instead of reading it ([schematic-to-physics](../../topics/physics/schematic-to-physics.md)).

## Code

- `kae/src/kae/circuit/{brief,evidence,netlist,roles,structures,values}.py` (about 5,500 lines).
- Run: `PYTHONPATH=kae/src python -m kae.circuit.brief BOARD.kicad_pcb [-o brief.json] [--no-sheets]`.
- Evaluation: `tools/research/physics/cm_comprehension_eval.py`, `cm_pin_type_robustness.py`. Tests: `kae/tests/test_circuit_*.py`.
- First appearances: evidence, netlist, values [39f8d17](https://github.com/magnetic-trowel/kicad-auto-everything/commit/39f8d1707be0300dfce0d6b81d33dd09b494c4f0); roles [83afe1b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/83afe1bb6bf8e270158b12c45059aad014f0f759); structures and brief [64a6858](https://github.com/magnetic-trowel/kicad-auto-everything/commit/64a6858cca92b72ead01cdf56e3b5667a71cb2bc); rail groups and pin robustness [6b5447e](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6b5447ea3b6b23930743f8d2caba1358d3cd7c1d); `nearest_pin` pairing [f20de50](https://github.com/magnetic-trowel/kicad-auto-everything/commit/f20de50c1e3c454907641f2c925471a21f6322b5); unannotated pins [dfe6260](https://github.com/magnetic-trowel/kicad-auto-everything/commit/dfe626056d1087259702fe786b4a098f85c0cbee).
- Used by both merit kae methods ("kae staged (restarts)", "kae joint loop (restarts)").

## Related

[kae-physics-terms](kae-physics-terms.md), [kae-placer](kae-placer.md), [critical copper routing](../routing/kae-critical-copper.md), topic doc [comprehension](../../topics/physics/comprehension.md).
