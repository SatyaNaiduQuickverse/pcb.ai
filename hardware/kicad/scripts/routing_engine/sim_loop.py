#!/usr/bin/env python3
"""sim_loop.py — Engine Step 7: the SIM-INTELLIGENCE LOOP (the SOTA differentiator).

Engine Step 7 of docs/ROUTING_ENGINE_DESIGN_2026-05-28.md §1 + §3 and
ROUTING_METHODOLOGY.md §0b "SOTA via SIM-INTELLIGENCE" + §7.

WHAT THIS IS (the two-layer split, made structural)
====================================================
Classical routers optimise an ABSTRACT overflow count with pure logic. Ours puts
REAL physics in the decision loop. But "real physics in the loop" splits into two
fundamentally different roles, and CONFLATING them is the failure mode this module
exists to prevent:

  ┌─ PROXY LAYER (fast, analytical, INNER LOOP) ──────────────────────────────┐
  │  Closed-form physics_primitives (IPC-2152 ampacity, Hammerstad-Jensen Z0,  │
  │  crosstalk_db, loop_inductance_nH, corner_current_crowding_factor,         │
  │  length_skew_ps). CHEAP — runs thousands of times to RANK candidates and   │
  │  INFORM engine decisions. It is ADVISORY. It is NEVER a verdict. A number   │
  │  it produces can be wrong by tens of percent and that is FINE — its job is  │
  │  to order work + flag where to spend complexity, not to certify the board. │
  └────────────────────────────────────────────────────────────────────────────┘
  ┌─ STRONG-SIM LAYER (openEMS / Elmer / ngspice, the BINDING SOURCE OF TRUTH) ┐
  │  The ONLY thing allowed to emit a binding VERDICT. A verdict is accepted    │
  │  ONLY if a real solver artifact set PASSES the sim-execution-gate           │
  │  ([[feedback-sim-execution-gate]], R18): result file present + result mtime │
  │  ≥ input mtime + extract-script output present + literal exec command       │
  │  present — AND provenance ([[feedback-sim-artifact-must-be-canonical]],     │
  │  R-sim-provenance): git-tracked, SHA-reproducible, NO /tmp citation.        │
  │  A proxy number, a guessed number, a stale artifact, a missing result, an   │
  │  artifact in /tmp — ALL REFUSED. The model CANNOT pass off a guess as a     │
  │  verdict; the gate is structural, not a discipline you have to remember.    │
  └────────────────────────────────────────────────────────────────────────────┘

WHICH PROXY INFORMS WHICH ENGINE DECISION (the documented mapping)
==================================================================
  decision                         proxy primitive(s)               consumer
  ───────────────────────────────  ───────────────────────────────  ──────────────
  net ordering (most-critical 1st) loop_inductance_nH, crosstalk_db, run_suite net
                                    length_skew_ps → criticality      ordering / Phase B
  WHERE to spend geometry          corner_current_crowding_factor →  Phase C §5b
   (which corner gets a fillet)     local fillet trigger              local-fillet
  WHEN to escalate to HDI          loop_inductance_nH over the FET-   Phase A / B
                                    cluster budget + ampacity         escalation
                                    (min_track_width_mm) over supply
  matched-bus meander budget       length_skew_ps vs timing budget    Phase C T7

  NONE of these EMIT a verdict. Each returns an ADVICE record the engine consumes.
  The BINDING confirmation of every one of these decisions is a STRONG sim
  (ROUTING_METHODOLOGY §7 per-tier table), gated by `binding_verdict()` below.

WHEN PROXY AND STRONG DISAGREE (the learning loop)
==================================================
A proxy disagreeing with the strong sim by more than tolerance is a LESSON, not a
crisis: `proxy_strong_divergence()` flags it (the engine writes a proposed
ROUTING_LESSONS.md entry); the STRONG sim governs the verdict regardless. The
proxy is then recalibrated. The proxy never overrides the strong sim.

PI-SHARED-MACHINE NOTE
======================
This module BUILDS + UNIT-TESTS the framework, the proxies, and the gate. It does
NOT launch any heavy solver (openEMS/Elmer/ngspice are CPU-heavy and the Pi is
shared with a co-tenant, [[feedback-pi-shared-system-protect]]). The actual strong-
sim RUNS happen at Step 8 / CH1 on real geometry on external x86
([[feedback-pi-bounded-subsystem-scope]]). The self-test exercises the gate with
SYNTHETIC artifact sets in a temp dir it creates + cleans — citing NOTHING in /tmp
as a committed artifact.

Pure Python stdlib + `physics_primitives` (+ the existing audit modules, imported
for the gate so the gate logic is SINGLE-SOURCED, never re-implemented). Not named
audit_/verify_ (meta-safe); lives in routing_engine/ (not scanned by
audit_meta_coverage which only lists scripts/ root). Touches no hash-locked doc.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --- physics proxy primitives (the fast inner loop) -------------------------
# Robust import whether run as a module or a loose script.
_SCRIPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import physics_primitives as PHYS  # noqa: E402

# --- the BINDING gate logic, SINGLE-SOURCED from the existing audits --------
# We do NOT re-implement the 4-point check or the provenance regex — we import
# the exact functions the master gate runs, so the engine's binding gate and the
# master's pre-merge gate can NEVER drift apart.
import audit_sim_execution as SIMEXEC          # noqa: E402  (4-point check)
import audit_sim_artifact_provenance as PROV   # noqa: E402  (no /tmp, SHA-repro)


# ============================================================================
# RESULT VOCABULARY
# ============================================================================

# The proxy layer NEVER returns these. They belong to the strong-sim gate only.
VERDICT_VOCAB = ("ROUTABLE", "INFEASIBLE", "CONDITIONAL",
                 "NEEDS-HDI", "NEEDS-PLACEMENT-CHANGE", "PASS", "FAIL")

# What the gate returns when an artifact set is NOT a valid strong-sim proof.
# It is a SENTINEL, not a verdict — the engine must treat it as "no verdict yet",
# never as a pass.
NOT_VERIFIED = "NOT-VERIFIED"


class SimVerdictError(Exception):
    """Raised by `binding_verdict(..., strict=True)` when a verdict is REFUSED:
    the artifact set is a proxy result, or is fabricated / stale / missing /
    non-canonical. Structurally prevents passing off a non-strong-sim number as
    a binding verdict."""


# ============================================================================
# PROXY LAYER — fast analytical advice (NON-BINDING, inner loop)
# ============================================================================

@dataclass
class NetProxy:
    """Inner-loop physics ADVICE for one candidate net routing. Every field is a
    proxy (closed-form) estimate — ADVISORY, never a verdict. `criticality` is the
    engine's net-ordering key (higher = route earlier / reserve capacity first)."""
    net_id: str
    loop_nH: Optional[float] = None        # commutation/return loop inductance
    crosstalk_db: Optional[float] = None   # worst coupled-line crosstalk (more -ve = better)
    skew_ps: Optional[float] = None        # length-match skew vs its group reference
    min_width_mm: Optional[float] = None   # ampacity-required width (IPC-2152)
    criticality: float = 0.0               # ordering key (computed below)
    notes: List[str] = field(default_factory=list)


