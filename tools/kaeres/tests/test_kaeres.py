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
        return dict(method=method, board=board, attempt=0, status=status, clean=errors == 0, completion=1.0, unconnected=0,
                    errors=errors, timed_out=False, partial=False, cpu_s=1.0, attempts=1, runtime_s=1.0,
                    physics_total=phys, physics_vs_human=None, module_ratio_median=None)
    rows = [row("a", "b1", 0, 1.0), row("a", "hard", 10, 9.0),
            row("b", "b1", 2, 3.0), row("b", "hard", None, None, status="no_output")]
    out = kaeres.method_table(rows, ["a", "b"], "t")
    assert "DRC errors / board, 1 common boards" in out[2] and "physics Σu, 1 common boards" in out[2]
    cells = {ln.split(" | ")[0].strip("| "): ln.split(" | ") for ln in out[4:6]}
    assert cells["a"][9:11] == ["5.00 (2)", "0.00"] and cells["b"][9:11] == ["2.00 (1)", "2.00"]
    assert cells["a"][17:19] == ["5.000 (2)", "1.000"] and cells["b"][17:19] == ["3.000 (1)", "3.000"]


def _r(method, board, attempt, clean, status="ok", unconnected=None):
    return dict(method=method, board=board, attempt=attempt, status=status, clean=clean, completion=1.0 if clean else 0.5,
                unconnected=0 if clean else (unconnected or 3), errors=0, errors_by_type="{}", timed_out=False, partial=False,
                cpu_s=1.0, attempts=1, runtime_s=1.0, physics_total=None, physics_vs_human=None, module_ratio_median=None)


def test_method_table_reports_k_and_cpk_over_attempts():
    rows = [_r("a", "b1", 0, False), _r("a", "b1", 1, True), _r("a", "b2", 0, False), _r("a", "b2", 1, False)]
    out = kaeres.method_table(rows, ["a"], "t")
    cells = out[4].split(" | ")
    assert cells[1:7] == ["2", "2", "0.000", "—", "2", "0.500"]   # boards, ok, cp1, xc, k, cpk


def test_paired_table_tests_cp1_and_cpk_and_lists_flips():
    rows = []
    for i in range(8):
        rows += [_r("base", f"b{i}", 0, False), _r("new", f"b{i}", 0, True)]
    rows += [_r("base", "x", 0, True), _r("new", "x", 0, False, unconnected=7), _r("base", "pending", 0, True)]
    out = "\n".join(kaeres.paired_table(rows, "base", ["base", "new"], {}))
    line = next(ln for ln in out.splitlines() if ln.startswith("| new | 9 |"))
    assert "| 1 |" in line                                    # one board not run by new yet
    assert "+8 / −1" in line and "B better" in line
    assert "| new | x | base | 7 |" in out


def test_method_cpu_s_ignores_cpu_lost_in_the_sandbox():
    lost = dict(runtime_s=600, method_usage=dict(cpu_s=0.006, processes=1), adapter_meta=dict(sandboxed=True))
    assert kaeres.method_cpu_s(lost) is None
    assert kaeres.method_cpu_s(dict(lost, job_steps=dict(run=dict(cgroup_cpu_s=2400.0)))) == 2400.0
    assert kaeres.method_cpu_s(dict(lost, work=dict(cpu_s=6198.8))) == 6198.8
    fr = dict(runtime_s=600, method_usage=dict(cpu_s=640.0, processes=3), adapter_meta={})
    assert kaeres.method_cpu_s(fr) == 640.0


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


def _task_dir(root, board_text="(kicad_pcb)\n", repo="local:/a"):
    """A kaebench tasks/<board> directory with a route input."""
    import json
    t = root / "b1"
    for sub in ("reference", "route/input"):
        (t / sub).mkdir(parents=True, exist_ok=True)
        (t / sub / "board.kicad_pcb").write_text(board_text)
        (t / sub / "drc.json").write_text(json.dumps({"date": str(root)}))  # dated: not content
    rec = dict(id="b1", repo=repo, task_spec=9, pcb_sha256="s", split="A", reference=dict(stats={"pads": 2}),
               tasks=dict(route=dict(input_stats={"tracks": 0})), roundtrip=dict(route=dict(ok=True)))
    (t / "task.json").write_text(json.dumps(rec))
    return t


