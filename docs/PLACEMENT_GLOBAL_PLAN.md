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

## 8. Sim-driven placement + subsystem development flow (Sai 2026-05-26 lock)

Per Sai 2026-05-26: *"now we run physics sims.. iterate what seems off.. think in middle of each structurally.. then we do routing then sims again.. then we do next subsystem which won't be ch2/3/4 — it would be something that comes beside.. simulate the 2 adjacent subsystems together iterate.. when we get to ch2/3/4 you can use symmetry and copy.. make sure our entire plan is included in audits without skipping and with honesty"*.

### 7-step flow per subsystem (BLOCKING — enforced by G_FLOW1)

```
1. PLACE (parametric engine → bring_selected pipeline)
2. AUDIT placement-class (65+ gates → must be 55+/56)
3. PHYSICS SIM placement-only — Elmer thermal + openEMS EMI + ngspice PI + loop-L extract
   Per R-sim-execution (locked rule): result file + mtime > input + extract output + literal exec command
4. STRUCTURAL RETHINK if sim fails (not band-aid — re-place from step 1)
5. ROUTE (subsystem-only, eagle's-eye I/O ports honored, leave others for next PR)
6. AUDIT routing-class + RE-SIM with actual traces
7. PR + master review + merge
```

### Subsystem order — ADJACENT-FIRST (Sai 2026-05-26)

```
Stages 0-2: S6 + TIER1 + CH1 (✅ DONE post b612c5f)

Post-CH1:
  Stage 3 — S5 BEC east strip (directly east of CH1; feeds via S5→CH1 port)
  Stage 4 — S2 bulk caps (feeds CH1 via S2→CH1 port)
  Stage 5 — S3 supervisor+Hall (feeds S2)
  Stage 6 — S1 battery input (feeds S3) — full south power chain operational
  Stage 7 — CH2 = mirror_X(CH1) pure transform + route mirror
  Stage 8 — CH3 = mirror_Y(CH2)
  Stage 9 — CH4 = mirror_X(CH3)
  Stage 10 — final integrate + cumulative sim
```

Master may fast-track Stage 7-9 (CH2/3/4 immediate after CH1 routes) per Sai's explicit option if routing-mirror efficiency wins.

### Adjacent integration sim (BLOCKING — enforced by G_FLOW2)

Each subsystem PR after the first MUST include a sim that pairs the new subsystem with its already-placed neighbors per the table below:

| New | Paired-with | Sim purpose |
|---|---|---|
| S5 | CH1 | BEC switching ↔ MCU ADC noise, BEC thermal coupling to FETs |
| S2 | S5 + CH1 | Bulk cap ESL with FET commutation, thermal at FET cluster |
| S3 | S2 | Hall ADC response to bulk cap ripple, +BATT path thermal |
| S1 | S3 | TVS clamping, NTC thermal response, full power chain integrity |
| CH2 | CH1 | Cross-channel EMI (BEMF crosstalk, SW-node radiation) |
| CH3 | CH2 | Mirror_Y validation |
| CH4 | CH3 | Mirror_X validation + 4-channel cumulative |
| Stage 10 | ALL | Cumulative thermal at 4×100A burst, full EMI, full DRC |

### I/O port discipline (BLOCKING — enforced by G_FLOW3)

A subsystem PR may only ROUTE pins to its ALLOCATED I/O ports per the BOARD_INVARIANTS.md I/O ports table. Other pins are LEFT for next-subsystem PRs.

### Honesty markers (Sai-mandated, all BLOCKING)

- A subsystem PR that skips step 3 placement-only sim → BANNED
- A subsystem PR that claims step 7 without step 5+6 routing audit + post-route sim → BANNED
- A subsystem PR for adjacent subsystem N+1 without integration sim with N → BANNED
- All 3 enforced by G_FLOW1-3 + R-sim-execution.

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

## §8 STEP 4 ROUTE CH1 (DISPATCHED 2026-05-26)


### Stage 2 — CH1 STEP 4 ROUTE (DISPATCHED 2026-05-26)

**Status**: Worker confirmed pull of PR #162 (OQ-014 stackup lock @ 8813d28).
STEP 3 sims master-cross-validated (thermal 54.65°C PASS / PI 0.037mV PASS /
EMI CONDITIONAL OQ-016 / loop-L CONDITIONAL OQ-014 → 0.15nH plane-ref post-lock).

**Dispatch constraints (BINDING per rulebook)**:

