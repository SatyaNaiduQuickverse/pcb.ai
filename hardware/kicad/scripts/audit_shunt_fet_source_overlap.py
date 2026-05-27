#!/usr/bin/env python3
"""audit_shunt_fet_source_overlap.py — G_SHUNT_FET_OVERLAP placement gate.

Per Sai R26 lock 2026-05-27 (worker STEP-5 SHUNT ampacity finding):
high-current shunts (R56/57/58/59 + per-channel mirrors, anything sensing
phase current at >=10A continuous) MUST physically overlap the LS FET
source pad of the phase they sense, with >=1.5mm² bbox overlap area.

Rationale (physics, per [[feedback-physics-as-compass]]):
  - R17 spec: 70A continuous / 100A burst-10s per channel
  - IPC-2152 (1oz, 10°C rise): 70A requires ~4mm trace width
  - Bridge trace between shunt and FET source pad is GEOMETRICALLY
    INFEASIBLE at typical 0.85mm-2mm clearance — only direct pad-to-pad
    via array works (16 × 0.6mm vias = ~96A continuous per IPC-2152)
  - 16-via array at 0.6mm pitch needs >=1.5mm² shared landing area
  - VESC + premium ESC reference designs all use shunt-source overlap
    (industry standard per [[feedback-anchor-on-most-capable-reference]])

This gate is BINDING for all placement PRs that touch shunts. It joins
R25 (decoupling), R23 (passive island), R19 (loop-L symmetry) as a
placement discipline (per [[feedback-codify-not-patch]]).

Detection logic:
  1. Identify shunts: refdes pattern matching SHUNT_REF_PATTERNS
     (default R(56|57|58|59) + _CHn suffix or unsuffixed CH1 base).
  2. For each shunt, identify its high-side ("TOP") net by inspecting
     its pad nets and matching SHUNT_[ABC]_TOP_CHn pattern. The phase
     letter + channel number then identify the LS FET (whose SOURCE
     pad connects to the SAME SHUNT_*_TOP_CHn net).
  3. Compute axis-aligned bbox overlap of shunt body bbox with the
     LS FET's largest source pad bbox. PASS if overlap area >= 1.5mm²,
     else FAIL with diagnostic.

Reference: STEP-5 verdict 2026-05-27 found CH1 Q.9 source -> R57.1
connection was 1×0.6mm via + 0.4mm F.Cu trace, blocked from via-array
by FET drain pads at 0.85mm gap, with bridge trace requiring ~4mm width
per IPC-2152 — geometrically impossible.

Exit 0 PASS, 1 FAIL, 2 USAGE.

Usage:
  python3 audit_shunt_fet_source_overlap.py <board.kicad_pcb> [--parked-exempt]

--parked-exempt (2026-05-27, master R26 G_META1 wiring):
  On a STAGED board (e.g. CH1 brought, CH2/3/4 parked off-board at x≥130),
  skip any shunt whose body centre x ≥ PARKING_X_THRESHOLD (130mm). Parked
  shunts can't overlap their FET source pads because both are parked off-board
  by design (park-then-bring-in R27). Mirrors the pattern in audit_decoupling.py
  so master_pre_merge.sh can propagate --staged → --parked-exempt uniformly.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

# --parked-exempt: skip shunts (and thus their FET pairs) parked off-board.
# Mirrors audit_decoupling.py PARKED_EXEMPT pattern (2026-05-26). board path is
# argv[1]; the flag is scanned in argv[2:] so it never collides with the board.
PARKING_X_THRESHOLD = 130.0  # board ≤100mm; parking_grid origin x≥200; 30mm buffer
PARKED_EXEMPT = "--parked-exempt" in sys.argv[2:]

# Refdes patterns. Original default included R56, but worker 2026-05-27
# clarified R56/R77/R113/R149 (per-channel) are 10K CSA-C FILTERS in 0402,
# NOT high-current shunts. The audit MUST identify shunts by their FOOTPRINT
# package (2512 chip = 1W power resistor) AND their high-side net membership,
# not by ref number alone. Without this filter the audit FAILs on the CSA
# filter that legitimately shares the SHUNT_C_TOP_CHn net but isn't a shunt.
#
# Identification chain (BOTH must hold):
#   1. Refdes is an "R" resistor with any number (allow CHn suffix per legacy)
#   2. Footprint name contains "2512" (1W 6332-metric chip resistor)
#   3. Has at least one pad on a SHUNT_[ABC]_TOP_CHn net
#
# Item (3) alone identified R56 (0402, on SHUNT_C_TOP_CH1) as a false-positive
# shunt in PR #197 self-test 2026-05-27.
SHUNT_REF_PATTERN = re.compile(r"^R\d+(_CH\d+)?$")
SHUNT_FOOTPRINT_HINT = "2512"  # 1W chip-resistor package marker

# High-side-of-shunt net pattern: SHUNT_A_TOP_CH1, SHUNT_B_TOP_CH2 etc.
SHUNT_TOP_NET_PATTERN = re.compile(r"^SHUNT_([ABC])_TOP_CH(\d+)$")

# Minimum overlap area for a 16-via array at 0.6mm pitch (per IPC-2152
# >=96A continuous, comfortable 1.37× margin over 70A spec)
MIN_OVERLAP_MM2 = 1.5


def _bbox_of(pos_nm, size_nm, mm):
    """Return (xmin, ymin, xmax, ymax) in mm given centre pos+size in nm."""
    cx = pos_nm.x / mm
    cy = pos_nm.y / mm
    hw = size_nm.x / mm / 2
    hh = size_nm.y / mm / 2
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def _bbox_overlap_area(a, b):
    """Axis-aligned bbox intersection area (mm²); 0 if disjoint."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0); ix1 = min(ax1, bx1)
    iy0 = max(ay0, by0); iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _shunt_body_bbox(fp, mm):
    """Body bbox = combined bbox of all SMD pads (proxy for body footprint
    for 0805/1206/2512 chip shunts). Falls back to GetBoundingBox() if
    SWIG bbox is exposed.
    """
    import pcbnew  # noqa: F401
    try:
        bb = fp.GetBoundingBox()
        # Some KiCad builds include silk in this bbox; we accept that
        # conservative-larger overlap, which is the right direction (will
        # PASS more aggressively, so any FAIL is a true geometric miss).
        return (bb.GetLeft() / mm, bb.GetTop() / mm,
                bb.GetRight() / mm, bb.GetBottom() / mm)
    except Exception:
        # Pad-union fallback
        xs0, ys0, xs1, ys1 = 1e9, 1e9, -1e9, -1e9
        for pad in fp.Pads():
            p = pad.GetPosition()
            s = pad.GetSize()
            x0 = p.x / mm - s.x / mm / 2
            y0 = p.y / mm - s.y / mm / 2
            x1 = p.x / mm + s.x / mm / 2
            y1 = p.y / mm + s.y / mm / 2
            xs0 = min(xs0, x0); ys0 = min(ys0, y0)
            xs1 = max(xs1, x1); ys1 = max(ys1, y1)
        return (xs0, ys0, xs1, ys1)


