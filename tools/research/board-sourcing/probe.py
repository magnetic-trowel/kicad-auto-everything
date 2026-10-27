#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""probe.py REPO_URL [REF] -> JSON: pinned commit, board/schematic files, licence texts.
Partial clone (blob:none) into $KAE_SOURCING_CACHE/clones; fetches only licence/readme blobs."""
import json, os, re, subprocess, sys, hashlib
S = os.environ.get('KAE_SOURCING_CACHE', os.path.expanduser('~/.cache/kae-sourcing'))
url = sys.argv[1].rstrip('/')
ref = sys.argv[2] if len(sys.argv) > 2 else None
name = re.sub(r'[^A-Za-z0-9]+', '_', url.split('://')[-1])
d = os.path.join(S, 'clones', name)
def git(*a, check=True):
    return subprocess.run(['git', '-C', d, *a], capture_output=True, check=check, timeout=600).stdout.decode('utf-8', 'replace')
env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
if not os.path.isdir(d):
    r = subprocess.run(['git', 'clone', '-q', '--filter=blob:none', '--no-checkout', '--depth', '1'] +
                       (['--branch', ref] if ref else []) + [url, d], capture_output=True, text=True, env=env, timeout=900)
    if r.returncode:
        print(json.dumps({'repo': url, 'error': r.stderr.strip()[-400:]})); sys.exit(1)
commit = git('rev-parse', 'HEAD').strip()
files = git('ls-tree', '-r', '--name-only', 'HEAD').splitlines()
bad = re.compile(r'(-backups/|_autosave|/\.history/|-bak\b|\.bak$|_backup|/backup/|~$)', re.I)
pcb = [f for f in files if f.endswith('.kicad_pcb') and not bad.search(f)]
sch = [f for f in files if f.endswith('.kicad_sch') or (f.endswith('.sch') and not f.endswith('.kicad_sch'))]
eagle_brd = [f for f in files if f.lower().endswith('.brd')]
other = [f for f in files if re.search(r'\.(PcbDoc|SchDoc|PrjPcb|net|cir|dsn|kicad_pro|kicad_dru|easyeda|json)$', f, re.I) and not f.endswith('.json') ]
lic = [f for f in files if re.search(r'(^|/)(LICEN[CS]E|COPYING|LICENSE[-_.]\w+|LICENSES/[^/]+)', f, re.I) and f.count('/') <= 3]
readme = [f for f in files if re.search(r'(^|/)README', f, re.I) and f.count('/') <= 2]
def blob(p, n=4000):
    try: return git('show', f'HEAD:{p}')[:n]
    except Exception as e: return f'<err {e}>'
out = {'repo': url, 'commit': commit, 'kicad_pcb': pcb[:200], 'n_kicad_pcb': len(pcb),
       'schematics': sch[:60], 'eagle_brd': eagle_brd[:60], 'other_cad': other[:40],
       'license_files': {p: blob(p, 1500) for p in lic[:6]},
       'readme_license_lines': {}}
for p in readme[:4]:
    t = blob(p, 60000)
    lines = [l for l in t.splitlines() if re.search(r'licen[cs]|CERN|Creative Commons|CC[- ]BY|copyright|non-?commercial', l, re.I)]
    out['readme_license_lines'][p] = lines[:15]
print(json.dumps(out, indent=1))
