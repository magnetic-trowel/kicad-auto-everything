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


def mains_with_outputs():
    """Line is the root; neutral and a switched output float on it (as on a relay board)."""
    d = Design("nest")
    d.net("L", domain="LINE", v=0, kind="mains")
    d.domain("LINE", ref="L", kind="mains")
    d.domain("NEUTRAL", ref="L", kind="mains")
    d.domain("OUT1", ref="L", kind="mains")
    d.net("N", domain="NEUTRAL", v=(-170, 170), kind="mains")
    d.net("L_SW1", domain="OUT1", v=(-170, 170), kind="mains")
    d.net("GND", domain="SELV", v=0, kind="ground")
    d.domain("SELV", ref="GND")
    d.barrier("LINE", "OUT1", grade="functional", v_work=170, creepage_mm=2.5, clearance_mm=1.5)
    d.barrier("NEUTRAL", "OUT1", grade="functional", v_work=340, creepage_mm=6.4, clearance_mm=3.2)
    d.barrier("SELV", "LINE", grade="reinforced", v_work=170, creepage_mm=8, clearance_mm=8)
    return d


def test_dru_nested_domains_direct_rules_win():
    from kaesynth.emit.project import NetClasses, dru_text
    d = mains_with_outputs()
    b = d.block("x")
    for net in ("L", "N", "L_SW1", "GND"):
        r = b.add(two_pin("R", v_max=1000))
        d.nets[net].connect(r[1], r[2])
    d.finalize()
    text = dru_text(d, NetClasses(d).build())
    rules = [ln for ln in text.splitlines() if ln.startswith('(rule "')]
    # the LINE/OUT1 barrier inherited by NEUTRAL comes before the direct NEUTRAL/OUT1 rule
    assert rules.index('(rule "IR:barrier.LINE.OUT1.inherited"') < rules.index('(rule "IR:barrier.NEUTRAL.OUT1"')
    # the reinforced barrier reaches the floating domains (outputs, neutral) too
    inh = text.split('(rule "IR:barrier.SELV.LINE.inherited"')[1].split("(rule")[0]
    assert "hasNetclass('OUT1')" in inh and "hasNetclass('NEUTRAL')" in inh
    # a parent/child barrier never applies inside the child
    lo = text.split('(rule "IR:barrier.LINE.OUT1.inherited"')[1].split("(rule")[0]
    cond = lo.split("condition")[1].split("||")
    assert not any("A.hasNetclass('OUT1')" in c and "B.hasNetclass('OUT1')" in c for c in cond)


def test_relation_names_resolve():
    d = mains_with_outputs()
    d.place.separate("SELV", "LINE")
    d.place.custom("current_path", net="L_SW1", amps=15)
    d.place.custom("label", obj="board", text="DANGER")
    f = run(d)
    assert "place.unknown_object" not in checks(f, "warning") + checks(f)
    res = d.place.resolve()
    assert res[0]["a"] == "domain:SELV" and res[1]["net"] == "net:L_SW1"


def test_i_through_and_one_hop_protector():
    from kaesynth.lib import D, Fuse
    d = Design("prot")
    d.domain("D", ref="GND")
    d.net("GND", domain="D", v=0, kind="ground")
    vin = d.net("VIN", domain="D", v=(0, 5.5), kind="power", i_max=0.5, external=True,
                threats=("overvoltage", "overcurrent"))
    rail = d.net("RAIL", domain="D", v=(0, 5.5), kind="power", i_max=0.5)
    b = d.block("x")
    f = b.add(Fuse(0.75, 16, "Fuse:Fuse_1206_3216Metric", ptc=True, mpn="PTC"))
    tvs = b.add(D("SMAJ5.0A", "Diode_SMD:D_SMA", 5.0, 0.01, kind="D_TVS"), i_through=0.0)
    vin.connect(f[1]); rail.connect(f[2], tvs["K"]); d.nets["GND"].connect(tvs["A"])
    fl = run(d)
    assert "protect.threat" not in checks(fl)                      # TVS one PTC in, PTC on the wire
    assert not any(x.check == "rating.current" and tvs.ref in x.objects for x in fl)


