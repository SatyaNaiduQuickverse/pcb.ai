#!/usr/bin/env python3
"""channel.py — Engine Step 3: the SURESHOT channel-routing PRIMITIVES.

Design: docs/ROUTING_ENGINE_DESIGN_2026-05-28.md §2 rows T1/T2/T8 + §3 Step 3
("Cyclic-VCG / density / left-edge", gate on T1/T2/T8) + §4 SURESHOT inventory
("Left-edge channel routing on acyclic VCG = optimal track count"; "Cyclic-VCG
detection / density lower bound = exact"; "River routing (order-preserving,
no-cross) = provably minimum-area planar"). Methodology SSoT:
docs/ROUTING_METHODOLOGY.md §0b (Phase A counting / Phase B topology) + §5c.

WHAT THIS IS (and is NOT)
-------------------------
The classical, DETERMINISTIC, PROVABLY-OPTIMAL channel-routing primitives — the
SURESHOT toolbox the engine reaches for BEFORE any heuristic search:

  * LEFT-EDGE channel router on an ACYCLIC VCG (Hashimoto-Stevens 1971): interval-
    graph coloring → assigns nets to tracks using EXACTLY `channel density` tracks,
    the provable optimum. Greedy-by-left-endpoint coloring is optimal on interval
    graphs (no backtracking needed); the track count it returns equals the density
    lower bound, so the result is certified optimal by construction.
  * CHANNEL DENSITY (Sherwani Ch.7): the max number of nets crossing any vertical
    cut = max interval overlap. This is the LOWER BOUND on tracks (two nets that
    share a column cannot share a track). Reuses fixtures.interval_density.
  * VCG construction + CYCLE DETECTION (Deutsch 1976; Sherwani Ch.7): the vertical
    constraint graph edge A→B means net A's terminal sits ABOVE net B's at a shared
    column, forcing A onto a higher track. A directed cycle ⇒ NO consistent track
    order ⇒ dogleg-free INFEASIBLE. We detect cycles (reuse fixtures.has_cycle) and
    compute the MINIMUM number of doglegs to break every cycle: the minimum
    feedback-edge / net-split count that makes the VCG acyclic. Deterministic.
  * RIVER ROUTING (Sherwani Ch.7): when N nets have the SAME left→right order on
    both channel boundaries (reuse fixtures.is_nested_river_order), they form N
    non-crossing "rivers" → a planar SINGLE-LAYER route with 0 crossings, 0 vias,
    exactly N tracks (provably minimum area).

These are EXACT algorithms (interval-graph coloring is polynomial-and-optimal,
cycle detection is exact, nested-interval planarity is a closed-form predicate).
NO A*, NO heuristic search, NO pcbnew, NO numpy. Pi-light, pure stdlib.

THE COUNTS, NOT THE ANSWER
--------------------------
Like phase_a.py, `solve(problem)` receives the INPUT-ONLY `Problem` view
(fixtures.Problem) — it has NO ground_truth / witness / alt_* attribute, so it
CANNOT read the answer it is scored against (anti-drift structural fix,
`[[feedback-systemic-rule-enforcement]]`). Every reported number is COMPUTED from
the problem inputs (pin coords, net→pin membership) via the primitives below —
nothing is hardcoded to the expected value.

PER-CASE DISPATCH (design §3 Step-3 gates)
------------------------------------------
  T1 (baseline channel): build horizontal intervals from pins, run LEFT-EDGE on
     the (acyclic) VCG → {verdict:"ROUTABLE", optimal_track_count == density}.
  T2 (cyclic VCG): build the VCG from the two-column terminal geometry; it has a
     2-cycle → dogleg-free INFEASIBLE; min_doglegs == minimum feedback edges to
     break all cycles == 1 → {verdict:"INFEASIBLE", vcg_cyclic:True, min_doglegs:1}.
  T8 (river): top order == bottom order (nested) → river route, 0 crossings →
     {verdict:"ROUTABLE", crossings:0} (+ tracks == N).

Pure Python + stdlib. No pcbnew, no numpy. Pi-light.
"""
from __future__ import annotations

