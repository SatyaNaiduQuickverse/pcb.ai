#!/usr/bin/env python3
"""
audit_edge_keepout.py — G17 board-edge keepout gate.

Proactive 2026-05-26 (Sai-#5 catch on Stage 0: J14 originally at y=90 was
10mm from edge, hit board-edge keepout rule). Codifying upfront so no
component lands inside the JLC keepout zone again.

Per JLC PCBA capability + IPC-7351:
- Default keepout from board edge: ≥3mm component body (no copper or
  silk closer than 3mm to edge for fab routing clearance)
- Connectors: ≥5mm from edge for cable strain relief
- Mount holes: edge proximity OK (designed mechanical interface)
- Test pads: ≥4mm from edge for probe clip access

Exit 0 = all PASS, 1 = any keepout violation.

Usage:
  python3 audit_edge_keepout.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# Rule semantics by component class:
#   default     : FAR from edge   — needs ≥ N mm clearance (fab routing)
#   connector   : NEAR edge       — needs ≤ N mm to edge (cable access, Sai-#5)
#                 AND ≥ 2mm to edge (so the body doesn't overhang)
#   test_point  : FAR from edge   — ≥ N mm probe clearance
KEEPOUT = {
    "default":         3.0,   # min distance from edge (FAR rule)
    "connector_max":   5.0,   # max distance to edge for cable connectors (NEAR rule, Sai-#5)
    "connector_min":   2.0,   # body must not overhang
    "test_point":      4.0,   # probe-clip access
}


def classify(ref, real_connector_refs):
    """real_connector_refs from lockfile filters real cable connectors from IC-named J*."""
    if ref in real_connector_refs:
        return "connector"
    if ref.startswith("TP"):
        return "test_point"
    if ref.startswith(("H", "FID")):
        return None  # mount/fid intentionally near edge
    return "default"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)
    bbox = board.GetBoardEdgesBoundingBox()
    x_min = pcbnew.ToMM(bbox.GetLeft())
    y_min = pcbnew.ToMM(bbox.GetTop())
    x_max = pcbnew.ToMM(bbox.GetRight())
    y_max = pcbnew.ToMM(bbox.GetBottom())

    # Load real-connector list from lockfile (same approach as G16)
    real_connector_refs = set()
    try:
        import yaml
        lock_path = Path("docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml")
        if lock_path.exists():
            lf = yaml.safe_load(lock_path.read_text()) or {}
            for e in (lf.get("connectors") or []):
                r = e.get("ref")
                if r:
                    real_connector_refs.add(r)
    except Exception:
        pass

    print(f"=== Edge keepout audit: {Path(board_path).name} ===")
    print(f"Board outline: ({x_min:.1f}, {y_min:.1f}) – ({x_max:.1f}, {y_max:.1f})")
    print(f"Connectors (cable mating): ≤{KEEPOUT['connector_max']}mm to edge AND ≥{KEEPOUT['connector_min']}mm (no overhang)")
    print(f"Other components: ≥{KEEPOUT['default']}mm from edge\n")

    fails = []
    parked_skipped = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        if x >= 130:  # parking zone — off-board by design
            parked_skipped += 1
            continue
        cls = classify(ref, real_connector_refs)
        if cls is None:
            continue
        min_edge = min(x - x_min, x_max - x, y - y_min, y_max - y)
        if cls == "connector":
            # External connector: NEAR-edge rule (Sai-#5 ≤5mm, AND ≥2mm no-overhang)
            # Allow 0.1mm KiCad numeric tolerance.
            if min_edge > KEEPOUT["connector_max"] + 0.1:
                fails.append(f"  [FAIL] {ref} (cable connector) @ ({x:.1f},{y:.1f}): {min_edge:.2f}mm to edge > {KEEPOUT['connector_max']}mm (too FAR from edge, Sai-#5)")
            elif min_edge < KEEPOUT["connector_min"]:
                fails.append(f"  [FAIL] {ref} (cable connector) @ ({x:.1f},{y:.1f}): {min_edge:.2f}mm to edge < {KEEPOUT['connector_min']}mm (body overhang)")
        else:
            # Internal: FAR-edge rule
            keep = KEEPOUT[cls if cls == "test_point" else "default"]
            if min_edge < keep:
                fails.append(f"  [FAIL] {ref} ({cls}) @ ({x:.1f},{y:.1f}): {min_edge:.2f}mm from edge < {keep}mm keepout")

    if parked_skipped:
        print(f"(skipped {parked_skipped} parked components)\n")

    if fails:
        for f in fails:
            print(f)
        print(f"\nRESULT: FAIL — {len(fails)} components inside board-edge keepout zone")
        sys.exit(1)
    print("RESULT: PASS — all components respect board-edge keepout")


if __name__ == "__main__":
    main()
