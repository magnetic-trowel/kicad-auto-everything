#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""atcommit.py REPO COMMIT -> JSON with licence files + README licence lines + kicad files at that exact commit."""
import json, os, re, subprocess, sys
S = os.environ.get('KAE_SOURCING_CACHE', os.path.expanduser('~/.cache/kae-sourcing'))
url, sha = sys.argv[1].rstrip('/'), sys.argv[2]
d = os.path.join(S, 'clones_at', re.sub(r'[^A-Za-z0-9]+', '_', url.split('://')[-1]) + '_' + sha[:10])
def g(*a, check=True):
    return subprocess.run(['git', '-C', d, *a], capture_output=True, check=check, timeout=900).stdout.decode('utf-8', 'replace')
if not os.path.isdir(d):
    os.makedirs(d); g('init', '-q'); g('remote', 'add', 'origin', url)
    r = subprocess.run(['git', '-C', d, 'fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin', sha], capture_output=True, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'), timeout=900)
    if r.returncode:
        print(json.dumps({'repo': url, 'commit': sha, 'error': r.stderr.decode()[-300:]})); sys.exit(1)
files = g('ls-tree', '-r', '--name-only', sha).splitlines()
lic = [f for f in files if re.search(r'(^|/)(LICEN[CS]E|COPYING)[^/]*$', f, re.I) and f.count('/') <= 3]
readme = [f for f in files if re.search(r'(^|/)README[^/]*$', f, re.I) and f.count('/') <= 2]
out = {'repo': url, 'commit': sha, 'license_files': {p: g('show', f'{sha}:{p}')[:1200] for p in lic[:6]}, 'readme_license_lines': {},
       'kicad_pcb': [f for f in files if f.endswith('.kicad_pcb')][:50]}
for p in readme[:4]:
    t = g('show', f'{sha}:{p}')[:80000]
    out['readme_license_lines'][p] = [l.strip()[:300] for l in t.splitlines() if re.search(r'licen[cs]|CERN|Creative Commons|CC[- ]BY|non-?commercial|all rights', l, re.I)][:15]
print(json.dumps(out))
