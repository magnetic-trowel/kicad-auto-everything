#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaeres: a results store for routing and placement methods, keyed by board.

Three kinds of record, each identified by a hash of what defines it:
- method: a runnable recipe (code commits, binary hash, adapter or command, parameters, KiCad
  version) with a human-readable name. Same recipe, same id; any change, a new id.
- run: one method on one board (output board, logs, CPU, router report), under the board.
- evaluation: one scorer on one run (kaebench DRC score, kae routed physics). A scorer is
  identified by the code it runs, so runs can be rescored without being re-run.
Experiments are views: a set of methods over a set of boards, with reports. A run that already
exists for a method on a board is reused by every later experiment.

  kaeres method add NAME --adapter freerouting --binary DIR/bin/freerouting --code router=SRC_OR_URL@REF [...]
  kaeres method add human --reference
  kaeres method list | show ID
  kaeres exp create NAME --method NAME_OR_ID [...] [--boards @FILE] [--harness REF] [--kae REF]
  kaeres exp submit NAME [--limit N] [--only ids|@FILE]    # queue one kaeq job per board that lacks runs
  kaeres exp status NAME | report NAME | install-timer NAME
  kaeres board ID                                          # every run and score of one board
  kaeres rerun RUN_DIR [--submit]                          # how to reproduce a run (or queue it again)
  kaeres index                                             # index.sqlite over every run and evaluation

Store (default ~/kae-baselines, $KAE_RESULTS): see tools/kaeres/README.md for the layout.
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import resource
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = Path(os.path.expanduser(os.environ.get("KAE_RESULTS", "~/kae-baselines")))
KAE_HOME = Path(os.path.expanduser(os.environ.get("KAE_HOME", "~/.cache/kaebench")))
CORPUS = Path(os.path.expanduser(os.environ.get("KAE_CORPUS", "~/kae-boards")))
MB = 1 << 20
AS_LIMIT = 40 * (1 << 30)  # address-space cap for the harness tree (a runaway KiCad DRC once reached 100 GB)
SCHEMA = "kaeres/1"
HARNESS_REPO = "kicad-auto-everything"
# Files whose content defines kaebench's scoring (the DRC evaluator's identity)
SCORER_PATHS = ("bench/src/kaebench/score.py", "bench/src/kaebench/tools.py", "bench/src/kaebench/boardfiles.py",
                "bench/src/kaebench/kicad_scripts")


# ------------------------------------------------------------------ small helpers
def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ident(recipe):
    """12-hex id of a canonical JSON recipe."""
    return hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "method"


def sh(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, text=True, capture_output=True, **kw).stdout.strip()


def git(repo, *args):
    return sh(["git", "-C", repo, *args])


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=1, default=str))
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def gz(src, dst):
    with open(src, "rb") as fi, gzip.open(dst, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo)


