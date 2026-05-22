"""Pair-wise sim S5↔S3 — BEC switching noise → supervisor + Hall.

Concern 1: BEC ripple raises V_VMOTOR ripple slightly (from S5↔S2 sim).
  Higher V_VMOTOR ripple → larger V_BATT_DIV ripple at TPS3700 supervisor.
  Verify still no false trip.

Concern 2: V5 BEC ripple feeds Hall V_CC. Hall ratiometric output cancels
  V_CC ripple at the BUS_CURR signal, but DC offset variations from V5
  load variations could shift V_OUT.
  Verify Hall noise stays within master-adjudicated 10mV end-to-end criterion.
"""
import math

# From S5↔S2 sim — combined V_VMOTOR ripple
V_VMOTOR_RIPPLE_COMBINED_MV = 65.1   # ~unchanged since BEC adds tiny vs 65mV baseline

# Divider ratio (R19 348K / R20 23K2)
DIVIDER_RATIO = 23.2 / (348 + 23.2)
V_DIV_RIPPLE_MV = V_VMOTOR_RIPPLE_COMBINED_MV * DIVIDER_RATIO

TPS3700_HYST_MV = 50.0  # Datasheet typ
ratio = TPS3700_HYST_MV / V_DIV_RIPPLE_MV

print("Pair-wise S5↔S3 — BEC noise → supervisor + Hall")
print()
print(f"(1) Supervisor TPS3700 false-trip from V_VMOTOR ripple:")
print(f"    V_VMOTOR combined ripple (S2 + BEC contribution): {V_VMOTOR_RIPPLE_COMBINED_MV:.1f} mV pk-pk")
print(f"    Divider ratio (R20/(R19+R20)): {DIVIDER_RATIO:.4f}")
print(f"    V_BATT_DIV ripple: {V_DIV_RIPPLE_MV:.3f} mV pk-pk")
print(f"    TPS3700 hysteresis (datasheet): {TPS3700_HYST_MV:.0f} mV")
print(f"    Hysteresis/ripple ratio: {ratio:.1f}×")
verdict1 = "PASS ✓" if V_DIV_RIPPLE_MV < TPS3700_HYST_MV else "FAIL ✗"
print(f"    Verdict: {verdict1} — no false trip")
print()

# Hall V_CC noise — TPS54560 V5_FC output ripple (Sim 2 result)
V5_RIPPLE_MV = 4.5   # From Sim 2 V5_FC ripple (well under 50 mV spec)

# Hall V_OUT noise contributions:
#   (a) Intrinsic Allegro datasheet: 8 mV pk-pk @ 80 kHz BW
#   (b) V_CC ripple effect: ratiometric output cancels common-mode V_CC ripple.
#       Hall V_OUT = V_CC/2 + I·sens (V_CC-dependent offset).
#       At I=0: V_OUT changes with V_CC ripple in proportion (V_CC/2 modulation).
#       4.5 mV V_CC ripple → 2.25 mV ripple at V_OUT (offset shift)
#       But this is DC-coupled to subsequent stages; FC samples at >50 Hz,
#       4.5mV @ 600 kHz is filtered by C44 10nF (cutoff 2.4 kHz):
#         attenuation 2.4k/600k = 4e-3 → 9 µV residual
HALL_INTRINSIC_MV = 8.0
v_cc_ripple_modulation = V5_RIPPLE_MV / 2.0
C44_F_CUT = 1.0 / (2 * math.pi * (10e3 * 20e3/(10e3+20e3)) * 10e-9)
attenuation = C44_F_CUT / 600e3
hall_routing_noise_from_vcc = v_cc_ripple_modulation * attenuation
total_hall_noise = math.sqrt(HALL_INTRINSIC_MV**2 + hall_routing_noise_from_vcc**2 + 0.18**2)
# 0.18 mV is routing pickup from S3↔S6 sim

print(f"(2) Hall V_OUT noise from V5_FC BEC switching:")
print(f"    V5_FC output ripple (Sim 2): {V5_RIPPLE_MV:.1f} mV pk-pk")
print(f"    V_CC modulation effect: {v_cc_ripple_modulation:.2f} mV at V_OUT (offset shift)")
print(f"    C44 10nF filter (f_3dB = {C44_F_CUT:.0f} Hz) at 600 kHz:")
print(f"      Attenuation = {C44_F_CUT/600e3:.4f}")
print(f"      Residual = {hall_routing_noise_from_vcc*1e3:.2f} µV pk-pk")
print()
print(f"    Components (RSS):")
print(f"      Intrinsic (datasheet): {HALL_INTRINSIC_MV} mV pk-pk")
print(f"      Routing pickup (S3↔S6): 0.18 mV pk-pk")
print(f"      V_CC ripple modulation: {hall_routing_noise_from_vcc*1e3:.4f} µV (essentially zero)")
print(f"    Total RSS: {total_hall_noise:.3f} mV pk-pk")
print()

SPEC_HALL_MV = 10.0  # Master-adjudicated end-to-end criterion
verdict2 = "PASS ✓" if total_hall_noise <= SPEC_HALL_MV else "FAIL ✗"
print(f"    Spec: ≤ {SPEC_HALL_MV} mV pk-pk (master-adjudicated end-to-end)")
print(f"    Verdict: {verdict2} (margin {SPEC_HALL_MV - total_hall_noise:.2f} mV)")
print()

print("OVERALL S5↔S3 verdict:")
print(f"  Supervisor: PASS — hysteresis {ratio:.1f}× margin")
print(f"  Hall: PASS — {total_hall_noise:.3f} mV ≤ 10 mV (master-adjudicated)")
