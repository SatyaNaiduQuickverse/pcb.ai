#!/usr/bin/env python3
"""mirror_ch1_to_ch2.py — PR-CH2 2026-05-23: pure X-mirror transform of CH1
channel passives to CH2 counterparts.

For each CH1 passive (R/C/D) with CH1-tagged net, find its CH2 counterpart
(same letter, paired by ref-number index per channel), and place at
mirror_X(50) of CH1 position.

Updates ch234_passives_dict.py with CH2 channel passive positions.
"""
import pcbnew, re, sys, collections
from pathlib import Path

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
CH234_DICT = Path("hardware/kicad/scripts/ch234_passives_dict.py")
PLACE_BOARD = Path("hardware/kicad/scripts/place_board.py")

# Read CH1 passive positions from place_board.py S4_CH1_POSITIONS dict
def parse_place_board_dict(name):
    txt = PLACE_BOARD.read_text()
    m = re.search(rf"{name}\s*=\s*\{{(.*?)\n\}}", txt, re.DOTALL)
    if not m: return {}
    out = {}
    for em in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", m.group(1)):
        out[em.group(1)] = (float(em.group(2)), float(em.group(3)), em.group(4), float(em.group(5)))
    return out

s4_ch1 = parse_place_board_dict("S4_CH1_POSITIONS")
print(f"S4_CH1: {len(s4_ch1)} entries")
# Also read CH234 dict for existing channel passive positions (CH1's auto-anchored)
ch234 = {}
if CH234_DICT.exists():
    txt = CH234_DICT.read_text()
    m = re.search(r"CH234_PASSIVES\s*=\s*\{(.*?)\n\}", txt, re.DOTALL)
    if m:
        for em in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", m.group(1)):
            ch234[em.group(1)] = (float(em.group(2)), float(em.group(3)), em.group(4), float(em.group(5)))
print(f"CH234 dict: {len(ch234)} entries")

# Build channel→letter→refs map from netlist
board = pcbnew.LoadBoard(PCB)
by_ch_letter = collections.defaultdict(lambda: collections.defaultdict(list))
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if not ref.startswith(('R','C','D')): continue
    for p in fp.Pads():
        if p.GetNet():
            nm = p.GetNet().GetNetname()
            m = re.search(r"_CH([1234])", nm)
            if m:
                ch = int(m.group(1))
                letter = ref[0]
                by_ch_letter[ch][letter].append(ref); break

def num(r): return int(re.match(r'[A-Z]+(\d+)', r).group(1))

# For each CH1 ref (sorted by ref-number), find paired CH2 ref by index
mirrors = {}  # CH2_ref → mirrored_position
for letter in 'RCD':
    ch1_refs = sorted(by_ch_letter[1][letter], key=num)
    ch2_refs = sorted(by_ch_letter[2][letter], key=num)
    for i, ch1_ref in enumerate(ch1_refs):
        if i >= len(ch2_refs): break
        ch2_ref = ch2_refs[i]
        # Look up CH1 position from S4_CH1 dict OR ch234 dict
        ch1_pos = s4_ch1.get(ch1_ref) or ch234.get(ch1_ref)
        if not ch1_pos: continue
        x, y, layer, rot = ch1_pos
        # Mirror_X(50): X' = 100 - X
        nx = 100.0 - x
        ny = y
        mirrors[ch2_ref] = (round(nx, 2), round(ny, 2), layer, rot)

print(f"Mirrored CH2 placements computed: {len(mirrors)}")

# Update ch234 dict: REMOVE all CH2 channel passive entries from auto-anchor,
# then add mirror-positions. This prevents auto-anchored CH2 placements from
# conflicting with mirrored ones.
ch2_passive_refs = set()
for letter in 'RCD':
    ch2_passive_refs.update(by_ch_letter[2][letter])
new_ch234 = {ref: pos for ref, pos in ch234.items() if ref not in ch2_passive_refs}
for ref, pos in mirrors.items():
    new_ch234[ref] = pos

with open(CH234_DICT, "w") as f:
    f.write('"""Auto-anchored + CH2-mirrored channel passive positions.\nPR-CH2 2026-05-23: CH2 channel passives = mirror_X(50) of CH1.\n"""\n')
    f.write("CH234_PASSIVES = {\n")
    for ref in sorted(new_ch234.keys()):
        x, y, layer, rot = new_ch234[ref]
        f.write(f"    '{ref}': ({x:.2f}, {y:.2f}, '{layer}', {rot:.1f}),\n")
    f.write("}\n")
print(f"Wrote {len(new_ch234)} entries to {CH234_DICT}")
