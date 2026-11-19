# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""restart.py with a stand-in kicad-cli (no KiCad): the final pass on the kept board."""
import gzip
import importlib.util
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

RESTART = Path(__file__).resolve().parents[1] / "restart.py"
_spec = importlib.util.spec_from_file_location("restart_under_test", RESTART)
restart = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(restart)

# a kicad-cli that reads "OPEN=n" from the board and reports n unconnected items
FAKE_CLI = """#!/usr/bin/env python3
import json, re, sys
args = sys.argv[1:]
out = args[args.index("--output") + 1]
board = open(args[-1]).read()
m = re.search(r"OPEN=(\\d+)", board)
n = int(m.group(1)) if m else 0
json.dump(dict(violations=[], unconnected_items=[dict(items=[dict(description=f"Pad 1 [N{i}] of U1")])
                                                for i in range(n)]), open(out, "w"))
"""


def _run(tmp_path, attempt, final, time_s=200, extra=()):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    cli = bin_ / "kicad-cli"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    inp = tmp_path / "in" / "board.kicad_pcb"
    inp.parent.mkdir()
    inp.write_text("(kicad_pcb OPEN=5)\n")
    out = tmp_path / "out" / "board.kicad_pcb"
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", KAE_KICAD_WRAP="")
    work = tmp_path / "work"
    work.mkdir()
    args = [sys.executable, str(RESTART), "--input", str(inp), "--output", str(out), "--time", str(time_s),
            "--parallel", "1", "--first-s", "25", "--max-attempts", "1", *extra]
    if final:
        args += ["--final", final, "--final-s", "20"]
    r = subprocess.run([*args, "--", attempt], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    return r, out, json.loads((work / "restarts" / "summary.json").read_text())


def test_final_pass_replaces_the_kept_board_when_better(tmp_path):
    r, out, summary = _run(tmp_path, "echo '(kicad_pcb OPEN=2)' > @OUT@",
                           "cp @BEST@ @OUT@.tmp && test -f @IN@ && echo '(kicad_pcb OPEN=0 time=@TIME@)' > @OUT@")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OPEN=0" in out.read_text()
    fin = summary["attempt_log"][-1]
    assert fin["k"] == "final" and fin["kept"] and fin["resumed_from"] == 0
    assert summary["best_attempt"] == "final" and summary["best_rank"] == [0, 0, 0, 0, 0]


def test_final_pass_kept_only_when_better(tmp_path):
    r, out, summary = _run(tmp_path, "echo '(kicad_pcb OPEN=2)' > @OUT@", "echo '(kicad_pcb OPEN=3)' > @OUT@")
    assert r.returncode == 0
    assert "OPEN=2" in out.read_text()
    assert summary["attempt_log"][-1]["kept"] is False and summary["best_attempt"] == 0


def test_final_time_is_reserved_from_the_start(tmp_path):
    """The attempt's budget leaves the final pass its time: it is not what the attempt left over."""
    r, out, summary = _run(tmp_path, "echo '(kicad_pcb OPEN=2)' > @OUT@",
                           "echo '(kicad_pcb OPEN=1 t=@TIME@)' > @OUT@", time_s=300,
                           extra=["--first-s", "1000"])
    a0, fin = summary["attempt_log"][0], summary["attempt_log"][-1]
    assert a0["budget"] <= 300 - 75 - 30   # the final reserve (20 s + a judgement + 10 s) came off it
    assert fin["budget"] >= 20 and fin["kept"]


def test_no_final_pass_on_a_clean_board(tmp_path):
    r, out, summary = _run(tmp_path, "echo '(kicad_pcb OPEN=0)' > @OUT@", "echo '(kicad_pcb OPEN=0)' > @OUT@")
    assert all(d["k"] != "final" for d in summary["attempt_log"])


# a kicad-cli that lists 3 unconnected items under the project's severity, filtered like KiCad:
# none when the check is ignored, only with --severity-all when it is a warning
SEVERITY_CLI = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
out, board = args[args.index("--output") + 1], args[-1]
sev = json.load(open(board[:-len(".kicad_pcb")] + ".kicad_pro"))["board"]["design_settings"]["rule_severities"]
sev = sev["unconnected_items"]
shown = sev == "error" or (sev == "warning" and "--severity-all" in args)
json.dump(dict(violations=[], unconnected_items=[dict(severity=sev, items=[])] * (3 if shown else 0)), open(out, "w"))
"""


def test_judge_counts_unconnected_items_of_any_severity(tmp_path, monkeypatch):
    """keytops-blank makes unconnected items warnings: --severity-error read 0 of its 43 open
    connections; a project that ignores them makes DRC list none whatever the flag."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("restart_mod", RESTART)
    restart = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(restart)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kicad-cli").write_text(SEVERITY_CLI)
    (bin_ / "kicad-cli").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setenv("KAE_KICAD_WRAP", "")
    for sev in ("error", "warning", "ignore"):
        inp = tmp_path / sev / "in" / "board.kicad_pcb"
        inp.parent.mkdir(parents=True)
        inp.write_text("(kicad_pcb)\n")
        pro = {"board": {"design_settings": {"rule_severities": {"unconnected_items": sev}}}}
        inp.with_suffix(".kicad_pro").write_text(json.dumps(pro))
        board = tmp_path / sev / "a0" / "board.kicad_pcb"
        board.parent.mkdir()
        board.write_text("(kicad_pcb)\n")
        assert restart.drc(board, inp, 60)["unconnected"] == 3, sev
        assert restart.judge(board, inp, {}, 60) == (0, 1, 3, 0, 0), sev
        assert json.loads(inp.with_suffix(".kicad_pro").read_text()) == pro  # the task's project untouched


# a kicad-cli that reports one clearance error per line of a .kicad_dru beside the board
RULES_CLI = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
out, board = args[args.index("--output") + 1], args[-1]
dru = board[:-len(".kicad_pcb")] + ".kicad_dru"
n = len(open(dru).read().splitlines()) if os.path.exists(dru) else 0
json.dump(dict(violations=[dict(type="clearance", severity="error", items=[])] * n, unconnected_items=[]), open(out, "w"))
"""


def test_judge_ignores_a_rules_file_the_method_left_when_the_task_has_none(tmp_path, monkeypatch):
    """The judge ranks every attempt under the task's rules: a .kicad_dru the method wrote beside its
    board is replaced by the task's, and removed when the task has none (before, it stayed and judged)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kicad-cli").write_text(RULES_CLI)
    (bin_ / "kicad-cli").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setenv("KAE_KICAD_WRAP", "")
    inp = tmp_path / "in" / "board.kicad_pcb"
    inp.parent.mkdir()
    inp.write_text("(kicad_pcb)\n")
    board = tmp_path / "a0" / "board.kicad_pcb"
    board.parent.mkdir()
    board.write_text("(kicad_pcb)\n")
    board.with_suffix(".kicad_dru").write_text("(version 1)\n(rule a)\n(rule b)\n")   # the method's own
    assert restart.drc(board, inp, 60)["types"] == {}
    assert not board.with_suffix(".kicad_dru").exists()
    inp.with_suffix(".kicad_dru").write_text("(version 1)\n")                         # the task's own
    board.with_suffix(".kicad_dru").write_text("(version 1)\n(rule a)\n(rule b)\n")
    assert restart.drc(board, inp, 60)["types"] == {"clearance": 1}


def test_judge_counts_past_drcs_cap_of_499_with_pcbnew(tmp_path, monkeypatch):
    """kicad-cli lists at most 499 unconnected items: polarfire-som's ~150 attempts all read 499, so
    the wrapper chose blind. Past the cap the count comes from pcbnew (a stand-in here)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("restart_cap", RESTART)
    restart = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(restart)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    # the stand-in kicad-cli must not run on the stand-in python3 below
    (bin_ / "kicad-cli").write_text(FAKE_CLI.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1))
    (bin_ / "kicad-cli").chmod(0o755)
    (bin_ / "python3").write_text("#!/bin/sh\necho '{\"unconnected\": 812}'\n")
    (bin_ / "python3").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setenv("KAE_KICAD_WRAP", "")
    inp = tmp_path / "in" / "board.kicad_pcb"
    inp.parent.mkdir()
    inp.write_text("(kicad_pcb)\n")
    for n, want in ((498, 498), (499, 812)):
        board = tmp_path / f"a{n}" / "board.kicad_pcb"
        board.parent.mkdir()
        board.write_text(f"(kicad_pcb) OPEN={n}\n")
        assert restart.drc(board, inp, 60)["unconnected"] == want
    (bin_ / "python3").write_text("#!/bin/sh\nexit 1\n")            # no KiCad Python: the capped count stays
    board = tmp_path / "nopy" / "board.kicad_pcb"
    board.parent.mkdir()
    board.write_text("(kicad_pcb) OPEN=499\n")
    assert restart.drc(board, inp, 60)["unconnected"] == 499


def test_judge_reports_unconnected_items_a_project_ignores(tmp_path):
    """A project that sets unconnected_items to "ignore" makes kicad-cli list none at all
    (gamaphy-freedom-rp2040): the judge's own copy turns the check back on, other
    severities stay as the board set them."""
    import json
    import restart
    pro = tmp_path / "board.kicad_pro"
    sev = {"unconnected_items": "ignore", "clearance": "warning"}
    pro.write_text(json.dumps({"board": {"design_settings": {"rule_severities": sev}}}))
    restart.report_unconnected(pro)
    got = json.loads(pro.read_text())["board"]["design_settings"]["rule_severities"]
    assert got == {"unconnected_items": "error", "clearance": "warning"}
    pro.write_text("{}")
    restart.report_unconnected(pro)                       # no severities: left alone
    assert pro.read_text() == "{}"


def test_final_pass_runs_last_mile_then_finish(tmp_path):
    """--final then --finish: the last mile's board is judged (its drc.json is the finish's @DRC@),
    the finish runs on the board kept and replaces it when no worse; only the last mile's time is
    reserved, the finish runs in what is left."""
    finish = ("test -s @DRC@ && grep -q OPEN=0 @BEST@ && test @DRC_S@ && "
              "sed 's/OPEN=0/OPEN=0 finished/' @BEST@ > @OUT@ && "
              "echo '{\"parts\": {\"ran\": [\"tails\", \"taut\"], \"skipped\": {\"power\": \"time\"}}, \"drc_runs\": 1}'")
    r, out, summary = _run(tmp_path, "echo '(kicad_pcb OPEN=2)' > @OUT@",
                           "echo '(kicad_pcb OPEN=0)' > @OUT@", time_s=300,
                           extra=["--finish", finish, "--finish-s", "20", "--first-s", "1000"])
    assert r.returncode == 0, r.stdout + r.stderr
    kinds = [d["k"] for d in summary["attempt_log"]]
    assert kinds == [0, "final", "finish"]
    fin, fz = summary["attempt_log"][1], summary["attempt_log"][2]
    assert fin["kept"] and fz["kept"] and fz["resumed_from"] == "final"
    assert "finished" in out.read_text()
    assert summary["finish"]["parts"]["skipped"] == {"power": "time"} and summary["finish"]["drc_runs"] == 1
    # reserved from the start: the last mile's 20 s with a judgement and 10 s; nothing for the finish
    b0 = summary["attempt_log"][0]["budget"]
    assert 300 - 75 - (20 + 10) - 15 <= b0 <= 300 - 75 - (20 + 10)
    assert fin["budget"] >= 20 and fz["budget"] >= 20


def test_attempts_defer_their_own_finish_to_the_wrapper(tmp_path):
    """With --finish, attempts get KAE_FINISH_KEPT=1 (kae.route.cli route then skips its own finish)."""
    r, out, summary = _run(tmp_path, "echo \"(kicad_pcb OPEN=0 K=$KAE_FINISH_KEPT)\" > @OUT@", "",
                           extra=["--finish", "exit 3"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "K=1" in out.read_text()
    (tmp_path / "nofinish").mkdir()
    r2, out2, _ = _run(tmp_path / "nofinish", "echo \"(kicad_pcb OPEN=0 K=$KAE_FINISH_KEPT)\" > @OUT@", "")
    assert "K=)" in out2.read_text()


def test_clear_runs_once_on_the_kept_board_with_its_own_allowance(tmp_path):
    """With --clear, attempts and the final pass get KAE_CLEAR_KEPT=1, and the clear pass runs once on the kept
    board after --final, with --clear-s as its @TIME@ (not the time routing left); its board is kept when no worse,
    and its wall time is recorded on its own."""
    r, out, summary = _run(tmp_path, "echo \"(kicad_pcb OPEN=2 C=$KAE_CLEAR_KEPT)\" > @OUT@",
                           "echo \"(kicad_pcb OPEN=1 C=$KAE_CLEAR_KEPT)\" > @OUT@",
                           extra=["--clear", "echo \"(kicad_pcb OPEN=1 cleared time=@TIME@ C=$KAE_CLEAR_KEPT)\" > @OUT@",
                                  "--clear-s", "77"])
    assert r.returncode == 0, r.stdout + r.stderr
    text = out.read_text()
    assert "cleared time=77 C=)" in text, text
    kinds = [d["k"] for d in summary["attempt_log"]]
    assert kinds[-2:] == ["final", "clear"], kinds
    assert summary["clear_kept"] is True and summary["clear_wall_s"] is not None
    attempt0 = (tmp_path / "work" / "restarts")
    assert any("C=1" in p.read_text() for p in attempt0.glob("*/board.kicad_pcb")), "attempts must defer clearing"


def test_finish_skipped_when_routing_left_too_little_time(tmp_path):
    """No reserve: a finish that would get less than FINISH_RUN_MIN_S is skipped, with a hazard."""
    import time as _t
    import types
    a = types.SimpleNamespace(finish="true", finish_s=20.0, time=100.0)
    best = dict(k="final", rank=(0, 0, 3, 0, 0))
    fz = restart.finish_pass(a, best, tmp_path / "in.kicad_pcb", {}, tmp_path, _t.monotonic() + 25.0, 5.0,
                             None, None, None)
    assert fz["skipped"].startswith("time:") and not fz["kept"] and fz["estimate_s"] == 20
    hz = restart.finish_hazards(fz)
    assert [h["code"] for h in hz] == ["finish_part_skipped"]
    rep = tmp_path / "report.json"
    rep.write_text(json.dumps(dict(hazards=[], hazard_summary=dict(info=0, total=0, shown=0))))
    restart.add_hazards(rep, hz)
    got = json.loads(rep.read_text())
    assert got["hazards"][0]["code"] == "finish_part_skipped" and got["hazard_summary"]["info"] == 1


def test_finish_killed_or_failed_is_a_hazard():
    hz = restart.finish_hazards(dict(k="finish", killed=True, rc=-9, budget=100, wall_s=105, kept=False,
                                     hazards=[dict(code="finish_part_skipped", severity="info"),
                                              dict(code="drc_clearance", severity="warn")]))
    assert [h["code"] for h in hz] == ["finish_failed", "finish_part_skipped"]
    kept = restart.finish_hazards(dict(k="finish", rc=0, kept=True, hazards=[dict(code="drc_clearance")]))
    assert [h["code"] for h in kept] == ["drc_clearance"]


def test_finish_runs_on_a_clean_board_and_is_not_kept_when_worse(tmp_path):
    r, out, summary = _run(tmp_path, "echo '(kicad_pcb OPEN=0)' > @OUT@", "",
                           extra=["--finish", "echo '(kicad_pcb OPEN=1)' > @OUT@", "--finish-s", "20"])
    assert r.returncode == 0, r.stdout + r.stderr
    fz = summary["attempt_log"][-1]
    assert fz["k"] == "finish" and not fz["kept"] and "OPEN=0" in out.read_text()


def test_kept_attempts_report_and_its_fresh_origin_are_stored(tmp_path):
    """A kept fresh attempt's JSON report goes to report.json; when a final pass is kept instead, that
    router's report does, and the fresh attempt it descends from goes to report-origin.json."""
    loop = """echo '{"iterations": [1, 2], "stop": "time"}'; echo '(kicad_pcb OPEN=2)' > @OUT@"""
    r, out, summary = _run(tmp_path, loop, """echo '{"route": 1}'; echo '(kicad_pcb OPEN=0)' > @OUT@""")
    assert r.returncode == 0, r.stdout + r.stderr
    wd = tmp_path / "work" / "restarts"
    assert summary["best_attempt"] == "final"
    assert json.loads((wd / "report.json").read_text()) == {"route": 1}
    origin = json.loads((wd / "report-origin.json").read_text())
    assert origin["iterations"] == [1, 2] and origin["stop"] == "time" and origin["origin_attempt"] == 0