1. **Subsystem-only routing** — CH1 nets ONLY. No global autoroute on adjacent
   zones. (Sai 2026-05-24 + R34 + [[feedback-build-routing-system-not-freerouter]].)
2. **Scoped Freerouter R34 OK** — for tangled inner-zone passive→IC nets if
   manual+rule-based router can't converge. Whole-board scope BANNED.
3. **Eagles-eye I/O ports** — CH1 connects to neighbors only at the I/O port
   coordinates allocated in BOARD_INVARIANTS.md §io_ports (gate-driver outputs,
   MOSFET SW node, BEMF sense, +VMOTOR, GND). Routes must terminate at port,
   not cross into S2/S5 zones.
4. **SW-node plane-referenced on In1.Cu GND** — per [[reference-dsn-plane-injection-vs-playbook-t1]]:
   SW conductor on F.Cu (HS drain) + B.Cu (LS via cluster) with In1.Cu GND
   plane reference at d=0.10mm. This achieves the L_loop ≤2nH target
   computed at 0.15nH (90× headroom) — OQ-014 closure.
5. **BEMF sense on In2 with In1.Cu between BEMF and F.Cu SW** — multi-layer
   shield per OQ-016. Routing must NOT escape In2 onto F.Cu/B.Cu in the BEMF
   path (would defeat shield).
6. **HS-LS commutation loop width ≥ 4.99mm** — per loop-L analytical: w=4.99mm
   minimum, area ≤27mm² per phase, 16 SW vias per phase (worker measured).
7. **High-current trace ampacity** — +VMOTOR & motor phases: per R17 burst
   spec (150A burst, 100A continuous). Use copper-pour fills + 35µm/70µm rules.
