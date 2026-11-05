# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A journal of copper changes and the one KiCad DRC gate that judges them (kae.route.finish).

    from kae.route import journal as J
    jr = J.Journal(input_text)
    jr.add(J.diff_entries("taut", before_text, after_text, keys={uuid: "net:GND", ...}))
    text = jr.text(kept_ids)                          # the input plus the kept entries
    out = J.gate(input_board, project_board, jr, workdir)   # DRC in/out, identity diff, ddmin revert

**Entries.** One entry is one change of one pass: its stage, net, the routing items it removed
(`before`, uuid -> block text) and those it wrote (`after`), and the earlier entries it built on
(`deps`). An entry builds on an earlier one when it removes or rewrites an item that one wrote
(taut tightening a tail rule D drew, power copper widening a tightened track), or when its new
copper lies within `margin` of copper of another net that the earlier one removed (it used the
room that change freed; restoring the old copper would collide). Reverting an entry reverts
everything that built on it (`dependants`); a kept set is always closed under `deps` (`closed`).

**Identity diff** (`diff`). A violation is (type, the input items involved, position bucket).
An output item that an entry wrote stands for the input items that entry (and those it built on)
removed (`ancestry`), so a pre-existing violation on a track taut rewrote is the same violation,
and a new one is new even when the count of its type did not grow. Unconnected items are
compared by count (the never-worse rule).

**Noise** (`noise_types`). Some checks report a different set on two runs of the same unchanged
board (magtag: `solder_mask_bridge`, 24 or 25). When a type looks worse, the gate runs the input
a second time (no step cache) and treats each type whose identity set differs as noise: it is
excluded from the identity diff and judged by count against the larger of the two input counts.

