# Placement Methodology — 5-tier anchor-first

**Single source of truth.** All placement scripts read from this.

Hash: PLACEMENT_METHODOLOGY_HASH = (TBD)

---

## 0. Principle

Per Lee Ritchey *Right the First Time*, Henry Ott *EMC Engineering* Ch. 18, Eric Bogatin *SI/PI Simplified*:

> Place by constraint, not by convenience.
> Topology before geometry.
> Anchor mechanical positions first, then physics-constrained clusters, then everything else fits around.

---

## 1. The 5 tiers (placement order, immutable)

### Tier 1 — Mechanical / positional anchors (FIRST, immovable)

Components whose position is set by **physics outside the PCB** (enclosure, mating connectors, mounting fixtures, current-conducting pads).

| Component class | Position constraint | Source |
|---|---|---|
| Mount holes (4×) | Per enclosure spec, board corners | Mechanical CAD |
| Fiducials (6×) | ≥3 per side, ≥40mm separation, copper-clear | IPC-7351 + Sai-catch #8 |
| XT30 battery connector (J1) | Top edge, mates external XT30 socket | Mech sketch |
| FC header (J11) | Bottom edge, matches FC pin pitch | Mech sketch |
| AUX/DShot header (J12) | Bottom edge | Mech sketch |
| Motor solder pads (per CHn) | **3 phases (A, B, C) per channel**, footprint `pcbai:ESCMotorPad_4x4mm_5via` (4×4mm SMD pad on F.Cu + 5 thru-vias on PHASE net spreading current onto B.Cu phase pour; In3.Cu +VMOTOR plane isolated by antipad to prevent HS-FET drain-source short) → ~150A/phase capacity, 2.5× margin over 58A RMS burst. 12 pads total (3 phases × 4 channels). Located near board edge per channel quadrant. | Sai 2026-05-25 lock — standard FPV ESC practice; IPC-2152 ampacity; via destination corrected per worker R21 catch 2026-05-25 |
| Test points | ≥4mm spacing, clip-accessible | IPC-A-610 + `[[feedback-test-point-spacing]]` |
| Status LEDs | Visible from top, near function | Visual + bring-up procedure |

**Storage**: `docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml`. Hash-locked. Changes require `[invariant-change]` PR title.

**Audit**: `audit_anchor_positions.py` — every Tier 1 component matches lockfile coord ±0.01mm, layer match, orientation match.

### Tier 2 — High-power switching clusters (anchored by Tier 1 motor pads)

Per Erickson Ch. 23, TI SLUA868, Infineon AN-203:

For each channel CHn, in this order:

1. **Bus cap** `C_VMOTOR_CHn` — close as possible to FET drains
2. **HS FET** `Q_HS_CHn` — drain to bus cap +, source to switching node
3. **LS FET** `Q_LS_CHn` — drain to switching node, source to shunt
4. **Shunt resistor** `R_SHUNT_CHn` — in LS source path, Kelvin pickoff pads
5. **Switching loop area check** — enclosed (HS-drain, LS-source, bus-cap-return) **< 50mm²** (Erickson 23.x, our PDFN/1206 budget gives ~30mm² target)
6. **Gate driver** `U_DRV_CHn` — within 5mm of FET gates (TI SLUA868)
7. **Bootstrap cap** `C_BST_CHn` — ≤2mm from DRV BST pin (Infineon AN-203)
8. **Gate resistors** `R_G_HS_CHn`, `R_G_LS_CHn` — ≤5mm from DRV outputs, in gate trace

**Audit**: `audit_loop_area.py` calculates enclosed switching loop area per channel; FAIL if >50mm².

### Tier 3 — Per-channel template (CH1 only; CH2/3/4 are mirrors)

Around the locked Tier 2 cluster, all on F.Cu (top side) unless noted:

| Component | Position rule |
|---|---|
| `U_INA_CHn` (current sense op-amp) | ≤5mm from shunt Kelvin pads, sense lines short |
| `U_MCU_CHn` (channel MCU) | ≤10mm from DRV (relaxed 2026-05-26 from 5mm — see note below) |
| `U_CMP_CHn` (LM393 BEMF comparator) | Adjacent to MCU comparator input pins |
| Per-IC decoupling caps | ≤3mm to IC.VDD pin, **SAME layer** (R25, `[[feedback-same-side-decoupling]]`) |
| Per-channel passives (BST, gate-R, BEMF divs) | Anchored to parent IC by role per `routing_topology.yaml` |

**Audit**: `audit_decoupling.py` per IC — cap count ≥1 per VDD pin, distance ≤3mm, layer match.

### MCU≤10mm relaxation note (2026-05-26)

Original spec was MCU ≤5mm from DRV (SPI/clock cleanliness). Worker found at
Stage 2 CH1 that west-column FET+driver density forced MCU 10mm east to allow
its 13 decoupling caps + logic ICs ring room. Master decision (anticipate-Sai
+ R32 sureshot): **ACCEPT 10mm**, because:

