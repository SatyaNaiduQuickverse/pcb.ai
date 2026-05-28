#!/usr/bin/env python3
"""phase_b.py — Engine Step 5: the generic-graph GLOBAL PLANNER (PHASE B).

Design: docs/ROUTING_ENGINE_DESIGN_2026-05-28.md §1 (exec summary, Phase B
paragraph) + §2 rows T3/T4/T5 + §3 Step 5 ("Phase B global plan + DOORS + net
ordering", gate on T3/T4/T5: "global plan beats greedy on T3/T4; door ordering on
T5; all doors <= headroom fill"). Methodology SSoT: docs/ROUTING_METHODOLOGY.md
§0b "PHASE B — Global plan + DOORS + topology" (generic graph; doors first-class;
net-ordering topology-before-geometry; via-slot pre-assignment; layer assignment;
capacity headroom) + §5c FoS-everywhere row "Routing-process capacity <= 75-80%,
never 100%" (the root-cause fix for the CH1 24/30 corner-paint). Board door model:
docs/BOARD_INVARIANTS.md (doors = I/O ports + interior channel mouths + highways).

WHAT THIS IS (and is NOT)
-------------------------
Phase B is the SYNTHESIS layer. It does NOT re-implement capacity (Phase A),
channel ordering (channel.py), or layer/via assignment (layer_assign.py) — it
COMPOSES those already-merged, already-validated modules into ONE structured
GLOBAL PLAN that a detailed router (Phase C, Step 6) later fills with exact
tracks. Phase A says "is it feasible + which net goes to which door"; Phase B
says "...and in what ORDER through each door, on which LAYER, traversing which
VIA SLOTS, with how much capacity HEADROOM" — the complete pre-geometry plan.

  * The GLOBAL ASSIGNMENT (which net -> which door) is EXACT (Phase A max-flow /
    Hall). SURESHOT — not search, not A*, not a heuristic. A* lives ONLY in
    Phase C (ROUTING_METHODOLOGY §0b "A* usage").
  * NET-ORDERING through a door reuses channel.py's VCG / left-edge ordering.
    Topology-before-geometry. Deterministic (ties broken by net id / x).
  * LAYER + VIA-SLOT pre-assignment reuses layer_assign.py + the Problem's
    via_slots. Each layer change = a full-stack via = an SI discontinuity, so
    via count is minimised within the layer-assignment constraints.
  * CAPACITY HEADROOM (FoS): each door's demand is checked against
    FOS_ROUTING_CAPACITY x capacity (<=75-80%, §5c). Where headroom is feasible
    we honour it; at a boundary fixture (T3/T4 are demand==supply==100%) a
    headroom-respecting plan is IMPOSSIBLE, so we route the hard-feasible plan
    AND flag `headroom_exceeded=True` (tight, no margin). Headroom is a planning
    PREFERENCE; hard-feasibility (Phase A) is the GATE. We never refuse a
    hard-feasible plan for lack of headroom — that is the honest report and it
    mirrors Phase A's behaviour.

THE GENERIC GRAPH MODEL (Sai-locked: build it generic even if slower)
---------------------------------------------------------------------
`build_routing_graph(problem)` builds a generic, extensible routing-resource +
demand graph from the INPUT-ONLY Problem (pins / nets / doors / via_slots /
obstacles / layers). It is NOT special-cased to the abstract fixtures — the same
node/edge vocabulary carries the real CH1 board (doors = BOARD_INVARIANTS I/O
ports + channel mouths + highways; via-sites = HDI dog-bone fanout slots;
corridor-junctions = where corridors meet). Node kinds + edge kinds:

  NODE kinds
    "pin"               a net terminal (one per Pin)
    "door"              a corridor cross-section / port (one per Door) — a SUPPLY
                        node carrying capacity_tracks
    "via_site"          an escape via slot (one per ViaSlot) — a SUPPLY node
    "corridor_junction" a synthetic node where corridors/doors meet (one per
                        distinct door coordinate cluster) — keeps the model
                        generic for multi-hop corridor paths on the real board

  EDGE kinds
    "supply"   door/via-site capacity edge: (node, capacity) — the routing
               resource a net consumes. capacity = Door.capacity_tracks (door) or
               1 (a single via_site slot).
    "demand"   net -> door / net -> via_site reachability edge: net needs ONE unit
               of that resource. Built from each net's EFFECTIVE feasible set
               (Phase A's declared/inferred reconciliation) for doors, and from
               via_slots' ic_side for escape nets.

The graph object exposes `nodes`, `edges`, and convenience views
(`doors()`, `via_sites()`, `demand_edges_of(net)`, `supply_capacity(node)`),
so Phase C can consume it directly. It is a plain dataclass of stdlib dicts/lists
— Pi-light, no numpy, no pcbnew.

THE GLOBAL PLAN (the OUTPUT — Phase C consumes this; see GlobalPlan / DoorPlan)
------------------------------------------------------------------------------
`plan(problem) -> GlobalPlan`. The schema is documented on the dataclasses below
and re-stated in `GlobalPlan.schema_doc()` so Phase C has an authoritative,
in-code contract. Summary:

  GlobalPlan
    .verdict            engine verdict (ROUTABLE / INFEASIBLE / NEEDS-HDI / ...)
    .feasible           bool — Phase A hard-feasibility gate result
    .doors              {door_id: DoorPlan}
    .via_assignment     {net_id: via_slot_id} (escape via-slot pre-assignment)
    .net_to_door        {net_id: door_id} (the global assignment witness)
    .net_layers         {net_id: layer_index} (layer_assign coloring)
    .headroom_exceeded   bool — ANY door over FoS headroom (tight plan, no margin)
    .greedy             {greedy_routes, global_routes, stranded_nets, ...}
    .escape_ledger      per-IC-side via demand/supply (when via_slots present)
    .rationale          human-readable provenance of the verdict

  DoorPlan (per door)
    .door_id            the door
    .capacity           Door.capacity_tracks (SUPPLY)
    .ordered_nets       nets passing this door, ORDERED (topology-before-geometry,
                        VCG / left-edge derived) — the sequence Phase C lays in
    .net_layers         {net_id: layer_index} for the nets at this door
    .net_via_slots      {net_id: [via_slot_id, ...]} the via slots each net
                        traverses through this door's corridor
    .demand             len(ordered_nets)
    .headroom_capacity  FOS_ROUTING_CAPACITY x capacity
    .headroom_ok        demand <= headroom_capacity (the §5c FoS flag)

GREEDY-VS-GLOBAL (the end-to-end proof the global phase is necessary — T3/T4)
-----------------------------------------------------------------------------
`greedy_vs_global(problem)` reuses phase_a's greedy-strand detection to
demonstrate that the GLOBAL plan routes ALL nets where the naive greedy
(least-constrained-first, shortest-door-first, no backtracking — the v1->v8
cooperative-router failure mode) STRANDS one. Returned in the plan's `.greedy`
block and surfaced to the harness so the T3/T4 `_special_checks` greedy proof
passes genuinely (greedy_routes < global_routes, stranded non-empty).

SOLVER CONTRACT (run_suite.py)
------------------------------
`solve(problem) -> dict`. `problem` is the INPUT-ONLY Problem view (pins / nets /
doors / via_slots / obstacles / layers) — NO ground_truth / witness / alt_*. We
compute every reported number from those inputs via the graph + the composed
modules; NOTHING is hardcoded from the expected answer. Dispatch is STRUCTURAL:

  * door-based feasibility problem (T3/T4: has doors, no plane-split):
      build the global plan; emit
      {verdict: ROUTABLE (a feasible GLOBAL assignment exists, Phase A gate),
       routed_nets: <the plan routes ALL nets> == global_routes,
       greedy: {greedy_routes, global_routes, stranded_nets}}.
      The harness accepts CONDITIONAL|ROUTABLE for T3/T4 and additionally
      REQUIRES routed_nets == global_routes AND a proven greedy strand — both
      satisfied genuinely by the plan.
  * crossing / single-layer-ordering problem (T5: no doors, nets cross):
      the planner orders the 2 crossing nets through the (implicit) single door
      and the layer-assignment step inserts the 1 via that resolves the crossing;
      emit {verdict: INFEASIBLE (single-layer base), vias_required: 1}.

Pure Python + stdlib. No pcbnew, no numpy, no A*. Pi-light. No geometry emitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# COMPOSE the already-merged engine modules — do NOT reimplement their logic.
try:
    from . import fixtures as F
    from . import phase_a as PA
    from . import channel as CH
    from . import layer_assign as LA
except ImportError:  # run as a loose script / -m from scripts dir
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fixtures as F  # type: ignore
    import phase_a as PA  # type: ignore
    import channel as CH  # type: ignore
    import layer_assign as LA  # type: ignore


# FoS headroom multiplier — single source is phase_a (ROUTING_METHODOLOGY §5c
# "Routing-process capacity <= 75-80%, never 100%"). We reuse Phase A's constant
# so the headroom band cannot drift between the two phases.
FOS_ROUTING_CAPACITY = PA.FOS_ROUTING_CAPACITY


# ============================================================================
# 1. THE GENERIC GRAPH MODEL
# ============================================================================

@dataclass(frozen=True)
class GraphNode:
    """A node in the generic routing-resource + demand graph.

    kind: "pin" | "door" | "via_site" | "corridor_junction".
    id  : the underlying object id (Pin.id / Door.id / ViaSlot.id) or a synthetic
          junction id.
    x_mm, y_mm : coordinate (for pins/doors/via_sites; junctions take their
          cluster coordinate). Kept so Phase C can geometrize without re-reading
          the Problem.
    capacity : SUPPLY capacity for supply-bearing nodes (door = capacity_tracks,
          via_site = 1); None for pins / junctions (they carry no supply).
    attrs : free-form extension dict (layer-set, ic_side, plane, ...) — keeps the
          model GENERIC/extensible for the real CH1 board without schema churn.
    """
    kind: str
    id: str
    x_mm: float
    y_mm: float
    capacity: Optional[int] = None
    attrs: tuple = ()   # tuple of (key, value) so the node stays frozen/hashable


@dataclass(frozen=True)
class GraphEdge:
    """An edge in the generic graph.

    kind: "supply" | "demand".
      supply  : u = a resource node (door / via_site); v == u (self-loop tag) —
                an edge that DECLARES the node's capacity as a routing resource.
                (Modelled as an edge so the graph carries both supply + demand in
                one uniform edge list, Phase-C-friendly.)
      demand  : u = a "net:<net_id>" demand token; v = a resource node the net can
                consume (door / via_site). One unit of demand per edge.
    capacity : for supply edges = the resource capacity; for demand = 1.
    """
    kind: str
    u: str
    v: str
    capacity: int


@dataclass
class RoutingGraph:
    """The generic routing-resource + demand graph (Phase B's model, Phase C
    consumes it). Plain stdlib containers; Pi-light. Generic by construction —
    the SAME node/edge vocabulary carries the real CH1 board."""
    nodes: Dict[str, GraphNode]                  # node key -> GraphNode
    edges: List[GraphEdge]                       # supply + demand edges
    net_feasible: Dict[str, Tuple[str, ...]]     # net_id -> reachable door ids
    net_via_sides: Dict[str, Tuple[str, ...]]    # net_id -> ic_side(s) it escapes

    # ---- convenience views (Phase C consumes these) ----------------------
    def doors(self) -> List[GraphNode]:
        return [n for n in self.nodes.values() if n.kind == "door"]

    def via_sites(self) -> List[GraphNode]:
        return [n for n in self.nodes.values() if n.kind == "via_site"]

    def pins(self) -> List[GraphNode]:
        return [n for n in self.nodes.values() if n.kind == "pin"]

    def junctions(self) -> List[GraphNode]:
        return [n for n in self.nodes.values() if n.kind == "corridor_junction"]

    def supply_capacity(self, node_id: str) -> int:
        n = self.nodes.get(node_id)
        return n.capacity if (n and n.capacity is not None) else 0

    def demand_edges_of(self, net_id: str) -> List[GraphEdge]:
        tok = f"net:{net_id}"
        return [e for e in self.edges if e.kind == "demand" and e.u == tok]


def _door_node_key(door_id: str) -> str:
    return f"door:{door_id}"


def _via_node_key(slot_id: str) -> str:
    return f"via:{slot_id}"


def _pin_node_key(pin_id: str) -> str:
    return f"pin:{pin_id}"


def build_routing_graph(problem) -> RoutingGraph:
    """Build the GENERIC graph from the INPUT-ONLY Problem.

    NODES:
      - one "pin" node per Pin (terminal of demand)
      - one "door" node per Door (SUPPLY = capacity_tracks)
      - one "via_site" node per ViaSlot (SUPPLY = 1, attrs carry ic_side/hdi_only)
      - one "corridor_junction" node per distinct door (x,y) cluster — synthetic
        nodes that keep the model generic for multi-hop corridor paths on the real
        board (the fixtures have one door per coord, so one junction per door).

    EDGES:
      - "supply" edge per door / via_site declaring its capacity
      - "demand" edge per (net, reachable-door) pair, using the net's EFFECTIVE
        feasible set (Phase A's declared/inferred reconciliation — single source
        of the reachability math, NOT re-derived here)
      - "demand" edge per (escape-net, via_site) pair, for escape nets whose
        ic_side the via_site serves

    This is COMPUTED from inputs; nothing hardcoded. Returns a RoutingGraph.
    """
    nodes: Dict[str, GraphNode] = {}
    edges: List[GraphEdge] = []

    # ---- pin nodes -------------------------------------------------------
    for p in problem.pins:
        key = _pin_node_key(p.id)
        nodes[key] = GraphNode("pin", p.id, p.x_mm, p.y_mm, None,
                               (("layer", p.layer),))

    # ---- door nodes + supply edges + corridor junctions ------------------
    junctions: Dict[Tuple[float, float], str] = {}
    for d in problem.doors:
        key = _door_node_key(d.id)
        nodes[key] = GraphNode(
            "door", d.id, d.x_mm, d.y_mm, d.capacity_tracks,
            (("layers", tuple(d.layers)), ("width_mm", d.width_mm),
             ("passes", tuple(d.passes))))
        edges.append(GraphEdge("supply", key, key, d.capacity_tracks))
        # A corridor junction per distinct door coordinate (generic multi-hop).
        coord = (round(d.x_mm, 6), round(d.y_mm, 6))
        if coord not in junctions:
            jkey = f"junction:{coord[0]}_{coord[1]}"
            junctions[coord] = jkey
            nodes[jkey] = GraphNode("corridor_junction", jkey,
                                    d.x_mm, d.y_mm, None,
                                    (("doors", (d.id,)),))

    # ---- via_site nodes + supply edges -----------------------------------
    for vs in problem.via_slots:
        key = _via_node_key(vs.id)
        nodes[key] = GraphNode(
            "via_site", vs.id, vs.x_mm, vs.y_mm, 1,
            (("ic_side", vs.ic_side), ("hdi_only", vs.hdi_only)))
        edges.append(GraphEdge("supply", key, key, 1))

    # ---- net DEMAND edges (reachability) ---------------------------------
    # Reuse Phase A's reconciliation as the SINGLE SOURCE of net->door
    # reachability (declared/inferred cross-check); do NOT re-derive it here.
    if problem.doors:
        effective_feasible, _reports = PA.reconcile_reachability(problem)
    else:
        effective_feasible = {}
    net_feasible: Dict[str, Tuple[str, ...]] = {}
    for net in problem.nets:
        feas = tuple(effective_feasible.get(net.net_id, ()))
        net_feasible[net.net_id] = feas
        tok = f"net:{net.net_id}"
        for door_id in feas:
            edges.append(GraphEdge("demand", tok, _door_node_key(door_id), 1))

    # ---- escape (via-site) demand edges ----------------------------------
    # In the abstract escape model (T9 / J18-J19) each escape net needs one slot
    # on its ic_side. With a single ic_side in the supply, every net is an escape
    # net for that side; this generalises to per-side attribution on the real
    # board (phase_a._demand_for_side is the hook). We add demand edges from each
    # escape net to EVERY via_site serving its side (the planner picks one).
    net_via_sides: Dict[str, Tuple[str, ...]] = {}
    if problem.via_slots:
        sides = {vs.ic_side for vs in problem.via_slots}
        only_side = next(iter(sides)) if len(sides) == 1 else None
        for net in problem.nets:
            side = only_side  # single-side fixtures; real board localises per net
            if side is None:
                net_via_sides[net.net_id] = ()
                continue
            net_via_sides[net.net_id] = (side,)
            tok = f"net:{net.net_id}"
            for vs in problem.via_slots:
                if vs.ic_side == side:
                    edges.append(GraphEdge("demand", tok, _via_node_key(vs.id), 1))

    return RoutingGraph(nodes=nodes, edges=edges,
                        net_feasible=net_feasible, net_via_sides=net_via_sides)


# ============================================================================
# 2. NET ORDERING through a door (topology-before-geometry; reuse channel.py)
# ============================================================================

def order_nets_through_door(problem, net_ids) -> List[str]:
    """Order the nets passing a door (topology-before-geometry). Reuse channel.py:
    derive each net's column SPAN and order by the LEFT-EDGE discipline (sort by
    left endpoint, tie-break by net id) — the deterministic interval-graph order
    channel.left_edge uses. This is the order Phase C lays the nets in through the
    door so the planar (acyclic) topology is honoured before any geometry exists.

    We use channel.net_spans (the same span primitive channel.left_edge consumes),
    so the ordering is the channel module's, not a Phase-B re-derivation. For nets
    with no usable span (single pin / degenerate) we fall back to net-id order.
    Returns the ordered net_ids."""
    spans = CH.net_spans(problem)
    def _key(nid):
        sp = spans.get(nid)
        lo = sp[0] if sp else 0.0
        return (lo, nid)
    return sorted(net_ids, key=_key)


# ============================================================================
# 3. VIA-SLOT PRE-ASSIGNMENT (reuse layer_assign for layers; assign slots from
#    the graph's via_sites so siblings don't fight over the same via).
# ============================================================================

def assign_layers(problem) -> Dict[str, int]:
    """Per-net layer index. Reuse layer_assign's SURESHOT conflict-graph coloring
    (the chromatic number = min signal layers; crossing nets get different layers).
    Returns {net_id: layer_index}. For nets with no crossing the coloring is all
    layer 0 (single layer)."""
    la = LA.layer_assignment(problem)
    coloring = dict(la["coloring"])
    # Ensure every net has a layer (coloring covers all nets, but be defensive).
    for net in problem.nets:
        coloring.setdefault(net.net_id, 0)
    return coloring, la


def preassign_via_slots(graph: RoutingGraph, problem,
                        net_to_door: Dict[str, str]) -> Dict[str, List[str]]:
    """Pre-assign the via slots each net traverses, so SIBLING escapes do not
    fight over the same via (the MASTER_COOP_ROUTER "multi-net joint A*" gap-fix,
    ROUTING_METHODOLOGY §0b Phase B item 3). Deterministic.

    Two sources of via slots:
      (a) ESCAPE slots: when the problem has via_sites, assign each escape net a
          DISTINCT via_site serving its side (a bijection where supply allows it),
          via Phase A's max-flow over the net->via_site demand graph (exact, no
          double-booking). This is the T9-style escape pre-assignment.
      (b) LAYER-CHANGE vias: a net whose assigned LAYER differs from its pin's base
          layer needs a via STRUCTURE to reach that layer (layer_assign's via).
          We record it as a synthetic slot id "layerhop:<net>" so Phase C knows a
          via is reserved on that net's corridor (no physical slot in the abstract
          fixtures — Phase C places it).

    Returns {net_id: [via_slot_id, ...]} (may be empty for a net needing none).
    """
    out: Dict[str, List[str]] = {n.net_id: [] for n in problem.nets}

    # (a) ESCAPE via-site pre-assignment via Phase A max-flow (no double-booking).
    if problem.via_slots:
        # Build a per-net feasible-via-slot map + unit capacities; reuse Phase A's
        # exact bipartite max-flow so two siblings never get the SAME slot.
        via_cap = {_via_node_key(vs.id): 1 for vs in problem.via_slots}
        feasible_of = {}
        for net in problem.nets:
            sides = graph.net_via_sides.get(net.net_id, ())
            slots = [_via_node_key(vs.id) for vs in problem.via_slots
                     if vs.ic_side in sides]
            feasible_of[net.net_id] = slots
        res = PA.feasible_assignment([n.net_id for n in problem.nets],
                                     feasible_of, via_cap)
        for nid, vkey in res["assignment"].items():
            # vkey == "via:<slot_id>" -> recover the slot id
            out[nid].append(vkey.split("via:", 1)[1])

    # (b) LAYER-CHANGE via reservation (a net lifted off its base layer).
    coloring, _la = assign_layers(problem)
    if coloring:
        base = min(coloring.values())
        for nid, c in coloring.items():
            if c != base:
                out.setdefault(nid, []).append(f"layerhop:{nid}")
    return out


# ============================================================================
# 4. THE GLOBAL PLAN (the OUTPUT — Phase C consumes this)
# ============================================================================

@dataclass
class DoorPlan:
    """The plan for ONE door (a corridor cross-section). Phase C lays tracks
    through this door consuming this plan. SCHEMA — see GlobalPlan.schema_doc()."""
    door_id: str
    capacity: int                       # SUPPLY = Door.capacity_tracks
    ordered_nets: List[str]             # nets through this door, ORDERED (topology)
    net_layers: Dict[str, int]          # {net_id: layer_index} at this door
    net_via_slots: Dict[str, List[str]] # {net_id: [via_slot_id,...]} traversed
    demand: int                         # len(ordered_nets)
    headroom_capacity: float            # FOS_ROUTING_CAPACITY x capacity
    headroom_ok: bool                   # demand <= headroom_capacity (§5c FoS)


@dataclass
class GlobalPlan:
    """The structured GLOBAL PLAN Phase B emits and Phase C consumes (Step 6).

    SCHEMA (authoritative; also returned as a plain dict by `to_dict()`):
      verdict          : engine verdict — ROUTABLE | INFEASIBLE | NEEDS-HDI |
                         NEEDS-PLACEMENT-CHANGE  (Phase A vocabulary)
      feasible         : bool — Phase A HARD-feasibility gate (max-flow == #nets)
      doors            : {door_id: DoorPlan}  (per-door ordered plan)
      net_to_door      : {net_id: door_id}   (the global assignment witness)
      net_layers       : {net_id: layer_index} (layer_assign coloring)
      via_assignment   : {net_id: [via_slot_id, ...]} (via-slot pre-assignment)
      headroom_exceeded: bool — ANY door over the §5c FoS headroom (tight, no
                         margin). NOT a refusal — a feasible plan with this flag
                         set is the honest "routable but tight" report.
      greedy           : {greedy_routes, global_routes, stranded_nets,
                          greedy_assignment} — the greedy-vs-global proof (T3/T4)
      escape_ledger    : {ic_side: {...}} per-IC-side via demand/supply (T9-style)
      routed_nets      : int — nets the FEASIBLE GLOBAL plan routes (== #nets when
                         feasible) — the harness's T3/T4 scored metric
      vias_required    : int — total layer-change vias the plan inserts (T5 metric)
      rationale        : human-readable provenance of the verdict
    """
    verdict: str
    feasible: bool
    doors: Dict[str, DoorPlan] = field(default_factory=dict)
    net_to_door: Dict[str, str] = field(default_factory=dict)
    net_layers: Dict[str, int] = field(default_factory=dict)
    via_assignment: Dict[str, List[str]] = field(default_factory=dict)
    headroom_exceeded: bool = False
    greedy: dict = field(default_factory=dict)
    escape_ledger: dict = field(default_factory=dict)
    routed_nets: int = 0
    vias_required: int = 0
    rationale: str = ""

    @staticmethod
    def schema_doc() -> str:
        """The plan schema, in prose, for Phase C implementers (single source)."""
        return (
            "GlobalPlan (Phase B -> Phase C contract):\n"
            "  verdict: str   feasible: bool   headroom_exceeded: bool\n"
            "  net_to_door: {net_id -> door_id}   (global assignment witness)\n"
            "  net_layers:  {net_id -> layer_index}\n"
            "  via_assignment: {net_id -> [via_slot_id,...]}\n"
            "  routed_nets: int   vias_required: int\n"
            "  greedy: {greedy_routes, global_routes, stranded_nets, "
            "greedy_assignment}\n"
            "  escape_ledger: {ic_side -> {demand, supply_std, supply_hdi, "
            "overflow_std, overflow_hdi, headroom_*}}\n"
            "  doors: {door_id -> DoorPlan}\n"
            "    DoorPlan: door_id, capacity, ordered_nets[], net_layers{}, \n"
            "      net_via_slots{net_id->[slot,...]}, demand, headroom_capacity, \n"
            "      headroom_ok\n"
            "  Phase C fills each door's ordered_nets, on net_layers, traversing \n"
            "  net_via_slots, with bounded A* INSIDE the door's certified region.")

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "feasible": self.feasible,
            "headroom_exceeded": self.headroom_exceeded,
            "net_to_door": dict(self.net_to_door),
            "net_layers": dict(self.net_layers),
            "via_assignment": {k: list(v) for k, v in self.via_assignment.items()},
            "routed_nets": self.routed_nets,
            "vias_required": self.vias_required,
            "greedy": dict(self.greedy),
            "escape_ledger": dict(self.escape_ledger),
            "rationale": self.rationale,
            "doors": {
                did: {
                    "door_id": dp.door_id,
                    "capacity": dp.capacity,
                    "ordered_nets": list(dp.ordered_nets),
                    "net_layers": dict(dp.net_layers),
                    "net_via_slots": {k: list(v)
                                      for k, v in dp.net_via_slots.items()},
                    "demand": dp.demand,
                    "headroom_capacity": dp.headroom_capacity,
                    "headroom_ok": dp.headroom_ok,
                }
                for did, dp in self.doors.items()
            },
        }


# ============================================================================
# 5. GREEDY-VS-GLOBAL (reuse phase_a's greedy-strand detection — T3/T4 proof)
# ============================================================================

def greedy_vs_global(problem, net_feasible: Dict[str, Tuple[str, ...]],
                     door_cap: Dict[str, int], global_routes: int) -> dict:
    """Demonstrate the GLOBAL plan beats the naive GREEDY (the proof the global
    phase is necessary — T3/T4 / the CH1 24/30 trap). Reuse phase_a's greedy
    simulator + its least-constrained-first ordering + nearest-door cost (the
    precise v1->v8 cooperative-router failure mode). Returns the greedy block the
    plan + harness consume."""
    net_ids = [n.net_id for n in problem.nets]
    # Same ordering anti-pattern Phase A uses: least-constrained (most doors)
    # first, so a loose net grabs the scarce shared resource a constrained net
    # is the only one able to use. Tie-break by input order (reproducible).
    greedy_order = sorted(
        net_ids,
        key=lambda nid: (-len(net_feasible.get(nid, ())), net_ids.index(nid)))
    net_door_cost = PA._net_door_costs(problem)
    greedy_routes, greedy_assign, stranded = PA.greedy_assignment(
        net_ids, net_feasible, door_cap,
        net_door_cost=net_door_cost, net_order=greedy_order)
    return {
        "greedy_routes": greedy_routes,
        "global_routes": global_routes,
        "stranded_nets": stranded,
        "greedy_assignment": greedy_assign,
        "greedy_order": greedy_order,
    }


# ============================================================================
# 6. THE PLANNER — compose everything into a GlobalPlan
# ============================================================================

def _build_door_plans(problem, graph, net_to_door, net_layers,
                      via_assignment) -> Tuple[Dict[str, DoorPlan], bool]:
    """Group the global assignment by door, ORDER the nets through each door
    (topology-before-geometry, reuse channel.py), attach per-net layers + via
    slots, and compute the §5c FoS headroom flag per door. Returns
    (door_plans, headroom_exceeded)."""
    cap = {d.id: d.capacity_tracks for d in problem.doors}
    nets_at: Dict[str, List[str]] = {d.id: [] for d in problem.doors}
    for nid, did in net_to_door.items():
        if did in nets_at:
            nets_at[did].append(nid)
    door_plans: Dict[str, DoorPlan] = {}
    headroom_exceeded = False
    for did, members in nets_at.items():
        ordered = order_nets_through_door(problem, members)
        capacity = cap.get(did, 0)
        demand = len(ordered)
        headroom_capacity = FOS_ROUTING_CAPACITY * capacity
        headroom_ok = demand <= headroom_capacity + 1e-9
        if not headroom_ok:
            headroom_exceeded = True
        door_plans[did] = DoorPlan(
            door_id=did,
            capacity=capacity,
            ordered_nets=ordered,
            net_layers={n: net_layers.get(n, 0) for n in ordered},
            net_via_slots={n: list(via_assignment.get(n, [])) for n in ordered},
            demand=demand,
            headroom_capacity=headroom_capacity,
            headroom_ok=headroom_ok,
        )
    return door_plans, headroom_exceeded


def plan(problem) -> GlobalPlan:
    """Build the GLOBAL PLAN by COMPOSING the merged modules.

    Pipeline (each step reuses an already-validated module — no re-implementation):
      1. build_routing_graph(problem)              — the generic graph (this file)
      2. Phase A feasible_assignment (max-flow)    — HARD feasibility GATE + the
         global net->door assignment witness (phase_a.py)
      3. escape_ledger (phase_a.py)                — per-IC-side via demand/supply
      4. _decide_verdict (phase_a.py)              — engine verdict from the ledger
      5. layer_assignment (layer_assign.py)        — per-net layers (SURESHOT)
      6. preassign_via_slots (this file, max-flow) — via-slot pre-assignment
      7. order_nets_through_door (channel.py)      — net ordering (topology)
      8. greedy_vs_global (phase_a.py)             — the necessity proof (T3/T4)
      9. FoS headroom flag per door (§5c)          — tight-plan honest report

    Returns a GlobalPlan. Hard-feasibility (Phase A) is the GATE; headroom is a
    PREFERENCE flag — a hard-feasible boundary plan (T3/T4) is emitted with
    headroom_exceeded=True, never refused.
    """
    graph = build_routing_graph(problem)
    net_ids = [n.net_id for n in problem.nets]
    door_cap = {d.id: d.capacity_tracks for d in problem.doors}

    # ---- 2. Phase A HARD feasibility + global assignment witness ----------
    if problem.doors:
        feas = PA.feasible_assignment(net_ids, graph.net_feasible, door_cap)
        net_to_door = dict(feas["assignment"])
        feasible = feas["feasible"]
        global_routes = feas["matched"]
    else:
        feas = None
        net_to_door = {}
        feasible = True
        global_routes = len(net_ids)

    # ---- 3 + 4. escape ledger + engine verdict (Phase A) ------------------
    esc = PA.escape_ledger(problem)
    if problem.doors:
        greedy_block = greedy_vs_global(problem, graph.net_feasible, door_cap,
                                        global_routes)
        greedy_routes = greedy_block["greedy_routes"]
        stranded = greedy_block["stranded_nets"]
    else:
        greedy_block = {"greedy_routes": global_routes,
                        "global_routes": global_routes, "stranded_nets": [],
                        "greedy_assignment": {}, "greedy_order": list(net_ids)}
        greedy_routes = global_routes
        stranded = []
    verdict, routed_nets, overflow_std, rationale = PA._decide_verdict(
        problem, feas, esc, global_routes, greedy_routes, stranded)

    # ---- 5. layer assignment (SURESHOT coloring) --------------------------
    net_layers, la = assign_layers(problem)

    # ---- 6. via-slot pre-assignment (escape max-flow + layer-hop vias) ----
    via_assignment = preassign_via_slots(graph, problem, net_to_door)
    vias_required = sum(len(v) for v in via_assignment.values()) \
        if problem.via_slots else LA.vias_required(problem, net_layers)

    # ---- 7 + 9. per-door ordered plan + FoS headroom flag -----------------
    door_plans, headroom_exceeded = _build_door_plans(
        problem, graph, net_to_door, net_layers, via_assignment)

    return GlobalPlan(
        verdict=verdict,
        feasible=feasible,
        doors=door_plans,
        net_to_door=net_to_door,
        net_layers=net_layers,
        via_assignment=via_assignment,
        headroom_exceeded=headroom_exceeded,
        greedy=greedy_block,
        escape_ledger={k: vars(v) for k, v in esc.items()},
        routed_nets=routed_nets,
        vias_required=vias_required,
        rationale=rationale,
    )


# ============================================================================
# 7. THE SOLVER (run_suite.py pluggable contract: solve(problem) -> dict)
# ============================================================================

def solve(problem):
    """Phase B global planner. Builds the GLOBAL PLAN by composing Phase A
    (capacity) + channel (ordering) + layer_assign (layers/vias), and emits the
    harness-scored dict + the plan as evidence.

    Dispatch is STRUCTURAL (not by reading the answer):
      * has doors, no plane-split (T3/T4) — door-based feasibility:
          verdict = the plan's engine verdict (ROUTABLE: a feasible GLOBAL
          assignment exists, Phase A gate). routed_nets == global_routes (the plan
          routes ALL nets). greedy block PROVES the strand (greedy < global,
          stranded non-empty). Satisfies the harness _accepted_verdicts +
          _special_checks for T3/T4 GENUINELY.
      * no doors (T5) — crossing / single-layer ordering:
          the planner orders the 2 crossing nets and the layer_assign step inserts
          the 1 via. verdict = INFEASIBLE (single-layer base), vias_required = 1.

    Returns the harness-recognised keys + a 'global_plan' block (the OUTPUT Phase C
    consumes) + the per-door ordered plan + greedy-vs-global. Nothing hardcoded —
    every number flows from the composed modules via the generic graph.
    """
    fx = problem

    # ---- T5-style: no doors, a crossing => single-layer ordering case ----
    # When there are NO doors (no corridor supply structure) the global plan is
    # degenerate at the door level; the binding decision is layer-assignment net
    # ordering + the via that resolves the crossing. Delegate the layer/via verdict
    # to layer_assign (the merged module) and surface the ORDERED nets the planner
    # would pass through the implicit single door.
    if not fx.doors and not fx.via_slots:
        la_res = LA.solve(fx)            # layer assignment / crossing verdict
        net_ids = [n.net_id for n in fx.nets]
        ordered = order_nets_through_door(fx, net_ids)  # topology order (channel)
        out = dict(la_res)               # carries verdict + vias_required (T5)
        out["ordered_nets"] = ordered
        out["global_plan"] = {
            "verdict": la_res.get("verdict"),
            "ordered_nets": ordered,
            "net_layers": LA.layer_assignment(fx)["coloring"],
            "vias_required": la_res.get("vias_required"),
            "note": ("no doors: single-layer ordering case (T5). The planner "
                     "orders the crossing nets; layer_assign inserts the via."),
        }
        out["rationale"] = (
            "Phase B (no-door case): order the crossing nets through the implicit "
            "door (topology-before-geometry, channel.left_edge order = "
            f"{ordered}); layer_assign resolves the crossing with "
            f"{la_res.get('vias_required')} via(s). " + la_res.get("rationale", ""))
        return out

    # ---- T3/T4-style: door-based global plan ----------------------------
    gp = plan(fx)

    return {
        # harness-scored keys -------------------------------------------------
        "verdict": gp.verdict,
        "routed_nets": gp.routed_nets,        # == global_routes (plan routes all)
        "overflow": _door_overflow_total(fx, gp),
        # greedy proof (T3/T4 _special_checks) --------------------------------
        "greedy": {
            "greedy_routes": gp.greedy.get("greedy_routes"),
            "global_routes": gp.greedy.get("global_routes"),
            "stranded_nets": gp.greedy.get("stranded_nets", []),
            "greedy_assignment": gp.greedy.get("greedy_assignment", {}),
        },
        # the GLOBAL PLAN OUTPUT (Phase C consumes this) ----------------------
        "global_plan": gp.to_dict(),
        "headroom_exceeded": gp.headroom_exceeded,
        "escape_ledger": gp.escape_ledger,
        "fos": FOS_ROUTING_CAPACITY,
        "rationale": gp.rationale,
    }


def _door_overflow_total(problem, gp: GlobalPlan) -> int:
    """Total hard overflow across doors in the plan (0 for a feasible plan)."""
    cap = {d.id: d.capacity_tracks for d in problem.doors}
    total = 0
    for did, dp in gp.doors.items():
        total += max(0, dp.demand - cap.get(did, 0))
    return total


# ============================================================================
# Human-readable plan printer (PR evidence / --explain)
# ============================================================================

def format_plan(name, problem, gp: GlobalPlan) -> str:
    lines = [f"=== Phase B GLOBAL PLAN — {name} ==="]
    lines.append(f"VERDICT: {gp.verdict}   feasible={gp.feasible}   "
                 f"headroom_exceeded={gp.headroom_exceeded}")
    lines.append(f"  rationale: {gp.rationale}")
    lines.append(f"  net_to_door (global assignment): {gp.net_to_door}")
    lines.append(f"  net_layers: {gp.net_layers}")
    if any(gp.via_assignment.values()):
        lines.append(f"  via_assignment: "
                     f"{ {k: v for k, v in gp.via_assignment.items() if v} }")
    g = gp.greedy
    lines.append(f"  GREEDY-VS-GLOBAL: greedy {g.get('greedy_routes')} vs global "
                 f"{g.get('global_routes')}; stranded={g.get('stranded_nets')} "
                 f"(greedy order {g.get('greedy_order')})")
    lines.append("  DOORS (door: cap | ordered nets | layers | via slots | "
                 f"FoS {FOS_ROUTING_CAPACITY}x headroom):")
    for did, dp in gp.doors.items():
        hr = "OK" if dp.headroom_ok else "TIGHT(no margin)"
        lines.append(f"    {did}: cap={dp.capacity} demand={dp.demand} "
                     f"[{hr}<= {dp.headroom_capacity:.2f}]")
        lines.append(f"        ordered_nets={dp.ordered_nets}")
        lines.append(f"        net_layers={dp.net_layers}")
        if any(dp.net_via_slots.values()):
            lines.append(f"        net_via_slots="
                         f"{ {k: v for k, v in dp.net_via_slots.items() if v} }")
    if gp.escape_ledger:
        lines.append("  ESCAPE LEDGER (side: demand vs supply):")
        for sid, L in gp.escape_ledger.items():
            lines.append(
                f"    {sid}: demand={L['demand']} std={L['supply_std']} "
                f"+HDI={L['supply_hdi']} overflow_std={L['overflow_std']} "
                f"overflow_hdi={L['overflow_hdi']}")
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

    ap = argparse.ArgumentParser(
        description="Engine Step 5 — Phase B generic-graph global planner")
    ap.add_argument("--cases", default="T3,T4,T5",
                    help="comma-separated case names (default T3,T4,T5)")
    ap.add_argument("--schema", action="store_true",
                    help="print the GlobalPlan schema (Phase C contract) and exit")
    args = ap.parse_args()
    if args.schema:
        print(GlobalPlan.schema_doc())
        raise SystemExit(0)
    want = [c.strip() for c in args.cases.split(",") if c.strip()]
    for fx in Fx.all_fixtures():
        if fx.name not in want:
            continue
        prob = fx.problem_view() if hasattr(fx, "problem_view") else fx
        if not prob.doors and not prob.via_slots:
            # T5-style: print the no-door planner output via solve().
            res = solve(prob)
            print(f"=== Phase B GLOBAL PLAN — {fx.name} (no-door / ordering) ===")
            print(f"VERDICT: {res['verdict']}   "
                  f"vias_required={res.get('vias_required')}")
            print(f"  ordered_nets={res.get('ordered_nets')}")
            print(f"  rationale: {res.get('rationale')}")
        else:
            gp = plan(prob)
            print(format_plan(fx.name, prob, gp))
        print()
