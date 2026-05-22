"""Generate CH2/CH3/CH4 placements from CH1 template via rotation+mirror transforms.

Per master spec 2026-05-23:
- CH1 NW (X=5-39, Y=42-72): 0° — already placed
- CH2 NE (X=61-95, Y=42-72): 90° rot, motor pads at east edge x=95
- CH3 SW (X=5-39, Y=13-42): 270° rot, motor pads at west edge x=5 with mirrored y
- CH4 SE (X=61-95, Y=13-42): 180° rot, motor pads at east edge x=95, mirrored y

Transform implementation (using simpler mirror — equivalent for placement):
- CH2: x → 100-x, y → y       (X-mirror across spine)
- CH3: x → x, y → 85-y         (Y-mirror across board middle)
- CH4: x → 100-x, y → 85-y     (XY mirror)

Component rotation:
- CH2 (X-mirror): rot += 180° (motor pads on opposite side; component flipped)
- CH3 (Y-mirror): rot += 180°
- CH4 (XY-mirror): rot += 0° (double mirror cancels rotation)

Ref mapping (CH1 → CH2 → CH3 → CH4) by net connectivity:
- Built via pcbnew net traversal at script-build time.

Output: S4_CH2_POSITIONS, S4_CH3_POSITIONS, S4_CH4_POSITIONS dicts pasted into place_board.py
"""
import pcbnew
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
board = pcbnew.LoadBoard(str(PCB))

# Map ref → channel (1-4) via net connectivity
ref_to_ch = {}
for code, net in board.GetNetsByNetcode().items():
    name = net.GetNetname()
    for ch in [1, 2, 3, 4]:
        if f"_CH{ch}" in name:
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if pad.GetNet() and pad.GetNet().GetNetname() == name:
                        ref = fp.GetReference()
                        if ref not in ref_to_ch:
                            ref_to_ch[ref] = ch
                        break

# CH1 placements from S4_CH1_POSITIONS (manually extracted from place_board.py)
CH1_POSITIONS = {
    'TP19':(5.0,46.0,'F.Cu',0.0),'TP20':(5.0,56.0,'F.Cu',0.0),'TP21':(5.0,66.0,'F.Cu',0.0),
    'Q5':(12.0,45.0,'B.Cu',0.0),'Q6':(30.0,45.0,'B.Cu',0.0),
    'Q7':(12.0,58.0,'B.Cu',0.0),'Q8':(30.0,58.0,'B.Cu',0.0),
    'Q9':(12.0,70.0,'B.Cu',0.0),'Q10':(30.0,70.0,'B.Cu',0.0),
    'J18':(32.0,52.0,'F.Cu',0.0),'J19':(22.0,50.0,'F.Cu',0.0),
    'J20':(15.0,45.0,'F.Cu',0.0),'J21':(15.0,55.0,'F.Cu',0.0),'J22':(15.0,65.0,'F.Cu',0.0),
    'U2':(35.0,64.0,'F.Cu',0.0),'U3':(28.0,64.0,'F.Cu',0.0),'U4':(37.0,60.0,'F.Cu',0.0),
    'D15':(10.0,43.0,'F.Cu',0.0),'D19':(28.0,59.0,'F.Cu',0.0),'D33':(35.0,43.0,'F.Cu',0.0),
    'TH1':(38.0,68.0,'F.Cu',0.0),
    'R56':(10.0,50.0,'F.Cu',0.0),'R57':(10.0,60.0,'F.Cu',0.0),'R58':(10.0,70.0,'F.Cu',0.0),
}

