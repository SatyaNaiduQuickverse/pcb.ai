#!/usr/bin/env python3
"""
geometry_primitives.py — routing-engine geometry primitive library (DESIGN STAGE)

Per `docs/ROUTING_METHODOLOGY.md` §5b (geometry policy, Sai-locked 2026-05-28)
and `docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` §3 step 1.

A small set of pure geometry constructors. The router (Phase C detailed fill)
AND hand touch-ups both call these — one set of validated primitives, no ad-hoc
track math. Each primitive that has analytic ground truth (length / clearance /
radius) is implemented + self-tested here; primitives whose ground truth needs
the KiCad board model (teardrop neck ratio, via annular, native PCB_ARC emit)
are documented stub signatures that raise NotImplementedError until the engine
is built — this is a DESIGN-stage deliverable for review, not the engine.

GEOMETRY POLICY (the WHY, per §5b):
  - DEFAULT octilinear (45°): simplest manufacturable; never creates acute
    (<90°) interior angles by construction. The 90°-corner-radiates belief is a
    myth below GHz (Howard Johnson HSDD) — our nets are sub-MHz/low-MHz.
  - GATE: reject any interior angle <90° (acid-trap / over-etch DFM class,
    IPC-2221 §6.1).
  - TEARDROPS at every pad/via junction (IPC stress + current-crowding relief).
  - LOCAL 45° chamfer/fillet on HIGH-CURRENT corners ONLY, sim-driven (current
    crowding on ~100A motor traces; Brooks "PCB Currents").
  - NO global chamfer/curve rule (rejected — bloat for no benefit).

Pure functions; no pcbnew import at module level so the self-test runs anywhere
(Pi-resident). The KiCad emitter (PCB_TRACK + native PCB_ARC) is specified as a
stub; it will import pcbnew when implemented.

Run self-test:  python3 geometry_primitives.py
"""

import math
from dataclasses import dataclass
from typing import Tuple

EPS = 1e-9
Point = Tuple[float, float]


# ─── helpers ───────────────────────────────────────────────────────────────

def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _norm(v: Point) -> float:
    return math.hypot(v[0], v[1])


def _interior_angle_deg(a: Point, vertex: Point, b: Point) -> float:
    """Interior angle (degrees) at `vertex` between rays vertex→a and vertex→b."""
    va, vb = _sub(a, vertex), _sub(b, vertex)
    na, nb = _norm(va), _norm(vb)
    if na < EPS or nb < EPS:
        return 180.0
    cos = max(-1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / (na * nb)))
    return math.degrees(math.acos(cos))


# ─── primitive results ──────────────────────────────────────────────────────

@dataclass
class Segment:
    """A straight track segment of width w from p1 to p2."""
    p1: Point
    p2: Point
    w: float

    @property
    def length(self) -> float:
        return _norm(_sub(self.p2, self.p1))


@dataclass
class Arc:
    """A circular arc through p1,p2 with radius r (center on the left of p1→p2)."""
    p1: Point
    p2: Point
    r: float
    center: Point


# ─── implemented primitives (analytic ground truth) ─────────────────────────

def straight(p1: Point, p2: Point, w: float) -> Segment:
    """One straight segment. Ground truth: length = ‖p2 − p1‖."""
    if w <= 0:
        raise ValueError("width must be > 0")
    return Segment(p1, p2, w)


def bend_45(corner: Point, setback: float, leg_in: Point, leg_out: Point):
    """Replace a 90° corner with two 45° segments (octilinear bend).

    `corner` is the vertex; `leg_in`/`leg_out` are the far endpoints of the two
    legs meeting at the corner (used only for direction). `setback` is the
    distance back from the corner along each leg where the 45° chamfer starts.

    Returns (Segment in→chamfer_start, Segment chamfer_start→chamfer_end,
    Segment chamfer_end→out)-style chamfer points. Ground truth: the inserted
    diagonal makes two 135° interior angles (never acute), each chamfer leg has
    the requested setback along its incoming direction.
    """
    if setback <= 0:
        raise ValueError("setback must be > 0")
    din = _sub(leg_in, corner)
    dout = _sub(leg_out, corner)
    nin, nout = _norm(din), _norm(dout)
    if nin < EPS or nout < EPS:
        raise ValueError("degenerate leg")
    uin = (din[0] / nin, din[1] / nin)
    uout = (dout[0] / nout, dout[1] / nout)
    a = (corner[0] + uin[0] * setback, corner[1] + uin[1] * setback)
    b = (corner[0] + uout[0] * setback, corner[1] + uout[1] * setback)
    return a, b  # chamfer endpoints; diagonal a→b replaces the sharp corner


