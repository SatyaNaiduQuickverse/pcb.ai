"""Phase 4a-restack-10L — board setup: 10-layer stack + Edge.Cuts + M3 mounting holes.

(Was 8L until 2026-05-26 Sai-locked 10L upgrade per docs/PHASE4A_RESTACK_10L_PROPOSAL.md.
Howard Johnson Sig Prop Ch.13.7 textbook remedy for QFN32 pin-remap-unavailable case;
Sai cost-OK directive cleared. Adds +1 signal layer + +1 GND plane = +50% routing capacity.)

Reads pcbai_fpv4in1.kicad_pcb (kinet2pcb output, 2-layer default),
upgrades to 8-layer per Phase 4a-restack-8L master directive (Task #37),
adds 100×85 Edge.Cuts outline, and 4× M3 mounting holes on a custom
90×75 pattern.

Board-size history:
  Phase 4a: 50×50 mm (initial square)
  Phase 4c-resume Option C: 85×70 mm rectangular (TOLL MOSFETs + bigger heatsink)
  Phase 4b-REDO2: 90×75 mm rectangular (BEC absorption per Sai's
    feedback-anchor-on-most-capable-reference rule — commercial-product class)
  Phase 4b-REDO3: 100×85 mm rectangular (signal-density Freerouting Pass #1 failed at 90×75)
  Phase 4a-restack-8L (this): 100×85 mm + 8-layer stackup (Phase 3-redo added
    +413 components requiring more signal-routing capacity per master D/S model)

Stackup specification (master Phase 4a-restack-10L directive 2026-05-26):
  Layer 0  F.Cu       signal  1oz   (top — HS FETs, MCU pads, J19 driver, connectors)
  Layer 1  In1.Cu     power   1oz   (GND plane — F.Cu reference, 0.10mm prepreg = OQ-014 LOCK)
  Layer 2  In2.Cu     signal  1oz   (NEW dedicated escape layer — J18/J19 fan-in destination)
  Layer 3  In3.Cu     power   1oz   (NEW GND plane — brackets In2 signals + In4 BEMF)
  Layer 4  In4.Cu     signal  1oz   (BEMF analog — shielded by In3 + In5, OQ-016 multi-layer shield)
  Layer 5  In5.Cu     power   3oz   (+VMOTOR plane — 280A burst, 3oz heavy-copper)
  Layer 6  In6.Cu     signal  1oz   (SW inner escape per OQ-017 In4 escape, was In4 in 8L)
  Layer 7  In7.Cu     power   1oz   (NEW GND plane — brackets In6 + In8 signals)
  Layer 8  In8.Cu     signal  1oz   (NEW signal — PWM_IN stragglers + low-current overflow)
  Layer 31 B.Cu       signal  1oz   (bottom — LS FETs, bulk caps, status LEDs)

5 signal layers (F.Cu, In2.Cu, In4.Cu, In6.Cu, In8.Cu, B.Cu) + 4 power planes
(In1.Cu GND, In3.Cu GND, In5.Cu +VMOTOR, In7.Cu GND) + dedicated BEMF (In4).
= 6 effective routing layers vs 4 in 8L = +50% routing capacity.

3oz copper layer: In5.Cu — for ≥280A continuous +VMOTOR bus (moved from In3 in 8L).
1oz copper layers: F.Cu, In1.Cu, In2.Cu, In3.Cu, In4.Cu, In6.Cu, In7.Cu, In8.Cu, B.Cu
— standard signal density at JLC SMT capability spec.

Stackup dielectric (locked, see docs/BOARD_INVARIANTS.md):
  F.Cu→In1.Cu prepreg = 0.10mm (LOAD-BEARING for loop-L plane reference, OQ-014 UNCHANGED)
  In1.Cu→In2.Cu core = 0.15mm
  In2.Cu→In3.Cu prepreg = 0.075mm
  In3.Cu→In4.Cu core = 0.15mm
  In4.Cu→In5.Cu prepreg = 0.10mm
  In5.Cu→In6.Cu core = 0.15mm
  In6.Cu→In7.Cu prepreg = 0.075mm
  In7.Cu→In8.Cu core = 0.15mm
  In8.Cu→B.Cu prepreg = 0.10mm (symmetric to F.Cu side)
Total board: 1.6mm 10L (JLC standard option, +\$1-2/board production).
"""

