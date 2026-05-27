#!/usr/bin/env python3
"""route_subsystem_cooperative.py — Cooperative ripup-reroute maze router for
dense IC-escape cascades on 10L stackup.

Per [[reference-cascading-escape-needs-negotiated-routing]] (2026-05-27):
greedy A* self-congests on dense pin-out cascades — each net's escape tracks
block the next net's via spots. Worker R26 hit this on J18 (AT32F421 QFN-32)
+ J19 (DRV8300DRGER QFN-24) CH1 fan-in: 3/9 nets routed then PLATEAUED.

Algorithm (Pathfinder/PathSearch family, after McMurchie+Ebeling 1995):
  Loop over iterations:
    For each unrouted net (priority order):
      A* search on grid with present-congestion cost
      If route found: commit (mark grid cells as used, increment historical
        congestion for any cell already shared)
      If route fails: skip; rip up no nets this pass
    After pass: if any failures remain, RIP-UP all nets sharing congested
      cells (history > threshold) AND re-queue them at higher priority for
      next iteration.
    Bump congestion weight (present_factor *= 1.4) each iteration —
      drives nets to spread out.
  Terminate: all routed OR max-iterations OR plateau (no progress 3 passes).

QFN/LQFP pad-fanout primitive (pad-stub + via):
  Pad is small (0.25×0.88mm typical for J18 QFN-32 0.5mm pitch). Direct
  via-in-pad infeasible. Standard:
    pad (F.Cu) -> short 0.5mm stub on F.Cu (perpendicular to pad axis,
    away from package body) -> via 0.6/0.3mm at stub end -> escape on
    inner layer.

Layer allocation (CH1 STEP-6 plan locked 2026-05-27 per dispatch):
  F.Cu / B.Cu : pad-fanout stubs ≤0.6mm + short island traces
  In2.Cu      : PRIMARY escape — PWM (SI-critical), CSA_OUT (analog SI), dense fan-in
  In4.Cu      : DEDICATED BEMF (OQ-016 lock; In3 + In5 plane shields)
  In6.Cu      : SW escape per OQ-017 (commutation already routed; spare capacity)
  In8.Cu      : ESCAPE-LAYER overflow per PR #192 multi-use (SWD/NRST/BOOT0/kill/VREF)
  In1/In3/In7 : GND planes — UNTOUCHED
  In5         : +VMOTOR plane — UNTOUCHED

Constraints:
  - DRC: trace ≥0.15mm (signal) ≥0.20mm (gate-drive), via 0.3/0.6mm,
    clearance ≥0.15mm board-min
  - Power-class nets (VMOTOR/MOTOR/SHUNT_TOP, +V*, GND) untouched
  - Existing tracks/vias/pads on OTHER nets are immovable obstacles
  - Custom DRU NC-net clearance exemption applies (see pcbai_fpv4in1.kicad_dru)

Usage:
  python3 route_subsystem_cooperative.py <board.kicad_pcb> \
    --subsystem CH1 \
    --output <routed.kicad_pcb> \
    [--max-iterations 30] [--grid-pitch 0.1] [--seed-nets <comma-list>]

Exit 0 if all target nets routed, 1 if any unrouted (with diagnostics).

Reusable for CH1 STEP-6 J18/J19 fan-in + CH2/3/4 mirror routing +
future dense subsystem escapes (S3 supervisor, S5 BEC if congested).

Master 2026-05-27 R26 dispatch — replaces greedy escape line.
"""
from __future__ import annotations

import argparse
import heapq
import math
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    import pcbnew
except ImportError:  # pragma: no cover
    sys.stderr.write("FATAL: pcbnew not importable (run inside KiCad python)\n")
    sys.exit(2)


# ─── Configuration ────────────────────────────────────────────────────────

# Default grid pitch (mm). 0.1mm = 100µm. CH1 zone 35×39mm => 350×390 cells per layer.
# 5 routing layers => ~680K cells. ~50 MB Python dict on Pi. Fits Pi memory budget.
DEFAULT_GRID_PITCH = 0.1
DEFAULT_MAX_ITER = 30

# Layer IDs (from pcbnew)
F_CU = pcbnew.F_Cu       # 0
B_CU = pcbnew.B_Cu       # 2
IN2_CU = pcbnew.In2_Cu   # 6  — primary escape
IN4_CU = pcbnew.In4_Cu   # 10 — BEMF dedicated
IN6_CU = pcbnew.In6_Cu   # 14 — SW (mostly used by commutation already)
IN8_CU = pcbnew.In8_Cu   # 18 — overflow / SWD / control

# Layers we may route on (in order of preference for layer-cost)
SIGNAL_LAYERS = [F_CU, B_CU, IN2_CU, IN4_CU, IN6_CU, IN8_CU]

# Net classification -> preferred inner-layer escape (highest priority first)
LAYER_PREF = [
    (re.compile(r"^BEMF_[ABC]_CH\d+$"), [IN4_CU, IN2_CU]),
    (re.compile(r"^PWM_(IN[HL][ABC])_CH\d+$"), [IN2_CU, IN8_CU]),
    (re.compile(r"^CSA_[ABC]_OUT_CH\d+$"), [IN2_CU, IN8_CU]),
    (re.compile(r"^CSA_MAX_CH\d+$"), [IN2_CU, IN8_CU]),
    (re.compile(r"^SW(DIO|CLK)_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^NRST_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^BOOT0_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^LED_GPIO_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^(I|OTP)_TRIP_N_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^KILL_(LOCAL|RAIL|LED_NODE)_(N_)?CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^VREF_(I_TRIP|OTP)_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^GH[ABC]_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^GL[ABC]_CH\d+$"), [IN8_CU, IN2_CU]),
    (re.compile(r"^BST[ABC]_CH\d+$"), [IN8_CU, IN2_CU]),
]
DEFAULT_INNER_LAYERS = [IN8_CU, IN2_CU]  # fallback

# Priority bucket (lower=route earlier). High-fanin / SI-critical first.
def net_priority(net_name: str) -> int:
    # 0: highest priority (BEMF analog, CSA analog)
    if re.match(r"^BEMF_[ABC]_CH\d+$", net_name): return 0
    if re.match(r"^CSA_[ABC]_OUT_CH\d+$", net_name): return 0
    if re.match(r"^CSA_MAX_CH\d+$", net_name): return 0
    # 1: dense fan-in PWM
    if re.match(r"^PWM_IN[HL][ABC]_CH\d+$", net_name): return 1
    # 2: gate drive (short hops)
    if re.match(r"^G[HL][ABC]_CH\d+$", net_name): return 2
    if re.match(r"^BST[ABC]_CH\d+$", net_name): return 2
    # 3: control / debug
    if re.match(r"^SW(DIO|CLK)_CH\d+$", net_name): return 3
    if re.match(r"^NRST_CH\d+$", net_name): return 3
    if re.match(r"^BOOT0_CH\d+$", net_name): return 3
    if re.match(r"^(I|OTP)_TRIP_N_CH\d+$", net_name): return 3
    if re.match(r"^KILL_", net_name): return 3
    if re.match(r"^VREF_", net_name): return 3
    if re.match(r"^LED_GPIO_CH\d+$", net_name): return 3
    return 4

