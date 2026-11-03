# Validating physics critics: calibration, planted faults and gaming guards

Scope: the three trust tests per critic (calibration, mutation, red team), calibration references and worked fits, the per-critic validation plan (reference, planted-fault operator, gaming guard), mutation scoring. Not here: critic definitions -> [physics-critics-catalog](physics-critics-catalog.md); benchmark protocol and prototype counts -> [physics-critics](physics-critics.md#5-the-drc-clean-but-physically-wrong-benchmark); coupons -> [validation-coupons](validation-coupons.md).
Keys: critic validation, calibration, mutation, red team, gaming routes, equivalent mutant, benign twin, metamorphic invariants, DRC-equivalent, Ott slot fit ΔV = a·ℓ·ln(ℓ/ℓ0), slot-line VOID proxy, Z_slot g/h, bridging-cap estimate, FastHenry, openEMS, padne, KiPI, emcvisual, V2, V3, V4, PC32, PC39

**Results:**
- A critic is trusted only after three tests: **calibration** (agrees with a higher-fidelity solver or measurement within a stated error inside a stated feature range), **mutation** (fires on planted DRC-clean faults at the site, quiet on benign edits), **red team** (no cheap edit improves its score without improving the physics). Gate each critic's reward use on all three and record the result with its version, like the judge licences in [V3](../../ideas/original/verification.md).
- Mutants need a physics label: swapping plane nets made some nets better and some worse on a real board, so detection is scored against an oracle delta; mutants below a significance threshold are *equivalent* and excluded.
- Most dangerous gaming routes: cosmetic copper (floating or badly stitched fills faking a reference), threshold cliffs (a via at 1.99 mm), role mislabelling. Guards: connectivity-qualified copper, continuous metrics, frozen human-confirmed role model.
- Prototype: 100% of physically real planted faults detected, no new findings on benign controls, on four open boards (counts: [physics-critics](physics-critics.md#6-prototype-results)); a method test, not a calibration.

## Calibration references (F3 and measurement)

| Reference | Use | Licence / note | Tag |
|---|---|---|---|
| FastHenry (partial-inductance PEEC) | loop L of hot loops, decap mounting, slot detours | internal calibration only, never shipped; ship our PEEC or PyPEEC ([open-solvers](open-solvers.md#licence-verdicts)) | [P] |
| openEMS via gerber2ems / si-wrapper slices | return-path discontinuities, via transitions, stubs, near field | GPLv3+ engine; si-wrapper VNA-validated on a DDR5 clock pair ([evaluation-stack](../verification/evaluation-stack.md)) | [P] |
| padne, KiPI, Ki-PIDA | IR drop, current density, PDN sweeps | KiPI GPL-3.0 alpha; padne via model uncertain except "large and short" vias | [P] |
| Elmer / CalculiX (Antmicro scripts) | ΔT; validated on an RPi5 enclosure at 2.5/8 W | open | [P] |
| Measured anchors in our docs | AN-139 loop L vs plane distance (13–187 nH table), SNVA803 (20 mm² lateral > 1 nH; 2 mm² vertical < 0.5 nH), EPC (0.4–2.9 nH), Axotron 0402 mounting (0.44–0.63 nH), Archambeault (0.9 → 3.2 nH from 10 → 100 mil depth), Ott slot voltages | fixed regression points ([hot-loops](../rules/power/hot-loops.md), [decoupling-pdn](../rules/decoupling-pdn.md), [si-fundamentals](../rules/si-fundamentals.md)) | [P] |
| Own coupons | 5–10 small boards with planted faults; VNA, near-field scan, thermal camera | only route to EMI ground truth; PC39 and the value-ranked panel in [validation-coupons](validation-coupons.md) | [I] |

**Worked fit 1: Ott slots [C].** Ott measured plane voltage across 1" under a trace crossing slots of ¼, ½, 1, 1.5" (+5, +11, +34, +60 mV over the 15 mV no-slot case). Linear-in-length misses 2–3×; ΔV = a·ℓ·ln(ℓ/ℓ0) fits all four within 1.4 mV with ℓ0 ≈ 0.09" (2.3 mm) ([pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py) §8). So VOID severity grows faster than slot length, and short voids still count: ℓ0 lies below Ott's shortest slot (6.35 mm), and PEEC gives 0.17–0.32 nH for 1–2 mm voids (other EM models up to 1.5× more, [validation-coupons](validation-coupons.md) §6); keep RET-COV severity for them until the short-void coupon is measured. Two parameters on four points: a shape check, not a validated model.

**Worked fit 2: slot-line VOID proxy [C].** pc_refplane.py's shorted-slot-line proxy (Z_slot = 100 Ω, two stubs in parallel, L = Z_s/v·ℓ/4 for a centred slot) vs the quasi-static PEEC plane solver ([fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py); trace width 2h, slot length 10–100h): proxy/PEEC = 0.97–1.18 for slot width g = 2h, 1.75–1.94 for g = 0.5h ([pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py) §11). Usable for wide voids, pessimistic (~1.8×) for narrow ones; a g/h-dependent Z_slot fixes most of the gap. The same run reproduces the lateral return spread 2/π·atan(x/h) within 0.02 at x = h, 3h, 10h, supporting RET-COV's w/2 + k·h margin.

## Per-critic validation plan

Operators are DRC-neutral by construction (a pour keep-out rule area only removes pour) or kept only if `kicad-cli pcb drc --refill-zones` gives the same per-type counts ("DRC-equivalent"). Fit each proxy's trust region from the calibration sweep ([V4](../../ideas/original/verification.md)); outside it escalate or mark "unverified". Run the red team ([V2](../../ideas/original/verification.md)), seeded with the gaming column, before any optimizer sees a new critic.

| ID | Calibrate against | Planted fault (operator) | Gaming route → guard |
|---|---|---|---|
| RET-COV | openEMS slice, ΔZ and S21 across the gap; Ott slot data | M-SLOT: pour keep-out strip across the reference under a net | floating fill patches under traces → count only fills connected to the reference net and stitched within d (PC32) |
| RET-HOP | FastHenry loop L, near vs far plane | M-SLOT on the near plane where a far plane exists | as RET-COV |
| RET-EDGE | MREMC L_ret offset formula; openEMS edge fringing | M-EDGE-SHIFT: move a run toward the board or plane edge | unstitched sliver pulls the plane edge out → stitching distance along plane edges |
| RET-VIA | openEMS via-transition slice; FastHenry | M-DEL-RETURN-VIA (stitching only, DRC holds); M-LAYER-SWAP | via touching only one plane (blind, isolated, thermal-relieved) → via must land on both reference fills |
| RET-REFNET | — (topological) | M-SWAP-REF: swap nets of two plane zones | rename nets → roles from the frozen role model, not names |
| RET-RPQF | FastHenry full-net loop L on 20 nets per board class | all RET operators | gains from short excursions → report per-net worst piece next to the ratio |
| PLANE-PERF | — (geometric); slot half-wave vs openEMS | M-TRACE-IN-PLANE: segment onto the plane layer with two vias | split the plane into two zones so neither passes the 30% test → planes declared in the IR stackup |
| SPLIT-X | openEMS split crossing with/without stitching cap | M-SPLIT: change a plane region's net | wrong-value or far stitching cap → check value and distance |
| CAVITY | openEMS plane-pair resonance; Palace eigenmodes | M-DEL-STITCH: delete stitching vias in a region | vias outside the overlap or not on both fills → count only qualifying vias |
| GND-ISLAND | openEMS island resonance | M-STITCH-ISLAND: delete an island's vias | hide islands below a size cut → no size cut; rank by resonance |
| XTALK | 2-D field solve of the coupled section; openEMS for broadside | M-PARALLEL: victim next to an aggressor | jog 6° to escape a ≤ 5° parallel test → angle-weighted projected coupled length, no hard cut |
| VIA-STUB | openEMS via model; backdrill data | M-STUB: blind → through via | mislabel data rate → t_r from IBIS or role model, frozen |
| IMP-DISC | 2-D solver Z0 per piece; TDR on coupons | M-NECK-SIG: neck a controlled-impedance run | many sub-threshold pieces → cumulative Γ along the net |
| DIFF-BAL | openEMS Scd21 on a slice | M-SKEW: lengthen one leg | compensate skew far from the cause → feature-local imbalance as well as total skew |
| TOPO | SPICE on an extracted tree | M-STUB-TRACE: add a branch | — |
| HOTLOOP-L | FastHenry on realized copper; AN-139, SNVA803, EPC anchors | M-HOTLOOP-STRETCH: move CIN_HF farther (place task); return through the far plane | members close but return detours → L from the realized current path, not pad centroids |
| DECAP-L | FastHenry; Axotron and Archambeault tables | M-DECAP-FAR: cap's GND via d mm away on a stub | extra caps to dilute → per-pin L, not per-rail count |
| PDN-Z | plane-pair solver; vendor PDN tools on EVMs | M-DECAP-FAR, M-DEL-STITCH | caps "near" with long vias → uses DECAP-L |
| IR-DROP | padne/KiPI; FEM; four-wire on coupons | M-NECK: pour keep-out necking a power pour | wide copper not carrying the current → solve the actual source-to-sink field |
| J-MAX | as IR-DROP; thermal camera | M-NECK; M-VIAFIELD: other-net via field across a pour | sliver copper lowering average J → report max J, not mean |
| VIA-AMP | FEM; via-array measurements | M-DEL-VIA in an array | — |
| PWR-TRACE | DC R and L from FastHenry | M-GND-TRACE: pour connection → 0.2 mm trace | widen to 0.41 mm to clear a width cut → judge R and L against the rail budget |
| SW-AREA | capacitance by 2-D solve | M-SW-GROW: enlarge SW copper | — |
| SENSE-M | FastHenry mutual L | M-SENSE-PARALLEL: FB next to SW | sense on another layer over a slot → include plane images and slots |
| KELVIN | IR-DROP potentials | M-KELVIN-MOVE: tap along the shunt path | — |
| CM-V | emcvisual (claims within 1 dB of openEMS 30–350 MHz [V]); coupon pre-scan | M-EDGE-SHIFT; M-CONNECTOR-SPLIT (place task) | mark a cable connector "internal" → role model frozen, human-confirmed |
| IO-COUPLE | 2-D solve; pre-scan | M-IO-PARALLEL | — |
| FILTER-POS | SPICE of the protection path; IEC 61000-4-2 on coupons | M-ESD-SWAP: swap TVS and series element order | — |
| LOOP-RAD | Ott formula vs openEMS far field | all loop operators | ranking only; never a pass gate |
| ANT-KEEP | module datasheet keep-out | M-ANT-INTRUDE: GND pour into the keep-out | — |
| SPECTRUM | openEMS resonances | M-DEL-STITCH (moves a resonance into the spectrum) | — |
| THERM-DT | Elmer/CalculiX; thermal camera | M-THERMAL-RELIEF: solid → two-spoke relief on a power pad | isolated islands looking like heatsinks → connectivity-based network |
| THERM-COUPLE | same | M-HOT-NEIGHBOUR: regulator next to the crystal (place task) | — |
| THERM-VIA | FEM; vendor θ data | M-DEL-VIA under an EP | — |
| HV-FIELD | 2-D electrostatics (FEniCS/Elmer) at corners | M-HV-CORNER: sharp corner at minimum clearance | — |
| CREEPAGE | hand cases from IEC 60664-1 examples | M-SLOT-NARROW: slot below the PD minimum width | narrow slots counted as barriers → width check |
| COPPER-BAL, TOMBSTONE, VIA-AR | fab and assembler data | M-POUR-ONE-SIDE; M-PAD-ASYM | — |

## Mutation scoring

- **Detection** = a marker of the critic's type within r = 2.5 mm of the planted site and a rise in its budget utilization (a marker anywhere would reward critics that fire everywhere).
- **Physics label:** oracle delta per mutant (F1 for all, F2/F3 on a sample). |delta| below the budget's resolution → **equivalent**, out of the denominator. In the prototype a deleted return via was equivalent whenever another wired GND via stayed within 2 mm.
- **Direction:** some edits improve one net and degrade another (M-SWAP-REF on a GND/3.3 V board moves the top layer's reference to GND, the bottom's to 3.3 V); score per net with signs.
- **Controls (benign twins):** a slot far from any budgeted net, an extra GND via, a 0.05 mm via nudge, a collinear segment split, a rotation of the whole board. False alarm = new finding on a control.
- **Metamorphic invariants:** results unchanged under translation, rotation, mirroring, segment splitting, net renaming; score continuous under ±0.05 mm nudges. Discontinuities are bugs and gaming cliffs.

## Open questions

- Ott's slot data are one geometry at one frequency; the PEEC comparison is quasi-static (no slot resonance); the slot-line VOID proxy is checked only against PEEC, not full-wave or measurement.
- Bridging-cap estimate 1.2–3 nH [C] vs Ott's 5–10 nH: the cap's own ESL and via loop are probably under-counted; calibrate with FastHenry before use.
- No open EMI ground truth for KiCad boards; coupons with pre-scan data are the only way to calibrate CM-V and LOOP-RAD ([validation-coupons](validation-coupons.md) ranks them by decision value).

## Sources

- Ott, slots: https://hott.shielddigitaldesign.com/techtips/tips-slots.html [P]; layer changes: https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html [P]
- Just et al., "Are mutants a valid substitute for real faults in software testing?", FSE 2014: 73% of 357 real faults coupled to mutants; the rest lacked suitable operators. https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf [S]
- Research notes: [constraints_verification_benchmarks.md § Q2, Q6B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md).
- Related: [ideas: verification](../../ideas/original/verification.md).
