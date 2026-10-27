# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Features and restart-pruning policies shared by the trainer (lv_model.py) and the
steered jc (lv_jc.jc_value / jc_heur).

A decision compares the running restart a at checkpoint c (iteration c of its beta
continuation; c = 0 is right after the lift) with the incumbent b (the best finished
restart on this board): features of b at checkpoint min(c, last checkpoint of b).
The model predicts dy = log(1 + cost_a) - log(1 + cost_b) of the two restarts' final
scores; the restart is abandoned when dy > margin. Pairs keep the board's scale out of
the model (costs span 5 to 3000 between boards), so it transfers across boards.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")  # sklearn/OpenMP: one thread (CPU budget, shared machine)
import json
import math
from pathlib import Path

import numpy as np

LOGF = ["hpwl", "phys", "route_cost", "length", "vias", "unrouted", "hist_sum", "hist_max",
        "hist_p99", "histc_sum", "fv", "xings", "ovf", "overlap", "wire_conf", "nets_bad", "moved"]
CHECKS = (0, 1, 2, 3, 5, 8, 12, 20, 30, 50)


def vec(f, phys_w):
    v = [math.log1p(max(float(f.get(k, 0.0) or 0.0), 0.0)) for k in LOGF]
    v.append(math.log1p(1e4 * float(f.get("hist_nz", 0.0))))
    v.append(math.log1p(max(f.get("route_cost", 0.0) + phys_w * f.get("phys", 0.0), 0.0)))
    v.append(math.log1p(f.get("overlap", 0) + f.get("wire_conf", 0)))
    return np.array(v)


VNAMES = LOGF + ["hist_nz", "cur_cost", "conf"]


def pair_x(fa, fb, b_done, c, board, phys_w, cap=42.0):
    va, vb = vec(fa, phys_w), vec(fb, phys_w)
    ctx = [c, math.log1p(100 * fa.get("beta", 0.0)), float(b_done), math.log(board["nets"] + 1),
           math.log(board["parts"] + 1), math.log(board["area_mm2"] + 1), fa.get("t_run", 0.0) / cap]
    return np.concatenate([va - vb, va, ctx])


PNAMES = ["d_" + n for n in VNAMES] + ["a_" + n for n in VNAMES] + \
    ["c", "beta", "b_done", "nets", "parts", "area", "tfrac"]


class _Base:
    """Holds the incumbent's checkpoints; subclass implements dy()."""

    def start(self, board_id, board, phys_w):
        self.bid, self.board, self.phys_w = board_id, board, phys_w
        self.cur = {}      # checkpoints of the running restart
        self.inc = None    # (final cost, {c: feats}) of the best finished restart
        self.runs = {}

    def __call__(self, stage, it, feats, lift_ref, best_cost):
        k = feats["k"]
        if k not in self.runs:
            self.runs = {k: {}}
        self.runs[k][it] = feats
        if it not in CHECKS or self.inc is None:
            return False
        cb, ckb = self.inc
        last = max(ckb)
        fb = ckb.get(min(it, last))
        if fb is None:
            fb = ckb[max(c for c in ckb if c <= min(it, last))]
        return self.dy(feats, fb, it > last, it) > self.margin

    def finished(self, k, cost):
        if k in self.runs and (self.inc is None or cost < self.inc[0]):
            self.inc = (cost, dict(self.runs[k]))


class ValuePolicy(_Base):
    def __init__(self, model_dir, margin=None):
        import joblib
        self.dir = Path(model_dir)
        self.meta = json.loads((self.dir / "meta.json").read_text())
        self.joblib = joblib
        self.margin_override = margin

    def start(self, board_id, board, phys_w, path=""):
        super().start(board_id, board, phys_w)
        obj = "phys" if phys_w > 0 else "lv"
        m = self.meta[obj]
        # the kaebench sandbox hides the task tree, so jc's _board_id can miss: match the
        # input path against the training boards (a board in no fold was never trained on)
        if board_id not in m["folds"]:
            for s_ in reversed(Path(path).parts):
                if s_ in m["folds"]:
                    board_id = s_
                    break
        self.bid = board_id
        fold = m["folds"].get(board_id, "all")
        self.fold = fold
        self.model = self.joblib.load(self.dir / obj / f"fold{fold}.pkl")
        self.margin = float(self.margin_override if self.margin_override is not None
                            else m["margin"][str(fold)])

    def dy(self, fa, fb, b_done, c):
        x = pair_x(fa, fb, b_done, c, self.board, self.phys_w)
        return float(self.model.predict(x[None, :])[0])


class HeuristicPolicy(_Base):
    """dy = log(1 + current routed cost + phys_w * physics) of the running restart minus
    the incumbent's at the same checkpoint."""

    def __init__(self, margin=None, model_dir=None):
        self.margin_default = margin

    def start(self, board_id, board, phys_w, path=""):
        super().start(board_id, board, phys_w)
        self.fold = None
        self.margin = 0.3 if self.margin_default is None else float(self.margin_default)

    def dy(self, fa, fb, b_done, c):
        va, vb = vec(fa, self.phys_w), vec(fb, self.phys_w)
        i = VNAMES.index("cur_cost")
        return float(va[i] - vb[i])
