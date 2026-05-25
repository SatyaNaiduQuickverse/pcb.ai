#!/usr/bin/env python3
"""
build_validation_board.py — construct a synthetic KiCad PCB with
KNOWN geometry, where each test case's expected value is computed
inline from first principles (math) or cited textbook formulas.

The board is consumed by validate_audits.py which runs each audit
script against it and compares output to ground truth.

This is the OPPOSITE of using a real-world PCB as test input — the
truth lives in the construction code, so any audit-vs-truth mismatch
indicates a bug in the audit (not in the test fixture).

OUTPUT: /tmp/audit_validation_board.kicad_pcb + ground_truth.json
"""

import json
import sys
import uuid
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# ============================================================
# GROUND TRUTH — these values are the SPECIFICATION
# Computed from first principles or cited textbook formulas.
# ============================================================

GROUND_TRUTH = {
    # ---------- audit_loop_area ----------
    # CH1 switching loop: 4 components at corners of a 5×5mm square.
    # Shoelace formula on vertices (0,0)→(5,0)→(5,5)→(0,5):
    #   |Σ(xi·y(i+1) − x(i+1)·yi)| / 2
    #   = |0·0 − 5·0 + 5·5 − 5·0 + 5·5 − 0·5 + 0·0 − 0·5| / 2
    #   = |0 + 25 + 25 + 0| / 2  =  25.0 mm²
    # Reference: Wikipedia "Shoelace formula", also Bogatin Ch. 5.
    "loop_area_CH1_mm2": 25.0,
    "loop_area_CH1_status": "PASS",  # 25 < 30 (optimal threshold)

    # CH2: corners of 7×7mm square = 49 mm²
    # → 30 < 49 < 50 → WARN
    "loop_area_CH2_mm2": 49.0,
    "loop_area_CH2_status": "WARN",

    # CH3: corners of 8×8mm square = 64 mm²
    # → 64 > 50 → FAIL
    "loop_area_CH3_mm2": 64.0,
    "loop_area_CH3_status": "FAIL",

    # ---------- audit_decoupling ----------
    # U_DECOUP_OK: IC (8x8mm body, ≥4mm² so engages) at (50,50) F.Cu
    #   VDD pin at (50,50), VDD-named net "+3V3"
    #   Cap C_OK_1 (0805) at (51.5, 50) F.Cu on +3V3
    #   Pythagorean distance = sqrt(1.5² + 0²) = 1.5 mm ≤ 3.0 mm → PASS
    "decoupling_U_DECOUP_OK_distance_mm": 1.5,
    "decoupling_U_DECOUP_OK_status": "PASS",

    # U_DECOUP_FAIL: same IC pattern but cap at 4.5mm → FAIL (>3mm)
    "decoupling_U_DECOUP_FAIL_distance_mm": 4.5,
    "decoupling_U_DECOUP_FAIL_status": "FAIL",

    # U_DECOUP_WARN: cap at 2mm but on opposite layer B.Cu → WARN
    "decoupling_U_DECOUP_WARN_distance_mm": 2.0,
    "decoupling_U_DECOUP_WARN_status": "WARN",
}


# ============================================================
# BOARD CONSTRUCTION
# Coordinates in mm. Pcbnew uses nm internally; pcbnew.FromMM converts.
# ============================================================


def new_uuid():
    return str(uuid.uuid4())


def add_minimal_footprint(board, ref, x_mm, y_mm, layer_name, pad_net=None, bbox_mm=(2, 1)):
    """Construct an in-memory footprint with one SMD pad.

    Returns the footprint (added to board). bbox_mm controls the bounding
    box width/height (used by audit_decoupling.is_ic threshold).
    """
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(f"TEST_{ref}")
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    # SetLayer takes layer ID, not name
    layer_id = pcbnew.F_Cu if layer_name == "F.Cu" else pcbnew.B_Cu
    fp.SetLayer(layer_id)

    # Add a pad to give the footprint a bounding box + net association.
    pad = pcbnew.PAD(fp)
    pad.SetNumber("1")
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(bbox_mm[0]), pcbnew.FromMM(bbox_mm[1])))
    pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm)))
    # Pad layer set
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


def ensure_net(board, name):
    nc = board.FindNet(name)
    if nc is not None:
        return nc
    nc = pcbnew.NETINFO_ITEM(board, name)
    board.Add(nc)
    return nc


