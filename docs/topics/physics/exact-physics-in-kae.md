# Exact physics in kae: `--physics-fidelity fast|exact|multi`

**TL;DR**
- `kae.physics.exact` evaluates routed loops (hot loops, power paths, decap loops, surge paths) by the research's reference solver: multi-filament PEEC over an image plane, inductive limit, on the same Loop network the module stage and the recheck build. It equals pw_peec to 10⁻¹² on Manhattan copper and handles any-angle copper (oblique filaments within 2·10⁻⁶ of Grover and adaptive quadrature) [C].
- `--physics-fidelity` (default `fast`, unchanged behaviour): `exact` uses PEEC for every routed-loop quote of the module stage and the recheck; `multi` searches with the closed forms and re-scores each via decision's fast top K (default 4) by PEEC, and evaluates finished boards by PEEC. The joint loop gets exact acceptance physics from one `configure` call [C].
- On 5 boards with switching cells and decaps a PEEC quote costs 8–22 ms cold and 0.9–1.8 ms warm (block cache) against 0.4–1.3 ms closed form; the module stage takes +10–40% in exact mode; multi is within the ±12% run-to-run noise [C].
- PEEC changed 4 of 41 multi decisions (all decap via sites), each lowering that module's exact L by 0.2–1.0%. Larger differences (−38% to +4% on single modules) are knock-on: later modules route around different copper. Summed exact L moves by −2.1% to +1.9% per board [C].
- So, as [exact-physics-options](exact-physics-options.md) predicted, exact physics on copper buys little in decisions; its value is the reported number (closed forms read +1.8% to +6.4% high in median per board, −21% to +36% per module) [C].

Tags: [C] computed on one core of the shared 4-core VM (KiCad 10.0.7 route tasks of `kae-work-v3`); [I] inference.

## 1. What is exact here

| Structure | Fast (closed form) | Exact (`kae.physics.exact`) |
|---|---|---|
| Hot loop, power path, decap loop | `critical_physics.Loop.value`: fastloop partial inductances with images, Hammerstad–Jensen strip self terms, projected oblique pairs | `loop_value(lp)`: PEEC on the same pieces, KCL rows and active set |
| Surge path (chain) | L′(w, h)·length + via | `surge_path(pts, w, h)`, `chain_module_exact(ctx, m)` |
| Thermal (placement) | fin kernel with edge images | `ThermalFV(terms)`: 2.5-D finite volume, factored once, cached 1 W source fields |

**PEEC model** (as pw_peec and ex_exact.peec_solve): a strip of width w at height h is nw filaments across its width (filament width below h/3, at most 60, none thinner than 1.2 t), t = 35 µm, at h + t/2; a vertical piece is a 6-filament ring (25 µm plating). Partial inductances by Neumann's integral: parallel filaments in Grover's closed form (self terms at the GMD 0.2235(w + t)), perpendicular ones zero, oblique ones by Gauss–Legendre along one filament of the analytic integral along the other, graded geometrically toward the closest approach (touching and crossing filaments). Images: mirrored end points, current reversed. Each piece carries its element's current, free to crowd across its filaments; the loop L is the minimum magnetic energy under the pieces' sums and the Loop's KCL rows, with alternative currents kept ≥ 0 as Loop does.

