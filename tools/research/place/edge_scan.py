# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Distance of mechanical-interface parts to the board edge, per connector sub-class.

usage: edge_scan.py OUT.jsonl LIST   (LIST: lines "id<TAB>path[<TAB>tag]")
One JSON row per classified part (+ a 'control' sample of unclassified parts).
"""
import gzip, json, math, os, re, sys, tempfile, random
from multiprocessing import Pool

os.environ.setdefault("OMP_NUM_THREADS", "1")
from shapely.geometry import Point, MultiPolygon, box
from shapely.ops import unary_union

from kae.board import kicad_file, transform
from kae.place import fixed, mech_rules

I = re.I
SUB = (  # first match wins; text = lib name value desc
    ("usb", re.compile(r"usb(?!lc)", I)),
    ("barrel", re.compile(r"barrel|dc[-_ ]?jack|dcjack|power_?jack|(?<![a-z])pj-?0\d\d|dc-?0\d\d|dc_?power", I)),
    ("audio", re.compile(r"audio|3\.5 ?mm|(?<![a-z])trr?s(?![a-z])|phone_?jack|stereo|(?<![a-z])pj-?3\d\d|(?<![a-z])sj-?\d|headphone|6\.35", I)),
    ("rj/modular", re.compile(r"rj\d\d|8p8c|6p6c|magjack|modular|ethernet", I)),
    ("video/dsub", re.compile(r"hdmi|displayport|d-?sub|(?<![a-z])db-?\d|(?<![a-z])de-?9|vga|dvi", I)),
    ("rf-edge", re.compile(r"(?<![a-z])(sma|smb|bnc|mcx|f_?type)(?![a-z])", I)),
    ("rf-board", re.compile(r"u\.?fl|ipex|mmcx|mhf|w\.fl|(?<![a-z])coax", I)),
    ("card-slot", re.compile(r"micro_?sd|(?<![a-z])(sd|tf)_?card|(?<![a-z])sd(?![a-z])|(?<![a-z])sim|card_?holder|card_?socket", I)),
    ("card-edge", re.compile(r"card_?edge|edge_?conn|pci|m\.?2(?![0-9])", I)),
    ("terminal", re.compile(r"terminal|screw|(?<![a-z])(phoenix|wago)|tb00|kf301|dg30", I)),
    ("fpc", re.compile(r"(?<![a-z])(fpc|ffc)(?![a-z])|zif", I)),
    ("wire-to-board", re.compile(r"jst|molex|micro-?fit|pico-?blade|(?<![a-z])jwt|(?<![a-z])(xh|ph|sh|gh|zh|eh)[-_]?\d|grove|qwiic|stemma", I)),
    ("castellated", re.compile(r"castellat|(?<![a-z])cast[-_]?\d", I)),
    ("header", re.compile(r"pin_?header|pinhd|pin_?socket|socket_strip|(?<![a-z])hdr|idc|box_?header|(?<![a-z])conn?_0?\d+x\d+|pinheader|header", I)),
)


def subclass(cls, why, row):
    text = " ".join(row.get(k) or "" for k in ("lib", "name", "value", "desc"))
    if cls == "connector":
        for name, rx in SUB:
            if rx.search(text):
                return name
        return "connector-other"
    if cls == "mounting":
        return "fiducial" if re.search(r"fiducial|fid", why + text, I) else "mount-hole"
    if cls == "user":
        if mech_rules.DISPLAY.search(text):
            return "display"
        if re.search(r"cherry|(?<![a-z])mx(?![a-z])|kailh|choc|gateron|key_?switch|keyswitch", text, I):
            return "keyswitch"
        if re.search(r"encoder|pot", text, I):
            return "pot/encoder"
        if re.search(r"led", text, I):
            return "led-indicator"
        if re.search(r"buzzer|speaker|beeper", text, I):
            return "buzzer"
        return "switch/button"
    return cls


def outline_of(board):
    polys = [p for p in board.outline if p is not None and not p.is_empty]
    if not polys:
        return None
    return unary_union(polys)


def scan(item):
    try:
        return _scan(item)
    except Exception as e:  # noqa
        return [dict(id=item[0], tag=item[2], error='scan: ' + repr(e)[:200])]


def _scan(item):
    bid, path, tag = item
    try:
        if path.endswith(".gz"):
            with gzip.open(path, "rb") as f, tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as t:
                t.write(f.read()); tmp = t.name
            try:
                b = kicad_file.load(tmp, rules=False)
            finally:
                os.unlink(tmp)
        else:
            b = kicad_file.load(path, rules=False)
    except Exception as e:  # noqa
        return [dict(id=bid, tag=tag, error=repr(e)[:200])]
    out_geom = outline_of(b)
    if out_geom is None or out_geom.area < 1:
        return [dict(id=bid, tag=tag, error="no outline")]
    parts = list(out_geom.geoms) if isinstance(out_geom, MultiPolygon) else [out_geom]
    minx, miny, maxx, maxy = out_geom.bounds
    rows = []
    rng = random.Random(hash(bid) & 0xffff)
    for fp in b.footprints:
        if not fp.pads or not getattr(fp, "on_board", True):
            continue
        row = fixed.mech_row(fp)
        cls, why = mech_rules.classify(row)
        if cls is None:
            if why.startswith("exclude") or rng.random() > 0.15:
                continue
            sub = "control"
        else:
            sub = subclass(cls, why, row)
        cy = transform.courtyard(fp, which="extent")
        if cy:
            g = unary_union(cy)
        else:
            xs = [p.x for p in fp.pads]; ys = [p.y for p in fp.pads]
            g = box(min(xs), min(ys), max(xs), max(ys))
        c = g.centroid
        host = min(parts, key=lambda p: p.distance(c))
        ext = host.exterior
        inside = host.contains(c)
        d_ext = g.distance(ext) if host.contains(g) else 0.0
        over = g.difference(host).area / g.area if g.area > 0 else 0.0
        d_any = min(d_ext, *(g.distance(i) for i in host.interiors)) if host.interiors else d_ext
        span = min(host.bounds[2] - host.bounds[0], host.bounds[3] - host.bounds[1])
        # facing: pad centroid -> courtyard centroid (body ahead of the pins) vs outward normal
        px = sum(pd.x for pd in fp.pads) / len(fp.pads); py = sum(pd.y for pd in fp.pads) / len(fp.pads)
        q = ext.interpolate(ext.project(c))
        ox, oy = q.x - c.x, q.y - c.y
        if not inside:
            ox, oy = -ox, -oy
        bx, by = c.x - px, c.y - py
        nb, no = math.hypot(bx, by), math.hypot(ox, oy)
        face = round((bx * ox + by * oy) / (nb * no), 3) if nb > 0.3 and no > 1e-6 else None
        rows.append(dict(id=bid, tag=tag, ref=fp.ref, side=fp.side, cls=cls, sub=sub, why=why,
                         lib=fp.lib_id, value=fp.value, pads=len(fp.pads), d=round(d_ext, 3),
                         d_any=round(d_any, 3), over=round(over, 3), inside=inside, span=round(span, 2),
                         cdist=round(c.distance(ext), 3), w=round(g.bounds[2] - g.bounds[0], 2),
                         h=round(g.bounds[3] - g.bounds[1], 2), x=round(fp.x, 3), y=round(fp.y, 3),
                         locked=fp.locked, face=face, rot=fp.rot))
    if not rows:
        rows.append(dict(id=bid, tag=tag, empty=True))
    return rows


def main():
    out, lst = sys.argv[1], sys.argv[2]
    nproc = int(os.environ.get("KAEQ_CPUS", "8"))
    items = []
    for line in open(lst):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2:
            items.append((p[0], p[1], p[2] if len(p) > 2 else "human"))
    with Pool(nproc, maxtasksperchild=50) as pool, open(out, "w") as f:
        for rows in pool.imap_unordered(scan, items, chunksize=4):
            for r in rows:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