# CH1 ref → role mapping (so we can find corresponding refs in other channels)
# Roles: MCU, DRV, INA_A, INA_B, INA_C, TL431, LM393, AND, LED_KILL, LED_FAULT, LED_STATUS, NTC, SHUNT_A, SHUNT_B, SHUNT_C, MOTOR_A, MOTOR_B, MOTOR_C, Q_AH, Q_AL, Q_BH, Q_BL, Q_CH, Q_CL
ch1_role_map = {
    'TP19':'MOTOR_A','TP20':'MOTOR_B','TP21':'MOTOR_C',
    'Q5':'Q_AH','Q6':'Q_AL','Q7':'Q_BH','Q8':'Q_BL','Q9':'Q_CH','Q10':'Q_CL',
    'J18':'MCU','J19':'DRV',
    'J20':'INA_A','J21':'INA_B','J22':'INA_C',
    'U2':'TL431','U3':'LM393','U4':'AND',
    'D15':'LED_KILL','D19':'LED_FAULT','D33':'LED_STATUS',
    'TH1':'NTC',
    'R56':'SHUNT_A','R57':'SHUNT_B','R58':'SHUNT_C',
}

# For each role in each channel, find the ref by looking up values + net patterns
# This is approximate — for refs that don't follow a strict pattern, manual map below
ROLE_PATTERNS = {
    'MOTOR_A': lambda v: v.startswith('MOTOR_A_CH'),
    'MOTOR_B': lambda v: v.startswith('MOTOR_B_CH'),
    'MOTOR_C': lambda v: v.startswith('MOTOR_C_CH'),
    'MCU': lambda v: 'AT32F421' in v,
    'DRV': lambda v: 'DRV8300' in v,
    'INA_A': lambda v: 'INA186' in v,
    'INA_B': lambda v: 'INA186' in v,
    'INA_C': lambda v: 'INA186' in v,
    'TL431': lambda v: 'TL431' in v,
    'LM393': lambda v: 'LM393' in v,
    'AND': lambda v: '74LVC1G08' in v,
    'LED_KILL': lambda v: 'RED_KILL_FW' in v,
    'LED_FAULT': lambda v: 'RED_FAULT_HW' in v,
    'LED_STATUS': lambda v: v == 'RED',
    'NTC': lambda v: '10K_B4250' in v,
    'SHUNT_A': lambda v: '0.2mR' in v,
    'SHUNT_B': lambda v: '0.2mR' in v,
    'SHUNT_C': lambda v: '0.2mR' in v,
    'Q_AH': lambda v: 'AOTL66912' in v,
    'Q_AL': lambda v: 'AOTL66912' in v,
    'Q_BH': lambda v: 'AOTL66912' in v,
    'Q_BL': lambda v: 'AOTL66912' in v,
    'Q_CH': lambda v: 'AOTL66912' in v,
    'Q_CL': lambda v: 'AOTL66912' in v,
}

# For each channel, find role→ref mapping
ch_role_to_ref = {1: {}, 2: {}, 3: {}, 4: {}}

for fp in board.GetFootprints():
    ref = fp.GetReference()
    val = fp.GetValue()
    ch = ref_to_ch.get(ref)
    if ch is None:
        continue
    # Motor pads (by value)
    if 'MOTOR_A_CH' in val and val == f'MOTOR_A_CH{ch}': ch_role_to_ref[ch]['MOTOR_A'] = ref
    if 'MOTOR_B_CH' in val and val == f'MOTOR_B_CH{ch}': ch_role_to_ref[ch]['MOTOR_B'] = ref
    if 'MOTOR_C_CH' in val and val == f'MOTOR_C_CH{ch}': ch_role_to_ref[ch]['MOTOR_C'] = ref
    # MCU
    if 'AT32F421' in val: ch_role_to_ref[ch]['MCU'] = ref
    # DRV
    if 'DRV8300' in val: ch_role_to_ref[ch]['DRV'] = ref
    # NTC
    if '10K_B4250' in val: ch_role_to_ref[ch]['NTC'] = ref
    # Other ICs by ref count below

