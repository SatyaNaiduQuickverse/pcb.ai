"""Sim 4 — Current sense shunt + INA186 chain (analytical from datasheet).

Per channel: 0.2 mΩ shunt + INA186 (gain typ 50 V/V).
Phase current range: -100 A regen → +100 A burst.

V_shunt = I × 0.2 mΩ → -20 mV to +20 mV across shunt.
V_INA_out = V_shunt × Gain + V_ref (typ V_CC/2 = 2.5V for bidirectional sensing).

INA186 datasheet anchors:
  - Output range: 0V to V_CC (3V3 or 5V supply)
  - Common-mode range: -V_CC to V_CC
  - Output saturation: ≥80 mV above V_NEG, ≤V_POS - 80 mV
  - Gain accuracy: ±0.5%

Acceptance per master: V_INA_out within 0-3.3V across ±100A range.
"""
SHUNT_OHM = 0.2e-3
GAIN_INA = 50.0
V_REF = 1.65   # V_CC/2 = 3.3/2 (bidirectional centering)
V_CC_INA = 3.3
V_SAT_MIN = 0.08
V_SAT_MAX = V_CC_INA - V_SAT_MIN

print("Sim 4 — Current sense chain (0.2 mΩ shunt + INA186 50 V/V)")
print(f"  Shunt: {SHUNT_OHM*1000:.1f} mΩ")
print(f"  INA186 gain: {GAIN_INA} V/V")
print(f"  V_REF (bidirectional center): {V_REF} V")
print(f"  ADC envelope: [0, {V_CC_INA}] V")
print(f"  INA186 output saturation: [{V_SAT_MIN}, {V_SAT_MAX}] V")
print()

scenarios = [
    ("Regen -100 A",  -100.0),
    ("Regen -50 A",   -50.0),
    ("Idle 0 A",      0.0),
    ("Cruise 40 A",   40.0),
    ("Continuous 70 A", 70.0),
    ("Burst 100 A",   100.0),
]
print(f"  {'Scenario':20s}  V_shunt  V_INA_out  Verdict")
all_pass = True
for label, I in scenarios:
    v_shunt = I * SHUNT_OHM
    v_ina = V_REF + v_shunt * GAIN_INA
    in_range = V_SAT_MIN <= v_ina <= V_SAT_MAX
    if not in_range:
        all_pass = False
    verdict = "PASS ✓" if in_range else "FAIL ✗ (saturated)"
    print(f"  {label:20s}  {v_shunt*1000:+6.2f}mV  {v_ina:5.3f}V    {verdict}")

print()
print(f"  Verdict: {'PASS ✓' if all_pass else 'FAIL ✗'}")
print()
# Resolution
i_per_lsb = (V_CC_INA / 4096) / (SHUNT_OHM * GAIN_INA)
print(f"  ADC resolution (12-bit, 3.3V): {3.3/4096*1000:.3f} mV/LSB")
print(f"  Current resolution: {i_per_lsb:.3f} A/LSB")
