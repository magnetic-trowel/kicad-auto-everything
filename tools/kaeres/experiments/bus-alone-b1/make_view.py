# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run in KiCad's Python: the bus-only view of a board. Pads of nets outside KEEP get no net; tracks, vias and zones of
those nets are removed. Usage: make_view.py IN.kicad_pcb OUT.kicad_pcb KEEP_FILE"""
import pcbnew
import sys

src, dst, keep_file = sys.argv[1:4]
keep = set(open(keep_file).read().split("\n")) - {""}
board = pcbnew.LoadBoard(src)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname() not in keep:
            pad.SetNetCode(0)
tracks = [t for t in board.Tracks() if t.GetNetname() not in keep]
zones = [z for z in board.Zones() if z.GetNetname() not in keep]
for t in tracks:
    board.Remove(t)
for z in zones:
    board.Remove(z)
board.Save(dst)