def tail(path, n=40):
    try:
        return "\n".join(Path(path).read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def github_link(url, commit=None, ref=None):
    u = re.sub(r"\.git$", "", url or "")
    if not u.startswith("https://github.com/"):
        return None
    return f"{u}/commit/{commit}" if commit else f"{u}/tree/{ref}"


def env_sh():
    """KAE_* settings from the kaebench setup's env.sh (KAE_KICAD_WRAP: KiCad in its container)."""
    out = {}
    p = KAE_HOME / "env.sh"
    if p.exists():
        for line in p.read_text().splitlines():
            m = re.match(r'export (\w+)="?(.*?)"?$', line.strip())
            if m:
                out[m.group(1)] = m.group(2)
    return out


def kicad_version():
    wrap = (os.environ.get("KAE_KICAD_WRAP") or env_sh().get("KAE_KICAD_WRAP", "")).split()
    try:
        return sh([*wrap, "kicad-cli", "version"]).splitlines()[-1].strip()
    except (subprocess.CalledProcessError, OSError, IndexError):
        return None


def main_repo():
    """The harness repo (where worktrees of frozen code are made)."""
    cfg = read_json(STORE / "config.json", {})
    if cfg.get("repo"):
        return cfg["repo"]
    repo = git(HERE, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return str(Path(repo).parent)


# ------------------------------------------------------------------ code components
def resolve_code(spec, allow_dirty=False):
    """NAME=LOCAL_REPO[@REF] or NAME=URL@REF -> (name, component dict). A local repo must be at a
    commit some remote branch contains (pushed), unless allow_dirty: then uncommitted changes are
    frozen as a snapshot commit and saved as a patch."""
    name, _, src = spec.partition("=")
    if not name or not src:
        raise SystemExit(f"--code {spec!r}: use NAME=PATH[@REF] or NAME=URL@REF")
    if re.match(r"https?://", src):
        url, _, ref = src.rpartition("@") if "@" in src.split("//", 1)[1] else (src, "", "HEAD")
        refs = dict(reversed(l.split("\t")) for l in sh(["git", "ls-remote", url]).splitlines() if "\t" in l)
        commit = next((refs[k] for k in (f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}", f"refs/heads/{ref}", ref) if k in refs), None)
        if commit is None and re.fullmatch(r"[0-9a-f]{40}", ref):
            commit = ref
        if commit is None:
            raise SystemExit(f"{url}: ref {ref!r} not found")
        return name, dict(repo=url, ref=ref, commit=commit, link=github_link(url, commit))
    path, _, ref = src.partition("@")
    path = os.path.abspath(os.path.expanduser(path))
    top = git(path, "rev-parse", "--show-toplevel")
    commit = git(top, "rev-parse", ref or "HEAD")
    url = None
    try:
        url = git(top, "remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        pass
    url = re.sub(r"^git@github\.com:", "https://github.com/", url or "")
    comp = dict(repo=url or top, commit=commit, link=github_link(url, commit))
    pushed = bool(git(top, "branch", "-r", "--contains", commit))
    dirty = not ref and bool(git(top, "status", "--porcelain", "--untracked-files=no"))
    if (dirty or not pushed) and not allow_dirty:
        why = "has uncommitted changes" if dirty else f"is at {commit[:7]}, which no remote branch contains"
        raise SystemExit(f"{name}: {top} {why}. Push it (so the method links to code anyone can fetch), "
                         "or pass --allow-dirty to freeze it as a local snapshot with a saved patch.")
    if dirty:
        snap = _snapshot(top)
        comp.update(commit=snap, base_commit=commit, dirty=True, link=None,
                    patch=git(top, "diff", commit, snap))
    elif not pushed:
        comp.update(unpushed=True, link=None)
    return name, comp


def _snapshot(top):
    idx = os.path.join(git(top, "rev-parse", "--absolute-git-dir"), f"kaeres-index-{os.getpid()}")
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        subprocess.run(["git", "-C", top, "read-tree", "HEAD"], check=True, env=env)
        subprocess.run(["git", "-C", top, "add", "-u"], check=True, env=env)
        tree = subprocess.run(["git", "-C", top, "write-tree"], check=True, env=env, capture_output=True, text=True).stdout.strip()
    finally:
        if os.path.exists(idx):
            os.unlink(idx)
    sha = git(top, "commit-tree", tree, "-p", "HEAD", "-m", "kaeres snapshot")
    git(top, "update-ref", f"refs/kaeres/{sha}", sha)
    return sha


def code_dir(commit):
    return STORE / "code" / f"{HARNESS_REPO}@{commit[:12]}"


def ensure_harness(commit, kae=False):
    """A frozen worktree of the harness repo at commit, with its venv (kaebench, or kae for physics)."""
    d = code_dir(commit)
    venv = d.with_name(d.name + (".venv-kae" if kae else ".venv"))
    repo = main_repo()
    if not d.exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        sh(["git", "-C", repo, "worktree", "add", "--detach", str(d), commit])
    if not (venv / "bin" / "python").exists():
        uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
        subprocess.run([uv, "venv", "-q", "--python", "3.12", str(venv)], check=True)
        pkg = f"{d / 'kae'}[fast]" if kae else str(d / "bench")
        subprocess.run([uv, "pip", "install", "-q", "-p", str(venv / "bin" / "python"), "-e", pkg], check=True)
    return d, venv


def tree_ids(commit, paths):
    repo = main_repo()
    return {p: git(repo, "rev-parse", f"{commit}:{p}") for p in paths}


# ------------------------------------------------------------------ methods
def methods():
    return {p.stem: json.loads(p.read_text()) for p in sorted((STORE / "methods").glob("*.json"))}


def find_method(key):
    ms = methods()
    if key in ms:
        return ms[key]
    hits = [m for m in ms.values() if m["id"].startswith(key) or m["name"] == key or m["slug"] == key]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"no method {key!r} (kaeres method list)")
    raise SystemExit(f"{key!r} names {len(hits)} methods ({', '.join(m['id'] for m in hits)}): use an id")


def cmd_method_add(a):
    comps = dict(resolve_code(s, a.allow_dirty) for s in a.code or [])
    harness = a.harness or "HEAD"
    if not a.reference:
        comps.setdefault("harness", resolve_code(f"harness={main_repo()}@{harness}" if harness != "HEAD"
                                                 else f"harness={main_repo()}", a.allow_dirty)[1])
    kicad = kicad_version()
    params = dict(kv.split("=", 1) for kv in a.param or [])
    if a.reference:
        runner = dict(type="reference")
        kind, params = "route", {}
    elif a.command:
        runner = dict(type="command", template=a.command)
        kind = a.kind
    else:
        if not a.binary:
            raise SystemExit("--binary is required for an adapter method")
        binary = Path(os.path.abspath(os.path.expanduser(a.binary)))
        root = binary.parent.parent if binary.parent.name == "bin" else binary.parent
        jar = next(iter(sorted(root.glob("lib/**/*.jar"))), None) or (binary if binary.suffix == ".jar" else None)
        runner = dict(type="kaebench-adapter", adapter=a.adapter,
                      binary_sha256=sha256_file(jar if jar else binary), binary_file=(jar or binary).name)
        kind = a.kind
        params.setdefault("timeout_s", str(a.timeout))
        params.setdefault("java_heap", "auto-v1")  # -Xmx from board size (see heap_gb)
        params.setdefault("java_processors", "2")
    recipe = dict(kind=kind, runner=runner, params=params, environment=dict(kicad=kicad, kicad_threads=a.kicad_threads),
                  code={k: {kk: vv for kk, vv in v.items() if kk in ("repo", "commit")} for k, v in comps.items()})
    mid = ident(recipe)
    path = STORE / "methods" / f"{mid}.json"
    if path.exists():
        m = read_json(path)
        print(f"already registered: {mid} {m['name']!r}")
        return
    m = dict(schema=SCHEMA, id=mid, name=a.name, slug=slugify(a.name), description=a.description or "",
             created=now(), recipe=recipe, code=comps, build=a.build)
    if runner["type"] == "kaebench-adapter":  # keep a copy of the exact binary, so the method can run again later
        dest = STORE / "bins" / f"{slugify(a.name)}-{runner['binary_sha256'][:8]}"
        if not dest.exists():
            tmp = dest.with_name(dest.name + ".tmp")
            shutil.rmtree(tmp, ignore_errors=True)
            if root == binary.parent and binary.suffix == ".jar":
                tmp.mkdir(parents=True)
                shutil.copy2(binary, tmp / binary.name)
            else:
                shutil.copytree(root, tmp, symlinks=True)
            os.replace(tmp, dest)
        bare_jar = root == binary.parent and binary.suffix == ".jar"
        m["binary"] = str(dest / (binary.name if bare_jar else binary.relative_to(root)))
        m["binary_source"] = str(binary)
        try:
            out = subprocess.run([m["binary"], "--help"], capture_output=True, text=True, timeout=120).stdout
            v = re.search(r"Freerouting v\S+", out)
            m["version"] = v.group(0) if v else None
        except (OSError, subprocess.TimeoutExpired):
            pass
    for c in comps.values():
        if c.get("patch"):
            (STORE / "methods" / f"{mid}.{c['commit'][:12]}.patch").write_text(c.pop("patch"))
    write_json(path, m)
    print(f"registered {mid} {a.name!r}")
    print(json.dumps(m, indent=1))


def cmd_method_list(a):
    for m in methods().values():
        code = ", ".join(f"{k}@{v['commit'][:7]}" for k, v in m["code"].items())
        print(f"{m['id']}  {m['name']:<28} {m['recipe']['kind']:<6} {m['recipe']['runner']['type']:<16} {code}  {m.get('version') or ''}")


def cmd_method_show(a):
    print(json.dumps(find_method(a.id), indent=1))


# ------------------------------------------------------------------ evaluators
def evaluators_for(harness, kae, kicad):
    """The DRC scorer and routed-physics evaluator a job at these commits applies, registered."""
    drc = dict(type="kaebench-drc", kicad=kicad, code=tree_ids(harness, SCORER_PATHS))
    phys = dict(type="kae-physics", kicad=kicad, measure="board_physics fills=kicad fidelity=fast, physics_total (cap 5, missing 3)",
                code=dict(kae=tree_ids(kae, ["kae/src"])["kae/src"], script=tree_ids(harness, ["tools/kaeres/physics_board.py"])["tools/kaeres/physics_board.py"]))
    out = {}
    for key, recipe, commits in (("drc", drc, dict(harness=harness)), ("physics", phys, dict(kae=kae, harness=harness))):
        eid = ident(recipe)
        p = STORE / "evaluators" / f"{eid}.json"
        if not p.exists():
            write_json(p, dict(schema=SCHEMA, id=eid, name=key, recipe=recipe, created=now(),
                               commits={k: dict(commit=v, link=github_link("https://github.com/magnetic-trowel/kicad-auto-everything", v))
                                        for k, v in commits.items()}))
        out[key] = eid
    return out


# ------------------------------------------------------------------ boards and runs on disk
def board_dir(bid):
    return STORE / "boards" / bid


def run_name(m, attempt, suffix=""):
    return f"{m['slug']}.{m['id'][:8]}.a{attempt}{suffix}"


def board_runs(bid):
    """[(run dir, run.json)] of a board."""
    out = []
    for p in sorted((board_dir(bid) / "runs").glob("*/run.json")):
        r = read_json(p)
        if r:
            out.append((p.parent, r))
    return out


def find_run(bid, method_id, attempt=0, task_id=None):
    hits = [(d, r) for d, r in board_runs(bid) if r["method_id"] == method_id and r["attempt"] == attempt
            and (task_id is None or r["task_id"] == task_id) and not r.get("repro_of")]
    return hits[-1] if hits else (None, None)


def evals_of(run_dir):
    return {p.stem: read_json(p) for p in sorted((Path(run_dir) / "evals").glob("*.json"))}


def corpus_rows():
    with open(CORPUS / "manifest.jsonl") as f:
        return {r["id"]: r for r in (json.loads(l) for l in f if l.strip())}


def board_size_mb(row):
    p = CORPUS / row["path"] / "board.kicad_pcb"
    return p.stat().st_size / MB if p.exists() else 1.0


def heap_gb(size_mb):
    """java_heap=auto-v1: Freerouting -Xmx from the board file size."""
    return int(min(16, max(2, 2 + size_mb / 8)))


def estimate(row, ms):
    """Queue resources for one board's job (board files range from KB to 230 MB)."""
    s = board_size_mb(row)
    mem = 1.2 + 0.12 * s + 0.3 * heap_gb(s)  # GB, one step at a time; kaeq requeues an overrun with a corrected value
    t = sum(int(m["recipe"]["params"].get("timeout_s", 0)) for m in ms)
    return dict(size_mb=round(s, 2), mem=f"{mem:.1f}G", disk=f"{int(100 + 10 * s)}M",
                timeout=f"{int(min(24 * 3600, t + 3600 + 240 * s))}s")


# ------------------------------------------------------------------ experiments
def exp_dir(name):
    return STORE / "experiments" / name


def load_exp(name):
    e = read_json(exp_dir(name) / "experiment.json")
    if not e:
        raise SystemExit(f"no experiment {name!r}")
    return e


def cmd_exp_create(a):
    d = exp_dir(a.name)
    if (d / "experiment.json").exists():
        raise SystemExit(f"experiment {a.name} exists")
    ms = [find_method(k) for k in a.method]
    repo = main_repo()
    harness = git(repo, "rev-parse", a.harness)
    kae = git(repo, "rev-parse", a.kae)
    for c in (harness, kae):
        if not git(repo, "branch", "-r", "--contains", c):
            raise SystemExit(f"{c[:7]} is on no remote branch: push it first, so the experiment links to fetchable code")
    if a.boards:
        boards = Path(a.boards[1:]).read_text().split() if a.boards.startswith("@") else a.boards.split(",")
    else:
        boards = sorted(corpus_rows())
    print(f"freezing harness {harness[:7]} (prepare, human scoring, physics brief) and kae {kae[:7]} (physics)")
    ensure_harness(harness)
    ensure_harness(kae, kae=True)
    for m in ms:
        hc = (m["code"].get("harness") or {}).get("commit")
        if hc:
            ensure_harness(hc)
    kicad = kicad_version()
    evs = evaluators_for(harness, kae, kicad)
    e = dict(schema=SCHEMA, name=a.name, description=a.description or "", created=now(),
             methods=[dict(id=m["id"], name=m["name"]) for m in ms], attempts=a.attempts,
             harness=dict(commit=harness, link=github_link("https://github.com/magnetic-trowel/kicad-auto-everything", harness)),
             kae=dict(commit=kae, link=github_link("https://github.com/magnetic-trowel/kicad-auto-everything", kae)),
             kicad=kicad, evaluators=evs, corpus=str(CORPUS), corpus_manifest_sha256=sha256_file(CORPUS / "manifest.jsonl"),
             boards=len(boards))
    d.mkdir(parents=True)
    (d / "boards.txt").write_text("\n".join(boards) + "\n")
    write_json(d / "experiment.json", e)
    write_json(STORE / "config.json", dict(read_json(STORE / "config.json", {}), repo=repo))
    print(json.dumps(e, indent=1))


def missing(e, bid):
    """Methods of the experiment without a finished run on this board (any task)."""
    out = []
    for a_ in range(e["attempts"]):
        for m in e["methods"]:
            d, r = find_run(bid, m["id"], a_)
            if d is None:
                out.append((m["id"], a_))
    return out


def prepare_failed(e, bid):
    return (board_dir(bid) / "prepare-failures" / f"{e['harness']['commit'][:12]}.json").exists()


def cmd_exp_submit(a):
    e = load_exp(a.name)
    rows = corpus_rows()
    boards = (exp_dir(a.name) / "boards.txt").read_text().split()
    if a.only:
        only = set(Path(a.only[1:]).read_text().split() if a.only.startswith("@") else a.only.split(","))
        boards = [b for b in boards if b in only]
    ms = {m["id"]: find_method(m["id"]) for m in e["methods"]}
    script = code_dir(e["harness"]["commit"]) / "tools" / "kaeres" / "kaeres.py"
    py = code_dir(e["harness"]["commit"]).with_name(code_dir(e["harness"]["commit"]).name + ".venv") / "bin" / "python"
    jobs = []
    boards.sort(key=lambda b: hashlib.sha1(b.encode()).hexdigest())  # sizes mixed over the run
    for bid in boards:
        if bid not in rows:
            continue
        need = missing(e, bid)
        if not need or (prepare_failed(e, bid) and not a.redo):
            continue
        est = estimate(rows[bid], [ms[m] for m, _ in need])
        jobs.append(dict(cmd=f"{py} {script} job --experiment {a.name} --board {bid}", name=f"{a.name}:{bid}", cpus=2,
                         mem=est["mem"], disk=est["disk"], timeout=est["timeout"], prio=1 if est["size_mb"] > 10 else 0))
        if a.limit and len(jobs) >= a.limit:
            break
    f = exp_dir(a.name) / f"jobs-{datetime.now().strftime('%Y%m%dT%H%M%S')}.jsonl"
    f.write_text("".join(json.dumps(j) + "\n" for j in jobs))
    print(f"{len(jobs)} board jobs -> {f}")
    if jobs and not a.dry_run:
        subprocess.run(["kaeq", "submit", "--jobs", str(f), "--owner", f"exp-{a.name}", "--tag", a.name, "--live",
                        "--cwd", str(code_dir(e["harness"]["commit"])), "--retries", "1"], check=True)


# ------------------------------------------------------------------ the per-board job
class Step:
    """Wall and CPU time (children's rusage) of one subprocess step."""

    def __init__(self, name, steps):
        self.name, self.steps = name, steps

    def __enter__(self):
        self.t0, self.r0 = time.monotonic(), resource.getrusage(resource.RUSAGE_CHILDREN)
        return self

    def __exit__(self, *exc):
        r = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.steps[self.name] = dict(wall_s=round(time.monotonic() - self.t0, 2),
                                     cpu_s=round(r.ru_utime + r.ru_stime - self.r0.ru_utime - self.r0.ru_stime, 2))


def _limit_as():
    try:
        resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))
    except (ValueError, OSError):
        pass


def run_logged(cmd, log, env, timeout):
    """Run cmd with output appended to log; returns (rc, timed_out)."""
    with open(log, "ab") as f:
        f.write(f"\n$ {' '.join(map(str, cmd))}\n".encode())
        f.flush()
        p = subprocess.Popen([str(x) for x in cmd], stdout=f, stderr=subprocess.STDOUT, env=env,
                             preexec_fn=_limit_as, start_new_session=True)
        try:
            return p.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, 9)
            p.wait()
            return None, True


class Bugs:
    def __init__(self, bid):
        self.bid, self.items = bid, []

    def add(self, who, category, detail, signature=None, evidence=(), **extra):
        self.items.append(dict(board=self.bid, method=who, category=category, signature=signature or f"{who}:{category}",
                               detail=str(detail)[:4000], evidence=list(evidence), **extra))


def cmd_job(a):
    """One board: prepare the task, run every missing method, evaluate, archive under the board."""
    e = load_exp(a.experiment) if a.experiment else None
    bid = a.board
    row = corpus_rows().get(bid)
    if row is None:
        raise SystemExit(f"{bid}: not in the corpus manifest")
    harness = a.harness or e["harness"]["commit"]
    kae = a.kae or e["kae"]["commit"]
    if a.method:
        todo = [(find_method(m)["id"], a.attempt) for m in a.method]
    else:
        todo = missing(e, bid)
    human = next((m for m in methods().values() if m["recipe"]["runner"]["type"] == "reference"), None)
    print(f"{bid}: pid {os.getpid()} job {os.environ.get('KAEQ_JOB')} methods {[m for m, _ in todo]}", flush=True)
    ws = Path(os.environ.get("KAEQ_SCRATCH") or tempfile.mkdtemp(prefix="kaeres-", dir="/var/tmp"))
    src = ws / "src" / bid
    src.mkdir(parents=True, exist_ok=True)
    for p in (CORPUS / row["path"]).iterdir():
        if (p.name.startswith("board.") or p.name == "row.json") and not (src / p.name).exists():
            os.symlink(p, src / p.name)
    size = board_size_mb(row)
    env = dict(os.environ)
    env.update({k: v for k, v in env_sh().items() if k not in env})
    binds = [b for b in env.get("APPTAINER_BIND", "").split(",") if b]
    env["APPTAINER_BIND"] = ",".join(dict.fromkeys(binds + [str(ws), str(CORPUS.resolve())]))
    kcfg = STORE / "kicad-config" / "threads-2"
    if not (kcfg / "10.0" / "kicad_advanced").exists():
        srcc = Path.home() / ".config" / "kicad" / "10.0"
        tmpc = kcfg.with_name(kcfg.name + f".tmp{os.getpid()}")
        shutil.copytree(srcc, tmpc / "10.0") if srcc.is_dir() else (tmpc / "10.0").mkdir(parents=True)
        (tmpc / "10.0" / "kicad_advanced").write_text("MaximumThreads=2\n")  # one thread per host CPU otherwise
        try:
            os.replace(tmpc, kcfg)
        except OSError:
            shutil.rmtree(tmpc, ignore_errors=True)
    env["KICAD_CONFIG_HOME"] = str(kcfg)
    env["KAE_DRC_TIMEOUT"] = str(900 if size < 20 else 3600)
    env["JAVA_TOOL_OPTIONS"] = f"-Xmx{heap_gb(size)}g -XX:ActiveProcessorCount=2"
    env.pop("VIRTUAL_ENV", None)
    log = ws / "job.log"
    pre = subprocess.run([*env.get("KAE_KICAD_WRAP", "").split(), "python3", "-c", "import pcbnew"],
                         capture_output=True, text=True, env=env, timeout=600)
    if pre.returncode != 0:  # the environment, not the board: kaeq retries and reports it
        print(f"preflight failed: KiCad's Python cannot import pcbnew (rc {pre.returncode}):\n{pre.stderr[-2000:]}", flush=True)
        return 75
    kicad = kicad_version()
    t0 = time.monotonic()

    # group methods by the harness commit they run with; the human reference goes with the experiment's
    groups = defaultdict(list)
    ms = {}
    for mid, att in todo:
        m = ms[mid] = find_method(mid)
        groups[(m["code"].get("harness") or {}).get("commit") or harness].append((m, att))
    if human and not find_run(bid, human["id"], 0)[0] and (human["id"], 0) not in todo:
        groups[harness].append((human, 0))  # every board gets the human layout scored, once
    made = []
    for hc, items in groups.items():
        made += _job_group(bid, row, hc, kae, items, human, ws, env, log, kicad, a, size)
    print(f"{bid}: {len(made)} run(s) written in {time.monotonic() - t0:.0f}s: {', '.join(made) or '-'}", flush=True)
    shutil.rmtree(ws / "w", ignore_errors=True)
    return 0


def _job_group(bid, row, hc, kae, items, human, ws, env, log, kicad, a, size):
    d, venv = code_dir(hc), code_dir(hc).with_name(code_dir(hc).name + ".venv")
    if not (venv / "bin" / "kaebench").exists():
        raise SystemExit(f"harness {hc[:7]} is not installed: kaeres exp create sets it up ({d})")
    work = ws / f"w-{hc[:8]}"
    kb = [venv / "bin" / "kaebench", "--workdir", work]
    genv = dict(env, PATH=f"{venv / 'bin'}:{env.get('PATH', '')}")
    steps = {}
    bugs = Bugs(bid)
    with Step("prepare", steps):
        rc, to = run_logged(kb + ["prepare-dir", "--dir", ws / "src", "--board-glob", "board.kicad_pcb",
                                  "--only", bid, "--kinds", "route", "-j", "1"], log, genv, timeout=3 * 3600)
    task = work / "tasks" / bid
    tj = task / "task.json"
    if not tj.exists():
        txt = tail(log, 200)
        infra = re.search(r"no Python with pcbnew|kicad-cli not found|FATAL: +container|apptainer.*FATAL", txt)
        if infra:
            print(f"prepare hit an environment error, not a board error: {infra.group(0)}\n{tail(log, 30)}", flush=True)
            raise SystemExit(75)
        bugs.add("harness", "prepare_timeout" if to else "prepare_error", _first_error(txt) or f"rc={rc}",
                 signature=f"harness:prepare:{_normalize(_first_error(txt))}", log_tail=tail(log, 60))
        write_json(board_dir(bid) / "prepare-failures" / f"{hc[:12]}.json",
                   dict(board=bid, harness=hc, at=now(), steps=steps, bugs=bugs.items, log_tail=tail(log, 200)))
        _board_json(bid, row)
        return []
    record = json.loads(tj.read_text())
    task_recipe = dict(board_sha256=record.get("pcb_sha256"), task_spec=record.get("task_spec"), kind="route", kicad=kicad)
    task_id = ident(task_recipe)
    tdir = board_dir(bid) / "tasks" / task_id
    if not (tdir / "task.json").exists():
        tmp = tdir.with_name(tdir.name + f".tmp{os.getpid()}")
        tmp.mkdir(parents=True, exist_ok=True)
        write_json(tmp / "task.json", dict(schema=SCHEMA, id=task_id, recipe=task_recipe, prepared_by=hc, at=now(), record=record))
        if (task / "reference" / "drc.json").exists():
            gz(task / "reference" / "drc.json", tmp / "human-drc.json.gz")
        try:
            os.replace(tmp, tdir)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
    _board_json(bid, row)
    evs = evaluators_for(hc, kae, kicad)
    # skip methods that already have a run on this task (another experiment may have made it meanwhile)
    todo = [(m, att) for m, att in items if a.method or find_run(bid, m["id"], att, task_id)[0] is None]
    if not todo:
        return []
    arms, cmds = [], []
    for m, att in todo:
        r = m["recipe"]["runner"]
        arm = f"m{m['id']}"
        if r["type"] == "reference":
            arms += ["--arm", f"name={arm},adapter=reference"]
        elif r["type"] == "kaebench-adapter":
            arms += ["--arm", f"name={arm},adapter={r['adapter']},freerouting={m['binary']}"]
        else:
            cmds.append(m)
    timeout = max([int(m["recipe"]["params"].get("timeout_s", 900)) for m, _ in todo] + [900])
    k = max(att for _, att in todo) + 1
    with Step("run", steps):
        if arms:
            rc, to = run_logged(kb + ["run", *arms, "--kinds", "route", "-k", str(k), "--timeout", str(timeout), "--all",
                                      "--only", bid, "--name", "base", "-j", "1"], log, genv,
                                timeout=len(todo) * k * (timeout + 1800) + 3600)
            if rc != 0:
                bugs.add("harness", "run_timeout" if to else "run_error", _first_error(tail(log, 200)) or f"rc={rc}",
                         log_tail=tail(log, 60))
        for m in cmds:
            p = m["recipe"]["params"]
            tpl = m["recipe"]["runner"]["template"]
            for name, comp in m["code"].items():
                tpl = tpl.replace("{code:" + name + "}", str(code_dir(comp["commit"])))
            rc, to = run_logged(kb + ["run", "--adapter", f"m{m['id']}", "--command", tpl, "--kinds", m["recipe"]["kind"],
                                      "-k", str(k), "--timeout", str(p.get("timeout_s", 900)), "--all", "--only", bid,
                                      "--name", f"cmd-{m['id']}", "-j", "1"], log, genv,
                                timeout=k * (int(p.get("timeout_s", 900)) + 1800) + 3600)
    human_run = find_run(bid, human["id"], 0, task_id) if human else (None, None)
    adirs = {}
    for m, att in todo:
        rn = "base" if m["recipe"]["runner"]["type"] != "command" else f"cmd-{m['id']}"
        adirs[(m["id"], att)] = work / "results" / rn / f"m{m['id']}" / m["recipe"]["kind"] / bid / f"attempt-{att}"
    human_adir = adirs.get((human["id"], 0)) if human else None
    human_types = {}
    if human_adir and (human_adir / "attempt.json").exists():
        human_types = (read_json(human_adir / "attempt.json").get("score") or {}).get("errors_by_type") or {}
    elif human_run[0]:
        human_types = ((read_json(human_run[0] / "evals" / f"{evs['drc']}.json") or {}).get("score") or {}).get("errors_by_type") or {}

    # routed physics of every new run's scored board (and the human board), one brief from the task input
    boards = {}
    for (mid, att), adir in adirs.items():
        aj = read_json(adir / "attempt.json") or {}
        if aj.get("status") == "ok" and (adir / "score" / "board.kicad_pcb").exists():
            boards[f"{mid}.{att}"] = adir / "score" / "board.kicad_pcb"
    phys = {}
    if boards:
        kd, kv = code_dir(kae), code_dir(kae).with_name(code_dir(kae).name + ".venv-kae")
        pout = ws / f"physics-{hc[:8]}.json"
        with Step("physics", steps):
            rc, to = run_logged([kv / "bin" / "python", d / "tools" / "kaeres" / "physics_board.py",
                                 "--input", task / "route" / "input" / "board.kicad_pcb",
                                 *[x for n, p in boards.items() for x in ("--board", f"{n}={p}")], "--out", pout],
                                log, genv, timeout=int(1800 + 120 * size))
        phys = read_json(pout) or dict(error=f"physics step {'timed out' if to else f'failed rc={rc}'}")
        if phys.get("error"):
            bugs.add("physics", "physics_error", phys["error"], signature=f"physics:board:{_normalize(phys['error'])}",
                     traceback=phys.get("traceback"))

    made = []
    for (mid, att), adir in adirs.items():
        m = find_method(mid)
        rb = Bugs(bid)
        aj = read_json(adir / "attempt.json")
        if aj is None:
            bugs.add("harness", "attempt_missing", f"kaebench wrote no attempt.json for {m['name']}", log_tail=tail(log, 60))
            continue
        if m["recipe"]["runner"]["type"] != "reference":
            _run_bugs(rb, m, aj, adir, human_types)
        if aj.get("status") == "score_error":
            rb.add("harness", "score_error", aj.get("error"), signature=f"harness:score_error:{_normalize(aj.get('error'))}",
                   evidence=["score_error.log"])
        ph = (phys.get("boards") or {}).get(f"{mid}.{att}")
        if ph and ph.get("error"):
            rb.add("physics", "physics_error", ph["error"], signature=f"physics:{_normalize(ph['error'])}",
                   evidence=[f"evals/{evs['physics']}.json"], traceback=ph.get("traceback"))
        name = _write_run(bid, m, att, task_id, hc, aj, adir, ph, evs, rb.items + bugs.items, steps, a)
        bugs.items = []  # board-level bugs go with the first run written
        if name:
            made.append(name)
    return made


def _board_json(bid, row):
    p = board_dir(bid) / "board.json"
    if not p.exists():
        write_json(p, row)


def _write_run(bid, m, att, task_id, hc, aj, adir, ph, evs, bugs, steps, a):
    """Archive one run (output, logs, evaluations, bugs) atomically under the board."""
    suffix = f".repro-{datetime.now().strftime('%Y%m%dT%H%M%S')}" if a.repro else ""
    dest = board_dir(bid) / "runs" / run_name(m, att, suffix)
    if dest.exists() and not suffix:
        d0, r0 = find_run(bid, m["id"], att, task_id)
        if d0 is not None:
            return None  # made by another experiment's job meanwhile
        dest = dest.with_name(dest.name + f".t{task_id[:8]}")  # same method, a different task (board or task spec changed)
    tmp = dest.with_name(f".tmp-{dest.name}-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "evals").mkdir(parents=True)
    out = adir / "output" / "board.kicad_pcb"
    if out.exists():
        gz(out, tmp / "output.kicad_pcb.gz")
    if (adir / "adapter.log").exists():
        gz(adir / "adapter.log", tmp / "adapter.log.gz")
    art = adir / "artifacts"
    if (art / "result.json").exists():
        shutil.copy2(art / "result.json", tmp / "router-report.json")
    if (art / "board.ses").exists():
        gz(art / "board.ses", tmp / "board.ses.gz")
    if any(b["category"] not in ("drc",) for b in bugs) and art.exists():  # the router's exact input, to reproduce
        (tmp / "artifacts").mkdir()
        for p in art.iterdir():
            if p.is_file() and p.name not in ("result.json", "board.ses"):
                gz(p, tmp / "artifacts" / (p.name + ".gz"))
    if (adir / "score_error.log").exists():
        shutil.copy2(adir / "score_error.log", tmp / "score_error.log")
    run = dict(schema=SCHEMA, run=dest.name, board=bid, method_id=m["id"], method_name=m["name"], attempt=att,
               task_id=task_id, harness_commit=hc, experiment=a.experiment, kaeq_job=os.environ.get("KAEQ_JOB"),
               finished=now(), java_tool_options=os.environ.get("JAVA_TOOL_OPTIONS") if m["recipe"]["runner"]["type"] != "reference" else None,
               status=aj.get("status"), error=aj.get("error"), runtime_s=aj.get("runtime_s"), over_time=aj.get("over_time"),
               method_usage=aj.get("method_usage"), adapter_meta=aj.get("adapter_meta"), load_avg=[aj.get("load_avg_start"), aj.get("load_avg_end")],
               job_steps=steps, **({"repro_of": run_name(m, att)} if suffix else {}))
    write_json(tmp / "run.json", run)
    if aj.get("score") is not None:
        ev = dict(schema=SCHEMA, evaluator=evs["drc"], run=dest.name, at=now(), score=aj["score"],
                  scoring_s=aj.get("scoring_s"), scoring_usage=aj.get("scoring_usage"))
        write_json(tmp / "evals" / f"{evs['drc']}.json", ev)
        if (adir / "score" / "drc.json").exists():
            gz(adir / "score" / "drc.json", tmp / "evals" / f"{evs['drc']}.drc.json.gz")
    if ph is not None:
        write_json(tmp / "evals" / f"{evs['physics']}.json", dict(schema=SCHEMA, evaluator=evs["physics"], run=dest.name,
                                                                   at=now(), physics={k: v for k, v in ph.items() if k != "traceback"}))
    write_json(tmp / "bugs.json", bugs)
    if dest.exists():
        shutil.rmtree(dest)
    os.replace(tmp, dest)
    return dest.name


_EXC = re.compile(r"\b((?:[a-z_][\w$]*\.)+[A-Z]\w*(?:Exception|Error))\b(:?[^\n]{0,200})")


def _first_error(text):
    for line in (text or "").splitlines():
        if re.search(r"Traceback|Error|Exception|error:|FAILED|Killed|Timeout|timed out", line):
            return line.strip()[:500]
    return ""


def _normalize(msg):
    """A grouping key: message with paths, numbers and ids removed."""
    msg = re.sub(r"/[^\s:'\"]+", "<path>", msg or "")
    msg = re.sub(r"0x[0-9a-f]+|\d+(\.\d+)?", "N", msg)
    return re.sub(r"\s+", " ", msg).strip()[:160]


def _java_exceptions(log):
    """Distinct Java exception classes in a router log, with the first message and frame of each."""
    out = {}
    lines = log.splitlines()
    for i, line in enumerate(lines):
        for m in _EXC.finditer(line):
            cls = m.group(1)
            if cls in out:
                out[cls]["count"] += 1
                continue
            frame = next((l.strip() for l in lines[i + 1:i + 6] if l.strip().startswith("at ")), "")
            out[cls] = dict(count=1, message=(m.group(2) or "").strip(": ")[:300], frame=frame[:300], line=line.strip()[:400])
    return out


def _run_bugs(bugs, m, row, adir, human_types):
    """Bug records for one method's attempt. Signatures start with the method name."""
    who = m["name"]
    st = row.get("status")
    meta = row.get("adapter_meta") or {}
    s = row.get("score") or {}
    log = (adir / "adapter.log").read_text(errors="replace") if (adir / "adapter.log").exists() else ""
    ev = ["run.json", "adapter.log.gz"]
    rep = meta.get("router_report") or {}
    if st == "adapter_error":
        err = row.get("error") or ""
        cat = "ses_import_error" if "import" in err.lower() else "adapter_error"
        bugs.add(who, cat, err, signature=f"{who}:{cat}:{_normalize(err)}", evidence=ev + ["artifacts/"])
    elif st == "no_output":
        if meta.get("ses_empty") or meta.get("ses_cut"):
            cat = "ses_incomplete"
        elif meta.get("timed_out"):
            cat = "no_output_at_deadline"  # the router ignored its own job timeout and wrote nothing
        elif meta.get("rc") not in (0, None):
            cat = "router_crash"
        else:
            cat = "no_output"
        bugs.add(who, cat, f"rc={meta.get('rc')} timed_out={meta.get('timed_out')} final_state={rep.get('final_state')}\n"
                 + "\n".join(log.splitlines()[-30:]), evidence=ev + ["artifacts/"])
    for cls, x in _java_exceptions(log).items():
        cat = "java_oom" if "OutOfMemoryError" in cls else "java_exception"
        bugs.add(who, cat, x["line"], signature=f"{who}:{cat}:{cls}:{x['frame']}", exception=cls, count=x["count"],
                 frame=x["frame"], evidence=ev + ["artifacts/"])
    # the router's own count of open connections vs KiCad's on the imported board: more open in KiCad
    # means connections were lost in translation (DSN export, SES import) or routed copper is illegal there
    own_open = ((rep.get("board_statistics") or {}).get("connections") or {}).get("incomplete_count")
    if st == "ok" and own_open is not None and s.get("unconnected") is not None and s["unconnected"] > own_open:
        bugs.add(who, "unconnected_mismatch", f"KiCad finds {s['unconnected']} unconnected, the router reported {own_open} incomplete",
                 count=s["unconnected"] - own_open, evidence=ev + ["router-report.json", "board.ses.gz"])
    if row.get("over_time"):
        bugs.add(who, "over_time", f"runtime {row.get('runtime_s')}s exceeded the attempt timeout", evidence=ev)
    if s and s.get("valid") is False:
        bad = [k for k, v in (s.get("integrity") or {}).items() if not v]
        bugs.add(who, "integrity", f"invalid output: {bad} foreign={(s.get('foreign') or {}).get('by_kind')}",
                 signature=f"{who}:integrity:{','.join(sorted(bad))}", evidence=ev + ["evals/"])
    # DRC errors the method created: per type, beyond what the human layout has on the same board
    for typ, n in sorted((s.get("errors_by_type") or {}).items()):
        extra = n - human_types.get(typ, 0)
        if extra > 0:
            bugs.add(who, "drc", f"{extra} {typ} error(s) beyond the human layout's {human_types.get(typ, 0)}",
                     signature=f"{who}:drc:{typ}", drc_type=typ, count=extra, evidence=["evals/", "output.kicad_pcb.gz"])


# ------------------------------------------------------------------ reading results back
def run_view(bid, d, r, evs, human_phys=None):
    """One flat row: a run with the given evaluators' results."""
    ed = evals_of(d)
    s = (ed.get(evs.get("drc")) or {}).get("score") or {}
    ph = ((ed.get(evs.get("physics")) or {}).get("physics")) or {}
    meta = r.get("adapter_meta") or {}
    rep = meta.get("router_report") or {}
    mu = r.get("method_usage") or {}
    row = dict(board=bid, method=r["method_name"], method_id=r["method_id"], run=r["run"], attempt=r["attempt"],
               task_id=r["task_id"], status=r["status"], valid=s.get("valid"), clean=s.get("clean"),
               completion=s.get("completion"), start_unconnected=s.get("start_unconnected"), unconnected=s.get("unconnected"),
               errors=s.get("errors"), warnings=s.get("warnings"), errors_by_type=json.dumps(s.get("errors_by_type") or {}, sort_keys=True),
               track_length_mm=s.get("track_length_mm"), vias=s.get("vias"), wl_ratio=s.get("wl_ratio"), via_delta=s.get("via_delta"),
               runtime_s=r.get("runtime_s"), cpu_s=mu.get("cpu_s"), max_rss_mb=mu.get("max_rss_mb"),
               timed_out=meta.get("timed_out"), partial=meta.get("partial"), final_state=rep.get("final_state"),
               router_incomplete=((rep.get("board_statistics") or {}).get("connections") or {}).get("incomplete_count"),
               router_introduced_violations=((rep.get("board_statistics") or {}).get("clearance_violations") or {}).get("router_introduced_count"),
               physics_total=ph.get("physics_total"), physics_modules=ph.get("n_modules"), physics_missing=ph.get("n_missing"),
               physics_open=ph.get("n_open"), worst_rail_mohm=ph.get("worst_rail_mohm"), physics_error=ph.get("error"),
               physics_vs_human=None, module_ratio_median=None, scored=bool(s), physics_scored=bool(ph))
    if human_phys and ph and not ph.get("error") and not human_phys.get("error"):
        if human_phys.get("physics_total"):
            row["physics_vs_human"] = round(ph["physics_total"] / human_phys["physics_total"], 4)
        ratios = [x["value"] / hm["value"] for k, x in (ph.get("modules") or {}).items()
                  if x.get("value") and not x.get("open_hops")
                  and (hm := (human_phys.get("modules") or {}).get(k) or {}).get("value") and not hm.get("open_hops")]
        row["module_ratio_median"] = round(statistics.median(ratios), 4) if ratios else None
    return row


def human_physics(bid, task_id, evs):
    human = next((m for m in methods().values() if m["recipe"]["runner"]["type"] == "reference"), None)
    if not human:
        return None
    d, _ = find_run(bid, human["id"], 0, task_id)
    if d is None:
        return None
    return ((evals_of(d).get(evs.get("physics")) or {}).get("physics")) or None


def cmd_board(a):
    bid = a.id
    b = read_json(board_dir(bid) / "board.json")
    if b is None:
        raise SystemExit(f"no results for board {bid}")
    print(f"{bid}: {b.get('layers')} layers, {b.get('footprints')} footprints, {b.get('nets')} nets, {b.get('collection')}, {b.get('license_tier')}")
    for p in sorted((board_dir(bid) / "tasks").glob("*/task.json")):
        t = read_json(p)
        rd = t["record"]["reference"]["drc"]
        print(f"task {t['id']}: split {t['record']['split']}, pads {t['record']['reference']['stats'].get('pads')}, "
              f"human unconnected {rd['unconnected']} errors {rd['errors']}, spec {t['recipe']['task_spec']}")
    for p in sorted((board_dir(bid) / "prepare-failures").glob("*.json")):
        f = read_json(p)
        print(f"prepare FAILED with harness {f['harness'][:7]}: {f['bugs'][0]['detail'][:120] if f['bugs'] else ''}")
    hdr = ("run", "method", "status", "clean", "compl", "unconn", "errors", "wl_ratio", "vias±", "cpu_s", "physΣu", "Σu/human")
    rows = []
    for d, r in board_runs(bid):
        ed = evals_of(d)
        drc = [k for k, v in ed.items() if (v or {}).get("score") is not None]
        phy = [k for k, v in ed.items() if (v or {}).get("physics") is not None]
        evs = dict(drc=drc[-1] if drc else None, physics=phy[-1] if phy else None)
        v = run_view(bid, d, r, evs, human_physics(bid, r["task_id"], evs))
        f = lambda x, nd=3: "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))
        rows.append((r["run"], r["method_name"][:24], v["status"], f(v["clean"]), f(v["completion"]), f(v["unconnected"]),
                     f(v["errors"]), f(v["wl_ratio"]), f(v["via_delta"]), f(v["cpu_s"], 1), f(v["physics_total"], 2),
                     f(v["physics_vs_human"])))
        if len(drc) > 1 or len(phy) > 1:
            rows.append(("", f"  ({len(drc)} DRC and {len(phy)} physics evaluations; latest shown)", *[""] * 10))
    w = [max(len(str(x[i])) for x in rows + [hdr]) for i in range(len(hdr))]
    for x in [hdr] + rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(x)))
    print(f"\nfiles: {board_dir(bid)}/runs/<run>/ (run.json, output.kicad_pcb.gz, evals/, bugs.json)")


