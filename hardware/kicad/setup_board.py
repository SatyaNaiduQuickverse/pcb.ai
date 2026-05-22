"""Phase 4a — board setup: 6-layer stack + Edge.Cuts + M3 mounting holes.

Reads pcbai_fpv4in1.kicad_pcb (kinet2pcb output, 2-layer default),
upgrades to 6-layer per PCB_PLAYBOOK §Routing, adds 50×50 Edge.Cuts
outline, and 4× M3 mounting holes on the 40×40 Betaflight pattern.
"""

import re
from pathlib import Path

PCB = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb")
BOARD_W = 50.0
BOARD_H = 50.0
MOUNT_PATTERN = 40.0           # M3 hole-center to hole-center
M3_HOLE_DIA = 3.2              # mm clearance through-hole

txt = PCB.read_text()

# ───────────── 1. Upgrade (layers ...) block to 6-layer per Playbook §Routing ─────────────
# kinet2pcb default 2-layer block uses indices (0 F.Cu, 2 B.Cu). For 6-layer
# we need 0..4 inner-copper indices + B.Cu shifted to index 31 per KiCad std.
# But KiCad accepts contiguous (0..5) for 6 copper layers in .kicad_pcb format.

NEW_LAYERS = '''(layers
		(0 "F.Cu" signal)
		(1 "In1.Cu" power "VMOTOR plane")
		(2 "In2.Cu" power "GND plane")
		(3 "In3.Cu" power "GND plane")
		(4 "In4.Cu" power "5V_3V3 split plane")
		(5 "B.Cu" signal)
		(9 "F.Adhes" user "F.Adhesive")
		(11 "B.Adhes" user "B.Adhesive")
		(13 "F.Paste" user)
		(15 "B.Paste" user)
		(5 "F.SilkS" user "F.Silkscreen")
		(7 "B.SilkS" user "B.Silkscreen")
		(1 "F.Mask" user)
		(3 "B.Mask" user)
		(17 "Dwgs.User" user "User.Drawings")
		(19 "Cmts.User" user "User.Comments")
		(21 "Eco1.User" user "User.Eco1")
		(23 "Eco2.User" user "User.Eco2")
		(25 "Edge.Cuts" user)
		(27 "Margin" user)
		(31 "F.CrtYd" user "F.Courtyard")
		(29 "B.CrtYd" user "B.Courtyard")
		(35 "F.Fab" user)
		(33 "B.Fab" user)
	)'''

# Actually — the layer index numbers in .kicad_pcb are fixed by KiCad's
# internal layer enumeration. The values 0/2 for F.Cu/B.Cu are correct for
# 2-layer (B.Cu at index 2 when no inner layers exist). For 6-layer the
# correct indices are: F.Cu=0, In1.Cu=1, In2.Cu=2, In3.Cu=3, In4.Cu=4, B.Cu=31.
# Per KiCad LayerNum_PCB enum. Reference: kicad-source.

NEW_LAYERS_FIXED = '''(layers
		(0 "F.Cu" signal)
		(1 "In1.Cu" power "+VMOTOR plane (Playbook §Routing)")
		(2 "In2.Cu" power "GND plane")
		(3 "In3.Cu" power "GND plane (return-path integrity)")
		(4 "In4.Cu" power "+5V_+3V3 split plane")
		(31 "B.Cu" signal)
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
txt = txt[:m.start()] + NEW_LAYERS_FIXED + txt[m.end():]
print("[1/3] Upgraded layer stack to 6-layer (F.Cu / In1-4.Cu / B.Cu)")

# ───────────── 2. Append Edge.Cuts outline (50×50 mm square at origin) ─────────────
EDGE_CUTS = '''
\t(gr_line (start 0 0) (end {W} 0) (stroke (width 0.05) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start {W} 0) (end {W} {H}) (stroke (width 0.05) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start {W} {H}) (end 0 {H}) (stroke (width 0.05) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 0 {H}) (end 0 0) (stroke (width 0.05) (type solid)) (layer "Edge.Cuts"))
'''.format(W=BOARD_W, H=BOARD_H)

# ───────────── 3. Append 4× M3 mounting holes on 40×40 pattern ─────────────
mh_inset = (BOARD_W - MOUNT_PATTERN) / 2.0       # 5 mm
mh_positions = [
    (mh_inset, mh_inset),
    (BOARD_W - mh_inset, mh_inset),
    (mh_inset, BOARD_H - mh_inset),
    (BOARD_W - mh_inset, BOARD_H - mh_inset),
]
MOUNTING_HOLES = ""
for (x, y) in mh_positions:
    MOUNTING_HOLES += f'''
\t(footprint "MountingHole:MountingHole_3.2mm_M3" (layer "F.Cu") (at {x} {y})
\t\t(attr through_hole exclude_from_pos_files exclude_from_bom)
\t\t(pad "" thru_hole circle (at 0 0) (size 6.0 6.0) (drill {M3_HOLE_DIA}) (layers "*.Cu" "*.Mask"))
\t)'''

# Insert Edge.Cuts + mounting holes before the closing top-level ')'
# The closing ')' is the very last non-whitespace char.
last_paren = txt.rstrip().rfind(')')
insertion = EDGE_CUTS + MOUNTING_HOLES + "\n"
txt = txt[:last_paren] + insertion + txt[last_paren:]
print(f"[2/3] Added Edge.Cuts 50×50 mm + 4× M3 holes on 40×40 mm pattern at corners {mh_positions}")

PCB.write_text(txt)
print(f"[3/3] Wrote: {PCB}  ({PCB.stat().st_size:,} bytes)")
