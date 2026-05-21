"""Phase 2b — analytical 1-D thermal benchmark for AON6260 at 70 A continuous.

Rigor §4 requires sim validation against an analytical benchmark BEFORE the
sim's verdict on the actual board is trusted. This script computes the lumped-
parameter T_J prediction; the Elmer FEM sim on the same scenario must agree to
within ~10% before its full-board verdict is trusted.

Application envelope (master's Phase 2b contract + 2026-05-22 adjudication
P1 + updated criterion 4):
  - I = 70 A continuous through one CHANNEL (motor RMS); per-MOSFET time-averaged
    is I² × duty_cycle (≈ 1/3 in a 3-phase BLDC with one high+one low conducting
    1/3 of the electrical period each).
  - T_amb = 60 °C (FPV hot-day envelope, conservative).
  - Still-air natural convection (initial sizing; prop-wash adds margin not
    claimed yet).
  - 10 mm × 10 mm outer-layer copper pour at each MOSFET drain.
  - JLC 6-layer stack-up: 1-oz outer / 0.5-oz inner / FR-4 1.6 mm total.
  - Board: representative 4-in-1 ≈ 30 × 30 mm = 9 cm² per side.

Datasheet inputs (AON6260 Rev 1.1, Sep 2023):
  R_DS(on) @ V_GS=10V, T_J=25°C : typ 1.95 mΩ, max 2.40 mΩ   (p.2 STATIC table)
  R_DS(on) @ V_GS=10V, T_J=125°C: typ 3.15 mΩ, max 3.90 mΩ   (p.2 STATIC table)
  R_thJC steady-state           : typ 1.0 °C/W, max 1.2 °C/W (p.1 Thermal)
  R_thJA on 1in² FR-4 + 2oz Cu  : typ 40 °C/W, max 55 °C/W   (p.1 Thermal)
  T_J max                       : 150 °C                      (p.1 Abs Max)
  Figure 4 normalized R_DS(on) saturates at ~2.0× the 25°C value near 175°C
  (NOT linear — saturating curve).

This script computes T_J via two paths:
  PATH A — lumped R_thJA (datasheet's 1in² FR-4 still-air rating, the most
           grounded number; serves as the sim-validation reference).
  PATH B — board-level model with N_active MOSFETs + heat spreading + convection
           from the full board area. More mechanistic; the Elmer sim should
           track PATH B.

If PATH A and PATH B agree within ~20%, both are credible. If they diverge by
much, the more conservative is the design floor.
"""

import math

# ---------- inputs ----------
I_continuous = 70.0           # A, per CHANNEL (motor RMS); per-MOSFET is duty-modulated
T_amb_C      = 60.0           # °C
# MOSFET conduction duty: 3-phase BLDC, each MOSFET conducts ~1/3 of electrical cycle
# (one high + one low per channel are on at any instant; six MOSFETs share equally).
duty_per_mosfet = 1.0 / 3.0
# Number of MOSFETs simultaneously conducting across the board: 8 (4 channels × 2 active)
N_active_simultaneous = 8
N_total = 24                  # 4 channels × 3 phases × 2 MOSFETs

# Datasheet specs (typ values; max values used in a separate run below)
R_dson_25_typ  = 1.95e-3      # Ω
R_dson_125_typ = 3.15e-3      # Ω
R_thJC_typ     = 1.0          # °C/W
R_thJA_1in2    = 40.0         # °C/W typ, on 1in² FR-4 2oz Cu still-air

def r_dson_at(T_J_C, T25=R_dson_25_typ, T125=R_dson_125_typ):
    """Saturating R_DS(on) curve from datasheet Fig 4 (typ).
       Linear from 25→125°C, then saturating toward ~2.0× the 25°C value at 175°C.
    """
    if T_J_C <= 125.0:
        return T25 + (T125 - T25) * (T_J_C - 25.0) / (125.0 - 25.0)
    # Above 125°C: saturating exponential toward 2.0×T25 at 175°C
    R_sat = 2.0 * T25
    R_125 = T125
    # Saturation with time-constant such that R(175)=R_sat - 5% of (R_sat-R_125)
    tau = (175.0 - 125.0) / 3.0
    return R_sat - (R_sat - R_125) * math.exp(-(T_J_C - 125.0) / tau)


