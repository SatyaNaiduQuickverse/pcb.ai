"""_adversarial_skip_retry_liar.py — DELIBERATELY BUGGY solver (T19 lever K2
MST-completion skip-retry pattern).

This module IS the adversary T19 is designed to reject: a solver that retains
the pre-K2 forward-only single-pass behaviour and rolls back the WHOLE TREE
on the first leaf failure. For a 4-pad net with 3 routable + 1 blocked edge,
the liar reports 0 routed instead of 4.

This liar:
  * Returns INFEASIBLE on T19 with routed_pads = 0 (whole-tree rollback)
  * Reports k2_mst.decision = "rollback_whole_tree (pre-K2)"

The T19 special-checks gate (run_suite._special_checks_T19_wrapped) FAILS
this liar on routed_pads != 4.

NOT shipped/registered; invoked only manually:
  PYTHONPATH=hardware/kicad/scripts \\
    python3 hardware/kicad/scripts/routing_engine/run_suite.py \\
    --solver routing_engine._adversarial_skip_retry_liar:solve \\
    --cases T19
"""
from __future__ import annotations


def solve(problem):
    """The buggy solver. Identifies the multi-pad net + body blocker; rolls
    back the WHOLE tree on first leaf failure (the very bug K2 fixes).
    Reports the lie honestly so the audit catches it via routed_pads."""
    multi = [n for n in problem.nets if len(n.pin_ids) >= 3]
    netname = multi[0].net_id if multi else "?"
    n_pads = len(multi[0].pin_ids) if multi else 0
    n_edges = max(0, n_pads - 1)
    failed_pairs = []
    # Heuristic: one leaf pair is body-blocked (the K2 trigger). We don't
    # need to find which — the lie is that we ROLL BACK ALL edges.
    if multi and len(multi[0].pin_ids) >= 2:
        failed_pairs = [[multi[0].pin_ids[0], multi[0].pin_ids[-1]]]
    return {
        # The LIE: claim INFEASIBLE on a case K2 makes ROUTABLE.
        "verdict": "INFEASIBLE",
        "routed_nets": 0,
        "routed_pads": 0,                # whole-tree rollback
        "n_failed_leaves_final": 1,
        "retry_cap": 1,                  # the pre-K2 single-pass cap
        "k2_mst": {
            "n_pads": n_pads,
            "n_mst_edges": n_edges,
            "retries_per_leaf": {"0": 1},   # only ever 1 attempt (no retry)
            "retry_cap": 1,
            "failed_pad_pairs": failed_pairs,
            "routed_paths": {},
            "decision": ("rollback_whole_tree (pre-K2 forward-only "
                          "single-pass)"),
        },
        "rationale": ("ADVERSARIAL skip-retry pattern (T19 LIAR): "
                       "retains the pre-K2 single-pass behaviour and "
                       "rolls back the whole MST tree on first leaf "
                       "failure (the case K2 fixes). Reports 0 routed "
                       f"instead of {n_pads}."),
    }
