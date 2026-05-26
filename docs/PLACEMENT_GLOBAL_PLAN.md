# Placement Global Plan — eagle's-eye SSoT (2026-05-26)

**Per Sai 2026-05-26**: *"you also know gotta route it so need to leave space.. and also you gotta run sims.. so you have to do placement that way you get headroom to edit and also you placement clashes the least in physics.. and routing has to be done taking the entire boards routing in account or you'll put some part at the far end.. i mean its a bit iterative you gotta have a rough plan at least from eagle's eye view so on a micro level you can take decisions.. and also like try to keep things parametric — placement and routing — it will keep our life easy"*

Plus: *"make sure you actually apply this not keep it stale.. also like don't forget components going on the other side of the board gotta account that too.. and which components how their routing will be easier we will save space and physics will become easy"*

This document is the **eagle's-eye SSoT** that every micro-level placement decision references. Worker MUST consume `parametric_placement.py` (the executable form of this plan) when placing — no hardcoded coords. G_PP21 audit enforces this.

---

## 1. Why this exists

CH1 placement REDO triggered by 64 body-bbox overlaps. Root cause beyond the missing audit: placement was done **bottom-up** (each IC placed individually) without **top-down** routing-aware + physics-aware + headroom-aware planning. Result: components packed in densely (no routing channels), driver pin orientation arbitrary (whack-a-mole creepage), per-channel decisions made without seeing the global net flow (some traces go board-spanning).

This document forces top-down. Every parameter, layer assignment, routing channel reserve is here. Worker reads this BEFORE placing anything.

---

## 2. Board canvas — 100×100mm, 8-layer

```
Layer stack (top to bottom):
  F.Cu                          ← Access floor (top)
  In1.Cu  GND                   ← Return reference plane
  In2.Cu  signal                ← BEMF + analog signals
  In3.Cu  +VMOTOR (3oz heavy)   ← 280A power plane
  In4.Cu  signal                ← Digital signals
  In5.Cu  GND                   ← Return reference plane
  In6.Cu  signal                ← Reserved (BEC / aux)
  B.Cu                          ← Filter + indicator floor (bottom)
```

**Layer-as-functional-floor (per BILATERAL_PLACEMENT.md):**
- **F.Cu** = Access + Power-source floor. Cables in. Probes land here. Polarized hand-solder readable. HS-FETs (drains carrying current INTO board).
- **B.Cu** = Return + Filter + Indicator floor. LS-FETs (sources, GND return). Bulk caps (under FET clusters for ultra-short loop). BEC bucks (centre, away from Hall). Status LEDs visible from underneath.

---

## 3. Eagle's-eye zone plan (BOTH layers)

```
        x=0          35          50          65         100
y=0    ┌────────────┬───────────┬───────────┬────────────┐
       │      S6  (J14 FC at 50,5  ·  J12 AUX at 75,5)   │  y=0-14
       │      ── TLM/AUX bus strip y=11.5-13.5 ──        │
y=14   ╞════════════╪═══════════╤═══════════╪════════════╡  ← CH boundary
       │            │           │           │            │
       │   CH4     │   S5N    │   S5N      │   CH3     │
       │ (NW, F+B)  │ x=35-40 │ x=60-65    │(NE, F+B)   │  y=14-50
       │  CH4-side  │ CH4 feed│ CH3 feed   │ mirror_X   │       (NEW
       │            │           │           │            │   north
y=50   ├────────────┼─── S3 supervisor y=18-40 ───┼─────┤    strip)
       │            │  (Hall ACS770 + TPS3700)    │     │
       │            ├──────── S2 bulk y=40-60 ───┤     │
       │            │  4× 150uF polymer (B.Cu)    │     │
       │   CH1     │   S5E   │   S5W      │   CH2     │
       │ (SW, F+B)  │ x=35-40 │ x=60-65    │(SE, F+B)   │  y=50-86
       │ template   │ CH1 feed│ CH2 feed   │ mirror_X   │
y=86   ╞════════════╪═══════════╪═══════════╪════════════╡  ← CH boundary
       │       S1   (BAT_P 45,95  ·  BAT_N 55,95)        │  y=86-100
       │  H1 (5,95)                              H2 (95,95)
y=100  └─────────────────────────────────────────────────┘
```

