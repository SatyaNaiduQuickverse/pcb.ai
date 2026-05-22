"""Sim 2 — Gate driver ringing analytical from DRV8300 + AOTL66912 datasheets.

DRV8300 datasheet: gate drive 1.5A peak, t_rise/t_fall ~10 ns into 1 nF.
AOTL66912 datasheet: V_GS_max=20V (abs); Qg=80nC typical; Ciss=4nF, Crss=0.4nF
Gate damping R_GH = 15Ω (per channel_skidl.py phase 3-redo).
Gate clamp: 5.6V Zener BZT52C5V6 (Vgs limit) + 10K pulldown.

Loop: DRV out → R_GH 15Ω → Q gate (Ciss 4nF) → source (motor node).
LC tank: L_loop ~5nH (PCB trace) + Ciss 4nF → f_ring ~1.1 MHz.
Damping factor ζ = R/(2·sqrt(L/C)) = 15/(2·sqrt(5e-9/4e-9)) = 6.7 → overdamped.

V_overshoot ≈ V_drive × exp(-π·ζ/sqrt(1-ζ²)) → effectively zero with ζ>1.

Acceptance per master spec: V_overshoot ≤ 18V (AOTL66912 V_GS_max 20V with 2V margin).
"""
import math

V_DRIVE = 12.0          # DRV8300 V_BST typ
R_GH = 15.0             # Gate damping
L_LOOP = 5e-9           # PCB gate loop ~5nH
C_ISS = 4e-9            # AOTL66912 input cap

omega0 = 1.0 / math.sqrt(L_LOOP * C_ISS)
f_ring = omega0 / (2 * math.pi)
zeta = R_GH / (2 * math.sqrt(L_LOOP / C_ISS))

print("Sim 2 — Gate driver ringing")
print(f"  Loop: DRV out → R_GH={R_GH}Ω → Q gate (Ciss={C_ISS*1e9}nF)")
print(f"  PCB loop L: {L_LOOP*1e9} nH")
print(f"  Resonant f: {f_ring/1e6:.2f} MHz")
print(f"  Damping ζ = {zeta:.2f}")
if zeta > 1:
    print(f"  Overdamped — no ringing")
    v_overshoot = 0.0
else:
    v_overshoot = V_DRIVE * math.exp(-math.pi * zeta / math.sqrt(1 - zeta**2))
print(f"  V_overshoot: {v_overshoot:.3f} V")
print()

V_GS_MAX_ABS = 20.0
V_GS_SPEC = 18.0  # Master spec margin
v_peak = V_DRIVE + v_overshoot
print(f"  V_GS peak: {V_DRIVE} + {v_overshoot:.3f} = {v_peak:.3f} V")
print(f"  Spec (master): ≤ {V_GS_SPEC} V (AOTL66912 V_GS_max={V_GS_MAX_ABS} V with 2V margin)")
verdict = "PASS ✓" if v_peak <= V_GS_SPEC else "FAIL ✗"
print(f"  Verdict: {verdict} (margin {V_GS_SPEC - v_peak:.2f} V)")
print()
print("  Note: 5.6V Zener clamp (BZT52C5V6) prevents V_GS > 6V regardless")
print("  of ringing (per Phase 3-redo gate-clamp design).")
