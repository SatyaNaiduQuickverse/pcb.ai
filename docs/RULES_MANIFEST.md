# RULES_MANIFEST — single source of truth for project rules

Per Sai 2026-05-24 systemic directive: "we dont want this kind of misses again
make sure.. put guidelines in place it happens that claude drifts and forgets
but change the system in such way to prevent that.. also for rest of our
rules.. redo whatever needs to be done dont cut back or leave any loose ends".

Every rule in this manifest must have **all 3 artifacts**:
1. **Codified fix script** — runnable Python that repairs the rule on demand
2. **Codified audit gate** — `check_*()` function in `audit_layout_compliance.py`
   or `audit_routing.py` that detects violation programmatically
3. **Master-verified status** — date master last independently regression-tested
   the gate against known-bad input

Rules without all 3 artifacts are flagged **GAP** — must be addressed before
the next merge.

Verify via `python3 hardware/kicad/scripts/audit_meta.py` (greps the script
files to confirm every named function/script in this manifest actually exists).

---

## CLAUDE.md rules R1-R25 — automated where possible

| # | Rule | Fix script | Audit gate | Master verified | Status |
|---|---|---|---|---|---|
| R1 | Read before acting | N/A (behavioral) | N/A | — | ✅ process rule, not auditable |
| R2 | Document contract before code | N/A (behavioral) | N/A | — | ✅ process rule |
| R3 | Never invent technical specifics | N/A (behavioral) | N/A | — | ✅ process rule |
| R4 | Match scope to request | N/A (behavioral) | N/A | — | ✅ process rule |
| R5 | For HW changes actually run it | manual (build/sim) | N/A | — | ✅ process rule, but see R18/R22 |
| R6 | Self-validate before "done" | manual checks | N/A | — | ✅ process rule |
| R7 | Verify destructive actions | manual (confirm) | N/A | — | ✅ process rule |
| R8 | Open questions in docs/OPEN_QUESTIONS.md | manual | N/A | — | ✅ process rule |
| R9 | Don't re-introduce known bugs | known-traps memory + audit gates | (see specific gates below) | — | ✅ enforced via per-rule gates |
| R10 | Comments are non-obvious WHY | code review | N/A | — | ✅ process rule |
| R11 | Memory hygiene | memory file structure | N/A | — | ✅ process rule |
| R12 | Communicate tightly | N/A (behavioral) | N/A | — | ✅ process rule |
| R13 | Stop and ask when ambiguous | N/A | N/A | — | ✅ process rule |
| R14 | Never bypass safety checks | hooks + manual | N/A | — | ✅ process rule |
| R15 | Don't write code owner didn't ask for | code review | N/A | — | ✅ process rule |
| R16 | Personal vs project separate | memory structure | N/A | — | ✅ process rule |
| R17 | No loose threads | this manifest | `audit_meta.py` | 2026-05-24 master | ✅ **NEW: enforced via meta-check** |
| R18 | Sim execution gate (4-point evidence) | (sim regen scripts per subsystem) | N/A (PR doc review) | — | ✅ process rule, master gate |
| R19 | Symmetry preserves work | `route_mirror_ch1_to_ch234.py`, `place_channel_passives_role_aware.py` | `check_symmetry()` (audit_layout L161), `check_route_symmetry()` (audit_routing L159) | 2026-05-23 master PR #68 | ✅ |
| R20 | Spec-vs-placement gate | `scripts/verify_spec_diff.py` | manual (script invoke) | 2026-05-23 master PR #68 | ⚠️ GAP — script exists but not called in audit_layout main; ADD to audit_meta lookup |
| R21 | Worker deviation disclosure | PR doc template | N/A (PR review) | — | ✅ process rule, master gate |
| R22 | Verify artifact not exit code | (sim/audit verify steps) | N/A (PR review) | — | ✅ process rule, parent of R5/R18/R20 |
| R23 | No passive island | `place_channel_passives_role_aware.py`, `auto_anchor_passives.py` | `check_passive_anchoring()` (audit_layout L243) | 2026-05-24 master PR #71 | ✅ |
| R24 | No off-board footprints | `anchor_off_board.py` | `check_off_board()` (audit_layout L55, pad-extent-aware as of 2026-05-24) | 2026-05-24 master | ✅ **upgraded to pad-extent** |
| R25 | Same-side decoupling | `place_channel_passives_role_aware.py` (anchor + same-layer keep) | sub-rule of `check_decoupling()` (audit_layout L275) — **GAP: doesn't check layer match** | — | ⚠️ GAP — extend check_decoupling to also verify same-layer |

---

## Sai-eye-catch classes — every catch becomes a permanent audit gate

