"""_adversarial_skip_cascade_liar.py — DELIBERATELY BUGGY solver (T17 lever-J
skip-cascade-check pattern).

This module IS the adversary T17 + G_J2 are designed to reject: a solver that
"succeeds" on the targeted-ripup case by ALLOWING UNBOUNDED CASCADE DEPTH —
rip foreigners → route N → re-route foreigner X requires its own rip Z →
re-route Z requires its own rip W → ... ad infinitum. R37 caps at depth 2;
this liar reports cascade_depth = 3 (one beyond the cap) to demonstrate the
audit catches the class.

This liar:
  * Returns ROUTABLE on T17 with routed_nets = 2 (the cooperative result)
  * Reports targeted_ripup.cascade_depth = 3 (the violation)
  * Trips T17 special-checks gate cascade_depth check (FAIL)
  * Trips G_J2 audit when synthetic provenance entries are written

NOT shipped/registered; invoked only manually.
"""
from __future__ import annotations


def solve(problem):
    """The buggy solver. Reports cascade_depth=3 — past the R37 cap."""
    nets = [n for n in problem.nets if len(n.pin_ids) == 2]
    blocked_id = nets[0].net_id if nets else "?"
    foreigner_id = nets[1].net_id if len(nets) > 1 else "?"
    return {
        "verdict": "ROUTABLE",
        "routed_nets": 2,
        "conflict_set_size": 1,
        # THE LIE: depth > 2
        "cascade_depth": 3,
        "shorts_delta": 0,
        "targeted_ripup": {
            "blocked_net": blocked_id,
            "conflict_set": [foreigner_id],
            "cascade_depth": 3,             # the violation
            "shorts_delta": 0,
            "frozen_routes_preserved": True,
            "outcome": "committed (with depth-3 cascade — R37 violation)",
            "rerouted": {
                foreigner_id: {
                    "path": "depth-3 cascade",
                    "depth": 3,
                },
            },
        },
        "rationale": "ADVERSARIAL skip-cascade-check (T17 LIAR)",
    }
