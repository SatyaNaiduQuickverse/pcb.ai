#!/usr/bin/env python3
"""mirror_bemf_clean.py — Delete CH2/3/4 BEMF tracks, then mirror CH1 BEMF cleanly.

For sensorless commutation timing, BEMF nets must mirror geometrically across
all 4 channels. Master 2026-05-24 REJECT: BEMF length spread must be <20%.

Strategy:
  1. Find CH1 BEMF_*_CH1 tracks
  2. Delete ALL BEMF_*_CH{2,3,4} existing tracks
  3. For each CH1 BEMF track, generate CH2 (mirror_X), CH3 (180°-rot),
     CH4 (mirror_Y) and assign to matching CH2/3/4 net
"""
import pcbnew
import re


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def mirror_pos(x, y, ch):
    if ch == 2: return (100.0 - x, y)
    if ch == 3: return (100.0 - x, 100.0 - y)
    if ch == 4: return (x, 100.0 - y)
    raise ValueError


def find_net(board, name):
    for n in board.GetNetsByName().values():
        if n.GetNetname() == name: return n
    return None


def main():
    board = pcbnew.LoadBoard(PCB)
    # Collect CH1 BEMF tracks (snapshot)
    ch1_tracks = []
    for t in board.GetTracks():
        nname = t.GetNetname() or ''
        if re.match(r'BEMF_[ABC]_CH1$', nname):
            ch1_tracks.append((t, nname))

    # Delete all CH2/3/4 BEMF tracks
    to_delete = []
    for t in board.GetTracks():
        nname = t.GetNetname() or ''
        if re.match(r'BEMF_[ABC]_CH([234])$', nname):
            to_delete.append(t)
    print(f"Deleting {len(to_delete)} CH2/3/4 BEMF tracks")
    for t in to_delete:
        board.Remove(t)

    # Mirror CH1 tracks to CH2/3/4
    added = 0
    for t, ch1_net in ch1_tracks:
        phase = ch1_net[len('BEMF_'):len('BEMF_A')]  # 'A', 'B', or 'C'
        for ch in (2, 3, 4):
            dst_net_name = f'BEMF_{phase}_CH{ch}'
            dst_net = find_net(board, dst_net_name)
            if dst_net is None: continue
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
                mx, my = mirror_pos(x, y, ch)
                v = pcbnew.PCB_VIA(board)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetPosition(pcbnew.VECTOR2I(int(mx*1e6), int(my*1e6)))
                v.SetDrill(t.GetDrill())
                v.SetWidth(t.GetWidth())
                v.SetNet(dst_net)
                board.Add(v)
            else:
                s = t.GetStart(); e = t.GetEnd()
                sx, sy = pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)
                ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
                msx, msy = mirror_pos(sx, sy, ch)
                mex, mey = mirror_pos(ex, ey, ch)
                nt = pcbnew.PCB_TRACK(board)
                nt.SetStart(pcbnew.VECTOR2I(int(msx*1e6), int(msy*1e6)))
                nt.SetEnd(pcbnew.VECTOR2I(int(mex*1e6), int(mey*1e6)))
                nt.SetLayer(t.GetLayer())
                nt.SetWidth(t.GetWidth())
                nt.SetNet(dst_net)
                board.Add(nt)
            added += 1
    print(f"Added {added} mirrored BEMF tracks/vias")
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
