# Routing Methodology — 6-tier constraint-driven

**Single source of truth.** All routing scripts read from this.

Hash: ROUTING_METHODOLOGY_HASH = (TBD)

---

## 0. Principle

Per Henry Ott *EMC Engineering*, Lee Ritchey *Right the First Time*, Eric Bogatin *SI/PI Simplified*, Howard Johnson *HSDD*:

> Routing is **PDN design** + **return-path control** + **per-class topology**.
> Find open space is the antipattern.
> Pick topology BEFORE drawing geometry; geometry implements topology.

Per `[[feedback-build-routing-system-not-freerouter]]` + `[[feedback-sureshot-over-sota]]`: this is a deterministic constraint-manager-style router, NOT Freerouter random search.

---

## 1. The 6 tiers (routing order, immutable)

Route every PR's nets in this strict tier order. Tier N+1 cannot start until Tier N audit + sim PASS.

### Tier 1 — PDN (Power Delivery Network) — *FIRST always*

Per Bogatin Ch. 7–10:

| Net | Strategy | Layer | Width |
|---|---|---|---|
| +VMOTOR | Plane + via grid stitching | In3.Cu (3oz copper, ampacity for 280A burst per IPC-2152) | plane |
| GND | Continuous plane (split only at clear analog/digital boundary if needed) | In1.Cu + In5.Cu | plane |
| +BATT trunk | Star from S1 (single source) | F.Cu over In1 GND reference | 2.5mm (40A continuous per IPC-2152) |
| +3V3 / +5V / +9V / +3V3A | Tree (per-rail trunk + stubs to loads) | In2.Cu / In4.Cu micro-planes or wide trunks | 1.5mm (10A typical) |

**Sim before Tier 2 starts**: DC IR drop (ngspice), AC PDN impedance Z-vs-freq (scikit-rf), thermal local for plane regions (Elmer).

### Tier 2 — Switching loops (per-channel local) — *physical, must be tight*

Per Erickson Ch. 23, TI SLUA868:

For each channel CHn:
- HS-FET drain → switching node → LS-FET source → shunt → GND return → bus cap → HS-FET drain
- Enclosed loop area < 50mm² (placement gate G3 already enforces; this verifies)
- Bootstrap loop: DRV BST pin → C_BST → SW node, ≤2mm
- Gate loop: DRV gate-out → R_G → MOSFET gate → MOSFET source → DRV gate-return, on same layer

**Sim**: switching transient ringing (ngspice with parasitic L extracted from layout); EMI near-field (openEMS local around switching cluster).

### Tier 3 — Decoupling — *R25 same-side, ≤3mm*

Per Bogatin Ch. 5:
- Each IC.VDD pin already has cap within 3mm same-layer (placement Tier 3 / G4 enforced)
- Router connects with shortest same-layer trace
- Via on cap pad to plane (if cap is connecting to plane via)

**Sim**: Z-vs-freq vs target (scikit-rf), self-resonance check.

### Tier 4 — Critical analog — *Kelvin + low-Z + matched*

Per Ralph Morrison *Grounding and Shielding*, Henry Ott Ch. 18:

| Net | Strategy |
|---|---|
| INA shunt sense (per CHn) | 4-wire Kelvin (not in current path); on layer adjacent to GND reference for noise shielding |
| BEMF refs (per phase, per CHn) | Differential pair, matched length ±0.5mm, on layer with clean GND ref |
| Hall ACS770 output | Single-ended analog, away from switching noise, shielded by GND on both sides |
| LM393 comparator inputs (per CHn) | Away from switching, short trace to MCU |

**Sim**: crosstalk to switching (openEMS); noise margin (ngspice with measured noise sources).

### Tier 5 — Signal highways — *controlled Z0 + length-matched*

Per Howard Johnson HSDD + Eric Bogatin SI:

| Net | Z0 | Length match | Layer | Topology |
|---|---|---|---|---|
| DShot_CHn (per channel) | 50Ω SE | per-CH match ±2mm | In2.Cu over In1 GND | Point-to-point S6 → CHn MCU |
| TLM_CHn (per channel) | 50Ω SE | per-CH match ±2mm | In2.Cu over In1 GND | Point-to-point CHn MCU → S6 |
| KILL_CHn (broadcast) | 50Ω SE | star preferred; daisy ok | In2.Cu | Star from S6 (or daisy CH1→CH2→CH3→CH4) |
| BUS_CURR_HALL_OUT | analog | — | In4.Cu over In5 GND | Star from S3 Hall → 4 CHn MCUs |

