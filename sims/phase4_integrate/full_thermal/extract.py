#!/usr/bin/env python3
import sys
from pathlib import Path
val = float(open(Path(__file__).parent / "ch1234_max.dat").readlines()[-1].strip())
print(f"PR-A4-integrate 4-channel thermal: T_J = {val:.2f}C")
print(f"  All 24 FETs identical hotspot via 4-channel symmetry")
print(f"  Acceptance: T_J ≤ 100C cont")
ok = val <= 100
print(f"  Verdict: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