# Widths per net pattern (mm)
WIDTH_RULES = [
    (re.compile(r"^G[HL][ABC]_CH\d+$"), 0.20),     # gate drive
    (re.compile(r"^BST[ABC]_CH\d+$"), 0.20),       # bootstrap
    (re.compile(r"^PWM_IN[HL][ABC]_CH\d+$"), 0.15),
    (re.compile(r"^BEMF_[ABC]_CH\d+$"), 0.15),
    (re.compile(r"^CSA_"), 0.15),
]
DEFAULT_WIDTH = 0.15

def width_for(net_name: str) -> float:
    for pat, w in WIDTH_RULES:
        if pat.match(net_name): return w
    return DEFAULT_WIDTH

def inner_layers_for(net_name: str):
    for pat, layers in LAYER_PREF:
        if pat.match(net_name): return list(layers)
    return list(DEFAULT_INNER_LAYERS)

# Skip these nets entirely (power / plane / handled-elsewhere by other PRs)
SKIP_NET_PATTERNS = [
    re.compile(r"^GND$"), re.compile(r"^BATGND$"),
    re.compile(r"^\+VMOTOR"), re.compile(r"^VMOTOR_CH"),
    re.compile(r"^MOTOR_[ABC]_CH\d+$"),
    re.compile(r"^SHUNT_[ABC]_TOP_CH\d+$"),
    re.compile(r"^\+V"),                 # +V5_FC / +V5_AI / +V9_VTX...
    re.compile(r"^\+3V"),                # +3V3 / +3V3A
    re.compile(r"^V3V3"),                # V3V3A
    re.compile(r"^V_BUCK"),
    re.compile(r"^HALL_VCC"),
    re.compile(r"^VBAT_SENSE"),
    re.compile(r"^\+BATT"),
    re.compile(r"^TLM$"), re.compile(r"^BUS_CURR_HALL_OUT$"),
    re.compile(r"^M1_CLEAN$"), re.compile(r"^M1_HALL"),  # Hall sensor nets
    re.compile(r"^NTC"),                  # thermistor sense
    re.compile(r"^VREF_2V5$"),            # global VREF — cross-subsystem (S3 generates)
    re.compile(r"^KILL_LED_NODE_CH\d+$"), # LED node — bilateral B.Cu, leave for later
    re.compile(r"^M[1-4]_CLEAN$"), re.compile(r"^M[1-4]_HALL"),
    re.compile(r"^NC$"), re.compile(r"_NC_CH\d+$"),  # NC nets — no routing
    re.compile(r"^N\$"),                  # unnamed
    re.compile(r"^Net-"),
    re.compile(r"^unconnected"),
]

def should_route(net_name: str) -> bool:
    if not net_name: return False
    for pat in SKIP_NET_PATTERNS:
        if pat.search(net_name): return False
    return True

# Constants
PAD_FANOUT_MM = 0.5     # length of pad-out stub before via drop
VIA_DRILL_MM = 0.3
VIA_DIAM_MM = 0.6
CLEARANCE_MM = 0.20     # board-min ≥0.20 (audit_power_drc HIGH_CURRENT_CLEARANCE_MM)
VIA_CLEAR_MM = 0.20
TRACE_HALF_MM = 0.08    # 0.15mm trace / 2 + small margin
GRID_SLOP_MM = 0.025    # extra halo to compensate grid-cell discretization (=pitch/4)
# halo total = 0.305mm pad-edge keepout for foreign-net cells.
# At 0.5mm QFN pitch with 0.125mm pad-half, between-pad gap = 0.25mm < 2×halo => no trace between
# adjacent QFN pads (must escape perpendicular only — correct dog-bone topology).

# A* tunables
LAYER_CHANGE_COST = 5.0       # via penalty (was 30 — too high vs free inner layer)
LAYER_BASE_COST = {           # per-step base cost by layer
    F_CU: 4.0,                # discourage long F.Cu signal routes (conflicts with bilateral pads)
    B_CU: 4.0,                # same
    IN2_CU: 1.0,              # PRIMARY signal escape
    IN4_CU: 1.0,              # BEMF dedicated
    IN6_CU: 1.5,              # SW already routed; mild bias against
    IN8_CU: 1.0,              # OVERFLOW/SWD layer
}
PRESENT_COST_BASE = 0.0       # baseline included in LAYER_BASE_COST now
PRESENT_COST_FACTOR_INIT = 1.0
PRESENT_COST_FACTOR_GROWTH = 1.4
HISTORY_COST_INIT = 0.0
HISTORY_COST_INC = 1.0
HEURISTIC_WEIGHT = 1.2        # >1 → weighted A*: faster, slightly sub-optimal paths


# Subsystem zones (replicated from BOARD_INVARIANTS for self-containment)
SUBSYSTEM_ZONES = {
    'CH1': (0, 50, 35, 89),
    'CH2': (65, 50, 100, 89),
    'CH3': (65, 11, 100, 50),
    'CH4': (0, 11, 35, 50),
}


# ─── Helpers ──────────────────────────────────────────────────────────────

def mm_to_iu(mm: float) -> int:
    return int(round(mm * 1e6))

def iu_to_mm(iu: int) -> float:
    return iu / 1e6


def layer_short_name(layer_id: int) -> str:
    return {F_CU: "F.Cu", B_CU: "B.Cu", IN2_CU: "In2.Cu",
            IN4_CU: "In4.Cu", IN6_CU: "In6.Cu", IN8_CU: "In8.Cu"}.get(layer_id, f"L{layer_id}")


# ─── Board state extraction ───────────────────────────────────────────────

