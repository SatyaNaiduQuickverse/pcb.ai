#!/usr/bin/env python3
"""maze_router.py — Engine Step 8b-ext (lever b): BOUNDED A* maze router.

PHASE C detailed-fill BACKEND #2 alongside `route_subsystem_cooperative`
(cooperative PathFinder negotiated-congestion router). Different tools for
different geometry, per ROUTING_METHODOLOGY.md §0b ("A* usage — Sai-locked"):

  cooperative router  ->  DENSE FANOUT (J18/J19 escape; many short nets fight
                          for the same scarce via supply; negotiated congestion
                          + rip-up beats greedy)
  maze router (this)  ->  LONG-PATH navigation through obstacle FIELDS (a small
                          number of nets must cross many millimetres past body
                          keep-outs; cooperative thrashes; bounded A* shines)

Both are PHASE C primitives — region-confined, expansion-capped, NEVER global.
Phase B has already certified the region feasible; Phase C realises the path.

WHY THIS EXISTS — the CH1 30/30 lever (b)
------------------------------------------
CH1 Step 8b revealed GLB (J19.10 -> R50.1, B.Cu) is standard-fab routable BUT
needs a ~20 mm cross-board path through ICs + passive bodies. The cooperative
router (v8) crossed foreign copper at -0.13 to -0.17 mm clearance every naive
attempt — its negotiated-congestion model assumes the bottleneck is via slots,
not free-space navigation. A bounded A* maze on a fine signal grid is the right
primitive for long-path navigation. Sai-approved as PHASE C complement.

A* DISCIPLINE (Sai-locked, ROUTING_METHODOLOGY §0b "A* usage")
--------------------------------------------------------------
1. REGION-BOUNDED:  search confined to the caller-supplied region_bbox; cells
                    outside are unreachable (cost = +inf). Global A* BANNED.
2. EXPANSION-CAPPED: hard cap on # of A* expansions; over-budget returns
                    NOT-ROUTABLE-EXPANSION-CAP cleanly (no infinite grind).
                    Caller escalates: widen region, change layer, kick to
                    Phase B re-plan — never thrash.
3. CLEARANCE = HARD: a grid cell whose track polygon (width + clearance_fos)
                    does not clear all obstacles by >= clearance_fos_mm is
                    UNREACHABLE (not cost-penalised). §5c "no cut-to-cut".
4. PLANE-CONTINUITY = HARD: a step that crosses a plane_split obstacle is
                    UNREACHABLE (not cost-penalised). §0b / §9.
5. OCTILINEAR by construction: 8-connected grid (H + V + 45° diagonals);
                    diagonals require both axis-cells passable (acid-trap-free
                    bevel). NEVER creates acute angles.
6. LAYER-AWARE VIA COST: layer changes go through one of allowed_via_classes
                    (microvia / blind / stacked / through). Each via class
                    has its own cost (microvia cheapest, full-stack costliest);
                    only classes whose layer span actually reaches the target
                    are considered. Respects HDI whitelist (per-pin gate).
7. HIGH-CURRENT CORNERS: cost adds the sim_loop.corner_current_crowding_factor
                    penalty (Brooks PCB Currents) for nets carrying current >
                    threshold. NON-binding, just biases A* toward straighter
                    routes on power nets — the binding check stays the §5c FoS.

OUTPUT
------
Route(segments, vias) on SUCCESS; or NotRoutable("EXPANSION-CAP" | "BLOCKED"
| "NO-PATH") on failure — the caller carries the verdict, no heroic re-route.
Routes are octilinear by construction (no acute angle); teardrops are inserted
at pad/via junctions via geometry_primitives.teardrop. Emission to a live
pcbnew BOARD goes through geometry_primitives.emit_to_kicad (lazy pcbnew).

DESIGN STAGE NOTE
-----------------
The grid resolution (default 0.10 mm) is a TRADEOFF: finer = more cells =
more A* expansions; coarser = cells too large to fit through tight pin escapes.
0.10 mm matches the cooperative router's --grid-pitch default and is the
JLC fab-min track pitch ballpark (track 0.10 + clearance 0.0889). Callers
may tune via grid_pitch_mm; the expansion_cap should scale with grid density.

Pure Python + heapq stdlib (the search). pcbnew is lazy-imported ONLY in the
live emit path via geometry_primitives.emit_to_kicad — pure search runs
anywhere (Pi master env).
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

# Reuse the physics proxies (corner crowding for high-current bias) — already on
# the engine path; cheap closed-form (Brooks). NEVER binding, only A* cost bias.
try:                                        # package import (engine internal)
    from . import sim_loop as _sim_loop     # noqa: F401  (kept for parity)
except ImportError:                         # loose-script invocation
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    # parent dir = .../scripts; physics_primitives lives there
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import sim_loop as _sim_loop  # type: ignore

# physics_primitives lives at hardware/kicad/scripts — one level above the
# routing_engine package. Try the canonical import path; fall back for loose.
try:
    import physics_primitives as PHYS  # type: ignore
except ImportError:                                       # pragma: no cover
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import physics_primitives as PHYS  # type: ignore


# ─── constants ──────────────────────────────────────────────────────────────

# Canonical 10L stack (mirror of geometry_primitives.LAYER_STACK so the search
# stays pcbnew-free at module load). Index = depth from F.Cu.
LAYER_STACK = (
    "F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu",
    "In5.Cu", "In6.Cu", "In7.Cu", "In8.Cu", "B.Cu",
)

# Via class catalogue (BOARD_INVARIANTS §HDI via-in-pad whitelist).
# Each class: (allowed_span_set, base_cost). The maze chooses the cheapest
# class whose span reaches the target layer transition, subject to caller's
# allowed_via_classes whitelist + per-pin HDI gate.
#   microvia    : adjacent outer-skin pair only (F.Cu<->In1, B.Cu<->In8)
#   blind       : F.Cu<->any inner OR B.Cu<->any inner (skip-layer drilled)
#   stacked     : a stack of microvias (here: any 2-layer adjacent inner pair
#                 promoted to stacked-microvia territory, e.g. In1<->In2)
#   through     : full-stack mechanical via (the cheapest in inventory)
VIA_CLASSES = {
    "microvia": {"adjacent_only": True,
                 "outer_skin_only": True,
                 "base_cost": 4.0},
    "blind":    {"adjacent_only": False,
                 "outer_skin_only": False,
                 "base_cost": 6.0,
                 "outer_required": True},   # one endpoint MUST be F.Cu or B.Cu
    "stacked":  {"adjacent_only": True,     # treat as adjacent-pair laser stack
                 "outer_skin_only": False,
                 "base_cost": 8.0},
    "through":  {"adjacent_only": False,
                 "outer_skin_only": False,
                 "base_cost": 2.0},
}

HDI_OUTER_PAIRS = (("F.Cu", "In1.Cu"), ("In8.Cu", "B.Cu"))

# A* cost weights (the cost FUNCTION — physics-derived multipliers, not magic).
COST_STEP_AXIS = 1.0           # 1 cell H/V hop = 1 unit of length
COST_STEP_DIAG = math.sqrt(2)  # 45° hop = sqrt(2) units (true Euclidean)
COST_CORNER = 0.30             # constant penalty per direction change (curvature)
COST_VIA_BASE = 2.0            # additive on top of the via class' base_cost
COST_HIGH_I_CORNER_K = 1.5     # multiplier on (crowd-1) for high-current nets

# Threshold above which corner-crowding cost biases A*.  See sim_loop.advise_corner_fillet.
HIGH_CURRENT_AMPS = 1.0

# Default grid pitch (mm). Documented tradeoff in the module docstring.
DEFAULT_GRID_PITCH_MM = 0.10

# Default expansion cap. Generous for the abstract suite; the real adapter scales
# this with region area × layers (see fill_region_with_maze in phase_c.py).
DEFAULT_EXPANSION_CAP = 100_000

# 8-connectivity moves (dx, dy, kind, base_cost).
_MOVES_8 = (
    (+1,  0, "axis", COST_STEP_AXIS),
    (-1,  0, "axis", COST_STEP_AXIS),
    ( 0, +1, "axis", COST_STEP_AXIS),
    ( 0, -1, "axis", COST_STEP_AXIS),
    (+1, +1, "diag", COST_STEP_DIAG),
    (+1, -1, "diag", COST_STEP_DIAG),
    (-1, +1, "diag", COST_STEP_DIAG),
    (-1, -1, "diag", COST_STEP_DIAG),
)


# ─── data types ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Obstacle:
    """A rectangular keep-out the maze MUST clear by >= clearance_fos_mm.

    kind='body'        : component / passive body keep-out (HARD clearance).
    kind='plane_split' : a GAP in a reference plane (HARD reject for any layer
                         change crossing that gap — Sai-locked SI rule).

    PER-LAYER FILTER (CH1 30/30 (E) engine correctness — 2026-05-28)
    ----------------------------------------------------------------
    `layers` declares the SET of signal layers this obstacle applies to:
      * `None` (default)  → applies to ALL layers (full-stack keep-out, the
                            back-compat behaviour). E.g. a component body
                            keep-out that conservatively blocks every signal
                            layer below it.
      * non-None frozenset → applies ONLY to the named layers (e.g. a track
                            on `In2.Cu` is a keep-out on `In2.Cu` only — a
                            route on `In6.Cu` is physically free to ignore
                            it). Pre-fix, the maze (which iterated obstacles
                            without checking their layer) WRONGLY blocked the
                            In6.Cu route — the engine-correctness bug T15
                            locks against.

    The A* expansion in `route()` skips an obstacle whose `layers` is not
    None AND does not contain the current cell's layer. For `layers=None`
    the obstacle blocks every layer (existing semantics).
    """
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    kind: str = "body"
    plane: Optional[str] = None    # for plane_split: the GND/+VMOTOR plane that splits
    layers: Optional[FrozenSet[str]] = None  # None=all layers (default);
                                             # else frozenset of layer names


@dataclass(frozen=True)
class Pin:
    """A start/end pin in the maze problem. layer is the KiCad signal layer name."""
    point: Tuple[float, float]
    layer: str
    is_hdi_whitelisted: bool = False    # per-pin gate (e.g. J18/J19 on real board)


@dataclass(frozen=True)
class Segment:
    """One straight section of routed trace (start, end, width_mm, layer)."""
    p1: Tuple[float, float]
    p2: Tuple[float, float]
    width_mm: float
    layer: str

    @property
    def length_mm(self) -> float:
        return math.hypot(self.p2[0] - self.p1[0], self.p2[1] - self.p1[1])


@dataclass(frozen=True)
class Via:
    """One layer transition (point, via_class, from_layer, to_layer)."""
    point: Tuple[float, float]
    via_class: str
    from_layer: str
    to_layer: str


@dataclass
class Route:
    """The maze router's success output: a polyline of segments + vias. The
    polyline is OCTILINEAR by construction (no acute interior angles); vias are
    drawn from the caller's allowed_via_classes subject to per-class span
    reachability. Teardrops are inserted at start/end (and at every via on the
    pad layer) via geometry_primitives.teardrop on emit_to_kicad."""
    segments: List[Segment] = field(default_factory=list)
    vias: List[Via] = field(default_factory=list)
    expansions: int = 0
    cost: float = 0.0

    @property
    def length_mm(self) -> float:
        return sum(s.length_mm for s in self.segments)

    @property
    def n_corners(self) -> int:
        """Count direction changes between consecutive segments on the same layer
        (segments separated by a via are NOT a corner — they are layer changes)."""
        if len(self.segments) < 2:
            return 0
        # Group segments by (layer, contiguous chain): a chain breaks at a via.
        # Vias separate chains; corners are direction changes WITHIN a chain.
        chains: List[List[Segment]] = []
        cur: List[Segment] = [self.segments[0]]
        for s in self.segments[1:]:
            if s.layer == cur[-1].layer and _close(s.p1, cur[-1].p2):
                cur.append(s)
            else:
                chains.append(cur)
                cur = [s]
        chains.append(cur)
        corners = 0
        for ch in chains:
            for a, b in zip(ch, ch[1:]):
                d1 = _dir(a.p1, a.p2)
                d2 = _dir(b.p1, b.p2)
                if d1 != d2:
                    corners += 1
        return corners

    @property
    def n_vias(self) -> int:
        return len(self.vias)


class NotRoutable(Exception):
    """Raised when no route exists OR the expansion cap is hit OR the inputs are
    invalid. The .reason field is one of: 'EXPANSION-CAP' | 'NO-PATH' | 'BLOCKED'
    | 'INVALID-INPUTS'. The caller carries this verdict forward — no heroic re-route."""
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# ─── small geometric helpers ─────────────────────────────────────────────────

def _close(a, b, eps=1e-6) -> bool:
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def _dir(p1, p2) -> Tuple[int, int]:
    """Unit-direction sign tuple for an octilinear segment (0/+1/-1)."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    sx = (dx > 1e-9) - (dx < -1e-9)
    sy = (dy > 1e-9) - (dy < -1e-9)
    return (sx, sy)


