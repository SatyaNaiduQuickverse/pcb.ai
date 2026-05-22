"""Phase 5b — inject inner power-plane LAYERS + plane defs into DSN.

Per master option A + Phase 5b empirical finding: a 2-layer DSN with all
components SMD on F.Cu has only ~3 of 250 GND pads on B.Cu — a GND plane on
B.Cu alone is essentially useless. Solution: inject TWO pseudo-inner layers
(In1.Cu + In2.Cu) into the DSN's layer list, then put planes on those. Freerouting
sees a 4-layer board with planes for GND/+VMOTOR/etc; routes signals on F.Cu/B.Cu.

The .kicad_pcb stays at 2-layer for the Phase 5b SES-import step (SES doesn't
contain trace data on inner layers because Freerouting doesn't route signals on
plane layers). Phase 5c re-adds the inner copper layers + pours to .kicad_pcb.

Layer assignment after injection:
  F.Cu (index 0) — signal routing
  In1.Cu (index 1) — GND plane (full board)
  In2.Cu (index 2) — power plane split (+VMOTOR + +V3V3 + others)
  B.Cu (index 3) — signal routing
"""
import re
from pathlib import Path

DSN = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.dsn")

BOARD_W_UM = 90000
BOARD_H_UM = 75000
EDGE_MARGIN_UM = 500


def y_to_dsn(y_um):
    return -y_um


def polygon_str(xy_pairs):
    return "  " + "  ".join(f"{x} {y}" for x, y in xy_pairs)


def plane(net, layer, polygon_coords):
    coords = polygon_str(polygon_coords + [polygon_coords[0]])
    return f"    (plane {net} (polygon {layer} 0{coords}))"


def main():
    if not DSN.exists():
        raise SystemExit(f"ERROR: {DSN} not found. Run dsn_strip_planes.py first.")
    txt = DSN.read_text()

    if "In1.Cu" in txt:
        print("Inner layers already injected; skipping.")
        return

    # ─── 1. Replace the 2-layer block with a 4-layer block ───
    old_layers_pattern = re.compile(
        r'(\s+\(layer F\.Cu\s+\(type signal\)\s+\(property\s+\(index 0\)\s+\)\s+\)\s+\(layer B\.Cu\s+\(type signal\)\s+\(property\s+\(index 1\)\s+\)\s+\))',
        re.DOTALL,
    )
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

    # ─── 2. Build plane defs ───
    planes = []

    # GND full-board plane on In1.Cu
    full_polygon = [
        (EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (BOARD_W_UM - EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (BOARD_W_UM - EDGE_MARGIN_UM, y_to_dsn(BOARD_H_UM - EDGE_MARGIN_UM)),
        (EDGE_MARGIN_UM, y_to_dsn(BOARD_H_UM - EDGE_MARGIN_UM)),
    ]
    planes.append(plane("GND", "In1.Cu", full_polygon))

    # VMOTOR plane on In2.Cu — central zone (battery section + MOSFET grid + bucks)
    vmotor_polygon = [
        (EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (BOARD_W_UM - EDGE_MARGIN_UM, y_to_dsn(EDGE_MARGIN_UM)),
        (BOARD_W_UM - EDGE_MARGIN_UM, y_to_dsn(45000)),
        (EDGE_MARGIN_UM, y_to_dsn(45000)),
    ]
    planes.append(plane("+VMOTOR", "In2.Cu", vmotor_polygon))

    # +V3V3 zone on In2.Cu (channel area — y=45..73)
    v3v3_polygon = [
        (EDGE_MARGIN_UM, y_to_dsn(45000)),
        (BOARD_W_UM - EDGE_MARGIN_UM, y_to_dsn(45000)),
        (BOARD_W_UM - EDGE_MARGIN_UM, y_to_dsn(BOARD_H_UM - EDGE_MARGIN_UM)),
        (EDGE_MARGIN_UM, y_to_dsn(BOARD_H_UM - EDGE_MARGIN_UM)),
    ]
    planes.append(plane("+3V3", "In2.Cu", v3v3_polygon))

    # ─── 3. Insert planes before (via line ───
    via_match = re.search(r'(\s+\(via )', txt)
    if not via_match:
        raise SystemExit("ERROR: could not find (via line in DSN")
    insert_idx = via_match.start()
    new_txt = txt[:insert_idx] + "\n" + "\n".join(planes) + txt[insert_idx:]

    # ─── 4. Update padstacks — add In1.Cu and In2.Cu shapes for through-hole pads ───
    # KiCad emits padstacks like:
    #   (padstack Round[A]Pad_xxx
    #     (shape (circle F.Cu RADIUS))
    #     (shape (circle B.Cu RADIUS))
    #     (attach off)
    #   )
    # For inner layers to work with through-hole pads, add (shape (circle In1.Cu R)) and In2.Cu.
    # SMD pads have only F.Cu OR B.Cu shape — leave those untouched (SMD doesn't drill).
    def expand_padstack(match):
        body = match.group(0)
        # Only expand if it has BOTH F.Cu and B.Cu shapes (through-hole pattern)
        f_shape_m = re.search(r'\(shape \(circle F\.Cu (\d+)\)\)', body)
        b_shape_m = re.search(r'\(shape \(circle B\.Cu (\d+)\)\)', body)
        f_path_m = re.search(r'\(shape \(path F\.Cu (\d+)([^)]*)\)\)', body)
        b_path_m = re.search(r'\(shape \(path B\.Cu (\d+)([^)]*)\)\)', body)
        if f_shape_m and b_shape_m:
            # Through-hole circular pad — add In1.Cu and In2.Cu shapes
            radius = f_shape_m.group(1)
            inner = (f"      (shape (circle In1.Cu {radius}))\n"
                     f"      (shape (circle In2.Cu {radius}))\n")
            body = body.replace(
                '(shape (circle B.Cu',
                inner + '      (shape (circle B.Cu',
                1,
            )
        elif f_path_m and b_path_m:
            r = f_path_m.group(1)
            rest = f_path_m.group(2)
            inner = (f"      (shape (path In1.Cu {r}{rest}))\n"
                     f"      (shape (path In2.Cu {r}{rest}))\n")
            body = body.replace(
                '(shape (path B.Cu',
                inner + '      (shape (path B.Cu',
                1,
            )
        return body

    new_txt = re.sub(r'\(padstack [^(]+\(.*?attach off\)\s+\)', expand_padstack, new_txt, flags=re.DOTALL)

    DSN.write_text(new_txt)
    print(f"Injected 4-layer DSN (F.Cu + In1.Cu + In2.Cu + B.Cu):")
    print(f"  - GND plane on In1.Cu (full board)")
    print(f"  - +VMOTOR plane on In2.Cu (top half y=0..45)")
    print(f"  - +3V3 plane on In2.Cu (bottom half y=45..75)")
    print(f"  - Padstack through-holes expanded to 4 layers")
    print(f"  - Output: {DSN} ({DSN.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