def test_stack_spacing_is_per_domain_pair():
    from kaesynth.emit.project import NetClasses, dru_text
    d = stack(n=16, v=(2.5, 4.2))
    b = d.block("mon")
    # a monitor IC touching every tap: adjacent pins are one cell apart
    afe = b.add(PartDef(mpn="AFE", category="ic", footprint="Package_SO:SSOP-28_5.3x10.2mm_P0.65mm",
                        pins=[PinDef(k, f"C{k}") for k in range(17)]))
    d.nets["GND"].connect(afe[0])
    for k in range(1, 17):
        d.nets[f"T{k}"].connect(afe[k])
    for k in range(1, 17):          # a second pin per tap so no net is single-pin
        r = b.add(two_pin("R", v_max=100))
        d.nets[f"T{k}"].connect(r[1]); (d.nets["GND"] if k == 1 else d.nets[f"T{k - 1}"]).connect(r[2])
    d.finalize()
    nc = NetClasses(d).build()
    assert max(c["clearance"] for c in nc.classes.values()) == 0.2      # no 0.6 mm on the AFE pins
    text = dru_text(d, nc)
    assert "IR:functional.B1.0.6mm" in text                          # far ends of the stack: 60+ V
    assert "memberOfFootprint('U101')" in text                       # its own pads are exempt


def test_vlimit_recommended_and_directional():
    d = Design("vl")
    d.domain("D", ref="GND")
    d.net("GND", domain="D", v=0, kind="ground")
    vdd = d.net("VDD", domain="D", v=(3.2, 3.4), kind="power")
    g = d.net("G", domain="D", v=(-10, 12))
    b = d.block("x")
    ic = b.add(PartDef(mpn="MCU", category="ic", footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                       pins=[PinDef(1, "VDD", "power_in"), PinDef(2, "VSS", "power_in")],
                       ratings=Ratings(limits=[VLimit(("VDD",), ("VSS",), 4.0, v_rec=3.6)])))
    q = b.add(PartDef(mpn="FET", category="mosfet", footprint="Package_TO_SOT_SMD:SOT-23",
                      pins=[PinDef(1, "G"), PinDef(2, "S"), PinDef(3, "D")],
                      ratings=Ratings(limits=[VLimit(("G",), ("S",), 20, v_min=-8)])))
    vdd.connect(ic["VDD"]); d.nets["GND"].connect(ic["VSS"], q["S"], q["D"]); g.connect(q["G"])
    f = run(d)
    msgs = [x.message for x in f if x.check == "rating.voltage"]
    assert not any("MCU" in m for m in msgs)                       # 3.4 V within recommended 3.6 V
    assert any("FET" in m and "below its -8 V" in m for m in msgs)  # -10 V gate violates v_min


def test_notes_are_not_object_names():
    d = mains_with_outputs()
    d.place.custom("label", obj="board", text="see B-5", note="B-5")
    assert "place.unknown_object" not in checks(run(d), "warning")


def test_inherited_barriers_strictest_wins():
    """Repro from the lead-acid encoding: barriers (B1,B4,1.5 mm) then (B1,B2,0.6 mm); a domain
    floating on B1 is covered by both inherited rules and must keep 1.5 mm to B4."""
    from kaesynth.emit.project import NetClasses, dru_text
    d = stack(n=4)
    d.domain("X", ref="T1")
    d.net("XN", domain="X", v=(0, 5))
    d.barrier("B1", "B4", grade="functional", v_work=60, creepage_mm=1.5, clearance_mm=1.5)
    d.barrier("B1", "B2", grade="functional", v_work=15, creepage_mm=0.6, clearance_mm=0.6)
    b = d.block("x")
    for net in ("GND", "T1", "T2", "T3", "T4", "XN"):
        r = b.add(two_pin("R", v_max=100))
        d.nets[net].connect(r[1], r[2])
    d.finalize()
    text = dru_text(d, NetClasses(d).build())
    assert text.index('"IR:barrier.B1.B2.inherited"') < text.index('"IR:barrier.B1.B4.inherited"')


