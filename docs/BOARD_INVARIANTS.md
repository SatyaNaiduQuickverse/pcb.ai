# Board Invariants (SSOT) — Phase 4-v2 Step 1

**Status**: v2 — addresses master review (5 issues). Pending Sai-approval lock.
**Per**: Phase 4-v2 dispatch Step 1.

Any PR changing this hash WITHOUT explicit "invariant-change" PR title = REJECT.

## Board geometry

- Outline: 100×100 mm
- Mount holes: 4× M3 at corners (5,5), (95,5), (5,95), (95,95)
- target.h md5: `7a4549d27e0e83d3d6f1ffaf67527d24` (firmware contract — LOCKED)
- Stackup: **10-layer** (F.Cu / In1=GND / In2=signal / In3=GND / In4=signal-BEMF / In5=+VMOTOR / In6=signal-SW / In7=GND / In8=signal / B.Cu)
- **Phase 4a-restack-10L 2026-05-26 (Sai-locked per PR #179 + docs/PHASE4A_RESTACK_10L_PROPOSAL.md)**: upgraded from 8L per Howard Johnson Sig Prop Ch.13.7 (more-layers remedy when QFN32 pin-remap unavailable). Sai cost-OK directive cleared (+$1-2/board production = 1-2% on $50-200 ESC BOM).
- **Stackup dielectric LOCKED 10L (preserves OQ-014 F.Cu→In1.Cu = 0.10mm)**:
  - F.Cu→In1.Cu prepreg: **0.10 mm** UNCHANGED (OQ-014 LOAD-BEARING; SW loop-L plane reference; STEP 6 0.1953nH/phase verification preserved)
  - In1.Cu→In2.Cu core: 0.15 mm (thinner than 8L's 0.20mm to fit extra layers in 1.6mm total)
  - In2.Cu→In3.Cu prepreg: 0.075 mm (NEW pair)
  - In3.Cu→In4.Cu core: 0.15 mm (NEW pair)
  - In4.Cu→In5.Cu prepreg: 0.10 mm (BEMF-to-VMOTOR spacing for OQ-016 shield)
  - In5.Cu→In6.Cu core: 0.15 mm
  - In6.Cu→In7.Cu prepreg: 0.075 mm (NEW pair)
  - In7.Cu→In8.Cu core: 0.15 mm (NEW pair)
  - In8.Cu→B.Cu prepreg: 0.10 mm (symmetric to F.Cu side)
  - **In8.Cu MULTI-USE** (lock 2026-05-27 expanded, worker R22+R26 catches during CH1 STEP 4 systemic FET-region congestion analysis): primarily signal-overflow (PWM stragglers + low-current control signals per STAGE0_10L_LAYER_MAP); ADDITIONALLY hosts:
    - **(a) Per-channel VMOTOR_CHn LOCAL pours** in FET regions (x≈4-16 for CH1, mirror per channel). VMOTOR_CHn is the per-channel post-Hall-sense rail (separated from +VMOTOR by R34 0R bridge in S3 supervisor). Local pour avoids surface-pour overlap conflicts on F.Cu/B.Cu in dense FET region; provides ~0.4nH bypass-loop physics per Bogatin Ch.5 for HS-FET bypass caps C62-70 (CH1) + mirror sets for CH2/3/4. R34 bridge vias In8↔In5 routed at S3 STEP 1.
    - **(b) FET-region universal escape** for residual stuck nets when F.Cu/B.Cu walled by SW-node zones + signal clusters. Eligible nets: SHUNT_A/B/C_TOP high-current returns, Kelvin sense traces (shunt→INA), CH1 +3V3 traversal, BEMF if In4 contended. Use thin In8 trace segments (≤6mm length) that enter walled corridor on inner layer + emerge on opposite side back to surface via stitching via pair. R34/S3 cross-subsystem integration unaffected.
    - **(c) Per-channel mirror inheritance**: CH2/3/4 inherit identical (a)+(b) usage at mirror coords (preserves R19/OQ-019 symmetry).
  In8 capacity budget: dual-use occupies ≤30% of FET region area per channel (3×3mm pour + ≤6 thin traces × 6mm × 0.25mm width ≈ 18mm²); signal-overflow capacity preserved outside FET regions (>70% In8 area unused). Per [[feedback-physics-as-compass]] + [[feedback-sureshot-over-sota]] + [[feedback-no-gui-session-autonomous-only]] (NO GUI fallback — autonomous layer-escalation is the answer for any walled net).
  - Total: 1.6 mm 10L (JLC standard) — copper 9×35µm (1oz) + 1×70µm (3oz In5 +VMOTOR) + 4×100µm prepreg + 4×75µm prepreg + 4×150µm core = ~1.6mm
  - Loop-L preservation: F.Cu→In1 = 0.10mm UNCHANGED → STEP 6 measured 0.1953nH/phase still valid + B.Cu→In7 (new) = 0.285mm (improved from 8L 0.335mm) → LS-side loop-L slightly better
  - EMI shield: BEMF (In4) now bracketed by In3 GND + In5 +VMOTOR (was In1 GND + In3 +VMOTOR in 8L); In5 +VMOTOR provides capacitive shield (favorable since SW switches against VMOTOR)
  - Routing capacity: 5 signal layers + 4 plane layers + dedicated In4 BEMF = 6 effective routing layers vs 4 in 8L = +50% capacity
  - JLC fab spec: 1.6mm 10L standard option (cost +$1-2/board production verified). Worker dispatch for setup_board.py re-run on canonical board mandatory.

## Subsystem zones (LOCKED on Sai-approval)

Per master v2 review #1: CH1-CH4 tightened to EXCLUDE the 35-65 central spine
(where S2/S3 sit).


## Bilateral layer assignment (per docs/BILATERAL_PLACEMENT.md, 2026-05-26)

Each subsystem zone applies to BOTH F.Cu + B.Cu, with components distributed
per the bilateral strategy:

| Subsystem | F.Cu role | B.Cu role |
|---|---|---|
| S1 battery | BAT_P/BAT_N solder pads + TVS | NTC + fuse (if room) |
| S2 bulk caps | (empty — top access not needed) | **4× 150µF polymer (under FET clusters)** |
| S3 supervisor + Hall | ACS770 (current path) + TPS3700 | (none) |
| S5 BEC | (analog routing if any) | **5× buck + LDO + LC filters** |
| S6 connectors + ESD | J14 + J12 + USBLC6 + LDO | (none) |
| CH1-CH4 | HS-FETs + shunt + gate-R + bypass + driver + MCU + INA + BEMF div | LS-FETs + LS decoupling + gate clamps + channel LEDs |

This layer assignment is enforced by G5 layout audit (per-side checks) and
G_PP6 HV creepage (skips pairs on different layer sets). Multi-layer thermal
sim at Stage 10 (OQ-007) validates the strategy.

| Subsystem | x_min | y_min | x_max | y_max | Function |
|---|---|---|---|---|---|
| S1 battery input | 0 | 89 | 100 | 100 | bottom edge — BAT_P/BAT_N solder pads + NTC + TVS (swapped 2026-05-26 with S6 per Sai mechanical revamp) |
| S6 connectors | 0 | 0 | 100 | 11 | top edge — J14 FC + J12 AUX + USBLC6 ESDs + LDO (swapped 2026-05-26 with S1) |
| CH1 (channel A) | 0 | 50 | 35 | 89 | NW — FET cluster + DRV + MCU + INA |
| CH2 (channel B) | 65 | 50 | 100 | 89 | NE — mirror_X(CH1) |
| CH3 (channel C) | 65 | 11 | 100 | 50 | SE — mirror_X(CH4) |
| CH4 (channel D) | 0 | 11 | 35 | 50 | SW — bottom-pair template |
| S2 bulk caps | 40 | 40 | 60 | 60 | central — 4× polymer caps low-ESR |
| S3 supervisor+Hall | 40 | 18 | 60 | 40 | central spine — TL431 + Hall |
| S5 BEC east strip (CH1 feed) | 35 | 50 | 40 | 82 | east of CH1 — feeds CH1 BEC rails |
| S5 BEC west strip (CH2 feed) | 60 | 50 | 65 | 82 | west of CH2 — feeds CH2 BEC rails (mirror of east) |
| S5 BEC south strip (CH4 feed) | 35 | 18 | 40 | 50 | east of CH4 — feeds CH4 BEC rails |
| S5 BEC north strip (CH3 feed) | 60 | 18 | 65 | 50 | west of CH3 — feeds CH3 BEC rails (mirror of south, ADDED 2026-05-26 per R20 symmetry — Sai-catch) |

Channels NO LONGER overlap central 35-65 column. S5 explicit bbox per v2 #4.

## Symmetry pairs (LOCKED, 2-fold mirror about x=50)

- **CH1 ↔ CH2**: mirror_X(50)
- **CH3 ↔ CH4**: mirror_X(50)

No 4-fold symmetry — only 2-fold pair-mirror per master dispatch.

## Subsystem I/O ports (LOCKED at zone boundary, ±0.5mm tolerance)

Per master v2 review #3: S6→CHn now 4 explicit rows.

| From → To | Port pos | Width | Signals | Reason |
|---|---|---|---|---|
| S1 → S3 | (50, 18) | 4 mm | +BATT, BATGND | central spine to bulk |
| S3 → S2 | (50, 40) | 4 mm | +BATT, BATGND, BUS_CURR_HALL_OUT | bulk caps + sensor |
| S2 → CH1 | (40, 50) | 4 mm | +VMOTOR, GND | feed CH1 FETs |
| S2 → CH2 | (60, 50) | 4 mm | +VMOTOR, GND | feed CH2 FETs |
| S2 → CH3 | (60, 50) | 4 mm | +VMOTOR, GND | feed CH3 FETs (mirror_Y of CH1) |
| S2 → CH4 | (40, 50) | 4 mm | +VMOTOR, GND | feed CH4 FETs |
| S6 → CH1 | (17, 82) | 2 mm | DShot_CH1, TLM_CH1, KILL_CH1 | FC commands CH1 |
| S6 → CH2 | (83, 82) | 2 mm | DShot_CH2, TLM_CH2, KILL_CH2 | FC commands CH2 |
| S6 → CH3 | (83, 50) | 2 mm | DShot_CH3, TLM_CH3, KILL_CH3 | FC→CH3 (south, mirror) |
| S6 → CH4 | (17, 50) | 2 mm | DShot_CH4, TLM_CH4, KILL_CH4 | FC→CH4 |
| S5 → CH1 | (35, 65) | 2 mm | +V5, +V9, +3V3 | BEC east strip → CH1 |
| S5 → CH2 | (65, 65) | 2 mm | +V5, +V9, +3V3 | BEC west strip → CH2 |
| S5 → CH3 | (65, 35) | 2 mm | +V5, +V9, +3V3 | mirror_Y |
| S5 → CH4 | (35, 35) | 2 mm | +V5, +V9, +3V3 | mirror_Y |

## Highway reservations (NO subsystem may place into)

Per master v2 review #2: removed vague "radial" entry; replaced with explicit
coords.

| Highway | x_min | y_min | x_max | y_max | Reason |
|---|---|---|---|---|---|
| +BATT/GND spine | 48 | 0 | 52 | 50 | 280A continuous power path top→center |
| BEMF return centerline | 47 | 50 | 53 | 82 | 4× BEMF signals to central MCU |
| TLM/AUX bus strip | 10 | 8.5 | 90 | 10.0 | inter-subsystem digital — relocated 2026-05-26 from (0,80,100,82) which collided with y86-extended CH south zones; now inside S6 (y0-14) just below J14/J12 connectors at y=5; x=10-90 width (cleared from H3/H4 corner mount KO circles at x<9 + x>91) (audit_highway_keepout.py G_M8 verifies no mount-hole intersection) |
| S2 to CH1 +VMOTOR feed | 30 | 47 | 36 | 53 | low-loop radial CH1 (6×6mm corner) |
| S2 to CH2 +VMOTOR feed | 64 | 47 | 70 | 53 | low-loop radial CH2 |
| S2 to CH3 +VMOTOR feed | 64 | 47 | 70 | 53 | low-loop radial CH3 (mirror) |
| S2 to CH4 +VMOTOR feed | 30 | 47 | 36 | 53 | low-loop radial CH4 |

## HDI via-in-pad whitelist (locked 2026-05-27 Sai cost-OK)

Per master 2026-05-27 R26 HDI dispatch (CH1 STEP-6 unblock — worker per-pin
analysis showed routing capped at 22/33 across PR#202–#206 due to via-area
saturation in the dog-bone fanout corridor between J18 south edge and
BEMF/CSA filter wall). HDI via-in-pad on J18 + J19 drops vias directly
under pin pads, eliminating the fan-out area pressure entirely.

| Component | Footprint | Pitch | HDI rationale |
|---|---|---|---|
| **J18** | QFN-32 5x5mm (AT32F421 MCU) | 0.5mm | South-edge BEMF + PWM escape; 11 nets saturated standard fanout |
| **J19** | HVQFN-24 4x4mm (DRV8300 gate driver) | 0.5mm | Driver fan-out; BSTA/B/C + PWM_INL/H fan-in collision |

**Whitelist scope is BINDING**: NO other components may use HDI via-in-pad
without Sai cost-OK + update to BOARD_INVARIANTS + audit_hdi_via_in_pad.
Cost envelope is +$2-3/board production (Sai cleared 2026-05-27) ONLY for
these two refs; expanding silently inflates BOM cost.

### HDI fab spec (verify in production with JLC quote)
- **Process**: HDI Class 2 — laser-drilled microvia + epoxy fill + plate-over
- **Microvia drill**: 0.10 mm (JLC laser limit; standard mechanical drill is 0.20mm min)
- **Microvia pad**: 0.25 mm (= QFN signal pad short-axis width — fits within SMD pad bbox)
- **Annular ring**: 0.075 mm (vs board std 0.10mm — DRU relaxes for HDI)
- **Hole clearance**: 0.10 mm (vs board std 0.25mm — DRU relaxes for HDI)
- **Fill**: epoxy non-conductive + Cu plate-over (required to prevent solder wicking during reflow)

### Enforcement gates
- `hardware/kicad/scripts/audit_hdi_via_in_pad.py` — verifies HDI vias only on whitelist
- `hardware/kicad/pcbai_fpv4in1.kicad_dru` — relaxes DRC for HDI sizes (scoped to `A.Hole <= 0.15mm`)
- `route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS` — router whitelist constant
- `docs/MASTER_HDI_SPEC.md` — full fab spec + production order requirements

### Other components: standard via cost preserved
All other footprints use board-default via: 0.30mm drill, 0.50mm pad,
0.10mm annular — standard JLC fab, no HDI surcharge.

## Invariant hash

Per master v2 review #5: compute + store hash.

Run `python3 hardware/kicad/scripts/compute_board_invariant_hash.py --write`
to compute and write.

```
BOARD_INVARIANT_HASH = c35d8b0c20db6452edf639011ddb3abf0c3c3c42b38425c57f8541bf3d3747f4
```

## Audit gate

`check_board_invariants_hash()` to be added to audit_meta.py:
- Recomputes hash from this file's structured tables
- Compares to stored BOARD_INVARIANT_HASH
- REJECT on drift unless PR title contains "invariant-change"

## Approval flow

1. master review v2 (this commit)
2. Compute + write hash
3. master final-approve
4. Lock — audit_meta enforces