# ============================================================
# PATH A — datasheet R_thJA (1in² 2oz Cu, still-air)
# ============================================================
# Treats one MOSFET on a 1 in² (~6.45 cm²) island of 2-oz copper, still air.
# Datasheet typ 40 °C/W. Self-heating iteration with duty cycle.
# P_loss(time-avg per MOSFET) = I² × R_DS(on)(T_J) × duty_per_mosfet
def path_a():
    T_J = T_amb_C + 30.0
    for _ in range(200):
        P = (I_continuous ** 2) * r_dson_at(T_J) * duty_per_mosfet
        T_J_new = T_amb_C + P * R_thJA_1in2
        if abs(T_J_new - T_J) < 0.01:
            break
        T_J = T_J_new
    return T_J, P

# ============================================================
# PATH B — board-level model with 24 MOSFETs + full-board convection
# ============================================================
# Heat sources: all 24 MOSFETs dissipating P_avg (time-averaged).
# Heat path:
#   junction → drain pad → solder → outer cu pour → through FR-4 dielectric (~0.1 mm)
#   → inner plane → spreads across whole board → convection from both sides + edges.
def path_b():
    # Convection parameters
    h_nat = 12.0                    # W/m²·K, natural conv (incl ~3 W/m²·K of radiative augmentation)
    A_board_one_side = (30e-3) ** 2 # 9 cm²
    A_edges = 4 * 30e-3 * 1.6e-3    # 4 edges × board height
    A_total_conv = 2 * A_board_one_side + A_edges
    R_thBA_global = 1.0 / (h_nat * A_total_conv)

    # Per-MOSFET R from junction to board (cu plane):
    R_thJC   = R_thJC_typ           # 1.0 °C/W
    R_thSOL  = 0.10                 # solder + drain pad (thin layer, low R)
    # Vertical conduction through 0.1 mm FR-4 to inner plane, with copper-pour lateral
    # spreading. The 10×10 mm pour spreads heat laterally before vertical conduction;
    # effective A is enlarged by spreading. Use a 1.5× spreading factor (conservative):
    A_eff_FR4 = 1.5 * (10e-3) ** 2
    R_thFR4   = 0.1e-3 / (0.3 * A_eff_FR4)   # k_FR4 = 0.3 W/m·K, t=0.1 mm
    R_thJB    = R_thJC + R_thSOL + R_thFR4

    # All 24 MOSFETs dissipate at duty-cycle-averaged power.
    T_J = T_amb_C + 30.0
    for _ in range(200):
        P_one = (I_continuous ** 2) * r_dson_at(T_J) * duty_per_mosfet
        P_total = N_total * P_one
        T_board = T_amb_C + P_total * R_thBA_global
        T_J_new = T_board + P_one * R_thJB
        if abs(T_J_new - T_J) < 0.01:
            break
        T_J = T_J_new
    return T_J, T_board, P_one, P_total, R_thBA_global, R_thJB


# ============================================================
# Report
# ============================================================
T_J_a, P_a = path_a()
T_J_b, T_b, P_b, P_t, R_BA, R_JB = path_b()

print("=" * 72)
print("Phase 2b analytical thermal benchmark — AON6260 at 70 A per channel cont.")
print("=" * 72)
print(f"  Worst-case still-air, T_amb = {T_amb_C} °C, FR-4 6-layer.")
print(f"  Duty cycle per MOSFET (3-phase BLDC) = 1/3 of electrical period.")
print()

print("PATH A — datasheet R_thJA (1in² FR-4 2oz Cu still-air, typ 40 °C/W)")
print(f"  R_DS(on) @ converged T_J = {r_dson_at(T_J_a)*1000:.2f} mΩ")
print(f"  P_loss per MOSFET (time-avg, duty-modulated) = {P_a:.2f} W")
print(f"  T_J (predicted)           = {T_J_a:.1f} °C")
print()

