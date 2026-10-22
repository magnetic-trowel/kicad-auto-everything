#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance runs for kae.board against pcbnew on the prepared kaebench tasks.

    board_acceptance.py verify    [--tasks DIR] [-j 2]   loader + transform vs pcbnew, every board
    board_acceptance.py roundtrip [--tasks DIR] [-n 20]  write_poses -> pcbnew -> pad_xy, structural diff
    board_acceptance.py place     [--tasks DIR]          staging off-board, locked parts in place
    board_acceptance.py loadtime  [--tasks DIR]          load time per board, sequential, median of 3
    board_acceptance.py loadall   [--tasks DIR]          regression: every board loads (exit 1 if not)
    board_acceptance.py merge --name OUT RUN [RUN...]    verify runs merged, later rows win

Boards: DIR/<id>/reference/board.kicad_pcb and DIR/<id>/place/input/board.kicad_pcb.
Results: kae-work/kae-board/acceptance/<run>.jsonl plus a summary on stdout and in
<run>.summary.json. Run with OMP_NUM_THREADS=1; -j counts pcbnew processes.
"""
import argparse
import importlib
import inspect
import json
import math
import os
import random
import shutil
import statistics
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from shapely.geometry import Polygon

from kae.board import kicad_file, pcbnew_io, sdiff, transform

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "kae-work" / "kae-board" / "acceptance"


def boards(tasks, kinds):
    out = []
    for d in sorted(Path(tasks).iterdir()):
        for kind in kinds:
            p = d / ("reference" if kind == "reference" else "place/input") / "board.kicad_pcb"
            if p.exists():
                out.append((d.name, kind, p))
    return out


def _clean(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


# ----------------------------------------------------------------------------- verify
def verify_one(arg):
    bid, kind, path = arg
    try:
        t0 = time.perf_counter()
        b = kicad_file.load(path)
        load_s = time.perf_counter() - t0
        rep = pcbnew_io.verify(path, board=b)
        rep.update(id=bid, kind=kind, load_s=load_s, n_flags=sum(1 for f in b.footprints if f.flags),
                   flags=sorted({fl for f in b.footprints for fl in f.flags}), warnings=b.warnings,
                   off_board=sum(1 for f in b.footprints if not f.on_board))
        return _clean(rep)
    except Exception as e:
        return dict(id=bid, kind=kind, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])


def summarize_verify(rows):
    ok = [r for r in rows if "error" not in r]
    s = dict(boards=len(rows), errors=[(r["id"], r["kind"], r["error"]) for r in rows if "error" in r])
    s["pads"] = sum(r["pads"] for r in ok)
    s["max_pad_err_mm"] = max((r["pad_err"] for r in ok), default=None)
    s["max_pad_err_loader_mm"] = max((r["pad_err_loader"] for r in ok), default=None)
    s["max_pad_err_vec_mm"] = max((r["pad_err_vec"] for r in ok), default=None)
    s["boards_over_1um"] = [(r["id"], r["kind"], r["pad_err"]) for r in ok if r["pad_err"] > 1e-3]
    s["max_pad_angle_err_deg"] = max((r["pad_angle_err"] for r in ok), default=None)
    for k in ("net_mismatch", "kind_mismatch", "layer_mismatch"):
        s[k] = sum(r[k] for r in ok)
    for k in ("missing_fp", "side_mismatch", "locked_mismatch", "pad_count_mismatch"):
        s[k] = sum(len(r[k]) for r in ok)
    cy = [r["courtyard"] for r in ok]
    s["courtyards"] = sum(c["n"] for c in cy)
    s["courtyards_with_arcs"] = sum(c["n_arcs"] for c in cy)
    s["courtyard_max_straight_mm"] = max((c["max_straight"] or 0 for c in cy), default=None)
    s["courtyard_max_arcs_mm"] = max((c["max_arcs"] or 0 for c in cy), default=None)
    s["courtyard_missing"] = sum(c["missing"] for c in cy)
    s["courtyard_extra"] = sum(c["extra"] for c in cy)
    s["courtyard_straight_over_1um"] = [(r["id"], r["kind"], r["courtyard"]["max_straight"]) for r in ok
                                        if (r["courtyard"]["max_straight"] or 0) > 1e-3]
    s["courtyard_mismatch_worst"] = [(r["id"], r["kind"], w) for r in ok for w in r["courtyard"]["worst"]
                                     if w[0] is None or (w[3] == "straight" and w[0] > 1e-3)][:30]
    s["outline_count_mismatch"] = [(r["id"], r["kind"], r["outline"]["ours"], r["outline"]["pcbnew"]) for r in ok
                                   if r.get("outline") and r["outline"]["ours"] != r["outline"]["pcbnew"]]
    s["outline_max_hausdorff_mm"] = max((r["outline"]["hausdorff"] or 0 for r in ok if r.get("outline")), default=None)
    s["outline_worst"] = sorted(((r["outline"]["hausdorff"] if r["outline"]["hausdorff"] is not None else 1e9,
                                  r["id"], r["kind"]) for r in ok if r.get("outline")), reverse=True)[:5]
    s["rules_diff"] = [(r["id"], r["kind"], r["rules_diff"]) for r in ok if r["rules_diff"]]
    s["netclass_diff"] = [(r["id"], r["kind"], len(r["netclass_diff"]), list(r["netclass_diff"].items())[:3])
                          for r in ok if r["netclass_diff"]]
    s["nets_missing"] = [(r["id"], r["kind"], r["nets_missing"]) for r in ok if r["nets_missing"]]
    s["copper_diff"] = [(r["id"], r["kind"], r["copper_diff"]) for r in ok if r["copper_diff"]]
    s["thickness_diff"] = [(r["id"], r["kind"], r["thickness_diff"]) for r in ok if r["thickness_diff"] > 1e-6]
    s["flags"] = sorted({f for r in ok for f in r["flags"]})
    for kind in ("reference", "place"):
        t = [r["load_s"] for r in ok if r["kind"] == kind]
        if t:
            s[f"load_s_{kind}"] = dict(median=statistics.median(t), max=max(t))
    return s


# ----------------------------------------------------------------------------- round trip
def _copy_board(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    for ext in (".kicad_pro", ".kicad_dru"):
        if src.with_suffix(ext).exists():
            shutil.copy(src.with_suffix(ext), dst.with_suffix(ext))


def random_poses(b, rng, n_parts=40, p_flip=0.3, p_free_angle=0.35):
    """Random poses for a sample of unlocked footprints: positions inside the board's
    bounding box, multiples of 90 degrees or arbitrary angles, some flips."""
    free = [f for f in b.footprints if not f.locked]
    sample = rng.sample(free, min(n_parts, len(free)))
    if b.outline:
        xs = [p.bounds for p in b.outline]
        x0, y0, x1, y1 = min(v[0] for v in xs), min(v[1] for v in xs), max(v[2] for v in xs), max(v[3] for v in xs)
    else:
        x0, y0, x1, y1 = (min(f.x for f in b.footprints), min(f.y for f in b.footprints),
                          max(f.x for f in b.footprints), max(f.y for f in b.footprints))
    poses = {}
    for f in sample:
        rot = round(rng.uniform(0, 360), 3) if rng.random() < p_free_angle else float(rng.choice([0, 90, 180, 270]))
        side = ("B" if f.side == "F" else "F") if rng.random() < p_flip else f.side
        poses[f.uuid] = (round(rng.uniform(x0, x1), 6), round(rng.uniform(y0, y1), 6), rot, side)
    return poses


def _pad_err(b, poses, x):
    """Max distance between pad_xy predictions and pcbnew's pads in extraction x."""
    k = {f["uuid"]: f for f in x["footprints"]}
    worst, n = 0.0, 0
    for fp in b.footprints:
        X, Y, R, S = poses.get(fp.uuid, (fp.x, fp.y, fp.rot, fp.side))
        pred = [transform.pad_xy(fp, p, X, Y, R, S) for p in fp.pads]
        pairs = pcbnew_io.pair_pads(fp.pads, k[fp.uuid]["pads"], pred)
        at = {id(p): xy for p, xy in zip(fp.pads, pred)}
        for p, q in pairs:
            ex, ey = at[id(p)]
            worst = max(worst, math.hypot(ex - q["x"], ey - q["y"]))
            n += 1
    return worst, n