from itertools import combinations

# Reuse the closed-form helpers — single source of the math (do NOT re-implement).
try:
    from . import fixtures as F
except ImportError:  # loose-script import
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fixtures as F  # type: ignore

interval_density = F.interval_density
has_cycle = F.has_cycle
is_nested_river_order = F.is_nested_river_order


# ----------------------------------------------------------------------------
# Geometry → intervals.  A horizontal net in a channel occupies the column span
# [min(x), max(x)] of its pins (Sherwani's channel model: nets run horizontally,
# terminals sit on the top/bottom boundary). The span is the net's INTERVAL.
# ----------------------------------------------------------------------------

def net_spans(problem):
    """{net_id: (lo_x, hi_x)} — each net's horizontal column span from its pins.
    This is the interval-graph node set for left-edge / density (Sherwani Ch.7)."""
    spans = {}
    for net in problem.nets:
        xs = [problem.pin(p).x_mm for p in net.pin_ids]
        spans[net.net_id] = (min(xs), max(xs))
    return spans


# ----------------------------------------------------------------------------
# 1 + 2.  CHANNEL DENSITY (lower bound) + LEFT-EDGE channel router (optimum).
# ----------------------------------------------------------------------------

def channel_density(spans):
    """Channel density = max # intervals overlapping any vertical cut (Sherwani
    Ch.7; Hashimoto-Stevens 1971). The LOWER BOUND on tracks: two nets sharing a
    column cannot share a track. `spans` = {net_id: (lo, hi)} or list of (lo, hi).
    Reuses fixtures.interval_density (single source of the sweep math)."""
    intervals = list(spans.values()) if isinstance(spans, dict) else list(spans)
    return interval_density(intervals)


def left_edge(spans):
    """LEFT-EDGE channel router on an ACYCLIC VCG (Hashimoto-Stevens 1971).

    Interval-graph coloring by left endpoint: sort nets by left x; place each on
    the FIRST track whose currently-occupied right edge is strictly past (so no
    column overlap with anything already on that track), opening a new track only
    when none fits. On interval graphs this greedy-by-left-endpoint coloring is
    OPTIMAL — it uses exactly `density` colors (tracks), the lower bound — so the
    result needs no backtracking and is certified optimal by construction.

    Returns {"track_of": {net_id: track_index}, "track_count": int}. Deterministic:
    ties at equal left endpoints break by net_id so the assignment is reproducible.

    PRECONDITION (the SURESHOT guarantee): the VCG is ACYCLIC. On a cyclic VCG the
    track-order constraints cannot all be honoured by horizontal tracks alone (a
    dogleg is required first — see vcg_min_doglegs); left-edge's track COUNT is
    still the density, but the assignment would violate a vertical constraint, so
    callers gate left-edge behind `vcg_is_acyclic()` (T1 is acyclic; T2 is not).
    """
    order = sorted(spans.items(), key=lambda kv: (kv[1][0], kv[0]))
    tracks = []                 # tracks[t] = right edge currently occupied on t
    track_of = {}
    for nid, (lo, hi) in order:
        placed = False
        for t, right in enumerate(tracks):
            if lo >= right:     # strictly past the shared column => no overlap
                track_of[nid] = t
                tracks[t] = hi
                placed = True
                break
        if not placed:
            track_of[nid] = len(tracks)
            tracks.append(hi)
    return {"track_of": track_of, "track_count": len(tracks)}


# ----------------------------------------------------------------------------
# 3.  VCG construction + CYCLE DETECTION + MIN-DOGLEGS-to-break-all-cycles.
# ----------------------------------------------------------------------------

