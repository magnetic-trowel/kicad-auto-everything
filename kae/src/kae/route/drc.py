# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""KiCad DRC with kicad-cli, the way kaebench scores (zones refilled, all severities, mm).

kicad-cli is found as in kaebench: KAE_KICAD_CLI (a command, possibly with a wrapper),
KAE_KICAD_WRAP + kicad-cli (e.g. "apptainer exec ~/kicad.sif"), or kicad-cli on PATH.
The board must have its project files (.kicad_pro, .kicad_dru) beside it, since KiCad takes
rule severities and custom rules from them.
"""
from kae import budget
import functools
import hashlib
import json
import re
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import stepcache
# what a report counts, shared with tools/kaeres/restart.py: on polarfire-som every repair round read
# 499 and last-mile rounds that joined 26-41 connections were discarded until the cap was looked past
from kae.drc_items import DRC_UNCONNECTED_CAP, ENV_DEPENDENT, UNCONNECTED_PY, errors, unconnected_ignored  # noqa: F401


class DrcError(RuntimeError):
    pass


@functools.lru_cache(maxsize=None)
def kicad_cli():
    v = os.environ.get("KAE_KICAD_CLI")
    if v:
        return tuple(shlex.split(v))
    w = os.environ.get("KAE_KICAD_WRAP")
    if w:
        return (*shlex.split(w), "kicad-cli")
    p = shutil.which("kicad-cli")
    if not p:
        raise DrcError("kicad-cli not found; set KAE_KICAD_CLI or KAE_KICAD_WRAP")
    return (p,)


def run(board, out_json, timeout=900, cache=True):
    """kicad-cli pcb drc on `board`; returns the parsed JSON report. `cache=False` runs KiCad even
    with the step cache on (a second run of the same board, to see which checks are noisy)."""
    board, out_json = Path(board).resolve(), Path(out_json).resolve()
    if out_json.exists():
        out_json.unlink()
    timeout = budget.wall_timeout(timeout)
    mb = board.stat().st_size / 1e6
    back, judged = {}, board
    if budget.work_mode():
        canonical_copper_order(board)
        judged, back = _judged_copy(board)
    try:
        rep = _run(judged, out_json, timeout, cache, mb)
        got = None
        if budget.work_mode() and rep.get("unconnected_items"):
            got = _copper_items(judged, timeout)
            canonical_unconnected(rep, (got or {}).get("items"))
        if len(rep.get("unconnected_items") or []) >= DRC_UNCONNECTED_CAP or unconnected_ignored(board):
            # the count copper_items took on the same refill, else pcbnew's own run
            n = got["unconnected"] if got and got.get("unconnected") is not None else uncapped_unconnected(judged, timeout)
            if n is not None:
                rep["unconnected_count"] = n
    finally:
        if judged != board:
            shutil.rmtree(judged.parent, ignore_errors=True)
    _map_uuids(rep, back)
    if budget.work_mode():
        # the file holds the report as returned (content order, the board's UUIDs, the uncapped count):
        # callers that read it back (repair's reroute rounds) see what this call's caller saw, not
        # KiCad's raw report of the temporary copy, whose UUIDs name nothing on `board`
        tmp = out_json.with_name(out_json.name + ".tmp")
        tmp.write_text(json.dumps(rep, indent=2))
        os.replace(tmp, out_json)
    return rep


def _run(board, out_json, timeout, cache, mb):
    cmd = [*kicad_cli(), "pcb", "drc", "--format", "json", "--refill-zones", "--severity-all",
           "--units", "mm", "-o", str(out_json), str(board)]
    try:
        if cache and stepcache.enabled():   # KAE_STEP_CACHE: a board DRC'd before, with the same rules, replays its report
            r = stepcache.run("kicad-drc", cmd, inputs=stepcache.kicad_inputs(board), outputs={"report": out_json},
                              wd=board.parent, timeout=timeout, tool=stepcache.kicad_version(kicad_cli()),
                              cwd=board.parent)
        else:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=board.parent, errors="replace")
    except subprocess.TimeoutExpired:
        raise DrcError(f"DRC timed out after {timeout}s")
    finally:
        from kae.board.pcbnew_io import zone_layers
        budget.charge("drc_run", 1)
        budget.charge("drc_mb", mb)
        budget.charge("drc_zone", zone_layers(board))    # --refill-zones: each zone layer refilled
    if not out_json.exists():
        raise DrcError(f"DRC failed (rc={r.returncode}): {(r.stdout + r.stderr)[-600:]}")
    with open(out_json) as f:
        rep = json.load(f)
    if budget.work_mode():              # KiCad's report follows the file's order (UUIDs: see kicad_file.load)
        for k in ("violations", "unconnected_items", "schematic_parity"):
            if rep.get(k):
                rep[k].sort(key=_content_key)
    return rep


def canonical_copper_order(board, uuids=False):
    """Rewrite `board` with its top-level (segment), (arc) and (via) blocks in the order of their content.
    KiCad writes copper in UUID order, new on every import of a routed board, and its ratsnest breaks ties
    between equally near copper by load order: the same board then reports other unconnected items.
    With `uuids`, the copper's UUIDs are also derived from that content (KiCad's counts depend on them
    too: two copies of one board with other UUIDs judged 96 and 97 open), and the result is
    {new uuid: old uuid}."""
    lines = Path(board).read_text(errors="replace").split("\n")
    blocks, first, out, i = [], None, [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith(("\t(segment", "\t(arc", "\t(via")) and not ln.startswith("\t(via_"):
            j, depth = i, 0
            while True:
                depth += lines[j].count("(") - lines[j].count(")")
                if depth <= 0:
                    break
                j += 1
            blocks.append(lines[i:j + 1])
            if first is None:
                first = len(out)
            i = j + 1
            continue
        out.append(ln)
        i += 1
    if blocks:
        blocks.sort(key=lambda b: [x for x in b if "(uuid" not in x and "(tstamp" not in x])
        back = {}
        if uuids:
            for k, blk in enumerate(blocks):
                h = hashlib.sha1(("%d\n" % k + "\n".join(x for x in blk if "(uuid" not in x)).encode()).hexdigest()
                u = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
                for x in blk:
                    m = _UUID.search(x)
                    if m:
                        back[u] = m.group(1)
                blocks[k] = [_UUID.sub(f'(uuid "{u}")', x) for x in blk]
        out[first:first] = [x for b in blocks for x in b]
        Path(board).write_text("\n".join(out))
        return back
    return {}


_UUID = re.compile(r'\(uuid "?([0-9a-fA-F-]+)"?\)')


def _judged_copy(board):
    """A temporary copy of `board` (with its project files) in canonical copper order with content UUIDs,
    and {new uuid: old uuid} to read its report against `board`."""
    d = Path(tempfile.mkdtemp(prefix="drc-canon-", dir=board.parent))
    for f in board.parent.glob(board.stem + ".kicad_*"):
        if f.suffix in (".kicad_pcb", ".kicad_pro", ".kicad_dru", ".kicad_prl"):
            shutil.copy2(f, d / f.name)
    c = d / board.name
    return c, canonical_copper_order(c, uuids=True)


def _map_uuids(rep, back):
    for k in ("violations", "unconnected_items"):
        for v in rep.get(k) or []:
            for it in v.get("items") or []:
                if it.get("uuid") in back:
                    it["uuid"] = back[it["uuid"]]


def _copper_items(board, timeout):
    """pcbnew_io.copper_items of `board` with clusters ({items, unconnected}), None when KiCad's Python
    cannot give them."""
    from kae.board.pcbnew_io import PcbnewError, copper_items
    try:
        got = copper_items(board, clusters=True, timeout=timeout)
        return got if isinstance(got.get("items"), list) else None
    except (PcbnewError, OSError, KeyError, TypeError, AttributeError):
        return None


def canonical_unconnected(rep, items):
    """Name the unconnected pairs of `rep` (in place) by choices that do not vary from run to run.

    kicad-cli's DRC of one and the same file names other pairs on every run (a 341-track board, five DRCs of
    one file: 1-9 of 182 pairs named otherwise each time, the count the same). Of the copper at the anchor
    the ratsnest joins (two tracks sharing an end, a connector's front and back pads at one position) it
    names whichever it came to first, and of equally long connections between clusters (copper laid out
    symmetrically, two clusters at one position) whichever its sort left first. The joint loop's congestion
    history and the repair loop's pad choice read those names and positions.

    For each net whose pairs all name pads, tracks, arcs, vias and copper graphics, the pairs are the
    connections of a minimum spanning tree between the net's clusters (`cluster` of `items`; without it, copper
    joined where anchors meet), equally long ones taken in the order of their anchors' positions, as long as
    there are as many as KiCad lists (else, e.g. past its cap, each pair is renamed alone: the nearest anchors
    of its two clusters, those with an anchor at one position taken as one). Each side of a connection is the
    first item (by description, position) of its cluster with an anchor there, and the pair's items are in that
    order. A zone's filled islands are items too (`key`: one per island, all with the zone's uuid; anchors:
    vertices of the outline): a pair that names a zone is mapped to the island that holds its position (else
    the nearest), and its side of a renamed pair is the zone at the connection's anchor. KiCad names a net's
    cut-off island as the zone in one DRC and as a pad of the island in the next (atrivatech ch32v003, at 2
    threads as at 16), and the repair loop split or dropped the net's planes by those names. A pair with an
    item `items` does not hold as KiCad describes it keeps KiCad's names, and the other pairs of its net are
    renamed one by one. `items`: pcbnew_io.copper_items of the board the report is of (None: the report is left
    as it is)."""
    if not items:
        return rep
    n = {}
    for it in items:
        n[_ident(it)] = n.get(_ident(it), 0) + 1
    items = [it for it in items if n[_ident(it)] == 1]          # a uuid two items share names neither
    if any("cluster" not in it for it in items):
        items = _anchor_clusters(items)
    by_uuid = {it["uuid"]: it for it in items if it.get("kind") != "zone"}
    islands = {}
    for it in items:
        if it.get("kind") == "zone":
            islands.setdefault(it["uuid"], []).append(it)

    def known_item(i):
        """`items`' item for a report item: by uuid, a zone's island by the report's position."""
        u = i.get("uuid")
        if u in by_uuid:
            return by_uuid[u]
        if u in islands and i.get("pos"):
            return _island_at(islands[u], (round(i["pos"]["x"] * 1e6), round(i["pos"]["y"] * 1e6)))
        return None
    at = {}                                       # (net, cluster) -> {anchor: [items]}
    for it in items:
        for p in it["anchors"]:
            at.setdefault((it["net"], it["cluster"]), {}).setdefault(tuple(p), []).append(it)

    # clusters with an anchor at one position (0 apart: a connector's front and back pads) as one, for
    # pairs renamed one by one: KiCad joins a third cluster to either
    sup = {k: k for k in at}

    def find(k):
        while sup[k] != k:
            sup[k] = sup[sup[k]]
            k = sup[k]
        return k
    meet = {}
    for (net, c), a in at.items():
        for p in a:
            k = meet.setdefault((net, p), (net, c))
            ra, rb = find(k), find((net, c))
            if ra != rb:
                sup[max(ra, rb, key=repr)] = min(ra, rb, key=repr)
    at_sup = {}
    for k, a in at.items():
        for p, its in a.items():
            at_sup.setdefault(find(k), {}).setdefault(p, []).extend(its)

    def rec(it, at_):
        x, y = at_ if it.get("kind") == "zone" else it["pos"]     # a zone: where the connection meets it
        return dict(description=it["description"], pos=dict(x=x / 1e6, y=y / 1e6), uuid=it["uuid"])

    def pair(ka, pa, kb, pb, of=at):
        first = [(min(of[k][p], key=lambda i: (i["description"], tuple(i["pos"]), _ident(i))), p)
                 for k, p in ((ka, pa), (kb, pb))]
        return sorted((rec(i, p) for i, p in first),
                      key=lambda r: (r["description"], r["pos"]["x"], r["pos"]["y"], r["uuid"]))

    def alone(u, x, y):
        """One pair renamed by itself: the nearest anchors of its two (merged) clusters."""
        ka, kb = find((x["net"], x["cluster"])), find((y["net"], y["cluster"]))
        if ka != kb:
            pa, pb = _nearest(list(at_sup[ka]), list(at_sup[kb]))
            u["items"] = pair(ka, pa, kb, pb, at_sup)

    per_net, raw = {}, set()
    for u in rep.get("unconnected_items") or []:
        its = u.get("items") or []
        known = [known_item(i) for i in its]
        nets = {k["net"] for k in known if k is not None}
        if len(its) != 2 or len(nets) != 1 or any(k is None or k["description"] != i.get("description")
                                                   for k, i in zip(known, its)):
            raw |= nets | {x for i in its for x in _NET_IN.findall(i.get("description") or "")}
            continue
        per_net.setdefault(nets.pop(), []).append((u, known))
    for net in sorted(per_net):
        got = per_net[net]
        tree = None if net in raw else _cluster_tree({c: list(a) for (nt, c), a in at.items() if nt == net})
        if tree is not None and len(tree) == len(got):
            for (u, _), (ca, pa, cb, pb) in zip(got, tree):
                u["items"] = pair((net, ca), pa, (net, cb), pb)
            continue
        for u, (x, y) in got:      # a net with zone pairs, past KiCad's cap, or a count that differs: one by one
            alone(u, x, y)
    for u in rep.get("unconnected_items") or []:
        if u.get("items"):
            u["items"].sort(key=lambda r: (r.get("description") or "", str(r.get("pos")), r.get("uuid") or ""))
    rep["unconnected_items"].sort(key=_content_key)
    return rep


