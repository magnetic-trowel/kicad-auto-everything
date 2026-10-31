---
name: kaeq
description: Run long tests, benchmarks or batch jobs on the shared remote machine through the kaeq queue instead of running them directly. Use whenever a command will take >1 minute, use many cores, or lots of RAM.
---
<!-- SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# kaeq job queue

Never run heavy jobs directly on the shared host; queue them. The daemon starts jobs
when CPU/RAM beyond a reserve for other users is free, at idle CPU priority.
Once per session: `export KAEQ_OWNER=<short-unique-session-label>` (e.g. `router-v3`).
If this session is not on the host: `export KAEQ_SSH=<host>` (commands run there; paths are host paths).

```bash
kaeq submit --cpus 4 --mem 12G --timeout 30m --name t1 --tag router-v3 -- pytest -x tests/foo   # one job
kaeq submit --batch cmds.txt --cpus 2 --mem 6G --tag sweep                                        # one command per line
kaeq wait                      # run with run_in_background: returns on the first failure batch, or when all done
kaeq status                    # a few lines: resources, your counts, running + problems
kaeq result 42                 # error lines + log tail of one job
kaeq retry 42 [--mem 20G]      # after fixing the code (same cmd/cwd); bare `kaeq retry` = all your failures
kaeq cancel --tag sweep
```

Code is frozen at submit time: inside a git repo the job runs a snapshot (HEAD + uncommitted + untracked, ignored files excluded) in a private worktree,
so switching branches or editing afterwards does not affect queued jobs. Needs git-ignored inputs (data, venv)? `--link kae-work --link .venv`.
`--live` runs in the directory as-is. `kaeq retry` re-snapshots from the original directory, so fixes are picked up.
Default owner is `repo@branch`; failures print `repo@branch:sha`.

Workflow: submit -> start `kaeq wait` in the background -> keep working. When it exits
(1 = problems printed, 0 = all done, 2 = timeout: just call it again), fix what it
reports, `kaeq retry`, and start `kaeq wait` again. Estimate `--cpus`/`--mem` honestly:
a job whose RSS exceeds 1.5x `--mem` is killed and auto-requeued with a corrected value.
Do not use `--retries` for deterministic test failures. Details: `tools/kaeq/README.md`.
