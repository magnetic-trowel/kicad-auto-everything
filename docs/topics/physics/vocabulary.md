# Physics-first layout vocabulary: primitives, relations, operators, bands, the physics graph

**TL;DR**
- A layout is what the schematic leaves out: a parasitic R, L, M, C, G network, field structures, heat paths, dielectric stress and a manufacturing artifact. This vocabulary names that realization with **12 atoms** (Port, Node, Loop, Body, Reference, Channel, Cavity, Discontinuity, Antenna, Heat path, Barrier, Coupling) and **5 value types** (Spectrum, Sensitivity, Budget, Band, Regime). Every structure is either *designed* (it has a spec) or *parasitic* (it has a budget).
- Three facts force these atoms instead of net/trace/via/pour:
  - a schematic net is **half a port**;
  - inductance belongs to **loops**, while partial inductance is the accounting unit;
  - where return current flows is a **regime** with a computable boundary, f_x ≈ R_□/(2π·µ0·h): about 0.3 MHz at h = 0.2 mm and 39 kHz at h = 1.6 mm for 1 oz copper [C].
- Aggressors and victims come as duals. **dv/dt Nodes** act through electric field (capacitive coupling, voltage-driven antennas); **di/dt Loops** act through magnetic field (inductive coupling, current-driven antennas). Every operator has a signed effect on both: widening copper helps loops and feeds and hurts nodes.
- Relations exist twice: **required** (detectors, LLM, human) and **observed** (computed on a PEEC-like physics graph). Critics diff the two. Budgets are queries over that graph, which reduces to port models for circuit simulation and expands to field maps for review.
- Rules of thumb become derived proxies: "3W" from a coupling budget, "crystal ≤ 5 mm" from a pF budget, "split the ground" from current exclusion plus sense ports, "minimize loop area" from a magnetic moment with its image (a plane 0.1 mm under a loop cuts coupling at 10 mm by about 55 dB; at 1.6 mm, by about 8 dB) [C].

## Key facts

### Why net, trace, via and pour are not enough

