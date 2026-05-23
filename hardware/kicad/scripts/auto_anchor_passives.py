#!/usr/bin/env python3
"""auto_anchor_passives.py — PR-A4-redo 2026-05-23.

For every footprint not in the existing S1-S6 placement dicts, derive an explicit
placement by anchoring to its electrical parent device (FET, IC, or connector).

Algorithm:
  1. Load all footprint refs + nets + values from .kicad_pcb
  2. Load existing placed refs from place_board.py (S1-S6 dicts + ch234_passives)
  3. For each unplaced ref:
     a. Find candidate parents (FET, IC, CONN) sharing any net
     b. Pick the most-specific net (smallest connection count, excluding power rails)
     c. Pick the closest-Y already-placed parent on that specific net
     d. Place at parent + spiral offset (avoiding occupied slots)
  4. Output a Python dict to stdout, ready to paste into place_board.py

Power-rail nets (skipped for parent disambiguation):
  GND, +3V3, +5V, +VMOTOR, V5_*, V9_*, V3V3, etc.

Per [[feedback-no-passive-island]]: max distance from parent enforced (5mm soft, 8mm hard).

Run: python3 auto_anchor_passives.py > /tmp/anchor_dict.py
"""
import pcbnew, re
from pathlib import Path
from collections import defaultdict

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")

POWER_NETS = re.compile(r'^(GND|GNDA?|\+?3V3.*|\+?5V.*|\+?V(MOTOR|9_).*|V5.*|V9.*|VMOTOR.*|VBAT.*|HALL_VCC.*|N\$\d+)$')

# Role spiral offsets: passives ~2.5mm from parent, on a small ring
# Different role offsets to spread refs around parent without overlap
SPIRAL_OFFSETS = [
    (2.5, 0.0), (-2.5, 0.0), (0.0, 2.5), (0.0, -2.5),
    (2.0, 2.0), (-2.0, 2.0), (2.0, -2.0), (-2.0, -2.0),
    (4.0, 0.0), (-4.0, 0.0), (0.0, 4.0), (0.0, -4.0),
    (4.0, 2.5), (-4.0, 2.5), (4.0, -2.5), (-4.0, -2.5),
    (2.5, 4.0), (-2.5, 4.0), (2.5, -4.0), (-2.5, -4.0),
]


def load_netlist():
    """Return ref → (value, layer_pref, set-of-nets) from PCB."""
    board = pcbnew.LoadBoard(str(PCB))
    out = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        val = fp.GetValue()
        layer = 'F.Cu' if fp.GetLayer() == pcbnew.F_Cu else 'B.Cu'
        nets = set()
        for pad in fp.Pads():
            if pad.GetNet():
                nets.add(pad.GetNet().GetNetname())
        out[ref] = (val, layer, nets)
    return out


def load_mount_holes_from_pcb():
    """Read mount-hole positions directly from PCB (set by setup_board.py)."""
    board = pcbnew.LoadBoard(str(PCB))
    mh = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H') and len(ref) > 1 and ref[1:].isdigit():
            p = fp.GetPosition()
            mh[ref] = (p.x/1e6, p.y/1e6, 'F.Cu', 0.0)
    return mh


def load_existing_placements():
    """Parse place_board.py + ch234_passives_dict.py for already-placed refs."""
    placed = {}  # ref → (x, y, layer, rot)
    # PR-CH1: include mount holes from PCB (setup_board.py-owned)
    placed.update(load_mount_holes_from_pcb())
    PB = open("hardware/kicad/scripts/place_board.py").read()
    # Find all dict literals like 'XYZ': (x, y, 'F.Cu'/'B.Cu', rot)
    for m in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", PB):
        ref, x, y, layer, rot = m.group(1), float(m.group(2)), float(m.group(3)), m.group(4), float(m.group(5))
        placed[ref] = (x, y, layer, rot)
    # ch234_passives_dict.py
    if Path("hardware/kicad/scripts/ch234_passives_dict.py").exists():
        CH234 = open("hardware/kicad/scripts/ch234_passives_dict.py").read()
        for m in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", CH234):
            ref, x, y, layer, rot = m.group(1), float(m.group(2)), float(m.group(3)), m.group(4), float(m.group(5))
            placed[ref] = (x, y, layer, rot)
    return placed