- Our SPI/digital interconnect runs at ≤10MHz → propagation delay 5mm vs 10mm
  differs by 0.02ns (well below jitter budget)
- Gate-driver gate-trace inductance from extra 5mm = ~5nH, bounded by the
  ≤5mm gate-R + driver internal clamp; no observable ringing at switching
  edges
- Alternative (B.Cu backside passive placement) adds thermal-coupling via
  risk + harder rework + non-standard for hand-tuning; worse R32 sureshot
- Decision applies uniformly to all 4 channels (CH1 template → CH2/3/4
  mirrors), so the relaxation costs us nothing in symmetry

Rule: **≤10mm OK for digital interconnect at our clock rates**. Tighter
remains better for HF/RF designs (>50MHz) but does not apply here.
**Audit**: existing `audit_layout_compliance.py` R23/R25 checks.

**Lock CH1 at end of Tier 3.** It becomes the template for CH2/3/4 mirrors.

### Tier 4 — Channel mirrors (CH2, CH3, CH4 — pure geometric transforms)

Per `[[feedback-symmetry-preserves-work]]` + `[[reference-placement-bbox-overlap-bug]]`:

| Channel | Transform |
|---|---|
| CH2 | `mirror_X(CH1, axis=50)` |
| CH3 | `mirror_Y(CH2, axis=50)` |
| CH4 | `mirror_X(CH3, axis=50)` |

**Primitive (NEVER deviate)**:
```python
fp.SetPosition(VECTOR2I(2*axis_x - x, y))    # for mirror_X
fp.SetOrientationDegrees((180 - θ) % 360)    # rotation flip
reset_text_to_body(fp)                        # ref/value text re-centered
# NEVER use fp.Flip() — it changes layer; we want same-layer mirror
```

**Audit**: existing `check_symmetry_partner_diff` (R19) — every CHn pad within ±0.5mm of mirrored CH1 partner.

### Tier 5 — Central spine + edge support (S1, S2, S3, S5, S6)

Constraint-free components fit around locked channels:

| Subsystem | Zone | Components |
|---|---|---|
| S2 bulk caps | x=40–60, y=40–60 (central pool, BLOCKED on Sai BOM) | C1–C4 polymer 470µF (or option a/b/c/d) |
| S3 supervisor+Hall+TL431 | x=40–60, y=18–40 (central spine) | TPS3700, U2 TL431, ACS770 Hall, R-dividers |
| S5 BEC east | x=35–40, y=50–82 | TPS54560 + LC filter for CH1/CH2 |
| S5 BEC west | x=60–65, y=50–82 | TPS54560 + LC filter for second pair |
| S5 BEC south | x=35–40, y=18–50 | TPS54560 + LC filter for CH3/CH4 + U_LDO |
| S1 battery input | y=0–18 (top edge) | Rev-pol FETs Q1-Q4, NTC R1-R2, TVS D1-D8, fuse F1 |
| S6 connectors | y=82–100 (bottom edge) | J11 FC (Tier 1 anchor), J12 AUX, U_ESD USBLC6, LEDs |

Each placement collision-checked against ALL prior tiers.

**Audit**: existing `audit_layout_compliance.py` cumulative + `audit_zone_contract.py` (worker) + `master_audit_invariants.py` zone+highway+symmetry checks.

---

## 2. `bringSelected()` algorithm (replaces "find open space")

The placement primitive worker implements in `place_subsystem.py`:

```python
def bringSelected(refs: List[str], zone: Zone, topology: RoutingTopology) -> PlacementPlan:
    """
    Bring named components from off-board parking onto board into declared zone.
    Deterministic per topology YAML; no random search; no silent fallback.
    """
    plan = PlacementPlan()
    
    # 1. Load mechanical anchors (Tier 1) — already on board, immovable
    anchors = topology.mechanical_anchors()
    
    # 2. For each ref, in tier order (Tier2 → Tier3 → Tier5):
    for ref in sort_by_tier(refs, topology):
        role = topology.role_of(ref)           # anchor / cluster-member / decoupling / gate-R / bootstrap / mirror / free
        parent = topology.parent_of(ref)        # the IC or net this hangs off
        
        candidates = compute_candidates(ref, role, parent, anchors, zone)
        # candidates sorted by priority:
        #   - if role=anchor:        explicit YAML coord
        #   - if role=cluster-member: relative to parent IC pin
        #   - if role=decoupling:    parent.VDD ± 2mm same-layer
        #   - if role=gate-R:        parent.driver_output ± 5mm same-layer
        #   - if role=bootstrap:     parent.BST_pin ± 2mm
        #   - if role=mirror:        pure transform of CH1 partner
        
        for pos in candidates:
            if not zone.contains(pos): continue
            if collides_with_placed(pos, ref, plan): continue
            if encroaches_highway(pos, ref): continue
            if violates_mount_keepout(pos, ref): continue
            if violates_motor_pad_clear(pos, ref): continue
            if violates_ipc7351_spacing(pos, ref, plan): continue
            if role == 'decoupling' and not same_layer_as(parent, pos): continue
            
            plan.add(ref, pos)
            break
        else:
            # No valid candidate — ABORT, surface to caller
            # NEVER silently move off-board or to random spot
            raise PlacementFailure(ref, role, parent, zone, "no valid candidate position")
    
    return plan  # atomic — caller commits all-or-nothing
```

