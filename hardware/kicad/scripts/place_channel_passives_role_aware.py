#!/usr/bin/env python3
"""place_channel_passives_role_aware.py — PR-channel-template-redo Phase 3.

Role-driven net-aware placement for per-channel passives. Built per master
2026-05-23 Option C dispatch: ref-shift events (e.g., SKiDL re-numbering after
component removal) must NOT break placement. This script identifies passives by
the NET PATTERN of their primary channel-tagged net, finds the appropriate
anchor IC + pad from the live PCB, and spiral-searches for a valid position
satisfying R23 (no passive island), R25 (same-side decoupling), R24 (on-board),
and quadrant-zone rules.

Algorithm:
  1. Parse netlist for per-channel passives (any pad on a *_CH<n> net).
  2. Classify role from net pattern (ROLE_PATTERNS table).
  3. Look up anchor IC (e.g., 'FET-gate-hi-A' → Q5/Q7/Q9 for CH1 hi-side phase A).
  4. Get anchor pad coordinate from current PCB (pcbnew API).
  5. Spiral search 0.5mm grid up to max_dist for collision-free, in-quadrant slot.
  6. CH1 placed first; CH2/3/4 mirrored via locked transforms.

Outputs final placements directly to PCB. Includes audit-trail print per ref.

Reusable: any future SKiDL refactor with same role-set runs without edit.
"""

import pcbnew
import re
import sys
from collections import defaultdict
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")

# Channel quadrant zones (FET-geometry derived, per Phase 4 R23 spec)
CHAN_ZONES = {
    1: (0, 50, 50, 100),    # CH1 NW
    2: (50, 50, 100, 100),  # CH2 NE
    3: (50, 0, 100, 50),    # CH3 SE
    4: (0, 0, 50, 50),      # CH4 SW
}
BOARD_MIN, BOARD_MAX = 0.0, 100.0
QUADRANT_TOL = 1.0   # mm slop allowed at channel-zone boundary

# Role classification: list of (regex on net name, role_key, anchor_role, max_dist_mm).
# anchor_role is a tuple lookup key used by find_anchor() below.
# Order matters — earlier patterns win.
ROLE_PATTERNS = [
    # gate-Rs: GH[ABC] = high-side gate, GL[ABC] = low-side gate
    (re.compile(r'^GH([ABC])_CH(\d+)$'), 'gate-R-hi-{m1}',        ('FET-gate-hi', '{m1}'),  5.0),
    (re.compile(r'^GL([ABC])_CH(\d+)$'), 'gate-R-lo-{m1}',        ('FET-gate-lo', '{m1}'),  5.0),
    # bootstrap caps between BST and motor output (DRV pins)
    (re.compile(r'^BST([ABC])_CH(\d+)$'),'bootstrap-{m1}',        ('DRV-BST', '{m1}'),      2.5),
    # BEMF dividers — anchored to motor output FET drain/motor pad
    (re.compile(r'^BEMF_([ABC])_CH(\d+)$'),'BEMF-{m1}',           ('motor-pad', '{m1}'),    6.0),
    # CSA filter cap — anchored to INA186 output pin
    (re.compile(r'^CSA_([ABC])_OUT_CH(\d+)$'),'csa-filter-{m1}',  ('INA-out', '{m1}'),      4.0),
    # CSA diode-OR network — anchored to LM393 input (CSA_MAX node)
    (re.compile(r'^CSA_MAX_CH(\d+)$'),    'csa-max',              ('LM393-csa-in', None),   6.0),
    # VREF divider/hysteresis — anchored to LM393 (per-channel divider top + r_fb)
    (re.compile(r'^VREF_I_TRIP_CH(\d+)$'),'vref-i-trip',          ('LM393-in+', None),      5.0),
    (re.compile(r'^VREF_OTP_CH(\d+)$'),   'vref-otp',             ('LM393-in-', None),      5.0),
    # NTC sense — anchored to MCU NTC pad (mcu[9]) — primary anchor
    (re.compile(r'^NTC_CH(\d+)$'),        'ntc-pullup',           ('NTC-thermistor', None), 5.0),
    (re.compile(r'^NTC_CH(\d+)_1$'),      'ntc-link',             ('NTC-thermistor', None), 3.0),
    # Kill-rail / I_TRIP / OTP_TRIP — anchored to AND gate
    (re.compile(r'^I_TRIP_N_CH(\d+)$'),   'i-trip-pullup',        ('AND-input', None),      5.0),
    (re.compile(r'^OTP_TRIP_N_CH(\d+)$'), 'otp-trip-pullup',      ('AND-input', None),      5.0),
    (re.compile(r'^KILL_LOCAL_N_CH(\d+)$'),'kill-local',          ('AND-output', None),     5.0),
    (re.compile(r'^KILL_RAIL_N_CH(\d+)$'),'kill-rail',            ('DRV-nSLEEP', None),     5.0),
    (re.compile(r'^KILL_BUS_CH(\d+)$'),   'kill-bus',             ('AND-output', None),     5.0),
    # SHUNT_TOP between FET source and INA186 sense
    (re.compile(r'^SHUNT_([ABC])_TOP_CH(\d+)$'),'shunt-cap-{m1}', ('INA-shunt', '{m1}'),    3.0),
    # MOTOR_X passives — TVS to GND, motor anchor
    (re.compile(r'^MOTOR_([ABC])_CH(\d+)$'),'motor-related-{m1}', ('motor-pad', '{m1}'),    3.0),
    # PWM input pull-down — anchored to DRV input pin / MCU output
    (re.compile(r'^PWM_INH([ABC])_CH(\d+)$'),'pwm-inh-{m1}',      ('MCU-pwm', '{m1}'),      5.0),
    (re.compile(r'^PWM_INL([ABC])_CH(\d+)$'),'pwm-inl-{m1}',      ('MCU-pwm', '{m1}'),      5.0),
    # MCU peripherals
    (re.compile(r'^NRST_CH(\d+)$'),       'mcu-nrst',             ('MCU-nrst', None),       3.0),
    (re.compile(r'^BOOT0_CH(\d+)$'),      'mcu-boot0',            ('MCU-boot0', None),      3.0),
    (re.compile(r'^VBAT_SENSE_CH(\d+)$'), 'mcu-vbat',             ('MCU-near', None),       5.0),
    # LED-related
    (re.compile(r'^LED_GPIO_CH(\d+)$'),   'led-gpio',             ('MCU-near', None),       5.0),
    (re.compile(r'^KILL_LED_NODE_CH(\d+)$'),'led-kill',           ('AND-output', None),     5.0),
    (re.compile(r'^HW_FAULT_LED_K_CH(\d+)$'),'led-hw-fault',      ('AND-output', None),     6.0),
    (re.compile(r'^N\$\d+$'),             'skip-anonymous',       None,                     0),
    (re.compile(r'^PA11_CH(\d+)_LED_KILL$'),'led-kill-mcu',       ('MCU-near', None),       5.0),
    # MCU NC pins — auto, near MCU body
    (re.compile(r'^(PA11_NC|PA12_NC|PB3_NC|PB5_NC|PB7_NC|PF0_NC|PF1_NC)_CH(\d+)$'),
                                          'mcu-nc',               ('MCU-near', None),       5.0),
    # SWD test points handled by S-layer placement (TP refs), skip here
    (re.compile(r'^SWDIO_CH(\d+)$'),      'skip-swd',             None,                     0),
    (re.compile(r'^SWCLK_CH(\d+)$'),      'skip-swd',             None,                     0),
]


