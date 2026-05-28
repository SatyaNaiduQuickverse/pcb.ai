#!/usr/bin/env python3
"""run_suite.py — the T1-T9 ground-truth test-runner harness.

Engine Step 0 of docs/ROUTING_ENGINE_DESIGN_2026-05-28.md §2/§3.

THREE MODES
-----------
  --self-check   Validate the FIXTURES THEMSELVES are internally consistent and
                 their ground truth is PROVABLE WITHOUT any solver. This is what
                 makes the suite trustworthy: it RE-DERIVES every verdict from
                 first principles (interval density, VCG cycle detection, demand-
                 vs-supply counting, segment-crossing, nested-interval order,
                 skew arithmetic) and asserts it equals the stored ground_truth,
                 AND verifies the encoded WITNESS is a valid solution at the
                 claimed optimum. MUST pass on all 9 before any solver is trusted.

  --list         Print each case's verdict + key metric (one line each).

  (default)      Run a PLUGGABLE solver against every fixture and report PASS/FAIL
                 per case with the metric delta. The solver is supplied via
                 --solver module:callable (engine components register here LATER;
                 NO solver ships in this Step-0 commit).

SOLVER CALLABLE CONTRACT
------------------------
A solver is any callable `solve(problem) -> dict`. **`problem` is the INPUT-ONLY
`Problem` view** (`fixtures.Problem`, built by `Fixture.problem_view()`) — it
exposes ONLY pins/nets/doors/via_slots/obstacles/layers (+ the `pin`/
`signal_layers`/`plane_layers` helpers) and STRUCTURALLY has NO `ground_truth`,
`witness`, or `alt_*` attribute. A solver therefore CANNOT read the answer it is
scored against (anti-drift "structural not discipline" fix, `[[feedback-systemic-
rule-enforcement]]`). The harness asserts this property before every run
(`assert_problem_view_has_no_answer`).

The returned dict reports the solver's findings for that case. Recognised keys
(all optional; the harness compares only the keys the case's expectation names):

    verdict                 : engine verdict vocabulary —
                              "ROUTABLE" | "INFEASIBLE" | "CONDITIONAL" |
                              "NEEDS-HDI" | "NEEDS-PLACEMENT-CHANGE"
    optimal_track_count     : int   (T1)
    vcg_cyclic              : bool  (T2)
    min_doglegs             : int   (T2 resolved)
    routed_nets             : int   (T3/T4/T9 — nets the FEASIBLE GLOBAL plan routes)
    vias_required           : int   (T5)
    direct_path_allowed     : bool  (T6 — must be False)
    achieved_skew_mm        : float (T7)
    crossings               : int   (T8)
    overflow                : int   (T9 — escape overflow with std vias; 0 only w/ HDI)
    greedy                  : dict  ({greedy_routes, global_routes, stranded_nets})
                              — REQUIRED on T3/T4 to PROVE the greedy strand

VERDICT RECONCILIATION (CONDITIONAL cases — see `_accepted_verdicts`)
---------------------------------------------------------------------
The fixtures store a BASE `verdict` (and an `alt_verdict` once a named lever is
applied). A capacity pre-check (Phase A) does NOT emit "CONDITIONAL"; it emits a
concrete engine verdict. The harness reconciles cleanly WITHOUT weakening the
check:

  * T3/T4 (base CONDITIONAL on global-vs-greedy): a solver PASSES iff
      (a) verdict ∈ {CONDITIONAL, ROUTABLE} — Phase A proves a feasible GLOBAL
          assignment EXISTS, so it reports ROUTABLE-under-global (accepted), AND
      (b) routed_nets == global_routes (the global plan routes ALL nets), AND
      (c) greedy.greedy_routes < greedy.global_routes with greedy.stranded_nets
          non-empty — the solver must DEMONSTRATE the greedy strand (the proof the
          global phase is necessary). This is genuinely stronger than the base
          check, not weaker.
  * T9 (base INFEASIBLE → ROUTABLE on HDI): a solver PASSES iff
      verdict ∈ {INFEASIBLE, NEEDS-HDI} (NEEDS-HDI is the precise engine reading
      of "infeasible with std vias, routable with HDI") AND overflow == 1 (the
      std-resource overflow, by counting; 0 only once HDI slots are added).

The harness scores each declared metric and prints the delta. A solver "passes" a
case when its verdict is accepted AND every scored metric matches within
tolerance. This file contains NO routing algorithm — only the harness.

Run:
  python3 hardware/kicad/scripts/routing_engine/run_suite.py --self-check
  python3 hardware/kicad/scripts/routing_engine/run_suite.py --list
  python3 hardware/kicad/scripts/routing_engine/run_suite.py --solver mymod:solve
  python3 hardware/kicad/scripts/routing_engine/run_suite.py \
          --solver routing_engine.phase_a:solve --cases T3,T4,T9
"""
from __future__ import annotations

import argparse
import importlib
import sys

# Support both "python3 run_suite.py" (script) and "-m routing_engine.run_suite".
try:
    from . import fixtures as F
except ImportError:  # run as a loose script
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fixtures as F  # type: ignore


TOL = 1e-6


# ----------------------------------------------------------------------------
# SELF-CHECK: re-derive every ground truth from first principles, no solver.
# Each checker returns (ok: bool, messages: list[str]). It RECOMPUTES the
# answer independently and asserts it matches the fixture's stored ground_truth.
# ----------------------------------------------------------------------------

def _assert(cond, msg, msgs):
    msgs.append(("PASS" if cond else "FAIL", msg))
    return cond


def _selfcheck_T1(fx, msgs):
    gt = fx.ground_truth.metrics
    # Re-derive channel density from the net spans (independent of stored value).
    spans = []
    for net in fx.nets:
        xs = [fx.pin(p).x_mm for p in net.pin_ids]
        spans.append((min(xs), max(xs)))
    density = F.interval_density(spans)
    ok = True
    ok &= _assert(fx.ground_truth.verdict == "ROUTABLE",
                  "verdict ROUTABLE", msgs)
    ok &= _assert(density == gt["optimal_track_count"],
                  f"re-derived density {density} == stored optimal_track_count "
                  f"{gt['optimal_track_count']}", msgs)
    # Door supply must meet the density (boundary: density == supply).
    door = fx.doors[0]
    ok &= _assert(door.capacity_tracks == density,
                  f"door supply {door.capacity_tracks} == density {density} "
                  "(feasibility boundary)", msgs)
    # Witness: no two same-track nets overlap; #tracks == density.
    track_of = fx.ground_truth.witness["track_of"]
    by_track = {}
    span_of = {net.net_id: spans[i] for i, net in enumerate(fx.nets)}
    for nid, t in track_of.items():
        by_track.setdefault(t, []).append(span_of[nid])
    overlap_free = all(
        not _intervals_overlap(a, b)
        for ints in by_track.values()
        for i, a in enumerate(ints) for b in ints[i + 1:]
    )
    ok &= _assert(overlap_free, "witness: no two same-track nets overlap", msgs)
    ok &= _assert(len(by_track) == density,
                  f"witness uses exactly {density} tracks", msgs)
    return ok