def _courtyard_err(b, poses, x, max_error):
    k = {f["uuid"]: f for f in x["footprints"]}
    worst_straight, worst_arcs, n = 0.0, 0.0, 0
    for fp in b.footprints:
        if fp.uuid not in poses:
            continue
        X, Y, R, S = poses[fp.uuid]
        own, opp = transform.courtyard_layers(fp, S)
        for which, layer in (("own", own), ("opposite", opp)):
            ours = transform.courtyard(fp, X, Y, R, S, which=which, deflate=max_error)
            theirs = pcbnew_io._polys(k[fp.uuid]["courtyard"].get(layer, []))
            if not ours and not theirs:
                continue
            n += 1
            hd, _ = pcbnew_io.shape_distance(ours, theirs)
            if pcbnew_io._has_curves(fp, which):
                worst_arcs = max(worst_arcs, hd)
            else:
                worst_straight = max(worst_straight, hd)
    return worst_straight, worst_arcs, n


def _library_frame_drift(b, b2, poses):
    old = b.by_uuid()
    dpos, drot, dcy, dlayer = 0.0, 0.0, 0.0, 0
    for f2 in b2.footprints:
        if f2.uuid not in poses:
            continue
        f1 = old[f2.uuid]
        q1 = {p.uuid: p for p in f1.pads}
        for p in f2.pads:
            q = q1[p.uuid]
            dpos = max(dpos, abs(p.lx - q.lx), abs(p.ly - q.ly))
            d = (p.lrot - q.lrot) % 360.0
            drot = max(drot, min(d, 360.0 - d))
            if set(transform.layers_at(q.layers, f1.side, f2.side, len(b.stackup.copper))) != set(p.layers):
                dlayer += 1
        for a, c in ((f1.courtyard, f2.courtyard), (f1.courtyard_back, f2.courtyard_back)):
            if a or c:
                hd, _ = pcbnew_io.shape_distance(a, c)
                dcy = max(dcy, hd)
    return dpos, drot, dcy, dlayer


