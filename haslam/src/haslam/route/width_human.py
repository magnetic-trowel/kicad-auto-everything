# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Power-net track width against the human layout of the same board (class-independent).

    python -m haslam.route.width_human ROUTED.kicad_pcb[.gz] HUMAN.kicad_pcb [--json OUT]

The reference is the width the **human drew** on each net, not its net class: a KiCad class width is only the default
for new tracks, and corpus classes rarely exceed the pads they enter (docs/research/routing/power-net-track-width.md W8).
Pure Python (haslam's own board parser), no KiCad.

Nets measured ("power nets"): nets of the human board whose brief role (haslam.circuit.brief) is rail, ground or
switch node, or whose human width w_h is at least `wide` (1.2) x the board's signal width w_sig, as long as the human
drew at least `min_human_mm` of track on the net (a net the human only poured has no drawn width to compare with).
The headline subset `power` drops wide nets whose role is impedance-driven (IMPEDANCE_ROLES: USB pairs, RF feeds).
- w_h: length-weighted median width of the human's tracks on the net.
- w_sig: length-weighted median width of the human's tracks on all other nets.
A segment is narrow when its width < (1 - tol) x w_h (tol 0.05 absorbs 0.254 vs 0.25 mm).

Definitions, each a share in [0, 1] per net and pooled per board (sum of numerators / sum of denominators):
- `share`: narrow length / routed length.
- `share_x`: the same over the length beyond `reach` mm of every same-net pad, where a neck is not legitimate, and
  narrow length inside a same-net zone on the track's layer counts as wide enough (`pour`, default on: the pour
  carries the current there).
  (synth/scripts/width_check.py exempts a whole segment whose two ends lie near pads, which also exempts a straight
  pad-to-pad run of any length; here only the length near the pads is left out.)
- `deficit`: sum of L x max(0, 1 - w / w_h) / routed length: the missing share of width, so 0.127 mm against a
  2 mm human trunk counts more than 0.2 against 0.25.
- `share_i`: `share_x` weighted by each segment's branch current (power_copper.branch_currents: resistive solve of
  the routed copper under the evaluator's DC plan, haslam.excite.dc.planned_injections; zone outlines stand in for
  fills, since router outputs store none). Only nets the plan gives a source and a load; elsewhere missing.
Boards without a human layout (generated designs): `--ref class` takes each net's KiCad class width as w_h
(reference_from_classes); that is the class-relative measure W8 warns about, stated as such.
- `share_neck`: the part of `share_x` that is also narrower than the net's own KiCad class width (from the human
  board's `.kicad_pro`; without rules, w_h): the router necking, as opposed to drawing at a class the human widened
  past by hand. `share_x - share_neck` is what only a width source other than the class can close.
The same definitions applied to the human layout against its own w_h (`human`) give the floor: humans neck too.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

POWER_ROLES = ("rail", "ground", "switch_node")
IMPEDANCE_ROLES = ("high_speed", "rf", "clock")   # drawn wide for impedance, not current (USB pairs, RF feeds)
DEFS = ("share", "share_x", "deficit", "share_i", "share_neck")
DEFAULTS = dict(tol=0.05, reach=1.0, wide=1.2, min_human_mm=2.0, branch=True, pour=True)


def _load(path, rules=False):
    """A board (`.kicad_pcb` or `.kicad_pcb.gz`); `rules`: read the net classes of the `.kicad_pro` beside it."""
    from haslam.board.kicad_file import load
    p = Path(path)
    if p.suffix == ".gz":
        with tempfile.TemporaryDirectory(prefix="haslam-wh-") as d:
            q = Path(d) / p.stem
            q.write_bytes(gzip.decompress(p.read_bytes()))
            return load(q, rules=False)
    return load(p, rules=rules)


def class_width(board, net):
    """The net's KiCad class track width (None without rules)."""
    from haslam.board.kicad_file import netclass_of
    r = getattr(board, "rules", None)
    ncs = getattr(r, "netclasses", None) or {}
    if not ncs:
        return None
    for name in netclass_of(r, net).split(","):
        if name in ncs and ncs[name].track_width:
            return ncs[name].track_width
    return ncs["Default"].track_width if "Default" in ncs else None


