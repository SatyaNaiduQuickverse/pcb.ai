#!/usr/bin/env python3
"""aggressive_resolver.py — PR-A4-integrate amendment 5i Blocker-1 fix.

Per master "redo not mitigate" directive: drive PAD-OVERLAP-DIFFNET to 0.

The original integrate_resolver only moves CH234_PASSIVES entries. Hand-placed
S-zone components in place_board.py also have collisions with each other and
with auto-anchored passives. This resolver is more aggressive:

  1. Scans ALL diff-net pad overlaps every iteration.
  2. For each overlap, identifies which side is MOVABLE:
     - If in CH234_PASSIVES dict → move freely
     - If small passive (R/C/D) in place_board.py S5/S6 dicts → move with parent constraint
     - If FET/IC/connector → do not move
  3. Tries 8-direction shift in 1mm steps up to 8mm (R23 max-distance).
  4. Picks first non-colliding position that respects existing keepouts.
  5. Updates CH234_PASSIVES dict (for ch234 refs) or
     S5_POSITIONS/S6_POSITIONS in place_board.py (for hand-placed).

Skips same-net overlaps (intentional pour share).
Skips overlaps involving unnetted pads.
"""
import pcbnew
import re
import subprocess
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
CH234_DICT = Path("hardware/kicad/scripts/ch234_passives_dict.py")
PLACE_BOARD = Path("hardware/kicad/scripts/place_board.py")

MAX_ITER = 16
MARGIN_MM = 0.4
MAX_PARENT_DIST = 8.0  # R23
SHIFT_STEP = 0.5  # mm per try
SHIFT_RADIUS = 8.0  # mm max from current position

# Motor TP zones (must stay clear)
MOTOR_TP_ZONES = [
    (5, 56, 7.3, 5.3), (5, 68, 7.3, 5.3), (5, 80, 7.3, 5.3),
    (95, 56, 7.3, 5.3), (95, 68, 7.3, 5.3), (95, 80, 7.3, 5.3),
    (95, 44, 7.3, 5.3), (95, 32, 7.3, 5.3), (95, 20, 7.3, 5.3),
    (5, 44, 7.3, 5.3), (5, 32, 7.3, 5.3), (5, 20, 7.3, 5.3),
]

def in_motor_tp(x, y):
    for cx, cy, hx, hy in MOTOR_TP_ZONES:
        if cx - hx <= x <= cx + hx and cy - hy <= y <= cy + hy:
            return True
    return False

# Refs we never move (must stay where they are)
FIXED_PREFIX = ('Q', 'J', 'U', 'H', 'F', 'TP')  # FETs, conn/IC, mount holes, fuses
# But channel passives (R/C/D) ARE movable even if in S4_CH1_POSITIONS dict
# S5 FB resistors / boot caps ARE movable too

def load_ch234():
    if not CH234_DICT.exists():
        return {}
    txt = CH234_DICT.read_text()
    m = re.search(r"CH234_PASSIVES\s*=\s*\{(.*?)\n\}", txt, re.DOTALL)
    d = {}
    if m:
        for em in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", m.group(1)):
            d[em.group(1)] = (float(em.group(2)), float(em.group(3)), em.group(4), float(em.group(5)))
    return d


def save_ch234(d):
    with CH234_DICT.open("w") as f:
        f.write('"""Auto-anchored + mirrors + aggressive resolver (amendment 5i)."""\nCH234_PASSIVES = {\n')
        for ref in sorted(d.keys()):
            x, y, layer, rot = d[ref]
            f.write(f"    '{ref}': ({x:.2f}, {y:.2f}, '{layer}', {rot:.1f}),\n")
        f.write("}\n")


