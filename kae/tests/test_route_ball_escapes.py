# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dog-bones of a synthetic ball grid (kae.route.escape, no KiCad): the rings the surface
cannot escape get one each, in a diagonal gap, legal exactly; the outer rings are left."""
import math

from kae.board.kicad_file import load
from kae.route import constraints as CN
from kae.route import escape
from kae.route.critical_space import Space

import critical_fixtures as F

N = 8           # 8 x 8 balls
PITCH = 1.27    # 0.4 mm balls 0.87 mm apart: one 0.25 mm track at 0.2 mm clearance between them
BALLS = [(f"{chr(65 + r)}{c + 1}", f"S{r}{c}", (c - (N - 1) / 2) * PITCH, (r - (N - 1) / 2) * PITCH,
          0.4, 0.4, "smd", 0.0, "", "passive") for r in range(N) for c in range(N)]
GRID = ("U7", "BGA", "Package_BGA:Grid", 134.5, 121.0, 0.0, BALLS, (4.8, 4.8))
# each ball's partner, so every net needs routing
PARTNER = ("P7", "Pads", "x:Pads", 104.0, 125.0, 0.0,
           [(str(k + 1), b[1], (k % 9) * 0.5 - 2.0, (k // 9) * 0.6 - 1.0, 0.3, 0.3, "smd", 0.0, "", "passive")
            for k, b in enumerate(BALLS)], (2.5, 1.5))


def test_dog_bones_for_inner_rings_in_diagonal_gaps(tmp_path):
    sp, info = _space(tmp_path)
    assert escape.dog_bones(sp, info, log=lambda m: None) == (16, 16)    # rings 2 and 3: the inner 4 x 4
    vias = [it for it in sp.routed if it.kind == "via"]
    balls = {b[1]: (134.5 + b[2], 121.0 + b[3]) for b in BALLS}
    for v in vias:
        bx, by = balls[v.net]
        assert (v.geom.x - bx) * (bx - 134.5) > 0 and (v.geom.y - by) * (by - 121.0) > 0


def _space(tmp_path):
    p = F.write_board(tmp_path, extra=[GRID, PARTNER])
    info = F.synth_info(load(p))
    return Space(load(p), info, plan=CN.plan(info, p, {})), info


def test_escape_plan_escapes_every_ball_and_lays_legal_copper(tmp_path):
    sp, info = _space(tmp_path)
    out = escape.run(sp, info, {}, log=lambda m: None)
    (pk,) = out["packages"]
    assert pk["signal"] == 64 and pk["planned"] == 64 and not out["blocked"]
    # the outer rings on the surface, the rest through dog-bones to B.Cu
    assert pk["by_layer"]["F.Cu"] >= 28 and pk["by_layer"]["B.Cu"] >= 4
    assert pk["laid"] >= 44
    balls = {b[1]: (134.5 + b[2], 121.0 + b[3]) for b in BALLS}
    for r in pk["escapes"]:
        if r["via"]:
            bx, by = balls[r["net"]]
            assert abs(abs(r["via"][0] - bx) - PITCH / 2) < 1e-6 and abs(abs(r["via"][1] - by) - PITCH / 2) < 1e-6
    for it in sp.routed:
        if it.kind == "via":
            assert not sp.via_violations(it.net, it.geom.x, it.geom.y, ignore=(it,))
        else:
            a, b = it.geom.coords
            assert not sp.track_violations(it.net, next(iter(it.layers)), it.width, a, b, ignore=(it,))


def test_has_grid_only_for_ball_grids():
    """The bridge's escape stage runs only on boards with a ball grid or a fine-pitch pad ring
    (escape.has_grid)."""
    from kae.route.escape import has_grid
    grid = [dict(attr="smd", layers=["F.Cu"], pos=(x * 0.8, y * 0.8), fp_index=1) for x in range(5) for y in range(5)]
    row = [dict(attr="smd", layers=["F.Cu"], pos=(x * 0.5, 0.0), fp_index=2) for x in range(20)]
    coarse = [dict(attr="smd", layers=["F.Cu"], pos=(x * 1.27, 0.0), fp_index=3) for x in range(20)]
    assert has_grid(dict(pads=grid)) and has_grid(dict(pads=row)) and not has_grid(dict(pads=coarse))
    assert not has_grid({})


def test_escape_bound_proves_too_wide_tracks_cannot_escape(tmp_path):
    sp, info = _space(tmp_path)
    (pkg,) = [p for p in escape.find_packages(sp) if p["kind"] == "grid"]
    ok, meta, _ = escape.bound(sp, pkg, info)
    assert ok >= 64 - 0.5 and escape.certificate(sp, pkg, info, log=lambda m: None) is None
    # 2 mm tracks: no channel between two balls or two vias holds one. The bound still credits
    # a gap between two empty via sites with the one track that crosses a pitch with nothing at
    # its ends (it must over-estimate runs of empty sites of any length), and the LP spreads
    # the vias fractionally, so it proves less than the 16 inner balls the planner's model
    # shuts in: still a proof that not all escape
    assert escape.fit(PITCH - 0.4, 2.0, 0.2) == 0 and escape.fit(2 * PITCH - 0.6, 2.0, 0.2) == 0
    low, meta, duals = escape.bound(sp, pkg, info, override=dict(w=2.0))
    assert low < 64 - 0.5 and duals


def test_an_unsolved_bound_neither_certifies_nor_throws_away_the_plan(tmp_path, monkeypatch):
    """bound() returns (None, ctx, {}) when the LP relaxation does not solve; certificate()
    did `None + 1e-6`, and the TypeError in run() dropped the plan already computed."""
    monkeypatch.setenv("KAE_ESCAPE_CACHE", str(tmp_path / "cache"))
    sp, info = _space(tmp_path)
    (pkg,) = [p for p in escape.find_packages(sp) if p["kind"] == "grid"]
    monkeypatch.setattr(escape, "bound", lambda *a, **k: (None, {"sig": [1, 2, 3]}, {}))
    assert escape.certificate(sp, pkg, info, log=lambda m: None) is None

    def boom(*a, **k):
        raise RuntimeError("proof failed")
    monkeypatch.setattr(escape, "certificate", boom)
    out = escape.run(sp, info, {}, log=lambda m: None)
    (pk,) = out["packages"]
    assert "error" not in pk and pk["planned"] == 64 and pk["laid"] >= 44 and not out["blocked"]


def _grid_space(tmp_path, pitch, ball, small=(), net=lambda r, c: f"S{r}{c}", drop=()):
    """An 8 x 8 grid at `pitch` of `ball` mm pads (the indices in `small` 0.3 mm), each with a
    partner, on the synthetic 2-layer board (clearance 0.2, tracks >= 0.15, vias 0.6/0.3);
    `net(row, column)` names each ball's net."""
    balls = [(f"{chr(65 + r)}{c + 1}", net(r, c), (c - (N - 1) / 2) * pitch, (r - (N - 1) / 2) * pitch,
              0.3 if r * N + c in small else ball, 0.3 if r * N + c in small else ball, "smd", 0.0, "", "passive")
             for r in range(N) for c in range(N) if (r, c) not in drop]
    grid = ("U7", "BGA", "Package_BGA:Grid", 134.5, 121.0, 0.0, balls, (4.8, 4.8))
    p = F.write_board(tmp_path, extra=[grid, PARTNER])
    info = F.synth_info(load(p))
    sp = Space(load(p), info, plan=CN.plan(info, p, {}))
    (pkg,) = [q for q in escape.find_packages(sp) if q["kind"] == "grid"]
    return sp, info, pkg


