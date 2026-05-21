# Phase 3a — Main schematic sheet (FPV 4-in-1 PL1)

Per `DESIGN_PHASES.md` Phase 3, `CLAUDE.md` §6 (one sub-phase = one PR).

## Scope adjustment (transparency)

Master's contract specified "KiCad 9 S-expression .kicad_sch". A fully-
rendered visual KiCad schematic comparable to Open-4in1's 11 740-line
`4in1ESC.kicad_sch` is a multi-hour KiCad-GUI task. The worker session
runs headless (no GUI access).

Path taken (honest scope deviation, flagged for master review):

1. **KiCad project skeleton** committed: `pcbai_fpv4in1.kicad_pro`,
   `pcbai_fpv4in1.kicad_sch` (main, minimal valid), `channel.kicad_sch`
   (stub, populated at 3b), `components.kicad_sym` (custom symbols for
   parts not in KiCad standard libs). All files load in KiCad 9; ERC
   passes with 0 violations on both sheets.
2. **Canonical netlist specification** in `pcbai_fpv4in1_skidl.py` — a
   SKiDL Python file enumerating every main-sheet part + every net
   connection. Per `PCB_PLAYBOOK.md` §Toolchain, SKiDL "use netlist-only
   mode for anything real" — the design intent here is THE canonical
   source; the .kicad_sch file is the human-readable rendering target.
3. **This document** captures the full per-section netlist in tables
   below — exhaustive enough that the Phase 4 GUI rendering pass is
   purely visual placement+wiring against a frozen spec.

Master is asked to either (a) accept this scope (project skeleton + netlist
spec + PHASE3A doc) and proceed to Phase 3b with the same pattern, or
(b) instruct worker to spend the additional time hand-authoring the
visual S-expression schematic.

## Files committed

| File | Purpose | Status |
|---|---|---|
| `hardware/kicad/pcbai_fpv4in1.kicad_pro` | KiCad 9 project file | minimal valid; loads in KiCad |
| `hardware/kicad/pcbai_fpv4in1.kicad_sch` | Main schematic file | minimal valid skeleton; ERC 0 violations |
| `hardware/kicad/channel.kicad_sch` | Channel sub-sheet stub | empty per Phase 3a (populated at 3b) |
| `hardware/kicad/components.kicad_sym` | Custom symbols for non-stdlib parts (AON6260, DRV8300DRGER, INA186A3IDCKR, USBLC6-2SC6, LMR51420YDDCR, TLV76733DRVR, SMBJ33A, SM08B-SRSS-TB, AT32F421K8T7) | author-time skeletons; populated visually at Phase 4 |
| `hardware/kicad/pcbai_fpv4in1_skidl.py` | SKiDL netlist generator (canonical design source) | spec for Phase 4 visual rendering |
| `hardware/kicad/.gitignore` | KiCad transient/backup ignore rules | |

## Schematic structure (text diagram)

