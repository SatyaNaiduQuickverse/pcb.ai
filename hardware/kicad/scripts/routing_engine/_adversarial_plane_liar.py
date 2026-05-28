"""_adversarial_plane_liar.py — DELIBERATELY BUGGY solver (the OQ-020 v1 bug).

This module IS the adversary T12 is designed to reject: a solver that counts
ALL hdi_only via slots as escape supply NAIVELY, ignoring whether the via
class' target_layer is a PLANE (= not a signal escape) or a SIGNAL layer.

Used by the PR validation to demonstrate that an honest layer-aware engine
PASSES T12 while this liar FAILS T12 — proves the case enforces the layer-
awareness constraint, not just states it. NOT shipped/registered; invoked
only manually by `run_suite --solver routing_engine._adversarial_plane_liar:solve`.
"""
from __future__ import annotations

try:
    from . import phase_a as PA
    from . import fixtures as F
except ImportError:
    import phase_a as PA  # type: ignore
    import fixtures as F  # type: ignore


def _liar_side_supply(fx):
    """The BUGGY engine-v1 counting: counts EVERY hdi_only slot as supply,
    regardless of whether its target_layer is a PLANE. This is the exact bug
    that mis-counted F.Cu↔In1 microvias (target=In1=GND PLANE) as signal
    escape supply on the CH1 board — the OQ-020 root cause."""
    sides = {}
    for vs in fx.via_slots:
        sides.setdefault(vs.ic_side, {"std": 0, "hdi": 0})
        if vs.hdi_only:
            sides[vs.ic_side]["hdi"] += 1
        else:
            sides[vs.ic_side]["std"] += 1
    return sides


def solve(problem, demand_by_side=None, consumed_by_side=None,
          crossing_override=None):
    """Run phase_a but with side_supply MONKEY-PATCHED to the buggy naive
    counting. Returns the same dict shape — only the supply counting differs."""
    orig = PA.side_supply
    PA.side_supply = _liar_side_supply
    try:
        return PA.solve(problem, demand_by_side=demand_by_side,
                        consumed_by_side=consumed_by_side,
                        crossing_override=crossing_override)
    finally:
        PA.side_supply = orig
