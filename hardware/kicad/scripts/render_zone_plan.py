#!/usr/bin/env python3
"""render_zone_plan.py — Generate zone-plan overlay PNGs for Phase 4-v2 Step 1.

Per master dispatch deliverables:
  - zone-boxes-top.png: board outline + 9 zone bboxes
  - io-port-overlay.png: zones + I/O port markers
  - highway-overlay.png: zones + reserved corridors
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

OUT = "/home/novatics64/escworker/pcb.ai/docs/renders/zone-plan"
os.makedirs(OUT, exist_ok=True)

# Per BOARD_INVARIANTS.md v2
BOARD = (0, 0, 100, 100)
MOUNT = [(5,5), (95,5), (5,95), (95,95)]
ZONES = {
    'S1 BATT':  (0, 0, 100, 18, 'lightcoral'),
    'S6 CONN':  (0, 82, 100, 100, 'lightyellow'),
    'CH1 (NW)': (0, 50, 35, 82, 'lightblue'),
    'CH2 (NE)': (65, 50, 100, 82, 'lightblue'),
    'CH3 (SE)': (65, 18, 100, 50, 'lightgreen'),
    'CH4 (SW)': (0, 18, 35, 50, 'lightgreen'),
    'S2 BULK':  (35, 40, 65, 60, 'plum'),
    'S3 SUP':   (35, 18, 65, 40, 'wheat'),
    'S5 E':     (35, 50, 40, 82, 'mistyrose'),
    'S5 W':     (60, 50, 65, 82, 'mistyrose'),
    'S5 S':     (35, 18, 40, 50, 'mistyrose'),
}
IO_PORTS = [
    ('S1→S3',   50, 18, '+BATT/BATGND'),
    ('S3→S2',   50, 40, 'BATT+IH'),
    ('S2→CH1',  35, 50, '+VM/GND'),
    ('S2→CH2',  65, 50, '+VM/GND'),
    ('S2→CH3',  65, 50, '+VM/GND'),
    ('S2→CH4',  35, 50, '+VM/GND'),
    ('S6→CH1',  17, 82, 'DShot1'),
    ('S6→CH2',  83, 82, 'DShot2'),
    ('S6→CH3',  83, 50, 'DShot3'),
    ('S6→CH4',  17, 50, 'DShot4'),
    ('S5→CH1',  35, 65, '+V5/9/3V3'),
    ('S5→CH2',  65, 65, '+V5/9/3V3'),
    ('S5→CH3',  65, 35, '+V5/9/3V3'),
    ('S5→CH4',  35, 35, '+V5/9/3V3'),
]
HIGHWAYS = [
    ('+BATT spine', 48, 0, 52, 50, 'red'),
    ('BEMF center', 47, 50, 53, 82, 'orange'),
    ('TLM/AUX', 0, 80, 100, 82, 'darkorange'),
    ('S2-CH1 radial', 30, 47, 36, 53, 'darkred'),
    ('S2-CH2 radial', 64, 47, 70, 53, 'darkred'),
    ('S2-CH3 radial', 64, 47, 70, 53, 'darkred'),
    ('S2-CH4 radial', 30, 47, 36, 53, 'darkred'),
]


def setup_fig(title):
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_xlim(-5, 105); ax.set_ylim(-5, 105)
    ax.set_aspect('equal')
    ax.set_xlabel('X (mm)'); ax.set_ylabel('Y (mm)')
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    # Board outline
    ax.add_patch(patches.Rectangle((0, 0), 100, 100, fill=False, edgecolor='black', lw=2))
    # Mount holes
    for mx, my in MOUNT:
        ax.add_patch(patches.Circle((mx, my), 1.5, color='gold'))
    return fig, ax


def draw_zones(ax):
    for name, (x1, y1, x2, y2, color) in ZONES.items():
        ax.add_patch(patches.Rectangle((x1, y1), x2-x1, y2-y1,
                                        facecolor=color, edgecolor='dimgray',
                                        alpha=0.5, lw=1))
        ax.text((x1+x2)/2, (y1+y2)/2, name, ha='center', va='center', fontsize=8)


# 1. Zone boxes
fig, ax = setup_fig('Phase 4-v2 — Subsystem zones (top view)')
draw_zones(ax)
plt.savefig(f'{OUT}/zone-boxes-top.png', dpi=150, bbox_inches='tight')
plt.close()

# 2. IO ports overlay
fig, ax = setup_fig('Phase 4-v2 — I/O ports overlay')
draw_zones(ax)
for label, x, y, signals in IO_PORTS:
    ax.plot(x, y, 'r*', markersize=15)
    ax.annotate(f'{label}\n{signals}', (x, y), textcoords='offset points',
                xytext=(5, 5), fontsize=7, color='darkred')
plt.savefig(f'{OUT}/io-port-overlay.png', dpi=150, bbox_inches='tight')
plt.close()

# 3. Highway overlay
fig, ax = setup_fig('Phase 4-v2 — Highway reservations (no-component corridors)')
draw_zones(ax)
for name, x1, y1, x2, y2, color in HIGHWAYS:
    ax.add_patch(patches.Rectangle((x1, y1), x2-x1, y2-y1,
                                    facecolor=color, edgecolor='none', alpha=0.6, hatch='//'))
    ax.text((x1+x2)/2, (y1+y2)/2, name, ha='center', va='center', fontsize=7, color='white', fontweight='bold')
plt.savefig(f'{OUT}/highway-overlay.png', dpi=150, bbox_inches='tight')
plt.close()

print(f"Generated 3 PNGs in {OUT}")
for f in ['zone-boxes-top.png', 'io-port-overlay.png', 'highway-overlay.png']:
    sz = os.path.getsize(f"{OUT}/{f}")
    print(f"  {f}: {sz} bytes")
