# Phase 4-v3 Plan — Park-then-bring-in REDO with strong gates + sims

**Single source of truth.** Status as of 2026-05-25, post-Sai-directive lock.

Hash: PHASE4V3_PLAN_HASH = (TBD — set by `audit_routing_system.py --write` after methodology docs land)

---

## 0. Why this plan exists

Phase 4-v2 (PR #91–99) accumulated 100 audit_layout FAILs across 11 classes + 154 reserved-highway-pad collisions + 35 components in undefined zones. Root cause: started from inherited pre-v2 placement and re-placed only some subsystems → ghost components left in stale positions invisible to per-PR audit but visible to full-board audit.

Sai (2026-05-25) taught the **park-then-bring-in pattern** as the fix: empty board → all components parked off-board → each PR brings its subsystem onto board into declared zone. Saved as `[[feedback-park-then-bring-in-pattern]]` memory.

This plan implements that pattern with the methodology research Sai authorized.

---

## 1. Cited methodology sources

All decisions in this plan are grounded in:

- Henry Ott, *Electromagnetic Compatibility Engineering* (2009)
- Howard Johnson, *High-Speed Digital Design* (1993) + *High-Speed Signal Propagation* (2003)
- Eric Bogatin, *Signal and Power Integrity — Simplified* (3rd ed, 2018)
- Lee Ritchey, *Right the First Time* (2003) — anchor-first, topology-before-geometry
- Mark Montrose, *PCB Design for EMC Compliance* (2nd ed, 2004)
- Erickson, *Fundamentals of Power Electronics* (3rd ed, 2020)
- IPC-2152 (current-carrying capacity), IPC-2221 (general design), IPC-7351 (component placement spacing), IPC-A-610 (acceptability)
- TI SLUA868 — Layout for power MOSFET applications
- Infineon AN-203 — Bootstrap and gate-loop minimization
- ON Semi AND9067/D — BLDC ESC layout
- NXP AN13267 — Multi-channel motor driver layout

---

## 2. Subsystem order (researched, locked)

Per `feedback-incremental-sim-driven-placement` memory + Boehm risk-driven dev + Henry Ott "critical-first" rule + Lee Ritchey "constraint-anchor first":

Smoke-test on simplest first (validates process), then hardest (defines topology), then mirrors (cheap), then support (fits around channels).

| Stage | Subsystem(s) | Reason | Component count |
|---|---|---|---|
| 0 | S6 connectors (smoke-test only — 3 components: J11, J12, U_ESD) | Validate park+bring tooling on trivial case | 3 |
| 1 | Mechanical anchors (Tier 1) | XT30, FC header, mount holes, motor pads, test points, LEDs, fiducials — immovable foundation | ~30 |
| 2 | CH1 full cycle (Tier 2 cluster + Tier 3 template) | Hardest = defines power+thermal+EMI topology | ~81 |
| 3 | CH2 mirror_X(CH1) | Symmetry preserves work | ~81 |
| 4 | CH3 mirror_Y(CH2) | Symmetry | ~81 |
| 5 | CH4 mirror_X(CH3) | Symmetry | ~81 |
| 6 | S3 supervisor + Hall + central TL431 | Central spine, feeds 4 channels | ~12 |
| 7 | S5 BEC rails (east/west/south) | Around channels | ~20 |
| 8 | S1 battery input (rev-pol FETs, TVS, NTC, fuse) | Top edge between CH1/CH2 | ~15 |
| 9 | S2 bulk caps **[BLOCKED on Sai BOM call]** | Central pool, last because needs upstream decision | 4 |
| 10 | S6 completion (USBLC6 ESD + status LEDs) | Bottom edge, finishes | ~10 |

Total ~570 components placed across 10 stages (Stage 0 is throwaway / re-merged into Stage 10).

---

## 3. Per-stage cycle (incremental sim-driven)

Per `feedback-incremental-sim-driven-placement` + Sai 2026-05-25 verbatim confirmation:

For each stage's PR:
1. **Place** components per Placement Methodology (Tier 1–5)
2. **Sim placement** — thermal-local (Elmer), decoupling-impedance (scikit-rf), shunt-sense path (ngspice)
3. **Edit if sim FAIL** → re-place → re-sim (loop until PASS)
4. **Route** per Routing Methodology (Tier 1–6 within this subsystem's scope)
5. **Sim routed** — thermal-with-tracks, IR drop, S-params, EMI near-field (openEMS local)
6. **Edit if sim FAIL** → re-route → re-sim (loop until PASS)
7. **Cumulative sim** with all prior placed+routed subsystems — full-board thermal, ground bounce, BEMF crosstalk, EMI farfield
8. **Edit from cumulative** → re-place/re-route locally → re-sim (loop until PASS)

Each step is its own PR with master gate review. Estimated 30-35 small PRs total across all stages.

---

## 4. Methodology references (in this same docs/ dir)

- `PLACEMENT_METHODOLOGY.md` — 5-tier anchor-first placement, `bringSelected()` algorithm spec
- `ROUTING_METHODOLOGY.md` — 6-tier constraint-driven routing, per-net topology rules
- `SIM_METHODOLOGY.md` — per-tier sim list, sim execution gate (4-point evidence per R18)
- `PHASE4V3_LOCKFILES/mechanical_anchors.yaml` — Tier 1 lockfile (immovable mechanical positions)
- `PHASE4V3_LOCKFILES/routing_topology.yaml` — per-net + per-component role classification

These are the SSoT. All scripts read from these YAMLs; no hardcoded coords or rules in code.

---

## 5. Gates (added to RULES_MANIFEST.md as R27–R32)

Every stage's PR must pass:

| Gate | What | Script | Required for |
|---|---|---|---|
| G1 | mechanical anchors match lockfile (±0.01mm) | `audit_anchor_positions.py` | every PR Stage 1+ |
| G2 | zone contract (untouched=parked OR prior-merged) | `audit_zone_contract.py` (worker building) | every PR Stage 0+ |
| G3 | loop area per channel < 50mm² | `audit_loop_area.py` | every PR touching CHn |
| G4 | decoupling per IC ≤3mm same-layer, value-matched | `audit_decoupling.py` | every PR touching ICs |
| G5 | audit_layout_compliance.py 0 FAIL on master HEAD post-merge | existing | every PR |
| G6 | master_audit_invariants.py 5/5 PASS on master HEAD post-merge | existing | every PR |
| G7 | audit_routing.py 6/6 PASS for tier-N net classes routed in this PR | existing | every routing PR |
| G8 | sim execution proof per R18 (4-point evidence in PR doc) | manual + audit | every sim PR |
| G9 | per-tier sim PASS within threshold (defined in SIM_METHODOLOGY.md) | per-tier sim scripts | every routing/place PR |
| G10 | target.h md5 unchanged (firmware contract lock) | manual md5 | every PR |

Master runs `master_pre_merge.sh` on every PR review. No exceptions per `[[feedback-master-gate-checklist]]`.

---

## 6. Single source of truth (SSoT) discipline

Per `[[feedback-codify-not-patch]]` + Sai 2026-05-25 directive:

| Concept | SSoT location | Hash-locked? |
|---|---|---|
| Board outline + stackup | `setup_board.py` + `BOARD_INVARIANTS.md` | BOARD_INVARIANTS_HASH |
| Component net assignments | SKiDL netlist (`hardware/kicad/*.kicad_sch`) | git commit hash |
| Mechanical anchors (Tier 1 lockfile) | `docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml` | MECHANICAL_ANCHORS_HASH |
| Routing topology (per-net class) | `docs/PHASE4V3_LOCKFILES/routing_topology.yaml` | ROUTING_TOPOLOGY_HASH |
| Placement methodology | `docs/PLACEMENT_METHODOLOGY.md` | PLACEMENT_METHODOLOGY_HASH |
| Routing methodology | `docs/ROUTING_METHODOLOGY.md` | ROUTING_METHODOLOGY_HASH |
| Sim methodology | `docs/SIM_METHODOLOGY.md` | SIM_METHODOLOGY_HASH |
| Lessons | `docs/ROUTING_LESSONS.md` | ROUTING_LESSONS_HASH |
| Firmware contract | `firmware/AM32/Mcu/PCBAI_FPV4IN1_F421/target.h` | md5 7a4549d2…  |

Any change to a hash-locked doc requires PR title tag `[methodology-change]` or `[invariant-change]`. `audit_routing_system.py` enforces drift detection on every PR.

---

## 7. Sureshot > SOTA (Sai 2026-05-25)

Per `[[feedback-sureshot-over-sota]]` memory: pick proven + fully-audit-gatable over fancy + uncertain.

Applied to this plan:
- ✅ **Manual + constraint-driven placement** with mirror primitive (industry-standard, every step audit-gatable) — not simulated-annealing autoplacer
- ✅ **6-tier constraint-driven routing** with explicit `routing_topology.yaml` — not Freerouter (failed 4×) or ML-based net classification
- ✅ **Elmer FEM thermal** — not lumped-capacitance heuristic
- ✅ **ngspice with measured component models** — not analytical operating-point
- ✅ **openEMS near-field for EMI** — not handwave radiation estimate

---

## 8. Master + worker parallel work split

Per Sai 2026-05-25 "you can also work alongside worker":

| Lane | Owner | Files (zero overlap) |
|---|---|---|
| Methodology SSoT docs + gates | Master | `docs/PHASE4V3_PLAN.md`, `docs/PLACEMENT_METHODOLOGY.md`, `docs/ROUTING_METHODOLOGY.md`, `docs/SIM_METHODOLOGY.md`, `docs/PHASE4V3_LOCKFILES/*.yaml`, `docs/RULES_MANIFEST.md` (amend), `hardware/kicad/scripts/master_pre_merge.sh`, `audit_loop_area.py`, `audit_decoupling.py`, `audit_anchor_positions.py` |
| Place+bring infrastructure | Worker | `hardware/kicad/scripts/park_all_components.py`, `place_subsystem.py` revised (bringSelected API), `audit_zone_contract.py` |
| Per-subsystem PRs (Stage 0–10) | Worker (master gates) | per-stage placement/routing PRs |
| Independent sim cross-check | Master | rerun Elmer/ngspice/openEMS on each merged stage, post comparison |
| EMC pre-compliance + heatsink sourcing | Master in parallel | Phase 6/7 prep docs |

PR sequence: master's methodology PR (this branch `phase4v3-methodology-ssot`) merges FIRST → worker's REDO infra PR merges SECOND → stage PRs follow.

---

## 9. S2 BOM blocker (Sai-decision)

S2 bulk-cap electrolytic 10×14.3mm doesn't fit current 20×20mm S2 zone. Options:

(a) Switch to smaller polymer cap package (more parts, lower per-cap C, parallel for total C)
(b) Enlarge S2 zone (overlaps S3 supervisor zone — cascading impact)
(c) Move S2 bulk-cap bank to different zone (changes routing topology)
(d) Mix: smaller polymer caps + accept slightly different EMI profile

Decision needed before Stage 9 PR. Queued in `/tmp/sai-queue.md`.

---

## 10. Status

| Item | Status |
|---|---|
| Plan SSoT (this doc) | DRAFT (this PR) |
| Placement methodology | DRAFT (this PR) |
| Routing methodology | DRAFT (this PR) |
| Sim methodology | DRAFT (this PR) |
| Mechanical anchors lockfile | DRAFT (this PR) |
| Routing topology lockfile | DRAFT (this PR) |
| Rules R27–R32 in RULES_MANIFEST | DRAFT (this PR) |
| `master_pre_merge.sh` | DRAFT (this PR) |
| `audit_loop_area.py` | DRAFT (this PR) |
| `audit_decoupling.py` | DRAFT (this PR) |
| `audit_anchor_positions.py` | DRAFT (this PR) |
| `park_all_components.py` | Worker (parallel) |
| `place_subsystem.py` revised | Worker (parallel) |
| `audit_zone_contract.py` | Worker (parallel) |
| Stage 0 smoke-test PR | After both methodology + infra PRs merge |
| Stages 1–10 PRs | Sequential after Stage 0 |

---

PHASE4V3_PLAN_HASH = (placeholder; computed by `audit_routing_system.py --write` after lock)
