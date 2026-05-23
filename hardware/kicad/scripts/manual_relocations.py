#!/usr/bin/env python3
"""manual_relocations.py — Sai-catch #12 Step 3 fix record (Master 2026-05-24).

Audit-trail of all relocations applied by fix_inside_body_targeted.py to clear
COMPONENT-INSIDE-BODY violations on pcbai_fpv4in1 (PR-placement-extensive-verify).

Format: {ref: {'from': (x, y), 'to': (x, y), 'reason': '...'}}

Reversible: subtract delta from each entry to restore pre-fix position.

Verification:
  - Initial inside-body invaders:      36 (after gate #15 + silk-overdraw exemption)
  - Fixes applied:                     33
  - INVESTIGATE FURTHER (stuck):       3 (C51, C115, C43)
  - Audit regressions:                 3 SILK-ON-PAD (LARGE-component silk text
    landed over moved-passive pad; not pad-overlap)
  - Net FAIL count: 30 → 16

Codified per [[feedback-anchor-outside-parent-body]] +
[[feedback-host-silk-overdraw-exempt]].
"""

# (ref, from_xy, to_xy, host, reason)
RELOCATIONS = [
    ('D78',  (28.68, 11.15), (28.20, 11.28), 'J33', 'shift -0.5,+0.1 — clear MCU body'),
    ('L8',   (64.50, 83.00), (64.76, 82.03), 'J23', 'shift +0.3,-1.0 — clear MCU body'),
    ('L6',   (35.50, 83.00), (36.75, 85.17), 'J18', 'shift +1.3,+2.2 — clear MCU body (caused 2 silk-on-pad regressions; INVESTIGATE)'),
    ('R30',  (84.00,  8.00), (80.86,  7.16), 'U1',  'shift -3.1,-0.8 — clear Hall body'),
    ('C93',  (72.66, 92.56), (72.92, 93.53), 'C33', 'shift +0.3,+1.0 — clear bulk cap'),
    ('C92',  (68.94, 91.65), (67.01, 92.17), 'C33', 'shift -1.9,+0.5'),
    ('C42',  (82.70,  9.00), (82.70, 12.25), 'D7',  'shift +0.0,+3.2 — clear SMA diode'),
    ('C152', (50.16, 46.18), (49.68, 46.05), 'U2',  'shift -0.5,-0.1'),
    ('C49',  (45.52, 85.48), (45.19, 86.69), 'U3',  'shift -0.3,+1.2 — stay within decoup 3mm'),
    ('R40',  (54.50, 86.00), (52.98, 86.88), 'U5',  'shift -1.5,+0.9'),
    ('C157', (65.30, 45.50), (66.17, 46.00), 'C4',  'shift +0.9,+0.5'),
    ('C109', (54.65, 13.35), (55.08, 13.10), 'U7',  'shift +0.4,-0.3 — preserve U7 decoupling'),
    ('R41',  (29.55, 83.56), (28.90, 81.15), 'J18', 'shift -0.6,-2.4 (caused 1 silk-on-pad regression; INVESTIGATE)'),
    ('R66',  (42.50, 16.00), (40.33, 16.58), 'U9',  'shift -2.2,+0.6'),
    ('D48',  (70.06, 93.28), (70.49, 93.53), 'C33', 'shift +0.4,+0.2'),
    ('R116', (75.00, 87.50), (76.00, 87.50), 'C33', 'shift +1.0,+0.0'),
    ('C122', (14.00, 82.00), (13.87, 81.52), 'D32', 'shift -0.1,-0.5'),
    ('C20',  ( 9.50, 26.00), ( 8.66, 29.14), 'D74', 'shift -0.8,+3.1 (non-decoup, allow larger move)'),
    ('R12',  (57.50, 74.00), (57.31, 74.72), 'J4',  'shift -0.2,+0.7'),
    ('D82',  (37.75, 35.20), (35.81, 37.14), 'C1',  'shift -1.9,+1.9 — clear bulk cap C1'),
    ('C94',  (74.00, 91.50), (75.25, 93.67), 'C33', 'shift +1.3,+2.2'),
    ('TP31', (68.71, 41.29), (68.58, 40.81), 'Q18', 'shift -0.1,-0.5'),
    ('TP38', (30.70, 41.25), (30.22, 41.12), 'Q24', 'shift -0.5,-0.1'),
    ('R113', (72.42, 14.58), (70.92, 17.18), 'R131','shift -1.5,+2.6 — clear 2512 shunt R131'),
    ('R71',  (44.91, 87.02), (45.23, 88.22), 'L2',  'shift +0.3,+1.2'),
    ('R151', (30.26, 17.85), (31.77, 16.98), 'Q28', 'shift +1.5,-0.9'),
    ('R111', (65.46, 79.25), (65.33, 79.74), 'Q16', 'shift -0.1,+0.5'),
    ('TH1',  (45.00, 82.00), (45.00, 80.75), 'L2',  'shift -0.0,-1.2'),
    ('R70',  (50.30, 81.81), (50.04, 80.84), 'L2',  'shift -0.3,-1.0'),
    ('R73',  (34.54, 78.52), (34.97, 78.77), 'Q10', 'shift +0.4,+0.2'),
    ('TP24', (68.71, 58.71), (69.19, 58.84), 'Q12', 'shift +0.5,+0.1'),
    ('R105', (60.00, 90.05), (60.43, 90.30), 'D12', 'shift +0.4,+0.2'),
    ('R112', (62.80, 65.16), (62.18, 64.07), 'L3',  'shift -0.6,-1.1'),
]

INVESTIGATE_FURTHER = [
    ('C51', 'U5', 'SOIC-8 decoupling cap stays within 3mm + body bbox edge; no clear edge position'),
    ('C115', 'D41', 'SMA diode (4×3mm), C115 placed centrally; needs Sai-eye placement'),
    ('C43', 'U1', 'Hall decoupling cap, U1 5×5 body, must stay within 3mm; needs re-anchor to alt VDD pin'),
]

REGRESSIONS_FROM_FIX = [
    ('U3 silk on L6.pad1',
     'L6 moved to (36.75, 85.17); U3 refdes silk text falls on L6 pad. '
     'U3 not silk-hide-eligible. Fix options: hide U3 silk, shift L6 farther, '
     'or move U3 refdes text in library.'),
    ('FID3 silk on L6.pad2', 'Same root cause as above — fiducial silk overlap.'),
    ('J13 silk on R41.pad1',
     'R41 moved to (28.90, 81.15); J13 connector refdes silk on R41 pad. '
     'Similar fix options.'),
]


if __name__ == '__main__':
    print(f"Relocations applied: {len(RELOCATIONS)}")
    print(f"INVESTIGATE FURTHER: {len(INVESTIGATE_FURTHER)}")
    print(f"REGRESSIONS FROM FIX (cosmetic, fab-marginal): {len(REGRESSIONS_FROM_FIX)}")
