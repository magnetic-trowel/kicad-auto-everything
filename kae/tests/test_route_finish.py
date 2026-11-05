# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.journal (entries, dependencies, identity diff, noise, the gate) and kae.route.finish."""
import json
from pathlib import Path

import pytest

from kae.route import critical_write as W
from kae.route import journal as J

HEAD = '(kicad_pcb\n\t(version 20250114)\n\t(generator "pcbnew")\n'


def _board(*items):
    return HEAD + "".join(items) + ")\n"


def _seg(uid, net, a, b, w=0.2, layer="F.Cu"):
    return W.track_sexpr(net, layer, w, a, b, uid=uid, locked=False)


def _via(uid, net, x, y):
    return W.via_sexpr(net, x, y, 0.6, 0.3, uid=uid, locked=False)


def _chain():
    """Input: A (N1) and B (N2). tails: A -> A1. taut: A1 -> A2 (builds on tails). power: a via of
    N2 where A was (builds on tails: it uses the room A left) and C widened from B (on its own)."""
    t0 = _board(_seg("A", "N1", (0, 0), (5, 0)), _seg("B", "N2", (0, 5), (5, 5)))
    t1 = _board(_seg("A1", "N1", (0, 0), (5, 0.5)), _seg("B", "N2", (0, 5), (5, 5)))
    t2 = _board(_seg("A2", "N1", (0, 0.2), (5, 0.5)), _seg("B", "N2", (0, 5), (5, 5)))
    t3 = _board(_seg("A2", "N1", (0, 0.2), (5, 0.5)), _seg("B", "N2", (0, 5), (5, 5), w=0.6),
                _via("V", "N2", 2.5, -0.3))
    jr = J.Journal(t0)
    jr.add(J.diff_entries("tails", t0, t1, {"A": "a", "A1": "a"}))
    jr.add(J.diff_entries("taut", t1, t2))
    jr.add(J.diff_entries("power", t2, t3, {"B": "B", "V": "V"}))
    return jr, (t0, t1, t2, t3)


def test_journal_entries_and_dependency_revert():
    jr, (t0, t1, t2, t3) = _chain()
    ids = {e.id for e in jr.entries}
    assert ids == {"tails:a", "taut:net:N1", "power:B", "power:V"}
    by = jr.by_id
    assert by["taut:net:N1"].deps == {"tails:a"}            # it rewrote the tail's track
    assert "tails:a" in by["power:V"].deps                  # the via sits where the old tail was
    assert by["power:B"].deps == set()                      # widened in place, on its own
    # reverting the tail takes the taut change and the via with it, not the widening
    assert jr.dependants({"tails:a"}) == {"tails:a", "taut:net:N1", "power:V"}
    assert jr.closed(ids - {"tails:a"}) == {"power:B"}
    # every kept set rebuilds a board: none = the input, all = the last pass's items
    assert set(J.items(jr.text(set()))) == {"A", "B"}
    assert set(J.items(jr.text())) == set(J.items(t3))
    assert J.items(jr.text())["B"][1] == J.items(t3)["B"][1]
    only_b = J.items(jr.text({"power:B"}))
    assert set(only_b) == {"A", "B"} and "(width 0.6)" in only_b["B"][1]
    # an output item stands for the input items it replaced
    anc = jr.ancestry()
    assert anc["A2"] == {"A"} and anc["V"] == {"power:V"}


def _rep(*viol, unconnected=0):
    return dict(violations=[dict(type=t, severity="error",
                                 items=[dict(uuid=u, description=u, pos=dict(x=x, y=y)) for u, x, y in its])
                            for t, its in viol],
                unconnected_items=[dict(items=[])] * unconnected)


def test_identity_diff_matches_rewritten_items_not_counts():
    base = _rep(("clearance", [("P", 1.0, 1.0), ("A", 1.1, 1.0)]))
    anc = {"A2": {"A"}, "V": {"power:V"}}
    # the same violation on the track that replaced A, moved a little: not new
    assert J.diff(base, _rep(("clearance", [("P", 1.0, 1.0), ("A2", 1.2, 1.1)])), anc) == []
    # same count, another violation: new (counts would have called this no worse)
    new = J.diff(base, _rep(("clearance", [("Q", 9.0, 9.0), ("V", 9.0, 9.1)])), anc)
    assert len(new) == 1 and new[0][0] == "clearance"
    assert J.judge([base], _rep(("clearance", [("Q", 9.0, 9.0), ("V", 9.0, 9.1)])), anc) == {"clearance": 1}
    # the same items further along the rewritten track: still the same violation (it moved with it)
    assert J.diff(base, _rep(("clearance", [("P", 4.0, 4.0), ("A2", 4.0, 4.0)])), anc) == []
    # but only once: a second one on the same items is new
    two = _rep(("clearance", [("P", 1.0, 1.0), ("A2", 1.2, 1.1)]), ("clearance", [("P", 4.0, 4.0), ("A2", 4.0, 4.0)]))
    assert len(J.diff(base, two, anc)) == 1 and J.diff(base, two, anc)[0][1][0][1] == (4.0, 4.0)
    # unconnected by count
    assert J.judge([base], _rep(("clearance", [("P", 1, 1), ("A", 1.1, 1)]), unconnected=1)) == {"unconnected": 1}


