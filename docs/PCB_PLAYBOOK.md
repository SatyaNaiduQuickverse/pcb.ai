# PCB playbook — toolchain + hard-won lessons

Distilled from a prior project. These are the things that cost real time to learn.
Read this before routing or before a manufacturability pass — it will save the same
pain.

## Toolchain

- **KiCad 9** — schematic + PCB; plain-text S-expression sources, committed.
- **SKiDL** — netlist generation from Python (note: `generate_schematic()` does not
  scale past trivial circuits — use netlist-only mode for anything real).
- **kinet2pcb** — netlist → KiCad board.
- **Freerouting v2.2.4** — autorouter (Specctra DSN/SES). See the routing recipe below.
- **Sim stack** — Elmer FEM (thermal + structural FEA), OpenEMS (3D FDTD EM),
  ngspice / PySpice (circuit), scikit-rf (transmission-line / S-parameter).
- **InteractiveHtmlBom** — BOM/assembly visualization.
- Export pipeline: scripted (`kicad-cli`), never click-exported.

## Routing — the recipe

Routing is the hardest, least-predictable phase. What works:

- **6-layer stack-up: signals on the two outer layers only; the four inner layers
  are solid planes.** Confirm the stack-up before routing.
- **Constrain the autorouter to the signal layers from the start.** A signal routed
  onto a plane layer cuts a void through that plane — catastrophic for signal
  integrity and EMC. The clean way to enforce it with Freerouting: export the DSN
  with **only the signal layers** in the `(structure)` section — omit the inner
  plane layers entirely. The router then physically cannot misroute onto a plane,
  and the malformed-DSN hangs are avoided. The plane fills are re-added in KiCad
  after the SES import.
- **Outer-layer GND pours.** Flood the unused outer-layer area with GND. A board
  *without* them forces every GND pad to need its own dedicated via — and in dense
  regions those vias don't fit. With the pour, GND pads connect by simply touching
  it. (Keep the pour cleared back from any controlled-impedance pair so it stays a
  clean microstrip.)
- **Plane stitching: vias on short stubs OUTSIDE component pads — never via-in-pad.**
  Standard fab processes do not allow via-in-pad without an extra (paid) process.
  For a power/ground pad, a short fanout stub to a via in clear space is the correct
  technique; a GND pad only needs to *touch* GND copper (trace, pour, or via).
- **Controlled-impedance nets** need a post-route geometry check — DRC does not
  catch "signal routed on the wrong layer / wrong reference." Verify layer,
  reference plane, width/spacing, and length-match explicitly.
- **Minimize rip operations.** Accumulated blanket "clean dangling copper" runs can
  silently delete load-bearing segments. Add-only where possible; DRC-verify after
  every operation; revert on a new error; commit labelled checkpoints frequently;
  never bulk-delete copper without confirming each item is genuinely an orphan.

## Manufacturability — match the fab, don't assume

- **The DRC ruleset must match the actual fab's capability spec — exactly.** A
  project ruleset laxer than the fab means "0 DRC errors" is *false comfort*: the
  board can pass the project's DRC and still violate the fab. Use the fab's
  published rule file where one exists; otherwise build the ruleset from the fab's
  capability doc and cite the source.
- Audit **every** rule, not a sample: min trace/space, min drill, min via diameter,
  **min annular ring**, **min hole-to-hole**, track-to-hole, edge clearance,
  soldermask sliver/dam, silkscreen line width / text height, drill sizes.
- **Via geometry must meet the annular-ring spec.** A via that is barely larger than
  its drill fails the annular-ring rule — size it properly.
- **Verify the BOM against the fab's assembly library** if ordering an assembled
  board — every part in-library (basic vs extended), or flagged for hand-solder.
- Silkscreen-over-pad and similar: the fab usually auto-clips on export — verify the
  *exported gerber* is clean rather than assuming, and document it.
- The final pre-order check is the fab's own DFM analyzer at upload time — the
  project owner runs that at the fab-order step.

## Simulation — validate before you trust

- A sim's verdict is worthless until the sim is validated. Validate each sim against
  a canonical benchmark (NAFEMS thermal cases, Hammerstad-Jensen / Pozar for
  impedance, vendor EVM data, a known reference design) before trusting its verdict
  on the real board. Where no good reference exists, say so and lean on the bench.
- Never loosen a pass criterion to make a sim pass — the design changes, not the
  criterion (`ENGINEERING_RIGOR.md §2`).
- If a 3D-EM solver won't converge on fine geometry in a bounded attempt, the
  validated analytical method + the bench measurement are the honest floor — don't
  fake a result.

## Known traps

- **Signals on plane layers** — cuts the reference planes; degrades SI/EMC board-
  wide. Constrain the router (above).
- **A lax DRC ruleset** — "0 DRC" against the wrong rules means nothing.
- **Via-in-pad assumed free** — it is a paid fab process; design vias outside pads.
- **Blanket copper deletion** — silently breaks nets; verify before deleting.
- **Cross-doc inconsistency** — when a spec lives in two docs, they drift; on any
  change, check every doc that references it.
- **Trusting a pin-budget count without checking alternate-function conflicts** — a
  "free peripheral" may have every pin option blocked by other assignments.
- **Connector physical accessibility not checked** — a connector set in from the board
  edge, or a mid-mount with no Edge.Cuts cutout, is *unpluggable*: the cable / card /
  plug cannot physically reach it. A board render does not make this obvious. At the
  placement gate, verify every connector's edge position and orientation explicitly,
  one by one — and confirm any mid-mount part has its required edge cutout.
- **Placement not validated for routability** — the most expensive trap. A placement
  can pass DRC, clearance, connector-access, and thermal checks and still be
  *routing-hostile*: the autorouter plateaus far short of 100% and the residual nets
  will not close. Routing difficulty is a *placement symptom*, not a routing problem —
  do not try to out-engineer it with cleverer routers. Prevention:
  - Do a **connectivity / net-flow analysis first** — tabulate which peripheral
    connects to which *side* of the hub chip (MCU) by package pin.
  - **Place each peripheral on the MCU side its pins exit.** A peripheral opposite its
    pins forces every net across the chip — that congestion strands the residual.
  - Identify **pin-locked vs movable** functions (e.g. SDMMC / USB / HSE crystal are
    typically pin-locked — they anchor the placement; muxable buses flex around them).
    Re-assigning MCU pins to suit the layout is normal, correct engineering.
  - The **placement gate must include a route-validation**: run the autorouter; it
    must reach ~100%. A low plateau is the diagnosis — re-place, do not brute-force.
  - Placement is multi-physics: weigh routability, EMI (separate switching/clock/
    high-speed aggressors from sensor/analog victims), thermal, SI, and mechanical
    explicitly — and simulate candidates *during* placement, not only at the gate.