def test_task_content_covers_inputs_not_paths_or_reports(tmp_path):
    a = kaeres.task_content(_task_dir(tmp_path / "a", repo="local:/a"), "route")
    b = kaeres.task_content(_task_dir(tmp_path / "b", repo="local:/b"), "route")
    c = kaeres.task_content(_task_dir(tmp_path / "c", board_text="(kicad_pcb (uuid x))\n"), "route")
    assert a and a == b and a != c
    assert kaeres.task_content(_task_dir(tmp_path / "d"), "place") is None


def _store(tmp_path, monkeypatch, old_content, new_content):
    """A board with a spec-9 route task (a run of method m on it, prepared by harness h9) and a spec-10
    route task of the same board file and KiCad, each with the recorded content."""
    import json
    monkeypatch.setattr(kaeres, "STORE", tmp_path)
    bd = tmp_path / "boards" / "b1"
    for tid, spec, hc, content in (("old000000000", 9, "h9", old_content), ("new000000000", 10, "h10", new_content)):
        (bd / "tasks" / tid).mkdir(parents=True)
        (bd / "tasks" / tid / "task.json").write_text(json.dumps(dict(
            id=tid, prepared_by=hc, recipe=dict(board_sha256="s", task_spec=spec, kind="route", kicad="10.0.7"))))
        (bd / "tasks" / tid / "content.json").write_text(json.dumps({hc: content}))
    (bd / "runs" / "m.a0").mkdir(parents=True)
    (bd / "runs" / "m.a0" / "run.json").write_text(json.dumps(dict(
        run="m.a0", method_id="m", attempt=0, task_id="old000000000", harness_commit="h9")))


def test_a_run_on_a_task_of_equal_content_is_reused(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch, "v1:same", "v1:same")
    d, r = kaeres.find_run("b1", "m", 0, "new000000000")
    assert r is not None and r["task_id"] == "old000000000"


def test_a_run_on_a_task_of_other_content_is_not_reused(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch, "v1:random-uuids", "v1:seeded")
    assert kaeres.find_run("b1", "m", 0, "new000000000") == (None, None)
    assert kaeres.find_run("b1", "m", 0, "old000000000")[1] is not None  # still on its own task


def test_content_of_another_harness_or_board_file_is_not_an_alias(tmp_path, monkeypatch):
    import json
    _store(tmp_path, monkeypatch, "v1:same", "v1:same")
    old = tmp_path / "boards" / "b1" / "tasks" / "old000000000"
    # the content recorded for the old task came from a harness that did not make the run
    (old / "content.json").write_text(json.dumps({"h9-other": "v1:same"}))
    assert kaeres.find_run("b1", "m", 0, "new000000000") == (None, None)
    (old / "content.json").write_text(json.dumps({"h9": "v1:same"}))
    tj = json.loads((old / "task.json").read_text())
    tj["recipe"]["board_sha256"] = "t"  # another board file
    (old / "task.json").write_text(json.dumps(tj))
    assert kaeres.find_run("b1", "m", 0, "new000000000") == (None, None)


def test_older_spec_methods_prepare_with_the_experiments_harness_from_spec_10(monkeypatch):
    specs = {"h8": 8, "h9": 9, "h10": 10, "h10b": 10}
    monkeypatch.setattr(kaeres, "harness_task_spec", lambda c: specs.get(c))
    assert kaeres.prep_harness("h9", "h10") == "h10"
    assert kaeres.prep_harness("h10b", "h10") == "h10b"
    assert kaeres.prep_harness("h8", "h9") == "h8"  # before spec 10 a method keeps its own tasks
    assert kaeres.prep_harness("h9", "unknown") == "h9"


