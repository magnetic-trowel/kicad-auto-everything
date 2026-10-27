# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""End to end against kicad-cli: ERC clean, schematic netlist identical to the IR, DRU parses."""
import json
from pathlib import Path

import pytest

from kaesynth.build import build
from kaesynth.lib import C, LED, NMOS, PINMAP_SOT23_FET, R, Conn

from test_core import isolated_design, opto

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "usb-led" / "design.py"


@pytest.mark.kicad
def test_example_builds_clean(tmp_path):
    d, findings, status, kicad = build(EXAMPLE, tmp_path, date="2026-01-01")
    assert kicad["ran"]
    assert kicad["netlist_problems"] == []
    assert kicad["erc_summary"].startswith("0 errors")
    assert status["error"] == 0
    assert (tmp_path / "usb-led.kicad_sch").exists() and (tmp_path / "intent.yaml").exists()


@pytest.mark.kicad
def test_deterministic_output(tmp_path):
    build(EXAMPLE, tmp_path / "a", date="2026-01-01")
    build(EXAMPLE, tmp_path / "b", date="2026-01-01")
    for name in ("usb-led.kicad_sch", "power.kicad_sch", "led.kicad_sch", "intent.yaml", "netlist.json"):
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text(), name


@pytest.mark.kicad
def test_barrier_rules_and_lib_parts(tmp_path):
    d, b, u = isolated_design(opto().with_(footprint="Package_DIP:SMDIP-4_W9.53mm"))
    d.nets["L"].connect(u["A"])
    rl = b.add(R("100k", "2512", v_max=200), p_diss=0.15)      # (120 V - 2 V)^2 / 100k
    n_a = b.net("LED_K", domain="MAINS", v=(-170, 170))
    d.nets["N"].connect(rl[1]); n_a.connect(rl[2], u["K"])
    q = b.add(NMOS("2N7002", "Package_TO_SOT_SMD:SOT-23", vds=60, vgs=20, i_d=0.3, pinmap=PINMAP_SOT23_FET))
    d.nets["IO"].connect(u["C"], q["G"]); d.nets["GND"].connect(u["E"], q["S"])
    led = b.add(LED(), v_across=3.0)     # never reverse biased: anode pulled to +5V
    rr = b.add(R("1k"))
    j = b.add(Conn(3, "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", v_max=50, i_max=1))
    v5 = d.net("+5V", domain="SELV", v=(0, 5.25), kind="power")
    k = b.net("K", domain="SELV", v=(0, 5.25))
    a = b.net("A", domain="SELV", v=(0, 5.25))
    v5.connect(j[1], rr[1]); a.connect(rr[2], led["A"]); k.connect(led["K"], q["D"])
    d.nets["GND"].connect(j[2]); d.nets["IO"].connect(j[3])
    jm = b.add(Conn(2, "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
                    v_max=250, i_max=10))
    d.nets["L"].connect(jm[1]); d.nets["N"].connect(jm[2])
    d.place.separate("MAINS", "SELV")
    _, findings, status, kicad = build(d, tmp_path, date="2026-01-01")
    assert kicad["netlist_problems"] == [], kicad["netlist_problems"]
    assert kicad["dru"] == "ok", kicad["dru"]
    dru = (tmp_path / "iso.kicad_dru").read_text()
    assert "creepage (min 5mm)" in dru and "hasNetclass('MAINS')" in dru
    # the renumbered MOSFET symbol lands in the project library with numeric pins
    lib = (tmp_path / "kaesynth.kicad_sym").read_text()
    assert 'Q_NMOS_G1S2D3' in lib
    errs = {f.check for f in findings if f.severity == "error" and not f.waived_by}
    assert not errs, [f.message for f in findings if f.severity == "error"]


def two_board_design(with_connector=True):
    from kaesynth import Design
    from kaesynth.lib import Conn, Fuse
    d = Design("twob")
    d.net("GND", domain="LV", v=0, kind="ground")
    d.domain("LV", ref="GND")
    d.board("main", width_mm=40, height_mm=30)
    d.board("remote", width_mm=20, height_mm=15)
    hv = d.net("PWR", domain="LV", v=(0, 12), kind="power", i_max=1)
    hdr = lambda: Conn(2, "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", v_max=50, i_max=3)
    a = d.block("a", board="main")
    j1 = a.add(hdr(), ref="J1")
    r1 = a.add(R("10k"))
    b = d.block("b", board="remote")
    j2 = b.add(hdr(), ref="J2")
    r2 = b.add(R("10k"))
    h = d.block("harness", board="off")
    f = h.add(Fuse(2, 32, None, mpn="ATO-2", manufacturer="Littelfuse"))
    mid = d.net("PWR_F", domain="LV", v=(0, 12), kind="power", i_max=1)
    hv.connect(j1[1], r1[1], f[1])
    mid.connect(f[2], j2[1] if with_connector else r2[2], r2[1])
    d.nets["GND"].connect(j1[2], r1[2], j2[2])
    if with_connector:
        d.nets["GND"].connect(r2[2])
    return d


def test_crossing_needs_connector():
    from kaesynth.checks import Checker
    errs = [f for f in Checker(two_board_design(False)).run() if f.check == "board.crossing_without_connector"]
    assert errs and "remote" in errs[0].message


@pytest.mark.kicad
def test_multi_board_projects(tmp_path):
    d = two_board_design()
    _, findings, status, kicad = build(d, tmp_path, date="2026-01-01")
    errs = [f.message for f in findings if f.severity == "error" and not f.waived_by]
    assert not errs, errs
    assert kicad["boards"] == {"main": [], "remote": []}
    assert (tmp_path / "board-main" / "twob-main.kicad_sch").exists()
    main_intent = (tmp_path / "board-main" / "intent.yaml").read_text()
    assert "J1" in main_intent and "J2" not in main_intent
    bom = (tmp_path / "bom.csv").read_text()
    assert "off,F" in bom.replace('"', "") and "harness" in bom
