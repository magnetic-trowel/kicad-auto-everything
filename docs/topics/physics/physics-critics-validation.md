# Validating physics critics: calibration, planted faults and gaming guards

**TL;DR**
- A critic is trusted only after three tests: **calibration** (its number agrees with a higher-fidelity solver or a measurement within a stated error, inside a stated feature range), **mutation** (it fires on planted DRC-clean faults at the planted site and stays quiet on benign edits), and **red-team** (no cheap edit improves its score without improving the physics).
- Mutants need a physics label, not just "mutated". Swapping plane nets made some nets better and some worse on a real board, so detection is scored against an oracle's delta, and mutants below a significance threshold count as *equivalent* and are excluded.
- The most dangerous gaming routes are cosmetic copper (floating or badly stitched fills that fake a reference), threshold cliffs (a via at 1.99 mm), and role mislabelling. The guards are connectivity-qualified copper, continuous metrics and a frozen, human-confirmed role model.
- On four open boards the prototype detected 100% of physically real planted faults in this run and raised no new findings on benign controls (counts in [physics-critics.md](physics-critics.md)). This is a test of the method, not a calibration.

## Key facts

### Calibration references (F3 and measurement)

| Reference | Use | Licence / note | Tag |
|---|---|---|---|
| FastHenry (partial-inductance PEEC) | Loop L of hot loops, decap mounting, slot detours | Source carries an MIT "internal, noncommercial … distribution strictly prohibited" notice: internal calibration only, never shipped; ship our PEEC or PyPEEC ([open-solvers](open-solvers.md)) | [P] |
| openEMS via gerber2ems / si-wrapper slices | Return-path discontinuities, via transitions, stubs, near field | GPLv3+ engine; si-wrapper VNA-validated on a DDR5 clock pair ([evaluation-stack](../verification/evaluation-stack.md)) | [P] |
| padne, KiPI, Ki-PIDA | IR drop, current density, PDN sweeps | KiPI GPL-3.0 alpha; padne via model uncertain except "large and short" vias | [P] |
| Elmer / CalculiX (Antmicro scripts) | ΔT; validated on an RPi5 enclosure at 2.5/8 W | Open | [P] |
| Measured anchors in our docs | AN-139 loop L vs plane distance (13–187 nH table), SNVA803 (20 mm² lateral >1 nH; 2 mm² vertical <0.5 nH), EPC (0.4–2.9 nH), Axotron 0402 mounting (0.44–0.63 nH), Archambeault (0.9→3.2 nH from 10→100 mil depth), Ott slot voltages | Use as fixed regression points ([hot-loops](../rules/power/hot-loops.md), [decoupling-pdn](../rules/decoupling-pdn.md), [si-fundamentals](../rules/si-fundamentals.md)) | [P] |
| Own coupons | 5–10 small boards with planted faults; VNA, near-field probe scan, thermal camera | The only route to EMI ground truth; see idea PC39 | [I] |

**Worked calibration example [C].** Ott measured plane voltage across 1" under a trace crossing slots of ¼, ½, 1 and 1.5" (+5, +11, +34, +60 mV over the 15 mV no-slot case). A linear-in-length model misses by 2–3× across that range. ΔV = a·ℓ·ln(ℓ/ℓ0) fits all four points within 1.4 mV with ℓ0 ≈ 0.09" (2.3 mm) ([pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py) §8). Two conclusions follow. Slots shorter than about 2 mm hardly matter, which matches Ott's "15 separate holes = no slot". And the VOID severity should grow faster than slot length. Two fitted parameters on four points is a shape check, not a validated model.

**Worked calibration example 2 [C].** The shorted-slot-line VOID proxy in pc_refplane.py (Z_slot = 100 Ω, two stubs in parallel, so L = Z_s/v·ℓ/4 for a centred slot) was compared with workstream 5's quasi-static PEEC plane solver ([fe_peec_plane.py](../../../tools/research/physics/fe_peec_plane.py); trace width 2h, slot length 10–100h). The proxy/PEEC ratio is 0.97–1.18 for slot width g = 2h and 1.75–1.94 for g = 0.5h ([pc_budget_calcs.py](../../../tools/research/physics/pc_budget_calcs.py) §11). So the proxy is usable for wide voids and pessimistic for narrow ones; a g/h-dependent Z_slot fixes most of the gap. The same PEEC run reproduces the lateral return-current spread 2/π·atan(x/h) within 0.02 at x = h, 3h and 10h, which supports RET-COV's w/2 + k·h margin.

### Per-critic validation plan

Mutation operators are DRC-neutral by construction (a pour keep-out rule area only removes pour) or are kept only if `kicad-cli pcb drc --refill-zones` gives the same per-type counts as the original ("DRC-equivalent").

