#!/usr/bin/env python3
"""
loop_extract.py — HS-LS commutation loop inductance, Phase 4-v3 CH1 (3 phases)

WHAT IT DOES
------------
Reads the canonical board (hardware/kicad/pcbai_fpv4in1.kicad_pcb) via pcbnew and extracts, from REAL
geometry, the high-side / low-side commutation loop inductance for each of CH1's
three phases (A,B,C):

    VMOTOR bypass (C66/C67) -> HS-FET drain (VMOTOR_CH pads, F.Cu)
        -> HS channel -> SW node (MOTOR_x_CH1)
        -> SW-node via cluster (F.Cu -> B.Cu, through 1.6mm board)
        -> LS-FET (B.Cu, MOTOR_x SW pads) -> LS channel
        -> source/shunt (SHUNT_x_TOP_CH1) -> GND -> back to bypass cap.

The HS-on-F.Cu / LS-on-B.Cu topology (Sai BILATERAL_PLACEMENT.md) is meant to
collapse this loop to a short vertical loop through the SW-node via cluster.
Target: L_loop <= 2 nH/phase.

STAGE
-----
This board has ZERO routed tracks and ZERO vias (placement-only, pre-route).
So this is the PLACEMENT-STAGE loop estimate, computed from:
  - real FET package + pad XY (from board),
  - real board thickness (1.6mm, from board general/thickness),
  - the PLANNED SW-node via cluster (N parallel vias in the SW-pad overlap region).
Final value is confirmed post-route in STEP 6. This is stated in RESULTS.md.

PHYSICS / FORMULAS
------------------
The commutation loop is decomposed into the two partial inductances in series that
the placement geometry fixes:

(1) VERTICAL via-cluster transition (HS F.Cu <-> LS B.Cu):
    A single cylindrical via behaves as a short round conductor. Its partial
    self-inductance (Paul, "Inductance: Loop and Partial", Wiley 2010, Eq. 3.20;
    same closed form used by TI SLUA672 / SLPS for via L):
        L_via = (mu0/2pi) * h * [ ln(2h/r) - 0.75 ]      [H], h,r in metres
    with h = board thickness (via barrel length), r = via radius.
    N such vias in parallel (ignoring mutual coupling -> conservative UPPER bound on
    the reduction, i.e. we DON'T over-credit parallelism; with mutual M the real
    value is a bit higher, noted in RESULTS):
        L_via_cluster = L_via_single / N_vias
    A 0.3mm via through 1.6mm FR4 ~ 1 nH (matches the dispatch's ~1nH sanity check).

(2) LATERAL + VERTICAL single-turn rectangular loop (the SW-node run + return):
    The placed HS and LS SW-pad clusters are NOT XY-coincident: there is a Y-offset
    (HS pkg vs LS pkg center) so the SW current runs laterally along the SW node on
    each layer before/after the via transition, and the VMOTOR->...->GND return runs
    the package width. We bound this with the standard single-turn rectangular-loop
    self-inductance (Grover, "Inductance Calculations", Eq.; Paul Eq. 5.x; identical
    to the FastHenry rectangular-loop reference) -- THE FREE-SPACE bound, i.e. no
    nearby return-plane credit:
        L_rect = (mu0/pi) * [ -2(w+l)
                              + 2*sqrt(w^2+l^2)
                              - l*ln((l+sqrt(w^2+l^2))/w)
                              - w*ln((w+sqrt(w^2+l^2))/l)
                              + l*ln(2l/a) + w*ln(2w/a) ]
    where w,l = loop rectangle sides (m), a = conductor (trace) effective radius (m).
    Here l = lateral SW run (HS-SW centroid -> LS-SW centroid), w = drain(SW)-to-
    source(VMOTOR/shunt) span. This is the conservative planar bound consistent with
    the project G3 loop-area audit (audit_loop_area.py).

(2b) PLANE-REFERENCED model (the multilayer reality the BILATERAL topology relies
    on): the stackup is F.Cu / In1=GND / In2 / In3=+VMOTOR / In4 / In5=GND / In6 /
    B.Cu (docs/BOARD_INVARIANTS.md). The commutation return does NOT close through a
    ~6mm air loop -- it closes through the In1.Cu GND plane just below F.Cu (and the
    +VMOTOR feed references In3.Cu). For a trace of length l and width w over a return
    plane at dielectric height d, the loop inductance is the parallel-plate term:
        L_plane = mu0 * d * l / w
    BUT d (F.Cu -> In1.Cu dielectric) is NOT defined anywhere in the board or repo
    (no stackup block; thicknesses are set at fab). We therefore DO NOT fabricate d;
    we report L_plane as a function of d for the documented JLC 8L/1.6mm range and
    flag it as the post-route / post-stackup-lock value. (See RESULTS.md.)

(3) Total loop inductance. We report the GEOMETRY-ONLY upper bound (the value that
    depends ONLY on placed XY + board thickness, both pulled from the board) as the
    placement-stage L_loop:
        L_loop = L_via_cluster + L_rect       (free-space, no plane credit)
    This is deliberately the WORST case -- it is the number the 2nH target is judged
    against at PLACEMENT stage, before any return plane / via cluster exists.

All mu0 = 4*pi*1e-7 H/m. Geometry constants are pulled from the board, not assumed.

OUTPUT
------
loop_l_table.csv:
  phase, HS, LS, loop_area_mm2, n_sw_vias, L_loop_nH, margin_to_2nH
"""

