# Functional evaluator: code architecture (`kae.sim`)

Scope: code, extraction, decks, budgets, CLI and runs of `kae.sim`: ngspice runs each testbench test on the ideal circuit (each net one node) and the routed circuit (test nets replaced by extracted copper) at every corner of its parameter intervals. Not here: semantics, check catalogue, verdict definitions -> [functional-evaluation](../physics/functional-evaluation.md); testbench format and its history -> [intent-interchange](intent-interchange.md); kernels and exactness classes -> [physics-engine-design](physics-engine-design.md).
Keys: kae.sim, testbench.tb.cir, autotb, extract.py, signal profile, power profile, lmax, lmin, names.py, ideal deck, routed deck, layout effect, capability, `incomplete`, `unknown`, `error`, `kae_pdiss`, `questions`, kae.sim.budget, `budgets`, board.budgets.json, `Vloop`, cell_body_floor, stand-in, hot loop, pt_mesh_loop, Gear, rshunt, e_sw, p_loss, ardor, argo, chesslab powerboard, astro-cat

Tags: [M] measured here, [I] design choice.

Status: 8 modules, 19 unit tests (analytic track R and L, I × R drop end to end through ngspice, coupling sign, format round trip), corpus runs in §7; no existing module, score or evaluator changed [M]. The simulator never sees a KiCad name; a missing measurement is a failure, never a silent pass.

## 1. Modules

| Module | Role |
|---|---|
| [`testbench.py`](../../../kae/src/kae/sim/testbench.py) | testbench format: parse (errors carry line numbers), render, SPICE numbers |
| [`autotb.py`](../../../kae/src/kae/sim/autotb.py) | default testbench from board + brief, no LLM: rail DC drop and load step, I2C, switching cells (buck, boost, half-bridge, motor-driver phases) and their hot loops, differential-pair delay and skew |
| [`design.py`](../../../kae/src/kae/sim/design.py) | board passives as elements: values from the value field, ESR and ESL by package (E5), ferrites as R + L |
| [`schematic.py`](../../../kae/src/kae/sim/schematic.py) | values and fields from a KiCad 6+ schematic via `kicad-cli sch export netlist` |
| [`extract.py`](../../../kae/src/kae/sim/extract.py) | copper → Network of R, L, C, K between node keys; copper islands per net |
| [`names.py`](../../../kae/src/kae/sim/names.py) | generates every node and element name: safe, case-proof, dot-free, kept both ways; unresolvable names rejected |
| [`ngspice.py`](../../../kae/src/kae/sim/ngspice.py) | batch runs (PATH or the KiCad container); reads `.meas`; keeps warnings and errors |
| [`evaluate.py`](../../../kae/src/kae/sim/evaluate.py) | decks per test, mode, corner; parallel runs; verdicts, capability, questions |
| [`cli.py`](../../../kae/src/kae/sim/cli.py) | `testbench`, `evaluate`, `questions`, `budgets` |

## 2. Data flow

```
board.kicad_pcb ─┬─ load (+ pintypes.json, + schematic values when the footprints carry none)
                 ├─ brief (kae.circuit.brief: roles, rails and sources, structures, diff pairs)
                 ├─ design (passives)                         ┌─ ideal deck  ─┐
testbench.tb.cir ┴─ tests ─▶ per test × corner ───────────────┤               ├─▶ ngspice ─▶ .meas
                             (RoutedBoard + kicad-cli fills) ─┴─ routed deck ─┘
                                                  └─ extract(nets of the test, profile)
  ─▶ verdicts (ideal, routed), layout effect, capability, incomplete/unknown/error ─▶ eval.json ─▶ questions
```

## 3. Extraction

Built on the repo's closed forms: Hammerstad–Jensen L′ and C′, Grover/Neumann mutuals with plane images, patch coupling.

| Piece | Model |
|---|---|
| Track, length l, width w, height h over the nearest plane layer of any net | R = ρl/(wt); L = L′(w, h)·l; C = C′(w, h, ε_r)·l split to both ends; sections ≤ `lmax`, so delay √(LC) and impedance √(L/C) follow the line |
| Via | barrel R and partial self-L between the layers it joins |
| Pour of a non-ground net | copper graph's pour links (2 mm strips) for R and L; plate capacitance εA/h over its contacts (coarse) |
| Ground net | pours = reference node; tracks and vias between pads and pours extracted |
| Neighbours (signal profile) | same-layer pieces of other nets within 1 mm: mutual L with plane images (K clamped at ±0.9), coupling C from patch potential coefficients over the dielectric slab (within 6 % of the layered field solver `kae.em.static` at gaps ≥ 3 h, up to 25 % low near h) |

