# Physics-first layout vocabulary: glossary, primitives, relations, bands

Scope: the one place symbols and terms of docs/topics/physics are defined (glossary), plus the layout vocabulary: 12 atoms, 5 value types, relations, bands and regimes. Not here: operators, the physics graph, glyphs -> [physics-graph](physics-graph.md); the 12 basis quantities -> [rule-basis-set](rule-basis-set.md#the-basis-set); IR schema -> [physics-ir](physics-ir.md); data model (Piece, Passport, Job …) -> [physics-core-v2-api](physics-core-v2-api.md).
Keys: glossary, symbols, notation, atoms, Port, Node, Loop, Body, Reference, Channel, Cavity, Discontinuity, Antenna, Heat path, Barrier, Coupling, Spectrum, Sensitivity, Budget, Band, Regime, half-port, partial inductance, return localization f_x

## Glossary

"Where" = doc with the defining derivation or table. 1 oz copper: t = 35 µm, R_s = 0.49 mΩ/□.

| Symbol / term | Definition | Unit | Where |
|---|---|---|---|
| θ | electrical length ωℓ/v | rad | [foundations](foundations.md#the-circuit-is-the-zeroth-order), [lens-ls](lens-ls.md) |
| T, T_d | delay ℓ/v of a piece | s | [foundations](foundations.md#theorem-t1-impedance-level) |
| v, v_p | propagation speed c/√ε_eff | m/s | all |
| Z0 | characteristic impedance √(L′/C′) | Ω | [foundations](foundations.md#theorem-t1-impedance-level) |
| Z | circuit impedance level ΔV/ΔI of a piece in a band | Ω | [foundations](foundations.md#theorem-t1-impedance-level) |
| m | Z0/Z (mismatch ratio) | — | [foundations-derivations](foundations-derivations.md#d2-impedance-level-t1) |
| ε_L, ε_C | KVL and KCL breaking parameters θ·Z0/Z, θ·Z/Z0 | — | [lens-ls](lens-ls.md) |
| K_L, K_C | CT's ε_L, ε_C without Z0 (ωL/\|Z\|, ωC\|Z\|); also crosstalk coefficients in [fields-si-emi](fields-si-emi.md#4-crosstalk-from-field-overlap) | — | [lens-ct](lens-ct.md) |
| G | loop gain of eliminated hidden coordinates; gentle iff ρ(G) < 1 | — | [foundations-derivations](foundations-derivations.md#d1-the-gentleness-criterion-g) |
| ρ(·) | spectral radius | — | [foundations](foundations.md) |
| g | electro-thermal loop gain ρ(D^½ΘD^½) | — | [lens-th](lens-th.md) |
| Q, Q_m | quality factor of mode m; 1/Q_m = Σ_k 1/Q_mk | — | [lens-th](lens-th.md) |
| Q_cu | copper-only Q of a wide pair, h/max(δ, δ²/t) | — | [foundations-derivations](foundations-derivations.md#d7-one-length-one-q-curve-t2-t8) |
| h | height of a conductor above its return / plane | m | all |
| d | plane-pair (cavity) spacing | m | [pdn-and-commutation](pdn-and-commutation.md) |
| t | copper thickness | m | all |
| w | conductor width | m | all |
| D | aggressor–victim (centre) spacing | m | [fields-si-emi](fields-si-emi.md) |
| b | stripline cavity height | m | [fields-si-emi](fields-si-emi.md) |
| R_s, R_□ | sheet resistance ρ/t | Ω/□ | all |
| N□ | number of squares between ports | — | [power-copper](power-copper.md#3-trace-vs-pour-vs-plane) |
| δ | skin depth √(ρ/(πfμ0)); 66 µm at 1 MHz in Cu | m | [power-copper](power-copper.md#5-ac-effects) |
| ℓ_m | plane resolution length R_s/(πμ0f) = δ²/t; 124 mm at 1 kHz, 0.124 mm at 1 MHz (1 oz) | m | [lens-ls](lens-ls.md) |
| ℓ50, ℓ_d | half-return-spread length R_s/(2πμ0f) = ℓ_m/2 (VP, SY names) | m | [lens-vp](lens-vp.md), [lens-sy](lens-sy.md) |
| f_x | return-localization crossover R_s/(2πμ0h) (ℓ_m = 2h) | Hz | [bands](#bands-and-regimes) |
| τ_e | insulator charge relaxation ε/σ (surface: ε_eff·g/σ_s) | s | [lens-ls](lens-ls.md) |
| η0 | free-space impedance ≈ 377 Ω | Ω | [lens-ls](lens-ls.md) |
| μ0, ε0, εr, ε_eff | vacuum permeability, permittivity, relative and effective permittivity | H/m, F/m, — | all |
| tanδ, Dk, Df | dielectric loss tangent, dielectric constant, dissipation factor | — | [lens-ls](lens-ls.md), [rf-geometry](rf-geometry.md) |
| L, L′, L_p, M | loop inductance, per length, partial inductance, mutual inductance | H, H/m | [pdn-and-commutation](pdn-and-commutation.md) |
| C_m, Cm | node or mutual capacitance (basis quantity Cm) | F | [rule-basis-set](rule-basis-set.md#the-basis-set) |
| C_ext | capacitance of a conductor to the outside world | F | [lens-ct](lens-ct.md) |
| I_CM, V_cm | common-mode current / voltage on cables | A, V | [fields-emi-budget](fields-emi-budget.md) |
| L_ret | return (plane) inductance between cable points (MREMC) | H | [fields-emi-budget](fields-emi-budget.md) |
| κ_ab | share of a local return voltage reaching cable-point pair (a, b) | — | [fields-si-emi](fields-si-emi.md) |
| Δψ, ψ | stream-function step (current intercepted) across a cut; ψ sheet stream function, J = ∇ψ × n | A | [lens-ct](lens-ct.md), [cross-domain-lessons](cross-domain-lessons.md) |
| ρ_b (leverage) | probability a piece lies in a random spanning tree; removal = a_b/(1 − ρ_b) | — | [lens-cd](lens-cd.md) |
| a_b | Tellegen attribution of a budget to piece b | budget unit | [lens-cd](lens-cd.md) |
| λ_max | collective leverage of an edit (largest eigenvalue of M) | — | [foundations-derivations](foundations-derivations.md#d1-the-gentleness-criterion-g) |
| χ | imbalance (current-division factor C1g/(C1g+C2g)); also cancellation index \|Σa\|/Σ\|a\| in [lens-cd](lens-cd.md) | — | [lens-sy](lens-sy.md) |
| f_p, ω_p, k_p | wire-medium (via-lattice / decap-field) plasma frequency, wavenumber; ω_p² = n/(L_post·C′) | Hz, rad/m | [lens-ls](lens-ls.md), [derivation-audit](derivation-audit.md#nine-short-derivations) |
| a (lattice) | via or decap pitch | m | [lens-ls](lens-ls.md) |
| λ (screening) | screening length of a sheet equation; PDN λ = √(L_c/(μ0·d·n)); thermal λ = √(G_s/h_total) | m | [cross-domain-lessons](cross-domain-lessons.md), [thermal-physics](thermal-physics.md) |
| λ_d, λ_g | wavelength in the dielectric, guided wavelength | m | [rf-geometry](rf-geometry.md) |
| G_s | thermal sheet conductance Σ k·t | W/K | [thermal-physics](thermal-physics.md) |
| h, h_total (thermal) | heat-transfer coefficient per face / both faces | W/m²K | [thermal-physics](thermal-physics.md) |
| Θ, θ_ij | thermal influence matrix (K/W); θ_JA, θ_JC, θ_JT package resistances | K/W | [thermal-physics](thermal-physics.md), [lens-th](lens-th.md) |
| α (thermal) | thermal diffusivity (Cu 1.1×10⁻⁴ m²/s); also TCR 0.00393/K | m²/s, 1/K | [power-copper](power-copper.md#4-corners-and-curves), [thermal-physics](thermal-physics.md) |
| κ | copper thermal diffusivity (foundations notation) | m²/s | [foundations-derivations](foundations-derivations.md#d8-loss-versus-damage-t11) |
| L0 | Lorenz number (Wiedemann–Franz G_th = L0·T·G_el) | W·Ω/K² | [lens-th](lens-th.md) |
| S | Seebeck coefficient | V/K | [lens-th](lens-th.md) |
| t_r | edge (rise) time; f_knee ≈ 0.35/t_r; spectral corner 1/(π·t_r) | s | [fields-emi-budget](fields-emi-budget.md) |
| L_T | transfer length of a via field | m | [cross-domain-lessons](cross-domain-lessons.md) |
| VOI, EVPI, EVPPI | value of (perfect, partial perfect) information | budget unit | [lens-in](lens-in.md) |
| σ_u, s | candidate-specific error spread, true spread among contenders | — | [lens-in](lens-in.md) |
| n* | perturbation order a victim needs, ln(B/S)/ln ε | — | [lens-ls](lens-ls.md) |
| τ (budget) | budget/floor ratio ranking a structure's tier | — | [worked-thought-experiments](worked-thought-experiments.md) |
| LII | layout-induced impairment index (≤ 1 passes) | — | [lens-in](lens-in.md) |
| D (damage) | life fraction Σ∫ḋ dt ≤ 1 (Miner) | — | [lens-th](lens-th.md) |
| r^(π/α−1) | field/current scaling near a wedge of interior angle α | — | [lens-sy](lens-sy.md) |
| F1–F7, T1–T13 | first principles, design theorems | — | [foundations](foundations.md) |
| P1–P7, MP, LG, CG | audit principle codes | — | [derivation-audit](derivation-audit.md#method) |
| L, M, Cm, R, Z, Bal, Vcm, Res, Ins, Th, Mech, Fab | basis quantities | — | [rule-basis-set](rule-basis-set.md#the-basis-set) |
| A, A′, B, C (term class) | self-energy lowered / raised by copper, interaction, non-variational | — | [lens-vp](lens-vp.md) |
| [P] [S] [V] [I] [C] | evidence tags | — | [CONVENTIONS](../../CONVENTIONS.md) |
| RB4 | reference board 60 × 40 mm, 4 layers, 0.1 mm prepreg, 0.5 oz planes | — | [lens-ls](lens-ls.md) |

## Why net, trace, via and pour are not enough

A layout is what the schematic leaves out: a parasitic R, L, M, C, G network, field structures, heat paths, dielectric stress and a manufacturing artifact. Every structure is *designed* (spec) or *parasitic* (budget); designed ones (antennas, transmission lines, PCB shunts and inductors, heat spreaders, Kelvin senses, guards, spark gaps) use the same primitives with the objective's sign flipped ([working hypothesis](rule-basis-set.md#the-working-hypothesis-sharpened)). Aggressors and victims come as duals: **dv/dt Nodes** act through E (capacitive coupling, voltage-driven antennas), **di/dt Loops** through B (inductive coupling, current-driven antennas); widening copper helps loops and feeds and hurts nodes.

- **A net is half a port.** Physics acts on terminal pairs: Modelica connectors pair a potential (equal across a connection) with a flow (sums to zero) ([spec § 9.2](https://specification.modelica.org/maint/3.6/connectors-and-connections.html)) [P]; FastHenry's port is `.External node1 node2`, and a port with "no possible return path" gives an impedance matrix that is "nonsense (NaN)" ([guide § 1.3.5](https://www.fastfieldsolvers.com/Download/FastHenry_User_Guide.pdf)) [P]; LearnEMC: "Signal currents always return to their source (i.e., steady state current paths are always loops)" and "Recognize the difference between ground and current return" ([guidelines](https://learnemc.com/the-most-important-emc-design-guidelines)) [P]. The layout decides the return.
- **Inductance belongs to loops; partial inductance is the accounting unit.** Paul: inductance is "fundamentally related to the inductance of a closed loop of current"; Ruehli's partial inductance (IBM J. R&D 16(5), 1972) lets an inductive voltage be "attributed between two points on a portion of that conductor", which ground bounce and rail collapse need; "Loop inductance has nothing to do with solving these problems" ([Paul, IEEE EMC Society Newsletter, 2010](https://ewh.ieee.org/soc/emcs/acstrial/newsletters/winter10/InductanceCal.pdf)) [P]. Budgets attach to Loops; the ledger attributes spend to segments with partial elements (I1).
- **Return location is a regime with a computable boundary.** 2-D partial-element model, 0.3 mm trace over a 1 oz plane ([vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py)) [C]:

  | h | 50% of return within ±3h | 70% within ±3h | f_x = R_□/(2πµ0h) |
  |---|---|---|---|
  | 0.1 mm | 0.31 MHz | 1.2 MHz | 0.62 MHz |
  | 0.2 mm | 0.14 MHz | 0.43 MHz | 0.31 MHz |
  | 1.6 mm | 18 kHz | 46 kHz | 39 kHz |

  Independent of plane width (20–100 mm). HF limit 0.77–0.80 within ±3h matches (2/π)·atan 3 = 0.795, Adamczyk's "80% within ±3h" ([si-fundamentals](../rules/si-fundamentals.md)). Published crossovers ("beyond 10 kHz", "500–1,000 kHz split") differ by geometry ([InCompliance, Adamczyk](https://digital.incompliancemag.com/issue/august-2023/return-current-distribution-in-a-pcb-microstrip-line-configuration/)) [S]. Below ~f_x/10 most return spreads by resistance and star-point and separation rules are physics; above ~3·f_x it rides under the trace and the same rules are harmful.
- **Loop area is the wrong scalar.** LearnEMC: "Radiation is NOT proportional to loop area" [P]. Mutual L between coplanar 20 mm² and 10 mm² loops ([vo_numbers.py halo](../../../tools/research/physics/vo_numbers.py)) [C]:

  | Distance | Free space | Plane 1.6 mm below | Plane 0.1 mm below |
  |---|---|---|---|
  | 10 mm | 20 pH | 7.5 pH | 0.036 pH |
  | 20 mm | 2.5 pH | 0.27 pH | 0.001 pH |

  A close plane's image turns the dipole into a near-quadrupole, ~1/r⁵ instead of 1/r³ (point dipoles, perfect plane, above f_x): a plane 0.1 mm under a loop cuts coupling at 10 mm by ~55 dB, at 1.6 mm by ~8 dB. Budget the moment *with its image*. AN-139's measured 13 nH (plane 0.12 mm) vs 187 nH (no plane) for one loop shows the same ([hot-loops](../rules/power/hot-loops.md)) [P].

## Atoms

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

**Value types.** *Spectrum*: envelope per node, loop, port, trapezoid corners 1/(πτ) and 1/(πt_r) ([LearnEMC](https://learnemc.com/ext/calculators/trapezoid_harmonics/index.html)) [S], or back-annotated from simulation. *Sensitivity*: threshold, band and the victim's own rejection (filter, PSRR, CMRR). *Budget*: bound, allocation, basis and ledger spend (I1). *Band*: a named frequency interval. *Regime*: computed per (structure, band); never written by the LLM.

**Composites** (code expands them into atoms): *Cell* = one commutation-cell template (switch pair, HF capacitor, switch node, gate loops, Kelvin points) for buck, boost, half-bridge, flyback, class D, motor phases; *Feed* = DC delivery port to port; *Sense port* = zero-current port with a tap point on a body; *Shield* = designed protection of a victim (grounded or driven guard, fence, can); *Exclusion* = region where an aggressor's current density stays below a fraction.

**Cut or merged.** *Branch* → graph edge (users see inductance only on loops). *Aperture* → Discontinuity or Barrier slot. *Spectrum* → value type. *Commutation cell* → Cell. *Ground* → Reference (role) plus a chassis Port. *Net* → KiCad binding only; *trace, via, pour* → geometry view only.

**Atoms are *where*, quantities *what*.** Each atom exposes part of the 12-quantity basis ([rule-basis-set](rule-basis-set.md#the-basis-set)): Loop → L, M, Vcm, Res; Node → Cm, Vcm; Body → R, L, Th; Channel → Z, Bal, Res; Cavity → Res; Barrier → Ins; Heat path → Th. Fab and Mech attach to bodies as constraints ([thermal-hv-mfg ideas](../../ideas/physics-first/thermal-hv-mfg.md)); Cog and Std attach to budgets as provenance.

## Relations

- `carries(Body, Loop/Feed)`: body is part of the current path. Required by templates; observed by J solve.
- `returns_through(Loop/Channel, Reference, band)`: return conductor per band. Required by LLM, templates; observed by current split.
- `references(Channel/Node, Reference, band)`: field is guided against it. Required by stackup; observed by reference map.
- `couples(aggr, victim, mech, band)`: entity with a budget. Required by screen, LLM; observed by C_m, M, R_shared, ΔT.
- `shields(Shield, victim, band)`: designed protection. Required by LLM; observed by coupling with and without.
- `excludes(region, Loop, band)`: aggressor J kept out. Required by LLM; observed by J solve.
- `senses(Port, Body@point)`: zero-current tap. Required by templates; observed by J on the tap segment.
- `feeds`, `bonds`, `isolates`, `spreads_heat`, `part_of`: DC delivery, chassis bond, barrier, heat flow, membership. Required by detectors; observed by solvers.

## Bands and regimes

| Boundary | Formula | Value [C] | Rule valid on one side only |
|---|---|---|---|
| Return localization | f_x ≈ R_□/(2πµ0h) | 0.31 MHz (h = 0.2 mm, 1 oz); 39 kHz (1.6 mm) | "Return under the trace" above. Star grounding pays only where the return spread ℓ_m/2 exceeds the aggressor–victim distance (below ~6 kHz at 10 mm on 1 oz; [derivation-audit](derivation-audit.md)) |
| Skin depth = copper thickness | f = ρ/(πµ0t²) | 3.56 MHz for 35 µm | DC width tables below |
| Lumped vs distributed | ℓ > (t_r/6)·v | 27.8 mm at 1 ns; 2.8 mm at 100 ps | Termination and stub rules above |
| Spectral knee | 1/(π·t_r) | 159 MHz at 2 ns | −40 dB/decade above |
| Plane cavity | f₁₀ = c/(2a√εr) | about 720 MHz for 100 mm FR-4 ([decoupling-pdn](../rules/decoupling-pdn.md)) | Lumped PDN models below |
| Corner geometry | — | multi-GHz only ([rf](../rules/rf.md)) | Arcs and mitres above |

Rule packs gain an `applies_if: {regime: ...}` key to pick the variant per regime ([rule-pack-format](../rules/rule-pack-format.md)).

## Use in kae

- Adopt the 12 atoms and 5 value types as the `physics:` block of `pcb-intent/0.3` ([physics-ir](physics-ir.md)); the LLM reasons in them, never draws copper [I].
- Make port pairs and closed loops validation errors, not warnings: most "DRC-clean but physically wrong" layouts have an unnamed return path [I].
- Compute regimes (f_x, skin depth, electrical length, cavity modes per structure) before selecting rules [I].
- Build the [physics graph](physics-graph.md#the-physics-graph) at two fidelities: closed forms in the placer's inner loop, our PEEC and FasterCap for verdicts; FastHenry internal-only (non-commercial notice); full-wave only for channels, transitions, antennas ([open-solvers](open-solvers.md)) [I].

## Open questions

- **Body granularity.** Per net per layer is simple; J solves need a mesh; per connected component may be the better id.
- **Image results are idealized:** a perfect infinite plane overstates shielding below f_x, near edges, over slots; the [C] table bounds, not predicts.
- **Designed vs parasitic overlap.** A VIN pour is a feed (widen) and part of a hot loop (tighten); a heat-spreading SW pour is a dv/dt aggressor. The ledger holds both budgets and shows the trade.
- **Consistency.** The regime table must agree with [rule-basis-set](rule-basis-set.md#regime-selectors-when-does-a-rule-bind); on disagreement the computed boundary wins.

## Sources

- Research notes: [rules_highspeed_emi.md § 1, 5](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_highspeed_emi.md); [rules_power_rf_analog_dfm.md § 1, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md)
- Primary sources (Paul 2010, Ruehli 1972, FastHenry guide, Modelica 3.6 ch. 9, LearnEMC) linked inline; Ruehli, IBM J. R&D 16(5):470–481, 1972 [S].
- Scripts: [vo_return_spread.py](../../../tools/research/physics/vo_return_spread.py), [vo_numbers.py](../../../tools/research/physics/vo_numbers.py), [vo_ir_check.py](../../../tools/research/physics/vo_ir_check.py)

See also: [physics-ir-examples](physics-ir-examples.md) · [constraint-ir](../architecture/constraint-ir.md) · [language ideas](../../ideas/physics-first/language.md)
