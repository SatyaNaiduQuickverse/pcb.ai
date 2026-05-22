"""Phase 5b → 4b-redo3 — inject inner power-plane LAYERS + plane defs into DSN.

Per master option A (2026-05-22) + Phase 5b empirical finding: a 2-layer DSN
with all components SMD on F.Cu has only a few % of pads on B.Cu — a GND plane
on B.Cu alone is essentially useless. Solution: inject pseudo-inner layers into
the DSN's layer list, put planes on those. Freerouting sees a 4-layer (or
5-layer if In3.Cu signal-promoted) board with planes for GND/+VMOTOR/+V3V3.

Per master's 4b-redo3 pre-emptive flag 2026-05-22 audit (R17 — no future loose
threads when geometry shifts): board outline + zone boundaries are parsed from
the DSN's (boundary ...) section rather than hardcoded. Phase 4b-redo3's grow
to 100×85 just works without script edit.

Layer assignment after injection (default: 4 layers; --3signal mode: 5 layers):
  F.Cu (index 0)   — signal routing
  In1.Cu (index 1) — GND plane (full board)
  In2.Cu (index 2) — power split (+VMOTOR top half + +V3V3 bottom half)
  [In3.Cu (index 3) — signal routing if --3signal mode (Phase 4b-redo3 per D/S gate)]
  B.Cu (index 3 or 4) — signal routing
"""
import re
import sys
from pathlib import Path

DSN = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.dsn")
EDGE_MARGIN_UM = 500


def parse_boundary(txt):
    """Extract board outline from (boundary (path pcb 0  x1 y1  x2 y2 ...))."""
    m = re.search(r'\(boundary\s+\(path pcb 0\s+([\d\s\-]+)\)\s+\)', txt)
    if not m:
        raise SystemExit("ERROR: could not parse (boundary ...) from DSN")
    coords = m.group(1).split()
    # Coords are pairs (x, y) in DSN-um units (y is NEGATIVE since DSN-y inverted).
    xs = [int(coords[i]) for i in range(0, len(coords), 2)]
    ys = [int(coords[i+1]) for i in range(0, len(coords), 2)]
    board_w_um = max(xs) - min(xs)
    board_h_um = max(ys) - min(ys)
    return board_w_um, board_h_um


def y_to_dsn(y_um):
    return -y_um


def polygon_str(xy_pairs):
    return "  " + "  ".join(f"{x} {y}" for x, y in xy_pairs)


def plane(net, layer, polygon_coords):
    coords = polygon_str(polygon_coords + [polygon_coords[0]])
    return f"    (plane {net} (polygon {layer} 0{coords}))"


