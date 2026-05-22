"""Sim 3 — BEMF sense voltage range (analytical for 6S motor commutation).

For sensorless BLDC FOC, BEMF zero-crossing detection uses motor phase voltage
divider sent to MCU ADC. Voltage scaling per typical AM32 BEMF divider:
- Motor phase voltage at commutation: ranges 0V to V_VMOTOR (25.2V at 6S)
- Divider top: typically 22K (high impedance for low loss)
- Divider bot: typically 22K (1:2 ratio → max 12.6V at ADC pin)
- Wait that's too high for 3.3V ADC.

AM32 standard divider per channel_skidl.py: 22K top + 22K bot? Let me check.
"""
import numpy as np

V_VMOTOR_NOMINAL = 25.2  # 6S full
V_MAX_OPERATING = 30.0   # OVP envelope
V_ADC_REF = 3.3          # MCU ADC ref

# Per channel_skidl.py: R_bemf 22K + 3.3K → ratio 3.3/(22+3.3) = 0.13
# V_OUT_ADC = V_BEMF × 0.13
RATIO = 3.3 / (22.0 + 3.3)

print("Sim 3 — BEMF sense voltage range (analytical)")
print(f"  Divider: R22 22K (top) / R60 3.3K (bot) = {1/RATIO:.2f}:1 ratio")
print(f"  Scaling: V_ADC = V_BEMF × {RATIO:.4f}")
print()

scenarios = [
    ("Motor stalled (0V BEMF)", 0.0),
    ("Cruise (8V BEMF)",         8.0),
    ("Nominal (15V BEMF)",      15.0),
    ("Burst (V_VMOTOR=25.2V)", V_VMOTOR_NOMINAL),
    ("OVP envelope (30V)",     V_MAX_OPERATING),
]
print(f"  {'Scenario':30s}  V_BEMF  V_ADC   Verdict")
all_pass = True
for label, v_bemf in scenarios:
    v_adc = v_bemf * RATIO
    in_range = 0 <= v_adc <= V_ADC_REF
    if not in_range:
        all_pass = False
    verdict = "PASS ✓" if in_range else "FAIL ✗ (ADC clamp)"
    print(f"  {label:30s}  {v_bemf:5.1f}V  {v_adc:5.3f}V  {verdict}")

print()
print(f"  Spec: V_ADC stays within [0, {V_ADC_REF}] V")
print(f"  Verdict: {'PASS ✓' if all_pass else 'FAIL ✗'}")
print()
# Theoretical max BEMF: V_BUS (no protection diode loss)
v_max_seen = V_MAX_OPERATING * RATIO
print(f"  Worst-case V_ADC at OVP envelope 30V: {v_max_seen:.3f} V")
print(f"  Headroom under 3.3V ADC: {V_ADC_REF - v_max_seen:.3f} V")
