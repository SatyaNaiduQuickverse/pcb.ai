# PARK-THEN-BRING-IN — Phase 4-v3 placement REDO process spec

**Status**: DRAFT for Sai review (worker, 2026-05-24). Do NOT re-run the 9
placement PRs until Sai approves this spec.
**Per**: Sai directive 2026-05-24 (PARK-THEN-BRING-IN pattern), relayed by master.
**Branch**: `phase4v3-park-and-bring`. **PR #100 (CH1 routing) stays as reference.**

## 1. Why (the failure this fixes)

The 9 v2 placement PRs (#91–#99) each started from a board that already carried
all 573 components in their *prior* positions, and each PR audited only the ~80
components it newly placed. The other ~490 "inherited" components stayed wherever
they last were — **ghosts** — invisible to the per-PR audit but real on the board.
They cross-collided with new placements and accumulated the 100 audit_layout +
35 zone + 154 highway failures master found on the merged HEAD.

Root cause beneath that: component→subsystem ownership was decided by **board
position** (the `_CHn` net-suffix check plus a zone-membership fall-through in
`get_chN_refs` / the v2 `place_subsystem.get_subsystem_components`). Position
decides ownership; ownership decides position — circular. A component with no
channel-tagged net (a decoupling cap on a global rail) could only be classified
by where it already sat.

## 2. The pattern

```
empty board ─▶ park ALL placeable comps off-board ─▶ per-subsystem PR brings its
roster into its zone ─▶ contract gate audits the FULL board every PR
```

- **Park, don't remove.** Removing footprints would force a kinet2pcb re-import to
  recover them, which silently drops nets when SKiDL pin names ≠ footprint pad
  numbers ([[reference-kinet2pcb-silent-drop]]). Parking preserves every
  footprint, pad, and net from the locked netlist import. target.h md5 and the
  netlist are untouched.
- **Ownership from the schematic SSOT, never position** (§3).
- **The contract gate sees the whole board.** A per-PR pass means no inherited
  component is hiding — ghosts become structurally impossible, not merely audited
  against. Proven by negative test (§5).

## 3. Roster — position-independent ownership (`roster.py`)

Ownership is derived only from `hardware/kicad/pcbai_fpv4in1.net` (the
SKiDL-generated netlist = schematic SSOT). No board coordinate is read.

| Signal (priority order) | Assigns |
|---|---|
| SKiDL source file `channel_skidl.py` | component belongs to a **channel** |
| single net name containing `CHn` | channel **instance** n |
| `CHn` in the component description | channel instance n |
| instantiation order within one `(file:line)` | channel instance — SKiDL runs each `channel()` call fully before the next, so the refs form 4 contiguous ascending blocks CH1<CH2<CH3<CH4 (block size = parts-per-channel at that line) |
| main-sheet source line → subsystem table (`MAIN_LINE_SUBSYS`) | central subsystem S1/S2/S3/S5/S6 (table is **validated to cover every main-sheet line** — an unmapped line is a hard error, never a silent default) |

The instantiation-order rule was **verified zero-mismatch against all 30
fully-CHn-tagged source lines** before being relied on for the 40 tagless caps.

**Result (validated total partition, channels equal):**

```
CH1 106  CH2 106  CH3 106  CH4 106   (channel total 424)
S1 14    S2 4     S3 23    S5 79    S6 29   (central total 149)
                                            netlist total 573, 0 unassigned
```

Note: the SKiDL-file method finds **388 channel comps vs only 328 the old
net-suffix method found** — the 60-comp gap is the global-rail decoupling caps the
old method could only place by position. That gap *was* the ghost surface.

Fixed mechanical geometry (`FID1-6`, `H1-4`) is not in the netlist; it is never
parked and never owned by a subsystem PR. Ten netlist test-points (`TP4,6,8,13,
14,15,18,25,32,39`) were dropped during placement and are simply absent from the
board; bring-in acts only on present refs.

## 4. Scripts

| Script | Role |
|---|---|
| `roster.py` | derive + validate the ownership partition; `--json` emits a reviewable manifest |
| `park_all_components.py` | park all 563 placeable comps to an off-board 5mm grid (x≥130), keep FID/H, strip tracks; verifies 0 placeable on-board |
| `place_subsystem.py` | `bring_selected(board, subsystem)`: precondition = roster refs parked; place into zone via `placer` callback; postcondition = all in zone |
| `audit_zone_contract.py` | full-board gate: every comp is fixed, in a *brought* zone, or parked — else GHOST/OUT-OF-ZONE/NOT-BROUGHT |

`place_subsystem.py` ships a deterministic **grid packer** that satisfies the zone
contract. The 9-PR re-run will pass each subsystem's **existing validated
geometry** (the `place_subsystem_ch1_v3` template, the mirror transforms) as the
`placer` callback — the harness owns the park/zone contract, the callback owns the
cluster geometry. No validated placement work is discarded.

## 5. Demonstration (run 2026-05-24, scratch board `/tmp/redo_e2e.kicad_pcb`)

```
park              → 563 parked, 0 on-board (verified), 5591 tracks stripped
audit brought=∅   → CONTRACT OK   (fixed 10, parked 563)
bring CH1         → 105 in zone
audit brought=CH1 → CONTRACT OK   (in_zone 105, parked 458)
bring S1, then audit brought=CH1  (S1 deliberately not declared brought)
                  → CONTRACT FAIL: 14 GHOST (J1,Q1-4,R1-5,D1-4)  ◀ gate catches it
```

The negative test is the point: the same situation that silently passed every v2
per-PR audit is now a hard failure.

## 6. Per-PR procedure (the 9-PR re-run, after Sai approval)

1. Start from the parked board (PR-0 commits `park_all_components.py` output).
2. PR-k: `bring_selected(<subsystem>)` with the subsystem's validated placer.
3. Gate (master): `audit_zone_contract.py --brought <all subsystems through k>`
   **plus** the existing `audit_layout_compliance` + `master_audit_invariants` +
   (for routing PRs) `audit_routing_system`. Per [[master-gate-checklist]] all
   gates run every PR — the discipline-miss in `docs/AUDIT_GAP_INVARIANTS.md`.
4. Order: CH1 (template) → CH2/CH3/CH4 (mirrors) → S1, S2, S3, S5, S6.

## 7. Open decisions for Sai / master

1. **Per-channel main-sheet items.** Status LEDs (`D15-22`, KILL/FAULT) + their
   resistors (`R22-29`) and per-channel test points (motor phase, SWD, status) are
   instantiated on the main sheet but are channel-specific (lines 512/515/531/534/
   907/912/914). `roster.py` assigns them to their channel (electrical ownership),
   so the channel PR brings them and they land in the **channel zone**. If Sai
   wants status LEDs at the **S6 connector edge** for visibility instead, move
   those lines to S6 in `MAIN_LINE_SUBSYS` — flagged per R21, not decided silently.
2. **S2 zone vs BOM** (pre-existing, still queued): C1-C4 are 10×14.3mm aluminium-
   polymer; the 20×20mm S2 zone may not fit 4 of them. Unblocks the S2 bring PR.
3. **Parking field placement.** x≥130 (off the 0-100 board). Confirm this collides
   with nothing in your fab/export flow (it is stripped before gerber export).

## 8. Invariants held

- target.h md5 `7a4549d27e0e83d3d6f1ffaf67527d24` — untouched (no firmware change).
- BOARD_INVARIANT_HASH `b6766bd…84c03e` — zones/highways unchanged; this is a
  process change, not an invariant change.
- Netlist unchanged — parking moves footprints, never edits nets.
