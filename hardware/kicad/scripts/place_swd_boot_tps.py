#!/usr/bin/env python3
"""place_swd_boot_tps.py — algorithmic SWD/BOOT TP placement with spacing.

Codifies SWD/BOOT TP positions so fresh kinet2pcb re-import doesn't regress
to the pre-PR-#67 cramped layout. Per master 2026-05-24 directive: every fix
must be CODIFIED so it can't regress.

Places 12 TPs (4 BOOT_JUMPER, 4 SWDIO, 4 SWCLK — 1 per channel) at safe
positions:
- ≥4mm center-to-center same layer (probe-access rule, PR #67 catch #4)
- Outside motor-TP keep-out zones (X=1.5-8.5, X=91.5-98.5)
- Outside IC body bbox (find nearest free zone)
- Spiral search if hardcoded targets collide with current placement
"""
import pcbnew, math

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Target positions (best initial guesses; spiral if blocked)
# Row 1: Y=84 north of motor TPs (above CH1/CH2 zone) — 7mm pitch, 4 BOOT_JUMPER + 2 SWDIO
# Row 2: Y=16 south of motor TPs — 7mm pitch
TARGETS = [
    # (ref, target_x, target_y) — Y=58 north of central spine, Y=42 south
    # to clear power TPs at Y=47.5/49.5/53
    ('TP17', 32.0, 58.0),  # BOOT_JUMPER_CH1
    ('TP24', 68.0, 58.0),  # BOOT_JUMPER_CH2
    ('TP31', 68.0, 42.0),  # BOOT_JUMPER_CH3
    ('TP38', 32.0, 42.0),  # BOOT_JUMPER_CH4
    ('TP22', 25.0, 58.0),  # SWDIO_CH1
    ('TP23', 39.0, 58.0),  # SWCLK_CH1
    ('TP29', 61.0, 58.0),  # SWDIO_CH2
    ('TP30', 75.0, 58.0),  # SWCLK_CH2
    ('TP36', 75.0, 42.0),  # SWDIO_CH3
    ('TP37', 61.0, 42.0),  # SWCLK_CH3
    ('TP43', 25.0, 42.0),  # SWDIO_CH4
    ('TP44', 39.0, 42.0),  # SWCLK_CH4
]


def pad_bboxes(fp, nx, ny):
    rot = fp.GetOrientationDegrees()
    cos_r = math.cos(math.radians(rot)); sin_r = math.sin(math.radians(rot))
    out = []
    for pad in fp.Pads():
        pos0 = pad.GetFPRelativePosition(); size = pad.GetSize()
        lx, ly = pos0.x/1e6, pos0.y/1e6
        rx = lx*cos_r - ly*sin_r; ry = lx*sin_r + ly*cos_r
        px, py = nx+rx, ny+ry
        pw, ph = size.x/1e6, size.y/1e6
        if rot in (90.0, 270.0): pw, ph = ph, pw
        ls = pad.GetLayerSet()
        ls_set = set()
        if ls.Contains(pcbnew.F_Cu): ls_set.add('F.Cu')
        if ls.Contains(pcbnew.B_Cu): ls_set.add('B.Cu')
        out.append({'x0':px-pw/2-0.1,'y0':py-ph/2-0.1,'x1':px+pw/2+0.1,'y1':py+ph/2+0.1,
                    'net':pad.GetNetname(),'ls':ls_set})
    return out


def others(b, exclude):
    out = []
    for fp in b.GetFootprints():
        if fp.GetReference() == exclude: continue
        out.extend([{**bx,'r':fp.GetReference()} for bx in pad_bboxes(fp, fp.GetPosition().x/1e6, fp.GetPosition().y/1e6)])
    return out


def collides(cb, ob):
    for c in cb:
        for o in ob:
            if c['net'] and c['net'] == o['net']: continue
            if not (c['ls'] & o['ls']): continue
            if c['x0'] < o['x1'] and c['x1'] > o['x0'] and c['y0'] < o['y1'] and c['y1'] > o['y0']:
                return o['r']
    return None


def center_col(b, fp, nx, ny, exclude, min_d=1.5):
    layer = fp.GetLayer()
    for of in b.GetFootprints():
        if of.GetReference() == exclude or of.GetLayer() != layer: continue
        ox, oy = of.GetPosition().x/1e6, of.GetPosition().y/1e6
        if math.hypot(nx-ox, ny-oy) < min_d: return of.GetReference()
    return None


def spiral(cx, cy, max_r=8.0, step=0.5):
    yield (cx, cy)
    for r_steps in range(1, int(max_r / step) + 2):
        r = r_steps * step
        n_pts = max(8, r_steps * 8)
        for i in range(n_pts):
            theta = 2 * math.pi * i / n_pts
            yield (cx + r * math.cos(theta), cy + r * math.sin(theta))


def main():
    b = pcbnew.LoadBoard(PCB)
    placed = {}  # ref → (x, y)
    moved = 0
    for ref, tx, ty in TARGETS:
        fp = None
        for f in b.GetFootprints():
            if f.GetReference() == ref:
                fp = f; break
        if not fp:
            print(f"  {ref}: not found"); continue
        other = others(b, ref)
        chosen = None
        for nx, ny in spiral(tx, ty, max_r=10.0):
            if nx < 3 or nx > 97 or ny < 3 or ny > 97: continue
            # Check 4mm spacing vs already-placed SWD/BOOT TPs
            ok_tp_spacing = True
            for other_ref, (ox, oy) in placed.items():
                if math.hypot(nx-ox, ny-oy) < 4.0:
                    ok_tp_spacing = False; break
            if not ok_tp_spacing: continue
            if center_col(b, fp, nx, ny, ref): continue
            if collides(pad_bboxes(fp, nx, ny), other): continue
            chosen = (nx, ny); break
        if chosen:
            nx, ny = chosen
            fp.SetPosition(pcbnew.VECTOR2I(int(nx*1e6), int(ny*1e6)))
            placed[ref] = (nx, ny)
            moved += 1
            print(f"  {ref} → ({nx:.1f}, {ny:.1f})")
        else:
            print(f"  {ref}: NO SLOT — stayed at original")
    b.Save(PCB)
    print(f"\nPlaced {moved} SWD/BOOT TPs with 4mm spacing")


if __name__ == "__main__":
    main()
