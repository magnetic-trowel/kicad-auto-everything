<!-- SPDX-FileCopyrightText: 2026 HaslamPCB contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Power-net track width: why haslam draws current-carrying nets at the board minimum

Scope: what the obd-solar end-to-end run (2026-11-27..28) established about track width on current-carrying nets:
the symptom, the measured causes (router, net-class sizing, placement, post-passes, gates, physics), what was changed,
what is on experiment branches, and the corpus questions still open. Board package for reproduction:
[`designs/obd-solar/handoff/`](../../../tools/research/llm-design/designs/obd-solar/handoff/README.md). Not here: the
power-copper post-pass's own design -> [haslam-power-copper](haslam-power-copper.md); the bridge ->
[haslam-freerouting-bridge](haslam-freerouting-bridge.md); the run's full friction log ->
[obd-solar FRICTION.md](../../../tools/research/llm-design/designs/obd-solar/FRICTION.md).
Keys: track width, power net width, neck, neck-down, neck_width_um, start_necked, neckedRouteNets, retryConnectionNecked, pin ties, tie_pins, class width, current-sized net class, width_check, branch current, power_copper, to_class, zones into pads, vector zones, trunk vs stubs, obd-solar, gfix-route-width, gfix-auto-widen

## W1. Symptom (obd-solar, 2-layer, 96 x 66 mm, 25 % courtyard density, 94 footprints)

| Net | i_max (A) | Class width (mm) | IPC-2221 need at 10 C (mm) | Drawn | Source |
|---|---|---|---|---|---|
| VBAT | 3.5 | 2.05 | 1.69 | 179 of 195 mm at 0.127 mm | seed 1, `layout.sh` |
| VBUS | 2.0 | 0.8 | 0.78 | 90 of 93 mm at 0.127 mm | same |
| CHG_OUT | 0.8 | 0.3 | 0.22 | 81 of 84 mm at 0.127 mm | same |
| /USB/BB_SW2 | 3.0 | 1.4 | 1.37 | 29 of 40 mm at 0.127 mm | same |

1. Every connection routed (0 unconnected); KiCad DRC: 4 `starved_thermal`, schematic parity 0. **No existing gate failed**: a
   KiCad net-class width is the default for new tracks, not a rule, and the generated `.kicad_dru` had no `track_width` rule.
2. The physics evaluator, once given a load fact and a heat term (W6), scored the same board: hottest track 199.6 K
   (VBAT, F.Cu, 0.127 mm; limit 20 K), VBUS drop 266 mV, U301 Tj 185 C, copper loss 1.76 W at a 12 W output.
3. Board size is not the cause: an earlier 80 x 55 board (60 % fuller) showed the same collapse; at 96 x 66 the router's
   channel utilisation was 0.27.

## W2. Router mechanism (measured per restart stage; FRICTION.md #59-60)

1. The class width cannot enter small pads (0603, SOT-23, 0.40 mm TSSOP pins) without hitting neighbouring pads, so the
   Freerouting fork retries the **whole connection** at the neck width (`AutorouteConnectionRouter.retryConnectionNecked`;
   bridge `neck_width_um = min_trace_width_um` = the largest legal minimum = the board minimum, `bridge.router_settings`,
   `constraints.plan`).
2. The retry adds the net to `neckedRouteNets`; the fork's default `autorouter.start_necked=true` then routes **every later
   connection of that net at the neck** without trying the class width, including pad-to-pad runs where 2.05 mm fits.