def chamfer(corner: Point, leg_in: Point, leg_out: Point, cut: float):
    """45° corner cut (alias of bend_45 with a single named cut length).
    Ground truth: cut leg length == `cut` on each side."""
    return bend_45(corner, cut, leg_in, leg_out)


def fillet(corner: Point, leg_in: Point, leg_out: Point, r: float) -> Arc:
    """Rounded corner of radius r tangent to both legs.

    Ground truth: the arc is tangent to both legs ⇒ distance from the corner to
    each tangent point = r / tan(theta/2) where theta is the interior angle, and
    the arc center is at distance r from each leg.
    """
    if r <= 0:
        raise ValueError("radius must be > 0")
    theta = math.radians(_interior_angle_deg(leg_in, corner, leg_out))
    if theta < EPS or abs(theta - math.pi) < EPS:
        raise ValueError("cannot fillet a straight or degenerate corner")
    tan_dist = r / math.tan(theta / 2.0)
    din = _sub(leg_in, corner)
    dout = _sub(leg_out, corner)
    uin = (din[0] / _norm(din), din[1] / _norm(din))
    uout = (dout[0] / _norm(dout), dout[1] / _norm(dout))
    t_in = (corner[0] + uin[0] * tan_dist, corner[1] + uin[1] * tan_dist)
    t_out = (corner[0] + uout[0] * tan_dist, corner[1] + uout[1] * tan_dist)
    # bisector direction (toward center)
    bis = (uin[0] + uout[0], uin[1] + uout[1])
    nb = _norm(bis)
    if nb < EPS:
        raise ValueError("degenerate bisector")
    ubis = (bis[0] / nb, bis[1] / nb)
    center_dist = r / math.sin(theta / 2.0)
    center = (corner[0] + ubis[0] * center_dist, corner[1] + ubis[1] * center_dist)
    return Arc(t_in, t_out, r, center)


def taper(p1: Point, p2: Point, w1: float, w2: float):
    """Width transition from w1 to w2 along p1→p2.
    Ground truth: monotone width; edges never form an acute angle with the
    centerline (the half-angle of a linear taper is < 90° for any positive
    length). Returns (length, edge_half_angle_deg)."""
    if w1 <= 0 or w2 <= 0:
        raise ValueError("widths must be > 0")
    L = _norm(_sub(p2, p1))
    if L < EPS:
        raise ValueError("zero-length taper")
    half_angle = math.degrees(math.atan2(abs(w2 - w1) / 2.0, L))
    return L, half_angle


def arc(p1: Point, p2: Point, r: float) -> Arc:
    """Circular arc through p1,p2 with radius r (center to the left of p1→p2).
    Ground truth: |center−p1| = |center−p2| = r, and r ≥ chord/2."""
    if r <= 0:
        raise ValueError("radius must be > 0")
    chord = _norm(_sub(p2, p1))
    if r < chord / 2.0 - EPS:
        raise ValueError(f"radius {r} too small for chord {chord} (min {chord/2})")
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    # perpendicular distance from midpoint to center
    h = math.sqrt(max(0.0, r * r - (chord / 2.0) ** 2))
    d = _sub(p2, p1)
    # left-hand perpendicular unit vector
    perp = (-d[1] / chord, d[0] / chord)
    center = (mid[0] + perp[0] * h, mid[1] + perp[1] * h)
    return Arc(p1, p2, r, center)


# ─── stub primitives (need the board model / engine — DESIGN stage) ─────────

def arc_tangent(*args, **kwargs):
    """Arc tangent to two segments. STUB — implement with the engine.
    Ground truth at impl time: tangency residual ≈ 0 at both contact points."""
    raise NotImplementedError("arc_tangent: design-stage stub (ROUTING_ENGINE_DESIGN_2026-05-28 §3 step 1)")


def teardrop(*args, **kwargs):
    """Teardrop fillet at a pad/via neck (IPC stress + current-crowding relief).
    STUB — needs pad geometry from the board. Ground truth at impl time:
    neck width ≥ trace width; IPC teardrop length/width ratio honored."""
    raise NotImplementedError("teardrop: design-stage stub (needs board pad model)")


def via_transition(*args, **kwargs):
    """Track → via landing transition. STUB — needs via stack from BOARD_INVARIANTS.
    Ground truth at impl time: annular ring + clearance preserved (FoS §5c)."""
    raise NotImplementedError("via_transition: design-stage stub (needs via stack)")