```
                           ┌──────────────────────────────────────────┐
                           │  Main sheet (pcbai_fpv4in1.kicad_sch)    │
                           │                                          │
   BATT_PAD                │   ┌──── TVS (SMBJ33A) ───── GND          │
       │   +BATT ──────────┼───┤                                       │
       │                   │   │                                       │
       │   BATGND ─────────┼───┤  Reverse-pol: 4× AON6260 N-FET ║      │
       │                   │   │     ║ S=BATGND  D=GND  G=GATE_RP     │
       └───────────────────┘   │     ║ R_GATE 10kΩ BATT→GATE_RP        │
                               │     ║ D_Z 12V GATE_RP→GND clamp        │
                               │                                       │
                               │   +VMOTOR = +BATT (after RP, high-side)
                               │   ║                                   │
                               │   ║   Bulk: 2× 470µF 63V to GND       │
                               │   ║                                   │
                               │   ║   ┌─── BUCK (LMR51420YDDCR) ──┐  │
                               │   ║   │ in: +VMOTOR, 10µF cap     │  │
                               │   ║   │ inductor 0.47µH (XRIM160) │  │
                               │   ║   │ FB divider 130k/24.9k     │  │
                               │   ║   │ out: +5V, 22µF cap        │  │
                               │   ║   └────────────────────────────┘  │
                               │                  ║                    │
                               │                  ║  ┌── LDO (TLV76733) ──┐ │
                               │                  ║  │ in: +5V, 1µF       │ │
                               │                  ║  │ out: +3V3, 1µF     │ │
                               │                  ║  └────────────────────┘ │
                               │                                       │
                               │   +3V3 ── ferrite (BLM03) ── +3V3A    │
                               │            (+3V3A: 1µF + 100nF to GND)│
                               │                                       │
                               │   FC connector (JST SM08B-SRSS-TB):   │
                               │     1=GND  2=VBAT_SENSE_OUT           │
                               │     3=CURR_OUT  4=TLM                 │
                               │     5=M4_RAW  6=M3_RAW                │
                               │     7=M2_RAW  8=M1_RAW                │
                               │                                       │
                               │   ESD 3× USBLC6-2SC6:                 │
                               │     #1: M1_RAW↔M1_CLEAN + M2_RAW↔M2_CLEAN│
                               │     #2: M3_RAW↔M3_CLEAN + M4_RAW↔M4_CLEAN│
                               │     #3: TLM↔TLM_CLEAN + ESD_SPARE     │
                               │                                       │
                               │   Power-good LED: +3V3 → 1kΩ → green LED → GND│
                               │                                       │
                               │   Hierarchical channel sub-sheets ×4: │
                               │     channel.kicad_sch instances (3c)  │
                               │     boundary nets: VMOTOR, +5V, +3V3, │
                               │       +3V3A, GND, M<n>_CLEAN (DShot   │
                               │       input), TLM_CLEAN, MOTOR_A/B/C_CH<n>,│
                               │       SWD_DIO_CH<n>, SWD_CLK_CH<n>    │
                               │                                       │
                               │   Motor solder pads: 12× 3.0 mm dia   │
                               │     (3 phases × 4 channels)           │
                               │   SWD pads: per-MCU × 4 (12 minimum)  │
                               └──────────────────────────────────────────┘
```

## Net list — global rails

| Net | Function | Source |
|---|---|---|
| `+BATT` | Battery positive raw (pre-protection) | Battery pad pin 1 |
| `BATGND` | Battery negative (pre-protection) | Battery pad pin 2 |
| `+VMOTOR` | Motor rail (post reverse-polarity, same as +BATT on high side; topology is low-side N-FET ideal-diode so +BATT passes through to MOSFETs unchanged) | Logical alias for +BATT |
| `+5V` | Buck output | LMR51420YDDCR pin OUT (via inductor SW node) |
| `+3V3` | Logic supply | TLV76733DRVR pin OUT |
| `+3V3A` | Analog supply (post-ferrite from +3V3) | BLM03 ferrite output node |
| `GND` | System ground (downstream of reverse-pol FETs) | Drain pins of 4× reverse-pol FETs |

## Net list — power input subsystem

| Designator | Symbol | Value | Connections | Source |
|---|---|---|---|---|
| `J_BATT` | Conn_01x02 | battery pads | pin 1 = +BATT, pin 2 = BATGND | new |
| `D_TVS1` | D_TVS | SMBJ33A | cathode=GND, anode=+BATT | Phase 2e |
| `R_GATE` | R | 10 kΩ 0603 | +BATT ↔ GATE_RP | new |
| `D_Z1` | D_Zener | 12 V 0.5 W SOD-323 | GATE_RP ↔ GND | new |
| `Q_RP1..4` | Q_NMOS (AON6260) | 4× DFN5x6 | each: G=GATE_RP, S=BATGND, D=GND | Phase 2e |
| `C_BULK1` | C_Polarized | 470 µF 63 V SMD radial | +VMOTOR ↔ GND | Phase 2d |
| `C_BULK2` | C_Polarized | 470 µF 63 V SMD radial | +VMOTOR ↔ GND | Phase 2d |

