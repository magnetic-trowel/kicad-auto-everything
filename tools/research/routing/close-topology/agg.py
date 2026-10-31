# SPDX-License-Identifier: GPL-3.0-or-later
"""Sum topo.py outputs: human (ana/h) against ours (ana/r: the merit route runs; ana/m:
merge2 seeds), over the multi-pad signal nets both have copper on.

usage: agg.py <ana dir>"""
import json, os, sys, glob
from collections import Counter, defaultdict
A = sys.argv[1]


def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None


def sums(pairs, sel=lambda h, o: True):
    s = Counter()
    for h, o in pairs:
        if not sel(h, o):
            continue
        s["nets"] += 1
        for k in ("pads", "branch", "thru", "vias", "len", "mst"):
            s["h_" + k] += h[k]
            s["o_" + k] += o[k]
    return s


def show(name, s):
    if not s["nets"]:
        return print(name, "none")
    n = s["nets"]
    f = lambda p: (f"branch/net {s[p+'branch']/n:.2f} thru/net {s[p+'thru']/n:.2f} "
                   f"Steiner share {s[p+'branch']/max(1,s[p+'branch']+s[p+'thru']):.2f} "
                   f"vias/net {s[p+'vias']/n:.2f} len/mst {s[p+'len']/max(1,s[p+'mst']):.2f}")
    print(f"{name}: {n} nets, {s['h_pads']/n:.1f} pads/net\n  human {f('h_')}\n  ours  {f('o_')}")


hs = {os.path.basename(p)[:-5]: load(p) for p in glob.glob(f"{A}/h/*.json")}
# buses on the human boards
nb = Counter()
for b, d in hs.items():
    if not d:
        continue
    ab = d["adj_buses"]
    nb["boards"] += 1
    if ab:
        nb["with_adj_bus"] += 1
        nb["adj_lines"] += sum(len(x["nets"]) for x in ab)
        if any(min(x["pitch"]) <= 0.65 for x in ab):
            nb["with_fine_bus"] += 1
    if d["name_buses"]:
        nb["with_name_bus"] += 1
    if ab and d["name_buses"]:
        nb["both"] += 1
    nb["multi_nets"] += len(d["nets"])
print("buses:", dict(nb))
for tag in ("r", "m"):
    pairs, cong, perboard = [], [], {}
    for p in glob.glob(f"{A}/{tag}/*.json"):
        o = load(p)
        b = os.path.basename(p)[:-5]
        if tag == "m":
            b = b.split("-", 1)[1].rsplit("-a", 1)[0]
        h = hs.get(b)
        if not o or not h:
            continue
        hn, on = h["nets"], o["nets"]
        common = [n for n in hn if n in on and on[n]["len"] >= 0.8 * on[n]["mst"]]
        if not common:
            continue
        med = sorted(hn[n]["dens"] for n in common)[len(common) // 2]
        pp = [(hn[n], on[n]) for n in common]
        pairs += pp
        cong += [(hn[n], on[n]) for n in common if hn[n]["dens"] >= med]
        perboard[os.path.basename(p)[:-5]] = sums(pp)
    print(f"== ours = {tag}: {len(perboard)} boards")
    show("all multi-pad nets", sums(pairs))
    show("congested half (net box copper density >= board median)", sums(cong))
    show("4+ pads", sums(pairs, lambda h, o: h["pads"] >= 4))
    more = sum(1 for s in perboard.values() if s["h_branch"] > s["o_branch"])
    less = sum(1 for s in perboard.values() if s["h_branch"] < s["o_branch"])
    print(f"  boards where the human branches more / less / same: {more} / {less} / {len(perboard)-more-less}")
