import os, pathlib
import json,sys
S=os.path.expandvars('$KAE_AB_SCRATCH/')
E=str(pathlib.Path(__file__).resolve().parents[5]) + '/tools/kaeres/experiments/'
fp={}
for l in open(os.path.expanduser('~/kae-boards/manifest.jsonl')):
    r=json.loads(l); fp[r['id']]=r.get('footprints') or 0
def ids(f): return [x for x in open(f).read().split() if not x.startswith('#')]
def bud(b,base): return min(4*3600, base*max(1,fp.get(b,0)/40)**.5)
# (cpu per budget-second, wall per budget-s)
M={'staged':(1.97,0.51,900),'joint':(2.27,0.54,900),'crit':(1.41,0.53,900),'place600':(1.8,1.05,600),'place300':(1.8,1.05,300)}
def cost(boards,meth,arms,k):
    c,w,base=M[meth]; B=sum(bud(b,base) for b in boards)
    return arms*k*c*B/3600, arms*k*w*B/3600
legd=ids(E+'legality-ab.boards.txt'); legr=ids(E+'legality-ab-relax.boards.txt'); legc=ids(E+'legality-ab-control.boards.txt')
m213=ids(os.path.expanduser('~/kae-baselines/experiments/merge3-ab/boards.txt'))
p4=ids(S+'p4-boards.txt'); cu=ids(S+'copper-boards.txt'); o71=ids(S+'joint-open71.txt')
plan=[
('T1 legality place: downgrade x4 arms k2',legd,'place600',4,2),
('T1 legality place: relax x3 arms k2',legr,'place600',3,2),
('T1 legality place: control x2 arms k2',legc,'place600',2,2),
('T1 legality place-fixed: downgrade x4 k2',legd,'place600',4,2),
('T1 legality place-fixed: relax x3 k2',legr,'place600',3,2),
('T1 legality place-fixed: control x2 k2',legc,'place600',2,2),
('T1 copper C2/RC3: 3 arms k2',cu,'crit',3,2),
('T1 P4 connector_edge: 2 arms k2 (staged, joint kind)',p4,'staged',2,2),
('T2 K11 keep-upright: 2 arms k2 place300',m213,'place300',2,2),
('T2 A/A + J13 + J10 control attempt0: joint 213 x3 arms (ctrl, aa, eff1) k1',m213,'joint',3,1),
('T3 J10: joint ctrl att1-2 on 71 + bump0,rmargin0 k3 on 71',o71,'joint',1,2+3+3),
('T3 P5/P10 staged 213 x4 arms k3',m213,'staged',4,3),
('T3 P5/P10 staged 213 x4 arms k2',m213,'staged',4,2),
]
for name,b,m,a,k in plan:
    c,w=cost(b,m,a,k); print(f"{name:75s} boards={len(b):3d} runs={len(b)*a*k:5d} cpu_h={c:6.0f} sumwall_h={w:6.0f}")
print('fp med 213',sorted(fp[b] for b in m213)[106], 'legd fp med',sorted(fp.get(b,0) for b in legd)[56])
