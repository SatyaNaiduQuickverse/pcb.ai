#!/usr/bin/env python3
"""route_mirror_ch1_to_ch234.py — Phase 5b Task #80.

Given CH1 routes drawn (by autoroute or hand), emit equivalent CH2/CH3/CH4
routes via the locked transforms:
  CH2 = mirror_X(50):    (x, y) → (100-x, y)
  CH3 = 180°-rot(50,50): (x, y) → (100-x, 100-y)
  CH4 = mirror_Y(50):    (x, y) → (x, 100-y)

For each CH1 track or via:
  - Copy track width / drill / diameter
  - Copy layer (F.Cu↔B.Cu swap on Y-mirror? NO — locked behavior preserves
    layer for in-plane mirrors; FETs are on B.Cu in all 4 channels by design)
  - Net assignment: replace _CH1 suffix with target channel suffix; create
    the target net if not present in board.

Usage:
  python3 route_mirror_ch1_to_ch234.py [ch2|ch3|ch4|all]

Self-test mode:
  python3 route_mirror_ch1_to_ch234.py --self-test
  Adds a stub CH1 trace at (10, 60)→(20, 60) F.Cu net BEMF_A_CH1, runs
  mirror, verifies CH2/CH3/CH4 tracks emerged at correct geometry.
"""
import pcbnew
import sys
import re

PCB_PATH = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"

# Locked mirror transforms (X=50, Y=50 axes)
TRANSFORMS = {
    'ch2': lambda x, y: (100.0 - x, y),
    'ch3': lambda x, y: (100.0 - x, 100.0 - y),
    'ch4': lambda x, y: (x, 100.0 - y),
}


def get_or_create_net(board, netname):
    """Find existing net by name; create if absent. Returns the net pointer."""
    netinfo = board.GetNetInfo()
    existing = netinfo.GetNetItem(netname)
    if existing and existing.GetNetCode() > 0:
        return existing
    new_net = pcbnew.NETINFO_ITEM(board, netname)
    board.Add(new_net)
    return new_net


def channel_net_name(ch1_netname, target_ch):
    """Map _CH1 suffix to target channel suffix.
    Also handles N$nn nets (no channel suffix) — keeps unchanged (shared)."""
    return re.sub(r'_CH1$', f'_CH{target_ch}', ch1_netname)


def mm_to_iu(x_mm):
    return pcbnew.FromMM(x_mm)


def iu_to_mm(x_iu):
    return pcbnew.ToMM(x_iu)


def mirror_tracks(board, target_ch):
    """For each CH1-net track/via on board, emit mirrored copy on target_ch."""
    if target_ch == 'ch2':
        ch_num = 2
    elif target_ch == 'ch3':
        ch_num = 3
    elif target_ch == 'ch4':
        ch_num = 4
    else:
        raise ValueError(f"Bad target_ch: {target_ch}")

    transform = TRANSFORMS[target_ch]

    # Collect CH1 source items first (don't iterate + mutate)
    ch1_tracks = []
    ch1_vias = []
    for item in board.GetTracks():
        try:
            nn = item.GetNet().GetNetname()
        except Exception:
            continue
        if not nn.endswith('_CH1'):
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            ch1_vias.append(item)
        elif isinstance(item, pcbnew.PCB_TRACK):
            ch1_tracks.append(item)

    n_tracks_added = 0
    n_vias_added = 0

    for trk in ch1_tracks:
        s = trk.GetStart()
        e = trk.GetEnd()
        s_mm = (iu_to_mm(s.x), iu_to_mm(s.y))
        e_mm = (iu_to_mm(e.x), iu_to_mm(e.y))
        ns_mm = transform(*s_mm)
        ne_mm = transform(*e_mm)
        new_netname = channel_net_name(trk.GetNet().GetNetname(), ch_num)
        new_net = get_or_create_net(board, new_netname)
        new_trk = pcbnew.PCB_TRACK(board)
        new_trk.SetStart(pcbnew.VECTOR2I(mm_to_iu(ns_mm[0]), mm_to_iu(ns_mm[1])))
        new_trk.SetEnd(pcbnew.VECTOR2I(mm_to_iu(ne_mm[0]), mm_to_iu(ne_mm[1])))
        new_trk.SetWidth(trk.GetWidth())
        new_trk.SetLayer(trk.GetLayer())
        new_trk.SetNet(new_net)
        board.Add(new_trk)
        n_tracks_added += 1

    for v in ch1_vias:
        p = v.GetPosition()
        p_mm = (iu_to_mm(p.x), iu_to_mm(p.y))
        np_mm = transform(*p_mm)
        new_netname = channel_net_name(v.GetNet().GetNetname(), ch_num)
        new_net = get_or_create_net(board, new_netname)
        new_via = pcbnew.PCB_VIA(board)
        new_via.SetPosition(pcbnew.VECTOR2I(mm_to_iu(np_mm[0]), mm_to_iu(np_mm[1])))
        new_via.SetWidth(v.GetWidth())
        new_via.SetDrill(v.GetDrillValue())
        # Layer pair preserve via LayerPair() tuple (KiCad 9 API)
        try:
            pair = v.LayerPair()
            new_via.SetLayerPair(pair[0], pair[1])
        except Exception:
            # Fallback: assume through-hole F.Cu ↔ B.Cu
            new_via.SetTopLayer(pcbnew.F_Cu)
            new_via.SetBottomLayer(pcbnew.B_Cu)
        new_via.SetNet(new_net)
        board.Add(new_via)
        n_vias_added += 1

    return n_tracks_added, n_vias_added


