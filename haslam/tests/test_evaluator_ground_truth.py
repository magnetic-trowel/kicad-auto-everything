# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The physics evaluator against answers known without it (docs/research/physics/evaluator-audit-2611.md, section 3).

Each case has a closed form or a hand calculation, written out in the test, not taken from the code under test:
- copper: a straight track's DC resistance rho L / (w t); a two-strip loop's partial inductance (Rosa/Ruehli bar
  self-inductance and filament mutual inductance, Grover), the raster's documented bias for tracks 1-3 cells wide;
- heating: IPC-2221's dT = (I / (k A^0.725))^(1/0.44) (A in mil^2) of the evaluator's own track reading;
- a synthetic board evaluated end to end (haslam.excite.evaluate, no KiCad): its rail and ground drop and copper loss
  by Ohm's law, a linear regulator's dissipation (V_in - V_out) I_out;
- a buck's loss from its datasheet efficiency point (TI TPS62933, SLUSE89, Figure 8-3: about 90 % at 12 V -> 3.3 V,
  2 A, read off the curve; the test uses the stated value, not the curve's exact reading);
- the published anchors of docs/research/physics/anchors-2611.md that pass (track heating, check 3).
"""
import math
import subprocess
import sys
from pathlib import Path

import pytest

RHO = 1.72e-8                  # ohm m, copper at 20 C (annealed, IEC 60028)
MU0 = 4e-7 * math.pi
T_CU = 0.035                   # mm, 1 oz


def _R(l_mm, w_mm, t_mm=T_CU):
    return RHO * l_mm * 1e-3 / (w_mm * 1e-3 * t_mm * 1e-3)


def _bar_self(l, w, t=T_CU):
    """Self partial inductance (H) of a straight rectangular bar, l x w x t mm (Rosa; Ruehli 1972)."""
    l, w, t = l * 1e-3, w * 1e-3, t * 1e-3
    return MU0 * l / (2 * math.pi) * (math.log(2 * l / (w + t)) + 0.5 + 0.2235 * (w + t) / l)


def _fil_mutual(l, d):
    """Mutual partial inductance (H) of two parallel filaments of length l at distance d, mm (Grover)."""
    l, d = l * 1e-3, d * 1e-3
    return MU0 * l / (2 * math.pi) * (math.log(l / d + math.sqrt(1 + (l / d) ** 2)) - math.sqrt(1 + (d / l) ** 2) + d / l)


def _hairpin_L(l, d, w):
    """A hairpin of two l-long strips d apart joined by a d-long one, driven at the open end: 2 L_s - 2 M + L_end."""
    return 2 * _bar_self(l, w) - 2 * _fil_mutual(l, d) + _bar_self(d, w)


def _hairpin(pitch, w, how, l=20.0, d=3.0):
    """(R ohm, L H) of the hairpin on one 35 um layer from haslam.em at 100 kHz (R-limited: uniform current)."""
    from haslam.em import solve as ES
    from haslam.em.mesh import Layer, Mesh
    m = Mesh.over(-2, -d / 2 - 2, l + 2, d / 2 + 2, pitch, [Layer("F.Cu", 0.0, T_CU, 1)])
    if how == "rect":
        m.rect(0, "A", 0, d / 2 - w / 2, l, d / 2 + w / 2)
        m.rect(0, "A", l - w, -d / 2 - w / 2, l, d / 2 + w / 2)
        m.rect(0, "A", 0, -d / 2 - w / 2, l, -d / 2 + w / 2)
    else:
        m.paint_line(0, "A", [(0, d / 2), (l, d / 2), (l, -d / 2), (0, -d / 2)], w)
    m.terminal("a", 0, xy=(0, d / 2), net="A")
    m.terminal("b", 0, xy=(0, -d / 2), net="A")
    V, _ = ES.potentials(m, {"a": 1.0, "b": -1.0}, 1e5, net=ES.Network(m))
    z = V["a"] - V["b"]
    return z.real, z.imag / (2 * math.pi * 1e5)


def test_a_track_loops_resistance_is_rho_l_over_w_t():
    """A 0.25 mm hairpin, 43 mm of track (two 20 mm strips and a 3 mm end), at the evaluator's 0.25 mm pitch."""
    R, _ = _hairpin(0.25, 0.25, "line")
    assert R == pytest.approx(_R(43.0, 0.25), rel=0.01)


