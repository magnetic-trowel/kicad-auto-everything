# Board sourcing (second pass, 2026-10-21)

Scripts behind the wide open-board corpus. The write-up (method, licence policy, numbers) is
[docs/research/data/board-corpus.md](../../../docs/research/data/board-corpus.md).

**What is here and what is not.** Only the scripts were ported to `main`. These stay on branch
[`claude/compassionate-ramanujan-lo56ee`](https://github.com/magnetic-trowel/kicad-auto-everything/tree/claude/compassionate-ramanujan-lo56ee) (commit `83687ad`):
- the candidate lists (`found/*.jsonl`, `*.rejected.jsonl`), `keep.txt`, `todo*.txt`, `dups.jsonl` and
  the enrich results (about 27 MB in all);
- the reviewed manifests `bench/manifests/wide.jsonl` (13 MB), `wide-noncommercial.jsonl` and
  `wide-duplicates.jsonl`;
- the harness changes the scripts import: Eagle/Altium/Allegro/PADS/CADSTAR import at fetch time and
  the KiCad 10 load repairs in `bench/src/kaebench/{fetch,boardfiles,manifest}.py`, plus
  `bench/scripts/build-corpus.sh`.

So `sig.py`, `enrich.py` and `corpus.py` run only against that branch's `kaebench`
(`kaebench.manifest.import_format` and the archive/import paths of `kaebench.fetch` are not on `main`).

| Step | Script | Output |
|---|---|---|
| Licence + file listing of one repo at HEAD | `probe.py URL [branch]` | JSON |
| Same at a pinned commit (bulk audits) | `atcommit.py URL SHA` | JSON |
| Licence family from licence/README text | `classify.py AUDIT.jsonl` | per-repo flags |
| Pick boards from the audited kicad-happy catalog | `kh_select.py` | `found/kicad-happy.jsonl` |
| Fetch all candidates, fingerprint, drop near-duplicates | `sig.py 'found/*.jsonl' WORKDIR bench/manifests/candidates.jsonl` | `WORKDIR/keep.txt`, `dups.jsonl` |
| Stats + DRC under each board's own rules | `enrich.py 'found/*.jsonl' OUT WORKDIR -j N --skip ... --only keep.txt` | manifest rows |
| Merge host results into the wide manifests | `merge.py WORKDIR 'results/*.jsonl' bench/manifests` | `wide.jsonl`, `wide-noncommercial.jsonl`, `wide-duplicates.jsonl` |

`found/<sector>.jsonl` are the agent-verified candidates (one row per board, licence evidence
quoted); `*.rejected.jsonl` record why repos were left out. `unloadable.rejected.jsonl`
lists boards that KiCad 10 cannot open or import, and why (old binary Eagle, ASCII Altium,
corrupt upstream files); enrich still tries them and they land in its `.failed` output.
`fabacademy-mirror.jsonl` re-sources Fab Academy boards whose repos are on gitlab.fabcloud.org,
whose robots.txt disallows `/*/raw`: each row is a single-file download from the student's
fabacademy.org site (or Software Heritage) pinned by sha256, with `.kicad_pro` in `file_urls`. Only 16 hand-picked
boards are kept (routed, DRC-clean, different assignments); the other 1,144 re-sourced boards are
mostly small repeated assignment boards and are listed in `fabacademy-mirror.rejected.jsonl`.
Do not fetch raw files from gitlab.fabcloud.org. `keep.txt` is the
de-duplicated id list; `todo.txt` the ids still to enrich when this was committed.

## Building the local corpus

`corpus.py` turns the reviewed manifests (`bench/manifests/wide*.jsonl`, built by `merge.py`
from the results files above) plus `candidates.jsonl` into one local folder of boards
(`bench/scripts/build-corpus.sh` on the branch runs it with the committed inputs). The folder layout
and manifest fields are in [board-corpus.md](../../../docs/research/data/board-corpus.md#local-corpus-layout).

## Running enrich on a big host

```bash
bench/scripts/setup.sh --no-freerouting && source bench/.venv/bin/activate
cd tools/research/board-sourcing
python enrich.py 'found/*.jsonl' out/remote.jsonl WORKDIR -j 40 \
  --skip ../../../bench/manifests/candidates.jsonl --only todo.txt --reverse
```

It is resumable (per-board results cache in `WORKDIR/meta`). `--reverse` lets a second
host work the same list from the other end; results merge by id.
