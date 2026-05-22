"""Phase 4c-resume — analytical thermal model with Option C parameters.

Sai's 2026-05-22 adjudication: Option C (TOLL phase MOSFETs + bigger rectangular
board). Engineering rigor over target relaxation; 70 A continuous spec stays.

Locked changes vs Phase 4c analytical_with_heatsink.py:
  Phase MOSFET: AOTL66912 TOLL-8L (100V over-spec; 1.4mΩ typ; R_thJC=0.2 °C/W)
  Board: 85 × 70 mm rectangular (sized via re-run of Phase 2.5 area budget)
  Heatsink: ~80 × 55 mm Al6061-T6 4mm (covers 24× TOLL 6×4 grid + 2 mm border)
  fin_multiplier: 10× (practical for FPV at this larger board size)

All other envelope parameters unchanged (h=80 floor preserved per master Rigor §2).
"""

import math

# ─────────── AOTL66912 datasheet (AOS Rev 1.0 June 2019, Phase 2b URGENT #1 capture) ───────────
# 100V N-Channel TOLL-8L. Datasheet typical values @ V_GS=10V:
R_dson_25_typ  = 1.4e-3        # Ω typ @ T_J=25°C (max 1.7 mΩ)
R_dson_125_typ = 2.25e-3       # Ω typ @ T_J=125°C (max 2.75 mΩ)
R_thJC_typ     = 0.2           # °C/W typ (max 0.3) — 5× better than AON6260's 1.0!

def r_dson_at(T_J_C):
    if T_J_C <= 125.0:
        return R_dson_25_typ + (R_dson_125_typ - R_dson_25_typ) * (T_J_C - 25.0) / 100.0
    R_sat = 2.0 * R_dson_25_typ
    R_125 = R_dson_125_typ
    tau = (175.0 - 125.0) / 3.0
    return R_sat - (R_sat - R_125) * math.exp(-(T_J_C - 125.0) / tau)


# ─────────── Heatsink geometry (Phase 4c-resume locked) ───────────
HS_W = 80e-3              # 80 mm wide (covers 6× TOLL × 11.5 mm pitch + 2 mm border)
HS_H = 55e-3              # 55 mm tall (covers 4× TOLL × 12.5 mm pitch + 2 mm border)
HS_THICKNESS = 4e-3
k_Al = 170.0

HS_SLAB_AREA = HS_W * HS_H                                  # 0.0044 m² = 44 cm²
A_HS_SLAB = (HS_W * HS_H) + 2 * (HS_W + HS_H) * HS_THICKNESS  # top + 4 edges

# ─────────── TIM (silicone 0.5mm @ 4 W/m·K, conservative) ───────────
TIM_THICKNESS = 0.5e-3
k_TIM = 4.0
A_TIM = HS_SLAB_AREA

R_thTIM = TIM_THICKNESS / (k_TIM * A_TIM)

# ─────────── R_thJC parallel for 24 MOSFETs ───────────
N_PHASE_FETS = 24
R_thJC_parallel = R_thJC_typ / N_PHASE_FETS

R_thHS_cond = HS_THICKNESS / (k_Al * HS_SLAB_AREA)


def R_thHS_conv(h_air, fin_multiplier=10.0):
    A_eff = A_HS_SLAB * fin_multiplier
    return 1.0 / (h_air * A_eff)


def P_per_MOSFET(I_channel, T_J_C):
    return (I_channel ** 2) * r_dson_at(T_J_C) * (1.0 / 3.0)


