#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Benchmark campaigns over the local board corpus, run unattended through the kaeq queue.

A campaign routes every corpus board with a fixed set of routers and keeps, per board,
everything needed to compare later methods against it: kaebench scores (score v7: clean,
completion, DRC errors by type, wire length and vias against the human layout), the human
layout scored the same way, routed physics (kae module physics, against the human board),
CPU time and memory of every step, router outcomes, and a bug log for a later fixing agent.

  campaign.py init NAME --router LABEL=PATH [--router ...] [--timeout 900]
  campaign.py submit NAME [--only id,id|@FILE] [--limit N] [--dry-run]
  campaign.py board NAME ID          # one board (what each queued job runs)
  campaign.py status NAME
  campaign.py summarize NAME         # REPORT.md, results.csv, bugs/index.jsonl, bugs/BY-SIGNATURE.md
  campaign.py install-timer NAME     # summarize hourly (systemd --user timer)

Layout (all under $KAE_CAMPAIGNS, default ~/kae-baselines, in the user's home). Board-first:
every campaign adds its results under the board, so all results for one board sit together.
  boards/<id>/board.json             the board's corpus row
  boards/<id>/<NAME>/                record.json (summary), bugs.json, task.json, physics.json,
                                     arms/<arm>/{attempt.json,drc.json,adapter.log.gz,result.json,board.ses.gz}
  campaigns/NAME/campaign.json       settings, routers, frozen code revisions
  campaigns/NAME/code/               frozen checkout of this repo (the harness that runs)
  campaigns/NAME/kae-src/, venv-kae/ frozen kae package for routed physics
  campaigns/NAME/venv-bench/, kicad-config/  kaebench venv; KiCad config (DRC threads capped)
  campaigns/NAME/bugs/, REPORT.md, results.csv   summaries (summarize)
Scratch work happens in $KAEQ_SCRATCH (local disk, deleted by kaeq when the job ends).
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
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.path.expanduser(os.environ.get("KAE_CAMPAIGNS", "~/kae-baselines")))
KAE_HOME = Path(os.path.expanduser(os.environ.get("KAE_HOME", "~/.cache/kaebench")))
CORPUS = Path(os.path.expanduser("~/kae-boards"))
MB = 1 << 20
HUMAN = "human"
AS_LIMIT = 40 * (1 << 30)  # address-space cap for the harness tree (a runaway KiCad DRC once reached 100 GB)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw).stdout.strip()


def croot(name):
    """A campaign's own files: settings, frozen code, venvs, summaries."""
    return ROOT / "campaigns" / name


def bdir(name, bid):
    """One board's results from one campaign."""
    return ROOT / "boards" / bid / name


