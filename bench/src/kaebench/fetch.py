# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch manifest boards at their pinned commit into a local cache."""
import hashlib
import json
import shutil
import subprocess
import tempfile
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


def _download(url, dest, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "kaebench"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


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

    A download that is not a zip is taken to be the board file itself (e.g. a single Zenodo file).
    """
    archive = dest_dir / "archive.zip"
    if not _download(entry["repo"], archive):
        raise FileNotFoundError(f"{entry['id']}: archive {entry['repo']} not found")
    digest = sha256(archive)
    if digest != entry["archive_sha256"]:
        raise ValueError(f"{entry['id']}: archive sha256 mismatch "
                         f"(manifest {entry['archive_sha256'][:12]}, fetched {digest[:12]})")
    got = {}
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
    # Eagle layers with no KiCad mapping (e.g. tDocu-style graphics) come out as layer
    # "UNDEFINED", which pcbnew refuses to load; they are documentation only.
    text = out.read_text(errors="replace")
    fixed = text.replace('(layer "UNDEFINED")', '(layer "Cmts.User")')
    fixed, _ = boardfiles.art_zones_to_polys(fixed)
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
    meta = {k: str(v) for k, v in got.items()}
    meta.update(id=entry["id"], pcb_sha256=digest, repo=entry["repo"], commit=entry.get("commit"))
    meta_path.write_text(json.dumps(meta, indent=1))
    return meta
