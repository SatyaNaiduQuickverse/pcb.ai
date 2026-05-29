#!/usr/bin/env python3
"""j19_micro_relief.py — codified J19 DRV8300 micro-relief tool (CH1 30/30 lever B+).

Per Sai 2026-05-29 directive (Option A approved): execute J19_CH1 +1.5mm NORTH
micro-relief move; Phase 5 R19 mirror cascade to J19_CH2/CH3/CH4 (currently
off-board parked at J24/J25/J26 references) is DEFERRED until CH2/3/4 placement
work completes.

Discipline:
  R21 (worker deviation disclosure) — CH1-only move + Phase 5 mirror cascade
    deferral is a DOCUMENTED structural deviation. CH2/3/4 channel circuits
    are NOT placed at canonical 085dee9 era; mirror targets J24/J25/J26 are
    kinet2pcb-parked at (215, -25) region. R19 cross-channel symmetry cannot
    be enforced until those are placed (Phase 5 scope, ~40-80 hours per
    channel × 3 = 120-240 hours).
  R19 (symmetry preserves work) — VIOLATED for J19 cross-channel post-this-move.
    Tagged as PHASE_5_R19_DEBT in provenance; Phase 5 R19 enforcement gate
    will enforce identical mirror moves on J24/J25/J26 when they become
    placed.

Usage:
    python3 j19_micro_relief.py <input.kicad_pcb> <output.kicad_pcb>
        [--dy -1.5]   # default: 1.5mm NORTH (decrease Y in KiCad y-down convention)

For Phase 5: extend MIRROR_TARGETS to include CH2/3/4 once those drivers are
placed. The script will then apply identical delta to all 4 instances and
verify R19 mirror invariant.
"""
from __future__ import annotations
import argparse
import json
import math
import pathlib
import sys
import time
import pcbnew


# ─── Configuration ────────────────────────────────────────────────────────────
J19_CH1_REF = "J19"
# Phase 5 mirror targets — currently empty because CH2/3/4 drivers are
# off-board parked (J24, J25, J26 at x=215, y=-25 region).
PHASE5_MIRROR_TARGETS = {
    "CH2": "J24",   # DRV8300 — off-board parked at (215, -25)
    "CH3": "J25",   # off-board parked
    "CH4": "J26",   # off-board parked
}


def _md5(path: str) -> str:
    import hashlib
    return hashlib.md5(pathlib.Path(path).read_bytes()).hexdigest()


