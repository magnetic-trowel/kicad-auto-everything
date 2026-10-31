# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.blocked: why open connections are open, on the synthetic board (no KiCad).
Its rules: clearance 0.2 mm (net class Default), track width 0.25 mm (class) and at least 0.15 mm
(board setup)."""
from kae.board.kicad_file import load
from kae.route import blocked as B
from kae.route import constraints as CN
from kae.route import critical_write as W

import critical_fixtures as F

XTAL = "Net-(U2-XTAL1)"      # U2.2, Y1.1, C4.1: three pads, no copper yet


def _report(net, *pads):
    return {"unconnected_items": [{"items": [{"description": f"Pad {n} [{net}] of {r} on F.Cu"} for r, n in pads]}]}


def _diagnose(p, rep, input_ids=()):
    info = F.synth_info(load(p))
    plan = CN.plan(info, p, {})
    return B.diagnose(p, info, plan, [], rep, input_ids=input_ids, log=lambda *a: None)


def _boxed(gap, dup=False):
    """SIG's pad S1.1 inside a box of +3V3 pads 0.35 mm away, open by `gap` mm at the bottom
    (no room for a via inside), and its other pad T1.1 5 mm below; `dup`: T1 has a no-net pad
    on top of T1.1 (a footprint with a duplicate pad)."""
    smd = lambda n, net, x, y, w, h: (n, net, x, y, w, h, "smd", 0.0, "", "passive")   # noqa: E731
    side = (2.2 - gap) / 4
    box = [smd("1", "SIG", 0.0, 0.0, 0.5, 0.5),
           smd("2", "+3V3", -0.85, 0.0, 0.5, 2.2), smd("3", "+3V3", 0.85, 0.0, 0.5, 2.2),
           smd("4", "+3V3", 0.0, -0.85, 2.2, 0.5),
           smd("5", "+3V3", -1.1 + side, 0.85, 2 * side, 0.5), smd("6", "+3V3", 1.1 - side, 0.85, 2 * side, 0.5)]
    tgt = [smd("1", "SIG", 0.0, 0.0, 0.5, 0.5)] + ([smd("2", "", 0.0, 0.0, 0.5, 0.5)] if dup else [])
    return [("S1", "box", "Test:Box", 136.0, 118.0, 0.0, box, (1.3, 1.3)),
            ("T1", "pad", "Test:Pad", 136.0, 124.0, 0.0, tgt, (0.5, 0.5))]


def test_congestion_is_not_blamed_on_a_rule(tmp_path):
    """A wall of our own copper (+3V3 across the board on both layers) cuts C4.1 off: a path
    exists without it, so the connection is congestion, not a rule; the same wall as the
    input's own copper is reported as such, with its net."""
    p = F.write_board(tmp_path)
    x = 114.7
    wall = [("+3V3", l, 0.25, (x, 100.6), (x, 129.4), W.new_uuid(), False) for l in ("F.Cu", "B.Cu")]
    W.append_items(p, p, tracks=wall)
    rep = _report(XTAL, ("C4", 1), ("U2", 2))
    out = _diagnose(p, rep)
    # three pads apart: two missing connections, C4.1's behind the wall
    assert not out["blocked"] and [r["cause"] for r in out["congestion"]] == ["congestion"] * 2
    out = _diagnose(p, rep, input_ids={w[5] for w in wall})
    assert [r["cause"] for r in out["blocked"]] == ["fixed copper"] and out["blocked"][0]["fixed_nets"] == ["+3V3"]
    assert out["blocked"][0]["pads"] == ["C4.1"] and len(out["congestion"]) == 1


def test_a_gap_a_narrower_track_fits_blames_the_minimum_width(tmp_path):
    """A 0.5 mm gap between +3V3 pads at 0.2 mm clearance leaves 0.1 mm for a track: the board's
    0.15 mm minimum (board setup) binds, and the report says which narrower track would pass."""
    p = F.write_board(tmp_path, extra=_boxed(0.5))
    out = _diagnose(p, _report("SIG", ("S1", 1), ("T1", 1)))
    assert len(out["blocked"]) == 1 and not out["congestion"]
    r = out["blocked"][0]
    b = r["binding"]
    assert r["cause"] == "rule" and r["pads"] in (["S1.1"], ["T1.1"])
    assert b["constraint"] == "track_width" and b["required"] == 0.15 and 0.05 <= b["available"] <= 0.1
    assert "board setup minimum track width" in b["where"] and b["source"] == "board"
    assert b["clearance"]["required"] == 0.2
    assert "relax to" in r["line"] and out["summary"] == [r["line"]]


def test_a_gap_no_track_fits_blames_the_net_class_clearance(tmp_path):
    p = F.write_board(tmp_path, extra=_boxed(0.3))
    out = _diagnose(p, _report("SIG", ("S1", 1), ("T1", 1)))
    b = out["blocked"][0]["binding"]
    assert out["blocked"][0]["cause"] == "rule"
    assert b["constraint"] == "clearance" and b["required"] == 0.2 and b["available"] < 0.2
    assert "net class 'Default'" in b["where"] and b["against"].startswith("pad S1.")


def test_a_pad_under_another_pad_is_geometry(tmp_path):
    """T1.1 lies under a no-net pad of its own footprint: no path even with every clearance at
    zero; the report names the pad that walls it in."""
    p = F.write_board(tmp_path, extra=_boxed(1.0, dup=True))
    out = _diagnose(p, _report("SIG", ("S1", 1), ("T1", 1)))
    r = out["blocked"][0]
    assert r["cause"] == "geometry" and any("pad T1.2" in w for w in r["walled_by"])


def test_rule_sources():
    """Constraint rule names map to where the rule lives, kae's own defaults with their override."""
    assert B._source("netclass 'Power'")[1] == ".kicad_pro net class 'Power'"
    assert B._source("my_bga_rule")[1] == ".kicad_dru rule 'my_bga_rule'"
    assert B._source("my_bga_rule (inside its area)")[1] == ".kicad_dru rule 'my_bga_rule'"
    k = B._source("clearance not checked on this board (floor 0.1 mm)")
    assert k[0] == "kae" and "KAE_IGNORED_CLEARANCE_FLOOR" in k[2]
