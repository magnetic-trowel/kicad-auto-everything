# Physics research

The physics-first line asked what a layout tool should optimise if it reasoned from the physics behind design rules instead of the rules themselves. Over about a day of focused work (2026-10-22, branch `claude/vigilant-mayer-i91rrr`) it produced a rule genealogy, seven first-principles "lenses", domain solvers, a representation design, real-board critics and passports, a red team, and a validation plan.

**Read this first: all of it is model against model.** The numbers come from closed forms, small field solvers and PEEC models checked against each other, against independent re-derivations, against published vendor/literature anchors, and against FastHenry on four loops (within 1.3%). **No physics-first number has been checked against a measurement of a real board.** The [red team](redteam-corrections.md) corrected about a quarter of the load-bearing claims; each page carries the corrections that touch it.

What reached the tools: `kae`'s fast place terms and exact PEEC/thermal check (`kae/src/kae/physics/`), the circuit comprehension brief, and the routed-copper physics used by the critical-copper router. Those are covered in the [placement](../placement/README.md) and [routing](../routing/README.md) areas.

| Path | Status | One-line result | Page | Code |
|---|---|---|---|---|
| Rule genealogy, derivation audit, foundations | partial | 160 rules → 12 physics quantities; 132/160 derive from 7 principles + damage, but only 12 of 67 quoted numbers do | [rule-genealogy](rule-genealogy.md) | `tools/research/physics/{rg,da,fd}_*.py` |
| Red team | worked | 9 independent re-derivations, 76 corrections; several headline claims wrong or overstated | [redteam-corrections](redteam-corrections.md) | `tools/research/physics/rt_*.py` |
| Vocabulary, IR, solver ladder, physics core v2 | not finished | schemas, validator and core skeleton; exact edit algebra holds to 1e-11; MS2 picks the best loop 96–98% but plain length 82–99% at fixed stackup | [physics-ir-and-core](physics-ir-and-core.md) | `tools/research/physics/{vo,sl}_*.py`, `pc2_core_skeleton.py` |
| Domain models (power, SI/EMI/RF, thermal/HV/mfg, reasoning, optimizer, cross-domain) | partial | rule overturns hold within the models; honest magnitudes modest (pour synthesis −14.5%, about fab tolerance) | [domain-models](domain-models.md) | `tools/research/physics/{pw,fe,tm,dr,op,xd}_*.py` |
| First-principles lenses VP, CT, SY, LS, TH, IN, CD | partial | exact floors, cut prices and passports for self terms; plain adjoints miss slots by ~30× | [first-principles-lenses](first-principles-lenses.md) | `tools/research/physics/{vp,ct,sy,ls,th,in,cd}_*.py` |
| Physics critics and conductor passports | partial | ran on all 112 suite boards in 15 min; one via carries a whole rail on 102/335 rails; Freerouting doubles worst rail drop (median ×1.9); uncalibrated | [physics-critics-and-passports](physics-critics-and-passports.md) | `pc_refplane.py`, `rb_board_passports.py`, `suite_passports.py`, `crit_compare.py` |
| Validation program | untested idea | VOI-ranked coupons and a two-arm board with pre-registered predictions; nothing fabricated | [validation-program](validation-program.md) | `tools/research/physics/val_*.py` |
| Exact physics in the placer before routing | see page | changed few decisions before copper exists | [kae-exact-physics-before-routing](../placement/kae-exact-physics-before-routing.md) | `kae/src/kae/physics/exact.py`, `tools/research/physics/ex_*.py` |
| Joint place-and-route theory and synthetic test | see page | joint search refines but ties an equal-CPU restart portfolio (5/10) | [kae-joint-loop](../joint/kae-joint-loop.md) | `tools/research/physics/jpr_*.py`, `rt_jpr_stats.py` |

Depth: the imported topic docs in [docs/topics/physics](../../topics/physics/README.md), the [physics-first digest](../../digests/physics-first.md), the [executive report](../../../reports/Physics-first%20PCB%20layout.md) and about 890 catalogued ideas in [docs/ideas/physics-first](../../ideas/physics-first/README.md).

Related areas: [routing](../routing/README.md), [placement](../placement/README.md), [joint](../joint/README.md).
