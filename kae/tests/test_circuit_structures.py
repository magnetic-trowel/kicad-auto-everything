# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Structures (kae.circuit.structures): commutation cells, decoupling, crystals, chains, victims, antennas."""
from circuit_fixtures import C, D, IC, L, Q, R, board, buck_board, fp, mcu_parts

from kae.circuit.netlist import Netlist
from kae.circuit.roles import infer_roles
from kae.circuit.structures import find_structures


def structures(parts):
    nl = Netlist.from_board(board(parts))
    r = infer_roles(nl)
    return nl, r, find_structures(nl, r)


def one(lst, **match):
    hits = [s for s in lst if all(s.get(k) == v for k, v in match.items())]
    assert len(hits) == 1, (match, [s['id'] for s in lst])
    return hits[0]


# ------------------------------------------------------------------------------- commutation cells
def test_integrated_buck_cell_loop_order_and_members():
    nl, r, st = structures(buck_board())
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'buck' and c['rail'] == '+12V' and c['sw'] == 'SW' and c['gnd'] == 'GND'
    # Cin+ -> U.VIN -> U.PGND -> Cin-, closed on the HF (smallest) input capacitor
    assert c['loop'][0] == ['C2', '1'] and c['loop'][-1] == ['C2', '2']
    assert c['loop'][1] == ['U1', ['3']] and c['loop'][2] == ['U1', ['1']]
    assert c['inductor'] == 'L1' and set(c['caps']) == {'C1', 'C2'}
    assert c['bootstrap_cap'] == 'C3'
    assert set(c['output_caps']) == {'C4', 'C5'}
    ex = c['excite']
    assert ex['V'] == 12.0 and ex['I'] == 1.2 and ex['t_sw_ns'] > 0 and ex['f_sw_Hz'] == 500e3


def test_feedback_divider_victim_states_the_output_voltage():
    nl, r, st = structures(buck_board())
    v = one(st['victims'], **{'class': 'feedback'})
    d = v['divider']
    assert d['top'] == 'R1' and d['bottom'] == 'R2' and d['sense_net'] == '+3V3'
    assert abs(d['vout_implied_V'] - 0.596 * (1 + 45.3 / 10)) < 0.01      # TPS54202 Vref 0.596 V
    assert v['nets'] == ['FB']


def test_async_buck_loop_runs_through_the_catch_diode():
    parts = [IC('U1', 'LM2596S-ADJ', 'Package_TO_SOT_SMD:TO-263-5', [('1', 'VIN', '+24V', 'power_in'), ('2', 'OUT', 'SW', 'output'),
                                                                    ('3', 'GND', 'GND', 'power_in'), ('4', 'FB', 'FB', 'input'),
                                                                    ('5', 'ON/OFF', 'GND', 'input')]),
             C('C1', '100uF', '+24V', 'GND', lib='Capacitor_SMD:CP_Elec_8x10'), C('C2', '1uF', '+24V', 'GND', lib='Capacitor_SMD:C_1206_3216Metric'),
             D('D1', 'SS34', 'SW', 'GND', lib='Diode_SMD:D_SMA'), L('L1', '33uH', 'SW', '+5V'),
             C('C3', '220uF', '+5V', 'GND', lib='Capacitor_SMD:CP_Elec_8x10'), R('R1', '3k', '+5V', 'FB'), R('R2', '1k', 'FB', 'GND')]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'buck'
    refs = [t[0] for t in c['loop']]
    assert refs[0] == refs[-1] == 'C2'               # the ceramic, not the electrolytic, closes the hot loop
    assert 'D1' in refs and refs.index('U1') < refs.index('D1')


