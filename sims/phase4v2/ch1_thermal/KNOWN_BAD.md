# KNOWN BAD — Phase 4-v2 CH1 thermal sim (OQ-015)

**Status**: KNOWN BAD — DO NOT TRUST NUMBERS in this directory.

**Symptom**: `ch1_global.dat` reports 36,236°C — physically impossible (FR4 Tg = 135°C, melt = 270°C).

**Root cause** (worker-discovered 2026-05-26 — see [`docs/OPEN_QUESTIONS.md`](../../../docs/OPEN_QUESTIONS.md) OQ-015):

1. Mesh boundary condition: parent columns held at fixed parent-temp instead of free-conv ambient → adiabatic enclosure → unbounded heat-rise.
2. Heat source units: W/kg specific power applied to volumetric mesh nodes; correct unit is W/m³. Off by factor of ρ_FR4 = 1850 (FR4 density) → 1850× over-estimation.

**Superseded by**: [`sims/phase4v3/ch1_thermal/`](../../phase4v3/ch1_thermal/) — Phase 4-v3 CH1 with both bugs fixed, real Elmer FEM result T_J = 54.65°C continuous / 89.28°C burst.

**Why kept**: historical lesson — see [[feedback-codify-not-patch]] + [[feedback-root-cause-not-symptom]]. Deleting hides the bug class. `audit_sim_result_sanity.py` (G_S3) honors `KNOWN_BAD.md` sentinel and skips this dir.

**Audit-suite exemption rationale**: this directory contains a documented-bad artifact retained for lesson-preservation; not a silent skip — the KNOWN_BAD.md presence is the exemption record.
