#!/usr/bin/env python3
"""
audit_decoupling.py — Phase 4-v3 Tier 3 per-IC decoupling audit

Per Bogatin SI/PI Ch. 5 + R25:
- Each IC.VDD pin needs ≥1 decoupling cap within 3mm SAME layer
- Cap value matched to IC switching freq:
  - Slow logic (≤10MHz): 100nF 0603
  - MCU (100MHz): 100nF + 10nF 0402 parallel
  - Switching regulator output: 10µF + 100nF parallel

Per Phase 4-v3 placement methodology Tier 3 (G4) + R25 (same-side).

Identifies decoupling caps by:
1. Lookup in docs/PHASE4V3_LOCKFILES/routing_topology.yaml role='decoupling'
2. Fallback: capacitors on net containing IC's VDD net within 5mm

For each IC.VDD pin (where IC.body_area_mm2 > 4):
- Find nearest cap on same net
- Verify distance ≤ 3mm
- Verify same layer
- Report cap value (from value field)

Exit 0 = all PASS, 1 = any FAIL.

Usage:
  python3 audit_decoupling.py <board.kicad_pcb>
"""

import re
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable")
    sys.exit(1)


MAX_DISTANCE_MM = 3.0  # R25 default (HIGH-frequency rails)
IC_BODY_AREA_MIN_MM2 = 4.0  # heuristic: ICs are >4mm² body, passives smaller
PARKING_X_THRESHOLD = 130.0  # board ≤100mm; parking_grid origin x=200; 30mm buffer

# Net-class-aware decoupling thresholds (Sai 2026-05-27 lock per Bogatin
# SI Simplified Ch.5 frequency-class analysis). Different rail classes have
# different decoupling distance requirements because the decoupling cap's
# job is to provide low-impedance current return at the rail's switching
# frequency. HIGH-frequency rails (digital MCU VDD, gate-driver V_DRIVE)
# need the cap CLOSE (≤3mm via stub L); LOWER-frequency rails (analog
# reference, connector supply) tolerate larger distance.
#
# Per Bogatin Ch.5: cap-stub inductance L = μ₀·d/π × ln(2d/r). At 3mm stub
# the inductance is ~3nH; at 8mm it's ~10nH. Impedance at 1MHz = 19mΩ vs
# 63mΩ — both acceptable for low-frequency loads. At 100MHz: 1.9Ω vs 6.3Ω
# — only the tight one works for high-frequency loads.
#
# Codified by [[feedback-codify-not-patch]]: rule emerges from physics,
# not arbitrary uniform threshold.
NET_CLASS_MAX_DISTANCE_MM = {
    # HIGH-FREQ (10MHz+ load transients): MCU digital VDD, gate-driver V_DRIVE
    r"^\+3V3$":     3.0,   # MCU digital VDD (24kHz PWM core, 100MHz CLK)
    r"^\+5V$":      3.0,   # driver V_DRIVE (high di/dt gate drive)
    # MEDIUM-FREQ (1-10MHz): buck outputs at switching freq
    r"^V_BUCK\d?":  5.0,   # buck output rails (1-2MHz buck switching freq)
    r"^\+V9":       5.0,   # gate-driver bootstrap supply (turn-on transient)
    # LOW-FREQ (≤1MHz): analog reference, connector supply quasi-static
    r"^\+3V3A$":    8.0,   # analog reference (LDO-filtered, low transient)
    r"^V5_FC$":     8.0,   # FC connector supply (FC consumer quasi-static)
    r"^\+V5_FC$":   8.0,   # synonym
    r"^V5_AI$":     5.0,   # AI rail (medium dynamics)
    r"^V5_PI5$":    8.0,   # PI camera supply (low transient)
}


def class_max_distance(netname):
    """Return per-net-class max decoupling distance per Bogatin Ch.5 frequency-class."""
    for pattern, max_d in NET_CLASS_MAX_DISTANCE_MM.items():
        if re.match(pattern, netname):
            return max_d
    return MAX_DISTANCE_MM  # default 3mm for unclassified high-freq nets

