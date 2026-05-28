#!/usr/bin/env python3
"""targeted_ripup.py — TARGETED RIPUP-REBUILD capability (CH1 30/30 lever J).

Sai-approved 2026-05-28 after cooperative router's 24-simultaneous-net cap
across 6 invocation strategies (`MASTER_COOP_ROUTER.md`, PR #227): global
ripup distributes costs but cannot surgically free a specific corridor for
a blocked net N. Targeted ripup identifies the SPECIFIC foreign net(s) X
whose tracks intersect N's ideal path (the "conflict set"), surgically rips
ONLY those, routes N on its preferred path, then re-routes X(s) treating N
as fixed obstacle. Atomic commit-or-rollback.

This module is the SSoT for:
  - The 6-step algorithm (corridor-conflict → minimum-set → feasibility →
    surgical rip → cascade-bounded recursion → atomic commit/rollback)
  - The net-criticality scoring (SAFETY > MOTOR > ANALOG > BUS > DEBUG)
  - The frozen-banked-nets list (R38) — nets that CANNOT be ripped
  - The provenance log schema (R36) — every targeted-ripup commit MUST log
    the conflict set + re-route mapping
  - The cascade-depth cap (R37) — depth ≤ 2 (rip → route → re-route once)
  - The phase-symmetric-ripup mirror discipline (R39)

Imported by:
  - `route_subsystem_cooperative.py` (the router that emits ripups)
  - `audit_targeted_ripup_provenance.py` G_J1
  - `audit_ripup_cascade_depth.py`        G_J2
  - `audit_frozen_banked_nets_preserved.py` G_J3
  - `audit_symmetric_ripup_mirror.py`     G_J4
  - `audit_ripup_shorts_delta_zero.py`    G_J5

Design refs:
  - `docs/ROUTING_METHODOLOGY.md` §0c (targeted ripup-rebuild, this PR)
  - `docs/ROUTING_LESSONS.md` L15 (the 24-cap diagnosis + design, this PR)
  - `docs/BOARD_INVARIANTS.md` §"Frozen banked nets" (the R38 table, this PR)
  - `docs/RULES_MANIFEST.md` R36-R39 + G_J1-G_J5 (this PR)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional


# ============================================================================
# NET CRITICALITY SCORING (Sai expansion)
# ============================================================================
# Priority drives BOTH:
#   * net-processing order — HIGH first (route safety + motor before debug)
#   * rip ranking          — LOW first  (rip debug before motor; protect safety)
#
# Each pattern is a regex; the FIRST match wins. Patterns are evaluated in the
# order below — most specific first, generic last (DEBUG catch-all is last but
# only matches the named SWD/TP prefix family). A net matching NONE of the
# patterns gets DEFAULT_PRIORITY (treated as bulk signal).
#
# Anchored on memory `[[feedback-physics-as-compass]]`: physics, not arbitrary
# rules. SAFETY=100 ensures KILL_* never ripped (only ROUTED FIRST); MOTOR=80
# ensures commutation/gate-drive route early; DEBUG=20 ripped first when in
# conflict (debug nets have ample alternate paths through ample manhattan
# routing capacity, whereas a motor net through a tight escape has none).

NET_CRITICALITY = (
    # (priority, regex, class_label)
    (100, r"^KILL($|_)",            "SAFETY"),
    (100, r"_KILL($|_)",            "SAFETY"),
    (100, r"^KILL_RAIL_N",          "SAFETY"),
    (80,  r"^PWM_",                 "MOTOR_CONTROL"),
    (80,  r"^GL[ABC]($|_)",         "MOTOR_CONTROL"),   # gate-low A/B/C
    (80,  r"^GH[ABC]($|_)",         "MOTOR_CONTROL"),   # gate-high A/B/C
    (80,  r"^BSTB($|_)",            "MOTOR_CONTROL"),   # bootstrap B
    (80,  r"^BSTA($|_)",            "MOTOR_CONTROL"),
    (80,  r"^BSTC($|_)",            "MOTOR_CONTROL"),
    (80,  r"^MOTOR_[ABC]",          "MOTOR_CONTROL"),   # SW node
    (70,  r"^BEMF_[ABC]",           "ANALOG_SENSE"),    # BEMF refs
    (70,  r"_SHUNT",                "ANALOG_SENSE"),
    (70,  r"^SHUNT_",               "ANALOG_SENSE"),
    (70,  r"_CURR_",                "ANALOG_SENSE"),
    (70,  r"^VREF",                 "ANALOG_SENSE"),
    (70,  r"^I_TRIP_N",             "ANALOG_SENSE"),
    (50,  r"^DSHOT_",               "DIGITAL_BUS"),
    (50,  r"^TLM_",                 "DIGITAL_BUS"),
    (50,  r"_RAIL_($|_)",           "DIGITAL_BUS"),
    (20,  r"^SWDIO($|_)",           "DEBUG"),
    (20,  r"^SWCLK($|_)",           "DEBUG"),
    (20,  r"^SWO($|_)",             "DEBUG"),
    (20,  r"^TP\d",                 "DEBUG"),
    (20,  r"^BOOT0($|_)",           "DEBUG"),
)

DEFAULT_PRIORITY = 40
DEFAULT_CLASS = "BULK_SIGNAL"


def net_criticality(netname: str) -> tuple[int, str]:
    """Return (priority, class_label) for `netname` per the NET_CRITICALITY table.
    Higher priority = route earlier + rip later (more protected)."""
    if not netname:
        return DEFAULT_PRIORITY, DEFAULT_CLASS
    for prio, pat, label in NET_CRITICALITY:
        if re.search(pat, netname):
            return prio, label
    return DEFAULT_PRIORITY, DEFAULT_CLASS


# ============================================================================
# FROZEN BANKED NETS (R38)
# ============================================================================
# Nets that CANNOT be ripped under any targeted-ripup attempt. Listed per
# physics-class. Order matters only for human-readability; the audit treats
# the set as a whole.
#
# The MASTER table lives in `docs/BOARD_INVARIANTS.md` §"Frozen banked nets";
# this Python module is the AUDIT-FACING SSoT. If they diverge, G_J3 fails
# with the offending name. Update both in the same PR.

FROZEN_BANKED_NETS = (
    # Power planes — never rippable (would brick PDN, 280A burst current)
    "+VMOTOR",
    "GND",
    "+BATT",
    # Per-channel VMOTOR pours (S3 R34 bridge feeds these via In8 local pours)
    "+VMOTOR_CH1",
    "+VMOTOR_CH2",
    "+VMOTOR_CH3",
    "+VMOTOR_CH4",
    # Per-channel bus-cap rail (post-Hall-sense VMOTOR; 85-pad envelope
    # including Q5/Q7/Q9 drain + C62-C100 bulk-cap network). Carries the
    # FET-region bypass-loop current at 280 A burst envelope. Ripping it
    # cascades into S2-bus + S5-BEC validation redo. Added 2026-05-28 per
    # docs/CH1_DRONE_RELIABILITY_SWEEP_2026-05-28.md Finding #5.
    "VMOTOR_CH",
    # Battery + bulk-cap interconnect (S1+S2 validated routing)
    "BATGND",
    # BEC trunks (S5 validated, cross-subsystem feeders)
    "+3V3",
    "+5V",
    "+9V",
    "+3V3A",
    # Mirror-symmetric validated CH1 power routing — once a per-channel power
    # rail is routed, ripping it forces a full per-channel power redo + sim.
    "+3V3_CH1",
    "+5V_CH1",
    "+9V_CH1",
    "+3V3A_CH1",
    "+3V3_CH2",
    "+5V_CH2",
    "+9V_CH2",
    "+3V3_CH3",
    "+5V_CH3",
    "+9V_CH3",
    "+3V3_CH4",
    "+5V_CH4",
    "+9V_CH4",
    # Safety kill broadcast (high enough criticality it gets ROUTED FIRST and
    # never ripped after — also R36 prio=100 makes the heuristic refuse it).
    "KILL_CH1",
    "KILL_CH2",
    "KILL_CH3",
    "KILL_CH4",
)


def is_frozen_banked(netname: str) -> bool:
    """Return True if `netname` is a frozen-banked net (R38; cannot be ripped)."""
    if not netname:
        return False
    if netname in FROZEN_BANKED_NETS:
        return True
    # Suffix-tolerant: +VMOTOR variants etc. Match exact name only — explicit
    # listing is preferred to wildcards to avoid accidental freezes.
    return False


# ============================================================================
# PHASE-SYMMETRIC NET CLASSIFICATION (R39)
# ============================================================================
# A net is phase-symmetric when its A/B/C peer set exists by per-phase rotation
# (R19 / OQ-019 binding: commutation-loop symmetry). Ripping one without the
# others breaks phase balance; either MIRROR the rip across A+B+C peers OR
# log the deviation with loop-L verification proof.

PHASE_SYMMETRIC_PREFIXES = (
    "GLA", "GLB", "GLC",       # gate-low A/B/C
    "GHA", "GHB", "GHC",       # gate-high A/B/C
    "BSTA", "BSTB", "BSTC",    # bootstrap A/B/C
    "BEMF_A", "BEMF_B", "BEMF_C",
    "MOTOR_A", "MOTOR_B", "MOTOR_C",   # SW nodes
    "SHUNT_A", "SHUNT_B", "SHUNT_C",
)


def phase_peer_set(netname: str) -> Optional[tuple[str, str, str]]:
    """If `netname` is phase-A/B/C symmetric, return the (A, B, C) peer triple
    in canonical order; else None.

    e.g. `GLB_CH1` -> (`GLA_CH1`, `GLB_CH1`, `GLC_CH1`).
         `BEMF_C_CH3` -> (`BEMF_A_CH3`, `BEMF_B_CH3`, `BEMF_C_CH3`).
    """
    if not netname:
        return None
    # Try each prefix pattern to find which phase letter this net carries.
    for fam in ("GL", "GH", "BST", "BEMF_", "MOTOR_", "SHUNT_"):
        for phase in ("A", "B", "C"):
            prefix = f"{fam}{phase}"
            if netname.startswith(prefix):
                # Suffix (e.g. "_CH1") is whatever comes after the phase letter
                suffix = netname[len(prefix):]
                a = f"{fam}A{suffix}"
                b = f"{fam}B{suffix}"
                c = f"{fam}C{suffix}"
                return (a, b, c)
    return None


# ============================================================================
# PROVENANCE LOG SCHEMA (R36)
# ============================================================================
# Every targeted-ripup commit writes one TargetedRipupEntry to a JSON log
# under `sims/routing_provenance/targeted_ripup/<commit_sha>.json`. The audit
# G_J1 scans the log directory; G_J2 builds the cascade-depth graph from it;
# G_J4 verifies phase-symmetric mirror.
#
# A SINGLE provenance entry covers ONE atomic ripup attempt (steps 1-6 of the
# algorithm). If the attempt rolls back, an entry is STILL written with
# `committed=False` + `rollback_reason` (so the audit can verify intent +
# rollback is logged, not silent).

PROVENANCE_DIR_REL = "sims/routing_provenance/targeted_ripup"


@dataclass
class TargetedRipupEntry:
    """One targeted-ripup attempt record (R36 provenance)."""
    # Identity
    schema_version: int = 1
    timestamp_iso: str = ""
    board_sha: str = ""               # git SHA of canonical board at attempt time
    subsystem: str = ""               # e.g. "CH1"
    # The blocked net we tried to free space for
    blocked_net: str = ""
    blocked_net_priority: int = 0
    # The conflict set ripped (foreign nets whose tracks/vias actually
    # intersected the blocked-net IDEAL path). Each element = net name.
    conflict_set: tuple = ()
    # Per-conflict-net criticality at rip-decision time (for audit traceability)
    conflict_set_priorities: tuple = ()  # parallel tuple of int
    # Re-route mapping: ripped_net -> {"path": "<summary>", "vias": int,
    #                                   "length_mm": float, "depth": int}
    rerouted: dict = field(default_factory=dict)
    # Cascade depth this attempt reached (1 = rip N foreigners + route N + re-
    # route foreigners; 2 = a re-route itself ripped another net once). R37
    # caps at 2.
    cascade_depth: int = 0
    # Outcome
    committed: bool = False
    rollback_reason: str = ""
    # SHORTS DELTA (R-J5 / G_J5): SHORTS pre-attempt vs SHORTS post-attempt.
    # MUST be <= 0 for the commit to be allowed.
    shorts_pre: int = 0
    shorts_post: int = 0
    # PHASE-SYMMETRIC RIPUP (R39): if any conflict-set net is phase-A/B/C,
    # either {mirrored: True, mirror_pair: (a,b,c)} OR a deviation_log_ref
    # to a routing-lessons L-row or master review note.
    phase_symmetric_mirror_status: str = "N/A"   # "MIRRORED" | "DEVIATION_LOGGED" | "N/A"
    phase_symmetric_peers: tuple = ()
    deviation_log_ref: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def provenance_dir(repo_root: Path) -> Path:
    return repo_root / PROVENANCE_DIR_REL


def write_provenance(entry: TargetedRipupEntry, repo_root: Path) -> Path:
    """Persist an entry under {repo_root}/sims/routing_provenance/targeted_ripup/.
    Filename = `{board_sha}_{blocked_net}_{seq}.json` where seq disambiguates
    multiple attempts on the same net at the same board SHA."""
    d = provenance_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    # Compute a non-clobbering filename
    base = f"{entry.board_sha[:12] or 'NOSHA'}_{entry.blocked_net or 'NONET'}"
    base = re.sub(r"[^A-Za-z0-9_.+-]", "_", base)
    seq = 0
    while True:
        p = d / f"{base}_{seq:03d}.json"
        if not p.exists():
            break
        seq += 1
    p.write_text(entry.to_json())
    return p


def load_provenance(repo_root: Path) -> list[TargetedRipupEntry]:
    """Return all entries in chronological order (by timestamp_iso then file)."""
    d = provenance_dir(repo_root)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            raw = json.loads(p.read_text())
            # Accept dict; reconstruct dataclass with defaults for missing fields
            kwargs = {k: v for k, v in raw.items() if k in TargetedRipupEntry.__dataclass_fields__}
            # Tuples come back as lists from JSON — coerce key tuple fields back
            for tk in ("conflict_set", "conflict_set_priorities",
                       "phase_symmetric_peers"):
                if tk in kwargs and isinstance(kwargs[tk], list):
                    kwargs[tk] = tuple(kwargs[tk])
            out.append(TargetedRipupEntry(**kwargs))
        except Exception as e:
            # A malformed entry MUST surface — never silently skip
            out.append(TargetedRipupEntry(
                schema_version=-1,
                blocked_net=f"<PARSE_ERROR:{p.name}:{type(e).__name__}>"))
    # Sort by timestamp where present (chronological cascade analysis)
    out.sort(key=lambda e: (e.timestamp_iso, e.blocked_net))
    return out


# ============================================================================
# CASCADE-DEPTH GRAPH (R37 / G_J2)
# ============================================================================
# Build a directed graph from the provenance log: rip edge X→N if attempt A
# routed N AND ripped X, and attempt B's re-route of X was itself a targeted
# ripup. A chain depth > 2 = FAIL (R37 cap).

def cascade_depth_violations(entries: Iterable[TargetedRipupEntry]) -> list[tuple[str, int]]:
    """Return [(blocked_net, depth)] for entries whose cascade_depth > 2."""
    bad = []
    for e in entries:
        if not e.committed:
            continue
        if e.cascade_depth > 2:
            bad.append((e.blocked_net, e.cascade_depth))
    return bad


# ============================================================================
# CONFLICT-SET SELECTION (steps 1-3 of the algorithm)
# ============================================================================
# These are LIVE-BOARD helpers used by route_subsystem_cooperative.py at
# attempt time. They are kept here so:
#   (a) the router AND the audits see the SAME definition (anti-drift);
#   (b) they are unit-testable independent of pcbnew (the geom inputs are
#       just (x1,y1,x2,y2,w,layer,netname) tuples — exactly the form
#       `BoardState.track_obstacles_by_layer` produces).

@dataclass
class ConflictCandidate:
    """One foreign-net track/via that intersects the blocked net's ideal path."""
    net: str
    kind: str            # "track" | "via"
    x: float
    y: float
    x2: Optional[float] = None    # tracks only
    y2: Optional[float] = None    # tracks only
    layer: str = ""
    width_mm: float = 0.0
    is_frozen: bool = False       # R38: never rippable
    priority: int = DEFAULT_PRIORITY
    criticality_class: str = DEFAULT_CLASS


