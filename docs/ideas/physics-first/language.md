# Language ideas: a shared physics vocabulary for layout (LA1–LA52)

Ideas for a physics vocabulary. The concepts are defined in
[vocabulary](../../topics/physics/vocabulary.md), the schema in
[physics-ir](../../topics/physics/physics-ir.md), and six worked circuits in
[physics-ir-examples](../../topics/physics/physics-ir-examples.md). These ideas build on the
budget ledger, dimensioned types and why-graph (I1–I3 in
[intent-and-why](../original/intent-and-why.md)) and do not repeat them. Where another
catalog owns the computation (RG = [rule-replacements](rule-replacements.md), XD =
[cross-domain](cross-domain.md), JPR = [joint-place-route](joint-place-route.md)), the idea here
is the *language handle* for it.

Tags: **new** (not found in the corpus), **combo** (combines known pieces), **sharp**
(sharpens an existing idea with a number or a test). Effort: S (days), M (weeks), L (months).
Evidence tags as in the topic docs; [C] numbers come from
`tools/research/physics/vo_*.py`.

**Top five to build first:** LA1 half-port promotion, LA12 band netlists for loop discovery,
LA7 current exclusion zones, LA30 operator sensitivity cards, LA39 mechanism hypotheses as the
LLM's main write.

## A. Atoms and grammar

1. **LA1. Half-port promotion** *(new, S)*. Before any placement, promote every net that touches an IC pin, a connector or a cell to a Port whose reference terminals are named: the nearest return pins from IBIS `GND`/`POWER` pins or the pin-role ontology, the receptacle's GND pins, the cap's other pad. A net that cannot be paired raises a "half-port" finding the LLM must resolve. A schematic says nothing about return current, and FastHenry refuses a port with no return path (NaN impedance) [P]; this names the return per signal instead of trusting "a solid plane somewhere". Test: on 20 open boards, check whether half-port findings predict RET-COV/RET-VIA failures from the [critic catalog](../../topics/physics/physics-critics-catalog.md).

2. **LA2. Required/observed twin relations** *(sharp, S)*. Every relation exists twice: required in `intent.yaml`, observed in `ledger.json`. Critics are set diffs: "required `returns_through(usb.sstx, ref.l2)`; observed 38% via In3.Cu after the connector". This replaces a flat DRC list with the physical expectation that broke. Test: seeded-fault exams (V3) measure time to root cause with diffs vs DRC lists.

3. **LA3. Designed/parasitic sign flag** *(new, S)*. One set of kinds covers a PCB antenna and an unintended antenna, a shunt trace and a parasitic resistance, a heat spreader and a switch node. `intent: designed` flips the objective and turns a budget into a spec. One ontology means one solver stack. Test: express 10 designed structures (IFA, PCB shunt, spiral inductor, spark gap, guard ring, fuse trace, Rogowski trace, thermal pad, CPWG, Kelvin bar) with no new kinds.

4. **LA4. Node–loop duality typing** *(new, S)*. Type every aggressor and victim by field: dv/dt Node (E-field, capacitive, voltage-driven common mode) or di/dt Loop (B-field, inductive, current-driven common mode). Every operator declares a signed effect on each. A 20 mm² switch-node pour 0.1 mm over a plane is 7.6 pF and 46 mA of displacement current per 6 V/ns edge [C]; "make it wide" helps the loop and hurts the node. Test: on 30 converter layouts, rank measured or simulated near-field EMI with a node-plus-loop score vs area alone.

5. **LA5. Antennas must name two halves** *(sharp, S)*. The grammar refuses "this trace radiates" unless it names two electrically large conductors and the voltage or current between them, following LearnEMC's antenna model ([emc-placement](../../topics/rules/emc-placement.md)) [P]. Candidate antennas are generated for every pair of external port references, heatsinks and shields, each with a V_cm budget (1 mV) or I_cm budget (5 µA, Ott Class B). Test: precision of the identified mechanism, CM-V critic vs free-text LLM EMI review, on 20 boards.

6. **LA6. Common impedance names its shared conductor** *(sharp, S)*. A `common_impedance` coupling must name `shared:`, and the ledger reports R and L of the shared segment from partial elements. For a 24-bit ADC, 20 mA of digital return through the reference must see ≤ 15 µΩ, or 0.031 squares of 1 oz copper [C], which forces a topology change rather than a wider trace. This is the IR form of RG18. Test: re-explain 20 forum ground-loop post-mortems; count correct shared-conductor identifications.