def _is_on_board(pos_mm: tuple, margin: float = 5.0) -> bool:
    x, y = pos_mm
    return (-margin <= x <= 100 + margin) and (-margin <= y <= 100 + margin)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--dx", type=float, default=0.0, help="X delta in mm")
    ap.add_argument("--dy", type=float, default=-1.5,
                    help="Y delta in mm (default -1.5 = NORTH per KiCad y-down convention)")
    ap.add_argument("--enforce-mirror", action="store_true",
                    help="Phase 5: enforce R19 mirror cascade to J24/J25/J26 "
                         "(REQUIRES CH2/3/4 drivers to be on-board first)")
    ap.add_argument("--provenance",
                    default="sims/routing_provenance/j19_micro_relief",
                    help="provenance dir")
    args = ap.parse_args()

    board = pcbnew.LoadBoard(args.input)
    j19 = None
    for f in board.GetFootprints():
        if f.GetReference() == J19_CH1_REF:
            j19 = f
            break
    if j19 is None:
        print(f"FAIL: {J19_CH1_REF} not found", file=sys.stderr)
        return 1

    # Verify J19 is DRV8300 HVQFN-24
    fpid = str(j19.GetFPID().GetLibItemName())
    if "HVQFN-24" not in fpid:
        print(f"WARN: J19 footprint is {fpid!r} (expected HVQFN-24); "
              f"proceeding but verify J19 is the DRV8300 gate driver",
              file=sys.stderr)

    old_pos = j19.GetPosition()
    old_xy = (old_pos.x / 1e6, old_pos.y / 1e6)
    new_xy = (old_xy[0] + args.dx, old_xy[1] + args.dy)

    # Mirror cascade check
    mirror_state = {}
    deviation_flags = []
    for ch, ref in PHASE5_MIRROR_TARGETS.items():
        m = None
        for f in board.GetFootprints():
            if f.GetReference() == ref:
                m = f
                break
        if m is None:
            mirror_state[ch] = {"ref": ref, "status": "NOT_FOUND"}
            continue
        mpos = m.GetPosition()
        mxy = (mpos.x / 1e6, mpos.y / 1e6)
        on_board = _is_on_board(mxy)
        mirror_state[ch] = {
            "ref": ref,
            "pos": mxy,
            "on_board": on_board,
            "status": "ON_BOARD" if on_board else "OFF_BOARD_PARKED",
        }
        if not on_board:
            deviation_flags.append(
                f"{ch} mirror target {ref} at {mxy} is off-board parked "
                f"(Phase 5 placement scope); R19 cross-channel mirror "
                f"DEFERRED")

    if args.enforce_mirror:
        # Phase 5: actually move the mirrors
        all_on_board = all(s.get("on_board", False) for s in mirror_state.values())
        if not all_on_board:
            print(f"FAIL: --enforce-mirror requires ALL mirrors on-board; "
                  f"current state:", file=sys.stderr)
            for ch, s in mirror_state.items():
                print(f"  {ch}: {s}", file=sys.stderr)
            return 2
        # Apply identical delta to each mirror (CH-to-CH transform is
        # subsystem-zone offset; same DX/DY adds the same physical relief
        # in each channel's local frame because zones are pure mirror
        # transforms per R19).
        for ch, s in mirror_state.items():
            for f in board.GetFootprints():
                if f.GetReference() == s["ref"]:
                    p = f.GetPosition()
                    f.SetPosition(pcbnew.VECTOR2I(
                        int((p.x / 1e6 + args.dx) * 1e6),
                        int((p.y / 1e6 + args.dy) * 1e6)))
                    break

    # Apply J19_CH1 move
    j19.SetPosition(pcbnew.VECTOR2I(int(new_xy[0] * 1e6),
                                     int(new_xy[1] * 1e6)))
    pcbnew.SaveBoard(args.output, board)

    # Provenance
    prov_dir = pathlib.Path(args.provenance)
    prov_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    prov = {
        "lever": "B+ J19 micro-relief (CH1 30/30 close-out)",
        "approval": "Sai 2026-05-29 Option A",
        "j19_ch1": {
            "ref": J19_CH1_REF,
            "footprint": fpid,
            "from": old_xy,
            "to": new_xy,
            "delta_mm": (args.dx, args.dy),
            "direction_label": f"NORTH +{abs(args.dy):.1f}mm" if args.dy < 0 else
                               f"SOUTH +{args.dy:.1f}mm" if args.dy > 0 else "no-Y-move",
        },
        "mirror_state": mirror_state,
        "deviation_flags_R21": deviation_flags,
        "phase_5_debt": "R19 cross-channel mirror cascade DEFERRED until "
                         "CH2/3/4 drivers (J24/J25/J26) placed; tag = "
                         "PHASE_5_R19_DEBT",
        "input_md5": _md5(args.input),
        "output_md5": _md5(args.output),
        "timestamp_utc": ts,
    }
    prov_path = prov_dir / f"j19_relief_{ts}.json"
    prov_path.write_text(json.dumps(prov, indent=2))

    print(f"\nJ19 {J19_CH1_REF} ({fpid}) moved:")
    print(f"  {old_xy} → {new_xy}")
    print(f"  delta: ({args.dx:+.2f}, {args.dy:+.2f}) mm "
          f"= {prov['j19_ch1']['direction_label']}")
    print(f"\nMirror cascade state (Phase 5 deferred):")
    for ch, s in mirror_state.items():
        print(f"  {ch} ({s['ref']}): {s['status']}")
    if deviation_flags:
        print(f"\nR21 deviation disclosure ({len(deviation_flags)} flag(s)):")
        for d in deviation_flags:
            print(f"  - {d}")
    print(f"\nOutput: {args.output}")
    print(f"Provenance: {prov_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
