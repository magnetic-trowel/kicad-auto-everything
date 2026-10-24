<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Physics score of the joint place-and-route runs (tag `phys`)

## How the scorer works
`physics_score.py RUN_DIR...` uses the `kae` physics engine (branch
`claude/vigilant-mayer-i91rrr`, run from that branch's venv with
`KAE_KICAD_PYTHON=/usr/bin/python3`). For each board it builds **one** circuit brief
(`kae.circuit.brief.build`, which reads the netlist only, never positions) and the place terms
`Terms(board, brief)`, and caches both under `kae-work/phys-cache/<id>/`. The human reference
board and every run's `attempt-0/output/board.kicad_pcb` are then scored with the same brief
and the same allocations:

- **place terms**: `Terms.total(poses)`, where poses are matched by uuid. This is the sum of
  confidence × φ(u) over structures, and φ has a quadratic barrier above budget. The scorer
  also records `total_by_kind` and a robust variant, **capped-u**: Σ min(u, 5), as the
  Scorecard caps routed u.
- **routed**: `critical_recheck.board_physics` on the real copper (zones refilled by KiCad),
  summarized as the Scorecard's `physics_total`. Each module's u is capped at 5, and a
  module with no value counts as 3.

A ratio is (method + 0.01) / (human + 0.01), averaged as a geometric mean. A board counts
as "worse" when the method's value is more than 0.1 % above the human's.
JSON per run: `kae-work/phys/<run>.json`. A cached rerun takes about 1 minute.

## Coverage
- All 33 A+B boards had a brief and were scored on both place and routed physics: human 33/33.
- **Only 10/33 boards have any physics structure.** On the other 23 the brief finds only
  `connector_chain`, `victim` or `antenna` entries with no aggressor or protection part to
  price, or nothing at all, so every term is 0.
- Each run is missing two outputs (`azonenberg…`, `suzyqboard`, status `no_output`), but
  neither board has any structures, so that costs no coverage.
- `pnr-anneal-v3` lost one physics board (no output).
- Per-board errors: none.

## Table (10 physics boards)
TABLE

## What it says
- **Every HPWL-driven placement is physically worse than the human's**:
  - capped-u is ×1.4–1.7 the human's;
  - 7–9 of 10 boards are worse;
  - φ-total is ×3–6, because single structures fly far over budget.
  - This still holds on legal placements only (×1.3–1.5).
- `pnr-route-v3` is a sanity check: the human placement routed by the engine. Its place
  terms are exactly 1.00, as they must be.
- The excess comes from three terms:
  - **decap** (about 40–60 % of the excess; worse on 5–8 of 10 boards). HPWL puts each
    capacitor beside the net's centroid, not beside the power pin it serves, and nothing
    prices the loop. Example: paw3222's VDDA decap loop goes from u 1.05 to 7.4.
  - **coupling** (30–40 %, on 2 boards). Example: olimex's buck feedback node lands beside
    the switch node, going from u 1.1 to 40 (405 mV against a 10 mV budget), and φ turns
    that into 1287.
  - **world_cm** (cable common-mode, ×6–10).
- Commutation and thermal are worse by about ×1.3–1.6. ESD paths come out slightly
  *better* (×0.65–0.88), because compaction shortens the connector-to-TVS hops.
- `anneal` is the least bad on place terms (×1.40 capped).
- **Routed physics** is worse by about ×1.25–1.55 for the HPWL methods. The engine's own
  router is not to blame: on the human placement it is ×0.90 on the 5 boards with no open
  hop. The loss therefore comes from the placement.
- **Caveat:** an unrouted hop inside a module is priced as a straight strip, which is
  optimistic. That is why the "no open hop" column exists.
- The priors are E5, meaning they have not been measured; humans also sit over budget on
  several boards (pmw3610 decap u ≈ 2.5). Read these numbers as *relative*, not as pass or
  fail.

## Optimizing physics in the loop
A method would need to:
1. Make `kae` importable from the method's interpreter. It needs numpy, scipy, shapely,
   ortools and numba. Either `pip install -e kae[fast]` into `bench/.venv` or put
   `kae/src` on `sys.path`. Build the terms once:
   `T = Terms(load(input_board), json.load(open('kae-work/phys-cache/<id>/brief.json')))`.
   The input board works too, because uuids match. Building the terms takes ≤ 0.5 s.
2. Keep poses keyed by uuid, as `run.py` writes them:
   `poses[p.uuid] = (*world.xy(cx, cy), ROTS[ri], 'B' if p.side else 'F')`.
   Include **every** part, because a part missing from `poses` is evaluated at its input
   pose.
3. Price each candidate move with `d = T.delta(poses, [uuid], {uuid: new_pose})`. This
   takes 30–60 µs per call on these boards, and `delta_by_kind` gives the per-term split.
   On acceptance, update `poses[uuid]`; the cache resyncs by identity.
4. Skip parts outside `T.parts()`: 9–18 parts per board carry physics, and the rest have
   zero delta.
5. Add `w_phys * d` to the existing cost (HPWL + routed length + overlap). Terms ignore
   legality, so on its own the descent stacks parts.
6. Use the capped-u form, or a modest `w_phys`, so that a single φ blow-up does not swamp
   routability.
7. After routing, `board_physics(path, brief=brief, terms=T)` gives the routed check
   (`kae.joint.scorecard.physics_total`) for accept or reject, as `kae.joint.stages.evaluate`
   does.

A first target: run decap-aware and aggressor/victim-aware moves for the 9–18 physics parts
after `seq`'s placement, then measure them with this scorer and DRC.