class BoardState:
    """Inventory pads, tracks, vias, zones from a loaded board."""

    def __init__(self, board, zone_bbox):
        self.board = board
        self.zone = zone_bbox  # (xmin,ymin,xmax,ymax)
        self.net_pads = defaultdict(list)        # netname -> [(ref, padname, x, y, layers, pad_size_x, pad_size_y)]
        self.net_obj = {}                        # netname -> NETINFO_ITEM
        # Obstacles per layer: list of (x,y,radius_mm, owner_netname)
        # Used during congestion grid build
        self.pad_obstacles_by_layer = defaultdict(list)
        self.track_obstacles_by_layer = defaultdict(list)  # (x1,y1,x2,y2,width_mm,owner)
        self.via_obstacles = []                            # (x,y,diam_mm,owner)
        self.zone_obstacles_by_layer = defaultdict(list)   # (poly_pts, owner)  — not used; treated soft via congestion

        self._collect()

    def _collect(self):
        b = self.board
        # Pads
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                netobj = pad.GetNet()
                netname = netobj.GetNetname() if netobj else ""
                p = pad.GetPosition()
                x = iu_to_mm(p.x); y = iu_to_mm(p.y)
                sz = pad.GetSize()
                sx = iu_to_mm(sz.x); sy = iu_to_mm(sz.y)
                ls = pad.GetLayerSet()
                layers = []
                for lid in SIGNAL_LAYERS:
                    if ls.Contains(lid): layers.append(lid)
                # If pad is on ALL copper layers (through-hole), include all signal layers
                if netname:
                    self.net_pads[netname].append((fp.GetReference(), pad.GetPadName(), x, y, layers, sx, sy))
                    if netobj and netname not in self.net_obj:
                        self.net_obj[netname] = netobj
                # Pad obstacle stored as (x, y, half_x, half_y, owner_net, padid).
                # Stamping in grid uses ELLIPTICAL keepout: actual pad bbox + clearance.
                # For SAME-net routing the pad cells become accessible.
                hx = sx / 2; hy = sy / 2
                for lid in layers:
                    self.pad_obstacles_by_layer[lid].append((x, y, hx, hy, netname or "<NC>", fp.GetReference()+"."+pad.GetPadName()))

        # Tracks + vias
        for t in b.GetTracks():
            netname = t.GetNetname()
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                x = iu_to_mm(p.x); y = iu_to_mm(p.y)
                # Use drill+clearance as effective keep-out
                diam = VIA_DIAM_MM  # default via diameter for keep-out
                try:
                    # KiCad 9: PCB_VIA.GetWidth(layer)
                    w = iu_to_mm(t.GetWidth(t.TopLayer()))
                    diam = max(diam, w)
                except (TypeError, Exception):
                    try:
                        w = iu_to_mm(t.GetDrillValue()) + 0.2  # drill + ring
                        diam = max(diam, w)
                    except Exception:
                        pass
                self.via_obstacles.append((x, y, diam/2 + CLEARANCE_MM, netname))
            else:
                s = t.GetStart(); e = t.GetEnd()
                x1 = iu_to_mm(s.x); y1 = iu_to_mm(s.y)
                x2 = iu_to_mm(e.x); y2 = iu_to_mm(e.y)
                w = iu_to_mm(t.GetWidth())
                self.track_obstacles_by_layer[t.GetLayer()].append((x1, y1, x2, y2, w, netname))

        # Zones (treat as soft obstacles — heavy penalty but not blocking)
        # We don't fully expand zone polys here; the zone fills mostly affect F/B.Cu
        # MOTOR / SHUNT zones on F.Cu. Treat their poly bbox as soft cost.
        for z in list(b.Zones()):
            netname = z.GetNetname()
            layer = z.GetLayer()
            try:
                bb = z.GetBoundingBox()
                xmin = iu_to_mm(bb.GetX()); ymin = iu_to_mm(bb.GetY())
                xmax = xmin + iu_to_mm(bb.GetWidth()); ymax = ymin + iu_to_mm(bb.GetHeight())
                self.zone_obstacles_by_layer[layer].append((xmin, ymin, xmax, ymax, netname))
            except Exception:
                pass

    def net_pads_in_zone(self, netname):
        """Return pads of net within the subsystem zone."""
        xmin, ymin, xmax, ymax = self.zone
        return [p for p in self.net_pads.get(netname, [])
                if xmin <= p[2] <= xmax and ymin <= p[3] <= ymax]

    def routable_nets(self):
        """Find nets that have ≥2 pads in zone AND need routing AND are unrouted."""
        out = []
        for nn, pads in self.net_pads.items():
            if not should_route(nn): continue
            in_zone = [p for p in pads if self.zone[0] <= p[2] <= self.zone[2]
                                       and self.zone[1] <= p[3] <= self.zone[3]]
            # Also include nets where SOME pads are in zone (channel-internal)
            if len(in_zone) >= 2:
                # Skip nets already substantially routed (>=2 tracks)
                tracks_on_net = sum(1 for lid_tracks in self.track_obstacles_by_layer.values()
                                    for (_,_,_,_,_,owner) in lid_tracks if owner == nn)
                if tracks_on_net >= 2:
                    continue
                out.append(nn)
        return out


# ─── Congestion grid ───────────────────────────────────────────────────────