def load_campaign(name):
    return json.loads((croot(name) / "campaign.json").read_text())


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------ init
def router_version(path):
    try:
        out = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=120).stdout
        m = re.search(r"Freerouting v\S+", out)
        return m.group(0) if m else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cmd_init(a):
    root = croot(a.name)
    if (root / "campaign.json").exists():
        sys.exit(f"{root} exists; pick a new name (campaigns are immutable once started)")
    root.mkdir(parents=True, exist_ok=True)
    repo = Path(sh(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"]))
    code_sha = sh(["git", "-C", str(repo), "rev-parse", a.code_ref])
    kae_sha = sh(["git", "-C", str(repo), "rev-parse", a.kae_ref])
    print(f"freezing harness {code_sha[:7]} and kae {kae_sha[:7]} into {root}")
    sh(["git", "-C", str(repo), "worktree", "add", "--detach", str(root / "code"), code_sha])
    sh(["git", "-C", str(repo), "worktree", "add", "--detach", str(root / "kae-src"), kae_sha])
    uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
    for venv, pkg in (("venv-bench", root / "code" / "bench"), ("venv-kae", f"{root / 'kae-src' / 'kae'}[fast]")):
        subprocess.run([uv, "venv", "-q", "--python", "3.12", str(root / venv)], check=True)
        subprocess.run([uv, "pip", "install", "-q", "-p", str(root / venv / "bin" / "python"), "-e", str(pkg)], check=True)
        if venv == "venv-bench":
            subprocess.run([uv, "pip", "install", "-q", "-p", str(root / venv / "bin" / "python"), "pytest"], check=True)
    cfg = root / "kicad-config"
    src = Path.home() / ".config" / "kicad" / "10.0"
    shutil.copytree(src, cfg / "10.0") if src.is_dir() else (cfg / "10.0").mkdir(parents=True)
    # kicad-cli's thread pool otherwise starts one thread per host CPU in every process
    (cfg / "10.0" / "kicad_advanced").write_text(f"MaximumThreads={a.kicad_threads}\n")
    routers = []
    for spec in a.router:
        label, _, path = spec.partition("=")
        path = os.path.abspath(os.path.expanduser(path))
        jar = next(iter(Path(path).parent.parent.glob("lib/**/*.jar")), None)
        routers.append(dict(label=label, path=path, version=router_version(path),
                            jar_sha256=sha256(jar) if jar else None))
    corpus = Path(os.path.expanduser(a.corpus))
    meta = dict(
        name=a.name, created=now(), corpus=str(corpus), corpus_manifest_sha256=sha256(corpus / "manifest.jsonl"),
        code_sha=code_sha, kae_sha=kae_sha, kae_ref=a.kae_ref, routers=routers, timeout_s=a.timeout, k=1,
        kicad_threads=a.kicad_threads, kinds=["route"], arms=[HUMAN] + [r["label"] for r in routers],
        kicad_wrap=os.environ.get("KAE_KICAD_WRAP") or _env_sh().get("KAE_KICAD_WRAP"),
        notes=a.notes,
    )
    (root / "campaign.json").write_text(json.dumps(meta, indent=1))
    (root / "bugs").mkdir(exist_ok=True)
    (ROOT / "boards").mkdir(exist_ok=True)
    print(json.dumps(meta, indent=1))


def _env_sh():
    """KAE_* settings from the kaebench setup's env.sh (KAE_KICAD_WRAP: KiCad in its container)."""
    out = {}
    p = KAE_HOME / "env.sh"
    if p.exists():
        for line in p.read_text().splitlines():
            m = re.match(r'export (\w+)="?(.*?)"?$', line.strip())
            if m:
                out[m.group(1)] = m.group(2)
    return out


# ------------------------------------------------------------------ submit
def corpus_rows(c):
    with open(Path(c["corpus"]) / "manifest.jsonl") as f:
        return [json.loads(l) for l in f if l.strip()]


def estimate(c, row):
    """Queue resources for one board from its file size (board files range from KB to 230 MB)."""
    pcb = Path(c["corpus"]) / row["path"] / "board.kicad_pcb"
    s = pcb.stat().st_size / MB if pcb.exists() else 1.0
    heap = int(min(16, max(2, 2 + s / 8)))                     # Freerouting -Xmx, GB
    # GB: one step at a time (KiCad pcbnew / DRC, or the router); smoke runs peaked at 0.5-0.9 GB on
    # boards under 5 MB. kaeq requeues a job that overruns 1.5x with a corrected estimate.
    mem = 1.2 + 0.12 * s + 0.3 * heap
    disk = 100 + 10 * s                                          # MB: tasks, three arms' boards and artifacts
    T = c["timeout_s"]
    timeout = int(min(16 * 3600, len(c["routers"]) * T + 3600 + 240 * s))
    return dict(size_mb=round(s, 2), heap_gb=heap, mem=f"{mem:.1f}G", disk=f"{int(disk)}M", timeout=f"{timeout}s")


def cmd_submit(a):
    c = load_campaign(a.name)
    root = croot(a.name)
    rows = corpus_rows(c)
    if a.only:
        ids = set(Path(a.only[1:]).read_text().split()) if a.only.startswith("@") else set(a.only.split(","))
        rows = [r for r in rows if r["id"] in ids]
    if not a.redo:
        rows = [r for r in rows if not (bdir(a.name, r["id"]) / "record.json").exists()]
    # a stable shuffle (sizes mixed, so memory-heavy boards spread over the run); the biggest boards first
    rows.sort(key=lambda r: hashlib.sha1(r["id"].encode()).hexdigest())
    if a.limit:
        rows = rows[:a.limit]
    py = root / "venv-bench" / "bin" / "python"
    script = root / "code" / "tools" / "campaign" / "campaign.py"
    lines = []
    for r in rows:
        e = estimate(c, r)
        lines.append(dict(cmd=f"{py} {script} board {a.name} {r['id']}", name=f"{a.name}:{r['id']}", cpus=2,
                          mem=e["mem"], disk=e["disk"], timeout=e["timeout"], prio=1 if e["size_mb"] > 10 else 0))
    jobs = root / f"jobs-{datetime.now().strftime('%Y%m%dT%H%M%S')}.jsonl"
    jobs.write_text("".join(json.dumps(x) + "\n" for x in lines))
    print(f"{len(lines)} boards -> {jobs}")
    if a.dry_run or not lines:
        return
    subprocess.run(["kaeq", "submit", "--jobs", str(jobs), "--owner", f"campaign-{a.name}", "--tag", a.name,
                    "--live", "--cwd", str(root / "code"), "--retries", "1"], check=True)


# ------------------------------------------------------------------ one board
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
                                     cpu_s=round(r.ru_utime + r.ru_stime - self.r0.ru_utime - self.r0.ru_stime, 2),
                                     max_rss_mb=round(r.ru_maxrss / 1024, 1))


def _limit_as():
    try:
        resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))
    except (ValueError, OSError):
        pass