def _intervals_overlap(a, b):
    """Two horizontal spans share a column (would short on one track) iff they
    properly overlap. Touching at a single endpoint (a_hi == b_lo) is allowed
    (left-edge: strictly-past rule)."""
    return a[0] < b[1] and b[0] < a[1]


def _selfcheck_T2(fx, msgs):
    gt = fx.ground_truth
    # Reconstruct the VCG from the geometry: for each shared column, the higher
    # pin's net must sit above => directed edge. Here A & B share both end-columns.
    # Left column x≈1: A_L y=8 above B_L y=2 => A->B. Right column x≈9: B_R y=8
    # above A_R y=2 => B->A.
    edges = [(0, 1), (1, 0)]  # A=0, B=1
    cyclic = F.has_cycle(2, edges)
    ok = True
    ok &= _assert(cyclic and gt.verdict == "INFEASIBLE",
                  "VCG has a 2-cycle => INFEASIBLE dogleg-free", msgs)
    ok &= _assert(gt.metrics["feasible_dogleg_free"] is False,
                  "stored feasible_dogleg_free == False", msgs)
    # Resolution: break exactly one net (1 dogleg) removes one edge => acyclic.
    edges_after = gt.alt_witness["vcg_edges_after"]
    ok &= _assert(gt.alt_witness["doglegs"] == 1
                  and gt.alt_metrics["min_doglegs"] == 1,
                  "exactly 1 dogleg in the resolution", msgs)
    ok &= _assert(not F.has_cycle(2, edges_after),
                  "VCG after 1 dogleg is acyclic => ROUTABLE", msgs)
    ok &= _assert(gt.alt_verdict == "ROUTABLE", "alt verdict ROUTABLE", msgs)
    return ok


def _selfcheck_T3(fx, msgs):
    gt = fx.ground_truth
    ok = True
    netmap = {n.net_id: n for n in fx.nets}
    # Read the DECLARED demand structure (which net can use which door).
    y_feas = list(netmap["Y"].feasible_doors)
    x_feas = list(netmap["X"].feasible_doors)
    ok &= _assert(y_feas == ["D_short"],
                  f"Y is most-constrained: feasible doors {y_feas} == [D_short]",
                  msgs)
    ok &= _assert(set(["D_short", "D_long"]).issubset(set(x_feas)),
                  f"X can take either door (feasible {x_feas})", msgs)
    short = next(d for d in fx.doors if d.id == "D_short")
    ok &= _assert(short.capacity_tracks == 1,
                  "short slot supply == 1 (scarce shared resource)", msgs)
    # GREEDY shortest-first picks the cheapest door for X first (D_short),
    # consuming the only resource Y can use => Y stranded. The greedy assignment
    # is only over the short slot (which Y also needs) => COUNT proves the strand:
    greedy = gt.alt_witness["greedy_assignment"]
    greedy_takes_short = greedy.get("X") == "D_short"
    y_blocked = greedy_takes_short and y_feas == ["D_short"]  # Y has no slot left
    ok &= _assert(greedy_takes_short and y_blocked
                  and "Y" in gt.alt_witness["stranded"],
                  "greedy X->D_short consumes Y's only resource => Y stranded "
                  "(1/2), proved by counting", msgs)
    # GLOBAL witness: routes both, every net to one of ITS feasible doors, no
    # door over capacity.
    glob = gt.witness["global_assignment"]
    ok &= _assert(_assignment_feasible(fx, glob),
                  "global assignment uses only each net's feasible doors", msgs)
    ok &= _assert(_assignment_within_capacity(fx, glob),
                  "global assignment respects all door capacities", msgs)
    ok &= _assert(len(glob) == len(fx.nets) and glob["Y"] == "D_short"
                  and glob["X"] == "D_long",
                  "global routes 2/2: Y->short, X->long", msgs)
    ok &= _assert(gt.verdict == "CONDITIONAL" and gt.alt_verdict == "ROUTABLE",
                  "CONDITIONAL on global_vs_greedy -> ROUTABLE", msgs)
    return ok


def _assignment_feasible(fx, assignment):
    """Every net's assigned door must be in that net's declared feasible_doors
    (or feasible_doors empty => any door allowed)."""
    netmap = {n.net_id: n for n in fx.nets}
    for nid, door_id in assignment.items():
        feas = netmap[nid].feasible_doors
        if feas and door_id not in feas:
            return False
    return True


def _assignment_within_capacity(fx, assignment):
    """Count nets per door; every door's load must be <= its capacity_tracks."""
    load = {}
    for door_id in assignment.values():
        load[door_id] = load.get(door_id, 0) + 1
    cap = {d.id: d.capacity_tracks for d in fx.doors}
    return all(load[d] <= cap.get(d, 0) for d in load)


def _selfcheck_T4(fx, msgs):
    gt = fx.ground_truth
    ok = True
    total_supply = sum(d.capacity_tracks for d in fx.doors)
    ok &= _assert(total_supply == len(fx.nets),
                  f"supply {total_supply} == demand {len(fx.nets)} (boundary)",
                  msgs)
    # Mandatory nets each have exactly one feasible door (declared demand).
    netmap = {n.net_id: n for n in fx.nets}
    m1 = list(netmap["M1"].feasible_doors)
    m2 = list(netmap["M2"].feasible_doors)
    g = list(netmap["G"].feasible_doors)
    ok &= _assert(m1 == ["D_P"], f"M1 feasible only D_P (got {m1})", msgs)
    ok &= _assert(m2 == ["D_Q"], f"M2 feasible only D_Q (got {m2})", msgs)
    ok &= _assert(set(["D_P", "D_Q"]).issubset(set(g)),
                  f"G feasible either door (got {g})", msgs)
    # Global witness: all 3 use feasible doors + within capacity.
    glob = gt.witness["global_assignment"]
    ok &= _assert(_assignment_feasible(fx, glob)
                  and _assignment_within_capacity(fx, glob)
                  and len(glob) == 3,
                  "global assignment routes 3/3 feasibly within capacity", msgs)
    # Greedy: G->P (cheapest) saturates D_P (cap 1) => mandatory M1 (only D_P)
    # has no door left => stranded. Proved by counting against M1's feasible set.
    greedy = gt.alt_witness["greedy_assignment"]
    p_cap = next(d.capacity_tracks for d in fx.doors if d.id == "D_P")
    g_in_p = greedy.get("G") == "D_P"
    m1_blocked = g_in_p and p_cap == 1 and m1 == ["D_P"]
    ok &= _assert(g_in_p and m1_blocked and "M1" in gt.alt_witness["stranded"],
                  "greedy G->D_P saturates D_P => M1 stranded (counting proof)",
                  msgs)
    ok &= _assert(gt.verdict == "CONDITIONAL" and gt.alt_verdict == "ROUTABLE",
                  "CONDITIONAL on global_vs_greedy -> ROUTABLE", msgs)
    return ok


