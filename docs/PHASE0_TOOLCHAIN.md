# Phase 0 — Toolchain verification

Per `DESIGN_PHASES.md` Phase 0 acceptance ("every tool runs a smoke test clean.
Record versions + install paths.") and the Rule-10 grep-then-state discipline
(`ENGINEERING_RIGOR.md` §10) — every version + path below was captured directly
from the tool, not from memory.

Project context: pcb.ai FPV 4-in-1 ESC (PL1) is the first design through this
pipeline. Tools listed under the playbook (`PCB_PLAYBOOK.md` §Toolchain) plus
the ARM-GNU toolchain for AM32 firmware (`REQUIREMENTS.md` §fpv-4in1 →
firmware = AM32).

Environment: novarobotics64 (Raspberry Pi 5, aarch64, Linux 6.18.29+rpt-rpi-2712).

## Smoke-test result table

| # | Tool | Version | Install path | Smoke-test verdict | Notes |
|---|---|---|---|---|---|
| 1 | KiCad 9 (kicad-cli) | 9.0.2 (dpkg `9.0.2+dfsg-1`) | `/usr/bin/kicad-cli`, `/usr/bin/kicad` | PASS — opened `pic_programmer.kicad_sch` demo, ran ERC (115 violations expected on demo), exported 1179-line netlist | No CLI "re-save" subcommand; ERC + netlist export are the round-trip equivalent (file fully parsed + traversed) |
| 2 | SKiDL | 2.2.3 | `/home/novatics64/.local/lib/python3.13/site-packages/skidl/` | PASS — 5-component netlist (R, C, LED, NPN BJT, 1×02 header) generated, 0 errors | Needs `KICAD_SYMBOL_DIR` / `KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols` env. Initial run failed on `Q_NPN_BCE` (not a KiCad 9 symbol); correct symbol is `Q_NPN`. 14 non-fatal "missing tstamps tag" warnings. |
| 3 | kinet2pcb | 1.1.4 | `/home/novatics64/.local/bin/kinet2pcb`, `/home/novatics64/.local/lib/python3.13/site-packages/kinet2pcb/` | PASS — converted SKiDL netlist → 22 KB `.kicad_pcb` with 5 footprints; kicad-cli renders it to SVG cleanly | Cosmetic startup line: `pcbnew/action_plugin.cpp(163): assert "PgmOrNull()"` — wxWidgets headless warning, non-blocking |
| 4 | Freerouting | post-v2.2.4 build (manifest: Built 2026-05-13 with Adoptium JDK 25.0.2+10-LTS, jar revision `20f1a72e546b9b23c7ba5127086885cfacbdd4be`) | `/home/novatics64/local/freerouting/freerouting.jar` (57.7 MB) | **DEFERRED — see OQ-005** | Jar requires Java 25 (class file v69); only Java 21 installed (`/usr/bin/java`, `/usr/lib/jvm/java-21-openjdk-arm64`). novapcb worker currently uses this install; coordinated change required. Resolution gated to Phase 5 (routing) prep. |
| 5 | Elmer FEM (ElmerSolver) | 26.2-devel (Rev `03313b2`, compiled 2026-05-20) | `/home/novatics64/local/elmer/bin/ElmerSolver` (source build at `/home/novatics64/local/src/em-fem-builds/elmerfem`) | PASS — `HeatControl` steady-state thermal test converged in 0.21 CPU-s; built-in reference comparison: relative error 1.33e-16 (machine precision) | Not on `$PATH` — absolute path needed |
| 6 | OpenEMS | `655947c` (CSXCAD `32847a2`, libCSXCAD.so.0.6.3, libopenEMS.so.0.0.36) | `/home/novatics64/local/openems/bin/openEMS`, `/home/novatics64/local/openems/lib/`, Python: `/home/novatics64/.local/lib/python3.13/site-packages/openEMS/` | PASS — 100-timestep FDTD on 726-cell vacuum box completed in 0.75 ms; et + ht output files produced | Python bindings need `LD_LIBRARY_PATH=/home/novatics64/local/openems/lib`. Probe `Box([0,0,0],[0,0,0])` produced a "primitive dimension not suitable" warning (cosmetic — use a non-zero-dim probe for real work) |
| 7 | ngspice | 44.2 (KLU direct linear solver, dpkg `44.2+ds-1`) | `/usr/bin/ngspice`, `/usr/lib/aarch64-linux-gnu/libngspice.so.0` (`libngspice0:arm64` 44.2+ds-1) | PASS — `rc.cir` direct batch transient charged to 4.9998 V by t=1 ms (theory ≈ 5) | The `libngspice0-dev` deb (with the un-versioned `libngspice.so` symlink) is **not** apt-installed; a copy exists at `/home/novatics64/local/src/libngspice0-dev.deb` |
| 7b | PySpice | 1.5 | `/home/novatics64/.local/lib/python3.13/site-packages/PySpice/` | PASS — RC transient via `ngspice-shared` reached 3.1552 V at t=τ (theory 3.1606 V) | **Two compatibility caveats**: (a) `ngspice-subprocess` backend FAILS — header parser expects "Circuit" label, ngspice 44.2 emits "Note" first; use `ngspice-shared`. (b) PySpice 1.5 doesn't find `libngspice.so` automatically (no .so symlink without -dev pkg) — must set `NGSPICE_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu/libngspice.so.0`. (c) Warning "Unsupported Ngspice version 44" is cosmetic |
| 8 | scikit-rf | 1.12.0 | `/home/novatics64/.local/lib/python3.13/site-packages/skrf/` | PASS — MLine model on 3 mm × 1.6 mm FR-4 microstrip gives Z₀ = 49.51 Ω; my analytical Hammerstad-Jensen (Pozar 4e eq. 3.196-7) gives 50.82 Ω; agreement within 1.31 Ω, both within 1 Ω of the 50 Ω target | DeprecationWarning: `Z0` → `z0` (lowercase) for v1.0+ — cosmetic |
| 9 | InteractiveHtmlBom | 2.11.1 | `/home/novatics64/venv-ardupilot/lib/python3.13/site-packages/InteractiveHtmlBom/` | PASS — generated 280 KB `ibom.html` from `pic_programmer.kicad_pcb` demo | Requires Edge.Cuts board outline; my SKiDL/kinet2pcb sample lacks one (kinet2pcb does not synthesize an outline). For pcb.ai sources we'll add Edge.Cuts in KiCad before BOM generation |
| 10 | kicad-cli `pcb export gerbers / drill` | 9.0.2 (same binary as #1) | `/usr/bin/kicad-cli` | PASS — exported full gerber layer set (`*-F_Cu.gtl`, `*-B_Cu.gbl`, masks, paste, silkscreen, courtyard, fab, edge cuts) + `pp.drl` to `/tmp/kicad_export/` | None |
| 11 | arm-none-eabi-gcc (system, /opt) | 10.2.1 (`GNU Arm Embedded Toolchain 10-2020-q4-major`, 20201103) | `/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi-gcc` (ELF aarch64-native) | PASS — `--version` clean; AM32 G071 build succeeded against it (row #12) | Pre-existing system install — no new install performed. **AM32's bundled xpack-arm-none-eabi-gcc-10.3.1-2.3 is x86_64 only** and cannot run on this aarch64 host (Exec format error from the bundled `arm-none-eabi-gcc`). Build invoked with `make ARM_SDK_PREFIX=/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi- g071` to use the system toolchain. Debian apt also has `gcc-arm-none-eabi 14.2.rel1-1` available if a newer LTS is needed later; not installed. |
| 12 | AM32 baseline build | repo HEAD (am32-firmware/AM32, default branch) | `/home/novatics64/escworker/AM32` | PASS — `make g071` built 51 G071 targets, zero errors; reference target `AM32_AM32_ESC_G071_2.20.elf` is 32-bit ARM EABI5, text=24180 B / data=1056 B / bss=2704 B, FLASH 38.4% of 63264 B used | Target family: **G071** (matches `REQUIREMENTS.md` §fpv-4in1 MCU candidate `STM32G071` OR `AT32F421`). Per-target outputs: `.elf` + `.bin` + `.hex` in `obj/`. Total build wall-time ≈ 5 min single-threaded on Pi 5. AM32's bundled toolchain (xpack 10.3.1) is x86_64 only — used system /opt aarch64 GCC 10.2.1 via `ARM_SDK_PREFIX` override; same major version, one point release behind. `-Werror -Wall -Wextra` clean across all 51 targets. |
| 13 | Python venv + sim deps | venv Python 3.13.5, pip 26.1.1 | `/home/novatics64/escworker/pcb.ai/.venv/` (gitignored per `.gitignore` line `.venv/`) | PASS — installed numpy 2.4.6, scipy 1.17.1, matplotlib 3.10.9, pyspice 1.5, scikit-rf 1.12.0; all imports clean | Created per Step 3 of master's Phase 0 contract |

## Deferred (NOT installed this phase)

Per master's Phase 0 contract Step 4 — these belong to PL2 (HV60 FOC family)
and are deferred until PL2 work opens. Raising to master before installing if a
real PL1 need surfaces (R4 + R15).

- STM32CubeIDE / CubeMX
- ST-LINK utility
- X-CUBE-MCSDK

## Open items from this phase

1. **Freerouting / Java 25 mismatch** (row #4) — DEFERRED to Phase 5 (routing) prep per OQ-005 (Sai's call, 2026-05-22). novapcb worker on this machine uses the same install; coordinated change only. Non-blocking for Phases 1-4 (no routing).
2. **PySpice subprocess backend broken** (row #7b) — workaround documented (use `ngspice-shared` + `NGSPICE_LIBRARY_PATH`). PySpice 1.5 was released before ngspice 44; long-term fix is upstream PySpice or pin ngspice ≤ 43. Not blocking — `ngspice-shared` works.
3. **`libngspice.so` symlink missing** (row #7b) — `libngspice0-dev` is not apt-installed though the .deb is staged at `/home/novatics64/local/src/libngspice0-dev.deb`. Workaround via env var. If desired later, `sudo dpkg -i` the staged deb (system-state change — requires authorization).

## Repro commands (for the audit / re-verification)

```bash
# Tool versions
kicad-cli --version
python3 -c "import skidl; print(skidl.__version__)"
kinet2pcb --version
java -jar /home/novatics64/local/freerouting/freerouting.jar --version   # FAILS — deferred per OQ-005, reverify at Phase 5 prep
/home/novatics64/local/elmer/bin/ElmerSolver --version
/home/novatics64/local/openems/bin/openEMS --version
ngspice --version
python3 -c "import PySpice; print(PySpice.__version__)"
python3 -c "import skrf; print(skrf.__version__)"
/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi-gcc --version

# Per-tool smoke tests live under /home/novatics64/escworker/scratch/
# (skidl_smoke.py, openems_smoke.py, pyspice_smoke.py, skrf_smoke.py, rc.cir, elmer_smoke/)

# AM32 build
make -C /home/novatics64/escworker/AM32 \
  ARM_SDK_PREFIX=/opt/gcc-arm-none-eabi-10-2020-q4-major/bin/arm-none-eabi- g071

# Venv
source /home/novatics64/escworker/pcb.ai/.venv/bin/activate
```

## Required env vars for sim / firmware sessions

These are workspace defaults, not committed shell config (memory hygiene per
`CLAUDE.md` Rule 11). Set per-session or per-script:

```bash
export KICAD_SYMBOL_DIR=/usr/share/kicad/symbols
export KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols
export LD_LIBRARY_PATH=/home/novatics64/local/openems/lib:${LD_LIBRARY_PATH}
export NGSPICE_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu/libngspice.so.0
```
