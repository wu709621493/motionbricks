"""Independent raster checks and an end-to-end, verified shard scene."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import numpy as np

from motionbricks.memory_lab import MIB, RunConfig, run
from motionbricks.memory_lab_render import Rasterizer, png_bytes, transform
from motionbricks.memory_lab_worker import CpuBlockRuntime


class RenderTests(unittest.TestCase):
    def test_vertex_transform_known_translation(self):
        points = np.array([[1, 2, 3, 1], [0, 0, 0, 1], [-1, 1, 0, 1]], dtype=np.float64)
        matrix = np.eye(4, dtype=np.float64)
        matrix[3, :3] = [2, 3, 4]
        runtime = CpuBlockRuntime(3)
        np.testing.assert_array_equal(transform(runtime, points, matrix),
                                      [[3, 5, 7, 1], [2, 3, 4, 1], [1, 4, 4, 1]])
        self.assertEqual(runtime.launches, 1)

    def test_depth_and_color_are_draw_order_independent(self):
        near = np.array([[1, 1, 1], [7, 1, 1], [1, 7, 1]], dtype=float)
        far = near.copy()
        far[:, 2] = 5
        scenes = []
        for order in ((0, 1), (1, 0)):
            raster = Rasterizer(8, 8)
            for index in order:
                raster.triangle((near, far)[index], ((10, 200, 100), (200, 10, 10))[index], index, index)
            self.assertEqual(raster.depth[2, 2], 1)
            np.testing.assert_array_equal(raster.image[2, 2], [10, 200, 100])
            scenes.append(raster.image)
        np.testing.assert_array_equal(*scenes)

    def test_scalar_barycentric_oracle_and_clipping(self):
        # Right triangle: inside iff x+y<=4, depth z=x+2*y at pixel centres.
        raster = Rasterizer(8, 8)
        raster.triangle([[-2, -2, -6], [6, -2, 2], [-2, 6, 10]], [1, 2, 3], 1, 4)
        for y in range(8):
            for x in range(8):
                inside = (x + .5) + (y + .5) <= 4
                self.assertEqual(np.isfinite(raster.depth[y, x]), inside)
                if inside:
                    self.assertAlmostEqual(raster.depth[y, x], (x + .5) + 2 * (y + .5))

    def test_degenerate_nonfinite_and_offscreen(self):
        raster = Rasterizer(8, 8)
        raster.triangle([[0, 0, 0]] * 3, [1, 2, 3], 0, 0)
        raster.triangle([[-10, -10, 0], [-9, -10, 0], [-10, -9, 0]], [1, 2, 3], 1, 0)
        self.assertFalse(np.isfinite(raster.depth).any())
        with self.assertRaises(ValueError):
            raster.triangle([[float('nan'), 0, 0]] * 3, [1, 2, 3], 2, 0)

    def test_coplanar_tie_uses_stable_id(self):
        for order in ((9, 3), (3, 9)):
            raster = Rasterizer(4, 4)
            for i in order:
                raster.triangle([[0, 0, 1], [4, 0, 1], [0, 4, 1]], [i] * 3, i, i)
            self.assertEqual(raster.owner[0, 0], 3)

    def test_png_roundtrip_without_external_codec(self):
        original = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
        encoded = png_bytes(original)
        self.assertEqual(encoded[:8], b'\x89PNG\r\n\x1a\n')
        pos, compressed, dimensions = 8, b'', None
        while pos < len(encoded):
            size = struct.unpack('>I', encoded[pos:pos + 4])[0]
            kind, data = encoded[pos + 4:pos + 8], encoded[pos + 8:pos + 8 + size]
            crc = struct.unpack('>I', encoded[pos + 8 + size:pos + 12 + size])[0]
            self.assertEqual(crc, zlib.crc32(kind + data) & 0xffffffff)
            if kind == b'IHDR':
                dimensions = struct.unpack('>II', data[:8])
            if kind == b'IDAT':
                compressed += data
            pos += size + 12
        self.assertEqual(dimensions, (3, 2))
        self.assertEqual(zlib.decompress(compressed), b'\0' + original[0].tobytes() + b'\0' + original[1].tobytes())

    def test_full_worker_scene_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scene.png'
            config = RunConfig(logical_shards=12, memory_mib=1, matrix_size=4,
                               cache_sizes=(16,), cache_repeats=1,
                               render_path=str(path), render_width=640, render_height=480)
            result = run(config)
            self.assertEqual(result['status'], 'PASSED', result)
            self.assertEqual(result['rendering']['scene_objects'], 12)
            self.assertEqual(result['rendering']['visible_objects'], 12)
            self.assertEqual(result['rendering']['triangles_submitted'], 144)
            self.assertEqual(result['rendering']['vertices_transformed_and_checked'], 96)
            self.assertEqual(result['rendering']['vertex_kernel_launches'], 24)
            self.assertEqual(result['pseudo_gpu']['launches'], 36)
            self.assertEqual(result['final_words_checked'] * 8, MIB)
            self.assertEqual(result['final_mismatched_words'], 0)
            self.assertTrue(path.is_file())
            before = path.read_bytes()
            refused = run(config)
            self.assertEqual(refused['status'], 'WORKER_FAILED')
            self.assertEqual(before, path.read_bytes())

    def test_render_bounds_affect_budget(self):
        plain = RunConfig()
        render = RunConfig(render_path='scene.png')
        self.assertGreater(render.estimated_bytes, plain.estimated_bytes)
        for fields in ({'render_path': 'scene.svg'}, {'render_width': 2000}, {'render_height': 0}):
            with self.assertRaises(ValueError):
                RunConfig(**fields)


if __name__ == '__main__':
    unittest.main()
