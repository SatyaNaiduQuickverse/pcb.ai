#!/usr/bin/env python3
"""
build_validation_board_v3.py — extended synthetic + topology yaml fixtures
to validate audit_via_stitching_density / audit_length_match /
audit_diff_pair_match / audit_kelvin_shunt_routing.

Builds:
  /tmp/audit_validation_board_v3.kicad_pcb
  /tmp/audit_validation_topology_v3.yaml
  /tmp/audit_validation_truth_v3.json

Truth is computed inline (track lengths via Pythagorean, via density via
count/area). Tracks are PCB_TRACK objects with explicit endpoints.

Per docs/AUDIT_VALIDATION.md methodology (ground-truth = construction code).
"""
import json
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# Board outline 100×100mm → area 100 cm²
BOARD_W = 100.0
BOARD_H = 100.0

# Via stitching: 16 vias on +VMOTOR over 100cm² → density = 0.16 vias/cm²
# Spec set in YAML to 0.1/cm² → 0.16 ≥ 0.1 → PASS
# Plus another net +VMOTOR_FAIL with 4 vias / 100cm² = 0.04 → spec 0.1 → FAIL
VMOTOR_VIA_COUNT_PASS = 16
VMOTOR_VIA_COUNT_FAIL = 4
DENSITY_SPEC = 0.1

# Diff pair OK: net DP_OK_POS = 30mm, DP_OK_NEG = 30.3mm → spread 0.3mm ≤ 0.5
# Diff pair FAIL: DP_FAIL_POS = 30mm, DP_FAIL_NEG = 35mm → spread 5mm > 0.5
# Length-match highway OK: HW_OK[1,2,3] = 50,51,49 → spread 2mm ≤ 2.5mm spec
# Length-match highway FAIL: HW_FAIL[1,2,3] = 50,60,49 → spread 11mm > 2.5mm

GROUND_TRUTH_V3 = {
    "via_stitching_PASS_count": VMOTOR_VIA_COUNT_PASS,
    "via_stitching_PASS_density": 0.16,
    "via_stitching_PASS_status": "PASS",
    "via_stitching_FAIL_count": VMOTOR_VIA_COUNT_FAIL,
    "via_stitching_FAIL_density": 0.04,
    "via_stitching_FAIL_status": "FAIL",

    "diff_pair_OK_spread_mm": 0.3,
    "diff_pair_OK_status": "PASS",
    "diff_pair_FAIL_spread_mm": 5.0,
    "diff_pair_FAIL_status": "FAIL",

    "length_match_OK_spread_mm": 2.0,
    "length_match_OK_status": "PASS",
    "length_match_FAIL_spread_mm": 11.0,
    "length_match_FAIL_status": "FAIL",

    "kelvin_OK_tap_at_centroid": True,
    "kelvin_OK_length_match_mm": 0.0,
    "kelvin_OK_status": "PASS",
}


def ensure_net(board, name):
    nc = board.FindNet(name)
    if nc is not None:
        return nc
    nc = pcbnew.NETINFO_ITEM(board, name)
    board.Add(nc)
    return nc


def add_track(board, net_name, x1, y1, x2, y2, layer=None, width_mm=0.25):
    layer = layer if layer is not None else pcbnew.F_Cu
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
    t.SetWidth(pcbnew.FromMM(width_mm))
    t.SetLayer(layer)
    nc = board.FindNet(net_name)
    if nc:
        t.SetNet(nc)
    board.Add(t)
    return t


def add_via(board, x, y, net_name, drill_mm=0.3, dia_mm=0.6):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    v.SetWidth(pcbnew.FromMM(dia_mm))
    v.SetDrill(pcbnew.FromMM(drill_mm))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    nc = board.FindNet(net_name)
    if nc:
        v.SetNet(nc)
    board.Add(v)
    return v


