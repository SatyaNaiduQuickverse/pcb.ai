#!/usr/bin/env python3
"""
build_validation_board_v2.py — extended synthetic validation board.

Adds to v1:
  - Distinct nets per decoupling scenario (so WARN case isolates correctly)
  - Anchor test fixtures on F.Cu AND B.Cu (validates G1 layer-fix)
  - Parked components (validates --parked-exempt mode)

OUTPUT: /tmp/audit_validation_board_v2.kicad_pcb + ground_truth_v2.json
        + /tmp/audit_validation_lockfile_v2.yaml (anchor SSoT for G1)
"""

import json
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


GROUND_TRUTH_V2 = {
    # --- Loop area (same as v1) ---
    "loop_area_CH1_mm2": 25.0, "loop_area_CH1_status": "PASS",
    "loop_area_CH2_mm2": 49.0, "loop_area_CH2_status": "WARN",
    "loop_area_CH3_mm2": 64.0, "loop_area_CH3_status": "FAIL",

    # --- Decoupling (now with isolated nets) ---
    "decoupling_U_OK_distance_mm": 1.5,
    "decoupling_U_OK_status": "PASS",
    "decoupling_U_FAR_distance_mm": 4.5,
    "decoupling_U_FAR_status": "FAIL",
    "decoupling_U_OPPLAYER_distance_mm": 2.0,
    "decoupling_U_OPPLAYER_status": "WARN",

    # --- Anchor positions (G1) ---
    # H_TOP at (10,10) F.Cu rot=0 → PASS
    # H_BOT at (20,10) B.Cu rot=90 → PASS (validates IsFlipped fix for B.Cu)
    # H_DRIFT at (30,10) F.Cu but actual placed at (30.5,10) → FAIL on x
    "anchor_H_TOP_status": "PASS",
    "anchor_H_BOT_status": "PASS",
    "anchor_H_DRIFT_status": "FAIL",

    # --- Parked-exempt (G5/G6) ---
    # 3 parked components at x=200,201,202 (parking zone, ≥130)
    # 3 on-board components in normal zone
    # Without --parked-exempt: G5 flags parked as off-board (FAIL)
    # With --parked-exempt: G5 sees only the 3 on-board (PASS)
    "parked_exempt_skipped_count": 3,
}


def ensure_net(board, name):
    nc = board.FindNet(name)
    if nc is not None:
        return nc
    nc = pcbnew.NETINFO_ITEM(board, name)
    board.Add(nc)
    return nc


def add_fp(board, ref, x_mm, y_mm, layer_name="F.Cu", pad_net=None,
           bbox_mm=(2, 1), rotation_deg=0.0):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(f"V_{ref}")
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    # Footprints default to F.Cu. Flip ONCE for B.Cu (don't SetLayer then Flip
    # — that cancels). For pad layer_set we still use the post-flip layer id.
    if layer_name == "B.Cu":
        fp.Flip(fp.GetPosition(), False)
    layer_id = fp.GetLayer()  # whatever it ended up after potential flip
    if rotation_deg:
        fp.SetOrientationDegrees(rotation_deg)

    pad = pcbnew.PAD(fp)
    pad.SetNumber("1")
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(bbox_mm[0]), pcbnew.FromMM(bbox_mm[1])))
    pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    layer_set = pcbnew.LSET()
    layer_set.AddLayer(layer_id)
    pad.SetLayerSet(layer_set)
    if pad_net is not None:
        nc = board.FindNet(pad_net)
        if nc is not None:
            pad.SetNet(nc)
    fp.Add(pad)
    board.Add(fp)
    return fp


