# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests that need no KiCad installation."""
import hashlib
import io
import json
import lzma
import os
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from kaebench import adapters, boardfiles, fetch, manifest, report, runner, score, tools

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
    for bad in (entry(commit="abc"), entry(pcb_path="x.step"), entry(id="has space"),
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
    assert manifest.project_paths(entry(pcb_path="hw/x.PcbDoc")) == {}


def test_import_formats():
    assert manifest.validate(entry(pcb_path="hw/board.brd"))
    assert manifest.import_format("hw/Board.PcbDoc") == "altium"
    assert manifest.import_format("hw/board.brd") == "auto"
    zipped = entry(commit=None, repo="https://example.com/cad.zip", archive_sha256="a" * 64, pcb_path="x/b.brd")
    assert manifest.validate(zipped)
    for bad in (dict(zipped, archive_sha256="abc"), dict(zipped, commit="b" * 40), entry(commit=None)):
        with pytest.raises(manifest.ManifestError):
            manifest.validate(bad)
    assert manifest.import_format("a/b.kicad_pcb") is None


def test_top_level_block_ignores_nested_and_strings():
    text = '(kicad_pcb (version 1) (footprint "x" (setup "(setup fake)")) (setup (a 1) (b "c)")) (net 0 ""))'
    assert boardfiles.top_level_block(text, "setup") == '(setup (a 1) (b "c)"))'
    assert boardfiles.top_level_block(text, "missing") is None


def test_fix_unloadable():
    text = '(pad 1 smd (net 34 313)) (pad 2 smd (net 1 GND)) (gr_line (layer "Rescue")) (fp_line (layer "UNDEFINED"))'
    assert boardfiles.fix_unloadable(text) == ('(pad 1 smd (net 34 "313")) (pad 2 smd (net 1 GND)) '
                                               '(gr_line (layer "Cmts.User")) (fp_line (layer "Cmts.User"))')
    text = '(net 16 -5) (net 6 +3.3) (net 45 1.02) (net 3 "+5V") (net 1 VCC)'
    assert boardfiles.fix_unloadable(text) == '(net 16 "-5") (net 6 "+3.3") (net 45 "1.02") (net 3 "+5V") (net 1 VCC)'
    text = '(kicad_pcb\n\t(property "SPDX-License-Identifier" "MIT")\n\t(version 20260206)\n\t(generator "pcbnew")'
    assert boardfiles.fix_unloadable(text).startswith(
        '(kicad_pcb\n\t(version 20260206)\n\t(property "SPDX-License-Identifier" "MIT")\n\t\n\t(generator')
    text = '(user_via 0.45 0.3 3 0 31) (user_via 0.6 0.4)'
    assert boardfiles.fix_unloadable(text) == '(user_via 0.45 0.3) (user_via 0.6 0.4)'


def test_zip_fetch_reads_tar_gz(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in (("d/PCB/b.PcbDoc", b"board"), ("d/other.txt", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    blob = buf.getvalue()
    monkeypatch.setattr(fetch, "_download", lambda url, dest: Path(dest).write_bytes(blob) or True)
    e = entry(commit=None, repo="https://example.com/d.tar.gz", pcb_path="d/PCB/b.PcbDoc",
              archive_sha256=hashlib.sha256(blob).hexdigest())
    got = fetch._zip_fetch(e, {"kicad_pcb": e["pcb_path"]}, tmp_path)
    assert got["kicad_pcb"].read_bytes() == b"board"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.PcbDoc"]


def test_single_file_row_fetches_project_files(tmp_path, monkeypatch):
    files = {"https://m.org/b.kicad_pcb": b"(kicad_pcb)", "https://m.org/b.kicad_pro": b"{}"}
    monkeypatch.setattr(fetch, "_download", lambda url, dest: Path(dest).write_bytes(files[url]) or True)
    h = {u: hashlib.sha256(b).hexdigest() for u, b in files.items()}
    e = entry(commit=None, repo="https://m.org/b.kicad_pcb", pcb_path="w6/b.kicad_pcb",
              archive_sha256=h["https://m.org/b.kicad_pcb"],
              file_urls={"kicad_pro": {"url": "https://m.org/b.kicad_pro", "sha256": h["https://m.org/b.kicad_pro"]}})
    assert manifest.validate(e)
    got = fetch._zip_fetch(e, manifest.project_paths(e) | {"kicad_pcb": e["pcb_path"]}, tmp_path)
    assert got["kicad_pro"].read_bytes() == b"{}" and got["kicad_pcb"].name == "b.kicad_pcb"
    e["file_urls"]["kicad_pro"]["sha256"] = "0" * 64
    (tmp_path / "x").mkdir()
    with pytest.raises(ValueError):
        fetch._zip_fetch(e, manifest.project_paths(e) | {"kicad_pcb": e["pcb_path"]}, tmp_path / "x")
    with pytest.raises(manifest.ManifestError):
        manifest.validate(dict(e, file_urls={"kicad_pro": {"url": "u"}}))


def test_download_retries_rate_limit(tmp_path, monkeypatch):
    import urllib.error
    calls, sleeps = [], []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) <= 2:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "30"}, None)
        return io.BytesIO(b"board")

    clock = [0.0]
    monkeypatch.setattr(fetch.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetch.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fetch.time, "sleep", lambda s: (sleeps.append(s), clock.__setitem__(0, clock[0] + s)))
    monkeypatch.setattr(fetch, "_hold_until", {})
    assert fetch._download("https://gitlab.example.org/a/-/raw/c/b.kicad_pcb", tmp_path / "b")
    assert (tmp_path / "b").read_bytes() == b"board" and len(calls) == 3
    assert len(sleeps) == 2 and all(30 <= s <= 37 for s in sleeps)  # Retry-After + jitter

    # a persistent 503 is given up after RETRY_BUDGET seconds; 404 is "not found", not an error
    def unavailable(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, None)
    monkeypatch.setattr(fetch.urllib.request, "urlopen", unavailable)
    with pytest.raises(urllib.error.HTTPError):
        fetch._download("https://gitlab.example.org/x", tmp_path / "x")
    assert clock[0] <= 2 * fetch.RETRY_BUDGET
    monkeypatch.setattr(fetch.urllib.request, "urlopen",
                        lambda req, timeout: (_ for _ in ()).throw(
                            urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)))
    assert fetch._download("https://gitlab.example.org/y", tmp_path / "y") is False


