#!/usr/bin/env python3
"""extract_thermal.py — Bulk cap T_J acceptance."""
import sys
from pathlib import Path
MAX_DAT = Path(__file__).parent / "cap_max_temp.dat"
ACC = 105.0
if not MAX_DAT.exists(): sys.exit(f"Missing {MAX_DAT}")
val = float(open(MAX_DAT).readlines()[-1].strip())
print(f"PR-S2 bulk cap ESR T_J:")
print(f"  Max board T (Elmer FEM steady-state): {val:.2f} °C")
print(f"  Acceptance: T_J ≤ {ACC} °C (polymer cap max)")
print(f"  Verdict: {'PASS' if val <= ACC else 'FAIL'}")
sys.exit(0 if val <= ACC else 1)
