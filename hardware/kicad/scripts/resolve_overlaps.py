"""PR-A4-e amendment: deterministic pad-overlap resolution per master 2026-05-23.

Algorithm:
  1. Load all placed components from .kicad_pcb (post place_board.py run)
  2. Find pad-pad overlap pairs via bbox_overlap_check (pad-only mode)
  3. For each overlap: identify smaller component (PASSIVE), compute min displacement
     vector to clear overlap + 0.3mm margin
  4. Apply displacement; iterate until 0 overlaps or 50 iterations
  5. Write updated positions to ch234_passives_dict.py OR S4_CH1_PASSIVES if CH1 affected

Outputs:
- Updated ch234_passives_dict.py with new positions
- Audit log of moves applied
"""
import pcbnew
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from verify_placement import bbox_overlap_check

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
MARGIN = 0.3  # mm — JLC pad-pad clearance margin
MAX_ITER = 50

# Refs that are PASSIVES (movable) — anything in CH234_PASSIVES dict or CH1 passive refs
def load_passives_dict():
    from ch234_passives_dict import CH234_PASSIVES
    return dict(CH234_PASSIVES)


def smaller_component(a, b, movable):
    """Return (passive_to_move, fixed). Prefers smaller; tie-breaks by being in movable."""
    a_in = a['ref'] in movable
    b_in = b['ref'] in movable
    if a_in and not b_in:
        return a, b
    if b_in and not a_in:
        return b, a
    # Both movable OR both not — pick smaller bbox; tie-break by higher ref
    a_size = (a['bbox'].GetWidth() / 1e6) * (a['bbox'].GetHeight() / 1e6)
    b_size = (b['bbox'].GetWidth() / 1e6) * (b['bbox'].GetHeight() / 1e6)
    if a_size < b_size:
        return a, b
    if a_size > b_size:
        return b, a
    # Equal size; pick higher ref-number to move
    if a['ref'] > b['ref']:
        return a, b
    return b, a


def compute_displacement(passive, fixed):
    """Compute min displacement vector to clear passive from fixed component.
    Returns (dx, dy) in mm."""
    px = passive['x']
    py = passive['y']
    pad_p = passive['pad_bbox']
    pad_f = fixed['pad_bbox']
    # Bbox in nm; convert to mm via 1e-6
    p_xmin = pad_p.GetPosition().x / 1e6
    p_ymin = pad_p.GetPosition().y / 1e6
    p_xmax = p_xmin + pad_p.GetSize().x / 1e6
    p_ymax = p_ymin + pad_p.GetSize().y / 1e6
    f_xmin = pad_f.GetPosition().x / 1e6
    f_ymin = pad_f.GetPosition().y / 1e6
    f_xmax = f_xmin + pad_f.GetSize().x / 1e6
    f_ymax = f_ymin + pad_f.GetSize().y / 1e6
    # Compute overlap in each axis
    overlap_x = min(p_xmax, f_xmax) - max(p_xmin, f_xmin)
    overlap_y = min(p_ymax, f_ymax) - max(p_ymin, f_ymin)
    # Move in axis of smaller overlap
    if overlap_x < overlap_y:
        # Move in x
        dx = overlap_x + MARGIN
        if px < (f_xmin + f_xmax) / 2:
            dx = -dx
        return (dx, 0.0)
    else:
        dy = overlap_y + MARGIN
        if py < (f_ymin + f_ymax) / 2:
            dy = -dy
        return (0.0, dy)


def main():
    passives = load_passives_dict()
    print(f"Loaded {len(passives)} CH2/3/4 passives")

    # Iterate
    moves_log = []
    for iter_num in range(MAX_ITER):
        # Re-run placement so PCB reflects current dict
        # (assume place_board.py already applied; we modify positions in-place)
        same_layer, _, _ = bbox_overlap_check()
        if len(same_layer) == 0:
            print(f"Iteration {iter_num}: 0 PAD-OVERLAP — DONE")
            break
        print(f"Iteration {iter_num}: {len(same_layer)} overlaps")
        moved_any = False
        # Process every overlap pair this iteration
        moved_refs = set()
        for a, b in same_layer:
            passive_row, fixed_row = smaller_component(a, b, passives)
            ref = passive_row['ref']
            if ref not in passives:
                continue
            if ref in moved_refs:
                continue  # don't move same ref twice per iteration
            dx, dy = compute_displacement(passive_row, fixed_row)
            old = passives[ref]
            new = (old[0] + dx, old[1] + dy, old[2], old[3])
            passives[ref] = new
            moves_log.append((ref, old[:2], new[:2]))
            moved_any = True
            moved_refs.add(ref)
        if not moved_any:
            print(f"No movable passives found — non-passive conflicts remain")
            break
        # Write back to dict file
        with open("hardware/kicad/scripts/ch234_passives_dict.py", "w") as f:
            f.write("CH234_PASSIVES = {\n")
            for ref in sorted(passives.keys()):
                x, y, layer, rot = passives[ref]
                f.write(f"    '{ref}': ({x:.1f}, {y:.1f}, '{layer}', {rot:.1f}),\n")
            f.write("}\n")
        # Re-run place_board to update PCB
        import subprocess
        subprocess.run(["python3", "hardware/kicad/scripts/place_board.py"],
                       capture_output=True, check=True)

    print(f"\nTotal moves applied: {len(moves_log)}")
    return moves_log


if __name__ == "__main__":
    main()
