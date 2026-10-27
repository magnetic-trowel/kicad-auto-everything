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

Calls go to a long-lived KiCad Python (pcbnew_bridge.py worker), started on first use, which
runs each operation in a child forked right after `import pcbnew`: the same operation code
and pcbnew state as a process of its own per call, without KiCad's start-up each time. A
process keeps one worker per thread calling at once. KAE_PCBNEW_WORKER=0 starts a process
per call instead.
"""
import atexit
import functools
import json
import math
import os
import select
import shlex
import signal
import subprocess
import tempfile
import threading
import time
from importlib import resources
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon
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
        if _worker_enabled() and _configured_python():
            _release(_acquire(300))  # starting a worker is the probe, and it is kept
        else:
            kicad_python()
        return True
    except PcbnewError:
        return False


def bridge_script():
    return str(resources.files("kae.board") / "kicad_scripts" / "pcbnew_bridge.py")


def _tmpdir():
    """KAE_TMPDIR when it names an existing directory, else the default temporary directory
    (a sandbox can hide the configured path, e.g. bwrap mounts a tmpfs over /var/tmp)."""
    d = os.environ.get("KAE_TMPDIR")
    return d if d and os.path.isdir(d) else None


def _result(op, status, rc, stderr, out):
    if status is None:
        raise PcbnewError(f"pcbnew {op} produced no result (rc={rc}): {stderr[-800:]}")
    if not status.get("ok"):
        detail = ""
        if os.path.exists(out):
            with open(out) as f:
                detail = json.dumps(json.load(f))[:800]
        raise PcbnewError(f"pcbnew {op} failed: {status.get('error')} {detail}")
    with open(out) as f:
        return json.load(f)


def _run_process(op, args, timeout):
    """One KiCad Python process for this call (KAE_PCBNEW_WORKER=0)."""
    with tempfile.TemporaryDirectory(prefix="kae-pcbnew-", dir=_tmpdir()) as d:
        out = os.path.join(d, "out.json")
        cmd = [*kicad_python(), bridge_script(), op, *args(out)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired:
            raise PcbnewError(f"pcbnew {op} timed out after {timeout}s")
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
        return _result(op, json.loads(lines[-1]) if lines else None, r.returncode, r.stderr, out)


# ----------------------------------------------------------------------------- worker
def _worker_enabled():
    return os.environ.get("KAE_PCBNEW_WORKER", "1").strip().lower() not in ("0", "false", "no", "off") \
        and hasattr(os, "fork")


def _configured_python():
    """The configured KiCad Python command (KAE_KICAD_PYTHON or KAE_KICAD_WRAP + python3),
    or None. A worker starts it without probing it first: its start fails clearly instead."""
    cmd = _env_cmd("KAE_KICAD_PYTHON")
    if cmd:
        return tuple(cmd)
    wrap = _env_cmd("KAE_KICAD_WRAP")
    return (*wrap, "python3") if wrap else None


class _WorkerDied(Exception):
    pass


class _WorkerTimeout(Exception):
    pass


def _tail(path, n=800):
    try:
        with open(path, errors="replace") as f:
            return f.read()[-n:]
    except OSError:
        return ""


def _fd_tail(fd, n=800):
    """The end of an open file (a worker's stderr, unlinked as soon as it is opened)."""
    try:
        size = os.fstat(fd).st_size
        return os.pread(fd, n, max(0, size - n)).decode(errors="replace")
    except OSError:
        return ""


class _Worker:
    """One `pcbnew_bridge.py worker` process. Answers are read from its stdout, where the
    bridge writes only its own JSON lines (KiCad's noise goes to stderr)."""

    def __init__(self, timeout):
        self.key = _worker_key()
        self.owner = os.getpid()
        self.closed = False
        fd, log = tempfile.mkstemp(prefix="kae-pcbnew-worker-", suffix=".log", dir=_tmpdir())
        os.unlink(log)  # nothing left behind, whatever ends this process
        self.log = fd
        cmd = [*(_configured_python() or kicad_python()), bridge_script(), "worker"]
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=fd)
        except OSError as e:
            os.close(fd)
            raise PcbnewError(f"pcbnew worker did not start ({shlex.join(cmd)}): {e}")
        self.buf = b""
        _ALL.add(self)
        try:
            ready = self._line(time.monotonic() + timeout)
        except (_WorkerDied, _WorkerTimeout) as e:
            err = _fd_tail(fd)
            self.close()
            how = "exited" if isinstance(e, _WorkerDied) else f"no answer in {timeout:.0f}s"
            raise PcbnewError(f"pcbnew worker did not start ({how}; {shlex.join(cmd)}): {err}")
        if ready.get("kae_worker") != "ready":
            self.close()
            raise PcbnewError(f"pcbnew worker did not start: {ready}")

    def _line(self, deadline):
        """The next JSON line of the worker's stdout."""
        fd = self.proc.stdout.fileno()
        while True:
            i = self.buf.find(b"\n")
            if i >= 0:
                ln, self.buf = self.buf[:i], self.buf[i + 1:]
                if ln.startswith(b"{"):
                    return json.loads(ln)
                continue
            left = deadline - time.monotonic()
            if left <= 0:
                raise _WorkerTimeout()
            r, _, _ = select.select([fd], [], [], left)
            if r:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    raise _WorkerDied()
                self.buf += chunk

    def request(self, argv, stderr, timeout):
        """(status line or None, exit status) of one operation."""
        deadline = time.monotonic() + timeout
        try:
            self.proc.stdin.write((json.dumps(dict(argv=argv, stderr=stderr)) + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            raise _WorkerDied()
        status = None
        while True:
            m = self._line(deadline)
            if "kae_worker" in m:
                return status, m.get("rc")
            status = m

    def close(self):
        _ALL.discard(self)
        if self.owner != os.getpid() or self.closed:
            return
        self.closed = True
        try:
            self.proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()  # its children die with it (PR_SET_PDEATHSIG)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        try:
            self.proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            os.close(self.log)
        except OSError:
            pass

    def kill(self):
        if self.owner == os.getpid() and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL)
        self.close()


_IDLE = []        # workers waiting for a call
_ALL = set()      # every live worker of this process
_LOCK = threading.Lock()


def _worker_key():
    """What a worker inherited when it started; one whose start differs is not reused (a
    process per call would see the current environment and directory)."""
    return (_configured_python() or kicad_python(), bridge_script(), dict(os.environ), os.getcwd())


def _acquire(timeout):
    key = _worker_key()
    stale = []
    with _LOCK:
        w = None
        while _IDLE:
            c = _IDLE.pop()
            if c.key == key and c.proc.poll() is None:
                w = c
                break
            stale.append(c)
    for c in stale:
        c.close()
    return w if w is not None else _Worker(timeout)


def _release(w):
    with _LOCK:
        _IDLE.append(w)


def _close_all():
    """At exit: idle workers end with their stdin, busy ones (other threads) are killed."""
    with _LOCK:
        idle, busy = list(_IDLE), [w for w in _ALL if w not in _IDLE]
        _IDLE.clear()
    for w in idle:
        w.close()
    for w in busy:
        w.kill()


def _forget_in_child():
    """A forked kae process must not talk to its parent's workers."""
    for w in list(_ALL):
        for f in (w.proc.stdin, w.proc.stdout):
            try:
                f.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            os.close(w.log)
        except OSError:
            pass
    _ALL.clear()
    _IDLE.clear()
    global _LOCK
    _LOCK = threading.Lock()


atexit.register(_close_all)
if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_forget_in_child)


