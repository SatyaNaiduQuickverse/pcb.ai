#!/usr/bin/env python3
"""test_audit_targeted_ripup.py — synthetic provenance tests for G_J1-G_J5.

Generates synthetic provenance JSON in a temp dir and asserts:
  * GOOD entries PASS all 5 audits.
  * Each adversarial entry FAILS exactly the audit it targets.

This is the "master independent regression test" artifact for R36-R39+R-J5
per [[feedback-codify-not-patch]]: every Sai-rule lever gets (a) the fix,
(b) the audit gate, (c) a regression test the audit catches a known-bad
input on.

Run: python3 test_audit_targeted_ripup.py
Exit 0 = ALL synthetic tests pass; 1 = any test fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import targeted_ripup as TR  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent.parent.parent


def _run_audit(script_name: str, repo_root: Path) -> tuple[int, str]:
    """Invoke an audit script with --repo-root <tempdir> --quiet; return (rc, output)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script_name),
         "--repo-root", str(repo_root)],
        capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout + result.stderr


def _seed_good_entry(root: Path) -> None:
    """Write a clean GOOD entry that should pass all 5 audits."""
    e = TR.TargetedRipupEntry(
        timestamp_iso="2026-05-28T10:00:00Z",
        board_sha="d4ab0f200000",
        subsystem="CH1",
        blocked_net="PWM_INHB_CH1",
        blocked_net_priority=80,
        conflict_set=("SWDIO_CH1", "TP19_NET"),
        conflict_set_priorities=(20, 20),
        rerouted={
            "SWDIO_CH1": {"path": "F.Cu→In8 detour", "vias": 1,
                          "length_mm": 14.2, "depth": 1},
            "TP19_NET": {"path": "south manhattan", "vias": 0,
                         "length_mm": 8.1, "depth": 1},
        },
        cascade_depth=1,
        committed=True,
        shorts_pre=0,
        shorts_post=0,
        phase_symmetric_mirror_status="N/A",
    )
    TR.write_provenance(e, root)


def _seed_provenance_missing_rerouted(root: Path) -> None:
    """G_J1 LIAR: committed entry whose rerouted does NOT cover conflict_set."""
    e = TR.TargetedRipupEntry(
        timestamp_iso="2026-05-28T10:01:00Z",
        board_sha="d4ab0f200001",
        subsystem="CH1",
        blocked_net="PWM_INLA_CH1",
        blocked_net_priority=80,
        conflict_set=("SWDIO_CH1", "TP19_NET"),
        conflict_set_priorities=(20, 20),
        rerouted={
            "SWDIO_CH1": {"path": "F.Cu detour", "vias": 1,
                          "length_mm": 12.3, "depth": 1},
            # MISSING TP19_NET — R36 violation
        },
        cascade_depth=1,
        committed=True,
        shorts_pre=0,
        shorts_post=0,
    )
    TR.write_provenance(e, root)


def _seed_cascade_depth_3(root: Path) -> None:
    """G_J2 LIAR: cascade_depth=3 (> cap of 2)."""
    e = TR.TargetedRipupEntry(
        timestamp_iso="2026-05-28T10:02:00Z",
        board_sha="d4ab0f200002",
        subsystem="CH1",
        blocked_net="GLB_CH1",
        blocked_net_priority=80,
        conflict_set=("SWDIO_CH1",),
        conflict_set_priorities=(20,),
        rerouted={
            "SWDIO_CH1": {"path": "depth-3 chain", "vias": 2,
                          "length_mm": 22.5, "depth": 3},
        },
        cascade_depth=3,    # the violation
        committed=True,
        shorts_pre=0,
        shorts_post=0,
        phase_symmetric_mirror_status="N/A",
    )
    TR.write_provenance(e, root)


def _seed_frozen_banked_ripped(root: Path) -> None:
    """G_J3 LIAR: committed entry that ripped a frozen-banked net."""
    e = TR.TargetedRipupEntry(
        timestamp_iso="2026-05-28T10:03:00Z",
        board_sha="d4ab0f200003",
        subsystem="CH1",
        blocked_net="PWM_INHB_CH1",
        blocked_net_priority=80,
        conflict_set=("+VMOTOR",),     # FROZEN — the violation
        conflict_set_priorities=(40,),
        rerouted={
            "+VMOTOR": {"path": "fake detour", "vias": 0,
                        "length_mm": 5.0, "depth": 1},
        },
        cascade_depth=1,
        committed=True,
        shorts_pre=0,
        shorts_post=0,
        phase_symmetric_mirror_status="N/A",
    )
    TR.write_provenance(e, root)


