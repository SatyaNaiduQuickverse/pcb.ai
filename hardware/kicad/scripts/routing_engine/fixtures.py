#!/usr/bin/env python3
"""fixtures.py — the fixture FORMAT + the 9 T1-T9 ground-truth fixtures.

Engine Step 0 of docs/ROUTING_ENGINE_DESIGN_2026-05-28.md §2/§3.

WHAT THIS IS
------------
A LIGHTWEIGHT, ABSTRACT board-state representation (NOT full .kicad_pcb files).
The design doc explicitly allows a "board-state fixture" and Phases A/B of the
engine operate on the abstract resource/topology graph, not on geometry. Keeping
the fixtures abstract makes them (a) Pi-light, (b) solver-agnostic, and most
importantly (c) PROVABLE BY HAND — every ground-truth verdict here is closed-form
combinatorics (interval density = max overlap, VCG cycle detection, demand-vs-
supply counting, nested-interval planarity) that a human can re-derive from the
fixture fields alone, with no solver and no KiCad/pcbnew dependency.

This is the validation FOUNDATION: these fixtures DEFINE ground truth, so they
must be provably correct independent of any solver. `run_suite.py --self-check`
re-derives every verdict from first principles and asserts it matches the stored
`ground_truth`. NO engine algorithm code is in this package yet.

ABSTRACTIONS (shared with the real board so fixtures transfer — BOARD_INVARIANTS.md)
-----------------------------------------------------------------------------------
- LAYERS mirror the 10L stackup model where relevant: signal layers route nets;
  plane layers (GND / +VMOTOR) are reference and split-able (return-path).
  Real board (BOARD_INVARIANTS.md §Board geometry):
    F.Cu / In1=GND / In2=sig / In3=GND / In4=sig-BEMF / In5=+VMOTOR /
    In6=sig-SW / In7=GND / In8=sig / B.Cu  → 6 signal + 4 plane.
  Fixtures use a minimal subset (1-3 signal layers + a plane where the test needs
  it) so the ground truth stays hand-checkable.
- DOORS / corridors mirror BOARD_INVARIANTS.md §Subsystem I/O ports + §Highway
  reservations: {id, coord, width_mm, layers, capacity_tracks, passes}. Capacity
  = boundary_length / track_pitch (ROUTING_METHODOLOGY §0b Phase A item 1).
- VIA_SLOTS mirror the HDI dog-bone fanout band escape model (BOARD_INVARIANTS.md
  §HDI via-in-pad whitelist J18/J19): a finite count of via sites that fit the
  fanout band at via keep-out spacing (Phase A item 2 "via-slot count").
- OBSTACLES: rectangular keep-outs (body keep-outs) and PLANE SPLITS (a gap in a
  reference plane → return-path discontinuity, a HARD SI constraint per §0b /
  ROUTING_METHODOLOGY §9).

GROUND-TRUTH METRICS PER CASE (provable; cited to the design-doc T-row + standard)
----------------------------------------------------------------------------------
- T1 left-edge optimal track count   = interval-graph chromatic number = local
                                       density = max # intervals overlapping any
                                       vertical cut (Hashimoto-Stevens 1971;
                                       Sherwani Ch.7 channel density).
- T2 min doglegs                     = # of edges that must break to make the VCG
                                       acyclic (here a forced 2-cycle → 1 dogleg;
                                       Deutsch 1976 doglegging).
- T3/T4 "global beats greedy"        = a witness GLOBAL assignment routes 100%
                                       while documented GREEDY order strands a net
                                       (miniature of the CH1 24/30 escape trap;
                                       Sherwani: maze routing is order-dependent).
- T5 via count + feasible net order  = single-layer infeasible iff the two nets
                                       cross (HCG/VCG conflict); 1 via + 1 layer
                                       hop removes the crossing.
- T6 plane-continuity hard constraint= shortest path crosses a split (REJECT);
                                       longer continuous-reference path is the
                                       answer (Ott; Howard Johnson return-path).
- T7 length-match groups + skew tol  = all bus members equalised to within the
                                       skew tolerance, meander spacing >= width
                                       (no self-coupling) (Howard Johnson skew).
- T8 river min-area, 0 vias          = nested-interval order identical on both
                                       boundaries → planar single-layer, provably
                                       minimum area (Sherwani river routing).
- T9 demand-vs-supply ledger         = demand = supply+1 with no HDI → overflow=1
                                       → INFEASIBLE; HDI adds via slots → supply
                                       rises → ROUTABLE (Phase A escalation; T9
                                       honesty test).

Each fixture carries:
  - pins, nets, doors, obstacles, layers, via_slots  (the demand + supply)
  - ground_truth  (verdict + the provable optimal metric + encoded WITNESS where
                   a ROUTABLE/CONDITIONAL claim needs a constructive proof)
  - construction_proof  (the math, in prose, re-derivable by hand)

Pure Python + stdlib. No KiCad/pcbnew. No solver. No engine algorithm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ----------------------------------------------------------------------------
# FIXTURE FORMAT (dataclasses)
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Pin:
    """A terminal / pad. (id, x_mm, y_mm, layer)."""
    id: str
    x_mm: float
    y_mm: float
    layer: str  # signal-layer name, e.g. "F.Cu", "In2", "B.Cu"


@dataclass(frozen=True)
class Net:
    """A connectivity demand. net_class names the LAYER_PREF/constraint family
    (BEMF / PWM / control / power / bus / critical) — mirrors MASTER_COOP_ROUTER
    v5 LAYER_PREF + ROUTING_METHODOLOGY §3 per-class constraints.

    `feasible_doors` = the set of door ids this net can physically use, given its
    pin placement + keep-outs. This is a DECLARED part of the demand structure
    (it IS the construction — e.g. T3's most-constrained net Y can only reach the
    short slot; T4's mandatory nets each reach exactly one door). The self-check
    does NOT trust the verdict directly: it COUNTS demand-vs-supply over these
    declared reachabilities to PROVE the routable/infeasible/greedy-trap verdict.
    Empty/None = unconstrained (any door)."""
    net_id: str
    pin_ids: tuple  # ordered tuple of Pin.id this net must connect
    net_class: str = "signal"
    feasible_doors: tuple = ()  # door ids this net can use ('' => any)
    # length-match group + skew tolerance (T7); None when not length-matched.
    match_group: Optional[str] = None
    skew_tol_mm: Optional[float] = None


@dataclass(frozen=True)
class Door:
    """A corridor cross-section = the SUPPLY (BOARD_INVARIANTS §Subsystem I/O
    ports + §Highway reservations; ROUTING_METHODOLOGY §0b Phase B 'DOORS are
    first-class objects').

    capacity_tracks = boundary_length / track_pitch  (Phase A item 1). We store
    it precomputed so the ground truth is a pure integer the self-check can count
    against; `capacity_from_width()` documents the derivation.
    """
    id: str
    x_mm: float
    y_mm: float
    width_mm: float
    layers: tuple            # which signal layers this door spans
    capacity_tracks: int     # SUPPLY: # of tracks that physically fit (per layer-set)
    passes: tuple = ()       # optional: net_ids/groups this door is reserved for

    @staticmethod
    def capacity_from_width(width_mm: float, track_pitch_mm: float,
                            n_layers: int = 1) -> int:
        """Phase A capacity = floor(width / pitch) per layer × n_layers.
        track_pitch = trace_width + clearance (ROUTING_METHODOLOGY §0b item 1)."""
        return int(width_mm // track_pitch_mm) * n_layers


@dataclass(frozen=True)
class ViaSlot:
    """An escape via site (HDI dog-bone fanout band model — BOARD_INVARIANTS
    §HDI via-in-pad whitelist). `hdi_only=True` slots exist ONLY when HDI
    via-in-pad is enabled (the T9 escalation lever)."""
    id: str
    x_mm: float
    y_mm: float
    ic_side: str             # which fine-pitch IC side this slot serves
    hdi_only: bool = False   # True => available only with HDI enabled


@dataclass(frozen=True)
class Obstacle:
    """A rectangular keep-out. kind='body' = component body keep-out;
    kind='plane_split' = a GAP in the named reference plane (return-path
    discontinuity — HARD constraint, ROUTING_METHODOLOGY §9 / §0b)."""
    id: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    kind: str = "body"       # 'body' | 'plane_split'
    plane: Optional[str] = None  # for plane_split: which reference plane is cut


@dataclass(frozen=True)
class Layer:
    """A stackup layer. role='signal' routes nets; role='plane' is reference/PDN
    (GND or +VMOTOR) — mirrors BOARD_INVARIANTS 10L model."""
    name: str
    role: str                # 'signal' | 'plane'
    plane_net: Optional[str] = None  # for plane layers: GND / +VMOTOR


@dataclass(frozen=True)
class GroundTruth:
    """The PROVABLE answer. `verdict` in {ROUTABLE, INFEASIBLE, CONDITIONAL}.

    CONDITIONAL = the verdict flips on a named lever (net ORDER for T5, GLOBAL-vs-
    GREEDY for T3/T4, HDI for T9). `conditional_on` names the lever and
    `alt_verdict` is the verdict once the lever is applied.

    `metrics` holds the case's provable optimal numbers (the design-doc
    pass-criterion metric). `witness` encodes a known feasible solution for
    ROUTABLE/CONDITIONAL claims so --self-check can assert a solution EXISTS at
    the claimed optimum without running any solver.
    """
    verdict: str
    metrics: dict
    witness: dict = field(default_factory=dict)
    conditional_on: Optional[str] = None
    alt_verdict: Optional[str] = None
    alt_metrics: dict = field(default_factory=dict)
    alt_witness: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Problem:
    """INPUT-ONLY view of a Fixture handed to a solver.

    Anti-drift "structural, not discipline" fix (`[[feedback-systemic-rule-
    enforcement]]`): a solver receives ONLY the problem inputs
    (name/layers/pins/nets/doors/obstacles/via_slots) and the geometry helpers
    (`pin`, `signal_layers`, `plane_layers`). It has NO `ground_truth`, NO
    `witness`, NO `alt_*` attribute — so it is STRUCTURALLY IMPOSSIBLE for a
    solver to read the answer it is being scored against (verified by
    `run_suite.assert_problem_view_has_no_answer`). The harness builds this from
    a Fixture via `Fixture.problem_view()` and passes it to `solve()`.
    """
    name: str
    layers: tuple
    pins: tuple
    nets: tuple
    doors: tuple
    obstacles: tuple
    via_slots: tuple

    def signal_layers(self):
        return [l for l in self.layers if l.role == "signal"]

    def plane_layers(self):
        return [l for l in self.layers if l.role == "plane"]

    def pin(self, pid):
        for p in self.pins:
            if p.id == pid:
                return p
        raise KeyError(f"{self.name}: no pin {pid}")


@dataclass(frozen=True)
class Fixture:
    """One T-case board-state fixture."""
    name: str                # e.g. "T1"
    title: str
    difficulty: str          # moderate / medium / hard / stretch
    tests: str               # what engine capability this gates (design §3)
    layers: tuple            # tuple[Layer]
    pins: tuple              # tuple[Pin]
    nets: tuple              # tuple[Net]
    doors: tuple             # tuple[Door]
    obstacles: tuple         # tuple[Obstacle]
    via_slots: tuple         # tuple[ViaSlot]
    ground_truth: GroundTruth
    construction_proof: str

    def signal_layers(self):
        return [l for l in self.layers if l.role == "signal"]

    def plane_layers(self):
        return [l for l in self.layers if l.role == "plane"]

    def pin(self, pid):
        for p in self.pins:
            if p.id == pid:
                return p
        raise KeyError(f"{self.name}: no pin {pid}")

    def problem_view(self):
        """Return the INPUT-ONLY `Problem` (no ground_truth/witness/alt_*). This
        is what `run_suite.run_solver` hands a solver, so the solver cannot read
        the answer (anti-drift structural fix)."""
        return Problem(
            name=self.name,
            layers=self.layers,
            pins=self.pins,
            nets=self.nets,
            doors=self.doors,
            obstacles=self.obstacles,
            via_slots=self.via_slots,
        )


# ----------------------------------------------------------------------------
# Helper: classic interval-graph local density (Hashimoto-Stevens / Sherwani).
# density(intervals) = max over all cut positions of the # of intervals covering
# that position. For a channel, the optimal (left-edge) track count on an ACYCLIC
# VCG equals this density. Used by both fixtures (to set ground truth) and
# self-check (to re-derive it) — single source of the math.
# ----------------------------------------------------------------------------

def interval_density(intervals):
    """intervals: list of (lo, hi). Returns max overlap count = channel density.

    Proof of correctness: at any vertical cut x, every net whose horizontal span
    [lo,hi] covers x must occupy a distinct track at x (two nets on one track
    would short). So tracks >= overlap(x) for every x, hence tracks >= max
    overlap. On an acyclic VCG left-edge achieves exactly this bound (Hashimoto-
    Stevens 1971). Endpoints are events; we sweep them.
    """
    if not intervals:
        return 0
    events = []
    for lo, hi in intervals:
        a, b = (lo, hi) if lo <= hi else (hi, lo)
        events.append((a, +1))
        events.append((b, -1))
    # Sort so that at a shared coordinate, ENTERS (+1) are processed before
    # EXITS (-1): a net entering and another exiting at the same x DO overlap at
    # that point (they share the cut), so we count them together.
    events.sort(key=lambda e: (e[0], -e[1]))
    cur = best = 0
    for _, d in events:
        cur += d
        best = max(best, cur)
    return best


def has_cycle(n_nodes, edges):
    """Directed-graph cycle detection (DFS 3-color). edges: list of (u, v).
    Used for VCG acyclicity (T1/T2). A VCG edge A->B means net A's terminal is
    ABOVE net B's at a shared column, so A must occupy a higher track => A above
    B in the track order. A cycle => no consistent track order => infeasible
    dogleg-free (Sherwani Ch.7; Deutsch 1976)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {i: WHITE for i in range(n_nodes)}
    adj = {i: [] for i in range(n_nodes)}
    for u, v in edges:
        adj[u].append(v)

    def dfs(u):
        color[u] = GRAY
        for w in adj[u]:
            if color[w] == GRAY:
                return True
            if color[w] == WHITE and dfs(w):
                return True
        color[u] = BLACK
        return False

    return any(color[i] == WHITE and dfs(i) for i in range(n_nodes))


def is_nested_river_order(top_order, bot_order):
    """River-routing planarity test (Sherwani Ch.7). Returns True iff the nets
    appear in the SAME left-to-right order on both channel boundaries — the exact
    condition for a planar, crossing-free, single-layer river route. (When the
    orders match, the nets form a set of non-crossing 'rivers'; minimum area is
    achieved by routing each at unit spacing.)"""
    return list(top_order) == list(bot_order)


# ----------------------------------------------------------------------------
# THE 9 FIXTURES
# Each `_build_TN()` returns a Fixture. Numbers are chosen so every fixture sits
# at a real feasibility boundary (demand == supply, or supply+1) per design §2.
# ----------------------------------------------------------------------------

# Shared canonical track pitch (trace 0.15 + clearance 0.15 = 0.30 mm). This is a
# representative fine-signal pitch; the exact value only scales coordinates, the
# COUNTS (which the ground truth uses) are what matter.
PITCH = 0.30


def _build_T1():
    """T1 — baseline-routable channel (moderate). Acyclic VCG, density == supply.

    Construction: a 2-layer horizontal channel. 6 horizontal nets span the
    channel; their vertical-span overlaps give a local density of 3 (three nets
    cover the middle column). The VCG is acyclic (terminals nest, no A-above-B
    AND B-above-A). Door supply = 3 tracks. density(3) == supply(3) => exactly
    at the boundary, ROUTABLE, optimal track count = 3.
    """
    layers = (
        Layer("F.Cu", "signal"),
        Layer("In1", "plane", "GND"),
        Layer("In2", "signal"),
    )
    # Place 6 nets as horizontal intervals on F.Cu. Column overlaps engineered so
    # density = 3 (nets n2,n3,n4 all cover x in [4,5]).
    spans = {
        "n1": (0.0, 3.0),
        "n2": (2.0, 8.0),
        "n3": (3.0, 9.0),
        "n4": (4.0, 10.0),
        "n5": (9.0, 12.0),
        "n6": (11.0, 14.0),
    }
    pins, nets = [], []
    for nid, (lo, hi) in spans.items():
        pins.append(Pin(f"{nid}_L", lo, 5.0, "F.Cu"))
        pins.append(Pin(f"{nid}_R", hi, 5.0, "F.Cu"))
        nets.append(Net(nid, (f"{nid}_L", f"{nid}_R"), "signal"))
    # The west door the channel feeds: 1.0 mm wide on F.Cu => floor(1.0/0.30)=3.
    door = Door("D_west", 0.0, 5.0, 1.0, ("F.Cu",),
                Door.capacity_from_width(1.0, PITCH, 1))
    density = interval_density(list(spans.values()))  # == 3
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "optimal_track_count": density,      # left-edge optimum = density
            "channel_density": density,
            "door_capacity": door.capacity_tracks,
            "vcg_acyclic": True,
            "vias_required": 0,
        },
        # Witness: a valid track assignment (track index per net) that uses
        # exactly `density` tracks with no two overlapping nets on one track.
        witness={"track_of": _left_edge_assign(spans)},
    )
    proof = (
        "T1 (design §2 row T1; Hashimoto-Stevens 1971; Sherwani Ch.7 channel "
        "density). Spans n2,n3,n4 all cover column x in [4,5] => local density 3. "
        "No column is covered by 4 nets. The VCG is acyclic (intervals do not "
        "form a both-directions vertical conflict). On an acyclic VCG the left-"
        "edge algorithm achieves track count == density == 3, optimal and equal "
        "to door supply 3 (boundary case). Witness track assignment encoded; "
        "self-check verifies no two same-track nets overlap and #tracks == 3."
    )
    return Fixture("T1", "baseline-routable channel", "moderate",
                   "detailed channel fill / left-edge; regression sanity floor",
                   layers, tuple(pins), tuple(nets), (door,), (), (), gt, proof)


