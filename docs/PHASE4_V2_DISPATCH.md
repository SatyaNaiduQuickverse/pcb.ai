# Phase 4-v2 Dispatch — Incremental Sim-Driven Placement + Routing

**Issued**: 2026-05-24 by master per Sai mandate restructuring placement process.
**Driver**: Old process patched downstream symptoms (`PR #77` BEMF asymmetry was symptom of placement asymmetry). New process: place + route + sim per subsystem together, redesign-don't-patch, single source of truth, drift prevention.

## What's preserved
- All R1–R25 + 12 Sai-catches + audit_layout (16 gates) + audit_routing (6 checks) + audit_meta + RULES_MANIFEST + post_kinet2pcb_pipeline + codified fix scripts (12)
- Schematic / netlist / target.h md5 `7a4549d27e0e83d3d6f1ffaf67527d24` (firmware contract locked)
- 3D CAD STEP + renders pipeline (PR #76 merged)
- Thermal sim infra (re-validate per Step 0)
- 8-layer stackup (F.Cu / In1=GND / In2=signal / In3=VMOTOR / In4=signal / In5=GND / In6=signal / B.Cu)

## What's deprecated
- All current routing artifacts in `routing-final-v2-clean` and `via-stitching-v2` (PRs #77, #78 closed)
- Old Phase 4 placement (current `pcbai_fpv4in1.kicad_pcb` placement) — replaced by Phase 4-v2 zone-first flow

---

## Step 0 — Sim validation (BLOCKING gate before any other step)

**Goal**: prove each sim toolchain against published reference within 10% before trusting it as a gate.

Create `docs/SIM_VALIDATION.md` with rows for:

| Sim | Reference | Published value | Our result | Delta% | Status |
|---|---|---|---|---|---|
| Elmer thermal | IPC-2152 Fig 4-1 (1oz, 10mil trace, 1A, free air) | ΔT = X°C | ? | ? | pending |
| Elmer thermal | Elmer HeatControl tutorial (canonical) | published T_max | ? | ? | pending |
| openEMS | Microstrip 50Ω canonical (IEEE TEHM) | Z₀ = 50Ω | ? | ? | pending |
| openEMS | Via stitching attenuation @ 1GHz (published study) | -X dB | ? | ? | pending |
| ngspice | Gate driver shoot-through (datasheet curve) | published Q_rr | ? | ? | pending |
| ngspice | BEC ripple (TPS5430 datasheet bench data) | published V_pp | ? | ? | pending |

**Exit criteria**: every row Status=PASS with delta <10%. Master independently re-runs each validation.

**Deliverable PR**: `PR-phase4v2-step0-simvalidation`
- `docs/SIM_VALIDATION.md` populated
- `sims/validation/` subdirs with input + result file + extract script per `feedback-sim-execution-gate`
- Master runs validation cases independently before approval

---

## Step 1 — Zone planning on empty board (BLOCKING gate before component placement)

**Goal**: lock subsystem zones + I/O port positions + highway reservations BEFORE placing any component.

Create `docs/BOARD_INVARIANTS.md` as the new single source of truth:

```markdown
# Board Invariants (SSOT)

## Board geometry
- Outline: 100×100 mm
- Mount holes: M3 at (5,5), (95,5), (5,95), (95,95)
- target.h md5: 7a4549d27e0e83d3d6f1ffaf67527d24 (firmware contract)
- Stackup: 8-layer (F.Cu / In1=GND / In2=signal / In3=VMOTOR / In4=signal / In5=GND / In6=signal / B.Cu)

## Subsystem zones (locked)
| Subsystem | x_min | y_min | x_max | y_max | Reason |
|---|---|---|---|---|---|
| S1 battery input | 0 | 0 | 100 | 18 | top edge — XT30 ergonomics |
| S6 connectors | 0 | 82 | 100 | 100 | bottom edge — FC + AUX strain relief |
| CH1 (channel) | 0 | 18 | 50 | 50 | NW corner — motor terminal NW edge |
| CH2 | 50 | 18 | 100 | 50 | NE corner — motor terminal NE edge |
| CH3 | 50 | 50 | 100 | 82 | SE corner — motor terminal SE edge |
| CH4 | 0 | 50 | 50 | 82 | SW corner — motor terminal SW edge |
| S2 bulk caps | 35 | 40 | 65 | 60 | central — low-ESR to all 4 channels |
| S3 supervisor+Hall | 35 | 18 | 65 | 40 | central spine — current sense in battery path |
| S5 BEC | east+west bands inside channels | flexible |

(Coords above are PROPOSED — worker to refine with Step 1 PR; master Sai-approve before lock.)

## Symmetry pairs (locked, 2-fold mirror)
- CH1 ↔ CH2: mirror about x=50 (vertical centerline)
- CH3 ↔ CH4: mirror about x=50

## Subsystem I/O ports (locked at zone boundary)
| Subsystem | Port | Signals | Position | Reason |
|---|---|---|---|---|
| S1 → S3 | south boundary, x=50 | +BATT, BATGND | (50, 18) | central spine to bulk |
| S3 → S2 | south boundary, x=50 | +BATT, BATGND, BUS_CURR_HALL_OUT | (50, 40) | bulk caps decoupling |
| S2 → CH1 | west boundary | +VMOTOR, GND | (35, 50) | feed CH1 FETs |
| S2 → CH2 | east boundary | +VMOTOR, GND | (65, 50) | feed CH2 FETs |
| ... (etc per subsystem) |

## Highway reservations (corridors NO subsystem may place into)
| Highway | x_min | y_min | x_max | y_max | Reserved width | Reason |
|---|---|---|---|---|---|---|
| +BATT/GND spine | 48 | 0 | 52 | 50 | 4mm | 280A continuous power path top→center |
| BEMF return centerline | 47 | 50 | 53 | 82 | 6mm | 4 BEMF signals to central MCU |
| TLM/AUX bus | 0 | 80 | 100 | 82 | 2mm | inter-subsystem digital bus |
| ... |

## Invariant hash
sha256(zones + holes + outline + I/O + highways) = <computed>

Any PR that changes the hash WITHOUT explicit "invariant-change" PR title = REJECT.
```

**Visual deliverable for Step 1**:
- `docs/renders/zone-plan/`: empty board outline + zone boxes overlay (top, bottom, 3D)
- `docs/renders/zone-plan/io-port-overlay.png`: zone boxes + I/O port markers
- `docs/renders/zone-plan/highway-overlay.png`: zone boxes + reserved corridors

**Exit criteria**:
- BOARD_INVARIANTS.md authored, master Sai-reviewed
- Visual renders rendered + reviewed
- Master Sai-approval before any component placement

**Deliverable PR**: `PR-phase4v2-step1-zone-plan`

---

## Step 2 — Per-subsystem placement + routing + sim (in priority order)

Order (most-constrained first; later subsystems work around earlier ones):
1. CH1 (NW channel) — template; all other channels mirror this
2. CH2 (NE channel) — pure mirror of CH1 about x=50
3. S2 bulk caps (central) — low-ESR critical
4. S1 battery input (top edge) — high-current
5. S6 connectors (bottom edge) — mechanical
6. S3 supervisor + Hall (central spine) — current sense
7. S5 BECs (east+west bands) — flexible
8. CH3 (SE channel) — template for bottom pair
9. CH4 (SW channel) — pure mirror of CH3 about x=50

### For each subsystem PR

**Pre-placement**:
- Read BOARD_INVARIANTS.md zone + I/O contract for this subsystem
- Read all locked rules for this subsystem class
- If 2-fold mirror partner already merged: PURE mirror, no post-processing (this is the no-bridges discipline)

**Placement** (inside zone box):
- All components within zone bbox
- All locked audit gates GREEN: audit_meta + audit_layout (16) + all R-rules
- Visual zoom rendered (2400×2400)

**Routing** (within subsystem + to declared I/O ports):
- Internal routes complete (zero unconnected within subsystem boundary)
- I/O ports land at declared positions ±0.5mm
- Routes stay within zone (zero subsystem-zone violations)
- Track widths per net class (zero TRACK-WIDTH violations)
- Visual: zone-vs-actual overlay rendered

**Sims** (per-subsystem):
- Thermal (Elmer FEM with per-component breakdown — never aggregate-only)
- Signal integrity for any analog (BEMF, shunt, INA outputs)
- Decoupling verification (impedance plot for VDD rails)
- Result file + mtime + extract-script output per `feedback-sim-execution-gate`

**Cumulative sim** (subsystem N + all prior merged):
- Full-board thermal with all merged subsystems active
- EMC crosstalk between this subsystem and all prior
- Per-component breakdown report (per `reference-averaging-masks-local-failure`)

**Visual verification** (mandatory per Sai 2026-05-24):
- 8 per-subsystem zoom renders (2400×2400 each, top/bottom/iso/labels visible)
- Zone-vs-actual overlay
- If has mirror partner: symmetry-diff overlay (this subsystem over mirror partner)
- Cumulative full-board render

**Master gate per PR**:
1. git fetch + checkout branch
2. md5 target.h unchanged
3. audit_meta — all manifest functions present
4. audit_layout — 16 gates, read every line
5. audit_routing — 6 gates, read every line
6. **NEW**: `check_board_invariants` — invariant hash unchanged
7. **NEW**: `check_subsystem_zone_compliance` — all components within declared zone
8. **NEW**: `check_io_port_compliance` — I/O ports at declared positions ±0.5mm
9. **NEW**: `check_highway_reservation` — no components in reserved corridors
10. Per-subsystem sim results: file exists, mtime > input mtime, extract-script output sane
11. Cumulative sim results: same checks
12. Visual checklist run + zoomed per subsystem
13. If mirror partner: symmetry-diff visually checked
14. Master independently renders + reviews
15. If ANY fail: REJECT with specific finding. Worker REDESIGNS, not patches.

**No advancing to subsystem N+1 until subsystem N is master-merged.**

---

## Step 3 — Master process additions (drift prevention)

### `BOARD_INVARIANTS.md` enforcement
- All zone, I/O, highway changes require explicit "invariant-change" PR
- Worker computes invariant_hash + reports in every PR
- Master rejects any drift

### `audit_meta.py` extensions
- `check_board_invariants_hash()` — REJECT on drift
- `check_subsystem_zone_compliance(subsystem)` — REJECT on out-of-zone components
- `check_io_port_compliance(subsystem)` — REJECT on off-position I/O ports
- `check_highway_reservation()` — REJECT on highway encroachment
- `check_symmetry_partner_diff(subsystem)` — REJECT on mirror-partner deviation >tolerance

### Visual gate
- Every PR includes ≥10 renders: 8 zoom + 2 full board + 1 iso 3D
- Master independently re-renders
- Pixel diff against prior PR (highlight changes)

### Sim validation registry
- `docs/SIM_VALIDATION.md` SSOT for trusted sims
- No sim is gate-trusted until validation registry shows PASS
- Master independently re-runs validation cases

### Codify-not-patch enforcement
- Every fix PR must include: fix script + audit gate function + regression test (3 artifacts)
- audit_meta verifies all 3 exist

---

## Cost estimate
- Step 0 (sim validation): 1-2 days
- Step 1 (zone plan + invariants): 0.5-1 day
- Step 2 (9 subsystem PRs × ~4-8h each): 4-7 days
- Step 3 (cumulative sims + final highways): 1-2 days
- **Total: 7-12 days for properly-done board**

## Worker discipline reinforced
- **Redesign-don't-patch** per `feedback-redo-not-mitigate`
- **Codify, don't patch** per `feedback-codify-not-patch`
- **Symmetry preserves work** per `feedback-symmetry-preserves-work`
- **Root cause, not symptom** per `feedback-root-cause-not-symptom`
- **Worker deviation disclosure** per `feedback-worker-deviation-disclosure`
- **No silent in-PR adjustments**
- **Action ≥ narration** per `feedback-deliver-not-promise`

## Anti-pattern explicitly banned
- ❌ "aggressive router patches" after mirror copy
- ❌ "I'll fix this in Phase 8"
- ❌ "engineering acceptable" without per-component breakdown + Sai sign-off
- ❌ master autonomous decision on threshold relaxation (was misapplied per PR #77)
- ❌ trust worker audit summary without independent re-run
- ❌ shipping with known issues hoping bring-up fixes them
