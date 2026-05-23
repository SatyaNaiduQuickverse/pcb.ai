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


# Master 2026-05-24 P1: design-intent override list. These components are
# CANONICALLY F.Cu by role. If we encounter fp_F+pad_B mismatch on these,
# flip PADS back to F.Cu (instead of dragging fp_layer to B.Cu).
CANONICAL_F_CU_REFS = set()
# Built dynamically based on value + footprint:
CANONICAL_F_CU_VALUES = {'0.2mR', '0.5mR'}  # current-sense shunts
CANONICAL_F_CU_FP_PATTERNS = ('R_2512',)     # 2512 shunts


def is_canonical_F(fp):
    """True if this component is F.Cu by design intent regardless of current pad-layer state."""
    if fp.GetReference() in CANONICAL_F_CU_REFS:
        return True
    val = fp.GetValue() or ''
    if val in CANONICAL_F_CU_VALUES:
        return True
    lib = str(fp.GetFPID().GetLibItemName() or '')
    for pat in CANONICAL_F_CU_FP_PATTERNS:
        if pat in lib:
            return True
    return False


def main():
    board = pcbnew.LoadBoard(PCB)
    flipped_a = 0
    flipped_b_set_fp = 0
    flipped_b_flip_pads = 0
    for fp in board.GetFootprints():
        pad_F, pad_B = pad_layer_summary(fp)
        if not (pad_F or pad_B):
            continue
        fp_layer = fp.GetLayer()
        # Direction A: fp_B + pad_F only  → flip pads (and fp_layer) to B
        if fp_layer == pcbnew.B_Cu and pad_F and not pad_B:
            fp.Flip(fp.GetPosition(), False)
            flipped_a += 1
            continue
        # Direction B: fp_F + pad_B only
        # DEFAULT: align fp_layer to B (set fp_layer; don't touch pads)
        # OVERRIDE: if component is canonically F.Cu by design → flip pads back to F
        if fp_layer == pcbnew.F_Cu and pad_B and not pad_F:
            if is_canonical_F(fp):
                # Pads should be F.Cu by design — flip pads back to F.
                # fp.Flip() with current fp_layer=F will move both fp+pads to B
                # (wrong direction). Instead, flip twice: once to B (everything),
                # once back to F (everything). Net effect: pads round-trip.
                pos = fp.GetPosition()
                fp.Flip(pos, False)  # F→B (everything)
                fp.Flip(pos, False)  # B→F (everything)
                flipped_b_flip_pads += 1
            else:
                # Standard Dir B: align fp_layer metadata to pad reality
                fp.SetLayer(pcbnew.B_Cu)
                flipped_b_set_fp += 1
    print(f"Direction A (fp_B + pad_F → flip pads): {flipped_a} footprints")
    print(f"Direction B set-fp-to-B (default): {flipped_b_set_fp} footprints")
    print(f"Direction B flip-pads-to-F (canonical-F override): {flipped_b_flip_pads} footprints")
    print(f"Total fixes: {flipped_a + flipped_b_set_fp + flipped_b_flip_pads}")
    board.Save(PCB)
    print(f"Saved {PCB}")


if __name__ == "__main__":
    main()
