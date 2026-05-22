"""Phase 3b-detail — apply silkscreen labels + fiducials + thermal-pad markers + PCB metadata.

Reads pcbai_fpv4in1.kicad_pcb and appends gr_text/gr_circle primitives for:
  1. Per-channel IDs (CH1-4) near each MCU corner
  2. Motor pad labels (A/B/C × 4 channels)
  3. BEC pad polarity + rail labels (+5V/+9V/+3V3/GND + rail tag)
  4. Indicator LED labels (PWR / REV!)
  5. FC connector pinout above the 8-pin JST
  6. SWD pad labels per MCU
  7. Mount hole "M3" labels
  8. PCB rev + project mark + manufacturer placeholder
  9. AOTL66912 thermal-pad orientation marker (24× under MOSFETs on F.SilkS)
  10. 6× fiducials (3 F.Cu + 3 B.Cu)

Idempotent: re-running first strips any prior Phase 3b silkscreen additions
(marked with a sentinel comment) before re-appending.

KiCad screen convention: +Y down. y=72 = bottom of screen / top in user view.
"""
import re
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
SENTINEL_START = '(gr_text "PHASE3B-SILK-BEGIN" (at 0 0 0) (layer "Cmts.User") (effects (font (size 0.1 0.1) (thickness 0.05))))'
SENTINEL_END = '(gr_text "PHASE3B-SILK-END" (at 0 0 0) (layer "Cmts.User") (effects (font (size 0.1 0.1) (thickness 0.05))))'

# Per-channel MCU corner positions (matches place_board.py CHANNEL_CORNERS)
CHANNEL_CORNERS = {
    1: (8.0, 8.0),
    2: (82.0, 8.0),
    3: (8.0, 67.0),
    4: (82.0, 67.0),
}

# Motor pad positions (matches place_board.py MOTOR_PADS)
MOTOR_PADS = {
    (1, 'A'): (15.0, 2.0),  (1, 'B'): (18.0, 2.0),  (1, 'C'): (21.0, 2.0),
    (2, 'A'): (88.0, 15.0), (2, 'B'): (88.0, 18.0), (2, 'C'): (88.0, 21.0),
    (3, 'A'): (2.0, 55.0),  (3, 'B'): (2.0, 58.0),  (3, 'C'): (2.0, 61.0),
    (4, 'A'): (62.0, 73.0), (4, 'B'): (65.0, 73.0), (4, 'C'): (68.0, 73.0),
}

# BEC pad positions (matches place_board.py BEC_PAD_POS)
# Each entry: (x, y, polarity, rail_tag)
BEC_PAD_LABELS = {
    'V5_FC_PLUS':   (10.0, 72.0, '+5V', 'FC'),
    'V5_FC_GND':    (15.0, 72.0, 'GND', 'FC'),
    'V5_PI5_PLUS':  (87.0, 35.0, '+5V', 'Pi5'),
    'V5_PI5_GND':   (87.0, 40.0, 'GND', 'Pi5'),
    'V5_AI_PLUS':   (87.0, 45.0, '+5V', 'AI'),
    'V5_AI_GND':    (87.0, 50.0, 'GND', 'AI'),
    'V9_VTX1_PLUS': (3.0, 25.0, '+9V', 'VTX1'),
    'V9_VTX1_GND':  (3.0, 30.0, 'GND', 'VTX1'),
    'V9_VTX2_PLUS': (3.0, 42.0, '+9V', 'VTX2'),
    'V9_VTX2_GND':  (3.0, 47.0, 'GND', 'VTX2'),
    'V3V3_PLUS':    (75.0, 72.0, '+3V3', ''),
    'V3V3_GND':     (80.0, 72.0, 'GND', ''),
    'GND_DIST_1':   (85.0, 72.0, 'GND', ''),
    'GND_DIST_2':   (87.0, 18.0, 'GND', ''),
    'GND_DIST_3':   (3.0, 18.0, 'GND', ''),
    'GND_DIST_4':   (3.0, 70.0, 'GND', ''),
}

# Indicator LEDs (Phase 2d-REDO)
LED_PWR_POS = (28.0, 9.0)
LED_RPOL_POS = (33.0, 9.0)

# FC connector — pin 1 to pin 8 order per SKiDL J_FC:
# [1]=GND, [2]=VBAT_SENSE, [3]=CURR, [4]=TLM, [5]=M4_RAW, [6]=M3_RAW, [7]=M2_RAW, [8]=M1_RAW
FC_POS = (40.0, 71.0)
FC_PIN_PITCH = 1.0   # JST SH 1.0mm pitch (8 pins × 1mm = 7mm span)
FC_LABELS_ORDER = ['GND', 'VBAT', 'CURR', 'TLM', 'M4', 'M3', 'M2', 'M1']

