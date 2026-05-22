"""Phase 4c — analytical thermal model with heatsink + TIM nodes.

Refines Phase 2b's envelopes.py by adding the actual heatsink geometry
(Phase 2.5 + 4a locked: ~46 × 32 mm Al6061-T6, 3-5 mm thick) + TIM
(silicone gap-filler, 0.5 mm @ 4 W/m·K conservative).

Computes T_J for the 3 envelopes (per REQUIREMENTS.md §fpv-4in1 → MOSFETs
Phase 2b adjudication on URGENT #3):
  E1 Cruise:    40 A avg/ch + still-air (h=12 W/m²·K) + 60 °C amb → ≤ 100 °C
  E2 Peak:      70 A cont/ch + prop-wash (h=80 W/m²·K conservative) + heatsink → ≤ 100 °C
  E3 Stress:    70 A cont/ch + still-air → ≤ T_J_max=150 °C survival
"""

import math

# ─────────── AON6260 datasheet (Phase 2b — Rev 1.1 Sep 2023) ───────────
R_dson_25_typ  = 1.95e-3          # Ω @ V_GS=10V
R_dson_125_typ = 3.15e-3
R_thJC_typ     = 1.0              # °C/W, per MOSFET

def r_dson_at(T_J_C):
    """Saturating R_DS(on)(T_J) per datasheet Figure 4."""
    if T_J_C <= 125.0:
        return R_dson_25_typ + (R_dson_125_typ - R_dson_25_typ) * (T_J_C - 25.0) / 100.0
    R_sat = 2.0 * R_dson_25_typ
    R_125 = R_dson_125_typ
    tau = (175.0 - 125.0) / 3.0
    return R_sat - (R_sat - R_125) * math.exp(-(T_J_C - 125.0) / tau)


# ─────────── Heatsink geometry (Phase 2.5 + 4a locked) ───────────
HS_W = 46e-3             # 46 mm wide
HS_H = 32e-3             # 32 mm tall
HS_THICKNESS = 4e-3      # 4 mm Al6061-T6 (mid-range of 3-5 mm spec)
k_Al = 170.0             # W/m·K (Al6061-T6)
HS_SLAB_AREA = HS_W * HS_H                          # 0.001472 m² = 14.72 cm²

# Heatsink surface convection area:
#   - Top + 4 edges of a flat slab: A_slab = top + edges
#     A_top = 1472 mm², A_edges = 2 × (46+32) × 4 = 1248 mm² → A_slab_total = ~2720 mm²
# For a FINNED heatsink, the surface area is multiplied by the fin-area-multiplier
# (worker-pickable; conservative 5×, more realistic for FPV-class finned 8-10×).
A_HS_SLAB = (HS_W * HS_H) + 2 * (HS_W + HS_H) * HS_THICKNESS    # ~0.00272 m²

# ─────────── TIM (silicone thermal pad) ───────────
TIM_THICKNESS = 0.5e-3
k_TIM = 4.0              # W/m·K — conservative end of silicone gap-filler (4–6 W/m·K range)
A_TIM = HS_SLAB_AREA     # full heatsink-to-PCB-drain-plane contact

R_thTIM = TIM_THICKNESS / (k_TIM * A_TIM)
# = 0.5e-3 / (4 × 0.001472) = 0.0849 °C/W

# ─────────── R_thJC parallel for 24 MOSFETs sharing the heatsink ───────────
# Each MOSFET R_thJC = 1.0 °C/W (datasheet typ). For N MOSFETs in parallel
# thermally to the same heatsink, equivalent R_thJC_parallel = R/N = 0.042 °C/W.
N_PHASE_FETS = 24
R_thJC_parallel = R_thJC_typ / N_PHASE_FETS


# ─────────── Heatsink-conduction resistance (negligible for thin slab) ───────────
# Through the thickness: R = thickness / (k × A) = 4e-3 / (170 × 0.001472) ≈ 0.016 °C/W. Small.
R_thHS_cond = HS_THICKNESS / (k_Al * HS_SLAB_AREA)

# ─────────── Convection from heatsink to air ───────────
def R_thHS_conv(h_air, fin_multiplier=5.0):
    """h_air in W/m²·K; fin_multiplier = 1 for flat slab, 5–10 for moderate fins."""
    A_eff = A_HS_SLAB * fin_multiplier
    return 1.0 / (h_air * A_eff)


# ─────────── Per-MOSFET P_loss (3-phase BLDC duty-cycle averaged) ───────────
def P_per_MOSFET(I_channel, T_J_C):
    """At any instant, 2 of 6 MOSFETs per channel conduct; each MOSFET conducts ~1/3
    of an electrical cycle. Time-averaged per-MOSFET P = I² × R_DS(on)(T_J) × (1/3).
    """
    return (I_channel ** 2) * r_dson_at(T_J_C) * (1.0 / 3.0)


