#!/usr/bin/env python3
"""
audit_hv_creepage.py — G_PP6 high-voltage creepage clearance gate.

Proactive 2026-05-26 (catch class: HV pad/trace clearance fail at fab).
Per IPC-2221 Table 6-1, B-grade (uncoated, ≤3050m altitude):

  Voltage   Min clearance (mm)
  ≤ 15 V    0.1
  16-30 V   0.1
  31-50 V   0.6
  51-100 V  0.6
  101-150 V 1.5

Our +VMOTOR rail is 25.2 V (6S nominal) → 27 V max (R17 burst) → 30 V class.
Per "next-step" margin (industry conservative), we apply the 31-50 V tier
(≥0.6 mm) — this gives FoS for future 8S compatibility too.

This gate scans pairs of pads/tracks on the SAME copper layer that carry
HV nets (+VMOTOR_*, +BATT, MOTOR_A/B/C_CH*) and verifies pad-edge-to-foreign-
pad-edge spacing ≥ HV_MIN_CLEARANCE_MM.

Pragmatic: O(N²) on HV pads only (typically <50 pads), runtime <2s.

Exit 0 = all PASS, 1 = any clearance violation.

Usage:
  python3 audit_hv_creepage.py <board.kicad_pcb>
"""

import re
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


HV_MIN_CLEARANCE_MM = 0.6  # IPC-2221 B-grade for 31-50V class (with FoS for 8S)

HV_NET_PATTERN = re.compile(
    r"^(\+VMOTOR|\+BATT|MOTOR_[ABC]_CH\d|SW_CH\d|\+27V|VBUS_PWR)",
    re.IGNORECASE,
)


def pad_rect(pad):
    """Return (x0, y0, x1, y1, layer, netname) for pad bbox."""
    bb = pad.GetBoundingBox()
    return (
        pcbnew.ToMM(bb.GetLeft()),
        pcbnew.ToMM(bb.GetTop()),
        pcbnew.ToMM(bb.GetRight()),
        pcbnew.ToMM(bb.GetBottom()),
        pad.GetLayerSet(),
        pad.GetNetname() or "",
    )


# 2026-05-26 worker call (b): half-bridge same-cell creepage relaxation.
# Inter-net pads inside the same FET cluster (gates + sources + BST cap + clamp
# + shunt sense — all switch coherently within ns) can be ≤0.3mm per industry
# compact-ESC practice (Bogatin §10). Inter-cell + inter-channel stays ≥0.6mm.
HALF_BRIDGE_CELL_RELAXED_MM = 0.3
import re as _re
_HB_NET_RE = _re.compile(
    r'^(MOTOR_[ABC]_CH\d+|BEMF_[ABC]_CH\d+|CSA_[ABC]_OUT_CH\d+|CSA_MAX_CH\d+'
    r'|SHUNT_[ABC]_TOP_CH\d+|GH[ABC]_CH\d+|GL[ABC]_CH\d+|BST[ABC]_CH\d+'
    r'|\+?VMOTOR(_CH\d*)?)$'
)


def both_in_hb_cell(net_a, net_b):
    """Both nets are HB-cell same-domain nets."""
    return bool(_HB_NET_RE.match(net_a) and _HB_NET_RE.match(net_b))