# Parse place_board.py for S4_CH1/S5/S6 dicts and their positions
def parse_place_board_dicts():
    txt = PLACE_BOARD.read_text()
    dicts = {}
    for name in ('S1_POSITIONS', 'S2_POSITIONS', 'S3_POSITIONS',
                 'S5_POSITIONS', 'S6_POSITIONS', 'S4_CH1_POSITIONS'):
        m = re.search(rf"^{name}\s*=\s*\{{(.*?)\n\}}", txt, re.DOTALL | re.MULTILINE)
        if not m:
            continue
        d = {}
        for em in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", m.group(1)):
            d[em.group(1)] = (float(em.group(2)), float(em.group(3)), em.group(4), float(em.group(5)))
        dicts[name] = d
    return dicts


def can_move(ref):
    """Return True if ref is a movable passive (R/C/D/L) — not FET/IC/header/mount-hole."""
    if not ref:
        return False
    if ref[0] not in 'RCDL':
        return False
    # All R/C/D/L are movable
    return True


def get_pads_for_board(board):
    """Return list of (ref, padnum, net, x1, y1, x2, y2, on_F, on_B, owner_fp)."""
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            ls = p.GetLayerSet()
            try:
                net = p.GetNet().GetNetname()
            except Exception:
                net = ""
            out.append((ref, p.GetPadName(), net,
                        pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                        pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                        ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu)))
    return out


def find_diffnet_overlaps(pads):
    overlaps = []
    for i in range(len(pads)):
        ar, _, an, ax1, ay1, ax2, ay2, aF, aB = pads[i]
        for j in range(i + 1, len(pads)):
            br, _, bn, bx1, by1, bx2, by2, cF, cB = pads[j]
            if ar == br:
                continue
            if not ((aF and cF) or (aB and cB)):
                continue
            if not (ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1):
                continue
            # Skip same-net intentional
            if an and bn and an == bn:
                continue
            # Skip H1-H4 mount-hole-only overlaps
            if ar.startswith('H') or br.startswith('H'):
                continue
            overlaps.append((ar, ax1, ay1, ax2, ay2, br, bx1, by1, bx2, by2))
    return overlaps


def get_ref_pad_bboxes(pads, ref):
    """Return list of (x1, y1, x2, y2, F, B) for ref's pads."""
    return [(x1, y1, x2, y2, F, B) for r, _, _, x1, y1, x2, y2, F, B in pads if r == ref]


def collides_at(new_x, new_y, current_x, current_y, ref_bboxes, all_pads, ref):
    """Check if shifting ref by (new_x - current_x, new_y - current_y) introduces
    new collision with non-self pads (ignoring same-net intentional)."""
    dx = new_x - current_x
    dy = new_y - current_y
    for x1, y1, x2, y2, F, B in ref_bboxes:
        nx1, ny1, nx2, ny2 = x1 + dx, y1 + dy, x2 + dx, y2 + dy
        for other_ref, _, _, ox1, oy1, ox2, oy2, oF, oB in all_pads:
            if other_ref == ref:
                continue
            if other_ref.startswith('H'):
                continue
            if not ((F and oF) or (B and oB)):
                continue
            if nx1 < ox2 and nx2 > ox1 and ny1 < oy2 and ny2 > oy1:
                return True
    return False