def _run_worker(op, args, timeout):
    with tempfile.TemporaryDirectory(prefix="kae-pcbnew-", dir=_tmpdir()) as d:
        out = os.path.join(d, "out.json")
        err = os.path.join(d, "stderr.txt")
        argv = [op, *args(out)]
        t_end = time.monotonic() + timeout
        for attempt in (0, 1):
            left = t_end - time.monotonic()
            if left <= 0:
                raise PcbnewError(f"pcbnew {op} timed out after {timeout}s")
            w = _acquire(left)  # raises PcbnewError when no worker starts
            try:
                status, rc = w.request(argv, err, max(1e-3, t_end - time.monotonic()))
            except _WorkerTimeout:
                w.kill()
                raise PcbnewError(f"pcbnew {op} timed out after {timeout}s")
            except _WorkerDied:
                log = _fd_tail(w.log)
                w.kill()
                if attempt:
                    raise PcbnewError(f"pcbnew worker died twice during {op}: {log}")
                continue
            except BaseException:
                w.kill()  # e.g. KeyboardInterrupt mid-request: its answer would be read by the next call
                raise
            _release(w)
            return _result(op, status, rc, _tail(err, 1 << 20), out)


def _run(op, args, timeout):
    if _worker_enabled():
        return _run_worker(op, args, timeout)
    return _run_process(op, args, timeout)


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
    KiCad's plain reader and writer (PCB_IO_MGR.Load/Save) are used, with no connectivity
    (pcbnew.LoadBoard/SaveBoard's would give copper under a moved pad that pad's net), and
    only `dst_path` is written, no project files. Returns {moved, flipped}.

    The older argument order write_poses(src_path, poses, dst_path) is also accepted.
    """
    if isinstance(dst_path, (dict, list, tuple)) and not isinstance(poses, (dict, list, tuple)):
        dst_path, poses = poses, dst_path
    items = _pose_list(poses)
    for p in items:
        if p["side"] not in ("F", "B"):
            raise ValueError(f"side must be 'F' or 'B': {p}")
        p["x"], p["y"], p["rot"] = float(p["x"]), float(p["y"]), transform.norm_deg(p["rot"])
    with tempfile.TemporaryDirectory(prefix="kae-poses-", dir=_tmpdir()) as d:
        pj = os.path.join(d, "poses.json")
        with open(pj, "w") as f:
            json.dump(items, f)
        flags = ["--allow-locked"] if allow_locked else []
        return _run("write-poses", lambda out: [_abs(src_path), pj, out, _abs(dst_path), *flags], timeout)


def resave(path_in, path_out, timeout=900):
    """pcbnew load + plain save, nothing changed (the baseline for structural diffs)."""
    return _run("resave", lambda out: [_abs(path_in), out, _abs(path_out)], timeout)


# ----------------------------------------------------------------------------- routing
def export_dsn(path, dsn_path, probes=True, timeout=900):
    """KiCad's Specctra DSN export of `path` (loaded with its project and design rules) to
    `dsn_path`, plus what the DSN leaves out (pcbnew_bridge.route_info): design settings,
    net classes, pads with their DSN pin ids, copper graphics, edges, zones and, with
    `probes`, KiCad's rule engine evaluated per net and copper layer."""
    flags = [] if probes else ["--no-probes"]
    return _run("export-dsn", lambda out: [_abs(path), _abs(dsn_path), out, *flags], timeout)


