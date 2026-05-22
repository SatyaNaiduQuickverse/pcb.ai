# Phase 3b-detail — Silkscreen + small electrical gaps

Closes the 6 small gaps surfaced earlier per Sai's 2026-05-22 authorization +
master's pre-research:
1. Telemetry USART_TX pull-up (4×)
2. BOOT0 pull-down + emergency-DFU jumper pads (4×)
3. Motor pad strain-relief copper reinforcement (12 pads)
4. Conformal coating spec for PL1 (REQUIREMENTS doc)
5. Full silkscreen labels (124 gr_text labels)
6. Manufacturing fiducials + PCB rev marking + AOTL66912 thermal-pad orientation marker

---

## 1. AM32 USART_TX behavior verification (Rigor §5b)

Master's contract preamble stated "AM32's USART_TX is open-drain when in
telemetry mode". Worker grep-then-stated finding from `AM32/Mcu/f421/Src/serial_telemetry.c`
lines 27-34:

```c
gpio_init_struct.gpio_drive_strength = GPIO_DRIVE_STRENGTH_STRONGER;
gpio_init_struct.gpio_out_type = GPIO_OUTPUT_PUSH_PULL;   // NOT open-drain
gpio_init_struct.gpio_mode = GPIO_MODE_MUX;
gpio_init_struct.gpio_pins = GPIO_PINS_6;
gpio_init_struct.gpio_pull = GPIO_PULL_UP;                // Internal pull-up enabled
gpio_init(GPIOB, &gpio_init_struct);
```
And line 59:
```c
usart_single_line_halfduplex_select(USART1, TRUE);   // Half-duplex
```

**Finding:** PB6 (TLM) is push-pull + internal pull-up + half-duplex single-line.

URGENT escalated to master 2026-05-22. Worker recommendation: **add external
10kΩ pull-up anyway** (option a). Rationale:
- FPV reference designs (BLHeli32 boards, Open-4in1) consistently include
  external pull-up for noise immunity on the shared TX/RX line.
- Internal pull-up is weak (~40 kΩ); external 10kΩ stronger and more deterministic.
- Half-duplex line shared with FC's UART input — external pull-up reliably
  biases the line during signal transitions and idle periods.
- BOM cost: 4× 10kΩ 0402 ≈ $0.10 total.

**SKiDL update (this PR):** added `r_tlm_pu = Part("Device", "R", value="10K")`
between `tlm` (PB6) and `v3v3` in every channel instance — 4 resistors total.

If master adjudicates option (b) [skip external pull-up], revert is a single
SKiDL line removal + regenerate netlist. No silkscreen / placement change.

---

## 2. BOOT0 emergency-DFU access

**AT32F421 LQFP-32 pin 31 = BOOT0** (per `PHASE2A_PIN_MAP.md`).

### Phase 3a state (before this PR)
`mcu[31] += gnd` — BOOT0 hard-tied to GND. Boots from user Flash always.
No emergency-DFU access if firmware bricks itself.

### Phase 3b-detail update

```python
boot0_node = Net(f"BOOT0_CH{cn}")
mcu[31] += boot0_node
# Pull-down resistor — default = boot from flash
r_boot0_pd = Part("Device", "R", value="10K", footprint="Resistor_SMD:R_0402_1005Metric")
r_boot0_pd[1] += boot0_node
r_boot0_pd[2] += gnd
# 2-pin solder jumper for emergency DFU
boot_jumper = Part("Connector", "TestPoint", value=f"BOOT_JUMPER_CH{cn}",
                   footprint="TestPoint:TestPoint_Pad_D1.5mm")
boot_jumper[1] += boot0_node
boot_jumper_3v = Part("Connector", "TestPoint", value=f"BOOT_3V_CH{cn}",
                      footprint="TestPoint:TestPoint_Pad_D1.5mm")
boot_jumper_3v[1] += v3v3
```

**Operation:**
- Normal: 10kΩ pull-down holds BOOT0 low → boot from user Flash.
- Emergency: user bridges `BOOT_JUMPER_CHn` to `BOOT_3V_CHn` with solder blob
  → BOOT0 high at reset → boot from system bootloader → DFU flash via UART or USB.

4× instances (one per channel). Silkscreen "BOOT" applied next to jumper pads
(see §6 silkscreen layout).

---

## 3. Motor pad strain-relief

12× motor solder pads (3 per channel × 4 channels). Each pad is a
`TestPoint:TestPoint_Pad_D3.0mm` (D 3 mm) currently.

**Phase 3b-detail strain-relief geometry** (applied by
`hardware/kicad/scripts/apply_motor_strain_relief.py`):

```
                   ╲    │    ╱
                    ╲   │   ╱
                  ────  ⊙  ────
                    ╱   │   ╲
                   ╱    │    ╲
```

- **Outer ring**: 5 mm dia copper ring (gr_circle, width 0.4 mm) on F.Cu
- **4 radial spokes**: 0.6 mm wide F.Cu traces at 45°, 135°, 225°, 315°
  connecting the inner pad (D 3 mm) to the outer ring
