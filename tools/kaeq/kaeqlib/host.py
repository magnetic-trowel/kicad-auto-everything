# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The machine: what kaeq reads (run queue, CPU, memory, processes) and does to jobs' cgroups (limits, freezing, compression, systemd properties). Host bundles the reads so tests and the simulator can pass their own."""
import os
import signal
import subprocess
import time
from .units import parse_cpus


def job_cpus(cfg):
    """CPUs jobs are pinned to (inherited by every child): a hard cap that leaves reserve_cpu free. None = no pinning."""
    spec = cfg["cpu_affinity"]
    if spec == "off" or not hasattr(os, "sched_getaffinity"):
        return None
    if spec == "auto":
        mine = sorted(os.sched_getaffinity(0))
        n = max(1, min(len(mine), cfg["threads"]) - cfg["reserve_cpu"])
        return set(mine[:n])
    return parse_cpus(spec)


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def meminfo():
    d = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            d[k] = int(v.split()[0]) // 1024  # MB
    return d


def cpu_ticks():
    """(busy, total) jiffies over all CPUs."""
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v[:8]) - idle, sum(v[:8])


def proc_by_session():
    """({sid: (rss_mb, cpu_ticks)}, {pid: (rss_mb, cpu_ticks)}) over every process we can read."""
    out, per_pid = {}, {}
    page_mb = os.sysconf("SC_PAGE_SIZE") / (1 << 20)
    for ent in os.listdir("/proc"):
        if not ent.isdigit():
            continue
        try:
            with open(f"/proc/{ent}/stat") as f:
                s = f.read()
            fld = s[s.rindex(")") + 2:].split()
            sid, ut, st, rss = int(fld[3]), int(fld[11]), int(fld[12]), int(fld[21])
        except (OSError, ValueError, IndexError):
            continue
        per_pid[int(ent)] = (rss * page_mb, ut + st)
        r, t = out.get(sid, (0.0, 0))
        out[sid] = (r + rss * page_mb, t + ut + st)
    return out, per_pid


def job_cgroup(pid):
    """The job's own systemd scope (cgroup v2 path), or None when it runs without one."""
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            for line in f:
                if line.startswith("0::") and line.rstrip().endswith(".scope") and "/run-" in line:
                    return "/sys/fs/cgroup" + line[3:].strip()
    except OSError:
        pass
    return None


def kill_tree(pid, cg=None, sig=signal.SIGKILL):
    """Kill a job: its process group, and every process in its scope (children that started
    their own session would otherwise outlive the job, e.g. in a deleted scratch dir).
    cg: the scope recorded while the job ran (never looked up from a pid that may be reused)."""
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError, TypeError):
        pass
    if not cg:
        return
    if sig == signal.SIGKILL and os.path.exists(os.path.join(cg, "cgroup.kill")):
        try:
            with open(os.path.join(cg, "cgroup.kill"), "w") as f:
                f.write("1")
            return
        except OSError:
            pass
    try:
        with open(os.path.join(cg, "cgroup.procs")) as f:
            for q in f.read().split():
                try:
                    os.kill(int(q), sig)
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
    except OSError:
        pass


def cg_mem(cg):
    """(use_mb, high_events) of a job's scope: the memory it cannot give back (anonymous and shared memory
    and the kernel's own for it; page cache is reclaimed at memory.high, so it is not use) and how often it
    has hit memory.high. None when the scope has no memory controller."""
    try:
        st = {}
        with open(os.path.join(cg, "memory.stat")) as f:
            for line in f:
                k, v = line.split()
                st[k] = int(v)
        use = st.get("anon", 0) + st.get("shmem", 0) + st.get("kernel", st.get("kernel_stack", 0) + st.get("pagetables", 0))
        high = 0
        with open(os.path.join(cg, "memory.events")) as f:
            for line in f:
                k, v = line.split()
                if k == "high":
                    high = int(v)
        return use / (1 << 20), high
    except (OSError, ValueError):
        return None


def cg_freeze(cg, on):
    """Freeze (or thaw) a job's scope (cgroup.freeze). A frozen job neither runs nor allocates, so it builds no
    memory pressure: systemd-oomd kills a scope under sustained pressure, which a job held at memory.high is."""
    try:
        with open(os.path.join(cg, "cgroup.freeze"), "w") as f:
            f.write("1" if on else "0")
        return True
    except OSError:
        return False


