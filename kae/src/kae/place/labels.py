# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board-level silk labels and the parts they name.

A place task keeps the board's own silkscreen texts (gr_text on F/B.SilkS) where the
designer put them; the footprints move. A label beside a connector pin ("SDA", "GND"), an
LED ("PWR", "ACT") or a switch ("ON/OFF", "RESET") is useless when its part lands elsewhere
(noisecard: D1-D10 away from their printed "dB" levels). `infer(board)` names each label's
part from the task input alone; `LabelTerm` prices the distance from each part to its label
(and the order along a row of labels) as a soft placement term. It is off by default
(tools/research/place/labels.py validates the inference on the human placements).

Inference, per label (its tokens: split on blanks, '|', '/', ','; ~{X} and leading '+' are
normalized away, case-insensitive):
  ref      a token is a part's reference.
  pin      a token is the pin function or the net (last path component) of a pad of a
           connector-like part (J, P, CN, CON, X, TP references): those pads.
  keyword  a token of 3+ characters is in the net names of an LED's or a switch's pads; ON
           and OFF name the switches when there are at most two.
  row      k >= 3 labels on one side in a row or column (same y or x within 0.3 mm), not named
           otherwise, and exactly one family of k parts with one reference prefix and
           consecutive numbers none of which is named otherwise: matched in order along the
           row, in either direction (two candidates: 'row<g>:asc' and 'row<g>:desc').