def score_net(net_id, *, loop_geom=None, crosstalk_geom=None, skew_geom=None,
              ampacity=None) -> NetProxy:
    """PROXY: score ONE candidate net routing from its geometry, producing the
    inner-loop ADVICE record. Each kwarg is an optional dict of geometry; only the
    physics relevant to the net is evaluated. NON-BINDING — informs net ordering
    (criticality) and width, never a verdict.

      loop_geom      = {length_mm, spacing_mm, width_mm[, height_mm]}
                       -> loop_inductance_nH  (commutation/return-loop criticality)
      crosstalk_geom = {W_mm, sep_mm, length_mm, freq_hz[, εr, h_mm]}
                       -> crosstalk_db        (victim-net criticality)
      skew_geom      = {length_a_mm, length_b_mm, eps_eff | εr, line_type}
                       -> length_skew_ps      (matched-bus criticality)
      ampacity       = {I_amps, layer_type[, cu_oz, dT_celsius]}
                       -> min_track_width_mm  (width demand; HDI-escalation input)

    Criticality (the net-ordering key) is a normalised sum of the active physics
    pressures — a net with a high loop-L, tight crosstalk, large skew, or a wide
    ampacity demand is MORE constrained and is ordered/reserved first (most-
    constrained-first, ROUTING_METHODOLOGY §0b). Weights are advisory tuning, not
    physics law; the STRONG sim is the source of truth for the actual values.
    """
    px = NetProxy(net_id=net_id)
    crit = 0.0
    if loop_geom:
        px.loop_nH = PHYS.loop_inductance_nH(**loop_geom)
        crit += px.loop_nH                         # nH-scale pressure
        px.notes.append(f"loop-L {px.loop_nH:.3f}nH (proxy, Paul §5.2)")
    if crosstalk_geom:
        px.crosstalk_db = PHYS.crosstalk_db(**crosstalk_geom)
        # more-positive dB (= closer to 0 = worse coupling) ⇒ higher criticality.
        crit += max(0.0, (px.crosstalk_db + 60.0) / 10.0)
        px.notes.append(f"crosstalk {px.crosstalk_db:.1f}dB (proxy)")
    if skew_geom:
        px.skew_ps = PHYS.length_skew_ps(**skew_geom)
        crit += px.skew_ps / 10.0                  # ps-scale pressure
        px.notes.append(f"skew {px.skew_ps:.2f}ps (proxy, HJ Ch.4)")
    if ampacity:
        px.min_width_mm = PHYS.min_track_width_mm(**ampacity)
        crit += px.min_width_mm                     # mm-scale width pressure
        px.notes.append(f"ampacity width {px.min_width_mm:.3f}mm (proxy, IPC-2152)")
    px.criticality = round(crit, 6)
    return px