def parse_chn_suffix(net_name):
    """Return the integer channel number from a *_CH<n> net name, or None."""
    m = re.search(r'_CH(\d+)(?:_|$)', net_name)
    if m:
        return int(m.group(1))
    return None


def classify_role(net_names):
    """Return (role_key, anchor_spec, max_dist, ch_num) for a passive's net set.
    Picks the FIRST matching (most-specific) net per ROLE_PATTERNS order."""
    for net in sorted(net_names):
        for pat, role_tpl, anchor_tpl, max_dist in ROLE_PATTERNS:
            m = pat.match(net)
            if not m:
                continue
            groups = m.groups()
            if len(groups) == 0:
                # Anonymous nets (N$xxx) — skip; continue scanning other nets
                continue
            # Most patterns have 1-2 groups: last is channel num
            if len(groups) == 1:
                ch = int(groups[0])
                role_key = role_tpl
                anchor = anchor_tpl
            else:
                # First group = phase letter or sub-pattern; last = channel
                ch = int(groups[-1])
                role_key = role_tpl.replace('{m1}', groups[0])
                if anchor_tpl is None:
                    anchor = None
                else:
                    a0, a1 = anchor_tpl
                    a1_real = a1.replace('{m1}', groups[0]) if a1 else None
                    anchor = (a0, a1_real)
            return (role_key, anchor, max_dist, ch)
    return (None, None, None, None)


def load_board_data():
    """Return: footprints dict, pad-position index, anchor lookup."""
    board = pcbnew.LoadBoard(str(PCB))
    fp_data = {}   # ref → {fp, x, y, nets, pads:[{num, x, y, net}]}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        p = fp.GetPosition()
        pads_info = []
        for pad in fp.Pads():
            pp = pad.GetPosition()
            pads_info.append({
                'num': pad.GetNumber(),
                'name': pad.GetName(),
                'x': pp.x / 1e6, 'y': pp.y / 1e6,
                'net': pad.GetNetname(),
            })
        fp_data[ref] = {
            'fp': fp,
            'x': p.x / 1e6, 'y': p.y / 1e6,
            'rot': fp.GetOrientationDegrees(),
            'layer': 'F.Cu' if fp.GetLayer() == pcbnew.F_Cu else 'B.Cu',
            'value': fp.GetValue(),
            'pads': pads_info,
            'nets': {pi['net'] for pi in pads_info if pi['net']},
        }
    return board, fp_data