def test_fetch_falls_back_to_git_when_raw_misses(tmp_path, monkeypatch):
    # gitlab.cba.mit.edu projects that moved to forge.cba.mit.edu 404 on the guessed raw URL
    monkeypatch.setattr(fetch, "_download", lambda url, dest: False)
    def git_fetch(repo, commit, paths, dest_dir):
        out = dest_dir / "b.kicad_pcb"
        out.write_text("(kicad_pcb (version 20240108))")
        return {"kicad_pcb": out}
    monkeypatch.setattr(fetch, "_git_fetch", git_fetch)
    e = entry(repo="https://gitlab.cba.mit.edu/u/p", pcb_path="hw/b.kicad_pcb")
    assert fetch.fetch(e, tmp_path)["kicad_pcb"].endswith("b.kicad_pcb")


def test_art_zones_to_polys():
    pts = "(pts (xy 0 0) (xy 1 0) (xy 1 1))"
    text = ('(kicad_pcb (version 1)\n'
            f' (footprint "x" (zone (layer "F.SilkS") (polygon {pts})))\n'
            f' (zone (layer "B.SilkS") (uuid "u1") (fill (thermal_gap 0.5)) (polygon {pts}))\n'
            f' (zone (net 1) (net_name "GND") (layer "F.Cu") (polygon {pts}))\n'
            f' (zone (layer "F.Cu") (keepout (tracks not_allowed)) (polygon {pts}))\n'
            f' (gr_text "(zone (layer \\"F.SilkS\\"))"))')
    new, n = boardfiles.art_zones_to_polys(text)
    assert n == 2
    assert f'(fp_poly {pts} (stroke (width 0) (type solid)) (fill yes) (layer "F.SilkS"))' in new
    assert f'(gr_poly {pts} (stroke (width 0) (type solid)) (fill yes) (layer "B.SilkS") (uuid "u1"))' in new
    assert new.count("(zone") == 3  # copper zone, keepout and the string are untouched


