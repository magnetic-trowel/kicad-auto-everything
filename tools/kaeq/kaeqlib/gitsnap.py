# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Git snapshots: a job runs a frozen copy of the submitter's tree in its own worktree."""
import os
import subprocess
from .store import jobdir


def git(root, *args, env=None):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, env=env)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "git failed")
    return r.stdout.strip()


def git_snapshot(cwd):
    """Freeze the working tree (tracked + untracked, not ignored) as a commit; None outside a git repo."""
    try:
        root = git(cwd, "rev-parse", "--show-toplevel")
        head = git(root, "rev-parse", "HEAD")
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        idx = os.path.join(git(root, "rev-parse", "--absolute-git-dir"), f"kaeq-index-{os.getpid()}")
        env = dict(os.environ, GIT_INDEX_FILE=idx)
        try:
            git(root, "read-tree", "HEAD", env=env)
            git(root, "add", "-A", env=env)
            tree = git(root, "write-tree", env=env)
        finally:
            if os.path.exists(idx):
                os.unlink(idx)
        sha = git(root, "commit-tree", tree, "-p", head, "-m", "kaeq snapshot")
        git(root, "update-ref", f"refs/kaeq/{sha}", sha)  # keeps it from being gc'd
        return dict(root=root, branch=branch, sha=sha, rel=os.path.relpath(os.path.realpath(cwd), os.path.realpath(root)))
    except (RuntimeError, OSError):
        return None


def drop_worktree(j):
    if j["sha"] and j["root"]:
        src = os.path.join(jobdir(j["id"]), "src")
        subprocess.run(["git", "-C", j["root"], "worktree", "remove", "--force", src], capture_output=True)
        subprocess.run(["git", "-C", j["root"], "worktree", "prune"], capture_output=True)


def ref(j):
    return f"{os.path.basename(j['root'])}@{j['branch']}:{j['sha'][:7]}" if j["sha"] else "live"
