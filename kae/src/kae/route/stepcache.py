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
import fcntl
import gzip
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
#
#   entries/<k2>/<key>.json   an entry's meta: its files as blob hashes (mtime: last use, for LRU)
#   blobs/<h2>/<sha>.gz       files, gzip-compressed, deduplicated by the sha256 of their content
#   locks/<key>               flock: shared while a job restores the entry, exclusive to evict it
#   lock, size.json           the store's write lock and its size ledger (bytes of blobs + entries)
#
# Every write takes the store's lock, adds its new bytes to the ledger and, past the cap
# (KAE_STEP_CACHE_MAX_GB, default 50), evicts the least recently used entries that no job is
# reading down to 90% of it, then the blobs no entry still names. An entry larger than 5% of
# the cap is not stored.

MAX_GB = 50.0
TARGET = 0.9        # eviction goes down to this share of the cap
MAX_ENTRY = 0.05    # an entry above this share of the cap is not stored


def cap_bytes():
    return int(float(os.environ.get("KAE_STEP_CACHE_MAX_GB") or MAX_GB) * 2 ** 30)


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _meta_path(key):
    return root() / "entries" / key[:2] / f"{key}.json"


def _blob(sha):
    return root() / "blobs" / sha[:2] / f"{sha}.gz"


class _Flock:
    def __init__(self, path, mode):
        self.path, self.mode, self.f = Path(path), mode, None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a")
        try:
            fcntl.flock(self.f, self.mode)
        except OSError:
            self.f.close()
            self.f = None
        return self.f is not None

    def __exit__(self, *exc):
        if self.f is not None:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()


def get(key):
    """An entry's meta, None on a miss (no lock: use reading() to restore it)."""
    if not enabled():
        return None
    try:
        return json.loads(_meta_path(key).read_text())
    except (OSError, ValueError):
        return None


class reading:
    """`with reading(key) as meta:` the entry (None on a miss), kept from eviction while the block
    runs; a use marks it recently used."""

    def __init__(self, key):
        self.key, self.lock = key, None

    def __enter__(self):
        if not enabled():
            return None
        self.lock = _Flock(root() / "locks" / self.key, fcntl.LOCK_SH)
        self.lock.__enter__()
        meta = get(self.key)
        if meta is not None:
            try:
                os.utime(_meta_path(self.key))
            except OSError:
                pass
        return meta

    def __exit__(self, *exc):
        if self.lock is not None:
            self.lock.__exit__()


def put(key, meta, files, wd=None):
    """Store an entry: `meta` (JSON-able) and `files` {name: path}, `wd` replaced by WD in the
    files, compressed and deduplicated. The first writer of a key wins (a concurrent job's entry
    is kept). Returns True when this call stored it."""
    if not enabled():
        return False
    r = root()
    tmps, names = {}, {}
    try:
        (r / "tmp").mkdir(parents=True, exist_ok=True)
        for name, src in sorted(files.items()):
            b = Path(src).read_bytes()
            if wd:
                b = _sub(b, wd, WD)
            sha = hashlib.sha256(b).hexdigest()
            names[name] = sha
            if sha not in tmps and not _blob(sha).exists():
                t = r / "tmp" / f"{sha}.{os.getpid()}.{uuid.uuid4().hex[:8]}"
                t.write_bytes(gzip.compress(b, 6))
                tmps[sha] = t
        doc = json.dumps(dict(meta, files=names, key=key, schema=SCHEMA,
                              stored=time.strftime("%Y-%m-%dT%H:%M:%S")), indent=1).encode()
        if sum(t.stat().st_size for t in tmps.values()) + len(doc) > MAX_ENTRY * cap_bytes():
            return False   # one entry too large for the cap: not cached
        with _Flock(r / "lock", fcntl.LOCK_EX):
            if _meta_path(key).exists():
                return False
            added = len(doc)
            for sha, t in tmps.items():
                dst = _blob(sha)
                if dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                added += t.stat().st_size
                os.rename(t, dst)
            known = (root() / "size.json").exists()
            _atomic_write(_meta_path(key), doc)
            size = _ledger() + added if known else _scan()[0]
            if size > cap_bytes():
                size = _evict(int(TARGET * cap_bytes()))
            _atomic_write(r / "size.json", json.dumps(dict(bytes=size)).encode())
        return True
    except OSError:
        return False
    finally:
        for t in tmps.values():
            if t.exists():
                t.unlink()


