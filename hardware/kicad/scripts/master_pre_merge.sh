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
# Set KICAD 3D model dir per worker-local install (per [[reference-nova-coord]] +
# kicad-packages3D location). Without this, G_M15 falsely reports all 529 fps
# as missing 3D models (it's just env var unset, not a real defect).
export KICAD9_3DMODEL_DIR=${KICAD9_3DMODEL_DIR:-/home/novatics64/escworker/local/kicad-packages3D}

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
# G16: connector symmetry (proactive 2026-05-26 per Sai)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_connector_symmetry.py" ]]; then
  run_gate "G16_connector_symmetry" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_connector_symmetry.py' '$BOARD'" true
else
  echo "[G16_connector_symmetry] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G17: board edge keepout (proactive — codifies Sai-#5 J14 catch)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_edge_keepout.py" ]]; then
  run_gate "G17_edge_keepout" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_edge_keepout.py' '$BOARD'" true
else
  echo "[G17_edge_keepout] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_FoS1: thermal Factor of Safety (Sai 2026-05-26 directive)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_fos_thermal.py" ]]; then
  run_gate "G_FoS1_thermal" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_fos_thermal.py'" true
else
  echo "[G_FoS1_thermal] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_L1: lockfile completeness (proactive catch-class)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_lockfile_completeness.py" ]]; then
  run_gate "G_L1_lockfile_completeness" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_lockfile_completeness.py' '$BOARD'" true
else
  echo "[G_L1_lockfile_completeness] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP1: polarity marker visibility (proactive — silent reverse-install class)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_polarity_marker.py" ]]; then
  run_gate "G_PP1_polarity_marker" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_polarity_marker.py' '$BOARD'" true
else
  echo "[G_PP1_polarity_marker] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP3: silk text size readability (JLC SMT ≥1mm)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_silk_size.py" ]]; then
  run_gate "G_PP3_silk_size" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_silk_size.py' '$BOARD'" true
else
  echo "[G_PP3_silk_size] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP6: HV creepage clearance (IPC-2221 B-grade for 27V VMOTOR)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_hv_creepage.py" ]]; then
  run_gate "G_PP6_hv_creepage" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_hv_creepage.py' '$BOARD'" true
else
  echo "[G_PP6_hv_creepage] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_M1/G_M2/G_M3 combined: JLC DFM (min trace + via drill + annular)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_jlc_dfm.py" ]]; then
  run_gate "G_M_jlc_dfm" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_jlc_dfm.py' '$BOARD'" true
else
  echo "[G_M_jlc_dfm] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_FoS2: trace ampacity FoS (post-routing)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_fos_current.py" ]]; then
  run_gate "G_FoS2_trace_ampacity" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_fos_current.py' '$BOARD'" true
else
  echo "[G_FoS2_trace_ampacity] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_R5: via current capacity FoS (post-routing)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_via_current_capacity.py" ]]; then
  run_gate "G_R5_via_current_capacity" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_via_current_capacity.py' '$BOARD'" true
else
  echo "[G_R5_via_current_capacity] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP2: pick-and-place head reach (small SMD near tall component)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_pickplace_reach.py" ]]; then
  run_gate "G_PP2_pickplace_reach" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_pickplace_reach.py' '$BOARD'" true
else
  echo "[G_PP2_pickplace_reach] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP4: component rotation alignment within subsystem (DFM uniformity)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_rotation_alignment.py" ]]; then
  run_gate "G_PP4_rotation_alignment" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_rotation_alignment.py' '$BOARD'" true
else
  echo "[G_PP4_rotation_alignment] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP5: TP probe-access clearance
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_test_point_access.py" ]]; then
  run_gate "G_PP5_tp_probe_access" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_test_point_access.py' '$BOARD'" true
else
  echo "[G_PP5_tp_probe_access] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP7: cable connector swing/bend-radius clearance
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_cable_swing.py" ]]; then
  run_gate "G_PP7_cable_swing" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_cable_swing.py' '$BOARD'" true
else
  echo "[G_PP7_cable_swing] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_FoS5: connector pin-current FoS
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_fos_pin_current.py" ]]; then
  run_gate "G_FoS5_pin_current" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_fos_pin_current.py' '$BOARD'" true
else
  echo "[G_FoS5_pin_current] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_R1: diff-pair Z0 impedance (trace width vs spec)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_diff_pair_z0.py" ]]; then
  run_gate "G_R1_diff_pair_z0" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_diff_pair_z0.py' '$BOARD'" true
else
  echo "[G_R1_diff_pair_z0] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_R3: return-path continuity (signal-layer ↔ ref-plane pour)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_return_path.py" ]]; then
  run_gate "G_R3_return_path" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_return_path.py' '$BOARD'" true