| Profile | Sections | Short pieces (< lmin) | Line C | Coupling | Used by |
|---|---|---|---|---|---|
| `signal` | 0.5–5 mm (lmin 0.5 mm) | R only (L and C to the ends) | yes | yes | I2C, pairs |
| `power` | long R–L sections ≤ 20 mm, pour and via parasitics | none | no (0.1 pF/mm against µF of decoupling) | no | rails, converters |

- **Micrometre pieces:** the copper graph splits tracks at junctions into µm-long pieces; as full sections they put fF behind µΩ, the matrix goes near-singular, ngspice reported "timestep too small" at 2 ps [M]. Short pieces keep R, drop only their negligible L. All R ≥ 0.1 mΩ.
- **Connectivity:** copper graph ([`kae.route.copper`](../../../kae/src/kae/route/copper.py)) connects items as KiCad does: shapes colliding on a shared layer, round-ended tracks, jumper pad groups, net-carrying copper shapes, pours one conductor each. On 150 human boards it splits 5 nets KiCad reports connected; the earlier `NetGraph` split 353 (overlapping round track ends, pours with distant contact clusters, jumper pads, net copper shapes) [M]. Custom pad primitives are still modelled as the pad's rectangle.
- **Copper islands:** test pins are checked against copper islands first; a split test is `incomplete` (stranded pins listed, routed runs skipped), since a load on an island returns only through the 10¹² Ω leak and the solver would chase 10¹¹ V.
- **Limits:** ideal plane under each piece (slots and splits are for geometric checks); power planes as AC ground for line C; no broadside coupling across layers; no pad copper or thermal spokes; no skin effect; coarse pours (a sheet solver, the engine's K2 operator, would replace the 2 mm strip mesh).

## 4. Decks

- **Ideal deck:** every pin of a net on one node; ground nets = node 0. **Routed deck:** each pin of an extracted net is its own node, joined by extracted copper.
- **Board passives** enter a test only if every terminal is on a test net, ground or a testbench-named net (else e.g. a capacitor's ESL feeds an undriven node).
- **Guards** [M]: KiCad names → generated names; `<…>` tokens resolving to nothing are an error; `v(a,b)` becomes a B-source probe (batch `.meas` cannot read it); `.option rshunt=1e12 method=gear`; every requested `.meas` must come back.
- **Dissipation:** a test naming `kae_pdiss` in its `.control` block gets a vector of the power in every board resistance (copper, resistors, capacitor ESR, inductor DCR), computed after the run, never as a probe node. Loss is summed over dissipating elements, never from sources' delivered power: that also counts energy still flowing into bus capacitors while the off-board feed settles (≈ 100 µs vs a 12-period run) and gave −3.5 W on a 1 W cell [M].

## 5. Verdicts

Verdict rules (pass / fail / marginal per requirement per mode; test status `unknown`, `incomplete`, `error`, else the worst requirement) → [functional-evaluation](../physics/functional-evaluation.md#5-inputs-verdicts-unknowns).

| Capability | Reported |
|---|---|
| `rail_dc` | load multiple at which the first pin reaches its bound, from the line through low and high corners (DC with current loads is linear) |
| `i2c` | fastest mode whose limit holds; with pull-up off board, bus capacitance and largest pull-up per mode |
| `pair` | delay and skew |
| `cell` | layout's power loss per corner, routed − ideal dissipation, also as share of output |
| `loop` | hot-loop inductance routed and ideal, and their difference |

`questions` ranks: (1) marginal verdicts and their prior inputs; (2) unknowns; (3) verdicts resting on priors alone.

## 5a. Budgets (`kae.sim.budget`)

`kae.sim.cli budgets` sweeps a series inductance at each cell's loop insertion point to derive a budget for the placer and critical router; it is applied only when trusted, achievable and stand-in independent, and only with `critical_cli route --budgets`, never by evaluators. None passed on the smoke boards. The boost loop's measures (router closed form vs mesh reference vs SPICE extraction) are cross-checked there too: [functional-evaluator-budgets](functional-evaluator-budgets.md).

## 6. Command line

```
python -m kae.sim.cli testbench BOARD.kicad_pcb [--pintypes F] [--schematic ROOT.kicad_sch] -o board.tb.cir
python -m kae.sim.cli evaluate  BOARD.kicad_pcb --testbench board.tb.cir [--pintypes F] [--schematic ROOT]
                                [--input TASK_INPUT.kicad_pcb] [-j 8] [--only ID ...] --workdir DIR -o eval.json
python -m kae.sim.cli questions eval.json
```

`--input` builds the brief from the task's input board, so two layouts of one task share their tests.

## 7. Results [M]

**`balazsbencs-ardor-ardor-io`** (Raspberry Pi HAT, 99 footprints, fully connected; values from its schematic): 8 tests, 44 simulations, 6 s.
- Rails +5V_PI and +5V_A (derived through ferrite FB101) pass DC drop and load step. Copper adds ≈ 8 mV to the ferrite's 11 mV on +5V_A at the load prior; capability 7.2× the prior before the first op-amp pin reaches 3%.
- I2C buses ≈ 11.4 pF routed (9.9 pF from pins): pull-ups up to ≈ 31 kΩ in Fast-mode.
- 4 tests unknown: I2C pull-ups off board; +3V3_PI with no recognised load.

**`azlan-works-argo-argo-v2`** (CM carrier, 80 footprints; human board unfinished): 50 tests, 199 simulations, 338 s.
- KiCad reports 132 unconnected items, incl. GND, VBUS and the buck's switch node; tests touching them are `incomplete` with stranded pins listed.
- 23 differential pairs: 75–260 ps routed vs a 100 ps driver-and-load ideal; intra-pair skew CRX1 30 ps, USB31_TX 6 ps.
- 2 pairs still time out; 1 reports a singular matrix at a ground node.

**Switching cells** (stand-ins; no LLM, no schematic). Every corner of both boards converges; 1–3 min per corner routed.

| Board | Cell | Hot loop routed vs caps alone | Loss ideal / routed | Other |
|---|---|---|---|---|
| `acarpm-chesslab-powerboard` | MT3608 boost, 3.7 V cell → 5 V; loop D3, C5, IC1 ground | 2.7 nH vs 1.0 nH | 0.28 / 0.29 W | conduction +15 mW; edges lose less (5.1 vs 9.8 nJ/period: loop L slows turn-on current); switch node peaks 8.5 V routed vs 5.6 V ideal: marginal on the prior bound (needs MT3608's switch rating) |
| `aarondennis-mup-astro-cat-hardware-astro-cat` | DRV88xx, 4 motor phases on 12 V, PWM prior 20 kHz | 1.66 nH vs 0.24 nH (4 caps parallel) | 0.22 / 0.23 W | conduction 0.206 W vs I²·R_on = 0.200 W; each phase rings to 26 V vs 11.9 V ideal (upper bound, §9) |

**LLM pilot on ardor** (one agent, 146k tokens, ≈ 10 web lookups, 9 min): replaced priors with cited datasheet intervals and bounds (ADS1115, OPA2320, TPA6132A2, Omron G5V-1, H11L1M; the Raspberry Pi's 1.8 kΩ I2C pull-ups, confirmed by the schematic's "Pi has them"). 4 pass / 4 unknown → 8 pass / 0 unknown. Found 8 errors in the automatic testbench, all fixed:

| Error | Fix |
|---|---|
| loads behind a ferrite on +3V3_PI missed; rail trees split into separate tests | supply trees through ferrites, fuses, small resistors (also finds supplies the brief did not name) |
| a relay's current returned at a contact pin, not through coil and driver; an IC's current at a grounded input, not PGND | IC current returns at its ground pin nearest the supply pin, other loads at the reference |
| I2C bus stopped at a 33 Ω series resistor | I2C lines followed through series resistors |
| resistor loads (pull-ups, dividers) ignored | dividers simulated, pull-ups counted at V/R |
| audio-rate loads stepped in ns | only logic ICs step in ns |
| two ideal sources on one rail make the ideal deck singular | parallel ideal sources merged |

On ardor the automatic testbench now judges the 3.3 V tree (was unknown); only the off-board I2C pull-ups still need an outside fact.

## 8. Next

1. Add crosstalk victim tests on routed copper, leakage and creepage, excitation and radiator inventories with the source-to-radiator check, antenna feed. Stand-ins: boost and half-bridge done (generic cells, hot-loop test); next flyback, buck-boost, charge pumps, LDO and load-switch dissipation, creepage and clearance vs working voltage. Find the cause of slow and singular signal runs (scaling couplings to keep the inductance matrix positive definite did not cure them).
2. Hook into kaeres as a new evaluator (evaluator id hashes the code tree) beside legacy `physics_total`; report per category, never inside cp1, cpk or `score.py` (deployment rule canonical in [functional-evaluation](../physics/functional-evaluation.md#6-trusting-the-evaluator)).
3. Re-run routed-physics baselines under the new connectivity (it changes the evaluator id); model custom pad primitives.
4. Before KiCad 11, port the SWIG `pcbnew` users (fills, board writer) to the IPC API.

## 9. Cell stand-in and numerics

**Stand-in:** log-linear switches (50 mΩ to 1 MΩ), body diodes (20 mΩ, 10 ns transit), 100 pF across each switch, inductor or winding held as a constant current source. Gives the copper's share of loss and the hot-loop ring, not control behaviour or ripple. Ring peak is an upper bound: SPICE diode recovers abruptly (body diodes softly); C_oss linear and lossless; copper and capacitor R at DC values (no skin effect). Loop inductance depends on none of these. Vendor or Verilog-A models would replace it.

**Numerics, checked by refinement** [M]: every change to how a cell is solved is checked against a finer reference; one that alters the circuit's physics is rejected.

| Choice | Evidence |
|---|---|
| Gear integration | holds p_loss within 0.01% from 0.25 ns step down to 2 ps; trapezoidal moved the peak by up to 3.5× (numerical ringing), not used |
| Step = min(T_SW/20, 0.25 ns), forced everywhere | within 0.2% of a 25 ps reference; step left to error control read the peak 6% low |
| Loss after the run, in `.control`, from converged waveforms | a B-source probe node for the v·i sum carries sub-nA solver noise and stalled solves that converge without it; an aborted run reports nothing, never a partial-waveform value |
| Diode series R 20 mΩ | without it the diode is a bare exponential on a Q ≈ 30 ring and Newton fails; with it every corner converges; result moves < 1.5% between 5 and 20 mΩ |
| C_oss loss 0.05 Ω (low end of 0.05–1 Ω) | at 1 ns edges 4 of the fixture's 9 corners failed with any solver setting, even `itl4=500`, and a 0 V link in the loop flipped the typical corner (ideal C_oss ringing at Q ≈ 30). Real C_oss charges through the switch's spreading resistance (hysteresis loss), which damps measured switch-node rings to Q ≈ 3–10. With 0.05 Ω every corner converges; loss moves < 0.5%; peak drops 0.2% (fixture), 0.2% (boost), 1.5% (motor driver); at 1 Ω the motor driver's peak is 10% lower |
| Simulated at max(F_SW, 300 kHz) | constant winding current: loss per period = conduction (settled middles of on and off intervals) + edge energy `e_sw`; `p_loss` = p_cond + e_sw·F_SW; each ring decays in ≈ 25 ns vs flats ≥ 1 µs |
| Frequency priors when the part table has none | motor drivers 1–100 kHz (typical 20 kHz), discrete half-bridges 20–500 kHz, integrated converters 150 kHz–3 MHz. A single 0.3–3 MHz prior had put motor drivers at converter frequencies, where a 100 ns edge and its dead time left a negative on-time and the switch never turned on |

## Open questions

- **Runtime:** most signal tests ≈ 1 s per corner, but a few large pairs reach the 300 s cap; power tests ms to s.
- **LLM cost:** ≈ 150k tokens per board for the questions-only pass; a per-part fact cache should lower it on later boards.

## Sources

- Code and tests: [`kae/src/kae/sim/`](../../../kae/src/kae/sim/), [`kae/tests/test_sim.py`](../../../kae/tests/test_sim.py).
- Reused: [`critical_recheck.py`](../../../kae/src/kae/route/critical_recheck.py) (RoutedBoard, fills), [`copper.py`](../../../kae/src/kae/route/copper.py) (NetGraph), [`kernels.py`](../../../kae/src/kae/physics/kernels.py), [`fastloop.py`](../../../kae/src/kae/physics/fastloop.py), [`priors.py`](../../../kae/src/kae/physics/priors.py), [`brief.py`](../../../kae/src/kae/circuit/brief.py).
- Related: [physics-critics](../physics/physics-critics.md).
