# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-seed DRC table of joint runs (kaebench --kinds joint, -k seeds = attempts).

    python seeds.py kae-v7/results/RUN1 kae-v7/results/RUN2 ... [--suite kae-v7/ab33.txt]

Per run and attempt (seed): legal, clean and completion over the suite (a missing or
failed attempt counts as not legal, not clean, completion 0); length and vias summed over
the boards that every run completed on every seed; statuses; DRC error types. Then mean
and spread (min..max) over seeds.
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def load(run, ids):
    out = {}  # (id, attempt) -> row
    for f in Path(run).glob("*/joint/*/attempt-*/attempt.json"):
        r = json.loads(f.read_text())
        if r["id"] not in ids:
            continue
        s = r.get("score") or {}
        out[(r["id"], r["attempt"])] = dict(
            status=r.get("status"), legal=bool(s.get("legal")), clean=bool(s.get("clean")),
            completion=float(s.get("completion") or 0.0) if s.get("valid") else 0.0,
            length=s.get("track_length_mm"), vias=s.get("vias"), errors=s.get("errors_by_type") or {},
            place_err=s.get("placement_errors") or {}, valid=s.get("valid"), t=r.get("runtime_s"))
    return out


def ms(xs, nd=3):
    m = sum(xs) / len(xs)
    return f"{m:.{nd}f} ± {(max(xs) - min(xs)) / 2:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suite", default="kae-v7/ab33.txt")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--override", action="append", default=[], metavar="RUN=OTHER",
                    help="take the --override-ids boards of RUN from run directory OTHER")
    ap.add_argument("--override-ids", default=None, help="file of board ids for --override")
    a = ap.parse_args()
    ids = [x for x in Path(a.suite).read_text().split() if x]
    data = {Path(r).name: load(r, set(ids)) for r in a.runs}
    oids = set(Path(a.override_ids).read_text().split()) if a.override_ids else set()
    for o in a.override:
        run, other = o.split("=", 1)
        d = {k: v for k, v in data[run].items() if k[0] not in oids}
        d.update(load(other, oids & set(ids)))
        data[run] = d
    seeds = range(a.seeds)
    full = [i for i in ids if all(d.get((i, k), {}).get("completion", 0) >= 1.0 and d[(i, k)]["length"]
                                  for d in data.values() for k in seeds)]
    print(f"{len(ids)} boards, {a.seeds} seeds; length/vias over the {len(full)} boards every run completed on every seed\n")
    print("| run | legal | clean | completion | length (mm) | vias | per seed legal / clean / completion | attempts | statuses |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, d in data.items():
        L, C, P, LEN, V = [], [], [], [], []
        per = []
        for k in seeds:
            rows = [d.get((i, k)) or dict(legal=False, clean=False, completion=0.0) for i in ids]
            L.append(sum(r["legal"] for r in rows) / len(ids))
            C.append(sum(r["clean"] for r in rows) / len(ids))
            P.append(sum(r["completion"] for r in rows) / len(ids))
            LEN.append(sum(d[(i, k)]["length"] for i in full))
            V.append(sum(d[(i, k)]["vias"] for i in full))
            per.append(f"{L[-1]:.3f}/{C[-1]:.3f}/{P[-1]:.3f}")
        st = Counter(r["status"] for r in d.values())
        print(f"| {name} | {ms(L)} | {ms(C)} | {ms(P)} | {ms(LEN, 0)} | {ms(V, 1)} | {'; '.join(per)} "
              f"| {len(d)} | {dict(st)} |")
    print("\nDRC error types (sum over all attempts; placement errors in brackets):\n")
    for name, d in data.items():
        e, pe = Counter(), Counter()
        for r in d.values():
            e.update(r["errors"])
            pe.update(r["place_err"])
        print(f"- {name}: {dict(e.most_common())} [{dict(pe.most_common())}]")
    print("\nNon-ok attempts:\n")
    for name, d in data.items():
        bad = sorted((i, k, r["status"]) for (i, k), r in d.items() if r["status"] != "ok")
        if bad:
            print(f"- {name}: " + "; ".join(f"{i} #{k} {s}" for i, k, s in bad))


if __name__ == "__main__":
    main()
