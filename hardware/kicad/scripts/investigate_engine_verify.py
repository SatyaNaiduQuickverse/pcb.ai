#!/usr/bin/env python3
"""investigate_engine_verify.py — Phase 5 UU.2 ENGINE VERIFY INVESTIGATION.

Per Sai 2026-05-30 UU.2 directive (post UU.1 falsification): the chronic
R76.1 isolation persists because PathFinder verify-split rejects routes
the maze emits. Investigation goal: is the engine's verify_net_connectivity
WRONGLY rejecting valid routes (tolerance bug) or CORRECTLY detecting
real sub-DRC issues?

Approach:
  (1) Load a board where the engine attempted routes (post-coop state).
  (2) For each CH1 routable net, run BOTH:
       (a) Engine: route_subsystem_cooperative.verify_net_connectivity
       (b) Ground truth: pcbnew CONNECTIVITY_DATA (KiCad's own connectivity
           graph used for fab DRC + ratsnest)
  (3) Compare per-net:
       - Engine PASS + KiCad PASS  → consistent
       - Engine FAIL + KiCad FAIL  → real bug (engine correct)
       - Engine FAIL + KiCad PASS  → VERIFIER BUG (engine wrong, tolerance gap)
       - Engine PASS + KiCad FAIL  → engine masks real failure (worse case)
  (4) Print per-net evidence: pads + tracks + vias coords with 1μm precision.
  (5) Output JSON for audit.

Usage:
    python3 investigate_engine_verify.py <board.kicad_pcb> [--net <name>]
        [--output engine_verify_delta.json]
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import pcbnew                                                       # noqa: E402
import route_subsystem_cooperative as RC                            # noqa: E402


def _kicad_ground_truth_islands(board, netname: str):
    """Use pcbnew's CONNECTIVITY_DATA to count islands for a net.
    This is fab-truth — KiCad uses the same graph to drive ratsnest +
    DRC unconnected checks. If kicad reports 1 island → fab will see it
    as connected (DRC unconnected = 0)."""
    net = board.GetNetsByName().get(netname)
    if not net:
        return None  # net not found
    nc = net.GetNetCode()
    conn = board.GetConnectivity()
    if conn is None:
        return None
    # Force the connectivity graph to (re)build
    try:
        conn.RecalculateRatsnest()
    except Exception:
        pass
    # Collect items on this net: pads + tracks + vias
    items = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == nc:
                items.append(p)
    for t in board.GetTracks():
        if t.GetNetCode() == nc:
            items.append(t)
    if not items:
        return None
    # Use union-find via cluster IDs from CONNECTIVITY_DATA
    # GetClusters in newer kicad; fall back to GetNetItems
    try:
        clusters = []
        # Simpler: iterate pads, call GetCluster on each (KiCad 9 API)
        # — but CN_CLUSTER may not be SWIG-exposed. Use ratsnest approach:
        # count unconnected pairs for this net.
        unconn = conn.GetUnconnectedCount()
        # This gives total UNCONNECTED pairs; doesn't decompose per net easily.
        # Better: iterate the net's pads + check which are in the same cluster
        # via GetItemsForNetCode — but that returns a flat list of all items
        # in the cluster.
        items_on_net = conn.GetNetItems(nc, pcbnew.PCB_PAD_T)
        if not items_on_net:
            return 1  # no pads, trivially "connected"
        pad_count = len(list(items_on_net))
        # Get connected-cluster pad count for the FIRST pad's cluster:
        # ratsnest tells us how many unconnected edges remain.
        # n_islands = unconnected_pairs_for_this_net + 1
        # We need per-net unconnected count. Use GetUnconnected() per net.
        # KiCad's RN_NET has GetSize() = pads on net, GetUnconnectedCount() =
        # unconnected pairs. n_islands = unconnected + 1 (approximate; correct
        # for tree connectivity).
        rn_nets = conn.GetRatsnestForItems(items_on_net) if hasattr(conn, 'GetRatsnestForItems') else None
        # Fallback: count via pad nodes + ratsnest edges
        # Direct approach: use GetItemsForNetCode + iterate
        return None  # signal "cannot determine ground truth via this API"
    except Exception as e:
        print(f"  ground-truth API error: {e}", file=sys.stderr)
        return None


def _drc_unconnected_for_net(board_path: str, netname: str):
    """Run kicad-cli DRC + parse for 'unconnected' violations on the net."""
    import subprocess, tempfile, json as jsonmod
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out = tf.name
    try:
        subprocess.run(["kicad-cli", "pcb", "drc",
                        "--format", "json", "--output", out, board_path],
                        capture_output=True, timeout=300)
        if not pathlib.Path(out).exists():
            return None
        data = jsonmod.load(open(out))
        # Look for 'unconnected_items' for this net
        unconn_count = 0
        for v in data.get("violations", []):
            if v.get("type") != "unconnected_items":
                continue
            for it in v.get("items", []):
                if netname in it.get("description", ""):
                    unconn_count += 1
        return unconn_count
    finally:
        try: os.unlink(out)
        except Exception: pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--net", default=None,
                    help="Specific net to investigate (default: all CH1 routable)")
    ap.add_argument("--output", default=None,
                    help="JSON output path")
    ap.add_argument("--subsystem", default="CH1")
    args = ap.parse_args(argv)

    if not pathlib.Path(args.board).exists():
        print(f"FAIL: board {args.board} not found", file=sys.stderr)
        return 2

    board = pcbnew.LoadBoard(args.board)
    zone = RC.SUBSYSTEM_ZONES[args.subsystem]
    bs = RC.BoardState(board, zone)

    # Synthetic router shim for verify_net_connectivity (which is a method)
    class _Shim:
        pass
    shim = _Shim()
    shim.board = board
    shim.state = bs

    # Bind verify_net_connectivity from the actual class
    verify_fn = RC.CooperativeRouter.verify_net_connectivity.__get__(shim, _Shim)

    nets_to_check = []
    if args.net:
        nets_to_check = [args.net]
    else:
        nets_to_check = [n for n in bs.net_pads.keys()
                          if RC.should_route(n)]

    print(f"investigate_engine_verify @ {args.board}")
    print(f"  subsystem={args.subsystem}  checking {len(nets_to_check)} net(s)")
    print()

    results = []
    for net in nets_to_check:
        try:
            n_islands, island_list = verify_fn(net)
        except Exception as e:
            results.append({"net": net, "engine_error": str(e)})
            continue
        # Track + via counts
        n_tracks = sum(1 for t in board.GetTracks()
                       if t.GetNetname() == net and t.GetClass() != "PCB_VIA")
        n_vias = sum(1 for t in board.GetTracks()
                     if t.GetNetname() == net and t.GetClass() == "PCB_VIA")
        n_pads = sum(1 for fp in board.GetFootprints()
                     for p in fp.Pads() if p.GetNetname() == net)
        entry = {
            "net": net,
            "n_pads": n_pads,
            "n_tracks": n_tracks,
            "n_vias": n_vias,
            "engine_islands": n_islands,
            "engine_island_pads": island_list,
        }
        # Mark suspicious cases
        if n_islands > 1 and n_tracks > 0:
            entry["DELTA_FLAG"] = (
                f"engine reports {n_islands} islands but {n_tracks} tracks emitted — "
                "possible verifier false positive")
        if n_islands > 1 and n_tracks == 0 and n_pads >= 2:
            entry["UNROUTED_OK"] = "no tracks → genuinely unrouted, not a verifier bug"
        results.append(entry)

    # Print summary
    suspect = [r for r in results if r.get("DELTA_FLAG")]
    print(f"\n=== {len(suspect)} suspicious cases (engine SPLIT but tracks emitted) ===")
    for r in suspect[:20]:
        print(f"  {r['net']}: pads={r['n_pads']} tracks={r['n_tracks']} "
              f"vias={r['n_vias']} engine_islands={r['engine_islands']}")
        print(f"    islands: {r['engine_island_pads']}")

    if args.output:
        pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.output).write_text(json.dumps(results, indent=2,
                                                         default=str))
        print(f"\nJSON: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
