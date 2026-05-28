#!/usr/bin/env python3
"""_adversarial_single_mech_liar.py — the SINGLE-MECH-ONLY LIAR adversary
that PROVES T20 (CH1 30/30 (K3) lockfile) is bug-distinguishing.

The K3 capability is multi-mechanism path planning — chaining 2+ DIFFERENT
via classes along a single route to bridge cross-stack nets (canonical
SWDIO_CH1 F.Cu->B.Cu). A solver that admits ONLY ONE via-class mechanism
per route attempt (the legacy single-mech maze) FAILS T20 because:

  blind_F_In2 only — lands on In2.Cu, cannot reach B.Cu (no In2->B class).
  through only      — REFUSED at the HDI start cell (cooperative router's
                       via_class_for_span; v6/v7 shorts lesson) AND the
                       F.Cu blocking field prevents a F.Cu detour to a
                       non-HDI cell.

Either way: NO-PATH on T20. This adversary REPRODUCES that behaviour by
calling `multi_mech_planner.plan_multi_mech_route` with the
allowed_via_classes restricted to ONE class at a time, then reports the
single-mech verdict back to the run_suite harness.

Expected harness verdict on T20: FAIL (the liar emits INFEASIBLE/NO-PATH
on T20, the run_suite expects ROUTABLE — the multi-mech chain). Other
cases the liar punts to the multi_mech planner so the test isolates
single-mech vs multi-mech behaviour on the K3 fixture.
"""
from __future__ import annotations


try:
    from . import multi_mech_planner as MMP
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import multi_mech_planner as MMP  # type: ignore


def solve(problem) -> dict:
    """Single-mech-only liar: tries each allowed via class in isolation;
    reports NO-PATH if none route. For non-T20 cases, returns NOT-MY-CASE
    so the harness scores only the K3 lockfile."""
    if problem.name != "T20":
        return {"verdict": "NOT-MY-CASE",
                "rationale": ("single-mech-only liar targets T20 only; "
                              f"got {problem.name}")}
    net = problem.nets[0]
    p_start = problem.pin(net.pin_ids[0])
    p_end = problem.pin(net.pin_ids[1])
    obs = tuple(
        MMP.Obstacle(x_min=o.x_min, y_min=o.y_min, x_max=o.x_max,
                     y_max=o.y_max, kind=o.kind, plane=o.plane,
                     layers=o.layers)
        for o in problem.obstacles)
    xs = [p_start.x_mm, p_end.x_mm] + [o.x_min for o in obs] + [o.x_max for o in obs]
    ys = [p_start.y_mm, p_end.y_mm] + [o.y_min for o in obs] + [o.y_max for o in obs]
    region = (min(xs) - 2.0, min(ys) - 2.0, max(xs) + 2.0, max(ys) + 2.0)
    sig_layers = tuple(L.name for L in problem.signal_layers())
    start_pin = MMP.Pin(point=(p_start.x_mm, p_start.y_mm),
                        layer=p_start.layer, is_hdi_whitelisted=True)
    end_pin = MMP.Pin(point=(p_end.x_mm, p_end.y_mm), layer=p_end.layer)

    # Try ONE via class at a time — the single-mech-only restriction.
    attempted = []
    for cls in ("blind_F_In2", "through"):
        plan = MMP.plan_multi_mech_route(
            start=start_pin, end=end_pin, region_bbox=region,
            obstacles=obs, allowed_layers=sig_layers,
            allowed_via_classes=(cls,),
            width_mm=0.20, clearance_fos_mm=0.20, grid_pitch_mm=0.5,
        )
        attempted.append({"class": cls, "result": plan})
        if plan is not None:
            # Liar accidentally found a route with one class — report it.
            # This is the bug-witness for a regression that admits same-class
            # repeats as if they were multi-mech.
            return {
                "verdict": "ROUTABLE",
                "routed": 1,
                "n_vias": plan.n_vias,
                "n_mechanisms": 1,    # single-mech LIAR — not the K3 chain
                "via_chain": list(plan.via_chain),
                "rationale": (f"single-mech-only LIAR found a route using "
                              f"ONLY {cls} — bug-witness emitted as if it "
                              "were K3 capability (it is NOT — single "
                              "mechanism repeated; the K3 chain requires "
                              "≥2 DISTINCT classes)."),
            }
    # All single-mech attempts failed — the honest single-mech-only verdict.
    return {
        "verdict": "INFEASIBLE",
        "routed": 0,
        "n_vias": 0,
        "n_mechanisms": 0,
        "via_chain": [],
        "reason": "NO-PATH",
        "rationale": ("single-mech-only LIAR: blind_F_In2 alone reaches "
                      "In2.Cu but no In2.Cu->B.Cu transition exists in the "
                      "single-class space; through alone is REFUSED at the "
                      "HDI start cell AND the F.Cu blocking field prevents "
                      "a F.Cu detour. The K3 multi-mech chain is the only "
                      "feasible route — this liar cannot route T20."),
    }