def cmd_rerun(a):
    d = Path(a.run).resolve()
    r = read_json(d / "run.json")
    if r is None:
        raise SystemExit(f"{d}: no run.json")
    m = find_method(r["method_id"])
    print(f"run {r['run']} of method {m['name']} ({m['id']}) on board {r['board']}, attempt {r['attempt']}, task {r['task_id']}")
    print("code:")
    for k, c in m["code"].items():
        extra = " (local snapshot; patch in methods/)" if c.get("dirty") else ""
        print(f"  {k}: {c['repo']} @ {c['commit']}{extra}  {c.get('link') or ''}")
    print(f"  harness that ran it: {r['harness_commit']}")
    if m.get("binary"):
        print(f"binary: {m['binary']} (sha256 {m['recipe']['runner']['binary_sha256'][:16]}..., copied from {m.get('binary_source')})")
    if m.get("build"):
        print(f"build: {m['build']}")
    print(f"recipe: {json.dumps(m['recipe'])}")
    exp = r.get("experiment")
    cmd = (f"kaeres job --board {r['board']} --method {m['id']} --attempt {r['attempt']} --harness {r['harness_commit']} "
           f"--kae {load_exp(exp)['kae']['commit'] if exp else '<kae commit>'} --repro")
    print(f"reproduce (writes runs/{r['run']}.repro-<time>/): {cmd}")
    if a.submit:
        py = code_dir(r["harness_commit"]).with_name(code_dir(r["harness_commit"]).name + ".venv") / "bin" / "python"
        script = code_dir(r["harness_commit"]) / "tools" / "kaeres" / "kaeres.py"
        subprocess.run(["kaeq", "submit", "--owner", "kaeres-rerun", "--live", "--cwd", str(code_dir(r["harness_commit"])),
                        "--mem", "8G", "--disk", "4G", "--timeout", "6h", "--cpus", "2", "--name", f"rerun:{r['run']}", "--",
                        str(py), str(script), *cmd.split()[1:]], check=True)