class CongestionGrid:
    """3D occupancy + congestion grid (x, y, layer).

    Cell (i, j, L):
      - obstacle: hard-block (pad/track/via owned by OTHER net) — cannot traverse
      - present: number of nets currently using this cell (≥1 => conflict for new net)
      - history: accumulated congestion penalty from past iterations
    """

    def __init__(self, zone_bbox, pitch_mm, layers):
        self.xmin, self.ymin, self.xmax, self.ymax = zone_bbox
        self.pitch = pitch_mm
        self.layers = list(layers)
        self.nx = int(math.ceil((self.xmax - self.xmin) / pitch_mm)) + 1
        self.ny = int(math.ceil((self.ymax - self.ymin) / pitch_mm)) + 1
        # dicts keyed by (i,j,L). Absent => default 0 / False.
        self.obstacle = set()     # (i,j,L) -> blocked for ALL nets (pad copper, track core)
        self.present = defaultdict(int)   # (i,j,L) -> count of nets routing here this iter
        self.history = defaultdict(float) # (i,j,L) -> historic congestion
        self.cell_owners = defaultdict(set)  # (i,j,L) -> {netname,...}
        # Pad-cell map: cell -> netname when cell is a pad endpoint we permit access for that net
        self.pad_cells = defaultdict(set)  # (i,j,L) -> {netnames whose pads occupy this cell}
        # Owner-net halo: cell -> set of net names that OWN this cell as clearance halo.
        # Blocked for ALL OTHER nets; accessible to listed nets.
        self.net_halo = defaultdict(set)  # (i,j,L) -> {netnames}
        # Via-forbidden zones: cells too close to a pad to host a via (clearance)
        self.via_forbidden_zones = {}  # (i,j,L) -> {netnames}

    def in_bounds(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.ny

    def cell_xy(self, i, j):
        return (self.xmin + i * self.pitch, self.ymin + j * self.pitch)

    def xy_to_ij(self, x, y):
        i = int(round((x - self.xmin) / self.pitch))
        j = int(round((y - self.ymin) / self.pitch))
        return i, j

    def stamp_obstacle_circle(self, x, y, r, layer):
        """Mark all cells within radius r of (x,y) on layer as obstacle."""
        if layer not in self.layers: return
        i0, j0 = self.xy_to_ij(x, y)
        n = int(math.ceil(r / self.pitch))
        r2 = r * r
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i = i0 + di; j = j0 + dj
                if not self.in_bounds(i, j): continue
                cx, cy = self.cell_xy(i, j)
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    self.obstacle.add((i, j, layer))

    def stamp_obstacle_rect(self, cx, cy, hx, hy, layer):
        """Mark all cells inside rectangle [cx±hx, cy±hy] on layer as obstacle."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(cx - hx, cy - hy)
        i_max, j_max = self.xy_to_ij(cx + hx, cy + hy)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                pcx, pcy = self.cell_xy(i, j)
                if abs(pcx - cx) <= hx and abs(pcy - cy) <= hy:
                    self.obstacle.add((i, j, layer))

    def stamp_halo_rect(self, cx, cy, hx, hy, layer, owner_net):
        """Mark cells in rect as net_halo[owner]: blocked for other nets only."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(cx - hx, cy - hy)
        i_max, j_max = self.xy_to_ij(cx + hx, cy + hy)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                pcx, pcy = self.cell_xy(i, j)
                if abs(pcx - cx) <= hx and abs(pcy - cy) <= hy:
                    self.net_halo[(i, j, layer)].add(owner_net)

    def stamp_obstacle_segment(self, x1, y1, x2, y2, w, layer):
        """Mark all cells within w/2 + clearance + trace_half + slop of segment as obstacle on layer.
        Ensures new trace edge stays ≥CLEARANCE_MM from this existing segment edge."""
        if layer not in self.layers: return
        half = w / 2 + CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
        # Bounding box of segment + half
        xa, xb = min(x1, x2), max(x1, x2)
        ya, yb = min(y1, y2), max(y1, y2)
        i_min, j_min = self.xy_to_ij(xa - half, ya - half)
        i_max, j_max = self.xy_to_ij(xb + half, yb + half)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        half2 = half * half
        # Vector for segment
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-12:
            # zero-length segment; treat as circle
            self.stamp_obstacle_circle(x1, y1, half, layer)
            return
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                cx, cy = self.cell_xy(i, j)
                # Project (cx,cy) onto segment
                tt = ((cx - x1) * dx + (cy - y1) * dy) / seg_len2
                tt = max(0.0, min(1.0, tt))
                px = x1 + tt * dx; py = y1 + tt * dy
                if (cx - px) ** 2 + (cy - py) ** 2 <= half2:
                    self.obstacle.add((i, j, layer))

    def stamp_obstacle_zone_bbox(self, x1, y1, x2, y2, layer, soft=True):
        """Mark cells inside zone bbox. If soft, only add to history (not obstacle)."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(x1, y1)
        i_max, j_max = self.xy_to_ij(x2, y2)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                if soft:
                    self.history[(i, j, layer)] += 0.5
                else:
                    self.obstacle.add((i, j, layer))

    def allow_pad_access_rect(self, x, y, layer, netname, hx, hy):
        """Mark all cells inside pad copper rect as accessible to netname."""
        if layer not in self.layers: return
        i_min, j_min = self.xy_to_ij(x - hx, y - hy)
        i_max, j_max = self.xy_to_ij(x + hx, y + hy)
        i_min = max(0, i_min); j_min = max(0, j_min)
        i_max = min(self.nx - 1, i_max); j_max = min(self.ny - 1, j_max)
        for i in range(i_min, i_max + 1):
            for j in range(j_min, j_max + 1):
                pcx, pcy = self.cell_xy(i, j)
                if abs(pcx - x) <= hx and abs(pcy - y) <= hy:
                    self.pad_cells[(i, j, layer)].add(netname)

    def mark_pad_zone(self, x, y, layer, netname, radius_mm=0.6):
        """Mark cells near a pad as 'pad-zone' for that net. Vias are forbidden
        in pad-zone cells (via-in-pad not feasible on small QFN pads).
        Also tracks the pad center cell for access purposes."""
        if layer not in self.layers: return
        i0, j0 = self.xy_to_ij(x, y)
        n = int(math.ceil(radius_mm / self.pitch))
        r2 = radius_mm * radius_mm
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i = i0 + di; j = j0 + dj
                if not self.in_bounds(i, j): continue
                cx, cy = self.cell_xy(i, j)
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    self.via_forbidden_zones.setdefault((i, j, layer), set()).add(netname)

    def is_via_forbidden(self, cell, netname):
        """Via at this cell forbidden for net (inside another net's pad keep-out)."""
        owners = self.via_forbidden_zones.get(cell)
        if not owners:
            return False
        # Allow via in own pad zone (pad-fanout will move it off-pad via search)
        # Forbid via in any OTHER net's pad zone (clearance)
        if owners - {netname}:
            return True
        return False

    def allow_pad_access(self, x, y, layer, netname, radius_mm=0.35):
        """For pads of this net: remove obstacle marks within radius on layer
        (router can ENTER the pad cell for net=netname)."""
        if layer not in self.layers: return
        i0, j0 = self.xy_to_ij(x, y)
        n = int(math.ceil(radius_mm / self.pitch))
        r2 = radius_mm * radius_mm
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                i = i0 + di; j = j0 + dj
                if not self.in_bounds(i, j): continue
                cx, cy = self.cell_xy(i, j)
                if (cx - x) ** 2 + (cy - y) ** 2 <= r2:
                    self.pad_cells[(i, j, layer)].add(netname)

    def is_blocked_for(self, cell, netname):
        """Cell hard-blocked for netname?

        Cell is blocked if:
          - in self.obstacle AND not in pad_cells[netname] (pad copper of other net or track core)
          - in self.net_halo AND ANY owner other than netname (clearance halo of other net)
        """
        if cell in self.obstacle:
            if netname not in self.pad_cells.get(cell, set()):
                return True
        halos = self.net_halo.get(cell)
        # If ANY halo-owner is not netname, the cell is in another net's clearance halo => blocked
        if halos and (halos - {netname}):
            return True
        return False

    def cost(self, cell, present_factor):
        """Soft cost: layer_base + present_factor*present + history."""
        i, j, L = cell
        base = LAYER_BASE_COST.get(L, 1.0)
        pres = self.present.get(cell, 0)
        hist = self.history.get(cell, 0.0)
        return base + present_factor * pres + hist

    def commit_path(self, path_cells, netname):
        """Mark path cells as present for netname."""
        for cell in path_cells:
            self.present[cell] += 1
            self.cell_owners[cell].add(netname)

    def uncommit_path(self, path_cells, netname):
        for cell in path_cells:
            if self.present.get(cell, 0) > 0:
                self.present[cell] -= 1
            self.cell_owners.get(cell, set()).discard(netname)

    def bump_history(self):
        """Increase history for cells with present > 0 (congested in last iter)."""
        for cell, pres in self.present.items():
            if pres > 1:
                self.history[cell] += HISTORY_COST_INC * (pres - 1)


# ─── A* maze router (per-net) ─────────────────────────────────────────────

# Neighbor moves: 8-connected on same layer + layer change via
SAME_LAYER_MOVES_8 = [(-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)]
SAME_LAYER_MOVES_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def heuristic(c1, c2, pitch):
    """Octile-distance heuristic on grid + via penalty.

    Lower bound on actual cost: each grid step incurs ≥1.0 base cost (inner layer),
    so distance×pitch is a valid lower bound. Adding layer-change cost too.
    """
    di = abs(c1[0] - c2[0])
    dj = abs(c1[1] - c2[1])
    d = (di + dj) + (math.sqrt(2) - 2) * min(di, dj)
    lc = LAYER_CHANGE_COST if c1[2] != c2[2] else 0
    return (d * pitch + lc) * HEURISTIC_WEIGHT


def find_path_astar(grid: CongestionGrid, sources, targets,
                    netname, allowed_layers, present_factor,
                    move_set=SAME_LAYER_MOVES_8, time_budget_s=5.0):
    """A* multi-source multi-target on the 3D grid.

    sources/targets: set of (i,j,L) cells. Sources have g=0; goal=any in targets.

    Returns (path_cells, cost) or (None, None).
    """
    start_time = time.monotonic()
    # Open: (f, g, cell, parent_key)
    open_heap = []
    came_from = {}      # cell -> parent cell
    g_score = {}
    # Precompute one representative target for heuristic
    if not targets: return None, None
    targets_set = set(targets)
    target_list = list(targets)
    # Choose nearest target as heuristic anchor (it's lower-bound to any)
    def h(cell):
        if not targets:
            return 0
        return min(heuristic(cell, t, grid.pitch) for t in target_list[:8])  # cap for speed

    for s in sources:
        g_score[s] = 0.0
        f = h(s)
        heapq.heappush(open_heap, (f, 0.0, s, None))
        came_from[s] = None

    nodes_expanded = 0
    while open_heap:
        if time.monotonic() - start_time > time_budget_s:
            return None, None
        f, g, cell, parent = heapq.heappop(open_heap)
        if g > g_score.get(cell, math.inf): continue
        nodes_expanded += 1
        if cell in targets_set:
            # Reconstruct
            path = []
            cur = cell
            while cur is not None:
                path.append(cur)
                cur = came_from.get(cur)
            path.reverse()
            return path, g
        i, j, L = cell
        # Same-layer neighbors
        for di, dj in move_set:
            ni, nj = i + di, j + dj
            if not grid.in_bounds(ni, nj): continue
            ncell = (ni, nj, L)
            if grid.is_blocked_for(ncell, netname): continue
            # For diagonal moves, also ensure both axis-adjacent cells are passable
            # (prevents trace edge from clipping corner of obstacle)
            if di and dj:
                if grid.is_blocked_for((i + di, j, L), netname): continue
                if grid.is_blocked_for((i, j + dj, L), netname): continue
            step = grid.pitch * (math.sqrt(2) if (di and dj) else 1.0)
            ng = g + step * grid.cost(ncell, present_factor)
            if ng < g_score.get(ncell, math.inf):
                g_score[ncell] = ng
                came_from[ncell] = cell
                heapq.heappush(open_heap, (ng + h(ncell), ng, ncell, cell))
        # Layer-change (via) neighbors
        # FORBID via inside any pad zone (own or other) — clearance to pads
        via_here_forbidden = grid.is_via_forbidden((i, j, L), netname)
        if not via_here_forbidden:
            for L2 in allowed_layers:
                if L2 == L: continue
                ncell = (i, j, L2)
                if grid.is_blocked_for(ncell, netname): continue
                # Also forbid via on dest layer if it lands in another net's pad zone
                if grid.is_via_forbidden((i, j, L2), netname): continue
                # via cost: fixed + congestion of both cells
                via_cost = LAYER_CHANGE_COST + grid.cost(ncell, present_factor)
                ng = g + via_cost
                if ng < g_score.get(ncell, math.inf):
                    g_score[ncell] = ng
                    came_from[ncell] = cell
                    heapq.heappush(open_heap, (ng + h(ncell), ng, ncell, cell))
    return None, None


# ─── Path -> KiCad geometry ───────────────────────────────────────────────

def segment_crosses_obstacle(grid, x1, y1, x2, y2, layer, netname):
    """Validate that a straight segment from (x1,y1) to (x2,y2) on layer doesn't
    cross any obstacle cell other than at endpoints (Bresenham-style cell traversal)."""
    i1, j1 = grid.xy_to_ij(x1, y1)
    i2, j2 = grid.xy_to_ij(x2, y2)
    di = i2 - i1; dj = j2 - j1
    n = max(abs(di), abs(dj))
    if n == 0: return False
    for k in range(n + 1):
        t = k / n
        ii = int(round(i1 + di * t))
        jj = int(round(j1 + dj * t))
        if grid.is_blocked_for((ii, jj, layer), netname):
            return True
    return False


def path_to_segments(path_cells, grid: CongestionGrid):
    """Convert grid path -> list of (x1,y1,x2,y2,layer) segments + via cells.

    Algorithm:
      1. Split path into per-layer runs; emit one via between adjacent runs.
      2. Within each run, simplify with Ramer-Douglas-Peucker-lite:
         collapse all cells that lie on the same straight line into one segment.
         A new segment starts whenever the next cell's direction differs from the
         current segment's direction.

    Returns (segments, vias) where:
      segments = [(x1,y1,x2,y2,layer), ...]
      vias = [(x, y), ...]
    """
    if not path_cells or len(path_cells) < 2:
        return [], []
    segments = []
    vias = []
    # Per-layer runs
    runs = []
    cur_layer = path_cells[0][2]
    cur_run = [path_cells[0]]
    for cell in path_cells[1:]:
        if cell[2] == cur_layer:
            cur_run.append(cell)
        else:
            runs.append((cur_layer, cur_run))
            i, j, _ = cur_run[-1]
            x, y = grid.cell_xy(i, j)
            vias.append((x, y))
            cur_layer = cell[2]
            cur_run = [cell]
    runs.append((cur_layer, cur_run))

    def norm_dir(di, dj):
        """Normalize to unit step direction in {-1,0,1}^2."""
        return (0 if di == 0 else (1 if di > 0 else -1),
                0 if dj == 0 else (1 if dj > 0 else -1))

    for layer, run in runs:
        if len(run) < 2:
            continue
        # Walk run, accumulating into one segment per consistent direction
        seg_start_idx = 0
        cur_dir = None
        for k in range(1, len(run)):
            di = run[k][0] - run[k - 1][0]
            dj = run[k][1] - run[k - 1][1]
            d = norm_dir(di, dj)
            if cur_dir is None:
                cur_dir = d
            elif d != cur_dir:
                # Emit segment from seg_start to k-1
                a = run[seg_start_idx]; b = run[k - 1]
                x1, y1 = grid.cell_xy(a[0], a[1])
                x2, y2 = grid.cell_xy(b[0], b[1])
                if (x1, y1) != (x2, y2):
                    segments.append((x1, y1, x2, y2, layer))
                seg_start_idx = k - 1
                cur_dir = d
        # Final segment
        a = run[seg_start_idx]; b = run[-1]
        x1, y1 = grid.cell_xy(a[0], a[1])
        x2, y2 = grid.cell_xy(b[0], b[1])
        if (x1, y1) != (x2, y2):
            segments.append((x1, y1, x2, y2, layer))
    return segments, vias


def emit_to_board(board, segments, vias, net_obj, width_mm, added_items):
    """Insert tracks + vias to board, recording for ripup."""
    for (x1, y1, x2, y2, layer) in segments:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm_to_iu(x1), mm_to_iu(y1)))
        t.SetEnd(pcbnew.VECTOR2I(mm_to_iu(x2), mm_to_iu(y2)))
        t.SetLayer(layer)
        t.SetWidth(mm_to_iu(width_mm))
        t.SetNet(net_obj)
        board.Add(t)
        added_items.append(t)
    for (x, y) in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm_to_iu(x), mm_to_iu(y)))
        v.SetLayerPair(F_CU, B_CU)
        v.SetDrill(mm_to_iu(VIA_DRILL_MM))
        # KiCad 9 PCB_VIA.SetWidth signature: SetWidth(layer, width)
        # Set width on each copper layer the via spans
        for lid in (F_CU, IN2_CU, IN4_CU, IN6_CU, IN8_CU, B_CU):
            try:
                v.SetWidth(lid, mm_to_iu(VIA_DIAM_MM))
            except Exception:
                pass
        v.SetNet(net_obj)
        board.Add(v)
        added_items.append(v)


