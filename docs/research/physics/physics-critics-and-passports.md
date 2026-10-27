# Physics critics and conductor passports on real boards

**Status:** partial (the tools run on real boards and the 112-board suite; they are measurement instruments without calibration: model outputs, not measured physics).
**First published:** 2026-10-22, commits [19c91b3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/19c91b384a4724e2b9b77744406ba2fda772ec13) (critics), [91671c8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/91671c8dd253b6b08c5a5df98bd8f9acce5057c7) (real-board passports), [34a12a8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/34a12a8e561cd161f1e7e5983700aa50f0b47d1f) (suite passports) on branch `claude/vigilant-mayer-i91rrr`; per-module comparison `crit_compare.py` 2026-10-23 in [6d731a8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6d731a8168626034c1c30f3954f8e346a2507f53).

DRC checks copper against typed numbers and cannot see unintended physics: a return path crossing a void, a decap via adding nanohenries, a neck carrying 143 A/mm², one via carrying a whole rail. We built a physics scorecard separate from cp1/cpk: return-path critics read from the `.kicad_pcb`, DC and hot-loop "conductor passports" on routed boards, and a per-module human-vs-router comparison. They ran on all 112 qualified boards. **These are model computations on real geometry; none is calibrated against a measurement.**

## Idea and how it works

**Critics (scorecard).** About 39 critics plus 2 integrity checks read one board model at four fidelity tiers (F0 geometry, F1 closed form, F2 2-D field solve, F3 full-wave). Each emits continuous physical values with per-object attribution and KiCad-style markers; severity comes only from budget utilisation. The scorecard never feeds cp1, cpk or DRC. The prototype `pc_refplane.py` parses a refilled board's S-expression and implements:
- **RET-COV:** erode the nearest reference fill by w/2 + k·h, intersect track centrelines, call unexplained gaps VOIDs (k = 1 keeps 50% of return current, k = 3 keeps 80%; lateral spread (2/π)·atan(x/h), checked against PEEC within 0.02);
- **RET-VIA:** layer change between differently-netted references, distance to the nearest return via or bridging cap; RET-HOP, RET-EDGE, RET-REFNET;
- **RPQF-lite:** estimated / ideal loop L; **PLANE-PERF:** foreign tracks, islands, slots > 2 mm with half-wave frequency; **PWR-TRACE:** power nets on thin traces; **CAVITY:** largest empty circle between stitching vias → first cavity mode.
- VOID severity: shorted slot line (Z_slot 100 Ω), and an Ott-anchored fit ΔV = a·ℓ·ln(ℓ/ℓ0), ℓ0 ≈ 2.3 mm.
- **Ground truth by mutation:** plant faults (M-SLOT, M-TRACE-IN-PLANE, M-DEL-RETURN-VIA, M-SWAP-REF, M-DECAP-FAR, M-NECK) and keep only mutants whose `kicad-cli pcb drc --refill-zones` per-type counts are unchanged, i.e. DRC-equivalent; pair each with benign twins.
- Gaming guards: connectivity-qualified reference copper, continuous metrics, a frozen role model.

**Conductor passports on a routed board** (`rb_board_passports.py`, lens CD applied; see [first-principles-lenses](first-principles-lenses.md)):
1. Parse the saved board without KiCad (stackup, pads, tracks/arcs, vias, zone fills).
2. Infer roles: ground, rails, shunts R ≤ 0.2 Ω, driver IC, connectors, decaps.
3. DC model: each power net rasterised on its own grid (0.05 mm for VIN/phases, 0.2 mm planes); via barrels R = ρ·l/(π(d+t)t), t = 20 µm; terminal pads equipotential; one sparse LU per component.
4. Passports: Tellegen attribution a_b = i_p(b)·i_q(b)·z_b, cancellation index χ, leverage ρ_b = g_b·R_eff(b) (exact for selected pieces, a 48-solve JL sketch for all, checked by Σρ = n − c), exact removal a_b/(1 − ρ_b), Thevenin addition −Δφ²/(z + Z_th).
5. HF hot loop: stack-local magnetostatic window, each copper island a sheet, part current paths 0.3 mm above; energy per face (μ0/2)Σ h_g·H_g²; L from W = ½LI² (inductive limit, valid above ~0.7 MHz).
6. Beckmann R ≥ R_s·d²/A and a Frank–Wolfe relaxed floor with a duality gap.

