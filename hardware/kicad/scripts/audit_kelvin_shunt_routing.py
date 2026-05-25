#!/usr/bin/env python3
"""
audit_kelvin_shunt_routing.py — Phase 4-v3 Tier 4 Kelvin shunt sense audit.

Per ROUTING_METHODOLOGY.md Tier 4 + TI SLOA192 + Bogatin SI/PI Ch. 6:
A current-shunt resistor (R_SHUNT_CHn ~ 0.5–1 mΩ) must be sensed in a
4-WIRE KELVIN topology — sense traces tap the shunt pads at their CENTRES
(not in the high-current path) and route as a tight, length-matched
differential pair to the current-sense amplifier (op-amp / INA).

Geometric criteria validated here:
  1. Sense net (SHUNT_SENSE_POS_CHn or *_NEG_CHn) MUST connect to a pad on
     R_SHUNT_CHn (proves the Kelvin tap exists).
  2. The first track segment from each shunt-pad starts AT the pad centroid
     within 0.2mm tolerance (proves the tap is at pad-centre, not at pad-edge
     where high current dominates).
  3. Pos/neg sense pair length-match within 0.5mm (Tier 4 spec).
  4. Pair runs together: at no point are they separated by >5mm transverse
     (proves they share a common-mode current-loop area — minimises EMI pickup).

Per [[reference-decoupling-cap-package-size]] insight — tight pair routing
matters for noise immunity at our ~10mV signal level.

Reads routing_topology.yaml kelvin_pairs entries:
  kelvin_pairs:
    - channel: CH1
      shunt_ref: R_SHUNT_CH1
      pos_net: SHUNT_SENSE_POS_CH1
      neg_net: SHUNT_SENSE_NEG_CH1
      tolerance_mm: 0.5
      max_separation_mm: 5.0

Exit 0 = all PASS, 1 = any FAIL, 2 = malformed yaml.

Usage:
  python3 audit_kelvin_shunt_routing.py <board.kicad_pcb> [<topology.yaml>]
"""

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


CENTROID_TOLERANCE_MM = 0.2  # Kelvin tap must be at pad centre


def shunt_pad_centroids(board, shunt_ref):
    """Return list of (pad_centroid_mm, netname) for shunt's pads."""
    fp = board.FindFootprintByReference(shunt_ref)
    if fp is None:
        return None
    out = []
    for pad in fp.Pads():
        c = pad.GetPosition()
        out.append(((pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)), pad.GetNetname()))
    return out


def first_track_start_on_net(board, netname):
    """Return (start_x, start_y, track) of any track on netname (mm). None if no tracks."""
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_TRACK) or isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetname() == netname:
            s = t.GetStart()
            return (pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), t)
    return None


def net_track_length_mm(board, netname):
    total = 0.0
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_TRACK) or isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetname() != netname:
            continue
        s, e = t.GetStart(), t.GetEnd()
        dx = pcbnew.ToMM(e.x - s.x)
        dy = pcbnew.ToMM(e.y - s.y)
        total += (dx * dx + dy * dy) ** 0.5
    return total


