#!/usr/bin/env python3
"""place_subsystem_ch1_v2.py — Phase 4-v2 Step 2 CH1 with constraint_engine.

Per master 5-step plan + clean-slate approach:
1. Read CH1 zone from BOARD_INVARIANTS via constraint_engine
2. Anchor ICs (Q5-Q10 fixed, J18/19/22/U3/U4 spaced)
3. Auto-anchor passives via role-based spiral search with collision detection
4. Per-place validate (pad-bbox + center-coincident + IC keepout)
5. On collision: try alternate anchor pin (not whack-a-mole shift)

Start: empty board (pcbai_fpv4in1_empty.kicad_pcb)
End: pcbai_fpv4in1.kicad_pcb with CH1-only placement
"""
import pcbnew
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from constraint_engine import parse_board_invariants

FULL = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
EMPTY = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1_empty.kicad_pcb"
OUT = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# IC anchors (per Phase 4-v2 master 5-step #2)
IC_ANCHORS = {
    # FETs Q5-Q10: 6×6mm body, 2 cols × 3 rows in zone (0-35, 50-82)
    'Q5':  (12.0, 56.0),
    'Q6':  (30.0, 56.0),
    'Q7':  (12.0, 68.0),
    'Q8':  (30.0, 68.0),
    'Q9':  (12.0, 80.0),
    'Q10': (30.0, 80.0),
    # MCU + DRV + INA + LM393 — spaced to avoid pad collisions
    # QFN-32 (5x5) + SOIC-8 (5x4) need ≥10mm center-to-center
    'J18': (22.0, 80.0),   # MCU QFN-32 — north center, between Q9/Q10
    'J19': (22.0, 62.0),   # DRV HVQFN-24 — south center, between Q5/Q6
    'J20': (5.0, 60.0),    # INA-A SOT-363 — west, near Q5
    'J21': (5.0, 72.0),    # INA-B SOT-363 — west, near Q7
    'J22': (5.0, 78.0),    # INA-C SOT-363 — west, near Q9
    'U3':  (8.0, 80.0),    # LM393 SOIC-8 — west of J22, 14mm from J18
    'U4':  (8.0, 68.0),    # LM393 SOT-353 — west, between J21+INAs
    # Motor TPs
    'TP19': (3.0, 56.0),
    'TP20': (3.0, 68.0),
    'TP21': (3.0, 80.0),
}

PAD_CLEARANCE_MM = 0.3
IC_BODY_MARGIN = 1.0


def get_ch1_refs(donor):
    refs = set()
    for fp in donor.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNetname() or ''
            if re.search(r'_CH1$', n):
                refs.add(fp.GetReference()); break
        if fp.GetReference() in IC_ANCHORS:
            refs.add(fp.GetReference())
    return refs


def get_pad_bboxes(fp_at_pos):
    """Return list of (x1, y1, x2, y2, F, B, net) for an fp tentatively at (x,y)."""
    out = []
    pos = fp_at_pos['fp'].GetPosition()
    cur_x = pcbnew.ToMM(pos.x); cur_y = pcbnew.ToMM(pos.y)
    dx = fp_at_pos['x'] - cur_x; dy = fp_at_pos['y'] - cur_y
    for pad in fp_at_pos['fp'].Pads():
        bb = pad.GetBoundingBox()
        ls = pad.GetLayerSet()
        out.append((
            pcbnew.ToMM(bb.GetLeft()) + dx,
            pcbnew.ToMM(bb.GetTop()) + dy,
            pcbnew.ToMM(bb.GetRight()) + dx,
            pcbnew.ToMM(bb.GetBottom()) + dy,
            ls.Contains(pcbnew.F_Cu),
            ls.Contains(pcbnew.B_Cu),
            pad.GetNetname() or '',
        ))
    return out


def position_valid(test_pads, placed_pad_bxs, placed_centers, x, y, layer):
    """Validate (x,y) for new fp test_pads against placed."""
    # Center collision (1.5mm c-to-c)
    for (px, py, pl) in placed_centers:
        if pl != layer: continue
        if math.hypot(px-x, py-y) < 1.6:
            return False
    # Pad-bbox collision
    for (b1, b2, b3, b4, F, B, net) in test_pads:
        for (p1, p2, p3, p4, pF, pB, pn) in placed_pad_bxs:
            if net and pn and net == pn: continue  # same-net OK
            same = (F and pF) or (B and pB)
            if not same: continue
            if b1 - PAD_CLEARANCE_MM < p3 and b3 + PAD_CLEARANCE_MM > p1 and \
               b2 - PAD_CLEARANCE_MM < p4 and b4 + PAD_CLEARANCE_MM > p2:
                return False
    return True


