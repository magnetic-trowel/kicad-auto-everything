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
