# Design phases — the canonical execution plan

All design-time work lives in one of the phases below. If a task doesn't fit a
phase, raise it rather than improvising — chat-only phase labels evaporate across
sessions. **This doc is the source of truth.**

Each phase has acceptance criteria that gate the transition to the next. No phase
skipping. One sub-phase = one PR. The master audits each phase against its criteria
before the next opens (`ENGINEERING_RIGOR.md §11`).

## Phase 0 — Toolchain

Install + smoke-test the toolchain on the worker machine: KiCad 9, the netlist /
schematic tooling, the autorouter, the simulation stack, the export tooling. Record
versions + install paths. *Acceptance:* every tool runs a smoke test clean.

## Phase 1 — Identity / firmware base (if applicable)

For a board that runs existing firmware (e.g. an autopilot): fork the board
definition, set the board ID / USB strings, baseline a clean build. *Acceptance:*
build clean; identity correct. (Skip if the board has no such firmware.)

## Phase 2 — Pin map + part selection

Assign the MCU/controller pin map; select every active part. Sensors/ICs must have
driver/software support where firmware will use them — verify it, don't assume.
*Acceptance:* pin map complete and conflict-free; every part vetted (function, fab
availability, datasheet, package).

## Phase 2.5 — Footprint / fit reality check

A cheap placement-only sketch to confirm everything physically fits the intended
form factor before schematic decisions cascade. *Acceptance:* fit confirmed plausible.

## Phase 3 — Schematic

Capture the schematic, per-sheet, one sub-phase per PR. The pin map is authoritative
— schematic ↔ pin-map mismatch is a stop-and-raise. *Acceptance:* ERC clean; netlist
parses; matches the pin map.

## Phase 3.5 — Reference-design audit

Cross-check each subsystem against ≥3 open reference designs. References agree →
match them. References diverge → pick one, document why. No reference exists →
subsystem is novel, confidence stays low, routes to external review. *Acceptance:*
no unresolved NEEDS-FIX items.

## Phase 4 — Placement

Physics-guided placement: separate the subsystems (power / sensitive analog /
digital / connectors), generous spacing, size the board to the placement. Sim-
validate the placement (thermal, EMI) before routing. *Acceptance:* placement
sim-validated; thermal/EMC margins met.

## Phase 5 — Routing

Route the placed board (autorouter + hand-routing of critical nets). On a 6-layer
board, signals on the outer layers, inner layers as solid reference/power planes.
See `PCB_PLAYBOOK.md` for the routing recipe. *Acceptance:* DRC clean against a
fab-matched ruleset; 0 unconnected; controlled-impedance nets verified.

## Phase 6 — Simulation regime

Every subsystem simulated — power, signal integrity, thermal, EMC, manufacturability
— at nominal/hot/cold corners. Sims validated per `ENGINEERING_RIGOR.md §4`. Sim
failures re-loop to Phase 4/5 — expected. *Acceptance:* every sim passes or has a
PR-justified disposition.

## Phase 6.5 — External review

Post the design + sim results for external review (the relevant hardware community /
an EE second opinion). Mandatory for low-confidence subsystems. *Acceptance:*
findings addressed.

## Phase 7 — Fab-ready freeze + fab order

- **7a — Freeze:** when the design is genuinely fab-ready (DRC/ERC clean, all sims
  dispositioned, gerbers export clean, BOM final, manufacturability verified), tag
  the validated design. This is the surely-works baseline.
- **7b — Fab order:** generate gerbers/drill/pick-place, order. **Requires the
  project owner's explicit sign-off** — the real-money gate (`ENGINEERING_RIGOR §5`).

## Phase 7.5 — Optimization (optional, post-freeze)

After the freeze, optionally shrink/optimize the board incrementally — sim-driven,
keeping a factor of safety, with the frozen baseline as the fallback.

## Phase 8 — Assembly

Assembled board (fab assembly or hand). Continuity-check power rails before first
power-up. *Acceptance:* ≥1 populated board, visual + meter pass.

## Phase 9 — Bring-up

Phased, do not skip a step: power-on / blink → peripheral roll-call → host
enumeration → firmware → bench validation → first constrained operation → full
operation. Each step gates the next.
