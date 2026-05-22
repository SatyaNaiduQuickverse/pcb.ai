"""Phase 4-place-bulk-caps S2 — hold-up sim post-processor + plot.

Runs ngspice on holdup_ngspice.cir (3-case sweep), generates holdup.png.
Honest per-load reporting: master spec is 1ms / ≤5V sag — passes at 5A cruise,
fails at 40A/100A (insufficient bulk capacitance for full-power glitch).
"""
import subprocess
import re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
DECK = HERE / "holdup_ngspice.cir"
DATA = HERE / "holdup_data.dat"
PNG = HERE / "holdup.png"

SAG_LIMIT_V = 5.0


def main():
    r = subprocess.run(["ngspice", "-b", str(DECK)], cwd=str(HERE),
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("ngspice failed")
    sags = {}
    for case, label in [("5a", "5A cruise"), ("40a", "40A hover"), ("100a", "100A burst")]:
        m = re.search(rf'sag_{case}\s*=\s*([\d.eE+-]+)', r.stdout)
        if m:
            sags[label] = float(m.group(1))
    print("Per-load V_VMOTOR sag at 1ms supply interruption:")
    for label, sag in sags.items():
        verdict = "PASS ✓" if sag <= SAG_LIMIT_V else f"FAIL ✗ (over by {sag - SAG_LIMIT_V:.1f}V)"
        print(f"  {label:15s}: sag = {sag:.2f} V  (spec ≤ {SAG_LIMIT_V} V)  → {verdict}")

    # Plot V_VMOTOR (last case = 100A) — most stressed
    arr = np.loadtxt(DATA)
    t = arr[:, 0]
    v_vmotor = arr[:, 1]
    v_bat = arr[:, 3]

    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    ax.plot(t * 1e3, v_bat, color='C2', linewidth=1.0, label='V_BAT (battery)', linestyle=':')
    ax.plot(t * 1e3, v_vmotor, color='C3', linewidth=1.4, label='V_VMOTOR (100A burst case)')
    ax.axhline(25.2 - SAG_LIMIT_V, color='r', linestyle='--', linewidth=1, label=f'sag spec floor ({25.2 - SAG_LIMIT_V} V)')
    ax.axvspan(10, 11, alpha=0.2, color='orange', label='1 ms interrupt')
    ax.set_xlabel('Time (ms)')
    ax.set_ylabel('Voltage (V)')
    ax.set_xlim(9.5, 12.0)
    ax.set_ylim(-5, 30)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='lower right', fontsize=9)
    plt.title("S2 supply hold-up (1 ms interrupt) — 100A burst case shows full-discharge sag\n"
              "Cruise 5A: PASS  |  Hover 40A: FAIL  |  Burst 100A: FAIL — bulk cap energy insufficient")
    plt.tight_layout()
    plt.savefig(PNG, dpi=120)
    print(f"\nWrote {PNG}")


if __name__ == "__main__":
    main()
