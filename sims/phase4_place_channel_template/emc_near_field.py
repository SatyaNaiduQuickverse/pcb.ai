"""Sim 5 — EMC near-field analytical estimate at PWM 30-60 kHz + harmonics.

Full openEMS FDTD sim deferred to autoroute (mesh requires routed traces).
Analytical near-field model: motor PWM loop area × dI/dt → magnetic field at MCU.

Loop geometry (R6 architecture):
  Motor pad at outer edge (x=5)
  Lo-FET source at x=30
  Loop area ≈ pad-to-source × ½ stackup = 25 mm × 0.8 mm = 20 mm²

dI/dt at PWM edge: I_phase / t_rise ≈ 70 A / 30 ns = 2.3 × 10⁹ A/s
H-field at MCU distance d=10mm: H = I·loop_area / (4π·d³)
"""
import math

I_PHASE = 70.0
T_RISE = 30e-9     # AOTL66912 + DRV8300 typical
LOOP_AREA_MM2 = 20
DIST_MM = 10
F_PWM = 50e3       # 30-60 kHz typical AM32 PWM

# Approximate H-field from current loop at distance d (m), area A (m²), current I (A)
A_m2 = LOOP_AREA_MM2 * 1e-6
d_m = DIST_MM * 1e-3

H_field = I_PHASE * A_m2 / (4 * math.pi * d_m**3)
B_field = 4 * math.pi * 1e-7 * H_field   # μ0·H in Tesla
E_field_estimate = B_field * 3e8  # crude E ≈ c·B for radiation regime

print("Sim 5 — EMC near-field analytical estimate")
print(f"  Loop area: {LOOP_AREA_MM2} mm² (motor pad → lo-FET source)")
print(f"  Phase current: {I_PHASE} A")
print(f"  PWM edge rise time: {T_RISE*1e9:.0f} ns")
print(f"  PWM frequency: {F_PWM/1e3:.0f} kHz (30-60 kHz AM32 range)")
print(f"  Observation distance: {DIST_MM} mm (MCU to closest FET)")
print()
print(f"  H-field at MCU: {H_field:.2f} A/m")
print(f"  B-field: {B_field*1e6:.2f} µT")
print(f"  E-field estimate: {E_field_estimate:.2f} V/m")
print()

# Acceptance — informal benchmark vs typical FCC/CISPR class B radiated emissions
# at 30 cm: ~40-50 dBμV/m (= 100-300 µV/m) in 30-1000 MHz range.
# Near-field at 10mm is much higher but rolls off as 1/d³ → at 30cm:
B_30cm = I_PHASE * A_m2 / (4 * math.pi * (0.3)**3) * 4 * math.pi * 1e-7
E_30cm = B_30cm * 3e8
print(f"  Extrapolated at 30 cm (far-field reference): E ≈ {E_30cm*1e6:.2f} µV/m")
print(f"  vs CISPR class B limit at 30-230 MHz: 40 dBµV/m = 100 µV/m")

verdict = "PASS ✓" if E_30cm * 1e6 < 100 else "FAIL ✗ (needs shielding/pour)"
print(f"  Verdict (analytical): {verdict}")
print()
print("  Note: full openEMS FDTD sim at autoroute will verify with actual")
print("  traces. Solid GND pour on In1 + In5 (8L stackup) provides image-current")
print("  return path that significantly reduces effective loop area.")