def _left_edge_assign(spans):
    """Greedy left-edge track assignment (used only to MANUFACTURE a witness for
    acyclic channels). Returns {net_id: track_index}. This is NOT engine code —
    it is a fixture-construction helper that produces a provably-valid witness
    that the solver-agnostic self-check then independently re-validates."""
    order = sorted(spans.items(), key=lambda kv: kv[1][0])  # by left endpoint
    tracks = []  # tracks[t] = current right edge occupied
    assign = {}
    for nid, (lo, hi) in order:
        placed = False
        for t, right in enumerate(tracks):
            if lo > right:  # strictly past => no overlap at the shared column
                assign[nid] = t
                tracks[t] = hi
                placed = True
                break
        if not placed:
            assign[nid] = len(tracks)
            tracks.append(hi)
    return assign


def _build_T2():
    """T2 — cyclic VCG / layer-assignment (medium). Forced 2-cycle.

    Construction: TWO nets in one channel whose terminals are arranged so the VCG
    has A->B (at column c1, A's pin is above B's) AND B->A (at column c2, B's pin
    is above A's). That 2-cycle makes a single-track-order impossible =>
    INFEASIBLE dogleg-free. Splitting ONE net with one dogleg (a jog to a 2nd
    track / a via) breaks the cycle => ROUTABLE with exactly 1 dogleg.
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    # Net A has pins: top-left + bottom-right.  Net B: bottom-left + top-right.
    # Column c1 (left): A_top above B_bot => A above B  (A->B).
    # Column c2 (right): B_top above A_bot => B above A  (B->A).  => 2-cycle.
    pins = [
        Pin("A_L", 1.0, 8.0, "F.Cu"), Pin("A_R", 9.0, 2.0, "F.Cu"),
        Pin("B_L", 1.0, 2.0, "F.Cu"), Pin("B_R", 9.0, 8.0, "F.Cu"),
    ]
    nets = [Net("A", ("A_L", "A_R"), "signal"),
            Net("B", ("B_L", "B_R"), "signal")]
    # VCG edges by construction (node 0=A, 1=B): A->B and B->A.
    vcg_edges = [(0, 1), (1, 0)]
    cyclic = has_cycle(2, vcg_edges)  # True
    door = Door("D_west", 0.0, 5.0, 1.0, ("F.Cu",),
                Door.capacity_from_width(1.0, PITCH, 1))
    gt = GroundTruth(
        verdict="INFEASIBLE",
        metrics={
            "vcg_cyclic": cyclic,
            "cycle": ["A", "B", "A"],
            "min_doglegs_dogleg_free": None,  # impossible without a dogleg
            "feasible_dogleg_free": False,
        },
        conditional_on="dogleg",
        alt_verdict="ROUTABLE",
        alt_metrics={"min_doglegs": 1, "vias_or_jogs_required": 1,
                     "vcg_cyclic_after": False},
        # Witness for the dogleg resolution: break net A into two segments joined
        # by 1 jog/via; the broken VCG (A_seg2 no longer conflicts) is acyclic.
        alt_witness={"break_net": "A", "doglegs": 1,
                     "vcg_edges_after": [(1, 0)]},  # only B->A remains => acyclic
    )
    proof = (
        "T2 (design §2 row T2; Deutsch 1976 doglegging; Sherwani Ch.7 VCG). "
        "By construction the VCG has A->B (left column: A pin above B pin) and "
        "B->A (right column: B pin above A pin) => a directed 2-cycle. A cycle in "
        "the VCG => no consistent top-to-bottom track order => INFEASIBLE without "
        "doglegs (proved by has_cycle on the 2-cycle). Breaking exactly ONE net "
        "with ONE dogleg/via removes one of the two conflict edges, leaving a "
        "single edge B->A which is acyclic => ROUTABLE with min_doglegs == 1. "
        "Self-check asserts has_cycle(before)==True and has_cycle(after)==False "
        "with exactly 1 break."
    )
    return Fixture("T2", "cyclic VCG / layer-assignment", "medium",
                   "VCG cycle detection + minimal dogleg insertion; "
                   "'report infeasible, don't thrash'",
                   layers, tuple(pins), tuple(nets), (door,), (), (), gt, proof)


def _build_T3():
    """T3 — saturated escape field (hard). Miniature of the CH1 24/30 bug.

    Construction: a corridor with a SHORT slot (1 track of supply) and a LONG
    detour path. Net X is unconstrained (can take the long detour). Net Y is the
    MOST-CONSTRAINED net: it can ONLY fit through the short slot (its endpoints
    force it). Total corridor supply == exactly enough IFF X detours so Y gets
    the short slot.

    GREEDY shortest-first routes X through the short slot first (cheaper for X),
    consuming the only resource Y needs => Y is STRANDED (reproduces the plateau).
    GLOBAL / most-constrained-first reserves the short slot for Y, sends X the
    long way => 100% routed. So verdict is CONDITIONAL on global-vs-greedy.
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    # Short slot = a 1-track door (the scarce shared resource). Long detour is a
    # separate wide door X can use.
    short_slot = Door("D_short", 5.0, 5.0, 0.30, ("F.Cu",),
                      Door.capacity_from_width(0.30, PITCH, 1))   # capacity 1
    long_detour = Door("D_long", 5.0, 12.0, 1.0, ("F.Cu",),
                       Door.capacity_from_width(1.0, PITCH, 1))    # capacity 3
    pins = [
        # Net Y: endpoints straddle the short slot at y=5; a body keep-out blocks
        # the route up to the long detour => short slot only (declared).
        Pin("Y_L", 0.0, 5.0, "F.Cu"), Pin("Y_R", 10.0, 5.0, "F.Cu"),
        # Net X: endpoints can reach EITHER door (long detour viable).
        Pin("X_L", 0.0, 8.0, "F.Cu"), Pin("X_R", 10.0, 8.0, "F.Cu"),
    ]
    # Demand structure (the construction): Y is the most-constrained net.
    nets = [Net("Y", ("Y_L", "Y_R"), "signal", feasible_doors=("D_short",)),
            Net("X", ("X_L", "X_R"), "signal",
                feasible_doors=("D_short", "D_long"))]
    # The keep-out that walls Y away from the long detour (makes Y short-only).
    body = Obstacle("KO_Y_up", 0.0, 6.0, 10.0, 11.5, kind="body")
    gt = GroundTruth(
        # The board IS routable — but only by the correct (global) decision.
        verdict="CONDITIONAL",
        metrics={
            "short_slot_capacity": short_slot.capacity_tracks,   # 1
            "Y_feasible_doors": ["D_short"],     # Y is most-constrained
            "X_feasible_doors": ["D_short", "D_long"],
            "greedy_shortest_first_routes": 1,   # only X => 1/2 (Y stranded)
            "global_routes": 2,                  # 2/2
        },
        conditional_on="global_vs_greedy",
        alt_verdict="ROUTABLE",                  # under global planning
        alt_metrics={"all_nets_routed": 2, "total_nets": 2},
        # Witness for the GLOBAL solution: Y->short slot, X->long detour.
        witness={"global_assignment": {"Y": "D_short", "X": "D_long"}},
        # And the documented greedy FAILURE (proves the global phase is the fix).
        alt_witness={"greedy_assignment": {"X": "D_short"},
                     "stranded": ["Y"]},
    )
    proof = (
        "T3 (design §2 row T3; the 24/30 escape trap; Sherwani: maze routing is "
        "order-dependent and needs global pre-planning). Y's endpoints admit "
        "ONLY the short slot (capacity 1); X admits the short slot OR the long "
        "detour. Supply is exactly enough IFF X detours. Greedy shortest-first "
        "assigns the cheap short slot to X first => the lone Y-resource is "
        "consumed => Y stranded (1/2). Global most-constrained-first reserves the "
        "short slot for Y (the only net that needs it) and sends X the long way "
        "=> 2/2. Self-check verifies: |Y_feasible_doors|==1, the greedy order "
        "strands Y, and the encoded global assignment routes both with no door "
        "over capacity."
    )
    return Fixture("T3", "saturated escape field (reproduces 24/30 trap)", "hard",
                   "global phase + most-constrained-first ordering",
                   layers, tuple(pins), tuple(nets),
                   (short_slot, long_detour), (body,), (), gt, proof)


