#!/usr/bin/env python3
"""route_power_plane_stitch.py — PR-routing-final G2 Phase A (O1 offset-via).

Per master 2026-05-24 O1 dispatch: offset-via-with-stub-trace pattern survives
ZONE_FILLER absorption. On-pad vias get absorbed by zone-fill (KiCad treats
them as redundant since zone copper already covers the pad). Off-pad via with
explicit pad→via stub trace is the standard pattern that persists.

Engineering rationale:
  - On-pad via: ZONE_FILLER sees same-net copper already at pad, removes via
  - Offset via (≥0.5mm from pad edge): via stays + stub trace = pad → via → plane

Algorithm per unconnected power-net pad:
  1. Compute candidate via positions: 8 cardinal directions, distance 0.8mm
     from pad center (clears 0.5mm pad-edge + 0.3mm safety)
  2. For each candidate, check no collision with other pads / tracks / vias
  3. Place via at first clear position; add stub trace pad-center → via
  4. After all vias added: save → reload → ZONE_FILLER.Fill(zones) → save

Per [[reference-pcbnew-zone-filler-save-pattern]] amended: this is the
correct pattern. On-pad approach was lossy.
"""
import pcbnew
import math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

PLANE_NETS = {'GND', 'BATGND', '+VMOTOR'}

VIA_DIA = 0.6
VIA_DRILL = 0.3
STUB_W = 0.3
OFFSET_DIST_MM = 0.9  # via offset from pad center (clear of typical 0.5mm pad edge)
MIN_PAD_CLEARANCE = 0.2  # via must be ≥0.2mm from any other pad


def collect_obstacles(board):
    """Return dict layer ('F'/'B') → list of bboxes for all pads + via positions."""
    pads = {'F': [], 'B': []}
    via_positions = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            box = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                   pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
            net = pad.GetNetname() or ''
            entry = {'box': box, 'net': net,
                     'ref': fp.GetReference(),
                     'pad': pad.GetPadName()}
            if ls.Contains(pcbnew.F_Cu): pads['F'].append(entry)
            if ls.Contains(pcbnew.B_Cu): pads['B'].append(entry)
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            via_positions.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                                   t.GetNetname() or ''))
    return pads, via_positions


def find_clear_via_position(pad_x, pad_y, layer, net_name, pads_idx, via_positions,
                            offset=OFFSET_DIST_MM):
    """Try 8 cardinal+diagonal positions at `offset` from pad center.
    Return (x, y) of first position that doesn't collide with other-net pads
    or duplicate same-net via at that location."""
    via_radius = VIA_DIA / 2
    for angle_deg in range(0, 360, 45):
        a = math.radians(angle_deg)
        vx = pad_x + offset * math.cos(a)
        vy = pad_y + offset * math.sin(a)
        # Check vs pads on this layer (different net = collision)
        bad = False
        for p in pads_idx[layer]:
            if p['net'] == net_name: continue
            bx0, by0, bx1, by1 = p['box']
            bx0 -= via_radius + MIN_PAD_CLEARANCE
            by0 -= via_radius + MIN_PAD_CLEARANCE
            bx1 += via_radius + MIN_PAD_CLEARANCE
            by1 += via_radius + MIN_PAD_CLEARANCE
            if bx0 <= vx <= bx1 and by0 <= vy <= by1:
                bad = True; break
        if bad: continue
        # Check vs existing vias on same net (avoid duplicates)
        dup = False
        for vx_e, vy_e, vn in via_positions:
            if vn != net_name: continue
            if math.hypot(vx - vx_e, vy - vy_e) < 0.5:
                dup = True; break
        if dup: continue
        # On-board?
        if vx < 1 or vx > 99 or vy < 1 or vy > 99: continue
        return (vx, vy)
    return None


def add_via(board, x_mm, y_mm, net_obj):
    v = pcbnew.PCB_VIA(board)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    v.SetDrill(pcbnew.FromMM(VIA_DRILL))
    v.SetWidth(pcbnew.FromMM(VIA_DIA))
    v.SetNet(net_obj)
    board.Add(v)


def add_stub_track(board, x1, y1, x2, y2, layer, net_obj):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    t.SetLayer(layer)
    t.SetWidth(pcbnew.FromMM(STUB_W))
    t.SetNet(net_obj)
    board.Add(t)


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name:
            return n
    return None


