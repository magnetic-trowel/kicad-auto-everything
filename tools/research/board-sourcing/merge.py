#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""merge.py WORKDIR RESULTS_GLOB OUT_DIR

Build bench/manifests/wide*.jsonl from enrich results: rows from any host's results
files plus WORKDIR/meta, restricted to the de-duplicated ids in WORKDIR/keep.txt and
checked against the current candidate rows (same repo/commit/path). Applies the manual
licence decisions below, splits off the noncommercial tier and writes the
near-duplicate map. Prints summary stats.
"""
import collections
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import enrich  # noqa: E402
from kaebench import manifest  # noqa: E402

HERE = Path(__file__).parent
# Manual decisions (see docs/topics/data/open-board-sources.md).
DROP_REPOS = {  # licence only in wiki review notes
    "https://gitlab.com/ohwr/project/fmc-nanofip", "https://gitlab.com/ohwr/project/fmc-vme-carrier"}
FORCE_NC = {  # README: "some discontinued filter boards are NC" without saying which -> most restrictive
    "shruthi": "CC-BY-NC-SA-3.0"}


def main():
    workdir, results_glob, out_dir = sys.argv[1:4]
    rows, _ = enrich.build_rows(str(HERE / "found" / "*.jsonl"), [str(HERE / "../../../bench/manifests/candidates.jsonl")])
    byid = {r["id"]: r for r in rows}
    keep = Path(workdir, "keep.txt").read_text().split()
    res = {}
    sources = [json.loads(l) for f in sorted(glob.glob(results_glob)) for l in open(f)]
    sources += [json.loads(p.read_text()) for p in Path(workdir, "meta").glob("*.json")]
    for r in sources:
        if r.get("_ok") is False or not r.get("layers"):
            continue
        cand = byid.get(r["id"])
        if cand and all(r.get(k) == cand.get(k) for k in ("repo", "commit", "pcb_path", "archive_sha256")):
            res[r["id"]] = r
    out, missing = [], []
    for i in keep:
        if i not in res:
            missing.append(i)
            continue
        r = dict(res[i])
        cand = byid[i]
        for k in ("license", "license_evidence", "license_tier", "dataset", "sch_path"):
            r[k] = cand[k]
        if r["repo"] in DROP_REPOS:
            continue
        for key, lic in FORCE_NC.items():
            if key in r["pcb_path"].lower() and "OR" in r["license"]:
                r["license"], r["license_tier"] = lic, "noncommercial"
                r["license_evidence"] = (r.get("license_evidence") or "") + \
                    " (ambiguous which boards are NC -> most restrictive)"
        out.append({k: r.get(k) for k in enrich.KEYS if k != "archive_sha256" or r.get(k)})
    out.sort(key=lambda r: r["id"])
    out_dir = Path(out_dir)
    main_rows = [r for r in out if r["license_tier"] != "noncommercial"]
    nc_rows = [r for r in out if r["license_tier"] == "noncommercial"]
    for name, rs in (("wide.jsonl", main_rows), ("wide-noncommercial.jsonl", nc_rows)):
        with open(out_dir / name, "w") as f:
            for r in rs:
                f.write(json.dumps(r) + "\n")
        manifest.load(out_dir / name)  # validates every row
    kept = {r["id"] for r in out}
    with open(out_dir / "wide-duplicates.jsonl", "w") as f:
        for l in open(Path(workdir, "dups.jsonl")):
            d = json.loads(l)
            f.write(json.dumps({k: d[k] for k in ("repo", "pcb_path", "rep_repo", "rep_path", "jaccard")}) + "\n")
    # stats
    def c(rs, fn):
        return collections.Counter(x for r in rs for x in fn(r)).most_common()
    print(f"rows {len(out)} (main {len(main_rows)}, nc {len(nc_rows)}), missing results {len(missing)}")
    print("repos", len({r['repo'] for r in out}))
    print("tier", c(out, lambda r: [r["license_tier"]]))
    print("dataset", c(out, lambda r: [r["dataset"]]))
    print("layers", c(out, lambda r: [min(r["layers"], 6) if r["layers"] < 6 else "6+"]))
    print("8+ layers", sum(r["layers"] >= 8 for r in out), "10+", sum(r["layers"] >= 10 for r in out))
    print("tags", c(out, lambda r: r["tags"])[:40])
    print("source", c(out, lambda r: [r["source"]]))
    fps = sorted(r["footprints"] for r in out)
    print("footprints median", fps[len(fps) // 2], "p90", fps[int(len(fps) * .9)], ">=300", sum(f >= 300 for f in fps),
          ">=1000", sum(f >= 1000 for f in fps))
    print("routed", sum(bool(r["routed"]) for r in out), "drc-clean", sum("drc-clean" in r["tags"] for r in out))
    Path(workdir, "missing.txt").write_text("\n".join(missing) + "\n")


if __name__ == "__main__":
    main()
