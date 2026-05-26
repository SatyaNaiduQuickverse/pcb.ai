# Audit-suite gap analysis — 2026-05-26 Sai catch (bbox overlap)

**Trigger**: Sai visual catch on CH1 placement found 57 same-layer component-body bbox overlaps. We had 55 BLOCKING gates active and ALL passed. The board would have shipped with components stacked on top of each other.

This document maps WHY this happened and what structural changes prevent any class of audit-coverage failure in the future. Per Sai's "go beyond, both outward and inward".

## 1. The immediate failure

`audit_layout_compliance.py` (G5) checks **pad-overlap-different-net** — DRC-level. That correctly returned 0 (no copper short → fab won't reject). But "no copper short" ≠ "components don't physically stack". G5 does NOT check component body extents.

`verify_placement.py` HAS contained body bbox-overlap detection since Phase 4-v1 (Task #47, 2026-05-22). It uses `pcbnew BOX2I::Intersects()`. **It was never wired into `master_pre_merge.sh`** during the Phase 4-v1 → v2 → v3 migrations.

## 2. The class of failure (the real bug)

The audit suite is built by **append**, never by **inventory**. Pattern:
- Sai catches something visually → I add a specialized gate → ship → repeat
- Audit-suite surface area grows monotonically
- BUT no process ever asks: "for every audit script in the codebase, is it actually wired in?"
- BUT no process ever asks: "what dimensions of correctness have ZERO gates?"

The 55-gate count is **growing breadth without depth verification**.

## 3. Audit script inventory (master HEAD 2026-05-26)

Total scripts: 49 (45 `audit_*.py` + 1 `verify_*.py` + 3 sim audits)
Wired into `master_pre_merge.sh` as BLOCKING: 45
**Orphaned (exist but never run)**:
| Script | Purpose | Why orphaned |
|---|---|---|
| `verify_placement.py` | Phase 4-v1 bbox overlap + grid + MCU rotation | Never migrated to v3 suite |
| `audit_body_bbox_overlap.py` | NEW — explicit G_PP11 body bbox | Just added; needs wiring |
| `audit_3d_model_coverage.py` | 3D STEP model assignment per footprint | OQ-009 follow-up; never wired |
| `audit_diff_pair_z0.py` | Diff-pair impedance | Routing-phase; queued for Phase 5 |
| `audit_meta.py` | Meta-audits including hash chain | Partially wired (need to verify) |

## 4. Audit-dimension gap map (what we DON'T check at all)

### Component-level (going OUTWARD)
| Dimension | Current gate | Status |
|---|---|---|
| Body bbox overlap (same layer) | **G_PP11 new** | gap closed (this PR) |
| Body bbox overlap **through board** (F.Cu tall vs B.Cu tall at same XY) | none | **NEW GAP** — needs G_PP12 z-aware-3D-overlap |
| Component vs enclosure top/bottom (Z clearance) | none | **NEW GAP** — needs G_PP13 enclosure_clearance |
| Component vs reserved routing highway (XY, all components not just mount holes) | only mount holes (G_M8) | **NEW GAP** — needs G_PP14 component_vs_highway |
| Component vs panelization v-groove | none | Phase 7 (panelization) |
| Tall-component (cap, inductor) keep-clear for heatsink mounting | none | **NEW GAP** — needs G_PP15 heatsink_keepout |
| Connector cable swing radius | G_M3 `audit_cable_swing` | exists |

### Pad-level
| Dimension | Current gate | Status |
|---|---|---|
| Pad overlap diff-net | G5 | exists |
| Pad creepage (HB-cell aware) | G_PP6 | exists |
| Pad-to-edge clearance | G_M14 | exists (just added) |
| Pad-to-mount-hole | G_M7 | exists |
| Pad annular ring (PTH) | none | **NEW GAP** — DRC catches but no early-stage audit |
| Pin1 indicator presence | G_PP10 `polarity_marker` | exists |
| Solder paste mask opening | none | DFM-stage; fab catches |

### Net-level
| Dimension | Current gate | Status |
|---|---|---|
| Trace ampacity | G_R `via_current_capacity` | exists |
| Plane via stitching | G_R6 + `via_stitching_density` | exists |
| Diff-pair length matching | `length_match` + `diff_pair_match` | exists |
| Diff-pair impedance | `diff_pair_z0` | **orphan** — wire in (Phase 5) |
| Kelvin sense routing | `kelvin_shunt_routing` | exists |
| Return-path continuity | `return_path` | exists |
| Stub length on high-speed | `stub_length` | exists |

### Zone/region/symmetry
| Dimension | Current gate | Status |
|---|---|---|
| Subsystem zone tile continuity | G_Z1 | exists |
| Component in declared zone | G5 | exists |
| Mirror pair coordinate match (CH1↔CH2) | `audit_invariants` partial | **partial — does it diff actual vs mirror-derived?** |
| Per-channel passive count match (CH1 BOM == CH2 BOM) | none | **NEW GAP** — needs G_PP16 channel_bom_match |
| EMC isolation (BEC ↔ Hall ≥15mm) | none | **NEW GAP** — needs G_PP17 emc_distance (BILATERAL.md §40) |
| Thermal forbidden pair (BEC under Hall) | none | **NEW GAP** — needs G_PP18 thermal_forbidden |

### Process/meta
| Dimension | Current gate | Status |
|---|---|---|
| BOM completeness | G_M1-M2 + `bom_lcsc` | exists |
| Assembly drawing | G_M5 | exists |
| Doc-sync (RULES_MANIFEST ↔ AUDIT_VALIDATION) | G_D `doc_sync` | exists |
| Hash chain validity | `audit_meta` | partial |
| Lockfile completeness | `lockfile_completeness` | exists |
| Spec diff vs locked-reference | `verify_spec_diff` | exists |

### META (going INWARD)
| Dimension | Current gate | Status |
|---|---|---|
| Every audit script wired into pre_merge | none | **NEW GAP** — needs G_META1 audit_coverage |
| Every audit has documented exempt-list | none | **NEW GAP** — needs G_META2 exempt_list_documented |
| Every audit has known-good + known-bad self-test | none | **NEW GAP** — needs G_META3 audit_self_test |
| Every R-rule has named audit function | none | **NEW GAP** — needs G_META4 rule_to_audit_map |
| Every audit declares its coverage (what it checks/doesn't) | none | **NEW GAP** — needs G_META5 audit_coverage_declaration |

## 5. Going OUTWARD — new audit dimensions to add

Beyond fixing the orphans, these are dimensions we've never audited but a SOTA process would:

- **3D component-vs-component through-board collision** — tall F.Cu cap + tall B.Cu cap at same XY = collision if heights sum > board thickness + buffer
- **Enclosure clearance** — component max-height ≤ (enclosure_inner_height - board_thickness) per side
- **Heatsink-mounting keep-clear** — tall components within heatsink footprint XY break thermal contact
- **EMC isolation matrix** — for every pair of subsystem types (BEC↔Hall, BEC↔FET, BEMF↔SW, MCU-clock↔HV), enforce minimum XY distance per BILATERAL_PLACEMENT.md §40
- **Thermal forbidden pairs** — BEC NOT under Hall (BILATERAL §50)
- **Channel BOM-match** — CH1 component count + ref-pattern == CH2/3/4 BOM-by-pattern (catches a missing per-channel cap silently)
- **Strain relief on through-hole connectors** — drilled hole adjacent to connector pad for cable tie-down
- **Pin-1 visibility from top** — pin-1 indicator silk readable in assembly orientation
- **Test-point label readability** — TP refs not under other components / readable orientation

## 6. Going INWARD — auditing the audit suite itself

The audit scripts ARE software. Each can have bugs, missing cases, stale thresholds. Inward dimensions:

- **G_META1 audit_coverage**: meta-script that scans `hardware/kicad/scripts/audit_*.py` + `verify_*.py` and FAILS if any are not referenced in `master_pre_merge.sh`. Catches future migration drift.
- **G_META2 exempt_list_documented**: every audit that has an EXEMPT_LIST must store it in `docs/EXEMPT_LISTS/<audit_name>.txt` with a comment per entry justifying it. No inline silent skips.
- **G_META3 audit_self_test**: every audit script has a `--self-test` mode that loads `tests/fixtures/known_good.kicad_pcb` (must PASS) + `known_bad.kicad_pcb` (must FAIL). Run nightly + on every audit script change.
- **G_META4 rule_to_audit_map**: every R-rule in `RULES_MANIFEST.md` declares its enforcing audit function. RULES_MANIFEST diff vs `master_pre_merge.sh` actual gates must match.
- **G_META5 audit_coverage_declaration**: every audit script's `__doc__` declares: (a) what it checks, (b) what it explicitly does NOT check, (c) known false-positive/false-negative cases.

## 7. Process change going forward

Rule (to be added to feedback memory):
**Every PR that adds an audit function MUST also wire it into `master_pre_merge.sh` as BLOCKING in the same commit, OR include an explicit OQ documenting why it's deferred.** Orphaned audits = banned.

Rule:
**Every Sai-catch root cause analysis MUST consider whether the catch class can manifest in another audit dimension we don't currently cover — and add a new gate for that dimension preemptively.**

Rule:
**The audit suite is itself part of the deliverable. It deserves audits. G_META gates enforce.**

## 8. PR plan

This batch (immediate):
- **PR A**: wire G_PP11 (body bbox overlap) + verify_placement.py + audit_meta.py + audit_3d_model_coverage.py + G_META1 audit_coverage. Plug all 5 orphans + add the meta-coverage check.

Follow-ups (queued):
- **PR B**: G_PP12 3D-through-board overlap + G_PP13 enclosure clearance + G_PP14 component vs highway + G_PP15 heatsink keepout
- **PR C**: G_PP16 channel BOM match + G_PP17 EMC isolation matrix + G_PP18 thermal forbidden
- **PR D**: G_META2-M5 — exempt-list documentation, self-test framework, rule-to-audit-map enforcement, audit-coverage declarations
- **PR E**: per-audit `--self-test` mode + `tests/fixtures/known_good.kicad_pcb` + `known_bad.kicad_pcb`

After all 5 PRs: gate count grows from 55 to ~70 BLOCKING + 5 META gates, with each audit self-testable, and the suite itself audit-coverage-verified.

## 9. Honest reflection

The audit-suite-completeness gap is the kind of mistake that would have shipped a board with overlapping components — fabricated, assembled, then DOA. Sai's eye caught what 55 gates missed. The lesson: gate-count is vanity, gate-coverage is sanity. Build dimension-coverage discipline, not gate-count theater.