def order_nets(net_proxies: List[NetProxy]) -> List[str]:
    """PROXY → DECISION: net ordering. Returns net_ids sorted MOST-CONSTRAINED
    FIRST (descending criticality). This is the advisory ordering the engine /
    Phase B consumes; the binding correctness of the resulting routing is a STRONG
    sim. Deterministic tie-break on net_id for reproducibility."""
    return [p.net_id for p in sorted(net_proxies,
                                     key=lambda p: (-p.criticality, p.net_id))]


# --- where to spend geometric complexity: the local-fillet trigger ----------

# Above this proxy crowding factor a high-current corner is flagged for a sim-
# driven local fillet (ROUTING_METHODOLOGY §5b — NO global chamfer rule; spend
# complexity only where the physics says so). Advisory threshold.
FILLET_CROWD_THRESHOLD = 1.5


@dataclass
class FilletAdvice:
    corner_id: str
    crowd_factor: float
    needs_fillet: bool
    suggested_radius_mm: float
    rationale: str


def advise_corner_fillet(corner_id, bend_angle_deg, inner_radius_mm, width_mm,
                         current_a=0.0) -> FilletAdvice:
    """PROXY → DECISION: WHERE to spend geometry. Uses
    corner_current_crowding_factor to decide if THIS corner (carrying current_a)
    needs a local fillet. High-current sharp corners crowd current on the inner
    edge (Brooks); a fillet relieves it. Returns advice + a suggested radius that
    would pull the crowd factor under the threshold. NON-BINDING — the binding
    confirmation is a near-field/current-density STRONG sim (openEMS / Elmer)."""
    crowd = PHYS.corner_current_crowding_factor(bend_angle_deg, inner_radius_mm, width_mm)
    needs = crowd > FILLET_CROWD_THRESHOLD and current_a > 0.0
    # Suggest the smallest radius (multiple of width) that gets crowd under thresh.
    suggested = inner_radius_mm
    if needs:
        r = inner_radius_mm
        for _ in range(40):                  # bounded search (advisory)
            r += 0.1 * width_mm
            if PHYS.corner_current_crowding_factor(bend_angle_deg, r, width_mm) <= FILLET_CROWD_THRESHOLD:
                break
        suggested = round(r, 4)
    return FilletAdvice(
        corner_id=corner_id, crowd_factor=round(crowd, 4), needs_fillet=needs,
        suggested_radius_mm=suggested,
        rationale=(f"crowd {crowd:.2f}× {'>' if needs else '<='} thresh "
                   f"{FILLET_CROWD_THRESHOLD}; current {current_a}A "
                   + ("→ FILLET (Brooks inner-edge crowd relief)" if needs
                      else "→ no fillet (uniform enough)")))


# --- when to escalate to HDI: the proxy pre-flag (Phase A/B input) ----------

@dataclass
class HDIAdvice:
    region_id: str
    escalate: bool
    reasons: List[str]
    loop_nH: Optional[float] = None
    width_demand_mm: Optional[float] = None


def advise_hdi_escalation(region_id, *, loop_geom=None, loop_budget_nH=None,
                          ampacity=None, width_supply_mm=None) -> HDIAdvice:
    """PROXY → DECISION: WHEN to escalate to HDI. If the proxy commutation loop-L
    exceeds the per-region budget, OR the ampacity-required width exceeds the
    available routing width supply, the region is FLAGGED for HDI/placement
    escalation BEFORE geometry is drawn (cheap early warning). NON-BINDING: the
    binding feasibility VERDICT is Phase A's escape ledger (counting) + the STRONG
    sim. This proxy only RAISES the flag early so Phase A/B can act."""
    reasons = []
    px = HDIAdvice(region_id=region_id, escalate=False, reasons=reasons)
    if loop_geom is not None and loop_budget_nH is not None:
        px.loop_nH = PHYS.loop_inductance_nH(**loop_geom)
        if px.loop_nH > loop_budget_nH:
            px.escalate = True
            reasons.append(f"loop-L {px.loop_nH:.3f}nH > budget {loop_budget_nH}nH "
                           "(tighten cluster / HDI via-in-pad shortens the loop)")
    if ampacity is not None and width_supply_mm is not None:
        px.width_demand_mm = PHYS.min_track_width_mm(**ampacity)
        if px.width_demand_mm > width_supply_mm:
            px.escalate = True
            reasons.append(f"ampacity width {px.width_demand_mm:.3f}mm > supply "
                           f"{width_supply_mm}mm (needs plane / more layers / HDI)")
    if not reasons:
        reasons.append("proxy within budgets — no early HDI flag (Phase A still gates)")
    return px


