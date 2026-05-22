# Phase 4 — Subsystem-aware placement spec (R6 motor-pad-anchored)

**Authored**: 2026-05-22 by master per Sai directive 'subsystem by subsystem with known I/O'.

This doc supersedes the R1 (center-cluster) and proposed R5 (corner-MCU) architectures. **R6 = motor-pad-anchored** per premium ESC research (T-Motor F55A Pro III, iFlight BLITZ E80, Tekko32 Metal industry pattern).

## 1. Architecture principle

4 channels distributed in 4 quadrants. For each channel:
- Motor output pad at outer-edge of quadrant
- 6 AOTL66912 MOSFETs SYMMETRIC around the motor pad (industry standard)
- MCU + 3 gate driver passive sets adjacent to FETs
- Protection cluster (LM393 + TL431 + 74LVC1G08 + LED + NTC) adjacent to MCU
- Per-FET-pair bypass cap stack (100nF+10nF+1nF × 3 pairs)
- 3 phase TVS at motor pad
- 12 gate clamps (6 zeners + 6 pulldowns) at FET gates

Central spine: battery → bulk caps → supervisor + Hall → 4-channel +VMOTOR split. BEC subsystem in distributed side bands. FC + AUX at remaining edges.

## 2. Board geometry (100×85 mm, 8L stackup)

Coordinate system: X = 0..100 (long axis), Y = 0..95 (short axis — amended PR-A4-a 2026-05-23 board grow). Mount holes: (5,5), (95,5), (5,90), (95,90) at 4 corners.

Zone allocation (PR-A4-b 2026-05-23 amendment for 100×95 board, P=12 FET pitch):

```
Y=82-95: TOP EDGE — FC connector + AUX header + USBLC6 ESD + BAT_V divider
Y=80-87: S5 OUTPUT-STRIP — 4× ferrites + C_OUT + TVS (B.Cu) + FB resistors + boot caps
Y=68-82: S5 SPINE POCKET — 4× buck ICs + LDO + supervisor + 4× inductors B.Cu
Y=47-80: CH1 NW + CH2 NE — 33mm tall channel quadrants (motor + 6 FETs + MCU + driver + INA + protection)
Y=24-46: S2 BULK CAPS row — 4× polymer caps at x=25/75 (+ Hall body envelope X=42-62 spine)
Y=20-58: S3 SUPERVISOR + HALL — central spine pocket
Y=15-47: CH3 SW + CH4 SE — 32mm tall channel quadrants
Y=14-19: S5 INPUT STRIP — 4× Schottky + eFuses + polyfuse
Y=0-13:  S1 BATTERY — XT30 + NTC + single-row 4× rev-pol FETs + TVS
```

Quadrants (PR-A4-b new zones):
- **NW** (X=5-39, Y=47-80): Channel 1 — motor pads x=5 at Y=54/66/78, 6 FETs at P=12 rows Y=54/66/78
- **NE** (X=61-95, Y=47-80): Channel 2 — motor pads x=95 mirror, X-mirror transform
- **SW** (X=5-39, Y=15-47): Channel 3 — motor pads x=5 at Y=17/29/41 (mirror y → 95-y)
- **SE** (X=61-95, Y=15-47): Channel 4 — motor pads x=95 mirror, XY-mirror transform
- **Central spine** (X=39-61, Y=0-85): power path (battery → bulk → supervisor → split) — widened 2026-05-22 master stage-3 amendment from X=42-58 (16mm) to X=39-61 (22mm) to fit ACS770ECB vertical Hall body (19.65mm wide at 0° rot) symmetrically. NW/NE/SW/SE quadrant inner edges shifted by 3mm; each channel still ~34mm wide, sufficient for MCU + 6 FETs + per-channel passives.

## 3. Subsystem I/O contracts