def import_ses(path, ses_path, dst_path, timeout=900):
    """KiCad's Specctra session import into `path`, written to `dst_path` with the plain
    writer (unlocked routing is replaced, locked routing kept). Returns {routing}."""
    return _run("import-ses", lambda out: [_abs(path), _abs(ses_path), out, _abs(dst_path)], timeout)


def edit_routing(path, dst_path, delete=(), widths=None, lock_all=False, unlock_all=False, add=(),
                 keep_locked=(), timeout=900):
    """Delete tracks and vias by uuid, set track widths ({uuid: mm}), add tracks
    ([{net, layer, a: [x, y], b: [x, y], width}], mm, canonical layer names), lock or unlock
    all routing (unlock_all leaves the uuids in `keep_locked` locked); written to `dst_path`
    with the plain writer. Returns {removed, widened, added, routing}."""
    with tempfile.TemporaryDirectory(prefix="kae-edit-", dir=_tmpdir()) as d:
        ej = os.path.join(d, "edits.json")
        with open(ej, "w") as f:
            json.dump(dict(delete=list(delete), width=dict(widths or {}), lock_all=lock_all,
                           unlock_all=unlock_all, add=list(add), keep_locked=list(keep_locked)), f)
        return _run("edit-routing", lambda out: [_abs(path), ej, out, _abs(dst_path)], timeout)


