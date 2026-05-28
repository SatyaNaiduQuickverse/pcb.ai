"""_adversarial_k1_disabled_liar.py — DELIBERATELY BUGGY solver (T18 lever K1
adjacent-HDI halo over-rejection pattern).

This module IS the adversary T18 is designed to reject: a solver that retains
the pre-K1 halo behaviour (centerline-to-centerline check uses
pad_a/2 + pad_b/2 + 2×CLEARANCE_MM) and therefore REFUSES two HDI vias at
0.5mm QFN pitch even though their pad-edge clearance (= 0.20mm) exactly meets
the §5c FoS target.

This liar:
  * Returns INFEASIBLE on T18 with routed_nets = 0 (BOTH vias refused)
  * Reports k1_pad_edge.decision = "refuse (pre-K1 halo)"

The T18 special-checks gate (run_suite._special_checks_T18_wrapped) FAILS
this liar on routed_nets != 2.

NOT shipped/registered; invoked only manually:
  PYTHONPATH=hardware/kicad/scripts \\
    python3 hardware/kicad/scripts/routing_engine/run_suite.py \\
    --solver routing_engine._adversarial_k1_disabled_liar:solve \\
    --cases T18
"""
from __future__ import annotations


def solve(problem):
    """The buggy solver. Refuses both HDI vias at adjacent QFN pitch using
    the pre-K1 halo-overlap rule (the very bug K1 fixes). Reports the lie
    honestly so the audit catches it via the routed_nets metric."""
    hdi_slots = [v for v in problem.via_slots
                 if getattr(v, "hdi_only", False)]
    pin_xy = {p.id: (p.x_mm, p.y_mm) for p in problem.pins}
    at_pin = []
    for v in hdi_slots:
        for pid, (px, py) in pin_xy.items():
            if abs(v.x_mm - px) < 1e-6 and abs(v.y_mm - py) < 1e-6:
                at_pin.append(v); break
    a = at_pin[0] if at_pin else None
    b = at_pin[1] if len(at_pin) >= 2 else None
    return {
        # The LIE: claim INFEASIBLE on a case K1 makes ROUTABLE.
        "verdict": "INFEASIBLE",
        "routed_nets": 0,            # BOTH refused under pre-K1 halo
        # Pad-edge / FoS metrics surfaced honestly so the audit can match
        # them against the witness — but routed_nets = 0 is the giveaway.
        "pad_edge_clearance_mm": 0.20,    # the AT-target value K1 would accept
        "fos_target_mm": 0.20,
        "k1_pad_edge": {
            "adjacent_slots": [s.id for s in (a, b) if s is not None],
            "distance_mm": 0.50,
            "pad_edge_clearance_mm": 0.20,
            "fos_target_mm": 0.20,
            "decision": "refuse (pre-K1 halo over-rejection)",
            "rule": ("pre-K1 halo: pad_half_a + pad_half_b + "
                      "2×CLEARANCE_MM ≈ 0.70mm > pitch 0.50mm — refuse"),
        },
        "rationale": ("ADVERSARIAL K1-disabled pattern (T18 LIAR): "
                       "retains the pre-K1 halo-overlap rule and refuses "
                       "both vias even though pad-edge = 0.20mm = FoS "
                       "target (the case K1 fixes)."),
    }