def test_functional_rule_not_skipped_by_netclass_clearance():
    """Repro from the Li-ion encoding: a looser inherited barrier must not beat IPC spacing
    just because a net class already had the IPC clearance."""
    from kaesynth.emit.project import NetClasses, dru_text
    d = stack(n=4)                       # T4 - GND up to 60 V
    d.domain("SW", ref="T2")
    d.net("SWN", domain="SW", v=(-30, 30))
    d.barrier("B1", "B2", grade="functional", v_work=15, creepage_mm=0.2, clearance_mm=0.2)
    b = d.block("x")
    for net in ("GND", "T1", "T2", "T3", "T4", "SWN"):
        r = b.add(two_pin("R", v_max=100))
        d.nets[net].connect(r[1], r[2])
    d.finalize()
    text = dru_text(d, NetClasses(d).build())
    i_inh = text.index('"IR:barrier.B1.B2.inherited"')
    fn = [ln for ln in text.splitlines() if ln.startswith('(rule "IR:functional.B1.') and "0.6mm" in ln]
    assert fn and text.index(fn[0]) > i_inh               # the 0.6 mm IPC rule comes after (wins)


def test_dc_barrier_needs_dc_working_rating():
    """Repro from the Prius encoding: a 600 Vrms-rated isolator passed an 820 V DC barrier."""
    def iso_part(**kw):
        return PartDef(mpn="ISO", category="ic", footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                       pins=[PinDef(1, "A"), PinDef(2, "B")],
                       ratings=Ratings(isolation=[Isolation(("A",), ("B",), 5000, grade="reinforced", **kw)]))
    for kw, bad in (({"v_work_rms": 600}, True), ({"v_work_rms": 600, "v_work_dc": 850}, False)):
        d = Design("dcbar")
        d.net("HVN", domain="HV", v=0); d.net("HVP", domain="HV", v=(0, 820))
        d.net("GND", domain="LV", v=0)
        d.domain("HV", ref="HVN"); d.domain("LV", ref="GND")
        d.barrier("HV", "LV", grade="reinforced", v_work=820, creepage_mm=10, clearance_mm=8)
        u = d.block("x").add(iso_part(**kw))
        d.nets["HVP"].connect(u["A"]); d.nets["GND"].connect(u["B"])
        for net in ("HVP", "GND"):
            pass
        assert ("barrier.working_voltage" in checks(run(d))) is bad


def test_unused_waiver_reported():
    d = Design("uw")
    d.domain("D", ref="GND")
    d.net("GND", domain="D", v=0, kind="ground")
    d.waive("rating.voltage", "NOTHING", "stale")
    ck = Checker(d)
    ck.run()
    ck.apply_waivers(final=True)
    assert any(f.check == "waiver.unused" for f in ck.findings)


def test_fuse_does_not_protect_loads_ahead_of_it():
    """Repro from the relay board: a supply fuse on the line input made the whole input look fused."""
    from kaesynth.lib import Fuse
    d = Design("ahead")
    d.domain("M", ref="N")
    d.net("N", domain="M", v=0, kind="mains")
    lin = d.net("L_IN", domain="M", v=(-170, 170), kind="mains", i_max=10, external=True, threats=("overcurrent",))
    lps = d.net("L_PSU", domain="M", v=(-170, 170), kind="mains", i_max=0.2)
    b = d.block("x")
    f = b.add(Fuse(1, 250, "Fuse:Fuse_1206_3216Metric", mpn="F1A"))
    k = b.add(two_pin("CONTACT", v_max=400, cat="relay"))
    load = b.add(two_pin("PSU", v_max=400))
    lin.connect(f[1], k[1]); lps.connect(f[2], load[1]); d.nets["N"].connect(k[2], load[2])
    errs = [x for x in run(d) if x.check == "protect.threat" and x.severity == "error"]
    assert errs and k.ref in errs[0].message


def test_fixed_position_needs_source():
    d = Design("fx")
    with pytest.raises(DesignError):
        d.place.fixed("J1", 10, 10)
