# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run-time model and queue forecast: how long jobs take and when each owner finishes."""
import time


def size_model(rows):
    """Run time against size for one owner: rows [(mem_mb, active_s)] of finished jobs. --mem stands in for size
    (submitters size it per board). Fits log(active) = a + b log(mem) by least squares when there are at least 8
    jobs and their --mem varies, else a constant (the median). Returns (predict(mem) -> s, ratios): ratios are
    the sorted actual/predicted of those jobs, how far reality strays from the model."""
    import math
    rows = [(m, t) for m, t in rows if m and m > 0 and t and t > 0]
    if len(rows) < 3:
        return None, []
    xs, ys = [math.log(m) for m, _ in rows], [math.log(t) for _, t in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs) / len(xs)
    if len(rows) >= 8 and vx > 0.05:
        b = max(0.0, min(2.0, sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs) / vx))
        a = my - b * mx
        pred = lambda m: math.exp(a + b * math.log(max(m, 1.0)))
    else:
        med = sorted(t for _, t in rows)[len(rows) // 2]
        pred = lambda m: med
    return pred, sorted(t / pred(m) for m, t in rows)


def given_so_far(pred, active, ratios):
    """Expected total run time of a job predicted to take pred that has run active so far: the mean of the
    owner's actual/predicted ratios at least active/pred (how jobs that got this far ended), else 1.3 x active."""
    k = active / pred if pred > 0 else 0.0
    tail = [r for r in ratios if r >= k]
    if k <= (ratios[0] if ratios else 1.0):
        return pred * (sum(ratios) / len(ratios) if ratios else 1.0)
    return pred * sum(tail) / len(tail) if tail else 1.3 * active


def board_of(name):
    """The board a job runs on, from its name: the longest ':'-separated part of 12+ characters
    (e.g. "escape-ab3:seeed-studio-oshw-...:0", "phys:<board>:<method>"), else None."""
    toks = [t for t in (name or "").split(":") if len(t) >= 12]
    return max(toks, key=len) if toks else None


def runtime_model(c, limit=30000):
    """Run time as owner speed x board difficulty, from the last `limit` finished jobs: log(active) = owner +
    board, fitted by alternating medians (owners) and shrunk means (boards seen once count little). The same
    boards run under many owners, and a board slow for one method is slow for the others. Returns (owner effect
    {owner: log s}, board effect {board: log}, residual ratios {owner: sorted actual/predicted})."""
    import math
    rows = [(o, board_of(n), math.log(t)) for o, n, t in c.execute(
        "SELECT owner, name, finished-started-COALESCE(frozen_s,0) AS t FROM jobs WHERE state='ok' AND started IS NOT "
        "NULL AND finished-started-COALESCE(frozen_s,0) > 0 ORDER BY finished DESC LIMIT ?", (limit,))]
    lo, lb = {}, {}
    for _ in range(8):
        acc = {}
        for o, b, y in rows:
            acc.setdefault(o, []).append(y - lb.get(b, 0.0))
        lo = {o: sorted(v)[len(v) // 2] for o, v in acc.items()}
        acc = {}
        for o, b, y in rows:
            if b:
                acc.setdefault(b, []).append(y - lo[o])
        lb = {b: sum(v) / (len(v) + 1) for b, v in acc.items()}   # shrunk: a board seen once counts half (backtested best)
    res = {}
    for o, b, y in rows:
        res.setdefault(o, []).append(math.exp(y - lo[o] - lb.get(b, 0.0)))
    return lo, lb, {o: sorted(v) for o, v in res.items()}


def expected_durations(c, jobs, now=None, model=None):
    """{job id: (expected active seconds, source)}, by what is known: the same name ran before ("name": a retry,
    or the same board and method again); owner speed x board difficulty ("board", runtime_model); the owner's
    size model when the board is new ("size", size_model); a new owner on a known board: the board x a typical
    owner ("board~"); else half its --timeout ("guess"). A running job's figure is its expected total given how
    long it has run already (given_so_far, from how its owner's runs strayed from these predictions)."""
    import math
    now = now or time.time()
    lo, lb, resid = model or runtime_model(c)
    typical = sorted(lo.values())[len(lo) // 2] if lo else 0.0
    sizes, out = {}, {}
    names = {j["name"] for j in jobs if j["name"]}
    by_name = {}
    if names:
        q = ",".join("?" * len(names))
        for n, act in c.execute(f"SELECT name, finished-started-COALESCE(frozen_s,0) FROM jobs WHERE state='ok' "
                                f"AND started IS NOT NULL AND name IN ({q}) ORDER BY finished", tuple(names)):
            by_name[n] = act                                  # the latest wins
    for j in jobs:
        o, b = j["owner"], board_of(j["name"])
        ratios = resid.get(o) or [1.0]
        if j["name"] in by_name and by_name[j["name"]] > 0:
            d, src = by_name[j["name"]], "name"
        elif o in lo and b in lb:
            d, src = math.exp(lo[o] + lb[b]), "board"
        else:
            if o not in sizes:
                sizes[o] = size_model(c.execute(
                    "SELECT mem_mb, finished-started-COALESCE(frozen_s,0) FROM jobs WHERE owner=? AND state='ok' "
                    "AND started IS NOT NULL ORDER BY finished DESC LIMIT 100", (o,)).fetchall())
            pred, sr = sizes[o]
            if pred:
                d, src, ratios = pred(j["mem_mb"]), "size", sr or ratios
            elif b in lb:
                d, src = math.exp(typical + lb[b]), "board~"
            else:
                d, src, ratios = 0.5 * j["timeout_s"], "guess", [1.0]
        if j["state"] == "running" and j["started"]:
            act = max(0.0, now - j["started"] - (j["frozen_s"] or 0.0) - (now - j["frozen_since"] if j["frozen_since"] else 0.0))
            d = given_so_far(d, act, ratios)
        out[j["id"]] = (min(d, j["timeout_s"]), src)
    return out


def forecast_queue(running, queued, dur, mem, cpus, mem_cap, cpu_cap, now, horizon=14 * 86400):
    """Replay the queue forward: when does each owner start and finish? running/queued: job rows; dur: {id:
    expected active s}; mem/cpus: {id: footprint}; mem_cap/cpu_cap: what jobs may hold. Running jobs end after
    their expected time left (at least a tenth of it, or a minute, once overdue). Starts follow the daemon's order
    (priority, then the owner with the fewest running, then submission), the first owner's next job that fits
    (backfill across owners). Returns {owner: (first start or None, finish)}."""
    import heapq
    ev, cnt, used_m, used_c, res = [], {}, 0.0, 0.0, {}
    for j in running:
        d = dur[j["id"]]
        act = max(0.0, now - (j["started"] or now) - (j["frozen_s"] or 0.0))
        end = now + max(d - act, 0.1 * d, 60.0)
        heapq.heappush(ev, (end, j["id"], j["owner"], mem[j["id"]], cpus[j["id"]]))
        cnt[j["owner"]] = cnt.get(j["owner"], 0) + 1
        used_m, used_c = used_m + mem[j["id"]], used_c + cpus[j["id"]]
        res[j["owner"]] = [now, max(res.get(j["owner"], [now, now])[1], end)]
    mem_cap, cpu_cap = max(mem_cap, used_m), max(cpu_cap, used_c)
    per = {}
    for j in sorted(queued, key=lambda j: (-j["prio"], j["submitted"])):
        per.setdefault(j["owner"], []).append(j)
    for q in per.values():
        q.reverse()                                   # pop() takes the next
    t = now
    while per and t < now + horizon:
        started = True
        while started:
            started = False
            heads = sorted(per, key=lambda o: (-per[o][-1]["prio"], cnt.get(o, 0), per[o][-1]["submitted"]))
            for o in heads:
                j = per[o][-1]
                if mem[j["id"]] <= mem_cap - used_m and (cpus[j["id"]] <= cpu_cap - used_c or not ev):
                    per[o].pop()
                    if not per[o]:
                        del per[o]
                    end = t + dur[j["id"]]
                    heapq.heappush(ev, (end, j["id"], o, mem[j["id"]], cpus[j["id"]]))
                    cnt[o] = cnt.get(o, 0) + 1
                    used_m, used_c = used_m + mem[j["id"]], used_c + cpus[j["id"]]
                    r = res.setdefault(o, [t, end])
                    r[1] = max(r[1], end)
                    started = True
                    break
        if not ev:
            break
        end, _, o, m, cp = heapq.heappop(ev)
        t = max(t, end)
        cnt[o] -= 1
        used_m, used_c = used_m - m, used_c - cp
    return {o: (r[0] if r[0] > now else None, r[1]) for o, r in res.items()}