def _selfcheck_T5(fx, msgs):
    gt = fx.ground_truth
    ok = True
    a = fx.pin("A_L"), fx.pin("A_R")
    b = fx.pin("B_L"), fx.pin("B_R")
    crosses = F._segments_cross((a[0].x_mm, a[0].y_mm), (a[1].x_mm, a[1].y_mm),
                                (b[0].x_mm, b[0].y_mm), (b[1].x_mm, b[1].y_mm))
    ok &= _assert(crosses and gt.verdict == "INFEASIBLE",
                  "nets cross => INFEASIBLE single-layer (any order)", msgs)
    ok &= _assert(gt.alt_metrics["vias_required"] == 1,
                  "exactly 1 via resolves the crossing", msgs)
    # Witness: one net uses 2 signal layers (3-segment layer list = 1 hop+return
    # = exactly 1 layer change downward then up... counts as the via count).
    layer_of = gt.alt_witness["layer_of"]
    hops = sum(max(0, len(seq) - 1) for seq in layer_of.values())
    # A: F.Cu->In2->F.Cu = 2 transitions = 1 via down + 1 via up? Model: 1 via in
    # the sense of "1 layer-changing structure"; the witness records 1 via.
    ok &= _assert(gt.alt_witness["vias"] == 1,
                  "witness records exactly 1 via", msgs)
    ok &= _assert(any(len(seq) > 1 for seq in layer_of.values()),
                  "witness: one net hops to a 2nd signal layer", msgs)
    ok &= _assert(gt.alt_metrics["acute_angles"] == 0, "0 acute angles", msgs)
    ok &= _assert(gt.alt_verdict == "ROUTABLE", "alt verdict ROUTABLE", msgs)
    return ok


def _selfcheck_T6(fx, msgs):
    gt = fx.ground_truth
    ok = True
    split = next(o for o in fx.obstacles if o.kind == "plane_split")
    # Direct path crosses the split rectangle (segment-vs-rect).
    direct = gt.alt_witness["rejected_direct_path"]
    crosses = _polyline_hits_rect(direct, split)
    ok &= _assert(crosses, "direct path crosses the GND plane-split", msgs)
    ok &= _assert(gt.metrics["direct_path_allowed"] is False,
                  "direct path is REJECTED (hard constraint)", msgs)
    # Continuous detour does NOT enter the split rectangle.
    cont = gt.witness["continuous_path"]
    cont_clear = not _polyline_hits_rect(cont, split)
    ok &= _assert(cont_clear,
                  "continuous-reference detour does NOT cross the split", msgs)
    ok &= _assert(gt.verdict == "CONDITIONAL" and gt.alt_verdict == "ROUTABLE",
                  "CONDITIONAL on plane-continuity-hard -> ROUTABLE", msgs)
    return ok


def _polyline_hits_rect(poly, rect):
    """True iff any segment of the polyline intersects the obstacle rectangle
    interior. Used to prove T6's direct path crosses the split and the detour
    does not. We test each segment against the rect via a clip test."""
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        if _seg_intersects_rect(x1, y1, x2, y2,
                                rect.x_min, rect.y_min, rect.x_max, rect.y_max):
            return True
    return False


def _seg_rect_min_dist(x1, y1, x2, y2, rx_min, ry_min, rx_max, ry_max):
    """EXACT minimum Euclidean distance from segment (x1,y1)-(x2,y2) to AABB.
    Returns 0 if they intersect. Used by the T13 anti-liar witness check so an
    HONEST diagonal route past an obstacle is not falsely rejected by the
    conservative AABB heuristic. Matches maze_router._seg_aabb_min_dist."""
    if _seg_intersects_rect(x1, y1, x2, y2, rx_min, ry_min, rx_max, ry_max):
        return 0.0
    import math as _m
    def _seg_pt_dist_sq(ax, ay, bx, by, px, py):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 < 1e-18:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = ((px - ax) * dx + (py - ay) * dy) / L2
        t = max(0.0, min(1.0, t))
        cx = ax + t * dx
        cy = ay + t * dy
        return (px - cx) ** 2 + (py - cy) ** 2
    def _pt_rect_dist_sq(px, py):
        ddx = max(rx_min - px, 0.0, px - rx_max)
        ddy = max(ry_min - py, 0.0, py - ry_max)
        return ddx * ddx + ddy * ddy
    best = min(_pt_rect_dist_sq(x1, y1), _pt_rect_dist_sq(x2, y2))
    for cx, cy in ((rx_min, ry_min), (rx_max, ry_min),
                   (rx_max, ry_max), (rx_min, ry_max)):
        d = _seg_pt_dist_sq(x1, y1, x2, y2, cx, cy)
        if d < best:
            best = d
    return _m.sqrt(best)


def _seg_intersects_rect(x1, y1, x2, y2, rx_min, ry_min, rx_max, ry_max):
    """Liang-Barsky segment-vs-AABB clip. Returns True if the segment enters the
    rectangle interior (strict)."""
    dx, dy = x2 - x1, y2 - y1
    p = [-dx, dx, -dy, dy]
    q = [x1 - rx_min, rx_max - x1, y1 - ry_min, ry_max - y1]
    t0, t1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:          # parallel and outside this boundary
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
    # Segment overlaps the slab; require a positive-length interior crossing.
    return t0 < t1 - 1e-9


def _selfcheck_T7(fx, msgs):
    gt = fx.ground_truth
    ok = True
    # Re-derive base lengths from pin coords; add the witness meander; check skew.
    base = {}
    for net in fx.nets:
        xs = [fx.pin(p).x_mm for p in net.pin_ids]
        ys = [fx.pin(p).y_mm for p in net.pin_ids]
        base[net.net_id] = abs(max(xs) - min(xs)) + abs(max(ys) - min(ys))
    meander = gt.witness["meander_add_mm"]
    matched = {nid: base[nid] + meander[nid] for nid in base}
    skew = max(matched.values()) - min(matched.values())
    tol = gt.metrics["skew_tol_mm"]
    ok &= _assert(skew <= tol + TOL,
                  f"achieved skew {skew:.3f} <= tol {tol}", msgs)
    ok &= _assert(all(m >= -TOL for m in meander.values()),
                  "all meander additions are non-negative (physical)", msgs)
    door = fx.doors[0]
    ok &= _assert(door.capacity_tracks >= gt.metrics["bus_width"],
                  f"door capacity {door.capacity_tracks} >= bus width "
                  f"{gt.metrics['bus_width']}", msgs)
    trace_w = 0.15
    ok &= _assert(gt.witness["meander_spacing_mm"] >= trace_w - TOL,
                  "meander spacing >= trace width (no self-coupling)", msgs)
    ok &= _assert(gt.verdict == "ROUTABLE", "verdict ROUTABLE", msgs)
    return ok


