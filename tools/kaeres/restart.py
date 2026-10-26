# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restart portfolio for any method: the same schedule as kae.route.portfolio, judged by KiCad.

    restart.py --input IN --output OUT --time T [--seed S] [--parallel P] [--first-s F] [--growth G]
               -- COMMAND...

COMMAND is one attempt of the method, run with `sh -c` in its own directory, with @IN@, @OUT@,
@SEED@ and @TIME@ replaced. `parallel` attempts run at once; attempt k gets seed S*1000+k and a
budget of F * G**(k // P) seconds (a doubling schedule: a board that needs one long attempt
still gets one). Each finished attempt is checked with kicad-cli DRC (errors, then unconnected
items, zones refilled, the input's project rules). The first clean one ends the run; otherwise
the best is kept when time runs out. Only stdlib; KiCad comes from KAE_KICAD_WRAP.

Work is measured, since a sandboxed method's processes are invisible to the harness: every
attempt's process session is sampled from /proc each second (CPU seconds summed over all its
processes, peak RSS), and the DRC judging is counted separately. The totals go to
restarts/summary.json and to a last stdout line `KAE_WORK {json}` that kaeres records.
"""
import argparse
import resource
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

GRACE_S = 30.0  # an attempt is killed this long after its own budget


def log(msg):
    print(f"[restart {time.strftime('%H:%M:%S')}] {msg}", flush=True)


TICK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")


class Meter:
    """CPU and memory of process sessions, by sampling /proc (processes that live < 1 s between
    samples are missed; their CPU is small)."""

    def __init__(self):
        self.cpu = {}   # sid -> {pid: cpu ticks last seen}
        self.rss = {}   # sid -> peak summed RSS bytes

    def sample(self, sids):
        now = {sid: 0 for sid in sids}
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                f = open(f"/proc/{d}/stat").read()
            except OSError:
                continue
            x = f[f.rindex(")") + 2:].split()
            sid = int(x[3])
            if sid in now:
                self.cpu.setdefault(sid, {})[int(d)] = int(x[11]) + int(x[12])
                now[sid] += int(x[21]) * PAGE
        for sid, r in now.items():
            self.rss[sid] = max(self.rss.get(sid, 0), r)

    def cpu_s(self, sid):
        return round(sum(self.cpu.get(sid, {}).values()) / TICK, 1)

    def rss_mb(self, sid):
        return round(self.rss.get(sid, 0) / 2 ** 20)


def child_cpu():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


ENV_DEPENDENT_CHECKS = ("lib_footprint_issues", "lib_footprint_mismatch")  # as kaebench.tools: not the board's


def drc(board, inp, timeout):
    """{type: count} of DRC errors (env-dependent checks dropped) and the unconnected count of a
    board by kicad-cli, with the input's project rules; None when there is no usable board."""
    if not board.exists() or board.stat().st_size == 0:
        return None
    for ext in (".kicad_pro", ".kicad_dru"):  # the task's rules, never the method's copy
        src = inp.with_suffix(ext)
        if src.exists():
            shutil.copy2(src, board.with_suffix(ext))
    rep = board.with_name("drc.json")
    cmd = [*shlex.split(os.environ.get("KAE_KICAD_WRAP", "")), "kicad-cli", "pcb", "drc", "--format", "json",
           "--severity-error", "--refill-zones", "--output", str(rep), str(board)]
    try:
        subprocess.run(cmd, capture_output=True, timeout=max(60, timeout))
        r = json.loads(rep.read_text())
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    types = {}
    for v in r.get("violations", []):
        if v.get("severity", "error") == "error" and v.get("type") not in ENV_DEPENDENT_CHECKS:
            types[v.get("type")] = types.get(v.get("type"), 0) + 1
    return dict(types=types, unconnected=len(r.get("unconnected_items", [])))


NUM = r"(-?[0-9.]+)"


