<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Bus yardstick: a bare-board bus detector and a report-only bus scorecard (A1), with a skew decomposition (A2)

**Status:** built (report-only tooling). Changes no score, cost or selection. The corpus run is queued (kaeq owner `bus-yardstick-1`; `kaeres bus report yardstick-1` writes `~/kae-baselines/bus/yardstick-1/BUS.md`).
**First published:** 2026-11-09, branch `bus-yardstick`.
Keys: bus scorecard, bus detector, lanes open, coupled share, via parity, skew budget, controller-keyed limits, skew decomposition, kae.bus

## What it is

- `kae.bus.detect` finds buses (nets meant to be routed as one object) from what a new board has: netlist, net names and classes, footprints, part data, pin positions. It never reads tracks or vias. It is the bus campaign's census detector, moved into the package unchanged: on 200 random corpus boards, stripped of copper, it gives exactly the census's buses (200/200 identical). Census validation (precision 96%, recall 92-99% by interface tag) carries over.
- `kae.bus.scorecard` measures a routed board's buses: per bus and per diff pair. `python -m kae.bus.scorecard BOARD [--drc drc.json] [--decompose]`.
- `kaeres bus submit|report` runs it over stored runs (`tools/kaeres/busreport.py`). Results live beside each run in `runs/<run>/bus/<evaluator>.json.gz`, not in `evals/`, so no DRC or physics reader sees them. `kaeres exp report` appends the tables when an experiment's runs have scorecards.

## Columns

| Column | Definition | Notes |
|---|---|---|
| lanes open, open items | Lanes (nets joined through series parts) with a `kicad-cli` `unconnected_items` entry naming one of their nets | Copper-graph fallback when the DRC list hit KiCad's 499-item cap or is missing (`opens_src`). Net names may contain brackets (`sdram_dq[0]`) |
| complete | No lane open | |
| vias/lane, via max, via spread, via equal | Layer changes along each lane's pad-to-pad copper path | |
| via span mismatch | Lanes whose sequence of layer pairs differs from the bus's most common one | TI: same count and same barrel length |
| skew mm, skew ps | max - min lane length; delay with 6.0 ps/mm outer, 6.8 ps/mm inner, via flight from the stackup | Point-to-point buses only; fly-by address skew is per device, so none is reported |
| layer agreement | Share of the bus's copper length on its modal layer | |
| stripline share | Share of length on inner layers | |
| coupled 3W | Share of sampled length whose nearest same-bus lane on the same layer is within 3 trace widths edge to edge | Shape only. No target. Never reward it |
| bundled 2 mm | Same, centre distance 2 mm (the census's number) | Shape only |
| limit, skew OK, via OK | `kae.bus.limits`: controller- or interface-keyed budget, else a class default marked `keyed: false` | A check with no key would fail most working boards (human DDR byte skew median 2.7 mm, 20% within 0.5 mm) |

Limits used (`kae.bus.limits`; sources in `bus/physics.md` §3 and the rule packs): DDR byte keyed by controller (TI AM62x 0.3 mm, TI KeyStone 0.254 mm, Intel DDR3 1.47 mm, Agilex 5 0.51 mm, PolarFire 3.7 mm), else by DRAM generation (DDR3 0.5 mm Micron, DDR4 3.7 mm, LPDDR4 22 mm with per-bit deskew), all marked assumed; vias at most 2 and equal. DDR address: vias only. SD/eMMC 6 mm assumed (HS400 would be 1.27 mm). RGMII 74 mm assumed. QSPI, RGB, GPIO, ribbons, matrices: no budget. Pairs by interface (PCIe, USB3, SATA 0.127 mm; MIPI 0.7 mm; HDMI 3.7 mm; LVDS 7.4 mm).

## A2: skew decomposition

For each complete point-to-point bus of at least 3 lanes, each lane's length minus the bus mean is split into additive terms:

- `chord`: the straight pad-to-pad distance minus its bus mean. Placement and pin positions set it; a router can only pay for it with meanders.
- `fan`: path length of the stretches before and after the lane's sustained bundled run (within 2 mm of a sibling for 3 of 4 mm), beyond their straight lines.
- `meander`: serpentine excess (arc minus chord of detected meander runs).
- `turn`: the trunk's turning term −d·Σf(θ), f = 2 tan(θ/2) per vertex, d the lane's offset across the bus at mid-trunk, Σf the median lane's (physics.md §5).
- `other`: the rest (detours, lanes that never bundle, order changes).

Delay terms: copper length at the bus's mean speed, the layer speed mix, via flight. Shares are pooled covariance shares Σx·y / Σy² (they add to 1); R² is each term alone. A synthetic 90° bend of parallel lanes gives `turn` = 1.00 (test).

## Results

Smoke (3 `bus_ddr` boards, human vs `fr-fork master`): the router leaves 69% of DDR byte lanes open (human 2%); on the one class
complete in both (RGB LCD, 4 buses) the router has more vias per lane (2.33 vs 2.00), fewer equal-via buses (25% vs 75%) and lower layer
agreement (0.68 vs 0.84). Corpus numbers (`bus_any`, 6,423 boards, human / `fr-fork master` / Freerouting 2.5.0): queued, owner
`bus-yardstick-1`; this page gets them when the run finishes.

Census bug found on the way: the census's DRC parser (`\[([^\]]*)\]`) truncates net names that contain brackets (`sdram_dq[0]`), so their
opens were not counted as bus opens. 172 of 56,864 detected buses (10 DDR bytes) have such names: the census's shares move by well under
1 point. `kae.bus.scorecard` parses them correctly (test).

## What it does not do

- It does not read fills (zones are reported by DRC only), so reference-plane continuity is not measured.
- Fly-by order and stub length are not measured.
- Delay uses nominal speeds, not a field solve; mode and crosstalk terms (physics.md §4.1) are not modelled.
- The detector's kind labels are rule based: `unknown` and `connector_ribbon` are broad.