# INAs and others — use ref sequence per channel
for ch in [1, 2, 3, 4]:
    refs = sorted([r for r, c in ref_to_ch.items() if c == ch])
    # INA186: SOT-363, 3 per channel
    inas = sorted([r for r in refs if r.startswith('J') and 'INA186' in (board.FindFootprintByReference(r).GetValue() if board.FindFootprintByReference(r) else '')])
    if len(inas) >= 3:
        ch_role_to_ref[ch]['INA_A'] = inas[0]
        ch_role_to_ref[ch]['INA_B'] = inas[1]
        ch_role_to_ref[ch]['INA_C'] = inas[2]
    # TL431
    tl431s = [r for r in refs if r.startswith('U') and 'TL431' in (board.FindFootprintByReference(r).GetValue() or '')]
    if tl431s: ch_role_to_ref[ch]['TL431'] = tl431s[0]
    # LM393
    lm393s = [r for r in refs if r.startswith('U') and 'LM393' in (board.FindFootprintByReference(r).GetValue() or '')]
    if lm393s: ch_role_to_ref[ch]['LM393'] = lm393s[0]
    # 74LVC1G08
    ands = [r for r in refs if r.startswith('U') and '74LVC1G08' in (board.FindFootprintByReference(r).GetValue() or '')]
    if ands: ch_role_to_ref[ch]['AND'] = ands[0]
    # LEDs
    led_kill = [r for r in refs if r.startswith('D') and 'RED_KILL_FW' in (board.FindFootprintByReference(r).GetValue() or '')]
    if led_kill: ch_role_to_ref[ch]['LED_KILL'] = led_kill[0]
    led_fault = [r for r in refs if r.startswith('D') and 'RED_FAULT_HW' in (board.FindFootprintByReference(r).GetValue() or '')]
    if led_fault: ch_role_to_ref[ch]['LED_FAULT'] = led_fault[0]
    led_stat = [r for r in refs if r.startswith('D') and (board.FindFootprintByReference(r).GetValue() or '') == 'RED']
    if led_stat: ch_role_to_ref[ch]['LED_STATUS'] = led_stat[0]
    # Shunts (3× 0.2mR per channel)
    shunts = sorted([r for r in refs if r.startswith('R') and '0.2mR' in (board.FindFootprintByReference(r).GetValue() or '')])
    if len(shunts) >= 3:
        ch_role_to_ref[ch]['SHUNT_A'] = shunts[0]
        ch_role_to_ref[ch]['SHUNT_B'] = shunts[1]
        ch_role_to_ref[ch]['SHUNT_C'] = shunts[2]
    # MOSFETs (6× AOTL66912 per channel)
    qs = sorted([r for r in refs if r.startswith('Q') and 'AOTL66912' in (board.FindFootprintByReference(r).GetValue() or '')], key=lambda r: int(r[1:]))
    if len(qs) >= 6:
        ch_role_to_ref[ch]['Q_AH'] = qs[0]
        ch_role_to_ref[ch]['Q_AL'] = qs[1]
        ch_role_to_ref[ch]['Q_BH'] = qs[2]
        ch_role_to_ref[ch]['Q_BL'] = qs[3]
        ch_role_to_ref[ch]['Q_CH'] = qs[4]
        ch_role_to_ref[ch]['Q_CL'] = qs[5]

# Print role maps
for ch in [1, 2, 3, 4]:
    print(f"CH{ch} role map: {ch_role_to_ref[ch]}")

# Transform CH1 positions for CH2/3/4
def transform(x, y, rot, channel):
    if channel == 2:  # NE: X-mirror
        return 100.0 - x, y, (rot + 180) % 360
    elif channel == 3:  # SW: Y-mirror
        return x, 85.0 - y, (rot + 180) % 360
    elif channel == 4:  # SE: XY-mirror
        return 100.0 - x, 85.0 - y, rot
    return x, y, rot

# Generate CHn dicts
for ch in [2, 3, 4]:
    print(f"\n# CH{ch} placements (X-mirror with rot+180):")
    out_lines = [f"S4_CH{ch}_POSITIONS = {{"]
    for ref, role in ch1_role_map.items():
        ch_ref = ch_role_to_ref[ch].get(role)
        if ch_ref is None:
            continue
        x, y, layer, rot = CH1_POSITIONS[ref]
        nx, ny, nrot = transform(x, y, rot, ch)
        out_lines.append(f"    '{ch_ref}': ({nx:.1f}, {ny:.1f}, '{layer}', {nrot:.1f}),")
    out_lines.append("}")
    print("\n".join(out_lines))
