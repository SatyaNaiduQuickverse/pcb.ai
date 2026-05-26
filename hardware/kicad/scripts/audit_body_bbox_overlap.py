#!/usr/bin/env python3
"""audit_body_bbox_overlap.py — G_PP11 component-body bbox overlap audit.

THE class-of-mistake meta-failure root cause (Sai 2026-05-26):

A bbox-overlap check existed in verify_placement.py (Phase 4-v1, Task #47
"Phase 4-bbox-check-tool") using pcbnew BOX2I::Intersects(). It was NEVER
promoted into the Phase 4-v3 47-gate BLOCKING suite during phase migrations.

Result: 47 + 7 (G_M7-M13) + 1 (G_M14) = 55 BLOCKING gates passed CH1 placement
with 57 same-layer body bbox overlaps (Sai-eye caught: D24/25/26 stacked on
Q6 LS-FET; J18 MCU overlapped by D37/D33/R76/J21; U4 op-amp overlapped by
D38/D19/D15 LEDs). Audit suite was checking pad-DRC + creepage + edge clearance
+ mount-hole + symmetry + zones + symmetry + ... but NOT the most fundamental
check: does component body A overlap component body B on the same layer.

G_PP11 closes that gap.

ALGORITHM:
  For every pair of footprints (i, j) where i < j and same layer:
    If footprint[i].GetBoundingBox(False, False).Intersects(footprint[j].GetBoundingBox()):
      FAIL unless (i.ref, j.ref) in EXEMPT_PAIRS.

EXEMPT pairs are documented same-net intentional-overlap cases:
  - HS-FET ↔ same-phase gate-R (gate-R sits at FET gate pin)
  - HS-FET ↔ same-phase bypass cap (cap sits at FET drain via cluster)
  - LS-FET ↔ same-phase gate-clamp diode (if intentional sharing on B.Cu)

The exempt list MUST be explicit per ref-pair, not "this class of part". Adding
to exempt list requires Sai-call. No silent skip.

Exit 0 = PASS (zero overlaps or all in exempt), 1 = FAIL.

Per [[feedback-codify-not-patch]] + [[feedback-systemic-rule-enforcement]]:
this fixes a class-of-failure not just CH1.
"""
import os, sys

def main():
    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not available", file=sys.stderr); return 1

    pcb_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

    board = pcbnew.LoadBoard(pcb_path)
    mm = 1000000.0

    # EXEMPT_PAIRS — documented intentional bbox overlaps.
    # Format: frozenset({ref_a, ref_b}). Order-independent.
    # Empty initially — populate as Sai-approves specific exceptions.
    EXEMPT_PAIRS = set()

    # Read exempt list from external file if present
    exempt_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "..", "..", "docs", "BBOX_OVERLAP_EXEMPT.txt")
    if os.path.exists(exempt_file):
        for ln in open(exempt_file):
            ln = ln.strip()
            if not ln or ln.startswith("#"): continue
            parts = ln.split()
            if len(parts) >= 2:
                EXEMPT_PAIRS.add(frozenset((parts[0], parts[1])))

    fps = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Skip unplaced parts (e.g., parked at default off-board grid)
        pos = fp.GetPosition()
        x = pos.x / mm; y = pos.y / mm
        if x < -5 or x > 200 or y < -5 or y > 200:
            continue
        bbox = fp.GetBoundingBox(False, False)
        layer = "F.Cu" if fp.GetLayer() == pcbnew.F_Cu else "B.Cu"
        fps.append((ref, bbox, layer, x, y))

    fails = []
    exempt_used = []
    for i in range(len(fps)):
        for j in range(i+1, len(fps)):
            ra, ba, la, xa, ya = fps[i]
            rb, bb, lb, xb, yb = fps[j]
            if la != lb:
                continue
            if not ba.Intersects(bb):
                continue
            pair = frozenset((ra, rb))
            if pair in EXEMPT_PAIRS:
                exempt_used.append(pair); continue
            # compute overlap dimensions for the report
            ax0 = ba.GetX()/mm; ay0 = ba.GetY()/mm
            ax1 = ax0 + ba.GetWidth()/mm; ay1 = ay0 + ba.GetHeight()/mm
            bx0 = bb.GetX()/mm; by0 = bb.GetY()/mm
            bx1 = bx0 + bb.GetWidth()/mm; by1 = by0 + bb.GetHeight()/mm
            ox = max(0, min(ax1, bx1) - max(ax0, bx0))
            oy = max(0, min(ay1, by1) - max(ay0, by0))
            fails.append((ra, rb, la, ox, oy, xa, ya, xb, yb))

    print("=" * 70)
    print(f"audit_body_bbox_overlap.py G_PP11 — {len(fps)} on-board footprints, {pcb_path}")
    print("=" * 70)
    if exempt_used:
        print(f"  ℹ {len(exempt_used)} exempt-pair overlap(s) skipped (listed in BBOX_OVERLAP_EXEMPT.txt)")
    if fails:
        # group by layer
        f_fail = [f for f in fails if f[2] == "F.Cu"]
        b_fail = [f for f in fails if f[2] == "B.Cu"]
        print()
        print(f"  ❌ FAIL — {len(fails)} component-body bbox overlap(s) ({len(f_fail)} F.Cu + {len(b_fail)} B.Cu)")
        print()
        # Show worst first
        worst = sorted(fails, key=lambda f: -(f[3]*f[4]))[:30]
        print("  Worst 30:")
        for ra, rb, la, ox, oy, xa, ya, xb, yb in worst:
            print(f"    {ra:6} @ ({xa:5.1f},{ya:5.1f}) ↔ {rb:6} @ ({xb:5.1f},{yb:5.1f}) [{la}]: {ox:5.2f}mm × {oy:5.2f}mm")
        return 1
    print()
    print(f"  ✅ PASS — zero same-layer body bbox overlaps (or all in EXEMPT_PAIRS)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