def test_boost_cell_closes_on_the_output_capacitor():
    parts = [IC('U1', 'MT3608', 'Package_TO_SOT_SMD:SOT-23-6', [('1', 'SW', 'SW', 'power_out'), ('2', 'GND', 'GND', 'power_in'),
                                                               ('3', 'FB', 'FB', 'input'), ('4', 'EN', '+3V3', 'input'),
                                                               ('5', 'IN', '+3V3', 'power_in'), ('6', 'NC', '', 'no_connect')]),
             C('C1', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'), L('L1', '4.7uH', '+3V3', 'SW'),
             D('D1', 'SS14', '+12V', 'SW', lib='Diode_SMD:D_SMA'), C('C2', '22uF', '+12V', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             R('R1', '191k', '+12V', 'FB'), R('R2', '10k', 'FB', 'GND')]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'boost' and c['rail'] == '+12V'
    assert c['loop'][0][0] == c['loop'][-1][0] == 'C2'
    assert [t[0] for t in c['loop'][1:3]] == ['D1', 'D1']


def test_discrete_half_bridge_cell_with_shunt():
    drv = IC('U1', 'IR2104', 'Package_SO:SOIC-8', [('1', 'VCC', '+12V', 'power_in'), ('2', 'IN', 'PWM', 'input'), ('7', 'HO', 'GH', 'output'),
                                                   ('5', 'LO', 'GL', 'output'), ('6', 'VS', 'PHASE', 'passive'), ('4', 'COM', 'GND', 'power_in')])
    parts = [drv, Q('Q1', 'IRF540N', 'GH', '+48V', 'PHASE', lib='Package_TO_SOT_THT:TO-220-3_Vertical'),
             Q('Q2', 'IRF540N', 'GL', 'PHASE', 'SRC', lib='Package_TO_SOT_THT:TO-220-3_Vertical'),
             R('R1', '0R01', 'SRC', 'GND', lib='Resistor_SMD:R_2512_6332Metric'),
             C('C1', '100uF', '+48V', 'GND', lib='Capacitor_THT:CP_Radial_D10.0mm_P5.00mm'), C('C2', '1uF', '+48V', 'GND'),
             C('C3', '100nF', '+12V', 'GND'),
             fp('J1', 'Conn_01x02', 'TerminalBlock:TerminalBlock_bornier-2_P5.08mm', [('1', 'PHASE', '', ''), ('2', 'GND', '', '')])]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], **{'class': 'half_bridge'})
    refs = [t[0] for t in c['loop']]
    assert refs == ['C2', 'Q1', 'Q1', 'Q2', 'Q2', 'R1', 'R1', 'C2']
    assert c['controller'] == 'U1' and c['shunt'] == 'R1' and c['excite']['V'] == 48.0


# ------------------------------------------------------------------------------- decoupling
def test_decap_groups_and_ownership_by_sheet():
    parts = mcu_parts(sheet='/MCU/') + [
        IC('U3', 'W25Q128JVS', 'Package_SO:SOIC-8_5.23x5.23mm', [('8', 'VCC', '+3V3', 'power_in'), ('4', 'GND', 'GND', 'power_in'),
                                                                 ('1', 'CS', 'CS', 'input')], sheet='/Flash/'),
        C('C30', '100nF', '+3V3', 'GND', sheet='/Flash/')]
    nl, r, st = structures(parts)
    mcu = one(st['decaps'], ic='U2', rail='+3V3')
    flash = one(st['decaps'], ic='U3', rail='+3V3')
    assert mcu['power_pins'] == ['1', '2', '3', '4'] and mcu['ground_pins'] == ['6', '7']
    assert set(mcu['caps']) == {'C10', 'C11', 'C12', 'C13', 'C14'}
    assert flash['caps'] == ['C30']
    assert mcu['bulk_caps'] == ['C14'] and 'C14' not in mcu['hf_caps']   # >= 4.7 uF is bulk
    vdda = one(st['decaps'], ic='U2', rail='+3V3A')
    assert vdda['caps'] == ['C15']
    assert set(mcu['pin_caps']) == {'1', '2', '3', '4'}


