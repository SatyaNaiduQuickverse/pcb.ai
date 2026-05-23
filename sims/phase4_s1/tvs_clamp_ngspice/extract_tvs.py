#!/usr/bin/env python3
"""extract_tvs.py — TVS clamp sim acceptance extract."""
import numpy as np
import sys
from pathlib import Path

RAW = Path(__file__).parent / "tvs_data.raw"
if not RAW.exists(): sys.exit(f"Missing {RAW}")
data = np.loadtxt(RAW, skiprows=1)
t = data[:, 0]; v_bus = data[:, 1]
v_clamp = float(np.max(v_bus))
t_peak = float(t[np.argmax(v_bus)])
ACC = 55.0  # SMBJ33A V_CL spec + Q1-Q4 V_DS_max margin
print(f"PR-S1 TVS clamp acceptance metrics:")
print(f"  V_BUS peak: {v_clamp:.2f} V at t={t_peak*1000:.3f} ms")
print(f"  Acceptance: V_clamp ≤ {ACC} V")
print(f"  Verdict: {'PASS' if v_clamp <= ACC else 'FAIL'}")
sys.exit(0 if v_clamp <= ACC else 1)
