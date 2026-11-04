# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the datasheet library (datasheet_prompt.md): every value's number must appear on the PDF page it
cites (in the page's pdftotext text, in any SI scaling: mA, uA, nC, pF, MHz ...). Writes index.jsonl
(one line per part: its datasheet, sha256, and counts) and marks each value "verified": true / false.

    python datasheet_check.py [LIBRARY]         (default $KAE_DATASHEETS or ~/kae-datasheets)

A value that is not found is not wrong by itself (a scanned PDF, a graph read, a sum of rows): it is
unverified, and a consumer may choose to use only verified values.
"""
import glob
import hashlib
import json
import os
import re
import sys

SCALES = (1, 1e3, 1e6, 1e9, 1e12, 1e-3, 1e-6)


def _forms(x):
    out = set()
    for s in (f"{x:g}", f"{x:.1f}", f"{x:.2f}", f"{x:.3f}"):
        out.add(s.rstrip("0").rstrip(".") if "." in s else s)
    return out


def _pages(lib, pdf):
    base = os.path.basename(pdf)[:-4]
    for c in [f"{lib}/text/{base}.txt"] + sorted(glob.glob(f"{lib}/text/{base}*.txt")):
        if os.path.exists(c):
            return open(c, errors="replace").read().split("\f")
    return None


def found(pages, page, nums):
    if not pages or not isinstance(page, int) or not 1 <= page <= len(pages):
        return False
    txt = pages[page - 1]
    for n in nums:
        for sc in SCALES:
            for s in _forms(n * sc):
                if re.search(r"(?<![\d.])" + re.escape(s) + r"(?![\d])", txt):
                    return True
    return False


def main(argv=None):
    lib = os.path.expanduser((argv or sys.argv[1:] or [os.environ.get("KAE_DATASHEETS", "~/kae-datasheets")])[0])
    index, tot = [], dict(values=0, verified=0)
    for p in sorted(glob.glob(f"{lib}/facts/*.json")):
        f = json.load(open(p))
        ds = f.get("datasheet") or {}
        pdf = ds.get("pdf")
        pages = _pages(lib, pdf) if pdf else None
        n = v = 0
        for k, val in (f.get("values") or {}).items():
            if not isinstance(val, dict) or k == "package":
                continue
            nums = [val.get(x) for x in ("typ", "min", "max") if isinstance(val.get(x), (int, float))]
            if not nums:
                continue
            val["verified"] = found(pages, val.get("page"), nums)
            n += 1
            v += val["verified"]
        if pdf and os.path.exists(f"{lib}/{pdf}"):
            ds["sha256"] = hashlib.sha256(open(f"{lib}/{pdf}", "rb").read()).hexdigest()
        with open(p, "w") as fh:
            json.dump(f, fh, indent=1)
            fh.write("\n")
        index.append(dict(slug=os.path.basename(p)[:-5], query=f.get("query"), part=f.get("part"),
                          identified=f.get("identified"), kind=f.get("kind"), pdf=pdf, url=ds.get("url"),
                          sha256=ds.get("sha256"), values=n, verified=v))
        tot["values"] += n
        tot["verified"] += v
    with open(f"{lib}/index.jsonl", "w") as fh:
        for r in index:
            fh.write(json.dumps(r) + "\n")
    print(f"{len(index)} parts, {sum(1 for r in index if r['pdf'])} with a datasheet; values {tot['values']}, "
          f"verified on their cited page {tot['verified']}")


if __name__ == "__main__":
    sys.exit(main())