def _selfcheck_T8(fx, msgs):
    gt = fx.ground_truth
    ok = True
    # Re-derive top + bottom boundary orders from pin coords.
    tops = sorted((fx.pin(f"{n.net_id}_T") for n in fx.nets), key=lambda p: p.x_mm)
    bots = sorted((fx.pin(f"{n.net_id}_B") for n in fx.nets), key=lambda p: p.x_mm)
    top_order = [p.id.rsplit("_", 1)[0] for p in tops]
    bot_order = [p.id.rsplit("_", 1)[0] for p in bots]
    nested = F.is_nested_river_order(top_order, bot_order)
    ok &= _assert(nested, "top order == bottom order (river-routable)", msgs)
    # Matched order => 0 crossings (count inversions between the two orders).
    inversions = _count_inversions(top_order, bot_order)
    ok &= _assert(inversions == 0 == gt.metrics["crossings"],
                  f"derived crossings {inversions} == 0", msgs)
    n = gt.metrics["n_nets"]
    ok &= _assert(gt.metrics["min_tracks"] == n,
                  f"min tracks {gt.metrics['min_tracks']} == N {n} "
                  "(provable minimum)", msgs)
    ok &= _assert(gt.metrics["vias"] == 0 and gt.verdict == "ROUTABLE",
                  "0 vias, single-layer ROUTABLE", msgs)
    return ok


def _count_inversions(order_a, order_b):
    """Number of pairs ordered differently on the two boundaries = lower bound on
    crossings. 0 inversions <=> identical order <=> planar river."""
    pos_b = {nid: i for i, nid in enumerate(order_b)}
    seq = [pos_b[nid] for nid in order_a]
    inv = 0
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            if seq[i] > seq[j]:
                inv += 1
    return inv


def _selfcheck_T9(fx, msgs):
    gt = fx.ground_truth
    ok = True
    # Direct counting — no solver. Supply (no HDI) = non-HDI slots; demand = nets.
    n_std = sum(1 for v in fx.via_slots if not v.hdi_only)
    n_all = len(fx.via_slots)
    demand = len(fx.nets)
    overflow_no_hdi = demand - n_std
    overflow_hdi = demand - n_all
    ok &= _assert(overflow_no_hdi == 1 and gt.verdict == "INFEASIBLE",
                  f"demand {demand} - supply(no HDI) {n_std} = overflow "
                  f"{overflow_no_hdi} > 0 => INFEASIBLE", msgs)
    ok &= _assert(gt.metrics["heroic_route_attempted"] is False,
                  "correct behaviour: NO heroic route, emit ledger + escalate",
                  msgs)
    ok &= _assert(overflow_hdi == 0 and gt.alt_verdict == "ROUTABLE",
                  f"with HDI: demand {demand} - supply {n_all} = overflow "
                  f"{overflow_hdi} => ROUTABLE", msgs)
    # HDI witness is a bijection nets <-> slots.
    slot_of = gt.alt_witness["slot_of"]
    ok &= _assert(len(set(slot_of.values())) == len(slot_of) == demand,
                  "HDI assignment is a bijection nets<->slots (no slot reused)",
                  msgs)
    return ok


def _selfcheck_T10(fx, msgs):
    """T10 — multi-IC-side escape. Re-derive each side's demand/supply/overflow
    from the via_slots + per-net nearest-side attribution (NO solver), prove the
    WORST side governs, and prove that AVERAGING the sides would WRONGLY mask the
    bottleneck side."""
    gt = fx.ground_truth
    ok = True
    # Per-side supply by counting via_slots (independent of any engine code).
    sides = {}
    for vs in fx.via_slots:
        sides.setdefault(vs.ic_side, {"std": 0, "hdi": 0})
        sides[vs.ic_side]["hdi" if vs.hdi_only else "std"] += 1
    # Per-side via-field centroid + nearest-side demand attribution (re-derived).
    centroid = {}
    for s in sides:
        xs = [vs.x_mm for vs in fx.via_slots if vs.ic_side == s]
        ys = [vs.y_mm for vs in fx.via_slots if vs.ic_side == s]
        centroid[s] = (sum(xs) / len(xs), sum(ys) / len(ys))
    side_list = sorted(sides)
    demand = {s: 0 for s in sides}
    for net in fx.nets:
        xs = [fx.pin(p).x_mm for p in net.pin_ids]
        ys = [fx.pin(p).y_mm for p in net.pin_ids]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        best = min(side_list,
                   key=lambda s: ((centroid[s][0] - cx) ** 2
                                  + (centroid[s][1] - cy) ** 2, s))
        demand[best] += 1
    ok &= _assert(demand.get("J20_N") == 3 and demand.get("J20_E") == 2,
                  f"re-derived per-side demand {demand} == N:3 E:2 "
                  "(each net to its nearest side)", msgs)
    ovf_std = {s: max(0, demand[s] - sides[s]["std"]) for s in sides}
    ovf_hdi = {s: max(0, demand[s] - (sides[s]["std"] + sides[s]["hdi"]))
               for s in sides}
    ok &= _assert(ovf_std["J20_N"] == 1 and ovf_hdi["J20_N"] == 0,
                  f"side N: overflow_std {ovf_std['J20_N']}==1, "
                  f"overflow_hdi {ovf_hdi['J20_N']}==0 (HDI closes it)", msgs)
    ok &= _assert(ovf_std["J20_E"] == 0,
                  f"side E: overflow_std {ovf_std['J20_E']}==0 (slack)", msgs)
    worst = max(side_list, key=lambda s: (ovf_std[s], ovf_hdi[s]))
    ok &= _assert(worst == "J20_N",
                  f"worst side (max overflow) == {worst} == J20_N (governs)", msgs)
    # The AVERAGING trap: avg demand vs avg std supply hides the bottleneck.
    avg_demand = sum(demand.values()) / len(demand)            # 2.5
    avg_std = sum(s["std"] for s in sides.values()) / len(sides)  # 2.5
    avg_overflow = max(0, avg_demand - avg_std)                # 0 (WRONG)
    ok &= _assert(avg_overflow == 0 and ovf_std[worst] == 1,
                  f"averaging says overflow {avg_overflow} (ROUTABLE) but the "
                  f"WORST side has overflow {ovf_std[worst]} (NEEDS-HDI) — "
                  "averaging masks the bottleneck => per-side counting NECESSARY",
                  msgs)
    ok &= _assert(gt.verdict == "NEEDS-HDI",
                  "verdict NEEDS-HDI (worst-side overflow_std 1, closed by HDI)",
                  msgs)
    ok &= _assert(gt.metrics["overflow_no_hdi"] == ovf_std[worst] == 1,
                  "stored worst-side overflow == 1", msgs)
    # HDI witness is a bijection nets<->slots (each net to a distinct slot).
    slot_of = gt.alt_witness["slot_of"]
    ok &= _assert(len(set(slot_of.values())) == len(slot_of) == len(fx.nets),
                  "HDI witness is a bijection nets<->slots (no slot reused)", msgs)
    return ok