def find_anchor_pad(anchor_spec, ch_num, fp_data):
    """Given anchor_spec = (anchor_kind, phase_letter_or_None), find the pad
    coordinate on the PCB that anchors this role for the given channel.
    Returns (x, y, parent_ref) or None.

    Anchor lookup logic per anchor_kind:
      'FET-gate-hi'/'FET-gate-lo': find FET whose gate net = GH[ABC]_CH<n> / GL[ABC]_CH<n>,
            return gate pad coord.
      'DRV-BST': find DRV (J19/J24/J29/J34) BST pin matching phase.
      'motor-pad': find TestPoint TP<n> whose value = MOTOR_<phase>_CH<n>.
      'INA-out': find INA186 (J20-J37) whose pad-5 (CSA_OUT) net = CSA_<phase>_OUT_CH<n>.
      'INA-shunt': find INA186 pad-1 (V+) net = SHUNT_<phase>_TOP_CH<n>.
      'LM393-csa-in': find LM393 pad-2 (Comp A IN-) on CSA_MAX_CH<n>.
      'LM393-in+': find LM393 pad-3 (Comp A IN+) on VREF_I_TRIP_CH<n>.
      'LM393-in-': find LM393 pad-6 (Comp B IN-) on VREF_OTP_CH<n>.
      'NTC-thermistor': find TH<n> footprint.
      'AND-input': find 74LVC1G08 pad-1 or pad-2.
      'AND-output': find 74LVC1G08 pad-4 (Y).
      'DRV-nSLEEP': find DRV pad-8.
      'MCU-pwm': find MCU pin for PWM_IN[HL]<phase>_CH<n>.
      'MCU-nrst'/'MCU-boot0': find MCU pin for NRST/BOOT0 net.
      'MCU-near': fall back to MCU body center.
    """
    anchor_kind, phase = anchor_spec
    chs = str(ch_num)

    # Build helper: find FP by net match
    def fp_with_net(net_name):
        for ref, d in fp_data.items():
            if net_name in d['nets']:
                return ref
        return None

    def pad_with_net(ref, net_name):
        d = fp_data.get(ref)
        if not d:
            return None
        for pi in d['pads']:
            if pi['net'] == net_name:
                return (pi['x'], pi['y'])
        return None

    if anchor_kind == 'FET-gate-hi':
        # Hi-side FET phase X for ch n: source pads (1/2/3/9) on MOTOR_<X>_CH<n>,
        # drain pads (5-8) on VMOTOR_CH. Gate pad (4) on anonymous N$.
        motor_net = f'MOTOR_{phase}_CH{chs}'
        for ref, d in fp_data.items():
            if not (ref.startswith('Q') and 'BSC014N06NS' in d['value']):
                continue
            # Find pad 1 net = MOTOR_<phase>_CH<n> (source side = hi-FET signature)
            p1 = next((pi for pi in d['pads'] if pi['name'] == '1'), None)
            if p1 and p1['net'] == motor_net:
                # This is the hi-side FET; return gate pad 4 coordinate
                p4 = next((pi for pi in d['pads'] if pi['name'] == '4'), None)
                if p4:
                    return (p4['x'], p4['y'], ref)
        return None
    if anchor_kind == 'FET-gate-lo':
        # Lo-side FET phase X for ch n: drain (5-8) on MOTOR_<X>_CH<n>,
        # source (1/2/3/9) on SHUNT_<X>_TOP_CH<n>. Gate pad (4) on anonymous N$.
        motor_net = f'MOTOR_{phase}_CH{chs}'
        shunt_net = f'SHUNT_{phase}_TOP_CH{chs}'
        for ref, d in fp_data.items():
            if not (ref.startswith('Q') and 'BSC014N06NS' in d['value']):
                continue
            p1 = next((pi for pi in d['pads'] if pi['name'] == '1'), None)
            p5 = next((pi for pi in d['pads'] if pi['name'] == '5'), None)
            if (p1 and p1['net'] == shunt_net) and (p5 and p5['net'] == motor_net):
                p4 = next((pi for pi in d['pads'] if pi['name'] == '4'), None)
                if p4:
                    return (p4['x'], p4['y'], ref)
        return None
    if anchor_kind == 'DRV-BST':
        net = f'BST{phase}_CH{chs}'
        ref = fp_with_net(net)
        if ref:
            p = pad_with_net(ref, net)
            if p: return (*p, ref)
        return None
    if anchor_kind == 'motor-pad':
        # PR-channel-template-redo Phase 3 fix (master 2026-05-24 finding):
        # OLD logic returned MOTOR_<phase>_CH<n> testpoint position, which put
        # motor-net components (Zener clamps, TVS, BEMF dividers) INSIDE the
        # motor-TP keep-out zone. Pre-Phase-3 PR #68 layout placed these near
        # the HI-side FET body (X=15-25 for CH1 west) — outside the TP zone
        # while still functionally on the motor net.
        #
        # New logic: anchor to HI-side FET for this phase+channel. HI-side FET
        # identified by pad-1 net = MOTOR_<phase>_CH<n>. Return FET body center.
        motor_net = f'MOTOR_{phase}_CH{chs}'
        for ref, d in fp_data.items():
            if not (ref.startswith('Q') and 'BSC014N06NS' in d['value']):
                continue
            p1 = next((pi for pi in d['pads'] if pi['name'] == '1'), None)
            if p1 and p1['net'] == motor_net:
                # HI-side FET; return body center (will spiral around it,
                # naturally clearing motor TP zone)
                return (d['x'], d['y'], ref)
        # Fallback: motor TP itself (if no HI FET found)
        target_val = f'MOTOR_{phase}_CH{chs}'
        for ref, d in fp_data.items():
            if d['value'] == target_val:
                return (d['x'], d['y'], ref)
        return None
    if anchor_kind == 'INA-out':
        net = f'CSA_{phase}_OUT_CH{chs}'
        for ref, d in fp_data.items():
            if ref.startswith('J') and 'INA186' in d['value'] and net in d['nets']:
                p = pad_with_net(ref, net)
                if p: return (*p, ref)
        return None
    if anchor_kind == 'INA-shunt':
        # PR-channel-template-redo Phase 3 fix: anchor LO-side FET (source pad is
        # on SHUNT_TOP net) instead of INA. INAs at X=5/8/92/95 are too close to
        # motor TPs; LO-side FETs are at X=30 (CH1/CH4) or X=70 (CH2/CH3), well
        # outside motor TP keep-out zones.
        shunt_net = f'SHUNT_{phase}_TOP_CH{chs}'
        motor_net = f'MOTOR_{phase}_CH{chs}'
        for ref, d in fp_data.items():
            if not (ref.startswith('Q') and 'BSC014N06NS' in d['value']):
                continue
            p1 = next((pi for pi in d['pads'] if pi['name'] == '1'), None)
            p5 = next((pi for pi in d['pads'] if pi['name'] == '5'), None)
            # LO-side FET: pad 1 source = SHUNT_TOP, pad 5 drain = MOTOR
            if (p1 and p1['net'] == shunt_net) and (p5 and p5['net'] == motor_net):
                return (d['x'], d['y'], ref)
        # Fallback: INA shunt pin
        for ref, d in fp_data.items():
            if ref.startswith('J') and 'INA186' in d['value'] and shunt_net in d['nets']:
                p = pad_with_net(ref, shunt_net)
                if p: return (*p, ref)
        return None
    if anchor_kind in ('LM393-csa-in', 'LM393-in+', 'LM393-in-'):
        net_map = {
            'LM393-csa-in': f'CSA_MAX_CH{chs}',
            'LM393-in+': f'VREF_I_TRIP_CH{chs}',
            'LM393-in-': f'VREF_OTP_CH{chs}',
        }
        net = net_map[anchor_kind]
        for ref, d in fp_data.items():
            if ref.startswith('U') and 'LM393' in d['value'] and net in d['nets']:
                p = pad_with_net(ref, net)
                if p: return (*p, ref)
        return None
    if anchor_kind == 'NTC-thermistor':
        # TH<channel> NTC thermistor
        target_refs = {1: 'TH1', 2: 'TH2', 3: 'TH3', 4: 'TH4'}
        ref = target_refs.get(ch_num)
        if ref and ref in fp_data:
            d = fp_data[ref]
            return (d['x'], d['y'], ref)
        return None
    if anchor_kind == 'AND-input':
        for ref, d in fp_data.items():
            if ref.startswith('U') and '74LVC1G08' in d['value']:
                # AND gate per channel: check it has the channel's I_TRIP_N or OTP_TRIP_N net
                ch_nets = {f'I_TRIP_N_CH{chs}', f'OTP_TRIP_N_CH{chs}', f'KILL_LOCAL_N_CH{chs}'}
                if d['nets'] & ch_nets:
                    return (d['x'], d['y'], ref)
        return None
    if anchor_kind == 'AND-output':
        for ref, d in fp_data.items():
            if ref.startswith('U') and '74LVC1G08' in d['value']:
                if f'KILL_LOCAL_N_CH{chs}' in d['nets']:
                    return (d['x'], d['y'], ref)
        return None
    if anchor_kind == 'DRV-nSLEEP':
        net = f'KILL_RAIL_N_CH{chs}'
        for ref, d in fp_data.items():
            if ref.startswith('J') and 'DRV8300' in d['value'] and net in d['nets']:
                p = pad_with_net(ref, net)
                if p: return (*p, ref)
        return None
    if anchor_kind == 'MCU-pwm':
        # MCU has PWM_IN[HL]<phase>_CH<n> on its pad
        for net_pre in (f'PWM_INH{phase}_CH{chs}', f'PWM_INL{phase}_CH{chs}'):
            for ref, d in fp_data.items():
                if ref.startswith('J') and 'AT32F421' in d['value'] and net_pre in d['nets']:
                    p = pad_with_net(ref, net_pre)
                    if p: return (*p, ref)
        return None
    if anchor_kind == 'MCU-nrst':
        net = f'NRST_CH{chs}'
        for ref, d in fp_data.items():
            if ref.startswith('J') and 'AT32F421' in d['value'] and net in d['nets']:
                p = pad_with_net(ref, net)
                if p: return (*p, ref)
        return None
    if anchor_kind == 'MCU-boot0':
        net = f'BOOT0_CH{chs}'
        for ref, d in fp_data.items():
            if ref.startswith('J') and 'AT32F421' in d['value'] and net in d['nets']:
                p = pad_with_net(ref, net)
                if p: return (*p, ref)
        return None
    if anchor_kind == 'MCU-near':
        # Find this channel's MCU body center
        for ref, d in fp_data.items():
            if ref.startswith('J') and 'AT32F421' in d['value']:
                # Verify channel by checking it has any _CH<n> net
                if any(re.search(rf'_CH{chs}(_|$)', n) for n in d['nets']):
                    return (d['x'], d['y'], ref)
        return None
    return None


