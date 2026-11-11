# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The bridge runs a Freerouting build that is named, never the newest one installed."""
import os

import pytest

from kae.route import freerouting as FR


def _build(home, name, age):
    b = home / name / "bin" / "freerouting"
    b.parent.mkdir(parents=True)
    b.write_text("#!/bin/sh\n")
    os.utime(b, (age, age))
    return b


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(FR, "KAE_HOME", tmp_path)
    monkeypatch.delenv("KAE_BRIDGE_FREEROUTING", raising=False)
    monkeypatch.delenv("KAE_FREEROUTING", raising=False)
    return tmp_path


def test_newest_install_is_never_picked(home):
    _build(home, "kae-freerouting-fork-aaaaaaa", 1_000)
    _build(home, "kae-freerouting-fork-bbbbbbb-experiment", 2_000)   # newer: an experiment's wrapper
    with pytest.raises(FR.FreeroutingError, match="pinned"):
        FR.command()


def test_pin_names_the_build(home):
    prod = _build(home, "kae-freerouting-fork-aaaaaaa", 1_000)
    _build(home, "kae-freerouting-fork-bbbbbbb-experiment", 2_000)
    (home / FR.PIN_FILE).write_text("kae-freerouting-fork-aaaaaaa/bin/freerouting\n")   # relative to KAE_HOME
    assert FR.command() == [str(prod)]
    (home / FR.PIN_FILE).write_text(str(prod))                                         # absolute
    assert FR.command() == [str(prod)]


def test_a_pin_to_a_missing_build_fails(home):
    (home / FR.PIN_FILE).write_text("kae-freerouting-fork-gone/bin/freerouting")
    with pytest.raises(FR.FreeroutingError, match="not a file"):
        FR.command()


def test_environment_wins_over_the_pin(home, monkeypatch):
    prod = _build(home, "kae-freerouting-fork-aaaaaaa", 1_000)
    (home / FR.PIN_FILE).write_text(str(prod))
    monkeypatch.setenv("KAE_BRIDGE_FREEROUTING", "/opt/fr/freerouting.jar")
    assert FR.command() == ["java", "-jar", "/opt/fr/freerouting.jar"]
    monkeypatch.delenv("KAE_BRIDGE_FREEROUTING")
    monkeypatch.setenv("KAE_FREEROUTING", "/opt/fr2/bin/freerouting")
    assert FR.command() == [str(prod)], "the pin comes before the generic KAE_FREEROUTING"
    (home / FR.PIN_FILE).unlink()
    assert FR.command() == ["/opt/fr2/bin/freerouting"]