def test_micro_arc_pile_and_remove_top_level():
    def arc(x, uid, layer="F.Cu", d=0.0000005):
        return (f'\t(arc\n\t\t(start {x} 5) (mid {x + d} 5.0000004) (end {x + 2 * d} 5)\n'
                f'\t\t(width 0.1)\n\t\t(layer "{layer}")\n\t\t(net 1)\n\t\t(uuid "{uid}")\n\t)\n')
    text = ("(kicad_pcb\n" + arc(1, "a") + arc(1.00001, "b") + arc(1, "c", "B.Cu") + arc(7, "d")
            + arc(9, "e", d=0.01)  # a real (if short) arc is not counted
            + '\t(zone (polygon (pts (arc (start 1 5) (mid 1 5) (end 1 5)))) (uuid "z"))\n)\n')
    assert boardfiles.micro_arc_pile(text) == 2
    new, n = boardfiles.remove_top_level(text, "arc", {"a", "d", "z"})
    assert n == 2 and '"a"' not in new and '"d"' not in new
    assert '(uuid "b")' in new and '(uuid "e")' in new and '(uuid "z")' in new  # zone pts arc kept
    assert new.startswith("(kicad_pcb\n\t(arc") and new.endswith("\n)\n")


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


def test_freerouting_empty_ses_is_no_output(tmp_path, monkeypatch):
    """A router that crashes and leaves a 0-byte session gets no_output, not an import error."""
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "board.kicad_pcb").write_text("(kicad_pcb)")

    def ops(op, *args, **kw):
        if op == "export-dsn":
            Path(args[1]).write_text("(pcb b (unit um))")
            return {"ok": True}
        if op == "stats":
            return {"ok": True, "rules": {}}
        raise AssertionError(f"unexpected pcbnew op {op}")

    def router(cmd, **kw):
        Path(cmd[cmd.index("-do") + 1]).write_text("")
        return subprocess.CompletedProcess(cmd, 1, "", "NullPointerException")

    monkeypatch.setattr(tools, "run_ops", ops)
    monkeypatch.setattr(tools, "run_measured", router)
    res = adapters.Freerouting(binary="freerouting").run("route", inp, tmp_path / "w", 0, 100)
    assert res.output is None and res.meta["ses_empty"] and res.meta["rc"] == 1


def test_freerouting_hung_after_writing_ses_keeps_it(tmp_path, monkeypatch):
    """A router killed at our deadline after writing a complete session is scored on it;
    a session cut off mid-write is no output."""
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "board.kicad_pcb").write_text("(kicad_pcb)")
    imported = []

    def ops(op, *args, **kw):
        if op == "export-dsn":
            Path(args[1]).write_text("(pcb b (unit um))")
            return {"ok": True}
        if op == "stats":
            return {"ok": True, "rules": {}}
        if op == "import-ses":
            imported.append(args[1])
            Path(args[2]).write_text("(kicad_pcb)")
            return {"ok": True}
        raise AssertionError(f"unexpected pcbnew op {op}")

    for text, kept in (('(session s (routes (network_out (net "a)" (wire (path F.Cu 1 0 0 1 1))))))\n', True),
                       ('(session s (routes (network_out (net "a" (wire', False)):
        def router(cmd, **kw):
            Path(cmd[cmd.index("-do") + 1]).write_text(text)
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])

        monkeypatch.setattr(tools, "run_ops", ops)
        monkeypatch.setattr(tools, "run_measured", router)
        res = adapters.Freerouting(binary="freerouting").run("route", inp, tmp_path / f"w{kept}", 0, 100)
        assert res.meta["timed_out"] and res.meta["partial"]
        assert (res.output is not None) == kept and res.meta.get("ses_cut", False) == (not kept), res.meta
    assert len(imported) == 1


