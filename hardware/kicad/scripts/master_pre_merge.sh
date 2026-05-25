#!/usr/bin/env bash
#
# master_pre_merge.sh — Phase 4-v3 master gate runner
#
# Runs the full audit suite on master HEAD post-merge for EVERY PR review.
# Per [[feedback-master-gate-checklist]] + [[feedback-park-then-bring-in-pattern]]
# + Sai 2026-05-25 "single source of truth and strong gates".
#
# Exit 0 = ALL gates PASS, ALL PR-merge criteria satisfied
# Exit 1 = ANY gate FAIL → REJECT PR
#
# Usage:
#   bash hardware/kicad/scripts/master_pre_merge.sh [<board.kicad_pcb>]
#
# Default board: hardware/kicad/pcbai_fpv4in1.kicad_pcb

set -uo pipefail

BOARD="${1:-hardware/kicad/pcbai_fpv4in1.kicad_pcb}"

# --staged <brought-csv>: per-stage PR mode. Propagates:
#   G1 audit_anchor_positions  → --staged <brought>     (parked anchors → PARK)
#   G2 audit_zone_contract     → --brought <brought>    (already supports)
#   G4 audit_decoupling        → --parked-exempt        (skip parked ICs/caps)
#   G5 audit_layout_compliance → --parked-exempt
#   G6 master_audit_invariants → --parked-exempt
# Example: master_pre_merge.sh <board.kicad_pcb> --staged S6
# Added 2026-05-26 (worker-caught: gates need staged-awareness; synthetic test
# boards have no parking concept so could not surface this class of bug).
STAGED_MODE=""
STAGED_BROUGHT=""
i=1
for arg in "$@"; do
  if [[ "$arg" == "--staged" ]]; then
    STAGED_MODE="--parked-exempt"
    # Next arg is the brought-csv (e.g. "S6" or "S6,CH1")
    next_idx=$((i + 1))
    if [[ $next_idx -le $# ]]; then
      STAGED_BROUGHT="${!next_idx}"
    fi
    break
  fi
  i=$((i + 1))
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SCRIPTS="$REPO_ROOT/hardware/kicad/scripts"

if [[ ! -f "$BOARD" ]]; then
  echo "FAIL: board file $BOARD not found"
  exit 1
fi

echo "════════════════════════════════════════════════════════════════════"
echo "Phase 4-v3 master pre-merge gate suite"
echo "Board: $BOARD"
echo "Date:  $(date '+%Y-%m-%d %H:%M:%S')"
echo "Commit: $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
echo "════════════════════════════════════════════════════════════════════"
echo

GATES_PASS=0
GATES_FAIL=0
GATES_WARN=0
GATES_SKIP=0
FAIL_DETAILS=()

run_gate() {
  local name="$1"
  local cmd="$2"
  local required="${3:-true}"  # true = must PASS, false = WARN allowed
  echo "──────────────────────────────────────────────────────────────────"
  echo "GATE: $name"
  echo "CMD:  $cmd"
  echo
  if eval "$cmd"; then
    echo "[$name] ✅ PASS"
    GATES_PASS=$((GATES_PASS + 1))
  else
    rc=$?
    if [[ "$required" == "true" ]]; then
      echo "[$name] ❌ FAIL (exit $rc)"
      GATES_FAIL=$((GATES_FAIL + 1))
      FAIL_DETAILS+=("$name")
    else
      echo "[$name] ⚠️  WARN (exit $rc, not blocking)"
      GATES_WARN=$((GATES_WARN + 1))
    fi
  fi
  echo
}

# ──────────────────────────────────────────────────────────────────
# G1: Tier 1 mechanical anchor lockfile diff
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_anchor_positions.py" ]] \
   && [[ -f "$REPO_ROOT/docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml" ]]; then
  G1_STAGED_ARGS=""
  if [[ -n "$STAGED_BROUGHT" ]]; then
    G1_STAGED_ARGS="--staged $STAGED_BROUGHT"
  fi
  run_gate "G1_anchor_positions" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_anchor_positions.py' '$BOARD' $G1_STAGED_ARGS" true
else
  echo "[G1_anchor_positions] ⏭  SKIP (script or lockfile missing — pre-methodology-PR)"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G2: Zone contract (park-then-bring) — worker building
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_zone_contract.py" ]]; then
  # G2 takes --board <B> --brought <csv>; defaults brought="" (Stage 0 = foundation only)
  G2_BROUGHT_ARG="--brought $STAGED_BROUGHT"
  run_gate "G2_zone_contract" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_zone_contract.py' --board '$BOARD' $G2_BROUGHT_ARG" true
else
  echo "[G2_zone_contract] ⏭  SKIP (script not yet built by worker)"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G3: Switching loop area per channel (Erickson 50mm² target)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_loop_area.py" ]]; then
  run_gate "G3_loop_area" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_loop_area.py' '$BOARD' --placement-only" true
else
  echo "[G3_loop_area] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G4: Per-IC decoupling R25 (≤3mm same-layer)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_decoupling.py" ]]; then
  run_gate "G4_decoupling" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_decoupling.py' '$BOARD' $STAGED_MODE" true