def test_ldo_input_and_output_caps():
    parts = [IC('U1', 'AMS1117-3.3', 'Package_TO_SOT_SMD:SOT-223-3_TabPin2', [('1', 'GND', 'GND', 'power_in'), ('2', 'VO', '+3V3', 'power_out'),
                                                                             ('3', 'VI', '+5V', 'power_in')]),
             C('C1', '10uF', '+5V', 'GND', lib='Capacitor_SMD:C_0805_2012Metric'),
             C('C2', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_1206_3216Metric'),
             IC('U2', 'ATTINY85-20SU', 'Package_SO:SOIC-8', [('4', 'GND', 'GND', 'power_in'), ('8', 'VCC', '+3V3', 'power_in')]),
             C('C3', '100nF', '+3V3', 'GND')]
    nl, r, st = structures(parts)
    out = one(st['decaps'], ic='U1', function='regulator_output')
    assert out['caps'] == ['C2']
    assert one(st['decaps'], ic='U2')['caps'] == ['C3']
    heat = one(st['heat_sources'], part='U1')
    assert 0.1 < heat['P_W'] < 2.0


# ------------------------------------------------------------------------------- crystal, chains, sense, antenna
def test_crystal_circuit():
    nl, r, st = structures(mcu_parts())
    x = one(st['crystals'], crystal='Y1')
    assert x['ic'] == 'U2' and x['xin'] == '8' and x['xout'] == '9'
    assert set(x['load_caps']) == {'C16', 'C17'} and x['f_Hz'] == 8e6
    one(st['victims'], **{'class': 'crystal'})


def test_usb_connector_chain_with_esd_and_series_resistors():
    parts = mcu_parts() + [
        fp('J1', 'USB_C_Receptacle', 'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',
           [('A6', 'D_P', 'D+', 'bidirectional'), ('A7', 'D_N', 'D-', 'bidirectional'), ('A4', 'VBUS', 'VBUS', 'passive'),
            ('A1', 'GND', 'GND', 'passive'), ('S1', 'SHIELD', 'SHIELD', 'passive')]),
        IC('U4', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6', [('1', 'I/O1', 'D_P', 'passive'), ('2', 'GND', 'GND', 'passive'),
                                                               ('3', 'I/O2', 'D_N', 'passive'), ('5', 'VBUS', 'VBUS', 'passive')]),
        R('R20', '22', 'D_P', 'USB_DP'), R('R21', '22', 'D_N', 'USB_DM'), C('C20', '10uF', 'VBUS', 'GND'),
        C('C21', '4.7nF', 'SHIELD', 'GND'), R('R22', '1M', 'SHIELD', 'GND')]
    nl, r, st = structures(parts)
    ch = one(st['chains'], connector='J1', pin='A6')
    assert ch['chain'] == [['J1', 'A6'], ['U4', '1'], ['R20', '1'], ['R20', '2'], ['U2', '12']]
    assert ch['protection'] == ['U4'] and ch['external'] == 'cable'
    sh = one(st['chains'], connector='J1', pin='S1')
    assert sh['shield_bond'] == 'rc_to_ground' and set(sh['bond']) == {'C21', 'R22'}


def test_sense_resistor_kelvin_loop():
    parts = [IC('U1', 'INA180A1', 'Package_TO_SOT_SMD:SOT-23-5', [('1', 'OUT', 'ISENSE', 'output'), ('2', 'GND', 'GND', 'power_in'),
                                                                 ('3', 'IN+', 'BUS', 'input'), ('4', 'IN-', 'LOAD', 'input'),
                                                                 ('5', 'VS', '+3V3', 'power_in')]),
             R('R1', '0R02', 'BUS', 'LOAD', lib='Resistor_SMD:R_2512_6332Metric'), C('C1', '100nF', '+3V3', 'GND'),
             C('C2', '10uF', 'BUS', 'GND'), R('R2', '10k', 'LOAD', 'GND')]
    nl, r, st = structures(parts)
    v = one(st['victims'], **{'class': 'sense'})
    assert v['shunt'] == 'R1' and v['amp'] == 'U1' and v['kelvin'] == 'pad_inner_edge'
    assert v['loop'] == [['R1', '1'], ['U1', '3'], ['U1', '4'], ['R1', '2']]