def zone_fills(path, timeout=900):
    """Every zone of `path` refilled as kicad-cli's DRC does (--refill-zones). Returns {zones:
    [{uuid, net, name, priority, clearance, teardrop, layers: {layer: [[outer ring, hole
    rings...]]}}]}."""
    return _run("zone-fills", lambda out: [_abs(path), out], timeout)


def text_shapes(path, timeout=300):
    """Glyph outlines of the visible silkscreen and copper texts of `path` (pcbnew_bridge
    text_shapes). Returns {texts: [{owner (footprint uuid or ''), uuid, layer, text, polys:
    [[outer ring, hole rings...]]}]}, board frame, mm."""
    return _run("text-shapes", lambda out: [_abs(path), out], timeout)


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


def pair_pads(pads, kpads, predicted=None):
    """Pair our pads with pcbnew's pad records of the same footprint.

    By file order when the counts and numbers agree (pcbnew keeps file order on load);
    otherwise by (uuid, number), the nearest to the predicted position first, because
    footprints may repeat a pad uuid (e.g. four pads "2" sharing one) and pcbnew's save
    re-sorts pads. predicted: [(x, y)] per pad (default: the pads' own x, y).
    Returns [(pad, record)] for the pads that found a partner."""
    if len(pads) == len(kpads) and all(p.number == q["number"] for p, q in zip(pads, kpads)):
        if len({p.uuid for p in pads}) == len(pads) and all(p.uuid == q["uuid"] for p, q in zip(pads, kpads)):
            return list(zip(pads, kpads))
        if predicted is None:
            return list(zip(pads, kpads))
    groups = {}
    for q in kpads:
        groups.setdefault((q["uuid"], q["number"]), []).append(q)
        groups.setdefault(("", q["number"]), []).append(q)
    used = set()
    out = []
    for i, p in enumerate(pads):
        px, py = predicted[i] if predicted is not None else (p.x, p.y)
        cands = [q for q in groups.get((p.uuid, p.number), []) if id(q) not in used] or \
                [q for q in groups.get(("", p.number), []) if id(q) not in used]
        if not cands:
            continue
        q = min(cands, key=lambda q: (q["x"] - px) ** 2 + (q["y"] - py) ** 2)
        used.add(id(q))
        out.append((p, q))
    return out


def _has_curves(fp, which):
    """Whether a library-frame courtyard has polygonized arcs: three or more vertices
    turning by less than 20 degrees (straight outlines turn by 45 or 90)."""
    polys = fp.courtyard if which == "own" else fp.courtyard_back
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            c = np.asarray(ring.coords)[:-1]
            if len(c) < 5:
                continue
            d = np.diff(np.vstack([c, c[:1]]), axis=0)
            a = np.arctan2(d[:, 1], d[:, 0])
            turn = np.abs((np.diff(np.concatenate([a, a[:1]])) + np.pi) % (2 * np.pi) - np.pi)
            if np.count_nonzero((turn > 1e-6) & (turn < np.radians(20))) >= 3:
                return True
    return False


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
    deflate = transform.KICAD_COURTYARD_DEFLATE
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
        for p, q in pair_pads(fp.pads, kp):
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
                ours = transform.courtyard(fp, which=which, deflate=deflate)
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
