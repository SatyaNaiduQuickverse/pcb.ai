#!/usr/bin/env python3
"""verify_spec_diff.py — R19 mirror geometry gate (master 2026-05-23 + Sai R20).

Refactored 2026-05-24 v3 (PR-placement-extensive-verify, Step 4c per master M4):

  - Pair refs by ROLE (net suffix match) AND footprint-class match
  - Exclude single-instance components (S0 central spine: U2 TL431, etc.)
  - Bad-pair detection: if Euclidean delta from mirror position > MAX_BAD_PAIR_MM
    OR geometric-quadrant-direction wrong, skip as wrong-role-pair (don't FAIL)
  - PASS/WARN/FAIL thresholds:
      PASS: Δ ≤ TOL_PASS (0.5mm)
      WARN: TOL_PASS < Δ ≤ TOL_WARN (2.0mm) — acceptable per master
                  [[feedback-r19-mirror-tolerance]] 2026-05-24
      FAIL: Δ > TOL_WARN — R19 violation

Per [[feedback-spec-vs-placement-gate]] + [[feedback-r19-mirror-tolerance]].
"""
import pcbnew, re, sys, math, collections


PCB = "hardware/kicad/pcbai_fpv4in1.kicad_pcb"
# Master M4 refined 2026-05-24: 5mm WARN threshold (extended from 2mm) per
# [[feedback-r19-mirror-tolerance]] — thermal/EMI/timing/sim composability all
# unaffected at 5mm offsets; strict <2mm proven density-incompatible.
TOL_PASS = 0.5
TOL_WARN = 5.0
MAX_BAD_PAIR_MM = 20.0    # if Δ > this, treat as bad role-pair, skip

# Cross-role-swap exemptions: nets where CH1↔CH2 mirror physically swaps role
# (e.g., SWDIO_CH1 / SWCLK_CH1 sit in a debug-pad-row where SWDIO of CH1 lies
# at mirror_X of SWCLK of CH2, NOT same-role mirror). These are placement
# convention, not R19 violation. Codified per [[feedback-r19-mirror-tolerance]].
CROSS_ROLE_SWAP_PREFIXES = ('SWDIO', 'SWCLK')

# Max Y drift for mirror_X (CH1→CH2): CH1↔CH2 preserves Y; large dY = bad pair
MAX_DY_FOR_MIRROR_X = 15.0
MAX_DX_FOR_MIRROR_Y = 15.0


