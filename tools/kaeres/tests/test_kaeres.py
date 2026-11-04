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


def test_runs_of_another_task_are_missing_and_not_reported(tmp_path, monkeypatch):
    """A run made on an older board file, task spec or KiCad satisfied missing() and was reported
    beside fresh ones; only runs on the experiment's own task count now."""
    corpus, code = tmp_path / "corpus", tmp_path / "code"
    (corpus / "boards" / "b1").mkdir(parents=True)
    (corpus / "boards" / "b1" / "board.kicad_pcb").write_text("(kicad_pcb)\n")
    prep = code / "bench" / "src" / "kaebench" / "prepare.py"
    prep.parent.mkdir(parents=True)
    prep.write_text("TASK_SPEC = 8\n")
    monkeypatch.setattr(kaeres, "CORPUS", corpus)
    monkeypatch.setattr(kaeres, "corpus_rows", lambda: {"b1": dict(path="boards/b1")})
    monkeypatch.setattr(kaeres, "code_dir", lambda c: code)
    monkeypatch.setattr(kaeres, "_run_kind", lambda r: "route")
    monkeypatch.setattr(kaeres, "_TASK_SPECS", {})
    monkeypatch.setattr(kaeres, "_BOARD_SHAS", {})
    e = dict(name="x", harness=dict(commit="c" * 40), kicad="10.0.7", attempts=1,
             methods=[dict(id="fresh", name="fresh"), dict(id="old", name="old")])
    tid = kaeres.exp_task_id(e, "b1", "route")
    sha = kaeres.sha256_file(corpus / "boards" / "b1" / "board.kicad_pcb")
    assert tid == kaeres.ident(dict(board_sha256=sha, task_spec=8, kind="route", kicad="10.0.7"))
    runs = [(tmp_path / "r1", dict(method_id="fresh", attempt=0, task_id=tid)),
            (tmp_path / "r2", dict(method_id="old", attempt=0, task_id="0" * 12))]
    monkeypatch.setattr(kaeres, "board_runs", lambda bid: runs)
    assert kaeres.missing(e, "b1") == [("old", 0)]
    monkeypatch.setattr(kaeres, "_TASK_SPECS", {e["harness"]["commit"]: None})  # harness code not here: any task
    assert kaeres.missing(e, "b1") == []


def test_a_place_run_is_clean_only_if_its_placement_is_legal(tmp_path):
    """Parts left off the outline are no DRC error: a clean probe route did not make an illegal placement clean."""
    import json
    (tmp_path / "evals").mkdir()
    r = dict(method_name="p", method_id="p", run="p.a0", attempt=0, task_id="t", status="ok")
    probe = dict(valid=True, clean=True, completion=1.0, errors=0, unconnected=0)
    for legal in (True, False):
        place = dict(valid=True, legal=legal, outside=0 if legal else 2)
        (tmp_path / "evals" / "drc1.json").write_text(json.dumps(dict(score=place, probe=dict(score=probe))))
        v = kaeres.run_view("b", tmp_path, r, dict(drc="drc1", physics="ph"))
        assert (v["clean"], v["legal"], v["valid"]) == (legal, legal, True)


def test_exp_create_refuses_a_method_prepared_on_another_task_spec(monkeypatch, tmp_path):
    import pytest
    K = kaeres
    specs = {"h9": 9, "h8": 8}
    monkeypatch.setattr(K, "harness_task_spec", lambda c: specs[c])
    monkeypatch.setattr(K, "exp_dir", lambda n: tmp_path / n)
    monkeypatch.setattr(K, "main_repo", lambda: str(tmp_path))
    monkeypatch.setattr(K, "git", lambda repo, *a: a[-1])
    monkeypatch.setattr(K, "on_remote", lambda repo, c: True)
    monkeypatch.setattr(K, "ensure_harness", lambda *a, **k: None)
    monkeypatch.setattr(K, "ensure_method_code", lambda m: None)
    monkeypatch.setattr(K, "corpus_rows", lambda: {"b1": {}})
    meth = {"fr": dict(id="fr0000000000", name="freerouting", code=dict(harness=dict(commit="h8")))}
    monkeypatch.setattr(K, "find_method", lambda k: meth[k])
    a = type("A", (), dict(name="x", method=["fr"], harness="h9", kae="h9", boards=None, attempts=1, description=""))
    with pytest.raises(SystemExit, match="another task spec"):
        K.cmd_exp_create(a)