def build_vcg(problem, col_tol=1e-6):
    """Build the VERTICAL CONSTRAINT GRAPH from terminal geometry (Sherwani Ch.7).

    A VCG edge A→B means: at some shared column x, net A has a terminal ABOVE net
    B's terminal — so A must occupy a HIGHER track than B (A above B in the track
    order). We detect shared columns by grouping pins by x (within `col_tol`); at
    each column, for every pair of pins from DIFFERENT nets, the higher-y pin's net
    constrains-above the lower-y pin's net.

    Returns (nodes: list[net_id], edges: set[(u_idx, v_idx)] over node indices).
    Edges are deduplicated; self-edges (same net at a column) are skipped. This is
    the exact geometric construction the fixtures' hand-derivation uses (T2: A_L
    above B_L at the left column → A→B; B_R above A_R at the right column → B→A →
    a 2-cycle)."""
    nodes = [n.net_id for n in problem.nets]
    idx = {nid: i for i, nid in enumerate(nodes)}
    net_of_pin = {}
    for net in problem.nets:
        for p in net.pin_ids:
            net_of_pin[p] = net.net_id

    # Group pins by column (x within tolerance). Sort x's, cluster adjacent ones.
    pin_list = [(problem.pin(pid)) for net in problem.nets for pid in net.pin_ids]
    pins_by_x = sorted(pin_list, key=lambda p: p.x_mm)
    columns = []
    cur = []
    for p in pins_by_x:
        if cur and abs(p.x_mm - cur[-1].x_mm) > col_tol:
            columns.append(cur)
            cur = []
        cur.append(p)
    if cur:
        columns.append(cur)

    edges = set()
    for col in columns:
        # For every ordered pair within this column, higher-y net -> lower-y net.
        for hi_pin, lo_pin in combinations(col, 2):
            # `combinations` keeps input order; we must compare y explicitly.
            for a, b in ((hi_pin, lo_pin), (lo_pin, hi_pin)):
                if a.y_mm > b.y_mm:
                    na, nb = net_of_pin[a.id], net_of_pin[b.id]
                    if na != nb:
                        edges.add((idx[na], idx[nb]))
    return nodes, edges


def vcg_is_acyclic(problem):
    """True iff the VCG (built from terminal geometry) has no directed cycle =>
    a consistent top-to-bottom track order exists => left-edge is valid + optimal
    dogleg-free (Sherwani Ch.7). Reuses fixtures.has_cycle."""
    nodes, edges = build_vcg(problem)
    return not has_cycle(len(nodes), list(edges))


def vcg_min_doglegs(problem):
    """MINIMUM number of doglegs to make the VCG acyclic = minimum FEEDBACK EDGE
    SET size = the fewest constraint edges whose removal breaks EVERY directed
    cycle (Deutsch 1976: one dogleg splits a net, dropping the constraint edge it
    sits on). If the VCG is already acyclic, 0.

    DETERMINISTIC + EXACT for the small per-channel VCGs we analyse: we search the
    minimum-feedback-edge-set by increasing size k = 1, 2, ... and, for each k,
    test every k-subset of edges; the first k for which SOME subset's removal makes
    has_cycle False is the answer (the minimum). Edge subsets are taken in a
    canonical (sorted) order so the result is reproducible. This is the textbook
    "min doglegs to acyclic-ify the VCG"; the minimum feedback arc set is NP-hard
    in general, but per-channel VCGs are tiny (a handful of edges), so the exact
    increasing-k enumeration is both tractable and SURESHOT (returns the true
    minimum or proves none below k). For T2 the single 2-cycle {A→B, B→A} is broken
    by removing exactly ONE edge => min_doglegs == 1.

    Returns (min_doglegs: int, broken_edges: list[(u_idx,v_idx)], nodes: list)."""
    nodes, edges = build_vcg(problem)
    edge_list = sorted(edges)
    n = len(nodes)
    if not has_cycle(n, edge_list):
        return 0, [], nodes
    for k in range(1, len(edge_list) + 1):
        for drop in combinations(range(len(edge_list)), k):
            drop_set = set(drop)
            kept = [e for i, e in enumerate(edge_list) if i not in drop_set]
            if not has_cycle(n, kept):
                broken = [edge_list[i] for i in drop]
                return k, broken, nodes
    # Unreachable: removing ALL edges is always acyclic.
    return len(edge_list), edge_list, nodes


