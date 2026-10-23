# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests that need no KiCad installation."""
import json
import lzma
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from kaebench import boardfiles, manifest, report, score, tools

SHA = "0" * 40


def entry(**kw):
    e = dict(id="b1", repo="https://github.com/o/r", commit=SHA, pcb_path="a/b.kicad_pcb", license="MIT")
    e.update(kw)
    return e


def test_manifest_validation(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in [
        entry(), entry(id="b2", license_tier="permissive", tags=["rf"])]) + "\n# comment\n")
    assert [e["id"] for e in manifest.load(p)] == ["b1", "b2"]
    assert [e["id"] for e in manifest.load(p, tags=["rf"])] == ["b2"]
    assert [e["id"] for e in manifest.load(p, tiers=["permissive"])] == ["b2"]
    for bad in (entry(commit="abc"), entry(pcb_path="x.brd"), entry(id="has space"),
                entry(license_tier="other"), {k: v for k, v in entry().items() if k != "license"}):
        with pytest.raises(manifest.ManifestError):
            manifest.validate(bad)


def test_duplicate_ids(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text(json.dumps(entry()) + "\n" + json.dumps(entry()) + "\n")
    with pytest.raises(manifest.ManifestError):
        manifest.load(p)


def test_project_paths():
    assert manifest.project_paths(entry()) == {"kicad_pro": "a/b.kicad_pro", "kicad_dru": "a/b.kicad_dru"}


def test_top_level_block_ignores_nested_and_strings():
    text = '(kicad_pcb (version 1) (footprint "x" (setup "(setup fake)")) (setup (a 1) (b "c)")) (net 0 ""))'
    assert boardfiles.top_level_block(text, "setup") == '(setup (a 1) (b "c)"))'
    assert boardfiles.top_level_block(text, "missing") is None


def test_strip_ses_placement(tmp_path):
    ses = tmp_path / "in.ses"
    ses.write_text('(session "b"\n (base_design "b")\n (placement (resolution um 10)\n  (component "R" (place R1 1 2 front 0)))\n (routes (resolution um 10)))\n')
    out = tmp_path / "out.ses"
    assert boardfiles.strip_ses_placement(ses, out)
    text = out.read_text()
    assert "placement" not in text and "(routes" in text


def test_quote_ses_net_names(tmp_path):
    ses = tmp_path / "b.ses"
    ses.write_text('(session b (routes (network_out\n  (net ADD|SUB (wire (path F.Cu 250 0 0 1 1)))\n'
                   '  (net "XOR_NOT" (via "Via[0-1]_800:400_um" 0 0))\n  (net \\JMP (wire)))))\n')
    assert boardfiles.quote_ses_net_names(ses) == 2
    text = ses.read_text()
    assert '(net "ADD|SUB" (wire' in text and '(net "XOR_NOT"' in text and '(net "\\JMP"' in text


def test_unblock_all_power_dsn(tmp_path):
    dsn = tmp_path / "b.dsn"
    head = "(pcb b (structure\n (layer F.Cu (type {}) (property (index 0)))\n (layer B.Cu (type power))\n"
    dsn.write_text(head.format("power") + " (plane GND (polygon F.Cu 0 0 0 1 1))))\n")
    assert boardfiles.unblock_all_power_dsn(dsn) == 2
    assert "power" not in dsn.read_text() and dsn.read_text().count("(type signal)") == 2
    dsn.write_text(head.format("signal") + "))\n")
    assert boardfiles.unblock_all_power_dsn(dsn) == 0 and "(type power)" in dsn.read_text()


def test_dsn_unset_netclass_sizes(tmp_path):
    dsn = tmp_path / "b.dsn"
    dsn.write_text('(pcb b (resolution um 10) (unit um)\n (structure (via "Via[0-1]_-0.001:-0.001_um")\n'
                   '  (rule (width -0.001) (clearance 150)))\n (library\n'
                   '  (padstack "Via[0-1]_-0.001:-0.001_um" (shape (circle F.Cu -0.001)) (shape (circle B.Cu -0.001))'
                   ' (attach off))\n  (padstack "Via[0-1]_600:300_um" (shape (circle F.Cu 600)) (attach off)))\n'
                   ' (network (class kicad_default a b (circuit (use_via "Via[0-1]_-0.001:-0.001_um"))'
                   ' (rule (width -0.001)))))\n')
    assert boardfiles.clamp_dsn_widths(dsn, 0.2) == 2
    assert boardfiles.fix_dsn_unsized_vias(dsn, 0.5, 0.3) == 1
    text = dsn.read_text()
    assert "-0.001" not in text and text.count("(width 200)") == 2
    assert text.count('"Via[0-1]_500:300_um"') == 3 and "(circle F.Cu 500)" in text and "(circle B.Cu 500)" in text
    assert "(circle F.Cu 600)" in text and "Via[0-1]_600:300_um" in text


def test_summarize_drc_ignores_library_checks():
    rep = dict(violations=[dict(type="clearance", severity="error"),
                           dict(type="lib_footprint_issues", severity="error"),
                           dict(type="silk_overlap", severity="warning")],
               unconnected_items=[{}, {}])
    s = tools.summarize_drc(rep)
    assert s == dict(unconnected=2, errors=1, warnings=1, errors_by_type={"clearance": 1})


def test_potential_orders_clean_first():
    clean = dict(valid=True, clean=True, completion=1.0, errors=0, track_length_mm=100)
    longer = dict(clean, track_length_mm=150)
    dirty = dict(valid=True, clean=False, completion=1.0, errors=1, track_length_mm=50)
    invalid = dict(valid=False, clean=True)
    ranked = sorted([dirty, invalid, longer, clean], key=score.potential, reverse=True)
    assert ranked == [clean, longer, dirty, invalid]


def test_report_best_of_k(tmp_path):
    def row(bid, a, clean, comp):
        return dict(adapter="x", kind="route", id=bid, split="A", attempt=a, status="ok", runtime_s=1.0,
                    score=dict(valid=True, clean=clean, completion=comp, errors=0 if clean else 3,
                               track_length_mm=10, wl_ratio=1.0, via_delta=0))
    rows = [row("b1", 0, False, 0.5), row("b1", 1, True, 1.0), row("b2", 0, False, 0.8), row("b2", 1, False, 0.9)]
    m = report.summarize(rows)[("x", "route", "all")]
    assert m["boards"] == 2 and m["k"] == 2
    assert m["cp1"] == 0.0 and m["cpk"] == 0.5
    assert m["completion"] == pytest.approx(0.95)
    assert "| x | all |" in report.to_markdown(report.summarize(rows))


def test_id_list_from_file(tmp_path):
    from kaebench.cli import _split
    f = tmp_path / "suite.txt"
    f.write_text("b1\n# comment\nb2  # trailing\n\n")
    assert _split(f"@{f}") == ["b1", "b2"]
    assert _split("a,b,,c") == ["a", "b", "c"] and _split("") is None


def test_local_boards_read_row_json(tmp_path):
    from kaebench.cli import _local_boards
    for name, row in (("b1", dict(id="b1", repo="https://github.com/o/r", commit=SHA, pcb_path="x/b.kicad_pcb",
                                  license="MIT", license_tier="permissive", tags=["rf"])), ("b2", None)):
        d = tmp_path / name
        d.mkdir()
        (d / "board.kicad_pcb").write_text("(kicad_pcb)")
        if row:
            (d / "row.json").write_text(json.dumps(row))
    items = {e["id"]: e for e, _ in _local_boards(tmp_path, "board.kicad_pcb", ["b1", "b2", "missing"])}
    assert items["b1"]["license_tier"] == "permissive" and items["b1"]["tags"] == ["rf"]
    assert items["b1"]["repo"] == "https://github.com/o/r" and items["b1"]["commit"] == SHA
    assert items["b2"]["license"] == "unknown (local)" and items["b2"]["tags"] == []
    assert len(_local_boards(tmp_path, "board.kicad_pcb", None)) == 2


def test_clamp_dsn_widths(tmp_path):
    dsn = tmp_path / "b.dsn"
    dsn.write_text("(pcb b (resolution um 10) (unit um)\n (structure (rule (width 101.6) (clearance 200)))\n"
                   " (network (class kicad_default a b (rule (width 250) (clearance 200)))))\n")
    assert boardfiles.clamp_dsn_widths(dsn, 0.127) == 1
    text = dsn.read_text()
    assert "(width 127)" in text and "(width 250)" in text and "(clearance 200)" in text


def _newc(entries):
    out = b""
    for ino, (name, mode, body) in enumerate([*entries, ("TRAILER!!!", 0, b"")]):
        nb = name.encode() + b"\0"
        out += b"070701" + b"".join(b"%08x" % v for v in (ino, mode, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(nb), 0))
        out += nb + b"\0" * ((-(110 + len(nb))) % 4) + body + b"\0" * ((-len(body)) % 4)
    return out


def test_rpm_shims(tmp_path):
    """setup.sh's rpm2cpio/cpio stand-ins (rootless Apptainer install) round-trip an RPM."""
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    archive = _newc([("./usr/bin", 0o40755, b""), ("./usr/bin/tool", 0o100755, b"#!/bin/sh\n"),
                     ("./usr/bin/alias", 0o120777, b"tool")])
    hdr = b"\x8e\xad\xe8\x01" + b"\0" * 4 + struct.pack(">II", 0, 0)
    rpm = b"\xed\xab\xee\xdb" + b"\0" * 92 + hdr + hdr + lzma.compress(archive)
    cpio = subprocess.run([sys.executable, scripts / "rpm2cpio.py", "-"], input=rpm, capture_output=True, check=True)
    assert cpio.stdout == archive
    subprocess.run([sys.executable, scripts / "cpio_extract.py", "-idum"], input=cpio.stdout, cwd=tmp_path, check=True)
    assert (tmp_path / "usr/bin/tool").read_bytes() == b"#!/bin/sh\n"
    assert os.access(tmp_path / "usr/bin/tool", os.X_OK)
    assert os.readlink(tmp_path / "usr/bin/alias") == "tool"
    # empty or truncated input must fail, so the installer's download retry loop runs
    for bad in (b"", archive[:150]):
        r = subprocess.run([sys.executable, scripts / "cpio_extract.py", "-idum"], input=bad, cwd=tmp_path)
        assert r.returncode != 0


def test_outside_is_judged_against_the_human_placement():
    allowed = {"J1": 2}  # the designer's edge connector has 2 pads over the edge
    rows = [dict(uuid="J1", pads_outside=2), dict(uuid="R1", pads_outside=0), dict(uuid="U1", pads_outside=None)]
    assert score.outside_count(rows, allowed) == 0
    assert score.outside_count([dict(uuid="J1", pads_outside=3), dict(uuid="R1", pads_outside=1)], allowed) == 2


def test_work_list_interleaves_arms_per_board():
    from kaebench import runner

    class A:
        kinds = ("route",)

        def __init__(self, name):
            self.name = name

    recs = [dict(id=f"b{i}", tasks={"route": {}}) for i in range(40)]
    arms = [(A("x"), None), (A("y"), None)]
    work = runner.work_list(recs, arms, ("route",), 1)
    # each board's arms are adjacent
    assert [w[0]["id"] for w in work] == [r["id"] for r in recs for _ in arms]
    firsts = [work[2 * i][3].name for i in range(len(recs))]
    assert set(firsts) == {"x", "y"}  # neither arm always goes first
    assert work == runner.work_list(recs, arms, ("route",), 1)  # deterministic
    sized = [dict(id=f"s{p}", tasks={"route": {}}, reference=dict(stats=dict(pads=p))) for p in (5, 500, 50)]
    assert [w[0]["id"] for w in runner.work_list(sized, arms[:1], ("route",), 1)] == ["s500", "s50", "s5"]

    class P:
        kinds = ("place",)
        name = "p"
    placeable = [dict(id=f"m{n}", tasks={"place": {"movable": n}}) for n in (0, 1, 5)]
    assert [w[0]["id"] for w in runner.work_list(placeable, [(P(), None)], ("place",), 1, min_movable=2)] == ["m5"]
    assert len(runner.work_list(placeable, [(P(), None)], ("place",), 1)) == 3  # default keeps all


def test_run_measured_peak_rss_is_the_childs_not_the_runners():
    # The runner's own peak RSS used to leak into every child's ru_maxrss via exec.
    big = bytearray(1 << 30)  # 1 GiB touched in this (parent) process
    for i in range(0, len(big), 4096):
        big[i] = 1
    tools.usage_take()
    r = tools.run_measured([sys.executable, "-c", "b = bytearray(200 << 20)"])
    u = tools.usage_take()
    assert r.returncode == 0 and u["processes"] == 1
    assert 200 <= u["max_rss_mb"] < 400, u
    tools.run_measured(["true"])
    assert tools.usage_take()["max_rss_mb"] < 50
    del big


def test_run_measured_cpu_exit_code_and_errors():
    tools.usage_take()
    r = tools.run_measured([sys.executable, "-c", "import sys\nx = 0\nfor i in range(3_000_000): x += i\n"
                            "print('out'); print('err', file=sys.stderr); sys.exit(3)"])
    u = tools.usage_take()
    assert (r.returncode, r.stdout, r.stderr) == (3, "out\n", "err\n")
    assert u["cpu_s"] > 0.05
    assert tools.run_measured(["sh", "-c", "kill -9 $$"]).returncode == -9
    with pytest.raises(FileNotFoundError):
        tools.run_measured(["/nonexistent/kae-command"])
    with pytest.raises(subprocess.TimeoutExpired):
        tools.run_measured([sys.executable, "-c", "while True: pass"], timeout=1)
    assert tools.usage_take()["cpu_s"] > 0.5  # the killed command's CPU is still accounted


def test_run_measured_cuts_a_stalled_command_short():
    """A process tree idling at ~0% CPU (as kicad-cli does when KiCad's zone filler
    deadlocks) is killed after `stall` seconds; a busy one only at its timeout."""
    import time
    t = time.monotonic()
    with pytest.raises(tools.Stalled):
        tools.run_measured(["sh", "-c", "sleep 60; true"], timeout=60, stall=3)
    assert time.monotonic() - t < 20
    busy = [sys.executable, "-c", "while True: pass"]
    with pytest.raises(subprocess.TimeoutExpired) as e:  # CPU of a grandchild counts as progress
        tools.run_measured(["sh", "-c", f"{subprocess.list2cmdline(busy)}; true"], timeout=6, stall=2)
    assert not isinstance(e.value, tools.Stalled)
    tools.usage_take()


def test_capped_drc_types_are_flagged():
    drc = dict(errors_by_type={"track_width": 199, "clearance": 12, "items_not_allowed": 499})
    assert score._capped_types(drc) == ["items_not_allowed", "track_width"]
    assert score._uncapped("unused.kicad_pcb", 12) == (12, False)  # below the cap: DRC's own count