def _fallback_writer():
    try:
        return importlib.import_module("kae.place.writer")
    except ImportError:
        return None


def _fallback_check(wr, b, src, base, work, poses):
    """kae.place.writer.write_sexpr vs write_poses for the same poses with sides kept (the
    S-expression writer does not flip), both re-extracted by pcbnew, pad by pad."""
    old = b.by_uuid()
    same_side = {u: (x, y, r, old[u].side) for u, (x, y, r, _) in poses.items()}
    ref_out, fb = work / "same_side.kicad_pcb", work / "fallback.kicad_pcb"
    pcbnew_io.write_poses(src, ref_out, same_side)
    names = list(inspect.signature(wr.write_sexpr).parameters)
    if len(names) >= 2 and names[1] == "poses":
        wr.write_sexpr(src, same_side, fb)
    else:
        wr.write_sexpr(src, fb, same_side)
    xr = pcbnew_io.extract(ref_out, courtyards=True, outline=False)
    xf = pcbnew_io.extract(fb, courtyards=True, outline=False)
    kf = {f["uuid"]: f for f in xf["footprints"]}
    dpos, dang, dcy, n, missing = 0.0, 0.0, 0.0, 0, 0
    for f in xr["footprints"]:
        g = kf.get(f["uuid"])
        if g is None:
            missing += 1
            continue
        gp = {p["uuid"]: p for p in g["pads"]}
        for p in f["pads"]:
            q = gp.get(p["uuid"])
            if q is None:
                missing += 1
                continue
            n += 1
            dpos = max(dpos, math.hypot(q["x"] - p["x"], q["y"] - p["y"]))
            d = (q["rot"] - p["rot"]) % 360.0
            dang = max(dang, min(d, 360.0 - d))
        if f["uuid"] in poses:
            for layer in ("F.CrtYd", "B.CrtYd"):
                a, c = pcbnew_io._polys(f["courtyard"][layer]), pcbnew_io._polys(g["courtyard"][layer])
                if a or c:
                    dcy = max(dcy, pcbnew_io.shape_distance(a, c)[0])
    pred, _ = _pad_err(b, same_side, xf)
    moved = set(poses)
    foreign = [c for c in sdiff.diff(base, fb) if c["id"] not in moved]
    return dict(fallback_pads=n, fallback_missing=missing, fallback_vs_pcbnew=dpos, fallback_angle_vs_pcbnew=dang,
                fallback_courtyard_vs_pcbnew=dcy, fallback_vs_pad_xy=pred, fallback_foreign=foreign[:10])