def test_attempts_keep_their_freerouting_telemetry(tmp_path):
    """Each attempt's record in summary.json holds the Freerouting telemetry of its route report."""
    rep = ('{"router": {"report": {"telemetry": {"loops": [{"unrouted": [3, 1]}]}}}, '
           '"repair": {"rounds": [{"router": {"telemetry": {"pour_cut_off": 2}}}]}}')
    r, out, summary = _run(tmp_path, f"echo '{rep}'; echo '(kicad_pcb OPEN=0)' > @OUT@", "")
    assert r.returncode == 0, r.stdout + r.stderr
    fr = summary["attempt_log"][0]["fr"]
    assert fr["first"]["loops"][0]["unrouted"] == [3, 1] and fr["repair"] == [{"pour_cut_off": 2}]


def _raw_attempts(wd, sizes):
    for k, n in enumerate(sizes):
        d = wd / f"a{k}" / "fr-raw"
        d.mkdir(parents=True)
        (d / "1-1-board.log").write_bytes(os.urandom(n))   # random: gzip cannot shrink it


def _fr_summary(n_chars):
    return dict(attempt_log=[dict(k=0, fr=dict(first=dict(loops=[dict(unrouted=[1] * n_chars)])))])


def test_raw_freerouting_files_all_kept_under_the_limit(tmp_path):
    _raw_attempts(tmp_path, [1000, 2000])
    rec = restart.keep_fr_raw(tmp_path, _fr_summary(5), limit=100_000)
    assert rec["parts_kept"] == 2 and rec["parts_dropped"] == 0 and rec["stored_bytes"] == (tmp_path / "fr-telemetry.tar").stat().st_size
    with tarfile.open(tmp_path / "fr-telemetry.tar") as t:
        assert json.load(t.extractfile("manifest.json"))["dropped"] == []
        assert len(gzip.decompress(t.extractfile("a1/1-1-board.log.gz").read())) == 2000
    assert not list(tmp_path.glob("a*/fr-raw"))


