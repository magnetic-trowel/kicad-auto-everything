# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restart portfolio for any method: the same schedule as kae.route.portfolio, judged by KiCad.

    restart.py --input IN --output OUT --time T [--seed S] [--parallel P] [--first-s F] [--growth G]
               -- COMMAND...

COMMAND is one attempt of the method, run with `sh -c` in its own directory, with @IN@, @OUT@,
@SEED@, @TIME@ and @BEST@ replaced. With --resume S, a share S of each wave after the first
continues from the best board so far: @BEST@ is a copy of it (with the input's project files) and
KAE_RESUME=1 is set; otherwise @BEST@ is the input and KAE_RESUME=0. A command decides what
continuing means (a router routes what is still open; a placer may keep the placement and route). `parallel` attempts run at once; attempt k gets seed S*1000+k and a
budget of F * G**(k // P) seconds (a doubling schedule: a board that needs one long attempt
still gets one). Each finished attempt is checked with kicad-cli DRC (zones refilled, the input's
project rules) and ranked by judge in the harness's order: legal first (--check-placement), then
fewer unconnected items, then fewer DRC errors beyond the input's own. The first clean one (none
open, no error beyond the input's) ends the run; otherwise the best is kept when time runs out. Only stdlib; KiCad comes from KAE_KICAD_WRAP.

With --final COMMAND, the board kept gets one more pass at the end (final_pass), however late its
attempt ended: COMMAND runs with @IN@ (the input), @BEST@ (a copy of the kept board with the
input's project files), @OUT@, @SEED@ and @TIME@ replaced, its time reserved from the start
(final_reserve: --final-s, or FINAL_MIN_S plus one DRC of the board, plus judging the result).
Its board replaces the kept one only when KiCad's DRC ranks it better. For a router this is the
last mile alone (kae.route.cli lastmile): an attempt that ended late is not punished for it.

With --finish COMMAND, the board kept after that (clean or not) gets the finish stage (for kae,
`python -m kae.route.finish @BEST@ @OUT@ --project @IN@ --time @TIME@ --input-drc @DRC@ --drc-s @DRC_S@`,
docs/topics/routing/routing-stages.md stage 7): @DRC@ is the judge's DRC report of @BEST@, so the
finish's gate need not run the input again. Its time is reserved from the start too
(finish_estimate: --finish-s, or an estimate from the input's pad count plus two DRCs), and its
board replaces the kept one when KiCad ranks it no worse. summary.json's "finish" says which parts
ran and which were skipped for time.

With --history, every judged attempt adds the nets KiCad found open on its board to a failure
history (restarts/history.json, {net: attempts that left it open}; record_open), and every attempt
gets its path in KAE_ROUTE_HISTORY: a router may route those nets first (kae.route.bridge does).
Each attempt's record in summary.json lists the nets it left open.

Work is measured, since a sandboxed method's processes are invisible to the harness: every
attempt's processes (its process tree and session, so a router started in a session of its own
counts too) are sampled from /proc each second (CPU seconds summed over all of them, peak RSS);
an attempt that exits is reaped with wait4, whose rusage covers every descendant it waited for,
and the larger of the two counts. The DRC judging is counted separately. The totals go to
restarts/summary.json and to a last stdout line `KAE_WORK {json}` that kaeres records.

With KAE_STEP_CACHE set (kae/src/kae/route/stepcache.py), the judge's DRCs and the attempts'
Freerouting runs and DRCs replay earlier identical runs, and time is charged as if they had
run. Every attempt appends its steps to its own KAE_CHARGE_FILE (restarts/a<k>/charge.jsonl);
the time a hit saved keeps the attempt's slot held after it exits, and counts against its
budget while it runs. A judge's hit holds this loop just as long. A hold elapses in real time
while any attempt is computing, and is skipped when none is, so the schedule (what starts, is
judged or killed when) is the uncached one, and only the wall time shrinks. The hits, misses
and charged seconds go to summary.json and KAE_WORK (step_cache).
"""
import argparse
import importlib.util
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
FINAL_MIN_S = 60.0  # the final pass at least, beyond one DRC of the board (a last mile's joins and refill)


def _stepcache():
    """kae's step cache module, loaded by path (stdlib only), when KAE_STEP_CACHE is set."""
    f = Path(__file__).resolve().parents[2] / "kae" / "src" / "kae" / "route" / "stepcache.py"
    if not os.environ.get("KAE_STEP_CACHE") or not f.exists():
        return None
    spec = importlib.util.spec_from_file_location("kae_stepcache", f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.AUTO_ADVANCE = False   # this loop holds instead: attempts compute meanwhile (hold)
    return m


SC = _stepcache()
BUSY = [lambda: False]   # whether any attempt is computing (main sets it)


def hold(seconds, tick=lambda: None):
    """Spend `seconds` of charged time a cache hit saved: in real time while an attempt computes
    (it would have computed meanwhile), skipped at once when none does."""
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        if not BUSY[0]():
            SC.advance(left)
            return
        tick()
        time.sleep(min(1.0, left))


def saved(info):
    """Charged seconds an attempt's cache hits saved so far (its charge file), 0 without one."""
    return SC.charges(info["charge"])["saved_s"] if SC and info.get("charge") else 0.0


def alive(pid):
    """A process that runs (not exited: a zombie waiting for wait4 is not computing)."""
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def log(msg):
    print(f"[restart {time.strftime('%H:%M:%S')}] {msg}", flush=True)


TICK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")


class Meter:
    """CPU and memory of attempts, by sampling /proc: an attempt is its root process, the
    processes below it and those in its session (processes that live < 1 s between samples are
    missed; reap() adds the CPU of those the attempt waited for)."""

    def __init__(self):
        self.cpu = {}   # root pid -> {pid: cpu ticks last seen}
        self.rss = {}   # root pid -> peak summed RSS bytes
        self.members = {}   # root pid -> its processes at the last sample

    def sample(self, roots):
        procs = {}      # pid -> (ppid, sid, ticks, rss)
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                f = open(f"/proc/{d}/stat").read()
            except OSError:
                continue
            x = f[f.rindex(")") + 2:].split()
            procs[int(d)] = (int(x[1]), int(x[3]), int(x[11]) + int(x[12]), int(x[21]) * PAGE)
        kids = {}
        for pid, (ppid, _, _, _) in procs.items():
            kids.setdefault(ppid, []).append(pid)
        for root in roots:
            mine = {pid for pid, v in procs.items() if v[1] == root}
            todo = [root]
            while todo:
                pid = todo.pop()
                if pid in procs:
                    mine.add(pid)
                todo.extend(c for c in kids.get(pid, ()) if c not in mine)
            self.members[root] = mine
            seen = self.cpu.setdefault(root, {})
            for pid in mine:
                seen[pid] = max(seen.get(pid, 0), procs[pid][2])
            self.rss[root] = max(self.rss.get(root, 0), sum(procs[pid][3] for pid in mine))

    def cpu_s(self, root):
        return round(sum(self.cpu.get(root, {}).values()) / TICK, 1)

    def rss_mb(self, root):
        return round(self.rss.get(root, 0) / 2 ** 20)


def reap(p, info, block=False):
    """p.poll() / p.wait() through wait4, keeping the CPU of p and every descendant it waited
    for (info["ru_cpu_s"]). Returns the exit code, None while p runs."""
    if p.returncode is not None:
        return p.returncode
    try:
        pid, status, ru = os.wait4(p.pid, 0 if block else os.WNOHANG)
    except ChildProcessError:
        return p.poll()
    if pid == 0:
        return None
    p.returncode = os.waitstatus_to_exitcode(status)
    info["ru_cpu_s"] = ru.ru_utime + ru.ru_stime
    return p.returncode


def child_cpu():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


ENV_DEPENDENT_CHECKS = ("lib_footprint_issues", "lib_footprint_mismatch")  # as kaebench.tools: not the board's


def report_unconnected(pro):
    """Make the project copy `pro` report unconnected items when it sets them to "ignore": KiCad's
    DRC then lists none at all, whatever --severity (7 corpus boards; the harness counts them by
    pcbnew there, kaebench.score._uncapped). Only the judge's copy beside an attempt's board."""
    try:
        d = json.loads(pro.read_text(encoding="utf-8"))
        sev = d["board"]["design_settings"]["rule_severities"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    if sev.get("unconnected_items") == "ignore":
        sev["unconnected_items"] = "error"
        pro.write_text(json.dumps(d, indent=2), encoding="utf-8")


def drc(board, inp, timeout):
    """{type: count} of DRC errors (env-dependent checks dropped) and the unconnected count of a
    board by kicad-cli, with the input's project rules; None when there is no usable board."""
    if not board.exists() or board.stat().st_size == 0:
        return None
    for ext in (".kicad_pro", ".kicad_dru"):  # the task's rules, never the method's copy
        src = inp.with_suffix(ext)
        if src.exists():
            shutil.copy2(src, board.with_suffix(ext))
    report_unconnected(board.with_suffix(".kicad_pro"))
    rep = board.with_name("drc.json")
    # --severity-all: kicad-cli filters unconnected items by the project's severity like violations,
    # so --severity-error read 0 open connections on boards that make them warnings (keytops-blank:
    # 43 with --severity-all, 0 with --severity-error) and kept the first error-free attempt as clean
    cmd = [*shlex.split(os.environ.get("KAE_KICAD_WRAP", "")), "kicad-cli", "pcb", "drc", "--format", "json",
           "--severity-all", "--refill-zones", "--output", str(rep), str(board)]
    try:
        if SC:
            rep.unlink(missing_ok=True)
            r = SC.run("kicad-drc-judge", cmd, inputs=SC.kicad_inputs(board), outputs={"report": rep}, wd=board.parent,
                       timeout=max(60, timeout), tool=SC.kicad_version(cmd[:cmd.index("kicad-cli") + 1]))
            hold(r.saved)
        else:
            subprocess.run(cmd, capture_output=True, timeout=max(60, timeout))
        r = json.loads(rep.read_text())
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    types = {}
    for v in r.get("violations", []):
        if v.get("severity", "error") == "error" and v.get("type") not in ENV_DEPENDENT_CHECKS:
            types[v.get("type")] = types.get(v.get("type"), 0) + 1
    n = len(r.get("unconnected_items", []))
    if n >= DRC_UNCONNECTED_CAP:
        # kicad-cli lists at most 499: past it, pcbnew's count after a zone fill (as the scorer,
        # kaebench score._uncapped). polarfire-som: ~150 attempts all read 499, so screening,
        # resume and the final pass chose blind (a 206 s attempt kept: 1306 open; 1500 s: 429)
        m = uncapped_unconnected(board, timeout)
        n = m if m is not None else n
    return dict(types=types, unconnected=n, overlaps=overlaps(r))


DRC_UNCONNECTED_CAP = 499
UNCONNECTED_PY = ("import json, sys, pcbnew\n"
                  "b = pcbnew.LoadBoard(sys.argv[1]); zs = pcbnew.ZONES()\n"
                  "for i in range(b.GetAreaCount()): zs.append(pcbnew.Cast_to_ZONE(b.GetArea(i)))\n"
                  "len(zs) and pcbnew.ZONE_FILLER(b).Fill(zs)\n"
                  "b.BuildConnectivity()\n"
                  "print(json.dumps(dict(unconnected=b.GetConnectivity().GetUnconnectedCount(False))))\n")


def uncapped_unconnected(board, timeout):
    """pcbnew's unconnected count after a zone fill, None when KiCad's Python cannot run it."""
    cmd = [*shlex.split(os.environ.get("KAE_KICAD_WRAP", "")), "python3", "-c", UNCONNECTED_PY, str(board)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=max(60, timeout), errors="replace")
        return int(json.loads(r.stdout.strip().splitlines()[-1])["unconnected"])
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError, KeyError):
        return None


OF_REF = re.compile(r"^(?:Footprint (\S+)$|.*\bpad\b.* of (\S+?)(?: on \S+)?$)", re.I)


def overlaps(report):
    """Pairs of parts a placement put on top of each other, from a DRC report: courtyards that
    overlap, and pads of two parts that short (pad to pad: a track's short is the router's).
    can485: a 1x6 header placed over a 1x12 one gave 47 shorting_items and was kept."""
    pairs = set()
    for v in report.get("violations", []):
        if v.get("type") not in ("courtyards_overlap", "shorting_items") or v.get("severity", "error") != "error":
            continue
        refs = []
        for it in v.get("items", []):
            m = OF_REF.match(it.get("description", ""))
            refs.append((m.group(1) or m.group(2)) if m else None)
        if len(refs) == 2 and None not in refs and refs[0] != refs[1]:
            pairs.add(tuple(sorted(refs)))
    return sorted(pairs)


NUM = r"(-?[0-9.]+)"


def block(txt, i):
    """The S-expression block opening at txt[i] == "(" (to the end of txt if it never closes)."""
    d, j, n, in_str = 0, i, len(txt), False
    while j < n:
        c = txt[j]
        if in_str:
            if c == "\\":
                j += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return txt[i:j + 1]
        j += 1
    return txt[i:]


def edge_cuts_graphics(txt):
    """Board graphics (gr_line/arc/rect/poly/circle) on Edge.Cuts, each its own block. A regex from
    a graphic to the next `(layer "Edge.Cuts")` took in every graphic on another layer before an
    Edge.Cuts one (mulcmu-plimsoll-3: outline (100,100)-(142,150) read as (-2.95,-2.85)-(142,150);
    6 of 115 corpus boards inflated), so parts staged on that side were not counted outside."""
    for m in re.finditer(r"\((?:gr_line|gr_arc|gr_rect|gr_poly|gr_circle)\b", txt):
        blk = block(txt, m.start())
        lay = re.search(r'\(layer "?([^"\s)]*)', blk)
        if lay and lay.group(1) == "Edge.Cuts":
            yield blk


def outside(board):
    """Unlocked footprints with pads whose anchor lies outside the Edge.Cuts bounding box (a part left staged
    off the board, which DRC does not flag): a cheap stand-in for the harness's legality check.
    Locked parts are the task's fixed interface and may overhang the edge."""
    txt = board.read_text(errors="replace")
    pts = [(float(x), float(y)) for blk in edge_cuts_graphics(txt)
           for x, y in re.findall(r"\((?:start|end|mid|xy|center) " + NUM + " " + NUM, blk)]
    if not pts:
        return 0
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    n = 0
    for m in re.finditer(r"\(footprint \"[^\"]*\"(.*?)\(at " + NUM + " " + NUM, txt, re.S):
        x, y = float(m.group(2)), float(m.group(3))
        end = txt.find("\n\t(footprint ", m.end())
        pads = "(pad " in txt[m.end():end if end > 0 else len(txt)]
        # like the harness (pad centres outside the outline): footprints without pads (logos) never count
        n += pads and "(locked" not in m.group(1) and not (x0 <= x <= x1 and y0 <= y <= y1)
    return n


def judge(board, inp, base, timeout, placement=False, base_pairs=()):
    """Rank key (lower is better) in the harness's order: legal, clean, then fewer unconnected,
    then fewer DRC errors beyond the input's own (per type). With `placement`, parts outside the
    outline, or parts on top of each other that the input (`base_pairs`) does not already have,
    make it illegal; the last field counts both. None when there is no board."""
    d = drc(board, inp, timeout)
    if d is None:
        return None
    new = sum(max(0, c - base.get(t, 0)) for t, c in d["types"].items())
    out = outside(board) if placement else 0
    if placement:
        out += len(set(map(tuple, d.get("overlaps", ()))) - set(map(tuple, base_pairs)))
    clean = out == 0 and new == 0 and d["unconnected"] == 0
    return (1 if out else 0, 0 if clean else 1, d["unconnected"], new, out)


def record_open(info, history, path):
    """Add the nets the DRC of attempt `info`'s board found open (its drc.json, written by judge)
    to `history` {net: attempts that left it open}, note them in `info` (open_nets), and write the
    history to `path` atomically (attempts read it when they start). info None: write it only."""
    if info is not None:
        nets = set()
        try:
            rep = json.loads(Path(info["out"]).with_name("drc.json").read_text())
        except (OSError, ValueError):
            rep = {}
        for u in rep.get("unconnected_items") or []:
            for it in u.get("items") or []:
                m = re.search(r"\[([^\]]*)\]", it.get("description") or "")
                if m and m.group(1) and m.group(1) != "<no net>":
                    nets.add(m.group(1))
        info["open_nets"] = sorted(nets)
        for n in nets:
            history[n] = history.get(n, 0) + 1
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, indent=1, sort_keys=True))
    os.replace(tmp, path)


def charge_env(info):
    return {"KAE_CHARGE_FILE": info["charge"]} if info.get("charge") else {}


# kae.route.finish's estimate from the board's size (finish.COEF and DRC_COEF, duplicated here since
# this file is stdlib only): its parts (rule D tails, taut, power copper) and the gate's two DRCs
FINISH_COEF = (15.0, 0.17)      # seconds: fixed, per pad (tails 5+0.02, taut 5+0.12, power 5+0.03)
FINISH_MIN_S = 30.0
_PADS = {}          # input board -> pad count (read once: deadline() asks every second)


def finish_estimate(a, inp, judge_est):
    """Seconds the finish pass gets: --finish-s, else its estimate from the input's pad count plus
    two DRCs (the gate's output DRC and one more) as long as the slowest judgement so far."""
    if not a.finish:
        return 0.0
    if a.finish_s:
        return a.finish_s
    if inp not in _PADS:
        try:
            _PADS[inp] = Path(inp).read_text(encoding="utf-8", errors="replace").count("(pad ")
        except (OSError, TypeError):
            _PADS[inp] = 0
    pads = _PADS[inp]
    return max(FINISH_MIN_S, FINISH_COEF[0] + FINISH_COEF[1] * pads + 2 * judge_est + 5.0)


def final_reserve(a, judge_est, inp=None):
    """Seconds kept free from the start for the final passes: the last mile (--final; --final-s,
    else FINAL_MIN_S plus one DRC of the board, as long as the slowest judgement so far) and the
    finish (--finish: finish_estimate), each with the judgement of its board. 0 without either."""
    r = 0.0
    if a.final:
        r += (a.final_s or FINAL_MIN_S + judge_est) + judge_est + 10.0
    if a.finish:
        r += finish_estimate(a, inp, judge_est) + judge_est + 10.0
    return r


def _last_json(path):
    """The last JSON object line of a log (a kae command's report), {} when there is none."""
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return {}
    for line in reversed(lines):
        if line.startswith("{"):
            try:
                r = json.loads(line)
                return r if isinstance(r, dict) else {}
            except ValueError:
                continue
    return {}


def _one_pass(a, kind, command, best, inp, base, wd, end, b, judge_est, meter, stop, cpu_s, base_pairs, keep_equal):
    """Run `command` once on the kept board (in wd/kind) with `b` seconds, judge its board and say
    whether it replaces the kept one: when KiCad ranks it better, or (keep_equal) no worse."""
    d = wd / kind
    d.mkdir(exist_ok=True)
    src, o = d / "best_in.kicad_pcb", d / "board.kicad_pcb"
    shutil.copy2(best["out"], src)
    for ext in (".kicad_pro", ".kicad_dru"):   # the task's rules
        if inp.with_suffix(ext).exists():
            shutil.copy2(inp.with_suffix(ext), src.with_suffix(ext))
    t = time.monotonic()
    seed = a.seed * 1000 + 999
    drc_json = Path(best["out"]).with_name("drc.json")      # the judge's DRC of the kept board
    c = command.replace("@IN@", shlex.quote(str(inp))).replace("@OUT@", shlex.quote(str(o)))
    c = c.replace("@BEST@", shlex.quote(str(src))).replace("@SEED@", str(seed)).replace("@TIME@", str(int(b)))
    c = c.replace("@DRC@", shlex.quote(str(drc_json)) if drc_json.exists() else "''")
    c = c.replace("@DRC_S@", str(round(judge_est, 1)))
    log(f"{kind} pass on #{best['k']}'s board: {b:.0f}s")
    info = dict(k=kind, seed=seed, budget=round(b), out=o, t=t, resumed_from=best["k"])
    if SC:
        info["charge"] = str(d / "charge.jsonl")
    p = subprocess.Popen(["sh", "-c", c], cwd=d, stdout=open(d / "log", "w"), stderr=subprocess.STDOUT,
                         start_new_session=True, env=dict(os.environ, KAE_RESUME="1", **charge_env(info)))
    while reap(p, info) is None:
        if time.monotonic() + saved(info) > min(t + b + GRACE_S, end - judge_est - 5):
            stop(p, info)
            info["killed"] = True
            break
        meter.sample([p.pid])
        time.sleep(1)
    info.update(cpu_s=cpu_s(p, info), peak_rss_mb=meter.rss_mb(p.pid), rc=p.returncode)
    if SC:
        hold(saved(info))
        info["step_cache"] = SC.charges(info["charge"])
    info["wall_s"] = round(time.monotonic() - t, 1)
    c0, w0 = child_cpu(), time.monotonic()
    rank = judge(o, inp, base, max(10.0, end - w0 - 5), a.check_placement, base_pairs)
    info.update(rank=rank, judge_cpu_s=child_cpu() - c0, judge_wall_s=time.monotonic() - w0)
    info["kept"] = rank is not None and (rank <= tuple(best["rank"]) if keep_equal else rank < tuple(best["rank"]))
    log(f"{kind} pass rc {p.returncode} {rank}: {'kept' if info['kept'] else 'not better'}")
    return info


def final_pass(a, best, inp, base, wd, end, judge_est, meter, stop, cpu_s, base_pairs=()):
    """One more pass of --final on the board kept, whenever its attempt ended: the time left up to
    the end (at least what final_reserve kept free) less one judgement and the finish's reserve.
    Returns its record (kept: whether KiCad's DRC ranks its board better than the kept one), None
    when there is nothing to do (no board, or a clean one)."""
    if best is None or best.get("rank") is None or best["rank"][:2] == (0, 0):
        return None
    fin_res = (finish_estimate(a, inp, judge_est) + judge_est + 10.0) if a.finish else 0.0
    b = max(20.0, end - time.monotonic() - judge_est - 10.0 - fin_res)
    return _one_pass(a, "final", a.final, best, inp, base, wd, end, b, judge_est, meter, stop, cpu_s, base_pairs,
                     keep_equal=False)


def finish_pass(a, best, inp, base, wd, end, judge_est, meter, stop, cpu_s, base_pairs=()):
    """--finish on the board kept (after --final), clean or not: the time left less one judgement.
    Its board replaces the kept one when KiCad ranks it no worse (finishing shapes copper; it does
    not aim to change the rank). The record carries the finish's own report summary (which parts
    ran, were skipped or failed; its DRC runs). None without a board."""
    if best is None or best.get("rank") is None:
        return None
    b = max(20.0, end - time.monotonic() - judge_est - 10.0)
    info = _one_pass(a, "finish", a.finish, best, inp, base, wd, end, b, judge_est, meter, stop, cpu_s, base_pairs,
                     keep_equal=True)
    rep = _last_json(wd / "finish" / "log")
    if rep:
        info["finish"] = dict(parts=rep.get("parts"), drc_runs=rep.get("drc_runs"),
                              drc_in_reused=rep.get("drc_in_reused"), entries=rep.get("entries"),
                              kept_entries=rep.get("kept"), noise=rep.get("noise"), seconds=rep.get("seconds"),
                              step_cache=rep.get("step_cache"))
    return info


def rung_plan(wall_s, parallel, screen_s, eta=2):
    """Successive halving sized from the budget: rung r runs budget screen_s * eta**r; each rung
    gets the same share of the slot-seconds (parallel * wall_s), so rung r holds n0 / eta**r
    candidates. At least two rungs (a top budget past the wall time is cut at the deadline;
    with one rung nothing is ever resumed: bestelampe, a 26 s DRC, got [304] s and 9 fresh
    placements), else the most whose top budget fits in the wall time and whose top rung still
    has one candidate. Returns (budgets, n0)."""
    R = 2
    while screen_s * eta ** R <= wall_s and (R + 1) * eta ** R * screen_s <= parallel * wall_s:
        R += 1
    n0 = max(parallel, int(parallel * wall_s // (R * screen_s)))
    return [screen_s * eta ** r for r in range(R)], n0


class Halving:
    """Asynchronous successive halving over placements (ASHA, Li et al., MLSys 2020): a free slot
    promotes a candidate in the top 1/eta of those judged at its rung (its board resumed with
    the next rung's budget, a new seed), else starts a new candidate (a fresh placement with the
    screen budget) while rung 0 has room, a lower rung may still promote or a new one has time
    to climb every rung, else resumes the best board at the top rung. A
    candidate's score at a rung is its attempt's rank there; every candidate and score goes to
    summary.json."""

    def __init__(self, budgets, n0, eta=2):
        self.budgets, self.n0, self.eta = budgets, n0, eta
        self.cands = []          # {id, seed, rungs: [{k, rank}], promoted: set of rungs}

    @staticmethod
    def last(c):
        """A candidate's latest judged attempt at any rung ({k, rank}), None before one."""
        xs = [x for x in c["rungs"] if x["rank"] is not None]
        return xs[-1] if xs else None

    def next(self, left=float("inf")):
        """(candidate or None, rung, budget, k of the attempt whose board it resumes or None):
        what the next free slot runs; `left`: seconds left for attempts."""
        top = len(self.budgets) - 1
        for r in range(top - 1, -1, -1):       # the highest rung first: its budget is the longest
            done = [c for c in self.cands if len(c["rungs"]) > r and c["rungs"][r]["rank"] is not None]
            done.sort(key=lambda c: c["rungs"][r]["rank"])
            for c in done[:len(done) // self.eta]:
                if r not in c["promoted"]:
                    c["promoted"].add(r)
                    return c, r + 1, self.budgets[r + 1], c["rungs"][r]["k"]
        waiting = any(not x.get("done") for c in self.cands for x, r in zip(c["rungs"], range(top)))
        if len(self.cands) < self.n0 or waiting or left >= sum(self.budgets):
            # rung 0 has room, a lower rung may still promote, or a new placement still has time
            # to climb every rung: a short fresh placement fills the slot. Resuming the same
            # board again rarely helps (merge2-eval-joint: 18 of 70 second resumes, 21.5 -> 21.0
            # open on average), so the best is resumed only when nothing else fits
            return None, 0, self.budgets[0], None
        scored = [c for c in self.cands if self.last(c)]
        if scored:
            c = min(scored, key=lambda c: self.last(c)["rank"])
            return c, top, self.budgets[top], self.last(c)["k"]
        return None, 0, self.budgets[0], None

    def started(self, cand, k, seed):
        if cand is None:
            cand = dict(id=len(self.cands), seed=seed, rungs=[], promoted=set())
            self.cands.append(cand)
        cand["rungs"].append(dict(k=k, rank=None))
        return cand

    def judged(self, cand, k, rank):
        for x in cand["rungs"]:
            if x["k"] == k:
                x["rank"], x["done"] = rank, True

    def summary(self):
        return dict(budgets=[round(b) for b in self.budgets], n0=self.n0, eta=self.eta,
                    candidates=[dict(id=c["id"], seed=c["seed"],
                                     rungs=[dict(k=x["k"], rank=x["rank"] and list(x["rank"])) for x in c["rungs"]])
                                for c in self.cands])


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
                    help="methods that place: unlocked parts outside the outline, or parts on top of each other "
                         "(courtyards, pad-to-pad shorts) beyond the input's, make an attempt illegal")
    ap.add_argument("--max-attempts", type=int, default=0,
                    help="stop launching after this many (deterministic methods: 1); 0 = no limit")
    ap.add_argument("--slack", type=float, default=1.0,
                    help="an attempt may run budget x slack before it is killed (methods whose budget is "
                         "solver CPU time and that spend more on KiCad I/O around it)")
    ap.add_argument("--resume", type=float, default=0.0,
                    help="share of each wave after the first that continues from the best board so far "
                         "(@BEST@, KAE_RESUME=1); 0 = every attempt starts from the input")
    ap.add_argument("--final", default="",
                    help="command for one last pass on the kept board (@IN@, @BEST@, @OUT@, @SEED@, @TIME@), "
                         "its time reserved from the start; kept only when KiCad ranks it better")
    ap.add_argument("--final-s", type=float, default=0.0,
                    help="seconds for the final pass; 0 = FINAL_MIN_S plus one DRC of the board")
    ap.add_argument("--finish", default="",
                    help="command for the finish stage on the kept board after --final (@IN@, @BEST@, @OUT@, @SEED@, "
                         "@TIME@, @DRC@: the judge's DRC report of @BEST@, @DRC_S@: one judgement's seconds), "
                         "its time reserved from the start; kept when KiCad ranks it no worse, clean boards too")
    ap.add_argument("--finish-s", type=float, default=0.0,
                    help="seconds for the finish pass; 0 = an estimate from the input's pad count plus two DRCs")
    ap.add_argument("--history", action="store_true",
                    help="keep a history of the nets judged attempts left open (restarts/history.json) and pass "
                         "its path to every attempt in KAE_ROUTE_HISTORY")
    ap.add_argument("--screen", action="store_true",
                    help="methods that place: successive halving over placements instead of the fixed waves "
                         "(fresh attempts at --screen-s, the best of each rung resumed with eta x the budget)")
    ap.add_argument("--screen-s", type=float, default=0.0,
                    help="rung-0 budget (0: first-s; kae staged at half of it overran its budget: placing alone "
                         "takes 60-100 s)")
    ap.add_argument("--eta", type=int, default=2)
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
    end = t0 + a.time
    base_dir = wd / "input"  # the input's own DRC errors (silk, rules) are not the method's
    base_dir.mkdir(exist_ok=True)
    shutil.copy2(inp, base_dir / "board.kicad_pcb")
    w = time.monotonic()
    b0 = drc(base_dir / "board.kicad_pcb", inp, 0.2 * a.time)
    judge_est = max(1.0, time.monotonic() - w)   # seconds one judgement takes (the slowest seen)

    def deadline():
        # attempts stop in time for the last wave to be judged one by one before the end
        # (seniordesign hdmi2rgb: a DRC takes ~60 s; a fixed reserve let the wrapper run 88 s
        # past its time, the harness killed it and kept nothing)
        return end - max(min(0.25 * a.time, 60 + 0.05 * a.time), a.parallel * judge_est + GRACE_S + 15) \
            - final_reserve(a, judge_est, inp)
    base = (b0 or {}).get("types", {})
    history = {}
    if a.history:
        os.environ["KAE_ROUTE_HISTORY"] = str(wd / "history.json")   # attempts inherit it
        record_open(None, history, wd / "history.json")
    sh = None
    if a.screen:
        sh = Halving(*rung_plan(deadline() - time.monotonic(), a.parallel, a.screen_s or a.first_s, a.eta), eta=a.eta)
        log(f"successive halving: rung budgets {[round(b) for b in sh.budgets]} s, {sh.n0} placements")
    log(f"input DRC errors by type: {base}")
    running, done, k = {}, [], 0
    best = None
    meter, judge_cpu, judge_wall = Meter(), 0.0, 0.0
    fast_fails = 0  # attempts in a row that died within seconds without a board: a broken command

    def launch():
        nonlocal k
        # the method's budget follows the schedule; slack only lets an attempt run past it (up to
        # the overall deadline), it does not shrink the budget of late attempts
        if sh is not None:
            cand, rung, b, src_k = sh.next(deadline() - time.monotonic())
            b = min(b, deadline() - time.monotonic())
            frm = next(x for x in done if x["k"] == src_k) if src_k is not None else None
        else:
            b = min(a.first_s * a.growth ** (k // a.parallel), deadline() - time.monotonic())
            frm = best if (a.resume > 0 and k >= a.parallel and best is not None and best["rank"] is not None
                           and k % a.parallel < round(a.resume * a.parallel)) else None
        if b < 20 or (a.max_attempts and k >= a.max_attempts):
            return False
        d = wd / f"a{k}"
        d.mkdir(exist_ok=True)
        o = d / "board.kicad_pcb"
        s = a.seed * 1000 + k
        src, resume = inp, False
        if frm is not None:
            src, resume = d / "best_in.kicad_pcb", True
            shutil.copy2(frm["out"], src)
            for ext in (".kicad_pro", ".kicad_dru"):   # the task's rules
                if inp.with_suffix(ext).exists():
                    shutil.copy2(inp.with_suffix(ext), src.with_suffix(ext))
        c = cmd.replace("@IN@", shlex.quote(str(inp))).replace("@OUT@", shlex.quote(str(o)))
        c = c.replace("@BEST@", shlex.quote(str(src)))
        c = c.replace("@SEED@", str(s)).replace("@TIME@", str(int(b)))
        ch = dict(charge=str(d / "charge.jsonl")) if SC else {}
        p = subprocess.Popen(["sh", "-c", c], cwd=d, stdout=open(d / "log", "w"), stderr=subprocess.STDOUT,
                             start_new_session=True, env=dict(os.environ, KAE_RESUME="1" if resume else "0",
                                                              **charge_env(ch)))
        running[p] = dict(k=k, seed=s, budget=round(b), out=o, t=time.monotonic(),
                          resumed_from=frm["k"] if resume else None, **ch)
        if sh is not None:
            running[p].update(cand=sh.started(cand, k, s), rung=rung)
        log(f"start #{k} seed {s} budget {b:.0f}s" + (f" from #{frm['k']}'s board" if resume else "")
            + (f" (candidate {running[p]['cand']['id']}, rung {rung})" if sh is not None else ""))
        k += 1
        return True

    def stop(p, info):
        # the whole tree, not just the process group: a router in a session of its own would
        # otherwise run on after its parent is gone
        meter.sample([p.pid])
        for pid in [p.pid, *meter.members.get(p.pid, ())]:
            try:
                os.killpg(pid, signal.SIGKILL) if pid == p.pid else os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        reap(p, info, block=True)

    def cpu_s(p, info):
        return max(meter.cpu_s(p.pid), round(info.pop("ru_cpu_s", 0.0), 1))

    def busy():
        # an attempt that has exited but is not reaped yet computes no more: note when it was seen
        # so, its hold counts from then even when a judge's hold is skipped meanwhile
        live = False
        for p, i in running.items():
            if "hold" not in i:
                if alive(p.pid):
                    live = True
                else:
                    i.setdefault("dead_at", time.monotonic())
        return live
    BUSY[0] = busy
    while launch() if len(running) < a.parallel else False:
        pass
    while running:
        if SC and all("hold" in i for i in running.values()):   # nothing computes: skip to the first hold's end
            SC.advance(min(i["hold"] for i in running.values()) - time.monotonic())
        else:
            time.sleep(1)
        meter.sample([p.pid for p in running if "hold" not in running[p]])
        now = time.monotonic()
        for p, info in list(running.items()):
            if "hold" not in info:
                spent = now + saved(info)   # the attempt's own clock: charged time counts as elapsed
                over = spent > info["t"] + info["budget"] * a.slack + GRACE_S or spent > deadline() + GRACE_S
                if reap(p, info) is None and not over:
                    continue
                if p.returncode is None:
                    stop(p, info)
                info.update(cpu_s=cpu_s(p, info), peak_rss_mb=meter.rss_mb(p.pid))
                # its slot stays taken for the time its hits saved, from when it exited
                info["hold"] = min(now, info.pop("dead_at", now)) + saved(info)
                if SC:
                    info["step_cache"] = SC.charges(info["charge"])
            if time.monotonic() < info["hold"]:
                continue
            del info["hold"]
            del running[p]
            info["wall_s"] = round(time.monotonic() - info["t"], 1)
            c0, w0 = child_cpu(), time.monotonic()
            if w0 + judge_est > end - 5:
                rank = None   # no time left to judge it: the best so far stays the output
                info["not_judged"] = "time"
            else:
                rank = judge(info["out"], inp, base, max(10.0, end - w0 - 5), a.check_placement,
                             (b0 or {}).get("overlaps", ()))
                judge_est = max(judge_est, time.monotonic() - w0)
            judge_cpu += child_cpu() - c0
            judge_wall += time.monotonic() - w0
            info.update(rc=p.returncode, rank=rank)
            if a.history and rank is not None:
                record_open(info, history, wd / "history.json")
            if sh is not None:
                sh.judged(info["cand"], info["k"], rank)
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
                if "hold" not in info:   # a held one has exited: its CPU and memory are counted
                    stop(p, info)
                    info.update(cpu_s=cpu_s(p, info), peak_rss_mb=meter.rss_mb(p.pid))
                    if SC:
                        info["step_cache"] = SC.charges(info["charge"])
                info.pop("hold", None)
                info.update(wall_s=round(time.monotonic() - info["t"], 1), rc=None, rank=None, stopped=True)
                done.append(info)
            running.clear()
            break
        if fast_fails >= 2 * a.parallel:
            log(f"{fast_fails} attempts in a row died within 10 s without a board: giving up (see restarts/a*/log)")
            for p, info in list(running.items()):
                if "hold" not in info:
                    stop(p, info)
            running.clear()
            break
        while len(running) < a.parallel and launch():
            pass
    fin = final_pass(a, best, inp, base, wd, end, judge_est, meter, stop, cpu_s,
                     (b0 or {}).get("overlaps", ())) if a.final else None
    if fin is not None:
        judge_cpu += fin.pop("judge_cpu_s", 0.0)
        judge_wall += fin.pop("judge_wall_s", 0.0)
        done.append(fin)
        if fin.get("kept"):
            best = fin
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(best["out"], out)
    fz = finish_pass(a, best, inp, base, wd, end, judge_est, meter, stop, cpu_s,
                     (b0 or {}).get("overlaps", ())) if a.finish else None
    carry = best["out"].parent if best else None   # the routed board's own report (blocked, hazards)
    if fz is not None:
        judge_cpu += fz.pop("judge_cpu_s", 0.0)
        judge_wall += fz.pop("judge_wall_s", 0.0)
        done.append(fz)
        if fz.get("kept"):
            best = fz
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(best["out"], out)
    work = dict(attempts=len(done), clean_found=bool(best and best["rank"][:2] == (0, 0)),
                best_attempt=best and best["k"], best_seed=best and best["seed"], best_rank=best and list(best["rank"]),
                cpu_s=round(sum(d.get("cpu_s", 0) for d in done) + judge_cpu, 1),
                method_cpu_s=round(sum(d.get("cpu_s", 0) for d in done), 1), judge_cpu_s=round(judge_cpu, 1),
                judge_wall_s=round(judge_wall, 1), wall_s=round(time.monotonic() - t0, 1), budget_s=a.time,
                parallel=a.parallel, peak_rss_mb=max([d.get("peak_rss_mb", 0) for d in done] + [0]),
                wall_to_best_s=best and round(best["t"] + best["wall_s"] - t0, 1),
                finish=(fz or {}).get("finish") if a.finish else None)
    if SC:   # wall_s and the attempts' times above are charged time; real_wall_s is what passed
        tot = dict(hits=SC.STATS["hits"], misses=SC.STATS["misses"], uncacheable=SC.STATS["uncacheable"],
                   charged_s=SC.STATS["charged_s"], saved_s=SC.STATS["saved_s"])
        for d_ in done:
            for k_ in tot:
                tot[k_] += (d_.get("step_cache") or {}).get(k_, 0)
        work["step_cache"] = dict({k_: round(v, 1) if isinstance(v, float) else v for k_, v in tot.items()},
                                  real_wall_s=round(work["wall_s"] - SC.offset(), 1), cache_gb=SC.size_gb())
    summary = dict(work, attempt_log=[{k_: (v["id"] if k_ == "cand" else v) for k_, v in d.items()
                                       if k_ not in ("out", "t", "charge", "dead_at")}
                                      for d in done])
    if sh is not None:
        summary["halving"] = sh.summary()
    (wd / "summary.json").write_text(json.dumps(summary, indent=1))
    print("KAE_WORK " + json.dumps(work), flush=True)
    if best is None:
        log("no attempt produced a board")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best["out"], out)
    log(f"kept #{best['k']} (seed {best['seed']}): {best['rank']}")
    carry_report(carry or best["out"].parent, wd)
    origin_report(best, done, wd)
    return 0


def carry_report(attempt_dir, wd):
    """The kept attempt's own JSON report (a method's last stdout line, as kae.route.cli prints it)
    goes to restarts/report.json, and its "blocked" lines (kae.route.blocked: the rule each open
    connection is blocked by) to this log, so the kept board's diagnosis reaches the caller."""
    try:
        lines = (attempt_dir / "log").read_text(errors="replace").splitlines()
    except OSError:
        return
    for line in reversed(lines):
        if line.startswith("{"):
            try:
                rep = json.loads(line)
            except ValueError:
                continue
            (wd / "report.json").write_text(json.dumps(rep, indent=1))
            b = rep.get("blocked") if isinstance(rep, dict) else None
            if isinstance(b, dict):
                log(f"blocked: {len(b.get('blocked') or [])} open connections the rules block, "
                    f"{len(b.get('congestion') or [])} congestion (restarts/report.json)")
                for s in b.get("summary") or []:
                    log(f"blocked: {s}")
            return


def origin_report(best, done, wd):
    """When the kept board came from a resumed attempt or a final pass, restarts/report.json is only
    that router's report: the report of the fresh attempt it descends from (a joint loop's iterations,
    windows and stop reason) goes to restarts/report-origin.json."""
    by_k, cur, seen = {d["k"]: d for d in done}, best, set()
    while cur.get("resumed_from") in by_k and cur["k"] not in seen:
        seen.add(cur["k"])
        cur = by_k[cur["resumed_from"]]
    if cur is not best:
        rep = _last_json(cur["out"].parent / "log")
        if rep:
            (wd / "report-origin.json").write_text(json.dumps(dict(rep, origin_attempt=cur["k"]), indent=1))


if __name__ == "__main__":
    sys.exit(main())