### S1: Battery input
- **Components**: XT30 connector, 2× MF72 5D25 NTC, 4× Infineon BSC014N06NS (rev-pol cluster), SMBJ33A TVS, polyfuse (if present)
- **Inputs**: +BATT_RAW, BATGND (from XT30 pins)
- **Outputs**: +BATT_FUSED, GND (post-NTC, post-rev-pol)
- **ALLOWED zone**: X=20-80, **Y=0-13** (PR-A4-b 2026-05-23 single-row revert; 4× rev-pol FETs in single linear row at y=10, electrically identical to 2×2; saves 7mm vertical for CH3/CH4 zones at 100×95 board)
- **FORBIDDEN zones** (PR-A4-b updated): all 4 channel zones (NW/NE Y=47-80, SW/SE Y=15-47); S5 spine pocket Y=68-82; S5 strips; S6 Y=82-95; S2 cap row Y=24-46; Hall spine X=39-61 Y=20-58
- **Adjacency**: outputs feed bulk caps directly above (Y=20-42 center)
- **Acceptance**: bbox-clean within subsystem, XT30 pad on board edge for soldering access

### S2: Bulk cap bank
- **Components**: 4× Panasonic EEHZS1V471P CBULK1-4 (470µF 35V polymer) + 8× ceramic decoupling (100nF + 10nF in parallel ×4)
- **Inputs**: +BATT_FUSED, GND
- **Outputs**: +VMOTOR (clean), GND
- **ALLOWED zone**: X=18-82, **Y=24-46** (PR-A4-b 2026-05-23 shifted +4mm for 100×95 board; C3/C4 stay at x=25/75 to clear NW/NE channel zone inner edges)
- **FORBIDDEN zones** (PR-A4-b updated): all 4 channel zones (NW X=5-39 Y=47-80; NE X=61-95 Y=47-80; SW X=5-39 Y=15-47; SE X=61-95 Y=15-47); S5 spine pocket Y=68-82; Hall body envelope X=42-62 Y=20-46; S1 battery zone Y=0-13; S6 top edge Y=82-95
- **Adjacency**: +VMOTOR output feeds Hall sensor primary directly above (Y=42-58 center)
- **Acceptance**: 4 caps in linear or 2×2 arrangement, ESR-minimizing trace length to FETs

### S3: Supervisor + Hall sensor
- **Components**: TPS3700 supervisor, ACS770ECB-200B Hall sensor, voltage dividers (R + R for OVP threshold), inrush delay cap
- **Inputs**: +VMOTOR, GND, +V3V3 (for supervisor logic)
- **Outputs**: OVUV_KILL_BUS (to 4-channel kill rails), BUS_CURR_OUT (analog to FC AUX), +VMOTOR_HOTSIDE (post-Hall) → to 4-channel split
- **ALLOWED zone**: X=39-61, Y=20-58 (unchanged from prior — Hall + supervisor in central spine; PR-A4-b 100×95 board keeps S3 at this position; A4-c may shift if Hall positioning needs adjustment for new S5 pocket position)
- **FORBIDDEN zones** (PR-A4-b updated): all 4 channel zones (NW/NE Y=47-80, SW/SE Y=15-47); S5 spine pocket Y=68-82 (reserved for S5 BEC); S6 top edge Y=82-95; S1/S2 zones
- **Adjacency**: Hall primary current pad 4 (north end) feeds from S2 bulk caps via B.Cu jumper R33 at (50, 25); pad 5 (south end) feeds out to 4-channel split via R34 at (50, 47) B.Cu (moved from (50, 65) per PR-A2). All 4 channels equidistant ~30mm from Hall center (symmetric loss budget per premium-ESC reference).
- **Acceptance**: Hall primary leads carry +VMOTOR with 3oz copper pour; supervisor divider accessible for test; vertical Hall orientation ensures channel-to-channel thermal symmetry

### S4: Channel template (instantiate × 4)
- **Components per channel**:
  - 1× AT32F421K8T7 MCU (LQFP-32)
  - 6× AOTL66912 MOSFETs (3 phases × high/low) symmetric around motor pad
  - 3× DRV8300 gate driver subsystems (one per phase)
  - 12× gate clamp zeners + 12× gate pulldown resistors (24 total per channel)
  - 9× local bypass caps (100nF+10nF+1nF × 3 phase nodes)
  - 3× phase TVS (33V on motor outputs)
  - 1× protection cluster: LM393 + TL431 + 74LVC1G08 + 1× LED + 1× NTC (per-channel current limit + OTP)
  - 3× current sense paths (shunt + INA186 + filter caps)
  - ~20 BEMF and PWM passives
