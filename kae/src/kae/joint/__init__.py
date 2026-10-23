# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.joint: the loop that integrates placement and routing.

    python -m kae.joint.cli run IN OUT --time S --seed N

1. Place, then route: kae.place, the module stage (kae.route.critical optimize_modules:
   module parts and their critical copper), the Freerouting bridge for the rest, KiCad DRC
   and the routed-physics recheck.
2. Feedback (feedback): unrouted connections become corridors and congestion history,
   DRC errors are attributed to parts and copper, modules whose routed physics shifted are
   flagged; problems are clustered into windows of parts.
3. Local repair (replace, ripup): the parts of one window are re-annealed with the rest
   fixed, under the congestion history (penalty); only the nets touching the window are
   ripped up; the window's modules get their module stage again; the bridge re-routes with
   everything else locked.
4. Accept or revert (scorecard): lexicographic on legality, completion and DRC, then
   routed physics; iterate until nothing improves or the time budget is spent.

The loop logic (loop.JointLoop) talks to the placer and routers only through a stages
object (stages.KaeStages for the real ones), so it is tested with stand-ins.
See docs/topics/architecture/joint-loop.md.
"""
