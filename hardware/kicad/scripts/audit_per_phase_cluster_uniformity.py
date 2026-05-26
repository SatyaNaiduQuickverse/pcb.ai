#!/usr/bin/env python3
"""audit_per_phase_cluster_uniformity.py — per-phase cluster pitch uniformity.

Class lesson 2026-05-26 (worker-caught during CH1 STEP 4 routing):

  J22 INA was at y=78 (canonical) instead of y=80, breaking the 3-INA
  uniform-Δ13 pitch (J20=54, J21=67, J22 should be 80 not 78). Root cause:
  sign typo in parametric_placement.py:254 — `motor['TP21'][1] - 1` instead
  of `+ 1`. The bug was within WARN-tolerance on existing placement gates +
  passed all 56 BLOCKING gates. Surfaced only when worker tried to apply R19
  pure-transform for STEP 4 routing (3-INA pitch mismatch breaks transform).

Per [[feedback-codify-not-patch]]: source-fix is necessary but not
sufficient — next sign typo on a different component will pass same gates.
This audit is the safety net independent of source.

Rule: for each declared per-phase cluster (3 instances, one per channel
phase A/B/C), the y-pitch between consecutive instances MUST be uniform
within 0.5mm tolerance. FAIL on any cluster with max(pitch) - min(pitch)
> 0.5mm. WARN-tolerance was the bug — this is binary FAIL.

Per-phase clusters (CH1 — extends to CH2/3/4 when they re-place):
  - HS FETs:    Q5, Q7, Q9
  - LS FETs:    Q6, Q8, Q10
  - Boot caps:  C59, C60, C61
  - Gate-R HS:  R45, R49, R53
  - Gate-R LS:  R46, R50, R54
  - Shunts:     R57, R58, R59
  - INAs:       J20, J21, J22  (the J22 trigger class)
  - Dividers:   R60, R62, R64

Exit 0 = all clusters uniform within 0.5mm, 1 = any cluster non-uniform.

Usage:
  python3 audit_per_phase_cluster_uniformity.py <board.kicad_pcb>
"""

import sys
from pathlib import Path

PER_PHASE_CLUSTERS_CH1 = {
    "HS_FETs_CH1":   ["Q5", "Q7", "Q9"],
    "LS_FETs_CH1":   ["Q6", "Q8", "Q10"],
    "Boot_caps_CH1": ["C59", "C60", "C61"],
    "Gate_R_HS_CH1": ["R45", "R49", "R53"],
    "Gate_R_LS_CH1": ["R46", "R50", "R54"],
    "Shunts_CH1":    ["R57", "R58", "R59"],
    "INAs_CH1":      ["J20", "J21", "J22"],
    "Dividers_CH1":  ["R60", "R62", "R64"],
}

# Future: extend with CH2/3/4 ref maps when those channels re-place
# PER_PHASE_CLUSTERS_CH2 = { ... mirrored Y ... }

PITCH_TOLERANCE_MM = 0.5
MM = 1_000_000.0  # pcbnew uses internal nanometers


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {Path(__file__).name} <board.kicad_pcb>", file=sys.stderr)
        sys.exit(2)
    pcb_path = sys.argv[1]
    if not Path(pcb_path).exists():
        print(f"=== Per-phase cluster uniformity audit ===")
        print(f"INFO: board not found ({pcb_path}) — gate inert")
        sys.exit(0)

    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not importable", file=sys.stderr)
        sys.exit(2)

    board = pcbnew.LoadBoard(pcb_path)
    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}

    print(f"=== Per-phase cluster uniformity audit: {Path(pcb_path).name} ===\n")
    fails = []
    skipped = []
    for cluster_name, ref_list in PER_PHASE_CLUSTERS_CH1.items():
        positions = []
        for r in ref_list:
            if r not in refs:
                skipped.append(f"{cluster_name}: {r} missing on board")
                positions = None
                break
            pos = refs[r].GetPosition()
            positions.append((r, pos.x / MM, pos.y / MM))
        if positions is None:
            continue
        # Sort by y (transformable cluster is y-stacked per parametric_placement)
        positions.sort(key=lambda t: t[2])
        pitches = []
        for i in range(1, len(positions)):
            dy = positions[i][2] - positions[i-1][2]
            pitches.append((positions[i-1][0], positions[i][0], dy))
        pitch_values = [p[2] for p in pitches]
        pitch_spread = max(pitch_values) - min(pitch_values)
        status = "PASS" if pitch_spread <= PITCH_TOLERANCE_MM else "FAIL"
        marker = "  ✅" if status == "PASS" else "  ❌"
        print(f"{marker} {cluster_name:18} pitches={[f'{p[2]:.2f}' for p in pitches]} spread={pitch_spread:.3f}mm")
        if status == "FAIL":
            fails.append((cluster_name, pitches, pitch_spread, positions))

    if skipped:
        print(f"\n  Skipped ({len(skipped)} cluster(s) — refs missing on this board):")
        for s in skipped[:5]:
            print(f"    {s}")

    if not fails:
        print(f"\nRESULT: PASS — all {len(PER_PHASE_CLUSTERS_CH1) - len([s for s in skipped if s])} cluster(s) uniform within {PITCH_TOLERANCE_MM}mm")
        sys.exit(0)

    print(f"\n  FAIL details:")
    for cluster, pitches, spread, positions in fails:
        print(f"    {cluster}: spread {spread:.3f}mm > tolerance {PITCH_TOLERANCE_MM}mm")
        for r, x, y in positions:
            print(f"      {r:5s} at ({x:.2f}, {y:.2f})")
        for r1, r2, dy in pitches:
            print(f"      {r1} → {r2}: Δy = {dy:.3f}mm")
    print(f"\nRESULT: FAIL — {len(fails)} cluster(s) non-uniform; R19 pure-transform broken")
    print(f"  Fix: locate parametric_placement.py source of anchor; check for sign/offset bugs")
    print(f"  Rationale: J22 class lesson 2026-05-26 — single-char source bug, WARN-tolerance escape, breaks R19")
    sys.exit(1)


if __name__ == "__main__":
    main()