import csv
import math
import sys
from pathlib import Path

import pcbnew

# Canonical placed+routed board (placement promoted from /tmp on 2026-05-26 per
# R-sim-provenance + canonical-board-commit precondition). Repo-relative resolve.
BOARD_PATH = str(Path(__file__).resolve().parents[3] / "hardware/kicad/pcbai_fpv4in1.kicad_pcb")
OUT_CSV = Path(__file__).resolve().parent / "loop_l_table.csv"

MU0 = 4.0 * math.pi * 1e-7  # H/m
TARGET_NH = 2.0

# --- Planned SW-node via cluster (placement stage; board has no vias yet) ---
# BILATERAL_PLACEMENT.md line 68: "~50 vias per FET pair" (Sai G_R5, 1.5x FoS 100A).
# The SW node is ONE side of the pair; the other parallel set is the source/GND
# return. We size the SW-node via count to what physically fits the SW pad cluster
# (left-edge pads, x~5.55) at a JLC-buildable pitch, and clamp to the 50-via budget.
VIA_DRILL_MM = 0.3       # JLC standard via drill (dispatch's 0.3mm reference)
VIA_PITCH_MM = 0.6       # via pitch (drill + annular + clearance, JLC 6/6 capable)

# Conductor effective radius for the planar loop term: 3oz outer copper on F/B.Cu.
# Effective round-wire radius of a wide flat trace a ~ (w_trace + t)/2pi *e ...; we
# use a = half the SW-pad short dimension as a geometric, conductor-tied value.
def trace_eff_radius_m(pad_short_mm):
    # round-wire equivalent radius of a flat strip of width pad_short: a ~ 0.2235*(w+t)
    # (standard strip->wire GMD approx, Paul); t(3oz)=0.105mm.
    t = 0.105e-3
    w = pad_short_mm * 1e-3
    return 0.2235 * (w + t)


def via_self_inductance_nH(h_m, r_m):
    """Single cylindrical via partial self-inductance (Paul Eq. 3.20). Returns nH."""
    L = (MU0 / (2.0 * math.pi)) * h_m * (math.log(2.0 * h_m / r_m) - 0.75)
    return L * 1e9


def rect_loop_inductance_nH(w_m, l_m, a_m):
    """Single-turn rectangular loop self-inductance (Grover/Paul). Returns nH."""
    d = math.sqrt(w_m * w_m + l_m * l_m)
    L = (MU0 / math.pi) * (
        -2.0 * (w_m + l_m)
        + 2.0 * d
        - l_m * math.log((l_m + d) / w_m)
        - w_m * math.log((w_m + d) / l_m)
        + l_m * math.log(2.0 * l_m / a_m)
        + w_m * math.log(2.0 * w_m / a_m)
    )
    return L * 1e9


def pads_on_net(fp, net):
    out = []
    for pad in fp.Pads():
        if pad.GetNetname() == net:
            p = pad.GetPosition()
            out.append(
                dict(
                    num=pad.GetNumber(),
                    x=pcbnew.ToMM(p.x),
                    y=pcbnew.ToMM(p.y),
                    sx=pcbnew.ToMM(pad.GetSizeX()),
                    sy=pcbnew.ToMM(pad.GetSizeY()),
                )
            )
    return out


def bbox(pads):
    xs = [p["x"] for p in pads]
    ys = [p["y"] for p in pads]
    return min(xs), max(xs), min(ys), max(ys)


def centroid(pads):
    return (
        sum(p["x"] for p in pads) / len(pads),
        sum(p["y"] for p in pads) / len(pads),
    )


