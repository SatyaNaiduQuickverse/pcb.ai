#!/usr/bin/env python3
"""
place_subsystem.py — Phase 4-v2 Step 2 subsystem placement engine

Places ALL components for a given subsystem within its declared zone
(per BOARD_INVARIANTS), anchoring passives to ICs using role-based
distance rules from constraint_engine + physics.

Per Sai 2026-05-24 mandate: redesign-don't-patch, physics-as-compass,
collision-aware (not whack-a-mole). Worker fills in the algorithm details
in the marked TODO regions.

INTERFACE LOCKED — worker implements the algorithm under this contract.

Usage:
  python3 place_subsystem.py <subsystem> [--dry-run] [--out <board.kicad_pcb>]

Examples:
  python3 place_subsystem.py CH1            # place CH1 on empty board, save in-place
  python3 place_subsystem.py CH1 --dry-run  # don't write, print plan
"""

import argparse
import math
import sys
from pathlib import Path

# Local imports (PR #87 routing system v2)
sys.path.insert(0, str(Path(__file__).parent))
import constraint_engine as ce
import physics_primitives as physics

try:
    import pcbnew
except ImportError:
    print("FATAL: pcbnew not importable — install KiCad python bindings.")
    sys.exit(2)


# ─── Subsystem component identification ───────────────────────────────────

def get_subsystem_components(board, subsystem, ce_obj):
    """Returns {ref: footprint} for components belonging to this subsystem.

    Identification heuristics:
      1. Net-suffix: refs whose pad nets end in `_CHn` belong to CHn
      2. Hard-coded prefix lists per subsystem (from project SKiDL conventions):
         CH1: Q5-Q10 + J18 + J19 + J20-22 + U3 + U4
         CH2: Q11-Q16 + J28 + J29 + J30-32 + U5 + U6 (mirror of CH1)
         CH3: Q17-Q22 + J38 + J39 + J40-42 + U7 + U8
         CH4: Q23-Q28 + J48 + J49 + J50-52 + U9 + U10
         S1:  XT30 (J1), NTC (R1-R2), Q1-Q4 protection FETs, D1-D8 TVS, fuse F1
         S2:  C1-C4 bulk caps
         S3:  TPS3700 (U1), ACS770 (U_HALL), R-dividers
         S5:  TPS54560 (U_BEC1-5), LDO (U_LDO), L_BEC*, C_BEC*
         S6:  FC header (J11), AUX (J12), USBLC6 (U_ESD), LEDs
    """
    # TODO worker fills: per-subsystem ref classification from schematic
    subsystem_prefixes = {
        "CH1": [f"Q{n}" for n in range(5, 11)] + ["J18", "J19", "J20", "J21", "J22", "U3", "U4"],
        "CH2": [f"Q{n}" for n in range(11, 17)] + ["J28", "J29", "J30", "J31", "J32", "U5", "U6"],
        "CH3": [f"Q{n}" for n in range(17, 23)] + ["J38", "J39", "J40", "J41", "J42", "U7", "U8"],
        "CH4": [f"Q{n}" for n in range(23, 29)] + ["J48", "J49", "J50", "J51", "J52", "U9", "U10"],
        "S1":  ["J1", "R1", "R2", "Q1", "Q2", "Q3", "Q4", "F1"] + [f"D{n}" for n in range(1, 9)],
        "S2":  ["C1", "C2", "C3", "C4"],
        "S3":  ["U1", "U2", "U_HALL"] + [f"R_DIV{n}" for n in range(1, 5)],
        "S5":  [f"U_BEC{n}" for n in range(1, 6)] + ["U_LDO"],
        "S6":  ["J11", "J12", "U_ESD"],
    }
    direct_refs = set(subsystem_prefixes.get(subsystem, []))

    # Component-by-component classification:
    components = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Mount holes + fiducials stay where they are
        if ref.startswith("H") or ref.startswith("FID"):
            continue

        # Direct prefix match
        if ref in direct_refs:
            components[ref] = fp
            continue

        # Net-suffix match (for *_CHn passives)
        for pad in fp.Pads():
            netname = pad.GetNetname()
            if netname.endswith(f"_{subsystem}"):
                components[ref] = fp
                break

    return components