def channel_zone(ch_num):
    return CHAN_ZONES[ch_num]


def in_zone(x, y, ch_num):
    x0, y0, x1, y1 = channel_zone(ch_num)
    return (x0 - QUADRANT_TOL <= x <= x1 + QUADRANT_TOL
            and y0 - QUADRANT_TOL <= y <= y1 + QUADRANT_TOL)


def get_pad_bboxes_at(d, new_x, new_y):
    """Compute pad absolute bboxes if footprint were placed at (new_x, new_y).
    Returns list of dicts {x0, y0, x1, y1, net, layer_set}.

    Uses footprint rotation + each pad's local offset. layer_set: set of layers
    the pad appears on (F.Cu, B.Cu, or both for THT). Padded with 0.1mm
    fab-clearance margin for safer audit-equivalent collision detection.
    """
    import math
    fp = d['fp']
    rot = d.get('rot', 0)
    cos_r = math.cos(math.radians(rot))
    sin_r = math.sin(math.radians(rot))
    fp_layer = d['layer']  # 'F.Cu' or 'B.Cu'
    bboxes = []
    for pad in fp.Pads():
        # GetFPRelativePosition returns local offset (FP-relative); GetSize returns size
        pos0 = pad.GetFPRelativePosition()
        size = pad.GetSize()
        lx = pos0.x / 1e6
        ly = pos0.y / 1e6
        # Rotate local offset by footprint rotation
        rx = lx * cos_r - ly * sin_r
        ry = lx * sin_r + ly * cos_r
        # Pad absolute center if footprint were at (new_x, new_y)
        px = new_x + rx
        py = new_y + ry
        # Pad size — assume axis-aligned with footprint; for SMD pads usually so
        pw = size.x / 1e6
        ph = size.y / 1e6
        # If footprint rotated 90/270, pad bbox W/H swap (approximate for SMD)
        if rot in (90.0, 270.0):
            pw, ph = ph, pw
        m = 0.1  # fab clearance margin
        # Pad layer detection: SMD on top layer = F.Cu; SMD on bot = B.Cu;
        # THT through both. For simplicity, follow footprint layer.
        attr = pad.GetAttribute()
        if attr == pcbnew.PAD_ATTRIB_PTH or attr == pcbnew.PAD_ATTRIB_NPTH:
            layer_set = {'F.Cu', 'B.Cu'}
        else:
            layer_set = {fp_layer}
        bboxes.append({
            'x0': px - pw/2 - m, 'y0': py - ph/2 - m,
            'x1': px + pw/2 + m, 'y1': py + ph/2 + m,
            'net': pad.GetNetname(),
            'layer_set': layer_set,
        })
    return bboxes


