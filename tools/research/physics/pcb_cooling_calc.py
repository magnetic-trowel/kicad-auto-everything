# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The [calc] numbers of docs/research/physics/pcb-cooling*.md: via thermal resistance, spreading
length and floor of a pour, face heat-transfer coefficients, in-plane conductivity of a stackup."""
import math
try:
    from scipy.special import k0,k1,i0,i1
except ImportError:
    k0=k1=None
kCu=390.
def via_R(drill_mm, plate_um, L_mm=1.6, fill_k=0.0):
    r=drill_mm/2e3; t=plate_um*1e-6; L=L_mm*1e-3
    Ab=math.pi*(r*r-(r-t)**2); Af=math.pi*(r-t)**2
    return L/(kCu*Ab+fill_k*Af)
print("single via R (K/W), L=1.6mm")
for d in (0.2,0.25,0.3,0.4,0.5):
    row=[f"{via_R(d,p):6.0f}" for p in (18,25,35)]
    print(d,"open 18/25/35um:",row," epoxy(0.3)",f"{via_R(d,25,fill_k=0.3):.0f}"," conductive(8)",f"{via_R(d,25,fill_k=8):.0f}"," solder(58)",f"{via_R(d,25,fill_k=58):.0f}"," Cu(390)",f"{via_R(d,25,fill_k=390):.0f}")
print("L=0.8mm 0.3/25:",round(via_R(0.3,25,0.8)),"L=1.0:",round(via_R(0.3,25,1.0)))
# fin length
def Lfin(kt,h): return math.sqrt(kt/h)
for name,kt in (("1 layer 1oz",390*35e-6),("2 layers 1oz",2*390*35e-6+0.3*1.5e-3),("2 layers 2oz",2*390*70e-6),("4 layers 1oz",4*390*35e-6)):
    for h,lab in ((12,"one face h=12"),(24,"two faces 2x12")):
        print(name,lab,"L=%.0f mm"%(1e3*Lfin(kt,h)))
if k0:
    print("annular fin, source radius a, plate to radius b, both faces h=12 each (htot=24), 2-layer 1oz")
    kt=2*390*35e-6; h=24
    L=Lfin(kt,h); m=1/L
    def Rfin(a,b):
        # insulated tip annular fin
        num = k1(m*b)*i0(m*a)+i1(m*b)*k0(m*a)
        den = i1(m*b)*k1(m*a)-k1(m*b)*i1(m*a)
        return num/(2*math.pi*kt*m*a*den)
    for a in (1.5,3,5):
        print(" a=%.1fmm"%a, ["b=%d:%.1f"%(b,Rfin(a*1e-3,b*1e-3)) for b in (5,10,20,30,40,60,80,120,200)])
    for name,kt2 in (("1 layer 1oz one face h=12",390*35e-6),):
        m=1/Lfin(kt2,12)
        def R2(a,b):
            num = k1(m*b)*i0(m*a)+i1(m*b)*k0(m*a)
            den = i1(m*b)*k1(m*a)-k1(m*b)*i1(m*a)
            return num/(2*math.pi*kt2*m*a*den)
        print(name," a=3mm",["b=%d:%.1f"%(b,R2(3e-3,b*1e-3)) for b in (10,20,40,80,200)])
    print("4-layer 1oz both faces h=24, a=3:")
    kt=4*390*35e-6; m=1/Lfin(kt,24)
    def R4(a,b):
        num = k1(m*b)*i0(m*a)+i1(m*b)*k0(m*a)
        den = i1(m*b)*k1(m*a)-k1(m*b)*i1(m*a)
        return num/(2*math.pi*kt*m*a*den)
    print(["b=%d:%.1f"%(b,R4(3e-3,b*1e-3)) for b in (10,20,40,80,200)])
# radiation h
s=5.67e-8
for e in (0.9,0.8,0.5,0.05):
    for Ts in (40,60,85):
        T=Ts+273.15;Ta=298.15
        print("eps",e,"Ts",Ts,"h_rad=%.1f"%(e*s*(T**2+Ta**2)*(T+Ta)))
# effective in-plane conductivity
t=1.6e-3
for lay,cu in ((2,35e-6),(4,35e-6),(2,70e-6)):
    kin=(lay*cu*390+(t-lay*cu)*0.3)/t
    print(lay,"layers",cu*1e6,"um: k_in=%.1f W/mK"%kin)