def test_a_wide_hairpins_inductance_converges_to_the_partial_inductance():
    """Polygon copper (tracks 3 cells and wider, pours): within 3 % of the closed form, and from above as the pitch
    refines (a raster restricts the current: its inductance is an upper bound)."""
    ref = _hairpin_L(20.0, 3.0, 0.5)                       # 26.46 nH
    Ls = [_hairpin(p, 0.5, "rect")[1] for p in (0.25, 0.125)]
    assert all(abs(L / ref - 1) < 0.03 for L in Ls), (Ls, ref)


@pytest.mark.parametrize("w, lo, hi", [(0.15, -0.04, 0.0), (0.25, -0.01, 0.01), (0.5, 0.05, 0.09), (0.7, 0.11, 0.15)])
def test_a_narrow_tracks_inductance_and_the_rasters_known_bias(w, lo, hi):
    """A track narrower than 3 cells is a chain of cells carrying its true width (haslam.em.mesh.paint_line; the
    evaluator's tracks under 0.75 mm at 0.25 mm). Its self term is corrected to the true width, its neighbours'
    mutual terms are not: up to one cell wide it meets the closed form (-2.5 % .. 0 %); 2 and 2.8 cells wide it reads
    7 % and 13 % high. That is the band the evaluator's mesh note states (-3 % .. +16 %); this test pins it, so a change
    to the raster shows here."""
    _, L = _hairpin(0.25, w, "line")
    err = L / _hairpin_L(20.0, 3.0, w) - 1
    assert lo <= err <= hi, err


def test_the_heating_observer_meets_ipc_2221():
    """dc.ipc_dT against IPC-2221 written out: dT = (I / (k A^0.725))^(1/0.44), k 0.048 outer, A in mil^2. 2 A on a
    0.5 mm, 35 um outer track: A = 27.12 mil^2, A^0.725 = 10.94, dT = (2 / 0.525)^2.273 = 20.9 K."""
    from haslam.excite import dc as DC
    A = (0.5 / 0.0254) * (0.035 / 0.0254)
    assert DC.ipc_dT(2.0, 0.5, 0.035) == pytest.approx((2.0 / (0.048 * A ** 0.725)) ** (1 / 0.44), rel=1e-12)
    assert DC.ipc_dT(2.0, 0.5, 0.035) == pytest.approx(20.9, abs=0.05)


def _pad(num, x, y, nid, net, fn="", pt="", w=1.0, h=1.0):
    extra = (f' (pinfunction "{fn}")' if fn else "") + (f' (pintype "{pt}")' if pt else "")
    return f'\t\t(pad "{num}" smd rect (at {x} {y}) (size {w} {h}) (layers "F.Cu") (net {nid} "{net}"){extra})\n'


def _fp(ref, value, lib, x, y, pads, k):
    return (f'\t(footprint "{lib}" (layer "F.Cu") (uuid "00000000-0000-0000-0000-{k:012d}") (at {x} {y})\n'
            f'\t\t(property "Reference" "{ref}" (at 0 0) (layer "F.SilkS"))\n'
            f'\t\t(property "Value" "{value}" (at 0 1) (layer "F.Fab"))\n' + "".join(pads) + '\t)\n')


def _seg(a, b, w, nid):
    return f'\t(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {w}) (layer "F.Cu") (net {nid}))\n'


HDR = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"


def _board(tmp_path, nets, fps, segs):
    head = '(kicad_pcb (version 20240108) (generator "test")\n\t(net 0 "")\n' + \
           "".join(f'\t(net {i} "{n}")\n' for i, n in enumerate(nets, 1))
    edge = "".join(f'\t(gr_line (start {a} {b}) (end {c} {d}) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts"))\n'
                   for a, b, c, d in ((0, 0, 60, 0), (60, 0, 60, 20), (60, 20, 0, 20), (0, 20, 0, 0)))
    p = tmp_path / "gt.kicad_pcb"
    p.write_text(head + edge + "".join(fps) + "".join(segs) + ")\n")
    return p


