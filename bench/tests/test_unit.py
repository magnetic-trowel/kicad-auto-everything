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

from kaebench import boardfiles, fetch, manifest, report, score, tools

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
