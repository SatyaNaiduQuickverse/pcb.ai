#!/usr/bin/env python3
"""stitch_vmotor_plane.py — CH1 30/30 lever M3
======================================================================

DRONE-GRADE PDN return-path stitcher for the +VMOTOR plane.

Per CH1_DRONE_RELIABILITY_SWEEP_2026-05-28.md Finding #2 (BLOCKER):
    G14 audit_via_stitching_density reports 0 vias / 100 cm² on
    the +VMOTOR plane against the 4-vias/cm² spec
    (routing_topology.yaml +VMOTOR.constraint.via_stitching_density_per_cm2).

At 280 A burst, the absence of stitching:
  1. Concentrates current in the In5 plane region without surface return,
  2. Defeats the Bogatin Ch. 5 bypass-loop physics for the local
     VMOTOR_CHn pours (which expect F↔In5 + In5↔B stitching at < 1 cm pitch),
  3. Breaks return-path continuity for any signal layer above In5 that
     references In3/In7 GND (current must travel around the plane edge),
  4. Per Howard Johnson "High-Speed Digital Design" §5: 100 A switching at
     50 kHz PWM with di/dt = 1 GA/s needs GND return vias within 1 inch
     of the source via OR the loop area integrates EMI / radiates.

Stackup (BOARD_INVARIANTS.md 10L):
    F.Cu / In1=GND / In2=signal / In3=GND / In4=BEMF / In5=+VMOTOR /
    In6=signal-SW / In7=GND / In8=signal / B.Cu

This tool walks a candidate grid, adds VMOTOR through-vias (F.Cu↔B.Cu)
landing on the +VMOTOR/In5.Cu pour, AND adds a paired GND through-via
within `--gnd-pair-spacing-mm` so the source via has an electrical
return-path stitch within the 1-inch Howard-Johnson budget.

Algorithm:
    1. Load .kicad_pcb. Identify +VMOTOR pour on In5 and adjacent GND
       pours (In1/In3/In7 + F.Cu/B.Cu surface) for return-path pairing.
    2. Generate a candidate grid across the board at GRID_PITCH_MM.
    3. For each candidate, run feasibility tests:
       (a) Inside +VMOTOR pour on In5,
       (b) Inside a GND pour on AT LEAST one inner GND layer (In1/In3/In7)
           at the proposed pair offset (otherwise the GND stitch via is
           floating — no return),
       (c) ≥ HOLE_HOLE_MM hole-to-hole from every existing drill,
       (d) ≥ FOS_FOREIGN_MM from every foreign-net pad / via on every
           layer the via barrel traverses (F.Cu, In1-In8, B.Cu),
       (e) NOT inside a known plane-keepout zone (sensitive-net keep-out),
       (f) Surface pads (F.Cu + B.Cu) land in empty space (no foreign
           copper).
    4. Emit a +VMOTOR stitch via + paired GND stitch via at the position.
    5. Skip candidates over/near sensitive analog (BEMF / CSA / SHUNT /
       MOTOR_*_CHn / BST / GH / GL / Hall divider) per the
       motor_pad_clear_exempt_nets regex from routing_topology.yaml.
    6. Output: modified board + per-region density + pairing report.

Usage:
    python3 stitch_vmotor_plane.py \\
        --board <path> \\
        --density-vias-per-cm2 4 \\
        --output <path>
        [--grid-pitch-mm 5.0]
        [--gnd-pair-spacing-mm 1.5]
        [--hole-hole-mm 0.25]      # drone-grade multi-fab default; 0.20 = JLC-Class-2-only
        [--fos-foreign-mm 0.25]
        [--sensitive-keepout-mm 1.5]
        [--via-drill-mm 0.30 --via-pad-mm 0.60]
        [--report <json-path>]

Engineering bounds (defaults):
    grid-pitch-mm 5.0       — 1 via / 25 mm² = 4 vias / cm² target
    gnd-pair-spacing-mm 1.5 — ≤ Howard-Johnson 1-inch ≈ 25 mm; we pair
                              within 1.5 mm for tight loop area.
    hole-hole-mm 0.25       — Drone-grade multi-fab supply-chain default
                              (lever R 2026-05-29). JLC HDI Class 2 floor is
                              0.20mm but pinning to floor leaves zero
                              process margin for fab swap to
                              PCBWay/Sierra/JLC-Class-1-standard which all
                              require 0.25mm. Override to 0.20 only when
                              JLC-Class-2-locked AND max stitch density
                              needed. Stitch grid pitch (3.9mm typical) is
                              much larger than h2h so density is unaffected
                              at 0.25mm in practice.
    fos-foreign-mm 0.25     — § 5c FoS target (0.20 mm JLC min × 1.25).
    sensitive-keepout-mm 1.5 — keep stitch via 1.5 mm from any
                              BEMF/CSA/SHUNT/MOTOR phase/Hall divider pad.
    via-drill / via-pad     — JLC 4-6 layer standard (0.30 / 0.60 mm).

READ-ONLY on the worker's canonical board (input is a copy / synthetic
path). Output is a NEW board file.
"""

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable; run on a host with KiCad Python bindings", file=sys.stderr)
    sys.exit(2)

