# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A board's kae.intent from a few facts about it (board_summary.py + a model's reading of it), under
the benchmark's standing priorities: power loss and efficiency, ripple, and EMI wherever the board has
a radio or a satellite receiver. Every term says where it came from.

    python intent_from_facts.py FACTS.json SUMMARY.json -o INTENT.json [--operating OPERATING.json]

FACTS (kae.board-facts/1): {"purpose": str, "radio": bool, "radio_parts": [refs], "radio_kinds": [str],
"enclosure": "none|plastic|metal|unknown", "cables": [{"connector": ref, "length_m": m, "why": str}],
"connectors": [{"ref", "function", "direction": "input|output|bidirectional|unknown",
"carries": "power|signal|both", "power": {"net", "volts", "amps"} | null, "why"}], "why": str}.
Only parts and connectors that exist on the board are used; the rest is dropped and listed.

OPERATING (kae.excite.evaluate --intent): the current each output connector delivers off the board,
{"parts": {ref: {"I_A": [0.5 a, 1.5 a]}}}, replacing the evaluator's class prior (a tenth of a
connector's rating, x0.1 .. x5). Input connectors are the board's sources; their current is the loads'.
"""
import argparse
import json
import sys

STANDING = "standing benchmark priority (2026-11-01): always power loss, efficiency and ripple; EMI on boards with a radio or GPS"
RADIO_FAIL = "the receiver's sensitivity: switching noise on its supply or pins desenses it"


def compile_intent(facts, summary):
    refs = {p["ref"] for p in summary.get("parts") or []} | {r for s in summary.get("sections") or [] for r in s.get("parts") or []}
    dropped = []
    radio_parts = [r for r in facts.get("radio_parts") or [] if r in refs or dropped.append(r)]
    cables = []
    for c in facts.get("cables") or []:
        if c.get("connector") in refs:
            cables.append(dict(connector=c["connector"], length_m=float(c.get("length_m") or 1.0),
                               why=f"guessed: {c.get('why') or 'cable on this connector'}"))
        else:
            dropped.append(c.get("connector"))
    radio = bool(facts.get("radio")) and bool(radio_parts)
    feedback = any(s["id"].startswith("victim:feedback") for s in summary.get("sections") or [])
    terms = [
        dict(id="P1", tier="cost", obs="loss.copper", rate="1 mW_eq/mW", agg="cvar20",
             why=f"power loss and efficiency: every mW the copper burns. {STANDING}"),
        dict(id="P2", tier="report", obs="drop.rail", why="rail drop is already paid for in P1; listed for regulation"),
        dict(id="R1", tier="cost", obs="supply.peak", rate="1 mW_eq/mV", agg="cvar20",
             why=f"ripple: noise on every IC's supply pins from the board's aggressors. {STANDING}"),
        dict(id="R3", tier="report", obs="overshoot.peak", why="switch ring; no voltage ratings known to make it a limit"),
    ]
    if feedback:
        terms.append(dict(id="R2", tier="cost", obs="pickup.peak", where={"to": "victim:feedback:*"}, rate="10 mW_eq/mV",
                          agg="cvar20", why=f"ripple and regulation: noise the converters' own feedback pins pick up. {STANDING}"))
    if radio:
        kinds = ", ".join(facts.get("radio_kinds") or []) or "radio"
        terms += [
            dict(id="E1", tier="cost", obs="supply.peak", where={"part": radio_parts}, rate="20 mW_eq/mV", agg="cvar20",
                 why=f"EMI into the {kinds} ({', '.join(radio_parts)}): {RADIO_FAIL}; on top of R1. {STANDING}"),
            dict(id="E2", tier="cost", obs="pickup.peak", where={"part": radio_parts}, rate="20 mW_eq/mV", agg="cvar20",
                 why=f"EMI into the {kinds} pins ({', '.join(radio_parts)}): {RADIO_FAIL}. {STANDING}"),
        ]
        if cables:
            terms.append(dict(id="E3", tier="limit", obs="emission.cable_E", max="30 dBuV/m", rate="20 mW_eq/dB",
                              source="CISPR 32 class B, 30-230 MHz, 10 m (reference)",
                              why=f"EMI: a board with a {kinds} radiating from its own cables. {STANDING}"))
        else:
            terms.append(dict(id="E3", tier="report", obs="cable_cm.v", why="no cable declared: common mode reported only"))
    else:
        terms.append(dict(id="E3", tier="report", obs="cable_cm.v", why="no radio or GPS: EMI is not a standing priority here"))
    intent = {
        "schema": "kae.intent/1", "generation": 1, "currency": "mW_eq", "defaults": "neutral/1",
        "environment": {"enclosure": {"kind": facts.get("enclosure") or "unknown", "why": "guessed from the board summary"},
                        "cables": cables if radio else []},
        "terms": terms,
        "provenance": dict(facts=facts, dropped_refs=[d for d in dropped if d],
                           note="board facts guessed by a model from board_summary.py; the term rates are the benchmark's, "
                                "the same on every board; GNSS and Wi-Fi bands above ~300 MHz are not computable (reported as such)"),
    }
    return intent


def operating(facts, summary):
    """The evaluator's operating facts from the connectors: what each output connector exports."""
    refs = {p["ref"] for p in summary.get("parts") or []}
    parts, why = {}, {}
    for c in facts.get("connectors") or []:
        pw = c.get("power") or {}
        a = pw.get("amps")
        if c.get("ref") in refs and c.get("direction") == "output" and c.get("carries") in ("power", "both") \
                and isinstance(a, (int, float)) and a > 0:
            parts[c["ref"]] = {"I_A": [round(0.5 * a, 6), round(1.5 * a, 6)]}
            why[c["ref"]] = f"guessed: {c.get('function') or 'power output'} ({a:g} A typical); {c.get('why') or ''}".strip()
    return {"parts": parts, "provenance": dict(why=why, note="connector export currents guessed by a model from "
                                                              "board_summary.py; the same file for every method on this board")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("facts"), ap.add_argument("summary"), ap.add_argument("-o", required=True)
    ap.add_argument("--operating", help="also write the evaluator's operating facts (kae.excite.evaluate --intent)")
    a = ap.parse_args(argv)
    from kae.intent import objective as OBJ
    facts, summary = json.load(open(a.facts)), json.load(open(a.summary))
    it = compile_intent(facts, summary)
    it["provenance"]["connectors"] = facts.get("connectors") or []
    OBJ.load(dict(it))          # the intent's own checks: units, tiers, rates, why
    with open(a.o, "w") as f:
        json.dump(it, f, indent=1)
        f.write("\n")
    if a.operating:
        with open(a.operating, "w") as f:
            json.dump(operating(facts, summary), f, indent=1)
            f.write("\n")


if __name__ == "__main__":
    sys.exit(main())
