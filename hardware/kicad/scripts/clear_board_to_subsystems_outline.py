#!/usr/bin/env python3
"""clear_board_to_subsystems_outline.py — Phase 4-v2 clean-slate.

Strips all components except mount holes + fiducials. Keeps board outline,
edge cuts, zones (planes), and stackup. Result: empty board ready for
per-subsystem clean-slate placement.

Per master Phase 4-v2 Step 2 directive (autonomous master decision):
  Each subsystem PR starts from empty board state and adds only ITS
  components. Cumulative state builds via successive subsystem merges.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"
OUT = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1_empty.kicad_pcb"


def main():
    b = pcbnew.LoadBoard(PCB)
    # Keep: mount holes (H1-H4) + fiducials (FID*)
    to_remove_fps = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith('H') and len(ref) > 1 and ref[1:].isdigit():
            continue  # keep mount hole
        if ref.startswith('FID'):
            continue  # keep fiducial
        to_remove_fps.append(fp)
    print(f"Removing {len(to_remove_fps)} footprints (keeping {len(list(b.GetFootprints())) - len(to_remove_fps)})")
    for fp in to_remove_fps:
        b.Remove(fp)

    # Remove all tracks + vias
    to_remove_tracks = list(b.GetTracks())
    for t in to_remove_tracks:
        b.Remove(t)
    print(f"Removed {len(to_remove_tracks)} tracks/vias")

    # KEEP: zones (planes), edge cuts (board outline), graphical drawings.
    b.Save(OUT)
    print(f"Empty board saved to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
