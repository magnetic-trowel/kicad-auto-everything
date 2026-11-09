# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.portfolio: parallel, growing restarts; the first attempt routed fully wins and stops the
rest; attempts rank by unconnected, then errors beyond the input's own; the kept board gets a final
last mile."""
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
                        extra=["HANG"], workdir=tmp_path / "wd", log=lambda m: None, final=None)
    assert rep["stop"] == "clean" and rep["best"]["k"] == 2 and tuple(rep["best"]["rank"]) == (0, 0)
    assert out.read_text() == "board 2"
    assert time.monotonic() - t < 60                       # the hanging attempts were stopped, not waited for
    assert sorted(a["k"] for a in rep["attempts"] if a["stopped"]) == [0, 1]   # and still reported


def test_without_a_clean_attempt_the_best_is_kept_and_budgets_grow(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch)
    (tmp_path / "fake_router.py").write_text(FAKE.replace("0 if k == 2 else 2", "2 if k == 3 else 5"))
    out = tmp_path / "out.kicad_pcb"
    rep = portfolio.run("in.kicad_pcb", out, seed=0, time_s=160, parallel=2, first_s=20, growth=2.0,
                        router="fake_router", workdir=tmp_path / "wd", log=lambda m: None, final=None)
    assert rep["stop"] == "time"
    assert tuple(rep["best"]["rank"]) == (2, 0) and out.read_text() == "board 3"
    budgets = [a["budget"] for a in rep["attempts"]]
    assert max(budgets) > min(budgets)                     # later waves got longer attempts


def test_attempts_that_fail_at_once_end_the_run(tmp_path, monkeypatch):
    (tmp_path / "broken_router.py").write_text("import sys; sys.exit(2)\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    t = time.monotonic()
    rep = portfolio.run("in.kicad_pcb", tmp_path / "out.kicad_pcb", time_s=600, parallel=2, first_s=60,
                        router="broken_router", workdir=tmp_path / "wd", log=lambda m: None, final=None)
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
                        router=["router_a", ("router_b", ["--x"])], workdir=tmp_path / "wd", log=lambda m: None,
                        final=None)
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
                        router=["slow_a", "fast_b"], workdir=tmp_path / "wd", log=lambda m: None, final=None)
    assert rep["stop"] == "clean" and rep["best"]["router"] == "slow_a" and out.read_text() == "slow_a"


def test_rank_reads_both_routers_reports():
    assert portfolio._rank(dict(repair=dict(final=dict(errors=0, unconnected=2)))) == (2, 0)
    assert portfolio._rank(dict(critical={}, bridge=dict(repair=dict(final=dict(errors=1, unconnected=0))))) == (0, 1)
    assert portfolio._rank(dict(drc=dict(errors=0, unconnected=3, by_type={}))) == (3, 0)
    assert portfolio._rank(dict(bridge=dict(drc=dict(errors=2, unconnected=1)))) == (1, 2)
    assert portfolio._rank(dict(mode="last mile only", final=dict(errors=0, unconnected=4))) == (4, 0)
    assert portfolio._rank(dict(status="error")) == (float("inf"), float("inf"))


def test_rank_puts_unconnected_first_and_counts_only_errors_beyond_the_input():
    # (1 moved mask bridge, 0 open) beats (0 errors, 30 open); the input's own errors are not counted
    a = dict(repair=dict(final=dict(errors=0, unconnected=30, by_type={})))
    b = dict(repair=dict(final=dict(errors=1, unconnected=0, by_type=dict(solder_mask_bridge=1))))
    assert portfolio._rank(b) < portfolio._rank(a)
    c = dict(repair=dict(final=dict(errors=173, unconnected=0, by_type=dict(solder_mask_bridge=170, clearance=3))))
    assert portfolio._rank(c, dict(solder_mask_bridge=172, clearance=3)) == (0, 0)
    assert portfolio._rank(c, dict(solder_mask_bridge=168)) == (0, 5)


INPUT_ERR = '''
import json, sys, time
a = sys.argv[1:]
k = int(a[a.index("--seed") + 1]) % 1000
if k == 0:
    time.sleep(float(a[a.index("--time") + 1]) + 300)        # never ends on its own
time.sleep(0.5)
open(a[2], "w").write("board %d" % k)
# every board keeps the input's 4 mask bridges; attempt 1 also leaves 1 open, attempt 2 none
fin = dict(errors=4, unconnected=0 if k == 2 else 1, by_type=dict(solder_mask_bridge=4))
open(a[a.index("--report") + 1], "w").write(json.dumps(dict(repair=dict(final=fin))))
'''


def test_an_input_with_errors_of_its_own_still_ends_early_when_routed_fully(tmp_path, monkeypatch):
    (tmp_path / "err_router.py").write_text(INPUT_ERR)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.setattr(portfolio, "_input_errors", lambda inp, wd, deadline: dict(solder_mask_bridge=4))
    out = tmp_path / "out.kicad_pcb"
    t = time.monotonic()
    rep = portfolio.run("in.kicad_pcb", out, time_s=600, parallel=3, first_s=60, router="err_router",
                        workdir=tmp_path / "wd", log=lambda m: None)
    assert rep["stop"] == "clean" and rep["best"]["k"] == 2 and tuple(rep["best"]["rank"]) == (0, 0)
    assert rep["final"] is None and out.read_text() == "board 2"        # routed fully: no final pass
    assert time.monotonic() - t < 60


LASTMILE = '''
import json, sys
a = sys.argv[1:]
assert a[0] == "lastmile"
inp, board, out = a[1:4]
open(out, "w").write(open(board).read() + " + last mile")
open(a[a.index("--report") + 1], "w").write(json.dumps(dict(mode="last mile only",
    final=dict(errors=0, unconnected=0, by_type={}), budget=float(a[a.index("--time") + 1]))))
'''


def test_the_kept_board_gets_a_final_last_mile_with_time_reserved(tmp_path, monkeypatch):
    # every attempt leaves open connections and the last runs to its deadline: the final pass still runs
    _fake(tmp_path, monkeypatch)
    (tmp_path / "fake_router.py").write_text(FAKE.replace("0 if k == 2 else 2", "2 if k == 3 else 5"))
    (tmp_path / "fake_lastmile.py").write_text(LASTMILE)
    out = tmp_path / "out.kicad_pcb"
    t = time.monotonic()
    rep = portfolio.run("in.kicad_pcb", out, seed=0, time_s=160, parallel=2, first_s=20, router="fake_router",
                        workdir=tmp_path / "wd", log=lambda m: None, final="fake_lastmile")
    assert rep["final"]["kept"] and rep["final"]["budget"] >= portfolio.final_reserve(160, portfolio.FINAL_DRC_S) - 31
    assert tuple(rep["best"]["rank"]) == (0, 0) and rep["best"]["final"]
    assert out.read_text() == "board 3 + last mile"
    assert time.monotonic() - t < 160 + portfolio.GRACE_S


def test_a_final_last_mile_that_is_not_better_leaves_the_kept_board(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch)
    (tmp_path / "fake_router.py").write_text(FAKE.replace("0 if k == 2 else 2", "2 if k == 3 else 5"))
    (tmp_path / "fake_lastmile.py").write_text(LASTMILE.replace("unconnected=0", "unconnected=3"))
    out = tmp_path / "out.kicad_pcb"
    rep = portfolio.run("in.kicad_pcb", out, seed=0, time_s=160, parallel=2, first_s=20, router="fake_router",
                        workdir=tmp_path / "wd", log=lambda m: None, final="fake_lastmile")
    assert rep["final"] is not None and not rep["final"]["kept"]
    assert tuple(rep["best"]["rank"]) == (2, 0) and out.read_text() == "board 3"
