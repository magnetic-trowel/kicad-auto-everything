# Red team: verdicts, 76 corrections and independent re-derivations

**Status:** worked (as a verification pass; it found and fixed errors). Everything checked is still model vs model.
**First published:** 2026-10-22, commit [91f22fa](https://github.com/magnetic-trowel/kicad-auto-everything/commit/91f22faad5ebda7c28519a13ba33511a2c67cad9) on branch `claude/vigilant-mayer-i91rrr`; corrections applied in [7fd127b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/7fd127b819838f14a0be1e22327c6367a8ce68f9) and [287e1f2](https://github.com/magnetic-trowel/kicad-auto-everything/commit/287e1f23aa2ccc12b4e407db2990758395ff16cd); folded into [verification-and-limits](../../topics/physics/verification-and-limits.md) at [91671c8](https://github.com/magnetic-trowel/kicad-auto-everything/commit/91671c8dd253b6b08c5a5df98bd8f9acce5057c7).

A third round re-implemented each load-bearing physics claim by a method its author did not use, issued verdicts on 15 claims and 76 verbatim text corrections, and wrote down where rule-following beats physics-first. It is the main reason to trust (or distrust) the numbers on the other physics pages. **Its checks are independent re-derivations, not measurements: "no [C] number here has met a measurement".**

## Idea and how it works

Every number the architecture relies on should pass three checks: an independent method, a refinement (convergence) study, and a reference validated where the optimizer actually selects, because optimizers drift to the edges of validated domains. For each claim the red team wrote a script `rt_*.py`, then issued corrections as records {file, verbatim current text, problem, replacement} and applied them to the owning docs.

It also recorded:
- **Steelman for rules:** at a fixed stackup "minimise length × h/w" picks the best hot loop 82–99% of the time vs 97–100% for the physics proxy MS2; the big computed wins (no slot under the net 24–38 dB, thin dielectric 15–17 dB) are textbook rules.
- **Pre-registered falsification tests:** e.g. ≥ 10 measured boards with ΔSpearman < 0.1 vs a rule-violation count falsifies the critics; joint place-and-route vs an equal-CPU portfolio on ≥ 20 real boards.
- **Independence note:** several idea ids are the same idea under different names (cut pricing = CT1, CT2, SY6–SY9, VP D4, CD2, CD6; world node = CT9, CT15, CT16, IN6, SY27, CD33, TH11). Agreement among lenses is "four routes to textbook results": evidence of correctness, not novelty.

## Results

The nine re-derivations (source: [verification-and-limits](../../topics/physics/verification-and-limits.md); scripts in `tools/research/physics/`):

| Script | Claim checked | Independent method | Verdict |
|---|---|---|---|
| `rt_cut_law.py` | slit law ΔR = (2/π)R_s·ln sec(πx/2), notch = exactly 2× | Galerkin crack-row, Chebyshev-U basis; exact rank-1 removal on lattices | holds to 6 digits (x = 0.02–0.9); the ×2 is grid-dependent (square 2, triangular 1.5, honeycomb 3), so the mesh-free statement is the polarization tensor |
| `rt_sheet_return.py` | ℓ50 = ℓ_m/2; "1 oz mirrors a 5 mm loop above 12 kHz"; "copper never damps" | spectral integrals + own 2-D PEEC | ℓ50/ℓ_m 0.42–0.53 holds for ℓ ≥ 6h; 12 kHz **wrong** (half-mirroring needs ~93 kHz); "never damps" **wrong** for plane pairs below ~30 MHz (Q 1.0/2.8/6.2/9.3 at 1/3/10/30 MHz, 0.1 mm, 1 oz); "1.3% outside" should be 18–27% |
| `rt_damping.py` | tuned snubber L_s·C_s ≈ L·C_oss; "damping is a 20–27 dB lever" | state-space eigenvalues + edge-plus-ring spectrum | Q values reproduce; lever **overstated 6–8 dB** (Q 10→1 buys 12.5–15 dB, 20→1 buys 18–21 dB) |
| `rt_impedance_match.py` | "invisible when Z0 = circuit impedance" | exact terminated line H/H0 = 1/(cos θ + jκ sin θ) | **wrong as stated**: first order is a pure delay for any Z0; only ~1–170 Ω nets can be matched; I²R moves the optimum width 2.3×. Foundations T1 restated |
| `rt_world_cm.py` | I_CM = −jωΣC_ext·V; "cables on one edge buy ~40 dB" | lumped charge-conservation circuit with Z_A | identity holds only with world-referenced V (circuit V over-predicts by the factor abs(1 + jωC_tot·Z_A), up to 10–29 dB); the 40 dB was a **script input**; real benefit 6–30 dB (24–48 dB parallel) |
| `rt_loop_proxy.py` | MS2 picks the PEEC-best loop 96–98%; "+64% winner error" | 2-D graded-filament and 61-filament cosine-graded 3-D reference | 7-equal-filament PEECN reads 11–21% low at w/h 10–60 (to 65% at ≥ 30); +64% was a reference artefact (+2.9 → +6.5%); MS2 96.8% on mixed stackups vs area 17.3%. **Partly holds** |
| `rt_voi_sensitivity.py` | off-board unknowns carry 33–84% of VOI | re-run with alternative priors | 84% under its own prior, **10–49%** under others; post-build pre-scan EVSI ≈ 0 for its own board |
| `rt_jpr_stats.py` | joint place-and-route beats sequential | sign tests + bootstrap on the published table | 10/10 vs its own start (p = 0.002, −18%) but **5/10 vs equal-CPU portfolio** (p = 1.0, ratio 0.96, CI 0.83–1.24); physics-term effect 0.99. Downgraded to "a refiner" |
| `rt_fill_z0.py` | fill-gap Z0 shift (−3.7% vs −6.5% conflict) | 20 cells per h FD over three copper thicknesses | −5.0% at g = h (thin) to −8.4% (t = 0.35h); ≤ 2.2% at g ≥ 2h; both earlier scripts under-resolved; "harmless at ≥ 2h" holds |

Other checks without a new script: PEECN vs FastHenry within 1.3% only for 4 loops (w/h 0.3–5, 100 MHz); convex copper floors move 2.2–12.8% between 0.2 and 0.1 mm grids (and two grids used different areas); the wire-medium model matches lumped anti-resonance by identity (975 MHz); thermal length λ = 37.7 mm reproduces; rank-1 passport updates match brute force to 2×10⁻⁹ ("algebra, not physics"); `pw_cells ring` takes R from a fixed 2-square loop while L is free, so its Q values (31–173) belong to no single geometry; `fe_field2d` and `rg_fill_and_decaps` are under-resolved by 1.3–1.9 points.

**The 76 corrections in summary.** They are text replacements in the lens, foundations, solver and field docs, of four kinds: scope added to a claim that held (ℓ50 valid for ℓ ≥ 6h; band numbers only for a 50 mm plane; image results assume a perfect infinite plane; "transitions" move up to 10× with the observable), numbers replaced by converged ones (fill-gap Z0, damping dB, loop-proxy drift, VOI share), claims withdrawn as wrong (12 kHz mirroring, copper never damps, Z0-matching invisibility, 40 dB cable benefit) and results re-labelled as inputs (`same_edge_db`). Each page in this area carries the corrections that touch it.

## Verdict

The red team did its job: about a quarter of the load-bearing claims were wrong, overstated or circular, and the corrections are now in the docs. What it could not do is say whether any of it is true of a real board. Left: measured boards (none exist), a full-wave board-plus-cable run for the common-mode estimate, a converged reference at w/h ≥ 30 (+4–7% from 31 to 61 filaments), the pre-registered ≥ 20-board joint P&R experiment, and a regression suite that recomputes every [C] number.

## Code

`tools/research/physics/rt_*.py`. Print-only; run as `OMP_NUM_THREADS=1 python tools/research/physics/rt_X.py [section]` (instant to ~4 min; `rt_fill_z0` is the slowest). `rt_loop_proxy`, `rt_voi_sensitivity` and `rt_jpr_stats` import `sl_loop_peec`, `in_decision_quality`, `in_emi_voi` and a table hard-coded from [joint-place-route-experiment](../../topics/physics/joint-place-route-experiment.md).

## Related

[rule-genealogy](rule-genealogy.md), [first-principles-lenses](first-principles-lenses.md), [domain-models](domain-models.md), [physics-ir-and-core](physics-ir-and-core.md), [validation-program](validation-program.md).