- **Inputs**: +VMOTOR_HOTSIDE (from S3), GND, KILL_LOCAL_N (per-channel from supervisor OR-bus), DShot_CH_n (from FC), +V3V3 (MCU supply)
- **Outputs**: MOTOR_A/B/C_CH_n (to motor pad), TLM_CH_n (to FC telemetry), HW_FAULT_LED_K_CH_n (visible on board)
- **ALLOWED zone**: one channel quadrant (PR-A4-b 100×95 zones): NW X=5-39 Y=47-80 (33mm); NE X=61-95 Y=47-80; SW X=5-39 Y=15-47 (32mm); SE X=61-95 Y=15-47 — per channel index. Symmetric R6 motor-pad-anchored at P=12 FET pitch fits cleanly in these zones. **Channel passives MUST remain within parent channel quadrant (X-half + Y-half boundary) AND respect §S5 FORBIDDEN zones (especially spine pocket B.Cu)** — added A4-e amendment 2.
- **FORBIDDEN zones** (PR-A4-b updated): central spine X=39-61 (reserved for S2/S3/S5); other channels' quadrants; S6 top edge Y=82-95; S1 battery zone Y=0-13
- **Adjacency**: motor pad at outer edge of quadrant; MCU + gate drivers between motor pad and central spine; protection cluster between MCU and quadrant corner
- **Acceptance per channel**: bbox-clean within quadrant; per-channel D/S < 0.85 in all sub-cells; thermal sim T_J ≤ 100°C at 70A continuous + 100A 10s burst; per-MCU pin-side connectivity (playbook T8) verified for the channel's rotation

### S5: BEC subsystem
- **Components**: 5× buck regulators (TPS54560 × 4 for V5_FC, V5_PI5, V5_AI, V9_VTX1; + 1 more for V9_VTX2 or shared) + 1× LDO for V3V3 + LC filters per output + protection diodes + bias passives
- **Inputs**: +VMOTOR (from S3 output), GND
- **Outputs**: +V5_FC, +V5_PI5, +V5_AI, +V9_VTX1, +V9_VTX2, +V3V3, +V3V3A
- **ALLOWED zones** (PR-A4-b 2026-05-23 amended for 100×95 board — 4-zone distribution preserved, Y-coords shifted):
  - **Zone A** — Central spine pocket X=39-61, **Y=68-82** (shifted +10 from Y=58-72; 308 mm²): 4× buck ICs F.Cu + 4× inductors B.Cu + LDO + supervisor (B.Cu) + boot caps
  - **Zone B** — Bottom-edge S5 strip X=12-92, **Y=14-19** (unchanged Y; between S1 single-row and S2 cap row): input-side passives (4× Schottky D5-D8, 3× eFuses J7-J9, 1× polyfuse F1)
  - **Zone C** — Top-edge S5 strip X=20-90, **Y=80-87** (shifted +10 from Y=70-77; between spine pocket and S6 USBLC6 row): output-side passives (4× ferrites L6-L9, 4× C_OUT, 4× TVS B.Cu, 8× FB resistors, 4× boot caps)
  - **Zone D** — SW corner X=2-22, **Y=22-38** (unchanged Y; Buck 5 V9_VTX2 cluster) — far from V9_VTX1 per Sai isolation directive
- **FORBIDDEN zones** (PR-A4-b + A4-e amendment 2 2026-05-23):
  - All channel zones (NW/NE Y=47-80, SW/SE Y=15-47) except explicit Zone B/D strips above
  - S1 main body Y=0-13
  - S2 cap envelope Y=18.5..29.5 + Y=38.5..49.5 (post +4mm shift)
  - S3 supervisor cluster X=39-61 Y=42-58 + Hall body X=42-62 Y=20-46
  - S6 connector zone X≥20 Y≥82
  - **Channel passives FORBIDDEN in §S5 spine pocket B.Cu (X=38-62, Y=68-82)** — reserved exclusively for BEC R50-R76 cluster per A4-d emergency relocation. Mirror-instantiation of channel passives must check this zone.
