# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Methods under test. An adapter turns a task input board into an output board.

Adapters get a private working copy of the task input and must write
`<workdir>/output/board.kicad_pcb`. They never score themselves: the runner
re-opens the output in a fresh process with the reference rules installed.

External tools (`--command`) run in a sandbox (bubblewrap) by default: no network, a
private /tmp, and a home directory that shows only the kaebench tool cache, the current
directory and paths passed with --sandbox-ro. The kaebench workdir (tasks, references,
other results) and any KAE_SANDBOX_HIDE paths are hidden; only the attempt's own work
directory is writable. A method therefore cannot read the human layout it is scored
against, download it, or touch other attempts.
"""
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import tools
from .boardfiles import (board_path, clamp_dsn_widths, copy_board, fix_dsn_unsized_vias, quote_ses_net_names,
                         strip_ses_placement, unblock_all_power_dsn)


@dataclass
class Sandbox:
    """bubblewrap jail for an untrusted method. `hide` paths are replaced by empty dirs;
    `ro` paths stay readable even inside the hidden home directory."""
    enabled: bool = True
    network: bool = False
    ro: list = field(default_factory=list)
    hide: list = field(default_factory=list)

    def describe(self):
        return dict(enabled=self.enabled, network=self.network, ro=[str(p) for p in self.ro],
                    hide=[str(p) for p in self._hidden()])

    def _hidden(self):
        extra = [p for p in os.environ.get("KAE_SANDBOX_HIDE", "").split(os.pathsep) if p]
        return [Path(p).resolve() for p in [*self.hide, *extra]]

    def _readable(self):
        paths = [tools.KAE_HOME, *self.ro]
        cwd = Path.cwd().resolve()
        if Path.home().resolve() in cwd.parents:
            paths.append(cwd)  # e.g. the repo checkout holding the method's code
        return [Path(p).resolve() for p in paths if Path(p).exists()]

    def wrap(self, argv, workdir):
        if not self.enabled:
            return list(argv)
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise tools.ToolError("bubblewrap (bwrap) not found; install it, or pass --no-sandbox "
                                  "(results are then marked unsandboxed)")
        home, work = Path.home().resolve(), Path(workdir).resolve()
        cmd = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
               "--tmpfs", "/tmp", "--tmpfs", "/var/tmp", "--tmpfs", str(home)]
        for p in self._readable():
            cmd += ["--ro-bind", str(p), str(p)]
        for p in self._hidden():
            if p.exists():
                cmd += ["--tmpfs", str(p)]
        cmd += ["--bind", str(work), str(work), "--chdir", str(work),
                "--unshare-pid", "--unshare-ipc", "--die-with-parent", "--new-session"]
        if not self.network:
            cmd.append("--unshare-net")
        return cmd + list(argv)


@dataclass
class AdapterResult:
    output: Path | None
    log: str = ""
    meta: dict = field(default_factory=dict)


class Adapter:
    name = "base"
    kinds = ("route", "place", "joint")
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

    By default it also closes DSN translation gaps seen on real boards: automatic neck-down
    (tracks thinner than the board minimum near pads) is disabled, the board's copper-to-edge
    and hole clearances are passed as router settings, track widths below the board minimum
    (or unset) and unsized vias get the board minimum, and a board whose copper layers are all
    KiCad "power" layers gets them as signal layers. `stock=True` runs Freerouting as shipped.
    """
    name = "freerouting"
    kinds = ("route",)
    PASS_SCHEDULE = (10, 20, 30, 15, 25, 40, 50, 60)

    def __init__(self, passes=None, extra_args=(), stock=False, binary=None):
        self.passes = passes
        self.extra_args = list(extra_args)
        self.stock = stock
        self.binary = binary
        if stock:
            self.name = "freerouting-stock"

    def cmd(self):
        if not self.binary:
            return tools.freerouting_cmd()
        return ["java", "-jar", str(self.binary)] if str(self.binary).endswith(".jar") else [str(self.binary)]

    def describe(self):
        return dict(name=self.name, cmd=" ".join(self.cmd()), passes=self.passes or
                    list(self.PASS_SCHEDULE), extra_args=self.extra_args, stock=self.stock)

    def _apply_board_rules(self, input_dir, dsn):
        """Router flags for the board's rules, and clamp DSN widths to the board minimum.

        Edge clearance makes Freerouting shrink some tracks to 75% near the edge (seen on
        real boards; `router.neck_width_um` does not prevent it), but on balance it removes
        far more copper-to-edge errors than the track-width errors it adds.
        """
        if self.stock:
            return [], {}
        rules = tools.run_ops("stats", board_path(input_dir)).get("rules", {})
        args = ["--router.automatic_neckdown=false"]
        if rules.get("edge_clearance_mm"):
            args.append(f"--router.copper_to_edge_clearance_um={round(rules['edge_clearance_mm'] * 1000)}")
        if rules.get("hole_clearance_mm"):
            args.append(f"--router.hole_clearance_um={round(rules['hole_clearance_mm'] * 1000)}")
        raised = clamp_dsn_widths(dsn, rules["min_track_width_mm"]) if rules.get("min_track_width_mm") else 0
        sized = fix_dsn_unsized_vias(dsn, rules.get("min_via_diameter_mm"), rules.get("min_through_drill_mm"))
        return args, dict(dsn_widths_raised=raised, dsn_vias_sized=sized,
                          dsn_power_layers_unblocked=unblock_all_power_dsn(dsn))

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        if kind != "route":
            raise ValueError("freerouting only routes")
        w = Path(workdir)
        out = w / "output"
        out.mkdir(parents=True, exist_ok=True)
        dsn, ses, ses2 = w / "board.dsn", w / "board.ses", w / "board_noplace.ses"
        t0 = time.monotonic()
        tools.run_ops("export-dsn", board_path(input_dir), dsn)
        passes = self.passes or self.PASS_SCHEDULE[attempt % len(self.PASS_SCHEDULE)]
        rule_args, dsn_fixes = self._apply_board_rules(input_dir, dsn)
        result = w / "result.json"
        remaining = max(10.0, timeout - (time.monotonic() - t0))
        # Freerouting's own deadline, inside ours: it then stops between items and still writes
        # what it has routed (it overran by 20-40 s in tests), so a board that runs out of time
        # is scored on its partial routing instead of returning nothing.
        job_s = int(max(10.0, remaining - max(120.0, 0.1 * remaining)))
        # A private settings/log directory per attempt, and no FREEROUTING__* overrides: otherwise
        # every run shares ~/.config/freerouting/freerouting.json (rewritten by whichever version
        # ran last) and any environment settings of the host.
        user_data = w / "freerouting-user"
        user_data.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("FREEROUTING__")}
        cmd = [*self.cmd(), "-de", str(dsn), "-do", str(ses), "-mp", str(passes),
               "-mt", "1", "--gui.enabled=false", "-da", f"--user_data_path={user_data}",
               f"--router.result_json={result}",
               f"--router.job_timeout={job_s // 3600:02d}:{job_s % 3600 // 60:02d}:{job_s % 60:02d}",
               *rule_args, *self.extra_args]
        # kept with the attempt: the exchange with the router and its own report
        artifacts = [dsn, ses, result]
        try:
            r = tools.run_measured(cmd, timeout=remaining, cwd=w, env=env)
            log = r.stdout + r.stderr
        except subprocess.TimeoutExpired as e:
            log = f"freerouting timed out after {remaining:.0f}s\n{e.stdout or ''}{e.stderr or ''}"
            return AdapterResult(None, log, dict(passes=passes, timed_out=True, job_timeout_s=job_s,
                                                 artifacts=artifacts))
        own = _router_report(result)
        partial = bool(own and own.get("final_state") == "TIMED_OUT")
        # A router that crashes can still leave an empty session file behind (Freerouting
        # 2.5.0 opens it before writing); that is no output, not a failed import.
        ses_empty = ses.exists() and ses.stat().st_size == 0
        if not ses.exists() or ses_empty:
            return AdapterResult(None, log, dict(passes=passes, rc=r.returncode, router_report=own,
                                                 job_timeout_s=job_s, partial=partial, **dsn_fixes,
                                                 ses_empty=ses_empty, artifacts=artifacts))
        stripped = strip_ses_placement(ses, ses2)
        quoted = quote_ses_net_names(ses2)
        meta = dict(passes=passes, rc=r.returncode, rule_args=rule_args, **dsn_fixes,
                    ses_placement_stripped=stripped, ses_nets_quoted=quoted, router_report=own,
                    job_timeout_s=job_s, partial=partial, artifacts=artifacts)
        try:
            tools.run_ops("import-ses", board_path(input_dir), ses2, board_path(out))
        except tools.ToolError as e:
            # still an adapter error, but keep the router's log and files for diagnosis
            e.adapter_log, e.adapter_meta = log, dict(meta, artifacts=[*artifacts, ses2])
            raise
        return AdapterResult(board_path(out), log, meta)


