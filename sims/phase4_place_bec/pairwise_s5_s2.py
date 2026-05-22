"""Pair-wise sim S5↔S2 — BEC ripple absorbed by S2 bulk caps.

5 bucks each draw pulsed input current. S2 bulk caps (4× 470µF polymer)
absorb input ripple, presenting low impedance at switching frequencies.

Verify: bulk caps don't see ripple > 100 mV pk-pk from BEC switching.
"""
import math

V_IN = 25.0
loads = [
    ("V5_FC",   5.0, 5.0, 600e3),
    ("V5_PI5",  5.0, 5.0, 600e3),
    ("V5_AI",   5.0, 3.0, 600e3),
    ("V9_VTX1", 9.0, 2.0, 500e3),
    ("V9_VTX2", 9.0, 2.0, 500e3),
]

print("Pair-wise S5↔S2 — BEC ripple absorbed by S2 bulk caps")
print()

# Sum input ripple current (worst-case in-phase) — same as S5↔S1
total_i_rip_A = 0
for name, vo, io, fsw in loads:
    eta = 0.88 if vo == 5.0 else 0.89
    p_in = (vo * io) / eta
    i_in_dc = p_in / V_IN
    i_in_rip = i_in_dc * 0.30
    total_i_rip_A += i_in_rip

# S2 cap impedance @ 600 kHz (worst-case freq)
F_TEST = 600e3
N_CAPS = 4
C_EACH_F = 470e-6
ESR_EACH_OHM = 0.010   # 10 mΩ typical for polymer
ESR_TOTAL = ESR_EACH_OHM / N_CAPS
C_TOTAL = N_CAPS * C_EACH_F
Z_C = 1.0 / (2 * math.pi * F_TEST * C_TOTAL)
Z_TOTAL = math.sqrt(ESR_TOTAL**2 + Z_C**2)

v_ripple_on_cap = total_i_rip_A * Z_TOTAL
v_ripple_on_cap_mv = v_ripple_on_cap * 1000

# Plus existing S2 self-ripple (65mV pk-pk from PR #34 sim) — RSS combination
S2_SELF_RIPPLE_MV = 65.0
v_ripple_total_mv = math.sqrt(v_ripple_on_cap_mv**2 + S2_SELF_RIPPLE_MV**2)

print(f"  Total BEC input ripple current: {total_i_rip_A:.3f} A pk-pk")
print(f"  S2 bulk cap impedance @ {F_TEST/1e3:.0f} kHz:")
print(f"    {N_CAPS}× {C_EACH_F*1e6:.0f}µF parallel — ESR_tot = {ESR_TOTAL*1000:.2f} mΩ")
print(f"    Z_C @ {F_TEST/1e3:.0f} kHz = {Z_C*1e3:.4f} mΩ")
print(f"    Z_total = {Z_TOTAL*1e3:.3f} mΩ (ESR-dominated)")
print()
print(f"  V_VMOTOR ripple from BEC: {v_ripple_on_cap_mv:.2f} mV pk-pk")
print(f"  S2 self-ripple (from PR #34): {S2_SELF_RIPPLE_MV:.0f} mV pk-pk")
print(f"  Combined RSS: {v_ripple_total_mv:.2f} mV pk-pk")
print()

SPEC_MV = 100.0
verdict = "PASS ✓" if v_ripple_total_mv <= SPEC_MV else "FAIL ✗"
print(f"  Spec: ≤ {SPEC_MV} mV pk-pk on V_VMOTOR (bulk-cap node)")
print(f"  Verdict: {verdict} (margin {SPEC_MV - v_ripple_total_mv:.1f} mV)")
print()
print("  Note: combined ripple stays under 100 mV spec; S2 bulk caps")
print("  effectively absorb BEC switching noise via low-ESR polymer caps.")
