"""Phase 4a-restack-8L — inject 8L layer geometry + planes into DSN for Freerouting.

Per master Phase 4a-restack-8L directive 2026-05-22 (Task #37):

Final 8L stackup (this script emits this geometry into the DSN):
  F.Cu (index 0)   — signal routing layer (3oz copper, autoroute target)
  In1.Cu (index 1) — GND plane (full board, 1oz)
  In2.Cu (index 2) — signal routing layer (1oz, autoroute target)
  In3.Cu (index 3) — +VMOTOR plane (full board where applicable, 3oz heavy-copper)
  In4.Cu (index 4) — signal routing layer (1oz, autoroute target)
  In5.Cu (index 5) — GND plane (full board, 1oz; dual-GND for EMC/return-path symmetry)
  In6.Cu (index 6) — signal routing layer (1oz, autoroute target)
  B.Cu (index 7)   — signal routing layer (3oz, autoroute target)

5 signal layers + 3 plane layers.

Per master Phase 5b-retry adjudication (carried over):
  padstack expansion option (a): pad shapes added to ALL inner layers so that
  Freerouting recognizes plane-served pads. SMD pads on F.Cu or B.Cu get
  identical-shape replicas on each inner layer (In1..In6). Through-hole pads
  already span; this re-emits the inner shapes if missing.

Per Phase 4b-redo3 audit (R17): board outline + zone boundaries are parsed
from the DSN's (boundary ...) section — no hardcoded dimensions.

Plane placement rationale (Phase 4a-restack-8L):
  - In1.Cu = GND (full board)        return-path integrity for top-side signals
  - In3.Cu = +VMOTOR (full board)    heavy-copper bus rail; 3oz for ≥280A
  - In5.Cu = GND (full board)        return-path integrity for bottom-side signals
                                      + EMC (dual-GND sandwich on VMOTOR layer)
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


# Phase 4a-restack-8L: 8L stackup is the canonical configuration.
# Signal layers (Freerouting autoroutes here): F.Cu, In2.Cu, In4.Cu, In6.Cu, B.Cu
# Plane layers (Freerouting plane-serves):     In1.Cu (GND), In3.Cu (+VMOTOR), In5.Cu (GND)
SIGNAL_LAYERS = ["F.Cu", "In2.Cu", "In4.Cu", "In6.Cu", "B.Cu"]
PLANE_LAYERS = ["In1.Cu", "In3.Cu", "In5.Cu"]
ALL_INNER_LAYERS = ["In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu", "In6.Cu"]


def build_layer_block():
    """Return the 8-layer (structure) ... (layer ...) block string."""
    # DSN structure section orders layers F top → B bottom, by ascending index.
    layer_order = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu",
                   "In4.Cu", "In5.Cu", "In6.Cu", "B.Cu"]
    lines = []
    for idx, name in enumerate(layer_order):
        lines.append(f'''    (layer {name}
      (type signal)
      (property
        (index {idx})
      )
    )''')
    return "\n".join(lines)


def main():
    if not DSN.exists():
        raise SystemExit(f"ERROR: {DSN} not found. Run dsn_strip_planes.py first.")
    txt = DSN.read_text()

    if "In1.Cu" in txt:
        print("Inner layers already injected; skipping.")
        return

    board_w_um, board_h_um = parse_boundary(txt)
    print(f"Parsed board outline from DSN: {board_w_um/1000:.1f} × {board_h_um/1000:.1f} mm")

    # ─── 1. Replace 2-layer block with 8-layer ───
    old_layers_pattern = re.compile(
        r'(\s+\(layer F\.Cu\s+\(type signal\)\s+\(property\s+\(index 0\)\s+\)\s+\)\s+\(layer B\.Cu\s+\(type signal\)\s+\(property\s+\(index 1\)\s+\)\s+\))',
        re.DOTALL,
    )
    new_layers = "\n" + build_layer_block()
    new_txt, nsub = old_layers_pattern.subn(new_layers, txt, count=1)
    if nsub == 0:
        raise SystemExit("ERROR: did not match the 2-layer pattern in DSN — has the DSN already been processed?")
    txt = new_txt

    # ─── 2. Build plane defs — full-board GND/VMOTOR/GND on In1/In3/In5 ───
    planes = []
    full_polygon = [
        (EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (board_w_um - EDGE_MARGIN_UM, y_to_dsn(board_h_um - EDGE_MARGIN_UM)),
        (EDGE_MARGIN_UM, y_to_dsn(board_h_um - EDGE_MARGIN_UM)),
    ]
    planes.append(plane("GND", "In1.Cu", full_polygon))
    planes.append(plane("+VMOTOR", "In3.Cu", full_polygon))
    planes.append(plane("GND", "In5.Cu", full_polygon))

    # ─── 3. Insert planes before (via line ───
    via_match = re.search(r'(\s+\(via )', txt)
    if not via_match:
        raise SystemExit("ERROR: could not find (via line in DSN")
    insert_idx = via_match.start()
    new_txt = txt[:insert_idx] + "\n" + "\n".join(planes) + txt[insert_idx:]

    # ─── 4. Update padstacks — expand to ALL 6 inner layers (option a per master) ───
    # Per Phase 5b master adjudication 2026-05-22: pads need shapes on inner
    # layers so Freerouting recognizes plane-served pads + correctly routes net
    # connections through plane fan-out. For SMD pads (F.Cu-only or B.Cu-only),
    # add inner-layer shape replicas on ALL 6 inner layers (In1..In6).
    # Freerouting auto-carves cutouts around non-matching-net pads on plane layers.

    def expand_padstack(match):
        body = match.group(0)
        shape_pattern = re.compile(r'\(shape \((circle|rect|path|polygon) (F\.Cu|B\.Cu)([^)]+)\)\)')
        # Collect existing inner-layer presence to avoid duplicating
        existing_inner = set()
        for L in ALL_INNER_LAYERS:
            if (f'circle {L}' in body or f'rect {L}' in body or
                f'path {L}' in body or f'polygon {L}' in body):
                existing_inner.add(L)
        m = shape_pattern.search(body)
        if not m:
            return body
        shape_type, _, params = m.groups()
        inner_lines = []
        for L in ALL_INNER_LAYERS:
            if L in existing_inner:
                continue
            inner_lines.append(f"      (shape ({shape_type} {L}{params}))")
        if not inner_lines:
            return body
        inner_block = "\n".join(inner_lines) + "\n      "
        body = body.replace(m.group(0), inner_block + m.group(0), 1)
        return body

    new_txt = re.sub(r'\(padstack [^(]+\(.*?attach off\)\s+\)', expand_padstack, new_txt, flags=re.DOTALL)

    DSN.write_text(new_txt)
    print(f"Injected DSN (8-layer, board {board_w_um/1000:.0f}×{board_h_um/1000:.0f}):")
    print(f"  - 5 signal layers: F.Cu, In2.Cu, In4.Cu, In6.Cu, B.Cu (autoroute targets)")
    print(f"  - 3 plane layers:")
    print(f"      In1.Cu = GND     (full board)")
    print(f"      In3.Cu = +VMOTOR (full board, 3oz heavy-copper)")
    print(f"      In5.Cu = GND     (full board, dual-GND for EMC)")
    print(f"  - Padstack pads expanded to {len(ALL_INNER_LAYERS)} inner layers (plane-served pad recognition)")
    print(f"  - Output: {DSN} ({DSN.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
