# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board's mechanical interface: parts that keep their given pose while the rest is placed.

The rules are the benchmark's place-fixed rules (bench/src/kaebench/kicad_scripts/
mech_rules.py), vendored unchanged as kae.place.mech_rules so that `kae place --fix-class`
fixes exactly the parts a place-fixed task locks (kae does not import kaebench; the test
test_place_fixed checks the copy is identical and that both classify the suite alike). See
mech_rules' docstring for the rules: connectors, mounting (holes, standoffs, fiducials,
all-NPTH footprints) and user parts (switches and key switches, buttons, panel pots and
encoders, displays, THT / light-pipe / bar LEDs, buzzers); test points, jumpers, batteries,
trimmers, IC sockets, SMD LEDs and programming / debug headers stay free.

    classify(board) -> {uuid: dict(ref, cls, rule_class, why)}   (fixed parts only)

Classes here are named as the kae place option takes them: connectors, mounting, user
(mech_rules: connector, mounting, user). The row mech_rules reads is built from kae's board
model as pcbnew_ops._mech_row builds it from pcbnew: library nickname and footprint name,
value, the footprint's library description, its pads' nets, pad count and PTH / NPTH / SMD
counts.
"""
from . import mech_rules

CLASSES = ("connectors", "mounting", "user")
_TO_KAE = {"connector": "connectors", "mounting": "mounting", "user": "user"}


def mech_row(fp):
    """The footprint as mech_rules reads it (pcbnew_ops._mech_row's fields)."""
    lib, _, name = fp.lib_id.partition(":") if ":" in fp.lib_id else ("", "", fp.lib_id)
    kinds = [pd.kind for pd in fp.pads]
    return dict(uuid=fp.uuid, ref=fp.ref, lib=lib, name=name, value=fp.value,
                desc=(fp.fields or {}).get("Footprint_descr", ""),
                nets=sorted({pd.net for pd in fp.pads} - {""}), pads=len(fp.pads),
                pth=sum(k == "thru_hole" for k in kinds), npth=sum(k == "np_thru_hole" for k in kinds),
                smd=sum(k in ("smd", "connect") for k in kinds))


def classify(board, with_free=False):
    """{uuid: dict(ref, cls, rule_class, why)} for the fixed parts (mech_rules.classify);
    with_free also returns {uuid: dict(ref, why)} for the parts a rule explicitly frees
    (evidence 'exclude: ...': test points, jumpers, trimmers, programming / debug headers ...)."""
    out, free = {}, {}
    for fp in board.footprints:
        row = mech_row(fp)
        cls, why = mech_rules.classify(row)
        if cls is not None:
            out[fp.uuid] = dict(ref=fp.ref, cls=_TO_KAE[cls], rule_class=cls, why=why, lib_id=fp.lib_id,
                                value=fp.value, pads=row["pads"])
        elif why.startswith("exclude"):
            free[fp.uuid] = dict(ref=fp.ref, why=why, lib_id=fp.lib_id, value=fp.value)
    return (out, free) if with_free else out


def fixed_uuids(board, classes=(), refs=()):
    """uuids of the footprints held fixed: those of `classes` (classify) and those named by
    `refs`. Unknown class names or references raise ValueError."""
    bad = [c for c in classes if c not in CLASSES]
    if bad:
        raise ValueError(f"unknown fix classes {bad} (known: {', '.join(CLASSES)})")
    out = set()
    if classes:
        out |= {u for u, c in classify(board).items() if c["cls"] in classes}
    by_ref = {}
    for f in board.footprints:
        by_ref.setdefault(f.ref, []).append(f.uuid)
    missing = [r for r in refs if r not in by_ref]
    if missing:
        raise ValueError(f"--fix names unknown references {missing[:8]}")
    for r in refs:
        out |= set(by_ref[r])
    return out
