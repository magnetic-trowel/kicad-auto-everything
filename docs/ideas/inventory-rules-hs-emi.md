# Idea inventory: high-speed, SI, EMC, stackup and interface rules

Scope: one line per idea from the high-speed/EMC/interface rule notes; detail and sources in the linked topic doc. Not here: power/RF/analog/DFM rules -> [inventory-rules-power](inventory-rules-power.md).
Keys: return path, crosstalk, stub, termination, stackup, diff pair, skew, interface pack, USB, PCIe, DDR, Ethernet, MIPI, crystal, EMC placement, MREMC, checkers A-I, rule tiers
Pointer tags = rule docs: [emc](../topics/rules/emc-placement.md), [checkers](../topics/rules/checkers-si-emi.md), [si](../topics/rules/si-fundamentals.md), [format](../topics/rules/rule-pack-format.md), [diff](../topics/rules/diff-pairs.md), [stackup](../topics/rules/stackup.md), [myths](../topics/rules/myths-and-contested.md), [clocks](../topics/rules/crystals-clocks.md), [dfm](../topics/rules/dfm-fab-limits.md), [buck](../topics/rules/power/buck.md), [pcie](../topics/rules/interfaces/pcie.md), [ddr](../topics/rules/interfaces/ddr.md), [usb3](../topics/rules/interfaces/usb3-usb4-typec.md), [eth](../topics/rules/interfaces/ethernet.md), [usb2](../topics/rules/interfaces/usb2.md), [sata](../topics/rules/interfaces/sata-ufs-sd.md), [mipi](../topics/rules/interfaces/mipi.md), [i2c](../topics/rules/interfaces/i2c-spi-qspi.md), [hdmi-dp](../topics/rules/interfaces/hdmi-dp.md), [can](../topics/rules/interfaces/can-rs485.md).
Source tags: [HS] `rules_highspeed_emi.md`, [IF] `interface_rule_packs.md`, [VR] `verification_rules.md` (research notes).

## Physics and modelling
1. Encode physics, not slogans; store myths as negative rules with the check that replaces them [HS] [myths]
2. Return current flows directly under the trace, so every fast net needs a continuous reference plane [HS] [si]
3. The ±1h/±3h/±10h return spread justifies edge and void offsets (1.5W ≈ 3h only at 50 Ω single-ended widths) [HS] [si]
4. A via passing through the same plane is not a discontinuity; don't flag it [HS] [si]
5. Merge antipads into void polygons and measure slot length perpendicular to the trace [HS] [checkers]
6. Use Ott's 4-level layer-change order as the router's policy [HS] [si]
7. Place return vias within 200 mil, tightened with data rate (~5 / 2.5 / 1.3 mm) [HS][IF] [si]
8. Use stitching caps (≤1 µF) only at unavoidable split crossings; "1–10 nF within 50 mil" is not primary [VR] [si]
9. Avoid power-plane references; never overlap planes that do not reference each other [HS] [si]
10. On boards with planes, use no ground traces or fill; connect grounds with direct vias [HS] [si]
11. Aim for a 10:1 signal:ground via ratio for 0.063" vias at about 500 ps edges (Johnson's 3-D scaling); SerDes pairs use the vendor return-via rules [HS] [si]
12. Differential pairs return under each leg, so apply the return-path rules to each leg [HS] [diff]
13. Skew becomes common mode: 20% skew gives 10% CM (Johnson) [HS] [diff]
14. Critical length: flag for SI review at t_r/6; terminate at t_r/2 (contested) [HS][VR] [si]
15. Slow edges first; default to a series R; target a transition time of ≈20% of the UI [HS] [si]
16. Choose termination values that minimise harmonic current, not ones that merely look good in voltage (Archambeault) [HS] [si]
17. Stub limit = min(15 mil, 0.3/Gbps in) on SerDes ≳3 Gb/s, counting the pad rings [HS][VR] [si]
18. Decide the stub strategy (backdrill, near-outer layers, blind vias) before the stackup [HS] [stackup]
19. Enter connector pads from the non-stub end; enter TH receptacles from the bottom [HS][VR] [si]
20. Model crosstalk with Johnson's K = 1/(1+(D/H)²), with saturation and a sum over aggressors [HS] [si]
21. Set spacing from a crosstalk budget: D ≥ H·√(1/K−1) [HS] [si]
22. Reduce crosstalk through lower h (the stackup) before adding spacing [HS] [stackup]
23. Guard traces only in stripline, end-shorted and length-matched; never in microstrip [VR] [myths]
24. Apply stricter crosstalk budgets to I/O and analog victims [HS] [si]
25. Route adjacent signal layers orthogonally [VR] [si]
26. Use LearnEMC's three-condition antenna model, with 1 mV (or 100 µV) between antenna parts as the limit [HS] [emc]
27. Use the MREMC algorithm as a computable common-mode EMI estimator [HS] [emc]
28. Use Ott's DM and CM radiation formulas and his 5/15 µA cable-current limits [HS] [emc]
29. Use the FCC 15.109 limits as the target for E_max [HS] [emc]
30. Cross-check consistency between 1 mV, 3.6 µA and the Class B limit [HS] [emc]
31. Use the cavity-resonance formula for the stitching checker [HS] [checkers]
32. Never use a spread-spectrum clock as a reference for transceivers, PLLs or RF [HS] [clocks]
33. Treat every pin of a fast IC as a potential HF source [HS] [emc]

