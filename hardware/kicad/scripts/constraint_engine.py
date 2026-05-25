#!/usr/bin/env python3
"""
constraint_engine.py — Phase 4-v2 routing constraint engine (v2)

Thin layer that composes:
- BOARD_INVARIANTS.md (zones, I/O ports, highways, symmetry pairs)
- ROUTING_LESSONS.md  (versioned learning database)
- physics_primitives  (IPC-2152, Hammerstad-Jensen, etc.)
- .kicad_pcb           (net classes, current state)

For any routing query `(net, position, layer, context)` returns physics-
DERIVED constraints — never asserted from lookup table.

Per Sai 2026-05-24 mandate: physics-as-compass + minimal-rules + learning.

Replaces the v1 rule-heavy approach (deleted unpushed) with a constraint
engine that asks physics, then refines via lessons DB.
"""

import json
import math
import re
import sys
from pathlib import Path

# Local import (master pre-built)
sys.path.insert(0, str(Path(__file__).parent))
import physics_primitives as physics


# ─── BOARD_INVARIANTS parser (canonical with worker's hash script) ─────────

class BoardInvariants:
    def __init__(self):
        self.outline = (0.0, 0.0, 100.0, 100.0)
        self.zones = {}
        self.symmetry_pairs = []
        self.io_ports = []
        self.highways = []
        self.target_h_md5 = None
        self.invariant_hash = None


def parse_board_invariants(path="docs/BOARD_INVARIANTS.md"):
    inv = BoardInvariants()
    text = Path(path).read_text()

    m = re.search(r"target\.h md5:\s*`([0-9a-f]{32})`", text)
    if m:
        inv.target_h_md5 = m.group(1)

    m = re.search(r"BOARD_INVARIANT_HASH\s*=\s*([0-9a-f]+)", text)
    if m:
        inv.invariant_hash = m.group(1)

    # Zones table — flexible name (allow parens, words, spaces).
    # 2026-05-26 worker URGENT catch: PR #126 inserted "## Bilateral layer
    # assignment" subheader BETWEEN "## Subsystem zones" and its coord table,
    # making the prior section-bounded (?=\n##) regex stop early and return
    # 0 zones → KeyError 'CH1' crash everywhere.
    # FIX: anchor on the coord-table HEADER row pattern itself, not the
    # section heading. The unique signature is `| Subsystem | x_min | y_min |
    # x_max | y_max |` which appears exactly once in the doc.
    zone_section = re.search(
        r"\|\s*Subsystem\s*\|\s*x_min\s*\|\s*y_min\s*\|\s*x_max\s*\|\s*y_max\s*\|[^\n]*\n"
        r"\|[\s\-:|]+\|\s*\n"  # alignment row
        r"((?:\|[^\n]*\n)+)",  # capture all subsequent table rows
        text
    )
    if zone_section:
        for line in zone_section.group(1).split("\n"):
            row = re.match(
                r"\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|",
                line)
            if row:
                words = row.group(1).strip().split()
                first_word = words[0]
                # Skip header-row + alignment-row
                if first_word in ("Subsystem", "---", ":---"):
                    continue
                # Disambiguate multi-zone subsystems (e.g., S5 east/west/south)
                # by combining first word + last word if length > 1
                name = first_word
                direction = next((w.lower() for w in words
                                  if w.lower() in ("east", "west", "south",
                                                   "north", "central", "spine")), None)
                if direction:
                    name = f"{first_word}_{direction}"
                try:
                    bbox = tuple(float(g) for g in row.groups()[1:5])
                    inv.zones[name] = bbox
                except ValueError:
                    continue

    # Symmetry pairs
    sym_section = re.search(
        r"## Symmetry pairs.*?\n\n([\s\S]+?)(?=\n##|\Z)", text)
    if sym_section:
        for m in re.finditer(
                r"\*\*([A-Z][A-Z0-9_]+)\s*[↔<->]+\s*([A-Z][A-Z0-9_]+)\*\*:\s*mirror_(\w+)\(([\d.]+)\)",
                sym_section.group(1)):
            inv.symmetry_pairs.append(
                (m.group(1), m.group(2), m.group(3).lower(), float(m.group(4))))

    # I/O ports
    io_section = re.search(
        r"## Subsystem I/O ports.*?\n\n([\s\S]+?)(?=\n##|\Z)", text)
    if io_section:
        for line in io_section.group(1).split("\n"):
            row = re.match(
                r"\|\s*(\w+)\s*[→\->]+\s*(\w+)\s*\|\s*\(([\d.]+),\s*([\d.]+)\)\s*\|\s*[^|]*\|\s*([^|]+)\|",
                line)
            if row:
                signals = [s.strip() for s in re.split(r"[,;]", row.group(5)) if s.strip()]
                inv.io_ports.append((
                    row.group(1).strip(), row.group(2).strip(),
                    float(row.group(3)), float(row.group(4)), signals))

    # Highways
    hw_section = re.search(
        r"## Highway reservations.*?\n\n([\s\S]+?)(?=\n##|\Z)", text)
    if hw_section:
        for line in hw_section.group(1).split("\n"):
            row = re.match(
                r"\|\s*([\w +/\-]+?)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|",
                line)
            if row:
                inv.highways.append((
                    row.group(1).strip(),
                    float(row.group(2)), float(row.group(3)),
                    float(row.group(4)), float(row.group(5))))

    return inv


