# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""offset_eval.py BOARD OPERATING OUT DX DY: kae.excite.evaluate with its default window (pads' box + 3 mm)
shifted by (DX, DY) mm, so the 0.25 mm raster samples the same copper at another origin (the raster noise
check of routing-stages.md section 5). DX = DY = 0 is the evaluator's own window."""
import os
import sys

from kae.board import transform
from kae.board.kicad_file import load
from kae.excite import evaluate as EV


def main(argv):
    board, op, out, dx, dy = argv[0], argv[1], argv[2], float(argv[3]), float(argv[4])
    b = load(board)
    xs, ys = [], []
    for fp in b.footprints:
        for p in fp.pads:
            x, y = transform.pad_xy(fp, p)
            xs.append(x)
            ys.append(y)
    w = (min(xs) - 3 + dx, min(ys) - 3 + dy, max(xs) + 3 + dx, max(ys) + 3 + dy)
    return EV.main([board, "--pitch", "0.25", "--max-cells", os.environ.get("KAE_EVAL_MAX_CELLS", "4000000"), "--intent", op, "-o", out, "--window", *map(str, w)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
