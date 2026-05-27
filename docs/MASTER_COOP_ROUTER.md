# Cooperative Ripup-Reroute Router

**Tool**: `hardware/kicad/scripts/route_subsystem_cooperative.py`

**Origin**: Master dispatch 2026-05-27 (worker R26 escalation on J18/J19 CH1 STEP-6 dense fan-in plateau).

**Algorithm**: Pathfinder-style (McMurchie + Ebeling 1995) cooperative ripup-reroute maze router on a 3D cell grid (x, y, layer). Solves the greedy-A* self-congestion problem identified in [[reference-cascading-escape-needs-negotiated-routing]].

**Status**: v3 operational. Master-verified on `phase4v3-stage1-ch1-on-10L` @ 9eed5ae.
- 100% routed (1/1) on isolated multi-pad subset (BEMF_A_CH1, 4 pads, ratsnest=0)
- 12/16 fully routed on full dense J18/J19 set (same as v2 — no regression)
- 0 SHORTS delta, 0 DRC delta, 7/8 multi-pad nets verified 1-island
- See "v3 fix history" + "v2 fix history" sections below

## Why

Greedy escape-to-inner routing on dense IC pin-out cascades self-congests:
each net's escape tracks block the next net's via positions. The standard PCB
EDA fix (Pathfinder / negotiated congestion) routes each net with per-cell
congestion cost, rips up nets blocking failed nets, increments history cost
per congested cell, and iterates until convergence or plateau.

See [[reference-cascading-escape-needs-negotiated-routing]] for the design rationale
(no Freerouter per [[reference-kicad-dsn-export-drops-inner-layers]]: DSN export drops
inner layers, breaking incremental routing on already-routed boards).

## Algorithm

```
For iteration in 1..N:
  Sort unrouted nets by (fail_count DESC, priority ASC)
  For each unrouted net:
    Build MST of pads (greedy nearest)
    For each MST edge:
      A* search on grid with cost = LAYER_BASE + present_factor*present + history
      Allow via-change between configured signal layers (LAYER_PREF per net pattern)
      Validate diagonal moves (axis-cells must also be passable)
    If routed: commit (stamp obstacles, increment present_count)
    Else: increment fail_count, queue for next pass
  After pass:
    Bump history: cells with present>1 get history += (present-1) (cong'd cells learned)
    present_factor *= 1.4 (raise pressure)
    Rip top-K nets blocking failed-net pads; force-rip 3 random nets if plateau
```

## Architecture

```
BoardState         — extracts pads + tracks + vias + zones from .kicad_pcb
CongestionGrid     — (x,y,layer) grid; obstacle / net_halo / pad_cells / present / history
CooperativeRouter  — main loop; A* per-edge; commit/rip; plateau detection
path_to_segments   — collapse path cells into straight segments + via points
```

### Pad model

```
Pad copper rect       = hard obstacle, OWN-NET cells accessible
Clearance halo        = pad rect + CLEARANCE + trace_half + slop; owner-net-only
Via-keepout zone      = pad rect + CLEARANCE + via_radius; via forbidden for foreign nets
```

For a QFN/LQFP at 0.5mm pitch with 0.25×0.88mm pads:
- Pad halo = 0.305mm beyond copper edge
- Between adjacent pads = 0.25mm < 2×0.305 → no trace between pads
  (correct dog-bone topology: escape MUST be perpendicular to pad row)
- Via must land at least `pad_half + CLEARANCE + via_radius ≈ 0.83mm` from
  any foreign pad center (prevents via-in-pad and inter-pad-clearance)

## Layer allocation (per CH1 STEP-6 plan, BOARD_INVARIANTS §10L)

```python
F.Cu / B.Cu : pad fanout stubs only (high LAYER_BASE_COST=4.0)
In2.Cu      : PRIMARY signal escape (PWM, CSA, dense fan-in)  cost=1.0
In4.Cu      : DEDICATED BEMF (OQ-016 lock)                     cost=1.0
In6.Cu      : SW escape (OQ-017; mostly free after STEP-4)    cost=1.5
In8.Cu      : SWD/NRST/BOOT0/control overflow (PR #192)        cost=1.0
```