3. `BatchAutorouter` also seeds `neckedRouteNets` from any trace narrower than its class at loop start;
   `translate.tie_pins` (default `pad_entry` "centreline") writes 0.05 mm fixed pin ties at every wire end inside a pad, so in
   every repair, incremental and finishing Freerouting run every tied net starts necked (how CHG_OUT and PV_IN lost their
   0.3 mm in the joint loop's policy 2).
4. Width by stage (mm of track by width):

| Stage | VBAT | VBUS | CHG_OUT |
|---|---|---|---|
| a0, first bridge route | 0.127: 250 | 0.127: 17, 0.8: 122 | 0.3: 94 |
| a3 (kept, policy 1 output) | 0.127: 229 | 0.127: 84, 0.8: 3.7 | 0.3: 51 |
| policy 2 output = delivered | 0.127: 179, 2.05: 15 | 0.127: 89 | 0.127: 81 |

5. Bridge-only arms on the a3 placement (seed 1, no repair/last mile): default VBAT 0.127: 222; no neck: 2.05: 46 but most
   pads unrouted (pad entry is what fails); `start_necked=false`: VBAT 2.05: 118 / 0.127: 104, VBUS 0.8: 83 / 0.127: 19 (class
   width 0 -> 53 % and 0 -> 81 % of length); `start_necked=false` + neck 0.25: VBAT 2.05: 98 / 0.25: 107.
6. Smaller sources: last mile tries opt then falls back to min (`lastmile.widths_of`); nets whose names end in N/P match
   KiCad's implicit "(diff pair)" rule, get opt = -1 nm and route at the minimum (`constraints._width_choice`).
7. A per-net KiCad `track_width (min X)` rule is honoured but does not suffice: `rules.strictest` takes the larger minimum of
   the geometric and non-geometric passes, so courtyard exemptions bind everywhere, and `plan` makes X the global neck and
   the fork's floor: fine-pitch pins become unroutable.

## W3. Net-class sizing (haslamsynth; FRICTION.md #36)

1. Before `fb25efc`, a class's width was IPC-2221 for its **bucket's** current at 10 C: 3.3-4 A nets became `_5A` at 2.8 mm,
   with 2.54/1.12 mm vias. The bucket now only names the class; width = widest member net's own IPC width at
   `BoardSpec.trace_rise_c` (default 10 C). Rebuilt designs: liion SW*_5A 1.4 -> 0.75 mm, prius 20 A 9.4 -> 6.9 mm, error counts
   unchanged.
2. Current-sized classes are many times wider than the pads they must enter; this, not the router change history, is what
   makes W2 bite on haslamsynth designs (W8).

## W4. Placement and the joint loop (FRICTION.md #54-55)

1. The placer prices physics, but hot-loop budgets come from overshoot vs the switch rating, capped at 50 nH
   (`physics/priors.py`), and far input caps combine as parallel loop paths (`physics/build.py`): moving a 30 mm-away input cap
   to the IC pin changed the cost by 0.0009. Relations touching physics parts are demoted unless `requested`.
2. The joint loop accepts a window on equal KiCad rank by routed module physics only (`joint/scorecard.py`): one DRC window
   moved C311 from 2.2 to 15 mm off U301 and raised the placer's FB pickup estimate 23 -> 773 mV, accepted as "physics better".
   Width is in neither the rank nor the acceptance; restart ranking (`rank.board_rank`) ignores it too.
3. Consequence for width: power trunks are long and pass close to other pads and vias, where no post-pass can widen them (W5).

## W5. Post-route widening and pours (FRICTION.md #61, #63-64, #68)

1. **Trunk vs stubs.** Branch currents (F101.2 +3.5 A, U301.13/17 sinking) show VBAT's trunk is 98 of 194.5 mm; the rest are
   stubs to decaps, dividers and the TVS carrying ~0 A DC. Widening lands mostly on stubs (they have room).
2. The trunk is boxed in: segments within 2 mm of BB_SW1/SW2 pads, between GND vias and CMP_INP/PV_IN pads, past the SWD pads
   on the other layer. Relaxing every extra spacing rule improves trunk too-narrow length only 83 -> 71 mm.
3. Variants on seed 1 under the branch-current gate (W6), too-narrow mm and DRC errors:

| Post-pass | VBAT | VBUS | CHG_OUT | BB_SW2 | DRC |
|---|---|---|---|---|---|
| none | 69.7 | 20.9 | 41.7 | 25.8 | 4 |
| `power_copper` widen (default before zones) | 68.2 | 15.5 | 11.2 | 25.8 | 4 |
| `--mode vector --vector-out zones` (pads necked) | 66.8 | 20.9 | 7.4 | 25.8 | 4 |
| same with `--no-neck` (pours into SMD pads) | 65.2 | 11.8 | 8.3 | 25.8 | 3 |
| `to_class` prototype (branch `gfix-auto-widen`) | - | - | - | 17.1 | 4 |

4. Zones were never the default because the route-task scorer counts any zone edit as invalid (`bench/src/haslambench/score.py`;
   haslam-power-copper.md "Width cap sweep"). Pouring solid into 0402/0603 lands raises reflow tombstoning risk (not checked).
5. Teardrops widen at the pad (the wrong place) and KiCad 10.0.8 has no generator API. Pre-laid pin-entry stubs (`fr_entry`)
   need the `haslam-pad-entry` fork (absent from the pinned build) and cost completion ([routing-stages](../../topics/routing/routing-stages.md) §2).

## W6. Gates and physics (FRICTION.md #31, #56, #57, #62, #65-66)

1. `synth/scripts/width_check.py` (post-route gate, run by `layout.sh` and required by `pipeline.py`): IPC-2221 need per segment
   from the segment's **branch current** (resistive solve of the routed copper, `power_copper.branch_currents`, under the
   evaluator's DC plan from the design's intent file, per net: `planned_injections(per_net=True)`), scaled so the largest branch carries the net's `i_max`, with a
   10 % floor for stubs; segments within 1 mm of a same-net pad are exempt; segments >= 90 % under a same-net fill count as
   poured. `--basis net` judges every segment by `i_max`.
