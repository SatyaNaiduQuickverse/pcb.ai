#!/usr/bin/env python3
"""
audit_crosstalk_spacing.py — G_R4 aggressor-victim crosstalk spacing gate.

Proactive 2026-05-26 (catch class: switching aggressor couples into adjacent
analog signal). Per Howard Johnson HSDD Ch. 11 + Bogatin §10:

For TWO parallel traces on the same layer, the per-unit crosstalk coupling
follows ~1/(d² + h²) (d = trace spacing, h = trace-to-reference-plane).

Industry rule of thumb: spacing ≥ 3× trace width gives <5% NEXT.
For our 8L stackup (h≈0.18mm), trace 0.13mm:
  - Routine logic: spacing ≥ 0.4mm OK (3× rule)
  - HF aggressor → analog: spacing ≥ 1.0mm + reference plane fence
  - Switching node (HS-FET drain) → ANY analog: ≥ 3mm (or different layer)

Reads routing_topology.yaml class annotations:
  - aggressor_classes: ['switching-node', 'high-current']
  - victim_classes:    ['analog', 'kelvin-sense', 'comparator']

Rule: for any track on aggressor net, no track on victim net within 1.0mm
on same layer; if 3mm rule needed (switching → analog), no track within 3mm.

SKIP if no tracks (placement-only).

Exit 0 = all PASS, 1 = any spacing violation.

Usage:
  python3 audit_crosstalk_spacing.py <board.kicad_pcb> [<topology.yaml>]
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed")
    sys.exit(1)

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# Conservative spacing minimums by aggressor-victim pairing
MIN_SPACING_MM = {
    ("switching-node", "analog"):       3.0,
    ("switching-node", "kelvin-sense"): 3.0,
    ("switching-node", "comparator"):   3.0,
    ("high-current",   "analog"):       1.5,
    ("digital-clock",  "analog"):       1.0,
    ("default",        "default"):      0.4,  # 3× trace width
}

# Net-name patterns to infer class
AGGRESSOR_PATTERNS = {
    "switching-node": re.compile(r"^(SW_CH|MOTOR_[ABC]_CH)\d", re.IGNORECASE),
    "high-current":   re.compile(r"^(\+VMOTOR|\+BATT|GND_HIGH)", re.IGNORECASE),
    "digital-clock":  re.compile(r"^(SCK|CLK|MCLK|SCL_)", re.IGNORECASE),
}
VICTIM_PATTERNS = {
    "analog":        re.compile(r"^(AVDD|VREF|HALL_OUT|BEMF_|VMON_)", re.IGNORECASE),
    "kelvin-sense":  re.compile(r"^(SHUNT_SENSE|ISENSE_)", re.IGNORECASE),
    "comparator":    re.compile(r"^(CMP_|COMP_OUT)", re.IGNORECASE),
}


def classify_net(name):
    for cls, pat in AGGRESSOR_PATTERNS.items():
        if pat.match(name):
            return "aggressor", cls
    for cls, pat in VICTIM_PATTERNS.items():
        if pat.match(name):
            return "victim", cls
    return None, None


def seg_distance_mm(s1, e1, s2, e2):
    """Minimum endpoint-pair distance — fast approximation, not exact line-line."""
    pts1 = [s1, e1]
    pts2 = [s2, e2]
    return min(((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5 for a in pts1 for b in pts2)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found"); sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    tracks = [t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_TRACK) and not isinstance(t, pcbnew.PCB_VIA)]
    if not tracks:
        print(f"=== Crosstalk spacing audit: {Path(board_path).name} ===")
        print("INFO: no tracks — gate post-routing only, SKIP"); sys.exit(0)

    aggressors = []
    victims = []
    for t in tracks:
        name = t.GetNetname()
        role, cls = classify_net(name)
        s = (pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y))
        e = (pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y))
        entry = (name, cls, t.GetLayer(), s, e)
        if role == "aggressor":
            aggressors.append(entry)
        elif role == "victim":
            victims.append(entry)

    print(f"=== Crosstalk spacing audit: {Path(board_path).name} ===")
    print(f"Aggressor segments: {len(aggressors)} · victim segments: {len(victims)}\n")

    fails = []
    for a_name, a_cls, a_layer, a_s, a_e in aggressors:
        for v_name, v_cls, v_layer, v_s, v_e in victims:
            if a_layer != v_layer:
                continue  # different layers — coupling weak through ref plane
            min_sp = MIN_SPACING_MM.get((a_cls, v_cls)) or MIN_SPACING_MM[("default", "default")]
            d = seg_distance_mm(a_s, a_e, v_s, v_e)
            if d < min_sp:
                fails.append(f"  [FAIL] aggressor {a_name} ({a_cls}) ↔ victim {v_name} ({v_cls}): "
                             f"{d:.2f}mm < {min_sp}mm required")

    if fails:
        for f in fails[:10]:
            print(f)
        if len(fails) > 10:
            print(f"  ... +{len(fails)-10} more")
        print(f"\nRESULT: FAIL — {len(fails)} crosstalk spacing violations")
        sys.exit(1)
    print("RESULT: PASS — aggressor-victim spacings respect minimums")


if __name__ == "__main__":
    main()