def build_placed_pad_index(placed_set, fp_data):
    """For each placed ref, get its pad bboxes (at CURRENT footprint position)."""
    idx = {}
    for ref in placed_set:
        d = fp_data[ref]
        idx[ref] = get_pad_bboxes_at(d, d['x'], d['y'])
    return idx


def pad_bbox_collision(candidate_bboxes, placed_pad_index, ignore_refs=()):
    """Return (other_ref, layer) of first colliding placed pad, or None."""
    for other_ref, other_bboxes in placed_pad_index.items():
        if other_ref in ignore_refs:
            continue
        for cb in candidate_bboxes:
            for ob in other_bboxes:
                # Same-net pads can overlap (intentional bus/pour) — skip
                if cb['net'] and cb['net'] == ob['net']:
                    continue
                # Different layers don't collide
                if not (cb['layer_set'] & ob['layer_set']):
                    continue
                # Bbox intersection test
                if (cb['x0'] < ob['x1'] and cb['x1'] > ob['x0']
                        and cb['y0'] < ob['y1'] and cb['y1'] > ob['y0']):
                    return (other_ref, list(cb['layer_set'] & ob['layer_set'])[0])
    return None


def collision_with_placed(ref, x, y, fp_data, placed_set, min_clear=1.0):
    """Check if placing `ref` at (x,y) would collide with any already-placed footprint.
    Distance metric: use larger clearance for larger components (rough proxy for
    pad bbox)."""
    for other_ref in placed_set:
        if other_ref == ref:
            continue
        od = fp_data[other_ref]
        # Larger components need more clearance (FET 6×5mm, SO-8 5×4mm, 0402 1×0.5mm)
        other_size_class = 1.0
        ov = od.get('value', '')
        if 'BSC014N06NS' in ov:      other_size_class = 4.0   # PDFN-8 6×5mm
        elif 'AT32F421' in ov:       other_size_class = 3.5   # QFN-32 5×5mm
        elif 'DRV8300' in ov:        other_size_class = 3.0   # HVQFN-24 4×4mm
        elif 'LM393' in ov:          other_size_class = 3.0   # SOIC-8 4.9×3.9mm
        elif 'TPS54560' in ov or 'AOZ1284' in ov or 'TPS3700' in ov:
                                     other_size_class = 4.0
        elif 'TPS259' in ov or 'TLV767' in ov:
                                     other_size_class = 2.5
        elif 'INA186' in ov or 'USBLC6' in ov or '74LVC1G08' in ov or 'TL431' in ov:
                                     other_size_class = 2.0   # SC-70-6, SOT-23
        elif 'TestPoint_Pad' in str(od['fp'].GetFPID().GetLibItemName() or ''):
                                     other_size_class = 2.0
        elif 'MountingHole' in ov:   other_size_class = 3.0
        elif 'C_0603' in str(od['fp'].GetFPID().GetLibItemName() or ''):
                                     other_size_class = 1.6
        elif 'C_0805' in str(od['fp'].GetFPID().GetLibItemName() or ''):
                                     other_size_class = 2.0
        eff_clear = max(min_clear, other_size_class)
        if abs(od['x'] - x) < eff_clear and abs(od['y'] - y) < eff_clear:
            return other_ref
    return None