def _build_T4():
    """T4 — greedy-trap channel (hard). Locally-cheap first choice blocks a later
    mandatory net; non-greedy global succeeds.

    Construction: 3 nets, 2 doors. Door P has capacity 1, door Q has capacity 1.
    - Net M1 (mandatory) can ONLY use door P.
    - Net M2 (mandatory) can ONLY use door Q.
    - Net G (the greed bait) can use EITHER P or Q, and P is the locally cheaper
      (shorter) choice for G.
    Greedy routes G first (or G before M1) into P (cheapest) => P saturated => M1
    cannot route => fail. Global gives P->M1, Q->M2, and G... has no door left =>
    so we tune supply: door P capacity 1, door Q capacity 2. Then global: M1->P,
    M2->Q, G->Q (Q has room). Greedy: G grabs P (cheapest), M1 has nowhere => fail.
    Demand(3) vs supply(P=1,Q=2 => 3) == exactly enough; only the non-greedy
    assignment fits.
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    door_P = Door("D_P", 3.0, 5.0, 0.30, ("F.Cu",),
                  Door.capacity_from_width(0.30, PITCH, 1))   # capacity 1
    door_Q = Door("D_Q", 7.0, 5.0, 0.60, ("F.Cu",),
                  Door.capacity_from_width(0.60, PITCH, 1))   # capacity 2
    pins = [
        Pin("M1_L", 0.0, 4.0, "F.Cu"), Pin("M1_R", 6.0, 4.0, "F.Cu"),  # only P
        Pin("M2_L", 4.0, 6.0, "F.Cu"), Pin("M2_R", 10.0, 6.0, "F.Cu"),  # only Q
        Pin("G_L", 1.0, 5.0, "F.Cu"), Pin("G_R", 9.0, 5.0, "F.Cu"),     # P or Q
    ]
    # Demand structure (the construction): M1, M2 each reach exactly one door;
    # G reaches both and prefers the cheaper D_P.
    nets = [Net("M1", ("M1_L", "M1_R"), "signal", feasible_doors=("D_P",)),
            Net("M2", ("M2_L", "M2_R"), "signal", feasible_doors=("D_Q",)),
            Net("G", ("G_L", "G_R"), "signal", feasible_doors=("D_P", "D_Q"))]
    gt = GroundTruth(
        verdict="CONDITIONAL",
        metrics={
            "door_P_capacity": door_P.capacity_tracks,    # 1
            "door_Q_capacity": door_Q.capacity_tracks,    # 2
            "total_supply": door_P.capacity_tracks + door_Q.capacity_tracks,  # 3
            "total_demand": len(nets),                    # 3
            "M1_feasible_doors": ["D_P"],
            "M2_feasible_doors": ["D_Q"],
            "G_feasible_doors": ["D_P", "D_Q"],
            "G_cheapest_door": "D_P",
            "greedy_routes": 2,    # G->P then M1 stranded
            "global_routes": 3,
        },
        conditional_on="global_vs_greedy",
        alt_verdict="ROUTABLE",
        alt_metrics={"all_nets_routed": 3, "total_nets": 3},
        witness={"global_assignment": {"M1": "D_P", "M2": "D_Q", "G": "D_Q"}},
        alt_witness={"greedy_assignment": {"G": "D_P", "M2": "D_Q"},
                     "stranded": ["M1"]},
    )
    proof = (
        "T4 (design §2 row T4; greedy corner-painting). Supply: P=1, Q=2 (total "
        "3) == demand 3 (boundary). M1 needs P only; M2 needs Q only; G fits "
        "either and P is its cheapest. Greedy takes G->P (locally cheap) => P "
        "full => mandatory M1 has no door => fail (2/3). The unique feasible "
        "global assignment is M1->P, M2->Q, G->Q (Q still has 1 of 2 free) => "
        "3/3. Self-check verifies the assignment respects every door capacity, "
        "routes all 3, and that placing G in P (the greedy choice) makes M1 "
        "infeasible."
    )
    return Fixture("T4", "greedy-trap channel", "hard",
                   "global plan beats greedy; Phase A capacity + non-greedy assign",
                   layers, tuple(pins), tuple(nets),
                   (door_P, door_Q), (), (), gt, proof)


def _build_T5():
    """T5 — forced crossings / net-ordering (medium). Topology before geometry.

    Construction: 2 nets that MUST cross on a single layer (net A goes top-left to
    bottom-right; net B goes bottom-left to top-right — an X). On one signal layer
    that crossing is a short => INFEASIBLE in the wrong order / single layer.
    Routable with the correct order + exactly 1 via (one net hops to a 2nd signal
    layer to pass the crossing, then returns) — equivalently a planar order with
    1 layer change.
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    pins = [
        Pin("A_L", 0.0, 8.0, "F.Cu"), Pin("A_R", 10.0, 2.0, "F.Cu"),
        Pin("B_L", 0.0, 2.0, "F.Cu"), Pin("B_R", 10.0, 8.0, "F.Cu"),
    ]
    nets = [Net("A", ("A_L", "A_R"), "signal"),
            Net("B", ("B_L", "B_R"), "signal")]
    # Crossing test: segments A and B intersect in the plane => they cross.
    crosses = _segments_cross((0, 8), (10, 2), (0, 2), (10, 8))  # True
    gt = GroundTruth(
        verdict="INFEASIBLE",       # on a single layer, any order (they cross)
        metrics={
            "nets_cross_single_layer": crosses,   # True
            "feasible_single_layer": False,
            "vias_required_min": 1,
            "signal_layers_required": 2,
        },
        conditional_on="layer_hop_with_via",
        alt_verdict="ROUTABLE",
        alt_metrics={"vias_required": 1, "acute_angles": 0,
                     "feasible_net_order": ["A", "B"]},
        # Witness: route B on F.Cu; route A on F.Cu up to the crossing, drop 1 via
        # to In2, cross under B, return (net A uses 1 via, 2 layers). 0 shorts.
        alt_witness={"layer_of": {"B": ["F.Cu"], "A": ["F.Cu", "In2", "F.Cu"]},
                     "vias": 1},
    )
    proof = (
        "T5 (design §2 row T5; topology-before-geometry; HCG/VCG crossing). A "
        "and B are an X (A: (0,8)->(10,2); B: (0,2)->(10,8)); their segments "
        "intersect => on ONE signal layer they short in EVERY net order => "
        "INFEASIBLE single-layer (proved by _segments_cross). Inserting exactly "
        "1 via to hop one net to a 2nd signal layer across the crossing removes "
        "the conflict => ROUTABLE with vias_required==1, 0 acute angles. Self-"
        "check asserts _segments_cross==True and the witness uses exactly 1 via "
        "on 2 signal layers."
    )
    return Fixture("T5", "forced crossings / net-ordering", "medium",
                   "net ordering through a door + minimal via insertion",
                   layers, tuple(pins), tuple(nets), (), (), (), gt, proof)