def main(in3_signal=False):
    if not DSN.exists():
        raise SystemExit(f"ERROR: {DSN} not found. Run dsn_strip_planes.py first.")
    txt = DSN.read_text()

    if "In1.Cu" in txt:
        print("Inner layers already injected; skipping.")
        return

    board_w_um, board_h_um = parse_boundary(txt)
    print(f"Parsed board outline from DSN: {board_w_um/1000:.1f} × {board_h_um/1000:.1f} mm")

    # ─── 1. Replace 2-layer block with 4-layer (or 5-layer if in3_signal) ───
    old_layers_pattern = re.compile(
        r'(\s+\(layer F\.Cu\s+\(type signal\)\s+\(property\s+\(index 0\)\s+\)\s+\)\s+\(layer B\.Cu\s+\(type signal\)\s+\(property\s+\(index 1\)\s+\)\s+\))',
        re.DOTALL,
    )
    if in3_signal:
        # 5-layer: F + In1(GND) + In2(power) + In3(signal) + B
        new_layers = '''
    (layer F.Cu
      (type signal)
      (property
        (index 0)
      )
    )
    (layer In1.Cu
      (type signal)
      (property
        (index 1)
      )
    )
    (layer In2.Cu
      (type signal)
      (property
        (index 2)
      )
    )
    (layer In3.Cu
      (type signal)
      (property
        (index 3)
      )
    )
    (layer B.Cu
      (type signal)
      (property
        (index 4)
      )
    )'''
    else:
        # 4-layer: F + In1(GND) + In2(power) + B
        new_layers = '''
    (layer F.Cu
      (type signal)
      (property
        (index 0)
      )
    )
    (layer In1.Cu
      (type signal)
      (property
        (index 1)
      )
    )
    (layer In2.Cu
      (type signal)
      (property
        (index 2)
      )
    )
    (layer B.Cu
      (type signal)
      (property
        (index 3)
      )
    )'''
    txt = old_layers_pattern.sub(new_layers, txt, count=1)

    # ─── 2. Build plane defs (geometry from parsed board outline) ───
    planes = []
    # GND full-board plane on In1.Cu
    full_polygon = [
        (EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(board_h_um - EDGE_MARGIN_UM)),
        (EDGE_MARGIN_UM, y_to_dsn(board_h_um - EDGE_MARGIN_UM)),
    ]
    planes.append(plane("GND", "In1.Cu", full_polygon))

    # VMOTOR plane on In2.Cu — top half (y=0..mid)
    mid_y_um = board_h_um // 2
    vmotor_polygon = [
        (EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(mid_y_um)),
        (EDGE_MARGIN_UM, y_to_dsn(mid_y_um)),
    ]
    planes.append(plane("+VMOTOR", "In2.Cu", vmotor_polygon))

    # +V3V3 zone on In2.Cu — bottom half
    v3v3_polygon = [
        (EDGE_MARGIN_UM, y_to_dsn(mid_y_um)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(mid_y_um)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(board_h_um - EDGE_MARGIN_UM)),
        (EDGE_MARGIN_UM, y_to_dsn(board_h_um - EDGE_MARGIN_UM)),
    ]
    planes.append(plane("+3V3", "In2.Cu", v3v3_polygon))

    # ─── 3. Insert planes before (via line ───
    via_match = re.search(r'(\s+\(via )', txt)
    if not via_match:
        raise SystemExit("ERROR: could not find (via line in DSN")
    insert_idx = via_match.start()
    new_txt = txt[:insert_idx] + "\n" + "\n".join(planes) + txt[insert_idx:]

    # ─── 4. Update padstacks — expand to ALL inner layers (option a per master) ───
    # Phase 5b-retry: master adjudication 2026-05-22 directive #1 — pads need
    # shapes on inner layers so Freerouting's plane-served-pad recognition fires.
    # For SMD pads (F.Cu-only or B.Cu-only), add inner-layer shapes too so plane
    # fanout works through the pad's logical "presence" on the plane layer.
    # Freerouting auto-carves cutouts around non-matching-net pads.
    inner_layers = ["In1.Cu", "In2.Cu", "In3.Cu"] if in3_signal else ["In1.Cu", "In2.Cu"]

    def expand_padstack(match):
        body = match.group(0)
        # Find ANY F.Cu or B.Cu shape (circle / rect / path) and add same shape on inner layers
        # Pattern matches '(shape (TYPE LAYER PARAMS))'
        shape_pattern = re.compile(r'\(shape \((circle|rect|path|polygon) (F\.Cu|B\.Cu)([^)]+)\)\)')
        # Collect existing inner-layer presence to avoid duplicating
        existing_inner = set()
        for L in inner_layers:
            if f'circle {L}' in body or f'rect {L}' in body or f'path {L}' in body or f'polygon {L}' in body:
                existing_inner.add(L)
        # Find first F.Cu or B.Cu shape definition
        m = shape_pattern.search(body)
        if not m:
            return body
        shape_type, _, params = m.groups()
        # Build inner-layer shapes
        inner_lines = []
        for L in inner_layers:
            if L in existing_inner:
                continue
            inner_lines.append(f"      (shape ({shape_type} {L}{params}))")
        if not inner_lines:
            return body
        inner_block = "\n".join(inner_lines) + "\n      "
        # Insert inner shapes before the FIRST outer-Cu shape line for clean grouping
        body = body.replace(m.group(0), inner_block + m.group(0), 1)
        return body

    new_txt = re.sub(r'\(padstack [^(]+\(.*?attach off\)\s+\)', expand_padstack, new_txt, flags=re.DOTALL)

    DSN.write_text(new_txt)
    print(f"Injected DSN ({'5-layer' if in3_signal else '4-layer'}, board {board_w_um/1000:.0f}×{board_h_um/1000:.0f}):")
    print(f"  - GND plane on In1.Cu (full board)")
    print(f"  - +VMOTOR plane on In2.Cu (top half y=0..{mid_y_um/1000:.0f}mm)")
    print(f"  - +3V3 plane on In2.Cu (bottom half y={mid_y_um/1000:.0f}..{board_h_um/1000:.0f}mm)")
    if in3_signal:
        print(f"  - In3.Cu = signal routing layer (3rd signal layer per Phase 4b-redo3 D/S gate)")
    print(f"  - Padstack through-holes expanded to {len(inner_layers)} inner layers")
    print(f"  - Output: {DSN} ({DSN.stat().st_size:,} bytes)")


if __name__ == "__main__":
    in3_signal = '--3signal' in sys.argv or '--in3-signal' in sys.argv
    main(in3_signal=in3_signal)
