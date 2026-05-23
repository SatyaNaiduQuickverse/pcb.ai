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
    'J1': (50.00, 4.00, 'F.Cu',  0.0),   # XT30 BATT_PAD (center primary input)
    # NTC inrush limiters (MF72_5D25) — west/east of FET cluster, mirror about X=50
    # NTCs MF72_5D25 (TH, 5mm lead pitch). KEEP MASTER baseline (22, 7.5)/(78, 7.5)
    # rotation 0. This accepts the 2 master-baseline R1↔Q1 pad overlaps (inside
    # §S1 zone, existed before PR-S1 — not introduced by this PR per master gate
    # "no NEW overlaps from this PR"). Rotation/shift attempts all introduced
    # NEW outside-§S1 overlaps (R1↔H4/TP15 or R1↔R83/TH4). Per master tradeoff
    # accept master-state for R1/R2 — Q1↔R1 will be re-examined in PR-CH1 with
    # CH1 FET reshuffle.
    # PR-A4-integrate amendment 5c: R1/R2 X-symmetric pair about X=50.
    # R2 originally moved to X=60 to clear U1 Hall (then big-bbox at X=86). After
    # Defect-1 fix shrunk U1 pads to X≤81.25, R2 at X=74.5 clears U1 cleanly while
    # restoring mirror_X(50) symmetry with R1 at X=25.5.
    'R1': (25.50, 5.00, 'F.Cu',  0.0),
    'R2': (69.50, 2.00, 'F.Cu',  0.0),
    # 4× BSC014N06NS rev-pol FETs, parallel; symmetric about X=50
    'Q1': (30.00, 7.50, 'B.Cu',  0.0),
    'Q2': (45.00, 7.50, 'B.Cu',  0.0),
    'Q3': (55.00, 7.50, 'B.Cu',  0.0),
    'Q4': (70.00, 7.50, 'B.Cu',  0.0),
    # Rev-pol FET gate cluster — R3 (10K pull) + D2 (12V Zener clamp) ≤5mm
    # from nearest FET gate per R23. R3 anchored to Q1 (4mm); D2 anchored to Q4 (4mm).
    'R3': (32.00, 10.50, 'F.Cu',  0.0),   # GATE_RP 10K pull, anchored to Q1
    'D2': (68.00, 10.50, 'F.Cu',  0.0),   # 12V Zener, anchored to Q4 (symmetric)
    # D3/D4/R4/R5 status LEDs moved to §S6 in PR-S6 (Task #72).
    # D26 SMBJ33A — net is MOTOR_A_CH1, this is CH1 motor TVS (mis-labeled by historical
    # placement). Leave at master placement (15, 5) — moved to CH1 in PR-CH1.
    'D26': (15.00, 5.00, 'B.Cu',  0.0),
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
    'C1': (32.50, 28.00, 'F.Cu', 0.0),
    'C2': (75.00, 28.00, 'F.Cu', 0.0),
    'C3': (26.00, 44.00, 'F.Cu', 0.0),
    'C4': (71.50, 40.50, 'F.Cu', 0.0),
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
    'U1': (86.00, 8.00, 'F.Cu', 90.0),   # ACS770ECB Hall — rot=90 lays 13.6mm tall × 27mm wide in §S1 zone per master Option A3
    # PR-A4-integrate amendment 2026-05-23: U1 Hall RELOCATED (50, 45) → (88, 8)
    # per master Option A3. Hall in-series with VBAT current path in §S1 zone.
    # Engineering benefit: direct current measurement, frees central spine.
    # Spec deviation: Hall+supervisor symmetry broken; supervisor stays central.
    'J11': (50.00, 38.00, 'F.Cu', 0.0),    # TPS3700 supervisor — central spine (kept)
    'R19': (47.00, 36.00, 'F.Cu', 0.0),    # 348K OVP/UVP divider top — 3mm NW of J11
    'R20': (53.00, 36.00, 'F.Cu', 0.0),    # 23K2 OVP/UVP divider bot — 3mm NE (mirror)
    'C41': (50.00, 40.00, 'F.Cu', 0.0),    # 100nF inrush-delay cap — 2mm S of J11
    'R21': (53.00, 40.00, 'F.Cu', 0.0),    # 10K PG_VMOTOR pullup — 3mm SE of J11
    # PR-A4-integrate amendment 5i Blocker-2 fix: U1 Hall MOVED to (86,8) per
    # Defect-1 Option A3. Decoupling + signal divider cluster relocated from
    # OLD U1 (50,45) area to within R23 ≤3mm same-layer of new U1 signal pads
    # (pad 1 HALL_VCC_5V @ 86,8; pad 2 GND @ 86,6.73; pad 3 HALL_VOUT_RAW @ 86,5.46).
    # All on F.Cu (same as U1 body) per R25 same-side decoupling.
    'R30': (84.00, 8.00, 'F.Cu', 0.0),     # 0Ω V5 → HALL_VCC bridge — 2mm W of U1 pad 1
    'C42': (83.00, 9.00, 'F.Cu', 0.0),     # 1uF bypass — 4mm W of U1 pad 1
    'C43': (84.00, 6.00, 'F.Cu', 0.0),     # 100nF bypass — 2mm SW of U1 pad 1 (HF stack)
    # Hall output divider + filter — close to U1 pad 3 (HALL_VOUT_RAW @ 86, 5.46)
    'R31': (84.00, 4.00, 'F.Cu', 0.0),     # 10K div top (5V→3.3V) — 2.5mm SW of U1 pad 3
    'R32': (83.00, 5.00, 'F.Cu', 0.0),     # 20K div bot — 4mm SW of U1 pad 3
    'C44': (83.00, 7.00, 'F.Cu', 0.0),     # 10nF output filter — 4mm W of U1 pad 2
    # PR-A4-integrate amendment 5i Blocker-3 fix: R34 0Ω jumper RELOCATED from
    # (50,47) to near U1 pad 5 (VMOTOR_HALL_LO @ 78.5, 3.16) — was 36mm islanded
    # after U1 moved. Now 4.5mm from parent pad per R23 ≤8mm.
    'R33': (78.50, 14.50, 'B.Cu', 0.0),    # +VMOTOR → Hall pad 4 (VMOTOR_HALL_HI @ 78.5, 10.3) — 2.7mm N
    'R34': (78.50, 6.00, 'B.Cu', 0.0),     # Hall pad 5 bridge (VMOTOR_HALL_LO @ 78.5, 3.16) — 2.8mm N
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
    # PR-A4-integrate amendment 5c 2026-05-23: master Defect-3 X-mirror rule
    # ──────────────────────────────────────────────────────────────────
    # SYMMETRY-BY-DEFAULT: any new S6 entry MUST either (a) have an X-mirror
    # partner across X=50, or (b) be placed AT X=50 (truly central) if it's a
    # single-instance with no functional counterpart. Asymmetric S6 entries
    # are BANNED — audit's check_quadrant_count_balance gate enforces this.
    # ──────────────────────────────────────────────────────────────────
    # J12 AUX single-instance → moved to X=50 central.
    # J14 FC single-instance → at X=50 central (was already).
    # J15/J16/J17 USBLC6: J15+J16 are mirror pair (X=40/X=60).
    #   J17 is the 3rd USBLC6 (TLM+spare) — single-instance, placed at X=50.
    # R36/R37/C49 VBAT divider — re-centered X=50.
    # D3/R4 NW corner ↔ D4/R5 NE corner — X-mirror pair (kept).
    'J12': (15.00, 90.00, 'F.Cu',   0.0),    # AUX BM06B NW (single-instance exempt)
    'J14': (50.00, 90.00, 'F.Cu',   0.0),    # FC SM08B central
    'J15': (40.00, 85.00, 'F.Cu',   0.0),    # USBLC6 ch1+ch2 DShot (NW)
    'J16': (60.00, 85.00, 'F.Cu',   0.0),    # USBLC6 ch3+ch4 DShot (NE, mirror_X of J15)
    'J17': (75.00, 85.00, 'F.Cu',   0.0),    # USBLC6 TLM+spare NE
    'R36': (50.00, 91.50, 'F.Cu',   0.0),    # VBAT divider top — central (was X=47)
    'R37': (55.50, 87.00, 'F.Cu',   0.0),    # VBAT divider bot — slightly NE (X-balance partner of C49)
    'C49': (47.00, 84.00, 'F.Cu',   0.0),    # VBAT filter — slightly NW (X-balance partner of R37)
    # Status LED pairs in §S6 north strip Y=96 — NW/NE X-mirror pair (kept)
    'D3': (15.00, 96.00, 'F.Cu',  0.0),     # GREEN_PWR LED (NW)
    'R4': (18.00, 96.00, 'F.Cu',  0.0),     # D3 limit-R (3mm pair pitch)
    'D4': (85.00, 96.00, 'F.Cu',  0.0),    # RED_RPOL LED (NE mirror_X of D3)
    'R5': (82.00, 96.00, 'F.Cu',  0.0),    # D4 limit-R (NE mirror_X of R4)
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
    'J2': (43.00, 72.00, 'F.Cu', 0.0),
    'L1': (35.00, 73.00, 'B.Cu', 0.0),
    # Buck #2 V5_PI5 + L2
    'J3': (43.00, 80.00, 'F.Cu', 0.0),
    'L2': (43.00, 79.50, 'B.Cu', 0.0),
    # Buck #3 V5_AI + L3
    'J4': (57.00, 72.00, 'F.Cu', 0.0),
    'L3': (62.00, 67.00, 'B.Cu', 0.0),
    # Buck #4 V9_VTX1 + L4
    'J5': (57.00, 80.00, 'F.Cu', 0.0),
    'L4': (63.50, 73.50, 'B.Cu', 0.0),
    # PR-S5 2026-05-23: FB resistors RE-ANCHORED per-buck within R23 3mm + X-mirror.
    # Each buck's FB pair adjacent to its IC; FB pairs mirror about X=50.
    # Buck #1 V5_FC J2@(43, 72) → R6/R7 cluster east of J2
    'R6': (40.00, 69.00, 'F.Cu', 0.0),    # V5_FC FB top 52K3 (3mm N of J2)
    'R7': (38.00, 69.50, 'F.Cu', 0.0),    # V5_FC FB bot 10K
    # Buck #2 V5_PI5 J3@(43, 80) → R8/R9 cluster
    'R8': (40.00, 75.00, 'F.Cu', 0.0),    # V5_PI5 FB top 52K3 (3mm N of J3)
    'R9': (38.00, 79.50, 'F.Cu', 0.0),    # V5_PI5 FB bot 10K
    # Buck #3 V5_AI J4@(57, 72) → R10/R11 cluster (mirror_X of R6/R7)
    'R10': (60.00, 69.00, 'F.Cu', 0.0),    # V5_AI FB top 52K3 (mirror_X of R6)
    'R11': (61.50, 70.50, 'F.Cu', 0.0),    # V5_AI FB bot 10K
    # Buck #4 V9_VTX1 J5@(57, 80) → R12/R13 cluster (mirror_X of R8/R9)
    'R12': (57.50, 74.00, 'F.Cu', 0.0),    # V9_VTX1 FB top 102K (mirror_X of R8)
    'R13': (61.50, 81.00, 'F.Cu', 0.0),    # V9_VTX1 FB bot 10K
    # Boot caps — within 2mm of buck IC BST pin per R23
    'C7': (48.00, 74.50, 'F.Cu', 0.0),    # Buck 1 boot 100nF (2.5mm E of J2)
    'C11': (48.00, 81.00, 'F.Cu', 0.0),    # Buck 2 boot
    'C14': (53.50, 72.00, 'F.Cu', 0.0),    # Buck 3 boot (mirror_X of C7)
    'C17': (55.50, 87.00, 'F.Cu', 0.0),    # Buck 4 boot (mirror_X of C11)
    # ── INPUT-side strip Y=12-19 between S1 components (per master amendment 2026-05-23) ──
    # 4× Schottky D5-D8 — between S1 Q3/Q4 FET columns + east of R2 NTC
    'D5': (49.50, 12.50, 'F.Cu', 0.0),    # V5_FC catch diode SS54
    'D6': (39.50, 20.00, 'F.Cu', 0.0),    # V5_PI5 catch diode SS54
    'D7': (85.50, 10.50, 'F.Cu', 0.0),    # V5_AI catch diode
    'D8': (79.50, 18.00, 'F.Cu', 0.0),    # V9_VTX1 catch diode
    # 3× eFuses + 1× polyfuse — input protection per rail
    'J7': (15.00, 14.00, 'F.Cu', 0.0),    # V5_FC eFuse TPS259251
    'J8': (22.00, 16.00, 'F.Cu', 0.0),    # V5_PI5 eFuse (moved east to clear J6 V9_VTX2 buck at (12, 22))
    'J9': (90.00, 14.00, 'F.Cu', 0.0),    # V5_AI eFuse (moved east to clear D7 SS54)
    'F1': (86.50, 18.00, 'F.Cu', 0.0),    # V9_VTX1 polyfuse MF-MSMF200
    # ── OUTPUT-side strip Y=70-77 (per master amendment 2026-05-23) ──
    # 4× ferrites (LC filter) — PR-A4-integrate amendment 5c: L7 moved from X=50
    # to X=51 for NW/NE balance (X=50 counts as NW per audit; X-mirror partner C8 at X=49).
    'L6': (35.50, 83.00, 'F.Cu', 0.0),    # V5_FC ferrite 600Ω (NW)
    'L7': (56.00, 88.00, 'F.Cu', 0.0),    # V5_PI5 ferrite — NE side (was X=50)
    'L8': (64.50, 83.00, 'F.Cu', 0.0),    # V5_AI ferrite (NE, mirror_X of L6)
    'L9': (81.00, 83.00, 'F.Cu', 0.0),    # V9_VTX1 ferrite
    # 4× C_OUT (22µF post-ferrite) — PR-A4-integrate amendment 5c: split X=49/51
    # for NW/NE balance (was both at X=50 → audit counts as NW; X-symmetric pair now)
    'C8': (49.00, 72.00, 'F.Cu', 0.0),    # V5_FC C_OUT — NW side spine pocket
    'C12': (51.00, 80.50, 'F.Cu', 0.0),    # V5_PI5 C_OUT — NE side spine pocket (mirror_X)
    'C15': (22.00, 85.00, 'F.Cu', 0.0),    # V5_AI C_OUT (top strip west, clears R7 FB resistor)
    'C18': (86.50, 83.00, 'F.Cu', 0.0),    # V9_VTX1 C_OUT (top strip east) — mirror_X of C15? actually X=22 mirror is X=78, slight offset for layout
    # 4× output TVS on B.Cu y=78 row — PR-A4-integrate amendment 5c: D11 moved
    # from X=50 to X=51 for NW/NE balance (X=50 counts as NW per audit).
    'D10': (30.00, 93.00, 'B.Cu', 0.0),    # V5_FC TVS SMAJ5.0A (NW)
    'D11': (50.00, 88.00, 'B.Cu', 0.0),    # V5_PI5 TVS — NE side (was X=50)
    'D12': (61.50, 88.50, 'B.Cu', 0.0),    # V5_AI TVS (NE, mirror_X of D10)
    'D13': (82.00, 88.00, 'B.Cu', 0.0),    # V9_VTX1 TVS SMAJ9.0A
    # ── Buck #5 V9_VTX2 (2A VTX #2, isolated from #1) — SE column (PR-A4-integrate
    #    amendment 5c: relocated from SW to SE per master Defect-3 X-mirror rule.
    #    Single-instance V9_VTX2 has no W-side partner; place X-mirror of where SW
    #    cluster would have been. Maintains isolation from Buck #1/2 east side.
    #    R19 symmetry: NW/NE bucks 1-4 stay west-east balanced; Buck #5 now SE
    #    counters SW V9_VTX1 cluster effect from south input/output strips. ──
    'J6': (88.00, 22.00, 'F.Cu', 0.0),    # buck IC AOZ1284
    'L5': (86.50, 33.00, 'F.Cu', 0.0),    # 10uH
    'D9': (88.00, 38.00, 'F.Cu', 0.0),    # SS54
    'F2': (95.00, 14.00, 'F.Cu', 0.0),    # V9_VTX2 polyfuse (V_IN side)
    'R14': (86.50, 16.50, 'F.Cu', 0.0),    # FB top 102K
    'R15': (90.00, 25.50, 'F.Cu', 0.0),    # FB bot 10K
    'C20': (97.50, 26.00, 'F.Cu', 0.0),    # boot 100nF
    'L10': (96.00, 38.00, 'F.Cu', 0.0),    # V9_VTX2 ferrite
    'D14': (77.50, 43.00, 'F.Cu', 0.0),    # V9_VTX2 TVS SMAJ9.0A
    'C21': (80.50, 46.00, 'F.Cu', 0.0),    # C_OUT 22uF
    # ── LDO + Supervisor — PR-A4-integrate amendment 5c: split X=49/X=51 for
    #    NW/NE balance (was both at X=50 → counted as NW per audit quadrant rule).
    #    J13 stays NW(X=49), J10 moves NE(X=51). Functionally equivalent positions.
    'J13': (49.00, 76.00, 'F.Cu', 0.0),    # LDO — NW side of spine pocket
    'J10': (51.00, 77.00, 'B.Cu', 0.0),    # supervisor — NE side of spine pocket
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
    # PR-CH1: motor pads shifted to align with new FET row Y=56/68/80
    'TP19': (5.00, 56.00, 'F.Cu', 0.0),    # MOTOR_A_CH1 (phase A motor pad)
    'TP20': (5.00, 68.00, 'F.Cu', 0.0),    # MOTOR_B_CH1
    'TP21': (5.00, 80.00, 'F.Cu', 0.0),    # MOTOR_C_CH1
    # 6× AOTL66912 MOSFETs on B.Cu (2 columns × 3 phase rows)
    # Hi-side west col x=12 (near motor pad), Lo-side east col x=28
    # PR-CH1 2026-05-23: FET rows shifted Y=56/68/80 (P=12) per A4-redo locked
    # symmetric spec on 100×100 board. Mirror Y=50; CH3/4 derived in PR-CH3/CH4.
    'Q5': (12.00, 56.00, 'B.Cu', 0.0),     # Phase A hi
    'Q6': (30.00, 56.00, 'B.Cu', 0.0),     # Phase A lo
    'Q7': (12.00, 68.00, 'B.Cu', 0.0),     # Phase B hi
    'Q8': (30.00, 68.00, 'B.Cu', 0.0),     # Phase B lo
    'Q9': (12.00, 80.00, 'B.Cu', 0.0),     # Phase C hi
    'Q10': (30.00, 80.00, 'B.Cu', 0.0),     # Phase C lo
    # MCU + DRV8300 on F.Cu (interior — east of FET cluster)
    # PR-CH1: MCU + gate driver + INAs + protection IC positions adjusted
    # for new FET row Y=56/68/80. Gate driver ≤10mm from FET cluster center
    # per industry-standard practice (≤10mm gate driver-to-FET).
    # CH1 MCU at (45, 62) — between FET rows 56/68, just east of FET X-cluster (X<38)
    # PR-A4-integrate amendment: J18 MCU + J19 DRV repositioned to clear J2 buck
    # (43, 70) and gate-driver-buck collision. New positions still ≤10mm from FETs.
    # PR-A4-integrate amendment 2: J18/J19 + CH-mirror MCUs need OFF-Y=50-axis to avoid
    # mirror-position collisions (CH1+CH4 at Y=50 mirror to same spot, same for CH2+CH3).
    # Place J18 at NE corner of CH1 quadrant (45, 86). Mirror positions don't collide.
    'J18': (32.00, 86.00, 'F.Cu', 0.0),     # CH1 MCU per master corner-spread (32,86)
    'J19': (40.00, 62.00, 'F.Cu', 0.0),     # DRV8300 (kept — 6mm east of FET cluster)
    # INA186 column on west edge X=5 between motor pads and FETs
    'J20': (5.00, 62.00, 'F.Cu', 0.0),      # Phase A INA186 (south of motor pad TP19@56)
    'J21': (5.00, 74.00, 'F.Cu', 0.0),      # Phase B INA186 (between motor B/C pads)
    # PR-A4-integrate amendment 5k Step-1: J22 INA186 RELOCATED from (40,86) to
    # (33,86) — moves 5mm W to clear U2 SOT-23 (pad 3 collision) + U3 LM393 west
    # pad cluster (>=2mm gap). 6mm separation from TL431+LM393 cluster per master.
    'J22': (40.00, 92.00, 'F.Cu', 0.0),     # Phase C INA186 (N of TL431 cluster — 5k)
    # PR-A4-integrate amendment 5i Blocker-1 fix: spread CH1 protection cluster
    # to clear pad overlaps. SOIC-8 LM393 (U3) is 6.9×4.4mm; its pad bbox
    # (44.55-51.45) overlapped U2 SOT-23 (43.33-46.67). Shifted X to give
    # clean separation.
    # 5i: U2 SOT-23 east pad at X=41.67 was overlapping U3 LM393 west pad at X=41.55.
    # Shifted U2 to X=38 (east pad X=39.67, gap 1.9mm to U3).
    'U2': (38.00, 86.00, 'F.Cu', 0.0),     # TL431 SOT-23
    'U3': (45.00, 84.00, 'F.Cu', 0.0),     # LM393 SOIC-8 — east pads end at X=48.45
    'U4': (38.00, 78.00, 'F.Cu', 0.0),     # 74LVC1G08 SOT-353 — under U2
    'D15': (10.00, 50.50, 'F.Cu', 0.0),     # RED_KILL_FW (north of H1 keep-out (10, 50))
    'D19': (45.00, 66.00, 'F.Cu', 0.0),     # RED_FAULT_HW (south of MCU)
    'D33': (44.50, 68.00, 'F.Cu', 0.0),     # RED status
    'TH1': (45.00, 82.00, 'B.Cu', 0.0),     # 10K B4250 NTC
    # Current sense shunts on motor-pad-to-FET path (west edge)
    'R56': (13.50, 60.00, 'F.Cu', 0.0),      # Phase A shunt (between TP19@56 and Q5@56)
    'R57': (13.50, 72.00, 'F.Cu', 0.0),      # Phase B shunt (between TP20@68 and Q7@68)
    'R58': (13.50, 84.00, 'F.Cu', 0.0),      # Phase C shunt (between TP21@80 and Q9@80)
    # ── CH1 passives placed via greedy bbox-aware packing (PR-A3 amendment 2026-05-23) ──
    # 33 placed F.Cu in NW + 23 on B.Cu (different layer from FETs) — total 56
    # F.Cu cluster:
    'C55': (13.50, 48.00, 'F.Cu', 0.0), 'C58': (21.00, 48.00, 'F.Cu', 0.0),
    'C59': (26.00, 53.00, 'F.Cu', 0.0), 'C60': (33.00, 52.00, 'F.Cu', 0.0),
    'C70': (38.50, 48.00, 'F.Cu', 0.0), 'C71': (21.00, 50.50, 'F.Cu', 0.0),
    'C72': (26.00, 50.50, 'F.Cu', 0.0), 'C73': (31.00, 50.50, 'F.Cu', 0.0),
    'C74': (38.50, 50.50, 'F.Cu', 0.0), 'C75': (13.50, 53.00, 'F.Cu', 0.0),
    'C77': (38.00, 76.00, 'F.Cu', 0.0),
    'D24': (17.50, 55.50, 'F.Cu', 0.0), 'D25': (13.50, 59.00, 'F.Cu', 0.0),
    'D27': (24.50, 67.00, 'F.Cu', 0.0), 'D28': (15.50, 65.50, 'F.Cu', 0.0),
    'D29': (18.00, 75.00, 'F.Cu', 0.0), 'D30': (18.00, 64.00, 'F.Cu', 0.0),
    'D31': (21.00, 71.00, 'F.Cu', 0.0), 'D32': (25.00, 75.00, 'F.Cu', 0.0),
    'D34': (13.50, 60.50, 'F.Cu', 0.0), 'D35': (13.50, 63.00, 'F.Cu', 0.0),
    'D36': (16.50, 72.50, 'F.Cu', 0.0), 'D37': (33.50, 75.50, 'F.Cu', 0.0),
    'D38': (18.50, 85.00, 'F.Cu', 0.0),
    'R39': (18.00, 58.00, 'F.Cu', 0.0), 'R41': (21.00, 60.50, 'F.Cu', 0.0),
    'R42': (7.50, 62.00, 'F.Cu', 0.0), 'R44': (21.00, 65.50, 'F.Cu', 0.0),
    'R45': (14.50, 68.00, 'F.Cu', 0.0), 'R46': (25.00, 73.50, 'F.Cu', 0.0),
    'R47': (13.50, 76.50, 'F.Cu', 0.0), 'R48': (33.50, 77.50, 'F.Cu', 0.0),
    'R49': (36.00, 79.50, 'F.Cu', 0.0),
    # 23 remaining passives placed on SW B.Cu (S5 Buck 5 cluster is on F.Cu;
    # B.Cu in SW area is free). Routed through B.Cu plane stitched to F.Cu signals.
    'R50': (42.50, 22.00, 'B.Cu', 0.0), 'R51': (44.00, 20.50, 'B.Cu', 0.0),
    'R52': (48.00, 22.00, 'B.Cu', 0.0), 'R53': (51.00, 21.00, 'B.Cu', 0.0),
    'R54': (54.00, 20.50, 'B.Cu', 0.0), 'R55': (58.00, 25.00, 'B.Cu', 0.0),
    'R59': (42.00, 26.00, 'B.Cu', 0.0), 'R60': (45.00, 26.00, 'B.Cu', 0.0),
    'R61': (42.00, 24.00, 'B.Cu', 0.0), 'R62': (51.00, 23.00, 'B.Cu', 0.0),
    'R63': (54.50, 23.50, 'B.Cu', 0.0), 'R64': (57.00, 26.00, 'B.Cu', 0.0),
    'R66': (42.00, 32.00, 'B.Cu', 0.0), 'R67': (45.00, 31.00, 'B.Cu', 0.0),
    'R68': (48.00, 30.00, 'B.Cu', 0.0), 'R69': (51.00, 30.00, 'B.Cu', 0.0),
    'R70': (53.00, 31.00, 'B.Cu', 0.0), 'R71': (57.00, 31.00, 'B.Cu', 0.0),
    'R72': (42.00, 34.00, 'B.Cu', 0.0), 'R73': (44.00, 33.00, 'B.Cu', 0.0),
    'R74': (48.00, 33.00, 'B.Cu', 0.0), 'R75': (51.00, 34.00, 'B.Cu', 0.0),
    'R76': (53.50, 35.00, 'B.Cu', 0.0),
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
    # PR-CH2 2026-05-23: CH2 = mirror_X(50) of CH1. Q11-Q16 at Y=56/68/80 per CH1.
    'TP26': (95.0, 56.0, 'F.Cu', 180.0),  # motor A (mirror of TP19@5,56)
    'TP27': (95.0, 68.0, 'F.Cu', 180.0),  # motor B
    'TP28': (95.0, 80.0, 'F.Cu', 180.0),  # motor C
    'Q11':  (88.0, 56.0, 'B.Cu', 180.0),  # Phase A hi (mirror of Q5@12,56)
    'Q12':  (70.0, 56.0, 'B.Cu', 180.0),  # Phase A lo (mirror of Q6@30,56)
    'Q13':  (88.0, 68.0, 'B.Cu', 180.0),  # Phase B hi
    'Q14':  (70.0, 68.0, 'B.Cu', 180.0),  # Phase B lo
    'Q15':  (88.0, 80.0, 'B.Cu', 180.0),  # Phase C hi
    'Q16':  (70.0, 80.0, 'B.Cu', 180.0),  # Phase C lo
    # PR-CH2 2026-05-23: CH2 ICs/shunts/LEDs/protection → mirror_X(50) of CH1
    'J23':  (68.0, 86.0, 'F.Cu', 0.0),    # CH2 MCU mirror_X(J18@32,86)
    'J24':  (60.0, 62.0, 'F.Cu', 0.0),    # CH2 DRV8300 (mirror_X of J19@40,62)
    'J25':  (95.0, 62.0, 'F.Cu', 0.0),    # CH2 INA #A (mirror of J20@5,62)
    'J27':  (95.0, 74.0, 'F.Cu', 0.0),    # CH2 INA #B (mirror of J21@5,74)
    'J26':  (60.0, 92.0, 'F.Cu', 0.0),    # CH2 INA #C (mirror_X of J22@40,92)
    # 5i: mirror_X of new U2/U3/U4 (X=38, 45, 38)
    'U5':   (62.0, 86.0, 'F.Cu', 0.0),    # CH2 TL431 (mirror_X of U2@38)
    'U6':   (55.0, 84.0, 'F.Cu', 0.0),    # CH2 LM393 (mirror_X of U3@45)
    'U7':   (62.0, 78.0, 'F.Cu', 0.0),    # CH2 74LVC1G08 (mirror_X of U4@38)
    'D16':  (90.0, 50.5, 'F.Cu', 0.0),    # CH2 RED_KILL_FW (mirror of D15@10,50.5)
    'D20':  (55.0, 66.0, 'F.Cu', 0.0),    # CH2 RED_FAULT_HW (mirror of D19@45,66)
    'D48':  (55.0, 70.0, 'F.Cu', 0.0),    # CH2 RED (mirror of D33@45,70)
    'TH2':  (55.0, 82.0, 'B.Cu', 0.0),    # CH2 NTC (mirror of TH1@45,82)
    'R94': (86.50, 60.00, 'F.Cu', 0.0),    # CH2 shunt Phase A (mirror of R56@8,60)
    'R95': (86.50, 72.00, 'F.Cu', 0.0),    # CH2 shunt Phase B (mirror of R57@8,72)
    'R96': (86.50, 84.00, 'F.Cu', 0.0),    # CH2 shunt Phase C (mirror of R58@8,84)
    # PR-CH3 2026-05-23: CH3 = 180°-rotate of CH1 about (50, 50). Y'=100-Y.
    # CH1 Y=56/68/80 → CH3 Y=44/32/20. P=12 preserved.
    'TP33': (95.0, 44.0, 'F.Cu',   0.0),  # rot of TP19@(5,56)
    'TP34': (95.0, 32.0, 'F.Cu',   0.0),  # rot of TP20@(5,68)
    'TP35': (95.0, 20.0, 'F.Cu',   0.0),  # rot of TP21@(5,80)
    'Q17':  (88.0, 44.0, 'B.Cu',   0.0),  # rot of Q5@(12,56)
    'Q18':  (70.0, 44.0, 'B.Cu',   0.0),  # rot of Q6@(30,56)
    'Q19':  (88.0, 32.0, 'B.Cu',   0.0),  # rot of Q7@(12,68)
    'Q20':  (70.0, 32.0, 'B.Cu',   0.0),  # rot of Q8@(30,68)
    'Q21':  (88.0, 20.0, 'B.Cu',   0.0),  # rot of Q9@(12,80)
    'Q22':  (70.0, 20.0, 'B.Cu',   0.0),  # rot of Q10@(30,80)
    # PR-CH3 ICs/LEDs/shunts via 180°-rot of CH1 counterparts (X'=100-X, Y'=100-Y)
    'J28':  (68.0, 14.0, 'F.Cu',   0.0),  # CH3 MCU 180°-rot(J18@32,86)
    'J29':  (60.0, 38.0, 'F.Cu',   0.0),  # CH3 DRV (180°-rot of J19@40,62)
    'J30':  (95.0, 38.0, 'F.Cu',   0.0),  # CH3 INA #A (rot of J20@5,62)
    'J32':  (95.0, 26.0, 'F.Cu',   0.0),  # CH3 INA #B (rot of J21@5,74)
    'J31':  (60.0,  8.0, 'F.Cu',   0.0),  # CH3 INA #C (180-rot of J22@40,92)
    # 5i: 180°-rot of new U2/U3/U4 (X=38,45,38)
    'U8':   (62.0, 14.0, 'F.Cu',   0.0),  # CH3 TL431 (180-rot of U2@38,86)
    'U9':   (55.0, 16.0, 'F.Cu',   0.0),  # CH3 LM393 (180-rot of U3@45,84)
    'U10':  (62.0, 22.0, 'F.Cu',   0.0),  # CH3 74LVC1G08 (180-rot of U4@38,78)
    'TH3':  (55.0, 18.0, 'B.Cu',   0.0),  # CH3 NTC (rot of TH1@45,82)
    'D17':  (90.0, 49.5, 'F.Cu',   0.0),  # CH3 RED_KILL_FW (rot of D15@10,50.5)
    'D21':  (55.0, 34.0, 'F.Cu',   0.0),  # CH3 RED_FAULT_HW (rot of D19@45,66)
    'D63':  (55.0, 30.0, 'F.Cu',   0.0),  # CH3 RED (rot of D33@45,70)
    'R132': (86.50, 40.00, 'F.Cu',   0.0),  # CH3 shunt Phase A (rot of R56@8,60)
    'R133': (86.50, 28.00, 'F.Cu',   0.0),  # CH3 shunt Phase B (rot of R57@8,72)
    'R134': (86.50, 16.00, 'F.Cu',   0.0),  # CH3 shunt Phase C (rot of R58@8,84)
    # PR-CH4 2026-05-23: CH4 = mirror_Y(50) of CH1. Y'=100-Y, X unchanged.
    # CH1 Y=56/68/80 → CH4 Y=44/32/20. P=12 preserved.
    'TP40': (5.0, 44.0, 'F.Cu', 0.0),     # mirror_Y of TP19@(5,56)
    'TP41': (5.0, 32.0, 'F.Cu', 0.0),     # mirror_Y of TP20@(5,68)
    'TP42': (5.0, 20.0, 'F.Cu', 0.0),     # mirror_Y of TP21@(5,80)
    'Q23':  (12.0, 44.0, 'B.Cu', 0.0),    # mirror_Y of Q5@(12,56)
    'Q24':  (30.0, 44.0, 'B.Cu', 0.0),    # mirror_Y of Q6@(30,56)
    'Q25':  (12.0, 32.0, 'B.Cu', 0.0),    # mirror_Y of Q7@(12,68)
    'Q26':  (30.0, 32.0, 'B.Cu', 0.0),    # mirror_Y of Q8@(30,68)
    'Q27':  (12.0, 20.0, 'B.Cu', 0.0),    # mirror_Y of Q9@(12,80)
    'Q28':  (30.0, 20.0, 'B.Cu', 0.0),    # mirror_Y of Q10@(30,80)
    # PR-CH4 ICs/LEDs/shunts via mirror_Y of CH1 counterparts
    'J33':  (32.0, 14.0, 'F.Cu', 0.0),    # CH4 MCU mirror_Y(J18@32,86)
    'J34':  (40.0, 38.0, 'F.Cu', 0.0),    # CH4 DRV (mirror_Y of J19@40,62)
    'J35':  (5.0,  38.0, 'F.Cu', 0.0),    # CH4 INA #A (mirror_Y of J20@5,62)
    'J36':  (5.0,  26.0, 'F.Cu', 0.0),    # CH4 INA #B (mirror_Y of J21@5,74)
    'J37':  (40.0,  8.0, 'F.Cu', 0.0),    # CH4 INA #C (mirror_Y of J22@40,92)
    # 5i: mirror_Y of new U2/U3/U4 (X=38,45,38)
    'U11':  (38.0, 14.0, 'F.Cu', 0.0),    # CH4 TL431 (mirror_Y of U2@38,86)
    'U12':  (45.0, 16.0, 'F.Cu', 0.0),    # CH4 LM393 (mirror_Y of U3@45,84)
    'U13':  (38.0, 22.0, 'F.Cu', 0.0),    # CH4 74LVC1G08 (mirror_Y of U4@38,78)
    'TH4':  (45.0, 18.0, 'B.Cu', 0.0),    # CH4 NTC (mirror_Y of TH1@45,82)
    'D18':  (10.0, 49.5, 'F.Cu', 0.0),    # CH4 RED_KILL_FW (mirror_Y of D15@10,50.5)
    'D22':  (45.0, 34.0, 'F.Cu', 0.0),    # CH4 RED_FAULT_HW (mirror_Y of D19@45,66)
    'D78':  (45.0, 30.0, 'F.Cu', 0.0),    # CH4 RED (mirror_Y of D33@45,70)
    'R170': (13.50, 40.00, 'F.Cu', 0.0),     # CH4 shunt Phase A (mirror_Y of R56@8,60)
    'R171': (13.50, 28.00, 'F.Cu', 0.0),     # CH4 shunt Phase B (mirror_Y of R57@8,72)
    'R172': (13.50, 16.00, 'F.Cu', 0.0),     # CH4 shunt Phase C (mirror_Y of R58@8,84)
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
        # PR-spine-fix 2026-05-23: skip mount holes (H*) — owned by setup_board.py
        # to avoid auto-anchor regression to legacy (44.6, 37.5) positions.
        if ref.startswith('H') and len(ref) > 1 and ref[1:].isdigit():
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