| ID | Calibrate against | Planted fault (operator) | Gaming route → guard |
|---|---|---|---|
| RET-COV | openEMS slice, ΔZ and S21 across the gap; Ott slot data | M-SLOT: pour keep-out strip across the reference under a net | Floating fill patches under traces → count only fills connected to the reference net and stitched within d (PC32) |
| RET-HOP | FastHenry loop L, near vs far plane | M-SLOT on the near plane where a far plane exists | Same as RET-COV |
| RET-EDGE | MREMC L_ret offset formula; openEMS edge fringing | M-EDGE-SHIFT: move a run toward the board or plane edge | Pull the plane edge out with an unstitched sliver → stitching distance along plane edges |
| RET-VIA | openEMS via-transition slice; FastHenry | M-DEL-RETURN-VIA (stitching only, so DRC holds); M-LAYER-SWAP | A via that touches only one plane (blind, isolated or thermal-relieved) → the via must land on both reference fills |
| RET-REFNET | — (topological) | M-SWAP-REF: swap the nets of two plane zones | Rename nets → roles come from the frozen role model, not names |
| RET-RPQF | FastHenry full-net loop L on 20 nets per board class | All RET operators | Gains from short excursions → report per-net worst piece next to the ratio |
| PLANE-PERF | — (geometric); slot half-wave vs openEMS | M-TRACE-IN-PLANE: move a segment onto the plane layer with two vias | Split the plane into two zones so neither passes the 30% plane test → planes are declared in the IR stackup, not inferred from fill share |
| SPLIT-X | openEMS split crossing with and without a stitching cap | M-SPLIT: change a plane region's net | Stitching cap of the wrong value or far away → check value and distance |
| CAVITY | openEMS plane-pair resonance; Palace eigenmodes | M-DEL-STITCH: delete stitching vias in a region | Vias outside the overlap or not landing on both fills → count only qualifying vias |
| GND-ISLAND | openEMS island resonance | M-STITCH-ISLAND: delete the vias of a pour island | Hide islands below a size cut → no size cut; rank by resonance instead |
| XTALK | 2-D field solve of the coupled section; openEMS for broadside | M-PARALLEL: move a victim run next to an aggressor | Jog by 6° to escape a ≤5° parallel test → angle-weighted projected coupled length, no hard cut |
| VIA-STUB | openEMS via model; backdrill data | M-STUB: blind via → through via | Mislabel the data rate → t_r from IBIS or role model, frozen |
| IMP-DISC | 2-D solver Z0 per piece; TDR on coupons | M-NECK-SIG: neck a controlled-impedance run | Many sub-threshold pieces → cumulative Γ along the net |
| DIFF-BAL | openEMS Scd21 on a slice | M-SKEW: lengthen one leg | Compensate skew far from the cause → feature-local imbalance as well as total skew |
| TOPO | SPICE on an extracted tree | M-STUB-TRACE: add a branch | — |
| HOTLOOP-L | FastHenry on the realized copper; AN-139, SNVA803, EPC anchors | M-HOTLOOP-STRETCH: move CIN_HF farther (place task); return through the far plane | Members close but return through a detour → L from the realized current path, not pad centroids |
| DECAP-L | FastHenry; Axotron and Archambeault tables | M-DECAP-FAR: move a cap's GND via d mm away on a stub track | Extra caps to dilute → per-pin L, not per-rail count |
| PDN-Z | Plane-pair solver; vendor PDN tools on EVMs | M-DECAP-FAR, M-DEL-STITCH | Caps placed "near" with long vias → uses DECAP-L |
| IR-DROP | padne/KiPI; FEM; four-wire measurement on coupons | M-NECK: pour keep-out necking a power pour | Wide copper that does not carry the current → solve the actual source-to-sink field |
| J-MAX | Same as IR-DROP; thermal camera | M-NECK; M-VIAFIELD: other-net via field across a pour | Sliver copper that lowers average J → report max J, not mean |
| VIA-AMP | FEM; via-array measurements | M-DEL-VIA in an array | — |
| PWR-TRACE | DC R and L from FastHenry | M-GND-TRACE: replace a pour connection with a 0.2 mm trace | Widen to 0.41 mm to clear a width cut → judge R and L against the rail's budget |
| SW-AREA | Capacitance by 2-D solve | M-SW-GROW: enlarge SW copper | — |
| SENSE-M | FastHenry mutual inductance | M-SENSE-PARALLEL: run FB next to SW | Route sense on another layer over a slot → include plane images and slots |
| KELVIN | IR-DROP potentials | M-KELVIN-MOVE: move the tap along the shunt path | — |
| CM-V | emcvisual (claims within 1 dB of openEMS from 30–350 MHz [V]); pre-scan of coupons | M-EDGE-SHIFT; M-CONNECTOR-SPLIT (place task) | Mark a cable connector "internal" → role model frozen and human-confirmed |
| IO-COUPLE | 2-D solve; pre-scan | M-IO-PARALLEL | — |
| FILTER-POS | SPICE of the protection path; IEC 61000-4-2 on coupons | M-ESD-SWAP: swap the TVS and series element order | — |
| LOOP-RAD | Ott formula vs openEMS far field | All loop operators | Ranking only; never a pass gate |
| ANT-KEEP | Module datasheet keep-out | M-ANT-INTRUDE: add GND pour into the keep-out | — |
| SPECTRUM | openEMS resonances | M-DEL-STITCH (moves a resonance into the spectrum) | — |
| THERM-DT | Elmer/CalculiX; thermal camera | M-THERMAL-RELIEF: solid → two-spoke relief on a power pad | Isolated copper islands that look like heatsinks → connectivity-based network |
| THERM-COUPLE | Same | M-HOT-NEIGHBOUR: move a regulator next to the crystal (place task) | — |
| THERM-VIA | FEM; vendor θ data | M-DEL-VIA under an EP | — |
| HV-FIELD | 2-D electrostatics (FEniCS/Elmer) at corners | M-HV-CORNER: sharp copper corner at minimum clearance | — |
| CREEPAGE | Hand cases from IEC 60664-1 examples | M-SLOT-NARROW: slot below the PD minimum width | Narrow slots counted as barriers → width check |
| COPPER-BAL, TOMBSTONE, VIA-AR | Fab and assembler data | M-POUR-ONE-SIDE; M-PAD-ASYM | — |