def proxy_strong_divergence(proxy_value, strong_value, rel_tol=0.20) -> dict:
    """The LEARNING LOOP. Compare a PROXY value against the STRONG-sim value for the
    same metric. Returns a record flagging divergence beyond `rel_tol`. The STRONG
    value GOVERNS regardless; a divergence is a proposed ROUTING_LESSONS.md entry
    (recalibrate the proxy), never a reason to distrust the strong sim."""
    if strong_value == 0:
        rel = 0.0 if proxy_value == 0 else float("inf")
    else:
        rel = abs(proxy_value - strong_value) / abs(strong_value)
    diverged = rel > rel_tol
    return {
        "proxy_value": proxy_value,
        "strong_value": strong_value,
        "rel_error": rel,
        "diverged": diverged,
        "governs": "strong",
        "action": ("PROPOSE ROUTING_LESSONS.md entry + recalibrate proxy "
                   "(strong sim governs the verdict)" if diverged
                   else "proxy tracks strong within tolerance"),
    }


# ============================================================================
# STRONG-SIM VERDICT GATE — the BINDING source of truth.
# A verdict is emitted ONLY when a real strong-sim artifact set PASSES the
# sim-execution-gate (4-point) AND provenance. Everything else is REFUSED.
# ============================================================================

@dataclass
class SimSpec:
    """Describes a STRONG-sim run whose artifacts are being offered as a binding
    verdict. The gate verifies these artifacts EXIST + are fresh + reproducible —
    it does NOT trust the caller's claimed verdict until the artifacts prove it.

      sim_dir      : directory holding the strong-sim artifacts. MUST be a git-
                     tracked path (no /tmp, no /var/tmp, no scratch) per
                     [[feedback-sim-artifact-must-be-canonical]].
      tier         : ROUTING_METHODOLOGY §7 tier this sim certifies (1..6) — used
                     only for the human-readable record.
      claimed_verdict : the verdict the caller proposes. ACCEPTED only if the
                     4-point + provenance gate PASSES; otherwise REFUSED.
      is_proxy     : if True, this is a PROXY result masquerading as a verdict —
                     the gate REFUSES it outright (a proxy is never binding).
      solver       : 'openems' | 'elmer' | 'ngspice' (record only).
    """
    sim_dir: str
    tier: int
    claimed_verdict: str
    is_proxy: bool = False
    solver: str = ""


# The git-tracked repo root — a sim_dir is SHA-reproducible iff it resolves to a
# path UNDER this root (that is the precise meaning of "reproducible from the
# repo SHA alone", [[feedback-sim-artifact-must-be-canonical]]). Computed from
# this file's location so it is correct wherever the repo is checked out.
REPO_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


def _provenance_ok(sim_dir: str, repo_root: str = REPO_ROOT) -> Tuple[bool, List[str]]:
    """R-sim-provenance check ([[feedback-sim-artifact-must-be-canonical]]). Two
    parts, both required:

      (1) LOCATION: sim_dir must resolve to a path UNDER the git-tracked repo root
          (that IS "reproducible from the repo SHA alone"). A path outside the repo
          — /tmp scratch, ~/Downloads, a sibling workspace — is NON-canonical. The
          location is judged by repo-containment, NOT by string-matching '/tmp'
          (so a repo checked out under /tmp for testing is still judged by whether
          the sim_dir is INSIDE that repo, which is the real reproducibility test).
      (2) CONTENT: no artifact file under sim_dir may CITE a forbidden non-canonical
          path (/tmp, /var/tmp, scratch, Downloads, a foreign workspace) — the
          regex is SINGLE-SOURCED from audit_sim_artifact_provenance.FORBIDDEN_PATTERNS
          (the exact master gate), so the two can never drift.

    Returns (ok, [violation lines])."""
    import re
    from pathlib import Path
    fails = []
    root = Path(sim_dir)
    if not root.exists():
        return False, [f"sim_dir does not exist: {sim_dir}"]
    # (1) LOCATION: must be inside the repo (SHA-reproducible).
    abs_dir = os.path.realpath(sim_dir)
    abs_repo = os.path.realpath(repo_root)
    if os.path.commonpath([abs_dir, abs_repo]) != abs_repo:
        fails.append(f"sim_dir is OUTSIDE the git-tracked repo (not SHA-"
                     f"reproducible): {sim_dir}")
    # (2) CONTENT: no forbidden non-canonical citations inside the artifacts.
    pattern = re.compile("|".join(f"(?:{p})" for p in PROV.FORBIDDEN_PATTERNS))
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        if (fp.suffix.lower() not in PROV.SCAN_EXTS
                and "README" not in fp.name and "RESULTS" not in fp.name):
            continue
        try:
            for lineno, line in enumerate(open(fp, errors="ignore"), 1):
                if pattern.search(line):
                    fails.append(f"{fp.name}:{lineno}: {line.strip()[:100]}")
        except Exception:
            continue
    return (len(fails) == 0), fails


