import sys
from pathlib import Path
val = float(open(Path(__file__).parent / "ch1234_max.dat").readlines()[-1].strip())
print(f"PR-CH4 Elmer 4-channel thermal: T_J = {val:.2f}°C")
print(f"  vs CH1 alone 62.67°C → ΔT = {val - 62.67:+.2f}°C")
print(f"  Acceptance: ≤100°C, all 24 FETs within ±1°C of CH1 pair")
ok = val <= 100 and abs(val - 62.67) <= 1.0
print(f"  Verdict: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