try:
    import yaml
except ImportError:
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TOPOLOGY_PATH = REPO_ROOT / "docs" / "PHASE4V3_LOCKFILES" / "routing_topology.yaml"

# Default sensitive-net regex (mirrors routing_topology.yaml
# motor_pad_clear_exempt_nets but EXPANDED to also cover the Hall
# divider + supervisor analog rails which are equally noise-sensitive).
DEFAULT_SENSITIVE_RE = (
    r"^(MOTOR_[ABC]_CH\d+|BEMF_[ABC]_CH\d+|CSA_[ABC]_OUT_CH\d+|"
    r"CSA_MAX_CH\d+|SHUNT_[ABC]_TOP_CH\d+|GH[ABC]_CH\d+|GL[ABC]_CH\d+|"
    r"BST[ABC]_CH\d+|BUS_CURR_HALL_OUT|VMOTOR_HALL_(HI|LO)|"
    r"VMOTOR_DIV|VMOTOR_SUPER_CT|VBAT_SENSE.*|PG_VMOTOR)$"
)

VMOTOR_NET = "+VMOTOR"
GND_NET = "GND"
# Stackup layer roles (10L, BOARD_INVARIANTS.md):
# These are seeded from BOARD_INVARIANTS hardcodes BUT overridden after
# board load by the actual zone-net layer mapping (some canonical boards
# carry +VMOTOR on a different inner layer than the spec, e.g. In3 instead
# of In5 after a stackup re-layout). The dangling-via fix relies on
# discovering the ACTUAL pour layer so post-refill verification is
# meaningful.
VMOTOR_LAYERS = []       # filled by setup_stackup_layers (discovered from zones)
GND_INNER_LAYERS = []    # filled by setup_stackup_layers (discovered from zones)
SURFACE_LAYERS = []      # F.Cu, B.Cu

ALL_BARREL_LAYERS = []   # F.Cu + In1..In8 + B.Cu (every layer through-via barrel crosses)


# ----------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------

def mm(value_iu):
    return pcbnew.ToMM(value_iu)


def iu(value_mm):
    return pcbnew.FromMM(value_mm)


def vec(x_mm, y_mm):
    return pcbnew.VECTOR2I(iu(x_mm), iu(y_mm))