7. **LA7. Current exclusion zones** *(new, M)*. `exclusion(region, of, band, J_frac)` replaces "split the ground". The checker solves the DC/LF current density of the named aggressor loops (sheet-resistance Laplace below f_x) and integrates it over the victim's reference region. Below f_x ≈ R_□/(2πµ0h) (0.31 MHz at h = 0.2 mm [C]) current spreads by resistance, so placement and solid copper can keep it out without the slot that a split creates for fast signals. Test: on 10 mixed-signal designs, compare solid plane plus exclusion against split planes, using a 2D solver for ADC-reference µV and RET-COV for HF nets.

8. **LA8. Sense ports with tap points** *(sharp, S)*. `use: sense` adds `I_through == 0` and a tap point on a body (`R70.1@inner_edge`), compiled to a net tie plus a checker that the tap segment carries no load current. This generalizes Kelvin to FB, remote sense, references and shunts (XD72 gives the computation). Test: 2D solve of tap error vs tap position on 20 shunt footprints; compare with the 10% figure for 0.1 mΩ of solder in a 1 mΩ path [C].

9. **LA9. Cell templates as typed molecules** *(sharp, S)*. One commutation-cell schema (switch pair, HF capacitor, switch node, gate loops, Kelvin points, shunt) covers buck, boost, half-bridge, flyback primary, class D and motor phases, with templates stored as data. XD12 makes the cell the placement unit; this makes it the language unit. Test: encode every topology in the [hot-loop table](../../topics/rules/power/hot-loops.md) with one schema and count special cases.

10. **LA10. Mechanical ports carry EM roles** *(sharp, S)*. Connectors, heatsinks, mounting holes and shield cans are imported from MCAD as fixed ports or bodies. Each also has an electromagnetic role: chassis bonds are where common-mode current leaves, heatsinks are capacitors to chassis (26 pF and 83 mA peaks for a TO-220 tab at 3.2 V/ns [C]). Test: CM-V predictions with and without bond locations on 10 boards with cables.

## B. Quantities, bands, regimes and spectra

11. **LA11. Regime per structure, not per board** *(sharp, S)*. Store the regime per (structure, band) in the ledger, so one net can be in the R regime for its 50 Hz content and the L regime for its edges at the same time. RG2 supplies the dimensionless groups; the IR contribution is attaching them to entities and gating rule packs with `applies_if: {regime}`. Test: count rules whose verdict changes when regimes are per structure instead of per board.

12. **LA12. Band netlists for loop discovery** *(new, S)*. For each band, replace parts by band models: capacitors whose |Z| is below a threshold become shorts, inductors and beads opens, switches both states. The cycles of the resulting graph are the AC loops: hot loops, decoupling loops, gate loops and snubber loops fall out of a cycle basis without hand-written templates. In each band the circuit is a different graph, and the hot loop is a cycle in the HF graph. Test: recover the hot-loop membership table for 30 converters against hand labels.

13. **LA13. Spectra as log-log envelopes** *(sharp, S)*. Store each spectrum as breakpoints: trapezoid corners at 1/(πτ) and 1/(πt_r) plus ring peaks. Store each coupling transfer as an envelope too, so the N² aggressor × victim screen is envelope addition in dB. Test: on 10 cells, screen verdicts from envelopes vs SPICE spectra; count false negatives.

14. **LA14. Spectra as a fixed point** *(new, M)*. Back-annotate excitations from a layout-aware cell model: layout → parasitics → spectrum → budgets → layout, iterated two or three times. A clean 2 ns trapezoid is 90 dB down at 2.45 GHz [C], but switch-node ringing set by L_loop and C_oss dominates there, so frozen schematic spectra miss the real aggressor. Test: track verdict changes across iterations on 10 converter + radio boards.

15. **LA15. Budgets on uncertainty, not value** *(new, S)*. Intervals (`[1.0 pF, 2.2 pF]`) let a budget spend only the *unknown* part. A known crystal stray is absorbed by choosing CL; only uncertainty costs ppm (±0.61 pF for ±17 ppm at 27.7 ppm/pF [C]). The same applies to offset trims and impedance tolerance. Test: crystal layouts with large but well-known strays should pass, where the mm rule fails them.

