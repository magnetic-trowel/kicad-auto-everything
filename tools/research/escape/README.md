<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Escape study scripts (rules-escape)

Open connections at dense packages (pitch <= 0.65 mm, BGA, WLCSP) in our route runs next to
the human layouts. `ESC_WORK` is the work directory, `BOARDS_JSON` the board list (one entry per
board: human_run, route.run, human_drc, ...).

1. `dump.py IN.kicad_pcb[.gz] OUT.json` (KiCad's Python): pads, tracks, vias, zones of a board.
2. `opens.py`: each open connection of the route runs, with the dense pin(s) it ends on (`pkg.py`
   classifies footprints: pitch, kind, BGA rings).
3. `compare.py`: per dense pin, the human's escape and ours (`esc.py`: via in pad, dog-bone,
   surface, zone; direction, width, via distance), and whether it is open in our run.
4. `slack.py` (escape feasibility under the board's rules; `rules.json` holds each board's .kicad_pro design rules and net classes), `sites.py` (what occupies the
   four dog-bone sites of each BGA ball), `corridor.py` and `walls.py` (foreign copper in a
   row package's straight escape corridors), `runopens.py` (opens of A/B runs by ring).