- **Inner pad unchanged**: D 3 mm TestPoint pad (solder area preserved)

The spoke pattern at 45° offsets:
- Avoids the 0°/90° axes where the motor wire entry direction lies
- Provides 4-fold symmetric copper reinforcement
- Spoke thermal mass + outer ring solder-iron heat-sinking reduces strain on
  the solder joint during wire flexing + thermal cycling

Total per board: 12 outer rings + 48 spokes = 60 F.Cu copper primitives added.

---

## 4. Conformal coating (PL1, documented in REQUIREMENTS)

Added new `§reliability-spec — PL1` section above the HV60 spec:

```
| 1 | Conformal coating optional for indoor/clean FPV use;
      RECOMMENDED for sustained outdoor / wet-environment / dusty use.
      Standard MG Chemicals 4223 acrylic or equivalent (silicone variant 422B for higher-temp).
      Apply post-assembly + post-bench-test. Coating breaks if rework needed —
      apply only after final QA.
```

No PCB change — documentation only.

---

## 5. Locked silkscreen strings — verbatim (this PR applies)

### Channel IDs (4×)
- "CH1" near (8, 8)
- "CH2" near (82, 8)
- "CH3" near (8, 67)
- "CH4" near (82, 67)

### Motor pad labels (12×: A/B/C per channel)
- CH1 motors at (15, 2), (18, 2), (21, 2): "A" "B" "C" below pads on F.SilkS
- CH2 motors at (88, 15-21): "A" "B" "C" left of pads
- CH3 motors at (2, 55-61): "A" "B" "C" right of pads
- CH4 motors at (62-68, 73): "A" "B" "C" above pads

### Battery section
- "BAT+" near (10, 2.5) [above battery pad]
- "NTC ICL" near (17.5, 11.5)

### BEC solder pad labels (16 pads × polarity + rail tag)
Each pad pair has polarity ("+5V" / "+9V" / "+3V3" / "GND") + rail tag
("FC", "Pi5", "AI", "VTX1", "VTX2") near it. Per Phase 2e-REDO doc §3
verbatim spec.

### Indicator LEDs
- "PWR" next to LED_PWR (green, 28, 7)
- "REV!" next to LED_RPOL (red, 33, 7)

### FC connector pinout
- Header label: "FC CONNECTOR" above the JST
- Per-pin labels (in SKiDL J_FC pin order 1→8): "GND" "VBAT" "CURR" "TLM" "M4" "M3" "M2" "M1"
- **Note** for master: pin order matches `pcbai_fpv4in1_skidl.py` J_FC assignment,
  NOT the contract preamble's "D1 D2 D3 D4 TLM BAT+ GND +5V" order. URGENT
  raised; worker used SKiDL actual.

### SWD pad labels (8 pads × 4 channels = 32 labels)
"SWDIO" / "SWCLK" per pad.

### Mount holes
"M3" near each of 4 mount holes.

### PCB metadata
- "Rev A" at (80, 36) on F.SilkS
- "pcb.ai FPV4in1 v0" at (45, 4) on F.SilkS
- "[MFR-MARK]" placeholder at (80, 38.5) on F.SilkS

### AOTL66912 thermal-pad orientation marker (24 MOSFETs × 2 labels)
- Per-MOSFET "TP" + "^" arrow on B.SilkS at each MOSFET position
- Single "THERMAL PADS UP TO HEATSINK" label at (36, 60) on B.SilkS

### BEC zone boundary
- Dashed rectangle (8, 22) → (70, 42) on F.SilkS labeling the buck strip
- "BEC" label at (39, 23)

**Total: 124 gr_text labels + 24 gr_circle (12 fiducials × 2 layers) on .kicad_pcb.**

---

## 6. Fiducials

3× F.Cu + 3× B.Cu fiducials at clear board positions (avoiding component zones):

| Layer | Positions | Notes |
|---|---|---|
| F.Cu | (5, 30), (85, 18), (45, 72.5) | 0.5 mm radius copper dots + 1 mm radius mask opening |
| B.Cu | (5, 36), (85, 36), (45, 6) | Same |

Standard SMT pick-and-place reference. Per Phase 3b-detail contract.

---

## 7. Build verification

### SKiDL

```
$ python3 hardware/kicad/pcbai_fpv4in1_skidl.py
INFO: 0 errors found while generating netlist.
=== Phase 3c netlist export ===
output: /home/novatics64/escworker/pcb.ai/hardware/kicad/pcbai_fpv4in1.net
  components (comp blocks): 722
  file size: 355,982 bytes
```

722 component blocks (was 690 at Phase 4b-REDO2): +32 for:
- 4× BOOT0 pull-down resistors
- 4× BOOT_JUMPER TestPoint pads
- 4× BOOT_3V TestPoint pads
- 4× TLM pull-up resistors
- Total: 16 new Parts × 2 (SKiDL comp-block double-count) = 32

### target.h md5

