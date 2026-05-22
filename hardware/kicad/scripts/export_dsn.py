"""Phase 5b — export Specctra DSN from .kicad_pcb via pcbnew Python API."""
import os
import pcbnew
import sys

PCB_FILE = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
DSN_RAW = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1_raw.dsn"

print(f"Loading {PCB_FILE}...")
board = pcbnew.LoadBoard(PCB_FILE)
print(f"Loaded. Board size: {board.GetBoardEdgesBoundingBox().GetWidth() / 1e6:.1f} × "
      f"{board.GetBoardEdgesBoundingBox().GetHeight() / 1e6:.1f} mm")
print(f"Footprint count: {len(board.GetFootprints())}")
print(f"Net count: {len(board.GetNetsByName())}")

print(f"\nExporting Specctra DSN to {DSN_RAW}...")
result = pcbnew.ExportSpecctraDSN(board, DSN_RAW)
print(f"Result: {result}")

if os.path.exists(DSN_RAW):
    size = os.path.getsize(DSN_RAW)
    print(f"DSN written: {size:,} bytes")
else:
    print("ERROR: DSN file not created!")
    sys.exit(1)
