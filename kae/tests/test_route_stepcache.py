# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.stepcache: key stability, atomic entries under concurrency, charge accounting, and
the Freerouting and DRC hooks (stand-in programs, no Java or KiCad)."""
import json
import multiprocessing
import sys
import time
from pathlib import Path

import pytest

from kae.route import drc, freerouting, stepcache


@pytest.fixture
def cache(tmp_path, monkeypatch):
    d = tmp_path / "cache"
    monkeypatch.setenv("KAE_STEP_CACHE", str(d))
    monkeypatch.setenv("KAE_CHARGE_FILE", str(tmp_path / "charge.jsonl"))
    for k in stepcache.STATS:
        monkeypatch.setitem(stepcache.STATS, k, type(stepcache.STATS[k])(0))
    monkeypatch.setattr(stepcache, "_offset", 0.0)
    monkeypatch.setattr(stepcache.time, "monotonic", stepcache._real_monotonic)
    return d


def test_key_is_canonical_and_sensitive():
    a = stepcache.make_key("s", {"x": 1, "y": [1, 2]})
    assert a == stepcache.make_key("s", {"y": [1, 2], "x": 1})          # dict order
    assert a != stepcache.make_key("s", {"x": 1, "y": [2, 1]})
    assert a != stepcache.make_key("t", {"x": 1, "y": [1, 2]})
    assert len(a) == 64


def test_file_sha_normalises_the_work_directory(tmp_path):
    shas = []
    for n in ("one", "two"):
        d = tmp_path / n
        d.mkdir()
        f = d / "board.dsn"
        f.write_text(f'(pcb "{d}/kicad.dsn"\n (x 1))\n')
        shas.append(stepcache.file_sha(f, d))
    assert shas[0] == shas[1]
    f.write_text(f'(pcb "{d}/kicad.dsn"\n (x 2))\n')
    assert stepcache.file_sha(f, d) != shas[0]
    assert stepcache.norm_argv(["-o", f"{d}/r.json", "/elsewhere"], d) == ["-o", "<WD>/r.json", "/elsewhere"]
    assert stepcache.norm_argv([f"{tmp_path}/b/x", f"{tmp_path}/bin/x", f"{tmp_path}/b"], tmp_path / "b") == \
        ["<WD>/x", f"{tmp_path}/bin/x", "<WD>"]                    # whole path components only


def test_disabled_without_the_variable(monkeypatch):
    monkeypatch.delenv("KAE_STEP_CACHE", raising=False)
    assert not stepcache.enabled() and stepcache.get("ab" * 32) is None and not stepcache.put("ab" * 32, {}, {})


def _writer(args):
    root, key, i = args
    import os
    os.environ["KAE_STEP_CACHE"] = root
    src = Path(root).parent / f"src{i}"
    src.write_bytes(bytes([i]) * 200_000)
    return stepcache.put(key, dict(rc=0, seconds=1.0, who=i), {"out": src})


def test_concurrent_writers_leave_one_whole_entry(cache):
    key = "cd" * 32
    with multiprocessing.get_context("fork").Pool(8) as pool:
        won = pool.map(_writer, [(str(cache), key, i) for i in range(16)])
    assert sum(won) == 1
    meta = stepcache.get(key)
    data = (meta["dir"] / "files" / meta["files"]["out"]).read_bytes()
    assert data == bytes([meta["who"]]) * 200_000                       # one writer's files, whole
    assert not any((cache / "tmp").iterdir())                          # no leftovers


def test_charges_parse_and_skip_a_partial_line(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text(json.dumps(dict(step="a", hit=True, charged_s=10, real_s=1, saved_s=9)) + "\n"
                 + json.dumps(dict(step="a", hit=False, charged_s=3, real_s=3, saved_s=0)) + "\n"
                 + json.dumps(dict(step="a", hit=False, cacheable=False, charged_s=2, real_s=2, saved_s=0)) + "\n"
                 + '{"step": "a", "hi')
    t = stepcache.charges(f)
    assert (t["hits"], t["misses"], t["uncacheable"]) == (1, 1, 1)
    assert (t["charged_s"], t["saved_s"]) == (15.0, 9.0)
    assert stepcache.charges(tmp_path / "none")["hits"] == 0


# a command that "computes" for a while: copies its input to its output, plus a side file
SLOW = """import sys, time, pathlib
time.sleep(float(sys.argv[3]))
pathlib.Path(sys.argv[2]).write_text(pathlib.Path(sys.argv[1]).read_text() + " done")
(pathlib.Path(sys.argv[2]).parent / "side.prl").write_text("ui state")
"""


def test_run_hit_replays_outputs_and_charges_its_duration(cache, tmp_path):
    prog = tmp_path / "slow.py"
    prog.write_text(SLOW)
    results = []
    for n in ("a", "b"):
        wd = tmp_path / n
        wd.mkdir()
        (wd / "in.txt").write_text(f"board in {wd}")      # its own path: normalised
        out = wd / "out.txt"
        t0 = time.monotonic()
        r = stepcache.run("t", [sys.executable, str(prog), str(wd / "in.txt"), str(out), "1.0"],
                          inputs=[wd / "in.txt", wd / "missing.dru"], outputs={"o": out}, wd=wd, timeout=60, tool="v1")
        results.append((r, time.monotonic() - t0, out.read_text(), (wd / "side.prl").exists()))
    (miss, _, text_a, side_a), (hit, clock_b, text_b, side_b) = results
    assert not miss.hit and hit.hit
    assert text_a == f"board in {tmp_path / 'a'} done" and text_b == f"board in {tmp_path / 'b'} done"
    assert side_a and side_b                                    # KiCad's side effect replayed
    assert hit.seconds == pytest.approx(miss.seconds, abs=0.01) and hit.seconds >= 1.0
    assert clock_b >= 1.0                                       # the clock counts the hit as its duration
    assert stepcache.offset() == pytest.approx(hit.saved) and hit.saved > 0.5
    t = stepcache.charges(tmp_path / "charge.jsonl")
    assert (t["hits"], t["misses"]) == (1, 1) and t["charged_s"] == pytest.approx(2 * miss.seconds, abs=0.01)


def test_run_misses_on_other_input_tool_or_a_short_timeout(cache, tmp_path):
    prog = tmp_path / "slow.py"
    prog.write_text(SLOW)
    wd = tmp_path / "w"
    wd.mkdir()
    (wd / "in.txt").write_text("x")

    def go(tool="v1", timeout=60):
        return stepcache.run("t", [sys.executable, str(prog), str(wd / "in.txt"), str(wd / "o.txt"), "0.6"],
                             inputs=[wd / "in.txt"], outputs={"o": wd / "o.txt"}, wd=wd, timeout=timeout, tool=tool)
    assert not go().hit and go().hit
    assert not go(tool="v2").hit                                # another KiCad
    (wd / "in.txt").write_text("y")
    assert not go().hit                                         # another board
    with pytest.raises(stepcache.subprocess.TimeoutExpired):    # would have timed out uncached: runs, times out
        go(timeout=0.2)


# a Freerouting stand-in: writes the session and its result file, counts its runs
FAKE_FR = """#!/usr/bin/env python3
import json, pathlib, sys, time
a = sys.argv[1:]
ses = a[a.index("-do") + 1]
res = next(x.split("=", 1)[1] for x in a if x.startswith("--router.result_json="))
n = pathlib.Path(__file__).with_name("runs")
n.write_text(str(int(n.read_text()) + 1 if n.exists() else 1))
time.sleep(3.5)
state = "TIMED_OUT" if "timeout" in pathlib.Path(a[a.index("-de") + 1]).read_text() else "COMPLETED"
pathlib.Path(ses).write_text("(session board (routes " + pathlib.Path(a[a.index("-de") + 1]).read_text() + "))")
json.dump(dict(final_state=state, normalized_score=1000.0), open(res, "w"))
print("Saving output file '" + ses + "' (SES)...")
"""


def _fr(tmp_path, monkeypatch, dsn_text="(pcb x)"):
    exe = tmp_path / "fr" / "freerouting"
    exe.parent.mkdir(exist_ok=True)
    exe.write_text(FAKE_FR)
    exe.chmod(0o755)
    monkeypatch.setenv("KAE_BRIDGE_FREEROUTING", str(exe))
    monkeypatch.setenv("KAE_FR_LOCKDIR", str(tmp_path / "slots"))
    return exe.with_name("runs"), dsn_text


def _route(tmp_path, name, text, budget=60.0):
    wd = tmp_path / name
    wd.mkdir(exist_ok=True)
    (wd / "board.dsn").write_text(f'(pcb "{wd}/kicad.dsn" {text})')
    return freerouting.route(wd / "board.dsn", wd / "board.ses", wd, settings={"fanout.enabled": "false"},
                             budget_s=budget, log_path=wd / "fr.log"), wd


def test_freerouting_replays_a_run_that_stopped_by_itself(cache, tmp_path, monkeypatch):
    runs, text = _fr(tmp_path, monkeypatch)
    a, wa = _route(tmp_path, "a", text)
    b, wb = _route(tmp_path, "b", text, budget=90.0)            # another job timeout: same key
    assert runs.read_text() == "1"
    assert b.report.get("step_cache") == "hit" and b.seconds == pytest.approx(a.seconds, abs=0.01)
    assert (wb / "board.ses").read_text() == (wa / "board.ses").read_text().replace(str(wa), str(wb))
    assert str(wb / "board.ses") in (wb / "fr.log").read_text()  # its log names its own paths
    assert b.report["final_state"] == "COMPLETED" and b.ses == wb / "board.ses"
    c, _ = _route(tmp_path, "c", text, budget=6.0)               # too short for the recorded run: runs
    assert runs.read_text() == "2" and c.report.get("step_cache") is None


def test_freerouting_at_its_timeout_is_not_cached(cache, tmp_path, monkeypatch):
    runs, _ = _fr(tmp_path, monkeypatch)
    _route(tmp_path, "a", "timeout")
    _route(tmp_path, "b", "timeout")
    assert runs.read_text() == "2"
    t = stepcache.charges(tmp_path / "charge.jsonl")
    assert (t["hits"], t["misses"], t["uncacheable"]) == (0, 0, 2)


def test_freerouting_unchanged_without_the_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("KAE_STEP_CACHE", raising=False)
    runs, text = _fr(tmp_path, monkeypatch)
    _route(tmp_path, "a", text)
    _route(tmp_path, "b", text)
    assert runs.read_text() == "2"


FAKE_CLI = """#!/usr/bin/env python3
import json, pathlib, sys
a = sys.argv[1:]
if a == ["version"]:
    print("10.0.7"); sys.exit(0)
n = pathlib.Path(__file__).with_name("runs")
n.write_text(str(int(n.read_text()) + 1 if n.exists() else 1))
json.dump(dict(violations=[dict(type="clearance", severity="error")], unconnected_items=[]), open(a[a.index("-o") + 1], "w"))
"""


def test_drc_run_through_the_cache(cache, tmp_path, monkeypatch):
    cli = tmp_path / "bin" / "kicad-cli"
    cli.parent.mkdir()
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    monkeypatch.setenv("KAE_KICAD_CLI", str(cli))
    drc.kicad_cli.cache_clear()
    src = tmp_path / "src.kicad_pcb"
    src.write_text("(kicad_pcb)")
    reps = []
    for n in ("a", "b"):    # two staged copies of one board: one DRC
        b = drc.stage_board(src, src, tmp_path / n)
        reps.append(drc.run(b, tmp_path / n / "drc.json", timeout=60))
    drc.kicad_cli.cache_clear()
    assert reps[0] == reps[1] and drc.summary(reps[1])["errors"] == 1
    assert (cli.with_name("runs")).read_text() == "1"
