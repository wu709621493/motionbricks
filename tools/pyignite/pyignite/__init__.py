"""Experimental FP32 inference primitives. No torch, autograd or training support."""
import ctypes as C
from pathlib import Path
import platform
import numpy as np

__version__ = '0.1.0'
_lib = None

def _native():
    global _lib
    if _lib is None:
        suffix = '.dylib' if platform.system() == 'Darwin' else '.so'
        lib = C.CDLL(str(Path(__file__).with_name('libpyignite' + suffix)))
        ptr = np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS')
        lib.ignite_pe.argtypes = [C.c_size_t, C.c_size_t, ptr]
        lib.ignite_linear.argtypes = [C.c_size_t]*3 + [ptr]*4 + [C.c_int]
        lib.ignite_pe.restype = lib.ignite_linear.restype = C.c_int
        _lib = lib
    return _lib

def _positive(value):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value <= 0:
        raise ValueError('dimensions must be positive integers')
    return int(value)

def _array(value):
    a = np.asarray(value)
    if a.dtype != np.float32:
        raise TypeError('only float32 arrays are accepted')
    if not np.isfinite(a).all():
        raise ValueError('non-finite tensor')
    return np.ascontiguousarray(a)

def PE1d_sincos(seq_length, dim):
    n, d = _positive(seq_length), _positive(dim)
    if d % 2:
        raise ValueError('dim must be even')
    result = np.empty((n, 1, d), dtype=np.float32)
    if _native().ignite_pe(n, d, result):
        raise ValueError('invalid native dimensions')
    return result

class FCBlock:
    """Eval-only FCBlock built from ordered (weight[out,in], bias[out]) pairs.

    Include all hidden layers followed by the unactivated output projection.
    Eval dropout is identity. Training-mode dropout is deliberately unsupported.
    Weights are copied at construction; arbitrary positive leading dimensions work.
    """
    def __init__(self, layers, *, training=False):
        if training:
            raise ValueError('training is unsupported')
        self._layers = []
        previous = None
        for weight, bias in layers:
            w, b = _array(weight).copy(), _array(bias).copy()
            if w.ndim != 2 or b.ndim != 1 or 0 in w.shape or b.shape != (w.shape[0],):
                raise ValueError('expected weight[out,in], bias[out]')
            if previous is not None and w.shape[1] != previous:
                raise ValueError('disconnected layer dimensions')
            previous = w.shape[0]
            w.flags.writeable = b.flags.writeable = False
            self._layers.append((w, b))
        if len(self._layers) < 2:
            raise ValueError('at least one hidden layer and one projection required')

    @property
    def weight_bytes(self):
        return sum(w.nbytes + b.nbytes for w, b in self._layers)

    def __call__(self, x):
        h = _array(x)
        if h.ndim < 1 or 0 in h.shape or h.shape[-1] != self._layers[0][0].shape[1]:
            raise ValueError('invalid input dimensions')
        leading = h.shape[:-1]
        for i, (w, b) in enumerate(self._layers):
            y = np.empty((*leading, w.shape[0]), dtype=np.float32)
            status = _native().ignite_linear(h.size // h.shape[-1], h.shape[-1],
                w.shape[0], h, w, b, y, int(i < len(self._layers)-1))
            if status:
                raise ValueError('invalid dimensions or non-finite native result')
            h = y
        return h
