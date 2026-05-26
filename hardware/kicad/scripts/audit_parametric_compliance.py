#!/usr/bin/env python3
"""audit_parametric_compliance.py — G_PP21 lockfile↔parametric-engine sync.

Per Sai 2026-05-26 + worker architecture clarification:

The parametric_placement.py engine is the SSoT for PARAMETERS. The lockfile YAML
+ BOARD_INVARIANTS.md are the SSoT for COORDS that worker's bring_selected pipeline
consumes. The two MUST stay synchronized:

  engine.motor_pad_pitch_y * N == (TP21.y - TP19.y)        # CH1 motor pad y-pitch
  engine.s6_height_mm == S6 zone y_max in BOARD_INVARIANTS  # zone heights
  engine.ch_zone_height_mm == (CH1.y_max - CH1.y_min)
  engine.tlm_aux_y_start == TLM/AUX highway y_min
  ...

If they drift → FAIL with the specific mismatch + suggested fix.

This is the "single SSoT for parameters" enforcement Sai requested. Edit engine →
audit forces lockfile to follow. Or edit lockfile → audit catches engine staleness.

Per [[feedback-systemic-rule-enforcement]] + worker clarification 2026-05-26.
"""
import os, sys, yaml, re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
LOCKFILE = os.path.join(REPO, "docs", "PHASE4V3_LOCKFILES", "mechanical_anchors.yaml")
INVARIANTS = os.path.join(REPO, "docs", "BOARD_INVARIANTS.md")

def parse_zones():
    """Returns {name: (x0,y0,x1,y1)} from BOARD_INVARIANTS.md."""
    text = open(INVARIANTS).read()
    zones = {}
    in_table = False
    for ln in text.splitlines():
        if "Subsystem | x_min | y_min | x_max | y_max" in ln:
            in_table = True; continue
        if in_table:
            if not ln.startswith('|') or '---' in ln[:5]:
                if not ln.strip(): break
                if '---' in ln[:5]: continue
                if not ln.startswith('|'): break
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if len(cells) >= 5:
                try:
                    zones[cells[0]] = (float(cells[1]), float(cells[2]),
                                        float(cells[3]), float(cells[4]))
                except ValueError:
                    continue
    return zones

def parse_highways():
    text = open(INVARIANTS).read()
    out = {}
    in_table = False
    for ln in text.splitlines():
        if "Highway | x_min | y_min | x_max | y_max" in ln:
            in_table = True; continue
        if in_table:
            if not ln.startswith('|') or '---' in ln[:5]:
                if not ln.strip(): break
                if '---' in ln[:5]: continue
                if not ln.startswith('|'): break
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if len(cells) >= 5:
                try:
                    out[cells[0]] = (float(cells[1]), float(cells[2]),
                                      float(cells[3]), float(cells[4]))
                except ValueError:
                    continue
    return out

def main():
    sys.path.insert(0, SCRIPT_DIR)
    from parametric_placement import BoardParameters, motor_pad_positions
    p = BoardParameters()
    d = yaml.safe_load(open(LOCKFILE))
    zones = parse_zones()
    highways = parse_highways()

    fails = []
    passes = []
    tol = 0.01  # mm

    # Check 1: motor pad y-pitch matches engine
    lock_motor = {m['ref']: tuple(m['pos']) for m in d.get('motor_pads', [])}
    eng_motor = motor_pad_positions(p)
    for ref, (ex, ey) in eng_motor.items():
        if ref not in lock_motor:
            fails.append(f"motor_pad {ref}: engine has it but lockfile doesn't")
            continue
        lx, ly = lock_motor[ref]
        if abs(lx - ex) > tol or abs(ly - ey) > tol:
            fails.append(f"motor_pad {ref}: lockfile=({lx},{ly}) engine=({ex},{ey})")
        else:
            passes.append(f"motor_pad {ref}: aligned")

    # Check 2: S6 + S1 + CH zone heights match engine
    zone_checks = [
        ("S6 connectors", p.s6_height_mm,  "y_max", 0),  # zone y0=0, y1=s6_height_mm
        ("S1 battery input", p.s1_height_mm, "y_min", p.height_mm - p.s1_height_mm),
        ("CH1 (channel A)", p.ch_zone_height_mm, "height", None),
        ("CH2 (channel B)", p.ch_zone_height_mm, "height", None),
        ("CH3 (channel C)", p.ch_zone_height_mm, "height", None),
        ("CH4 (channel D)", p.ch_zone_height_mm, "height", None),
    ]
    for zname, expect, kind, expect_val in zone_checks:
        if zname not in zones:
            fails.append(f"zone {zname}: not in BOARD_INVARIANTS.md")
            continue
        x0,y0,x1,y1 = zones[zname]
        if kind == "height":
            h = y1 - y0
            if abs(h - expect) > tol:
                fails.append(f"zone {zname}: BOARD_INVARIANTS height={h} engine={expect}")
            else: passes.append(f"zone {zname}: height aligned")
        elif kind == "y_max":
            if abs(y1 - expect) > tol:
                fails.append(f"zone {zname}: BOARD_INVARIANTS y_max={y1} engine s6_height={expect}")
            else: passes.append(f"zone {zname}: y_max aligned")
        elif kind == "y_min":
            if abs(y0 - expect_val) > tol:
                fails.append(f"zone {zname}: BOARD_INVARIANTS y_min={y0} engine derived={expect_val}")
            else: passes.append(f"zone {zname}: y_min aligned")

    # Check 3: TLM/AUX highway alignment
    if "TLM/AUX bus strip" in highways:
        _, hy0, _, hy1 = highways["TLM/AUX bus strip"]
        if abs(hy0 - p.tlm_aux_y_start) > tol or abs(hy1 - p.tlm_aux_y_end) > tol:
            fails.append(f"TLM/AUX highway: lockfile y=({hy0},{hy1}) engine y=({p.tlm_aux_y_start},{p.tlm_aux_y_end})")
        else: passes.append("TLM/AUX highway: aligned")

    print("=" * 70)
    print(f"audit_parametric_compliance.py G_PP21 — lockfile ↔ parametric-engine sync")
    print("=" * 70)
    print(f"  Checked: {len(passes) + len(fails)} parameter↔lockfile relationships")
    print(f"  Aligned: {len(passes)}")
    print(f"  Drift:   {len(fails)}")
    if fails:
        print()
        print(f"  ❌ FAIL — {len(fails)} engine↔lockfile mismatches:")
        for f in fails: print(f"    {f}")
        print()
        print("  Fix: edit parametric_placement.py BoardParameters to match lockfile,")
        print("  OR re-generate lockfile from engine (engine is the SSoT for derivable values).")
        return 1
    print()
    print(f"  ✅ PASS — parametric engine + lockfile are in sync")
    return 0

if __name__ == "__main__":
    sys.exit(main())