**Gate** (`gate`). DRC of the input (or the caller's report of it) and of the full output. When
the output is worse: the second input run (noise), then attribution (entries whose items the new
violations name, else within 1 mm, then 2.5 mm of them, with their dependants), then ddmin: from
the input, add stages back one by one, a failing stage net by net (halving), a failing net entry
by entry (halving), keeping each addition KiCad finds no worse. The board kept is the input or a
set KiCad has judged no worse: never worse than the input by type, nor in unconnected.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import time
from pathlib import Path

from . import critical_write as W

HEADS = ("segment", "arc", "via", "zone")
BUCKET = 0.5           # mm: position bucket of a violation (neighbouring buckets match too)
MARGIN = 0.5           # mm: new copper this close to another net's removed copper builds on its removal
                       # (finish passes the project's largest clearance, clearance_margin)
NET_RE = re.compile(r'\(net\s+("(?:[^"\\]|\\.)*"|[^\s()]+)')


# ----------------------------------------------------------------------------- items
def items(text):
    """{uuid: (head, block text)} of the board's top-level routing items and zones, file order."""
    out = {}
    for head, a, b in W._blocks(text, HEADS):
        blk = text[a:b]
        u = W._uuid_of(blk)
        if u:
            out[u] = (head, blk)
    return out


def net_of(block):
    m = NET_RE.search(block)
    if not m:
        return ""
    t = m.group(1)
    return json.loads(t) if t.startswith('"') else t


def _xy(block, key):
    m = re.search(r"\(" + key + r"\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\)", block)
    return (float(m.group(1)), float(m.group(2))) if m else None


def _num(block, key, default=0.0):
    m = re.search(r"\(" + key + r"\s+(-?[\d.eE+-]+)\)", block)
    return float(m.group(1)) if m else default


def geom(head, block):
    """(layers, shapely geometry) of an item's copper; layers None = every copper layer (a via)."""
    from shapely.geometry import LineString, Point, Polygon
    if head == "via":
        at = _xy(block, "at")
        return None, Point(at).buffer(_num(block, "size", 0.6) / 2, quad_segs=6) if at else None
    m = re.search(r'\(layer\s+"([^"]+)"', block)
    layers = {m.group(1)} if m else set(re.findall(r'"([^"]+\.Cu)"', block[:400]))
    if head == "zone":
        i = block.find("(polygon")
        sub = block[i:] if i >= 0 else ""
        for stop in ("(filled_polygon", "(polygon", "(fill_segments"):
            j = sub.find(stop, 1)
            if j > 0:
                sub = sub[:j]
        pts = [(float(x), float(y)) for x, y in re.findall(r"\(xy\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\)", sub)]
        return layers, Polygon(pts).buffer(0) if len(pts) >= 3 else None
    a, b = _xy(block, "start"), _xy(block, "end")
    if a is None or b is None:
        return layers, None
    w = _num(block, "width", 0.2)
    mid = _xy(block, "mid") if head == "arc" else None
    line = LineString([a, mid, b] if mid else [a, b]) if a != b or mid else Point(a)
    return layers, line.buffer(w / 2, quad_segs=4)


def clearance_margin(project_board, default=0.2, cap=MARGIN):
    """The largest net-class clearance of the project (what a restored track must keep from new
    copper), at most `cap`; `default` without one."""
    try:
        pro = json.loads(Path(project_board).with_suffix(".kicad_pro").read_text(encoding="utf-8"))
        cl = [float(c.get("clearance") or 0) for c in (pro.get("net_settings") or {}).get("classes") or []]
        return min(cap, max(cl)) if cl and max(cl) > 0 else default
    except (OSError, ValueError, TypeError, AttributeError):
        return default


# ----------------------------------------------------------------------------- entries
class Entry:
    __slots__ = ("id", "stage", "net", "before", "after", "deps", "meta")

    def __init__(self, id, stage, net, before, after, meta=None):
        self.id, self.stage, self.net = id, stage, net
        self.before, self.after = dict(before), dict(after)     # uuid -> (head, block)
        self.deps = set()
        self.meta = dict(meta or {})

    def record(self):
        return dict(id=self.id, stage=self.stage, net=self.net, before=sorted(self.before), after=sorted(self.after),
                    deps=sorted(self.deps), **self.meta)


def diff_entries(stage, before_text, after_text, keys=None, meta=None, net_keys=None):
    """The changes from `before_text` to `after_text` as entries of `stage`, one per key: `keys`
    {uuid: key} groups items (a pass's own change ids); an item without one is grouped by its net,
    or by `net_keys` {net: key} (the two nets of a diff pair: one entry, kept or reverted together).
    `meta` {key: dict}: extra fields per entry (kind, lengths). Unchanged items are left out."""
    keys = keys or {}
    meta = meta or {}
    net_keys = net_keys or {}
    b, a = items(before_text), items(after_text)
    groups = {}

    def put(u, side, item):
        n = net_of(item[1])
        k = keys.get(u) or net_keys.get(n) or "net:" + n
        g = groups.setdefault(k, dict(before={}, after={}, net=net_of(item[1])))
        g[side][u] = item
    for u, it in b.items():
        if u not in a or a[u][1] != it[1]:
            put(u, "before", it)
    for u, it in a.items():
        if u not in b or b[u][1] != it[1]:
            put(u, "after", it)
    return [Entry(f"{stage}:{k}", stage, g["net"], g["before"], g["after"], meta.get(k))
            for k, g in groups.items()]


class Journal:
    """The input board's text and the entries applied to it, in order."""

    def __init__(self, input_text, margin=MARGIN):
        self.input = input_text
        self.margin = margin
        self.entries = []          # in the order they were made
        self.by_id = {}
        self.writer = {}           # uuid -> id of the entry that last wrote it
        self._removed = []         # (entry id, net, layers, geometry) of removed copper, for space deps

    def add(self, entries):
        """Append one pass's entries, working out what each built on: items it removes that an earlier
        entry wrote, and other nets' copper that an entry of an earlier pass removed within `margin` of
        what it writes. Within one pass the changes were planned against each other in an order the
        diff does not keep, so two of its entries in such a conflict (either way round) are merged into
        one: kept or reverted together (taut: net A tightened into room net B left)."""
        from shapely import STRtree
        entries = list(entries)
        for e in entries:
            if e.id in self.by_id:
                raise ValueError(f"duplicate journal entry {e.id}")
        mine = []
        for k, e in enumerate(entries):
            for u, (head, blk) in e.before.items():
                layers, g = geom(head, blk)
                if g is not None:
                    mine.append((k, e.net, layers, g))
        removed = [(r, True) for r in self._removed] + [(r, False) for r in mine]
        tree = STRtree([r[3] for r, _ in removed]) if removed else None
        parent = list(range(len(entries)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for k, e in enumerate(entries):
            for u in e.before:
                if u in self.writer:
                    e.deps.add(self.writer[u])
            if tree is None:
                continue
            for u, (head, blk) in e.after.items():
                layers, g = geom(head, blk)
                if g is None:
                    continue
                for i in tree.query(g.buffer(self.margin)):
                    (who, net, ls, g2), earlier = removed[int(i)]
                    if net == e.net or (not earlier and who == k):
                        continue
                    if layers is not None and ls is not None and not (layers & ls):
                        continue
                    if g2.distance(g) > self.margin:
                        continue
                    if earlier:
                        e.deps.add(who)
                    else:
                        parent[find(k)] = find(who)
        groups = {}
        for k in range(len(entries)):
            groups.setdefault(find(k), []).append(entries[k])
        merged = []
        for k in sorted(groups):
            g = groups[k]
            if len(g) == 1:
                merged.append(g[0])
                continue
            nets = sorted({x.net for x in g})
            m = Entry(g[0].id, g[0].stage, "|".join(nets), {}, {}, dict(merged=[x.id for x in g]))
            for x in g:
                m.before.update(x.before)
                m.after.update(x.after)
                m.deps |= x.deps
            merged.append(m)
        for e in merged:
            self.entries.append(e)
            self.by_id[e.id] = e
            for u in e.after:
                self.writer[u] = e.id
            for u, (head, blk) in e.before.items():
                layers, g = geom(head, blk)
                if g is not None:
                    self._removed.append((e.id, e.net, layers, g))
        return self

    def ids(self, stage=None):
        return [e.id for e in self.entries if stage is None or e.stage == stage]

    def stages(self):
        out = []
        for e in self.entries:
            if e.stage not in out:
                out.append(e.stage)
        return out

    def dependants(self, ids):
        """`ids` and every entry that built on them, transitively."""
        out = set(ids)
        for e in self.entries:                 # entries only build on earlier ones
            if e.deps & out:
                out.add(e.id)
        return out

    def closed(self, ids):
        """The entries of `ids` whose dependencies are all kept (transitively): a set that can be built."""
        keep = set()
        for e in self.entries:
            if e.id in ids and e.deps <= keep:
                keep.add(e.id)
        return keep

    def text(self, kept=None):
        """The input with the entries in `kept` (all when None) applied in order; `kept` must be
        closed (see `closed`). Removed and rewritten input items are cut out; every item an
        entry wrote and no later kept entry removed is appended."""
        kept = set(self.by_id) if kept is None else set(kept)
        removed, added = set(), {}
        for e in self.entries:
            if e.id not in kept:
                continue
            for u in e.before:
                if u in added:
                    del added[u]
                else:
                    removed.add(u)
            for u, it in e.after.items():
                added[u] = it
        text = self.input
        out, pos = [], 0
        for head, a, b in W._blocks(text, HEADS):
            u = W._uuid_of(text[a:b])
            if u in removed or u in added:
                out.append(text[pos:a])
                pos = W._eat_newline(text, b)
        out.append(text[pos:])
        text = "".join(out)
        return W._insert(text, [blk + "\n" for _h, blk in added.values()]) if added else text

    def ancestry(self, kept=None):
        """{uuid written by a kept entry: the input uuids it stands for} (what that entry and those it
        built on removed; a pure addition stands for its entry)."""
        kept = set(self.by_id) if kept is None else set(kept)
        anc = {}
        for e in self.entries:
            if e.id not in kept:
                continue
            src = set()
            for u in e.before:
                src |= anc.get(u, {u})
            src = src or {e.id}
            for u in e.after:
                anc[u] = src
        return anc

    def records(self, kept=None):
        kept = set(self.by_id) if kept is None else set(kept)
        return [dict(e.record(), kept=e.id in kept) for e in self.entries]


# ----------------------------------------------------------------------------- identity diff
def violations(report):
    """[(type, [(uuid or description, (x, y) or None)])] of a report's error-level violations
    (as kaebench counts them)."""
    from . import drc
    out = []
    for v in drc.errors(report):
        its = []
        for it in v.get("items") or []:
            p = it.get("pos")
            its.append((it.get("uuid") or it.get("description") or "", (p["x"], p["y"]) if p else None))
        out.append((v.get("type"), its))
    return out


def _bucket(p):
    return (math.floor(p[0] / BUCKET), math.floor(p[1] / BUCKET)) if p else None


def identity(v, anc=None):
    """(type, frozenset of input items, position bucket) of a violation; `anc` maps output uuids to
    the input uuids they stand for."""
    t, its = v
    anc = anc or {}
    ids = frozenset(x for u, _ in its for x in anc.get(u, {u}))
    pos = next((p for _, p in its if p), None)
    return (t, ids, _bucket(pos))


def _near(b1, b2):
    if b1 is None or b2 is None:
        return b1 == b2
    return abs(b1[0] - b2[0]) <= 1 and abs(b1[1] - b2[1]) <= 1


def diff(base, out, anc=None, noise=()):
    """Violations of report `out` that report `base` does not have, by identity, one to one:
    [(type, items)] new in `out` (noise types left out). An output violation matches an input one
    of its type whose items it covers: every item of the input violation is among what the output's
    items stand for, and each output item stands for at least one of them. Matches in the same or a
    neighbouring position bucket are made first; then any position (a pre-existing violation on a
    track a pass rewrote moves with the track: cm4-carrier's track_width and clearance)."""
    anc = anc or {}
    pool = {}
    for v in violations(base):
        if v[0] in noise:
            continue
        t, ids, b = identity(v)
        pool.setdefault(t, []).append([ids, b, False])
    todo = []
    for v in violations(out):
        if v[0] in noise:
            continue
        per = [anc.get(u, {u}) for u, _ in v[1]]
        todo.append((v, identity(v, anc)[2], per, set().union(*per) if per else set()))

    def match(t, b, per, cover, near):
        hit = None
        for c in pool.get(t, ()):
            if c[2] or (near and not _near(c[1], b)):
                continue
            if c[0] <= cover and all(x & c[0] for x in per):
                hit = c
                if c[1] == b:
                    break
        return hit
    left = []
    for v, b, per, cover in todo:
        t = v[0]
        hit = match(t, b, per, cover, True)
        if hit is None:
            left.append((v, b, per, cover))
        else:
            hit[2] = True
    new = []
    for v, b, per, cover in left:
        t = v[0]
        hit = match(t, b, per, cover, False)
        if hit is None:
            new.append(v)
        else:
            hit[2] = True
    return new


def noise_types(rep1, rep2):
    """Types whose identity sets differ between two DRC reports of the same unchanged board."""
    from collections import Counter
    a = Counter(identity(v) for v in violations(rep1))
    b = Counter(identity(v) for v in violations(rep2))
    return sorted({k[0] for k in (a - b) + (b - a)})


def judge(base_reps, out, anc=None, noise=()):
    """What makes report `out` worse than the input: {type: n} of new violations by identity (noise
    types by count against the larger input count), plus 'unconnected' by count. {} = no worse."""
    from . import drc
    worse = {}
    for t, _ in diff(base_reps[0], out, anc, noise):
        worse[t] = worse.get(t, 0) + 1
    s = drc.summary(out)
    bs = [drc.summary(r) for r in base_reps]
    for t in noise:
        n = s["by_type"].get(t, 0) - max(b["by_type"].get(t, 0) for b in bs)
        if n > 0:
            worse[t] = n
    if s["unconnected"] > max(b["unconnected"] for b in bs):
        worse["unconnected"] = s["unconnected"] - max(b["unconnected"] for b in bs)
    # the floor of the never-worse rule: no type above the input's count either (an identity match
    # is one to one, so this only bites on a report that the match cannot see, e.g. no positions)
    for t, n in s["by_type"].items():
        if t not in worse and t not in noise and n > max(b["by_type"].get(t, 0) for b in bs):
            worse[t] = n - max(b["by_type"].get(t, 0) for b in bs)
    return worse


# ----------------------------------------------------------------------------- the gate
def _culprits(jr, kept, rep, new, near):
    """Kept entries the new violations name (an item they wrote), else whose copper lies within
    `near` mm of a violation's position."""
    from shapely.geometry import Point
    writer = {}
    for e in jr.entries:
        if e.id in kept:
            for u in e.after:
                writer[u] = e.id
    bad = set()
    pts = []
    for t, its in new:
        named = {writer[u] for u, _ in its if u in writer}
        if named:
            bad |= named
        else:
            pts += [p for _, p in its if p]
    if pts and not bad:
        for e in jr.entries:
            if e.id not in kept:
                continue
            for head, blk in list(e.after.values()) + list(e.before.values()):
                _, g = geom(head, blk)
                if g is not None and any(g.distance(Point(p)) <= near for p in pts):
                    bad.add(e.id)
                    break
    return bad


def gate(input_board, project_board, jr, workdir, base_report=None, budget=24, deadline=None, log=print,
         drc_run=None, recover=8):
    """Judge the journal's entries with KiCad's DRC and keep the largest set found no worse than the
    input. `base_report`: a DRC report of the input the caller already has (else one is run).
    `recover`: DRC runs at most for adding back what attribution reverted (0: none).
    Returns dict(kept={ids}, text, drc_in, drc_out, worse_full, noise, rounds, drc_runs, seconds)."""
    from . import drc
    t0 = time.monotonic()
    run = drc_run or drc.run
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    runs = [0]          # KiCad DRC runs (input runs included)
    probes = [0]        # of them, boards with entries (the budget)
    rounds = []

    def left():
        return 3600.0 if deadline is None else deadline - time.monotonic()

    def check(text, tag, fresh=False):
        d = wd / tag
        staged = drc.stage_board(input_board, project_board, d)
        if text is not None:
            staged.write_text(text, encoding="utf-8")
        runs[0] += 1
        kw = dict(cache=False) if fresh else {}
        return run(staged, d / "drc.json", timeout=max(10, left() - 5), **kw)

    reused = base_report is not None
    base = [base_report if reused else check(None, "in")]
    allids = set(jr.by_id)
    res = dict(kept=set(), drc_in=drc.summary(base[0]), drc_in_reused=reused, noise=[], rounds=rounds)
    if not allids:
        res.update(text=jr.input, drc_out=res["drc_in"], drc_runs=runs[0], seconds=round(time.monotonic() - t0, 1))
        return res
    noise = []
    best = dict(kept=set(), rep=base[0])

    def judged(kept, tag):
        probes[0] += 1
        rep = check(jr.text(kept), tag)
        worse = judge(base, rep, jr.ancestry(kept), noise)
        rounds.append(dict(tag=tag, kept=len(kept), summary=drc.summary(rep), worse=worse))
        log(f"[finish-gate] {tag}: {len(kept)}/{len(allids)} entries, {drc.summary(rep)['errors']} errors, "
            f"{drc.summary(rep)['unconnected']} unconnected; worse {worse or 'none'}")
        return rep, worse

    def addback(accepted, cands, limit, tag):
        """Grow `accepted` (judged no worse, or the input) by groups of `cands`: stages, failing ones by net
        halves, failing nets by entry halves, breadth first, each kept when KiCad finds it no worse.
        Returns the best (kept, report) found, None when nothing was added."""
        got = None
        queue = [("stage", [i for i in jr.ids(s) if i in cands]) for s in jr.stages()]
        k = 0
        while queue and probes[0] < limit and not (left() <= 20 and res.setdefault("time_limited", True)):
            level, group = queue.pop(0)
            if not group:
                continue
            trial = jr.closed(accepted | set(group))
            if trial == accepted:
                continue
            rep2, w2 = judged(trial, f"{tag}{k}-{level}")
            k += 1
            if not w2:
                accepted = trial
                got = dict(kept=set(trial), rep=rep2)
                continue
            nets = {}
            for i in group:
                nets.setdefault(jr.by_id[i].net, []).append(i)
            ns = sorted(nets)
            if level != "entries" and len(ns) > 1:
                h = len(ns) // 2
                queue += [("nets", [i for n in ns[:h] for i in nets[n]]), ("nets", [i for n in ns[h:] for i in nets[n]])]
            elif len(group) > 1:
                queue += [("entries", group[:len(group) // 2]), ("entries", group[len(group) // 2:])]
        return got

    rep, worse = judged(allids, "out")
    res["worse_full"] = dict(worse)
    if worse and any(t != "unconnected" for t in worse) and not (left() <= 30 and res.setdefault("time_limited", True)):
        # a type looks worse: is it noise? (a second run of the unchanged input, no cache)
        base.append(check(None, "in2", fresh=True))
        noise = noise_types(base[0], base[1])
        res["noise"] = noise
        if noise:
            log(f"[finish-gate] noise types (differ between two runs of the input): {noise}")
            worse = judge(base, rep, jr.ancestry(allids), noise)
            rounds.append(dict(tag="out/noise", kept=len(allids), summary=drc.summary(rep), worse=worse))
    if not worse:
        best = dict(kept=set(allids), rep=rep)
    else:
        # attribution: the entries the new violations name, else near them, and their dependants
        kept = set(allids)
        for near in (1.0, 2.5):
            if probes[0] >= budget or left() < 20:
                if left() < 20:
                    res["time_limited"] = True
                break
            new = diff(base[0], rep, jr.ancestry(kept), noise)
            bad = _culprits(jr, kept, rep, new, near)
            if not bad:
                continue
            kept = jr.closed(kept - jr.dependants(bad))
            rep, worse = judged(kept, f"attr{near}")
            if not worse:
                best = dict(kept=set(kept), rep=rep)
                break
        if worse:
            # ddmin from the input, breadth first: every stage, then the failing stages' halves by net, then a
            # failing net's entries by halves (a failing stage does not use up the budget of the later ones)
            best = addback(set(), set(allids), budget, "dd") or best
        elif recover and best["kept"] != allids:
            # attribution reverts whole neighbourhoods: add them back the same way while budget is left
            best = addback(set(best["kept"]), allids - best["kept"], min(budget, probes[0] + recover), "rec") or best
    kept = best["kept"]
    res.update(kept=kept, text=jr.text(kept) if kept else jr.input, drc_out=drc.summary(best["rep"]),
               drc_runs=runs[0], seconds=round(time.monotonic() - t0, 1))
    return res


def write(text, dst, project_board):
    """`text` to `dst` with `project_board`'s project files beside it."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    for ext in (".kicad_pro", ".kicad_dru"):
        s = Path(project_board).with_suffix(ext)
        if s.exists() and s.resolve() != dst.with_suffix(ext).resolve():
            shutil.copy2(s, dst.with_suffix(ext))
    return dst