What it does not remove: the plane is still ideal and per strip (the Loop's model), so cut planes, far-side decaps and real stack effects stay as the Loop models them; for those the real-copper stack model of [suite-physics-results](suite-physics-results.md) is the next rung ([solver-ladder](solver-ladder.md)). PEEC is a better model, not a measurement ([validation-program](validation-program.md)).

Blocks of the filament matrix are cached per pair of pieces, so a via search re-uses its hops' blocks; that is why warm quotes cost about a closed-form quote.

## 2. Validation [C]

`kae/tests/test_physics_exact.py` (18 tests, 42 s):

| Check | Reference | Result |
|---|---|---|
| Hot-loop validation geometry (pt_validate_kernels.cell_segments, A*-routed, 24 loops) | pw_peec | rel. difference ≤ 10⁻⁹ (max seen 5·10⁻¹³) |
| Parallel ground return (surface track ∥ vias through the plane) | ex_exact.peec_L nodal solve | ≤ 10⁻⁹; shares sum to 1 |
| pw_peec.exp_validate: square wire over a plane, h 1 / 5 mm | 81.16 / 150.63 nH | same to 0.006 nH |
| same: 10 mm strip, h 0.1 / 0.2 / 0.5 mm | 130.5 / 242.7 / 549.4 pH | same to 0.06 pH |
| Filaments meeting at 30–135° | Grover's corner formula | ≤ 2·10⁻⁶ |
| Separated and crossing oblique filaments | adaptive quadrature | ≤ 2·10⁻⁶ |
| Loop with 45° hops turned by 45° and 0.3 rad | itself | ≤ 2·10⁻⁵ |
| Closed forms on the 24 routed loops ([place-terms §2](place-terms.md#2-loop-inductance-a-b): 5.0% median, 9.4% max on 324) | PEEC | kernels.loop_L 3.9% median (8.2% max); Loop.value 3.3% (7.8%) |
| FV operator, tm_board_thermal_fv E0 (uniform 2-layer board) | 11.59, 8.14, 4.87, 2.21 K at r = 5–40 mm | same to 0.006 K |
| ThermalFV on the buck test board | ex_exact.FVThermal | rises to 10⁻⁹; a second evaluation solves nothing |
| Module stage, synthetic board, all three fidelities | — | same statuses; multi makes decisions; multi's exact L ≤ 1.02 × fast's |

`pytest kae/tests/test_route_critical.py` (54 tests) passes unchanged in fast mode.

## 3. Using it

```bash
# critical router (module stage, bridge, recheck rounds)
kae/.venv/bin/python -m kae.route.critical_cli route IN.kicad_pcb OUT.kicad_pcb --rounds 2 \
    --physics-fidelity multi --physics-k 4
# routed physics of a finished board, by PEEC
kae/.venv/bin/python -m kae.route.critical_cli physics BOARD.kicad_pcb --physics-fidelity exact
# as a kaebench method
kaebench run --adapter kae-crit --kinds route --command \
  "<venv>/bin/python -m kae.route.critical_cli route {input} {output} --seed {attempt} --time {timeout} --physics-fidelity multi"
```

The route report gains `physics_fidelity`: mode, k, decisions, changed, PEEC calls and seconds, failures (PEEC fell back to the closed form), per decision kind.

**Where it plugs in** (all no-ops in fast mode):
- `critical_physics.Loop.value` calls `exact.loop_hook` first: PEEC when the mode is exact or inside `exact_now()`.
- `critical_modules`: the cell return-via pair, the cell's extra vias and the decap cap/IC ground vias choose through `exact.pick(cands, rescore)`: the first lowest value (as before), or in multi the fast top K re-scored by PEEC.
- `critical_recheck.board_physics` carries `@exact.final_fidelity`: in exact and multi, stage values, recheck and the retweak's badness are PEEC.
- In-process callers: `exact.configure(mode, k)` once (or `with exact.scope(mode, k):`); `exact.add_cli_args(parser)` adds the two flags.

**Joint loop.** `JointStages.evaluate` takes `Scorecard.modules` from `recheck`/`board_physics`, so `accept` compares exact routed physics as soon as the process runs with `exact.configure("exact")` (the module stage then also quotes by PEEC); `scorecard.py` needs no change. The hook is in `joint/cli.py`: `EX.add_cli_args(r)` before parsing, `EX.configure(a.physics_fidelity, a.physics_k)` after. For exact acceptance with a fast module stage, `exact.routed_utilizations(board, brief, terms, stage)` returns `{module: u}` by PEEC whatever the mode.

**Thermal.** `ThermalFV(terms).cost()` prices the placer's thermal term with FV rises; a source move costs one solve (cached by pose), a victim move none. It is for multi-fidelity arbitration of placements (design (b)+(h) in [exact-physics-options](exact-physics-options.md#4-designs)) and is not wired into the placer.

## 4. Measurements [C]

`tools/research/physics/ex_fidelity.py` routes every loop module of a board (cells, power paths, decaps, chains; no rails, no bridge) once per fidelity from one shared setup, K = 4; `ex_fidelity_report.py` makes the tables. Outputs in `kae-work-v3/physics/exact-fidelity/` (not committed).

Cost:

| Board | Loop modules | Closed form, ms per quote | PEEC ms cold / warm | Module stage s: fast / multi / exact | PEEC calls multi / exact |
|---|---|---|---|---|---|
| libresolar bms-c1 | 15 | 0.41 | 21.9 / 0.9 | 3.9 / 4.1 / 4.3 | 24 / 193 |
| brenocq bldcm-power | 16 | 0.42 | 9.0 / 1.0 | 5.1 / 5.3 / 5.6 | 40 / 189 |
| justbuchanan oasis-pcb | 4 | 1.06 | 15.3 / 1.2 | 0.8 / 0.7 / 1.1 | 24 / 147 |
| tcsullivan noisecard | 4 | 1.26 | 10.5 / 1.8 | 0.5 / 0.5 / 0.6 | 34 / 172 |
| waterloo canhw-processor | 8 | 0.58 | 8.4 / 1.1 | 1.6 / 1.4 / 1.8 | 61 / 139 |

Medians over modules; a cell quote is up to 5 loops (cell variants). Stage seconds include routing (A*), which dominates.

Decisions and resulting physics (exact L of each module on the copper it ended with):

| Board | Multi decisions (changed) | Modules with other vias: multi / exact | Σ exact L, nH: fast / multi / exact | Closed form ÷ PEEC − 1 on fast copper: median (range) |
|---|---|---|---|---|
| bms-c1 | 4 (0) | 0 / 0 of 15 | 133.21 / 133.21 / 133.21 | +4.4% (−9.1…+14.9%) |
| bldcm-power | 10 (1) | 1 / 1 of 16 | 46.41 / 45.50 / 45.44 | +6.4% (−20.6…+35.8%) |
| oasis-pcb | 5 (1) | 1 / 1 of 4 | 36.21 / 36.19 / 36.90 | +1.8% (+0.5…+3.1%) |
| noisecard | 6 (0) | 0 / 0 of 4 | 15.77 / 15.77 / 15.77 | +3.8% (+1.6…+10.0%) |
| canhw-processor | 16 (2) | 2 / 2 of 8 | 35.02 / 35.00 / 35.10 | +4.1% (+2.5…+15.0%) |

- **Direct effect.** The 4 changed decisions (decap cap or IC ground via sites) lower that module's exact L by 0.2–1.0% (oasis L3 2.437 → 2.420 nH, bldcm U2 3.926 → 3.885, canhw U5 7.551 → 7.530, U4 2.184 → 2.179). Exact mode made the same choices as multi on every module whose own decision changed: K = 4 recalls the exact optimum.
- **Knock-on effect.** A different via changes the copper later modules route around: bldcm's U2 5 V decap drops 34–38% (2.61 → 1.73 / 1.62 nH) and its U9 path and decap move −1% to +4%; oasis's Q1 power path rises 3.3% in exact mode, canhw's U2 decap 2.4%. These are route-floor effects of module order, not physics, and they have both signs, so Σ exact L changes −2.1% (bldcm) to +1.9% (oasis) per board.
- **Few decisions.** Most modules make no via decision (pads already reach the plane, through-hole parts, chains with one site), so 41 decisions over 47 modules; 10% changed, above the 0.3–3.3% of [exact-physics-options §4(e)](exact-physics-options.md#4-designs) but over a small sample.

## 5. Open questions

- A suite run (all qualified boards, multi vs fast, same KiCad, manifest and suite; cp1, cpk, completion, per-type DRC) is the acceptance test of Stage 1 in [exact-physics-options §5](exact-physics-options.md#5-recommendation); it needs the 50-core host.
- Chains in the recheck and crystals keep their closed forms (ESD physics floor 0.3%, crystal 0%: [exact-physics-options §3](exact-physics-options.md#3-decision-flips)).
- Trim-width checks and the joint optimizer's module moves stay fast in multi (no candidate list); in exact they are PEEC.

## Sources

- Code: [kae/src/kae/physics/exact.py](../../../kae/src/kae/physics/exact.py), tests [kae/tests/test_physics_exact.py](../../../kae/tests/test_physics_exact.py), scripts [ex_fidelity.py](../../../tools/research/physics/ex_fidelity.py), [ex_fidelity_report.py](../../../tools/research/physics/ex_fidelity_report.py); references [pw_peec](../../../tools/research/physics/pw_peec.py), [ex_exact](../../../tools/research/physics/ex_exact.py), [pt_validate_kernels](../../../tools/research/physics/pt_validate_kernels.py), [tm_board_thermal_fv](../../../tools/research/physics/tm_board_thermal_fv.py).

See also: [exact-physics-options](exact-physics-options.md) · [place-terms](place-terms.md) · [solver-ladder](solver-ladder.md) · [joint-place-route](joint-place-route.md)