def test_the_bound_uses_the_smallest_ball_not_the_median(tmp_path):
    """A certificate is a proof only if every capacity over-estimates the real one: one small
    ball (0.3 mm among 0.4 mm ones) sets the ball size of the bound, while the planner keeps
    its typical (median) value."""
    sp, info, pkg = _grid_space(tmp_path, PITCH, 0.4, small=(9,))
    assert abs(escape._setup(sp, pkg, info, minimum=True)["d"] - 0.3) < 1e-6
    assert abs(escape._setup(sp, pkg, info)["d"] - 0.4) < 1e-6


def test_breakpoints_are_where_a_capacity_steps():
    """Closed-form thresholds: at each breakpoint of the track width some gap holds one track
    more than a micrometre above it (fit(g) = floor((g - s1 - s2 + c) / (w + c)))."""
    r = dict(w=0.15, c=0.2, c_via=0.2, D=0.6, drill=0.3, c_pad=0.2)
    meta = dict(p=1.0, d=0.4, cpad=0.2, B="F.Cu", real=["F.Cu", "B.Cu"], R={"F.Cu": dict(r), "B.Cu": dict(r)})
    for key in ("w", "c", "D"):
        lo = 0.05 if key != "D" else 0.25
        bps = escape.breakpoints(meta, key, lo, r[key])
        assert bps and bps == sorted(bps, reverse=True) and all(lo <= v < r[key] for v in bps)
        for v in bps:
            def caps(x):
                out = []
                for l in meta["real"]:
                    rr = dict(meta["R"][l], **({"c": x, "c_via": x} if key == "c" else {key: x}))
                    out.append(sorted(escape._caps(meta["p"], meta["d"], meta["cpad"], rr, l == "F.Cu").items()))
                return out
            assert caps(v) != caps(round(v + 0.001, 3)), (key, v)