def test_raw_freerouting_files_over_the_limit_drop_the_bulkiest_first_and_say_so(tmp_path):
    _raw_attempts(tmp_path, [60_000, 30_000, 5_000])
    summary = _fr_summary(200)
    rec = restart.keep_fr_raw(tmp_path, summary, limit=50_000)
    tar = tmp_path / "fr-telemetry.tar"
    compact = len(json.dumps(summary, indent=1)) - len(json.dumps(dict(attempt_log=[dict(k=0)]), indent=1))
    assert tar.stat().st_size + compact <= 50_000
    assert rec["parts_dropped"] == 1 and rec["dropped_raw_bytes"] == 60_000
    with tarfile.open(tar) as t:
        m = json.load(t.extractfile("manifest.json"))
        assert [d["name"] for d in m["dropped"]] == ["a0/1-1-board.log.gz"] and m["limit_bytes"] == 50_000
        assert {p["name"] for p in m["parts"]} == {"a1/1-1-board.log.gz", "a2/1-1-board.log.gz"}


def test_raw_freerouting_files_that_cannot_fit_leave_a_record_and_no_tar(tmp_path):
    _raw_attempts(tmp_path, [2000])
    rec = restart.keep_fr_raw(tmp_path, _fr_summary(5), limit=100)
    assert rec["file"] is None and rec["parts_dropped"] == 1 and not (tmp_path / "fr-telemetry.tar").exists()


