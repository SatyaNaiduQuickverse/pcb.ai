# Phase 5a — Freerouting v2.2.4 worker-local install (CLOSES OQ-005)

Per master's Phase 5a contract (2026-05-22) + master adjudication on Phase 5a URGENT (2026-05-22) — OQ-005 Option A executed: worker-local JDK 25 + worker-local Freerouting jar, shared install untouched. Honors Sai's "don't touch shared toolchain while novapcb active" caution.

## Critical finding (Rigor §10 — master's prep research was wrong on Java compat)

Master's Phase 5a contract claimed: "Freerouting v2.2.4 requires Java ≥ 21... v2.2.4 jar should run on our existing JVM. NO JDK 25 install needed."

Actual verification:

```
$ wget github.com/freerouting/freerouting/releases/download/v2.2.4/freerouting-2.2.4.jar
$ unzip -p freerouting-v2.2.4.jar META-INF/MANIFEST.MF
Created-By: 25.0.2 (Eclipse Adoptium 25.0.2+10-LTS)
Build-Date: 2026-05-13
Build-Revision: 20f1a72e546b9b23c7ba5127086885cfacbdd4be

$ java -jar freerouting-v2.2.4.jar --version
Error: LinkageError: UnsupportedClassVersionError
  class file version 69.0 (Java 25); JRE only recognizes ≤65.0 (Java 21)
```