def in_motor_tp_zone(x, y, fp_data, margin=2.0):
    """True if (x, y) is inside motor-TP bbox + `margin` keep-out (matches
    audit_layout_compliance.py check_motor_pad_clear logic). Motor TP pad
    is 3.0mm dia → bbox 3×3mm. Audit uses fp.GetBoundingBox() which may
    include silk/courtyard giving slightly larger bbox."""
    for ref, d in fp_data.items():
        if not ref.startswith('TP'):
            continue
        v = d.get('value', '')
        if not v.startswith('MOTOR_'):
            continue
        # TP bbox approx 3.0×3.0 centered on fp position (1.5 each side)
        # +margin keep-out
        x0 = d['x'] - 1.5 - margin
        y0 = d['y'] - 1.5 - margin
        x1 = d['x'] + 1.5 + margin
        y1 = d['y'] + 1.5 + margin
        if x0 <= x <= x1 and y0 <= y <= y1:
            return ref
    return None


def in_ic_body_zone(x, y, fp_data, parent_ref=None):
    """True if (x, y) is inside an IC's pad-extent bbox (don't place passives on
    IC pads). Returns the IC ref or None.
    parent_ref is the anchor's owner — allowed to be near it (will spiral out)."""
    # IC pad-extent half-widths (from datasheet body bbox + pad fingers)
    IC_HALF_BBOX = {
        'BSC014N06NS':  (3.5, 3.0),   # PDFN-8 6×5mm → pad extent ~6.5×5
        'AT32F421':     (3.0, 3.0),   # QFN-32 5×5mm + 0.5mm pad
        'DRV8300':      (2.5, 2.5),   # HVQFN-24 4×4mm + 0.5mm
        'LM393':        (2.7, 2.3),   # SOIC-8 4.9×3.9mm
        'TPS54560':     (3.0, 3.0),   # SO-PowerPad-8 4×4mm
        'AOZ1284':      (3.5, 3.5),   # SO-8-EP 5×6mm
        'TPS3700':      (1.5, 1.0),   # SOT-23-8
        'TPS259':       (2.5, 2.0),
        'TLV767':       (1.5, 1.5),
        'INA186':       (1.2, 1.2),
        'USBLC6':       (1.2, 1.2),
        'ACS770ECB':    (10.0, 6.8),  # 13.6mm tall × 27mm wide @ rot=90 → swap
        'SM08B':        (4.0, 1.8),   # JST SH 8-pin connector
        'BM06B':        (3.0, 1.8),
        'BATT_PAD':     (2.5, 2.5),
        '74LVC1G08':    (0.9, 1.0),   # SOT-353
        'TL431':        (0.9, 1.0),   # SOT-23
    }
    for ref, d in fp_data.items():
        if ref == parent_ref:
            continue
        v = d.get('value', '')
        hb = None
        for key, dim in IC_HALF_BBOX.items():
            if key in v:
                hb = dim; break
        if hb is None:
            continue
        hx, hy = hb
        # Account for IC rotation — rough: if rot is 90/270, swap
        rot = d.get('rot', 0)
        if rot in (90.0, 270.0):
            hx, hy = hy, hx
        if (d['x'] - hx <= x <= d['x'] + hx
                and d['y'] - hy <= y <= d['y'] + hy):
            return ref
    return None


