# PCB project starter kit

This repo is the working base for a **Claude-driven PCB design project**, run with a
**master / worker** pair of Claude sessions plus a human project owner.

It is a *starter kit* — it carries the rules, the rigor discipline, the master/worker
protocol, the PCB design-phase structure, and the hard-won lessons from a prior
project. It does **not** yet contain a specific PCB. The project owner briefs the
master on what the board is; the master records it in `CLAUDE.md §2` and the work
begins.

## Read order (cold start)

1. `CLAUDE.md` — the bootstrap: the master/worker model, the rules, the working style.
2. `docs/ENGINEERING_RIGOR.md` — the non-negotiable commitments.
3. `docs/MASTER_WORKER_PROTOCOL.md` — how master and worker communicate + coordinate.
4. `docs/NOVA_COORD_SETUP.md` — deploying this project's coordination server.
5. `docs/DESIGN_PHASES.md` — the PCB design-phase structure (the canonical plan).
6. `docs/PCB_PLAYBOOK.md` — the toolchain + the hard-won routing / manufacturability / sim lessons.

## The model in one line

The **project owner** sets direction. The **master** orchestrates, reviews, gates, and
adjudicates. The **worker** executes the hands-on work (KiCad, sims, builds, fab files).
Master and worker each run as a Claude session; they talk over a small coordination
server. Every phase passes a verification gate before the next begins.

## First steps for a new project

1. Project owner briefs the master on the PCB (function, interfaces, constraints).
2. Master records the project identity + system context in `CLAUDE.md §2` and writes
   a project-specific interface/requirements doc.
3. Master + worker stand up the toolchain and the coordination channel
   (`docs/MASTER_WORKER_PROTOCOL.md`).
4. Work proceeds phase by phase per `docs/DESIGN_PHASES.md`, gated.
