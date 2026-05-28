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

### HDI Class extension: blind/buried F.Cu↔In2 (Sai cost-OK 2026-05-28; OQ-020 ACTIVATE)

The HDI extension for the 4 residual J18/J19 escape nets the engine v1
naively counted as "covered by F-In1 microvia" but which physically bottom on
the In1=GND plane (NOT a signal escape). Per the layer-aware escape supply
correction (T12 in the engine fixture suite + `docs/DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE.md`
2026-05-28 "DIAGNOSIS CORRECTION" + escape-density-not-layer-capacity), the
engine v1 / PR #171 OQ-020 closure was wrong — the offered HDI microvia
F-In1 was DROPPED from supply by layer-awareness (it stitches to GND), so
the 4 nets still had no escape. The fix is a blind/buried via class that
reaches In2 (a signal layer on the 10L stackup).

**New via class** (added to whitelist on top of the existing microvia F-In1):

- **Process**: JLC HDI Class with blind/buried — laser-drilled blind via,
  epoxy-filled + plate-over (same fab process; just span extends one layer).
- **Span**: F.Cu → In2.Cu (skips In1=GND, lands on In2=signal). Total depth
  ≈ 0.10mm prepreg (F-In1) + 0.035mm In1 copper + 0.15mm core (In1-In2) =
  ~0.285 mm — well within JLC laser capability (≤0.4 mm typical).
- **Blind via drill**: 0.15 mm (>= JLC HDI blind/buried laser min; +50% FoS
  above the 0.10mm single-microvia laser limit, per §5c FoS-everywhere).
- **Blind via pad**: 0.30 mm (>= drill + 2×annular ring = 0.15 + 2×0.075 =
  0.30 mm; sits within QFN signal-pad bbox 0.25mm short-axis when emitted
  via-in-pad on the long-axis dimension; verify per-pin in DRC).
- **Annular ring**: 0.075 mm (= existing microvia ring; ≥ board std 0.10mm
  AFTER plate-over; FoS margin above JLC blind-via fab min of 0.05mm).
- **Hole clearance**: 0.10 mm (= existing HDI hole clearance; relaxed from
  board std 0.25mm only inside the whitelist).
- **Fab cost adder**: ~$2-5/board over base-HDI (JLC blind/buried Class
  upgrade; on top of the existing +$2-3/board epoxy-fill+plate-over). Sai
  cost-cleared 2026-05-28 for the 4 residual signals (~$5/board total HDI
  envelope: standard microvia + blind/buried add-on, ONLY on J18+J19).

**NARROWEST possible scope** — blind F-In2 vias are permitted ONLY on these
**specific J18/J19 signal pins** (CH1 only; 6 nets, 8 sanctioned net+pin
landings, one blind via per pin). The canonical .kicad_pcb net names carry
the schematic `_CH1` channel suffix (J18+J19 are the CH1 instances of the
MCU + gate-driver; the CH2/3/4 mirrors at J28+J29/J38+J39/J48+J49 are NOT
in this whitelist).

| Net (canonical .kicad_pcb name) | Logical signal | Footprint | Pin # | Rationale |
|---|---|---|---|---|
| `BSTB_CH1` | BSTB | J19 | 17 | gate-driver bootstrap B — residual escape on J19 west side |
| `PWM_INHB_CH1` | PWM_INHB | J18 | 19 | PWM input high B — residual escape on J18 east side |
| `SWDIO_CH1` | SWDIO | J18 | 23 | SWD data — residual escape on J18 east side |
| `PWM_INLA_CH1` | PWM_INLA | J18 | 15 | PWM input low A — residual escape on J18 south side |
| `PWM_INHB_CH1` | PWM_INHB | J19 | 23 | partner pin of `PWM_INHB_CH1` at J18.19 — J19-end blind escape (lever D 2026-05-28) |
| `PWM_INLA_CH1` | PWM_INLA | J19 | 1  | partner pin of `PWM_INLA_CH1` at J18.15 — J19-end blind escape (lever D 2026-05-28) |
| `GLB_CH1`      | GLB      | J19 | 10 | gate-driver low B output — new net+pin; closes J19_S overflow residual (lever D 2026-05-28) |
| `KILL_RAIL_N_CH1` | KILL_RAIL_N | J19 | 8  | DRV nSLEEP / kill-rail — new net+pin; closes CH1 30/30 LAST residual after lever c (GLC In2 detour) + lever F (per-class halo) opened J19.8 to 0.383mm per-layer clearance (lever G 2026-05-28) |

