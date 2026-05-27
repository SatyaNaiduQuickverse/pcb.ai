#!/usr/bin/env python3
"""selftest_shunt_overlap_pr197.py — math + audit verification for §8 #9 shunt anchors.

Master sub-agent PR #197 self-test (R26 codify-not-patch: every Sai-catch fix
needs a master-independent regression test). Loads the canonical .kicad_pcb,
applies the SHUNT_ANCHORS dict from place_subsystem_ch1_v3 + IC_ANCHORS for
Q5-Q10 (LS layer flip preserved), writes the mutated board to a /tmp test
location, then runs audit_shunt_fet_source_overlap.py against it.

PASS criteria:
  - All 3 CH1 shunts (R57/R58/R59) audit PASS with ≥1.5mm² overlap
  - All 9 CH2/3/4 mirror shunts (R93/94/95, R129/130/131, R165/166/167)
    audit PASS with ≥1.5mm² overlap (after mirroring)
  - Per-channel uniformity: overlap area within ±0.05mm² (geometric symmetry)

Exit 0 PASS, 1 FAIL.

Note: this self-test mutates ONLY a /tmp copy of the canonical board. The
canonical .kicad_pcb in hardware/kicad/ is NOT touched (master sub-agent
boundary: coords + spec only; worker transplants to canonical).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "hardware" / "kicad" / "scripts"
CANONICAL_PCB = ROOT / "hardware" / "kicad" / "pcbai_fpv4in1.kicad_pcb"
TEST_PCB = Path("/tmp/pr197_test_board.kicad_pcb")

sys.path.insert(0, str(SCRIPTS))

import pcbnew  # noqa: E402
from place_subsystem_ch1_v3 import IC_ANCHORS, SHUNT_ANCHORS  # noqa: E402

MM = 1_000_000.0

# CH1 LS-FET refs → CH2/3/4 mirror refs (from roster + net-tracing 2026-05-27)
LS_FET_MIRROR_MAP = {
    'Q6': {'CH1': 'Q6', 'CH2': 'Q12', 'CH3': 'Q18', 'CH4': 'Q24'},
    'Q8': {'CH1': 'Q8', 'CH2': 'Q14', 'CH3': 'Q20', 'CH4': 'Q26'},
    'Q10': {'CH1': 'Q10', 'CH2': 'Q16', 'CH3': 'Q22', 'CH4': 'Q28'},
}

# CH1 shunt refs → CH2/3/4 mirror refs (from roster + net-tracing)
SHUNT_MIRROR_MAP = {
    'R57': {'CH1': 'R57', 'CH2': 'R93', 'CH3': 'R129', 'CH4': 'R165'},
    'R58': {'CH1': 'R58', 'CH2': 'R94', 'CH3': 'R130', 'CH4': 'R166'},
    'R59': {'CH1': 'R59', 'CH2': 'R95', 'CH3': 'R131', 'CH4': 'R167'},
}

# Mirror transforms (per parametric_placement.py)
BOARD_MID_X = 50.0
BOARD_MID_Y = 50.0


def mirror_x(x):
    return 2 * BOARD_MID_X - x


def mirror_y(y):
    return 2 * BOARD_MID_Y - y


def transform_for_channel(x, y, channel):
    """CH1 → CH2 = mirror_X, CH3 = mirror_Y(CH2), CH4 = mirror_X(CH3)."""
    if channel == 'CH1':
        return (x, y)
    if channel == 'CH2':
        return (mirror_x(x), y)
    if channel == 'CH3':
        return (mirror_x(x), mirror_y(y))
    if channel == 'CH4':
        return (x, mirror_y(y))
    raise ValueError(channel)


def transform_rotation_for_channel(rot, channel):
    """Rotation under mirror transforms. CH2 = mirror_X → flip horizontal
    component (180 - rot). CH3 = mirror_Y of CH2 → vertical flip ((-rot) % 360).
    CH4 = mirror_X of CH3 → (180 - rot) again. Matches the placer scripts."""
    if channel == 'CH1':
        return rot
    if channel == 'CH2':
        return (180.0 - rot) % 360.0
    if channel == 'CH3':
        # CH3 is mirror_Y of CH2's rotation
        ch2 = (180.0 - rot) % 360.0
        return (-ch2) % 360.0
    if channel == 'CH4':
        ch2 = (180.0 - rot) % 360.0
        ch3 = (-ch2) % 360.0
        return (180.0 - ch3) % 360.0
    raise ValueError(channel)


def apply_anchors(board):
    """Apply Q5-Q10 IC_ANCHORS (with LS layer flip to B.Cu for Q6/8/10),
    SHUNT_ANCHORS for R57/58/59, and propagate mirrors for CH2/3/4."""
    # 1. CH1 FETs (Q5/Q7/Q9 stay F.Cu; Q6/Q8/Q10 go B.Cu)
    ls_refs = {'Q6', 'Q8', 'Q10'}
    placed = []
    for ref, (x, y) in IC_ANCHORS.items():
        if not (ref.startswith('Q') and ref[1:].isdigit()):
            continue
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"  WARN: {ref} not found")
            continue
        want_back = ref in ls_refs
        if fp.IsFlipped() != want_back:
            fp.Flip(fp.GetPosition(), False)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
        # FETs come from parking with rotation 180°; for the IC_ANCHORS placement
        # we preserve that (the v3 placer doesn't change orientation either, so
        # the source-pad-9 EP stays at footprint center either way).
        placed.append(ref)

    # 2. CH1 SHUNT_ANCHORS (rotation + layer explicit)
    for ref, spec in SHUNT_ANCHORS.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"  WARN: {ref} not found")
            continue
        x, y = spec['pos']
        want_back = (spec['layer'] == 'B.Cu')
        if fp.IsFlipped() != want_back:
            fp.Flip(fp.GetPosition(), False)
        fp.SetOrientationDegrees(spec['rotation'])
        fp.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
        placed.append(ref)

    # 3. CH2/3/4 mirror FETs — derive from CH1
    for ch1_q_ref, chan_map in LS_FET_MIRROR_MAP.items():
        ch1_x, ch1_y = IC_ANCHORS[ch1_q_ref]
        for chan, mirror_ref in chan_map.items():
            if chan == 'CH1':
                continue
            mx, my = transform_for_channel(ch1_x, ch1_y, chan)
            mfp = board.FindFootprintByReference(mirror_ref)
            if mfp is None:
                print(f"  WARN: mirror FET {mirror_ref} not found")
                continue
            # All LS-FETs on B.Cu (same as CH1)
            if not mfp.IsFlipped():
                mfp.Flip(mfp.GetPosition(), False)
            mfp.SetPosition(pcbnew.VECTOR2I(int(mx * MM), int(my * MM)))
            placed.append(mirror_ref)

    # CH2/3/4 mirror HS-FETs too (Q5/Q7/Q9) — for completeness
    for ch1_q_ref in ['Q5', 'Q7', 'Q9']:
        ch1_x, ch1_y = IC_ANCHORS[ch1_q_ref]
        # Find the HS-FET partner in each channel by adding +6 to Q number
        # (Q5→Q11/17/23 for CH2/3/4, etc., per LS map offsets +6 +12 +18)
        num = int(ch1_q_ref[1:])
        for chan, offset in [('CH2', 6), ('CH3', 12), ('CH4', 18)]:
            mirror_ref = f'Q{num + offset}'
            mx, my = transform_for_channel(ch1_x, ch1_y, chan)
            mfp = board.FindFootprintByReference(mirror_ref)
            if mfp is None:
                continue
            # HS-FETs on F.Cu
            if mfp.IsFlipped():
                mfp.Flip(mfp.GetPosition(), False)
            mfp.SetPosition(pcbnew.VECTOR2I(int(mx * MM), int(my * MM)))
            placed.append(mirror_ref)

    # 4. CH2/3/4 mirror SHUNTS — derive from CH1 SHUNT_ANCHORS
    for ch1_r_ref, chan_map in SHUNT_MIRROR_MAP.items():
        spec = SHUNT_ANCHORS[ch1_r_ref]
        ch1_x, ch1_y = spec['pos']
        ch1_rot = spec['rotation']
        for chan, mirror_ref in chan_map.items():
            if chan == 'CH1':
                continue
            mx, my = transform_for_channel(ch1_x, ch1_y, chan)
            mrot = transform_rotation_for_channel(ch1_rot, chan)
            mfp = board.FindFootprintByReference(mirror_ref)
            if mfp is None:
                print(f"  WARN: mirror shunt {mirror_ref} not found")
                continue
            # All shunts on B.Cu (matching CH1)
            if not mfp.IsFlipped():
                mfp.Flip(mfp.GetPosition(), False)
            mfp.SetOrientationDegrees(mrot)
            mfp.SetPosition(pcbnew.VECTOR2I(int(mx * MM), int(my * MM)))
            placed.append(mirror_ref)

    return placed


def compute_overlap_for_pair(board, shunt_ref, fet_ref, top_net):
    """Independently compute bbox overlap of shunt's largest SHUNT_*_TOP_CHn
    pad against FET's largest source-net pad (mirrors the audit logic)."""
    shunt = board.FindFootprintByReference(shunt_ref)
    fet = board.FindFootprintByReference(fet_ref)
    if shunt is None or fet is None:
        return None

    # Shunt body bbox (use GetBoundingBox to match audit script)
    sb = shunt.GetBoundingBox()
    shunt_bbox = (sb.GetLeft() / MM, sb.GetTop() / MM,
                  sb.GetRight() / MM, sb.GetBottom() / MM)

    # FET source pad = largest pad on top_net
    best_area = -1
    fet_pad_bbox = None
    for pad in fet.Pads():
        if pad.GetNetname() != top_net:
            continue
        p = pad.GetPosition()
        s = pad.GetSize()
        a = (s.x / MM) * (s.y / MM)
        if a > best_area:
            best_area = a
            fet_pad_bbox = (p.x / MM - s.x / MM / 2,
                            p.y / MM - s.y / MM / 2,
                            p.x / MM + s.x / MM / 2,
                            p.y / MM + s.y / MM / 2)
    if fet_pad_bbox is None:
        return None

    # Overlap
    ix0 = max(shunt_bbox[0], fet_pad_bbox[0])
    iy0 = max(shunt_bbox[1], fet_pad_bbox[1])
    ix1 = min(shunt_bbox[2], fet_pad_bbox[2])
    iy1 = min(shunt_bbox[3], fet_pad_bbox[3])
    overlap = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    return overlap, shunt_bbox, fet_pad_bbox


