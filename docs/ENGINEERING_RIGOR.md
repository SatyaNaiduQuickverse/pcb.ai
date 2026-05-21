# Engineering rigor — non-negotiables

These commitments bind the master and the worker on every session. They exist to
prevent quiet downscoping when the work gets hard. Changing any of them requires a
PR to this file with technical justification and the project owner's approval.

## 1. The simulation regime is the plan, not a suggestion

Every simulation sub-phase in `DESIGN_PHASES.md` runs. Skipping one requires a PR to
this file recording **what** was skipped, **when**, and **what risk was accepted**.
No quiet downscoping in chat or commit messages.

## 2. Failing sims change the design, not the pass criteria

If a sim says "<5 % rail droop" and the design droops 12 %, the design changes.
Adjusting a pass criterion mid-project requires a PR with technical justification —
never "we got tired of waiting."

## 3. Confidence ratings only go up by evidence

A subsystem's confidence rises because a sim passed, a reference audit matched, or a
bench measurement landed — never because it has been discussed enough.

## 4. Simulations are validated before their verdicts are trusted

A sim is only as good as its validation. Before a sim's verdict on this board is
trusted, the sim must be checked against a known reference — a canonical/analytical
benchmark (NAFEMS thermal cases, Hammerstad-Jensen / Pozar impedance, vendor EVM
data) and, where one genuinely exists, a known reference PCB / published design.
Where no good reference exists, say so plainly and treat the bench measurement as
the ground truth — do not overclaim.

## 5. The fab order requires explicit owner sign-off

No autonomous authority for the fab order. It is the real-money gate — only the
project owner's explicit, typed sign-off authorizes it.

## 6. Re-loops between layout and simulation are expected

Sim failures route back to layout. That is not a project failure — it is the
process working. The failure mode is *avoiding* the re-loop by relaxing a spec.

## 7. External review for low-confidence subsystems

Every subsystem that cannot be validated against a reference or a sim goes through
external review (the relevant hardware community / an EE second opinion) before the
fab order. Optional for high-confidence subsystems.

## 8. Brutal honesty, mode-locked

Reports state what was checked AND what was not. "Looks clean" without enumeration
is a violation. Pushback over flattery, explicit gaps over false coverage, "I don't
know" over confident filler.

## 9. Task contracts gate sub-phase work

Every sub-phase has a contract (inputs, outputs, pass criteria) agreed before work
starts. Scope expansion without updating the contract first is a scope violation.

## 10. Grep-then-state, never state-then-grep

Every assertion about external state — file contents, build hashes, PR diffs, pin
assignments, fab specs — is preceded by a fresh read/grep/lookup, not a memory
recall. Both master and worker are bound by this.

## 11. Verification gates are real

Phase acceptance criteria gate phase transitions. The master audits the worker's
output against the criteria before the next phase opens, and reports what was
verified AND what was not. A gate is not a formality.

## Modifying this file

Requires a PR, technical justification in the description, and the owner's
approval. Deliberately heavy — if commitments can be quietly edited, they aren't
commitments.