@dataclass
class BindingResult:
    """The gate's output. `verdict` is a real verdict string ONLY when accepted;
    otherwise it is NOT_VERIFIED and `accepted` is False with the refusal reasons."""
    accepted: bool
    verdict: str
    reasons: List[str]
    four_point: List[Tuple[str, str, str]] = field(default_factory=list)
    provenance: List[str] = field(default_factory=list)
    sim_dir: str = ""
    tier: int = 0


def binding_verdict(sim_spec: SimSpec, strict: bool = False) -> BindingResult:
    """THE BINDING GATE. Returns a real verdict ONLY if `sim_spec`'s artifacts
    PASS both the 4-point sim-execution gate (audit_sim_execution.check_sim_dir)
    AND the R-sim-provenance check. Otherwise REFUSES:

      * is_proxy=True            -> REFUSED ("a proxy is never a binding verdict")
      * missing result file      -> REFUSED (4-point fail: sim not executed)
      * result mtime < input     -> REFUSED (4-point fail: stale, not re-run)
      * no extract output        -> REFUSED (4-point fail: number not extracted)
      * no literal exec command  -> REFUSED (4-point fail: not reproducible)
      * /tmp / scratch artifact   -> REFUSED (provenance fail: not SHA-reproducible)

    With strict=True a refusal RAISES SimVerdictError (so a caller cannot silently
    ignore a refused verdict). With strict=False it returns a BindingResult with
    accepted=False, verdict=NOT_VERIFIED.

    The 4-point logic is SINGLE-SOURCED from audit_sim_execution (the master gate),
    so the engine's binding gate and the master's pre-merge gate can never drift.
    """
    reasons: List[str] = []

    # GUARD 0: a proxy result is structurally INELIGIBLE to be a verdict.
    if sim_spec.is_proxy:
        reasons.append("REFUSED: proxy (analytical) result offered as a binding "
                       "verdict — proxies inform the inner loop only; the binding "
                       "verdict MUST come from a strong sim (openEMS/Elmer/ngspice).")
        return _refuse(sim_spec, reasons, strict)

    # GUARD 1: the 4-point sim-execution gate (reused verbatim from the audit).
    four_point = SIMEXEC.check_sim_dir(sim_spec.sim_dir)
    if not four_point:
        reasons.append("REFUSED: no recognised strong-sim INPUT in sim_dir "
                       "(*.sif / *.cir / openems_*.py) — nothing was executed.")
        return _refuse(sim_spec, reasons, strict, four_point=four_point)
    failed = [(s, p, w) for (s, p, w) in four_point if s != "PASS"]
    if failed:
        for _, p, w in failed:
            reasons.append(f"REFUSED (4-point): {os.path.basename(p)}: {w}")
        return _refuse(sim_spec, reasons, strict, four_point=four_point)

    # GUARD 2: provenance — canonical, SHA-reproducible, no /tmp.
    prov_ok, prov_fails = _provenance_ok(sim_spec.sim_dir)
    if not prov_ok:
        for f in prov_fails:
            reasons.append(f"REFUSED (provenance): {f}")
        return _refuse(sim_spec, reasons, strict,
                       four_point=four_point, provenance=prov_fails)

    # GUARD 3: the claimed verdict must be a real verdict token (no free-text).
    if sim_spec.claimed_verdict not in VERDICT_VOCAB:
        reasons.append(f"REFUSED: claimed_verdict {sim_spec.claimed_verdict!r} "
                       f"is not in the verdict vocabulary {VERDICT_VOCAB}.")
        return _refuse(sim_spec, reasons, strict, four_point=four_point)

    # ACCEPTED — every gate passed; the strong sim is the source of truth.
    reasons.append(f"ACCEPTED: strong-sim ({sim_spec.solver or 'solver'}) artifact "
                   f"set passed the 4-point sim-execution gate + provenance; "
                   f"verdict {sim_spec.claimed_verdict} is BINDING (tier "
                   f"{sim_spec.tier}, reproducible from repo SHA).")
    return BindingResult(
        accepted=True, verdict=sim_spec.claimed_verdict, reasons=reasons,
        four_point=four_point, provenance=[], sim_dir=sim_spec.sim_dir,
        tier=sim_spec.tier)


