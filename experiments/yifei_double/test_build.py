# SPDX-License-Identifier: Apache-2.0
"""Geometry and contract tests; no GPU inference implied."""
import math
import json
from pathlib import Path
import tempfile
import unittest
import build


class ChoreographyTests(unittest.TestCase):
    def test_build_utf8_and_pose_export(self):
        with tempfile.TemporaryDirectory() as directory:
            result=build.build(directory)
            output=Path(directory)
            html=(output/'Yifei_Double_Audition.html').read_text(encoding='utf-8')
            self.assertIn('真假刘亦菲',html)
            self.assertNotIn('/*__MOTION_DATA__*/null',html)
            self.assertEqual(json.loads((output/'soma_pose_window.json').read_text(encoding='utf-8')),build.pose_window())
            self.assertEqual(result['frames'],361)
            self.assertEqual(result['model_inference'],'NOT_RUN')

    def test_quaternion_axis_and_composition(self):
        for a,b in zip(build.rotate(build.quaternion(z=90),[1,0,0]),[0,1,0]):
            self.assertAlmostEqual(a,b)

    def test_finite_unit_rotations_and_constant_bones(self):
        for frame in range(361):
            pose=build.pose(frame/30)
            world=build.world_positions(pose)
            for i,(_,parent,offset) in enumerate(build.RIG):
                self.assertTrue(all(math.isfinite(x) for x in pose[i]))
                self.assertAlmostEqual(sum(x*x for x in pose[i][3:]),1.,places=12)
                if parent>=0:
                    self.assertAlmostEqual(math.dist(world[i],world[parent]),math.dist(offset,[0,0,0]),places=12)

    def test_delay_changes_pose_and_zero_delay_is_identical(self):
        a=build.world_positions(build.pose(2.2))
        self.assertEqual(a,build.world_positions(build.pose(2.2)))
        self.assertGreater(sum(math.dist(x,y) for x,y in zip(a,build.world_positions(build.pose(1.9)))),.1)

    def test_clamped_endpoints_and_invalid_time(self):
        self.assertEqual(build.pose(-1),build.pose(0))
        self.assertEqual(build.pose(13),build.pose(12))
        for value in [math.inf,math.nan,-math.inf]:
            with self.assertRaises(ValueError):build.pose(value)

    def test_window_timing(self):
        window=build.pose_window()
        self.assertEqual(window['context'][0],build.pose(3.9))
        self.assertEqual(window['context'][-1],build.pose(4))
        self.assertEqual(window['target'][0],build.pose(5))
        self.assertEqual(len(window['target']),4)


if __name__=='__main__':unittest.main()
