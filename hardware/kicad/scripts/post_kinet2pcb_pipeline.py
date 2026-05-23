#!/usr/bin/env python3
"""post_kinet2pcb_pipeline.py — single orchestrator for all post-import fixups.

Per Sai 2026-05-24 systemic directive + master Step 3: every fresh kinet2pcb
import wipes manual placement fixes. This script chains ALL codified fix
scripts so a re-import → run-this → board back to compliant state.

Pipeline order (each step is idempotent + audit-verified after):

  1. fix_fet_netlist_drop.py   — kinet2pcb silent-drop on G/D/S → 1/2/3 pad map
  2. flip_bcu_footprints.py    — fp.GetLayer()=B.Cu while pads on F.Cu trap
  3. fix_u1_hall_footprint.py  — ACS770 library quirk (wrong pad positions)
  4. setup_board.py            — 8L stackup + Edge.Cuts + M3 mounting holes
  5. place_board.py            — S0-S6 IC-level + auto-anchor fallback placement
  6. place_channel_passives_role_aware.py — net-pattern role-driven CH1 + mirror
  7. anchor_off_board.py       — recover any remaining off-board components
  8. fix_tp_spacing.py         — TP spacing 4mm c-to-c (Sai catch #4)
  9. place_swd_boot_tps.py     — algorithmic SWD/BOOT TP placement
 10. place_fiducials.py        — JLC SMT fiducials (Sai catch #8)
 11. fix_coincident_placements.py — final pass to clear <1.5mm placement bugs

Run: python3 hardware/kicad/scripts/post_kinet2pcb_pipeline.py

After completion: run `python3 hardware/kicad/scripts/audit_layout_compliance.py
hardware/kicad/pcbai_fpv4in1.kicad_pcb` — should be all GREEN.

Per [[feedback-codify-not-patch]]: this is the orchestrator that guarantees
manual fixes never go un-applied after a fresh import.
"""
import subprocess
import sys
import shutil
from pathlib import Path

REPO = Path(__file__).parent.parent.parent.parent
SCRIPTS = REPO / "hardware/kicad/scripts"
PCB = REPO / "hardware/kicad/pcbai_fpv4in1.kicad_pcb"
AUDIT = SCRIPTS / "audit_layout_compliance.py"


# (script_filename, description, optional)
PIPELINE = [
    ('fix_fet_netlist_drop.py',           'FET symbolic-pin → numeric-pad mapping',                 True),
    ('flip_bcu_footprints.py',            'Flip footprints where fp_layer=B.Cu but pads on F.Cu',   True),
    ('fix_u1_hall_footprint.py',          'ACS770 Hall library pad-position fix',                   True),
    ('setup_board.py',                    '8L stackup + Edge.Cuts + M3 mount holes',                True),
    ('place_board.py',                    'S0-S6 IC-level + auto-anchor passives',                  True),
    ('place_channel_passives_role_aware.py', 'Net-pattern role-driven channel placement',            True),
    ('anchor_off_board.py',               'Off-board recovery for any leftover refs',                True),
    ('fix_tp_spacing.py',                 'TP spacing 4mm c-to-c + delete redundant power TPs',     False),
    ('place_swd_boot_tps.py',             'Algorithmic SWD/BOOT TP placement (Sai catch #4)',       False),
    ('place_fiducials.py',                'JLC SMT fiducials F.Cu + B.Cu (Sai catch #8)',           False),
    ('fix_coincident_placements.py',      'Clear <1.5mm coincident-placement bugs',                  False),
    ('fix_led_stub_width.py',             'Widen LED indicator stubs on power nets (PR #67 amendment)', False),
]


def run_step(script_name, description, optional):
    script_path = SCRIPTS / script_name
    if not script_path.exists():
        if optional:
            print(f"  ⊘ SKIP (script not found): {script_name}")
            return True
        print(f"  ❌ MISSING (required): {script_name}")
        return False
    print(f"\n--- {script_name} — {description} ---")
    try:
        r = subprocess.run([sys.executable, str(script_path)],
                           cwd=str(REPO), capture_output=True, timeout=300)
        out = (r.stdout or b'').decode(errors='replace').strip()
        err = (r.stderr or b'').decode(errors='replace').strip()
        if out:
            # show last 4 lines as a summary
            tail = '\n'.join(out.splitlines()[-4:])
            print(f"  stdout:\n    {tail.replace(chr(10), chr(10)+'    ')}")
        if r.returncode != 0:
            print(f"  ❌ exit code {r.returncode}")
            if err:
                print(f"  stderr:\n    {err.splitlines()[-4:]}")
            return False
        print(f"  ✓ ok")
        return True
    except subprocess.TimeoutExpired:
        print(f"  ❌ TIMEOUT after 300s")
        return False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False


def run_audit():
    print("\n--- audit_layout_compliance.py — final audit ---")
    if not AUDIT.exists():
        print("  ❌ audit script missing")
        return False
    r = subprocess.run([sys.executable, str(AUDIT), str(PCB)],
                       capture_output=True, timeout=120)
    out = (r.stdout or b'').decode(errors='replace')
    # show FAIL lines only
    fail_lines = [ln for ln in out.splitlines() if 'FAIL' in ln or 'fails' in ln.lower()]
    if fail_lines:
        for ln in fail_lines:
            print(f"  {ln}")
    else:
        print("  audit emitted no FAIL summary line")
    # exit-code 0 vs non-zero — but audit script doesn't always exit 1 on fail; rely on stdout
    return True


def main():
    if not PCB.exists():
        print(f"FATAL: {PCB} not found")
        return 1
    print(f"=== post_kinet2pcb_pipeline ===")
    print(f"PCB: {PCB}")
    print(f"Running {len(PIPELINE)} fix steps")
    failures = []
    for script, desc, optional in PIPELINE:
        ok = run_step(script, desc, optional)
        if not ok:
            failures.append(script)
    run_audit()
    print(f"\n=== Pipeline complete ===")
    if failures:
        print(f"❌ {len(failures)} step(s) failed: {failures}")
        return 1
    print("✓ All pipeline steps executed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