2. The evaluator modelled width correctly but its DC plan injected 50 mA + 30 mA (no load facts), so 0.127 mm on a 3.5 A net
   read 0 K; with `parts.J301.I_A` the track reads 120 K, and a `heat.track` term prices it. Its DC plan covers neither a charger
   into an external battery nor converter inputs, so obd-solar supplied injections by hand. Branch `synth/dc-defaults` (from
   `physics/dc-plan-cells`): an unstated export alone on a converter's rail keeps its 1 % typical with its band's top at the converter's current, a charger
   with no load charges the external source one series part away, and the gate's plan has the facts and per-net
   series-part currents; the hand file is gone and the verdicts are unchanged (FRICTION.md #73).
3. Cell-window solves at 0.0625 mm needed > 8.5 GB on a spread cell (OOM kill at 13.2 GB); `--cell-pitch 0.125` took 84 s, 3 GB.

## W7. Changes made and pending

| Change | Where | Status |
|---|---|---|
| Current check by path current, not net total | `5c1ad72` | on `obd-solar-e2e` |
| Class widths from each net's current | `fb25efc` | on `obd-solar-e2e` |
| Fab profile (full JLC rules) | `304f23e` | on `obd-solar-e2e` |
| Width gate (net basis), then branch-current basis, pour credit | `a2e5ed6`, `5bdc8f8`, `6ee7923` | on `obd-solar-e2e` |
| `power_copper` post-pass in `layout.sh` | `896a21d` | on `obd-solar-e2e` (zones-into-pads default staged) |
| Hot loops as requested near relations | `af417e4` | on `obd-solar-e2e` |
| `start_necked=false` default, `neck_floor="class"`, opt <= 0 guard | `5895488` | branch `gfix-route-width`, experiment pending |
| `power_copper to_class` (switch nodes, narrowed nets to class width) | branch `gfix-auto-widen` | prototype, experiment pending |
| PVOUT as converter output pin | `10561d8` | branch `gfix-pvout-cell`, experiment pending |

## W7a. One-seed smoke A/B of gfix-route-width (FRICTION.md #72)

Same unplaced board (`handoff/unplaced`), current intent, seed 1, `HASLAM_TIME=1200`, zones-into-pads post-pass in both arms.

| Too narrow (branch gate), mm | A: obd-solar-e2e | B: + start_necked off (+ neckdown requested) |
|---|---|---|
| VBUS | 39.0 | 0.4 |
| VBAT | 16.5 | 21.3 |
| BB_SW2 / BB_SW1 | 15.3 / pass | 19.1 / 4.4 |
| DRC errors; unconnected | 5 clearance + 1 starved_thermal; 0 | 1 clearance + 3 starved_thermal; 1 |

1. `autorouter.start_necked=false` is confirmed in B's saved bridge settings; `automatic_neckdown` reads false in both arms,
   so the neckdown part of B is unconfirmed.
2. A's 5 clearance errors come from an over-strict generated 0.6 mm rule (an interval sum over a gate-drive domain), not from
   width (FRICTION.md #71). One seed decides nothing; this is the shape of the sprint, not its verdict.

## W8. Why the corpus did not show it (FRICTION.md #67)

1. The one corpus width metric (`start_necked=false` precondition, [freerouting-settings-2611](freerouting-settings-2611.md)):
   power-net track below **class width** 13.5 % (bridge) vs 14.6 % (human), 170 merit boards: no gap, so R43 was shelved.
2. That metric is relative to human net classes, which rarely exceed the pads' widths (humans widen by hand or pour). Corpus
   route tasks keep human placement (compact power paths), many boards carry power on planes, scoring is opens/DRC/cp1, and
   without intent files the evaluator injects no real current. Not verified on the corpus (not on the host where this ran).

## Open questions (for a corpus run)

1. **Class-independent width metric.** Per power net (corpus nets with a power role, or nets the human drew wider than the
   board's default), share of haslam-routed length narrower than the **human's routed width on the same net**: does haslam
   under-width power copper on corpus boards, or only with current-sized classes?
2. **How often does class width exceed pad entry?** Over the corpus: power nets whose class width exceeds the narrowest pad
   they connect to, and by how much. Predicts where W2 triggers.
3. **Experiment `gfix-route-width`** against `control-w48`: arms (a) `start_necked` off, (b) (a) + `neck_floor=class`, (c) (a) +
   `--set bridge.neckdown=1` (pin-local neck, already in the fork: `MazeSearchEngine`, `FoundConnectionInserter`); suites
   sprint + `bench/suites/mech/` power-distribution, buck, boost, battery-charging (width gain) and fine-pitch, usb, diffpairs
   (neck regressions). Report completion, cp1/cpk, per-type DRC and the width metric of question 1.
4. **Experiment `gfix-auto-widen`** (`to_class`) and zones into pads: zones need a scorer decision (a design task kind, or
   pours scored) before route-task benchmarks can measure them.
5. Fork option if (3c) falls short: after a necked retry, re-insert the connection's traces beyond k x pin pitch at class width.
6. Check haslamsynth designs (solar-small, leadacid, liion, prius, rpi) with `width_check.py`: solar-small "routed clean" was
   never width-checked.

## Sources

- Run log: [obd-solar FRICTION.md](../../../tools/research/llm-design/designs/obd-solar/FRICTION.md) #19, #29, #31, #36, #47,
  #54-#68; design: `tools/research/llm-design/designs/obd-solar/` (DESIGN.md, REVIEW.md).
- Board package with every input, output and evaluation: [`handoff/README.md`](../../../tools/research/llm-design/designs/obd-solar/handoff/README.md).
- Prior work: [haslam-power-copper](haslam-power-copper.md), [freerouting-settings-2611](freerouting-settings-2611.md),
  [haslam-freerouting-bridge](haslam-freerouting-bridge.md), docs/research/dead-ends-2611b.md §2, dead-ends-2611c.md §2, §11.
