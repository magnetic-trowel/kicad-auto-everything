# Hot-loop evaluation: per-cell primaries, open cells, the window solve

Scope: how `kae.excite.evaluate` measures a switching cell's commutation (hot) loop and how `kae.intent` prices it: open cells, the per-cell window solve, its pitch, what it leaves out. Not here: the loop physics and expert layouts -> [pdn-and-commutation](pdn-and-commutation.md#1-commutation-loop-geometry); the router's own loop quote -> [critical-net-routing](../routing/critical-net-routing.md); the hot-loop routing design and A/B -> [kae-hot-loops](../../research/routing/kae-hot-loops.md).
Keys: hot loop, commutation cell, commutated current, L_loop, R_loop, overshoot.peak, loss.loop, loss.loop_ac, loss.swnode, open cell, open_cells, cells, window solve, CELL_PITCH, MARGIN_H, kae.excite.hotloop, skin correction, cap body, ESL, ½·L·I²·f, EPC, loss.copper_ac, inductor ripple, kae.excite.ripple, scope losses, AC copper loss

Tags: [C] computed by the scripts named; [I] inference; [P] primary source.

## 1. What a cell is measured as

A cell (`kae.excite.sources._cell`) is a unit current source across its switch; the circuit (`kae.excite.circuit`) splits the commutated current over the cell's capacitors at each frequency. I and D below are the cell's commutated current and duty by topology ([converter-currents](converter-currents.md#1-equations-ccm-steady-state)): a buck at I_out through its input capacitors, a boost (and a boost LED driver) at its input current I_out·V_out/(V_in·η) through its rectifier and output capacitors (the switch sits SW→PGND and the rectifier SW→VOUT, so the solve closes the loop through COUT), a 4-switch leg static in its region at 0. Per cell, with the overshoot observer k at the switch port and the layout's share `z(f) = J_kᵀ·v − J_kᵀ·v_ideal` (copper solve minus the same parts with ideal copper, [functional evaluation](functional-evaluation.md)):

| Quantity | Definition | Where |
|---|---|---|
| `L_loop` | `Im z(f_e) / (2π f_e)`, f_e the edge band (≤ 10 MHz, `observe.gentle_f`) | ev.json `cells[].L_loop_nH`; board solve: `rings`, `loss.loop` label |
| `R_loop(f)` | `Re z(f)` at f_sw, 3·f_sw, 5·f_sw (a trapezoid's odd harmonics) | `cells[].R_loop_mohm` (f_sw), `cells[].R_harmonics` |
| overshoot peak | `|Z(f_sw)|·(2/π)·|sin πD|·I + L_loop·I_pk/t_i` per corner (`harm.peak`; I_pk the turn-off current) | `cells[].overshoot_V` {typ, worst}; board solve: `overshoot.peak` |
| `loss.loop` | `½·L_loop·I_pk²·f_sw` per corner (I_pk = I + ΔI/2 when the inductor is in the circuit, else I) (max(L_loop, 0): a negative copper share costs nothing, the cell stays) | observation |
| `loss.loop_ac` | with a refined window: `Σₙ |cₙ|²/2 · R_loop(n·f_sw)`, `cₙ = (2I/nπ)·|sin nπD|·sinc(n·f_sw·t_i)` (199 harmonics), R_loop(f) from the window's solves at f_sw, 3 f_sw, 5 f_sw (lateral crowding toward the return in the field solve, crowding through the thickness by `kae.em.skin`), log-log between them and `∝ √f` above 5 f_sw; it reduces to `I²·D·(1−D)·R` for flat R. Without a window: `I²·D·(1−D)·R_loop(f_sw)` of the board solve, no skin (a lower bound) | observation (`scope.R_harmonics_mohm`) |
| `loss.copper_ac` | the inductor's ripple (§ 7): `Σₙ cₙ²·P₁(n·f_sw)` | observation |
| `loss.swnode` | `½·C_sw·V²·f_sw`, C_sw from the electrostatic solve | observation |

The board solve (0.25 mm) gives the observations the intent prices; the window solve (§3) gives the per-cell primaries, reported beside the board solve's values (`cells[].global`) for cell-by-cell comparison of layouts. `kae.intent` copies the rows into `status.cells`; `python -m kae.excite.hotloop A.ev.json B.ev.json ...` pairs two arms cell by cell.

## 2. Open cells

A cell whose loop copper is open (the injection cannot close through copper and the lumped parts: an unrouted hop) used to be "not computed": every term it could feed went unpriced and the cell left that arm's sum, so a router that left a hot loop open looked no worse than one that routed it badly (route-finish-ab: 4–9 cells per arm without a value, [kae-hot-loops](../../research/routing/kae-hot-loops.md#measured-gap-per-cell-diagnosis-24-boards-evaluator-at-025-mm-c)).

Now (`evaluate.open_cell_observations`), an open cell has explicit observations at caps that are the same for every layout:

| Observation | Cap | Why |
|---|---|---|
| `overshoot.peak` | `V_abs − V` (the switch's absolute maximum above the bus; prior rating when unknown, `criteria.overshoot_limits`) | the commutated current has no path but the switch: it rings to breakdown |
| `loss.loop`, `loss.loop_ac` | `V·I`, the cell's throughput | a converter whose hot loop is open converts nothing; a closed loop reaches `½·L·I²·f = V·I` only at `L = 2V/(I·f)`, microhenries |
| `loss.swnode` | computed as for a closed cell | C_sw is electrostatic and needs no closed loop |

- ev.json lists the cell under `open_cells` (with the open islands); its other harms (supply, pickup, cable) stay not computed.
- `kae.intent` prices terms on `overshoot.peak`, `loss.loop`, `loss.loop_ac`, `loss.swnode` with these values instead of marking them incomplete (`objective._gap`, `OPEN_KINDS`); the status lists `open_cells` with the terms that priced them. A hard overshoot term is violated: an open hot loop is a broken converter.
- In a paired comparison (`hotloop.paired`) a cell open in one arm only ranks worst for that arm (ratio ∞ or 0); open in both, it is counted, not compared. Medians keep every cell.
- **DRC-unconnected loop members.** The remaining copper can still close a loop when one loop pad is unrouted (hdmi2rgb U11's ground pin in arms A and C, priced at 3.1 and 7.4 nH). When a KiCad DRC report of the board is at hand (`--drc FILE`, or the scorer's `drc.json` / `score/drc.json` beside the board; `--no-drc` ignores it), a cell any of whose loop pads (brief `loop`, switch pins) it lists as unconnected is an open cell, priced the same way (`evaluate.drc_open_cells`; ev.json `drc` names the report).
- A cell whose pads are not in the copper model (`pads outside the copper model`) is `not_computed`, reported, not priced: that is the evaluator's gap, not the layout's.

## 3. The window solve

`kae.excite.hotloop.cell_rows` re-solves each closed cell in a window at `CELL_PITCH`:

1. **Window.** The parts through which ≥ 5 % (`SHARE`) of the cell's peak pad current passes (half the part's summed pad |J|: a module takes its share over many pins), for the cell's pattern or its overshoot observer's, at f_sw and f_e in the copper-free circuit solve, grown by `max(3 mm, 3·h)`, h the outer layers' depth to their next layer. It depends on placement and circuit only: every layout of one placement is judged in the same window at the same pitch. A window over 1.2 M cells × layers doubles its pitch (reported).
2. **Fine solve.** The same quantities as the board solve on the window's copper at `CELL_PITCH`, each copper layer's resistance scaled by `kae.em.skin.correction` per frequency (crowding beyond the nsub = 2 filaments; one-sided crowding: a loop over its plane). Frequencies ascend, each warm-started from the last. Pads the window left out (each below 5 %) are taken as a leak (`potentials_many(leak=SHARE)`); if the copper closes the loop only outside, the margin doubles (`grown`, at most 4 times).
3. **Truncation correction (two-grid).** The return of a 2-layer board and its bulk caps reach beyond any affordable window: at the board's own pitch the raw window read +12 % (qubik-bmps, 24 mm window) and +36 % (it8951 booster, 3 mm margin) over the board solve [C]. The window is solved again at the board's pitch without skin, and the cell's value is `fine window + (board solve − window at the board's pitch)`: the board solve corrected for pitch by the window, as truncation and pitch errors add to first order. Both terms are in `window` (`L_raw_nH`, `trunc_L_nH`, `R_raw_mohm`, `trunc_R_mohm`, `corrected`); the f_sw term also corrects the harmonics. The window must close at both pitches: a neck the fine raster resolves and the coarse one loses (qubik-bmps arm A: U1's exposed pad joins the pour only through thin copper) closes the loop inside at 0.0625 mm but not at 0.25 mm, so the margin doubles until both close (uncorrected, that cell read 2.12 nH against the board's 1.37; corrected, 1.27). The correction must also be small: when the window at the board's pitch differs from the board solve by more than half the board's L_loop or R_loop (`TRUNC_MAX`, floors 0.1 nH and 0.5 mΩ), the window misses where the loop closes on the board and the margin doubles too; if it never gets small, or the corrected L_loop is not positive, the board solve's values stand (`refined: false`, `why`). Before this check nekoink's boost read −0.17 nH in arm K: a 41 × 19 mm window closed the loop at 32.8 nH (39.4 nH at 0.25 mm) against the board's 6.5 nH, and the difference of two large pitch-dependent values went negative.
4. **Check.** At the board's pitch without skin the cell's value is the board solve's exactly; over the whole board the raw window matches it within 0.5 % (test).

**Pitch: 0.0625 mm** [C, `hl_cell_convergence.py`, human layouts, raw window L_loop]:

| Board (cell) | 0.25 | 0.125 | 0.0625 | 0.03125 mm | 0.0625 vs 0.03125 |
|---|---|---|---|---|---|
| powerboost (boost) | 1.132 | 1.091 | 1.065 | 1.069 nH | −0.4 % (R −1.3 %) |
| max98357 (half bridge) | 2.436 | 2.248 | 2.025 | 2.023 | +0.1 % (R +2.6 %) |
| it8951 booster (boost) | 6.831 | 6.425 | 6.283 | 6.300 | −0.3 % (R +1.8 %) |
| govish (buck) | 1.988 | 1.572 | 1.571 | 1.576 | −0.3 % |
| bq25306 (buck) | 1.604 | 1.445 | 1.415 | — | 0.125 vs 0.0625: +2 % |

0.0625 mm is within 0.5 % (L) and 3 % (R) of 0.03125 mm; 0.125 mm is up to 11 % off (max98357), 0.25 mm up to 27 % (govish). **Margin** (corrected values at 0.0625 mm, margins 3, 6, 12 mm against the default): within 3 % on four boards, +9 % at 3 mm on govish.

**Run time and a reverted window cap:** windows take a median 104 s per board, 49 % of an evaluation; `--cell-pitch 0.125` cuts that about 4× at up to 11 % L error, `--no-cells` skips it; a window on the loop's own pads moved L_loop up to 16 % and was reverted ([hot-loop-evaluation-runs § 1](../../research/physics/hot-loop-evaluation-runs.md#1-window-run-time-and-the-reverted-window-cap)).

**Scope `losses`** (`--scope losses`, `evaluate(scope="losses")`) solves only what the loss terms need: the cells' own bands (f_sw and the edge band) with their overshoot observers, the switch-node capacitance, the DC and heat bands (the heat band's copper temperatures scale the DC loss, TCR) and the cell windows. Every other source and observer is still set up, so the mesh, terminals and network are the full evaluation's and the values computed are bit-identical to it.

| Kept | Dropped |
|---|---|
| overshoot.peak, loss.loop, loss.loop_ac, the cells' rows (L_loop, R_loop at f_sw, 3 f_sw, 5 f_sw), loss.swnode, loss.copper, loss.part, drop.rail, heat.track, temp.junction | supply.peak, pickup.peak, cable_cm.v (every non-cell source's solves, every noise and EMI observer) |

This evaluator has no board-level AC copper loss outside the cells (ripple in caps, inductor ripple in rails): `loss.copper` is the DC band's; only `kae.excite.wideband` adds switching harmonics to it. kae.intent marks terms on dropped kinds incomplete (`scope losses: …`), never zero. Kept observations are bit-identical to the full evaluation on five boards; the saving is on boards with many sources (librewave-ecp5 6,192 → 1,140 s) ([hot-loop-evaluation-runs § 1](../../research/physics/hot-loop-evaluation-runs.md#1-window-run-time-and-the-reverted-window-cap)).

## 4. Validation on human layouts

Window and board solve order two layouts of a cell alike in 81 of 82 pairs; human L_loop of integrated converters 0.24–2.35 nH (median 1.2), inside TI SNVA803's and EPC's ranges [C, P]; counting open cells moves arm C from 1.10× to 1.38× human L_loop. Tables, the harmonic sum's effect on `loss.loop_ac` and the human-layout runs: [hot-loop-evaluation-runs § 2](../../research/physics/hot-loop-evaluation-runs.md#2-validation-on-human-layouts-2026-11-14).

## 5. Capacitor bodies: not modelled, and why

Two-pad parts are lumped branches between their pads' terminals (`mesh.Lumped`): the capacitor's ESL is a number with no field, so cap orientation and alternating paralleled caps (0.38–0.46× vs 0.54–0.62× of a single cap, [pdn § 3](pdn-and-commutation.md#3-decoupling-capacitors-mounting-orientation-spreading)) are invisible. A body bar (the cap's internal path as a strip at body height between its terminations, as the router's `critical_physics.Loop.body`) was considered and not added [I]:

- **Not faithful in absolute value.** The bar reads 1.3–2× the measured mounted inductance (Axotron; pdn § 3): the current runs through an interleaved electrode stack, not a solid bar.
- **Double counting.** The evaluator prices the copper's share, the solve minus the same parts with ideal copper. A body in the raster carries its own loop L, already inside the datasheet ESL the lumped model keeps; subtracting it needs the ESL fixture's geometry (plane depth, pads), which datasheets do not give.
- **Not a routing lever in the A/B.** Route tasks keep the human placement, so every arm has the same caps in the same orientation; orientation and alternation are placement levers (P1 in the design doc). What routing changes under a cap, the return plane, the raster already sees at the pads and the hop copper (the bq25306 plane cut: 82 % of A's gap, [kae-hot-loops](../../research/routing/kae-hot-loops.md#measured-gap-per-cell-diagnosis-24-boards-evaluator-at-025-mm-c)).
- **Cost.** A body needs a raster layer above the top copper (and one below the bottom for bottom-side caps), a via landing joining two nets (`Network` lands a via on one net only) and the ESL fixture's model: medium cost for a placement-only effect. Use the router's `Loop.body` for placement and joint tasks (J1, P1).

## 6. Absolute loss scale: ½·L·I²·f understates

`loss.loop = ½·L·I_pk²·f_sw` is the energy of the loop's inductance at turn-off, at the inductor's peak I_pk = I + ΔI/2; turn-on is not charged, its inductance acting as a snubber ([converter-currents § 4](converter-currents.md#4-turn-off-current-what-the-hot-loops-inductance-costs)). EPC measures more than 4 % efficiency over 0.4 → 2.9 nH at 12 → 1.2 V, 1 MHz, about 0.4 W/nH at an assumed 20 A against ½·L·I²·f's 0.2 W/nH, 0.26 W/nH at I_pk with 30 % ripple: the rest is slower commutation and the overshoot's own loss [P, I] ([kae-hot-loops](../../research/routing/kae-hot-loops.md#what-experts-do-and-why-quantified)). The factor depends on the cell (integrated vs discrete switches, gate drive), not on the layout, so for one cell it is a constant: layout ratios and rankings hold; watts across cells of different classes do not compare. Not retuned: a per-class switching model is an open question.

## 7. Board-level AC copper loss: the split between loss.loop_ac and loss.copper_ac

A converter carries two AC currents besides its DC: the commutated (pulsed) current between the hot-loop capacitors (a buck's input, a boost's output) and the switches, and the inductor's triangular ripple through the switch node, inductor, output capacitors and ground. The split is by current, not by region:

| Term | Current | Where it is counted |
|---|---|---|
| `loss.copper` | DC load and source currents | whole board (DC band) |
| `loss.loop_ac` | the commutated current, its harmonics | whole board: `R_loop = Re Jᵀ Z J` at the switch port is, by Tellegen, that pattern's dissipation in all copper it reaches (bulk caps, input traces, planes), less the parts' ESR redistribution; the window refines it near the cell, the truncation correction keeps the rest of the board |
| `loss.copper_ac` | the inductor ripple, its harmonics | whole board (`kae.excite.ripple`) |

No region is counted twice. Left out: the cross term where both AC currents share copper (the switch's ground pins), cells without an inductor in their structure, and non-converter AC currents (clocks, IC cores), which `kae.excite.wideband` includes.

**Model** (`kae.excite.ripple`). A Norton source across the inductor's pads, solved on the board solve's network at f_sw, 3 f_sw, 5 f_sw; per unit amplitude `P₁(f) = ½ Σ_b R_b(f)·|I_b|²` over the copper branches (filaments, via barrels; not parts), each layer's R × `kae.em.skin.correction(f)`. Triangle of `ΔI = V·D·(1−D)/(L·f_sw)` peak to peak (V the switch's bus; CCM, capped at 2 I), `cₙ = ΔI·|sin nπD| / (π²n²·D(1−D))`, `Σ cₙ²/2 = ΔI²/12`. L from the inductor's circuit model. A path open beyond a 1 % leak marks `ripple:<cell>` not computed; only `loss.copper_ac` terms see it.

**Pricing.** An intent that prices `loss.copper` (cost, unscoped) and says nothing of `loss.copper_ac` prices it the same (term `<id>ac`); `neutral/1` adds `D1ac`. Evaluations without the kind price as before.

**Hand check** (fixture buck, 12 V, D 0.275, 4.7 µH, 1.1 MHz): ΔI = 0.462 A; R_eff at f_sw 9.8 mΩ against ~8.8 mΩ by hand (5.8 mm of 0.5 mm track outside the pads at 0.98 mΩ/mm, two 0.3 mm barrels at ~1.05 mΩ, ~1 mΩ of plane); loss = ΔI²/12·R_eff within 3 % (`test_the_inductor_ripple_copper_loss_matches_a_hand_estimate`).

Measured on the converter boards (copper_ac against copper and loop_ac, and against `kae.excite.wideband`): [hot-loop-evaluation-runs § 3](../../research/physics/hot-loop-evaluation-runs.md#3-ac-copper-loss-on-the-converter-boards).

## Use the solver, not the routed-copper estimator, for comparisons

`kae.route.critical_recheck` (what the critical router optimizes: closed-form strips over image planes, one brief loop through the brief's chosen input cap) disagrees with the field solve: over 68 cell/arm pairs of the hot-loop diagnosis it reads a median 1.85× the solver's L (0.31× to 7.5×), orders two layouts of a cell the same way only 41 of 55 times (75 %), and gives −0.24 nH on the human bq25306 board (a strip with no plane under it mixed with imaged strips) [C, diagnosis `estimator_vs_solver.csv`]. Compare layouts with the solver's cell rows (§ 3), never with the estimator.

## Open questions

- Does the router's quote (fastloop, image plane) rank cells as the window solve does? Spearman ρ on the hotloop A/B's cells.
- R_loop at even harmonics and above 5 f_sw is interpolated and extrapolated (√f), not solved; a resonance near a harmonic (gecko5 U13: 15, 24, 136 mΩ at 1, 3, 5 f_sw) then weighs on everything above it.

## Sources

- Code: `kae/src/kae/excite/hotloop.py`, `kae/src/kae/excite/evaluate.py` (`open_cell_observations`), `kae/src/kae/intent/objective.py` (`OPEN_KINDS`, `_gap`).
- Tests: `kae/tests/test_excite_hotloop.py` (open cells, window vs board, ranking, file order, threads).
- Convergence: `tools/research/physics/hl_cell_convergence.py`; mesh bias at 0.25 mm: [field-solver-accuracy § 3](../../research/physics/field-solver-accuracy.md#3-mesh-bias-at-025-mm-e7).