def _evaluate(p, facts):
    from haslam.board import kicad_file
    from haslam.excite.evaluate import evaluate
    b = kicad_file.load(p, rules=False)
    return evaluate(str(p), b=b, intent=facts, cells=False, drc=False, fills={}, log=lambda m: None)


def test_a_synthetic_boards_drop_and_copper_loss_are_ohms_law(tmp_path):
    """J1 brings 5 V in (the facts name it: two identical headers on one rail leave the source unsaid); a 0.5 mm
    track 40 mm long feeds J2, which exports a stated 1 A; it returns over a 2 mm ground
    track. Pad centre to pad centre, by hand: R_rail = 38.3 mOhm and R_gnd = 9.6 mOhm over the 39 mm between the 1 mm
    pads' facing edges (the evaluator reads 1 % above it); drop = 1 A x (R_rail + R_gnd), copper loss = 1 A^2 x the same, both at 20 C and then
    at the copper's temperature (the evaluator's TCR factor, which it reports)."""
    nets = ["VIN", "GND"]
    fps = [_fp("J1", "Conn_01x02", HDR, 10, 10, [_pad("1", 0, 0, 1, "VIN", pt="passive"),
                                                 _pad("2", 0, 3, 2, "GND", pt="passive")], 1),
           _fp("J2", "Conn_01x02", HDR, 50, 10, [_pad("1", 0, 0, 1, "VIN", pt="passive"),
                                                 _pad("2", 0, 3, 2, "GND", pt="passive")], 2)]
    p = _board(tmp_path, nets, fps, [_seg((10, 10), (50, 10), 0.5, 1), _seg((10, 13), (50, 13), 2.0, 2)])
    r = _evaluate(p, {"nets": {"VIN": {"V_V": 5.0, "source": "J1", "kind": "external"}}, "parts": {"J2": {"I_A": 1.0}},
                      "requirements": {"thermal": {"T_amb_C": 20}}})
    assert r["total"]["complete"]
    rows = {h["observer"]: h for h in r["harms"]}
    drop, loss = rows["dc:drop:J2@VIN"], rows["dc:copper_loss"]
    R = _R(39.0, 0.5) + _R(39.0, 2.0)                    # between the pads' facing edges
    f_d, f_l = drop.get("copper_temp_factor") or 1.0, loss.get("copper_temp_factor") or 1.0
    assert 1.0 <= f_d < 1.05 and 1.0 <= f_l < 1.05        # 50 mW in 60 x 20 mm: a few kelvin
    assert drop["dV_mV"] / f_d == pytest.approx(1.0 * R * 1e3, rel=0.03)
    assert loss["P_mW"] / f_l == pytest.approx(1.0 ** 2 * R * 1e3, rel=0.03)
    # the rail track's rise by IPC-2221 at 1 A: A = 27.12 mil^2, (1 / 0.525)^2.273 = 4.3 K; its 40 mm run, held by
    # the pads at both ends, is a fin of l = w t sqrt(k_Cu dT / rho) / I = 5.47 mm: 4.3 (1 - 1/cosh(40 / 10.94)) = 4.08 K
    heat = rows["dc:heating:VIN@F.Cu"]
    assert heat["I_A"] == pytest.approx(1.0, rel=1e-3) and heat["ipc_K"] == pytest.approx(4.3, abs=0.06)
    assert heat["track"]["run_mm"] == pytest.approx(40.0) and heat["track"]["held_ends"] == 2
    assert heat["dT_K"] == pytest.approx(4.08, abs=0.06)


