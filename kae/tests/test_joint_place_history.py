# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.joint.feedback.CongestionHistory save / merged: the history attempts pass each other."""
import numpy as np

from kae.joint.feedback import CongestionHistory


def _hist(amount):
    h = CongestionHistory((0.0, 0.0, 10.0, 10.0), bin_mm=1.0)
    h.add_corridor((2.0, 2.0), (8.0, 2.0), width=1.0, amount=amount)
    return h


def test_merged_is_the_mean_over_attempts(tmp_path):
    a, b = _hist(1.0), _hist(3.0)
    a.save(tmp_path / "h-0-1.npz")
    b.save(tmp_path / "h-1-2.npz")
    m = CongestionHistory.merged(sorted(tmp_path.glob("h-*.npz")))
    assert m.attempts == 2
    assert np.allclose(m.h, (a.h + b.h) / 2.0)
    assert m.b == 1.0 and m.x0 == 0.0 and m.h.shape == a.h.shape
    # it still samples onto another grid, as the placer's hook does
    assert m.sample(0.0, 0.0, 2.0, 5, 5).sum() > 0


def test_merged_skips_broken_files_and_other_grids(tmp_path):
    _hist(1.0).save(tmp_path / "h-0-1.npz")
    (tmp_path / "h-9-9.npz").write_bytes(b"not a zip")
    other = CongestionHistory((0.0, 0.0, 20.0, 20.0), bin_mm=1.0)
    other.add_corridor((1.0, 1.0), (9.0, 1.0), width=1.0)
    other.save(tmp_path / "h-5-5.npz")
    m = CongestionHistory.merged(sorted(tmp_path.glob("h-*.npz")))
    assert m is not None
    assert m.attempts == 1


def test_merged_empty(tmp_path):
    assert CongestionHistory.merged([]) is None
