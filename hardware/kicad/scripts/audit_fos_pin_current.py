#!/usr/bin/env python3
"""
audit_fos_pin_current.py — G_FoS5 connector pin current Factor of Safety.

Proactive 2026-05-26 (Sai FoS mandate). For each cable connector, verify
total pin current capacity (per-pin rating × pin count on a single net)
≥ load current × 1.5 FoS.

Connector per-pin ratings (manufacturer datasheet):
  AMASS XT30:        15A per pin (2 pins → 30A theoretical, 15A practical
                                  paralleled limit per AMASS datasheet)
  JST SH SM06B-SRSS: 1A per pin (signal-grade, NOT power)
  JST SH SM08B-SRSS: 1A per pin
  Pin Header (THT):  3A per pin (1A practical)

Reads docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml connectors:
  - ref: J1
    role: battery_input
    max_load_A: 100  (added 2026-05-26 for FoS gate)

If max_load_A not specified, falls back to derived from net role.

Exit 0 = all PASS or skip-no-data, 1 = any FoS violation.

Usage:
  python3 audit_fos_pin_current.py <board.kicad_pcb> [<lockfile.yaml>]
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: pyyaml not installed")
    sys.exit(1)

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


# Connector per-pin current rating (A), keyed by footprint substring
# Per-pin continuous current ratings from manufacturer datasheets (2026-05-26 verified):
PIN_RATING_A = {
    "AMASS_XT30":         30.0,   # AMASS XT30U: 30A cont, 60A burst — UNDERSPECCED for our 70A cont
    "AMASS_XT60":         60.0,   # AMASS XT60U: 60A cont, 130A burst
    "AMASS_XT90":         90.0,   # AMASS XT90U: 90A cont, 240A burst
    "JST_SH_SM06B-SRSS":   1.0,   # JST SH 1mm signal
    "JST_SH_SM08B-SRSS":   1.0,
    "Pin_Header":          1.0,
}
DEFAULT_PIN_RATING_A = 1.0
FOS_PIN = 1.5


def pin_rating_for_fp(fp_libname):
    for k, v in PIN_RATING_A.items():
        if k in fp_libname:
            return v
    return DEFAULT_PIN_RATING_A


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    lock_path = sys.argv[2] if len(sys.argv) > 2 else "docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml"
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(lock_path).exists():
        print(f"FAIL: {lock_path} not found")
        sys.exit(1)

    lf = yaml.safe_load(Path(lock_path).read_text()) or {}
    board = pcbnew.LoadBoard(board_path)

    print(f"=== Connector pin-current FoS audit: {Path(board_path).name} ===")
    print(f"FoS multiplier: {FOS_PIN}× (industry conservative)\n")

    fails = []
    audited = 0
    skipped = 0

    for entry in (lf.get("connectors") or []):
        ref = entry.get("ref")
        max_load = entry.get("max_load_A")
        if max_load is None:
            skipped += 1
            print(f"  [SKIP] {ref}: no max_load_A spec — add to lockfile for FoS audit")
            continue
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"  [SKIP] {ref}: not on board (parked / un-brought)")
            continue
        fp_lib = str(fp.GetFPID().GetLibItemName())
        per_pin = pin_rating_for_fp(fp_lib)
        # Group pads by net to find which net carries the load
        net_pin_count = {}
        for pad in fp.Pads():
            n = pad.GetNetname() or ""
            net_pin_count[n] = net_pin_count.get(n, 0) + 1
        # Find max parallel pin count (assumes load is concentrated on one net)
        max_pins = max(net_pin_count.values()) if net_pin_count else 0
        capacity = per_pin * max_pins
        required = max_load * FOS_PIN
        audited += 1
        if capacity < required:
            fails.append(f"  [FAIL] {ref}: {max_pins} pins × {per_pin}A/pin = {capacity}A < "
                         f"required {required:.1f}A ({max_load}A load × {FOS_PIN} FoS)")
        else:
            print(f"  [PASS] {ref}: {max_pins} pins × {per_pin}A = {capacity}A ≥ {required:.1f}A "
                  f"({max_load}A × {FOS_PIN} FoS)")

    print()
    print(f"Audited: {audited} · skipped (no spec): {skipped}\n")
    if fails:
        for f in fails:
            print(f)
        print(f"\nRESULT: FAIL — {len(fails)} connector pin-current FoS violations")
        sys.exit(1)
    if audited == 0:
        print("RESULT: SKIP — no connector has max_load_A spec in lockfile yet (add to enable)")
        sys.exit(0)
    print("RESULT: PASS — all connectors meet pin-current FoS")


if __name__ == "__main__":
    main()
