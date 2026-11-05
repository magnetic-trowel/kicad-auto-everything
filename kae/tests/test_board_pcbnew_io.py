# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board.pcbnew_io against live pcbnew (skipped without KiCad's Python)."""
import json
import math
import random
import shutil
from pathlib import Path

import pytest

from kae.board import kicad_file, pcbnew_io, sdiff, transform

DATA = Path(__file__).parent / "data" / "board"
FIXTURE = DATA / "fixture.kicad_pcb"

pytestmark = [pytest.mark.kicad,
              pytest.mark.skipif(not pcbnew_io.available(), reason="no Python with pcbnew")]


def _copy(tmp_path, name="board", text=None):
    p = tmp_path / f"{name}.kicad_pcb"
    if text is None:
        shutil.copy(FIXTURE, p)
    else:
        p.write_text(text)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(FIXTURE.with_suffix(ext), p.with_suffix(ext))
    return p


def test_verify_live_and_golden_unchanged():
    x = pcbnew_io.extract(FIXTURE)
    rep = pcbnew_io.verify(FIXTURE, data=x)
    assert rep["pad_err"] < 1e-6 and rep["net_mismatch"] == rep["layer_mismatch"] == 0
    assert rep["courtyard"]["max_straight"] < 1e-5 and rep["netclass_diff"] == {}
    golden = json.loads((DATA / "fixture.pcbnew.json").read_text())
    pads = {(f["uuid"], p["uuid"]): (p["x"], p["y"]) for f in golden["footprints"] for p in f["pads"]}
    for f in x["footprints"]:
        for p in f["pads"]:
            gx, gy = pads[(f["uuid"], p["uuid"])]
            assert abs(gx - p["x"]) < 1e-9 and abs(gy - p["y"]) < 1e-9


def _random_poses(b, rng):
    poses = {}
    for fp in b.footprints:
        if fp.locked:
            continue
        rot = rng.choice([0.0, 90.0, 180.0, 270.0, rng.uniform(0, 360)])
        poses[fp.uuid] = (round(fp.x + rng.uniform(-8, 8), 6), round(fp.y + rng.uniform(-8, 8), 6), rot,
                          rng.choice("FB"))
    return poses


def test_write_poses_round_trip(tmp_path):
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    poses = _random_poses(b, random.Random(11))
    assert any(s == "B" for *_, s in poses.values()) and any(r % 90 for _, _, r, _ in poses.values())
    out = tmp_path / "out.kicad_pcb"
    res = pcbnew_io.write_poses(src, out, poses)
    assert res["moved"] == len(poses) and res["flipped"] > 0
    assert not out.with_suffix(".kicad_pro").exists()          # no project files written
    x = pcbnew_io.extract(out, courtyards=False, outline=False)
    k = {f["uuid"]: f for f in x["footprints"]}
    worst = 0.0
    for fp in b.footprints:
        X, Y, R, S = poses.get(fp.uuid, (fp.x, fp.y, fp.rot, fp.side))
        kf = k[fp.uuid]
        assert kf["side"] == S
        kp = {p["uuid"]: p for p in kf["pads"]}
        for p in fp.pads:
            ex, ey = transform.pad_xy(fp, p, X, Y, R, S)
            worst = max(worst, math.hypot(ex - kp[p.uuid]["x"], ey - kp[p.uuid]["y"]))
    assert worst < 1e-6
    # the written file reads back the same in the library frame
    b2 = kicad_file.load(out)
    old = b.by_uuid()
    for f2 in b2.footprints:
        f1 = old[f2.uuid]
        q1 = {p.uuid: p for p in f1.pads}
        for p in f2.pads:
            assert abs(p.lx - q1[p.uuid].lx) < 2e-6 and abs(p.ly - q1[p.uuid].ly) < 2e-6
            assert transform.layers_at(q1[p.uuid].layers, f1.side, f2.side, 4) == p.layers or \
                set(transform.layers_at(q1[p.uuid].layers, f1.side, f2.side, 4)) == set(p.layers)
    # nothing but the moved footprints changed; moving them back restores the file
    base = tmp_path / "base.kicad_pcb"
    pcbnew_io.resave(src, base)
    assert sdiff.diff(src, base) == []
    changes = sdiff.diff(base, out)
    assert changes and all(c["kind"] == "footprint" and c["change"] == "changed" for c in changes)
    assert {c["id"] for c in changes} <= set(poses)
    back = tmp_path / "back.kicad_pcb"
    pcbnew_io.write_poses(out, back, {fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in b.footprints
                                      if fp.uuid in poses})
    # pcbnew keeps off-axis rectangles as polygons and text upright: nothing else differs
    assert sdiff.diff(base, back, tol=1e-4, rotation_artifacts=True) == []


