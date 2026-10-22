# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Methods under test. An adapter turns a task input board into an output board.

Adapters get a private working copy of the task input and must write
`<workdir>/output/board.kicad_pcb`. They never score themselves: the runner
re-opens the output in a fresh process with the reference rules installed.
"""
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import tools
from .boardfiles import board_path, clamp_dsn_widths, strip_ses_placement


@dataclass
class AdapterResult:
    output: Path | None
    log: str = ""
    meta: dict = field(default_factory=dict)


class Adapter:
    name = "base"
    kinds = ("route", "place")
    needs_reference = False

    def describe(self):
        return dict(name=self.name)

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        raise NotImplementedError


class Reference(Adapter):
    """The human layout: reference copper for route tasks, human placement for place tasks."""
    name = "reference"
    needs_reference = True

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        out = Path(workdir) / "output"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reference[kind], board_path(out))
        return AdapterResult(board_path(out))


class Noop(Adapter):
    """Returns the task input unchanged (lower bound)."""
    name = "noop"

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        out = Path(workdir) / "output"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(board_path(input_dir), board_path(out))
        return AdapterResult(board_path(out))


class Freerouting(Adapter):
    """Freerouting via Specctra DSN/SES with the pitfalls from docs/topics/kicad/specctra-freerouting-integration.md:
    single-threaded optimizer, SES placement block stripped, analytics off, best-of-k via pass schedule.

    By default it also closes two DSN translation gaps seen on real boards: automatic neck-down
    (tracks thinner than the board minimum near pads) is disabled, and the board's copper-to-edge
    and hole clearances are passed as router settings. `stock=True` runs Freerouting as shipped.
    """
    name = "freerouting"
    kinds = ("route",)
    PASS_SCHEDULE = (10, 20, 30, 15, 25, 40, 50, 60)

    def __init__(self, passes=None, extra_args=(), stock=False):
        self.passes = passes
        self.extra_args = list(extra_args)
        self.stock = stock
        if stock:
            self.name = "freerouting-stock"

    def describe(self):
        return dict(name=self.name, cmd=" ".join(tools.freerouting_cmd()), passes=self.passes or
                    list(self.PASS_SCHEDULE), extra_args=self.extra_args, stock=self.stock)

    def _apply_board_rules(self, input_dir, dsn):
        """Router flags for the board's rules, and clamp DSN widths to the board minimum.

        Edge clearance makes Freerouting shrink some tracks to 75% near the edge (seen on
        real boards; `router.neck_width_um` does not prevent it), but on balance it removes
        far more copper-to-edge errors than the track-width errors it adds.
        """
        if self.stock:
            return [], 0
        rules = tools.run_ops("stats", board_path(input_dir)).get("rules", {})
        args = ["--router.automatic_neckdown=false"]
        if rules.get("edge_clearance_mm"):
            args.append(f"--router.copper_to_edge_clearance_um={round(rules['edge_clearance_mm'] * 1000)}")
        if rules.get("hole_clearance_mm"):
            args.append(f"--router.hole_clearance_um={round(rules['hole_clearance_mm'] * 1000)}")
        raised = clamp_dsn_widths(dsn, rules["min_track_width_mm"]) if rules.get("min_track_width_mm") else 0
        return args, raised

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        if kind != "route":
            raise ValueError("freerouting only routes")
        w = Path(workdir).resolve()  # Freerouting runs with cwd=w, so its paths must be absolute
        out = w / "output"
        out.mkdir(parents=True, exist_ok=True)
        dsn, ses, ses2 = w / "board.dsn", w / "board.ses", w / "board_noplace.ses"
        t0 = time.monotonic()
        tools.run_ops("export-dsn", board_path(input_dir), dsn)
        passes = self.passes or self.PASS_SCHEDULE[attempt % len(self.PASS_SCHEDULE)]
        rule_args, widths_raised = self._apply_board_rules(input_dir, dsn)
        cmd = [*tools.freerouting_cmd(), "-de", str(dsn), "-do", str(ses), "-mp", str(passes),
               "-mt", "1", "--gui.enabled=false", "-da", *rule_args, *self.extra_args]
        remaining = max(10.0, timeout - (time.monotonic() - t0))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=remaining, cwd=w)
            log = r.stdout[-20000:] + r.stderr[-5000:]
        except subprocess.TimeoutExpired as e:
            log = f"freerouting timed out after {remaining:.0f}s\n{(e.stdout or b'')[-5000:]!r}"
            return AdapterResult(None, log, dict(passes=passes, timed_out=True))
        if not ses.exists():
            return AdapterResult(None, log, dict(passes=passes, rc=r.returncode))
        stripped = strip_ses_placement(ses, ses2)
        tools.run_ops("import-ses", board_path(input_dir), ses2, board_path(out))
        return AdapterResult(board_path(out), log, dict(passes=passes, rc=r.returncode, rule_args=rule_args,
                                                        dsn_widths_raised=widths_raised,
                                                        ses_placement_stripped=stripped))


class Command(Adapter):
    """Any external tool: a command template run in the work directory.

    Placeholders: {input} {output} {workdir} {kind} {attempt} {timeout}. The tool
    reads {input} (a .kicad_pcb with its project files beside it) and writes {output}.
    """
    name = "command"

    def __init__(self, template, name=None, kinds=("route", "place")):
        self.template = template
        if name:
            self.name = name
        self.kinds = tuple(kinds)

    def describe(self):
        return dict(name=self.name, template=self.template, kinds=list(self.kinds))

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        # The command runs with cwd=w, so every path it is given must be absolute.
        w, input_dir = Path(workdir).resolve(), Path(input_dir).resolve()
        out = w / "output"
        out.mkdir(parents=True, exist_ok=True)
        cmd = self.template.format(input=shlex.quote(str(board_path(input_dir))),
                                   output=shlex.quote(str(board_path(out))),
                                   workdir=shlex.quote(str(w)), kind=kind, attempt=attempt,
                                   timeout=int(timeout))
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=w)
            log = r.stdout[-20000:] + r.stderr[-5000:]
        except subprocess.TimeoutExpired:
            return AdapterResult(None, f"timed out after {timeout}s", dict(timed_out=True))
        ok = board_path(out).exists()
        return AdapterResult(board_path(out) if ok else None, log, dict(rc=r.returncode))


def make(name, command=None, passes=None):
    if name == "reference":
        return Reference()
    if name == "noop":
        return Noop()
    if name == "freerouting":
        return Freerouting(passes=passes)
    if name == "freerouting-stock":
        return Freerouting(passes=passes, stock=True)
    if command:
        return Command(command, name=name)
    raise ValueError(f"unknown adapter {name!r} (built-ins: reference, noop, freerouting; "
                     "or pass --command for an external tool)")