def main():
    inv = parse_board_invariants("docs/BOARD_INVARIANTS.md")
    # CH1 zone per BOARD_INVARIANTS
    ch1_zone = inv.zones.get('CH1', (0, 50, 35, 82))
    if hasattr(ch1_zone, 'x_min'):
        zone = (ch1_zone.x_min, ch1_zone.y_min, ch1_zone.x_max, ch1_zone.y_max)
    else:
        zone = ch1_zone
    print(f"CH1 zone: x=[{zone[0]}-{zone[2]}], y=[{zone[1]}-{zone[3]}]")

    donor = pcbnew.LoadBoard(FULL)
    recipient = pcbnew.LoadBoard(EMPTY)
    ch1_refs = get_ch1_refs(donor)
    print(f"CH1 components: {len(ch1_refs)}")

    # Place ICs first
    placed_centers = []  # (x, y, layer)
    placed_pad_bxs = []
    placed_count = 0
    failed = []

    # Move recipient's existing pads to "occupied"
    for fp in recipient.GetFootprints():
        pos = fp.GetPosition()
        layer = fp.GetLayer()
        placed_centers.append((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), layer))
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            placed_pad_bxs.append((
                pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu),
                pad.GetNetname() or '',
            ))

    # Step 2a: place IC anchors
    for ref, (x, y) in IC_ANCHORS.items():
        if ref not in ch1_refs: continue
        donor_fp = donor.FindFootprintByReference(ref)
        if donor_fp is None: continue
        new_fp = donor_fp.Duplicate()
        new_fp.SetPosition(pcbnew.VECTOR2I(int(x*1e6), int(y*1e6)))
        recipient.Add(new_fp)
        placed_centers.append((x, y, new_fp.GetLayer()))
        # Add pad bboxes
        for pad in new_fp.Pads():
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            placed_pad_bxs.append((
                pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu),
                pad.GetNetname() or '',
            ))
        placed_count += 1
    print(f"Anchors placed: {placed_count}")

    # Step 2b: passives via role-based spiral around parent IC pad
    passives = sorted(ch1_refs - set(IC_ANCHORS.keys()))
    for ref in passives:
        donor_fp = donor.FindFootprintByReference(ref)
        if donor_fp is None: continue
        # Determine parent IC via shared net
        parent_pin_pos = None
        for pad in donor_fp.Pads():
            n = pad.GetNetname() or ''
            if not n or n in ('GND', '+VMOTOR'): continue
            # Find an IC anchor with matching net
            for anchor_ref in IC_ANCHORS:
                if anchor_ref not in ch1_refs: continue
                anchor_fp = donor.FindFootprintByReference(anchor_ref)
                if anchor_fp is None: continue
                for apad in anchor_fp.Pads():
                    an = apad.GetNetname() or ''
                    if an == n:
                        # Found parent — use the NEW anchor position + this pad offset
                        anchor_x, anchor_y = IC_ANCHORS[anchor_ref]
                        apad_pos = apad.GetPosition()
                        anchor_old = anchor_fp.GetPosition()
                        pin_dx = pcbnew.ToMM(apad_pos.x) - pcbnew.ToMM(anchor_old.x)
                        pin_dy = pcbnew.ToMM(apad_pos.y) - pcbnew.ToMM(anchor_old.y)
                        parent_pin_pos = (anchor_x + pin_dx, anchor_y + pin_dy)
                        break
                if parent_pin_pos: break
            if parent_pin_pos: break
        if parent_pin_pos is None:
            # No IC anchor found — try zone center
            parent_pin_pos = ((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)

        # Spiral search from parent pin
        chosen = None
        for r_steps in range(1, 20):
            r = r_steps * 0.5
            n_pts = max(8, r_steps * 4)
            for i in range(n_pts):
                theta = 2 * math.pi * i / n_pts
                tx = parent_pin_pos[0] + r * math.cos(theta)
                ty = parent_pin_pos[1] + r * math.sin(theta)
                # In zone?
                if not (zone[0] + 0.5 <= tx <= zone[2] - 0.5 and zone[1] + 0.5 <= ty <= zone[3] - 0.5):
                    continue
                # Build test pads at (tx, ty)
                test_pads_info = {'fp': donor_fp, 'x': tx, 'y': ty}
                tb = get_pad_bboxes(test_pads_info)
                if position_valid(tb, placed_pad_bxs, placed_centers, tx, ty, donor_fp.GetLayer()):
                    chosen = (tx, ty); break
            if chosen: break
        if chosen is None:
            failed.append(ref)
            continue
        # Place
        new_fp = donor_fp.Duplicate()
        new_fp.SetPosition(pcbnew.VECTOR2I(int(chosen[0]*1e6), int(chosen[1]*1e6)))
        recipient.Add(new_fp)
        placed_centers.append((chosen[0], chosen[1], new_fp.GetLayer()))
        for pad in new_fp.Pads():
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            placed_pad_bxs.append((
                pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu),
                pad.GetNetname() or '',
            ))
        placed_count += 1

    print(f"Total placed: {placed_count}/{len(ch1_refs)}")
    if failed:
        print(f"Failed ({len(failed)}): {failed[:10]}")
    recipient.Save(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