| # | Catch | Date | Fix script | Audit gate | Master verified | Status |
|---|---|---|---|---|---|---|
| 1 | pad-in-body-bbox (library footprint quirks like Allegro_CB_PFF) | 2026-05-23 | `fix_u1_hall_footprint.py` | `check_pad_in_body_bbox()` (audit_layout L330) | 2026-05-24 PR #71 | ✅ |
| 2 | motor-pad-clear (solder access keep-out) + sense-net exemption | 2026-05-23 / refined 2026-05-24 | (placement strategy in `place_channel_passives_role_aware.py`) | `check_motor_pad_clear()` (audit_layout L501) with `_has_motor_adjacent_net_pad()` exemption | 2026-05-24 PR #71 | ✅ |
| 3 | quadrant-balance 3-bucket | 2026-05-23 | (placement strategy) | `check_quadrant_count_balance()` (audit_layout L639) | 2026-05-24 PR #71 | ✅ |
| 4 | TP-spacing (probe access ≥4mm c-to-c) | 2026-05-23 | `fix_tp_spacing.py`, `place_swd_boot_tps.py` | `check_test_point_spacing()` (audit_layout L417) | 2026-05-24 master | ✅ **re-codified after regression** |
| 5 | external-connector-edge (J14/J12 ≤5mm from edge) | 2026-05-23 | `fix_tp_spacing.py` (includes J14/J12 repositions) | `check_external_connector_edge()` (audit_layout L444) | 2026-05-24 master | ✅ |
| 6 | per-channel-passive-quadrant | 2026-05-23 | `place_channel_passives_role_aware.py` | `check_per_channel_passive_quadrant()` (audit_layout L754) | 2026-05-24 PR #71 | ✅ |
| 7 | coincident-placement (<1.5mm c-to-c real bug) | 2026-05-24 | `fix_coincident_placements.py` | `check_coincident_placement()` (audit_layout L392) | 2026-05-24 PR #71 | ✅ |
| 8 | fiducials (≥3 per side, ≥40mm separation) | 2026-05-24 | `place_fiducials.py` | `check_fiducials()` (audit_layout L465) | 2026-05-24 master | ✅ **NEW this PR** |
| 9 | label-overlap (silkscreen refdes piling) | 2026-05-24 | (manual: re-position refdes via KiCad GUI or hide silk for tight clusters) | `check_label_overlap()` (audit_layout) | 2026-05-24 master | ✅ **NEW this PR** — detection only; manual fix |
| 10 | silk-on-pad (silk text touching copper pad, DFM) | 2026-05-24 | (manual: re-position refdes off pad) | `check_silk_on_pad()` (audit_layout) | 2026-05-24 master | ✅ **NEW this PR** — detection only; manual fix |
| 11 | fp-layer-mismatch (text-edit-without-flip trap recurrence) | 2026-05-24 | `flip_bcu_footprints.py` | `check_fp_layer_mismatch()` (audit_layout) | 2026-05-24 master | ✅ **NEW this PR** — the 162-footprint trap that masked PR #71 audit |
| 12 | LED-indicator stub on power net (track-width sub-class) | PR #67 amendment | `fix_led_stub_width.py` | `check_track_width()` (audit_routing) | 2026-05-24 master | ✅ **NEW this PR** — was one-shot patch; now codified |
| 13 | ZONE_FILLER on-pad-via absorption trap | PR-routing-final O1 | offset-via-with-stub pattern in `route_power_plane_stitch.py` (NEW) | (audit_meta could grow `check_post_zonefill_vias` step — TBD) | 2026-05-24 master | ⚠️ Trap documented `[[reference-pcbnew-zone-filler-onpad-trap]]`; deeper DRC pad-to-plane connectivity under master/Sai review |
| 14 | component-inside-body (small fp inside larger fp's silk bbox; fab-blocking) | 2026-05-24 Sai-catch #12 | `relocate_inside_body_invaders.py` (WIP) + structural fix to `auto_anchor_passives.py` + `place_channel_passives_role_aware.py` (silk-bbox keep-out for hosts ≥5mm²) | `check_component_inside_body()` (audit_layout) — area-ratio ≥4×, same-layer, motor-adjacent-net exempt | 2026-05-24 master | ✅ **NEW gate added**; 46 fab-blockers detected on master baseline; relocation strategy under master/Sai review per `[[feedback-anchor-outside-parent-body]]` |

---

## Memory feedback/reference rules

| # | Memory | Class | Fix script | Audit gate | Status |
|---|---|---|---|---|---|
| M1 | feedback-flip-bcu-footprints-recurrence | trap-class | `flip_bcu_footprints.py` | (no direct check; trap detected via PAD-OVERLAP regression) | ⚠️ **GAP — add `check_fp_layer_mismatch()`** |
| M2 | feedback-motor-pad-clear-zone | rule refinement | (see catch #2) | (see catch #2 with `_has_motor_adjacent_net_pad()` exemption) | ✅ |
| M3 | feedback-no-passive-island | R23 | (see R23) | (see R23) | ✅ |
| M4 | feedback-no-unplaced-footprints | R24 | (see R24) | (see R24) | ✅ |
| M5 | feedback-redo-not-mitigate | process rule | N/A | N/A | ✅ process rule |
| M6 | feedback-root-cause-not-symptom | process rule | N/A | N/A (PR doc template required Symptom/Fix/RootCause/Prevention) | ✅ process rule |
| M7 | feedback-sai-catches-are-samples | meta-rule | this manifest + audit_meta.py | meta-enforcement via audit_meta.py | ✅ **this PR enforces** |
| M8 | feedback-sim-execution-gate | R18 | (per-sim regen scripts) | N/A (PR doc review with 4-point evidence) | ✅ process rule |
| M9 | feedback-spec-vs-placement-gate | R20 | `verify_spec_diff.py` | (see R20 — GAP flagged) | ⚠️ GAP — see R20 |
| M10 | feedback-symmetry-preserves-work | R19 | (see R19) | (see R19) | ✅ |
| M11 | feedback-worker-deviation-disclosure | R21 | N/A | N/A (PR doc required "Spec deviations" section) | ✅ process rule |
| M12 | feedback-systemic-rule-enforcement | 2026-05-24 Sai | this manifest | `audit_meta.py` | ✅ **this PR delivers** |
| M13 | feedback-codify-not-patch | 2026-05-24 master | this manifest | `audit_meta.py` | ✅ **this PR enforces** |
| M14 | reference-kinet2pcb-silent-drop | trap-class | `fix_fet_netlist_drop.py` + `flip_bcu_footprints.py` | (post-fix audit + R24 check) | ✅ |

---

## Phase 7-prep deliverables (informational, not auditable)

| # | Doc | Class | Notes |
|---|---|---|---|
| P7-1 | `docs/PHASE7_MECH_PREP.md` | mech-hardware spec (heatsink + TIM + mounting) | Doc-only; specifies hardware to realize Phase 5c thermal sim h_bottom=1500 W/m²K. Master 2026-05-24 adjudicated Q2-Q7; Q1 (form factor) pending Sai. Informational entry — not gated by audit_meta. |

---

## GAP summary — to address in this PR

| Gap | Type | Action |
|---|---|---|
| R20 audit integration | call gap | Add `verify_spec_diff.py` invocation to audit pipeline or have `audit_meta.py` flag it |
| R25 same-side-decoupling | sub-check missing | Extend `check_decoupling()` to verify cap-layer == IC-layer |
| Catch #9 label-overlap | new gate (detect-only) | `check_label_overlap()` added in audit_layout; fix is manual refdes reposition |
| Catch #10 silk-on-pad | new gate (detect-only) | `check_silk_on_pad()` added in audit_layout; fix is manual refdes reposition |
| M1 flip_bcu trap detection | new gate | Add `check_fp_layer_mismatch()` — detect fp.GetLayer() vs pad.GetLayerSet() disagreement |

**Total identified gaps: 5** (3 new audit gates, 1 sub-check extension, 1 pipeline integration)

---

## Process for adding a new rule

1. Sai or master identifies the issue → save memory entry per
   `[[feedback-sai-catches-are-samples]]`
2. Author the fix script under `hardware/kicad/scripts/` (codified fix)
3. Author the audit gate function in `audit_layout_compliance.py` or
   `audit_routing.py` and call it from main
4. Add row to this manifest with all 4 columns
5. Run `audit_meta.py` — must show 0 GAPs
6. Master independently verifies on known-bad input + sets verification date

---

## Where audit_meta.py lives

`hardware/kicad/scripts/audit_meta.py` — parses this manifest, greps each named
function/script, fails with exit code 1 if any rule has GAP status. Master
runs before every layout PR merge.

```bash
python3 hardware/kicad/scripts/audit_meta.py
```

## Post-kinet2pcb pipeline

`hardware/kicad/scripts/post_kinet2pcb_pipeline.py` chains all idempotent
fix-scripts so a fresh kinet2pcb import → run this → board back to compliant
state. Per Sai 2026-05-24 systemic directive — manual fixes can never go
un-applied after re-import.

```bash
python3 hardware/kicad/scripts/post_kinet2pcb_pipeline.py
```

Pipeline order (each step idempotent, audited after):
1. `fix_fet_netlist_drop.py`
2. `flip_bcu_footprints.py`
3. `fix_u1_hall_footprint.py`
4. `setup_board.py` (8L stackup + edges + mount holes)
5. `place_board.py` (S0-S6 IC-level placement)
6. `place_channel_passives_role_aware.py` (role-driven channel passives)
7. `anchor_off_board.py` (off-board recovery)
8. `fix_tp_spacing.py` (TP 4mm c-to-c)
9. `place_swd_boot_tps.py` (algorithmic SWD/BOOT TPs)
10. `place_fiducials.py` (JLC SMT fiducials)
11. `fix_coincident_placements.py` (final coincident clearance)
