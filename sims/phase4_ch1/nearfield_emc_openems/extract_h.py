#!/usr/bin/env python3
"""extract_h.py — PR-CH1 amendment: extract |H| @ 100MHz from openEMS FDTD
frequency-domain dump.

openEMS dump_type=13 computes DFT of H-field during sim and saves complex
amplitude at requested frequencies. No post-process FFT needed.

Acceptance: |H| ≤ 100 A/m at 100MHz (FCC Class B near-field precursor).
"""
import os, sys
import numpy as np
import h5py

WORK = os.path.join(os.path.dirname(__file__), "openems_work")
H5_FILE = os.path.join(WORK, "Hf_probe.h5")
if not os.path.exists(H5_FILE):
    sys.exit(f"Missing {H5_FILE} — run run_openems.py first")

with h5py.File(H5_FILE, 'r') as f:
    fd = f['FieldData']['FD']
    freq = fd.attrs['frequency'][0]
    h_complex = fd['f0'][:]   # shape (3, nx, ny, nz) complex64

print(f"openEMS FDTD frequency-domain H-field probe")
print(f"  Probe frequency: {freq/1e6:.1f} MHz")
print(f"  H-field array shape: {h_complex.shape}")  # (3 components, x, y, z)

# Compute |H| magnitude per cell
h_mag = np.sqrt(np.abs(h_complex[0])**2 + np.abs(h_complex[1])**2 + np.abs(h_complex[2])**2)
print(f"  |H| min: {h_mag.min():.4e} A/m")
print(f"  |H| max: {h_mag.max():.4e} A/m")
print(f"  |H| mean: {h_mag.mean():.4e} A/m")

# Acceptance uses MAX over probe box (worst case at 1mm above trace center)
H_peak = float(h_mag.max())
ACC = 100.0
print(f"  Peak |H| at 100MHz: {H_peak:.4e} A/m")
print(f"  Acceptance: ≤{ACC} A/m")
verdict = H_peak <= ACC
print(f"  Verdict: {'PASS' if verdict else 'FAIL'}")

# Save extract summary
with open(os.path.join(os.path.dirname(__file__), "openems_extract.txt"), "w") as fh:
    fh.write(f"openEMS FDTD H-field probe @ 1mm above trace, 100MHz component\n")
    fh.write(f"  Sim: 50000 timesteps, dt=5e-10s = 25us total\n")
    fh.write(f"  Dump: dump_type=13 (frequency-domain DFT) at 100MHz\n")
    fh.write(f"  H-field tensor shape: {h_complex.shape}\n")
    fh.write(f"  Peak |H| at 100MHz: {H_peak:.4e} A/m\n")
    fh.write(f"  Acceptance: ≤{ACC} A/m\n")
    fh.write(f"  Verdict: {'PASS' if verdict else 'FAIL'}\n")

sys.exit(0 if verdict else 1)
