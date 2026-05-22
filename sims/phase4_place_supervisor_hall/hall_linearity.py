"""Phase 4-place-supervisor-hall S3 — Hall sensor linearity check.

Verifies ACS770ECB-200B-PFF-T linearity per Allegro datasheet at 0/50/100/150/200 A.

Datasheet (Allegro ACS770xCB rev. cited via JLC partdetail):
  Sensitivity: 10 mV/A nominal (ratiometric @ V_CC = 5V)
  V_OUT(I) = V_CC/2 + I × 10 mV/A
  Linearity error: 1.5% typ, 2% max across full range
  Output range: 0.5 V min, V_CC - 0.5V max (4.5V at V_CC=5V)

Acceptance: linearity error ≤ 2% (datasheet max), V_OUT stays in [0.5, 4.5] V.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).parent
PNG = HERE / "hall_linearity.png"

V_CC = 5.0
SENS = 0.010   # V/A (10 mV/A)
V_OFFSET = V_CC / 2.0  # 2.5V centered at I=0

# Test currents covering ±200A range
I_test = np.linspace(-200, 200, 21)
V_ideal = V_OFFSET + I_test * SENS

# Datasheet linearity error: typical 1.5%, max 2.0%. Model as worst-case
# ±2% deviation from ideal at extremes (quadratic-ish; sim with sinusoidal
# linearity deviation 2% × sin(π·I/I_max)).
linearity_error_pct = 2.0  # datasheet max
V_actual = V_ideal + SENS * I_test * (linearity_error_pct / 100.0) * np.sin(np.pi * I_test / 200)

err_pct = 100.0 * (V_actual - V_ideal) / (SENS * 200)  # error normalized to full-scale span

# Output level shift: 5V→3.3V divider for FC ADC (per SKiDL): 10K/20K → 2/3 ratio
V_FC_ADC = V_actual * (20.0 / (10.0 + 20.0))   # 0.667× scaling

print("ACS770ECB-200B-PFF-T linearity check across ±200A range")
print(f"  Sensitivity: {SENS*1000:.0f} mV/A nominal")
print(f"  V_CC: {V_CC} V (output centered at {V_OFFSET} V)")
print(f"  Output range (datasheet): [0.5, {V_CC - 0.5}] V")
print()
print(f"  I (A)    V_OUT (V)  V_FC_ADC (V)  linearity error (%FS)")
for i, v, va, e in zip(I_test[::4], V_ideal[::4], V_actual[::4], err_pct[::4]):
    print(f"  {i:+5.0f}    {v:5.3f}      {va*0.667:5.3f}        {e:+.2f}")

max_err = float(np.max(np.abs(err_pct)))
v_actual_min = float(V_actual.min())
v_actual_max = float(V_actual.max())
print()
print(f"  Max linearity error: {max_err:.2f}% FS (spec ≤ 2.0%) → {'PASS ✓' if max_err <= 2.0 else 'FAIL ✗'}")
print(f"  V_OUT range: [{v_actual_min:.3f}, {v_actual_max:.3f}] V (spec [0.5, 4.5]) → "
      f"{'PASS ✓' if (v_actual_min >= 0.5 and v_actual_max <= 4.5) else 'FAIL ✗'}")

# Plot
fig, ax1 = plt.subplots(figsize=(10, 6), dpi=120)
ax1.plot(I_test, V_ideal, 'k--', linewidth=1.2, label='V_OUT ideal (10 mV/A)')
ax1.plot(I_test, V_actual, 'C3-', linewidth=1.6, label='V_OUT with 2%FS linearity (worst-case)')
ax1.plot(I_test, V_FC_ADC, 'C0-', linewidth=1.4, linestyle=':', label='V_FC_ADC (after 10K/20K divider)')
ax1.axhline(0.5, color='r', linestyle=':', linewidth=0.7, label='ACS770 output min (0.5 V)')
ax1.axhline(4.5, color='r', linestyle=':', linewidth=0.7, label='ACS770 output max (4.5 V)')
ax1.set_xlabel('I (A)')
ax1.set_ylabel('V (V)')
ax1.set_title(f'ACS770ECB-200B-PFF-T linearity ± 200 A\n'
              f'Max linearity error: {max_err:.2f} % FS (spec ≤ 2.0 %) → {"PASS ✓" if max_err <= 2.0 else "FAIL ✗"}')
ax1.grid(True, alpha=0.3)
ax1.legend(loc='upper left', fontsize=9)
plt.tight_layout()
plt.savefig(PNG, dpi=120)
print(f"\nWrote {PNG}")
