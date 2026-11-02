# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaeres.py: which board physics evaluates, how runs are matched to tasks, report means (stdlib only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kaeres  # noqa: E402


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("(kicad_pcb)\n")
    return p


def test_physics_of_a_place_run_reads_the_probes_routed_board(tmp_path):
    """A place task's score/board.kicad_pcb has no copper: physics read every module as missing."""
    unrouted = _touch(tmp_path / "score" / "board.kicad_pcb")
    probe = _touch(tmp_path / "probe" / "score" / "board.kicad_pcb")
    ok = dict(status="ok", probe=dict(status="ok"))
    assert kaeres.routed_board("route", ok, tmp_path) == unrouted
    for kind in ("place", "place-fixed"):
        assert kaeres.routed_board(kind, ok, tmp_path) == probe
        assert kaeres.routed_board(kind, dict(ok, probe=dict(status="adapter_error")), tmp_path) is None
        assert kaeres.routed_board(kind, dict(status="ok"), tmp_path) is None
    assert kaeres.routed_board("route", dict(status="no_output"), tmp_path) is None
    joint = _touch(tmp_path / "j" / "score" / "routing" / "board.kicad_pcb")
    assert kaeres.routed_board("joint", ok, tmp_path / "j") == joint