**4-corner mount holes only** (H1-H4 at 90mm pitch). H5-H8 cinematic removed per Sai PR #137 — caused TP/highway conflicts.

---

## 4. Sub-zone strategy within each CHn (the lesson from PR #137-139)

Each CHn zone (35×36mm) splits into 3 lanes:

```
   x: 0    8.4   15        22          28         35
      ┌────┬────┬─────────┬──────────┬───────────┐
      │ FET│ MTR│ ROUTING │ MOTOR    │ LOGIC     │
      │ col│ pad│ CHANNEL │ SUB-ZONE │ SUB-ZONE  │
      │    │    │ reserve │ (driver  │ (MCU,     │
      │ HS │TP19│ 1.5mm   │  MOTOR-  │  +3V3     │
      │ F.Cu    │  min    │  side    │  caps,    │
      │ LS │TP20│         │  pins)   │  ADC      │
      │ B.Cu    │ via stch│  J19,    │  dividers)│
      │    │TP21│         │  shunts  │  J18,U3,  │
      │ HS+│    │         │  J20-22, │  U4, INA  │
      │ LS │    │         │  D-clamps│  D-status │
      │ gate-R     1.5mm  │ HV       │  +3V3     │
      └────┴────┴─────────┴──────────┴───────────┘
        west FET column  | east MCU/DRV strip
```

Sub-zoning solves the PR #138 G_PP6 whack-a-mole: 27V SW-node pins live in MOTOR sub-zone, 3.3V logic in LOGIC sub-zone, with a 1.5mm routing-channel reserve between them. Audit G_PP19 verifies.

---

## 5. BILATERAL — per-layer placement on each CHn quadrant

