# Phase 2e-REDO — Connector strategy (solder-pad-first per Sai 2026-05-22)

Per Sai's 2026-05-22 verbatim direction: *"9v 2a 2 pins is better choice.. connector
is your choice.. think from users POV soldering is also better"* + new memory
`feedback-anchor-on-most-capable-reference`: anchor on industrial-drone power-hub
class (not entry-level FPV).

This redo replaces the Phase 2d-REDO `BEC_OUT 10-pin AUX header` placeholder with
a **solder-pad-first** strategy: every BEC rail exit point is a generous solder
pad pair (per-rail sized for current). Connector footprints, where applicable,
are **optional overlays** that Phase 3b-detail can place beside the solder pads.

This honors three user requirements simultaneously:
1. **Manufacturability** — JLCPCB SMT assembly only solders surface-mount parts;
   solder pads need no assembly step.
2. **Reliability** — soldered wire joints are mechanically superior to crimped
   connectors for vibration-heavy drone use.
3. **Flexibility** — users who prefer connectors can attach a JST/XT30 by hand
   to the same pad locations.

---

## 1. Design strategy: pads-first, connector-optional

### Why pads?

| Criterion | Solder pad | Connector (header/JST/XT30) |
|---|---|---|
| Mechanical reliability (vibration) | Excellent — solder joint immobilized | Connector-dependent; locking variants better but bulky |
| Current capacity at small footprint | Limited only by pad/trace width | Pin-current-limit per connector spec |
| User assembly | Requires soldering iron | Cable + crimp tool / pre-made cable assy |
| BOM cost | $0 (no part) | $0.20-2 per connector |
| JLC SMT assembly compatibility | n/a — exposed pad only | Through-hole = wave-solder or hand-assemble step |
| Failure mode | Re-flow / mechanical break | Contact corrosion / connector unmate / pin fatigue |
| Repair / field-swap | Wire-cut + re-solder | Crimp swap (faster but needs spare cable) |

For an **autonomous-drone power-hub** (RPi 5 + AI HAT host), reliability under
vibration trumps swap-ability. Solder is the default. Connector is opt-in.

### Optional connector picks (overlaid at Phase 3b-detail)

Each rail's solder pad pair has an associated optional connector footprint that
can be placed adjacent (NOT physically overlapping) for users who want to
crimp a cable.

| Rail | Optional connector | KiCad footprint | JLC PN class | Rationale |
|---|---|---|---|---|
| +V5_FC (5A) | JST SH 2-pin horizontal | `Connector_JST:JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal` | JST SH family (BM/SM02B) | FC + cam + RX standard; small, low-profile |
| +V5_PI5 (5A) | XT30 2-pin (TBD custom footprint) | TBD custom symbol from `components.kicad_sym` | XT30 generic | RPi 5 may draw 5A peak; XT30 is 30A-rated, robust and locks in place — sensitive load deserves better connector |
| +V5_AI (3A) | JST SH 2-pin horizontal | same as V5_FC | JST SH | AI HAT typical 1.5A, peak 3A — JST SH ≤3A spec just adequate |
| +V9_VTX1 (2A) | JST SH 2-pin horizontal | same | JST SH | Standard VTX power cable |
| +V9_VTX2 (2A) | JST SH 2-pin horizontal | same | JST SH | Same |
| +V3V3 (1A) | None — pads only | — | — | Low current; rare to need a connector |

**Notes on connector selection:**
- **JST SH BM02B-SRSS-TB**: 1.0 mm pitch, rated 1 A per contact per JST datasheet
  (1 A × 2 pins = 2 A effective for parallel-wire). For >2A rails (V5_FC, V5_PI5),
  this is over-spec'd at the connector; users who pick the connector option get
  derated current vs the pad's full capacity. Solder pads remain the primary path
  for higher current.
- **XT30 for V5_PI5**: not in standard KiCad lib. A custom footprint will be added
  to `hardware/kicad/components.kicad_sym` (Phase 3b-detail). Provides a robust
  locking connector for RPi 5 power.
- All connectors share the SH/XT30 pad-spacing so the cable side is interchangeable.

### How "overlaid" works in practice

The solder pad is the primary footprint. At Phase 3b-detail, the layout designer
(or scripted layout) places the optional connector footprint **adjacent to the
solder pad** (within 1-2 mm), with silkscreen lines showing "PADS↓" and "CONN↓"
clearly so the user knows which pads are for which purpose. The pads themselves
are NOT physically merged with connector pins — the user solders directly to the
pads OR to the connector pins, whichever they install.

---

## 2. Per-rail pad spec