def _segments_cross(p1, p2, p3, p4):
    """Proper segment-intersection test (orientation method). Used to PROVE two
    nets cross (T5). Returns True iff segment p1p2 properly intersects p3p4."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return (v > 0) - (v < 0)  # sign
    d1 = orient(p3, p4, p1)
    d2 = orient(p3, p4, p2)
    d3 = orient(p1, p2, p3)
    d4 = orient(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _build_T6():
    """T6 — return-path / plane-split trap (medium). SI HARD constraint.

    Construction: a critical net from A to B. The SHORT (direct) path crosses a
    GAP in the GND reference plane (a plane split) — return current cannot follow
    => SI failure (Ott; Howard Johnson). A LONGER path detours around the split,
    staying over continuous GND. Ground truth: ROUTABLE only if plane-continuity
    is a HARD constraint (the short path is REJECTED, not cost-penalised); the
    continuous-reference path is the answer.
    """
    layers = (
        Layer("F.Cu", "signal"),
        Layer("In1", "plane", "GND"),   # the reference plane, with a split
        Layer("In2", "signal"),
    )
    # The critical net: from (0,5) to (20,5). The direct path runs along y=5.
    pins = [Pin("CRIT_A", 0.0, 5.0, "F.Cu"), Pin("CRIT_B", 20.0, 5.0, "F.Cu")]
    nets = [Net("CRIT", ("CRIT_A", "CRIT_B"), "critical")]
    # Plane split: a vertical gap in In1 GND from (9..11) spanning y in [0..8],
    # so the direct y=5 path WOULD cross it. A detour via y>8 stays over GND.
    split = Obstacle("SPLIT_GND", 9.0, 0.0, 11.0, 8.0, kind="plane_split",
                     plane="GND")
    # A "door" / continuous-reference corridor above the split (y >= 8.5).
    door = Door("D_continuous", 10.0, 9.0, 1.0, ("F.Cu",),
                Door.capacity_from_width(1.0, PITCH, 1))
    gt = GroundTruth(
        verdict="CONDITIONAL",
        metrics={
            "direct_path_crosses_split": True,
            "direct_path_allowed": False,    # HARD reject
            "continuous_path_exists": True,
            "plane_continuity_is_hard": True,
        },
        conditional_on="plane_continuity_hard_constraint",
        alt_verdict="ROUTABLE",
        alt_metrics={"path": "continuous-reference detour above split",
                     "crosses_split": False},
        # Witness: a polyline from A up over the split (y>=8.5) and back to B,
        # never entering the split rectangle.
        witness={"continuous_path": [(0.0, 5.0), (5.0, 5.0), (5.0, 9.0),
                                      (15.0, 9.0), (15.0, 5.0), (20.0, 5.0)]},
        # The rejected short path (encoded so self-check confirms it DOES cross).
        alt_witness={"rejected_direct_path": [(0.0, 5.0), (20.0, 5.0)]},
    )
    proof = (
        "T6 (design §2 row T6; Ott; Howard Johnson return-path; ROUTING_"
        "METHODOLOGY §9 plane-continuity HARD constraint). The direct y=5 path "
        "from (0,5) to (20,5) crosses the GND-plane split rect x in [9,11], "
        "y in [0,8] => return current has no continuous reference => SI failure. "
        "Treated as a HARD constraint, the short path is REJECTED. The encoded "
        "continuous detour (up to y=9, across, back down) never enters the split "
        "rectangle => valid. Self-check asserts the direct path's segment "
        "intersects the split rect AND the detour polyline does not."
    )
    return Fixture("T6", "return-path / plane-split trap", "medium",
                   "SI hard-constraint enforcement in the cost field",
                   layers, tuple(pins), tuple(nets), (door,), (split,), (),
                   gt, proof)


def _build_T7():
    """T7 — matched-bus-under-congestion (hard). Length-match + completion.

    Construction: a 3-bit bus (D0,D1,D2) that must arrive length-matched to a skew
    tolerance, routed through a congested region (a door with capacity exactly ==
    bus width, 3 tracks). The geometric (Manhattan) lengths differ; serpentine
    meanders bring the two short members up to the longest member's length within
    the skew tolerance. Meander spacing must be >= trace width (no self-coupling).
    Ground truth: ROUTABLE with all 3 matched within tol; meander budget exists.
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    # Three bus members at y = 4,5,6; same x-span but different detour lengths.
    # Base (unmatched) Manhattan lengths chosen to differ.
    base_len = {"D0": 20.0, "D1": 18.5, "D2": 17.0}  # mm, before meander
    pins, nets = [], []
    for i, nid in enumerate(("D0", "D1", "D2")):
        y = 4.0 + i
        pins.append(Pin(f"{nid}_L", 0.0, y, "F.Cu"))
        pins.append(Pin(f"{nid}_R", base_len[nid], y, "F.Cu"))
        nets.append(Net(nid, (f"{nid}_L", f"{nid}_R"), "bus",
                        match_group="BUS", skew_tol_mm=0.20))
    # Congested door: width = 3 tracks exactly (== bus width) on 1 signal layer.
    # floor(0.90/0.30) == 3 => capacity 3 == bus width (congestion boundary).
    door = Door("D_congest", 10.0, 5.0, 0.90, ("F.Cu",),
                Door.capacity_from_width(0.90, PITCH, 1), passes=("D0", "D1", "D2"))
    target = max(base_len.values())   # match everyone up to the longest = 20.0
    tol = 0.20
    trace_w = 0.15
    # Meander needed per member (to reach target within tol). Encoded witness:
    # add this much serpentine length.
    meander = {nid: round(target - L, 3) for nid, L in base_len.items()}
    matched_len = {nid: base_len[nid] + meander[nid] for nid in base_len}
    skew = max(matched_len.values()) - min(matched_len.values())  # 0.0
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "match_groups": ["BUS"],
            "skew_tol_mm": tol,
            "achieved_skew_mm": round(skew, 3),     # 0.0 <= tol
            "door_capacity": door.capacity_tracks,  # 3
            "bus_width": 3,
            "meander_spacing_min_mm": trace_w,      # >= trace width (no self-couple)
            "all_routed": 3,
        },
        # Witness: per-member added meander length + final matched length.
        witness={"meander_add_mm": meander, "matched_len_mm": matched_len,
                 "meander_spacing_mm": trace_w},
    )
    proof = (
        "T7 (design §2 row T7; Howard Johnson skew/length-match; serpentine "
        "spacing >= width to avoid self-coupling). Door capacity == bus width 3 "
        "(congestion boundary): all 3 fit but with zero spare track. Base "
        "Manhattan lengths 20.0/18.5/17.0 differ by up to 3.0 mm >> 0.20 mm tol. "
        "Adding serpentine meander (0.0/1.5/3.0 mm) equalises all to 20.0 mm => "
        "achieved skew 0.0 <= 0.20 tol. Meander spacing 0.15 mm == trace width "
        "(>= width => no self-coupling). Self-check asserts base+meander gives "
        "intra-group skew <= tol AND door capacity >= bus width AND spacing >= "
        "trace width."
    )
    return Fixture("T7", "matched-bus-under-congestion", "hard",
                   "length-match to skew tolerance + completion under congestion",
                   layers, tuple(pins), tuple(nets), (door,), (), (), gt, proof)