def remove_from_board(board, items):
    for it in items:
        try:
            board.Remove(it)
        except Exception:
            pass


# ─── Cooperative router ───────────────────────────────────────────────────

class CooperativeRouter:

    def __init__(self, board, subsystem_name, grid_pitch=DEFAULT_GRID_PITCH,
                 seed_nets=None, verbose=True):
        self.board = board
        self.subsystem = subsystem_name
        self.zone = SUBSYSTEM_ZONES[subsystem_name]
        self.grid_pitch = grid_pitch
        self.verbose = verbose

        self.state = BoardState(board, self.zone)
        self.grid = CongestionGrid(self.zone, grid_pitch, SIGNAL_LAYERS)
        self._stamp_obstacles()

        # Per-net committed routes: net -> (path_cells, added_items)
        self.committed = {}

        # Identify target nets
        if seed_nets:
            self.nets = [n for n in seed_nets if n in self.state.net_pads]
        else:
            self.nets = self.state.routable_nets()
        # Filter to nets with pads on F/B/inner — all should be fine
        self.nets.sort(key=lambda n: (net_priority(n), -len(self.state.net_pads[n]), n))

        # Stats
        self.iteration_count = 0
        self.ripup_count = 0
        self.start_time = 0.0

    def log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    def _stamp_obstacles(self):
        s = self.state
        g = self.grid
        # Pad model:
        #   Pad copper rect = HARD obstacle to all (including own net for cell-traversal),
        #     but pad center cell is marked accessible via pad_cells[owner_net]
        #   Clearance halo (pad bbox + clearance + trace_half) = NET-OWNED halo;
        #     blocked for other nets, accessible to owner net (own copper extends here)
        #   Via-keep-out (pad bbox + clearance + via_half) = via forbidden for other nets
        # For routing net X exiting its own pad:
        #   - start cell = pad_cells[X] (accessible despite obstacle)
        #   - immediate neighbors are net_halo[X] cells (accessible to X, blocked to others)
        #   - can traverse 0.3-0.4mm of own halo then transition to free cells
        # Halo dimensions: pad copper edge + clearance + trace half-width + grid slop
        # ensures track centerline never lands closer than (clearance + trace_half) to pad edge
        # which means track edge stays ≥clearance from pad edge.
        halo_m = CLEARANCE_MM + TRACE_HALF_MM + GRID_SLOP_MM
        for layer in SIGNAL_LAYERS:
            for (x, y, hx, hy, owner, padid) in s.pad_obstacles_by_layer.get(layer, []):
                # Pad copper obstacle
                g.stamp_obstacle_rect(x, y, hx, hy, layer)
                # Mark pad cells as accessible to owner net (full pad copper bbox)
                if owner and owner != "<NC>":
                    g.allow_pad_access_rect(x, y, layer, owner, hx, hy)
                    # Net-owned clearance halo: pad bbox + clearance + trace half-width + slop
                    g.stamp_halo_rect(x, y, hx + halo_m, hy + halo_m, layer, owner)
                else:
                    # NC pad: still need clearance halo from other nets — make it a hard obstacle
                    g.stamp_obstacle_rect(x, y, hx + halo_m, hy + halo_m, layer)
                # Via-keep-out: cells within (pad bbox + clearance + via_radius + slop) forbid via
                via_keepout = max(hx, hy) + CLEARANCE_MM + VIA_DIAM_MM / 2 + GRID_SLOP_MM
                g.mark_pad_zone(x, y, layer, owner or "<NC>", radius_mm=via_keepout)
        # Tracks -> hard obstacle on their layer
        for layer in SIGNAL_LAYERS:
            for (x1, y1, x2, y2, w, owner) in s.track_obstacles_by_layer.get(layer, []):
                g.stamp_obstacle_segment(x1, y1, x2, y2, w, layer)
        # Vias -> obstacle on all signal layers (through vias)
        for (x, y, r, owner) in s.via_obstacles:
            for layer in SIGNAL_LAYERS:
                g.stamp_obstacle_circle(x, y, r, layer)
        # Zone bboxes on F.Cu / B.Cu (MOTOR/SHUNT pours) -> soft history bump
        for layer in (F_CU, B_CU):
            for (x1, y1, x2, y2, owner) in s.zone_obstacles_by_layer.get(layer, []):
                # Only stamp zones whose net is a power/MOTOR/SHUNT net (would conflict with signals)
                if owner and (owner.startswith('MOTOR_') or owner.startswith('SHUNT_')
                              or owner.startswith('VMOTOR') or owner.startswith('+V')):
                    g.stamp_obstacle_zone_bbox(x1, y1, x2, y2, layer, soft=True)
        # (F.Cu / B.Cu discouragement implemented via LAYER_BASE_COST in cost() —
        # no per-cell history bump needed; saves memory.)

    def _pad_cells_for_net(self, netname):
        """For each pad of net, mark its cells as accessible to the net."""
        cells_by_pad = []
        for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(netname, []):
            # Pad center cell
            if not (self.zone[0] <= x <= self.zone[2]
                    and self.zone[1] <= y <= self.zone[3]):
                # Pad outside zone — skip (router only reaches pads inside zone)
                continue
            i, j = self.grid.xy_to_ij(x, y)
            if not self.grid.in_bounds(i, j):
                continue
            # Mark FULL pad copper as accessible to own net (covers all pad cells)
            hx = sx / 2; hy = sy / 2
            for layer in layers:
                self.grid.allow_pad_access_rect(x, y, layer, netname, hx, hy)
            # Use pad center cell as canonical access point + 8 neighbors
            pad_layers = list(layers) if layers else [F_CU]
            cells = set()
            for dii in range(-1, 2):
                for djj in range(-1, 2):
                    for L in pad_layers:
                        ci, cj = i + dii, j + djj
                        if self.grid.in_bounds(ci, cj):
                            cells.add((ci, cj, L))
            cells_by_pad.append((ref, padname, x, y, cells, pad_layers, sx, sy))
        return cells_by_pad

    def route_one_net_mst(self, netname, present_factor, time_budget_s=8.0):
        """Build MST of pads. For each MST edge route via A*. Accumulate paths.

        Returns (paths_list, success_bool). paths_list = [(segments, vias, width)]
        """
        pad_info = self._pad_cells_for_net(netname)
        if len(pad_info) < 2:
            return [], False  # nothing to route
        # MST: greedy nearest-neighbor from pad 0
        connected = {0}
        edges = []
        while len(connected) < len(pad_info):
            best = None; best_d = math.inf
            for i in connected:
                xi, yi = pad_info[i][2], pad_info[i][3]
                for j in range(len(pad_info)):
                    if j in connected: continue
                    xj, yj = pad_info[j][2], pad_info[j][3]
                    d = (xi - xj) ** 2 + (yi - yj) ** 2
                    if d < best_d:
                        best_d = d; best = (i, j)
            if best is None: break
            edges.append(best); connected.add(best[1])

        # Allowed layers for this net's routing
        allowed = list(set([F_CU, B_CU] + inner_layers_for(netname)))

        # Route each MST edge with A*, growing the connected set per edge
        # After routing edge k, the resulting path cells become valid SOURCES for next edges
        # of the same net (so the net's own routes are reusable, not obstacles).
        # For simplicity we route each MST edge from source pad cells -> target pad cells +
        # any prior committed path cells of this net (multi-source).
        all_paths = []
        my_route_cells = set()
        # Initial sources = first pad
        for (i_edge, (a, b)) in enumerate(edges):
            sources = set()
            for cell in pad_info[a][4]:
                sources.add(cell)
            sources |= my_route_cells
            targets = set()
            for cell in pad_info[b][4]:
                targets.add(cell)
            # Time budget per edge
            edge_budget = max(2.0, time_budget_s / max(1, len(edges)))
            path, cost = find_path_astar(self.grid, sources, targets,
                                          netname, allowed, present_factor,
                                          time_budget_s=edge_budget)
            if path is None:
                return all_paths, False
            # Track cells
            for c in path: my_route_cells.add(c)
            all_paths.append(path)
        return all_paths, True

    def commit_net(self, netname, paths):
        """Commit paths to board + grid."""
        width = width_for(netname)
        net_obj = self.state.net_obj.get(netname)
        if net_obj is None:
            # Net obj missing; try lookup
            net_obj = self.board.GetNetsByName().get(netname)
        added = []
        all_cells = set()
        for path in paths:
            segments, vias = path_to_segments(path, self.grid)
            emit_to_board(self.board, segments, vias, net_obj, width, added)
            for c in path: all_cells.add(c)
        self.grid.commit_path(all_cells, netname)
        # Also stamp committed segments as obstacles for OTHER nets in next iters
        # by adding to track_obstacles (so next A* sees them as hard blockers)
        for path in paths:
            segments, vias = path_to_segments(path, self.grid)
            for (x1, y1, x2, y2, layer) in segments:
                self.grid.stamp_obstacle_segment(x1, y1, x2, y2, width, layer)
                # Allow this net's own pads to remain accessible
            for (vx, vy) in vias:
                for layer in SIGNAL_LAYERS:
                    self.grid.stamp_obstacle_circle(vx, vy, VIA_DIAM_MM/2 + CLEARANCE_MM, layer)
        # Re-allow pad cells for THIS net (in case its own pads got stamped)
        for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(netname, []):
            for lid in layers:
                self.grid.allow_pad_access_rect(x, y, lid, netname, sx/2, sy/2)
        self.committed[netname] = (all_cells, added)

    def rip_net(self, netname):
        """Remove a net's committed tracks/vias and obstacles."""
        if netname not in self.committed: return
        cells, added = self.committed[netname]
        remove_from_board(self.board, added)
        # Rebuild obstacle map cleanly (cheap path: blow away cell-based obstacles and re-stamp from non-committed state).
        # Lightweight approach: do NOT remove old obstacles cells (we'd have to recount references).
        # Instead, decrement present count; obstacle cells set is rebuilt on next iter via _rebuild_grid().
        self.grid.uncommit_path(cells, netname)
        del self.committed[netname]
        self.ripup_count += 1

    def _rebuild_grid(self):
        """Reset grid; restamp from current board state + current commits."""
        # Re-read board state (cheap; small)
        self.state = BoardState(self.board, self.zone)
        # Preserve historic congestion
        old_history = dict(self.grid.history)
        self.grid = CongestionGrid(self.zone, self.grid_pitch, SIGNAL_LAYERS)
        self.grid.history = defaultdict(float, old_history)
        self._stamp_obstacles()
        # Re-allow pad access for all target nets (own copper bbox)
        for n in self.nets:
            for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(n, []):
                for lid in layers:
                    self.grid.allow_pad_access_rect(x, y, lid, n, sx/2, sy/2)

    def run(self, max_iter=DEFAULT_MAX_ITER):
        """Cooperative loop (Pathfinder-style negotiated congestion + ripup)."""
        self.start_time = time.monotonic()
        unrouted = list(self.nets)
        # Track per-net fail-count; nets that fail repeatedly get higher priority
        fail_count = defaultdict(int)
        self.log(f"[coop] {len(unrouted)} target nets in {self.subsystem}: "
                 f"{', '.join(unrouted[:8])}{'...' if len(unrouted) > 8 else ''}")

        present_factor = PRESENT_COST_FACTOR_INIT
        plateau_count = 0
        last_routed = -1

        for it in range(max_iter):
            self.iteration_count = it + 1
            self.log(f"\n[coop] === Iteration {it+1}/{max_iter} (present_factor={present_factor:.2f}) ===")
            # Re-allow pad access (in case obstacle map was reset)
            for n in unrouted:
                for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(n, []):
                    for lid in layers:
                        self.grid.allow_pad_access_rect(x, y, lid, n, sx/2, sy/2)

            # Sort unrouted: high fail-count nets get highest priority (route first)
            unrouted.sort(key=lambda n: (-fail_count[n], net_priority(n), n))

            still_unrouted = []
            routed_this_iter = []
            for nn in unrouted:
                if nn in self.committed:
                    continue
                # Higher budget for repeatedly-failing nets
                budget = 6.0 + min(fail_count[nn], 5) * 4.0
                paths, ok = self.route_one_net_mst(nn, present_factor, time_budget_s=budget)
                if ok:
                    self.commit_net(nn, paths)
                    routed_this_iter.append(nn)
                    n_segs = sum(len(path_to_segments(p, self.grid)[0]) for p in paths)
                    n_vias = sum(len(path_to_segments(p, self.grid)[1]) for p in paths)
                    self.log(f"  [+] {nn}: routed ({n_segs} segs, {n_vias} vias) "
                             f"fail_count_was={fail_count[nn]}")
                else:
                    still_unrouted.append(nn)
                    fail_count[nn] += 1
                    self.log(f"  [.] {nn}: FAILED (fail_count={fail_count[nn]})")

            self.log(f"  pass result: routed_this_iter={len(routed_this_iter)} "
                     f"still_unrouted={len(still_unrouted)}")
            unrouted = still_unrouted
            if not unrouted:
                self.log(f"\n[coop] ALL ROUTED in {it+1} iterations.")
                break

            # Plateau detection: no NET MAKING PROGRESS for N iters
            # (count "progress" = at least 1 net routed this pass that wasn't routed before)
            if not routed_this_iter:
                plateau_count += 1
            else:
                plateau_count = 0

            # Bump history (Pathfinder negotiated congestion update)
            self.grid.bump_history()
            present_factor *= PRESENT_COST_FACTOR_GROWTH

            # Selective ripup: rip routed nets that BLOCK the failed nets,
            # weighted by plateau-persistence (more aggressive when stuck).
            if it < max_iter - 1 and unrouted:
                k = min(2 + plateau_count * 2, max(2, len(self.committed) // 4))
                rip_candidates = self._select_ripup_candidates(unrouted, k=k)
                if rip_candidates:
                    self.log(f"  ripping {len(rip_candidates)} congestion-blocker nets: {rip_candidates}")
                    for nn in rip_candidates:
                        self.rip_net(nn)
                        unrouted.append(nn)
                    self._rebuild_grid()
                # If selective ripup found nothing AND we're stuck, force-rip random-3
                # (avoids local minima)
                elif plateau_count >= 2 and self.committed:
                    import random
                    random.seed(it)
                    cand = random.sample(list(self.committed.keys()),
                                         min(3, len(self.committed)))
                    self.log(f"  plateau force-rip 3 random nets: {cand}")
                    for nn in cand:
                        self.rip_net(nn)
                        unrouted.append(nn)
                    self._rebuild_grid()

        elapsed = time.monotonic() - self.start_time
        self.log(f"\n[coop] DONE. routed={len(self.committed)}/{len(self.nets)} "
                 f"iterations={self.iteration_count} ripups={self.ripup_count} "
                 f"unrouted={len(unrouted)} elapsed={elapsed:.1f}s")
        if unrouted:
            self.log(f"[coop] UNROUTED nets: {unrouted}")
        return unrouted

    def _select_ripup_candidates(self, failed_nets, k=3):
        """Find committed nets that pass near failed-net pads — likely blockers."""
        # For each failed net, find committed nets whose paths come within 1mm of any failed-net pad
        scores = defaultdict(int)
        for fnn in failed_nets:
            for (ref, padname, x, y, layers, sx, sy) in self.state.net_pads.get(fnn, []):
                if not (self.zone[0] <= x <= self.zone[2]
                        and self.zone[1] <= y <= self.zone[3]):
                    continue
                fi, fj = self.grid.xy_to_ij(x, y)
                R = int(1.5 / self.grid.pitch)
                for cnn, (cells, _) in self.committed.items():
                    if cnn == fnn: continue
                    for ci, cj, cL in cells:
                        if abs(ci - fi) <= R and abs(cj - fj) <= R:
                            scores[cnn] += 1
                            break
        # Top-k
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return [nn for nn, sc in ranked[:k] if sc > 0]


# ─── CLI ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Cooperative ripup-reroute maze router")
    ap.add_argument("board", help="Input .kicad_pcb")
    ap.add_argument("--subsystem", default="CH1", choices=list(SUBSYSTEM_ZONES.keys()))
    ap.add_argument("--output", required=True, help="Output .kicad_pcb")
    ap.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITER)
    ap.add_argument("--grid-pitch", type=float, default=DEFAULT_GRID_PITCH)
    ap.add_argument("--seed-nets", help="Comma-list of net names to route (default: auto-detect)")
    ap.add_argument("--report", help="Optional CSV report file for routed/unrouted nets + metrics")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    board = pcbnew.LoadBoard(args.board)
    seed = [s.strip() for s in args.seed_nets.split(",")] if args.seed_nets else None

    router = CooperativeRouter(board, args.subsystem,
                                grid_pitch=args.grid_pitch,
                                seed_nets=seed,
                                verbose=not args.quiet)
    unrouted = router.run(max_iter=args.max_iterations)

    pcbnew.SaveBoard(args.output, board)
    print(f"\nSaved: {args.output}")
    print(f"Result: {len(router.committed)}/{len(router.nets)} routed, "
          f"{router.iteration_count} iterations, {router.ripup_count} ripups")
    if args.report:
        with open(args.report, "w") as f:
            f.write("net,status,pads,priority,fail_count\n")
            for n in router.nets:
                status = "ROUTED" if n in router.committed else "UNROUTED"
                pads = len(router.state.net_pads.get(n, []))
                f.write(f"{n},{status},{pads},{net_priority(n)},0\n")
            f.write(f"\n# summary: {len(router.committed)}/{len(router.nets)} routed, "
                    f"{router.iteration_count} iterations, {router.ripup_count} ripups\n")
        print(f"Report: {args.report}")
    return 0 if not unrouted else 1


if __name__ == "__main__":
    sys.exit(main())