def test_noisy_type_is_judged_by_count_against_the_larger_run():
    r1 = _rep(("solder_mask_bridge", [("P1", 0, 0)]), ("solder_mask_bridge", [("P2", 5, 5)]),
              ("clearance", [("P", 1, 1)]))
    r2 = _rep(("solder_mask_bridge", [("P1", 0, 0)]), ("solder_mask_bridge", [("P3", 9, 9)]),
              ("solder_mask_bridge", [("P4", 12, 12)]), ("clearance", [("P", 1, 1)]))
    assert J.noise_types(r1, r2) == ["solder_mask_bridge"]
    out = _rep(("solder_mask_bridge", [("P7", 20, 20)]), ("solder_mask_bridge", [("P8", 30, 30)]),
               ("solder_mask_bridge", [("P9", 40, 40)]), ("clearance", [("P", 1, 1)]))
    assert J.judge([r1], out) == {"solder_mask_bridge": 3}
    assert J.judge([r1, r2], out, noise=["solder_mask_bridge"]) == {}      # 3 <= max(2, 3)
    out4 = _rep(*[("solder_mask_bridge", [(f"Q{i}", i, i)]) for i in range(4)])
    assert J.judge([r1, r2], out4, noise=["solder_mask_bridge"]) == {"solder_mask_bridge": 1}


def _fake_drc(rules):
    """A DRC stand-in: `rules` (board text -> [(type, [(uuid, x, y)])]) per call; records calls."""
    calls = []

    def run(board, out_json, timeout=900, cache=True):
        text = Path(board).read_text()
        calls.append(dict(uuids=set(J.items(text)), cache=cache))
        rep = _rep(*rules(text, len(calls)))
        Path(out_json).write_text(json.dumps(rep))
        return rep
    return run, calls


def test_gate_reverts_the_culprit_and_its_dependants_only(tmp_path):
    jr, (t0, *_rest) = _chain()
    src = tmp_path / "in" / "board.kicad_pcb"
    src.parent.mkdir()
    src.write_text(t0)

    def rules(text, k):
        return [("clearance", [("V", 2.5, -0.3)])] if '"V"' in text else []
    run, calls = _fake_drc(rules)
    g = J.gate(src, src, jr, tmp_path / "g", drc_run=run, log=lambda *a: None, recover=0)
    assert g["kept"] == {"tails:a", "taut:net:N1", "power:B"}
    assert g["drc_out"]["errors"] == 0 and g["drc_runs"] == len(calls)
    # input, the full output, the noise run (no cache), the attributed board
    assert [c["cache"] for c in calls] == [True, True, False, True]
    assert set(J.items(g["text"])) == {"A2", "B"}
    # with recovery, the reverted entry is tried again once (and stays out)
    run, calls = _fake_drc(rules)
    g = J.gate(src, src, jr, tmp_path / "g2", drc_run=run, log=lambda *a: None)
    assert g["kept"] == {"tails:a", "taut:net:N1", "power:B"} and len(calls) == 5


def test_gate_ddmin_when_nothing_is_attributable(tmp_path):
    jr, (t0, *_rest) = _chain()
    src = tmp_path / "in" / "board.kicad_pcb"
    src.parent.mkdir()
    src.write_text(t0)

    def rules(text, k):
        # the widened B starves something far away, reported against items nobody changed
        return [("starved_thermal", [("PAD9", 80.0, 80.0)])] if "(width 0.6)" in text else []
    run, _ = _fake_drc(rules)
    g = J.gate(src, src, jr, tmp_path / "g", drc_run=run, log=lambda *a: None)
    assert "power:B" not in g["kept"] and {"tails:a", "taut:net:N1", "power:V"} <= g["kept"]
    assert g["drc_out"]["errors"] == 0 and any(r["tag"].startswith("dd") for r in g["rounds"])
    assert "starved_thermal" not in J.items(g["text"])["B"][1] and "(width 0.6)" not in g["text"]


def test_gate_noise_run_keeps_a_board_whose_only_difference_is_noise(tmp_path):
    jr, (t0, *_rest) = _chain()
    src = tmp_path / "in" / "board.kicad_pcb"
    src.parent.mkdir()
    src.write_text(t0)

    def rules(text, k):
        # the mask-bridge set moves between runs whatever the board
        return [("solder_mask_bridge", [(f"P{k}", 3.0 * k, 0.0)])]
    run, calls = _fake_drc(rules)
    g = J.gate(src, src, jr, tmp_path / "g", drc_run=run, log=lambda *a: None)
    assert g["noise"] == ["solder_mask_bridge"] and g["kept"] == set(jr.by_id) and len(calls) == 3