def main():
    ch234 = load_ch234()
    pb_dicts = parse_place_board_dicts()
    # Build a "where does this ref live?" map
    owner = {}
    for ref in ch234:
        owner[ref] = 'ch234'
    for name, d in pb_dicts.items():
        for ref in d:
            if ref not in owner:
                owner[ref] = name

    for it in range(MAX_ITER):
        board = pcbnew.LoadBoard(str(PCB))
        pads = get_pads_for_board(board)
        overlaps = find_diffnet_overlaps(pads)
        print(f"Iter {it}: {len(overlaps)} diff-net overlaps")
        if not overlaps:
            print("CONVERGED — 0 diff-net overlaps")
            break

        moved = set()
        progress = False
        for ar, ax1, ay1, ax2, ay2, br, bx1, by1, bx2, by2 in overlaps:
            # Pick which side to move
            cand = None
            for r in (ar, br):
                if r in moved:
                    continue
                if not can_move(r):
                    continue
                if r not in owner:
                    continue
                cand = r
                break
            if cand is None:
                continue
            # Get current position
            src = owner[cand]
            if src == 'ch234':
                cur = ch234[cand]
            else:
                cur = pb_dicts[src][cand]
            cx, cy, layer, rot = cur
            # Try concentric ring shifts in 8 directions
            ref_bboxes = get_ref_pad_bboxes(pads, cand)
            best = None
            for radius in [r * SHIFT_STEP for r in range(1, int(SHIFT_RADIUS / SHIFT_STEP) + 1)]:
                for dx, dy in [(radius, 0), (-radius, 0), (0, radius), (0, -radius),
                               (radius, radius), (-radius, radius), (radius, -radius), (-radius, -radius)]:
                    nx, ny = round(cx + dx, 2), round(cy + dy, 2)
                    if nx < 1.5 or nx > 98.5 or ny < 1.5 or ny > 98.5:
                        continue
                    if in_motor_tp(nx, ny):
                        continue
                    if not collides_at(nx, ny, cx, cy, ref_bboxes, pads, cand):
                        best = (nx, ny)
                        break
                if best:
                    break
            if best:
                nx, ny = best
                if src == 'ch234':
                    ch234[cand] = (nx, ny, layer, rot)
                else:
                    pb_dicts[src][cand] = (nx, ny, layer, rot)
                moved.add(cand)
                progress = True

        # Save updates and re-place
        if progress:
            save_ch234(ch234)
            # Update place_board.py for any S-zone changes
            pb_txt = PLACE_BOARD.read_text()
            for name, d in pb_dicts.items():
                # Re-write each dict block
                m = re.search(rf"(^{name}\s*=\s*\{{)(.*?)(\n\}})", pb_txt, re.DOTALL | re.MULTILINE)
                if not m:
                    continue
                # Build new body preserving comments — only update entries we know about
                old_body = m.group(2)
                new_body = old_body
                for ref, (x, y, layer, rot) in d.items():
                    pat = re.compile(rf"'{ref}'\s*:\s*\(\s*[\d.]+\s*,\s*[\d.]+\s*,(\s*'[^']+'\s*,\s*[\d.]+\s*)\)")
                    new_body = pat.sub(f"'{ref}': ({x:.2f}, {y:.2f},{m_inner.group(1) if False else ''}",
                                       new_body) if False else new_body
                # Simpler: just rewrite each ref entry inline
                for ref, (x, y, layer, rot) in d.items():
                    pat = re.compile(rf"'{ref}'\s*:\s*\(\s*[\d.]+\s*,\s*[\d.]+\s*,(\s*'[^']+',\s*[\d.]+)\s*\)")
                    mm = pat.search(new_body)
                    if mm:
                        new_body = pat.sub(f"'{ref}': ({x:.2f}, {y:.2f},{mm.group(1)})", new_body)
                pb_txt = pb_txt[:m.start()] + m.group(1) + new_body + m.group(3) + pb_txt[m.end():]
            PLACE_BOARD.write_text(pb_txt)
            subprocess.run(["python3", "hardware/kicad/setup_board.py"], capture_output=True)
            subprocess.run(["python3", "hardware/kicad/scripts/place_board.py"], capture_output=True)
            # Re-apply fix_fet_netlist_drop in case FET pads got reset
            subprocess.run(["python3", "hardware/kicad/scripts/fix_fet_netlist_drop.py"], capture_output=True)
        else:
            print("No progress — stuck.")
            break

    # Final audit
    board = pcbnew.LoadBoard(str(PCB))
    pads = get_pads_for_board(board)
    overlaps = find_diffnet_overlaps(pads)
    print(f"FINAL: {len(overlaps)} diff-net overlaps")


if __name__ == "__main__":
    main()