def test_attempts_are_told_where_to_keep_raw_freerouting_files(tmp_path):
    r, out, summary = _run(tmp_path, "mkdir -p $KAE_FR_RAW_DIR; echo log > $KAE_FR_RAW_DIR/1-1-board.log; echo '(kicad_pcb OPEN=0)' > @OUT@", "")
    assert r.returncode == 0, r.stdout + r.stderr
    assert summary["fr_raw"]["parts_kept"] == 1 and summary["fr_raw"]["file"] == "fr-telemetry.tar"


def test_a_failed_attempt_keeps_why(tmp_path):
    """An attempt that exits non-zero keeps its report's status and error and the end of its log."""
    fail = """echo 'Traceback: pcbnew worker did not start' >&2; echo '{"status": "error", "error": "PcbnewError: x"}'; exit 2"""
    r, out, summary = _run(tmp_path, fail, "")
    rec = summary["attempt_log"][0]
    assert rec["rc"] == 2
    assert rec["failure"]["status"] == "error" and rec["failure"]["error"] == "PcbnewError: x"
    assert "pcbnew worker did not start" in rec["failure"]["log_tail"]


def test_a_kept_fresh_attempt_has_no_origin_report(tmp_path):
    loop = """echo '{"iterations": [1], "stop": "no improvement"}'; echo '(kicad_pcb OPEN=0)' > @OUT@"""
    r, out, summary = _run(tmp_path, loop, "")
    assert r.returncode == 0, r.stdout + r.stderr
    wd = tmp_path / "work" / "restarts"
    assert json.loads((wd / "report.json").read_text())["stop"] == "no improvement"
    assert not (wd / "report-origin.json").exists()


