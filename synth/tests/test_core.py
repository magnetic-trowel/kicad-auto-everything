# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""IR and check behaviour that does not need KiCad (all parts use generated symbols)."""
import pytest

from kaesynth import Design, DesignError, Isolation, PinDef, Ratings, VLimit
from kaesynth.checks import Checker
from kaesynth.ir import PartDef
from kaesynth import sexpr


def two_pin(name, v_max=None, cat="resistor", p_max=None, value="1k"):
    return PartDef(mpn=name, value=value, category=cat, footprint="Resistor_SMD:R_0603_1608Metric",
                   pins=[PinDef(1, "A"), PinDef(2, "B")], ratings=Ratings(v_max=v_max, p_max=p_max))


def opto(grade="reinforced", v_iso=5000):
    return PartDef(mpn="OPTO", category="opto", footprint="Package_DIP:SMDIP-4_W9.53mm",
                   pins=[PinDef(1, "A", "passive"), PinDef(2, "K", "passive"), PinDef(3, "E", "passive"),
                         PinDef(4, "C", "passive")],
                   ratings=Ratings(isolation=[Isolation(("A", "K"), ("E", "C"), v_iso, grade=grade)]))


def run(d):
    return Checker(d).run()


def checks(findings, sev="error"):
    return sorted({f.check for f in findings if f.severity == sev and not f.waived_by})


def test_sexpr_round_trip():
    text = '(a "x y" (b 1 2.5) (c "q\\"uote") sym)'
    node = sexpr.loads(text)
    assert node[1] == "x y" and isinstance(node[-1], sexpr.Sym)
    assert sexpr.loads(sexpr.dumps(node)) == node


def stack(n=4, v=(10.5, 15.0)):
    """n batteries in series; each battery's domain floats on the previous positive."""
    d = Design("stack")
    d.net("GND", domain="B1", v=0, kind="ground")
    prev = "GND"
    for k in range(1, n + 1):
        if k > 1:
            d.domain(f"B{k}", ref=prev, kind="battery")
        else:
            d.domain("B1", ref="GND", kind="battery")
        d.net(f"T{k}", domain=f"B{k}", v=v, kind="power")
        prev = f"T{k}"
    return d


def test_stacked_domains_use_correlation():
    d = stack()
    ck = Checker(d.finalize())
    # adjacent taps: exactly one battery, not the loose interval difference
    assert ck.vdiff(d.nets["T3"], d.nets["T2"]) == (10.5, 15.0)
    assert ck.vdiff(d.nets["T4"], d.nets["GND"]) == (42.0, 60.0)
    assert ck.vdiff(d.nets["T4"], d.nets["T1"]) == (31.5, 45.0)


def test_voltage_rating_across_stack():
    d = stack()
    b = d.block("bal")
    r1 = b.add(two_pin("C16V", v_max=16, cat="capacitor_ceramic"))   # one battery: 94% of rating
    r2 = b.add(two_pin("R25V", v_max=25))       # across three batteries: 45 V > 25 V
    d.nets["T2"].connect(r1[1]); d.nets["T3"].connect(r1[2])
    d.nets["T1"].connect(r2[1]); d.nets["T4"].connect(r2[2])
    f = run(d)
    errs = [x for x in f if x.check == "rating.voltage" and x.severity == "error"]
    assert len(errs) == 1 and r2.ref in errs[0].objects
    warns = [x for x in f if x.check == "rating.voltage" and x.severity == "warning"]
    assert any(r1.ref in x.objects for x in warns)          # 15/16 = 94% > 80% capacitor derating


def isolated_design(part, grade="reinforced", v_test=3000):
    d = Design("iso")
    d.net("N", domain="MAINS", v=0, kind="mains")
    d.net("L", domain="MAINS", v=(-170, 170), kind="mains")
    d.net("GND", domain="SELV", v=0, kind="ground")
    d.net("IO", domain="SELV", v=(0, 3.3))
    d.domain("MAINS", ref="N", kind="mains")
    d.domain("SELV", ref="GND", kind="selv")
    d.barrier("MAINS", "SELV", grade=grade, v_work=170, creepage_mm=5.0, clearance_mm=3.0,
              standard="IEC 62368-1", v_test_rms=v_test)
    b = d.block("x")
    p = b.add(part)
    return d, b, p