def roundtrip_one(arg):
    bid, kind, path, seed, n_parts = arg
    work = OUT / "rt" / bid
    try:
        if work.exists():
            shutil.rmtree(work)
        src = work / "board.kicad_pcb"
        _copy_board(Path(path), src)
        b = kicad_file.load(src)
        rng = random.Random(f"{seed}:{bid}")
        poses = random_poses(b, rng, n_parts)
        out = work / "out.kicad_pcb"
        res = pcbnew_io.write_poses(src, out, poses)
        x = pcbnew_io.extract(out, courtyards=True, outline=False)
        pad_err, n_pads = _pad_err(b, poses, x)
        cs, ca, ncy = _courtyard_err(b, poses, x, transform.KICAD_COURTYARD_DEFLATE)
        b2 = kicad_file.load(out)
        dpos, drot, dcy, dlayer = _library_frame_drift(b, b2, poses)
        rep2 = pcbnew_io.verify(out, board=b2, data=x)
        base = work / "base.kicad_pcb"
        pcbnew_io.resave(src, base)
        noop = sdiff.diff(src, base)
        changed = sdiff.diff(base, out)
        moved = {u for u, (X, Y, R, S) in poses.items()}
        foreign = [c for c in changed if not (c["kind"] == "footprint" and c["change"] == "changed"
                                             and c["id"] in moved)]
        back = work / "back.kicad_pcb"
        orig = {fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in b.footprints if fp.uuid in poses}
        pcbnew_io.write_poses(out, back, orig)
        restore_raw = sdiff.diff(base, back)
        restore = sdiff.diff(base, back, rotation_artifacts=True)
        row = dict(id=bid, kind=kind, footprints=len(b.footprints), moved=res["moved"], flipped=res["flipped"],
                   free_angle=sum(1 for p in poses.values() if p[2] % 90), pads_checked=n_pads,
                   pad_err=pad_err, courtyards_checked=ncy, courtyard_err_straight=cs, courtyard_err_arcs=ca,
                   written_file_pad_err=rep2["pad_err"], library_drift_pos=dpos, library_drift_rot=drot,
                   library_drift_courtyard=dcy, layer_flip_mismatch=dlayer,
                   noop_resave_changes=len(noop), changed_objects=len(changed), foreign_changes=foreign[:20],
                   restore_changes_raw=len(restore_raw), restore_changes=restore[:20])
        wr = _fallback_writer()
        if wr is not None and hasattr(wr, "write_sexpr"):
            try:
                row.update(_fallback_check(wr, b, src, base, work, poses))
            except Exception as e:
                row["fallback_error"] = f"{type(e).__name__}: {e}"
        shutil.rmtree(work, ignore_errors=True)
        return _clean(row)
    except Exception as e:
        return dict(id=bid, kind=kind, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])


