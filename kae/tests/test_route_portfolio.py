# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.portfolio: parallel, growing restarts; the first clean attempt wins and stops the rest."""
import json
import os
import sys
import time

from kae.route import portfolio

FAKE = '''
import json, sys, time
a = sys.argv[1:]
out, seed, budget, rep = a[2], int(a[a.index("--seed") + 1]), float(a[a.index("--time") + 1]), a[a.index("--report") + 1]
k = seed % 1000
# attempt 0 and 1 hang (a board that does not close), attempt 2 is clean quickly, 3 leaves 2 open
if k in (0, 1):
    time.sleep(budget + 300 if "HANG" in a else budget + 3)
time.sleep(0.5)
open(out, "w").write("board %d" % k)
fin = dict(errors=0, unconnected=0 if k == 2 else 2)
open(rep, "w").write(json.dumps(dict(repair=dict(final=fin))))
'''


def _fake(tmp_path, monkeypatch):
    (tmp_path / "fake_router.py").write_text(FAKE)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.syspath_prepend(str(tmp_path))


def test_first_clean_attempt_wins_and_stops_the_others(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch)
    out = tmp_path / "out.kicad_pcb"
    t = time.monotonic()
    rep = portfolio.run("in.kicad_pcb", out, seed=0, time_s=600, parallel=3, first_s=40, router="fake_router",
                        extra=["HANG"], workdir=tmp_path / "wd", log=lambda m: None)
    assert rep["stop"] == "clean" and rep["best"]["k"] == 2 and tuple(rep["best"]["rank"]) == (0, 0)
    assert out.read_text() == "board 2"
    assert time.monotonic() - t < 60                       # the hanging attempts were stopped, not waited for
    assert sorted(a["k"] for a in rep["attempts"] if a["stopped"]) == [0, 1]   # and still reported


def test_without_a_clean_attempt_the_best_is_kept_and_budgets_grow(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch)
    (tmp_path / "fake_router.py").write_text(FAKE.replace("0 if k == 2 else 2", "2 if k == 3 else 5"))
    out = tmp_path / "out.kicad_pcb"
    rep = portfolio.run("in.kicad_pcb", out, seed=0, time_s=160, parallel=2, first_s=20, growth=2.0,
                        router="fake_router", workdir=tmp_path / "wd", log=lambda m: None)
    assert rep["stop"] == "time"
    assert tuple(rep["best"]["rank"]) == (0, 2) and out.read_text() == "board 3"
    budgets = [a["budget"] for a in rep["attempts"]]
    assert max(budgets) > min(budgets)                     # later waves got longer attempts


def test_attempts_that_fail_at_once_end_the_run(tmp_path, monkeypatch):
    (tmp_path / "broken_router.py").write_text("import sys; sys.exit(2)\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    t = time.monotonic()
    rep = portfolio.run("in.kicad_pcb", tmp_path / "out.kicad_pcb", time_s=600, parallel=2, first_s=60,
                        router="broken_router", workdir=tmp_path / "wd", log=lambda m: None)
    assert rep["stop"] == "failed" and rep["best"] is None and len(rep["attempts"]) == 4
    assert time.monotonic() - t < 30


def test_mixed_routers_cycle_through_their_modules(tmp_path, monkeypatch):
    # router a leaves 1 open, router b is clean: the mix finds b's clean board
    def fake(name, unconnected):
        (tmp_path / f"{name}.py").write_text(
            "import json, sys\na = sys.argv[1:]\nopen(a[2], 'w').write('%s')\n" % name
            + "open(a[a.index('--report') + 1], 'w').write(json.dumps(dict(repair=dict(final="
            + "dict(errors=0, unconnected=%d)))))\n" % unconnected)
    fake("router_a", 1)
    fake("router_b", 0)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    out = tmp_path / "out.kicad_pcb"
    rep = portfolio.run("in.kicad_pcb", out, time_s=300, parallel=2, first_s=60,
                        router=["router_a", ("router_b", ["--x"])], workdir=tmp_path / "wd", log=lambda m: None)
    assert rep["stop"] == "clean" and rep["best"]["router"] == "router_b" and out.read_text() == "router_b"
    assert {a["router"] for a in rep["attempts"]} == {0, 1}


def test_a_clean_board_of_the_first_router_is_preferred(tmp_path, monkeypatch):
    # the first router is clean but slow; the second is clean at once: the first one's board is kept
    (tmp_path / "slow_a.py").write_text(
        "import json, sys, time\na = sys.argv[1:]\ntime.sleep(6)\nopen(a[2], 'w').write('slow_a')\n"
        "open(a[a.index('--report') + 1], 'w').write(json.dumps(dict(repair=dict(final=dict(errors=0, unconnected=0)))))\n")
    (tmp_path / "fast_b.py").write_text(
        "import json, sys\na = sys.argv[1:]\nopen(a[2], 'w').write('fast_b')\n"
        "open(a[a.index('--report') + 1], 'w').write(json.dumps(dict(repair=dict(final=dict(errors=0, unconnected=0)))))\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    out = tmp_path / "out.kicad_pcb"
    rep = portfolio.run("in.kicad_pcb", out, time_s=300, parallel=2, first_s=60,
                        router=["slow_a", "fast_b"], workdir=tmp_path / "wd", log=lambda m: None)
    assert rep["stop"] == "clean" and rep["best"]["router"] == "slow_a" and out.read_text() == "slow_a"


def test_rank_reads_both_routers_reports():
    assert portfolio._rank(dict(repair=dict(final=dict(errors=0, unconnected=2)))) == (0, 2)
    assert portfolio._rank(dict(critical={}, bridge=dict(repair=dict(final=dict(errors=1, unconnected=0))))) == (1, 0)
    assert portfolio._rank(dict(drc=dict(errors=0, unconnected=3, by_type={}))) == (0, 3)
    assert portfolio._rank(dict(bridge=dict(drc=dict(errors=2, unconnected=1)))) == (2, 1)
    assert portfolio._rank(dict(status="error")) == (float("inf"), float("inf"))