- **Adjacency**: outputs feed FC connector + AUX header (above) + 4 MCU subsystems (per-channel V3V3)
- **Acceptance**: thermal separation from FET clusters (channel quadrants); bbox-clean; output trace ampacity for each rail. ROOT-CAUSE PREVENTION: spine pocket is reserved S5 territory; channels are forbidden zone for BEC.

### S6: FC connector + AUX header
- **Components**: FC connector (existing pin header), BM06B-SRSS-TB AUX 6-pin (Hall + NTC + spare GPIO + BEC outs), 4× protection-status LEDs (per-channel kill indicator), DShot TVS × 4, BAT_V divider
- **Inputs**: DShot_CH1-4 (from MCUs), TLM_CH1-4 (from MCUs), BUS_CURR_OUT (from S3 Hall), BAT_V (from S2 divider), +V5_FC (from S5)
- **Outputs**: (to FC and user)
- **ALLOWED zone**: top edge, **Y=82-95** (PR-A4-b shifted +10 from Y=72-85 for 100×95 board) (with ≥3mm clearance from H3/H4 mount holes at (5,90)/(95,90))
- **FORBIDDEN zones** (PR-A4-b updated): all channel zones; spine pocket Y=68-82; S5 top strip Y=80-87 (overlapping but on different layers); S1/S2/S3 zones
- **Acceptance**: bbox-clean; LEDs visible from top; FC pins accessible

### S7: Edge.Cuts + mount holes (already in setup_board.py)
- 100×85 outline + 4 corner mount holes — no new placement

## 4. Routing principle

Given subsystem I/O contracts, routing constraints flow naturally:
- Vertical spine (central column) carries +BATT → +VMOTOR → 4-channel split
- Horizontal channel-feeds (left + right edges) carry +VMOTOR to each quadrant
- Per-channel motor outputs route within quadrant to motor pad
- BEC outputs route from spine outward to MCUs (per-channel +V3V3 + AUX rails)
- FC signals route from FC connector down to MCUs via top of each quadrant
- All ground via plane (In1 + In5 8L stackup)
- VMOTOR via plane (In3)

Per-cluster D/S target ≤ 0.85 for each subsystem zone independently.

## 5. Placement sub-phase ordering

1. S1 battery input — Phase 4-place-battery-input (PR)
2. S2 bulk caps — Phase 4-place-bulk-caps (PR)
3. S3 supervisor + Hall — Phase 4-place-supervisor-hall (PR)
4. S4 channel template — Phase 4-place-channel-template (PR with 1 channel + per-channel thermal + per-cluster D/S)
5. S4 × 4 — Phase 4-place-channels-x4 (PR instantiating template at 4 corners)
6. S5 BEC — Phase 4-place-bec (PR)
7. S6 connectors — Phase 4-place-connectors (PR)
8. Phase 4-place-integrate — global verify + 3D render + master visual gate
9. Phase 4-via-stitching-v2 — bump VMOTOR vias to ≥360 (15+/FET)
10. Phase 4c-v2 — thermal sim on R6
11. Phase 5b-v2 — autoroute

Each sub-phase = one PR. Each PR carries forward bbox-check (locked rule) + 3D render visual gate (locked rule).

## 6. Acceptance gate (master visual + verification)

Every Phase 4-place-* PR must include:
- verify_placement.py output showing 0 same-layer bbox overlaps for the subsystem
- 3D render PNG (top + bottom) of current state of placement (use kicad-cli pcb render)
- Per-cluster D/S < 0.85 for the subsystem zone
- target.h md5 unchanged
- Updates only the components in this subsystem (no cross-subsystem moves)

## 7. References + rationale

- Premium ESC research 2026-05-22 (T-Motor F55A, BLITZ E80, Tekko32 Metal): MOSFET pattern is per-channel-symmetric around motor pad, not corner/center cluster. Bulk caps central. 15-25 thermal vias per MOSFET. Source: Oscar Liang reviews + iFlight/Holybro/Hobbywing spec sheets.
- [[reference-placement-bbox-overlap-bug]] — bbox-check now MANDATORY gate.
- [[reference-kinet2pcb-silent-drop]] — verify components present, not trust tool exit codes.
- Sai directive 2026-05-22: 'subsystem by subsystem with known I/O' — this doc is the operational mechanism.