# ------------------------------------------------------------------ experiment reports
def exp_rows(e):
    """(rows, bugs, prepare failures) of an experiment: each method's run on each board, viewed through
    the experiment's evaluators (falling back to the run's newest evaluation of the same type)."""
    boards = (exp_dir(e["name"]) / "boards.txt").read_text().split()
    human = next((m for m in methods().values() if m["recipe"]["runner"]["type"] == "reference"), None)
    want = ([dict(id=human["id"], name=human["name"])] if human else []) + [m for m in e["methods"] if not human or m["id"] != human["id"]]
    rows, bugs, fails = [], [], []
    evs = e["evaluators"]
    for bid in boards:
        bd = board_dir(bid)
        if not bd.exists():
            continue
        for p in (bd / "prepare-failures").glob(f"{e['harness']['commit'][:12]}.json"):
            fails.append(read_json(p))
        task_meta = None
        for m in want:
            d, r = find_run(bid, m["id"], 0)
            if d is None:
                continue
            if task_meta is None:
                task_meta = (read_json(bd / "tasks" / r["task_id"] / "task.json") or {}).get("record") or {}
            ed = evals_of(d)
            use = dict(evs)
            for key, field in (("drc", "score"), ("physics", "physics")):
                if use[key] not in ed:
                    other = [k for k, v in ed.items() if (v or {}).get(field) is not None]
                    use[key] = other[-1] if other else None
            v = run_view(bid, d, r, use, human_physics(bid, r["task_id"], use))
            v["evaluator_drc"], v["evaluator_physics"] = use["drc"], use["physics"]
            v["foreign_evaluator"] = use["drc"] != evs["drc"]
            b = read_json(bd / "board.json") or {}
            v.update(split=task_meta.get("split"), pads=(task_meta.get("reference") or {}).get("stats", {}).get("pads"),
                     human_clean=task_meta.get("human_clean"), qualified=task_meta.get("qualified"),
                     layers=b.get("layers"), footprints=b.get("footprints"), collection=b.get("collection"), license_tier=b.get("license_tier"))
            rows.append(v)
            bugs += read_json(d / "bugs.json", [])
    return rows, bugs, fails


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def _f(x, nd=3):
    if x is None:
        return "—"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def method_table(rows, names, title):
    out = [f"### {title}", "", "| method | boards | ok | cp1 (clean) | completion | not closed | DRC errors / board | "
           "timeouts | no output | errors | CPU s median / p90 / total h | physics Σu | Σu vs human (median) | module ratio (median) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        rs = [r for r in rows if r["method"] == n]
        if not rs:
            continue
        ok = [r for r in rs if r["status"] == "ok"]
        cpu = [r["cpu_s"] for r in rs]
        out.append("| " + " | ".join([
            n, str(len(rs)), str(len(ok)), _f(_mean([1.0 if r["clean"] else 0.0 for r in rs])),
            _f(_mean([r["completion"] if r["completion"] is not None else 0.0 for r in rs])),
            str(sum(1 for r in ok if (r["unconnected"] or 0) > 0)), _f(_mean([r["errors"] for r in ok]), 2),
            str(sum(1 for r in rs if r["timed_out"] or r["partial"])), str(sum(1 for r in rs if r["status"] == "no_output")),
            str(sum(1 for r in rs if r["status"] in ("adapter_error", "score_error"))),
            f"{_f(_med(cpu), 1)} / {_f(_q(cpu, 0.9), 1)} / {_f(sum(x or 0 for x in cpu) / 3600, 1)}",
            _f(_mean([r["physics_total"] for r in rs]), 3), _f(_med([r["physics_vs_human"] for r in rs]), 3),
            _f(_med([r["module_ratio_median"] for r in rs]), 3)]) + " |")
    return out + [""]


def cmd_exp_report(a):
    e = load_exp(a.name)
    d = exp_dir(a.name)
    rows, bugs, fails = exp_rows(e)
    for f in fails:
        bugs += f.get("bugs") or []
    human = next((m for m in methods().values() if m["recipe"]["runner"]["type"] == "reference"), None)
    names = ([human["name"]] if human else []) + [m["name"] for m in e["methods"] if not human or m["id"] != human["id"]]
    fields = list(rows[0].keys()) if rows else ["board"]
    with open(d / "results.csv.tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(d / "results.csv.tmp", d / "results.csv")
    (d / "bugs").mkdir(exist_ok=True)
    with open(d / "bugs" / "index.jsonl.tmp", "w") as f:
        for b in bugs:
            f.write(json.dumps({k: v for k, v in b.items() if k not in ("traceback", "log_tail")}) + "\n")
    os.replace(d / "bugs" / "index.jsonl.tmp", d / "bugs" / "index.jsonl")
    groups = defaultdict(list)
    for b in bugs:
        groups[b["signature"]].append(b)
    bl = [f"# Bugs by signature: {a.name}", "",
          f"{len(bugs)} records in {len(groups)} signatures over {len({b['board'] for b in bugs})} boards. Each record is in "
          "`~/kae-baselines/boards/<board>/runs/<run>/bugs.json` (with tracebacks and log tails; evidence paths are relative "
          "to the run folder), prepare failures in `boards/<board>/prepare-failures/`. All records: `bugs/index.jsonl`.", "",
          "| signature | boards | records | count | example boards | example detail |", "|---|---|---|---|---|---|"]
    for sig, bs in sorted(groups.items(), key=lambda kv: (-len({b["board"] for b in kv[1]}), kv[0])):
        boards = sorted({b["board"] for b in bs})
        bl.append(f"| `{sig[:120]}` | {len(boards)} | {len(bs)} | {sum(b.get('count', 1) for b in bs)} | "
                  f"{', '.join(boards[:3])} | {bs[0]['detail'].splitlines()[0][:160] if bs[0]['detail'] else ''} |")
    (d / "bugs" / "BY-SIGNATURE.md").write_text("\n".join(bl) + "\n")
    total = e["boards"]
    done = len({r["board"] for r in rows})
    ms = {m["id"]: find_method(m["id"]) for m in e["methods"]}
    rep = [f"# Experiment {a.name}", "", e.get("description") or "", "",
           f"Generated {now()}. Boards with results: {done} / {total}; prepare failed: {len(fails)}. "
           f"Harness {e['harness']['commit'][:7]} (prepare, human scoring), kae {e['kae']['commit'][:7]} (physics), KiCad {e['kicad']}. "
           f"Evaluators: DRC `{e['evaluators']['drc']}`, physics `{e['evaluators']['physics']}`.", "", "Methods:", ""]
    for m in ms.values():
        code = "; ".join(f"{k} [{c['commit'][:7]}]({c['link']})" if c.get("link") else f"{k} {c['commit'][:7]} (local)"
                         for k, c in m["code"].items())
        rep.append(f"- **{m['name']}** `{m['id']}` {m.get('version') or ''}: {m['recipe']['runner'].get('adapter') or m['recipe']['runner']['type']}, "
                   f"{json.dumps(m['recipe']['params'])}; {code}")
    foreign = sum(1 for r in rows if r["foreign_evaluator"])
    if foreign:
        rep += ["", f"**Note:** {foreign} runs were scored by a different DRC evaluator than this experiment's (reused runs from "
                "an older scorer). Rescore them before comparing numbers."]
    rep += ["", "Columns: cp1 = share of boards routed clean (valid, 0 unconnected, 0 DRC errors) on attempt 0; completion = "
            "share of initially unconnected items routed (0 for no output); not closed = boards with unconnected items left; "
            "timeouts = stopped at the deadline (partial); CPU s = the method's own processes (router, DSN export, SES import), "
            "not scoring; physics Σu = kae module physics total (lower is better; modules without a value count 3); Σu vs "
            "human = per-board ratio to the human board's; module ratio = per-board median of method / human module value "
            "over modules routed in both (lower is better). The human method is the original copper scored the same way.", ""]
    rep += method_table(rows, names, "All boards")
    rep += method_table([r for r in rows if r["human_clean"]], names, "Boards whose human layout is DRC-clean")
    for sp in ("A", "B", "C"):
        rep += method_table([r for r in rows if r["split"] == sp], names,
                            f"Split {sp} ({'≤ 31' if sp == 'A' else '≤ 100' if sp == 'B' else '> 100'} pads)")
    for lab, test in (("2 layers", lambda n: n == 2), ("4 layers", lambda n: n == 4), ("6+ layers", lambda n: (n or 0) >= 6)):
        rep += method_table([r for r in rows if test(r["layers"])], names, lab)
    rep += ["### DRC error types (errors on ok attempts)", "", "| type | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    per = {n: Counter() for n in names}
    for r in rows:
        if r["status"] == "ok" and r["method"] in per:
            per[r["method"]].update(json.loads(r["errors_by_type"]))
    for typ in sorted(set().union(*per.values()), key=lambda t: -sum(per[n][t] for n in names))[:25]:
        rep.append(f"| {typ} | " + " | ".join(str(per[n][typ]) for n in names) + " |")
    rep += ["", "### Router final states", "", "| method | COMPLETED | TIMED_OUT | other | none |", "|---|---|---|---|---|"]
    for m in ms.values():
        fs = Counter((r["final_state"] or "none") for r in rows if r["method_id"] == m["id"])
        other = sum(v for k, v in fs.items() if k not in ("COMPLETED", "TIMED_OUT", "none"))
        rep.append(f"| {m['name']} | {fs['COMPLETED']} | {fs['TIMED_OUT']} | {other} | {fs['none']} |")
    rep += ["", "### Bugs", "", f"{len(bugs)} records, {len(groups)} signatures; top 15 (all: `bugs/BY-SIGNATURE.md`):", ""]
    rep += bl[5:5 + 2 + 15]
    (d / "REPORT.md").write_text("\n".join(rep) + "\n")
    print(f"wrote {d / 'REPORT.md'}, results.csv ({len(rows)} rows), bugs/ ({len(bugs)} records)")


def cmd_exp_status(a):
    e = load_exp(a.name)
    boards = (exp_dir(a.name) / "boards.txt").read_text().split()
    done = sum(1 for b in boards if not missing(e, b))
    failed = sum(1 for b in boards if prepare_failed(e, b))
    print(f"{a.name}: {done}/{len(boards)} boards complete, {failed} prepare failures")
    subprocess.run(["kaeq", "status", "--owner", f"exp-{a.name}", "--limit", "5"])


def cmd_exp_timer(a):
    e = load_exp(a.name)
    d = Path.home() / ".config" / "systemd" / "user"
    d.mkdir(parents=True, exist_ok=True)
    unit = f"kaeres-{a.name}"
    cd = code_dir(e["harness"]["commit"])
    py = cd.with_name(cd.name + ".venv") / "bin" / "python"
    (d / f"{unit}.service").write_text(
        f"[Unit]\nDescription=kaeres report {a.name}\n\n[Service]\nType=oneshot\nNice=19\n"
        f"ExecStart={py} {cd / 'tools' / 'kaeres' / 'kaeres.py'} exp report {a.name}\n"
        f"ExecStartPost={py} {cd / 'tools' / 'kaeres' / 'kaeres.py'} index\n")
    (d / f"{unit}.timer").write_text(f"[Unit]\nDescription=kaeres report {a.name} hourly\n\n[Timer]\nOnBootSec=10min\n"
                                     "OnUnitActiveSec=1h\n\n[Install]\nWantedBy=timers.target\n")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{unit}.timer"], check=True)
    print(f"enabled {unit}.timer (stop: systemctl --user disable --now {unit}.timer)")


# ------------------------------------------------------------------ index
def cmd_index(a):
    """Rebuild index.sqlite: methods, evaluators, tasks, runs and evaluations (a cache; files are the truth)."""
    tmp = STORE / f"index.sqlite.tmp{os.getpid()}"
    c = sqlite3.connect(tmp)
    c.executescript("""
    CREATE TABLE methods(id TEXT PRIMARY KEY, name TEXT, kind TEXT, runner TEXT, version TEXT, json TEXT);
    CREATE TABLE evaluators(id TEXT PRIMARY KEY, name TEXT, json TEXT);
    CREATE TABLE boards(id TEXT PRIMARY KEY, layers INT, footprints INT, nets INT, collection TEXT, license_tier TEXT);
    CREATE TABLE runs(board TEXT, run TEXT, method_id TEXT, method_name TEXT, attempt INT, task_id TEXT, status TEXT,
      runtime_s REAL, cpu_s REAL, max_rss_mb REAL, final_state TEXT, timed_out INT, experiment TEXT, path TEXT,
      PRIMARY KEY(board, run));
    CREATE TABLE evals(board TEXT, run TEXT, evaluator TEXT, clean INT, valid INT, completion REAL, unconnected INT,
      errors INT, errors_by_type TEXT, wl_ratio REAL, via_delta INT, physics_total REAL, physics_modules INT, json TEXT,
      PRIMARY KEY(board, run, evaluator));
    """)
    for m in methods().values():
        c.execute("INSERT INTO methods VALUES(?,?,?,?,?,?)", (m["id"], m["name"], m["recipe"]["kind"], m["recipe"]["runner"]["type"],
                                                               m.get("version"), json.dumps(m)))
    for p in (STORE / "evaluators").glob("*.json"):
        v = read_json(p)
        c.execute("INSERT INTO evaluators VALUES(?,?,?)", (v["id"], v["name"], json.dumps(v)))
    n = 0
    for bd in sorted((STORE / "boards").iterdir()) if (STORE / "boards").exists() else []:
        b = read_json(bd / "board.json") or {}
        c.execute("INSERT OR REPLACE INTO boards VALUES(?,?,?,?,?,?)", (bd.name, b.get("layers"), b.get("footprints"),
                                                                         b.get("nets"), b.get("collection"), b.get("license_tier")))
        for d, r in board_runs(bd.name):
            mu = r.get("method_usage") or {}
            meta = r.get("adapter_meta") or {}
            c.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (bd.name, r["run"], r["method_id"], r["method_name"], r["attempt"], r["task_id"], r["status"],
                       r.get("runtime_s"), mu.get("cpu_s"), mu.get("max_rss_mb"), (meta.get("router_report") or {}).get("final_state"),
                       int(bool(meta.get("timed_out") or meta.get("partial"))), r.get("experiment"), str(d)))
            for eid, ev in evals_of(d).items():
                s = (ev or {}).get("score") or {}
                ph = (ev or {}).get("physics") or {}
                c.execute("INSERT OR REPLACE INTO evals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (bd.name, r["run"], eid, s.get("clean"), s.get("valid"), s.get("completion"), s.get("unconnected"),
                           s.get("errors"), json.dumps(s.get("errors_by_type") or {}), s.get("wl_ratio"), s.get("via_delta"),
                           ph.get("physics_total"), ph.get("n_modules"), json.dumps(ev)))
            n += 1
    c.commit()
    c.close()
    os.replace(tmp, STORE / "index.sqlite")
    print(f"indexed {n} runs -> {STORE / 'index.sqlite'}")


# ------------------------------------------------------------------ cli
def main():
    ap = argparse.ArgumentParser(prog="kaeres", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mp = sub.add_parser("method").add_subparsers(dest="sub", required=True)
    s = mp.add_parser("add", help="register a method (its id is the hash of its recipe)")
    s.add_argument("name", help="human-readable name, e.g. 'freerouting 2.5.0'")
    s.add_argument("--description")
    s.add_argument("--reference", action="store_true", help="the human layout (original copper)")
    s.add_argument("--adapter", default="freerouting", help="kaebench built-in adapter")
    s.add_argument("--binary", help="router binary (its install dir is copied into the store)")
    s.add_argument("--command", help="kaebench --command template; {code:NAME} is a frozen checkout of code NAME")
    s.add_argument("--kind", default="route", help="route | place | joint")
    s.add_argument("--code", action="append", metavar="NAME=PATH[@REF] | NAME=URL@REF",
                   help="a code component; the harness (this repo, HEAD) is added unless given")
    s.add_argument("--harness", help="harness revision this method runs with (default HEAD)")
    s.add_argument("--param", action="append", metavar="K=V")
    s.add_argument("--timeout", type=int, default=900, help="seconds per attempt (adapter methods)")
    s.add_argument("--kicad-threads", type=int, default=2)
    s.add_argument("--build", help="how the binary was built, e.g. a script and ref")
    s.add_argument("--allow-dirty", action="store_true", help="allow uncommitted or unpushed code (snapshot + patch)")
    s.set_defaults(f=cmd_method_add)
    s = mp.add_parser("list")
    s.set_defaults(f=cmd_method_list)
    s = mp.add_parser("show")
    s.add_argument("id")
    s.set_defaults(f=cmd_method_show)
    ep = sub.add_parser("exp").add_subparsers(dest="sub", required=True)
    s = ep.add_parser("create")
    s.add_argument("name"), s.add_argument("--description")
    s.add_argument("--method", action="append", required=True)
    s.add_argument("--boards", help="ids or @FILE (default: the whole corpus)")
    s.add_argument("--attempts", type=int, default=1)
    s.add_argument("--harness", default="HEAD", help="revision for prepare, the human reference and physics briefs")
    s.add_argument("--kae", default="origin/claude/vigilant-mayer-i91rrr", help="revision with the kae package (physics)")
    s.set_defaults(f=cmd_exp_create)
    s = ep.add_parser("submit")
    s.add_argument("name"), s.add_argument("--only"), s.add_argument("--limit", type=int)
    s.add_argument("--redo", action="store_true", help="also retry boards whose prepare failed")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(f=cmd_exp_submit)
    for n, f in (("status", cmd_exp_status), ("report", cmd_exp_report), ("install-timer", cmd_exp_timer)):
        s = ep.add_parser(n)
        s.add_argument("name")
        s.set_defaults(f=f)
    s = sub.add_parser("job", help="one board (what each queued job runs)")
    s.add_argument("--experiment"), s.add_argument("--board", required=True)
    s.add_argument("--method", action="append", help="run these methods (default: the experiment's missing ones)")
    s.add_argument("--attempt", type=int, default=0)
    s.add_argument("--harness"), s.add_argument("--kae")
    s.add_argument("--repro", action="store_true", help="write a reproduction next to the original run")
    s.set_defaults(f=cmd_job)
    s = sub.add_parser("board", help="every run and score of one board")
    s.add_argument("id")
    s.set_defaults(f=cmd_board)
    s = sub.add_parser("rerun", help="how to reproduce a run; --submit queues the reproduction")
    s.add_argument("run"), s.add_argument("--submit", action="store_true")
    s.set_defaults(f=cmd_rerun)
    s = sub.add_parser("index", help="rebuild index.sqlite")
    s.set_defaults(f=cmd_index)
    a = ap.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