def test_resistor_across_isolation_is_an_error():
    d, b, r = isolated_design(two_pin("R", v_max=1000))
    d.nets["L"].connect(r[1]); d.nets["IO"].connect(r[2])
    assert "domain.crossing" in checks(run(d))


def test_rated_optocoupler_crosses_barrier():
    d, b, u = isolated_design(opto())
    d.nets["L"].connect(u["A"]); d.nets["N"].connect(u["K"])
    d.nets["IO"].connect(u["C"]); d.nets["GND"].connect(u["E"])
    f = run(d)
    assert not {"domain.crossing", "barrier.grade", "barrier.withstand"} & set(checks(f))


def test_basic_optocoupler_fails_reinforced_barrier():
    d, b, u = isolated_design(opto(grade="basic", v_iso=2500))
    d.nets["L"].connect(u["A"]); d.nets["N"].connect(u["K"])
    d.nets["IO"].connect(u["C"]); d.nets["GND"].connect(u["E"])
    errs = checks(run(d))
    assert "barrier.grade" in errs and "barrier.withstand" in errs


def test_unconnected_and_single_pin():
    d = Design("conn")
    d.domain("D", ref="GND")
    d.net("GND", domain="D", v=0, kind="ground")
    b = d.block("x")
    r = b.add(two_pin("R"))
    d.nets["GND"].connect(r[1])
    errs = checks(run(d))
    assert "conn.unconnected_pin" in errs and "conn.single_pin_net" in errs


def test_waiver_and_calc_limit():
    d = Design("calc")
    d.domain("D", ref="GND")
    d.net("GND", domain="D", v=0, kind="ground")
    d.calc("Tj_Q1", 131.0, "C", expr="Ta + P*Rth", limit=125)
    f = run(d)
    assert "calc.limit" in checks(f)
    d2 = Design("calc2")
    d2.domain("D", ref="GND")
    d2.net("GND", domain="D", v=0, kind="ground")
    d2.calc("Tj_Q1", 131.0, "C", limit=125)
    d2.waive("calc.limit", "Tj_Q1", "short pulses only", by="reviewer")
    f2 = run(d2)
    assert "calc.limit" not in checks(f2) and any(x.waived_by for x in f2)


def test_double_connection_rejected():
    d = Design("dbl")
    d.domain("D", ref="GND")
    a, g = d.net("A", domain="D", v=1), d.net("GND", domain="D", v=0)
    b = d.block("x")
    r = b.add(two_pin("R"))
    a.connect(r[1])
    with pytest.raises(DesignError):
        g.connect(r[1])


def test_refdes_assignment_is_stable():
    d = Design("refs")
    for name in ("a", "b"):
        blk = d.block(name)
        blk.add(two_pin("R")); blk.add(two_pin("R"))
    d.blocks[0].add(two_pin("R"), ref="R1")
    d.finalize()
    refs = [p.ref for p in d.all_parts()]
    assert refs == ["R101", "R102", "R1", "R201", "R202"]


def test_duplicate_fixed_refdes_rejected():
    d = Design("dup")
    for name in ("a", "b"):
        d.block(name).add(two_pin("R"), ref="R1")
    with pytest.raises(DesignError):
        d.finalize()


def test_dru_lint():
    from kaesynth import dru
    good = "(version 1)\n(rule \"a\" (condition \"A.hasNetclass('X') && B.hasNetclass('Y')\")\n" \
           "  (constraint clearance (min 3mm)) (constraint creepage (min 5mm)))\n"
    assert dru.lint(good, {"X", "Y"}) == []
    bad = "(version 1)\n(rule \"a\" (condition \"A.hasNetclazz('X')\") (constraint creepage (min 5th))" \
          " (constraint bogus (min 1mm)) (constraint creepage (min 1mm)))\n"
    probs = " | ".join(dru.lint(bad, {"X"}))
    assert "hasNetclazz" in probs and "bogus" in probs and "twice" in probs and "'th'" in probs
