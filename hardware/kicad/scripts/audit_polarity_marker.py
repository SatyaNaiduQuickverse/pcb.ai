#!/usr/bin/env python3
"""
audit_polarity_marker.py — G_PP1 polarity marker visibility gate.

Proactive 2026-05-26 (catch class: silent polarity reversal at assembly).
LEDs (D*), Schottky/zener diodes, electrolytic caps (CP*), Hall sensors,
and TVS arrays MUST have a visible polarity / pin-1 marker on the silk
layer matching the footprint side. Assembly without polarity marker leads
to ~5% reverse-install rate (industry) — costs bring-up time.

Heuristic check: for refdes prefixes (D, CP, U) where pin polarity matters,
verify there is at least one polarity-distinguishing graphic on F.SilkS /
B.SilkS within the footprint courtyard:
  - Triangle (cathode indicator) for diodes/LEDs
  - "+" or chamfer (anode/positive) for electrolytics
  - Dot/chamfer (pin-1) for ICs

Pragmatic implementation: count silk graphic primitives on the same side
as the component. If 0 silk shapes → FAIL (no polarity hint). Doesn't
verify the graphic shape semantically; that requires KiCad-API depth we
defer to manual G_V1 inspection.

Exit 0 = all PASS, 1 = any polarity-critical component with no silk.

Usage:
  python3 audit_polarity_marker.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# Refdes prefixes where polarity / pin-1 matters at assembly
POLARITY_PREFIXES = ("D", "CP", "U")


def is_polarity_ref(ref):
    """Diodes (D[digit]), electrolytics (CP*), ICs (U[digit])."""
    if ref.startswith("CP"):
        return True
    if ref.startswith("D") and ref[1:].isdigit():
        return True
    if ref.startswith("U") and ref[1:].isdigit():
        return True
    return False


def silk_layer_for(fp):
    return pcbnew.F_SilkS if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_SilkS


def count_silk_shapes_in_footprint(fp):
    """Count silk-layer drawing primitives (lines/arcs/polys) that belong to fp.
    Polarity markers in KiCad libs are FP_SHAPE instances on F.SilkS layer."""
    target_layer = silk_layer_for(fp)
    n = 0
    for it in fp.GraphicalItems():
        try:
            lyr = it.GetLayer()
        except AttributeError:
            continue
        if lyr == target_layer:
            n += 1
    return n


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    print(f"=== Polarity marker audit: {Path(board_path).name} ===")
    print(f"Polarity-critical prefixes: D[digit], CP*, U[digit]")
    print(f"Rule: ≥1 silk graphic primitive on component side (FP_SHAPE on F/B SilkS)\n")

    fails = []
    parked = 0
    checked = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not is_polarity_ref(ref):
            continue
        if pcbnew.ToMM(fp.GetPosition().x) >= 130:
            parked += 1
            continue
        checked += 1
        n = count_silk_shapes_in_footprint(fp)
        if n == 0:
            fails.append(f"  [FAIL] {ref}: no silk graphic on component side (no polarity/pin-1 marker)")

    print(f"Checked {checked} polarity-critical refs; skipped {parked} parked\n")
    if fails:
        for f in fails[:20]:
            print(f)
        if len(fails) > 20:
            print(f"  ... +{len(fails)-20} more")
        print(f"\nRESULT: FAIL — {len(fails)} polarity-critical components lack silk marker")
        sys.exit(1)
    print("RESULT: PASS — all polarity-critical components have silk marker")


if __name__ == "__main__":
    main()
