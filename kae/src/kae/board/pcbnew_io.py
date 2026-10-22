# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge to KiCad's pcbnew, run as a subprocess in KiCad's own Python.

    extract(path)                      pcbnew's poses, pads, courtyards, outline, rules
    write_poses(src, dst, poses)       set x, y, rot, side through pcbnew and save
    verify(path)                       kicad_file + transform vs pcbnew, pad by pad

KiCad's Python is found as in kaebench: KAE_KICAD_PYTHON (a command, possibly with a
wrapper prefix) or KAE_KICAD_WRAP (a prefix such as "apptainer exec ~/kicad.sif", to which
"python3" is appended), else the first of /usr/bin/python3, python3.12, python3.11 and the
macOS/Windows KiCad bundles that can `import pcbnew`. Paths are passed absolute, so a
containerized Python sees the same files (Apptainer binds $HOME, the cwd and /tmp).
Set KAE_TMPDIR when the container cannot see the default temporary directory.
"""
import functools
import json
import math
import os
import shlex
import subprocess
import tempfile
from importlib import resources
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from . import kicad_file, transform


class PcbnewError(RuntimeError):
    pass


def _env_cmd(name):
    v = os.environ.get(name)
    return shlex.split(v) if v else None


@functools.lru_cache(maxsize=None)
def kicad_python():
    """Command prefix for a Python that can `import pcbnew`."""
    cmd = _env_cmd("KAE_KICAD_PYTHON")
    wrap = _env_cmd("KAE_KICAD_WRAP")
    if cmd:
        cands = [cmd]
    elif wrap:
        cands = [[*wrap, "python3"]]
    else:
        cands = [[c] for c in ("/usr/bin/python3", "/usr/bin/python3.12", "/usr/bin/python3.11",
                               "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
                               r"C:\Program Files\KiCad\10.0\bin\python.exe") if Path(c).exists()]
    for c in cands:
        try:
            r = subprocess.run([*c, "-c", "import pcbnew"], capture_output=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            return tuple(c)
    raise PcbnewError("no Python with pcbnew found; set KAE_KICAD_PYTHON or KAE_KICAD_WRAP")


def available():
    """True when a Python with pcbnew can be found."""
    try:
        kicad_python()
        return True
    except PcbnewError:
        return False


def bridge_script():
    return str(resources.files("kae.board") / "kicad_scripts" / "pcbnew_bridge.py")


def _run(op, args, timeout):
    with tempfile.TemporaryDirectory(prefix="kae-pcbnew-", dir=os.environ.get("KAE_TMPDIR")) as d:
        out = os.path.join(d, "out.json")
        cmd = [*kicad_python(), bridge_script(), op, *args(out)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired:
            raise PcbnewError(f"pcbnew {op} timed out after {timeout}s")
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
        status = json.loads(lines[-1]) if lines else None
        if status is None:
            raise PcbnewError(f"pcbnew {op} produced no result (rc={r.returncode}): {r.stderr[-800:]}")
        if not status.get("ok"):
            detail = ""
            if os.path.exists(out):
                with open(out) as f:
                    detail = json.dumps(json.load(f))[:800]
            raise PcbnewError(f"pcbnew {op} failed: {status.get('error')} {detail}")
        with open(out) as f:
            return json.load(f)


def _abs(p):
    return str(Path(p).resolve())


def extract(path, courtyards=True, outline=True, timeout=900):
    """pcbnew's authoritative view of a board as a dict (see pcbnew_bridge.extract)."""
    flags = ([] if courtyards else ["--no-courtyards"]) + ([] if outline else ["--no-outline"])
    return _run("extract", lambda out: [_abs(path), out, *flags], timeout)


def _pose_list(poses):
    """Poses as [{uuid, x, y, rot, side}] from {uuid: (x, y, rot, side)},
    {uuid: {x, y, rot, side}}, or [{uuid, x, y, rot, side}]."""
    if isinstance(poses, dict):
        items = []
        for key, p in poses.items():
            if isinstance(p, dict):
                items.append(dict(uuid=key, **{k: p[k] for k in ("x", "y", "rot", "side")}))
            else:
                x, y, rot, side = p
                items.append(dict(uuid=key, x=x, y=y, rot=rot, side=side))
        return items
    return [dict(uuid=p.get("uuid") or p.get("ref"), x=p["x"], y=p["y"], rot=p["rot"], side=p["side"])
            for p in poses]