def test_command_killed_at_the_deadline_keeps_its_output(tmp_path, monkeypatch):
    """An anytime method (restart.py) keeps its best board in {output}: killed at the harness
    deadline it is scored on it, as Freerouting is on its partial session; no file is no output."""
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "board.kicad_pcb").write_text("(kicad_pcb)")
    for wrote in (True, False):
        def run(cmd, timeout=None, **kw):
            if wrote:
                (kw["cwd"] / "output" / "board.kicad_pcb").write_text("(kicad_pcb)")
            raise subprocess.TimeoutExpired(cmd, timeout, output="best so far")
        monkeypatch.setattr(tools, "run_measured", run)
        res = adapters.Command("true").run("route", inp, tmp_path / f"w{wrote}", 0, 10)
        assert res.meta["timed_out"] and res.meta["partial"] == wrote and "best so far" in res.log
        assert (res.output == tmp_path / f"w{wrote}" / "output" / "board.kicad_pcb") if wrote else res.output is None


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


def test_report_means_over_the_boards_every_adapter_scored():
    """A board without output drops out of an adapter's error mean; that favours a method that fails
    on hard boards, so the means are also over the boards both scored (and the counts are shown)."""
    def row(adapter, bid, errors):
        sc = dict(valid=True, clean=errors == 0, completion=1.0, errors=errors, wl_ratio=1.0, via_delta=0)
        return dict(adapter=adapter, kind="route", id=bid, split="A", attempt=0, runtime_s=1.0,
                    status="ok" if errors is not None else "no_output", score=sc if errors is not None else None)
    rows = [row("a", "b1", 0), row("a", "hard", 10), row("b", "b1", 2), row("b", "hard", None)]
    s = report.summarize(rows)
    a, b = s[("a", "route", "all")], s[("b", "route", "all")]
    assert (a["errors"], a["scored"], b["errors"], b["scored"]) == (5.0, 2, 2.0, 1)
    assert (a["errors_common"], b["errors_common"], a["common"], b["common"]) == (0.0, 2.0, 1, 1)
    assert "errors_common" in report.to_markdown(s)


def test_report_keeps_runs_of_one_adapter_apart(tmp_path):
    """A method and its baseline run with the same adapter name must not be pooled."""
    def write(run, adapter, bid, clean, version):
        d = tmp_path / run / adapter / "route" / bid / "attempt-0"
        d.mkdir(parents=True)
        (d / "attempt.json").write_text(json.dumps(dict(
            adapter=adapter, kind="route", id=bid, split="A", attempt=0, status="ok", runtime_s=1.0,
            score_version=version, score=dict(valid=True, clean=clean, completion=1.0, errors=0, track_length_mm=10))))
    for bid in ("b1", "b2"):
        write("baseline", "freerouting", bid, False, 5)
        write("new", "freerouting", bid, True, 6)
        write("new", "reference", bid, True, 6)
    summary, rows = report.report([tmp_path / "new", tmp_path / "baseline"])
    assert summary[("freerouting@baseline", "route", "all")]["cp1"] == 0.0
    assert summary[("freerouting@new", "route", "all")]["cp1"] == 1.0
    assert summary[("freerouting@new", "route", "all")]["k"] == 1
    assert ("reference", "route", "all") in summary  # unshared names keep their plain label
    assert report.score_versions(rows) == [5, 6]
    single, _ = report.report([tmp_path / "new"])
    assert ("freerouting", "route", "all") in single


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


def _project(d, severity):
    d.mkdir(parents=True, exist_ok=True)
    (d / "board.kicad_pro").write_text(json.dumps(
        {"board": {"design_settings": {"rule_severities": {"unconnected_items": severity}}}}))
    return d / "board.kicad_pcb"


