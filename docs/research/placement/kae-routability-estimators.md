# Routability estimators for the kae placer (dead end)

**Status:** did not work (congestion, pour fragmentation, probe-select, edge pull); untested (free angles).
**First published:** 2026-10-22, commit [537d08f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/537d08feff641d222ae645461b953c66ae414227) on branch `claude/vigilant-mayer-i91rrr` (channel term [11bb4e3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/11bb4e3ebf3d07e0ce3e199582854d3872ab273f), pour fragmentation [07a2fdd](https://github.com/magnetic-trowel/kicad-auto-everything/commit/07a2fdd8c16d5981faa7d4be8ed0ca2d62072e5b), probe-select [f61812b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/f61812b0f611b2c410873ddea637f53915898fd2)).

Our placements route worse than the human ones on dense boards (split C: 30/78 clean vs 43/78; [kae-staged](../joint/kae-staged.md)). We tried to predict and prevent that inside the placer with routability estimators: RUDY and its variants, channel halos, cut capacity, corridors, pour fragmentation, and finally by routing several candidate placements briefly and keeping the best. None of them separates the placements that fail from the ones that route. Grouped here so others can skip them or start from what we measured.

## Idea and how it works

**RUDY congestion** (`place/cost.py`, `Congestion`). On a coarse bin grid each net spreads w + h of its pin bounding box uniformly over the box. The x and y weights are separable, so a net's demand is an outer product and moves are incremental. Pins add escape demand; pads with clearance halos remove supply. Supply per bin = layers x bin area / track pitch x (1 - beta * blocked). Cost = mean over bins of max(0, u - 0.5)^2 with u = demand / supply. RUDY stays in the annealer cost (`w_cong`) and is the base for the joint loop's congestion history ([kae-joint-loop](../joint/kae-joint-loop.md)).

**Variants studied:** pad gaps, net crossings, pour access, corridor overflow, cut capacity (demand across a cut line vs tracks that fit through it), and a **channel term** `w_chan`: soft halos around pads so a track fits between neighbouring parts' pads.

**Pour fragmentation** (`place/pour.py`). Per (net, layer): fill region = union of the net's zones inside the edge clearance, minus higher-priority zones of other nets, keepouts and other-net copper grown by clearance, then opened by the zone's minimum width. Pieces across layers are joined by the net's through-hole pads and vias. Count the components that hold the net's pads, plus pads on poured layers that touch no piece: the connections the router must add. A variant adds a minimum-spanning-tree track estimate as obstacles.

**Probe-select** (`--probe-select N`). Place with seeds seed .. seed+N-1 (`--probe-jitter F` moves later candidates' seed stage by F x board span; `--probe-parallel P` runs P at once), route each briefly with the [kae bridge](../routing/kae-freerouting-bridge.md) and [last mile](../routing/kae-last-mile.md), and keep the fewest open connections among candidates within 10% of the best physics.

**Connector edge pull.** A soft term pulling connectors and mounting parts to the board edge, calibrated on human edge rates.

**Free angles** (`--angles STEP`). Parts may take any multiple of STEP degrees in the annealer (heatsink-mount packages keep right angles; CP-SAT stays on right angles). `tools/research/place/anglepolish.py` is a paired test: both arms start from the same finished legal placement and get the same number of low-temperature moves (geometric T0 * hot -> T0 * 1e-4, final legality weight, same seed).

## What we tried

Estimators were measured on three dense sensor boards (paw3395, badjeff-pmw3610, siderakb-pmw3610), our placements against the human ones, each routed with 3 router seeds, and checked against human boards that route (an estimator that flags routable human boards is wrong).

## Results

All from [kae-place](../../topics/placement/kae-place.md), section "Negative results"; small n (1-3 boards, 3 router seeds).

| estimator | result |
|---|---|
| RUDY (several variants), pad gaps, net crossings, pour access | none separates failing from routing placements |
| corridor overflow | flags 42 of 109 human boards that route |
| cut capacity | failed human validation (human boards above capacity route); not built |
| channel term `w_chan`, paw3395 (unconnected, 3 router seeds) | 11/10/10 -> 9/9/2 at weight 1 -> 2/5/3 at weight 3; not validated on human boards; off (`CHAN_W = 0`) |
| pour fragmentation, pads only | human baseline 334/412 pours need nothing; every paw3395 and siderakb placement (ours and human) is one piece: islands appear only once tracks exist |
| pour fragmentation + MST tracks | human 54/76 small two-layer pours need nothing; the most split paw3395 placement (w_chan 3, 6 pads stranded) routes among the best; on siderakb the estimate points the wrong way; the routed human paw3395 is as fragmented as ours |
| probe-select, paw3395 (mean unconnected, 900 s finals) | probe 3: 4.7; w_chan 3 + probe 3: 11.0; + jitter 0.15: 7.7; probe 5 + jitter: 3.7; vs w_chan 3 alone 3.3, human 0 |
| edge pull (human edge rates) | USB, barrel, audio 100%; headers 69%; mounting holes 84%; term dropped |
| free angles | no recorded paired result |

## Verdict

Did not work. Reasons we found:
- On PCBs, RUDY-style demand ranks routability near chance. Our reading (not tested separately): failures come from local escape geometry (caps in the strip between sensor pins and the board edge, a locked sensor taking half the board) that box-spread demand does not see.
- Fragmentation of pours only shows once tracks exist, so a pre-route estimate has nothing to count.
- A 90-140 s probe route reports 7-20 open connections and its ranking does not carry over to a 900 s route; each candidate gets only 46-76 s of placement; the physics slack excluded the best-probing candidate; and jitter barely diversifies candidates because the CP-SAT floorplan pulls seeds back together.
- Edge pull became moot when the mechanical interface was fixed ([kae-fixed-interface](kae-fixed-interface.md)).

What replaced them: let the router judge. The [joint loop](../joint/kae-joint-loop.md) feeds KiCad's unrouted report back into the placer as congestion history and local windows. Free angles remain an untested idea: run `anglepolish.py` before relying on `--angles`.

## Code

- `kae/src/kae/place/cost.py` (RUDY), `engine.py`, `pipeline.py` (`CHAN_W`), `pour.py` (diagnostic; test `kae/tests/test_place_pour.py`), `kae/src/kae/cli.py` (`--probe-select`, `--probe-parallel`, `--probe-jitter`, `--angles`).
- `tools/research/place/anglepolish.py`.
- First appearances: RUDY [537d08f](https://github.com/magnetic-trowel/kicad-auto-everything/commit/537d08feff641d222ae645461b953c66ae414227) (calibration [bde4bc4](https://github.com/magnetic-trowel/kicad-auto-everything/commit/bde4bc4ac8f15c6dfe21aee47d4b14a868c0d9da)); `CHAN_W` [11bb4e3](https://github.com/magnetic-trowel/kicad-auto-everything/commit/11bb4e3ebf3d07e0ce3e199582854d3872ab273f); pour [07a2fdd](https://github.com/magnetic-trowel/kicad-auto-everything/commit/07a2fdd8c16d5981faa7d4be8ed0ca2d62072e5b); probe-select [f61812b](https://github.com/magnetic-trowel/kicad-auto-everything/commit/f61812b0f611b2c410873ddea637f53915898fd2), jitter [68a05f2](https://github.com/magnetic-trowel/kicad-auto-everything/commit/68a05f271ac27d6c1d2810a750a7b19a3bbf9540); `--angles` [6a32272](https://github.com/magnetic-trowel/kicad-auto-everything/commit/6a322723ca7e85f6136de3655071a9c132c2b163), anglepolish [e171267](https://github.com/magnetic-trowel/kicad-auto-everything/commit/e171267e73ad11b230df15ac32a9ef9e2e832be0).

## Related

[kae-placer](kae-placer.md), [kae-staged](../joint/kae-staged.md), [kae-joint-loop](../joint/kae-joint-loop.md), [placement algorithm families](../../topics/placement/algorithm-families.md).
