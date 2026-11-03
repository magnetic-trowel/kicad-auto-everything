# Physics graph, operators and glyphs

Scope: the operators that edit layout atoms (with signed physics effects), the PEEC-like physics graph with its views and transforms, and the visual glyphs rendered from it. Not here: atoms, relations, bands, glossary -> [vocabulary](vocabulary.md); IR schema -> [physics-ir](physics-ir.md).
Keys: operators, widen_to_pour, shrink_node, fold_loop_vertical, overlap_return, stitch, fence, bridge, kelvin_tap, split_band, exclude, orthogonalize, guard, symmetrize, shape_by_current, void, slow_edge, sensitivity card, physics graph, PEEC, Kron reduction, model-order reduction, extract, reduce, expand, back-annotate, synthesize, glyphs, VLM renders, U5

## Operators

| Operator | Target | Signed physics effect | Compiles to |
|---|---|---|---|
| `widen_to_pour` | Body | R↓, L↓ (logarithmic), ΔT↓; C↑ (bad on dv/dt nodes) | zone with current-shaped outline |
| `shrink_node` | Node | C↓, E-field↓; R↑ | pad-only copper, max-area zone |
| `fold_loop_vertical` | Loop | L ∝ h: SNVA803 2 mm², <0.5 nH; EPC about 65% below the best lateral loop ([hot-loops](../rules/power/hot-loops.md)) | via reservations, return zone on the next layer |
| `overlap_return` | Loop, Channel | go/return mutual↑, L_loop↓, field confined | return conductor on the adjacent layer |
| `stitch` / `fence` | Reference pair, Channel | cavity Q↓, transitions bridged; pitch ≤ λ_g/20 | via arrays |
| `bridge` | Discontinuity | detour↓ | via or stitching capacitor site |
| `kelvin_tap` | Sense port | I on the sense path → 0 | net tie, tap at the pad's inner edge |
| `split_band` | Reference | DC through a tie, HF through capacitors | net tie plus capacitor sites |
| `exclude` | region | aggressor J↓ in a victim's reference | rule area plus router cost |
| `orthogonalize` / `cancel` | inductive Coupling, Loop | M → 0 by axis rotation; counter-rotating halves make a quadrupole | orientation and symmetry constraints |
| `guard` | Node | leakage and C_m shunted | guard ring, driven or grounded |
| `symmetrize` / `isothermalize` | pair, region | mode conversion↓; thermal EMF↓ | symmetry constraints, copper island |
| `relocate_port` / `swap_pins` | Port | moves energy entry points | anchor or pin-swap ECO |
| `shape_by_current` | Body | removes low-J copper that adds C or antenna area | topology optimization ([copper-shape-synthesis](copper-shape-synthesis.md)) |
| `void` | Reference | designed discontinuity (RF pad, TIA IN−) | zone cut-out |
| `slow_edge` | Port | spectrum↓ above the knee; switching loss↑ | schematic ECO (series R, slew setting) |

Each operator carries a sensitivity card: which budgets move, sign, magnitude model and cost (area, vias, fab class).

## The physics graph

- **Graph.** Nodes are mesh cells of bodies, port terminals and thermal nodes. Edges are partial R, partial L, M (dense, sparsified by distance or hierarchy), C to references and between bodies, G (leakage) and thermal conductances, with electrothermal coupling through I²R. This is PEEC (Ruehli 1972) [S]; FastHenry's input (nodes, segments, planes, terminal-pair ports) is nearly this graph [P].
- **Per band.** R regime: resistive network; L regime: R + jωL; distributed: line segments or a full-wave call ([solver-ladder](solver-ladder.md)).
- **Queries.** Loop L (impedance between two port terminals), M and C_m between named structures, IR drop, J inside an exclusion region, ΔT. A budget is a query plus a bound.
- **Three views and five transforms.**
  - Views: *geometry* (KiCad objects), *circuit* (port Z/Y/S matrices, SPICE subcircuits, Touchstone), *field* (J, near-field B and E, T, rasterized per band).
  - Transforms: *extract* (geometry → graph), *reduce* (graph → circuit, by Kron reduction or passive model-order reduction), *expand* (graph → field), *back-annotate* (circuit simulation → spectra), *synthesize* (field → geometry through operators).
- **Incremental.** One edit touches few bodies; update the reduced model with low-rank corrections and re-extract locally ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)) [I].

## Visual vocabulary (board view and VLM renders)

- **Loop:** translucent filled polygon, arrowed outline; fill colour = budget used (green < 50%, amber, red > 100%); label "0.7/1.0 nH".
- **Node:** hatched area with a dashed halo; halo radius = distance at which the worst victim's budget is met.
- **Return path:** dashed ghost of the signal on its reference layer; red ✕ at each discontinuity crossed.
- **Port:** filled dot (signal) and open dot (reference) joined by a bar; arrow for power flow; edge-anchored ports drawn on the outline.
- **Coupling:** zig-zag spring between aggressor and victim; letter C/M/Z/R/T/G for mechanism; thickness = budget used.
- **Antenna:** both halves outlined, joined by a "V_cm" label; budget used.
- **Heat path:** orange arrows from source to sink; isotherms; ΔT label.
- **Barrier:** double line; creepage path drawn; "needed / present" mm.
- **Sense tap:** small "K" diamond at the tap point; —.
- **Budget bar:** stacked bar per budget, split by spender; ledger attribution.

This extends U5 ([workflow-ux](../../ideas/original/workflow-ux.md)). Glyphs come from the *observed* graph and share ids with the text, so a VLM judge and a human see the same objects.

- Render glyphs from the ledger with the same ids as the IR, for humans and the VLM judge [I].

## Sources

- A. E. Ruehli, IBM J. R&D 16(5):470–481, 1972 [S]; FastHenry 3.0 user guide: https://www.fastfieldsolvers.com/Download/FastHenry_User_Guide.pdf [P].
