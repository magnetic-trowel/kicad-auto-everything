# Rule genealogy: routing style, geometry, vias, pours, DFM, placement method

**TL;DR**
- Routing *style* (45°, Manhattan layer bias, few turns, teardrops, thermal reliefs, acute-angle bans) is mostly **manufacturing legacy, tool limitation and human cognition**, not circuit physics. Octilinear routing costs only 5.5% mean path length over any-angle; Manhattan costs 27% [C]. Keep 45° for editability, not for physics.
- Corner shape barely matters for DC either: a sharp 90° bend counts as **0.56 squares** of resistance, a rounded one 0.50, an inner fillet 0.24 [C]. The only real corner effects are RF on thick substrates, local current crowding at the inner corner (pulse/fusing) and possibly kV ESD.
- "Short", "wide", "no vias" and "keep away" are **overloaded proxies**: each stands for 2–5 basis quantities at once. "Wide" lowers inductance only when a return plane is close (L ∝ h/w); off-plane a 16× wider strip lowers L by only ~48% [C].
- Pour and fill rules change sign with layer count: on 2-layer boards a stitched pour *is* the return plane; on multilayer boards same-layer fill is harmless beyond ~2h and pointless or harmful closer [C].
- Placement methodology rules (template first, critical first, freeze) are cognition and sequential-tool workarounds that happen to order the work by **budget dominance**. A physics-first system can derive the order from budget sensitivity instead.

Legend as in [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md). [C] sections refer to [rg_proxies.py](../../../tools/research/physics/rg_proxies.py), [rg_corners.py](../../../tools/research/physics/rg_corners.py) and [rg_fill_and_decaps.py](../../../tools/research/physics/rg_fill_and_decaps.py).

## Key facts

### Geometry and routing style ([what-good-looks-like](../workflow/what-good-looks-like.md), [myths-and-contested](../rules/myths-and-contested.md))