16. **LA16. Victim sensitivity includes its own rejection** *(sharp, S)*. Thresholds carry the victim's transfer (sinc filter of a sigma-delta ADC, PSRR, CMRR, anti-alias RC), so the in-band threshold is computed. MHz coupling into a 10 SPS ADC is mostly rejected; DC/LF common impedance, heat and alias bands are not. This avoids over-separation that costs area. Test: count couplings dropped or kept on 10 mixed-signal boards; check a sample by simulation.

17. **LA17. Dimensional lint with feedback** *(sharp, S)*. `vo_ir_check.py` catches 12 of 12 seeded errors (half-port, open loop, pF for nH, capacitive coupling from a loop, unknown band, missing shared conductor, unlike dimensions in an expression, alloc > 100%, unknown key, bare numbers) [C]. Run it as a tool the LLM must call before submitting, with errors that name the fix. Test: authoring error rate on 200 LLM-written IR files with and without the loop.

18. **LA18. The LLM writes expressions, never resolved numbers** *(sharp, S)*. `0.85*V_abs(U3.VIN)` and `lambda_g(2.48 GHz, F.Cu)/20` instead of "17 V" and "3.4 mm". A stackup or part change re-derives every bound, which is I2 enforced at the grammar level. Test: change the stackup on 5 boards and count stale numbers in number-written vs expression-written IR.

19. **LA19. Margin in dB as the common currency** *(combo, S)*. Every ledger row reports margin = 20·log10(limit/spent) for amplitudes and 10·log10 for powers, so nH, µV, ppm and K margins can be compared for arbitration (N1 market, N6 ε-tiers). Temperature uses ΔT ratios. Test: on contested regions, compare arbitration quality with hand-tuned weights.

20. **LA20. Band-indexed references** *(new, S)*. A reference serves named bands: an analog reference region serves DC–10 kHz for the ADC; chassis serves the ESD band; the main plane serves everything above f_x. Star, hybrid and multipoint grounding become different band assignments, not different religions. Test: express 10 published grounding schemes as band-indexed references and check each compiles to its known-good layout.

## C. Physics graph and views

21. **LA21. Partial elements as the accounting unit** *(sharp, M)*. Attribute loop-inductance spend to segments with partial self and mutual terms (Paul/Ruehli), and print mutual terms as separate "interaction" rows so sums stay honest: "C10 ESL+pads 0.28 nH, vias 0.19 nH, lateral 0.25 nH, interaction −0.05 nH". Test: compare attribution with FastHenry leave-one-out ablation on 5 hot loops.

22. **LA22. Port macromodels per cell** *(combo, M)*. Kron-reduce the physics graph to each cell's ports per band and emit a passive SPICE subcircuit or Touchstone file; the circuit view then gives V_pk, ringing and PDN impedance. This is the language-level contract for XD28. Test: reduced vs full extraction at 5 frequencies, target < 5% error.

23. **LA23. Named, versioned view transforms** *(new, S)*. `extract`, `reduce`, `expand`, `back_annotate` and `synthesize` are versioned functions, and every ledger number cites the transform and model that produced it. Then "which solver said this?" is always answerable. Test: regenerate the ledger from geometry and compare hashes; diff after a solver upgrade.

24. **LA24. Field tiles for the LLM and VLM** *(combo, M)*. Per-band raster maps of J, near-field B_z, E and T at fixed resolution with entity-id overlays, as a compact image channel, so the agent can ask "where is J > 1% of the digital return in AGND?". Test: seeded-fault exam accuracy of the VLM judge with field tiles vs plain renders (U5/V3 protocol).

25. **LA25. Halos as derived geometry** *(sharp, S)*. A halo is a contour around an aggressor, per victim class, where the coupling budget is met; it compiles to a rule area and placer repulsion and is drawn as a glyph. RG53 and XD68 compute the distance; including the plane image matters, since coupling at 10 mm drops from 20 pH (free space) to 0.036 pH over a plane 0.1 mm away [C]. Test: compare halo conflicts with "20 mm from the SMPS" conflicts on 10 boards.

26. **LA26. Moment with image replaces loop area** *(new, S)*. Budget a loop's effective magnetic moment (I·A including its plane image) and report its multipole order. Coupling falls as about 1/r⁵ over a close plane instead of 1/r³ [C], and "fold" and "cancel" operators change the order. Test: rank 30 hot-loop layouts by moment, by area and by openEMS near-field; compare rank correlation.