### Mutation scoring

- **Detection** = the critic emits a marker of its type within r (2.5 mm) of the planted site and its budget utilization rises. Counting a marker anywhere would reward critics that fire everywhere.
- **Physics label.** Each mutant gets a delta from an oracle (F1 formula for all, F2/F3 on a sampled subset). If |delta| is below the budget's resolution, the mutant is **equivalent** and leaves the denominator. In the prototype a deleted return via was equivalent whenever another wired GND via stayed within 2 mm.
- **Direction.** Some edits improve one net and degrade another (M-SWAP-REF on a GND/3.3 V board moves the top layer's reference to GND and the bottom layer's to 3.3 V). Score per net, with signs.
- **Controls.** For each operator, apply a benign twin: a slot far from any budgeted net, an extra GND via, a 0.05 mm via nudge, a collinear segment split, a rotation of the whole board. False alarm = a new finding on a control.
- **Metamorphic invariants.** Results must not change under translation, rotation, mirroring, segment splitting or renaming nets. Score must change continuously under ±0.05 mm nudges. Discontinuities are both bugs and gaming cliffs.

## Recommendations for our system

- Gate each critic's use in rewards on all three tests, and record the result next to its version, like the judge licences in [V3](../../ideas/original/verification.md).
- Fit each proxy's trust region from the calibration sweep ([V4](../../ideas/original/verification.md)). Outside it, escalate fidelity or mark the result "unverified".
- Run the red team against each new critic before any optimizer sees it ([V2](../../ideas/original/verification.md)), seeded with the gaming column above.

## Conflicts and open questions

- Ott's slot data are one geometry at one frequency, and the PEEC comparison is quasi-static (no slot resonance). The slot-line VOID proxy is checked only against PEEC, not against full-wave or measurement.
- The bridging-cap estimate (1.2–3 nH [C]) is well below Ott's 5–10 nH; the cap's own ESL and via loop are probably under-counted. Calibrate with FastHenry before use.
- No open EMI ground truth exists for KiCad boards. Coupons with pre-scan data are the only way to calibrate CM-V and LOOP-RAD.

## Sources

- Ott, slots: https://hott.shielddigitaldesign.com/techtips/tips-slots.html [P]; layer changes: https://hott.shielddigitaldesign.com/techtips/pcb-stack-up-6.html [P]
- Just et al., "Are mutants a valid substitute for real faults in software testing?", FSE 2014: 73% of 357 real faults coupled to mutants; the rest lacked suitable operators. https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf [S]
- research notes: [constraints_verification_benchmarks.md § Q2, Q6B](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/constraints_verification_benchmarks.md)

See also: [physics-critics.md](physics-critics.md), [physics-critics-catalog.md](physics-critics-catalog.md), [../verification/evaluation-stack.md](../verification/evaluation-stack.md), [../../ideas/original/verification.md](../../ideas/original/verification.md)