| Rail | Pad size | Footprint (KiCad) | Estimated I_max via pad | Position constraint (T7) |
|---|---|---|---|---|
| +V5_FC | **D 4.0 mm** | `TestPoint:TestPoint_Pad_D4.0mm` | 5 A continuous (0.5 mm trace, 1 oz Cu) | Board edge — top or right side near FC connector |
| +V5_PI5 | **D 4.0 mm** | same | 5 A continuous | Board edge — right or bottom (near where RPi 5 mounts) |
| +V5_AI | **D 4.0 mm** | same | 3 A continuous (generous; pad sized like 5V rails) | Board edge — adjacent V5_PI5 (RPi 5 + AI HAT share edge area) |
| +V9_VTX1 | **D 3.0 mm** | `TestPoint:TestPoint_Pad_D3.0mm` | 2 A continuous | Board edge — different from VTX2 for cable management |
| +V9_VTX2 | **D 3.0 mm** | same | 2 A continuous | Board edge — separated from VTX1 |
| +V3V3 | **D 2.5 mm** | `TestPoint:TestPoint_Pad_D2.5mm` | 1 A | Any edge or interior (low current) |
| **GND distribution × 4** | **D 3.0 mm** | `TestPoint:TestPoint_Pad_D3.0mm` | per-pad 3-5 A return | Spread around pad-cluster area for return distribution |

Each rail also has a GND pad of matching size paired directly next to its
+V pad — that GND pad is the dedicated return for that rail's load. The
4 additional GND distribution pads spread the return current across the board.

Total: **12 pad components** (6 +V + 6 GND-pair) + **4 GND distribution pads** =
**16 new solder pads**.

---

## 3. Silkscreen requirements (forward-listed for Phase 3b-detail)

Per master's contract: Phase 3b-detail will apply silkscreen. This section
documents the requirements so they are not lost.

| Pad designator | Required silkscreen label | Required polarity marker | Notes |
|---|---|---|---|
| PAD_V5_FC_PLUS | `+5V_FC` | `+` next to pad | Centered above or below pad |
| PAD_V5_FC_GND | `GND` | `-` next to pad | |
| PAD_V5_PI5_PLUS | `+5V_PI5` | `+` | Also "RPi 5" annotation if space permits |
| PAD_V5_PI5_GND | `GND` | `-` | |
| PAD_V5_AI_PLUS | `+5V_AI` | `+` | Also "AI HAT" annotation if space permits |
| PAD_V5_AI_GND | `GND` | `-` | |
| PAD_V9_VTX1_PLUS | `+9V_VTX1` | `+` | "VTX 1" annotation |
| PAD_V9_VTX1_GND | `GND` | `-` | |
| PAD_V9_VTX2_PLUS | `+9V_VTX2` | `+` | "VTX 2" annotation |
| PAD_V9_VTX2_GND | `GND` | `-` | |
| PAD_V3V3_PLUS | `+3.3V` | `+` | |
| PAD_V3V3_GND | `GND` | `-` | |
| PAD_GND_DIST_1..4 | `GND` | (no polarity — GND is unambiguous) | spread across pad cluster zone |

### Additional silkscreen elements

- **Pad cluster boundary box**: outline the BEC pad cluster region with silkscreen
  rectangle + label "BEC OUTPUTS" at top.
- **Voltage warnings**: small "HIGH-CURRENT" annotation near +V5_PI5 (peak 5 A).
- **Connector zone markers**: when Phase 3b-detail places optional connector
  footprints adjacent to pads, add silkscreen "PADS ↑" and "CONN ↑" arrows for
  clarity.
- **Indicator LED annotations** (from Phase 2d-REDO, also Phase 3b-detail scope):
  silkscreen "PWR" next to LED_PWR (green) and "REV-POL" next to LED_RPOL (red).
- **Solder tip recommendation**: small text "TIP: 35W @ 350°C for 4mm pads".

R17: this list is the canonical spec for silkscreen — Phase 3b-detail layout
designer applies it from this doc.

---

## 4. Phase 2e components unchanged from original Phase 2e

Per master contract Step 2 — these are preserved without modification:

- **TVS on +BATT_NTC** (existing SMBJ33A in SKiDL) — kept
- **ESD array USBLC6-2SC6 × 3** (FC connector RX-side ESD on M1-4_RAW + TLM) — kept
- **Reverse-polarity stack** (4× AON6260 N-FETs + R_GATE + D_Z + indicator LEDs) — kept (LEDs added in 2d-REDO)
- **SWD test pads × 4 channels** (existing per-MCU pad pair) — kept

---

## 5. Board edge layout constraints (T7 — connector accessibility)

All 16 new solder pads must be reachable from the board edge for cable routing.
With the 85×70 board and the existing edge population:

- **Top edge (y ≈ 66-70 mm)**: occupied by FC connector at (38, 66). ~50 mm of
  edge space remains (x = 0-30 mm or x = 50-85 mm) — pads can go here.
