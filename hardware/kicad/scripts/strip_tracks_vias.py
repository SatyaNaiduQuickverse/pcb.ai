#!/usr/bin/env python3
"""strip_tracks_vias.py — Remove all PCB_TRACK + PCB_VIA from a board.

Preserves footprints, pads, zones, edge.cuts, silk, courtyards.
Used to give the lever-Z route-hardest-first phase a CLEAN canonical
to exercise true hardest-first ordering (residuals get first dibs at
J18/J19 corridors before any greedy main-pass commits foreign copper).

Usage:
    python3 strip_tracks_vias.py <input.kicad_pcb> <output.kicad_pcb>
"""
from __future__ import annotations
import sys
import pcbnew


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    in_path, out_path = sys.argv[1], sys.argv[2]
    b = pcbnew.LoadBoard(in_path)

    # Snapshot pre-strip census for verification
    pre_tracks = pre_vias = 0
    pre_zones = len(list(b.Zones()))
    pre_fps = len(list(b.Footprints()))
    for t in b.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            pre_vias += 1
        else:
            pre_tracks += 1

    # Collect everything to remove (don't mutate while iterating)
    to_remove = list(b.GetTracks())
    for t in to_remove:
        b.Remove(t)

    # Post-strip census + invariant checks
    post_tracks = post_vias = 0
    for t in b.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            post_vias += 1
        else:
            post_tracks += 1
    post_zones = len(list(b.Zones()))
    post_fps = len(list(b.Footprints()))

    pcbnew.SaveBoard(out_path, b)

    print(f"Pre-strip:  tracks={pre_tracks}  vias={pre_vias}  "
          f"zones={pre_zones}  footprints={pre_fps}")
    print(f"Post-strip: tracks={post_tracks}  vias={post_vias}  "
          f"zones={post_zones}  footprints={post_fps}")
    if post_tracks or post_vias:
        print(f"FAIL: residual {post_tracks} tracks + {post_vias} vias",
              file=sys.stderr)
        return 1
    if post_zones != pre_zones or post_fps != pre_fps:
        print(f"FAIL: zone or footprint count changed", file=sys.stderr)
        return 1
    print(f"OK: stripped board saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