**Sim**: TDR for impedance discontinuity, eye diagram (ngspice transient with DShot edge rates), reflection coefficient at branches.

### Tier 6 — Bulk — *remaining signals*

| Net | Strategy |
|---|---|
| USB DP/DM (if used) | Differential pair 90Ω if reaches USB connector |
| Status LED control | Shortest manhattan, via minimization |
| Debug/SWD | Manhattan, length not critical |
| Pull-ups, BOOT0 | Standard signal |

**Sim**: DRC + visual only.

---

## 2. Per-net topology decisions (Ritchey "topology before geometry")

For each net class, topology chosen EXPLICITLY before drawing tracks. Stored in `docs/PHASE4V3_LOCKFILES/routing_topology.yaml`.

| Net class | Topology | Why |
|---|---|---|
| +VMOTOR | Plane + via grid | Lowest impedance, current spread |
| +BATT | Star from S1 | Single source, defined return |
| BEC rails (+3V3/+5V/+9V/+3V3A) | Tree (trunk + stubs) | Multiple loads, minimize voltage difference |
| GND | Continuous plane | Reference for all signals |
| DShot/TLM (per CHn) | Point-to-point | Single driver, single receiver |
| KILL | Star from S6 (preferred) | Lowest skew for safety-critical broadcast |
| BUS_CURR_HALL_OUT | Star (Hall → 4 MCUs) | One sensor, 4 readers |
| Shunt sense | Kelvin (4-wire) | Sense without IR-drop error |
| BEMF | Differential pair, matched | Common-mode rejection |
| Decoupling | Direct cap-to-VDD same-layer | Lowest ESL |
| Bulk signal | Manhattan shortest | Density-optimal |

---

## 3. Constraint per class (auto-enforced)

| Class | Width | Spacing | Z0 | Length match | Layer ref |
|---|---|---|---|---|---|
| +VMOTOR | plane | — | — | — | In3 3oz |
| +BATT | 2.5mm | 1mm | — | — | F.Cu over In1 GND |
| BEC trunks | 1.5mm | 0.5mm | — | — | In2/In4 |
| Decoupling | 0.5mm | 0.2mm | — | — | same as IC |
| DShot | 0.25mm | 0.25mm | 50Ω | per-CH match ±2mm | In2 over In1 GND |
| BEMF diff | 0.2mm | 0.15mm | 90Ω diff | matched ±0.5mm | In4 over In5 GND |
| Shunt sense | 0.25mm | 0.25mm | — | Kelvin | adjacent to current path on diff layer |
| Bulk signal | 0.25mm | 0.2mm | — | — | any signal layer |

These map to KiCad net classes; `audit_routing.py` enforces.

---

## 4. Symmetry preservation (per Tier 4 routing)

Per `[[feedback-symmetry-preserves-work]]`:

Route CH1 fully (Tiers 1–6), then mirror routes to CH2/3/4 via `route_mirror_ch1_to_ch234.py`:

```python
# Pure geometric transform on each track segment
for track in ch1_tracks:
    mirror_x = 2 * 50 - track.x
    mirror_y = track.y
    add_track_to_ch2(mirror_x, mirror_y, track.layer, track.width, track.net)
```

**Audit**: `audit_routing.py check_route_symmetry()` — per-channel track count + length spread ≤5%.

---

## 5. Antipatterns to avoid

Documented in Ott/Bogatin/Johnson, caught by audit gates:

1. **Find open space** (Freerouter style) — Use deterministic constraint-manager topology.
2. **Route across plane splits** — Return current jumps, EMI. Audit checks net stays over single reference plane.
3. **Signal over via field** — Impedance discontinuity. Audit checks via density along signal path.
4. **High-speed adjacent to switching** — Crosstalk. Spatial separation enforced by Tier order + layer assignment.
5. **Share return path digital/analog** — Ground bounce contaminates analog. Split GND only at clear boundary if needed (Ralph Morrison Ch. 4).
6. **Star ground with multi-MHz signal** — Inductive loop at center. Use plane for return below ~100kHz, controlled-impedance traces above.
7. **Right-angle traces at high speed** — Field discontinuity (minor effect at our edge rates but cosmetic discipline).
8. **Stub from main bus** — Reflection. For DShot/TLM use point-to-point or fly-by.
9. **Unbalanced differential pair** — Common-mode → radiation. Audit enforces length match + parallelism.
10. **Decoupling cap with long via stub** — ESL kills high-freq decoupling. Place cap pad with via-in-pad if needed.