def main():
    print(f"=== PR #197 self-test: shunt-FET overlap on test board ===\n")

    if not CANONICAL_PCB.exists():
        print(f"FAIL — canonical board not found: {CANONICAL_PCB}", file=sys.stderr)
        return 1

    board = pcbnew.LoadBoard(str(CANONICAL_PCB))
    print(f"Loaded canonical board: {CANONICAL_PCB.name}")
    placed = apply_anchors(board)
    print(f"Applied {len(placed)} anchors (FETs + shunts, CH1 + mirrors)\n")

    # Save mutated board to /tmp
    board.Save(str(TEST_PCB))
    print(f"Wrote test board: {TEST_PCB}\n")

    # Per-pair overlap reporting (independent math, parallel to audit script)
    pair_list = []
    for ch1_r_ref, chan_map in SHUNT_MIRROR_MAP.items():
        # Determine phase letter from shunt ref → top_net
        shunt = board.FindFootprintByReference(ch1_r_ref)
        top_net_ch1 = None
        for pad in shunt.Pads():
            n = pad.GetNetname() or ''
            if n.startswith('SHUNT_') and '_TOP_CH' in n:
                top_net_ch1 = n
                break
        phase = top_net_ch1.split('_')[1]   # A, B, C
        # Match LS-FET ref by channel
        ls_q_ch1 = {'A': 'Q6', 'B': 'Q8', 'C': 'Q10'}[phase]
        for chan, mirror_shunt in chan_map.items():
            mirror_fet = LS_FET_MIRROR_MAP[ls_q_ch1][chan]
            top_net = top_net_ch1.replace('_CH1', f'_{chan}')
            result = compute_overlap_for_pair(board, mirror_shunt, mirror_fet, top_net)
            if result is None:
                pair_list.append((mirror_shunt, mirror_fet, top_net, None))
                continue
            overlap, sb, fb = result
            pair_list.append((mirror_shunt, mirror_fet, top_net, overlap))

    # Print + per-channel uniformity check
    print("Per-pair overlap (independent math):")
    print(f"  {'Shunt':6}  {'LS-FET':6}  {'Net':24} {'Overlap':>10}  {'Verdict':10}")
    fails = 0
    by_phase = {'A': [], 'B': [], 'C': []}
    for shunt_ref, fet_ref, net, overlap in pair_list:
        if overlap is None:
            verdict = "MISSING"
            fails += 1
        elif overlap >= 1.5:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            fails += 1
        print(f"  {shunt_ref:6}  {fet_ref:6}  {net:24} {overlap if overlap else 0:>10.3f}mm² {verdict:10}")
        if overlap is not None:
            phase = net.split('_')[1]
            by_phase[phase].append(overlap)

    print()
    print("Per-phase uniformity check (4-channel symmetry preservation):")
    for phase, vals in by_phase.items():
        if len(vals) != 4:
            print(f"  phase {phase}: INCOMPLETE ({len(vals)}/4)")
            continue
        spread = max(vals) - min(vals)
        verdict = "PASS" if spread < 0.05 else "FAIL"
        print(f"  phase {phase}: 4× {vals[0]:.3f}mm² (spread={spread:.4f}mm²) {verdict}")
        if spread >= 0.05:
            fails += 1

    print()
    # Now invoke the official audit on the same test board
    print("=== Running audit_shunt_fet_source_overlap.py on test board ===")
    audit_script = SCRIPTS / "audit_shunt_fet_source_overlap.py"
    res = subprocess.run(
        [sys.executable, str(audit_script), str(TEST_PCB)],
        capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr, file=sys.stderr)
    audit_passed = (res.returncode == 0)
    print(f"\nAudit exit: {res.returncode} ({'PASS' if audit_passed else 'FAIL'})")

    overall = (fails == 0) and audit_passed
    print()
    print("=" * 70)
    print(f"SELF-TEST: {'PASS' if overall else 'FAIL'} "
          f"(pair-math fails={fails}, audit={'PASS' if audit_passed else 'FAIL'})")
    print("=" * 70)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