def add_minimal_fp(board, ref, x, y, pad_nets=None, pad_offsets=None):
    """Shunt-like 2-pad footprint at (x,y); pad_nets list [net1,net2]."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(f"V_{ref}")
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    fp.SetLayer(pcbnew.F_Cu)
    pad_nets = pad_nets or [None, None]
    pad_offsets = pad_offsets or [(-1.0, 0.0), (1.0, 0.0)]
    for i, (dx, dy) in enumerate(pad_offsets):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(i + 1))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.0), pcbnew.FromMM(1.0)))
        pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x + dx), pcbnew.FromMM(y + dy)))
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(ls)
        if pad_nets[i] is not None:
            nc = board.FindNet(pad_nets[i])
            if nc:
                pad.SetNet(nc)
        fp.Add(pad)
    board.Add(fp)
    return fp


def main():
    board_out = Path("/tmp/audit_validation_board_v3.kicad_pcb")
    topo_out = Path("/tmp/audit_validation_topology_v3.yaml")
    truth_out = Path("/tmp/audit_validation_truth_v3.json")

    board = pcbnew.NewBoard(str(board_out))

    # Board outline 100x100
    for i in range(4):
        x1, y1 = [(0,0),(100,0),(100,100),(0,100)][i]
        x2, y2 = [(0,0),(100,0),(100,100),(0,100)][(i+1)%4]
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        s.SetLayer(pcbnew.Edge_Cuts)
        board.Add(s)

    # Nets
    for n in ["+VMOTOR_TEST_PASS", "+VMOTOR_TEST_FAIL",
              "DP_OK_POS", "DP_OK_NEG", "DP_FAIL_POS", "DP_FAIL_NEG",
              "HW_OK_1", "HW_OK_2", "HW_OK_3",
              "HW_FAIL_1", "HW_FAIL_2", "HW_FAIL_3",
              "SHUNT_KELVIN_POS_CHTEST", "SHUNT_KELVIN_NEG_CHTEST"]:
        ensure_net(board, n)

    # ─── audit_via_stitching_density ────────────────────────────────────
    # 16 vias on +VMOTOR_TEST_PASS over 100cm² area
    for i in range(16):
        gx = 10 + (i % 4) * 5
        gy = 10 + (i // 4) * 5
        add_via(board, gx, gy, "+VMOTOR_TEST_PASS")
    # 4 vias on +VMOTOR_TEST_FAIL — density 0.04/cm² (under 0.1 spec)
    for i in range(4):
        add_via(board, 50 + i * 3, 50, "+VMOTOR_TEST_FAIL")

    # ─── audit_diff_pair_match ──────────────────────────────────────────
    # DP_OK_POS: straight line 0→30mm = 30mm
    add_track(board, "DP_OK_POS", 5, 70, 35, 70)
    # DP_OK_NEG: 0→30.3mm = 30.3mm — spread 0.3 ≤ 0.5 PASS
    add_track(board, "DP_OK_NEG", 5, 71, 35.3, 71)

    # DP_FAIL_POS: 30mm; DP_FAIL_NEG: 35mm — spread 5mm > 0.5 FAIL
    add_track(board, "DP_FAIL_POS", 60, 70, 90, 70)
    add_track(board, "DP_FAIL_NEG", 60, 71, 95, 71)

    # ─── audit_length_match ─────────────────────────────────────────────
    # HW_OK group: 50, 51, 49 mm; spread 2mm; spec 2.5 → PASS
    add_track(board, "HW_OK_1", 5, 80, 55, 80)        # 50
    add_track(board, "HW_OK_2", 5, 81, 56, 81)        # 51
    add_track(board, "HW_OK_3", 5, 82, 54, 82)        # 49
    # HW_FAIL group: 50, 60, 49 → spread 11 > 2.5 → FAIL
    add_track(board, "HW_FAIL_1", 5, 88, 55, 88)      # 50
    add_track(board, "HW_FAIL_2", 5, 89, 65, 89)      # 60
    add_track(board, "HW_FAIL_3", 5, 90, 54, 90)      # 49

    # ─── audit_kelvin_shunt_routing ─────────────────────────────────────
    # Shunt R_SHUNT_CHTEST at (40, 40); pads at (39, 40) pos / (41, 40) neg
    # Kelvin sense tracks start AT pad centroids, run parallel right by 10mm.
    add_minimal_fp(board, "R_SHUNT_CHTEST", 40, 40,
                   pad_nets=["SHUNT_KELVIN_POS_CHTEST", "SHUNT_KELVIN_NEG_CHTEST"],
                   pad_offsets=[(-1.0, 0.0), (1.0, 0.0)])
    # Pos sense: starts at (39,40) — the pad centre — runs to (49,40) = 10mm
    add_track(board, "SHUNT_KELVIN_POS_CHTEST", 39.0, 40.0, 49.0, 40.0)
    # Neg sense: starts at (41,40) — the pad centre — runs to (51,40) = 10mm
    add_track(board, "SHUNT_KELVIN_NEG_CHTEST", 41.0, 40.0, 51.0, 40.0)
    # Length-match: |10-10|=0mm; tap-at-centroid PASS; separation ≤2mm

    pcbnew.SaveBoard(str(board_out), board)

    # Topology yaml — audits expect nets.NAME schema (not arrays).
    # via_stitching_density_per_cm2 + length_match_group are per-net.
    topo = """version: "v3-validation"
nets:
  "+VMOTOR_TEST_PASS":
    constraint:
      via_stitching_density_per_cm2: 0.1
  "+VMOTOR_TEST_FAIL":
    constraint:
      via_stitching_density_per_cm2: 0.1
  HW_OK_1:
    length_match_group: hw_ok
    length_match_tolerance_mm: 2.5
  HW_OK_2:
    length_match_group: hw_ok
    length_match_tolerance_mm: 2.5
  HW_OK_3:
    length_match_group: hw_ok
    length_match_tolerance_mm: 2.5
  HW_FAIL_1:
    length_match_group: hw_fail
    length_match_tolerance_mm: 2.5
  HW_FAIL_2:
    length_match_group: hw_fail
    length_match_tolerance_mm: 2.5
  HW_FAIL_3:
    length_match_group: hw_fail
    length_match_tolerance_mm: 2.5

diff_pair_groups:
  - name: dp_ok
    pos: DP_OK_POS
    neg: DP_OK_NEG
    tolerance_mm: 0.5
  - name: dp_fail
    pos: DP_FAIL_POS
    neg: DP_FAIL_NEG
    tolerance_mm: 0.5

length_match_groups:
  - name: hw_ok
    nets: [HW_OK_1, HW_OK_2, HW_OK_3]
    tolerance_mm: 2.5
  - name: hw_fail
    nets: [HW_FAIL_1, HW_FAIL_2, HW_FAIL_3]
    tolerance_mm: 2.5

kelvin_pairs:
  - channel: CHTEST
    shunt_ref: R_SHUNT_CHTEST
    pos_net: SHUNT_KELVIN_POS_CHTEST
    neg_net: SHUNT_KELVIN_NEG_CHTEST
    tolerance_mm: 0.5
    max_separation_mm: 5.0
"""
    topo_out.write_text(topo)
    truth_out.write_text(json.dumps(GROUND_TRUTH_V3, indent=2))

    print(f"✓ {board_out} ({board_out.stat().st_size} bytes)")
    print(f"✓ {topo_out}")
    print(f"✓ {truth_out}")
    for k, v in GROUND_TRUTH_V3.items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