def _refuse(sim_spec, reasons, strict, four_point=None, provenance=None):
    res = BindingResult(
        accepted=False, verdict=NOT_VERIFIED, reasons=reasons,
        four_point=four_point or [], provenance=provenance or [],
        sim_dir=sim_spec.sim_dir, tier=sim_spec.tier)
    if strict:
        raise SimVerdictError("; ".join(reasons))
    return res


# ============================================================================
# SELF-TEST — proxy scoring on a fixture + the gate's accept/reject proof.
# Uses ONLY temp files it creates + cleans (no /tmp citation committed).
# Run: python3 routing_engine/sim_loop.py
# ============================================================================

def _make_valid_strong_sim_artifacts(sim_dir):
    """Create a SYNTHETIC but STRUCTURALLY-VALID strong-sim artifact set in
    `sim_dir`: an input (*.cir) older than its result (*.raw), an extract output
    (RESULTS.md) containing a literal exec command + git-tracked path. This is the
    minimal artifact set the master's 4-point + provenance gates accept. NO solver
    is run — we just lay down the artifact shapes to prove the GATE works."""
    import time
    os.makedirs(sim_dir, exist_ok=True)
    cir = os.path.join(sim_dir, "loop_l.cir")
    with open(cir, "w") as f:
        f.write("* ngspice deck (synthetic, gate self-test)\n.tran 1n 1u\n.end\n")
    # Make the result CLEARLY newer than the input (mtime > input).
    older = time.time() - 100
    os.utime(cir, (older, older))
    raw = os.path.join(sim_dir, "loop_l.raw")
    with open(raw, "w") as f:
        f.write("synthetic ngspice rawfile (gate self-test)\n")
    # extract output WITH a literal exec command + a git-tracked artifact path.
    results = os.path.join(sim_dir, "RESULTS.md")
    with open(results, "w") as f:
        f.write("# loop-L strong-sim RESULTS (synthetic)\n\n"
                "Exec command (reproducible):\n\n"
                "    ngspice -b loop_l.cir -r loop_l.raw\n"
                "    python3 extract_loop.py loop_l.raw\n\n"
                "Geometry: hardware/kicad/pcbai_fpv4in1.kicad_pcb (canonical).\n")
    extract = os.path.join(sim_dir, "extract_loop.py")
    with open(extract, "w") as f:
        f.write("#!/usr/bin/env python3\n# synthetic extract script\nprint('L=0.1953nH')\n")
    return {"input": cir, "result": raw, "results": results, "extract": extract}


