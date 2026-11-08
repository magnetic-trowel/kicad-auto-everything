# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pad-entry counts of several versions of one routed board (kae.route.pad_trim.stats, touching
same-net pad shapes merged), one JSON line per board.

    python tools/research/routing/pad_entry_compare.py BEFORE.kicad_pcb NAME=OTHER.kicad_pcb ...

The pads come from BEFORE (KiCad's DSN export); every version must have the same placement."""
import json
import sys
from pathlib import Path

from kae.route import pad_trim as T


def main(argv):
    before = argv[0]
    info = T._info(before)
    out = {"before": T.stats(Path(before).read_text(encoding="utf-8"), info)}
    for a in argv[1:]:
        name, path = a.split("=", 1)
        out[name] = T.stats(Path(path).read_text(encoding="utf-8"), info)
    print(json.dumps(dict(board=before, **out)))


if __name__ == "__main__":
    main(sys.argv[1:])