_NET_IN = re.compile(r"\[([^\]]*)\]")


def _ident(it):
    """A copper item's identity: its uuid, or a zone island's key (a zone's islands share its uuid)."""
    return it.get("key") or it["uuid"]


def _island_at(isls, p):
    """Of a zone's islands (copper_items' zone items), the one whose outline holds the point `p` (nm),
    else the one with the nearest anchor; ties by key."""
    def inside(ring):
        x, y = p
        n, hit = len(ring), False
        for i in range(n):
            (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % n]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
        return hit
    return min(isls, key=lambda it: (0 if inside(it.get("ring") or it["anchors"]) else 1,
                                     min((a[0] - p[0]) ** 2 + (a[1] - p[1]) ** 2 for a in it["anchors"]),
                                     it["key"]))


def _cluster_tree(anchors):
    """A minimum spanning tree between clusters ({cluster: [anchor (x, y) nm]}): [(cluster a, anchor a,
    cluster b, anchor b)], each connection between the nearest anchors of what it joins, equally long ones
    in the order of their anchors; None when it cannot be computed (a degenerate large net)."""
    import numpy as np
    owners = {}
    for c, ps in anchors.items():
        for p in ps:
            owners.setdefault(p, set()).add(c)
    pts = sorted(owners)
    if len(anchors) < 2:
        return []
    cand = []
    for p in pts:                                 # clusters with an anchor at one position: 0 apart
        cs = sorted(owners[p], key=repr)
        cand += [(0, p, p, a, b) for i, a in enumerate(cs) for b in cs[i + 1:]]
    if len(pts) <= 400:
        pairs = [(i, j) for i in range(len(pts)) for j in range(i + 1, len(pts))]
    else:
        try:
            from scipy.spatial import Delaunay
            tri = Delaunay(np.array(pts, dtype=float))
        except Exception:                          # noqa: BLE001 - collinear or degenerate points
            return None
        ind, nb = tri.vertex_neighbor_vertices
        pairs = sorted({(min(i, j), max(i, j)) for i in range(len(pts)) for j in nb[ind[i]:ind[i + 1]]})
    for i, j in pairs:
        p, q = pts[i], pts[j]
        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
        for a in owners[p]:
            for b in owners[q]:
                if a != b:
                    cand.append((d, p, q, a, b))
    cand.sort(key=lambda e: (e[0], e[1], e[2], repr(e[3]), repr(e[4])))
    parent = {c: c for c in anchors}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c
    out = []
    for d, p, q, a, b in cand:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            out.append((a, p, b, q))
            if len(out) == len(anchors) - 1:
                break
    return out