def verify_mirror(board, target_ch):
    """Quick geometric check: for each CH1 track, find a target_ch track
    whose endpoints satisfy the transform. Return (matched, total)."""
    transform = TRANSFORMS[target_ch]
    target_suffix = f"_CH{target_ch[-1]}"

    ch1_segs = []
    target_segs = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        try:
            nn = item.GetNet().GetNetname()
        except Exception:
            continue
        s = item.GetStart()
        e = item.GetEnd()
        seg = ((iu_to_mm(s.x), iu_to_mm(s.y)),
               (iu_to_mm(e.x), iu_to_mm(e.y)),
               item.GetLayer(), item.GetWidth())
        if nn.endswith('_CH1'):
            ch1_segs.append(seg)
        elif nn.endswith(target_suffix):
            target_segs.append(seg)

    matched = 0
    for (s, e, layer, w) in ch1_segs:
        exp_s = transform(*s)
        exp_e = transform(*e)
        for ts, te, tl, tw in target_segs:
            if (abs(ts[0] - exp_s[0]) < 0.01 and abs(ts[1] - exp_s[1]) < 0.01
                    and abs(te[0] - exp_e[0]) < 0.01 and abs(te[1] - exp_e[1]) < 0.01
                    and tl == layer and tw == w):
                matched += 1
                break
    return matched, len(ch1_segs)


def self_test():
    """Insert a stub CH1 trace, mirror to all 3 channels, verify."""
    board = pcbnew.LoadBoard(PCB_PATH)

    # Snapshot existing track count
    pre_count = sum(1 for _ in board.GetTracks())

    # Insert stub CH1 trace at (10, 60) → (20, 60) on F.Cu
    bemf_a_ch1 = get_or_create_net(board, "BEMF_A_CH1")
    stub = pcbnew.PCB_TRACK(board)
    stub.SetStart(pcbnew.VECTOR2I(mm_to_iu(10.0), mm_to_iu(60.0)))
    stub.SetEnd(pcbnew.VECTOR2I(mm_to_iu(20.0), mm_to_iu(60.0)))
    stub.SetWidth(pcbnew.FromMM(0.2))
    stub.SetLayer(pcbnew.F_Cu)
    stub.SetNet(bemf_a_ch1)
    board.Add(stub)
    print("Self-test: added stub CH1 track at (10,60)→(20,60) F.Cu net=BEMF_A_CH1")

    # Mirror to ch2, ch3, ch4
    for ch in ('ch2', 'ch3', 'ch4'):
        nt, nv = mirror_tracks(board, ch)
        print(f"  {ch}: mirrored {nt} tracks, {nv} vias")

    # Verify
    all_pass = True
    expected_positions = {
        'ch2': ((90.0, 60.0), (80.0, 60.0)),
        'ch3': ((90.0, 40.0), (80.0, 40.0)),
        'ch4': ((10.0, 40.0), (20.0, 40.0)),
    }
    for ch, (exp_s, exp_e) in expected_positions.items():
        target_suffix = f"_CH{ch[-1]}"
        found = False
        for item in board.GetTracks():
            if isinstance(item, pcbnew.PCB_VIA):
                continue
            try:
                nn = item.GetNet().GetNetname()
            except Exception:
                continue
            if not nn.endswith(target_suffix):
                continue
            s = (iu_to_mm(item.GetStart().x), iu_to_mm(item.GetStart().y))
            e = (iu_to_mm(item.GetEnd().x), iu_to_mm(item.GetEnd().y))
            if (abs(s[0] - exp_s[0]) < 0.01 and abs(s[1] - exp_s[1]) < 0.01
                    and abs(e[0] - exp_e[0]) < 0.01 and abs(e[1] - exp_e[1]) < 0.01):
                found = True
                print(f"  {ch}: ✓ found mirrored trace at {s}→{e}")
                break
        if not found:
            print(f"  {ch}: ✗ MISSING mirrored trace at expected {exp_s}→{exp_e}")
            all_pass = False

    # Don't save — self-test is non-destructive
    print(f"\nSelf-test: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    if args[0] == '--self-test':
        return self_test()

    target_chs = []
    for a in args:
        if a == 'all':
            target_chs = ['ch2', 'ch3', 'ch4']
            break
        if a in ('ch2', 'ch3', 'ch4'):
            target_chs.append(a)
    if not target_chs:
        print("Usage: route_mirror_ch1_to_ch234.py [ch2|ch3|ch4|all|--self-test]")
        return 1

    board = pcbnew.LoadBoard(PCB_PATH)
    total_tracks = 0
    total_vias = 0
    for ch in target_chs:
        nt, nv = mirror_tracks(board, ch)
        print(f"{ch}: mirrored {nt} tracks, {nv} vias")
        total_tracks += nt
        total_vias += nv
        matched, expected = verify_mirror(board, ch)
        print(f"  verify: {matched}/{expected} CH1 segments have correct {ch} mirror")
    board.Save(PCB_PATH)
    print(f"\nSaved {PCB_PATH}")
    print(f"Total: {total_tracks} tracks + {total_vias} vias mirrored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