def _seed_phase_symmetric_no_mirror(root: Path) -> None:
    """G_J4 LIAR: GLB ripped alone (no GLA+GLC mirror; no deviation log)."""
    e = TR.TargetedRipupEntry(
        timestamp_iso="2026-05-28T10:04:00Z",
        board_sha="d4ab0f200004",
        subsystem="CH1",
        blocked_net="PWM_INHB_CH1",
        blocked_net_priority=80,
        conflict_set=("GLB_CH1",),     # phase-symmetric, ripped alone
        conflict_set_priorities=(80,),
        rerouted={
            "GLB_CH1": {"path": "fake detour", "vias": 0,
                        "length_mm": 5.0, "depth": 1},
        },
        cascade_depth=1,
        committed=True,
        shorts_pre=0,
        shorts_post=0,
        # The lie: status is N/A even though GLB is phase-symmetric
        phase_symmetric_mirror_status="N/A",
    )
    TR.write_provenance(e, root)


def _seed_shorts_delta_positive(root: Path) -> None:
    """G_J5 LIAR: shorts_post > shorts_pre on a committed entry."""
    e = TR.TargetedRipupEntry(
        timestamp_iso="2026-05-28T10:05:00Z",
        board_sha="d4ab0f200005",
        subsystem="CH1",
        blocked_net="SWDIO_CH1",
        blocked_net_priority=20,
        conflict_set=("TP19_NET",),
        conflict_set_priorities=(40,),
        rerouted={
            "TP19_NET": {"path": "fake detour", "vias": 0,
                         "length_mm": 5.0, "depth": 1},
        },
        cascade_depth=1,
        committed=True,
        shorts_pre=0,
        shorts_post=18,          # the +18 violation
        phase_symmetric_mirror_status="N/A",
    )
    TR.write_provenance(e, root)


def _scenario(label: str, seed_fn, expect_fail_audit: str | None) -> bool:
    """Run all 5 audits against a fresh root + GOOD seed + the optional liar.
    Verify each audit's PASS/FAIL outcome matches expectation."""
    print(f"\n--- scenario: {label} ---")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Always seed a good entry first so PASS-scenarios have something
        _seed_good_entry(root)
        if seed_fn is not None:
            seed_fn(root)
        # Special case: G_J3 requires the BOARD_INVARIANTS.md doc to be
        # readable from `root`. Symlink the repo doc into root.
        (root / "docs").mkdir(exist_ok=True)
        try:
            (root / "docs/BOARD_INVARIANTS.md").symlink_to(
                REPO_ROOT / "docs/BOARD_INVARIANTS.md")
        except FileExistsError:
            pass

        results = {}
        for audit in ["audit_targeted_ripup_provenance.py",
                      "audit_ripup_cascade_depth.py",
                      "audit_frozen_banked_nets_preserved.py",
                      "audit_symmetric_ripup_mirror.py",
                      "audit_ripup_shorts_delta_zero.py"]:
            rc, _out = _run_audit(audit, root)
            results[audit] = rc
            tag = "PASS" if rc == 0 else "FAIL"
            mark = ""
            if expect_fail_audit and audit == expect_fail_audit:
                mark = "  (expected FAIL ✓)" if rc != 0 else "  (EXPECTED FAIL BUT GOT PASS ❌)"
            elif expect_fail_audit and audit != expect_fail_audit:
                mark = "  (expected PASS ✓)" if rc == 0 else "  (unexpected FAIL ❌)"
            elif expect_fail_audit is None:
                mark = "  (expected PASS ✓)" if rc == 0 else "  (unexpected FAIL ❌)"
            print(f"  {audit}: {tag}{mark}")
        # Verify expectations
        ok = True
        if expect_fail_audit:
            for audit, rc in results.items():
                if audit == expect_fail_audit:
                    ok &= (rc != 0)
                else:
                    ok &= (rc == 0)
        else:
            ok &= all(rc == 0 for rc in results.values())
        return ok


def main():
    print("=" * 70)
    print("test_audit_targeted_ripup — synthetic provenance regression tests")
    print("for G_J1-G_J5 (R36-R39 + R-J5; CH1 30/30 lever J)")
    print("=" * 70)

    scenarios = [
        ("good entry only (all PASS)", None, None),
        ("R36 violation: rerouted missing conflict-set entry",
         _seed_provenance_missing_rerouted,
         "audit_targeted_ripup_provenance.py"),
        ("R37 violation: cascade_depth=3 (> cap 2)",
         _seed_cascade_depth_3,
         "audit_ripup_cascade_depth.py"),
        ("R38 violation: +VMOTOR (frozen-banked) ripped",
         _seed_frozen_banked_ripped,
         "audit_frozen_banked_nets_preserved.py"),
        ("R39 violation: GLB ripped alone, no mirror, no deviation log",
         _seed_phase_symmetric_no_mirror,
         "audit_symmetric_ripup_mirror.py"),
        ("R-J5 violation: shorts_post=18 vs shorts_pre=0",
         _seed_shorts_delta_positive,
         "audit_ripup_shorts_delta_zero.py"),
    ]

    n_ok = 0
    for label, seed, expect in scenarios:
        if _scenario(label, seed, expect):
            n_ok += 1

    print(f"\n{'='*70}")
    print(f"RESULT: {n_ok}/{len(scenarios)} scenario(s) match expected audit outcomes.")
    return 0 if n_ok == len(scenarios) else 1


if __name__ == "__main__":
    sys.exit(main())
