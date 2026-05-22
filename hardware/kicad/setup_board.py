"""Phase 4a-restack-8L — board setup: 8-layer stack + Edge.Cuts + M3 mounting holes.

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

Stackup specification (master Phase 4a-restack-8L directive 2026-05-22):
  Layer 0  F.Cu       signal  3oz   (top — high-current motor traces, TOLL MOSFET pads, thermal face)
  Layer 1  In1.Cu     power   1oz   (GND plane — full board, return-path integrity)
  Layer 2  In2.Cu     signal  1oz   (inner signal — autoroute target)
  Layer 3  In3.Cu     power   3oz   (+VMOTOR plane — heavy-copper for bus current ≥280A)
  Layer 4  In4.Cu     signal  1oz   (inner signal — autoroute target)
  Layer 5  In5.Cu     power   1oz   (GND plane — dual GND for EMC + return-path symmetry)
  Layer 6  In6.Cu     signal  1oz   (inner signal — autoroute target)
  Layer 31 B.Cu       signal  3oz   (bottom — thermal face for TOLL MOSFETs, secondary high-current)

5 signal layers (F.Cu, In2.Cu, In4.Cu, In6.Cu, B.Cu) for autoroute;
3 power/plane layers (In1.Cu GND, In3.Cu +VMOTOR, In5.Cu GND).

3oz copper layers: F.Cu, In3.Cu, B.Cu — for ≥100A burst current on motor phases
and ≥400A peak on +VMOTOR bus. JLC DRC at 3oz: minimum trace width = 5 mil
(vs 4 mil for 1oz/2oz); update routing constraint baseline for Phase 5b-retry.
1oz copper layers: In1.Cu, In2.Cu, In4.Cu, In5.Cu, In6.Cu — standard signal
density at JLC SMT capability spec.
"""

import re
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
BOARD_W = 100.0                # Phase 4b-REDO3: grew 90 → 100 for signal-density (Freerouting Pass #1 failed at 90×75)
BOARD_H = 85.0                 # grew 75 → 85
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
txt = txt[:m.start()] + NEW_LAYERS_8L + txt[m.end():]
print(f"[1/3] Upgraded layer stack to 8L: 5 signal (F/In2/In4/In6/B) + 3 plane (In1/In3/In5 GND/VMOTOR/GND)")
print(f"        3oz copper on: F.Cu, In3.Cu, B.Cu (heavy-current); 1oz on inner signal layers")

# ───────────── 2. Append Edge.Cuts outline (rectangle at origin) ─────────────
# Phase 5b discovery: pcbnew.ExportSpecctraDSN fails on 4-separate-gr_line outlines
# (the exporter wants a single closed polygon). Use gr_rect — Specctra-compatible.
EDGE_CUTS = '''
\t(gr_rect (start 0 0) (end {W} {H}) (stroke (width 0.05) (type solid)) (fill no) (layer "Edge.Cuts"))
'''.format(W=BOARD_W, H=BOARD_H)

# ───────────── 3. Append 4× M3 mounting holes — proper KiCad9 footprint format ─────────────
# Phase 5b discovery: pcbnew.ExportSpecctraDSN fails when mount-hole footprints
# are missing uuid/descr/tags. Emit a complete KiCad9 mount-hole footprint here.
import uuid as _uuid

mh_positions = [
    (MOUNT_X_PAD, MOUNT_Y_PAD),
    (BOARD_W - MOUNT_X_PAD, MOUNT_Y_PAD),
    (MOUNT_X_PAD, BOARD_H - MOUNT_Y_PAD),
    (BOARD_W - MOUNT_X_PAD, BOARD_H - MOUNT_Y_PAD),
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
