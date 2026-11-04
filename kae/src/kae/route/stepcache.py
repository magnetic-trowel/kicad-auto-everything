# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Content-addressed cache of expensive deterministic steps (Freerouting, kicad-cli DRC).

Off unless KAE_STEP_CACHE names a directory (local disk, e.g. /var/tmp/$USER/step-cache).
Two arms of an A/B that share their early steps then compute them once: the second arm
replays the first one's outputs.

Key: sha256 over a canonical JSON of everything the step reads: the input files' bytes (the
work directory's path replaced by a placeholder, so two work directories share a key), the
argv with its paths normalised, the tool's identity (Freerouting: its jars' sha256; KiCad: its
version), the environment that matters and SCHEMA. Value: the output files, the exit code,
the stdout/stderr tail and the measured duration. Entries are directories written under
tmp/ and renamed into place, so concurrent jobs never see half an entry; the first writer of
a key wins. Only stdlib: tools/kaeres/restart.py loads this file by path.

Time is charged, not saved: a hit costs its recorded duration. Each step appends a record to
$KAE_CHARGE_FILE (one JSON line: step, hit, charged_s, real_s), and a hit advances this
process's time.monotonic by what it saved (install_clock), so every deadline in the process
counts the step as if it had run. restart.py reads its attempts' charge files and holds a
slot until the attempt's charged time is spent (see restart.py). Results therefore do not
change with the cache on; only wall time and CPU do.

A step is cached only when it is deterministic under the settings used: Freerouting only
when it stopped by itself (not at its job timeout, nor its optimizer at its own), and a hit
only when the recorded run fits in the caller's time limit, so the uncached run would also
have finished on its own; DRC only when it wrote its report within its timeout.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

SCHEMA = 1
WD = "<WD>"          # the work directory's path in keys and stored files
_real_monotonic = time.monotonic
_offset = 0.0
AUTO_ADVANCE = True   # a hit moves this process's clock on; restart.py holds instead (see there)
STATS = dict(hits=0, misses=0, uncacheable=0, charged_s=0.0, saved_s=0.0)
_sha_memo = {}


def root():
    """The cache directory (KAE_STEP_CACHE), None when the cache is off."""
    d = os.environ.get("KAE_STEP_CACHE")
    return Path(d) if d else None


def enabled():
    return root() is not None


# ---- clock --------------------------------------------------------------------------------

def _monotonic():
    return _real_monotonic() + _offset


def install_clock():
    """Make time.monotonic count charged time: real time plus what cache hits saved (0 until a
    hit). Monotonic, since the offset only grows. Modules must call time.monotonic() through
    the module (kae.route does); `from time import monotonic` copies are not affected."""
    if time.monotonic is not _monotonic:
        time.monotonic = _monotonic


def advance(seconds):
    """Move this process's clock on by `seconds` (a hit's saved time, or a restart wrapper's
    fast-forward when nothing is computing)."""
    global _offset
    if seconds > 0:
        install_clock()
        _offset += seconds


def offset():
    return _offset


# ---- keys ---------------------------------------------------------------------------------

def _sub(data, path, ph):
    """`data` (str or bytes) with the directory `path` replaced by `ph` where it is a whole path
    component (/w/a, not the start of /w/abc)."""
    if isinstance(data, bytes):
        return re.sub(re.escape(str(path).encode()) + rb"(?![^/\s\"')])", ph.encode(), data)
    return re.sub(re.escape(str(path)) + r"(?![^/\s\"')])", ph.replace("\\", r"\\"), data)


def file_sha(path, wd=None):
    """sha256 of a file's bytes, with `wd` (a directory path) replaced by WD. Never memoised: a
    file rewritten within one mtime tick at the same size would keep a stale key."""
    b = Path(path).read_bytes()
    return hashlib.sha256(_sub(b, wd, WD) if wd else b).hexdigest()