def _seg_point_dist_sq(ax, ay, bx, by, px, py) -> float:
    """Squared Euclidean distance from point (px,py) to segment a-b."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-18:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2


def _seg_aabb_min_dist(p1, p2, rx_min, ry_min, rx_max, ry_max) -> float:
    """Minimum Euclidean distance between a segment p1-p2 and an axis-aligned
    rectangle (rx_min..rx_max, ry_min..ry_max). Returns 0 if they intersect.
    This is the EXACT clearance check the fab cares about (not the conservative
    AABB approximation). Used by both the maze-router cell-clearance test and
    the run_suite anti-liar witness check (single source of geometric truth)."""
    # If the segment intersects the rect, distance = 0.
    if _seg_intersects_aabb_strict(p1[0], p1[1], p2[0], p2[1],
                                   rx_min, ry_min, rx_max, ry_max):
        return 0.0
    # Otherwise: min distance from either segment endpoint to the rect, OR from
    # the rect's 4 corners to the segment. The minimum of these covers all cases.
    def pt_to_rect_dist_sq(px, py):
        ddx = max(rx_min - px, 0.0, px - rx_max)
        ddy = max(ry_min - py, 0.0, py - ry_max)
        return ddx * ddx + ddy * ddy
    best = min(pt_to_rect_dist_sq(p1[0], p1[1]),
               pt_to_rect_dist_sq(p2[0], p2[1]))
    for cx, cy in ((rx_min, ry_min), (rx_max, ry_min),
                   (rx_max, ry_max), (rx_min, ry_max)):
        d = _seg_point_dist_sq(p1[0], p1[1], p2[0], p2[1], cx, cy)
        if d < best:
            best = d
    return math.sqrt(best)


def _seg_intersects_aabb_strict(x1, y1, x2, y2, rx_min, ry_min, rx_max, ry_max) -> bool:
    """Liang-Barsky strict-interior segment-vs-AABB clip (Cohen-Sutherland kin)."""
    dx, dy = x2 - x1, y2 - y1
    p = [-dx, dx, -dy, dy]
    q = [x1 - rx_min, rx_max - x1, y1 - ry_min, ry_max - y1]
    t0, t1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:
                return False
        else:
            r = qi / pi
            if pi < 0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
    return t0 < t1 - 1e-9


def _obstacle_applies_to_layer(o: "Obstacle", layer: Optional[str]) -> bool:
    """PER-LAYER FILTER (CH1 30/30 (E) engine correctness — 2026-05-28).

    Return True iff obstacle `o` applies on `layer`:
      * `o.layers is None`        → applies to ALL layers (back-compat).
      * `layer is None`           → caller skipped layer (conservative; apply).
      * `layer in o.layers`       → applies on this layer.
      * else                      → does NOT apply (skip — the per-layer fix:
                                     an In2.Cu obstacle does NOT block an In6.Cu
                                     route just because their xy footprints
                                     coincide).
    """
    if o.layers is None:
        return True
    if layer is None:
        return True
    return layer in o.layers


def _swept_track_clears(p1, p2, width_mm, clearance_mm, obstacles,
                        layer: Optional[str] = None) -> bool:
    """True iff the swept trace from p1 to p2 (width + clearance margin on each
    side) clears EVERY APPLICABLE body obstacle by >= (width/2 + clearance)
    Euclidean distance — the EXACT fab clearance check, not the conservative
    AABB. For octilinear traces this matches the AABB only on axis-aligned
    segments; for 45° diagonals the AABB over-rejects, so we use the exact
    segment-to-rect min distance (the same primitive the anti-liar witness
    check uses).

    `layer` is the signal-layer the trace is being drawn on. Per the per-layer
    obstacle filter (Obstacle.layers field; CH1 30/30 (E) fix), an obstacle
    whose `layers` field is set and does NOT include `layer` is SKIPPED —
    physics says a track on In6.Cu is not blocked by an In2.Cu-only keep-out.
    For back-compat, `layer=None` or `o.layers=None` preserves the original
    full-stack-block behaviour.
    """
    margin = width_mm / 2.0 + clearance_mm
    for o in obstacles:
        if o.kind != "body":
            continue
        if not _obstacle_applies_to_layer(o, layer):
            continue
        d = _seg_aabb_min_dist(p1, p2, o.x_min, o.y_min, o.x_max, o.y_max)
        if d < margin - 1e-9:
            return False
    return True


def _step_crosses_plane_split(p1, p2, from_layer, to_layer, obstacles) -> bool:
    """A LAYER-CHANGE step (via) is unreachable if it would punch through a
    plane-split GAP at (p1==p2) on a reference plane between from/to layers.

    Conservative: any plane_split rectangle that CONTAINS the via point makes
    this via unreachable on this site (no continuous reference plane available
    for the return current). HARD constraint per ROUTING_METHODOLOGY §0b / §9.
    """
    # Vias only — same-point step.
    if from_layer == to_layer:
        return False
    for o in obstacles:
        if o.kind != "plane_split":
            continue
        if (o.x_min - 1e-9 <= p1[0] <= o.x_max + 1e-9
                and o.y_min - 1e-9 <= p1[1] <= o.y_max + 1e-9):
            return True
    return False


def _via_class_reachable(via_class: str, from_layer: str, to_layer: str) -> bool:
    """True iff this via class can physically span from_layer<->to_layer per
    its catalogue entry (BOARD_INVARIANTS HDI rules + JLC standard via menu)."""
    if from_layer == to_layer:
        return False
    if from_layer not in LAYER_STACK or to_layer not in LAYER_STACK:
        return False
    i_from = LAYER_STACK.index(from_layer)
    i_to = LAYER_STACK.index(to_layer)
    span = abs(i_to - i_from)
    cls = VIA_CLASSES[via_class]
    pair = (from_layer, to_layer) if i_from < i_to else (to_layer, from_layer)
    if cls.get("adjacent_only") and span != 1:
        return False
    if cls.get("outer_skin_only") and pair not in HDI_OUTER_PAIRS:
        return False
    if cls.get("outer_required"):
        # at least one endpoint must be an outer skin
        if from_layer not in ("F.Cu", "B.Cu") and to_layer not in ("F.Cu", "B.Cu"):
            return False
    return True


def _select_via_class(allowed_classes: Iterable[str], from_layer: str,
                      to_layer: str, hdi_allowed_here: bool) -> Optional[Tuple[str, float]]:
    """Pick the CHEAPEST via class from `allowed_classes` that spans the layer
    pair. Returns (class_name, base_cost) or None if no class reaches.

    HDI gating: microvia and stacked (laser-drilled) require hdi_allowed_here
    (per-pin/per-region whitelist). Without it, only non-HDI classes are
    considered — i.e. the shortage is surfaced, never silently HDI-routed."""
    best = None
    for cls in allowed_classes:
        if cls not in VIA_CLASSES:
            continue
        if cls in ("microvia", "stacked") and not hdi_allowed_here:
            continue
        if not _via_class_reachable(cls, from_layer, to_layer):
            continue
        cost = VIA_CLASSES[cls]["base_cost"]
        if best is None or cost < best[1]:
            best = (cls, cost)
    return best


# ─── A* search node ──────────────────────────────────────────────────────────

@dataclass(order=True)
class _Node:
    """Priority-queue entry. Order = (f, tiebreaker) — bigger-h-first for ties
    keeps the search depth-tilted (Hart-Nilsson-Raphael 1968)."""
    f: float
    tie: int
    g: float = field(compare=False)
    ix: int = field(compare=False)
    iy: int = field(compare=False)
    layer: str = field(compare=False)
    parent_dir: Tuple[int, int] = field(compare=False, default=(0, 0))


# ─── the bounded A* maze router ──────────────────────────────────────────────

def route(
    start: Pin,
    end: Pin,
    region_bbox: Tuple[float, float, float, float],
    obstacles: Iterable[Obstacle],
    allowed_layers: Tuple[str, ...],
    allowed_via_classes: Tuple[str, ...],
    width_mm: float,
    clearance_fos_mm: float,
    expansion_cap: int = DEFAULT_EXPANSION_CAP,
    grid_pitch_mm: float = DEFAULT_GRID_PITCH_MM,
    net_current_a: float = 0.0,
) -> Route:
    """BOUNDED A* maze router. Region-confined, expansion-capped, clearance HARD,
    plane-continuity HARD, octilinear-by-construction. See module docstring.

    Args:
        start, end          : Pin (point, layer, is_hdi_whitelisted).
        region_bbox         : (x_min, y_min, x_max, y_max) mm — the gcell box
                              Phase B hands down. Cells outside are unreachable.
        obstacles           : iterable of Obstacle (body + plane_split).
        allowed_layers      : KiCad layer names the search may use (subset of
                              the 10L stack). MUST include start.layer and end.layer.
        allowed_via_classes : subset of VIA_CLASSES keys the search may emit.
        width_mm            : trace width (the router uses width + clearance_fos
                              as the swept-rect inflation for hard-reject).
        clearance_fos_mm    : clearance ABOVE the fab min (§5c "no cut-to-cut").
        expansion_cap       : hard limit on A* node expansions. Over => raise
                              NotRoutable('EXPANSION-CAP'). No silent grind.
        grid_pitch_mm       : signal grid pitch. Default 0.10 mm (see module doc).
        net_current_a       : net current in A; >= HIGH_CURRENT_AMPS adds the
                              corner-crowding cost bias (Brooks); 0 = signal net.

    Returns:
        Route(segments, vias, expansions, cost). Octilinear; vias only via
        allowed_via_classes; teardrops added on emit, not in the search.

    Raises:
        NotRoutable('INVALID-INPUTS' | 'BLOCKED' | 'EXPANSION-CAP' | 'NO-PATH').
    """
    # ---- input validation (fail loud, never silent) ------------------------
    if grid_pitch_mm <= 0:
        raise NotRoutable("INVALID-INPUTS", f"grid_pitch_mm={grid_pitch_mm}")
    if width_mm <= 0 or clearance_fos_mm < 0:
        raise NotRoutable("INVALID-INPUTS",
                          f"width={width_mm}, clearance={clearance_fos_mm}")
    if start.layer not in allowed_layers or end.layer not in allowed_layers:
        raise NotRoutable(
            "INVALID-INPUTS",
            f"start.layer={start.layer!r} or end.layer={end.layer!r} not in "
            f"allowed_layers={allowed_layers}")
    if expansion_cap <= 0:
        raise NotRoutable("INVALID-INPUTS", f"expansion_cap={expansion_cap}")
    x_min, y_min, x_max, y_max = region_bbox
    if not (x_min < x_max and y_min < y_max):
        raise NotRoutable("INVALID-INPUTS", f"empty region_bbox={region_bbox}")
    if not (x_min - 1e-6 <= start.point[0] <= x_max + 1e-6
            and y_min - 1e-6 <= start.point[1] <= y_max + 1e-6):
        raise NotRoutable("INVALID-INPUTS", f"start {start.point} outside region")
    if not (x_min - 1e-6 <= end.point[0] <= x_max + 1e-6
            and y_min - 1e-6 <= end.point[1] <= y_max + 1e-6):
        raise NotRoutable("INVALID-INPUTS", f"end {end.point} outside region")

    obstacles = tuple(obstacles)

    # ---- grid setup --------------------------------------------------------
    g = grid_pitch_mm
    nx = max(1, int(math.ceil((x_max - x_min) / g)))
    ny = max(1, int(math.ceil((y_max - y_min) / g)))

    def cell_of(point) -> Tuple[int, int]:
        ix = int(round((point[0] - x_min) / g))
        iy = int(round((point[1] - y_min) / g))
        return (max(0, min(nx, ix)), max(0, min(ny, iy)))

    def point_of(ix: int, iy: int) -> Tuple[float, float]:
        return (x_min + ix * g, y_min + iy * g)

    sx, sy = cell_of(start.point)
    ex, ey = cell_of(end.point)

    # ---- precompute per-(cell, layer) "cell is clear" (HARD clearance) -----
    # A cell is CLEAR iff a width_mm trace centred at the cell point clears every
    # APPLICABLE body obstacle by >= clearance_fos_mm.
    #
    # PER-LAYER FILTER (CH1 30/30 (E) engine correctness — 2026-05-28):
    # An obstacle whose `Obstacle.layers` is set and does NOT contain the
    # candidate cell's layer is SKIPPED. For back-compat the default
    # (layers=None) blocks every layer — same conservative semantics as the
    # original (full-stack body keep-out). The fix matters when callers
    # ATTRIBUTE obstacles to specific layers (e.g. an In2.Cu track that should
    # NOT block an In6.Cu route).
    inflate = width_mm / 2.0 + clearance_fos_mm
    body_obs = [o for o in obstacles if o.kind == "body"]

    def cell_clear(ix: int, iy: int, layer: Optional[str] = None) -> bool:
        if ix < 0 or ix > nx or iy < 0 or iy > ny:
            return False
        px, py = point_of(ix, iy)
        cell_x_min = px - inflate
        cell_y_min = py - inflate
        cell_x_max = px + inflate
        cell_y_max = py + inflate
        for o in body_obs:
            if not _obstacle_applies_to_layer(o, layer):
                continue
            if (cell_x_max <= o.x_min or cell_x_min >= o.x_max
                    or cell_y_max <= o.y_min or cell_y_min >= o.y_max):
                continue
            return False
        return True

    # Endpoint cells get a permissive override: a pin sits inside its component
    # body by definition (its pad IS the body's terminal). Clearance is checked
    # against EVERY OTHER body obstacle. Without this the search can never start
    # — the start cell is "inside the IC". Standard maze-router practice (Lee 1961).
    def endpoint_cell_clear(ix: int, iy: int, pin_point,
                            layer: Optional[str] = None) -> bool:
        if ix < 0 or ix > nx or iy < 0 or iy > ny:
            return False
        px, py = point_of(ix, iy)
        cell_x_min = px - inflate
        cell_y_min = py - inflate
        cell_x_max = px + inflate
        cell_y_max = py + inflate
        for o in body_obs:
            if not _obstacle_applies_to_layer(o, layer):
                continue
            # Skip the body the pin actually sits inside.
            if (o.x_min - 1e-6 <= pin_point[0] <= o.x_max + 1e-6
                    and o.y_min - 1e-6 <= pin_point[1] <= o.y_max + 1e-6):
                continue
            if (cell_x_max <= o.x_min or cell_x_min >= o.x_max
                    or cell_y_max <= o.y_min or cell_y_min >= o.y_max):
                continue
            return False
        return True

    if not endpoint_cell_clear(sx, sy, start.point, start.layer):
        raise NotRoutable("BLOCKED", f"start cell ({sx},{sy}) blocked")
    if not endpoint_cell_clear(ex, ey, end.point, end.layer):
        raise NotRoutable("BLOCKED", f"end cell ({ex},{ey}) blocked")

    # ---- A* ---------------------------------------------------------------
    # State = (ix, iy, layer). A move = one of _MOVES_8 (same layer) OR a via
    # transition (ix,iy,layer)->(ix,iy,layer') for layer' in allowed_layers\\{layer}.
    high_current = net_current_a >= HIGH_CURRENT_AMPS

    def heuristic(ix: int, iy: int, layer: str) -> float:
        """Octilinear distance (admissible: never over-estimates true cost) +
        a tiny tie-breaker for layer difference (encourages target-layer-first)."""
        dx = abs(ix - ex)
        dy = abs(iy - ey)
        # exact octilinear shortest distance = max(dx,dy)+ (sqrt2-1)*min(dx,dy)
        octi = max(dx, dy) + (math.sqrt(2) - 1.0) * min(dx, dy)
        layer_diff = 0.0 if layer == end.layer else 0.001 * abs(
            LAYER_STACK.index(layer) - LAYER_STACK.index(end.layer))
        return octi + layer_diff

    # The "came-from" map tracks (predecessor_state, edge_cost, kind).
    came_from: Dict[Tuple[int, int, str], Tuple[Tuple[int, int, str], str, str]] = {}
    g_score: Dict[Tuple[int, int, str], float] = {}
    via_class_used: Dict[Tuple[int, int, str], str] = {}   # for via edges only

    start_state = (sx, sy, start.layer)
    end_state = (ex, ey, end.layer)
    g_score[start_state] = 0.0

    tie = 0
    open_heap: List[_Node] = []
    heapq.heappush(open_heap, _Node(
        f=heuristic(sx, sy, start.layer), tie=tie, g=0.0,
        ix=sx, iy=sy, layer=start.layer, parent_dir=(0, 0)))
    tie += 1

    expansions = 0
    closed: set = set()

    while open_heap:
        node = heapq.heappop(open_heap)
        state = (node.ix, node.iy, node.layer)
        if state in closed:
            continue
        closed.add(state)
        expansions += 1
        if expansions > expansion_cap:
            raise NotRoutable(
                "EXPANSION-CAP",
                f"hit cap {expansion_cap} (region {region_bbox}, grid "
                f"{grid_pitch_mm}mm, layers {allowed_layers}); kick to Phase B")

        if state == end_state:
            # Reconstruct + emit.
            route_obj = _reconstruct(
                start_state, end_state, came_from, via_class_used,
                point_of, width_mm)
            route_obj.expansions = expansions
            route_obj.cost = node.g
            return route_obj

        # 8-connected moves on same layer.
        for dx, dy, kind, base in _MOVES_8:
            nx2, ny2 = node.ix + dx, node.iy + dy
            if not (0 <= nx2 <= nx and 0 <= ny2 <= ny):
                continue
            # cells along the move must be passable (octilinear): both axis cells
            # for a diagonal step ('acid-trap-free bevel' rule). Layer-aware
            # filter: skip obstacles attributed to other layers (Obstacle.layers).
            if kind == "diag":
                if not cell_clear(node.ix + dx, node.iy, node.layer):
                    continue
                if not cell_clear(node.ix, node.iy + dy, node.layer):
                    continue
            # The arrival cell itself: endpoint override iff it IS the end.
            if (nx2, ny2) == (ex, ey) and node.layer == end.layer:
                arrival_ok = endpoint_cell_clear(nx2, ny2, end.point, node.layer)
            elif (nx2, ny2) == (sx, sy) and node.layer == start.layer:
                arrival_ok = endpoint_cell_clear(nx2, ny2, start.point, node.layer)
            else:
                arrival_ok = cell_clear(nx2, ny2, node.layer)
            if not arrival_ok:
                continue
            # the swept trace (from current point to next point) must also clear,
            # honoring the per-layer obstacle filter at this trace's layer.
            p_curr = point_of(node.ix, node.iy)
            p_next = point_of(nx2, ny2)
            if not _swept_track_clears(p_curr, p_next, width_mm, clearance_fos_mm,
                                       obstacles, layer=node.layer):
                continue
            cost = base
            # corner penalty (direction change)
            if node.parent_dir != (0, 0) and node.parent_dir != (dx, dy):
                cost += COST_CORNER
                if high_current:
                    # Brooks crowd factor proxy — bias toward straighter routes
                    # on high-current nets. Inner-corner radius = 0 (sharp).
                    crowd = PHYS.corner_current_crowding_factor(
                        bend_angle_deg=90.0,
                        inner_radius_mm=0.0,
                        width_mm=width_mm,
                    )
                    cost += COST_HIGH_I_CORNER_K * (crowd - 1.0)
            new_state = (nx2, ny2, node.layer)
            new_g = node.g + cost
            if new_g < g_score.get(new_state, math.inf) - 1e-12:
                g_score[new_state] = new_g
                came_from[new_state] = (state, kind, "step")
                f = new_g + heuristic(nx2, ny2, node.layer)
                heapq.heappush(open_heap, _Node(
                    f=f, tie=tie, g=new_g,
                    ix=nx2, iy=ny2, layer=node.layer, parent_dir=(dx, dy)))
                tie += 1

        # via transitions on this cell.
        for new_layer in allowed_layers:
            if new_layer == node.layer:
                continue
            # plane-continuity HARD reject: no via crossing a plane-split.
            p_here = point_of(node.ix, node.iy)
            if _step_crosses_plane_split(p_here, p_here, node.layer, new_layer,
                                         obstacles):
                continue
            hdi_ok = start.is_hdi_whitelisted or end.is_hdi_whitelisted
            picked = _select_via_class(allowed_via_classes, node.layer, new_layer,
                                       hdi_allowed_here=hdi_ok)
            if picked is None:
                continue
            cls_name, cls_cost = picked
            cost = COST_VIA_BASE + cls_cost
            new_state = (node.ix, node.iy, new_layer)
            new_g = node.g + cost
            if new_g < g_score.get(new_state, math.inf) - 1e-12:
                g_score[new_state] = new_g
                came_from[new_state] = (state, "via", cls_name)
                via_class_used[new_state] = cls_name
                f = new_g + heuristic(node.ix, node.iy, new_layer)
                heapq.heappush(open_heap, _Node(
                    f=f, tie=tie, g=new_g,
                    ix=node.ix, iy=node.iy, layer=new_layer, parent_dir=(0, 0)))
                tie += 1

    # exhausted the open heap without reaching the end.
    raise NotRoutable("NO-PATH",
                      f"no octilinear route from {start.point}@{start.layer} to "
                      f"{end.point}@{end.layer} within region {region_bbox} "
                      f"({expansions} expansions, region capped by clearance "
                      f"+ obstacles)")


def _reconstruct(start_state, end_state, came_from, via_class_used,
                 point_of, width_mm) -> Route:
    """Walk came_from end->start, COLLAPSE colinear same-layer steps into single
    Segments, emit Vias at layer changes. Resulting Route is octilinear by
    construction (the search emits no acute angles)."""
    # Build the reverse path (list of states from start to end).
    path = [end_state]
    while path[-1] != start_state:
        prev, _kind, _why = came_from[path[-1]]
        path.append(prev)
    path.reverse()

    segments: List[Segment] = []
    vias: List[Via] = []

    # Walk forward, collapsing colinear same-layer steps.
    i = 0
    while i < len(path) - 1:
        cur = path[i]
        nxt = path[i + 1]
        if cur[2] != nxt[2]:
            # via transition (same cell, different layer)
            cls_name = via_class_used[nxt]
            pt = point_of(cur[0], cur[1])
            vias.append(Via(point=pt, via_class=cls_name,
                             from_layer=cur[2], to_layer=nxt[2]))
            i += 1
            continue
        # collect a run on the same layer with the same direction.
        layer = cur[2]
        seg_start = point_of(cur[0], cur[1])
        dx = nxt[0] - cur[0]
        dy = nxt[1] - cur[1]
        j = i + 1
        while (j + 1 < len(path)
               and path[j][2] == layer and path[j + 1][2] == layer
               and (path[j + 1][0] - path[j][0]) == dx
               and (path[j + 1][1] - path[j][1]) == dy):
            j += 1
        seg_end = point_of(path[j][0], path[j][1])
        segments.append(Segment(p1=seg_start, p2=seg_end,
                                width_mm=width_mm, layer=layer))
        i = j
    return Route(segments=segments, vias=vias)


# ─── solver adapter for run_suite.py (pluggable contract) ────────────────────

def solve(problem) -> dict:
    """run_suite.py contract: `solve(problem) -> dict` where problem is the
    fixtures.Problem input-only view. The maze router addresses single-net
    long-path-through-obstacles cases:
      * T13 — bodies block the direct path on the route's layer; multi-bend
              octilinear detour is forced (the original maze-gate case).
      * T15 — bodies on OTHER layers project onto the route's xy footprint,
              but the per-layer Obstacle.layers filter correctly recognises
              they do NOT block this route's layer (CH1 30/30 (E) engine
              correctness fix, 2026-05-28).
    For every OTHER case the solver returns a clear 'NOT-MY-CASE' verdict
    (so a misuse fails loudly).

    For T13 / T15 the solver:
      1. extracts the single long-path net (start + end pins) from the fixture,
      2. constructs the Obstacle list from problem.obstacles (body kind),
         carrying the per-layer `layers` field through verbatim,
      3. picks the search region as the fixture's pin-bounding box + a margin,
      4. calls route(...) with conservative defaults (octilinear + via through),
      5. PROVES routability + reports the harness-scored metrics:
            verdict = ROUTABLE
            routed = 1
            length_mm
            n_corners
            n_vias
            expansions
    """
    # The maze router's registered cases.
    if problem.name not in ("T13", "T15"):
        return {"verdict": "NOT-MY-CASE",
                "rationale": f"maze_router.solve handles T13/T15 long-path "
                             f"through obstacles; got {problem.name}. Use "
                             "phase_c.solve for general dispatch."}

    if len(problem.nets) != 1:
        return {"verdict": "INVALID-INPUTS",
                "rationale": f"{problem.name} declares 1 long-path net; "
                             f"got {len(problem.nets)}"}

    net = problem.nets[0]
    if len(net.pin_ids) != 2:
        return {"verdict": "INVALID-INPUTS",
                "rationale": f"{problem.name} net needs 2 pins; "
                             f"got {len(net.pin_ids)}"}

    p_start = problem.pin(net.pin_ids[0])
    p_end = problem.pin(net.pin_ids[1])

    # Build maze obstacles from fixture obstacles (body keep-outs).
    # Per-layer filter carries through: fixture Obstacle.layers (None = all
    # layers, back-compat; or frozenset of layer names — the CH1 30/30 (E)
    # engine-correctness fix, T15) is preserved verbatim into the maze
    # Obstacle, so the A* expansion can correctly skip obstacles on layers
    # the candidate cell is not routed on.
    obs = tuple(
        Obstacle(x_min=o.x_min, y_min=o.y_min, x_max=o.x_max,
                 y_max=o.y_max, kind=o.kind, plane=o.plane,
                 layers=o.layers)
        for o in problem.obstacles)

    # Region bbox = pin-bounding rect with a 2mm margin. T13's witness path stays
    # inside this region by construction (encoded in the fixture).
    xs = [p_start.x_mm, p_end.x_mm] + [o.x_min for o in obs] + [o.x_max for o in obs]
    ys = [p_start.y_mm, p_end.y_mm] + [o.y_min for o in obs] + [o.y_max for o in obs]
    region = (min(xs) - 2.0, min(ys) - 2.0, max(xs) + 2.0, max(ys) + 2.0)

    # Conservative defaults: trace = 0.20mm; clearance_fos = 0.20mm (well above
    # JLC 0.0889mm fab min — §5c "above fab min, never at it").
    sig_layers = tuple(L.name for L in problem.signal_layers())
    if p_start.layer not in sig_layers:
        sig_layers = (p_start.layer,) + sig_layers
    if p_end.layer not in sig_layers:
        sig_layers = sig_layers + (p_end.layer,)

    try:
        r = route(
            start=Pin(point=(p_start.x_mm, p_start.y_mm), layer=p_start.layer),
            end=Pin(point=(p_end.x_mm, p_end.y_mm), layer=p_end.layer),
            region_bbox=region,
            obstacles=obs,
            allowed_layers=sig_layers,
            allowed_via_classes=("through",),  # T13 stays on one layer; vias allowed
            width_mm=0.20,
            clearance_fos_mm=0.20,
            expansion_cap=DEFAULT_EXPANSION_CAP,
            grid_pitch_mm=0.5,    # coarser pitch — T13 is mm-scale, not pad-scale
        )
    except NotRoutable as e:
        return {"verdict": "INFEASIBLE",
                "routed": 0,
                "reason": e.reason,
                "rationale": f"maze A* failed: {e}"}

    # Reconstruct the polyline (sequence of (x,y) along the route) so the
    # harness witness check can re-verify endpoints + octilinearity + clearance.
    path: List[Tuple[float, float]] = []
    for s in r.segments:
        if not path or path[-1] != s.p1:
            path.append(s.p1)
        path.append(s.p2)
    return {
        "verdict": "ROUTABLE",
        "routed": 1,
        "length_mm": round(r.length_mm, 4),
        "n_corners": r.n_corners,
        "n_vias": r.n_vias,
        "expansions": r.expansions,
        "path": path,                              # witness for the anti-liar gate
        "segments": [{"p1": s.p1, "p2": s.p2,
                       "width_mm": s.width_mm, "layer": s.layer}
                      for s in r.segments],
        "vias": [{"point": v.point, "via_class": v.via_class,
                   "from_layer": v.from_layer, "to_layer": v.to_layer}
                  for v in r.vias],
        "rationale": (
            f"PHASE C maze (bounded A*): octilinear path length {r.length_mm:.2f} "
            f"mm with {r.n_corners} corners + {r.n_vias} vias, {r.expansions} A* "
            f"expansions (cap {DEFAULT_EXPANSION_CAP}). Region {region} confined; "
            f"clearance 0.20mm + width 0.20mm hard-checked against "
            f"{sum(1 for o in obs if o.kind == 'body')} body obstacles."),
    }


# ─── self-test (no pcbnew, no fixtures dependency at import time) ────────────

def _self_test() -> int:
    """Lightweight standalone self-test: prove the search core works end-to-end
    on a hand-constructed 4-obstacle long-path case, prove EXPANSION-CAP fires
    cleanly when set absurdly low, prove BLOCKED fires when no path exists."""
    print("=" * 72)
    print("maze_router.py — bounded-A* self-test")
    print("=" * 72)
    ok = True

    # 1. Long-path through 3 body obstacles (forces multi-bend octilinear path).
    obs = (
        Obstacle(5.0, 0.0, 6.0, 7.0, kind="body"),
        Obstacle(10.0, 3.0, 11.0, 10.0, kind="body"),
        Obstacle(15.0, 0.0, 16.0, 7.0, kind="body"),
    )
    try:
        r = route(
            start=Pin(point=(0.0, 5.0), layer="F.Cu"),
            end=Pin(point=(20.0, 5.0), layer="F.Cu"),
            region_bbox=(-2.0, -2.0, 22.0, 12.0),
            obstacles=obs,
            allowed_layers=("F.Cu",),
            allowed_via_classes=("through",),
            width_mm=0.20,
            clearance_fos_mm=0.20,
            grid_pitch_mm=0.5,
            expansion_cap=DEFAULT_EXPANSION_CAP,
        )
        cond = (r.length_mm >= 20.0 - 1e-9 and r.n_corners >= 2
                and r.n_vias == 0)
        ok &= cond
        print(f"  {'ok ' if cond else 'XX '}long-path 20mm/3 obs: length="
              f"{r.length_mm:.2f}mm, corners={r.n_corners}, vias={r.n_vias}, "
              f"expansions={r.expansions}")
    except NotRoutable as e:
        ok = False
        print(f"  XX long-path failed: {e}")

    # 2. EXPANSION-CAP: same problem with a stupidly low cap. MUST raise cleanly.
    try:
        route(
            start=Pin(point=(0.0, 5.0), layer="F.Cu"),
            end=Pin(point=(20.0, 5.0), layer="F.Cu"),
            region_bbox=(-2.0, -2.0, 22.0, 12.0),
            obstacles=obs,
            allowed_layers=("F.Cu",),
            allowed_via_classes=("through",),
            width_mm=0.20,
            clearance_fos_mm=0.20,
            grid_pitch_mm=0.5,
            expansion_cap=3,
        )
        ok = False
        print("  XX EXPANSION-CAP: route did NOT raise on cap=3")
    except NotRoutable as e:
        cap_ok = e.reason == "EXPANSION-CAP"
        ok &= cap_ok
        print(f"  {'ok ' if cap_ok else 'XX '}EXPANSION-CAP fires cleanly: {e.reason}")

    # 3. BLOCKED: a sealed obstacle field with no escape.
    sealed = (
        Obstacle(-1.0, 2.0, 6.0, 3.0, kind="body"),
        Obstacle(-1.0, 7.0, 6.0, 8.0, kind="body"),
        Obstacle(-1.0, 2.0, 0.5, 8.0, kind="body"),
        Obstacle(5.0, 2.0, 6.0, 8.0, kind="body"),
    )
    try:
        route(
            start=Pin(point=(3.0, 5.0), layer="F.Cu"),
            end=Pin(point=(20.0, 5.0), layer="F.Cu"),
            region_bbox=(-2.0, -2.0, 22.0, 12.0),
            obstacles=sealed,
            allowed_layers=("F.Cu",),
            allowed_via_classes=("through",),
            width_mm=0.20,
            clearance_fos_mm=0.20,
            grid_pitch_mm=0.5,
            expansion_cap=DEFAULT_EXPANSION_CAP,
        )
        ok = False
        print("  XX BLOCKED: route did NOT raise on sealed region")
    except NotRoutable as e:
        blk_ok = e.reason in ("NO-PATH", "BLOCKED")
        ok &= blk_ok
        print(f"  {'ok ' if blk_ok else 'XX '}sealed region raises: {e.reason}")

    # 4. via-class reachability matrix sanity.
    cond_via = (_via_class_reachable("microvia", "F.Cu", "In1.Cu")
                and not _via_class_reachable("microvia", "F.Cu", "In4.Cu")
                and _via_class_reachable("through", "F.Cu", "B.Cu")
                and not _via_class_reachable("blind", "In2.Cu", "In4.Cu"))
    ok &= cond_via
    print(f"  {'ok ' if cond_via else 'XX '}via-class catalogue reachability matrix")

    # 5. plane-split via reject.
    split_obs = (Obstacle(4.5, 4.5, 5.5, 5.5, kind="plane_split", plane="GND"),)
    blocked = _step_crosses_plane_split((5.0, 5.0), (5.0, 5.0),
                                        "F.Cu", "In2.Cu", split_obs)
    ok &= blocked
    print(f"  {'ok ' if blocked else 'XX '}plane-split via reject (HARD): "
          f"step_crosses={blocked}")

    print("\n" + "=" * 72)
    print("maze_router self-test: " + ("ALL PASS" if ok else "FAILURES PRESENT"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