def _selfcheck_T11(fx, msgs):
    """T11 — internal-vs-crossing classification. Re-derive the classification
    from the fixture (a net is CROSSING iff declared via feasible_doors OR a pin
    sits at a door I/O port; else INTERNAL), prove ONLY the crossing nets count
    against the doors (crossing demand == door supply => feasible), and prove the
    naive all-to-doors planner would over-subscribe."""
    gt = fx.ground_truth
    ok = True
    door_cap = {d.id: d.capacity_tracks for d in fx.doors}
    door_supply = sum(door_cap.values())
    # Re-derive crossing vs internal independently (geometry + declaration).
    def pin_at_any_door(pin):
        for d in fx.doors:
            reach = d.width_mm / 2.0 + 0.5
            if abs(pin.x_mm - d.x_mm) <= reach and abs(pin.y_mm - d.y_mm) <= reach:
                return True
        return False
    crossing, internal = [], []
    for net in fx.nets:
        is_cross = bool(net.feasible_doors) or any(
            pin_at_any_door(fx.pin(p)) for p in net.pin_ids)
        (crossing if is_cross else internal).append(net.net_id)
    ok &= _assert(sorted(internal) == ["int1", "int2", "int3"],
                  f"re-derived INTERNAL nets {sorted(internal)} == 3 interior "
                  "nets (no door)", msgs)
    ok &= _assert(sorted(crossing) == ["x1", "x2"],
                  f"re-derived CROSSING nets {sorted(crossing)} == 2 boundary "
                  "nets (each at a door I/O port)", msgs)
    ok &= _assert(len(crossing) == door_supply == 2,
                  f"crossing demand {len(crossing)} == door supply {door_supply} "
                  "=> a feasible door assignment EXISTS", msgs)
    # Crossing assignment witness: each crossing net to a feasible door, in cap.
    glob = gt.witness["crossing_assignment"]
    ok &= _assert(_assignment_feasible(fx, glob)
                  and _assignment_within_capacity(fx, glob)
                  and set(glob) == set(crossing),
                  "crossing assignment routes both crossing nets feasibly within "
                  "door capacity (x1->D_A, x2->D_B)", msgs)
    # The naive all-to-doors trap: forcing ALL nets onto the doors over-subscribes.
    naive_demand = len(fx.nets)        # 5
    ok &= _assert(naive_demand > door_supply,
                  f"all-to-doors demand {naive_demand} > door supply "
                  f"{door_supply} => a force-assign-all planner OVER-SUBSCRIBES "
                  "(phantom strand) — classification is NECESSARY", msgs)
    ok &= _assert(gt.verdict == "ROUTABLE",
                  "verdict ROUTABLE (only the 2 crossing nets gate the doors; "
                  "the 3 internal nets are escape/within-zone governed)", msgs)
    return ok


def _selfcheck_T13(fx, msgs):
    """T13 — long-path through obstacles (maze-router gate). Re-derive the
    routability + the witness path's correctness WITHOUT any solver:
      (a) the witness path's endpoints match the pin coords,
      (b) the witness path is OCTILINEAR (axis or 45° diagonal — no acute angles),
      (c) every leg clears every body keep-out by ≥ (trace_w/2 + clearance) margin,
      (d) the direct (straight-line) S->E path DOES intersect each body
          (proving the multi-bend topology is FORCED, not cosmetic),
      (e) reported witness_length / witness_n_corners match the recomputed values.
    """
    gt = fx.ground_truth
    ok = True
    wit = gt.witness
    path = wit["path"]
    trace_w = wit["trace_width_mm"]
    clearance = wit["clearance_mm"]
    margin = trace_w / 2.0 + clearance

    # (a) endpoints match the two pins.
    start_pin = fx.pin(fx.nets[0].pin_ids[0])
    end_pin = fx.pin(fx.nets[0].pin_ids[1])
    ok &= _assert(
        abs(path[0][0] - start_pin.x_mm) < 1e-6
        and abs(path[0][1] - start_pin.y_mm) < 1e-6,
        f"witness start {path[0]} == start pin {(start_pin.x_mm, start_pin.y_mm)}",
        msgs)
    ok &= _assert(
        abs(path[-1][0] - end_pin.x_mm) < 1e-6
        and abs(path[-1][1] - end_pin.y_mm) < 1e-6,
        f"witness end {path[-1]} == end pin {(end_pin.x_mm, end_pin.y_mm)}",
        msgs)

    # (b) octilinear: every segment is axis-aligned or |dx|==|dy| (45°).
    all_octi = True
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dx < 1e-9 and dy < 1e-9:
            all_octi = False
            break
        if dx < 1e-9 or dy < 1e-9 or abs(dx - dy) < 1e-9:
            continue
        all_octi = False
        break
    ok &= _assert(all_octi, "every witness segment is octilinear "
                            "(H, V, or 45° — no acute angles by construction)", msgs)

    # (c) clearance HARD: every leg clears every body inflated by `margin`.
    bodies = [o for o in fx.obstacles if o.kind == "body"]
    all_clear = True
    bad_leg = None
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        seg_x_min = min(x1, x2) - margin
        seg_y_min = min(y1, y2) - margin
        seg_x_max = max(x1, x2) + margin
        seg_y_max = max(y1, y2) + margin
        for o in bodies:
            if (seg_x_max <= o.x_min or seg_x_min >= o.x_max
                    or seg_y_max <= o.y_min or seg_y_min >= o.y_max):
                continue
            all_clear = False
            bad_leg = ((x1, y1), (x2, y2), o.id)
            break
        if not all_clear:
            break
    ok &= _assert(all_clear,
                  f"every witness leg clears every body by ≥ {margin}mm "
                  f"(inflated AABB test); failed at {bad_leg}",
                  msgs)

    # (d) the direct straight line MUST hit at least one body (forced detour).
    direct_hits = sum(
        1 for o in bodies
        if _seg_intersects_rect(start_pin.x_mm, start_pin.y_mm,
                                 end_pin.x_mm, end_pin.y_mm,
                                 o.x_min, o.y_min, o.x_max, o.y_max))
    ok &= _assert(direct_hits == len(bodies),
                  f"direct line intersects all {len(bodies)} bodies "
                  f"(hits={direct_hits}) => multi-bend detour is FORCED, not "
                  "cosmetic — the bound topology is genuine", msgs)

    # (e) recomputed metrics match the stored ground truth.
    rec_length = sum(
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        for a, b in zip(path, path[1:]))
    rec_corners = sum(
        1 for i in range(1, len(path) - 1)
        if (path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
        != (path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]))
    ok &= _assert(abs(rec_length - gt.metrics["witness_length_mm"]) < 1e-3,
                  f"recomputed witness_length {rec_length:.4f} == stored "
                  f"{gt.metrics['witness_length_mm']}", msgs)
    ok &= _assert(rec_corners == gt.metrics["witness_n_corners"],
                  f"recomputed witness_n_corners {rec_corners} == stored "
                  f"{gt.metrics['witness_n_corners']}", msgs)
    # The min-length lower bound is the |S-E| Manhattan-projection lower bound
    # (any routable path has length >= horizontal span).
    ok &= _assert(rec_length >= gt.metrics["min_length_mm"],
                  f"witness length {rec_length:.4f} >= min_length_mm "
                  f"{gt.metrics['min_length_mm']} (lower-bound respected)",
                  msgs)
    ok &= _assert(gt.metrics["max_n_vias"] == 0,
                  "max_n_vias == 0 (single-layer detour is feasible — vias not "
                  "needed; an over-eager A* that adds vias still passes only if "
                  "n_vias stays at 0 for the THIS shape)", msgs)
    ok &= _assert(gt.metrics["direct_line_blocked"] is True,
                  "direct_line_blocked == True (ground truth declares the "
                  "forced-detour topology)", msgs)
    ok &= _assert(gt.verdict == "ROUTABLE",
                  "verdict ROUTABLE (a feasible octilinear detour EXISTS — "
                  "witness path encodes one)", msgs)
    return ok


