"""_adversarial_rip_everything_liar.py — DELIBERATELY BUGGY solver (T17 lever-J
rip-everything pattern).

This module IS the adversary T17 is designed to reject: a solver that "succeeds"
on the targeted-ripup case by RIPPING EVERY FOREIGN NET (not the minimum
conflict subset) and then routing the blocked net alone — DROPPING the ripped
foreigners without re-routing them. The frozen-routes-preserved invariant
(carried forward from R34 `--no-rip-routed` + lever J atomic-commit discipline)
catches this: a committed targeted ripup MUST re-route every ripped net.

This liar:
  * Returns ROUTABLE on T17 with routed_nets = 1 (the blocked net alone)
  * Reports targeted_ripup.frozen_routes_preserved = False (the lie)
  * Reports targeted_ripup.outcome = "rip-everything (foreigners dropped)"

The T17 special-checks gate (run_suite._special_checks_T17_wrapped) FAILS
this liar on (a) routed_nets != 2 metric mismatch AND (b) the
frozen_routes_preserved == False rejection.

NOT shipped/registered; invoked only manually:
  python3 routing_engine/run_suite.py \
    --solver routing_engine._adversarial_rip_everything_liar:solve \
    --cases T17
"""
from __future__ import annotations


def solve(problem):
    """The buggy solver. Routes the blocked net alone, drops every foreigner.
    Reports the lie honestly so the audit catches it."""
    # Find the lane-overlap pair (same logic as the honest solver but inverted
    # outcome).
    nets = [n for n in problem.nets if len(n.pin_ids) == 2]
    lanes = {}
    for n in nets:
        pa = problem.pin(n.pin_ids[0])
        pb = problem.pin(n.pin_ids[1])
        if abs(pa.y_mm - pb.y_mm) > 1e-6:
            continue
        y = round(pa.y_mm, 6)
        xa, xb = sorted([pa.x_mm, pb.x_mm])
        lanes.setdefault(y, []).append((n.net_id, xa, xb))
    blocked_id = None
    foreigner_id = None
    for y, items in lanes.items():
        if len(items) < 2:
            continue
        items_sorted = sorted(items, key=lambda it: -(it[2] - it[1]))
        a = items_sorted[0]
        b = items_sorted[1]
        if min(a[2], b[2]) - max(a[1], b[1]) >= 1.0:
            blocked_id = a[0]
            foreigner_id = b[0]
            break
    return {
        "verdict": "ROUTABLE",
        # The LIE: claim 1 routed (blocked alone) but tell the truth in the
        # provenance block — the harness uses the metric AND the provenance
        # to catch us.
        "routed_nets": 1,
        "conflict_set_size": 1,
        "cascade_depth": 1,
        "shorts_delta": 0,
        "targeted_ripup": {
            "blocked_net": blocked_id,
            "conflict_set": [foreigner_id] if foreigner_id else [],
            "cascade_depth": 1,
            "shorts_delta": 0,
            "frozen_routes_preserved": False,   # THE LIE we cannot hide
            "outcome": "rip-everything (foreigners dropped without re-routing)",
            "rerouted": {},
        },
        "rationale": "ADVERSARIAL rip-everything pattern (T17 LIAR)",
    }
