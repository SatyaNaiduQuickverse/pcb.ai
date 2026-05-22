"""Pair-wise sim S2↔S6 — S2 bulk-cap ripple → S6 BAT_V FC ADC reading.

S2 V_VMOTOR ripple: 65 mV pk-pk @ 30 kHz (per PR #34 sim).
But VBAT divider connects to BATT net (pre-S2 cap), NOT V_VMOTOR.

Path: BATT terminal → R1/R2 NTC → S2 caps (V_VMOTOR). The R_NTC = 5Ω
isolates BATT from V_VMOTOR ripple. Ripple seen at BATT terminal is much
smaller: ratio = R_batt_int / (R_batt_int + R_NTC) ≈ 30mΩ/5Ω = 0.006.
So 65 mV V_VMOTOR ripple → ~0.4 mV at BATT terminal.

Then divider ratio 0.1228 → 0.4 × 0.1228 = 0.05 mV at V_SENSE.
C49 100nF filter further attenuates 30 kHz / 130 Hz = 231× → 0.0002 mV.

Effectively zero ripple seen at FC ADC.

Acceptance: BAT_V ripple ≤ 10 mV at FC ADC input.
"""
import numpy as np

V_VMOTOR_RIPPLE_PKPK = 0.065   # 65 mV @ 30 kHz (S2 sim)
R_NTC = 5.0     # MF72 5D25 cold resistance
R_BATT_INT = 0.030    # 30 mΩ battery internal R (6S LiPo typ)
RATIO = 14e3 / (100e3 + 14e3)  # divider
F_RIPPLE = 30e3
F_CUT = 130.0   # C49 filter cutoff

# Ripple at BATT terminal (after NTC isolation)
ripple_at_batt = V_VMOTOR_RIPPLE_PKPK * R_BATT_INT / (R_BATT_INT + R_NTC)

# Ripple at V_SENSE (pre-filter)
ripple_vsense_raw = ripple_at_batt * RATIO

# Post-filter ripple — 1st-order RC attenuation at 30 kHz
attenuation = F_CUT / F_RIPPLE  # for f >> f_cut: gain = f_cut / f
ripple_vsense_filt = ripple_vsense_raw * attenuation

print("Pair-wise S2↔S6 — S2 bulk-cap ripple → BAT_V FC ADC")
print(f"  S2 V_VMOTOR ripple: {V_VMOTOR_RIPPLE_PKPK*1000:.0f} mV pk-pk @ {F_RIPPLE/1e3:.0f} kHz")
print(f"  R_NTC: {R_NTC} Ω | R_BATT_INT: {R_BATT_INT*1000:.0f} mΩ")
print()
print(f"  Ripple at BATT terminal (post-NTC isolation):")
print(f"    = {V_VMOTOR_RIPPLE_PKPK*1000} mV × ({R_BATT_INT}/({R_BATT_INT}+{R_NTC}))")
print(f"    = {ripple_at_batt*1e6:.1f} µV pk-pk")
print()
print(f"  Ripple at V_SENSE (× divider ratio {RATIO:.4f}):")
print(f"    = {ripple_vsense_raw*1e6:.2f} µV pk-pk")
print()
print(f"  Post-C49 filter (130 Hz cutoff, 30 kHz ripple attenuation):")
print(f"    Gain at 30 kHz = {F_CUT}/{F_RIPPLE/1e3:.0f}k = {attenuation:.6f}")
print(f"    Ripple at FC ADC = {ripple_vsense_filt*1e6:.3f} µV pk-pk")
print()
acceptance_mV = 10.0
ripple_mV = ripple_vsense_filt * 1000
print(f"  Spec: ≤ {acceptance_mV} mV pk-pk at FC ADC")
verdict = "PASS ✓" if ripple_mV <= acceptance_mV else "FAIL ✗"
print(f"  Verdict: {verdict} (margin: {acceptance_mV/max(ripple_mV, 1e-9):.0f}×)")
print()
print("  Two-stage isolation (R_NTC + C49 filter) effectively zeroes V_VMOTOR")
print("  ripple at FC ADC. PWM frequency well-rejected by design.")
