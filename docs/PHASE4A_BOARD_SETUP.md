# Phase 4a — Board setup (footprint typo fixes + Edge.Cuts + 6-layer stack-up)

Per master's Phase 4a contract (2026-05-22). Phase 4 split into 3 sub-phases:
- 4a (this PR): board setup
- 4b: scripted placement per Phase 2.5 sketch
- 4c: placement-validated thermal sim (closes Phase 2b gap)

## Footprint typo fixes (5 of 5 resolved)

Per Phase 3c PR description, 5 footprints had name typos against KiCad 9 std-lib. Fixed in SKiDL source per Rigor §10 (every name verified against actual `ls /usr/share/kicad/footprints/*.pretty`).

| Original (Phase 3c) | Fixed (Phase 4a) | Where fixed |
|---|---|---|
| `Inductor_SMD:L_1608_0603Metric` | `Inductor_SMD:L_0603_1608Metric` | axis-order swap; KiCad uses imperial-then-metric order |
| `Package_TO_SOT_SMD:SC-70-6_Handsoldering` | `Package_TO_SOT_SMD:SOT-363_SC-70-6` | KiCad's full name (SOT-363 prefix is the JEDEC alias for SC-70) |
| `Connector:TerminalBlock_Phoenix_MPT-2.54mm_1x02_P2.54mm_Horizontal` | `Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical` | KiCad has no Phoenix MPT 2.54mm variant; switched to a simpler 2-pin pad pattern for the BATT solder pads |
| `Package_DFN_QFN:VQFN-24_4x4mm_P0.5mm_EP2.6x2.6mm` | `Package_DFN_QFN:HVQFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm` | KiCad uses HVQFN prefix + `-1EP` suffix |
| `Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP0.9x1.6mm` | `Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm` | EP dimension was off by 0.1 mm (KiCad has EP1x1.6 not EP0.9x1.6) |

**Result**: kinet2pcb re-run shows **0 missing footprints** → all 249/249 footprints resolved. ✓

Files modified:
- `hardware/kicad/pcbai_fpv4in1_skidl.py` — battery pad, inductor, ESD/LDO/buck footprints
- `hardware/kicad/channel_skidl.py` — DRV8300 (HVQFN-24) + INA186 (SOT-363/SC-70-6) per-channel footprints

## Edge.Cuts outline + mounting holes

Per `REQUIREMENTS.md` §Mechanical (Phase 2.5 lock):

| Item | Value |
|---|---|
| Board outline | 50.0 × 50.0 mm square, drawn as 4× `gr_line` on `Edge.Cuts` layer, 0.05 mm stroke |
| Mounting pattern | 4 × M3 holes on 40.0 × 40.0 mm Betaflight stack pattern |
| Hole positions (from board origin 0,0) | (5, 5), (45, 5), (5, 45), (45, 45) mm |
| Hole diameter | 3.2 mm (M3 clearance, no thread) |
| Pad size | 6.0 mm dia (~3× hole diameter for solder mask + stress relief) |
| Footprint used | `MountingHole:MountingHole_3.2mm_M3` (with thru-hole pad on `*.Cu` + `*.Mask`) |

Added by `hardware/kicad/setup_board.py` (committed in this PR for reproducibility).

## 6-layer stack-up

Per `PCB_PLAYBOOK.md` §Routing + master's Phase 4a function assignment:

| Layer | Function | Notes |
|---|---|---|
| F.Cu | Signal (signal-side components) | MCUs, gate drivers, CSAs, decoupling, LEDs, FC connector, motor pads, SWD |
| In1.Cu | Power plane: +VMOTOR distribution | Solid pour; routes battery to MOSFET high-side drains; high-current path |
| In2.Cu | Ground plane | Solid pour; primary signal return + thermal spreading |
| In3.Cu | Ground plane | Solid pour; redundant for return-path integrity per Playbook §Routing |
| In4.Cu | Split power: +5V / +3V3 | Solid-ish pour with optional split for the two BEC outputs |
| B.Cu | Signal (power-side components) | 24+4 MOSFETs, 12 shunts, 2 bulk caps, TVS, buck inductor, heatsink interface |

JLC 6-layer standard stack-up will be the official thickness profile at Phase 5 routing (when impedance-controlled traces matter). For Phase 4a: layer function is locked; thickness profile is JLC default (1.6 mm total, 1-oz outer, 0.5-oz inner).

**Layer indices in the .kicad_pcb file** (KiCad std):
```
(0 "F.Cu" signal)
(1 "In1.Cu" power)
(2 "In2.Cu" power)
(3 "In3.Cu" power)
(4 "In4.Cu" power)
(31 "B.Cu" signal)
```

The `setup_board.py` script applies these changes idempotently to the kinet2pcb output.

## Verification

### kinet2pcb consumption (0 unresolved footprints)

```
$ kinet2pcb -i pcbai_fpv4in1.net -o pcbai_fpv4in1.kicad_pcb -w \
            -l <13 KiCad footprint libraries including Connector_PinHeader_2.54mm>
(no "Unable to find footprint" warnings)
```

249/249 footprints resolved. ✓

### kicad-cli pcb export smoke test

```
$ kicad-cli pcb export svg --output /tmp/pcb_4a_test.svg \
            --layers "F.Cu,B.Cu,Edge.Cuts" pcbai_fpv4in1.kicad_pcb
Plotted to '/tmp/pcb_4a_test.svg'.
Done.
```

.kicad_pcb file loads cleanly in KiCad 9 via the CLI. Edge.Cuts outline + mounting holes render in the SVG. 462 KB output. ✓

### File sizes

| File | Phase 3c | Phase 4a | Change |
|---|---|---|---|
| `pcbai_fpv4in1.kicad_pcb` | 992 KB | 1.12 MB | +130 KB (layer stack expansion + Edge.Cuts + 4× mount holes) |
| `pcbai_fpv4in1.net` | 254 KB | 254 KB | unchanged (netlist regenerated with footprint fixes but same component count) |

## Phase 4b handoff

`hardware/kicad/pcbai_fpv4in1.kicad_pcb` is now:
- 249/249 footprints resolved
- 6-layer stack-up locked per `PCB_PLAYBOOK.md` §Routing
- Edge.Cuts outline + 4× M3 mounting holes in place
- All footprints currently at origin (0, 0) per kinet2pcb default — **Phase 4b places them per Phase 2.5 sketch**

Phase 4b sub-phases (per master's Phase 4 split):
- 4b: scripted placement via Python pcbnew API or pcb-tools — position MOSFETs in 6×4 grid on B.Cu, MCUs in 2×2 on F.Cu, etc., per `sims/phase2_5_fit/placement_*.png` reference
- 4c: real Elmer thermal sim with placement + heatsink + Envelope 2 prop-wash → must hit T_J ≤ 100 °C to gate Phase 5 routing

## Rules check

Clean. Rigor §10: every footprint name verified against `ls /usr/share/kicad/footprints/*.pretty` output, no recall. R3 (no invented specifics): KiCad's `MountingHole_3.2mm_M3` is the actual footprint name; dimensions cite Phase 2.5 + `REQUIREMENTS.md` §Mechanical lock. R17 (no loose threads): 5/5 typos fixed; 0 missing footprints remain.