## Net list — BEC subsystem

### Buck (LMR51420YDDCR, +VMOTOR → +5V)

| Designator | Symbol | Value | Connections | Source |
|---|---|---|---|---|
| `U_BUCK` | LMR51420YDDCR (functional stand-in: TPS563200DDC) | SOT-23-6 | VIN=+VMOTOR, EN=+VMOTOR, GND=GND, SW=BUCK_SW, BST=BUCK_BST, FB=BUCK_FB | Phase 2d |
| `C_BUCK_IN` | C | 10 µF 25V 0805 X7R | +VMOTOR ↔ GND | Phase 2d (C440198) |
| `C_BUCK_OUT` | C | 22 µF 0603 X5R | +5V ↔ GND | Phase 2d (C2762594) |
| `L_BUCK` | L | 0.47 µH (XRIM160808SR47MBCD) | BUCK_SW ↔ +5V | Phase 2d (C48391583) |
| `C_BST` | C | 100 nF 0402 | BUCK_BST ↔ BUCK_SW | Phase 2d |
| `R_FB_TOP` | R | 130 kΩ 0402 | +5V ↔ BUCK_FB | derived (V_FB ≈ 0.8 V, V_OUT = 5.0 V → ratio 5.25) |
| `R_FB_BOT` | R | 24.9 kΩ 0402 | BUCK_FB ↔ GND | derived |

### LDO (TLV76733DRVR, +5V → +3V3)

| Designator | Symbol | Value | Connections | Source |
|---|---|---|---|---|
| `U_LDO` | TLV76733DRVR (functional stand-in: AP2127K-3.3) | WSON-6 | IN=+5V, EN=+5V (always-on), GND=GND, OUT=+3V3 | Phase 2d |
| `C_LDO_IN` | C | 1 µF 0402 X7R | +5V ↔ GND | Phase 2d |
| `C_LDO_OUT` | C | 1 µF 0402 X7R | +3V3 ↔ GND | Phase 2d |
| `FB_VDDA` | L (ferrite bead) | 120 Ω @ 100 MHz 0201 (BLM03PX121SN1D) | +3V3 ↔ +3V3A | Phase 2d (C525479) |
| `C_VDDA_1u` | C | 1 µF 0402 X7R | +3V3A ↔ GND | Phase 2d |
| `C_VDDA_100n` | C | 100 nF 0402 X7R | +3V3A ↔ GND | Phase 2d |

## Net list — FC connector + ESD

### FC connector (J_FC: JST SM08B-SRSS-TB)

| Pin | Net | Function |
|---|---|---|
| 1 | GND | Signal + battery return |
| 2 | VBAT_SENSE_OUT | Battery voltage divider out → FC analog input (Phase 4 GUI: add divider) |
| 3 | CURR_OUT | Current-sense aggregate out → FC analog (Phase 4 GUI: aggregate from channel CSAs) |
| 4 | TLM | Telemetry bidirectional (single-line half-duplex) |
| 5 | M4_RAW | DShot input for channel 4 |
| 6 | M3_RAW | DShot input for channel 3 |
| 7 | M2_RAW | DShot input for channel 2 |
| 8 | M1_RAW | DShot input for channel 1 |

### ESD arrays (3× USBLC6-2SC6)

| Designator | Pin 1 (I/O1) | Pin 4 (I/O2) | Notes |
|---|---|---|---|
| `U_ESD1` | M1_RAW | M2_RAW | shunt-to-GND ESD on M1, M2 |
| `U_ESD2` | M3_RAW | M4_RAW | shunt-to-GND ESD on M3, M4 |
| `U_ESD3` | TLM | ESD_SPARE | shunt-to-GND ESD on TLM + spare for future expansion |

