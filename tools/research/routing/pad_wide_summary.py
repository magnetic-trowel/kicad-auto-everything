# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Before/after tables for tracks wider than their land (pad_entry.overhang, necks, land hazards).

    python tools/research/routing/pad_wide_summary.py rd   ROOT BASE_TAG NEW_TAG   # pad_reroute
    python tools/research/routing/pad_wide_summary.py taut ROOT BASE_ROOT          # kae.route.taut

rd: ROOT/<board>/ holds before.kicad_pcb, BASE_TAG.{json,kicad_pcb} and NEW_TAG.{json,kicad_pcb}
(pad_edge_smoke.sh rd-TAG) and phys/<tag>.status.json. Entry counts of every version come from
the current pad_trim.stats (touching same-net shapes merged), so the base's overhanging entries
are counted by the same rule as the new one's.
taut: ROOT/<board>/ holds the new taut.{json,kicad_pcb} (taut_smoke.sh taut), BASE_ROOT/<board>/
the base's; counts from the current taut.board_stats. Needs KiCad (DSN export) for the pads.
"""
import json
import sys
from pathlib import Path


def _j(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def _phys(p):
    st = _j(p)
    if not st:
        return None, {}
    t = {x["id"]: (x.get("contribution"), x.get("value")) for x in st.get("terms", []) if x.get("contribution") is not None}
    return sum(c for c, _ in t.values()), t


def _dphys(d, base, new):
    b0, t0 = _phys(d / "phys" / "before.status.json")
    if b0 is None:
        return "–"
    out = []
    for tag in (base, new):
        x, t = _phys(d / "phys" / f"{tag}.status.json")
        out.append(_pct(x, b0))
    return " / ".join(out)


def _pct(x, b0):
    """Change of a physics total against the input's, in % (absolute when the input's is 0)."""
    if x is None:
        return "pending"
    return f"{(x - b0) / abs(b0) * 100:+.2f} %" if b0 else f"{x - b0:+.3g}"


def _drc(r):
    s = (r or {}).get("drc_out") or {}
    return f"{s.get('errors', '?')}/{s.get('unconnected', '?')}"


def _worse(rb, rn):
    a, b = (rb or {}).get("drc_out") or {}, (rn or {}).get("drc_out") or {}
    w = {t: n - a.get("by_type", {}).get(t, 0) for t, n in (b.get("by_type") or {}).items()
         if n > a.get("by_type", {}).get(t, 0)}
    return ", ".join(f"{t} +{n}" for t, n in w.items()) or "none"


def rd(root, base, new):
    from kae.route import pad_trim as T
    rows, tot = [], {}
    print("| Board | Candidates base/new | Kept base/new | Oblique/acute in / base / new | Overhanging in / base / new "
          "| Necks | Hazards | No target | Track Δ mm base/new | DRC err/unconn new (worse vs base) | Physics base / new |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for d in sorted(Path(root).iterdir()):
        rb, rn = _j(d / f"{base}.json"), _j(d / f"{new}.json")
        if not rb or not rn:
            continue
        info = T._info(d / "before.kicad_pcb")
        st = {k: T.stats((d / f"{k}.kicad_pcb").read_text(encoding="utf-8"), info) for k in ("before", base, new)}
        ob, on = rb["outcome"], rn["outcome"]
        nt = on.get("fail_no_target", 0) + on.get("fail_no_fit", 0)
        row = dict(cb=ob.get("candidates", 0), cn=on.get("candidates", 0), kb=rb.get("kept", 0), kn=rn.get("kept", 0),
                   necks=rn.get("necks", 0), haz=len(rn.get("hazards") or []), nt=nt,
                   lb=rb.get("len_delta_mm", 0.0), ln=rn.get("len_delta_mm", 0.0))
        for k, v in row.items():
            tot[k] = tot.get(k, 0) + v
        for k in ("before", base, new):
            for f in ("oblique", "acute", "overhanging"):
                tot[(k, f)] = tot.get((k, f), 0) + st[k][f]
        print(f"| {d.name[:32]} | {row['cb']}/{row['cn']} | {row['kb']}/{row['kn']} | "
              f"{st['before']['oblique']}/{st['before']['acute']} / {st[base]['oblique']}/{st[base]['acute']} / "
              f"{st[new]['oblique']}/{st[new]['acute']} | {st['before']['overhanging']} / {st[base]['overhanging']} / "
              f"{st[new]['overhanging']} | {row['necks']} | {row['haz']} | {nt} | {row['lb']:+.1f}/{row['ln']:+.1f} | "
              f"{_drc(rn)} ({_worse(rb, rn)}) | {_dphys(d, base, new)} |")
        rows.append(dict(board=d.name, outcome_base=ob, outcome_new=on, stats=st, hazards=rn.get("hazards"),
                         drc_base=rb.get("drc_out"), drc_new=rn.get("drc_out")))
    print(f"| **total** | {tot.get('cb')}/{tot.get('cn')} | {tot.get('kb')}/{tot.get('kn')} | "
          f"{tot[('before', 'oblique')]}/{tot[('before', 'acute')]} / {tot[(base, 'oblique')]}/{tot[(base, 'acute')]} / "
          f"{tot[(new, 'oblique')]}/{tot[(new, 'acute')]} | {tot[('before', 'overhanging')]} / "
          f"{tot[(base, 'overhanging')]} / {tot[(new, 'overhanging')]} | {tot['necks']} | {tot['haz']} | {tot['nt']} | "
          f"{tot['lb']:+.1f}/{tot['ln']:+.1f} | | |")
    return rows


def taut(root, base_root):
    from kae.route import taut as TT
    rows, tot = [], {}
    print("| Board | Branches improved base/new | Oblique/acute entries in / base / new | Overhanging in / base / new "
          "| Necks | Overhangs removed | Hazards | Copper m in / base / new | DRC err/unconn new (worse vs base) "
          "| Physics base / new |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for d in sorted(Path(root).iterdir()):
        b = Path(base_root) / d.name
        rb, rn = _j(b / "taut.json"), _j(d / "taut.json")
        if not rb or not rn:
            continue
        st = {"before": TT.board_stats(d / "before.kicad_pcb"), "base": TT.board_stats(b / "taut.kicad_pcb"),
              "new": TT.board_stats(d / "taut.kicad_pcb")}
        cu = {k: sum(v["length"].values()) / 1000 for k, v in st.items()}
        row = dict(ib=rb["stats"].get("improved", 0), inn=rn["stats"].get("improved", 0), necks=rn.get("necks", 0),
                   fixed=rn.get("overhang_fixed", 0), haz=len(rn.get("hazards") or []))
        for k, v in row.items():
            tot[k] = tot.get(k, 0) + v
        for k in st:
            for f in ("oblique", "acute_entries", "overhanging"):
                tot[(k, f)] = tot.get((k, f), 0) + st[k][f]
            tot[(k, "cu")] = tot.get((k, "cu"), 0) + cu[k]
        ph = "–"
        if (b / "phys" / "before.status.json").exists():
            b0, _ = _phys(b / "phys" / "before.status.json")
            xb, _ = _phys(b / "phys" / "taut.status.json")
            xn, _ = _phys(d / "phys" / "taut.status.json")
            ph = " / ".join(_pct(x, b0) for x in (xb, xn))
        print(f"| {d.name[:32]} | {row['ib']}/{row['inn']} | "
              + " / ".join(f"{st[k]['oblique']}/{st[k]['acute_entries']}" for k in st) + " | "
              + " / ".join(str(st[k]["overhanging"]) for k in st)
              + f" | {row['necks']} | {row['fixed']} | {row['haz']} | "
              + " / ".join(f"{cu[k]:.3f}" for k in st)
              + f" | {_drc(rn)} ({_worse(rb, rn)}) | {ph} |")
        rows.append(dict(board=d.name, stats=st, hazards=rn.get("hazards"), drc_base=rb.get("drc_out"),
                         drc_new=rn.get("drc_out"), skipped_new=rn["stats"].get("skipped")))
    print(f"| **total** | {tot.get('ib')}/{tot.get('inn')} | "
          + " / ".join(f"{tot[(k, 'oblique')]}/{tot[(k, 'acute_entries')]}" for k in ("before", "base", "new")) + " | "
          + " / ".join(str(tot[(k, "overhanging")]) for k in ("before", "base", "new"))
          + f" | {tot['necks']} | {tot['fixed']} | {tot['haz']} | "
          + " / ".join(f"{tot[(k, 'cu')]:.3f}" for k in ("before", "base", "new")) + " | | |")
    return rows


if __name__ == "__main__":
    mode, args = sys.argv[1], sys.argv[2:]
    rows = rd(*args) if mode == "rd" else taut(*args)
    out = Path(args[0]) / f"summary-{mode}.json"
    out.write_text(json.dumps(rows, indent=1, default=str))
