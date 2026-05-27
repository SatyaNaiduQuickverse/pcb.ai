#!/usr/bin/env python3
"""inject_stackup.py — inject the LOCKED 10L dielectric stackup into a board.

WHY THIS EXISTS
---------------
The board carries the 10-copper-layer *stack* (the (layers ...) block from
setup_board.py), but it has NO `(setup (stackup ...))` block. The dielectric
heights — most critically the F.Cu→In1.Cu 0.10mm prepreg that the SW
commutation loop-L assumption is load-bearing on (OQ-014) — exist only as
human-readable comments in the layer descriptors. Without a real (stackup)
block, JLC builds a DEFAULT 1.6mm 10L stack with whatever dielectric split
their house process picks → the 0.10mm F.Cu→In1 reference is NOT guaranteed
→ the 0.1953nH/phase loop-L verdict (STEP 6) silently breaks.

An independent audit (2026-05-27) flagged this as a structural blindspot: every
gate validated against the *intended* stackup, none checked the board actually
carries one. This tool + the companion G_M17 gate (audit_stackup_dielectric.py)
close it.

WHAT IT DOES
------------
Adds a proper KiCad-9 `(setup (stackup ...))` block to a board file, encoding
the LOCKED 10L dielectric stack from docs/BOARD_INVARIANTS.md (OQ-014):

  F.Cu (1oz 35µm)
    prepreg 0.10mm   <- OQ-014 LOAD-BEARING (loop-L plane reference)
  In1.Cu (1oz)
    core    0.15mm
  In2.Cu (1oz)
    prepreg 0.075mm
  In3.Cu (1oz)
    core    0.15mm
  In4.Cu (1oz)
    prepreg 0.10mm
  In5.Cu (3oz 70µm, +VMOTOR)
    core    0.15mm
  In6.Cu (1oz)
    prepreg 0.075mm
  In7.Cu (1oz)
    core    0.15mm
  In8.Cu (1oz)
    prepreg 0.10mm   (symmetric to F.Cu side)
  B.Cu (1oz)

  Total ~1.6mm (9×35µm Cu + 1×70µm Cu + 4×100µm + 2×75µm prepreg + 4×150µm core).

IDEMPOTENT: any pre-existing (stackup ...) block is stripped first (paren-counting,
mirrors setup_board.py _strip_* pattern), then the canonical block is inserted as
the first child of (setup ...). Tracks / footprints / zones / vias are NOT touched.

USAGE
-----
  python3 inject_stackup.py <board.kicad_pcb>            # modify in place
  python3 inject_stackup.py <board.kicad_pcb> --output <out.kicad_pcb>

EXIT 0 on success, 1 on failure.
"""

import argparse
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────
# LOCKED 10L dielectric stack — docs/BOARD_INVARIANTS.md lines 15-30, OQ-014.
# Copper thickness: 1oz = 0.035mm (35µm), 3oz = 0.070mm (70µm) on In5 (+VMOTOR).
# Dielectric epsilon_r 4.5 (FR4 nominal), loss_tangent 0.02 (JLC FR4-7628 class).
# Copper layers and dielectric layers alternate top→bottom; the dielectric
# ordinal index ("dielectric N") increments in physical stack order.
# ──────────────────────────────────────────────────────────────────────────

CU_1OZ = 0.035   # mm
CU_3OZ = 0.070   # mm
EPS_R = 4.5
LOSS_TAN = 0.02

# (copper_layer_name, copper_thickness_mm), and the dielectric BELOW it
# (dielectric_type, dielectric_thickness_mm) — None below B.Cu (last copper).
# This is the single source of truth; the F.Cu→In1 0.10mm prepreg is the first
# dielectric entry and is the OQ-014 load-bearing value the G_M17 gate checks.
STACK = [
    ("F.Cu",  CU_1OZ, ("prepreg", 0.10)),    # OQ-014 LOAD-BEARING
    ("In1.Cu", CU_1OZ, ("core",    0.15)),
    ("In2.Cu", CU_1OZ, ("prepreg", 0.075)),
    ("In3.Cu", CU_1OZ, ("core",    0.15)),
    ("In4.Cu", CU_1OZ, ("prepreg", 0.10)),
    ("In5.Cu", CU_3OZ, ("core",    0.15)),    # +VMOTOR 3oz heavy-copper
    ("In6.Cu", CU_1OZ, ("prepreg", 0.075)),
    ("In7.Cu", CU_1OZ, ("core",    0.15)),
    ("In8.Cu", CU_1OZ, ("prepreg", 0.10)),    # symmetric to F.Cu side
    ("B.Cu",   CU_1OZ, None),
]

# Technical layers KiCad lists in the stackup after the copper/dielectric stack.
# Soldermask + silkscreen carry a thickness; paste does not. These are NOT
# load-bearing for any gate but KiCad's stackup editor round-trips them, so we
# emit them for a clean, GUI-editable stackup.
TECH_LAYERS = [
    ("F.SilkS", '(type "Top Silk Screen")'),
    ("F.Paste", '(type "Top Solder Paste")'),
    ("F.Mask",  '(type "Top Solder Mask")\n\t\t\t(thickness 0.01)'),
    ("B.Mask",  '(type "Bottom Solder Mask")\n\t\t\t(thickness 0.01)'),
    ("B.Paste", '(type "Bottom Solder Paste")'),
    ("B.SilkS", '(type "Bottom Silk Screen")'),
]