def _build_T8():
    """T8 — river / topological (medium). Order-preserving, planar, min-area.

    Construction: N nets whose left-to-right order on the TOP boundary equals
    their order on the BOTTOM boundary (no crossings). Such a set is river-
    routable on a single layer, planar, 0 vias, provably minimum area (each net is
    a non-crossing 'river'; minimum tracks == 1 per net at unit spacing => width
    == N tracks, the lower bound since N distinct nets cross any vertical cut...
    actually nested-order rivers each occupy their own track band; min area is the
    nested-order packing).
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"))
    # 5 rivers: top pins r1..r5 left->right; bottom pins r1..r5 SAME order.
    n = 5
    pins, nets = [], []
    top_order, bot_order = [], []
    for i in range(1, n + 1):
        nid = f"r{i}"
        pins.append(Pin(f"{nid}_T", float(i), 10.0, "F.Cu"))  # top boundary
        pins.append(Pin(f"{nid}_B", float(i), 0.0, "F.Cu"))   # bottom boundary
        nets.append(Net(nid, (f"{nid}_T", f"{nid}_B"), "signal"))
        top_order.append(nid)
        bot_order.append(nid)
    nested = is_nested_river_order(top_order, bot_order)  # True
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "river_order_matches": nested,    # True
            "crossings": 0,
            "vias": 0,
            "single_layer": True,
            "min_tracks": n,                  # provable minimum (N parallel rivers)
            "n_nets": n,
        },
        # Witness: each net routed straight on its own track band, order preserved.
        witness={"order": top_order, "track_of": {nid: i for i, nid in
                                                   enumerate(top_order)}},
    )
    proof = (
        "T8 (design §2 row T8; Sherwani Ch.7 river routing; nested-interval "
        "planarity). Top order r1..r5 == bottom order r1..r5 (proved by "
        "is_nested_river_order). Identical boundary orders => the nets form N "
        "non-crossing rivers => planar, single-layer, 0 vias. Minimum tracks == "
        "N == 5: any vertical cut is crossed by all N nets which must occupy N "
        "distinct tracks (lower bound), and the order-preserving route achieves "
        "exactly N (upper bound) => provably minimum area. Self-check asserts "
        "order-match True, derives crossings==0 from the matched order, and "
        "min_tracks==N."
    )
    return Fixture("T8", "river / topological", "medium",
                   "river routing (order-preserving SURESHOT) + min-area",
                   layers, tuple(pins), tuple(nets), (), (), (), gt, proof)


def _build_T9():
    """T9 — GENUINELY-INFEASIBLE honesty test (stretch). Escalation logic.

    Construction: a fine-pitch QFN side (the J18/J19 escape model) with K via
    slots of SUPPLY and K+1 nets of DEMAND that must escape that side. With NO HDI
    allowed, supply == K, demand == K+1 => overflow == 1 => provably INFEASIBLE;
    the ONLY correct answer is STOP + escalate + emit the demand-vs-supply ledger
    (NOT a heroic route). Enabling HDI via-in-pad adds >=1 HDI-only via slot =>
    supply == K+1 == demand => ROUTABLE. This is the design's central honesty
    correction (T9; DEEP_RESEARCH_2026-05-26).
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    K = 4  # standard (non-HDI) via slots on the south side of the QFN.
    # K standard via slots + 1 HDI-only slot (the escalation lever).
    via_slots = []
    for i in range(K):
        via_slots.append(ViaSlot(f"VS{i}", 1.0 + i, 2.0, "J18_south",
                                 hdi_only=False))
    via_slots.append(ViaSlot("VS_HDI", 1.0 + K, 2.0, "J18_south",
                             hdi_only=True))
    # K+1 nets that must each escape the south side (one via slot each).
    pins, nets = [], []
    for i in range(K + 1):
        nid = f"esc{i}"
        pins.append(Pin(f"{nid}_PAD", 1.0 + i, 3.0, "F.Cu"))   # on the QFN pad
        pins.append(Pin(f"{nid}_DST", 1.0 + i, 0.0, "F.Cu"))   # escape target
        nets.append(Net(nid, (f"{nid}_PAD", f"{nid}_DST"), "PWM"))
    n_std_slots = sum(1 for v in via_slots if not v.hdi_only)   # K = 4
    n_all_slots = len(via_slots)                                # K+1 = 5
    demand = len(nets)                                          # K+1 = 5
    gt = GroundTruth(
        verdict="INFEASIBLE",
        metrics={
            "ic_side": "J18_south",
            "demand_nets": demand,             # 5
            "supply_via_slots_no_hdi": n_std_slots,   # 4
            "overflow_no_hdi": demand - n_std_slots,  # 1  (> 0 => INFEASIBLE)
            "verdict_reason": "demand 5 > supply 4 (no HDI) => overflow 1",
            "escalation": "HDI via-in-pad (BOARD_INVARIANTS HDI whitelist J18)",
            "heroic_route_attempted": False,   # the correct behaviour
        },
        conditional_on="hdi_via_in_pad",
        alt_verdict="ROUTABLE",
        alt_metrics={
            "supply_via_slots_with_hdi": n_all_slots,   # 5
            "overflow_with_hdi": demand - n_all_slots,  # 0
            "all_nets_escape": demand,
        },
        # Witness for the HDI-enabled solution: assign each net to a distinct slot
        # (the K+1-th uses the HDI slot).
        alt_witness={"slot_of": {f"esc{i}": (f"VS{i}" if i < K else "VS_HDI")
                                 for i in range(K + 1)}},
    )
    proof = (
        "T9 (design §2 row T9; the honesty test; DEEP_RESEARCH_2026-05-26 escape "
        "correction; Phase A demand-vs-supply ledger). Fine-pitch QFN south side "
        "(J18 model) has K=4 standard via slots (supply) and K+1=5 nets that must "
        "escape it (demand). overflow = demand - supply = 5 - 4 = 1 > 0 => "
        "provably INFEASIBLE by direct counting; the correct deliverable is STOP "
        "+ escalate + emit the ledger, NOT a heroic route. Enabling HDI via-in-"
        "pad adds 1 HDI-only slot => supply 5 == demand 5 => overflow 0 => "
        "ROUTABLE. Self-check counts slots vs nets directly (no solver) and "
        "asserts overflow 1 (no HDI) and 0 (HDI), and that the encoded HDI slot "
        "assignment is a bijection nets<->slots."
    )
    return Fixture("T9", "GENUINELY-INFEASIBLE honesty test", "stretch",
                   "escalation logic: detect infeasibility -> STOP + escalate "
                   "+ emit demand-vs-supply proof; re-verdict with HDI",
                   layers, tuple(pins), tuple(nets), (), (), tuple(via_slots),
                   gt, proof)


