"""Phase 2.5 — placement sketch on 50×50 mm form factor.

Generates SVG + PNG placement-only diagrams for F.Cu (signal side) and
B.Cu (power side) for visual fit confirmation.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
import os

BOARD_W = 50.0
BOARD_H = 50.0
MOUNT_HOLE_PATTERN = 40.0
MOUNT_HOLE_DIA = 3.2

OUT_DIR = "/home/novatics64/escworker/pcb.ai/sims/phase2_5_fit"


def board_outline(ax, label):
    ax.add_patch(Rectangle((0, 0), BOARD_W, BOARD_H, fill=False, edgecolor='black', linewidth=2))
    mh_offset = (BOARD_W - MOUNT_HOLE_PATTERN) / 2
    for x, y in [(mh_offset, mh_offset), (BOARD_W - mh_offset, mh_offset),
                 (mh_offset, BOARD_H - mh_offset), (BOARD_W - mh_offset, BOARD_H - mh_offset)]:
        ax.add_patch(Circle((x, y), MOUNT_HOLE_DIA/2, fill=False, edgecolor='red', linewidth=1.5))
    ax.text(BOARD_W/2, BOARD_H + 1.5, label, ha='center', fontsize=11, fontweight='bold')
    ax.set_xlim(-2, BOARD_W + 2)
    ax.set_ylim(-2, BOARD_H + 3)
    ax.set_aspect('equal')
    ax.set_xticks(range(0, int(BOARD_W) + 1, 10))
    ax.set_yticks(range(0, int(BOARD_H) + 1, 10))
    ax.grid(alpha=0.2)
    ax.set_xlabel('mm')
    ax.set_ylabel('mm')


def place_box(ax, x, y, w, h, color, label, fontsize=7):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=color, edgecolor='black', linewidth=0.5, alpha=0.7))
    if label:
        ax.text(x + w/2, y + h/2, label, ha='center', va='center', fontsize=fontsize)


def f_cu_sketch():
    fig, ax = plt.subplots(figsize=(8, 8))
    board_outline(ax, 'F.Cu (signal side) - 50x50 mm')
    place_box(ax, BOARD_W/2 - 4, BOARD_H - 4.5, 8.0, 3.4, 'tab:blue', 'JST 8-pin\nFC')
    mcu_positions = [(3, 3, 'MCU\nCH1'), (BOARD_W - 12, 3, 'MCU\nCH2'),
                     (3, BOARD_H - 18, 'MCU\nCH3'), (BOARD_W - 12, BOARD_H - 18, 'MCU\nCH4')]
    for x, y, lbl in mcu_positions:
        place_box(ax, x, y, 9, 9, 'tab:green', lbl)
    driver_positions = [(13, 5, 'GD\nCH1'), (BOARD_W - 17, 5, 'GD\nCH2'),
                        (13, BOARD_H - 14, 'GD\nCH3'), (BOARD_W - 17, BOARD_H - 14, 'GD\nCH4')]
    for x, y, lbl in driver_positions:
        place_box(ax, x, y, 4, 4, 'tab:purple', lbl, fontsize=6)
    for x, y in [(3, 13), (BOARD_W - 6, 13), (3, BOARD_H - 22), (BOARD_W - 6, BOARD_H - 22)]:
        place_box(ax, x, y, 3, 2.5, 'tab:orange', 'CSA\nx3', fontsize=6)
    for x in [BOARD_W/2 - 8, BOARD_W/2 - 4, BOARD_W/2 + 1]:
        place_box(ax, x, BOARD_H - 9, 3, 3, 'lightcoral', 'ESD', fontsize=6)
    place_box(ax, BOARD_W - 12, BOARD_H/2 - 3, 5, 3, 'tab:cyan', 'Buck')
    place_box(ax, BOARD_W - 12, BOARD_H/2 + 1, 5, 3, 'tab:olive', 'LDO')
    for i in range(4):
        place_box(ax, 0.5, 22 + i*3, 1, 1, 'gray', f'S{i+1}', fontsize=5)
    for i in range(3):
        ax.add_patch(Circle((20 + i*3, 0.5), 1.5, color='red', alpha=0.6))
        ax.add_patch(Circle((BOARD_W - 23 + i*3, 0.5), 1.5, color='red', alpha=0.6))
        ax.add_patch(Circle((20 + i*3, BOARD_H - 0.5), 1.5, color='red', alpha=0.6))
        ax.add_patch(Circle((BOARD_W - 23 + i*3, BOARD_H - 0.5), 1.5, color='red', alpha=0.6))
    for i in range(5):
        ax.add_patch(Circle((BOARD_W/2 - 5 + i*2.5, BOARD_H/2 - 5), 0.6, color='green' if i == 0 else 'red'))
    fig.savefig(os.path.join(OUT_DIR, 'placement_F_Cu.png'), bbox_inches='tight', dpi=120)
    plt.close(fig)


def b_cu_sketch():
    fig, ax = plt.subplots(figsize=(8, 8))
    board_outline(ax, 'B.Cu (power side) - 50x50 mm  [heatsink over MOSFETs]')
    fet_w, fet_h = 5.0, 6.0
    spacing_x, spacing_y = 2.0, 1.5
    grid_w = 6 * fet_w + 5 * spacing_x
    grid_h = 4 * fet_h + 3 * spacing_y
    grid_x0 = (BOARD_W - grid_w) / 2
    grid_y0 = (BOARD_H - grid_h) / 2
    hs_x0 = grid_x0 - 2
    hs_y0 = grid_y0 - 2
    hs_w = grid_w + 4
    hs_h = grid_h + 4
    ax.add_patch(Rectangle((hs_x0, hs_y0), hs_w, hs_h, fill=True, facecolor='lightgray',
                           edgecolor='black', linewidth=1, alpha=0.4, hatch='///'))
    ax.text(BOARD_W/2, hs_y0 + hs_h - 1, f'Heatsink ~{hs_w:.0f}x{hs_h:.0f}mm',
            ha='center', fontsize=8, fontweight='bold')
    ch_labels = ['CH1', 'CH2', 'CH3', 'CH4']
    for row in range(4):
        for col in range(6):
            x = grid_x0 + col * (fet_w + spacing_x)
            y = grid_y0 + row * (fet_h + spacing_y)
            label = f'{ch_labels[row]}' if col == 0 else ''
            place_box(ax, x, y, fet_w, fet_h, 'tab:red', label, fontsize=6)
    for i in range(4):
        x = grid_x0 + i * (grid_w / 4)
        place_box(ax, x, grid_y0 - 5, grid_w/4 - 1, 3, 'darkgreen', f'Shunt x3\nCH{i+1}', fontsize=6)
    place_box(ax, 1.5, BOARD_H - 16, 12.5, 13.5, 'tab:brown', '470uF\n63V')
    place_box(ax, BOARD_W - 14, BOARD_H - 16, 12.5, 13.5, 'tab:brown', '470uF\n63V')
    for i in range(4):
        place_box(ax, BOARD_W/2 - 14 + i*7, 1.5, 5, 6, 'tab:pink',
                  f'RP\nFET{i+1}', fontsize=5)
    place_box(ax, BOARD_W/2 + 16, 2, 4.3, 3.4, 'tab:olive', 'TVS\nSMBJ33A', fontsize=6)
    fig.savefig(os.path.join(OUT_DIR, 'placement_B_Cu.png'), bbox_inches='tight', dpi=120)
    plt.close(fig)


if __name__ == '__main__':
    f_cu_sketch()
    b_cu_sketch()
    print(f"placement_F_Cu.png + placement_B_Cu.png written to {OUT_DIR}/")
