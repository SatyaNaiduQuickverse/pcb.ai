#!/usr/bin/env python3
import sys
from pathlib import Path
val = float(open(Path(__file__).parent / "ch1ch2_max.dat").readlines()[-1].strip())
print(f"PR-CH2 Elmer regression CH1+CH2 thermal: T_J = {val:.2f}°C")
print(f"  vs CH1 alone: 62.67°C → ΔT = {val - 62.67:+.2f}°C (symmetry payoff: identical hotspot)")
print(f"  Acceptance: T_J ≤ 100°C continuous; CH1↔CH2 ΔT ≤ 1°C")
ok = val <= 100 and abs(val - 62.67) <= 1.0
print(f"  Verdict: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