## Stackup
34. Ott's four factors and five objectives; 8 layers is the minimum that meets all five with more than two routing layers [HS] [stackup]
35. A candidate stackup library for 4/6/8/10 layers [HS] [stackup]
36. An 8-step stackup selection and scoring algorithm [HS] [stackup]
37. Encode the Ott-vs-Hartley 6-layer disagreement as a warning with rationale [HS] [stackup]
38. Penalise forced P↔G reference changes in the stackup score [HS] [stackup]
39. Use a plane pair <0.25 mm apart when ≥3 power pins share a rail [HS] [stackup]
40. Put power planes on one layer, with gap ≥ the plane-to-ground spacing (≥3 mm "maybe") [HS][VR] [stackup]
41. Choose the stackup before placement [HS] [stackup]
42. Microstrip vs stripline for HS pairs is a context switch [VR] [myths]
43. Mitigate fibre weave with 10–35° rotation or zig-zag routing [VR] [stackup]
44. Ott's impedance and delay rules of thumb as a fallback when no field solver is available [HS] [stackup]
45. Fab stack and material data (OSH Park, JLC Dk) as stackup inputs [IF][VR] [stackup]

## Differential pairs
46. skew_max = min(spec, 0.1·t_r), converted with the per-layer delay [HS] [diff]
47. Running-skew compensation near the mismatch, not only at the end of the route [HS] [diff]
48. Place ICs so pairs exit and enter in the same direction [HS] [diff]
49. Serpentine switchbacks ≪ ⅓ t_r or uncoupled; jogs ≥3W; spread <2S [HS][VR] [diff]
50. Coupling tighter than 0.5 mm buys no extra EMI; choose the gap for Zdiff and density [HS] [diff]
51. GND vias pinning the planes at each differential via (XFP pattern) [HS] [diff]
52. Absolute keep-outs on high-speed interface pairs (TI scope): 30 mil to other signals, 50 mil to clocks [VR] [diff]
53. Uncoupled length ≤45 mil; breakout within 0.25 in [VR] [diff]
54. Equal via counts on both legs; via limits scoped to the device family [VR] [diff]
55. 30 mil antipads; no non-functional pads [VR] [diff]
56. Symmetric 0402 in-line parts with 100%, 2-layer-deep pad voids [VR][IF] [diff]
57. Bends >135°, with balanced left and right turns [VR][IF] [diff]
58. KiCad pair-to-pair clearance condition `A.inDiffPair('*') && !AB.isCoupledDiffPair()` [HS] [diff]