def emit_to_kicad(*args, **kwargs):
    """Emit primitives as KiCad PCB_TRACK + native PCB_ARC. STUB — imports pcbnew
    when implemented. Ground truth at impl time: round-trip length match
    (emitted geometry length == primitive length within grid tolerance)."""
    raise NotImplementedError("emit_to_kicad: design-stage stub (imports pcbnew at impl)")


# ─── self-test (analytic ground truth) ──────────────────────────────────────

def _self_test():
    # straight: length
    s = straight((0.0, 0.0), (3.0, 4.0), 0.25)
    assert abs(s.length - 5.0) < 1e-9, f"straight length {s.length} != 5"

    # bend_45: replacing a 90° corner yields two 135° interior angles (>90°, no acute)
    # corner at origin, legs along +x and +y; setback 1.0
    a, b = bend_45((0.0, 0.0), 1.0, leg_in=(5.0, 0.0), leg_out=(0.0, 5.0))
    assert abs(a[0] - 1.0) < 1e-9 and abs(a[1]) < 1e-9, f"bend leg-in point {a}"
    assert abs(b[0]) < 1e-9 and abs(b[1] - 1.0) < 1e-9, f"bend leg-out point {b}"
    # interior angle at `a` between (leg_in far point) and `b` must be 135°
    ang_a = _interior_angle_deg((5.0, 0.0), a, b)
    assert abs(ang_a - 135.0) < 1e-6, f"bend_45 interior angle {ang_a} != 135 (acute would be <90)"

    # fillet: tangent radius == r; center at distance r from each leg
    arc_obj = fillet((0.0, 0.0), leg_in=(5.0, 0.0), leg_out=(0.0, 5.0), r=2.0)
    # for a 90° corner, tangent distance = r/tan(45) = r
    assert abs(_norm(_sub(arc_obj.p1, (2.0, 0.0)))) < 1e-9, f"fillet tangent-in {arc_obj.p1}"
    assert abs(_norm(_sub(arc_obj.p2, (0.0, 2.0)))) < 1e-9, f"fillet tangent-out {arc_obj.p2}"
    # center equidistant (=r along the perpendicular) from each leg → on the leg x=r and y=r lines
    assert abs(arc_obj.center[0] - 2.0) < 1e-9 and abs(arc_obj.center[1] - 2.0) < 1e-9, \
        f"fillet center {arc_obj.center} != (r, r)"

    # arc: center equidistant r from both endpoints; r >= chord/2 enforced
    a2 = arc((0.0, 0.0), (4.0, 0.0), 3.0)
    assert abs(_norm(_sub(a2.center, a2.p1)) - 3.0) < 1e-9, "arc center-p1 != r"
    assert abs(_norm(_sub(a2.center, a2.p2)) - 3.0) < 1e-9, "arc center-p2 != r"
    try:
        arc((0.0, 0.0), (4.0, 0.0), 1.0)  # chord 4, r 1 < 2 → must raise
        raise AssertionError("arc should reject r < chord/2")
    except ValueError:
        pass

    # taper: monotone, edge half-angle < 90°
    L, ha = taper((0.0, 0.0), (10.0, 0.0), 0.25, 2.5)
    assert abs(L - 10.0) < 1e-9 and 0.0 < ha < 90.0, f"taper L={L} half-angle={ha}"

    # chamfer alias
    ca, cb = chamfer((0.0, 0.0), (5.0, 0.0), (0.0, 5.0), cut=1.5)
    assert abs(_norm(_sub(ca, (0.0, 0.0))) - 1.5) < 1e-9, "chamfer cut leg != 1.5"

    # stubs raise NotImplementedError (design-stage, by design)
    for stub in (arc_tangent, teardrop, via_transition, emit_to_kicad):
        try:
            stub()
            raise AssertionError(f"{stub.__name__} should be a NotImplementedError stub")
        except NotImplementedError:
            pass

    print("✅ geometry_primitives self-test PASS")
    print(f"   straight (3,4): length {s.length:.3f}mm")
    print(f"   bend_45 90°→ two 135° interior angles (no acute): {ang_a:.1f}°")
    print(f"   fillet r=2 at 90° corner: center {arc_obj.center}, tangent dist = r")
    print(f"   arc through (0,0)-(4,0) r=3: center {a2.center}")
    print(f"   taper 0.25→2.5 over 10mm: edge half-angle {ha:.2f}°")
    print("   stubs (arc_tangent/teardrop/via_transition/emit_to_kicad): NotImplementedError as designed")


if __name__ == "__main__":
    _self_test()
