# kae

Physics-first joint placement and routing for KiCad boards. Plan:
[month-plan](../docs/topics/architecture/month-plan.md); design:
[system-design](../docs/topics/architecture/system-design.md).

```bash
python3 -m venv kae/.venv
kae/.venv/bin/pip install -e 'kae[dev]'
kae/.venv/bin/pytest kae/tests          # KiCad tests skip without pcbnew
```

## `kae.board`

- `model`: the board model (Contract 1), dataclasses with `to_dict`/`from_dict`.
  Units are mm and degrees in KiCad board coordinates (y down). The footprint uuid is
  the part key (the loader synthesizes a stable one when a file has none or repeats one).
- `kicad_file.load(path)`: pure-Python reader for `.kicad_pcb` (KiCad 10, tolerant of
  6-9), with the sibling `.kicad_pro` and `.kicad_dru`. Median 0.05 s per board
  (max 1.1 s for a 17.7 MB file).
- `transform`: `pad_xy`, `pads_xy` (vectorized), `courtyard`; KiCad's rotation and flip
  conventions, verified against pcbnew pad by pad.
- `pcbnew_io`: `extract(path)`, `write_poses(src, dst, {uuid: (x, y, rot, side)})` and
  `verify(path)`, through KiCad's own Python in a subprocess (the writer uses KiCad's plain
  reader and writer, so nothing but poses changes). Set `KAE_KICAD_PYTHON`
  (a command, e.g. `/usr/bin/python3`) or `KAE_KICAD_WRAP` (a prefix, e.g.
  `apptainer exec ~/kicad.sif`), as for kaebench. One KiCad Python per process
  serves the calls (each in a child forked after `import pcbnew`, so outputs are as with a
  process per call, without its ~1 s start-up); `KAE_PCBNEW_WORKER=0` starts one per call.
- `sdiff.diff(a, b)`: structural diff of two board files (objects keyed by uuid).

Footprint frame: pad and courtyard coordinates are stored in the library frame (the
footprint as drawn, front side, 0 degrees). A pose `(x, y, rot, side)` maps a local point
`(lx, ly)` to `(x, y) + R(rot) (lx, s*ly)` with `s = -1` on the back, where
`R(a) (u, v) = (u cos a + v sin a, -u sin a + v cos a)`; a pad's angle is `rot + s*lrot`.

Acceptance against pcbnew on the prepared kaebench tasks:
`kae/.venv/bin/python kae/scripts/board_acceptance.py {verify,roundtrip,place,loadtime} --tasks DIR`.

`pcbnew_io` also serves `kae.route`: `export_dsn` (KiCad's Specctra export plus what it leaves
out, and KiCad's rule engine probed per net and layer), `import_ses`, `edit_routing` (delete,
widen, add, lock and unlock tracks and vias) and `zone_fills` (zones refilled as the DRC does).

## `kae.route`

The KiCad -> Freerouting -> KiCad bridge: every KiCad constraint reaches the router or is
enforced after import ([freerouting-constraint-bridge](../docs/topics/routing/freerouting-constraint-bridge.md)).

```bash
kae/.venv/bin/python -m kae.route.cli route IN.kicad_pcb OUT.kicad_pcb --seed 0 --time 600
kaebench run --adapter kae-fr --kinds route \
  --command "kae/.venv/bin/python -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout}"
```

**Read `blocked` when connections stay open.** The router never relaxes a board's rules. At the
end it diagnoses each connection still open (`kae.route.blocked`, a few seconds; `--no-blocked`
turns it off) and the JSON report (last stdout line, `--report FILE`) carries a `blocked`
section, with one line per connection in the log (`blocked: ...`). Each connection gets a cause:
`congestion` (a path exists without our other copper: not a rule), `fixed copper` (the input's
own tracks of the nets named), `rule` (a board rule: the value required and the value available,
where, and its source: the `.kicad_pro` net class or board setup, a `.kicad_dru` rule by name, a
footprint, a rule area, a pad's solder-mask opening), `kae default` (one of kae's own limits, with
its `KAE_<NAME>` / `--set` override when there is one) or `geometry` (walled in by copper even with
every clearance at zero). For example:
`U2.17 CS1: needs a 0.160 mm track at (2.52, -16.60) F.Cu, minimum track width 0.200 mm (.kicad_pro
board setup minimum track width); relax to 0.160 to allow`. The caller decides: change the rule,
move a part, or accept the open connection. Under `tools/kaeres/restart.py` the kept attempt's
report goes to `restarts/report.json` and its `blocked` lines to the wrapper's log.
`python -m kae.route.blocked ROUTED INPUT [--drc REPORT] [--out FILE]` runs the diagnosis alone.

Locked tracks and vias in the input are kept as they are; zones named `kae-crit:...` are
obstacles for other nets. `kae.route.effective.load(board)` gives any other router the same
numbers per net and layer (`track_width`, `via`, `clearance`, `pad_clearance`,
`edge_clearance`, `same_net_via_pitch`). Needs Freerouting 2.5.x (found as kaebench finds it)
and kicad-cli.

`kae` never imports `kaebench` (or research scripts); methods plug into the harness with
`kaebench run --command`.