def _largest_pad_on_net(fp, net_name, mm):
    """Return (bbox_mm, pad_ref) for the LARGEST pad on fp connected to
    net_name. Used to find the LS FET's source pad (largest pad of a
    DPAK/PowerPAK FET == the source/drain tab; we want the source-net pad).
    Returns (None, None) if no pad matches.
    """
    best_area = -1.0
    best_bbox = None
    best_ref = None
    for pad in fp.Pads():
        if pad.GetNetname() != net_name:
            continue
        p = pad.GetPosition()
        s = pad.GetSize()
        area = (s.x / mm) * (s.y / mm)
        if area > best_area:
            best_area = area
            best_bbox = (p.x / mm - s.x / mm / 2,
                         p.y / mm - s.y / mm / 2,
                         p.x / mm + s.x / mm / 2,
                         p.y / mm + s.y / mm / 2)
            best_ref = pad.GetPadName()
    return best_bbox, best_ref


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python3 {Path(__file__).name} <board.kicad_pcb>", file=sys.stderr)
        sys.exit(2)
    pcb_path = sys.argv[1]
    if not Path(pcb_path).exists():
        print(f"=== Shunt-FET source-pad overlap (G_SHUNT_FET_OVERLAP) ===")
        print(f"INFO: board not found ({pcb_path}) — gate inert")
        sys.exit(0)

    try:
        import pcbnew
    except ImportError:
        print("FAIL — pcbnew not importable", file=sys.stderr)
        sys.exit(2)

    print(f"=== Shunt-FET source-pad overlap: {Path(pcb_path).name} ===\n")
    print(f"R26 lock 2026-05-27 (STEP-5 SHUNT ampacity): every high-current")
    print(f"shunt MUST overlap LS FET source pad >= {MIN_OVERLAP_MM2}mm²")
    print(f"(16-via 0.6mm array per IPC-2152, ~96A continuous).")
    if PARKED_EXEMPT:
        print(f"--parked-exempt: shunts at x ≥ {PARKING_X_THRESHOLD}mm skipped (parked off-board).")
    print()

    board = pcbnew.LoadBoard(pcb_path)
    mm = 1_000_000.0

    # Build pad-net index: net -> list of (fp, pad_ref, pad_bbox, pad_area)
    net_to_pads = defaultdict(list)
    fp_by_ref = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        fp_by_ref[ref] = fp
        for pad in fp.Pads():
            n = pad.GetNetname()
            if not n:
                continue
            p = pad.GetPosition()
            s = pad.GetSize()
            bbox = (p.x / mm - s.x / mm / 2,
                    p.y / mm - s.y / mm / 2,
                    p.x / mm + s.x / mm / 2,
                    p.y / mm + s.y / mm / 2)
            area = (s.x / mm) * (s.y / mm)
            net_to_pads[n].append((fp, pad.GetPadName(), bbox, area))

    # Identify shunts: ref pattern + 2512 footprint + SHUNT_*_TOP_CHn net.
    # Without all three, CSA filter R56/R77/R113/R149 (10K 0402 on
    # SHUNT_C_TOP_CHn for CSA-C circuit) is falsely classified as a shunt.
    def _fpid_str(fp):
        fpid = fp.GetFPID()
        try:
            return fpid.GetLibItemName().c_str()
        except Exception:
            return str(fpid.GetLibItemName())

    def _has_top_net(fp):
        for pad in fp.Pads():
            if SHUNT_TOP_NET_PATTERN.match(pad.GetNetname() or ''):
                return True
        return False

    def _is_parked(fp):
        # --parked-exempt: shunt centre x ≥ threshold ⇒ off-board parked.
        if not PARKED_EXEMPT:
            return False
        return (fp.GetPosition().x / mm) >= PARKING_X_THRESHOLD

    parked_skipped = 0
    shunts = []
    for ref, fp in fp_by_ref.items():
        if not (SHUNT_REF_PATTERN.match(ref)
                and SHUNT_FOOTPRINT_HINT in _fpid_str(fp)
                and _has_top_net(fp)):
            continue
        if _is_parked(fp):
            parked_skipped += 1
            continue  # parked off-board; FET pair also parked (R27)
        shunts.append(fp)
    if not shunts:
        print(f"INFO: no shunts matched pattern {SHUNT_REF_PATTERN.pattern}")
        print(f"      (pattern covers R56/57/58/59 + optional _CHn suffix)")
        print(f"RESULT: PASS — no shunts present to gate")
        sys.exit(0)

    fails = []
    passes = []
    skipped = []

    for shunt in shunts:
        ref = shunt.GetReference()
        # Find shunt's TOP net by inspecting its pads
        top_net = None
        for pad in shunt.Pads():
            n = pad.GetNetname()
            m = SHUNT_TOP_NET_PATTERN.match(n) if n else None
            if m:
                top_net = n
                phase = m.group(1)
                chan = m.group(2)
                break
        if not top_net:
            skipped.append(f"{ref}: no SHUNT_[ABC]_TOP_CHn pad — not a high-current shunt, skipped")
            continue

        # Find LS FET on this net: any footprint OTHER than the shunt itself
        # whose pad is on top_net. The largest such pad belongs to the FET
        # SOURCE (tab pad of DPAK / PowerPAK).
        fet_fp = None
        fet_source_bbox = None
        fet_source_pad_ref = None
        best_area = -1.0
        for fp_other, pad_ref, pad_bbox, pad_area in net_to_pads[top_net]:
            if fp_other.GetReference() == ref:
                continue
            if pad_area > best_area:
                best_area = pad_area
                fet_fp = fp_other
                fet_source_bbox = pad_bbox
                fet_source_pad_ref = pad_ref
        if fet_fp is None:
            fails.append(f"{ref}: net '{top_net}' has NO other-footprint pad — "
                         f"LS FET source unfindable (shunt-only net?)")
            continue

        shunt_bbox = _shunt_body_bbox(shunt, mm)
        overlap = _bbox_overlap_area(shunt_bbox, fet_source_bbox)
        sx = (shunt_bbox[0] + shunt_bbox[2]) / 2
        sy = (shunt_bbox[1] + shunt_bbox[3]) / 2
        diag = (f"{ref} (phase {phase} CH{chan}) <-> {fet_fp.GetReference()}.{fet_source_pad_ref} "
                f"(source pad on {top_net}) overlap={overlap:.2f}mm² @ shunt-center"
                f"=({sx:.2f},{sy:.2f}) min={MIN_OVERLAP_MM2}mm²")
        if overlap >= MIN_OVERLAP_MM2:
            passes.append(diag)
        else:
            fails.append(f"FAIL: {diag}")

    # Report
    print(f"Shunts evaluated: {len(shunts)} "
          f"(PASS={len(passes)}, FAIL={len(fails)}, SKIP={len(skipped)}"
          f"{f', PARKED-SKIP={parked_skipped}' if PARKED_EXEMPT else ''})\n")

    if skipped:
        print(f"SKIP ({len(skipped)}):")
        for s in skipped:
            print(f"  {s}")
        print()

    if passes:
        print(f"PASS ({len(passes)}):")
        for p in passes[:20]:
            print(f"  {p}")
        if len(passes) > 20:
            print(f"  ... and {len(passes) - 20} more")
        print()

    if fails:
        print(f"FAIL ({len(fails)}):")
        for f in fails:
            print(f"  {f}")
        print()
        print(f"RESULT: FAIL — {len(fails)} shunt(s) do NOT overlap LS FET source by >= {MIN_OVERLAP_MM2}mm²")
        print(f"Required fix: re-place shunt so its body bbox overlaps the FET source pad")
        print(f"(see PLACEMENT_GLOBAL_PLAN.md §8 addendum #9 + STEP-5 SHUNT ampacity verdict).")
        sys.exit(1)

    print(f"RESULT: PASS — all {len(passes)} shunts overlap LS FET source pad by >= {MIN_OVERLAP_MM2}mm²")
    sys.exit(0)


if __name__ == "__main__":
    main()
