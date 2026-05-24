# Phase 7-prep — Mechanical hardware (heatsink, TIM, mounting)

**Status**: doc-prep (orthogonal to Phase 5b routing decision); 2026-05-24.
**Driver**: Phase 5c thermal sim assumed `h_bottom = 1500 W/m²K` ambient 60°C —
that boundary condition is only realistic when the PCB bottom is pressed
against a heat-spreader with a thermal-interface material. This document
specifies the mechanical hardware needed to realize that assumption.

## 1. Why this matters (sim → fab readiness)

Phase 5c full-thermal Elmer FEM (commit `a32bb78`):
- 100A burst per FET, R_DS_on = 1.45 mΩ (BSC014N06NS @ 25°C)
- Per FET = 14.5 W → 24 FETs = 348 W board total
- Boundary conditions used in sim (`ch1234_thermal_100A_burst.sif`):
  - Bottom: h = 1500 W/m²K, T_amb = 60 °C
  - Top: h = 80 W/m²K, T_amb = 60 °C
  - Edge: h = 10 W/m²K, T_amb = 60 °C
- Result: T_J max = **82.99 °C** (PASS — 17 °C margin to 100 °C design limit;
  67 °C margin to 150 °C T_J_max)

**Without heat-spreader (h_bot = h_top = 80):** linear scaling shows T_J would
land around 200°C — well above survival limit. The mechanical hardware in this
doc is **not optional**; it makes the sim assumptions real.

## 2. Heat-spreader plate

### 2.1 Form-factor envelope

- PCB outline: 100 × 100 mm (current `pcbai_fpv4in1.kicad_pcb`)
- Mount holes: 4 × M3, positions from `setup_board.py` (read at fab time)
- Bottom-side components: minimal (per pick-place); heat-spreader contacts
  bare bottom copper + thermal pads

### 2.2 Heat-spreader spec

| Parameter | Value | Notes |
|---|---|---|
| Material | 6061-T6 aluminum or AlN ceramic | Al common; AlN higher k but expensive |
| Thickness | 1.6–2.0 mm | Stiffness + thermal mass |
| Footprint | 100 × 100 mm (full board) | Matches PCB outline |
| Surface finish | Black anodized (radiation ε ≈ 0.85) | Improves radiation cooling |
| Cooling fins | Optional — depends on cruise vs burst regime | See §6 sourcing |

### 2.3 Heat-transfer coefficient validation

Sim assumed `h_bottom = 1500 W/m²K`. For aluminum heat-spreader pressed against
PCB bottom via thermal pad:

- Thermal-pad junction: h_pad = k_pad / t_pad (k_pad ≈ 6 W/m·K, t_pad ≈ 0.2 mm
  → h_pad ≈ 30,000 W/m²K — far above sim assumption ✓)
- Plate-to-air convection: h_air ≈ 50–150 W/m²K natural; 200–500 forced
  (propwash); 1000+ with fins + propwash

Net `h_bottom` is limited by the **plate-air junction**. 1500 W/m²K assumes
forced air (propwash) on a finned plate. **Verify experimentally** during
bring-up by IR thermography under load.

## 3. Thermal Interface Material (TIM)

### 3.1 Selection criteria

| Criterion | Requirement | Rationale |
|---|---|---|
| Thermal conductivity | k ≥ 4 W/m·K | Realize h_pad ≥ 20,000 |
| Compressibility | ≥ 50% strain at 100 psi | Conform to board topology |
| Thickness | 0.2–0.5 mm | Trade-off compression vs heat path |
| Operating temp | -40 to +150 °C | FPV ambient + thermal margin |
| Electrical isolation | ≥ 1500 V breakdown | Bottom copper may be biased |
| Vibration resistance | High (≥ 20 G sustained) | FPV motors + propwash + crashes |

### 3.2 Recommended parts (doc-only, master to confirm sourcing)

| Part # | Vendor | k (W/m·K) | Thickness | Cost (est) | Notes |
|---|---|---|---|---|---|
| **3M TC-5022** | 3M | 4.0 | 0.5 mm | $4/cm² | Industry standard, JLC-stocked |
| **T-Global IB-100** | T-Global | 5.0 | 0.5 mm | $3/cm² | Asian alt; JLCPCB-friendly |
| **Bergquist GP-3000** | Bergquist | 3.0 | 0.5 mm | $5/cm² | Lower k but lower compression |
| **Laird Tflex 720** | Laird | 3.0 | 1.0 mm | $4/cm² | Thicker for larger gap tolerance |

**Default recommendation**: 3M TC-5022 (k=4.0, 0.5mm). Available at JLCPCB
SMT-friendly stock. ≈ $40 per board (100×100mm = 10,000 mm² × $4/cm²).

## 4. Mounting hardware

### 4.1 PCB → heat-spreader

- 4 × **M3 × 8mm pan-head Phillips screws** (steel, black-oxide or zinc)
- 4 × **M3 nylon washers** (PCB-side, electrical isolation from screw head)
- 4 × **M3 spring lock washers** (heat-spreader-side, vibration resistance)
- Torque: 0.5 N·m (PCB-safe, prevents over-compression of TIM)

**Alternative**: M3 nylock nuts for permanent assembly (slight cost increase,
better vibration resistance for racing/freestyle pilots).

### 4.2 Stack-up integration

