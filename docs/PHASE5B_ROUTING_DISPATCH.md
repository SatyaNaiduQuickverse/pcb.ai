# Phase 5b Routing Dispatch

Per master Task #80 + [[feedback-routing-procedures-gap]]: routing is
subsystem-aware and symmetry-preserving, not bulk autoroute.

## Routing order

Per-subsystem routing dispatch order — chosen to minimize cross-PR
contention (internal subsystem routes precede inter-subsystem bus
distribution):

| # | PR | Subsystem | Internal nets to route | Inter-subsystem buses (exempt; routed in #82) |
|---|----|-----------|------------------------|------------------------------------------------|
| 1 | PR-S1-route | Battery input | VMOTOR XT30→bulk caps; BATGND XT30→Q1-Q4 sources; GATE_RP R3→Q gates; D2 Zener clamp | +VMOTOR distribution (handled in #82) |
| 2 | PR-S2-route | Bulk caps | C1/C2/C3/C4 internal VMOTOR + GND stitching (planes; mostly zone-fill) | +VMOTOR (plane); GND (plane) |
| 3 | PR-S3-route | Supervisor + Hall | HALL_VCC R30→C42/C43→U1 pad 1; HALL_VOUT_RAW U1.3→R31/R32 divider→MCU ADC; OVUV_N divider R19/R20→J11 TPS3700; PG_VMOTOR R21→J11; R33/R34 0Ω VMOTOR bridges | (handled in #82) |
| 4 | PR-S5-route | BEC subsystem | Per-buck: VIN→J input pin; SW→inductor→catch diode→C_OUT; FB R-divider→FB pin; bootstrap cap pad-to-pad; ferrite→C_OUT post-filter; TVS→output | +V5/+V9 rails (handled in #82); +VMOTOR plane (#82); GND plane (#82) |
| 5 | PR-S6-route | Connectors | J14 FC: DSHOT/TLM/+V5/+3V3/GND/M1-4 raw motor sense; J12 AUX header; J15/J16/J17 USBLC6 ESD; D3/D4 LED limit-R; R36/R37/C49 VBAT divider | +V5_FC, +V9_VTX1, +V3V3 to MCU (#82) |
| 6 | PR-CH1-route | Channel 1 (NW) | DRV J19→gate-R→FET Q5-Q10 gates; FET drains→motor pads TP19-21; FET sources→shunt R56/R57/R58→INA J20/J21/J22; INA outputs CSA_*→MCU ADC; MCU J18 supply/decoupling; per-channel kill rail; TL431 U2/U3/U4 protection cluster | (handled in #82) |
| 7 | PR-CH2/3/4-route | Channel 2/3/4 (mirrored) | `route_mirror_ch1_to_ch234.py all` — propagates CH1 routes via X-mirror, 180°-rot, Y-mirror | (handled in #82) |
| 8 | PR-routing-final | Inter-subsystem | VMOTOR plane stitching; +V5 distribution; +3V3 + V3V3A distribution; GND plane fills (In1/In5); full DRC | All buses + plane fills |

## Per-PR gate

Each routing PR MUST:
- Run `python3 hardware/kicad/scripts/audit_routing.py hardware/kicad/pcbai_fpv4in1.kicad_pcb`
- All 6 checks PASS, OR document specific spec deviations
- Visual diff render (top + bottom) showing new routes overlaid on placement
- Per-channel PR (#7): run `route_mirror_ch1_to_ch234.py all` after CH1 complete; verify_mirror reports 100% match before commit

## Symmetry tooling

`hardware/kicad/scripts/route_mirror_ch1_to_ch234.py` (Task #80) propagates CH1 routes to CH2/CH3/CH4 via:
- `CH2 = mirror_X(50)`: `(x, y) → (100-x, y)`
- `CH3 = 180°-rot(50, 50)`: `(x, y) → (100-x, 100-y)`
- `CH4 = mirror_Y(50)`: `(x, y) → (x, 100-y)`

Per-track and per-via copy preserves width, drill, diameter, layer.
Net rename: `_CH1` suffix → `_CH2/3/4`. New nets auto-created if absent.

`verify_mirror()` post-mirror cross-check: every CH1 segment must have a
matching CH2/3/4 segment at the transformed coordinates (tolerance 0.01mm).

## Net-class assignments (used by audit_routing.py check_track_width)

| Net pattern | Min width (mm) | Layer hint |
|-------------|---------------:|------------|
| `+VMOTOR`, `VMOTOR_CH`, `VMOTOR_HALL_*` | 1.0 | In3.Cu plane primary + F.Cu/B.Cu thick traces |
| `MOTOR_X_CHn` | 1.0 | F.Cu (FET drain→TP); B.Cu (FET source→shunt) |
| `SHUNT_*` | 1.0 | F.Cu |
| `BATGND` | 1.0 | Plane + traces |
| `+V5_*`, `+V9_*`, `V_BUCK*_OUT` | 0.3 | F.Cu/B.Cu |
| `+3V3`, `V3V3A` | 0.25 | F.Cu/B.Cu |
| `HALL_VCC_5V` | 0.3 | F.Cu (short) |
| Signals (`PWM_*`, `GLA*`, `GHA*`, `BEMF_*`, `CSA_*`, `NRST_*`, `BOOT0_*`, etc) | 0.15 | F.Cu/Inner signal layers In2/In4/In6 |
| `GND` | (plane) | In1.Cu, In5.Cu — zone fill |

## Deferred to Phase 6

- Full plane flood-fill optimization (manual zone tweaks if check_plane_island flags isolated areas)
- USB-style differential pair impedance tuning (current spec: length-matched only)
- High-frequency BEMF + CSA differential routing for EMC margin (after EMC sim feedback)

## Memorialization

Routing complete when:
- PR-routing-final merged (#82)
- audit_routing.py all 6 gates PASS
- Phase 5b autoroute approved by master
- target.h md5 7a4549d27e0e83d3d6f1ffaf67527d24 unchanged
- All channel-mirror checks 100% match
