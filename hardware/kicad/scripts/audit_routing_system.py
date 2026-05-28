#!/usr/bin/env python3
"""
audit_routing_system.py — drift-prevention meta-audit for the routing system

Per Sai 2026-05-24: "make sure routing system doesnt drift".

Checks:
1. ROUTING_SYSTEM_HASH matches stored value (any change requires PR tag
   `[routing-system-update]`)
2. ROUTING_LESSONS_HASH matches stored value (any change requires PR tag
   `[lesson-update]`)
3. ROUTING_METHODOLOGY_HASH matches stored value (any change requires PR tag
   `[methodology-change]`)
4. ROUTING_TOPOLOGY_HASH matches stored value (any change requires PR tag
   `[methodology-change]`)
5. physics_primitives.py self-test still PASS
6. constraint_engine.py smoke test still PASS
7. All required scripts present + importable

Run on every routing PR. Master gate REJECTS if any drift not pre-declared.
"""

import hashlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS = REPO_ROOT / "hardware/kicad/scripts"
DOCS = REPO_ROOT / "docs"


# ─── Hash computation ─────────────────────────────────────────────────────

def compute_doc_content_hash(path):
    """SHA256 of normalized doc content (excludes the hash storage line itself
    to allow self-referencing)."""
    text = Path(path).read_text()
    # Remove the stored-hash line so the hash is reproducible
    text = re.sub(r"^.*HASH\s*=\s*\([^)]*\)\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^.*HASH\s*=\s*[0-9a-f]+\s*$", "", text, flags=re.MULTILINE)
    return hashlib.sha256(text.encode()).hexdigest()


def extract_stored_hash(path, var_name):
    """Read stored `VAR_NAME = <hex>` line from doc."""
    text = Path(path).read_text()
    m = re.search(rf"{var_name}\s*=\s*([0-9a-f]+)", text)
    if m:
        return m.group(1)
    m = re.search(rf"{var_name}\s*=\s*\(([^)]+)\)", text)
    if m:
        return None  # placeholder, not yet computed
    return None


# ─── Checks ────────────────────────────────────────────────────────────────

def check_routing_system_doc_hash():
    path = DOCS / "ROUTING_SYSTEM.md"
    if not path.exists():
        return "FAIL", f"{path} missing"
    computed = compute_doc_content_hash(path)
    stored = extract_stored_hash(path, "ROUTING_SYSTEM_HASH")
    if stored is None:
        return "WARN", f"computed={computed[:16]}, no stored hash to compare (run --write to lock)"
    if stored != computed:
        return "FAIL", f"computed={computed[:16]}, stored={stored[:16]} — drift; PR must tag [routing-system-update]"
    return "PASS", f"hash={computed[:16]}"


def check_routing_lessons_doc_hash():
    path = DOCS / "ROUTING_LESSONS.md"
    if not path.exists():
        return "FAIL", f"{path} missing"
    computed = compute_doc_content_hash(path)
    stored = extract_stored_hash(path, "ROUTING_LESSONS_HASH")
    if stored is None:
        return "WARN", f"computed={computed[:16]}, no stored hash (run --write to lock)"
    if stored != computed:
        return "FAIL", f"computed={computed[:16]}, stored={stored[:16]} — drift; PR must tag [lesson-update]"
    return "PASS", f"hash={computed[:16]}"


def check_routing_methodology_doc_hash():
    path = DOCS / "ROUTING_METHODOLOGY.md"
    if not path.exists():
        return "FAIL", f"{path} missing"
    computed = compute_doc_content_hash(path)
    stored = extract_stored_hash(path, "ROUTING_METHODOLOGY_HASH")
    if stored is None:
        return "WARN", f"computed={computed[:16]}, no stored hash (run --write to lock)"
    if stored != computed:
        return "FAIL", f"computed={computed[:16]}, stored={stored[:16]} — drift; PR must tag [methodology-change]"
    return "PASS", f"hash={computed[:16]}"


