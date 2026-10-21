# Board sourcing (second pass, 2026-10-21)

Scripts and candidate lists behind `bench/manifests/wide*.jsonl`. See
[docs/topics/data/open-board-sources.md](../../../docs/topics/data/open-board-sources.md) for results.

| Step | Script | Output |
|---|---|---|
| Licence + file listing of one repo at HEAD | `probe.py URL [branch]` | JSON |
| Same at a pinned commit (bulk audits) | `atcommit.py URL SHA` | JSON |
| Licence family from licence/README text | `classify.py AUDIT.jsonl` | per-repo flags |
| Pick boards from the audited kicad-happy catalog | `kh_select.py` | `found/kicad-happy.jsonl` |
| Fetch all candidates, fingerprint, drop near-duplicates | `sig.py 'found/*.jsonl' WORKDIR bench/manifests/candidates.jsonl` | `WORKDIR/keep.txt`, `dups.jsonl` |
| Stats + DRC under each board's own rules | `enrich.py 'found/*.jsonl' OUT WORKDIR -j N --skip ... --only keep.txt` | manifest rows |

`found/<sector>.jsonl` are the agent-verified candidates (one row per board, licence evidence
quoted); `*.rejected.jsonl` record why repos were left out. `unloadable.rejected.jsonl`
lists boards that KiCad 10 cannot open or import, and why (old binary Eagle, ASCII Altium,
corrupt upstream files); enrich still tries them and they land in its `.failed` output. `keep.txt` is the
de-duplicated id list; `todo.txt` the ids still to enrich when this was committed.

## Running enrich on a big host

```bash
bench/scripts/setup.sh --no-freerouting && source bench/.venv/bin/activate
cd tools/research/board-sourcing
python enrich.py 'found/*.jsonl' out/remote.jsonl ~/kae-sourcing-work -j 40 \
  --skip ../../../bench/manifests/candidates.jsonl --only todo.txt --reverse
```

It is resumable (per-board results cache in `WORKDIR/meta`). `--reverse` lets a second
host work the same list from the other end; results merge by id.
