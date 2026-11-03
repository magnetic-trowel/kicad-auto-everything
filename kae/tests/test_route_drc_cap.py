# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.route.drc: the unconnected count past kicad-cli's report cap of 499."""
import json

from kae.route import drc


def test_summary_counts_past_the_cap(monkeypatch, tmp_path):
    items = [dict(items=[dict(description=f"Pad 1 [N{i}] of U1")]) for i in range(499)]

    def fake_run(cmd, **kw):
        out = cmd[cmd.index("-o") + 1]
        json.dump(dict(violations=[], unconnected_items=items), open(out, "w"))
        return type("R", (), dict(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(drc, "kicad_cli", lambda: ("kicad-cli",))
    monkeypatch.setattr(drc.subprocess, "run", fake_run)
    monkeypatch.setattr(drc, "uncapped_unconnected", lambda board, timeout=900: 1306)
    b = tmp_path / "board.kicad_pcb"
    b.write_text("(kicad_pcb)\n")
    rep = drc.run(b, tmp_path / "drc.json")
    assert drc.summary(rep)["unconnected"] == 1306
    del items[0]                                    # 498: below the cap DRC's own list is the count
    rep = drc.run(b, tmp_path / "drc2.json")
    assert drc.summary(rep)["unconnected"] == 498 and "unconnected_count" not in rep
