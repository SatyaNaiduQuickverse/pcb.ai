"""Sim 2 — Per-rail output ripple (analytical from datasheet).

For a non-synchronous buck:
  I_L_pkpk = V_IN × D × (1-D) / (f_sw × L)
  V_ripple_pkpk ≈ I_L_pkpk × ESR_cap + I_L_pkpk / (8 × f_sw × C_OUT)

Datasheet anchors:
  TPS54560 f_sw = 600 kHz, AOZ1284 f_sw = 500 kHz
  C_OUT = 22 µF MLCC (X7R), ESR at switching freq: ~2-5 mΩ
  V_IN nominal = 25 V (6S charged); D = V_OUT/V_IN

Acceptance per master spec: ≤ 50 mV pk-pk per rail at full load.
"""
import numpy as np

V_IN = 25.0  # 6S nominal
ESR_CAP_OHM = 0.003   # 3 mΩ typical for 22µF X7R MLCC @ 500-600 kHz

rails = [
    # rail, V_out, I_max, L (uH), C_out (uF), f_sw (kHz), IC
    ("V5_FC",   5.0, 5.0, 4.7,  22.0, 600, "TPS54560"),
    ("V5_PI5",  5.0, 5.0, 4.7,  22.0, 600, "TPS54560"),
    ("V5_AI",   5.0, 3.0, 8.2,  22.0, 600, "TPS54560"),
    ("V9_VTX1", 9.0, 2.0, 10.0, 22.0, 500, "AOZ1284PI"),
    ("V9_VTX2", 9.0, 2.0, 10.0, 22.0, 500, "AOZ1284PI"),
]

print("Sim 2 — Per-rail output ripple (analytical)")
print(f"  V_IN nominal: {V_IN} V")
print(f"  C_OUT ESR: {ESR_CAP_OHM*1000:.1f} mΩ (X7R MLCC @ switching freq)")
print()
print(f"  {'Rail':10s}  V_out  D     I_L_pp(A)  V_rip_pp(mV)  Verdict")
SPEC_MV = 50.0
all_pass = True
for rail, vo, i_max, L_uh, C_uf, fsw_khz, ic in rails:
    D = vo / V_IN
    fsw = fsw_khz * 1e3
    L = L_uh * 1e-6
    C = C_uf * 1e-6
    I_pkpk = V_IN * D * (1 - D) / (fsw * L)
    v_ripple_esr = I_pkpk * ESR_CAP_OHM
    v_ripple_C = I_pkpk / (8 * fsw * C)
    v_ripple_total = v_ripple_esr + v_ripple_C
    v_ripple_mv = v_ripple_total * 1000
    passes = v_ripple_mv <= SPEC_MV
    if not passes:
        all_pass = False
    verdict = "PASS ✓" if passes else "FAIL ✗"
    print(f"  {rail:10s}  {vo:4.1f}V  {D:.3f} {I_pkpk:6.2f}    {v_ripple_mv:6.2f}     {verdict}")

print()
print(f"  Spec: ≤ {SPEC_MV} mV pk-pk per rail at full load")
print()
print(f"  OVERALL: {'PASS ✓' if all_pass else 'FAIL ✗'}")