# ─────────── Envelope solver ───────────
def solve_envelope(name, I_per_ch, h_air, fin_multiplier, T_amb_C, T_J_target,
                   use_heatsink=True):
    """Solves for T_J at the hottest MOSFET via self-consistent iteration on
    R_DS(on)(T_J). All 24 MOSFETs share the heatsink → parallel R_thJC.
    """
    T_J = T_amb_C + 30.0   # initial guess
    if use_heatsink:
        R_th_total = R_thJC_parallel + R_thTIM + R_thHS_cond + R_thHS_conv(h_air, fin_multiplier)
    else:
        # Without heatsink: just board surface convection from full 50×50 area
        # (Phase 2b Path B simplification — total board dissipation hits whole board area)
        A_board = (50e-3) ** 2 * 2 + 4 * 50e-3 * 1.6e-3    # both sides + edges
        R_th_total = R_thJC_parallel + 1.0 / (h_air * A_board)

    for _ in range(500):
        P_per_fet = P_per_MOSFET(I_per_ch, T_J)
        P_total = N_PHASE_FETS * P_per_fet
        T_J_new = T_amb_C + P_total * R_th_total
        if abs(T_J_new - T_J) < 0.01:
            break
        T_J = T_J_new

    if T_J > 1e4:
        verdict = f"NON-PHYSICAL ({T_J:.0f} °C — design infeasible at this op point)"
    elif T_J <= T_J_target:
        verdict = f"PASS  (T_J={T_J:.1f} °C ≤ {T_J_target} °C; margin {T_J_target - T_J:.1f} °C)"
    elif T_J <= 150.0:
        verdict = f"FAIL target ({T_J:.1f} °C > {T_J_target} °C; survives < 150 °C abs-max)"
    else:
        verdict = f"FAIL abs-max ({T_J:.1f} °C > 150 °C — part destruct)"
    return T_J, P_total, R_th_total, verdict


def report(name, T_J, P_total, R_th, verdict):
    print(f"\n--- {name} ---")
    print(f"  R_DS(on) at T_J converged : {r_dson_at(T_J)*1000:.2f} mΩ")
    print(f"  Total board P             : {P_total:.1f} W")
    print(f"  R_th_total (J → ambient)  : {R_th:.4f} °C/W")
    print(f"  Predicted T_J             : {T_J:.1f} °C")
    print(f"  Verdict                   : {verdict}")


print("=" * 78)
print("Phase 4c — analytical thermal envelopes (AON6260 24× + heatsink)")
print("=" * 78)
print(f"  R_thJC parallel (24 MOSFETs) : {R_thJC_parallel:.4f} °C/W")
print(f"  R_thTIM (0.5 mm silicone)    : {R_thTIM:.4f} °C/W")
print(f"  R_thHS_cond (4 mm Al6061)    : {R_thHS_cond:.4f} °C/W (negligible)")
print(f"  Heatsink slab area           : {HS_SLAB_AREA*1e4:.2f} cm² ({HS_W*1000:.0f}×{HS_H*1000:.0f} mm)")


# ─────────── Envelope 1: Cruise (40A avg, still-air, no HS active) ───────────
# Still-air means no heatsink active (FPV at low/cruise doesn't engage HS as much).
# Use the without-heatsink path (board-area convection).
T_J, P, R_th, v = solve_envelope("E1 Cruise", 40.0, 12.0, 1.0, 60.0, 100.0, use_heatsink=False)
report("Envelope 1 — Cruise (40 A avg/ch + still-air + 60 °C amb)", T_J, P, R_th, v)


# ─────────── Envelope 2: Peak / sustained throttle (70A cont, prop-wash, +HS) ───────────
# h_air = 80 W/m²·K (master's conservative pick); explore fin_multiplier sensitivities.
for fin_mult in [5, 8, 10, 12, 15]:
    T_J, P, R_th, v = solve_envelope(f"E2 Peak (fin_mult={fin_mult}×)",
                                     70.0, 80.0, fin_mult, 60.0, 100.0,
                                     use_heatsink=True)
    report(f"Envelope 2 — Peak (70 A cont + h=80 + HS area {HS_SLAB_AREA*fin_mult*1e4:.1f} cm²)",
           T_J, P, R_th, v)


# ─────────── Envelope 3: Stress (70A cont, still-air, NO HS active) ───────────
T_J, P, R_th, v = solve_envelope("E3 Stress", 70.0, 12.0, 1.0, 60.0, 150.0, use_heatsink=False)
report("Envelope 3 — Stress (70 A cont/ch + still-air; abs-max survival)", T_J, P, R_th, v)


print()
print("=" * 78)
print("Sensitivity: improved TIM (graphite-sheet at 25 W/m·K, 0.5 mm)")
print("=" * 78)
# Recompute R_thTIM with graphite sheet
R_thTIM_graphite = TIM_THICKNESS / (25.0 * A_TIM)
print(f"  R_thTIM (graphite 25 W/m·K)  : {R_thTIM_graphite:.4f} °C/W "
      f"(vs silicone {R_thTIM:.4f}; gain {R_thTIM - R_thTIM_graphite:.4f} °C/W)")
print(f"  TIM is NOT the bottleneck — gain is small vs R_thHS_conv contribution.")
