"""Phase 0 scikit-rf smoke test — load a touchstone-format network.

Builds an inline 1-port Touchstone of a known 50Ω load (S11 = 0 at all freqs),
parses it via skrf.Network, asserts reflection coefficient ≈ 0.
"""
import skrf as rf
import numpy as np
import tempfile
import os

print(f'scikit-rf version: {rf.__version__}')

# Build minimal Touchstone .s1p — 50Ω matched load → S11 = 0 across band
touchstone = """!Phase 0 smoke — matched 50Ω load
# GHz S MA R 50
1.0  0.0  0.0
2.0  0.0  0.0
5.0  0.0  0.0
10.0 0.0  0.0
"""
with tempfile.NamedTemporaryFile(mode='w', suffix='.s1p', delete=False) as f:
    f.write(touchstone)
    fname = f.name

try:
    net = rf.Network(fname)
    print(f'Loaded {fname}')
    print(f'  Network name: {net.name}')
    print(f'  Frequency range: {net.f[0]/1e9} - {net.f[-1]/1e9} GHz')
    print(f'  S11 mag (linear): {np.abs(net.s).flatten()}')
    assert np.allclose(np.abs(net.s).flatten(), 0.0), 'Expected |S11| = 0 for matched load'
    print('scikit-rf smoke PASS')
finally:
    os.unlink(fname)
