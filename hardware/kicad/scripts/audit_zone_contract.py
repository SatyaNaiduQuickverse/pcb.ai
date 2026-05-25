#!/usr/bin/env python3
"""audit_zone_contract.py — Phase 4-v3 PARK-THEN-BRING-IN contract gate (G2).

The single gate that makes "ghost" components structurally impossible. Given the
set of subsystems brought so far (the PRs merged up to this point), it asserts
that EVERY component on the board is exactly where the process says it must be:

  foundation (mounts/fiducials/J1/J11/J12)  → placed once at lockfile pos (G1 owns
                                               position; here just not-parked)
  roster subsystem ∈ brought, anchored      → on-board (its coord is G1's job)
  roster subsystem ∈ brought, non-anchor    → inside that subsystem's zone
  roster subsystem ∉ brought                → still parked (off-board)
  on-board but its subsystem not brought     → GHOST — the exact failure prevented

Because the gate covers the FULL board (not just the PR's new components), a
per-PR pass means no stale inherited component is hiding in an old position — the
property the 9 v2 PRs lacked ([[ghost-components]]).

  python3 audit_zone_contract.py --board B --brought CH1,CH2,S1
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import constraint_engine as ce
import lockfile
import roster as roster_mod
from place_subsystem import SUBSYS_ZONES, is_parked, in_any_zone

try:
    import pcbnew
except ImportError:
    print("FATAL: pcbnew not importable")
    sys.exit(2)


def audit(board, brought):
    inv = ce.parse_board_invariants()
    zone_of = {s: [inv.zones[z] for z in zs] for s, zs in SUBSYS_ZONES.items()}
    roster = roster_mod.derive_roster(roster_mod.parse_netlist())
    foundation = lockfile.foundation_refs()
    anchors = lockfile.load_anchors()

    fails = []
    stats = {"foundation": 0, "in_zone": 0, "anchored": 0, "parked": 0, "checked": 0}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in foundation:
            stats["foundation"] += 1
            if is_parked(fp):
                fails.append(f"FOUNDATION-PARKED: {ref} should be at lockfile pos")
            continue
        stats["checked"] += 1
        p = fp.GetPosition()
        x, y = p.x / 1e6, p.y / 1e6
        sub = roster.get(ref)
        if sub is None:
            fails.append(f"UNKNOWN: {ref} on board but not in roster")
            continue
        if sub in brought:
            if is_parked(fp):
                fails.append(f"NOT-BROUGHT: {ref} ({sub}) still parked though "
                             f"{sub} was brought")
            elif ref in anchors:
                stats["anchored"] += 1  # exact coord verified by audit_anchor_positions (G1)
            elif not in_any_zone(x, y, zone_of[sub]):
                fails.append(f"OUT-OF-ZONE: {ref} ({sub}) at ({x:.1f},{y:.1f}) "
                             f"not in {sub} zone")
            else:
                stats["in_zone"] += 1
        else:  # subsystem not yet brought → must be parked
            if not is_parked(fp):
                fails.append(f"GHOST: {ref} ({sub}) on-board at ({x:.1f},{y:.1f}) "
                             f"but {sub} not in brought set {sorted(brought)}")
            else:
                stats["parked"] += 1
    return fails, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="hardware/kicad/pcbai_fpv4in1_parked.kicad_pcb")
    ap.add_argument("--brought", default="",
                    help="comma-separated subsystems brought so far, e.g. CH1,CH2,S1")
    args = ap.parse_args()
    brought = {s.strip() for s in args.brought.split(",") if s.strip()}
    bad = brought - set(SUBSYS_ZONES)
    if bad:
        print(f"FATAL: unknown subsystems {bad}; valid: {sorted(SUBSYS_ZONES)}")
        return 2

    board = pcbnew.LoadBoard(args.board)
    fails, stats = audit(board, brought)

    print(f"board: {args.board}")
    print(f"brought: {sorted(brought) or '(none — fully parked)'}")
    print(f"foundation={stats['foundation']} checked={stats['checked']} "
          f"in_zone={stats['in_zone']} anchored={stats['anchored']} parked={stats['parked']}")
    if fails:
        print(f"\nCONTRACT FAIL: {len(fails)} violations")
        for f in fails[:25]:
            print(f"  {f}")
        if len(fails) > 25:
            print(f"  ... +{len(fails) - 25} more")
        return 1
    print("\nCONTRACT OK — every component foundation, brought (in-zone/anchored), or parked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