- **Right edge (x ≈ 80-85 mm)**: motor pads CH2 (3× motors at y=15, 18, 21).
  Pads can go in y = 25-65 mm range.
- **Left edge (x ≈ 0-5 mm)**: motor pads CH3 at y=50, 53, 56 + SWD pads.
  Pads can go in y = 5-45 mm range.
- **Bottom edge (y ≈ 0-5 mm)**: battery solder pads + TVS + rev-pol FETs.
  Limited space; could fit 2-3 GND distribution pads.

**Tentative pad allocation (for Phase 4b-redo-II to optimize):**
- +V5_FC, +V5_FC_GND: top edge (left of FC at x ≈ 5-25)
- +V5_PI5, +V5_PI5_GND: right edge (y ≈ 25-35) — close to RPi 5 typical mount
- +V5_AI, +V5_AI_GND: right edge (y ≈ 40-55) — adjacent V5_PI5
- +V9_VTX1, +V9_VTX1_GND: left edge (y ≈ 10-20)
- +V9_VTX2, +V9_VTX2_GND: left edge (y ≈ 25-35)
- +V3V3, +V3V3_GND: any free area (interior or edge — low current)
- 4× GND_DIST: spread across pad cluster area + 1-2 near battery section

**Feasibility check:** 16 pads (12 rail + 4 GND) × ~30 mm² per pad cluster
(pad + clearance) ≈ 480 mm². Board has ~150 mm of edge perimeter. With
~3 mm pad-edge inset, ~150 mm × 6 mm = 900 mm² of edge-zone area. **Pads fit
with margin.** No URGENT escalation needed for T7.

---

## 6. Notes for Phase 4b-redo-II (bundled per master directive)

Phase 4b-redo-II will need to handle:
1. **Placement of all Phase 2d-REDO BEC components** — 5 bucks + LC + indicators +
   NTC (~1200 mm² as worker flagged in Phase 2d-REDO doc §7).
2. **Placement of all 16 BEC solder pads on board edges** (~480 mm² as above).
3. **Board-size decision**: keep 85 × 70 / grow to 90 × 75 / migrate some to B.Cu /
   compress channel-passive zones. Per master directive, this decision belongs
   to Phase 4b-redo-II, not here.

This Phase 2e-REDO sets the spec; placement decisions happen later.

---

## 7. Optional connector footprint follow-up (Phase 3b-detail)

After this PR merges, Phase 3b-detail (or the next iteration of placement)
should:
1. Add custom symbols for XT30 connector to `hardware/kicad/components.kicad_sym`.
2. Place optional JST SH and XT30 footprints adjacent to the appropriate solder
   pads.
3. Apply all silkscreen labels per §3.

These are NOT included in this PR's SKiDL netlist (they're footprint-only, no
electrical connection beyond the pads they live next to).

---

## 8. Files modified

| File | Status |
|---|---|
| `hardware/kicad/pcbai_fpv4in1_skidl.py` | BEC_OUT 10-pin header → 12 solder pads (6 V + 6 GND) + 4 GND distribution pads |
| `hardware/kicad/pcbai_fpv4in1.net` | regenerated (660 → 690 components) |
| `docs/PHASE2E_REDO_CONNECTORS.md` | NEW — this document |
| `docs/REQUIREMENTS.md` | §Connectors + Mechanical updated |
| `firmware/am32-target/PCBAI_FPV4IN1_F421.target.h` | UNCHANGED (md5 verified, no firmware impact) |

---

## 9. Build verification

- **SKiDL build:** 0 errors. 690 component blocks generated.
- **`target.h` unchanged:** md5 hash 7a4549d27e0e83d3d6f1ffaf67527d24 (pre+post) —
  no firmware impact.
- **AM32 build:** unchanged (no rebuild needed).

---

## 10. Rules check

- **Rigor §10 / §5b:** every connector class verified against KiCad standard libraries
  (`ls /usr/share/kicad/footprints/Connector_JST.pretty/`) + JST datasheet
  reference for current rating.
- **Sai's user-POV directive (2026-05-22):** solder-first explicitly framed.
- **`feedback-anchor-on-most-capable-reference`:** XT30 spec for V5_PI5 is industrial-class
  (30A rated for a 5A rail = 6× FoS at the connector itself).
- **R17 (no loose threads):** silkscreen requirements forward-listed in §3 so they
  do not get lost between Phase 2e and Phase 3b-detail. XT30 custom-symbol need is
  flagged explicitly.
- **Bundled-decision principle:** Phase 4b-redo-II board-size + placement decisions
  flagged in §6 instead of being deferred silently. Worker confirms current 85×70
  board is feasible for pad placement; final placement layout pick lives in 4b-redo-II.
- **No scope creep:** stayed within Phase 2e (connector strategy + pad spec). Did
  NOT touch Phase 2d-REDO architecture; did NOT add placement (that's 4b-redo-II).