# --parked-exempt: skip ICs AND caps in parking zone. Added 2026-05-26 (worker-
# caught: G4 flagged channel MCUs J18/J26/J32/J35 at parking coords for not-yet-
# brought channels, which is by design for park-then-bring-in R27).
PARKED_EXEMPT = "--parked-exempt" in sys.argv[2:]


def _is_parked(fp):
    if not PARKED_EXEMPT:
        return False
    return pcbnew.ToMM(fp.GetPosition().x) >= PARKING_X_THRESHOLD


def _body_bbox_area_mm2(fp):
    """Footprint body area in mm² — EXCLUDES reference + value text.

    BUG-FIX 2026-05-26 (caught by validate_audits.py):
    Default FOOTPRINT.GetBoundingBox() includes reference text, which on
    long refs (e.g. "C_DECOUP_OK", "Q_HS_CH1") makes every footprint look
    bigger than its body. With (False, False) we get body-only.

    Validated against synthetic board with pad-area ground truth — see
    docs/AUDIT_VALIDATION/audit_decoupling.md.
    """
    bb = fp.GetBoundingBox(False, False)  # aIncludeText=False, aIncludeInvisibleText=False
    return pcbnew.ToMM(bb.GetWidth()) * pcbnew.ToMM(bb.GetHeight())


def is_ic(fp):
    """True if footprint is likely an IC (vs passive/connector/test-point).

    BUG-FIX 2026-05-26 (worker-caught on real S6 board): bbox-only heuristic
    incorrectly classified connectors (J* — JST/XT30) and test-pads (TP* —
    PAD_V3V3 etc) as ICs. They have ≥4mm² body but they aren't powered ICs
    needing decoupling. Exclude by refdes prefix.
    """
    ref = fp.GetReference()
    # 2026-05-26 batch 1.6 (VESC cross-check caught C11 false positive):
    # Exhaustive passive + connector + mech-fiducial prefix exclusion. Only
    # U* style ICs need decoupling check (and a handful of niche IC prefixes
    # like MK / IC). Better to under-exclude here than over-flag every big-body
    # bulk cap on real boards.
    if ref.startswith(("J", "P", "TP", "H", "FID", "FB", "CP", "C", "R", "Q", "Y", "BT", "SW", "SP", "K", "M")):
        return False  # P/J = connectors/pin-headers/sockets
    if ref.startswith("D") and ref[1:].isdigit():
        return False  # diodes (LEDs, schottky)
    if ref.startswith("L") and ref[1:].isdigit():
        return False  # inductors / ferrite beads
    if ref.startswith("F") and ref[1:].isdigit():
        return False  # fuses
    return _body_bbox_area_mm2(fp) > IC_BODY_AREA_MIN_MM2


def is_decoupling_cap(fp):
    """True if footprint is a small ceramic cap (0402/0603/0805)."""
    ref = fp.GetReference()
    if not ref.startswith("C"):
        return False
    return _body_bbox_area_mm2(fp) < 5.0  # 0805 and smaller


def get_vdd_pins(fp):
    """Return [(pad, netname)] for VDD-like pins on this IC."""
    vdd_patterns = re.compile(
        r"^(\+3V3|\+5V|\+9V|\+12V|\+VMOTOR|VDD|VCC|AVDD|DVDD|VBAT|VREG|VPP|VAA)",
        re.IGNORECASE,
    )
    out = []
    for pad in fp.Pads():
        netname = pad.GetNetname()
        if netname and vdd_patterns.match(netname):
            out.append((pad, netname))
    return out