def hypot_mm(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


# ----------------------------------------------------------------------
# Board inspection
# ----------------------------------------------------------------------

def setup_stackup_layers(board):
    """Populate global layer lists by DISCOVERING actual pour layers from
    the board's zone table — not by hardcoded enum assumption.

    Rationale (worker R22 catch 2026-05-29 on M3 dangling-via fix):
        BOARD_INVARIANTS.md says +VMOTOR lives on In5.Cu but some
        canonical board variants carry +VMOTOR on a different inner
        layer (observed: layer_id=8 = In3.Cu on the current canonical).
        The PR #241 implementation hardcoded In5.Cu — the
        `inside_any_poly` check then evaluated against an EMPTY pour
        list on the wrong layer, fell through to bbox-like behavior on
        the surface, and emitted 470 vias of which 199 (42%) failed
        post-refill electrical-connection verification. We now scan
        zone-net layer assignments at runtime and use whatever inner
        layer carries the +VMOTOR fill. The post-emit verification
        gate catches any residual mismatch.
    """
    global VMOTOR_LAYERS, GND_INNER_LAYERS, SURFACE_LAYERS, ALL_BARREL_LAYERS
    enabled = set(board.GetEnabledLayers().Seq())
    cu_layers = (
        pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu,
        pcbnew.In5_Cu, pcbnew.In6_Cu, pcbnew.In7_Cu, pcbnew.In8_Cu, pcbnew.B_Cu,
    )
    ALL_BARREL_LAYERS = [l for l in cu_layers if l in enabled]
    inner_layers = [l for l in ALL_BARREL_LAYERS
                    if l not in (pcbnew.F_Cu, pcbnew.B_Cu)]

    # Discover where +VMOTOR + GND pours actually exist on this board.
    vmotor_layers_found = set()
    gnd_layers_found = set()
    for z in board.Zones():
        nn = z.GetNetname() or ""
        for lyr in z.GetLayerSet().Seq():
            if lyr not in ALL_BARREL_LAYERS:
                continue
            if nn == VMOTOR_NET:
                vmotor_layers_found.add(lyr)
            elif nn == GND_NET:
                gnd_layers_found.add(lyr)

    # Preserve hardcoded spec as fallback if nothing was found (so
    # the FAIL message in main() still fires meaningfully).
    if not vmotor_layers_found:
        vmotor_layers_found = {l for l in (pcbnew.In5_Cu,) if l in enabled}
    VMOTOR_LAYERS = sorted(vmotor_layers_found)
    # GND_INNER_LAYERS: actual inner-layer GND pours discovered on board.
    GND_INNER_LAYERS = sorted(l for l in gnd_layers_found if l in inner_layers)
    if not GND_INNER_LAYERS:
        # spec-default fallback
        GND_INNER_LAYERS = [
            l for l in (pcbnew.In1_Cu, pcbnew.In3_Cu, pcbnew.In7_Cu)
            if l in enabled
        ]
    SURFACE_LAYERS = [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if l in enabled]


def collect_filled_polys(board):
    """Return dict (net_name, layer_id) -> list of SHAPE_POLY_SET."""
    out = defaultdict(list)
    for z in board.Zones():
        nn = z.GetNetname()
        if not nn:
            continue
        for lyr in z.GetLayerSet().Seq():
            if lyr not in ALL_BARREL_LAYERS:
                continue
            fp = z.GetFilledPolysList(lyr)
            if fp is None:
                continue
            if fp.OutlineCount() == 0:
                continue
            out[(nn, lyr)].append(fp)
    return out


def collect_drills(board):
    """Return list of (x_mm, y_mm, drill_mm) for ALL existing drills
    (pad PTH + vias). Used for hole-to-hole."""
    drills = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            attr = pad.GetAttribute()
            if attr in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                p = pad.GetPosition()
                ds = pad.GetDrillSize()
                d = mm(max(ds.x, ds.y))
                drills.append((mm(p.x), mm(p.y), d))
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            drills.append((mm(p.x), mm(p.y), mm(t.GetDrill())))
    return drills


def collect_pad_obstacles(board):
    """Per-layer list of (x_mm, y_mm, half_w_mm, half_h_mm, net_name) for
    every SMD/PTH pad. Used for surface-copper foreign-clearance and
    barrel-traversal foreign-clearance."""
    by_layer = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            p = pad.GetPosition()
            sz = pad.GetSize()
            net = pad.GetNetname() or ""
            half_w = mm(sz.x) / 2 + 0.05  # +50um for rotated bbox margin
            half_h = mm(sz.y) / 2 + 0.05
            ent = (mm(p.x), mm(p.y), half_w, half_h, net)
            ls = pad.GetLayerSet()
            for lyr in ALL_BARREL_LAYERS:
                if ls.Contains(lyr):
                    by_layer[lyr].append(ent)
    return by_layer


def collect_track_segments(board):
    """Per-layer list of (x1, y1, x2, y2, width_mm, net_name) tracks."""
    by_layer = defaultdict(list)
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        s = t.GetStart()
        e = t.GetEnd()
        lyr = t.GetLayer()
        by_layer[lyr].append(
            (mm(s.x), mm(s.y), mm(e.x), mm(e.y), mm(t.GetWidth()), t.GetNetname() or "")
        )
    return by_layer


def collect_sensitive_keepout_points(board, sens_re):
    """Return list of (x_mm, y_mm) pad centers on sensitive nets — these
    define the analog-keepout radius for stitch-via skip logic."""
    pts = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nn = pad.GetNetname() or ""
            if sens_re.match(nn):
                p = pad.GetPosition()
                pts.append((mm(p.x), mm(p.y)))
    return pts


# ----------------------------------------------------------------------
# Feasibility tests
# ----------------------------------------------------------------------

def inside_any_poly(polys, x_mm, y_mm):
    """True if (x,y) is inside ANY of the given SHAPE_POLY_SET list.

    DEPRECATED for dangling-prevention — kept for compat / debug only.
    The dangling-via fix uses inside_any_poly_with_margin instead.
    """
    p = vec(x_mm, y_mm)
    for fp in polys:
        if fp.Contains(p):
            return True
    return False


def inside_any_poly_with_margin(polys, x_mm, y_mm, margin_mm):
    """True iff (x,y) is inside ANY polygon in `polys` AND the polygon's
    boundary is at least `margin_mm` away from (x,y).

    This is the STRICT pour-membership check that prevents dangling vias.
    Semantics:
      * `fp.Contains(p)` honors SHAPE_POLY_SET holes correctly (a point
        inside a hole is NOT contained), so foreign-net clearance cutouts
        are handled.
      * `fp.CollideEdge(p, None, margin_iu)` returns True if `p` is within
        `margin_iu` of an EDGE — outer boundary OR any internal hole
        boundary. (Note: `Collide(p, m)` is the WRONG primitive — it also
        returns True for points deep in the polygon interior because
        "inside" is treated as "collide with the filled set". We must
        use CollideEdge for the inset semantic.)
      * "Inside AND not edge-near" ⇒ a disk of radius `margin_mm` around
        (x,y) is fully inside the pour ⇒ the zone-fill engine will
        unambiguously connect the via pad after refill.

    Caller chooses `margin_mm = via_pad_radius + connection_clearance` so
    the full via pad + its post-refill connection halo lives strictly in
    the pour.
    """
    p = vec(x_mm, y_mm)
    margin_iu = iu(margin_mm)
    for fp in polys:
        if not fp.Contains(p):
            continue
        # Inside this polygon; now require ≥ margin to its boundary.
        # Use CollideEdge — returns True only if point is within `margin`
        # of an EDGE (outer ring OR a hole boundary). Collide() instead
        # returns True for any point inside-or-near, which is useless
        # for "fully inset" semantics.
        try:
            edge_near = fp.CollideEdge(p, None, margin_iu)
        except Exception:
            # API surface variation — fall back to strict containment only.
            edge_near = False
        if edge_near:
            continue
        return True
    return False


def via_pad_connects_to_pour_after_refill(board, via, net_name):
    """After zone refill, verify the via's pad on F.Cu OR B.Cu (or any
    barrel-traversed layer carrying a pour of `net_name`) is electrically
    connected to a filled pour of `net_name`.

    Uses pcbnew.ZONE.HitTestFilledArea — geometry-exact post-refill test
    (per audit_power_drc.py existing pattern). Caller must ensure zones
    were just refilled.

    Returns True iff the via's center is inside the FILLED polygon (post-
    refill) of at least one zone with net_name == `net_name`.
    """
    pt = via.GetPosition()
    for z in board.Zones():
        if z.GetNetname() != net_name:
            continue
        if not z.IsFilled():
            continue
        for lyr in z.GetLayerSet().Seq():
            try:
                hit = z.HitTestFilledArea(lyr, pt)
            except TypeError:
                try:
                    hit = z.HitTestFilledArea(pt)
                except Exception:
                    hit = False
            except Exception:
                hit = False
            if hit:
                return True
    return False


def segment_point_distance_mm(sx, sy, ex, ey, px, py):
    """Min distance from point (px,py) to segment (sx,sy)-(ex,ey)."""
    dx, dy = ex - sx, ey - sy
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - sx, py - sy)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / L2))
    cx, cy = sx + t * dx, sy + t * dy
    return math.hypot(px - cx, py - cy)