def cg_frozen(cg):
    """Whether a job's scope is set to be frozen (cgroup.freeze)."""
    try:
        with open(os.path.join(cg, "cgroup.freeze")) as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def cg_swap_mb(cg):
    """MB of a job's memory in swap (memory.swap.current): compressed, if the swap is zram."""
    try:
        with open(os.path.join(cg, "memory.swap.current")) as f:
            return int(f.read()) / (1 << 20)
    except (OSError, ValueError):
        return 0.0


def cg_anon_refaults(cg):
    """(anon MB, anon pages refaulted from swap so far) of a job (memory.stat). Under MGLRU active/inactive_anon
    say nothing about coldness, but reclaim takes the oldest pages first, and refaults show what was hot."""
    try:
        st = {}
        with open(os.path.join(cg, "memory.stat")) as f:
            for line in f:
                k, v = line.split()
                st[k] = int(v)
        return st.get("anon", 0) / (1 << 20), st.get("workingset_refault_anon", 0)
    except (OSError, ValueError):
        return 0.0, 0


def compress_room_mb(mode):
    """Swap that compress_frozen may fill (MB): zram devices only for "zram", up to 80% of their size (the
    host's systemd-oomd kills when swap is 90% used), less 512 MB."""
    if mode == "off":
        return 0.0
    free = 0.0
    try:
        with open("/proc/swaps") as f:
            for line in list(f)[1:]:
                name, _, size, used, *_ = line.split()
                if mode == "any" or "/zram" in name:
                    free += (0.8 * int(size) - int(used)) / 1024
    except (OSError, ValueError):
        return 0.0
    return max(0.0, free - 512)


def compress(cg, mb, running=False, done=None, pressure=None):
    """Push up to mb of a job's memory into swap (zram: compressed in RAM), in a thread (a large reclaim takes
    seconds). A frozen job stays frozen; its pages come back as it touches them after a thaw. running=True: a
    running job (squeeze): the kernel takes its least recently used pages, and swapping is turned off again after.
    done(mb_reclaimed) is called at the end."""
    def go():
        set_unit_prop(cg, MemorySwapMax="infinity")
        try:
            with open(os.path.join(cg, "memory.swap.max"), "w") as f:
                f.write("max")
        except OSError:
            return
        # memory.reclaim takes page cache first (already counted as free, so no gain), and kernel 6.8 ignores
        # its swappiness= argument: reclaim in steps until mb has actually gone to swap (memory.swap.current),
        # or three steps in a row moved nothing (what is left is hot, or it ended)
        base, t0, idle = cg_swap_mb(cg), time.time(), 0
        while cg_swap_mb(cg) - base < mb and idle < 3 and (running or cg_frozen(cg)) and time.time() - t0 < 120:
            if (pressure or user_pressure)() > 10.0:   # in steps, pausing while the user manager is under pressure
                time.sleep(2)                    # (systemd-oomd kills it at 50% for 20 s)
                continue
            before = cg_swap_mb(cg)
            try:
                with open(os.path.join(cg, "memory.reclaim"), "w") as f:
                    f.write("512M")
            except OSError:
                pass                              # EAGAIN: reclaimed less than asked
            idle = idle + 1 if cg_swap_mb(cg) - before < 16 else 0
            if not os.path.exists(os.path.join(cg, "memory.reclaim")):
                break                             # the job ended
        got = max(0.0, cg_swap_mb(cg) - base)
        if running:
            uncompress(cg)
        if done:
            done(got)
    import threading
    threading.Thread(target=go, daemon=True).start()