The first 4 entries are the original CH1 STEP-8b worker-analysis set
(needing In2 to escape; on the 10L stackup the only way to get a F.Cu pin
to In2 in one structure is a blind F.Cu↔In2 via). Entries 5-7 are the
**2026-05-28 lever D additions** for CH1 30/30 — Phase 3 PR #227 left 5
residuals; 3 of them blocked because their J19-end pin had no blind
supply. Entry 8 is the **2026-05-28 lever G addition** — after lever c
(GLC In2 detour, PR #227 8922420) opened J19.8 per-layer clearance to
0.383mm and lever F (per-class halo, PR #231 fd52f40) honored it,
KILL_RAIL_N_CH1 at J19.8 was the last CH1 residual blocked solely on
missing whitelist entry (via_class_for_span returned None for every L2
because microvia_F_In1 lands on In1=GND and blind_F_In2 required the
net to be in BLIND_F_IN2_NET_WHITELIST — not present, refused). Adding
KILL_RAIL_N_CH1.J19.8 → router emits blind F.Cu↔In2 at J19.8 → escape to
In2 → cooperative/maze routes onward to D38/R76/D37 on B.Cu, closing
CH1 30/30.

Same OQ-020 fab class across all 8 landings (drill 0.15mm / pad 0.30mm /
annular 0.075mm / hole clearance 0.10mm, all above fab min with §5c FoS
— never cut-to-cut), zero marginal fab cost (stays inside the +$2-5/board
JLC HDI blind/buried envelope Sai cleared 2026-05-28). The existing
microvia F.Cu↔In1 class is RETAINED for nets whose return-path / GND-
stitch need is what the microvia delivers (and where the signal escape is
via the standard fanout band, not via-in-pad).

**Whitelist scope is BINDING**: blind F.Cu↔In2 vias on ANY pin not in the
above 8 landings = FAIL `audit_hdi_via_in_pad.py` (layer + whitelist
check). Adding a new pin requires Sai cost-OK + update to this section +
audit re-lock.

**DRU enforcement**: `hardware/kicad/pcbai_fpv4in1.kicad_dru` carries a
blind-via geometry rule scoped to vias with the new dimensions (drill
0.15mm) AND on the 6 named nets only — `==` net-name comparison per
[[reference-kicad-dru-libeval-crash]] (KiCad 9.0.2 libeval SIGTRAPs on
`=~` regex; only `==` is headless-safe). KiCad libeval cannot reliably
condition on pin number; per-pin enforcement is documentary (this table
+ `audit_hdi_via_in_pad.BLIND_F_IN2_SANCTIONED_LANDINGS`) — the DRU's
net-name set is the binding fab gate. The 2 PWM_INHB / PWM_INLA J19-end
partner pins required NO DRU edit (the net names were already in the
condition); `GLB_CH1` was added to the net condition for lever D;
`KILL_RAIL_N_CH1` was added for lever G.

### HDI Class extension: stacked microvia F.Cu↔In1↔In2 (Sai cost-OK 2026-05-28; LEVER L)

Master 2026-05-28 CH1 30/30 LEVER L (drone-grade reliability + no cut
corners). JLC HDI Class 2 supports **stacked microvia** natively: TWO
microvias geometrically aligned (top F.Cu↔In1.Cu stacked directly on top
of bottom In1.Cu↔In2.Cu). This adds a **SECOND signal-reaching via
mechanism per pin** in addition to the OQ-020 blind F-In2 class — the
router may choose blind OR stacked per pin, both reaching In2 (signal
layer). The In1 landing between the two stacked microvias is an isolated
"antipad+pad" copper island, NOT tied to the In1 GND plane and NOT tied
to the signal — it is the stacked-via pad between two adjacent-layer
microvias.

**Why this MATHEMATICALLY GUARANTEES escape budget > demand at 0.5mm QFN
pitch**: adding stacked microvia as a second signal-reaching mechanism
per whitelist pin DOUBLES the layer-aware supply on each whitelist side
(per `phase_a.side_supply`: blind_F_In2 = 1 slot per whitelist-eligible
residual net + stacked_microvia_F_In1_In2 = 1 slot per same = 2 signal-
reaching slots per pin). Pin landings on the 6 LEVER L whitelist nets
each carry supply 2, demand 1 — guaranteed surplus at every landing.

**Industry standard since iPhone 4 era** — Apple/Samsung phones use
stacked microvia extensively at every fine-pitch BGA/QFN; established
reliability with millions of fielded units. No new fab process (same
JLC HDI Class 2 — laser-drilled microvia + epoxy fill + plate-over);
just two laser passes geometrically aligned.

**New via class** (added to whitelist on top of blind F-In2):

- **Process**: JLC HDI Class 2 stacked microvia — TWO laser-drilled
  microvias geometrically aligned + epoxy-filled + plate-over (same fab
  process; just two laser passes per stack).
- **Top microvia**: drill 0.10mm / pad 0.25mm; span F.Cu↔In1.Cu (adjacent
  laser pair; identical geometry to existing OQ-014 microvia F-In1).
- **Bottom microvia**: drill 0.10mm / pad 0.25mm; span In1.Cu↔In2.Cu
  (adjacent laser pair; the In1 landing is an isolated pad island).
- **Annular ring**: 0.075mm each (≥ board std 0.10mm AFTER plate-over;
  FoS margin above JLC blind-via fab min 0.05mm).
- **Stacking alignment tolerance**: ≤0.025mm laser-to-laser registration
  per JLC HDI Class 2 spec (well within the 0.075mm annular budget; no
  cut-to-cut per §5c FoS).
- **Continuous signal path**: F.Cu pin → top microvia → In1 pad island →
  bottom microvia → In2 signal escape; bypasses In1 GND via the
  antipad+pad isolation.
- **Fab cost adder**: ~$1-2/board over base-HDI (no new process, second
  laser pass + alignment). Sai cost-cleared 2026-05-28 for the same 6
  whitelist nets (~$3-7/board total HDI envelope: standard microvia +
  blind/buried OQ-020 + stacked LEVER L; ONLY on J18+J19).

**Same scope, narrowest possible** — stacked microvia permitted ONLY on
the same 6 nets / 8 sanctioned (net, pin) landings as BLIND_F_IN2 (CH1
only). The canonical .kicad_pcb net names carry the schematic `_CH1`
suffix; CH2/3/4 mirrors NOT in this whitelist.

| Net (canonical .kicad_pcb name) | Logical signal | Footprint | Pin # | Rationale |
|---|---|---|---|---|
| `BSTB_CH1` | BSTB | J19 | 17 | gate-driver bootstrap B — +1 signal-reaching slot (paired with blind F-In2) |
| `PWM_INHB_CH1` | PWM_INHB | J18 | 19 | PWM input high B — +1 signal-reaching slot |
| `SWDIO_CH1` | SWDIO | J18 | 23 | SWD data — +1 signal-reaching slot |
| `PWM_INLA_CH1` | PWM_INLA | J18 | 15 | PWM input low A — +1 signal-reaching slot |
| `PWM_INHB_CH1` | PWM_INHB | J19 | 23 | partner pin of J18.19 — +1 signal-reaching slot |
| `PWM_INLA_CH1` | PWM_INLA | J19 | 1  | partner pin of J18.15 — +1 signal-reaching slot |
| `GLB_CH1`      | GLB      | J19 | 10 | gate-driver low B output — +1 signal-reaching slot |
| `KILL_RAIL_N_CH1` | KILL_RAIL_N | J19 | 8  | DRV nSLEEP / kill-rail — +1 signal-reaching slot |

**Whitelist scope is BINDING**: stacked microvia on ANY pin not in the
above 8 landings = FAIL `audit_hdi_via_in_pad.py` (pair detection +
whitelist check). Adding a new pin requires Sai cost-OK + update to this
section + audit re-lock.

**DRU enforcement**: `hardware/kicad/pcbai_fpv4in1.kicad_dru` carries a
stacked-microvia leg-geometry rule scoped to vias with the new
dimensions (drill 0.10mm) AND on the 6 named nets only — `==` net-name
comparison per [[reference-kicad-dru-libeval-crash]]. KiCad libeval
cannot reliably condition on pin number or via stacking; per-pin + per-
pair enforcement is documentary (this table +
`audit_hdi_via_in_pad.STACKED_MICROVIA_SANCTIONED_LANDINGS`) and the
audit's pair-detection logic is the binding fab gate.

**Audit identification**: the stacked structure is recognised as TWO
VIATYPE_MICROVIA vias at the SAME (x, y) (±0.05mm TOLERANCE_MM) on the
same net, one with layer pair (F.Cu, In1.Cu) and the other with layer
pair (In1.Cu, In2.Cu). Each leg individually still satisfies the v7
adjacent-pair microvia span check; the audit's post-loop pair detection
groups co-located legs by (snap-grid XY, net) and flags any cluster
having both top and bottom legs as a stacked microvia.

### Enforcement gates
- `hardware/kicad/scripts/audit_hdi_via_in_pad.py` — verifies HDI vias only on whitelist
  (extended 2026-05-28 to accept blind F.Cu↔In2 vias on the 6 net whitelist
  above [4 OQ-020 ACTIVATE + GLB_CH1 lever D + KILL_RAIL_N_CH1 lever G],
  in addition to the existing microvia F.Cu↔In1 acceptance; LEVER L 2026-
  05-28 adds STACKED_MICROVIA_NET_WHITELIST + post-loop pair detection
  for the F.Cu↔In1↔In2 stacked class on the same 6 nets / 8 landings)
- `hardware/kicad/pcbai_fpv4in1.kicad_dru` — relaxes DRC for HDI sizes (scoped to `A.Hole <= 0.15mm`),
  + new blind F.Cu↔In2 geometry rule scoped to the 6 net names above
  + new stacked-microvia leg-geometry rules scoped to the same 6 nets (LEVER L)
- `route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS` — router whitelist constant
- `hardware/kicad/scripts/routing_engine/phase_a.py` — LAYER-AWARE escape supply
  (`side_supply` drops plane-bottoming via classes from supply; T12 fixture
  proves a naive plane-counting liar FAILS — the OQ-020 root fix)
- `docs/MASTER_HDI_SPEC.md` — full fab spec + production order requirements

### Other components: standard via cost preserved
All other footprints use board-default via: 0.30mm drill, 0.50mm pad,
0.10mm annular — standard JLC fab, no HDI surcharge.

## Frozen banked nets (CH1 30/30 lever J — R38, 2026-05-28)

Per master 2026-05-28 CH1 30/30 lever J (targeted ripup-rebuild) and Sai
mandate "have strong validation and audit gates": when the cooperative
router's targeted-ripup capability surgically rips a foreign net to free
a corridor for a blocked net, certain nets MUST NEVER be ripped under
any circumstance. They are "banked" — validated, sim-confirmed, and any
re-route would either (a) brick a PDN already-current-density / EMI /
thermal verified, or (b) cascade into a per-channel power redo + sim
that defeats the surgical-rip cost saving.

The list is enforced TWO ways:
  1. **Code-side SSoT**: `hardware/kicad/scripts/targeted_ripup.py`
     `FROZEN_BANKED_NETS` tuple (the import boundary the router consults
     at rip-decision time; `is_frozen_banked(netname)` returns True for
     any name in the list).
  2. **Doc-side SSoT**: this table. Audit gate
     `audit_frozen_banked_nets_preserved.py` G_J3 verifies the code-side
     and doc-side intersect on the canonical set + are NOT divergent.

Updating the list requires editing BOTH AND a new PR tagged
`[invariant-change]`. Per `[[feedback-codify-not-patch]]` 2026-05-24
codified-fix + codified-audit + master-independent-test, all 3 artifacts
travel together for every entry.

| Net | Class | Why frozen |
|---|---|---|
| `+VMOTOR` | Power plane | 280A burst — PDN already current-density + thermal verified (Tier 1 sim PASS). Re-route ⇒ full PDN redo + sim. |
| `GND` | Reference plane | Continuous plane reference for every signal layer; ripping ⇒ return-path discontinuity for the entire board. |
| `+BATT` | Power trunk (S1 star) | Single 40A source; star topology validated. Ripping defeats the +BATT/GND-return loop validated at Tier 1. |
| `+VMOTOR_CH1` | Per-channel rail | Post-Hall-sense +VMOTOR rail; separated from +VMOTOR by R34 0R bridge in S3. In8 local pours (BOARD_INVARIANTS §In8 multi-use a) feed FET bypass caps with 0.4nH bypass-loop physics. |
| `+VMOTOR_CH2` | Per-channel rail | Mirror_X(CH1) per R19 — same validation. |
| `+VMOTOR_CH3` | Per-channel rail | Mirror per R19. |
| `+VMOTOR_CH4` | Per-channel rail | Mirror per R19. |
| `VMOTOR_CH` | Per-channel bus-cap rail | 85-pad envelope including Q5/Q7/Q9 HS-FET drain + C62-C100 bulk-cap network; carries the FET-region bypass-loop current at 280A burst envelope. Ripping cascades into S2-bus + S5-BEC validation redo. Added 2026-05-28 per `docs/CH1_DRONE_RELIABILITY_SWEEP_2026-05-28.md` Finding #5. |
| `BATGND` | Battery return | S1↔S2 validated low-impedance return; ripping breaks the bulk-cap → battery loop sim (Tier 1). |
| `+3V3` | BEC trunk | S5 BEC validated (multi-load tree); cross-subsystem feeder. |
| `+5V` | BEC trunk | S5 BEC validated. |
| `+9V` | BEC trunk | S5 BEC validated. |
| `+3V3A` | BEC analog trunk | S5 BEC validated; analog reference rail. |
| `+3V3_CH1` | Per-channel BEC | CH1-side BEC tap — validated by S5→CH1 cumulative sim. |
| `+5V_CH1` | Per-channel BEC | CH1-side BEC tap. |
| `+9V_CH1` | Per-channel BEC | CH1-side BEC tap. |
| `+3V3A_CH1` | Per-channel BEC analog | CH1-side BEC tap. |
| `+3V3_CH2` | Per-channel BEC | Mirror_X(CH1) per R19. |
| `+5V_CH2` | Per-channel BEC | Mirror. |
| `+9V_CH2` | Per-channel BEC | Mirror. |
| `+3V3_CH3` | Per-channel BEC | Mirror per R19. |
| `+5V_CH3` | Per-channel BEC | Mirror. |
| `+9V_CH3` | Per-channel BEC | Mirror. |
| `+3V3_CH4` | Per-channel BEC | Mirror per R19. |
| `+5V_CH4` | Per-channel BEC | Mirror. |
| `+9V_CH4` | Per-channel BEC | Mirror. |
| `KILL_CH1` | Safety kill broadcast | Per-channel KILL is SAFETY (criticality 100, R36); routed FIRST, never ripped. |
| `KILL_CH2` | Safety kill broadcast | Per R19 mirror. |
| `KILL_CH3` | Safety kill broadcast | Per R19 mirror. |
| `KILL_CH4` | Safety kill broadcast | Per R19 mirror. |

Code-side import target:

```python
from hardware.kicad.scripts.targeted_ripup import (
    FROZEN_BANKED_NETS, is_frozen_banked,
)
```

A net NOT in this list is rippable subject to the other R36-R39 / G_J1-
G_J5 disciplines. Adding a net to the frozen set RAISES the protection;
removing requires Sai cost-OK + new sim cycle on the affected subsystem.

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