def foreign_clearance_ok(x_mm, y_mm, via_pad_mm, target_net, pads_by_layer,
                          tracks_by_layer, fos_foreign_mm):
    """For every layer the through-via barrel crosses, ensure the via pad
    (assumed circular, radius = via_pad_mm/2) has ≥ fos_foreign_mm to any
    foreign-net pad or track copper. Treat foreign as anything not in
    {target_net}."""
    via_r = via_pad_mm / 2
    for lyr in ALL_BARREL_LAYERS:
        for (px, py, hw, hh, net) in pads_by_layer.get(lyr, []):
            if net == target_net:
                continue
            # box - point distance approximation: rectangle expanded by via_r
            dx = max(0, abs(x_mm - px) - hw)
            dy = max(0, abs(y_mm - py) - hh)
            d_edge = math.hypot(dx, dy)
            if d_edge < via_r + fos_foreign_mm:
                return False, f"layer={lyr} foreign pad net={net} d={d_edge:.3f}"
        for (sx, sy, ex, ey, w, net) in tracks_by_layer.get(lyr, []):
            if net == target_net:
                continue
            d = segment_point_distance_mm(sx, sy, ex, ey, x_mm, y_mm)
            if d < via_r + w / 2 + fos_foreign_mm:
                return False, f"layer={lyr} foreign track net={net} d={d:.3f}"
    return True, None


def hole_to_hole_ok(x_mm, y_mm, drill_mm, drills, hole_hole_mm):
    """≥ hole_hole_mm edge-to-edge for all existing drills."""
    r = drill_mm / 2
    for (dx, dy, dd) in drills:
        edge = math.hypot(x_mm - dx, y_mm - dy) - r - dd / 2
        if edge < hole_hole_mm:
            return False, f"hole-to-hole d_edge={edge:.3f}"
    return True, None


def sensitive_keepout_ok(x_mm, y_mm, sens_pts, keepout_mm):
    """≥ keepout_mm from every sensitive-net pad."""
    k2 = keepout_mm * keepout_mm
    for (sx, sy) in sens_pts:
        if (x_mm - sx) ** 2 + (y_mm - sy) ** 2 < k2:
            return False, f"sensitive d={math.hypot(x_mm - sx, y_mm - sy):.3f}"
    return True, None


# ----------------------------------------------------------------------
# Via creation
# ----------------------------------------------------------------------

