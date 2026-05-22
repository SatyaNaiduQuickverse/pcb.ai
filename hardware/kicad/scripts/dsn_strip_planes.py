"""Phase 5b — strip inner power-plane layers (In1.Cu .. In4.Cu) from DSN.

Per playbook trap T1: Freerouting must NOT see plane layers in the (structure)
section, otherwise it may route on them. Inner copper pours land via KiCad
post-route (Phase 5c).

Input:  hardware/kicad/pcbai_fpv4in1_raw.dsn (from ExportSpecctraDSN)
Output: hardware/kicad/pcbai_fpv4in1.dsn      (consumed by Freerouting)

Idempotent: if no In*.Cu layers are present (current Phase 5b state — 2-layer
.kicad_pcb), the script is a no-op pass-through.
"""
import re
import sys
from pathlib import Path

RAW_DSN = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1_raw.dsn")
PROCESSED_DSN = Path("/home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.dsn")


def strip_inner_layers(txt):
    """Find each `(layer In[1-4].Cu ...)` block inside (structure ...) and remove it."""
    stripped_count = 0
    while True:
        # Find next (layer InN.Cu opening
        m = re.search(r'\(layer In[1-4]\.Cu\b', txt)
        if not m:
            break
        start = m.start()
        # Walk balanced parens
        depth = 0
        i = start
        while i < len(txt):
            if txt[i] == '(':
                depth += 1
            elif txt[i] == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        # Strip the (layer InN.Cu ... ) block + any leading whitespace/newline
        line_start = txt.rfind('\n', 0, start)
        if line_start < 0:
            line_start = 0
        else:
            line_start += 1
        txt = txt[:line_start] + txt[end:].lstrip('\n')
        stripped_count += 1
    return txt, stripped_count


def main():
    if not RAW_DSN.exists():
        print(f"ERROR: {RAW_DSN} not found. Run export_dsn.py first.")
        sys.exit(1)
    txt = RAW_DSN.read_text()
    raw_lines = txt.count('\n')

    new_txt, stripped = strip_inner_layers(txt)
    new_lines = new_txt.count('\n')

    PROCESSED_DSN.write_text(new_txt)
    print(f"Raw DSN:       {raw_lines:,} lines / {len(txt):,} bytes")
    print(f"Processed DSN: {new_lines:,} lines / {len(new_txt):,} bytes")
    if stripped:
        print(f"Stripped {stripped} inner-plane layer blocks (In*.Cu) per playbook T1.")
    else:
        print("No inner-plane layers found (board is currently 2-layer F.Cu/B.Cu).")
        print("Pass-through complete — Phase 5c will add planes after autoroute.")
    print(f"Output: {PROCESSED_DSN}")


if __name__ == "__main__":
    main()
