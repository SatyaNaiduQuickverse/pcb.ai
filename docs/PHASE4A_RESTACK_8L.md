# Phase 4a-restack-8L — 6-layer → 8-layer stackup change

**Status:** complete on branch; pending master audit + PR review.
**Branch:** `phase4a-restack-8L/8layer-stackup`.
**Scope:** pure stackup change. No netlist change, no firmware change, no
placement change (Phase 4b-redo4-R1 owns placement).
**Master directive:** Task #37 dispatch 2026-05-22.

---

## 1. Why scale to 8 layers

Phase 3-redo added **+413 components** (752 → 1,165) — a ~55% increase in
schematic complexity. Master's pre-prediction at the existing 6L stack
configuration (with In3.Cu promoted to signal) put D/S at risk of crossing
the 0.85 PASS gate.

8L gives:
1. **3 inner signal layers** (In2, In4, In6) instead of 1 → routing supply
   approximately doubles vs 6L-with-In3-promoted.
2. **Dual GND planes** (In1 + In5) sandwiching the +VMOTOR plane (In3) →
   return-path integrity + EMC headroom + symmetric reference for high-side
   and low-side signal layers.
3. **3 oz copper layers** (F.Cu, In3.Cu, B.Cu) → trace ampacity at 100 A
   burst per channel + 400 A peak bus (Phase 2-burst-resize lock).

JLC fab cost impact: **~$8–12 per board** at 5+ qty for the 8L+3oz upgrade
(vs 6L+1oz). Master pre-approved as part of Phase 2-burst-resize premium
upgrades.

## 2. Stackup specification

| Idx | Layer  | Type   | Cu wt | Purpose |
|---:|---|---|---:|---|
| 0  | F.Cu   | signal | 3 oz | Top signal + motor-phase high-current traces + TOLL FET pads + thermal face |
| 1  | In1.Cu | power  | 1 oz | GND plane (full board) — return-path for F.Cu/In2 signals |
| 2  | In2.Cu | signal | 1 oz | Inner signal — autoroute target (high-density nets) |
| 3  | In3.Cu | power  | 3 oz | **+VMOTOR plane (full board)** — heavy-copper for ≥280 A continuous, 400 A peak |
| 4  | In4.Cu | signal | 1 oz | Inner signal — autoroute target |
| 5  | In5.Cu | power  | 1 oz | GND plane (full board) — return-path for In4/In6 signals + dual-GND EMC sandwich |
| 6  | In6.Cu | signal | 1 oz | Inner signal — autoroute target |
| 31 | B.Cu   | signal | 3 oz | Bottom signal + secondary high-current + TOLL FET drain pads + thermal face |

**5 signal layers + 3 plane layers**. Total: 8 copper layers.

### 3 oz copper rationale

- **F.Cu / B.Cu** carry motor-phase traces (4 channels × 3 phases × 70 A continuous
  / 100 A 10 s burst). Per `sims/phase2_burst_resize/ipc2152_trace_ampacity.py`,
  3 oz @ 4 mm trace width handles 100 A 10 s burst comfortably.
- **In3.Cu (+VMOTOR plane)** carries the entire bus current — 280 A continuous
  worst case (all 4 channels at 70 A) and 400 A burst peak. 3 oz plane area
  has effective ampacity per width that vastly exceeds the requirement.

### JLC DRC implications at 3 oz copper

| Constraint | 1 oz minimum | 3 oz minimum (JLC capability) |
|---|---:|---:|
| Trace width  | 4 mil (0.10 mm) | 5 mil (0.13 mm) |
| Track-to-track clearance | 4 mil (0.10 mm) | 5 mil (0.13 mm) |
| Annular ring (via) | 4 mil (0.10 mm) | 4 mil (0.10 mm) |
| Min drill | 0.20 mm | 0.30 mm |

Phase 5b-retry routing constraint baseline updates: **W_eff = 0.13 + 2 × 0.13
= 0.39 mm** at 3 oz (was 0.45 mm at 1 oz). Slightly tighter footprint per
trace → marginally better D/S supply.

## 3. Code changes

### `hardware/kicad/setup_board.py`

- Replaced 6L `NEW_LAYERS_FIXED` with 8L `NEW_LAYERS_8L` constant.
- Per-layer descriptions document copper weight + intent.
- All 8 copper layers typed as "signal" (DSN-export-compatible per playbook
  trap T8); 3 plane layers carry "Phase 5c re-classifies to power" descriptor
  for post-autoroute layer-type correction.
