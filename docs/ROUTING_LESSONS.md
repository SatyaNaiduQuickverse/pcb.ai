# Routing Lessons Database (versioned)

**Per**: Sai 2026-05-24 — "make a system as you learn from mistakes... solve problems from the root not the symptom... system which learns and grows".

**Format**: lessons are observation-pattern + cost adjustment, NOT rules. Router uses them as soft penalties in the cost function, not hard blocks (except where the failure is categorical — e.g., L1 external router).

**Drift lock**: any update to this file requires PR tagged `[lesson-update]`. Hash at bottom.

---

## Lessons (status: proposed | active | retired)

### L1 — External autorouter doesn't model our constraints

- **Date**: 2026-05-23
- **Pattern**: invoking Freerouter / Topor / any external black-box autorouter
- **Observation**: 4× Freerouter v2.2.4 + v2.2.3 attempts, all failed identically (~16s exit, no progress logs)
- **Root cause** (physics): external tools don't model our 8-layer multi-rail planes, tight DRC, subsystem boundaries, or 2-fold symmetry constraint — they explore an impossible solution space
- **Cost adjustment**: hard block (`constraint_engine.assert_no_external_router`)
- **Status**: active
- **Sim cross-check**: N/A (tool didn't run)

### L2 — Mirror copies don't perfectly land on partner pads

- **Date**: 2026-05-24
- **Pattern**: routing template subsystem (CH1) → mirror copy to partner (CH2/3/4) → 1-5mm pad offset
- **Observation**: PR #77 BEMF length spread 50-93% because aggressive router added bridge tracks only on CH2/3/4, breaking symmetric trace count
- **Root cause** (physics): R19 5mm placement tolerance means mirror copy ends 1-5mm away from actual partner pad. Bridges close the gap but break symmetry. Real fix is structural: mirror-snap failures surface back to template re-route.
- **Cost adjustment**: on snap failure (>R19 tolerance), `route_mirror.py` REPORTS failure to template router — no bridge insertion
- **Status**: active
- **Sim cross-check**: 333 ps delay was within commutation budget (worker math sound), BUT crosstalk + EMI consequences not fully modeled — so we lock symmetry structurally

### L3 — Net-class width must be checked at INSERT time

- **Date**: 2026-05-24
- **Pattern**: routing a power-class net (+BATT, +VMOTOR) at signal-class width (0.15mm) on a non-plane layer
- **Observation**: PR #77 v2 had 16 +BATT tracks at 0.15mm including two 87.5mm full-board mains; would vaporize at 280A first power-up
- **Root cause** (physics): IPC-2152 ampacity formula → 0.15mm × 3oz Cu carries ~2.5A; +BATT at 280A needs ≥10mm trace OR plane connection. Audit caught it AFTER worker had submitted PR.
- **Cost adjustment**: `routing_primitives.place_track` HARD FAILS if `width < physics.min_track_width(net.expected_current, layer.cu_oz, dT_budget)`
- **Status**: active
- **Sim cross-check**: trivial — vaporization is binary

### L4 — Plane-pad vias get absorbed by ZONE_FILLER

- **Date**: 2026-05-24
- **Pattern**: placing a via directly on a pad that connects to a power plane
- **Observation**: Phase A routing pass — vias on +VMOTOR FET pads "disappeared" after `pcbnew.ZONE_FILLER.Fill()` rebuild
- **Root cause** (physics): KiCad's zone filler merges via copper into pad-flood polygon, then removes "redundant" via — the connection appears continuous to the netlist but vanishes from the gerber. Physically: via copper IS the pad pour; visually + electrically OK; but later operations (zone refill, DRC) treat the via as redundant and may remove it.
- **Cost adjustment**: for power-net pads, `routing_primitives.place_offset_via_with_stub` mandatory: via ≥0.5mm from pad center + stub trace to pad. Implemented as a structural pattern in `place_via` for power nets.
- **Status**: active
- **Sim cross-check**: gerber inspection confirmed via persistence with stub pattern

### L5 — Subsystem-zone constraint must be pre-route, not post-route audit

- **Date**: 2026-05-24
- **Pattern**: routing crosses subsystem zone boundary without being in highway corridor
- **Observation**: PR #77 had 8 SUBSYSTEM-ZONE violations on +BATT / BUS_CURR_HALL_OUT / LED_PG_NODE found by post-route audit
- **Root cause** (physics): route planner had no zone-awareness; it chose shortest geometric path. Audit was reactive, not proactive.
- **Cost adjustment**: `constraint_engine.cost_at(x, y, layer, context)` returns `+∞` for grid cells outside the routing net's allowed zones (subsystem zone OR declared highway corridor for inter-subsystem nets). CBS router naturally avoids.
- **Status**: active
- **Sim cross-check**: post-route audit becomes pre-route avoidance

### L9 — Mirror partner lookup needs dual-strategy match

- **Date**: 2026-05-24
- **Pattern**: subsystem mirror script (CH2 = mirror_X(CH1)) using single-strategy partner match
- **Observation**: Phase 4-v2 Step 2 PR-CH2 — net-signature-only match produced false positives (D39 matched TP19 because both had only MOTOR_A_CH1 after stripping anonymous N$ nets); position-only match would risk wrong-prefix matches (e.g., a CH1 R near where a CH2 D should mirror).
- **Root cause** (physics-equivalent): mirror partner identity is a constraint over (net-equivalence, ref-prefix, mirror-position) — any single dimension is ambiguous. Pure net-match fails on shared anonymous nets; pure ref-prefix is ambiguous (R56/R60 same prefix); pure position-match risks finding any unrelated nearby component.
- **Cost adjustment** (codified in `place_subsystem_ch2_mirror.py`): 3-tier match cascade:
  1. **IC partner ref-list** (hardcoded Q5→Q11, J18→J28, U3→U5 etc.)
  2. **EXACT net-set match** (after stripping `N\$` anonymous nets) + **same ref-prefix letter** — strict, no false positives from fuzzy fragments
  3. **Geometric-position fallback**: find CH1 fp of same ref-prefix letter at expected mirror_X(CH2.current_xy) within 2mm
  Components failing all three → genuine asymmetric component → surface to Sai-queue (don't mirror, flag in PR doc).
- **Status**: proposed
- **Sim cross-check**: pending — PR #92 will validate via 0 CH1↔CH2 violations + low CH2-internal collision count

### L8 — Comparator-class ICs exempt from local decoupling cap

- **Date**: 2026-05-24
- **Pattern**: low-speed analog comparators (LM393/LM339/LM319/LM193/LM2901/LM2903/TL3221/TLV3201/TLV3202/MCP6541) flagged by R25 audit for missing local 100nF, but don't physically require one
- **Observation**: Phase 4-v2 Step 2 PR-CH1 — U3 LM393 had no shared-net +3V3 cap in CH1; geometric fixup couldn't fit inside SOIC-8 silk + 3mm radius window; investigation showed no CH1 decoupling cap exists in schematic for U3
- **Root cause** (physics): comparators switch ~5mA at <100kHz. Board-level +3V3 plane decoupling (S5 BEC caps) presents supply impedance ~1Ω at 100kHz → V_noise ~5mV → after comparator PSRR -30dB → 150µV output ripple << 10-50mV typical hysteresis. False trigger probability negligible. Local 100nF benefits high-speed digital (MCU/DRV gate-drive) and op-amps with GHz GBW, NOT comparators with kHz response.
- **Cost adjustment**: `audit_layout_compliance.check_decoupling` EXEMPTS ICs matching `COMPARATOR_VALUE_RE` from the "C within 3mm" rule. Surfaces as `DECOUPLING-L8-COMPARATOR-EXEMPT` warn count for visibility.
- **Status**: proposed
- **Sim cross-check**: pending — supply impedance + PSRR math per IR2110/LM393 datasheets

### L6 — Test-point keep-out is layer-agnostic (probe access in XY)

- **Date**: 2026-05-24
- **Pattern**: placement scripts filter keepout by layer (F.Cu test point ignores B.Cu components and vice versa); but `audit_layout_compliance.MOTOR-PAD-CLEAR` evaluates keepout in XY only.
- **Observation**: Phase 4-v2 Step 2 PR-CH1 v3.1 — R69 placed at (16.32, 72.64) on B.Cu near TP21 at (14.23, 75.37) on F.Cu. `position_valid` skipped the keepout because `tl != test_layer`; audit flagged it.
- **Root cause** (physics): a B.Cu component sticks UP into the test-probe envelope of an F.Cu pad (and vice versa). Component height + body extent invades the probe-finger swing volume regardless of which copper layer the pad lives on. The audit captures this: probe access is a 3D mechanical constraint approximated as 2D XY keepout, NOT a per-layer copper constraint.
- **Cost adjustment**: placement scripts MUST enforce TP keepout (TP pad bbox + 2 mm) in XY for any non-sense-net component, regardless of layer. `constraint_engine.cost_at` should treat motor-TP zones as 3D keepouts (cost `+∞` for top + bottom layers within the XY zone). Same rule for any future user-probed test point (BEMF taps, IH/IL sense taps, gate-drive scope points).
- **Status**: proposed
- **Sim cross-check**: pending master review

### L10 — 24/30 plateau = missing GLOBAL routing phase (greedy detailed-only paints into corners)

- **Date**: 2026-05-28
- **Pattern**: routing a dense subsystem with a detailed-only router (greedy MST + per-edge A* / cooperative PathFinder, `route_subsystem_cooperative.py` v1→v8) and NO global capacity-planning phase
- **Observation**: CH1 signal routing plateaued at **24/30** on 10L, robust across 4 router configurations (`--no-rip-routed` / full cooperative ripup 97-rips-45-iters / single-net isolation / moved-placement). Early nets consumed the shared J18/J19 escape-via room; nets ~25–30 had no escape that does not short neighbors.
- **Root cause** (physics + algorithm): the canonical VLSI flow is GLOBAL routing (assign nets to capacity-limited regions, detect overflow cheaply) → DETAILED routing (exact tracks inside a region). Our router has ONLY the detailed phase, so it spends a shared scarce escape-via resource on whichever nets come first (fail_count+priority order = arbitrary w.r.t. resource contention). PathFinder negotiates *redistribution when slack exists* but cannot manufacture capacity that is absent — so it oscillates and plateaus. (Sherwani: maze routing is order-dependent and needs global pre-planning. DEEP_RESEARCH_2026-05-28 §1.2.)
- **Cost adjustment**: add the missing phases (ROUTING_METHODOLOGY §0b): Phase A capacity + escape pre-check (deterministic demand/supply ledger, verdict ROUTABLE/NEEDS-HDI/INFEASIBLE up front), Phase B global plan with doors + topology-before-geometry + via-slot pre-assignment, with FoS-on-routing-process (doors filled ≤75–80%, never 100%). Demote the cooperative router to the Phase-C region filler. Cost model: planner reserves escape slots for most-constrained nets first; overflow resolved at region level (microseconds) not by ripping copper.
- **Status**: proposed
- **Sim cross-check**: pending — validated against the T1–T9 ground-truth suite (esp. T3 greedy-trap + T4/T5 escape-feasibility boundary) per `docs/ROUTING_ENGINE_DESIGN_2026-05-28.md` before the engine touches the real board.

### L11 — Corner geometry is a LOCAL high-current concern, not a global rule

- **Date**: 2026-05-28
- **Pattern**: applying (or proposing) a board-wide chamfer/curve/rounding rule to "fix" 90° corners on signal traces
- **Observation**: the "90°-corner radiates / must be rounded" belief drives cosmetic global geometry rules that add complexity for no electrical benefit at our edge rates
- **Root cause** (physics): per Howard Johnson *HSDD*, the right-angle reflection/radiation effect is negligible above ~tens of ps rise times; our PWM/DShot/BEMF nets are sub-MHz to low-MHz, far below the threshold where a 90° corner matters electrically. The corner effects that DO matter are mechanical/manufacturing (acid-trap at acute angles; drill breakout + thermal-cycle crack at the trace-to-pad neck; current-crowding at ~100A motor-trace inside corners) — all LOCAL and targeted.
- **Cost adjustment** (ROUTING_METHODOLOGY §5b geometry policy): NO global chamfer/curve rule (rejected). DEFAULT octilinear (45°) — simplest manufacturable, never creates acute angles by construction. GATE: reject any interior angle <90° (acid-trap class). TEARDROPS at every pad/via junction (IPC-standard stress + current-crowding relief). LOCAL 45° chamfer/fillet on high-current corners ONLY, sim-driven (current-density flags crowding). Router + hand touch-ups call the same `geometry_primitives.py` library.
- **Status**: proposed
- **Sim cross-check**: pending — local fillet placement gated by current-density sim on motor-phase traces (Brooks *PCB Currents*); acute-angle gate is a deterministic geometric check.

### L12 — Factor of Safety EVERYWHERE / no cut-to-cut (Sai 2026-05-28)

- **Date**: 2026-05-28
- **Pattern**: sizing any routing quantity (trace width, clearance, via current, annular ring, impedance, loop-L, thermal, creepage, OR corridor/door fill) to its raw limit / fab minimum
- **Observation**: Sai mandate — "very important", "no cut-to-cut". The design target must never be the raw limit; routing to the exact fab minimum or filling a corridor to 100% leaves zero margin and is the cut-to-cut that produced the 24/30 corner-paint plateau (corridor filled to capacity → no slack for later nets or negotiation).
- **Root cause** (physics + process): every physical limit has process/measurement/registration variance. Sizing AT the limit means ~50% of parts violate after normal process drift. FoS converts a brittle point target into a robust band. The routing PROCESS itself needs a FoS (doors/corridors ≤75–80% fill) — overflow-at-capacity is a planning failure (ISPD-2008: any overflow is strictly inferior).
- **Cost adjustment** (ROUTING_METHODOLOGY §5c FoS table + `routing_topology.yaml` `factor_of_safety:` + `global_capacity_headroom:`): every physical quantity declares a FoS — limit÷FoS (ceilings) / requirement×FoS (floors). Aligns with implemented gates: ampacity 1.5× cont / 1.2× burst (G_FoS2), via current 1.5× (audit_via_current_capacity), thermal 25% cont / 10% burst (G_FoS1), cap voltage 1.4×/1.5× (G_FoS3), pin current 1.5× (G_FoS5), clearance above-fab-min, impedance ±10% band, routing-process fill ≤0.75–0.80. Planned FoS meta-gate: flag any physical quantity sized to raw limit (G_META1 analogue for safety) — described as planned, not yet scripted.
- **Status**: proposed
- **Sim cross-check**: thermal/ampacity FoS already gated by the implemented audit_fos_* suite; routing-process headroom validated by T3 (greedy-trap) in the T1–T9 suite where a 100%-fill plan fails and an ≤80%-fill plan succeeds.

---

## Lesson template for new entries

```
### L_N — One-line summary

- **Date**: YYYY-MM-DD
- **Pattern**: when does this trigger
- **Observation**: what happened
- **Root cause** (physics): the underlying mechanism
- **Cost adjustment**: how router accounts for it
- **Status**: proposed → active (after master review + sim cross-check)
- **Sim cross-check**: what validated the lesson
```

---

## Update protocol

1. Lesson observed (worker or master). Add row as `status: proposed`.
2. PR tagged `[lesson-proposed]`.
3. Master reviews root-cause + cost-adjustment design.
4. Sim cross-check executes (validated toolchain from Step 0).
5. If sim confirms pattern → status `active`. PR re-tagged `[lesson-update]`.
6. ROUTING_LESSONS_HASH recomputed + stored.
7. Router picks up new lesson on next run (versioned read).

A lesson can be `retired` if later evidence shows the pattern was a false positive OR the root cause was fixed elsewhere (e.g., placement redo eliminates the routing-symptom class).

---

## ROUTING_LESSONS_HASH

```
ROUTING_LESSONS_HASH = 4424015d88c739fdeaca5ec7e2113018d06efc69e7abd0ca7a62473858f99cfb
```