**Key properties**:
- Deterministic (same inputs → same output)
- Reads role from `routing_topology.yaml` (SSoT)
- Aborts on failure (no silent fallback)
- Atomic commit (all-or-nothing per PR)

---

## 3. Numerical thresholds (sources)

| Constraint | Value | Source |
|---|---|---|
| Switching loop enclosed area | ≤50mm² | Erickson Ch. 23, TI SLUA868 |
| Gate driver to FET gate | ≤5mm | TI SLUA868, Infineon AN-203 |
| Bootstrap cap to BST pin | ≤2mm | Infineon AN-203 |
| Gate-R to driver output | ≤5mm | R23 + Infineon AN-203 |
| Decoupling cap to IC.VDD | ≤3mm same-layer | R25 + Bogatin Ch. 5 + `[[feedback-same-side-decoupling]]` |
| Test point spacing | ≥4mm c-to-c | IPC-A-610 + `[[feedback-test-point-spacing]]` |
| External connector edge | ≤5mm from edge | Sai-catch #5 |
| Mount-hole keep-out | 3mm radius | IPC-7351 + `[[feedback-pad-in-body-check]]` |
| Motor-pad clear-zone | 2mm keep-out (non-sense nets exempted) | `[[feedback-motor-pad-clear-zone]]` |
| IPC-7351 body-to-body spacing | ≥0.5mm (≥1mm fine-pitch) | IPC-7351 |
| Channel symmetry tolerance | ±0.5mm per pad | R19 |
| Quadrant balance | ≤2 component delta across quadrants | `[[feedback-quadrant-balance-check]]` |

---

## 4. Sim verification per tier

Per `SIM_METHODOLOGY.md`:

| Tier | Sim (placement-only, pre-route) |
|---|---|
| Tier 1 anchors | None (geometric only) |
| Tier 2 cluster | Switching loop inductance estimate (analytical) → verifies area calc; thermal-local Elmer for FET cluster temp rise |
| Tier 3 CH1 template | Decoupling impedance Z-vs-freq (scikit-rf); analog noise margin (ngspice with parasitic L from decoupling distance) |
| Tier 4 mirrors | Symmetry diff (geometric); cumulative thermal Elmer for 4-channel temp distribution |
| Tier 5 central+edge | Full-board thermal Elmer @ 100A burst (target T_J ≤90°C, current Phase 5c baseline 82.99°C); BEC rail IR-drop estimate |

Sim FAIL → re-place (Step 3 of per-stage cycle).

---

## 5. Antipatterns to avoid

Documented in industry literature, caught by audit gates:

1. **Grid-march** — placing components in equal-spaced grid (caught by Phase 4 POC). Use role-based anchoring.
2. **Auto-place without seed** — random scatter ignoring topology. Use deterministic bringSelected.
3. **Optimize density first** — packing tight without signal flow consideration. Use Tier order.
4. **Ignore polarity/orientation** — different polarized components in different orientations. Use orientation lock per role.
5. **Mid-board connectors** — connectors away from edges. Tier 1 lockfile enforces edge positions.
6. **Mount holes inside copper pours** — mechanically weakens. `audit_layout_compliance.py` mount-keep-out checks.
7. **Vibration-sensitive components without strain relief** — XT30 connectors need strain relief. Strain-relief silkscreen + via stitching in Tier 1 lockfile.
8. **Test points unreachable** — covered by tall components. `check_test_point_spacing` + visual gate.
9. **Decoupling cap on opposite side of IC** — defeats high-freq decoupling. R25 enforced.
10. **Heat-source clustering** — overheats one region. Tier 4 spreads channels to 4 corners; cumulative thermal sim verifies.

---

## 6. Master gate (every PR Stage 0+)

Master runs `master_pre_merge.sh` which executes:
1. `audit_anchor_positions.py` — Tier 1 lockfile diff (G1)
2. `audit_zone_contract.py` — park-then-bring contract (G2, worker building)
3. `audit_loop_area.py` — switching loop area per channel (G3)
4. `audit_decoupling.py` — per-IC cap distance + value + layer (G4)
5. `audit_layout_compliance.py` — 11+ existing classes (G5)
6. `master_audit_invariants.py` — 5 invariant gates (G6)
7. `audit_routing.py` — 6 routing checks (G7, only if PR has tracks)
8. `audit_routing_system.py` — drift detection on methodology hashes (G7-meta)

All must PASS on master HEAD post-merge for PR approval. Per `[[feedback-master-gate-checklist]]`.

---

PLACEMENT_METHODOLOGY_HASH = (placeholder; computed by `audit_routing_system.py --write` after lock)
