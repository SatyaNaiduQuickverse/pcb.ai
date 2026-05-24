#!/usr/bin/env python3
"""snap_mirror_validated.py — Step 4c M4 (master 2026-05-24).

For each CH1↔CH{2,3,4} role-paired ref with Δ > TARGET_MM, attempt to snap
the dst ref to mirror_X/Y/180° position of src. Validate against all 5 audit
gates BEFORE applying. If snap fails validation, try shifts within 1mm of
target. If all fail, mark as INVESTIGATE.

Target: clear all FAIL pairs (>2mm) where snap is possible without regression.
"""
import pcbnew, re, math, collections


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
TARGET_MM = 2.0
TOL_OK = 0.5

COINCIDENT_MIN = 1.6
MOTOR_PAD_KEEPOUT = 2.0
DECOUPLING_RADIUS = 3.0
PAD_CLEAR = 0.3
AREA_RATIO = 4.0
HOST_MIN_AREA = 5.0

MOTOR_TP_REFS = ('TP19','TP20','TP21','TP26','TP27','TP28',
                 'TP33','TP34','TP35','TP40','TP41','TP42')
_MOTOR_RE = re.compile(
    r'^(MOTOR_[ABC]_CH\d+|BEMF_[ABC]_CH\d+|CSA_[ABC]_OUT_CH\d+|CSA_MAX_CH\d+'
    r'|SHUNT_[ABC]_TOP_CH\d+|GH[ABC]_CH\d+|GL[ABC]_CH\d+|BST[ABC]_CH\d+)$'
)
HARDCODED_BODY_BBOX_REL = {
    'Sensor_Current:Allegro_CB_PFF': (-2.5, -2.5, 2.5, 2.5),
}

CROSS_ROLE_SWAP_PREFIXES = ('SWDIO', 'SWCLK')
MAX_DY_FOR_MIRROR_X = 15.0
MAX_DX_FOR_MIRROR_Y = 15.0

SILK_HIDE_PASSIVE_CLASSES = (
    'R_0402', 'R_0603', 'R_0805',
    'C_0402', 'C_0603', 'C_0805',
    'L_0402', 'L_0603', 'L_0805',
    'D_SOD-123', 'D_SOD-323', 'BAT54', 'BZT52',
    'R_2512', 'C_2512',
)


def is_silk_hide_eligible(fp):
    lib = str(fp.GetFPID().GetLibItemName() or '')
    for cls in SILK_HIDE_PASSIVE_CLASSES:
        if cls in lib: return True
    return False


def silk_bbox(fp):
    silk_pts = []
    for d in fp.GraphicalItems():
        if not isinstance(d, pcbnew.PCB_SHAPE): continue
        if d.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS): continue
        bb = d.GetBoundingBox()
        silk_pts.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                          pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    if not silk_pts:
        bb = fp.GetBoundingBox()
        return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    xs = [b[0] for b in silk_pts] + [b[2] for b in silk_pts]
    ys = [b[1] for b in silk_pts] + [b[3] for b in silk_pts]
    return (min(xs), min(ys), max(xs), max(ys))


def container_bbox(fp):
    lib = fp.GetFPID().GetUniStringLibId()
    rel = HARDCODED_BODY_BBOX_REL.get(lib)
    if rel is not None:
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        return (cx + rel[0], cy + rel[1], cx + rel[2], cy + rel[3])
    return silk_bbox(fp)


def is_motor_exempt(fp):
    for pad in fp.Pads():
        no = pad.GetNet()
        if no is None: continue
        if _MOTOR_RE.match(no.GetNetname() or ''):
            return True
    return False


def build_state(board):
    state = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H'): continue
        cbox = container_bbox(fp)
        area = max(0, (cbox[2]-cbox[0]) * (cbox[3]-cbox[1]))
        pos = fp.GetPosition()
        cx = pcbnew.ToMM(pos.x); cy = pcbnew.ToMM(pos.y)
        pads_pos = []
        pad_bxs = []
        for pad in fp.Pads():
            pp = pad.GetPosition()
            pads_pos.append((pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)))
            bb = pad.GetBoundingBox()
            ls = pad.GetLayerSet()
            pad_bxs.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                            pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                            ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu),
                            pad.GetNetname() or ''))
        ch_nets = {}
        for pad in fp.Pads():
            no = pad.GetNet()
            if no is None: continue
            n = no.GetNetname() or ''
            m = re.search(r'_CH([1234])$', n)
            if m:
                ch_nets.setdefault(int(m.group(1)), set()).add(n[:m.start()])
        state[ref] = {
            'fp': fp, 'cx': cx, 'cy': cy, 'cbox': cbox, 'area': area,
            'pads_pos': pads_pos, 'pad_bxs': pad_bxs,
            'layer': fp.GetLayer(),
            'motor_exempt': is_motor_exempt(fp),
            'ch_nets': ch_nets,
            'channels': set(ch_nets.keys()),
            'lib': str(fp.GetFPID().GetLibItemName() or ''),
            'first': ref[0],
        }
    return state


