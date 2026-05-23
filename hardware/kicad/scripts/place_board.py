"""Phase 4 subsystem-aware placement (R6 motor-pad-anchored architecture).

Per docs/PHASE4_SUBSYSTEMS.md (Phase 4-subsystem-spec, master Task #48,
landed in PR #31). Replaces the previous R1 center-cluster placement which
had 1301 same-layer body-bbox defects from grid-stacking bugs.

Sub-phase ordering (one PR per subsystem per spec §5):
  S1 battery input — implemented here
  S2 bulk caps — Phase 4-place-bulk-caps (next)
  S3 supervisor + Hall — Phase 4-place-supervisor-hall
  S4 channel template (×4) — Phase 4-place-channel-template / -channels-x4
  S5 BEC — Phase 4-place-bec
  S6 FC + AUX — Phase 4-place-connectors
  S7 Edge.Cuts + mount holes — already in setup_board.py

Each sub-phase places ONLY its assigned components. Other 570+ components
remain at kinet2pcb-default positions in this phase; subsequent sub-phases
place them.

This file's structure:
  ALL_PLACERS: list of (name, function) tuples. Each function takes the
  list of footprints + the placements dict; appends ref→(x, y, layer, rot)
  entries for its subsystem only.

  main() runs all enabled placers in order.

CLI:
  python3 place_board.py                — run all enabled subsystem placers
  python3 place_board.py --only=S1      — run only the named subsystem
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")

# ────────────────────────────────────────────────────────────────────
# S1: Battery input subsystem (per docs/PHASE4_SUBSYSTEMS.md §S1)
# Zone: X=20-80, Y=0-13 (bottom edge band, but RP FET 2×2 cluster spills
# to y=18 due to SuperSO8 5×6 body + minimum-clearance requirement;
# acceptable since adjacent S2 bulk-cap zone (Y=13-42) is empty at PR-time).
# ────────────────────────────────────────────────────────────────────
S1_POSITIONS = {
    # PR-S1 2026-05-23: §S1 battery input — Y=0-13 zone, X-symmetric about X=50.
    'J1':         (50.0,  4.0, 'F.Cu',  0.0),   # XT30 BATT_PAD (center primary input)
    # NTC inrush limiters (MF72_5D25) — west/east of FET cluster, mirror about X=50
    # NTCs MF72_5D25 (TH, 5mm lead pitch). KEEP MASTER baseline (22, 7.5)/(78, 7.5)
    # rotation 0. This accepts the 2 master-baseline R1↔Q1 pad overlaps (inside
    # §S1 zone, existed before PR-S1 — not introduced by this PR per master gate
    # "no NEW overlaps from this PR"). Rotation/shift attempts all introduced
    # NEW outside-§S1 overlaps (R1↔H4/TP15 or R1↔R83/TH4). Per master tradeoff
    # accept master-state for R1/R2 — Q1↔R1 will be re-examined in PR-CH1 with
    # CH1 FET reshuffle.
    'R1':         (22.0,  7.5, 'F.Cu',  0.0),
    'R2':         (78.0,  7.5, 'F.Cu',  0.0),
    # 4× BSC014N06NS rev-pol FETs, parallel; symmetric about X=50
    'Q1':         (30.0,  7.5, 'B.Cu',  0.0),
    'Q2':         (45.0,  7.5, 'B.Cu',  0.0),
    'Q3':         (55.0,  7.5, 'B.Cu',  0.0),
    'Q4':         (70.0,  7.5, 'B.Cu',  0.0),
    # Rev-pol FET gate cluster — R3 (10K pull) + D2 (12V Zener clamp) ≤5mm
    # from nearest FET gate per R23. R3 anchored to Q1 (4mm); D2 anchored to Q4 (4mm).
    'R3':         (32.0, 11.0, 'F.Cu',  0.0),   # GATE_RP 10K pull, anchored to Q1
    'D2':         (68.0, 11.0, 'F.Cu',  0.0),   # 12V Zener, anchored to Q4 (symmetric)
    # D3/D4/R4/R5 status LEDs moved to §S6 in PR-S6 (Task #72).
    # D26 SMBJ33A — net is MOTOR_A_CH1, this is CH1 motor TVS (mis-labeled by historical
    # placement). Leave at master placement (15, 5) — moved to CH1 in PR-CH1.
    'D26':        (15.0,  5.0, 'B.Cu',  0.0),
}
S1_EXPECTED_VALUES = {
    'J1':  'BATT_PAD',
    'D26': 'SMBJ33A',
    'R1':  'MF72_5D25',  'R2':  'MF72_5D25',
    'Q1':  'BSC014N06NS', 'Q2':  'BSC014N06NS', 'Q3':  'BSC014N06NS', 'Q4':  'BSC014N06NS',
    'R3':  '10K',
    'D2':  '12V',
}


def place_battery_input(fps_by_ref, placements):
    """S1 — battery input subsystem placement (docs/PHASE4_SUBSYSTEMS.md §S1)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, expected_value in S1_EXPECTED_VALUES.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        actual_value = fp['value']
        if expected_value not in actual_value:
            mismatched.append((ref, expected_value, actual_value))
            continue
        x, y, layer, rot = S1_POSITIONS[ref]
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S1 components missing in netlist: {missing}")
    if mismatched:
        print(f"  WARN: S1 ref/value mismatch (sanity-check failed):")
        for ref, exp, act in mismatched:
            print(f"    {ref}: expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S2: Bulk cap bank (docs/PHASE4_SUBSYSTEMS.md §S2, amended zone Y=20-42)
# CBULK1-4 (C1-C4) in 2×2 linear bank at central spine X=42-58, Y=25-35.
# NOTE: master spec §S2 also lists 8× ceramic decouplers (4× 100nF + 4× 10nF).
# These are NOT present in the netlist — flagged as Phase 5 SKiDL follow-up.
# ────────────────────────────────────────────────────────────────────
S2_POSITIONS = {
    # CP_Elec_10x14.3 actual bbox = 13.59×11.05 mm. Master 2026-05-22 stage-3
    # amendment: Hall (S3 U1) placed vertical at (50, 45) 0° rot → body bbox
    # (42.1, 20.3)..(61.7, 46.0). Initial outward shift: C1/C3 at x=30, C2/C4
    # at x=70 cleared Hall body but C3/C4 bbox y_max=45.5 intruded into S4
    # channel lower strip (y=42-58), blocking channel template placement
    # (PR-A1 stage from Option A adjudication 2026-05-22).
    # Stage-4 amendment: C3 → (25, 40), C4 → (75, 40). Pushes outward by 5mm
    # so C3/C4 bbox falls outside NW/NE channel-zone inner edges (X=39/61).
    # C3 bbox now (18.1, 34.5)..(31.7, 45.5) — x_max=31.7 well under channel
    # NW inner edge x=39. C4 bbox (68.1, 34.5)..(81.9, 45.5) — x_min=68.1
    # well over channel NE inner edge x=61. Cleared for S4 channel placement.
    # C1/C2 at y=24 left at (30, 24)/(70, 24) — clear of S4 (S4 starts y=42).
    # PR-S2 2026-05-23: 2×2 mirror grid about (50, 36) per master locked spec.
    # C1 was (22, 28), C2 was (85, 28) — not X-symmetric. Fixed to (25, 28)/(75, 28).
    'C1': (25.0, 28.0, 'F.Cu', 0.0),
    'C2': (75.0, 28.0, 'F.Cu', 0.0),
    'C3': (25.0, 44.0, 'F.Cu', 0.0),
    'C4': (75.0, 44.0, 'F.Cu', 0.0),
}
S2_EXPECTED_VALUE = "EEHZS1V471P"


def place_bulk_caps(fps_by_ref, placements):
    """S2 — bulk cap bank placement (docs/PHASE4_SUBSYSTEMS.md §S2)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S2_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        if S2_EXPECTED_VALUE not in fp['value']:
            mismatched.append((ref, S2_EXPECTED_VALUE, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S2 components missing in netlist: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S2 ref {ref} value mismatch — expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S3: Supervisor + Hall sensor (docs/PHASE4_SUBSYSTEMS.md §S3)
# Central spine middle, zone X=42-58, Y=42-58.
# Components:
#   J11 TPS3700 supervisor (Conn_01x08 SOT-23-8 placeholder; Phase 5b SKiDL
#     swap to real TPS3700 symbol)
#   U1 ACS770ECB-200B Hall sensor (Allegro_CB_PFF; large body 13.6×27 mm —
#     rotated 90° to fit horizontally in middle band; primary leads carry +VMOTOR)
#   R19 348K + R20 23K2: VMOTOR OVP/UVP divider (27V trip / 18V trip via 0.0625 ratio)
#   C41 100nF: 10 ms inrush delay cap (CT pin)
#   R21 10K: PG_VMOTOR open-drain pull-up to +3V3
#   R30 0R: Hall VCC bridge (V5 → HALL_VCC, optional filter location)
#   C42 1uF, C43 100nF: Hall VCC bypass
#   R31 10K + R32 20K: Hall VOUT divider 5V → 3.3V (FC-ADC compatible)
#   C44 10nF: Hall output post-divider noise filter
#   R33 0Ω 2512, R34 0Ω 2512: VMOTOR primary copper-bridge jumpers
#     (placement-layout aids; physical realization is Phase 5b 3 oz copper bar
#     through Hall primary)
# Total: 14 components (10 in immediate zone + 2 VMOTOR jumpers + supervisor + Hall)
# ────────────────────────────────────────────────────────────────────
S3_POSITIONS = {
    # Hall vertical orientation (0° rot) per master 2026-05-22 stage-3 amendment.
    # Symmetric placement at central spine middle Y=45 — all 4 channels are
    # equidistant ~30 mm from Hall (premium-ESC reference for thermal symmetry).
    # Body bbox at 0° rot = (42.1, 20.3)..(61.7, 46.0); pad 4 (primary current)
    # at (52.96, 22.97) extends north. Spine widened to X=39-61 per master
    # amendment (channel inner edges shifted to X=39/61) — Hall 19.65mm fits.
    'U1':  (50.0, 45.0, 'F.Cu', 0.0),
    # Supervisor cluster — SOUTH of Hall body in central spine y=50-59
    # (Hall body occupies y=20.3-46; spine middle y=46-58 is clear).
    'J11': (50.0, 55.0, 'F.Cu', 0.0),    # TPS3700 supervisor SOT-23-8
    'R19': (45.0, 53.0, 'F.Cu', 0.0),    # 348K OVP/UVP divider top
    'R20': (55.0, 53.0, 'F.Cu', 0.0),    # 23K2 OVP/UVP divider bot
    'C41': (50.0, 59.0, 'F.Cu', 0.0),    # 100nF 10ms inrush-delay cap
    'R21': (45.0, 57.0, 'F.Cu', 0.0),    # 10K PG_VMOTOR pullup
    # Hall VCC bridge + bypass — east of Hall pad 2/3 signal pads at y=45
    # Pad 2 V_CC @ (51.91, 45), pad 3 GND @ (53.82, 45). Decouplers immediately east.
    'R30': (54.0, 47.5, 'F.Cu', 0.0),    # 0Ω V5 → HALL_VCC bridge
    'C42': (56.0, 47.5, 'F.Cu', 0.0),    # 1uF bypass
    'C43': (58.0, 47.5, 'F.Cu', 0.0),    # 100nF bypass
    # Hall output divider + filter — west of Hall pad 1 (signal output @ (50, 45))
    'R31': (45.0, 47.5, 'F.Cu', 0.0),    # 10K div top (5V→3.3V)
    'R32': (45.0, 49.5, 'F.Cu', 0.0),    # 20K div bot
    'C44': (47.0, 49.5, 'F.Cu', 0.0),    # 10nF output filter
    # VMOTOR copper-bridge jumpers (0Ω 2512) on B.Cu — Hall primary path
    # Hall vertical at (50, 45) 0° rot → pad 4 (primary IN) at (52.96, 22.97).
    # Pad 5 (primary OUT) at south end of body near y=46.
    # Bridges placed on B.Cu to backside-route +VMOTOR via PTH to primary pads.
    'R33': (50.0, 25.0, 'B.Cu', 0.0),    # +VMOTOR → Hall pad 4 (north end, IP+)
    'R34': (50.0, 47.0, 'B.Cu', 0.0),    # Hall pad 5 bridge — moved from spine pocket (50, 65) per PR-A2 to free S5 BEC pocket Y=58-72
}
S3_EXPECTED_VALUES = {
    'U1':  'ACS770ECB',
    'J11': 'TPS3700',
    'R19': '348K',
    'R20': '23K2',
    'C41': '100nF',
    'R21': '10K',
    'R30': '0R',
    'C42': '1uF',
    'C43': '100nF',
    'R31': '10K',
    'R32': '20K',
    'C44': '10nF',
    'R33': '0R',
    'R34': '0R',
}


def place_supervisor_hall(fps_by_ref, placements):
    """S3 — supervisor + Hall sensor placement (docs/PHASE4_SUBSYSTEMS.md §S3)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S3_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        expected = S3_EXPECTED_VALUES[ref]
        if expected not in fp['value']:
            mismatched.append((ref, expected, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S3 components missing in netlist: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S3 ref {ref} value mismatch — expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S6: FC + AUX connectors (docs/PHASE4_SUBSYSTEMS.md §S6)
# Top edge zone Y=72-85 (avoid mount holes H3 at (5,80) and H4 at (95,80)
# with ≥3mm clearance — keep S6 inside x=10..90).
# Master reorder 2026-05-22: S6 before S5 (low-EMC tier-2 anchor before
# introducing BEC tier-3 switching noise).
# Components in netlist:
#   J12 BM06B-SRSS-TB AUX 6-pin (Hall + NTC + AUX_GPIO)
#   J14 SM08B-SRSS-TB FC 8-pin (DShot×4 + TLM + VBAT_SENSE + CURR + GND)
#   J15/J16/J17 USBLC6-2SC6 ESD arrays (3 chips covering 4×DShot + TLM + spare)
#   R36 100K, R37 14K VBAT_SENSE divider (8.143:1 ratio)
#   C49 100nF VBAT filter cap
# Total: 8 components (LEDs come from S1/S3 already; master "4 per-channel
# kill LEDs" are part of S4 channel template, not S6 — honest deviation flag)
# ────────────────────────────────────────────────────────────────────
S6_POSITIONS = {
    # PR-S6 2026-05-23: master baseline kept for connectors/USBLC6/VBAT divider.
    'J12': (15.0, 90.0, 'F.Cu',   0.0),    # AUX BM06B-SRSS-TB west top
    'J14': (50.0, 90.0, 'F.Cu',   0.0),    # FC SM08B-SRSS-TB central top (X=50 symmetric)
    'J15': (40.0, 85.0, 'F.Cu',   0.0),    # USBLC6 ESD ch1+ch2 DShot
    'J16': (60.0, 85.0, 'F.Cu',   0.0),    # USBLC6 ESD ch3+ch4 DShot (mirror of J15 about X=50)
    'J17': (75.0, 85.0, 'F.Cu',   0.0),    # USBLC6 ESD TLM + spare
    'R36': (47.0, 86.0, 'F.Cu',   0.0),    # VBAT divider top 100K
    'R37': (47.0, 84.0, 'F.Cu',   0.0),    # VBAT divider bot 14K
    'C49': (45.0, 84.0, 'F.Cu',   0.0),    # VBAT filter 100nF
    # Status LED pairs in §S6 north strip Y=96 — clear zone (only TP16/TP7 at Y=95
    # from PR-S1, no overlap). D3+R4 at NW (X=5/8), D4+R5 at NE (X=95/92) mirror.
    'D3':  (5.0, 96.0, 'F.Cu',  0.0),     # GREEN_PWR LED (NW)
    'R4':  (8.0, 96.0, 'F.Cu',  0.0),     # D3 limit-R (3mm pair pitch)
    'D4':  (95.0, 96.0, 'F.Cu',  0.0),    # RED_RPOL LED (NE mirror_X)
    'R5':  (92.0, 96.0, 'F.Cu',  0.0),    # D4 limit-R (mirror)
}
S6_EXPECTED_VALUES = {
    'J12': 'BM06B',
    'J14': 'SM08B',
    'J15': 'USBLC6', 'J16': 'USBLC6', 'J17': 'USBLC6',
    'R36': '100K', 'R37': '14K', 'C49': '100nF',
    'D3':  'GREEN_PWR', 'D4':  'RED_RPOL',
    'R4':  '5K1', 'R5':  '5K1',
}


def place_connectors(fps_by_ref, placements):
    """S6 — FC + AUX connectors placement (docs/PHASE4_SUBSYSTEMS.md §S6)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S6_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        expected = S6_EXPECTED_VALUES[ref]
        if expected not in fp['value']:
            mismatched.append((ref, expected, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S6 components missing in netlist: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S6 ref {ref} value mismatch — expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S5: BEC subsystem (docs/PHASE4_SUBSYSTEMS.md §S5)
# 5 buck rails + LDO + V5_PI5 supervisor. Master 2026-05-22 dispatch
# (Task #54): zone allocation flexible; worker's call to distribute
# bucks for thermal separation from channel FETs.
#
# Strategy: NW + NE side-band strip at Y=58-72 (between S3 Hall body
# y=20-46 and S6 connectors y=72-85). Buck #5 V9_VTX2 isolated from
# Buck #4 V9_VTX1 by placing centrally between S3 supervisor cluster
# (y≤59) and S6 connectors (y≥72). LDO + supervisor IC clustered
# next to Buck #5 in central spine pocket.
#
# Components (17 — core BEC; eFuses/polyfuses/TVS/FB-resistors deferred
# to subsequent passes where they cluster around the buck + load,
# matching master's 15-25 estimate):
#   J2 V5_FC TPS54560 + L1 4.7uH + D5 SS54
#   J3 V5_PI5 TPS54560 + L2 4.7uH + D6 SS54
#   J4 V5_AI TPS54560 + L3 8.2uH + D7 SS54
#   J5 V9_VTX1 AOZ1284PI + L4 10uH + D8 SS54
#   J6 V9_VTX2 AOZ1284PI + L5 10uH + D9 SS54 (isolated from #4)
#   J13 LDO TLV76733DRVR (V5_FC → V3V3)
#   J10 V5_PI5 supervisor (PG_RPI to FC)
# ────────────────────────────────────────────────────────────────────
S5_POSITIONS = {
    # ── Bucks 1-4 + inductors + LDO RELOCATED to SPINE POCKET (PR-A2 Option A) ──
    # 4 bucks F.Cu in 2×2 arrangement; 4 inductors B.Cu underneath (stack via layers).
    # Buck #1 V5_FC + L1
    'J2':  (43.0, 72.0, 'F.Cu', 0.0),
    'L1':  (43.0, 72.0, 'B.Cu', 0.0),
    # Buck #2 V5_PI5 + L2
    'J3':  (43.0, 80.0, 'F.Cu', 0.0),
    'L2':  (43.0, 80.0, 'B.Cu', 0.0),
    # Buck #3 V5_AI + L3
    'J4':  (57.0, 72.0, 'F.Cu', 0.0),
    'L3':  (57.0, 72.0, 'B.Cu', 0.0),
    # Buck #4 V9_VTX1 + L4
    'J5':  (57.0, 80.0, 'F.Cu', 0.0),
    'L4':  (57.0, 80.0, 'B.Cu', 0.0),
    # FB resistors — 0402 in top strip Y=70-72 lateral area (outside spine pocket bucks)
    'R6':  (24.0, 80.0, 'F.Cu', 0.0),    # V5_FC FB top 52K3
    'R7':  (24.0, 82.0, 'F.Cu', 0.0),    # V5_FC FB bot 10K
    'R8':  (28.0, 80.0, 'F.Cu', 0.0),    # V5_PI5 FB top 52K3
    'R9':  (28.0, 82.0, 'F.Cu', 0.0),    # V5_PI5 FB bot 10K
    'R10': (70.0, 80.0, 'F.Cu', 0.0),    # V5_AI FB top 52K3
    'R11': (70.0, 82.0, 'F.Cu', 0.0),    # V5_AI FB bot 10K
    'R12': (76.0, 80.0, 'F.Cu', 0.0),    # V9_VTX1 FB top 102K
    'R13': (76.0, 82.0, 'F.Cu', 0.0),    # V9_VTX1 FB bot 10K
    # Boot caps — 0402 in top strip Y=76 (close to S6 BAT/USBLC6 row but between gaps)
    'C7':  (30.0, 86.0, 'F.Cu', 0.0),    # Buck 1 boot 100nF
    'C11': (52.0, 86.0, 'F.Cu', 0.0),    # Buck 2 boot
    'C14': (65.0, 86.0, 'F.Cu', 0.0),    # Buck 3 boot
    'C17': (80.0, 86.0, 'F.Cu', 0.0),    # Buck 4 boot
    # ── INPUT-side strip Y=12-19 between S1 components (per master amendment 2026-05-23) ──
    # 4× Schottky D5-D8 — between S1 Q3/Q4 FET columns + east of R2 NTC
    'D5':  (48.0, 14.0, 'F.Cu', 0.0),    # V5_FC catch diode SS54
    'D6':  (48.0, 18.0, 'F.Cu', 0.0),    # V5_PI5 catch diode SS54
    'D7':  (82.0, 14.0, 'F.Cu', 0.0),    # V5_AI catch diode
    'D8':  (82.0, 18.0, 'F.Cu', 0.0),    # V9_VTX1 catch diode
    # 3× eFuses + 1× polyfuse — input protection per rail
    'J7':  (15.0, 14.0, 'F.Cu', 0.0),    # V5_FC eFuse TPS259251
    'J8':  (22.0, 16.0, 'F.Cu', 0.0),    # V5_PI5 eFuse (moved east to clear J6 V9_VTX2 buck at (12, 22))
    'J9':  (90.0, 14.0, 'F.Cu', 0.0),    # V5_AI eFuse (moved east to clear D7 SS54)
    'F1':  (88.0, 18.0, 'F.Cu', 0.0),    # V9_VTX1 polyfuse MF-MSMF200
    # ── OUTPUT-side strip Y=70-77 (per master amendment 2026-05-23) ──
    # 4× ferrites (LC filter) on F.Cu at y=73 row (between spine pocket south edge and S6 USBLC6)
    'L6':  (35.0, 83.0, 'F.Cu', 0.0),    # V5_FC ferrite 600Ω
    'L7':  (50.0, 83.0, 'F.Cu', 0.0),    # V5_PI5 ferrite (in spine-pocket center column gap)
    'L8':  (65.0, 83.0, 'F.Cu', 0.0),    # V5_AI ferrite
    'L9':  (82.0, 83.0, 'F.Cu', 0.0),    # V9_VTX1 ferrite
    # 4× C_OUT (22µF post-ferrite) — spine pocket center + top strip edges
    'C8':  (50.0, 72.0, 'F.Cu', 0.0),    # V5_FC C_OUT (spine pocket center, between J2/J4 row)
    'C12': (50.0, 80.0, 'F.Cu', 0.0),    # V5_PI5 C_OUT (spine pocket center, between J3/J5 row)
    'C15': (22.0, 85.0, 'F.Cu', 0.0),    # V5_AI C_OUT (top strip west, clears R7 FB resistor)
    'C18': (88.0, 83.0, 'F.Cu', 0.0),    # V9_VTX1 C_OUT (top strip east)
    # 4× output TVS on B.Cu y=78 row (clears S4 CH1 Q9/Q10 B.Cu y_max=75.675; S6 all F.Cu)
    'D10': (35.0, 88.0, 'B.Cu', 0.0),    # V5_FC TVS SMAJ5.0A
    'D11': (50.0, 88.0, 'B.Cu', 0.0),    # V5_PI5 TVS
    'D12': (65.0, 88.0, 'B.Cu', 0.0),    # V5_AI TVS
    'D13': (82.0, 88.0, 'B.Cu', 0.0),    # V9_VTX1 TVS SMAJ9.0A
    # ── Buck #5 V9_VTX2 SW (2A VTX #2, isolated from #1) — vertical column x=5 ──
    'J6':  (12.0, 22.0, 'F.Cu', 0.0),    # buck IC AOZ1284
    'L5':  (12.0, 33.0, 'F.Cu', 0.0),    # 10uH
    'D9':  (12.0, 38.0, 'F.Cu', 0.0),    # SS54
    'F2':  (5.0,  14.0, 'F.Cu', 0.0),    # V9_VTX2 polyfuse (V_IN side)
    'R14': (8.0, 18.0, 'F.Cu', 0.0),    # FB top 102K
    'R15': (5.0,  22.0, 'F.Cu', 0.0),    # FB bot 10K
    'C20': (5.0,  26.0, 'F.Cu', 0.0),    # boot 100nF
    'L10': (5.0, 38.0, 'F.Cu', 0.0),    # V9_VTX2 ferrite
    'D14': (5.0, 36.0, 'F.Cu', 0.0),    # V9_VTX2 TVS SMAJ9.0A
    'C21': (8.0, 40.0, 'F.Cu', 0.0),    # C_OUT 22uF
    # ── LDO + Supervisor (central spine pocket) ──
    'J13': (50.0, 76.0, 'F.Cu', 0.0),    # LDO — center spine pocket (between 4 bucks)
    'J10': (50.0, 77.0, 'B.Cu', 0.0),    # V5_PI5 supervisor on B.Cu in spine pocket center (clears all F.Cu and B.Cu inductors)
}
S5_EXPECTED_VALUES = {
    'J2':  'TPS54560', 'J3':  'TPS54560', 'J4':  'TPS54560',
    'J5':  'AOZ1284',  'J6':  'AOZ1284',
    'L1':  '4.7uH',    'L2':  '4.7uH',    'L3':  '8.2uH',
    'L4':  '10uH',     'L5':  '10uH',
    'D5':  'SS54',     'D6':  'SS54',     'D7':  'SS54',
    'D8':  'SS54',     'D9':  'SS54',
    'J13': 'TLV76733', 'J10': 'VSUP',
    # FB pairs (52K3 + 10K for 5V; 102K + 10K for 9V)
    'R6':  '52K3', 'R7':  '10K',
    'R8':  '52K3', 'R9':  '10K',
    'R10': '52K3', 'R11': '10K',
    'R12': '102K', 'R13': '10K',
    'R14': '102K', 'R15': '10K',
    # Boot caps + C_OUT per buck
    'C7':  '100nF', 'C8':  '22uF',
    'C11': '100nF', 'C12': '22uF',
    'C14': '100nF', 'C15': '22uF',
    'C17': '100nF', 'C18': '22uF',
    'C20': '100nF', 'C21': '22uF',
    # Safety stacks per rail
    'J7':  'TPS259251', 'J8':  'TPS259251', 'J9':  'TPS259251',
    'F1':  'MF-MSMF200', 'F2':  'MF-MSMF200',
    'L6':  '600ohm', 'L7':  '600ohm', 'L8':  '600ohm', 'L9':  '600ohm', 'L10': '600ohm',
    'D10': 'SMAJ5.0A', 'D11': 'SMAJ5.0A', 'D12': 'SMAJ5.0A',
    'D13': 'SMAJ9.0A', 'D14': 'SMAJ9.0A',
}


def place_bec(fps_by_ref, placements):
    """S5 — BEC subsystem placement (docs/PHASE4_SUBSYSTEMS.md §S5)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S5_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        expected = S5_EXPECTED_VALUES[ref]
        if expected not in fp['value']:
            mismatched.append((ref, expected, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S5 components missing in netlist: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S5 ref {ref} value mismatch — expected '{exp}', got '{act}'")
    return placed


# ────────────────────────────────────────────────────────────────────
# S4 CH1: Channel #1 template (docs/PHASE4_SUBSYSTEMS.md §S4)
# NW quadrant X=5-39, Y=42-72 — now FULLY CLEAR after PR-A2 S5 4-zone relocation.
# Per R6 motor-pad-anchored architecture:
#   - 3 motor phase pads at outer west edge x=5
#   - 6 MOSFETs on B.Cu in 2×3 grid (full NW B.Cu)
#   - MCU + DRV + 3 INA on F.Cu interior
#   - Protection cluster (TL431/LM393/74LVC1G08) interior east edge
#   - LEDs + NTC interior
#   - Current shunts on B.Cu near Q lo-side FETs
# ────────────────────────────────────────────────────────────────────
S4_CH1_POSITIONS = {
    # Motor phase pads — west edge x=5
    'TP19': (5.0, 54.0, 'F.Cu', 0.0),    # MOTOR_A_CH1 (phase A motor pad)
    'TP20': (5.0, 66.0, 'F.Cu', 0.0),    # MOTOR_B_CH1
    'TP21': (5.0, 78.0, 'F.Cu', 0.0),    # MOTOR_C_CH1
    # 6× AOTL66912 MOSFETs on B.Cu (2 columns × 3 phase rows)
    # Hi-side west col x=12 (near motor pad), Lo-side east col x=28
    'Q5':  (12.0, 54.0, 'B.Cu', 0.0),     # Phase A hi
    'Q6':  (30.0, 54.0, 'B.Cu', 0.0),     # Phase A lo (x=30 for 1.3mm gap from Q5 x_max=20.35)
    'Q7':  (12.0, 66.0, 'B.Cu', 0.0),     # Phase B hi
    'Q8':  (30.0, 66.0, 'B.Cu', 0.0),     # Phase B lo
    'Q9':  (12.0, 78.0, 'B.Cu', 0.0),     # Phase C hi
    'Q10': (30.0, 78.0, 'B.Cu', 0.0),     # Phase C lo
    # MCU + DRV8300 on F.Cu (interior — east of FET cluster)
    'J18': (32.0, 58.0, 'F.Cu', 0.0),     # AT32F421 MCU LQFP-32 (y=52 clears S2 C3 bbox y_max=45.5)
    'J19': (22.0, 56.0, 'F.Cu', 0.0),     # DRV8300 gate driver HVQFN-24
    # INA186 column (x=15) — wide 10mm y-pitch to clear shunt 0402 courtyards
    'J20': (15.0, 51.0, 'F.Cu', 0.0),     # Phase A INA186
    'J21': (15.0, 61.0, 'F.Cu', 0.0),     # Phase B INA186
    'J22': (15.0, 71.0, 'F.Cu', 0.0),     # Phase C INA186
    # Protection cluster — row y=64 in NW quadrant SE corner
    'U2':  (35.0, 70.0, 'F.Cu', 0.0),     # TL431 SOT-23
    'U3':  (28.0, 70.0, 'F.Cu', 0.0),     # LM393 SOIC-8
    'U4':  (37.0, 66.0, 'F.Cu', 0.0),     # 74LVC1G08 SOT-353 (clear J2 spine pocket boundary at x=39.275)
    # Status LEDs — top row y=43 (north of S4 quadrant, clear of S2 caps + INA col)
    'D15': (10.0, 49.0, 'F.Cu', 0.0),     # RED_KILL_FW
    'D19': (28.0, 65.0, 'F.Cu', 0.0),     # RED_FAULT_HW (south of MCU, between MCU and U3 LM393)
    'D33': (35.0, 49.0, 'F.Cu', 0.0),     # RED status
    # NTC for OTP — north of protection cluster
    'TH1': (38.0, 74.0, 'F.Cu', 0.0),     # 10K B4250
    # Current sense shunts F.Cu in INA cluster gaps (x=10 column, between motor pads and INAs)
    'R56': (10.0, 58.0, 'F.Cu', 0.0),     # Phase A shunt (between J20 y=45 and J21 y=55)
    'R57': (10.0, 70.0, 'F.Cu', 0.0),     # Phase B shunt (between J21 y=55 and J22 y=65)
    'R58': (14.0, 80.0, 'F.Cu', 0.0),     # Phase C shunt (south of J22)
    # ── CH1 passives placed via greedy bbox-aware packing (PR-A3 amendment 2026-05-23) ──
    # 33 placed F.Cu in NW + 23 on B.Cu (different layer from FETs) — total 56
    # F.Cu cluster:
    'C55': (6.0, 48.0, 'F.Cu', 0.0), 'C58': (21.0, 48.0, 'F.Cu', 0.0),
    'C59': (26.0, 53.0, 'F.Cu', 0.0), 'C60': (33.0, 50.0, 'F.Cu', 0.0),
    'C70': (38.5, 48.0, 'F.Cu', 0.0), 'C71': (21.0, 50.5, 'F.Cu', 0.0),
    'C72': (26.0, 50.5, 'F.Cu', 0.0), 'C73': (31.0, 50.5, 'F.Cu', 0.0),
    'C74': (38.5, 50.5, 'F.Cu', 0.0), 'C75': (11.0, 53.0, 'F.Cu', 0.0),
    'C77': (38.0, 76.0, 'F.Cu', 0.0),
    'D24': (16.0, 55.5, 'F.Cu', 0.0), 'D25': (4.0, 58.0, 'F.Cu', 0.0),
    'D27': (25.0, 67.0, 'F.Cu', 0.0), 'D28': (16.0, 65.5, 'F.Cu', 0.0),
    'D29': (16.0, 75.0, 'F.Cu', 0.0), 'D30': (18.0, 64.0, 'F.Cu', 0.0),
    'D31': (21.0, 71.0, 'F.Cu', 0.0), 'D32': (25.0, 75.0, 'F.Cu', 0.0),
    'D34': (11.0, 60.5, 'F.Cu', 0.0), 'D35': (11.0, 63.0, 'F.Cu', 0.0),
    'D36': (16.0, 72.5, 'F.Cu', 0.0), 'D37': (33.5, 75.5, 'F.Cu', 0.0),
    'D38': (18.0, 85.0, 'F.Cu', 0.0),
    'R39': (18.0, 58.0, 'F.Cu', 0.0), 'R41': (21.0, 60.5, 'F.Cu', 0.0),
    'R42': (4.0, 62.0, 'F.Cu', 0.0), 'R44': (21.0, 65.5, 'F.Cu', 0.0),
    'R45': (11.0, 68.0, 'F.Cu', 0.0), 'R46': (25.0, 73.5, 'F.Cu', 0.0),
    'R47': (4.0, 75.5, 'F.Cu', 0.0), 'R48': (33.5, 78.0, 'F.Cu', 0.0),
    'R49': (38.5, 78.0, 'F.Cu', 0.0),
    # 23 remaining passives placed on SW B.Cu (S5 Buck 5 cluster is on F.Cu;
    # B.Cu in SW area is free). Routed through B.Cu plane stitched to F.Cu signals.
    'R50': (42.0, 22.0, 'B.Cu', 0.0), 'R51': (45.0, 22.0, 'B.Cu', 0.0),
    'R52': (48.0, 22.0, 'B.Cu', 0.0), 'R53': (51.0, 22.0, 'B.Cu', 0.0),
    'R54': (54.0, 22.0, 'B.Cu', 0.0), 'R55': (57.0, 22.0, 'B.Cu', 0.0),
    'R59': (42.0, 26.0, 'B.Cu', 0.0), 'R60': (45.0, 26.0, 'B.Cu', 0.0),
    'R61': (42.0, 24.0, 'B.Cu', 0.0), 'R62': (51.0, 23.0, 'B.Cu', 0.0),
    'R63': (54.0, 23.0, 'B.Cu', 0.0), 'R64': (57.0, 26.0, 'B.Cu', 0.0),
    'R66': (42.0, 30.0, 'B.Cu', 0.0), 'R67': (45.0, 30.0, 'B.Cu', 0.0),
    'R68': (48.0, 30.0, 'B.Cu', 0.0), 'R69': (51.0, 30.0, 'B.Cu', 0.0),
    'R70': (54.0, 30.0, 'B.Cu', 0.0), 'R71': (57.0, 30.0, 'B.Cu', 0.0),
    'R72': (42.0, 34.0, 'B.Cu', 0.0), 'R73': (45.0, 34.0, 'B.Cu', 0.0),
    'R74': (48.0, 34.0, 'B.Cu', 0.0), 'R75': (51.0, 34.0, 'B.Cu', 0.0),
    'R76': (54.0, 34.0, 'B.Cu', 0.0),
}
S4_CH1_EXPECTED_VALUES = {
    'TP19': 'MOTOR_A_CH1', 'TP20': 'MOTOR_B_CH1', 'TP21': 'MOTOR_C_CH1',
    'Q5':  'AOTL66912', 'Q6':  'AOTL66912', 'Q7':  'AOTL66912',
    'Q8':  'AOTL66912', 'Q9':  'AOTL66912', 'Q10': 'AOTL66912',
    'J18': 'AT32F421', 'J19': 'DRV8300',
    'J20': 'INA186', 'J21': 'INA186', 'J22': 'INA186',
    'U2':  'TL431', 'U3':  'LM393', 'U4':  '74LVC1G08',
    'D15': 'RED', 'D19': 'RED', 'D33': 'RED',
    'TH1': '10K_B4250',
    'R56': '0.2mR', 'R57': '0.2mR', 'R58': '0.2mR',
    # 56 passives
    'D24': 'BZT52C5V6', 'D25': 'BZT52C5V6', 'D27': 'BZT52C5V6',
    'D28': 'BZT52C5V6', 'D30': 'BZT52C5V6', 'D31': 'BZT52C5V6',
    'D29': 'SMBJ33A', 'D32': 'SMBJ33A',
    'D34': 'BAT54', 'D35': 'BAT54', 'D36': 'BAT54', 'D37': 'BAT54', 'D38': 'BAT54',
    'R44': '15R', 'R45': '15R', 'R48': '15R', 'R49': '15R', 'R52': '15R', 'R53': '15R',
    'R39': '10K', 'R41': '10K', 'R42': '10K', 'R46': '10K', 'R47': '10K',
    'R50': '10K', 'R51': '10K', 'R54': '10K', 'R55': '10K',
    'R59': '22K', 'R61': '22K', 'R63': '22K', 'R70': '22K',
    'R60': '3.3K', 'R62': '3.3K', 'R64': '3.3K',
    'R66': '10K', 'R67': '2K', 'R68': '1K', 'R69': '24K', 'R71': '3K',
    'R72': '100K', 'R73': '10K', 'R74': '10K', 'R75': '20K', 'R76': '10K',
    'C55': '100nF', 'C58': '1uF', 'C59': '1uF', 'C60': '1uF',
    'C70': '100nF', 'C71': '100nF', 'C72': '100nF', 'C77': '100nF',
    'C73': '1nF', 'C74': '1nF', 'C75': '1nF',
}


def place_channel_ch1(fps_by_ref, placements):
    """S4 CH1 — channel #1 template (NW quadrant per spec)."""
    placed = 0
    missing = []
    mismatched = []
    for ref, pos in S4_CH1_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            missing.append(ref)
            continue
        expected = S4_CH1_EXPECTED_VALUES[ref]
        if expected not in fp['value']:
            mismatched.append((ref, expected, fp['value']))
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    if missing:
        print(f"  WARN: S4 CH1 components missing: {missing}")
    if mismatched:
        for ref, exp, act in mismatched:
            print(f"  WARN: S4 CH1 {ref} mismatch — expected '{exp}', got '{act}'")
    return placed




# ────────────────────────────────────────────────────────────────────
# S4 CH2/CH3/CH4 — PR-A4-d 2026-05-23 mirror instantiation per master spec
# CH2 NE: mirror CH1 NW about X=50 (x → 100-x), rot += 180°
# CH3 SE: mirror CH1 NW about (X=50, Y=47.5) (x → 100-x, y → 95-y), rot += 0° (double mirror)
# CH4 SW: mirror CH1 NW about Y=47.5 (y → 95-y), rot += 180°
# 24 FETs total + 9 motor pads + 9 supporting per channel = 12 core × 3 = 36 cores
# Channel passives DEFERRED to A4-e per master scope
# ────────────────────────────────────────────────────────────────────
S4_CH234_POSITIONS = {
    # CH2 NE (mirror x → 100-x)
    'TP26': (95.0, 54.0, 'F.Cu', 180.0),  # motor A
    'TP27': (95.0, 66.0, 'F.Cu', 180.0),  # motor B
    'TP28': (95.0, 78.0, 'F.Cu', 180.0),  # motor C
    'Q11':  (88.0, 54.0, 'B.Cu', 180.0),  # Phase A hi
    'Q12':  (70.0, 54.0, 'B.Cu', 180.0),  # Phase A lo
    'Q13':  (88.0, 66.0, 'B.Cu', 180.0),  # Phase B hi
    'Q14':  (70.0, 66.0, 'B.Cu', 180.0),  # Phase B lo
    'Q15':  (88.0, 78.0, 'B.Cu', 180.0),  # Phase C hi
    'Q16':  (70.0, 78.0, 'B.Cu', 180.0),  # Phase C lo
    # CH3 SE (mirror both axes)
    'TP33': (95.0, 41.0, 'F.Cu',   0.0),  # mirror y=54 → 41
    'TP34': (95.0, 29.0, 'F.Cu',   0.0),  # mirror y=66 → 29
    'TP35': (95.0, 17.0, 'F.Cu',   0.0),  # mirror y=78 → 17
    'Q17':  (88.0, 41.0, 'B.Cu',   0.0),  # Phase A hi
    'Q18':  (70.0, 41.0, 'B.Cu',   0.0),  # Phase A lo
    'Q19':  (88.0, 30.0, 'B.Cu',   0.0),  # Phase B hi
    'Q20':  (70.0, 30.0, 'B.Cu',   0.0),  # Phase B lo
    'Q21':  (88.0, 19.0, 'B.Cu',   0.0),  # Phase C hi
    'Q22':  (70.0, 19.0, 'B.Cu',   0.0),  # Phase C lo
    # CH4 SW (mirror y about Y=47.5)
    'TP40': (5.0, 41.0, 'F.Cu', 180.0),
    'TP41': (5.0, 29.0, 'F.Cu', 180.0),
    'TP42': (5.0, 17.0, 'F.Cu', 180.0),
    'Q23':  (12.0, 41.0, 'B.Cu', 180.0),
    'Q24':  (30.0, 41.0, 'B.Cu', 180.0),
    'Q25':  (12.0, 30.0, 'B.Cu', 180.0),
    'Q26':  (30.0, 30.0, 'B.Cu', 180.0),
    'Q27':  (12.0, 19.0, 'B.Cu', 180.0),
    'Q28':  (30.0, 19.0, 'B.Cu', 180.0),
}


def place_channels_234(fps_by_ref, placements):
    """S4 CH2/3/4 — mirror instantiate per A4-d."""
    placed = 0
    for ref, pos in S4_CH234_POSITIONS.items():
        fp = fps_by_ref.get(ref)
        if not fp:
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    return placed


def place_auto_anchored(fps_by_ref, placements):
    """S8 (PR-A4-infra) — auto-anchored fill placements per R23 (no-island) + R24
    (no-unplaced). Picks up ANY netlist ref not placed by other subsystem placers
    and assigns it a slot near its electrical parent (FET/IC/connector) via
    scripts/auto_anchor_passives.py. Slots persisted in ch234_passives_dict.py."""
    try:
        from ch234_passives_dict import CH234_PASSIVES
    except ImportError:
        return 0
    placed = 0
    for ref, pos in CH234_PASSIVES.items():
        if ref in placements:
            continue
        fp = fps_by_ref.get(ref)
        if not fp:
            continue
        x, y, layer, rot = pos
        placements[ref] = (x, y, layer, rot)
        placed += 1
    return placed


# Registry of subsystem placers in spec order. PR-A4-infra structure: 8 functions
# defined (S1-S6 + S4 CH1 + S4 CH234 + S8 auto-anchored fallback). Subsystem PRs
# will refine each in turn.
ALL_PLACERS = [
    ('S1', 'Battery input',         place_battery_input),
    ('S2', 'Bulk cap bank',         place_bulk_caps),
    ('S3', 'Supervisor + Hall',     place_supervisor_hall),
    ('S6', 'FC + AUX connectors',   place_connectors),
    ('S5', 'BEC subsystem',         place_bec),
    ('S4 CH1', 'Channel #1 template (NW)', place_channel_ch1),
    ('S4 CH234', 'Channels 2/3/4 mirror', place_channels_234),
    ('S8 auto', 'Auto-anchored remainder',  place_auto_anchored),
]


# ────────────────────────────────────────────────────────────────────
# Footprint parser + helpers
# ────────────────────────────────────────────────────────────────────


def parse_footprints(pcb_text):
    results = []
    pos = 0
    while True:
        idx = pcb_text.find("\n\t(footprint ", pos)
        if idx < 0:
            break
        start = idx + 1
        depth = 0
        end = start
        for i, c in enumerate(pcb_text[start:], start):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        block = pcb_text[start:end]
        lib_m = re.search(r'\(footprint "([^"]+)"', block)
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
        val_m = re.search(r'\(property "Value" "([^"]+)"', block)
        layer_m = re.search(r'\(layer "([^"]+)"\)', block)
        at_m = re.search(r'\(at ([0-9.\-]+) ([0-9.\-]+)(?: ([0-9.\-]+))?\)', block)
        results.append({
            'start': start, 'end': end, 'block': block,
            'lib': lib_m.group(1) if lib_m else None,
            'ref': ref_m.group(1) if ref_m else '?',
            'value': val_m.group(1) if val_m else '?',
            'layer': layer_m.group(1) if layer_m else '?',
            'x': float(at_m.group(1)) if at_m else 0.0,
            'y': float(at_m.group(2)) if at_m else 0.0,
            'rot': float(at_m.group(3)) if at_m and at_m.group(3) else 0.0,
        })
        pos = end
    return results


def dedup_mount_holes(txt):
    """Drop duplicate MountingHole footprints (setup_board.py is non-idempotent
    on mount-hole addition; keep first 4 at intended corners)."""
    mh_blocks = []
    pos = 0
    while True:
        idx = txt.find('\n\t(footprint "MountingHole:', pos)
        if idx < 0:
            break
        start = idx + 1
        depth = 0
        end = start
        for i, c in enumerate(txt[start:], start):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        mh_blocks.append((idx, end))
        pos = end
    if len(mh_blocks) <= 4:
        return txt, 0
    # PR-A4-c 2026-05-23: keep LAST 4 (most recently added by setup_board.py)
    # to use the current board-geometry mount-hole positions, not stale earlier ones.
    deleted = 0
    for idx, end in reversed(mh_blocks[:-4]):
        txt = txt[:idx] + txt[end:]
        deleted += 1
    return txt, deleted


def main():
    only = None
    for arg in sys.argv[1:]:
        if arg.startswith('--only='):
            only = arg.split('=', 1)[1]

    txt = PCB.read_text()

    txt, mh_deleted = dedup_mount_holes(txt)
    if mh_deleted:
        print(f"Pre-processing: removed {mh_deleted} duplicate mount holes")

    fps = parse_footprints(txt)
    print(f"Parsed {len(fps)} footprints")
    fps_by_ref = {fp['ref']: fp for fp in fps}

    # Build placements: ref → (x, y, layer, rot)
    placements = {}
    for name, label, placer in ALL_PLACERS:
        if only and name != only:
            print(f"\nSkipping {name} ({label}) — --only={only} filter")
            continue
        print(f"\nSub-phase {name} ({label}):")
        n = placer(fps_by_ref, placements)
        print(f"  Placed: {n} components")

    print(f"\nTotal placements: {len(placements)} of {len(fps)} footprints")

    # Apply placements by rewriting (at ...) + (layer ...) lines per footprint
    replacements = []
    for fp in fps:
        ref = fp['ref']
        if ref not in placements:
            continue
        x, y, layer, rot = placements[ref]
        block = fp['block']
        new_block = re.sub(r'\(at [0-9.\-]+ [0-9.\-]+(?: [0-9.\-]+)?\)',
                           f'(at {x:.2f} {y:.2f} {rot:.1f})',
                           block, count=1)
        new_block = re.sub(r'\(layer "[^"]+"\)', f'(layer "{layer}")',
                           new_block, count=1)
        replacements.append((fp['start'], fp['end'], new_block))

    new_txt = txt
    for start, end, new_block in sorted(replacements, key=lambda r: -r[0]):
        new_txt = new_txt[:start] + new_block + new_txt[end:]

    PCB.write_text(new_txt)
    print(f"\nWrote: {PCB} ({PCB.stat().st_size:,} bytes)")
    print(f"Subsystem components placed: {len(replacements)}")
    if len(replacements) < len(fps):
        print(f"Remaining {len(fps) - len(replacements)} footprints stay at "
              f"kinet2pcb default positions (will be placed in subsequent sub-phases)")


if __name__ == "__main__":
    main()
