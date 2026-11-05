# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.board.dru_check against KiCad's own verdicts, and drift tests for KiCad updates.

Each case's `kicad_loads` was measured on KiCad 10.0.7 with kae.board.dru_check.kicad_check
(sentinel rule on a probe board; KiCad drops the whole file on any parse error, without a
message). The static pass (vocabulary 10.0) must flag an error exactly when KiCad rejects.

Drift tests (need kicad-cli; run them after every KiCad bump):
- test_installed_kicad_has_vocabulary: a vocabulary exists for the installed major.minor
- test_kicad_verdicts_unchanged: the installed KiCad still gives every case's verdict
- test_vocabulary_still_accepted: every function and property of that vocabulary still loads
When one fails: `python -m kae.board.dru_vocab fetch <tag>`, then `sync <src> <major.minor>
--verify`, re-measure the changed cases, and update the docs (drc-rule-language-reference).
"""
import os

import pytest

from kae.board import dru_check, dru_vocab

MEASURED_ON = "10.0.7"
VOCAB = "10.0"

CASES = [
    ('ok', '(version 1)\n(rule "u" (constraint track_width (min 0.1mm)))', True),
    ('semicolon', '(version 1)\n(rule "u" (constraint track_width (min 0.1mm))) ; c', False),
    ('hashline', '(version 1)\n# c\n(rule "u" (constraint track_width (min 0.1mm)))', True),
    ('midhash', '(version 1)\n(rule "u" (constraint track_width (min 0.1mm))) # c', False),
    ('badconstraint', '(version 1)\n(rule "u" (constraint clearence (min 1mm)))', False),
    ('badexpr', '(version 1)\n(rule "u" (condition "A.NetName == ") (constraint clearance (min 1mm)))', False),
    ('badfunc', '(version 1)\n(rule "u" (condition "A.hasNetklass(\'X\')") (constraint clearance (min 1mm)))', False),
    ('badprop', '(version 1)\n(rule "u" (condition "A.NetNme == \'X\'") (constraint clearance (min 1mm)))', False),
    ('spaceunit', '(version 1)\n(rule "u" (constraint clearance (min 1 mm)))', True),
    ('badlayer', '(version 1)\n(rule "u" (layer "F.Cuu") (constraint clearance (min 1mm)))', False),
    ('missingparen', '(version 1)\n(rule "u" (constraint clearance (min 1mm))', False),
    ('badseverity', '(version 1)\n(rule "u" (severity warn) (constraint clearance (min 1mm)))', False),
    ('badoption', '(version 1)\n(rule "u" (constraint skew (max 1mm) (within_diff_pair)))', False),
    ('master_only', '(version 1)\n(rule "u" (constraint microvia_stack_depth (max 2)))', False),
    ('noversion', '(rule "u" (constraint track_width (min 0.1mm)))', False),
    ('time_in_clear', '(version 1)\n(rule "u" (constraint clearance (min 10ps)))', False),
    ('th_unit', '(version 1)\n(rule "u" (constraint clearance (min 10th)))', False),
    ('dup_constraint', '(version 1)\n(rule "u" (constraint clearance (min 1mm)) (constraint clearance (min 2mm)))', False),
    ('two_layers', '(version 1)\n(rule "u" (layer "F.Cu") (layer "B.Cu") (constraint clearance (min 1mm)))', False),
    ('truelit', '(version 1)\n(rule "u" (condition "A.Locked == true") (constraint clearance (min 1mm)))', False),
    ('andword', '(version 1)\n(rule "u" (condition "A.Locked and B.Locked") (constraint clearance (min 1mm)))', False),
    ('undocprop', '(version 1)\n(rule "u" (condition "A.Hole_Shape == \'x\'") (constraint clearance (min 1mm)))', True),
    ('deprecated', '(version 1)\n(rule "u" (constraint mechanical_clearance (min 1mm)))', True),
    ('disallow_bad', '(version 1)\n(rule "u" (constraint disallow trackz))', False),
    ('zone_bad', '(version 1)\n(rule "u" (constraint zone_connection thermal))', False),
    ('spokes', '(version 1)\n(rule "u" (constraint min_resolved_spokes 2))', True),
    ('assertion', '(version 1)\n(rule "u" (constraint assertion "A.Orientation == 0deg"))', True),
    ('bare_num', '(version 1)\n(rule "u" (constraint clearance (min 100000)))', False),
    ('lay_courtyard', '(version 1)\n(rule "u" (layer "F.Courtyard") (constraint clearance (min 1mm)))', True),
    ('lay_unquoted', '(version 1)\n(rule "u" (layer F.Cu) (constraint clearance (min 1mm)))', True),
    ('docexamples', '(version 1)\n(rule "DDR_CLK len" (condition "A.fromTo(\'U1-C5\',\'U2-D3\')") (constraint length (min 20mm) (max 25mm)))\n(rule "USB delay"   (condition "A.inDiffPair(\'/USB\')") (constraint length (max 500ps)))\n(rule "DQ skew"     (condition "A.fromTo(\'U1-A*\',\'U2-B*\')") (constraint skew (max 0.2mm)))\n(rule "USB intra"   (condition "A.inDiffPair(\'/USB*\')") (constraint skew (max 5ps) (within_diff_pairs)))\n(rule "Clock gap"   (condition "A.inDiffPair(\'/CLK\')") (constraint diff_pair_gap (min 0.12mm) (opt 0.15mm) (max 0.2mm)) (constraint diff_pair_uncoupled (max 3mm)))\n(rule "DP clearance" (condition "A.inDiffPair(\'*\') && !AB.isCoupledDiffPair()") (constraint clearance (min 1.5mm)))\n(rule "HS vias"     (condition "A.hasNetclass(\'HS\')") (constraint via_count (max 2)))\n(rule front_courtyard_to_edge (layer "F.Courtyard") (condition "B.Layer == \'Edge.Cuts\'") (constraint physical_clearance (min 3mm)))\n(rule "TP spacing"  (condition "A.Reference == \'TP*\' && B.Reference == \'TP*\'") (constraint courtyard_clearance (min 1.5mm)))\n', True),
    ('new2', '(version 1)\n(rule "IR:USB2-SKEW:intra"\n  (condition "A.hasNetclass(\'USB2\')")\n  (constraint skew (max 1.27mm) (within_diff_pairs)))\n(rule "IR:PWR-05:sens-sw"\n  (severity warning)\n  (condition "A.hasNetclass(\'SENSITIVE\') && B.hasNetclass(\'SW\')")\n  (constraint clearance (min 1mm)))   ; soft default, buck.md rule 4', False),
    ('mixed_ops', '(version 1)\n(rule "u" (condition "A.NetName == \'X\' || A.NetName == \'Y\' && B.NetName == \'Z\'") (constraint clearance (min 1mm)))', True),
    ('multi_good_bad', '(version 1)\n(rule "a" (constraint track_width (min 0.1mm)))\n(rule "b" (constraint clearence (min 1mm)))\n(rule "c" (constraint via_count (max 2)))', False),
    ('dangling_and', '(version 1)\n(rule "u" (condition "A.Locked &&") (constraint clearance (min 1mm)))', False),
    ('two_operands', '(version 1)\n(rule "u" (condition "A.Locked B.Locked") (constraint clearance (min 1mm)))', False),
    ('not_eq', '(version 1)\n(rule "u" (condition "!A.Locked && A.NetName != \'X\'") (constraint clearance (min 1mm)))', True),
    ('neg_val', '(version 1)\n(rule "u" (condition "A.Position_X > -5mm") (constraint clearance (min 1mm)))', True),
    ('fromto', '(version 1)\n(rule "u" (condition "A.fromTo(\'U1-C5\', \'U2-D3\')") (constraint length (max 20mm)))', True),
    ('pair_fn', '(version 1)\n(rule "u" (condition "A.inDiffPair(\'*\') && !AB.isCoupledDiffPair()") (constraint clearance (min 1.5mm)))', True),
    ('unknownprop_far', '(version 1)\n(rule "u" (condition "A.Zork == \'x\'") (constraint clearance (min 1mm)))', False),
    ('getfield', '(version 1)\n(rule "u" (condition "A.getField(\'Sim.Device\') == \'R\'") (constraint clearance (min 1mm)))', True),
    ('type_pad', '(version 1)\n(rule "u" (condition "A.Type == \'Pad\' && B.Type == \'Via\'") (constraint hole_clearance (min 0.3mm)))', True),
    # real-world forms from the board corpus, KiCad 10.0.7 verdicts
    ("chained_prop", "(version 1)\n(rule \"u\" (condition \"A.Parent.Reference == 'J1'\") (constraint edge_clearance (min 0mm)))", False),
    ("parent_alone", "(version 1)\n(rule \"u\" (condition \"A.Parent == 'J1'\") (constraint edge_clearance (min 0mm)))", True),
    ("unterminated_sq", "(version 1)\n(rule \"u\" (condition \"A.NetClass == 'Diff\") (constraint clearance (min 1mm)))", True),
    ("wildcard_layer", '(version 1)\n(rule "u" (layer "?.Silkscreen") (constraint silk_clearance (min 0.1mm)))', True),
    ("no_values", '(version 1)\n(rule "u" (constraint courtyard_clearance) (severity ignore))', True),
    ("decimal_comma", '(version 1)\n(rule "u" (constraint length (min 31,1794mm) (max 31,1796mm)))', True),
    ("bare_L", "(version 1)\n(rule \"u\" (constraint silk_clearance (min 0.1mm)) (condition \"L == 'F.Mask' || L == 'B.Mask'\"))", True),
    ("repeated_opt", '(version 1)\n(rule "u" (constraint length (min 233.7ps)(opt 235ps)(opt 235.3ps)))', True),
]
STATIC_WARN_ONLY: set = set()


@pytest.mark.parametrize("name,text,kicad_loads", CASES, ids=[c[0] for c in CASES])
def test_static_matches_kicad(name, text, kicad_loads):
    issues = dru_check.static_check(text, VOCAB)
    errors = [i for i in issues if i.severity == "error"]
    if name in STATIC_WARN_ONLY:
        assert not errors and any(i.severity == "warning" for i in issues)
    else:
        assert (not errors) == kicad_loads, [str(i) for i in issues]


def test_semicolon_points_at_the_comment():
    text = '(version 1)\n(rule "a"\n  (constraint clearance (min 1mm)))   ; soft\n'
    (err,) = [i for i in dru_check.static_check(text) if i.severity == "error"]
    assert (err.line, err.col) == (3, 39) and "#" in err.message


def test_precedence_warning():
    text = "(version 1)\n(rule \"a\" (condition \"A.Locked || B.Locked && A.Locked\") (constraint clearance (min 1mm)))"
    assert any("parentheses" in i.message for i in dru_check.static_check(text))


def test_rule_spans():
    text = '(version 1)\n# x (rule "no")\n(rule "a" (constraint clearance (min 1mm)))\n(rule b (constraint via_count (max 2)))\n'
    assert [(n, l) for n, l, _ in dru_check.rule_spans(text)] == [("a", 3), ("b", 4)]


def _cli():
    try:
        from kae.route.drc import kicad_cli
        return kicad_cli()
    except Exception:
        return None


def test_vocabulary_consistent():
    v = dru_vocab.load(VOCAB)
    assert set(dru_check.FORMS) <= set(v["constraints"])
    import re
    assert set(re.split(r",\s*(?:or\s+)?", v["units_message"])) == dru_check.UNITS
    assert v["source_ref"] == v["verified_with"] == MEASURED_ON


def test_value_property_hint():
    text = "(version 1)\n(rule \"a\" (condition \"A.Value == '10k'\") (constraint clearance (min 1mm)))"
    assert any("getField('Value')" in i.message for i in dru_check.static_check(text, VOCAB))


@pytest.mark.skipif(not os.environ.get("KAE_KICAD_SRC"), reason="set KAE_KICAD_SRC to a KiCad checkout")
def test_vocabulary_matches_source():
    """KAE_KICAD_SRC=<checkout of the vocabulary's tag>: the committed file is what sync makes."""
    old = dru_vocab.load(VOCAB)
    new = dru_vocab.extract(os.environ["KAE_KICAD_SRC"])
    for k, rej in old.get("rejected", {}).items():
        new[k] = [n for n in new[k] if n not in rej]
    assert dru_vocab.diff(old, new) == []


