"""Phase 2b — three-envelope thermal analysis for AON6260 on a 30×30 mm 4-in-1.

Per master's 2026-05-22 adjudication on URGENT #3 (P1+P3+P5 approved):
  Envelope 1 — Cruise: 40 A avg/ch + still-air + 60 °C amb → T_J ≤ 100 °C
  Envelope 2 — Peak/sustained throttle: 70 A cont/ch + prop-wash (h≥80) + heatsink → T_J ≤ 100 °C
  Envelope 3 — Stress/abs-max: 70 A cont/ch + still-air → T_J ≤ T_J_max=150 °C survival

This script computes T_J for each envelope using the lumped board-level model
(Path B from analytical.py — full physics). Output: pass/fail per envelope.
"""

import math

# ---- AON6260 datasheet (Rev 1.1 Sep 2023) ----
R_dson_25_typ  = 1.95e-3        # @ Vgs=10V
R_dson_125_typ = 3.15e-3
R_thJC_typ     = 1.0            # °C/W

def r_dson_at(T_J_C):
    """Saturating R_DS(on)(T_J) — linear 25→125°C, exponential saturation
       toward 2.0×R25 at high T_J per datasheet Figure 4."""
    if T_J_C <= 125.0:
        return R_dson_25_typ + (R_dson_125_typ - R_dson_25_typ) * (T_J_C - 25.0) / 100.0
    R_sat = 2.0 * R_dson_25_typ
    R_125 = R_dson_125_typ
    tau = (175.0 - 125.0) / 3.0
    return R_sat - (R_sat - R_125) * math.exp(-(T_J_C - 125.0) / tau)


# ---- Board + thermal-path geometry ----
A_board_one_side = (30e-3) ** 2     # 9 cm² per side
A_edges          = 4 * 30e-3 * 1.6e-3
A_board_conv     = 2 * A_board_one_side + A_edges
N_total          = 24                # 4 ch × 3 ph × 2 (high+low)

# Per-MOSFET R from junction to board copper plane
# R_thJC + solder + lateral-spread + FR-4 vertical to inner plane
R_thJC   = R_thJC_typ
R_thSOL  = 0.10
A_eff_FR4 = 1.5 * (10e-3) ** 2
R_thFR4   = 0.1e-3 / (0.3 * A_eff_FR4)
R_thJB    = R_thJC + R_thSOL + R_thFR4    # ≈ 3.3 °C/W


def envelope(name, I_continuous, h_conv, duty_per_mosfet, T_amb_C, T_J_target,
             heatsink_factor=1.0):
    """Solve self-consistent T_J for one envelope.
       heatsink_factor: multiplier on convection area (heatsink adds fin surface).
       Returns (T_J, P_total, verdict_str).
    """
    A_total = A_board_conv * heatsink_factor
    R_BA    = 1.0 / (h_conv * A_total)
    T_J     = T_amb_C + 30.0
    for _ in range(500):
        P_one   = I_continuous ** 2 * r_dson_at(T_J) * duty_per_mosfet
        P_total = N_total * P_one
        T_board = T_amb_C + P_total * R_BA
        T_J_new = T_board + P_one * R_thJB
        if abs(T_J_new - T_J) < 0.01:
            break
        T_J = T_J_new
    if T_J > 1000:
        verdict = f"NON-PHYSICAL (T_J={T_J:.0f} °C) — board cannot dissipate {P_total:.0f} W in this envelope"
    elif T_J <= T_J_target:
        verdict = f"PASS by {T_J_target - T_J:.1f} °C"
    elif T_J <= 150:
        verdict = f"FAIL target by {T_J - T_J_target:.1f} °C (still under T_J_max=150 °C)"
    else:
        verdict = f"FAIL target AND exceeds T_J_max=150 °C"
    return T_J, T_board, P_one, P_total, R_BA, verdict


# Duty cycle in 3-phase BLDC: each MOSFET is active 1/3 of electrical period.
DUTY = 1.0 / 3.0
T_amb = 60.0