class HumanFreerouting(Freerouting):
    """Joint baseline: the human placement routed by Freerouting (its kinds: joint only)."""
    name = "human-freerouting"
    kinds = ("joint",)
    needs_reference = True

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        human = Path(workdir) / "human-placement"
        copy_board(Path(reference["joint_placement"]).parent, human)
        return super().run("route", human, workdir, attempt, timeout)


def _router_report(path):
    """Freerouting's own view of its result (--router.result_json): kept as a diagnostic next
    to the score, never as the score (only kicad-cli on the rebuilt board counts)."""
    try:
        d = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    use = d.get("resource_usage") or {}
    return dict(app_version=d.get("app_version"), final_state=d.get("final_state"),
                router_score=d.get("normalized_score"), optimizer_score=d.get("optimizer_score"),
                cpu_time_s=use.get("cpu_time"), peak_memory_mb=use.get("peak_memory"))


class Command(Adapter):
    """Any external tool: a command template run in the work directory, sandboxed.

    Placeholders: {input} {output} {workdir} {kind} {attempt} {timeout}. The tool
    reads {input} (a .kicad_pcb with its project files beside it) and writes {output}.
    """
    name = "command"

    def __init__(self, template, name=None, kinds=("route", "place", "joint"), sandbox=None):
        self.template = template
        if name:
            self.name = name
        self.kinds = tuple(kinds)
        self.sandbox = sandbox or Sandbox()

    def describe(self):
        return dict(name=self.name, template=self.template, kinds=list(self.kinds),
                    sandbox=self.sandbox.describe())

    def hide(self, *paths):
        """Hide these paths from the method (the runner passes its tasks and results dirs)."""
        self.sandbox.hide.extend(Path(p) for p in paths)

    def run(self, kind, input_dir, workdir, attempt, timeout, reference=None):
        w = Path(workdir)
        out = w / "output"
        out.mkdir(parents=True, exist_ok=True)
        cmd = self.template.format(input=shlex.quote(str(board_path(input_dir))),
                                   output=shlex.quote(str(board_path(out))),
                                   workdir=shlex.quote(str(w)), kind=kind, attempt=attempt,
                                   timeout=int(timeout))
        argv = self.sandbox.wrap(["sh", "-c", cmd], w)
        try:
            r = tools.run_measured(argv, timeout=timeout, cwd=w)
            log = r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return AdapterResult(None, f"timed out after {timeout}s", dict(timed_out=True))
        ok = board_path(out).exists()
        return AdapterResult(board_path(out) if ok else None, log,
                             dict(rc=r.returncode, sandboxed=self.sandbox.enabled))


def make(name, command=None, passes=None, sandbox=None, freerouting=None):
    if name == "reference":
        return Reference()
    if name == "noop":
        return Noop()
    if name == "freerouting":
        return Freerouting(passes=passes, binary=freerouting)
    if name == "human-freerouting":
        return HumanFreerouting(passes=passes, binary=freerouting)
    if name == "freerouting-stock":
        return Freerouting(passes=passes, stock=True, binary=freerouting)
    if command:
        return Command(command, name=name, sandbox=sandbox)
    raise ValueError(f"unknown adapter {name!r} (built-ins: reference, noop, freerouting; "
                     "or pass --command for an external tool)")
