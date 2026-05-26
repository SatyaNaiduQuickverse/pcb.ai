#!/usr/bin/env python3
"""G_PP10 — driver MOTOR-pin creepage audit (master + Sai 2026-05-26).

Codifies the east-strip MOTOR/LOGIC domain separation: the gate driver's MOTOR_x
pins are the half-bridge SW node (≈27V working). Any NON-MOTOR-domain pad (e.g.
+3V3 / GND-referenced logic on the MCU, decoupling, protection) within 0.6mm of a
driver MOTOR pin violates IPC-2221 B-grade creepage for the 27V↔logic gap. The
HB-cell 0.3mm relaxation does NOT apply (different domains, not same SW potential).

This is the dedicated, always-BLOCKING gate behind the placer's option-1 keepout
(place_subsystem.py driver_keepouts) — it catches any regression, including in the
CH2/CH3/CH4 mirrors.

Run: python3 audit_driver_motor_pin_creepage.py <board.kicad_pcb> [--parked-exempt]
"""
import re
import sys

try:
    import pcbnew
except ImportError:
    sys.exit("FATAL: pcbnew not importable")

CREEP_MM = 0.6
PARKING_X = 130.0
DRIVER_VALUE_RE = re.compile(r"DRV8300", re.IGNORECASE)
MOTOR_PIN_RE = re.compile(r"^MOTOR_[ABC]_CH\d+$")
# MOTOR-domain nets that share the SW potential (same domain → no creepage rule).
MOTOR_DOMAIN_RE = re.compile(r"^(MOTOR_[ABC]_CH\d+|\+?VMOTOR(_CH\d*)?|SW_CH\d+)$")


def _pads(board, parked_exempt):
    for fp in board.GetFootprints():
        if parked_exempt and pcbnew.ToMM(fp.GetPosition().x) >= PARKING_X:
            continue
        yield fp


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: audit_driver_motor_pin_creepage.py <board> [--parked-exempt]")
    board = pcbnew.LoadBoard(sys.argv[1])
    parked_exempt = "--parked-exempt" in sys.argv[2:]
    print(f"=== Driver MOTOR-pin creepage audit (G_PP10): {sys.argv[1].split('/')[-1]} ===")
    print(f"Min clearance: {CREEP_MM}mm (IPC-2221 B-grade, SW-node↔logic domains)\n")

    # Collect driver MOTOR pins + every other pad.
    motor_pins, other_pads = [], []
    n_drivers = 0
    for fp in _pads(board, parked_exempt):
        ref = fp.GetReference()
        is_driver = bool(DRIVER_VALUE_RE.search(fp.GetValue() or ""))
        if is_driver:
            n_drivers += 1
        for pad in fp.Pads():
            net = pad.GetNetname() or ""
            bb = pad.GetBoundingBox()
            rect = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                    pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                    pad.GetLayerSet(), net, ref, pad.GetPadName())
            if is_driver and MOTOR_PIN_RE.match(net):
                motor_pins.append(rect)
            else:
                other_pads.append(rect)

    if not motor_pins:
        print(f"No driver MOTOR pins on-board (drivers seen: {n_drivers}) — SKIP")
        sys.exit(0)
    print(f"Driver MOTOR pins: {len(motor_pins)} · other on-board pads: {len(other_pads)}\n")

    def gap(a, b):
        dx = max(0.0, max(a[0] - b[2], b[0] - a[2]))
        dy = max(0.0, max(a[1] - b[3], b[1] - a[3]))
        return (dx * dx + dy * dy) ** 0.5

    fails, seen = [], set()
    for mp in motor_pins:
        for op in other_pads:
            if op[6] == mp[6]:                       # same footprint
                continue
            if MOTOR_DOMAIN_RE.match(op[5]):         # same SW domain → no rule
                continue
            if not (mp[4] & op[4]).any():            # different copper layers
                continue
            d = gap(mp, op)
            if d < CREEP_MM:
                k = tuple(sorted([f"{mp[6]}.{mp[7]}", f"{op[6]}.{op[7]}"]))
                if k in seen:
                    continue
                seen.add(k)
                fails.append(f"  [FAIL] {mp[6]}.{mp[7]} (MOTOR SW-node) ↔ {op[6]}.{op[7]} "
                             f"(net={op[5]}): {d:.3f}mm < {CREEP_MM}mm")

    if fails:
        print("\n".join(fails))
        print(f"\nRESULT: FAIL — {len(fails)} driver MOTOR-pin creepage violation(s)")
        sys.exit(1)
    print("RESULT: PASS — all driver MOTOR pins clear non-MOTOR pads by ≥0.6mm")
    sys.exit(0)


if __name__ == "__main__":
    main()