def _ledger():
    try:
        return int(json.loads((root() / "size.json").read_text())["bytes"])
    except (OSError, ValueError, KeyError):
        return _scan()[0]


def _scan():
    """(bytes, entries {key: (mtime, path, blobs)}, blobs {sha: (bytes, path)}) by walking the store."""
    r, entries, blobs, total = root(), {}, {}, 0
    for p in (r / "entries").glob("*/*.json"):
        try:
            st, meta = p.stat(), json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        entries[p.stem] = (st.st_mtime, p, set(meta.get("files", {}).values()))
        total += st.st_size
    for p in (r / "blobs").glob("*/*.gz"):
        try:
            blobs[p.name[:-3]] = (p.stat().st_size, p)
            total += blobs[p.name[:-3]][0]
        except OSError:
            pass
    return total, entries, blobs


def _evict(target):
    """With the store's lock held: drop least recently used entries that no job is reading, and
    the blobs no remaining entry names, until the store is at most `target` bytes. Returns its size."""
    total, entries, blobs = _scan()
    refs = {}
    for _, _, bs in entries.values():
        for b in bs:
            refs[b] = refs.get(b, 0) + 1
    for b, (n, p) in list(blobs.items()):   # orphans (a write that died between blob and entry)
        if not refs.get(b) and time.time() - p.stat().st_mtime > 3600:
            p.unlink(missing_ok=True)
            total -= n
    for key, (_, path, bs) in sorted(entries.items(), key=lambda kv: kv[1][0]):
        if total <= target:
            break
        with _Flock(root() / "locks" / key, fcntl.LOCK_EX | fcntl.LOCK_NB) as free:
            if not free:
                continue           # a job is restoring it
            try:
                total -= path.stat().st_size
                path.unlink()
            except OSError:
                continue
        (root() / "locks" / key).unlink(missing_ok=True)
        for b in bs:
            refs[b] -= 1
            if refs[b] == 0 and b in blobs:
                blobs[b][1].unlink(missing_ok=True)
                total -= blobs[b][0]
    return total


def stats():
    """The store: bytes (walked), the ledger, the cap, entries per step, blobs."""
    if not enabled() or not root().exists():
        return dict(bytes=0, entries=0)
    total, entries, blobs = _scan()
    steps = {}
    for key in entries:
        m = get(key) or {}
        steps[m.get("step", "?")] = steps.get(m.get("step", "?"), 0) + 1
    return dict(bytes=total, gb=round(total / 2 ** 30, 3), ledger=_ledger(), cap_gb=round(cap_bytes() / 2 ** 30, 2),
                entries=len(entries), blobs=len(blobs), steps=steps)


def size_gb():
    """The store's size by its ledger (cheap), for run reports."""
    return round(_ledger() / 2 ** 30, 3) if enabled() and root().exists() else 0.0


def prune(max_gb=None):
    """Evict down to `max_gb` (default: the cap's eviction target). Returns the size in bytes."""
    target = int(max_gb * 2 ** 30) if max_gb is not None else int(TARGET * cap_bytes())
    with _Flock(root() / "lock", fcntl.LOCK_EX):
        size = _evict(target)
        _atomic_write(root() / "size.json", json.dumps(dict(bytes=size)).encode())
    return size


def restore(meta, dests, wd=None):
    """Write an entry's files to `dests` {name: path} (WD replaced by `wd`). Call it inside
    reading(); raises OSError when a blob is missing."""
    for name, dst in dests.items():
        b = gzip.decompress(_blob(meta["files"][name]).read_bytes())
        if wd:
            b = b.replace(WD.encode(), str(wd).encode())
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b)


def tail(text, n=4000):
    return (text or "")[-n:]


# ---- fork points --------------------------------------------------------------------------
#
# kae.route.bridge saves an attempt's board at the stage boundaries an A/B branches at: "routed"
# (Freerouting's session imported; the raw session too), "repaired" (repair rounds and last mile)
# and "final" (the attempt's output). The key is conservative: the input board and its project
# files, the seed, the time budget, the caller's options, the KAE_* environment, the failure
# history it reads and the whole kae source (code_id), so a hit is the same attempt by the same
# code. A method that knows its change lies past a stage can look up the control arm's point with
# that arm's code id (find_fork(..., code=...)) and continue from it.