8. **Post-route audit gates** must pass before STEP 5 PR:
   - `audit_routing.py` (6 checks, already exists per Task #79)
   - `audit_sim_execution.py` (re-run loop-L extract on routed geometry +
     openEMS FDTD post-route — both will then yield REAL numbers, not
     CONDITIONAL placement-stage)
   - `audit_sim_result_sanity.py` (G_S3)
   - `extract_sim_verdicts.py` (STEP 6 binding: loop-L < 2nH measured,
     EMI BEMF ≤ -40dB measured)

**Tools allowed**: KiCad pcbnew Python API + Freerouter (scoped) + DSN
roundtrip per [[reference-dsn-plane-injection-vs-playbook-t1]] (plane injection
mandatory for VMOTOR/GND multi-rail).

**Acceptance gate**: STEP 4 PR must include (a) routed .kicad_pcb, (b) DRC
zero-errors report, (c) audit_routing.py PASS, (d) preliminary post-route
loop-L re-extract showing ≤2nH measured (not analytical), (e) topology
render (top/bottom/inner-layer overlay).

**Adjacent-next pairing**: After STEP 4 ROUTE CH1 + STEP 5 audit, the
adjacent-first queue advances to S5 BEC east strip (CH1 east edge ↔ S5
gate-driver supply path). S5 placement uses same 7-step flow.


### Stage 2 — CH1 STEP 4 ROUTE — addendum 2026-05-26 (worker-caught class lesson)

**NEW BINDING PRECONDITION for STEP 3 entry (retroactive)**: the .kicad_pcb
geometry under test MUST be committed to canonical
`hardware/kicad/pcbai_fpv4in1.kicad_pcb` BEFORE STEP 3 sims fire. Sims that
cite `/tmp/`, `~/Desktop`, `/home/<user>/local/*.kicad_pcb`, or
`escworker/local/*.kicad_pcb` produce unreproducible verdicts and are REJECTED.

**Class lesson**: worker discovered during CH1 STEP 4 pickup that the validated
CH1 placement existed ONLY in `/tmp/ch1_152.kicad_pcb` — committed canonical
board still had CH1 parked off-board (4041eed Stage-1 anchors). All 4 STEP 3
sims cited the volatile /tmp/ artifact; if /tmp had been cleaned (reboot,
tmpwatch cron), the verdicts would be unreproducible from SHA.

**Codified by**: `audit_sim_artifact_provenance.py` (R-sim-provenance, wired
into master_pre_merge.sh 2026-05-26). Distinguishes solver TOOL paths
(`ElmerSolver`, `openems` libs — exempt) from DATA artifact paths
(`/tmp/*.kicad_pcb`, `/tmp/*.sif` — REJECTED).

**STEP 3 sim entry checklist** (revised):
- [ ] Geometry committed to canonical board path (no /tmp/ artifact)
- [ ] Worker PR cites canonical-board SHA at top of sim RESULTS.md
- [ ] R-sim-provenance audit PASS
- [ ] R-sim-execution audit PASS (4-point proof)
- [ ] G_S3 sanity audit PASS

For CH1 STEP 7 PR (placement+route): worker MUST update the 5 known
`/tmp/ch1_152.kicad_pcb` references in `sims/phase4v3/ch1_emi/` +
`sims/phase4v3/ch1_loop_l/` to point at `hardware/kicad/pcbai_fpv4in1.kicad_pcb`
+ re-extract loop-L from the canonical board (must yield same 13.5578 nH
free-space; plane-referenced ~0.15 nH post-route).


### Stage 2 — CH1 STEP 4 ROUTE — addendum 2026-05-26 #2 (Pi-bounded operations)

**Class lesson** (worker-caught 2026-05-26 during Freerouter verification): `kicad-cli pcb drc` on full-board hung 107min CPU then OOM-killed on 15GB Pi. Plane zones × 573 footprints × clearance boolean intersections exceeds available RAM.

**Binding rule for Phase 4-v3 STEP 4-6**:

> Pi-bounded operations (DRC, full-board render, full-board route, full-board sim) MUST be **subsystem-scoped** during Phase 4-v3 placement+route. Full-board operations are **Phase 7 integration gates only** and require external x86 infrastructure (logged OQ-018).

**STEP 5 acceptance DRC** = CH1 nets only, via one of:
1. `pcbnew.RunDRC()` Python API with footprint/track pre-filter to CH1 nets (preferred — fastest, bounded memory)
2. Plane-clipped copy: extract CH1 zone bbox + 5mm port buffer, clip GND/VMOTOR planes to scope, run `kicad-cli pcb drc` on copy (cleanest PR artifact)
3. Pure-Python pairwise clearance check (slowest, fully bounded)

Worker picks fastest per context; STEP 5 PR artifact should be option 2 output (reproducible by any future auditor).

**See also**: OQ-018 (Phase 7 full-board DRC infrastructure decision), [[feedback-pi-bounded-subsystem-scope]].


### Stage 2 — CH1 STEP 4 ROUTE — addendum 2026-05-26 #3 (R19 scope clarification)

**Class lesson** (worker-caught 2026-05-26): R19 / OQ-017 pure-transform of per-phase ROUTING was geometrically infeasible at 13mm phase pitch — per-phase routing footprint spans ~15mm in y, so +13mm translation overlaps neighbor band by ~2mm (+273 real inter-phase clearance flags). Worker escalated rather than band-aiding ([[feedback-redo-not-mitigate]]).

**Master adjudication (OQ-019)**: R19 binding re-scoped — required is **commutation loop symmetry** (FET cluster + via cluster + GND-return-discipline = identical per-phase loop-L), NOT identical SW-trace polylines.

Physics: 3-phase BLDC is sequential (not paralleled phases) → no current-sharing concern. BEMF blanking tolerates per-phase switching delta. EMI compliance measured CUMULATIVELY at integrate stage. Trade-off: widening pitch 13→15mm costs 12% board area for sub-percent EMI/sim gain. Physics doesn't require it.

**Updated R19/OQ-017 binding for STEP 6 verification**:
- ✓ Measured loop-L per phase ≤2nH (geometric, from routed v6)
- ✓ A=B=C to 4 decimals AT FET-CLUSTER COMMUTATION LOOP (not at outward traces)
- ✗ Identical SW-trace polylines NOT required (re-scoped)

**CH2/3/4 implication**: cross-channel mirror symmetry (CH2 = mirror_X(CH1) etc) UNCHANGED. Per-phase intra-channel asymmetric routing is acceptable on each channel individually.


### Stage 2 — CH1 STEP 4 ROUTE — addendum 2026-05-26 #4 (pre-placement visual-decision gate)

**Sai-locked rule 2026-05-26** (after J18/J19 via-capacity escalation surfaced the need): BEFORE any placement shift to relieve routing density, master+worker MUST perform pre-decision visual verification:

1. **Zoom-render the problem area** — `kicad-cli pcb export svg --layers F.Cu,B.Cu` or `render_pr_visual.py --zone-zoom`, 300+ DPI
2. **Identify space available WITHIN designated subsystem zone** — never propose moves outside the zone per [[reference-board-invariants-zone-hard-edges]]
3. **Propose specific Δxy** — concrete numbers, not vague
4. **Mock up + screenshot the proposed state** — same DPI as before
5. **Visually verify the move actually helps**:
   - Corridor/escape ring widens?
   - Via-capacity-saturated pads have more escape room?
   - Gate-R distances still ≤5mm (R23 no-passive-island)?
   - Decoupling distances still ≤3mm (R25)?
   - Per-phase cluster pitch still uniform (G_PP22)?
   - No NEW collisions introduced?
6. **THEN commit** — codify in parametric_placement.py, re-verify all 58 gates, re-route

**Without visual verification**: placement changes can shift problem corridor to another (whack-a-mole), or fix one constraint while breaking another. Pre-decision visualization is cheap (minutes); post-commit re-route + re-audit + re-mirror is expensive (hours).

**Sai's broader principle**: "stay within designated area, take some space [inside the zone]" — use the zone's internal space, don't escape it.

Codified by: [[feedback-pre-placement-visual-decision]] (memory) + this §8 addendum.


### Stage 2 — CH1 STEP 4 ROUTE — addendum 2026-05-26 #5 (R20 move-the-obstacle, per-net targeted)

**Sai-locked rule 2026-05-26** (sourced from novapcb's hard-won lesson — routing-techniques Point 2 / their Rule 20 invented mid-session): when a passive component (resistor, capacitor, ferrite bead) blocks where a specific trace needs to go, **move that specific passive creatively to unblock that specific trace** — NOT generic envelope-edge shifts hoping to help multiple nets.

**Distinction from generic envelope-edge shift (worker's earlier failed pattern)**:

| Generic edge-shift (anti-pattern) | R20 targeted obstacle move |
|---|---|
| Pick candidate passives near "the area" | Identify SPECIFIC passive at SPECIFIC via-conflict location |
| Shift by generic Δ (e.g., -0.5mm in some direction) | Specific creative move: 180° flip, 90° rotation, specific-direction Δxy, zone-internal relocation |
| Hope it helps multiple nets | Targets ONE specific net's specific blockage |
| Effect: maybe 0.5mm room | Effect: directly unblocks the conflicted via |

**Apply this rule (per stuck net):**

1. Identify the EXACT pad/via location where the conflict occurs
2. Identify the EXACT passive component(s) blocking THAT specific via — not generic candidates
3. Check the passive's electrical envelope:
   - Decoupling cap → R25 ≤3mm to IC VDD pin
   - Kelvin sense R → R13 ≤5mm to FET shunt pad
   - G_PP22 cluster member → CANNOT move (uniformity locked)
   - Gate-R → R23 no-passive-island ≤5mm to FET gate
   - Other passives → mostly position-flexible
4. Propose the SPECIFIC creative move: rotation, flip, or directional Δxy that opens the SPECIFIC blocked path
5. Per addendum #4: render BEFORE/AFTER + visually verify the move helps + no new collisions
6. Apply ONLY on master+Sai approval per visual review

**novapcb's 6 worked examples (reference proof of the pattern)**:
- R45/R46 CAN termination: **180° flip** opened bus daisy
- SPI1_MOSI: **0.4mm specific-direction nudge** unblocked MOT1/2
- FB2 ferrite: **repositioned entirely** for CAN keystone
- U15 CAN ESD: **relocated** to open bus daisy
- R11/R12 I²C pull-ups: **moved** to unblock bus tangle
- IMU CS verticals: **repositioned** for HSE crystal work

**When R20 is the right path (vs J19-shift cascade or full GUI)**:
- Multiple stuck nets each with identifiable specific obstacle
- Obstacles are non-critical passives (not G_PP22 / not R25-tight / not R13-tight)
- Cascading reroute is uncertain
- Full GUI manual is expensive
- Worker has live geometry context to identify specifics

**Anti-patterns (banned)**:
- Generic "move R60 -0.5mm" without identifying it as the blocker for a specific net
- Moving G_PP22 cluster members (breaks symmetry)
- Moving R25/R13-critical passives past their electrical envelope
- Skipping the §8 #4 visual verification before commit

Codified by: [[feedback-move-the-obstacle-per-net-targeted]] (memory) + this §8 addendum #5. Reference source: http://100.81.21.121:8765/static/techniques.html (novapcb routing-techniques Point 2 / Rule 20).
