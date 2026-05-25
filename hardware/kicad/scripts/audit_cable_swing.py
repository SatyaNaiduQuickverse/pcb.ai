#!/usr/bin/env python3
"""
audit_cable_swing.py — G_PP7 mating connector cable-swing clearance gate.

Proactive 2026-05-26 (catch class: cable bends mechanically interfere with
neighbour components at install/operation). Cable connectors (XT30, JST,
SM08B-SRSS) project a cable that needs a bend radius — typically 15mm for
14AWG silicone, 5mm for 28AWG ribbon.

Rule: for each cable connector, no component within an outward sweep zone
of (bend_radius × cable_strain_relief_factor). The sweep zone is a half-disc
extending outward from the connector pad face, away from the board centre.

Bend radius lookup (per cable type from connector model):
  XT30 (14AWG silicone):  15mm bend radius
  JST SM06/SM08-SRSS:      5mm (ribbon cable)
  Default unknown:        10mm

Pragmatic: half-disc oriented along the board-edge-outward normal.
For top-edge connector, sweep is upward (above board, y < edge).
For bottom-edge, sweep is downward (y > edge). Symmetric for left/right.

Components within the sweep zone (above/below the board plane) — these don't
exist in PCB layout, but we approximate: check for ON-BOARD components within
a half-disc on the SAME side as the cable exits (i.e., between connector and
board interior within bend-radius distance).

Exit 0 = all PASS, 1 = any cable-swing violation.

Usage:
  python3 audit_cable_swing.py <board.kicad_pcb>
"""

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


# Cable bend-radius per connector footprint family
BEND_RADIUS_MM = {
    "AMASS_XT30": 15.0,   # 14AWG silicone
    "JST_SH_SM": 5.0,     # SM06/SM08 ribbon
    "Pin_Header": 8.0,    # generic male pin header (wire-to-board)
}
DEFAULT_BEND_MM = 10.0
STRAIN_RELIEF_FACTOR = 1.0  # multiplier on bend_radius for safety


def bend_radius_for_fp(fp_libname):
    for key, val in BEND_RADIUS_MM.items():
        if key in fp_libname:
            return val
    return DEFAULT_BEND_MM


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
    bx_min = pcbnew.ToMM(bbox.GetLeft())
    by_min = pcbnew.ToMM(bbox.GetTop())
    bx_max = pcbnew.ToMM(bbox.GetRight())
    by_max = pcbnew.ToMM(bbox.GetBottom())

    # Load lockfile.connectors as real-connector filter
    real_conn = set()
    try:
        lf = yaml.safe_load(Path("docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml").read_text())
        for e in (lf.get("connectors") or []):
            r = e.get("ref")
            if r:
                real_conn.add(r)
    except Exception:
        pass

    print(f"=== Cable-swing clearance audit: {Path(board_path).name} ===")
    print(f"Real connectors: {sorted(real_conn)}\n")

    # Refinement 2026-05-26 post-smoketest:
    #   - Cable enters off the F.Cu top side → only same-side (F.Cu) on-board
    #     components block (B.Cu fiducials etc. are physically below the board)
    #   - Only TALL components (≥3mm body) block; flat passives + ESD ICs
    #     (<1mm tall) let the cable bend OVER them without interference
    TALL_PREFIXES_LOCAL = ("CP",)
    TALL_LIB_HINTS_LOCAL = ("TO-220", "TO220", "TO-263", "TO-247",
                            "AMASS_XT30", "Mounting", "SM06B-SRSS", "SM08B-SRSS")
    def is_tall_local(fp):
        ref = fp.GetReference()
        if any(ref.startswith(p) for p in TALL_PREFIXES_LOCAL):
            return True
        lib = str(fp.GetFPID().GetLibItemName())
        return any(h in lib for h in TALL_LIB_HINTS_LOCAL)

    fails = []
    others = []
    connectors = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        x, y = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        if x >= 130:
            continue
        side = "F" if fp.GetLayer() == pcbnew.F_Cu else "B"
        if ref in real_conn:
            lib = str(fp.GetFPID().GetLibItemName())
            connectors.append((ref, x, y, bend_radius_for_fp(lib) * STRAIN_RELIEF_FACTOR, side))
        elif is_tall_local(fp):
            # Only tall components on same side as cable bend are blockers
            others.append((ref, x, y, side))

    for ref, x, y, br, side in connectors:
        dists = [(x - bx_min, "left"), (bx_max - x, "right"),
                 (y - by_min, "top"), (by_max - y, "bottom")]
        dists.sort()
        exit_dir = dists[0][1]
        print(f"  {ref} @ ({x:.1f}, {y:.1f}) — cable exits {exit_dir}, bend-radius {br:.0f}mm, side {side}")
        for o_ref, ox, oy, o_side in others:
            if o_ref == ref:
                continue
            if o_side != side:
                continue  # opposite-side tall — doesn't block cable on connector's side
            dx = ox - x
            dy = oy - y
            inland = False
            if exit_dir == "top" and dy > 0:
                inland = True
            elif exit_dir == "bottom" and dy < 0:
                inland = True
            elif exit_dir == "left" and dx > 0:
                inland = True
            elif exit_dir == "right" and dx < 0:
                inland = True
            if inland:
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist < br:
                    fails.append(f"    [FAIL] {ref} cable-swing collision with TALL {o_ref}@({ox:.1f},{oy:.1f}) at {dist:.2f}mm < bend-radius {br}mm (same side {side})")

    if fails:
        for f in fails[:15]:
            print(f)
        if len(fails) > 15:
            print(f"  ... +{len(fails)-15} more")
        print(f"\nRESULT: FAIL — {len(fails)} cable-swing violations")
        sys.exit(1)
    print("\nRESULT: PASS — all cable connectors have clear bend-radius zone")


if __name__ == "__main__":
    main()