needs_kicad = pytest.mark.skipif(_cli() is None, reason="kicad-cli not found")


@needs_kicad
def test_installed_kicad_has_vocabulary():
    ver = dru_check.kicad_version(_cli())
    assert dru_check.vocab_for(ver), (f"no dru vocabulary for KiCad {ver}: run python -m kae.board.dru_vocab "
                                      f"fetch {ver}; ... sync <src> <major.minor> --verify")


@needs_kicad
def test_kicad_verdicts_unchanged():
    import concurrent.futures
    cli = _cli()
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        got = list(ex.map(lambda c: dru_check.kicad_check(c[1], cli, workers=1).accepted, CASES))
    changed = [(c[0], c[2], g) for c, g in zip(CASES, got) if c[2] != g]
    assert not changed, (f"KiCad {dru_check.kicad_version(cli)} changed verdicts vs {MEASURED_ON} "
                         f"(case, was, now): {changed}")


@needs_kicad
def test_vocabulary_still_accepted():
    cli = _cli()
    label = dru_check.vocab_for(dru_check.kicad_version(cli)) or VOCAB
    v = dru_vocab.load(label)
    again = dru_vocab.verify(v, cli)
    lost = {k: sorted(set(v[k]) - set(again[k])) for k in ("functions", "deprecated_functions", "properties")}
    assert not any(lost.values()), f"KiCad no longer accepts: {lost}"


@needs_kicad
def test_kicad_pass_finds_culprit():
    good = dru_check.kicad_check(dict((c[0], c[1]) for c in CASES)["ok"], _cli())
    assert good.accepted
    bad = dru_check.kicad_check(dict((c[0], c[1]) for c in CASES)["multi_good_bad"], _cli())
    assert not bad.accepted and bad.culprits == [("b", 3)]
    semi = dru_check.kicad_check(dict((c[0], c[1]) for c in CASES)["semicolon"], _cli())
    assert not semi.accepted and semi.outside_rules