def test_gate_reuses_the_callers_input_report(tmp_path):
    jr, (t0, *_rest) = _chain()
    src = tmp_path / "in" / "board.kicad_pcb"
    src.parent.mkdir()
    src.write_text(t0)
    run, calls = _fake_drc(lambda text, k: [])
    g = J.gate(src, src, jr, tmp_path / "g", base_report=_rep(), drc_run=run, log=lambda *a: None)
    assert g["drc_in_reused"] and len(calls) == 1 and g["kept"] == set(jr.by_id)


def test_finish_cache_hit(tmp_path, monkeypatch):
    from kae.route import finish, stepcache
    monkeypatch.setenv("KAE_STEP_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("KAE_CHARGE_FILE", str(tmp_path / "charge.jsonl"))
    monkeypatch.setattr(stepcache, "kicad_version", lambda prefix: "10.0.7")
    monkeypatch.setattr("kae.route.drc.kicad_cli", lambda: ("kicad-cli",))
    src = tmp_path / "in.kicad_pcb"
    src.write_text(_board(_seg("A", "N1", (0, 0), (5, 0))))
    runs = []

    def fake(inp, out, project, o, workdir, time_s, base_report, drc_s, log):
        runs.append(o["parts"])
        J.write(_board(_seg("A2", "N1", (0, 0), (5, 0))), out, project)
        return dict(kept=1, parts=dict(ran=list(o["parts"]), skipped={})), True
    monkeypatch.setattr(finish, "_run", fake)
    r1 = finish.run(src, tmp_path / "o1.kicad_pcb", time_s=100)
    r2 = finish.run(src, tmp_path / "o2.kicad_pcb", time_s=100)
    assert len(runs) == 1 and r1["step_cache"] == "stored" and r2["step_cache"] == "hit"
    assert (tmp_path / "o2.kicad_pcb").read_text() == (tmp_path / "o1.kicad_pcb").read_text()
    finish.run(src, tmp_path / "o3.kicad_pcb", opts=dict(parts=("taut",)), time_s=100)    # other options: a miss
    assert len(runs) == 2
    lines = [json.loads(x) for x in (tmp_path / "charge.jsonl").read_text().splitlines()]
    assert [x["hit"] for x in lines if x["step"] == "finish"] == [False, True, False]


def test_estimate_skips_power_copper_when_the_reserve_is_short(tmp_path):
    from kae.route import finish
    src = tmp_path / "b.kicad_pcb"
    src.write_text(HEAD + "".join("\t(footprint\n\t\t(pad \"1\")\n\t)\n" for _ in range(2000)) + ")\n")
    est = finish.estimate(src)
    assert est["taut"] > est["tails"] and est["power"] > 0 and est["total"] > est["taut"] + est["gate"]


@pytest.mark.kicad
def test_finish_end_to_end_on_a_fixture_board(tmp_path):
    from kae.board import pcbnew_io
    if not pcbnew_io.available():
        pytest.skip("no Python with pcbnew")
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from test_route_taut import _detour_board
    from kae.board.kicad_file import load
    from kae.route import finish
    from kae.route.arcs import track_length
    src = _detour_board(tmp_path)
    rep = finish.run(src, tmp_path / "out" / "board.kicad_pcb", workdir=tmp_path / "w", log=lambda *a: None)
    assert rep["parts"]["ran"] == ["tails", "taut", "power"] and not rep["parts"]["failed"]
    for t, n in rep["drc_out"]["by_type"].items():
        assert n <= rep["drc_in"]["by_type"].get(t, 0)
    assert rep["drc_out"]["unconnected"] <= rep["drc_in"]["unconnected"]
    assert rep["stages"]["taut"]["kept_entries"] >= 1
    after = load(tmp_path / "out" / "board.kicad_pcb")
    assert sum(track_length(t) for t in after.tracks if t.net == "SIGA") < 15.0 + 1e-6
    # one gate: the input, the output, and only what a worse output needs
    assert rep["drc_runs"] <= 2 + len(rep["gate_rounds"])
    assert all(e["stage"] in ("tails", "taut", "power") for e in rep["journal"])


def test_entries_of_one_pass_in_conflict_are_merged():
    """Taut moves N2 away and N1 into the room it left: reverting N2 alone would put it back on N1's
    new copper, so the two are one entry (either order in the diff)."""
    t0 = _board(_seg("A", "N1", (0, 0), (5, 0)), _seg("B", "N2", (0, 1), (5, 1)), _seg("C", "N3", (0, 9), (5, 9)))
    t1 = _board(_seg("A2", "N1", (0, 0), (5, 1)), _seg("B2", "N2", (0, 1), (5, 2)), _seg("C2", "N3", (0, 9), (5, 8)))
    jr = J.Journal(t0, margin=0.2).add(J.diff_entries("taut", t0, t1))
    assert len(jr.entries) == 2
    big = next(e for e in jr.entries if "|" in e.net)
    assert big.net == "N1|N2" and set(big.after) == {"A2", "B2"} and sorted(big.meta["merged"])
    assert set(J.items(jr.text({big.id}))) == {"A2", "B2", "C"}