# ------------------------------------------------------------------ choose-better portfolio (--alt-env)
# each arm writes its board with a marker of its setting; the tie-break scores it (arm B's loop is the better)
ARM_ATTEMPT = "echo \"(kicad_pcb OPEN=${OPENS:-0} arm=${HL:-A})\" > @OUT@"
TIEBREAK = ("python3 -c \"import json,sys; b=open(sys.argv[1]).read(); "
            "json.dump(dict(score=1.0 if 'arm=B' in b else 2.0), open(sys.argv[2], 'w'))\" @BOARD@ @OUT@")


def test_choose_better_keeps_the_arm_with_the_better_quote_among_equal_ranks(tmp_path):
    r, out, summary = _run(tmp_path, ARM_ATTEMPT, "", extra=[
        "--parallel", "2", "--max-attempts", "2", "--alt-env", "HL=B", "--tiebreak", TIEBREAK])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "arm=B" in out.read_text()
    cb = summary["choose_better"]
    assert cb["kept_arm"] == "B" and cb["alt_env"] == {"HL": "B"}
    assert [d["arm"] for d in summary["attempt_log"]] == ["A", "B"]
    (t,) = cb["ties"]
    assert t["rank"] == [0, 0, 0, 0, 0] and t["switched"] == (t["kept_arm"] == "A")


