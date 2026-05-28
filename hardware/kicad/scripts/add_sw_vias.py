#!/usr/bin/env python3
"""add_sw_vias.py — CH1 30/30 (M2) SW-node via field adder.

Drone-grade ampacity tool: adds through-vias to MOTOR_X_CHn SW-node copper
so the via cluster carries 100A continuous (×1.5 FoS = 150A) at the IPC-2152
+ Brooks "PCB Currents" per-via rating of 1.0A continuous (0.3mm drill, 0.6mm
pad, 1oz plating).

Per `docs/CH1_DRONE_RELIABILITY_SWEEP_2026-05-28.md` Finding #1: MOTOR_A/B/C_CH1
currently route 5/5/6 SW vias against ≥150 needed. Worker PR #227 attempted
+11/phase but hit hole-to-hole (0.20mm) + dangling (barrel pad outside SW
copper) violations on HDI microvia 0.10/0.25 attempts. This tool prefers
through-vias (the only via class whose pads land inside the F.Cu+B.Cu SW-node
copper without HDI complications) and rigorously validates EVERY drill against:

  1. Inside the SW-node copper region on BOTH F.Cu AND B.Cu (no dangling).
  2. ≥0.20mm hole-to-hole clearance from EVERY existing drill (vias + footprint
     pads + mounting holes) — board-wide walk.
  3. ≥0.20mm clearance from EVERY foreign-net copper on every layer the via
     barrel + pads traverse (anti-pad clearance to foreign copper).
  4. Phase symmetry (R19): if MOTOR_A receives N vias, MOTOR_B + MOTOR_C
     receive N vias at MIRRORED positions per BOARD_INVARIANTS mirror axis.

Algorithm:
  Phase 1 — Inventory: load board, extract per-net SW-node copper polygons
            (F.Cu + B.Cu filled-zone outlines + LS-FET drain B.Cu pads), and
            existing drills (vias + through-hole pad drills + mount holes).
  Phase 2 — Candidate grid: generate (x, y) candidates inside the F∩B copper
            region at configurable pitch (default 0.5mm).
  Phase 3 — Per-candidate filter: hole-to-hole + dangling-safety + foreign-
            copper clearance (per layer).
  Phase 4 — Greedy add up to target_count, prioritizing:
              (a) farther from existing drills (avoid sub-FoS cluster crowding),
              (b) spread across SW region (no clusters).
  Phase 5 — Output: write modified .kicad_pcb + report (per-via class, pos,
            margins; ampacity FoS achieved; max-feasible report if target
            geometrically infeasible).

Usage:
  python3 add_sw_vias.py --board <in.kicad_pcb> --net <MOTOR_A_CH1|MOTOR_B_CH1|MOTOR_C_CH1>
                         --target-count <N> --output <out.kicad_pcb>
                         [--hole-to-hole 0.20] [--foreign-clearance 0.20]
                         [--pitch 0.5] [--via-drill 0.3] [--via-pad 0.6]

Returns exit 0 on PASS (target met or honestly-reported max-feasible);
exit 1 only on tool error (e.g. net not found).
"""

import argparse
import json
import math
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable", file=sys.stderr)
    sys.exit(2)


# =============================================================================
# Constants — IPC-2152 + R19 + BOARD_INVARIANTS-derived
# =============================================================================

# Through-via geometry (0.3mm drill, 0.6mm pad, 1oz plating).
# Per Brooks "PCB Currents" + IPC-2152: 1.0 A/via continuous, 3.0 A/via
# burst (1-s pulse, 10°C rise from ambient).
VIA_DRILL_MM_DEFAULT = 0.30
VIA_PAD_MM_DEFAULT   = 0.60
VIA_AMP_CONT_PER_VIA = 1.0
VIA_AMP_BURST_PER_VIA = 3.0

# Sai 2026-05-28 reliability sweep FoS targets:
FOS_VIA_CURRENT = 1.5  # × continuous demand for via-cluster ampacity (G_R5)
FOS_VIA_BURST   = 1.2  # × burst demand (audit_via_current_capacity.py)

# Sub-FoS hole-to-hole rule (Sai-locked 2026-05-28 + JLC fab):
# JLC absolute hole-to-hole min = 0.20mm; we use this AS the threshold (NOT
# above-fab-min FoS) because the SW-cluster geometry is genuinely
# pitch-constrained and the master-route can lift this only by escalating to
# HDI which trades ampacity for density. 0.20mm is the floor, not a target;
# tool flags any drill < 0.25mm to-hole as a "tight" warning row in the report.
HOLE_TO_HOLE_MIN_MM = 0.20
HOLE_TO_HOLE_WARN_MM = 0.25

