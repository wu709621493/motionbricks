"""Eval-only position addition from an explicit, frozen model buffer."""
import hashlib
import io
from pathlib import Path

import numpy as np


class PositionEmbedding:
    """Add a saved FP32 [sequence, 1, dimension] buffer to [batch, time, dim].

    The supplied buffer is authoritative, including any learned modifications.
    It is never regenerated with the local math library. No training/dropout.
    """

    def __init__(self, embedding, *, training=False):
        if training:
            raise ValueError('training is unsupported')
        a = np.asarray(embedding)
        if a.dtype != np.float32:
            raise TypeError('only float32 arrays are accepted')
        if a.ndim != 3 or a.shape[1] != 1 or 0 in a.shape:
            raise ValueError('expected embedding[sequence, 1, dimension]')
        if not np.isfinite(a).all():
            raise ValueError('non-finite embedding')
        # Immutable bytes prevent callers from re-enabling ndarray writes.
        self._embedding = np.frombuffer(a.tobytes(), dtype=np.float32).reshape(a.shape)

    @classmethod
    def from_npy(cls, path, *, sha256):
        """Load the exact hashed bytes; never unpickle or regenerate a buffer."""
        if (not isinstance(sha256, str) or len(sha256) != 64
                or any(c not in '0123456789abcdef' for c in sha256)):
            raise ValueError('expected a lowercase SHA-256 digest')
        data = Path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError('position buffer SHA-256 mismatch')
        buffer = np.load(io.BytesIO(data), allow_pickle=False)
        if not isinstance(buffer, np.ndarray):
            buffer.close()
            raise ValueError('expected a single NPY array')
        return cls(buffer)

    def __call__(self, x):
        a = np.asarray(x)
        if a.dtype != np.float32:
            raise TypeError('only float32 arrays are accepted')
        if (a.ndim != 3 or 0 in a.shape or a.shape[1] > self._embedding.shape[0]
                or a.shape[2] != self._embedding.shape[2]):
            raise ValueError('expected nonempty [batch, time <= sequence, dimension]')
        if not np.isfinite(a).all():
            raise ValueError('non-finite input')
        with np.errstate(over='ignore', invalid='ignore'):
            result = a + self._embedding[:a.shape[1], 0, :]
        if not np.isfinite(result).all():
            raise ValueError('non-finite position result')
        return np.ascontiguousarray(result)
