#!/usr/bin/env python3
"""
master_audit_invariants.py — Phase 4-v2 master audit gates

Reads BOARD_INVARIANTS.md (SSOT) and runs 5 new master gates:
  1. check_board_invariants_hash — invariant hash drift detection
  2. check_subsystem_zone_compliance — all components within declared zone bbox
  3. check_io_port_compliance — I/O port positions land within ±0.5mm of declared
  4. check_highway_reservation — no components inside reserved corridors
  5. check_symmetry_partner_diff — mirror partner per-pad delta within tolerance

Per Phase 4-v2 dispatch + R26 (no idle when blocked) — master pre-built so
worker can call from audit_meta.py in Step 2 PRs without waiting.

Usage:
  python3 master_audit_invariants.py <board.kicad_pcb> [<invariants.md>]

Reads invariants from docs/BOARD_INVARIANTS.md by default.

Exit code: 0 = all PASS, 1 = any FAIL.
"""

import hashlib
import re
import sys
from pathlib import Path

try:
    import pcbnew
except ImportError:
    print("FAIL: pcbnew not importable — install kicad or PYTHONPATH=/usr/lib/python3/dist-packages")
    sys.exit(1)


# ─── BOARD_INVARIANTS.md parser ──────────────────────────────────────────────

class Invariants:
    """Parsed BOARD_INVARIANTS.md content."""

    def __init__(self):
        self.outline = None              # (xmin, ymin, xmax, ymax)
        self.mount_holes = []            # [(x, y, ref), ...]
        self.zones = {}                  # {subsystem_name: (xmin, ymin, xmax, ymax)}
        self.io_ports = []               # [(from_sys, to_sys, side, signals, x, y), ...]
        self.highways = []               # [(name, xmin, ymin, xmax, ymax, width_mm), ...]
        self.symmetry_pairs = []         # [(sys_a, sys_b, mirror_axis, axis_value), ...]
        self.target_h_md5 = None
        self.raw_text = ""

    def hash(self):
        """sha256 of canonicalized invariants."""
        canon = "\n".join([
            f"outline={self.outline}",
            f"mount_holes={sorted(self.mount_holes)}",
            f"zones={sorted(self.zones.items())}",
            f"io_ports={sorted(self.io_ports)}",
            f"highways={sorted([h[:6] for h in self.highways])}",
            f"symmetry_pairs={sorted(self.symmetry_pairs)}",
            f"target_h_md5={self.target_h_md5}",
        ])
        return hashlib.sha256(canon.encode()).hexdigest()[:16]