def test_a_linear_regulators_dissipation_is_its_drop_times_its_current(tmp_path):
    """5 V in, a SOT-223 LDO to 3.3 V, a stated 0.5 A export: (5 - 3.3) x 0.5 = 0.85 W, exactly."""
    nets = ["VIN", "3V3", "GND"]
    fps = [_fp("J1", "Conn_01x02", HDR, 5, 10, [_pad("1", 0, 0, 1, "VIN", pt="passive"),
                                                _pad("2", 0, 2.54, 3, "GND", pt="passive")], 1),
           _fp("U1", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 30, 10,
               [_pad("1", 0, 2.3, 3, "GND", "GND", "power_in"), _pad("2", 0, 0, 2, "3V3", "VO", "power_out"),
                _pad("3", 0, -2.3, 1, "VIN", "VI", "power_in")], 2),
           _fp("J2", "Conn_01x02", HDR, 55, 10, [_pad("1", 0, 0, 2, "3V3", pt="passive"),
                                                 _pad("2", 0, 2.54, 3, "GND", pt="passive")], 3)]
    segs = [_seg((5, 10), (30, 7.7), 0.5, 1), _seg((30, 10), (55, 10), 0.5, 2),
            _seg((5, 12.54), (30, 12.3), 1.0, 3), _seg((30, 12.3), (55, 12.54), 1.0, 3)]
    p = _board(tmp_path, nets, fps, segs)
    r = _evaluate(p, {"nets": {"VIN": {"V_V": 5.0}, "3V3": {"V_V": 3.3, "source": "U1", "from": "VIN", "kind": "linear"}},
                      "parts": {"J2": {"I_A": 0.5}}, "requirements": {"thermal": {"T_amb_C": 25}}})
    assert r["part_power_W"]["U1"] == pytest.approx((5.0 - 3.3) * 0.5, rel=1e-9)


def test_a_bucks_loss_from_its_datasheet_efficiency():
    """TPS62933 (TI SLUSE89, Figure 8-3): about 90 % at 12 V -> 3.3 V, 2 A. Stated as cells.<id>.eta 0.9, the converter
    loses P_out (1/eta - 1) = 6.6 W x 0.111 = 0.733 W; its inductor's winding (50 mOhm stand-in) takes I^2 DCR =
    0.2 W of it at its own pads, the controller the rest, 0.533 W; the input draws P_out / (eta V_in) = 0.611 A."""
    from types import SimpleNamespace as NS

    from haslam.excite import dc as DC
    from haslam.excite import heat as H
    from haslam.excite.beliefs import Param
    from haslam.excite.circuit import Circuit
    from haslam.excite.models import _par, _rl, _rlc
    cell = dict(id="c", cls="buck", src="cell:c", vin="VIN", vout="3V3", sw="SW", ctrl="U1", rect=None, ind="L1")
    pl = DC.Plan()
    pl.volts = {"VIN": 12.0, "3V3": 3.3}
    pl.pads = {"J1": [("1", "VIN", "", ""), ("2", "GND", "", "")],
               "U1": [("1", "VIN", "power_in", "VIN"), ("2", "SW", "", "SW"), ("3", "GND", "", "GND")],
               "J2": [("1", "3V3", "", ""), ("2", "GND", "", "")]}
    pl.grounds = {"GND"}
    pl.feeds = {"VIN": dict(kind="external", ref="J1", out=["J1.1"], gnd=["J1.2"], rating=5.0),
                "3V3": dict(kind="cell", cell=cell, ref="U1", eta=Param("dc:U1", "eta", 0.9, 0.9, 0.9, "", "intent", "t"))}
    pl.loads = [dict(ref="J2", rail="3V3", sup=["J2.1"], gnd=["J2.2"], key=("dc:J2", "I_A"))]
    cv = {("dc:J2", "I_A"): 2.0, ("dc:U1", "eta"): 0.9, "cell:c": {"I_A": 2.0, "D": 3.3 / 12}}
    inj = DC.injections(pl, cv)
    assert inj["J1.1"] == pytest.approx(3.3 * 2.0 / (0.9 * 12.0))
    c = Circuit("GND")
    c.z("L1", "SW", "3V3", _par(_rl(0.05, 4.7e-6), _rlc(0, 0, 5e-12)), "L1.1", "L1.2", "L")
    heat = H.part_heat(NS(part_kind={}, circuit=c), pl, cv, {}, inj)
    loss = 3.3 * 2.0 * (1 / 0.9 - 1)
    assert heat["U1"] + 2.0 ** 2 * 0.05 == pytest.approx(loss)
    assert loss == pytest.approx(0.733, abs=1e-3)


def test_the_published_track_heating_anchor_passes():
    """anchors-2611 check 3: IPC-2221 and the Brooks-Adam fit of IPC-2152 reproduce every tabulated value."""
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, str(root / "tools/research/physics/anchors/track_heating.py")],
                       capture_output=True, text=True, env={"PYTHONPATH": str(root / "haslam/src")}, timeout=120)
    assert r.returncode == 0 and "VERDICT: PASS" in r.stdout, r.stdout[-500:]
