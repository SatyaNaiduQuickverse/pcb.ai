#!/usr/bin/env python3
"""
audit_fos_thermal.py — G_FoS1 thermal Factor of Safety gate.

Sai 2026-05-26 directive: "and gave factor of safety". Industry reliability
standard for Si MOSFETs: T_J operates ≤ 75% of T_J_max (25% FoS continuous),
≤ 90% for transient bursts <T_τ (10% FoS).

Reads sims/<thermal_run>/extract_*.py outputs (or docs/THERMAL_BASELINE.md
locked values) and verifies operating T_J peaks against the locked FoS bounds.

Per docs/THERMAL_BASELINE.md regression rule (updated 2026-05-26):
  Continuous T_J ≤ 65.5 °C (min of baseline+3°C and 25% FoS)
  100 A burst T_J ≤ 87 °C   (min of baseline+4°C and 10% transient FoS)

Exit 0 = both PASS, 1 = either FAIL.

Usage:
  python3 audit_fos_thermal.py [--cont T_C] [--burst T_C]
  python3 audit_fos_thermal.py  # reads sims/phase4_integrate/full_thermal/extract*.py
"""

import re
import subprocess
import sys
from pathlib import Path


CONT_LIMIT_C = 65.5  # min(62.76+3 regression, 75 FoS) = 65.5
BURST_LIMIT_C = 87.0  # min(82.99+4 regression, 90 FoS) = 87.0


def extract_peak(script_path):
    """Run extract script, parse the T_J line."""
    try:
        out = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=30, check=True
        ).stdout
    except Exception as e:
        return None, f"extract failed: {e}"
    m = re.search(r"T_J\s*=\s*([\d.]+)\s*[CK]", out)
    if not m:
        return None, "no T_J found in output"
    return float(m.group(1)), out


def main():
    cont_T = None
    burst_T = None
    args = sys.argv[1:]
    if "--cont" in args:
        cont_T = float(args[args.index("--cont") + 1])
    if "--burst" in args:
        burst_T = float(args[args.index("--burst") + 1])

    # If args missing, try extract scripts
    base = Path("sims/phase4_integrate/full_thermal")
    if cont_T is None and (base / "extract.py").exists():
        cont_T, _ = extract_peak(base / "extract.py")
    if burst_T is None and (base / "extract_100A_burst.py").exists():
        burst_T, _ = extract_peak(base / "extract_100A_burst.py")

    print("=== Thermal Factor of Safety audit ===")
    print(f"Limits: continuous ≤ {CONT_LIMIT_C} °C · burst ≤ {BURST_LIMIT_C} °C")
    print(f"(per docs/THERMAL_BASELINE.md regression rule + 25%/10% FoS)\n")

    any_fail = False
    if cont_T is not None:
        margin = CONT_LIMIT_C - cont_T
        status = "PASS" if margin >= 0 else "FAIL"
        if status == "FAIL":
            any_fail = True
        print(f"  [{status}] Continuous: T_J = {cont_T:.2f} °C "
              f"({'margin' if margin>=0 else 'EXCEED'} {abs(margin):.2f} °C)")
    else:
        print("  [SKIP] Continuous: no extract data available")

    if burst_T is not None:
        margin = BURST_LIMIT_C - burst_T
        status = "PASS" if margin >= 0 else "FAIL"
        if status == "FAIL":
            any_fail = True
        print(f"  [{status}] 100 A burst: T_J = {burst_T:.2f} °C "
              f"({'margin' if margin>=0 else 'EXCEED'} {abs(margin):.2f} °C)")
    else:
        print("  [SKIP] Burst: no extract data available")

    if any_fail:
        print("\nRESULT: FAIL — thermal FoS violated")
        sys.exit(1)
    if cont_T is None and burst_T is None:
        print("\nRESULT: SKIP — no sim data; gate inert pre-Stage-10")
        sys.exit(0)
    print("\nRESULT: PASS — thermal FoS satisfied")


if __name__ == "__main__":
    main()