# ----------------------------------------------------------------------------
# 4.  RIVER ROUTING (order-preserving, planar, single-layer, minimum-area).
# ----------------------------------------------------------------------------

def boundary_orders(problem, top_suffix="_T", bot_suffix="_B"):
    """Derive each net's order on the TOP and BOTTOM channel boundaries from pin
    geometry. A river fixture (T8) has one pin per net on each boundary, named
    "<net>_T" / "<net>_B". We sort each boundary's pins left→right (by x) and read
    off the net order. Returns (top_order: list[net_id], bot_order: list[net_id]).
    Falls back to splitting pins by y (higher half = top) when suffixes absent."""
    tops, bots = [], []
    suffixed = all(
        any(p.id.endswith(top_suffix) or p.id.endswith(bot_suffix)
            for p in [problem.pin(pid) for pid in net.pin_ids])
        for net in problem.nets
    )
    if suffixed:
        for net in problem.nets:
            for pid in net.pin_ids:
                p = problem.pin(pid)
                if p.id.endswith(top_suffix):
                    tops.append((p.x_mm, net.net_id))
                elif p.id.endswith(bot_suffix):
                    bots.append((p.x_mm, net.net_id))
    else:
        # Geometry fallback: per net, the higher-y pin is its top terminal.
        all_y = [problem.pin(pid).y_mm for net in problem.nets
                 for pid in net.pin_ids]
        mid = (min(all_y) + max(all_y)) / 2.0
        for net in problem.nets:
            for pid in net.pin_ids:
                p = problem.pin(pid)
                (tops if p.y_mm >= mid else bots).append((p.x_mm, net.net_id))
    top_order = [nid for _, nid in sorted(tops, key=lambda t: (t[0], t[1]))]
    bot_order = [nid for _, nid in sorted(bots, key=lambda t: (t[0], t[1]))]
    return top_order, bot_order


def count_crossings(top_order, bot_order):
    """# of net pairs in a different relative order on the two boundaries =
    inversions between the orders = the minimum # of crossings forced (Sherwani
    Ch.7). 0 inversions <=> identical order <=> a planar crossing-free river."""
    pos = {nid: i for i, nid in enumerate(bot_order)}
    seq = [pos[nid] for nid in top_order if nid in pos]
    inv = 0
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            if seq[i] > seq[j]:
                inv += 1
    return inv


def river_route(problem):
    """RIVER ROUTING (Sherwani Ch.7). If the nets share the SAME left→right order
    on both boundaries (is_nested_river_order), they form N non-crossing rivers =>
    a PLANAR single-layer route: 0 crossings, 0 vias, exactly N tracks (provably
    minimum area — any vertical cut is crossed by all N nets, forcing >= N tracks;
    the order-preserving route achieves exactly N).

    Returns dict:
      river_routable : bool (orders match => planar)
      crossings      : int  (0 iff river-routable; else the forced inversions)
      vias           : int  (0 for a single-layer river)
      track_of       : {net_id: track_index} (left->right order = its own band)
      track_count    : int  (== N when river-routable)
      single_layer   : bool
    """
    top_order, bot_order = boundary_orders(problem)
    nested = is_nested_river_order(top_order, bot_order)
    crossings = count_crossings(top_order, bot_order)
    n = len(problem.nets)
    if nested:
        track_of = {nid: i for i, nid in enumerate(top_order)}
        return {
            "river_routable": True,
            "crossings": 0,          # nested order => provably 0 crossings
            "vias": 0,
            "track_of": track_of,
            "track_count": n,        # N parallel rivers = minimum area
            "single_layer": True,
        }
    return {
        "river_routable": False,
        "crossings": crossings,
        "vias": 0,
        "track_of": {},
        "track_count": n,
        "single_layer": True,
    }