# ─── IC anchoring (high priority — placed first) ──────────────────────────

def anchor_ics(components, zone_bbox, ce_obj):
    """Place ICs within zone with minimum IC-IC separation.

    Returns {ref: (x, y, rotation_deg)}.

    Algorithm (worker fills):
      - Compute IC list (footprint body_size > 3mm² as heuristic)
      - Greedy place largest IC first at zone center
      - Subsequent ICs: nearest free position with ≥10mm center-to-center
      - Honor I/O port positions — IC nearest to a declared I/O port
        should be the one driving that signal (e.g., MCU near S6 ports)

    Returns placement dict; collisions are FAILURE (no placement).
    """
    x0, y0, x1, y1 = zone_bbox
    placements = {}

    # Classify by size
    ic_refs = []
    for ref, fp in components.items():
        bb = fp.GetBoundingBox()
        body_mm2 = (pcbnew.ToMM(bb.GetWidth()) * pcbnew.ToMM(bb.GetHeight()))
        if body_mm2 > 3.0:  # heuristic: ICs are >3mm² body
            ic_refs.append((ref, fp, body_mm2))

    # Place largest first
    ic_refs.sort(key=lambda x: -x[2])

    # TODO worker fills: actual collision-aware IC anchoring algorithm
    # Suggested approach:
    #   1. Largest IC at zone center
    #   2. For each next: scan 30-candidate positions in spiral from center
    #   3. For each candidate: check IC-IC ≥10mm + zone-bbox contain + per-IC
    #      access to relevant I/O port (MCU→S6, DRV→FET cluster, etc.)
    #   4. Return failure if no valid position for any IC
    return placements  # SKELETON returns empty — worker implements


# ─── Passive auto-anchoring (role-based, distance-bounded) ────────────────

def role_based_anchor_passives(passives, ic_placements, ce_obj):
    """Anchor each passive to its parent IC per role-based distance rules.

    Rules (per locked R23 + R25 + memories):
      - Decoupling caps: ≤3mm from host VDD pin, SAME copper layer (R25)
      - Gate resistors (R_G): ≤5mm from gate driver output pin
      - Bootstrap caps: ≤2mm from BST pin
      - INA shunts: ≤2mm from INA± pins (same package side)
      - Pull-ups: ≤10mm from receiver pin
      - General passives: nearest available slot within zone, ≥0.2mm pad clearance

    Returns {ref: (x, y, rotation, layer)}.

    Algorithm (worker fills):
      1. For each passive, identify parent IC from netname pattern
      2. Look up role from ref prefix + netname (e.g., C_VDD = decoupling, R_G = gate-R)
      3. Get role's max-distance from rules table
      4. Search candidate positions around IC pad within max-distance
      5. Validate: no pad overlap, no IC body overlap, on same layer for R25
      6. If no valid position: try smaller package size (decoupling 0402 fallback)
      7. If still no position: surface failure to caller (no patches)
    """
    placements = {}
    # TODO worker fills
    return placements


# ─── Per-place validation ─────────────────────────────────────────────────

def validate_placement(board, placement, ref, ce_obj):
    """Returns (valid, reason). Checks at insert time:
      - Position inside subsystem zone (constraint_engine)
      - No highway encroachment (constraint_engine)
      - No pad-overlap-diff-net with already-placed components
      - No silk-on-pad
      - No component-inside-body for tight clusters
      - For R25-decoupling: cap on same layer as IC power pin

    Per L5 lesson: zone violation surfaces here, not at post-audit.
    """
    x, y = placement[:2]
    rotation = placement[2] if len(placement) > 2 else 0
    layer = placement[3] if len(placement) > 3 else "F.Cu"

    # Zone containment
    # TODO: get target subsystem from caller context
    in_zone = ce_obj.position_to_subsystem(x, y)
    if not in_zone:
        return False, f"position ({x:.2f}, {y:.2f}) not in any declared zone"

    # Highway encroachment
    in_highway = ce_obj.is_position_in_highway(x, y)
    if in_highway:
        return False, f"position ({x:.2f}, {y:.2f}) in reserved highway '{in_highway}'"

    # TODO worker fills: per-pad collision check vs already-placed components
    return True, "OK"


