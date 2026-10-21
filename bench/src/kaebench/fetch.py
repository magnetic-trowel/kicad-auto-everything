# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch manifest boards at their pinned commit into a local cache."""
import email.utils
import hashlib
import itertools
import json
import random
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from . import boardfiles, tools
from .manifest import import_format, project_paths


def _raw_url(repo, commit, path):
    u = urllib.parse.urlparse(repo)
    slug = u.path.strip("/").removesuffix(".git")
    qpath = urllib.parse.quote(path)
    if u.netloc == "github.com":
        return f"https://raw.githubusercontent.com/{slug}/{commit}/{qpath}"
    if u.netloc == "gitlab.com" or u.netloc.startswith("gitlab.") or u.netloc == "gitlab.fabcloud.org":
        return f"https://{u.netloc}/{slug}/-/raw/{commit}/{qpath}"
    if u.netloc == "codeberg.org":
        return f"https://codeberg.org/{slug}/raw/commit/{commit}/{qpath}"
    return None


# Rate limiting: GitLab instances (gitlab.fabcloud.org allows 60 unauthenticated raw GETs a
# minute) answer 429 when many worker threads fetch at once. A 429/5xx makes every thread hold
# off that host until the Retry-After time, then retry; a file is given up after RETRY_BUDGET s.
RETRY_CODES = {429, 502, 503, 504}
RETRY_BUDGET = 600
_hold_lock = threading.Lock()
_hold_until = {}  # host -> time.monotonic() before which no request is sent


def _retry_after(headers, attempt):
    """Seconds to wait: the Retry-After header (seconds or HTTP date), else 2**attempt; capped."""
    v = (headers or {}).get("Retry-After")
    delay = None
    if v:
        try:
            delay = float(v)
        except ValueError:
            try:
                delay = email.utils.parsedate_to_datetime(v).timestamp() - time.time()
            except (TypeError, ValueError):
                pass
    if delay is None:
        delay = 2 ** attempt
    return min(max(delay, 1), 120) + random.uniform(0, 5)


def _download(url, dest, timeout=120):
    host = urllib.parse.urlparse(url).netloc
    req = urllib.request.Request(url, headers={"User-Agent": "kaebench"})
    deadline = time.monotonic() + RETRY_BUDGET
    for attempt in itertools.count():
        with _hold_lock:
            wait = _hold_until.get(host, 0) - time.monotonic()
        if wait > 0:
            time.sleep(wait + random.uniform(0, 2))  # jitter so held threads don't return at once
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            if e.code not in RETRY_CODES or time.monotonic() >= deadline:
                raise
            delay = min(_retry_after(e.headers, attempt), max(deadline - time.monotonic(), 0))
            with _hold_lock:
                _hold_until[host] = max(_hold_until.get(host, 0), time.monotonic() + delay)


def _git_fetch(repo, commit, paths, dest_dir):
    """Fallback for hosts without raw URLs: shallow fetch of one commit."""
    got = {}
    with tempfile.TemporaryDirectory() as tmp:
        run = lambda *a: subprocess.run(["git", "-C", tmp, *a], check=True, capture_output=True, timeout=600)
        run("init", "-q")
        run("remote", "add", "origin", repo)
        run("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", commit)
        for key, p in paths.items():
            r = subprocess.run(["git", "-C", tmp, "show", f"{commit}:{p}"], capture_output=True, timeout=300)
            if r.returncode == 0:
                out = dest_dir / Path(p).name
                out.write_bytes(r.stdout)
                got[key] = out
    return got


