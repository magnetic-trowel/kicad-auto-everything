# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""restart.py with a stand-in kicad-cli (no KiCad): the final pass on the kept board."""
import json
import os
import subprocess
import sys
from pathlib import Path

RESTART = Path(__file__).resolve().parents[1] / "restart.py"

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