def expected_mirror(x, y, src_ch, dst_ch):
    if src_ch == 1 and dst_ch == 2: return (100.0 - x, y)
    if src_ch == 1 and dst_ch == 3: return (100.0 - x, 100.0 - y)
    if src_ch == 1 and dst_ch == 4: return (x, 100.0 - y)
    raise ValueError


def find_pairs(state):
    """Return list of (src_ref, dst_ref, dst_ch, delta) for CH1→CH{2,3,4} pairs."""
    ch_to_role = {1: {}, 2: {}, 3: {}, 4: {}}
    for ref, d in state.items():
        if len(d['channels']) != 1: continue
        ch = next(iter(d['channels']))
        if any(r.startswith(p) for r in d['ch_nets'][ch]
               for p in CROSS_ROLE_SWAP_PREFIXES):
            continue
        sig = (tuple(sorted(d['ch_nets'][ch])), d['first'], d['lib'])
        ch_to_role[ch].setdefault(sig, []).append(ref)
    pairs = []
    for dst_ch in (2, 3, 4):
        for sig, src_refs in ch_to_role[1].items():
            dst_refs = ch_to_role[dst_ch].get(sig, [])
            if not dst_refs: continue
            used = set()
            for src in src_refs:
                sx, sy = state[src]['cx'], state[src]['cy']
                ex, ey = expected_mirror(sx, sy, 1, dst_ch)
                best = None; best_d = 1e9
                for dr in dst_refs:
                    if dr in used: continue
                    dx, dy = state[dr]['cx'], state[dr]['cy']
                    d = math.hypot(dx - ex, dy - ey)
                    if d < best_d:
                        best_d = d; best = dr
                if best is None: continue
                used.add(best)
                # Direction sanity
                bx, by = state[best]['cx'], state[best]['cy']
                if dst_ch == 2 and abs(by - sy) > MAX_DY_FOR_MIRROR_X: continue
                if dst_ch == 4 and abs(bx - sx) > MAX_DX_FOR_MIRROR_Y: continue
                pairs.append((src, best, dst_ch, best_d, (ex, ey)))
    return pairs


def position_violates(ref, nx, ny, state):
    """Check 4 audit gates for tentative position. Returns list of violations."""
    s = state[ref]
    dx = nx - s['cx']; dy = ny - s['cy']
    new_pads = [(p[0]+dx, p[1]+dy) for p in s['pads_pos']]
    new_pad_bxs = [(b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy, b[4], b[5], b[6])
                   for b in s['pad_bxs']]
    layer = s['layer']
    inh_nets = {b[6] for b in s['pad_bxs']}
    vios = []
    # 1. COINCIDENT
    for oref, o in state.items():
        if oref == ref: continue
        if o['layer'] != layer: continue
        if math.hypot(o['cx'] - nx, o['cy'] - ny) < COINCIDENT_MIN:
            vios.append(f"COINCIDENT-{oref}")
            return vios
    # 2. INSIDE-BODY (host)
    for oref, host in state.items():
        if oref == ref: continue
        if host['layer'] != layer: continue
        if host['area'] < AREA_RATIO * s['area']: continue
        if host['area'] < HOST_MIN_AREA: continue
        bx0, by0, bx1, by1 = host['cbox']
        ctr_in = bx0 <= nx <= bx1 and by0 <= ny <= by1
        pads_in = any(bx0 <= px <= bx1 and by0 <= py <= by1
                      for (px, py) in new_pads)
        if ctr_in or pads_in:
            vios.append(f"INSIDE-{oref}")
            return vios
    # 3. PAD-OVERLAP-DIFFNET
    for oref, o in state.items():
        if oref == ref: continue
        for opp in o['pad_bxs']:
            for nb in new_pad_bxs:
                if nb[6] == opp[6] and nb[6] != '': continue
                same_layer = (nb[4] and opp[4]) or (nb[5] and opp[5])
                if not same_layer: continue
                if nb[0]-PAD_CLEAR < opp[2] and nb[2]+PAD_CLEAR > opp[0] and \
                   nb[1]-PAD_CLEAR < opp[3] and nb[3]+PAD_CLEAR > opp[1]:
                    vios.append(f"PAD-OVERLAP-{oref}.{opp[6]}")
                    return vios
    # 4. MOTOR-PAD-CLEAR
    for mref in MOTOR_TP_REFS:
        if mref not in state: continue
        m = state[mref]
        if m['layer'] != layer: continue
        if abs(nx - m['cx']) < MOTOR_PAD_KEEPOUT and \
           abs(ny - m['cy']) < MOTOR_PAD_KEEPOUT and not s['motor_exempt']:
            vios.append(f"MOTOR-TP-{mref}")
            return vios
    # 5. IC-LOSE-CAP
    if ref.startswith('C') and ref[1:].isdigit():
        for iref, ic in state.items():
            if not (iref.startswith('U') and iref[1:].isdigit()): continue
            if ic['layer'] != layer: continue
            d_old = math.hypot(ic['cx'] - s['cx'], ic['cy'] - s['cy'])
            d_new = math.hypot(ic['cx'] - nx, ic['cy'] - ny)
            if d_old > DECOUPLING_RADIUS: continue
            if d_new <= DECOUPLING_RADIUS: continue
            has_other = False
            for cref, co in state.items():
                if cref == ref: continue
                if not (cref.startswith('C') and cref[1:].isdigit()): continue
                if co['layer'] != ic['layer']: continue
                if math.hypot(co['cx'] - ic['cx'], co['cy'] - ic['cy']) <= DECOUPLING_RADIUS:
                    has_other = True; break
            if not has_other:
                vios.append(f"IC-LOSE-CAP-{iref}")
                return vios
    return vios