def _zip_fetch(entry, paths, dest_dir):
    """Download a design-file archive, check archive_sha256, extract the board and project files.

    Zip and tar (optionally compressed) archives are supported. A download that is neither
    is taken to be the board file itself (e.g. a single Zenodo file).
    """
    archive = dest_dir / "archive.zip"
    if not _download(entry["repo"], archive):
        raise FileNotFoundError(f"{entry['id']}: archive {entry['repo']} not found")
    digest = sha256(archive)
    if digest != entry["archive_sha256"]:
        raise ValueError(f"{entry['id']}: archive sha256 mismatch "
                         f"(manifest {entry['archive_sha256'][:12]}, fetched {digest[:12]})")
    got = {}
    if not zipfile.is_zipfile(archive) and tarfile.is_tarfile(archive):
        with tarfile.open(archive) as t:
            for m in t:
                key = next((k for k, p in paths.items() if p == m.name), None)
                if key and m.isfile():
                    out = dest_dir / Path(m.name).name
                    with t.extractfile(m) as f, open(out, "wb") as o:
                        shutil.copyfileobj(f, o)
                    got[key] = out
        archive.unlink()
        return got
    if not zipfile.is_zipfile(archive):
        out = dest_dir / Path(entry["pcb_path"]).name
        archive.rename(out)
        return {"kicad_pcb": out}
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        for key, p in paths.items():
            if p in names:
                out = dest_dir / Path(p).name
                out.write_bytes(z.read(p))
                got[key] = out
    archive.unlink()
    return got


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _import_board(src, fmt, dest_dir, timeout=1800):
    """Convert an Eagle/Allegro/Altium/PADS/... board to .kicad_pcb with `kicad-cli pcb import`.

    pcb_sha256 stays the hash of the upstream source file; the import is redone locally.
    """
    out = Path(dest_dir) / (Path(src).stem + ".kicad_pcb")
    cmd = [*tools.kicad_cli(), "pcb", "import", "--format", fmt, "-o", str(out), str(src)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise tools.ToolError(f"pcb import timed out after {timeout}s")
    if r.returncode or not out.exists():
        raise tools.ToolError(f"pcb import ({fmt}) failed (rc={r.returncode}): {(r.stdout + r.stderr)[-400:]}")
    text = out.read_text(errors="replace")
    fixed, _ = boardfiles.art_zones_to_polys(boardfiles.fix_unloadable(text))
    if fixed != text:
        out.write_text(fixed)
    return out


def fetch(entry, cache_dir, force=False):
    """Fetch board + project files into cache_dir/<id>/. Returns a dict of local paths."""
    dest = Path(cache_dir) / entry["id"]
    meta_path = dest / "fetch.json"
    if meta_path.exists() and not force:
        return json.loads(meta_path.read_text())
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    paths = {"kicad_pcb": entry["pcb_path"], **project_paths(entry)}
    got = {}
    raw = None if entry.get("archive_sha256") else _raw_url(entry["repo"], entry["commit"], entry["pcb_path"])
    if entry.get("archive_sha256"):
        got = _zip_fetch(entry, paths, dest)
    elif raw:
        for key, p in paths.items():
            out = dest / Path(p).name
            if _download(_raw_url(entry["repo"], entry["commit"], p), out):
                got[key] = out
        if "kicad_pcb" not in got:
            # the raw URL is guessed from the host name, which goes stale when a project moves
            # (gitlab.cba.mit.edu redirects to a Forgejo with other URLs); git follows redirects
            try:
                got = _git_fetch(entry["repo"], entry["commit"], paths, dest) or got
            except subprocess.SubprocessError:
                pass
    else:
        got = _git_fetch(entry["repo"], entry["commit"], paths, dest)
    if "kicad_pcb" not in got:
        raise FileNotFoundError(f"{entry['id']}: {entry['pcb_path']} not found at {entry['commit']}")
    digest = sha256(got["kicad_pcb"])
    want = entry.get("pcb_sha256")
    if want and want != digest:
        raise ValueError(f"{entry['id']}: sha256 mismatch (manifest {want[:12]}, fetched {digest[:12]})")
    fmt = import_format(entry["pcb_path"])
    if fmt:
        got["source_pcb"] = got["kicad_pcb"]
        got["kicad_pcb"] = _import_board(got["source_pcb"], fmt, dest)
    else:
        text = got["kicad_pcb"].read_text(errors="replace")
        fixed = boardfiles.fix_unloadable(text)
        if fixed != text:
            got["kicad_pcb"].write_text(fixed)
    meta = {k: str(v) for k, v in got.items()}
    meta.update(id=entry["id"], pcb_sha256=digest, repo=entry["repo"], commit=entry.get("commit"))
    meta_path.write_text(json.dumps(meta, indent=1))
    return meta