import re
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
BOARD_W = 100.0                # Phase 4b-REDO3: grew 90 → 100 for signal-density (Freerouting Pass #1 failed at 90×75)
BOARD_H = 100.0                # PR-A4-redo Sai-approved 2026-05-23: 95 → 100 per master Option-A refined; dimensional infeasibility of P=12 + 4 channels in 95mm. Mount holes shifted to (5,5)(95,5)(5,95)(95,95).
# Custom mount-hole pattern for 90×75 board: 80×65 spacing (5mm inset from each edge).
# No standard FPV stack pattern fits 90×75 — commercial-product-class custom pattern.
MOUNT_X_PAD = 5.0              # inset from board edges in X
MOUNT_Y_PAD = 5.0              # inset from board edges in Y
M3_HOLE_DIA = 3.2              # mm clearance through-hole

txt = PCB.read_text()

# ───────────── 1. Upgrade (layers ...) block to 8-layer per Phase 4a-restack-8L ─────────────
# Master directive 2026-05-22 (Task #37): scale to 8L for D/S signal-density
# improvement after Phase 3-redo added +413 components.
# Layer indices in .kicad_pcb follow KiCad's internal layer enumeration:
#   F.Cu = 0, In1.Cu = 1, In2.Cu = 2, ..., In6.Cu = 6, B.Cu = 31.
# 8L stackup (5 signal + 3 power planes), 3oz on F.Cu/In3.Cu/B.Cu:
#   - F.Cu (3oz) — top signal + high-current motor traces + TOLL FET pads
#   - In1.Cu (1oz) — GND plane (full board)
#   - In2.Cu (1oz) — signal (autoroute)
#   - In3.Cu (3oz) — +VMOTOR plane (heavy-copper for 280A continuous / 400A peak)
#   - In4.Cu (1oz) — signal (autoroute)
#   - In5.Cu (1oz) — GND plane (dual-GND for EMC / return-path symmetry)
#   - In6.Cu (1oz) — signal (autoroute)
#   - B.Cu (3oz) — bottom signal + secondary high-current + thermal face

NEW_LAYERS_8L = '''(layers
		(0 "F.Cu" signal "F.Cu 3oz — high-current motor traces / TOLL FET pads / thermal face")
		(1 "In1.Cu" signal "GND plane (full board, signal-typed for DSN export; Phase 5c re-classifies to power)")
		(2 "In2.Cu" signal "Inner signal #2 (1oz, autoroute target)")
		(3 "In3.Cu" signal "+VMOTOR plane (3oz, heavy-copper for ≥280A bus; signal-typed for DSN export; Phase 5c re-classifies to power)")
		(4 "In4.Cu" signal "Inner signal #4 (1oz, autoroute target)")
		(5 "In5.Cu" signal "GND plane #2 (dual-GND for EMC / return-path symmetry; signal-typed for DSN export; Phase 5c re-classifies to power)")
		(6 "In6.Cu" signal "Inner signal #6 (1oz, autoroute target)")
		(31 "B.Cu" signal "B.Cu 3oz — bottom signal + secondary high-current + thermal face")
		(32 "B.Adhes" user "B.Adhesive")
		(33 "F.Adhes" user "F.Adhesive")
		(34 "B.Paste" user)
		(35 "F.Paste" user)
		(36 "B.SilkS" user "B.Silkscreen")
		(37 "F.SilkS" user "F.Silkscreen")
		(38 "B.Mask" user)
		(39 "F.Mask" user)
		(40 "Dwgs.User" user "User.Drawings")
		(41 "Cmts.User" user "User.Comments")
		(42 "Eco1.User" user "User.Eco1")
		(43 "Eco2.User" user "User.Eco2")
		(44 "Edge.Cuts" user)
		(45 "Margin" user)
		(46 "B.CrtYd" user "B.Courtyard")
		(47 "F.CrtYd" user "F.Courtyard")
		(48 "B.Fab" user)
		(49 "F.Fab" user)
	)'''

