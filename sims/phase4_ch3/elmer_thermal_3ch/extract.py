#!/usr/bin/env python3
import sys
from pathlib import Path
val = float(open(Path(__file__).parent / "ch123_max.dat").readlines()[-1].strip())
print(f"PR-CH3 Elmer regression CH1+CH2+CH3: T_J = {val:.2f}°C")
print(f"  vs CH1 alone (62.67) ΔT = {val - 62.67:+.2f}°C; vs CH1+CH2 (62.71) ΔT = {val - 62.71:+.2f}°C")
print(f"  Acceptance: ≤100°C, hot spots within ±1°C of CH1/CH2")
ok = val <= 100 and abs(val - 62.67) <= 1.0
print(f"  Verdict: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
