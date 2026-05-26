#!/usr/bin/env python3
"""migrate_footprints.py — Phase 4-v3 in-place footprint corrections.

One-time, in-place pcbnew footprint swap (NO kinet2pcb re-import — avoids the
[[reference-kinet2pcb-silent-drop]] net-drop trap; master+Sai 2026-05-25 path ii):

  • 12 motor phase pads (TP19-42)  TestPoint_Pad_D3.0mm → pcbai:ESCMotorPad_4x4mm_5via
       target read from mechanical_anchors.yaml (motor_pads category, SSoT)
  • 4  bulk caps (C1-C4)           CP_Elec_10x14.3      → Capacitor_SMD:CP_Elec_8x6.2
       Sai-locked option (ζ): Nichicon PCH1V151MCL1GS 150µF/35V

Run once during REDO setup. Footprint is independent of position, so order vs
park/bring does not matter. Each swap preserves the component's
reference/value/position/orientation/layer and re-binds every pad of the new
footprint to the old pad's net (single-pad-number footprints like the motor pad
inherit the one net on all pads).

IMPORTANT — one swap PER SUBPROCESS: KiCad's pcbnew SWIG bindings accumulate an
object-table corruption when multiple Remove/Add footprint mutations run in one
process (FindFootprintByReference / GetFPID start returning raw SwigPyObject).
Verified: a single load→swap→save per process is reliable; batching in one
process is not. So the orchestrator spawns a fresh `--swap-one` worker per ref.

Usage:
  python3 migrate_footprints.py --in BOARD --out BOARD [--report]
  python3 migrate_footprints.py --swap-one --board B --ref R --target FP   (worker)
"""
import argparse
import glob
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pcbnew
import lockfile

PCBAI_LIB = str(Path(__file__).resolve().parents[1] / "pcbai.pretty")
SYS_FP_DIR = "/usr/share/kicad/footprints"
CAP_TARGET = {f"C{i}": "CP_Elec_8x6.2" for i in range(1, 5)}  # Sai (ζ) 2026-05-25


def resolve_lib(fp_name):
    if (Path(PCBAI_LIB) / f"{fp_name}.kicad_mod").exists():
        return PCBAI_LIB
    hits = glob.glob(f"{SYS_FP_DIR}/*.pretty/{fp_name}.kicad_mod")
    return str(Path(hits[0]).parent) if hits else None


def build_targets(board_path=None):
    """ref -> target bare footprint name, for every ref whose footprint changes."""
    targets = dict(CAP_TARGET)
    # Anchors whose lockfile footprint differs from the imported one: motor pads
    # (→ESCMotorPad) and connectors (J1→AMASS XT30; J12/J14 already JST → no-op).
    for ref, a in lockfile.load_anchors().items():
        if a.get("category") in ("motor_pads", "connectors") and a.get("footprint"):
            targets[ref] = a["footprint"]
    # OQ-013: the SMBJ33A TVS clamps (motor-phase D26/29/32 + CH2-4 mirrors, input
    # D1) were authored as Diode_SMD:D_SMA — but SMBJ33A is a DO-214AA (SMB) part;
    # SMB pads (~3.0mm span) do not fit D_SMA's undersized ~1.8mm pads (won't solder
    # reliably). Correct DO-214AA = D_SMB. Value-based so every instance is caught.
    # Root fix belongs in the SKiDL schematic (tracked OQ-013); this is the same
    # post-import correction lane as the bulk caps / motor pads above.
    if board_path:
        b = pcbnew.LoadBoard(board_path)
        for fp in b.GetFootprints():
            if (fp.GetValue() or "") == "SMBJ33A" and \
                    fp.GetFPID().GetLibItemName() != "D_SMB":
                targets[fp.GetReference()] = "D_SMB"
    return targets


def swap_one(board_path, ref, target):
    """Single swap in this (fresh) process; loads, swaps, saves. Returns status."""
    board = pcbnew.LoadBoard(board_path)
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        return "absent"
    if fp.GetFPID().GetLibItemName() == target:
        return "already"
    lib = resolve_lib(target)
    if lib is None:
        return f"ERR:{target} not found"
    new = pcbnew.FootprintLoad(lib, target)
    if new is None:
        return f"ERR:FootprintLoad {target}"
    nickname = "pcbai" if lib == PCBAI_LIB else Path(lib).stem
    # Snapshot the old placement + nets before mutating the board.
    pos, orient, flipped = fp.GetPosition(), fp.GetOrientation(), fp.IsFlipped()
    val = fp.GetValue()
    old_nets = {}
    for p in fp.Pads():
        old_nets.setdefault(p.GetPadName(), p.GetNet())
    new.SetFPID(pcbnew.LIB_ID(nickname, target))
    new.SetReference(ref)
    new.SetValue(val)
    # Add to the board BEFORE Flip(): pcbnew segfaults flipping a board-less
    # footprint. Only triggers for parts already on B.Cu (e.g. the flipped TVS
    # clamp D26); the non-flipped instances skipped this branch and masked it.
    board.Remove(fp)
    board.Add(new)
    new.SetPosition(pos)
    if flipped:
        new.Flip(pos, False)
    new.SetOrientation(orient)
    fallback = next(iter(old_nets.values()), None)
    for p in new.Pads():
        net = old_nets.get(p.GetPadName(), fallback)
        if net is not None:
            p.SetNet(net)
    pcbnew.SaveBoard(board_path, board)
    return "swapped"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="hardware/kicad/pcbai_fpv4in1.kicad_pcb")
    ap.add_argument("--out", dest="out", default="hardware/kicad/pcbai_fpv4in1.kicad_pcb")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--swap-one", action="store_true", help="internal per-ref worker")
    ap.add_argument("--board")
    ap.add_argument("--ref")
    ap.add_argument("--target")
    args = ap.parse_args()

    if args.swap_one:
        print(swap_one(args.board, args.ref, args.target))
        return 0

    targets = build_targets(args.inp)
    print(f"footprint targets: {len(targets)} refs "
          f"({sum(1 for r in targets if r.startswith('TP'))} motor pads + "
          f"{sum(1 for r in targets if r.startswith('C'))} caps + "
          f"{sum(1 for r, t in targets.items() if t == 'D_SMB')} SMBJ33A→D_SMB)")
    if args.report:
        for r, t in sorted(targets.items()):
            print(f"  {r} → {t}")
        return 0

    # Orchestrate one fresh subprocess per swap (SWIG isolation — see docstring).
    if args.inp != args.out:
        import shutil
        shutil.copyfile(args.inp, args.out)
    tally, errs = {}, []
    for ref in sorted(targets):
        r = subprocess.run(
            [sys.executable, str(Path(__file__)), "--swap-one",
             "--board", args.out, "--ref", ref, "--target", targets[ref]],
            capture_output=True, text=True)
        status = (r.stdout.strip().splitlines() or ["ERR:no-output"])[-1]
        if status.startswith("ERR") or r.returncode != 0:
            errs.append(f"{ref}: {status or r.stderr.strip()[-120:]}")
        tally[status] = tally.get(status, 0) + 1
    print(f"result: {tally}")
    if errs:
        for e in errs:
            print(f"  {e}")
        return 1
    print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