def test_certificate_says_no_obstruction_found_and_labels_the_fab_class(tmp_path):
    """At 1 mm pitch only via-in-pad or a via under JLCPCB's standard 0.45 mm escapes every
    ball. The certificate never says "feasible"; each relaxation is its exact threshold
    (the via diameter one step of the search above fails), never finer than the fab builds,
    labelled with the cheapest class; a class beyond standard is a manufacturing hazard."""
    sp, info, pkg = _grid_space(tmp_path, 1.0, 0.4)
    c = escape.certificate(sp, pkg, info, log=lambda m: None)
    assert c and "feasible" not in c["summary"] and "no obstruction found with" in c["summary"]
    assert c["fab"] == "JLCPCB" and c["short"] == 8
    via = next(r for r in c["relaxations"] if r["rule"] == "via diameter")
    assert via["all"] and via["exact"] and via["fab_class"] == "advanced" and 0.25 <= via["value"] < 0.45
    fl = escape.fab_floors(*escape._fab(sp, None))
    above, _m, _d = escape.bound(sp, pkg, info, override=dict(D=round(via["value"] + escape.VIA_GRID, 4)),
                                 floors=fl)
    assert above < c["demand"] - 0.5
    for r in c["relaxations"]:
        if "value" in r:
            assert r["value"] >= r.get("model_floor", 0.0) - 1e-9
    codes = {(h["code"], h["severity"], h["category"]) for h in c["hazards"]}
    assert codes == {("relaxation_beyond_standard_fab", "warn", "manufacturing")}
    assert len(c["hazards"]) == sum(1 for r in c["relaxations"] if r.get("all") and r.get("fab_class") != "standard"
                                    and "fab_class" in r)