## Interface packs
59. Vendor profiles are mandatory; when the vendor is unknown, use the tightest [P] value plus an info finding (policy under review; two-sided windows intersect, and an empty intersection asks) [IF] [format]
60. USB in-line order: connector → ESD → CMC → AC cap → PHY [IF] [usb3]
61. Keep Qualcomm's 5 ps USB3 skew as the "physics-justified relaxed" option [IF] [usb3]
62. Charge each via ~25–50 mm of equivalent length in the SerDes cost model [IF] [pcie]
63. Charge ESD+CMC ≈1 in of equivalent length [IF] [usb3]
64. Resolve the USB shield-termination conflict by asking the user [IF] [usb2]
65. USB2 worked pack: YAML with DRU, geometric and BOM checks [IF] [usb2]
66. Type-C CC: width, capacitance window, no series passives [IF] [usb3]
67. Compute PCIe L_max from the loss budget and material tables, not a stored mm value [IF] [pcie]
68. AC cap near either endpoint; never mid-line or staggered [IF] [pcie]
69. A 176–220 nF BOM window is universally safe for PCIe Gen3+ [IF] [pcie]
70. Edge-finger inner-layer keep-outs (0.381 mm; planes ≤2 mm into the finger area) [IF] [pcie]
71. Emit lane-to-lane matching only when the device demands it [IF] [pcie]
72. DDR: one `fromTo` rule per SDRAM per group [IF] [ddr]
73. Never emit cross-byte DDR skew rules [IF] [ddr]
74. Derate to 20% of each limit as `opt`, keep the full limit as `max`, then verify with IBIS PVT [IF] [ddr]
75. Default skew budget: Micron's 1% of the clock period, scaled with the clock [IF] [ddr]
76. Use the stackup delay model, not a single ps/mm constant [IF] [ddr]
77. Ethernet PHY↔magnetics as a soft window (~25 mm target; error >76 mm) [IF] [eth]
78. Ethernet ESD location (PHY side vs connector side) as a pack parameter [IF] [eth]
79. Chassis island and Bob Smith geometry as clearance rules [IF] [eth]
80. Store UI-based skew budgets as formulas, resolved at the data rate [IF] [hdmi-dp]
81. D-PHY length-vs-rate table with a `cable_il_db` input [IF] [mipi]
82. A loose-coupling flag for MIPI pairs [IF] [mipi]
83. SATA polarity swap is controller-dependent; make it a profile flag [IF] [sata]
84. CAN/RS-485: termination only at end nodes; protection in the signal path [IF] [can]
85. I2C pull-up window computed from stackup capacitance plus pins [IF] [i2c]
86. SD CLK↔data matching; series R at the source [IF] [sata]
87. Slow multi-drop clock limits: star branch Δ <30 mm; daisy-chain stub <7 mm [IF] [i2c]
88. Crystal placement as an annulus (vendor minimum to 12 mm) [IF] [clocks]
89. Score crystal parasitic capacitance from trace length × C′ [IF] [clocks]
90. Crystal metal-can, under-crystal copper and guard-tie conflicts as vendor switches [IF] [clocks]
91. A C-shaped GND-via ring at clock and RF transitions [IF] [clocks]
92. Buck pack: Cin <2 mm, loop-area tiers, L estimate → overshoot (power cluster) [IF] [buck]
93. Inductance anchors make "minimise the loop" a scoreable objective [IF] [buck]
94. Datasheet reference-layout override at precedence 40 [IF] [format]
95. Fab and safety minimums are floors applied after resolution (effective_min = max(resolved, fab, safety)), not precedence ranks [IF] [format], [dfm]
96. Mounting-hole keep-out derived from the screw head + margin (RP2040: 6 mm) [IF] [dfm]

## EMC placement
97. Cluster cabled connectors on one edge or corner [HS] [emc]
98. No HS circuitry between connectors, scored with MREMC [HS] [emc]
99. 2 cm I/O-zone defaults (device ≤2 cm from its connector; other parts ≥2 cm away) [HS][VR] [emc]
100. A clear I/O corridor; no HF under I/O parts [HS] [emc]
101. I/O nets end in a series or filter part near the connector [HS] [emc]
102. TVS topology as comparative constraints rather than mm values [VR] [emc]
103. TVS GND via immediately adjacent; ESD-path corners ≤45° (2.6 mm arc radius) [VR] [emc]
104. On the ESD path, the via comes only after the TVS (Case 1) [VR] [emc]
105. CMC within ~5 mm of the connector as a soft target [VR] [emc]
106. Edge rules: 90 mil from the plane edge (HS differential pairs, TI), 2X from the board edge, 3W [VR] [emc]
107. Check plane-edge offset against zone boundaries; `edge_clearance` does not cover it [VR][IF] [emc]
108. A largest-unstitched-region metric reconciles the perimeter-vs-distributed stitching debate [HS] [checkers]
109. Split-boundary stitching every 10–15 mm (soft) [VR] [emc]
110. Chassis bond: overlapping layer + SMT caps + one low-frequency tie [HS] [emc]
111. One partitioned ground; for ≥14-bit converters, isolated regions joined under the ADC [HS] [emc]
112. Check the 300 mV inter-plane limit only when a split is deliberate [VR] [emc]
113. Optional filter, TVS and shield footprints when compliance is uncertain [HS] [emc]
114. Two EMC design reviews: before layout and at the first draft [HS] [emc]
115. Visualise the current path of each compliance test [HS] [emc]
116. Clamp-measure the common-mode current on every cable [HS] [emc]
117. Ott's red flags as a lint list; invert his "maximize emission" list [HS] [emc]
118. emcvisual's placement thresholds for crystals, inductors and switch nodes [HS] [emc]
119. A 7-step placement priority order (steps 1–3 hard, 4–6 soft) [HS] [emc]
120. Placer cost terms: V_cm, I/O intrusion, length, crossings, direction alignment [HS] [emc]
121. Power stages: minimal switch-node area, MHz switching, no isolated power grounds [HS][VR] [emc]