else
  echo "[G4_decoupling] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G5: audit_layout_compliance.py — 11+ existing classes
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_layout_compliance.py" ]]; then
  run_gate "G5_layout_compliance" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_layout_compliance.py' '$BOARD' $STAGED_MODE" true
else
  echo "[G5_layout_compliance] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G6: master_audit_invariants.py — 5 invariant gates
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/master_audit_invariants.py" ]]; then
  run_gate "G6_master_invariants" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/master_audit_invariants.py' '$BOARD' docs/BOARD_INVARIANTS.md $STAGED_MODE" true
else
  echo "[G6_master_invariants] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G7: audit_routing.py — 6 routing checks (only if board has tracks)
# ──────────────────────────────────────────────────────────────────
TRACK_COUNT="$(python3 -c "
import pcbnew
b = pcbnew.LoadBoard('$BOARD')
print(sum(1 for t in b.GetTracks() if isinstance(t, pcbnew.PCB_TRACK)))
" 2>/dev/null || echo 0)"

if [[ "$TRACK_COUNT" -gt 0 ]] && [[ -f "$SCRIPTS/audit_routing.py" ]]; then
  run_gate "G7_routing" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_routing.py' '$BOARD'" true
else
  echo "[G7_routing] ⏭  SKIP (no tracks: $TRACK_COUNT)"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G8: audit_routing_system.py — drift detection on methodology hashes
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_routing_system.py" ]]; then
  run_gate "G8_routing_system_drift" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_routing_system.py'" true
else
  echo "[G8_routing_system_drift] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G12: Tier 4 differential pair length match
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_diff_pair_match.py" ]]; then
  run_gate "G12_diff_pair_match" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_diff_pair_match.py' '$BOARD'" true
else
  echo "[G12_diff_pair_match] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G13: Tier 4 Kelvin shunt sense routing
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_kelvin_shunt_routing.py" ]]; then
  run_gate "G13_kelvin_shunt" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_kelvin_shunt_routing.py' '$BOARD'" true
else
  echo "[G13_kelvin_shunt] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G14: Tier 1 PDN via stitching density
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_via_stitching_density.py" ]]; then
  run_gate "G14_via_stitching" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_via_stitching_density.py' '$BOARD'" true
else
  echo "[G14_via_stitching] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G15: Tier 5 signal highway length match
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_length_match.py" ]]; then
  run_gate "G15_length_match" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_length_match.py' '$BOARD'" true
else
  echo "[G15_length_match] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G11: Vision check render set present (per VISION_CHECK_METHODOLOGY.md)
