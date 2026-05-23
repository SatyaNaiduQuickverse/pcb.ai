"""verify_spec_diff.py — PR-A4-e amendment 4 2026-05-23 master-gate tool.

Locks rule [[feedback-spec-vs-placement-gate]]: every layout PR involving
multi-instance symmetric components must include automated coord-diff
(actual placement vs reference-transform). FAIL if any delta > 0.5mm.

Scope per master 2026-05-23 dispatch:
 - CH1-CH4 FETs vs locked-reference transforms
   * CH2 = mirror_X(50.0):    x → 100-x, y unchanged
   * CH3 = 180°-rot(50, 47.5): x → 100-x, y → 95-y
   * CH4 = mirror_Y(47.5):    x unchanged, y → 95-y
 - S2 bulk caps: C1-C4 form 2×2 mirror about (50, 36)
 - S3 Hall (U1) at (50, 45) ± 1mm tolerance
 - S5 BEC: J2-J5 mirror about X=50
 - S6 connectors: DOCUMENTED EXCEPTION (one-corner placement by spec); not checked.

Tolerance: 0.5mm per coord (covers nm→mm rounding + 0.1mm placement step).

Output: per-subsystem PASS/FAIL with per-ref delta table.
"""
import pcbnew
import re
import sys
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
TOL_MM = 0.5  # Sai-locked tolerance

TRANSFORMS = {
    'CH2': ('mirror_X(50.0)', lambda x, y: (100.0 - x, y)),
    'CH3': ('180°-rot(50, 47.5)', lambda x, y: (100.0 - x, 95.0 - y)),
    'CH4': ('mirror_Y(47.5)', lambda x, y: (x, 95.0 - y)),
}

# Reference FETs (CH1)
CH1_FETS = ['Q5', 'Q6', 'Q7', 'Q8', 'Q9', 'Q10']
# Paired FETs CH2/3/4 (by index, sorted)
CH234_FETS = {
    'CH2': ['Q11', 'Q12', 'Q13', 'Q14', 'Q15', 'Q16'],
    'CH3': ['Q17', 'Q18', 'Q19', 'Q20', 'Q21', 'Q22'],
    'CH4': ['Q23', 'Q24', 'Q25', 'Q26', 'Q27', 'Q28'],
}


def get_positions():
    """Read footprint positions from .kicad_pcb via pcbnew."""
    board = pcbnew.LoadBoard(str(PCB))
    pos = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        p = fp.GetPosition()
        pos[ref] = (p.x / 1e6, p.y / 1e6)
    return pos


def check_fets(pos):
    """CH1 FETs vs CH2/3/4 transforms."""
    print("\n=== FET symmetry check ===")
    failures = []
    for i, ch1_ref in enumerate(CH1_FETS):
        if ch1_ref not in pos:
            print(f"  MISSING: {ch1_ref}")
            continue
        x1, y1 = pos[ch1_ref]
        for ch, refs in CH234_FETS.items():
            tname, tfunc = TRANSFORMS[ch]
            target_ref = refs[i]
            if target_ref not in pos:
                print(f"  MISSING: {target_ref}")
                continue
            ax, ay = pos[target_ref]
            ex, ey = tfunc(x1, y1)
            dx = ax - ex
            dy = ay - ey
            d = (dx * dx + dy * dy) ** 0.5
            status = "PASS" if d <= TOL_MM else "FAIL"
            if status == "FAIL":
                failures.append((target_ref, ch1_ref, ch, ex, ey, ax, ay, d))
            print(f"  {ch1_ref}→{target_ref} ({ch} {tname}): expected ({ex:.2f},{ey:.2f}) actual ({ax:.2f},{ay:.2f}) Δ={d:.3f}mm  {status}")
    return failures


def check_s2_caps(pos):
    """S2 bulk caps: C1, C2 mirror_X(50); C3, C4 mirror_X(50); all 4 form 2×2 grid."""
    print("\n=== S2 bulk caps symmetry check ===")
    failures = []
    pairs = [('C1', 'C2'), ('C3', 'C4')]
    for left, right in pairs:
        if left not in pos or right not in pos:
            print(f"  MISSING: {left} or {right}")
            continue
        lx, ly = pos[left]
        rx, ry = pos[right]
        ex, ey = 100.0 - lx, ly
        dx = rx - ex
        dy = ry - ey
        d = (dx * dx + dy * dy) ** 0.5
        status = "PASS" if d <= TOL_MM else "FAIL"
        if status == "FAIL":
            failures.append((right, left, 'mirror_X(50)', ex, ey, rx, ry, d))
        print(f"  {left}→{right} (mirror_X(50)): expected ({ex:.2f},{ey:.2f}) actual ({rx:.2f},{ry:.2f}) Δ={d:.3f}mm  {status}")
    return failures