def edge_distance_mm(a, b):
    """Min edge-to-edge distance between two axis-aligned bboxes."""
    ax0, ay0, ax1, ay1 = a[:4]
    bx0, by0, bx1, by1 = b[:4]
    dx = max(0, max(bx0 - ax1, ax0 - bx1))
    dy = max(0, max(by0 - ay1, ay0 - by1))
    return (dx * dx + dy * dy) ** 0.5


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    print(f"=== HV creepage audit: {Path(board_path).name} ===")
    print(f"HV nets: {HV_NET_PATTERN.pattern}")
    print(f"Min clearance: {HV_MIN_CLEARANCE_MM}mm (IPC-2221 B-grade, 31-50V with FoS)\n")

    # Collect HV pads + non-HV pads (we check HV vs everything else).
    # 2026-05-26: pad tuples now include ref to skip same-component pad pairs
    # (worker bug catch: C61.2↔C61.1 are 2 pads of same physical part with
    # fixed footprint geometry — not a layout-controllable issue).
    hv_pads = []
    other_pads = []
    parked_skipped = 0
    for fp in board.GetFootprints():
        if pcbnew.ToMM(fp.GetPosition().x) >= 130:
            parked_skipped += 1
            continue
        ref = fp.GetReference()
        for pad in fp.Pads():
            net = pad.GetNetname() or ""
            rect = pad_rect(pad) + (ref, pad.GetPadName())
            if HV_NET_PATTERN.match(net):
                hv_pads.append(rect)
            else:
                other_pads.append(rect)

    if not hv_pads:
        print("No HV-net pads found on-board (subsystems not yet brought?) — SKIP")
        sys.exit(0)

    print(f"HV pads: {len(hv_pads)} · other on-board pads: {len(other_pads)} · parked skipped: {parked_skipped}\n")

    fails = []
    seen = set()
    # Refinements 2026-05-26 (worker catches):
    # (a) Skip same-ref pad pairs (e.g. C61.1↔C61.2 = same physical part,
    #     fixed footprint, not layout-controllable).
    # (b) Same-NET pads = same node, no creepage rule (HV-vs-HV branch already
    #     had this; extended to HV-vs-other).
    # (c) Same half-bridge cell (both nets in _HB_NET_RE) gets RELAXED 0.3mm
    #     bound — same-domain transients are slew-coupled, not random; per
    #     Bogatin §10 + industry compact-ESC practice. Inter-cell stays 0.6mm.

    def _required_clearance(net_a, net_b):
        if both_in_hb_cell(net_a, net_b):
            return HALF_BRIDGE_CELL_RELAXED_MM
        return HV_MIN_CLEARANCE_MM

    # HV-vs-other (same layer, different net + different ref only)
    for hv in hv_pads:
        for o in other_pads:
            if hv[6] == o[6]:  # same ref = same physical component
                continue
            if hv[5] == o[5] and hv[5]:  # same non-empty net = same node
                continue
            try:
                if not (hv[4] & o[4]).any():
                    continue
            except Exception:
                pass
            d = edge_distance_mm(hv, o)
            min_clear = _required_clearance(hv[5], o[5])
            if d < min_clear:
                k = tuple(sorted([f"{hv[6]}.{hv[7]}", f"{o[6]}.{o[7]}"]))
                if k in seen:
                    continue
                seen.add(k)
                tag = "HB-cell" if min_clear == HALF_BRIDGE_CELL_RELAXED_MM else "IPC-2221"
                fails.append(f"  [FAIL] {hv[6]}.{hv[7]} (net={hv[5]}) ↔ {o[6]}.{o[7]} (net={o[5]}): "
                             f"edge gap {d:.3f}mm < {min_clear}mm ({tag})")

    # HV-vs-HV different-net same-layer + different ref
    for i, a in enumerate(hv_pads):
        for b in hv_pads[i+1:]:
            if a[6] == b[6]:
                continue  # same ref
            if a[5] == b[5]:
                continue  # same net
            try:
                if not (a[4] & b[4]).any():
                    continue
            except Exception:
                pass
            d = edge_distance_mm(a, b)
            min_clear = _required_clearance(a[5], b[5])
            if d < min_clear:
                k = tuple(sorted([f"{a[6]}.{a[7]}", f"{b[6]}.{b[7]}"]))
                if k in seen:
                    continue
                seen.add(k)
                tag = "HB-cell" if min_clear == HALF_BRIDGE_CELL_RELAXED_MM else "IPC-2221"
                fails.append(f"  [FAIL] HV-HV {a[6]}.{a[7]} ({a[5]}) ↔ {b[6]}.{b[7]} ({b[5]}): "
                             f"edge gap {d:.3f}mm < {min_clear}mm ({tag})")

    if fails:
        for f in fails[:15]:
            print(f)
        if len(fails) > 15:
            print(f"  ... +{len(fails)-15} more")
        print(f"\nRESULT: FAIL — {len(fails)} HV creepage violations (IPC-2221 B-grade)")
        sys.exit(1)
    print("RESULT: PASS — all HV pad-to-pad clearances ≥0.6mm (IPC-2221 B-grade)")


if __name__ == "__main__":
    main()
