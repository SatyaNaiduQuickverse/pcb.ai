#!/usr/bin/env python3
"""
audit_fos_cap_ripple.py — G_FoS4 capacitor ripple-current FoS gate.

Proactive 2026-05-26 (Sai FoS mandate). Polymer/electrolytic caps have a
RIPPLE CURRENT rating (RMS, at specified frequency). Exceeding it shortens
life dramatically (ESR × I²_RMS = self-heating).

FoS rule: I_ripple_rated ≥ I_RMS_actual × 1.5 (industry conservative)

For our 4-channel switching ESC with phase-staggered PWM, total bulk-cap
RMS current is REDUCED by 3-4× vs single-channel (per OQ-006 R17 deferred).
Final RMS comes from Stage 9 ngspice sim.

This gate reads docs/PHASE4V3_BOM.yaml + sim results to enforce. Inert
until BOM + sim data are populated:
  components:
    C1:
      part: PCH1V151MCL1GS
      ripple_rated_mA_at_100kHz: 3300  # Nichicon datasheet
      ripple_actual_mA_RMS: 1200       # from ngspice OQ-006 sim
  audit_fos: 1.5

Closes OQ-006 R17 partially (provides the FoS gate; sim still pending).

Exit 0 = all PASS or SKIP, 1 = any FAIL.

Usage:
  python3 audit_fos_cap_ripple.py [bom.yaml]
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed"); sys.exit(1)


FOS_RIPPLE = 1.5


def main():
    bom_path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/PHASE4V3_BOM.yaml")
    if not bom_path.exists():
        print(f"=== Cap ripple FoS audit ===")
        print(f"INFO: {bom_path} not found — gate inert until BOM + ngspice OQ-006 sim data populated")
        sys.exit(0)

    bom = yaml.safe_load(bom_path.read_text()) or {}
    comps = (bom.get("components") or {})
    print(f"=== Cap ripple-current FoS audit: {bom_path.name} ===")
    print(f"FoS: {FOS_RIPPLE}× (industry conservative)\n")

    fails = []
    audited = 0
    for ref, info in comps.items():
        if not ref.startswith(("C", "CP")):
            continue
        i_rated = info.get("ripple_rated_mA_at_100kHz")
        i_actual = info.get("ripple_actual_mA_RMS")
        if i_rated is None or i_actual is None:
            continue
        audited += 1
        required = i_actual * FOS_RIPPLE
        if i_rated < required:
            fails.append(f"  [FAIL] {ref}: rated {i_rated}mA < required {required:.0f}mA "
                         f"({i_actual}mA × {FOS_RIPPLE} FoS)")
        else:
            print(f"  [PASS] {ref}: {i_rated}mA ≥ {required:.0f}mA")

    print()
    print(f"Audited {audited} caps with ripple metadata\n")
    if fails:
        for f in fails: print(f)
        print(f"\nRESULT: FAIL — {len(fails)} cap ripple FoS violations")
        sys.exit(1)
    if audited == 0:
        print("RESULT: SKIP — no caps have ripple_rated + ripple_actual metadata (BOM+sim pending)")
        sys.exit(0)
    print("RESULT: PASS — all caps meet ripple-current FoS")


if __name__ == "__main__":
    main()