def _anchor_clusters(items):
    """Copies of `items` with `cluster`: those of a net that share an anchor, directly or through others."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    first = {}
    for i, it in enumerate(items):
        for a in it["anchors"]:
            j = first.setdefault((it["net"], tuple(a)), i)
            parent[find(j)] = find(i)
    return [dict(it, cluster=find(i)) for i, it in enumerate(items)]


def _nearest(a, b):
    """The pair (p, q), p of `a` and q of `b` (integer points), nearest each other; of equally near pairs the
    first (p, q) in order."""
    if len(a) * len(b) <= 4096:
        return min(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2, p, q) for p in a for q in b)[1:]
    import numpy as np
    from scipy.spatial import cKDTree
    if len(a) > len(b):
        q, p = _nearest(b, a)
        return p, q
    tb = cKDTree(np.array(b, dtype=float))
    d, _ = tb.query(np.array(a, dtype=float), k=1)
    r = float(d.min()) + 2.0                     # float error; the exact choice is made in integers below
    best = None
    for i in np.flatnonzero(d <= r):
        p = a[i]
        for j in tb.query_ball_point(np.array(p, dtype=float), r):
            q = b[j]
            c = ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2, p, q)
            if best is None or c < best:
                best = c
    return best[1:]


def _content_key(v):
    """A violation's order by what it says, not by the UUIDs of the items it names."""
    return (v.get("type") or "", v.get("severity") or "", sorted((i.get("description") or "", str(i.get("pos"))) for i in v.get("items") or []))