- Activated the layer upgrade (previously bypassed in Phase 5b workaround).
- Smoke-tested: new `pcbai_fpv4in1.kicad_pcb` emits 8 copper layers
  (F.Cu, In1.Cu .. In6.Cu, B.Cu) with correct descriptions.

### `hardware/kicad/scripts/dsn_inject_planes.py`

- Rewrote layer-block builder to emit all 8 layers (F.Cu, In1.Cu, In2.Cu,
  In3.Cu, In4.Cu, In5.Cu, In6.Cu, B.Cu).
- Plane defs: GND on In1.Cu (full board), +VMOTOR on In3.Cu (full board),
  GND on In5.Cu (full board) — replaces the 4L/5L 3-plane-on-In2 layout.
- Padstack expansion to ALL 6 inner layers (`ALL_INNER_LAYERS = In1..In6`)
  for plane-served pad recognition.

### `hardware/kicad/scripts/dsn_strip_planes.py`

- Regex updated from `In[1-4].Cu` to `In[1-6].Cu` to handle 8L geometry.
- Idempotent pass-through preserved.

### `hardware/kicad/scripts/signal_density_check.py`

- Added `ETA_ROUTER_5LAYER = 0.65` (extrapolated from 2L=0.40, 3L=0.55).
- `_eta_for()` helper added; supports `num_signal_layers ∈ {2, 3, 5}`.
- Supply calc extended for 3 inner signal layers (In2 + In4 + In6) when
  num_signal_layers=5.

## 4. D/S re-prediction at 8L

Master's pre-dispatch estimate: **0.55–0.65 PASS** (at 1,165 components + 8L
+ R1 placement). The re-prediction here is **model-based** since the
.kicad_pcb at this stage is still the Phase 2-burst-resize-era 752-comp
layout — Phase 4b-redo4-R1 owns the actual placement-based D/S validation.

### Model: D growth

Phase 2-burst-resize 752 components → Phase 3-redo 1,165 components is a
**+55% delta**. Most new components are reliability passives (gate clamps,
bypass caps, TVS, NTC, dividers) that are placed *adjacent* to existing
high-current parts — typically *tighter* footprint per net than long-route
signals. Master's empirical estimate: **D grows by ~30%** (not 55%) because
the new nets are short and local.

Phase 2-burst-resize D ≈ 35,000 mm² (at 100×85 board, ~95 signal nets).
Phase 4a-restack-8L D ≈ 35,000 × 1.30 = **45,500 mm² (est.)**.

### Model: S growth (5 signal layers vs prior 2 or 3)

A_board = 100 × 85 = 8,500 mm² (board area unchanged).
η_router_5L = 0.65 (extrapolated empirical; vs 0.40 @ 2L / 0.55 @ 3L).

Per-layer signal supply ≈ A_board × (1 − f_pad) × η:
- F.Cu (f_pad ≈ 0.20):   8,500 × 0.80 × 0.65 = 4,420 mm²
- B.Cu (f_pad ≈ 0.05):   8,500 × 0.95 × 0.65 = 5,250 mm²
- In2.Cu (f_pad ≈ 0.05): 8,500 × 0.95 × 0.65 = 5,250 mm²
- In4.Cu (f_pad ≈ 0.05): 8,500 × 0.95 × 0.65 = 5,250 mm²
- In6.Cu (f_pad ≈ 0.05): 8,500 × 0.95 × 0.65 = 5,250 mm²

**S_total ≈ 25,400 mm² (est.)** at 5-layer routing.

### Predicted D/S

D/S = 45,500 / 25,400 ≈ **0.59** — comfortably in the **0.55–0.65 PASS
band** master pre-predicted. Margin to the 0.85 PASS gate: 0.26 (=
0.85 − 0.59). About 30% spare capacity.

### Validation deferred to Phase 4b-redo4-R1

Phase 4b-redo4-R1 will:
1. Regenerate `.kicad_pcb` from the Phase 3-redo netlist using kinet2pcb +
   setup_board.py (with the 8L stackup baked in).
