# Board Invariants (SSOT) — Phase 4-v2 Step 1

**Status**: DRAFT pending master Sai-approval. Locks zones/I-O/highways/hash.
**Per**: Phase 4-v2 dispatch Step 1.

Any PR changing this hash WITHOUT explicit "invariant-change" PR title = REJECT.

## Board geometry

- Outline: 100×100 mm (per Phase 4 setup_board.py)
- Mount holes: 4× M3 at corners (5,5), (95,5), (5,95), (95,95)
- target.h md5: `7a4549d27e0e83d3d6f1ffaf67527d24` (firmware contract — LOCKED)
- Stackup: 8-layer
  - F.Cu (top signal + components)
  - In1.Cu (GND plane)
  - In2.Cu (signal)
  - In3.Cu (+VMOTOR plane, 3oz)
  - In4.Cu (signal)
  - In5.Cu (GND plane)
  - In6.Cu (signal)
  - B.Cu (bottom signal + secondary components)

## Subsystem zones (LOCKED on Sai-approval)

| Subsystem | x_min | y_min | x_max | y_max | Function |
|---|---|---|---|---|---|
| S1 battery input | 0 | 0 | 100 | 18 | top edge — XT30 + NTC inrush + TVS |
| S6 connectors | 0 | 82 | 100 | 100 | bottom edge — FC + AUX + DShot connectors |
| CH1 (channel A) | 0 | 50 | 50 | 82 | NW — FET cluster + DRV + MCU + INA |
| CH2 (channel B) | 50 | 50 | 100 | 82 | NE — mirror_X(CH1) |
| CH3 (channel C) | 50 | 18 | 100 | 50 | SE — mirror_X(CH4) |
| CH4 (channel D) | 0 | 18 | 50 | 50 | SW — bottom-pair template |
| S2 bulk caps | 35 | 40 | 65 | 60 | central — 4× polymer caps low-ESR to all channels |
| S3 supervisor+Hall | 35 | 18 | 65 | 40 | central spine — TL431 VREF + Hall current sense |
| S5 BEC | east+west bands inside channels | flexible | TPS54560 bucks (×5) + L + C_OUT |

**Note on overlaps**: S2 (35-65, 40-60) and S3 (35-65, 18-40) sit within the
central spine. CH1-CH4 zones must AVOID this central column unless
inter-subsystem nets specifically pass through.

## Symmetry pairs (LOCKED, 2-fold mirror about x=50)

- **CH1 ↔ CH2**: mirror_X(50). Each channel's placement+routing in CH1 mechanically
  mirrored to CH2 via `route_mirror_ch1_to_ch234.py ch2` for routes,
  `place_channel_passives_role_aware.py` mirror logic for components.
- **CH3 ↔ CH4**: mirror_X(50). Bottom pair, separate template from CH1/CH2.

No 4-fold symmetry — only the 2-fold pair-mirror per master dispatch
("2-fold symmetry locked CH1↔CH2 mirror about x=50, CH3↔CH4 mirror about x=50").

## Subsystem I/O ports (LOCKED at zone boundary, ±0.5mm tolerance)

| From → To | Port pos | Width | Signals | Reason |
|---|---|---|---|---|
| S1 → S3 | (50, 18) | 4 mm | +BATT, BATGND | central spine to bulk |
| S3 → S2 | (50, 40) | 4 mm | +BATT, BATGND, BUS_CURR_HALL_OUT | bulk caps + sensor |
| S2 → CH1 | (35, 50) | 4 mm | +VMOTOR, GND | feed CH1 FETs |
| S2 → CH2 | (65, 50) | 4 mm | +VMOTOR, GND | feed CH2 FETs |
| S2 → CH3 | (65, 40) | 4 mm | +VMOTOR, GND | feed CH3 FETs |
| S2 → CH4 | (35, 40) | 4 mm | +VMOTOR, GND | feed CH4 FETs |
| S6 → CHn | (depends on connector) | per net | DShot, TLM, KILL, etc. | FC commands |
| S5 → CHn | varies | per rail | +V5, +V9, +3V3 | BEC outputs |

## Highway reservations (NO subsystem may place into)

| Highway | x_min | y_min | x_max | y_max | Width | Reason |
|---|---|---|---|---|---|---|
| +BATT/GND spine | 48 | 0 | 52 | 50 | 4mm | 280A continuous power path top→center |
| BEMF return centerline | 47 | 50 | 53 | 82 | 6mm | 4× BEMF signals to central MCU |
| TLM/AUX bus strip | 0 | 80 | 100 | 82 | 2mm | inter-subsystem digital |
| Bulk-cap-to-FET radial | per channel | (varies) | 3mm | low-loop-area transient path |

## Invariant hash

```
sha256(geometry + zones + io_ports + highways + symmetry_pairs + target_md5)
```

Computed by `scripts/compute_board_invariant_hash.py`. Hash recorded here:

```
BOARD_INVARIANT_HASH = (TBD on first Step 1 commit)
```

## Audit gate

`check_board_invariants_hash()` in audit_layout_compliance.py (Step 1 deliverable):
- Recomputes hash from BOARD_INVARIANTS.md content
- Compares to stored hash
- REJECT on drift unless PR title contains "invariant-change"

## Approval

**Pending master Sai-approval** before lock. Once approved + hash stored,
this becomes single source of truth.
