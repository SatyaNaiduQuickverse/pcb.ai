#!/usr/bin/env python3
"""audit_k3_chain_pitch_collision.py — G_K3_CHAIN_PITCH_COLLISION binding gate.

Lever EE (2026-05-30): K3 multi-mech chain emitter previously excluded WHOLE
footprints from its halo check via `exclude_refs=own_refs`. For routes
ending at fine-pitch HDI pads (J18 / J19 0.5mm pitch), this masked
sibling-pin collisions — the via at one pad collided with neighbor pads
of the same footprint, surfacing as DRC `shorting_items` at fab.

This gate runs at-MERGE on a routed .kicad_pcb: walk every via, find any
that sits inside (or within (via_pad_radius + clearance) of) an HDI
whitelist footprint pad of a foreign net. Such a via is a K3-chain
pitch-collision — REFUSE per shorts-gate semantics.

Exit 0 = no chain-collision vias found.
Exit 1 = ≥1 chain-collision via detected.

Usage:
    python3 audit_k3_chain_pitch_collision.py <board.kicad_pcb>
        [--hdi-refs J18,J19] [--clearance-mm 0.10]
"""
from __future__ import annotations
import argparse
import math
import os
import sys
from typing import List, Tuple

import pcbnew


# SSoT-mirror: route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS
DEFAULT_HDI_REFS = ("J18", "J19")
# Through-via pad / drill (route_subsystem_cooperative SSoT)
THROUGH_PAD_MM = 0.60
HDI_BLIND_PAD_MM = 0.30
HDI_MICROVIA_PAD_MM = 0.25
# Default fab clearance (board std 0.10mm)
DEFAULT_CLEARANCE_MM = 0.10


def _via_pad_radius_mm(via) -> float:
    """Return outer pad radius (mm) of a via. Uses VIATYPE_* to map
    to canonical pad geometry."""
    try:
        vt = via.GetViaType()
        if vt == pcbnew.VIATYPE_THROUGH:
            return THROUGH_PAD_MM / 2.0
        if vt == pcbnew.VIATYPE_BLIND_BURIED:
            return HDI_BLIND_PAD_MM / 2.0
        if vt == pcbnew.VIATYPE_MICROVIA:
            return HDI_MICROVIA_PAD_MM / 2.0
    except Exception:                                              # pragma: no cover
        pass
    # Fallback: query the via's reported width on F.Cu
    try:
        return via.GetWidth(pcbnew.F_Cu) / 1e6 / 2.0
    except TypeError:
        return via.GetWidth() / 1e6 / 2.0


def audit(board_path: str, hdi_refs: Tuple[str, ...],
          clearance_mm: float) -> Tuple[int, List[str]]:
    board = pcbnew.LoadBoard(board_path)
    issues: List[str] = []

    # Build the HDI pad map (ref, padname, x_mm, y_mm, half_x, half_y, netname)
    hdi_pads = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in hdi_refs:
            continue
        for pad in fp.Pads():
            pos = pad.GetPosition()
            size = pad.GetSize()
            try:
                pad_name = pad.GetPadName() if hasattr(pad, "GetPadName") \
                           else pad.GetNumber()
            except Exception:                                      # pragma: no cover
                pad_name = ""
            try:
                netname = pad.GetNetname() if pad.GetNet() else ""
            except Exception:                                      # pragma: no cover
                netname = ""
            hdi_pads.append((ref, pad_name, pos.x / 1e6, pos.y / 1e6,
                              size.x / 1e6 / 2.0, size.y / 1e6 / 2.0,
                              netname))

    if not hdi_pads:
        print(f"G_K3_CHAIN_PITCH_COLLISION audit @ {board_path}")
        print(f"  no HDI whitelist footprints {hdi_refs} found — vacuous PASS")
        return 0, []

    # Walk every via, find foreign-net collisions with HDI pads
    n_vias = n_chain_vias = 0
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        n_vias += 1
        via_pos = t.GetPosition()
        vx, vy = via_pos.x / 1e6, via_pos.y / 1e6
        try:
            via_net = t.GetNetname() if t.GetNet() else ""
        except Exception:                                          # pragma: no cover
            via_net = ""
        via_radius = _via_pad_radius_mm(t)
        # required edge-to-edge clearance: via_radius + pad_half + clearance
        for (pref, ppad, px, py, hx, hy, pnet) in hdi_pads:
            # Skip same-net (the via and pad are part of the same circuit
            # — the via at the pad is intentional).
            if via_net and pnet and via_net == pnet:
                continue
            # Pad bbox extents
            x_min, y_min = px - hx, py - hy
            x_max, y_max = px + hx, py + hy
            # Closest point on pad bbox to via center
            dx = max(x_min - vx, 0, vx - x_max)
            dy = max(y_min - vy, 0, vy - y_max)
            d = math.hypot(dx, dy)
            required = via_radius + clearance_mm
            if d < required:
                n_chain_vias += 1
                issues.append(
                    f"via@({vx:.3f},{vy:.3f}) net={via_net!r} r={via_radius:.3f}mm "
                    f"vs HDI pad {pref}.{ppad} net={pnet!r} at ({px:.3f},{py:.3f}) "
                    f"d={d:.3f}mm < required {required:.3f}mm")
                break    # report once per via

    print(f"G_K3_CHAIN_PITCH_COLLISION audit @ {board_path}")
    print(f"  HDI refs: {hdi_refs}, clearance {clearance_mm:.3f}mm")
    print(f"  vias scanned: {n_vias}, HDI pads scanned: {len(hdi_pads)}")
    print(f"  chain-collision vias: {n_chain_vias}")
    if n_chain_vias:
        print("\n❌ FAIL — K3 chain emit pitch collisions detected:")
        for s in issues[:20]:
            print(f"  - {s}")
        if len(issues) > 20:
            print(f"  ... ({len(issues)-20} more)")
        return 1, issues
    print("\n✅ PASS — no via collides with foreign-net HDI pads")
    return 0, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--hdi-refs", default="J18,J19",
                    help="comma-sep HDI whitelist refs (default J18,J19)")
    ap.add_argument("--clearance-mm", type=float, default=DEFAULT_CLEARANCE_MM,
                    help=f"fab clearance (default {DEFAULT_CLEARANCE_MM}mm)")
    args = ap.parse_args(argv)
    refs = tuple(r.strip() for r in args.hdi_refs.split(",") if r.strip())
    code, _ = audit(args.board, refs, args.clearance_mm)
    return code


if __name__ == "__main__":
    sys.exit(main())