def run_logged(cmd, log, env, timeout, cwd=None):
    """Run cmd with output appended to log; returns (rc, timed_out)."""
    with open(log, "ab") as f:
        f.write(f"\n$ {' '.join(map(str, cmd))}\n".encode())
        f.flush()
        p = subprocess.Popen([str(x) for x in cmd], stdout=f, stderr=subprocess.STDOUT, env=env, cwd=cwd,
                             preexec_fn=_limit_as, start_new_session=True)
        try:
            return p.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, 9)
            p.wait()
            return None, True


def gz(src, dst):
    with open(src, "rb") as fi, gzip.open(dst, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo)


def tail(path, n=40):
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def cmd_board(a):
    c = load_campaign(a.name)
    root = croot(a.name)
    bid = a.id
    row = next((r for r in corpus_rows(c) if r["id"] == bid), None)
    if row is None:
        sys.exit(f"{bid}: not in the corpus manifest")
    est = estimate(c, row)
    t_start = time.monotonic()
    ws = Path(os.environ.get("KAEQ_SCRATCH") or tempfile.mkdtemp(prefix=f"kae-{bid[:20]}-", dir="/var/tmp"))
    ws.mkdir(parents=True, exist_ok=True)
    src = ws / "src" / bid
    src.mkdir(parents=True)
    corpus_dir = Path(c["corpus"]) / row["path"]
    for p in corpus_dir.iterdir():
        if p.name.startswith("board.") or p.name == "row.json":
            os.symlink(p, src / p.name)
    work = ws / "w"
    env = dict(os.environ)
    env.update({k: v for k, v in _env_sh().items() if k not in env})
    binds = [b for b in env.get("APPTAINER_BIND", "").split(",") if b]
    env["APPTAINER_BIND"] = ",".join(dict.fromkeys(binds + [str(ws), str(Path(c["corpus"]).resolve())]))
    env["KICAD_CONFIG_HOME"] = str(root / "kicad-config")
    env["KAE_DRC_TIMEOUT"] = str(900 if est["size_mb"] < 20 else 3600)
    env["JAVA_TOOL_OPTIONS"] = f"-Xmx{est['heap_gb']}g -XX:ActiveProcessorCount=2"
    env["PATH"] = f"{root / 'venv-bench' / 'bin'}:{env.get('PATH', '')}"
    env.pop("VIRTUAL_ENV", None)
    kb = [str(root / "venv-bench" / "bin" / "kaebench"), "--workdir", str(work)]
    log = ws / "campaign.log"
    print(f"{bid}: pid {os.getpid()} ppid {os.getppid()} job {os.environ.get('KAEQ_JOB')} scratch {ws}", flush=True)
    # The environment must work before a board's failure can be blamed on the board: a broken
    # container or bind is an infrastructure failure (non-zero exit: kaeq retries and reports it).
    pre = subprocess.run([*env.get("KAE_KICAD_WRAP", "").split(), "python3", "-c", "import pcbnew"],
                         capture_output=True, text=True, env=env, timeout=600)
    if pre.returncode != 0:
        print(f"preflight failed: KiCad's Python cannot import pcbnew (rc {pre.returncode}):\n{pre.stderr[-2000:]}", flush=True)
        return 75
    steps = {}
    rec = dict(id=bid, campaign=a.name, started=now(), host_job=os.environ.get("KAEQ_JOB"), estimate=est,
               corpus=dict((k, row.get(k)) for k in ("collection", "license_tier", "layers", "footprints", "nets", "tracks",
                                                       "vias", "zones", "routed", "tags", "source")),
               steps=steps, arms={})
    bugs = []

    def bug(arm, category, detail, signature=None, evidence=(), **extra):
        sig = signature or f"{arm}:{category}"
        bugs.append(dict(campaign=a.name, board=bid, arm=arm, category=category, signature=sig,
                         detail=str(detail)[:4000], evidence=list(evidence), **extra))

    # 1. prepare the route task (convert to KiCad 10, DRC the human layout, strip copper)
    with Step("prepare", steps):
        rc, to = run_logged(kb + ["prepare-dir", "--dir", ws / "src", "--board-glob", "board.kicad_pcb",
                                  "--only", bid, "--kinds", "route", "-j", "1"], log, env,
                            timeout=int(est["timeout"][:-1]) // 2)
    task = work / "tasks" / bid
    tj = task / "task.json"
    infra = re.search(r"no Python with pcbnew|kicad-cli not found|FATAL: +container|apptainer.*FATAL", tail(log, 200))
    if not tj.exists() and infra:
        print(f"prepare hit an environment error, not a board error: {infra.group(0)}\n{tail(log, 30)}", flush=True)
        return 75
    if not tj.exists():
        rec["status"] = "prepare_failed"
        bug("harness", "prepare_timeout" if to else "prepare_error",
            _first_error(tail(log, 200)) or f"rc={rc}", signature=f"harness:prepare:{_normalize(_first_error(tail(log, 200)))}",
            evidence=["prepare.log.gz"], log_tail=tail(log, 60))
        return _archive(root, bid, rec, bugs, ws, task, {}, log, t_start, row=row)
    record = json.loads(tj.read_text())
    rec["task"] = dict(split=record["split"], pads=record["reference"]["stats"].get("pads"),
                       human_clean=record["human_clean"], qualified=record["qualified"],
                       human_drc=record["reference"]["drc"], start_unconnected=record["tasks"]["route"]["input_drc"]["unconnected"],
                       roundtrip=(record.get("roundtrip") or {}).get("route"))

    # 2. route: the human layout (reference) and every router, interleaved, scored by kaebench
    arms = ["--arm", f"name={HUMAN},adapter=reference"]
    for r in c["routers"]:
        arms += ["--arm", f"name={r['label']},adapter=freerouting,freerouting={r['path']}"]
    with Step("run", steps):
        rc, to = run_logged(kb + ["run", *arms, "--kinds", "route", "-k", "1", "--timeout", str(c["timeout_s"]),
                                  "--all", "--only", bid, "--name", "base", "-j", "1"], log, env,
                            timeout=int(est["timeout"][:-1]))
    if rc != 0:
        bug("harness", "run_timeout" if to else "run_error", _first_error(tail(log, 200)) or f"rc={rc}",
            evidence=["campaign.log.gz"], log_tail=tail(log, 60))
    run_dir = work / "results" / "base"
    adirs = {arm: run_dir / arm / "route" / bid / "attempt-0" for arm in c["arms"]}
    for arm, adir in adirs.items():
        aj = adir / "attempt.json"
        if aj.exists():
            rec["arms"][arm] = json.loads(aj.read_text())

    # 3. routed physics of every scored board, against the human board's modules
    boards = {}
    if (task / "reference" / "board.kicad_pcb").exists():
        boards[HUMAN] = task / "reference" / "board.kicad_pcb"
    for arm in c["routers"]:
        p = adirs[arm["label"]] / "score" / "board.kicad_pcb"
        if p.exists() and (rec["arms"].get(arm["label"]) or {}).get("status") == "ok":
            boards[arm["label"]] = p
    phys = {}
    if boards:
        pout = ws / "physics.json"
        with Step("physics", steps):
            rc, to = run_logged([root / "venv-kae" / "bin" / "python", root / "code" / "tools" / "campaign" / "physics_board.py",
                                 "--input", task / "route" / "input" / "board.kicad_pcb",
                                 *[x for n, p in boards.items() for x in ("--board", f"{n}={p}")], "--out", pout],
                                log, env, timeout=1800 + 120 * int(est["size_mb"]))
        if pout.exists():
            phys = json.loads(pout.read_text())
        else:
            phys = dict(error=f"physics step {'timed out' if to else f'failed rc={rc}'}")
        if phys.get("error"):
            bug("physics", "physics_error", phys["error"], signature=f"physics:board:{_normalize(phys['error'])}",
                evidence=["physics.json"], traceback=phys.get("traceback"))
        for n, b in (phys.get("boards") or {}).items():
            if b.get("error"):
                bug("physics", "physics_error", b["error"], signature=f"physics:{_normalize(b['error'])}",
                    evidence=["physics.json"], measured=n, traceback=b.get("traceback"))
    rec["physics"] = {n: {k: v for k, v in b.items() if k != "modules" and k != "traceback"}
                      for n, b in (phys.get("boards") or {}).items()}
    _physics_ratios(rec, phys)

    # 4. bugs and outcomes per arm
    human_types = ((rec["arms"].get(HUMAN) or {}).get("score") or {}).get("errors_by_type") or {}
    for arm in c["arms"]:
        row_a = rec["arms"].get(arm)
        if row_a is None:
            bug(arm if arm == HUMAN else "harness", "attempt_missing", "kaebench wrote no attempt.json",
                evidence=["campaign.log.gz"])
            continue
        _arm_bugs(bug, arm, row_a, adirs[arm], human_types)
    return _archive(root, bid, rec, bugs, ws, task, adirs, log, t_start, phys, row=row)


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


def _arm_bugs(bug, arm, row, adir, human_types):
    st = row.get("status")
    meta = row.get("adapter_meta") or {}
    s = row.get("score") or {}
    log = ""
    if (adir / "adapter.log").exists():
        log = (adir / "adapter.log").read_text(errors="replace")
    ev = [f"arms/{arm}/attempt.json", f"arms/{arm}/adapter.log.gz"]
    if st == "score_error":
        bug("harness", "score_error", row.get("error"), signature=f"harness:score_error:{_normalize(row.get('error'))}",
            evidence=ev + [f"arms/{arm}/score_error.log"], scored_arm=arm)
    if arm == HUMAN:
        return
    rep = meta.get("router_report") or {}
    if st == "adapter_error":
        err = row.get("error") or ""
        cat = "ses_import_error" if "import-ses" in err or "import" in err.lower() else "adapter_error"
        bug(arm, cat, err, signature=f"{arm}:{cat}:{_normalize(err)}", evidence=ev + [f"arms/{arm}/artifacts"])
    elif st == "no_output":
        if meta.get("ses_empty") or meta.get("ses_cut"):
            cat = "ses_incomplete"
        elif meta.get("timed_out"):
            cat = "no_output_at_deadline"  # the router ignored its own job timeout and wrote nothing
        elif meta.get("rc") not in (0, None):
            cat = "router_crash"
        else:
            cat = "no_output"
        bug(arm, cat, f"rc={meta.get('rc')} timed_out={meta.get('timed_out')} final_state={rep.get('final_state')}\n"
            + "\n".join(log.splitlines()[-30:]), signature=f"{arm}:{cat}", evidence=ev + [f"arms/{arm}/artifacts"])
    for cls, e in _java_exceptions(log).items():
        cat = "java_oom" if "OutOfMemoryError" in cls else "java_exception"
        bug(arm, cat, e["line"], signature=f"{arm}:{cat}:{cls}:{e['frame']}", exception=cls, count=e["count"],
            frame=e["frame"], evidence=ev + [f"arms/{arm}/artifacts"])
    # the router's own count of open connections vs KiCad's on the imported board: more open in KiCad
    # means connections were lost in translation (DSN export, SES import) or routed copper is illegal there
    own_open = ((rep.get("board_statistics") or {}).get("connections") or {}).get("incomplete_count")
    if st == "ok" and own_open is not None and s.get("unconnected") is not None and s["unconnected"] > own_open:
        bug(arm, "unconnected_mismatch", f"KiCad finds {s['unconnected']} unconnected, the router reported {own_open} incomplete",
            signature=f"{arm}:unconnected_mismatch", count=s["unconnected"] - own_open,
            evidence=ev + [f"arms/{arm}/result.json", f"arms/{arm}/board.ses.gz"])
    if row.get("over_time"):
        bug(arm, "over_time", f"runtime {row.get('runtime_s')}s exceeded the attempt timeout", evidence=ev)
    if s and s.get("valid") is False:
        bad = [k for k, v in (s.get("integrity") or {}).items() if not v]
        bug(arm, "integrity", f"invalid output: {bad} foreign={(s.get('foreign') or {}).get('by_kind')}",
            signature=f"{arm}:integrity:{','.join(sorted(bad))}", evidence=ev + [f"arms/{arm}/drc.json"])
    # DRC errors the router created: per type, beyond what the human layout has on the same board
    for typ, n in sorted((s.get("errors_by_type") or {}).items()):
        extra = n - human_types.get(typ, 0)
        if extra > 0:
            bug(arm, "drc", f"{extra} {typ} error(s) beyond the human layout's {human_types.get(typ, 0)}",
                signature=f"{arm}:drc:{typ}", drc_type=typ, count=extra, evidence=[f"arms/{arm}/drc.json", f"arms/{arm}/board.ses.gz"])


def _physics_ratios(rec, phys):
    """Per arm: physics_total relative to the human board's, and the median module value ratio."""
    b = phys.get("boards") or {}
    h = b.get(HUMAN) or {}
    for n, x in b.items():
        if n == HUMAN or x.get("error") or h.get("error") or not h:
            continue
        r = rec["physics"][n]
        if h.get("physics_total"):
            r["total_vs_human"] = round(x["physics_total"] / h["physics_total"], 4)
        ratios = [m["value"] / hm["value"] for k, m in (x.get("modules") or {}).items()
                  if m.get("value") and not m.get("open_hops")
                  and (hm := (h.get("modules") or {}).get(k) or {}).get("value") and not hm.get("open_hops")]
        r["module_ratios"] = len(ratios)
        r["module_ratio_median"] = round(statistics.median(ratios), 4) if ratios else None


def _archive(root, bid, rec, bugs, ws, task, adirs, log, t_start, phys=None, row=None):
    """Copy what is worth keeping into the board's folder (home), atomically per campaign."""
    dest = bdir(rec["campaign"], bid)
    tmp = dest.parent / f".tmp-{rec['campaign']}-{os.getpid()}"
    if row is not None and not (dest.parent / "board.json").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        (dest.parent / "board.json").write_text(json.dumps(row, indent=1))
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    if (task / "task.json").exists():
        shutil.copy2(task / "task.json", tmp / "task.json")
    if task.exists() and (task / "reference" / "drc.json").exists():
        gz(task / "reference" / "drc.json", tmp / "human-drc.json.gz")
    buggy = {b["arm"] for b in bugs if b["category"] not in ("drc",)}
    for arm, adir in adirs.items():
        if not adir.exists():
            continue
        d = tmp / "arms" / arm
        d.mkdir(parents=True)
        for name in ("attempt.json", "score_error.log"):
            if (adir / name).exists():
                shutil.copy2(adir / name, d / name)
        if (adir / "score" / "drc.json").exists():
            shutil.copy2(adir / "score" / "drc.json", d / "drc.json")
        if (adir / "adapter.log").exists():
            gz(adir / "adapter.log", d / "adapter.log.gz")
        art = adir / "artifacts"
        if (art / "result.json").exists():
            shutil.copy2(art / "result.json", d / "result.json")
        if (art / "board.ses").exists():
            gz(art / "board.ses", d / "board.ses.gz")
        if arm in buggy and art.exists():  # the router's exact input, to reproduce the bug without KiCad
            (d / "artifacts").mkdir()
            for p in art.iterdir():
                if p.is_file() and p.name != "result.json":
                    gz(p, d / "artifacts" / (p.name + ".gz"))
    if phys:
        (tmp / "physics.json").write_text(json.dumps(phys, indent=1, default=str))
    gz(log, tmp / "campaign.log.gz") if log.exists() else None
    if rec.get("status") == "prepare_failed" and log.exists():
        gz(log, tmp / "prepare.log.gz")
    rec.setdefault("status", "done")
    rec["finished"] = now()
    rec["wall_s"] = round(time.monotonic() - t_start, 1)
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    rec["cpu_s"] = round(r.ru_utime + r.ru_stime, 1)
    rec["bugs"] = len(bugs)
    (tmp / "bugs.json").write_text(json.dumps(bugs, indent=1))
    (tmp / "record.json").write_text(json.dumps(rec, indent=1, default=str))  # written last: marks the board done
    if dest.exists():
        shutil.rmtree(dest)
    os.replace(tmp, dest)
    shutil.rmtree(ws / "w", ignore_errors=True)
    print(f"{bid}: {rec['status']} in {rec['wall_s']}s, {len(bugs)} bug record(s) -> {dest}")
    return 0


# ------------------------------------------------------------------ status / summarize
def records(name):
    out = []
    for p in sorted((ROOT / "boards").glob(f"*/{name}/record.json")):
        try:
            out.append((json.loads(p.read_text()), json.loads((p.parent / "bugs.json").read_text())))
        except (OSError, ValueError):
            pass
    return out


def cmd_status(a):
    c = load_campaign(a.name)
    root = croot(a.name)
    total = len(corpus_rows(c))
    recs = records(a.name)
    st = Counter(r["status"] for r, _ in recs)
    print(f"{a.name}: {len(recs)}/{total} boards done ({dict(st)}), {sum(len(b) for _, b in recs)} bug records")
    subprocess.run(["kaeq", "status", "--owner", f"campaign-{a.name}", "--limit", "5"])


def flat(rec, arm):
    row = rec["arms"].get(arm) or {}
    s = row.get("score") or {}
    m = row.get("adapter_meta") or {}
    rep = m.get("router_report") or {}
    t = rec.get("task") or {}
    ph = (rec.get("physics") or {}).get(arm) or {}
    mu = row.get("method_usage") or {}
    su = row.get("scoring_usage") or {}
    co = rec.get("corpus") or {}
    return dict(
        board=rec["id"], arm=arm, board_status=rec["status"], split=t.get("split"), pads=t.get("pads"),
        layers=co.get("layers"), footprints=co.get("footprints"), nets=co.get("nets"), collection=co.get("collection"),
        license_tier=co.get("license_tier"), human_clean=t.get("human_clean"), qualified=t.get("qualified"),
        status=row.get("status"), valid=s.get("valid"), clean=s.get("clean"), completion=s.get("completion"),
        start_unconnected=s.get("start_unconnected"), unconnected=s.get("unconnected"), errors=s.get("errors"),
        warnings=s.get("warnings"), errors_by_type=json.dumps(s.get("errors_by_type") or {}, sort_keys=True),
        track_length_mm=s.get("track_length_mm"), vias=s.get("vias"), wl_ratio=s.get("wl_ratio"), via_delta=s.get("via_delta"),
        runtime_s=row.get("runtime_s"), cpu_s=mu.get("cpu_s"), max_rss_mb=mu.get("max_rss_mb"),
        scoring_s=row.get("scoring_s"), scoring_cpu_s=su.get("cpu_s"),
        timed_out=m.get("timed_out"), partial=m.get("partial"), final_state=rep.get("final_state"), passes=m.get("passes"),
        router_incomplete=((rep.get("board_statistics") or {}).get("connections") or {}).get("incomplete_count"),
        router_introduced_violations=((rep.get("board_statistics") or {}).get("clearance_violations") or {}).get("router_introduced_count"),
        router_peak_heap_mb=((rep.get("phases") or {}).get("autorouter") or {}).get("peak_heap_mb"),
        physics_total=ph.get("physics_total"), physics_vs_human=ph.get("total_vs_human"),
        module_ratio_median=ph.get("module_ratio_median"), physics_modules=ph.get("n_modules"),
        physics_missing=ph.get("n_missing"), physics_open=ph.get("n_open"), worst_rail_mohm=ph.get("worst_rail_mohm"),
        physics_error=ph.get("error"), board_wall_s=rec.get("wall_s"), board_cpu_s=rec.get("cpu_s"),
    )


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


def arm_table(rows, arms, title):
    out = [f"### {title}", "", "| arm | boards | ok | cp1 (clean) | completion | not closed | DRC errors / board | "
           "timeouts | no output | errors | CPU s median / p90 / total h | physics Σu | Σu vs human (median) | module ratio (median) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        ok = [r for r in rs if r["status"] == "ok"]
        cpu = [r["cpu_s"] for r in rs]
        out.append("| " + " | ".join([
            arm, str(len(rs)), str(len(ok)),
            _f(_mean([1.0 if r["clean"] else 0.0 for r in rs])),
            _f(_mean([r["completion"] if r["completion"] is not None else 0.0 for r in rs])),
            str(sum(1 for r in ok if (r["unconnected"] or 0) > 0)),
            _f(_mean([r["errors"] for r in ok]), 2),
            str(sum(1 for r in rs if r["timed_out"] or r["partial"])),
            str(sum(1 for r in rs if r["status"] == "no_output")),
            str(sum(1 for r in rs if r["status"] in ("adapter_error", "score_error"))),
            f"{_f(_med(cpu), 1)} / {_f(_q(cpu, 0.9), 1)} / {_f(sum(x or 0 for x in cpu) / 3600, 1)}",
            _f(_mean([r["physics_total"] for r in rs]), 3),
            _f(_med([r["physics_vs_human"] for r in rs]), 3),
            _f(_med([r["module_ratio_median"] for r in rs]), 3)]) + " |")
    return out + [""]


def cmd_summarize(a):
    c = load_campaign(a.name)
    root = croot(a.name)
    recs = records(a.name)
    total = len(corpus_rows(c))
    arms = c["arms"]
    rows = [flat(r, arm) for r, _ in recs for arm in arms if r["status"] != "prepare_failed"]
    with open(root / "results.csv.tmp", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(flat({"id": "", "status": "", "arms": {}}, HUMAN).keys()))
        w.writeheader()
        w.writerows(rows)
    os.replace(root / "results.csv.tmp", root / "results.csv")
    bugs = [b for _, bs in recs for b in bs]
    with open(root / "bugs" / "index.jsonl.tmp", "w") as f:
        for b in bugs:
            f.write(json.dumps({k: v for k, v in b.items() if k not in ("traceback", "log_tail")}) + "\n")
    os.replace(root / "bugs" / "index.jsonl.tmp", root / "bugs" / "index.jsonl")
    # bugs grouped by signature, most boards first: the work list for a fixing agent
    groups = defaultdict(list)
    for b in bugs:
        groups[b["signature"]].append(b)
    bl = [f"# Bugs by signature: {a.name}", "",
          f"{len(bugs)} records in {len(groups)} signatures over {sum(1 for _, bs in recs if bs)} boards. "
          f"Evidence paths are relative to `~/kae-baselines/boards/<board>/{a.name}/`. Full records: `bugs/index.jsonl`; "
          f"per board with tracebacks and log tails: `boards/<board>/{a.name}/bugs.json`.", "",
          "| signature | boards | records | count | example boards | example detail |", "|---|---|---|---|---|---|"]
    for sig, bs in sorted(groups.items(), key=lambda kv: (-len({b["board"] for b in kv[1]}), kv[0])):
        boards = sorted({b["board"] for b in bs})
        bl.append(f"| `{sig[:120]}` | {len(boards)} | {len(bs)} | {sum(b.get('count', 1) for b in bs)} | "
                  f"{', '.join(boards[:3])} | {bs[0]['detail'].splitlines()[0][:160] if bs[0]['detail'] else ''} |")
    (root / "bugs" / "BY-SIGNATURE.md").write_text("\n".join(bl) + "\n")
    # report
    st = Counter(r["status"] for r, _ in recs)
    rep = [f"# Campaign {a.name}", "",
           f"Generated {now()}. Boards done: {len(recs)} / {total} ({dict(st)}). Router timeout {c['timeout_s']} s, k = 1, "
           f"score v7 (kaebench at {c['code_sha'][:7]}), routed physics from kae at {c['kae_sha'][:7]}, KiCad DRC threads "
           f"{c['kicad_threads']}.", "",
           "Routers: " + "; ".join(f"`{r['label']}` = {r['version']} ({r['path']})" for r in c["routers"]) + ".", "",
           "Columns: cp1 = share of boards routed clean (valid, 0 unconnected, 0 DRC errors) on the single attempt; "
           "completion = share of initially unconnected items routed (0 for no output); not closed = boards with unconnected "
           "items left; timeouts = router stopped at its deadline (partial); CPU s = the method's own processes (router, "
           "DSN export, SES import), not scoring; physics Σu = kae module physics total (lower is better; modules without a "
           "value count 3), Σu vs human = per-board ratio to the human board's Σu; module ratio = per-board median of router "
           "module value / human module value over modules routed in both (lower is better). The `human` arm is the original "
           "copper scored the same way.", ""]
    rep += arm_table(rows, arms, "All boards")
    rep += arm_table([r for r in rows if r["human_clean"]], arms, "Boards whose human layout is DRC-clean")
    for sp in ("A", "B", "C"):
        rep += arm_table([r for r in rows if r["split"] == sp], arms, f"Split {sp} ({'≤ 31' if sp == 'A' else '≤ 100' if sp == 'B' else '> 100'} pads)")
    for lab, test in (("2 layers", lambda n: n == 2), ("4 layers", lambda n: n == 4), ("6+ layers", lambda n: (n or 0) >= 6)):
        rep += arm_table([r for r in rows if test(r["layers"])], arms, lab)
    rep += ["### DRC error types (all boards, errors on ok attempts)", "", "| type | " + " | ".join(arms) + " |",
            "|---|" + "---|" * len(arms)]
    per = {arm: Counter() for arm in arms}
    for r in rows:
        if r["status"] == "ok":
            per[r["arm"]].update(json.loads(r["errors_by_type"]))
    for typ in sorted(set().union(*per.values()), key=lambda t: -sum(per[a][t] for a in arms))[:25]:
        rep.append(f"| {typ} | " + " | ".join(str(per[a][typ]) for a in arms) + " |")
    rep += ["", "### Router final states", "", "| arm | " + " | ".join(["COMPLETED", "TIMED_OUT", "other", "none"]) + " |", "|---|---|---|---|---|"]
    for arm in c["routers"]:
        fs = Counter((r["final_state"] or "none") for r in rows if r["arm"] == arm["label"])
        other = sum(v for k, v in fs.items() if k not in ("COMPLETED", "TIMED_OUT", "none"))
        rep.append(f"| {arm['label']} | {fs['COMPLETED']} | {fs['TIMED_OUT']} | {other} | {fs['none']} |")
    rep += ["", "### Bugs", "", f"{len(bugs)} records, {len(groups)} signatures; top 15 (full list: `bugs/BY-SIGNATURE.md`):", ""]
    rep += bl[5:5 + 2 + 15]
    rep += ["", "### Machine time", "",
            f"Board jobs: wall {sum(r.get('wall_s') or 0 for r, _ in recs) / 3600:.1f} h, CPU {sum(r.get('cpu_s') or 0 for r, _ in recs) / 3600:.1f} h "
            f"(prepare, three scored arms, physics). Steps (mean wall s): " + ", ".join(
                f"{k} {_mean([(r.get('steps') or {}).get(k, {}).get('wall_s') for r, _ in recs]) or 0:.0f}"
                for k in ("prepare", "run", "physics")), ""]
    (root / "REPORT.md").write_text("\n".join(rep) + "\n")
    print(f"wrote {root / 'REPORT.md'}, results.csv ({len(rows)} rows), bugs/ ({len(bugs)} records)")


def cmd_install_timer(a):
    root = croot(a.name)
    d = Path.home() / ".config" / "systemd" / "user"
    d.mkdir(parents=True, exist_ok=True)
    unit = f"kae-campaign-{a.name}"
    (d / f"{unit}.service").write_text(
        f"[Unit]\nDescription=summarize campaign {a.name}\n\n[Service]\nType=oneshot\nNice=19\n"
        f"ExecStart={root / 'venv-bench' / 'bin' / 'python'} {root / 'code' / 'tools' / 'campaign' / 'campaign.py'} summarize {a.name}\n")
    (d / f"{unit}.timer").write_text(f"[Unit]\nDescription=summarize campaign {a.name} hourly\n\n[Timer]\nOnBootSec=10min\n"
                                     "OnUnitActiveSec=1h\n\n[Install]\nWantedBy=timers.target\n")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{unit}.timer"], check=True)
    print(f"enabled {unit}.timer (stop: systemctl --user disable --now {unit}.timer)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("name")
    s.add_argument("--router", action="append", required=True, metavar="LABEL=PATH")
    s.add_argument("--timeout", type=int, default=900, help="seconds per router attempt")
    s.add_argument("--corpus", default=str(CORPUS))
    s.add_argument("--code-ref", default="HEAD", help="revision of this repo the campaign runs (frozen)")
    s.add_argument("--kae-ref", default="origin/claude/vigilant-mayer-i91rrr", help="revision with the kae package (physics)")
    s.add_argument("--kicad-threads", type=int, default=2)
    s.add_argument("--notes", default="")
    s.set_defaults(f=cmd_init)
    s = sub.add_parser("submit")
    s.add_argument("name"), s.add_argument("--only"), s.add_argument("--limit", type=int)
    s.add_argument("--redo", action="store_true", help="also boards that already have a record")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(f=cmd_submit)
    s = sub.add_parser("board")
    s.add_argument("name"), s.add_argument("id")
    s.set_defaults(f=cmd_board)
    for n, f in (("status", cmd_status), ("summarize", cmd_summarize), ("install-timer", cmd_install_timer)):
        s = sub.add_parser(n)
        s.add_argument("name")
        s.set_defaults(f=f)
    a = ap.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