def test_unconnected_is_counted_where_the_project_ignores_it(tmp_path, monkeypatch):
    """A project with "unconnected_items": "ignore" makes DRC report none: the start and every
    output read 0 and an empty output scored complete (gamaphy-freedom-rp2040). Both are then
    counted by pcbnew's connectivity, the same way."""
    counts = {}
    monkeypatch.setattr(tools, "run_ops", lambda op, board, *a: dict(unconnected=counts[Path(board).parent.name]))
    ign, warn = _project(tmp_path / "ign", "ignore"), _project(tmp_path / "warn", "warning")
    counts.update(ign=40, warn=99)
    assert boardfiles.unconnected_ignored(ign) and not boardfiles.unconnected_ignored(warn)
    assert not boardfiles.unconnected_ignored(tmp_path / "none" / "board.kicad_pcb")
    assert score._uncapped(ign, 0) == (40, False)
    assert score._uncapped(warn, 0) == (0, False)  # a warning is still reported by DRC (--severity-all)
    cache = tmp_path / "ign" / "unconnected.json"
    assert score._uncapped(ign, 0, cache=cache) == (40, False) and json.loads(cache.read_text()) == {"unconnected": 40}
    counts["ign"] = 1
    assert score._uncapped(ign, 0, cache=cache) == (40, False)  # the start's cache
    # prepare: the human layout and the task start are counted the same way
    from kaebench import prepare
    monkeypatch.setattr(tools, "run_drc", lambda b, o: dict(violations=[], unconnected_items=[]))
    assert prepare._drc(ign, None)["unconnected"] == 1
    assert prepare._drc(warn, None)["unconnected"] == 0