27. **LA27. Operator previews from low-rank updates** *(combo, M)*. Each candidate operator shows a predicted Δmargin computed by an adjoint or low-rank update of the reduced model in milliseconds (XD51 gives the maths), so the LLM menu is priced before anything moves. Test: prediction error against a full re-extraction on 100 operator applications.

28. **LA28. One electrothermal graph** *(combo, M)*. Thermal conductances share bodies with the electrical graph and are coupled through I²R. `widen_to_pour` then reports ΔR and ΔT together, and thermal-EMF couplings use the same temperatures. RG50 covers the checks. Test: compare ΔT with Elmer on 5 power boards.

29. **LA29. Physics digest for context** *(new, S)*. Summarize a board for the LLM as entities plus the top ledger rows in at most 2k tokens ("18 loops, 3 over budget; 7 couplings, 1 over; 2 antennas"), never as copper. Test: repair success and tokens with the digest vs a geometry dump, on 30 repair tasks.

## D. Operators

30. **LA30. Operator sensitivity cards** *(new, S)*. Each operator has a card: affected budgets, sign, magnitude model, cost (area, vias, fab class) and preconditions. The LLM picks from a menu ranked by Δmargin per cost instead of editing geometry. Test: S5-style refactoring tasks with cards vs free-form operator choice; success and regressions.

31. **LA31. Refuse net-negative operators** *(sharp, S)*. Because effects are signed per budget (LA4), the menu hides operators whose net effect is negative across the budgets they touch, for example widening a body that is mostly a switch node. Test: count harmful applications prevented in logged LLM repair loops.

32. **LA32. Off-board operators** *(new, S)*. `slow_edge`, `thin_dielectric`, `swap_package` (lower ESL), `swap_pins` and `move_frequency` let the agent propose a schematic or stackup change. AN-139's loop measured 23 nH over a plane 0.5 mm away and 13 nH at 0.12 mm [P], a gain few copper edits match. Test: share of over-budget cases whose best fix by Δmargin per cost is off-board.

33. **LA33. Kelvin by construction** *(sharp, S)*. `kelvin_tap` compiles to a KiCad net-tie footprint at the tap point, a "K" glyph and a checker that J on the sense path is zero. This makes TI's net-tie advice ([current-sense-kelvin](../../topics/rules/power/current-sense-kelvin.md)) the default output, not a manual trick. Test: tap-error estimates on 20 shunt boards before and after.

34. **LA34. `split_band` operator** *(new, S)*. Produce a DC tie (net tie) plus HF capacitor sites for a band-split reference, with the crossover frequency as the only parameter. Test: simulate noise for 5 analog/digital ground cases against a single plane and a hard split.

35. **LA35. `cancel` operator** *(new, M)*. Split a loop into counter-rotating halves (two input capacitors on either side of a switch pair) so the far field becomes quadrupole. XD11 explores figure-8 loops; the operator makes it a one-word choice with a predicted moment. Test: dipole sums from `vo_numbers.py` and openEMS near-field on 3 GaN cells.

36. **LA36. `void` as a designed discontinuity** *(sharp, S)*. Planned plane cut-outs under RF match pads, AC-coupling cap pads and TIA IN− carry a purpose and a budget. An 0402 pad 0.1 mm over a plane is 0.11 pF, worth −27 dB of |S11| by itself at 2.45 GHz [C]; critics then stop flagging the void as a return-path defect. Test: false RET-COV findings removed on 10 RF and high-speed boards.

37. **LA37. Operator scripts with physics postconditions** *(sharp, S)*. S5 refactorings gain a postcondition: protected budgets may not lose margin, else the whole script rolls back. Test: "move the USB block to the other edge" tasks with and without postconditions.

## E. LLM interface and authoring

38. **LA38. Datasheet prose → entities** *(combo, S)*. Extraction prompts target typed entities, not millimetres. "Keep the loop formed by CIN, Q1 and Q2 small" becomes a commutation loop with members and a V_pk budget; "place the feedback divider close to the FB pin" becomes a sense port and a capacitive coupling budget. Test: 50 datasheet layout sections; entity precision and recall against expert labels, and the mm-hallucination rate.