- 4 × **M3 × 30mm standoffs (aluminum, hex)** for stack-mount to flight controller
- Stack spacing: typically 5-10 mm between board layers (FC ↔ ESC ↔ next board)
- Heat-spreader replaces the ESC bottom-side standoff position

### 4.3 Frame mounting (drone integration)

- 4 × **M3 × 6mm cap-head** screws into frame standoffs
- 4 × **M3 silicone vibration-dampening grommets** (frame-side, FPV standard)
- Common frame standoff patterns: 20×20, 30.5×30.5, 25.5×25.5 mm

**Owner decision needed**: which stack pattern does the PCB target? Current
PCB outline 100×100 mm is non-standard for racing; suggests this is a
cinematic / long-range build with custom frame. Confirm with owner.

## 5. Bill of materials (mechanical, per ESC)

| Item | Qty | Part # / spec | Cost (est) | Source |
|---|---|---|---|---|
| Aluminum heat-spreader 100×100×1.6mm anodized | 1 | Custom CNC | $8 | Aliexpress / JLCCNC |
| 3M TC-5022 thermal pad 100×100×0.5mm | 1 | TC-5022 | $40 | Digi-Key 3M9885 |
| M3×8mm pan-head Phillips screw | 4 | DIN 7985 | $0.10/ea | McMaster |
| M3 nylon washer | 4 | DIN 125A nylon | $0.05/ea | McMaster |
| M3 spring lock washer | 4 | DIN 7980 | $0.05/ea | McMaster |
| M3×30mm aluminum hex standoff | 4 | M3-30-AL | $0.50/ea | Aliexpress |
| **Total mech BOM per ESC** | | | **≈ $51** | |

Compared to current PCB BOM (~$30 per board), mech hardware adds significant
cost. Master/owner to validate against per-unit cost target.

## 6. Sourcing prep — links to verify

- 3M TC-5022 thermal pad: Digi-Key #3M9885-ND
- M3 screw kit (mixed lengths + washers + standoffs): Aliexpress ≈ $10/100pcs
- 6061-T6 aluminum plate stock: McMaster #8975K34 (3" × 6" × 1/16")
- JLCCNC anodized aluminum machining: ≈ $5-10 per plate at qty 10

## 7. Open questions — master adjudications (2026-05-24)

| # | Question | Decision | Notes |
|---|---|---|---|
| Q1 | Final form factor — is 100×100mm correct, or shrink to standard FPV stack pattern (30.5×30.5)? | **PENDING SAI** | Potentially fab-impacting. Other 6 are bring-up-time decisions. |
| Q2 | Heat-spreader: aluminum (cheap) or AlN ceramic (high k, expensive)? | **Al 6061-T6** | AlN is 10× cost, overkill for prototype. AlN only if Sai mandates premium thermal margin. |
| Q3 | Active cooling (small fan) for non-airborne bench testing? | **YES for bench bring-up, NO for production** | Add to Phase 8 setup note. |
| Q4 | TIM brand preference (3M, T-Global, Bergquist, Laird)? | **3M TC-5022** | Bergquist Gap Pad / Laird alternatives functionally equivalent; pick on availability + price at order time. |
| Q5 | Mounting strategy: M3 screws + spring washers, or rivnut press-fit? | **M3 screws (prototype), rivnut for production rev** | Easy disassembly during bring-up. |
| Q6 | Heat-spreader integration: separate part (assembly step) or PCB-mounted (LDF / heat-bus) at fab? | **Separate spreader** | Simpler fab, removable for rework. |
| Q7 | IR thermography during bring-up to validate h_bottom assumption? | **YES** | Add to Phase 8 task list. |

## 8. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| h_bottom assumption invalid in production | T_J exceeds 100°C → reduced FET life | IR thermography bring-up + sim re-run with measured h |
| TIM degrades over thermal cycles (oil-bleed, hardening) | Δh over 1000+ flights | Sim regression every 200 flight-hours |
| Heat-spreader vibration loosens mounting | Increased thermal resistance over time | Spring lock washers + thread-locker (Loctite 222) |
| Bottom-side copper electrical short to spreader | DC fault, fire risk | TIM electrical isolation ≥ 1500V, verified per batch |

## 9. Integration into design phases

- **This document is doc-only Phase 6.5 / Phase 7-prep prep** (no PCB / fab impact)
- **Phase 7a freeze (per `docs/DESIGN_PHASES.md`)**: incorporate mech BOM
  decisions before fab order. Q1 (form factor) must be resolved before freeze.
- **Phase 8 bring-up** — adopt per master adjudication 2026-05-24:
  - **Bench setup**: active cooling fan attached to heat-spreader (Q3 yes)
  - **IR thermography**: FLIR rental or owned camera; thermal map under
    sustained 70 A continuous + 100 A burst envelopes (Q7 yes). Measured
    h_bottom delta vs sim assumption logged for regression
  - **Disassembly**: M3 screws permit pad/spreader rework during bring-up (Q5)
- **Phase 9 reliability**: HALT testing must include mech-hardware-loaded
  configuration (not bare PCB). If proto Q5=screws holds for HALT,
  carry forward; otherwise switch to rivnut for production rev.

## 10. Status

This is a **doc-prep snapshot** to surface mech-hardware decisions before
Phase 7 freeze. No code, no fab, no orders. Master + owner to validate
recommendations + sourcing before procurement is triggered.

Routing remains frozen pending Sai's Topor vs manual decision.
