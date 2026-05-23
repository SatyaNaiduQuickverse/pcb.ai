#!/usr/bin/env python3
"""clear_motor_tp_zones.py — PR-A4-integrate Defect 2 fix.

12 motor terminal pads (TP19-42) need clear-zones for 14-16AWG motor wire
soldering. Each pad bbox + 2mm keep-out must contain zero other component
centers.

Sai-caught defect 2026-05-23: 73 components (auto-anchored debris) sitting
inside motor-TP zones. Relocate each to clear the zone, pushing inward
toward X=50 axis. Updates CH234_PASSIVES dict + re-runs place_board.

Mirror symmetry preserved: any move applied to a CH1 ref propagates via
mirror_ch1_to_ch234.py to CH2/CH3/CH4 on subsequent pipeline run.
"""
import pcbnew
import re
import subprocess
from pathlib import Path

PCB = "hardware/kicad/pcbai_fpv4in1.kicad_pcb"
CH234_DICT = Path("hardware/kicad/scripts/ch234_passives_dict.py")
PLACE_BOARD = Path("hardware/kicad/scripts/place_board.py")
MOTOR_TPS = ['TP19','TP20','TP21','TP26','TP27','TP28','TP33','TP34','TP35','TP40','TP41','TP42']
KEEPOUT = 2.0  # mm beyond pad bbox

# Safe-X for each side (half_x=7.3 + small margin)
SAFE_LEFT = 15.0   # for TPs at X=5 — push encroachers to X ≥ 15.0 (zone right edge ~12.3)
SAFE_RIGHT = 85.0  # for TPs at X=95 — push encroachers to X ≤ 85.0 (zone left edge ~87.7)


def get_tp_zones(board):
    zones = {}
    for fp in board.GetFootprints():
        if fp.GetReference() in MOTOR_TPS:
            bb = fp.GetBoundingBox()
            zones[fp.GetReference()] = (
                pcbnew.ToMM(bb.GetLeft()) - KEEPOUT,
                pcbnew.ToMM(bb.GetTop()) - KEEPOUT,
                pcbnew.ToMM(bb.GetRight()) + KEEPOUT,
                pcbnew.ToMM(bb.GetBottom()) + KEEPOUT,
                pcbnew.ToMM(fp.GetPosition().x),
            )
    return zones


def find_encroachers(board, zones):
    """Return list of (ref, cx, cy, tp_ref, tp_center_x)."""
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in MOTOR_TPS:
            continue
        if ref.startswith(('Q', 'J', 'U', 'H')):
            continue
        pos = fp.GetPosition()
        cx, cy = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        for tp, (x1, y1, x2, y2, tcx) in zones.items():
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                out.append((ref, cx, cy, tp, tcx))
                break
    return out


def load_ch234_dict():
    txt = CH234_DICT.read_text()
    d = {}
    m = re.search(r"CH234_PASSIVES\s*=\s*\{(.*?)\n\}", txt, re.DOTALL)
    if m:
        for em in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", m.group(1)):
            d[em.group(1)] = (float(em.group(2)), float(em.group(3)),
                               em.group(4), float(em.group(5)))
    return d


def save_ch234_dict(d):
    with open(CH234_DICT, "w") as f:
        f.write('"""Auto-anchored + mirrors + integrate-resolver outputs.\n"""\n')
        f.write("CH234_PASSIVES = {\n")
        for ref in sorted(d.keys()):
            x, y, layer, rot = d[ref]
            f.write(f"    '{ref}': ({x:.2f}, {y:.2f}, '{layer}', {rot:.1f}),\n")
        f.write("}\n")


def main():
    board = pcbnew.LoadBoard(PCB)
    zones = get_tp_zones(board)
    enc = find_encroachers(board, zones)
    print(f"Found {len(enc)} encroachers across {len(set(e[3] for e in enc))} TPs")

    # Move each: keep Y, set X to safe-side based on TP center
    placements = load_ch234_dict()
    placed_text = PLACE_BOARD.read_text()
    moved_dict = 0
    moved_placed = 0
    not_owned = []
    plan = []
    for ref, cx, cy, tp, tcx in enc:
        if tcx < 50:  # TP on left edge — push right
            new_x = SAFE_LEFT
        else:         # TP on right edge — push left
            new_x = SAFE_RIGHT
        plan.append((ref, cx, cy, new_x, cy, tp))
        if ref in placements:
            old = placements[ref]
            placements[ref] = (new_x, cy, old[2], old[3])
            moved_dict += 1
        else:
            # Try to patch place_board.py directly — many of these are in
            # the placements dict in place_board.py (hand-placed S* zone refs).
            pat = re.compile(rf"'{ref}'\s*:\s*\(\s*[\d.]+\s*,\s*[\d.]+\s*,(\s*'[^']+',\s*[\d.]+\s*)\)")
            m = pat.search(placed_text)
            if m:
                placed_text = pat.sub(f"'{ref}': ({new_x:.2f}, {cy:.2f},{m.group(1)})", placed_text)
                moved_placed += 1
            else:
                not_owned.append(ref)

    save_ch234_dict(placements)
    if moved_placed:
        PLACE_BOARD.write_text(placed_text)
    print(f"Moved {moved_dict} via ch234_passives_dict, {moved_placed} via place_board.py")
    if not_owned:
        print(f"Not owned by either (orphan auto-anchor): {not_owned}")

    print("\nRelocation plan:")
    for r, ox, oy, nx, ny, tp in plan:
        print(f"  {r}: ({ox:.1f},{oy:.1f}) → ({nx:.1f},{ny:.1f})  [out of {tp}]")

    # Re-run placement pipeline to apply
    print("\nRunning place_board + setup_board ...")
    subprocess.run(["python3", "hardware/kicad/setup_board.py"], check=False)
    subprocess.run(["python3", "hardware/kicad/scripts/place_board.py"], check=False)


if __name__ == "__main__":
    main()