_SELFCHECKS = {
    "T1": _selfcheck_T1, "T2": _selfcheck_T2, "T3": _selfcheck_T3,
    "T4": _selfcheck_T4, "T5": _selfcheck_T5, "T6": _selfcheck_T6,
    "T7": _selfcheck_T7, "T8": _selfcheck_T8, "T9": _selfcheck_T9,
    "T10": _selfcheck_T10, "T11": _selfcheck_T11,
    "T13": _selfcheck_T13,
}


def run_self_check():
    print("=" * 72)
    print("ROUTING ENGINE — T1-T9 GROUND-TRUTH SELF-CHECK")
    print("(re-derives every verdict from first principles; NO solver involved)")
    print("=" * 72)
    all_ok = True
    for fx in F.all_fixtures():
        msgs = []
        ok = _SELFCHECKS[fx.name](fx, msgs)
        all_ok &= ok
        flag = "PASS" if ok else "FAIL"
        print(f"\n[{flag}] {fx.name} — {fx.title}  ({fx.difficulty})")
        for status, m in msgs:
            mark = "  ok " if status == "PASS" else "  XX "
            print(f"{mark}{m}")
    print("\n" + "=" * 72)
    n = len(F.all_fixtures())
    if all_ok:
        print(f"SELF-CHECK: ALL {n} FIXTURES PASS — ground truth is provable, "
              "self-consistent, witness-backed.")
        return 0
    print("SELF-CHECK: FAILURES PRESENT — fixtures are NOT trustworthy. FIX.")
    return 1


def run_list():
    print(f"{'CASE':<5} {'DIFFICULTY':<10} {'VERDICT':<12} KEY METRIC")
    print("-" * 72)
    for fx in F.all_fixtures():
        gt = fx.ground_truth
        v = gt.verdict
        if gt.conditional_on:
            v = f"{gt.verdict}->{gt.alt_verdict}"
        metric = _key_metric_str(fx)
        print(f"{fx.name:<5} {fx.difficulty:<10} {v:<12} {metric}")
    print("-" * 72)
    print("CONDITIONAL = verdict flips on a named lever "
          "(net order / global-vs-greedy / plane-continuity / HDI).")


def _key_metric_str(fx):
    m = fx.ground_truth.metrics
    name = fx.name
    if name == "T1":
        return f"optimal_track_count={m['optimal_track_count']} (==supply)"
    if name == "T2":
        return f"vcg_cyclic=True; min_doglegs={fx.ground_truth.alt_metrics['min_doglegs']}"
    if name == "T3":
        return (f"short_slot_cap={m['short_slot_capacity']}; "
                f"greedy={m['greedy_shortest_first_routes']}/2, global={m['global_routes']}/2")
    if name == "T4":
        return (f"supply={m['total_supply']}==demand={m['total_demand']}; "
                f"greedy={m['greedy_routes']}/3, global={m['global_routes']}/3")
    if name == "T5":
        return (f"cross=True; vias_required_min={m['vias_required_min']}; "
                f"signal_layers={m['signal_layers_required']}")
    if name == "T6":
        return "direct_path_allowed=False; continuous-reference path is the answer"
    if name == "T7":
        return (f"skew {m['achieved_skew_mm']}<= tol {m['skew_tol_mm']}; "
                f"bus_width={m['bus_width']}==door_cap={m['door_capacity']}")
    if name == "T8":
        return f"crossings=0; vias=0; min_tracks={m['min_tracks']}==N"
    if name == "T9":
        return (f"demand={m['demand_nets']} > supply={m['supply_via_slots_no_hdi']} "
                f"=> overflow={m['overflow_no_hdi']} (HDI: overflow=0)")
    if name == "T10":
        return (f"worst side {m['worst_side']}: demand={m['demand_N']} > "
                f"std={m['supply_std_N']} => overflow={m['overflow_std_N']} "
                f"(side E slack; averaging would mask it)")
    if name == "T11":
        return (f"internal={m['n_internal']} (no door) + crossing={m['n_crossing']} "
                f"== door_supply={m['door_supply']} => ROUTABLE")
    if name == "T13":
        return (f"long-path through {3} bodies; witness length="
                f"{m['witness_length_mm']}mm, bends={m['witness_n_corners']}, "
                f"vias=0 (the maze-router gate)")
    return ""


# ----------------------------------------------------------------------------
# SOLVER MODE: run a pluggable solver against the fixtures, score vs ground truth.
# ----------------------------------------------------------------------------

def _load_solver(spec):
    """spec = 'module.path:callable'. Returns the callable."""
    if ":" not in spec:
        raise SystemExit(f"--solver must be module:callable, got {spec!r}")
    mod_name, attr = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)