| Component class | F.Cu | B.Cu | Why |
|---|---|---|---|
| HS-FET (drains, 27V source) | ✓ | | Top access for thermal + soldering visibility |
| LS-FET (sources, GND return) | | ✓ | Directly under HS-FET → ~50 SW-node vias, 1mm² loop |
| HS gate-R + bypass | ✓ | | Co-located with HS-FET pin |
| LS gate-R + bootstrap | | ✓ | Co-located with LS-FET gate (B.Cu) |
| Driver J19 + 0.1µF decoupling | ✓ (MOTOR sub-zone) | | Drives the HS-FET gates; must be ≤5mm from HS-FET (R23) |
| MCU J18 + 0.1µF decoupling | ✓ (LOGIC sub-zone) | | SWD + UART pads top-accessible |
| Shunts (J20/J21/J22) | ✓ (MOTOR sub-zone) | | Kelvin sense routing requires co-located INA on same layer (audit_kelvin_shunt_routing) |
| INA (U3, U4 op-amps) | ✓ (LOGIC sub-zone) | | Analog → ADC routed to MCU via inner-signal layer |
| BEMF voltage dividers (R-network) | ✓ (LOGIC sub-zone) | | Drives ADC; close to MCU pins |
| Status LEDs (D15, D19, D33) | | ✓ | Visible from underneath board during bring-up |
| LS-side gate-clamp diodes (D24-D36) | | ✓ ALONGSIDE LS-FETs | NOT ON TOP (the PR #139 catch); 2-3mm offset to LS-FET source pin |
| S2 bulk caps (4× 150µF) | | ✓ | Directly under FET clusters; 1mm² loop |
| S5 BEC bucks (5×) | | ✓ | ≥15mm from Hall (EMC); central area, away from FET switching |
| S6 connectors (J14, J12, J15-J17) | ✓ | | Cables enter top |
| BAT_P / BAT_N solder pads | ✓ | | External XT90 wire hand-soldered |

---

## 6. Routing-aware placement — high-current power flow

```
External XT90 ─┐
               ├─► BAT_P/BAT_N (50, 95 on F.Cu)
               ├─► NTC + TVS (S1)
               ├─► +BATT spine (x=48-52, vertical, In3 + F.Cu copper pour)
               ├─► Reverse-pol FETs + fuse (S3 supervisor zone)
               ├─► Hall ACS770 (current sense, y=22-26)
               ├─► +VMOTOR plane In3.Cu (3oz, 280A continuous)
               │
               ├─► S2 bulk caps 4× (B.Cu, under FET clusters)
               │   ├─► CH1 FET cluster (low-loop via cluster)
               │   ├─► CH2 FET cluster
               │   ├─► CH3 FET cluster
               │   └─► CH4 FET cluster
               │
               └─► Per-FET-cluster:
                   HS-FET drain (F.Cu) → SW-node (50 vias) → LS-FET drain (B.Cu)
                   LS-FET source (B.Cu GND return) → In1/In5 GND planes → S1 BAT_N
                   SW-node trace → 4mm copper → motor pad (TP19-TP21 for CH1)
```

**Implications for placement:**
- Bulk caps S2 must be at y=40-60 (between channels) so cap-to-FET radial vector is minimized for all 4
- HS-FET ↔ motor pad: 6.6mm offset (motor pad x=15, HS-FET x=8.4) — short SW node trace
- HS-FET ↔ LS-FET via cluster: directly under (0mm XY offset, just 3.6mm Y offset for collision-free pair)

---

## 7. Routing-aware placement — signal flow

```
J14 (FC connector, 50, 5)
  ├─► DShot_CH1 → internal layer In2 → MCU CH1 (LOGIC sub-zone, east strip CH1) → DRV CH1 → HS gates
  ├─► DShot_CH2 → mirror_X → MCU CH2
  ├─► DShot_CH3 → MCU CH3 (north channel)
  ├─► DShot_CH4 → MCU CH4
  ├─► UART TLM_CH1 → MCU CH1 USART
  ├─► (×4) TLM
  └─► KILL line → all 4 MCUs (multi-drop)

ADC (per channel):
  Shunt → INA op-amp (LOGIC sub-zone) → MCU ADC pin (LOGIC sub-zone)
    ↳ Routes via In2 or In4 (signal layers), distance ≤8mm
  BEMF divider (each phase) → MCU BEMF pin
    ↳ Same channel only; ≤5mm
  Hall current sense (S3) → all 4 MCUs (via S3→S2→CHn spine routing)
```

**Implications:**
- MCU pins for DShot/TLM should face TOWARD J14 (north) — so DShot trace is short
- MCU pins for ADC (BEMF + INA) should face TOWARD east-strip-MOTOR sub-zone — so analog traces are short
- This DICTATES MCU orientation: rotate J18 so logic-side pins face NORTH-EAST, ADC pins face WEST-SOUTH

---

## 8. Sim-driven placement loop

After parametric placement generates initial coords, sim-loop refines:

```
Loop per subsystem (CH1 example):
  1. Initial parametric coords → place
  2. Run analytical proxy sims (fast):
     - Loop area = HS-LS XY distance + via count → target ≤ 2 nH
     - Decoupling distance = each IC to nearest cap → target ≤ 3 mm
     - HPWL = sum of net half-perimeter wire lengths → minimize
  3. If proxy sims out of spec → adjust placement parameters
  4. After proxy converged → run FEM sim (Elmer thermal, openEMS EMI)
  5. If FEM sim out of spec → adjust + back to step 3
  6. After FEM converged → push placement PR
```

Implementation: `place_with_sim_loop.py` (worker-PR-B). For now (CH1 REDO): worker runs proxy sims manually + adjusts. FEM gate runs in master review.

---

## 9. Parameter set — the SSoT (every coord derives from these)

See `hardware/kicad/scripts/parametric_placement.py` for the executable form. The parameter file is the *editable* SSoT. Edit there → run engine → board updates → audits verify.

Categories (see code for details):
- BOARD (outline, layer stack, mount-hole pattern)
- MECHANICAL (motor pad pitch, fiducial spacing, edge keepout)
- ZONE GEOMETRY (channel zone xy, S1-S6 zones, S5 strips, sub-zone within CHn)
- BILATERAL (HS layer, LS layer, LS-Y-offset-from-HS)
- ROUTING RESERVE (channel widths, via keepouts, layer assignment by net role)
- PHYSICS (loop area target, decoupling distance, EMC isolation distances, thermal max temp)
- DENSITY BUDGET (component %, routing %, headroom %)

Change one parameter → propagates everywhere through engine → no manual recompute.

---

## 10. Going OUTWARD — items still open in this plan

| Item | Status |
|---|---|
| Routing channel reservation in `parametric_placement.py` | In this PR |
| Sim-driven placement loop | Methodology doc (this) + worker-PR-B implementation |
| Eagle's-eye visual render | In this PR (`/tmp/board-render/latest/global_plan.png`) |
| Per-net HPWL tracking during placement | worker-PR-B |
| 3D enclosure clearance audit | queued PR B (G_PP12-15) |
| EMC isolation matrix audit | queued PR C (G_PP17) |
| Thermal forbidden-pair audit | queued PR C (G_PP18) |

---

## 11. Going INWARD — how this plan stays alive

1. **Worker MUST USE parametric engine** — not hardcoded coords. G_PP21 audits worker placement scripts for hardcoded coords; FAILS if found.
2. **This doc and `parametric_placement.py` are paired SSoT** — any update to one requires update to the other in the same PR. G_D doc-sync verifies.
3. **Visual render auto-regenerates on every PR** — Sai sees deltas immediately.
4. **Sim-driven loop is required for every subsystem PR** at Phase 5 entry — sim-execution gate (R-sim-execution) verifies real sim output not just claimed.

---

## 12. How this slots into the existing framework (COMPLEMENTS, does not replace)

**Per Sai 2026-05-26**: *"make sure this is well thought off we dont leave our subsystem based approach and audit gates and all ... these other strategies will only complement them"*

This eagle's-eye + parametric layer is **additive**, not a replacement:

| Existing discipline | Status with this plan |
|---|---|
| Subsystem-based PRs (S1, S2, S3, S5, S6, CH1-CH4) | UNCHANGED — still the unit of placement work, dispatch, master review, merge |
| Per-subsystem placement scripts (`place_subsystem_ch1_v3.py`, etc.) | UNCHANGED in execution; CHANGED in INPUT — they consume `parametric_placement.py` output instead of hardcoded coord dicts |
| Lockfile YAMLs (`mechanical_anchors.yaml`) | UNCHANGED as SSoT for mechanical anchors; parametric engine REFLECTS lockfile values into IC anchors |
| 61 BLOCKING audit gates (G1-G17, G_PP1-16, G_FoS, G_R, G_M1-15, G_S, G_D, G_Z, G_L, G_META) | UNCHANGED; new audits G_PP19-21 ADD to the suite |
| Park-then-bring-in placement (R27) | UNCHANGED; parametric engine produces the coords each "bring-in" step uses |
| Sim execution gate (4-point check) | UNCHANGED; sim-loop methodology FEEDS this gate with per-iteration sim results |
| Rules manifest + RULES_MANIFEST.md | UNCHANGED; this plan adds NEW R-rule "R28 parametric placement SSoT" |
| Master pre-merge gate (`master_pre_merge.sh`) | UNCHANGED orchestration; ADDS G_PP19-21 |
| Worker deviation disclosure rule | UNCHANGED; any parametric override worker applies MUST be flagged in PR per existing rule |
| Codify-not-patch + Sai-catches-are-samples | UNCHANGED; this PR codifies the placement methodology gap that 64-overlaps exposed |

**The complementarity model:**
1. Eagle's-eye plan (this doc) = HUMAN strategy SSoT
2. Parametric engine (`parametric_placement.py`) = EXECUTABLE form of strategy
3. Lockfile YAMLs = MECHANICAL FACTS the engine reads
4. Per-subsystem placement scripts = USE engine output to materialize the board
5. Audit suite (61 + 3 new) = VERIFIES every step
6. Subsystem PR cadence = WORKFLOW that ties it together

Pre-this-PR: placement was bottom-up, hardcoded, no routing reserve, no headroom budget, sim-after-place. Result: every Sai-catch was a new spot-fix that broke something else.

Post-this-PR: same subsystem PRs + same gates + same lockfile + ADDED top-down parametric strategy SSoT that feeds the subsystem scripts. Each micro decision references the eagle's-eye plan. Changes propagate automatically. Sim-loop catches physics conflicts before fab.

Per [[feedback-audit-coverage-not-count]]: this is dimension coverage, not gate-count theater.
Per [[feedback-codify-not-patch]]: methodology gap codified into engine + audits, not patched in next PR.
Per [[feedback-systemic-rule-enforcement]]: structural change (SSoT + engine), not procedural.