- **Half-ports.** A schematic net is one node. Physics acts on terminal pairs:
  - Modelica connectors pair a potential (equal across a connection) with a flow (sums to zero) ([spec § 9.2](https://specification.modelica.org/maint/3.6/connectors-and-connections.html)) [P];
  - FastHenry's port is `.External node1 node2`, and a port with "no possible return path" gives an impedance matrix that is "nonsense (NaN)" ([guide § 1.3.5](https://www.fastfieldsolvers.com/Download/FastHenry_User_Guide.pdf)) [P];
  - LearnEMC: "Signal currents always return to their source (i.e., steady state current paths are always loops)" and "Recognize the difference between ground and current return" ([guidelines](https://learnemc.com/the-most-important-emc-design-guidelines)) [P].
  
  The schematic is silent about how current comes back; the layout decides.
- **Loops and partial elements.** Paul: inductance is "fundamentally related to the inductance of a closed loop of current". Ruehli's partial inductance (IBM J. R&D 16(5), 1972) lets an inductive voltage be "attributed between two points on a portion of that conductor", which is what ground bounce and rail collapse need. "Loop inductance has nothing to do with solving these problems" ([Paul, IEEE EMC Society Newsletter, 2010](https://ewh.ieee.org/soc/emcs/acstrial/newsletters/winter10/InductanceCal.pdf)) [P]. So budgets attach to Loops, and the ledger attributes spend to segments with partial elements (I1).
- **Return location is a regime.** A 2D partial-element model of a 0.3 mm trace over a 1 oz plane ([vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py)) [C]:

  | h (trace to plane) | 50% of return within ±3h | 70% within ±3h | f_x = R_□/(2πµ0h) |
  |---|---|---|---|
  | 0.1 mm | 0.31 MHz | 1.2 MHz | 0.62 MHz |
  | 0.2 mm | 0.14 MHz | 0.43 MHz | 0.31 MHz |
  | 1.6 mm | 18 kHz | 46 kHz | 39 kHz |

  The boundary does not depend on plane width (20–100 mm). The high-frequency limit, 0.77–0.80 within ±3h, matches the closed form (2/π)·atan 3 = 0.795, Adamczyk's "80% within ±3h" ([si-fundamentals](../rules/si-fundamentals.md)). Published crossovers ("beyond 10 kHz", "500–1,000 kHz split") differ because their geometries differ ([InCompliance, Adamczyk](https://digital.incompliancemag.com/issue/august-2023/return-current-distribution-in-a-pcb-microstrip-line-configuration/)) [S]. Below f_x/10, return current spreads by resistance, and star-point and separation rules are physics. Above about 3·f_x it rides under the trace, and the same rules are harmful.
- **Loop area is the wrong scalar.** LearnEMC: "Radiation is NOT proportional to loop area" [P]. Mutual inductance between coplanar loops of 20 mm² and 10 mm² ([vo_numbers.py halo](../../../tools/research/physics/vo_numbers.py)) [C]:

  | Distance | Free space | Plane 1.6 mm below | Plane 0.1 mm below |
  |---|---|---|---|
  | 10 mm | 20 pH | 7.5 pH | 0.036 pH |
  | 20 mm | 2.5 pH | 0.27 pH | 0.001 pH |

  The image of a loop in a close plane turns its dipole into a near-quadrupole, falling as about 1/r⁵ instead of 1/r³ (point dipoles, perfect plane, above f_x). The scalar to budget is the moment *with its image*, not the area. AN-139's measured 13 nH (plane 0.12 mm) against 187 nH (no plane) for the same loop shows the same physics ([hot-loops](../rules/power/hot-loops.md)) [P].

### The working hypothesis, sharpened

We adopt it with three amendments [I]:
1. **"Invisible" becomes "designed or budgeted".** Some realizations *are* the function: antennas, transmission lines, PCB shunts and inductors, heat spreaders, Kelvin senses, guards, spark gaps. They use the same primitives with the objective's sign flipped.
2. **Invisibility is relative to a victim in a band.** Ott's source → path → receptor triple becomes a Coupling with a margin in dB: threshold − (spectrum × transfer).
3. **The spectrum is partly a layout output.** A clean 12 V, 2 ns trapezoid is 90 dB down at 2.45 GHz [C], but switch-node ringing at hundreds of MHz, set by loop L and C_oss, dominates the GHz content. Excitations must be back-annotated from layout-aware simulation ([schematic-to-physics](schematic-to-physics.md)).

### Atoms

| Atom | Definition | Physics it carries | Why it earns its place | Rule of thumb it decompresses |
|---|---|---|---|---|
| **Port** | Terminal pair (signal + reference) where energy enters or leaves a structure; connectors are ports with fixed poses | impedance, spectrum, pose | The reference terminal makes the return explicit | "decap close to the pin", "connectors on one edge" |
| **Node** | Equipotential conductor set in a band, characterized by dv/dt and source impedance | C to reference, C_m, E-field, voltage-driven antenna | Dual of Loop; the home of displacement current and high-impedance victims | "keep SW small", "guard high-Z inputs" |
| **Loop** | Closed current path including its return, characterized by di/dt | L_loop, magnetic moment, M | Inductance and B-field exist only for loops | "minimize loop area" |
| **Body** | 2.5D copper region of one net on one layer (tracks, pads, zones and via barrels merged) carrying a current density J | partial R, L, C; J; heat spreading | Operators reshape bodies, not centrelines | "pour power", "1 mm per amp" |
| **Reference** | Conductor region a structure is guided against in a band: plane region, pour, return trace, cable shield | return distribution, image | Separates *ground* (a net) from *return* (a physical role) | "solid ground plane" |
| **Channel** | Port → port path with cross-section, reference and transitions | Z0, delay, loss, mode conversion | Owns dB, ps and mV budgets | "match length", "≤ N vias" |
| **Cavity** | Two overlapping references | modes f_mn, Q | Resonances no lumped element shows | "stitch every λ/20", "20H" |
| **Discontinuity** | Break in a reference under a served structure: slot, split, edge, antipad chain, reference change | detour inductance, plane voltage, CM | Turns a return path into an antenna feed; may be designed (void under an RF pad) | "never cross splits", "1.5W from voids" |
| **Antenna** | Two electrically large conductors with a voltage or current between them ([emc-placement](../rules/emc-placement.md)) | V_cm, I_cm, far field | Two named halves; one type for intended and unintended | "no HS circuitry between connectors" |
| **Heat path** | Thermal network from a dissipating source to a sink | K/W, ΔT, gradient | Tj, thermal EMF, I²R feedback | "2 cm² per W", "thermal vias" |
| **Barrier** | Separation between voltage domains | creepage, clearance, C across | Dielectric stress and the EMI path across isolation | creepage tables |
| **Coupling** | Aggressor, victim, mechanism, band, transfer | C_m, M, shared impedance, radiation, heat, leakage | Where budgets live | "3W", "keep away from" |

**Value types.** *Spectrum*: envelope per node, loop or port, with the trapezoid corners 1/(πτ) and 1/(πt_r) ([LearnEMC](https://learnemc.com/ext/calculators/trapezoid_harmonics/index.html)) [S], or back-annotated from simulation. *Sensitivity*: threshold, band and the victim's own rejection (filter, PSRR, CMRR). *Budget*: bound, allocation, basis and ledger spend (I1). *Band*: a named frequency interval. *Regime*: computed per (structure, band); never written by the LLM.

**Composites** (code expands them into atoms):
- *Cell*: one commutation-cell template (switch pair, HF capacitor, switch node, gate loops, Kelvin points) for buck, boost, half-bridge, flyback, class D and motor phases.
- *Feed*: DC delivery from port to port.
- *Sense port*: a zero-current port with a tap point on a body.
- *Shield*: a designed structure protecting a victim (grounded or driven guard, fence, can).
- *Exclusion*: a region where an aggressor's current density must stay below a fraction.

**Cut or merged.** *Branch* → graph edge (users see inductance only on loops). *Aperture* → Discontinuity or Barrier slot. *Spectrum* → value type. *Commutation cell* → Cell. *Ground* → Reference (role) plus a chassis Port. *Net* → KiCad binding only; *trace, via, pour* → geometry view only.

**Atoms are *where*; quantities are *what*.** Each atom exposes part of the 12-quantity basis in [rule-basis-set](rule-basis-set.md): Loop → L, M, Vcm, Res; Node → Cm, Vcm; Body → R, L, Th; Channel → Z, Bal, Res; Cavity → Res; Barrier → Ins; Heat path → Th. Fab and Mech attach to bodies as constraints ([thermal-hv-mfg ideas](../../ideas/physics-first/thermal-hv-mfg.md)); Cog and Std attach to budgets as provenance.

### Relations

| Relation | Meaning | Required by | Observed by |
|---|---|---|---|
| `carries(Body, Loop/Feed)` | body is part of the current path | templates | J solve |
| `returns_through(Loop/Channel, Reference, band)` | return conductor per band | LLM, templates | current split |
| `references(Channel/Node, Reference, band)` | field is guided against it | stackup | reference map |
| `couples(aggr, victim, mech, band)` | entity with a budget | screen, LLM | C_m, M, R_shared, ΔT |
| `shields(Shield, victim, band)` | designed protection | LLM | coupling with and without |
| `excludes(region, Loop, band)` | aggressor J kept out | LLM | J solve |
| `senses(Port, Body@point)` | zero-current tap | templates | J on the tap segment |
| `feeds`, `bonds`, `isolates`, `spreads_heat`, `part_of` | DC delivery, chassis bond, barrier, heat flow, membership | detectors | solvers |

### Bands and regimes

| Boundary | Formula | Value [C] | Rule valid on one side only |
|---|---|---|---|
| Return localization | f_x ≈ R_□/(2πµ0h) | 0.31 MHz (h = 0.2 mm, 1 oz); 39 kHz (1.6 mm) | Star ground below; "return under the trace" above |
| Skin depth = copper thickness | f = ρ/(πµ0t²) | 3.56 MHz for 35 µm | DC width tables below |
| Lumped vs distributed | ℓ > (t_r/6)·v | 27.8 mm at 1 ns; 2.8 mm at 100 ps | Termination and stub rules above |
| Spectral knee | 1/(π·t_r) | 159 MHz at 2 ns | −40 dB/decade above |
| Plane cavity | f₁₀ = c/(2a√εr) | about 720 MHz for 100 mm FR-4 ([decoupling-pdn](../rules/decoupling-pdn.md)) | Lumped PDN models below |
| Corner geometry | — | multi-GHz only ([rf](../rules/rf.md)) | Arcs and mitres above |

Rule packs gain an `applies_if: {regime: ...}` key, so the system picks the right variant instead of a global slogan ([rule-pack-format](../rules/rule-pack-format.md)).

### Operators

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

### The physics graph

- **Graph.** Nodes are mesh cells of bodies, port terminals and thermal nodes. Edges are partial R, partial L, M (dense, sparsified by distance or hierarchy), C to references and between bodies, G (leakage) and thermal conductances, with electrothermal coupling through I²R. This is PEEC (Ruehli 1972) [S]; FastHenry and FasterCap inputs are nearly this graph [P].
- **Per band.** R regime: resistive network; L regime: R + jωL; distributed: line segments or a full-wave call ([solver-ladder](solver-ladder.md)).
- **Queries.** Loop L (impedance between two port terminals), M and C_m between named structures, IR drop, J inside an exclusion region, ΔT. A budget is a query plus a bound.
- **Three views and five transforms.**
  - Views: *geometry* (KiCad objects), *circuit* (port Z/Y/S matrices, SPICE subcircuits, Touchstone), *field* (J, near-field B and E, T, rasterized per band).
  - Transforms: *extract* (geometry → graph), *reduce* (graph → circuit, by Kron reduction or passive model-order reduction), *expand* (graph → field), *back-annotate* (circuit simulation → spectra), *synthesize* (field → geometry through operators).
- **Incremental.** One edit touches few bodies; update the reduced model with low-rank corrections and re-extract locally ([physics-in-the-loop-optimization](physics-in-the-loop-optimization.md)) [I].

### Visual vocabulary (board view and VLM renders)

| Element | Glyph | Encodes |
|---|---|---|
| Loop | translucent filled polygon, arrowed outline | fill colour = budget used (green < 50%, amber, red > 100%); label "0.7/1.0 nH" |
| Node | hatched area with a dashed halo | halo radius = distance at which the worst victim's budget is met |
| Return path | dashed ghost of the signal on its reference layer | red ✕ at each discontinuity crossed |
| Port | filled dot (signal) and open dot (reference) joined by a bar; arrow for power flow | edge-anchored ports drawn on the outline |
| Coupling | zig-zag spring between aggressor and victim | letter C/M/Z/R/T/G for mechanism; thickness = budget used |
| Antenna | both halves outlined, joined by a "V_cm" label | budget used |
| Heat path | orange arrows from source to sink; isotherms | ΔT label |
| Barrier | double line; creepage path drawn | "needed / present" mm |
| Sense tap | small "K" diamond at the tap point | — |
| Budget bar | stacked bar per budget, split by spender | ledger attribution |

This extends U5 ([workflow-ux](../../ideas/original/workflow-ux.md)). Glyphs come from the *observed* graph and share ids with the text, so a VLM judge and a human see the same objects.

## Recommendations for our system

- **Adopt the 12 atoms and 5 value types** as the `physics:` block of `pcb-intent/0.3` ([physics-ir](physics-ir.md)); the LLM reasons in these nouns and never draws copper [I].
- **Make port pairs and closed loops validation errors**, not warnings. Most "DRC-clean but physically wrong" layouts have a return path nobody named [I].
- **Compute regimes before selecting rules.** f_x, skin depth, electrical length and cavity modes per structure decide which rule variant applies [I].
- **Build the physics graph at two fidelities first:** closed forms for the placer's inner loop, FastHenry/FasterCap decks for verdicts; full-wave only for channels, transitions and antennas ([open-solvers](open-solvers.md)) [I].
- **Render glyphs from the ledger** with the same ids as the IR, for humans and the VLM judge [I].

## Conflicts and open questions

- **Body granularity.** One body per net per layer is simple, but J solves need a mesh; per connected component may be the better id.
- **The image results are idealized.** A perfect, infinite plane overstates shielding below f_x, near plane edges and over slots; the [C] table bounds the effect and does not predict it.
- **Designed vs parasitic can overlap.** A VIN pour is a feed (widen it) and part of a hot loop (keep it tight); a heat-spreading pour on a switch node is a dv/dt aggressor. The ledger must hold both budgets and show the trade.
- **Consistency with rule genealogy.** The regime table must agree with the basis set in [rule-basis-set](rule-basis-set.md); if the two disagree, the computed boundary should win.

## Sources

- Research notes: [rules_highspeed_emi.md § 1, 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [rules_power_rf_analog_dfm.md § 1, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
- C. R. Paul, "Comments on the paper by Al Ruehli", IEEE EMC Society Newsletter, Winter 2010: https://ewh.ieee.org/soc/emcs/acstrial/newsletters/winter10/InductanceCal.pdf [P]; A. E. Ruehli, IBM J. R&D 16(5):470–481, 1972 [S]
- FastHenry 3.0 user guide: https://www.fastfieldsolvers.com/Download/FastHenry_User_Guide.pdf [P]
- Modelica 3.6, ch. 9: https://specification.modelica.org/maint/3.6/connectors-and-connections.html [P]
- LearnEMC: https://learnemc.com/the-most-important-emc-design-guidelines [P]
- Scripts: [vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py), [vo_numbers.py](../../../tools/research/physics/vo_numbers.py), [vo_ir_check.py](../../../tools/research/physics/vo_ir_check.py)

See also: [README.md](README.md), [physics-ir.md](physics-ir.md), [physics-ir-examples.md](physics-ir-examples.md), [rule-basis-set.md](rule-basis-set.md), [design-reasoning-architecture.md](design-reasoning-architecture.md), [../architecture/constraint-ir.md](../architecture/constraint-ir.md), [../../ideas/physics-first/language.md](../../ideas/physics-first/language.md)
