# Vision Check Methodology — robust feedback loop with eyes on every PR

**Single source of truth.** Master + worker discipline for visual verification.

Hash: VISION_CHECK_METHODOLOGY_HASH = (TBD)

---

## 0. Principle

Per Sai 2026-05-25:

> "see the feedback loop is robust with vision checks on subsystems"

Per `[[feedback-vision-check-gate]]` + `[[feedback-sai-catches-are-samples]]`:

Script audits catch geometric rules; eyes catch what scripts miss (silk-on-pad readability, density gestalt, route aesthetic, mechanical-clearance 3D gut-check, polarity-orientation consistency, subsystem visual identity).

Multiple prior Sai-catches were caught visually (Sai-eye-catch #9 label-overlap, #10 silk-on-pad, #11 component-inside-body, #11 fp-layer-mismatch). Each became a script gate AFTER eye caught it. But eyes are still needed for the next class of catches.

---

## 1. Render set per PR (mandatory)

Every per-subsystem PR (Phase 4-v3 Stages 0–10 + all future place/route PRs) auto-generates this render set, committed to `sims/<phase>/<subsystem>/renders/`:

| # | Render | Tool | Purpose |
|---|---|---|---|
| 1 | Top side full board (F.Cu + silk + paste) | `kicad-cli pcb render --side top` | Scan for silk-on-pad, label overlap, missing components, density imbalances |
| 2 | Bottom side full board (B.Cu + silk + paste) | `kicad-cli pcb render --side bottom` | Same as #1 for bottom |
| 3 | 3D iso NE perspective (with components) | `kicad-cli pcb export step` + `freecad-cli` render | Scan for component-inside-body, mechanical clearance, polarity orientation, height stacking |
| 4 | Per-zone zoom for THIS PR's subsystem | crop of #1/#2 to subsystem zone bbox + 5mm padding | Scan routing density, decoupling proximity, gestalt |
| 5 | Diff overlay (this PR vs prior master HEAD) | `render_pr_visual.py --diff` (master-built) | Confirm changes match stated scope, NO silent component moves |
| 6 | Cumulative thermal map (from R31 sim, if available) | Elmer + ParaView export PNG | T_J distribution sanity check |
| 7 | Cumulative EMI nearfield (from R31 sim, if available) | openEMS + matplotlib | E-field hotspot check |

For routing PRs add:
| # | Render | Tool | Purpose |
|---|---|---|---|
| 8 | Per-tier routing overlay (Tier N highlighted) | `render_routing_by_tier.py` | Verify tier completion + topology matches `routing_topology.yaml` |
| 9 | Per-net-class width/Z0 heatmap | extension of #8 | Verify constraint enforcement visually |

All renders at 300 DPI minimum, PNG format. Lossless.

---

## 2. Standardized render parameters (deterministic)

Eyes need consistent baselines to compare PR-to-PR.

| Parameter | Value |
|---|---|
| Top/bottom 2D render zoom | Full board, 1:1 scale, 300 DPI |
| 3D iso angle | Azimuth 45°, elevation 30° (NE high) |
| 3D iso lighting | Default KiCad/FreeCAD studio lighting |
| Zone zoom padding | 5mm beyond zone bbox |
| Diff overlay color | red (deletions), green (additions), blue (moves) |
| Silk text size | Render at fab DPI to assess readability |

Worker bakes these into `render_pr_visual.py`. Master verifies via render set checksum diff (parameter drift = re-render).

---

## 3. Master visual inspection checklist (per PR review)

Before posting PR verdict, master inspects each render against this checklist:

### Top + bottom 2D renders (#1, #2)
- [ ] No silk text overlapping pads (cross-check `check_silk_on_pad` script PASS)
- [ ] No silk text labels overlapping each other on same layer (cross-check `check_label_overlap`)
- [ ] All declared components present (count matches PR diff)
- [ ] Component density looks balanced (no extreme crowding or empty regions)
- [ ] Polarity marks visible and consistent orientation (diodes, electrolytic caps)
- [ ] Test points visible and not blocked by tall components

### 3D iso render (#3)
- [ ] No small component inside larger component's body bbox
- [ ] Tall components (electrolytic caps, connectors) clear of heatsink/enclosure interior
- [ ] Mating connectors (XT30, FC header) face correct direction for assembly
- [ ] Mount holes clear of components
- [ ] Channel symmetry visible (CH1/2/3/4 look like mirror images)

### Per-zone zoom (#4)
- [ ] Subsystem zone fully populated (no orphan components left in zone)
- [ ] No components leaked into adjacent zones or highway corridors
- [ ] Decoupling caps visibly adjacent to host ICs (gestalt check on `audit_decoupling` PASS)
- [ ] Routing within zone takes expected paths (no weird detours)

### Diff overlay (#5)
- [ ] All red (deletions) explained in PR description
- [ ] All green (additions) match PR scope (subsystem this PR builds)
- [ ] No blue (silent moves) of components NOT in this PR's scope
- [ ] Diff matches the `audit_zone_contract` PASS narrative (untouched stayed parked or in prior zone)

### Sim renders #6, #7 (when present)
- [ ] T_J peak within target (Phase 4-v3 ≤90°C local, ≤100°C cumulative)
- [ ] EMI hotspots correlate with declared switching cluster, not elsewhere

### Routing-PR renders #8, #9
- [ ] Tier highlighted matches PR's tier scope
- [ ] No tier-N+1 routing present (sequence violated)
- [ ] Width/Z0 heatmap shows uniform color within each class

---

## 4. Worker-side render generation (in PR workflow)

Worker's `place_subsystem.py` / `route_subsystem.py` automatically calls `render_pr_visual.py` at end of each script run. Renders committed to PR.

Worker also generates a `RENDER_SET_MANIFEST.md` in the renders dir with:
- Render file checksums
- Generation timestamp + script version
- Standardized parameter set used
- This-PR-scope description + diff target commit

Master `master_pre_merge.sh` adds gate G11:

```bash
run_gate "G11_vision_check_render_set" \
  "test -d sims/phase4v3/<subsystem>/renders/ && \
   test -f sims/phase4v3/<subsystem>/renders/RENDER_SET_MANIFEST.md && \
   test -f sims/phase4v3/<subsystem>/renders/top.png && \
   test -f sims/phase4v3/<subsystem>/renders/bottom.png && \
   test -f sims/phase4v3/<subsystem>/renders/iso.png && \
   test -f sims/phase4v3/<subsystem>/renders/zone_zoom.png && \
   test -f sims/phase4v3/<subsystem>/renders/diff.png" true
```

G11 verifies render set is PRESENT. Master visually inspects content separately.

---

## 5. Master visual verdict template

When master posts PR review comment, includes:

```
## Vision Check Verdict

**Render set**: ✅ present (G11 PASS)

| Render | Inspection | Verdict |
|---|---|---|
| Top 2D | silk/labels/density/polarity scan | ✅ clean / ⚠️ note: <issue> / ❌ <issue> |
| Bottom 2D | same | ✅/⚠️/❌ |
| 3D iso | clearance/orientation/height | ✅/⚠️/❌ |
| Per-zone zoom | density/routing gestalt | ✅/⚠️/❌ |
| Diff overlay | scope match | ✅/⚠️/❌ |
| Thermal sim render | T_J distribution | ✅/⚠️/❌ |

**Overall vision check**: ✅ PASS / ❌ REJECT

**Findings (if any)**:
1. [render file] — [specific concern with annotated screenshot if needed]
```

ANY ❌ → REJECT PR + worker fixes + re-renders + re-review.

---

## 6. Sai-eye-catch promotion path

When master's vision check catches something scripts missed:
1. Document the catch in PR comment with annotated render
2. Save to `docs/SAI_EYE_CATCHES.md` (catalog) — assign new Sai-catch # (continuing from 14)
3. Worker codifies an audit gate (per `[[feedback-codify-not-patch]]`)
4. Add gate to `master_pre_merge.sh`
5. Update RULES_MANIFEST.md Sai-eye-catch table

This is the same loop as `[[feedback-sai-catches-are-samples]]` but applied to MASTER vision catches as well as Sai catches. Master eyes are a feedback source too.

---

## 7. Why this is robust (not theatre)

- **Mandatory** (G11 gate) — can't skip even on "trivial" PRs
- **Standardized** (deterministic render params) — comparable across PRs and over time
- **Cumulative** (cumulative sim renders show whole-board state, not just this PR's scope)
- **Scope-checked** (diff overlay catches silent moves)
- **Promotable** (visual catch → script gate, so the same defect class can't recur)
- **Sai-visible** (`/tmp/board-render/index.html` refreshed after every merge)
- **Multi-source** (master + Sai both review)

---

VISION_CHECK_METHODOLOGY_HASH = (placeholder; computed by `audit_routing_system.py --write` after lock)