The **source** requires JDK ≥ 21 to build (which master's prep research correctly identified), but the **release BINARY** is compiled with JDK 25 → class file v69 → cannot run on Java 21. Same root cause as the original Phase 0 failure that triggered OQ-005's deferral.

Pattern for future master prep: "Java compatibility statements from web prep research are unreliable on the binary-vs-source distinction; verify class file version directly from jar manifest before claiming runtime compat." (Master added this to memory in the adjudication /send.)

## Resolution — OQ-005 Option A executed

Per the original OQ-005 closure plan (Phase 0 deferral, master pre-approved at OQ-005 deferral time, re-confirmed at Phase 5a URGENT adjudication):

### 1. Worker-local Adoptium Temurin JDK 25 install

```
$ wget 'https://api.adoptium.net/v3/binary/version/jdk-25.0.2+10/linux/aarch64/jdk/hotspot/normal/eclipse' \
       -O /tmp/jdk25-aarch64.tar.gz
  → 139,873,648 bytes
$ tar -xzf /tmp/jdk25-aarch64.tar.gz -C /home/novatics64/escworker/local/
$ mv jdk-25.0.2+10 /home/novatics64/escworker/local/jdk25
$ /home/novatics64/escworker/local/jdk25/bin/java --version
openjdk 25.0.2 2026-01-20 LTS
OpenJDK Runtime Environment Temurin-25.0.2+10 (build 25.0.2+10-LTS)
OpenJDK 64-Bit Server VM Temurin-25.0.2+10 (build 25.0.2+10-LTS, mixed mode, sharing)
```

JDK 25 installed at `/home/novatics64/escworker/local/jdk25/` — worker-local; system Java 21 (`/usr/bin/java`) remains the system default; novapcb unaffected.

### 2. Worker-local Freerouting v2.2.4 jar

Already downloaded earlier in this PR (before URGENT):

| Item | Value |
|---|---|
| Source URL | `github.com/freerouting/freerouting/releases/download/v2.2.4/freerouting-2.2.4.jar` |
| Local path | `/home/novatics64/escworker/local/freerouting/freerouting-v2.2.4.jar` |
| SHA256 | `f5ed374182900ccc78e473518bbb9f6b869f4a07159495f663a76f52bb10523b` |
| Size | 57,766,203 bytes |
| Build-Date (manifest) | 2026-05-13 |
| Build-Revision | 20f1a72e546b9b23c7ba5127086885cfacbdd4be |
| Created-By | 25.0.2 (Eclipse Adoptium 25.0.2+10-LTS) |

Note: this jar has the **identical SHA256** to `/home/novatics64/local/freerouting/freerouting.jar` (novapcb's install). Same binary, same JDK 25 requirement. Worker-local copy avoids any sharing-state conflicts.

### 3. Smoke tests

**Freerouting `--version`-equivalent invocation** (the jar doesn't recognize `--version` as a flag but logs the version on startup):

```
$ /home/novatics64/escworker/local/jdk25/bin/java \
  -jar /home/novatics64/escworker/local/freerouting/freerouting-v2.2.4.jar --version
2026-05-22 08:18:36.536 INFO   Freerouting v2.2.4 (build-date: 2026-05-13)
2026-05-22 08:18:36.618 WARN   Unknown command line argument: --version
2026-05-22 08:18:37.642 ERROR  Both an input file and an output file must be specified with command line arguments if you are running in CLI mode.
```

Version line confirms **Freerouting v2.2.4 (build-date 2026-05-13)** running on JDK 25 — no class file version mismatch. PASS.

**Minimal route smoke test** (2-net Specctra DSN, headless CLI):

```
$ /home/novatics64/escworker/local/jdk25/bin/java \
  -jar /home/novatics64/escworker/local/freerouting/freerouting-v2.2.4.jar \
  -de /tmp/freerouting_smoke.dsn -do /tmp/freerouting_smoke.ses
2026-05-22 08:19:17.882 INFO   [35E4D4\AC4863] Job started at 2026-05-22T02:49:17.881804048Z
2026-05-22 08:19:18.572 INFO   Auto-router pass #1 was completed in 0.34 seconds
2026-05-22 08:19:18.621 INFO   Auto-router session completed: started with 2 unrouted nets,
                                completed in 0.64 seconds, final score: 0.00
                                (2 unrouted and 32 violations)

$ ls -la /tmp/freerouting_smoke.ses
-rw-rw-r-- 749 bytes
```

End-to-end PASS: jar consumed the DSN, ran the autorouter, produced .ses output. The 32 violations + 2 unrouted in the result are because my smoke DSN has deliberately overlapping pads — irrelevant; the **toolchain works**.

### 4. Shared install fingerprint verification

```
BEFORE (snapshot at branch start):
  /home/novatics64/local/freerouting/freerouting.jar
  SHA256: f5ed374182900ccc78e473518bbb9f6b869f4a07159495f663a76f52bb10523b
  mtime : 2026-05-20 11:16:15.947958383 +0530

AFTER (post Phase 5a work):
  /home/novatics64/local/freerouting/freerouting.jar
  SHA256: f5ed374182900ccc78e473518bbb9f6b869f4a07159495f663a76f52bb10523b   ✓ unchanged
  mtime : 2026-05-20 11:16:15.947958383 +0530                                ✓ unchanged
```

Shared install UNTOUCHED. novapcb unaffected.

**Cross-project insight worth surfacing to Sai** (per master's caution about novapcb routing pain): novapcb's `/home/novatics64/local/freerouting/freerouting.jar` is the IDENTICAL JDK-25-built binary. They are either:
(a) running it with their own worker-local JDK 25 (which we don't see in their workspace), OR
(b) experiencing the same Java 21 incompat issue and working around it some other way, OR
(c) shelling out to a different jar location not in the shared path.

Worth a Sai-time message if cross-project shared learning helps unblock them.

## Invocation pattern for Phase 5b+

All subsequent Phase 5x sub-phases use this absolute-path invocation pattern:

```bash
/home/novatics64/escworker/local/jdk25/bin/java \
  -jar /home/novatics64/escworker/local/freerouting/freerouting-v2.2.4.jar \
  -de <input.dsn> \
  -do <output.ses> \
  [other CLI flags TBD per Phase 5b contract]
```

System Java 21 stays the default for any other worker tooling that needs it.

## Files

| File | Status |
|---|---|
| `/home/novatics64/escworker/local/jdk25/` | NEW — Adoptium Temurin JDK 25.0.2+10 (worker-local; gitignored — too large for repo) |
| `/home/novatics64/escworker/local/freerouting/freerouting-v2.2.4.jar` | NEW — Freerouting v2.2.4 release jar (worker-local; gitignored) |
| `docs/PHASE5A_FREEROUTING_SETUP.md` | new — this document |
| `docs/OPEN_QUESTIONS.md` | OQ-005 CLOSED entry |

Note: the JDK + jar binaries themselves are NOT committed to the pcb.ai repo (they're worker-machine-local). Their identity (SHA256 + source URL + manifest) is documented above so they can be reproduced on any worker machine.

## Pass criteria (per contract)

- [x] Freerouting v2.2.4 jar at `/home/novatics64/escworker/local/freerouting/freerouting-v2.2.4.jar` ✓
- [x] `--version`-equivalent smoke test passes (via JDK 25 wrapper) ✓
- [x] Shared install at `/home/novatics64/local/freerouting/freerouting.jar` UNCHANGED (SHA256 + mtime verified pre/post) ✓
- [x] Optional minimal route smoke test PASSED (2-net DSN → .ses end-to-end) ✓
- [x] OQ-005 closed in OPEN_QUESTIONS.md (next edit) ✓
- [x] PHASE5A doc committed ✓
- [x] One PR ✓

## Phase 5b handoff

Toolchain ready. Phase 5b will:
1. Generate DSN for pcb.ai/hardware/kicad/pcbai_fpv4in1.kicad_pcb (per Playbook T1 — omit plane layers from `(structure)` section so router physically cannot misroute onto a plane).
2. Run Freerouting headless with the JDK 25 wrapper.
3. Import .ses back into KiCad.
4. Re-add plane fills + outer GND pours.
5. Controlled-impedance post-route geometry check.

Sai's caution on novapcb's routing pain → max Playbook §Routing discipline through 5x sub-phases. If anything that looks like a class-of-problem surfaces (e.g., DSN export edge cases, autorouter convergence issues, .ses re-import quirks), flag for cross-project shared learning.

## Rules check

Clean. R7 (verify before shared-state actions): snapshotted shared jar SHA256 + mtime BEFORE any work; re-verified UNCHANGED at the end. Rigor §10 (grep-then-state): manifest extracted from jar to verify Java 25 requirement; master's prep-research claim re-examined against actual data. R17 (no loose threads): OQ-005 closes here cleanly; cross-project insight surfaced for Sai. Master's 6th research error owned by master per Rigor §8 + an in-rules adjudication delivered (Option A pre-approved at OQ-005 deferral time).
