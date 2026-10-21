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
from pathlib import Path

from .manifest import project_paths


def _raw_url(repo, commit, path):
    u = urllib.parse.urlparse(repo)
    slug = u.path.strip("/").removesuffix(".git")
    qpath = urllib.parse.quote(path)
    if u.netloc == "github.com":
        return f"https://raw.githubusercontent.com/{slug}/{commit}/{qpath}"
    if u.netloc == "gitlab.com":
        return f"https://gitlab.com/{slug}/-/raw/{commit}/{qpath}"
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


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    raw = _raw_url(entry["repo"], entry["commit"], entry["pcb_path"])
    if raw:
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
    meta = {k: str(v) for k, v in got.items()}
    meta.update(id=entry["id"], pcb_sha256=digest, repo=entry["repo"], commit=entry["commit"])
    meta_path.write_text(json.dumps(meta, indent=1))
    return meta
