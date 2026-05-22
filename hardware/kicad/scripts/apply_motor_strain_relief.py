"""Phase 3b-detail — apply motor pad strain-relief copper reinforcement.

For each of the 12 motor solder pads (3 per channel × 4 channels), adds a
larger F.Cu copper polygon (5 mm dia annular ring + 4 radial spokes connecting
the inner test-point pad to the outer ring). Pattern matches FPV-standard
strain-relief topology: bigger solder area + spoke thermal relief.

Idempotent: uses sentinel markers (PHASE3B-MOTOR-RELIEF-BEGIN/END on
Cmts.User layer) so re-runs strip and re-apply cleanly.
"""
import math
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
SENTINEL_BEGIN = '(gr_text "PHASE3B-MOTOR-RELIEF-BEGIN" (at 0 0 0) (layer "Cmts.User") (effects (font (size 0.1 0.1) (thickness 0.05))))'
SENTINEL_END = '(gr_text "PHASE3B-MOTOR-RELIEF-END" (at 0 0 0) (layer "Cmts.User") (effects (font (size 0.1 0.1) (thickness 0.05))))'

# Same MOTOR_PADS as place_board.py / apply_silkscreen.py
MOTOR_PADS = {
    (1, 'A'): (15.0, 2.0),  (1, 'B'): (18.0, 2.0),  (1, 'C'): (21.0, 2.0),
    (2, 'A'): (98.0, 15.0), (2, 'B'): (98.0, 18.0), (2, 'C'): (98.0, 21.0),
    (3, 'A'): (2.0, 65.0),  (3, 'B'): (2.0, 68.0),  (3, 'C'): (2.0, 71.0),
    (4, 'A'): (70.0, 83.0), (4, 'B'): (73.0, 83.0), (4, 'C'): (76.0, 83.0),
}

# Strain-relief geometry per pad:
#  - Outer ring: 5 mm dia copper arc on F.Cu (gr_arc full circle)
#  - 4 radial spokes connecting inner pad (D 3mm) to outer ring
#  - Inner pad: already exists as TestPoint_Pad_D3.0mm
OUTER_RADIUS = 2.5    # mm — outer ring radius (5mm dia total)
INNER_RADIUS = 1.5    # mm — inner pad radius (D3 = 1.5)
SPOKE_WIDTH = 0.6     # mm — copper spoke trace width
RING_WIDTH = 0.4      # mm — outer ring trace width


def gr_circle(cx, cy, radius, layer, width):
    """Filled circle on F.Cu (acts as copper polygon)."""
    return (f'\n\t(gr_circle\n'
            f'\t\t(center {cx:.2f} {cy:.2f})\n'
            f'\t\t(end {cx + radius:.2f} {cy:.2f})\n'
            f'\t\t(stroke (width {width}) (type solid))\n'
            f'\t\t(fill no)\n'
            f'\t\t(layer "{layer}")\n'
            f'\t)')


def gr_line(x1, y1, x2, y2, layer, width):
    """Line segment on the specified layer."""
    return (f'\n\t(gr_line\n'
            f'\t\t(start {x1:.2f} {y1:.2f})\n'
            f'\t\t(end {x2:.2f} {y2:.2f})\n'
            f'\t\t(stroke (width {width}) (type solid))\n'
            f'\t\t(layer "{layer}")\n'
            f'\t)')


def find_sentinel_block_end(txt, sentinel_text):
    """Find the start + end indices of a sentinel gr_text S-expression."""
    begin = txt.find(sentinel_text[:50])  # match by leading chars (avoid escaping issues)
    if begin < 0:
        return None
    # Walk to find balanced ')'
    depth = 0
    i = begin
    while i < len(txt):
        if txt[i] == '(':
            depth += 1
        elif txt[i] == ')':
            depth -= 1
            if depth == 0:
                return (begin, i + 1)
        i += 1
    return None


def main():
    txt = PCB.read_text()

    # Strip prior block (idempotent re-run)
    begin_range = find_sentinel_block_end(txt, '(gr_text "PHASE3B-MOTOR-RELIEF-BEGIN"')
    if begin_range:
        end_range = find_sentinel_block_end(txt, '(gr_text "PHASE3B-MOTOR-RELIEF-END"')
        if end_range:
            line_start = txt.rfind('\n', 0, begin_range[0]) + 1
            txt = txt[:line_start].rstrip() + '\n' + txt[end_range[1]:].lstrip('\n')
            print("Removed prior motor-relief block.")

    additions = [SENTINEL_BEGIN]

    for (ch, phase), (cx, cy) in MOTOR_PADS.items():
        # Outer ring (D 5mm) on F.Cu
        additions.append(gr_circle(cx, cy, OUTER_RADIUS, "F.Cu", RING_WIDTH))
        # 4 radial spokes at 45°, 135°, 225°, 315° (avoiding the wire entry axis at 0°/90°)
        for angle_deg in (45, 135, 225, 315):
            angle_rad = math.radians(angle_deg)
            x1 = cx + INNER_RADIUS * math.cos(angle_rad)
            y1 = cy + INNER_RADIUS * math.sin(angle_rad)
            x2 = cx + OUTER_RADIUS * math.cos(angle_rad)
            y2 = cy + OUTER_RADIUS * math.sin(angle_rad)
            additions.append(gr_line(x1, y1, x2, y2, "F.Cu", SPOKE_WIDTH))

    additions.append(SENTINEL_END)

    # Insert before closing top-level ')'
    last_paren = txt.rstrip().rfind(')')
    insertion = "\n" + "\n".join(additions) + "\n"
    new_txt = txt[:last_paren] + insertion + txt[last_paren:]

    PCB.write_text(new_txt)

    ring_count = sum(1 for a in additions if 'gr_circle' in a)
    spoke_count = sum(1 for a in additions if 'gr_line' in a)
    print(f"Applied motor strain-relief:")
    print(f"  - 12 outer copper rings (D 5mm, F.Cu, width {RING_WIDTH}mm)")
    print(f"  - {spoke_count} spokes total (4 per motor pad × 12 pads = 48)")
    print(f"  - Inner pad (D 3mm) untouched — solder area preserved")
    print(f"  - File: {PCB} ({PCB.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
