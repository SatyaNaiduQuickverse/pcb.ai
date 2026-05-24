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
ROUTING_LESSONS_HASH = 4d8eea62304304de79d2c5d69f25674e1547fd7290239f812eb28af439e9b1f4
```