def uncapped_unconnected(board, timeout=900):
    """pcbnew's unconnected count of `board` after a zone fill (no cap), None when it cannot run."""
    from kae.board.pcbnew_io import PcbnewError, _charge, kicad_python
    try:
        r = subprocess.run([*kicad_python(), "-c", UNCONNECTED_PY, str(board)], capture_output=True, text=True,
                           timeout=budget.wall_timeout(timeout), cwd=Path(board).parent, errors="replace")
        return int(json.loads(r.stdout.strip().splitlines()[-1])["unconnected"])
    except (PcbnewError, OSError, subprocess.TimeoutExpired, ValueError, IndexError, KeyError):
        return None
    finally:
        _charge(board, True)        # a KiCad Python of its own: the board loaded and its zones refilled


def summary(report):
    errs = errors(report)
    by = {}
    for v in errs:
        by[v["type"]] = by.get(v["type"], 0) + 1
    n = report.get("unconnected_count")
    return dict(errors=len(errs), unconnected=n if n is not None else len(report.get("unconnected_items", [])), by_type=by)


def excess(summary, base):
    """Error-level violations of `summary` beyond `base` ({type: count}, the board's own errors
    before routing), per type: what routing added. 0 for a board whose only errors it had already."""
    base = base or {}
    return sum(max(0, n - base.get(t, 0)) for t, n in (summary.get("by_type") or {}).items())