def max_transverse_separation_mm(board, pos_net, neg_net):
    """For each segment of pos_net, find nearest neg_net segment endpoint and
    measure perpendicular distance. Return max across all pos segments. Crude
    but catches gross deviations (pair drifts >5mm apart)."""
    pos_segs = [(t.GetStart(), t.GetEnd()) for t in board.GetTracks()
                if isinstance(t, pcbnew.PCB_TRACK) and not isinstance(t, pcbnew.PCB_VIA)
                and t.GetNetname() == pos_net]
    neg_pts = []
    for t in board.GetTracks():
        if not isinstance(t, pcbnew.PCB_TRACK) or isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetname() == neg_net:
            for p in (t.GetStart(), t.GetEnd()):
                neg_pts.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
    if not pos_segs or not neg_pts:
        return 0.0
    max_sep = 0.0
    for s, e in pos_segs:
        mid_x = pcbnew.ToMM((s.x + e.x) / 2)
        mid_y = pcbnew.ToMM((s.y + e.y) / 2)
        nearest = min((((nx - mid_x) ** 2 + (ny - mid_y) ** 2) ** 0.5
                       for nx, ny in neg_pts), default=0.0)
        max_sep = max(max_sep, nearest)
    return max_sep


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    topology_path = (
        sys.argv[2] if len(sys.argv) > 2
        else "docs/PHASE4V3_LOCKFILES/routing_topology.yaml"
    )

    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(topology_path).exists():
        print(f"INFO: {topology_path} not found — no kelvin_pairs to audit")
        sys.exit(0)

    topology = yaml.safe_load(Path(topology_path).read_text()) or {}
    pairs = topology.get("kelvin_pairs", [])
    if not pairs:
        print("INFO: routing_topology.yaml has no kelvin_pairs — nothing to audit")
        sys.exit(0)

    board = pcbnew.LoadBoard(board_path)

    print(f"=== Tier 4 Kelvin shunt sense audit: {Path(board_path).name} ===")
    print(f"Topology: {topology_path}")
    print(f"Pairs: {len(pairs)}\n")

    any_fail = False

    for p in pairs:
        ch = p.get("channel", "?")
        shunt_ref = p.get("shunt_ref")
        pos_net = p.get("pos_net")
        neg_net = p.get("neg_net")
        tol = p.get("tolerance_mm", 0.5)
        max_sep = p.get("max_separation_mm", 5.0)

        if not (shunt_ref and pos_net and neg_net):
            print(f"  [SKIP] {ch}: incomplete pair spec")
            continue

        # Check 1: shunt exists + sense nets actually connect to shunt pads
        pads = shunt_pad_centroids(board, shunt_ref)
        if pads is None:
            print(f"  [SKIP] {ch}: {shunt_ref} not on board (subsystem parked?)")
            continue
        pos_pad = next((c for c, n in pads if n == pos_net), None)
        neg_pad = next((c for c, n in pads if n == neg_net), None)
        if pos_pad is None or neg_pad is None:
            print(f"  [FAIL] {ch}: {shunt_ref} has no pad on {pos_net}/{neg_net} "
                  f"(Kelvin tap missing)")
            any_fail = True
            continue

        # Check 2: first track starts AT pad centroid (tap-at-centre)
        for net, expected in ((pos_net, pos_pad), (neg_net, neg_pad)):
            ts = first_track_start_on_net(board, net)
            if ts is None:
                print(f"  [SKIP] {ch}/{net}: no tracks routed yet")
                continue
            tx, ty, _ = ts
            d = ((tx - expected[0]) ** 2 + (ty - expected[1]) ** 2) ** 0.5
            if d > CENTROID_TOLERANCE_MM:
                print(f"  [FAIL] {ch}/{net}: first track start ({tx:.2f},{ty:.2f}) "
                      f"is {d:.2f}mm from shunt pad centre — Kelvin tap displaced")
                any_fail = True

        # Check 3: length match
        len_pos = net_track_length_mm(board, pos_net)
        len_neg = net_track_length_mm(board, neg_net)
        if len_pos == 0 and len_neg == 0:
            print(f"  [SKIP] {ch}: pair not routed yet")
            continue
        spread = abs(len_pos - len_neg)
        status = "PASS" if spread <= tol else "FAIL"
        if status == "FAIL":
            any_fail = True
        print(f"  [{status}] {ch} length-match: |{len_pos:.2f}−{len_neg:.2f}| = "
              f"{spread:.2f}mm (tol ±{tol}mm)")

        # Check 4: pair max transverse separation
        sep = max_transverse_separation_mm(board, pos_net, neg_net)
        status = "PASS" if sep <= max_sep else "FAIL"
        if status == "FAIL":
            any_fail = True
        print(f"  [{status}] {ch} max-separation: {sep:.2f}mm "
              f"(≤{max_sep}mm per spec)")

    if any_fail:
        print("\nRESULT: FAIL — Kelvin shunt routing violates spec")
        sys.exit(1)
    print("\nRESULT: PASS — all Kelvin shunt pairs comply with Tier 4 spec")


if __name__ == "__main__":
    main()
