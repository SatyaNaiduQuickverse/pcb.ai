#!/usr/bin/env python3
"""Live-load test: CH1 30/30 lever (Y) JOINT K3 multi-mech rescue on
the worker's POST-W canonical board (/tmp/post_route2.kicad_pcb).

Loads the canonical post-W board (commit 509e6c0, branch
phase4v3-stage1-ch1-on-10L, sims/routing_provenance/27of30_post_W/).
The board has 24 nets already routed + 5 RESIDUAL unrouted:
  PWM_INHB_CH1, PWM_INLA_CH1, GLB_CH1, KILL_RAIL_N_CH1, SWDIO_CH1.

Worker's sequential K3 run on this board (lever W): rescues 2/5
(PWM_INHB + SWDIO). The OTHER 3 fail because each preceding success
exhausts the corridor the next one wanted (net-swap occupancy
oscillation).

This script:
  1. Loads the canonical board into pcbnew.
  2. Constructs a synthetic CooperativeRouter shell (no run; we only
     need self.zone, self.board, self.subsystem, self.grid_pitch,
     self.via_in_pad_allowed, self.state.net_pads, self.committed,
     self.log — the minimal contract the joint-K3 method consumes).
  3. Calls _try_multi_mech_fallback_joint(['PWM_INHB_CH1',
     'PWM_INLA_CH1', 'GLB_CH1', 'KILL_RAIL_N_CH1', 'SWDIO_CH1']).
  4. Reports per-net verdicts + total rescued.

THIS DOES NOT WRITE A NEW CANONICAL BOARD. The output is a JSON
provenance report at /tmp/y_joint_canonical_outcome.json + a log
at /tmp/y_joint_canonical.log. The board mutations are in-memory
ONLY (we never SaveBoard).

Run: python3 live_load_y_joint_k3.py
"""
from __future__ import annotations
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "routing_engine"))

import pcbnew

import route_subsystem_cooperative as RC
from routing_engine import phase_c as PC

# ── Constants matching the worker's diag setup.
CANONICAL_BOARD = "/tmp/post_route2.kicad_pcb"
SUBSYSTEM = "CH1"
GRID_PITCH = 0.1
RESIDUALS = [
    "PWM_INHB_CH1",
    "PWM_INLA_CH1",
    "GLB_CH1",
    "KILL_RAIL_N_CH1",
    "SWDIO_CH1",
]
OUT_JSON = "/tmp/y_joint_canonical_outcome.json"
OUT_LOG = "/tmp/y_joint_canonical.log"


def collect_net_pads_from_board(board, target_nets):
    """Build self.state.net_pads from the live board.
    Returns dict[net_name -> list of (ref, padname, x_mm, y_mm,
    frozenset(layers), sx_mm, sy_mm)].
    """
    out = {nn: [] for nn in target_nets}
    target_set = set(target_nets)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            netname = p.GetNetname()
            if netname not in target_set:
                continue
            pos = p.GetPosition()
            x_mm = RC.iu_to_mm(pos.x)
            y_mm = RC.iu_to_mm(pos.y)
            size = p.GetSize()
            sx_mm = RC.iu_to_mm(size.x)
            sy_mm = RC.iu_to_mm(size.y)
            # Layer set (canonical names).
            layers = set()
            lset = p.GetLayerSet()
            for cand in ("F.Cu", "B.Cu", "In2.Cu", "In4.Cu", "In6.Cu",
                         "In8.Cu", "In1.Cu", "In3.Cu", "In5.Cu", "In7.Cu"):
                try:
                    lid = board.GetLayerID(cand)
                    if lset.Contains(lid):
                        layers.add(cand)
                except Exception:
                    continue
            out[netname].append((ref, p.GetPadName(), x_mm, y_mm,
                                 frozenset(layers), sx_mm, sy_mm))
    return out


class _State:
    """Minimal CooperativeRouter state stub for joint-K3 entry."""
    def __init__(self, net_pads):
        self.net_pads = net_pads