print("PATH B — board-level (24 MOSFETs + full-board still-air convection)")
print(f"  R_thBA_global (board → amb)        = {R_BA:.1f} °C/W per W of TOTAL board diss")
print(f"  R_thJB (junction → board copper)   = {R_JB:.2f} °C/W per W of THIS MOSFET diss")
print(f"  R_DS(on) @ converged T_J = {r_dson_at(T_J_b)*1000:.2f} mΩ")
print(f"  P_loss per MOSFET (time-avg)       = {P_b:.2f} W")
print(f"  Total board dissipation            = {P_t:.1f} W")
print(f"  T_board (bulk above amb)           = {T_b:.1f} °C")
print(f"  T_J (predicted)                    = {T_J_b:.1f} °C")
print()

# ============================================================
# Verdict vs new criterion 4
# ============================================================
T_J_target = 100.0
T_J_max    = 150.0
print("=" * 72)
print(f"Verdict vs new criterion 4: T_J ≤ {T_J_target} °C (Phase 2b master adjud. 2026-05-22)")
print("=" * 72)
for label, T_J in [("PATH A", T_J_a), ("PATH B", T_J_b)]:
    if T_J <= T_J_target:
        print(f"  {label}: T_J = {T_J:.1f} °C → PASS (margin {T_J_target - T_J:.1f} °C)")
    elif T_J <= T_J_max:
        print(f"  {label}: T_J = {T_J:.1f} °C → FAIL target by "
              f"{T_J - T_J_target:.1f} °C, but under T_J_max={T_J_max} °C")
    else:
        print(f"  {label}: T_J = {T_J:.1f} °C → CRITICAL — exceeds T_J_max")
print()

# ============================================================
# Sensitivity — with prop-wash assumption (forced convection)
# ============================================================
# Prop-wash forced convection: h_forced ≈ 60-100 W/m²·K typical for FPV motors
# at moderate throttle. Re-run PATH B with h=60 to show the design margin
# available with prop-wash claimed.
def path_b_propwash(h_force=60.0):
    A_board_one_side = (30e-3) ** 2
    A_edges = 4 * 30e-3 * 1.6e-3
    A_total_conv = 2 * A_board_one_side + A_edges
    R_BA = 1.0 / (h_force * A_total_conv)
    R_thJC = R_thJC_typ
    R_thSOL = 0.10
    A_eff_FR4 = 1.5 * (10e-3) ** 2
    R_thFR4 = 0.1e-3 / (0.3 * A_eff_FR4)
    R_JB = R_thJC + R_thSOL + R_thFR4
    T_J = T_amb_C + 30.0
    for _ in range(200):
        P_one = (I_continuous ** 2) * r_dson_at(T_J) * duty_per_mosfet
        P_total = N_total * P_one
        T_board = T_amb_C + P_total * R_BA
        T_J_new = T_board + P_one * R_JB
        if abs(T_J_new - T_J) < 0.01:
            break
        T_J = T_J_new
    return T_J, R_BA

print("Sensitivity — with prop-wash forced convection (h = 60 W/m²·K)")
T_J_pw, R_BA_pw = path_b_propwash(60.0)
print(f"  R_thBA_global (forced conv) = {R_BA_pw:.1f} °C/W per W of TOTAL board diss")
print(f"  T_J (predicted)              = {T_J_pw:.1f} °C  "
      f"→ {'PASS' if T_J_pw <= T_J_target else 'still over target'}")
print()
print("Notes on the still-air result:")
print(f"  Path A and Path B both show T_J >> {T_J_target} °C under the still-air worst case.")
print( "  This is consistent with the known FPV thermal reality: 4-channel continuous")
print( "  at 70 A is fundamentally a forced-convection (prop-wash) operating regime.")
print( "  The Elmer FEM is expected to reproduce Path B to within ~20% (with its")
print( "  better lateral-conduction model possibly giving a slightly lower T_J).")
