#!/usr/bin/env python3
"""mirror_ch1_to_ch234.py — Mirror CH1 passives + ICs to CH2/3/4 per locked
transforms:
  CH2 = mirror_X(50):    x'=100-x, y'=y
  CH3 = 180°-rot(50,50): x'=100-x, y'=100-y
  CH4 = mirror_Y(50):    x'=x, y'=100-y

Usage: python3 mirror_ch1_to_ch234.py [ch2|ch3|ch4|all]
"""
import pcbnew, re, sys, collections
from pathlib import Path

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
CH234_DICT = Path("hardware/kicad/scripts/ch234_passives_dict.py")
PLACE_BOARD = Path("hardware/kicad/scripts/place_board.py")

target_chs = sys.argv[1:] or ['all']
if 'all' in target_chs:
    target_chs = ['ch2', 'ch3', 'ch4']

TRANSFORMS = {
    'ch2': lambda x, y: (100.0 - x, y),
    'ch3': lambda x, y: (100.0 - x, 100.0 - y),
    'ch4': lambda x, y: (x, 100.0 - y),
}

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

ch234 = {}
if CH234_DICT.exists():
    txt = CH234_DICT.read_text()
    m = re.search(r"CH234_PASSIVES\s*=\s*\{(.*?)\n\}", txt, re.DOTALL)
    if m:
        for em in re.finditer(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)", m.group(1)):
            ch234[em.group(1)] = (float(em.group(2)), float(em.group(3)), em.group(4), float(em.group(5)))
print(f"CH234 dict: {len(ch234)} entries")

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
                ch = int(m.group(1)); letter = ref[0]
                by_ch_letter[ch][letter].append(ref); break

def num(r): return int(re.match(r'[A-Z]+(\d+)', r).group(1))

# For each target channel, compute mirrors from CH1
new_ch234 = dict(ch234)
for ch_name in target_chs:
    target_ch = {'ch2':2, 'ch3':3, 'ch4':4}[ch_name]
    transform = TRANSFORMS[ch_name]
    # Remove existing CH target passive entries (avoid auto-anchor conflicts)
    ch_passive_refs = set()
    for letter in 'RCD':
        ch_passive_refs.update(by_ch_letter[target_ch][letter])
    new_ch234 = {ref: pos for ref, pos in new_ch234.items() if ref not in ch_passive_refs}

    # Mirror CH1 passives → target_ch
    count = 0
    for letter in 'RCD':
        ch1_refs = sorted(by_ch_letter[1][letter], key=num)
        target_refs = sorted(by_ch_letter[target_ch][letter], key=num)
        for i, ch1_ref in enumerate(ch1_refs):
            if i >= len(target_refs): break
            target_ref = target_refs[i]
            ch1_pos = s4_ch1.get(ch1_ref) or ch234.get(ch1_ref)
            if not ch1_pos: continue
            x, y, layer, rot = ch1_pos
            nx, ny = transform(x, y)
            new_ch234[target_ref] = (round(nx, 2), round(ny, 2), layer, rot)
            count += 1
    print(f"  {ch_name}: {count} mirror positions computed")

with open(CH234_DICT, "w") as f:
    f.write(f'"""Auto-anchored + CH2/3/4 mirror channel positions.\n')
    f.write(f'PR-CH3 2026-05-23: pure transforms applied to CH1 reference.\n"""\n')
    f.write("CH234_PASSIVES = {\n")
    for ref in sorted(new_ch234.keys()):
        x, y, layer, rot = new_ch234[ref]
        f.write(f"    '{ref}': ({x:.2f}, {y:.2f}, '{layer}', {rot:.1f}),\n")
    f.write("}\n")
print(f"Wrote {len(new_ch234)} entries to {CH234_DICT}")