def _human_store(tmp_path, monkeypatch, evals):
    """A board whose human run on task t1 has these evaluations ({evaluator: errors_by_type or None}, in age order)."""
    run = tmp_path / "human.a0"
    (run / "evals").mkdir(parents=True)
    for i, (ev, types) in enumerate(evals.items()):
        kaeres.write_json(run / "evals" / f"{ev}.json", dict(evaluator=ev, at=f"2026-11-0{i + 1}T00:00:00+00:00",
                                                             score=dict(errors_by_type=types) if types is not None else None))
    monkeypatch.setattr(kaeres, "board_runs", lambda bid: [(run, dict(method_id="h", attempt=0, task_id="t1"))])
    monkeypatch.setattr(kaeres, "on_task", lambda bid, r, tid: tid == r["task_id"])
    return dict(id="h")


def _drc_records(base, types):
    bugs = kaeres.Bugs("b1")
    kaeres._drc_bugs(bugs, "m", types, base)
    return bugs.items


def test_drc_bugs_without_the_experiments_human_eval_use_the_newest_and_say_so(tmp_path, monkeypatch):
    """baseline-2611b: no human eval under its evaluator read as an empty human layout, so every
    method error was reported as beyond the human layout's 0."""
    human = _human_store(tmp_path, monkeypatch, {"zz-old": dict(drill_out_of_range=9), "aa-new": dict(drill_out_of_range=4)})
    base = kaeres.human_drc_baseline("b1", human, "t1", "exp-eval")
    assert (base["source"], base["evaluator"]) == ("fallback", "aa-new")  # newest by time, not by file name
    assert _drc_records(base, dict(drill_out_of_range=4)) == []
    [rec] = _drc_records(base, dict(drill_out_of_range=6))
    assert rec["count"] == 2 and rec["signature"] == "m:drc:drill_out_of_range:human-fallback"
    assert "beyond the human layout's 4" in rec["detail"] and "aa-new" in rec["detail"]
    assert rec["human_baseline"] == dict(source="fallback", evaluator="aa-new")


def test_drc_bugs_against_the_experiments_own_human_eval_keep_their_signature(tmp_path, monkeypatch):
    human = _human_store(tmp_path, monkeypatch, {"exp-eval": dict(clearance=1), "newer": dict(clearance=7)})
    base = kaeres.human_drc_baseline("b1", human, "t1", "exp-eval")
    assert base["source"] == "exact" and base["types"] == dict(clearance=1)
    [rec] = _drc_records(base, dict(clearance=3))
    assert rec["signature"] == "m:drc:clearance" and rec["detail"] == "2 clearance error(s) beyond the human layout's 1"


def test_a_clean_human_eval_is_a_real_zero_and_another_task_is_a_fallback(tmp_path, monkeypatch):
    human = _human_store(tmp_path, monkeypatch, {"exp-eval": {}})
    assert kaeres.human_drc_baseline("b1", human, "t1", "exp-eval")["source"] == "exact"
    base = kaeres.human_drc_baseline("b1", human, "other-task", "exp-eval")
    assert base["source"] == "fallback" and base["evaluator"] == "exp-eval"
    assert "on another task" in _drc_records(base, dict(clearance=1))[0]["detail"]


def test_no_scored_human_run_is_no_baseline_and_not_zero(tmp_path, monkeypatch):
    human = _human_store(tmp_path, monkeypatch, {"exp-eval": None})
    base = kaeres.human_drc_baseline("b1", human, "t1", "exp-eval")
    assert base["source"] == "none"
    [rec] = _drc_records(base, dict(clearance=3))
    assert rec["count"] == 3 and rec["signature"] == "m:drc:clearance:no-human-baseline"
    assert "no human baseline" in rec["detail"] and "beyond" not in rec["detail"]
    monkeypatch.setattr(kaeres, "board_runs", lambda bid: [])
    assert kaeres.human_drc_baseline("b1", human, "t1", "e")["source"] == "none"
    assert kaeres.human_drc_baseline("b1", None, "t1", "e")["source"] == "none"


