# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kaebench's stock Freerouting is named (KAE_FREEROUTING or a pin), never the newest install."""
import hashlib

import pytest

from kaebench import tools


def _bundle(home, name, jar=b"jar"):
    b = home / name / "bin" / "freerouting"
    b.parent.mkdir(parents=True)
    b.write_text("#!/bin/sh\n")
    (home / name / "lib").mkdir()
    (home / name / "lib" / "freerouting.jar").write_bytes(jar)
    return b


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "KAE_HOME", tmp_path)
    monkeypatch.delenv("KAE_FREEROUTING", raising=False)
    tools.freerouting_cmd.cache_clear()
    yield tmp_path
    tools.freerouting_cmd.cache_clear()


def test_two_installs_without_a_pin_raise(home):
    _bundle(home, "freerouting-2.5.0-linux-x64")
    _bundle(home, "freerouting-2.6.0-RC10-20261106-linux-x64")   # sorts last: was the default
    with pytest.raises(tools.ToolError, match="pinned"):
        tools.freerouting_cmd()


def test_the_pin_names_the_build(home):
    stock = _bundle(home, "freerouting-2.5.0-linux-x64")
    _bundle(home, "freerouting-2.6.0-RC10-20261106-linux-x64")
    (home / tools.STOCK_PIN).write_text("freerouting-2.5.0-linux-x64/bin/freerouting\n")
    assert tools.freerouting_cmd() == [str(stock)]


def test_a_pin_to_a_missing_build_fails(home):
    (home / tools.STOCK_PIN).write_text("freerouting-9.9.9-linux-x64/bin/freerouting")
    with pytest.raises(tools.ToolError, match="not a file"):
        tools.freerouting_cmd()


def test_environment_wins_over_the_pin(home, monkeypatch):
    stock = _bundle(home, "freerouting-2.5.0-linux-x64")
    (home / tools.STOCK_PIN).write_text(str(stock))
    monkeypatch.setenv("KAE_FREEROUTING", "/opt/fr/freerouting-2.5.0.jar")
    assert tools.freerouting_cmd() == ["java", "-jar", "/opt/fr/freerouting-2.5.0.jar"]


def test_identity_is_the_bundles_jar(home):
    stock = _bundle(home, "freerouting-2.5.0-linux-x64", jar=b"the 2.5.0 jar")
    ident = tools.freerouting_identity([str(stock)])
    assert ident["path"] == str(stock) and ident["file"].endswith("lib/freerouting.jar")
    assert ident["sha256"] == hashlib.sha256(b"the 2.5.0 jar").hexdigest()
