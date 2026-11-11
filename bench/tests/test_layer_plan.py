# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which copper layers a task may use (kicad_scripts/layer_plan.py); no KiCad needed."""
import pytest

from kaebench.kicad_scripts import layer_plan as lp


def use(n=4, inner=(), routing=10, zones=0, stackup=True, named=()):
    return dict(copper_layers=n, inner_used=[f"In{i}.Cu" for i in inner], routing_items=routing, copper_zones=zones,
                has_stackup=stackup, named_inner=list(named))


# (a) what can be inferred
def test_eagle_16_default_is_two_layers_even_without_copper():
    p = lp.plan(use(16, routing=0, stackup=False), unconnected=None)
    assert p == dict(declared=16, used=2, copper_layers=2, forbidden=[], reason="eagle-16-default")


def test_incomplete_or_empty_boards_keep_their_declaration():
    assert lp.plan(use(4, routing=0), unconnected=0) is None  # no copper: 0 unconnected says nothing
    assert lp.plan(use(4), unconnected=3) is None             # incomplete: inner layers may be planned
    assert lp.plan(use(4), unconnected=None) is None          # not known
    assert lp.plan(use(16, routing=0, stackup=True), unconnected=0) is None  # a stackup: not the default
    assert lp.plan(use(16, routing=0, stackup=False, named=["In3.Cu"]), unconnected=0) is None


def test_complete_copper_decides():
    p = lp.plan(use(4), unconnected=0)
    assert (p["copper_layers"], p["forbidden"], p["reason"]) == (2, [], "complete-human-copper")
    assert lp.plan(use(16, routing=50, stackup=True), unconnected=0)["copper_layers"] == 2


def test_nearly_complete_copper_is_evidence_too():
    p = lp.plan(use(4, routing=1000), unconnected=1)
    assert (p["copper_layers"], p["reason"]) == (2, "near-complete-human-copper")
    assert lp.plan(use(4, routing=100), unconnected=20) is None  # a sixth open


def test_two_layer_and_fully_used_boards_do_not_change():
    assert lp.plan(use(2), unconnected=0) is None
    assert lp.plan(use(4, inner=(1, 2)), unconnected=0) is None
    assert lp.plan(use(6, inner=(1, 2, 3, 4)), unconnected=0) is None


# (b) even stacks; no renumbering
@pytest.mark.parametrize("n,inner,count,forbidden", [
    (4, (1,), 4, ["In2.Cu"]),                  # 4->3
    (4, (2,), 4, ["In1.Cu"]),
    (8, (1, 2, 3, 4, 5), 8, ["In6.Cu"]),       # 8->7
    (6, (1,), 4, ["In2.Cu"]),                  # 6->3: cut to 4, one still forbidden
    (6, (1, 2), 4, []),                        # 6->4, the two kept are the first two
    (6, (1, 4), 6, ["In2.Cu", "In3.Cu"]),      # names cannot move: nothing can be cut
    (8, (1, 2, 3, 4), 6, []),
    (11, (1,), 4, ["In2.Cu"]),
])
def test_stack_stays_even_and_names_stay(n, inner, count, forbidden):
    p = lp.plan(use(n, inner=inner), unconnected=0)
    assert (p["copper_layers"], p["forbidden"]) == (count, forbidden)
    assert p["copper_layers"] % 2 == 0


def test_odd_declaration_is_not_extended():
    assert lp.plan(use(11, inner=range(1, 10)), unconnected=0) is None
    p = lp.plan(use(11, inner=(1, 2, 3, 4, 5, 6, 7, 9)), unconnected=0)
    assert (p["copper_layers"], p["forbidden"]) == (11, ["In8.Cu"])


def test_rules_naming_a_layer_keep_it():
    p = lp.plan(use(6), '(rule x (layer "In3.Cu") (constraint clearance (min 1mm)))', unconnected=0)
    assert p["copper_layers"] == 6 and p["forbidden"] == ["In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"]