def wmedian(pairs):
    """Length-weighted median of [(width, length)]; None when there is no length."""
    pairs = sorted((w, l) for w, l in pairs if l > 0)
    tot = sum(l for _w, l in pairs)
    if tot <= 0:
        return None
    acc = 0.0
    for w, l in pairs:
        acc += l
        if acc >= tot / 2:
            return w
    return pairs[-1][0]


def _seg_len(t):
    return math.dist(t.start, t.end)


def reference(human, brief=None, wide=DEFAULTS["wide"], min_human_mm=DEFAULTS["min_human_mm"]):
    """{net: {"w_h", "human_mm", "role", "by_role", "by_width"}} for the power nets of the human board, and w_sig."""
    if brief is None:
        from haslam.circuit.brief import build
        brief = build(human)
    roles = {n: (r or {}).get("role") for n, r in (brief.get("nets") or {}).items()}
    per = defaultdict(list)
    for t in human.tracks:
        if t.net:
            per[t.net].append((t.width, _seg_len(t)))
    power_role = {n for n, r in roles.items() if r in POWER_ROLES}
    w_sig = wmedian([p for n, ps in per.items() if n not in power_role for p in ps])
    out = {}
    for n, ps in per.items():
        mm = sum(l for _w, l in ps)
        if mm < min_human_mm:
            continue
        w_h = wmedian(ps)
        by_role = n in power_role
        by_width = bool(w_sig and w_h >= wide * w_sig - 1e-9)
        if by_role or by_width:
            out[n] = dict(w_h=w_h, human_mm=round(mm, 3), role=roles.get(n), by_role=by_role, by_width=by_width,
                          w_class=class_width(human, n))
    return out, w_sig


def reference_from_classes(board, brief=None, wide=DEFAULTS["wide"]):
    """reference() for a board with no human layout (a generated design): w_h = the net's KiCad class width, for nets
    whose class is >= `wide` x the Default class width or whose role is a power role. `board` loaded with rules."""
    from haslam.board.kicad_file import netclass_of
    if brief is None:
        from haslam.circuit.brief import build
        brief = build(board)
    roles = {n: (r or {}).get("role") for n, r in (brief.get("nets") or {}).items()}
    ncs = board.rules.netclasses
    w0 = ncs["Default"].track_width if "Default" in ncs else board.rules.track_min

    def width(net):
        for name in netclass_of(board.rules, net).split(","):
            if name in ncs and ncs[name].track_width:
                return ncs[name].track_width
        return w0
    out = {}
    for n in {t.net for t in board.tracks if t.net}:
        w = width(n)
        by_role = roles.get(n) in POWER_ROLES
        by_width = w >= wide * w0 - 1e-9
        if by_role or by_width:
            out[n] = dict(w_h=w, human_mm=None, role=roles.get(n), by_role=by_role, by_width=by_width, basis="class",
                          w_class=w)
    return out, w0


def _pads(board):
    """{net: [(token, board-frame polygon, copper layers)]}."""
    from haslam.route.critical_recheck import pad_poly
    out = defaultdict(list)
    for f in board.footprints:
        for p in f.pads:
            if not p.net:
                continue
            try:
                g = pad_poly(f, p)
            except Exception:
                continue
            out[p.net].append((f"{f.ref}.{p.number}", g, [ly for ly in p.layers if ly.endswith(".Cu") or ly == "*.Cu"]))
    return out


def _currents(board, nets, pads, intent=None, extra=None):
    """{net: {segment key: A}} from the DC plan's resistive solve, for nets it gives a source and a load.
    `intent`: operating facts for the plan (None: the evaluator's defaults); `extra`: {net: {"REF.PAD": A}} added
    for nets the plan does not cover (a design's width_injections.json)."""
    from haslam.excite import dc as DC
    from haslam.route import power_copper as P
    try:
        inj_all = dict(DC.planned_injections(board, intent) or {})
    except Exception:
        inj_all = {}
    fills = _pours(board)
    out = {}
    for net in nets:
        toks = {tk for tk, _g, _l in pads.get(net, ())}
        inj = {k: v for k, v in inj_all.items() if k in toks}
        inj.update({k: float(v) for k, v in ((extra or {}).get(net) or {}).items()})
        if not (any(v > 0 for v in inj.values()) and any(v < 0 for v in inj.values())):
            continue
        st = {}
        try:
            P.branch_currents(net, board.tracks, board.vias, pads.get(net, ()), dict(fills.get(net) or {}), inj, stats=st)
        except Exception:
            continue
        cur = {}
        for ln, i in st.get("track_i", []):
            c = list(ln.coords)
            cur[_key(c[0], c[-1])] = i
        out[net] = cur
    return out


