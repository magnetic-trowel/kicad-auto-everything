# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The fixed-part classifier (kae.place.fixed.classify) on the human boards: per class and
split, how many parts and boards, the lib/kind mix, and borderline cases to review
(programming / debug headers, connector-kind parts with test-point or jumper names, DIP
switches, SMD LEDs left out, trimmers left out, displays, batteries).

    python tools/research/place/fixed.py kae-work-v3/tasks [--json rows.json]
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

from kae.board.kicad_file import load
from kae.circuit.netlist import Netlist
from kae.circuit.roles import infer_roles
from kae.place import fixed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rows, border = [], collections.defaultdict(list)
    per = collections.Counter()
    boards = collections.defaultdict(set)
    kinds = collections.defaultdict(collections.Counter)
    for d in sorted(glob.glob(os.path.join(a.tasks, "*"))):
        bp = os.path.join(d, "route", "input", "board.kicad_pcb")
        if not os.path.exists(bp):
            continue
        tid = os.path.basename(d)
        split = json.load(open(os.path.join(d, "task.json"))).get("split", "?")
        try:
            b = load(bp)
            got, free = fixed.classify(b, with_free=True)
            nl = Netlist.from_board(b)
            roles = infer_roles(nl)
        except Exception as e:      # noqa: BLE001
            print(f"{tid}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        uu = {nl.parts[k].uuid: pr for k, pr in roles.parts.items()}
        for f in b.footprints:
            c = got.get(f.uuid)
            pr = uu.get(f.uuid)
            kind = pr.kind if pr else "?"
            text = f"{f.lib_id} {f.value}"
            if c:
                per[(c["cls"], split)] += 1
                per[(c["cls"], "all")] += 1
                boards[c["cls"]].add(tid)
                kinds[c["cls"]][c["kind"]] += 1
                rows.append(dict(id=tid, split=split, **{k: v for k, v in c.items() if k != "why"}))
                if c["cls"] == "connectors" and re.search(r"swd|jtag|isp|prog|tag.?connect|uart|debug|tck|swclk", text, re.I):
                    border["connector with programming-like words, still fixed"].append((tid, f.ref, f.lib_id, f.value))
                if c["cls"] == "connectors" and re.search(r"test|^TP", f"{f.ref} {text}", re.I):
                    border["test-point-like connector (fixed)"].append((tid, f.ref, f.lib_id, f.value))
                if c["cls"] == "user" and re.search(r"dip.?sw|SW_DIP", text, re.I):
                    border["DIP switch (fixed as user)"].append((tid, f.ref, f.lib_id, f.value))
                if c["cls"] == "user" and c["kind"] == "led":
                    border["LED kept as panel LED (fixed)"].append((tid, f.ref, f.lib_id, f.value))
            elif f.uuid in free:
                per[("prog_free", split)] += 1
                per[("prog_free", "all")] += 1
                boards["prog_free"].add(tid)
                border["programming / debug header (free)"].append((tid, f.ref, f.lib_id[:40] + " " + f.value,
                                                                    free[f.uuid]["why"][0]))
            else:
                if kind == "led":
                    border["SMD LED left free"].append((tid, f.ref, f.lib_id, f.value))
                elif kind == "potentiometer":
                    border["trimmer left free"].append((tid, f.ref, f.lib_id, f.value))
                elif kind in ("jumper", "test_point", "battery"):
                    border[f"{kind} left free"].append((tid, f.ref, f.lib_id, f.value))
                elif kind == "connector":
                    border["connector kind left free (IC socket)"].append((tid, f.ref, f.lib_id, f.value))
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=0)
    print(f"{'class':12s} {'A':>5s} {'B':>5s} {'C':>5s} {'all':>5s} {'boards':>6s}  kinds")
    for cl in fixed.CLASSES + ("prog_free",):
        print(f"{cl:12s} {per[(cl, 'A')]:5d} {per[(cl, 'B')]:5d} {per[(cl, 'C')]:5d} {per[(cl, 'all')]:5d} "
              f"{len(boards[cl]):6d}  {dict(kinds[cl].most_common(6)) if cl in kinds else ''}")
    for k, v in border.items():
        print(f"\n{k}: {len(v)}")
        for x in v[:int(os.environ.get("SHOW", "6"))]:
            print("   ", x[0][:40], x[1], x[2][:60], x[3][:24] if len(x[3]) < 26 else x[3][26:])


if __name__ == "__main__":
    main()