def tool_sha(exe):
    """Identity of a Freerouting command's program: sha256 over a native bundle's launcher and
    jars (bin/freerouting + lib/**/*.jar), or over the file itself (a jar, a binary)."""
    p = Path(exe).resolve()
    rootdir = p.parent.parent if p.parent.name == "bin" else None
    files = [p] + (sorted(rootdir.glob("lib/**/*.jar")) if rootdir else [])
    memo = tuple((str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in files)   # release files: immutable
    if memo not in _sha_memo:
        h = hashlib.sha256()
        for f in files:
            h.update(f.name.encode() + b"\0" + file_sha(f).encode())
        _sha_memo[memo] = h.hexdigest()
    return _sha_memo[memo]


def kicad_version(prefix):
    """kicad-cli's version for a command prefix (wrapper + kicad-cli), memoised on disk by the
    prefix and the modification times of the paths in it (an updated container is a new tool)."""
    stamp = [(a, os.stat(a).st_mtime_ns) if os.path.exists(a) else (a, None) for a in prefix]
    k = hashlib.sha256(json.dumps(stamp).encode()).hexdigest()[:24]
    f = root() / "versions" / f"kicad-{k}" if root() else None
    if f and f.exists():
        return f.read_text().strip()
    r = subprocess.run([*prefix, "version"], capture_output=True, text=True, timeout=300)
    v = (r.stdout or "").strip().splitlines()[-1:] or [""]
    v = v[0]
    if r.returncode != 0 or not v:
        raise RuntimeError(f"kicad-cli version failed (rc {r.returncode})")
    if f:
        _atomic_write(f, v.encode())
    return v


def make_key(step, parts):
    """sha256 key of a step: its name, SCHEMA and `parts` (JSON-able) in canonical form."""
    blob = json.dumps(dict(schema=SCHEMA, step=step, parts=parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def norm_argv(argv, wd, extra=()):
    """argv with the work directory and other paths (`extra`: (path, placeholder)) replaced."""
    out = []
    for a in map(str, argv):
        for p, ph in extra:
            a = _sub(a, p, ph)
        out.append(_sub(a, wd, WD) if wd else a)
    return out


# ---- store --------------------------------------------------------------------------------

def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _entry(key):
    return root() / key[:2] / key


def get(key):
    """The entry's meta (with "dir": its directory), None on a miss."""
    if not enabled():
        return None
    d = _entry(key)
    try:
        meta = json.loads((d / "meta.json").read_text())
    except (OSError, ValueError):
        return None
    meta["dir"] = d
    return meta


def put(key, meta, files, wd=None):
    """Store an entry: `meta` (JSON-able) and `files` {name: path}, `wd` replaced by WD in the
    files. Written into tmp/ and renamed into place: atomic, and a key already stored (by a
    concurrent job) is kept. Returns True when this call stored it."""
    if not enabled():
        return False
    tmp = root() / "tmp" / f"{key}.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    try:
        (tmp / "files").mkdir(parents=True)
        names = {}
        for i, (name, src) in enumerate(sorted(files.items())):
            b = Path(src).read_bytes()
            if wd:
                b = _sub(b, wd, WD)
            (tmp / "files" / f"f{i}").write_bytes(b)
            names[name] = f"f{i}"
        (tmp / "meta.json").write_text(json.dumps(dict(meta, files=names, key=key, schema=SCHEMA,
                                                       stored=time.strftime("%Y-%m-%dT%H:%M:%S")), indent=1))
        dst = _entry(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(tmp, dst)
            return True
        except OSError:   # stored meanwhile by another job: the same deterministic result
            return False
    except OSError:
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def restore(meta, dests, wd=None):
    """Write an entry's files to `dests` {name: path} (WD replaced by `wd`)."""
    for name, dst in dests.items():
        b = (meta["dir"] / "files" / meta["files"][name]).read_bytes()
        if wd:
            b = b.replace(WD.encode(), str(wd).encode())
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b)


def tail(text, n=4000):
    return (text or "")[-n:]


# ---- charges ------------------------------------------------------------------------------

def charge(step, hit, charged_s, real_s, key=None, cacheable=True):
    """Account one step: counters, a line in $KAE_CHARGE_FILE, and on a hit the clock moved on
    by the time it saved (charged_s - real_s)."""
    saved = max(0.0, charged_s - real_s) if hit else 0.0
    STATS["hits" if hit else ("misses" if cacheable else "uncacheable")] += 1
    STATS["charged_s"] += charged_s
    STATS["saved_s"] += saved
    if hit and AUTO_ADVANCE:
        advance(saved)
    f = os.environ.get("KAE_CHARGE_FILE")
    if f:
        line = json.dumps(dict(step=step, hit=hit, cacheable=cacheable, charged_s=round(charged_s, 3),
                               real_s=round(real_s, 3), saved_s=round(saved, 3), key=key and key[:16])) + "\n"
        try:
            fd = os.open(f, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, line.encode())   # one write under PIPE_BUF: atomic among appenders
            finally:
                os.close(fd)
        except OSError:
            pass
    return saved


def charges(path):
    """Totals of a charge file: hits, misses, uncacheable, charged_s, real_s, saved_s."""
    t = dict(hits=0, misses=0, uncacheable=0, charged_s=0.0, real_s=0.0, saved_s=0.0)
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return t
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue   # a line being written
        t["hits" if r.get("hit") else ("misses" if r.get("cacheable", True) else "uncacheable")] += 1
        for k in ("charged_s", "real_s", "saved_s"):
            t[k] += float(r.get(k) or 0.0)
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in t.items()}


# ---- a cached command ---------------------------------------------------------------------

class Result:
    def __init__(self, returncode, stdout, stderr, hit, seconds, saved=0.0):
        self.returncode, self.stdout, self.stderr, self.hit, self.seconds = returncode, stdout, stderr, hit, seconds
        self.saved = saved   # charged less real seconds of a hit


def kicad_inputs(board):
    """What a kicad-cli DRC of `board` reads: the board, its project files and library tables,
    and KiCad's advanced config (thread count) in KICAD_CONFIG_HOME."""
    b = Path(board)
    fs = [b, *(b.with_suffix(e) for e in (".kicad_pro", ".kicad_dru")), b.parent / "fp-lib-table"]
    cfg = os.environ.get("KICAD_CONFIG_HOME")
    return fs + (sorted(Path(cfg).glob("*/kicad_advanced")) if cfg else [])


def _listing(d):
    out = {}
    try:
        for p in Path(d).iterdir():
            if p.is_file():
                st = p.stat()
                out[p.name] = (st.st_size, st.st_mtime_ns)
    except OSError:
        pass
    return out


def run(step, argv, *, inputs, outputs, wd, timeout, tool, cwd=None):
    """subprocess.run(argv, capture_output, text, timeout) through the cache. `inputs`: files the
    command reads (missing ones count as absent); `outputs` {name: path}: files it must write
    (all of them, or it is not stored); `wd`: the directory whose path is normalised, whose
    other new or changed files (side effects, e.g. KiCad's .kicad_prl) are stored and replayed
    too; `tool`: the program's identity. A hit needs its recorded duration within `timeout`
    (the uncached run would have finished too) and is charged that duration. Raises
    subprocess.TimeoutExpired like subprocess.run."""
    wd = Path(wd).resolve()
    parts = dict(argv=norm_argv(argv, wd), tool=tool,
                 inputs={norm_argv([p], wd)[0]: (file_sha(p, wd) if Path(p).exists() else None) for p in map(str, inputs)})
    key = make_key(step, parts)
    t0 = _real_monotonic()
    meta = get(key)
    if meta is not None and meta.get("seconds", 0) <= timeout:
        side = {n: wd / n for n in meta.get("side", [])}
        restore(meta, {**outputs, **{f"side:{n}": p for n, p in side.items()}}, wd)
        saved = charge(step, True, meta["seconds"], _real_monotonic() - t0, key)
        return Result(meta["rc"], meta.get("stdout", ""), meta.get("stderr", ""), True, meta["seconds"], saved)
    before = _listing(wd)
    t1 = _real_monotonic()
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, errors="replace")
    except subprocess.TimeoutExpired:
        charge(step, False, _real_monotonic() - t1, _real_monotonic() - t1, key, cacheable=False)
        raise
    dt = _real_monotonic() - t1
    outs = {n: Path(p) for n, p in outputs.items()}
    ok = all(p.exists() for p in outs.values())
    if ok:
        after = _listing(wd)
        names = {p.name for p in outs.values() if p.parent.resolve() == wd}
        side = sorted(n for n, s in after.items() if before.get(n) != s and n not in names)
        put(key, dict(step=step, rc=r.returncode, seconds=round(dt, 3), stdout=tail(r.stdout), stderr=tail(r.stderr),
                      side=side, parts=parts),
            {**outs, **{f"side:{n}": wd / n for n in side}}, wd)
    charge(step, False, dt, dt, key, cacheable=ok)
    return Result(r.returncode, r.stdout, r.stderr, False, dt)