def write_poses(src_path, dst_path, poses, allow_locked=False, timeout=900):
    """Write `dst_path` = `src_path` with footprints moved to `poses`, through pcbnew.

    poses: {fp_uuid: (x, y, rot, side)} (values may also be dicts, or poses a list of
    {uuid, x, y, rot, side}); x, y in mm, rot in degrees as KiCad reports it for the placed
    part, side 'F' or 'B'. Keys are footprint uuids (Footprint.uuid, including the keys the
    loader synthesizes); a key that is no uuid but names exactly one reference is accepted.
    A side change uses FOOTPRINT::Flip (left-right, about the footprint's own position),
    then SetOrientation and SetPosition; nothing else changes. Unknown, ambiguous or
    locked footprints (unless allow_locked) fail the call before anything is written.
    pcbnew's SaveBoard writes `dst_path` only (no project files). Returns {moved, flipped}.

    The older argument order write_poses(src_path, poses, dst_path) is also accepted.
    """
    if isinstance(dst_path, (dict, list, tuple)) and not isinstance(poses, (dict, list, tuple)):
        dst_path, poses = poses, dst_path
    items = _pose_list(poses)
    for p in items:
        if p["side"] not in ("F", "B"):
            raise ValueError(f"side must be 'F' or 'B': {p}")
        p["x"], p["y"], p["rot"] = float(p["x"]), float(p["y"]), transform.norm_deg(p["rot"])
    with tempfile.TemporaryDirectory(prefix="kae-poses-", dir=os.environ.get("KAE_TMPDIR")) as d:
        pj = os.path.join(d, "poses.json")
        with open(pj, "w") as f:
            json.dump(items, f)
        flags = ["--allow-locked"] if allow_locked else []
        return _run("write-poses", lambda out: [_abs(src_path), pj, out, _abs(dst_path), *flags], timeout)


def resave(path_in, path_out, timeout=900):
    """pcbnew load + save, nothing changed (the baseline for structural diffs)."""
    return _run("resave", lambda out: [_abs(path_in), out, _abs(path_out)], timeout)


# ----------------------------------------------------------------------------- verify
def _polys(rings_list):
    out = []
    for rings in rings_list:
        if rings and len(rings[0]) >= 3:
            p = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
            out.append(p if p.is_valid else p.buffer(0))
    return out


def _geom(polys):
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else unary_union(polys)


def shape_distance(a, b, densify=0.25):
    """Symmetric Hausdorff distance between the boundaries of two (multi)polygons and
    the area of their symmetric difference."""
    ga, gb = _geom(a), _geom(b)
    if ga is None and gb is None:
        return 0.0, 0.0
    if ga is None or gb is None:
        return math.inf, (ga or gb).area
    hd = shapely.hausdorff_distance(ga.boundary, gb.boundary, densify=densify)
    return float(hd), float(ga.symmetric_difference(gb).area)


def _has_curves(fp, which):
    """Whether a library-frame courtyard came from arcs or circles (many vertices)."""
    polys = fp.courtyard if which == "own" else fp.courtyard_back
    return any(len(p.exterior.coords) > 12 for p in polys)