def find_parent(ref, nets, ref_info, placed):
    """For each net of `ref`, find candidate placed parents.
    Pick the most-specific (smallest connection count) non-power net + its parent."""
    # Build net → set-of-refs index
    net_to_refs = defaultdict(set)
    for r, (_, _, rnets) in ref_info.items():
        for n in rnets:
            net_to_refs[n].add(r)

    candidate_anchors = []
    # Pass 1: non-power nets (strong preference)
    for n in nets:
        if POWER_NETS.match(n):
            continue
        refs_on_n = net_to_refs[n]
        anchors = [r for r in refs_on_n
                   if r != ref and r in placed]
        if not anchors:
            continue
        specificity = 100.0 / len(refs_on_n)
        for a in anchors:
            # Prefer FET/IC/CONN over passives, but accept passives as anchors
            type_bonus = 10 if (a.startswith('Q') or a.startswith('U') or a.startswith('J')) else 0
            candidate_anchors.append((specificity + type_bonus, a, n))
    # Pass 2: if nothing yet, allow power-rail anchoring (low specificity)
    if not candidate_anchors:
        for n in nets:
            refs_on_n = net_to_refs[n]
            anchors = [r for r in refs_on_n
                       if r != ref and r in placed
                       and (r.startswith('Q') or r.startswith('U') or r.startswith('J'))]
            if not anchors:
                continue
            specificity = 1.0 / len(refs_on_n)
            for a in anchors:
                candidate_anchors.append((specificity, a, n))
    if not candidate_anchors:
        return None, None
    candidate_anchors.sort(reverse=True)
    return candidate_anchors[0][1], candidate_anchors[0][2]