def test_tools_get_absolute_paths_under_a_relative_workdir(tmp_path, monkeypatch):
    """Methods and Freerouting run with cwd=<attempt dir>, so relative paths would miss."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "board.kicad_pcb").write_text("(kicad_pcb)")
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(tools, "run_measured", run)
    def ops(op, *args, **kw):
        if op == "export-dsn":
            Path(args[1]).write_text("(pcb b (unit um))")
        return {"ok": True, "rules": {}}

    monkeypatch.setattr(tools, "run_ops", ops)
    adapters.Command("cp {input} {output}", sandbox=False).run("route", Path("in"), Path("w1"), 0, 10)
    adapters.Freerouting(binary="freerouting").run("route", Path("in"), Path("w2"), 0, 10)
    flat = [str(x) for c in seen for x in (c if isinstance(c, list) else [c])]
    paths = [x for x in " ".join(flat).split() if x.endswith((".kicad_pcb", ".dsn", ".ses"))]
    assert paths and all(Path(x.strip("'")).is_absolute() for x in paths), paths


def test_kicad_killed_by_a_signal_is_retried_once(tmp_path, monkeypatch):
    """A pcbnew op or DRC that dies on a signal without a result runs once more; one that
    exits normally without a result, or crashes twice, is still an error."""
    calls = []

    def flaky(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, -5, "", "Assert failure")
        if "drc" in cmd:
            Path(cmd[cmd.index("-o") + 1]).write_text('{"violations": []}')
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, '{"ok": true, "n": 1}\n', "")

    monkeypatch.setattr(tools, "run_measured", flaky)
    monkeypatch.setattr(tools, "kicad_python", lambda: ["py"])
    monkeypatch.setattr(tools, "kicad_cli", lambda: ["kicad-cli"])
    assert tools.run_ops("stats", "b")["n"] == 1 and len(calls) == 2
    calls.clear()
    assert tools.run_drc(tmp_path / "b.kicad_pcb", tmp_path / "d.json") == {"violations": []}
    assert len(calls) == 2

    calls.clear()
    monkeypatch.setattr(tools, "run_measured",
                        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, -11, "", ""))
    with pytest.raises(tools.ToolError):
        tools.run_ops("stats", "b")
    assert len(calls) == 2
    calls.clear()
    monkeypatch.setattr(tools, "run_measured",
                        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 1, "", ""))
    with pytest.raises(tools.ToolError):
        tools.run_ops("stats", "b")
    assert len(calls) == 1


def _fp(ref, fpid, value="", pads=2, pth=0, npth=0):
    lib, _, name = fpid.rpartition(":")
    return dict(ref=ref, lib=lib, name=name, value=value, pads=pads, pth=pth, npth=npth,
                smd=pads - pth - npth)


@pytest.mark.parametrize("fp,cls,rule", [
    # library names first
    (_fp("J1", "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", pads=20), "connector", "lib"),
    (_fp("P3", "MountingHole:MountingHole_4.3mm_M4", "CONN_1", pads=1, pth=1), "mounting", "lib"),
    (_fp("FID1", "Fiducial:Fiducial_1mm_Mask2mm", pads=1), "mounting", "lib"),
    (_fp("SW1", "Button_Switch_SMD:SW_SPST_TL3342", pads=4), "user", "lib"),
    (_fp("D3", "LED_THT:LED_D5.0mm", pads=2, pth=2), "user", "lib"),
    (_fp("X1", "Molex:78171-0002", "Battery", pads=4), "connector", "lib"),
    # holes without copper
    (_fp("REF**", "panel:PanelHole_AudioJack_3.5mm", pads=1, npth=1), "mounting", "npth"),
    # names of custom footprints
    (_fp("J3", "x:CONN_FFC_0.5MM_1x20", pads=20), "connector", "name"),
    (_fp("KSW1", "yuiop:Cherry_MX_Hotswap_1.0u_v4", pads=2), "user", "name"),
    (_fp("D1", "DIYSynthMNL:LED_D5.0mm_BigPads", pads=2, pth=2), "user", "name"),
    (_fp("H1", "x:MECHANICAL_CLEARANCEHOLE_4_40", pads=1, pth=1), "mounting", "name"),
    # symbol names as values, then reference prefixes
    (_fp("P1", "x:SMD_4PAD", "CONN_01X04", pads=4), "connector", "value"),
    (_fp("J9", "x:1P-1.5x1.5", "EXTGND", pads=1), "connector", "ref"),
    (_fp("RV9", "x:RV2X4", "1K", pads=3, pth=3), "user", "ref"),
    # the user's choices: key switches and panel pots fixed, light pipes and LED bars too
    (_fp("SW3", "x:Gateron_KS-33_LowProfile", pads=2), "user", "name"),
    (_fp("RV3", "DIYSynthMNL:Potentiometer_RV09_BigPads", "CV_lvl_50k", pads=5, pth=5), "user", "name"),
    (_fp("D7", "x:LightPipe_3mm_SMD", pads=2), "user", "name"),
    (_fp("BAR1", "x:LED-Bar_10seg", pads=20, pth=20), "user", "name"),
    (_fp("J4", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "UART", pads=4, pth=4),
     "connector", "lib"),
    (_fp("JST1", "battery_connector_jst_ph_2", pads=2, pth=2), "connector", "name"),
    # castellated edge pads (circuitmonkey chips-0123: +12, GND, DAI0-2, EN) and 4UCONN micro-USB
    (_fp("DAI1", "CAST01-2.00MM:CAST-01X12.00MM", pads=3, pth=3), "connector", "name"),
    (_fp("+5", "x:Castellated_Pad_2mm", pads=1, pth=1), "connector", "name"),
    (_fp("X2", "x:4UCONN_20329", "MicroB", pads=13, pth=6), "connector", "name"),
])
def test_mech_classifier_fixes(fp, cls, rule):
    from kaebench.kicad_scripts import mech_rules
    got, evidence = mech_rules.classify(fp)
    assert got == cls and evidence.startswith(rule), (got, evidence)


@pytest.mark.parametrize("fp,rule", [
    (_fp("TP1", "TestPoint:TestPoint_Pad_D1.0mm", pads=1), "exclude"),
    (_fp("J1", "TestPoint:TestPoint_THTPad_D2.0mm_Drill1.0mm", "Conn_01x01", pads=1, pth=1), "exclude"),
    (_fp("JP1", "Jumper:SolderJumper-2_P1.3mm_Open_Pad1.0x1.5mm", pads=2), "exclude"),
    (_fp("JP2", "x:Header_1x02", pads=2, pth=2), "exclude"),
    (_fp("M12", "x:HEATSINK_WAKEFIELD_960", pads=2, npth=2), "exclude"),
    (_fp("G1", "Symbol:OSHW-Logo2_7.3x6mm_SilkScreen", pads=0), "exclude"),
    (_fp("USB1", "LEDs:LED-0805", "USB", pads=2), "conflict"),  # an LED named after what it shows
    (_fp("D1201", "BR_Discretes:SMA_L4.4-W2.6-LS5.0-RD", "60V 3A", pads=2), "conflict"),  # SMA diode
    (_fp("P1", "Package_DIP:DIP-28_W7.62mm_Socket_LongPads", "SUPP28", pads=28, pth=28), "exclude: IC socket"),
    (_fp("LED1", "Kobold:LED_choc_6028R", "RGB", pads=4), "conflict"),  # a per-key LED, not a switch
    (_fp("X1", "Crystal:Crystal_HC49-U_Vertical", pads=2, pth=2), "conflict"),
    (_fp("VR1", "x:SOT223", "LD1117", pads=4), "conflict"),
    (_fp("LED1", "dp-LED:SK6812-mini-e", pads=4), ""),
    (_fp("U1", "kbd:ProMicro_v3", "ProMicro", pads=24, pth=24), ""),
    # the user's choices: debug headers, batteries, trimmers and IC sockets stay free
    (_fp("J5", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical", "SWD", pads=10, pth=10),
     "exclude: programming/debug header"),
    (_fp("ISP1", "Connector_IDC:IDC-Header_2x03_P2.54mm_Vertical", "AVR", pads=6, pth=6),
     "exclude: programming/debug header"),
    (_fp("J1", "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", "TagConnect", pads=6),
     "exclude: programming/debug header"),
    (_fp("J3", "x:CONN_HEADER_1.27MM_2x10_SMT", "CORTEX_DEBUG_ETM", pads=20), "exclude: programming/debug header"),
    (_fp("BT1", "Battery:BatteryHolder_Keystone_3034_1x20mm", "CR2032", pads=3), "exclude: battery"),
    (_fp("BT2", "x:CellHolder_CR2032", pads=2, pth=2), "exclude: battery"),
    (_fp("RV1", "x:TRIM_3362P", "5K", pads=3, pth=3), "exclude: trimmer"),
    (_fp("RV2", "Potentiometer_THT:Potentiometer_Bourns_3296W_Vertical", pads=3, pth=3), "exclude: trimmer"),
    (_fp("P3", "footprints:40tex-Ell600", "SUPP40", pads=40, pth=40), "exclude: IC socket"),
    (_fp("J2", "CHIPSAlliance_Connector:SOIC-Socket_LOTES_ACA-SPI-004_2x04_P1.27mm", pads=8),
     "exclude: IC socket"),
    (_fp("D2", "LED_SMD:LED_0603_1608Metric", "LED", pads=2), "conflict"),
    # the user's judgement calls (rules 4)
    (_fp("U12", "footprints:sim72", "SIM4X32", pads=72, pth=72), "exclude: SIMM socket"),
    (_fp("MK1", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", "Microphone_Condenser",
         pads=2, pth=2), "exclude: microphone"),
    (_fp("RV4", "DIYSynthMNL:Potentiometer_RV09_BigPads", "Mix_trim_50k", pads=3, pth=3), "exclude: trimmer"),
])

def test_mech_classifier_leaves_free(fp, rule):
    from kaebench.kicad_scripts import mech_rules
    got, evidence = mech_rules.classify(fp)
    assert got is None and evidence.startswith(rule), (got, evidence)


def test_mech_classifier_keeps_a_prog_button_fixed():
    """The debug-header rule frees connectors only: a boot button labelled PROG stays fixed."""
    from kaebench.kicad_scripts import mech_rules
    got, _ = mech_rules.classify(_fp("SW2", "Button_Switch_SMD:SW_SPST_B3U-1000P", "PROG", pads=2))
    assert got == "user"


def test_mech_overrides():
    from kaebench.kicad_scripts import mech_rules
    rows = [dict(ref="J1", **{"class": "connector"}, evidence="lib: Connector"),
            dict(ref="U1", **{"class": None}, evidence="")]
    applied = mech_rules.apply_overrides(rows, {"fix": ["U1", "U9"], "free": ["J1"]})
    assert applied == {"fix": ["U1"], "free": ["J1"], "unknown": ["U9"]}
    assert [r["fixed"] for r in rows] == [False, True]
    assert rows[1]["class"] == "override" and rows[0]["evidence"].startswith("override: free")


def test_work_list_skips_place_fixed_whose_round_trip_failed():
    class Ad:
        name, kinds = "a", ("place", "place-fixed", "joint-fixed")
    ok = {"ok": True}
    rec = dict(id="b", tasks={"place": {"movable": 5}, "place-fixed": {"movable": 2}},
               roundtrip={"route": ok, "place": ok, "place-fixed": {"ok": False}})
    kinds = ("place", "place-fixed", "joint-fixed")
    assert [w[1] for w in runner.work_list([rec], [(Ad(), None)], kinds, 1)] == ["place"]
    rec["roundtrip"]["place-fixed"] = ok
    assert [w[1] for w in runner.work_list([rec], [(Ad(), None)], kinds, 1)] == list(kinds)
    assert [w[1] for w in runner.work_list([rec], [(Ad(), None)], kinds, 1, min_movable=3)] == ["place"]


@pytest.mark.parametrize("fp,cls", [
    # aligned with the placement research classifier
    (dict(_fp("J5", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", "Conn_01x05", pads=5, pth=5),
          nets=["GND", "+3V3", "/SWDIO", "/SWCLK", "/NRST"]), None),        # SWD by its nets
    (dict(_fp("J6", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", "Conn_01x05", pads=5, pth=5),
          nets=["GND", "/TX", "/RX", "/SDA", "/SCL"]), "connector"),         # UART/I2C stays
    (_fp("J7", "x:CHRG_PROG_HDR", "charger PROG", pads=2, pth=2), "connector"),  # not programming
    (_fp("JP9", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", "Jumper_2_Open", pads=2), None),
    (_fp("CT1", "kit:PinHeader_1x02_P2.54mm_Vertical", "JUMPER", pads=2, pth=2), None),
    (_fp("TP8", "x:CONN_U.FL_TE_1909763-1", "U.FL", pads=3), "connector"),  # an RF test port is a connector
    (_fp("TP9", "BR_Connectors:TEST-TH_BD2.54-P1.4_RED", "GND", pads=1, pth=1), None),
    (dict(_fp("U1", "x:TSOP39238_Standoff", "TSOP39238", pads=3, pth=3), nets=["GND", "VCC", "/IR"]), None),
    (_fp("U2", "x:ST_STUSB03EQR_QFN-16-1EP_3x3mm", "STUSB03EQR", pads=17), None),
    (_fp("U5", "modules:wemos-d1-mini-with-pin-header-and-connector", "WeMos_mini", pads=16, pth=16), None),
    (_fp("U1", "SwitchScience:RP2040_Breakout-PTH", "RP2040_breakout", pads=40, pth=40), None),
    (_fp("COMP1", "x:SWITCHCRAFT_PJRAN1X1U04X_CIRCULAR", "PJRAN1X1U04X", pads=3, pth=3), "connector"),
    (_fp("U3", "x:24pin0.5mm", "e-paper", pads=26), "user"),
    (_fp("RST1", "x:TS026660BK100SCRD", "TS02-66-60", pads=4, pth=4), "user"),
    (_fp("D4", "x:LED_custom", "RED", pads=2, pth=2), "user"),
    (_fp("REF1", "DIYSynthMNL:PanelHole_Bourns_3296W_TrimPot", pads=1, npth=1), "mounting"),  # a hole
])
def test_mech_classifier_matches_the_research_rules(fp, cls):
    from kaebench.kicad_scripts import mech_rules
    got, evidence = mech_rules.classify(fp)
    assert got == cls, (got, evidence)