# ─── Main flow ────────────────────────────────────────────────────────────

def place_subsystem(subsystem_name, board_path, dry_run=False):
    """Top-level: place all components of subsystem within its zone."""
    print(f"=== place_subsystem({subsystem_name}) ===\n")

    # Load constraint engine (BOARD_INVARIANTS + lessons)
    inv = ce.parse_board_invariants()
    lessons = ce.parse_routing_lessons()
    ce_obj = ce.ConstraintEngine(inv, lessons)

    if subsystem_name not in inv.zones:
        print(f"FATAL: subsystem '{subsystem_name}' not in BOARD_INVARIANTS zones")
        print(f"       available: {sorted(inv.zones.keys())}")
        sys.exit(2)
    zone_bbox = inv.zones[subsystem_name]
    print(f"Zone: {zone_bbox}")
    print(f"BOARD_INVARIANT_HASH: {inv.invariant_hash[:16]}...")
    print(f"ROUTING_LESSONS_HASH: {lessons.hash[:16] if lessons.hash else 'NONE'}...")
    print()

    board = pcbnew.LoadBoard(board_path)
    components = get_subsystem_components(board, subsystem_name, ce_obj)
    print(f"Subsystem components: {len(components)}")
    for ref in sorted(components.keys())[:10]:
        print(f"  {ref}: {components[ref].GetFPID().GetLibItemName()}")
    if len(components) > 10:
        print(f"  ... +{len(components) - 10} more")
    print()

    # Phase 1: anchor ICs
    print("Phase 1: IC anchoring...")
    ic_placements = anchor_ics(components, zone_bbox, ce_obj)
    print(f"  ICs placed: {len(ic_placements)}")
    print()

    # Phase 2: passive role-based anchoring
    print("Phase 2: passive anchoring...")
    passives = {r: f for r, f in components.items()
                if r not in ic_placements}
    passive_placements = role_based_anchor_passives(passives, ic_placements, ce_obj)
    print(f"  Passives placed: {len(passive_placements)}")
    print()

    # Phase 3: validate every placement at insert time
    all_placements = {**ic_placements, **passive_placements}
    print(f"Phase 3: validating {len(all_placements)} placements...")
    fails = []
    for ref, place in all_placements.items():
        ok, reason = validate_placement(board, place, ref, ce_obj)
        if not ok:
            fails.append((ref, reason))
    if fails:
        print(f"  FAIL: {len(fails)} placements failed")
        for ref, reason in fails[:10]:
            print(f"    {ref}: {reason}")
        sys.exit(1)
    print(f"  All {len(all_placements)} placements valid")
    print()

    # Apply placements to board (unless dry-run)
    if dry_run:
        print("[dry-run] not writing to board")
    else:
        for ref, (x, y, *rest) in all_placements.items():
            fp = components[ref]
            fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
            if rest and rest[0] != 0:
                fp.SetOrientationDegrees(rest[0])
            if len(rest) > 1 and rest[1] != fp.GetLayerName():
                # Flip if needed
                if rest[1] == "B.Cu":
                    fp.Flip(fp.GetPosition(), True)
        pcbnew.SaveBoard(board_path, board)
        print(f"  Saved to {board_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("subsystem", help="e.g., CH1, S1, S2, S3, S5, S6")
    parser.add_argument("--out", default="hardware/kicad/pcbai_fpv4in1.kicad_pcb")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    place_subsystem(args.subsystem, args.out, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