def check_routing_topology_hash():
    path = DOCS / "PHASE4V3_LOCKFILES/routing_topology.yaml"
    if not path.exists():
        return "FAIL", f"{path} missing"
    computed = compute_doc_content_hash(path)
    stored = extract_stored_hash(path, "ROUTING_TOPOLOGY_HASH")
    if stored is None:
        return "WARN", f"computed={computed[:16]}, no stored hash (run --write to lock)"
    if stored != computed:
        return "FAIL", f"computed={computed[:16]}, stored={stored[:16]} — drift; PR must tag [methodology-change]"
    return "PASS", f"hash={computed[:16]}"


def check_physics_primitives_self_test():
    """Run physics_primitives.py and check exit code."""
    path = SCRIPTS / "physics_primitives.py"
    if not path.exists():
        return "FAIL", f"{path} missing"
    result = subprocess.run(
        [sys.executable, str(path)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        last_lines = "\n".join(result.stderr.split("\n")[-5:])
        return "FAIL", f"self-test failed:\n{last_lines}"
    return "PASS", "physics_primitives self-test"


def check_constraint_engine_smoke():
    """Run constraint_engine.py and check exit code."""
    path = SCRIPTS / "constraint_engine.py"
    if not path.exists():
        return "FAIL", f"{path} missing"
    result = subprocess.run(
        [sys.executable, str(path)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        last_lines = "\n".join(result.stderr.split("\n")[-5:])
        return "FAIL", f"smoke test failed:\n{last_lines}"
    return "PASS", "constraint_engine smoke test"


def check_required_files_present():
    """All routing-system files must exist."""
    required = [
        DOCS / "ROUTING_SYSTEM.md",
        DOCS / "ROUTING_LESSONS.md",
        DOCS / "ROUTING_METHODOLOGY.md",
        DOCS / "PHASE4V3_LOCKFILES/routing_topology.yaml",
        SCRIPTS / "physics_primitives.py",
        SCRIPTS / "constraint_engine.py",
        SCRIPTS / "audit_routing_system.py",  # this file
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        return "FAIL", f"missing: {[str(p.relative_to(REPO_ROOT)) for p in missing]}"
    return "PASS", f"all {len(required)} required files present"


# ─── --write mode (lock hashes after PR-tagged update) ────────────────────

def write_hashes():
    """Compute current hashes and write into the doc files."""
    for path, var_name in [
            (DOCS / "ROUTING_SYSTEM.md", "ROUTING_SYSTEM_HASH"),
            (DOCS / "ROUTING_LESSONS.md", "ROUTING_LESSONS_HASH"),
            (DOCS / "ROUTING_METHODOLOGY.md", "ROUTING_METHODOLOGY_HASH"),
            (DOCS / "PHASE4V3_LOCKFILES/routing_topology.yaml", "ROUTING_TOPOLOGY_HASH"),
    ]:
        if not path.exists():
            continue
        text = path.read_text()
        computed = compute_doc_content_hash(path)
        # Replace placeholder or stored hash
        new_text, count = re.subn(
            rf"{var_name}\s*=\s*[^\n]+",
            f"{var_name} = {computed}",
            text)
        if count == 0:
            # No existing line — append
            new_text += f"\n{var_name} = {computed}\n"
        path.write_text(new_text)
        print(f"  → {path.name}: {var_name} = {computed[:16]}...")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--write":
        print("=== Computing + writing routing-system hashes ===")
        write_hashes()
        return

    print("=== Routing system drift audit ===\n")
    any_fail = False
    for name, fn in [
            ("REQUIRED_FILES", check_required_files_present),
            ("ROUTING_SYSTEM_HASH", check_routing_system_doc_hash),
            ("ROUTING_LESSONS_HASH", check_routing_lessons_doc_hash),
            ("ROUTING_METHODOLOGY_HASH", check_routing_methodology_doc_hash),
            ("ROUTING_TOPOLOGY_HASH", check_routing_topology_hash),
            ("PHYSICS_PRIMITIVES", check_physics_primitives_self_test),
            ("CONSTRAINT_ENGINE", check_constraint_engine_smoke),
    ]:
        status, msg = fn()
        print(f"[{status}] {name}: {msg}")
        if status == "FAIL":
            any_fail = True
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
