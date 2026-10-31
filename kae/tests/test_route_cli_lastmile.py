# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""`kae.route.cli lastmile`: the post-route stage alone, as the restart wrapper's final pass calls it."""
import json

from kae.route import bridge, cli


def test_lastmile_command_passes_board_input_and_options(monkeypatch, capsys, tmp_path):
    seen = {}

    def fake(input_path, board_path, output_path, time_s, seed, workdir, opts):
        seen.update(input=input_path, board=board_path, output=output_path, time=time_s, seed=seed, opts=opts)
        return dict(status="repaired", final=dict(unconnected=0, errors=0))
    monkeypatch.setattr(bridge, "last_mile_only", fake)
    rc = cli.main(["lastmile", "in.kicad_pcb", "best.kicad_pcb", "out.kicad_pcb", "--time", "90", "--seed", "7",
                   "--set", "last_mile_free_first=false", "--report", str(tmp_path / "r.json")])
    assert rc == 0
    assert seen["input"] == "in.kicad_pcb" and seen["board"] == "best.kicad_pcb" and seen["output"] == "out.kicad_pcb"
    assert seen["time"] == 90.0 and seen["seed"] == 7 and seen["opts"]["last_mile_free_first"] is False
    assert json.loads((tmp_path / "r.json").read_text())["status"] == "repaired"


def test_lastmile_command_fails_cleanly(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("no board")
    monkeypatch.setattr(bridge, "last_mile_only", boom)
    assert cli.main(["lastmile", "a", "b", "c"]) == 2
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "error"


def test_route_first_reads_the_restart_history(monkeypatch, tmp_path):
    h = tmp_path / "history.json"
    h.write_text(json.dumps({"SCLK": 2, "MOSI": 1, "GND": 0}))
    monkeypatch.delenv("KAE_ROUTE_HISTORY", raising=False)
    assert bridge.route_first({}) == ([], None)
    monkeypatch.setenv("KAE_ROUTE_HISTORY", str(h))
    assert bridge.route_first({}) == (["SCLK", "MOSI"], str(h))
    assert bridge.route_first({"history": str(tmp_path / "missing.json")})[0] == []   # unreadable: empty