| ID | Rule | Orig | Physics (basis: equation; binds when) | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| R01 | No 90° corners | Hb (MECL 1971) + Mf (etch era) | **Z**: corner −20 dB at ~3/h GHz·mm; **R**: corner = 0.56 □ [C corners] | X for digital below ~10 GHz on thin dielectrics; see S46 for RF | corner Γ only for RF/≥10 Gb/s classes [CF] |
| R02 | Route at 45° everywhere | Tl+Cg+Mf | **Cog**: path +5.5% mean, +8.2% max vs any-angle [C §O] | R as convention; physics-neutral | style channel [GE] |
| R03 | Curves / any-angle routing | Cg cost | **Cog**: ≤8% shorter than 45°; no L or Z benefit at board scale | M: real benefit for RF bends, flex strain, HV edges; costs editability | allow per net class (RF, flex, HV) [GE] |
| R04 | No acute angles (acid traps) | Mf legacy | **Fab**: etch pockets with immersion etchants; modern spray etch mostly fixed [S] | C except <0.1 mm features and flex | fab DFM pocket check [GE] |
| R05 | Short and direct | Sp | **L**, **R**, **Z** (delay, loss), **M**, **Cm** all scale with length | M: A when "short" leaves the plane or crosses a slot ("longer over plane beats short off-plane") | evaluate each quantity [mixed] |
| R06 | Minimise vias | Sp | via **L** 0.1–1.3 nH [C §D], stub **Res**, plane perforation, **Fab** cost | M: vias *help* decap mounting, thermal and current paths | per-via budgets per class [CF/FW] |
| R07 | Constant width, no necking | Ph+Mf | **Z** step Γ=(Z2−Z1)/(Z2+Z1); neck shorter than ~t_r/6 is invisible | C at low speed; R for RF | Γ·(neck delay/t_r) [CF] |
| R08 | Width by net class (signal 0.15–0.25 mm, power wider) | Sp+Cg | **Z** for controlled nets; **R**/**Th** for current | M | width from Z0 target or I/IR budget [CF] |
| R09 | Wide = low inductance | Sp | **L**: off-plane strip 20 mm: 21.8→11.4 nH for 0.25→4 mm; over plane L′ ∝ h/w for w ≫ h [C §B] | M: A off-plane, R over a close plane | L estimate [CF] |
| R10 | Route over the plane even if longer | Ph | **L** ∝ h | R | [CF] |
| R11 | Layer direction bias (H/V per layer, Manhattan) | Tl (router channels) + Ph | broadside **M**/**Cm** only between adjacent signal layers without a plane between | R for routability; physics only for S19 | overlap-length coupling check [2D] |
| R12 | Neat parallel bus routing | Cg | **M**/**Cm** grow with parallel length (Olney) | A | coupled-length budget [CF] |
| R13 | Length-tune with serpentines | Ph | **Z**, **M**: delay match vs self-coupling and loss | R when timing-limited | see S25 [2D/SP] |
| R14 | Keep traces off board edge (≥2h) and copper ≥0.2 mm from routed edge | Ph+Mf | edge fringing → **Vcm**; routing tolerance ±0.2 mm | R | k·h + fab tolerance [2D/LU] |

### Vias and fan-out ([dfm-fab-limits](../rules/dfm-fab-limits.md), [placement-methodology](../rules/placement-methodology.md))

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| R15 | No vias in hot loop / RF line / ESD path / crystal lines | Ph | **L** (hot loop, ESD), **Z** (RF), **Cm** (crystal) | R; one slogan, four quantities | per-class budget (nH, Γ, fF) [CF/PEEC] |
| R16 | One via per power pad, never shared (Feranec) | Ph | **L**/**M**: shared via carries two pins' current | R for BGA power | per-pin nH [PEEC] |
| R17 | Dog-bone ≥0.8 mm pitch; via-in-pad below | Mf+Ph | **Fab** escape geometry; **L** lower with VIP | R | [GE] |
| R18 | Teardrops | Mf+Ph | **Fab**, **Mech**: drill breakout margin at trace junction; stress at neck (flex, cycling) | C on rigid boards with ≥0.15 mm traces and normal rings; R for HDI and flex | breakout probability from drill σ and ring [GE] |
| R19 | Annular ring ≥ fab minimum | Mf | **Fab**: drill position tolerance | R | [LU] |
| R20 | Via aspect ratio ≤10 (or 8) | Mf | plating throw → barrel thickness (**Th**, **R**, reliability) | R | [LU] |
| R21 | Tent/plug policy; no open via in pad | Mf | **Fab**: solder wicking, voids | R | [LU] |
| R22 | Merged antipads form slots | Ph | **L** detour (Ott: separate holes ≈ no slot) | R | void-polygon slot length [GE] |
| R23 | Remove non-functional pads | Ph+Mf | **Z**/**Res**: pad capacitance on stubs; also drill wear | R ≥ ~5 Gb/s | [FW/LU] |
| R24 | KiCad stitching default max(2 mm, 2× via) | Tl | **Res** | C for most boards | λ-based pitch [CF] |

### Pours, planes and reliefs

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| R25 | Thermal reliefs on plane connections | Mf (hand/wave soldering) | **Th** 4 spokes 0.25×0.5 mm ≈37 K/W; adds ~50–90 pH and 0.25 mΩ [C §I]. In reflow a pad couples ~0.1 mW/K to the oven vs 27–54 mW/K through spokes, so it follows the plane either way (Wiedemann–Franz: decoupling it would cost ≥ 66 mΩ) [C da §A] | M: needed for hand/wave/TH; no physical basis in reflow, which contradicts vendor 0201/0402 balance guidance and needs an assembly test; harmful on sub-nH loops and >~3 A pads | per-pad process heat balance vs ΔL, ΔR [TN] |
| R26 | Direct-connect thermal and power pads | Ph | **Th**, **R**, **L** | R | same check [TN] |
| R27 | Pour all unused copper (2-layer) | Ph | **L**: the pour becomes the return plane if stitched | R on 2-layer when stitched and continuous | return-path map [2D] |
| R28 | Ground fill on multilayer | Hb | **Z** −0.9% at 2h; floating islands **Res** | X as default | s/h ≥ 2 and stitched islands [2D/CF] |
| R29 | No floating or isolated copper | Ph+Mf | **Res**, **Cm** re-radiation; copper balance | R | island detect + stitch or delete [GE] |
| R30 | Hatched vs solid planes | Hb+Mech | **Z** if hatch pitch ≳ h; flex stiffness | M: hatched for flex; solid for rigid | hatch pitch vs h [2D] |
| R31 | Copper balance, thieving | Mf | plating uniformity, warp (**Mech**) | R | density map [GE] |
| R32 | Plane necks; length:width ≤3:1 | Ph | **L**, **R** constriction | R | current solve [2D/PEEC] |
| R33 | Pour clearance > track clearance; no slivers or <45° pour angles | Mf | **Fab**: slivers lift; etch | R | [GE] |
| R34 | Big pours for power ("closer to a pour than a trace") | Ph | **R** ∝ 1/w; **L** ∝ h/w only with a close return; **Th** within fin length | R for quiet nets; A on switching nodes (**Cm**) | pour-shape objective R+ωL+Th s.t. Cm caps [2D/PEEC/TN] |
| R35 | Round inside corners of power pours | Ph | **R**: rounding saves ≤0.07–0.3 □ per corner; removes crowding peak (~3× at sharp inner corner, singular) [C corners] | M: negligible for steady current; R for pulse/fusing hot spots | sheet-current solve [2D] |

### DFM, assembly and placement method

| ID | Rule | Orig | Physics | Verdict | Replacement [cost] |
|---|---|---|---|---|---|
| R36 | DRC at fab absolute; router at recommended + margin | Mf | **Fab** yield vs margin | R | yield-aware margin [LU] |
| R37 | Courtyard 0.25 mm (IPC-7351 B) | Mf | **Fab**: placement tolerance, rework | R (often turned off) | [LU] |
| R38 | Symmetric pad copper on 0201/0402 (tombstones) | Mf+Ph | **Th**: pad heat-up mismatch → wetting-time difference → surface-tension torque | R | pad thermal-mass ratio [TN] |
| R39 | MLCCs 3–5 mm from V-score, parallel to edge | Ph+Mf | **Mech**: depanel flex strain cracks MLCCs | R | strain map [FEM/CF] |
| R40 | Polarized parts one orientation, 0/90° | Cg+Mf | **Cog**: none (inspection, placement error) | R as style | style channel [GE] |
| R41 | Single-sided SMT if it fits | Mf | **Fab**: cost | R | [LU] |
| R42 | Fiducials; test points 1 mm from parts | Mf | **Fab** | R | [GE] |
| R43 | Placement order mechanical → anchors → templates → decaps → flow; route critical first and freeze | Cg+Tl | **Cog**: orders work by budget dominance; sequential tools cannot co-optimise | R given sequential tools | order by budget sensitivity (RG37) [—] |
| R44 | Schematic-flow placement, readability | Cg | **Cog**: correlates with short nets | neutral | style channel [—] |
| R45 | Mounting-hole keep-outs; no high speed near holes | Ph+Mf | screw head clearance; chassis currents (**Vcm**) | R | [GE] |
| R46 | Generic "keep sensitive nets ≥1–3 mm from Y" (magnetics, SW, clocks, heat) | Sp | **M**, **Cm**, **Th**, **Ins**: coupling falls as 1/(1+(d/h)²) for traces over a plane, ~1/d³ for a magnetic dipole, slowly for heat | M: C near quiet parts, A near large open-flux magnetics or 2-layer boards | distance solved from M(d), Cm(d), ΔT(d) curves and the victim budget (RG53) [CF/PEEC] |

## Recommendations for our system
- Split every layout score into three channels as [what-good-looks-like](../workflow/what-good-looks-like.md) proposes: physics (gates), manufacturing (yield margin), style (Cg/Tl conventions). R02, R11, R40, R44 go to style and never block physics.
- Allow non-45° geometry only for classes where physics or mechanics pays: RF bends (Douville–James miter), flex bends, HV edges, and power pours with pulse current. Everywhere else keep 45° for editability.
- Decide reliefs per pad from the declared assembly process and the pad's loop budget (RG28), not globally.
- Decide fill per layer count: 2-layer → stitched return pour mandatory; multilayer → fill only if s ≥ 2h and every island is stitched below λ/10 at f_max (RG20).
- Never let the LLM emit "short", "wide", "close", "no vias" or "keep away" without the quantity it means (RG10).

## Conflicts and open questions
- **R05 vs R10/R13:** short vs over-plane vs length-matched; each optimises a different quantity (L vs Z-delay).
- **R25 vs R26:** solderability (Fab/Th of the joint) vs loop L and IR; the selector is the assembly process plus the loop budget.
- **R34:** a big pour lowers R, L and Th on quiet nets, but raises Cm on switching nodes (P07). Pour shape is a multi-objective problem, not a style choice; see [power-copper](power-copper.md) and [copper-shape-synthesis](copper-shape-synthesis.md).
- **Unverified:** teardrop and acid-trap evidence is vendor/forum level [S]; no controlled study of reliefs in reflow was found. The DC bend numbers are 2-D sheet solutions (no thickness or skin effect); the classic 0.559-square corner value matches our 0.562.

## Sources
- research notes: [expert_workflow_and_checklists.md § Q1, Q6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/expert_workflow_and_checklists.md); [practitioner_discussions.md § Q3–Q5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/practitioner_discussions.md); [rules_power_rf_analog_dfm.md § 6, 7](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
- Checklist items: [checklist-full-thermal-routing-assembly-test](../verification/checklist-full-thermal-routing-assembly-test.md), [checklist-full-process-dfm-stackup](../verification/checklist-full-process-dfm-stackup.md)
- Acid traps: https://www.eevblog.com/forum/eda/acid-traps-310805/msg3983057 [S]; https://resources.pcb.cadence.com/blog/are-acid-traps-still-a-problem-for-pcbs [S]
- Thermal reliefs and reflow: https://resources.altium.com/p/how-to-design-circuit-boards-with-thermal-relief-pads [V]; https://jlcpcb.com/blog/thermal-relief-pad-design [V]
- Teardrops: https://sierraconnect.protoexpress.com/t/use-of-teardrops-in-pcb-design/2781 [S]
- 45° history: https://resources.altium.com/p/pcb-routing-angle-myths-45-degree-angle-versus-90-degree-angle [S]

See also: [rule-basis-set](rule-basis-set.md), [rule-genealogy-power-analog-thermal](rule-genealogy-power-analog-thermal.md), [rule-genealogy-si-emi-rf](rule-genealogy-si-emi-rf.md), [../verification/looks-right-metrics.md](../verification/looks-right-metrics.md)