# Foreign-net copper clearance (anti-pad to foreign track/pad/zone):
# JLC fab min 0.127mm; routing_topology.yaml `clearance: above-fab-min` FoS;
# 0.20mm = 0.127 + ~60% margin (matches the existing 8 sub-FoS sub-tier in
# CH1_DRONE_RELIABILITY_SWEEP_2026-05-28 Appendix A — sets a consistent floor).
FOREIGN_COPPER_CLEAR_MM = 0.20

# BOARD_INVARIANTS mirror primitive (routing_topology.yaml):
MIRROR_AXIS_Y = 50.0  # mirror_Y axis for CH1 phases A↔B↔C is NOT a phase-mirror.
# CH1 phases A/B/C are NOT mirrors of each other — they are 3 phases of one
# 3-phase channel, stacked y∈[50,89] in order A (y≈53), B (y≈66), C (y≈79).
# R19 SYMMETRY for SW vias means IDENTICAL COUNT + IDENTICAL TRANSLATION-OFFSET
# of via positions from the phase-cluster origin. We compute the offset vector
# (dx, dy) of every added via relative to its HS-FET drain centroid (Q5.9 for
# A, Q7.9 for B, Q9.9 for C) so adding one phase auto-projects to the others.
# This is the "R19 = commutation loop-L symmetry, NOT identical polylines"
# rule per reference-r19-loop-vs-trace-symmetry — identical via PATTERN
# relative to each phase-cluster origin guarantees identical loop-L.

# Per-phase cluster origins (Q*.9 pad = HS-FET drain centroid):
PHASE_ORIGINS_CH1 = {
    "MOTOR_A_CH1": (8.4, 53.0, "Q5", "9"),
    "MOTOR_B_CH1": (8.4, 66.0, "Q7", "9"),
    "MOTOR_C_CH1": (8.4, 79.0, "Q9", "9"),
}


# =============================================================================
# Geometry helpers
# =============================================================================