else
  echo "[G_R3_return_path] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_R6: antenna-structure prevention (aggressor net length ≤ λ/4 threshold)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_antenna_structure.py" ]]; then
  run_gate "G_R6_antenna_structure" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_antenna_structure.py' '$BOARD'" true
else
  echo "[G_R6_antenna_structure] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_FoS4: cap ripple-current FoS (BOM + sim)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_fos_cap_ripple.py" ]]; then
  run_gate "G_FoS4_cap_ripple" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_fos_cap_ripple.py'" true
else
  echo "[G_FoS4_cap_ripple] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_M4: BOM LCSC stock + part-number presence (pre-fab)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_bom_lcsc.py" ]]; then
  run_gate "G_M4_bom_lcsc" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_bom_lcsc.py'" true
else
  echo "[G_M4_bom_lcsc] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_R2: transmission-line stub length (post-routing)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_stub_length.py" ]]; then
  run_gate "G_R2_stub_length" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_stub_length.py' '$BOARD'" true
else
  echo "[G_R2_stub_length] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_R4: aggressor-victim crosstalk spacing (post-routing)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_crosstalk_spacing.py" ]]; then
  run_gate "G_R4_crosstalk_spacing" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_crosstalk_spacing.py' '$BOARD'" true
else
  echo "[G_R4_crosstalk_spacing] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_FoS3: cap voltage derating FoS (BOM metadata)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_fos_cap_voltage.py" ]]; then
  run_gate "G_FoS3_cap_voltage" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_fos_cap_voltage.py'" true
else
  echo "[G_FoS3_cap_voltage] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_M6: JLC panelization fit
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_panel_fit.py" ]]; then
  run_gate "G_M6_panel_fit" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_panel_fit.py' '$BOARD'" true
else
  echo "[G_M6_panel_fit] ⏭  SKIP"
  GATES_SKIP=$((GATES_SKIP + 1))
  echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP8: anchor pitch uniformity (Sai-caught 2026-05-26)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_anchor_pitch.py" ]]; then
  run_gate "G_PP8_anchor_pitch" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_anchor_pitch.py'" true
else
  echo "[G_PP8_anchor_pitch] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP9: polarity-marker direction consistency
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_polarity_direction.py" ]]; then
  run_gate "G_PP9_polarity_direction" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_polarity_direction.py' '$BOARD'" true
else
  echo "[G_PP9_polarity_direction] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_Z1: subsystem zone tile continuity (no overlaps)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_zone_tile_continuity.py" ]]; then
  run_gate "G_Z1_zone_tile_continuity" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_zone_tile_continuity.py'" true
else
  echo "[G_Z1_zone_tile_continuity] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_M7-M13: mount-hole keep-out + pattern + symmetry + spacing + edge
# (Sai 2026-05-26 — class-of-mistake gate after H5-H8 cinematic-mount fiasco)
# 7 sub-gates in one script: mount-hole-vs-everything exhaustive audit
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_mount_hole_keepout.py" ]]; then
  run_gate "G_M7_through_M13_mount_hole_audit" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_mount_hole_keepout.py'" true
else
  echo "[G_M7_through_M13_mount_hole_audit] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────
# G_M14: pad-vs-board-edge clearance (Sai 2026-05-26 — my OWN class-of-mistake catch)
# I moved TP2 in PR #137 without checking pad bbox vs board edge -> G17 fail.
# G_M14 prevents recurrence: every fixed pad bbox >= MIN_PAD_EDGE_CLEAR from outline.
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_pad_edge_clearance.py" ]]; then
  run_gate "G_M14_pad_edge_clearance" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_pad_edge_clearance.py'" true
else
  echo "[G_M14_pad_edge_clearance] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP11: component-body bbox overlap (the BIG miss — Sai 2026-05-26)
# 57 same-layer body overlaps on CH1 passed every other audit.
# verify_placement.py existed since Phase 4-v1 Task #47 but was never wired.
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_body_bbox_overlap.py" ]]; then
  run_gate "G_PP11_body_bbox_overlap" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_body_bbox_overlap.py' '$BOARD'" true
else
  echo "[G_PP11_body_bbox_overlap] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_LEGACY_VERIFY_PLACEMENT: Phase 4-v1 Task #47 placement verifier
# Belt-and-suspenders alongside G_PP11.
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/verify_placement.py" ]]; then
  run_gate "G_LEGACY_verify_placement" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/verify_placement.py' '$BOARD'" true
else
  echo "[G_LEGACY_verify_placement] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_M15: 3D model coverage (OQ-009 follow-up — every footprint has .step assigned)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_3d_model_coverage.py" ]]; then
  run_gate "G_M15_3d_model_coverage" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_3d_model_coverage.py' '$BOARD'" true
