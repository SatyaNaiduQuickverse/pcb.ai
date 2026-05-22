"""Pair-wise sim S5↔S1 — BEC switching noise injected back to +VMOTOR/+BATT.

5 bucks switching at 500-600 kHz draw pulsed current from +VMOTOR. Input
ripple = I_OUT × D pk-pk pulled from V_IN per buck.

Total input ripple seen at +VMOTOR pre-bulk-cap depends on phase between
bucks (worst case: all in-phase = 5 × ripple addition).

S2 bulk caps absorb most ripple (470µF × 4 polymer caps). Residual ripple
back to BATT through R_NTC isolates +BATT from V_VMOTOR ripple.

Acceptance per master: induced V_BATT ripple ≤ 50 mV pk-pk.
"""
import math

V_IN = 25.0
loads = [
    # name, V_OUT, I_OUT, f_sw, IC
    ("V5_FC",   5.0, 5.0, 600e3, "TPS54560"),
    ("V5_PI5",  5.0, 5.0, 600e3, "TPS54560"),
    ("V5_AI",   5.0, 3.0, 600e3, "TPS54560"),
    ("V9_VTX1", 9.0, 2.0, 500e3, "AOZ1284"),
    ("V9_VTX2", 9.0, 2.0, 500e3, "AOZ1284"),
]

# Input current pulses per buck — pk = I_OUT × (V_OUT/V_IN)·during ON,
# spikes ~ 2 × DC average during MOSFET switch.
# Approximate input ripple current per buck (typical 30% of DC input)
print("Pair-wise S5↔S1 — BEC switching noise → V_BATT")
print(f"  V_IN: {V_IN} V")
print()

total_input_ripple_A = 0.0
print(f"  {'Rail':10s}  D       I_in_dc(A)  I_in_rip(A)  f_sw")
for name, vo, io, fsw, ic in loads:
    D = vo / V_IN
    p_out = vo * io
    eta = 0.88 if vo == 5.0 else 0.89  # rough
    p_in = p_out / eta
    i_in_dc = p_in / V_IN
    # Input ripple: ~30% of DC (typical buck input rms)
    i_in_rip = i_in_dc * 0.30
    total_input_ripple_A += i_in_rip
    print(f"  {name:10s}  {D:.3f}  {i_in_dc:5.3f}      {i_in_rip:5.3f}        {fsw/1e3:.0f} kHz")

print()
print(f"  Total input ripple (worst-case in-phase sum): {total_input_ripple_A:.3f} A pk-pk")
print()

# S2 bulk cap impedance at ~600 kHz (worst-case buck freq)
# 4× 470µF polymer caps in parallel, ESR ~10 mΩ each → ESR_total ~2.5 mΩ
# Z_C at 600 kHz: 1/(2π × 600e3 × 4 × 470e-6) = 0.14 mΩ (dominated by ESR)
F_SW_WORST = 600e3
C_BULK_uF = 4 * 470
ESR_BULK_OHM = 0.0025  # 4× parallel
Z_BULK = math.sqrt(ESR_BULK_OHM**2 + (1.0 / (2 * math.pi * F_SW_WORST * C_BULK_uF * 1e-6))**2)
v_ripple_on_vmotor = total_input_ripple_A * Z_BULK
v_ripple_on_vmotor_mv = v_ripple_on_vmotor * 1000

print(f"  S2 bulk caps Z @ {F_SW_WORST/1e3:.0f} kHz: {Z_BULK*1e3:.3f} mΩ (ESR-dominated)")
print(f"  Ripple at V_VMOTOR (bulk cap node): {v_ripple_on_vmotor_mv:.2f} mV pk-pk")
print()

# Isolation to BATT through NTC R=5Ω + battery R_int=30mΩ
R_NTC = 5.0
R_BATT = 0.030
isolation = R_BATT / (R_NTC + R_BATT)
v_ripple_on_batt_mv = v_ripple_on_vmotor_mv * isolation

print(f"  Isolation BATT← V_VMOTOR via R_NTC ({R_NTC} Ω) + R_batt ({R_BATT*1000:.0f} mΩ):")
print(f"    Ratio: {isolation:.6f}")
print(f"    V_BATT ripple: {v_ripple_on_batt_mv:.4f} mV pk-pk")
print()

SPEC_MV = 50.0
verdict = "PASS ✓" if v_ripple_on_batt_mv <= SPEC_MV else "FAIL ✗"
print(f"  Spec: ≤ {SPEC_MV} mV pk-pk at V_BATT")
print(f"  Verdict: {verdict} (margin {SPEC_MV/max(v_ripple_on_batt_mv, 1e-3):.0f}×)")
