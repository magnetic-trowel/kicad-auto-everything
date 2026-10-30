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

## Results (2026-10-30, kae.route.cli single attempt, opens / errors by kicad-cli on the output)

Escape pre-pass (`--set escapes=soft`, kae/src/kae/route/escape.py) against the same code
without it; `--set passes=8`, 1800 s, seeds 1-3, Freerouting on a private slot set:

| board | base | escapes (spoke margin) | escapes (DRC-checked) |
|---|---|---|---|
| gecko5education (6 L, BGA-381) | 123 / 99 / 94, 0 err | 66 / 71 / 81, 0 err | 79 / 70 / 80, 0 err |
| nekoink (4 L, BGA-289) | 119 / 105 / 114, 11 err | 100 / 94 / 97, 11 / 13 / 14 err | 115 / 99 / 97, 11 err |

Opens at BGA balls of ring >= 2: gecko5 38 / 34 / 35 -> 0 / 0 / 3 (0 / 3 / 2 checked), nekoink
37 / 26 / 41 -> 15 / 15 / 12 (14 / 9 / 9). sdi-mipi (8 L, three BGAs, 1800 s, seed 1): 202 -> 179
open, ring >= 2 107 -> 58. 2400 s, seed 1: gecko5 129 -> 83, nekoink 124 -> 98. Zero-slack row
stubs alone (kata0510, edison, 2 seeds): no change in opens (they move to the stub's far end).
