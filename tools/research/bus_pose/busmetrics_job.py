#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run busmetrics.process on one job file (JSON: board, runs). Usage: busmetrics_job.py JOB OUT.jsonl"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import busmetrics as X  # noqa: E402

job = json.load(open(sys.argv[1]))
os.makedirs(X.TMP, exist_ok=True)
with open(sys.argv[2], 'w') as out:
    X.process(job, out)