def test_antenna_feed_through_a_matching_network():
    parts = [fp('AE1', '2450AT18A100', 'RF_Antenna:Johanson_2450AT18x100', [('1', 'ANT', 'FEED', 'passive'), ('2', 'NC', '', 'no_connect')]),
             C('C1', '1.5pF', 'ANT', 'GND'), L('L1', '2.7nH', 'ANT', 'RF_M', lib='Inductor_SMD:L_0402_1005Metric'),
             C('C2', '1.2pF', 'RF_M', 'GND'),
             IC('U1', 'nRF52832', 'Package_DFN_QFN:QFN-48', [('30', 'ANT', 'RF_M', 'bidirectional'), ('31', 'VSS', 'GND', 'power_in'),
                                                             ('32', 'VDD', '+3V3', 'power_in')]),
             C('C3', '100nF', '+3V3', 'GND')]
    nl, r, st = structures(parts)
    a = one(st['antennas'], part='AE1')
    assert a['feed'][0] == ['AE1', '1'] and a['feed'][-1] == ['U1', '30']
    assert {'C1', 'L1', 'C2'} <= set(a['match']) and a['f_Hz'] == 2.45e9


# ------------------------------------------------------------------------------- audit fixes
def _opamp(ref, sheet=''):
    return IC(ref, 'NE5532', 'Package_DIP:DIP-8_W7.62mm', [('8', 'V+', '+12V', 'power_in'), ('4', 'V-', '-12V', 'power_in'),
                                                          ('3', '+', f'IN_{ref}', 'input'), ('1', '', f'OUT_{ref}', 'output')], sheet=sheet)


def test_split_supply_decoupling_and_entry_bulk():
    """Op-amps decoupled V+ to V- (one cap across each), and the electrolytics stay at the power entry."""
    parts = [fp('J1', 'EuroPower', 'Connector_IDC:IDC-Header_2x05', [('1', '-12V_IN', '-12V', 'passive'), ('3', 'GND', 'GND', 'passive'),
                                                                    ('9', '+12V_IN', '+12V', 'passive')]),
             D('D1', '1N4001', '+12V', '+12V_IN'), D('D2', '1N4001', '-12V_IN', '-12V'),
             C('C1', '22uF', '+12V', 'GND', lib='Capacitor_THT:CP_Radial_D5.0mm_P2.50mm'),
             C('C2', '22uF', 'GND', '-12V', lib='Capacitor_THT:CP_Radial_D5.0mm_P2.50mm'),
             _opamp('U1'), _opamp('U2'), _opamp('U3'),
             C('C3', '100nF', '+12V', '-12V'), C('C4', '100nF', '+12V', '-12V'), C('C5', '100nF', '+12V', '-12V')]
    nl, r, st = structures(parts)
    split = {d['ic']: d for d in st['decaps'] if d['function'] == 'split_supply'}
    assert {k: v['caps'] for k, v in split.items()} == {'U1': ['C3'], 'U2': ['C4'], 'U3': ['C5']}
    assert split['U1']['rail'] == '+12V' and split['U1']['ground'] == '-12V' and split['U1']['ground_pins'] == ['4']
    entry = {d['rail']: d for d in st['decaps'] if d['function'] == 'entry'}
    assert entry['+12V']['ic'] == 'D1' and entry['+12V']['caps'] == ['C1']
    assert entry['-12V']['ic'] == 'D2' and entry['-12V']['caps'] == ['C2']
    assert not any(u['ic'] in ('U1', 'U2', 'U3') for u in st['uncovered'])


def test_converter_output_caps_sit_at_the_inductor():
    nl, r, st = structures(buck_board() + mcu_parts())
    d = one(st['decaps'], function='converter_output')
    assert d['ic'] == 'L1' and d['rail'] == '+3V3' and set(d['caps']) == {'C4', 'C5'}
    mcu = one(st['decaps'], ic='U2', rail='+3V3')
    assert set(mcu['caps']) >= {'C10', 'C11', 'C12', 'C13'}       # the 100 nF caps stay with the MCU's VDD pins