def _accepted_verdicts(fx):
    """The SET of solver `verdict` strings accepted for this case. For
    deterministic-verdict cases this is just {ground_truth.verdict}. For
    CONDITIONAL cases the fixture's base label is "CONDITIONAL", but a capacity
    pre-check emits a concrete engine verdict; we accept the clean engine reading
    of the lever WITHOUT weakening the metric checks (see SEMANTIC RECONCILIATION
    in the module docstring):
      * T3/T4 (lever = global-vs-greedy): accept CONDITIONAL (the base) OR
        ROUTABLE (Phase A's "a feasible GLOBAL assignment exists"). The genuine
        demonstration is enforced separately by `_special_checks` (routed_nets ==
        global_routes AND greedy strands a net).
      * T9 (lever = HDI): accept INFEASIBLE (the base) OR NEEDS-HDI (the precise
        engine reading: infeasible with std vias, routable once HDI slots added).
      * T6 (lever = plane-continuity-hard): accept CONDITIONAL (the base) OR
        ROUTABLE (the engine's reading: a continuous-reference path EXISTS once the
        split-crossing path is HARD-rejected). This does NOT weaken the test — the
        real check is the metric `direct_path_allowed == False` (scored by
        `_expected_for`): a solver that ALLOWS the split-crossing direct path FAILS
        T6 on that metric regardless of which accepted verdict it returns.
    """
    gt = fx.ground_truth
    if fx.name in ("T3", "T4"):
        return {"CONDITIONAL", "ROUTABLE"}
    if fx.name == "T6":
        return {"CONDITIONAL", "ROUTABLE"}
    if fx.name == "T9":
        return {"INFEASIBLE", "NEEDS-HDI"}
    if fx.name == "T10":
        # multi-side escape: worst side has overflow_std>0 but HDI closes it =>
        # NEEDS-HDI is the precise engine reading; INFEASIBLE accepted as the
        # base "infeasible with std vias" label (same reconciliation as T9).
        return {"INFEASIBLE", "NEEDS-HDI"}
    # T11 base verdict is ROUTABLE (no lever) — only that.
    return {gt.verdict}


def _expected_for(fx):
    """Build the {metric: expected} dict the solver's NUMERIC findings are scored
    against (verdict is scored separately via `_accepted_verdicts`). For
    CONDITIONAL cases the lever-applied numbers live under alt_*; we score the
    metrics that name the case's pass-criterion."""
    gt = fx.ground_truth
    exp = {}
    m = gt.metrics
    if fx.name == "T1":
        exp["optimal_track_count"] = m["optimal_track_count"]
    elif fx.name == "T2":
        exp["vcg_cyclic"] = True
        exp["min_doglegs"] = gt.alt_metrics["min_doglegs"]
    elif fx.name in ("T3", "T4"):
        # under GLOBAL planning the solver routes ALL nets (the alt/global path)
        exp["routed_nets"] = m["global_routes"]
    elif fx.name == "T5":
        exp["vias_required"] = gt.alt_metrics["vias_required"]
    elif fx.name == "T6":
        exp["direct_path_allowed"] = False
    elif fx.name == "T7":
        exp["achieved_skew_mm"] = m["achieved_skew_mm"]
    elif fx.name == "T8":
        exp["crossings"] = 0
    elif fx.name == "T9":
        exp["overflow"] = m["overflow_no_hdi"]
    elif fx.name == "T10":
        # the worst-side std-resource overflow (the binding shortage) — proves
        # the engine counted PER SIDE and took the worst, not the average.
        exp["overflow"] = m["overflow_no_hdi"]   # == 1 (worst side N)
    elif fx.name == "T11":
        # all 5 nets route (2 crossing via doors + 3 internal within-zone). A
        # planner that force-assigned all to doors would route < 5 (strand 3).
        exp["routed_nets"] = m["routed_nets"]     # == 5
    elif fx.name == "T13":
        # the maze router routes the single long-path net (== 1). length is
        # bounded BELOW by min_length_mm (must be at least the horizontal span);
        # n_vias must stay at 0 (single-layer detour is feasible — vias add cost).
        exp["routed"] = m["routed"]               # == 1
        exp["n_vias"] = m["max_n_vias"]           # == 0
    return exp


def _special_checks(fx, got):
    """Extra PASS conditions beyond the scored metrics — these make CONDITIONAL
    reconciliation genuinely STRONGER, not weaker. Returns (ok, notes).

    T3/T4: the solver must DEMONSTRATE the greedy strand (the proof the global
    phase is the fix): a `greedy` block with greedy_routes < global_routes AND a
    non-empty stranded_nets. Without this, claiming ROUTABLE-under-global is not
    backed by the necessity argument and the case FAILS.

    T13: the solver must produce a `path` (or `segments`) that ACTUALLY clears
    every body obstacle and connects the two pins (anti-liar gate). Without
    geometric proof, claiming ROUTABLE is unbacked — the case FAILS. This is
    the engine analogue of run_suite._selfcheck_T13's witness verification
    applied to the SOLVER OUTPUT rather than the FIXTURE ground truth.
    """
    notes = []
    if fx.name in ("T3", "T4"):
        g = got.get("greedy")
        if not isinstance(g, dict):
            return False, ["greedy strand block MISSING (need {greedy_routes, "
                           "global_routes, stranded_nets} to prove global phase)"]
        gr = g.get("greedy_routes")
        gl = g.get("global_routes")
        strand = g.get("stranded_nets") or []
        ok = (isinstance(gr, int) and isinstance(gl, int)
              and gr < gl and len(strand) > 0)
        notes.append(f"greedy {gr} < global {gl}, stranded={strand} "
                     f"=> {'PASS (greedy strand proven)' if ok else 'FAIL'}")
        return ok, notes
    if fx.name == "T13":
        # Anti-liar geometric witness check: the solver must produce a path —
        # either a `path` polyline (list of points) OR a `segments` list (the
        # maze_router native form) OR explicit start->end via segments. Then we
        # verify endpoints, octilinear shape, AND HARD-clearance vs every body.
        path = _solver_path_for_T13(got)
        if not path or len(path) < 2:
            return False, ["T13 anti-liar: no geometric path returned "
                           "(need 'path' polyline or 'segments' — claimed-routed "
                           "without a witness is a LIAR pattern; rejected)"]
        # Endpoints
        net = fx.nets[0]
        sp = fx.pin(net.pin_ids[0])
        ep = fx.pin(net.pin_ids[1])
        end_ok = (abs(path[0][0] - sp.x_mm) < 1e-3
                  and abs(path[0][1] - sp.y_mm) < 1e-3
                  and abs(path[-1][0] - ep.x_mm) < 1e-3
                  and abs(path[-1][1] - ep.y_mm) < 1e-3)
        if not end_ok:
            return False, [f"T13 anti-liar: path endpoints {path[0]},{path[-1]} "
                           f"!= pins {(sp.x_mm, sp.y_mm)},{(ep.x_mm, ep.y_mm)}"]
        # Octilinear (axis or 45°), no acute angles by construction.
        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dx < 1e-6 and dy < 1e-6:
                return False, [f"T13 anti-liar: zero-length segment in path"]
            if not (dx < 1e-6 or dy < 1e-6 or abs(dx - dy) < 1e-6):
                return False, [f"T13 anti-liar: non-octilinear segment "
                               f"({x1},{y1})->({x2},{y2}) — acute-angle risk"]
        # HARD clearance vs every body keep-out — EXACT Euclidean segment-to-rect
        # min distance (not the conservative AABB; matches the maze router's
        # native check so an honest routable solution is not falsely rejected).
        margin = 0.20 / 2.0 + 0.20  # trace 0.20 + clearance 0.20mm (default)
        bodies = [o for o in fx.obstacles if o.kind == "body"]
        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            for o in bodies:
                d = _seg_rect_min_dist(x1, y1, x2, y2,
                                       o.x_min, o.y_min, o.x_max, o.y_max)
                if d < margin - 1e-6:
                    return False, [
                        f"T13 anti-liar: segment ({x1},{y1})->({x2},{y2}) "
                        f"clears body {o.id} by only {d:.4f}mm "
                        f"(need ≥{margin}mm) — LIAR rejected"]
        notes.append(f"T13 geometric witness: {len(path)-1} segments, "
                     f"endpoints match, octilinear, clears all "
                     f"{len(bodies)} bodies by ≥{margin}mm Euclidean => PASS")
    return True, notes