def promote_severities(staged_board, checks):
    """Set `checks` to 'error' in the staged board's .kicad_pro (a copy: stage_board), so KiCad's
    DRC reports what kae's fixed placement profile treats as errors. Returns the checks changed.
    Custom .kicad_dru rules with their own severity still apply (a designer's per-object waiver)."""
    pro = Path(staged_board).with_suffix(".kicad_pro")
    if not pro.exists():
        return []           # no project: KiCad's defaults, all of these are errors already
    try:
        d = json.loads(pro.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        return []
    rs = d.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rule_severities", {})
    changed = [c for c in checks if rs.get(c, "error") != "error"]
    if changed:
        for c in changed:
            rs[c] = "error"
        pro.write_text(json.dumps(d, indent=2))
    return changed


def stage_board(src_board, project_board, dest_dir):
    """Copy `src_board` into `dest_dir` as board.kicad_pcb with the project files of
    `project_board` (its .kicad_pro and .kicad_dru) beside it; returns the staged path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = dest_dir / "board.kicad_pcb"
    shutil.copy2(src_board, dst)
    for ext in (".kicad_pro", ".kicad_dru"):
        src = Path(project_board).with_suffix(ext)
        tgt = dest_dir / f"board{ext}"
        if src.exists():
            shutil.copy2(src, tgt)
        elif tgt.exists():
            tgt.unlink()
    return dst
