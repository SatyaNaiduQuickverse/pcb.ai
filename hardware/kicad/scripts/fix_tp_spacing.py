#!/usr/bin/env python3
"""fix_tp_spacing.py — PR-TP-and-edge-fix per master Sai-eye catches #4 + #5.

Catch #4: 58 same-layer TP-pair spacing violations. Scope probe tip 1.5mm +
clip 4-5mm/side → need ≥4mm center-to-center AND ≥2.5mm edge gap.

Catch #5: external connectors J14 FC + J12 AUX placed 12mm from S edge
(cable exits cramped + components in cable-bend zone). Move to Y=95
(3-5mm from S edge per master). Relocate D3/D4/R4/R5 corner LEDs from
S edge (Y=96) to N edge (Y=2) to free cable-bend zone.

FIX STRATEGY:
  1. Remove redundant GND/+3V3 TPs (multiple GND/+3V3 probes per cluster
     don't add testability — keep 1 per row, delete rest).
  2. Repitch remaining TPs to ≥5mm center-to-center (4mm hard minimum + 1mm
     margin).
  3. Motor TPs (TP19-21, TP26-28, TP33-35, TP40-42) preserved at edge
     positions — they're solder pads, not probe points, already spaced.

DELETION LIST (redundant power TPs):
  TP4, TP6, TP8 — duplicate GNDs on Y=89.5 (keep TP2)
  TP13, TP14, TP15 — duplicate GNDs on Y=47.5 (keep TP12)
  TP18, TP25 — duplicate +3V3s on Y=47.5 (keep TP11)
  TP32, TP39 — duplicate +3V3s on Y=49.5 (keep TP16 GND nearby)

REPITCH (remaining unique TPs on central spine B.Cu):
  Y=47.5 row (5 TPs after deletions): TP11/TP12/TP23/TP24/TP29/TP30
  Y=49.5 row (5 TPs after deletions): TP1/TP31/TP36/TP37/TP43/TP38/TP44/TP16
  Repitch at 5mm pitch.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Redundant duplicates to remove
DELETE_REFS = [
    'TP4', 'TP6', 'TP8',           # duplicate GNDs Y=89.5
    'TP13', 'TP14', 'TP15',        # duplicate GNDs Y=47.5
    'TP18', 'TP25',                # duplicate +3V3s Y=47.5
    'TP32', 'TP39',                # duplicate +3V3s Y=49.5
]

# Repitched positions (after deletions). Sourced from current placement +
# 5mm spacing constraint within central spine X=35-65 zone, B.Cu.
NEW_POSITIONS = {
    # Y=47.5 row — 6 TPs at 5.5mm pitch (TP pads ~2.7mm dia → edge needs ≥2.5)
    'TP11': (35.5, 47.5),  # +3V3
    'TP12': (41.0, 47.5),  # GND
    'TP23': (46.5, 47.5),  # SWCLK_CH1
    'TP24': (52.0, 47.5),  # BOOT0_CH2
    'TP29': (57.5, 47.5),  # SWDIO_CH2
    'TP30': (70.0, 47.5),  # SWCLK_CH2 — moved E to clear TP10 (at 63.8, 45.5)
    # TP10 at (63.8, 45.5) — leave in place; just space TP30 to clear it
    # Y=53.0 row — 8 TPs at 5.5mm pitch with X offset by 2.75mm from Y=47.5
    # so diagonal pairs ≥6.2mm center, vertical pairs same X ≥5.5mm.
    # 6.5mm pitch ensures center≥4 and edge≥2.5 for 1.75mm radius pads
    'TP1':  (38.0, 53.0),   # +V5_FC
    'TP16': (44.5, 53.0),   # GND
    'TP31': (51.0, 53.0),   # BOOT0_CH3
    'TP36': (57.5, 53.0),   # SWDIO_CH3
    'TP37': (64.0, 53.0),   # SWCLK_CH3
    'TP43': (70.5, 53.0),   # SWDIO_CH4
    'TP38': (77.0, 53.0),   # BOOT0_CH4
    'TP44': (83.5, 53.0),   # SWCLK_CH4
    # Y=89.5 row — surviving 3 TPs at 5mm pitch — moved to Y=86 to clear cable zone
    'TP2':  (5.0, 86.0),   # GND
    'TP7':  (15.0, 86.0),  # +V9_VTX1
    'TP9':  (25.0, 86.0),  # +V9_VTX2

    # Catch #5: external connectors moved to S edge (Y=95)
    'J14':  (50.0, 95.0),  # FC SM08B 8-pin — central S edge
    'J12':  (25.0, 95.0),  # AUX BM06B 6-pin — SW S edge

    # Corner LEDs MOVED from S edge to N edge (free cable-bend zone)
    'D3':   (12.0, 2.0),   # PWR LED NW N corner
    'R4':   (15.0, 2.0),   # PWR LED limit-R
    'D4':   (88.0, 2.0),   # RPOL LED NE N corner
    'R5':   (85.0, 2.0),   # RPOL LED limit-R
}


def main():
    # Phase 1: delete redundant TPs + save
    board = pcbnew.LoadBoard(PCB)
    deleted = []
    to_delete = [fp for fp in board.GetFootprints() if fp.GetReference() in DELETE_REFS]
    for fp in to_delete:
        deleted.append(fp.GetReference())
        board.Remove(fp)
    print(f"Deleted {len(deleted)} redundant TPs: {deleted}")
    board.Save(PCB)

    # Phase 2: reload board (clean iterator), reposition, save
    board = pcbnew.LoadBoard(PCB)
    repositioned = []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r in NEW_POSITIONS:
            x, y = NEW_POSITIONS[r]
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
            repositioned.append(r)
    print(f"Repositioned {len(repositioned)} TPs: {repositioned}")
    board.Save(PCB)
    print(f"Saved {PCB}")


if __name__ == "__main__":
    main()