def polygon_contains(poly_pts, x, y):
    """Even-odd ray cast. poly_pts = [(x,y), ...] closed implicitly."""
    n = len(poly_pts)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly_pts[i]
        xj, yj = poly_pts[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def dist_point_to_polygon_edge(poly_pts, x, y):
    """Min distance from (x,y) to any edge of polygon. 0 if inside."""
    if polygon_contains(poly_pts, x, y):
        return 0.0
    best = float("inf")
    n = len(poly_pts)
    for i in range(n):
        ax, ay = poly_pts[i]
        bx, by = poly_pts[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 == 0:
            d = math.hypot(x - ax, y - ay)
        else:
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            px, py = ax + t * dx, ay + t * dy
            d = math.hypot(x - px, y - py)
        best = min(best, d)
    return best


def signed_inside_margin(polys, x, y):
    """For a list of polygons (a union of MOTOR-net copper shapes), return
    the BEST (max) inset-distance-from-edge among polygons that contain the
    point. Returns -1 if outside ALL polygons.

    Semantics: a via pad of radius r is non-dangling iff at least one polygon
    contains the entire disk — i.e. the point is inside that polygon AND its
    distance to that polygon's boundary is ≥ r. Returning the MAX inset gives
    the largest such "safe disk" across the union; the caller compares it to
    the required pad radius.
    """
    best_inset = -1.0
    for poly in polys:
        if polygon_contains(poly, x, y):
            d = _dist_inside_polygon(poly, x, y)
            if d > best_inset:
                best_inset = d
    return best_inset


def _dist_inside_polygon(poly_pts, x, y):
    """Distance from interior point (x,y) to nearest polygon edge."""
    best = float("inf")
    n = len(poly_pts)
    for i in range(n):
        ax, ay = poly_pts[i]
        bx, by = poly_pts[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 == 0:
            d = math.hypot(x - ax, y - ay)
        else:
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            px, py = ax + t * dx, ay + t * dy
            d = math.hypot(x - px, y - py)
        best = min(best, d)
    return best


# =============================================================================
# Board introspection
# =============================================================================

def extract_filled_polys(board, net_name, layer_name_substr):
    """Return list of filled-zone polygons on the layer name matching substr,
    for the given net. Each polygon is a list of (x_mm, y_mm) vertices."""
    polys = []
    for z in board.Zones():
        if z.GetNetname() != net_name:
            continue
        for layer_id in range(pcbnew.PCB_LAYER_ID_COUNT):
            if not z.IsOnLayer(layer_id):
                continue
            ln = board.GetLayerName(layer_id)
            if layer_name_substr not in ln:
                continue
            try:
                fp = z.GetFilledPolysList(layer_id)
                n_oc = fp.OutlineCount()
            except Exception:
                continue
            for oi in range(n_oc):
                try:
                    cp = fp.COutline(oi)
                    npts = cp.PointCount()
                    pts = [(cp.CPoint(i).x / 1e6, cp.CPoint(i).y / 1e6)
                           for i in range(npts)]
                    if len(pts) >= 3:
                        polys.append(pts)
                except Exception:
                    pass
    return polys


def extract_pad_polys_for_net(board, net_name, layer_id):
    """SMD pads on the given layer that belong to the net — approximate as
    rectangles. Returns list of polygon-vertex lists. Skips PTH pad drills
    (these are themselves drills we want to avoid, not areas we want to
    place new vias inside — the drill subtracts copper)."""
    polys = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != net_name:
                continue
            lset = pad.GetLayerSet()
            if not lset.Contains(layer_id):
                continue
            pos = pad.GetPosition()
            sz = pad.GetSize()
            cx, cy = pos.x / 1e6, pos.y / 1e6
            hw, hh = sz.x / 2e6, sz.y / 2e6
            # Account for pad rotation (approximate by bbox at 0°/90°)
            try:
                rot_deg = pad.GetOrientation().AsDegrees()
            except Exception:
                rot_deg = 0.0
            if abs(((rot_deg + 45) % 180) - 90) < 45:
                hw, hh = hh, hw
            polys.append([
                (cx - hw, cy - hh), (cx + hw, cy - hh),
                (cx + hw, cy + hh), (cx - hw, cy + hh),
            ])
    return polys


def collect_existing_drills(board):
    """Every drilled hole on the board: vias + PTH/NPTH pad drills + mount
    holes. Returns list of (x_mm, y_mm, drill_mm, kind, ref)."""
    drills = []
    # Vias
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            drills.append((p.x / 1e6, p.y / 1e6, t.GetDrillValue() / 1e6,
                           "via", t.GetNetname()))
    # Pad drills (through-hole pads + NPTH mount holes)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            ds = pad.GetDrillSize()
            if ds.x <= 0:
                continue
            p = pad.GetPosition()
            drills.append((p.x / 1e6, p.y / 1e6, ds.x / 1e6,
                           "pad", f"{ref}.{pad.GetPadName()}"))
    return drills


def collect_foreign_copper_per_layer(board, our_net_name, layer_ids):
    """For each layer_id, collect (x, y, radius_eff_mm) of foreign-net copper
    centers we want to clear by FOREIGN_COPPER_CLEAR_MM. Approximations:
      * Tracks: midpoints + half-length-radius + half-width (point-cloud-ish).
      * Pads: bbox-treated-as-circle (radius = max(w,h)/2).
      * Vias of OTHER nets: pad-radius.
    For exact geometric correctness we'd need polygon ops; this conservative
    over-approximation is what the candidate-clearance test uses, paired with
    a final hole-to-hole exact check.
    Returns dict: layer_id → list of (cx, cy, r_eff)."""
    out = {lid: [] for lid in layer_ids}
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            if t.GetNetname() == our_net_name:
                continue
            p = t.GetPosition()
            try:
                w = t.GetWidth(pcbnew.F_Cu) / 1e6
            except Exception:
                try:
                    w = t.GetWidth() / 1e6
                except Exception:
                    w = 0.6
            for lid in layer_ids:
                out[lid].append((p.x / 1e6, p.y / 1e6, w / 2.0))
            continue
        # regular track
        net = t.GetNetname()
        if net == our_net_name:
            continue
        lid = t.GetLayer()
        if lid not in layer_ids:
            continue
        s, e = t.GetStart(), t.GetEnd()
        try:
            w = t.GetWidth() / 1e6
        except Exception:
            w = 0.25
        # subdivide track into points every 0.5mm
        L = math.hypot((e.x - s.x) / 1e6, (e.y - s.y) / 1e6)
        nseg = max(1, int(L / 0.5))
        for k in range(nseg + 1):
            tt = k / nseg if nseg > 0 else 0
            cx = (s.x + (e.x - s.x) * tt) / 1e6
            cy = (s.y + (e.y - s.y) * tt) / 1e6
            out[lid].append((cx, cy, w / 2.0))
    # pads
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetname()
            if net == our_net_name:
                continue
            lset = pad.GetLayerSet()
            p = pad.GetPosition()
            sz = pad.GetSize()
            r_eff = max(sz.x, sz.y) / 2e6
            for lid in layer_ids:
                if lset.Contains(lid):
                    out[lid].append((p.x / 1e6, p.y / 1e6, r_eff))
    return out


def collect_foreign_zones_per_layer(board, our_net_name, layer_ids):
    """Zones (filled pours) on foreign nets — polygons, per layer."""
    out = {lid: [] for lid in layer_ids}
    for z in board.Zones():
        if z.GetNetname() == our_net_name:
            continue
        for lid in layer_ids:
            if not z.IsOnLayer(lid):
                continue
            try:
                fp = z.GetFilledPolysList(lid)
            except Exception:
                continue
            for oi in range(fp.OutlineCount()):
                try:
                    cp = fp.COutline(oi)
                    npts = cp.PointCount()
                    pts = [(cp.CPoint(i).x / 1e6, cp.CPoint(i).y / 1e6)
                           for i in range(npts)]
                    if len(pts) >= 3:
                        out[lid].append((z.GetNetname(), pts))
                except Exception:
                    pass
    return out


# =============================================================================
# Candidate scoring + filter
# =============================================================================

def candidate_pass(x, y, drills, sw_polys_F, sw_polys_B,
                   foreign_pts_per_layer, foreign_zones_per_layer,
                   via_pad_mm, via_drill_mm,
                   hole_min_mm, foreign_clear_mm,
                   layer_ids):
    """Return (pass: bool, reason: str, h2h_min: float).
    A candidate PASSES iff:
      * pad fits inside ≥1 F.Cu SW polygon (entire pad disk),
      * pad fits inside ≥1 B.Cu SW polygon (entire pad disk),
      * drill clears every existing drill by ≥ hole_min_mm (edge-to-edge),
      * pad disk clears every foreign-copper feature on every traversed
        layer by ≥ foreign_clear_mm (edge-to-edge: dist > r_foreign + pad/2
        + foreign_clear_mm).
    """
    pad_r = via_pad_mm / 2.0
    drill_r = via_drill_mm / 2.0

    # 1. Dangling check: pad must fit inside F + B copper.
    # 1µm tolerance — keep KiCad-scale precision aligned with the IU grid.
    eps = 1e-3
    insetF = signed_inside_margin(sw_polys_F, x, y)
    if insetF + eps < pad_r:
        return False, f"dangle-F ({insetF:.3f}<pad_r {pad_r:.3f})", 0.0
    insetB = signed_inside_margin(sw_polys_B, x, y)
    if insetB + eps < pad_r:
        return False, f"dangle-B ({insetB:.3f}<pad_r {pad_r:.3f})", 0.0

    # 2. Hole-to-hole.
    h2h_min = float("inf")
    for (dx, dy, dd, kind, ref) in drills:
        center_dist = math.hypot(x - dx, y - dy)
        edge = center_dist - (drill_r + dd / 2.0)
        if edge < h2h_min:
            h2h_min = edge
        if edge < hole_min_mm:
            return False, f"hole2hole {edge:.3f}mm vs {kind} {ref} @({dx:.2f},{dy:.2f})", edge

    # 3. Foreign-copper clearance, per layer.
    # For foreign TRACKS + PADS: exact edge-to-edge clearance (pad-disk vs
    # track/pad radius). Strict.
    # For foreign ZONES (filled pours): the pour will auto-CLEAR around the
    # new via on re-fill (KiCad zone clearance semantics). So we don't reject
    # candidates inside foreign zones — but we DO record that the via lives
    # inside a foreign pour so the post-add zone-refill must be re-run by the
    # caller. We only reject if the foreign zone is geometrically TIGHT to
    # an EDGE such that there's no room for the auto-clear anti-pad.
    for lid in layer_ids:
        for (fx, fy, fr) in foreign_pts_per_layer.get(lid, []):
            d = math.hypot(x - fx, y - fy) - (pad_r + fr)
            if d < foreign_clear_mm:
                return False, f"foreign-copper {d:.3f}mm layer={lid}", h2h_min
        # Foreign zones: auto-clear handles via-inside-pour. The only failure
        # mode is when the via is RIGHT AT the zone EDGE such that the
        # auto-clear anti-pad would clip the zone outline. That's the
        # "(d_to_edge - pad_r) < foreign_clear_mm AND NOT inside" case.
        for (fnet, poly) in foreign_zones_per_layer.get(lid, []):
            inside_foreign = polygon_contains(poly, x, y)
            if inside_foreign:
                continue  # auto-clear; ok
            d_to_edge = dist_point_to_polygon_edge(poly, x, y)
            if (d_to_edge - pad_r) < foreign_clear_mm:
                return False, (f"foreign zone {fnet} layer={lid} "
                               f"{d_to_edge - pad_r:.3f}mm"), h2h_min

    return True, "OK", h2h_min


def generate_grid(sw_polys_F, sw_polys_B, pitch, margin):
    """Return candidate (x, y) list.
    Grid is the bbox UNION of F + B SW copper (so the through-via must land
    inside ≥1 F shape AND ≥1 B shape, but the bbox is intentionally over-
    sized so e.g. the TP19 F.Cu motor-pad area is searched even if B.Cu has
    a smaller bbox there). The dangling check filters per-shape."""
    if not sw_polys_F or not sw_polys_B:
        return []
    all_pts = [p for pl in sw_polys_F + sw_polys_B for p in pl]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    x_min, x_max = min(xs) + margin, max(xs) - margin
    y_min, y_max = min(ys) + margin, max(ys) - margin
    cands = []
    y = y_min
    while y <= y_max + 1e-6:
        x = x_min
        while x <= x_max + 1e-6:
            cands.append((x, y))
            x += pitch
        y += pitch
    return cands


# =============================================================================
# Main per-net add
# =============================================================================

def add_vias_for_net(board, net_name, target_count, args):
    """Return list of (x, y, via_drill, via_pad, h2h_min, dF, dB) added.
    Also returns a structured report dict."""
    print(f"\n=== {net_name} ===")
    report = {
        "net": net_name,
        "target_count": target_count,
        "added": [],
        "rejected_summary": {},
        "feasibility": "UNKNOWN",
        "ampacity": {},
    }

    # Extract SW copper polygons — zones AND pads. Pads on the same net are
    # MOTOR_X copper too (e.g. TP19 4x4mm motor pad, Q5.9 3x3mm drain pad).
    # If a candidate via pad-disk sits fully inside (zone ∪ pad-rect), it
    # is non-dangling.
    sw_F = extract_filled_polys(board, net_name, "F.Cu") \
         + extract_pad_polys_for_net(board, net_name, pcbnew.F_Cu)
    sw_B = extract_filled_polys(board, net_name, "B.Cu") \
         + extract_pad_polys_for_net(board, net_name, pcbnew.B_Cu)
    print(f"  SW copper F.Cu shapes: {len(sw_F)} | B.Cu shapes: {len(sw_B)}")
    if not sw_F or not sw_B:
        report["feasibility"] = "NO_COPPER"
        print("  ABORT: missing F or B copper")
        return [], report

    # Collect drills + foreign copper.
    drills = collect_existing_drills(board)
    print(f"  existing drills board-wide: {len(drills)}")

    layer_ids = [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
                 pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.In5_Cu, pcbnew.In6_Cu,
                 pcbnew.In7_Cu, pcbnew.In8_Cu]
    foreign_pts = collect_foreign_copper_per_layer(board, net_name, layer_ids)
    foreign_zones = collect_foreign_zones_per_layer(board, net_name, layer_ids)
    print(f"  foreign copper points (sample F.Cu): {len(foreign_pts.get(pcbnew.F_Cu, []))}")

    # Candidate grid — generous margin.
    via_pad = args.via_pad
    via_drill = args.via_drill
    cands = generate_grid(sw_F, sw_B, args.pitch, margin=via_pad / 2.0)
    print(f"  candidate grid: {len(cands)}")

    # Score + filter with funnel diagnostics so the worker sees WHICH stage
    # gates each candidate (dangling vs hole-to-hole vs foreign-clearance).
    accepted = []
    rejections = {}
    funnel = {"after_dangle": 0, "after_h2h": 0, "after_foreign": 0}
    for (cx, cy) in cands:
        ok, reason, h2h = candidate_pass(
            cx, cy, drills, sw_F, sw_B,
            foreign_pts, foreign_zones,
            via_pad, via_drill,
            args.hole_to_hole, args.foreign_clearance,
            layer_ids,
        )
        # Funnel: replicate the gates so we can count where each cand died.
        insetF_dbg = signed_inside_margin(sw_F, cx, cy)
        insetB_dbg = signed_inside_margin(sw_B, cx, cy)
        eps = 1e-3
        if insetF_dbg + eps >= via_pad / 2.0 and insetB_dbg + eps >= via_pad / 2.0:
            funnel["after_dangle"] += 1
            if ok or (not ok and not reason.startswith("hole2hole")
                     and not reason.startswith("dangle")):
                # passed h2h; may still fail foreign
                pass
            if ok or (not reason.startswith("hole2hole")):
                funnel["after_h2h"] += 1
            if ok:
                funnel["after_foreign"] += 1
        if ok:
            accepted.append({"x": cx, "y": cy, "h2h": h2h,
                             "insetF": insetF_dbg, "insetB": insetB_dbg})
        else:
            rkey = reason.split()[0]
            rejections[rkey] = rejections.get(rkey, 0) + 1
    print(f"  candidate funnel: total={len(cands)} "
          f"| pass_dangle={funnel['after_dangle']} "
          f"| pass_h2h={funnel['after_h2h']} "
          f"| pass_foreign={funnel['after_foreign']} = accepted")
    print(f"  rejections by class: {rejections}")
    report["funnel"] = funnel
    report["rejected_summary"] = rejections

    # Greedy spread: maintain min-pitch ≥ args.spread_pitch between added vias
    # AND ≥ hole_to_hole + via_drill so newly added vias don't violate each
    # other.
    new_via_pitch_min = args.via_drill + args.hole_to_hole
    # Sort accepted by h2h (looser first → safer-margin candidates picked first).
    accepted.sort(key=lambda c: -c["h2h"])
    chosen = []

    # Per docs/CH1_DRONE_RELIABILITY_SWEEP §2: ≥16 (loop-L floor), ≥50 (ampacity).
    for c in accepted:
        if len(chosen) >= target_count:
            break
        too_close = False
        for ch in chosen:
            if math.hypot(c["x"] - ch["x"], c["y"] - ch["y"]) < new_via_pitch_min:
                too_close = True
                break
        if too_close:
            continue
        chosen.append(c)

    print(f"  chosen (spread-filtered): {len(chosen)} / target {target_count}")
    if len(chosen) >= target_count:
        report["feasibility"] = "MET"
    elif len(chosen) >= 16:
        report["feasibility"] = "LOOP_L_OK_AMPACITY_PARTIAL"
    else:
        report["feasibility"] = "INFEASIBLE_AT_TARGET"
    report["added"] = chosen
    report["accepted_pre_greedy"] = len(accepted)

    # Diagnostic actionable shopping list when target infeasible — what
    # the worker can do to unlock more vias.
    actions = []
    if rejections.get("dangle-B", 0) > rejections.get("hole2hole", 0):
        actions.append(
            "EXPAND B.Cu copper for this net (most candidates dangled on B). "
            "The B.Cu zone outline + LS-FET drain pads don't cover all positions "
            "where the F.Cu motor pad lives. Worker: add a B.Cu pour for "
            f"{net_name} spanning the F.Cu motor-pad area, then re-run.")
    if rejections.get("dangle-F", 0) > rejections.get("hole2hole", 0):
        actions.append(
            "EXPAND F.Cu copper for this net (most candidates dangled on F). "
            "Either the F.Cu zone has too many cutouts around VMOTOR_CH passives "
            "or the routed tracks don't form a contiguous F.Cu MOTOR pour. "
            "Worker: re-route VMOTOR_CH passives or relocate to free F.Cu area.")
    if rejections.get("hole2hole", 0) > 0 and len(chosen) < target_count:
        actions.append(
            "RELOCATE existing drills near the SW cluster — current 5 vias at "
            "0.8mm/0.6mm grid maximally pack the 0.20mm hole-to-hole rule. "
            "Worker: relocate VMOTOR_CH / GND vias or use HDI microvia (smaller "
            "drill + pad) inside the SW envelope to relax hole-to-hole.")
    if not actions:
        actions.append("TARGET MET — no shopping list needed.")
    report["unlock_actions"] = actions

    return chosen, report


def commit_vias(board, net_name, chosen, via_drill, via_pad):
    """Physically add PCB_VIA objects to board on F.Cu↔B.Cu for net."""
    net_obj = None
    for n in board.GetNetsByName().values():
        if n.GetNetname() == net_name:
            net_obj = n
            break
    if net_obj is None:
        raise RuntimeError(f"net {net_name} not found in board")
    for c in chosen:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(c["x"]),
                                       pcbnew.FromMM(c["y"])))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetDrill(pcbnew.FromMM(via_drill))
        v.SetWidth(pcbnew.FromMM(via_pad))
        v.SetNet(net_obj)
        board.Add(v)


# =============================================================================
# R19 symmetry projection
# =============================================================================

def project_to_other_phases(chosen, src_net, all_nets, origins):
    """Given chosen vias on src_net, project (dx, dy) offsets from src origin
    to each target net's origin. Returns dict: net → list of candidate
    positions (NOT validated)."""
    src_ox, src_oy, _, _ = origins[src_net]
    out = {}
    for tgt in all_nets:
        if tgt == src_net:
            continue
        ox, oy, _, _ = origins[tgt]
        dx, dy = ox - src_ox, oy - src_oy
        out[tgt] = [{"x": c["x"] + dx, "y": c["y"] + dy,
                     "h2h": -1.0, "insetF": -1.0, "insetB": -1.0}
                    for c in chosen]
    return out


def validate_projected(board, net_name, projected_cands, args):
    """Re-validate each projected candidate against board state for the
    target net. Returns the filtered list (keeps only positions that pass
    EVERY check on the target phase too)."""
    sw_F = extract_filled_polys(board, net_name, "F.Cu") \
         + extract_pad_polys_for_net(board, net_name, pcbnew.F_Cu)
    sw_B = extract_filled_polys(board, net_name, "B.Cu") \
         + extract_pad_polys_for_net(board, net_name, pcbnew.B_Cu)
    if not sw_F or not sw_B:
        return [], "no copper"
    drills = collect_existing_drills(board)
    layer_ids = [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
                 pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.In5_Cu, pcbnew.In6_Cu,
                 pcbnew.In7_Cu, pcbnew.In8_Cu]
    foreign_pts = collect_foreign_copper_per_layer(board, net_name, layer_ids)
    foreign_zones = collect_foreign_zones_per_layer(board, net_name, layer_ids)
    out = []
    rejected = 0
    for c in projected_cands:
        ok, reason, h2h = candidate_pass(
            c["x"], c["y"], drills, sw_F, sw_B,
            foreign_pts, foreign_zones,
            args.via_pad, args.via_drill,
            args.hole_to_hole, args.foreign_clearance,
            layer_ids,
        )
        if ok:
            c2 = dict(c)
            c2["h2h"] = h2h
            c2["insetF"] = signed_inside_margin(sw_F, c["x"], c["y"])
            c2["insetB"] = signed_inside_margin(sw_B, c["x"], c["y"])
            out.append(c2)
        else:
            rejected += 1
    return out, f"projected_rejected={rejected}"


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", required=True, type=str)
    p.add_argument("--net", required=True, type=str,
                   choices=list(PHASE_ORIGINS_CH1.keys()))
    p.add_argument("--target-count", type=int, default=50,
                   help="target via count per phase (default 50 = drone-grade ampacity FoS)")
    p.add_argument("--output", required=True, type=str)
    p.add_argument("--pitch", type=float, default=0.5,
                   help="candidate grid pitch in mm")
    p.add_argument("--via-drill", type=float, default=VIA_DRILL_MM_DEFAULT)
    p.add_argument("--via-pad", type=float, default=VIA_PAD_MM_DEFAULT)
    p.add_argument("--hole-to-hole", type=float, default=HOLE_TO_HOLE_MIN_MM)
    p.add_argument("--foreign-clearance", type=float, default=FOREIGN_COPPER_CLEAR_MM)
    p.add_argument("--symmetric-phases", action="store_true",
                   help="also add R19-symmetric vias to the other 2 phases "
                        "(MOTOR_A_CH1 → also B + C with mirrored positions)")
    p.add_argument("--report-json", type=str, default=None,
                   help="optional path to write the full report as JSON")
    return p.parse_args()


def main():
    args = parse_args()
    board_path = Path(args.board)
    if not board_path.exists():
        print(f"FAIL: board {board_path} not found", file=sys.stderr)
        sys.exit(2)

    board = pcbnew.LoadBoard(str(board_path))

    # ----------------- Single-net add path -----------------
    chosen, report = add_vias_for_net(board, args.net, args.target_count, args)

    overall_report = {
        "primary_net": args.net,
        "target_count": args.target_count,
        "primary_report": report,
        "symmetric_results": {},
    }

    if args.symmetric_phases:
        # R19: project to other phases + intersect feasibility (drop
        # candidates infeasible on ANY phase to preserve symmetric count).
        other_nets = [n for n in PHASE_ORIGINS_CH1 if n != args.net]
        projections = project_to_other_phases(chosen, args.net,
                                              [args.net] + other_nets,
                                              PHASE_ORIGINS_CH1)
        # Validate each projection.
        per_net_valid = {args.net: chosen}
        feasibility_mask = [True] * len(chosen)
        for tgt in other_nets:
            valid, dbg = validate_projected(board, tgt, projections[tgt], args)
            print(f"\n  R19-projected validate {tgt}: {len(valid)}/{len(projections[tgt])} OK ({dbg})")
            # Map back which indices were dropped.
            valid_set = {(round(c["x"], 4), round(c["y"], 4)) for c in valid}
            for i, c in enumerate(projections[tgt]):
                if (round(c["x"], 4), round(c["y"], 4)) not in valid_set:
                    feasibility_mask[i] = False
            per_net_valid[tgt] = valid

        # Apply symmetry: only commit positions where ALL phases feasible.
        sym_chosen_primary = [c for i, c in enumerate(chosen) if feasibility_mask[i]]
        sym_chosen_per_net = {args.net: sym_chosen_primary}
        for tgt in other_nets:
            ox, oy, _, _ = PHASE_ORIGINS_CH1[tgt]
            sox, soy, _, _ = PHASE_ORIGINS_CH1[args.net]
            dx, dy = ox - sox, oy - soy
            sym_chosen_per_net[tgt] = [
                {"x": c["x"] + dx, "y": c["y"] + dy,
                 "h2h": -1.0, "insetF": -1.0, "insetB": -1.0}
                for c in sym_chosen_primary
            ]
        print(f"\n  R19-symmetric final count per phase: {len(sym_chosen_primary)}")
        for tgt in other_nets + [args.net]:
            commit_vias(board, tgt, sym_chosen_per_net[tgt],
                        args.via_drill, args.via_pad)
        overall_report["symmetric_results"] = {
            n: len(sym_chosen_per_net[n]) for n in sym_chosen_per_net
        }
        overall_report["r19_symmetric_count"] = len(sym_chosen_primary)
    else:
        # Just commit the primary net's vias.
        commit_vias(board, args.net, chosen, args.via_drill, args.via_pad)

    # ----------------- Save -----------------
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    board.Save(str(out_path))
    print(f"\n  saved: {out_path}")

    # ----------------- Ampacity check + summary -----------------
    # Re-count vias on each MOTOR_X_CH1 net in the saved board.
    final_board = pcbnew.LoadBoard(str(out_path))
    counts = {n: 0 for n in PHASE_ORIGINS_CH1}
    for t in final_board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() in counts:
            counts[t.GetNetname()] += 1
    print(f"\n=== POST-ADD VIA COUNTS ===")
    for n, c in counts.items():
        cap_cont = c * VIA_AMP_CONT_PER_VIA
        cap_burst = c * VIA_AMP_BURST_PER_VIA
        need_cont = 100.0 * FOS_VIA_CURRENT
        need_burst = 280.0 * FOS_VIA_BURST
        ok_c = "PASS" if cap_cont >= need_cont else "FAIL"
        ok_b = "PASS" if cap_burst >= need_burst else "FAIL"
        print(f"  {n}: {c} vias → {cap_cont:.0f}A cont ({ok_c} vs {need_cont:.0f}A) "
              f"| {cap_burst:.0f}A burst ({ok_b} vs {need_burst:.0f}A)")
    overall_report["post_add_counts"] = counts

    if args.report_json:
        Path(args.report_json).write_text(json.dumps(overall_report, indent=2))
        print(f"\n  report-json: {args.report_json}")


if __name__ == "__main__":
    main()