def test_write_poses_refusals(tmp_path):
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    locked = next(f for f in b.footprints if f.locked)
    out = tmp_path / "out.kicad_pcb"
    with pytest.raises(pcbnew_io.PcbnewError, match="locked"):
        pcbnew_io.write_poses(src, out, {locked.uuid: (1, 1, 0, "F")})
    with pytest.raises(pcbnew_io.PcbnewError, match="unknown"):
        pcbnew_io.write_poses(src, out, {"no-such-uuid": (1, 1, 0, "F")})
    assert not out.exists()
    pcbnew_io.write_poses(src, out, {locked.uuid: (locked.x + 1, locked.y, 0, "F")}, allow_locked=True)
    assert kicad_file.load(out).by_uuid()[locked.uuid].x == locked.x + 1
    # the older argument order, and a unique reference as the key
    u1 = next(f for f in b.footprints if f.ref == "U1")
    pcbnew_io.write_poses(src, {"U1": (u1.x, u1.y + 2, 180, "B")}, out)
    f = kicad_file.load(out).by_uuid()[u1.uuid]
    assert (f.y, f.rot, f.side) == (u1.y + 2, 180.0, "B")


def test_kicad8_dialect_through_pcbnew(tmp_path):
    from test_board_kicad_file import _to_kicad8
    p = _copy(tmp_path, "k8", _to_kicad8(FIXTURE.read_text()))
    rep = pcbnew_io.verify(p)
    assert rep["pad_err"] < 1e-6 and rep["net_mismatch"] == 0 and not rep["missing_fp"]
    assert rep["locked_mismatch"] == [] and rep["netclass_diff"] == {}


def test_missing_kae_tmpdir_falls_back_to_the_default(monkeypatch):
    """A KAE_TMPDIR the process cannot see (e.g. hidden by a sandbox tmpfs) must not break
    pcbnew calls: the default temporary directory is used instead."""
    monkeypatch.setenv("KAE_TMPDIR", "/nonexistent/kae-tmp")
    assert pcbnew_io._tmpdir() is None
    monkeypatch.setenv("KAE_TMPDIR", "/tmp")
    assert pcbnew_io._tmpdir() == "/tmp"


def test_worker_answers_as_a_process_per_call(tmp_path, monkeypatch):
    """The worker (default) and a KiCad process per call (KAE_PCBNEW_WORKER=0) return the
    same JSON and write the same bytes."""
    src = _copy(tmp_path)
    poses = _random_poses(kicad_file.load(src), random.Random(5))
    moved, dsn = tmp_path / "moved.kicad_pcb", tmp_path / "board.dsn"
    got = {}
    for mode in ("1", "0"):
        monkeypatch.setenv("KAE_PCBNEW_WORKER", mode)
        res = [pcbnew_io.extract(src), pcbnew_io.zone_fills(src), pcbnew_io.text_shapes(src),
               pcbnew_io.write_poses(src, moved, poses), pcbnew_io.export_dsn(src, dsn),
               pcbnew_io.edit_routing(moved, moved, lock_all=True)]
        got[mode] = (json.dumps(res), moved.read_bytes(), dsn.read_bytes())
        moved.unlink()
        dsn.unlink()
    assert got["1"] == got["0"]


def test_worker_timeout_and_restart(monkeypatch):
    monkeypatch.setenv("KAE_PCBNEW_WORKER", "1")
    n = len(pcbnew_io.extract(FIXTURE)["footprints"])
    with pytest.raises(pcbnew_io.PcbnewError, match="timed out"):
        pcbnew_io.zone_fills(FIXTURE, timeout=0.01)
    assert all(w.proc.poll() is None for w in pcbnew_io._ALL)  # the timed-out worker is gone
    w = pcbnew_io._acquire(300)
    w.proc.kill()  # a worker that died while idle is replaced
    w.proc.wait()
    pcbnew_io._release(w)
    assert len(pcbnew_io.extract(FIXTURE)["footprints"]) == n
    assert w not in pcbnew_io._ALL


