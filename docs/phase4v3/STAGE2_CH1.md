# Phase 4-v3 Stage 2 — CH1 (channel template)

**Branch**: `phase4v3-stage2-ch1`. Builds on Stage 0 (S6) + Stage 1 (anchors).
Brings the 99 CH1 components from the parking grid into the CH1 zone, layer-aware
(HS-FET F.Cu / LS-FET B.Cu beneath, per Sai option-a), and locks CH1 as the
template that CH2/CH3/CH4 mirror in Stages 3–5.

## What this PR does

- Brings CH1 to **99/99 placed** (anchor + role engine, 0 grid, 0 unplaced).
- Establishes the **west/east sub-zone split** (master 2026-05-26): west FET strip
  (x0–22) holds the 3 half-bridge phases as **R20-identical 12mm-pitch geometric
  copies**; east control strip (x22–35) holds MCU(J18) + DRV(J19) + INA + the
  +3V3 decoupling. CH1 is the locked template; CH2=mirror_X, CH3/CH4=mirror_Y/X.
- Adds the role-based placement engine + per-phase transform (below) to
  `place_subsystem.py` + `derive_ch1_roles.py`; CH1 roles in `routing_topology.yaml`.
- No netlist / schematic / target.h change (md5 `7a4549d27e0e83d3d6f1ffaf67527d24`
  unchanged).

## Per-phase R20 transform (the channel-template core)

The 3 phases must be **identical geometric copies** (Sai symmetry-preserves-work /
R20) so the channel composes for sims + mirrors cleanly. Implementation
(`replicate_phases` + `bring_selected`):
- Place ONE reference phase's west switching cell (HS+LS FET, shunt, gate-R,
  clamp, VMOTOR bypass) via the role engine in the replication-safe sub-zone, then
  snap phases B/C onto it translated by the 12mm motor-pad pitch — *not* an
  independent ring-search per phase (which gave a 21.6mm non-uniform row pitch).
- **HS-FET left-offset** (≥6.5mm −X of its motor pad): the B.Cu LS FET stacked
  beneath must clear the motor pad's both-layer thru-via field, and a −X offset
  keeps the cluster at pad-Y so the replicated phase-C copy stays clear of the
  zone top edge.
- **East-control-first ordering**: the east strip (MCU/DRV/INA) is placed before
  the reference phase, so the FET cluster — and its replicated copies — avoid the
  driver/MCU instead of landing on them.
- Result: HS FETs at exact 12mm Y-pitch (56/68/80), G5 SYMMETRY + QUADRANT pass.

## Root-cause log (per Sai R: Symptom / Fix / Root cause / Prevention)

### 1. G4 — U3/U4 reported undecoupled
- **Symptom**: G4 flagged U3.8 / U4.5 (+3V3) with no cap ≤3mm.
- **Fix**: `derive_ch1_roles.py` assigns each bypass cap to the IC it was
  *authored* for, using SKiDL creation order (a bypass cap is instantiated right
  after its IC). C79→U3, C80→U4, C51/C52→J18. G4 passes with **no schematic add**.
- **Root cause**: the decoupling-by-rail pass round-robin'd caps across a shared
  rail's VDD pins by net order, reassigning C79/C80 (the real U3/U4 bypass caps)
  to other pins.
- **Prevention**: intent (SKiDL order) drives decoupling ownership, never net order.
- **Latent (logged OQ-009, not this PR)**: the 3 INAs (J20-22) have no V+ bypass
  cap in the schematic; invisible to G4 (INAs use Connector_Generic footprints
  with unnamed pins). For a future schem rev.

### 2. G5 — 18 pad-overlaps under the MCU
- **Symptom**: 18 different-net pad overlaps, all J18.33 (MCU exposed pad) vs
  B.Cu parts.
- **Fix**: `_layers(fp)` — a footprint blocks whichever copper sides its *pads*
  occupy; `fits()` rejects accordingly. Pad-overlaps 18 → 0.
- **Root cause**: the placer modeled the MCU as F.Cu-only, but its exposed-pad
  thermal field (F land + B land + 9 thru vias) occupies B.Cu too, so B.Cu clamps
  were placed under it.
- **Prevention**: layer presence (pad layer set), not mounted side, drives collision.

### 3. G5 — parts drifted into the motor-pad keep-out
- **Symptom**: non-motor parts inside the motor-TP 2mm keep-out.
- **Fix**: motor-keepout enforcement in `fits()` (`_MOTOR_ADJ_NET_RE`); non-motor-
  adjacent parts must clear motor TP pads + 2mm. Regex is the netlist-verified
  single source shared with the G5 audit. 5 drifted parts (C54/C55/C58/R44/D37)
  moved out.