def spiral_positions(cx, cy, max_dist):
    """Yield (x, y) positions on a 0.5mm spiral from (cx, cy) up to max_dist."""
    step = 0.5
    yield (cx, cy)
    for r_steps in range(1, int(max_dist / step) + 2):
        r = r_steps * step
        # 12 angles per ring
        n_pts = max(8, r_steps * 6)
        for i in range(n_pts):
            import math
            theta = 2 * math.pi * i / n_pts
            yield (cx + r * math.cos(theta), cy + r * math.sin(theta))


def is_per_channel_passive(ref, d):
    """True if ref is a passive (R/C/D/L/TH/TP) AND has a *_CH<n> net (per-ch identity)."""
    if not ref or not ref[0] in ('R', 'C', 'D', 'L'):
        return False
    if not ref[1:].isdigit():
        return False
    # Check any net is channel-tagged
    return any(re.search(r'_CH\d+(?:_|$)', n) for n in d['nets'])


def place_one(ref, d, anchor_xy, max_dist, ch_num, fp_data, placed_set, pad_idx):
    """Try to place `ref` near anchor with collision avoidance + zone check.
    Returns final (x, y) on success, or None on failure.

    pad_idx: incremental pad-bbox index for placed components."""
    ax, ay, parent_ref = anchor_xy
    # Component-size-aware clearance: own size also matters
    ov = d.get('value', '')
    own_clear = 1.5
    fp_lib = str(d['fp'].GetFPID().GetLibItemName() or '')
    if 'R_0402' in fp_lib or 'C_0402' in fp_lib:
        own_clear = 2.0
    elif 'R_0603' in fp_lib or 'C_0603' in fp_lib:
        own_clear = 2.3
    elif 'C_0805' in fp_lib:
        own_clear = 2.8
    elif 'SOD-123' in fp_lib or 'SOD-323' in fp_lib:
        own_clear = 2.2
    elif 'SMA' in fp_lib or 'SMB' in fp_lib:
        own_clear = 3.5
    elif 'LED_0603' in fp_lib or 'LED_0402' in fp_lib:
        own_clear = 2.0

    for x, y in spiral_positions(ax, ay, max_dist + 2.0):
        if not (BOARD_MIN <= x <= BOARD_MAX and BOARD_MIN <= y <= BOARD_MAX):
            continue
        if not in_zone(x, y, ch_num):
            continue
        # Motor-TP keep-out (R20 audit gate) — uses bbox+margin to match audit
        # Audit uses MOTOR_PAD_KEEPOUT=2.0; we use 2.5 for safety margin
        if in_motor_tp_zone(x, y, fp_data, margin=2.5):
            continue
        # IC body bbox keep-out — don't place inside IC pad extent
        if in_ic_body_zone(x, y, fp_data, parent_ref=parent_ref):
            continue
        dist = ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5
        if dist > max_dist + 2.0:
            continue
        # Primary check: pad-bbox collision against placed pad index (canonical
        # per audit). Computes candidate pad bboxes at (x,y) and intersects with
        # all placed pads on same layer + different net.
        candidate_bboxes = get_pad_bboxes_at(d, x, y)
        col = pad_bbox_collision(candidate_bboxes, pad_idx, ignore_refs=(ref,))
        if col is None:
            return (x, y)
    return None


def update_pad_idx(ref, d, x, y, pad_idx):
    """Update the pad index after placing `ref` at (x, y)."""
    pad_idx[ref] = get_pad_bboxes_at(d, x, y)


def apply_position(ref, fp, x, y, layer=None, rot=None):
    fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
    if rot is not None:
        fp.SetOrientationDegrees(rot)


def mirror_transform(ch_num, x, y, rot):
    """Apply locked geometric transform from CH1 to CH2/3/4."""
    if ch_num == 2:
        return (100.0 - x, y, (rot + 180) % 360)
    if ch_num == 3:
        return (100.0 - x, 100.0 - y, rot)
    if ch_num == 4:
        return (x, 100.0 - y, (rot + 180) % 360)
    raise ValueError(f"bad ch {ch_num}")


