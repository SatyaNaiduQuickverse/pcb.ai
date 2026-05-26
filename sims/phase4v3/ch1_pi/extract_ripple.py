#!/usr/bin/env python3
"""
extract_ripple.py — Phase 4-v3 CH1 +3V3 PI ripple extraction.

Parses the ngspice wrdata output (vdd_ripple.dat) and computes steady-state
peak-to-peak ripple at each IC VDD node, then writes ripple_table.txt
(markdown) with margin to the 50 mV pk-pk target.

The startup window (t < SETTLE) is excluded because the deck runs with UIC and
all rail/decap nodes initialize at 0 V and charge up over the first few µs —
that charge-up is not switching ripple. Steady-state switching ripple is the
pk-pk over the remaining periodic window.
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
DAT = HERE / "vdd_ripple.dat"
OUT = HERE / "ripple_table.txt"

SETTLE = 50e-6      # exclude UIC charge-up transient (>~5 PWM periods in)
TARGET_MVPP = 50.0  # spec: VDD ripple <= 50 mV pk-pk at any IC pin

# Column map of the wrdata output (col0 = time, then SAVE order).
# header: time v(vJ19) v(vJ18) v(vJ20) v(vJ21) v(vJ22) v(vU3) v(vU4)
COLS = [
    ("J19 DRV8300 gate driver", "vJ19", 1),
    ("J18 MCU AT32F421",        "vJ18", 2),
    ("J20 INA186 #1",           "vJ20", 3),
    ("J21 INA186 #2",           "vJ21", 4),
    ("J22 INA186 #3",           "vJ22", 5),
    ("U3 LM393 comparator",     "vU3",  6),
    ("U4 74LVC1G08 logic",      "vU4",  7),
]

def main():
    if not DAT.exists():
        sys.exit(f"FATAL: missing raw output {DAT} — run ngspice first.")

    data = np.loadtxt(DAT, skiprows=1)
    t = data[:, 0]
    mask = t > SETTLE
    if mask.sum() < 10:
        sys.exit("FATAL: not enough steady-state samples after SETTLE window.")

    rows = []
    worst_mvpp = 0.0
    worst_ic = None
    for name, node, col in COLS:
        v = data[mask, col]
        vpp_mv = float(v.max() - v.min()) * 1000.0
        margin = TARGET_MVPP - vpp_mv
        rows.append((name, node, vpp_mv, margin))
        if vpp_mv > worst_mvpp:
            worst_mvpp = vpp_mv
            worst_ic = name

    verdict = "PASS" if worst_mvpp <= TARGET_MVPP else "FAIL"

    # ---- console echo (reproduces numbers from the raw) ----
    print(f"Phase 4-v3 CH1 — +3V3 VDD ripple (steady-state, t>{SETTLE*1e6:.0f}us)")
    print(f"source: {DAT.name}  rows>SETTLE: {mask.sum()}")
    print(f"{'IC':<28}{'node':<8}{'ripple_mVpp':>14}{'margin_mV':>12}")
    for name, node, vpp_mv, margin in rows:
        print(f"{name:<28}{node:<8}{vpp_mv:>14.4f}{margin:>12.3f}")
    print(f"\nWORST: {worst_ic} = {worst_mvpp:.4f} mVpp  (target {TARGET_MVPP} mVpp)")
    print(f"VERDICT: {verdict}")

    # ---- markdown table ----
    with open(OUT, "w") as f:
        f.write("# +3V3 VDD Ripple — Phase 4-v3 CH1 PI\n\n")
        f.write(f"Steady-state window: t > {SETTLE*1e6:.0f} us "
                f"(UIC charge-up excluded). Target <= {TARGET_MVPP:.0f} mV pk-pk.\n\n")
        f.write("| IC | VDD node | ripple_mVpp | margin to 50mV |\n")
        f.write("|----|----------|-------------|----------------|\n")
        for name, node, vpp_mv, margin in rows:
            f.write(f"| {name} | {node} | {vpp_mv:.4f} | {margin:+.3f} mV |\n")
        f.write(f"\n**Worst case:** {worst_ic} = {worst_mvpp:.4f} mVpp  ")
        f.write(f"({TARGET_MVPP - worst_mvpp:+.3f} mV margin)\n\n")
        f.write(f"**VERDICT: {verdict}** "
                f"(worst {worst_mvpp:.4f} mVpp vs {TARGET_MVPP:.0f} mVpp target)\n")

    print(f"\nwrote {OUT}")
    sys.exit(0 if verdict == "PASS" else 1)

if __name__ == "__main__":
    main()