def verify(path, board=None, data=None, courtyards=True, worst=10):
    """Compare kicad_file.load + transform with pcbnew, pad by pad.

    Returns a report: pose and pad position errors (mm; transform path `pad_err` and the
    loader's stored `Pad.x/y` `pad_err_loader`), pad angle, net, kind and copper-layer
    mismatches, courtyard and outline distances, rule and net-class differences.
    """
    b = board if board is not None else kicad_file.load(path)
    x = data if data is not None else extract(path, courtyards=courtyards)
    kfp = {f["uuid"]: f for f in x["footprints"]}
    rep = dict(path=str(path), kicad_version=x.get("kicad_version"), footprints=len(b.footprints),
               pads=0, missing_fp=[], extra_fp=sorted(set(kfp) - {f.uuid for f in b.footprints})[:20],
               pose_err=0.0, rot_err=0.0, side_mismatch=[], locked_mismatch=[], pad_count_mismatch=[],
               pad_err=0.0, pad_err_loader=0.0, pad_err_vec=0.0, pad_angle_err=0.0,
               net_mismatch=0, kind_mismatch=0, layer_mismatch=0, worst_pads=[])
    worst_pads = []
    lx, ly, X, Y, R, S, KX, KY = [], [], [], [], [], [], [], []
    max_error = x.get("rules", {}).get("max_error", b.rules.max_error)
    cy = dict(n=0, n_arcs=0, max_straight=0.0, max_arcs=0.0, area_straight=0.0, missing=0, extra=0, worst=[])
    klist = x["footprints"]
    for i, fp in enumerate(b.footprints):
        k = kfp.get(fp.uuid)
        if k is None and i < len(klist) and klist[i]["lib_id"] == fp.lib_id:
            k = klist[i]  # no uuid in the file: pcbnew invents one; same file order
        if k is None:
            rep["missing_fp"].append(fp.ref)
            continue
        rep["pose_err"] = max(rep["pose_err"], math.hypot(fp.x - k["x"], fp.y - k["y"]))
        da = (fp.rot - k["rot"]) % 360.0
        rep["rot_err"] = max(rep["rot_err"], min(da, 360.0 - da))
        if fp.side != k["side"]:
            rep["side_mismatch"].append(fp.ref)
        if fp.locked != k["locked"]:
            rep["locked_mismatch"].append(fp.ref)
        kp = k["pads"]
        if len(kp) != len(fp.pads):
            rep["pad_count_mismatch"].append(fp.ref)
        by_uuid = {p["uuid"]: p for p in kp}
        for i, p in enumerate(fp.pads):
            q = by_uuid.get(p.uuid) if p.uuid else None
            if q is None and i < len(kp):
                q = kp[i]
            if q is None:
                continue
            rep["pads"] += 1
            ex, ey = transform.pad_xy(fp, p)
            err = math.hypot(ex - q["x"], ey - q["y"])
            rep["pad_err"] = max(rep["pad_err"], err)
            rep["pad_err_loader"] = max(rep["pad_err_loader"], math.hypot(p.x - q["x"], p.y - q["y"]))
            da = (transform.pad_angle(fp, p) - q["rot"]) % 360.0
            rep["pad_angle_err"] = max(rep["pad_angle_err"], min(da, 360.0 - da))
            if p.net != q["net"]:
                rep["net_mismatch"] += 1
            if p.kind != q["kind"]:
                rep["kind_mismatch"] += 1
            if {l for l in p.layers if l.endswith(".Cu")} != {l for l in q["layers"] if l.endswith(".Cu")}:
                rep["layer_mismatch"] += 1
            worst_pads.append((err, fp.ref, p.number))
            lx.append(p.lx)
            ly.append(p.ly)
            X.append(fp.x)
            Y.append(fp.y)
            R.append(fp.rot)
            S.append(fp.side == "B")
            KX.append(q["x"])
            KY.append(q["y"])
        if courtyards and "courtyard" in k:
            own, opp = transform.courtyard_layers(fp)
            for which, layer in (("own", own), ("opposite", opp)):
                ours = transform.courtyard(fp, which=which, deflate=max_error)
                theirs = _polys(k["courtyard"].get(layer, []))
                if not ours and not theirs:
                    continue
                cy["n"] += 1
                if not theirs:
                    cy["extra"] += 1
                    cy["worst"].append((math.inf, fp.ref, layer, "only ours"))
                    continue
                if not ours:
                    cy["missing"] += 1
                    cy["worst"].append((math.inf, fp.ref, layer, "only pcbnew"))
                    continue
                hd, da = shape_distance(ours, theirs)
                curved = _has_curves(fp, which)
                if curved:
                    cy["n_arcs"] += 1
                    cy["max_arcs"] = max(cy["max_arcs"], hd)
                else:
                    cy["max_straight"] = max(cy["max_straight"], hd)
                    cy["area_straight"] = max(cy["area_straight"], da)
                cy["worst"].append((hd, fp.ref, layer, "arcs" if curved else "straight"))
    if lx:
        px, py = transform.pads_xy(np.array(lx), np.array(ly), np.array(X), np.array(Y), np.array(R), np.array(S))
        rep["pad_err_vec"] = float(np.max(np.hypot(px - np.array(KX), py - np.array(KY))))
    worst_pads.sort(reverse=True)
    rep["worst_pads"] = [(round(e, 9), r, n) for e, r, n in worst_pads[:worst]]
    if courtyards:
        cy["worst"] = sorted(cy["worst"], key=lambda t: -t[0])[:worst]
        rep["courtyard"] = cy
    if "outline" in x:
        theirs = _polys(x["outline"])
        hd, da = shape_distance(b.outline, theirs)
        rep["outline"] = dict(ours=len(b.outline), pcbnew=len(theirs), hausdorff=hd, area_xor=da,
                              area=sum(p.area for p in theirs))
    rr = x.get("rules", {})
    rep["rules_diff"] = {k: (getattr(b.rules, k), v) for k, v in rr.items()
                         if hasattr(b.rules, k) and abs(getattr(b.rules, k) - v) > 1e-6}
    ncls = x.get("netclass", {})
    rep["netclass_diff"] = {n: (b.nets[n].netclass if n in b.nets else None, c) for n, c in ncls.items()
                            if n not in b.nets or b.nets[n].netclass != c}
    rep["nets_missing"] = sorted(set(ncls) - set(b.nets))[:20]
    rep["copper_diff"] = None if x.get("copper") == b.stackup.copper else (b.stackup.copper, x.get("copper"))
    rep["thickness_diff"] = abs(b.stackup.thickness - x.get("thickness", b.stackup.thickness))
    return rep