def main():
    board, fp_data = load_board_data()
    print(f"Loaded {len(fp_data)} footprints from PCB")

    # 1) Identify per-channel passives, group by channel
    per_ch_refs = defaultdict(list)
    skipped_no_role = []
    for ref, d in fp_data.items():
        if not is_per_channel_passive(ref, d):
            continue
        role, anchor, max_dist, ch = classify_role(d['nets'])
        if not role:
            skipped_no_role.append((ref, d['nets']))
            continue
        if role == 'skip-swd':
            continue
        per_ch_refs[ch].append((ref, role, anchor, max_dist))
    print(f"\nClassified {sum(len(v) for v in per_ch_refs.values())} per-channel passives")
    for ch in sorted(per_ch_refs):
        print(f"  CH{ch}: {len(per_ch_refs[ch])} passives")
    if skipped_no_role:
        print(f"  WARN: {len(skipped_no_role)} unclassified per-channel refs")
        for r, n in skipped_no_role[:5]:
            print(f"    {r}: nets={sorted(n)[:3]}")

    # 2) Track placed refs (start with everything that's currently on-board OR is
    # an explicit IC anchor we never move). For CH1 layout, we start from current
    # IC placements + all S0/S1/S2/S3/S5/S6 components.
    on_board = set()
    for ref, d in fp_data.items():
        if BOARD_MIN <= d['x'] <= BOARD_MAX and BOARD_MIN <= d['y'] <= BOARD_MAX:
            on_board.add(ref)

    # Move all per-channel passives to "unplaced" status — they'll be re-anchored.
    # Strategy: don't actually move them off-board (no need), just don't count them
    # in collision check until we re-place them.
    per_ch_set = {r for ch in per_ch_refs for (r, *_) in per_ch_refs[ch]}
    placed_set = on_board - per_ch_set

    # Build initial pad-bbox index for placed (non-per-ch) components
    print(f"Building pad-bbox index for {len(placed_set)} placed components...")
    pad_idx = build_placed_pad_index(placed_set, fp_data)

    # 3) CH1 placement (role-driven) — record role→(x, y, layer, rot) for mirror
    ch1_role_pos = {}  # role_key → (ref, x, y, layer, rot)
    ch1_failed = []
    print("\n=== CH1 placement ===")
    for ref, role, anchor, max_dist in per_ch_refs.get(1, []):
        d = fp_data[ref]
        anchor_xy = find_anchor_pad(anchor, 1, fp_data) if anchor else None
        if not anchor_xy:
            ch1_failed.append((ref, role, 'NO_ANCHOR'))
            continue
        pos = place_one(ref, d, anchor_xy, max_dist, 1, fp_data, placed_set, pad_idx)
        if not pos:
            ch1_failed.append((ref, role, 'NO_FREE_SLOT'))
            continue
        x, y = pos
        d['x'], d['y'] = x, y
        apply_position(ref, d['fp'], x, y)
        placed_set.add(ref)
        update_pad_idx(ref, d, x, y, pad_idx)
        ch1_role_pos[role] = (ref, x, y, d['layer'], d['rot'])

    print(f"CH1 placed: {len(ch1_role_pos)}, failed: {len(ch1_failed)}")
    for r, role, reason in ch1_failed[:20]:
        print(f"  FAIL {r} (role={role}): {reason}")

    # 4) CH2/3/4 — mirror CH1 by role
    for ch in (2, 3, 4):
        print(f"\n=== CH{ch} mirror placement ===")
        ch_n = 0
        ch_failed = []
        for ref, role, anchor, max_dist in per_ch_refs.get(ch, []):
            if role not in ch1_role_pos:
                # CH1 didn't have this role placed — try direct placement instead
                d = fp_data[ref]
                anchor_xy = find_anchor_pad(anchor, ch, fp_data) if anchor else None
                if not anchor_xy:
                    ch_failed.append((ref, role, 'NO_CH1_MIRROR_NO_ANCHOR'))
                    continue
                pos = place_one(ref, d, anchor_xy, max_dist, ch, fp_data, placed_set, pad_idx)
                if not pos:
                    ch_failed.append((ref, role, 'NO_FREE_SLOT'))
                    continue
                x, y = pos
            else:
                _, x1, y1, layer1, rot1 = ch1_role_pos[role]
                x, y, rot = mirror_transform(ch, x1, y1, rot1)
                # Pad-bbox collision check; if conflicts, spiral nearby
                d = fp_data[ref]
                cb = get_pad_bboxes_at(d, x, y)
                col = pad_bbox_collision(cb, pad_idx, ignore_refs=(ref,))
                if col is not None:
                    pos = place_one(ref, d, (x, y, 'mirror'), 4.0, ch, fp_data, placed_set, pad_idx)
                    if not pos:
                        ch_failed.append((ref, role, f'MIRROR_COL_{col[0]}_NO_ALT'))
                        continue
                    x, y = pos
            d = fp_data[ref]
            d['x'], d['y'] = x, y
            apply_position(ref, d['fp'], x, y)
            placed_set.add(ref)
            update_pad_idx(ref, d, x, y, pad_idx)
            ch_n += 1
        print(f"CH{ch} placed: {ch_n}, failed: {len(ch_failed)}")
        for r, role, reason in ch_failed[:10]:
            print(f"  FAIL {r} (role={role}): {reason}")

    board.Save(str(PCB))
    print(f"\nSaved {PCB}")
    print(f"Final placed_set: {len(placed_set)} / {len(fp_data)} footprints")


if __name__ == "__main__":
    main()
