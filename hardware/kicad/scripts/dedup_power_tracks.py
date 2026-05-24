#!/usr/bin/env python3
"""dedup_power_tracks.py — Remove duplicate power-net tracks (mirror/aggressive overlaps).

After multi-pass routing (Phase A + mirror + aggressive), power nets accumulate
duplicate parallel tracks (same start/end/layer/net). Remove duplicates.
"""
import pcbnew


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def main():
    b = pcbnew.LoadBoard(PCB)
    seen = {}
    to_remove = []
    for t in b.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA): continue
        s = t.GetStart(); e = t.GetEnd()
        # Normalize: smaller endpoint first
        sk = (s.x, s.y, e.x, e.y) if (s.x, s.y) < (e.x, e.y) else (e.x, e.y, s.x, s.y)
        key = (sk, t.GetLayer(), t.GetNetname() or '', t.GetWidth())
        if key in seen:
            to_remove.append(t)
        else:
            seen[key] = t
    print(f"Removing {len(to_remove)} duplicate tracks")
    for t in to_remove:
        b.Remove(t)
    b.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