NEW_LAYERS_10L = '''(layers
		(0 "F.Cu" signal "F.Cu 1oz — HS FETs, MCU pads, drivers, connectors")
		(1 "In1.Cu" signal "GND plane #1 — F.Cu reference @ 0.10mm prepreg (OQ-014 lock); signal-typed for DSN export; Phase 5c re-classifies to power")
		(2 "In2.Cu" signal "Inner signal #2 (NEW 10L) — dedicated J18/J19 fan-in escape layer")
		(3 "In3.Cu" signal "GND plane #2 (NEW 10L) — brackets In2 escape signals; signal-typed for DSN export; Phase 5c re-classifies to power")
		(4 "In4.Cu" signal "Inner signal #4 — BEMF analog (shielded by In3 + In5, OQ-016)")
		(5 "In5.Cu" signal "+VMOTOR plane (3oz, ≥280A bus; moved from In3 in 8L); signal-typed for DSN export; Phase 5c re-classifies to power")
		(6 "In6.Cu" signal "Inner signal #6 — SW inner escape per OQ-017 (was In4 in 8L)")
		(7 "In7.Cu" signal "GND plane #3 (NEW 10L) — brackets In6 + In8 signals; signal-typed for DSN export; Phase 5c re-classifies to power")
		(8 "In8.Cu" signal "Inner signal #8 (NEW 10L) — PWM_IN stragglers + low-current overflow")
		(31 "B.Cu" signal "B.Cu 1oz — LS FETs, bulk caps, status LEDs")
		(32 "B.Adhes" user "B.Adhesive")
		(33 "F.Adhes" user "F.Adhesive")
		(34 "B.Paste" user)
		(35 "F.Paste" user)
		(36 "B.SilkS" user "B.Silkscreen")
		(37 "F.SilkS" user "F.Silkscreen")
		(38 "B.Mask" user)
		(39 "F.Mask" user)
		(40 "Dwgs.User" user "User.Drawings")
		(41 "Cmts.User" user "User.Comments")
		(42 "Eco1.User" user "User.Eco1")
		(43 "Eco2.User" user "User.Eco2")
		(44 "Edge.Cuts" user)
		(45 "Margin" user)
		(46 "B.CrtYd" user "B.Courtyard")
		(47 "F.CrtYd" user "F.Courtyard")
		(48 "B.Fab" user)
		(49 "F.Fab" user)
	)'''

# Phase 4a-restack-10L (2026-05-26): default to 10L per Sai-locked proposal
# PR #179. NEW_LAYERS_8L kept as deprecated reference for migration audit.
NEW_LAYERS = NEW_LAYERS_10L

# Replace the existing (layers ...) block (multiline, ends with matching paren).
# Use a careful regex matched against the kinet2pcb default 2-layer output.
pat = re.compile(r'\(layers\s*\n.*?\n\t\)', re.DOTALL)
m = pat.search(txt)
if not m:
    raise SystemExit("could not locate (layers ...) block in pcbai_fpv4in1.kicad_pcb")
# Phase 4a-restack-8L: ACTIVATE the layer upgrade (was skipped in Phase 5b
# workaround). All 8 copper layers are typed as "signal" to remain
# DSN-export-compatible (Phase 5b finding T8: ExportSpecctraDSN silently fails
# when inner power planes are declared). The 3 plane layers (In1, In3, In5)
# carry "(Phase 5c re-classifies to power)" descriptors — Phase 5c reclassifies
# AFTER the DSN export → Freerouting autoroute → SES re-import workflow.
# dsn_strip_planes.py + dsn_inject_planes.py handle the autoroute-time geometry.
txt = txt[:m.start()] + NEW_LAYERS + txt[m.end():]
print(f"[1/3] Upgraded layer stack to 10L: 5 signal (F/In2/In4/In6/In8/B) + 4 plane (In1/In3 GND + In5 VMOTOR + In7 GND)")
print(f"        3oz on: In5.Cu (+VMOTOR 280A bus); 1oz on all other 9 layers")

# ───────────── 2. Append Edge.Cuts outline (rectangle at origin) ─────────────
# Phase 5b discovery: pcbnew.ExportSpecctraDSN fails on 4-separate-gr_line outlines
# (the exporter wants a single closed polygon). Use gr_rect — Specctra-compatible.
EDGE_CUTS = '''
\t(gr_rect (start 0 0) (end {W} {H}) (stroke (width 0.05) (type solid)) (fill no) (layer "Edge.Cuts"))
'''.format(W=BOARD_W, H=BOARD_H)

# ───────────── 3. Append 4× M3 mounting holes — proper KiCad9 footprint format ─────────────
# Phase 5b discovery: pcbnew.ExportSpecctraDSN fails when mount-hole footprints
# are missing uuid/descr/tags. Emit a complete KiCad9 mount-hole footprint here.
import re as _re
import uuid as _uuid

