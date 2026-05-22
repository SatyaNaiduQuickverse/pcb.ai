"""Sim 1 — Per-FET thermal (lumped 1D from AOTL66912 datasheet).

NOTE: Full 3D Elmer FEM would model the 8L stackup with 3oz copper pour heat
spreading + per-FET thermal coupling. Lumped 1D analytical model below provides
upper-bound T_J for sanity check; finer Elmer sim deferred to autoroute phase.

AOTL66912 datasheet:
  V_DS = 100 V, R_DS(on) typ = 1.6 mΩ at V_GS=10V, T_J=25°C
  R_DS(on) max = 2.0 mΩ at T_J=125°C
  Theta_JA = 50 °C/W (datasheet, FR4 1oz copper)
  Theta_JC = 0.6 °C/W (junction to case, thermal pad)
  T_J_max abs: 175 °C
  T_J operating: ≤ 100 °C (Sai-locked reliability margin)

Per-phase loss: I² × R_DS(on) × duty_high + I² × R_DS(on) × duty_low + sw losses
For 3-phase BLDC at PWM duty 50%:
  P_loss per FET ≈ 0.5 × I² × R_DS(on) per phase, 6 FETs per channel
  At I=70A continuous: P_per_FET = 0.5 × 70² × 2e-3 = 4.9 W
  At I=100A burst (10s): P_per_FET = 10 W

With 8L stackup (3oz on F.Cu/B.Cu, internal planes), effective Theta_JA improves
to ~25-30 °C/W per master Phase 4a-restack-8L analysis.

Acceptance per master: T_J ≤ 100 °C continuous, ≤ 175 °C burst abs.
"""
import math

R_DS_HOT = 2.0e-3    # mΩ at T_J=125°C
DUTY = 0.5
THETA_JA_8L = 27.5   # °C/W with 8L 3oz copper (per Phase 4a-restack)
T_AMB = 65.0         # °C drone enclosure ambient

scenarios = [
    ("Cruise hover 40 A continuous", 40.0, "continuous"),
    ("Nominal 70 A continuous",      70.0, "continuous"),
    ("Burst 100 A (10s)",           100.0, "burst"),
]

print("Sim 1 — Per-FET thermal (analytical lumped 1D)")
print(f"  R_DS(on) @ T_J=125°C: {R_DS_HOT*1000:.1f} mΩ")
print(f"  PWM duty: {DUTY}")
print(f"  Theta_JA (8L 3oz stackup): {THETA_JA_8L} °C/W")
print(f"  T_ambient (enclosure): {T_AMB} °C")
print()
print(f"  {'Scenario':33s}  I (A)  P_FET (W)  T_J (°C)  spec  Verdict")
all_pass = True
for label, I, mode in scenarios:
    P_per_fet = DUTY * I**2 * R_DS_HOT
    T_J = T_AMB + P_per_fet * THETA_JA_8L
    spec = 100.0 if mode == "continuous" else 175.0
    verdict = "PASS ✓" if T_J <= spec else "FAIL ✗"
    if T_J > spec:
        all_pass = False
    print(f"  {label:33s}  {I:5.1f}  {P_per_fet:5.2f}      {T_J:5.1f}    ≤{spec:.0f}°C  {verdict}")

print()
print(f"  Verdict: {'PASS ✓' if all_pass else 'FAIL ✗'}")
print()
print("  Note: 100A burst T_J modeled steady-state with Theta_JA. Actual 10s")
print("  burst sees transient Theta(t) heating; if T_J > 175°C steady, the 10s")
print("  burst duration must include Cthermal·τ_thermal correction for short")
print("  pulse. Master full Elmer FEM at autoroute will verify.")