def test_choose_better_never_trades_rank_for_the_quote(tmp_path):
    """Arm B's quote is better but its board leaves a connection open: KiCad's rank decides."""
    r, out, summary = _run(tmp_path, ARM_ATTEMPT, "", extra=[
        "--parallel", "2", "--max-attempts", "2", "--alt-env", "HL=B OPENS=1", "--tiebreak", TIEBREAK])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "arm=A" in out.read_text() and summary["choose_better"]["kept_arm"] == "A"
    assert summary["choose_better"]["ties"] == []


def test_the_final_pass_runs_with_the_kept_boards_arm(tmp_path):
    """Arm A leaves 3 connections open, arm B 1: B is kept and its final pass runs with B's setting."""
    r, out, summary = _run(tmp_path, "echo \"(kicad_pcb OPEN=${OPENS:-3} arm=${HL:-A})\" > @OUT@",
                           "echo \"(kicad_pcb OPEN=0 final=${HL:-A})\" > @OUT@", extra=[
                               "--parallel", "2", "--max-attempts", "2", "--alt-env", "HL=B OPENS=1"])
    assert r.returncode == 0, r.stdout + r.stderr
    fin = summary["attempt_log"][-1]
    assert fin["k"] == "final" and fin["arm"] == "B" and "final=B" in out.read_text()