else
  echo "[G_M15_3d_model_coverage] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_META_HASH: BOARD_INVARIANT_HASH chain validity
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_meta.py" ]]; then
  run_gate "G_META_HASH_chain" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_meta.py'" true
else
  echo "[G_META_HASH_chain] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_META1: audit-suite coverage (every audit script wired or explicitly deferred)
# Catches future "audit exists but never runs" gaps from phase migrations.
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_meta_coverage.py" ]]; then
  run_gate "G_META1_audit_coverage" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_meta_coverage.py'" true
else
  echo "[G_META1_audit_coverage] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP16: per-channel BOM consistency (R20 symmetry deep-check)
# Sai 2026-05-26 outward-thinking sweep — would catch a missing per-channel cap
# that mirror-transform forgot, before it ships.
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_channel_bom_match.py" ]]; then
  run_gate "G_PP16_channel_bom_match" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_channel_bom_match.py' '$BOARD'" true
else
  echo "[G_PP16_channel_bom_match] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_PP19/G_PP20/G_PP21: parametric placement framework (Sai 2026-05-26)
# - G_PP19 routing channel reserve (don't pack out routing space)
# - G_PP20 zone density budget (≤55% comp, ≥20% routing, ≥25% headroom)
# - G_PP21 parametric compliance (no hardcoded coords; consume parametric_placement.py)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_routing_channels.py" ]]; then
  run_gate "G_PP19_routing_channel_reserve" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_routing_channels.py' '$BOARD'" true
else
  echo "[G_PP19_routing_channel_reserve] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi
if [[ -f "$SCRIPTS/audit_zone_density.py" ]]; then
  run_gate "G_PP20_zone_density" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_zone_density.py' '$BOARD'" true
else
  echo "[G_PP20_zone_density] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi
if [[ -f "$SCRIPTS/audit_parametric_compliance.py" ]]; then
  run_gate "G_PP21_parametric_compliance" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_parametric_compliance.py'" true
else
  echo "[G_PP21_parametric_compliance] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# RENDER (non-blocking): net connectivity graph — Sai 2026-05-26 viz
# Auto-generates /tmp/board-render/latest/net_graph.png for visual review
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/render_net_connectivity_graph.py" ]]; then
  python3 "$SCRIPTS/render_net_connectivity_graph.py" "$BOARD" 2>&1 | tail -1 || true
fi

# ──────────────────────────────────────────────────────────────────
# R-sim-execution (Sai 2026-05-23 locked, wired 2026-05-26): 4-point sim proof
# G_FLOW1/2/3 (Sai 2026-05-26 lock): 7-step flow + adjacent sim + I/O port discipline
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_sim_execution.py" ]]; then
  run_gate "R_sim_execution" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_sim_execution.py'" true
else
  echo "[R_sim_execution] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi
if [[ -f "$SCRIPTS/audit_subsystem_flow.py" ]]; then
  run_gate "G_FLOW1_2_3_subsystem_flow" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_subsystem_flow.py'" true
else
  echo "[G_FLOW1_2_3_subsystem_flow] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# R-sim-provenance (2026-05-26 worker-caught CH1-placement-only-in-/tmp/ class):
# sim inputs/results MUST cite git-tracked paths; /tmp/ + ~/Desktop + ~/scratch
# + /home/<user>/local/*.kicad_pcb FAIL. Solver TOOL paths (ElmerSolver,
# openems libs) are exempt — only DATA artifact paths gate reproducibility.
if [[ -f "$SCRIPTS/audit_sim_artifact_provenance.py" ]]; then
  run_gate "R_sim_provenance" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_sim_artifact_provenance.py'" true
else
  echo "[R_sim_provenance] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# G_PP22 per-phase cluster uniformity (2026-05-26 worker-caught J22 class):
# transformable per-phase clusters MUST have uniform pitch within 0.5mm.
# G_M16 stackup layer count (Phase 4a-restack-10L 2026-05-26): board must have
# 10 enabled copper layers (F.Cu + In1-In8 + B.Cu). Catches accidental 8L drift
# after stackup upgrade. Per OQ-014 lock + STEP 6 loop-L preservation.
if [[ -f "$SCRIPTS/audit_stackup_layers.py" ]]; then
  run_gate "G_M16_stackup_layers" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_stackup_layers.py' '$BOARD'" true
else
  echo "[G_M16_stackup_layers] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# G_M17 stackup DIELECTRIC presence + lock (2026-05-27 independent-audit catch).
# G_M16 counts copper LAYERS; G_M17 verifies the board actually carries a
# (stackup) block AND the F.Cu→In1.Cu dielectric == 0.10mm (OQ-014 loop-L
# plane-reference LOCK). Without this the dielectric was a comment, never a
# fabricable definition → JLC default split → loop-L assumption breaks silently.
# FIX path: hardware/kicad/scripts/inject_stackup.py.
if [[ -f "$SCRIPTS/audit_stackup_dielectric.py" ]]; then
  run_gate "G_M17_stackup_dielectric" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_stackup_dielectric.py' '$BOARD'" true