---

## 6. Audit gates per tier (extends existing `audit_routing.py`)

| Tier | Audit |
|---|---|
| 1 PDN | `check_plane_continuity()` (existing PLANE-ISLAND), `check_via_stitching_density()` (new for In3 +VMOTOR), `check_ir_drop()` (sim-driven) |
| 2 switching loops | `audit_loop_area.py` (placement) + `check_switching_loop_routing()` (new — verifies track stays in declared loop region) |
| 3 decoupling | `audit_decoupling.py` (placement) + `check_decoupling_via_length()` (new) |
| 4 critical analog | `check_kelvin_shunt_routing()` (new), `check_diff_pair_match()` (existing R19-style) |
| 5 signal highways | `check_track_width()` (existing per-class), `check_length_match()` (new per-CH ±2mm), `check_z0()` (Hammerstad-Jensen, existing in physics_primitives) |
| 6 bulk | `check_track_width()` minimum |

All called by `master_pre_merge.sh` per `[[feedback-master-gate-checklist]]`.

---

## 7. Sim verification per tier (per SIM_METHODOLOGY.md)

| Tier | Sim |
|---|---|
| 1 PDN | DC IR drop (ngspice), AC Z (scikit-rf), thermal local for plane regions (Elmer) |
| 2 switching loops | Transient ringing (ngspice + extracted L), near-field EMI (openEMS local) |
| 3 decoupling | Z-vs-freq vs target (scikit-rf), self-resonance check |
| 4 analog | Crosstalk to switching (openEMS), noise margin (ngspice) |
| 5 signal | TDR for impedance discontinuity, eye diagram (ngspice), reflection coefficient |
| 6 bulk | DRC + visual |

Sim FAIL → re-route (Step 6 of per-stage cycle in PHASE4V3_PLAN.md).

---

## 8. Topology lockfile (`docs/PHASE4V3_LOCKFILES/routing_topology.yaml`)

Per-net classification + per-component role. Schema:

```yaml
nets:
  +VMOTOR:
    tier: 1
    class: power-plane
    topology: plane-via-grid
    layer: In3.Cu
    width: plane
    constraint: ampacity 280A burst per IPC-2152
  
  DShot_CH1:
    tier: 5
    class: signal-highway
    topology: point-to-point
    source: J11.pin_DSHOT_CH1
    sink: U_MCU_CH1.pin_PWM_IN
    z0: 50
    layer: In2.Cu
    ref_layer: In1.Cu
    length_match_group: dshot_ch1234
    length_match_tolerance: 2mm
  
  # ... etc per net

components:
  C_VMOTOR_CH1:
    tier: 2
    role: cluster-member
    parent: Q_HS_CH1
    relation: bus-cap
    max_distance_mm: 5
    same_layer_as_parent: true
  
  C_DECOUP_U_DRV_CH1_VDD:
    tier: 3
    role: decoupling
    parent: U_DRV_CH1
    parent_pin: VDD
    max_distance_mm: 3
    same_layer_as_parent: true   # R25 enforced
  
  # ... etc per component
```

This is the SSoT for both placement (parent + max_distance) AND routing (tier + topology + constraints). One file, two consumers, no drift.

---

## 9. Master gate (every routing PR)

Master runs `master_pre_merge.sh`:
1. Tiers verified in order (Tier N+1 not allowed if Tier N FAIL)
2. `audit_routing.py` 6 checks
3. Per-tier sim PASS within threshold (SIM_METHODOLOGY.md)
4. `audit_routing_system.py` drift detection on methodology hashes
5. `master_audit_invariants.py` board invariants
6. Symmetry diff for mirrored channels

All must PASS on master HEAD post-merge.

---

ROUTING_METHODOLOGY_HASH = (placeholder; computed by `audit_routing_system.py --write` after lock)
