#!/usr/bin/env python3
"""extract_crosstalk.py — S2→S3 supervisor + Hall crosstalk."""
import numpy as np, sys
from pathlib import Path
RAW = Path(__file__).parent / "s2_s3_crosstalk.raw"
if not RAW.exists(): sys.exit(f"Missing {RAW}")
data = np.loadtxt(RAW, skiprows=1)
t = data[:, 0]
v_ina = data[:, 2]; v_hall_div = data[:, 4]
mask = t > 500e-6
v_ina_pp = float(np.max(v_ina[mask]) - np.min(v_ina[mask]))
v_hall_pp = float(np.max(v_hall_div[mask]) - np.min(v_hall_div[mask]))
print(f"PR-S3 S2→S3 crosstalk metrics:")
print(f"  (a) V_INA ripple at supervisor input pk-pk: {v_ina_pp*1000:.2f} mV (≤50mV)")
print(f"  (b) V_HALL_OUT noise pk-pk: {v_hall_pp*1000:.2f} mV (≤10mV)")
a_ok = v_ina_pp <= 0.050
b_ok = v_hall_pp <= 0.010
print(f"  Verdicts: (a) {'PASS' if a_ok else 'FAIL'}, (b) {'PASS' if b_ok else 'FAIL'}")
sys.exit(0 if (a_ok and b_ok) else 1)
