#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kh_select.py AUDIT_JSONL CATALOG_JSON OUT_FOUND_JSONL OUT_REVIEW_JSONL

Pick boards from the licence-audited kicad-happy repos. One licence family in the
licence files, no README line naming a different hardware licence, no NC/ND/ARR flag
(CC NC without ND -> noncommercial). Up to 15 boards per repo; near-duplicate revisions are removed later by content.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from classify import PAT, classify  # noqa: E402

SPDX = {"GPL-3.0": "GPL-3.0-only", "GPL-2.0": "GPL-2.0-only", "AGPL-3.0": "AGPL-3.0-only", "LGPL-3.0": "LGPL-3.0-only"}
SKIP = re.compile(r"panel|panelized|jig|test|template|example|footprint|lib(rary)?/|/libs?/|old|backup|archive|"
                  r"deprecated|obsolete|frame|stencil|_bak|-bak|copy|rescue|demo/|/qa/|tmp|scratch", re.I)
NC = re.compile(r"Attribution-NonCommercial-ShareAlike|by-nc-sa|CC[- ]BY[- ]NC[- ]SA|Attribution-NonCommercial |by-nc/|CC[- ]BY[- ]NC\b", re.I)
ND = re.compile(r"NoDeriv|by-nc-nd|by-nd|CC[- ]BY[- ](NC[- ])?ND", re.I)
HW_LINE = re.compile(r"hardware|pcb|kicad|schematic|board|design files", re.I)


def other_licences_in_readme(rec, mine):
    hits = set()
    for lines in rec.get("readme_license_lines", {}).values():
        for l in lines:
            if not HW_LINE.search(l):
                continue
            for spdx, rx in PAT:
                if re.search(rx, l, re.I) and spdx.split("-")[0] != mine.split("-")[0]:
                    hits.add(spdx)
    return hits


def pick_boards(pcbs, n):
    cands = [p for p in pcbs if not SKIP.search(p)]
    def score(p):
        stem, parent = Path(p).stem.lower(), Path(p).parent.name.lower()
        return (stem == parent or parent in ("pcb", "hardware", "kicad", "") or stem in p.lower().split("/")[0].lower(),
                -p.count("/"))
    return sorted(cands, key=score, reverse=True)[:n]


def main():
    audit, catalog, out_found, out_review = sys.argv[1:5]
    cat = {c["url"].rstrip("/").lower(): c for c in json.load(open(catalog))}
    nf = nr = 0
    with open(out_found, "w") as fo, open(out_review, "w") as fr:
        for line in open(audit):
            a = json.loads(line)
            if "error" in a or not a.get("kicad_pcb"):
                continue
            found, bad = classify(a)
            fams = sorted(set(s for _, s in found))
            texts = " ".join(a["license_files"].values()) + " " + " ".join(
                l for ls in a["readme_license_lines"].values() for l in ls)
            tier_lic, ev = None, None
            if ND.search(texts):
                continue
            if NC.search(texts):
                m = re.search(r"by-nc-sa/(\d\.\d)|NonCommercial-ShareAlike (\d\.\d)", texts, re.I)
                ver = (m.group(1) or m.group(2)) if m else "4.0"
                tier_lic = f"CC-BY-NC-SA-{ver}" if re.search(r"ShareAlike|nc-sa|NC[- ]SA", texts, re.I) else f"CC-BY-NC-{ver}"
                ev = "licence/README text names " + tier_lic
            elif bad:
                fr.write(json.dumps({"repo": a["repo"], "commit": a["commit"], "why": "flagged: " + "; ".join(bad)[:300]}) + "\n")
                nr += 1
                continue
            elif len(fams) != 1:
                if fams:
                    fr.write(json.dumps({"repo": a["repo"], "commit": a["commit"], "why": f"multiple licences {fams}"}) + "\n")
                    nr += 1
                continue
            else:
                other = other_licences_in_readme(a, fams[0])
                if other:
                    fr.write(json.dumps({"repo": a["repo"], "commit": a["commit"],
                                         "why": f"LICENSE {fams[0]} but README hardware line names {sorted(other)}"}) + "\n")
                    nr += 1
                    continue
                tier_lic = SPDX.get(fams[0], fams[0])
                ev = [p for p, s in found if s == fams[0]][0]
            c = cat.get(a["repo"].rstrip("/").lower(), {})
            layers = (c.get("complexity") or {}).get("pcb_layers_max") or 0
            for p in pick_boards(a["kicad_pcb"], 15):  # near-duplicates are removed after stats
                stem = p[:-len(".kicad_pcb")]
                fo.write(json.dumps(dict(repo=a["repo"], commit=a["commit"], pcb_path=p, sch_path=stem + ".kicad_sch",
                                         license=tier_lic, license_evidence=ev, name=None,
                                         category=None, notes=f"From kicad-happy catalog @8bae5a0 ({c.get('category', '?')})."))
                         + "\n")
                nf += 1
    print(f"{nf} boards selected, {nr} repos for review", file=sys.stderr)


if __name__ == "__main__":
    main()