def _build_T10():
    """T10 — MULTI-IC-SIDE ESCAPE (stretch). Generalises the single-side T9 to a
    multi-side IC where the per-side overflow DIFFERS — the case the real CH1 board
    (8 sides across J18+J19) exposed and the OLD `escape_ledger` got WRONG (it fell
    back to all-nets-per-side, masking which side is the bottleneck).

    Construction — ONE IC (J20) with TWO populated sides:
      * SIDE N (north): K_N=2 standard via slots + H_N=2 HDI-only slots (supply);
        DEMAND_N = 3 escape nets. overflow_std = 3-2 = 1 > 0, but with HDI
        overflow = 3-(2+2) = 0 => this side is NEEDS-HDI.
      * SIDE E (east):  K_E=3 standard via slots + H_E=0 HDI slots (supply);
        DEMAND_E = 2 escape nets. overflow_std = 2-3 = 0 => this side is ROUTABLE
        with slack (1 spare std slot).

    Each net is attributed to the ONE side it physically escapes (its pin centroid
    is nearest that side's via-slot field). The WORST side governs (averaging-
    masks-local-failure): the verdict is NEEDS-HDI, driven by SIDE N (overflow_std
    1, closed by HDI). The point of the fixture: AVERAGING the two sides — avg
    demand (3+2)/2 = 2.5 vs avg std supply (2+3)/2 = 2.5 — would WRONGLY report
    overflow 0 (ROUTABLE); per-side counting proves NEEDS-HDI. An averaging liar
    FAILS T10; a correct per-side worst-governs engine PASSES.
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    # SIDE N via field along the NORTH edge (y high, x spread).  SIDE E via field
    # along the EAST edge (x high, y spread). Coordinates chosen so each net's
    # centroid is unambiguously nearest its own side's via centroid.
    via_slots = []
    # North side: 2 std + 2 HDI, near (x in 1..4, y=10).
    for i in range(2):
        via_slots.append(ViaSlot(f"VN_STD{i}", 1.0 + i, 10.0, "J20_N",
                                 hdi_only=False))
    for i in range(2):
        via_slots.append(ViaSlot(f"VN_HDI{i}", 3.0 + i, 10.0, "J20_N",
                                 hdi_only=True))
    # East side: 3 std, near (x=10, y in 1..3).
    for i in range(3):
        via_slots.append(ViaSlot(f"VE_STD{i}", 10.0, 1.0 + i, "J20_E",
                                 hdi_only=False))
    pins, nets = [], []
    # 3 escape nets on the NORTH side (pins clustered up near y=10).
    for i in range(3):
        nid = f"escN{i}"
        pins.append(Pin(f"{nid}_PAD", 1.0 + i, 9.0, "F.Cu"))   # near north field
        pins.append(Pin(f"{nid}_DST", 1.0 + i, 11.5, "F.Cu"))  # escape outward
        nets.append(Net(nid, (f"{nid}_PAD", f"{nid}_DST"), "PWM"))
    # 2 escape nets on the EAST side (pins clustered right near x=10).
    for i in range(2):
        nid = f"escE{i}"
        pins.append(Pin(f"{nid}_PAD", 9.0, 1.0 + i, "F.Cu"))   # near east field
        pins.append(Pin(f"{nid}_DST", 11.5, 1.0 + i, "F.Cu"))  # escape outward
        nets.append(Net(nid, (f"{nid}_PAD", f"{nid}_DST"), "PWM"))
    # Per-side ground-truth counts (re-derivable from the slots/nets above).
    n_std_N = sum(1 for v in via_slots if v.ic_side == "J20_N" and not v.hdi_only)
    n_hdi_N = sum(1 for v in via_slots if v.ic_side == "J20_N" and v.hdi_only)
    n_std_E = sum(1 for v in via_slots if v.ic_side == "J20_E" and not v.hdi_only)
    dem_N = 3
    dem_E = 2
    overflow_std_N = max(0, dem_N - n_std_N)            # 1 (the WORST side)
    overflow_hdi_N = max(0, dem_N - (n_std_N + n_hdi_N))  # 0
    overflow_std_E = max(0, dem_E - n_std_E)            # 0
    # Worst side = N (max overflow_std). Verdict = NEEDS-HDI (overflow_std>0,
    # overflow_hdi==0). The harness `overflow` metric = worst-side overflow_std.
    gt = GroundTruth(
        verdict="NEEDS-HDI",
        metrics={
            "worst_side": "J20_N",
            "demand_N": dem_N, "supply_std_N": n_std_N, "supply_hdi_N": n_hdi_N,
            "overflow_std_N": overflow_std_N,        # 1 (> 0 => not ROUTABLE)
            "overflow_with_hdi_N": overflow_hdi_N,   # 0 (HDI closes it)
            "demand_E": dem_E, "supply_std_E": n_std_E,
            "overflow_std_E": overflow_std_E,        # 0 (E has slack)
            "overflow_no_hdi": overflow_std_N,       # harness-scored (worst side)
            "averaging_would_say": "overflow 0 (WRONG — masks side N)",
            "verdict_reason": "side N demand 3 > std supply 2 (overflow 1); HDI "
                              "closes it; side E has slack — WORST side governs",
        },
        conditional_on="hdi_via_in_pad",
        alt_verdict="ROUTABLE",
        alt_metrics={"overflow_with_hdi": 0, "all_nets_escape": dem_N + dem_E},
        # Witness for the HDI-enabled solution: side N's 3 nets use its 2 std + 1
        # HDI slot; side E's 2 nets use 2 of its 3 std slots. A valid bijection.
        alt_witness={"slot_of": {
            "escN0": "VN_STD0", "escN1": "VN_STD1", "escN2": "VN_HDI0",
            "escE0": "VE_STD0", "escE1": "VE_STD1",
        }},
    )
    proof = (
        "T10 (multi-IC-side escape; generalises T9; the real-CH1 multi-side gap). "
        "ONE IC, TWO sides. SIDE N: std supply 2, HDI 2, demand 3 => overflow_std "
        "1 (> 0) closed by HDI (overflow 0). SIDE E: std supply 3, demand 2 => "
        "overflow_std 0 (slack). Each net is attributed to the ONE side its pin "
        "centroid is nearest (escN* -> J20_N, escE* -> J20_E). The WORST side (N) "
        "governs (averaging-masks-local-failure): verdict NEEDS-HDI, worst-side "
        "overflow_std 1. CRITICAL: averaging the sides (avg demand 2.5 vs avg std "
        "supply 2.5) reports overflow 0 = ROUTABLE, WRONGLY masking side N — so a "
        "per-side worst-governs engine is NECESSARY. Self-check counts each side "
        "independently (no solver), asserts overflow_std_N==1, overflow_std_E==0, "
        "the worst side is N, verdict NEEDS-HDI, and the HDI witness is a "
        "bijection nets<->slots."
    )
    return Fixture("T10", "multi-IC-side escape (worst side governs)", "stretch",
                   "per-IC-side escape ledger: worst side governs the verdict "
                   "(averaging masks the bottleneck side)",
                   layers, tuple(pins), tuple(nets), (), (), tuple(via_slots),
                   gt, proof)


def _build_T11():
    """T11 — INTERNAL + CROSSING net classification (stretch). The real-CH1 gap
    the OLD planner got WRONG: it force-assigned EVERY routable net to a door, so a
    door supply that only the genuine boundary-crossing nets consume was over-
    subscribed => phantom feasible=False + phantom stranded nets.

    Construction — ONE subsystem zone with:
      * N=3 INTERNAL nets (escN1..3): both pins INSIDE the zone, FAR from any door
        => they route WITHIN the zone, traverse NO boundary door, consume NO door
        capacity.
      * k=2 CROSSING nets (xN1..2): one pin sits AT a boundary DOOR (the I/O port)
        and the other inside the zone => each MUST traverse that door.
      * 2 doors, capacity 1 each => total door supply = k = 2.

    Ground truth: ROUTABLE. Only the k=2 crossing nets count against the doors,
    and door supply (2) == crossing demand (2) => a feasible door assignment
    exists. The N=3 internal nets are escape/within-zone governed and do NOT touch
    the door ledger. THE POINT: a planner that force-assigns all N+k = 5 nets to
    the 2 doors OVER-SUBSCRIBES (5 > 2) and WRONGLY reports infeasible / strands 3
    nets — exactly the real-board phantom strand. Correct classification PASSES;
    the all-to-doors liar FAILS T11.
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"),
              Layer("In2", "signal"))
    # Two boundary doors (I/O ports) at the zone edge; capacity 1 each.
    door_A = Door("D_A", 0.0, 4.0, 0.30, ("F.Cu",),
                  Door.capacity_from_width(0.30, PITCH, 1))   # capacity 1
    door_B = Door("D_B", 0.0, 6.0, 0.30, ("F.Cu",),
                  Door.capacity_from_width(0.30, PITCH, 1))   # capacity 1
    pins, nets = [], []
    # 3 INTERNAL nets — both pins INSIDE the zone interior (x in 4..8), well away
    # from the doors at x=0 => geometrically NOT at any door => INTERNAL.
    for i in range(1, 4):
        nid = f"int{i}"
        y = 3.0 + i * 0.5
        pins.append(Pin(f"{nid}_A", 4.0, y, "F.Cu"))
        pins.append(Pin(f"{nid}_B", 8.0, y, "F.Cu"))
        nets.append(Net(nid, (f"{nid}_A", f"{nid}_B"), "signal"))
    # 2 CROSSING nets — one pin sits AT a boundary door (within the door's
    # half-width+tol of the door coord) => must traverse that door => CROSSING.
    # x1 terminates at door A (0,4); x2 at door B (0,6). Other pin is interior.
    pins.append(Pin("x1_DOOR", 0.0, 4.0, "F.Cu"))   # AT door A
    pins.append(Pin("x1_INT", 6.0, 4.0, "F.Cu"))
    nets.append(Net("x1", ("x1_DOOR", "x1_INT"), "signal",
                    feasible_doors=("D_A",)))
    pins.append(Pin("x2_DOOR", 0.0, 6.0, "F.Cu"))   # AT door B
    pins.append(Pin("x2_INT", 6.0, 6.0, "F.Cu"))
    nets.append(Net("x2", ("x2_DOOR", "x2_INT"), "signal",
                    feasible_doors=("D_B",)))
    n_internal = 3
    n_crossing = 2
    door_supply = door_A.capacity_tracks + door_B.capacity_tracks  # 2
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "n_internal": n_internal,            # 3 (NOT in door ledger)
            "n_crossing": n_crossing,            # 2 (the door demand)
            "internal_nets": ["int1", "int2", "int3"],
            "crossing_nets": ["x1", "x2"],
            "door_supply": door_supply,          # 2
            "crossing_demand": n_crossing,       # 2 == door_supply => feasible
            "routed_nets": n_internal + n_crossing,  # all 5 route
            "naive_all_to_doors_demand": n_internal + n_crossing,  # 5 (the liar)
            "naive_oversubscribed": (n_internal + n_crossing) > door_supply,  # True
            "verdict_reason": "only the 2 CROSSING nets count vs door supply 2 "
                              "=> feasible; the 3 INTERNAL nets need no door",
        },
        # Witness: the door assignment for the CROSSING nets ONLY (internal nets
        # carry no door). Each crossing net to its single feasible door, in cap.
        witness={"crossing_assignment": {"x1": "D_A", "x2": "D_B"},
                 "internal_no_door": ["int1", "int2", "int3"]},
    )
    proof = (
        "T11 (internal-vs-crossing classification; the real-CH1 phantom-strand "
        "gap). 3 INTERNAL nets (both pins interior, far from any door) + 2 "
        "CROSSING nets (each with one pin AT a boundary door). Door supply = 2 "
        "(cap 1 each). A net is CROSSING iff it traverses a boundary door (a pin "
        "at the I/O port, or a declared feasible_door); else INTERNAL. ONLY the 2 "
        "crossing nets count against the doors: crossing demand 2 == door supply 2 "
        "=> feasible door assignment exists (x1->D_A, x2->D_B) => ROUTABLE; the 3 "
        "internal nets consume no door capacity. CRITICAL: a planner that force-"
        "assigns all 5 nets to the 2 doors over-subscribes (5 > 2) and WRONGLY "
        "reports infeasible / strands 3 nets (the phantom strand). Self-check "
        "classifies by geometry/declaration (no solver), asserts 3 internal + 2 "
        "crossing, crossing_demand == door_supply, the crossing assignment is "
        "within capacity, and that all-to-doors would over-subscribe."
    )
    return Fixture("T11", "internal + crossing classification", "stretch",
                   "net topology: only boundary-crossing nets consume door "
                   "capacity (internal nets are escape/within-zone governed)",
                   layers, tuple(pins), tuple(nets),
                   (door_A, door_B), (), (), gt, proof)


# ----------------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------------

_BUILDERS = [
    _build_T1, _build_T2, _build_T3, _build_T4, _build_T5,
    _build_T6, _build_T7, _build_T8, _build_T9, _build_T10, _build_T11,
]


def all_fixtures():
    """Return the 9 fixtures T1..T9 in difficulty-build order."""
    return [b() for b in _BUILDERS]


def get_fixture(name):
    for f in all_fixtures():
        if f.name == name:
            return f
    raise KeyError(f"no fixture named {name!r}")


if __name__ == "__main__":
    for f in all_fixtures():
        print(f"{f.name}: {f.title} [{f.difficulty}] -> "
              f"{f.ground_truth.verdict}"
              + (f" (->{f.ground_truth.alt_verdict} on "
                 f"{f.ground_truth.conditional_on})"
                 if f.ground_truth.conditional_on else ""))
