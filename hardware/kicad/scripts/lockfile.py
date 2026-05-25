#!/usr/bin/env python3
"""lockfile.py — Phase 4-v3 SSoT readers for the two lockfiles.

Single place that parses docs/PHASE4V3_LOCKFILES/{mechanical_anchors,routing_topology}.yaml
so park/place/contract scripts never hardcode coords or roles (R32 sureshot,
PHASE4V3_PLAN §6 SSoT discipline). All consumers import from here.

mechanical_anchors.yaml gives, per anchored ref: pos/layer/rotation/footprint +
category. Categories:
  FOUNDATION (mount_holes, fiducials, connectors) — never parked; placed once at
    lockfile position by the Stage-1 anchor bring.
  ANCHORED-OWNED (motor_pads, test_points, leds) — parked like any component, then
    brought by their owning subsystem PR TO their lockfile coordinate (role=anchor).
Distinction per master 2026-05-25 LED routing (LEDs/motor pads/TPs travel with
their subsystem stage, not a monolithic Tier-1 placement).

routing_topology.yaml gives, per component: tier/role/parent/relation/max_distance/
same_layer — the inputs bringSelected() uses to position non-anchor components.
"""
from pathlib import Path

import yaml

ANCHORS_YAML = Path("docs/PHASE4V3_LOCKFILES/mechanical_anchors.yaml")
TOPOLOGY_YAML = Path("docs/PHASE4V3_LOCKFILES/routing_topology.yaml")

FOUNDATION_CATEGORIES = ("mount_holes", "fiducials", "connectors")
ANCHORED_OWNED_CATEGORIES = ("motor_pads", "test_points", "leds")
ALL_ANCHOR_CATEGORIES = FOUNDATION_CATEGORIES + ANCHORED_OWNED_CATEGORIES


def _is_placeholder(entry):
    if entry.get("ref") in (None, "TBD"):
        return True
    pos = entry.get("pos")
    if pos is None:
        return True
    return any(p == "TBD" or isinstance(p, str) for p in pos)


def load_anchors(path=ANCHORS_YAML):
    """Return {ref: {pos,layer,rotation,footprint,category,...}} for all concrete
    (non-placeholder) anchor entries across every category."""
    data = yaml.safe_load(Path(path).read_text())
    out = {}
    for cat in ALL_ANCHOR_CATEGORIES:
        for e in data.get(cat, []) or []:
            if _is_placeholder(e):
                continue
            rec = dict(e)
            rec["category"] = cat
            out[e["ref"]] = rec
    return out


def foundation_refs(path=ANCHORS_YAML):
    """Refs that are never parked (placed once at lockfile position)."""
    data = yaml.safe_load(Path(path).read_text())
    refs = set()
    for cat in FOUNDATION_CATEGORIES:
        for e in data.get(cat, []) or []:
            if not _is_placeholder(e):
                refs.add(e["ref"])
    return refs


def parking_grid(path=ANCHORS_YAML):
    data = yaml.safe_load(Path(path).read_text())
    g = data["parking_grid"]
    return {
        "origin": tuple(g["origin"]),
        "spacing": float(g["spacing_mm"]),
        "cols": int(g["cols"]),
        "layer": g.get("layer", "F.Cu"),
        "rotation": g.get("rotation", 0),
    }


def load_component_roles(path=TOPOLOGY_YAML):
    """Return {ref: {tier,role,subsystem,parent,relation,max_distance_mm,
    same_layer_as_parent,...}} for concrete component entries. Empty until the
    components: section is filled (CH1 + central)."""
    data = yaml.safe_load(Path(path).read_text())
    comps = data.get("components") or {}
    return {ref: rec for ref, rec in comps.items() if isinstance(rec, dict)}
