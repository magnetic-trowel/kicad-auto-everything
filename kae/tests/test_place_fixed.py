# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.place.fixed: the benchmark's place-fixed rules (mech_rules), vendored, on kae's model."""
import json
import subprocess
from pathlib import Path

import pytest

from kae.board.kicad_file import load
from kae.place import fixed, mech_rules

ROOT = Path(__file__).resolve().parents[2]
BENCH_RULES = ROOT / "bench" / "src" / "kaebench" / "kicad_scripts" / "mech_rules.py"
BENCH_OPS = BENCH_RULES.parent / "pcbnew_ops.py"
FIXTURE = Path(__file__).parent / "data" / "board" / "fixture.kicad_pcb"


def test_vendored_rules_are_the_benchmarks():
    """kae.place.mech_rules is a copy of the harness's rules: update both together."""
    if not BENCH_RULES.exists():
        pytest.skip("no bench/ checkout beside kae")
    assert (Path(mech_rules.__file__).read_text() == BENCH_RULES.read_text()), \
        "kae/src/kae/place/mech_rules.py differs from bench/.../mech_rules.py: copy it over"


def test_rows_follow_pcbnew_ops_and_classes_are_kae_names():
    b = load(FIXTURE)
    got = fixed.classify(b)
    assert got and {c["cls"] for c in got.values()} <= set(fixed.CLASSES)
    for f in b.footprints:
        r = fixed.mech_row(f)
        assert r["pads"] >= r["pth"] + r["npth"] + r["smd"]
        assert (r["lib"] + ":" + r["name"]) == f.lib_id or r["name"] == f.lib_id


def test_same_classes_as_the_harness_on_the_fixture():
    """Where KiCad's Python and the harness's pcbnew_ops are here, both classify alike."""
    from kae.board import pcbnew_io
    if not BENCH_OPS.exists() or not pcbnew_io.available():
        pytest.skip("no pcbnew or no bench/ checkout")
    py = pcbnew_io.kicad_python()
    r = subprocess.run([*py, str(BENCH_OPS), "classify-mech", str(FIXTURE)], capture_output=True, text=True,
                       timeout=300)
    rows = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1])["footprints"]
    harness = {x["uuid"]: x["class"] for x in rows}
    ours = {u: c["rule_class"] for u, c in fixed.classify(load(FIXTURE)).items()}
    assert {u: c for u, c in harness.items() if c} == ours