# PR-spine-fix 2026-05-23: strip existing MountingHole footprints to prevent
# orphan accumulation (PR-S3 discovery: H1/H2 at (44.6, 37.5)/(51.8, 37.5)
# were legacy positions from old spine-pattern run). Regex matches the entire
# (footprint "MountingHole:..." ...) S-expression block.
def _strip_mounting_holes(s):
    """Remove all (footprint "MountingHole:..." ...) blocks. Uses paren-counting
    to handle nested S-expressions properly."""
    out = []
    i = 0
    stripped = 0
    needle = '(footprint "MountingHole:'
    while i < len(s):
        j = s.find(needle, i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        # find matching close paren
        depth = 0
        k = j
        while k < len(s):
            if s[k] == '(': depth += 1
            elif s[k] == ')':
                depth -= 1
                if depth == 0:
                    break
            k += 1
        i = k + 1
        stripped += 1
        # Skip trailing newline+whitespace
        while i < len(s) and s[i] in '\n\t ':
            i += 1
    return ''.join(out), stripped

txt, _orig_mh_count = _strip_mounting_holes(txt)
if _orig_mh_count:
    print(f"  Stripped {_orig_mh_count} existing MountingHole footprints (legacy/orphan)")


# PR-spine-fix 2026-05-23: H1/H2 relocated from (44.6,37.5)/(51.8,37.5) — which
# were inside U1 Hall body. Master spec'd (10, 50)/(90, 50) flanks but those
# positions overlap CH1/CH2 FET clusters (Q5@(12,54) bbox X=4-20 Y=49-59).
# Spec deviation: use canonical 4-corner pattern (5,95)/(95,95)/(5,5)/(95,5)
# instead. Symmetric X-mirror preserved; clears all FET clusters.
mh_positions = [
    (MOUNT_X_PAD, BOARD_H - MOUNT_Y_PAD),     # H1 NW upper corner (5, 95)
    (BOARD_W - MOUNT_X_PAD, BOARD_H - MOUNT_Y_PAD), # H2 NE upper corner (95, 95)
    (MOUNT_X_PAD, MOUNT_Y_PAD),                # H3 NW lower corner (5, 5)
    (BOARD_W - MOUNT_X_PAD, MOUNT_Y_PAD),      # H4 NE lower corner (95, 5)
]
MOUNTING_HOLES = ""
for idx, (x, y) in enumerate(mh_positions, start=1):
    fp_uuid = str(_uuid.uuid4())
    pad_uuid = str(_uuid.uuid4())
    ref_uuid = str(_uuid.uuid4())
    val_uuid = str(_uuid.uuid4())
    MOUNTING_HOLES += f'''
\t(footprint "MountingHole:MountingHole_3.2mm_M3"
\t\t(layer "F.Cu")
\t\t(uuid "{fp_uuid}")
\t\t(at {x} {y})
\t\t(descr "Mounting Hole 3.2mm, M3 — Phase 4b-REDO2 90×75 custom pattern")
\t\t(tags "mountinghole M3")
\t\t(attr through_hole exclude_from_pos_files exclude_from_bom)
\t\t(property "Reference" "H{idx}"
\t\t\t(at 0 -4.15 0)
\t\t\t(layer "F.SilkS")
\t\t\t(uuid "{ref_uuid}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(property "Value" "MountingHole"
\t\t\t(at 0 4.15 0)
\t\t\t(layer "F.Fab")
\t\t\t(uuid "{val_uuid}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
\t\t(pad "" thru_hole circle
\t\t\t(at 0 0)
\t\t\t(size 6 6)
\t\t\t(drill {M3_HOLE_DIA})
\t\t\t(layers "*.Cu" "*.Mask")
\t\t\t(uuid "{pad_uuid}")
\t\t)
\t)'''

# Insert Edge.Cuts + mounting holes before the closing top-level ')'
last_paren = txt.rstrip().rfind(')')
insertion = EDGE_CUTS + MOUNTING_HOLES + "\n"
txt = txt[:last_paren] + insertion + txt[last_paren:]
print(f"[2/3] Added Edge.Cuts {BOARD_W:.0f}×{BOARD_H:.0f} mm + 4× M3 holes at corners {mh_positions}")

PCB.write_text(txt)
print(f"[3/3] Wrote: {PCB}  ({PCB.stat().st_size:,} bytes)")