_NOT_SETTINGS = ("KAE_STEP_CACHE", "KAE_STEP_CACHE_MAX_GB", "KAE_CHARGE_FILE", "KAE_ROUTE_HISTORY", "KAE_HOME",
                 "KAE_FR_LOCKDIR", "KAE_FR_SLOTS", "KAE_KICAD_WRAP", "KAE_KICAD_CLI", "KAE_KICAD_PYTHON",
                 "KAE_RESUME", "KAE_WORKERS", "KAE_DRC_TIMEOUT")
_code = {}


def code_id(src=None):
    """sha256 over the kae package's Python sources (kae/src/kae/**/*.py)."""
    src = Path(src or Path(__file__).resolve().parents[1])
    if src not in _code:
        h = hashlib.sha256()
        for f in sorted(src.rglob("*.py")):
            h.update(str(f.relative_to(src)).encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
        _code[src] = h.hexdigest()
    return _code[src]


def fork_context(input_path, seed, time_s, opts):
    """What a route attempt's fork points are keyed by (None when the cache is off)."""
    if not enabled():
        return None
    b = Path(input_path)
    files = {e: file_sha(b.with_suffix(e)) for e in (".kicad_pcb", ".kicad_pro", ".kicad_dru") if b.with_suffix(e).exists()}
    hist = os.environ.get("KAE_ROUTE_HISTORY")
    env = {k: v for k, v in os.environ.items() if k.startswith("KAE_") and k not in _NOT_SETTINGS}
    if env.get("KAE_BRIDGE_FREEROUTING"):
        try:
            env["KAE_BRIDGE_FREEROUTING"] = tool_sha(env["KAE_BRIDGE_FREEROUTING"])
        except OSError:
            pass
    return dict(input=files, seed=seed, time_s=time_s, env=env,
                opts=json.loads(json.dumps(opts or {}, sort_keys=True, default=str)),
                history=file_sha(hist) if hist and Path(hist).exists() else None, code=code_id())


def fork_key(ctx, stage, code=None):
    return make_key(f"fork:{stage}", dict(ctx, code=code or ctx["code"]))


def save_fork(ctx, stage, files, elapsed_s, report=None):
    """Store fork point `stage` of an attempt: `files` {name: path}, the charged seconds spent to
    reach it and its report. A no-op without the cache; never fails the attempt."""
    if ctx is None:
        return False
    try:
        fs = {n: p for n, p in files.items() if p and Path(p).exists()}
        if report is not None:
            rp = Path(next(iter(fs.values()))).with_name(f".fork-{stage}-report.json")
            rp.write_text(json.dumps(report, default=str))
            fs["report"] = rp
        ok = put(fork_key(ctx, stage), dict(step=f"fork:{stage}", seconds=round(elapsed_s, 3)), fs)
        if report is not None:
            rp.unlink(missing_ok=True)
        return ok
    except (OSError, StopIteration, TypeError, ValueError):
        return False


def find_fork(ctx, stage, code=None):
    """The meta of a saved fork point (restore it inside reading(fork_key(...))), None if there is none."""
    return get(fork_key(ctx, stage, code)) if ctx is not None else None


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
    with reading(key) as meta:
        if meta is not None and meta.get("seconds", 0) <= timeout:
            side = {n: wd / n for n in meta.get("side", [])}
            try:
                restore(meta, {**outputs, **{f"side:{n}": p for n, p in side.items()}}, wd)
            except OSError:
                meta = None
            if meta is not None:
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


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="stepcache", description="kae's step cache (KAE_STEP_CACHE)")
    ap.add_argument("cmd", choices=("stats", "prune"))
    ap.add_argument("--dir", help="the cache directory (default: $KAE_STEP_CACHE)")
    ap.add_argument("--max-gb", type=float, help="prune: down to this size (default: 90%% of the cap)")
    a = ap.parse_args(argv)
    if a.dir:
        os.environ["KAE_STEP_CACHE"] = a.dir
    if not enabled():
        ap.error("no cache: set KAE_STEP_CACHE or pass --dir")
    if a.cmd == "prune":
        prune(a.max_gb)
    print(json.dumps(stats(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