`7a4549d27e0e83d3d6f1ffaf67527d24` pre + post. NO firmware impact. AM32 build
unchanged (no pin assignments altered).

### verify_placement.py

```
Total footprints: 364
  MCU ch1 (ref J16) @ (8.0, 8.0) rot=0.0° ✓
  MCU ch2 (ref J16) @ (82.0, 8.0) rot=90.0° ✓
  MCU ch3 (ref J31) @ (8.0, 67.0) rot=270.0° ✓
  MCU ch4 (ref J26) @ (82.0, 67.0) rot=180.0° ✓
  Mount holes (4) at corners [(5,5),(85,5),(5,70),(85,70)] ✓
  FC connector @ (40.0, 71.0) ✓ (top of board)
  Silkscreen labels: 124 gr_text + 24 gr_circle ✓
  Phase 3b silkscreen + motor strain-relief sentinels present ✓

All checks PASSED.
  - 364 footprints placed
  - 24 phase MOSFETs on expected 6×4 B.Cu grid
  - 4 MCUs with per-channel rotations preserved
  - 12 motor pads on board edges (with strain-relief copper)
  - 0 overlaps
  - 124 silkscreen text labels applied (Phase 3b-detail)
```

---

## 8. Files modified

| File | Status |
|---|---|
| `hardware/kicad/channel_skidl.py` | +4 BOOT0 pull-downs + 4 BOOT jumper pads + 4 TLM pull-ups per-channel |
| `hardware/kicad/pcbai_fpv4in1.net` | regenerated — 722 component blocks |
| `hardware/kicad/pcbai_fpv4in1.kicad_pcb` | full pipeline regen + silkscreen + strain-relief applied |
| `hardware/kicad/scripts/apply_silkscreen.py` | NEW — 124 gr_text labels (channel IDs, motor, BEC pads, FC, SWD, mount, metadata, thermal markers) + 6 fiducials + BEC boundary box |
| `hardware/kicad/scripts/apply_motor_strain_relief.py` | NEW — 12 outer rings + 48 spokes |
| `hardware/kicad/scripts/verify_placement.py` | silkscreen presence check added |
| `docs/PHASE3B_DETAIL_SILKSCREEN_GAPS.md` | NEW — this document |
| `docs/REQUIREMENTS.md` | §reliability-spec PL1 conformal coating + silkscreen + fiducials standards added |
| `docs/artifacts/phase3b-detail/placement_F_Cu_silk.svg` | NEW (1.37 MB; F.Cu + F.SilkS + Edge.Cuts) |
| `docs/artifacts/phase3b-detail/placement_B_Cu_silk.svg` | NEW (125 KB; B.Cu + B.SilkS + Edge.Cuts) |

---

## 9. Pass criteria (contract)

- [x] All locked silkscreen strings applied at correct locations (124 labels)
- [x] 6× fiducials present (3 F.Cu + 3 B.Cu)
- [x] 4× telemetry pull-ups added (pending master adjudication confirmation on push-pull approach)
- [x] 4× BOOT0 pull-downs + 4× BOOT0 jumper pad pairs in SKiDL
- [x] 12× motor pads have strain-relief copper relief (12 rings + 48 spokes)
- [x] REQUIREMENTS.md conformal-coating note added
- [x] AOTL66912 thermal-pad orientation marker visible on silkscreen (24 per-MOSFET + 1 zone label)
- [x] target.h md5 unchanged (`7a4549d...`)
- [x] SVGs updated
- [x] PR

---

## 10. Phase 5b handoff

After this merges, Phase 5b autoroute proceeds (per playbook trap T8: autoroute
is *confirmation*, not discovery). The placement gate is now fully complete:
- Connectivity-driven MCU rotation (Phase 4b-REDO)
- BEC absorption + 90×75 board (Phase 4b-REDO2)
- Solder-pad-first BEC outputs (Phase 2e-REDO)
- Small electrical gaps closed (this phase)
- All silkscreen + fiducials + metadata in place

Expected autoroute: ~100% routing reach. If plateau: re-placement, not router
tuning.

---

## 11. Rules check

- **Rigor §5b/§5c (grep-then-state — no recall):** AM32 USART_TX behavior
  verified from `Mcu/f421/Src/serial_telemetry.c` lines 27-34 directly.
  URGENT raised on master's contradictory preamble.
- **Playbook trap T7:** silkscreen polarity (+/-) on every external pad pair
  (12 BEC pad polarity labels + battery + motor pads).
- **Playbook trap T5 (cross-doc consistency):** silkscreen rail names match
  REQUIREMENTS.md §Power subsystem locked rail names (+V5_FC, +V5_PI5, etc.).
- **R17 (no loose threads):** all 6 gaps closed in this PR. The URGENT on
  USART_TX was raised + worker's recommendation executed pending adjudication
  (revert is trivial if master picks option b).
- **No-defer:** every silkscreen string was applied; every electrical addition
  is in SKiDL; thermal-pad markers visible; fiducials placed.
