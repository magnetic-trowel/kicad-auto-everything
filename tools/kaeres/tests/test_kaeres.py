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


def test_method_table_means_over_common_boards():
    """DRC errors and physics are also averaged over the boards every method scored."""
    def row(method, board, errors, phys, status="ok"):
        return dict(method=method, board=board, status=status, clean=errors == 0, completion=1.0, unconnected=0,
                    errors=errors, timed_out=False, partial=False, cpu_s=1.0, attempts=1, runtime_s=1.0,
                    physics_total=phys, physics_vs_human=None, module_ratio_median=None)
    rows = [row("a", "b1", 0, 1.0), row("a", "hard", 10, 9.0),
            row("b", "b1", 2, 3.0), row("b", "hard", None, None, status="no_output")]
    out = kaeres.method_table(rows, ["a", "b"], "t")
    assert "DRC errors / board, 1 common boards" in out[2] and "physics Σu, 1 common boards" in out[2]
    cells = {ln.split(" | ")[0].strip("| "): ln.split(" | ") for ln in out[4:6]}
    assert cells["a"][6:8] == ["5.00 (2)", "0.00"] and cells["b"][6:8] == ["2.00 (1)", "2.00"]
    assert cells["a"][14:16] == ["5.000 (2)", "1.000"] and cells["b"][14:16] == ["3.000 (1)", "3.000"]