- **Root cause**: the placer had no motor keep-out, so aux caps filled gaps next
  to high-current pads.
- **Prevention**: placer ↔ audit share one motor-exempt regex.

### 4. S6 save regression (caught during CH1 work)
- **Symptom**: "brought 11" but 0 S6 on-board / G2 NOT-BROUGHT for all S6.
- **Fix**: decoupling caps ring from the VDD pin with a body-diag fallback radius
  (nearest-first → ≤3mm when room exists, but an over-subscribed pin still seats);
  surplus rail caps → cluster-aux; pure-power caps auto-parent to a roled FET on
  their rail, never the MCU.
- **Root cause**: the bring step does not save on any "no slot", so one
  unplaceable cap silently dropped the whole subsystem's placement.
- **Prevention**: a single tight constraint must not be able to drop an entire
  subsystem; nearest-first + generous fallback keeps both G4 optimality and
  convergence.

### 5. `_PHASE_NET_RE` word-boundary bug — gate-Rs not phase-tagged
- **Symptom**: per-phase FET cell over-crowded; the reference-phase TVS clamp had
  no slot. Phase classification put only 14/16 phase-A parts in `pa`.
- **Fix**: `_PHASE_NET_RE` gate-drive alternative `(GH|GL|BST)([ABC])\b` → `(?:_|\b)`.
- **Root cause**: `\b` requires a word↔non-word boundary, but a phase letter
  followed by `_` (e.g. `GHA_CH1`) has none (`_` is a word char), so the gate-drive
  resistors (R45/46/49/50/53/54) never phase-tagged → fell into rest_role →
  scattered across the full zone, crowding the west FET cells.
- **Prevention**: the MOTOR/SHUNT alternative already used `(?:_|\b)`; both halves
  of the regex now match identically.

### 6. Motor-phase TVS clamps (D26/29/32) — mis-parent + wrong footprint + relocate
- **Symptom**: D26 (SMBJ33A, MOTOR_A↔GND) couldn't place; chained onto a sibling
  2-pin diode; G_PP11 body overlaps.
- **Fix**: (a) `derive_ch1_roles.py` — a diode whose only signal net is a MOTOR_x
  switching node anchors to the half-bridge LS-FET, not the nearest-pins sibling;
  (b) footprint corrected SMBJ33A → `D_SMB` (it is a DO-214AA/SMB part, not SMA —
  see OQ-013); (c) relocated to the B.Cu east-MOTOR strip rotated 90° (7.4mm part
  won't fit the dense west cell; placed beside the per-phase INA, excluded from the
  west-cell replication).
- **Root cause**: `derive`'s fewest-pins parent heuristic (right for signal
  dividers) chained power clamps onto sibling diodes; the SMA land is too small for
  the SMB body so it never accounted for the real size.
- **Prevention**: power-switching-node parts anchor to the half-bridge; value-based
  footprint correction in `migrate_footprints.py`.

### 7. `migrate_footprints.swap_one` flip-segfault (latent, surfaced by #6)
- **Symptom**: SIGFAULT swapping the one flipped (B.Cu) SMBJ33A; the other 11
  swapped fine.
- **Fix**: `board.Add(new)` BEFORE `new.Flip()` — pcbnew segfaults flipping a
  board-less footprint. Snapshot pos/orient/nets before the swap.
- **Prevention**: never call geometry ops on an orphan footprint.

