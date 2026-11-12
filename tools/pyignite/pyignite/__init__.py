"""Experimental FP32 inference primitives. No torch, autograd or training support."""
import ctypes as C
from pathlib import Path
import platform
import numpy as np
from .position import PositionEmbedding
from .thermal import TemperatureGuard, ThermalSafetyError

__version__ = '0.2.0'
_lib = None

class _Layer(C.Structure):
    _fields_ = [('size_in', C.c_size_t), ('size_out', C.c_size_t),
                ('weight', C.POINTER(C.c_float)), ('bias', C.POINTER(C.c_float))]

def _native():
    global _lib
    if _lib is None:
        suffix = '.dylib' if platform.system() == 'Darwin' else '.so'
        lib = C.CDLL(str(Path(__file__).with_name('libpyignite' + suffix)))
        ptr = np.ctypeslib.ndpointer(dtype=np.float32, flags='C_CONTIGUOUS')
        lib.ignite_pe.argtypes = [C.c_size_t, C.c_size_t, ptr]
        lib.ignite_linear.argtypes = [C.c_size_t]*3 + [ptr]*4 + [C.c_int]
        lib.ignite_fc.argtypes = [C.POINTER(_Layer), C.c_size_t, C.c_size_t,
                                 ptr, ptr, ptr, C.c_size_t]
        lib.ignite_pe.restype = lib.ignite_linear.restype = lib.ignite_fc.restype = C.c_int
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
    backend='scalar' retains the original implementation. 'fused' performs one
    native call for the block; 'numpy' uses NumPy's matrix backend. Selection is
    explicit because the fastest choice depends on shape, BLAS and hardware.
    max_batch_rows optionally bounds hidden activations per chunk, not total RAM.
    """
    def __init__(self, layers, *, training=False, backend='scalar', max_batch_rows=None,
                 temperature_guard=None):
        if training:
            raise ValueError('training is unsupported')
        if backend not in ('scalar', 'fused', 'numpy'):
            raise ValueError('backend must be scalar, fused or numpy')
        self.backend = backend
        self.max_batch_rows = None if max_batch_rows is None else _positive(max_batch_rows)
        self.temperature_guard = temperature_guard
        self._layers = []
        previous = None
        for weight, bias in layers:
            w, b = _array(weight).copy(), _array(bias).copy()
            if w.ndim != 2 or b.ndim != 1 or 0 in w.shape or b.shape != (w.shape[0],):
                raise ValueError('expected weight[out,in], bias[out]')
            if previous is not None and w.shape[1] != previous:
                raise ValueError('disconnected layer dimensions')
            previous = w.shape[0]
            # Bytes-backed arrays cannot have writes re-enabled. This is the
            # ownership contract permitting fused calls to skip weight rescans.
            w = np.frombuffer(w.tobytes(), np.float32).reshape(w.shape)
            b = np.frombuffer(b.tobytes(), np.float32).reshape(b.shape)
            self._layers.append((w, b))
        if len(self._layers) < 2:
            raise ValueError('at least one hidden layer and one projection required')
        self._descriptors = (_Layer * len(self._layers))(*[
            _Layer(w.shape[1], w.shape[0], w.ctypes.data_as(C.POINTER(C.c_float)),
                   b.ctypes.data_as(C.POINTER(C.c_float))) for w, b in self._layers])
        self._width = max(w.shape[0] for w, _ in self._layers[:-1])

    @property
    def weight_bytes(self):
        return sum(w.nbytes + b.nbytes for w, b in self._layers)

    def __call__(self, x):
        guard = self.temperature_guard
        if guard is not None:
            guard.check()
        h = _array(x)
        if h.ndim < 1 or 0 in h.shape or h.shape[-1] != self._layers[0][0].shape[1]:
            raise ValueError('invalid input dimensions')
        rows = h.size // h.shape[-1]
        if guard is not None:
            guard.check_result_size(rows * self._layers[-1][0].shape[0] * 4)
        if self.max_batch_rows is not None and rows > self.max_batch_rows:
            # Bound hidden activations/scratch only. Weights, the contiguous
            # input and complete output still occupy memory. No cache bypass.
            flat = h.reshape(rows, h.shape[-1])
            y = np.empty((rows, self._layers[-1][0].shape[0]), np.float32)
            for start in range(0, rows, self.max_batch_rows):
                if guard is not None:
                    guard.check()
                stop = min(rows, start + self.max_batch_rows)
                y[start:stop] = self._evaluate(flat[start:stop])
                if guard is not None:
                    guard.check()
            result = y.reshape((*h.shape[:-1], y.shape[-1]))
        else:
            result = self._evaluate(h)
        if guard is not None:
            guard.check()
            guard.save_result(result.tobytes(), shape=result.shape, dtype=result.dtype.str)
        return result

    def _evaluate(self, h):
        leading = h.shape[:-1]
        if self.backend == 'fused':
            rows = h.size // h.shape[-1]
            y = np.empty((*leading, self._layers[-1][0].shape[0]), np.float32)
            # Per-call scratch keeps simultaneous calls independent. The two
            # buffers are reused between hidden layers, never across callers.
            workspace = np.empty((2, rows, self._width), np.float32)
            status = _native().ignite_fc(self._descriptors, len(self._layers), rows,
                                        h, y, workspace, self._width)
            if status:
                raise ValueError('invalid dimensions or non-finite native result')
            return y
        for i, (w, b) in enumerate(self._layers):
            y = np.empty((*leading, w.shape[0]), dtype=np.float32)
            if self.backend == 'numpy':
                with np.errstate(over='ignore', invalid='ignore'):
                    np.matmul(h, w.T, out=y)
                    np.add(y, b, out=y)
                if not np.isfinite(y).all():
                    raise ValueError('non-finite matrix result')
                if i < len(self._layers)-1:
                    np.multiply(y, np.float32(.01), out=y, where=y < 0)
                h = y
                continue
            status = _native().ignite_linear(h.size // h.shape[-1], h.shape[-1],
                w.shape[0], h, w, b, y, int(i < len(self._layers)-1))
            if status:
                raise ValueError('invalid dimensions or non-finite native result')
            h = y
        return h