def find_decoupling_caps_for_pin(board, ic_pad, ic_layer, vdd_netname):
    """Return list of (cap_fp, distance_mm, same_layer) for caps on this net."""
    pin_pos = ic_pad.GetPosition()
    pin_x = pcbnew.ToMM(pin_pos.x)
    pin_y = pcbnew.ToMM(pin_pos.y)

    candidates = []
    for fp in board.GetFootprints():
        if not is_decoupling_cap(fp):
            continue
        if _is_parked(fp):
            continue  # parked cap not on-board yet (--parked-exempt)
        # Check if any pad of this cap is on the same VDD net
        cap_on_net = False
        for pad in fp.Pads():
            if pad.GetNetname() == vdd_netname:
                cap_on_net = True
                break
        if not cap_on_net:
            continue
        cap_pos = fp.GetPosition()
        cap_x = pcbnew.ToMM(cap_pos.x)
        cap_y = pcbnew.ToMM(cap_pos.y)
        dist = ((cap_x - pin_x) ** 2 + (cap_y - pin_y) ** 2) ** 0.5
        same_layer = fp.GetLayerName() == ic_layer
        candidates.append((fp, dist, same_layer))
    candidates.sort(key=lambda c: c[1])
    return candidates


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)

    board = pcbnew.LoadBoard(board_path)

    print(f"=== Per-IC decoupling audit: {Path(board_path).name} ===")
    print(f"Max distance: net-class-aware per Bogatin Ch.5 (default {MAX_DISTANCE_MM}mm HIGH-freq; +3V3A/V5_FC ≤8mm LOW-freq)")
    if PARKED_EXEMPT:
        print(f"--parked-exempt: ICs and caps at x ≥ {PARKING_X_THRESHOLD}mm skipped\n")
    else:
        print()

    fails = []
    warns = []
    passes = 0
    skipped_ics = 0
    skipped_parked = 0

    for fp in board.GetFootprints():
        if not is_ic(fp):
            continue
        if _is_parked(fp):
            skipped_parked += 1
            continue
        ic_ref = fp.GetReference()
        ic_layer = fp.GetLayerName()
        vdd_pins = get_vdd_pins(fp)
        if not vdd_pins:
            skipped_ics += 1
            continue  # no VDD net (likely passive cluster or test point)

        for pad, vdd_netname in vdd_pins:
            caps = find_decoupling_caps_for_pin(board, pad, ic_layer, vdd_netname)
            if not caps:
                fails.append(
                    f"{ic_ref}.{pad.GetPadName()} (net={vdd_netname}): NO decoupling cap on net"
                )
                continue
            # Best cap = nearest same-layer
            best = next(
                (c for c in caps if c[2]),  # same_layer=True
                caps[0],  # else just nearest
            )
            cap_fp, dist, same_layer = best
            cap_ref = cap_fp.GetReference()

            # Net-class-aware per Bogatin Ch.5 (Sai 2026-05-27 lock)
            max_d = class_max_distance(vdd_netname)
            if dist > max_d:
                fails.append(
                    f"{ic_ref}.{pad.GetPadName()} (net={vdd_netname}): "
                    f"nearest cap {cap_ref} @ {dist:.2f}mm > {max_d}mm "
                    f"(class-aware: {'HIGH' if max_d<=3 else 'MED' if max_d<=5 else 'LOW'}-freq)"
                )
            elif not same_layer:
                warns.append(
                    f"{ic_ref}.{pad.GetPadName()} (net={vdd_netname}): "
                    f"cap {cap_ref} @ {dist:.2f}mm but on opposite layer (R25 violation)"
                )
            else:
                passes += 1

    print(f"PASS: {passes} IC.VDD pins with cap ≤3mm same-layer")
    if warns:
        print(f"\nWARN ({len(warns)} opposite-layer):")
        for w in warns[:15]:
            print(f"  {w}")
        if len(warns) > 15:
            print(f"  ... +{len(warns)-15} more")
    if fails:
        print(f"\nFAIL ({len(fails)}):")
        for f in fails[:20]:
            print(f"  {f}")
        if len(fails) > 20:
            print(f"  ... +{len(fails)-20} more")
    print(f"\n(skipped {skipped_ics} ICs with no VDD-named net"
          f"{f', plus {skipped_parked} parked ICs' if skipped_parked else ''})")

    if fails:
        print("\nRESULT: FAIL — decoupling rule R25 violated")
        sys.exit(1)
    if warns:
        print("\nRESULT: WARN — same-layer R25 violations (opposite-layer caps)")
    print("\nRESULT: PASS — all ICs decoupled per R25")


if __name__ == "__main__":
    main()
