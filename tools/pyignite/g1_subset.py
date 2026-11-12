"""Extract one explicitly scoped, checksum-verified G1 root FCBlock and PE.

Only an offline validation adapter. Does not alter the exporter or robot runtime.
The optional safetensors dependency is not imported by the PyIgnite package.
"""
import hashlib
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'backbone_net._proj_start_input.'
PE_KEY = 'backbone_net._position_emb.embed'
LAYER_NAMES = ('fc_layers.0', 'fc_layers.1', 'forward_projection')
SHAPES = ((512, 384), (512, 512), (512, 512))


def load_g1_root_subset(path):
    from safetensors.numpy import load

    spec = importlib.util.spec_from_file_location('checkpoint_checksums', ROOT / 'tools/onnx/checksums.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Use the repository's existing release identity, not a user-supplied hash.
    releases = module.CHECKPOINTS
    entry = next(e for e in releases['g1']['files'] if e['path'].startswith('motionbricks_root/'))
    path = Path(path)
    if path.stat().st_size != entry['bytes']:
        raise ValueError('G1 root checkpoint size mismatch')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry['sha256']:
        raise ValueError('G1 root checkpoint SHA-256 mismatch')
    state = load(data)  # Parse the exact bytes that were hashed; never pickle.
    expected_keys = {PREFIX + name + suffix for name in LAYER_NAMES for suffix in ('.weight', '.bias')}
    if {key for key in state if key.startswith(PREFIX)} != expected_keys:
        raise ValueError('unexpected G1 FCBlock keys')
    layers = []
    for name, shape in zip(LAYER_NAMES, SHAPES):
        w, b = state[PREFIX + name + '.weight'], state[PREFIX + name + '.bias']
        if w.shape != shape or b.shape != (shape[0],):
            raise ValueError('unexpected G1 FCBlock shape')
        if w.dtype != np.float32 or b.dtype != np.float32 or not np.isfinite(w).all() or not np.isfinite(b).all():
            raise ValueError('invalid G1 FCBlock dtype/values')
        layers.append((w.copy(), b.copy()))
    pe = state[PE_KEY]
    if pe.shape != (16, 1, 512) or pe.dtype != np.float32 or not np.isfinite(pe).all():
        raise ValueError('invalid G1 position buffer')
    return layers, pe.copy(), {'checkpoint_sha256': digest, 'checkpoint_bytes': len(data),
                              'fc_prefix': PREFIX, 'pe_key': PE_KEY,
                              'scope': 'real released weights; synthetic subgraph inputs; not full G1 inference'}
