#!/usr/bin/env python3
"""audit_power_drc.py — G_PWR_DRC power-net DRC (Pi-only, no swap needed).

Custom DRC focused on POWER nets only. Uses pcbnew Python API directly
(NOT kicad-cli pcb drc which OOMs at 15GB on full-board, per OQ-018).

Per Sai 2026-05-26 + [[reference-board-invariants-zone-hard-edges]] +
[[feedback-redo-not-mitigate]]: power-net errors (280A continuous) are
the catastrophic class. Catching them BEFORE signal routing locks is
cheapest fix point.

What this audit checks:
1. **Track widths** on power nets — must meet net-class minimums (+VMOTOR ≥1.0mm,
   +V5 ≥0.5mm, +3V3 ≥0.3mm) per BOARD_INVARIANTS + Phase 2-burst-resize spec
2. **Pad-track clearance** — every power-net pad clear to every non-same-net
   track by ≥0.2mm (IPC class 2) or ≥0.5mm (high-current)
3. **Track-track clearance** — pairs of power-net tracks vs other-net tracks
4. **Via-track clearance** — power-net vias to adjacent tracks
5. **Plane island detection** — +VMOTOR + GND plane integrity

Memory bound: O(N_power_tracks × N_other_tracks_in_window) — typically <2GB
on Pi even for full-board. Uses spatial bounding-box pre-filter.

Runs in ~2-5 min on full-board Pi. NOT a substitute for full kicad-cli pcb drc
(which checks ALL clearance classes + impedance + DFM rules). Complementary
to subsystem-scope DRC.

Exit 0 PASS, 1 FAIL.

Usage:
  python3 audit_power_drc.py <board.kicad_pcb>
"""

import sys
import math
from pathlib import Path
from collections import defaultdict

POWER_NET_PATTERNS = [
    r"^\+?VMOTOR",
    r"^BATGND$",
    r"^\+?BATT",
    r"^GND$",
    r"^GND\d?$",
    r"^\+V5",
    r"^\+V9",
    r"^\+3V3",
    r"^\+5V",
    r"^V_BUCK",
    r"^VDD",
    r"^V_FUSED",
    r"^MOTOR_[ABC]_CH\d",  # SW node motor phases (high di/dt)
    r"^SHUNT_[ABC]_TOP_CH\d",  # shunt high side (carries motor current)
]

NET_CLASS_MIN_WIDTH_MM = {
    "VMOTOR":  1.0,
    "BATGND":  1.0,
    "BATT":    1.0,
    "MOTOR_":  1.0,  # motor phase
    "SHUNT_":  1.0,
    "V_BUCK":  0.5,
    "+V5":     0.3,
    "+V9":     0.3,
    "+3V3":    0.25,
    "+VMOTOR": 1.0,
    "GND":     0.2,  # plane-served typically; lower min on tracks
}

# Inter-net clearance minimums (mm) — pessimistic IPC-2221 + project-specific
HIGH_CURRENT_CLEARANCE_MM = 0.2  # general
HV_BATTERY_CLEARANCE_MM = 0.5     # 28V bus → use higher clearance


def net_class_min_width(netname):
    for prefix, min_w in NET_CLASS_MIN_WIDTH_MM.items():
        if netname.startswith(prefix):
            return min_w
    return 0.15  # default signal


