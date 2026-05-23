#!/usr/bin/env python3
"""extract_pairwise.py — S1+S2 inrush combined sim metrics."""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "s1s2_inrush.raw"
if not RAW.exists(): sys.exit(f"Missing {RAW}")
data = np.loadtxt(RAW, skiprows=1)
t = data[:, 0]; i_sense = data[:, 1]; v_c = data[:, 3]
ipeak = float(np.max(np.abs(i_sense)))
target = 0.95 * 25.2
above = np.where(v_c >= target)[0]
t_95 = float(t[above[0]]) if len(above) else float('nan')
print(f"PR-S2 pair-wise S1+S2 inrush:")
print(f"  Peak inrush current: {ipeak:.2f} A (≤200A: {'PASS' if ipeak <= 200 else 'FAIL'})")
print(f"  t_95% to 23.94V: {t_95*1000:.3f} ms (≤5ms: {'PASS' if t_95 <= 5e-3 else 'FAIL'})")
ok = ipeak <= 200 and t_95 <= 5e-3
print(f"  OVERALL: {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
