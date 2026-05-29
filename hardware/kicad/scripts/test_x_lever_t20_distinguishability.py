#!/usr/bin/env python3
"""X-lever T20 K3-distinguishability regression test (CH1 30/30 close-out).

W (PR #254) fixed the multi-mech planner correctness (per-pad obstacle
model + canonical layer-name lookup + HDI escape-corridor relaxation
0.5mm) — drove the 30/30 close-out. But W's HDI relaxation made the
prior T20 geometry (F.Cu blockers at 0.4mm from HDI pin POINT)
admissible: the LIAR could detour on F.Cu via the relaxed corridor
and route as ONE mechanism instead of the canonical K3 chain. The
T20 fixture stopped distinguishing K3 (multi-mech) from a single-mech
solver.

The X-lever redo (2026-05-29) PUSHES every F.Cu blocker edge to
0.6mm from the HDI pin POINT — JUST OUTSIDE W's 0.5mm relaxation
radius — so the planner's `_in_hdi_relaxation` does NOT admit them.
The canonical K3 chain ['blind_F_In2', 'through'] becomes the ONLY
admissible path again, and the through-only / blind-only / microvia-
only / multi-class-missing-canonical liars ALL return None.

This test locks the distinguishability gate. It runs the planner on
the T20 fixture in seven configurations and asserts:

  (1) Multi-mech (full HDI catalogue) ROUTES with chain
      ['blind_F_In2', 'through'].
  (2) Through-only LIAR returns None.
  (3) Blind_F_In2-only LIAR returns None.
  (4) Microvia_F_In1-only LIAR returns None.
  (5) Microvia_B_In8-only LIAR returns None.
  (6) Multi-class {through, microvia_B_In8} (missing blind_F_In2)
      returns None.
  (7) Multi-class {blind_F_In2, microvia_B_In8} (missing through)
      returns None.

If any of these regress, the K3-distinguishability gate is broken
and T20 no longer catches the bug class W fixed.

The fixture geometry, planner, and via-class catalogue are
INDEPENDENT axes — this test exercises all three together, so a
silent regression in any one of them flips a `LIAR returns None`
assertion. The test is the audit-coverage net for the W → X
hand-off.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from routing_engine import fixtures as F
from routing_engine import multi_mech_planner as MMP


def _build_runner():
    fx = F.get_fixture("T20")
    sp = fx.pin(fx.nets[0].pin_ids[0])
    ep = fx.pin(fx.nets[0].pin_ids[1])
    obs = tuple(
        MMP.Obstacle(x_min=o.x_min, y_min=o.y_min, x_max=o.x_max,
                     y_max=o.y_max, kind=o.kind, plane=o.plane,
                     layers=o.layers)
        for o in fx.obstacles)
    region = (-2.0, -2.0, 13.0, 13.0)
    start_pin = MMP.Pin(point=(sp.x_mm, sp.y_mm), layer=sp.layer,
                        is_hdi_whitelisted=True)
    end_pin = MMP.Pin(point=(ep.x_mm, ep.y_mm), layer=ep.layer)
    sig_layers = tuple(L.name for L in fx.signal_layers())

    def run(classes):
        return MMP.plan_multi_mech_route(
            start=start_pin, end=end_pin, region_bbox=region,
            obstacles=obs, allowed_layers=sig_layers,
            allowed_via_classes=classes,
            width_mm=0.20, clearance_fos_mm=0.20,
            grid_pitch_mm=0.5,
        )

    return fx, run


def _assert(cond, msg):
    print(f"  {'ok' if cond else 'XX'} {msg}")
    return cond


def main():
    print("=" * 72)
    print("X-lever T20 K3-distinguishability regression self-test")
    print("=" * 72)
    fx, run = _build_runner()
    ok = True

    # (1) Multi-mech full catalogue MUST route with canonical chain.
    plan = run(("blind_F_In2", "through",
                "microvia_F_In1", "microvia_B_In8"))
    if plan is None:
        ok &= _assert(
            False,
            "(1) multi-mech full catalogue ROUTES with canonical "
            "['blind_F_In2', 'through'] chain — got NONE (planner "
            "regression breaks K3)")
    else:
        ok &= _assert(
            plan.n_vias == 2 and plan.n_mechanisms == 2
            and "blind_F_In2" in plan.via_chain
            and "through" in plan.via_chain,
            f"(1) multi-mech full catalogue ROUTES with canonical "
            f"chain: got via_chain={plan.via_chain}, n_vias="
            f"{plan.n_vias}, n_mechanisms={plan.n_mechanisms}")

    # (2)-(5) SINGLE-MECH-ONLY LIARS — all MUST return None.
    for label, classes, why in [
        ("(L1) blind_F_In2-only", ("blind_F_In2",),
         "lands on In2.Cu, cannot reach B.Cu"),
        ("(L2) through-only", ("through",),
         "REFUSED at HDI start + all adjacent F.Cu cells blocked "
         "by NON-relaxation-eligible blockers (X-lever 0.6mm offset "
         "survives W's 0.5mm relaxation)"),
        ("(L3) microvia_F_In1-only", ("microvia_F_In1",),
         "In1 is plane, NOT in allowed_layers"),
        ("(L4) microvia_B_In8-only", ("microvia_B_In8",),
         "wrong layer pair at F.Cu start"),
    ]:
        liar = run(classes)
        ok &= _assert(liar is None,
                      f"{label} LIAR returns None — {why}")

    # (6)-(7) MULTI-CLASS LIARS missing canonical mechanism — None.
    for label, classes, why in [
        ("(L6) {through, microvia_B_In8} (no blind_F_In2)",
         ("through", "microvia_B_In8"),
         "cannot escape HDI start without blind_F_In2"),
        ("(L7) {blind_F_In2, microvia_B_In8} (no through)",
         ("blind_F_In2", "microvia_B_In8"),
         "blind lands on In2; no In2→B transition without through"),
    ]:
        liar = run(classes)
        ok &= _assert(liar is None,
                      f"{label} LIAR returns None — {why}")

    print("=" * 72)
    if ok:
        print("ALL X-LEVER T20 DISTINGUISHABILITY TESTS PASS")
        return 0
    else:
        print("X-LEVER T20 DISTINGUISHABILITY: FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
