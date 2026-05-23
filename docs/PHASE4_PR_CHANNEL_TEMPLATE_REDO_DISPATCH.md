# PR-channel-template-redo — dispatch (post-/compact briefing)

**Dispatched:** master 2026-05-23 (after PR #68 merge)
**Base branch:** master @ df413b4 (post-#68)
**Branch to create:** `phase4-channel-template-redo`
**Estimated:** 4-6h fresh context budget

## Context

PR #68 closed the gate-R quadrant fix (R23 critical-path resolved) +
added `check_per_channel_passive_quadrant` audit gate. 56 residual
non-gate-R passive quadrant violations remain. Master adjudicated:
spot-fix infeasible due to density (252 channel-tagged passives in
2500mm² each = ~10mm² per component). Architectural redo required.

## Phases

### Phase 1 — Architectural audit (DO NOT touch placement yet)

1. Read SKiDL schematic — identify per-channel vs shareable components:
   - **TL431 references** (U2/U5/U8/U11): Are these 4 separate 2.5V
     references per channel, or can ONE shared reference feed all 4
     channels' comparators? Star-routed VREF would let TL431 move to
     central spine. Drift/noise tradeoff vs ~50mm² freed per channel.
   - **LM393 comparators** (U3/U6/U9/U12): Per-channel CSA_MAX trip
     uses per-channel current sense — likely MUST stay per-channel.
     Verify by walking schematic.
   - **74LVC1G08 AND gates** (U4/U7/U10/U13): Per-channel kill logic
     gating per-channel DRV enable — likely MUST stay per-channel.
   - **VREF distribution**: If TL431 shared, VREF_2V5 net spans
     channels — needs central placement + star routing back to each
     comparator's VREF pin.

2. **Output**: `docs/PHASE4_CH_TEMPLATE_REDO_ARCH.md` — architectural
   decision doc listing which of the 12 channel ICs stay per-channel
   vs which move to central spine.

3. If any IC moves central: SKiDL change needed (rename nets, remove
   `_CHn` suffix from shared components). **Flag separately** —
   may need its own intermediate PR (Phase 3-redo class).

### Phase 2 — Re-architect channel template

4. With reduced per-channel component count, redesign CH1 template:
   - ONLY truly per-channel components in CH1 zone (50×50mm)
   - Breathing room for R23 + R25 + per-channel-quadrant
   - Centralized components in spine area
5. Run all 12 audit gates on CH1 — must be GREEN incl.
   `check_per_channel_passive_quadrant`.
6. Mirror to CH2/3/4 via `route_mirror_ch1_to_ch234.py` logic adapted
   for placement (not just tracks).
7. Verify all 12 gates GREEN board-wide.

### Phase 3 — Re-do affected routing

8. Existing routes from PR #59-#66 may have endpoints on moved
   components.
9. Identify orphan routes — delete or adjust endpoint to new pad
   location.
10. Re-run `audit_routing.py` — all 6 gates PASS.

### Phase 4 — Push PR-channel-template-redo

11. Master review per [[feedback-sai-catches-are-samples]]:
    per-subsystem visual + audit + thermal re-sim.
12. Merge.

## Acceptance criteria

- 0 violations on all 12 placement audit gates (incl. CH-PASSIVE-QUADRANT)
- 0 violations on all 6 routing audit gates
- target.h md5 unchanged at `7a4549d27e0e83d3d6f1ffaf67527d24`
- Each gate-R within 5mm of parent FET (R23) — currently already met
- Each IC-decoupling cap same-layer as VDD pin (R25)
- Symmetry preserved: locked mirror transforms produce equivalent CH2/3/4

## Files likely touched

- `pcbai_fpv4in1_skidl.py` and/or `channel_skidl.py` (if SKiDL changes)
- `hardware/kicad/pcbai_fpv4in1.kicad_pcb` (placement repositioning)
- `hardware/kicad/scripts/place_board.py` or new template script
- `hardware/kicad/scripts/route_mirror_ch1_to_ch234.py` (placement variant)
- `docs/PHASE4_CH_TEMPLATE_REDO_ARCH.md` (new arch decision doc)

## Constraints (carry-over)

- target.h md5 must stay `7a4549d27e0e83d3d6f1ffaf67527d24` (NO firmware change per Sai)
- Don't touch FET footprints until Sai answers PDFN-8 vs TO-263 question
- NEVER touch shared `/home/novatics64/local/freerouting/freerouting.jar` while novapcb active
- Per-command `git -c user.name="Sai Kishore Naidu" -c user.email="naidu.saikishore9@gmail.com"`
- Master/worker /send via `http://localhost:8766/send/master` with `from:"worker"` tag

## Memory references

- [[feedback-redo-not-mitigate]] — why this redo PR exists
- [[feedback-sai-catches-are-samples]] — audit-gate-first approach
- [[feedback-symmetry-preserves-work]] — N-instance pure geometric transforms
- [[feedback-no-passive-island]] — R23 anchoring rule
- [[feedback-same-side-decoupling]] — R25 layer-match rule