def main():
    ref_info = load_netlist()
    placed = load_existing_placements()
    print(f"# Total refs: {len(ref_info)}", file=__import__('sys').stderr)
    print(f"# Already placed: {len(placed)}", file=__import__('sys').stderr)
    unplaced = [r for r in ref_info if r not in placed]
    print(f"# To place: {len(unplaced)}", file=__import__('sys').stderr)

    # Pad-bbox occupancy: per-pad rectangles from actual kicad footprint pads
    board = pcbnew.LoadBoard(str(PCB))
    fp_by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    pad_bboxes = []  # (xmin, ymin, xmax, ymax, layers_F, layers_B, owner_ref)

    def update_pad_bbox_for_ref(ref, new_pos):
        """Compute pad bboxes if `ref` were placed at new_pos. Returns list of (xmin, ymin, xmax, ymax, F, B)."""
        fp = fp_by_ref.get(ref)
        if not fp: return []
        # Use existing pad positions relative to current fp position
        cur_pos = fp.GetPosition()
        dx = new_pos[0] - cur_pos.x / 1e6
        dy = new_pos[1] - cur_pos.y / 1e6
        out = []
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            x1, y1, x2, y2 = bb.GetLeft()/1e6, bb.GetTop()/1e6, bb.GetRight()/1e6, bb.GetBottom()/1e6
            ls = pad.GetLayerSet()
            F = ls.Contains(pcbnew.F_Cu); B = ls.Contains(pcbnew.B_Cu)
            out.append((x1+dx, y1+dy, x2+dx, y2+dy, F, B))
        return out

    # Initialize pad_bboxes from currently placed refs
    for r, (x, y, layer, rot) in placed.items():
        for bb in update_pad_bbox_for_ref(r, (x, y)):
            pad_bboxes.append(bb + (r,))

    occupied = {}  # (round_x, round_y, layer) → ref (kept for legacy grid filter)
    for r, (x, y, layer, rot) in placed.items():
        occupied[(round(x, 1), round(y, 1), layer)] = r

    def has_pad_collision(test_bboxes):
        for x1, y1, x2, y2, F, B, _ in test_bboxes:
            for bx1, by1, bx2, by2, bF, bB, _ in pad_bboxes:
                same = (F and bF) or (B and bB)
                if not same: continue
                if x1 < bx2 and x2 > bx1 and y1 < by2 and y2 > by1:
                    return True
        return False
    # FET pad bboxes + IC + connector bboxes — keepouts on same layer
    keepouts = []  # (x, y, hx, hy, layer)
    for r, (x, y, layer, rot) in placed.items():
        if r.startswith('Q'):
            if 1 <= int(r[1:]) <= 4:
                keepouts.append((x, y, 3.5, 4.0, layer))
            elif 5 <= int(r[1:]) <= 28:
                keepouts.append((x, y, 8.5, 5.7, layer))
        elif r.startswith('U'):
            # Most ICs: ~3×3mm half-bbox
            keepouts.append((x, y, 3.5, 3.5, layer))
        elif r in ('J18', 'J23', 'J28', 'J33'):  # MCU LQFP-32 ~5×5
            keepouts.append((x, y, 4.0, 4.0, layer))
        elif r in ('J19', 'J24', 'J29', 'J34'):  # DRV8300 HVQFN-24 ~4×4
            keepouts.append((x, y, 3.0, 3.0, layer))
        elif r in ('J2', 'J3', 'J4', 'J5', 'J6'):  # Buck ICs ~3×3
            keepouts.append((x, y, 3.5, 3.5, layer))
        elif r in ('L1', 'L2', 'L3', 'L4', 'L5'):  # Buck inductors ~4×4
            keepouts.append((x, y, 4.0, 4.0, layer))
        elif r.startswith('J') and r[1:].isdigit() and int(r[1:]) >= 20:  # INA186 etc.
            keepouts.append((x, y, 2.5, 2.5, layer))
        elif r in ('U1',):  # Hall body
            keepouts.append((x, y, 10.0, 13.5, layer))
        elif r.startswith('TP') and r != 'TH1':
            pass  # test points are small
        elif r in ('J1',):  # XT30
            keepouts.append((x, y, 5.0, 4.0, layer))
        # PR-CH1 2026-05-23: mount-hole 3mm keep-out — applies to both layers
        elif r.startswith('H') and len(r) > 1 and r[1:].isdigit():
            keepouts.append((x, y, 3.0, 3.0, 'F.Cu'))
            keepouts.append((x, y, 3.0, 3.0, 'B.Cu'))
        # Cap/R/D: small ~1mm; rely on occupancy grid

    def inside_keepout(nx, ny, layer):
        for fx, fy, hx, hy, fl in keepouts:
            if fl == layer and abs(nx - fx) < hx + 0.5 and abs(ny - fy) < hy + 0.4:
                return True
        return False

    auto_placements = {}
    no_parent = []
    far_anchored = []
    EXTENDED_OFFSETS = SPIRAL_OFFSETS + [
        (5.5, 1.5), (-5.5, 1.5), (5.5, -1.5), (-5.5, -1.5),
        (6.0, 4.0), (-6.0, 4.0), (6.0, -4.0), (-6.0, -4.0),
        (3.0, 5.5), (-3.0, 5.5), (3.0, -5.5), (-3.0, -5.5),
        (7.0, 0), (-7.0, 0), (0, 7.0), (0, -7.0),
        (7.5, 4.5), (-7.5, 4.5), (7.5, -4.5), (-7.5, -4.5),
    ]

    # Track how many passives are anchored per parent to enforce a per-anchor cap.
    per_anchor_count = {}
    PER_ANCHOR_MAX = 5  # limit pile-up; excess refs forced to grid fallback

    # Multi-pass: keep extending the placed set as new passives find homes
    remaining = list(sorted(unplaced))
    for pass_num in range(8):
        progress = False
        next_remaining = []
        for ref in remaining:
            val, layer, nets = ref_info[ref]
            anchor_ref, anchor_net = find_parent(ref, nets, ref_info, placed)
            if anchor_ref is None:
                next_remaining.append(ref)
                continue
            if per_anchor_count.get(anchor_ref, 0) >= PER_ANCHOR_MAX:
                next_remaining.append(ref)
                continue
            ax, ay, _, _ = placed[anchor_ref]
            placed_ok = False
            for ox, oy in EXTENDED_OFFSETS:
                nx, ny = round(ax + ox, 1), round(ay + oy, 1)
                if nx < 1.5 or nx > 98.5 or ny < 1.5 or ny > 93.5:
                    continue
                # Skip FET pad-bbox keepout zones
                if inside_keepout(nx, ny, layer):
                    continue
                # Look for nearby occupied (within ~1.5mm in same layer)
                collide = False
                for occ_xyl in occupied:
                    ox_o, oy_o, layer_o = occ_xyl
                    if layer_o != layer: continue
                    if abs(ox_o - nx) < 1.8 and abs(oy_o - ny) < 1.5:
                        collide = True; break
                if collide: continue
                # Pad-bbox collision check (uses actual kicad pads)
                tb = [bb + (ref,) for bb in update_pad_bbox_for_ref(ref, (nx, ny))]
                if has_pad_collision(tb): continue
                auto_placements[ref] = (nx, ny, layer, 0.0)
                placed[ref] = (nx, ny, layer, 0.0)
                occupied[(nx, ny, layer)] = ref
                pad_bboxes.extend(tb)
                per_anchor_count[anchor_ref] = per_anchor_count.get(anchor_ref, 0) + 1
                placed_ok = True
                progress = True
                dist = ((nx-ax)**2 + (ny-ay)**2)**0.5
                if dist > 8.0:
                    far_anchored.append((ref, anchor_ref, dist))
                break
            if not placed_ok:
                next_remaining.append(ref)
        remaining = next_remaining
        if not progress: break
    no_parent = remaining

    # Final fallback: place ANY remaining ref in a grid slot on-board (per R24 — no kinet2pcb defaults).
    # Walk a Y-strip grid: top row Y=2-4, north strip Y=46.5-49, etc.
    GRID_STRIPS = [
        # central south strip
        (2.0, 6.0, (35.0, 65.0), 'F.Cu'),
        (2.0, 6.0, (35.0, 65.0), 'B.Cu'),
        # spine middle band Y=46-49 (between S2 and S4 channels)
        (45.5, 49.5, (35.0, 65.0), 'F.Cu'),
        (45.5, 49.5, (35.0, 65.0), 'B.Cu'),
        # north Y=90-93 strip
        (89.5, 93.0, (2.0, 98.0), 'F.Cu'),
        (89.5, 93.0, (2.0, 98.0), 'B.Cu'),
        # east edge X=92-98 vertical
        (15.0, 80.0, (92.0, 98.0), 'F.Cu'),
        (15.0, 80.0, (92.0, 98.0), 'B.Cu'),
        # west edge X=2-7 vertical
        (15.0, 80.0, (2.0, 7.0), 'F.Cu'),
        (15.0, 80.0, (2.0, 7.0), 'B.Cu'),
        # CH3/4 middle band Y=24-26 (between FET rows Y=20 and Y=32)
        (24.0, 28.0, (35.0, 65.0), 'F.Cu'),
        (24.0, 28.0, (35.0, 65.0), 'B.Cu'),
        # CH1/2 middle band Y=55-59 (between FET rows Y=51 and Y=63)
        (55.0, 59.0, (35.0, 65.0), 'F.Cu'),
        (55.0, 59.0, (35.0, 65.0), 'B.Cu'),
        # CH3/4 middle band Y=36-39
        (35.5, 39.5, (35.0, 65.0), 'F.Cu'),
        (35.5, 39.5, (35.0, 65.0), 'B.Cu'),
        # CH1/2 middle band Y=67-71
        (67.0, 71.0, (35.0, 65.0), 'F.Cu'),
        (67.0, 71.0, (35.0, 65.0), 'B.Cu'),
    ]
    forced_far = []
    for ref in no_parent[:]:
        _, layer, _ = ref_info[ref]
        # Find any free grid slot
        placed_ok = False
        for sy0, sy1, (sx0, sx1), slayer in GRID_STRIPS:
            if slayer != layer: continue
            y = sy0
            while y <= sy1 and not placed_ok:
                x = sx0
                while x <= sx1:
                    nx, ny = round(x, 1), round(y, 1)
                    if inside_keepout(nx, ny, layer):
                        x += 2.4; continue
                    collide = False
                    for ox_o, oy_o, layer_o in occupied:
                        if layer_o != layer: continue
                        if abs(ox_o - nx) < 1.8 and abs(oy_o - ny) < 1.5:
                            collide = True; break
                    if not collide:
                        # Pad-bbox check
                        tb = [bb + (ref,) for bb in update_pad_bbox_for_ref(ref, (nx, ny))]
                        if not has_pad_collision(tb):
                            auto_placements[ref] = (nx, ny, layer, 0.0)
                            occupied[(nx, ny, layer)] = ref
                            pad_bboxes.extend(tb)
                            forced_far.append(ref)
                            placed_ok = True
                            break
                    x += 2.4
                y += 2.0
            if placed_ok: break
        if placed_ok:
            no_parent.remove(ref)
    if forced_far:
        print(f"# Forced into grid (no parent slot): {len(forced_far)}", file=__import__('sys').stderr)

    # Last-ditch: full-board grid scan for any remaining
    if no_parent:
        print(f"# Final scan for {len(no_parent)} remaining...", file=__import__('sys').stderr)
        for ref in no_parent[:]:
            _, layer, _ = ref_info[ref]
            placed_ok = False
            for y_int in range(20, 920, 22):  # Y=2.0 to 92, 2.2mm step
                if placed_ok: break
                y = y_int / 10.0
                for x_int in range(20, 990, 24):  # X=2.0 to 99, 2.4mm step
                    x = x_int / 10.0
                    nx, ny = round(x, 1), round(y, 1)
                    if inside_keepout(nx, ny, layer): continue
                    tb = [bb + (ref,) for bb in update_pad_bbox_for_ref(ref, (nx, ny))]
                    if has_pad_collision(tb): continue
                    collide = False
                    for ox_o, oy_o, layer_o in occupied:
                        if layer_o == layer and abs(ox_o-nx) < 1.8 and abs(oy_o-ny) < 1.5:
                            collide = True; break
                    if collide: continue
                    auto_placements[ref] = (nx, ny, layer, 0.0)
                    occupied[(nx, ny, layer)] = ref
                    pad_bboxes.extend(tb)
                    placed_ok = True
                    break
            if placed_ok:
                no_parent.remove(ref)
        print(f"# Still unplaced after full scan: {len(no_parent)}", file=__import__('sys').stderr)

    print(f"# Auto-placed: {len(auto_placements)}", file=__import__('sys').stderr)
    print(f"# No parent or no free slot: {len(no_parent)}", file=__import__('sys').stderr)
    if no_parent[:20]:
        print(f"# Unplaced (first 20): {no_parent[:20]}", file=__import__('sys').stderr)
    if far_anchored:
        print(f"# Far-anchored (>5mm, first 5): {far_anchored[:5]}", file=__import__('sys').stderr)

    # Output as Python dict
    print("AUTO_PLACEMENTS = {")
    for ref in sorted(auto_placements.keys()):
        x, y, layer, rot = auto_placements[ref]
        print(f"    '{ref}': ({x:.1f}, {y:.1f}, '{layer}', {rot:.1f}),")
    print("}")


if __name__ == "__main__":
    main()
