"""Phase 4-place-battery-input S1 — inrush sim post-processor.

Runs ngspice on inrush_ngspice.cir, parses the output, generates inrush_current.png.
"""
import os
import subprocess
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
DECK = HERE / "inrush_ngspice.cir"
DATA = HERE / "inrush_data.dat"
PNG = HERE / "inrush_current.png"
PEAK_LIMIT_A = 16.0


def run_ngspice():
    res = subprocess.run(
        ["ngspice", "-b", str(DECK)], cwd=str(HERE),
        capture_output=True, text=True, check=False,
    )
    if res.returncode != 0:
        print("ngspice stderr:")
        print(res.stderr)
        raise SystemExit("ngspice failed")
    # Echo key measurements
    for line in res.stdout.splitlines():
        if any(k in line for k in ("i_peak", "v_cap_final", "t_settle")):
            print(line)
    return res.stdout


def parse_data():
    """ngspice wrdata writes columns: t V(vbat) t V(n5) t I(V_BAT)
    (one time column per probed signal, then the signal itself)."""
    arr = np.loadtxt(DATA)
    # 3 signals × (t, val) pairs → 6 columns
    t   = arr[:, 0]
    v_b = arr[:, 1]
    v_c = arr[:, 3]
    i_b = arr[:, 5]
    return t, v_b, v_c, i_b


def main():
    print("Running ngspice...")
    run_ngspice()
    t, v_bat, v_cap, i_bat = parse_data()
    i_peak = float(np.max(np.abs(i_bat)))
    t_peak = t[int(np.argmax(np.abs(i_bat)))]

    fig, ax1 = plt.subplots(figsize=(10, 6), dpi=120)
    ax1.plot(t * 1e3, i_bat, color="C3", linewidth=1.4, label="I_BAT (A)")
    ax1.axhline(PEAK_LIMIT_A, color="r", linestyle="--", linewidth=1, label=f"16 A spec ceiling")
    ax1.axhline(-PEAK_LIMIT_A, color="r", linestyle="--", linewidth=1)
    ax1.set_xlabel("Time (ms)")
    ax1.set_ylabel("Inrush current I_BAT (A)")
    ax1.set_xlim(0, 30)
    ax1.set_ylim(-2, max(PEAK_LIMIT_A * 1.2, i_peak * 1.1))
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right")

    ax2 = ax1.twinx()
    ax2.plot(t * 1e3, v_cap, color="C0", linewidth=1.2, linestyle="-", label="V_CBULK (V)")
    ax2.plot(t * 1e3, v_bat, color="C2", linewidth=0.9, linestyle=":", label="V_BAT step (V)")
    ax2.set_ylabel("Voltage (V)")
    ax2.set_ylim(-2, 30)
    ax2.legend(loc="center right")

    verdict_color = "green" if i_peak <= PEAK_LIMIT_A else "red"
    verdict = "PASS" if i_peak <= PEAK_LIMIT_A else "FAIL"
    plt.title(f"Phase 4-place-battery-input S1 — inrush transient\n"
              f"peak = {i_peak:.2f} A @ t={t_peak*1e3:.3f} ms  "
              f"(spec ≤ {PEAK_LIMIT_A} A: {verdict})",
              color=verdict_color)
    plt.tight_layout()
    plt.savefig(PNG, dpi=120)
    print(f"Wrote {PNG}")
    print(f"VERDICT: peak {i_peak:.2f} A — {verdict} (margin to spec: {PEAK_LIMIT_A - i_peak:.2f} A)")


if __name__ == "__main__":
    main()
