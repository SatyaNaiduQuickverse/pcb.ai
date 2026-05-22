"""Phase 4-place-bulk-caps S2 — ripple sim post-processor.

Runs ngspice on ripple_ngspice.cir, parses output, generates ripple.png.
Per-cap measurements (per master 'per-component metrics' rule).
"""
import subprocess
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
DECK = HERE / "ripple_ngspice.cir"
DATA = HERE / "ripple_data.dat"
PNG = HERE / "ripple.png"

RIPPLE_LIMIT_MV = 200.0
PER_CAP_IRMS_LIMIT_A = 4.0   # Panasonic EEHZS1V471P AEC-Q200 rated I_RMS
PER_CAP_ESR_W_LIMIT = 1.0    # Master spec


def main():
    r = subprocess.run(["ngspice", "-b", str(DECK)], cwd=str(HERE),
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("ngspice failed")
    print("ngspice key measurements:")
    for line in r.stdout.splitlines():
        if any(k in line for k in ("v_ripple_pk", "i_c", "p_esr")):
            if "=" in line and "from" not in line:
                print(f"  {line}")

    # Parse measurements from stdout
    import re
    def grab(name):
        m = re.search(rf'{name}\s*=\s*([\d.eE+-]+)', r.stdout)
        return float(m.group(1)) if m else None

    v_ripple = grab('v_ripple_pk')
    i_c = [grab(f'i_c{i}_rms') for i in range(1, 5)]
    p_esr = [grab(f'p_esr_c{i}') for i in range(1, 5)]

    arr = np.loadtxt(DATA)
    # 5 signals × (t, val) = 10 cols: t Vbus | t Ic1 | t Ic2 | t Ic3 | t Ic4
    t = arr[:, 0]
    vbus = arr[:, 1]
    ic1 = arr[:, 3]; ic2 = arr[:, 5]; ic3 = arr[:, 7]; ic4 = arr[:, 9]
    iload = ic1 + ic2 + ic3 + ic4  # superposition: load current ≈ sum of cap currents at high freq

    fig, axes = plt.subplots(2, 1, figsize=(11, 8), dpi=120, sharex=True)
    ax1 = axes[0]
    ax1.plot(t * 1e6, vbus, color='C3', linewidth=1.0)
    ax1.set_ylabel('V_VMOTOR (V)')
    ax1.set_xlim(100, 200)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f'V_VMOTOR pk-pk ripple = {v_ripple*1000:.1f} mV  '
                  f'(spec ≤ {RIPPLE_LIMIT_MV} mV: '
                  f'{"PASS ✓" if v_ripple*1000 <= RIPPLE_LIMIT_MV else "FAIL ✗"})')
    ax2 = axes[1]
    ax2.plot(t * 1e6, ic1, color='C0', linewidth=0.9, label='C1')
    ax2.plot(t * 1e6, ic2, color='C1', linewidth=0.9, label='C2')
    ax2.plot(t * 1e6, ic3, color='C2', linewidth=0.9, label='C3')
    ax2.plot(t * 1e6, ic4, color='C3', linewidth=0.9, label='C4', linestyle=':')
    ax2.plot(t * 1e6, iload, color='black', linewidth=0.6, linestyle='--', label='I_LOAD')
    ax2.set_ylabel('Current (A)')
    ax2.set_xlabel('Time (µs)')
    ax2.set_xlim(100, 200)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(PNG, dpi=120)
    print(f"\nWrote {PNG}")
    print()
    print("Per-cap verdicts (per Panasonic EEHZS1V471P spec):")
    for i, (irms, pesr) in enumerate(zip(i_c, p_esr), start=1):
        v_irms = "PASS ✓" if irms <= PER_CAP_IRMS_LIMIT_A else "FAIL ✗"
        v_pesr = "PASS ✓" if pesr <= PER_CAP_ESR_W_LIMIT else "FAIL ✗"
        print(f"  C{i}: I_RMS={irms:.3f} A (spec ≤4 A, {v_irms})  P_ESR={pesr*1000:.2f} mW (spec ≤1 W, {v_pesr})")


if __name__ == "__main__":
    main()