def test_choose_better_keeps_arm_a_when_the_tiebreak_cannot_decide(tmp_path):
    """Arm B's board cannot be scored (the command writes no score): arm A, the method as given, is kept."""
    none = "python3 -c \"import json,sys; json.dump(dict(score=None), open(sys.argv[1], 'w'))\" @OUT@"
    r, out, summary = _run(tmp_path, ARM_ATTEMPT, "", extra=[
        "--parallel", "2", "--max-attempts", "2", "--alt-env", "HL=B", "--tiebreak", none])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "arm=A" in out.read_text() and summary["choose_better"]["kept_arm"] == "A"
def test_work_mode_gives_the_finish_its_finish_s(tmp_path, monkeypatch):
    """KAE_BUDGET=work: the passes get --final-s / --finish-s of nominal work when given (a 70/30 split of
    restarts and finish), else their fixed shares of --time; the attempts' plan is what is left."""
    monkeypatch.setenv("KAE_BUDGET", "work")
    finish = "sed 's/OPEN=1/OPEN=1 t=@TIME@/' @BEST@ > @OUT@"
    r, out, summary = _run(tmp_path, "echo '(kicad_pcb OPEN=2)' > @OUT@",
                           "echo '(kicad_pcb OPEN=1)' > @OUT@", time_s=1000,
                           extra=["--finish", finish, "--finish-s", "300", "--first-s", "2000"])
    assert r.returncode == 0, r.stdout + r.stderr
    log = {d["k"]: d for d in summary["attempt_log"]}
    assert log["finish"]["budget"] == 300 and log["final"]["budget"] == 20
    assert log[0]["budget"] <= 1000 - 300 - 20
    a = SimpleNamespace(time=1000.0, final="x", final_s=0.0, finish="y", finish_s=0.0)
    assert restart.work_final_s(a) == 150.0 and restart.work_finish_s(a) == 100.0


# a kicad-cli that reports one unconnected item per routing item of the board, naming it by UUID
UUID_CLI = """#!/usr/bin/env python3
import json, re, sys
args = sys.argv[1:]
out = args[args.index("--output") + 1]
us = re.findall(r'\\(uuid "([^"]+)"\\)', open(args[-1]).read())
json.dump(dict(violations=[], unconnected_items=[dict(items=[dict(description=f"Track [N{i}]", uuid=u)])
                                                for i, u in enumerate(us)]), open(out, "w"))
"""
_TRACKS = ('(kicad_pcb\n\t(segment\n\t\t(start 0 0)\n\t\t(end 1 0)\n\t\t(uuid "{a}")\n\t)\n'
           '\t(segment\n\t\t(start 2 0)\n\t\t(end 3 0)\n\t\t(uuid "{b}")\n\t)\n)\n')


