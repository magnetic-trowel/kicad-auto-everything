# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Smallest end-to-end example: a USB-powered 3.3 V LDO driving an LED through a MOSFET."""
from kaesynth import Design, Isolation, PinDef, Ratings, VLimit
from kaesynth.lib import C, IC, LED, NMOS, PINMAP_SOT23_FET, R, Conn, Fuse


def build():
    d = Design("usb-led", title="USB LED example", brief="Light an LED from USB, switchable from a header.")
    d.require("REQ-1", "Run from USB 5 V", value="4.4-5.5 V", verify="bench")
    d.question("Q-1", "Which LED colour?", default="green")

    gnd = d.net("GND", domain="USB", v=0, kind="ground")
    vbus = d.net("VBUS", domain="USB", v=(0, 5.5), kind="power", i_max=0.3, external=True,
                 threats=("overcurrent",))
    v5 = d.net("+5V", domain="USB", v=(0, 5.5), kind="power", i_max=0.3)
    v33 = d.net("+3V3", domain="USB", v=(0, 3.4), kind="power", i_max=0.1)
    d.domain("USB", ref="GND", kind="selv", description="USB bus power")

    ldo = IC("AP2112K-3.3TRG1", manufacturer="Diodes Inc.", footprint="Package_TO_SOT_SMD:SOT-23-5",
             pins=[PinDef(1, "VIN", "power_in"), PinDef(2, "GND", "power_in"), PinDef(3, "EN", "input"),
                   PinDef(4, "NC", "no_connect"), PinDef(5, "VOUT", "power_out")],
             ratings=Ratings(limits=[VLimit(("VIN",), ("GND",), 6.5)]),
             datasheet="https://www.diodes.com/assets/Datasheets/AP2112.pdf",
             source={"pins": "AP2112 DS, SOT-25 pin description table", "ratings": "abs max: VIN 6.5 V"})

    pwr = d.block("power", title="USB input and 3.3 V LDO")
    j = pwr.add(Conn(2, "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", i_max=3, v_max=50), ref="J1")
    f = pwr.add(Fuse(0.5, 6, "Fuse:Fuse_0805_2012Metric", ptc=True, mpn="0805L050SLWR", manufacturer="Littelfuse"))
    u = pwr.add(ldo)
    cin = pwr.add(C("1u", 16, "0603"))
    cout = pwr.add(C("1u", 16, "0603"))
    vbus.connect(j[1], f[1])
    gnd.connect(j[2], u["GND"], cin[2], cout[2])
    v5.connect(f[2], u["VIN"], u["EN"], cin[1])
    v33.connect(u["VOUT"], cout[1])
    u.nc_pins("NC", reason="no internal connection (datasheet pin table)")

    drv = d.block("led", title="LED driver")
    q = drv.add(NMOS("2N7002", "Package_TO_SOT_SMD:SOT-23", vds=60, vgs=20, i_d=0.3, manufacturer="onsemi",
                         pinmap=PINMAP_SOT23_FET, datasheet="https://www.onsemi.com/pdf/datasheet/nds7002a-d.pdf",
                         source={"pinmap": "2N7002 DS, SOT-23 pinout: 1 G, 2 S, 3 D", "ratings": "abs max table"}))
    rl = drv.add(R("150", "0603"))
    rg = drv.add(R("10k", "0603"))
    led = drv.add(LED("green"))
    hdr = drv.add(Conn(1, "Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical", i_max=1, v_max=50))
    a = drv.net("LED_A", v=(0, 3.4))
    k = drv.net("LED_K", v=(0, 3.4))
    ctl = drv.net("CTL", v=(0, 3.4), external=True)
    v33.connect(rl[1])
    a.connect(rl[2], led["A"])
    k.connect(led["K"], q["D"])
    ctl.connect(hdr[1], q["G"], rg[1])
    gnd.connect(q["S"], rg[2])

    d.place.edge(j, "west")
    d.place.near(cin, u["VIN"], "tight")
    d.place.group(drv)
    d.board(width_mm=30, height_mm=20, layers=2)
    return d