def summarize_roundtrip(rows):
    ok = [r for r in rows if "error" not in r]
    s = dict(boards=len(rows), errors=[(r["id"], r["error"]) for r in rows if "error" in r])
    s["moved"] = sum(r["moved"] for r in ok)
    s["flipped"] = sum(r["flipped"] for r in ok)
    s["free_angle"] = sum(r["free_angle"] for r in ok)
    s["pads_checked"] = sum(r["pads_checked"] for r in ok)
    for k in ("pad_err", "courtyard_err_straight", "courtyard_err_arcs", "written_file_pad_err",
              "library_drift_pos", "library_drift_rot", "library_drift_courtyard"):
        s[f"max_{k}"] = max((r[k] or 0 for r in ok), default=None)
    s["layer_flip_mismatch"] = sum(r["layer_flip_mismatch"] for r in ok)
    s["noop_resave_changes"] = sum(r["noop_resave_changes"] for r in ok)
    s["foreign_changes"] = [(r["id"], r["foreign_changes"]) for r in ok if r["foreign_changes"]]
    s["restore_changes_raw"] = sum(r["restore_changes_raw"] for r in ok)
    s["restore_changes"] = [(r["id"], r["restore_changes"]) for r in ok if r["restore_changes"]]
    s["fallback_errors"] = [(r["id"], r["fallback_error"]) for r in ok if r.get("fallback_error")]
    fb = [r for r in ok if "fallback_vs_pcbnew" in r]
    if fb:
        s["fallback_boards"] = len(fb)
        s["fallback_pads"] = sum(r["fallback_pads"] for r in fb)
        s["fallback_missing"] = sum(r["fallback_missing"] for r in fb)
        for k in ("fallback_vs_pcbnew", "fallback_angle_vs_pcbnew", "fallback_courtyard_vs_pcbnew",
                  "fallback_vs_pad_xy"):
            s[f"max_{k}"] = max((r[k] if r[k] is not None else math.inf) for r in fb)
        s["fallback_foreign"] = [(r["id"], r["fallback_foreign"]) for r in fb if r["fallback_foreign"]]
    return s


# ----------------------------------------------------------------------------- place
def place_one(arg):
    bid, tasks = arg
    try:
        ref = kicad_file.load(Path(tasks) / bid / "reference" / "board.kicad_pcb")
        pl = kicad_file.load(Path(tasks) / bid / "place" / "input" / "board.kicad_pcb")
        rf = ref.by_uuid()
        row = dict(id=bid, footprints=len(pl.footprints), unlocked=0, unlocked_on_board=[], locked=0,
                   locked_moved=[], locked_off_board=[], ref_off_board=sum(1 for f in ref.footprints if not f.on_board),
                   missing=[], outline=len(pl.outline), warnings=pl.warnings)
        for f in pl.footprints:
            r = rf.get(f.uuid)
            if r is None:
                row["missing"].append(f.ref)
                continue
            if f.locked:
                row["locked"] += 1
                da = (f.rot - r.rot) % 360.0
                if (math.hypot(f.x - r.x, f.y - r.y) > 1e-6 or min(da, 360 - da) > 1e-6 or f.side != r.side):
                    row["locked_moved"].append(f.ref)
                if f.on_board != r.on_board:
                    row["locked_off_board"].append(f.ref)
            else:
                row["unlocked"] += 1
                if f.on_board:
                    row["unlocked_on_board"].append(f.ref)
        return row
    except Exception as e:
        return dict(id=bid, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])


def summarize_place(rows):
    ok = [r for r in rows if "error" not in r]
    return dict(boards=len(rows), errors=[(r["id"], r["error"]) for r in rows if "error" in r],
                footprints=sum(r["footprints"] for r in ok), unlocked=sum(r["unlocked"] for r in ok),
                unlocked_on_board=[(r["id"], r["unlocked_on_board"]) for r in ok if r["unlocked_on_board"]],
                locked=sum(r["locked"] for r in ok),
                locked_moved=[(r["id"], r["locked_moved"]) for r in ok if r["locked_moved"]],
                locked_on_board_differs=[(r["id"], r["locked_off_board"]) for r in ok if r["locked_off_board"]],
                no_outline=[(r["id"], r["warnings"]) for r in ok if not r["outline"]],
                ref_parts_off_board=[(r["id"], r["ref_off_board"]) for r in ok if r["ref_off_board"]])


# ----------------------------------------------------------------------------- load time
def loadtime(items, repeat=3):
    rows = []
    for bid, kind, p in items:
        ts = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            kicad_file.load(p)
            ts.append(time.perf_counter() - t0)
        rows.append(dict(id=bid, kind=kind, bytes=os.path.getsize(p), load_s=statistics.median(ts)))
    return rows


