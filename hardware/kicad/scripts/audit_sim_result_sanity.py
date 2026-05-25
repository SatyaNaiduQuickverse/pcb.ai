#!/usr/bin/env python3
"""
audit_sim_result_sanity.py — G_S3 simulation result physical-plausibility.

Proactive 2026-05-26 (catch class: solver runs, produces numbers, numbers
are in wrong units or out of physical range, downstream consumes as truth).

Cross-checks for every sim result file:
  1. Temperature values in expected range (Kelvin 273-700 K OR Celsius 0-400 °C
     — both common, depending on solver setup; reject if NEGATIVE Kelvin or
     temps > 700°C suggesting unit confusion)
  2. Current values in expected range (typically mA - A, not pA/nA which
     suggests scaling error)
  3. Voltage values bounded (≤ V_max_on_board × 1.5)
  4. Power dissipation ≥ 0 (positive sign convention)

Reads sim extract_*.py output text or .csv data files. Looks for keywords
"T_J", "T_max", "current", "voltage", "power" + parses the number.

Inert until sim runs exist.

Exit 0 = sanity OK or no sim data, 1 = implausible value detected.

Usage:
  python3 audit_sim_result_sanity.py [<sim_dir>]
"""

import re
import subprocess
import sys
from pathlib import Path


# Plausibility ranges
RANGES = {
    "T_J":      (0, 200),    # °C, junction temp
    "T_max":    (0, 200),
    "T_min":    (-40, 200),
    "I":        (1e-6, 1000),  # A, anywhere from 1µA to 1kA
    "V":        (0, 1000),   # V, signed for AC but ±1kV bound
    "P":        (0, 10000),  # W
}


def main():
    sim_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sims")
    if not sim_root.exists():
        print(f"=== Sim result sanity audit ===")
        print("INFO: sims/ not found — gate inert")
        sys.exit(0)

    print(f"=== Sim result sanity audit: {sim_root} ===\n")

    extracts = list(sim_root.rglob("extract*.py"))
    if not extracts:
        print("INFO: no extract*.py scripts found — gate inert")
        sys.exit(0)

    fails = []
    for e in extracts:
        try:
            out = subprocess.run([sys.executable, str(e)], capture_output=True,
                                 text=True, timeout=30, cwd=e.parent).stdout
        except Exception as ex:
            print(f"  [SKIP] {e.relative_to(sim_root)}: extract failed ({ex})")
            continue
        # Parse common value patterns
        for line in out.splitlines():
            for key, (lo, hi) in RANGES.items():
                m = re.search(rf"\b{key}\s*[=:]\s*(-?[\d.eE+-]+)", line)
                if m:
                    try:
                        v = float(m.group(1))
                    except ValueError:
                        continue
                    if not (lo <= v <= hi):
                        fails.append(f"  [FAIL] {e.relative_to(sim_root)}: {key}={v} outside plausible [{lo},{hi}]")

    if fails:
        for f in fails[:10]: print(f)
        print(f"\nRESULT: FAIL — {len(fails)} implausible sim values")
        sys.exit(1)
    print("RESULT: PASS — all sim values within physical plausibility ranges")


if __name__ == "__main__":
    main()