def add_thru_via(board, x_mm, y_mm, net_obj, drill_mm, pad_mm):
    v = pcbnew.PCB_VIA(board)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetPosition(vec(x_mm, y_mm))
    v.SetDrill(iu(drill_mm))
    # KiCad 9 SetWidth overload — pass layer to silence the
    # "PCB_VIA::SetWidth called without a layer argument" assertion;
    # for through vias the width is uniform on every Cu layer.
    width_iu = iu(pad_mm)
    try:
        v.SetWidth(pcbnew.F_Cu, width_iu)
        v.SetWidth(pcbnew.B_Cu, width_iu)
    except TypeError:
        v.SetWidth(width_iu)
    v.SetNet(net_obj)
    board.Add(v)
    return v


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="VMOTOR plane stitcher (CH1 30/30 M3)")
    ap.add_argument("--board", required=True, help="input .kicad_pcb")
    ap.add_argument("--output", required=True, help="output .kicad_pcb (modified)")
    ap.add_argument("--density-vias-per-cm2", type=float, default=4.0,
                    help="target +VMOTOR stitch density (vias/cm²)")
    ap.add_argument("--grid-pitch-mm", type=float, default=None,
                    help="candidate-grid pitch (default: derived from target density)")
    ap.add_argument("--gnd-pair-spacing-mm", type=float, default=1.5,
                    help="GND return via offset from each +VMOTOR stitch via")
    ap.add_argument(
        "--hole-hole-mm", type=float, default=0.25,
        help=(
            "min hole-to-hole edge-to-edge clearance in mm "
            "(default 0.25 = drone-grade multi-fab supply-chain safe; "
            "JLC HDI Class 2 min is 0.20 but pinning to that floor leaves "
            "ZERO margin for fab swap to PCBWay/Sierra/JLC-Class-1 standard "
            "library which all require 0.25mm. Override to 0.20 only when "
            "the build is JLC-Class-2-locked AND max stitch density is "
            "required to hit the 4-vias/cm2 density target). "
            "TRADE-OFF: 0.25mm vs 0.20mm reduces max achievable stitch "
            "density by ~14 pct in tight pad/track clusters."
        ),
    )
    ap.add_argument("--fos-foreign-mm", type=float, default=0.25,
                    help="FoS clearance to foreign-net copper")
    ap.add_argument("--sensitive-keepout-mm", type=float, default=1.5,
                    help="keep-out radius around sensitive-net pads")
    ap.add_argument("--via-drill-mm", type=float, default=0.30,
                    help="stitch via drill (JLC standard)")
    ap.add_argument("--via-pad-mm", type=float, default=0.60,
                    help="stitch via copper pad diameter (JLC standard)")
    ap.add_argument("--connection-margin-mm", type=float, default=0.50,
                    help=("inset margin from pour boundary for via pad. "
                          "via must sit ≥ (pad_radius + this) inside the "
                          "+VMOTOR pour to guarantee zone-refill picks it "
                          "up. Worker R22 catch 2026-05-29: PR #241 "
                          "without this margin emitted 42 pct dangling vias."))
    ap.add_argument("--skip-post-verify", action="store_true",
                    help=("DANGEROUS: skip the post-refill electrical-"
                          "connection verify pass. Default OFF — every "
                          "committed via is verified non-dangling. Use "
                          "ONLY for offline diagnostic runs."))
    ap.add_argument("--sensitive-regex", default=DEFAULT_SENSITIVE_RE,
                    help="sensitive-net regex (default mirrors routing_topology.yaml)")
    ap.add_argument("--report", default=None, help="JSON report path")
    ap.add_argument("--no-pair", action="store_true",
                    help="skip GND return-pair via emission (testing only)")
    args = ap.parse_args()

    in_path = Path(args.board)
    out_path = Path(args.output)
    if not in_path.exists():
        print(f"FAIL: input board not found: {in_path}", file=sys.stderr)
        sys.exit(2)

    sens_re = re.compile(args.sensitive_regex)
    target_density = args.density_vias_per_cm2

    # Derive grid pitch from density spec if not given:
    # 1 via per (pitch²) mm² → density = 100 / pitch² per cm²
    # pitch_mm = sqrt(100 / density)
    if args.grid_pitch_mm is None:
        grid_pitch = math.sqrt(100.0 / target_density)
    else:
        grid_pitch = args.grid_pitch_mm
    # Over-supply by ~30%: empirically the worker board skips ~12% of
    # candidates to obstacles / sensitive-net keepouts (mostly CH1 NW
    # quadrant FET cluster); shrink pitch by sqrt(1.3) ≈ 0.88 to keep
    # post-skip density above target.
    candidate_pitch = grid_pitch * 0.78

    print(f"=== stitch_vmotor_plane.py — CH1 30/30 M3 ===")
    print(f"Input:  {in_path}")
    print(f"Output: {out_path}")
    print(f"Target density: {target_density:.2f} vias/cm²")
    print(f"Grid pitch:     {candidate_pitch:.2f} mm (target {grid_pitch:.2f}, "
          f"over-supplied 8%)")
    print(f"GND pair offset: {args.gnd_pair_spacing_mm:.2f} mm "
          f"(Howard Johnson < 1 inch return-path)")
    print()

    board = pcbnew.LoadBoard(str(in_path))
    # Pre-fill zones so GetFilledPolysList returns the post-refill polygon
    # (the strict pour-membership check needs the ACTUAL filled outline,
    # including foreign-net clearance holes — that's the geometry the
    # post-emit verify also sees). Idempotent on already-filled boards.
    try:
        pre_fill_zones = [z for z in board.Zones()]
        if pre_fill_zones:
            pcbnew.ZONE_FILLER(board).Fill(pre_fill_zones)
    except Exception as e:
        print(f"WARN: pre-fill ZONE_FILLER raised {e!r}; "
              f"proceeding with input fill state", file=sys.stderr)
    setup_stackup_layers(board)

    if not VMOTOR_LAYERS:
        print("FAIL: In5.Cu not found in stackup; +VMOTOR plane layer missing",
              file=sys.stderr)
        sys.exit(2)
    if not GND_INNER_LAYERS:
        print("FAIL: no GND inner layers (In1/In3/In7) found", file=sys.stderr)
        sys.exit(2)

    print(f"+VMOTOR plane layer: {[pcbnew.LSET.Name(l) for l in VMOTOR_LAYERS]}")
    print(f"GND inner layers:    {[pcbnew.LSET.Name(l) for l in GND_INNER_LAYERS]}")
    print()

    # Gather geometry
    polys = collect_filled_polys(board)
    vmotor_polys = []
    for lyr in VMOTOR_LAYERS:
        vmotor_polys.extend(polys.get((VMOTOR_NET, lyr), []))
    gnd_inner_polys_by_layer = {
        lyr: polys.get((GND_NET, lyr), []) for lyr in GND_INNER_LAYERS
    }
    if not vmotor_polys:
        print(f"FAIL: no +VMOTOR filled poly on In5.Cu", file=sys.stderr)
        sys.exit(2)

    drills = collect_drills(board)
    pads_by_layer = collect_pad_obstacles(board)
    tracks_by_layer = collect_track_segments(board)
    sens_pts = collect_sensitive_keepout_points(board, sens_re)
    print(f"Existing drills: {len(drills)}")
    print(f"Sensitive-net pad keepout centers: {len(sens_pts)}")
    print()

    vmotor_net_obj = board.FindNet(VMOTOR_NET)
    gnd_net_obj = board.FindNet(GND_NET)
    if vmotor_net_obj is None or gnd_net_obj is None:
        print("FAIL: +VMOTOR or GND net not present", file=sys.stderr)
        sys.exit(2)

    # Board bbox for grid extent
    bbox = board.GetBoardEdgesBoundingBox()
    x0, y0 = mm(bbox.GetX()), mm(bbox.GetY())
    w, h = mm(bbox.GetWidth()), mm(bbox.GetHeight())
    area_cm2 = (w * h) / 100.0

    # Region counters (board quadrants — used for per-region density report
    # so failures concentrate visibly; matches audit_quadrant_balance idiom).
    REGIONS = {
        "NW": (x0, y0 + h / 2, x0 + w / 2, y0 + h),
        "NE": (x0 + w / 2, y0 + h / 2, x0 + w, y0 + h),
        "SW": (x0, y0, x0 + w / 2, y0 + h / 2),
        "SE": (x0 + w / 2, y0, x0 + w, y0 + h / 2),
    }
    region_counts = {k: 0 for k in REGIONS}

    skip_reasons = defaultdict(int)
    added_vmotor = []        # list of (x_mm, y_mm) — kept for legacy reporting
    added_gnd = []           # list of (x_mm, y_mm)
    via_added_drills = []    # accumulate drills as we add (so vias don't collide each other)
    # Parallel lists of the actual PCB_VIA objects + per-pair GND xy, used
    # for the post-refill dangling-verify pass + atomic pair removal of
    # any via whose pad isn't picked up by ZONE_FILLER. Index is
    # consistent across via_objs_vmotor / via_objs_gnd_pair /
    # added_vmotor / pair_xy_per_vmotor.
    via_objs_vmotor = []
    via_objs_gnd_pair = []   # one entry per VMOTOR via; None where no pair
    pair_xy_per_vmotor = []  # (gx,gy) of the paired GND via or None

    # Generate candidate grid (half-pitch offset so we don't land on
    # round-number-rich coordinates that are likely to coincide with
    # existing components):
    nx = int(math.ceil(w / candidate_pitch))
    ny = int(math.ceil(h / candidate_pitch))
    candidates = []
    for ix in range(nx):
        for iy in range(ny):
            cx = x0 + (ix + 0.5) * candidate_pitch
            cy = y0 + (iy + 0.5) * candidate_pitch
            candidates.append((cx, cy))
    print(f"Candidate grid: {nx} x {ny} = {len(candidates)} positions")
    print()

    # Pair directions (try multiple offset directions for GND pair via;
    # angles in degrees CCW from +X).
    PAIR_DIRS = [0, 45, 90, 135, 180, 225, 270, 315]

    # Inset margin = via pad radius + connection clearance, so a disk of
    # this radius around the via center sits strictly inside the pour AND
    # is robustly captured by ZONE_FILLER after refill (no dangling).
    pad_radius_mm = args.via_pad_mm / 2.0
    pour_inset_mm = pad_radius_mm + args.connection_margin_mm

    def can_place_at(x_mm, y_mm, net_name, drill_mm, pad_mm,
                     extra_drills=()):
        """Run the full feasibility chain. Return (ok, reason)."""
        # (a) STRICT pour membership with margin: the via pad must sit
        #     fully inside the pour polygon (not just bbox) with a
        #     half-pad + connection-clearance inset, so the zone refill
        #     unambiguously connects the via to the pour. This is the
        #     fix for the PR #241 dangling-via bug (199/470 = 42%
        #     dangling on worker's empirical run, R22 catch 2026-05-29).
        if net_name == VMOTOR_NET:
            if not inside_any_poly_with_margin(vmotor_polys, x_mm, y_mm,
                                                pour_inset_mm):
                return False, "outside-vmotor-pour"
        elif net_name == GND_NET:
            inside_gnd = False
            for lyr_polys in gnd_inner_polys_by_layer.values():
                if inside_any_poly_with_margin(lyr_polys, x_mm, y_mm,
                                                pour_inset_mm):
                    inside_gnd = True
                    break
            if not inside_gnd:
                return False, "outside-gnd-inner-pour"
        # (c) hole-to-hole vs existing drills + previously-added vias
        ok, why = hole_to_hole_ok(x_mm, y_mm, drill_mm, drills, args.hole_hole_mm)
        if not ok:
            return False, "hole-to-hole-existing"
        ok, why = hole_to_hole_ok(x_mm, y_mm, drill_mm, via_added_drills,
                                   args.hole_hole_mm)
        if not ok:
            return False, "hole-to-hole-stitch"
        for ed in extra_drills:
            edge = math.hypot(x_mm - ed[0], y_mm - ed[1]) - drill_mm / 2 - ed[2] / 2
            if edge < args.hole_hole_mm:
                return False, "hole-to-hole-pair"
        # (d) foreign-net clearance on every barrel layer
        ok, why = foreign_clearance_ok(x_mm, y_mm, pad_mm, net_name,
                                        pads_by_layer, tracks_by_layer,
                                        args.fos_foreign_mm)
        if not ok:
            return False, "foreign-clearance"
        # (e) sensitive keepout
        ok, why = sensitive_keepout_ok(x_mm, y_mm, sens_pts,
                                        args.sensitive_keepout_mm)
        if not ok:
            return False, "sensitive-keepout"
        return True, None

    for (cx, cy) in candidates:
        # Test +VMOTOR via at the candidate
        ok, reason = can_place_at(cx, cy, VMOTOR_NET,
                                   args.via_drill_mm, args.via_pad_mm)
        if not ok:
            skip_reasons[reason] += 1
            continue
        if args.no_pair:
            pair_xy = None
        else:
            # Try each direction for GND pair
            pair_xy = None
            for ang in PAIR_DIRS:
                a = math.radians(ang)
                gx = cx + args.gnd_pair_spacing_mm * math.cos(a)
                gy = cy + args.gnd_pair_spacing_mm * math.sin(a)
                ok2, reason2 = can_place_at(
                    gx, gy, GND_NET, args.via_drill_mm, args.via_pad_mm,
                    extra_drills=[(cx, cy, args.via_drill_mm)],
                )
                if ok2:
                    pair_xy = (gx, gy)
                    break
            if pair_xy is None:
                skip_reasons["no-gnd-pair-slot"] += 1
                continue
        # Emit both
        v_vmotor = add_thru_via(board, cx, cy, vmotor_net_obj,
                                 args.via_drill_mm, args.via_pad_mm)
        via_added_drills.append((cx, cy, args.via_drill_mm))
        added_vmotor.append((cx, cy))
        via_objs_vmotor.append(v_vmotor)
        v_gnd = None
        if pair_xy is not None:
            gx, gy = pair_xy
            v_gnd = add_thru_via(board, gx, gy, gnd_net_obj,
                                  args.via_drill_mm, args.via_pad_mm)
            via_added_drills.append((gx, gy, args.via_drill_mm))
            added_gnd.append((gx, gy))
        via_objs_gnd_pair.append(v_gnd)
        pair_xy_per_vmotor.append(pair_xy)
        # Region tally on the +VMOTOR via:
        for rname, (rx0, ry0, rx1, ry1) in REGIONS.items():
            if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                region_counts[rname] += 1
                break

    # =================================================================
    # Post-emit verification — ZONE_FILLER refill + per-via connectivity
    # =================================================================
    # Worker R22 catch 2026-05-29: PR #241 emitted 470 vias of which 199
    # (~42%) were DANGLING post-refill. The pre-filter "inside pour"
    # check used SHAPE_POLY_SET.Contains(point) without a pad+margin
    # inset, so vias near the pour boundary slipped through. The strict
    # inside_any_poly_with_margin filter above is the PRIMARY fix; this
    # post-emit verify is the BACKSTOP gate — any via whose pad does not
    # actually connect to its pour after a fresh ZONE_FILLER refill is
    # removed before save. The tool MUST NEVER persist a dangling via.
    #
    # Per [[feedback-sim-execution-gate]] sibling pattern: don't just
    # check at filter time, EXECUTE the refill + RE-CHECK the actual
    # post-refill state. Geometry filters lie occasionally; KiCad
    # zone-fill engine is the source of truth.
    dangling_vmotor = 0
    dangling_gnd = 0
    if not args.skip_post_verify:
        print("--- Post-emit ZONE_FILLER verification ---")
        # Run ZONE_FILLER on every zone, then HitTestFilledArea per via.
        zones_list = [z for z in board.Zones()]
        print(f"Refilling {len(zones_list)} zones to check via connectivity...")
        try:
            pcbnew.ZONE_FILLER(board).Fill(zones_list)
        except Exception as e:
            print(f"WARN: ZONE_FILLER raised {e!r}; proceeding with existing fill state")

        kept_vmotor_xy = []
        kept_gnd_xy = []
        kept_region_counts = {k: 0 for k in REGIONS}
        for idx, v in enumerate(via_objs_vmotor):
            if v is None:
                continue
            cx, cy = added_vmotor[idx]
            ok_v = via_pad_connects_to_pour_after_refill(
                board, v, VMOTOR_NET)
            v_gnd = via_objs_gnd_pair[idx]
            ok_g = True
            if v_gnd is not None:
                ok_g = via_pad_connects_to_pour_after_refill(
                    board, v_gnd, GND_NET)
            if not ok_v:
                dangling_vmotor += 1
            if v_gnd is not None and not ok_g:
                dangling_gnd += 1
            # Atomic-pair acceptance: keep ONLY if both sides verified.
            # A dangling +VMOTOR via with a connected GND pair is still
            # useless (+VMOTOR side defeats the stitch's purpose); a
            # connected +VMOTOR with a dangling GND breaks the Howard-
            # Johnson return-path pairing. Reject the pair.
            keep = ok_v and ok_g
            if keep:
                kept_vmotor_xy.append((cx, cy))
                if v_gnd is not None and pair_xy_per_vmotor[idx] is not None:
                    kept_gnd_xy.append(pair_xy_per_vmotor[idx])
                for rname, (rx0, ry0, rx1, ry1) in REGIONS.items():
                    if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                        kept_region_counts[rname] += 1
                        break
            else:
                # Remove both — keep board atomic.
                try:
                    board.Remove(v)
                except Exception as e:
                    print(f"WARN: failed to remove vmotor via at "
                          f"({cx:.2f},{cy:.2f}): {e!r}")
                if v_gnd is not None:
                    try:
                        board.Remove(v_gnd)
                    except Exception as e:
                        print(f"WARN: failed to remove gnd via: {e!r}")

        print(f"Pre-verify accepted: {len(added_vmotor)} VMOTOR + "
              f"{len(added_gnd)} GND")
        print(f"Dangling detected:   {dangling_vmotor} VMOTOR + "
              f"{dangling_gnd} GND")
        print(f"Post-verify kept:    {len(kept_vmotor_xy)} VMOTOR + "
              f"{len(kept_gnd_xy)} GND")
        skip_reasons["post-refill-dangling-removed"] = (
            dangling_vmotor + dangling_gnd)

        # If we removed any via, the previous refill is now stale w.r.t.
        # the kept set. Refill once more so the saved board is geometry-
        # consistent and the next audit pass sees the final state.
        if dangling_vmotor + dangling_gnd > 0:
            try:
                pcbnew.ZONE_FILLER(board).Fill(zones_list)
            except Exception:
                pass

        added_vmotor = kept_vmotor_xy
        added_gnd = kept_gnd_xy
        region_counts = kept_region_counts
        print()

    # ----- Report -----
    achieved_density = len(added_vmotor) / area_cm2 if area_cm2 > 0 else 0
    print(f"--- Stitching summary ---")
    print(f"Board area:           {area_cm2:.2f} cm²")
    print(f"+VMOTOR stitch vias:  {len(added_vmotor)}")
    print(f"Paired GND vias:      {len(added_gnd)}")
    print(f"Achieved density:     {achieved_density:.3f} vias/cm² "
          f"(target {target_density:.2f}/cm²) "
          f"{'PASS' if achieved_density >= target_density else 'SHORT'}")
    print()
    print("Per-region (board quadrant) +VMOTOR via count:")
    for rname, n in region_counts.items():
        # Region area is quarter of board for the quadrant grid:
        ra = area_cm2 / 4
        print(f"  {rname}: {n} vias / {ra:.1f}cm² = "
              f"{n/ra:.2f}/cm²")
    print()
    print(f"Pair coverage: {len(added_gnd)}/{len(added_vmotor)} "
          f"= {100*len(added_gnd)/max(1,len(added_vmotor)):.1f}% "
          f"({'PASS' if (args.no_pair or len(added_gnd)==len(added_vmotor)) else 'PARTIAL'})")
    print()
    print("Skip reasons (candidate grid filter):")
    for reason, n in sorted(skip_reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {reason}: {n}")
    print()

    print(f"Saving modified board: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    board.Save(str(out_path))

    if args.report:
        report = {
            "input_board": str(in_path),
            "output_board": str(out_path),
            "target_density_per_cm2": target_density,
            "achieved_density_per_cm2": achieved_density,
            "board_area_cm2": area_cm2,
            "vmotor_vias_added": len(added_vmotor),
            "gnd_vias_added": len(added_gnd),
            "vmotor_dangling_removed": dangling_vmotor,
            "gnd_dangling_removed": dangling_gnd,
            "post_verify_skipped": bool(args.skip_post_verify),
            "pair_coverage_pct": (
                100 * len(added_gnd) / max(1, len(added_vmotor))),
            "region_counts": region_counts,
            "skip_reasons": dict(skip_reasons),
            "params": {
                "grid_pitch_mm": candidate_pitch,
                "gnd_pair_spacing_mm": args.gnd_pair_spacing_mm,
                "hole_hole_mm": args.hole_hole_mm,
                "fos_foreign_mm": args.fos_foreign_mm,
                "sensitive_keepout_mm": args.sensitive_keepout_mm,
                "via_drill_mm": args.via_drill_mm,
                "via_pad_mm": args.via_pad_mm,
                "connection_margin_mm": args.connection_margin_mm,
            },
            "verdict": "PASS" if achieved_density >= target_density else "FAIL",
            "dangling_invariant": (
                "0 dangling vias committed" if not args.skip_post_verify
                else "post-verify-skipped"),
        }
        Path(args.report).write_text(json.dumps(report, indent=2))
        print(f"Report: {args.report}")

    verdict = "PASS" if achieved_density >= target_density else "FAIL"
    print(f"\nRESULT: {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