## Classification and verification
122. Rule tiers: hard / soft-strong / soft-weak / context switch [VR] [format]
123. Blog-sourced mm values become rank objectives, never DRC errors [VR] [format]
124. Add `source_scope`, `statement_strength` and `contested_by` fields [VR] [format]
125. The LLM turns relative source wording into comparative constraints [VR] [format]
126. Severity recalibrations (TL-5, EMI-7, EMI-6, RF-05) [VR] [format]
127. Corner-angle rule scoped to ESD and RF net classes, differential pairs and nets ≥10 Gb/s [VR] [myths]
128. Contested rules are never defaults; store both variants plus a selector [VR] [myths]
129. Montrose's conditions serve as the 20-H selector [VR] [myths]
130. Store part-specific numbers (Espressif, u-blox) per part, not as general rules [VR] [format]

## Encoding and checkers
131. KiCad 10 ps-domain constraints and `fromTo` paths for DDR and SerDes [HS][IF] [checkers]
132. Emit KiCad master `return_path` and `stub_length` when available [HS] [checkers]
133. Checker A: reference-layer map from the stackup plus fills [HS] [checkers]
134. Checker B: return continuity with an A* detour; VOID/ISLAND/SPLIT [HS] [checkers]
135. Checker C: reference change → nearby via or capacitor [HS] [checkers]
136. Checker D: loop-area ranking with Ott's DM formula [HS] [checkers]
137. Checker E: crosstalk extraction by spatial hash [HS] [checkers]
138. Checker F: connector clustering and between-ness via MREMC [HS] [checkers]
139. Checker G: largest empty circle vs cavity resonance and λ/20 [HS] [checkers]
140. Checker H: via-stub length and resonant frequency [HS] [checkers]
141. Checker I: protection topology, islands, edge-rate ratio, I/O corridor [HS] [checkers]
142. Interface-pack geometric functions: path order, offset coverage, distance windows, loop L, trace C [IF] [checkers]
143. Report through an HTML/JSON overlay, since IPC cannot create persistent DRC markers [HS] [checkers]
144. Parse the stackup from `.kicad_pcb`, or use IPC `get_stackup` [HS] [checkers]
145. Use KiCad master's via-stitch GUARD generator for via fences [HS] [checkers]
146. Licence gating: reuse MIT, 0BSD and GPL-3.0 checkers; unlicensed and non-commercial ones are reference-only [HS] [checkers]
147. Rank findings by consequence (risk score, far-field share) [HS] [checkers]
148. Expert-system framing (source/path/antenna) rather than full simulation [HS] [checkers]
149. Closing the loop (generate constraints → route → physics-check) is an unoccupied niche [HS] [checkers]

## Format and knowledge base
150. Five-part rule definition: match, typed parameters, provenance and precedence, backend, placement intent [IF] [format]
151. YAML pack schema with `by_vendor`, `conflicts` and `resolution` [IF] [format]
152. Resolution policy: [S] never overrides [P]; [D]/[I] values default to warning [IF] [format]
153. Knowledge-base record schema with `basis` (h, λ, fraction of t_r) [HS] [format]
154. Net classification: regex seeds → LLM pin/datasheet confirmation → user overrides [HS] [checkers]
155. Assign each net a t_r, flagged as an assumption when estimated [HS] [si]
156. Calibrate [I] heuristics against vendor evaluation-board layouts [IF] [format]
157. Test the emitted DRU syntax on the installed KiCad [IF] [format]

[checkers]: ../topics/rules/checkers-si-emi.md
[clocks]: ../topics/rules/crystals-clocks.md
[dfm]: ../topics/rules/dfm-fab-limits.md
[diff]: ../topics/rules/diff-pairs.md
[emc]: ../topics/rules/emc-placement.md
[can]: ../topics/rules/interfaces/can-rs485.md
[ddr]: ../topics/rules/interfaces/ddr.md
[eth]: ../topics/rules/interfaces/ethernet.md
[hdmi-dp]: ../topics/rules/interfaces/hdmi-dp.md
[i2c]: ../topics/rules/interfaces/i2c-spi-qspi.md
[mipi]: ../topics/rules/interfaces/mipi.md
[pcie]: ../topics/rules/interfaces/pcie.md
[sata]: ../topics/rules/interfaces/sata-ufs-sd.md
[usb2]: ../topics/rules/interfaces/usb2.md
[usb3]: ../topics/rules/interfaces/usb3-usb4-typec.md
[myths]: ../topics/rules/myths-and-contested.md
[buck]: ../topics/rules/power/buck.md
[format]: ../topics/rules/rule-pack-format.md
[si]: ../topics/rules/si-fundamentals.md
[stackup]: ../topics/rules/stackup.md
