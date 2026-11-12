import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/pyignite'))
from pyignite import PositionEmbedding


class FrozenPositionContracts(unittest.TestCase):
    def test_saved_buffer_is_authoritative_and_immutable(self):
        # Deliberately not sinusoidal: stored/learned values must be preserved.
        values = np.arange(24, dtype=np.float32).reshape(6, 1, 4)
        model = PositionEmbedding(values)
        values[:] = -99
        with self.assertRaises(ValueError):
            model._embedding.flags.writeable = True
        x = np.zeros((2, 3, 8), np.float32)[:, :, ::2]
        expected = np.broadcast_to(np.arange(12, dtype=np.float32).reshape(1, 3, 4), x.shape)
        for _ in range(3):
            np.testing.assert_array_equal(model(x), expected)
        np.testing.assert_array_equal(x, 0)

    def test_file_hash_and_pickle_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pe.npy'
            np.save(path, np.ones((4, 1, 2), np.float32), allow_pickle=False)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            model = PositionEmbedding.from_npy(path, sha256=sha)
            np.testing.assert_array_equal(model(np.zeros((1, 4, 2), np.float32)), 1)
            path.write_bytes(path.read_bytes() + b'tampered')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                PositionEmbedding.from_npy(path, sha256=sha)
            np.save(path, np.array([{}], dtype=object))
            with self.assertRaises(ValueError):
                PositionEmbedding.from_npy(path, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def test_refuses_invalid_inputs(self):
        for shape in [(2, 4), (2, 2, 4), (0, 1, 4)]:
            with self.assertRaises(ValueError):
                PositionEmbedding(np.zeros(shape, np.float32))
        with self.assertRaises(TypeError):
            PositionEmbedding(np.zeros((2, 1, 4), np.float64))
        with self.assertRaises(ValueError):
            PositionEmbedding(np.zeros((2, 1, 4), np.float32), training=True)
        with self.assertRaises(ValueError):
            PositionEmbedding(np.full((2, 1, 4), np.nan, np.float32))
        model = PositionEmbedding(np.zeros((2, 1, 4), np.float32))
        for shape in [(1, 3, 4), (0, 1, 4), (1, 1, 3), (2, 4)]:
            with self.assertRaises(ValueError):
                model(np.zeros(shape, np.float32))
        with self.assertRaises(TypeError):
            model(np.zeros((1, 1, 4), np.float64))
        with self.assertRaises(ValueError):
            model(np.full((1, 1, 4), np.inf, np.float32))
        maximum = np.finfo(np.float32).max
        with self.assertRaises(ValueError):
            PositionEmbedding(np.full((1, 1, 4), maximum, np.float32))(
                np.full((1, 1, 4), maximum, np.float32))


if __name__ == '__main__':
    unittest.main()
