"""Phase 4-place-battery-input S1 — TVS clamp sim post-processor.

Runs ngspice on tvs_clamp_ngspice.cir, plots V_in (transient source) vs V_clamp
(protected +BATT rail) over the 30 V/µs slew event. Verifies SMBJ33A clamps
below 60 V (BSC014N06NS VDS rating).
"""
import subprocess
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
DECK = HERE / "tvs_clamp_ngspice.cir"
DATA = HERE / "tvs_data.dat"
PNG = HERE / "tvs_clamp.png"
CLAMP_LIMIT_V = 60.0   # BSC014N06NS V_DS rating


def run_ngspice():
    res = subprocess.run(
        ["ngspice", "-b", str(DECK)], cwd=str(HERE),
        capture_output=True, text=True, check=False,
    )
    if res.returncode != 0:
        print(res.stderr)
        raise SystemExit("ngspice failed")
    for line in res.stdout.splitlines():
        if any(k in line for k in ("v_clamp_peak", "v_in_peak")):
            print(line)
    return res.stdout


def main():
    print("Running ngspice...")
    run_ngspice()
    arr = np.loadtxt(DATA)
    t   = arr[:, 0]
    v_in     = arr[:, 1]
    v_clamp  = arr[:, 3]
    v_tvs_ck = arr[:, 5]
    v_peak = float(np.max(v_clamp))
    t_peak = t[int(np.argmax(v_clamp))]

    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    ax.plot(t * 1e6, v_in, color="C2", linewidth=1.4, label="V_in (transient source, 30 V/µs)")
    ax.plot(t * 1e6, v_clamp, color="C3", linewidth=1.6, label="V_clamp (+BATT rail, TVS-protected)")
    ax.plot(t * 1e6, v_tvs_ck, color="C0", linewidth=0.9, linestyle=":", label="V_tvs_ck (TVS Z-knee node)")
    ax.axhline(CLAMP_LIMIT_V, color="r", linestyle="--", linewidth=1, label=f"{CLAMP_LIMIT_V} V VDS rating (rev-pol FET)")
    ax.axhline(36.7, color="orange", linestyle=":", linewidth=0.8, label="36.7 V V_BR (SMBJ33A nominal)")
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("Voltage (V)")
    ax.set_xlim(0, 5)
    ax.set_ylim(0, 70)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)

    verdict_color = "green" if v_peak <= CLAMP_LIMIT_V else "red"
    verdict = "PASS" if v_peak <= CLAMP_LIMIT_V else "FAIL"
    plt.title(f"Phase 4-place-battery-input S1 — SMBJ33A TVS clamp\n"
              f"V_clamp peak = {v_peak:.2f} V @ t={t_peak*1e6:.2f} µs  "
              f"(spec ≤ {CLAMP_LIMIT_V} V: {verdict})",
              color=verdict_color)
    plt.tight_layout()
    plt.savefig(PNG, dpi=120)
    print(f"Wrote {PNG}")
    print(f"VERDICT: V_clamp {v_peak:.2f} V — {verdict} (margin to spec: {CLAMP_LIMIT_V - v_peak:.2f} V)")


if __name__ == "__main__":
    main()
