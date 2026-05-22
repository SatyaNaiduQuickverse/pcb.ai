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
    # ref          (x,    y,   layer,  rot)   notes
    # Bottom-edge row at y=4-5 — XT30 + TVS
    'J1':         (50.0,  4.0, 'F.Cu',  0.0),   # BATT_PAD (XT30) center-bottom
    'D26':        (32.0,  5.0, 'B.Cu',  0.0),   # SMBJ33A TVS (D_SMB), left of XT30
    # Second row at y=10 — NTCs flanking + FET 2×2 cluster centered
    'R1':         (28.0, 10.0, 'F.Cu',  0.0),   # MF72_5D25 NTC inrush #1
    'R2':         (72.0, 10.0, 'F.Cu',  0.0),   # MF72_5D25 NTC inrush #2
    # 2×2 RP FET cluster around (50, 13.5)
    'Q1':         (40.0, 10.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #1 (top-left)
    'Q2':         (60.0, 10.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #2 (top-right)
    'Q3':         (40.0, 17.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #3 (bot-left)
    'Q4':         (60.0, 17.0, 'B.Cu',  0.0),   # BSC014N06NS rev-pol #4 (bot-right)
    # Note: Q3/Q4 spill into Y=13-17 (nominally bulk-cap S2 zone) — RP FET
    # SuperSO8 5×6 body × 2 rows requires ≥12mm vertical span; spec'd Y=0-13
    # zone is too tight. Per master spec §S1 the 2×2 cluster centers at (50, 11);
    # we adopt a slightly south-offset cluster (50, 13.5) to keep ≥1mm gap to
    # row-1 (J1, D26) bbox. S2 bulk caps will avoid the (40-60, 13-17) range.
}
# Expected SKiDL values per ref (sanity check; abort if mismatched)
S1_EXPECTED_VALUES = {
    'J1':  'BATT_PAD',
    'D26': 'SMBJ33A',
    'R1':  'MF72_5D25',
    'R2':  'MF72_5D25',
    'Q1':  'BSC014N06NS',
    'Q2':  'BSC014N06NS',
    'Q3':  'BSC014N06NS',
    'Q4':  'BSC014N06NS',
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
    # (42.1, 20.3)..(61.7, 46.0). S2 caps must clear this. Shifted outward:
    # C1/C3 at x=30, C2/C4 at x=70 — outside Hall body bbox by ≥1mm.
    # This pushes caps into what will become NW/NE channel zones (master
    # amended channel inner-edges to X=39/61); Phase 4-place-channels-x4
    # will coordinate (likely shifts channel passive zone to clear bulk caps).
    'C1': (30.0, 24.0, 'F.Cu', 0.0),
    'C2': (70.0, 24.0, 'F.Cu', 0.0),
    'C3': (30.0, 40.0, 'F.Cu', 0.0),
    'C4': (70.0, 40.0, 'F.Cu', 0.0),
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
    'R34': (50.0, 65.0, 'B.Cu', 0.0),    # Hall pad 5 (south end) → +VMOTOR_CH
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
    'J12': (15.0, 80.0, 'F.Cu',   0.0),    # AUX BM06B-SRSS-TB west top
    'J14': (50.0, 80.0, 'F.Cu',   0.0),    # FC SM08B-SRSS-TB central top
    'J15': (40.0, 75.0, 'F.Cu',   0.0),    # USBLC6 ESD ch1+ch2 DShot
    'J16': (60.0, 75.0, 'F.Cu',   0.0),    # USBLC6 ESD ch3+ch4 DShot
    'J17': (75.0, 75.0, 'F.Cu',   0.0),    # USBLC6 ESD TLM + spare
    'R36': (47.0, 76.0, 'F.Cu',   0.0),    # VBAT divider top 100K
    'R37': (47.0, 74.0, 'F.Cu',   0.0),    # VBAT divider bot 14K
    'C49': (45.0, 74.0, 'F.Cu',   0.0),    # VBAT filter 100nF
}
S6_EXPECTED_VALUES = {
    'J12': 'BM06B',
    'J14': 'SM08B',
    'J15': 'USBLC6',
    'J16': 'USBLC6',
    'J17': 'USBLC6',
    'R36': '100K',
    'R37': '14K',
    'C49': '100nF',
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
    # ── Buck #1 V5_FC NW (5A FC + cam + RX) ──
    'J2':  (12.0, 60.0, 'F.Cu', 0.0),    # buck IC TPS54560
    'L1':  (22.0, 60.0, 'F.Cu', 0.0),    # 4.7uH inductor
    'D5':  (32.0, 60.0, 'F.Cu', 0.0),    # SS54 Schottky
    'R6':  (5.0,  60.0, 'F.Cu', 0.0),    # FB top 52K3
    'R7':  (5.0,  62.0, 'F.Cu', 0.0),    # FB bot 10K
    'C7':  (5.0,  64.0, 'F.Cu', 0.0),    # boot 100nF
    'C8':  (38.0, 60.0, 'F.Cu', 0.0),    # C_OUT 22uF
    'J7':  (38.0, 55.0, 'F.Cu', 0.0),    # V5_FC eFuse TPS259251
    'L6':  (28.0, 54.0, 'F.Cu', 0.0),    # V5_FC ferrite 600Ω
    'D10': (44.0, 60.0, 'F.Cu', 0.0),    # V5_FC TVS SMAJ5.0A (east of C8)
    # ── Buck #2 V5_PI5 NW (5A RPi 5) ──
    'J3':  (12.0, 70.0, 'F.Cu', 0.0),    # buck IC
    'L2':  (22.0, 70.0, 'F.Cu', 0.0),    # 4.7uH inductor
    'D6':  (32.0, 70.0, 'F.Cu', 0.0),    # SS54
    'R8':  (5.0,  70.0, 'F.Cu', 0.0),    # FB top 52K3
    'R9':  (5.0,  72.0, 'F.Cu', 0.0),    # FB bot 10K
    'C11': (5.0,  74.0, 'F.Cu', 0.0),    # boot 100nF
    'C12': (38.0, 70.0, 'F.Cu', 0.0),    # C_OUT 22uF
    'J8':  (35.0, 75.0, 'F.Cu', 0.0),    # V5_PI5 eFuse (east of L2)
    'L7':  (52.0, 75.0, 'F.Cu', 0.0),    # V5_PI5 ferrite (clear S6 VBAT divider + FC connector)
    'D11': (44.0, 70.0, 'F.Cu', 0.0),    # V5_PI5 TVS (east of C12)
    # ── Buck #3 V5_AI NE (3A AI HAT) ──
    'J4':  (88.0, 60.0, 'F.Cu', 0.0),    # buck IC
    'L3':  (78.0, 60.0, 'F.Cu', 0.0),    # 8.2uH
    'D7':  (68.0, 60.0, 'F.Cu', 0.0),    # SS54
    'R10': (95.0, 60.0, 'F.Cu', 0.0),    # FB top 52K3
    'R11': (95.0, 62.0, 'F.Cu', 0.0),    # FB bot 10K
    'C14': (95.0, 64.0, 'F.Cu', 0.0),    # boot 100nF
    'C15': (62.0, 60.0, 'F.Cu', 0.0),    # C_OUT 22uF
    'J9':  (62.0, 55.0, 'F.Cu', 0.0),    # V5_AI eFuse
    'L8':  (70.0, 54.0, 'F.Cu', 0.0),    # V5_AI ferrite
    'D12': (56.0, 60.0, 'F.Cu', 0.0),    # V5_AI TVS (west of C15)
    # ── Buck #4 V9_VTX1 NE (2A VTX #1) ──
    'J5':  (88.0, 70.0, 'F.Cu', 0.0),    # buck IC AOZ1284
    'L4':  (78.0, 70.0, 'F.Cu', 0.0),    # 10uH
    'D8':  (68.0, 70.0, 'F.Cu', 0.0),    # SS54
    'R12': (95.0, 70.0, 'F.Cu', 0.0),    # FB top 102K
    'R13': (95.0, 72.0, 'F.Cu', 0.0),    # FB bot 10K
    'C17': (95.0, 74.0, 'F.Cu', 0.0),    # boot 100nF
    'C18': (62.0, 70.0, 'F.Cu', 0.0),    # C_OUT 22uF
    'F1':  (62.0, 78.0, 'F.Cu', 0.0),    # V9_VTX1 polyfuse MF-MSMF200 (clear S6 J16)
    'L9':  (70.0, 75.0, 'F.Cu', 0.0),    # V9_VTX1 ferrite
    'D13': (56.0, 70.0, 'F.Cu', 0.0),    # V9_VTX1 TVS (west of C18)
    # ── Buck #5 V9_VTX2 SW (2A VTX #2, isolated from #1) — vertical column x=5 ──
    'J6':  (12.0, 22.0, 'F.Cu', 0.0),    # buck IC AOZ1284
    'L5':  (12.0, 30.0, 'F.Cu', 0.0),    # 10uH
    'D9':  (12.0, 38.0, 'F.Cu', 0.0),    # SS54
    'F2':  (5.0,  14.0, 'F.Cu', 0.0),    # V9_VTX2 polyfuse (V_IN side)
    'R14': (5.0,  18.0, 'F.Cu', 0.0),    # FB top 102K
    'R15': (5.0,  22.0, 'F.Cu', 0.0),    # FB bot 10K
    'C20': (5.0,  26.0, 'F.Cu', 0.0),    # boot 100nF
    'L10': (5.0,  30.0, 'F.Cu', 0.0),    # V9_VTX2 ferrite
    'D14': (5.0,  34.0, 'F.Cu', 0.0),    # V9_VTX2 TVS SMAJ9.0A
    'C21': (5.0,  40.0, 'F.Cu', 0.0),    # C_OUT 22uF
    # ── LDO + Supervisor (central spine pocket) ──
    'J13': (38.0, 67.0, 'F.Cu', 0.0),    # LDO TLV76733 WSON-6 (V5_FC→V3V3)
    'J10': (50.0, 65.0, 'F.Cu', 0.0),    # V5_PI5 supervisor SOT-23
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


# Registry of subsystem placers in spec order
ALL_PLACERS = [
    ('S1', 'Battery input',         place_battery_input),
    ('S2', 'Bulk cap bank',         place_bulk_caps),
    ('S3', 'Supervisor + Hall',     place_supervisor_hall),
    ('S6', 'FC + AUX connectors',   place_connectors),
    ('S5', 'BEC subsystem',         place_bec),
    # ('S4', 'Channel template (×4)', place_channels),          # PR ×2
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
    deleted = 0
    for idx, end in reversed(mh_blocks[4:]):
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