def main():
    board_out = Path("/tmp/audit_validation_board.kicad_pcb")
    truth_out = Path("/tmp/audit_validation_truth.json")

    board = pcbnew.NewBoard(str(board_out))

    # Set a reasonable board outline (Edge.Cuts rectangle).
    # Not strictly needed by audits but keeps KiCad happy.
    outline_pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    for i in range(4):
        x1, y1 = outline_pts[i]
        x2, y2 = outline_pts[(i + 1) % 4]
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        board.Add(seg)

    # Nets
    ensure_net(board, "+VMOTOR_CH1")
    ensure_net(board, "+VMOTOR_CH2")
    ensure_net(board, "+VMOTOR_CH3")
    ensure_net(board, "+3V3")
    ensure_net(board, "GND")

    # ============================================================
    # audit_loop_area test fixtures
    # ============================================================

    # CH1 — 5×5mm square → 25 mm² (PASS, ≤30 optimal)
    # Vertices in audit order: HS → LS → SHUNT → VMOTOR
    add_minimal_footprint(board, "Q_HS_CH1",     0,  0, "F.Cu", pad_net="+VMOTOR_CH1")
    add_minimal_footprint(board, "Q_LS_CH1",     5,  0, "F.Cu", pad_net="+VMOTOR_CH1")
    add_minimal_footprint(board, "R_SHUNT_CH1",  5,  5, "F.Cu", pad_net="GND")
    add_minimal_footprint(board, "C_VMOTOR_CH1", 0,  5, "F.Cu", pad_net="+VMOTOR_CH1")

    # CH2 — 7×7mm square → 49 mm² (WARN, between 30 and 50)
    add_minimal_footprint(board, "Q_HS_CH2",     20,  0, "F.Cu", pad_net="+VMOTOR_CH2")
    add_minimal_footprint(board, "Q_LS_CH2",     27,  0, "F.Cu", pad_net="+VMOTOR_CH2")
    add_minimal_footprint(board, "R_SHUNT_CH2",  27,  7, "F.Cu", pad_net="GND")
    add_minimal_footprint(board, "C_VMOTOR_CH2", 20,  7, "F.Cu", pad_net="+VMOTOR_CH2")

    # CH3 — 8×8mm square → 64 mm² (FAIL, >50)
    add_minimal_footprint(board, "Q_HS_CH3",     40,  0, "F.Cu", pad_net="+VMOTOR_CH3")
    add_minimal_footprint(board, "Q_LS_CH3",     48,  0, "F.Cu", pad_net="+VMOTOR_CH3")
    add_minimal_footprint(board, "R_SHUNT_CH3",  48,  8, "F.Cu", pad_net="GND")
    add_minimal_footprint(board, "C_VMOTOR_CH3", 40,  8, "F.Cu", pad_net="+VMOTOR_CH3")

    # (CH4 deliberately omitted to exercise SKIP path)

    # ============================================================
    # audit_decoupling test fixtures
    # ============================================================

    # U_DECOUP_OK — IC at (50,50) F.Cu with cap at 1.5mm away same layer
    # IC bbox must be >4mm² → use 8mm × 8mm pad (= 64 mm² bbox)
    add_minimal_footprint(board, "U_DECOUP_OK", 50, 50, "F.Cu",
                          pad_net="+3V3", bbox_mm=(8, 8))
    # Cap (0805 = bbox ~1.6×0.8 = 1.28mm² < 5mm² threshold)
    add_minimal_footprint(board, "C_DECOUP_OK", 51.5, 50, "F.Cu",
                          pad_net="+3V3", bbox_mm=(1.6, 0.8))

    # U_DECOUP_FAIL — IC at (50,70) with cap at 4.5mm → distance > 3mm
    add_minimal_footprint(board, "U_DECOUP_FAIL", 50, 70, "F.Cu",
                          pad_net="+3V3", bbox_mm=(8, 8))
    add_minimal_footprint(board, "C_DECOUP_FAIL", 54.5, 70, "F.Cu",
                          pad_net="+3V3", bbox_mm=(1.6, 0.8))

    # U_DECOUP_WARN — IC at (80,50) F.Cu with cap at 2mm on B.Cu (opposite)
    add_minimal_footprint(board, "U_DECOUP_WARN", 80, 50, "F.Cu",
                          pad_net="+3V3", bbox_mm=(8, 8))
    add_minimal_footprint(board, "C_DECOUP_WARN", 82, 50, "B.Cu",
                          pad_net="+3V3", bbox_mm=(1.6, 0.8))

    # Save.
    pcbnew.SaveBoard(str(board_out), board)
    truth_out.write_text(json.dumps(GROUND_TRUTH, indent=2))

    print(f"✓ Wrote {board_out} ({board_out.stat().st_size} bytes)")
    print(f"✓ Wrote {truth_out} ({len(GROUND_TRUTH)} truth entries)")
    for k, v in GROUND_TRUTH.items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