def test_pad_ring_relaxations_are_labelled_and_never_feasible(tmp_path):
    """A 0.4 mm-pitch row of 0.32 mm pads at 0.2 mm clearance: a 0.10 mm track (JLCPCB's
    2-layer floor, the board sets 0.15) keeps 0.19 mm from the next pad at best. The ring
    certificate's track width (0.08 mm: no JLCPCB class) and clearance (0.19 mm: standard)
    are closed form, rounded down to micrometres, labelled, and never called "feasible"."""
    pads = [(str(k + 1), f"Q{k}", (k - 9.5) * 0.4, 0.0, 0.32, 0.8, "smd", 0.0, "", "passive") for k in range(20)]
    part = [(str(k + 1), f"Q{k}", (k % 10) * 0.6, (k // 10) * 0.8, 0.3, 0.3, "smd", 0.0, "", "passive")
            for k in range(20)]
    p = F.write_board(tmp_path, extra=[("U9", "Row", "x:Row", 130.0, 110.0, 0.0, pads, (8.5, 1.0)),
                                       ("P9", "Pads", "x:Pads", 104.0, 110.0, 0.0, part, (6.0, 1.0))])
    info = F.synth_info(load(p))
    sp = Space(load(p), info, plan=CN.plan(info, p, {}))
    (pkg,) = [q for q in escape.find_packages(sp) if q["kind"] == "ring" and q["ref"] == "U9"]
    c = escape.ring_certificate(sp, pkg, log=lambda m: None)
    assert c and "feasible" not in c["summary"] and c["fab"] == "JLCPCB"
    for r in c["relaxations"]:
        assert "fab_class" in r and r["value"] == round(r["value"], 3)
        assert r["all"] == (r["fab_class"] is not None)
    by = {r["rule"]: r for r in c["relaxations"]}
    assert by["track width"]["fab_class"] is None and by["clearance"]["fab_class"] == "standard"
    assert not c["hazards"] and "no obstruction found with clearance" in c["summary"]


def test_the_bound_credits_the_smallest_via_the_rules_allow(tmp_path):
    """A net class's via is only the default size of new vias; DRC checks the board setup's
    minimums. The bound credits the smallest via those allow, never finer than the fab's
    finest via."""
    sp, info = _space(tmp_path)
    s = sp.settings
    old = {k: s.get(k) for k in ("min_drill", "min_via", "min_annular")}
    try:
        s.update(min_drill=0.0, min_via=0.0, min_annular=0.0)
        assert escape.legal_via(sp) is None
        assert escape.legal_via(sp, dict(D=(0.2, 0.1))) == (0.2, 0.1)
        s.update(min_drill=0.2, min_via=0.3, min_annular=0.1)
        assert escape.legal_via(sp, dict(D=(0.2, 0.1))) == (0.4, 0.2)
    finally:
        s.update(old)


def test_the_demand_is_one_escape_per_net_that_leaves(tmp_path):
    """Balls of one net may join inside the ball field (four adjacent supply balls of a CSP, an
    eMMC's paired data balls), so the bound demands one escape per net with a pad off the
    package, not one per ball: the inner 4 x 4 on one net is one demand, and the 1 mm-pitch
    grid that leaves 8 inner balls shut in is no longer certified."""
    inner = lambda r, c: "S22" if 2 <= r <= 5 and 2 <= c <= 5 else f"S{r}{c}"    # noqa: E731
    sp, info, pkg = _grid_space(tmp_path, 1.0, 0.4, net=inner)
    e, ctx, _d = escape.bound(sp, pkg, info, floors=escape.fab_floors(*escape._fab(sp, None)))
    assert ctx["demand"] == 64 - 16 + 1 and e >= ctx["demand"] - 0.5
    assert escape.certificate(sp, pkg, info, log=lambda m: None) is None


def test_a_depopulated_interior_is_no_proof(tmp_path):
    """The model puts vias only at the dog-bone sites and in the pads; in a depopulated
    interior a via may sit anywhere (three eMMC-153 packages routed cleanly by hand were
    certified 1 net short). The entry says so and carries proof False."""
    sp, info, pkg = _grid_space(tmp_path, 1.0, 0.4, drop={(3, 3), (3, 4), (4, 3), (4, 4)})
    c = escape.certificate(sp, pkg, info, log=lambda m: None)
    assert c and c["proof"] is False and "not a proof" in c["summary"]
    sp, info, pkg = _grid_space(tmp_path / "full", 1.0, 0.4)
    assert escape.certificate(sp, pkg, info, log=lambda m: None)["proof"] is True
