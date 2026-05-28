#!/usr/bin/env python3
"""
geometry_primitives.py — routing-engine geometry primitive library (DESIGN STAGE)

Per `docs/ROUTING_METHODOLOGY.md` §5b (geometry policy, Sai-locked 2026-05-28)
and `docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` §3 step 1.

A small set of pure geometry constructors. The router (Phase C detailed fill)
AND hand touch-ups both call these — one set of validated primitives, no ad-hoc
track math. Every primitive is implemented + self-tested against analytic ground
truth (length / clearance / radius / tangency residual):
  straight, bend_45, chamfer, fillet, arc, taper  — base octilinear set
  arc_tangent  — arc tangent to two segments (rounded corner; acute-angle gated)
  teardrop     — two-arc IPC teardrop fillet at a trace→pad/via junction
  via_transition — track→via→track layer change with FoS annular + HDI flag
  emit_to_kicad  — primitives → portable KiCad track/arc/via descriptors
                   (+ live PCB_TRACK/PCB_ARC/PCB_VIA when a board + pcbnew exist)

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

Pure functions; NO pcbnew import at module level so the self-test runs anywhere
(Pi-resident master env). The KiCad emitter (`emit_to_kicad`) lazy-imports
pcbnew INSIDE the function and only when a live board is passed — the
descriptor-generation path is fully pcbnew-free and is the analytic ground truth.

Run self-test:  python3 geometry_primitives.py
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

EPS = 1e-9
Point = Tuple[float, float]

# ─── fab + FoS constants (ROUTING_METHODOLOGY.md §5c + BOARD_INVARIANTS.md) ───
# These are the floors the geometry primitives enforce. Per §5c the design
# target is NEVER the raw limit — clearances/rings sit ABOVE the fab min with a
# registration/headroom margin. Sourced from BOARD_INVARIANTS.md (10L stackup,
# HDI via-in-pad whitelist) so the primitives inherit the locked fab numbers.
FAB_ANNULAR_MIN_STD = 0.10   # mm — JLC std annular ring (BOARD_INVARIANTS line 153)
FAB_ANNULAR_MIN_HDI = 0.075  # mm — HDI laser-microvia annular (BOARD_INVARIANTS line 142)
FAB_DRILL_MIN_STD = 0.30     # mm — JLC std mechanical drill (BOARD_INVARIANTS line 153)
FAB_DRILL_MIN_HDI = 0.10     # mm — HDI laser drill (BOARD_INVARIANTS line 140)
# Registration headroom multiplier on the annular ring (§5c "above fab min,
# never at it"; ring at fab min risks breakout on layer-registration error).
ANNULAR_FOS = 1.20

# 10L copper stack, top→bottom (BOARD_INVARIANTS.md line 13). Index 0 = F.Cu.
# Used to decide whether a via spans an ADJACENT pair (single laser microvia
# territory) or multiple layers (full mechanical through/buried stack).
LAYER_STACK = [
    "F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu",
    "In5.Cu", "In6.Cu", "In7.Cu", "In8.Cu", "B.Cu",
]
# Adjacent pairs that BOARD_INVARIANTS calls HDI-microvia territory (§5c +
# HDI whitelist): the outer-skin laser-drilled pairs F.Cu↔In1 and B.Cu↔In8.
HDI_ADJACENT_PAIRS = {("F.Cu", "In1.Cu"), ("In8.Cu", "B.Cu")}


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


def _unit(v: Point) -> Point:
    n = _norm(v)
    if n < EPS:
        raise ValueError("cannot normalize a zero-length vector")
    return (v[0] / n, v[1] / n)


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _scale(v: Point, s: float) -> Point:
    return (v[0] * s, v[1] * s)


def _dist(a: Point, b: Point) -> float:
    return _norm(_sub(a, b))


def _perp(v: Point) -> Point:
    """Left-hand perpendicular (90° CCW)."""
    return (-v[1], v[0])


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

    @property
    def midpoint(self) -> Point:
        """Point on the arc midway (by angle) between p1 and p2 — the point a
        native KiCad PCB_ARC stores as its (mid) control point."""
        a1 = math.atan2(self.p1[1] - self.center[1], self.p1[0] - self.center[0])
        a2 = math.atan2(self.p2[1] - self.center[1], self.p2[0] - self.center[0])
        # take the short sweep between the two endpoints
        da = a2 - a1
        while da > math.pi:
            da -= 2.0 * math.pi
        while da < -math.pi:
            da += 2.0 * math.pi
        am = a1 + da / 2.0
        return (self.center[0] + self.r * math.cos(am),
                self.center[1] + self.r * math.sin(am))


@dataclass
class Teardrop:
    """Teardrop fillet at a trace→pad/via junction (IPC-7351C reliability).

    Two mirror arcs (`arc_left`, `arc_right`) tangent to the trace edges on the
    neck side and tangent to the pad circle on the pad side, sweeping the trace
    width out to the pad. `neck_width` is the narrowest width (= trace width by
    construction at the neck) and `pad_tangent_*` are the contact points on the
    pad circle (each at distance pad_radius from pad_center)."""
    pad_center: Point
    pad_radius: float
    trace_end: Point        # where the straight trace meets the teardrop neck
    trace_width: float
    neck_width: float
    arc_left: Arc
    arc_right: Arc
    pad_tangent_left: Point
    pad_tangent_right: Point
    ratio: float            # IPC teardrop length/pad-diameter ratio used


@dataclass
class Via:
    """A track→via→track layer transition descriptor (ROUTING_METHODOLOGY §5c).

    `annular_ring` = (pad − drill)/2. `is_hdi` flags an outer-skin laser
    microvia (adjacent-layer pair per BOARD_INVARIANTS) vs a full-stack
    mechanical via. `fos_ok` is True iff the ring clears its fab floor WITH the
    registration headroom multiplier (never sized at the raw fab min, §5c)."""
    point: Point
    from_layer: str
    to_layer: str
    drill: float
    pad: float
    net: object
    annular_ring: float
    is_hdi: bool
    layer_span: int          # number of copper layers crossed (1 = adjacent)
    fos_ok: bool
    fos_floor: float         # the annular floor this via was checked against
    warnings: List[str] = field(default_factory=list)


@dataclass
class KiCadRecord:
    """Structured, pcbnew-free descriptor of one emitted board object.

    kind ∈ {"track", "arc", "via"}. For tracks `mid` is None; for arcs `mid` is
    the native-arc control point on the arc; for vias `start`==`end`==via point
    and `layer` is "from→to". This is the portable hand-off the emitter returns
    even when pcbnew is absent (master env)."""
    kind: str
    start: Point
    mid: Optional[Point]
    end: Point
    width: float
    layer: str
    net: object


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


# ─── pad/via + emitter primitives (analytic ground truth + lazy pcbnew) ─────

def arc_tangent(seg_in: Segment, seg_out: Segment, radius: float) -> Arc:
    """Rounded corner: a circular arc of `radius` tangent to both an incoming
    and an outgoing segment that share a corner vertex.

    The two segments must meet at a common endpoint (the corner). The arc is
    constructed so its two tangent points lie ON the segments and the arc is
    tangent (perpendicular-radius) to each — i.e. the corner is rounded with no
    reflex/acute artifact.

    Geometry (the documented closed form):
      θ          = interior angle between the two segments at the corner
      tan_dist   = radius / tan(θ/2)   ← distance from corner to each tangent pt
      center_dist= radius / sin(θ/2)   ← distance from corner to the arc center
                                          along the interior-angle bisector
    The center sits on the bisector at center_dist; both tangent points are at
    distance radius from the center by construction.

    FoS / policy: rounding an obtuse/right corner can NEVER introduce an acute
    interior angle (the arc only removes material at the vertex). We additionally
    GATE θ ≥ 90° (the §5b acute-angle reject) so the primitive is never used to
    "smooth" an already-illegal acute corner — that must be re-routed, not
    filleted. Returns an Arc(tangent_in, tangent_out, radius, center).
    """
    if radius <= 0:
        raise ValueError("radius must be > 0")
    # find the shared corner vertex (the endpoint the two segments have in common)
    corner = None
    far_in = far_out = None
    for ci in (seg_in.p1, seg_in.p2):
        for co in (seg_out.p1, seg_out.p2):
            if _dist(ci, co) < 1e-6:
                corner = ci
                far_in = seg_in.p2 if ci == seg_in.p1 else seg_in.p1
                far_out = seg_out.p2 if co == seg_out.p1 else seg_out.p1
    if corner is None:
        raise ValueError("seg_in and seg_out must share a corner endpoint")

    theta_deg = _interior_angle_deg(far_in, corner, far_out)
    theta = math.radians(theta_deg)
    if theta < EPS or abs(theta - math.pi) < EPS:
        raise ValueError("cannot round a straight or degenerate corner")
    if theta_deg < 90.0 - 1e-6:
        # §5b acute-angle GATE: never fillet an illegal acute corner.
        raise ValueError(
            f"interior angle {theta_deg:.2f}° is acute (<90°); §5b acid-trap "
            "reject — re-route the corner, do not arc-smooth it")

    uin = _unit(_sub(far_in, corner))
    uout = _unit(_sub(far_out, corner))
    tan_dist = radius / math.tan(theta / 2.0)
    if tan_dist > seg_in.length + 1e-9 or tan_dist > seg_out.length + 1e-9:
        raise ValueError(
            f"radius {radius} too large: tangent setback {tan_dist:.3f}mm "
            "exceeds an adjoining segment length")
    t_in = _add(corner, _scale(uin, tan_dist))
    t_out = _add(corner, _scale(uout, tan_dist))
    bis = _add(uin, uout)
    if _norm(bis) < EPS:
        raise ValueError("degenerate bisector (180° corner)")
    ubis = _unit(bis)
    center_dist = radius / math.sin(theta / 2.0)
    center = _add(corner, _scale(ubis, center_dist))
    return Arc(t_in, t_out, radius, center)


def teardrop(pad_center: Point, pad_radius: float, trace_end: Point,
             trace_width: float, ratio: float = 1.0) -> Teardrop:
    """Teardrop fillet at a trace→pad (or trace→via) junction.

    The classic two-arc teardrop: two mirror arcs spread from the trace edges at
    the neck out to tangency with the pad circle, so current crowding and
    drill-breakout / thermal-cycle stress at the pad neck are relieved (IPC-7351C
    land-pattern reliability + IPC-2221 thermal cycling; ROUTING_METHODOLOGY §5b).

    `ratio` is the IPC-style teardrop length ratio = (teardrop length along the
    trace axis) / (pad diameter). IPC-7351C / common CAM practice uses ~1.0
    (length ≈ pad diameter) with a default 1.0; values 0.5–1.0 are typical. The
    default 1.0 is the conservative (longer, gentler) teardrop.

    FoS / policy (§5b + §5c):
      • neck width ≥ trace width — the teardrop only WIDENS toward the pad; the
        narrowest point (the neck where the straight trace enters) is exactly the
        trace width, never below it (so the teardrop never necks the conductor).
      • pad-side tangency: each arc touches the pad circle (distance
        pad_center→tangent-point == pad_radius), so there is no acute sliver
        where copper meets the pad.
      • monotone widening trace→pad.

    Construction: let the trace axis run from `trace_end` toward `pad_center`
    (unit u). The neck half-width is trace_width/2 on each side (perp p). Each
    side's arc starts at the neck edge point (trace_end ± p·tw/2) and is tangent
    to the pad circle. We size each arc's radius R_td so that the arc is tangent
    to the pad circle of radius pad_radius centered at pad_center. For the
    symmetric teardrop the arc center lies on the line through the neck edge
    point parallel to the trace axis, offset so the arc both passes through the
    neck edge and is internally tangent to the pad circle. Solving tangency:
        R_td = (d² − pad_radius² ... )   (closed form below)
    where d is along-axis neck-to-pad distance. Returns a Teardrop.
    """
    if pad_radius <= 0:
        raise ValueError("pad_radius must be > 0")
    if trace_width <= 0:
        raise ValueError("trace_width must be > 0")
    if not (0.0 < ratio <= 1.5):
        raise ValueError("ratio out of sane IPC range (0,1.5]")
    half = trace_width / 2.0
    axis_len = _dist(trace_end, pad_center)
    if axis_len < pad_radius + EPS:
        raise ValueError("trace_end is inside the pad — nothing to teardrop")
    if half >= pad_radius - EPS:
        raise ValueError("trace half-width ≥ pad radius — pad too small to teardrop")
    u = _unit(_sub(pad_center, trace_end))   # trace axis, neck → pad
    p = _perp(u)                              # left-hand perpendicular

    # IPC-7351C length ratio: teardrop length (neck→pad-edge along the axis) =
    # ratio × pad diameter. ratio<1.0 SHORTENS the teardrop by moving the
    # EFFECTIVE neck closer to the pad — the tangency solve below then runs at
    # that effective neck so the arcs stay EXACTLY tangent to the pad for ANY
    # ratio (no broken geometry). The neck never moves inside the pad nor past
    # the supplied trace_end (clamped). ratio=1.0 (default) = the conservative
    # full-length teardrop whose length ≈ pad diameter (common CAM default).
    desired_len = ratio * (2.0 * pad_radius)               # neck→pad-edge length
    neck_to_pad = pad_radius + min(desired_len, axis_len - pad_radius)
    neck_to_pad = min(neck_to_pad, axis_len)               # never beyond real trace_end
    eff_neck = _add(pad_center, _scale(u, -neck_to_pad))   # effective neck point

    # Each side's arc passes through the neck edge point E (on the trace edge,
    # offset ±half off-axis from the effective neck) and is tangent to BOTH the
    # trace edge line at E and to the pad circle on the SAME side as E (so the
    # two arcs form the convex teardrop flare, never crossing the axis).
    #   • tangent to the trace edge at E ⇒ the radius C→E is perpendicular to the
    #     trace edge ⇒ the arc center C lies on the perpendicular through E, on
    #     the far side of E from the axis: C = E + (side)·p·R_td.
    #   • external tangency to the pad circle ⇒ |C − pad_center| = pad_radius + R_td,
    #     which places the contact point on the same (E) side of the axis.
    # Let `along` = E→pad along-axis distance and `lateral` = E off-axis offset
    # (= half). Then:
    #   |C − pad_center|² = along² + (lateral + R_td)²  =  (pad_radius + R_td)²
    #   along² + lateral² + 2·lateral·R_td = pad_radius² + 2·pad_radius·R_td
    #   along² + lateral² − pad_radius² = 2·R_td·(pad_radius − lateral)
    along = neck_to_pad
    lateral = half
    denom = 2.0 * (pad_radius - lateral)      # > 0 (half < pad_radius enforced above)
    R_td = (along * along + lateral * lateral - pad_radius * pad_radius) / denom
    if R_td <= 0:
        raise ValueError("degenerate teardrop geometry (pad/trace proportions)")

    def _build_side(sign: float) -> Tuple[Arc, Point]:
        ps = _scale(p, sign)
        E = _add(eff_neck, _scale(ps, half))          # neck edge point (E side)
        C = _add(E, _scale(ps, R_td))                 # arc center, AWAY from axis
        # pad-side tangent point = where the line pad_center→C crosses pad circle
        v = _unit(_sub(C, pad_center))
        T = _add(pad_center, _scale(v, pad_radius))
        return Arc(E, T, R_td, C), T

    arc_l, tang_l = _build_side(+1.0)
    arc_r, tang_r = _build_side(-1.0)

    # Verify monotone widening: width at the neck = trace_width; width near the
    # pad = lateral span between the two pad-tangent points ≥ trace_width.
    pad_span = _dist(tang_l, tang_r)
    neck_width = trace_width
    if pad_span < neck_width - 1e-9:
        raise ValueError("teardrop narrows toward pad — geometry inverted")

    return Teardrop(
        pad_center=pad_center, pad_radius=pad_radius, trace_end=trace_end,
        trace_width=trace_width, neck_width=neck_width,
        arc_left=arc_l, arc_right=arc_r,
        pad_tangent_left=tang_l, pad_tangent_right=tang_r, ratio=ratio,
    )


def via_transition(point: Point, from_layer: str, to_layer: str,
                   via_drill: float, via_pad: float, net: object) -> Via:
    """Geometry for a track→via→track layer change.

    Returns a Via descriptor carrying the annular ring, an HDI-microvia vs
    full-stack classification, and a FoS verdict. The entry/exit stub geometry
    is the via landing point itself (`point`); callers append the track segments
    on `from_layer`/`to_layer` that terminate at `point` (the emitter stitches
    track→via→track).

    FoS / policy (§5c "Annular ring & drill", BOARD_INVARIANTS via spec):
      • annular_ring = (via_pad − via_drill)/2 must be ABOVE the fab min — not
        at it. We check against floor = fab_min × ANNULAR_FOS (registration
        headroom) and set `fos_ok` / warn if below. A ring at the raw fab min
        risks breakout on layer-registration error.
      • HDI vs full-stack: a via spanning an ADJACENT outer-skin pair
        (F.Cu↔In1 or B.Cu↔In8 per BOARD_INVARIANTS) is a laser-drilled microvia
        and is checked against the relaxed HDI floor (0.075mm); anything else is
        a full mechanical via checked against the std floor (0.10mm). HDI is
        flagged distinctly (`is_hdi=True`) so the whitelist gate can enforce it.
    """
    if via_drill <= 0 or via_pad <= 0:
        raise ValueError("via_drill and via_pad must be > 0")
    if via_pad <= via_drill:
        raise ValueError("via_pad must exceed via_drill (annular ring > 0)")
    if from_layer not in LAYER_STACK or to_layer not in LAYER_STACK:
        raise ValueError(f"layers must be in the 10L stack {LAYER_STACK}")
    if from_layer == to_layer:
        raise ValueError("from_layer and to_layer must differ")

    i_from = LAYER_STACK.index(from_layer)
    i_to = LAYER_STACK.index(to_layer)
    layer_span = abs(i_to - i_from)  # # of copper layers crossed
    pair = (from_layer, to_layer) if i_from < i_to else (to_layer, from_layer)
    is_hdi = (layer_span == 1) and (pair in HDI_ADJACENT_PAIRS)

    annular = (via_pad - via_drill) / 2.0
    fab_floor = FAB_ANNULAR_MIN_HDI if is_hdi else FAB_ANNULAR_MIN_STD
    fos_floor = fab_floor * ANNULAR_FOS

    warnings: List[str] = []
    fos_ok = annular >= fos_floor - 1e-9
    if not fos_ok:
        warnings.append(
            f"annular ring {annular:.4f}mm < FoS floor {fos_floor:.4f}mm "
            f"(fab min {fab_floor}mm × {ANNULAR_FOS} headroom) — "
            "sized at/below fab min, §5c violation; enlarge pad or shrink drill")
    if is_hdi:
        warnings.append(
            f"HDI laser microvia ({from_layer}↔{to_layer} adjacent pair) — "
            "only allowed on the BOARD_INVARIANTS J18/J19 via-in-pad whitelist")
    elif layer_span == 1:
        # adjacent but NOT an outer-skin pair → buried microvia would need a
        # non-standard process; note it (still treated as full-stack std floor).
        warnings.append(
            f"adjacent inner pair {from_layer}↔{to_layer} is NOT an HDI "
            "outer-skin pair — treated as a standard (mechanical) via")

    return Via(
        point=point, from_layer=from_layer, to_layer=to_layer,
        drill=via_drill, pad=via_pad, net=net,
        annular_ring=annular, is_hdi=is_hdi, layer_span=layer_span,
        fos_ok=fos_ok, fos_floor=fos_floor, warnings=warnings,
    )


def emit_to_kicad(primitives, board=None, default_layer: str = "F.Cu",
                  default_net: object = 0) -> List[KiCadRecord]:
    """Convert primitive outputs to KiCad track/arc/via records.

    PORTABILITY: pcbnew is lazy-imported INSIDE this function. On the master env
    (no pcbnew) the descriptor path runs fully; if a live `board` is passed AND
    pcbnew imports, the matching PCB_TRACK / PCB_ARC / PCB_VIA objects are also
    created and added to the board.

    Always returns a list of `KiCadRecord` (portable descriptors). Each record:
        kind ∈ {"track","arc","via"}
        start, mid (arc control point or None), end, width, layer, net
    For an `Arc`, `mid` is the native-arc control point ON the arc (what
    pcbnew's PCB_ARC stores). For a `Via`, start==end==via point and `layer`
    is "from→to".

    Supported primitive inputs: Segment, Arc, Via, Teardrop (emitted as its two
    arcs), or a 2-tuple (primitive, {"layer":..,"net":..,"width":..}) override.
    """
    records: List[KiCadRecord] = []

    def _emit_one(prim, layer, net, width_override):
        if isinstance(prim, Segment):
            records.append(KiCadRecord(
                "track", prim.p1, None, prim.p2,
                width_override if width_override is not None else prim.w,
                layer, net))
        elif isinstance(prim, Arc):
            w = width_override if width_override is not None else default_width
            records.append(KiCadRecord(
                "arc", prim.p1, prim.midpoint, prim.p2, w, layer, net))
        elif isinstance(prim, Via):
            records.append(KiCadRecord(
                "via", prim.point, None, prim.point, prim.pad,
                f"{prim.from_layer}→{prim.to_layer}", prim.net))
        elif isinstance(prim, Teardrop):
            w = width_override if width_override is not None else prim.trace_width
            for a in (prim.arc_left, prim.arc_right):
                records.append(KiCadRecord(
                    "arc", a.p1, a.midpoint, a.p2, w, layer, net))
        else:
            raise TypeError(f"cannot emit primitive of type {type(prim).__name__}")

    default_width = 0.25  # mm fallback when an Arc carries no width

    for item in primitives:
        layer, net, width_override = default_layer, default_net, None
        prim = item
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict):
            prim, opts = item
            layer = opts.get("layer", default_layer)
            net = opts.get("net", default_net)
            width_override = opts.get("width")
        _emit_one(prim, layer, net, width_override)

    # ── optional live-board path (lazy pcbnew import) ───────────────────────
    if board is not None:
        try:
            import pcbnew  # noqa: F401  (lazy — master env may lack it)
        except Exception as e:  # pragma: no cover - env-dependent
            print(f"   emit_to_kicad: SKIP pcbnew-object path ({e})")
            return records
        _add_pcbnew_objects(records, board, pcbnew)

    return records


def _add_pcbnew_objects(records, board, pcbnew):  # pragma: no cover - needs pcbnew
    """Create PCB_TRACK / PCB_ARC / PCB_VIA from descriptors and add to `board`.
    Separated so the descriptor path is fully testable without pcbnew."""
    def _vp(pt):
        return pcbnew.VECTOR2I(pcbnew.FromMM(pt[0]), pcbnew.FromMM(pt[1]))

    for r in records:
        if r.kind == "track":
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(_vp(r.start)); t.SetEnd(_vp(r.end))
            t.SetWidth(pcbnew.FromMM(r.width))
            t.SetLayer(board.GetLayerID(r.layer))
            if isinstance(r.net, int):
                t.SetNetCode(r.net)
            board.Add(t)
        elif r.kind == "arc":
            a = pcbnew.PCB_ARC(board)
            a.SetStart(_vp(r.start)); a.SetMid(_vp(r.mid)); a.SetEnd(_vp(r.end))
            a.SetWidth(pcbnew.FromMM(r.width))
            a.SetLayer(board.GetLayerID(r.layer))
            if isinstance(r.net, int):
                a.SetNetCode(r.net)
            board.Add(a)
        elif r.kind == "via":
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(_vp(r.start))
            v.SetWidth(pcbnew.FromMM(r.width))
            if isinstance(r.net, int):
                v.SetNetCode(r.net)
            board.Add(v)


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

    # newly-implemented primitives (analytic ground truth, no longer stubs)
    at = _test_arc_tangent()
    td = _test_teardrop()
    vt = _test_via_transition()
    em = _test_emit_to_kicad()

    print("✅ geometry_primitives self-test PASS")
    print(f"   straight (3,4): length {s.length:.3f}mm")
    print(f"   bend_45 90°→ two 135° interior angles (no acute): {ang_a:.1f}°")
    print(f"   fillet r=2 at 90° corner: center {arc_obj.center}, tangent dist = r")
    print(f"   arc through (0,0)-(4,0) r=3: center {a2.center}")
    print(f"   taper 0.25→2.5 over 10mm: edge half-angle {ha:.2f}°")
    print(f"   arc_tangent r=2 at 90° corner: |center→tangent|=r both sides; "
          f"interior {at['theta']:.1f}° ≥90° (no acute)")
    print(f"   teardrop pad r=1, trace w=0.5: neck {td['neck']:.3f}mm ≥ trace "
          f"{td['trace']:.3f}mm; pad-tangent residual {td['resid']:.2e}; "
          f"monotone-widen ✓")
    print(f"   via_transition: std F.Cu→In4 ring {vt['std_ring']:.3f}mm < FoS "
          f"floor {vt['std_floor']:.3f}mm → correctly fos_ok={vt['bad_ok']} "
          f"(§5c: ring at fab-min rejected); HDI F.Cu↔In1 microvia flagged "
          f"(is_hdi={vt['hdi_flag']})")
    print(f"   emit_to_kicad straight→arc_tangent→straight: {em['kinds']} "
          f"endpoints chained ✓, arc-mid on arc (residual {em['mid_resid']:.2e})")


def _test_arc_tangent():
    """arc_tangent: tangent-point distance from center == radius (both sides);
    no acute angle introduced. Ground truth at a 90° corner: tan_dist = r/tan45 = r,
    center on the 45° bisector at r/sin45 = r·√2."""
    r = 2.0
    # corner at origin; in-segment from (5,0)→(0,0), out-segment (0,0)→(0,5)
    seg_in = straight((5.0, 0.0), (0.0, 0.0), 0.3)
    seg_out = straight((0.0, 0.0), (0.0, 5.0), 0.3)
    a = arc_tangent(seg_in, seg_out, r)
    assert abs(_dist(a.center, a.p1) - r) < 1e-9, f"tangent-in dist {_dist(a.center,a.p1)} != r"
    assert abs(_dist(a.center, a.p2) - r) < 1e-9, f"tangent-out dist {_dist(a.center,a.p2)} != r"
    # tangent points at r/tan(45)=r along each segment from corner
    assert abs(_dist(a.p1, (0.0, 0.0)) - r) < 1e-9, "in tangent setback != r"
    assert abs(_dist(a.p2, (0.0, 0.0)) - r) < 1e-9, "out tangent setback != r"
    # center on the +x/+y bisector at r·√2
    assert abs(_dist(a.center, (0.0, 0.0)) - r * math.sqrt(2.0)) < 1e-9, "center dist != r·√2"
    # tangency: radius to each tangent point ⊥ to its segment
    for tp, seg_far in ((a.p1, (5.0, 0.0)), (a.p2, (0.0, 5.0))):
        radial = _sub(tp, a.center)
        along = _sub(seg_far, (0.0, 0.0))
        dot = radial[0] * along[0] + radial[1] * along[1]
        assert abs(dot) < 1e-9, f"radius not ⊥ to segment at {tp} (dot={dot})"
    theta = _interior_angle_deg((5.0, 0.0), (0.0, 0.0), (0.0, 5.0))
    assert theta >= 90.0 - 1e-6, "arc_tangent must not be used on acute corner"
    # acute-corner gate: a 60° corner must be REJECTED, not smoothed
    seg_a = straight((5.0, 0.0), (0.0, 0.0), 0.3)
    seg_b = straight((0.0, 0.0), (math.cos(math.radians(60)) * 5,
                                  math.sin(math.radians(60)) * 5), 0.3)
    try:
        arc_tangent(seg_a, seg_b, 0.5)
        raise AssertionError("arc_tangent must reject an acute (<90°) corner")
    except ValueError:
        pass
    return {"theta": theta}


def _test_teardrop():
    """teardrop: neck width ≥ trace width; arcs tangent to pad circle
    (|pad_center→tangent| == pad_radius both); monotone widening trace→pad."""
    pad_c, pad_r = (0.0, 0.0), 1.0
    trace_w = 0.5
    trace_end = (-3.0, 0.0)   # trace approaches the pad along +x
    t = teardrop(pad_c, pad_r, trace_end, trace_w, ratio=1.0)
    # neck width == trace width (never necks the conductor)
    assert t.neck_width >= trace_w - 1e-9, f"neck {t.neck_width} < trace {trace_w}"
    assert abs(t.neck_width - trace_w) < 1e-9, "neck should equal trace width"
    # pad-side tangency: both pad-tangent points lie exactly on the pad circle
    resid_l = abs(_dist(pad_c, t.pad_tangent_left) - pad_r)
    resid_r = abs(_dist(pad_c, t.pad_tangent_right) - pad_r)
    assert resid_l < 1e-9 and resid_r < 1e-9, f"pad tangency residual {resid_l},{resid_r}"
    # each arc center is at distance R_td from BOTH its neck edge point and (pad_r+R_td)
    # from pad_center → external tangency to the pad circle
    for arc_obj in (t.arc_left, t.arc_right):
        assert abs(_dist(arc_obj.center, arc_obj.p1) - arc_obj.r) < 1e-9, "arc not through neck edge"
        assert abs(_dist(arc_obj.center, pad_c) - (pad_r + arc_obj.r)) < 1e-9, \
            "arc not externally tangent to pad circle"
    # monotone widening: width at neck ≤ span at pad
    pad_span = _dist(t.pad_tangent_left, t.pad_tangent_right)
    assert pad_span >= t.neck_width - 1e-9, f"pad span {pad_span} < neck {t.neck_width}"
    # Sample the envelope half-width along the left arc, neck→pad, and require it
    # to be NON-DECREASING (the teardrop only ever widens). Half-width at a point
    # on the arc = its perpendicular distance from the trace axis line; we walk
    # the arc by sweep angle from its neck-edge endpoint to its pad-tangent point.
    u = _unit(_sub(pad_c, t.trace_end))   # axis direction neck→pad
    arc_obj = t.arc_left
    c, R = arc_obj.center, arc_obj.r
    ang_start = math.atan2(arc_obj.p1[1] - c[1], arc_obj.p1[0] - c[0])
    ang_end = math.atan2(arc_obj.p2[1] - c[1], arc_obj.p2[0] - c[0])
    da = ang_end - ang_start
    while da > math.pi:
        da -= 2 * math.pi
    while da < -math.pi:
        da += 2 * math.pi
    half_widths = []
    for k in range(11):
        ang = ang_start + da * k / 10.0
        pt = (c[0] + R * math.cos(ang), c[1] + R * math.sin(ang))
        # perpendicular distance from axis line through pad_c with direction u
        rel = _sub(pt, pad_c)
        perp_off = abs(rel[0] * u[1] - rel[1] * u[0])   # |cross(rel,u)|
        half_widths.append(perp_off)
    for i in range(1, len(half_widths)):
        assert half_widths[i] >= half_widths[i - 1] - 1e-9, \
            f"non-monotone widening at step {i}: {half_widths}"
    # endpoints: neck half-width == trace half-width; pad-end == pad-tangent offset
    assert abs(half_widths[0] - trace_w / 2.0) < 1e-9, f"neck half-width {half_widths[0]}"
    return {"neck": t.neck_width, "trace": trace_w, "resid": max(resid_l, resid_r)}


def _test_via_transition():
    """via_transition: annular ring ≥ FoS floor; HDI adjacent-pair microvia
    flagged distinctly from full-stack; under-min ring flagged not-ok."""
    net = 7
    # std full-stack via F.Cu→In4 (layer_span 4), pad 0.50 drill 0.30 → ring 0.10
    v_std = via_transition((10.0, 10.0), "F.Cu", "In4.Cu", 0.30, 0.50, net)
    assert abs(v_std.annular_ring - 0.10) < 1e-9, f"std ring {v_std.annular_ring}"
    assert not v_std.is_hdi, "F.Cu→In4 is not adjacent → not HDI"
    assert v_std.layer_span == 4, f"span {v_std.layer_span} != 4"
    # ring 0.10 vs floor 0.10×1.20 = 0.12 → BELOW FoS floor → flagged
    assert not v_std.fos_ok, "std ring 0.10 should fail the 0.12 FoS floor (§5c)"
    assert any("annular" in w for w in v_std.warnings), "missing annular warning"
    # a PROPERLY-sized std via: pad 0.60 drill 0.30 → ring 0.15 ≥ 0.12 floor → ok
    v_ok = via_transition((10.0, 10.0), "F.Cu", "In4.Cu", 0.30, 0.60, net)
    assert v_ok.fos_ok, f"ring {v_ok.annular_ring} should clear floor {v_ok.fos_floor}"
    # HDI outer-skin microvia F.Cu↔In1 (adjacent pair) pad 0.25 drill 0.10 → ring 0.075
    v_hdi = via_transition((4.0, 4.0), "F.Cu", "In1.Cu", 0.10, 0.25, net)
    assert v_hdi.is_hdi, "F.Cu↔In1 adjacent skin pair must flag HDI"
    assert v_hdi.layer_span == 1, "HDI span must be 1"
    assert abs(v_hdi.fos_floor - FAB_ANNULAR_MIN_HDI * ANNULAR_FOS) < 1e-12, "HDI floor wrong"
    assert any("HDI" in w for w in v_hdi.warnings), "HDI not flagged in warnings"
    # B.Cu↔In8 is the other HDI skin pair
    v_hdi2 = via_transition((4.0, 4.0), "In8.Cu", "B.Cu", 0.10, 0.25, net)
    assert v_hdi2.is_hdi, "In8↔B.Cu adjacent skin pair must flag HDI"
    # adjacent INNER pair (In4↔In5) is NOT an HDI skin pair → not HDI
    v_inner = via_transition((4.0, 4.0), "In4.Cu", "In5.Cu", 0.30, 0.60, net)
    assert not v_inner.is_hdi, "inner adjacent pair is not an HDI skin pair"
    return {"std_ring": v_std.annular_ring, "std_floor": v_std.fos_floor,
            "hdi_flag": v_hdi.is_hdi, "bad_ok": v_std.fos_ok}


def _test_emit_to_kicad():
    """emit_to_kicad (descriptor path, no board): a straight→arc_tangent→straight
    path emits track,arc,track with chained endpoints, correct widths/layers, and
    a native-arc midpoint that lies ON the arc. pcbnew-object path SKIPs cleanly."""
    w, layer, net = 0.3, "In2.Cu", 5
    seg_in = straight((5.0, 0.0), (0.0, 0.0), w)
    seg_out = straight((0.0, 0.0), (0.0, 5.0), w)
    a = arc_tangent(seg_in, seg_out, 2.0)
    # build the chained path: track up to arc.p1, the arc, track from arc.p2 onward
    t1 = straight((5.0, 0.0), a.p1, w)
    t2 = straight(a.p2, (0.0, 5.0), w)
    recs = emit_to_kicad(
        [(t1, {"layer": layer, "net": net}),
         (a, {"layer": layer, "net": net, "width": w}),
         (t2, {"layer": layer, "net": net})])
    kinds = [r.kind for r in recs]
    assert kinds == ["track", "arc", "track"], f"kinds {kinds}"
    # endpoint chaining: arc start == prev track end; arc end == next track start
    assert _dist(recs[0].end, recs[1].start) < 1e-9, "arc start != prev track end"
    assert _dist(recs[1].end, recs[2].start) < 1e-9, "arc end != next track start"
    # widths + layers propagate
    for r in recs:
        assert abs(r.width - w) < 1e-9, f"width {r.width} != {w}"
        assert r.layer == layer and r.net == net, "layer/net not propagated"
    # native-arc midpoint lies ON the arc (|center→mid| == r)
    mid = recs[1].mid
    assert mid is not None, "arc record missing native mid point"
    mid_resid = abs(_dist(a.center, mid) - a.r)
    assert mid_resid < 1e-9, f"arc mid not on arc (residual {mid_resid})"
    # via + teardrop also emit
    v = via_transition((0.0, 5.0), "In2.Cu", "In3.Cu", 0.30, 0.60, net)
    td = teardrop((0.0, 7.0), 1.0, (0.0, 5.5), 0.3)
    recs2 = emit_to_kicad([v, td])
    assert recs2[0].kind == "via" and recs2[0].start == recs2[0].end == (0.0, 5.0)
    assert recs2[0].layer == "In2.Cu→In3.Cu", f"via layer {recs2[0].layer}"
    assert [r.kind for r in recs2[1:]] == ["arc", "arc"], "teardrop must emit two arcs"
    # pcbnew-object path. The descriptor path above is the analytic ground truth
    # and ALWAYS runs (pcbnew-free). The live-board path is environment-dependent:
    #   • pcbnew NOT importable (e.g. master Pi) → must SKIP gracefully (print
    #     SKIP, no raise) and still return the descriptors.
    #   • pcbnew importable (worker) → create a real BOARD and emit real
    #     PCB_TRACK/PCB_ARC/PCB_VIA onto it; verify the object count matches.
    try:
        import pcbnew  # noqa: F401
        have_pcbnew = True
    except Exception:
        have_pcbnew = False
    if have_pcbnew:
        board = pcbnew.BOARD()
        path = [(t1, {"layer": "F.Cu", "net": 0}),
                (a, {"layer": "F.Cu", "net": 0, "width": w}),
                (t2, {"layer": "F.Cu", "net": 0})]
        before = len(list(board.GetTracks()))
        emit_to_kicad(path, board=board)
        after = len(list(board.GetTracks()))
        assert after - before == 3, f"expected 3 board tracks, got {after - before}"
        print(f"   emit_to_kicad pcbnew-object path: created {after - before} "
              "board items on a live BOARD (track,arc,track)")
    else:
        # force the SKIP branch with a dummy non-None board; it must NOT raise
        skipped = emit_to_kicad([t1], board=object())
        assert len(skipped) == 1 and skipped[0].kind == "track", \
            "board path must still return descriptors when pcbnew absent"
        print("   emit_to_kicad pcbnew-object path: SKIP (pcbnew not importable)")
    return {"kinds": kinds, "mid_resid": mid_resid}


if __name__ == "__main__":
    _self_test()
