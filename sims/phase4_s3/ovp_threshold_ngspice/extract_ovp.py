#!/usr/bin/env python3
"""extract_ovp.py — OVP trip threshold."""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "ovp_data.raw"
if not RAW.exists(): sys.exit(f"Missing {RAW}")
data = np.loadtxt(RAW, skiprows=1)
t = data[:, 0]; v_bat = data[:, 1]; v_out_od = data[:, 3]
# OUT_OD switches from 3.3 to 0 at trip
fall = np.where(np.diff(v_out_od) < -1.0)[0]
if len(fall) == 0: sys.exit("No trip detected")
i_trip = fall[0]
v_trip = float(v_bat[i_trip+1])
ACC = 26.5
print(f"PR-S3 OVP threshold:")
print(f"  V_trip: {v_trip:.2f} V")
print(f"  Acceptance: V_trip ≤ {ACC} V")
print(f"  Verdict: {'PASS' if v_trip <= ACC else 'FAIL'}")
sys.exit(0 if v_trip <= ACC else 1)
