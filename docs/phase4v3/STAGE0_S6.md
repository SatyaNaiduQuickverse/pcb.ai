# Phase 4-v3 Stage 0 — S6 smoke test

**Branch**: `phase4v3-stage0-s6`. First real exercise of the park-then-bring REDO +
G11 vision check. Validates the tooling on the connector/BEC-LDO/ESD subsystem.

## What this PR does

Produces the empty-board REDO baseline + brings S6, via the locked pipeline:

```
park_all_components  → 560 parked off-board (x≥130), 13 foundation snapped to lockfile, tracks stripped
migrate_footprints   → 17 in-place footprint swaps (12 motor pads→ESCMotorPad, 4 caps→CP_Elec_8x6.2, J1→AMASS_XT30U-M)
place_subsystem S6   → 21 brought (10 anchor@lockfile + 11 real role-based); 0 grid
audit_zone_contract  → CONTRACT OK (foundation 13 / in_zone 11 / anchored 10 / parked 539)
render_pr_visual     → G11 set: top/bottom/iso/zone_zoom/diff + manifest (PIL, no ImageMagick)
```

## Placement quality (S6)

Real role-based placement (`role_place`, PLACEMENT_METHODOLOGY §2) — grid fallback
unused (R32: grid is banned as primary — caused fab-blocking overlaps + no decoupling):

- J13 (TLV76733 LDO) in-zone; J15-17 (USBLC6 ESD) clustered at the FC header J14.
- Decoupling anchored ≤3mm to parent pad: C45→J13 1.2mm, C46→J13 1.8mm, C47→L11 1.8mm.
- 0 PAD-OVERLAP-DIFFNET, 0 COINCIDENT-PLACEMENT, 0 S6 SILK-ON-PAD (small-passive refs hidden).

## Spec deviations (R21)

1. **J1 footprint** `Connector_XT30` (placeholder) → `AMASS_XT30U-M_1x02_P5.0mm_Vertical`
   (real KiCad Connector_AMASS fp, male board-mount, Sai-confirmed). Lockfile + board.
2. **J14 position** `(50,90)` → `(50,96)`. At y=90 it was 10mm from the y=100 edge,
   violating EXTERNAL-CONNECTOR-EDGE (Sai-catch #5, ≤5mm). y=96 → 4mm.
   *(Both lockfile edits → mechanical_anchors hash changes; master to recompute.)*

## Gate status (master_pre_merge.sh --staged S6, against #106 audits)

PASS: G2 (zone contract), G3 (loop area), G8 (drift), G9 (target.h md5).
G7/G11 SKIP (no tracks / renders present). G1/G4 confirmed fixed for on-board comps.

**Remaining FAILs are all parked/staged-awareness gaps in master's audits, NOT this
placement** (synthetic truth boards are all-on-board so never hit these):
- G1 `audit_anchor_positions`: not staged — flags parked channel anchors (TP19-44).
- G2 in runner: needs `--brought S6` passthrough (passes standalone).
- G4 `audit_decoupling`: `--parked-exempt` doesn't skip parked ICs (channel MCUs).
- G5 SYMMETRY / QUADRANT-BALANCE / SILK-ON-PAD: count parked channel/BEC components.

Worker's S6 placement is clean; these need master's `--staged`/`--parked-exempt`
extensions (in flight). Pushed so master can cross-validate against this real board.

## Invariants

target.h md5 `7a4549d27e0e83d3d6f1ffaf67527d24` unchanged. Netlist unchanged (footprint
swaps in-place, no kinet2pcb re-import).
