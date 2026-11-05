# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.critical_taut: critical copper tightened before it is locked, guarded by the
module's routed physics (critical_modules.quote). KiCad-free on the synthetic board
(critical_fixtures); the DRC check at the end is skipped without KiCad."""
import math

import pytest

import critical_fixtures as F
from kae.route import critical_write as W
from kae.route.critical_grid import Route


def _detour(s, m, key, offsets=(1.5, -1.5, 2.0, -2.0, 1.0, -1.0, 2.5, -2.5), width=None):
    """Replace module m's single-layer hop `key` by a legal two-piece detour through a point
    off its middle (the copy of a grid route that is not taut), `width` wide (default the
    hop's). Returns the detour's length."""
    sp = s.space
    rt = m.hops[key]
    if width is not None:
        rt = Route(net=rt.net, width=width, segs=rt.segs, vias=rt.vias, length=rt.length)
    assert rt is not None and rt.segs and len({l for l, _, _ in rt.segs}) == 1
    layer = rt.segs[0][0]
    a, b = rt.segs[0][1], rt.segs[-1][2]
    old = [it for it in m.copper if it.owner == (m.id, key) and it.kind == "track"]
    sp.remove(old)
    m.copper = [c for c in m.copper if c not in old]
    L = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    for off in offsets:
        c = (mid[0] - uy * off, mid[1] + ux * off)
        if not sp.track_violations(rt.net, layer, rt.width, a, c) and not sp.track_violations(rt.net, layer, rt.width, c, b):
            break
    else:
        pytest.skip("no legal detour on the synthetic board")
    for p, q in ((a, c), (c, b)):
        m.copper.append(sp.add_track(rt.net, layer, rt.width, p, q, owner=(m.id, key)))
    sp.invalidate()
    m.hops[key] = Route(net=rt.net, width=rt.width, segs=[(layer, a, c), (layer, c, b)], length=math.dist(a, c) + math.dist(c, b))
    from kae.route.critical_modules import quote
    quote(s.ctx, m)
    return m.hops[key].length


def _module(s, kind):
    return next(m for m in s.modules if m.kind == kind and m.status in ("routed", "partial"))


def _hop_key(m, prefix):
    return next(k for k, rt in m.hops.items() if k.startswith(prefix) and rt is not None and rt.segs
                and len({l for l, _, _ in rt.segs}) == 1)


@pytest.mark.parametrize("kind,prefix,width", [("decap", "rail:", None), ("cell", "hop", 0.5)],
                         ids=["decap-loop", "buck-hot-loop"])
def test_tightening_lowers_the_loop_and_is_kept(tmp_path, kind, prefix, width):
    """A detour the grid could have drawn is pulled taut: shorter, lower loop L, kept. (The buck
    hop is drawn 0.5 mm wide, inside its lands: at its full width taut's only legal entries are
    square through the long edges, which the guard refuses, see the next test.)"""
    s = F.session(tmp_path, tighten=True)
    s.route()
    m = _module(s, kind)
    key = _hop_key(m, prefix)
    detour = _detour(s, m, key, width=width)
    v0 = m.physics["value"]
    rep = s.tighten()
    row = next(r for r in rep["modules"] if r["id"] == m.id)
    assert row["kept"] >= 1 and rep["kept"] >= 1
    assert row["after"] < row["before"] * 0.999 and math.isclose(row["before"], v0, rel_tol=1e-4)
    assert m.physics["value"] == pytest.approx(row["after"], rel=1e-4)       # the stage value is the tightened copper's
    assert m.hops[key].length < detour - 0.1
    assert rep["after"]["length_mm"] < rep["before"]["length_mm"]
    for r in rep["modules"]:                   # the guard: no quoted module got worse
        if r.get("before") is not None:
            assert r["after"] <= r["before"] * (1 + rep["tol"]) + 1e-12, r
    # every kept piece is exactly legal on the session's space
    from kae.route import arcs as A
    for it in m.copper:
        if it.kind == "track":
            assert not A.polyline_violations(s.space, it.net, next(iter(it.layers)), it.width, list(it.geom.coords))
    # written locked, arcs as KiCad arcs
    out = tmp_path / "out" / "board.kicad_pcb"
    out.parent.mkdir()
    s.write(out)
    items = W.routing(out)
    assert items and all(r["locked"] for r in items)
    from kae.board.kicad_file import load
    b = load(out)
    assert len(b.tracks) == sum(1 for it in s.space.routed if it.kind == "track")
    assert sum(1 for t in b.tracks if t.mid is not None) == len(s.arcs)


def test_guard_keeps_the_hot_loop_when_taut_would_raise_it(tmp_path):
    """At its full width the buck's input hop overhangs both lands; taut's rule-D entries square
    through the long edges remove that but make the hot loop larger (synthetic board: 5.2 ->
    7.4 nH). The guard judges by the loop, not by the rule or the length: the cell keeps its
    copper and its value, while other modules may still be tightened."""
    s = F.session(tmp_path, tighten=True)
    s.route()
    m = _module(s, "cell")
    key = _hop_key(m, "hop")
    _detour(s, m, key)
    v0 = m.physics["value"]
    copper0 = {id(c) for c in m.copper}
    rep = s.tighten()
    row = next(r for r in rep["modules"] if r["id"] == m.id)
    assert row["after"] <= row["before"] * (1 + rep["tol"])
    if row["kept"] == 0:
        assert {id(c) for c in m.copper} == copper0 and m.physics["value"] == v0
        assert rep["refused_why"].get("physics", 0) >= 1


def test_guard_refuses_a_shorter_path_the_physics_quotes_worse(tmp_path, monkeypatch):
    """Shorter is not always a lower loop: a quote that rates the tightened hops worse keeps the
    module's copper exactly as it was."""
    from kae.route import critical_modules as CM
    s = F.session(tmp_path, tighten=True)
    s.route()
    m = _module(s, "decap")
    key = _hop_key(m, "rail:")
    _detour(s, m, key)
    hops0 = dict(m.hops)
    copper0 = {id(c) for c in m.copper}
    v0 = m.physics["value"]
    real = CM.quote

    def worse(ctx, mm, store=True):
        v = real(ctx, mm, store=store)
        if mm is m and v is not None and any(mm.hops.get(k) is not hops0.get(k) for k in hops0):
            return v * 1.5
        return v
    monkeypatch.setattr(CM, "quote", worse)
    rep = s.tighten()
    row = next(r for r in rep["modules"] if r["id"] == m.id)
    assert row["kept"] == 0 and rep["refused_why"].get("physics", 0) >= 1
    assert {id(c) for c in m.copper} == copper0
    assert all(m.hops[k] is hops0[k] for k in hops0)
    assert m.physics["value"] == v0


def test_keep45_leaves_the_copper_and_says_why(tmp_path):
    s = F.session(tmp_path, tighten=True, arc_policy="keep45")
    s.route()
    m = _module(s, "decap")
    _detour(s, m, _hop_key(m, "rail:"))
    before = [(id(it), it.geom.wkt) for it in s.space.routed]
    rep = s.tighten()
    assert "keep45" in rep["skipped"] and "segment-only" in rep["skipped"]
    assert [(id(it), it.geom.wkt) for it in s.space.routed] == before and not s.arcs
    assert s.report()["tighten"]["arc_policy"] == "keep45"


def test_untouched_copper_and_fixed_owners_stay(tmp_path):
    """Thermal spokes and stitching never move; a board with nothing to gain changes nothing."""
    s = F.session(tmp_path, tighten=True)
    s.route()
    fixed = [(id(it), it.geom.wkt) for it in s.space.routed if it.owner and it.owner[0] in ("spokes", "stitch")]
    rep = s.tighten()
    assert rep["kept"] + rep["refused"] == rep["groups"]
    left = {(id(it), it.geom.wkt) for it in s.space.routed}
    assert all(f in left for f in fixed)


@pytest.mark.kicad
def test_tightened_copper_adds_no_drc_error(tmp_path):
    from kae.board import pcbnew_io
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    from kae.route import drc
    s = F.session(tmp_path / "s", tighten=True)
    s.route()
    for kind, prefix in (("decap", "rail:"), ("cell", "hop")):
        m = _module(s, kind)
        _detour(s, m, _hop_key(m, prefix))
    out0 = tmp_path / "grid" / "board.kicad_pcb"
    out0.parent.mkdir()
    s.write(out0)
    rep = s.tighten()
    assert rep["kept"] >= 1
    out = tmp_path / "taut" / "board.kicad_pcb"
    out.parent.mkdir()
    s.write(out)
    e0 = drc.errors(drc.run(out0, tmp_path / "grid.json"))
    d1 = drc.run(out, tmp_path / "taut.json")
    e1 = drc.errors(d1)
    assert len(e1) <= len(e0), [(v["type"], v["description"]) for v in e1]