def rank_conflict_set_for_rip(candidates: list[ConflictCandidate],
                               blocked_priority: int) -> list[ConflictCandidate]:
    """Step 2 of the 6-step algorithm — choose the smallest subset to rip.

    Heuristic (Sai expansion):
      1. ALWAYS exclude frozen-banked-nets (R38) — they cannot be ripped.
      2. ALWAYS exclude candidates whose priority >= blocked_priority — would
         re-introduce the same problem (rip a higher-criticality net to make
         room for a lower one).
      3. Among the remaining, rank by ALTERNATIVE-RE-ROUTE COUNT proxy =
         (low priority = easy to re-route since it has slack); break ties by
         net criticality (debug>20 before motor>=80).

    Returns the ranked list (lowest priority = first-to-rip). Caller selects
    smallest prefix that clears the blocked net's path.
    """
    rippable = [c for c in candidates
                if not c.is_frozen
                and c.priority < blocked_priority]
    # Sort: lowest priority FIRST (rip debug before bus before motor),
    # then by class name (deterministic; debug<digital_bus<analog<motor<safety).
    rippable.sort(key=lambda c: (c.priority, c.criticality_class, c.net))
    return rippable


def feasibility_alt_reroute_count_proxy(net: str, board_state,
                                         exclude_zones=None) -> int:
    """Step 3 of the 6-step algorithm — lightweight reachability proxy.

    Counts how many "alternative escape directions" the net has if its current
    routing were removed. We use a SURESHOT counting proxy (Sai-locked from
    `[[feedback-sureshot-over-sota]]`): pin count + per-pin-side capacity
    estimate. A net with all pins on one IC side has 1 alternative; a net
    fanning across the board has many. Zero alternatives ⇒ abort the rip
    attempt for the blocked net (cannot fix downstream).

    `board_state` is duck-typed: must expose `.net_pads[netname]` -> list of
    (ref, padname, x, y, layers, sx, sy). `exclude_zones` is reserved for
    future global-router integration; not used in this proxy.
    """
    pads = []
    try:
        pads = board_state.net_pads.get(net, [])
    except Exception:
        return 1
    if not pads:
        return 0
    # Distinct (ref, IC-side-x-bin, IC-side-y-bin) sites — coarse 5mm bins
    sides = set()
    for entry in pads:
        if len(entry) < 4:
            continue
        x, y = entry[2], entry[3]
        sides.add((entry[0], int(x // 5), int(y // 5)))
    return max(1, len(sides))


# ============================================================================
# SELF-TEST (run `python3 targeted_ripup.py`)
# ============================================================================

def _self_test():
    """Sanity checks for the module's primitives — no pcbnew dependency."""
    # Net criticality
    assert net_criticality("KILL_CH1") == (100, "SAFETY")
    assert net_criticality("KILL_RAIL_N_CH1") == (100, "SAFETY")
    assert net_criticality("PWM_INHB_CH1") == (80, "MOTOR_CONTROL")
    assert net_criticality("GLB_CH1") == (80, "MOTOR_CONTROL")
    assert net_criticality("BSTB_CH1") == (80, "MOTOR_CONTROL")
    assert net_criticality("BEMF_A_CH1") == (70, "ANALOG_SENSE")
    assert net_criticality("DSHOT_CH1") == (50, "DIGITAL_BUS")
    assert net_criticality("SWDIO_CH1") == (20, "DEBUG")
    assert net_criticality("NET_RANDOM_FOO")[0] == DEFAULT_PRIORITY
    print("[self-test] net_criticality OK")

    # Frozen banked nets
    assert is_frozen_banked("+VMOTOR") is True
    assert is_frozen_banked("GND") is True
    assert is_frozen_banked("+3V3_CH1") is True
    assert is_frozen_banked("KILL_CH1") is True
    assert is_frozen_banked("PWM_INHB_CH1") is False
    assert is_frozen_banked("") is False
    print("[self-test] is_frozen_banked OK")

    # Phase-peer set
    assert phase_peer_set("GLB_CH1") == ("GLA_CH1", "GLB_CH1", "GLC_CH1")
    assert phase_peer_set("BEMF_C_CH3") == ("BEMF_A_CH3", "BEMF_B_CH3", "BEMF_C_CH3")
    assert phase_peer_set("MOTOR_A_CH2") == ("MOTOR_A_CH2", "MOTOR_B_CH2", "MOTOR_C_CH2")
    assert phase_peer_set("PWM_INHB_CH1") is None  # not in phase-symmetric family
    assert phase_peer_set("KILL_RAIL_N") is None
    print("[self-test] phase_peer_set OK")

    # Rip-set ranking — protect safety/motor, rip debug first
    candidates = [
        ConflictCandidate("KILL_CH1", "track", 0, 0, priority=100,
                          criticality_class="SAFETY", is_frozen=True),
        ConflictCandidate("PWM_INHB_CH1", "track", 0, 0, priority=80,
                          criticality_class="MOTOR_CONTROL"),
        ConflictCandidate("SWDIO_CH1", "track", 0, 0, priority=20,
                          criticality_class="DEBUG"),
        ConflictCandidate("DSHOT_CH1", "track", 0, 0, priority=50,
                          criticality_class="DIGITAL_BUS"),
        ConflictCandidate("+VMOTOR", "track", 0, 0, priority=DEFAULT_PRIORITY,
                          criticality_class=DEFAULT_CLASS, is_frozen=True),
    ]
    ranked = rank_conflict_set_for_rip(candidates, blocked_priority=80)
    # SWDIO (debug, 20) first, then DSHOT (bus, 50); MOTOR excluded by >=
    # KILL excluded by frozen; +VMOTOR excluded by frozen.
    assert [c.net for c in ranked] == ["SWDIO_CH1", "DSHOT_CH1"], \
        f"unexpected rip ranking: {[c.net for c in ranked]}"
    print("[self-test] rank_conflict_set_for_rip OK")

    # Cascade-depth violations
    entries = [
        TargetedRipupEntry(blocked_net="A", committed=True, cascade_depth=1),
        TargetedRipupEntry(blocked_net="B", committed=True, cascade_depth=2),
        TargetedRipupEntry(blocked_net="C", committed=True, cascade_depth=3),
        TargetedRipupEntry(blocked_net="D", committed=False, cascade_depth=5),  # not committed
    ]
    bad = cascade_depth_violations(entries)
    assert bad == [("C", 3)], f"unexpected cascade violations: {bad}"
    print("[self-test] cascade_depth_violations OK")

    # Provenance round-trip in a temp dir
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        e = TargetedRipupEntry(
            timestamp_iso="2026-05-28T00:00:00Z",
            board_sha="abc123def456",
            subsystem="CH1",
            blocked_net="PWM_INHB_CH1",
            blocked_net_priority=80,
            conflict_set=("SWDIO_CH1", "TP19_NET"),
            conflict_set_priorities=(20, 20),
            rerouted={"SWDIO_CH1": {"path": "F.Cu detour", "vias": 1,
                                      "length_mm": 12.3, "depth": 1}},
            cascade_depth=1,
            committed=True,
            shorts_pre=0,
            shorts_post=0,
        )
        p = write_provenance(e, root)
        loaded = load_provenance(root)
        assert len(loaded) == 1
        assert loaded[0].blocked_net == "PWM_INHB_CH1"
        assert loaded[0].conflict_set == ("SWDIO_CH1", "TP19_NET")
        assert loaded[0].rerouted["SWDIO_CH1"]["depth"] == 1
        # Malformed entry surfaces
        (root / PROVENANCE_DIR_REL / "broken.json").write_text("{not valid")
        loaded2 = load_provenance(root)
        assert any(e.schema_version == -1 for e in loaded2), \
            "malformed entry must surface"
    print("[self-test] provenance round-trip OK")

    print("\ntargeted_ripup.py self-test: ALL PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