# ----------------------------------------------------------------------------- write checks
def _ses(path, nets, vias=()):
    """A minimal Specctra session: nets {name: [(layer, [(x, y), ...])]} in mm, KiCad frame;
    vias [(net, x, y)] with one through padstack."""
    k = 10000.0      # (resolution um 10): units per mm

    def xy(p):
        return f"{round(p[0] * k)} {round(-p[1] * k)}"
    body = []
    names = list(nets) + [v[0] for v in vias if v[0] not in nets]
    for name in names:
        body.append(f'      (net "{name}"')
        for layer, pts in nets.get(name, ()):
            body.append(f"        (wire (path {layer} 2500 {' '.join(xy(p) for p in pts)}))")
        for n, x, y in vias:
            if n == name:
                body.append(f'        (via "Via[0-3]_600:300_um" {xy((x, y))})')
        body.append("      )")
    path.write_text("(session s (base_design s)\n  (routes (resolution um 10)\n"
                    '    (library_out (padstack "Via[0-3]_600:300_um" (shape (circle F.Cu 6000 0 0))'
                    " (shape (circle B.Cu 6000 0 0)) (attach off)))\n"
                    "    (network_out\n" + "\n".join(body) + "\n    )\n  )\n)\n")
    return path


def test_writes_check_stamp_counts_and_nets(tmp_path):
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    u1 = next(f for f in b.footprints if f.ref == "U1")
    out = tmp_path / "out.kicad_pcb"
    res = pcbnew_io.write_poses(src, out, {u1.uuid: (u1.x + 1, u1.y, 270, "F")})
    chk = res["write_check"]
    assert chk["stamp_in"] == chk["stamp_out"] == 20260206
    assert chk["counts_changed"] == {} and chk["pads_changed"] == chk["routing_changed"] == chk["zones_changed"] == 0
    assert chk["counts"]["footprints"] == len(b.footprints) and res["hazards"] == []
    # a KiCad 8 board comes out in KiCad 10's format: said, as a data hazard
    from test_board_kicad_file import _to_kicad8
    k8 = _copy(tmp_path, "k8", _to_kicad8(FIXTURE.read_text()))
    res = pcbnew_io.resave(k8, tmp_path / "k8out.kicad_pcb")
    assert res["write_check"]["stamp_in"] == 20240108 and res["write_check"]["stamp_out"] == 20260206
    assert [h["code"] for h in res["hazards"]] == ["kicad_format_upgraded"]
    assert res["hazards"][0]["severity"] == "warn" and res["hazards"][0]["category"] == "data"


def test_edit_routing_refuses_unknown_nets_and_layers(tmp_path):
    src = _copy(tmp_path)
    out = tmp_path / "out.kicad_pcb"
    for net, layer in (("NOPE", "F.Cu"), ("", "F.Cu"), ("GND", "Bogus.Cu"), ("GND", "F.SilkS")):
        with pytest.raises(pcbnew_io.PcbnewRefused) as e:
            pcbnew_io.edit_routing(src, out, add=[dict(net=net, layer=layer, a=[1, 1], b=[2, 1], width=0.2)])
        assert e.value.detail["unknown_nets"] or e.value.detail["unknown_layers"]
        assert not out.exists()
    res = pcbnew_io.edit_routing(src, out, add=[dict(net="GND", layer="In2.Cu", a=[1, 1], b=[2, 1], width=0.2)])
    assert res["added"] == 1 and res["hazards"] == []
    assert any(t.net == "GND" and t.layer == "In2.Cu" for t in kicad_file.load(out).tracks)