print("=" * 78)
print("Phase 2b three-envelope thermal verdict — AON6260 on a 30×30 mm 4-in-1 board")
print("=" * 78)
print(f"  R_thJB (junction → inner plane) = {R_thJB:.2f} °C/W per W of one MOSFET")
print(f"  Board convection area (no HS)    = {A_board_conv*1e4:.1f} cm² (2 sides + 4 edges)")
print()

# Envelope 1: Cruise
print("-" * 78)
print("Envelope 1 — Cruise: 40 A avg/ch + still-air + 60 °C amb")
print(f"  Target: T_J ≤ 100 °C")
T_J, T_b, P_o, P_t, R_BA, v = envelope("E1", 40.0, 12.0, DUTY, T_amb, 100.0)
print(f"  h_conv = 12 W/m²·K (natural+radiative); heatsink_factor = 1.0")
print(f"  R_thBA_global = {R_BA:.1f} °C/W per W of TOTAL board diss")
print(f"  R_DS(on) @ T_J = {r_dson_at(T_J)*1000:.2f} mΩ")
print(f"  P/MOSFET = {P_o:.2f} W ; Total board P = {P_t:.1f} W")
print(f"  T_board = {T_b:.1f} °C ; T_J = {T_J:.1f} °C")
print(f"  VERDICT: {v}")
print()

# Envelope 2: Peak / sustained throttle (prop-wash + heatsink)
print("-" * 78)
print("Envelope 2 — Peak/sustained throttle: 70 A cont/ch + prop-wash + heatsink")
print(f"  Target: T_J ≤ 100 °C")
T_J, T_b, P_o, P_t, R_BA, v = envelope("E2", 70.0, 80.0, DUTY, T_amb, 100.0,
                                       heatsink_factor=2.5)
print(f"  h_conv = 80 W/m²·K (prop-wash forced); heatsink_factor = 2.5 (modest fin area)")
print(f"  R_thBA_global = {R_BA:.1f} °C/W per W of TOTAL board diss")
print(f"  R_DS(on) @ T_J = {r_dson_at(T_J)*1000:.2f} mΩ")
print(f"  P/MOSFET = {P_o:.2f} W ; Total board P = {P_t:.1f} W")
print(f"  T_board = {T_b:.1f} °C ; T_J = {T_J:.1f} °C")
print(f"  VERDICT: {v}")
print()

# Envelope 3: Stress / abs-max (70A cont still-air; survival not steady-op)
print("-" * 78)
print("Envelope 3 — Stress/abs-max: 70 A cont/ch + still-air (survival only)")
print(f"  Target: T_J ≤ T_J_max=150 °C (survives, not steady operation)")
T_J, T_b, P_o, P_t, R_BA, v = envelope("E3", 70.0, 12.0, DUTY, T_amb, 150.0)
print(f"  h_conv = 12 W/m²·K (no airflow, no heatsink); heatsink_factor = 1.0")
print(f"  R_thBA_global = {R_BA:.1f} °C/W per W of TOTAL board diss")
print(f"  R_DS(on) @ T_J = {r_dson_at(T_J)*1000:.2f} mΩ (saturated)")
print(f"  P/MOSFET = {P_o:.2f} W ; Total board P = {P_t:.1f} W")
print(f"  T_board = {T_b:.1f} °C ; T_J = {T_J:.1f} °C")
print(f"  VERDICT: {v}")
print()

print("=" * 78)
print("Notes:")
print("  - Envelope 3 verdict is INFORMATIONAL: still-air at 70 A cont. is not a steady-state")
print("    operating envelope, it's a thermal stress test. The board would heat up rapidly")
print("    and either trigger over-temp protection or fault before reaching steady state.")
print("    Real-world FPV ESCs handle this by: (a) being in prop-wash whenever the motor")
print("    is at high throttle; (b) firmware over-temp protection cutting demand.")
print("  - Envelope 2 is the rated continuous spec. Pass here = product viable.")
print("  - Envelope 1 is the typical-race continuous condition. Pass here = comfortable margin.")