GND planes In1/In3/In7, +VMOTOR In5 are UNTOUCHED. Power nets (MOTOR/SHUNT/+V*/GND)
matched by SKIP_NET_PATTERNS and never routed.

## Usage

```bash
python3 hardware/kicad/scripts/route_subsystem_cooperative.py \
  /path/to/board.kicad_pcb \
  --subsystem CH1 \
  --output /tmp/routed.kicad_pcb \
  --max-iterations 25 \
  [--grid-pitch 0.1] \
  [--seed-nets NET1,NET2,...] \
  [--report routed.csv] \
  [--no-rip-routed]  # v4: multi-pass preserve
```

### Auto-detect mode (default)

Without `--seed-nets`, router auto-picks all CH1 nets with ≥2 pads in zone,
≤2 existing tracks (unrouted), and not matching SKIP_NET_PATTERNS.

### Targeted mode

With `--seed-nets net1,net2,...`, router targets the explicit list — useful for:
- Re-routing a specific set after a partial run
- Routing stragglers after main batch
- Testing on isolated nets to debug obstacle stamping

### Multi-pass mode (v4 — `--no-rip-routed`)

In multi-pass workflows where pass N+1 must preserve pass N's routes (e.g.
CH1 STEP-6 dense-J18-first then local-by-local; CH2/3/4 mirror cycles),
pass `--no-rip-routed` to pass 2+. Effect:

- Pre-existing routed nets (≥1 track/via in input board at load time) are
  snapshotted into `preserved_nets` set.