def outside(board):
    """Unlocked footprints whose anchor lies outside the Edge.Cuts bounding box (a part left staged
    off the board, which DRC does not flag): a cheap stand-in for the harness's legality check.
    Locked parts are the task's fixed interface and may overhang the edge."""
    txt = board.read_text(errors="replace")
    pts = [(float(x), float(y)) for m in re.finditer(r"\((?:gr_line|gr_arc|gr_rect|gr_poly|gr_circle)\b(.*?)\(layer \"Edge\.Cuts\"\)", txt, re.S)
           for x, y in re.findall(r"\((?:start|end|mid|xy|center) " + NUM + " " + NUM, m.group(1))]
    if not pts:
        return 0
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    n = 0
    for m in re.finditer(r"\(footprint \"[^\"]*\"(.*?)\(at " + NUM + " " + NUM, txt, re.S):
        x, y = float(m.group(2)), float(m.group(3))
        n += "(locked" not in m.group(1) and not (x0 <= x <= x1 and y0 <= y <= y1)
    return n


def judge(board, inp, base, timeout, placement=False):
    """Rank key (lower is better) in the harness's order: legal, clean, then fewer unconnected,
    then fewer DRC errors beyond the input's own (per type). None when there is no board."""
    d = drc(board, inp, timeout)
    if d is None:
        return None
    new = sum(max(0, c - base.get(t, 0)) for t, c in d["types"].items())
    out = outside(board) if placement else 0
    clean = out == 0 and new == 0 and d["unconnected"] == 0
    return (1 if out else 0, 0 if clean else 1, d["unconnected"], new, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--time", type=float, required=True, help="wall seconds for everything")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--first-s", type=float, default=60.0)
    ap.add_argument("--growth", type=float, default=2.0)
    ap.add_argument("--scale-first", action="store_true",
                    help="first-s x sqrt(footprints / 40) when above 1: big boards need longer single attempts")
    ap.add_argument("--check-placement", action="store_true",
                    help="methods that place: unlocked parts outside the outline make an attempt illegal")
    ap.add_argument("--max-attempts", type=int, default=0,
                    help="stop launching after this many (deterministic methods: 1); 0 = no limit")
    ap.add_argument("--slack", type=float, default=1.0,
                    help="an attempt may run budget x slack before it is killed (methods whose budget is "
                         "solver CPU time and that spend more on KiCad I/O around it)")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = " ".join(a.command[1:] if a.command[:1] == ["--"] else a.command)
    inp, out = Path(a.input).resolve(), Path(a.output).resolve()
    wd = Path.cwd() / "restarts"
    wd.mkdir(exist_ok=True)
    t0 = time.monotonic()
    if a.scale_first:
        nfp = inp.read_text(errors="replace").count("(footprint ")
        a.first_s *= max(1.0, nfp / 40) ** 0.5
        log(f"{nfp} footprints: first wave {a.first_s:.0f}s")
    # leave room for the last attempt's DRC and the copy
    deadline = t0 + a.time - min(0.25 * a.time, 60 + 0.05 * a.time)
    base_dir = wd / "input"  # the input's own DRC errors (silk, rules) are not the method's
    base_dir.mkdir(exist_ok=True)
    shutil.copy2(inp, base_dir / "board.kicad_pcb")
    b0 = drc(base_dir / "board.kicad_pcb", inp, 0.2 * a.time)
    base = (b0 or {}).get("types", {})
    log(f"input DRC errors by type: {base}")
    running, done, k = {}, [], 0
    best = None
    meter, judge_cpu, judge_wall = Meter(), 0.0, 0.0
    fast_fails = 0  # attempts in a row that died within seconds without a board: a broken command

    def launch():
        nonlocal k
        # the method's budget follows the schedule; slack only lets an attempt run past it (up to
        # the overall deadline), it does not shrink the budget of late attempts
        b = min(a.first_s * a.growth ** (k // a.parallel), deadline - time.monotonic())
        if b < 20 or (a.max_attempts and k >= a.max_attempts):
            return False
        d = wd / f"a{k}"
        d.mkdir(exist_ok=True)
        o = d / "board.kicad_pcb"
        s = a.seed * 1000 + k
        c = cmd.replace("@IN@", shlex.quote(str(inp))).replace("@OUT@", shlex.quote(str(o)))
        c = c.replace("@SEED@", str(s)).replace("@TIME@", str(int(b)))
        p = subprocess.Popen(["sh", "-c", c], cwd=d, stdout=open(d / "log", "w"), stderr=subprocess.STDOUT,
                             start_new_session=True)
        running[p] = dict(k=k, seed=s, budget=round(b), out=o, t=time.monotonic())
        log(f"start #{k} seed {s} budget {b:.0f}s")
        k += 1
        return True

    def stop(p):
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()

    while launch() if len(running) < a.parallel else False:
        pass
    while running:
        time.sleep(1)
        meter.sample([p.pid for p in running])
        now = time.monotonic()
        for p, info in list(running.items()):
            over = now > info["t"] + info["budget"] * a.slack + GRACE_S or now > deadline + GRACE_S
            if p.poll() is None and not over:
                continue
            if p.poll() is None:
                stop(p)
            del running[p]
            info.update(wall_s=round(time.monotonic() - info["t"], 1), cpu_s=meter.cpu_s(p.pid), peak_rss_mb=meter.rss_mb(p.pid))
            c0, w0 = child_cpu(), time.monotonic()
            rank = judge(info["out"], inp, base, deadline - time.monotonic() + GRACE_S, a.check_placement)
            judge_cpu += child_cpu() - c0
            judge_wall += time.monotonic() - w0
            info.update(rc=p.returncode, rank=rank)
            fast_fails = fast_fails + 1 if rank is None and info["wall_s"] < 10 else 0
            done.append(info)
            log(f"end #{info['k']} rc {p.returncode} (illegal, not clean, unconnected, new errors, outside) {rank}")
            if rank is not None and (best is None or rank < best["rank"]):
                best = info
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(best["out"], out)  # at once: a kill at the deadline keeps the best so far
        if best and best["rank"][:2] == (0, 0):
            log(f"#{best['k']} is clean: stopping the rest")
            meter.sample([p.pid for p in running])
            for p, info in list(running.items()):
                stop(p)
                info.update(wall_s=round(time.monotonic() - info["t"], 1), cpu_s=meter.cpu_s(p.pid),
                            peak_rss_mb=meter.rss_mb(p.pid), rc=None, rank=None, stopped=True)
                done.append(info)
            running.clear()
            break
        if fast_fails >= 2 * a.parallel:
            log(f"{fast_fails} attempts in a row died within 10 s without a board: giving up (see restarts/a*/log)")
            for p in list(running):
                stop(p)
            running.clear()
            break
        while len(running) < a.parallel and launch():
            pass
    work = dict(attempts=len(done), clean_found=bool(best and best["rank"][:2] == (0, 0)),
                best_attempt=best and best["k"], best_seed=best and best["seed"], best_rank=best and list(best["rank"]),
                cpu_s=round(sum(d.get("cpu_s", 0) for d in done) + judge_cpu, 1),
                method_cpu_s=round(sum(d.get("cpu_s", 0) for d in done), 1), judge_cpu_s=round(judge_cpu, 1),
                judge_wall_s=round(judge_wall, 1), wall_s=round(time.monotonic() - t0, 1), budget_s=a.time,
                parallel=a.parallel, peak_rss_mb=max([d.get("peak_rss_mb", 0) for d in done] + [0]),
                wall_to_best_s=best and round(best["t"] + best["wall_s"] - t0, 1))
    summary = dict(work, attempt_log=[{k_: v for k_, v in d.items() if k_ not in ("out", "t")} for d in done])
    (wd / "summary.json").write_text(json.dumps(summary, indent=1))
    print("KAE_WORK " + json.dumps(work), flush=True)
    if best is None:
        log("no attempt produced a board")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best["out"], out)
    log(f"kept #{best['k']} (seed {best['seed']}): {best['rank']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
