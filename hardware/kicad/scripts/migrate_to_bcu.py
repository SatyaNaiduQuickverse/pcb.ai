#!/usr/bin/env python3
"""migrate_to_bcu.py — PR-A4-integrate amendment 5j Path D.

Per master directive: move debug TPs + generic pull-ups/downs from F.Cu to
B.Cu to relieve top-side density (4.5 components/cm² → target 3.5). Frees
top space for 7 IC decoupling caps + lets aggressive resolver clear
remaining 88 diff-net overlaps.

Migration list:
  Debug TPs (non-motor): TP1-TP18, TP22-TP25, TP29, TP30, TP31, TP32,
    TP36-TP39, TP43, TP44. Motor terminals TP19-21/26-28/33-35/40-42
    STAY F.Cu (they're solder pads for motor wires).
  Generic pulls: R16, R17, R26, R65, R78, R81, R154, R157, R179
    (anchored to +3V3 / GND signals — slow, R25 doesn't apply).

Preserves channel mirror symmetry: by updating layer in CH234_PASSIVES dict,
mirror_ch1_to_ch234.py will propagate the layer change to CH2/CH3/CH4 partners.

Updates both ch234_passives_dict.py (for auto-anchored entries) and
place_board.py S4_CH1_POSITIONS / S1_POSITIONS / etc. (for hand-placed).
"""
import re
from pathlib import Path

CH234_DICT = Path("hardware/kicad/scripts/ch234_passives_dict.py")
PLACE_BOARD = Path("hardware/kicad/scripts/place_board.py")

MOTOR_TPS = {'TP19','TP20','TP21','TP26','TP27','TP28',
             'TP33','TP34','TP35','TP40','TP41','TP42'}
PULL_LIST = {'R16','R17','R26','R65','R78','R81','R154','R157','R179'}


def should_migrate(ref):
    if ref.startswith('TP') and ref not in MOTOR_TPS:
        return True
    if ref in PULL_LIST:
        return True
    return False


def patch_dict_block(text, dict_name):
    """Within a dict block, replace layer 'F.Cu' with 'B.Cu' for migration refs."""
    pat = re.compile(rf"(^{dict_name}\s*=\s*\{{)(.*?)(\n\}})", re.DOTALL | re.MULTILINE)
    m = pat.search(text)
    if not m:
        return text, 0
    body = m.group(2)
    count = 0
    def replace_entry(em):
        nonlocal count
        ref = em.group(1)
        layer = em.group(4)
        if should_migrate(ref) and layer == 'F.Cu':
            count += 1
            return f"'{ref}': ({em.group(2)}, {em.group(3)}, 'B.Cu', {em.group(5)})"
        return em.group(0)
    body2 = re.sub(r"'([A-Z]+\d+)'\s*:\s*\(\s*([\d.]+),\s*([\d.]+),\s*'([^']+)',\s*([\d.]+)\)",
                   replace_entry, body)
    return text[:m.start()] + m.group(1) + body2 + m.group(3) + text[m.end():], count


def main():
    # CH234 dict
    txt = CH234_DICT.read_text()
    new_txt, n_ch234 = patch_dict_block(txt, "CH234_PASSIVES")
    if n_ch234:
        CH234_DICT.write_text(new_txt)
    print(f"CH234_PASSIVES: migrated {n_ch234} entries to B.Cu")

    # place_board dicts
    pb_txt = PLACE_BOARD.read_text()
    total_pb = 0
    for name in ('S1_POSITIONS', 'S2_POSITIONS', 'S3_POSITIONS',
                 'S5_POSITIONS', 'S6_POSITIONS', 'S4_CH1_POSITIONS'):
        pb_txt, n = patch_dict_block(pb_txt, name)
        if n:
            print(f"  {name}: {n} migrations")
        total_pb += n
    PLACE_BOARD.write_text(pb_txt)
    print(f"place_board.py: migrated {total_pb} entries to B.Cu")
    print(f"TOTAL: {n_ch234 + total_pb} components moved to B.Cu")


if __name__ == "__main__":
    main()
