#!/usr/bin/env python3
"""extract — S5→S3 supervisor crosstalk"""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "s5_supervisor_data.raw"
data = np.loadtxt(RAW, skiprows=1)
t = data[:,0]; v_ina = data[:,2]
mask = t > 500e-6
pp = float(np.max(v_ina[mask]) - np.min(v_ina[mask]))
print(f"PR-S5→S3 supervisor: V_INA pk-pk = {pp*1000:.2f} mV (≤50mV)")
print(f"Verdict: {'PASS' if pp <= 0.050 else 'FAIL'}")
sys.exit(0 if pp <= 0.050 else 1)
