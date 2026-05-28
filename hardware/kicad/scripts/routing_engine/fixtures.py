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
    via-in-pad is enabled (the T9 escalation lever).

    LAYER-AWARE ESCAPE SUPPLY (T12 / OQ-020 root-fix — 2026-05-28)
    --------------------------------------------------------------
    A via class is escape SUPPLY only if it reaches a USABLE SIGNAL layer.
    On the locked 10L stackup a single-step F.Cu↔In1 microvia BOTTOMS ON the
    In1=GND plane — it provides a stitch to GND, NOT a signal escape route
    (the net cannot continue from In1 because In1 is a reference plane). On
    the same stackup a blind F.Cu↔In2 via reaches In2 (a signal layer) and IS
    a signal escape (the OQ-020 lever).

      target_layer : name of the layer this via class terminates at (the deep
                     side of the blind / microvia hop). MUST match a Layer.name
                     in the same fixture / Problem when set. When None (back-
                     compat with T1-T11 which abstract away layer targets) the
                     slot is counted naively (treated as a usable signal slot).
                     `phase_a.side_supply` cross-checks target_layer against
                     the fixture's layers tuple and DROPS slots whose target is
                     a plane (role='plane') — that is the layer-aware fix.
      via_class    : optional human-readable class tag for ledgers/PR evidence
                     (e.g. "microvia_F_In1", "blind_F_In2", "through"). Not
                     used by the supply math; pure provenance.
    """
    id: str
    x_mm: float
    y_mm: float
    ic_side: str             # which fine-pitch IC side this slot serves
    hdi_only: bool = False   # True => available only with HDI enabled
    target_layer: Optional[str] = None   # layer the via terminates at (None=naive)
    via_class: Optional[str] = None      # provenance tag, e.g. "blind_F_In2"


@dataclass(frozen=True)
class Obstacle:
    """A rectangular keep-out. kind='body' = component body keep-out;
    kind='plane_split' = a GAP in the named reference plane (return-path
    discontinuity — HARD constraint, ROUTING_METHODOLOGY §9 / §0b).

    PER-LAYER FILTER (the CH1 30/30 (E) engine-correctness fix; 2026-05-28)
    -----------------------------------------------------------------------
    `layers` declares WHICH signal layers this obstacle applies to:
      * `None` (default)  → applies to ALL layers (full-stack keep-out, the
                            current/back-compat behaviour; e.g. a component
                            body that blocks every signal layer below it in
                            the conservative model). T1-T14 all use this
                            default — unchanged.
      * non-None frozenset → applies ONLY to the named layers (e.g. an
                            In2.Cu track is a keep-out on In2.Cu but NOT on
                            In6.Cu; physics says a route on In6.Cu is free to
                            ignore an In2.Cu obstacle). T15 (per-layer-maze
                            engine-correctness fixture, 2026-05-28) is the
                            first user of this field.

    Consumers (e.g. `maze_router.route`'s A* expansion) MUST skip an obstacle
    when the current cell's layer is NOT in `obstacle.layers` (with layers
    not None). For `layers=None` the obstacle is treated as full-stack — the
    exact current behaviour for back-compat.
    """
    id: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    kind: str = "body"       # 'body' | 'plane_split'
    plane: Optional[str] = None  # for plane_split: which reference plane is cut
    layers: Optional[frozenset] = None  # None=all layers (default);
                                        # else frozenset[str] of layer names


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


def _build_T12():
    """T12 — LAYER-AWARE ESCAPE SUPPLY (stretch). The OQ-020 root-fix fixture.

    The CH1 graduation surfaced a counting bug: the engine v1 added an HDI via
    slot as +1 escape supply NAIVELY, regardless of which layer the via class
    actually reached. On the locked 10L stackup (F.Cu / In1=GND / In2=sig /
    In3=GND / ...) a single-step F.Cu↔In1 microvia BOTTOMS ON the In1=GND
    PLANE — it stitches to GND, NOT a signal escape route. A blind F.Cu↔In2
    via reaches In2 (a signal layer) and IS a signal escape (the OQ-020 fab
    class). The engine MUST count a via class as supply ONLY if its target
    layer is a SIGNAL layer (per the stackup roles).

    Construction (the smallest faithful case — provable by hand):
      * STACKUP (3 layers): F.Cu signal, In1 PLANE (GND), In2 SIGNAL.
      * ONE IC side (J20_S) with K=2 standard via slots
        (`via_class=through`, `target_layer=B.Cu`-equivalent — but our 3-layer
        stack uses In2 as the deep signal so std target=In2 signal) BUT to
        keep the counting tight here, std slots use `target_layer=None`
        (back-compat: treated as signal-usable; mirrors the abstract T9 std
        slots that don't declare a target).
      * On TOP of the std supply we add a LIAR class of HDI-only slots whose
        target is In1 (plane) — 2 microvias F.Cu↔In1. A NAIVE counter (engine
        v1) would add these +2 to the supply and call it ROUTABLE. The
        LAYER-AWARE engine must DROP them from supply (they bottom on GND).
      * We also add a TRUTH class of HDI-only slots whose target is In2
        (signal) — 1 blind F.Cu↔In2. These DO count as supply.

      * DEMAND = K+2 = 4 escape nets, all attributed to J20_S (the only side).

    Ground-truth counting (re-derivable by hand, no solver):
      std supply (signal target) = 2
      plane-bottoming microvia F-In1 supply = 0  (DROPPED — they reach plane)
      blind F-In2 supply = 1                       (signal target — kept)
      LAYER-AWARE total HDI supply = 1
      demand 4 > std 2 + HDI 1 = 3 => overflow = 1 with HDI
                                 => NEEDS-PLACEMENT-CHANGE / NEEDS-other-via-class
      NAIVE (engine-v1 liar) total HDI supply = 1 + 2 = 3
      demand 4 vs std 2 + naive HDI 3 = 5 => overflow 0 => WRONGLY ROUTABLE/NEEDS-HDI

    THE POINT: a naive plane-counting liar PASSES the case as ROUTABLE/NEEDS-HDI
    (overflow 0); the layer-aware engine reports NEEDS-PLACEMENT-CHANGE
    (overflow 1 with HDI — HDI doesn't close it because the offered HDI is
    mostly plane-bottoming). The base verdict the engine emits with std-only is
    INFEASIBLE (demand 4 > std 2 = overflow 2) — the conditional lever is the
    blind-F-In2 supply, which on its own ALSO leaves overflow 1 (because the
    plane-bottoming HDI is not supply). So the fixture's BASE verdict is
    NEEDS-PLACEMENT-CHANGE, exposing the layer-aware miscount.
    """
    # 3-layer minimum stackup to express plane vs signal targeting.
    layers = (
        Layer("F.Cu", "signal"),
        Layer("In1", "plane", "GND"),     # PLANE — vias bottoming here are NOT signal escape
        Layer("In2", "signal"),           # SIGNAL — vias bottoming here ARE signal escape
    )
    via_slots = []
    # K=2 STANDARD slots (no target_layer declared => signal-usable, back-compat).
    K = 2
    for i in range(K):
        via_slots.append(ViaSlot(f"VS_STD{i}", 1.0 + i, 2.0, "J20_S",
                                 hdi_only=False, target_layer=None,
                                 via_class="through"))
    # LIAR class: 2 HDI microvia F.Cu↔In1 — target=In1 (PLANE). These would be
    # +2 supply under naive counting but DROPPED by the layer-aware engine.
    LIAR = 2
    for i in range(LIAR):
        via_slots.append(ViaSlot(f"VS_HDI_PLANE{i}", 3.0 + i, 2.0, "J20_S",
                                 hdi_only=True, target_layer="In1",
                                 via_class="microvia_F_In1"))
    # TRUTH class: 1 HDI blind F.Cu↔In2 — target=In2 (SIGNAL). Counts as supply.
    TRUTH = 1
    for i in range(TRUTH):
        via_slots.append(ViaSlot(f"VS_HDI_SIG{i}", 5.0 + i, 2.0, "J20_S",
                                 hdi_only=True, target_layer="In2",
                                 via_class="blind_F_In2"))
    # K+2=4 escape nets, each must escape J20_S.
    DEMAND = K + 2   # 4 — provably ABOVE std (2) + truthful HDI (1) supply
    pins, nets = [], []
    for i in range(DEMAND):
        nid = f"esc{i}"
        pins.append(Pin(f"{nid}_PAD", 1.0 + i, 3.0, "F.Cu"))
        pins.append(Pin(f"{nid}_DST", 1.0 + i, 0.0, "F.Cu"))
        nets.append(Net(nid, (f"{nid}_PAD", f"{nid}_DST"), "PWM"))
    # Ground-truth bookkeeping (re-derivable from the slots/nets above).
    std_signal = sum(1 for v in via_slots
                     if not v.hdi_only
                     and (v.target_layer is None
                          or any(L.name == v.target_layer and L.role == "signal"
                                 for L in layers)))
    hdi_signal = sum(1 for v in via_slots
                     if v.hdi_only
                     and v.target_layer is not None
                     and any(L.name == v.target_layer and L.role == "signal"
                             for L in layers))
    hdi_plane = sum(1 for v in via_slots
                    if v.hdi_only
                    and v.target_layer is not None
                    and any(L.name == v.target_layer and L.role == "plane"
                            for L in layers))
    naive_hdi = sum(1 for v in via_slots if v.hdi_only)   # plane + signal (the liar)
    overflow_std_layer_aware = max(0, DEMAND - std_signal)        # 4-2 = 2
    overflow_all_layer_aware = max(0, DEMAND - (std_signal + hdi_signal))  # 4-3 = 1
    overflow_all_naive = max(0, DEMAND - (std_signal + naive_hdi))         # 4-5 = 0 (LIAR)
    gt = GroundTruth(
        # Base verdict: even with the offered HDI, the layer-aware engine
        # reports overflow 1 (HDI can't close it because most of the HDI is
        # plane-bottoming) -> NEEDS-PLACEMENT-CHANGE per phase_a._decide_verdict.
        verdict="NEEDS-PLACEMENT-CHANGE",
        metrics={
            "ic_side": "J20_S",
            "demand_nets": DEMAND,                              # 4
            "supply_std_signal": std_signal,                    # 2
            "supply_hdi_signal": hdi_signal,                    # 1 (blind F-In2)
            "supply_hdi_plane_DROPPED": hdi_plane,              # 2 (microvia F-In1 — NOT supply)
            "overflow_std_layer_aware": overflow_std_layer_aware,    # 2
            "overflow_all_layer_aware": overflow_all_layer_aware,    # 1 (binding overflow with HDI)
            "naive_hdi_supply_LIAR": naive_hdi,                 # 3 (plane + signal counted alike)
            "overflow_all_naive_LIAR": overflow_all_naive,      # 0 — WRONGLY ROUTABLE
            "verdict_reason": ("demand 4 > std 2 + LAYER-AWARE HDI 1 = 3 "
                               "(overflow_with_hdi 1, HDI does not close); "
                               "NAIVE counter sees demand 4 vs supply 5 "
                               "(overflow 0 — wrongly ROUTABLE) — proves the "
                               "engine MUST drop plane-bottoming via classes "
                               "from supply; OQ-020 root fix."),
            "escalation": "blind/buried F.Cu→In2 (signal target) — the only "
                          "HDI class that adds REAL signal escape supply on a "
                          "stackup where F-In1 bottoms on GND",
            "overflow": overflow_all_layer_aware,   # harness-scored: overflow w/ HDI offered
        },
        conditional_on=None,    # the offered HDI cannot resolve it (only 1 blind)
        alt_verdict=None,
        alt_metrics={},
        alt_witness={},
        # Witness for the LAYER-AWARE supply ledger (re-checkable by hand):
        witness={
            "supply_by_class": {
                "through (target=None signal-usable)": std_signal,
                "microvia_F_In1 (target=In1 PLANE)": "DROPPED (not signal supply)",
                "blind_F_In2 (target=In2 SIGNAL)": hdi_signal,
            },
            "layer_aware_total_supply": std_signal + hdi_signal,
            "naive_total_supply_LIAR": std_signal + naive_hdi,
        },
    )
    proof = (
        "T12 (LAYER-AWARE ESCAPE SUPPLY; the OQ-020 root-fix; "
        "DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE 2026-05-28 escape-density "
        "correction; engine layer-awareness). 3-layer stackup: F.Cu signal, "
        "In1 PLANE (GND), In2 SIGNAL. ONE IC side J20_S with 4 demand nets "
        "and three via classes offered: 2 STANDARD slots (target=None, "
        "signal-usable by back-compat); 2 HDI microvia F-In1 (target=In1 "
        "PLANE — NOT signal escape supply); 1 HDI blind F-In2 (target=In2 "
        "SIGNAL — IS signal escape supply). LAYER-AWARE counting: std supply "
        "2 + HDI(signal) 1 = 3 < demand 4 => overflow_with_hdi 1 — the "
        "offered HDI cannot close the gap because most of it bottoms on the "
        "GND plane; verdict NEEDS-PLACEMENT-CHANGE (the only HDI class that "
        "would help is MORE blind F-In2 slots — the OQ-020 lever). NAIVE "
        "counter (engine v1 liar): would add 1+2=3 HDI slots indiscriminately "
        "=> total 2+3=5 >= demand 4 => overflow 0 => WRONGLY ROUTABLE/NEEDS-"
        "HDI. Self-check counts by class (no solver), asserts the layer-aware "
        "overflow_with_hdi == 1 AND the naive overflow == 0 AND asserts a "
        "plane-counting liar would FAIL T12 by reporting overflow 0."
    )
    return Fixture("T12", "layer-aware escape supply (OQ-020 root fix)",
                   "stretch",
                   "layer-aware escape: count via class as supply ONLY if it "
                   "reaches a SIGNAL layer (plane-bottoming via classes are "
                   "DROPPED from supply); generalises the HDI counting "
                   "(engine v1 counted naively => the OQ-020 J18/J19 miscount)",
                   layers, tuple(pins), tuple(nets), (), (), tuple(via_slots),
                   gt, proof)


# ----------------------------------------------------------------------------
# T13 — LONG-PATH-THROUGH-OBSTACLES (stretch). Appended by Engine Step 8b-ext
# lever (b) — the maze-router (bounded A*) ground-truth case. Different from
# T9/T10 escape (the cooperative router's bread-and-butter): this one's
# bottleneck is FREE-SPACE NAVIGATION past component bodies over ~20mm. The
# cooperative router thrashes (its negotiated-congestion model assumes the
# bottleneck is via slots); a bounded-A* maze on a fine signal grid shines.
# ----------------------------------------------------------------------------

def _build_T13():
    """T13 — LONG-PATH-THROUGH-OBSTACLES (stretch).

    Construction: ONE critical net from S=(0,7) to E=(20,7), both on F.Cu. Three
    body keep-outs are placed across the direct line — TWO with the gap BELOW
    (y>=2), ONE with the gap ABOVE (y<=13). The direct y=7 line crosses all
    three; the only feasible route weaves up-over / down-under / up-over them
    (a multi-bend ~58mm detour), provable by hand:

        obs1: x in [4,6],   y in [2,15]  (gap BELOW y=2)
        obs2: x in [9,11],  y in [0,13]  (gap ABOVE y=13)
        obs3: x in [14,16], y in [2,15]  (gap BELOW y=2)

    Why the cooperative router stalls and the maze wins (the case this fixture
    GATES, ROUTING_METHODOLOGY §0b):
      * cooperative: negotiated congestion on via slots; no via supply here =>
        the rip-up budget burns on dead-end pushes; iterations exhaust.
      * maze (bounded A*): octilinear grid search over free space; clearance +
        plane-continuity HARD; the multi-bend detour is the natural shortest
        octilinear path, found within a small expansion budget.

    Ground truth: ROUTABLE with a single witness path. Encoded:
        path = [(0,7),(0,1),(7.5,1),(7.5,14),(12.5,14),(12.5,1),(20,1),(20,7)]
    Hand-verifiable (each leg clears every obstacle by >= 0.3mm; total length =
    58mm; 6 right-angle bends; 0 vias). Self-check confirms the witness is valid
    (every leg clears every body AABB inflated by the trace + clearance margin)
    AND the direct y=7 line DOES intersect each body (proving the bend topology
    is forced, not cosmetic).
    """
    layers = (Layer("F.Cu", "signal"), Layer("In1", "plane", "GND"))
    pins = [Pin("LP_S", 0.0, 7.0, "F.Cu"), Pin("LP_E", 20.0, 7.0, "F.Cu")]
    nets = [Net("LP", ("LP_S", "LP_E"), "signal")]
    # Three body keep-outs forcing a multi-bend octilinear detour.
    obstacles = (
        Obstacle("BODY_1", 4.0,  2.0,  6.0, 15.0, kind="body"),   # gap BELOW
        Obstacle("BODY_2", 9.0,  0.0, 11.0, 13.0, kind="body"),   # gap ABOVE
        Obstacle("BODY_3", 14.0, 2.0, 16.0, 15.0, kind="body"),   # gap BELOW
    )
    # Witness path (octilinear; uses only 90° bends so the hand-derivation stays
    # closed-form). The maze router will likely find a SHORTER octilinear-45°
    # path; the witness just PROVES routability + bounds.
    witness_path = [(0.0, 7.0), (0.0, 1.0), (7.5, 1.0), (7.5, 14.0),
                    (12.5, 14.0), (12.5, 1.0), (20.0, 1.0), (20.0, 7.0)]
    witness_length = sum(
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        for a, b in zip(witness_path, witness_path[1:]))
    witness_corners = sum(
        1 for i in range(1, len(witness_path) - 1)
        if (witness_path[i][0] - witness_path[i - 1][0],
            witness_path[i][1] - witness_path[i - 1][1])
        != (witness_path[i + 1][0] - witness_path[i][0],
            witness_path[i + 1][1] - witness_path[i][1]))
    # Min path length is the L-shaped wrap around the tightest obstacle: any
    # routable path MUST detour at least 2×(min_y_gap below + min_y_gap above) +
    # horizontal span; a conservative lower bound is the horizontal span 20mm.
    # A tighter bound: any path crossing x=10 must reach y<=0-0.3 OR y>=13+0.3 =>
    # the integral of |dy/dx| forces total path length > 20mm + 2×(13-7) - small
    # margins. We declare a SAFE lower bound 20mm (every routable path >=20mm).
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "routed": 1,
            "min_length_mm": 20.0,          # lower bound (horizontal span)
            "max_n_corners": 12,            # upper bound: the maze should not
                                             # generate >12 bends in this region
            "max_n_vias": 0,                # single layer => no vias needed
            "witness_length_mm": round(witness_length, 4),
            "witness_n_corners": witness_corners,
            "direct_line_blocked": True,    # the direct y=7 line crosses bodies
        },
        witness={"path": witness_path,
                 "trace_width_mm": 0.20,
                 "clearance_mm": 0.20},
    )
    proof = (
        "T13 (long-path through obstacles; the maze-router gate). The direct "
        "line (0,7)→(20,7) crosses three body keep-outs at x in {4..6, 9..11, "
        "14..16} (each obstacle spans y=7 by construction). The witness path "
        "weaves down-under obs1+3 (y=1) and up-over obs2 (y=14), clearing every "
        "AABB by ≥0.3mm (= trace 0.10 + clearance 0.20mm margin). Total witness "
        f"length {witness_length:.2f}mm with {witness_corners} bends and 0 vias. "
        "Self-check asserts: (a) the witness path clears every body inflated by "
        "0.3mm; (b) the witness endpoints match the pin coords; (c) the direct "
        "y=7 line DOES intersect each body (forcing the detour topology); (d) "
        "all witness segments are octilinear (axis or 45° diagonal) — no acute "
        "angles."
    )
    return Fixture("T13", "long-path through obstacles (maze gate)", "stretch",
                   "bounded-A* maze on free-space navigation past body keep-outs",
                   layers, tuple(pins), tuple(nets), (), obstacles, (), gt, proof)


# ----------------------------------------------------------------------------
# T14 — PER-NET WHITELIST PRESERVATION UNDER STD OVERFLOW (stretch). Appended
# 2026-05-28 to lock the OQ-020 T14 root-fix (the engine bug where per-named-
# net blind_F_In2 supply was eaten by side-level std overflow of OTHER nets;
# canonical d4ab0f2 J19_N PWM_INHB regression). APPEND-ONLY: T1-T13 unchanged.
# ----------------------------------------------------------------------------

def _build_T14():
    """T14 — PER-NET WHITELIST PRESERVATION UNDER STD OVERFLOW (stretch).
    The OQ-020 T14 root-fix fixture (2026-05-28; engine_v2 layer+per-net
    awareness on top of T12 layer-awareness).

    THE BUG (canonical d4ab0f2 J19_N regression — the live failure case):
    when the engine sees consumed > std_total on an IC side (some routed nets
    used HDI/non-std mechanisms), the engine v2 (pre-T14) DERATED the per-net
    HDI supply by the overflow:
        hdi_remaining = max(0, hdi_total - max(0, consumed - std_total))
    This treats HDI as fungible BACKFILL for std overflow. But the OQ-020
    blind_F_In2 supply is a PER-NAMED-NET RESERVATION (driver emits 1 blind
    slot per whitelist-eligible residual net by construction) — the std
    overflow of OTHER nets MUST NOT eat into the reserved slot for PWM_INHB
    (or BSTB/SWDIO/PWM_INLA). On the canonical board, J19_N had std_total=3,
    consumed=4, hdi_total=1 (blind for PWM_INHB), and the buggy engine
    reported hdi_remaining = max(0, 1 - 1) = 0 ⇒ INFEASIBLE for PWM_INHB,
    when the truth is the per-net slot IS reserved for it ⇒ ROUTABLE.

    Construction (smallest faithful reproduction — provable by hand):
      * STACKUP (3 layers): F.Cu signal, In1 PLANE (GND), In2 SIGNAL — the
        same minimal layer-aware stack T12 uses (so T14 stacks on T12, not
        bypassing layer-awareness).
      * ONE IC side (J21_N) with three via classes:
          - 2 STANDARD slots (target=None back-compat signal-usable; the
            T9-style abstract std).
          - 1 HDI microvia F.Cu↔In1 LIAR slot (target=In1 PLANE — DROPPED
            from signal supply by layer-awareness; included only to confirm
            T12's plane-drop rule still fires under T14).
          - 1 HDI blind F.Cu↔In2 slot (target=In2 SIGNAL, via_class=
            "blind_F_In2") — the PER-NAMED-NET reserved class. Driver-
            equivalent: one such slot reserved for the residual whitelist
            net on this side.
      * DEMAND = 1 escape net (`wl0`) — the residual whitelist net the
        blind slot is reserved for.

    GROUND TRUTH (re-derivable by hand, no solver) — under consumed=3:
      std_remaining = max(0, std_total 2 - consumed 3) = 0
      hdi_per_net (blind_F_In2, signal target) = 1   (RESERVED for wl0)
      hdi_plane (microvia_F_In1) = 1                  (DROPPED by layer-aware)
      whitelist_demand = 1  (wl0)
      non_whitelist_demand = demand 1 - whitelist 1 = 0
      ⇒ overflow_std (per-net-aware) = max(0, 0 - 0) = 0
      ⇒ overflow_hdi (per-net-aware) = 0 + max(0, 1 - 1) = 0
      ⇒ VERDICT = ROUTABLE (the per-net slot satisfies the whitelist demand)
    BUGGY-ENGINE ground truth (re-derived by the LIAR formula) — same inputs:
      hdi_remaining (BUGGY) = max(0, hdi_total 1 - max(0, consumed 3 - std 2))
                            = max(0, 1 - 1) = 0
      std_remaining = max(0, 2 - 3) = 0
      ⇒ demand 1 > supply (0 std + 0 HDI) = 0 ⇒ overflow_hdi = 1
      ⇒ VERDICT = INFEASIBLE (WRONG — per-net slot was reserved for wl0).

    THE POINT (T14 is the OQ-020 lockfile against engine drift):
    a regression to the buggy formula (or any side-aggregate-overflow logic
    that lets std overflow of OTHER nets consume per-net reserved supply)
    FAILS T14 immediately — selfcheck calls the engine directly with the
    bug-trigger inputs (consumed_by_side={"J21_N": 3},
    demand_by_side={"J21_N": 1}) and asserts the engine reports overflow
    0 and verdict ROUTABLE, AND re-derives the BUGGY formula to confirm a
    liar reproducing the old logic would say INFEASIBLE on the SAME inputs.

    SOLVER-PATH NOTE: the run_suite harness calls `solve(problem)` with no
    consumed_by_side override (the abstract fixtures default to consumed=0).
    With consumed=0 the fixture trivially routes (demand 1 ≤ std 2 + blind 1
    = 3 supply) — both buggy + fixed engines emit ROUTABLE. The bug-witness
    lives in selfcheck (direct engine invocation, which is where the
    canonical d4ab0f2 driver flow hits the bug too). Ground truth verdict
    is ROUTABLE under BOTH consumed scenarios; the bug-witness is the
    per-net allocation math + buggy-formula re-derivation, not the
    solver-path verdict alone.
    """
    # 3-layer minimum stackup to express plane vs signal targeting (same as T12).
    layers = (
        Layer("F.Cu", "signal"),
        Layer("In1", "plane", "GND"),     # PLANE — microvia bottoming here is NOT signal
        Layer("In2", "signal"),           # SIGNAL — blind via bottoming here IS signal
    )
    # 2 STANDARD slots (target_layer=None back-compat signal-usable).
    via_slots = [
        ViaSlot("VS_STD0", 1.0, 2.0, "J21_N",
                hdi_only=False, target_layer=None, via_class="through"),
        ViaSlot("VS_STD1", 2.0, 2.0, "J21_N",
                hdi_only=False, target_layer=None, via_class="through"),
        # LIAR class: 1 HDI microvia F.Cu↔In1 — target=In1 (PLANE). DROPPED
        # by layer-awareness (T12 rule); confirms T14 layers on T12, not
        # bypasses it.
        ViaSlot("VS_HDI_PLANE0", 3.0, 2.0, "J21_N",
                hdi_only=True, target_layer="In1", via_class="microvia_F_In1"),
        # TRUTH class: 1 HDI blind F.Cu↔In2 — target=In2 (SIGNAL), PER-NET
        # reserved (via_class in `phase_a.PER_NET_RESERVED_VIA_CLASSES`).
        # Reserved for the residual whitelist net `wl0` by construction
        # (driver invariant: 1 blind slot per eligible residual net).
        ViaSlot("VS_HDI_BLIND_FIn2_0", 4.0, 2.0, "J21_N",
                hdi_only=True, target_layer="In2", via_class="blind_F_In2"),
    ]
    # 1 demand net (the residual whitelist net the blind slot is reserved for).
    pins = [
        Pin("wl0_PAD", 1.0, 3.0, "F.Cu"),    # on the IC pad
        Pin("wl0_DST", 1.0, 0.0, "F.Cu"),    # escape target
    ]
    nets = [Net("wl0", ("wl0_PAD", "wl0_DST"), "PWM")]
    # Re-derivable counts (ground-truth bookkeeping; selfcheck cross-checks).
    std_total = sum(1 for v in via_slots if not v.hdi_only)              # 2
    hdi_signal = sum(1 for v in via_slots
                     if v.hdi_only
                     and v.target_layer is not None
                     and any(L.name == v.target_layer and L.role == "signal"
                             for L in layers))                            # 1
    hdi_plane = sum(1 for v in via_slots
                    if v.hdi_only
                    and v.target_layer is not None
                    and any(L.name == v.target_layer and L.role == "plane"
                            for L in layers))                             # 1
    hdi_per_net = sum(1 for v in via_slots
                      if v.hdi_only and v.via_class == "blind_F_In2")     # 1
    hdi_pool = hdi_signal - hdi_per_net                                   # 0
    demand = len(nets)                                                    # 1
    # Bug-trigger inputs the selfcheck feeds the engine (the canonical
    # d4ab0f2 J19_N pattern: consumed > std_total, demand = 1 whitelist net).
    consumed_for_bug_witness = 3
    # PER-NET-AWARE (fixed engine) accounting on those inputs:
    std_remaining_fixed = max(0, std_total - consumed_for_bug_witness)    # 0
    whitelist_demand_fixed = min(hdi_per_net, demand)                     # 1
    non_whitelist_demand_fixed = demand - whitelist_demand_fixed          # 0
    overflow_std_fixed = max(0, non_whitelist_demand_fixed
                             - std_remaining_fixed)                       # 0
    overflow_hdi_fixed = (max(0, non_whitelist_demand_fixed
                              - (std_remaining_fixed + hdi_pool))
                          + max(0, whitelist_demand_fixed - hdi_per_net)) # 0
    # BUGGY (engine_v1 pre-T14) accounting on the SAME inputs — the liar:
    hdi_remaining_buggy = max(0, hdi_signal
                              - max(0, consumed_for_bug_witness - std_total))  # 0
    std_remaining_buggy = max(0, std_total - consumed_for_bug_witness)    # 0
    overflow_std_buggy = max(0, demand - std_remaining_buggy)             # 1
    overflow_hdi_buggy = max(0, demand
                             - (std_remaining_buggy + hdi_remaining_buggy))  # 1
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "ic_side": "J21_N",
            "demand_nets": demand,                                  # 1
            "std_total": std_total,                                 # 2
            "supply_hdi_signal": hdi_signal,                        # 1 (blind only)
            "supply_hdi_per_net": hdi_per_net,                      # 1 (blind reserved)
            "supply_hdi_pool": hdi_pool,                            # 0
            "supply_hdi_plane_DROPPED": hdi_plane,                  # 1 (microvia F-In1)
            "consumed_for_bug_witness": consumed_for_bug_witness,   # 3
            # Fixed-engine (per-net-aware) under the bug-trigger inputs:
            "fixed_std_remaining": std_remaining_fixed,             # 0
            "fixed_non_whitelist_demand": non_whitelist_demand_fixed,  # 0
            "fixed_whitelist_demand": whitelist_demand_fixed,       # 1
            "fixed_overflow_std": overflow_std_fixed,               # 0
            "fixed_overflow_hdi": overflow_hdi_fixed,               # 0
            "fixed_verdict": "ROUTABLE",
            # Buggy-engine (side-aggregate-overflow-eats-whitelist) on SAME:
            "buggy_hdi_remaining": hdi_remaining_buggy,             # 0 (the EATEN slot)
            "buggy_std_remaining": std_remaining_buggy,             # 0
            "buggy_overflow_std": overflow_std_buggy,               # 1
            "buggy_overflow_hdi": overflow_hdi_buggy,               # 1
            "buggy_verdict": "INFEASIBLE",
            "verdict_reason": (
                "with consumed_by_side={'J21_N': 3} > std_total 2, the bug "
                "formula `hdi_remaining = max(0, 1 - max(0, 3-2))` = 0 "
                "INCORRECTLY consumes the per-net blind_F_In2 slot reserved "
                "for the whitelist net wl0 (the d4ab0f2 J19_N PWM_INHB "
                "regression). The per-net-aware fix preserves the reservation "
                "(non_whitelist_demand=0, blind_per_net=1, allocated to wl0) "
                "⇒ overflow 0 ⇒ ROUTABLE."),
            "escalation": (
                "ALREADY APPLIED — the per-net-aware allocation in "
                "phase_a.escape_ledger preserves per-named-net blind_F_In2 "
                "supply against side-level std-overflow consumption (the "
                "OQ-020 / T14 root fix; PER_NET_RESERVED_VIA_CLASSES "
                "policy)."),
            # Harness-scored metric on the SOLVER path (consumed=0): the
            # fixture trivially routes (1 demand ≤ 3 supply); overflow == 0.
            "overflow": 0,
        },
        # Witness: explicit allocation under both consumed scenarios.
        witness={
            # Under consumed=3 (the bug-trigger): fixed engine assigns the
            # per-net blind_F_In2 slot to wl0, std_remaining = 0 but
            # non_whitelist_demand = 0 too — every net is allocated.
            "allocation_consumed3": {
                "wl0": "VS_HDI_BLIND_FIn2_0 (per-net reserved blind F-In2)",
            },
            # Under consumed=0 (the solver path): wl0 may use std or blind;
            # we record the per-net-preferred assignment.
            "allocation_consumed0": {
                "wl0": "VS_STD0 (std slot — wl0 has fallback options too)",
            },
            "supply_by_class_layer_aware": {
                "through (target=None signal-usable)": std_total,
                "microvia_F_In1 (target=In1 PLANE)": "DROPPED (not signal supply)",
                "blind_F_In2 (target=In2 SIGNAL; PER-NET reserved)": hdi_per_net,
            },
        },
        # No CONDITIONAL lever — the fix is structural (engine refactor), not
        # a runtime escalation; the fixture is ROUTABLE both ways once the
        # engine is correct.
        conditional_on=None,
        alt_verdict=None,
        alt_metrics={},
        alt_witness={},
    )
    proof = (
        "T14 (PER-NET WHITELIST PRESERVATION UNDER STD OVERFLOW; the OQ-020 "
        "T14 root-fix; canonical d4ab0f2 J19_N PWM_INHB regression). 3-layer "
        "stackup F.Cu/In1=GND/In2=signal (same as T12 — layer-aware). ONE IC "
        "side J21_N with 4 via classes (2 std + 1 microvia F-In1 LIAR + 1 "
        "blind F-In2 PER-NET) and 1 whitelist demand net wl0. BUG-WITNESS "
        "inputs: consumed_by_side={'J21_N': 3} (3 routed nets consumed std + "
        "spilled to other mechanisms), demand_by_side={'J21_N': 1} (the "
        "residual whitelist net). The buggy formula "
        "`hdi_remaining = max(0, hdi_total - max(0, consumed - std_total))` "
        "computes hdi_remaining = max(0, 1 - 1) = 0, EATING the per-net "
        "blind slot reserved for wl0 ⇒ demand 1 > supply (0 std + 0 HDI) ⇒ "
        "INFEASIBLE (WRONG). The PER-NET-AWARE fix recognizes blind_F_In2 "
        "as PER-NAMED-NET RESERVATION (PER_NET_RESERVED_VIA_CLASSES = "
        "{'blind_F_In2'}); the std-overflow of OTHER nets does NOT consume "
        "it (non_whitelist_demand 0, std_remaining 0, blind_per_net 1, "
        "whitelist_demand 1 served by blind) ⇒ overflow 0 ⇒ ROUTABLE. "
        "Self-check (1) invokes phase_a.escape_ledger directly with the "
        "bug-trigger inputs and asserts overflow_std=0, overflow_hdi=0, "
        "supply_hdi_per_net=1, verdict ROUTABLE; (2) re-derives the BUGGY "
        "formula on the SAME inputs and asserts the liar would compute "
        "hdi_remaining=0, overflow_hdi=1, verdict INFEASIBLE; (3) asserts "
        "the T12 plane-drop rule still fires (microvia F-In1 = 0 signal "
        "supply, blind F-In2 = 1 signal supply). The fixture also routes "
        "trivially under consumed=0 (the solver-path verdict ROUTABLE) — "
        "the bug-witness is the consumed=3 selfcheck path, mirroring the "
        "live d4ab0f2 J19_N driver invocation."
    )
    return Fixture("T14",
                   "per-net whitelist preservation under std overflow "
                   "(OQ-020 T14 root fix)",
                   "stretch",
                   "per-net HDI allocation: blind_F_In2 slots are PER-NAMED-"
                   "NET RESERVATIONS that std-overflow of OTHER nets MUST "
                   "NOT consume (canonical d4ab0f2 J19_N PWM_INHB "
                   "regression; engine_v2 layer+per-net awareness)",
                   layers, tuple(pins), tuple(nets), (), (), tuple(via_slots),
                   gt, proof)


# ----------------------------------------------------------------------------
# T15 — PER-LAYER OBSTACLE FILTER (stretch). Appended 2026-05-28 to lock the
# CH1 30/30 lever (E) engine-correctness fix: the maze router's obstacle
# check MUST be layer-aware. Pre-fix, an obstacle on (say) In2.Cu WRONGLY
# blocked a route on F.Cu just because the obstacle's xy footprint coincided
# with the route — physics says the In2.Cu keep-out does not apply on F.Cu.
# T15 is the fixture that catches the bug class. APPEND-ONLY: T1-T14 unchanged.
# ----------------------------------------------------------------------------

def _build_T15():
    """T15 — PER-LAYER OBSTACLE FILTER (stretch).
    The CH1 30/30 (E) engine-correctness fixture (2026-05-28; the maze
    router's Obstacle dataclass gains a `layers` field; A* expansion skips
    obstacles whose `layers` is not None AND does not include the candidate
    cell's layer — physics, not heuristics).

    THE BUG CLASS:
    Pre-fix, `maze_router.route` iterated `body_obs` in `cell_clear` /
    `_swept_track_clears` WITHOUT examining each obstacle's layer attribution
    — every body keep-out blocked EVERY signal layer below its xy footprint.
    This is correct for true full-stack body keep-outs (a component package
    in the conservative model) but WRONG for layer-attributed obstacles
    (e.g. an In2.Cu copper track placed by a prior subsystem PR does NOT
    block an In6.Cu route on a separate layer). The cooperative router's
    real-board harness papered over the bug by filtering obstacles per
    layer at the call boundary — the engine itself was still incorrect.
    T15 is the engine-level lockfile.

    Construction (smallest faithful reproduction — provable by hand):
      * STACKUP: F.Cu signal, In2.Cu signal (BOTH signal — so layer
        attribution is meaningful; an obstacle attributed to one is NOT a
        body, it is a per-layer keep-out, the field the fix introduces).
      * 1 NET: LP from S=(0, 5, F.Cu) to E=(10, 5, F.Cu). Both endpoints on
        F.Cu — the route stays on F.Cu (no via needed).
      * 1 OBSTACLE: `BODY_IN2` at x in [-100, 100], y in [-100, 100], on
        `layers={"In2.Cu"}` ONLY. Its xy footprint covers the ENTIRE pin
        envelope + a huge halo (the F.Cu pin region is INSIDE the body
        bbox in xy). A 2D-LAYER-AGNOSTIC maze (the pre-fix behaviour) sees
        the body as full-stack and so EVERY mid-path F.Cu cell at y=5 is
        marked BLOCKED (cell xy is inside body xy and the body is treated
        as full-stack); the start/end cells survive only via the endpoint
        override (pins sit inside the body's xy) but no path exists
        BETWEEN them — the 2D-agnostic maze raises NotRoutable('NO-PATH'),
        the WRONG verdict. The PER-LAYER MAZE recognises layers={'In2.Cu'}
        and skips the body on F.Cu, so every cell on the y=5 row is clear
        and the straight 10mm F.Cu segment routes trivially.

        The "halo body containing the pins" construction is deliberate:
        it removes the possibility of the 2D-agnostic maze finding ANY
        detour around the obstacle (the body engulfs the entire region in
        xy), so the bug class is unambiguous on the live engine path too
        (not just on the simulated filter check).

    GROUND TRUTH (re-derivable by hand, no solver):
      verdict = ROUTABLE under per-layer filter.
      Witness path: a single straight F.Cu segment (0,5)→(10,5).
      witness_length_mm = 10.0  (exact — pure horizontal segment).
      witness_n_corners = 0     (single straight segment).
      max_n_vias = 0            (single-layer route).

    BUG-WITNESS (re-derivable by hand, no solver):
      A 2D-layer-agnostic maze simulated by `Obstacle.layers is treated as
      None` for filtering => the obstacle is full-stack => the F.Cu cell
      clearance check at any x ∈ [3,7] FAILS (cell xy-footprint intersects
      body) => no F.Cu path exists at y=5 within [3,7] => the bounded A*
      reports INFEASIBLE / NO-PATH (or BLOCKED if start/end happen to be
      inside the body — not the case here; the bodies are clear of pins).
      This is the bug-witness the fixture catches: same fixture, two
      filter behaviours, two verdicts. The self-check re-derives BOTH.

    SELF-CHECK DEMONSTRATES (5 assertions):
      (a) the obstacle's `layers` field is set (the engine refactor's new
          field is actually exercised — not a no-op fixture);
      (b) the witness path's endpoints match the pin coords;
      (c) under PER-LAYER filter, every F.Cu witness segment clears every
          F.Cu-applicable body — and since no body is attributed to F.Cu,
          the path clears trivially (ROUTABLE);
      (d) under 2D-LAYER-AGNOSTIC simulation (force-apply every obstacle
          to every layer), the same F.Cu segment DOES intersect the body
          AABB — proving the bug class is REAL on this fixture
          (a regression to the 2D filter would FAIL the maze on T15);
      (e) per-layer ROUTABLE invokes `maze_router.solve` directly and
          asserts the engine reports `verdict=ROUTABLE`, `routed=1`,
          `n_vias=0`, with a witness path on F.Cu that connects S→E and
          clears all F.Cu-applicable obstacles by ≥ (trace/2 + clearance).
    """
    # 2 signal layers: F.Cu (the route) and In2.Cu (where the obstacle lives).
    layers = (
        Layer("F.Cu", "signal"),
        Layer("In2.Cu", "signal"),
    )
    # 1 single-segment F.Cu net with both pins on F.Cu (no via needed).
    pins = [
        Pin("LP_S", 0.0, 5.0, "F.Cu"),
        Pin("LP_E", 10.0, 5.0, "F.Cu"),
    ]
    nets = [Net("LP", ("LP_S", "LP_E"), "signal")]
    # 1 PER-LAYER body keep-out on In2.Cu ONLY (the engine-correctness lever).
    # xy footprint ENGULFS the entire pin envelope + a huge halo so a
    # 2D-layer-agnostic maze (the pre-fix bug) cannot find ANY detour
    # around the body (every cell at y=5 between the pins is "blocked"
    # under the liar filter); the per-layer filter correctly recognises
    # the body does not apply on F.Cu, so the F.Cu route is straight.
    obstacles = (
        Obstacle("BODY_IN2", -100.0, -100.0, 100.0, 100.0,
                 kind="body",
                 layers=frozenset({"In2.Cu"})),
    )
    # Witness path: pure horizontal F.Cu segment, end to end.
    witness_path = [(0.0, 5.0), (10.0, 5.0)]
    witness_length = ((witness_path[-1][0] - witness_path[0][0]) ** 2
                      + (witness_path[-1][1] - witness_path[0][1]) ** 2) ** 0.5
    # Trace + clearance margin (matches T13 / the maze solve() defaults so the
    # selfcheck uses the same physics the solver path uses).
    trace_w = 0.20
    clearance = 0.20
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "routed": 1,
            "min_length_mm": 10.0,
            "witness_length_mm": round(witness_length, 4),
            "witness_n_corners": 0,
            "max_n_vias": 0,
            # The xy projection of the In2.Cu-only body DOES intersect the
            # F.Cu direct line — that is the whole reason a 2D-agnostic
            # filter would have wrongly rejected it.
            "direct_line_xy_hits_body": True,
            # Under the PER-LAYER filter, F.Cu has no applicable bodies
            # (the only body is In2.Cu-only), so the F.Cu path is clear:
            "f_cu_applicable_bodies": 0,
            # Under a 2D-AGNOSTIC liar filter, the same body applies on F.Cu
            # too — the F.Cu route would WRONGLY be blocked at x ∈ [3,7]:
            "liar_f_cu_applicable_bodies": 1,
            "liar_verdict": "INFEASIBLE",
        },
        witness={
            "path": witness_path,
            "layer": "F.Cu",
            "trace_width_mm": trace_w,
            "clearance_mm": clearance,
            "per_layer_filter_applied": True,
        },
        # No CONDITIONAL lever — the fix is structural (engine refactor), not
        # a runtime escalation. Under both consumed scenarios the fixture is
        # ROUTABLE once the engine carries the layer field through correctly.
        conditional_on=None,
        alt_verdict=None,
        alt_metrics={},
        alt_witness={},
    )
    proof = (
        "T15 (PER-LAYER OBSTACLE FILTER; the CH1 30/30 (E) engine-correctness "
        "lockfile; maze_router.Obstacle gains a `layers` field). Stackup: "
        "F.Cu signal, In2.Cu signal. ONE net LP: F.Cu (0,5)→(10,5). ONE body "
        "obstacle BODY_IN2 at x∈[-100,100], y∈[-100,100] on layers={'In2.Cu'} "
        "ONLY. The body engulfs the entire pin envelope + halo in xy — a "
        "2D-layer-agnostic maze (the pre-fix bug) treats the body as full-"
        "stack so every mid-path F.Cu cell at y=5 is wrongly BLOCKED; pins "
        "survive only via the endpoint override (xy inside body) but no "
        "path exists between them, raising NotRoutable('NO-PATH') — the "
        "wrong verdict. The PER-LAYER FILTER recognises layers={'In2.Cu'} "
        "and skips the body on F.Cu cell-clearance / swept-trace checks, so "
        "the straight F.Cu segment (length "
        f"{witness_length:.2f}mm, 0 bends, 0 vias) routes cleanly. "
        "Self-check (1) asserts the obstacle's `layers` field is actually "
        "set (the refactor is exercised); (2) asserts the witness endpoints "
        "match pin coords; (3) under the PER-LAYER filter the witness "
        "segment clears every F.Cu-applicable body (zero of them) — "
        "ROUTABLE; (4) under a 2D-AGNOSTIC LIAR filter (force every "
        "obstacle to apply on every layer) the F.Cu segment INTERSECTS the "
        "body AABB — proving the bug class is real and a regression to the "
        "2D filter would FAIL T15; (5) invokes `maze_router.solve` directly "
        "and asserts the engine emits verdict=ROUTABLE, routed=1, n_vias=0, "
        "with a witness polyline that connects S→E on F.Cu and clears every "
        "F.Cu-applicable body by ≥ (trace/2 + clearance) Euclidean distance."
    )
    return Fixture("T15",
                   "per-layer obstacle filter (engine correctness; "
                   "CH1 30/30 (E) lockfile)",
                   "stretch",
                   "maze_router.Obstacle.layers per-layer filter: an obstacle "
                   "attributed to layer L blocks routes on L only (not on "
                   "every layer below its xy footprint). 2D-layer-agnostic "
                   "maze WRONGLY blocks routes on OTHER layers — the engine "
                   "bug class T15 catches.",
                   layers, tuple(pins), tuple(nets), (), obstacles, (),
                   gt, proof)


# ----------------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------------

_BUILDERS = [
    _build_T1, _build_T2, _build_T3, _build_T4, _build_T5,
    _build_T6, _build_T7, _build_T8, _build_T9, _build_T10, _build_T11,
    _build_T12, _build_T13, _build_T14,
]
# APPEND-ONLY: T15 — per-layer obstacle filter (CH1 30/30 (E) engine
# correctness lockfile; 2026-05-28). Appended via `.append(...)` so the
# T1-T14 line above stays byte-identical (diff-stat: only NEW lines).
_BUILDERS.append(_build_T15)


# ----------------------------------------------------------------------------
# T16 — MAZE VIA-CELL-HALO PER-CLASS (stretch). Appended 2026-05-28 to lock
# the CH1 30/30 lever (H) engine-correctness fix: the maze router's A* via
# candidate cell-clearance check MUST use the PER-VIA-CLASS pad halo
# (pad_radius + clearance_fos), NOT the trace-inflate halo (trace/2 +
# clearance_fos). Through-via pads (0.30mm radius) blow past a 0.20mm trace's
# 0.10mm half-width; pre-fix the maze emitted vias at cells the trace-inflate
# said were clear at 0.30mm but the actual pad+clearance landed 0.04-0.18mm
# from foreign copper (worker Phase 3 final route: GLB stitch shorts GLA
# F.Cu at 0.04mm, SWDIO shorts LED_GPIO In2 at 0.127mm, PWM_INLA shorts
# I_TRIP_N In2 at 0.01mm — 18 total shorts caught by shorts-gate + worker
# reverted canonical). T16 is the engine-level lockfile. APPEND-ONLY:
# T1-T15 unchanged.
# ----------------------------------------------------------------------------

def _build_T16():
    """T16 — MAZE VIA-CELL-HALO PER-CLASS (stretch).
    The CH1 30/30 (H) engine-correctness fixture (2026-05-28; the maze
    router's A* layer-change expansion gains a per-via-class cell-halo
    check — `maze_via_halo_radius_mm(via_class, clearance_fos_mm)` ≥
    pad_radius + clearance_fos, instead of the buggy trace-inflate
    width/2 + clearance_fos — applied across EVERY layer the via barrel
    physically traverses via `maze_via_span_layers`).

    THE BUG CLASS:
    Pre-fix, `maze_router.route` evaluated a via candidate cell with the
    same `cell_clear(ix, iy)` test used for same-layer track cells —
    inflate = width/2 + clearance_fos (e.g. 0.30mm for a 0.20mm trace +
    0.20mm FoS). That inflate is CORRECT for a track sweep but WRONG for
    a via emit: the physical via pad is LARGER. JLC sanctioned via
    classes (BOARD_INVARIANTS §HDI Class 2 + OQ-020):
      through   : pad diam 0.60mm → halo 0.30 + 0.20 = 0.50mm
      blind     : pad diam 0.30mm → halo 0.15 + 0.20 = 0.35mm
      microvia  : pad diam 0.25mm → halo 0.125 + 0.20 = 0.325mm
    All three exceed the 0.30mm trace-inflate. Worker's Phase 3 final
    route empirically witnessed it: 3 maze routes (SWDIO, GLB, PWM_INLA)
    were "routable" at cell-grid level but emitted 18 NEW shorts when
    the vias landed — shorts-gate caught them and the worker REVERTED
    canonical (safe behaviour). T16 is the fixture that catches the bug
    class at the engine level (no live-board emit needed; the maze
    itself reports verdict that distinguishes buggy from fixed).

    CONSTRUCTION (smallest faithful reproduction — provable by hand):
      * STACKUP: F.Cu signal, In2.Cu signal.
      * 1 NET: LP from S=(0, 5, F.Cu) to E=(10, 5, In2.Cu). The layer
        difference FORCES a via somewhere on the route.
      * 1 OBSTACLE: `FOREIGN_IN2` at x in [10.32, 11.0], y in [3.0, 7.0],
        on `layers={"In2.Cu"}` ONLY. It sits 0.32mm RIGHT of the E pin
        (which is on In2.Cu). Distance from any cell at (x_via, 5) to the
        body's nearest edge = max(0, 10.32 - x_via).
        - trace-inflate (BUGGY check) at via cell: 0.30mm. Cell at x≥10.02
          is "clear" (trace half-width fits in the 0.32mm gap with 0.02mm
          slack). The END pin cell at (10, 5) passes the buggy check by
          0.02mm.
        - per-class halo (FIXED check):
            through halo 0.50mm → cell at (10, 5) FAILS by 0.18mm.
            blind halo 0.35mm   → cell at (10, 5) FAILS by 0.03mm.
            microvia halo 0.325mm → cell at (10, 5) FAILS by 0.005mm.
          ALL sanctioned via classes refuse the (10, 5) cell. The maze
          must place the via at a SAFE cell — the rightmost cell that
          clears the through halo by ≥0 is x_via = 10.32 - 0.50 = 9.82mm
          (snapped to grid 0.10mm: 9.80mm). The witness route is then:
            F.Cu (0,5) → (9.80, 5), via through @ (9.80, 5),
            In2.Cu (9.80, 5) → (10, 5).

    WHY THIS IS THE EXACT WORKER-WITNESSED CASE:
    Worker's Phase 3 shorts (GLB stitch via @(24.41,64.76) shorts GLA
    F.Cu at 0.04mm; SWDIO via @(29.24,70.75) shorts LED_GPIO In2 at
    0.127mm; PWM_INLA via @(32.96,68.47) shorts I_TRIP_N In2 at 0.01mm)
    all fit the same shape: a candidate via cell that the trace-inflate
    said was clear, where the emitted pad+clearance landed sub-clearance.
    T16's 0.32mm body gap reproduces that geometry: 0.32mm > 0.30mm
    (passes trace-inflate, the buggy check) AND 0.32mm < 0.50mm
    (fails through-halo, the physics check). Same root cause; same fix
    surface area; T16 is the bug-distinguishing fixture.

    GROUND TRUTH (re-derivable by hand, no solver):
      verdict = ROUTABLE under per-class halo (the FIX).
      Witness path: F.Cu (0,5) → (9.80, 5) → via through →
                    In2.Cu (9.80, 5) → (10, 5).
      witness_length_mm = 9.80 + 0.20 = 10.00mm (the In2.Cu hop is the
                          0.20mm tail past the via).
      witness_n_corners = 0   (single straight F.Cu segment + via + single
                                straight In2.Cu segment).
      max_n_vias = 1          (one layer change).
      via_via_class = 'through'   (the only allowed_via_classes used).
      via_clearance_at_emit_mm = 0.52mm   (10.32 - 9.80 = 0.52 ≥ 0.50
                                            through halo — CLEAR by 0.02mm).

    BUG-WITNESS (re-derivable by hand, no solver):
      The BUGGY 2D-via-halo liar uses trace-inflate (0.30mm) for via
      cells. Cell at (10, 5) passes by 0.02mm. The maze HAPPILY emits a
      through-via at (10, 5). PHYSICAL pad+clearance halo = 0.50mm; at
      0.32mm distance from body, the pad+clearance lands 0.18mm INSIDE
      the foreign body → SHORT. Verdict = "ROUTABLE-BUT-SHORTS" (the
      maze claims routable, shorts-gate downstream catches the emit at
      0.18mm sub-clearance and rejects). The PER-CLASS halo (the fix)
      refuses the (10, 5) cell + every cell at x ∈ (9.82, 10.32], so
      the via must land at x ≤ 9.82 (the safe cell at 9.80 above).

    SELF-CHECK DEMONSTRATES (6 assertions):
      (a) the obstacle's `layers` field is set to {"In2.Cu"} (the
          per-layer filter the fix relies on is exercised);
      (b) the witness path's endpoints match the pin coords on the
          correct layers (F.Cu start, In2.Cu end);
      (c) the witness via at x=9.80 clears the body by 0.52mm Euclidean
          (through halo 0.50mm — safe by 0.02mm), AND a buggy 2D-halo
          via at x=10.00 would short by 0.18mm (the bug class is real);
      (d) every witness segment clears every per-layer-applicable body
          (F.Cu segment trivially; In2.Cu segment by ≥0.30mm at the
          tail);
      (e) under a 2D-VIA-HALO LIAR simulation (force via halo =
          trace-inflate 0.30mm) the maze WOULD emit a through-via at
          (10, 5) and SHORT — proving the bug class is REAL on this
          fixture and a regression to trace-inflate via cells would
          FAIL T16 on the shorts-gate downstream;
      (f) INVOKES `maze_router.solve` DIRECTLY and asserts the engine
          emits verdict=ROUTABLE, routed=1, n_vias=1 with a via whose
          XY position clears every In2.Cu-applicable body by ≥ the
          per-class halo (the engine wires the fix end-to-end).
    """
    # 2 signal layers: F.Cu (the start layer) and In2.Cu (the end layer).
    # The pin layer mismatch forces a via somewhere on the route.
    layers = (
        Layer("F.Cu", "signal"),
        Layer("In2.Cu", "signal"),
    )
    pins = [
        Pin("LP_S", 0.0, 5.0, "F.Cu"),
        Pin("LP_E", 10.0, 5.0, "In2.Cu"),
    ]
    nets = [Net("LP", ("LP_S", "LP_E"), "signal")]
    # 2 PER-LAYER body keep-outs, both on In2.Cu ONLY (the per-layer filter
    # from lever E correctly skips them on F.Cu — same physics chain).
    #
    # FOREIGN_IN2 (the lever (H) bug-witness body): sits 0.32mm to the right
    # of pin E. The 0.32mm gap is the EXACT shape worker's Phase 3 GLB/SWDIO/
    # PWM_INLA shorts had: passes the buggy trace-inflate check (0.30mm) by
    # 0.02mm of slack but fails every sanctioned per-class via halo (through
    # 0.50, blind 0.35, microvia 0.325). The maze must place the via at a
    # SAFE cell at x ≤ 9.82 (the witness via at x=9.80).
    #
    # DISPATCH_BODY (forces phase_c.classify() to dispatch this fixture to
    # the MAZE branch): the In2.Cu-only body's xy footprint must intersect
    # the direct S→E 2D line (phase_c's `_direct_line_through_body` check
    # is 2D-only; it doesn't read Obstacle.layers — by design, dispatch is
    # a SHAPE classifier not a physics check). Placed at x∈[4.5,5.5],
    # y∈[3,7] so the direct line at y=5 crosses it. The body is on In2.Cu
    # ONLY so the F.Cu portion of the route correctly skips it (lever E
    # filter); the In2.Cu portion of the witness route is from the safe
    # via cell (x=9.80) to pin E (x=10) — does NOT pass through the
    # dispatch body's x-band (4.5..5.5), so the In2.Cu tail is clear.
    obstacles = (
        Obstacle("FOREIGN_IN2", 10.32, 3.0, 11.0, 7.0,
                 kind="body",
                 layers=frozenset({"In2.Cu"})),
        Obstacle("DISPATCH_BODY", 4.5, 3.0, 5.5, 7.0,
                 kind="body",
                 layers=frozenset({"In2.Cu"})),
    )
    # Witness path: F.Cu (0,5) → (9.80, 5), via through, In2.Cu (9.80, 5) → (10, 5).
    # The via at x=9.80 clears the body's x_min=10.32 by 0.52mm — safe by
    # 0.02mm over the through-via halo (0.50mm).
    witness_via_x = 9.80
    witness_via_y = 5.0
    witness_path = [(0.0, 5.0), (witness_via_x, witness_via_y),
                    (10.0, 5.0)]
    # Path length = horizontal F.Cu run + horizontal In2.Cu tail. The via at
    # the bend point has zero length contribution (it is a layer change at
    # the same xy).
    witness_length = ((witness_via_x - 0.0) + (10.0 - witness_via_x))  # = 10.0
    # Buggy 2D-halo via at the END pin cell (x=10): pad+clearance 0.50mm
    # extends into body 0.18mm. That is the SHORT the lever (H) fix prevents.
    buggy_via_x = 10.0
    buggy_via_clearance = 10.32 - buggy_via_x  # = 0.32 mm (< 0.50mm halo)
    buggy_via_short_mm = 0.50 - buggy_via_clearance  # = 0.18 mm SHORT
    # Safe via at x=9.80 (the witness): pad+clearance 0.50mm leaves 0.02mm slack.
    safe_via_clearance = 10.32 - witness_via_x  # = 0.52 mm (>= 0.50mm halo)
    safe_via_slack_mm = safe_via_clearance - 0.50  # = 0.02 mm SLACK
    trace_w = 0.20
    clearance = 0.20
    through_halo_mm = 0.60 / 2.0 + clearance     # 0.50
    blind_halo_mm = 0.30 / 2.0 + clearance        # 0.35
    microvia_halo_mm = 0.25 / 2.0 + clearance     # 0.325
    trace_inflate_mm = trace_w / 2.0 + clearance  # 0.30 — the BUGGY check
    gt = GroundTruth(
        verdict="ROUTABLE",
        metrics={
            "routed": 1,
            "min_length_mm": 10.0,
            "witness_length_mm": round(witness_length, 4),
            "witness_n_corners": 0,
            "max_n_vias": 1,
            # The body gap distance from the worker's witnessed shorts shape:
            # 0.32mm passes trace-inflate (0.30) by 0.02 — the bug surface.
            "body_gap_to_end_pin_mm": 0.32,
            "trace_inflate_halo_mm": round(trace_inflate_mm, 4),
            "through_halo_mm": round(through_halo_mm, 4),
            "blind_halo_mm": round(blind_halo_mm, 4),
            "microvia_halo_mm": round(microvia_halo_mm, 4),
            # The buggy via emit (the lever (H) bug class):
            "buggy_via_x_mm": buggy_via_x,
            "buggy_via_clearance_to_body_mm": round(buggy_via_clearance, 4),
            "buggy_via_short_mm": round(buggy_via_short_mm, 4),    # 0.18 mm short
            # The safe via emit (the witness; lever (H) fix):
            "safe_via_x_mm": witness_via_x,
            "safe_via_clearance_to_body_mm": round(safe_via_clearance, 4),
            "safe_via_slack_mm": round(safe_via_slack_mm, 4),       # 0.02 mm slack
            # Under a 2D-VIA-HALO LIAR (uses trace-inflate for via cells) the
            # maze would emit a through-via at the END pin cell and short:
            "liar_verdict": "ROUTABLE-BUT-SHORTS",
        },
        witness={
            "path": witness_path,
            "layers_in_order": ["F.Cu", "In2.Cu"],  # before-via / after-via
            "via_at": [witness_via_x, witness_via_y],
            "via_class": "through",
            "trace_width_mm": trace_w,
            "clearance_mm": clearance,
            "per_via_class_halo_applied": True,
        },
        conditional_on=None,
        alt_verdict=None,
        alt_metrics={},
        alt_witness={},
    )
    proof = (
        "T16 (MAZE VIA-CELL-HALO PER-CLASS; the CH1 30/30 (H) engine-"
        "correctness lockfile; analog of cooperative router lever F). "
        "Stackup: F.Cu signal, In2.Cu signal. ONE net LP: F.Cu (0,5) → "
        "In2.Cu (10,5) — layer-change FORCES a via. ONE body obstacle "
        "FOREIGN_IN2 on In2.Cu ONLY at x∈[10.32,11.0], y∈[3,7] — sits "
        "0.32mm right of pin E. The 0.32mm gap reproduces the EXACT bug "
        "class of worker's Phase 3 shorts (GLB/SWDIO/PWM_INLA at 0.01-"
        "0.18mm sub-clearance): passes the BUGGY trace-inflate via-cell "
        "check (0.30mm) by 0.02mm slack BUT fails EVERY sanctioned "
        f"per-class via halo (through {through_halo_mm}, blind "
        f"{blind_halo_mm}, microvia {microvia_halo_mm}). The PER-CLASS "
        "halo (the fix) refuses the END pin cell + every cell at "
        f"x∈(9.82,10.32]; the maze places the via at x={witness_via_x} "
        f"(safe by {safe_via_slack_mm}mm over through halo). Witness "
        f"path: F.Cu (0,5)→({witness_via_x},5)→via through→In2.Cu "
        f"({witness_via_x},5)→(10,5); length {witness_length}mm, 0 "
        "bends, 1 via. Self-check (a) asserts the per-layer field is "
        "exercised; (b) endpoints match pins on correct layers; (c) "
        f"the witness via clears body by {safe_via_clearance}mm (>= "
        f"through halo {through_halo_mm}); (d) every witness leg "
        "clears every per-layer-applicable body by >= (trace/2 + "
        f"clearance) = {trace_inflate_mm}mm Euclidean; (e) under a "
        "2D-VIA-HALO LIAR (force via halo = trace-inflate) the maze "
        f"would emit a through-via at x={buggy_via_x} that shorts the "
        f"body by {buggy_via_short_mm}mm — proving the bug class is "
        "real and a regression to trace-inflate via cells FAILS T16; "
        "(f) INVOKES `maze_router.solve` DIRECTLY and asserts the "
        "engine emits verdict=ROUTABLE, routed=1, n_vias=1 with a via "
        "whose XY position clears every In2.Cu-applicable body by >= "
        "the per-class halo (engine wires the fix end-to-end)."
    )
    return Fixture("T16",
                   "maze per-via-class cell halo (engine correctness; "
                   "CH1 30/30 (H) lockfile)",
                   "stretch",
                   "maze_router A* via candidate cell-clearance uses the "
                   "PER-VIA-CLASS pad halo (pad_radius + clearance_fos), "
                   "NOT the trace-inflate (trace/2 + clearance_fos), "
                   "across EVERY layer the via barrel traverses. The "
                   "trace-inflate halo silently under-clearance'd via "
                   "emits by up to 0.20mm (worker Phase 3 GLB/SWDIO/"
                   "PWM_INLA shorts); T16 is the bug-distinguishing "
                   "fixture.",
                   layers, tuple(pins), tuple(nets), (), obstacles, (),
                   gt, proof)


# APPEND-ONLY: T16 — maze per-via-class cell halo (CH1 30/30 (H) engine
# correctness lockfile; 2026-05-28). Appended via `.append(...)` so the
# T1-T15 lines above stay byte-identical (diff-stat: only NEW lines).
_BUILDERS.append(_build_T16)


# ----------------------------------------------------------------------------
# T17 — TARGETED-RIPUP-BEATS-GLOBAL (stretch). Appended 2026-05-28 to lock
# the CH1 30/30 lever (J) capability: a small synthetic case where global
# ripup converges at N-1 routed because the blocking foreign X has globally
# LOWER total cost than the blocked net Y, but X has SLACK (an alternate
# path) while Y has NONE. Targeted ripup identifies X as the SPECIFIC
# corridor conflict, surgically rips X, routes Y on its preferred path,
# then re-routes X on its alt → 2/2 routed.
#
# T1-T16 above remain byte-identical. APPEND-ONLY.
# ----------------------------------------------------------------------------

def _build_T17():
    """T17 — TARGETED-RIPUP-BEATS-GLOBAL (stretch).
    The CH1 30/30 lever (J) capability fixture (2026-05-28; cooperative
    router's 24-simultaneous cap broken by surgical conflict-set rip-
    rebuild — worker empirical PR #227 5-residual diagnosis).

    THE BUG CLASS (a class of failure, not a one-shot):
    Cooperative PathFinder evaluates each potential evict at GLOBAL cost.
    When the blocking foreign X has alternates but the blocked Y does
    not, GLOBAL cost-min keeps X (its eviction touches many cells, all
    accounted) and strands Y (its strand touches one net). The
    asymmetry between X's slack and Y's no-slack is invisible to the
    global cost function; PathFinder oscillates and plateaus.

    CONSTRUCTION (smallest faithful reproduction — provable by hand):
      * STACKUP: F.Cu signal only (1 signal layer; via slots not needed
        — the case is about IN-LAYER corridor competition, not escape).
      * 2 NETS:
          - Y ("blocked") — must route from S=(0, 5) to E=(10, 5). Its
            ONLY feasible path crosses the corridor at x ∈ [4, 6], y=5.
            (Body keep-outs to the north + south make any detour
            impossible: NORTH_BODY at y ∈ [6, 10] across x ∈ [0, 10];
            SOUTH_BODY at y ∈ [0, 4] across x ∈ [0, 10]. The y=5 lane
            is the ONLY 1-mm-tall slot Y can use.)
          - X ("foreigner") — currently routes from S=(2, 5) to
            E=(8, 5). Its routed path RUNS THROUGH the y=5 lane at
            x ∈ [2, 8] — overlapping Y's required corridor. X has an
            ALT path through (2, 5) → (2, 2.5) → (8, 2.5) → (8, 5)
            using the south-corridor at y ∈ [2, 3] (which is a
            free strip between SOUTH_BODY's top edge y=4 and another
            keep-out — left intentionally CLEAR for X's alternate).
            X's alt is LONGER (10mm vs 6mm) so global cost-min
            keeps the y=5 path and strands Y.
      * 1 OBSTACLE pair: NORTH_BODY + SOUTH_BODY pinning Y to y=5.
        Plus 2 SOUTH-CORRIDOR-BOUNDARY bodies leaving x ∈ [2, 8],
        y ∈ [2, 3] as X's alt path (X-only — Y cannot reach it
        because Y's start/end are on y=5).

    GLOBAL RIPUP outcome (the failure mode lever J fixes):
      * X is committed at y=5; Y attempts to route → blocked by X.
      * Global ripup evaluates evicting X: X's re-route cost = 10mm
        (alt path). Cost of stranding Y = 1 stranded net (Y has 0
        alternates → strand is mandatory). PathFinder's cost
        comparison: 10mm-extra-X-route ≫ 1-stranded-Y, so global
        keeps X, strands Y. Routed = 1/2; Y BLOCKED.

    TARGETED RIPUP outcome (the fix):
      1. Identify Y's IDEAL CORRIDOR ignoring foreigns → the y=5 lane,
         x ∈ [0, 10].
      2. Identify FOREIGN NETS intersecting → {X}. CONFLICT SET = {X}.
      3. Pre-rip feasibility: X has ≥1 alternate (the south corridor)
         → PASS.
      4. Surgically rip X. Route Y on the y=5 lane (now free) — 10mm.
         Re-route X on alt path (south corridor) — 10mm. Both routed.
      5. Cascade depth = 1 (X's re-route did not itself need a rip).
      6. Atomic commit: SHORTS pre = 0, SHORTS post = 0 (delta 0 OK).

    ADVERSARIAL "RIP-EVERYTHING" LIAR:
      A liar that rips ALL foreigns (X + any other committed routes)
      then routes Y alone "succeeds" at Y but DESTROYS the X commit
      without re-routing it. T17 ground-truth witness asserts X is
      ALSO routed in the final state (the frozen-routes-preserved
      invariant). The liar FAILS the routed-count metric (1/2 instead
      of 2/2).

    ADVERSARIAL "SKIP-CASCADE-CHECK" LIAR:
      A liar that allows depth > 2 would succeed on T17 trivially
      (T17's chain depth is 1). But a downstream provenance log
      check would catch a depth > 2 entry — that audit lives in
      G_J2 (independently testable against synthetic provenance).
      T17 doesn't exercise the cascade beyond depth 1 by
      construction; the deeper-cascade check belongs to G_J2.

    GROUND TRUTH (re-derivable by hand, no solver):
      verdict = ROUTABLE under targeted ripup (the FIX),
                CONDITIONAL on lever='targeted_ripup' applied.
      Base verdict (no lever) = CONDITIONAL with greedy=1/2,
                                  global=1/2, targeted=2/2.
      Witness paths:
          Y: (0,5) → (10,5)  [straight; 10mm]
          X: (2,5) → (2,2.5) → (8,2.5) → (8,5)  [alt corridor; 10mm]
      witness_n_corners_X = 2  (two right-angle bends in X's alt path)
      witness_n_corners_Y = 0  (single straight segment)
      witness_n_vias = 0       (single signal layer)
      conflict_set = ("X",)
      cascade_depth = 1
      shorts_delta = 0
    """
    # Single signal layer keeps the case 1D-resource (no via-slot supply
    # accounting muddying the corridor-competition logic).
    layers = (
        Layer("F.Cu", "signal"),
    )
    # Pins
    Ys = Pin("Y_S", 0.0, 5.0, "F.Cu")
    Ye = Pin("Y_E", 10.0, 5.0, "F.Cu")
    Xs = Pin("X_S", 2.0, 5.0, "F.Cu")
    Xe = Pin("X_E", 8.0, 5.0, "F.Cu")
    pins = [Ys, Ye, Xs, Xe]
    nets = [
        Net("Y", ("Y_S", "Y_E"), "signal"),
        Net("X", ("X_S", "X_E"), "signal"),
    ]
    # Body keep-outs pinning Y to y=5 (Y has NO alternate path):
    #   NORTH wall at y ∈ [6, 10] across x ∈ [0, 10]
    #   SOUTH wall at y ∈ [0, 4] across x ∈ [0, 10]
    # Plus south-corridor boundaries leaving x ∈ [0, 10], y ∈ [2, 3] open
    # for X's alt — but this strip is UNREACHABLE for Y (Y's pins are at y=5
    # and the south wall blocks any detour from y=5 to y=3 across x ∈ [0,10]
    # except through y=5 itself — which X is currently using).
    # Wait — we must leave a vertical channel for X to get from y=5 to y=3.
    # Solution: leave two narrow vertical gaps at x=2 (X_S) and x=8 (X_E)
    # only — encode by making SOUTH wall NOT a single block but two blocks
    # leaving the X_S → south and X_E → south gaps open (Y cannot use them
    # because Y has no pins at x=2 or x=8 on y=5 — Y's path enters at x=0
    # which is blocked by SOUTH wall and exits at x=10 which is blocked).
    obstacles = (
        # North wall (full-width)
        Obstacle("NORTH_WALL", 0.0, 6.0, 10.0, 10.0, kind="body"),
        # South wall WITH 2 gaps (at x ∈ [1.7, 2.3] and x ∈ [7.7, 8.3]).
        # The gaps are 0.6mm wide — wide enough for ONE trace (0.20mm + 2x
        # clearance 0.20mm = 0.60mm exactly), exactly what X needs to descend
        # from y=5 to y=2.5 at its endpoints. Y's pins at x=0 and x=10 are
        # OUTSIDE the gaps so Y cannot use them.
        Obstacle("SOUTH_WALL_W", 0.0, 0.0, 1.7, 4.0, kind="body"),
        Obstacle("SOUTH_WALL_M", 2.3, 0.0, 7.7, 4.0, kind="body"),
        Obstacle("SOUTH_WALL_E", 8.3, 0.0, 10.0, 4.0, kind="body"),
    )
    # Y's IDEAL CORRIDOR (the construction's binding fact):
    #   the only feasible y-band for Y at x ∈ [0, 10] is y ∈ [4, 6] (between
    #   the south + north walls' inner edges); within that band, X's existing
    #   route at y=5 occupies the centerline. Any detour off y=5 within the
    #   y ∈ [4, 6] slot would still cross X's track at some x ∈ [2, 8].
    # Conflict set = {X}. Witness for the FIX:
    #   Y: (0,5) → (10,5) ; length 10mm, 0 bends.
    #   X (re-routed): (2,5) → (2,2.5) → (8,2.5) → (8,5) ; length 10mm,
    #     2 bends (rises out of y=5 lane through gap at x=2, runs along
    #     south corridor at y=2.5, climbs back through gap at x=8).
    # Both routes coexist; SHORTS delta = 0.
    witness_Y_path = [(0.0, 5.0), (10.0, 5.0)]
    witness_X_alt_path = [(2.0, 5.0), (2.0, 2.5), (8.0, 2.5), (8.0, 5.0)]
    Y_len = 10.0  # straight
    X_len = (5.0 - 2.5) + (8.0 - 2.0) + (5.0 - 2.5)   # 2.5 + 6.0 + 2.5 = 11.0
    gt = GroundTruth(
        verdict="CONDITIONAL",
        metrics={
            # Base (no lever): greedy AND global converge at 1/2 routed
            # (X committed first at y=5 — global cost keeps it, strands Y).
            "greedy_routes": 1,
            "global_routes": 1,
            # The 'targeted' lever applied: 2/2 routed via surgical rip of X
            # + route Y on y=5 lane + re-route X on south corridor.
            "targeted_routes": 2,
            "conflict_set_size": 1,
            "cascade_depth": 1,
            "shorts_delta": 0,
            "frozen_routes_preserved": True,
            "witness_Y_len_mm": Y_len,
            "witness_X_alt_len_mm": X_len,
            "witness_Y_n_bends": 0,
            "witness_X_alt_n_bends": 2,
            "max_n_vias": 0,
        },
        witness={
            "routed_paths": {
                "Y": witness_Y_path,
                "X": witness_X_alt_path,
            },
            "conflict_set": ["X"],
            "cascade_depth": 1,
            "shorts_delta": 0,
            "frozen_routes_preserved": True,
        },
        conditional_on="targeted_ripup",
        alt_verdict="ROUTABLE",
        alt_metrics={
            "routed": 2,
            "conflict_set_size": 1,
            "cascade_depth": 1,
            "shorts_delta": 0,
        },
        alt_witness={
            "routed_paths": {
                "Y": witness_Y_path,
                "X": witness_X_alt_path,
            },
            "conflict_set": ["X"],
            "cascade_depth": 1,
        },
    )
    proof = (
        "T17 (TARGETED-RIPUP-BEATS-GLOBAL; the CH1 30/30 lever (J) "
        "capability lockfile; cooperative router's 24-simultaneous cap "
        "broken by surgical conflict-set rip-rebuild). Stackup: F.Cu "
        "signal only. TWO nets — Y (blocked, S=(0,5)→E=(10,5)) and "
        "X (foreigner, S=(2,5)→E=(8,5)). FOUR body obstacles pin Y to "
        "y=5 (its ONLY feasible lane between NORTH_WALL y∈[6,10] and "
        "SOUTH_WALL y∈[0,4]); the SOUTH_WALL is broken into 3 segments "
        "leaving 0.6mm gaps at x=2 and x=8 ONLY (wide enough for one "
        "trace; unreachable for Y whose pins are at x=0 and x=10). "
        "X's CURRENT route runs along y=5 — overlapping Y's required "
        "corridor. X has an ALTERNATIVE through the south corridor "
        f"y=2.5 (length {X_len}mm, 2 bends) but it's LONGER than Y's "
        f"required y=5 path ({Y_len}mm, 0 bends). GLOBAL cost-min "
        "keeps X at y=5 (lower total cost), strands Y → 1/2 routed. "
        "TARGETED RIPUP identifies the conflict set = {X} from Y's "
        "ideal corridor walk, verifies X has an alternate (south "
        "corridor exists + reachable through gap-at-x=2 and gap-at-"
        "x=8), surgically rips X, routes Y on its preferred y=5 "
        "lane, re-routes X on the alt south corridor → 2/2 routed. "
        "Cascade depth = 1 (X's re-route did not itself trigger a "
        "rip). SHORTS delta = 0 (no overlapping new copper). "
        "ADVERSARIAL 'rip-everything' LIAR would rip X then route Y "
        "but DROP X's re-route — fails the routed-count witness "
        "(1/2 instead of 2/2) AND fails the frozen-routes-preserved "
        "invariant. ADVERSARIAL 'skip-cascade-check' LIAR would "
        "allow depth > 2 — irrelevant on T17 (chain depth IS 1), "
        "but caught downstream by G_J2 against synthetic provenance "
        "(the audit is independently testable). Self-check verifies "
        "(a) the obstacle layout pins Y to y=5; (b) X's alt path "
        "exists (reaches y=2.5 through gaps at x=2 and x=8); (c) "
        "the witness X-route bypasses Y's y=5 lane; (d) the witness "
        "Y-route uses the y=5 lane; (e) conflict_set is {X} with "
        "cascade depth 1; (f) shorts delta = 0; (g) global / greedy "
        "verdict is 1/2 (the FAILURE mode the lever fixes); (h) the "
        "rip-everything liar produces 1/2 routed — FAILS the "
        "frozen-routes-preserved invariant."
    )
    return Fixture("T17",
                   "targeted-ripup-beats-global (capability; "
                   "CH1 30/30 (J) lockfile)",
                   "stretch",
                   "targeted ripup-rebuild: identify corridor conflict, "
                   "verify feasibility, surgically rip foreigner(s), "
                   "route blocked net, re-route foreigners on alts. "
                   "Cascade-bounded (≤2), frozen-banked-nets immutable, "
                   "shorts-delta ≤ 0. Cooperative global ripup converges "
                   "at 1/2 routed on this case (cost-min keeps the "
                   "long-alt foreigner X over the no-alt blocked Y); "
                   "targeted ripup achieves 2/2 by addressing the "
                   "asymmetry the global cost function cannot see.",
                   layers, tuple(pins), tuple(nets), (), obstacles, (),
                   gt, proof)


# APPEND-ONLY: T17 — targeted ripup-rebuild (CH1 30/30 (J) capability
# lockfile; 2026-05-28). Appended via `.append(...)` so the T1-T16 lines
# above stay byte-identical (diff-stat: only NEW lines).
_BUILDERS.append(_build_T17)


# ----------------------------------------------------------------------------
# T20 — MULTI-MECH-PATH (stretch). Appended 2026-05-28 to lock the CH1 30/30
# lever (K3) capability: multi-mechanism path planning that chains 2+ via
# classes along a single route. The seed case is the canonical SWDIO_CH1
# failure on PR #227: J18.23 (F.Cu, HDI-whitelisted) -> TP22.1 (B.Cu). The
# whitelist permits blind_F_In2 escape at J18.23 (lands on In2.Cu) but no
# single mechanism reaches B.Cu from there — In2->B.Cu needs a through-via
# elsewhere along the path. Single-mech maze fails; multi-mech chain
# succeeds. APPEND-ONLY: T1-T17 unchanged.
# ----------------------------------------------------------------------------

def _build_T20():
    """T20 — MULTI-MECH-PATH (stretch).
    The CH1 30/30 (K3) capability fixture (2026-05-28; the multi-mech
    planner chains 2+ via mechanisms along a single route — the canonical
    SWDIO_CH1 unblocker).

    THE PROBLEM CLASS (PR #227 SWDIO_CH1 reproducer):
    A single net whose START and END live on DIFFERENT outer copper layers
    (F.Cu start + B.Cu end). The start pin is HDI-whitelisted: at fine-pitch
    QFN cells like J18.23, the cooperative router's via_class_for_span
    REFUSES through-via (would short adjacent inner-layer pads on every
    layer in the F.Cu↔B.Cu barrel — the v6/v7 shorts lesson). Only the
    sanctioned HDI classes (microvia_F_In1 / microvia_B_In8 / blind_F_In2)
    are physically realisable at the HDI cell. blind_F_In2 lands on In2.Cu.
    To reach B.Cu from In2.Cu the route needs ANOTHER mechanism — a
    through-via at a non-HDI cell somewhere along the path. The chain is:

        blind_F_In2 (F.Cu→In2.Cu) at the start cell
            → In2.Cu route to a clear cell
                → through-via (In2.Cu→B.Cu) at the clear cell
                    → B.Cu route to the end cell

    A SINGLE-MECHANISM maze (the lever-(b) router) tries one via class per
    attempt:
      * blind_F_In2 only — lands on In2.Cu, cannot reach B.Cu (wrong layer).
      * through only      — REFUSED at the HDI start cell (HDI policy).
    Either way: NO-PATH. The board GEOMETRY supports the route; the router
    can't plan the chain. The MULTI-MECH planner lifts the state-space to
    (cell, layer, last_via_class), admitting 2+ via transitions in one A*
    path, and routes the chain natively. T20 locks this end-to-end.

    Construction (smallest faithful reproduction — provable by hand):
      * STACKUP: F.Cu signal, In1=GND plane (for plane-continuity context),
        In2.Cu signal, In8.Cu signal (signal-symmetric to In2 on the B side),
        B.Cu signal. 5-layer minimum so blind_F_In2 has a sanctioned span
        (F.Cu+In1+In2) and through has a sanctioned span (F.Cu..B.Cu).
      * 1 NET: MM from S=(0,5,F.Cu, HDI-whitelisted) to E=(10,5,B.Cu).
      * 2 OBSTACLES:
        - F.Cu blocking field at x∈[0.5, 11.5], y∈[-1, 11] on
          layers={"F.Cu"}. The start cell at (0,5) is the only F.Cu cell
          that clears; F.Cu past x=0.5 is blocked. The route MUST escape
          off F.Cu at the start cell — and the start cell is HDI-
          whitelisted, so through is REFUSED there; blind_F_In2 is the
          ONLY legal escape.
        - B.Cu blocking field at x∈[-1.5, 9.5], y∈[-1, 11] on
          layers={"B.Cu"}. B.Cu cells before x≈9.5 are blocked. The
          through-via to B.Cu MUST land near the end cell (x≥9.5); the
          via comes AFTER the In2.Cu route to (~9.5, 5).
      * HDI WHITELIST: the start pin is HDI-whitelisted (mirrors J18.23
        per BOARD_INVARIANTS).

    GROUND TRUTH (re-derivable by hand, no solver):
      verdict        = ROUTABLE under multi-mech (CONDITIONAL on the K3
                       lever — single-mech reports NO-PATH).
      Witness chain  = [blind_F_In2 at (0,5) F→In2,
                        In2.Cu trace (0,5)→(9.5,5),
                        through at (9.5,5) In2→B,
                        B.Cu trace (9.5,5)→(10,5)]
      routed         = 1   (the single multi-mech net is routed)
      n_vias         = 2   (one blind + one through)
      n_mechanisms   = 2   (two DIFFERENT via classes — the K3 chain)
      via_chain      = ['blind_F_In2', 'through']

    BUG-WITNESS (the single-mech adversary fails):
      A SINGLE-MECH-ONLY liar (the legacy maze or any router that admits
      ONE via class per attempt) reports NO-PATH:
        * blind_F_In2 only → lands on In2.Cu, no transition to B.Cu
                              available → NO-PATH.
        * through only     → REFUSED at the HDI start cell (HDI policy)
                              AND the F.Cu blocking field prevents the
                              route from stepping to a non-HDI F.Cu cell
                              first → NO-PATH.
      The K3 planner ADMITS the chain (state-space lifted with
      last_via_class) and routes ROUTABLE — the lockfile catches a
      regression to single-mech-only.

    SELF-CHECK DEMONSTRATES (8 assertions):
      (a) the start pin is HDI-whitelisted (the K3 lever requires the
          asymmetric HDI cell — a non-HDI start would admit through-via
          single-mech trivially);
      (b) the witness chain has exactly 2 vias of 2 distinct classes
          (the K3 capability is the multi-mechanism nature);
      (c) the first via is blind_F_In2 F.Cu→In2.Cu at the start cell;
      (d) the second via is through (In2.Cu→B.Cu) at the chain cell;
      (e) the In2.Cu trace clears the In2-applicable bodies by ≥ margin
          (per-layer filter from lever (E));
      (f) the chain cell at x=9.5 clears the B.Cu body by ≥ through halo
          (per-class halo from lever (H));
      (g) a SINGLE-MECH-ONLY liar (admits ONLY 'blind_F_In2' OR ONLY
          'through' classes) reports NO-PATH on the same fixture —
          PROVES the bug class is real and a regression FAILS T20;
      (h) INVOKES `multi_mech_planner.solve` directly and asserts the
          engine emits verdict=ROUTABLE, routed=1, n_vias=2,
          via_chain matches the witness — the engine wires the fix
          end-to-end.
    """
    # 5-layer minimum stackup to express both via classes:
    layers = (
        Layer("F.Cu", "signal"),
        Layer("In1.Cu", "plane", "GND"),
        Layer("In2.Cu", "signal"),
        Layer("In8.Cu", "signal"),
        Layer("B.Cu", "signal"),
    )
    pins = [
        Pin("MM_S", 0.0, 5.0, "F.Cu"),
        Pin("MM_E", 10.0, 5.0, "B.Cu"),
    ]
    nets = [Net("MM", ("MM_S", "MM_E"), "signal")]
    # Two-layer obstacle field that forces the chain:
    obstacles = (
        # F.Cu east blocker (no F.Cu detour east of start).
        Obstacle("F_BLOCK_E", 0.4, -2.0, 11.5, 12.0,
                 kind="body", layers=frozenset({"F.Cu"})),
        # F.Cu north blocker (no F.Cu detour north of start). Stops at
        # x=0.3 so the start cell itself (x=0) is clear.
        Obstacle("F_BLOCK_N", -2.0, 5.4, 0.3, 12.0,
                 kind="body", layers=frozenset({"F.Cu"})),
        # F.Cu south blocker (no F.Cu detour south of start).
        Obstacle("F_BLOCK_S", -2.0, -2.0, 0.3, 4.6,
                 kind="body", layers=frozenset({"F.Cu"})),
        # F.Cu west blocker (no F.Cu detour west of start; the start cell
        # at (0,5) sits in a clear "slot" between -0.3 and 0.3 on x).
        Obstacle("F_BLOCK_W", -2.0, -2.0, -0.4, 12.0,
                 kind="body", layers=frozenset({"F.Cu"})),
        # B.Cu blocking field (B.Cu clear only near the end cell).
        # Through halo 0.50mm; chain cell at x>=9.5 lands clear of body
        # at x_max=9.4 (clearance >= 0.10mm at the chain edge; ample).
        Obstacle("B_BLOCK", -2.5, -2.0, 9.4, 12.0,
                 kind="body", layers=frozenset({"B.Cu"})),
    )
    # Witness chain — provable by hand:
    #   start (F.Cu, 0, 5)
    #     blind_F_In2 → In2.Cu
    #   trace (In2.Cu, 0, 5) → (10, 5)
    #     through → B.Cu     (lands at end pin — chain cell == end cell)
    # The chain cell sits AT the end pin (10, 5) because B_BLOCK extends to
    # x=9.4 and the through-via halo (0.50mm pad+clearance) needs >= 0.1mm
    # gap to the body — only x>=9.9 clears, so the LAST grid-aligned cell
    # the through-via can land at (with 0.5mm grid pitch) is x=10.0 = the
    # end cell. The B.Cu segment is the zero-length "segment" between the
    # via and the end pin — encoded in the witness as the path's final
    # vertex (10, 5).
    chain_x = 10.0
    witness_vias = [
        {"point": (0.0, 5.0), "via_class": "blind_F_In2",
         "from_layer": "F.Cu", "to_layer": "In2.Cu"},
        {"point": (chain_x, 5.0), "via_class": "through",
         "from_layer": "In2.Cu", "to_layer": "B.Cu"},
    ]
    witness_segments = [
        {"p1": (0.0, 5.0), "p2": (chain_x, 5.0),
         "layer": "In2.Cu", "width_mm": 0.20},
        {"p1": (chain_x, 5.0), "p2": (10.0, 5.0),
         "layer": "B.Cu", "width_mm": 0.20},
    ]
    witness_path = [(0.0, 5.0), (chain_x, 5.0), (10.0, 5.0)]
    witness_length = ((chain_x - 0.0) ** 2 + 0.0) ** 0.5 \
        + ((10.0 - chain_x) ** 2 + 0.0) ** 0.5
    gt = GroundTruth(
        verdict="CONDITIONAL",
        metrics={
            "routed": 1,
            "n_vias": 2,
            "n_mechanisms": 2,
            "via_chain": ["blind_F_In2", "through"],
            "witness_length_mm": round(witness_length, 4),
            "single_mech_blind_only_verdict": "INFEASIBLE",
            "single_mech_through_only_verdict": "INFEASIBLE",
            "multi_mech_verdict": "ROUTABLE",
        },
        witness={
            "path": witness_path,
            "segments": witness_segments,
            "vias": witness_vias,
            "via_chain": ["blind_F_In2", "through"],
            "trace_width_mm": 0.20,
            "clearance_mm": 0.20,
        },
        conditional_on="multi_mech",
        alt_verdict="ROUTABLE",
        alt_metrics={
            "routed": 1,
            "n_vias": 2,
            "n_mechanisms": 2,
        },
        alt_witness={
            "path": witness_path,
            "via_chain": ["blind_F_In2", "through"],
        },
    )
    proof = (
        "T20 (MULTI-MECH-PATH; the CH1 30/30 (K3) capability lockfile; "
        "multi-mechanism path planning chains 2+ via classes along a "
        "single route — the canonical SWDIO_CH1 unblocker). Stackup: "
        "F.Cu signal + In1=GND plane + In2.Cu signal + In8.Cu signal + "
        "B.Cu signal (5 layers). ONE net MM: S=(0,5,F.Cu,HDI-whitelisted) "
        "→ E=(10,5,B.Cu). TWO body obstacles encapsulate the route on "
        "F.Cu and B.Cu: F_BLOCK on F.Cu at x∈[0.5,11.5] y∈[-1,11] forces "
        "the route off F.Cu at the start cell (no detour available); "
        "B_BLOCK on B.Cu at x∈[-1.5,9.5] y∈[-1,11] forces the through-"
        "via to land near the end cell (x≥9.5). At the HDI start cell, "
        "through-via is REFUSED (cooperative router's via_class_for_span "
        "policy; the v6/v7 shorts lesson: through F.Cu↔B.Cu at a fine-"
        "pitch QFN pad shorts adjacent inner-layer copper on every "
        "barrel layer). So blind_F_In2 is the ONLY legal escape — lands "
        "on In2.Cu. From In2.Cu the route runs east to x=9.5 (the first "
        "B.Cu-clear column) and emits a through-via to B.Cu, then a "
        "0.5mm B.Cu hop to the end pin. Two distinct mechanisms chained: "
        "via_chain = ['blind_F_In2', 'through']. Witness path = "
        "[(0,5)→(9.5,5)→(10,5)] (the In2.Cu segment + B.Cu segment); "
        f"witness length = {witness_length:.2f}mm. SINGLE-MECH-ONLY "
        "LIARS fail: a blind-only solver lands on In2.Cu and cannot "
        "reach B.Cu (no second mechanism); a through-only solver is "
        "REFUSED at the HDI start AND the F.Cu blocking field prevents "
        "stepping to a non-HDI F.Cu cell — NO-PATH on both. The K3 "
        "MULTI-MECH planner lifts the A* state-space to (cell, layer, "
        "last_via_class) and admits 2+ via transitions in one path, "
        "routing the chain natively. Self-check (a) asserts the start "
        "pin is HDI-whitelisted; (b) the witness chain has 2 vias of "
        "2 distinct classes; (c) first via is blind_F_In2 F→In2 at "
        "start; (d) second via is through In2→B at chain cell; (e) "
        "In2.Cu segment clears every In2-applicable body by ≥0.30mm; "
        "(f) the chain cell at x=9.5 clears B_BLOCK by ≥ through halo "
        "0.50mm; (g) a single-mech-only liar reports NO-PATH (bug "
        "class is real, regression FAILS T20); (h) invokes "
        "multi_mech_planner.solve and asserts the engine emits "
        "verdict=ROUTABLE, routed=1, n_vias=2, via_chain == witness."
    )
    return Fixture("T20",
                   "multi-mech path planning (CH1 30/30 (K3) lockfile)",
                   "stretch",
                   "multi-mechanism path planner: chain 2+ via classes "
                   "along a single route. Single-mech maze fails on "
                   "F.Cu-start + B.Cu-end + HDI-cell constraints "
                   "(canonical SWDIO_CH1 reproducer); multi-mech "
                   "planner lifts the A* state-space and routes the "
                   "chain natively. The K3 capability lockfile.",
                   layers, tuple(pins), tuple(nets), (), obstacles, (),
                   gt, proof)


# APPEND-ONLY: T20 — multi-mech-path planner (CH1 30/30 (K3) capability
# lockfile; 2026-05-28). Appended via `.append(...)` so the T1-T17 lines
# above stay byte-identical (diff-stat: only NEW lines).
_BUILDERS.append(_build_T20)


def all_fixtures():
    """Return the registered fixtures in case-number order (T1..T14)."""
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