- Preserved nets are **dropped from target list** (never re-attempted, even
  if explicitly seeded — they're left alone).
- Preserved nets are **never selected as ripup candidates** (selective ripup
  + plateau force-rip both exclude them).
- `rip_net()` has a defensive guard refusing to rip preserved nets even if
  called directly.
- Pre-existing tracks remain as **hard obstacles** to new routes (same
  `_stamp_obstacles` path as before — no algorithm change there).

**Use case rationale** (worker discovery 2026-05-27 CH1 STEP-6 (c) re-approach):
pass 1 cooperative routed BEMF_C; pass 2 local net-by-net ran cooperative
ripup and **ripped BEMF_C** because cooperative-ripup treats ALL routes
(including pass 1's) as session-mutable. `--no-rip-routed` is the explicit
mark-as-immovable mechanism.

**Tradeoff**: new route success rate may be lower because the router has
fewer degrees of freedom — preserved nets cannot move out of the way. Where
it would have ripped a blocker, it now reports FAILED. Hand-route or
re-place if pass 2+ plateaus too low.

**Default OFF** for backward compatibility with single-pass fresh-board runs.

## Validation gate (per [[feedback-sim-execution-gate]] discipline)

After running, every PR MUST verify on the OUTPUT board:

```bash
# 1. audit_routing.py: 0 new TRACK-WIDTH/UNROUTED failures vs input baseline
python3 hardware/kicad/scripts/audit_routing.py <output.kicad_pcb> --subsystem CH1

# 2. audit_power_drc.py: 0 new POWER-PAD-CLEARANCE violations on SAME LAYER
#    (audit's L∞ approximation gives false positives on different layers;
#    use the layer-aware check script if available)
python3 hardware/kicad/scripts/audit_power_drc.py <output.kicad_pcb>

# 3. Per-net connectivity: every routed target net has 1 island (use union-find
#    over pad positions + track endpoints)
```

## v4 fix history (2026-05-27 — --no-rip-routed cross-pass interference fix)

**Worker discovery on v3 (commit e5ddb23, CH1 STEP-6 (c) re-approach)**: ran
cooperative router in two sequential passes:
- Pass 1 (dense-J18 cooperative, 17 nets): routed 11/17 including BEMF_C_CH1
- Pass 2 (local gate/boot net-by-net, 13 nets): routed 9/13 BUT **RIPPED
  BEMF_C_CH1 from pass 1's result**

**Root cause**: cooperative ripup-reroute treats ALL existing routes as
session-mutable. Pass 2's congestion-blocker scoring (`_select_ripup_candidates`)
finds pass 1's BEMF_C tracks near pass 2's failed pad cells → rips them →
can't re-route because original conditions don't apply (different seed_nets,
different congestion landscape).

The bug is fundamental to cooperative ripup: it assumes all routes are
session-owned. Multi-pass workflows need an explicit way to mark pass-N
nets as immovable for pass N+1+.

### v4 fix

`--no-rip-routed` CLI flag (default OFF for back-compat). When set:

1. **Snapshot at init**: walk `board.GetTracks()` immediately, snapshot
   every net name with ≥1 track or via into `self.preserved_nets` (string
   set; netcodes can theoretically be re-issued by KiCad on mutation).

2. **Drop preserved nets from target list**: even if user explicitly passes
   them in `--seed-nets`, they are excluded — the flag overrides intent
   (consistent with "immovable" semantics). Logged at startup:
   `[coop] --no-rip-routed: N pre-existing routed nets snapshotted; K dropped`

3. **Ripup-candidate exclusion**: `_select_ripup_candidates` skips any net
   in preserved_nets. (They wouldn't normally enter `self.committed` —
   defensive belt-and-suspenders.)

4. **Force-rip pool exclusion**: plateau-recovery's random-3 force-rip
   pool excludes preserved_nets. Logs `"plateau but no rippable nets (all preserved)"`
   if the pool is empty.

5. **`rip_net()` defensive guard**: if called directly on a preserved net,
   logs refusal and returns early. Covers any future code path that
   bypasses the candidate-selection layer.

Pre-existing tracks/vias remain as **hard obstacles** to new routes (the
existing `_stamp_obstacles` already stamps every track/via from board
state — no algorithm change needed for that path).

### v4 validation results (2026-05-27)

Input: `phase4v3-stage1-ch1-on-10L @ e5ddb23` (22/33 CH1 signals routed,
32 nets total with tracks/vias in CH1 region).

Test A — `--no-rip-routed` snapshot + drop:
- Input: 32 pre-existing routed nets
- Log: `[coop] --no-rip-routed: 32 pre-existing routed nets snapshotted (immovable)`
- With `--seed-nets BEMF_C_CH1,LED_GPIO_CH1`: BEMF_C dropped (preserved),
  LED_GPIO retained as target
- After 5 iterations: LED_GPIO unrouted (corridor saturation, expected),
  **0 ripups**, BEMF_C unchanged

Test B — preserved-net identity post-run:
- All 32 preserved nets: track+via count IDENTICAL pre/post
- Per-net union-find island count IDENTICAL pre/post (0 splits introduced)
- Zone fill: tracks=566 vias=217 zones=17 IDENTICAL pre/post
- kicad-cli DRC: violations 549 → 549 (delta 0); unconnected 499 → 499 (delta 0)
- Breakdown: clearance 77, courtyards_overlap 105, drill_out_of_range 66,
  shorting_items 147, solder_mask_bridge 154 — ALL IDENTICAL

The flag works exactly as specified: no preserved net ripped, no new shorts,
no new DRC violations. New route attempt may fail (tradeoff for the
constraint), but preserved work is bit-exactly retained.

### When to use `--no-rip-routed`

- **Pass 2+ of any multi-pass cooperative run** (CH1 STEP-6 c-re-approach
  pattern; CH2/3/4 mirror cycles using same dense-first-then-local pattern)
- **Touch-up runs after hand-routing** — when worker hand-routes some
  stragglers and wants the router to try one more pass on residuals without
  rewriting hand-work
- **Post-merge incremental** — once a PR merges with N nets routed,
  subsequent routing PRs should use `--no-rip-routed` to avoid disturbing
  merged baseline

### When NOT to use

- Pass 1 of a fresh routing batch (no pre-existing routes to preserve)
- When you explicitly want the router to optimize globally (rip + reroute
  everything together)
- When pass 1's routes are known-bad and you want them displaced

## v3 fix history (2026-05-27 — multi-pad MST completion safety net)

**Worker R22 catch on v2 (PR #203)**: claim — "for 4-pad nets (BEMF_A/B/C,
BOOT0, KILL_RAIL_N, etc), router connects ONE pad-to-pad edge then reports
'routed=1/1', but ratsnest>0 (net SPLIT)". Master investigation:

- v2's `route_one_net_mst` correctly iterates N-1 MST edges for N pads and
  returns `(paths, False)` if ANY edge fails. `commit_net` is NOT called on
  failure → no tracks added → DRC + router-report agree on "UNROUTED".
- Concrete test on `9eed5ae`: BEMF_A_CH1 (4 pads) under v2 dense run reaches
  status ROUTED after 4 iterations with 3 MST edges, ratsnest=0 (verified
  via union-find on track endpoints + pad bboxes).
- v2 dense outcome (16-net target): 12/16 fully routed, BEMF_B_CH1 +
  PWM_INHC + SWDIO + PWM_INLB unrouted. NO multi-pad net was silently SPLIT.

So the literal "1 edge then report routed=1/1" claim does not reproduce.
HOWEVER, the underlying concern is valid: v2 had NO post-MST connectivity
verification — if a future bug caused MST to claim success without all pads
linking (e.g. grid-snap rounding pulling a track endpoint outside pad bbox,
or a multi-pad with coincident-position pads creating MST degeneracy), v2
would silently ship a split net.

### v3 fixes

1. **Explicit PARTIAL status + diagnostic** (`route_one_net_mst` return type):
   Now returns `(paths, status, failed_pairs)` where status is
   `'ROUTED' | 'PARTIAL' | 'FAILED'` and `failed_pairs` lists pad-label
   pairs whose A* failed. PARTIAL routes are NOT committed (preserves v2's
   all-or-nothing routing guarantee — the partial routes would lock in and
   block their own subsequent MST attempts). The pad-pair diagnostic
   persists across iterations via `self.partial_pairs[netname]`, so the
   final report tells the worker WHICH specific pair was the blocker —
   actionable next-step info for hand-routing.

2. **Post-MST connectivity verification** (`verify_net_connectivity`):
   After every `commit_net` of status=='ROUTED' net, builds a union-find
   over the board's pads + tracks + vias for that net. If the result is
   >1 island, the net is RIPPED + re-queued with fail_count bump, and the
   inter-island pad-pair is recorded as diagnostic. Uses union-find (not
   `GetRatsnestForNet`) because the SWIG binding for `RN_NET *` exposes
   no methods — the Python-only object cannot be iterated or counted.

3. **Termination condition**: `if not unrouted` was insufficient — now
   requires `not unrouted AND not self.partial_pairs` to avoid breaking
   out of the iteration loop while leaving open diagnostic markers.

4. **Final report extensions**:
   - Summary line: `full={N} partial={K} unrouted={M}` (was just
     `routed={N+K}`)
   - CSV report adds `partial_pairs` column with `pa->pb;pa2->pb2` for
     each partial net
   - Exit code 1 if ANY net is partial OR unrouted (was: only if unrouted)

5. **Unused helper `route_pad_pair` retained**: not currently called (the
   PARTIAL rollback semantics make per-pair repair unnecessary), but kept
   for future enhancement where partial-commit + selective-repair becomes
   viable (e.g. when a future net-ordering heuristic ensures siblings
   route in a way that doesn't self-block).

### v3 validation results (2026-05-27)

Worker board `phase4v3-stage1-ch1-on-10L` @ 9eed5ae. Baseline DRC after
refill: 552 violations, 153 shorts, 499 unconnected items.

| Run | Routed (full) | Routed (partial) | Unrouted | DRC delta | SHORTS delta | Multi-pad verify |
|---|---|---|---|---|---|---|
| BEMF_A_CH1 only (seed) | 1/1 | 0 | 0 | 0 | 0 | 1/1 1-island |
| Dense 16-net | 12/16 | 0 | 4 | 0 | 0 | 7/8 1-island* |

*BEMF_B_CH1 is in the 4 unrouted set; v3 reports `J18.10 -> C75.1` as the
specific failed pad-pair (actionable for worker hand-routing). v2 reported
the same outcome but without the pad-pair diagnostic.

### Known limit (fixed v3 in spirit; remains a routing capacity issue)

The MST-completion safety net does not improve routing CAPACITY (same
12/16 on dense as v2). The remaining unrouted nets are pin-escape
bottlenecks per [[reference-qfn-pin-escape-bottleneck]]; their fix
requires multi-net joint A* (future v4) or smaller grid pitch (Phase 7
x86 per [[feedback-pi-shared-system-protect]]). v3 adds DIAGNOSTIC and
DEFENSE-IN-DEPTH but not capacity.

## v2 fix history (2026-05-27)

**Worker R22 catch on PR #202 (v1)**: 807 DRC violations introduced (330 after
zone-refill), 35 net-to-net SHORTS. Root cause two bugs:

1. **Via cross-layer obstacle gap**: The maze A* validated proposed vias only
   against the obstacle map on the source/dest signal layer. A through-via
   (F.Cu→B.Cu, the only via type the router emits) actually intersects EVERY
   copper layer in the stack. Foreign-net tracks on intermediate signal layers
   (e.g. SHUNT_A_TOP_CH1 track on In2.Cu) caused via-track shorts that the
   router never noticed.
2. **Soft plane treatment**: Inner-plane fills (GND on In1/In3/In7, +VMOTOR
   on In5) were tagged as soft (history-bump only) per L313-323 of v1. Foreign
   vias landed inside the plane fills; KiCad auto-antipads on refill made
   inner planes safe (correct behaviour) but F.Cu / B.Cu MOTOR / SHUNT pours
   were treated the same way and routinely got pierced by signal vias.

### v2 fixes

1. **Full-stack via obstacle validation** (`CongestionGrid.via_blocked_for_net`):
   For every proposed via at (i, j), iterate every signal layer in the via's
   span, checking the obstacle/halo cells within a via-pad+clearance halo
   of (i, j) for foreign-net obstacles. Two scan radii:
   - `r_obs`: extra cells beyond the existing track halo to account for the
     wider via pad vs. trace half-width (~2 cells at 0.1mm pitch).
   - `r_plane`: full `via_pad/2 + clearance` cells for via_plane_owners (the
     plane raster has no built-in margin).
2. **Hard plane via-obstacle on F.Cu/B.Cu pours only**
   (`BoardState.filled_zones` + `CongestionGrid.stamp_plane_fill`):
   Filled MOTOR_*_CHn and SHUNT_*_TOP_CHn pours on F.Cu/B.Cu are rasterized
   into `via_plane_owners[(i, j)][layer] = pour_net`. Foreign-net vias touching
   any cell of a foreign pour get rejected. Inner-plane fills (GND, +VMOTOR)
   are NOT rasterized — KiCad ZONE_FILLER auto-antipads them correctly, and
   blocking them entirely would prevent the router from placing vias anywhere.
3. **Through-via obstacle stamping on all 10 copper layers**: `via_obstacles`
   and committed-via stamping now write obstacle cells on every layer in
   ALL_COPPER_LAYERS (not just SIGNAL_LAYERS), so a foreign-net via cannot
   land on top of an existing via on a plane layer.
4. **Wider via obstacle radius**: existing-via and committed-via obstacle
   circles use `r = via_pad/2 + CLEARANCE + trace_half + slop` (was
   `via_pad/2 + CLEARANCE`). Accommodates via-vs-track clearance, not just
   via-vs-via.
5. **THT pad plane-layer obstacle**: Through-hole pad copper on plane layers
   is added to `via_plane_owners` so foreign-net vias respect THT pad
   clearance on every copper layer (not just signal layers).

### v2 validation results (2026-05-27)

Worker board `phase4v3-stage1-ch1-on-10L` @ 9eed5ae. Baseline (refilled): 891
violations, 0 CH1-zone shorts.

| Run | Routed | DRC delta | NEW CH1 shorts |
|---|---|---|---|
| v1 (PR #202)  | 24/30 | **+342** | **+46 catastrophic** |
| v2 (2-net) | 2/2 | 0 | 0 |
| v2 (15-net dispatch) | 11/15 | +2 minor clearance | 0 |

The v2 +2 clearance violations are 0.0093mm shortfalls (`actual 0.1907mm vs
required 0.2mm`) between router-emitted track and router-emitted via on the
same iteration. These are sub-rounding grid-discretization corner cases:
within fab tolerance (typically ±0.05mm) and orders of magnitude less severe
than v1's net-to-net shorts. Bumping `GRID_SLOP_MM` from 0.025 to 0.05 fixes
them but cuts routing yield from 11/15 to 7/15 — tradeoff not worth it. Accept
the +2 minor clearance as known limit; worker can hand-tweak with KiCad if a
specific fab requires <0.01mm tolerance.

The v2 changes are correctness-preserving and apply BEFORE the path is
committed: an A* expansion that would yield a shorting via simply isn't
explored. Routing capacity may drop slightly when bypass paths require longer
detours, but the same Pathfinder negotiated-congestion machinery (history,
ripup, present_factor escalation) compensates.

## Mandatory pre-PR validation (per [[feedback-coord-pr-must-simulate-placement]])

Every PR touching this router MUST execute the 7-step gate:

```bash
# (a) Fetch worker board (or canonical baseline)
git show <worker_branch>:hardware/kicad/pcbai_fpv4in1.kicad_pcb > /tmp/router_in.kicad_pcb

# (b) Run modified router
python3 hardware/kicad/scripts/route_subsystem_cooperative.py \
    /tmp/router_in.kicad_pcb --subsystem CH1 --output /tmp/router_out.kicad_pcb \
    --max-iterations 15

# (c) POST-ROUTE ZONE REFILL (mandatory — without refill, plane antipads are missing)
python3 -c "
import pcbnew
b = pcbnew.LoadBoard('/tmp/router_out.kicad_pcb')
pcbnew.ZONE_FILLER(b).Fill(list(b.Zones()))
b.Save('/tmp/router_out_refilled.kicad_pcb')
"

# (d) Baseline DRC (run once)
kicad-cli pcb drc /tmp/router_in.kicad_pcb --output /tmp/drc_in.json --format json

# (e) Refilled-output DRC
kicad-cli pcb drc /tmp/router_out_refilled.kicad_pcb --output /tmp/drc_out.json --format json

# (f) Diff: VERIFY 0 new shorts in CH1 zone (0-35, 50-89)
python3 -c "
import json
i = json.load(open('/tmp/drc_in.json'))['violations']
o = json.load(open('/tmp/drc_out.json'))['violations']
def in_ch1(v):
    for it in v.get('items',[]):
        p = it.get('pos',{})
        if 0 <= p.get('x',-1) <= 35 and 50 <= p.get('y',-1) <= 89: return True
    return False
shorts_in  = sum(1 for v in i if v['type']=='shorting_items' and in_ch1(v))
shorts_out = sum(1 for v in o if v['type']=='shorting_items' and in_ch1(v))
print(f'CH1 shorts delta: {shorts_out - shorts_in}')
assert shorts_out <= shorts_in, 'GATE FAILED: new CH1 shorts introduced'
"

# (g) IF assertion passes: open PR. Else iterate router fix.
```

## Known limitations + future work

0. **FIXED in v2 (2026-05-27)**: cross-layer via obstacle validation +
   F.Cu/B.Cu pour hard-block via_plane_owners. v1 emitted via-vs-foreign-track
   shorts because A* only consulted source/dest layer obstacle map.

1. **Plateau at ~80% on dense full-CH1 signal set**: 6 nets typically remain
   unrouted in mutual-blocking scenarios. Each routes IN ISOLATION (3/3 verified
   on PWM_INHB+PWM_INLB+SWDIO alone), but greedy sibling routing starves them.
   - **Fix path**: multi-net joint A* (route all sibling QFN-row nets as one
     atomic operation with distinct via slots pre-assigned).

2. **Grid pitch 0.1mm**: 0.05mm pitch needed for ultra-dense QFN escapes but
   blows Pi memory budget (3.4M cells × 6 layers). Per [[feedback-pi-shared-system-protect]],
   stay at 0.1mm for Pi-resident master ops; escalate to Phase 7 x86 for finer pitch.

3. **MST + per-edge A***: doesn't optimize globally; near-optimal but not
   length-optimal. Tradeoff: O(E·A*) time vs O(N²·A*) for full-net Steiner.

4. **Diagonal moves**: 8-connected A* with axis-cell-passable check prevents
   corner-clipping but doesn't perfectly model trace mitering. Bresenham-style
   segment validation added post-collapse for hard correctness.

5. **History-cost decay**: not implemented. Long-running routing may have stale
   history dominating present-congestion. Add decay factor if observed.

## Test results (CH1 dense fan-in scenario)

### v1 (PR #202 — DEPRECATED, introduces shorts)

| Target set | Iter | Time | Routed | Ripups | NEW shorts |
|---|---|---|---|---|---|
| 30 nets (full CH1 auto) | 30 | 200s | 24/30 | 58 | **+46 (catastrophic)** |

### v2 (this PR — corrected via full-stack via validation)

| Target set | Iter | Time | Routed | Ripups | NEW shorts |
|---|---|---|---|---|---|
| 2 nets (PWM_INHA, INLA) | 1 | 6s | 2/2 | 0 | 0 |
| 6 nets (all PWM_IN*) | 15 | 138s | 4/6 | 28 | 0 |
| 30 nets (full CH1 auto) | (see PR body) | | | | 0 |

The v2 metrics show a real (not papered-over) routing capacity: v1's
"24/30 routed" hid 46 net-to-net shorts that made the board unusable. v2's
4/6 PWM with 0 shorts is the TRUE routing capacity at the current parameter
tuning. Hand-routing the remaining nets (or relaxing parameters with care)
is the correct next step — DRC clean is non-negotiable per [[feedback-sim-execution-gate]].

Sibling-blocking plateau still exists (PWM_INLB/PWM_INHC unrouted at 4/6) —
same root-cause as v1: greedy MST + per-edge A* doesn't reserve via slots
across siblings. Fix path remains multi-net joint A* (deferred).

## Worker workflow integration

```bash
# 1. Worker checks out branch with placed CH1 + routed STEP-4 power
git checkout phase4v3-stage1-ch1-on-10L
cp hardware/kicad/pcbai_fpv4in1.kicad_pcb /tmp/in.kicad_pcb

# 2. Run cooperative router on dense fan-in subset
python3 hardware/kicad/scripts/route_subsystem_cooperative.py \
  /tmp/in.kicad_pcb \
  --subsystem CH1 \
  --output /tmp/out.kicad_pcb \
  --seed-nets BEMF_B_CH1,BEMF_C_CH1,CSA_A_OUT_CH1,CSA_B_OUT_CH1,CSA_C_OUT_CH1,PWM_INHA_CH1,PWM_INLA_CH1,PWM_INHB_CH1,PWM_INLB_CH1,PWM_INHC_CH1,PWM_INLC_CH1,SWDIO_CH1,SWCLK_CH1,NRST_CH1,BOOT0_CH1 \
  --max-iterations 25 \
  --report /tmp/coop_report.csv

# 3. Apply to canonical
cp /tmp/out.kicad_pcb hardware/kicad/pcbai_fpv4in1.kicad_pcb

# 4. Audit gate
python3 hardware/kicad/scripts/audit_routing.py hardware/kicad/pcbai_fpv4in1.kicad_pcb --subsystem CH1
python3 hardware/kicad/scripts/audit_power_drc.py hardware/kicad/pcbai_fpv4in1.kicad_pcb

# 5. If unrouted nets remain: re-run on stragglers in isolation, then merge

# 6. Commit + PR per worker R-process
```

## References

- [[reference-cascading-escape-needs-negotiated-routing]] — design rationale
- [[reference-kicad-dsn-export-drops-inner-layers]] — why not Freerouter
- [[reference-qfn-pin-escape-bottleneck]] — dog-bone fanout topology
- [[feedback-build-routing-system-not-freerouter]] — Sai 2026-05-24 directive
- [[feedback-codify-not-patch]] — this doc + audit gate satisfy the 3-artifact rule
- McMurchie + Ebeling 1995, "PathFinder: A Negotiation-Based
  Performance-Driven Router for FPGAs" — algorithmic precedent
