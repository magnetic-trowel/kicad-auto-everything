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


def test_history_of_open_nets_reaches_later_attempts(tmp_path):
    attempt = "cp \"$KAE_ROUTE_HISTORY\" seen.json; echo '(kicad_pcb OPEN=2)' > @OUT@"
    r, out, summary = _run(tmp_path, attempt, "", extra=["--max-attempts", "2", "--history"])
    assert r.returncode == 0, r.stdout + r.stderr
    work = tmp_path / "work" / "restarts"
    assert json.loads((work / "history.json").read_text()) == {"N0": 2, "N1": 2}
    assert json.loads((work / "a0" / "seen.json").read_text()) == {}               # nothing judged yet
    assert json.loads((work / "a1" / "seen.json").read_text()) == {"N0": 1, "N1": 1}
    assert [d["open_nets"] for d in summary["attempt_log"]] == [["N0", "N1"], ["N0", "N1"]]


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
    the finish runs on the board kept and replaces it when no worse; both times are reserved."""
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
    # reserved from the start: the last mile's 20 s and the finish's 20 s, each with a judgement and 10 s
    assert summary["attempt_log"][0]["budget"] <= 300 - 2 * (20 + 10) - 30
    assert fin["budget"] >= 20 and fz["budget"] >= 20


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