# ----------------------------------------------------------------------------
# THE SOLVER (the run_suite.py pluggable contract: solve(problem) -> dict).
# `problem` is the INPUT-ONLY view (fixtures.Problem) — no ground_truth visible.
# Dispatch per the design §3 Step-3 cases (T1/T2/T8); every reported number is
# COMPUTED from the primitives above (never hardcoded to the expected value).
# ----------------------------------------------------------------------------

def solve(problem):
    """SURESHOT channel-routing primitives, dispatched per fixture.

    Returns the harness-scored keys plus the primitive evidence (the proof):
      T1: verdict ROUTABLE, optimal_track_count == channel density (left-edge).
      T2: verdict INFEASIBLE (dogleg-free), vcg_cyclic True, min_doglegs == min
          feedback edges to acyclic-ify (== 1 for the single 2-cycle).
      T8: verdict ROUTABLE, crossings == 0 (river, order-preserving).

    Dispatch is BY STRUCTURE (not by name): a cyclic VCG => the T2 branch; a river
    (matched boundary orders, no doors) => the T8 branch; otherwise an acyclic
    channel => the T1 branch. The verdict + every metric is COMPUTED here.
    """
    spans = net_spans(problem)
    density = channel_density(spans)
    nodes, vcg_edges = build_vcg(problem)
    cyclic = has_cycle(len(nodes), list(vcg_edges))

    # ---- T2 branch: cyclic VCG => dogleg-free INFEASIBLE -----------------
    if cyclic:
        min_dl, broken, _ = vcg_min_doglegs(problem)
        return {
            "verdict": "INFEASIBLE",          # dogleg-free (the base T2 verdict)
            "vcg_cyclic": True,
            "min_doglegs": min_dl,            # min feedback edges to acyclic-ify
            # evidence ------------------------------------------------------
            "channel_density": density,
            "vcg_edges": sorted(vcg_edges),
            "vcg_nodes": nodes,
            "doglegs_break_edges": broken,    # which constraint edges 1 dogleg drops
            "rationale": (
                f"VCG over {nodes} has edges {sorted(vcg_edges)} forming a "
                f"directed cycle (has_cycle=True) => no consistent track order => "
                f"INFEASIBLE dogleg-free; minimum {min_dl} dogleg(s) drop edge(s) "
                f"{broken} to make the VCG acyclic => then ROUTABLE "
                f"(Deutsch 1976; Sherwani Ch.7)."),
        }

    # ---- T8 branch: river (matched boundary orders, no door supply) ------
    # A river channel has terminals on BOTH boundaries in a comparable order and
    # no door/corridor supply structure. Detect it by the boundary-order test.
    top_order, bot_order = boundary_orders(problem)
    is_river = (len(top_order) == len(bot_order) == len(problem.nets)
                and len(problem.doors) == 0 and len(problem.via_slots) == 0)
    if is_river:
        rr = river_route(problem)
        verdict = "ROUTABLE" if rr["river_routable"] else "INFEASIBLE"
        return {
            "verdict": verdict,
            "crossings": rr["crossings"],
            # evidence ------------------------------------------------------
            "vias": rr["vias"],
            "single_layer": rr["single_layer"],
            "track_count": rr["track_count"],
            "track_of": rr["track_of"],
            "n_nets": len(problem.nets),
            "top_order": top_order,
            "bot_order": bot_order,
            "rationale": (
                f"river boundary orders top={top_order} bot={bot_order} "
                f"{'match' if rr['river_routable'] else 'differ'} => "
                f"{rr['crossings']} crossing(s); planar single-layer river with "
                f"{rr['track_count']} tracks == N, 0 vias (Sherwani Ch.7)."),
        }

    # ---- T1 branch: acyclic channel => LEFT-EDGE optimal -----------------
    le = left_edge(spans)
    # On an acyclic VCG the left-edge track count EQUALS the density (the optimum,
    # Hashimoto-Stevens 1971). We report both and the certification they match.
    optimal = le["track_count"]
    door_cap = (problem.doors[0].capacity_tracks if problem.doors else None)
    return {
        "verdict": "ROUTABLE",
        "optimal_track_count": optimal,
        # evidence ----------------------------------------------------------
        "channel_density": density,
        "vcg_acyclic": True,
        "track_of": le["track_of"],
        "vias_required": 0,
        "door_capacity": door_cap,
        "left_edge_equals_density": optimal == density,
        "rationale": (
            f"acyclic VCG (has_cycle=False) => left-edge interval coloring is "
            f"optimal; track_count={optimal} == channel_density={density} "
            f"(Hashimoto-Stevens 1971 optimum)"
            + (f", == door supply {door_cap}" if door_cap is not None else "")
            + "."),
    }