def _key(a, b):
    a, b = (round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))
    return (a, b) if a <= b else (b, a)


def _pours(board):
    """{net: {layer: [polygon]}}: zone outlines (router outputs store no fills; an outline over-credits a pour that
    a clearance or another net cuts)."""
    out = defaultdict(lambda: defaultdict(list))
    for z in board.zones:
        if z.net and z.outline is not None:
            for ly in z.layers or ():
                out[z.net][ly].append(z.outline)
    return out


def measure_layout(board, ref, tol=DEFAULTS["tol"], reach=DEFAULTS["reach"], branch=DEFAULTS["branch"],
                   pour=DEFAULTS["pour"], intent=None, injections=None):
    """{net: {"routed_mm", "share", "share_x", "deficit", "share_i", "num": {...}, "den": {...}}} of `board`'s tracks
    on the nets of `ref` (reference()), against each net's human width."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    pads = _pads(board)
    by_net = defaultdict(list)
    for t in board.tracks:
        if t.net in ref:
            by_net[t.net].append(t)
    cur = _currents(board, [n for n in ref if by_net.get(n)], pads, intent, injections) if branch else {}
    pours = _pours(board)
    out = {}
    for net, r in ref.items():
        ts = by_net.get(net) or []
        w_h = r["w_h"]
        w_neck = min(w_h, r.get("w_class") or w_h)      # below this a track is narrower than its own class too
        zone = unary_union([g.buffer(reach) for _tk, g, _l in pads.get(net, ())]) if pads.get(net) else None
        poured = {ly: unary_union(gs) for ly, gs in pours.get(net, {}).items()} if pour else {}
        num = dict.fromkeys(DEFS, 0.0)
        den = dict.fromkeys(DEFS, 0.0)
        ci = cur.get(net)
        for t in ts:
            L = _seg_len(t)
            if L <= 0:
                continue
            narrow = t.width < (1 - tol) * w_h
            # the part of the segment beyond `reach` of every same-net pad (pad entry is where a neck is legitimate)
            seg = LineString([t.start, t.end])
            rest = seg.difference(zone) if zone is not None else seg
            Lx = rest.length
            # length a same-net zone on the layer carries counts as wide enough (in the denominator, never narrow)
            Ln = (rest.difference(poured[t.layer]).length if t.layer in poured and not rest.is_empty else Lx) \
                if narrow else 0.0
            den["share"] += L
            den["deficit"] += L
            num["share"] += L if narrow else 0.0
            num["deficit"] += L * max(0.0, 1.0 - t.width / w_h)
            if Lx > 1e-9:
                den["share_x"] += Lx
                num["share_x"] += Ln
                den["share_neck"] += Lx
                num["share_neck"] += Ln if t.width < (1 - tol) * w_neck else 0.0
                if ci is not None:
                    i = ci.get(_key(t.start, t.end), 0.0)
                    den["share_i"] += Lx * i
                    num["share_i"] += Ln * i
        if den["share"] <= 0:
            continue
        row = dict(routed_mm=round(den["share"], 3), w_h=w_h, num=num, den=den)
        for k in DEFS:
            row[k] = (num[k] / den[k]) if den[k] > 0 else None
        out[net] = row
    return out


def subsets_of(ref):
    """Net subsets reported: `power` (the headline: power roles, plus wide nets that are not impedance-driven),
    `power_no_gnd`, `by_role`, `by_width` (every wide net, USB and RF pairs included) and `all`."""
    power = {n for n, r in ref.items() if r["by_role"] or (r["by_width"] and r["role"] not in IMPEDANCE_ROLES)}
    return {"power": power, "power_no_gnd": {n for n in power if ref[n]["role"] != "ground"},
            "by_role": {n for n, r in ref.items() if r["by_role"]},
            "by_width": {n for n, r in ref.items() if r["by_width"]}, "all": None}


def pooled(rows, nets=None):
    """{definition: share} pooled over `rows` (measure_layout) restricted to `nets`."""
    res = {}
    for k in DEFS:
        n = sum(r["num"][k] for m, r in rows.items() if nets is None or m in nets)
        d = sum(r["den"][k] for m, r in rows.items() if nets is None or m in nets)
        res[k] = (n / d) if d > 0 else None
    return res


def measure(routed_path, human_path, opts=None, human=None, ref=None):
    """The board-level result: reference nets, per-net rows of the routed layout and of the human layout, pooled shares
    over all power nets and over the role / width subsets."""
    o = {**DEFAULTS, **(opts or {})}
    if human is None:
        human = _load(human_path)
    if ref is None:
        ref, w_sig = reference(human, wide=o["wide"], min_human_mm=o["min_human_mm"])
    else:
        ref, w_sig = ref
    routed = _load(routed_path)
    rows = measure_layout(routed, ref, o["tol"], o["reach"], o["branch"], o["pour"], o.get("intent"),
                          o.get("injections"))
    subsets = subsets_of(ref)
    return dict(opts=o, w_sig=w_sig, ref=ref, nets={n: {k: v for k, v in r.items() if k not in ("num", "den")}
                                                     for n, r in rows.items()},
                rows=rows, pooled={s: pooled(rows, ns) for s, ns in subsets.items()})


def human_floor(human_path, opts=None):
    """measure() of the human layout against itself."""
    o = {**DEFAULTS, **(opts or {})}
    human = _load(human_path)
    ref = reference(human, wide=o["wide"], min_human_mm=o["min_human_mm"])
    return measure(human_path, human_path, o, human=human, ref=ref)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("routed")
    ap.add_argument("human", help="the human layout; with --ref class, the board whose class widths are the reference")
    ap.add_argument("--ref", choices=("human", "class"), default="human")
    ap.add_argument("--no-pour", action="store_true")
    ap.add_argument("--intent", help="operating facts JSON for the DC plan (default: the evaluator's defaults)")
    ap.add_argument("--injections", help="JSON {net: {\"REF.PAD\": A}} for nets the DC plan does not cover")
    ap.add_argument("--tol", type=float, default=DEFAULTS["tol"])
    ap.add_argument("--reach", type=float, default=DEFAULTS["reach"])
    ap.add_argument("--wide", type=float, default=DEFAULTS["wide"])
    ap.add_argument("--no-branch", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    o = dict(tol=a.tol, reach=a.reach, wide=a.wide, branch=not a.no_branch, pour=not a.no_pour,
             intent=json.loads(Path(a.intent).read_text()) if a.intent else None,
             injections=json.loads(Path(a.injections).read_text()) if a.injections else None)
    if a.ref == "class":
        from haslam.board.kicad_file import load
        ref = reference_from_classes(load(Path(a.human)), wide=a.wide)
        res = measure(a.routed, None, o, human=False, ref=ref)
        hum = {"pooled": {s: dict.fromkeys(DEFS) for s in res["pooled"]}}
    else:
        res = measure(a.routed, a.human, o)
        hum = human_floor(a.human, o)
    if a.json:
        Path(a.json).write_text(json.dumps({"routed": {k: v for k, v in res.items() if k not in ("rows", "opts")},
                                            "opts": {k: v for k, v in o.items() if k not in ("intent", "injections")},
                                            "human": {k: v for k, v in hum.items() if k not in ("rows", "opts")}},
                                           indent=1))
    print(f"w_sig {res['w_sig']} mm; {len(res['ref'])} power nets")
    for n, r in sorted(res["nets"].items()):
        f = res["ref"][n]
        print(f"{n}: w_h {f['w_h']:.3f} ({f['role']}{', wide' if f['by_width'] else ''}); routed {r['routed_mm']:.1f} mm; "
              + " ".join(f"{k} {r[k]:.2f}" if r[k] is not None else f"{k} -" for k in DEFS))
    for s, p in res["pooled"].items():
        print(f"pooled {s}: " + " ".join(f"{k} {v:.3f}" if v is not None else f"{k} -" for k, v in p.items())
              + " | human " + " ".join(f"{k} {v:.3f}" if v is not None else f"{k} -" for k, v in hum["pooled"][s].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
