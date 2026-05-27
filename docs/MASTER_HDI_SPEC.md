# Master HDI Via-in-Pad Spec (J18 + J19 whitelist)

**Sai-locked**: 2026-05-27, cost-OK cleared (+$2-3/board production).
**Scope**: J18 (AT32F421 QFN-32) + J19 (DRV8300 HVQFN-24) ONLY.
**Trigger**: Worker per-pin analysis 2026-05-27 — CH1 STEP-6 routing capped
at 22/33 across PR#202–#206 (greedy v1, dense-first v2, MST-completion v3,
no-rip-routed v4, layer-pref v5). All 5 router versions plateau at the
same set: ~11 residual nets on J18 south edge + J19 driver fan-out, where
the dog-bone fanout via-area saturates (~22 escape vias available for
~33 pins at 0.5mm pitch).

## Root cause

QFN-32 at 0.5mm pitch with standard dog-bone fanout requires:
- Pad → ~0.5mm fanout stub on F.Cu (perpendicular to pad axis)
- Via 0.30mm drill / 0.60mm pad at stub end
- Escape track on inner layer (In2/In4/In6/In8)

Per pad, the fanout-via consumes:
- 0.25mm pad-edge + 0.5mm stub + 0.30mm via-half = ~1.05mm radial fanout reach
- 0.60mm via pad + 0.20mm clearance = 0.80mm via-keepout diameter

For J18 32 pads in a 5×5mm body, fanout reach extends to ~7mm × 7mm. The
required via-area density is one 0.80mm via-keepout per pad. At
1mm × 1mm spacing per via, only ~7×7 = 49 vias fit nominal, but
BEMF/CSA filter R/C wall at x≈17–22 blocks the south corridor — effective
escape area drops to ~30 via slots, of which ~22 are reachable from J18
without crossing the BEMF wall.

**Standard fanout cannot escape all 33 pins** with the placed BEMF/CSA
wall geometry. Possible mitigations evaluated:
- Move BEMF/CSA wall further south (R34 supplement) — placement constraint
  violation, requires re-place
- Reduce via size — limited by board-min hole (0.30mm) and annular (0.10mm)
- HDI via-in-pad — **chosen** per Sai cost-OK 2026-05-27

## HDI via-in-pad geometry (chosen approach)

Place a microvia DIRECTLY on the SMD pad center. No fanout stub. No via-
keepout zone. The microvia is small enough to fit entirely within the
0.25mm pad width:

| Parameter | Standard via | HDI microvia (J18/J19) |
|---|---|---|
| Drill | 0.30 mm | **0.10 mm** (laser-drilled) |
| Pad | 0.60 mm | **0.25 mm** (= QFN pad width) |
| Annular ring | 0.10 mm (5mil) | **0.075 mm** |
| Hole clearance | 0.25 mm | **0.10 mm** |
| Fill | none (tented) | **epoxy + plate-over** (mandatory) |
| JLC process | standard | HDI Class 2 |
| Cost impact | $0 (baseline) | **+$2-3/board** production |

Sai cost-OK 2026-05-27 cleared HDI Class 2 add-on for J18 + J19.

## Whitelist (BINDING)

The HDI process applies **ONLY** to these footprints:
- **J18** — AT32F421 QFN-32 5x5mm, 0.5mm pitch
- **J19** — DRV8300 HVQFN-24 4x4mm, 0.5mm pitch

NO other components may use HDI via-in-pad without:
1. Sai cost-OK approval (+$X/board per additional whitelist entry)
2. Update to `route_subsystem_cooperative.HDI_VIA_IN_PAD_REFS` constant
3. Update to `audit_hdi_via_in_pad.py` `HDI_VIA_IN_PAD_WHITELIST` tuple
4. Update to this doc + `docs/BOARD_INVARIANTS.md` HDI section
5. Update to `hardware/kicad/pcbai_fpv4in1.kicad_dru` if scope outside
   J18/J19 nets requires different rule conditions

## Production fab order requirements

When generating gerbers for JLC, the order must explicitly call out:
1. **Layer count**: 10 (per BOARD_INVARIANTS Phase 4a 10L lock)
2. **HDI process**: Class 2 with **via-in-pad** option enabled
3. **Via fill**: Epoxy non-conductive (Type IV per IPC-4761) +
   copper plate-over (Type VII)
4. **Drill list distinction**: 0.10mm microvia drills are HDI laser;
   0.30mm and larger are standard mechanical
5. **Pad list distinction**: 0.25mm pads at via locations should be
   inspected at fab — if reported as "below min pad" for standard
   process, FAB must use HDI Class 2 quotation

JLC tooling note: their UI usually has an "HDI Order" or "Via-in-pad"
checkbox in advanced options. Always confirm with JLC sales before
production run.

## Router integration

`route_subsystem_cooperative.py` v6:

```python
HDI_VIA_IN_PAD_REFS = ("J18", "J19")  # whitelist constant
HDI_VIA_DRILL_MM = 0.10               # microvia geometry
HDI_VIA_DIAM_MM = 0.25
```

CLI flag: `--via-in-pad-allowed` (default OFF for back-compat).
When ON:
1. `_stamp_obstacles` skips the via-keepout zone for J18/J19 pads,
   leaving the SMD pad cell available as an HDI via site.
