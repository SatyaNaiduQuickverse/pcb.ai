"""BAT_V divider accuracy sim — FC battery voltage sensing.

Divider: R36 (100K ±1%) / R37 (14K ±1%) = 8.143:1 ratio
Filter: C49 (100nF) on V_SENSE node — 8.143 / 2π·100k·100nF cutoff = ~16 Hz

Acceptance per master spec:
  ADC accuracy ±5% across 18-30V V_BATT range

Datasheet anchors:
  - FC ADC ref: 3.3V (typical Betaflight/iNAV ADC reference)
  - Resistor tolerance: ±1% (E96 series typical)
  - V_BATT operating range: 18V (LVC) to 30V (6S full + headroom)
"""
import numpy as np

R_TOP_NOM = 100e3  # 100K
R_BOT_NOM = 14e3   # 14K
TOL = 0.01         # ±1%

V_BATT_LVC = 18.0  # LiPo low-voltage cutoff
V_BATT_FULL = 25.2  # 6S × 4.2V
V_BATT_MAX = 30.0  # headroom

def divider(v_batt, r_top, r_bot):
    return v_batt * r_bot / (r_top + r_bot)

print("BAT_V divider accuracy sim — R36/R37 = 100K/14K (8.143:1)")
print(f"  Nominal ratio: {R_BOT_NOM/(R_TOP_NOM+R_BOT_NOM):.6f}")
print(f"  V_BATT range: {V_BATT_LVC} V (LVC) to {V_BATT_MAX} V (max)")
print(f"  Expected V_SENSE at V_BATT=25.2 V: {divider(V_BATT_FULL, R_TOP_NOM, R_BOT_NOM):.4f} V")
print()

# Worst-case corner: R_TOP high + R_BOT low → V_SENSE biased low
# Best-case: R_TOP low + R_BOT high → V_SENSE biased high
corners = [
    ("nominal",         R_TOP_NOM,           R_BOT_NOM),
    ("R_top hi + R_bot lo", R_TOP_NOM*(1+TOL), R_BOT_NOM*(1-TOL)),
    ("R_top lo + R_bot hi", R_TOP_NOM*(1-TOL), R_BOT_NOM*(1+TOL)),
]

print(f"  {'corner':25s}  V_BATT (V)  V_SENSE (V)  ratio    err (%)")
max_err_pct = 0.0
for label, rt, rb in corners:
    for v in (V_BATT_LVC, V_BATT_FULL, V_BATT_MAX):
        vs = divider(v, rt, rb)
        ratio = (rt + rb) / rb
        # error vs nominal V_SENSE at same V_BATT
        vs_nom = divider(v, R_TOP_NOM, R_BOT_NOM)
        err_pct = 100.0 * (vs - vs_nom) / vs_nom
        if abs(err_pct) > max_err_pct:
            max_err_pct = abs(err_pct)
        print(f"  {label:25s}  {v:6.2f}     {vs:6.4f}     {ratio:7.4f}  {err_pct:+.3f}")

print()
ACCEPTANCE_PCT = 5.0
print(f"  Worst-case corner error: {max_err_pct:.3f} % (spec ±{ACCEPTANCE_PCT}%)")
verdict = "PASS ✓" if max_err_pct <= ACCEPTANCE_PCT else "FAIL ✗"
print(f"  Verdict: {verdict}")
print()

# FC firmware can also account for measured resistor values via calibration —
# so even ±1% tolerance error is typically eliminated by per-board offset cal.
print("  Note: FC firmware (Betaflight/iNAV) typically supports per-board V_BATT")
print("  calibration multiplier, eliminating most of the ±1% systematic error.")
print()

# Filter cutoff
import math
F_CUT = 1.0 / (2 * math.pi * R_TOP_NOM * R_BOT_NOM / (R_TOP_NOM + R_BOT_NOM) * 100e-9)
R_PARALLEL = R_TOP_NOM * R_BOT_NOM / (R_TOP_NOM + R_BOT_NOM)
print(f"  Filter cutoff: f_3dB = 1 / (2π·R_par·C_filt)")
print(f"    R_parallel = {R_PARALLEL/1000:.2f} kΩ")
print(f"    C_filt = 100 nF")
print(f"    f_3dB = {F_CUT:.1f} Hz")
print(f"  Rejects: PWM ripple (30 kHz S2 ripple → {30000/F_CUT:.0f}× attenuated below cutoff)")
