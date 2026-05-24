#!/usr/bin/env python3
"""mirror_fail_histogram.py — distribution of mirror deltas for failing pairs."""
import pcbnew, re, math, collections


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


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
        info[ref] = {'x': cx, 'y': cy, 'fp': fp, 'ch_nets': ch_nets,
                    'channels': set(ch_nets.keys()),
                    'lib': str(fp.GetFPID().GetLibItemName() or ''),
                    'first': ref[0]}

    ch_to_role_ref = {1: {}, 2: {}}
    for ref, d in info.items():
        if len(d['channels']) != 1: continue
        ch = next(iter(d['channels']))
        if ch not in (1, 2): continue
        sig = (tuple(sorted(d['ch_nets'][ch])), d['first'], d['lib'])
        ch_to_role_ref[ch].setdefault(sig, []).append(ref)

    pairs = []  # (src, dst, delta)
    for sig, src_refs in ch_to_role_ref[1].items():
        dst_refs = ch_to_role_ref[2].get(sig, [])
        if not dst_refs: continue
        used = set()
        for src in src_refs:
            sx, sy = info[src]['x'], info[src]['y']
            ex, ey = 100.0 - sx, sy
            best = None; best_d = 1e9
            for dr in dst_refs:
                if dr in used: continue
                dx, dy = info[dr]['x'], info[dr]['y']
                d = math.hypot(dx - ex, dy - ey)
                if d < best_d:
                    best_d = d; best = dr
            if best: used.add(best); pairs.append((src, best, best_d))

    pairs.sort(key=lambda p: p[2])
    print(f"Total CH1↔CH2 role-paired refs: {len(pairs)}")
    buckets = {'<0.5mm': 0, '0.5-1mm': 0, '1-2mm': 0, '2-5mm': 0, '5-10mm': 0, '>10mm': 0}
    for src, dst, d in pairs:
        if d < 0.5: buckets['<0.5mm'] += 1
        elif d < 1.0: buckets['0.5-1mm'] += 1
        elif d < 2.0: buckets['1-2mm'] += 1
        elif d < 5.0: buckets['2-5mm'] += 1
        elif d < 10.0: buckets['5-10mm'] += 1
        else: buckets['>10mm'] += 1
    for k, v in buckets.items():
        print(f"  {k}: {v}")
    print(f"\nFailing pairs (Δ > 0.5mm):")
    fail_pairs = [p for p in pairs if p[2] > 0.5]
    for src, dst, d in fail_pairs[-20:]:
        print(f"  {src} → {dst}: Δ={d:.2f}mm  CH1_lib={info[src]['lib']}")


if __name__ == "__main__":
    main()