def build_stackup_block():
    """Return the canonical (stackup ...) S-expression, tab-indented to sit as
    a child of (setup ...) (which is itself indented one tab inside (kicad_pcb))."""
    lines = ["\t\t(stackup"]
    dielectric_ordinal = 0
    for cu_name, cu_thk, below in STACK:
        # Copper layer entry
        lines.append(f'\t\t\t(layer "{cu_name}"')
        lines.append(f'\t\t\t\t(type "copper")')
        lines.append(f'\t\t\t\t(thickness {cu_thk})')
        lines.append(f'\t\t\t)')
        # Dielectric below this copper (prepreg/core), if any
        if below is not None:
            d_type, d_thk = below
            dielectric_ordinal += 1
            type_desc = "Prepreg" if d_type == "prepreg" else "Core"
            lines.append(f'\t\t\t(layer "dielectric {dielectric_ordinal}"')
            lines.append(f'\t\t\t\t(type "{type_desc}")')
            lines.append(f'\t\t\t\t(thickness {d_thk})')
            lines.append(f'\t\t\t\t(material "FR4")')
            lines.append(f'\t\t\t\t(epsilon_r {EPS_R})')
            lines.append(f'\t\t\t\t(loss_tangent {LOSS_TAN})')
            lines.append(f'\t\t\t)')
    # Technical layers (silk / paste / mask)
    for tname, tbody in TECH_LAYERS:
        lines.append(f'\t\t\t(layer "{tname}"')
        for bl in tbody.split("\n"):
            lines.append(f'\t\t\t\t{bl}')
        lines.append(f'\t\t\t)')
    lines.append('\t\t\t(copper_finish "ENIG")')
    lines.append('\t\t\t(dielectric_constraints no)')
    lines.append('\t\t)')
    return "\n".join(lines)


def _strip_stackup(s):
    """Remove all (stackup ...) blocks via paren-counting. Mirror of
    setup_board.py _strip_edge_cuts / _strip_mounting_holes. Returns
    (new_text, count_stripped). Idempotent re-run safety."""
    out = []
    i = 0
    stripped = 0
    needle = "(stackup"
    while i < len(s):
        j = s.find(needle, i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        depth = 0
        k = j
        while k < len(s):
            if s[k] == '(':
                depth += 1
            elif s[k] == ')':
                depth -= 1
                if depth == 0:
                    break
            k += 1
        i = k + 1
        stripped += 1
        # consume trailing newline/whitespace so we don't leave a blank line
        while i < len(s) and s[i] in '\n\t ':
            i += 1
    return ''.join(out), stripped


def inject(txt):
    """Strip any existing stackup, then insert the canonical block as the first
    child of (setup ...). Returns new text. Raises if (setup not found."""
    txt, n = _strip_stackup(txt)
    if n:
        print(f"  Stripped {n} existing (stackup) block(s) — idempotent re-run")

    setup_idx = txt.find("(setup")
    if setup_idx < 0:
        raise SystemExit("FAIL: could not locate (setup ...) block — not a KiCad board?")
    # insertion point = right after "(setup\n"
    after = setup_idx + len("(setup")
    # consume the newline immediately following "(setup" so our block sits
    # on its own line as the first child
    nl = txt.find("\n", after)
    if nl < 0:
        raise SystemExit("FAIL: malformed (setup ...) block")
    block = build_stackup_block()
    new_txt = txt[:nl + 1] + block + "\n" + txt[nl + 1:]
    return new_txt


def main():
    ap = argparse.ArgumentParser(description="Inject locked 10L stackup into a KiCad board")
    ap.add_argument("board", help="path to .kicad_pcb")
    ap.add_argument("--output", help="write to this path instead of in place")
    args = ap.parse_args()

    board = Path(args.board)
    if not board.exists():
        print(f"FAIL: board not found: {board}", file=sys.stderr)
        return 1

    txt = board.read_text()
    n_tracks_before = txt.count("(segment ")
    n_vias_before = txt.count("(via ")
    n_fp_before = txt.count("(footprint ")
    n_zones_before = txt.count("(zone ")

    new_txt = inject(txt)

    out = Path(args.output) if args.output else board
    out.write_text(new_txt)

    n_tracks_after = new_txt.count("(segment ")
    n_vias_after = new_txt.count("(via ")
    n_fp_after = new_txt.count("(footprint ")
    n_zones_after = new_txt.count("(zone ")

    print(f"[inject_stackup] wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"  stackup block: {len(STACK)} copper + "
          f"{sum(1 for _, _, b in STACK if b)} dielectric + {len(TECH_LAYERS)} technical layers")
    print(f"  F.Cu→In1.Cu prepreg = {STACK[0][2][1]}mm (OQ-014 load-bearing)")
    total = sum(thk for _, thk, _ in STACK) + sum(b[1] for _, _, b in STACK if b)
    # ~1.435mm copper+dielectric per the BOARD_INVARIANTS per-pair table; JLC's
    # 1.6mm "standard" board adds soldermask + fab tolerance to reach 1.6mm nominal.
    print(f"  copper+dielectric thickness = {total:.3f}mm "
          f"(BOARD_INVARIANTS per-pair table; ~1.6mm nominal incl. mask+tolerance)")
    print(f"  content preserved: segments {n_tracks_before}->{n_tracks_after}  "
          f"vias {n_vias_before}->{n_vias_after}  footprints {n_fp_before}->{n_fp_after}  "
          f"zones {n_zones_before}->{n_zones_after}")

    # sanity: content counts must be unchanged
    if (n_tracks_before, n_vias_before, n_fp_before, n_zones_before) != \
       (n_tracks_after, n_vias_after, n_fp_after, n_zones_after):
        print("FAIL: board content count changed — refusing (stackup injection must be content-neutral)",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