else
  echo "[G_M17_stackup_dielectric] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# G_PWR_DRC power-net custom DRC (Sai 2026-05-26 — Pi-only, no kicad-cli OOM
# path). Catches catastrophic power-net clearance violations early (280A
# continuous = arc/fire risk). Complementary to subsystem-scope DRC.
# Runs ~2-5 min on full-board Pi. Memory bounded <2GB via 5mm window pre-filter.
if [[ -f "$SCRIPTS/audit_power_drc.py" ]]; then
  run_gate "G_PWR_DRC_power_net_drc" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_power_drc.py' '$BOARD'" true
else
  echo "[G_PWR_DRC_power_net_drc] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# WARN-tolerance was the bug — this is binary FAIL. Catches sign-typo class.
if [[ -f "$SCRIPTS/audit_per_phase_cluster_uniformity.py" ]]; then
  run_gate "G_PP22_per_phase_cluster_uniformity" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_per_phase_cluster_uniformity.py' '$BOARD'" true
else
  echo "[G_PP22_per_phase_cluster_uniformity] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# G_M5: assembly drawing completeness (CPL/BOM/rotation/value)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_assembly_drawing.py" ]]; then
  run_gate "G_M5_assembly_drawing" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_assembly_drawing.py' '$BOARD'" true
else
  echo "[G_M5_assembly_drawing] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_S2: sim mesh validity (Elmer mesh pre-solve sanity)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_sim_mesh_validity.py" ]]; then
  run_gate "G_S2_sim_mesh_validity" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_sim_mesh_validity.py'" true
else
  echo "[G_S2_sim_mesh_validity] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_S3: sim result physical-plausibility (T/I/V/P range check)
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_sim_result_sanity.py" ]]; then
  run_gate "G_S3_sim_result_sanity" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_sim_result_sanity.py'" true
else
  echo "[G_S3_sim_result_sanity] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP+1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_D1/G_D2/G_D3: doc-sync combined gate
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_doc_sync.py" ]]; then
  run_gate "G_D_doc_sync" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_doc_sync.py'" true
else
  echo "[G_D_doc_sync] ⏭  SKIP"
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
# G_SHUNT_FET_OVERLAP: §8#9 shunt-FET source pad overlap (PR #194)
# High-current shunt body MUST overlap its LS-FET source pad ≥1.5mm²
# (16-via 0.6mm array per IPC-2152, ~96A continuous). Staged mode skips
# parked shunts (x≥130) whose FET pair is also parked off-board (R27).
# Wired 2026-05-27 (master R26 G_META1 audit-integrity fix).
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_shunt_fet_source_overlap.py" ]]; then
  run_gate "G_SHUNT_FET_OVERLAP" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_shunt_fet_source_overlap.py' '$BOARD' $STAGED_MODE" true
else
  echo "[G_SHUNT_FET_OVERLAP] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP + 1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_SW_GND_VIA: SW commutation via ↔ GND-return via pairing (PR #198)
# Every SW (MOTOR_*_CHn) via needs a co-located GND through-via for clean
# commutation-loop inductance + EMI ringing prevention at 70A switching.
# Staged mode skips parked-channel SW vias (x≥130). Wired 2026-05-27
# (master R26 G_META1 audit-integrity fix).
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_sw_gnd_return_pair.py" ]]; then
  run_gate "G_SW_GND_VIA" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_sw_gnd_return_pair.py' '$BOARD' $STAGED_MODE" true
else
  echo "[G_SW_GND_VIA] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP + 1)); echo
fi

# ──────────────────────────────────────────────────────────────────
# G_HDI_VIA_IN_PAD: HDI via-in-pad cost-scope whitelist (PR #207)
# Any HDI microvia (≤0.15mm drill) in an SMD pad must be on the J18/J19
# QFN whitelist (cost envelope). Board-wide whitelist check — no staged
# mode (vacuous-pass when no HDI vias). Wired 2026-05-27 (master R26
# G_META1 audit-integrity fix).
# ──────────────────────────────────────────────────────────────────
if [[ -f "$SCRIPTS/audit_hdi_via_in_pad.py" ]]; then
  run_gate "G_HDI_VIA_IN_PAD" \
    "cd '$REPO_ROOT' && python3 '$SCRIPTS/audit_hdi_via_in_pad.py' '$BOARD'" true
else
  echo "[G_HDI_VIA_IN_PAD] ⏭  SKIP"; GATES_SKIP=$((GATES_SKIP + 1)); echo
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