def test_import_ses_keeps_preroute_nets_and_checks_the_session(tmp_path):
    from kae.route.bridge import import_session
    src = _copy(tmp_path)
    pre = tmp_path / "pre.kicad_pcb"
    # a locked GND pre-route that ends on U1 pad 1 (SIG1): KiCad's import rebuilds
    # connectivity, which would hand it SIG1
    pcbnew_io.edit_routing(src, pre, add=[dict(net="GND", layer="F.Cu", a=[7.0, 9.2], b=[8.5, 9.2], width=0.2)],
                           lock_all=True)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy(src.with_suffix(ext), pre.with_suffix(ext))
    before = {t.uuid: t.net for t in kicad_file.load(pre).tracks}
    ses = _ses(tmp_path / "good.ses", {"SIG2": [("F.Cu", [(19.2, 11.5), (25.0, 11.5), (39.717, 10.566)])]},
               vias=[("SIG2", 25.0, 11.5)])
    out = tmp_path / "out.kicad_pcb"
    res = import_session(pre, ses, out)
    after = kicad_file.load(out)
    assert {t.uuid: t.net for t in after.tracks if t.uuid in before} == before
    assert set(res["kept"]) >= set(before)
    chk = res["import_check"]
    assert chk["session"] == dict(segments=2, arcs=0, vias=1) and chk["landed"] == chk["session"]
    assert chk["missing"] == {} and chk["extra"] == {}
    assert all(h["severity"] != "block" for h in res["hazards"])
    if res["renetted"]:      # KiCad moved the pre-route; kae put it back and says so
        assert res["renetted"][0]["net"] == "GND"
        assert "preroute_overlaps_foreign_pad" in [h["code"] for h in res["hazards"]]
    # a wire on a net the board does not have lands on net 0; one on an unknown layer is skipped
    bad = _ses(tmp_path / "bad.ses", {"NOPE": [("F.Cu", [(60, 30), (65, 30)])],
                                       "SIG3": [("Bogus.Cu", [(60, 35), (65, 35)])]})
    res = import_session(pre, bad, tmp_path / "bad.kicad_pcb")
    codes = {h["code"]: h["severity"] for h in res["hazards"]}
    assert codes.get("ses_import_wrong_net") == "block" and codes.get("ses_import_incomplete") == "warn"


def test_write_poses_keep_upright_arm(tmp_path):
    """keep_upright turns parts with FOOTPRINT::Rotate: same poses and pads as
    SetOrientation, footprint texts kept readable (equal up to sdiff's rotation artefacts)."""
    src = _copy(tmp_path)
    b = kicad_file.load(src)
    poses = {f.uuid: (f.x, f.y, (f.rot + 180.0) % 360.0, f.side) for f in b.footprints if not f.locked}
    plain, upright = tmp_path / "plain.kicad_pcb", tmp_path / "upright.kicad_pcb"
    pcbnew_io.write_poses(src, plain, poses)
    pcbnew_io.write_poses(src, upright, poses, keep_upright=True)
    a, c = kicad_file.load(plain).by_uuid(), kicad_file.load(upright).by_uuid()
    for u, (x, y, rot, side) in poses.items():
        assert abs(c[u].x - x) < 1e-6 and abs((c[u].rot - rot + 180) % 360 - 180) < 1e-6
        assert all(math.hypot(p.x - q.x, p.y - q.y) < 2e-6 for p, q in zip(a[u].pads, c[u].pads))
    assert sdiff.diff(plain, upright, rotation_artifacts=True) == []


def test_write_check_reports_merged_duplicate_drawings(tmp_path):
    """KiCad's writer keeps board drawings in a std::set ordered without the uuid, so an
    exact duplicate is written once: reported as a data hazard, not an error."""
    text = FIXTURE.read_text()
    i = text.index("\t(gr_line")
    j = text.index("\n\t)\n", i) + 4
    dup = text[i:j]
    u = dup.split('(uuid "', 1)[1].split('"', 1)[0]
    text = text[:j] + dup.replace(u, "00000000-0000-4000-8000-0000000d0b1e") + text[j:]
    src = _copy(tmp_path, "dup", text)
    res = pcbnew_io.resave(src, tmp_path / "out.kicad_pcb")
    assert res["write_check"]["drawings_merged"] == 1 and res["write_check"]["drawings_lost"] == 0
    assert [h["code"] for h in res["hazards"]] == ["kicad_write_merged_duplicate_drawings"]
