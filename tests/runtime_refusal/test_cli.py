# SPDX-License-Identifier: Apache-2.0
"""Independent subprocess regression checks; no model or GPU installation."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOST = f'{platform.system()}/{platform.machine().lower()}'
SUPPORTED = platform.system() in ('Linux', 'Windows') and platform.machine().lower() in ('x86_64', 'amd64')


class RuntimeRefusalTests(unittest.TestCase):
    def cli(self, script, *args):
        result = subprocess.run(
            [sys.executable, '-S', str(Path(__file__).with_name('guarded_cli.py')), script, *args],
            cwd=ROOT, capture_output=True, text=True, timeout=45,
        )
        self.assertNotIn('SAFETY_SENTINEL', result.stderr, result.stderr)
        self.assertNotIn('Traceback', result.stderr, result.stderr)
        print(f'{HOST}: {script} {" ".join(args)} -> {result.returncode}', flush=True)
        return result

    def test_runner_identity(self):
        expected = os.environ.get('REFUSAL_EXPECT_HOST')
        if expected:
            self.assertEqual(HOST, expected)

    def test_default_success_is_not_runtime_success(self):
        for model in ('soma', 'unitree_g1'):
            with self.subTest(model=model):
                result = self.cli('preflight.py', '--model', model, '--json')
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertTrue(report['offline_ok'])
                self.assertFalse(report['runtime_prerequisites_verified'])
                self.assertEqual(report['inference'], 'NOT_RUN')
                self.assertTrue(any(c['status'] == 'FAIL' and c['scope'] == 'runtime' for c in report['checks']))

    def test_require_runtime_refuses(self):
        for model in ('soma', 'unitree_g1'):
            with self.subTest(model=model):
                result = self.cli('preflight.py', '--model', model, '--require-runtime', '--json')
                self.assertEqual(result.returncode, 1, result.stderr)
                report = json.loads(result.stdout)
                self.assertTrue(report['offline_ok'])
                self.assertFalse(report['runtime_prerequisites_verified'])
                self.assertEqual(report['inference'], 'NOT_RUN')
                checks = {c['name']: c for c in report['checks']}
                if SUPPORTED:
                    for name in ('cuda_driver', 'tensorrt_import', 'warp_cuda'):
                        self.assertEqual(checks[name]['status'], 'FAIL')
                        self.assertIn('CPU_TEST_FIXTURE', checks[name]['detail'])
                else:
                    self.assertEqual(checks['runtime_platform']['status'], 'FAIL')
                    self.assertIn(HOST, checks['runtime_platform']['detail'])
                    self.assertIn('unsupported', checks['runtime_platform']['detail'])
                    self.assertEqual(checks['gpu_probes']['status'], 'SKIP')
                    self.assertIn('no native GPU imports attempted', checks['gpu_probes']['detail'])
                    self.assertTrue({'cuda_driver', 'tensorrt_import', 'warp_cuda'}.isdisjoint(checks))

    def test_execute_refuses_before_example_launch(self):
        for model in ('soma', 'unitree_g1'):
            for example in ('generate_once', 'locomotion_loop'):
                with self.subTest(model=model, example=example):
                    result = self.cli('run_example.py', example, '--model', model, '--execute')
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, '')
                    if SUPPORTED:
                        self.assertIn('Not launched: runtime prerequisites are incomplete.', result.stderr)
                        self.assertIn('FAIL cuda_driver: CPU_TEST_FIXTURE', result.stderr)
                    else:
                        self.assertIn(f'Not launched: {HOST} is unsupported', result.stderr)
                        self.assertIn('CPU-only checks', result.stderr)
                        self.assertNotIn('CPU_TEST_FIXTURE', result.stderr)


if __name__ == '__main__':
    unittest.main()
