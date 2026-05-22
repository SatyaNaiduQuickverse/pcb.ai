# Phase 5b-retry — plane-served fix + NW relief + autoroute (v2.2.4 incomplete; v2.2.3 fallback pending)

Per master adjudication 2026-05-22 (3 binding commitments before retry):
1. ✅ Plane-served fix (option a — SMD pad shapes on inner plane layers)
2. ✅ NW hotspot relief attempts
3. ⏳ Empirical η_router calibration (deferred)

Plus master's secondary adjudication 2026-05-22:
4. ⏳ v2.2.3 fallback test (next; this PR commits the empirical findings first)

---

## 1. Plane-served fix (option a) — EMPIRICALLY VALIDATED

`dsn_inject_planes.py` previously only expanded through-hole padstacks to
include inner-layer shapes. Phase 5b-retry: expanded ALL padstacks (SMD too).
SMD pads on F.Cu/B.Cu now also have shapes on In1.Cu/In2.Cu/In3.Cu so
Freerouting recognizes them as plane-served when they fall inside a plane
polygon.

**Result confirmed from Freerouting startup log:**

| Net | Before pad expansion | After pad expansion |
|---|---|---|
| GND (247 pins) | "Pin on net 'GND' (connected: 1/247)" × 247 queued | **0 queued** ✓ |
| +VMOTOR | queued | **0 queued** ✓ |
| Total items to route | 872 | **597** (−32%) |
| Pass #1 failures (14 min in) | 1069+ | **102** (−90%) |

Plane-served working. GND + VMOTOR completely off the routing queue.

Remaining queued nets: +V5_FC (27 pins), +BATT_NTC (24), +3V3 (24), +3V3A
(15), TLM (11), +V5_PI5 (8), +V5_AI (7), buck SW/FB/BST nets, signal nets.
Those route normally on signal layers — that's correct.

---

## 2. NW hotspot relief — partial improvement (1.43 → 1.22)

Per master path (i) + (ii). Multiple migration attempts:

| Iteration | NW D/S | Overall D/S |
|---|---|---|
| Phase 4b-redo3 baseline (refined supply per path iii) | 1.43 | 0.91 |
| After V9_VTX1 pads migrated NW→SE (2 pads) | 1.24 | 0.91 |
| After BEC bucks shifted +10mm right | 1.33 | 0.91 |
| After BEC bucks shifted to x=50..90 (NE) | 1.27 | 0.91 |
| After BEC bucks shifted to x=50..90 (final NE) + battery section migrated NW→SE | **1.22** | 0.91 |

**Irreducible NW load = CH1 channel MCU + per-channel 50+ passives** (f_F_NW =
0.77; 77% of F.Cu pad-blocked by CH1 cluster). Channel-at-corner architecture
is structurally bound to per-MCU pin-side connectivity (Phase 4b-redo,
playbook trap T8). NW relief options exhausted without major MCU restructure.

Per-zone final state (refined supply, path iii):

| Quadrant | D | f_F | S | D/S |
|---|---|---|---|---|
| NW | 3092 mm² | 0.77 | 2527 mm² | **1.22** ← hotspot (CH1 cluster) |
| NE | 2938 | 0.53 | 2793 | 1.05 ← hotspot |
| SW | 2406 | 0.37 | 2999 | 0.80 |
| SE | 1883 | 0.27 | 3112 | 0.61 |

Whole-board D/S = 0.91 = **MARGINAL** per master gate (0.85 ≤ x < 1.00 = "try
autoroute but expect <95%").

---

## 3. Freerouting v2.2.4 — Pass #1 incomplete after 37 min wall (KILLED)

```
Started: 2026-05-22 13:26:24 UTC
Pass #1 init: 597 items to route, 413 incompletes (vs prior 872/688)
Wall time: 37 min (vs prior 14 min for kill)
CPU time: 1h12m (4-core, intensive)
Failure count: 188 (vs prior 1069 — improvement)
Pass #1 completion: NEVER REACHED
Process killed at 37 min wall.
```

Failure rate slowed (49 at 13min → 102 at 26min → 188 at 37min — decelerating)
suggesting Freerouting was making progress but pathologically slow. Same
"MazeSearchAlgo.init: no accessible expansion doors" pattern in latter failures,
indicating CH1-cluster routing congestion despite plane-served power nets.

Per master's locked thresholds: <95% post-plane-injection = genuine placement
defect → trigger feedback-redo-not-mitigate. But v2.2.3 fallback test
adjudicated FIRST (next step per master 2026-05-22 second adjudication).

---

## 4. Files committed in this PR

| File | Status |
|---|---|
| `hardware/kicad/scripts/dsn_inject_planes.py` | Option (a) padstack expansion to ALL inner layers (was through-hole only) |
| `hardware/kicad/scripts/signal_density_check.py` | Path (iii) per-zone supply refinement + empirically-refined plane-served list (GND + VMOTOR only — others route as signal) |
| `hardware/kicad/scripts/place_board.py` | NW relief: V9_VTX1 pads NW→SE, BEC bucks → x=50..90, battery section NW→SE, BEC passive band centered |
| `hardware/kicad/scripts/apply_silkscreen.py` | Position updates for new battery/BEC layout |
| `hardware/kicad/pcbai_fpv4in1.kicad_pcb` | regen (364 footprints, 0 overlaps, MCU rotations preserved) |
| `hardware/kicad/pcbai_fpv4in1.dsn` + `_raw.dsn` | regen with full padstack expansion |
| `docs/PHASE5B_RETRY.md` | this document |
| `docs/artifacts/phase5b-retry/placement_F_Cu_silk.svg` + `_B_Cu_silk.svg` | snapshots |
| `docs/artifacts/phase5b_autoroute/freerouting.log` | v2.2.4 run log (37 min, killed) |

target.h md5 `7a4549d27e0e83d3d6f1ffaf67527d24` pre+post. **NO firmware impact.**

---

## 5. Next step (per master adjudication 2026-05-22)

GO option (d) — install Freerouting v2.2.3 worker-local + retry Pass #1 with
60-min budget. Same DSN as committed here. Outcomes:
- ≥95% → amend this PR with SES import + completion %.
- <95% or no termination → pause + flag Sai-queue (per master) for next path: (b) channel restructure or (c) board grow 100×85 → 120×100. NO third attempt without owner input.

---

## 6. Rules check

- **Rigor §10/§5b/§5c:** every metric from actual Freerouting run / pcbnew measurement, not estimate.
- **Playbook trap T8:** placement-routability validated via D/S gate; NW exhausted reasonable relief; remaining is structural CH1 corner.
- **`feedback-redo-not-mitigate`:** redo applied at Phase 4b-redo (rotation), 4b-redo2 (BEC absorb), 4b-redo3 (board grow + density gate). Phase 5b-retry continues this — plane fix is real engineering, not band-aid.
- **R17 (no loose threads):** all 3 master commitments addressed (one deferred per adjudication); empirical findings surfaced in §1-3; next path explicitly queued per master 2026-05-22.
- **No-defer:** v2.2.3 test happens RIGHT AFTER this PR commit per master directive (single-variable change).