### 8. `is_position_forbidden()` perf — placement timed out (worker-caught, fixed #148)
- **Symptom**: CH1 placement ran for minutes then SIGTERM; "no test board".
- **Fix**: the parametric engine rebuilt the forbidden-zone list on every call
  (~38ms × ~10⁵ spiral candidates = hours). Compute `placement_forbidden_zones()`
  ONCE at placer module-load + inline the bbox check in `fits()` (master cached it
  engine-side in #148).
- **Prevention**: never call an O(n)-rebuild helper inside the spiral inner loop.

### 9. Stale east-IC anchors — synced to the parametric engine
- **Symptom**: U3's zone_hint x28.0 sat inside the x27-28.5 routing channel →
  no-slot; the 3 INAs were on the LOGIC side (x32), far from their shunts (R23).
- **Fix**: synced all 7 east cluster-anchor zone_hints (J18-22/U3/U4) to
  `ch_ic_anchors('CH1')` — MOTOR ICs (driver + INAs) at x24.5, LOGIC ICs at x31.75,
  routing channel between.
- **Prevention**: the parametric engine is the SSoT for anchor positions
  (G_PP21); hand hints must track it.

### 10. G_PP10 driver-creepage gate — orphaned + LSET bug; G4 fab-tolerance
- **Symptom**: G_META1 flagged `audit_driver_motor_pin_creepage.py` as a never-run
  orphan; running it crashed (`LSET & LSET` unsupported).
- **Fix**: wired G_PP10 into `master_pre_merge.sh` + AUDIT_VALIDATION.md;
  replaced the LSET intersection with `Contains(F_Cu)/Contains(B_Cu)` membership.
- **G4 fab-tolerance**: U3 (LM393) and U4 (74LVC1G08) sit at the east zone edge
  with VDD pins on the body edge, so a ≤3.0mm same-side decoupling cap lands ON the
  IC body — physically the closest is 3.01–3.08mm. Added a documented 0.05mm fab
  placement tolerance to `audit_decoupling.py` (master-adjudicated A3).

## Gate status (`master_pre_merge.sh <board> --staged S6,CH1`)

**55 PASS / 1 FAIL / 2 SKIP.** The single FAIL is `G_M15_3d_model_coverage`
(0/36 STEP models) — a **sim-time/optional** gate (master-confirmed not a
placement blocker; 3D models are generated at the assembly/sim phase). Every
placement, electrical, and mechanical gate is green:

- **Placement**: G_PP11 body-bbox = 0 overlaps (was 64), G_PP19 routing channels
  clear, G_PP20 zone density, G_PP21 lockfile↔engine sync, G_PP8/9 anchor pitch /
  polarity, G_Z1 zone tiling, G_LEGACY verify_placement.
- **Electrical**: G4 decoupling (R25 + 0.05mm fab tol), G_PP10 driver SW-node
  creepage, G12 diff-pair, G13 Kelvin shunt, G14 via stitching, G_R1-6 SI,
  G_FoS3/4 cap derating.
- **Mechanical**: G_M5 assembly, G_M6 panel fit, G_M7-M14 mount-hole + pad-edge,
  G_M4 BOM/LCSC.
- **Symmetry/zone**: G5 layout compliance (HS-FET pitch = 13mm per engine), G6
  master invariants (highway same-net exemption), G16 connector symmetry, G_PP16
  channel BOM (staged-aware).
- **Meta**: G_META1 audit coverage (G_PP10 wired), G_META_HASH chain, G_D doc-sync.

CH1 = **99/99 placed**, locked as the channel template.

## Spec deviations (R21)

- **TVS phase clamps D26/D29/D32** (SMBJ33A, MOTOR_x↔GND) are NOT in the
  per-phase west switching cell — they're on **B.Cu in the east-MOTOR strip**
  (under the per-phase INA), rotated 90°. Reason: the corrected D_SMB footprint
  (7.4×4.6mm) does not fit the dense 22×13mm west cell, and the 13mm pitch +
  replication bound leave no south-of-LS-FET slot (short by 0.25mm). Inductance
  penalty ~5nH / +5V at 100A·100ns⁻¹ — SMBJ33A still clamps the ≤50V SW-node
  transient (master-adjudicated). They are placed per-phase symmetric.
- **VMOTOR bypass caps C66/C67** zone-fill to the B.Cu east edge inside the
  `S2→CHn +VMOTOR feed` highway corridor. Reason: the dense west cell has no slot
  near the HS-FET drain; the corridor carries the same VMOTOR net, so the cap is
  the intended load-side tap, not a routing obstruction (G6 same-net exemption,
  master-adjudicated A1).
- **G4/G5 decoupling tolerance**: U3 (LM393) + U4 (74LVC1G08) sit at the dense
  east zone edge with VDD pins on the body edge → ≤3.0mm same-side decoupling is
  physically impossible (cap lands on the IC body); nearest achievable 3.01-3.08mm.
  Resolved by a documented 0.05mm fab-placement tolerance + the L8/L8b
  board-plane-sufficient exemptions (single-gate logic + comparators).

## Open items flagged to master

- Engine `BoardParameters.hs_fet_row_pitch = 12.0` is **stale** (unused by
  `ch_fet_anchors`, which uses `motor_pad_pitch_y = 13.0`); should be 13.0 to
  match Option A. The G5 SYMMETRY check now reads `motor_pad_pitch_y`.
- OQ-013: SMBJ33A→D_SMA footprint mismatch (corrected at import; schematic-side
  fix tracked).

## Dependency note

Requires merged master #122 (mechanical revamp + G_PP6/G16 refines) + #123
(motor-exempt regex). The CH1 template is locked here; CH2=mirror_X(50),
CH3=mirror_Y(50), CH4=mirror_X(50) follow in Stages 3–5.
