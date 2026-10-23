# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The real stages of the joint loop: kae.place, the module stage, the bridge, KiCad DRC and
the routed-physics recheck, behind the interface loop.JointLoop drives.

A `Layout` is one candidate solution on disk: a work board (the input with the placed poses
and all routing, critical copper locked, no guard zones) and the bookkeeping the next
iteration needs (which copper is critical and which module owns it, each module's guard
pours and module-stage values). Work boards live in the loop's work directory, each with
the input's project files beside it (KiCad's refill and DRC read the rules from them).

Stage by stage:
- place: kae.place.pipeline.place on the input, written with kae.place.writer.
- modules: kae.route.critical_joint.optimize_modules (module parts and critical copper
  together), optionally limited to `modules` with the parts outside the window locked;
  guards per module from Session.guards; critical.write_joint writes poses and copper.
- route: every routing item locked, guards added, the bridge routes the rest; afterwards
  everything but the critical copper is unlocked again and the guards dropped.
- evaluate: kicad-cli DRC (zones refilled, as kaebench) and critical_recheck.recheck against
  the module-stage values (the critical copper alone).
- repair: replace.replace_window, ripup.plan_ripup, then modules and route on the result.
- finish: OUTPUT = the input with the final poses (kae.place.writer) plus the final routing
  (critical_write.transplant), so nothing else of the input changes.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .feedback import PartGeom
from .scorecard import PLACEMENT_TYPES, Scorecard