def summarize_loadtime(rows):
    s = {}
    for kind in ("reference", "place"):
        t = sorted(r["load_s"] for r in rows if r["kind"] == kind)
        if t:
            worst = max((r for r in rows if r["kind"] == kind), key=lambda r: r["load_s"])
            s[kind] = dict(boards=len(t), median_s=statistics.median(t), p90_s=t[int(0.9 * (len(t) - 1))],
                           max_s=t[-1], max_board=worst["id"], max_bytes=worst["bytes"],
                           over_1s=sum(1 for x in t if x > 1.0))
    return s


def loadall(items):
    rows = []
    for bid, kind, p in items:
        try:
            b = kicad_file.load(p)
            rows.append(dict(id=bid, kind=kind, ok=True, warnings=b.warnings,
                             flags=sorted({f for fp in b.footprints for f in fp.flags})))
        except Exception as e:
            rows.append(dict(id=bid, kind=kind, ok=False, error=f"{type(e).__name__}: {e}",
                             trace=traceback.format_exc()[-1500:]))
    return rows


def summarize_loadall(rows):
    return dict(boards=len(rows), failed=[(r["id"], r["kind"], r["error"]) for r in rows if not r["ok"]],
                warnings=[(r["id"], r["kind"], r["warnings"]) for r in rows if r["ok"] and r["warnings"]],
                flags=sorted({f.split(":")[0] for r in rows if r["ok"] for f in r["flags"]}))


def _run(fn, args, jobs):
    if jobs <= 1:
        return [fn(a) for a in args]
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(fn, args))


def _save(name, rows, summary):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    (OUT / f"{name}.summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["verify", "roundtrip", "place", "loadtime", "loadall", "merge"])
    ap.add_argument("runs", nargs="*", help="merge: verify run names")
    ap.add_argument("--tasks", default=str(ROOT / "kae-work" / "tasks"))
    ap.add_argument("--kinds", default="reference,place")
    ap.add_argument("--only", default="", help="comma-separated task ids")
    ap.add_argument("-j", "--jobs", type=int, default=2)
    ap.add_argument("-n", type=int, default=20, help="roundtrip: number of boards")
    ap.add_argument("--parts", type=int, default=40, help="roundtrip: footprints moved per board")
    ap.add_argument("--seed", default="1")
    ap.add_argument("--name", default="")
    a = ap.parse_args(argv)
    only = set(filter(None, a.only.split(",")))
    items = [x for x in boards(a.tasks, a.kinds.split(",")) if not only or x[0] in only]
    name = a.name or a.what
    if a.what == "verify":
        rows = _run(verify_one, items, a.jobs)
        _save(name, rows, summarize_verify(rows))
    elif a.what == "roundtrip":
        refs = [x for x in items if x[1] == "reference"]
        step = max(1, len(refs) // a.n)
        pick = refs[::step][:a.n] if not only else refs
        rows = _run(roundtrip_one, [(i, k, p, a.seed, a.parts) for i, k, p in pick], a.jobs)
        _save(name, rows, summarize_roundtrip(rows))
    elif a.what == "place":
        ids = sorted({i for i, k, p in items if k == "place"})
        rows = _run(place_one, [(i, a.tasks) for i in ids], a.jobs)
        _save(name, rows, summarize_place(rows))
    elif a.what == "loadtime":
        rows = loadtime(items)
        _save(name, rows, summarize_loadtime(rows))
    elif a.what == "loadall":
        rows = loadall(items)
        summary = summarize_loadall(rows)
        _save(name, rows, summary)
        return 1 if summary["failed"] else 0
    elif a.what == "merge":
        merged = {}
        for run in a.runs:
            for line in open(OUT / f"{run}.jsonl"):
                r = json.loads(line)
                merged[(r["id"], r["kind"])] = r
        rows = [merged[k] for k in sorted(merged)]
        _save(name, rows, summarize_verify(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