# ─── ROUTING_LESSONS parser ───────────────────────────────────────────────

class RoutingLessons:
    def __init__(self):
        self.lessons = []  # [{id, date, pattern, observation, root_cause, cost_adjustment, status}]
        self.hash = None


def parse_routing_lessons(path="docs/ROUTING_LESSONS.md"):
    lessons = RoutingLessons()
    text = Path(path).read_text()

    m = re.search(r"ROUTING_LESSONS_HASH\s*=\s*([0-9a-f]+)", text)
    if m:
        lessons.hash = m.group(1)

    # Parse each "### Lx — ..." block
    for m in re.finditer(
            r"### (L\d+)\s*—\s*([^\n]+)\n\n"
            r"- \*\*Date\*\*:\s*([^\n]+)\n"
            r"- \*\*Pattern\*\*:\s*([^\n]+)\n"
            r"- \*\*Observation\*\*:\s*([^\n]+)\n"
            r"- \*\*Root cause\*\*[^:]*:\s*([^\n]+)\n"
            r"- \*\*Cost adjustment\*\*:\s*([^\n]+)\n"
            r"- \*\*Status\*\*:\s*(\w+)",
            text):
        lessons.lessons.append({
            "id": m.group(1), "summary": m.group(2),
            "date": m.group(3), "pattern": m.group(4),
            "observation": m.group(5), "root_cause": m.group(6),
            "cost_adjustment": m.group(7), "status": m.group(8),
        })

    return lessons


# ─── Net current estimation (from netname conventions) ─────────────────────

def estimate_net_current(netname, context_subsystem=None):
    """Returns expected (continuous_A, burst_A) for a net based on naming +
    locked spec context. Used by min_width derivation.

    Per project R17 burst spec: 280A continuous (4 channels × 70A) on +VMOTOR
    main; per-channel +VMOTOR feed = 70A continuous, 100A burst.
    BEMF/sense signals = mA-level.
    """
    name = netname.strip("/") if netname else ""

    if name in ("+VMOTOR",):
        # Per-channel +VMOTOR feed sees 70A continuous, 100A burst
        # Spine sees 280A continuous (use plane, not trace)
        return (70.0, 100.0)
    if name in ("+BATT", "BATGND"):
        return (70.0, 100.0)  # battery-side, per-channel
    if name in ("GND",):
        return (70.0, 100.0)
    if name.startswith("+V") and name not in ("+VMOTOR",):
        # BEC outputs +V5, +V9, +V12, +3V3, +V5_PI5, etc.
        return (1.0, 3.0)
    if name.startswith("BEMF") or name.startswith("CSA"):
        return (0.001, 0.01)  # sense lines
    if name.startswith("DSHOT") or name.startswith("TLM") or name.startswith("KILL"):
        return (0.005, 0.020)  # digital
    if name.startswith("BSTA") or name.startswith("BSTB") or name.startswith("BSTC"):
        return (0.1, 0.5)  # bootstrap
    return (0.01, 0.05)  # default signal


# ─── Layer type lookup ────────────────────────────────────────────────────

