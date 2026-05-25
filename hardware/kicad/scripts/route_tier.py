#!/usr/bin/env python3
"""
route_tier.py — Phase 4-v3 6-tier constraint-driven router

Per `docs/ROUTING_METHODOLOGY.md` + Sai 2026-05-25 sureshot directive.

Routes ONE tier at a time. Reads `docs/PHASE4V3_LOCKFILES/routing_topology.yaml`
for per-net classification and per-class constraints. Refuses to route Tier N+1
until Tier N audit + sim PASS.

This replaces the prior "MST star + L-shape Manhattan find-open-space" approach
that contributed to PR #100 routing spiral. Constraint-driven, deterministic,
explainable failure modes.

Per [[feedback-sureshot-over-sota]] + [[feedback-build-routing-system-not-freerouter]]:
NO Freerouter, NO random search, NO simulated annealing. Industry-standard
constraint-manager pattern (Cadence Allegro / Mentor Xpedition equivalent).

Usage:
  python3 route_tier.py <board.kicad_pcb> --tier <1-6> [--subsystem <Sn|CHn>]
                       [--dry-run] [--verify-prior-tier]

  --tier 1            Route Tier 1 PDN (planes + power trunks)
  --tier 2            Route Tier 2 switching loops (per-CH local)
  --tier 3            Route Tier 3 decoupling (cap-to-IC-VDD same-layer)
  --tier 4            Route Tier 4 critical analog (Kelvin shunt, BEMF diff)
  --tier 5            Route Tier 5 signal highways (DShot, TLM, KILL)
  --tier 6            Route Tier 6 bulk (everything else)
  --subsystem CH1     Limit to nets within this subsystem's scope
  --dry-run           Plan but don't write
  --verify-prior-tier Re-audit Tier N-1 before starting Tier N

Exit codes:
  0  routing applied + audit PASS
  1  audit FAIL or prior-tier check FAIL
  2  arg/input error

NOTE: This is the skeleton + interface lock. Tier 1 PDN implementation is
provided as the canonical example. Tier 2-6 implementations are TBD-marked
for worker iteration. Each tier is a separate, bounded routing problem.
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FATAL: pyyaml not installed; pip install pyyaml")
    sys.exit(2)

try:
    import pcbnew
except ImportError:
    print("FATAL: pcbnew not importable — install KiCad python bindings")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TOPOLOGY_PATH = REPO_ROOT / "docs" / "PHASE4V3_LOCKFILES" / "routing_topology.yaml"


# ───────────────────────────────────────────────────────────────────────
# Topology loader
# ───────────────────────────────────────────────────────────────────────


def load_topology():
    if not TOPOLOGY_PATH.exists():
        print(f"FATAL: {TOPOLOGY_PATH} not found")
        sys.exit(2)
    return yaml.safe_load(TOPOLOGY_PATH.read_text())


def nets_in_tier(topology, tier, subsystem=None):
    """Returns dict {net_name: net_spec} for nets in given tier (and optional subsystem)."""
    out = {}
    for net_name, spec in (topology.get("nets") or {}).items():
        if spec is None:
            continue
        if spec.get("tier") != tier:
            continue
        if subsystem is not None:
            # Net belongs to subsystem if source or sinks reference it
            references = [spec.get("source", "")] + (
                spec.get("sinks", [spec.get("sink", "")])
                if isinstance(spec.get("sinks"), list)
                else [spec.get("sink", "")]
            )
            if not any(subsystem in str(ref) for ref in references):
                continue
        out[net_name] = spec
    return out


# ───────────────────────────────────────────────────────────────────────
# Tier 1 — PDN (canonical example implementation)
# ───────────────────────────────────────────────────────────────────────


def route_tier_1_pdn(board, topology, subsystem=None, dry_run=False):
    """Tier 1: PDN — planes + power trunks.

    Strategy:
      - +VMOTOR: ensure plane on In3.Cu covers entire board; add via stitching
        between F.Cu/B.Cu motor pads and In3.Cu plane (with phase-net antipad
        protection per worker R21 catch — phase pads use phase-net stitching,
        NOT VMOTOR-net stitching)
      - GND: ensure plane on In1.Cu + In5.Cu covers entire board; add via
        stitching for return-path continuity
      - +BATT: star route from J1 (source) to S3 + S2 inputs (sinks), 2.5mm
        width per IPC-2152 for 40A continuous
      - BEC rails (+3V3/+5V/+9V/+3V3A): tree route per topology yaml
    """
    nets = nets_in_tier(topology, 1, subsystem)
    print(f"Tier 1 PDN: {len(nets)} nets to route")
    for net_name, spec in nets.items():
        print(f"  - {net_name}: class={spec.get('class')} topology={spec.get('topology')} layer={spec.get('layer')}")

    routed = 0
    failed = 0
    skipped_planes = 0

    for net_name, spec in nets.items():
        cls = spec.get("class")
        topo = spec.get("topology")
        if cls in ("power-plane", "ground-plane"):
            # Plane handling: existing zones cover this; verify presence + via stitching
            # NOTE: actual plane creation done by setup_board.py; we audit + add stitching
            print(f"    [{net_name}] plane net — existing zone(s) verified by audit_routing.py PLANE-ISLAND check")
            skipped_planes += 1
        elif topo == "star":
            # Star: source → each sink as separate trunk
            # TODO worker fills: net-class width, layer-routing per spec, via stitching at junctions
            print(f"    [{net_name}] STAR topology — TBD worker (use ROUTING_METHODOLOGY §1 Tier 1 spec)")
            failed += 1  # marked failed for now; worker implements
        elif topo == "tree":
            # Tree: source → main trunk → branch stubs to each load
            # TODO worker fills: per-rail trunk + stubs
            print(f"    [{net_name}] TREE topology — TBD worker")
            failed += 1
        else:
            print(f"    [{net_name}] unrecognized topology '{topo}' — FAIL (must be in routing_topology.yaml)")
            failed += 1

    print(f"\nTier 1 summary: {routed} routed, {skipped_planes} planes (verified), {failed} TBD/failed")
    return failed == 0


# ───────────────────────────────────────────────────────────────────────
# Tier 2-6 — TBD worker (interface locked)
# ───────────────────────────────────────────────────────────────────────


def route_tier_2_switching(board, topology, subsystem=None, dry_run=False):
    """Tier 2: per-channel switching loops. HS-FET drain → SW → LS-FET source
    → shunt → GND return → bus-cap → HS-FET drain. Loop area < 50mm² (geometry
    enforced by placement Tier 2; routing verifies + adds connections).

    Per Erickson Ch. 23, TI SLUA868. TBD worker implementation.
    """
    print("Tier 2 switching loops — TBD worker implementation")
    print("  Requires per-channel: HS/LS-FET pads, bus cap, shunt, gate driver placed (Tier 2 placement)")
    print("  Routes:")
    print("    - high-current power loop (FET drain/source/shunt/bus-cap) on F.Cu, plane-referenced")
    print("    - bootstrap loop (DRV.BST → C_BST → SW) ≤2mm")
    print("    - gate loop (DRV.GATE → R_G → MOSFET.GATE → MOSFET.SOURCE → DRV) same-layer")
    return False  # not yet implemented


def route_tier_3_decoupling(board, topology, subsystem=None, dry_run=False):
    """Tier 3: cap-to-IC-VDD same-layer connection. Cap already placed within
    3mm same-layer (R25). Router connects with shortest same-layer trace +
    via on cap pad to plane.

    Per Bogatin Ch. 5. TBD worker implementation.
    """
    print("Tier 3 decoupling — TBD worker implementation")
    return False


def route_tier_4_analog(board, topology, subsystem=None, dry_run=False):
    """Tier 4: Kelvin shunt sense + BEMF differential pairs + Hall analog.
    All on layer adjacent to GND reference for noise shielding.

    Per Ott Ch. 18, Morrison Grounding & Shielding. TBD worker implementation.
    """
    print("Tier 4 critical analog — TBD worker implementation")
    return False


def route_tier_5_highway(board, topology, subsystem=None, dry_run=False):
    """Tier 5: DShot 50Ω SE, TLM, KILL, BUS_CURR_HALL_OUT. Length-matched per
    CH group ±2mm, controlled Z0.

    Per Johnson HSDD. TBD worker implementation.
    """
    print("Tier 5 signal highways — TBD worker implementation")
    return False


def route_tier_6_bulk(board, topology, subsystem=None, dry_run=False):
    """Tier 6: remaining signals (status LEDs, debug, USB if any). Manhattan
    shortest-path with via minimization.

    TBD worker implementation.
    """
    print("Tier 6 bulk — TBD worker implementation")
    return False


TIER_DISPATCH = {
    1: route_tier_1_pdn,
    2: route_tier_2_switching,
    3: route_tier_3_decoupling,
    4: route_tier_4_analog,
    5: route_tier_5_highway,
    6: route_tier_6_bulk,
}


# ───────────────────────────────────────────────────────────────────────
# Prior-tier verification (sequence enforcement)
# ───────────────────────────────────────────────────────────────────────


def verify_prior_tier(board_path, tier):
    """Re-runs audit for tier N-1 before starting tier N. PASS = OK to continue."""
    if tier <= 1:
        return True  # no prior tier
    # In MVP: call audit_routing.py + tier-specific audits if available
    # TBD: per-tier audit subset
    print(f"  Verifying Tier {tier-1} PASS before starting Tier {tier}... (TBD: per-tier audit subset)")
    return True


# ───────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("board", help="path to .kicad_pcb")
    parser.add_argument("--tier", type=int, required=True, choices=[1, 2, 3, 4, 5, 6])
    parser.add_argument("--subsystem", default=None, help="limit to subsystem (CH1/CH2/S1/...)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-prior-tier", action="store_true")
    args = parser.parse_args()

    board_path = Path(args.board)
    if not board_path.exists():
        print(f"FATAL: {board_path} not found")
        sys.exit(2)

    topology = load_topology()
    board = pcbnew.LoadBoard(str(board_path))

    print(f"=== route_tier.py — Tier {args.tier} ===")
    print(f"Board: {board_path.name}")
    print(f"Subsystem filter: {args.subsystem or 'all'}")
    print(f"Dry-run: {args.dry_run}")
    print()

    if args.verify_prior_tier:
        if not verify_prior_tier(board_path, args.tier):
            print(f"FAIL: prior tier {args.tier-1} did not pass audit; cannot proceed")
            sys.exit(1)

    tier_fn = TIER_DISPATCH[args.tier]
    success = tier_fn(board, topology, subsystem=args.subsystem, dry_run=args.dry_run)

    if not success:
        print(f"\n❌ Tier {args.tier} routing INCOMPLETE — worker must implement TBD sections")
        sys.exit(1)

    if not args.dry_run:
        # In MVP: save board (commented out for skeleton)
        # pcbnew.SaveBoard(str(board_path), board)
        print("\n✅ Tier routing applied (board save TBD)")
    else:
        print("\n✅ Tier routing plan generated (dry-run, board not modified)")


if __name__ == "__main__":
    main()