def user_pressure():
    """full avg10 memory pressure (%) of this user's systemd manager, which the host's systemd-oomd watches."""
    uid = os.getuid()
    try:
        for line in open(f"/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service/memory.pressure"):
            if line.startswith("full"):
                return float(line.split()[1].split("=")[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def uncompress(cg):
    """After a thaw: no more swapping (memory.swap.max 0); what is in swap comes back as the job needs it."""
    set_unit_prop(cg, MemorySwapMax="0")
    try:
        with open(os.path.join(cg, "memory.swap.max"), "w") as f:
            f.write("0")
    except OSError:
        pass


def cg_mem_pressure(cg):
    """full avg10 memory pressure (%) of a job's scope: the share of time all its tasks stalled on memory."""
    try:
        with open(os.path.join(cg, "memory.pressure")) as f:
            for line in f:
                if line.startswith("full"):
                    return float(line.split()[1].split("=")[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def at_high(cg, high_mb):
    """Whether a job's memory (page cache included) is at the memory.high kaeq set for it (high_mb), within 5%:
    only then is its memory pressure kaeq's doing (a 10-s pressure average lags a raised limit)."""
    if not isinstance(high_mb, (int, float)):
        return False
    try:
        with open(os.path.join(cg, "memory.current")) as f:
            return int(f.read()) / (1 << 20) >= 0.95 * high_mb
    except (OSError, ValueError):
        return False


def set_unit_prop(cg, **props):
    """Set a job scope's systemd properties too (systemctl --user set-property --runtime): systemd re-applies a
    unit's properties to its cgroup when it reconfigures units of the same slice (every job start), so a value
    written only to the cgroup file is reverted to what the scope was started with. Runs in the background."""
    unit = os.path.basename(cg.rstrip("/"))
    if not unit.endswith(".scope"):
        return
    try:
        subprocess.Popen(["systemctl", "--user", "set-property", "--runtime", unit, *[f"{k}={v}" for k, v in props.items()]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def cg_high_mb(cg):
    """A job's memory.high now, MB (None: no limit)."""
    try:
        with open(os.path.join(cg, "memory.high")) as f:
            v = f.read().strip()
        return None if v == "max" else int(v) >> 20
    except (OSError, ValueError):
        return "?"


def cg_set_high(cg, mb):
    """Set a job's grant: its scope's memory.high (the kernel throttles, never kills, above it); None: no limit.
    Written to the cgroup (at once) and to the scope's systemd properties (so systemd does not revert it)."""
    set_unit_prop(cg, MemoryHigh="infinity" if mb is None else f"{int(mb)}M")
    try:
        with open(os.path.join(cg, "memory.high"), "w") as f:
            f.write("max" if mb is None else str(int(mb) << 20))
        return True
    except OSError:
        return False


TICK_HZ = os.sysconf("SC_CLK_TCK")


def runnable_threads():
    """Threads ready to run right now, over the whole machine (procs_running, minus this one)."""
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("procs_running"):
                return max(0, int(line.split()[1]) - 1)
    return 0


def job_usage(j, sessions, per_pid, cgroups):
    """(rss_mb, cpu_ticks) of a job: every process in its scope (children that start their own
    session stay in it), else every process in its session. CPU comes from the scope's cpu.stat
    when it has one: it includes children that have already exited (a job running many short
    subprocesses otherwise looks idle)."""
    cg = cgroups.get(j["id"])
    if not cg or not os.path.isdir(cg):      # (a cached scope of an earlier attempt is gone: look it up again)
        cg = job_cgroup(j["pid"])
    if cg:
        cgroups[j["id"]] = cg
        try:
            with open(os.path.join(cg, "cgroup.procs")) as f:
                pids = [int(x) for x in f.read().split()]
            rss = ticks = 0
            for q in pids:
                r, t = per_pid.get(q, (0.0, 0))
                rss += r
                ticks += t
            try:
                with open(os.path.join(cg, "cpu.stat")) as f:
                    usec = int(f.readline().split()[1])  # usage_usec
                ticks = usec * TICK_HZ // 1_000_000
            except (OSError, ValueError, IndexError):
                pass
            return rss, ticks
        except (OSError, ValueError):
            pass
    return sessions.get(j["pid"], (0.0, 0))


def cg_pressure(cg):
    """(some_s, full_s): cumulative seconds in which some / all of a job's runnable threads waited for a CPU
    (its scope's cpu.pressure; needs no delegated cpu controller). None without a scope."""
    try:
        out = {}
        with open(os.path.join(cg, "cpu.pressure")) as f:
            for line in f:
                k, *kv = line.split()
                out[k] = int(dict(x.split("=") for x in kv)["total"]) / 1e6
        return out.get("some", 0.0), out.get("full", 0.0)
    except (OSError, ValueError, KeyError):
        return None


class Host:
    """What the daemon reads from the machine, in one place: tests and the simulator pass their own (overriding
    methods), so a test never depends on how busy the machine running it is."""

    def runnable_threads(self):
        return runnable_threads()

    def cpu_ticks(self):
        return cpu_ticks()

    def meminfo(self):
        return meminfo()

    def user_pressure(self):
        return user_pressure()

    def proc_by_session(self):
        return proc_by_session()


def shutil_which(x):
    import shutil
    return shutil.which(x)
