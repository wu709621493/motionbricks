import concurrent.futures
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/pyignite'))
from pyignite import FCBlock


class BackendContracts(unittest.TestCase):
    def test_nonuniform_widths_ranks_and_owned_outputs(self):
        rng = np.random.default_rng(214)
        layers = [(rng.normal(0, .1, (o, i)).astype(np.float32),
                   rng.normal(0, .1, o).astype(np.float32))
                  for i, o in [(7, 11), (11, 3), (3, 13), (13, 5)]]
        for shape in [(7,), (4, 7), (2, 3, 7)]:
            x = rng.normal(size=(*shape[:-1], 14)).astype(np.float32)[..., ::2]
            expected = FCBlock(layers)(x)
            for backend in ('fused', 'numpy'):
                with self.subTest(shape=shape, backend=backend):
                    model = FCBlock(layers, backend=backend)
                    y = model(x)
                    if backend == 'fused':
                        np.testing.assert_array_equal(y, expected)
                    else:
                        np.testing.assert_allclose(y, expected, atol=2e-5, rtol=2e-5)
                    y[:] = -99
                    np.testing.assert_allclose(model(x), expected, atol=2e-5, rtol=2e-5)
                    with self.assertRaises(ValueError):
                        model._layers[0][0].flags.writeable = True

    def test_failures_remain_failures(self):
        identity = (np.eye(2, dtype=np.float32), np.zeros(2, np.float32))
        maximum = np.finfo(np.float32).max
        overflow = (np.full((2, 2), maximum, np.float32), np.zeros(2, np.float32))
        for backend in ('scalar', 'fused', 'numpy'):
            with self.subTest(backend=backend):
                for layers in ([overflow, identity], [identity, overflow]):
                    with self.assertRaises(ValueError):
                        FCBlock(layers, backend=backend)(np.full(2, 2, np.float32))
                model = FCBlock([identity, identity], backend=backend)
                for x in (np.full(2, np.nan, np.float32), np.ones(3, np.float32)):
                    with self.assertRaises(ValueError):
                        model(x)
                with self.assertRaises(TypeError):
                    model(np.ones(2, np.float64))
        with self.assertRaises(ValueError):
            FCBlock([identity, identity], backend='automatic')

    def test_concurrent_calls_use_separate_scratch(self):
        rng = np.random.default_rng(36)
        layers = [(rng.normal(0, .1, (32, 32)).astype(np.float32),
                   np.zeros(32, np.float32))] * 4
        inputs = [rng.normal(size=(8, 32)).astype(np.float32) for _ in range(12)]
        for backend in ('fused', 'numpy'):
            model = FCBlock(layers, backend=backend)
            expected = [model(x) for x in inputs]
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                actual = list(pool.map(model, inputs))
            for a, b in zip(actual, expected):
                np.testing.assert_array_equal(a, b)


if __name__ == '__main__':
    unittest.main()