def test_exp_rows_rebases_stored_drc_records_without_writing_them(tmp_path, monkeypatch):
    """Reports are made from each run's bugs.json, which holds what its job knew; they must not
    repeat a stale comparison, and a report must not rewrite those files."""
    store = tmp_path / "s"
    monkeypatch.setattr(kaeres, "STORE", store)
    human = dict(id="h", name="human", recipe=dict(runner=dict(type="reference")))
    monkeypatch.setattr(kaeres, "methods", lambda: {"h": human})
    e = dict(name="x", harness=dict(commit="c" * 40), evaluators=dict(drc="exp", physics="p"), attempts=1, methods=[dict(id="m", name="meth")])
    kaeres.exp_dir("x").mkdir(parents=True)
    (kaeres.exp_dir("x") / "boards.txt").write_text("b1\n")
    hd, md = kaeres.board_dir("b1") / "runs" / "h", kaeres.board_dir("b1") / "runs" / "m"
    kaeres.write_json(hd / "evals" / "old.json", dict(at="2026-11-01", score=dict(errors_by_type=dict(drill=4))))
    kaeres.write_json(md / "evals" / "exp.json", dict(at="2026-11-02", score=dict(errors_by_type=dict(drill=4, track=1))))
    stale = [dict(board="b1", method="meth", category="drc", signature="meth:drc:drill", detail="4 drill error(s) beyond the human layout's 0",
                  drc_type="drill", count=4, evidence=[]),
             dict(board="b1", method="meth", category="over_time", signature="meth:over_time", detail="slow", evidence=[])]
    kaeres.write_json(md / "bugs.json", stale)
    before = (md / "bugs.json").read_bytes()
    runs = dict(h=(hd, dict(method_id="h", attempt=0, task_id="t")), m=(md, dict(method_id="m", attempt=0, task_id="t")))
    monkeypatch.setattr(kaeres, "find_run", lambda b, mid, att=0, tid=None: runs[mid] if att == 0 else (None, None))
    monkeypatch.setattr(kaeres, "exp_task_id", lambda *a: "t")
    monkeypatch.setattr(kaeres, "_run_kind", lambda r: "route")
    monkeypatch.setattr(kaeres, "human_physics", lambda *a: None)
    monkeypatch.setattr(kaeres, "run_view", lambda *a, **k: dict(board="b1"))
    _, bugs, _ = kaeres.exp_rows(e)
    assert sorted(b["signature"] for b in bugs) == ["meth:drc:track:human-fallback", "meth:over_time"]
    assert (md / "bugs.json").read_bytes() == before


def test_restart_reports_are_kept_with_the_run(tmp_path):
    """J13: the kept attempt's report survives the deleted work directory; kaebench keeps it as an artifact."""
    art, tmp = tmp_path / "artifacts", tmp_path / "run"
    art.mkdir()
    tmp.mkdir()
    (art / "summary.json").write_text('{"attempt_log": []}')
    (art / "report.json").write_text('{"iterations": []}')
    kaeres._keep_restart_files(art, tmp)
    assert (tmp / "restarts.json").read_text() == '{"attempt_log": []}'
    assert (tmp / "restart-report.json").read_text() == '{"iterations": []}'
    assert not (tmp / "restart-report-origin.json").exists()