Each USBLC6-2SC6: pin 2 = GND, pin 3 = Vbus = +5V (the chip's supply tap), pin 5 = GND. Per ST datasheet C_io max 3.5 pF, IEC ±15 kV.

Net equivalence: `M<n>_CLEAN` = `M<n>_RAW` post-ESD (the device is shunt-only on the data line). At Phase 4 GUI the trace routes through the device's data pins; the Phase 3a netlist treats them as logically merged.

## Net list — status LED

| Designator | Symbol | Value | Connections |
|---|---|---|---|
| `LED_PG` | LED | 0603 green | A = LED_PG_NODE, K = GND |
| `R_LED_PG` | R | 1 kΩ 0402 | +3V3 ↔ LED_PG_NODE |

I = (3.3 V − 2.1 V LED V_F) / 1 kΩ = ~1.2 mA → adequate visibility, low power.

## Hierarchical sub-sheet boundary nets (per channel)

Phase 3a declares these; Phase 3b populates `channel.kicad_sch`; Phase 3c instantiates the channel sheet 4× and wires each instance.

| Net (per channel `n=1..4`) | Direction at boundary | Function |
|---|---|---|
| `+VMOTOR` | in | Motor power input |
| `+5V` | in | Gate driver supply |
| `+3V3` | in | MCU digital supply |
| `+3V3A` | in | MCU analog supply |
| `GND` | in/out | System ground |
| `M<n>_CLEAN` | in | DShot input to MCU |
| `TLM_CLEAN` | in/out | Shared telemetry bus (4 channels share; AM32 BLHeli-passthrough convention) |
| `MOTOR_A_CH<n>` | out | Phase A motor pad |
| `MOTOR_B_CH<n>` | out | Phase B motor pad |
| `MOTOR_C_CH<n>` | out | Phase C motor pad |
| `SWD_DIO_CH<n>` | bidirectional | SWD data (PA13 of channel `n` MCU) |
| `SWD_CLK_CH<n>` | in | SWD clock (PA14 of channel `n` MCU) |

## Motor + SWD test pad designators

| Designator pattern | Per channel | Total | Footprint | Connections |
|---|---|---|---|---|
| `MOTOR_<A/B/C>_CH<n>` | 3 | 12 | TestPoint:TestPoint_Pad_D3.0mm | Net `MOTOR_<phase>_CH<n>` |
| `SWDIO_CH<n>` | 1 | 4 | TestPoint:TestPoint_Pad_D1.0mm | Net `SWD_DIO_CH<n>` |
| `SWCLK_CH<n>` | 1 | 4 | TestPoint:TestPoint_Pad_D1.0mm | Net `SWD_CLK_CH<n>` |

## ERC verification

```
$ kicad-cli sch erc --output /tmp/erc_3a_final.json --format json \
            hardware/kicad/pcbai_fpv4in1.kicad_sch
Checking for off grid pins and wires...
Checking for labels on more than one wire...
Checking for undefined netclasses...
Found 0 violations
```

ERC PASSES on both main and channel schematic skeletons with 0 violations.

**Caveat per the scope adjustment**: ERC verifies the .kicad_sch file format
+ structure, not the netlist intent in `pcbai_fpv4in1_skidl.py`. The
canonical netlist correctness lives in the SKiDL spec and the tables above.

## Per-part designator → Phase 2 BOM cross-reference

Every part in the main sheet traces back to a Phase 2 sub-phase decision:

| Part / family | Phase | PR# | JLC C# (where applicable) |
|---|---|---|---|
| AON6260 (reverse-pol × 4) | 2b | #4 | n/a — AOS-original; hand-solder per supply note |
| 470 µF 63 V bulk caps | 2d | #6 | criteria-locked; specific C# at Phase 3 GUI |
| LMR51420YDDCR buck | 2d | #6 | C7296200 |
| 0.47 µH inductor (XRIM160808SR47MBCD) | 2d | #6 | C48391583 |
| TLV76733DRVR LDO | 2d | #6 | C2848334 |
| BLM03PX121SN1D ferrite bead | 2d | #6 | C525479 |
| 10 µF 0805 X5R | 2d | #6 | C440198 |
| 22 µF 0603 X5R | 2d | #6 | C2762594 |
| 100 nF 0402 X7R | 2d | #6 | C307331 |
| SMBJ33A TVS | 2e | #7 | multi-vendor (C710242/C78419/etc); pick at Phase 3 |
| JST SM08B-SRSS-TB | 2e | #7 | C160407 |
| USBLC6-2SC6 ESD × 3 | 2e | #7 | C7519 |
| Status LED green + 1 kΩ R | 2e | #7 | commodity Basic-tier |

## License attribution

Open-4in1-AM32-ESC (CERN-OHL-S licensed at `/tmp/OpenESC_20X20/`) was **studied
for structure only**. No schematic content was copy-pasted into our schematic.
- Verified C-numbers against their `schematic_analysis.json` BOM where parts
  matched our criteria (LMR51420YDDCR, TLV76733DRVR, ceramic decoupling).
- Topology decisions (low-side N-FET reverse-polarity, 4-in-1 single-MCU-per-
  channel architecture, 6-layer stack-up) were independently derived from
  master's contracts and Phase 2 adjudications.
- The actual schematic files (`pcbai_fpv4in1.kicad_sch`, `channel.kicad_sch`,
  `components.kicad_sym`, `pcbai_fpv4in1_skidl.py`) are our own work, free of
  CERN-OHL-S derivative-licensing obligation.

## Phase 3a pass criteria check

- [x] KiCad project skeleton at `hardware/kicad/`: `.kicad_pro` + 2× `.kicad_sch` + `components.kicad_sym` + `.gitignore`. All files load in KiCad 9.
- [x] Main sheet captures every main-sheet part (full inventory in net-list tables above + SKiDL spec file). **Visual placement deferred to Phase 4 GUI** — flagged scope.
- [x] Global power symbols defined (+BATT, +VMOTOR, +5V, +3V3, +3V3A, GND).
- [x] 4× hierarchical channel boundary nets declared (`MOTOR_<phase>_CH<n>`, `SWD_DIO_CH<n>`, `SWD_CLK_CH<n>`, etc.). Actual sheet INSTANCE blocks deferred to Phase 3c per the contract (channel sheet doesn't exist yet at 3a).
- [x] ERC 0 violations on main + channel skeleton files.
- [x] PHASE3A doc + REQUIREMENTS.md update.
- [x] One PR.

## Items flagged for next sub-phases

| Item | Closes at | Why |
|---|---|---|
| Visual placement of all main-sheet symbols | Phase 4 (placement) | Requires KiCad GUI |
| Channel sub-sheet contents (MCU + driver + 6 FETs + 3 shunts + 3 CSAs + decoupling) | Phase 3b | Master's split |
| Hierarchical sheet INSTANCES wiring | Phase 3c | After channel sheet exists |
| VBAT voltage divider for FC pin 2 (VBAT_SENSE_OUT) | Phase 3a→Phase 4 GUI | Add 2-resistor divider scaling +BATT (25.2 V max) to 3.3 V at FC ADC |
| CURR_OUT aggregate from per-channel CSAs | Phase 3c | Sum-and-scale from each channel's CSA outputs |
| Symbol pin-by-pin verification: LMR51420 (used TPS563200 stand-in), TLV76733 (used AP2127K-3.3 stand-in), USBLC6-2SC6, DRV8300DRGER, INA186A3IDCKR, AON6260 | Phase 4 GUI | KiCad GUI to author proper symbols against datasheet pin tables |
| Exact FC connector pin order verification vs Open-4in1's actual netlist | Phase 4 GUI | Open-4in1's net labels (M1/M2/M3/M4/CURR/TLM/VBAT/GND) confirmed; assignment to JST pins 1-8 is per-vendor convention |