"""
from __future__ import annotations

import re
from pathlib import Path

import shapely

SPLIT = re.compile(r"[\s|/,;:]+")
CONN = re.compile(r"^(J|P|CN|CON|X|TP|H|JP)\d+$", re.I)
LED = re.compile(r"^(D|LED|LD)\d+$", re.I)
SWITCH = re.compile(r"^(SW|S|BTN|K)\d+$", re.I)
REFNUM = re.compile(r"^([A-Za-z_]+)(\d+)$")
ROW_TOL = 0.3     # mm: labels within this of one y (or x) are a row (column)


def norm(tok):
    """KiCad text markup and net naming normalized: '~{RST}' -> 'RST', '+3V3' -> '3V3',
    '/power/VCC' -> 'VCC', case folded."""
    t = tok.strip()
    t = re.sub(r"[~_^]\{([^}]*)\}", r"\1", t)
    t = t.rsplit("/", 1)[-1]
    t = t.strip("()[]<>*!?.:'\"")
    if t.startswith("+") and len(t) > 1:
        t = t[1:]
    return t.upper()


def tokens(text):
    out = []
    for raw in SPLIT.split(text.replace("\\n", "\n")):
        t = norm(raw)
        if t:
            out.append(t)
    return out


def board_labels(board):
    """Board-level silkscreen texts of a board (kae.board Board or a path): [{text, tokens,
    side (0 F, 1 B), geom (estimated box), xy}]."""
    from kae.board import sexpr
    from kae.board.kicad_file import _text_box, load
    if not hasattr(board, "footprints"):
        board = load(board)
    path = getattr(board, "path", "")
    if not path or not Path(path).exists():
        return []
    tree = sexpr.parse(sexpr.strip_blocks(Path(path).read_text(encoding="utf-8", errors="replace")))
    out = []
    for n in tree:
        if type(n) is not list or not n or n[0] != "gr_text":
            continue
        ly = sexpr.value(n, "layer")
        if ly not in ("F.SilkS", "B.SilkS"):
            continue
        txt = n[1] if len(n) > 1 and type(n[1]) is str else ""
        g = _text_box(n)
        if not txt or g is None:
            continue
        c = g.centroid
        out.append(dict(text=txt, tokens=tokens(txt), side=0 if ly == "F.SilkS" else 1, geom=g, xy=(c.x, c.y)))
    return out


def _pad_names(fp):
    """{normalized name: [pad index]} from pin functions and net names."""
    out = {}
    for k, pd in enumerate(fp.pads):
        for name in (getattr(pd, "pinfunction", "") or "", pd.net or ""):
            t = norm(name)
            if t:
                out.setdefault(t, []).append(k)
    return out


def infer(board, labels=None):
    """[{label (index), how, part (uuid), pads (indices or None)}]: what each label names."""
    labels = board_labels(board) if labels is None else labels
    fps = [f for f in board.footprints if f.pads]
    by_ref = {}
    for f in fps:
        by_ref.setdefault(norm(f.ref), []).append(f)
    conns = [f for f in fps if CONN.match(f.ref or "")]
    leds = [f for f in fps if LED.match(f.ref or "")]
    switches = [f for f in fps if SWITCH.match(f.ref or "")]
    names = {f.uuid: _pad_names(f) for f in conns}
    out = []
    named = set()
    labelled = set()
    for li, lab in enumerate(labels):
        for t in lab["tokens"]:
            if t in by_ref and len(by_ref[t]) == 1:
                out.append(dict(label=li, how="ref", part=by_ref[t][0].uuid, pads=None))
                named.add(by_ref[t][0].uuid)
                labelled.add(li)
                continue
            for f in conns:
                ks = names[f.uuid].get(t)
                if ks:
                    out.append(dict(label=li, how="pin", part=f.uuid, pads=sorted(set(ks))))
                    labelled.add(li)
            if len(t) >= 3:
                for f in leds + switches:
                    if any(t in norm(pd.net or "") for pd in f.pads if pd.net):
                        out.append(dict(label=li, how="keyword", part=f.uuid, pads=None))
                        named.add(f.uuid)
                        labelled.add(li)
            if t in ("ON", "OFF") and 0 < len(switches) <= 2:
                for f in switches:
                    out.append(dict(label=li, how="keyword", part=f.uuid, pads=None))
                    named.add(f.uuid)
                    labelled.add(li)
    out += _rows(fps, labels, named, labelled)
    return out


def _rows(fps, labels, named, labelled):
    """Rows (columns) of unnamed labels matched in order to the one family of as many
    unnamed parts with consecutive reference numbers."""
    fam = {}
    for f in fps:
        m = REFNUM.match(f.ref or "")
        if m and f.uuid not in named:
            fam.setdefault(m.group(1).upper(), []).append((int(m.group(2)), f))
    fams = {}
    for p, items in fam.items():
        items.sort(key=lambda t: t[0])
        nums = [n for n, _ in items]
        if nums and nums == list(range(nums[0], nums[0] + len(nums))):
            fams[p] = [f for _, f in items]
    free = [i for i in range(len(labels)) if i not in labelled]
    out, gi, used = [], 0, set()
    for axis in (1, 0):      # rows (same y), then columns (same x)
        for side in (0, 1):
            pool = sorted([i for i in free if labels[i]["side"] == side and i not in used],
                          key=lambda i: labels[i]["xy"][axis])
            groups, cur = [], []
            for i in pool:
                if cur and abs(labels[i]["xy"][axis] - labels[cur[0]]["xy"][axis]) > ROW_TOL:
                    groups.append(cur)
                    cur = []
                cur.append(i)
            if cur:
                groups.append(cur)
            for g in groups:
                if len(g) < 3:
                    continue
                g = sorted(g, key=lambda i: labels[i]["xy"][1 - axis])
                cand = [p for p, members in fams.items() if len(members) == len(g)]
                if len(cand) != 1:
                    continue
                members = fams[cand[0]]
                for direction, seq in (("asc", members), ("desc", members[::-1])):
                    for li, f in zip(g, seq):
                        out.append(dict(label=li, how=f"row{gi}:{direction}", part=f.uuid, pads=None))
                used.update(g)
                gi += 1
    return out


def distance(geom, fp, pads=None):
    """Label box to the nearest of the footprint's pad centres (or of `pads`), mm."""
    ks = pads if pads else range(len(fp.pads))
    pts = [(fp.pads[k].x, fp.pads[k].y) for k in ks if k < len(fp.pads)]
    if not pts:
        return float("inf")
    return float(min(geom.distance(shapely.Point(x, y)) for x, y in pts))

