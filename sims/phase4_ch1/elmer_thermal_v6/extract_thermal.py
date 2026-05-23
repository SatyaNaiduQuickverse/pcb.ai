#!/usr/bin/env python3
"""extract — CH1 thermal v6"""
import sys
from pathlib import Path
val = float(open(Path(__file__).parent / "ch1_max_temp.dat").readlines()[-1].strip())
print(f"PR-CH1 thermal v6 (P=12 Y=56/68/80, 70A cont): T_J = {val:.2f}°C (≤100°C cont)")
print(f"Verdict: {'PASS' if val <= 100 else 'FAIL'}")
sys.exit(0 if val <= 100 else 1)
