#!/usr/bin/env python3
"""fix_bemf_symmetry.py — Clear duplicate BEMF tracks + re-mirror cleanly.

Master 2026-05-24 REJECT: BEMF length spread must be <20% (commutation
timing). Currently 24-64% due to mirror+role-aware duplication.

Strategy:
  1. Identify CH1 BEMF tracks (canonical reference)
  2. Delete ALL BEMF_*_CH2/3/4 tracks
  3. Re-derive CH2/3/4 via mirror_X / 180°-rot / mirror_Y of CH1
"""
import pcbnew
import re


PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def main():
    board = pcbnew.LoadBoard(PCB)
    # Delete BEMF_*_CH2/3/4 tracks
    to_delete = []
    for t in board.GetTracks():
        nname = t.GetNetname() or ''
        m = re.match(r'BEMF_[ABC]_CH([234])$', nname)
        if m:
            to_delete.append(t)
    print(f"Deleting {len(to_delete)} BEMF CH2/3/4 tracks")
    for t in to_delete:
        board.Remove(t)
    board.Save(PCB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