def test_boost_cell_leaves_the_mcu_its_small_caps():
    """A boost converter's output loop closes on the large ceramic when the loads' pins need every 100 nF."""
    u = IC('U1', 'TPS61023', 'Package_TO_SOT_SMD:SOT-563', [('1', 'VIN', '+BATT', 'power_in'), ('2', 'SW', 'SW', 'power_out'),
                                                           ('3', 'GND', 'GND', 'power_in'), ('4', 'VOUT', '+3V3', 'power_out'),
                                                           ('5', 'FB', 'FB', 'input'), ('6', 'EN', '+BATT', 'input')])
    parts = [u, L('L1', '1uH', '+BATT', 'SW'), C('C1', '10uF', '+BATT', 'GND', lib='Capacitor_SMD:C_0603_1608Metric'),
             C('C2', '22uF', '+3V3', 'GND', lib='Capacitor_SMD:C_0603_1608Metric'), R('R1', '732k', '+3V3', 'FB'), R('R2', '100k', 'FB', 'GND'),
             fp('BT1', 'LiPo', 'Battery:BatteryHolder_Keystone_1042_1x18650', [('1', '+BATT', '+', 'passive'), ('2', 'GND', '-', 'passive')])]
    parts += [x for x in mcu_parts() if x.ref not in ('C14',)]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1', **{'class': 'boost'})
    assert c['caps'][0] == 'C2' and c['loop'][0][0] == 'C2'
    mcu = one(st['decaps'], ic='U2', rail='+3V3')
    assert set(mcu['caps']) == {'C10', 'C11', 'C12', 'C13'}
    assert c['loop'][1] == ['U1', ['4']]                       # VOUT only, not the EN pin tied to the rail


def test_mcu_internal_smps_keeps_its_io_supply_pins_as_loads():
    mcu = IC('U1', 'RP2350A', 'Package_DFN_QFN:QFN-60', [('44', 'VREG_VIN', '+3V3', 'power_in'), ('45', 'VREG_LX', 'LX', 'power_out'),
                                                        ('46', 'VREG_PGND', 'GND', 'power_in'), ('47', 'VREG_FB', '+1V1', 'input'),
                                                        ('1', 'IOVDD', '+3V3', 'power_in'), ('10', 'IOVDD', '+3V3', 'power_in'),
                                                        ('22', 'IOVDD', '+3V3', 'power_in'), ('23', 'DVDD', '+1V1', 'power_in'),
                                                        ('61', 'GND', 'GND', 'power_in')])
    parts = [mcu, L('L1', '3.3uH', 'LX', '+1V1'), C('C1', '4.7uF', '+3V3', 'GND'), C('C2', '100nF', '+3V3', 'GND'),
             C('C3', '100nF', '+3V3', 'GND'), C('C4', '100nF', '+3V3', 'GND'), C('C5', '4.7uF', '+1V1', 'GND')]
    nl, r, st = structures(parts)
    one(st['commutation_cells'], controller='U1')
    io = one(st['decaps'], ic='U1', rail='+3V3')
    assert io['power_pins'] == ['1', '10', '22'] and len(io['caps']) >= 2


def test_chains_skip_cell_parts_and_led_zeners():
    parts = buck_board() + [fp('J2', 'Out', 'TerminalBlock:TerminalBlock_bornier-2_P5.08mm', [('1', '+3V3', '', ''), ('2', 'GND', '', '')]),
                            D('D5', 'BZV55C6V2', '+3V3', 'LEDZ', lib='Diode_SMD:D_MiniMELF'), R('R5', '1k', 'LEDZ', 'LEDA'),
                            D('D6', 'LED', 'GND', 'LEDA', lib='LED_SMD:LED_0603_1608Metric')]
    nl, r, st = structures(parts)
    for ch in st['chains']:
        if ch['connector'] == 'J2':
            assert 'D5' not in ch['protection'] and 'L1' not in ch['series']