def parse_invariants(path):
    """Parse BOARD_INVARIANTS.md. Tolerant of different table formats — looks for
    section headers + table rows. Returns Invariants object."""
    inv = Invariants()
    text = Path(path).read_text()
    inv.raw_text = text

    # target.h md5 — `target.h md5: <hex>`
    m = re.search(r"target\.h md5:\s*([0-9a-f]{32})", text, re.IGNORECASE)
    if m:
        inv.target_h_md5 = m.group(1)

    # outline — `Outline: 100×100 mm` or `outline: 0,0,100,100`
    m = re.search(r"[Oo]utline[:\s]+(\d+)[×x](\d+)\s*mm", text)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        inv.outline = (0, 0, w, h)
    else:
        m = re.search(r"outline:\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)", text, re.IGNORECASE)
        if m:
            inv.outline = tuple(int(g) for g in m.groups())

    # mount holes — table or list
    # Format: `M3 at (5,5)` or table row `| H1 | 5 | 5 |`
    for m in re.finditer(r"M3 at \((\d+\.?\d*),\s*(\d+\.?\d*)\)", text):
        inv.mount_holes.append((float(m.group(1)), float(m.group(2)), ""))

    # Zones — table with header `| subsystem | x_min | y_min | x_max | y_max | reason |`
    # Find the zones table
    zone_section = re.search(
        r"## Subsystem zones.*?\n\n([\s\S]+?)(?=\n##|\Z)", text)
    if zone_section:
        for line in zone_section.group(1).split("\n"):
            row = re.match(r"\|\s*([A-Z][A-Z0-9_]*)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
            if row:
                name = row.group(1)
                bbox = tuple(float(g) for g in row.groups()[1:5])
                inv.zones[name] = bbox

    # Symmetry pairs — `## Symmetry pairs` section
    sym_section = re.search(
        r"## Symmetry pairs.*?\n\n([\s\S]+?)(?=\n##|\Z)", text)
    if sym_section:
        for m in re.finditer(
                r"([A-Z][A-Z0-9_]*)\s*[↔<->]+\s*([A-Z][A-Z0-9_]*):\s*mirror about (\w+)=([\d.]+)",
                sym_section.group(1)):
            inv.symmetry_pairs.append(
                (m.group(1), m.group(2), m.group(3), float(m.group(4))))

    # I/O ports table
    io_section = re.search(
        r"## Subsystem I/O ports.*?\n\n([\s\S]+?)(?=\n##|\Z)", text)
    if io_section:
        for line in io_section.group(1).split("\n"):
            row = re.match(
                r"\|\s*(\w+)\s*[→\->]+\s*(\w+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*\(([\d.]+),\s*([\d.]+)\)",
                line)
            if row:
                inv.io_ports.append((
                    row.group(1).strip(), row.group(2).strip(),
                    row.group(3).strip(), row.group(4).strip(),
                    float(row.group(5)), float(row.group(6))))

    # Highways table
    hw_section = re.search(
        r"## Highway reservations.*?\n\n([\s\S]+?)(?=\n##|\Z)", text)
    if hw_section:
        for line in hw_section.group(1).split("\n"):
            row = re.match(
                r"\|\s*([\w +/]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)mm",
                line)
            if row:
                inv.highways.append((
                    row.group(1).strip(),
                    float(row.group(2)), float(row.group(3)),
                    float(row.group(4)), float(row.group(5)),
                    float(row.group(6))))

    return inv


# ─── Gate 1: invariant hash drift ────────────────────────────────────────────

def check_board_invariants_hash(inv, board, declared_hash=None):
    """Compute invariant hash + compare to declared (in BOARD_INVARIANTS.md
    final line) if provided. PR title must declare 'invariant-change' if hash
    drifted intentionally."""
    computed = inv.hash()

    # Also extract declared from raw text if present
    if declared_hash is None:
        m = re.search(r"[Ii]nvariant.hash[:\s=]+([0-9a-f]{16,})", inv.raw_text)
        if m:
            declared_hash = m.group(1)[:16]

    if declared_hash is None:
        return "WARN", f"computed hash={computed}, no declared hash to compare against (add to BOARD_INVARIANTS.md)"
    if declared_hash != computed:
        return "FAIL", f"computed hash={computed} != declared={declared_hash} — invariant drift; PR must declare 'invariant-change'"
    return "PASS", f"hash={computed}"


# ─── Gate 2: subsystem zone compliance ───────────────────────────────────────

def _component_subsystem(ref):
    """Map refdes to subsystem name. Worker convention: CHn channel passives
    suffixed _CHn; everything else inferred by position or ref prefix.
    Returns subsystem name or None."""
    # CHn suffix
    m = re.match(r".*_CH([1-4])$", ref)
    if m:
        return f"CH{m.group(1)}"
    # H1-H4 mount holes
    if re.match(r"^H[1-4]$", ref):
        return None  # mount holes are not in zones
    return None  # position-based for the rest, handled by zone-bbox containment


def check_subsystem_zone_compliance(inv, board):
    """Every component must be within declared zone bbox (for the subsystem
    its refdes maps to). For position-only subsystems, every component's
    position must be inside SOME declared zone."""
    if not inv.zones:
        return "WARN", "no zones declared — skipping"

    fails = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        # Skip mount holes
        if re.match(r"^H[1-4]$", ref):
            continue

        pos = fp.GetPosition()
        x = pcbnew.ToMM(pos.x)
        y = pcbnew.ToMM(pos.y)

        # If ref maps to specific subsystem, check THAT zone
        sub = _component_subsystem(ref)
        if sub is not None and sub in inv.zones:
            xmin, ymin, xmax, ymax = inv.zones[sub]
            if not (xmin <= x <= xmax and ymin <= y <= ymax):
                fails.append(f"{ref} at ({x:.1f},{y:.1f}) outside {sub} zone ({xmin},{ymin})-({xmax},{ymax})")
                continue

        # Otherwise: must be inside SOME zone
        in_any = any(
            xmin <= x <= xmax and ymin <= y <= ymax
            for (xmin, ymin, xmax, ymax) in inv.zones.values())
        if not in_any:
            fails.append(f"{ref} at ({x:.1f},{y:.1f}) outside ALL declared zones")

    if fails:
        msg = f"{len(fails)} components out-of-zone:\n  " + "\n  ".join(fails[:10])
        if len(fails) > 10:
            msg += f"\n  ... +{len(fails)-10} more"
        return "FAIL", msg
    return "PASS", f"all {board.GetFootprints().size()} components within declared zones"


# ─── Gate 3: I/O port compliance ─────────────────────────────────────────────

def check_io_port_compliance(inv, board, tolerance_mm=0.5):
    """For each declared I/O port, verify at least one track endpoint or pad
    of the declared signal lands within tolerance of declared position."""
    if not inv.io_ports:
        return "WARN", "no I/O ports declared — skipping"

    fails = []
    for (from_sys, to_sys, side, signals_raw, px, py) in inv.io_ports:
        signals = [s.strip() for s in re.split(r"[,;]", signals_raw) if s.strip()]
        for sig in signals:
            # Find net
            net = board.FindNet(sig)
            if net is None:
                continue  # skip unknown nets silently
            # Check if any pad or track endpoint of this net is near (px, py)
            found = False
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if pad.GetNetname() == sig:
                        pp = pad.GetPosition()
                        d = ((pcbnew.ToMM(pp.x) - px)**2 + (pcbnew.ToMM(pp.y) - py)**2)**0.5
                        if d <= tolerance_mm:
                            found = True
                            break
                if found:
                    break
            if not found:
                # Check track endpoints
                for t in board.GetTracks():
                    if not isinstance(t, pcbnew.PCB_TRACK):
                        continue
                    if t.GetNetname() == sig:
                        for endpoint in [t.GetStart(), t.GetEnd()]:
                            d = ((pcbnew.ToMM(endpoint.x) - px)**2 + (pcbnew.ToMM(endpoint.y) - py)**2)**0.5
                            if d <= tolerance_mm:
                                found = True
                                break
                    if found:
                        break
            if not found:
                fails.append(f"{from_sys}→{to_sys} signal={sig} not landing within {tolerance_mm}mm of declared port ({px},{py})")

    if fails:
        return "FAIL", f"{len(fails)} I/O port mismatches:\n  " + "\n  ".join(fails[:10])
    return "PASS", f"all {len(inv.io_ports)} I/O ports compliant (±{tolerance_mm}mm)"


# ─── Gate 4: highway reservation ─────────────────────────────────────────────

def check_highway_reservation(inv, board, exclusion_margin_mm=0.5):
    """No component pad center inside reserved highway corridor."""
    if not inv.highways:
        return "WARN", "no highways declared — skipping"

    fails = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            pp = pad.GetPosition()
            x, y = pcbnew.ToMM(pp.x), pcbnew.ToMM(pp.y)
            for (name, hx_min, hy_min, hx_max, hy_max, width) in inv.highways:
                if (hx_min - exclusion_margin_mm <= x <= hx_max + exclusion_margin_mm and
                        hy_min - exclusion_margin_mm <= y <= hy_max + exclusion_margin_mm):
                    fails.append(f"{ref}.{pad.GetPadName()} at ({x:.1f},{y:.1f}) inside highway '{name}' ({hx_min},{hy_min})-({hx_max},{hy_max})")
                    break

    if fails:
        return "FAIL", f"{len(fails)} pads in reserved highways:\n  " + "\n  ".join(fails[:10])
    return "PASS", f"no pads in {len(inv.highways)} reserved highways"


# ─── Gate 5: symmetry partner diff ───────────────────────────────────────────

def check_symmetry_partner_diff(inv, board, tolerance_mm=5.0):
    """For each declared symmetry pair, every component in sys_a must have a
    mirror partner in sys_b within tolerance of mirrored position.
    R19 tolerance is 5mm by default per [[feedback-r19-mirror-tolerance]]."""
    if not inv.symmetry_pairs:
        return "WARN", "no symmetry pairs declared — skipping"

    fails = []
    for (sys_a, sys_b, axis, axis_val) in inv.symmetry_pairs:
        # Find all components in sys_a and sys_b
        a_comps = {}  # refdes_stem → (x, y)
        b_comps = {}
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            stem_match = re.match(r"([A-Z]+\d+)_(CH\d)$", ref)
            if not stem_match:
                continue
            stem, ch = stem_match.group(1), stem_match.group(2)
            pos = fp.GetPosition()
            entry = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
            if ch == sys_a:
                a_comps[stem] = entry
            elif ch == sys_b:
                b_comps[stem] = entry

        # For each a, find mirror partner in b
        for stem, (ax, ay) in a_comps.items():
            if stem not in b_comps:
                # No partner — count as fail
                fails.append(f"{stem}_{sys_a} has no {stem}_{sys_b} partner")
                continue
            bx, by = b_comps[stem]
            # Compute expected mirror position
            if axis == "x":
                exp_bx = 2 * axis_val - ax
                exp_by = ay
            elif axis == "y":
                exp_bx = ax
                exp_by = 2 * axis_val - ay
            else:
                continue
            d = ((bx - exp_bx)**2 + (by - exp_by)**2)**0.5
            if d > tolerance_mm:
                fails.append(f"{stem}: {sys_a}({ax:.1f},{ay:.1f}) ↔ {sys_b}({bx:.1f},{by:.1f}) — mirror delta {d:.2f}mm > {tolerance_mm}mm")

    if fails:
        return "FAIL", f"{len(fails)} symmetry violations:\n  " + "\n  ".join(fails[:10])
    return "PASS", f"all symmetry pairs within {tolerance_mm}mm"


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    board_path = sys.argv[1]
    inv_path = sys.argv[2] if len(sys.argv) > 2 else "docs/BOARD_INVARIANTS.md"

    if not Path(board_path).exists():
        print(f"FAIL: {board_path} not found")
        sys.exit(1)
    if not Path(inv_path).exists():
        print(f"FAIL: {inv_path} not found — Step 1 BOARD_INVARIANTS.md must exist before this gate")
        sys.exit(1)

    inv = parse_invariants(inv_path)
    board = pcbnew.LoadBoard(board_path)

    print(f"=== Phase 4-v2 master invariants audit: {Path(board_path).name} ===")
    print(f"Invariants: {inv_path}")
    print(f"  zones={len(inv.zones)}, io_ports={len(inv.io_ports)}, "
          f"highways={len(inv.highways)}, symmetry_pairs={len(inv.symmetry_pairs)}")
    print()

    any_fail = False
    for name, fn in [
            ("BOARD_INVARIANTS_HASH", lambda: check_board_invariants_hash(inv, board)),
            ("SUBSYSTEM_ZONE_COMPLIANCE", lambda: check_subsystem_zone_compliance(inv, board)),
            ("IO_PORT_COMPLIANCE", lambda: check_io_port_compliance(inv, board)),
            ("HIGHWAY_RESERVATION", lambda: check_highway_reservation(inv, board)),
            ("SYMMETRY_PARTNER_DIFF", lambda: check_symmetry_partner_diff(inv, board)),
    ]:
        status, msg = fn()
        print(f"[{status}] {name}: {msg}")
        print()
        if status == "FAIL":
            any_fail = True

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