def _rebuild_boards():
    import importlib.util
    spec = importlib.util.spec_from_file_location("rebuild_boards", Path(__file__).resolve().parent.parent / "rebuild_boards.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rebuild_call_matches_the_harness_scorers_signature():
    rb = _rebuild_boards()

    class New:
        @staticmethod
        def _rebuild(op, out, inp, rules, work, ref=None, flags=()):
            return flags

    class Old:
        @staticmethod
        def _rebuild(op, out, inp, rules, work, ref=None):
            return "no flags"
    assert rb.rebuild_call(New, "transplant-routing", 1, 2, 3, 4, 5) == ("--zones",)
    assert rb.rebuild_call(Old, "transplant-routing", 1, 2, 3, 4, 5) == "no flags"


def test_rephysics_job_fails_when_no_run_could_be_rebuilt(tmp_path, monkeypatch, capsys):
    """A rephysics job whose every rebuild failed exited 0 with 0 evaluations (a harness venv without _rebuild(flags=)):
    the queue saw it done, nothing was measured."""
    import json
    d = tmp_path / "runs" / "r1"
    d.mkdir(parents=True)
    r = dict(run="r1", harness_commit="h" * 40, task_id="t", attempt=0, method_id="m")
    monkeypatch.setattr(kaeres, "corpus_rows", lambda: {"b1": dict(path="boards/b1")})
    monkeypatch.setattr(kaeres, "evaluators_for", lambda h, k, kc: dict(physics="pid"))
    monkeypatch.setattr(kaeres, "kicad_version", lambda: "10.0.7")
    monkeypatch.setattr(kaeres, "_rephysics_todo", lambda bid, mids, pid: [(d, r)])
    monkeypatch.setattr(kaeres, "board_size_mb", lambda row: 1.0)
    monkeypatch.setattr(kaeres, "env_sh", dict)
    monkeypatch.setattr(kaeres, "code_dir", lambda c: tmp_path / "code")
    monkeypatch.setattr(kaeres, "board_dir", lambda bid: tmp_path)
    monkeypatch.setattr(kaeres, "_run_kind", lambda r: "route")
    monkeypatch.setenv("KAEQ_SCRATCH", str(tmp_path))

    def fake_run(cmd, log, env, timeout):
        out = Path(cmd[cmd.index("--out") + 1])
        out.write_text(json.dumps(dict(input="i", board_sha256=None, runs=dict(
            r1=dict(error="TypeError: _rebuild() got an unexpected keyword argument 'flags'")))))
        return 0, False
    monkeypatch.setattr(kaeres, "run_logged", fake_run)
    a = type("A", (), dict(board="b1", harness="h" * 40, kae="k" * 40, methods="m"))()
    assert kaeres.cmd_rephysics_job(a) == 1
    out = capsys.readouterr().out
    assert "0 physics evaluation(s)" in out and "unexpected keyword" in out and "no run could be rebuilt" in out


def _xr(method, board, xc, kind="route"):
    return dict(_r(method, board, 0, False), xc=xc, kind=kind)


def test_xc_is_clean_net_of_the_route_inputs_errors():
    drc = dict(errors_by_type=dict(courtyards_overlap=2, solder_mask_bridge=1))
    row = dict(valid=True, unconnected=0, errors_by_type='{"courtyards_overlap": 2}')
    assert kaeres.clean_net_of_input(row, drc) is True
    assert kaeres.clean_net_of_input(dict(row, errors_by_type='{"courtyards_overlap": 3}'), drc) is False
    assert kaeres.clean_net_of_input(dict(row, errors_by_type='{"clearance": 1}'), drc) is False
    assert kaeres.clean_net_of_input(dict(row, unconnected=1), drc) is False
    assert kaeres.clean_net_of_input(dict(row, valid=False), drc) is False
    assert kaeres.clean_net_of_input(row, None) is None
    assert kaeres.clean_net_of_input(row, dict(errors_by_type=None)) is None   # input DRC never measured
    assert kaeres.clean_net_of_input(dict(row, errors_by_type="{}"), dict(errors_by_type={})) is True


def test_method_table_marks_xc_of_placing_methods():
    rows = [_xr("router", "b1", True), _xr("router", "b2", False), _xr("placer", "b1", True, "joint-fixed"),
            _xr("placer", "b2", True, "joint-fixed"), _xr("unknown", "b1", None)]
    out = kaeres.method_table(rows, ["router", "placer", "unknown"], "t")
    assert "xc (clean net of input; † placing method, not comparable)" in out[2]
    assert out[4].split(" | ")[4] == "0.500" and out[5].split(" | ")[4] == "1.000†" and out[6].split(" | ")[4] == "—"
