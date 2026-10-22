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
  6-9), with the sibling `.kicad_pro` and `.kicad_dru`. Median 0.07 s per board.
- `transform`: `pad_xy`, `pads_xy` (vectorized), `courtyard`; KiCad's rotation and flip
  conventions, verified against pcbnew pad by pad.
- `pcbnew_io`: `extract(path)`, `write_poses(src, dst, {uuid: (x, y, rot, side)})` and
  `verify(path)`, through KiCad's own Python in a subprocess. Set `KAE_KICAD_PYTHON`
  (a command, e.g. `/usr/bin/python3`) or `KAE_KICAD_WRAP` (a prefix, e.g.
  `apptainer exec ~/kicad.sif`), as for kaebench.
- `sdiff.diff(a, b)`: structural diff of two board files (objects keyed by uuid).

Footprint frame: pad and courtyard coordinates are stored in the library frame (the
footprint as drawn, front side, 0 degrees). A pose `(x, y, rot, side)` maps a local point
`(lx, ly)` to `(x, y) + R(rot) (lx, s*ly)` with `s = -1` on the back, where
`R(a) (u, v) = (u cos a + v sin a, -u sin a + v cos a)`; a pad's angle is `rot + s*lrot`.

Acceptance against pcbnew on the prepared kaebench tasks:
`kae/.venv/bin/python kae/scripts/board_acceptance.py {verify,roundtrip,place,loadtime} --tasks DIR`.

`kae` never imports `kaebench` (or research scripts); methods plug into the harness with
`kaebench run --command`.
