# Phase 5b routing — strategy options for Sai

**Status:** 2026-05-24, after ~6h of routing attempts on phase5b-routing-final
branch. Master + worker have exhausted in-scope manual + autoroute approaches.
Re-engaging Sai for tool/strategy adjudication with empirical data.

## What's locked at master

- **127 baseline tracks + 232 vias** from PR-CH1-route + PR-S1/S2/S3/S5/S6-route + PR-routing-final (partial) + PR-routing-rebuild — power path, channel motor-phase, mirror, VREF star, LED-stub-width fix.
- **PR #72** rules-compliance-system: 14 HARD audit gates, audit_meta.py integrity meta-fence, post_kinet2pcb_pipeline.py orchestrator, 11 codified fix scripts.
- **target.h md5** unchanged: `7a4549d27e0e83d3d6f1ffaf67527d24`.

## What's NOT locked

499 KiCad DRC unconnected items remain. Breakdown (after Phase A attempt):

| Category | Count | Notes |
|---|---|---|
| GND/BATGND/+VMOTOR (plane-net) | ~28 | Phase A reduced from 164 → 28 (Phase A pre-absorption) |
| +3V3/+3V3A/+V5_*/+V9_* (non-plane power) | ~163 | Need trace routing — no dedicated plane |
| MOTOR_X_CHn (FET-source-to-INA Kelvin) | ~100 | Channel-internal |
| CSA_X_OUT_CH/CSA_MAX_CH | ~32 | Channel-internal sense signals |
| BEMF/SHUNT/GH/GL gate-drive | ~50 | Channel-internal sense + gate |
| PWM/KILL/VREF/NTC | ~80 | Channel-internal control |
| Other | ~46 | Mix |

## What I tried — empirical results

### F1-F4: Freerouting v2.2.4 autoroute
4 attempts, all identical failure mode:

| # | Args | Duration | SES | Log progress |
|---|---|---|---|---|
| 1 | `-mp 3 -opt` | 51 min | none | init only |
| 2 | `-mp 3 -opt` (post-PR-#72 DSN) | 30 min | none | init only |
| 3 | `-mp 3 -opt` (post-PR-#72 + fiducials) | 30 min | none | init only |
| 4 | `-mp 1` (single-pass, unlocked baseline) | 16 sec | none | init only |

Java process burned CPU at 99% throughout but emitted no progress messages
after init. Process exited (timeout or self-terminate) without producing
SES file in any attempt. **Conclusion**: Freerouting v2.2.4 fundamentally
incompatible with this density / 8L stackup / 306-net board.

### F2: Manual route_signals_role_aware.py (1148 routes)
- 351 power-stub vias + 228 power-trace + 569 signal L-shape
- Result: DRC went from 1451 → 2460 violations (+1009 from collisions)
- Unconnected stayed at 499 (routes didn't satisfy KiCad's connectivity)
- Reverted.

### Phase A: route_power_plane_stitch.py with on-pad vias (351 added)
- ZONE_FILLER + save-reload-fill-save sequence worked
- Initial DRC showed GND unconnected 120 → 16 (-87%), +VMOTOR 26 → 0
- **BUT**: on subsequent ZONE_FILLER runs, the on-pad vias get ABSORBED
  (KiCad treats same-net via inside same-net zone-fill copper as redundant)
- Phase A "win" was actually fragile; subsequent operations would erase it.

### O1: Offset-via-with-stub-trace (373 added)
- Removed 396 Phase A on-pad vias, added 373 offset-via + stub pairs
- Vias DO persist after ZONE_FILLER (offset clears zone-fill region)
- BUT DRC unconnected stays at 499 — KiCad's pad-to-plane connectivity check
  isn't satisfied by offset-via-with-stub when plane zone-fill has tight
  pad-edge clearance
- NEW track-width violations from 0.3mm stub on 1.0mm VMOTOR/BATGND nets

## Identified KiCad-specific quirks (codified as memory)

- `[[reference-pcbnew-zone-filler-save-pattern]]` — save-reload-fill-save
  sequence (ZONE_FILLER.Fill segfaults headless without isolation).
- `[[reference-pcbnew-zone-filler-onpad-trap]]` — on-pad vias absorbed; use
  offset-via-with-stub at net-class width.

## Three forward paths

### P1 — Re-engage Topor decision

**Cost:** ~$300 (single-license), 1-day procurement
**Benefit:** Designed for dense 8L boards. Likely produces SES in minutes.
**Risk:** Still might not converge (Freerouting also "designed for" this and
failed). But Topor has stronger industry track record on multilayer.
**Codification:** locks/exports remain in current scripts; Topor takes
DSN/imports SES same as Freerouting.
**Time:** 1-2h after procurement + import + DRC fix pass.

### P2 — Continued manual routing across multiple PRs

**Cost:** ~8-16h additional engineering across 3-4 PRs.
**Benefit:** Each PR locks a piece. Codified per [[feedback-codify-not-patch]].
**Risk:** Each manual pattern hits new KiCad-specific quirk (just like F2,
Phase A, O1). The 6h of attempts didn't converge towards 0; suggests next
8-16h may not either. Diminishing returns.
**Time:** Calendar 2-4 days minimum.

### P3 — Sai KiCad GUI interactive routing

**Cost:** Sai's hands-on time (counter-policy per project's "delegate to
Claude").
**Benefit:** Sai's domain expertise + KiCad GUI visualization = correct
trace placement.
**Risk:** Couples board completion to Sai's availability.
**Time:** Estimated 1-2 days of Sai-routing.

### P4 (worker did not surface earlier) — Hybrid: Sai routes power+motor, worker scripts signals

**Cost:** Sai routes the ~28 stuck power + ~100 motor Kelvin paths
(critical-high-current paths) via KiCad GUI; worker continues scripts for
the ~371 lower-current channel signals using lessons from Phase A+O1.
**Benefit:** Splits work where each contributor has strongest leverage.
**Risk:** Boundary coordination overhead.
**Time:** ~1 day Sai + 4-6h worker in parallel.

## Worker recommendation

**P1 (Topor) primary, P4 (hybrid) fallback**:
- P1 buys back the 6h of engineering with a tested tool. If Topor produces
  SES in 1-2h, total cost is bounded.
- P4 if Topor budget rejected — distributes effort to highest-leverage paths.

## What the worker can do while Sai weighs in

- Codify the ZONE_FILLER traps in memory (DONE 2026-05-24).
- Sanitize PCB state to master HEAD e0d7d60 (DONE).
- Stress-test audit_meta.py against simulated regressions.
- Prepare PR-routing-final draft commit list (Phase A scripts, this options
  doc, RULES_MANIFEST row 13 trap entry) ready to push under whichever path
  Sai picks.

target.h md5 unchanged throughout: `7a4549d27e0e83d3d6f1ffaf67527d24`.

## Re-engagement format

When Sai responds, the worker needs adjudication on:
1. P1/P2/P3/P4 choice
2. If P1: who procures Topor license + timeline
3. If P4: which specific nets are Sai's vs worker's

Standing by.