def pad_has_route(board, pad_x, pad_y, net_name, tol=0.3):
    """True if any existing track endpoint or via is within tol of pad center on same net."""
    for t in board.GetTracks():
        if t.GetNetname() != net_name: continue
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            if math.hypot(pcbnew.ToMM(p.x) - pad_x,
                           pcbnew.ToMM(p.y) - pad_y) < tol:
                return True
        else:
            for p in (t.GetStart(), t.GetEnd()):
                if math.hypot(pcbnew.ToMM(p.x) - pad_x,
                               pcbnew.ToMM(p.y) - pad_y) < tol:
                    return True
    return False


def has_stub_track_to_via(board, pad_x, pad_y, net_name):
    """True if pad has an explicit TRACK (not just a via) emanating from it on
    same net — meaning it's properly routed."""
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA): continue
        if t.GetNetname() != net_name: continue
        for p in (t.GetStart(), t.GetEnd()):
            if math.hypot(pcbnew.ToMM(p.x) - pad_x,
                           pcbnew.ToMM(p.y) - pad_y) < 0.2:
                return True
    return False


def remove_on_pad_vias(board, pad_positions_by_net):
    """Delete vias whose position is at a pad center on same net — these don't
    route the pad and just get absorbed by ZONE_FILLER. Phase A added these."""
    removed = 0
    to_remove = []
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_VIA): continue
        net = t.GetNetname()
        if net not in PLANE_NETS: continue
        p = t.GetPosition()
        vx = pcbnew.ToMM(p.x); vy = pcbnew.ToMM(p.y)
        # Check if this via is at any pad center on same net
        for (px, py) in pad_positions_by_net.get(net, []):
            if math.hypot(vx - px, vy - py) < 0.3:
                to_remove.append(t)
                removed += 1
                break
    for t in to_remove:
        board.Remove(t)
    return removed


def main():
    board = pcbnew.LoadBoard(PCB)
    pads_idx, via_positions = collect_obstacles(board)
    pre_vias = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))

    added = {'GND': 0, 'BATGND': 0, '+VMOTOR': 0}
    skipped_already_routed = 0
    skipped_no_slot = 0

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net_obj = pad.GetNet()
            if net_obj is None: continue
            net_name = net_obj.GetNetname()
            if net_name not in PLANE_NETS: continue
            if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH,
                                       pcbnew.PAD_ATTRIB_NPTH):
                continue
            p = pad.GetPosition()
            px = pcbnew.ToMM(p.x)
            py = pcbnew.ToMM(p.y)
            # Skip if pad already has a STUB TRACK route (not just via)
            if has_stub_track_to_via(board, px, py, net_name):
                skipped_already_routed += 1
                continue
            # Determine layer for stub trace based on pad
            ls = pad.GetLayerSet()
            layer = pcbnew.F_Cu if ls.Contains(pcbnew.F_Cu) else pcbnew.B_Cu
            layer_str = 'F' if layer == pcbnew.F_Cu else 'B'
            via_pos = find_clear_via_position(px, py, layer_str, net_name,
                                               pads_idx, via_positions)
            if via_pos is None:
                skipped_no_slot += 1
                continue
            vx, vy = via_pos
            add_via(board, vx, vy, net_obj)
            add_stub_track(board, px, py, vx, vy, layer, net_obj)
            via_positions.append((vx, vy, net_name))
            added[net_name] += 1

    print(f"Vias added (offset+stub): GND={added['GND']}, BATGND={added['BATGND']}, "
          f"+VMOTOR={added['+VMOTOR']}")
    print(f"Skipped (already routed): {skipped_already_routed}")
    print(f"Skipped (no clear slot): {skipped_no_slot}")

    print("Save vias+stubs...")
    board.Save(PCB)
    print("Reload + ZONE_FILLER (offset vias should persist)...")
    board = pcbnew.LoadBoard(PCB)
    zones = [z for z in board.Zones()]
    pcbnew.ZONE_FILLER(board).Fill(zones)
    board.Save(PCB)
    post_vias = sum(1 for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA))
    print(f"\nVias before: {pre_vias}, after: {post_vias}")
    print(f"Net via delta: {post_vias - pre_vias}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
