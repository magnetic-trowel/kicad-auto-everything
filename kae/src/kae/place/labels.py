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
           connector-like part (J, P, CN, CON, X, TP, JP references): those pads.
  keyword  a token of 3+ characters is in the net names of an LED's or a switch's pads; ON
           and OFF name the switches when there are at most two.
  row      k >= 3 labels on one side in a row or column (text anchors on one y or x within
           0.3 mm), not named otherwise, each with a distinct number, and exactly one family
           of k LEDs, switches or connectors with one reference prefix and consecutive numbers
           none of which is named otherwise: matched in numeric order (noisecard: '<40dB'
           ... '>105dB' to D1 ... D10). Consecutive integers ('1' ... '8' beside a header) are
           pin numbers: they name a family only when they are its reference numbers.
"""
from __future__ import annotations

import re
from pathlib import Path

import shapely

SPLIT = re.compile(r"[\s|/,;:]+")
CONN = re.compile(r"^(J|P|CN|CON|X|TP|JP)\d+$", re.I)
LED = re.compile(r"^(D|LED|LD)\d+$", re.I)
SWITCH = re.compile(r"^(SW|S|BTN|K)\d+$", re.I)
REFNUM = re.compile(r"^([A-Za-z_]+)(\d+)$")
NUMBER = re.compile(r"\d+(\.\d+)?")
ROW_TOL = 0.3     # mm: labels within this of one y (or x) are a row (column)
POWER = {"GND", "VCC", "VDD", "VSS", "VBUS", "VSYS", "VIN", "AGND", "DGND", "PGND", "GNDA", "GNDD", "VBAT"}
POWER_RE = re.compile(r"^\d+V\d*$|^\d+V\d+$|^\d+(\.\d+)?V$")   # 5V, 3V3, 12V, 3.3V


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
        at = sexpr.first(n, "at")
        out.append(dict(text=txt, tokens=tokens(txt), side=0 if ly == "F.SilkS" else 1, geom=g, xy=(c.x, c.y),
                        at=(float(at[1]), float(at[2]))))
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
            if len(t) >= 3 and t not in POWER and not POWER_RE.match(t):
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
    """Rows (columns) of unnamed labels that carry numbers ('<40dB' ... '>105dB', 'KEY0' ...
    'KEY3'), matched in numeric order to the one family of as many unnamed LEDs, switches
    or connectors with consecutive reference numbers (noisecard: D1 at '<40dB')."""
    fam = {}
    for f in fps:
        m = REFNUM.match(f.ref or "")
        if m and f.uuid not in named and (LED.match(f.ref) or SWITCH.match(f.ref) or CONN.match(f.ref)):
            fam.setdefault(m.group(1).upper(), []).append((int(m.group(2)), f))
    fams = {}
    for p, items in fam.items():
        items.sort(key=lambda t: t[0])
        nums = [n for n, _ in items]
        if nums == list(range(nums[0], nums[0] + len(nums))):
            fams[p] = [f for _, f in items]
    num = {}
    for i, lab in enumerate(labels):
        m = NUMBER.search(lab["text"])
        if m and i not in labelled:
            num[i] = float(m.group(0))
    out, gi, used = [], 0, set()
    for axis in (1, 0):      # rows (same y), then columns (same x), by the texts' anchors
        for side in (0, 1):
            pool = sorted([i for i in num if labels[i]["side"] == side and i not in used],
                          key=lambda i: labels[i]["at"][axis])
            groups, cur = [], []
            for i in pool:
                if cur and abs(labels[i]["at"][axis] - labels[cur[-1]]["at"][axis]) > ROW_TOL:
                    groups.append(cur)
                    cur = []
                cur.append(i)
            if cur:
                groups.append(cur)
            for g in groups:
                vals = sorted(num[i] for i in g)
                if len(g) < 3 or len(set(vals)) < len(g):
                    continue
                cand = [p for p, members in fams.items() if len(members) == len(g)]
                if len(cand) != 1:
                    continue
                members = fams.pop(cand[0])          # a family takes one row
                # consecutive integers are pin or channel numbers (a header's '1' ... '8'): they
                # name a family only when they are its reference numbers
                if all(v == int(v) for v in vals) and vals == list(range(int(vals[0]), int(vals[0]) + len(vals))):
                    refs = [int(REFNUM.match(f.ref).group(2)) for f in members]
                    if [int(v) for v in vals] != refs:
                        fams[cand[0]] = members
                        continue
                along = 0 if axis == 1 else 1           # a row (one y) runs along x
                cs = sorted(labels[i]["at"][along] for i in g)
                pitch = sorted(b - a for a, b in zip(cs, cs[1:]))[len(cs) // 2 - 1] if len(cs) > 1 else 0.0
                for li, f in zip(sorted(g, key=lambda i: num[i]), members):
                    out.append(dict(label=li, how=f"row{gi}", part=f.uuid, pads=None, along=along, pitch=pitch))
                used.update(g)
                gi += 1
    return out


def distance(geom, fp, pads=None, edge=False):
    """Label box to the nearest of the footprint's pad centres (or of `pads`), mm; edge=True
    to the pad's copper (its centre less half its smaller side: a terminal block's 3 mm pad
    beside its label is beside it)."""
    ks = [k for k in (pads if pads else range(len(fp.pads))) if k < len(fp.pads)]
    if not ks:
        return float("inf")
    out = []
    for k in ks:
        pd = fp.pads[k]
        d = geom.distance(shapely.Point(pd.x, pd.y))
        if edge:
            d = max(0.0, d - min(pd.size) / 2) if getattr(pd, "size", None) else d
        out.append(d)
    return float(min(out))



KINDS = ("pin", "row", "keyword")    # the kinds tools/research/place/labels.py validates
# on by default: kinds whose part the human put within 3 mm (pad copper) of its label on >= 90%
# of A/B/C (numbered rows 14/14 on 2 boards; connector pins 68%, keywords 49%: off)
DEFAULT_KINDS = ("row",)
DEFAULT_WEIGHT = 1.0


def associations(board, kinds=KINDS):
    """The labels that name exactly one part, of the validated kinds, with their evidence:
    [{label, text, xy, how, part (uuid), ref, pads (indices or None), evidence}]."""
    labs = board_labels(board)
    found = infer(board, labs)
    by_uuid = {f.uuid: f for f in board.footprints}
    groups = {}
    for a in found:
        kind = re.sub(r"\d+$", "", a["how"])
        if kind not in kinds:
            continue
        groups.setdefault((a["label"], a["how"]), []).append(a)
    out = []
    for (li, how), cands in groups.items():
        if len({a["part"] for a in cands}) != 1:
            continue          # several candidates: the label names one of them, not which
        a = cands[0]
        f = by_uuid[a["part"]]
        lab = labs[li]
        if a["pads"]:
            pads = [f.pads[k] for k in a["pads"]]
            ev = (f"'{lab['text'][:20]}' = " + ", ".join(sorted({p.pinfunction or p.net for p in pads}))[:40]
                  + f" of {f.ref} pad {', '.join(p.number for p in pads)[:20]}")
        elif how.startswith("row"):
            ev = f"'{lab['text'][:20]}' in a row of numbered labels, numeric order -> {f.ref}"
        elif {"ON", "OFF"} & set(lab["tokens"]):
            ev = f"'{lab['text'][:20]}' beside a switch: {f.ref}"
        else:
            ev = f"'{lab['text'][:20]}' in the nets of {f.ref}"
        x0, y0, x1, y1 = lab["geom"].bounds
        row = dict(along=a["along"], pitch=round(a["pitch"], 3)) if "along" in a else {}
        out.append(dict(label=li, text=lab["text"], xy=(round(lab["xy"][0], 3), round(lab["xy"][1], 3)),
                        half=round(max(x1 - x0, y1 - y0) / 2, 3), how=re.sub(r"\d+$", "", how), part=f.uuid,
                        ref=f.ref, pads=a["pads"], evidence=ev, **row))
    return out


def anchors(P, assoc, d0=1.5, weight=1.0, kinds=None):
    """Annealer label targets from associations (of `kinds`, default all): {part index: ([(X,
    Y) target origin per rotation], dead zone cells (one, or (x, y)), weight)} putting the
    labelled pads' centre at the label (dead zone: d0 plus half the label box's longer side;
    along a numbered row a third of its pitch, which keeps the row's order). A part named by
    several labels takes the first."""
    import math
    import numpy as np
    by_uuid = {p.uuid: p for p in P.parts}
    out = {}
    for a in assoc:
        if kinds is not None and a["how"] not in kinds:
            continue
        p = by_uuid.get(a["part"])
        if p is None or not p.movable or p.i in out:
            continue
        lx, ly = a["xy"]
        ks = a["pads"] or list(range(len(p.fp.pads)))
        tg = []
        for r in p.rots:
            c = np.asarray(r.pins)[ks].mean(axis=0) if len(r.pins) else np.zeros(2)
            tg.append((int(round((lx - P.ox - c[0]) / P.g)), int(round((ly - P.oy - c[1]) / P.g))))
        r = int(math.ceil((d0 + a.get("half", 0.0)) / P.g))
        if a.get("along") is not None and a.get("pitch"):
            # order within a numbered row: along the row a third of its pitch, so no two parts
            # of the row can trade places without leaving their labels
            ra = max(1, int(a["pitch"] / 3.0 / P.g))
            r = (ra, r) if a["along"] == 0 else (r, ra)
        out[p.i] = (tg, r, float(weight))
    return out
