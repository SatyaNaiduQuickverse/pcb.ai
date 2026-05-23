#!/usr/bin/env python3
"""extract_thermal.py — Rev-pol FET cluster T_J acceptance metrics."""
import sys
from pathlib import Path

MAX_DAT = Path(__file__).parent / "max_temp.dat"
VTU = Path(__file__).parent / "revpol_row" / "revpol_row_t0002.vtu"
ACC_T_J = 100.0  # °C continuous

if not MAX_DAT.exists():
    sys.exit(f"Missing {MAX_DAT}")
val = float(open(MAX_DAT).readlines()[-1].strip())
print(f"PR-S1 rev-pol FET continuous T_J:")
print(f"  Max board T (Elmer FEM steady-state): {val:.2f} °C")
print(f"  Acceptance: T_J ≤ {ACC_T_J} °C continuous")
print(f"  Verdict: {'PASS' if val <= ACC_T_J else 'FAIL'}")
print(f"  VTU artifact: {VTU} (exists: {VTU.exists()})")
sys.exit(0 if val <= ACC_T_J else 1)