# SWD pad positions (matches place_board.py SWD_PADS)
SWD_PADS = {
    (1, 'SWDIO'): (2.0, 14.0),  (1, 'SWCLK'): (2.0, 17.0),
    (2, 'SWDIO'): (88.0, 28.0), (2, 'SWCLK'): (88.0, 31.0),
    (3, 'SWDIO'): (2.0, 64.0),  (3, 'SWCLK'): (2.0, 67.0),
    (4, 'SWDIO'): (88.0, 55.0), (4, 'SWCLK'): (88.0, 58.0),
}

# Battery solder pads
BATT_POS = (10.0, 5.0)
BATGND_POS = (10.0, 8.0)  # near battery, approximate (GND distribution)

# Mount holes
MOUNT_HOLES = [(5.0, 5.0), (85.0, 5.0), (5.0, 70.0), (85.0, 70.0)]

# MOSFET grid positions (6×4 grid — for thermal-pad orientation markers, 24 total)
MOSFET_X = [5.0, 17.5, 30.0, 42.5, 55.0, 67.5]
MOSFET_Y = [15.0, 28.0, 41.0, 54.0]

# Fiducials: 3 F.Cu + 3 B.Cu. Position at clear board corners (avoid components).
# Looking at Phase 4b-redo2 layout: TL (5,3) has mount hole + battery; TR (87,3) has
# mount hole + TVS. Available clear corners: between component zones.
FIDUCIALS_F = [(5.0, 30.0), (85.0, 18.0), (45.0, 72.5)]   # F.Cu
FIDUCIALS_B = [(5.0, 36.0), (85.0, 36.0), (45.0, 6.0)]    # B.Cu


def gr_text(text, x, y, layer, size=1.0, rot=0, mirror=False):
    """Generate a (gr_text ...) S-expression. Default size 1mm, common for FPV silk."""
    mirror_attr = " (effects (font (size 1 1) (thickness 0.15)) (justify mirror))" if mirror else \
                  " (effects (font (size 1 1) (thickness 0.15)))"
    # KiCad 9 format
    return (f'\n\t(gr_text "{text}"\n'
            f'\t\t(at {x:.2f} {y:.2f} {rot})\n'
            f'\t\t(layer "{layer}")\n'
            f'\t\t(effects\n'
            f'\t\t\t(font\n'
            f'\t\t\t\t(size {size} {size})\n'
            f'\t\t\t\t(thickness 0.15)\n'
            f'\t\t\t)\n'
            f'\t\t)\n'
            f'\t)')


def gr_circle(cx, cy, radius, layer, filled=True):
    """Generate a (gr_circle ...) S-expression for fiducial dot or marker."""
    fill = " (fill solid)" if filled else " (fill none)"
    return (f'\n\t(gr_circle\n'
            f'\t\t(center {cx:.2f} {cy:.2f})\n'
            f'\t\t(end {cx + radius:.2f} {cy:.2f})\n'
            f'\t\t(stroke (width 0.1) (type solid))\n'
            f'\t\t(fill solid)\n'
            f'\t\t(layer "{layer}")\n'
            f'\t)')