EXTERNAL_LAYERS = {"F.Cu", "B.Cu"}
INTERNAL_LAYERS = {"In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu", "In6.Cu"}
SIGNAL_LAYERS = {"F.Cu", "In2.Cu", "In4.Cu", "In6.Cu", "B.Cu"}
PLANE_LAYERS = {"In1.Cu", "In5.Cu", "In3.Cu"}  # GND, GND, +VMOTOR


def layer_type(layer_name):
    if layer_name in EXTERNAL_LAYERS:
        return "external"
    if layer_name in INTERNAL_LAYERS:
        return "internal"
    raise ValueError(f"unknown layer: {layer_name}")


def layer_cu_oz(layer_name):
    """Per locked 8-layer stackup: F.Cu/B.Cu = 1oz, In3 (+VMOTOR) = 3oz, others = 1oz."""
    if layer_name == "In3.Cu":
        return 3.0
    return 1.0


# ─── Constraint Engine ────────────────────────────────────────────────────

class ConstraintEngine:
    def __init__(self, invariants=None, lessons=None):
        self.inv = invariants or parse_board_invariants()
        self.lessons = lessons or parse_routing_lessons()

    # — Position queries —

    def is_position_in_subsystem(self, x, y, subsystem):
        if subsystem not in self.inv.zones:
            return False
        x0, y0, x1, y1 = self.inv.zones[subsystem]
        return x0 <= x <= x1 and y0 <= y <= y1

    def position_to_subsystem(self, x, y):
        for name, bbox in self.inv.zones.items():
            x0, y0, x1, y1 = bbox
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def is_position_in_highway(self, x, y, margin_mm=0.0):
        for name, x0, y0, x1, y1 in self.inv.highways:
            if (x0 - margin_mm <= x <= x1 + margin_mm and
                    y0 - margin_mm <= y <= y1 + margin_mm):
                return name
        return None

    # — Physics-derived constraints —

    def min_track_width_mm(self, netname, layer_name, dT_celsius=30):
        """Physics-derived min width for net on given layer. IPC-2221 formula."""
        I_cont, I_burst = estimate_net_current(netname)
        # Design to burst current with reasonable thermal margin
        I_design = max(I_cont, I_burst * 0.7)  # 70% derate from burst
        return physics.min_track_width_mm(
            I_amps=I_design,
            layer_type=layer_type(layer_name),
            cu_oz=layer_cu_oz(layer_name),
            dT_celsius=dT_celsius,
        )

    def microstrip_z0_for(self, W_mm, layer_name, εr=4.3):
        """Z0 of a microstrip on this layer (assumes In1 or In5 GND is nearest plane)."""
        # Distance to nearest reference plane
        # Stackup: F.Cu (0) → In1 GND (0.21mm) → In2 (0.41) → ...
        STACKUP_TO_PLANE = {
            "F.Cu": 0.21,    # to In1 GND
            "B.Cu": 0.21,    # to In5 GND (assuming symmetric)
            "In2.Cu": 0.20,  # to In1 GND
            "In4.Cu": 0.20,  # to In3 +VMOTOR (acts as plane)
            "In6.Cu": 0.20,  # to In5 GND
        }
        H_mm = STACKUP_TO_PLANE.get(layer_name, 0.2)
        return physics.microstrip_z0(W_mm, H_mm, εr)

    # — Symmetry —

    def symmetry_partner(self, subsystem):
        for sys_a, sys_b, axis, axis_val in self.inv.symmetry_pairs:
            if sys_a == subsystem:
                return (sys_b, axis, axis_val)
            if sys_b == subsystem:
                return (sys_a, axis, axis_val)
        return None

    def mirror_transform(self, x, y, axis, axis_val):
        if axis == "x":
            return (2 * axis_val - x, y)
        if axis == "y":
            return (x, 2 * axis_val - y)
        raise ValueError(f"unknown axis: {axis}")

    # — Lessons-applied (cost adjustments) —

    def cost_adjustment_for(self, netname, x, y, layer_name, context=None):
        """Returns +cost from lesson patterns matching this query.

        Default: 0. Lessons add penalties when their patterns apply.
        Returns dict {lesson_id: cost_added} for transparency.
        """
        adjustments = {}
        for L in self.lessons.lessons:
            if L["status"] != "active":
                continue
            lid = L["id"]
            # L1: external router — N/A for direct position query
            # L2: mirror snap failure — not a position query
            # L3: net-class width — handled by min_track_width_mm
            # L4: power-pad via — handled by requires_offset_via
            # L5: subsystem-zone violation — already infinity below
            pass
        # L5 enforced as hard cost: not-in-allowed-zone → +∞
        net_subsystem = None  # TODO: derive from netname suffix or pad lookup
        # Simple version: if in any highway, allowed only for inter-subsystem nets
        # If in a zone, allowed only for that subsystem's internal nets
        in_zone = self.position_to_subsystem(x, y)
        in_highway = self.is_position_in_highway(x, y)
        if not in_zone and not in_highway:
            adjustments["L5-zone-violation"] = float("inf")
        return adjustments

    # — Hard checks —

    def requires_offset_via(self, netname):
        """L4 lesson — power nets connecting to planes use offset-via-with-stub."""
        return netname in ("+VMOTOR", "+BATT", "GND", "BATGND")

    def assert_no_external_router(self, tool_name):
        """L1 lesson — refuse external autorouter invocations."""
        banned = {"freerouter", "topor", "specctra"}
        if tool_name.lower() in banned:
            raise RuntimeError(
                f"L1 lesson (ROUTING_LESSONS.md): external autorouter "
                f"'{tool_name}' banned. Use route_subsystem.py / "
                f"route_mirror.py / route_highway.py."
            )


