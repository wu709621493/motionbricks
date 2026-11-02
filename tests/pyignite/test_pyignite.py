import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/pyignite'))
from pyignite import FCBlock, PE1d_sincos

class Contracts(unittest.TestCase):
    def setUp(self):
        self.layers = [(np.eye(2,dtype=np.float32), np.zeros(2,np.float32))]*2
        self.model = FCBlock(self.layers)

    def test_values_and_shape(self):
        x = np.array([[-2,3],[0,1]],np.float32)
        np.testing.assert_allclose(self.model(x), [[-.02,3],[0,1]])
        np.testing.assert_array_equal(PE1d_sincos(1,4), [[[0,1,0,1]]])

    def test_dimensions(self):
        for args in [(0,2),(-1,2),(1,0),(2,3),(True,2),(2.5,2)]:
            with self.subTest(args=args), self.assertRaises(ValueError): PE1d_sincos(*args)
        for shape in [(),(0,2),(3,),(2,0)]:
            with self.subTest(shape=shape), self.assertRaises(ValueError): self.model(np.zeros(shape,np.float32))
        for layers in [[],self.layers[:1],[(np.ones((2,3),np.float32),np.ones(3,np.float32))]*2,
                       [(np.ones((2,3),np.float32),np.ones(2,np.float32))]*2]:
            with self.assertRaises(ValueError): FCBlock(layers)

    def test_nonfinite(self):
        for v in [np.nan,np.inf,-np.inf]:
            with self.subTest(v=v):
                with self.assertRaises(ValueError): self.model(np.array([v,1],np.float32))
                for index in [0,1]:
                    pair = [np.eye(2,dtype=np.float32),np.zeros(2,np.float32)]
                    pair[index].flat[0] = v
                    with self.assertRaises(ValueError): FCBlock([pair,self.layers[1]])

    def test_overflow(self):
        pair = (np.full((2,2),np.finfo(np.float32).max,np.float32),np.zeros(2,np.float32))
        with self.assertRaises(ValueError): FCBlock([pair,self.layers[1]])(np.ones(2,np.float32)*2)

    def test_dtype_and_training(self):
        with self.assertRaises(TypeError): self.model(np.ones(2,np.float64))
        with self.assertRaises(TypeError): FCBlock([(np.eye(2), np.zeros(2))]*2)
        with self.assertRaises(ValueError): FCBlock(self.layers,training=True)

    def test_repeat_and_noncontiguous(self):
        x = np.arange(24,dtype=np.float32).reshape(2,3,4)[:,:,::2]
        original = x.copy()
        for _ in range(100): np.testing.assert_array_equal(self.model(x),original)
        np.testing.assert_array_equal(x, original)
        self.layers[0][0][:] = 0
        np.testing.assert_array_equal(self.model(x),original)

    def test_torch_independent_import(self):
        import subprocess
        subprocess.run([sys.executable,'-c',
            "import sys; sys.path.insert(0, 'tools/pyignite'); import pyignite; assert 'torch' not in sys.modules; pyignite.PE1d_sincos(2,4)"],check=True,
            cwd=Path(__file__).resolve().parents[2])

if __name__ == '__main__': unittest.main()