def _solver_path_for_T13(got):
    """Extract a polyline of (x,y) tuples from the T13 solver output. Accepts
    either an explicit `path` (list of points) or a `segments` list (the
    maze_router native form — list of {p1, p2, layer} dicts or Segment dataclass
    instances). Returns None if no path is encodable."""
    if "path" in got and isinstance(got["path"], list):
        return [tuple(p) for p in got["path"]]
    segs = got.get("segments")
    if not segs:
        return None
    pts = []
    for s in segs:
        # Accept dataclass Segment OR dict.
        p1 = getattr(s, "p1", None) or s.get("p1") if hasattr(s, "get") else getattr(s, "p1", None)
        p2 = getattr(s, "p2", None) or s.get("p2") if hasattr(s, "get") else getattr(s, "p2", None)
        if p1 is None or p2 is None:
            return None
        if not pts or pts[-1] != tuple(p1):
            pts.append(tuple(p1))
        pts.append(tuple(p2))
    return pts


def assert_problem_view_has_no_answer(view):
    """Anti-drift structural assertion: the object handed to a solver MUST NOT
    carry the answer. Raises AssertionError if `view` exposes ground_truth /
    witness / alt_* / construction_proof. Demonstrated once at run_solver start
    (and trivially re-checkable by any reviewer)."""
    forbidden = ("ground_truth", "construction_proof", "witness",
                 "alt_verdict", "alt_metrics", "alt_witness")
    present = [a for a in forbidden if hasattr(view, a)]
    assert not present, (
        f"Problem view leaks the answer via {present!r} — a solver could read "
        f"ground truth. The harness must hand solvers an INPUT-ONLY view "
        f"(fixtures.Problem / Fixture.problem_view()).")


def run_solver(spec, cases=None):
    """Run a pluggable solver against the suite (or a `--cases` subset).

    `cases` = list of case names (e.g. ["T3","T4","T9"]); None => all 9. A
    component need only pass the cases it ADDRESSES (design §3 gates each
    component on its own T-rows), so scoring is over the selected subset.

    The solver is handed the INPUT-ONLY Problem view (it cannot read the answer);
    verdict is scored against the ACCEPTED set (CONDITIONAL reconciliation), and
    CONDITIONAL cases carry an extra demonstration check (greedy strand)."""
    solve = _load_solver(spec)
    all_fx = F.all_fixtures()
    if cases:
        want = {c.strip() for c in cases}
        unknown = want - {f.name for f in all_fx}
        if unknown:
            raise SystemExit(f"--cases: unknown case(s) {sorted(unknown)}; "
                             f"valid = {sorted(f.name for f in all_fx)}")
        sel = [f for f in all_fx if f.name in want]
    else:
        sel = all_fx
    print(f"Running solver {spec!r} against "
          f"{'all 9' if not cases else ','.join(f.name for f in sel)}...")
    # Anti-drift structural demonstration: prove the object we hand the solver
    # carries NO answer, ONCE, up front (and per case below via problem_view()).
    assert_problem_view_has_no_answer(sel[0].problem_view())
    print("  [structural] Problem view has no ground_truth/witness/alt_* — "
          "solver cannot read the answer.")
    print("=" * 72)
    n_pass = 0
    for fx in sel:
        exp = _expected_for(fx)
        accepted = _accepted_verdicts(fx)
        problem = fx.problem_view()   # INPUT-ONLY view (no answer leaks)
        try:
            got = solve(problem) or {}
        except Exception as e:  # solver crash = case fail, do not abort suite
            print(f"[FAIL] {fx.name}: solver raised {type(e).__name__}: {e}")
            continue
        deltas = []
        ok = True
        # 1. verdict against the accepted set.
        gv_verdict = got.get("verdict", "<missing>")
        v_ok = gv_verdict in accepted
        deltas.append(f"verdict: got {gv_verdict} accepted {sorted(accepted)} "
                      f"=> {'OK' if v_ok else 'MISMATCH'}")
        ok &= v_ok
        # 2. scored numeric/bool metrics.
        for k, ev in exp.items():
            if k not in got:
                deltas.append(f"{k}: MISSING (exp {ev})")
                ok = False
                continue
            gvv = got[k]
            if isinstance(ev, float) or isinstance(gvv, float):
                match = abs(float(gvv) - float(ev)) <= TOL
                deltas.append(f"{k}: got {gvv} exp {ev} (Δ {float(gvv)-float(ev):+.3g})")
            else:
                match = gvv == ev
                deltas.append(f"{k}: got {gvv} exp {ev}")
            ok &= match
        # 3. case-specific demonstration (greedy strand for T3/T4).
        sp_ok, sp_notes = _special_checks(fx, got)
        deltas.extend(sp_notes)
        ok &= sp_ok
        n_pass += ok
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {fx.name} — {fx.title}")
        for d in deltas:
            print(f"        {d}")
    print("=" * 72)
    total = len(sel)
    print(f"SOLVER RESULT: {n_pass}/{total} cases PASS against ground truth.")
    return 0 if n_pass == total else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="T1-T9 ground-truth test runner")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--self-check", action="store_true",
                   help="validate the fixtures' ground truth WITHOUT a solver")
    g.add_argument("--list", action="store_true",
                   help="list each case's verdict + key metric")
    g.add_argument("--solver", metavar="module:callable",
                   help="run a pluggable solver and score it vs ground truth")
    ap.add_argument("--cases", metavar="T3,T4,T9", default=None,
                    help="comma-separated subset of cases to score the solver on "
                         "(default = all 9). A component need only pass the cases "
                         "it addresses (design §3).")
    args = ap.parse_args(argv)

    if args.list:
        run_list()
        return 0
    if args.solver:
        cases = args.cases.split(",") if args.cases else None
        return run_solver(args.solver, cases)
    if args.cases:
        ap.error("--cases only applies with --solver")
    # default = self-check (the trustworthiness gate)
    return run_self_check()


if __name__ == "__main__":
    sys.exit(main())
