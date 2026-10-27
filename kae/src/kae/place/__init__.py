# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-first placement: problem model, clusters, seed, annealer, legalizer, writer.

    from kae.place.pipeline import place
    result = place(board, seed=0, time_s=120, physics=True)

See kae/src/kae/place/pipeline.py for the stages and docs/topics/placement/ for the plan.
"""
