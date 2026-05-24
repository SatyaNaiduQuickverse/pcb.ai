#!/usr/bin/env python3
"""snap_mirror_partners.py — Step 4c: enforce CH2 = mirror_X(CH1) for all
role-paired channel passives (master 2026-05-24 R19 lock).

For each CH1 channel-tagged ref, find its CH2 role-paired counterpart and
snap CH2 position to mirror_X(50) of CH1. Same for CH3 = 180°-rot, CH4 = mirror_Y.

Pairing: by role signature (sorted net suffixes + ref-prefix-letter + footprint
lib class), matching one CH1 ref to one CH2 ref per signature. Multiple
candidates resolved by closest-to-expected-mirror-position.

Codified per [[feedback-symmetry-preserves-work]] +
[[feedback-spec-vs-placement-gate]].
"""
import pcbnew, re, sys, math, collections


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
TOL = 0.5


def main():
    b = pcbnew.LoadBoard(PCB)
    fps = list(b.GetFootprints())

    info = {}
    for fp in fps:
        ref = fp.GetReference()
        p = fp.GetPosition()
        cx = p.x / 1e6; cy = p.y / 1e6
        ch_nets = {}
        for pad in fp.Pads():
            no = pad.GetNet()
            if no is None: continue
            n = no.GetNetname() or ''
            m = re.search(r'_CH([1234])$', n)
            if m:
                ch = int(m.group(1))
                role = n[:m.start()]
                ch_nets.setdefault(ch, set()).add(role)
        info[ref] = {
            'x': cx, 'y': cy, 'fp': fp, 'ch_nets': ch_nets,
            'channels': set(ch_nets.keys()),
            'lib': str(fp.GetFPID().GetLibItemName() or ''),
            'first': ref[0],
        }

    # Group by channel + role signature
    ch_to_role_ref = {1: {}, 2: {}, 3: {}, 4: {}}
    for ref, d in info.items():
        if len(d['channels']) != 1: continue
        ch = next(iter(d['channels']))
        role_sig = (tuple(sorted(d['ch_nets'][ch])), d['first'], d['lib'])
        ch_to_role_ref[ch].setdefault(role_sig, []).append(ref)

    def expected_mirror(src_x, src_y, src_ch, dst_ch):
        if src_ch == 1 and dst_ch == 2: return (100.0 - src_x, src_y)
        if src_ch == 1 and dst_ch == 3: return (100.0 - src_x, 100.0 - src_y)
        if src_ch == 1 and dst_ch == 4: return (src_x, 100.0 - src_y)
        raise ValueError

    snaps = []
    for dst_ch in (2, 3, 4):
        src_ch = 1
        src_roles = ch_to_role_ref[src_ch]
        dst_roles = ch_to_role_ref[dst_ch]
        for role_sig, src_refs in src_roles.items():
            dst_refs = dst_roles.get(role_sig, [])
            if not dst_refs: continue
            used_dst = set()
            # Pair each src_ref to closest dst_ref to its expected mirror
            for src_ref in src_refs:
                sx, sy = info[src_ref]['x'], info[src_ref]['y']
                ex, ey = expected_mirror(sx, sy, src_ch, dst_ch)
                best = None; best_d = 1e9
                for dr in dst_refs:
                    if dr in used_dst: continue
                    dx2, dy2 = info[dr]['x'], info[dr]['y']
                    d = math.hypot(dx2 - ex, dy2 - ey)
                    if d < best_d:
                        best_d = d; best = (dr, dx2, dy2, d)
                if best is None: continue
                used_dst.add(best[0])
                dr, dx2, dy2, d = best
                if d > TOL:
                    # Snap dst_ref to expected mirror position
                    snaps.append((dr, dx2, dy2, ex, ey, d, src_ref))
                    info[dr]['fp'].SetPosition(
                        pcbnew.VECTOR2I(int(ex * 1e6), int(ey * 1e6)))
                    info[dr]['x'] = ex; info[dr]['y'] = ey

    for dr, ox, oy, nx, ny, d, src in snaps:
        print(f"  {dr} ({ox:.2f},{oy:.2f}) → ({nx:.2f},{ny:.2f})  "
              f"Δ_was={d:.2f}mm  ref={src}")
    print(f"\nSnapped {len(snaps)} mirror partners")
    b.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