def test_needs_completeness():
    assert not lp.needs_completeness(use(2))
    assert not lp.needs_completeness(use(4, inner=(1, 2)))
    assert not lp.needs_completeness(use(16, stackup=False))
    assert lp.needs_completeness(use(16, stackup=True))
    assert lp.needs_completeness(use(4))


# (d) stackup block
STACK = '''(setup
\t\t(stackup
\t\t\t(layer "F.Mask"
\t\t\t\t(type "Top Solder Mask")
\t\t\t\t(thickness 0.01)
\t\t\t)
\t\t\t(layer "F.Cu"
\t\t\t\t(type "copper")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer "dielectric 1"
\t\t\t\t(type "prepreg")
\t\t\t\t(thickness 0.1)
\t\t\t\t(material "A")
\t\t\t)
\t\t\t(layer "In1.Cu"
\t\t\t\t(type "copper")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer "dielectric 2"
\t\t\t\t(type "core")
\t\t\t\t(thickness 1.24)
\t\t\t\t(material "B")
\t\t\t)
\t\t\t(layer "In2.Cu"
\t\t\t\t(type "copper")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer "dielectric 3"
\t\t\t\t(type "prepreg")
\t\t\t\t(thickness 0.1)
\t\t\t\t(material "A")
\t\t\t\taddsublayer
\t\t\t\t(thickness 0.05)
\t\t\t\t(material "C")
\t\t\t)
\t\t\t(layer "B.Cu"
\t\t\t\t(type "copper")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(copper_finish "None")
\t\t)
\t)
'''


def _total(text):
    import re
    return round(sum(float(x) for x in re.findall(r"\(thickness ([\d.]+)", text)), 6)


def test_stackup_merge_keeps_total_thickness():
    out = lp.merge_stackup(STACK, 2)
    assert _total(out) == _total(STACK)
    assert "In1.Cu" not in out and "In2.Cu" not in out
    assert 'dielectric 1"' in out and "dielectric 2" not in out
    assert '(material "B")' in out and "addsublayer" not in out  # the thickest's material
    assert out.count("(layer") == 4  # mask, F, one dielectric, B
    assert "(copper_finish" in out


def test_stackup_cut_keeps_upper_layers():
    text = STACK
    out = lp.merge_stackup(text, 2)
    assert lp.merge_stackup(text.replace("(stackup", "(stack"), 2) == text.replace("(stackup", "(stack")  # no block
    assert out.index("F.Cu") < out.index("B.Cu")


def test_stackup_four_of_six_keeps_inner_dielectrics():
    six = STACK.replace('"In2.Cu"', '"In4.Cu"').replace('"dielectric 3"', '"dielectric 5"')
    head, tail = six.split('\t\t\t(layer "In4.Cu"')
    six = (head + '\t\t\t(layer "In2.Cu"\n\t\t\t\t(type "copper")\n\t\t\t\t(thickness 0.035)\n\t\t\t)\n'
           '\t\t\t(layer "dielectric 3"\n\t\t\t\t(type "prepreg")\n\t\t\t\t(thickness 0.2)\n\t\t\t\t(material "D")\n\t\t\t)\n'
           '\t\t\t(layer "In3.Cu"\n\t\t\t\t(type "copper")\n\t\t\t\t(thickness 0.035)\n\t\t\t)\n'
           '\t\t\t(layer "dielectric 4"\n\t\t\t\t(type "core")\n\t\t\t\t(thickness 0.3)\n\t\t\t\t(material "D")\n\t\t\t)\n'
           '\t\t\t(layer "In4.Cu"' + tail)
    out = lp.merge_stackup(six, 4)
    assert _total(out) == _total(six)
    assert "In3.Cu" not in out and "In4.Cu" not in out and "In2.Cu" in out
    assert '"dielectric 3"' in out and '"dielectric 4"' not in out
