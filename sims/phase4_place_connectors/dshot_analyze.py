"""Analyze DShot 600 signal integrity sim output.

Extract rise time, fall time, overshoot/ringing from V(rx_in) waveform.

Acceptance per Betaflight DShot spec:
  - t_rise/fall ≤ 100ns (acceptable; ideal ≤ 50ns)
  - Overshoot/ringing ≤ 10% of pulse amplitude (3.3V → ≤ 0.33V)
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "dshot_data.txt"

# Each wrdata col-set: t v(...). For 3 vars: (t,drv), (t,tx_in), (t,rx_in)
raw = np.loadtxt(DATA)
t = raw[:, 0]
v_drv = raw[:, 1]
v_tx = raw[:, 3]
v_rx = raw[:, 5]

V_HIGH = 3.3
V_10 = 0.1 * V_HIGH
V_90 = 0.9 * V_HIGH

def find_transition(t, v, going_up=True):
    """Find first 10%-90% transition."""
    if going_up:
        mask10 = v >= V_10
        mask90 = v >= V_90
        i10 = np.argmax(mask10) if mask10.any() else -1
        i90 = np.argmax(mask90) if mask90.any() else -1
    else:
        # Find AFTER the first rising edge
        rising_done = np.argmax(v >= V_90)
        sub_t = t[rising_done:]
        sub_v = v[rising_done:]
        mask90 = sub_v <= V_90
        mask10 = sub_v <= V_10
        i90 = (np.argmax(mask90) + rising_done) if mask90.any() else -1
        i10 = (np.argmax(mask10) + rising_done) if mask10.any() else -1
    return i10, i90

# Rise time on rx_in
i10_r, i90_r = find_transition(t, v_rx, going_up=True)
t_rise = (t[i90_r] - t[i10_r]) * 1e9 if i10_r > 0 and i90_r > 0 else float('nan')

# Fall time on rx_in (after first rising)
i90_f, i10_f = find_transition(t, v_rx, going_up=False)
t_fall = (t[i10_f] - t[i90_f]) * 1e9 if i90_f > 0 and i10_f > 0 else float('nan')

# Overshoot — max v_rx during/after first rising edge
v_steady_high = V_HIGH  # nominal
v_peak = v_rx.max()
overshoot_V = max(0.0, v_peak - v_steady_high)
overshoot_pct = 100.0 * overshoot_V / v_steady_high

# Ringing — look at first 200ns after the rising edge top
window_start = t[i90_r] if i90_r > 0 else 0
window_end = window_start + 200e-9
window_mask = (t >= window_start) & (t <= window_end)
v_ring_peak = v_rx[window_mask].max() if window_mask.any() else v_steady_high
v_ring_trough = v_rx[window_mask].min() if window_mask.any() else v_steady_high
ringing_pkpk_V = v_ring_peak - v_ring_trough
ringing_pct = 100.0 * ringing_pkpk_V / V_HIGH

# Spec checks
RISE_SPEC_NS = 100.0  # Betaflight DShot acceptable
RING_SPEC_PCT = 10.0  # Betaflight

print("DShot 600 signal integrity — 50 mm FC→MCU trace")
print(f"  Driver: 3.3V, R_src=50Ω, ideal rise/fall=10ns")
print(f"  Trace: 5×10mm LC ladder (L=3.2nH+C=0.8pF per section)")
print(f"  Receiver: USBLC6 ESD shunt 25pF + MCU input 5pF")
print()
print(f"  Rise time (rx 10-90%): {t_rise:.1f} ns  (spec ≤ {RISE_SPEC_NS} ns)")
print(f"  Fall time (rx 90-10%): {t_fall:.1f} ns  (spec ≤ {RISE_SPEC_NS} ns)")
print(f"  Overshoot:             {overshoot_V*1000:.0f} mV ({overshoot_pct:.1f}% of V_high)")
print(f"  Ringing (200ns post):  {ringing_pkpk_V*1000:.0f} mV pk-pk ({ringing_pct:.1f}%)")
print()
rise_ok = t_rise <= RISE_SPEC_NS
fall_ok = t_fall <= RISE_SPEC_NS
ring_ok = ringing_pct <= RING_SPEC_PCT
print(f"  Rise PASS: {rise_ok} ✓" if rise_ok else f"  Rise FAIL: {rise_ok} ✗")
print(f"  Fall PASS: {fall_ok} ✓" if fall_ok else f"  Fall FAIL: {fall_ok} ✗")
print(f"  Ringing PASS: {ring_ok} ✓" if ring_ok else f"  Ringing FAIL: {ring_ok} ✗")
print()
print(f"  OVERALL: {'PASS ✓' if (rise_ok and fall_ok and ring_ok) else 'FAIL ✗'}")

# Plot
fig, ax = plt.subplots(figsize=(12, 5), dpi=120)
ax.plot(t*1e6, v_drv, 'k--', linewidth=0.8, alpha=0.5, label='V_DRIVE (3.3V pulse)')
ax.plot(t*1e6, v_tx, 'C1-', linewidth=1.0, alpha=0.6, label='V(tx_in) — driver after 50Ω')
ax.plot(t*1e6, v_rx, 'C3-', linewidth=1.4, label='V(rx_in) — MCU input (post-trace + ESD)')
ax.axhline(V_HIGH, color='gray', linestyle=':', linewidth=0.5)
ax.axhline(V_10, color='lime', linestyle=':', linewidth=0.5, label='10% / 90% (V_HIGH)')
ax.axhline(V_90, color='lime', linestyle=':', linewidth=0.5)
ax.set_xlabel('time (µs)')
ax.set_ylabel('V')
ax.set_title(f'DShot 600 — FC→MCU 50mm trace + ESD shunt\n'
             f'Rise: {t_rise:.0f}ns | Fall: {t_fall:.0f}ns | Ring: {ringing_pct:.1f}% ({ringing_pkpk_V*1000:.0f}mV pk-pk)')
ax.grid(True, alpha=0.3)
ax.legend(loc='center right', fontsize=9)
plt.tight_layout()
plt.savefig(HERE / "dshot_si.png", dpi=120)
print(f"  Wrote {HERE / 'dshot_si.png'}")