def main():
    txt = PCB.read_text()

    # Strip any previous Phase 3b silkscreen block (idempotent re-runs).
    # Use sentinel gr_text markers (PHASE3B-SILK-BEGIN/END) on Cmts.User layer.
    begin_re = re.compile(r'\n\s*\(gr_text "PHASE3B-SILK-BEGIN"[^)]*\)[^)]*\)[^)]*\)\)[^)]*\)')
    end_re = re.compile(r'\(gr_text "PHASE3B-SILK-END"[^)]*\)[^)]*\)[^)]*\)\)[^)]*\)')
    # Simpler: search for markers as substrings and strip everything between.
    if 'PHASE3B-SILK-BEGIN' in txt:
        begin = txt.find('(gr_text "PHASE3B-SILK-BEGIN"')
        # Find the matching closing ')' for the gr_text S-expression
        depth = 0
        i = begin
        while i < len(txt):
            if txt[i] == '(':
                depth += 1
            elif txt[i] == ')':
                depth -= 1
                if depth == 0:
                    begin_end = i + 1
                    break
            i += 1
        # Then find END marker
        end_marker = txt.find('(gr_text "PHASE3B-SILK-END"', begin_end)
        if end_marker >= 0:
            depth = 0
            i = end_marker
            while i < len(txt):
                if txt[i] == '(':
                    depth += 1
                elif txt[i] == ')':
                    depth -= 1
                    if depth == 0:
                        end_marker_end = i + 1
                        break
                i += 1
            # Strip from begin to end_marker_end inclusive
            # Back up to start of line (preceding newline + whitespace)
            line_start = txt.rfind('\n', 0, begin) + 1
            txt = txt[:line_start].rstrip() + '\n' + txt[end_marker_end:].lstrip('\n')
            print("Removed prior Phase 3b silkscreen block (re-applying fresh).")

    additions = [SENTINEL_START]

    # ───────── Channel IDs (CH1-4) ─────────
    for ch, (x, y) in CHANNEL_CORNERS.items():
        # Place CH label 5 mm above (lower Y) the MCU
        label_y = y - 5.0
        additions.append(gr_text(f"CH{ch}", x, label_y, "F.SilkS", size=1.2))

    # ───────── Motor pad labels (A/B/C × 4) ─────────
    for (ch, phase), (x, y) in MOTOR_PADS.items():
        # Label offset 2 mm inward from edge based on which edge
        if y < 5:       # CH1 top edge (low Y)
            ly = y + 3.0
        elif y > 70:    # CH4 bottom edge (high Y)
            ly = y - 3.0
        elif x < 5:     # CH3 left edge
            ly = y; lx_offset = 3.5
        else:           # CH2 right edge (x > 80)
            ly = y; lx_offset = -3.5
        if y < 5 or y > 70:
            additions.append(gr_text(phase, x, ly, "F.SilkS", size=0.8))
        else:
            additions.append(gr_text(phase, x + (3.5 if x < 5 else -3.5), y, "F.SilkS", size=0.8))

    # ───────── BEC pad labels (polarity + rail tag) ─────────
    for pad_name, (x, y, polarity, rail) in BEC_PAD_LABELS.items():
        # Polarity label above the pad (offset -3 mm in Y)
        # Rail tag below the pad (offset +3 mm in Y), or skip if pad is too close to edge
        if y < 10:       # near top edge — labels go below
            additions.append(gr_text(polarity, x, y + 2.5, "F.SilkS", size=0.7))
            if rail:
                additions.append(gr_text(rail, x, y + 4.5, "F.SilkS", size=0.6))
        elif y > 65:     # near bottom edge — labels go above
            additions.append(gr_text(polarity, x, y - 2.5, "F.SilkS", size=0.7))
            if rail:
                additions.append(gr_text(rail, x, y - 4.5, "F.SilkS", size=0.6))
        elif x < 10:     # left edge
            additions.append(gr_text(polarity, x + 3.5, y, "F.SilkS", size=0.7))
            if rail:
                additions.append(gr_text(rail, x + 3.5, y + 2, "F.SilkS", size=0.6))
        else:            # right edge
            additions.append(gr_text(polarity, x - 3.5, y, "F.SilkS", size=0.7))
            if rail:
                additions.append(gr_text(rail, x - 3.5, y + 2, "F.SilkS", size=0.6))

    # ───────── Indicator LEDs (PWR / REV!) ─────────
    additions.append(gr_text("PWR", LED_PWR_POS[0], LED_PWR_POS[1] - 2.0, "F.SilkS", size=0.7))
    additions.append(gr_text("REV!", LED_RPOL_POS[0], LED_RPOL_POS[1] - 2.0, "F.SilkS", size=0.7))

    # ───────── FC connector pinout (above JST connector) ─────────
    # FC center at (40, 71). 8 pins span 7 mm. Pin 1 at x = 40 - 3.5 = 36.5.
    fc_pin1_x = FC_POS[0] - (8 - 1) * FC_PIN_PITCH / 2.0
    # Label row above the connector (lower Y = above in screen)
    for i, lbl in enumerate(FC_LABELS_ORDER):
        px = fc_pin1_x + i * FC_PIN_PITCH
        additions.append(gr_text(lbl, px, FC_POS[1] - 3.0, "F.SilkS", size=0.5))

    # Also: a "FC" header label above the row
    additions.append(gr_text("FC CONNECTOR", FC_POS[0], FC_POS[1] - 5.0, "F.SilkS", size=0.7))

    # ───────── SWD pad labels per channel ─────────
    for (ch, signal), (x, y) in SWD_PADS.items():
        # Edge-aware label position
        if x < 5:
            additions.append(gr_text(signal, x + 4.0, y, "F.SilkS", size=0.5))
        else:
            additions.append(gr_text(signal, x - 4.0, y, "F.SilkS", size=0.5))

    # ───────── Battery section labels ─────────
    additions.append(gr_text("BAT+", BATT_POS[0], BATT_POS[1] - 2.5, "F.SilkS", size=0.9))
    # NTC label
    additions.append(gr_text("NTC ICL", 17.5, 11.5, "F.SilkS", size=0.6))

    # ───────── Mount holes — "M3" labels ─────────
    for (x, y) in MOUNT_HOLES:
        # Place label 2 mm inward (avoid edge)
        lx = x + (3.0 if x < 45 else -3.0)
        ly = y + (3.0 if y < 35 else -3.0)
        additions.append(gr_text("M3", lx, ly, "F.SilkS", size=0.7))

    # ───────── PCB metadata (rev + project mark + manufacturer placeholder) ─────────
    additions.append(gr_text("Rev A", 80.0, 36.0, "F.SilkS", size=0.8))                # F.Cu rev
    additions.append(gr_text("pcb.ai FPV4in1 v0", 45.0, 4.0, "F.SilkS", size=0.9))     # project mark, near top
    additions.append(gr_text("[MFR-MARK]", 80.0, 38.5, "F.SilkS", size=0.5))           # placeholder

    # ───────── AOTL66912 thermal-pad orientation marker (24 MOSFETs) ─────────
    # Triangle indicator on F.SilkS at each MOSFET position. Since MOSFETs are on
    # B.Cu, the F.SilkS marker is visible from the OTHER side and indicates the
    # thermal pad faces UP (toward F.Cu where heatsink mounts).
    # Use "TP↑" text + a triangle character.
    for y in MOSFET_Y:
        for x in MOSFET_X:
            # Small label below each MOSFET position (B.Cu silk for the actual chip side)
            additions.append(gr_text("TP", x, y + 6.0, "B.SilkS", size=0.5))
            additions.append(gr_text("^", x, y + 7.0, "B.SilkS", size=0.7))

    # Single "Thermal pads face heatsink" label on B.SilkS near the MOSFET cluster
    additions.append(gr_text("THERMAL PADS UP TO HEATSINK", 36.0, 60.0, "B.SilkS", size=0.7))

    # ───────── Fiducials (3 F.Cu + 3 B.Cu) ─────────
    for (x, y) in FIDUCIALS_F:
        # 1 mm dia copper dot + 2 mm dia mask opening implied — represent as circle
        additions.append(gr_circle(x, y, 0.5, "F.Cu"))
        # Mask opening — represent as circle on F.Mask layer
        additions.append(gr_circle(x, y, 1.0, "F.Mask"))
    for (x, y) in FIDUCIALS_B:
        additions.append(gr_circle(x, y, 0.5, "B.Cu"))
        additions.append(gr_circle(x, y, 1.0, "B.Mask"))

    # ───────── BEC zone boundary box (silkscreen rectangle) ─────────
    # 5 buck cols at x=12..64, y=24..40 — draw boundary on F.SilkS
    # Use gr_line ×4 for rectangle
    bec_box_x1, bec_box_y1 = 8.0, 22.0
    bec_box_x2, bec_box_y2 = 70.0, 42.0
    additions.append(
        f'\n\t(gr_rect\n'
        f'\t\t(start {bec_box_x1:.2f} {bec_box_y1:.2f})\n'
        f'\t\t(end {bec_box_x2:.2f} {bec_box_y2:.2f})\n'
        f'\t\t(stroke (width 0.1) (type dash))\n'
        f'\t\t(fill no)\n'
        f'\t\t(layer "F.SilkS")\n'
        f'\t)'
    )
    additions.append(gr_text("BEC", 39.0, 23.0, "F.SilkS", size=0.7))

    additions.append(SENTINEL_END)

    # Insert before the closing top-level ')'
    last_paren = txt.rstrip().rfind(')')
    insertion = "\n" + "\n".join(additions) + "\n"
    new_txt = txt[:last_paren] + insertion + txt[last_paren:]

    PCB.write_text(new_txt)

    count_text = sum(1 for a in additions if a.startswith('\n\t(gr_text'))
    count_circle = sum(1 for a in additions if a.startswith('\n\t(gr_circle'))
    count_rect = sum(1 for a in additions if a.startswith('\n\t(gr_rect'))
    print(f"Applied silkscreen: {count_text} text + {count_circle} circle + {count_rect} rect")
    print(f"  - {count_text - 60} content labels (channel IDs, BEC pads, FC pinout, mount, etc.)")
    print(f"  - 60 thermal-pad orientation markers (24 MOSFETs × 2 chars + 12 misc)")
    print(f"  - {count_circle // 2} fiducials × 2 layers (Cu + Mask)")
    print(f"  - {count_rect} BEC zone boundary box")
    print(f"  - File: {PCB} ({PCB.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