2. `via_blocked_for_net` uses precise geometric distance check
   (`hdi_via_blocked_geom`) at HDI cells — the cell-based scan is
   over-conservative for the 0.25mm microvia.
3. `emit_to_board` writes HDI geometry (0.10mm/0.25mm) and tags
   the via as `VIATYPE_MICROVIA` so DRC applies HDI-relaxed rules.
4. Allowed layers expand to all SIGNAL_LAYERS for HDI-touching nets
   (router can spill to In4/In6 if In2/In8 saturated).

Worker re-runs the router with `--via-in-pad-allowed` and `--no-rip-routed`
on each subsystem PR; output drops into the same canonical .kicad_pcb.

## Audit gate (G_HDI_VIA_IN_PAD)

`audit_hdi_via_in_pad.py` enforces the whitelist:
- Iterates all vias on the board
- Filters to HDI vias (drill ≤ 0.15mm OR type MICROVIA)
- For each HDI via, checks if its center lies inside any SMD pad bbox
- PASS if every HDI via lies inside a J18/J19 SMD pad
- FAIL if any HDI via outside whitelist (cost scope creep) OR
  HDI via inside non-whitelist SMD pad (silent scope expansion)

Output:
- `✅ PASS — all HDI via-in-pad placements on whitelist`
- `❌ FAIL — N violations, action: rip OR extend whitelist (Sai approval)`

Run on every layout PR via master_review_board.py (added to
`AUDIT_TAKES_BOARD` set).

## DRU integration

`pcbai_fpv4in1.kicad_dru` HDI section:

```
(rule "HDI via diameter"
  (constraint via_diameter (min 0.25mm))
  (condition "A.Type == 'via' && A.Hole <= 0.15mm"))
(rule "HDI via hole size"
  (constraint hole_size (min 0.10mm))
  (condition "A.Type == 'via' && A.Hole <= 0.15mm"))
(rule "HDI via annular width"
  (constraint annular_width (min 0.075mm))
  (condition "A.Type == 'via' && A.Hole <= 0.15mm"))
(rule "HDI via hole clearance"
  (constraint hole_clearance (min 0.10mm))
  (condition "A.Type == 'via' && A.Hole <= 0.15mm"))
```

Per `[[reference-kicad-dru-libeval-crash]]`: uses `==` (exact string)
not `=~` (regex) — KiCad 9.0.2 headless libeval crashes on `=~`.
Scope-by-drill (`A.Hole <= 0.15mm`) captures HDI vias precisely
without needing a via-type expression token.

Project `kicad_pro` flags also enabled:
- `rules.allow_microvias = true`
- `rules.allow_blind_buried_vias = true`

## Validation results (worker e5ddb23 input)

Before HDI (input board, worker pass #206):
- 22/33 CH1 escape pins routed
- 10 unrouted CH1 nets (BEMF_A/B, PWM_INHC/INLA/INLC, BSTA/B, KILL_RAIL_N, LED_GPIO, SWDIO)
- 555 DRC violations baseline

After HDI (this PR, --via-in-pad-allowed --no-rip-routed, 10 iterations):
- **8/10 CH1 unrouted nets now routed** (28/33 total in zone — +6 over input baseline)
- Remaining 2 (KILL_RAIL_N_CH1, LED_GPIO_CH1) have non-HDI-pad target pads
  in dense regions (D33, R76) — they need cross-channel routing assistance,
  not HDI on J18/J19. Out of HDI scope.
- 551 DRC violations (DOWN 4 from baseline — new routes resolved more
  unconnected ratsnest than they introduced clearance issues)
- Net new DRC delta: +1 clearance violation (0.025mm tight clearance on
  BSTA microvia to D29 GND pad — router edge case, worker to iterate)
- HDI audit: ✅ PASS — 6 HDI vias on whitelist, 0 off-whitelist

## Open questions / follow-ups for worker

1. **KILL_RAIL_N_CH1 + LED_GPIO_CH1**: connect R76 ↔ J19.8 and D33 ↔ J18.25
   require routing through dense passive area NOT solvable by HDI alone.
   Worker may need to allow limited ripup of pre-existing tracks or move
   D33/R76 placement to reduce route length.
2. **CH2/3/4 mirror**: HDI policy extends to J18/J19 across all 4 channels
   by symmetry. Router automatically handles this (same refs across mirror).
3. **Cross-channel KILL/LED nets**: may benefit from a separate router
   pass with cross-channel routing scope.
4. **Production cost confirmation**: worker should request JLC quote for
   actual HDI Class 2 surcharge before first fab run — published +$2-3/board
   estimate is from public JLC tech spec but may vary by panel size.

## References

- Worker per-pin analysis (PR#206 follow-up): J18 escape saturation evidence
- Altium BGA fanout guide: HDI via-in-pad for fine-pitch packages
- NWEngineering "BGA Escape Routing with Impedance Control in HDI PCBs"
- IPC-4761 Type IV (epoxy fill) + Type VII (Cu plate over) standards
- JLC HDI Class 2 public tech spec (laser microvia + plate-over capability)
- `[[reference-kicad-dru-libeval-crash]]` — `==` not `=~` for DRU conditions
- `docs/DEEP_RESEARCH_2026-05-26_J18_J19_ESCAPE.md` — original placement-stage analysis