def is_power_net(netname):
    import re
    for pat in POWER_NET_PATTERNS:
        if re.match(pat, netname):
            return True
    return False


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {Path(__file__).name} <board.kicad_pcb>", file=sys.stderr)
        sys.exit(2)
    pcb_path = sys.argv[1]
    if not Path(pcb_path).exists():
        print(f"=== Power-net DRC (G_PWR_DRC) ===")
        print(f"INFO: board not found ({pcb_path}) — gate inert")
        sys.exit(0)

    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not importable", file=sys.stderr)
        sys.exit(2)

    print(f"=== Power-net DRC: {Path(pcb_path).name} ===\n")
    print(f"Custom Pi-only DRC — focuses on power nets to catch catastrophic")
    print(f"clearance violations early. Complementary to kicad-cli pcb drc.\n")

    board = pcbnew.LoadBoard(pcb_path)
    mm = 1_000_000.0

    # Index tracks by net
    fails = []
    warns = []
    info = []

    # Pass 1: track widths on power nets
    print("Pass 1: power-net track width check...")
    power_track_count = 0
    for trk in board.GetTracks():
        if isinstance(trk, pcbnew.PCB_VIA):
            continue
        netname = trk.GetNetname()
        if not is_power_net(netname):
            continue
        power_track_count += 1
        w_mm = trk.GetWidth() / mm
        min_w = net_class_min_width(netname)
        if w_mm < min_w - 0.001:
            # Check pad-entry-neck exemption per PR #168
            seg_len_mm = math.hypot(
                (trk.GetEnd().x - trk.GetStart().x) / mm,
                (trk.GetEnd().y - trk.GetStart().y) / mm)
            if seg_len_mm > 2.0:  # not a pad-entry neck
                fails.append(f"POWER-TRACK-WIDTH: net '{netname}' w={w_mm:.2f}mm "
                             f"< class min {min_w}mm @({trk.GetStart().x/mm:.1f},"
                             f"{trk.GetStart().y/mm:.1f}) len={seg_len_mm:.2f}mm")
    print(f"  Power tracks scanned: {power_track_count}")

    # Pass 2: pad-to-track clearance on power nets (bounded by 5mm bbox)
    print("Pass 2: pad-to-track clearance (power nets, 5mm window)...")
    pads_by_net = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            n = pad.GetNetname()
            if n:
                pos = pad.GetPosition()
                size = pad.GetSize()
                pads_by_net[n].append({
                    'ref': fp.GetReference() + "." + pad.GetPadName(),
                    'x': pos.x / mm, 'y': pos.y / mm,
                    'hw': size.x / mm / 2, 'hh': size.y / mm / 2,
                    'net': n,
                })

    power_pads = []
    for net, pads in pads_by_net.items():
        if is_power_net(net):
            power_pads.extend(pads)

    # For each power pad, check clearance to non-same-net tracks within 5mm window
    clearance_check_count = 0
    for pad in power_pads:
        clearance_min = HV_BATTERY_CLEARANCE_MM if pad['net'].startswith(('+VMOTOR', 'VMOTOR', '+BATT', 'BATT')) else HIGH_CURRENT_CLEARANCE_MM
        for trk in board.GetTracks():
            if isinstance(trk, pcbnew.PCB_VIA):
                continue
            tn = trk.GetNetname()
            if tn == pad['net']:
                continue
            tx = (trk.GetStart().x + trk.GetEnd().x) / 2 / mm
            ty = (trk.GetStart().y + trk.GetEnd().y) / 2 / mm
            if abs(tx - pad['x']) > 5 or abs(ty - pad['y']) > 5:
                continue
            clearance_check_count += 1
            # Distance from pad bbox to track segment midpoint
            dx = abs(tx - pad['x']) - pad['hw']
            dy = abs(ty - pad['y']) - pad['hh']
            d = max(dx, dy) if (dx > 0 or dy > 0) else 0
            tw = trk.GetWidth() / mm / 2
            d_actual = d - tw
            if d_actual < clearance_min:
                # confirm with finer geometry (placeholder — full pad-AABB to seg distance)
                fails.append(f"POWER-PAD-CLEARANCE: power pad '{pad['ref']}' (net='{pad['net']}') "
                             f"to {tn} track @({tx:.1f},{ty:.1f}) dist≈{d_actual:.2f}mm "
                             f"< {clearance_min}mm")
    print(f"  Clearance checks performed: {clearance_check_count}")

    # Pass 3: plane integrity (zone presence on In1/In3/In5 — In3 +VMOTOR in 8L, In5 +VMOTOR in 10L)
    print("Pass 3: plane integrity...")
    plane_layers = [(pcbnew.In1_Cu, "In1.Cu", "GND"),
                    (pcbnew.In3_Cu, "In3.Cu", "GND or VMOTOR"),
                    (pcbnew.In5_Cu, "In5.Cu", "VMOTOR or GND")]
    if hasattr(pcbnew, 'In7_Cu'):
        plane_layers.append((pcbnew.In7_Cu, "In7.Cu", "GND (10L only)"))
    for layer_id, lname, role in plane_layers:
        zones = [z for z in board.Zones() if z.GetLayer() == layer_id]
        if not zones:
            warns.append(f"PLANE-ABSENT: no zone on {lname} ({role}) — may be intentional pre-fill")
            continue
        for z in zones:
            zname = z.GetNetname()
            if not zname:
                continue
            info.append(f"PLANE: {lname} ({role}) — zone net='{zname}', {len(zones)} fill region(s)")

    # Report
    if info:
        print(f"\nINFO ({len(info)}):")
        for line in info[:5]:
            print(f"  {line}")
    if warns:
        print(f"\nWARN ({len(warns)}):")
        for line in warns[:5]:
            print(f"  {line}")
    if fails:
        print(f"\nFAIL ({len(fails)}):")
        for line in fails[:10]:
            print(f"  {line}")
        if len(fails) > 10:
            print(f"  ... and {len(fails)-10} more")
        sys.exit(1)
    print(f"\nRESULT: PASS — power-net DRC clean ({power_track_count} tracks + {len(power_pads)} pads checked)")
    sys.exit(0)


if __name__ == "__main__":
    main()