def test_feedback_found_from_the_net_name_when_pins_are_unnamed():
    u = IC('U1', 'TX4138', 'Package_SO:SOIC-8', [('1', '', 'SW', 'passive'), ('3', '', 'VIN', 'passive'), ('4', '', 'GND', 'passive'),
                                                 ('5', '', 'Vfb', 'passive')])
    parts = [u, L('L1', '33uH', 'SW', 'VOUT'), D('D1', 'SS510', 'SW', 'GND', lib='Diode_SMD:D_SMC'),
             C('C1', '100nF', 'VIN', 'GND'), C('C2', '470uF', 'VOUT', 'GND', lib='Capacitor_THT:CP_Radial_D8.0mm_P3.50mm'),
             R('R1', '56.2k', 'VOUT', 'Vfb'), R('R2', '10k', 'Vfb', 'GND')]
    nl, r, st = structures(parts)
    v = one(st['victims'], **{'class': 'feedback'})
    assert v['divider']['top'] == 'R1' and v['divider']['bottom'] == 'R2'


def test_pmic_buck_input_is_not_its_own_output():
    """nPM1300: the bucks run from VSYS (pin V_DD); +1V8 is buck 1's output through a 0 ohm link, not its input."""
    pm = IC('U1', 'nPM1300-QEXX', 'Package_DFN_QFN:QFN-32', [('1', 'VOUT1', 'VOUT1', 'power_out'), ('2', 'PVSS1', 'GND', 'input'),
                                                            ('3', 'SW1', 'SW1', 'input'), ('4', 'V_{DD}', 'VSYS', 'power_in'),
                                                            ('12', 'V_{IO}', '+1V8', 'power_in'), ('20', 'V_{SYS}', 'VSYS', 'power_out'),
                                                            ('33', 'GND', 'GND', 'passive')])
    parts = [pm, L('L1', '2u2', 'VOUT1', 'SW1'), C('C1', '10uF', 'VOUT1', 'GND'), R('R1', '0R', 'VOUT1', '+1V8'),
             C('C2', '100n', '+1V8', 'GND'), C('C3', '100n', '+1V8', 'GND'), C('C4', '10uF', 'VSYS', 'GND'), C('C5', '10uF', 'VSYS', 'GND')]
    nl, r, st = structures(parts)
    c = one(st['commutation_cells'], controller='U1')
    assert c['class'] == 'buck' and c['rail'] == 'VSYS' and c['loop'][1] == ['U1', ['4']]


def test_logic_strap_divider_is_no_victim_but_an_adc_divider_is():
    parts = [IC('U1', 'STM32F030C8T6', 'Package_QFP:LQFP-48', [('10', 'PA0', 'TOUCH_EN', 'bidirectional'), ('11', 'PA1', 'ADC_VBAT', 'bidirectional'),
                                                             ('1', 'VDD', '+3V3', 'power_in'), ('8', 'VSS', 'GND', 'power_in')]),
             IC('U2', 'AP2112K-3.3', 'Package_TO_SOT_SMD:SOT-23-5', [('1', 'VIN', 'VBAT', 'power_in'), ('5', 'VOUT', '+3V3', 'power_out'),
                                                                     ('2', 'GND', 'GND', 'power_in')]),
             C('C1', '1uF', '+3V3', 'GND'), C('C2', '1uF', 'VBAT', 'GND'),
             R('R1', '100k', '+3V3', 'TOUCH_EN'), R('R2', '100k', 'TOUCH_EN', 'GND'),
             R('R3', '1M', 'VBAT', 'ADC_VBAT'), R('R4', '1M', 'ADC_VBAT', 'GND'),
             fp('BT1', 'LiPo', 'Battery:BatteryHolder_Keystone_1042_1x18650', [('1', 'VBAT', '+', 'passive'), ('2', 'GND', '-', 'passive')])]
    nl, r, st = structures(parts)
    ids = {v['id'] for v in st['victims']}
    assert 'victim:divider:ADC_VBAT' in ids and 'victim:divider:TOUCH_EN' not in ids