def test_work_mode_judge_keeps_its_report_beside_the_board_with_the_boards_uuids(tmp_path, monkeypatch):
    """Work mode judges a canonical copy in a temporary directory; its report must still be left beside
    the attempt's board, as in time mode (--finish's @DRC@), naming the
    board's own copper (the copy's UUIDs are derived from content)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kicad-cli").write_text(UUID_CLI.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1))
    (bin_ / "kicad-cli").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setenv("KAE_KICAD_WRAP", "")
    monkeypatch.setattr(restart, "WORK", True)
    monkeypatch.setattr(restart, "SC", None)
    inp = tmp_path / "in" / "board.kicad_pcb"
    inp.parent.mkdir()
    inp.write_text("(kicad_pcb)\n")
    a, b = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    board = tmp_path / "a0" / "board.kicad_pcb"
    board.parent.mkdir()
    board.write_text(_TRACKS.format(a=b, b=a))
    assert restart.drc(board, inp, 60)["unconnected"] == 2
    rep = json.loads(board.with_name("drc.json").read_text())
    assert sorted(it["uuid"] for u in rep["unconnected_items"] for it in u["items"]) == [a, b]
    assert sorted(p.name for p in board.parent.iterdir()) == ["board.kicad_pcb", "drc.json"]   # copy removed


def test_completion_first_runs_alt_on_a_clean_board_and_keeps_it_when_no_worse(tmp_path):
    """Phase 1 routes everything (OPEN=0, clean): the second run is --alt, kept when it ranks no worse."""
    r, out, s = _run(tmp_path, "echo '(kicad_pcb OPEN=0 first)' > @OUT@", None, time_s=200,
                     extra=("--policy", "completion-first", "--alt", "echo '(kicad_pcb OPEN=0 alt)' > @OUT@"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["second"] == "alt" and s["kept"] == 2 and "alt" in out.read_text()


def test_completion_first_restarts_again_when_the_first_board_is_open(tmp_path):
    """Phase 1 leaves opens: the second run is COMMAND again with the next seed (never --alt); the better is kept."""
    r, out, s = _run(tmp_path, "if [ @SEED@ -ge 1000 ]; then echo '(kicad_pcb OPEN=1 second)' > @OUT@; "
                               "else echo '(kicad_pcb OPEN=3 first)' > @OUT@; fi", None, time_s=200,
                     extra=("--policy", "completion-first", "--alt", "echo '(kicad_pcb OPEN=0 alt)' > @OUT@"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["second"] == "restart" and s["kept"] == 2 and "second" in out.read_text()
    assert [p["seed"] for p in s["phases"]] == [0, 1]


def test_alt_alone_makes_completion_first_the_policy(tmp_path):
    """--alt without --policy runs completion-first (the default policy whenever an alternative is given)."""
    r, out, s = _run(tmp_path, "echo '(kicad_pcb OPEN=0 first)' > @OUT@", None, time_s=200,
                     extra=("--alt", "echo '(kicad_pcb OPEN=0 alt)' > @OUT@"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["policy"] == "completion-first" and s["second"] == "alt"


def test_completion_first_open_alt_works_on_the_first_board_when_it_is_open(tmp_path):
    """Phase 1 leaves opens: with --open-alt the second run works on phase 1's board (@BEST@), not a fresh restart;
    kept when no worse."""
    r, out, s = _run(tmp_path, "echo '(kicad_pcb OPEN=3 first)' > @OUT@", None, time_s=200,
                     extra=("--policy", "completion-first", "--alt", "echo '(kicad_pcb OPEN=0 alt)' > @OUT@",
                            "--open-alt", "grep -q first @BEST@ && echo '(kicad_pcb OPEN=1 polished)' > @OUT@"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["second"] == "open-alt" and s["kept"] == 2 and "polished" in out.read_text()


def test_open_rest_spends_the_windows_unused_budget(tmp_path):
    """--open-rest: the open-alt run reports it used little of its budget (@REPORT@ seconds), so one more run gets
    the rest: COMMAND with the next seed on an open board, --alt with --open-rest-alt once the board is clean."""
    win = ("sed 's/first/win/' @BEST@ > @OUT@ && echo '{\"seconds\": 10}' > @REPORT@")
    cmd = ("if [ @SEED@ -ge 2 ]; then echo '(kicad_pcb OPEN=1 third)' > @OUT@; "
           "else echo '(kicad_pcb OPEN=3 first)' > @OUT@; fi")
    r, out, s = _run(tmp_path, cmd, None, time_s=600,
                     extra=("--policy", "completion-first", "--alt", "echo '(kicad_pcb OPEN=0 alt)' > @OUT@",
                            "--open-alt", win, "--open-rest"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["second"] == "open-alt" and s["third"] == "restart" and s["kept"] == 3 and "third" in out.read_text()
    assert (tmp_path / "work" / "restarts" / "report-windows.json").exists()


def test_open_rest_alt_runs_alt_on_a_board_the_windows_completed(tmp_path):
    win = "echo '(kicad_pcb OPEN=0 win)' > @OUT@ && echo '{\"seconds\": 10}' > @REPORT@"
    r, out, s = _run(tmp_path, "echo '(kicad_pcb OPEN=3 first)' > @OUT@", None, time_s=600,
                     extra=("--policy", "completion-first", "--alt", "echo '(kicad_pcb OPEN=0 alt)' > @OUT@",
                            "--open-alt", win, "--open-rest", "--open-rest-alt"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["third"] == "alt" and s["kept"] == 3 and "alt" in out.read_text()
