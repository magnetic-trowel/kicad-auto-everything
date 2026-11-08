# DFM, DFA and fab limits

Scope: canonical home for fab profiles (JLCPCB, PCBWay, OSH Park, Eurocircuits), copper-weight minimums, courtyards, tombstoning, fiducials, test points, depaneling, orientation/silk, mounting holes, DFM rule IDs. Not here: floor semantics -> [rule-pack-format.md](rule-pack-format.md#rule-pack-requirements); HV spacing -> [isolation-creepage.md](isolation-creepage.md); current capacity -> [power/high-current.md](power/high-current.md).
Keys: DFM, DFA, fab limits, JLCPCB, PCBWay, OSH Park, Eurocircuits, trace/space, annular ring, drill, V-cut, mouse bite, castellation, panel, copper weight, courtyard, IPC-7351 Level B, tombstoning, fiducial, SMEMA 7.62 mm, test point, flying probe, depaneling, MLCC crack, mounting hole, ISO 273, DFM-01, DFM-12

## DFM rules
1. DRC minimums = fab absolute limits; router targets = fab recommended + margin. Fab-profile packs set `min` only, `recommended` as router `opt`. They are floors applied after resolution, not a precedence rank: no interface, vendor or datasheet pack can relax them ([rule-pack-format.md](rule-pack-format.md#rule-pack-requirements)); also written into Board Setup → Constraints.
2. Most limits are native KiCad constraints (`track_width`, `clearance`, `hole_size`, `annular_width`, `edge_clearance`, `hole_to_hole`, `text_height`, `text_thickness`, `silk_clearance`, `courtyard_clearance`); Python checks for tombstone symmetry, fiducial and test-point coverage, part-class edge/V-score distances.
3. Copper-weight choice feeds pad-gap checks ([power/high-current.md](power/high-current.md), HC-03).
4. Corrected assembly numbers: fiducial edge distance = SMEMA 7.62 mm + clearance on own-edge conveying, else the assembler's rail spec (not "≥5 mm"); test pads 1.0 mm from components (not 2.5 mm); silk ≥1.0 mm text / 0.15 mm line (CORRECTED).
5. Mounting-hole keep-outs have no standard: screw head + margin; RP2040 reference 6 mm around a 2.75 mm hole.

## Fab profiles
Official pages read 2026-10-20; compiled in [interface_rule_packs.md § 10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)) [P]:

| Parameter | JLCPCB 2L (rec / abs) | JLCPCB ML (rec / abs) | PCBWay std | OSH Park 2L | OSH Park 4L | KiCad check |
|---|---|---|---|---|---|---|
| Trace / space (1 oz) | 0.10 / 0.10 mm | 0.09 / 0.09 mm (3 mil in BGA fan-outs) | 0.10 / 0.10 mm | 0.152 mm | 0.127 mm | `track_width`, `clearance` |
| Min drill | 0.2 pref / 0.15 mm | same | 0.15 mm (≥0.2 no surcharge) | 0.254 mm | 0.254 mm | `hole_size` |
| Annular ring | 0.25 / 0.18 mm | 0.20 / 0.15 mm | 0.15 mm | 0.127 mm | 0.102 mm | `annular_width` |
| Copper to routed edge | 0.2 mm | 0.2 mm | 0.20–0.25 mm | 0.381 mm | 0.381 mm | `edge_clearance` |
| Copper to V-cut | 0.4 mm | 0.4 mm | — | — | — | `edge_clearance` |
| Hole to hole | 0.2 via / 0.45 pad | same | table | 0.127 rec | 0.127 rec | `hole_to_hole` |
| Silk line / text | ≥0.15 / ≥1.0 mm | same | ≥0.15 / ≥0.8 mm (1:5) | 0.127 (0.076) mm | same | `text_thickness`, `text_height` |
| Pad-to-silk | 0.15 mm | 0.15 mm | — | — | — | `silk_clearance` |
| Mask bridge | 0.10 (green) / 0.13 mm (black/white) | same | 4 mil class | — | — | DRC |
| Impedance tol. | ±10% (±5% on request) | same | ±10% (±5 Ω ≤50 Ω) | — | — | — |

Sources: [JLCPCB PCB](https://jlcpcb.com/capabilities/pcb-capabilities); [JLCPCB assembly](https://jlcpcb.com/capabilities/pcb-assembly-capabilities); [PCBWay](https://www.pcbway.com/capabilities.html); [OSH Park 2L](https://docs.oshpark.com/services/two-layer/), [4L](https://docs.oshpark.com/services/four-layer/); [Eurocircuits](https://www.eurocircuits.com/pcb-design-guidelines-classification/).

**Fab classes for suggested relaxations** (pages read 2026-11-03; table `PROFILES` in `kae/src/kae/route/fab.py`). kae's diagnoses (BGA escape certificates, `kae.route.blocked`) suggest rule relaxations to the commanding LLM. Each suggestion is clipped at the board's fab's finest class and labelled with the cheapest class that builds it; anything beyond *standard* is a manufacturing hazard (warn) that names the cost. The fab is the board's `KAE_FAB` text variable or `--set fab=` (default `jlcpcb`); `opts["fab_profiles"]` adds profiles. Values in mm, 1 oz, multilayer (2-layer in brackets where it differs):

| Fab, class | Track / space | Pad to track | Via (diameter / drill) | Via-in-pad | Cost, per the fab |
|---|---|---|---|---|---|
| JLCPCB standard | 0.09 / 0.09 (0.10) | 0.10 | 0.45 / 0.20 | from 6 layers | none ("0.2mm or 0.25mm hole size with via diameter less than 0.45mm … will cost more") |
| JLCPCB advanced | 0.076 / 0.076 ("3 mil is acceptable in BGA fan-outs"; 0.10 on 2 layers) | 0.09 ("min. 0.09 mm for multilayer boards") | 0.25 / 0.15 | yes, filled and capped | surcharge |
| JLCPCB HDI | 0.069 / 0.069 ("Extreme capability: 2.7 mil"; 3 mil standard HDI) | 0.076 [I] | 0.20 / 0.10 (≤1 mm boards, ENIG/OSP; or laser blind vias 0.075–0.15 mm) | yes | "may increase both cost and production time" |
| PCBWay standard / advanced | 0.10 / 0.10 | 0.10 [I] | 0.50 / 0.20; 0.45 / 0.15 with a surcharge (ring 0.15) | advanced | surcharge below 0.2 mm drill |
| OSH Park 4L (2L) | 0.127 (0.152) | same [I] | 0.458 / 0.254 (0.508 / 0.254) | no | standard only |

Sources: [JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) (incl. its HDI section); [JLCPCB BGA design guidelines](https://jlcpcb.com/help/article/bga-design-guidelines---pcb-layout-recommendations-for-bga-packages) (trace-to-BGA-pad 0.10 mm on 2 and 4 layers, 0.076 mm "on some traces", via-in-pad free on 6–20 layers); [JLCPCB POFV](https://jlcpcb.com/blog/Free-Via-in-Pad-on-6-20-Layer-PCBs-with-POFV); [PCBWay capabilities](https://www.pcbway.com/capabilities.html) (its advanced table grades 3–3.5 mil as medium/high difficulty without one number per class, so kae lists no PCBWay HDI class); OSH Park as above. **Conflict:** JLCPCB's capabilities page allows 0.09 mm pad-to-track at BGAs on multilayer boards, its BGA guideline says 0.10 mm; kae calls 0.10 standard and 0.09 advanced. Eurocircuits' pattern and drill classes are an image on its page and were not read.

## JLCPCB detail
Incl. V-cut, castellation and panel geometry; [interface_rule_packs.md § 10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)) [P]:
- **Copper weight → min track/space:** 2 oz 0.16 (2L) / 0.15 mm (ML); 2.5 oz 0.20; 3.5 oz 0.25; 4.5 oz 0.30 mm (2L only). Available weights: 2L 1/2/2.5/3.5/4.5 oz; ML outer 1–2 oz, inner 0.5 oz default.
- **Tolerances:** track width ±20%. PTH annular ring at 2 oz ≥0.254 mm; NPTH ring ≥0.45 mm.
- **Vias:** ≥0.15 mm hole / 0.25 mm diameter (0.1/0.2 only for ≤1 mm boards with ENIG/OSP); diameter = hole + 0.1 (0.15 preferred); "Preferred Min. Via hole size: 0.2mm". Drill range 0.15–6.3 mm.
- **Clearances:**
  - pad-to-track 0.1 (0.09 at BGA); SMD pad-to-pad (different nets) 0.15 mm; min SMD pad 0.25 × 0.25;
  - via-to-track 0.2; PTH-to-track 0.28 (0.35 recommended); NPTH-to-track 0.2;
  - inner via-to-copper 0.2; inner PTH-to-copper 0.3.
- **Vias in BGA pads must be filled and plated over.** Plugged vias ≤0.5 mm, ≥0.35 mm from openings.
- **Outline:** routed edge ±0.2 mm (±0.1 precision); V-cut ±0.4 mm at 25° (boards ≥0.6 mm); V-cuts ≥2 mm apart (3 mm recommended); boards ≥2 mm apart.
- **Panels:** mouse-bite spacing 1.6 or 2 mm; min tooling edge 3 mm. SMT panels: 5 mm rails, 2 mm tooling holes, 1 mm fiducials 3.85 mm from the panel edges.
- **Castellations** ≥0.5 mm, 1 mm from the edge.
- **Materials:** FR-4 Dk 4.5 (2L), 7628 4.4, 3313 4.1, 2116 4.16. Backdrill on 4–32 layers, ≥0.8 mm thick.
- **Assembly:** min IC pitch 0.35 mm (standard) / 0.40 mm (economic); BGA pitch 0.3/0.5 mm; 01005 supported; recommended max panel 250 × 250 mm. Part-to-outline 0.2 (routed) / 0.4 mm (V-cut) per a support reply [S].

## Other fabs
[P]
- PCBWay: PTH hole tolerance ±0.08 / NPTH ±0.05 mm; half-holes ≥0.4 mm; panel spacing 1.6 mm (routing) / 0 (V-score); line-to-edge 0.25/0.20 mm (CNC).
- OSH Park 2L: edge keep-out 15 mil; drill tolerance ±2.5 mil; no blind, buried or filled vias. 4L: FR408HR, L1–L2 prepreg 7.87 mil, core 39 mil.
- Eurocircuits: inner pad isolation = IAR + 0.075 (≥0.200 mm); connected NPTH ring ≥0.30 mm.
- Third-party blog numbers (e.g. "5 mil") lose to official pages.

## Courtyards and spacing
- IPC-7351 courtyard excess per side: Level A (most) ≈0.50, **B (nominal) 0.25**, C (least) ≈0.10 mm. Density levels are solder-fillet goals, not quality classes. B gives ≥0.5 mm land-to-land.
- Hausherr (PCB Libraries): customers use 0.10/0.20/0.40; "Siemens, Cadence and Zuken users turn off all Courtyard Excess values" ([forum](https://www.pcblibraries.com/forum/placement-courtyard-excess_topic3372.html)) [S], VERIFIED.
- Secondary [S]: 1.0 mm courtyard around BGAs, ~1.5 mm BGA rework clearance; Cadence 0.25–0.3 mm side-to-side and 0.5–1 mm to edge; TI ≥0.508 mm between land areas.

## Tombstoning
[S]
- One end wets first and surface tension stands the part up; 0201/0402 are most susceptible.
- Symmetric IPC-7351 pads; thermal relief on plane-connected pads (spokes 0.10–0.20 mm, gaps 0.20–0.30 mm); mirror any via within 1 mm of one pad; balance paste; a longer soak helps ([JLCPCB](https://jlcpcb.com/blog/pcb-tombstone); [AtlasPCB](https://www.atlaspcb.com/blog/pcb-tombstoning-prevention-smt/)).

## Fiducials
Source: ([Solutions Mfg](https://www.solutionsmfg.com/images/pdf/fiducial.pdf)) [P], CORRECTED:
- Minimum 1 mm, maximum 3 mm. Clear area ≥ the mark radius, preferably equal to the diameter.
- Edge distance ≥ 7.62 mm (SMEMA transport clearance) + fiducial clearance for a board conveyed on its own edges. On railed panels the assembler's rail spec applies (JLC: 1 mm fiducials 3.85 mm from the panel edges on 5 mm rails, VR). There is no "≥5 mm" in the primary.
- Local fiducials for ≤0.020" (0.5 mm) pitch; others use <1.0 or ≤0.4 mm.
- Three global fiducials in an asymmetric L, all the same size; mask never covers them.

## Test points
Source: ([Test Electronics](https://testelectronics.com/info/whitepapers/dft.php)) [P], CORRECTED:
- Pitch 0.100" whenever possible, 0.050" minimum; pads ~0.035".
- ≥0.125" from the board edge; ≥0.040" (1.0 mm) from components; handlers may need up to 0.138".
- All on one side.
- Flying probe [S]: pads 0.5 minimum / 0.75 mm recommended, spacing 60/80 mil.

## Depaneling and panels
[S]
- Components ≥2 mm from the V-cut centreline; MLCCs 3–5 mm (5 mm on 0.8 mm boards), because flex cracks pass test and fail later; use soft-termination MLCCs near edges.
- Stress ranking from lowest: push-back < slit < V-groove < perforation.
- Rails 5–10 mm; tooling holes 2–4 mm NPTH, asymmetric, ≥2 mm clear; mouse bites 0.5–1.0 mm with tabs 2–3 mm wide every 50–90 mm; parts 1.5–2.5 mm from tabs.

## Orientation and silk
[S]
- Polarized parts in one direction, 0/90°; clear pin-1 and polarity marks; avoid THT ([Cadence DFA](https://resources.pcb.cadence.com/home/2024-dfa-guidelines-for-pcb)).
- FEDEVEL: extra silk on connectors and slots to prevent placement errors.

## Mounting holes
(No standard; [interface_rule_packs.md § 10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)):
- Raspberry Pi RP2040 reference: "NPTH FD2.75mm SM3.15mm KO6mm"; other Pi boards FD2.7 / SM5.8 / KO6.2 ([RP2040 HW design](https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf)) [P].
- ISO 273 clearance holes (M2 2.2/2.4/2.6; M2.5 2.7/2.9/3.1; **M3 3.2/3.4/3.6**; M4 4.3/4.5/4.8 mm) [S].
- M3 socket head ≈5.5 mm; ~7 mm clearance in practice [S].
- TI: no high-speed traces near mounting holes [P].

## DFM rule IDs
RPA §6, VR [I].

| ID | Rule | Numeric | Check | Class |
|---|---|---|---|---|
| DFM-01 | DRC at absolute limits; router at recommended + margin | JLC as above; edge copper prefer 0.3–0.5 mm | Board setup + DRU | Hard |
| DFM-02 | Courtyards never overlap (same side) | Level B 0.25 mm | Built-in | Hard |
| DFM-03 | Symmetric thermal connection on 0201/0402/0603 | Copper within r = 1 mm of each pad; ratio > ~2 flags | Geometric | Soft (S3) |
| DFM-04 | Polarized parts consistent per side, 0/90° only | ≤2 orientations per class | Rotation histogram | S4 |
| DFM-05 | Single-sided SMT if it fits; only light, small parts on the bottom; no THT under SMD | — | Bottom-side count / mass | S3 |
| DFM-06 | Fiducials: 3 global + 2 local per fine-pitch part | 1.0 mm Cu, 2.0 mm opening, corrected edge rule | Count/position/asymmetry | S3 |
| DFM-07 | Test point per required net, one side | Corrected clearances | Coverage %; pitch | S3 |
| DFM-08 | Edge keep-outs by part class | Parts ≥0.5–1 mm from routed edges [I]; MLCC/BGA 3–5 mm from V-score | Courtyard → Edge.Cuts / V-score | S2 (MLCC), soft |
| DFM-09 | Mounting-hole keep-out ring | Ø ≥ head/standoff + 2 × 0.5 mm [I]; RP2040 6 mm | Rule area per hole | S2 |
| DFM-10 | HV clearance per IPC-2221B or the safety standard | [isolation-creepage.md](isolation-creepage.md) | HV net class | Hard |
| DFM-11 | Silk legible, off pads, pin-1 outside the body | JLC ≥1.0 mm / 0.15 mm | `text_height`, silk DRC | Hard (JLC) |
| DFM-12 | Height zones from the enclosure | Mechanical drawing | 3-D height vs rule areas | S1 |

## Open questions
- **JLCPCB SMD pad spacing:** RPA §6 [P] lists "≥0.10 mm (1 oz) / 0.20 mm (2 oz)", while VR/IRP list different-net pad-to-pad 0.15 mm. These may be different parameters (mask-bridge vs different-net); re-check before encoding.
- **Not readable:** JLCPCB's component-spacing table (JavaScript) and PCBWay's assembly spacing.
- **No authoritative source** for the double-sided assembly cost premium or a mounting-hole standard. IPC-7351 and IPC-2221B are paywalled (expert reproductions used).

## Sources
- [rules_power_rf_analog_dfm.md § 6](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/rules_power_rf_analog_dfm.md); [verification_rules.md § 1B, § 2](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/verification_rules.md); [interface_rule_packs.md § 10](../../../research_notes/LLM%20driven%20PCB%20placement%20and%20routing/interface_rule_packs.md)

See also: [isolation-creepage.md](isolation-creepage.md), [power/high-current.md](power/high-current.md), [placement-methodology.md](placement-methodology.md)