def _log(msg):
    print(f"[kae.joint {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


@dataclass
class Layout:
    board: str                                      # routed work board
    poses: dict = field(default_factory=dict)       # every footprint: uuid -> (x, y, rot, side)
    crit: set = field(default_factory=set)          # critical (locked) copper uuids
    owners: dict = field(default_factory=dict)      # critical copper uuid -> module id
    guards: dict = field(default_factory=dict)      # module id -> [guard zone tuples]
    status: dict = field(default_factory=dict)      # module id -> module-stage status
    stage: dict = field(default_factory=dict)       # module id -> {u, plane_cover} (critical copper alone)
    info: dict = field(default_factory=dict)        # stage reports


def _project(src_board, dst_board):
    """Copy the project files of src_board beside dst_board (same stem)."""
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = Path(src_board).with_suffix(ext)
        t = Path(dst_board).with_suffix(ext)
        if s.exists() and s.resolve() != t.resolve():
            shutil.copy2(s, t)


class KaeStages:
    """The real stages (see the module docstring). `opts` keys: module_time, route_share,
    place_share, cong_mult, history_scale, bump_mm, margin, big_pads, max_cross, phys."""

    def __init__(self, input_path, workdir, opts=None, log=_log):
        self.input = Path(input_path).resolve()
        self.wd = Path(workdir)
        self.wd.mkdir(parents=True, exist_ok=True)
        self.opts = dict(opts or {})
        self.log = log
        self.brief = None
        self.terms = None
        self.locked = set()
        self.module_parts = {}
        self.edge_parts = set()

    # ------------------------------------------------------------------ helpers
    def _path(self, it, name):
        d = self.wd / f"it{it:02d}"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{name}.kicad_pcb"

    def _load(self, path):
        from kae.board.kicad_file import load
        return load(path)

    def _all_poses(self, board):
        return {fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in board.footprints}

    def _write_poses(self, src, dst, poses):
        from kae.place.writer import write
        write(str(src), str(dst), poses, mode=self.opts.get("writer", "auto"), log=None)
        _project(self.input, dst)
        return dst

    # ------------------------------------------------------------------ place
    def place(self, seed, time_s):
        from kae.place.pipeline import place
        t0 = time.monotonic()
        board = self._load(self.input)
        self.locked = {fp.uuid for fp in board.footprints if fp.locked}
        self.edge_parts = {fp.uuid for fp in board.footprints if fp.edge_cuts}
        res = place(board, seed=seed, time_s=time_s, physics=not self.opts.get("no_physics"), workers=1,
                    log=lambda m: self.log(f"place: {m}"), edge_mate=bool(self.opts.get("edge_mate")))
        out = self._path(0, "placed")
        if res.poses:
            self._write_poses(self.input, out, res.poses)
        else:
            shutil.copy2(self.input, out)
            _project(self.input, out)
        rep = res.report
        legal = bool(rep.get("legal_grid") and not rep.get("exact") and not rep.get("outline_incomplete"))
        b = self._load(out)
        info = dict(place=dict(seconds=round(time.monotonic() - t0, 1), legal=legal, hpwl=rep.get("hpwl"),
                               scorecard=(rep.get("scorecard") or {}).get("total"), budget_s=rep.get("budget_s")))
        return Layout(board=str(out), poses=self._all_poses(b), info=info)

    def layout_from(self, board_path):
        """A Layout from a placed board (no loop placement: e.g. the human placement)."""
        out = self._path(0, "placed")
        shutil.copy2(board_path, out)
        _project(self.input, out)
        b = self._load(out)
        self.locked = {fp.uuid for fp in b.footprints if fp.locked}
        self.edge_parts = {fp.uuid for fp in b.footprints if fp.edge_cuts}
        return Layout(board=str(out), poses=self._all_poses(b))

    def _ensure_brief(self, board):
        if self.brief is None:
            try:
                from kae.circuit.brief import build
                self.brief = build(board)
            except Exception as e:  # noqa: BLE001 - routing still runs without modules
                self.log(f"brief failed ({type(e).__name__}: {e})")
                self.brief = {"structures": [], "nets": {}, "parts": {}}
            from kae.route.critical_modules import modules_from_brief
            self.module_parts = {m.id: list(m.parts) for m in modules_from_brief(self.brief)}
            try:
                from kae.place.stubs import make_terms
                self.terms, _ = make_terms(board, self.brief)
            except Exception as e:  # noqa: BLE001
                self.log(f"place terms failed ({type(e).__name__}: {e})")
                self.terms = None
        return self.brief

    # ------------------------------------------------------------------ module stage
    def modules(self, lay, it, only=None, window_parts=None, time_s=None):
        """Module stage on lay.board (all modules, or `only` with the parts outside
        `window_parts` locked). Returns a new Layout (routing as before plus new copper)."""
        from kae.route.critical import Session, write_joint
        from kae.route.critical_joint import optimize_modules
        t0 = time.monotonic()
        board = self._load(lay.board)
        brief = self._ensure_brief(board)
        out = self._path(it, "modules")
        new = Layout(board=str(out), poses=dict(lay.poses), crit=set(lay.crit), owners=dict(lay.owners),
                     guards=dict(lay.guards), status=dict(lay.status), stage=dict(lay.stage), info=dict(lay.info))
        if only is not None and not only:
            shutil.copy2(lay.board, out)
            _project(self.input, out)
            new.info["modules"] = dict(skipped="no module in the window")
            return new
        locked = set(self.locked)
        if window_parts is not None:
            locked |= {fp.uuid for fp in board.footprints if fp.uuid not in set(window_parts)}
        t_mod = time_s if time_s is not None else float(self.opts.get("module_time", 90.0))
        try:
            sess = Session(lay.board, brief=brief, opts=dict(rails="none"), log=lambda m: None, board=board,
                           terms=self.terms)
            moved, copper, rep = optimize_modules(board, brief, terms=self.terms, locked=sorted(locked),
                                                  log=lambda m: self.log(f"modules: {m}"), time_s=t_mod, session=sess,
                                                  rails=only is None, modules=None if only is None else list(only))
        except Exception as e:  # noqa: BLE001 - the bridge still routes everything
            import traceback
            traceback.print_exc(file=sys.stderr)
            self.log(f"module stage failed: {type(e).__name__}: {e}")
            shutil.copy2(lay.board, out)
            _project(self.input, out)
            new.info["modules"] = dict(error=f"{type(e).__name__}: {e}")
            return new
        owners = {}
        for item in sess.space.routed:
            if item.uuid and item.owner:
                owners[item.uuid] = str(item.owner[0])
        guards = {}
        mods = list(sess.modules)
        try:
            for m in mods:
                sess.modules = [m]
                g = sess.guards()
                if g:
                    guards[m.id] = g
        finally:
            sess.modules = mods
        write_joint(lay.board, out, moved, copper)
        _project(self.input, out)
        new.poses.update({u: tuple(p) for u, p in moved.items()})
        new.crit |= {c.uuid for c in copper}
        new.owners.update(owners)
        for m in mods:
            new.status[m.id] = m.status
            new.guards.pop(m.id, None)
        new.guards.update(guards)
        new.stage = self._stage_values(out, it)
        new.info["modules"] = dict(seconds=round(time.monotonic() - t0, 1), moved=sorted(rep.get("moved") or {}),
                                   copper=len(copper), modules=[dict(id=m["id"], u0=m.get("u0"), u=m.get("u"),
                                                                     status=m.get("status"))
                                                                for m in rep.get("modules") or []])
        return new

    def _stage_values(self, board_with_crit, it):
        """{module id: {u, plane_cover}} on the critical copper alone."""
        from kae.route.critical_recheck import locked_only, stage_values
        lo = self._path(it, "crit_only")
        try:
            locked_only(board_with_crit, lo)
            _project(self.input, lo)
            return stage_values(lo, self.brief, terms=self.terms)
        except Exception as e:  # noqa: BLE001 - without stage values there is no recheck flag
            self.log(f"stage values failed: {type(e).__name__}: {e}")
            return {}

    # ------------------------------------------------------------------ route
    def route(self, lay, it, seed, time_s):
        """The bridge around everything already on lay.board (locked) and the guards."""
        from kae.route import bridge as BR
        from kae.route import critical_write as W
        from kae.route.critical_recheck import merge_guards
        t0 = time.monotonic()
        locked = self._path(it, "route_in")
        W.edit(lay.board, locked, lock="all", drop_guards=True)
        guards = merge_guards([g for _, gs in sorted(lay.guards.items()) for g in gs])
        if guards:
            W.append_items(locked, locked, zones=guards)
        _project(self.input, locked)
        raw = self._path(it, "route_raw")
        rep = BR.route(locked, raw, seed=seed, time_s=time_s, workdir=self.wd / f"it{it:02d}" / "bridge",
                       opts=dict(keep=bool(self.opts.get("keep"))), log=lambda m: self.log(f"bridge: {m}"))
        out = self._path(it, "routed")
        src = raw if raw.exists() else locked
        allr = W.routing(src)
        W.edit(src, out, unlock=[r["uuid"] for r in allr if r["locked"] and r["uuid"] not in lay.crit],
               drop_guards=True)
        _project(self.input, out)
        new = Layout(board=str(out), poses=dict(lay.poses), crit=set(lay.crit), owners=dict(lay.owners),
                     guards=dict(lay.guards), status=dict(lay.status), stage=dict(lay.stage), info=dict(lay.info))
        fin = ((rep.get("repair") or {}).get("final") or rep.get("drc") or {})
        new.info["route"] = dict(seconds=round(time.monotonic() - t0, 1), status=rep.get("status"), guards=len(guards),
                                 router_s=(rep.get("router") or {}).get("seconds"),
                                 errors=fin.get("errors"), unconnected=fin.get("unconnected"))
        return new

    # ------------------------------------------------------------------ evaluate
    def evaluate(self, lay, it):
        """(Scorecard, feedback dict(drc=report, recheck=result))."""
        from kae.route import drc as D
        from kae.route.critical_recheck import recheck
        t0 = time.monotonic()
        d = self.wd / f"it{it:02d}" / "drc"
        staged = D.stage_board(lay.board, self.input, d)
        try:
            rep = D.run(staged, d / "drc.json", timeout=int(self.opts.get("drc_timeout", 600)))
        except D.DrcError as e:
            self.log(f"DRC failed: {e}")
            rep = {"violations": [], "unconnected_items": [], "error": str(e)}
        s = D.summary(rep)
        card = Scorecard(unconnected=s["unconnected"], errors=s["errors"], errors_by_type=s["by_type"])
        card.placement_errors = placement_errors(rep)
        if rep.get("error"):
            card.unconnected, card.errors, card.note = 10 ** 6, 10 ** 6, "drc failed"
        rc = {}
        brief = self.brief
        if brief is None:
            brief = self._ensure_brief(self._load(lay.board))
        stage = {k: v for k, v in lay.stage.items() if lay.status.get(k) in ("routed", "partial")}
        if stage:
            try:
                rc = recheck(lay.board, brief, stage, terms=self.terms)
            except Exception as e:  # noqa: BLE001
                self.log(f"recheck failed: {type(e).__name__}: {e}")
                rc = {}
        card.modules = {k: (v or {}).get("u_routed") for k, v in (rc.get("modules") or {}).items()}
        card.flagged = sorted(rc.get("retweak") or [])
        rails = rc.get("rails") or {}
        worst = [v for res in rails.values() if isinstance(res, dict) for v in res.values()
                 if isinstance(v, (int, float))]
        card.worst_rail_mohm = round(max(worst), 3) if worst else None
        if self.terms is not None:
            try:
                card.place_terms = float(self.terms.total(dict(lay.poses)))
            except Exception as e:  # noqa: BLE001
                self.log(f"place terms total failed: {type(e).__name__}: {e}")
        lay.info["evaluate_s"] = round(time.monotonic() - t0, 1)
        return card, dict(drc=rep, recheck=rc)

    # ------------------------------------------------------------------ geometry for windows
    def geometry(self, lay):
        """(parts {uuid: PartGeom}, board bounds, part centres, refs) of a layout."""
        from kae.board import transform
        b = self._load(lay.board)
        parts = {}
        for fp in b.footprints:
            box = None
            try:
                cy = transform.courtyard(fp)
                if cy is not None and not cy.is_empty:
                    box = cy.bounds
            except Exception:  # noqa: BLE001 - fall back to the pads
                box = None
            if box is None:
                xy = [transform.pad_xy(fp, p) for p in fp.pads] or [(fp.x, fp.y)]
                box = (min(x for x, _ in xy) - 0.5, min(y for _, y in xy) - 0.5,
                       max(x for x, _ in xy) + 0.5, max(y for _, y in xy) + 0.5)
            parts[fp.uuid] = PartGeom(uuid=fp.uuid, ref=fp.ref, bbox=tuple(box), side=fp.side,
                                      locked=bool(fp.locked or fp.uuid in self.locked or fp.uuid in self.edge_parts
                                                  or not fp.on_board))
        if b.outline:
            xs = [p.bounds for p in b.outline]
            bounds = (min(r[0] for r in xs), min(r[1] for r in xs), max(r[2] for r in xs), max(r[3] for r in xs))
        else:
            bxs = [g.bbox for g in parts.values()]
            bounds = (min(r[0] for r in bxs), min(r[1] for r in bxs), max(r[2] for r in bxs), max(r[3] for r in bxs))
        centres = {u: g.center for u, g in parts.items()}
        refs = {u: g.ref for u, g in parts.items()}
        return parts, bounds, centres, refs

    # ------------------------------------------------------------------ local repair
    def repair(self, lay, window, history, it, seed, time_s, bump_refs=(), attempt=0):
        """Re-place the window, rip up what it invalidates, redo its modules, re-route.
        Returns (Layout or None, report)."""
        from kae.route import critical_write as W

        from .replace import replace_window
        from .ripup import plan_ripup
        t0 = time.monotonic()
        o = self.opts
        board = self._load(lay.board)
        self._ensure_brief(board)
        rep = dict(attempt=attempt)
        res = replace_window(board, window, self.brief, history=history, seed=seed,
                             time_s=min(float(o.get("replace_time", 25.0)), max(5.0, 0.2 * time_s)),
                             cong_mult=float(o.get("cong_mult", 2.0)) * (1.5 ** attempt),
                             history_scale=float(o.get("history_scale", 1.0)), bump_mm=float(o.get("bump_mm", 0.25)),
                             bump_refs=bump_refs, margin=float(o.get("margin", 0.3)),
                             physics=not o.get("no_physics"), log=lambda m: self.log(f"replace: {m}"))
        rep["replace"] = {k: v for k, v in res.report.items() if k not in ("window",)}
        if not res.poses:
            rep["outcome"] = res.report.get("rejected") or res.report.get("skipped") or "no part moved"
            return None, rep
        plan = plan_ripup(board, window, set(res.poses), lay.owners, self.module_parts,
                          big_pads=int(o.get("big_pads", 20)), max_cross=int(o.get("max_cross", 4)))
        rep["ripup"] = plan.to_dict()
        ripped = self._path(it, "ripped")
        W.edit(lay.board, ripped, remove=plan.remove)
        _project(self.input, ripped)
        placed = self._path(it, "replaced")
        self._write_poses(ripped, placed, res.poses)
        removed = set(plan.remove)
        mid = Layout(board=str(placed), poses=dict(lay.poses), crit=set(lay.crit) - removed,
                     owners={u: m for u, m in lay.owners.items() if u not in removed},
                     guards={m: g for m, g in lay.guards.items() if m not in set(plan.redo)},
                     status=dict(lay.status), stage=dict(lay.stage), info={})
        mid.poses.update({u: tuple(p) for u, p in res.poses.items()})
        left = time_s - (time.monotonic() - t0)
        redo = [] if o.get("no_modules") else plan.redo
        mod = self.modules(mid, it, only=redo, window_parts=window.parts,
                           time_s=min(float(o.get("module_time", 90.0)), max(5.0, 0.15 * left)))
        rep["modules"] = mod.info.get("modules")
        left = time_s - (time.monotonic() - t0)
        routed = self.route(mod, it, seed=seed, time_s=max(30.0, left))
        rep["route"] = routed.info.get("route")
        rep["seconds"] = round(time.monotonic() - t0, 1)
        return routed, rep

    # ------------------------------------------------------------------ output
    def finish(self, lay, output):
        """OUTPUT = input + final poses + final routing (nothing else changes)."""
        from kae.route import critical_write as W
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        base = {fp.uuid: fp for fp in self._load(self.input).footprints}
        moved = {}
        for u, p in lay.poses.items():
            fp = base.get(u)
            if fp is None or fp.locked:
                continue
            if math.dist((fp.x, fp.y), p[:2]) > 1e-6 or abs(((fp.rot - p[2]) + 180) % 360 - 180) > 1e-6:
                moved[u] = p
        tmp = self.wd / "final_placed.kicad_pcb"
        if moved:
            self._write_poses(self.input, tmp, moved)
        else:
            shutil.copy2(self.input, tmp)
        W.transplant(lay.board, tmp, output)
        return dict(moved=len(moved), output=str(output))


def placement_errors(drc_report):
    """KiCad placement-type errors that involve no routing item (pads and footprints only):
    the placement's, not the router's."""
    from .feedback import parse_item
    n = 0
    for v in drc_report.get("violations") or []:
        if v.get("severity") != "error" or v.get("type") not in PLACEMENT_TYPES:
            continue
        kinds = {parse_item(x)["kind"] for x in v.get("items") or []}
        if kinds and kinds <= {"pad", "footprint", "other"}:
            n += 1
    return n


def dump(obj, path):
    Path(path).write_text(json.dumps(obj, indent=1, default=str))