39. **LA39. Mechanism hypotheses as the LLM's main write** *(new, S)*. The LLM adds what the screen cannot see: "the heatsink is a capacitor to chassis", "the TC connector makes a thermocouple with board copper", "the cable shield bonds at J4, not J1". Each is a Coupling or Antenna entity with mechanism and band; code quantifies it. Test: on published failure post-mortems, count failures the automatic screen misses but LLM hypotheses catch.

40. **LA40. Questions ranked by ∂margin/∂unknown** *(combo, S)*. Unknown spectra and sensitivities generate questions ordered by how much the answer can move a margin, implementing U3 with physics. For example, "gate-driver sink current?" sets di/dt and therefore the hot-loop V_pk margin. Test: compare the generated question order with an expert's on 10 briefs.

41. **LA41. Slogan-to-entity translator** *(sharp, S)*. When a user or source writes a slogan ("keep away", "3W", "solid ground", "short and wide"), propose the entity that encodes it, with derived numbers, and ask for confirmation. RG49 detects slogans in LLM output; this converts them on input. Test: time to encode intent and errors, in a user study.

42. **LA42. Physical-unit intent diffs** *(sharp, S)*. Extend I6: diffs report entity and margin changes in units ("buck1.hot V_pk margin −4 dB; new antenna J1↔J4"). Test: the I6 seeded-regression protocol.

43. **LA43. Stable entity ids across ECOs** *(sharp, S)*. Derive ids from cell, template and role (`buck1.hot`, `usb.sstx.t_conn`), not refdes, so they survive re-annotation and part swaps. Test: id survival rate after re-annotation and 10 refactorings.

## F. Human and visual

44. **LA44. Glyph language from the ledger** *(sharp, S)*. Loop polygons filled by budget use, return ghosts per band, node halos, coupling springs lettered by mechanism, port dot pairs, antenna halves, "K" taps and budget bars, drawn from the observed graph with ids shared with the text ([vocabulary § visual](../../topics/physics/vocabulary.md#visual-vocabulary-board-view-and-vlm-renders)). RG48 renders return current; this fixes the symbol set around it. Test: designer comprehension test and VLM judge accuracy on seeded faults.

45. **LA45. Spender bars** *(sharp, S)*. Each budget is a stacked bar split by the objects that spend it, and clicking a segment selects the object on the board. Test: time for a reviewer to find the dominant spender, with bars vs a tabular report.

46. **LA46. Sketch-to-entity** *(combo, M)*. Extend U6: the user lassos a loop, draws a spring between two parts or circles a region, and the system proposes the entity (loop, coupling, exclusion) with derived budgets. Test: entity entry time and accuracy against YAML authoring.

47. **LA47. Entity cursor** *(new, S)*. Hovering any copper object lists the entities it belongs to and its spend share in each ("this via: 19% of buck1.hot L; 0% elsewhere"). Test: reviewer task success on "is this via safe to move?".

## G. Compilation and verification

48. **LA48. Six-target compiler with proxy tags** *(sharp, M)*. Each entity compiles to KiCad objects, DRU rules, placer terms, router costs, critics and solver decks. DRU rules that only approximate a budget carry their derivation (I2) and the ledger records which target produced the verdict. Test: rate of disagreement between DRU proxies and critics on 20 boards.

49. **LA49. FastHenry and FasterCap decks from entities** *(sharp, S)*. A loop becomes a FastHenry deck cut at its decoupling capacitor with `.External` across the cut; nodes become FasterCap conductors. Solver ports and IR ports are the same terminal pairs, so the half-port rule is shared. Test: 5 EVM hot loops against published nH (SNVA803, EPC).

50. **LA50. Entity stamps in the board file** *(sharp, S)*. Extend I7: component classes `loop:<id>`, rule areas `IR:<id>`, net ties for sense ports and glyph outlines on a User layer. Test: delete the sidecar and measure how many entities are rebuilt from stamps.

51. **LA51. Mutants per entity kind** *(sharp, S)*. V1 by kind: break a return, add a via to a hot loop, move a Kelvin tap, bridge a barrier, add copper inside an antenna keep-out. Each critic must kill its kind's mutants. Test: mutation score per entity kind.

52. **LA52. Physics IR as a dataset format** *(new, M)*. Extract entities and observed ledgers from open boards to build priors ("achieved L_loop for 1 MHz, 3 A bucks: median X nH") that default budgets and calibrate spend models ([measured-priors](../../topics/data/measured-priors.md)). Test: extract on 100 boards and report the spread per cell type.
