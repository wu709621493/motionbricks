import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace

from motionbricks.cornea import HEALTHY, KERATOCONUS, export, make_mesh, validate_mesh


class CorneaTests(unittest.TestCase):
    def test_healthy_axis_symmetry_and_center(self):
        self.assertAlmostEqual(HEALTHY.sample(0, 0)[2], .55)
        for x, y in [(1, 2), (.5, -3), (4, 0)]:
            self.assertEqual(HEALTHY.sample(x, y), HEALTHY.sample(-y, x))

    def test_cone_center_has_specified_displacement_and_thinning(self):
        x, y = KERATOCONUS.cone_x_mm, KERATOCONUS.cone_y_mm
        h, k = HEALTHY.sample(x, y), KERATOCONUS.sample(x, y)
        self.assertAlmostEqual(k[0]-h[0], .28)
        self.assertAlmostEqual(h[2]-k[2], .20)
        self.assertAlmostEqual(k[1]-h[1], .48)
        self.assertLess(k[2], KERATOCONUS.sample(x, -y)[2])

    def test_taper_preserves_edge(self):
        for i in range(72):
            a=2*math.pi*i/72
            h, k = [m.sample(5*math.cos(a), 5*math.sin(a)) for m in (HEALTHY, KERATOCONUS)]
            for v, w in zip(h, k):
                self.assertAlmostEqual(v, w)

    def test_closed_oriented_shells_and_matching_topology(self):
        h, k = [make_mesh(m) for m in (HEALTHY, KERATOCONUS)]
        self.assertEqual(h['faces'], k['faces'])
        for mesh in (h, k):
            result=validate_mesh(mesh)
            n=mesh['surface_vertex_count']
            self.assertEqual(len(mesh['vertices_mm'])-3*len(mesh['faces'])//2+len(mesh['faces']), 2)
            self.assertTrue(result['closed_oriented'])
            for front, back in zip(mesh['vertices_mm'][:n], mesh['vertices_mm'][n:]):
                self.assertEqual(front[:2], back[:2])
                self.assertGreater(front[2], back[2])
        self.assertLess(k['minimum_sampled_axial_thickness_um'], 400)
        self.assertGreater(k['minimum_sampled_axial_thickness_um'], 300)

    def test_validator_rejects_hole_and_flipped_face(self):
        mesh=make_mesh(HEALTHY, 4, 12)
        with self.assertRaises(ValueError):
            validate_mesh(dict(mesh, faces=mesh['faces'][:-1]))
        with self.assertRaises(ValueError):
            validate_mesh(dict(mesh, faces=[mesh['faces'][0][::-1]]+mesh['faces'][1:]))

    def test_invalid_parameters_and_coordinates(self):
        for kwargs in [{'radius_mm': float('nan')}, {'cone_width_mm':0},
                       {'thinning_mm':.6}, {'cone_x_mm':4}, {'protrusion_mm':-.1},
                       {'central_thickness_mm':.3,'thinning_mm':.25}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(HEALTHY, **kwargs)
        for xy in [(6,0), (float('inf'),0)]:
            with self.assertRaises(ValueError):
                HEALTHY.sample(*xy)
        with self.assertRaises(ValueError):
            make_mesh(HEALTHY, True, 72)

    def test_deterministic_export_and_hashes(self):
        template=Path(__file__).resolve().parents[2]/'docs/cornea/viewer.template.html'
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            one,two=export(a,template),export(b,template)
            self.assertEqual(one,two)
            for name,sha in one['files'].items():
                raw=(Path(a)/name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),sha)
                self.assertEqual(raw,(Path(b)/name).read_bytes())
            data=json.loads((Path(a)/'models.json').read_text())
            self.assertTrue(data['synthetic'])
            self.assertNotIn('__CORNEA_DATA__',(Path(a)/'index.html').read_text())
            for mesh in data['models']:
                obj=(Path(a)/(mesh['name']+'.obj')).read_text().splitlines()
                self.assertEqual(sum(s.startswith('v ') for s in obj),len(mesh['vertices_mm']))
                self.assertEqual(sum(s.startswith('f ') for s in obj),len(mesh['faces']))


if __name__ == '__main__':
    unittest.main()
