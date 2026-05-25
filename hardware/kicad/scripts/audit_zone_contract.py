#!/usr/bin/env python3
"""audit_zone_contract.py — Phase 4-v3 PARK-THEN-BRING-IN contract gate.

The single gate that makes "ghost" components structurally impossible. Given the
set of subsystems brought so far (the PRs merged up to this point), it asserts
that EVERY component on the board is exactly where the process says it must be:

  fixed (FID*, H*)                  → ignored (mechanical, never parked)
  roster subsystem ∈ brought        → MUST be on-board AND inside that zone
  roster subsystem ∉ brought        → MUST still be parked (off-board)
  on-board but ∉ any brought zone   → GHOST — the exact failure this prevents

Because the gate covers the FULL board (not just the PR's new components), a
per-PR pass here means no stale inherited component is hiding in an old position.
That is the property the 9 v2 PRs lacked: each audited only its own additions and
was blind to the 490 inherited footprints left in place ([[ghost-components]]).

Run after every bring-in PR with the cumulative brought-subsystem list:
  python3 audit_zone_contract.py --board B --brought CH1,CH2,S1
  python3 audit_zone_contract.py --board B --brought CH1 --parked-only   # pre-bring
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import constraint_engine as ce
import roster as roster_mod
from place_subsystem import SUBSYS_ZONES, is_parked, in_any_zone
from park_all_components import is_fixed

try:
    import pcbnew
except ImportError:
    print("FATAL: pcbnew not importable")
    sys.exit(2)


def audit(board, brought):
    inv = ce.parse_board_invariants()
    zone_of = {s: [inv.zones[z] for z in zs] for s, zs in SUBSYS_ZONES.items()}
    roster = roster_mod.derive_roster(roster_mod.parse_netlist())

    fails = []
    stats = {"fixed": 0, "in_zone": 0, "parked": 0, "checked": 0}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if is_fixed(ref):
            stats["fixed"] += 1
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
    print(f"fixed={stats['fixed']} checked={stats['checked']} "
          f"in_zone={stats['in_zone']} parked={stats['parked']}")
    if fails:
        print(f"\nCONTRACT FAIL: {len(fails)} violations")
        for f in fails[:25]:
            print(f"  {f}")
        if len(fails) > 25:
            print(f"  ... +{len(fails) - 25} more")
        return 1
    print("\nCONTRACT OK — every component fixed, in a brought zone, or parked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