def main():
    board_out = Path("/tmp/audit_validation_board_v2.kicad_pcb")
    truth_out = Path("/tmp/audit_validation_truth_v2.json")
    lock_out = Path("/tmp/audit_validation_lockfile_v2.yaml")

    board = pcbnew.NewBoard(str(board_out))

    # ALSO simulate custom layer name to exercise G1 layer-name fix.
    # When the board has a renamed F.Cu (e.g. "F.Cu 3oz — heat layer"),
    # GetLayerName() returns that string. The fixed audit uses IsFlipped().
    board.SetLayerName(pcbnew.F_Cu, "F.Cu 3oz — heat layer")
    board.SetLayerName(pcbnew.B_Cu, "B.Cu 3oz — heat layer")

    # Outline 100x100
    for i in range(4):
        x1, y1 = [(0,0),(100,0),(100,100),(0,100)][i]
        x2, y2 = [(0,0),(100,0),(100,100),(0,100)][(i+1)%4]
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        s.SetLayer(pcbnew.Edge_Cuts)
        board.Add(s)

    # Nets — distinct per decoupling scenario
    for n in ["+VMOTOR_CH1", "+VMOTOR_CH2", "+VMOTOR_CH3", "GND",
              "+3V3_OK", "+3V3_FAR", "+3V3_OPP"]:
        ensure_net(board, n)

    # Loop area fixtures
    add_fp(board, "Q_HS_CH1", 0, 0, pad_net="+VMOTOR_CH1")
    add_fp(board, "Q_LS_CH1", 5, 0, pad_net="+VMOTOR_CH1")
    add_fp(board, "R_SHUNT_CH1", 5, 5, pad_net="GND")
    add_fp(board, "C_VMOTOR_CH1", 0, 5, pad_net="+VMOTOR_CH1")

    add_fp(board, "Q_HS_CH2", 20, 0, pad_net="+VMOTOR_CH2")
    add_fp(board, "Q_LS_CH2", 27, 0, pad_net="+VMOTOR_CH2")
    add_fp(board, "R_SHUNT_CH2", 27, 7, pad_net="GND")
    add_fp(board, "C_VMOTOR_CH2", 20, 7, pad_net="+VMOTOR_CH2")

    add_fp(board, "Q_HS_CH3", 40, 0, pad_net="+VMOTOR_CH3")
    add_fp(board, "Q_LS_CH3", 48, 0, pad_net="+VMOTOR_CH3")
    add_fp(board, "R_SHUNT_CH3", 48, 8, pad_net="GND")
    add_fp(board, "C_VMOTOR_CH3", 40, 8, pad_net="+VMOTOR_CH3")

    # Decoupling — each scenario on its own net so they don't cross-contaminate
    add_fp(board, "U_OK", 50, 50, pad_net="+3V3_OK", bbox_mm=(8, 8))
    add_fp(board, "C_OK", 51.5, 50, pad_net="+3V3_OK", bbox_mm=(1.6, 0.8))

    add_fp(board, "U_FAR", 50, 70, pad_net="+3V3_FAR", bbox_mm=(8, 8))
    add_fp(board, "C_FAR", 54.5, 70, pad_net="+3V3_FAR", bbox_mm=(1.6, 0.8))

    add_fp(board, "U_OPPLAYER", 80, 50, pad_net="+3V3_OPP", bbox_mm=(8, 8))
    add_fp(board, "C_OPPLAYER", 82, 50, layer_name="B.Cu",
           pad_net="+3V3_OPP", bbox_mm=(1.6, 0.8))

    # Anchor fixtures
    # H_TOP at (10,10) F.Cu rot=0 — matches lockfile exactly
    add_fp(board, "H_TOP", 10, 10, layer_name="F.Cu", rotation_deg=0)
    # H_BOT at (20,10) B.Cu rot=90 — matches lockfile (validates IsFlipped fix)
    add_fp(board, "H_BOT", 20, 10, layer_name="B.Cu", rotation_deg=90)
    # H_DRIFT placed at (30.5,10) but lockfile says (30,10) → fail on x
    add_fp(board, "H_DRIFT", 30.5, 10, layer_name="F.Cu", rotation_deg=0)

    # Parked components
    add_fp(board, "PARKED_1", 200, 5, pad_net="GND")
    add_fp(board, "PARKED_2", 205, 5, pad_net="GND")
    add_fp(board, "PARKED_3", 210, 5, pad_net="GND")

    pcbnew.SaveBoard(str(board_out), board)
    truth_out.write_text(json.dumps(GROUND_TRUTH_V2, indent=2))

    # Lockfile for G1 — minimal anchor-only YAML
    lock_yaml = """version: "v2-validation"
mount_holes:
  - ref: H_TOP
    pos: [10, 10]
    layer: F.Cu
    rotation: 0
  - ref: H_BOT
    pos: [20, 10]
    layer: B.Cu
    rotation: 90
  - ref: H_DRIFT
    pos: [30, 10]
    layer: F.Cu
    rotation: 0
fiducials: []
connectors: []
motor_pads: []
test_points: []
leds: []
parking_grid:
  origin: [200, -50]
  spacing_mm: 5
"""
    lock_out.write_text(lock_yaml)

    print(f"✓ {board_out} ({board_out.stat().st_size} bytes)")
    print(f"✓ {truth_out}")
    print(f"✓ {lock_out}")
    for k, v in GROUND_TRUTH_V2.items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