def self_test() -> int:
    import tempfile
    import shutil
    print("=" * 72)
    print("sim_loop.py — Step 7 sim-intelligence loop self-test")
    print("=" * 72)
    ok = True

    # ---- PART A: PROXY LAYER on a fixture (fast inner-loop scoring) ---------
    print("\n[proxy] net scoring + ordering (NON-BINDING inner loop):")
    # A small fixture of candidate net routings (commutation loop, victim net,
    # matched-bus member, power net) — the physics each net is sensitive to.
    proxies = [
        score_net("PWM_AH_CH1",
                  loop_geom={"length_mm": 0.5, "spacing_mm": 0.4, "width_mm": 0.3}),
        score_net("BEMF_A_CH1",
                  crosstalk_geom={"W_mm": 0.15, "sep_mm": 0.2, "length_mm": 8.0,
                                  "freq_hz": 1e8}),
        score_net("DShot_CH1",
                  skew_geom={"length_a_mm": 50.0, "length_b_mm": 56.0,
                             "eps_eff": None, "line_type": "microstrip", "εr": 4.3}),
        score_net("VMOTOR_CH1",
                  ampacity={"I_amps": 40.0, "layer_type": "external", "cu_oz": 2}),
    ]
    order = order_nets(proxies)
    for p in proxies:
        print(f"    {p.net_id}: criticality {p.criticality:.3f} | {'; '.join(p.notes)}")
    print(f"    ORDER (most-constrained first): {order}")
    # Sanity: the heavy-ampacity power net + the big-skew net dominate ordering;
    # ordering is a permutation of the inputs (advisory, deterministic).
    ok &= set(order) == {p.net_id for p in proxies}
    ok &= order == [p.net_id for p in sorted(proxies, key=lambda q: (-q.criticality, q.net_id))]
    print(f"  {'ok ' if ok else 'XX '}ordering is a deterministic permutation by criticality")

    # ---- PART A2: fillet decision (WHERE to spend geometry) -----------------
    print("\n[proxy] corner-fillet decision (WHERE to spend geometry):")
    sharp = advise_corner_fillet("CORNER_VMOTOR_1", bend_angle_deg=90,
                                 inner_radius_mm=0.0, width_mm=1.0, current_a=40.0)
    gentle = advise_corner_fillet("CORNER_SIG_1", bend_angle_deg=45,
                                  inner_radius_mm=0.0, width_mm=0.15, current_a=0.0)
    print(f"    {sharp.corner_id}: {sharp.rationale}; suggest r={sharp.suggested_radius_mm}mm")
    print(f"    {gentle.corner_id}: {gentle.rationale}")
    c_sharp = sharp.needs_fillet and sharp.suggested_radius_mm > 0
    c_gentle = (not gentle.needs_fillet)
    ok &= c_sharp and c_gentle
    print(f"  {'ok ' if (c_sharp and c_gentle) else 'XX '}high-current sharp 90° → fillet; "
          f"low-current gentle bend → no fillet")

    # ---- PART A3: HDI-escalation pre-flag (WHEN to escalate) ----------------
    print("\n[proxy] HDI-escalation pre-flag (WHEN to escalate):")
    esc = advise_hdi_escalation(
        "CH1_FET_CLUSTER",
        loop_geom={"length_mm": 12.0, "spacing_mm": 2.0, "width_mm": 0.3},
        loop_budget_nH=0.5,
        ampacity={"I_amps": 60.0, "layer_type": "external", "cu_oz": 1},
        width_supply_mm=3.0)
    noesc = advise_hdi_escalation(
        "CH1_LOGIC",
        loop_geom={"length_mm": 0.5, "spacing_mm": 0.4, "width_mm": 0.3},
        loop_budget_nH=0.5)
    print(f"    {esc.region_id}: escalate={esc.escalate} :: {'; '.join(esc.reasons)}")
    print(f"    {noesc.region_id}: escalate={noesc.escalate} :: {'; '.join(noesc.reasons)}")
    ok &= esc.escalate and (not noesc.escalate)
    print(f"  {'ok ' if (esc.escalate and not noesc.escalate) else 'XX '}"
          f"over-budget loop/ampacity → HDI flag; within-budget → no flag")

    # ---- PART A4: learning loop (proxy-vs-strong divergence) ----------------
    print("\n[proxy] learning loop (proxy vs strong divergence; STRONG governs):")
    near = proxy_strong_divergence(0.1591, 0.1953)   # proxy vs strong loop-L
    far = proxy_strong_divergence(0.50, 0.1953)
    print(f"    near: rel_err {near['rel_error']:.2%} diverged={near['diverged']} → {near['action']}")
    print(f"    far : rel_err {far['rel_error']:.2%} diverged={far['diverged']} → {far['action']}")
    ok &= (not near["diverged"]) and far["diverged"] \
        and near["governs"] == far["governs"] == "strong"
    print(f"  {'ok ' if ((not near['diverged']) and far['diverged']) else 'XX '}"
          f"strong sim GOVERNS; large divergence flags a lesson")

    # ---- PART B: THE STRONG-SIM VERDICT GATE — accept + reject proof --------
    print("\n[gate] strong-sim binding-verdict gate (the no-fabricated-verdict proof):")
    # The provenance gate REJECTS /tmp as non-canonical (correct production
    # behaviour). So the self-test creates its synthetic artifacts under the REPO
    # WORKING TREE (a canonical-region path) in a uniquely-named scratch dir it
    # DELETES in `finally` — nothing is committed, and the ACCEPT path can be
    # demonstrated honestly without citing /tmp.
    repo_root = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
    tmp = tempfile.mkdtemp(prefix=".simloop_selftest_", dir=repo_root)
    try:
        # B1. VALID artifact set => ACCEPTED, returns a real binding verdict.
        valid_dir = os.path.join(tmp, "valid_sim")
        arts = _make_valid_strong_sim_artifacts(valid_dir)
        spec_ok = SimSpec(sim_dir=valid_dir, tier=2,
                          claimed_verdict="PASS", solver="ngspice")
        r_ok = binding_verdict(spec_ok)
        accept_ok = r_ok.accepted and r_ok.verdict == "PASS"
        ok &= accept_ok
        print(f"  {'ok ' if accept_ok else 'XX '}ACCEPT: valid 4-point+provenance "
              f"=> accepted={r_ok.accepted}, verdict={r_ok.verdict}")
        print(f"        reason: {r_ok.reasons[-1]}")

        # B2. REJECT — proxy result masquerading as a verdict.
        r_proxy = binding_verdict(SimSpec(sim_dir=valid_dir, tier=2,
                                          claimed_verdict="PASS", is_proxy=True))
        rej_proxy = (not r_proxy.accepted) and r_proxy.verdict == NOT_VERIFIED
        ok &= rej_proxy
        print(f"  {'ok ' if rej_proxy else 'XX '}REJECT proxy-as-verdict: "
              f"accepted={r_proxy.accepted}, verdict={r_proxy.verdict}")
        print(f"        reason: {r_proxy.reasons[0]}")

        # B3. REJECT — missing result file (sim not executed).
        miss_dir = os.path.join(tmp, "missing_result")
        os.makedirs(miss_dir)
        with open(os.path.join(miss_dir, "loop_l.cir"), "w") as f:
            f.write("* deck with NO result\n.end\n")
        r_miss = binding_verdict(SimSpec(sim_dir=miss_dir, tier=2,
                                         claimed_verdict="PASS"))
        rej_miss = (not r_miss.accepted) and r_miss.verdict == NOT_VERIFIED
        ok &= rej_miss
        print(f"  {'ok ' if rej_miss else 'XX '}REJECT missing-result: "
              f"accepted={r_miss.accepted}, verdict={r_miss.verdict}")
        print(f"        reason: {r_miss.reasons[0]}")

        # B4. REJECT — stale result (mtime < input: not re-run after edit).
        stale_dir = os.path.join(tmp, "stale_result")
        st = _make_valid_strong_sim_artifacts(stale_dir)
        import time
        # Touch the INPUT to be NEWER than the result (the staleness signature).
        now = time.time()
        os.utime(st["input"], (now, now))
        os.utime(st["result"], (now - 500, now - 500))
        r_stale = binding_verdict(SimSpec(sim_dir=stale_dir, tier=2,
                                          claimed_verdict="PASS"))
        rej_stale = (not r_stale.accepted) and r_stale.verdict == NOT_VERIFIED
        ok &= rej_stale
        print(f"  {'ok ' if rej_stale else 'XX '}REJECT stale-mtime: "
              f"accepted={r_stale.accepted}, verdict={r_stale.verdict}")
        print(f"        reason: {r_stale.reasons[0]}")

        # B5. REJECT — no literal exec command (not reproducible). The extract
        # SCRIPT + an extract OUTPUT still exist (points 1-3 pass), but NO file
        # carries the literal solver/python3 command, so point 4 (reproducibility)
        # fails — this isolates the "number with no reproducible command" mode.
        nocmd_dir = os.path.join(tmp, "no_exec_cmd")
        nc = _make_valid_strong_sim_artifacts(nocmd_dir)
        # Replace the extract OUTPUT (RESULTS.md) with a bare number — no command,
        # no 'ngspice'/'python3 '/'ElmerSolver'/'openems' token anywhere.
        with open(nc["results"], "w") as f:
            f.write("# loop-L result table (extract output)\n\nL = 0.1953 nH\n")
        # Rename the extract output to a non-RESULTS name the exec-scan ignores so
        # the ONLY remaining failure is the missing exec command (not points 1-3).
        os.rename(nc["results"], os.path.join(nocmd_dir, "loop_l_table.txt"))
        r_nocmd = binding_verdict(SimSpec(sim_dir=nocmd_dir, tier=2,
                                          claimed_verdict="PASS"))
        rej_nocmd = (not r_nocmd.accepted) and r_nocmd.verdict == NOT_VERIFIED
        ok &= rej_nocmd
        print(f"  {'ok ' if rej_nocmd else 'XX '}REJECT no-exec-command: "
              f"accepted={r_nocmd.accepted}, verdict={r_nocmd.verdict}")
        print(f"        reason: {r_nocmd.reasons[0]}")

        # B6. REJECT — non-canonical (/tmp) artifact citation (provenance fail).
        # Build an otherwise-valid set but cite a /tmp/*.kicad_pcb in RESULTS.md.
        prov_dir = os.path.join(tmp, "bad_provenance")
        pv = _make_valid_strong_sim_artifacts(prov_dir)
        with open(pv["results"], "a") as f:
            f.write("\nGeometry: /tmp/ch1_volatile.kicad_pcb  (NON-CANONICAL!)\n")
        r_prov = binding_verdict(SimSpec(sim_dir=prov_dir, tier=2,
                                         claimed_verdict="PASS"))
        rej_prov = (not r_prov.accepted) and r_prov.verdict == NOT_VERIFIED \
            and any("provenance" in s for s in r_prov.reasons)
        ok &= rej_prov
        print(f"  {'ok ' if rej_prov else 'XX '}REJECT non-canonical (/tmp) artifact: "
              f"accepted={r_prov.accepted}, verdict={r_prov.verdict}")
        print(f"        reason: {[s for s in r_prov.reasons if 'provenance' in s][0]}")

        # B7. strict=True RAISES on a refusal (cannot silently ignore).
        raised = False
        try:
            binding_verdict(SimSpec(sim_dir=valid_dir, tier=2,
                                    claimed_verdict="PASS", is_proxy=True),
                            strict=True)
        except SimVerdictError:
            raised = True
        ok &= raised
        print(f"  {'ok ' if raised else 'XX '}strict=True RAISES SimVerdictError on refusal")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 72)
    print("sim_loop self-test: " + ("ALL PASS" if ok else "FAILURES PRESENT"))
    print("  (NO heavy solver run — synthetic artifacts only; Pi co-tenant safe)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(self_test())