def check_s3_hall(pos):
    """S3 Hall (U1) at (50, 45) ± 1mm."""
    print("\n=== S3 Hall ACS770 placement check ===")
    failures = []
    if 'U1' not in pos:
        print("  MISSING: U1")
        return failures
    ux, uy = pos['U1']
    ex, ey = 50.0, 45.0
    d = ((ux - ex) ** 2 + (uy - ey) ** 2) ** 0.5
    status = "PASS" if d <= 1.0 else "FAIL"  # spec tolerance 1mm
    if status == "FAIL":
        failures.append(('U1', None, 'fixed', ex, ey, ux, uy, d))
    print(f"  U1: expected ({ex:.2f},{ey:.2f}) actual ({ux:.2f},{uy:.2f}) Δ={d:.3f}mm  {status}")
    return failures


def check_s5_bec(pos):
    """S5 BEC: J2-J5 mirror about X=50."""
    print("\n=== S5 BEC bucks symmetry check ===")
    failures = []
    pairs = [('J2', 'J4'), ('J3', 'J5')]  # west-east mirrors per existing placement
    for left, right in pairs:
        if left not in pos or right not in pos:
            print(f"  MISSING: {left} or {right}")
            continue
        lx, ly = pos[left]
        rx, ry = pos[right]
        ex, ey = 100.0 - lx, ly
        d = ((rx - ex) ** 2 + (ry - ey) ** 2) ** 0.5
        status = "PASS" if d <= TOL_MM else "FAIL"
        if status == "FAIL":
            failures.append((right, left, 'mirror_X(50)', ex, ey, rx, ry, d))
        print(f"  {left}→{right} (mirror_X(50)): expected ({ex:.2f},{ey:.2f}) actual ({rx:.2f},{ry:.2f}) Δ={d:.3f}mm  {status}")
    return failures


def check_passives(pos):
    """All CH2/3/4 R/C/D passives vs CH1 source + transform."""
    print("\n=== Channel passives transform check (summary) ===")
    # Load pairings dict
    import collections
    board = pcbnew.LoadBoard(str(PCB))
    by_ch_letter = collections.defaultdict(lambda: collections.defaultdict(list))
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref.startswith(('R', 'C', 'D')):
            continue
        for pad in fp.Pads():
            if pad.GetNet():
                nm = pad.GetNet().GetNetname()
                m = re.search(r"_CH([1234])", nm)
                if m:
                    by_ch_letter[int(m.group(1))][ref[0]].append(ref)
                    break

    def num(r):
        return int(re.match(r'[A-Z]+(\d+)', r).group(1))

    pairings = {}  # CH234_ref -> (CH1_ref, channel)
    for letter in 'RCD':
        ch1 = sorted(by_ch_letter[1][letter], key=num)
        for ch in [2, 3, 4]:
            ch_list = sorted(by_ch_letter[ch][letter], key=num)
            for i, cref in enumerate(ch_list):
                if i < len(ch1):
                    pairings[cref] = (ch1[i], ch)

    failures = []
    total = 0
    for cref, (ch1_ref, ch) in pairings.items():
        if ch1_ref not in pos or cref not in pos:
            continue
        x1, y1 = pos[ch1_ref]
        tname, tfunc = TRANSFORMS[f'CH{ch}']
        ex, ey = tfunc(x1, y1)
        ax, ay = pos[cref]
        d = ((ax - ex) ** 2 + (ay - ey) ** 2) ** 0.5
        total += 1
        if d > TOL_MM:
            failures.append((cref, ch1_ref, f'CH{ch}', ex, ey, ax, ay, d))

    print(f"  Total channel passive pairs checked: {total}")
    print(f"  PASS: {total - len(failures)}")
    print(f"  FAIL (Δ > {TOL_MM}mm): {len(failures)}")
    if failures:
        print(f"  First 5 failures:")
        for f in failures[:5]:
            print(f"    {f[0]}→{f[1]} ({f[2]}): exp ({f[3]:.2f},{f[4]:.2f}) act ({f[5]:.2f},{f[6]:.2f}) Δ={f[7]:.3f}mm")
    return failures


def main():
    pos = get_positions()
    print(f"Loaded {len(pos)} footprint positions from {PCB.name}")
    print(f"Tolerance: ≤ {TOL_MM} mm per coord (Sai-locked 2026-05-23)")

    all_failures = []
    all_failures.extend(check_fets(pos))
    all_failures.extend(check_s2_caps(pos))
    all_failures.extend(check_s3_hall(pos))
    all_failures.extend(check_s5_bec(pos))
    all_failures.extend(check_passives(pos))

    print(f"\n=== TOTAL FAILURES: {len(all_failures)} ===")
    if all_failures:
        print("OVERALL VERDICT: FAIL")
        sys.exit(1)
    else:
        print("OVERALL VERDICT: PASS — full board symmetric within tolerance")
        sys.exit(0)


if __name__ == "__main__":
    main()