# ----------------------------------------------------------------------------
# Human-readable primitive printer (for the PR evidence / --raw).
# ----------------------------------------------------------------------------

def format_primitives(name, problem):
    """Print the RAW primitive output for one case (left-edge / density / VCG /
    river) — the evidence that the solver's numbers come from the algorithms."""
    lines = [f"=== Channel primitives — {name} ==="]
    spans = net_spans(problem)
    density = channel_density(spans)
    nodes, edges = build_vcg(problem)
    cyclic = has_cycle(len(nodes), list(edges))
    lines.append(f"  net spans (col intervals): "
                 f"{ {k: (round(a, 2), round(b, 2)) for k, (a, b) in spans.items()} }")
    lines.append(f"  channel DENSITY (max overlap) = {density}")
    lines.append(f"  VCG nodes={nodes} edges={sorted(edges)} cyclic={cyclic}")
    if not cyclic and spans:
        le = left_edge(spans)
        lines.append(f"  LEFT-EDGE track_of={le['track_of']} "
                     f"track_count={le['track_count']} "
                     f"(== density {density}: {le['track_count'] == density})")
    if cyclic:
        md, broken, _ = vcg_min_doglegs(problem)
        lines.append(f"  MIN-DOGLEGS to acyclic-ify = {md} (drop edges {broken})")
    top_order, bot_order = boundary_orders(problem)
    if (len(top_order) == len(bot_order) == len(problem.nets)
            and not problem.doors and not problem.via_slots):
        rr = river_route(problem)
        lines.append(f"  RIVER top={top_order} bot={bot_order} "
                     f"routable={rr['river_routable']} crossings={rr['crossings']} "
                     f"vias={rr['vias']} tracks={rr['track_count']}==N")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    try:
        from . import fixtures as Fx
    except ImportError:
        import os
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import fixtures as Fx  # type: ignore

    ap = argparse.ArgumentParser(description="SURESHOT channel-routing primitives")
    ap.add_argument("--cases", default="T1,T2,T8",
                    help="comma-separated case names (default T1,T2,T8)")
    args = ap.parse_args()
    want = [c.strip() for c in args.cases.split(",") if c.strip()]
    for fx in Fx.all_fixtures():
        if fx.name not in want:
            continue
        prob = fx.problem_view() if hasattr(fx, "problem_view") else fx
        print(format_primitives(fx.name, prob))
        res = solve(prob)
        print(f"  solve() -> {{verdict:{res['verdict']!r}"
              + (f", optimal_track_count:{res['optimal_track_count']}"
                 if 'optimal_track_count' in res else "")
              + (f", vcg_cyclic:{res['vcg_cyclic']}, min_doglegs:{res['min_doglegs']}"
                 if 'vcg_cyclic' in res else "")
              + (f", crossings:{res['crossings']}"
                 if 'crossings' in res else "")
              + "}")
        print()
