"""Pair-wise sim S1↔S3 — Hall sensor V_OUT during S1 battery inrush.

During battery-connect, S1 inrush is 9.86 A peak (per PR #32 sim). Hall sensor
primary leads carry this current and translate to V_OUT via 10 mV/A sensitivity.

Verify V_OUT stays within ACS770 output envelope [0.5, 4.5] V and within
FC-ADC range [0, 3.3] V after the 10K/20K divider.
"""
import numpy as np

V_CC = 5.0
SENS = 0.010
V_OFFSET = V_CC / 2.0

I_inrush_peak_A = 9.86      # from PR #32 inrush sim
I_continuous_A = 70.0       # board nominal continuous bus current
I_burst_A = 100.0           # 10s burst (matches Phase 2-burst-resize)

DIVIDER_GAIN = 20.0 / 30.0  # 10K + 20K → 0.667

print("Pair-wise S1↔S3 — Hall sensor V_OUT envelope during S1 inrush + flight modes")
print(f"  ACS770ECB-200B sensitivity: {SENS*1000} mV/A, V_OUT = {V_OFFSET}V + I·sens (ratiometric V_CC=5V)")
print(f"  Output envelope: [0.5, 4.5] V (datasheet)")
print(f"  Post-divider FC_ADC envelope: [0, 3.3] V")
print()

scenarios = [
    ("S1 inrush peak (9.86 A)",  I_inrush_peak_A),
    ("Cruise hover (40 A)",       40.0),
    ("Continuous nominal (70 A)", I_continuous_A),
    ("Burst peak (100 A)",        I_burst_A),
    ("Regen (worst-case -50 A)", -50.0),
]

for label, I in scenarios:
    v_out = V_OFFSET + I * SENS
    v_fc = v_out * DIVIDER_GAIN
    in_acs_env  = 0.5 <= v_out  <= 4.5
    in_fc_env   = 0.0 <= v_fc   <= 3.3
    verdict = "PASS ✓" if (in_acs_env and in_fc_env) else "FAIL ✗"
    print(f"  {label:30s}: V_OUT={v_out:5.3f} V, V_FC_ADC={v_fc:5.3f} V → {verdict}")
print()
print("VERDICT: S1 inrush + all flight modes produce Hall V_OUT well within both")
print("envelopes. No saturation, no clipping, no overflow into ADC overrange.")