class _MinimalRouter:
    """Minimal CooperativeRouter shell — exposes only the attributes
    `_try_multi_mech_fallback_joint` consumes. Reuses the actual method
    bound from the real CooperativeRouter class.
    """
    def __init__(self, board, subsystem, net_pads):
        self.board = board
        self.subsystem = subsystem
        self.zone = RC.SUBSYSTEM_ZONES[subsystem]
        self.grid_pitch = GRID_PITCH
        self.via_in_pad_allowed = True
        self.state = _State(net_pads)
        self.committed = {}
        self._log_lines = []

    def log(self, msg):
        self._log_lines.append(msg)
        print(msg)

    # Bind the real router's K3 + helpers.
    _try_multi_mech_fallback_joint = RC.CooperativeRouter.__dict__[
        "_try_multi_mech_fallback_joint"]
    _try_multi_mech_fallback = RC.CooperativeRouter.__dict__[
        "_try_multi_mech_fallback"]
    _rollback_added_since = RC.CooperativeRouter.__dict__[
        "_rollback_added_since"]
    _stable_item_key = RC.CooperativeRouter.__dict__[
        "_stable_item_key"]


def main():
    t0 = time.time()
    if not os.path.exists(CANONICAL_BOARD):
        print(f"ERROR: canonical board {CANONICAL_BOARD} not found.")
        return 2

    print(f"=== CH1 30/30 lever (Y) JOINT K3 — live load on canonical ===")
    print(f"board: {CANONICAL_BOARD}")
    board = pcbnew.LoadBoard(CANONICAL_BOARD)
    n_fp = sum(1 for _ in board.GetFootprints())
    n_tracks = sum(1 for _ in board.GetTracks())
    print(f"loaded: {n_fp} footprints, {n_tracks} tracks "
          f"({time.time()-t0:.1f}s)")

    net_pads = collect_net_pads_from_board(board, RESIDUALS)
    for nn, pads in net_pads.items():
        print(f"  {nn}: {len(pads)} pads on board "
              f"({[(r, p) for (r, p, *_) in pads]})")

    # In-zone filter — what the joint K3 will actually attempt.
    zone = RC.SUBSYSTEM_ZONES[SUBSYSTEM]
    xmin, ymin, xmax, ymax = zone
    for nn, pads in net_pads.items():
        in_zone = [p for p in pads if xmin <= p[2] <= xmax
                                    and ymin <= p[3] <= ymax]
        print(f"  {nn}: {len(in_zone)} pads inside zone")

    router = _MinimalRouter(board, SUBSYSTEM, net_pads)
    print(f"\n=== running JOINT K3 ===")
    t = time.time()
    try:
        verdicts = router._try_multi_mech_fallback_joint(RESIDUALS)
    except Exception as exc:
        print(f"FAILED with {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        # Persist partial log for diagnosis.
        with open(OUT_LOG, "w") as f:
            f.write("\n".join(router._log_lines) + "\n")
            f.write(f"\nERROR: {type(exc).__name__}: {exc}\n")
            f.write(traceback.format_exc())
        return 2
    elapsed = time.time() - t

    n_routed = sum(1 for v in verdicts.values() if v == "routed")
    n_total = len(RESIDUALS)
    print(f"\n=== RESULT ===")
    print(f"  joint K3 routed: {n_routed}/{n_total}")
    for nn in RESIDUALS:
        v = verdicts.get(nn, "missing")
        print(f"    {nn}: {v}")
    print(f"  elapsed: {elapsed:.1f}s")
    print(f"  total: {time.time()-t0:.1f}s")

    # Persist outcome.
    payload = {
        "board": CANONICAL_BOARD,
        "subsystem": SUBSYSTEM,
        "residuals": RESIDUALS,
        "verdicts": verdicts,
        "n_routed": n_routed,
        "n_total": n_total,
        "elapsed_sec": elapsed,
        "lever": "Y_joint_k3",
        "comparison_to_sequential_post_W": {
            "sequential_W_routed": 2,
            "sequential_W_rescued": ["PWM_INHB_CH1", "SWDIO_CH1"],
            "sequential_W_failed": ["PWM_INLA_CH1", "GLB_CH1",
                                    "KILL_RAIL_N_CH1"],
            "joint_Y_routed": n_routed,
            "joint_Y_rescued": [nn for nn, v in verdicts.items()
                                if v == "routed"],
            "joint_Y_failed": [nn for nn, v in verdicts.items()
                               if v != "routed"],
        },
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  wrote {OUT_JSON}")
    with open(OUT_LOG, "w") as f:
        f.write("\n".join(router._log_lines) + "\n")
    print(f"  wrote {OUT_LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
