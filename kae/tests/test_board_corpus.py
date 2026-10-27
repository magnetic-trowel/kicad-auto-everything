# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Load regressions on prepared kaebench boards (skipped when kae-work/ is absent).

KAE_TASKS points at a tasks directory (default: kae-work-v2/tasks, then kae-work/tasks).
`kae/scripts/board_acceptance.py loadall` sweeps every board; this test keeps the boards
that broke the loader before.
"""
import os
from pathlib import Path

import pytest

from kae.board import kicad_file

ROOT = Path(__file__).resolve().parents[2]
REGRESSIONS = [
    "pcbcorpus-waterloo-rocketry-canhw-processor",       # degenerate courtyard contour
    "piotr-binkowski-kintex-pcie-board-kintex-pcie",     # same; card edge from a footprint
    "pcbcorpus-tomtor-stm32-rfm95-pcb-avr-lora-805",     # four pads sharing one uuid
    "pcbcorpus-justbuchanan-oasis-pcb",                   # slots closed by a line drawn back
    "pcbcorpus-wibblyghost-southerly-split-keeb-southerly-ca3258",  # duplicated courtyards
]


def _tasks():
    env = os.environ.get("KAE_TASKS")
    for d in ([Path(env)] if env else []) + [ROOT / "kae-work-v2" / "tasks", ROOT / "kae-work" / "tasks"]:
        if d.is_dir():
            return d
    return None


@pytest.mark.parametrize("bid", REGRESSIONS)
@pytest.mark.parametrize("kind", ["reference", "place/input"])
def test_regression_boards_load(bid, kind):
    tasks = _tasks()
    p = tasks / bid / kind / "board.kicad_pcb" if tasks else None
    if p is None or not p.exists():
        pytest.skip("prepared kaebench boards not available")
    b = kicad_file.load(p)
    assert b.footprints and len({f.uuid for f in b.footprints}) == len(b.footprints)
    if kind == "reference":
        assert b.outline and all(f.on_board for f in b.footprints if f.locked)
