#!/usr/bin/env python3
"""verify_spec_diff.py — PR-CH2 2026-05-23: verify CH2 = mirror_X(50) of CH1.
Per master R20 spec-vs-placement gate (≤0.5mm tolerance)."""
import pcbnew, re, sys, math, collections
b = pcbnew.LoadBoard("hardware/kicad/pcbai_fpv4in1.kicad_pcb")
# Build by-letter dict per channel
by_ch_letter = collections.defaultdict(lambda: collections.defaultdict(list))
for fp in b.GetFootprints():
    ref = fp.GetReference()
    for p in fp.Pads():
        if p.GetNet():
            m = re.search(r"_CH([1234])", p.GetNet().GetNetname())
            if m:
                ch = int(m.group(1))
                by_ch_letter[ch][ref[0]].append(ref); break

def num(r): return int(re.match(r'[A-Z]+(\d+)', r).group(1))

# Get positions
pos = {fp.GetReference(): (fp.GetPosition().x/1e6, fp.GetPosition().y/1e6) for fp in b.GetFootprints()}

# Check CH1↔CH2 FET pairs
fet_pairs = [('Q5','Q11'), ('Q6','Q12'), ('Q7','Q13'), ('Q8','Q14'), ('Q9','Q15'), ('Q10','Q16'),
             ('TP19','TP26'), ('TP20','TP27'), ('TP21','TP28'),
             ('J18','J23'), ('J19','J24'), ('J20','J25'), ('J21','J27'), ('J22','J26'),
             ('U2','U5'), ('U3','U6'), ('U4','U7'),
             ('D15','D16'), ('D19','D20'), ('D33','D48'),
             ('TH1','TH2'), ('R56','R94'), ('R57','R95'), ('R58','R96')]
TOL = 0.5
fails = 0; passes = 0
for ch1_ref, ch2_ref in fet_pairs:
    if ch1_ref not in pos or ch2_ref not in pos:
        print(f"  MISSING: {ch1_ref} or {ch2_ref}"); continue
    x1, y1 = pos[ch1_ref]
    x2, y2 = pos[ch2_ref]
    ex, ey = 100.0 - x1, y1
    d = math.hypot(x2 - ex, y2 - ey)
    status = "PASS" if d <= TOL else "FAIL"
    if status == "PASS": passes += 1
    else: fails += 1
    print(f"  {ch1_ref}@({x1:.1f},{y1:.1f}) → {ch2_ref}@({x2:.1f},{y2:.1f}); expected ({ex:.1f},{ey:.1f}); Δ={d:.3f}mm {status}")

# Channel passive pair check (index-based per letter)
for letter in 'RCD':
    ch1_refs = sorted(by_ch_letter[1][letter], key=num)
    ch2_refs = sorted(by_ch_letter[2][letter], key=num)
    pair_fails = 0
    for i, ch1_ref in enumerate(ch1_refs):
        if i >= len(ch2_refs): break
        ch2_ref = ch2_refs[i]
        if ch1_ref not in pos or ch2_ref not in pos: continue
        x1, y1 = pos[ch1_ref]; x2, y2 = pos[ch2_ref]
        ex, ey = 100.0 - x1, y1
        d = math.hypot(x2 - ex, y2 - ey)
        if d > TOL: pair_fails += 1
        else: passes += 1
    if pair_fails > 0:
        fails += pair_fails
        print(f"  {letter}-refs CH1↔CH2 pairs: {pair_fails} FAIL")
    else:
        print(f"  {letter}-refs CH1↔CH2 pairs: ALL PASS ({len(ch1_refs)} pairs)")

print(f"\nTotal: {passes} PASS, {fails} FAIL")
sys.exit(0 if fails == 0 else 1)
