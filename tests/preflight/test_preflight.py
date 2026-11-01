# SPDX-License-Identifier: Apache-2.0
"""Run with python -m unittest discover -s tests/preflight -v (no runtime dependencies)."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preflight", ROOT / "tools/preflight.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def payload(model):
    _, data = p.manifest(ROOT, model)
    pose = ([[0, 0, 0, 0, 0, 0, 1] for _ in data['joint_names']] if model == 'soma'
            else [0, 0, 0, 0, 0, 0, 1] + [0] * 29)
    return dict(model=model, joint_names=data['joint_names'],
                context=[copy.deepcopy(pose) for _ in range(4)], target=[copy.deepcopy(pose)])


class PoseTests(unittest.TestCase):
    def validate(self, value):
        _, data = p.manifest(ROOT, value['model'])
        p.validate_poses(value, value['model'], data['joint_names'])

    def test_both_rigs_and_target_counts(self):
        for rig in p.RIGS:
            for count in range(1, 5):
                value = payload(rig)
                value['target'] *= count
                self.validate(value)

    def test_bad_frame_counts(self):
        for rig in p.RIGS:
            for field, count in [('context', 3), ('context', 5), ('target', 0), ('target', 5)]:
                value = payload(rig)
                value[field] = [value['context'][0]] * count
                with self.subTest(rig=rig, field=field, count=count), self.assertRaises(ValueError):
                    self.validate(value)

    def test_bad_values(self):
        for rig in p.RIGS:
            for bad in [float('nan'), float('inf'), True, '0', None, 1e39, 10**400]:
                value = payload(rig)
                vector = value['context'][0][0] if rig == 'soma' else value['context'][0]
                vector[0] = bad
                with self.subTest(rig=rig, bad=repr(bad)), self.assertRaises(ValueError):
                    self.validate(value)

    def test_bad_quaternion_and_ragged_shape(self):
        for rig in p.RIGS:
            for bad in ('quaternion', 'shape'):
                value = payload(rig)
                vector = value['target'][0][0] if rig == 'soma' else value['target'][0]
                if bad == 'quaternion':
                    vector[6] = 0
                else:
                    vector.pop()
                with self.subTest(rig=rig, bad=bad), self.assertRaises(ValueError):
                    self.validate(value)

    def test_joint_order_and_missing_joints(self):
        for rig in p.RIGS:
            value = payload(rig)
            value['joint_names'][0], value['joint_names'][1] = value['joint_names'][1], value['joint_names'][0]
            with self.assertRaises(ValueError):
                self.validate(value)

    def test_soma_extra_joints(self):
        value = payload('soma')
        value['joint_names'].append('ExtraFinger')
        for frame in value['context'] + value['target']:
            frame.append([0, 0, 0, 0, 0, 0, 1])
        self.validate(value)

    def test_model_mismatch(self):
        with self.assertRaises(ValueError):
            p.validate_poses(payload('soma'), 'unitree_g1', [])


class AssetTests(unittest.TestCase):
    def test_missing_empty_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'model.onnx'
            self.assertEqual(p.asset_status(path, root)[0], 'FAIL')
            for data in [b'', b'version https://git-lfs.github.com/spec/v1\noid sha256:abc']:
                path.write_bytes(data)
                self.assertEqual(p.asset_status(path, root)[0], 'FAIL')

    def test_hash_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'model.onnx'
            path.write_bytes(b'abc')
            pointer = f'oid sha256:{hashlib.sha256(b"abc").hexdigest()}\nsize 3'
            with patch.object(p, 'command', return_value=(True, pointer)):
                self.assertEqual(p.asset_status(path, root)[0], 'PASS')
                path.write_bytes(b'abd')
                self.assertEqual(p.asset_status(path, root)[0], 'FAIL')
                path.write_bytes(b'abcd')
                self.assertEqual(p.asset_status(path, root)[0], 'FAIL')
            with patch.object(p, 'command', return_value=(False, 'not a git checkout')):
                self.assertEqual(p.asset_status(path, root)[0], 'WARN')


class EnvironmentTests(unittest.TestCase):
    def test_default_does_not_probe_gpu(self):
        with patch.object(p, 'cuda_probe', side_effect=AssertionError('must not probe')):
            report = p.inspect(ROOT)
        self.assertEqual(report['inference'], 'NOT_RUN')
        self.assertEqual(report['checks'][-1]['status'], 'SKIP')

    def test_cuda_library_missing(self):
        with patch.object(p.ctypes, 'CDLL', side_effect=OSError('not installed')):
            self.assertEqual(p._cuda_driver_probe()[0], 'FAIL')

    def test_command_missing(self):
        with patch.object(p.subprocess, 'Popen', side_effect=FileNotFoundError('missing')):
            self.assertFalse(p.command(['missing'])[0])

    def test_tensor_version_mismatch(self):
        with patch.object(p.importlib.metadata, 'version', return_value='0.0'):
            report = p.inspect(ROOT)
        self.assertEqual(sum(c['status'] == 'FAIL' for c in report['checks'] if c['name'].startswith('tensorrt')), 3)

    def test_bad_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = p.inspect(Path(tmp))
        self.assertTrue(any(c['scope'] == 'offline' and c['status'] == 'FAIL' for c in report['checks']))

    def test_cli_valid_and_invalid_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'poses.json'
            value = payload('unitree_g1')
            args = [sys.executable, str(ROOT / 'tools/preflight.py'), '--model', 'unitree_g1', '--poses', str(path), '--json']
            for valid in (True, False):
                if not valid:
                    value['context'] = []
                path.write_text(json.dumps(value))
                result = subprocess.run(args, capture_output=True, text=True)
                report = json.loads(result.stdout)
                self.assertEqual(result.returncode, 0 if valid else 1)
                self.assertEqual(report['offline_ok'], valid)
                self.assertFalse(report['runtime_prerequisites_verified'])

    def test_strict_exit_and_implicit_probe(self):
        from contextlib import redirect_stdout
        import io
        checks = [dict(name='blocked', status='FAIL', scope='runtime', detail='missing')]
        with patch.object(p, 'inspect', return_value=dict(checks=checks)) as inspect, redirect_stdout(io.StringIO()):
            self.assertEqual(p.main(['--require-runtime']), 1)
        self.assertTrue(inspect.call_args.args[3])


if __name__ == '__main__':
    unittest.main()
