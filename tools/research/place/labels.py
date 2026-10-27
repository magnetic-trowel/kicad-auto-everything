# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Board-level silk labels and the parts they name: inference from the place task's input
alone, validated on the human placement.

A place task keeps the board's own silkscreen texts (gr_text on F/B.SilkS) where the
designer put them, while every movable footprint is staged off the board. A label such as
"SDA" beside a connector pin, "PWR" beside an LED or "ON/OFF" beside a switch names a part
that belongs next to it (noisecard: D1-D10 beside their printed "dB" labels). This tool infers
each label's part from the input board only, then measures on the reference board how close
the human put that part to the label, and how that compares with the other parts.

Inference (kae.place.labels.infer):
  ref      a token equal to a part's reference (D3, U2).
  pin      a token equal to a connector-like part's pad pin function or its net's last name
           component (SDA, GND, 3V3, ~{RST}); a net on several such pads names them all.
  keyword  a token in the net names of an LED or a switch (PWR, ACT, STATUS, RESET, BOOT),
           and ON/OFF for the only switches.
  row      k labels in a row or column carrying distinct numbers and the one family of k
           unlabelled LEDs, switches or connectors with consecutive reference numbers:
           matched in numeric order.

    python tools/research/place/labels.py --tasks kae-work-v3/tasks [--split A] [--ids a,b] [--out FILE]

Prints per split: boards with labels, labels, labels with an inferred part, and for those
the human distance (label box to the part's nearest pad), the share within 3 and 5 mm, and
the part's rank among all footprints by that distance (1 = nearest).
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
from pathlib import Path


def check_task(tdir):
    from kae.board.kicad_file import load
    from kae.place import labels
    t = json.loads((tdir / "task.json").read_text())
    inp = load(tdir / "place" / "input" / "board.kicad_pcb")
    ref = load(tdir / "reference" / "board.kicad_pcb")
    labs = labels.board_labels(inp)
    assoc = labels.infer(inp, labs)
    by_uuid = {f.uuid: f for f in ref.footprints}
    rows = []
    others_by_label = {}
    for a in assoc:
        lab = labs[a["label"]]
        f = by_uuid.get(a["part"])
        if f is None or not f.pads:
            continue
        d = labels.distance(lab["geom"], f, a.get("pads"))
        if a["label"] not in others_by_label:
            others_by_label[a["label"]] = sorted(labels.distance(lab["geom"], g, None) for g in ref.footprints if g.pads)
        others = others_by_label[a["label"]]
        rank = 1 + sum(1 for o in others if o < d - 1e-9)
        rows.append(dict(li=a["label"], label=lab["text"][:24], how=a["how"], ref=f.ref, d=round(d, 2), rank=rank,
                         d_edge=round(labels.distance(lab["geom"], f, a.get("pads"), edge=True), 2)))
    # a label naming several candidates (a "GND" beside one of the connectors with a GND
    # pin) names one of them: the nearest counts
    best = {}
    for r in rows:
        k = (r["li"], r["how"])
        if k not in best or r["d"] < best[k]["d"]:
            best[k] = dict(r, candidates=sum(1 for x in rows if (x["li"], x["how"]) == k))
    keep = list(best.values())
    return dict(id=t["id"], split=t.get("split"), labels=len(labs), inferred=len({r["li"] for r in keep}), rows=keep)


def summarize(results):
    out = {}
    for split in sorted({r["split"] for r in results}):
        rs = [r for r in results if r["split"] == split and "error" not in r]
        assoc = [x for r in rs for x in r["rows"]]
        by_how = collections.defaultdict(list)
        for x in assoc:
            kind = re.sub(r"\d+$", "", x["how"])
            by_how[kind].append(x)
            by_how[f"{kind}/{'one' if x.get('candidates', 1) == 1 else 'several'} candidate(s)"].append(x)

        def stats(xs):
            if not xs:
                return None
            ds = [x["d"] for x in xs]
            return dict(n=len(xs), median_mm=round(statistics.median(ds), 2),
                        within_3mm=round(sum(1 for d in ds if d <= 3) / len(ds), 3),
                        within_5mm=round(sum(1 for d in ds if d <= 5) / len(ds), 3),
                        rank1=round(sum(1 for x in xs if x["rank"] == 1) / len(xs), 3),
                        rank_le3=round(sum(1 for x in xs if x["rank"] <= 3) / len(xs), 3))
        out[split] = dict(boards=len(rs), boards_with_labels=sum(1 for r in rs if r["labels"]),
                          labels=sum(r["labels"] for r in rs),
                          labels_inferred=sum(r.get("inferred", 0) for r in rs),
                          boards_with_inferred=sum(1 for r in rs if r["rows"]),
                          associations=stats(assoc), by_how={k: stats(v) for k, v in sorted(by_how.items())})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", default="kae-work-v3/tasks")
    ap.add_argument("--split")
    ap.add_argument("--ids")
    ap.add_argument("--out")
    ap.add_argument("-v", action="store_true", help="print every association")
    a = ap.parse_args(argv)
    want = set(a.ids.split(",")) if a.ids else None
    results = []
    for tj in sorted(Path(a.tasks).glob("*/task.json")):
        t = json.loads(tj.read_text())
        if not t.get("qualified", True) or (a.split and t.get("split") != a.split) or (want and t["id"] not in want):
            continue
        try:
            r = check_task(tj.parent)
        except Exception as e:      # noqa: BLE001 - one unreadable task must not end the study
            r = dict(id=t["id"], split=t.get("split"), error=f"{type(e).__name__}: {e}", labels=0, rows=[])
        results.append(r)
        if a.v:
            print(r["id"], r.get("error", ""), [(x["label"], x["how"], x["ref"], x["d"], x["rank"]) for x in r["rows"]],
                  flush=True)
    summ = summarize(results)
    print(json.dumps(summ, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(dict(summary=summ, boards=results), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