# Master visually inspects content per VISION_CHECK_METHODOLOGY.md §3 checklist
# ──────────────────────────────────────────────────────────────────
RENDER_DIR_CANDIDATE="$(find "$REPO_ROOT/sims" -type d -name renders 2>/dev/null | sort | tail -1)"
if [[ -n "$RENDER_DIR_CANDIDATE" ]] && [[ -d "$RENDER_DIR_CANDIDATE" ]]; then
  required_files=("RENDER_SET_MANIFEST.md" "top.png" "bottom.png" "iso.png" "zone_zoom.png" "diff.png")
  missing=()
  for f in "${required_files[@]}"; do
    if [[ ! -f "$RENDER_DIR_CANDIDATE/$f" ]]; then
      missing+=("$f")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    echo "[G11_vision_check_render_set] ✅ PASS — render set complete in $RENDER_DIR_CANDIDATE"
    GATES_PASS=$((GATES_PASS + 1))
  else
    echo "[G11_vision_check_render_set] ❌ FAIL — missing in $RENDER_DIR_CANDIDATE:"
    for f in "${missing[@]}"; do echo "  - $f"; done
    echo "  Generate via: python3 $SCRIPTS/render_pr_visual.py <board> $RENDER_DIR_CANDIDATE --subsystem <Sn|CHn> --diff-against origin/master"
    GATES_FAIL=$((GATES_FAIL + 1))
    FAIL_DETAILS+=("G11_vision_check_render_set")
  fi
else
  echo "[G11_vision_check_render_set] ⏭  SKIP (no renders dir found; pre-Stage0 PR exempt)"
  GATES_SKIP=$((GATES_SKIP + 1))
fi
echo

# ──────────────────────────────────────────────────────────────────
# G10: verify_spec_diff.py — R20 mirror geometry gate (CH1↔CH2/3/4 ≤2mm)
# Wired 2026-05-26 to close R20 GAP. Symmetric-mirror channels only.
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/verify_spec_diff.py" ]]; then
  # In --staged mode: parked mirror partners aren't on-board → skip gate
  if [[ -n "$STAGED_MODE" ]]; then
    echo "[G10_spec_diff_R20] ⏭  SKIP (staged mode — partner channels not all brought)"
    GATES_SKIP=$((GATES_SKIP + 1))
  else
    run_gate "G10_spec_diff_R20" \
      "cd '$REPO_ROOT' && python3 '$SCRIPTS/verify_spec_diff.py' '$BOARD'" true
  fi
else
  echo "[G10_spec_diff_R20] ⏭  SKIP (script missing)"
  GATES_SKIP=$((GATES_SKIP + 1))
fi
echo

# ──────────────────────────────────────────────────────────────────
# G9: target.h md5 (firmware contract lock)
# ──────────────────────────────────────────────────────────────────
TARGET_H="$REPO_ROOT/firmware/am32-target/PCBAI_FPV4IN1_F421.target.h"
EXPECTED_MD5="7a4549d27e0e83d3d6f1ffaf67527d24"
if [[ -f "$TARGET_H" ]]; then
  ACTUAL_MD5="$(md5sum "$TARGET_H" | awk '{print $1}')"
  if [[ "$ACTUAL_MD5" == "$EXPECTED_MD5" ]]; then
    echo "[G9_target_h_md5] ✅ PASS ($ACTUAL_MD5)"
    GATES_PASS=$((GATES_PASS + 1))
  else
    echo "[G9_target_h_md5] ❌ FAIL"
    echo "  expected: $EXPECTED_MD5"
    echo "  actual:   $ACTUAL_MD5"
    GATES_FAIL=$((GATES_FAIL + 1))
    FAIL_DETAILS+=("G9_target_h_md5")
  fi
else
  echo "[G9_target_h_md5] ⏭  SKIP (target.h not found at $TARGET_H)"
  GATES_SKIP=$((GATES_SKIP + 1))
fi
echo

# ──────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "Master pre-merge gate suite — SUMMARY"
echo "  PASS: $GATES_PASS"
echo "  FAIL: $GATES_FAIL"
echo "  WARN: $GATES_WARN"
echo "  SKIP: $GATES_SKIP"
echo "════════════════════════════════════════════════════════════════════"

if [[ $GATES_FAIL -gt 0 ]]; then
  echo
  echo "❌ MERGE BLOCKED — failed gates:"
  for g in "${FAIL_DETAILS[@]}"; do
    echo "  - $g"
  done
  echo
  echo "Per [[feedback-master-gate-checklist]]: ANY FAIL = REJECT PR."
  exit 1
fi

echo
echo "✅ ALL REQUIRED GATES PASSED — PR can be merged"
exit 0