def solve_envelope(I_per_ch, h_air, fin_multiplier, T_amb_C, T_J_target,
                   use_heatsink=True):
    T_J = T_amb_C + 30.0
    if use_heatsink:
        R_th_total = R_thJC_parallel + R_thTIM + R_thHS_cond + R_thHS_conv(h_air, fin_multiplier)
    else:
        # Without HS: board surface convection. New board 85×70.
        A_board = (85e-3 * 70e-3) * 2 + 2 * (85e-3 + 70e-3) * 1.6e-3
        R_th_total = R_thJC_parallel + 1.0 / (h_air * A_board)

    for _ in range(500):
        P_per_fet = P_per_MOSFET(I_per_ch, T_J)
        P_total = N_PHASE_FETS * P_per_fet
        T_J_new = T_amb_C + P_total * R_th_total
        if abs(T_J_new - T_J) < 0.01:
            break
        T_J = T_J_new

    if T_J > 1e4:
        verdict = f"NON-PHYSICAL ({T_J:.0f} °C)"
    elif T_J <= T_J_target:
        verdict = f"PASS  (T_J={T_J:.1f} °C ≤ {T_J_target} °C; margin {T_J_target - T_J:.1f} °C)"
    elif T_J <= 150.0:
        verdict = f"FAIL target ({T_J:.1f} °C > {T_J_target} °C; survives < 150 °C)"
    else:
        verdict = f"FAIL abs-max ({T_J:.1f} °C > 150 °C)"
    return T_J, P_total, R_th_total, verdict


print("=" * 78)
print("Phase 4c-resume — analytical with Option C parameters")
print("=" * 78)
print(f"  Part            : AOTL66912 TOLL-8L (100V over-spec, 1.4mΩ typ)")
print(f"  Board form factor: 85 × 70 mm rectangular")
print(f"  Heatsink slab   : {HS_W*1000:.0f} × {HS_H*1000:.0f} mm Al6061-T6, {HS_THICKNESS*1000:.0f} mm thick")
print(f"  Heatsink fin mult: 10× (practical for 85×70 board)")
print(f"  TIM             : 0.5 mm silicone @ 4 W/m·K (conservative)")
print()
print(f"  R_thJC parallel (24×): {R_thJC_parallel:.5f} °C/W (vs Phase 4c DFN5x6's 0.0417)")
print(f"  R_thTIM             : {R_thTIM:.4f} °C/W (improved vs Phase 4c due to larger HS area)")
print(f"  R_thHS_cond         : {R_thHS_cond:.4f} °C/W")
print()

# Envelope 2 — the critical gate
T_J, P, R_th, v = solve_envelope(70.0, 80.0, 10.0, 60.0, 100.0, use_heatsink=True)
print(f"--- Envelope 2 (CRITICAL GATE) ---")
print(f"  Conditions: 70 A cont/ch + h=80 W/m²·K + heatsink fin_mult=10×")
print(f"  R_th_total = {R_th:.4f} °C/W")
print(f"  Total board P = {P:.1f} W")
print(f"  T_J predicted = {T_J:.1f} °C")
print(f"  Verdict      : {v}")
print()

# Envelope 1 — cruise (still-air, no HS active)
T_J1, P1, R_th1, v1 = solve_envelope(40.0, 12.0, 1.0, 60.0, 100.0, use_heatsink=False)
print(f"--- Envelope 1 (cruise still-air, no HS) ---")
print(f"  Conditions: 40 A avg/ch + still-air h=12 + 60°C amb, no heatsink (cruise reality)")
print(f"  R_th_total = {R_th1:.4f} °C/W")
print(f"  Total board P = {P1:.1f} W")
print(f"  T_J predicted = {T_J1:.1f} °C")
print(f"  Verdict      : {v1}")
print()

# Envelope 1 alternative — cruise WITH heatsink engaged (more realistic)
T_J1b, P1b, R_th1b, v1b = solve_envelope(40.0, 12.0, 10.0, 60.0, 100.0, use_heatsink=True)
print(f"--- Envelope 1 alt (cruise + heatsink natural-convection active) ---")
print(f"  Conditions: 40 A avg/ch + heatsink fin_mult=10 + still-air h=12 + 60°C amb")
print(f"  R_th_total = {R_th1b:.4f} °C/W")
print(f"  Total board P = {P1b:.1f} W")
print(f"  T_J predicted = {T_J1b:.1f} °C")
print(f"  Verdict      : {v1b}")
print()

# Envelope 3 — stress (70A cont still-air, no HS active)
T_J3, P3, R_th3, v3 = solve_envelope(70.0, 12.0, 1.0, 60.0, 150.0, use_heatsink=False)
print(f"--- Envelope 3 (stress / abs-max survival, still-air) ---")
print(f"  Conditions: 70 A cont/ch + still-air h=12 + 60°C amb, no HS (stress test)")
print(f"  T_J predicted = {T_J3:.1f} °C")
print(f"  Verdict      : {v3}")