**Suite passports** (`suite_passports.py`): per board, copy with reference rules, refill zones with kicad-cli, then in separate processes (600 s, 4 GB RSS watchdog) role inference, a DC passport for ground and every medium/high-confidence rail (≤ 300k nodes, COLAMD sparse LU, 1 A per load), necks, via bottlenecks (ρ ≥ 0.8; sole path ρ ≥ 0.999), dead copper, floors, and up to 3 hot-loop cells. `--boards-glob` runs the same on router outputs paired by task id.

**crit_compare.py**: per-module paired comparison of human vs router arms on the same route tasks: commutation and decap loop L (nH), crystal trace capacitance, surge-path L, per-rail source-to-load R (mΩ), via `kae.route.critical_recheck.board_physics`.

## What we tried

Boards (fetched at pinned commits from `bench/manifests/candidates.jsonl`, hash-checked, not committed; licences from that manifest):
- BLDCM-Power from [brenocq/bldc-motor](https://github.com/brenocq/bldc-motor), MIT;
- oasis from [justbuchanan/oasis](https://github.com/justbuchanan/oasis), Apache-2.0;
- Caffeinated-AFTONSPARV from [caffeinated-labs/Caffeinated-AFTONSPARV](https://github.com/caffeinated-labs/Caffeinated-AFTONSPARV), CERN-OHL-S-2.0;
- Pi5_PCIe from [m1geo/Pi5_PCIe](https://github.com/m1geo/Pi5_PCIe), MIT;
- the 112 boards of the KiCad 10.0.7 qualified suite (licences per board in the manifest).

## Results

All model outputs [C]. Sources: [physics-critics](../../topics/physics/physics-critics.md), [physics-critics-validation](../../topics/physics/physics-critics-validation.md), [real-board-passports](../../topics/physics/real-board-passports.md), [suite-physics-results](../../topics/physics/suite-physics-results.md).

**Critic self-test** (four open 4-layer boards): fired at 31/31 planted sites (M-SLOT 12/12, trace-in-plane 12/12, deleted return via 4/4, swap-ref 3/3), 0/7 benign twins, 1.4–2.7 s per board. Critic and mutants share an author, so this tests the method, not accuracy. Human-board findings: Pi5_PCIe PCIe pairs clean (RPQF 1.01–1.09) with 11 sideband void crossings; oasis USB D± change reference from GND to power (est. +2.9–3.4 nH). Slot proxy/PEEC ratio 0.97–1.18 at g = 2h but 1.75–1.94 at g = 0.5h (pessimistic for narrow voids).

**BLDCM-Power passports** (32 mm round, 4 layers, TMC6300 bridge, 50 mΩ shunts): the bridge return reaches ground only through 0.2 mm tracks and an exposed pad with no vias (1.76 mΩ, 20% of the 8.8 mΩ supply path); the 10 µF capacitor's three ground vias carry under 5% of DC but 86% of commutation current; the 3.3 V plane is the hot loop's image conductor (removing it raises L 9.1 → 25.4 nH); one 0.2 mm via carries 52% of J3's ground current (ρ 0.87). Best single added via −15% L (best of 511 legal sites, median −0.4%). Exactness vs brute force 3.5×10⁻¹¹; Foster sum 110,875 vs n − c 110,879; whole script ~48 s.

| Board (licence) | Hot-loop L | Energy in deepest gap | Inner-plane swap |
|---|---|---|---|
| oasis, LMR54406 (Apache-2.0) | 2.4 nH | 8% | −22% |
| BLDCM-Power (MIT) | 9.1 nH | 18% | −19% |
| AFTONSPARV, SY8201 (CERN-OHL-S-2.0) | 12.7 nH | 56% | −62% |

**Suite, 112 boards:** 112/112 ran, 15.2 min at 3 jobs, median 8.8 s per board, peak 3.3 GB; 335 rails on 90 boards, 22 hot-loop cells on 19. One via carries all supply current on 102/335 rails; median rail copper 9.7 mΩ; worst-load drop median 21 mV/A (p90 96); hot-loop L median 5.5 nH (p10–p90 2.1–17.9). On 18 complete A+B boards, Freerouting doubles the worst rail drop (median ×1.9, up to ×8.4). Critics: median 46% edge-critical length over the reference, 11 void crossings per board, 36 of 88 inner planes carry foreign tracks. COLAMD vs minimum degree: 82 s vs 2,749 s summed; address-space caps break SuperLU (use RSS watchdogs).

**Router comparisons** with `crit_compare.py` (ratios vs human; details on the routing pages): [2026-10-23-crit-v3-4e88308](../../../bench/results/2026-10-23-crit-v3-4e88308.md), [2026-10-25-crit-v6-10x-1ef5bf1](../../../bench/results/2026-10-25-crit-v6-10x-1ef5bf1.md), [2026-10-24-physics-fidelity-92afed4](../../../bench/results/2026-10-24-physics-fidelity-92afed4.md).

Caveats on the HF model: no lateral fringing (×1.52 high for a 1 mm strip at 0.2 mm), lossless, crude part paths (25–31% of L); the true BLDCM loop L is believed to be 6–9 nH. Use shares and rankings, not nH. DC grid 0.1 vs 0.2 mm moves R under 1%; HF grid moves L 7%.

**Red team** ([redteam-corrections](redteam-corrections.md)): ε_r = 1 electrostatics overstates world-charge shares up to ~4×; the ×2 removal price belongs to the square grid. Proposed falsification tests (critics rank ≥ 10 measured boards better than a rule count; critics separate autorouted from human boards above their false-alarm rate) have not been run.

## Verdict

As instruments these worked: cheap, exact on their raster, and they find real-looking problems that DRC cannot (single-via rails, missing exposed-pad vias, foreign planes in hot loops) and quantify what a router does to power copper. They are not validated: critic and mutants share an author, roles come from net-name regexes, the self-test found blind spots (own-antipad exclusion hides slots under a same-net pad), and crit v6 shows critical arms with more return-coverage findings yet better inductance on every metric (unresolved). Left: calibrate the HF model against FastHenry or openEMS, EMI/thermal ground truth, DECAP-L/HOTLOOP-L/thermal/HV critics, a packaged `physics-report` tool.

## Code

`tools/research/physics/`:
- `pc_refplane.py`: `python3 -I pc_refplane.py BOARD.kicad_pcb [--json OUT] [--roles ROLES.json] [--selftest]` (reads a refilled board; `kae/src/kae/board/sexpr.py` is adapted from its parser); `pc_budget_calcs.py`.
- `rb_board_passports.py`: `python -I rb_board_passports.py BOARD.kicad_pcb [--quick] [--no-hf]`.
- `suite_passports.py`, `suite_physics.py`: suite runners; outputs go under a git-ignored work dir.
- `crit_compare.py`: `--tasks DIR --out DIR --arm name=results/<run>/<adapter>`; imports `kae`.

Board files are never committed; only summary numbers are.

## Related

[first-principles-lenses](first-principles-lenses.md) (lens CD), [validation-program](validation-program.md), [routing area](../routing/README.md) (critical copper uses `kae.route.critical_recheck`), [physics-critics-catalog](../../topics/physics/physics-critics-catalog.md), [critics ideas](../../ideas/physics-first/critics.md).
