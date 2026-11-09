# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run in KiCad's Python: the bus-only view of a board. Pads of nets outside KEEP get no net; tracks, vias and zones of
those nets are removed. Usage: make_view.py IN.kicad_pcb OUT.kicad_pcb KEEP_FILE"""
import sys

import pcbnew

src, dst, keep_file = sys.argv[1:4]
keep = {ln.rstrip("\n") for ln in open(keep_file) if ln.strip()}
board = pcbnew.LoadBoard(src)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname() not in keep:
            pad.SetNetCode(0)
for t in [t for t in board.Tracks() if t.GetNetname() not in keep]:
    board.Remove(t)
for z in [z for z in board.Zones() if z.GetNetname() not in keep]:
    board.Remove(z)
board.Save(dst)
