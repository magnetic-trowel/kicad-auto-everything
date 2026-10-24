# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-seed summary of joint runs (harness score v7, --kinds joint, -k seeds):

    python agg3.py RUN_DIR [RUN_DIR ...] [--suite FILE] [--seeds 3] [--per-board]

Per run and seed (attempt-N = seed N): legal, clean, completion, open connections (DRC
unconnected, summed), error count; routed length and vias summed over the boards that
every run completed at that seed. Printed as mean +- half-range over seeds. Reads the
harness score only (attempt.json); never re-scores.
"""
import argparse
import json
from pathlib import Path


def load(run, attempt):
    out = {}
    for f in Path(run).glob(f"*/joint/*/attempt-{attempt}/attempt.json"):
        r = json.loads(f.read_text())
        s = r.get("score") or {}
        out[r["id"]] = dict(
            split=r.get("split"), legal=bool(s.get("legal")), clean=bool(s.get("clean")) and bool(s.get("legal")),
            completion=s.get("completion", 0.0) if s.get("valid") else 0.0,
            open=s.get("unconnected", 0) if s.get("valid") else s.get("start_unconnected", 0),
            errors=s.get("errors", 0) or 0, length=s.get("track_length_mm"), vias=s.get("vias"))
    return out


def pm(xs, fmt="{:.3f}"):
    if not xs:
        return "-"
    m = sum(xs) / len(xs)
    h = (max(xs) - min(xs)) / 2
    return (fmt + " ± " + fmt).format(m, h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suite")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--per-board", action="store_true")
    a = ap.parse_args()
    ids = None
    if a.suite:
        ids = [x.strip() for x in Path(a.suite).read_text().split() if x.strip() and not x.startswith("#")]
    data = {Path(r).name: [load(r, s) for s in range(a.seeds)] for r in a.runs}
    if ids is None:
        ids = sorted(set.intersection(*[set(d[0]) for d in data.values()]))
    print(f"boards: {len(ids)}, seeds: {a.seeds} (mean ± half-range over seeds)\n")
    print("| run | legal | clean | completion | open conn. | errors | length (mm) | vias | boards in len |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, seeds in data.items():
        cols = {k: [] for k in ("legal", "clean", "completion", "open", "errors", "length", "vias")}
        nfull = []
        for s, d in enumerate(seeds):
            if not all(i in d for i in ids):
                continue
            rows = [d[i] for i in ids]
            n = len(rows)
            for k in ("legal", "clean", "completion"):
                cols[k].append(sum(r[k] for r in rows) / n)
            cols["open"].append(sum(r["open"] for r in rows))
            cols["errors"].append(sum(r["errors"] for r in rows))
            full = [i for i in ids if all(i in dd[s] and dd[s][i]["completion"] >= 1.0 and dd[s][i]["length"]
                                          for dd in data.values())]
            cols["length"].append(sum(d[i]["length"] for i in full))
            cols["vias"].append(sum(d[i]["vias"] for i in full))
            nfull.append(len(full))
        print(f"| {name} | {pm(cols['legal'])} | {pm(cols['clean'])} | {pm(cols['completion'])} "
              f"| {pm(cols['open'], '{:.1f}')} | {pm(cols['errors'], '{:.1f}')} | {pm(cols['length'], '{:.0f}')} "
              f"| {pm(cols['vias'], '{:.1f}')} | {nfull} |")
    if a.per_board:
        names = list(data)
        print("\nper board, seed 0: clean/legal mark, completion, length, vias")
        print("| board | split | " + " | ".join(names) + " |")
        print("|---|---|" + "---|" * len(names))
        for i in ids:
            cells = []
            for nm in names:
                r = data[nm][0].get(i)
                if r is None:
                    cells.append("?")
                    continue
                mark = "C" if r["clean"] else ("L" if r["legal"] else "-")
                cells.append(f"{mark} {r['completion']:.2f} {r['length'] or 0:.0f} {r['vias'] or 0}")
            sp = next((data[nm][0][i]["split"] for nm in names if i in data[nm][0]), "?")
            print(f"| {i[:40]} | {sp} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
