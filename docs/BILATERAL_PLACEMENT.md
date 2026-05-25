# Bilateral Subsystem Placement — F.Cu + B.Cu strategy

**Per Sai 2026-05-26**: *"if we have both sides why not use them properly rather
than fitting everything on top.. some components if we like distribute we could
keep subsystems far from each other.."*

This doc codifies the **layer-as-functional-floor** principle adopted for
Phase 4-v3 starting with B.Cu LS-FETs (PR #115), extending to whole-subsystem
distribution across F.Cu / B.Cu for EMC, thermal, and density wins.

## Principle

Each board side has a *functional purpose*:

| Layer | Functional purpose |
|---|---|
| **F.Cu — "Access + Power-source floor"** | Top-accessible: cables enter, test probes land, ICs we debug, polarized parts the eye reads at assembly. Power SOURCES (battery feed, FET drains carrying current INTO the board). |
| **B.Cu — "Return + Filter + Indicator floor"** | Bottom-side: hidden from access. Filter components (bulk caps, BEC bucks), heat-spreading copper, return-path planes, status indicators visible from underneath. Power RETURN (LS-FET sources, GND fills). |

Both floors are CONNECTED by stitching vias (mostly under FETs + bulk caps for
ultra-short loops).

## Subsystem → layer assignment (Phase 4-v3 lock)

| Subsystem | Layer | Reason |
|---|---|---|
| **Foundation** (mount holes, fids, motor pads, all TPs, BAT solder pads, J14 FC, J12 AUX) | F.Cu | Access required for cables, probes, hand-solder, frame-mount |
| **CH1-CH4 HS-FETs + shunt + gate-R + bypass cap (per phase)** | F.Cu | Power source side; gate-R near driver output; INA Kelvin sense to shunt all on one layer |
| **CH1-CH4 LS-FETs + LS-side decoupling + gate clamps** | B.Cu | Directly beneath HS-FETs (PR #115). SW node via cluster between them — ultra-short loop |
| **S1 battery input** (BAT pads + NTC + TVS + fuse) | F.Cu (pads), B.Cu (TVS/NTC if room) | BAT solder pads need access; protection components can go B.Cu to free F.Cu |
| **S2 bulk caps** (4× 150µF polymer 8mm) | **B.Cu** | **Directly under FET clusters** — HS drain F.Cu → via cluster → bulk cap B.Cu = lowest-ESL DC source loop. Caps don't need top access (no probe, no test). Frees ~32×8mm of F.Cu real estate. |
| **S3 supervisor + Hall** (ACS770, TPS3700) | F.Cu | Hall on +BATT current path geometrically constrained; supervisor near analog signals |
| **S5 BEC** (5× buck regulators + LDO + LC filters) | **B.Cu** (centre area, away from FET clusters) | Low-current rails (≤3A each); rarely accessed post-boot; switching EMI (600kHz-2MHz) BUT physically far from Hall via spatial separation; frees ~25×20mm of F.Cu |
| **S6 connectors + ESD + S6-LDO** | F.Cu (top) | Cables enter; ESDs on FC data lines need short trace to J14 |
| **Per-channel MCU + driver + INA** | F.Cu | Debug TP access at top; SWD/BOOT pads top-side |
| **Per-channel decoupling caps** | **Distribute F.Cu + B.Cu** around each IC | Each IC has VDD pins on BOTH sides of its package — caps on respective sides reduces F.Cu congestion + improves R25 access |
| **Per-channel BEMF dividers + filter caps** | F.Cu (near INA) | Analog signal path; co-locate with INA Kelvin sense |
| **Status LEDs** (3 global + 12 per-channel) | F.Cu | Top-visible for status indication during bring-up + operation |

## EMC isolation distance rules (proactive)

When subsystems CAN be placed on the same layer, enforce minimum separation to
prevent coupling (per Ott §6 + Bogatin §10):

| Pair | Min XY distance | Why |
|---|---|---|
| **BEC S5 ↔ Hall ACS770** | ≥ 15 mm | Hall is EMI-susceptible (DC + low-freq); BEC switches 600kHz-2MHz |
| **BEC S5 ↔ any FET cluster** | ≥ 10 mm | Different switching freqs (~24-48kHz FET vs 600kHz-2MHz BEC) — avoid intermodulation coupling |
| **BEMF comparator (U_CMP_*) ↔ any switching node (SW_*, MOTOR_*)** | ≥ 10 mm | Analog signal integrity |
| **MCU clock pins ↔ any high-current trace** | ≥ 5 mm | Digital noise immunity |
| **Bulk caps S2 ↔ FETs** | tight (≤ 5 mm via cluster) | DELIBERATELY close — shortens switching loop |
| **Adjacent HS-FET drains (different phases)** | ≥ 3 mm pad-to-pad | Cross-phase coupling minimization |

## Thermal coupling rules

| Pair | Rule |
|---|---|
| **FET clusters** | Spread heat to both layers via 4-9 thermal vias per FET package |
| **Bulk caps under FETs** | OK — caps generate negligible heat at 1.5x FoS ripple current |
| **BEC under MCU** | OK — BEC bucks at ~80% efficiency dissipate <0.5W each → MCU sees <5°C rise |
| **BEC under Hall** | FORBIDDEN — Hall thermal drift coefficient is ~0.2%/°C; BEC heat could shift ADC reading. Keep ≥15mm XY separation. |

## Routing implications

- **PDN +VMOTOR plane** on In3.Cu (heavy 3oz inner) → no change
- **GND continuous** on In1.Cu + In5.Cu → no change
- **B.Cu added to plane stack** for return-path under B.Cu components (BEC switching nodes, bulk cap return)
- **HS↔LS SW-node vias**: ~50 vias per FET pair (Sai G_R5 1.5x FoS at 100A burst)
- **BEC switching nodes (B.Cu)**: route locally in BEC region, reference inner GND plane

## Audit gate impacts

The bilateral strategy is enforced by:

| Gate | Behavior |
|---|---|
| G3 audit_loop_area | XY projection of HS+LS loop = small (~1mm² via cluster) → PASS easily |
| G4 audit_decoupling | Per-IC caps may be F.Cu OR B.Cu; same-side rule (R25) applies per side |
| G5 audit_layout_compliance | Layer-aware checks (per-side overlap, per-side passive anchoring) |
| G_PP6 audit_hv_creepage | Already layer-aware (skips pairs on different layer sets) |
| **G_EMC1 (NEW, future)** | Audit min XY distance between named pairs above (BEC↔Hall etc) — TODO future gate |
| **G_THERMAL_COUPLING (NEW, future)** | Audit no FORBIDDEN thermal pair (BEC vertically aligned with Hall) — TODO future gate |

## Implementation rollout

| Stage | Bilateral action |
|---|---|
| 0 (S6) | F.Cu only (no change — connectors must be top-side) |
| 1 (anchors) | F.Cu only (motor pads have B.Cu component for via stitching but anchored on F.Cu) |
| **2 (CH1)** | **HS F.Cu / LS B.Cu** (per PR #115 — locked); per-channel decoupling distribute on next iteration |
| 3-5 (CH2-4) | Mirrors of CH1 — same F.Cu/B.Cu split (mirror preserves layer-pairing) |
| 6 (S3 supervisor) | F.Cu (Hall constrained) |
| **7 (S5 BEC)** | **B.Cu** (NEW per this doc) — under MCU/centre, ≥15mm from Hall |
| 8 (S1 input) | F.Cu pads + B.Cu protection |
| **9 (S2 bulk caps)** | **B.Cu under FET clusters** (NEW per this doc) — ultra-short switching loop |
| 10 (final integrate) | Cumulative thermal sim re-run (validates OQ-007 + this strategy) |

## Open questions opened by this strategy

### OQ-010 — B.Cu component-density vs F.Cu balance

With S2 + S5 + LS-FETs + LS decoupling + LEDs on B.Cu, does B.Cu density
exceed F.Cu? Need component-area-by-layer audit after CH1 lands (we'll see).
Resolution: if B.Cu > 60% density, pull some LEDs back to F.Cu.

### OQ-011 — Thermal model needs multi-layer + multi-side update

Phase 4-v2 baseline T_J was single-side. With S2 bulk caps + S5 BEC on B.Cu
directly under FET clusters, multi-layer thermal sim at Stage 10 is essential.
Already tracked as OQ-007; this doc adds the constraint that the multi-layer
sim must include BEC heat sources too.
