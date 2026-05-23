#!/usr/bin/env python3
"""surgical_clear.py — final-mile pad-overlap surgery for amendment 5l.

Targeted moves for the remaining 23 overlap pairs. Each rule shifts one
component 1-3mm to clear its conflict, preserving channel symmetry where
applicable via mirror propagation.

Uses pcbnew API to apply moves directly to the board (post place_board),
then saves. This bypasses the dict-text-edit path which has been
unreliable for some refs.
"""
import pcbnew

PCB = "hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# (ref, new_x, new_y, layer) — None layer means keep current
MOVES = [
    # Surgery 2: C17 BUCK4 boot cap was moved to (55.5, 87) on top of R37.
    # Move back near J5 BUCK4 IC (57, 80) — 2.5mm E for boot pin proximity.
    ('C17', 59.5, 80.0, 'F.Cu'),
    # R37 VBAT divider stays at (50.5, 84) per 5c.
    ('R37', 50.5, 84.0, 'F.Cu'),
    # Surgery 1: J6 BUCK#5 SOIC-8 at (88, 22) overlaps Q21 PDFN-8 at (88, 20).
    # Q21 bbox 85-91, 17-23. J6 SOIC bbox 84-92, 18-26. Move J6 N by 5mm to (88, 27).
    ('J6', 88.0, 27.0, 'F.Cu'),
    # D9 Buck#5 catch diode at (88, 38) overlaps R132 CH3 shunt at (86.5, 40).
    # Move D9 N to (88, 33) — clear of R132 (which is the 2512 shunt).
    ('D9', 88.0, 33.0, 'F.Cu'),
    # Surgery: J9 V5_AI eFuse at (90, 14) overlaps R134 CH3 shunt at (86.5, 16).
    # Move J9 N by 4mm to (90, 18) — clears 2512 shunt's south edge.
    # Wait — R134 is at (86.5, 16) which is 2512 (6.3mm wide). Move J9 further from R134.
    # Better: leave J9 in S1 strip, move R134 N by 2mm.
    ('R134', 86.5, 18.0, 'F.Cu'),
    # Surgery: J7 V5_FC eFuse at (15, 14) overlaps R172 CH4 channel ref at (13.5, 16).
    # R172 is auto-anchored channel passive in CH4 SW. Move R172 W to (10.5, 16).
    ('R172', 10.5, 16.0, 'F.Cu'),
    # Surgery 3: J4 BUCK3 SOIC at (57, 72) overlaps D48 LED at (55, 70).
    # Move D48 N+W by 3mm to clear J4 bbox.
    ('D48', 55.0, 68.0, 'F.Cu'),
    # Surgery 4: U2 SOT-23 (38, 86) ↔ J15 USBLC6 (40, 85).
    # U2/J15 west boundary collision. Move J15 W to (37, 85) — clears U2.
    # But mirror partner J16 NE at (60, 85) needs corresponding move.
    # J15/J16 USBLC6 — MIGRATE to B.Cu (non-critical ESD on data lines).
    # Stays at original X=40/X=60 but flipped to B.Cu, clearing F.Cu U-clusters.
    ('J15', 40.0, 85.0, 'B.Cu'),
    ('J16', 60.0, 85.0, 'B.Cu'),
    # D66 LED — move away from J6 new pos (88, 27). To (95, 35).
    # ('D66', 95.0, 35.0, 'F.Cu'),  # no longer needed after Buck#5 SW revert
    # J6 new pos (88, 27): R133 at (86.5, 28) — Buck#5 still close. R15 at (86.5, 22) is below J6.
    # Move J6 to (95, 27) — board edge, fully clear of CH3 components at X<92.
    # ('J6', 95.0, 27.0, 'F.Cu'),  # reverted to SW per place_board
    # Surgery 4b: U3 LM393 (45, 84) ↔ J15 NW. With J15 → (37, 85), J15 pads at X=35.7-38.3.
    # U3 west pad at X=41.55. Clear.
    # Same-spot R129/R176 (48, 85) B.Cu — both at same position. Likely mirror script left
    # CH1 R129 and CH3-180-rot R176 both landing at (48, 85). Spread.
    ('R129', 47.0, 85.0, 'B.Cu'),  # CH1 — move W 1mm
    ('R176', 49.0, 85.0, 'B.Cu'),  # CH3 — move E 1mm (180-rot of 47 wouldn't be 49, but acceptable spread)
    # R144/R183 same-spot (52, 70) B.Cu.
    ('R144', 51.0, 70.0, 'B.Cu'),
    ('R183', 53.0, 70.0, 'B.Cu'),
]


def main():
    board = pcbnew.LoadBoard(PCB)
    moved = 0
    not_found = []
    for ref, nx, ny, layer in MOVES:
        fp = None
        for f in board.GetFootprints():
            if f.GetReference() == ref:
                fp = f
                break
        if fp is None:
            not_found.append(ref)
            continue
        new_pos = pcbnew.VECTOR2I(pcbnew.FromMM(nx), pcbnew.FromMM(ny))
        fp.SetPosition(new_pos)
        # Layer flip if needed
        target = pcbnew.F_Cu if layer == 'F.Cu' else pcbnew.B_Cu
        if fp.GetLayer() != target:
            fp.Flip(new_pos, False)
        moved += 1
    print(f"Moved {moved}/{len(MOVES)} components.")
    if not_found:
        print(f"Not found: {not_found}")
    board.Save(PCB)
    print(f"Saved {PCB}")


if __name__ == "__main__":
    main()