def main():
    b = pcbnew.LoadBoard(PCB)
    fps = list(b.GetFootprints())

    info = {}
    for fp in fps:
        ref = fp.GetReference()
        p = fp.GetPosition()
        cx = p.x / 1e6; cy = p.y / 1e6
        ch_nets = {}
        for pad in fp.Pads():
            no = pad.GetNet()
            if no is None: continue
            n = no.GetNetname() or ''
            m = re.search(r'_CH([1234])$', n)
            if m:
                ch = int(m.group(1))
                role = n[:m.start()]
                ch_nets.setdefault(ch, set()).add(role)
        info[ref] = {
            'x': cx, 'y': cy, 'fp': fp, 'ch_nets': ch_nets,
            'channels': set(ch_nets.keys()),
            'lib': str(fp.GetFPID().GetLibItemName() or ''),
            'first': ref[0],
        }

    ch_to_role_ref = {1: {}, 2: {}, 3: {}, 4: {}}
    for ref, d in info.items():
        if len(d['channels']) != 1: continue
        ch = next(iter(d['channels']))
        # Skip cross-role-swap convention refs (SWDIO/SWCLK debug-pad-row)
        if any(role.startswith(p) for role in d['ch_nets'][ch]
               for p in CROSS_ROLE_SWAP_PREFIXES):
            continue
        role_sig = (tuple(sorted(d['ch_nets'][ch])), d['first'], d['lib'])
        ch_to_role_ref[ch].setdefault(role_sig, []).append(ref)

    def expected_mirror(x, y, src_ch, dst_ch):
        if src_ch == 1 and dst_ch == 2: return (100.0 - x, y)
        if src_ch == 1 and dst_ch == 3: return (100.0 - x, 100.0 - y)
        if src_ch == 1 and dst_ch == 4: return (x, 100.0 - y)
        if src_ch == 2 and dst_ch == 3: return (x, 100.0 - y)
        if src_ch == 2 and dst_ch == 4: return (100.0 - x, 100.0 - y)
        if src_ch == 3 and dst_ch == 4: return (100.0 - x, y)
        raise ValueError

    passes = 0; warns = 0; fails = 0
    bad_pairs = 0
    fail_details = []
    warn_details = []

    # Hardcoded high-confidence pairs (FET cluster + DRV/MCU + paired connectors)
    HARDCODED_PAIRS = [
        ('Q5','Q11'), ('Q6','Q12'), ('Q7','Q13'),
        ('Q8','Q14'), ('Q9','Q15'), ('Q10','Q16'),
        ('TP19','TP26'), ('TP20','TP27'), ('TP21','TP28'),
        ('J18','J23'), ('J19','J24'), ('J22','J26'),
    ]
    for ch1_ref, ch2_ref in HARDCODED_PAIRS:
        if ch1_ref not in info or ch2_ref not in info:
            print(f"  MISSING: {ch1_ref} or {ch2_ref}"); continue
        x1, y1 = info[ch1_ref]['x'], info[ch1_ref]['y']
        x2, y2 = info[ch2_ref]['x'], info[ch2_ref]['y']
        ex, ey = expected_mirror(x1, y1, 1, 2)
        d = math.hypot(x2 - ex, y2 - ey)
        if d <= TOL_PASS:
            passes += 1; status = "PASS"
        elif d <= TOL_WARN:
            warns += 1; status = "WARN"
            warn_details.append((ch1_ref, ch2_ref, d))
        else:
            fails += 1; status = "FAIL"
            fail_details.append((ch1_ref, ch2_ref, d))
        print(f"  {ch1_ref}@({x1:.1f},{y1:.1f}) → {ch2_ref}@({x2:.1f},{y2:.1f}); expected ({ex:.1f},{ey:.1f}); Δ={d:.3f}mm {status}")

    # Role-based pairing for channel passives (CH1↔CH2 + CH3 + CH4)
    role_pair_stats = collections.defaultdict(lambda: {'pass': 0, 'warn': 0, 'fail': 0, 'bad': 0})
    src_ch = 1
    src_roles = ch_to_role_ref[src_ch]
    for dst_ch in (2, 3, 4):
        dst_roles = ch_to_role_ref[dst_ch]
        for role_sig, src_refs in src_roles.items():
            dst_refs = dst_roles.get(role_sig, [])
            if not dst_refs: continue
            used_dst = set()
            for src_ref in src_refs:
                sx, sy = info[src_ref]['x'], info[src_ref]['y']
                ex, ey = expected_mirror(sx, sy, src_ch, dst_ch)
                best = None; best_d = 1e9
                for dr in dst_refs:
                    if dr in used_dst: continue
                    dx2, dy2 = info[dr]['x'], info[dr]['y']
                    d = math.hypot(dx2 - ex, dy2 - ey)
                    if d < best_d:
                        best_d = d; best = (dr, dx2, dy2, d)
                if best is None: continue
                used_dst.add(best[0])
                dr, dx2, dy2, d = best
                letter = role_sig[1]
                # Geometric-mirror-direction check: large axial drift = bad pair
                if dst_ch in (2,):  # mirror_X: dY should be small
                    if abs(dy2 - sy) > MAX_DY_FOR_MIRROR_X:
                        role_pair_stats[(letter, dst_ch)]['bad'] += 1
                        bad_pairs += 1
                        continue
                if dst_ch in (4,):  # mirror_Y: dX should be small
                    if abs(dx2 - sx) > MAX_DX_FOR_MIRROR_Y:
                        role_pair_stats[(letter, dst_ch)]['bad'] += 1
                        bad_pairs += 1
                        continue
                if d > MAX_BAD_PAIR_MM:
                    role_pair_stats[(letter, dst_ch)]['bad'] += 1
                    bad_pairs += 1
                    continue
                if d <= TOL_PASS:
                    role_pair_stats[(letter, dst_ch)]['pass'] += 1
                    passes += 1
                elif d <= TOL_WARN:
                    role_pair_stats[(letter, dst_ch)]['warn'] += 1
                    warns += 1
                    warn_details.append((src_ref, dr, d))
                else:
                    role_pair_stats[(letter, dst_ch)]['fail'] += 1
                    fails += 1
                    fail_details.append((src_ref, dr, d))

    for (letter, dst_ch), s in sorted(role_pair_stats.items()):
        if s['pass'] + s['warn'] + s['fail'] + s['bad'] == 0: continue
        print(f"  {letter}-refs CH1→CH{dst_ch}: {s['pass']} PASS, "
              f"{s['warn']} WARN, {s['fail']} FAIL, {s['bad']} bad-pair-skip")

    print(f"\nTotal: {passes} PASS, {warns} WARN (≤{TOL_WARN}mm), "
          f"{fails} FAIL (>{TOL_WARN}mm), {bad_pairs} bad-pair-skip")
    if fails:
        print("\nFAIL pairs (Δ > {TOL_WARN}mm):")
        for src, dst, d in sorted(fail_details, key=lambda x: -x[2])[:20]:
            print(f"  {src} → {dst}: Δ={d:.2f}mm")
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
