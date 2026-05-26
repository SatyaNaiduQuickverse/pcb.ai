#!/usr/bin/env python3
"""audit_routing_channels.py — G_PP19 routing-channel reserve audit.

Per Sai 2026-05-26: "gotta route it so need to leave space".

Verifies that parametric routing channels (defined in BoardParameters) are
NOT occupied by component bodies. Specifically:
  - Inter-sub-zone routing channel within each CHn east strip (x=routing_channel_x_start
    to routing_channel_x_end) must have ZERO component bbox overlap
  - The 1.5mm gap between MOTOR + LOGIC sub-zones must be honored

If a component's bbox intersects a reserved channel → FAIL with the channel id
and offending refs.
"""
import os, sys

def main():
    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not available", file=sys.stderr); return 1

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from parametric_placement import BoardParameters

    pcb_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
    board = pcbnew.LoadBoard(pcb_path)
    mm = 1000000.0
    p = BoardParameters()

    # Define reserved channels (xmin, ymin, xmax, ymax, name)
    # Per-channel routing channel (between FET column and east MCU strip)
    # CH1 (SW): x = routing_channel_x_start..end, y = 50..89 (CH1 zone)
    south_y_min, south_y_max = 50, p.height_mm - p.s1_height_mm
    north_y_min, north_y_max = p.s6_height_mm, 50

    # Inter-FET-column-and-east-strip channel
    chans = [
        (p.routing_channel_x_start, south_y_min, p.routing_channel_x_end, south_y_max,
         "CH1 FET/east routing channel"),
        (2 * p.mirror_x_axis - p.routing_channel_x_end, south_y_min,
         2 * p.mirror_x_axis - p.routing_channel_x_start, south_y_max,
         "CH2 FET/east routing channel (mirror_X)"),
        (p.routing_channel_x_start, north_y_min, p.routing_channel_x_end, north_y_max,
         "CH4 FET/east routing channel"),
        (2 * p.mirror_x_axis - p.routing_channel_x_end, north_y_min,
         2 * p.mirror_x_axis - p.routing_channel_x_start, north_y_max,
         "CH3 FET/east routing channel (mirror_X)"),
        # Inter-sub-zone (MOTOR/LOGIC) routing channel within east strip
        (p.east_strip_motor_x_end, south_y_min, p.east_strip_logic_x_start, south_y_max,
         "CH1 MOTOR/LOGIC sub-zone routing channel"),
        (2 * p.mirror_x_axis - p.east_strip_logic_x_start, south_y_min,
         2 * p.mirror_x_axis - p.east_strip_motor_x_end, south_y_max,
         "CH2 MOTOR/LOGIC sub-zone (mirror_X)"),
        (p.east_strip_motor_x_end, north_y_min, p.east_strip_logic_x_start, north_y_max,
         "CH4 MOTOR/LOGIC sub-zone"),
        (2 * p.mirror_x_axis - p.east_strip_logic_x_start, north_y_min,
         2 * p.mirror_x_axis - p.east_strip_motor_x_end, north_y_max,
         "CH3 MOTOR/LOGIC sub-zone (mirror_X)"),
    ]

    fails = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        if pos.x/mm < -5 or pos.x/mm > 200 or pos.y/mm < -5 or pos.y/mm > 200:
            continue  # parked
        bbox = fp.GetBoundingBox(False, False)
        bx0 = bbox.GetX()/mm; by0 = bbox.GetY()/mm
        bx1 = bx0 + bbox.GetWidth()/mm; by1 = by0 + bbox.GetHeight()/mm
        for cx0, cy0, cx1, cy1, cname in chans:
            if bx0 < cx1 and bx1 > cx0 and by0 < cy1 and by1 > cy0:
                fails.append((ref, cname, (bx0,by0,bx1,by1)))

    print("=" * 70)
    print(f"audit_routing_channels.py G_PP19 — {len(chans)} reserved channels")
    print("=" * 70)
    if fails:
        print()
        print(f"  ❌ FAIL — {len(fails)} component(s) inside reserved routing channels:")
        for ref, cname, bb in fails[:20]:
            print(f"    {ref} bbox {bb} intersects {cname}")
        return 1
    print()
    print(f"  ✅ PASS — all reserved routing channels clear")
    return 0

if __name__ == "__main__":
    sys.exit(main())