def apply_move(ref, nx, ny, state):
    s = state[ref]
    s['fp'].SetPosition(pcbnew.VECTOR2I(int(nx*1e6), int(ny*1e6)))
    dx = nx - s['cx']; dy = ny - s['cy']
    s['cx'] = nx; s['cy'] = ny
    s['cbox'] = (s['cbox'][0]+dx, s['cbox'][1]+dy,
                 s['cbox'][2]+dx, s['cbox'][3]+dy)
    s['pads_pos'] = [(p[0]+dx, p[1]+dy) for p in s['pads_pos']]
    s['pad_bxs'] = [(b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy, b[4], b[5], b[6])
                    for b in s['pad_bxs']]


def main():
    board = pcbnew.LoadBoard(PCB)
    state = build_state(board)
    pairs = find_pairs(state)
    fails = [p for p in pairs if p[3] > TARGET_MM]
    print(f"Total pairs: {len(pairs)}, fails (>{TARGET_MM}mm): {len(fails)}")

    snaps = 0; alternates = 0; failed = 0
    log = []
    # Sort by delta descending — fix worst first
    for src, dst, dst_ch, d_orig, (ex, ey) in sorted(fails, key=lambda x: -x[3]):
        # Try exact mirror
        vios = position_violates(dst, ex, ey, state)
        if not vios:
            apply_move(dst, ex, ey, state)
            if is_silk_hide_eligible(state[dst]['fp']):
                state[dst]['fp'].Reference().SetVisible(False)
            snaps += 1
            log.append((dst, dst_ch, ex, ey, d_orig, 'exact-snap', src))
            continue
        # Try nearby positions within 1mm of target (8 cardinals + 8 diagonals)
        found = False
        for r in (0.5, 1.0, 1.5):
            for ai in range(16):
                theta = 2 * math.pi * ai / 16
                nx = ex + r * math.cos(theta)
                ny = ey + r * math.sin(theta)
                if nx < 1.5 or nx > 98.5 or ny < 1.5 or ny > 98.5: continue
                vios = position_violates(dst, nx, ny, state)
                if not vios:
                    apply_move(dst, nx, ny, state)
                    if is_silk_hide_eligible(state[dst]['fp']):
                        state[dst]['fp'].Reference().SetVisible(False)
                    alternates += 1
                    log.append((dst, dst_ch, nx, ny, d_orig, f'alt-r{r}', src))
                    found = True; break
            if found: break
        if not found:
            failed += 1
            log.append((dst, dst_ch, None, None, d_orig, f'FAILED ({vios[:1]})', src))

    for entry in log:
        dst, dst_ch, nx, ny, d_orig, action, src = entry
        if nx is None:
            print(f"  {dst} (CH1↔CH{dst_ch} mirror of {src}, Δ_was={d_orig:.2f}mm): {action}")
        else:
            print(f"  {dst} → ({nx:.2f},{ny:.2f}) (mirror of {src}, Δ_was={d_orig:.2f}mm) [{action}]")
    print(f"\nExact-snapped: {snaps}, alt-position: {alternates}, FAILED: {failed}")
    board.Save(PCB)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
