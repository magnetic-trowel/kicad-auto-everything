# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The report-only bus tables: aggregation and rendering from scorecard records."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("KAE_RESULTS", "/tmp/kaeres-busreport-test-store")
import busreport as B  # noqa: E402


def rec(board, a="J1", b="J2", names=("D0", "D1", "D2", "D3"), lanes_open=0, skew=2.0, vias=0.5, keyed=True, ok=1, decomp=False):
    r = dict(kind="ddr_byte", width=len(names), a=a, b=b, names=list(names), multi_lanes=0, lanes_open=lanes_open, open_items=lanes_open * 2,
             complete=lanes_open == 0, measured=len(names), len_mean=30.0, vias_lane=vias, via_equal=1, via_span_mismatch=0, skew_mm=skew,
             skew_ps=skew * 6.8, layer_agreement=0.9, coupled_3w=0.5, limit=dict(keyed=keyed, skew_mm=1.0), _board=board, _src="drc")
    if ok is not None:
        r["skew_ok"] = ok
    if decomp:
        r["skew_decomp"] = dict(n=4, trunked=4, tbar_ps_mm=6.5, mm_yy=4.0, ps_yy=170.0,
                                mm=dict(chord=[1.0, 1.0, 1.0], fan=[0.5, 0.5, 1.0], meander=[0.0, 0.0, 0.0], turn=[2.0, 2.0, 2.0], other=[0.5, 0.5, 1.0]),
                                ps=dict(length=[170.0, 170.0, 13.0], layer=[0.0, 0.0, 0.0], via=[0.0, 0.0, 0.0]))
    return r


def test_class_row_counts():
    r = B._class_row("m", "ddr_byte", [rec("b1", lanes_open=1, ok=0, keyed=True), rec("b2", ok=1, keyed=False), rec("b2", a="U1", ok=None)])
    assert r["buses"] == 3 and r["boards"] == 2 and r["lanes_open"] == 1 and r["lanes"] == 12
    assert r["skew_ok_keyed"] == 0 and r["skew_n_keyed"] == 1 and r["skew_ok_assumed"] == 1 and r["skew_n_assumed"] == 1


def test_complete_in_both_matches_on_board_and_names():
    a = [rec("b1"), rec("b1", a="U9"), rec("b2", lanes_open=2)]
    b = [rec("b1"), rec("b2")]
    assert [x["a"] for x, _ in B._complete_in_both(a, b)] == ["J1"]


def test_decomposition_shares_add_to_one_and_tables_render():
    recs = [rec("b1", decomp=True), rec("b2", decomp=True)]
    t, ps = B._decomp_table(recs)
    assert sum(v[0] for v in t.values()) == 1.0
    per = {"human": {"ddr_byte": recs}, "fr": {"ddr_byte": recs}}
    text = "\n".join(B.tables(per, {"human": 2, "fr": 2}, {}))
    assert "Skew decomposition" in text and "Against the human" in text


def test_outputs_load_with_the_projects_net_classes(tmp_path):
    """A run keeps only its board; the scorecard's pair tier needs the net classes of the project's .kicad_pro."""
    import gzip
    import json
    import pytest
    pytest.importorskip("kae.board.kicad_file")
    from kae.board.kicad_file import load
    from kae.route.pairs import tier_of
    fixture = Path(__file__).resolve().parents[3] / "bench" / "tests" / "fixtures" / "two_pads.kicad_pcb"
    text = fixture.read_text().replace('"N1"', '"SIG_P"').replace('"N2"', '"SIG_N"')
    run = tmp_path / "output.kicad_pcb.gz"
    with gzip.open(run, "wt") as f:
        f.write(text)
    proj = tmp_path / "corpus"
    proj.mkdir()
    (proj / "board.kicad_pro").write_text(json.dumps(dict(net_settings=dict(
        classes=[dict(name="Default", clearance=0.2, track_width=0.2, diff_pair_width=0.2, diff_pair_gap=0.25),
                 dict(name="HS", clearance=0.15, track_width=0.15, diff_pair_width=0.12, diff_pair_gap=0.12)],
        netclass_patterns=[dict(pattern="SIG_*", netclass="HS")]))))
    work = tmp_path / "work"
    work.mkdir()
    board = B.load_output(run, proj, work)
    assert board.nets["SIG_P"].netclass.split(",")[0] == "HS"     # KiCad 10 names the effective class "HS,Default"
    assert tier_of(board, "SIG_P", "SIG_N")[0] == "rule"        # a class that sets its own pair width and gap
    bare = load(str(work / "b.kicad_pcb"), rules=False)          # what busreport loaded before: no class, no rule tier
    assert tier_of(bare, "SIG_P", "SIG_N")[0] == "name"