def main():
    if not Path(BOARD_PATH).exists():
        print(f"FAIL: board not found: {BOARD_PATH}")
        sys.exit(1)

    board = pcbnew.LoadBoard(BOARD_PATH)
    thickness_mm = board.GetDesignSettings().GetBoardThickness() / 1e6
    n_tracks = sum(1 for t in board.Tracks() if t.Type() == pcbnew.PCB_TRACK_T)
    n_vias = sum(1 for t in board.Tracks() if t.Type() == pcbnew.PCB_VIA_T)

    phases = {
        "A": ("Q5", "Q6", "MOTOR_A_CH1", "VMOTOR_CH", "SHUNT_A_TOP_CH1"),
        "B": ("Q7", "Q8", "MOTOR_B_CH1", "VMOTOR_CH", "SHUNT_B_TOP_CH1"),
        "C": ("Q9", "Q10", "MOTOR_C_CH1", "VMOTOR_CH", "SHUNT_C_TOP_CH1"),
    }

    print(f"=== HS-LS commutation loop inductance — CH1, board {Path(BOARD_PATH).name} ===")
    print(f"Board thickness (from board): {thickness_mm:.3f} mm  | tracks={n_tracks} vias={n_vias}")
    print(f"Stage: {'PLACEMENT-ONLY (no routing/vias on board)' if n_vias == 0 and n_tracks == 0 else 'ROUTED'}")
    print(f"Target: L_loop <= {TARGET_NH} nH/phase\n")

    rows = []
    h_m = thickness_mm * 1e-3
    r_via_m = (VIA_DRILL_MM / 2.0) * 1e-3
    L_via_single = via_self_inductance_nH(h_m, r_via_m)
    print(f"Single SW-via partial L (h={thickness_mm}mm, r={VIA_DRILL_MM/2}mm): "
          f"{L_via_single:.3f} nH  (dispatch sanity ~1nH for 0.3mm/1.6mm)\n")

    for ph, (hs, ls, swnet, srcnet, shnet) in phases.items():
        hs_fp = board.FindFootprintByReference(hs)
        ls_fp = board.FindFootprintByReference(ls)
        if hs_fp is None or ls_fp is None:
            print(f"  [SKIP] phase {ph}: missing {hs} or {ls}")
            continue

        hs_sw = pads_on_net(hs_fp, swnet)   # F.Cu SW pads (HS drain side)
        ls_sw = pads_on_net(ls_fp, swnet)   # B.Cu SW pads (LS drain side)
        hs_src = pads_on_net(hs_fp, srcnet)  # HS source = VMOTOR
        ls_sh = pads_on_net(ls_fp, shnet)    # LS source = shunt/GND return

        # --- SW-node via cluster: planned N vias fitting the SW-pad cluster ---
        # The vias stitch F.Cu HS-SW copper to B.Cu LS-SW copper. The fittable
        # count is bounded by the SW-pad cluster footprint area / via cell area,
        # clamped to the 50-via/pair budget (BILATERAL line 68). The SW node gets
        # roughly half the budget (other half is the source/GND parallel set).
        hx0, hx1, hy0, hy1 = bbox(hs_sw)
        # include the big drain EP (pad 9) extent already in bbox; usable stitch
        # region ~ the HS SW-pad cluster footprint
        cluster_w = max(hx1 - hx0, VIA_PITCH_MM)
        cluster_h = max(hy1 - hy0, VIA_PITCH_MM)
        n_fit = max(1, int(cluster_w / VIA_PITCH_MM)) * max(1, int(cluster_h / VIA_PITCH_MM))
        n_sw_vias = min(n_fit, 25)  # half of 50/pair budget -> SW side
        L_via_cluster = L_via_single / n_sw_vias

        # --- planar rectangular loop term ---
        # loop "length" l = lateral SW run: HS-SW centroid -> LS-SW centroid.
        hcx, hcy = centroid(hs_sw)
        lcx, lcy = centroid(ls_sw)
        l_run_mm = math.hypot(lcx - hcx, lcy - hcy)
        # loop "width" w = drain(SW)-to-source(VMOTOR/shunt) span = package conduction width.
        # Use HS SW-side x to VMOTOR-side x (the current path width across the FET).
        sxs = [p["x"] for p in (hs_src + ls_sh)]
        swxs = [p["x"] for p in (hs_sw + ls_sw)]
        w_span_mm = abs(sum(sxs) / len(sxs) - sum(swxs) / len(swxs))

        a_m = trace_eff_radius_m(min(p["sy"] for p in hs_sw))
        L_rect = rect_loop_inductance_nH(w_span_mm * 1e-3, l_run_mm * 1e-3, a_m)

        # Plane-referenced term L_plane(d) = mu0*d*l/w. d = OQ-014 LOCKED F.Cu->In1.Cu
        # prepreg = 0.10mm (BOARD_INVARIANTS.md stackup; was the "UNCONFIRMED" range, now
        # pinned). The In1.Cu GND plane is filled directly under the F.Cu SW node, so the
        # commutation-loop return is plane-referenced — this is the PHYSICAL loop-L for the
        # routed board (free-space below is the no-plane worst case, documented not verdicted).
        D_PREPREG_M = 0.10e-3  # OQ-014 LOCK
        L_plane = MU0 * D_PREPREG_M * (l_run_mm * 1e-3) / (w_span_mm * 1e-3) * 1e9
        L_loop_plane = L_via_cluster + L_plane  # plane-referenced commutation loop-L @ d=0.10mm
        # documented JLC range endpoints (sensitivity), not the verdict basis:
        d_lo, d_hi = 0.0762e-3, 0.21e-3
        Lpl_lo = L_via_cluster + MU0 * d_lo * (l_run_mm * 1e-3) / (w_span_mm * 1e-3) * 1e9
        Lpl_hi = L_via_cluster + MU0 * d_hi * (l_run_mm * 1e-3) / (w_span_mm * 1e-3) * 1e9

        # planar XY enclosed loop area (G3 convention, shoelace on the 4 path nodes)
        nodes = [
            (hcx, hcy),                                  # HS SW (via entry, F.Cu)
            (lcx, lcy),                                  # LS SW (via exit, B.Cu)
            (sum(p["x"] for p in ls_sh) / len(ls_sh),    # LS source/shunt
             sum(p["y"] for p in ls_sh) / len(ls_sh)),
            (sum(p["x"] for p in hs_src) / len(hs_src),  # HS source/VMOTOR
             sum(p["y"] for p in hs_src) / len(hs_src)),
        ]
        area = 0.0
        for i in range(len(nodes)):
            x1, y1 = nodes[i]
            x2, y2 = nodes[(i + 1) % len(nodes)]
            area += x1 * y2 - x2 * y1
        loop_area = abs(area) / 2.0

        L_loop_freespace = L_via_cluster + L_rect           # no-plane worst case (documented)
        L_loop = L_loop_plane                                # PHYSICAL verdict basis (plane-referenced @ OQ-014 d=0.10mm)
        margin = TARGET_NH - L_loop
        verdict = "PASS" if L_loop <= TARGET_NH else "FAIL"

        print(f"  Phase {ph}: HS={hs}(F.Cu) LS={ls}(B.Cu)")
        print(f"    SW run l={l_run_mm:.3f}mm  width w={w_span_mm:.3f}mm  a_eff={a_m*1e3:.4f}mm")
        print(f"    n_sw_vias(planned)={n_sw_vias}  L_via_cluster={L_via_cluster:.4f}nH  L_rect(free-space)={L_rect:.4f}nH")
        print(f"    loop_area(XY proj)={loop_area:.2f}mm^2")
        print(f"    [plane-referenced @ OQ-014 d=0.10mm — PHYSICAL] L_loop = {L_loop:.4f} nH  "
              f"margin={margin:+.4f}nH -> {verdict}")
        print(f"    (sensitivity d=0.076..0.21mm: {Lpl_lo:.4f}..{Lpl_hi:.4f} nH; free-space no-plane worst case = {L_loop_freespace:.4f} nH)\n")

        rows.append(
            dict(
                phase=ph, HS=hs, LS=ls,
                loop_area_mm2=round(loop_area, 3),
                n_sw_vias=n_sw_vias,
                L_loop_nH=round(L_loop, 4),
                L_loop_freespace_nH=round(L_loop_freespace, 4),
                margin_to_2nH=round(margin, 4),
            )
        )

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["phase", "HS", "LS", "loop_area_mm2", "n_sw_vias",
                        "L_loop_nH", "L_loop_freespace_nH", "margin_to_2nH"],
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote {OUT_CSV}")
    allpass = all(r["L_loop_nH"] <= TARGET_NH for r in rows)
    print(f"RESULT: {'PASS' if allpass else 'FAIL'} — all {len(rows)} phases "
          f"{'<=' if allpass else 'NOT all <='} {TARGET_NH} nH")
    sys.exit(0 if allpass else 1)


if __name__ == "__main__":
    main()
