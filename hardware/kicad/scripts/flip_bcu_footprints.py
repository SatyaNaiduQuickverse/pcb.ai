#!/usr/bin/env python3
"""flip_bcu_footprints.py — post-place_board layer-alignment for footprints.

Per master 2026-05-24 extension: handle BOTH directions of the
text-edit-without-flip trap-class:
  (A) fp.GetLayer()=B.Cu but pads only on F.Cu (place_board.py text-edit bug
      that flipped fp_layer text but not pad layer set) → flip pads to B.Cu
  (B) fp.GetLayer()=F.Cu but pads only on B.Cu (REVERSE direction discovered
      2026-05-24 PR-rules-compliance-system; many shunt/passive flips left
      pad-layer changed but fp_layer not) → flip fp_layer to B.Cu

Both cases catch the same trap-class from [[feedback-flip-bcu-footprints-recurrence]] —
either side of the mismatch produces silent audit / Freerouting / DRC bugs.

KiCad treats fp.GetLayer() as the "side" indicator; pads' actual copper
layer determines fabrication output. They MUST agree.

After this script: `check_fp_layer_mismatch()` audit gate should report 0.
"""
import pcbnew

PCB = "/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb"


def pad_layer_summary(fp):
    """Return (any_pad_F, any_pad_B) — does ANY SMD pad with copper layer
    appear on F.Cu / B.Cu? Skips unnamed courtyard pads (no layer set)."""
    any_F = False
    any_B = False
    for p in fp.Pads():
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            continue
        ls = p.GetLayerSet()
        f = ls.Contains(pcbnew.F_Cu)
        b = ls.Contains(pcbnew.B_Cu)
        if not (f or b):
            continue
        any_F = any_F or f
        any_B = any_B or b
    return any_F, any_B


def main():
    board = pcbnew.LoadBoard(PCB)
    flipped_a = 0
    flipped_b = 0
    for fp in board.GetFootprints():
        pad_F, pad_B = pad_layer_summary(fp)
        if not (pad_F or pad_B):
            continue
        fp_layer = fp.GetLayer()
        # Direction A: fp_B + pad_F only  → flip pads
        if fp_layer == pcbnew.B_Cu and pad_F and not pad_B:
            fp.Flip(fp.GetPosition(), False)
            flipped_a += 1
            continue
        # Direction B: fp_F + pad_B only  → set fp_layer to B.Cu
        # IMPORTANT: We don't Flip() here because pads are ALREADY on B.Cu.
        # We just need to align fp_layer metadata to match the pad reality.
        # Use SetLayerAndFlip with current layer so geometry unchanged but
        # fp_layer reflects pad side. Actually safer: call Flip() twice (once
        # to flip everything, once to flip back) — net change is just fp_layer
        # metadata. Or use SetLayer directly.
        if fp_layer == pcbnew.F_Cu and pad_B and not pad_F:
            # Move fp_layer to B.Cu without touching pad geometry.
            # Approach: Flip() flips pads + sets fp_layer; calling it once
            # would mess up pads. Use SetLayer() to just update metadata.
            fp.SetLayer(pcbnew.B_Cu)
            flipped_b += 1
    print(f"Direction A (fp_B + pad_F → flip pads): {flipped_a} footprints")
    print(f"Direction B (fp_F + pad_B → set fp_layer to B): {flipped_b} footprints")
    print(f"Total fixes: {flipped_a + flipped_b}")
    board.Save(PCB)
    print(f"Saved {PCB}")


if __name__ == "__main__":
    main()