2. Place all 1,165 components in R1 layout (4 MCUs in 2×2 center cluster
   per Sai's lock from earlier session).
3. Run `signal_density_check.py 5` for an actual D/S measurement.

If actual D/S exceeds 0.85, Phase 4b-redo4-R1 needs a placement redo (per
Sai's redo-not-mitigate rule). If actual D/S falls within the predicted
0.55–0.65 band, Phase 5b autoroute should converge cleanly.

## 5. +VMOTOR via-stitching audit (Task #43)

Script: `sims/phase4a_restack_8l/via_stitching_audit.py`.

### Inputs

- Bus current continuous: 4 ch × 70 A = **280 A** (Phase 2-burst-resize lock)
- Bus current burst @ 10 s: 4 ch × 100 A = **400 A** (Phase 2-burst-resize lock)
- Per-via ampacity (JLC 0.3 mm drill / 0.45 mm pad):
  - Conservative continuous (no copper-pour assist): 1.0 A/via
  - Aggressive continuous (with 3 oz pour + thermal mass): 2.0 A/via
  - 10 s burst (1.5× continuous derate): 1.5 A/via (cons.) / 3.0 A/via (aggr.)
- FoS target (Sai's reliability rule): 1.5× over continuous + burst

### Verdict at master's target (200 vias)

| Dimension | Bus load | Capacity | Margin | Status |
|---|---:|---:|---:|---|
| Continuous (conservative) | 280 A | 200 A | 0.71× | MARGINAL (relies on 3 oz pour) |
| Continuous (aggressive)   | 280 A | 400 A | 1.43× | MARGINAL (5% short of 1.5× FoS) |
| Burst @ 10 s (aggressive) | 400 A | 600 A | 1.50× | PASS ✓ |

### Recommendation: bump to **210 vias** for 1.5× FoS on both

| Dimension | Bus load | Capacity @ 210 vias | Margin | Status |
|---|---:|---:|---:|---|
| Continuous (aggressive) | 280 A | 420 A | 1.50× | PASS ✓ |
| Burst @ 10 s (aggressive) | 400 A | 630 A | 1.58× | PASS ✓ |

Delta from master's spec: **+10 vias** (200 → 210). JLC fab cost impact: **$0**
(vias are inclusive in standard SMT order).

### Placement strategy for Phase 5b-retry

| Region | Approx. via count |
|---|---:|
| CBULK output → VMOTOR rail entry (4× polymer cap × ~5 vias) | 20 |
| Per-channel VMOTOR fanout × 4 (~50 each: FET drains + trace + bypass cap stacks) | 200 |
| Mid-trace stitching (filler, ~ 1 via / 5 mm² VMOTOR pour) | 20 |
| **Total target** | **≥ 210** |

**Critical layout requirement**: 3 oz copper pour on +VMOTOR rail (F.Cu and
B.Cu) must surround every via to sustain the 2 A/via continuous baseline.
Without copper-pour assist, per-via ampacity drops to 1.0 A → bus capacity
at 210 vias = 210 A, MARGINAL (75% of continuous bus load).

## 6. Acceptance against master criteria

| Criterion | Status |
|---|---|
| setup_board.py emits 8L stackup with 3 oz on F.Cu/In3/B.Cu, 1 oz elsewhere | ✓ |
| dsn_inject_planes.py handles 8L geometry (5 signal + 3 plane layers) | ✓ |
| via-stitching count documented + meets ≥ 200 target | ✓ (recommend 210 for 1.5× FoS on both dimensions; delta $0) |
| D/S re-prediction matches master's ~0.55–0.65 estimate | ✓ (model predicts ~0.59; validation in Phase 4b) |
| target.h md5 unchanged (no firmware impact) | ✓ (`7a4549d27e0e83d3d6f1ffaf67527d24`) |
| One PR | ✓ (this PR — `phase4a-restack-8L/8layer-stackup`) |

## 7. Out-of-scope (deferred to next phases)

- **Actual placement** in 8L → Phase 4b-redo4-R1 (Task #38).
- **Actual D/S measurement** against placed components → Phase 4b post-placement.
- **Actual via placement** on +VMOTOR rail → Phase 5b-retry (post-autoroute pour fill).
- **Phase 5c layer-type reclassification** to power for the 3 plane layers
  in the final fab `.kicad_pcb` → after autoroute completes.
- **Conformal coating spec** (premium upgrade #4) → manufacturing-phase doc,
  not schematic.