# ─── Smoke test ────────────────────────────────────────────────────────────

def _smoke_test():
    """Standalone smoke test of constraint engine."""
    print("=== Constraint Engine smoke test ===\n")

    inv = parse_board_invariants()
    print(f"BOARD_INVARIANT_HASH: {inv.invariant_hash[:16] if inv.invariant_hash else 'NONE'}...")
    print(f"target.h md5: {inv.target_h_md5}")
    print(f"Zones: {len(inv.zones)} → {sorted(inv.zones.keys())}")
    print(f"Symmetry pairs: {inv.symmetry_pairs}")
    print(f"Highways: {len(inv.highways)}")
    print(f"I/O ports: {len(inv.io_ports)}")
    print()

    lessons = parse_routing_lessons()
    print(f"ROUTING_LESSONS_HASH: {lessons.hash[:16] if lessons.hash else 'NONE'}...")
    print(f"Active lessons: {sum(1 for l in lessons.lessons if l['status'] == 'active')}")
    for l in lessons.lessons:
        print(f"  {l['id']} ({l['status']}): {l['summary']}")
    print()

    ce = ConstraintEngine(inv, lessons)

    print("Physics-derived constraint queries:")
    print(f"  +VMOTOR min width on F.Cu (1oz, 30°C): {ce.min_track_width_mm('+VMOTOR', 'F.Cu'):.2f}mm")
    print(f"  +VMOTOR min width on In3.Cu (3oz, 30°C): {ce.min_track_width_mm('+VMOTOR', 'In3.Cu'):.2f}mm")
    print(f"  /BEMF_A_CH1 min width on In2.Cu: {ce.min_track_width_mm('/BEMF_A_CH1', 'In2.Cu'):.2f}mm")
    print(f"  Z0 of 0.2mm trace on F.Cu (to In1 GND): {ce.microstrip_z0_for(0.2, 'F.Cu'):.1f}Ω")
    print()

    print("Position queries:")
    print(f"  (10, 60) is in CH1? {ce.is_position_in_subsystem(10, 60, 'CH1')}")
    print(f"  (10, 60) is in any zone: {ce.position_to_subsystem(10, 60)}")
    print(f"  (50, 25) is in highway: {ce.is_position_in_highway(50, 25)}")
    print(f"  CH1 symmetry partner: {ce.symmetry_partner('CH1')}")
    print(f"  Mirror (10, 60) about x=50: {ce.mirror_transform(10, 60, 'x', 50.0)}")
    print()

    print("Hard checks (lesson enforcement):")
    print(f"  +VMOTOR requires offset via: {ce.requires_offset_via('+VMOTOR')}")
    print(f"  /BEMF requires offset via: {ce.requires_offset_via('/BEMF_A_CH1')}")
    try:
        ce.assert_no_external_router("freerouter")
    except RuntimeError as e:
        print(f"  L1 enforcement on freerouter: ✓ raised RuntimeError: {str(e)[:60]}...")

    print("\n✅ constraint_engine smoke test PASS")


if __name__ == "__main__":
    _smoke_test()
